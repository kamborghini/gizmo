"""The page: splitting the one page into its shell, stylesheet and script,
rendering the shell, its ETag, the packed and hashed assets (the composer
among them), the frame headers that pin the page to the shop's admin, and
the build id. Moved out of copilot.py (stage 4 of the 14 October audit); its
routes, the page's own and its assets, are in gizmo/routes/rendering.py.
Read as `rendering.NAME`.
"""
import logging
import os
import re
import threading
import hashlib
from typing import Optional
import perf
import pagesource
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


# The repository, where static/ ships with the code. This module is one
# folder down from where copilot.py built this path from its own file.
_REPO = os.path.dirname(os.path.dirname(__file__))


_STATIC_DIR = os.path.join(_REPO, "static")   # composer.js; the page itself is joined by pagesource.py from static/src
_page_cache: Optional[str] = None   # the shell: the page with its CSS and JS lifted out
_page_assets: dict = {}             # "css" / "js" -> (media type, bytes), served at hashed URLs
_asset_hashes: dict = {}            # "css" / "js" -> the content hash in their URL
_page_etag_val: str = ""




# ---------------------------------------------------------------------------
# Page rendering
# ---------------------------------------------------------------------------

def _split_page(html: str):
    """Split the single-file app into (shell, css, js).

    The app is authored as one file deliberately, so the split happens here at
    serve time rather than in the source: the tests, the em dash check and every
    edit still see one file. Returns (html, "", "") unchanged if the markers are
    not where they are expected, so a future edit to the page can never take the
    app down, only make it heavier."""
    try:
        s0 = html.index("    <style>") + len("    <style>")
        s1 = html.index("    </style>", s0)
        j0 = html.index("    <script>", s1) + len("    <script>")
        j1 = html.index("    </script>", j0)
    except ValueError:
        logger.warning("page split: style/script markers not found, serving the page inline")
        return html, "", ""
    css, js = html[s0:s1], html[j0:j1]
    if not css.strip() or not js.strip():
        return html, "", ""
    # Assigned, not setdefault: the hash in the URL has to track the content it
    # is standing for, or a second split would serve new bytes under an old tag.
    _asset_hashes["css"] = hashlib.sha256(css.encode("utf-8")).hexdigest()[:12]
    _asset_hashes["js"] = hashlib.sha256(js.encode("utf-8")).hexdigest()[:12]
    css_url = "/assets/app.css?v=" + _asset_hashes["css"]
    js_url = "/assets/app.js?v=" + _asset_hashes["js"]
    shell = (html[:s0 - len("    <style>")]
             + f'<link rel="stylesheet" href="{css_url}" />\n'
               f'    <link rel="preload" as="script" href="{js_url}" />\n'
               f'    <meta name="app-build" content="{_build_marker(_asset_hashes["js"])}" />'
             + html[s1 + len("    </style>"):j0 - len("    <script>")]
             + f'<script src="{js_url}"></script>'
             + html[j1 + len("    </script>"):])
    return shell, css, js


def _page_parts() -> tuple:
    """(shell, assets) for the running build, computed once.

    The whole page is ~460 KB and the CSS and JS are ~95% of it. Shopify admin
    opens an embedded app with a freshly minted id_token every time, so the page
    URL is never the same twice and caching the page itself would buy nothing.
    Moving the weight into two content-hashed URLs does: those are stable across
    opens, cacheable for a year, and a new build simply asks for a new URL."""
    global _page_cache, _page_assets
    if _page_cache is None:
        # The page is joined from its sections (static/src), byte for byte the
        # single file it was: the split below and its hashed URLs are unchanged.
        raw = pagesource.join()
        shell, css, js = _split_page(raw)
        assets = {}
        if css and js:
            assets["css"] = ("text/css; charset=utf-8", css.encode("utf-8"))
            assets["js"] = ("text/javascript; charset=utf-8", js.encode("utf-8"))
            # The composer is the one script that lives outside the page: the
            # editor is big enough to deserve its own file and its own cache
            # line. Same hash-in-the-URL contract as app.js, loaded after it
            # because the page's mail code calls into it, never the reverse.
            try:
                with open(os.path.join(_STATIC_DIR, "composer.js"), "r",
                          encoding="utf-8") as fh:
                    composer = fh.read()
            except OSError:
                composer = ""
            if composer.strip():
                _asset_hashes["composer"] = hashlib.sha256(composer.encode("utf-8")).hexdigest()[:12]
                assets["composer"] = ("text/javascript; charset=utf-8", composer.encode("utf-8"))
                app_tag = '<script src="/assets/app.js?v=' + _asset_hashes["js"] + '"></script>'
                shell = shell.replace(app_tag, app_tag + '<script src="/assets/composer.js?v='
                                      + _asset_hashes["composer"] + '"></script>', 1)
            logger.info("page split: shell %d KB, css %d KB, js %d KB",
                        len(shell) // 1024, len(css) // 1024, len(js) // 1024)
        _page_cache, _page_assets = shell, assets
    return _page_cache, _page_assets


def _build_marker(js_hash: str) -> str:
    """An id that changes exactly when the JavaScript changes, and that opens
    nothing if it leaks. See _build_id for why it is not the hash itself."""
    return hashlib.sha256(("gizmo-build|" + js_hash).encode("utf-8")).hexdigest()[:12]


def _render_page() -> str:
    shell, _assets = _page_parts()
    # Embedded-only: always load App Bridge (which provides the session token).
    head = (
        f'<meta name="shopify-api-key" content="{config.SHOPIFY_API_KEY}" />\n'
        '    <script src="https://cdn.shopify.com/shopifycloud/app-bridge.js"></script>'
    ) if config.SHOPIFY_API_KEY else ""
    return shell.replace("<!--APPBRIDGE-->", head)


def _page_etag() -> str:
    """A quoted hash of exactly the bytes this build serves.

    Hashing the rendered shell rather than the commit keeps it honest in every
    environment: there is no commit sha outside Railway, and rotating
    SHOPIFY_API_KEY changes the page without changing the commit."""
    global _page_etag_val
    if not _page_etag_val:
        _page_etag_val = '"' + hashlib.sha256(_render_page().encode("utf-8")).hexdigest()[:16] + '"'
    return _page_etag_val


def _etag_matches(header: Optional[str], etag: str) -> bool:
    """RFC-shaped If-None-Match check: a list, a weak tag or * all count."""
    for part in (header or "").split(","):
        p = part.strip()
        if p == "*":
            return True
        if p.startswith("W/"):
            p = p[2:].strip()
        if p and p == etag:
            return True
    return False


# (kind, content hash, encoding) -> the asset compressed at the strongest
# level. Keyed on the hash of the bytes that were packed, never on whatever
# _asset_hashes says at that moment, so a page swapped mid-pack (the tests
# do it) can never put one build's bytes under another build's URL.
_asset_packed: dict = {}
_asset_packing: set = set()     # content hashes whose packing has started


def _pack_assets() -> None:
    """Compress the page's assets once per build, zstd and gzip at their
    strongest levels. Runs in a thread (see _pack_assets_soon): zstd at level
    19 is about half a second on app.js, which no request should wait for."""
    _shell, assets = _page_parts()
    live = set()
    for kind, (_media, blob) in list(assets.items()):
        h = hashlib.sha256(blob).hexdigest()[:12]
        live.add(h)
        for enc in ("zstd", "gzip"):
            if (kind, h, enc) not in _asset_packed:
                try:
                    _asset_packed[(kind, h, enc)] = perf.compress(blob, enc, strong=True)
                except ValueError:
                    pass                # no zstd on this Python: gzip alone
    for key in [k for k in _asset_packed if k[1] not in live]:
        _asset_packed.pop(key, None)    # an earlier build's copies


def _pack_assets_soon() -> None:
    """Start _pack_assets in a thread, once per build. Until it lands, the
    middleware compresses each request at its quick level, as before."""
    h = _asset_hashes.get("js", "")
    if not h or h in _asset_packing:
        return
    _asset_packing.add(h)

    def run():
        try:
            _pack_assets()
        except Exception:
            logger.exception("assets: packing failed; serving them compressed per request")
    threading.Thread(target=run, name="asset-pack", daemon=True).start()


def _asset_response(kind: str, version: str = "", accept: str = ""):
    """The app's own CSS or JS. Static bytes with no data and no auth, and the
    URL carries a content hash, so a year of caching is safe: a new build asks
    for a new URL and there is nothing to invalidate.

    The hash must match. The page itself 404s outside the Shopify admin, and
    without this check these two URLs would hand the app's whole client source
    to anyone who guessed the path. The shell always sends the current hash,
    and it is revalidated on every open, so it can never send a stale one.

    Served from the build's packed copy when there is one in an encoding the
    browser takes. Compressing app.js again on every uncached request cost
    about 50 ms of the event loop per first open, bunched after each update
    when everybody reloads (the 2026-10-12 audit, D3)."""
    _shell, assets = _page_parts()
    asset = assets.get(kind)
    if not asset or version != _asset_hashes.get(kind, ""):
        return PlainTextResponse("Not found", status_code=404, headers=gate._API_HEADERS)
    media, blob = asset
    headers = {**gate._API_HEADERS, "Cache-Control": "public, max-age=31536000, immutable"}
    enc = perf.pick_encoding(accept)
    packed = _asset_packed.get((kind, version, enc)) if enc else None
    if packed is None:
        _pack_assets_soon()
        return Response(blob, media_type=media, headers=headers)
    # The middleware leaves an answer that already has an encoding alone, and
    # still adds Vary: Accept-Encoding to it.
    return Response(packed, media_type=media, headers={**headers, "Content-Encoding": enc})


_SHOP_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\.myshopify\.com$")


def _frame_headers(request: Request) -> dict:
    """Headers for the chat page: allow the admin iframe (must NOT send
    X-Frame-Options) and block MIME sniffing / referrer leakage."""
    # Who may frame the page. With the store configured, that store and the
    # admin, whatever the URL says: trusting a well-formed ?shop= let any
    # myshopify.com store, a free development one included, frame Reactor
    # under decoy buttons and steer a signed-in person's clicks. Unconfigured
    # (a local run), a well-formed ?shop= or the wildcard, as before, so a
    # crafted value still cannot inject extra frame hosts.
    shop = request.query_params.get("shop", "")
    if config.SHOPIFY_STORE:
        ancestors = f"https://{config.SHOPIFY_STORE.split('.')[0]}.myshopify.com https://admin.shopify.com"
    elif _SHOP_RE.match(shop):
        ancestors = f"https://{shop} https://admin.shopify.com"
    else:
        ancestors = "https://admin.shopify.com https://*.myshopify.com"
    # Full CSP: lock down sources while allowing exactly what the page needs —
    # App Bridge (cdn.shopify.com), Google Fonts, same-origin API calls, and the
    # store/admin for the embed.
    #
    # script-src carries NO 'unsafe-inline'. It used to, from when the page was
    # one file with its script inline; splitting the JS into /assets/app.js made
    # that allowance dead weight, and dead weight in a CSP is the difference
    # between an injected string being inert and being executed. Verified before
    # removing it: the served shell has zero inline <script>, zero inline
    # <style> and zero on*= attributes, and App Bridge itself never builds a
    # script element, evals, or calls new Function. The session token lives in
    # localStorage, so this is the layer that keeps a future HTML sink from
    # becoming an account takeover.
    #
    # style-src keeps 'unsafe-inline': the page still sets element.style
    # throughout and the shell carries style= attributes. Narrowing that needs
    # its own pass and buys far less.
    csp = (
        "default-src 'self'; "
        # PATH-scoped, and only the one script the shell actually loads.
        # cdn.shopify.com is also where Shopify serves every store's uploaded
        # Files, and Shopify Files accepts .js - so a bare host entry trusts
        # JavaScript uploaded by anyone with a free development store, which
        # is the whole of what this directive is here to prevent.
        "script-src 'self' https://cdn.shopify.com/shopifycloud/; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        # Every image the page shows is a Shopify CDN product image, a data:
        # barcode, or a signed link to this account's own bucket (appended
        # below). "https:" additionally made every host on the internet a
        # beacon for anything a compromised page wanted to send out.
        "img-src 'self' data: https://cdn.shopify.com"
        + (" " + fileserver._files_endpoint() if fileserver._files_configured() else "")   # image preview from the bucket
        + "; "
        # Files uploads/downloads go browser-to-bucket, so the page must be
        # allowed to talk to this account's R2 endpoint and nothing broader.
        # Without it the browser kills the PUT before it starts and the only
        # symptom is "the transfer failed".
        # No *.myshopify.com: the page never calls one, and a name under it
        # costs a free trial signup - which made it an exfiltration host
        # anybody could register. *.shopify.com stays for App Bridge; those
        # names cannot be registered by an outsider.
        "connect-src 'self' https://*.shopify.com"
        + (" " + fileserver._files_endpoint() if fileserver._files_configured() else "")
        + "; "
        # The store's own quote domain is allowed so the Proof modal can embed
        # proposal pages; nothing else may be framed.
        f"frame-src https://*.shopify.com https://{orderbook.PROPOSAL_HOST}"
        + (" " + fileserver._files_endpoint() if fileserver._files_configured() else "")   # in-app PDF preview
        + "; "
        "base-uri 'self'; form-action 'self'; object-src 'none'; "
        f"frame-ancestors {ancestors};"
    )
    return {
        **gate._API_HEADERS,
        "Content-Security-Policy": csp,
        # The shell must be revalidated on every open so a deploy is never
        # missed; its ETag is the build's own content hash, so revalidating
        # costs a 304 rather than the page. Never add a max-age here: the URL
        # carries no build hash, so there would be no way to bust it. The bulk
        # of the app lives in the hashed /assets URLs, which cache for a year.
        "Cache-Control": "private, no-cache",
    }


def _build_id() -> str:
    """Which build answered, in every API reply.

    A browser tab left open across a deploy keeps running the old page - Shopify
    admin holds an embedded app open for days - and from the desk that is
    invisible: it looks exactly like a bug that was already fixed. The page
    carries the same marker in a meta tag and compares the two.

    Derived from the asset hash rather than being it. That hash is the token
    /assets/app.js checks before serving, and an unauthenticated call gets a
    reply (a 401 is a reply), so publishing it here would hand the app's whole
    client source to anyone who asked. This changes when the JavaScript does and
    opens nothing."""
    try:
        _page_parts()                       # fills _asset_hashes, then cached
        h = _asset_hashes.get("js", "")
        return _build_marker(h) if h else ""
    except Exception:
        return ""


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as sibling.NAME, never a copied name.
from gizmo import files as fileserver  # noqa: E402
from gizmo import gate  # noqa: E402
from gizmo import orderbook  # noqa: E402
from gizmo import config  # noqa: E402
