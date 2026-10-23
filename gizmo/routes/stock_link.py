"""The day's stock usage sheet: what the bench used, reviewed and sent to the
stock sheet. Gathered from add_routes with the stock move where the first
stood; their paths are literal, so no request changes hands.
"""
import logging
from datetime import datetime, timezone
from starlette.requests import Request
from gizmo import store as jsonstore
from gizmo.gate import _guard, _json
from gizmo.activity import _track

from gizmo import stock, stock_link

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


def register(mcp, registry):
    """Add the stock usage sheet's routes to the app."""

    @mcp.custom_route("/api/stock-usage", methods=["POST"])
    async def stock_usage_route(request: Request):
        # Glass blanks consumed by everything marked Made on one day. Read-only, no AI.
        err, body, _who = await _guard(request)
        if err:
            return err
        try:
            res = await stock_link.run_stock_usage(registry, str(body.get("date") or ""))
            if not res.get("error"):
                # The day's send record rides along, so the page can say
                # "already sent" instead of letting a double-send surprise.
                sheets = jsonstore._load_json_store(stock_link.USAGE_SHEETS_PATH, "sheets", {})
                if isinstance(sheets, dict) and res.get("date") in sheets:
                    rec = dict(sheets[res["date"]])
                    rec.pop("result", None)
                    res["sent"] = rec
            return _json(res, 400 if res.get("error") else 200)
        except Exception:
            logger.exception("Stock usage failed")
            return _json({"error": "Couldn't build the stock usage list."}, 500)

    @mcp.custom_route("/api/stock-usage/send", methods=["POST"])
    async def stock_usage_send_route(request: Request):
        """The reviewed day sheet goes to the stock sheet (Reactor's own once
        it has moved in, the stock app's before) as FINAL figures. Only the
        difference against what the automatic per-order bookings already
        recorded is applied, so this can never double-count;
        re-sending a day REPLACES its previous sheet. Every line comes back
        with its own status, and the send is recorded here for the record of
        final-versus-estimate."""
        err, body, who = await _guard(request)
        if err:
            return err
        if not stock_link._zeta_configured():
            return _json({"error": "The stock app isn't connected: its address and sync "
                                   "token are not set on the server."}, 400)
        date_str = str(body.get("date") or "")
        raw = body.get("lines")
        if not isinstance(raw, list) or not raw or len(raw) > 100:
            return _json({"error": "The sheet needs between 1 and 100 lines."}, 400)
        lines = []
        for ln in raw:
            if not isinstance(ln, dict):
                continue
            family = str(ln.get("family") or "").strip()[:60]
            size = str(ln.get("size") or "").strip()[:40]
            try:
                final = int(round(float(ln.get("final"))))
                est = max(0, int(round(float(ln.get("estimated") or 0))))
            except (TypeError, ValueError, OverflowError):
                return _json({"error": f"The quantity for {family} {size} is not a number."}, 400)
            if not family or not size:
                return _json({"error": "Every line needs a glass type and a size."}, 400)
            if final < 0 or final > 10000:
                return _json({"error": f"The quantity for {family} {size} must be between "
                                       "0 and 10,000."}, 400)
            lines.append({"family": family, "size": size, "estimated": est, "final": final})
        if not lines:
            return _json({"error": "The sheet needs at least one line."}, 400)
        # The day's covered orders are recomputed HERE: the sheet's deltas are
        # measured against these orders' automatic bookings, and that list is
        # not something a page should be trusted to supply.
        try:
            usage = await stock_link.run_stock_usage(registry, date_str)
        except Exception:
            logger.exception("stock usage recompute failed")
            return _json({"error": "Couldn't rebuild the day's order list."}, 500)
        if usage.get("error"):
            return _json({"error": usage["error"]}, 400)
        # FINAL figures replace what the per-order bookings recorded, for every
        # order named in the sheet. An order that could not be read has no
        # glass in these lines, so sending it would un-book what it used.
        if usage.get("fetch_failed"):
            n = int(usage.get("fetch_failed") or 0)
            ids = ", ".join(str(i) for i in (usage.get("unread_ids") or [])[:10])
            return _json({"error": f"{n} made order{'' if n == 1 else 's'} could not be read from "
                                   f"Shopify just now (order id {ids}), so the day's figures are "
                                   "incomplete. Nothing was sent; refresh the sheet in a moment and "
                                   "send it then."}, 409)
        payload = {"sheet_id": "day-" + usage["date"], "day": usage["date"],
                   "order_ids": [str(i) for i in (usage.get("order_ids") or [])],
                   "lines": lines}
        try:
            result = await stock_link._send_sheet(payload, who)
        except stock.Refused as e:
            return _json({"error": e.words}, e.status)
        except Exception as e:
            if stock.is_live():
                logger.exception("usage sheet could not be recorded")
                return _json({"error": "The stock sheet could not record the day's sheet just now. "
                                       "Nothing was recorded; try again."}, 500)
            logger.warning("usage sheet send failed: %s", e)
            return _json({"error": "The stock app didn't accept the sheet. Nothing was "
                                   "recorded; check it is up and try again."}, 502)
        rec = {"sent_at": datetime.now(timezone.utc).isoformat(), "by": who,
               "lines": lines, "result": result, "replaced": bool(result.get("replaced"))}
        try:
            sheets = jsonstore._load_json_store(stock_link.USAGE_SHEETS_PATH, "sheets", {})
            if not isinstance(sheets, dict):
                sheets = {}
            sheets[usage["date"]] = rec
            if jsonstore._store_writable(stock_link.USAGE_SHEETS_PATH):
                jsonstore._write_json_store(stock_link.USAGE_SHEETS_PATH, "sheets", sheets)
        except Exception:
            logger.exception("usage sheet record failed (the stock app HAS the sheet)")
        _track(who, "production", "sent a stock sheet",
               f"{usage['date']} · {len(lines)} line(s)"
               + (" · replaced the earlier send" if result.get("replaced") else ""))
        gone = usage.get("gone_ids") or []
        return _json({"ok": True, "sent": {"sent_at": rec["sent_at"], "by": who,
                                           "replaced": rec["replaced"]},
                      "result": result,
                      "note": (f"{len(gone)} made order{'' if len(gone) == 1 else 's'} Shopify no "
                               f"longer has (order id {', '.join(str(i) for i in gone[:10])}) "
                               f"{'was' if len(gone) == 1 else 'were'} left out of the sheet; "
                               "the glass booked for it stays booked." if gone else "")})
