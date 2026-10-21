"""The status page and the health check. Gathered from add_routes (stage 4 of
the 14 October audit) where the first stood; their paths are literal, so no
request changes hands.
"""
import logging
import os
import perf
import google_data
import google_mail
try:
    import worldoptions
except Exception:                     # keep the app booting if the connector is unavailable
    worldoptions = None
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from gizmo import store as jsonstore
from gizmo import errors
from gizmo import ai as claude
from gizmo import shopify

import copilot as core
from gizmo import backup
from gizmo import gate
from gizmo import orderbook
from gizmo import scheduler
from gizmo import size_list
from gizmo import team
from gizmo import status as appstatus

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


def register(mcp, registry):
    """Add the status page and the health check to the app."""

    @mcp.custom_route("/healthz", methods=["GET"])
    async def healthz(request: Request):
        # Also the scheduler's boot hook: the platform polls this, so auto-refresh
        # resumes after a redeploy without waiting for someone to open the app.
        scheduler._ensure_scheduler(registry)
        # The running build's commit, so "is the deploy live" is an exact check
        # against a hash rather than an inference from a 200. Railway sets the env.
        sha = (os.environ.get("RAILWAY_GIT_COMMIT_SHA") or "")[:12]
        return PlainTextResponse("ok " + sha if sha else "ok")

    @mcp.custom_route("/api/status", methods=["POST"])
    async def status_route(request: Request):
        """Connection-health summary for the Settings panel: Shopify, AI, and Google.
        Admin+ only: the health detail carries internal error strings (the R2
        endpoint with the account id, the stock-app URL, the /data path), which
        a restricted part-time member has no business reading."""
        err, _body, who = await gate._guard(request, body=False)
        if err:
            return err
        if team._team_role(who) not in ("master", "admin"):
            return gate._json({"error": "Connection status is for admins."}, 403)
        body = await gate._read_json_capped(request)
        if body is None:
            return gate._json({"error": "Request too large."}, 413)
        api_version = shopify._api_version
        shop_ok, shop_name, currency = False, None, None
        try:
            shop = await shopify._tool_json(registry, "shopify_get_shop", {})
            if shop and shop.get("name"):
                shop_ok, shop_name, currency = True, shop.get("name"), shop.get("currency")
        except Exception:
            pass  # an unreachable shop shows as not connected (shop_ok stays False)
        # Volume sentinel: prove the data disk is writable, or nothing persists.
        vol_ok, vol_detail = True, ""
        try:
            probe = os.path.join(os.path.dirname(scheduler.SCHEDULE_PATH) or ".", ".probe")
            with open(probe, "w", encoding="utf-8") as fh:
                fh.write("ok")
            os.remove(probe)
        except Exception as e:  # the status page shows the volume as not writable, with why
            vol_ok, vol_detail = False, str(e)[:200]
        watch = scheduler._load_watch()
        health = size_list._gobo_sizes().get("health") or {}
        scope_state = {"checked": False, "missing": {}, "error": ""}
        if shopify._scope_reader is not None and shop_ok:
            try:
                got = await shopify._scope_reader()
                scope_state = {"checked": not got.get("error"),
                               "missing": got.get("missing") or {},
                               "error": got.get("error") or ""}
            except Exception as e:  # the status page shows the scope check's error
                scope_state["error"] = str(e)[:200]
        return gate._json({
            "shopify": {"ok": shop_ok, "name": shop_name, "currency": currency,
                        "api_version": api_version,
                        "down_since": watch.get("shopify_down"),
                        # What the INSTALL may actually do, read from Shopify -
                        # not what the config file asks for. A write the app
                        # performs but the install cannot is invisible until
                        # the moment it matters, which is the wrong moment.
                        "scopes": scope_state},
            "ai": {"ok": bool(claude.ANTHROPIC_API_KEY),
                   "models": {"chat": claude._model_name(claude.MODEL_FAST), "deep": claude._model_name(claude.MODEL_DEEP),
                              "fallback": claude._model_name(claude._fallback_for(claude.MODEL_DEEP, Exception())
                                                      or claude._fallback_for(claude.MODEL_FAST, Exception())) if (
                                  claude._fallback_for(claude.MODEL_DEEP, Exception()) or claude._fallback_for(claude.MODEL_FAST, Exception())) else ""},
                   "last_failure": dict(claude._AI_LAST_FAIL) or None},
            "google": google_data.status(),
            "gmail": google_mail.status(),
            "shipping": {"ok": bool(worldoptions and worldoptions.configured()),
                         "available": bool(worldoptions),
                         "fulfillment": bool(shopify._fulfillment_writer is not None)},
            "volume": {"ok": vol_ok, "detail": vol_detail,
                       "poisoned": sorted(os.path.basename(p) for p in jsonstore._poisoned_stores),
                       # Sizes, and the parse cost of anything over a megabyte:
                       # the stores are read from disk per request, so this is
                       # what a slow CRM save would show up as, before it does.
                       "stores": appstatus._store_report()},
            # Each route's typical and slowest time since this process
            # started (perf.summary), slowest first: the live numbers the
            # 2026-10-12 speed audit could only model.
            "timing": perf.summary(),
            "email_alerts": {"ok": bool(scheduler.RESEND_API_KEY and scheduler.ALERT_EMAIL_TO)},
            # Whether the long-lived credentials on the volume are encrypted.
            # Read from the FILES, not from the environment: a key that is set
            # while a token still sits in plaintext looks fine from the
            # environment alone, and that is the failure worth catching.
            "token_vault": appstatus.token_vault_state(),
            # Live updates: whether Shopify is pushing order events to the app,
            # and when one last arrived. Without them the desk falls back to the
            # short cache and the Refresh button, which still work.
            "webhooks": {"ok": bool((orderbook._webhook_state.get("ensured") or {}).get("ok")),
                         "detail": (orderbook._webhook_state.get("ensured") or {}).get("detail") or "",
                         "last_event_at": (orderbook._webhook_state["last_at"] or None),
                         "version": orderbook._webhook_state.get("version") or None,
                         "events": orderbook._webhook_state["count"]},
            # The stock bridge: glass booked at the stock app when orders are
            # marked made. Pending = bookings still waiting on a retry.
            "stock_bridge": {"configured": core._zeta_configured(),
                             "pending": len(core._load_zeta_pending()),
                             "last_ok_at": (core._zeta_last["ok_at"] or None),
                             "error": core._zeta_last["error"]},
            "backup": (lambda b: {"snapshot_at": b.get("snapshot_at"),
                                  "download_at": b.get("download_at")})(
                jsonstore._load_json_store(backup.BACKUP_STATE_PATH, "backup", {}) or {}),
            # Visible whether or not email is configured, which it is not yet.
            "errors": {"last_24h": len(errors._recent_errors(24)),
                       "recent": errors._recent_errors(24)[:5]},
            "size_list": health,
            "coverage": {"at": watch.get("coverage_at"), "pct": watch.get("coverage_pct")},
            "storage": {"warning": appstatus._data_volume_warning()},
        })
