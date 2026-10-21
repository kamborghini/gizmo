"""The page's routes: the page itself and its three assets. Gathered from
add_routes (stage 4 of the 14 October audit) where the first stood; their
paths are literal, so no request changes hands.
"""
import logging
from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse, Response

import copilot as core
from gizmo import config
from gizmo import gate
from gizmo import scheduler
from gizmo import rendering

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


def register(mcp, registry):
    """Add the page and its assets to the app."""

    @mcp.custom_route("/", methods=["GET"])
    async def index(request: Request):
        # When embedded, only serve the page when it's loaded from Shopify
        # admin (which always appends shop/host/embedded). A direct browser
        # visit has none of those — return nothing so the app is invisible
        # outside the admin. (Real auth is still enforced on /api/chat.)
        if config.SHOPIFY_API_KEY:
            qp = request.query_params
            if not (qp.get("shop") or qp.get("host") or qp.get("embedded") or qp.get("id_token")):
                return PlainTextResponse("Not Found", status_code=404, headers=gate._API_HEADERS)
        scheduler._ensure_scheduler(registry)  # start the background auto-refresh loop on first load (no-op until enabled)
        headers = rendering._frame_headers(request)
        headers["ETag"] = etag = rendering._page_etag()
        if rendering._etag_matches(request.headers.get("if-none-match"), etag):
            # Same build: send the headers again (the CSP's frame-ancestors is
            # computed per request, so a bare 304 would leave the browser using
            # whichever one it stored) and skip the body.
            return Response(status_code=304, headers=headers)
        return HTMLResponse(rendering._render_page(), headers=headers)

    @mcp.custom_route("/assets/app.css", methods=["GET"])
    async def app_css(request: Request):
        return rendering._asset_response("css", request.query_params.get("v", ""),
                               request.headers.get("accept-encoding", ""))

    @mcp.custom_route("/assets/app.js", methods=["GET"])
    async def app_js(request: Request):
        return rendering._asset_response("js", request.query_params.get("v", ""),
                               request.headers.get("accept-encoding", ""))

    @mcp.custom_route("/assets/composer.js", methods=["GET"])
    async def composer_js(request: Request):
        return rendering._asset_response("composer", request.query_params.get("v", ""),
                               request.headers.get("accept-encoding", ""))
