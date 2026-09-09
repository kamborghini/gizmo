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
from datetime import datetime, timedelta
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
        from .ingest import (access_token, fetch_products, monthly_cash, orders_to_rows,
                             run_bulk_orders, to_daily_panel)
        from .pipeline import Runner
        from .simple import sanity_forecasts
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
            products = fetch_products(shop, api_token)
            # CatBoost runs up to 1200 rounds a fit and there are forty fits in a
            # run, so it is the long pole by a distance. Off, the run is roughly
            # halved: worth it for a first forecast, or on a small container.
            cfg = Config(as_of=as_of, horizon_days=int(env.get("FORECAST_HORIZON", "90")),
                         use_nbeats=env.get("FORECAST_NBEATS", "0") == "1",
                         use_catboost=env.get("FORECAST_CATBOOST", "1") != "0")
            log.info("models: lightgbm%s%s", "+catboost" if cfg.use_catboost else "",
                     "+nbeats" if cfg.use_nbeats else "")
            panel = to_daily_panel(orders_to_rows(orders, cfg, products), as_of)
            if panel.empty:
                raise RuntimeError("no orders came back from Shopify")
            runner = Runner(cfg, panel, cf, Path(tmp) / "out", scenario=env.get("FORECAST_SCENARIO") or None)
            runner.run()
            if hasattr(signal, "SIGALRM"):
                signal.alarm(0)
            payload = runner.payload()
            # Five plain models on the monthly total, beside the big one. They
            # cost milliseconds, they can be checked by eye, and where they
            # disagree is itself worth reading. A failure here must not lose a
            # run that has already done the expensive part.
            try:
                cash = monthly_cash(orders, as_of)
                payload["sanity"] = sanity_forecasts(cash)
                log.info("sanity: %d complete months, best by backtest: %s",
                         len(cash), (payload["sanity"] or {}).get("best"))
            except Exception as e:
                log.error("sanity models failed: %s", e)
                payload["sanity"] = {"available": False,
                                     "reason": f"{type(e).__name__}: {e}"[:300],
                                     "history": [], "models": []}
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
