"""The forecast's routes: the four hooks the nightly service calls, the
Forecast tab's read and the workbook upload. Gathered from add_routes (stage
4 of the 14 October audit) where the first stood; their paths are literal,
so no request changes hands.
"""
import logging
import base64
from datetime import datetime, timezone
from starlette.requests import Request
from starlette.responses import Response
from gizmo import store as jsonstore
from gizmo import shopify

from gizmo import forecasting
from gizmo import gate
from gizmo import team
from gizmo import bodies

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")



class WorkbookBody(bodies.Body):
    """What /api/forecast/workbook reads (gizmo/bodies.py): the workbook's name and its bytes."""
    name: bodies.Text = None
    data_b64: bodies.Text = None



class ForecastResultsBody(bodies.Body):
    """What /hooks/forecast/results reads (gizmo/bodies.py): a nightly run's date and figures, or its error. The other keys the service posts are kept as they come."""
    as_of: bodies.Text = None
    error: bodies.Text = None
    monthly: bodies.Items = None
    scenarios: bodies.Items = None
    year: bodies.Fields = None
    alerts: bodies.Items = None
    seen_through: bodies.Text = None
    in_use: bodies.Fields = None
    predictions: bodies.Fields = None
    actuals: bodies.Fields = None



class ForecastShopifyBody(bodies.Body):
    """What /hooks/forecast/shopify reads (gizmo/bodies.py): the start date, the page cursor and the bulk query's id."""
    since: bodies.Text = None
    after: bodies.Text = None
    id: bodies.Text = None


def register(mcp, registry):
    """Add the forecast's routes to the app."""






    @mcp.custom_route("/hooks/forecast/results", methods=["POST"])
    async def forecast_results_hook(request: Request):
        """The nightly forecasting service (a second Railway service on this
        repo, `python -m forecast nightly`) posts each run here. A shared secret
        in the header is the whole authentication: the service has no account
        and the token never leaves the two Railway environments. A run that
        failed posts {"error": ...} so the tab can say so instead of showing a
        stale forecast as if it were fresh."""
        if not forecasting.FORECAST_INGEST_TOKEN:
            return gate._json({"error": "The forecast hook is switched off: no hook token is set on this server."}, 503)
        if not forecasting._forecast_token_ok(request):
            return gate._json({"error": "Unauthorized"}, 401)
        # No session and no rate window, like the Shopify webhook receiver: the
        # secret is the gate, and the reader caps what it will hold in memory.
        body = await gate._read_json_capped(request, cap=forecasting.FORECAST_MAX_BYTES)
        if body is None:
            return gate._json({"error": "Request too large."}, 413)
        if not isinstance(body, dict):
            return gate._json({"error": "A JSON object is required."}, 400)
        refused = gate._body_refusal(ForecastResultsBody, body)
        if refused:
            return refused
        # as_of is kept in the run history, deduped by its exact value, and in
        # the ledger: a date (or the datetime the service may send), never
        # whatever arrived, or sixty large ones would fill the volume.
        if not (isinstance(body.get("as_of"), str) and forecasting._FORECAST_AS_OF_RE.fullmatch(body["as_of"])):
            return gate._json({"error": "as_of must be the run's date, as YYYY-MM-DD."}, 400)
        state = forecasting._forecast_state()
        now = datetime.now(timezone.utc).isoformat()
        if body.get("error"):
            state["last_error"] = {"at": now, "as_of": body.get("as_of"), "error": str(body["error"])[:2000]}
        else:
            missing = [k for k in ("as_of", "monthly", "scenarios") if k not in body]
            if missing:
                return gate._json({"error": "The run is missing " + ", ".join(missing) + "."}, 400)
            body["received_at"] = now
            state["latest"] = body
            state.pop("last_error", None)
            runs = [r for r in state.get("runs", []) if r.get("as_of") != body.get("as_of")]
            runs.append({"as_of": body.get("as_of"), "received_at": now,
                         "year_p50": forecasting._forecast_figure((body.get("year") if isinstance(body.get("year"), dict) else {}).get("p50")),
                         "alerts": len(body.get("alerts") or [])})
            state["runs"] = runs[-60:]
            # Who said what, and who turned out to be right. Kept here rather
            # than in the service, because the service is stateless by design
            # and this is the one thing that has to outlive a run.
            state["ledger"] = forecasting._forecast_ledger(state, body)
        jsonstore._write_json_store(forecasting.FORECAST_PATH, "forecast", state)
        return gate._json({"ok": True})

    @mcp.custom_route("/hooks/forecast/workbook", methods=["GET"])
    async def forecast_workbook_hook(request: Request):
        """The service fetches the workbook an admin uploaded in the tab, so the
        plan lives in one place and a revised sheet reaches the next run."""
        if not forecasting.FORECAST_INGEST_TOKEN:
            return gate._json({"error": "The forecast hook is switched off: no hook token is set on this server."}, 503)
        if not forecasting._forecast_token_ok(request):
            return gate._json({"error": "Unauthorized"}, 401)
        wb = forecasting._forecast_state().get("workbook") or {}
        if not wb.get("data_b64"):
            return gate._json({"error": "No cash flow workbook has been uploaded yet."}, 404)
        try:
            raw = base64.b64decode(wb["data_b64"], validate=True)
        except (ValueError, TypeError):
            return gate._json({"error": "The stored workbook did not decode."}, 500)
        return Response(raw, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={**gate._API_HEADERS, "Cache-Control": "no-store",
                                 "Content-Disposition": 'attachment; filename="Cash Flow.xlsx"'})

    @mcp.custom_route("/hooks/forecast/ledger", methods=["GET"])
    async def forecast_ledger_hook(request: Request):
        """The service reads back who has actually been right, so a run can
        weigh its sources on their record rather than only on a backtest it
        computed itself a moment earlier."""
        if not forecasting.FORECAST_INGEST_TOKEN:
            return gate._json({"error": "The forecast hook is switched off: no hook token is set on this server."}, 503)
        if not forecasting._forecast_token_ok(request):
            return gate._json({"error": "Unauthorized"}, 401)
        led = forecasting._forecast_state().get("ledger")
        led = led if isinstance(led, dict) else {}
        return gate._json({"results": (led.get("results") or [])[-36:]})

    @mcp.custom_route("/hooks/forecast/shopify", methods=["POST"])
    async def forecast_shopify_hook(request: Request):
        """The service's reads of the store, made here with the app's own
        credential, so the service holds no Shopify credential at all. It once
        held the app's client secret, which also signs every webhook this app
        trusts. Four fixed reads (see server.forecast_store_read), nothing
        else: the token that opens them cannot write, and cannot choose what
        is read beyond a date and a page."""
        if not forecasting.FORECAST_INGEST_TOKEN:
            return gate._json({"error": "The forecast hook is switched off: no hook token is set on this server."}, 503)
        if not forecasting._forecast_token_ok(request):
            return gate._json({"error": "Unauthorized"}, 401)
        body = await gate._read_json_capped(request, cap=4096)
        if body is None:
            return gate._json({"error": "Request too large."}, 413)
        if not isinstance(body, dict):
            return gate._json({"error": "A JSON object is required."}, 400)
        refused = gate._body_refusal(ForecastShopifyBody, body)
        if refused:
            return refused
        if shopify._forecast_reader is None:
            return gate._json({"error": "The store is not connected."}, 503)
        out = await shopify._forecast_reader(str(body.get("op") or ""), body)
        if out.get("error"):
            return gate._json({"error": out["error"]}, int(out.get("status") or 502))
        return gate._json({"data": out.get("data")})

    @mcp.custom_route("/api/forecast", methods=["POST"])
    async def forecast_route(request: Request):
        """What the tab shows: the latest run, the last failure if the latest
        attempt failed, the recent runs, the workbook on file and whether the
        hook is configured at all."""
        err, _body, who = await gate._guard(request)
        if err:
            return err
        state = forecasting._forecast_state()
        wb = {k: v for k, v in (state.get("workbook") or {}).items() if k != "data_b64"}
        led = state.get("ledger") if isinstance(state.get("ledger"), dict) else {}
        return gate._json({"latest": state.get("latest"), "last_error": state.get("last_error"),
                      "runs": state.get("runs", [])[-14:], "workbook": wb,
                      "ledger": {"results": (led.get("results") or [])[-24:],
                                 "open": sorted(led.get("predicted") or {})[-6:]},
                      "hook_configured": bool(forecasting.FORECAST_INGEST_TOKEN),
                      "can_upload": team._team_level(who) >= team.ROLE_LEVELS["admin"]})

    @mcp.custom_route("/api/forecast/workbook", methods=["POST"])
    async def forecast_workbook_upload_route(request: Request):
        """An admin replaces the cash flow workbook. It is a real .xlsx or it is
        refused: the app has no spreadsheet library of its own, but a workbook
        is a zip with xl/workbook.xml in it, and that much can be checked. It
        is kept inside the forecast store, base64, so the one writer writes it
        and the backup carries it; a 70 KB sheet does not need a file of its own."""
        cap = forecasting.FORECAST_MAX_BYTES + 2 * 1024 * 1024   # base64 overhead
        err, _b, who = await gate._guard(request, max_body=cap, body=False)
        if err:
            return err
        if team._team_level(who) < team.ROLE_LEVELS["admin"]:
            return gate._json({"error": "Only an admin can replace the cash flow workbook."}, 403)
        body = await gate._read_json_capped(request, cap=cap)
        if body is None:
            return gate._json({"error": "That file is too large (8 MB cap)."}, 413)
        refused = gate._body_refusal(WorkbookBody, body)
        if refused:
            return refused
        name = str(body.get("name") or "Cash Flow.xlsx")[:120]
        try:
            raw = base64.b64decode(str(body.get("data_b64") or ""), validate=True)
        except (ValueError, TypeError):
            return gate._json({"error": "The upload did not decode."}, 400)
        if len(raw) > forecasting.FORECAST_MAX_BYTES:
            return gate._json({"error": "That file is too large (8 MB cap)."}, 413)
        import io as _io
        import zipfile as _zipfile
        try:
            names = _zipfile.ZipFile(_io.BytesIO(raw)).namelist()
        except _zipfile.BadZipFile:
            names = []
        if "xl/workbook.xml" not in names:
            return gate._json({"error": "That file is not an .xlsx workbook."}, 400)
        state = forecasting._forecast_state()
        meta = {"name": name, "size": len(raw), "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "by": team._team_name(who) or ""}
        state["workbook"] = {**meta, "data_b64": base64.b64encode(raw).decode("ascii")}
        jsonstore._write_json_store(forecasting.FORECAST_PATH, "forecast", state)
        return gate._json({"ok": True, "workbook": meta})
