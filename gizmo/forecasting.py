"""The forecast's hooks, the app's side of the nightly forecasting service: its
store, the hook token, and the figure and ledger it keeps from each run.
Moved out of copilot.py (stage 4 of the 14 October audit); its routes are in
gizmo/routes/forecasting.py. Named apart from the forecast/ service package.
Read as `forecasting.NAME`.
"""
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional
from starlette.requests import Request
from gizmo import store as jsonstore

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


FORECAST_PATH      = os.environ.get("FORECAST_PATH", "/data/forecast.json")  # the nightly forecasting service's latest run, and the cash flow workbook an admin uploaded (base64), in one store
FORECAST_INGEST_TOKEN = os.environ.get("FORECAST_INGEST_TOKEN", "").strip()  # shared secret the nightly forecasting service presents to /hooks/forecast/*; empty switches the hooks off
FORECAST_MAX_BYTES = 8 * 1024 * 1024

# ---- values add_routes used to build every time it ran ---------------------
# These were plain assignments inside add_routes, which made them invisible to
# every test and to every other function in the file: a constant nothing can
# import is a constant nobody can check, and a cache nothing can reach is a
# cache no test can clear between cases. add_routes is called exactly once
# (server.py), so hoisting them changes nothing at runtime and makes them
# reachable as copilot.<name>.
FORECAST_LEDGER_MONTHS = 36
FORECAST_LEDGER_SOURCES = 40

# ---- Forecast: the nightly forecasting service and the tab that reads it ----
def _forecast_state() -> dict:
    d = jsonstore._load_json_store(FORECAST_PATH, "forecast", None)
    return d if isinstance(d, dict) else {}

def _forecast_token_ok(request: Request) -> bool:
    return gate._secret_ok(str(request.headers.get("x-forecast-token") or ""), FORECAST_INGEST_TOKEN)

# The run date the service posts: date.isoformat(), or a datetime's.
_FORECAST_AS_OF_RE = re.compile(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})?)?")


def _forecast_figure(x) -> Optional[float]:
    """A figure the run history keeps: a finite number to the penny, or None."""
    import math
    if isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, 2) if math.isfinite(v) else None

# Months scored before the ledger kept the source in use. September 2026 was
# forecast by "Last year, adjusted for this year" (its run of 9 September was
# rebuilt from the forecast's own code and matched the notes of that day to
# the pound: 0.65 x last September, likely range +/-28.7%). Its figure is the
# source's own first word, already in the ledger; only the label is supplied.
FORECAST_IN_USE_BACKFILL = {
    "2026-09": {"source": "Last year, adjusted for this year", "seen_through": "2026-08", "band": 0.287},
}


def _forecast_ledger(state: dict, body: dict) -> dict:
    """The standing record of who was right, kept across runs.

    The backtest each run computes is retrospective: it refits a model to
    old months and marks it, which is useful but forgiving, because the
    model is being asked about a period the code already knows the shape
    of. This is the other kind, and the honest one: what each source
    ACTUALLY said about September, written down in September while
    September was still unknown, then marked when September closed.

    Predictions are recorded once and never revised. A later run may have
    a better opinion about a month, but overwriting the earlier one would
    turn a forecast into a hindcast and every source would look excellent.

    `in_use` is the other half: what the page's numbers came from. For each
    month it keeps the source in use, its figure and likely range and what the
    page showed, from the first run that had seen every whole month before it
    (seen_through = the month before). Every month is then judged on a
    forecast of the same age, made without any of its own whole-month data,
    and a director can see what they were actually told. `predicted` keeps
    each source's first word, whenever that was, for the ranking."""
    import math
    led = state.get("ledger") if isinstance(state.get("ledger"), dict) else {}
    predicted = led.get("predicted") if isinstance(led.get("predicted"), dict) else {}
    in_use = led.get("in_use") if isinstance(led.get("in_use"), dict) else {}
    results = led.get("results") if isinstance(led.get("results"), list) else []

    def _num(x):
        try:
            v = float(x)
        except (TypeError, ValueError):
            return None
        return round(v, 2) if math.isfinite(v) else None

    seen = str(body.get("seen_through") or "")[:7]
    iu = body.get("in_use") if isinstance(body.get("in_use"), dict) else {}
    if re.fullmatch(r"\d{4}-\d{2}", seen) and isinstance(iu.get("months"), dict):
        y, mo = int(seen[:4]), int(seen[5:7])
        nxt = f"{y + (mo == 12)}-{(mo % 12) + 1:02d}"
        rec = iu["months"].get(nxt)
        if nxt not in in_use and isinstance(rec, dict) and _num(rec.get("value")) is not None:
            in_use[nxt] = {"source": str(iu.get("source") or "")[:80], "value": _num(rec.get("value")),
                           "p10": _num(rec.get("p10")), "p90": _num(rec.get("p90")),
                           "shown": _num(rec.get("shown")), "made": body.get("as_of"),
                           "seen_through": seen}

    preds = body.get("predictions")
    if isinstance(preds, dict):
        for month, by_source in list(preds.items())[:24]:
            if not isinstance(month, str) or not isinstance(by_source, dict):
                continue
            month = month[:7]
            slot = predicted.setdefault(month, {})
            for name, value in list(by_source.items())[:FORECAST_LEDGER_SOURCES]:
                try:
                    v = float(value)
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(v) or name in slot:
                    continue                      # first word only: never revised
                slot[str(name)[:80]] = {"value": round(v, 2), "made": body.get("as_of")}

    actuals = body.get("actuals")
    scored = {r.get("month") for r in results if isinstance(r, dict)}
    if isinstance(actuals, dict):
        for month, value in list(actuals.items())[:24]:
            month = str(month)[:7]
            if month in scored or month not in predicted:
                continue
            try:
                actual = float(value)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(actual) or actual <= 0:
                continue
            by = {}
            for name, rec in predicted[month].items():
                v = rec.get("value")
                if not isinstance(v, (int, float)):
                    continue
                by[name] = {"predicted": v, "error": round((v - actual) / actual, 4),
                            "made": rec.get("made")}
            if not by:
                continue
            winner = min(by.items(), key=lambda kv: abs(kv[1]["error"]))
            entry = {"month": month, "actual": round(actual, 2), "by_source": by,
                     "winner": winner[0], "winner_error": winner[1]["error"],
                     "closed_at": datetime.now(timezone.utc).isoformat()}
            u = in_use.get(month)
            if isinstance(u, dict) and isinstance(u.get("value"), (int, float)):
                lo, hi = u.get("p10"), u.get("p90")
                entry["in_use"] = dict(u, error=round((u["value"] - actual) / actual, 4),
                                       inside=(bool(lo <= actual <= hi)
                                               if isinstance(lo, (int, float)) and isinstance(hi, (int, float))
                                               else None))
            results.append(entry)
            scored.add(month)

    for r in results:
        b = FORECAST_IN_USE_BACKFILL.get(r.get("month")) if isinstance(r, dict) else None
        src = ((r.get("by_source") or {}).get(b["source"]) if b else None) or {}
        if b and "in_use" not in r and isinstance(src.get("predicted"), (int, float)) and r.get("actual"):
            v, a = float(src["predicted"]), float(r["actual"])
            lo, hi = round(max(0.0, v * (1 - b["band"])), 2), round(v * (1 + b["band"]), 2)
            r["in_use"] = {"source": b["source"], "value": round(v, 2), "p10": lo, "p90": hi,
                           "shown": None, "made": src.get("made"), "seen_through": b["seen_through"],
                           "error": round((v - a) / a, 4), "inside": bool(lo <= a <= hi),
                           "reconstructed": True}

    results.sort(key=lambda r: r.get("month") or "")
    results = results[-FORECAST_LEDGER_MONTHS:]
    keep = {r["month"] for r in results}
    # A month still ahead keeps its predictions; one long closed does not.
    predicted = {m: v for m, v in predicted.items()
                 if m in keep or m >= min(keep, default=m)}
    in_use = {m: v for m, v in in_use.items() if m in keep or m >= min(keep, default=m)}
    return {"predicted": predicted, "in_use": in_use, "results": results}


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as sibling.NAME, never a copied name.
from gizmo import gate  # noqa: E402
