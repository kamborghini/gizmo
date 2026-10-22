"""The shop's own website, read behind a guard: which hosts are the store's,
and a fetch that follows redirects only while they stay on those hosts. Learn
my store (gizmo/knowledge.py) reads the site through it. It lived in the SEO
report's file until the report tabs were removed (22 Oct 2026). Read as
`storefront.NAME`.
"""
from typing import Optional
from urllib.parse import urlparse, urljoin
import httpx
from gizmo import config
from gizmo import shopify


_domains_cache: dict = {}


async def _resolve_domains(registry: dict) -> tuple[str, set]:
    """Return (primary_domain, allowed_hosts) for the store. Cached per process."""
    if _domains_cache.get("primary"):
        return _domains_cache["primary"], _domains_cache["hosts"]
    shop = await shopify._tool_json(registry, "shopify_get_shop", {})
    myshop = shop.get("myshopify_domain") or (f"{config.SHOPIFY_STORE}.myshopify.com" if config.SHOPIFY_STORE else "")
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
