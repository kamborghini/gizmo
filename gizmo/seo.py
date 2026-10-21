"""SEO and keywords: the SEO knowledge, reading the store's own site (store
knowledge reads it too), fetching an outside page behind the guard and the
keywords it targets, the SEO and Google data tools the chat is given, the
SEO audit, keywords, the keyword scan and the product audit. Moved out of
copilot.py (stage 4 of the 14 October audit); its routes are in
gizmo/routes/seo.py, but for the product page's, which stays in add_routes.
Read as `seo.NAME`.
"""
import logging
import os
import re
import json
import socket
import asyncio
import ipaddress
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse, urljoin
import httpx
import google_data
from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field
from gizmo.config import _env_num
from gizmo import ai as claude
from gizmo import shopify

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")




# ---------------------------------------------------------------------------
# SEO — knowledge layer + live technical audit
# ---------------------------------------------------------------------------

SEO_SAMPLE_PAGES = _env_num(int, os.environ.get("SEO_SAMPLE_PAGES", "5"), "5", "SEO_SAMPLE_PAGES")
SEO_DETAIL_CAP = 80  # products or pages listed behind a KPI; the card shows the count

SEO_KNOWLEDGE = """## Technical SEO + revenue-optimization expertise (apply this model)
You are the store's optimization intelligence layer. Your job is to help the merchant make more
money by fusing four data sets: technical SEO, Google Search Console (how the store performs in
search), Google Analytics (traffic and on-site behavior), and Shopify commerce (orders, revenue,
products). Find where money is being left on the table and rank fixes by expected revenue impact.

Locate every organic-search issue on the pipeline: Discover, Crawl, Render, Index, Understand,
Rank, Serve. The first four are GATES (binary): if a page cannot be discovered, crawled, rendered,
or indexed, no ranking work matters, so fix gates BEFORE optimizations. Prioritize by
(business impact x confidence) / effort, favoring template and systemic fixes.

High-value cross-referenced opportunities to look for:
- High impressions + low CTR + mid position (roughly 5 to 15) queries: rewrite the title and meta
  to win clicks already being shown. Quantify the click upside.
- Pages or products with strong search/traffic but weak conversion or sales: a merchandising,
  pricing, or page-quality problem, not a traffic problem.
- Best-selling products that rank poorly or lack rich-result schema: protect and grow the winners.
- Traffic with no matching revenue (or vice versa): reconcile GA sessions against Shopify orders.

Correct these on sight:
- robots.txt Disallow is not noindex. Disallow blocks crawling; a disallowed URL can still be
  indexed. To remove from the index: allow crawl plus noindex, then optionally block.
- Canonical is a hint, not a directive. Duplicate content is selection, not a penalty.
- Crawl budget is a non-issue below roughly 100k URLs unless there is severe waste.
- Core Web Vitals (LCP, CLS, INP, not FID) are a minor tiebreaker, not a primary factor.
- Rankings are not traffic, traffic is not revenue. Optimize for the highest business metric.

Shopify-specific traps:
- Faceted/filter and ?variant= URLs create crawl traps and duplicate clusters. Control them via
  canonicals and parameters; do not let them bloat the index.
- Themes and apps can inject accidental noindex or wrong canonicals. Verify the rendered tags.
- Product and collection pages need Product, Offer, and BreadcrumbList JSON-LD. Thin descriptions
  and missing image alt text weaken Understand-stage signals. Collections are topical pillars;
  internal-link them deliberately.

Ground every claim in the supplied data, cite the supporting numbers, name the pipeline stage,
and give dev-ready fixes. Treat Google Search Central, web.dev, and schema.org as ground truth
when an exact threshold or field matters."""

_SEO_HINTS = ("seo", "search engine", "google", "ranking", "rank ", " index", "crawl",
              "robots", "sitemap", "canonical", "meta description", "title tag", "schema",
              "structured data", "keyword", "serp", "backlink", "alt text", "organic")


def _is_seo(messages: list[dict]) -> bool:
    for m in reversed(messages):
        if m.get("role") == "user":
            c = m.get("content")
            text = c if isinstance(c, str) else json.dumps(c)
            return any(h in text.lower() for h in _SEO_HINTS)
    return False


_domains_cache: dict = {}


async def _resolve_domains(registry: dict) -> tuple[str, set]:
    """Return (primary_domain, allowed_hosts) for the store. Cached per process."""
    if _domains_cache.get("primary"):
        return _domains_cache["primary"], _domains_cache["hosts"]
    shop = await shopify._tool_json(registry, "shopify_get_shop", {})
    myshop = shop.get("myshopify_domain") or (f"{core.SHOPIFY_STORE}.myshopify.com" if core.SHOPIFY_STORE else "")
    primary = shop.get("domain") or myshop
    hosts = {h.lower() for h in (primary, myshop) if h}
    if primary:
        _domains_cache["primary"], _domains_cache["hosts"] = primary, hosts
    return primary, hosts


async def _http_get(url: str, allowed_hosts: Optional[set] = None) -> tuple[Optional[int], str]:
    """Fetch a URL, following redirects MANUALLY (max 4 hops). When allowed_hosts
    is given, every hop — including the initial URL — must be on that allow-list,
    which blocks redirect-based SSRF (e.g. a page 302-ing to an internal/metadata
    address). Returns (status, text); ("blocked" hops yield the redirect status, "")."""
    try:
        if allowed_hosts is not None and urlparse(url).netloc.lower() not in allowed_hosts:
            return None, ""
        async with httpx.AsyncClient(follow_redirects=False, timeout=15.0,
                                     headers={"User-Agent": "Reactor-SEO/1.0"}) as c:
            for _ in range(4):
                r = await c.get(url)
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                    nxt = urljoin(url, r.headers["location"])
                    if allowed_hosts is not None and urlparse(nxt).netloc.lower() not in allowed_hosts:
                        return r.status_code, ""  # refuse to follow off-allowlist redirect
                    url = nxt
                    continue
                return r.status_code, r.text
            return None, ""  # too many redirects
    except Exception:
        return None, ""


def _parse_seo(html: str) -> dict:
    soup = BeautifulSoup(html or "", "html.parser")
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    desc_el = soup.find("meta", attrs={"name": "description"})
    desc = (desc_el.get("content") or "").strip() if desc_el else ""
    can_el = soup.find("link", attrs={"rel": lambda v: v and "canonical" in (v if isinstance(v, list) else [v])})
    canonical = (can_el.get("href") or "").strip() if can_el else ""
    rb = soup.find("meta", attrs={"name": "robots"})
    robots = (rb.get("content") or "").strip() if rb else ""
    types: list[str] = []
    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(s.string or "")
        except Exception:
            continue
        for it in (data if isinstance(data, list) else [data]):
            t = it.get("@type") if isinstance(it, dict) else None
            types.extend(t if isinstance(t, list) else [t] if t else [])
    imgs = soup.find_all("img")
    missing_alt = sum(1 for i in imgs if not (i.get("alt") or "").strip())
    return {
        "title": title, "title_len": len(title),
        "meta_description": desc, "meta_description_len": len(desc),
        "canonical": canonical, "meta_robots": robots, "noindex": "noindex" in robots.lower(),
        "jsonld_types": sorted({t for t in types if t}),
        "h1_count": len(soup.find_all("h1")),
        "images": len(imgs), "images_missing_alt": missing_alt,
        "word_count": len(soup.get_text(" ", strip=True).split()),
    }


# ---------------------------------------------------------------------------
# Keyword scraper for arbitrary external URLs (SSRF-guarded) + on-page keywords
# ---------------------------------------------------------------------------


EXTERNAL_FETCH_MAX = _env_num(int, os.environ.get("EXTERNAL_FETCH_MAX", str(600 * 1024)), str(600 * 1024), "EXTERNAL_FETCH_MAX")  # bytes of text kept

_STOPWORDS = set((
    "the a an and or but of to in on for with at by from as is are was were be been being this that "
    "these those it its your you we our us they them their he she his her i me my our ours not no yes "
    "do does did have has had will would can could should may might must shall into over under out up "
    "down off about above below more most some any all each every other than then once here there when "
    "where why how what which who whom whose if else while because so such only own same too very just "
    "get got make made use used new free shop store home page click here read learn back next per via "
    "also one two three com www http https"
).split())


def _ip_is_public(addr: str) -> bool:
    """A public, routable address: not loopback, private, link-local (which is
    where the cloud metadata service lives), reserved, multicast or unspecified."""
    try:
        ip = ipaddress.ip_address(str(addr).split("%")[0])
    except ValueError:
        return False
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified)


def _host_is_public(host: str) -> bool:
    """True only if every resolved IP for host is a public, routable address.
    Used to gate external scraping."""
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    if not infos:
        return False
    return all(_ip_is_public(info[4][0]) for info in infos)


async def _fetch_external(url: str) -> tuple[Optional[int], str, str]:
    """Fetch an arbitrary http(s) URL with SSRF protection: validates the scheme and
    that the host resolves only to public IPs, on the initial URL AND every redirect
    hop (redirects are followed manually). Returns (status, final_url, text)."""
    for _ in range(5):
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            raise RuntimeError("Enter a full http or https URL.")
        if not await asyncio.to_thread(_host_is_public, p.hostname):
            raise RuntimeError("That address is not allowed (only public websites can be scanned).")
        async with httpx.AsyncClient(follow_redirects=False, timeout=12.0,
                                     headers={"User-Agent": "Reactor-SEO/1.0"}) as c:
            async with c.stream("GET", url) as r:
                # The check above resolved the name once; the client resolves
                # it again to connect, and a name whose records alternate can
                # answer the second lookup with a private address. So the
                # address actually connected to is checked before a byte of
                # the body is read: whatever answered on the inside is never
                # shown, and never reaches the model.
                stream = r.extensions.get("network_stream")
                peer = stream.get_extra_info("server_addr") if stream is not None else None
                if peer and not _ip_is_public(peer[0]):
                    raise RuntimeError("That address is not allowed (only public websites can be scanned).")
                # Read no more than is kept. Reading the whole body first held
                # a video or an endless page in the one worker's memory (the
                # timeout is per read, not per response) before cutting it.
                held = bytearray()
                async for chunk in r.aiter_bytes():
                    held += chunk
                    if len(held) >= EXTERNAL_FETCH_MAX:
                        break
                body = bytes(held[:EXTERNAL_FETCH_MAX])
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
            url = urljoin(url, r.headers["location"])
            continue
        try:
            text = body.decode(r.charset_encoding or "utf-8", "replace")
        except LookupError:
            text = body.decode("utf-8", "replace")
        return r.status_code, str(r.url), text[:EXTERNAL_FETCH_MAX]
    raise RuntimeError("Too many redirects.")


def _extract_page_keywords(html_text: str) -> dict:
    """Pull on-page keyword signals: title, meta, headings, and the top single terms
    and two-word phrases by frequency (stopwords removed)."""
    from collections import Counter
    soup = BeautifulSoup(html_text or "", "html.parser")
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    desc_el = soup.find("meta", attrs={"name": "description"})
    desc = (desc_el.get("content") or "").strip() if desc_el else ""
    kw_el = soup.find("meta", attrs={"name": "keywords"})
    meta_kw = (kw_el.get("content") or "").strip() if kw_el else ""
    h1 = [h.get_text(" ", strip=True) for h in soup.find_all("h1")][:10]
    h2 = [h.get_text(" ", strip=True) for h in soup.find_all("h2")][:25]
    h3 = [h.get_text(" ", strip=True) for h in soup.find_all("h3")][:25]
    for t in soup(["script", "style", "noscript"]):
        t.extract()
    text = soup.get_text(" ", strip=True).lower()
    words = re.findall(r"[a-z][a-z'-]{2,}", text)
    toks = [w for w in words if w not in _STOPWORDS and len(w) > 2]
    uni = Counter(toks)
    bigrams = Counter(toks[i] + " " + toks[i + 1] for i in range(len(toks) - 1)
                      if toks[i] not in _STOPWORDS and toks[i + 1] not in _STOPWORDS)
    return {
        "title": title, "title_len": len(title), "meta_description": desc, "meta_keywords": meta_kw,
        "h1": h1, "h2": h2, "h3": h3, "word_count": len(words),
        "top_terms": [{"term": t, "count": c} for t, c in uni.most_common(25)],
        "top_phrases": [{"term": t, "count": c} for t, c in bigrams.most_common(15) if c > 1],
    }


async def _seo_product_signals(registry: dict) -> dict:
    products, ok, _truncated = await core._all_products(registry, "id,title,handle,body_html,images")
    if not ok:
        # A read that failed is not a catalogue with nothing wrong in it: the
        # audit said "0 thin descriptions" and took nothing off the score.
        return {"unavailable": True, "products_sampled": 0, "thin_descriptions": 0,
                "missing_descriptions": 0, "duplicate_titles": 0, "images": 0,
                "images_missing_alt": 0, "alt_coverage_pct": None, "thin_items": [],
                "missing_items": [], "alt_items": [], "duplicate_groups": []}
    by_title: dict[str, list[dict]] = {}
    thin = no_desc = total_imgs = missing_alt = 0
    # The products behind each count, so a KPI can open the list it counted
    # (capped: the card shows the count, the list shows where to start).
    thin_items: list[dict] = []
    missing_items: list[dict] = []
    alt_items: list[dict] = []
    for p in products:
        t = (p.get("title") or "").strip().lower()
        ident = {"title": p.get("title") or p.get("handle") or "", "handle": p.get("handle")}
        by_title.setdefault(t, []).append(ident)
        wc = len(re.sub("<[^>]+>", " ", p.get("body_html") or "").split())
        if wc == 0:
            no_desc += 1
            missing_items.append({**ident, "words": 0})
        elif wc < 50:
            thin += 1
            thin_items.append({**ident, "words": wc})
        n_imgs = n_missing = 0
        for img in p.get("images", []):
            total_imgs += 1
            n_imgs += 1
            if not (img.get("alt") or "").strip():
                missing_alt += 1
                n_missing += 1
        if n_missing:
            alt_items.append({**ident, "missing": n_missing, "images": n_imgs})
    dup_groups = [{"title": items[0]["title"], "count": len(items), "handles": [i["handle"] for i in items]}
                  for items in by_title.values() if len(items) > 1]
    return {
        "products_sampled": len(products),
        "thin_descriptions": thin, "missing_descriptions": no_desc,
        "duplicate_titles": len(dup_groups),
        "images": total_imgs, "images_missing_alt": missing_alt,
        "alt_coverage_pct": round(100 * (total_imgs - missing_alt) / total_imgs) if total_imgs else None,
        "thin_items": sorted(thin_items, key=lambda i: i["words"])[:SEO_DETAIL_CAP],
        "missing_items": missing_items[:SEO_DETAIL_CAP],
        "alt_items": sorted(alt_items, key=lambda i: -i["missing"])[:SEO_DETAIL_CAP],
        "duplicate_groups": sorted(dup_groups, key=lambda g: -g["count"])[:SEO_DETAIL_CAP],
    }


def _seo_scorecard(signals: dict, rs, ss, pages: list[dict], domain: str | None = None,
                   sitemap_locs: int | None = None) -> tuple[int | None, list[dict]]:
    """The score, and one KPI per check. Every KPI carries a `detail`: the
    pages or products behind its number, so the card can open them. The score
    is None when the product read failed: three of its checks never ran, so a
    number would read as passing them, and the change alert would compare it
    with the last whole one."""
    score = 100
    any_noindex = any(p.get("noindex") for p in pages)
    has_product_schema = any("Product" in (p.get("jsonld_types") or []) for p in pages)
    sitemap_ok, robots_ok = ss == 200, rs == 200
    md_pct = round(100 * sum(1 for p in pages if p.get("meta_description")) / len(pages)) if pages else 0
    alt = signals.get("alt_coverage_pct")
    thin = signals.get("thin_descriptions", 0)
    dup = signals.get("duplicate_titles", 0)
    unread = bool(signals.get("unavailable"))   # the product read failed: say so, deduct nothing
    unread_note = "Shopify did not answer the product read, so this was not checked."

    deductions: list[dict] = []
    if any_noindex:        score -= 25; deductions.append({"label": "noindex found on a sampled page", "note": "-25"})
    if not sitemap_ok:     score -= 10; deductions.append({"label": "sitemap.xml missing", "note": "-10"})
    if not robots_ok:      score -= 5;  deductions.append({"label": "robots.txt missing", "note": "-5"})
    # The page checks mark pages. With none sampled there is nothing to mark,
    # as with a failed product read: say so and deduct nothing, rather than
    # take 24 points for a schema and meta descriptions nobody looked at.
    if not pages:
        deductions.append({"label": "page checks not run: the storefront could not be crawled",
                           "note": "not scored"})
    if pages and not has_product_schema: score -= 12; deductions.append({"label": "no Product JSON-LD on the sampled pages", "note": "-12"})
    if alt is not None and alt < 90:
        d = min(15, (90 - alt) // 5 * 2); score -= d; deductions.append({"label": f"image alt coverage {alt}%", "note": f"-{d}"})
    if pages and md_pct < 90:
        d = min(12, (90 - md_pct) // 10 * 3); score -= d; deductions.append({"label": f"meta descriptions on {md_pct}% of pages", "note": f"-{d}"})
    if thin:
        d = min(10, thin); score -= d; deductions.append({"label": f"{thin} thin product descriptions", "note": f"-{d}"})
    if dup:
        d = min(10, dup); score -= d; deductions.append({"label": f"{dup} duplicated product titles", "note": f"-{d}"})
    score = max(0, min(100, score))
    if unread:
        # The sentence goes in the label: the note is the figure column,
        # where a sentence sat among the -10s and -5s.
        deductions.append({"label": "product checks not run: Shopify did not answer the product read",
                           "note": "not scored"})

    def purl(handle):
        return f"https://{domain}/products/{handle}" if (domain and handle) else None

    def detail(title, items, empty, total=None):
        return {"title": title, "items": items, "empty": empty, "total": total if total is not None else len(items)}

    noindex_pages = [{"label": p.get("url"), "note": p.get("meta_robots") or "noindex", "url": p.get("url")}
                     for p in pages if p.get("noindex")]
    schema_pages = [{"label": p.get("url"), "note": ", ".join(p.get("jsonld_types") or []) or "no JSON-LD", "url": p.get("url")}
                    for p in pages]
    no_meta_pages = [{"label": p.get("url"), "note": "no meta description", "url": p.get("url")}
                     for p in pages if not p.get("meta_description")]
    thin_items = [{"label": i["title"], "note": (f"{i['words']} words" if i.get("words") else "no description"),
                   "url": purl(i.get("handle"))}
                  for i in (signals.get("missing_items") or []) + (signals.get("thin_items") or [])]
    alt_items = [{"label": i["title"], "note": f"{i['missing']} of {i['images']} images without alt", "url": purl(i.get("handle"))}
                 for i in signals.get("alt_items") or []]
    dup_items = [{"label": g["title"], "note": f"{g['count']} products", "url": purl((g.get("handles") or [None])[0])}
                 for g in signals.get("duplicate_groups") or []]
    # A fetch that never answered has no status: it read 'HTTP None'.
    def http(code):
        return f"HTTP {code}" if code else "No answer"
    site_items = [{"label": f"https://{domain}/sitemap.xml" if domain else "sitemap.xml",
                   "note": (http(ss) + (f" · {sitemap_locs} locations" if sitemap_ok and sitemap_locs else "")),
                   "url": f"https://{domain}/sitemap.xml" if domain else None},
                  {"label": f"https://{domain}/robots.txt" if domain else "robots.txt", "note": http(rs),
                   "url": f"https://{domain}/robots.txt" if domain else None}]
    n_pages = len(pages)
    # No page could be sampled: the page checks did not run, and saying '0% of
    # sampled' in warning colour, over 'Every one of the 0 sampled pages has a
    # meta description', claimed a result that nobody measured.
    no_pages = "The storefront could not be crawled, so no pages were sampled."

    metrics = [
        {"label": "SEO score", "value": "n/a" if unread else f"{score}/100",
         "tone": "warn" if unread or score < 70 else None,
         "detail": detail("How the score is made", deductions, "No deductions: every check passed.")},
        {"label": "Indexable", "value": ("Not checked" if not n_pages else "noindex found" if any_noindex else "Yes"),
         "tone": "unknown" if not n_pages else ("warn" if any_noindex else None),
         "detail": detail("Sampled pages blocked from the index", noindex_pages,
                          f"All {n_pages} sampled pages are indexable." if n_pages else no_pages)},
        {"label": "Sitemap", "value": "OK" if sitemap_ok else "Missing", "tone": None if sitemap_ok else "warn",
         "detail": detail("Crawl files", site_items, "")},
        {"label": "Product schema", "value": ("Not checked" if not n_pages else "Present" if has_product_schema else "Missing"),
         "tone": ("unknown" if not n_pages else None if has_product_schema else "warn"),
         "detail": detail("Structured data on the sampled pages", schema_pages, no_pages)},
        {"label": "Meta descriptions", "value": f"{md_pct}%" if n_pages else "Not checked",
         "note": "of sampled pages have one" if n_pages else None,
         "tone": ("unknown" if not n_pages else "warn" if md_pct < 90 else None),
         "detail": detail("Sampled pages without a meta description", no_meta_pages,
                          f"Every one of the {n_pages} sampled pages has a meta description." if n_pages else no_pages)},
        {"label": "Image alt", "value": f"{alt}%" if alt is not None else "n/a",
         "tone": "warn" if (alt is not None and alt < 90) else None,
         "detail": detail("Products with images missing alt text", alt_items,
                          unread_note if unread else "Every product image has alt text.",
                          total=len(signals.get("alt_items") or []))},
        {"label": "Thin descriptions", "value": "n/a" if unread else str(thin), "tone": "warn" if thin else None,
         "detail": detail("Products with under 50 words of description", thin_items,
                          unread_note if unread else "Every product has at least 50 words.",
                          total=thin + signals.get("missing_descriptions", 0))},
        {"label": "Duplicate titles", "value": "n/a" if unread else str(dup), "tone": "warn" if dup else None,
         "detail": detail("Titles shared by more than one product", dup_items,
                          unread_note if unread else "Every product title is unique.", total=dup)},
    ]
    return (None if unread else score), metrics


class SeoFetchPageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path_or_url: str = Field(..., description="A path like '/products/handle' or a full URL on THIS store's domain.")


class SeoEmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _build_seo_tools(registry: dict) -> dict:
    async def seo_fetch_page(params: SeoFetchPageInput) -> str:
        """Fetch a page on THIS store's storefront and return its on-page SEO signals: title,
        meta description, canonical, meta robots/noindex, JSON-LD types, H1 count, image alt
        coverage, and word count. Accepts a path like '/products/handle' or a full store URL."""
        primary, hosts = await _resolve_domains(registry)
        if not primary:
            return json.dumps({"error": "Could not resolve the store domain."})
        raw = (params.path_or_url or "").strip()
        if raw.startswith("http"):
            if urlparse(raw).netloc.lower() not in hosts:
                return json.dumps({"error": f"Refused: only this store's domain ({primary}) can be fetched."})
            url = raw
        else:
            url = f"https://{primary}/{raw.lstrip('/')}"
        status, html = await _http_get(url, allowed_hosts=hosts)
        if not status:
            return json.dumps({"error": f"Could not fetch {url}"})
        return json.dumps({"url": url, "status": status, **_parse_seo(html)}, default=str)

    async def seo_check_robots_sitemap(params: SeoEmptyInput) -> str:
        """Fetch this store's robots.txt and sitemap.xml and summarize their health
        (found, whether robots references the sitemap, risky Disallow rules, sitemap size)."""
        primary, hosts = await _resolve_domains(registry)
        rs, rtext = await _http_get(f"https://{primary}/robots.txt", allowed_hosts=hosts)
        ss, stext = await _http_get(f"https://{primary}/sitemap.xml", allowed_hosts=hosts)
        return json.dumps({
            "robots_txt": {"status": rs, "found": rs == 200,
                           "references_sitemap": "sitemap" in (rtext or "").lower(),
                           "disallows_products": "Disallow: /products" in (rtext or ""),
                           "disallows_collections": "Disallow: /collections" in (rtext or ""),
                           "sample": (rtext or "")[:1500]},
            "sitemap_xml": {"status": ss, "found": ss == 200, "child_locs": (stext or "").count("<loc>")},
        }, default=str)

    return {
        "seo_fetch_page": (seo_fetch_page, SeoFetchPageInput),
        "seo_check_robots_sitemap": (seo_check_robots_sitemap, SeoEmptyInput),
    }


# ---------------------------------------------------------------------------
# Google data chat tools (only registered when GSC/GA4 is configured)
# ---------------------------------------------------------------------------

class DaysInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    days: Optional[int] = Field(default=28, ge=1, le=180, description="Look-back window in days.")


def _google_not_ready(key: str) -> str:
    """Why the chat cannot read one Google source: an unticked permission is
    not the same as no connection, and saying so tells the person what to do."""
    if google_data.oauth_connected() and google_data.granted().get(key) is False:
        name = {"gsc": "Search Console", "ga4": "Analytics"}[key]
        return json.dumps({"error": f"Google is connected without permission to read {name}. "
                                    f"Connect Google again in Settings and leave {name} ticked."})
    return json.dumps({"error": "Google isn't connected yet. Connect it in Settings."})


def _build_google_tools() -> dict:
    tools: dict = {}
    if google_data.gsc_enabled():
        async def get_search_console_data(params: DaysInput) -> str:
            """Real Google Search Console data for this store: total clicks, impressions, CTR and
            average position, plus the top search queries (with per-query impressions/CTR/position).
            Use this to ground SEO advice in how the store actually performs in Google Search —
            e.g. high-impression, low-CTR, mid-position queries are title/meta rewrite opportunities."""
            if not google_data.gsc_configured():
                return _google_not_ready("gsc")
            days = params.days or 28
            return json.dumps({"overview": await google_data.gsc_overview(days),
                               "top_queries": await google_data.gsc_top_queries(days)}, default=str)
        tools["get_search_console_data"] = (get_search_console_data, DaysInput)

    if google_data.ga4_enabled():
        async def get_ga4_data(params: DaysInput) -> str:
            """Real Google Analytics 4 data for this store: sessions, revenue, engaged sessions and
            the top traffic channels over the window. Use to ground answers about traffic, acquisition
            and on-site performance in real analytics rather than order data alone."""
            if not google_data.ga4_configured():
                return _google_not_ready("ga4")
            return json.dumps(await google_data.ga4_summary(params.days or 28), default=str)
        tools["get_ga4_data"] = (get_ga4_data, DaysInput)

    return tools


async def run_seo_audit(registry: dict, extra_system: str = "") -> dict:
    claude._ai_kind.set("seo")
    primary, hosts = await _resolve_domains(registry)
    if not primary:
        raise RuntimeError("Could not resolve the store's domain to audit.")
    gsc_on, ga4_on = google_data.gsc_configured(), google_data.ga4_configured()
    since28 = (datetime.now(timezone.utc) - timedelta(days=28)).isoformat()
    # First wave: every independent input at once (product signals, robots, sitemap, a product
    # sample for page audits, Search Console + Analytics, shop, and 28-day orders).
    signals, robots, sitemap, sample, gsc_ov, gsc_tq, ga_sum, shop, o28r = await asyncio.gather(
        _seo_product_signals(registry),
        _http_get(f"https://{primary}/robots.txt", allowed_hosts=hosts),
        _http_get(f"https://{primary}/sitemap.xml", allowed_hosts=hosts),
        shopify._tool_json(registry, "shopify_list_products", {"limit": SEO_SAMPLE_PAGES, "fields": "handle"}),
        google_data.gsc_overview(28) if gsc_on else analytics._ret({}),
        google_data.gsc_top_queries(28) if gsc_on else analytics._ret({}),
        google_data.ga4_summary(28) if ga4_on else analytics._ret({}),
        shopify._tool_json(registry, "shopify_get_shop", {}),
        orderbook._orders_28d(registry),
    )
    rs, rtext = robots
    ss, stext = sitemap
    shop = shop or {}
    urls = [f"https://{primary}/"] + [f"https://{primary}/products/{p['handle']}"
                                      for p in sample.get("products", []) if p.get("handle")]
    urls = urls[:SEO_SAMPLE_PAGES + 1]
    # Second wave: fetch the sampled pages concurrently.
    fetched = await asyncio.gather(*[_http_get(u, allowed_hosts=hosts) for u in urls])
    pages = [{"url": u, "status": st, **_parse_seo(html)} for u, (st, html) in zip(urls, fetched) if st]

    score, metrics = _seo_scorecard(signals, rs, ss, pages, domain=primary,
                                    sitemap_locs=(stext or "").count("<loc>"))
    context = {
        "domain": primary, "computed_seo_score": score,
        # the counts only: the item lists are for the cards, not the model;
        # and no counts at all from a read that failed, whose zeros are not findings
        "product_signals": ({"unavailable": True, "note": "Shopify did not answer the product read, "
                                                         "so the product checks and the score were not worked out."}
                            if signals.get("unavailable")
                            else {k: v for k, v in signals.items() if not isinstance(v, list)}),
        "robots_txt": {"status": rs, "found": rs == 200, "sample": (rtext or "")[:1000]},
        "sitemap_xml": {"status": ss, "found": ss == 200, "child_locs": (stext or "").count("<loc>")},
        "sampled_pages": pages,
    }
    if gsc_on:
        context["search_console"] = {"overview": gsc_ov, "top_queries": gsc_tq}
    if ga4_on:
        context["analytics"] = ga_sum

    # Shopify commerce context: 28-day revenue, orders, and best sellers.
    o28 = list(o28r or [])
    from collections import Counter
    units: Counter = Counter()
    o28 = [o for o in o28 if orderbook._order_counts(o)]
    for o in o28:
        for li in o.get("line_items", []):
            if li.get("title"):
                units[li["title"]] += li.get("quantity") or 0
    context["commerce"] = {
        "currency": shop.get("currency"),
        "revenue_28d": round(sum(orderbook._order_revenue(o) for o in o28), 2),
        "orders_28d": len(o28),
        "top_products_28d": [{"title": t, "units": q} for t, q in units.most_common(8)],
    }

    client = claude._anthropic()
    msg = ("Optimization intelligence for this Shopify store (collected live, fusing technical SEO, "
           "Google Search Console, Google Analytics, and Shopify commerce):\n"
           + json.dumps(context, indent=2, default=str)
           + "\n\nProduce the report now via present_response. Goal: help the merchant make more money. "
             "Lead with the highest-impact, revenue-ranked opportunities in `actions` (each with the "
             "supporting numbers and the expected impact). Use `insights` for the most important "
             "performance issues and wins, cross-referencing the data sets. Fix indexation and crawl "
             "gates before optimizations. Be specific and quantify in money or percent wherever you can.")
    # Fetch the search trend series WHILE the model writes the report.
    resp, gts = await asyncio.gather(
        claude._xcreate(client,
            model=claude.MODEL_DEEP, max_tokens=claude.MAX_TOKENS,
            system=prompts.OVERVIEW_SYSTEM + "\n\n" + SEO_KNOWLEDGE + extra_system,
            tools=[prompts.PRESENT_RESPONSE_TOOL], tool_choice={"type": "tool", "name": prompts.PRESENT_RESPONSE_TOOL["name"]},
            messages=[{"role": "user", "content": msg}],
            output_config={"effort": core._effort_for(claude.MODEL_DEEP)},
        ),
        google_data.gsc_timeseries(480) if gsc_on else analytics._ret({}),
    )
    structured = assistant._coerce_structured(prompts._report_answer(resp, "the SEO audit"))
    structured.pop("metrics", None)
    seo_trends: dict = {}
    try:
        if gsc_on and isinstance(gts, dict) and not gts.get("error"):
            for k in ("clicks", "impressions", "ctr", "position"):
                if gts.get(k):
                    seo_trends[k] = gts[k]
    except Exception:
        logger.exception("seo trends failed")
    out = {"score": score, "metrics": metrics, "structured": structured, "trends": seo_trends}
    if score is None:
        out["score_note"] = ("Not worked out this time: Shopify did not answer the product read, "
                             "so three of the checks could not run.")
    return out


# ---------------------------------------------------------------------------
# Keyword + CPC intelligence, and the external-URL keyword scanner
# ---------------------------------------------------------------------------

async def run_keywords(registry: dict, extra_system: str = "") -> dict:
    """Fuse Search Console keywords with Google Ads (via GA4) into a money-ranked
    keyword + CPC plan. Returns the AI analysis plus the raw keyword list and ad data
    for the UI tables. Degrades gracefully when Google is not connected."""
    claude._ai_kind.set("keywords")
    days = 90
    gsc_ok = google_data.gsc_configured()
    ga4_ok = google_data.ga4_configured()
    overview, top, ads, shop = await asyncio.gather(
        google_data.gsc_overview(days) if gsc_ok else analytics._ret({}),
        google_data.gsc_top_queries(days, limit=100) if gsc_ok else analytics._ret({}),
        google_data.ga4_ads(days) if ga4_ok else analytics._ret({}),
        shopify._tool_json(registry, "shopify_get_shop", {}),
    )
    shop = shop or {}
    currency = shop.get("currency", "")
    queries = top.get("queries", []) if isinstance(top, dict) else []

    metrics: list[dict] = []
    if overview and not overview.get("error"):
        metrics.append({"label": "Search clicks (90d)", "value": f"{overview.get('clicks', 0):,}"})
        metrics.append({"label": "Impressions (90d)", "value": f"{overview.get('impressions', 0):,}"})
        if overview.get("ctr") is not None:
            metrics.append({"label": "Avg CTR", "value": f"{overview.get('ctr', 0)}%"})
        if overview.get("position") is not None:
            metrics.append({"label": "Avg position", "value": str(overview.get("position"))})
    if ads and ads.get("totals") and ads.get("has_ads"):
        t = ads["totals"]
        metrics.append({"label": "Ad spend (90d)", "value": analytics._money(t["cost"], currency)})
        metrics.append({"label": "Avg CPC", "value": f"{t['cpc']:.2f} {currency}".strip()})
        if t.get("roas"):
            metrics.append({"label": "ROAS", "value": f"{t['roas']}x"})

    context = {"currency": currency, "range_days": days,
               "search_console_overview": overview, "top_queries": queries,
               "google_ads_via_ga4": ads}
    client = claude._anthropic()
    msg = ("Keyword and paid-search data for this store (collected live):\n"
           + json.dumps(context, indent=2, default=str)
           + "\n\nProduce a money-ranked keyword and cost-per-click optimization plan via present_response. "
             "Lead with the highest-value opportunities in `actions` (each with the supporting numbers and "
             "expected impact). Use `insights` for the key findings across organic search and paid. Use "
             "`sections` for supporting detail. If paid data is absent, focus on organic and say what to "
             "connect. Be specific and quantify in money or percent.")
    resp = await claude._xcreate(client,
        model=claude.MODEL_DEEP, max_tokens=claude.MAX_TOKENS,
        system=prompts.OVERVIEW_SYSTEM + "\n\n" + prompts.KEYWORD_SYSTEM + extra_system,
        tools=[prompts.PRESENT_RESPONSE_TOOL], tool_choice={"type": "tool", "name": prompts.PRESENT_RESPONSE_TOOL["name"]},
        messages=[{"role": "user", "content": msg}],
        output_config={"effort": core._effort_for(claude.MODEL_DEEP)},
    )
    structured = assistant._coerce_structured(prompts._report_answer(resp, "the keyword analysis"))
    structured.pop("metrics", None)
    return {"metrics": metrics, "structured": structured, "currency": currency,
            "keywords": queries, "ads": ads if (ads and not ads.get("error")) else None,
            "gsc_connected": gsc_ok, "ga4_connected": ga4_ok}


async def run_keyword_scan(registry: dict, url: str, extra_system: str = "") -> dict:
    """Scrape an external URL (SSRF-guarded), extract its on-page keyword targeting,
    and have Claude analyze what it targets and how the merchant can compete."""
    claude._ai_kind.set("keyword_scan")
    status, final_url, html_text = await _fetch_external(url)
    if not html_text:
        raise RuntimeError("Could not read that page (it returned no readable HTML).")
    extracted = _extract_page_keywords(html_text)
    ours = await google_data.gsc_top_queries(90, limit=40) if google_data.gsc_configured() else {}
    context = {"scanned_url": final_url, "http_status": status, "page": extracted,
               "your_top_queries": (ours.get("queries") if isinstance(ours, dict) else [])}
    client = claude._anthropic()
    msg = ("On-page keyword extraction from an external URL (treat it as a competitor or reference page):\n"
           + json.dumps(context, indent=2, default=str)
           + "\n\nAnalyze it via present_response. In `summary`, state the page's primary topic and the "
             "keywords it targets. Use `insights` for what it does well and where it is weak. Use `actions` "
             "for specific keywords, topics or pages the merchant should create or optimize to compete, "
             "cross-referencing the merchant's own queries when provided. Be concrete and prioritized.")
    resp = await claude._xcreate(client,
        model=claude.MODEL_DEEP, max_tokens=claude.MAX_TOKENS,
        system=prompts.OVERVIEW_SYSTEM + "\n\n" + prompts.KEYWORD_SYSTEM + extra_system,
        tools=[prompts.PRESENT_RESPONSE_TOOL], tool_choice={"type": "tool", "name": prompts.PRESENT_RESPONSE_TOOL["name"]},
        messages=[{"role": "user", "content": msg}],
        output_config={"effort": core._effort_for(claude.MODEL_DEEP)},
    )
    structured = assistant._coerce_structured(prompts._report_answer(resp, "the scan"))
    structured.pop("metrics", None)
    return {"url": final_url, "extracted": extracted, "structured": structured}


async def run_product_audit(registry: dict, product_id: int, extra_system: str = "") -> dict:
    claude._ai_kind.set("product")
    p = await shopify._tool_json(registry, "shopify_get_product", {"product_id": product_id})
    if not p or not p.get("id"):
        raise RuntimeError("Product not found.")
    extra_system = extra_system + skillbook._skills_to_system(" ".join(["product plan", str(p.get("title") or ""),
                                                              str(p.get("product_type") or ""), str(p.get("tags") or "")]))
    handle = p.get("handle") or ""
    path = f"/products/{handle}"
    primary, hosts = await _resolve_domains(registry)

    page = {}
    if primary and handle:
        st, html = await _http_get(f"https://{primary}{path}", allowed_hosts=hosts)
        if st and html:
            page = {"url": f"https://{primary}{path}", "status": st, **_parse_seo(html)}

    gsc = await google_data.gsc_page_queries(path) if google_data.gsc_configured() else {}
    ga = await google_data.ga4_page(path) if google_data.ga4_configured() else {}

    units, rev = 0, 0.0
    for o in await orderbook._orders_28d(registry):
        for li in o.get("line_items", []):
            if li.get("product_id") == product_id:
                qty = li.get("quantity") or 0
                units += qty
                rev += float(li.get("price") or 0) * qty
    shop = await shopify._tool_json(registry, "shopify_get_shop", {})
    currency = shop.get("currency", "")
    imgs = p.get("images", []) or []

    context = {
        "product": {
            "title": p.get("title"), "handle": handle, "status": p.get("status"),
            "price": (p.get("variants") or [{}])[0].get("price"),
            "product_type": p.get("product_type"), "tags": p.get("tags"),
            "description_words": len(re.sub("<[^>]+>", " ", p.get("body_html") or "").split()),
            "images": len(imgs),
            "images_missing_alt": sum(1 for i in imgs if not (i.get("alt") or "").strip()),
        },
        "page_seo": page,
        "search_console": gsc,
        "analytics": ga,
        "sales_28d": {"units": units, "revenue": round(rev, 2), "currency": currency},
    }
    client = claude._anthropic()
    msg = ("Per-product optimization data for one product (collected live):\n"
           + json.dumps(context, indent=2, default=str)
           + "\n\nProduce a focused, money-ranked optimization plan for THIS product via present_response. "
             "Lead with the highest-impact opportunities in `actions` (with the supporting numbers and the "
             "expected impact). Use `insights` for the key findings across search, traffic, sales and on-page "
             "SEO. Be specific to this product and quantify wherever you can.")
    resp = await claude._xcreate(client,
        model=claude.MODEL_DEEP, max_tokens=claude.MAX_TOKENS,
        system=prompts.OVERVIEW_SYSTEM + "\n\n" + SEO_KNOWLEDGE + extra_system,
        tools=[prompts.PRESENT_RESPONSE_TOOL], tool_choice={"type": "tool", "name": prompts.PRESENT_RESPONSE_TOOL["name"]},
        messages=[{"role": "user", "content": msg}],
        output_config={"effort": core._effort_for(claude.MODEL_DEEP)},
    )
    structured = assistant._coerce_structured(prompts._report_answer(resp, "the optimisation plan"))
    structured.pop("metrics", None)

    metrics = []
    if gsc and gsc.get("totals"):
        t = gsc["totals"]
        metrics += [{"label": "Search clicks (28d)", "value": f"{t.get('clicks', 0):,}"},
                    {"label": "Impressions (28d)", "value": f"{t.get('impressions', 0):,}"}]
        if t.get("position"):
            metrics.append({"label": "Avg position", "value": str(t["position"])})
    if ga and not ga.get("error") and ("sessions" in ga):
        metrics.append({"label": "Sessions (28d)", "value": f"{ga.get('sessions', 0):,}"})
    metrics.append({"label": "Units sold (28d)", "value": str(units)})
    metrics.append({"label": "Revenue (28d)", "value": analytics._money(rev, currency)})

    trend = {"units": [], "revenue": []}
    try:
        months = orderbook._month_axis(core.PRODUCT_TREND_MONTHS)
        p_orders = await orderbook._orders_snapshot(registry, days=len(months) * 31)
        b = orderbook._orders_product_monthly(p_orders, months).get(product_id, {"units": {}, "revenue": {}})
        trend = {"units": [{"label": mk, "value": b["units"].get(mk, 0)} for mk in months],
                 "revenue": [{"label": mk, "value": round(b["revenue"].get(mk, 0.0), 2)} for mk in months]}
    except Exception:
        logger.exception("product trend failed")
    return {"product": {"title": p.get("title"), "handle": handle}, "metrics": metrics,
            "structured": structured, "trend": trend, "currency": currency}


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as core.NAME and sibling.NAME, never a copied name.
from gizmo import analytics  # noqa: E402
from gizmo import orderbook  # noqa: E402
from gizmo import skills as skillbook  # noqa: E402
from gizmo import prompts  # noqa: E402
import copilot as core  # noqa: E402
from gizmo import chat as assistant  # noqa: E402
