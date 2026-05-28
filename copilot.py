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
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import anthropic
import jwt
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


async def run_chat(history: list[dict], dispatch: Callable, data_tools: list[dict], model: str) -> dict:
    """Run a multi-step tool-use conversation. The final answer is delivered via
    the present_response tool and returned as a structured dict."""
    client = _anthropic()
    messages = list(history)
    tools_used: list[str] = []
    all_tools = data_tools + [PRESENT_RESPONSE_TOOL]

    for _ in range(MAX_TOOL_ROUNDS):
        resp = await client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
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


async def _compute_metrics(registry: dict) -> tuple[list[dict], dict]:
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
        "catalog": {"total_products": total_products, "low_stock_count": len(low),
                    "low_stock_examples": low[:8]},
        "top_products_7d": [{"title": t, "units": q} for t, q in units.most_common(5)],
        "note": "Order figures are based on up to 250 orders per 7-day window.",
    }
    return [m for m in metrics if m.get("value") is not None], context


async def run_overview(registry: dict) -> dict:
    metrics, context = await _compute_metrics(registry)
    client = _anthropic()
    msg = ("Current store KPIs (computed live):\n" + json.dumps(context, indent=2, default=str)
           + "\n\nGive the executive overview now by calling present_response.")
    resp = await client.messages.create(
        model=MODEL_FAST, max_tokens=MAX_TOKENS, system=OVERVIEW_SYSTEM,
        tools=[PRESENT_RESPONSE_TOOL], tool_choice={"type": "tool", "name": PRESENT_RESPONSE_TOOL["name"]},
        messages=[{"role": "user", "content": msg}],
    )
    present = next((b.input for b in resp.content
                    if b.type == "tool_use" and b.name == PRESENT_RESPONSE_TOOL["name"]), None)
    structured = _coerce_structured(present or {"summary": "Here's your store overview."})
    structured.pop("metrics", None)  # UI shows the computed metrics, not Claude's echo
    return {"metrics": metrics, "structured": structured}


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
    tools = _build_tools(registry)
    dispatch = _build_dispatch(registry)

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
        try:
            result = await run_chat(history, dispatch, tools, model)
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
        try:
            result = await run_overview(registry)
        except RuntimeError as e:
            return _json({"error": str(e)}, 500)
        except anthropic.APIError:
            logger.exception("Anthropic API error (overview)")
            return _json({"error": "The AI service returned an error. Please try again."}, 502)
        except Exception:
            logger.exception("Overview failed")
            return _json({"error": "Couldn't build the overview. Check the server logs."}, 500)
        return _json(result)
