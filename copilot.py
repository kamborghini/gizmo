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
import logging
import secrets
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
ANTHROPIC_MODEL    = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
SHOPIFY_API_KEY    = os.environ.get("SHOPIFY_API_KEY", "")      # app client ID
SHOPIFY_API_SECRET = os.environ.get("SHOPIFY_API_SECRET", "")   # app client secret
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")

MAX_TOOL_ROUNDS    = int(os.environ.get("COPILOT_MAX_TOOL_ROUNDS", "12"))
MAX_TOKENS         = int(os.environ.get("COPILOT_MAX_TOKENS", "4096"))
TOOL_RESULT_CAP    = int(os.environ.get("COPILOT_TOOL_RESULT_CAP", "50000"))

_PAGE_PATH = os.path.join(os.path.dirname(__file__), "static", "index.html")
_page_cache: Optional[str] = None

SYSTEM_PROMPT = """You are a helpful AI assistant embedded inside the admin of a Shopify store. \
You act as the merchant's store copilot.

Your job: answer questions about the store and proactively suggest concrete, prioritized \
improvements — for products, merchandising, pricing, inventory, collections, customers, and orders.

Rules:
- Always ground answers in real data. Use the tools to look things up before making claims or \
suggestions. Never invent numbers, product names, or IDs.
- You have READ-ONLY access. You cannot create, update, or delete anything. If asked to make a \
change, explain exactly what you would change and where the merchant can do it, but be clear you \
can't perform writes yourself.
- When listing suggestions, reference actual products/orders/figures from the store and explain \
the expected impact. Order them by impact.
- Be concise and skimmable: short paragraphs and bullet points.
- If a tool errors, briefly explain it (e.g. a missing API scope) rather than guessing data.
- Respect the store's currency and timezone; call shopify_get_shop if unsure."""


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


async def run_chat(history: list[dict], dispatch: Callable, tools: list[dict]) -> dict:
    """Run a multi-step tool-use conversation and return the final assistant text."""
    client = _anthropic()
    messages = list(history)
    tools_used: list[str] = []

    for _ in range(MAX_TOOL_ROUNDS):
        resp = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )

        # Reconstruct the assistant turn from minimal, API-safe blocks.
        assistant_blocks: list[dict] = []
        tool_uses: list[Any] = []
        for block in resp.content:
            if block.type == "text":
                assistant_blocks.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_blocks.append({
                    "type": "tool_use", "id": block.id,
                    "name": block.name, "input": block.input,
                })
                tool_uses.append(block)
        messages.append({"role": "assistant", "content": assistant_blocks})

        if resp.stop_reason != "tool_use":
            text = "".join(b["text"] for b in assistant_blocks if b["type"] == "text")
            return {"reply": text.strip(), "tools_used": tools_used}

        tool_results = []
        for tu in tool_uses:
            tools_used.append(tu.name)
            logger.info(f"copilot tool call: {tu.name} {tu.input}")
            result = await dispatch(tu.name, tu.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": result,
            })
        messages.append({"role": "user", "content": tool_results})

    return {
        "reply": "I made several lookups but didn't reach a final answer. "
                 "Please narrow the question and try again.",
        "tools_used": tools_used,
    }


# ---------------------------------------------------------------------------
# Auth: Shopify session token OR dashboard password
# ---------------------------------------------------------------------------

def _verify_session_token(token: str) -> dict:
    if not SHOPIFY_API_SECRET:
        raise RuntimeError("SHOPIFY_API_SECRET not configured")
    return jwt.decode(
        token,
        SHOPIFY_API_SECRET,
        algorithms=["HS256"],
        audience=SHOPIFY_API_KEY or None,
        leeway=5,
        options={"require": ["exp", "nbf"], "verify_aud": bool(SHOPIFY_API_KEY)},
    )


def _authorize(request: Request) -> tuple[bool, Optional[str]]:
    """Return (ok, who). Accepts a valid Shopify session token or the dashboard password."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer ") and SHOPIFY_API_SECRET:
        try:
            claims = _verify_session_token(auth[7:])
            return True, claims.get("dest")
        except Exception as e:
            logger.warning(f"session token rejected: {e}")
            # fall through to password check

    if DASHBOARD_PASSWORD:
        pw = request.headers.get("x-dashboard-password", "")
        if pw and secrets.compare_digest(pw, DASHBOARD_PASSWORD):
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
    """CSP so the admin can iframe this page. Must NOT send X-Frame-Options."""
    shop = request.query_params.get("shop")
    ancestors = (
        f"https://{shop} https://admin.shopify.com"
        if shop else "https://admin.shopify.com https://*.myshopify.com"
    )
    return {"Content-Security-Policy": f"frame-ancestors {ancestors};"}


# ---------------------------------------------------------------------------
# Route registration (mounted onto the existing FastMCP app)
# ---------------------------------------------------------------------------

def add_routes(mcp, registry: dict) -> None:
    tools = _build_tools(registry)
    dispatch = _build_dispatch(registry)

    mode = "embedded (App Bridge)" if SHOPIFY_API_KEY else "standalone (password)"
    logger.info(f"Copilot enabled — mode: {mode}; model: {ANTHROPIC_MODEL}; tools: {len(tools)}")
    if not ANTHROPIC_API_KEY:
        logger.warning("Copilot: ANTHROPIC_API_KEY not set — chat will return an error until it is.")
    if not SHOPIFY_API_KEY and not DASHBOARD_PASSWORD:
        logger.warning("Copilot: no SHOPIFY_API_SECRET and no DASHBOARD_PASSWORD — /api/chat is locked.")

    @mcp.custom_route("/", methods=["GET"])
    async def index(request: Request):
        return HTMLResponse(_render_page(), headers=_frame_headers(request))

    @mcp.custom_route("/healthz", methods=["GET"])
    async def healthz(request: Request):
        return PlainTextResponse("ok")

    @mcp.custom_route("/api/chat", methods=["POST"])
    async def chat(request: Request):
        ok, _who = _authorize(request)
        if not ok:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

        history = body.get("messages")
        if not history and body.get("message"):
            history = [{"role": "user", "content": body["message"]}]
        if not history:
            return JSONResponse({"error": "Provide 'messages' or 'message'"}, status_code=400)

        try:
            result = await run_chat(history, dispatch, tools)
        except RuntimeError as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        except anthropic.APIError as e:
            logger.error(f"Anthropic API error: {e}")
            return JSONResponse({"error": f"Claude API error: {e}"}, status_code=502)
        return JSONResponse(result)
