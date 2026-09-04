#!/usr/bin/env python3
"""
Shopify MCP Server — Full Admin API access via FastMCP.
Provides tools for managing products, orders, customers, collections,
inventory, and fulfillments through the Shopify Admin REST API.

Token Management:
  - Uses client_credentials grant to auto-generate and refresh tokens
  - Set SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET (recommended for OAuth apps)
  - Falls back to static SHOPIFY_ACCESS_TOKEN if client credentials not set
"""
import gzip
import json
import os
import logging
import time
import asyncio
import secrets
from typing import Optional, List, Dict, Any
from enum import Enum
import httpx
from pydantic import BaseModel, Field, ConfigDict, field_validator
from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse
from starlette.datastructures import MutableHeaders

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SHOPIFY_STORE        = os.environ.get("SHOPIFY_STORE", "")           # e.g. "my-store"
SHOPIFY_TOKEN        = os.environ.get("SHOPIFY_ACCESS_TOKEN", "")    # Static token (shpat_...)
SHOPIFY_CLIENT_ID    = os.environ.get("SHOPIFY_CLIENT_ID", "")
SHOPIFY_CLIENT_SECRET = os.environ.get("SHOPIFY_CLIENT_SECRET", "")
API_VERSION          = os.environ.get("SHOPIFY_API_VERSION", "2026-07")

# Refresh buffer: refresh token 30 minutes before expiry (only used with OAuth)
TOKEN_REFRESH_BUFFER = int(os.environ.get("TOKEN_REFRESH_BUFFER", "1800"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("shopify_mcp")

# Off-host log shipping, when LOG_DRAIN_URL is set. Returns False and changes
# nothing when it is not, so a deployment without one behaves as before.
import logdrain
if logdrain.install():
    logger.info("log drain installed")

PORT          = int(os.environ.get("PORT", "8000"))
MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "streamable-http")

mcp = FastMCP("shopify_mcp", host="0.0.0.0", port=PORT, json_response=True)


# ---------------------------------------------------------------------------
# MCP endpoint authentication (fail-closed)
# ---------------------------------------------------------------------------
# The /mcp endpoint exposes every Shopify tool, including destructive writes
# (delete product, cancel order, set inventory) and full customer/order PII.
# It must never be open to the internet. Without MCP_BEARER_TOKEN set, /mcp is
# LOCKED. When set, callers (e.g. the Claude.ai integration) must send
# `Authorization: Bearer <MCP_BEARER_TOKEN>`.
MCP_BEARER_TOKEN = os.environ.get("MCP_BEARER_TOKEN", "")


class MCPAuthMiddleware:
    """Pure-ASGI auth gate for /mcp. Kept at the ASGI layer (not
    BaseHTTPMiddleware) so it never buffers the transport's streaming
    responses — it only short-circuits unauthorized requests."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            path = scope.get("path", "")
            if path == "/mcp" or path.startswith("/mcp/"):
                headers = dict(scope.get("headers") or [])
                provided = headers.get(b"authorization", b"").decode("latin-1")
                if not MCP_BEARER_TOKEN:
                    logger.warning("Blocked /mcp request — MCP_BEARER_TOKEN is not set (endpoint locked).")
                    await JSONResponse(
                        {"error": "MCP endpoint is locked. Set MCP_BEARER_TOKEN on the server."},
                        status_code=503,
                    )(scope, receive, send)
                    return
                if not (provided and secrets.compare_digest(provided, f"Bearer {MCP_BEARER_TOKEN}")):
                    await JSONResponse({"error": "Unauthorized"}, status_code=401)(scope, receive, send)
                    return
        await self.app(scope, receive, send)


# One pooled HTTP client for every Shopify call, built lazily so it is created
# inside the running loop.
#
# A fresh httpx.AsyncClient per call means a fresh TCP connection and a fresh
# TLS handshake per call: measured at a median 89 ms against shopify.com versus
# 29 ms on a warm pooled client. That is paid 8 times on a cold production
# queue, 30 times on the Liability tab, and once per order on a bulk print -
# about 900 ms on a 50-order print alone.
#
# keepalive_expiry is deliberately short. The whole benefit is in BURSTS, where
# the pages of one sweep follow each other in milliseconds; letting a
# connection sit idle for minutes only invites the far end to reap it between
# our requests, which is the one failure mode pooling adds that a fresh
# connection never had.
_pool: Optional[httpx.AsyncClient] = None


def _http() -> httpx.AsyncClient:
    global _pool
    if _pool is None or _pool.is_closed:
        _pool = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=8,
                                keepalive_expiry=30.0))
    return _pool


GZIP_MIN_BYTES = int(os.environ.get("GZIP_MIN_BYTES", "1024"))
GZIP_LEVEL = int(os.environ.get("GZIP_LEVEL", "6"))
# What is worth compressing. Everything here is text; images, PDFs and the
# stored label files are already compressed and would only cost CPU.
_COMPRESSIBLE = ("application/json", "application/javascript", "application/xml",
                 "image/svg+xml", "text/")


class CompressionMiddleware:
    """Gzip complete responses. Never streaming ones.

    Kept at the ASGI layer beside MCPAuthMiddleware, and for the same reason:
    Starlette's own GZipMiddleware buffers a StreamingResponse to compress it,
    which would silently break the chat SSE route and the MCP transport, where
    the whole point is that bytes leave as they are produced.

    The discriminator is Content-Length. A response that declares one has
    already been built in full, so buffering it costs nothing - it is already
    in memory. A streaming response never declares one, so it cannot be caught
    here by construction rather than by a list of paths somebody has to
    remember to update.

    Measured on this app's own routes: the Complete production queue goes from
    1,117 KB to 30 KB, the CRM board from 1,162 KB to 309 KB, and app.js from
    819 KB to 196 KB, for single-digit milliseconds of CPU."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("method") == "HEAD":
            await self.app(scope, receive, send)
            return
        raw = scope.get("headers") or []
        accepts = any(k == b"accept-encoding" and b"gzip" in v.lower() for k, v in raw)

        state: dict = {"start": None}
        chunks: list = []

        async def send_wrapper(message):
            kind = message["type"]
            if kind == "http.response.start":
                hdrs = MutableHeaders(raw=message["headers"])
                ctype = hdrs.get("content-type", "").lower()
                worth = any(ctype.startswith(c) for c in _COMPRESSIBLE)
                if not worth:
                    await send(message)
                    return
                # Say the body varies even when this particular client did not
                # ask for gzip, or a cache between us could hand a compressed
                # body to one that cannot read it.
                hdrs.append("vary", "Accept-Encoding")
                length = hdrs.get("content-length") or ""
                if (accepts and length.isdigit() and int(length) >= GZIP_MIN_BYTES
                        and not hdrs.get("content-encoding")
                        and message.get("status") not in (204, 304)):
                    state["start"] = message      # hold the head: the length changes
                    return
                await send(message)
                return
            if kind == "http.response.body" and state["start"] is not None:
                chunks.append(message.get("body", b""))
                if message.get("more_body"):
                    return
                body = gzip.compress(b"".join(chunks), GZIP_LEVEL)
                head = state["start"]
                hdrs = MutableHeaders(raw=head["headers"])
                hdrs["content-encoding"] = "gzip"
                hdrs["content-length"] = str(len(body))
                state["start"] = None
                await send(head)
                await send({"type": "http.response.body", "body": body, "more_body": False})
                return
            await send(message)

        await self.app(scope, receive, send_wrapper)


def build_app():
    """The app exactly as it is served.

    Production and the test suite both build it HERE. Assembling the stack in
    two places is how a suite comes to pass over middleware the merchant
    actually runs, or over middleware they do not: the tests were built on a
    bare mcp.streamable_http_app() while production wrapped it in two layers,
    so nothing ever exercised those layers against a real route."""
    # Before the first request: anything long-lived already on the volume gets
    # encrypted now, rather than whenever it next happens to be rewritten.
    try:
        copilot.reseal_secrets_at_rest()
    except Exception:
        logger.exception("token vault: re-seal pass failed; continuing")
    # Before the reaper next ticks: rescue files that were marked as macOS junk
    # by a pattern that also matched ordinary names beginning with an
    # underscore. They are invisible and on course to be deleted.
    try:
        copilot.rescue_misfiled_junk()
    except Exception:
        logger.exception("files: junk rescue failed; continuing")
    app = mcp.streamable_http_app()
    app.add_middleware(MCPAuthMiddleware)
    # Added last, so it wraps outermost and sees every response, including the
    # static assets and the print pages.
    app.add_middleware(CompressionMiddleware)
    return app


# ---------------------------------------------------------------------------
# Token Manager — handles automatic token lifecycle
# ---------------------------------------------------------------------------

class TokenManager:
    """
    Manages Shopify Admin API access tokens.

    Two modes:
      1. Static token  — set SHOPIFY_ACCESS_TOKEN (recommended for Custom Apps)
      2. OAuth / client_credentials — set SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET
         Enables auto-refresh before expiry and retry on 401.
    """

    def __init__(
        self,
        store: str,
        client_id: str,
        client_secret: str,
        static_token: str = "",
        refresh_buffer: int = 1800,
    ):
        self._store         = store
        self._client_id     = client_id
        self._client_secret = client_secret
        self._static_token  = static_token
        self._refresh_buffer = refresh_buffer

        self._access_token: str   = ""
        self._expires_at: float   = 0.0
        self._lock = asyncio.Lock()

        # Prefer an explicit static token. client_credentials is only used when
        # no static token is set — otherwise providing CLIENT_ID/SECRET for App
        # Bridge embedding would silently switch Admin API auth to a (likely
        # unscoped) client_credentials grant and break reads.
        self._use_client_credentials = bool(client_id and client_secret) and not static_token

        if self._use_client_credentials:
            logger.info("Token mode: client_credentials (auto-refresh enabled)")
        elif static_token:
            logger.info("Token mode: static SHOPIFY_ACCESS_TOKEN (no auto-refresh)")
            self._access_token = static_token
            self._expires_at   = float("inf")
        else:
            logger.warning(
                "No credentials configured. Set SHOPIFY_ACCESS_TOKEN or "
                "SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET."
            )

    @property
    def is_expired(self) -> bool:
        if not self._access_token:
            return True
        return time.time() >= (self._expires_at - self._refresh_buffer)

    async def get_token(self) -> str:
        if not self.is_expired:
            return self._access_token

        async with self._lock:
            if not self.is_expired:
                return self._access_token

            if self._use_client_credentials:
                await self._refresh_token()
            elif not self._access_token:
                raise RuntimeError(
                    "No valid token available. "
                    "Set SHOPIFY_ACCESS_TOKEN in your environment variables."
                )

        return self._access_token

    async def force_refresh(self) -> str:
        if not self._use_client_credentials:
            raise RuntimeError(
                "Cannot refresh — using a static token. "
                "Set SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET to enable auto-refresh."
            )
        async with self._lock:
            await self._refresh_token()
        return self._access_token

    async def _refresh_token(self) -> None:
        url = f"https://{self._store}.myshopify.com/admin/oauth/access_token"
        logger.info("Refreshing Shopify access token via client_credentials grant...")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                data={
                    "grant_type":    "client_credentials",
                    "client_id":     self._client_id,
                    "client_secret": self._client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15.0,
            )

            if resp.status_code != 200:
                logger.error(f"Token refresh failed ({resp.status_code}): {resp.text[:500]}")
                raise RuntimeError(
                    f"Token refresh failed ({resp.status_code}). "
                    "Check SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET."
                )

            data               = resp.json()
            self._access_token = data["access_token"]
            expires_in         = data.get("expires_in", 86399)
            self._expires_at   = time.time() + expires_in

            scope         = data.get("scope", "")
            scope_preview = scope[:80] + "..." if len(scope) > 80 else scope
            logger.info(
                f"Token refreshed. Expires in {expires_in}s "
                f"({expires_in // 3600}h {(expires_in % 3600) // 60}m). "
                f"Scopes: {scope_preview}"
            )


# Global token manager
token_manager = TokenManager(
    store=SHOPIFY_STORE,
    client_id=SHOPIFY_CLIENT_ID,
    client_secret=SHOPIFY_CLIENT_SECRET,
    static_token=SHOPIFY_TOKEN,
    refresh_buffer=TOKEN_REFRESH_BUFFER,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _base_url() -> str:
    return f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/{API_VERSION}"


async def _headers() -> dict:
    token = await token_manager.get_token()
    return {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
    }


# The app's own routes fire bursts of concurrent Shopify reads (bulk print,
# stock usage, the liability sweep). Shopify's REST bucket leaks ~2/s, so an
# unbounded burst guarantees 429s. Cap in-flight requests and retry throttled
# or transient failures with backoff, so a busy moment slows down instead of
# silently dropping data.
_shopify_gate = asyncio.Semaphore(int(os.environ.get("SHOPIFY_MAX_CONCURRENCY", "4")))
_RETRY_STATUS = {429, 500, 502, 503, 504}


async def _request(
    method: str,
    path: str,
    params: Optional[dict] = None,
    body:   Optional[dict] = None,
    _retried: bool = False,
    idempotent: Optional[bool] = None,
) -> dict:
    """Central HTTP helper — every API call flows through here.
    Retries once on 401 (OAuth refresh), and up to 3 times with backoff on
    429/5xx/timeout so throttling and transient errors don't surface as data loss.

    `idempotent` decides whether an AMBIGUOUS failure (a timeout, or a 5xx that
    may have been raised after the write landed) is retried. It defaults to
    "everything except POST", because re-posting a create is how one shipment
    becomes two, and how a customer gets two tracking emails. A 429 is retried
    for every method: Shopify rejected it before doing anything.
    """
    if idempotent is None:
        idempotent = method.upper() != "POST"
    if not SHOPIFY_STORE:
        raise RuntimeError(
            "Missing SHOPIFY_STORE environment variable. "
            "Set it before starting the server."
        )

    url     = f"{_base_url()}/{path}"

    async with _shopify_gate:
        for attempt in range(4):
            headers = await _headers()
            try:
                resp = await _http().request(
                    method, url,
                    headers=headers,
                    params=params,
                    json=body,
                    timeout=30.0,
                )
            except httpx.ConnectError as e:
                # The connection was never established, so nothing was sent and
                # nothing can have been acted on. This is the ONE transport
                # failure a POST may be replayed after, and pooling is what
                # makes it worth naming: a reaped idle connection surfaces
                # here, and refusing to retry would report a write that never
                # left the machine as a failure.
                if attempt >= 3:
                    raise
                await asyncio.sleep(min(2 ** attempt, 8))
                logger.warning("Shopify %s %s: could not connect - retry %d", method, path, attempt + 1)
                continue
            except (httpx.TimeoutException, httpx.TransportError) as e:
                # Everything else is ambiguous: the request may have arrived and
                # been acted on. A POST is not replayed after an ambiguous
                # failure, and that rule does not bend for a faster client.
                if attempt >= 3 or not idempotent:
                    raise
                await asyncio.sleep(min(2 ** attempt, 8))
                logger.warning("Shopify %s %s: %s — retry %d", method, path, type(e).__name__, attempt + 1)
                continue

            if resp.status_code == 401 and not _retried and token_manager._use_client_credentials:
                logger.warning("Got 401, refreshing the token and retrying")
                _retried = True
                await token_manager.force_refresh()
                continue

            if (resp.status_code in _RETRY_STATUS and attempt < 3
                    and (idempotent or resp.status_code == 429)):
                # Respect Retry-After on 429; otherwise exponential backoff.
                try:
                    # CLAMPED. This sleep happens while holding a permit on the
                    # process-wide Shopify gate, so an edge 503 carrying a
                    # legal "Retry-After: 3600" would park a quarter of the
                    # app's Shopify capacity for an hour, and four of them
                    # would stall every queue, dispatch and tag write behind it.
                    wait = min(float(resp.headers.get("Retry-After", "")), 10.0)
                except ValueError:
                    wait = min(2 ** attempt, 8)
                logger.warning("Shopify %s %s: %d — backing off %.1fs (retry %d)",
                               method, path, resp.status_code, wait, attempt + 1)
                await asyncio.sleep(max(0.5, wait))
                continue

            resp.raise_for_status()
            if resp.status_code == 204:
                return {}
            return resp.json()
    # Exhausted retries on a retryable status: surface it, don't return empty.
    resp.raise_for_status()
    return {}


def _error(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text[:500]
        messages = {
            401: "Authentication failed — check your SHOPIFY_ACCESS_TOKEN (should start with shpat_).",
            403: "Permission denied — your token may be missing required API scopes.",
            404: "Resource not found — double-check the ID.",
            422: f"Validation error: {json.dumps(detail)}",
            429: "Rate-limited — wait a moment and retry.",
        }
        return messages.get(status, f"Shopify API error {status}: {json.dumps(detail)}")
    if isinstance(e, httpx.TimeoutException):
        return "Request timed out — try again."
    if isinstance(e, RuntimeError):
        return str(e)
    return f"Unexpected error: {type(e).__name__}: {e}"


def _fmt(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════════════════
# PRODUCTS
# ═══════════════════════════════════════════════════════════════════════════

class ListProductsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    limit:          Optional[int]  = Field(default=50, ge=1, le=250, description="Max products to return (1-250)")
    status:         Optional[str]  = Field(default=None, description="Filter by status: active, archived, draft")
    product_type:   Optional[str]  = Field(default=None, description="Filter by product type")
    vendor:         Optional[str]  = Field(default=None, description="Filter by vendor name")
    collection_id:  Optional[int]  = Field(default=None, description="Filter by collection ID")
    since_id:       Optional[int]  = Field(default=None, description="Pagination: return products after this ID")
    fields:         Optional[str]  = Field(default=None, description="Comma-separated fields to include")


@mcp.tool(
    name="shopify_list_products",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_list_products(params: ListProductsInput) -> str:
    """List products from the Shopify store with optional filters."""
    try:
        p: Dict[str, Any] = {"limit": params.limit}
        for field in ["status", "product_type", "vendor", "collection_id", "since_id", "fields"]:
            val = getattr(params, field)
            if val is not None:
                p[field] = val
        data     = await _request("GET", "products.json", params=p)
        products = data.get("products", [])
        return _fmt({"count": len(products), "products": products})
    except Exception as e:
        return _error(e)


class GetProductInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: int = Field(..., description="The Shopify product ID")


@mcp.tool(
    name="shopify_get_product",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_get_product(params: GetProductInput) -> str:
    """Retrieve a single product by ID, including all variants and images."""
    try:
        data = await _request("GET", f"products/{params.product_id}.json")
        return _fmt(data.get("product", data))
    except Exception as e:
        return _error(e)


class CreateProductInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    title:        str                        = Field(..., min_length=1, description="Product title")
    body_html:    Optional[str]              = Field(default=None, description="HTML description")
    vendor:       Optional[str]              = Field(default=None)
    product_type: Optional[str]              = Field(default=None)
    tags:         Optional[str]              = Field(default=None, description="Comma-separated tags")
    status:       Optional[str]              = Field(default="draft", description="active, archived, or draft")
    variants:     Optional[List[Dict[str, Any]]] = Field(default=None, description="Variant objects with price, sku, etc.")
    options:      Optional[List[Dict[str, Any]]] = Field(default=None, description="Product options (Size, Color, etc.)")
    images:       Optional[List[Dict[str, Any]]] = Field(default=None, description="Image objects with src URL")


@mcp.tool(
    name="shopify_create_product",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def shopify_create_product(params: CreateProductInput) -> str:
    """Create a new product in the Shopify store."""
    try:
        product: Dict[str, Any] = {"title": params.title}
        for field in ["body_html", "vendor", "product_type", "tags", "status", "variants", "options", "images"]:
            val = getattr(params, field)
            if val is not None:
                product[field] = val
        data = await _request("POST", "products.json", body={"product": product})
        return _fmt(data.get("product", data))
    except Exception as e:
        return _error(e)


class UpdateProductInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    product_id:   int            = Field(..., description="Product ID to update")
    title:        Optional[str]  = Field(default=None)
    body_html:    Optional[str]  = Field(default=None)
    vendor:       Optional[str]  = Field(default=None)
    product_type: Optional[str]  = Field(default=None)
    tags:         Optional[str]  = Field(default=None)
    status:       Optional[str]  = Field(default=None, description="active, archived, or draft")
    variants:     Optional[List[Dict[str, Any]]] = Field(default=None)


@mcp.tool(
    name="shopify_update_product",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_update_product(params: UpdateProductInput) -> str:
    """Update an existing product. Only provided fields are changed."""
    try:
        product: Dict[str, Any] = {}
        for field in ["title", "body_html", "vendor", "product_type", "tags", "status", "variants"]:
            val = getattr(params, field)
            if val is not None:
                product[field] = val
        data = await _request("PUT", f"products/{params.product_id}.json", body={"product": product})
        return _fmt(data.get("product", data))
    except Exception as e:
        return _error(e)


class DeleteProductInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: int = Field(..., description="Product ID to delete")


@mcp.tool(
    name="shopify_delete_product",
    annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_delete_product(params: DeleteProductInput) -> str:
    """Permanently delete a product. This cannot be undone."""
    try:
        await _request("DELETE", f"products/{params.product_id}.json")
        return f"Product {params.product_id} deleted."
    except Exception as e:
        return _error(e)


class ProductCountInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status:       Optional[str] = Field(default=None, description="active, archived, or draft")
    vendor:       Optional[str] = Field(default=None)
    product_type: Optional[str] = Field(default=None)


@mcp.tool(
    name="shopify_count_products",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_count_products(params: ProductCountInput) -> str:
    """Get the total count of products, optionally filtered."""
    try:
        p: Dict[str, Any] = {}
        for field in ["status", "vendor", "product_type"]:
            val = getattr(params, field)
            if val is not None:
                p[field] = val
        data = await _request("GET", "products/count.json", params=p)
        return _fmt(data)
    except Exception as e:
        return _error(e)


# ═══════════════════════════════════════════════════════════════════════════
# ORDERS
# ═══════════════════════════════════════════════════════════════════════════

class ListOrdersInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    limit:               Optional[int] = Field(default=50, ge=1, le=250)
    status:              Optional[str] = Field(default="any", description="open, closed, cancelled, any")
    financial_status:    Optional[str] = Field(default=None, description="authorized, pending, paid, refunded, voided, any")
    fulfillment_status:  Optional[str] = Field(default=None, description="shipped, partial, unshipped, unfulfilled, any")
    since_id:            Optional[int] = Field(default=None)
    created_at_min:      Optional[str] = Field(default=None, description="ISO 8601 date, e.g. 2024-01-01T00:00:00Z")
    created_at_max:      Optional[str] = Field(default=None)
    fields:              Optional[str] = Field(default=None)


@mcp.tool(
    name="shopify_list_orders",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_list_orders(params: ListOrdersInput) -> str:
    """List orders with optional filters for status, financial/fulfillment status, and date range."""
    try:
        p: Dict[str, Any] = {"limit": params.limit, "status": params.status}
        for field in ["financial_status", "fulfillment_status", "since_id", "created_at_min", "created_at_max", "fields"]:
            val = getattr(params, field)
            if val is not None:
                p[field] = val
        data   = await _request("GET", "orders.json", params=p)
        orders = data.get("orders", [])
        return _fmt({"count": len(orders), "orders": orders})
    except Exception as e:
        return _error(e)


class GetOrderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: int = Field(..., description="The Shopify order ID")


@mcp.tool(
    name="shopify_get_order",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_get_order(params: GetOrderInput) -> str:
    """Retrieve a single order by ID with full details."""
    try:
        data = await _request("GET", f"orders/{params.order_id}.json")
        return _fmt(data.get("order", data))
    except Exception as e:
        return _error(e)


class OrderCountInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status:             Optional[str] = Field(default="any")
    financial_status:   Optional[str] = Field(default=None)
    fulfillment_status: Optional[str] = Field(default=None)


@mcp.tool(
    name="shopify_count_orders",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_count_orders(params: OrderCountInput) -> str:
    """Get total order count, optionally filtered."""
    try:
        p: Dict[str, Any] = {"status": params.status}
        for field in ["financial_status", "fulfillment_status"]:
            val = getattr(params, field)
            if val is not None:
                p[field] = val
        data = await _request("GET", "orders/count.json", params=p)
        return _fmt(data)
    except Exception as e:
        return _error(e)


class CloseOrderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: int = Field(..., description="Order ID to close")


@mcp.tool(
    name="shopify_close_order",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_close_order(params: CloseOrderInput) -> str:
    """Close an order (marks it as completed)."""
    try:
        data = await _request("POST", f"orders/{params.order_id}/close.json")
        return _fmt(data.get("order", data))
    except Exception as e:
        return _error(e)


class CancelOrderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: int            = Field(..., description="Order ID to cancel")
    reason:   Optional[str]  = Field(default=None, description="customer, fraud, inventory, declined, other")
    email:    Optional[bool] = Field(default=True,  description="Send cancellation email to customer")
    restock:  Optional[bool] = Field(default=False, description="Restock line items")


@mcp.tool(
    name="shopify_cancel_order",
    annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
)
async def shopify_cancel_order(params: CancelOrderInput) -> str:
    """Cancel an order. Optionally restock items and notify the customer."""
    try:
        body: Dict[str, Any] = {}
        for field in ["reason", "email", "restock"]:
            val = getattr(params, field)
            if val is not None:
                body[field] = val
        data = await _request("POST", f"orders/{params.order_id}/cancel.json", body=body)
        return _fmt(data.get("order", data))
    except Exception as e:
        return _error(e)


# ═══════════════════════════════════════════════════════════════════════════
# CUSTOMERS
# ═══════════════════════════════════════════════════════════════════════════

class ListCustomersInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    limit:          Optional[int] = Field(default=50, ge=1, le=250)
    since_id:       Optional[int] = Field(default=None)
    created_at_min: Optional[str] = Field(default=None, description="ISO 8601 date")
    created_at_max: Optional[str] = Field(default=None)
    fields:         Optional[str] = Field(default=None)


@mcp.tool(
    name="shopify_list_customers",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_list_customers(params: ListCustomersInput) -> str:
    """List customers from the store."""
    try:
        p: Dict[str, Any] = {"limit": params.limit}
        for f in ["since_id", "created_at_min", "created_at_max", "fields"]:
            val = getattr(params, f)
            if val is not None:
                p[f] = val
        data      = await _request("GET", "customers.json", params=p)
        customers = data.get("customers", [])
        return _fmt({"count": len(customers), "customers": customers})
    except Exception as e:
        return _error(e)


class SearchCustomersInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    query: str           = Field(..., min_length=1, description="Search query (name, email, etc.)")
    limit: Optional[int] = Field(default=50, ge=1, le=250)


@mcp.tool(
    name="shopify_search_customers",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_search_customers(params: SearchCustomersInput) -> str:
    """Search customers by name, email, or other fields."""
    try:
        p         = {"query": params.query, "limit": params.limit}
        data      = await _request("GET", "customers/search.json", params=p)
        customers = data.get("customers", [])
        return _fmt({"count": len(customers), "customers": customers})
    except Exception as e:
        return _error(e)


class GetCustomerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: int = Field(..., description="Shopify customer ID")


@mcp.tool(
    name="shopify_get_customer",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_get_customer(params: GetCustomerInput) -> str:
    """Retrieve a single customer by ID."""
    try:
        data = await _request("GET", f"customers/{params.customer_id}.json")
        return _fmt(data.get("customer", data))
    except Exception as e:
        return _error(e)


class CreateCustomerInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    first_name:         Optional[str]  = Field(default=None)
    last_name:          Optional[str]  = Field(default=None)
    email:              Optional[str]  = Field(default=None)
    phone:              Optional[str]  = Field(default=None)
    tags:               Optional[str]  = Field(default=None)
    note:               Optional[str]  = Field(default=None)
    addresses:          Optional[List[Dict[str, Any]]] = Field(default=None)
    send_email_invite:  Optional[bool] = Field(default=False)


@mcp.tool(
    name="shopify_create_customer",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def shopify_create_customer(params: CreateCustomerInput) -> str:
    """Create a new customer."""
    try:
        customer: Dict[str, Any] = {}
        for field in ["first_name", "last_name", "email", "phone", "tags", "note", "addresses", "send_email_invite"]:
            val = getattr(params, field)
            if val is not None:
                customer[field] = val
        data = await _request("POST", "customers.json", body={"customer": customer})
        return _fmt(data.get("customer", data))
    except Exception as e:
        return _error(e)


class UpdateCustomerInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    customer_id: int           = Field(..., description="Customer ID to update")
    first_name:  Optional[str] = Field(default=None)
    last_name:   Optional[str] = Field(default=None)
    email:       Optional[str] = Field(default=None)
    phone:       Optional[str] = Field(default=None)
    tags:        Optional[str] = Field(default=None)
    note:        Optional[str] = Field(default=None)


@mcp.tool(
    name="shopify_update_customer",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_update_customer(params: UpdateCustomerInput) -> str:
    """Update an existing customer. Only provided fields are changed."""
    try:
        customer: Dict[str, Any] = {}
        for field in ["first_name", "last_name", "email", "phone", "tags", "note"]:
            val = getattr(params, field)
            if val is not None:
                customer[field] = val
        data = await _request("PUT", f"customers/{params.customer_id}.json", body={"customer": customer})
        return _fmt(data.get("customer", data))
    except Exception as e:
        return _error(e)


class CustomerOrdersInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: int           = Field(..., description="Customer ID")
    limit:       Optional[int] = Field(default=50, ge=1, le=250)
    status:      Optional[str] = Field(default="any")


@mcp.tool(
    name="shopify_get_customer_orders",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_get_customer_orders(params: CustomerOrdersInput) -> str:
    """Get all orders for a specific customer."""
    try:
        p      = {"limit": params.limit, "status": params.status}
        data   = await _request("GET", f"customers/{params.customer_id}/orders.json", params=p)
        orders = data.get("orders", [])
        return _fmt({"count": len(orders), "orders": orders})
    except Exception as e:
        return _error(e)


# ═══════════════════════════════════════════════════════════════════════════
# COLLECTIONS (Custom + Smart)
# ═══════════════════════════════════════════════════════════════════════════

class ListCollectionsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit:           Optional[int] = Field(default=50, ge=1, le=250)
    since_id:        Optional[int] = Field(default=None)
    collection_type: Optional[str] = Field(default="custom", description="'custom' or 'smart'")


@mcp.tool(
    name="shopify_list_collections",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_list_collections(params: ListCollectionsInput) -> str:
    """List custom or smart collections."""
    try:
        endpoint = "custom_collections.json" if params.collection_type == "custom" else "smart_collections.json"
        p: Dict[str, Any] = {"limit": params.limit}
        if params.since_id:
            p["since_id"] = params.since_id
        data = await _request("GET", endpoint, params=p)
        key  = "custom_collections" if params.collection_type == "custom" else "smart_collections"
        collections = data.get(key, [])
        return _fmt({"count": len(collections), "collections": collections})
    except Exception as e:
        return _error(e)


class GetCollectionProductsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    collection_id: int           = Field(..., description="Collection ID")
    limit:         Optional[int] = Field(default=50, ge=1, le=250)


@mcp.tool(
    name="shopify_get_collection_products",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_get_collection_products(params: GetCollectionProductsInput) -> str:
    """Get all products in a specific collection."""
    try:
        p        = {"limit": params.limit, "collection_id": params.collection_id}
        data     = await _request("GET", "products.json", params=p)
        products = data.get("products", [])
        return _fmt({"count": len(products), "products": products})
    except Exception as e:
        return _error(e)


# ═══════════════════════════════════════════════════════════════════════════
# INVENTORY
# ═══════════════════════════════════════════════════════════════════════════

class ListInventoryLocationsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


@mcp.tool(
    name="shopify_list_locations",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_list_locations(params: ListInventoryLocationsInput) -> str:
    """List all inventory locations for the store."""
    try:
        data      = await _request("GET", "locations.json")
        locations = data.get("locations", [])
        return _fmt({"count": len(locations), "locations": locations})
    except Exception as e:
        return _error(e)


class GetInventoryLevelsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    location_id:         Optional[int] = Field(default=None, description="Filter by location ID")
    inventory_item_ids:  Optional[str] = Field(default=None, description="Comma-separated inventory item IDs")


@mcp.tool(
    name="shopify_get_inventory_levels",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_get_inventory_levels(params: GetInventoryLevelsInput) -> str:
    """Get inventory levels for specific locations or inventory items."""
    try:
        p: Dict[str, Any] = {}
        if params.location_id:
            p["location_ids"] = params.location_id
        if params.inventory_item_ids:
            p["inventory_item_ids"] = params.inventory_item_ids
        data   = await _request("GET", "inventory_levels.json", params=p)
        levels = data.get("inventory_levels", [])
        return _fmt({"count": len(levels), "inventory_levels": levels})
    except Exception as e:
        return _error(e)


class GetVariantInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variant_id: int = Field(..., description="Product variant ID")


@mcp.tool(
    name="shopify_get_variant",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_get_variant(params: GetVariantInput) -> str:
    """Retrieve a single product variant (includes its inventory_item_id)."""
    try:
        data = await _request("GET", f"variants/{params.variant_id}.json")
        return _fmt(data.get("variant", data))
    except Exception as e:
        return _error(e)


class GetInventoryItemsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: str = Field(..., min_length=1, description="Comma-separated inventory item IDs (max 100)")


@mcp.tool(
    name="shopify_get_inventory_items",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_get_inventory_items(params: GetInventoryItemsInput) -> str:
    """Inventory items by id: unit cost, harmonized_system_code (customs HS) and
    country_code_of_origin live here, not on the product."""
    try:
        data = await _request("GET", "inventory_items.json", params={"ids": params.ids, "limit": 100})
        items = data.get("inventory_items", [])
        return _fmt({"count": len(items), "inventory_items": items})
    except Exception as e:
        return _error(e)


class SetInventoryLevelInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inventory_item_id: int = Field(..., description="Inventory item ID")
    location_id:       int = Field(..., description="Location ID")
    available:         int = Field(..., description="Available quantity to set")


@mcp.tool(
    name="shopify_set_inventory_level",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_set_inventory_level(params: SetInventoryLevelInput) -> str:
    """Set the available inventory for an item at a location."""
    try:
        body = {
            "inventory_item_id": params.inventory_item_id,
            "location_id":       params.location_id,
            "available":         params.available,
        }
        # An absolute set, not an increment: safe to repeat.
        data = await _request("POST", "inventory_levels/set.json", body=body, idempotent=True)
        return _fmt(data.get("inventory_level", data))
    except Exception as e:
        return _error(e)


# ═══════════════════════════════════════════════════════════════════════════
# FULFILLMENTS
# ═══════════════════════════════════════════════════════════════════════════

class ListFulfillmentsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: int           = Field(..., description="Order ID")
    limit:    Optional[int] = Field(default=50, ge=1, le=250)


@mcp.tool(
    name="shopify_list_fulfillments",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_list_fulfillments(params: ListFulfillmentsInput) -> str:
    """List fulfillments for a specific order."""
    try:
        p            = {"limit": params.limit}
        data         = await _request("GET", f"orders/{params.order_id}/fulfillments.json", params=p)
        fulfillments = data.get("fulfillments", [])
        return _fmt({"count": len(fulfillments), "fulfillments": fulfillments})
    except Exception as e:
        return _error(e)


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PayoutTxnInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payout_id: Optional[int] = Field(default=None, description="Limit to one payout's transactions")


async def _payments_get(path: str, params: Optional[dict] = None) -> dict:
    """Shopify Payments endpoints answer 403 when the scope is missing and 404
    when the store simply is not on Shopify Payments. Both are ordinary states
    for this store, not errors: the reconciliation engine records that the
    check COULD NOT run, which is a different fact from "no payouts exist"."""
    try:
        return await _request("GET", path, params=params)
    except httpx.HTTPStatusError as e:
        code = e.response.status_code if e.response is not None else 0
        if code in (401, 403):
            return {"available": False,
                    "reason": "The access token lacks the Shopify Payments read scopes "
                              "(read_shopify_payments_payouts / read_shopify_payments_disputes)."}
        if code == 404:
            return {"available": False,
                    "reason": "This store does not appear to use Shopify Payments."}
        raise


@mcp.tool(
    name="shopify_list_payouts",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_list_payouts(params: EmptyInput) -> str:
    """List Shopify Payments payouts (id, amount, date, status). Answers with
    available:false when the scope is missing or the store is not on Shopify Payments."""
    try:
        d = await _payments_get("shopify_payments/payouts.json", params={"limit": 250})
        if d.get("available") is False:
            return _fmt(d)
        return _fmt({"payouts": d.get("payouts", [])})
    except Exception as e:
        return _error(e)


@mcp.tool(
    name="shopify_payout_transactions",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_payout_transactions(params: PayoutTxnInput) -> str:
    """Balance transactions (charges, refunds, FEES, adjustments), optionally for one payout.
    This is where the fee that explains a payout-vs-bank gap lives."""
    try:
        q: Dict[str, Any] = {"limit": 250}
        if params.payout_id:
            q["payout_id"] = params.payout_id
        d = await _payments_get("shopify_payments/balance/transactions.json", params=q)
        if d.get("available") is False:
            return _fmt(d)
        return _fmt({"transactions": d.get("transactions", [])})
    except Exception as e:
        return _error(e)


@mcp.tool(
    name="shopify_list_disputes",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_list_disputes(params: EmptyInput) -> str:
    """Chargebacks and inquiries against the store, with amounts, reasons and status."""
    try:
        d = await _payments_get("shopify_payments/disputes.json", params={"limit": 250})
        if d.get("available") is False:
            return _fmt(d)
        return _fmt({"disputes": d.get("disputes", [])})
    except Exception as e:
        return _error(e)


@mcp.tool(
    name="shopify_get_shop",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_get_shop(params: EmptyInput) -> str:
    """Get store information: name, domain, plan, currency, timezone, etc."""
    try:
        data = await _request("GET", "shop.json")
        return _fmt(data.get("shop", data))
    except Exception as e:
        return _error(e)


# ═══════════════════════════════════════════════════════════════════════════
# WEBHOOKS
# ═══════════════════════════════════════════════════════════════════════════

class ListWebhooksInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: Optional[int] = Field(default=50, ge=1, le=250)
    topic: Optional[str] = Field(default=None, description="Filter by topic, e.g. orders/create")


@mcp.tool(
    name="shopify_list_webhooks",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def shopify_list_webhooks(params: ListWebhooksInput) -> str:
    """List configured webhooks."""
    try:
        p: Dict[str, Any] = {"limit": params.limit}
        if params.topic:
            p["topic"] = params.topic
        data     = await _request("GET", "webhooks.json", params=p)
        webhooks = data.get("webhooks", [])
        return _fmt({"count": len(webhooks), "webhooks": webhooks})
    except Exception as e:
        return _error(e)


class CreateWebhookInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    topic:   str           = Field(..., description="Webhook topic, e.g. orders/create, products/update")
    address: str           = Field(..., description="URL to receive the webhook POST")
    format:  Optional[str] = Field(default="json", description="json or xml")


@mcp.tool(
    name="shopify_create_webhook",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def shopify_create_webhook(params: CreateWebhookInput) -> str:
    """Create a new webhook subscription."""
    try:
        webhook = {"topic": params.topic, "address": params.address, "format": params.format}
        data    = await _request("POST", "webhooks.json", body={"webhook": webhook})
        return _fmt(data.get("webhook", data))
    except Exception as e:
        return _error(e)


# ---------------------------------------------------------------------------
# Store Copilot — embedded Claude chat UI (adds GET / and POST /api/chat)
# ---------------------------------------------------------------------------
# Curated READ-ONLY tools exposed to the in-admin chat assistant. Write tools
# are intentionally excluded so the copilot can analyze and suggest, never
# mutate the store. The same functions still power the full MCP integration.
COPILOT_TOOLS = {
    "shopify_get_shop":              (shopify_get_shop,              EmptyInput),
    "shopify_list_products":         (shopify_list_products,         ListProductsInput),
    "shopify_get_product":           (shopify_get_product,           GetProductInput),
    "shopify_count_products":        (shopify_count_products,        ProductCountInput),
    "shopify_list_orders":           (shopify_list_orders,           ListOrdersInput),
    "shopify_get_order":             (shopify_get_order,             GetOrderInput),
    "shopify_count_orders":          (shopify_count_orders,          OrderCountInput),
    "shopify_list_customers":        (shopify_list_customers,        ListCustomersInput),
    "shopify_search_customers":      (shopify_search_customers,      SearchCustomersInput),
    "shopify_get_customer":          (shopify_get_customer,          GetCustomerInput),
    "shopify_get_customer_orders":   (shopify_get_customer_orders,   CustomerOrdersInput),
    "shopify_list_collections":      (shopify_list_collections,      ListCollectionsInput),
    "shopify_get_collection_products": (shopify_get_collection_products, GetCollectionProductsInput),
    "shopify_list_locations":        (shopify_list_locations,        ListInventoryLocationsInput),
    "shopify_get_inventory_levels":  (shopify_get_inventory_levels,  GetInventoryLevelsInput),
    "shopify_get_variant":           (shopify_get_variant,           GetVariantInput),
    "shopify_get_inventory_items":   (shopify_get_inventory_items,   GetInventoryItemsInput),
    "shopify_list_webhooks":         (shopify_list_webhooks,         ListWebhooksInput),
    "shopify_list_payouts":          (shopify_list_payouts,          EmptyInput),
    "shopify_payout_transactions":   (shopify_payout_transactions,   PayoutTxnInput),
    "shopify_list_disputes":         (shopify_list_disputes,         EmptyInput),
}

async def update_order_tags(order_id: int, tags: str) -> dict:
    """Replace an order's tag string. Deliberately NOT in COPILOT_TOOLS: the AI
    chat must stay read-only. Only the app's own print/made button paths call
    this, via the writer handed to copilot.add_routes below."""
    return await _request("PUT", f"orders/{order_id}.json",
                          body={"order": {"id": int(order_id), "tags": tags}})


def _template_gone(msg: str) -> bool:
    """Shopify no longer accepts the cached template id - deleted and recreated
    with a new gid, most often. Order matters here: "does not exist" contains
    "exist", so testing a success phrase first turned every missing-template
    failure into a cheerful "already on the order"."""
    low = (msg or "").lower()
    return ("template" in low or "not found" in low or "invalid" in low
            or "does not exist" in low)


# The writes this app actually performs, and the scope each one needs. A
# missing scope is invisible until the moment it matters - the payment-terms
# writer failed on every account order for days because the app requested
# read_payment_terms and never write_payment_terms, and nothing said so.
REQUIRED_WRITE_SCOPES = {
    "write_orders": "editing an order, moving its tags",
    "write_fulfillments": "marking an order shipped",
    "write_merchant_managed_fulfillment_orders": "fulfilling and holding orders",
    "write_payment_terms": "putting an unpaid purchase order on 30-day terms",
}
_granted_scopes: dict = {"at": 0.0, "scopes": None, "error": ""}


async def shopify_granted_scopes(max_age: float = 900.0) -> dict:
    """{"scopes": [...], "missing": {scope: why}, "error": str}.

    What the INSTALLED app may actually do, read from Shopify rather than
    from the config file that merely asks. Cached: this answers a settings
    panel, not a hot path."""
    now = time.monotonic()
    if _granted_scopes["scopes"] is not None and now - _granted_scopes["at"] < max_age:
        got = _granted_scopes["scopes"]
    else:
        try:
            data = await _request("POST", "graphql.json", idempotent=True, body={
                "query": "{ currentAppInstallation { accessScopes { handle } } }"})
            rows = (((data.get("data") or {}).get("currentAppInstallation") or {})
                    .get("accessScopes")) or []
            got = sorted({str(r.get("handle") or "") for r in rows if r.get("handle")})
            if not got:
                raise RuntimeError("no scopes returned")
            _granted_scopes.update({"at": now, "scopes": got, "error": ""})
        except Exception as e:
            _granted_scopes["error"] = str(e)[:200]
            # Unknown is not the same as missing: never claim a scope is
            # absent because the lookup itself failed.
            return {"scopes": [], "missing": {}, "error": str(e)[:200]}
    return {"scopes": got, "error": "",
            "missing": {k: v for k, v in REQUIRED_WRITE_SCOPES.items() if k not in got}}


async def shopify_order_tax_id(order_id: int) -> dict:
    """{"tax_id": str, "source": str} - the RECEIVER's tax / VAT id for a
    customs declaration, or empty when the customer has not given one.

    Shopify keeps this in more than one place and the Customer object itself
    has no tax-id field at all, so all three are asked in ONE query and the
    most authoritative answer wins:

      1. the order's own localization extensions with purpose TAX - the
         country-specific credential a checkout collects (ES, IT, PT, TR, MX,
         BR and the rest);
      2. a B2B order's company location tax registration id (purchasingEntity
         -> PurchasingCompany -> location.taxSettings.taxRegistrationId);
      3. a customer metafield that names itself tax or vat - where a shop
         records it by hand when neither of the above applies.

    Read-only, and never fatal: a failure here means the operator types the
    number as they always have."""
    q = """query($id: ID!) {
      order(id: $id) {
        localizationExtensions(first: 10, purposes: [TAX]) {
          edges { node { key value title countryCode } } }
        purchasingEntity {
          ... on PurchasingCompany {
            company { name }
            location { name taxSettings { taxRegistrationId } } } }
        customer { id metafields(first: 30) { edges { node { namespace key value } } } }
      }
    }"""
    try:
        data = await _request("POST", "graphql.json", idempotent=True, body={
            "query": q, "variables": {"id": f"gid://shopify/Order/{int(order_id)}"}})
        order = ((data.get("data") or {}).get("order")) or {}
        if not order:
            return {"tax_id": "", "source": ""}
        for e in (((order.get("localizationExtensions") or {}).get("edges")) or []):
            n = e.get("node") or {}
            val = str(n.get("value") or "").strip()
            if val:
                what = str(n.get("title") or n.get("key") or "tax id")
                return {"tax_id": val[:40], "source": "the order's " + what}
        pe = order.get("purchasingEntity") or {}
        loc = pe.get("location") or {}
        reg = str(((loc.get("taxSettings") or {}).get("taxRegistrationId")) or "").strip()
        if reg:
            co = (pe.get("company") or {}).get("name") or loc.get("name") or "the company"
            return {"tax_id": reg[:40], "source": str(co)[:60] + "'s tax registration"}
        for e in ((((order.get("customer") or {}).get("metafields") or {}).get("edges")) or []):
            n = e.get("node") or {}
            name = (str(n.get("namespace") or "") + "." + str(n.get("key") or "")).lower()
            val = str(n.get("value") or "").strip()
            # Only a field that SAYS it is one, and only a plausible id: a
            # wrong number on a declaration is worse than an empty box.
            if val and 4 <= len(val) <= 40 and ("tax" in name or "vat" in name or "eori" in name):
                return {"tax_id": val[:40], "source": "the customer's " + name + " field"}
        return {"tax_id": "", "source": ""}
    except Exception as e:
        logger.warning("tax id lookup failed for order %s: %s", order_id, str(e)[:200])
        return {"tax_id": "", "source": "", "error": str(e)[:200]}


_net30_template = {"id": ""}    # found once, remembered for the process's life

async def set_order_payment_terms_net30(order_id: int) -> dict:
    """Put NET-30 payment terms on an order.

    GraphQL, because payment terms have no REST surface. Needs write_payment_terms.

    An order usually ALREADY carries payment terms - Shopify gives one to
    anything that came through a checkout - and `paymentTermsCreate` refuses
    outright when any exist, with a message saying so. Creating blindly and
    reading "already" as success is therefore wrong twice over: it never
    attaches anything, and it reports the goal state to a merchant who is about
    to invoice on terms the order does not have. So this reads what is on the
    order first and then does the matching thing:

      nothing there            -> create
      already Net 30           -> nothing to do, and say so truthfully
      some other terms         -> update those terms to the Net 30 template

    Deliberately NOT in COPILOT_TOOLS - the AI chat stays read-only; only the
    app's own release paths reach this, via the writer handed to
    copilot.add_routes. Returns {ok, ...} and never raises for the expected
    cases, so the release flow can report instead of break.
    """
    async def gql(query: str, variables: dict, read: bool = False) -> dict:
        # GraphQL travels by POST, so the transport treats every call here as a
        # write and will not retry it after an ambiguous failure. That is right
        # for the mutations and wrong for the two queries: a read costs nothing
        # to repeat, and losing one to a blip fails a release for no reason.
        return await _request("POST", "graphql.json", idempotent=read,
                              body={"query": query, "variables": variables})

    def _throttled(payload: dict) -> bool:
        """Shopify answers a throttled GraphQL call with HTTP 200 and an errors
        array, so it never reaches the HTTP retry path. Every call here has to
        recognise it, or the merchant is told something that reads like a real
        refusal when the answer is simply to try again."""
        for e in (payload.get("errors") or []):
            code = str(((e.get("extensions") or {}).get("code")) or "").upper()
            if code == "THROTTLED" or "throttl" in str(e.get("message", "")).lower():
                return True
        return False

    _THROTTLE = {"ok": False, "reason": "throttled",
                 "detail": "Shopify is rate-limiting right now; the terms were not "
                           "attached. Try this order again in a moment."}

    async def _terms_now() -> Optional[dict]:
        """What payment terms the order carries RIGHT NOW.

        For deciding whether a write we lost the answer to actually happened.
        A create that succeeds and then loses its response - a timeout, a
        gateway 502 - leaves the order correctly on Net 30 while the release
        reports a red failure, which is the one thing this function exists to
        stop. None means we could not find out."""
        try:
            again = await gql("query($id: ID!) { order(id: $id) { paymentTerms {"
                              " id paymentTermsName paymentTermsType dueInDays } } }",
                              {"id": gid}, read=True)
        except Exception:
            return None
        if _throttled(again):
            return None
        return ((again.get("data") or {}).get("order") or {}).get("paymentTerms") or None

    def _is_net30(terms: Optional[dict]) -> bool:
        return bool(terms and terms.get("paymentTermsType") == "NET"
                    and terms.get("dueInDays") == 30)

    def _perm(scope: str) -> dict:
        return {"ok": False, "reason": "permission",
                "detail": "The access token lacks " + scope + "."}

    def _user_errors(payload: dict, key: str) -> str:
        errs = (((payload.get("data") or {}).get(key) or {}).get("userErrors")) or []
        return "; ".join(str(e.get("message") or "") for e in errs)[:200]

    gid = f"gid://shopify/Order/{int(order_id)}"
    try:
        if not _net30_template["id"]:
            t = await gql("query { paymentTermsTemplates { id name paymentTermsType dueInDays } }",
                          {}, read=True)
            rows = ((t.get("data") or {}).get("paymentTermsTemplates")) or []
            hit = next((x for x in rows
                        if x.get("paymentTermsType") == "NET" and x.get("dueInDays") == 30), None)
            if not hit:
                # A throttled answer is not "your store has no Net 30 template",
                # which sent the merchant off to fix a configuration that was
                # never wrong.
                if _throttled(t):
                    return dict(_THROTTLE)
                for e in (t.get("errors") or []):
                    if "access" in str(e.get("message", "")).lower():
                        return _perm("the payment terms scopes "
                                     "(read_payment_terms / write_payment_terms)")
                # ANY other error means we did not get to see the templates, so
                # we do not know that there is no Net 30 one. Saying there is
                # none sends the merchant to build a template they already have.
                first = str(((t.get("errors") or [{}])[0]).get("message") or "").strip()
                if first:
                    return {"ok": False, "reason": "graphql",
                            "detail": "Shopify could not list the payment terms templates: "
                                      + first[:160]}
                return {"ok": False, "reason": "no_template",
                        "detail": "No Net 30 payment terms template exists on this store."}
            _net30_template["id"] = str(hit["id"])

        # What is on the order right now.
        q = await gql("query($id: ID!) { order(id: $id) { createdAt paymentTerms {"
                      " id paymentTermsName paymentTermsType dueInDays } } }",
                      {"id": gid}, read=True)
        if _throttled(q):
            return dict(_THROTTLE)
        for e in (q.get("errors") or []):
            msg = str(e.get("message") or "")
            if "access" in msg.lower():
                return _perm("read_payment_terms")
            return {"ok": False, "reason": "graphql", "detail": msg[:200]}
        order = ((q.get("data") or {}).get("order")) or {}
        if not order:
            return {"ok": False, "reason": "not_found",
                    "detail": "Shopify did not return that order."}
        current = order.get("paymentTerms") or None
        # Shopify emits createdAt in exactly the form it wants back as issuedAt.
        # The Liability tab computes a missing due date as created + days, so
        # issuing from the order date keeps Shopify's due date and the app's
        # identical instead of a day or two apart.
        issued = str(order.get("createdAt") or "") or None
        schedules = [{"issuedAt": issued}] if issued else []

        if current:
            was = str(current.get("paymentTermsName") or "").strip() or "existing terms"
            if current.get("paymentTermsType") == "NET" and current.get("dueInDays") == 30:
                return {"ok": True, "already": True, "name": was}
            m = await gql(
                "mutation($input: PaymentTermsUpdateInput!) {"
                " paymentTermsUpdate(input: $input) {"
                "   paymentTerms { id }"
                "   userErrors { field message } } }",
                {"input": {"paymentTermsId": str(current.get("id") or ""),
                           "paymentTermsAttributes": {
                               "paymentTermsTemplateId": _net30_template["id"],
                               "paymentSchedules": schedules}}})
            if _throttled(m):
                return dict(_THROTTLE)
            for e in (m.get("errors") or []):
                msg = str(e.get("message") or "")
                if "access" in msg.lower():
                    return _perm("write_payment_terms")
                return {"ok": False, "reason": "graphql", "detail": msg[:200]}
            msg = _user_errors(m, "paymentTermsUpdate")
            if msg:
                if _template_gone(msg):
                    _net30_template["id"] = ""
                return {"ok": False, "reason": "user_error", "detail": msg, "was": was}
            return {"ok": True, "updated": True, "was": was}

        m = await gql(
            "mutation($referenceId: ID!, $paymentTermsAttributes: PaymentTermsCreateInput!) {"
            " paymentTermsCreate(referenceId: $referenceId,"
            "                    paymentTermsAttributes: $paymentTermsAttributes) {"
            "   paymentTerms { id }"
            "   userErrors { field message } } }",
            {"referenceId": gid,
             "paymentTermsAttributes": {"paymentTermsTemplateId": _net30_template["id"],
                                        "paymentSchedules": schedules}})
        if _throttled(m):
            return dict(_THROTTLE)
        for e in (m.get("errors") or []):
            msg = str(e.get("message") or "")
            if "access" in msg.lower():
                return _perm("write_payment_terms")
            return {"ok": False, "reason": "graphql", "detail": msg[:200]}
        msg = _user_errors(m, "paymentTermsCreate")
        if msg:
            if _template_gone(msg):
                _net30_template["id"] = ""
            # Terms appeared between the read and the write. Rare, but the answer
            # is a re-run, not a false claim of success.
            if "already" in msg.lower():
                return {"ok": False, "reason": "raced",
                        "detail": "Payment terms were added to this order while it was "
                                  "being released. Press it once more."}
            return {"ok": False, "reason": "user_error", "detail": msg}
        return {"ok": True, "created": True}
    except httpx.HTTPStatusError as e:
        code = e.response.status_code if e.response is not None else 0
        if code == 403:
            return _perm("write_payment_terms")
        if code == 401:
            # NOT a missing scope: the token itself was refused (expired, or
            # revoked by a re-install). Sending the merchant to add a scope
            # they already have is the wrong errand.
            return {"ok": False, "reason": "auth",
                    "detail": "Shopify refused the app's access token. Open the app from "
                              "your Shopify admin to refresh it, then try again."}
        landed = await _terms_now()
        if _is_net30(landed):
            logger.warning("payment terms: Shopify answered %s but order %s is on Net 30",
                           code, order_id)
            return {"ok": True, "verified": True,
                    "name": str((landed or {}).get("paymentTermsName") or "Net 30")}
        return {"ok": False, "reason": "http", "detail": f"Shopify answered {code}."}
    except (httpx.TimeoutException, httpx.TransportError):
        # The write may well have landed; asking beats guessing, and guessing
        # wrong here means a red failure toast over an order that is correctly
        # on 30-day terms.
        landed = await _terms_now()
        if _is_net30(landed):
            logger.warning("payment terms: the answer was lost but order %s is on Net 30", order_id)
            return {"ok": True, "verified": True,
                    "name": str((landed or {}).get("paymentTermsName") or "Net 30")}
        return {"ok": False, "reason": "timeout",
                "detail": "Shopify did not answer in time, and the order is not on 30-day "
                          "terms. Try this order again."}
    except Exception as e:
        logger.exception("payment terms: net-30 attach failed for order %s", order_id)
        return {"ok": False, "reason": "error", "detail": str(e)[:200]}


async def create_order_fulfillment(
    order_id: int,
    tracking_number: Optional[str] = None,
    tracking_company: Optional[str] = None,
    tracking_url: Optional[str] = None,
    notify_customer: bool = True,
) -> dict:
    """Mark an order shipped via the modern fulfillment-orders flow (the legacy
    orders/{id}/fulfillments.json endpoint is gone). Fulfils every open/in-progress
    fulfillment order in full and attaches tracking. Returns a small status dict;
    never raises for the expected "nothing to fulfill" / "no permission" cases so
    the dispatch flow can report them cleanly.

    Deliberately NOT in COPILOT_TOOLS — the AI chat stays read-only; only the app's
    own Dispatch button reaches this, via the writer handed to copilot.add_routes."""
    try:
        fo = await _request("GET", f"orders/{order_id}/fulfillment_orders.json")
    except httpx.HTTPStatusError as e:
        code = e.response.status_code if e.response is not None else 0
        if code in (401, 403):
            return {"ok": False, "reason": "permission",
                    "detail": "The access token is missing fulfillment permissions "
                              "(read/write merchant-managed fulfillment orders + write_fulfillments)."}
        raise
    orders = fo.get("fulfillment_orders", []) or []
    # Only fulfillment orders we can actually action now.
    groups = [{"fulfillment_order_id": f["id"]}
              for f in orders
              if f.get("status") in ("open", "in_progress", "scheduled")
              and f.get("id")]
    if not groups:
        return {"ok": False, "reason": "nothing_to_fulfill",
                "detail": "Shopify has no open items to fulfill for this order "
                          "(it may already be fulfilled)."}
    tracking_info = {}
    if tracking_number:
        tracking_info["number"] = tracking_number
    if tracking_company:
        tracking_info["company"] = tracking_company
    if tracking_url:
        tracking_info["url"] = tracking_url
    body = {"fulfillment": {
        "line_items_by_fulfillment_order": groups,
        "notify_customer": bool(notify_customer),
    }}
    if tracking_info:
        body["fulfillment"]["tracking_info"] = tracking_info
    async def _already_landed() -> Optional[dict]:
        """Did the write we just lost the answer to actually happen? A create
        that succeeds and then loses its response - a 30s timeout, a gateway
        502 - has already emailed the customer their tracking. Reporting that
        as a failure (which reverts the tag and leaves the order sitting in the
        queue) is the worse half of the two wrong answers, so ask Shopify."""
        try:
            again = await _request("GET", f"orders/{order_id}/fulfillment_orders.json")
        except Exception:
            return None
        rows = again.get("fulfillment_orders", []) or []
        tried = {g["fulfillment_order_id"] for g in groups}
        still_open = [r for r in rows if r.get("id") in tried
                      and r.get("status") in ("open", "in_progress", "scheduled")]
        if still_open:
            return None                      # nothing landed; the caller's error stands
        fid, status = None, ""
        try:
            done = await _request("GET", f"orders/{order_id}/fulfillments.json")
            live = [f for f in (done.get("fulfillments") or [])
                    if f.get("status") != "cancelled"]
            if live:
                fid, status = live[-1].get("id"), live[-1].get("status") or ""
        except Exception:
            pass
        return {"ok": True, "fulfillment_id": fid, "status": status,
                "note": "Shopify did not answer, but the fulfillment is there."}

    try:
        data = await _request("POST", "fulfillments.json", body=body)
    except httpx.HTTPStatusError as e:
        code = e.response.status_code if e.response is not None else 0
        if code in (401, 403):
            return {"ok": False, "reason": "permission",
                    "detail": "The access token can read fulfillment orders but cannot create "
                              "fulfillments (needs write_fulfillments)."}
        landed = await _already_landed()
        if landed:
            logger.warning("fulfillment POST answered %s but the fulfillment exists; "
                           "treating order %s as fulfilled", code, order_id)
            return landed
        raise
    except (httpx.TimeoutException, httpx.TransportError):
        landed = await _already_landed()
        if landed:
            logger.warning("fulfillment POST timed out but the fulfillment exists; "
                           "treating order %s as fulfilled", order_id)
            return landed
        raise
    f = data.get("fulfillment", data)
    return {"ok": True, "fulfillment_id": f.get("id"), "status": f.get("status")}


async def cancel_order_fulfillment(fulfillment_id: int) -> dict:
    """Cancel a fulfillment (used when a dispatched shipment is voided, so the
    customer is not left holding dead tracking). Same rules as the other writers:
    NOT in COPILOT_TOOLS, reachable only from the app's own Cancel action."""
    try:
        await _request("POST", f"fulfillments/{int(fulfillment_id)}/cancel.json")
        return {"ok": True}
    except httpx.HTTPStatusError as e:
        code = e.response.status_code if e.response is not None else 0
        if code in (401, 403):
            return {"ok": False, "detail": "The access token cannot cancel fulfillments "
                                           "(needs write_fulfillments)."}
        return {"ok": False, "detail": f"Shopify refused the fulfillment cancel ({code})."}
    except Exception as e:
        return {"ok": False, "detail": f"Fulfillment cancel failed: {type(e).__name__}"}


# Webhook topics the desk listens for. orders/updated fires for paid, cancelled,
# edited, fulfilled and tag changes, so together these cover everything the
# order snapshot caches; duplicate deliveries are deduped at the receiver.
WEBHOOK_TOPICS = ("orders/create", "orders/updated", "refunds/create")


def _app_public_url() -> str:
    """Where Shopify should POST webhooks: this app's own public address.
    Railway sets RAILWAY_PUBLIC_DOMAIN; APP_URL overrides for anything else.
    Empty locally, which simply leaves webhooks unregistered there."""
    url = os.environ.get("APP_URL", "").strip().rstrip("/")
    if url:
        return url
    dom = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
    return f"https://{dom}" if dom else ""


async def ensure_order_webhooks() -> dict:
    """Make sure the order webhooks exist and point at this deployment.

    Idempotent and safe to run hourly: Shopify quietly deletes a subscription
    after sustained delivery failure (an outage on our side), so registration
    must be a standing repair, not a one-off install step. Returns a small
    status dict for the Settings panel; never raises."""
    base = _app_public_url()
    if not base:
        return {"ok": False, "detail": "No public URL (APP_URL/RAILWAY_PUBLIC_DOMAIN unset)."}
    address = base + "/webhooks/orders"
    try:
        data = await _request("GET", "webhooks.json", params={"limit": 250})
        have = {}
        for w in data.get("webhooks", []):
            if str(w.get("address") or "") == address:
                have[str(w.get("topic") or "")] = w
        made = 0
        for topic in WEBHOOK_TOPICS:
            if topic in have:
                continue
            await _request("POST", "webhooks.json",
                           body={"webhook": {"topic": topic, "address": address, "format": "json"}})
            made += 1
        if made:
            logger.info("webhooks: registered %d subscription(s) at %s", made, address)
        return {"ok": True, "address": address,
                "topics": sorted(set(list(have.keys()) + list(WEBHOOK_TOPICS)))}
    except Exception as e:
        logger.warning("webhooks: could not ensure subscriptions: %s", e)
        return {"ok": False, "detail": f"{type(e).__name__}: {e}"[:200]}


# The subset of an order Shopify actually lets you change after the fact, in the
# app's own internal address shape (the one _ship_to produces and ADDR_FIELDS
# edits). Anything not named here is not sent, so a partial form cannot blank a
# field it never showed.
_ORDER_ADDR_MAP = {
    "firstname": "firstName", "lastname": "lastName", "company": "company",
    "street": "address1", "street2": "address2", "city": "city",
    "postcode": "zip", "phone": "phone",
}


def _addr_input(a: dict) -> dict:
    """Our address shape -> Shopify's address input.

    Country and province each have a code form and a free-text form, and sending
    both invites a conflict, so exactly one of each goes: the code when it looks
    like a code, the text otherwise. A merchant who types "United Kingdom" gets
    `country`; one who types "GB" gets `countryCode`, which is the enum Shopify
    actually validates against.
    """
    out = {}
    for ours, theirs in _ORDER_ADDR_MAP.items():
        if ours in a:
            out[theirs] = str(a.get(ours) or "")
    country = str(a.get("country") or "").strip()
    if country:
        out["countryCode" if len(country) == 2 else "country"] = (
            country.upper() if len(country) == 2 else country)
    state = str(a.get("state") or "").strip()
    if state:
        out["provinceCode" if len(state) in (2, 3) else "province"] = (
            state.upper() if len(state) in (2, 3) else state)
    return out


async def update_order_fields(order_id: int, fields: dict) -> dict:
    """Change what Shopify still allows on a placed order: the delivery address,
    the contact details and the note.

    GraphQL, not REST. The REST order update cannot touch shipping_address at
    all - verified against the Admin API reference, which says only "a few"
    attributes are changeable and names addresses among those that are not - and
    REST has been legacy since October 2024. Needs write_orders.

    Tags are deliberately NOT accepted here even though orderUpdate would take
    them: orderUpdate REPLACES the whole tag list, and this app's production
    queues are tag-driven. Tag changes go through update_order_tags, which reads,
    merges and writes under a per-order lock.

    Deliberately NOT in COPILOT_TOOLS - the AI chat stays read-only; only the
    app's own Edit panel reaches this, via the writer handed to
    copilot.add_routes. Returns {ok, ...} and never raises for the expected cases
    so the route can report instead of break.
    """
    inp = {"id": f"gid://shopify/Order/{int(order_id)}"}
    if isinstance(fields.get("ship_to"), dict):
        addr = _addr_input(fields["ship_to"])
        if addr:
            inp["shippingAddress"] = addr
    for ours, theirs in (("email", "email"), ("phone", "phone"), ("note", "note")):
        if ours in fields:
            inp[theirs] = str(fields.get(ours) or "")
    if len(inp) == 1:
        return {"ok": False, "reason": "nothing", "detail": "Nothing to change."}
    try:
        m = await _request("POST", "graphql.json", body={
            "query": "mutation($input: OrderInput!) { orderUpdate(input: $input) {"
                     "   order { id }"
                     "   userErrors { field message } } }",
            "variables": {"input": inp}})
        for e in (m.get("errors") or []):
            msg = str(e.get("message") or "")
            if "access" in msg.lower():
                return {"ok": False, "reason": "permission",
                        "detail": "The access token lacks write_orders."}
            return {"ok": False, "reason": "graphql", "detail": msg[:200]}
        errs = (((m.get("data") or {}).get("orderUpdate") or {}).get("userErrors")) or []
        if errs:
            # Shopify names the offending field, and "shippingAddress.countryCode"
            # is a far more useful thing to put on screen than "invalid".
            detail = "; ".join(
                (".".join(str(x) for x in (e.get("field") or []) if x != "input") + ": "
                 if e.get("field") else "") + str(e.get("message") or "")
                for e in errs)[:300]
            return {"ok": False, "reason": "user_error", "detail": detail}
        return {"ok": True}
    except httpx.HTTPStatusError as e:
        code = e.response.status_code if e.response is not None else 0
        if code in (401, 403):
            return {"ok": False, "reason": "permission",
                    "detail": "The access token lacks write_orders."}
        return {"ok": False, "reason": "http", "detail": f"Shopify answered {code}."}
    except Exception as e:
        logger.exception("order update failed for order %s", order_id)
        return {"ok": False, "reason": "error", "detail": str(e)[:200]}


try:
    import copilot
    copilot.add_routes(mcp, COPILOT_TOOLS,
                       order_tag_writer=update_order_tags,
                       fulfillment_writer=create_order_fulfillment,
                       fulfillment_canceler=cancel_order_fulfillment,
                       webhook_ensurer=ensure_order_webhooks,
                       payment_terms_writer=set_order_payment_terms_net30,
                       scope_reader=shopify_granted_scopes,
                       tax_id_reader=shopify_order_tax_id,
                       order_writer=update_order_fields)
except Exception as e:
    logger.error(f"Store Copilot disabled (chat UI unavailable): {e}")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if MCP_TRANSPORT == "streamable-http":
        # Build the ASGI app ourselves so we can wrap /mcp with auth middleware.
        import uvicorn
        app = build_app()
        if not MCP_BEARER_TOKEN:
            logger.warning("SECURITY: MCP_BEARER_TOKEN not set — /mcp is locked (returns 503).")
        # access_log off: uvicorn's access lines print full query strings, which for
        # this app include live session tokens and signed print URLs. Route handlers
        # already log every meaningful request without secrets.
        uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info", access_log=False)
    else:
        mcp.run(transport=MCP_TRANSPORT)
