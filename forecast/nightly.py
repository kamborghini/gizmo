"""The nightly job: `python -m forecast nightly`, run by a second Railway
service on this repo with a cron schedule.

  REACTOR_URL             https://<the app's domain>
  FORECAST_INGEST_TOKEN   the shared secret, the same value Reactor holds
  SHOP                    <store>.myshopify.com
  SHOPIFY_FORECAST_TOKEN  an Admin API access token with read_orders and read_products
  FORECAST_SCENARIO       optional: which scenario feeds the baseline feature
  FORECAST_HISTORY_DAYS   optional, default 900
  FORECAST_HORIZON        optional, default 90
  FORECAST_NBEATS         optional, "1" to train N-BEATS (needs torch in the image)

It fetches the workbook an admin uploaded in the Forecast tab, pulls the
orders and products, runs the pipeline as of yesterday (London), and posts
the payload to Reactor. A failure posts {"error": ...} so the tab says so.
"""
from __future__ import annotations

import json
import logging
import os
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
    missing = [k for k, v in (("REACTOR_URL", base), ("FORECAST_INGEST_TOKEN", token), ("SHOP", shop),
                              ("SHOPIFY_FORECAST_TOKEN", stoken)) if not v]
    if missing:
        log.error("missing: %s", ", ".join(missing))
        return 2
    as_of = (datetime.now(ZoneInfo("Europe/London")) - timedelta(days=1)).date()
    results_url = base + "/hooks/forecast/results"
    try:
        from .cashflow import CashFlowModel
        from .config import Config
        from .ingest import fetch_products, orders_to_rows, run_bulk_orders, to_daily_panel
        from .pipeline import Runner
        with tempfile.TemporaryDirectory() as tmp:
            wb = _fetch_workbook(base + "/hooks/forecast/workbook", token, Path(tmp))
            if wb is None:
                _post(results_url, token, {"as_of": as_of.isoformat(),
                                           "error": "No cash flow workbook has been uploaded in the Forecast tab yet."})
                return 0
            cf = CashFlowModel.from_workbook(wb)
            since = as_of - timedelta(days=int(env.get("FORECAST_HISTORY_DAYS", "900")))
            log.info("pulling orders since %s", since)
            orders = run_bulk_orders(shop, stoken, since)
            products = fetch_products(shop, stoken)
            cfg = Config(as_of=as_of, horizon_days=int(env.get("FORECAST_HORIZON", "90")),
                         use_nbeats=env.get("FORECAST_NBEATS", "0") == "1")
            panel = to_daily_panel(orders_to_rows(orders, cfg, products), as_of)
            if panel.empty:
                raise RuntimeError("no orders came back from Shopify")
            runner = Runner(cfg, panel, cf, Path(tmp) / "out", scenario=env.get("FORECAST_SCENARIO") or None)
            runner.run()
            _post(results_url, token, runner.payload())
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
