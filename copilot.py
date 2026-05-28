#!/usr/bin/env python3
"""
Store Copilot — an embedded Shopify admin chat backed by Claude.

This module adds an in-admin chat experience to the existing MCP server:
  GET  /            -> serves the chat page (App Bridge when embedded)
  POST /api/chat    -> runs a Claude tool-use loop over the store's data

It REUSES the Shopify tool functions already defined in server.py (passed in
as a registry), so there is one source of truth for Shopify API access.

Auth on /api/chat (either is accepted):
  1. Shopify session token (Bearer JWT from App Bridge) — used when embedded.
  2. A shared dashboard password (X-Dashboard-Password) — used standalone.

Required env vars:
  ANTHROPIC_API_KEY     Claude API key (sk-ant-...). Required to chat.
  ANTHROPIC_MODEL       Optional. Defaults to claude-sonnet-4-6.
  SHOPIFY_API_KEY       App client ID. Enables embedded/App Bridge mode.
  SHOPIFY_API_SECRET    App client secret. Verifies session tokens.
  DASHBOARD_PASSWORD    Enables standalone password mode (optional fallback).
"""
import os
import re
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
from urllib.parse import urlparse

import anthropic
import httpx
import jwt
from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse

logger = logging.getLogger("shopify_mcp.copilot")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
# Hybrid models: a fast model for normal chat, a deep model for heavy analysis.
MODEL_FAST = os.environ.get("ANTHROPIC_MODEL_FAST") or os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-6"
MODEL_DEEP = os.environ.get("ANTHROPIC_MODEL_DEEP", "claude-opus-4-7")
LOW_STOCK_THRESHOLD = int(os.environ.get("LOW_STOCK_THRESHOLD", "5"))
# App Bridge identity = the app's Client ID + secret. Accept either the
# SHOPIFY_API_KEY/SECRET names or the SHOPIFY_CLIENT_ID/SECRET names (same values).
SHOPIFY_API_KEY    = os.environ.get("SHOPIFY_API_KEY") or os.environ.get("SHOPIFY_CLIENT_ID", "")
SHOPIFY_API_SECRET = os.environ.get("SHOPIFY_API_SECRET") or os.environ.get("SHOPIFY_CLIENT_SECRET", "")
SHOPIFY_STORE      = os.environ.get("SHOPIFY_STORE", "")        # used to pin session tokens to this shop
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")

# Headers applied to every API/page response (defense in depth).
_API_HEADERS = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}

MAX_TOOL_ROUNDS    = int(os.environ.get("COPILOT_MAX_TOOL_ROUNDS", "12"))
MAX_TOKENS         = int(os.environ.get("COPILOT_MAX_TOKENS", "4096"))
TOOL_RESULT_CAP    = int(os.environ.get("COPILOT_TOOL_RESULT_CAP", "50000"))
STORE_CONTEXT_CAP  = int(os.environ.get("STORE_CONTEXT_CAP", "4000"))
# Server-side store profile. Default path lives under /data so a Railway volume
# mounted there makes it durable across redeploys.
PROFILE_PATH       = os.environ.get("PROFILE_PATH", "/data/store_profile.json")
PROFILE_FIELD_CAP  = int(os.environ.get("PROFILE_FIELD_CAP", "6000"))

_PAGE_PATH = os.path.join(os.path.dirname(__file__), "static", "index.html")
_page_cache: Optional[str] = None

SYSTEM_PROMPT = """You are Store Copilot, a senior e-commerce analyst embedded in the admin of a \
Shopify store. You help the merchant understand and grow their store.

How you work:
- Always ground answers in real data — use the read tools to look things up before making any claim, \
number, or suggestion. Never invent figures, product names, or IDs. Call shopify_get_shop when you \
need the store's currency or timezone.
- You have READ-ONLY access. You cannot create, update, or delete anything. If asked to make a change, \
explain exactly what to change and where in the admin to do it, but be clear you can't perform writes.
- Gather data efficiently: request multiple tools in parallel when they're independent.

How you answer — IMPORTANT:
- When you have what you need, you MUST deliver your final answer by calling the `present_response` \
tool. Do not write the final answer as plain prose. Everything the merchant sees comes from that call.
- Put the headline in `summary` (1–2 sentences). Use `metrics` for the key numbers, `insights` for \
notable findings (type them as win/warning/opportunity/insight), `sections` for supporting detail, \
`actions` for concrete prioritized recommendations, and `followups` for 2–4 natural next questions.
- Only include fields that add value — a simple factual answer can be just `summary` (+ maybe a metric \
or two). Don't pad. Be specific and reference real figures from the store."""

OVERVIEW_SYSTEM = """You are a senior Shopify analyst writing an executive overview. You are given the \
store's current KPIs (already computed from live data). Identify what truly matters: wins, risks or \
anomalies, and the highest-impact opportunities — specific to these numbers, not generic advice. \
Deliver everything by calling `present_response`: a one-line `summary`, 2–4 `insights` \
(win/warning/opportunity/insight), 2–4 prioritized `actions`, and 3 `followups` the merchant might ask. \
Do not restate every metric; interpret them."""

# Final-answer tool: forces clean structured output instead of raw markdown.
PRESENT_RESPONSE_TOOL = {
    "name": "present_response",
    "description": (
        "Present your final answer to the merchant as structured UI. Call this once, as your LAST "
        "action, after gathering any data you need. Everything shown to the merchant comes from here."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "The headline answer, 1–2 sentences."},
            "metrics": {
                "type": "array",
                "description": "Key figures to show as stat cards. Omit if not relevant.",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "value": {"type": "string"},
                        "delta": {"type": "string", "description": "Optional change, e.g. '+12%'."},
                        "trend": {"type": "string", "enum": ["up", "down", "flat"]},
                    },
                    "required": ["label", "value"],
                },
            },
            "insights": {
                "type": "array",
                "description": "Notable findings as color-coded callouts.",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["insight", "win", "warning", "opportunity"]},
                        "title": {"type": "string"},
                        "detail": {"type": "string"},
                    },
                    "required": ["type", "title"],
                },
            },
            "sections": {
                "type": "array",
                "description": "Expandable detail sections.",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "body": {"type": "string", "description": "Short paragraphs or '- ' bullet lines."},
                    },
                    "required": ["title", "body"],
                },
            },
            "actions": {
                "type": "array",
                "description": "Concrete recommended actions, most impactful first.",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                    },
                    "required": ["text"],
                },
            },
            "followups": {
                "type": "array",
                "description": "2–4 natural next questions the merchant might ask.",
                "items": {"type": "string"},
            },
        },
        "required": ["summary"],
    },
}

# Heuristic: escalate to the deep model for broad, analytical asks.
_DEEP_HINTS = (
    "analyz", "audit", "full", "overall", "everything", "deep", "strateg", "grow",
    "optimi", "improve my", "whole store", "all my", "report", "forecast", "why are",
)


def _pick_model(messages: list[dict], deep: bool) -> str:
    if deep:
        return MODEL_DEEP
    last = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            c = m.get("content")
            last = c if isinstance(c, str) else json.dumps(c)
            break
    low = last.lower()
    return MODEL_DEEP if any(h in low for h in _DEEP_HINTS) else MODEL_FAST


def _context_block(context: Optional[str]) -> str:
    """Format ad-hoc custom instructions (legacy single-field) as a system addendum."""
    if not context or not str(context).strip():
        return ""
    text = str(context).strip()[:STORE_CONTEXT_CAP]
    return ("\n\n## Store profile — set by the merchant (authoritative)\n"
            "Follow these preferences and constraints in every answer; never contradict them:\n"
            + text)


def _load_profile() -> dict:
    try:
        with open(PROFILE_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_profile(data: dict) -> dict:
    data = data or {}
    prefs = data.get("prefs") or {}
    clean = {
        "brand_voice": str(data.get("brand_voice", ""))[:PROFILE_FIELD_CAP],
        "business_goals": str(data.get("business_goals", ""))[:PROFILE_FIELD_CAP],
        "strategy": str(data.get("strategy", ""))[:PROFILE_FIELD_CAP],
        "notes": str(data.get("notes", ""))[:PROFILE_FIELD_CAP],
        "prefs": {
            "track_inventory": bool(prefs.get("track_inventory", True)),
            "concise": bool(prefs.get("concise", False)),
            "proactive": bool(prefs.get("proactive", True)),
            "flag_anomalies": bool(prefs.get("flag_anomalies", True)),
        },
    }
    os.makedirs(os.path.dirname(PROFILE_PATH) or ".", exist_ok=True)
    tmp = PROFILE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(clean, fh)
    os.replace(tmp, PROFILE_PATH)
    return clean


def _profile_to_system(p: dict) -> str:
    """Compose the stored profile into an authoritative system addendum."""
    if not p:
        return ""
    fields = []
    for key, label in (("brand_voice", "Brand voice"), ("business_goals", "Business goals"),
                       ("strategy", "Overall strategy"), ("notes", "Other notes")):
        val = (p.get(key) or "").strip()
        if val:
            fields.append(f"- {label}: {val}")
    prefs = p.get("prefs") or {}
    rules = []
    if prefs.get("track_inventory") is False:
        rules.append("We carry unlimited stock — never give inventory, stock-level, or restock advice.")
    if prefs.get("concise"):
        rules.append("Keep answers concise and skimmable; favor short bullets over prose.")
    if prefs.get("proactive", True):
        rules.append("Always surface 1–3 concrete recommendations or opportunities, even when not asked.")
    if prefs.get("flag_anomalies", True):
        rules.append("Proactively flag anomalies, risks, or unusual changes you notice in the data.")
    if not fields and not rules:
        return ""
    block = "\n\n## Store profile — set by the merchant (authoritative; follow in every answer)\n"
    if fields:
        block += "\n".join(fields) + "\n"
    if rules:
        block += "Preferences:\n" + "\n".join("- " + r for r in rules)
    return block


# ---------------------------------------------------------------------------
# Anthropic tool schema + dispatch (derived from the injected registry)
# ---------------------------------------------------------------------------
# registry: dict[str, tuple[async_callable, pydantic_model_cls]]

def _build_tools(registry: dict) -> list[dict]:
    """Derive Anthropic tool schemas from the Shopify functions + Pydantic models."""
    tools = []
    for name, (func, model) in registry.items():
        schema = model.model_json_schema()
        schema.pop("title", None)
        tools.append({
            "name": name,
            "description": (func.__doc__ or "").strip(),
            "input_schema": schema,
        })
    return tools


def _build_dispatch(registry: dict) -> Callable:
    async def dispatch(name: str, args: dict) -> str:
        entry = registry.get(name)
        if not entry:
            return f"Unknown tool: {name}"
        func, model = entry
        try:
            payload = model(**(args or {}))
        except Exception as e:
            return f"Invalid arguments for {name}: {e}"
        result = await func(payload)
        result = str(result)
        if len(result) > TOOL_RESULT_CAP:
            result = result[:TOOL_RESULT_CAP] + "\n…[truncated — narrow your query for more]"
        return result
    return dispatch


# ---------------------------------------------------------------------------
# Claude tool-use loop
# ---------------------------------------------------------------------------
_client: Optional[anthropic.AsyncAnthropic] = None


def _anthropic() -> anthropic.AsyncAnthropic:
    global _client
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set on the server. Add it in Railway → Variables."
        )
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def _coerce_structured(data: Any) -> dict:
    """Make sure we always hand the UI a dict with at least a summary string."""
    if not isinstance(data, dict):
        return {"summary": str(data)}
    if not isinstance(data.get("summary"), str) or not data["summary"].strip():
        data["summary"] = "Here's what I found."
    return data


async def run_chat(history: list[dict], dispatch: Callable, data_tools: list[dict],
                   model: str, extra_system: str = "") -> dict:
    """Run a multi-step tool-use conversation. The final answer is delivered via
    the present_response tool and returned as a structured dict."""
    client = _anthropic()
    messages = list(history)
    tools_used: list[str] = []
    all_tools = data_tools + [PRESENT_RESPONSE_TOOL]
    system = SYSTEM_PROMPT + extra_system

    for _ in range(MAX_TOOL_ROUNDS):
        resp = await client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=system,
            tools=all_tools,
            messages=messages,
        )

        assistant_blocks: list[dict] = []
        data_uses: list[Any] = []
        present: Optional[dict] = None
        for block in resp.content:
            if block.type == "text":
                assistant_blocks.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_blocks.append({
                    "type": "tool_use", "id": block.id, "name": block.name, "input": block.input,
                })
                if block.name == PRESENT_RESPONSE_TOOL["name"]:
                    present = block.input
                else:
                    data_uses.append(block)
        messages.append({"role": "assistant", "content": assistant_blocks})

        if present is not None:
            return {"structured": _coerce_structured(present), "tools_used": tools_used, "model": model}

        if not data_uses:
            # Ended without present_response — wrap any prose as the summary.
            text = "".join(b["text"] for b in assistant_blocks if b["type"] == "text").strip()
            return {"structured": {"summary": text or "(no response)"}, "tools_used": tools_used, "model": model}

        tool_results = []
        for tu in data_uses:
            tools_used.append(tu.name)
            logger.info(f"copilot tool call: {tu.name}")  # name only — inputs may contain PII
            tool_results.append({
                "type": "tool_result", "tool_use_id": tu.id,
                "content": await dispatch(tu.name, tu.input),
            })
        messages.append({"role": "user", "content": tool_results})

    return {
        "structured": {"summary": "I gathered a lot of data but couldn't finalize an answer. "
                                  "Please narrow the question and try again."},
        "tools_used": tools_used, "model": model,
    }


# ---------------------------------------------------------------------------
# Overview — live KPIs (computed deterministically) + AI insight pass
# ---------------------------------------------------------------------------

async def _tool_json(registry: dict, name: str, args: dict) -> dict:
    func, model = registry[name]
    try:
        return json.loads(await func(model(**(args or {}))))
    except Exception:
        return {}


def _money(amount: float, currency: str) -> str:
    try:
        return f"{amount:,.0f} {currency}".strip()
    except Exception:
        return f"{amount} {currency}".strip()


def _delta(cur: float, prev: float) -> tuple[Optional[str], str]:
    if prev <= 0:
        return (None, "flat")
    change = (cur - prev) / prev * 100
    trend = "up" if change > 1 else "down" if change < -1 else "flat"
    return (f"{'+' if change >= 0 else ''}{change:.0f}%", trend)


async def _compute_metrics(registry: dict, track_inventory: bool = True) -> tuple[list[dict], dict]:
    now = datetime.now(timezone.utc)
    d7, d14 = (now - timedelta(days=7)).isoformat(), (now - timedelta(days=14)).isoformat()
    metrics: list[dict] = []

    shop = await _tool_json(registry, "shopify_get_shop", {})
    currency = shop.get("currency", "")

    o7 = (await _tool_json(registry, "shopify_list_orders",
                           {"status": "any", "created_at_min": d7, "limit": 250})).get("orders", [])
    op = (await _tool_json(registry, "shopify_list_orders",
                           {"status": "any", "created_at_min": d14, "created_at_max": d7, "limit": 250})).get("orders", [])
    rev7 = sum(float(o.get("total_price") or 0) for o in o7)
    revp = sum(float(o.get("total_price") or 0) for o in op)
    n7, npv = len(o7), len(op)
    aov = rev7 / n7 if n7 else 0
    unfulfilled = sum(1 for o in o7 if o.get("fulfillment_status") in (None, "partial", "unfulfilled"))

    rev_delta, rev_trend = _delta(rev7, revp)
    ord_delta, ord_trend = _delta(n7, npv)
    metrics.append({"label": "Revenue (7d)", "value": _money(rev7, currency), "delta": rev_delta, "trend": rev_trend})
    metrics.append({"label": "Orders (7d)", "value": str(n7), "delta": ord_delta, "trend": ord_trend})
    metrics.append({"label": "Avg order value", "value": _money(aov, currency)})
    metrics.append({"label": "Unfulfilled (7d)", "value": str(unfulfilled), "tone": "warn" if unfulfilled else None})

    new_cust = len((await _tool_json(registry, "shopify_list_customers",
                                     {"created_at_min": d7, "limit": 250})).get("customers", []))
    metrics.append({"label": "New customers (7d)", "value": str(new_cust)})

    total_products = (await _tool_json(registry, "shopify_count_products", {})).get("count")
    if total_products is not None:
        metrics.append({"label": "Products", "value": str(total_products)})

    low = []
    if track_inventory:
        products = (await _tool_json(registry, "shopify_list_products",
                                     {"limit": 250, "fields": "id,title,variants"})).get("products", [])
        low = [
            {"product": p.get("title"), "variant": v.get("title"), "qty": v.get("inventory_quantity")}
            for p in products for v in p.get("variants", [])
            if isinstance(v.get("inventory_quantity"), int) and v["inventory_quantity"] <= LOW_STOCK_THRESHOLD
        ]
        metrics.append({"label": f"Low stock (≤{LOW_STOCK_THRESHOLD})", "value": str(len(low)),
                        "tone": "warn" if low else None})

    from collections import Counter
    units = Counter()
    for o in o7:
        for li in o.get("line_items", []):
            if li.get("title"):
                units[li["title"]] += li.get("quantity") or 0

    context = {
        "shop": {"name": shop.get("name"), "currency": currency},
        "last_7d": {"revenue": round(rev7, 2), "orders": n7, "aov": round(aov, 2),
                    "unfulfilled": unfulfilled, "new_customers": new_cust},
        "prev_7d": {"revenue": round(revp, 2), "orders": npv},
        "catalog": ({"total_products": total_products, "low_stock_count": len(low),
                     "low_stock_examples": low[:8]} if track_inventory
                    else {"total_products": total_products, "inventory": "not tracked — unlimited stock"}),
        "top_products_7d": [{"title": t, "units": q} for t, q in units.most_common(5)],
        "note": "Order figures are based on up to 250 orders per 7-day window.",
    }
    return [m for m in metrics if m.get("value") is not None], context


async def run_overview(registry: dict, extra_system: str = "", track_inventory: bool = True) -> dict:
    metrics, context = await _compute_metrics(registry, track_inventory)
    client = _anthropic()
    msg = ("Current store KPIs (computed live):\n" + json.dumps(context, indent=2, default=str)
           + "\n\nGive the executive overview now by calling present_response.")
    resp = await client.messages.create(
        model=MODEL_FAST, max_tokens=MAX_TOKENS, system=OVERVIEW_SYSTEM + extra_system,
        tools=[PRESENT_RESPONSE_TOOL], tool_choice={"type": "tool", "name": PRESENT_RESPONSE_TOOL["name"]},
        messages=[{"role": "user", "content": msg}],
    )
    present = next((b.input for b in resp.content
                    if b.type == "tool_use" and b.name == PRESENT_RESPONSE_TOOL["name"]), None)
    structured = _coerce_structured(present or {"summary": "Here's your store overview."})
    structured.pop("metrics", None)  # UI shows the computed metrics, not Claude's echo
    return {"metrics": metrics, "structured": structured}


# ---------------------------------------------------------------------------
# SEO — knowledge layer + live technical audit
# ---------------------------------------------------------------------------

SEO_SAMPLE_PAGES = int(os.environ.get("SEO_SAMPLE_PAGES", "5"))

SEO_KNOWLEDGE = """## Technical SEO expertise (apply this model)
Locate every organic-search issue on the pipeline: Discover → Crawl → Render → Index →
Understand → Rank → Serve. The first four are GATES (binary): if a page can't be discovered,
crawled, rendered, or indexed, no ranking work matters — fix gates BEFORE optimizations.
Prioritize by (business impact × confidence) ÷ effort, favoring template/systemic fixes.

Correct these on sight:
- robots.txt Disallow ≠ noindex. Disallow blocks crawling; a disallowed URL can still be
  indexed. To remove from index: allow crawl + noindex, then optionally block.
- Canonical is a hint, not a directive. Duplicate content is selection, not a penalty.
- Crawl budget is a non-issue below ~100k URLs unless there's severe waste.
- Core Web Vitals (LCP/CLS/INP, not FID) are a minor tiebreaker, not a primary factor.
- Rankings ≠ traffic ≠ revenue — optimize for intent and the highest business metric.

Shopify-specific traps:
- Faceted/filter and ?variant= URLs create crawl traps and duplicate clusters — control via
  canonicals/parameters, don't let them bloat the index.
- Themes/apps can inject accidental noindex or wrong canonicals — verify the rendered tags.
- Product/Collection pages need Product/Offer/BreadcrumbList JSON-LD; thin descriptions and
  missing image alt text weaken Understand-stage signals. Collections are topical pillars —
  internal-link them deliberately.

Ground every claim in the supplied data, name the pipeline stage, and give dev-ready fixes.
Treat Google Search Central / web.dev / schema.org as ground truth when an exact threshold
or field matters."""

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
    shop = await _tool_json(registry, "shopify_get_shop", {})
    myshop = shop.get("myshopify_domain") or (f"{SHOPIFY_STORE}.myshopify.com" if SHOPIFY_STORE else "")
    primary = shop.get("domain") or myshop
    hosts = {h.lower() for h in (primary, myshop) if h}
    if primary:
        _domains_cache["primary"], _domains_cache["hosts"] = primary, hosts
    return primary, hosts


async def _http_get(url: str) -> tuple[Optional[int], str]:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0,
                                     headers={"User-Agent": "StoreCopilot-SEO/1.0"}) as c:
            r = await c.get(url)
            return r.status_code, r.text
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


async def _seo_product_signals(registry: dict) -> dict:
    data = await _tool_json(registry, "shopify_list_products",
                            {"limit": 250, "fields": "id,title,handle,body_html,images"})
    products = data.get("products", [])
    titles: dict = {}
    thin = no_desc = total_imgs = missing_alt = 0
    for p in products:
        t = (p.get("title") or "").strip().lower()
        titles[t] = titles.get(t, 0) + 1
        wc = len(re.sub("<[^>]+>", " ", p.get("body_html") or "").split())
        if wc == 0:
            no_desc += 1
        elif wc < 50:
            thin += 1
        for img in p.get("images", []):
            total_imgs += 1
            if not (img.get("alt") or "").strip():
                missing_alt += 1
    return {
        "products_sampled": len(products),
        "thin_descriptions": thin, "missing_descriptions": no_desc,
        "duplicate_titles": sum(1 for c in titles.values() if c > 1),
        "images": total_imgs, "images_missing_alt": missing_alt,
        "alt_coverage_pct": round(100 * (total_imgs - missing_alt) / total_imgs) if total_imgs else None,
    }


def _seo_scorecard(signals: dict, rs, ss, pages: list[dict]) -> tuple[int, list[dict]]:
    score = 100
    any_noindex = any(p.get("noindex") for p in pages)
    has_product_schema = any("Product" in (p.get("jsonld_types") or []) for p in pages)
    sitemap_ok, robots_ok = ss == 200, rs == 200
    md_pct = round(100 * sum(1 for p in pages if p.get("meta_description")) / len(pages)) if pages else 0
    alt = signals.get("alt_coverage_pct")
    thin = signals.get("thin_descriptions", 0)
    dup = signals.get("duplicate_titles", 0)

    if any_noindex:        score -= 25
    if not sitemap_ok:     score -= 10
    if not robots_ok:      score -= 5
    if not has_product_schema: score -= 12
    if alt is not None and alt < 90:   score -= min(15, (90 - alt) // 5 * 2)
    if md_pct < 90:        score -= min(12, (90 - md_pct) // 10 * 3)
    if thin:               score -= min(10, thin)
    if dup:                score -= min(10, dup)
    score = max(0, min(100, score))

    metrics = [
        {"label": "SEO score", "value": f"{score}/100", "tone": "warn" if score < 70 else None},
        {"label": "Indexable", "value": "noindex found" if any_noindex else "Yes",
         "tone": "warn" if any_noindex else None},
        {"label": "Sitemap", "value": "OK" if sitemap_ok else "Missing", "tone": None if sitemap_ok else "warn"},
        {"label": "Product schema", "value": "Present" if has_product_schema else "Missing",
         "tone": None if has_product_schema else "warn"},
        {"label": "Meta descriptions", "value": f"{md_pct}% of sampled", "tone": "warn" if md_pct < 90 else None},
        {"label": "Image alt", "value": f"{alt}%" if alt is not None else "n/a",
         "tone": "warn" if (alt is not None and alt < 90) else None},
        {"label": "Thin descriptions", "value": str(thin), "tone": "warn" if thin else None},
        {"label": "Duplicate titles", "value": str(dup), "tone": "warn" if dup else None},
    ]
    return score, metrics


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
        status, html = await _http_get(url)
        if not status:
            return json.dumps({"error": f"Could not fetch {url}"})
        return json.dumps({"url": url, "status": status, **_parse_seo(html)}, default=str)

    async def seo_check_robots_sitemap(params: SeoEmptyInput) -> str:
        """Fetch this store's robots.txt and sitemap.xml and summarize their health
        (found, whether robots references the sitemap, risky Disallow rules, sitemap size)."""
        primary, _ = await _resolve_domains(registry)
        rs, rtext = await _http_get(f"https://{primary}/robots.txt")
        ss, stext = await _http_get(f"https://{primary}/sitemap.xml")
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


async def run_seo_audit(registry: dict) -> dict:
    primary, _ = await _resolve_domains(registry)
    if not primary:
        raise RuntimeError("Could not resolve the store's domain to audit.")
    signals = await _seo_product_signals(registry)
    rs, rtext = await _http_get(f"https://{primary}/robots.txt")
    ss, stext = await _http_get(f"https://{primary}/sitemap.xml")

    urls = [f"https://{primary}/"]
    sample = await _tool_json(registry, "shopify_list_products", {"limit": SEO_SAMPLE_PAGES, "fields": "handle"})
    urls += [f"https://{primary}/products/{p['handle']}" for p in sample.get("products", []) if p.get("handle")]
    pages = []
    for u in urls[:SEO_SAMPLE_PAGES + 1]:
        st, html = await _http_get(u)
        if st:
            pages.append({"url": u, "status": st, **_parse_seo(html)})

    score, metrics = _seo_scorecard(signals, rs, ss, pages)
    context = {
        "domain": primary, "computed_seo_score": score, "product_signals": signals,
        "robots_txt": {"status": rs, "found": rs == 200, "sample": (rtext or "")[:1000]},
        "sitemap_xml": {"status": ss, "found": ss == 200, "child_locs": (stext or "").count("<loc>")},
        "sampled_pages": pages,
    }
    client = _anthropic()
    msg = ("Technical SEO audit data for this Shopify store (collected live):\n"
           + json.dumps(context, indent=2, default=str)
           + "\n\nProduce the audit now via present_response. Lead with the highest-impact, "
             "gates-first fixes; be specific to this data; cite the pipeline stage per finding.")
    resp = await client.messages.create(
        model=MODEL_FAST, max_tokens=MAX_TOKENS, system=OVERVIEW_SYSTEM + "\n\n" + SEO_KNOWLEDGE,
        tools=[PRESENT_RESPONSE_TOOL], tool_choice={"type": "tool", "name": PRESENT_RESPONSE_TOOL["name"]},
        messages=[{"role": "user", "content": msg}],
    )
    present = next((b.input for b in resp.content
                    if b.type == "tool_use" and b.name == PRESENT_RESPONSE_TOOL["name"]), None)
    structured = _coerce_structured(present or {"summary": "SEO audit complete."})
    structured.pop("metrics", None)
    return {"score": score, "metrics": metrics, "structured": structured}


# ---------------------------------------------------------------------------
# Auth: Shopify session token OR dashboard password
# ---------------------------------------------------------------------------

def _verify_session_token(token: str) -> dict:
    if not SHOPIFY_API_SECRET:
        raise RuntimeError("SHOPIFY_API_SECRET not configured")
    claims = jwt.decode(
        token,
        SHOPIFY_API_SECRET,
        algorithms=["HS256"],
        audience=SHOPIFY_API_KEY or None,
        leeway=5,
        options={"require": ["exp", "nbf"], "verify_aud": bool(SHOPIFY_API_KEY)},
    )
    # Defense in depth: only accept tokens minted for this store.
    if SHOPIFY_STORE:
        expected = f"https://{SHOPIFY_STORE}.myshopify.com"
        if claims.get("dest") != expected:
            raise jwt.InvalidTokenError(f"session token dest mismatch")
    return claims


def _authorize(request: Request, body: dict) -> tuple[bool, Optional[str]]:
    """Return (ok, who). Accepts a Shopify session token (Bearer header) or the
    dashboard password (request body, with legacy header fallback)."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer ") and SHOPIFY_API_SECRET:
        try:
            claims = _verify_session_token(auth[7:])
            return True, claims.get("dest")
        except Exception as e:
            logger.warning(f"session token rejected: {e}")
            # fall through to password check

    if DASHBOARD_PASSWORD:
        pw = (body or {}).get("password") or request.headers.get("x-dashboard-password", "")
        # Compare as bytes — secrets.compare_digest raises on non-ASCII strings.
        if pw and secrets.compare_digest(str(pw).encode("utf-8"), DASHBOARD_PASSWORD.encode("utf-8")):
            return True, "password"

    return False, None


# ---------------------------------------------------------------------------
# Page rendering
# ---------------------------------------------------------------------------

def _render_page() -> str:
    global _page_cache
    if _page_cache is None:
        with open(_PAGE_PATH, "r", encoding="utf-8") as fh:
            _page_cache = fh.read()
    if SHOPIFY_API_KEY:
        head = (
            f'<meta name="shopify-api-key" content="{SHOPIFY_API_KEY}" />\n'
            '    <script src="https://cdn.shopify.com/shopifycloud/app-bridge.js"></script>'
        )
        mode = "embedded"
    else:
        head = ""
        mode = "password"
    return _page_cache.replace("<!--APPBRIDGE-->", head).replace("__MODE__", mode)


def _frame_headers(request: Request) -> dict:
    """Headers for the chat page: allow the admin iframe (must NOT send
    X-Frame-Options) and block MIME sniffing / referrer leakage."""
    shop = request.query_params.get("shop")
    ancestors = (
        f"https://{shop} https://admin.shopify.com"
        if shop else "https://admin.shopify.com https://*.myshopify.com"
    )
    return {
        "Content-Security-Policy": f"frame-ancestors {ancestors};",
        "Cache-Control": "no-store",  # mode (embedded vs password) is env-dependent — never cache it
        **_API_HEADERS,
    }


def _json(data: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status, headers=_API_HEADERS)


# ---------------------------------------------------------------------------
# Route registration (mounted onto the existing FastMCP app)
# ---------------------------------------------------------------------------

def add_routes(mcp, registry: dict) -> None:
    chat_registry = {**registry, **_build_seo_tools(registry)}  # Shopify tools + live SEO tools
    tools = _build_tools(chat_registry)
    dispatch = _build_dispatch(chat_registry)

    mode = "embedded (App Bridge)" if SHOPIFY_API_KEY else "standalone (password)"
    logger.info(f"Copilot enabled — mode: {mode}; models: fast={MODEL_FAST}, deep={MODEL_DEEP}; tools: {len(tools)}")
    if not ANTHROPIC_API_KEY:
        logger.warning("Copilot: ANTHROPIC_API_KEY not set — chat will return an error until it is.")
    if not SHOPIFY_API_KEY and not DASHBOARD_PASSWORD:
        logger.warning("Copilot: no SHOPIFY_API_SECRET and no DASHBOARD_PASSWORD — /api/chat is locked.")
    if SHOPIFY_API_SECRET and DASHBOARD_PASSWORD:
        logger.warning("Copilot: DASHBOARD_PASSWORD is set alongside Shopify auth — consider removing it "
                       "so access requires signing into Shopify admin.")

    @mcp.custom_route("/", methods=["GET"])
    async def index(request: Request):
        # When embedded, only serve the page when it's loaded from Shopify
        # admin (which always appends shop/host/embedded). A direct browser
        # visit has none of those — return nothing so the app is invisible
        # outside the admin. (Real auth is still enforced on /api/chat.)
        if SHOPIFY_API_KEY:
            qp = request.query_params
            if not (qp.get("shop") or qp.get("host") or qp.get("embedded") or qp.get("id_token")):
                return PlainTextResponse("Not Found", status_code=404, headers=_API_HEADERS)
        return HTMLResponse(_render_page(), headers=_frame_headers(request))

    @mcp.custom_route("/healthz", methods=["GET"])
    async def healthz(request: Request):
        return PlainTextResponse("ok")

    @mcp.custom_route("/api/chat", methods=["POST"])
    async def chat(request: Request):
        try:
            body = await request.json()
        except Exception:
            return _json({"error": "Invalid JSON body"}, 400)

        ok, _who = _authorize(request, body)
        if not ok:
            return _json({"error": "Unauthorized"}, 401)

        history = body.get("messages")
        if not history and body.get("message"):
            history = [{"role": "user", "content": body["message"]}]
        if not history:
            return _json({"error": "Provide 'messages' or 'message'"}, 400)

        model = _pick_model(history, bool(body.get("deep")))
        extra = _profile_to_system(_load_profile())
        if _is_seo(history):
            extra += "\n\n" + SEO_KNOWLEDGE
        try:
            result = await run_chat(history, dispatch, tools, model, extra)
        except RuntimeError as e:
            return _json({"error": str(e)}, 500)
        except anthropic.APIError:
            logger.exception("Anthropic API error")
            return _json({"error": "The AI service returned an error. Please try again."}, 502)
        return _json(result)

    @mcp.custom_route("/api/overview", methods=["POST"])
    async def overview(request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        ok, _who = _authorize(request, body)
        if not ok:
            return _json({"error": "Unauthorized"}, 401)
        profile = _load_profile()
        extra = _profile_to_system(profile)
        track = (profile.get("prefs") or {}).get("track_inventory", True)
        try:
            result = await run_overview(registry, extra, bool(track))
        except RuntimeError as e:
            return _json({"error": str(e)}, 500)
        except anthropic.APIError:
            logger.exception("Anthropic API error (overview)")
            return _json({"error": "The AI service returned an error. Please try again."}, 502)
        except Exception:
            logger.exception("Overview failed")
            return _json({"error": "Couldn't build the overview. Check the server logs."}, 500)
        return _json(result)

    @mcp.custom_route("/api/profile", methods=["POST"])
    async def profile_route(request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        ok, _who = _authorize(request, body)
        if not ok:
            return _json({"error": "Unauthorized"}, 401)
        # Save when a profile object is supplied; otherwise just load.
        if isinstance(body.get("profile"), dict):
            try:
                saved = _save_profile(body["profile"])
                return _json({"profile": saved})
            except Exception:
                logger.exception("Profile save failed")
                return _json({"error": "Couldn't save the profile (is a writable volume mounted at /data?)."}, 500)
        return _json({"profile": _load_profile()})

    @mcp.custom_route("/api/seo", methods=["POST"])
    async def seo_route(request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        ok, _who = _authorize(request, body)
        if not ok:
            return _json({"error": "Unauthorized"}, 401)
        try:
            result = await run_seo_audit(registry)
        except RuntimeError as e:
            return _json({"error": str(e)}, 500)
        except anthropic.APIError:
            logger.exception("Anthropic API error (seo)")
            return _json({"error": "The AI service returned an error. Please try again."}, 502)
        except Exception:
            logger.exception("SEO audit failed")
            return _json({"error": "Couldn't run the SEO audit. Check the server logs."}, 500)
        return _json(result)
