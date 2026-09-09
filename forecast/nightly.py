"""The nightly job: `python -m forecast nightly`, run by a second Railway
service on this repo with a cron schedule.

  REACTOR_URL             https://<the app's domain>
  FORECAST_INGEST_TOKEN   the shared secret, the same value Reactor holds
  SHOP                    <store>.myshopify.com
  and ONE Shopify credential, the second preferred because it is the app's own
  and there is then one thing to rotate rather than two:
  SHOPIFY_FORECAST_TOKEN  a static Admin API token with read_all_orders + read_products
  SHOPIFY_CLIENT_ID       Reactor's client id and secret, exchanged for a
  SHOPIFY_CLIENT_SECRET   short-lived token that carries the app's own scopes
  FORECAST_SCENARIO       optional: which scenario feeds the baseline feature
  FORECAST_HISTORY_DAYS   optional, default 900
  FORECAST_HORIZON        optional, default 90
  FORECAST_NBEATS         optional, "1" to train N-BEATS (needs torch in the image)
  FORECAST_CATBOOST       optional, "0" to train LightGBM alone, which roughly
                          halves a run: CatBoost is forty fits of up to 1200 rounds
  FORECAST_MAX_MINUTES    optional, default 120: the whole run's ceiling. Past it
                          the run posts a failure instead of hanging until someone
                          notices a container still going at lunchtime.

It fetches the workbook an admin uploaded in the Forecast tab, pulls the
orders and products, runs the pipeline as of yesterday (London), and posts
the payload to Reactor. A failure posts {"error": ...} so the tab says so.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import tempfile
import traceback
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

log = logging.getLogger("forecast.nightly")


def _post(url: str, token: str, payload: dict) -> None:
    req = urllib.request.Request(url, data=json.dumps(payload, default=str).encode(),
                                 headers={"Content-Type": "application/json", "X-Forecast-Token": token})
    with urllib.request.urlopen(req, timeout=120) as resp:
        resp.read()


def _fetch_workbook(url: str, token: str, into: Path) -> Path | None:
    req = urllib.request.Request(url, headers={"X-Forecast-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            path = into / "Cash Flow.xlsx"
            path.write_bytes(resp.read())
            return path
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def _payload(cfg, cf, sanity, opinions, monthly, cash, alerts, summary, actual_daily, fdaily) -> dict:
    """What the Forecast tab draws, as one JSON document.

    The same shape the tab has always read - as_of, scenarios, monthly, cash,
    alerts, daily - so nothing on the page had to be re-plumbed, plus the five
    models and which three are being quoted. Tens of kilobytes."""
    import numpy as np
    import pandas as pd

    def f(x):
        try:
            v = float(x)
        except (TypeError, ValueError):
            return None
        return None if np.isnan(v) else round(v, 2)

    names = cf.scenario_names if cf else []
    rows = []
    for _, r in monthly.iterrows():
        rows.append({"month": pd.Timestamp(r["month"]).strftime("%Y-%m"), "method": r["method"],
                     "actual_to_date": f(r["actual_to_date"]), "p10": f(r["projected_p10"]),
                     "p50": f(r["projected_p50"]), "p90": f(r["projected_p90"]),
                     "targets": {n: f(r[f"target|{n}"]) for n in names},
                     "gap": {n: f(r[f"gap|{n}"]) for n in names},
                     "gap_pct": {n: f(r[f"gap_pct|{n}"]) for n in names},
                     "verdict": {n: r[f"verdict|{n}"] for n in names},
                     "risk": {n: r[f"risk|{n}"] for n in names}})
    cash_out = {}
    for n, path in cash.items():
        cash_out[n] = [{"month": pd.Timestamp(r["month"]).strftime("%Y-%m"), "gross_sales": f(r["gross_sales"]),
                        "repayment": f(r["repayment"]), "net_cash": f(r["net_cash"]),
                        "working_capital": f(r["working_capital"]), "loan_end": f(r["loan_end"]),
                        "below_buffer": bool(r["below_buffer"]), "negative": bool(r["negative"])}
                       for _, r in path.iterrows()]
    hist = actual_daily.tail(120)
    return {
        "as_of": cfg.as_of.isoformat(), "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenarios": names, "scenario_feature": None,
        "basis": "order total (cash in), the units the plan and Shopify both use",
        "forecast_by": [{"name": m["name"], "note": m.get("note"),
                         "mape": f(m["score"]["mape"]), "bias": f(m["score"]["bias"])} for m in opinions],
        "summary": summary, "monthly": rows,
        "year": {"p50": f(monthly["projected_p50"].sum()) if len(monthly) else None,
                 "targets": {n: f(monthly[f"target|{n}"].sum()) for n in names} if len(monthly) else {}},
        "cash": cash_out, "alerts": alerts, "sanity": sanity,
        "daily": {"history": [{"date": pd.Timestamp(d).strftime("%Y-%m-%d"), "actual": f(v)}
                              for d, v in hist.items()],
                  "forecast": [{"date": pd.Timestamp(r["date"]).strftime("%Y-%m-%d"), "p10": f(r["p10"]),
                                "p50": f(r["p50"]), "p90": f(r["p90"])} for _, r in fdaily.iterrows()]},
    }


def main() -> int:
    env = os.environ
    base = env.get("REACTOR_URL", "").rstrip("/")
    token = env.get("FORECAST_INGEST_TOKEN", "")
    shop, stoken = env.get("SHOP", ""), env.get("SHOPIFY_FORECAST_TOKEN", "")
    cid, csec = env.get("SHOPIFY_CLIENT_ID", ""), env.get("SHOPIFY_CLIENT_SECRET", "")
    missing = [k for k, v in (("REACTOR_URL", base), ("FORECAST_INGEST_TOKEN", token),
                              ("SHOP", shop)) if not v]
    # Either credential shape will do, so neither name alone is missing.
    if not stoken and not (cid and csec):
        missing.append("SHOPIFY_FORECAST_TOKEN, or SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET")
    if missing:
        log.error("missing: %s", ", ".join(missing))
        return 2
    as_of = (datetime.now(ZoneInfo("Europe/London")) - timedelta(days=1)).date()
    results_url = base + "/hooks/forecast/results"
    # A nightly job with no ceiling is how a container is still running at
    # lunchtime, looking identical to one that is merely slow. The alarm raises
    # in the main thread, so the failure travels the ordinary path and reaches
    # the tab. Cancelled before the result is posted, so a post is never cut.
    budget_min = int(env.get("FORECAST_MAX_MINUTES", "120"))
    if budget_min > 0 and hasattr(signal, "SIGALRM"):
        def _out_of_time(_sig, _frame):
            raise TimeoutError(f"the run passed its {budget_min} minute ceiling "
                               "(raise FORECAST_MAX_MINUTES, or ask for less history)")
        signal.signal(signal.SIGALRM, _out_of_time)
        signal.alarm(budget_min * 60)
        log.info("ceiling: %d minutes", budget_min)
    from .cpu import cpu_budget
    log.info("cpu budget: %d thread(s)", cpu_budget())
    try:
        from .cashflow import CashFlowModel
        from .config import Config
        from .ingest import (access_token, daily_cash, fetch_products, monthly_cash,
                             orders_to_rows, run_bulk_orders, to_daily_panel)
        from .simple import daily_frame, pick_opinions, sanity_forecasts
        from .variance import VarianceEngine
        with tempfile.TemporaryDirectory() as tmp:
            wb = _fetch_workbook(base + "/hooks/forecast/workbook", token, Path(tmp))
            if wb is None:
                _post(results_url, token, {"as_of": as_of.isoformat(),
                                           "error": "No cash flow workbook has been uploaded in the Forecast tab yet."})
                return 0
            cf = CashFlowModel.from_workbook(wb)
            # Inside the try: a refused grant is a run that failed, and the tab
            # should say so rather than the service exiting quietly.
            api_token = access_token(shop, stoken, cid, csec)
            since = as_of - timedelta(days=int(env.get("FORECAST_HISTORY_DAYS", "900")))
            log.info("pulling orders since %s", since)
            orders = run_bulk_orders(shop, api_token, since)
            cfg = Config(as_of=as_of, horizon_days=int(env.get("FORECAST_HORIZON", "90")))

            # THE FORECAST. Five plain models on the monthly total, ranked by
            # what each scored on this shop's own history; the best one drives
            # the month table, the cash path and the alerts, and the next two
            # stand beside it as second and third opinions.
            #
            # The per-product daily model that used to do this job is off by
            # default (FORECAST_M5=1 brings it back). It forecast October -
            # the best month of the year, over 60k twice - at 16,436, because
            # it predicts every product on every day and adds them up, and
            # half this revenue is quoted projector work where one order is a
            # tenth of the month.
            months = monthly_cash(orders, as_of)
            actual_daily = daily_cash(orders, as_of)
            if months.empty:
                raise RuntimeError("no orders came back from Shopify")
            sanity = sanity_forecasts(months, horizon=int(env.get("FORECAST_MONTHS", "6")))
            if not sanity.get("available"):
                raise RuntimeError(sanity.get("reason") or "not enough history to forecast")
            opinions = pick_opinions(sanity)
            primary = opinions[0]
            log.info("forecast: %s (typical error %.0f%%, bias %+.0f%%); second %s, third %s",
                     primary["name"], primary["score"]["mape"] * 100, primary["score"]["bias"] * 100,
                     opinions[1]["name"] if len(opinions) > 1 else "-",
                     opinions[2]["name"] if len(opinions) > 2 else "-")

            eng = VarianceEngine(cfg, cf)
            # The month is spread over its days by the shop's OWN weekday and
            # intra-month shape rather than evenly, so the daily line looks like
            # trading rather than a staircase. It still sums back to the month
            # exactly, so nothing about the monthly figure changes.
            from .cashflow import DayProfile
            fdaily = daily_frame(primary, as_of, DayProfile.fit(actual_daily))
            monthly_view = eng.monthly_view(actual_daily, fdaily)
            cash_view = {n: eng.cash_view(monthly_view, n) for n in cf.scenario_names if n in cf.flows}
            alerts = eng.alerts(monthly_view, cash_view)
            payload = _payload(cfg, cf, sanity, opinions, monthly_view, cash_view, alerts,
                               eng.summary(monthly_view, cash_view, alerts), actual_daily, fdaily)

            if env.get("FORECAST_M5", "0") == "1":
                # Kept, not deleted: it is a lot of careful work and it may yet
                # earn its place on a business with denser per-product history.
                from .pipeline import Runner
                # CatBoost runs up to 1200 rounds a fit and there are forty fits
                # in a run, so it is the long pole by a distance when this path
                # is switched back on.
                m5cfg = Config(as_of=as_of, horizon_days=cfg.horizon_days,
                               use_nbeats=env.get("FORECAST_NBEATS", "0") == "1",
                               use_catboost=env.get("FORECAST_CATBOOST", "1") != "0")
                log.info("m5 models: lightgbm%s%s", "+catboost" if m5cfg.use_catboost else "",
                         "+nbeats" if m5cfg.use_nbeats else "")
                products = fetch_products(shop, api_token)
                panel = to_daily_panel(orders_to_rows(orders, m5cfg, products), as_of)
                runner = Runner(m5cfg, panel, cf, Path(tmp) / "out",
                                scenario=env.get("FORECAST_SCENARIO") or None)
                runner.run()
                payload["m5"] = runner.payload()

            if hasattr(signal, "SIGALRM"):
                signal.alarm(0)
            _post(results_url, token, payload)
            log.info("posted the run as of %s", as_of)
            return 0
    except Exception as e:
        log.error("nightly run failed: %s\n%s", e, traceback.format_exc())
        try:
            _post(results_url, token, {"as_of": as_of.isoformat(), "error": f"{type(e).__name__}: {e}"[:1500]})
        except Exception as e2:  # pragma: no cover
            log.error("could not even post the failure: %s", e2)
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sys.exit(main())
