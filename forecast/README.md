# Reactor forecasting

Multi-level sales forecasting for the store, benchmarked every day against
Shopify actuals and against the manual cash flow model. It is a batch package
that lives beside the app and never runs inside it: its own dependencies, its
own environment, a command line, files out.

## What it answers

Three questions, monthly and to the pound:

1. What will we sell, by variant, product, category, customer segment and in
   total, for the next 90 days, with a band we have earned in backtests.
2. How does that compare with what Shopify says we have actually sold this
   month so far, and with every scenario in `Cash Flow.xlsx`.
3. What does that do to the cash: working capital and the Shopify Capital
   balance, month by month, through the scenario's own mechanics.

The target is the workbook's own line, **Net Sales** (gross minus discounts
and returns, before shipping and taxes). Units are carried alongside so a
price move and a volume move are told apart.

## Architecture

```
  Shopify                                   Cash Flow.xlsx
  orders JSON / admin CSV / GraphQL bulk    Assumptions | actual years | 3 scenarios | IN OUT flows
        |                                          |
        v                                          v
  ingest.to_daily_panel                    cashflow.CashFlowModel
  variant x segment x day, zero-filled     monthly actuals + scenarios + cash mechanics
        |                                          |
        |                    DayProfile (weekday + intra-month shape from history)
        |                                          |
        v                                          v
  features.FeatureBuilder  <------- daily baseline: month target spread over days
  lags >= horizon, rolling, EWMA, zero share, price, discount,
  target + frequency encodings, UK calendar, cash-flow share and baseline, age
        |
        v
  backtest: 5 expanding 28-day folds x horizon buckets (1-7, 8-14, 15-28)
     LightGBM (Tweedie)  CatBoost (Tweedie)  SeasonalLevel      N-BEATS (product, category,
     bottom grain        bottom grain        bottom grain       segment, total)
        |                    |                    |                  |
        +---- out-of-fold predictions, WRMSSE / MAE / bias per level ----+
        |
        v
  ensemble: NNLS blend weights per level (sum to one)   intervals: OOF quantile bands per level x bucket
        |                                                residuals: for MinT
        v
  forecast: refit on all history, blend, cold-start lean for young SKUs
        |
        v
  reconcile.Hierarchy: MinT-shrink over the grouped hierarchy
     total <- category <- product <- variant <- (variant x segment) -> segment -> total
        |
        v
  variance.VarianceEngine
     per month: actual | actual-to-date + forecast | forecast | extrapolated
     vs each scenario: gap, verdict (on track / underrun / overrun), risk (secure / watch / high)
     cash path per scenario: working capital, loan balance, buffer alerts
        |
        v
  out/: forecast_daily.csv, forecast_monthly.csv, backtest_metrics.csv, blend_weights.json,
        feature_importance.csv, variance_monthly.csv, cash_path_<scenario>.csv, alerts.json, summary.txt
```

### Why these choices

* **Direct multi-horizon GBDTs.** One model per horizon bucket, every
  history feature shifted by the bucket's longest horizon. A row can never
  see its own future, and the backtest measures exactly what production
  will do. This is the M5 winners' recipe; recursive forecasting compounds
  its own errors over 90 days.
* **Tweedie loss.** Bottom-level demand is mostly zeros with a heavy tail.
  Tweedie is the natural likelihood for that and never predicts below zero.
* **CatBoost beside LightGBM.** Different treatment of the high-cardinality
  keys (ordered target statistics vs. native categorical splits), so the
  two disagree in useful ways and the blend gains.
* **N-BEATS on the aggregate levels only.** Dense series have a shape a
  network can learn; the bottom grain does not. MinT is what lets a network
  forecast at the product level and a GBDT at the variant level agree.
* **Blend weights from out-of-fold predictions, per level.** A model earns
  weight where it was right on days it had not seen. The weights are convex
  (non-negative, sum to one), so the blend never rescales a model.
* **MinT-shrink reconciliation.** Every level is forecast, then the whole
  vector is projected onto the coherent subspace weighted by the inverse
  residual covariance. SKU forecasts sum to the top line the cash flow model
  is measured on, and the top line borrows accuracy from the levels below.
* **Empirical intervals.** P10 and P90 are the backtest's own error
  quantiles per level and horizon bucket, applied multiplicatively. The
  band is only as wide as the model's record says it must be.
* **The workbook as a feature and as a benchmark.** The month's target,
  spread over days by the store's own weekday and intra-month shape, is a
  feature (`cf_baseline`, `level_vs_baseline`) and the line the forecast is
  compared with. The model learns how the store tracks its plan; it is not
  anchored to it.

## Installing

```bash
python3 -m venv ~/.venvs/reactor-forecast
~/.venvs/reactor-forecast/bin/pip install -r forecast/requirements.txt
# macOS only, for LightGBM:
brew install libomp
```

CatBoost and PyTorch are optional: drop them from the requirements and pass
`--no-catboost` / `--no-nbeats`.

## Running

Pull the orders. The bulk GraphQL puller in `forecast/ingest.py`
(`run_bulk_orders`) needs a shop domain and an Admin API access token with
`read_orders`; keep the token in the environment, never in a file:

```python
import json, os
from datetime import date
from forecast.ingest import run_bulk_orders
orders = run_bulk_orders(os.environ["SHOP"], os.environ["SHOPIFY_ADMIN_TOKEN"], date(2024, 5, 1))
json.dump({"orders": orders}, open("orders.json", "w"))
```

Or export Orders from the admin as CSV and pass `--csv export.csv` instead.

Then:

```bash
python -m forecast run --orders orders.json --products products.json \
    --cashflow "Cash Flow.xlsx" --as-of 2026-09-08 --out out/ --scenario "Algorithm 3"
```

`products.json` is `{product_id: {"product_type": ...}}` and gives the
category; without it the category is inferred from the title. `--scenario`
picks which scenario feeds the baseline feature; every scenario is reported
against regardless.

`summary.txt` is the report. `alerts.json` is what an automated run should
post. The CSVs are for the spreadsheet.

A synthetic store for a dry run:

```bash
python -m forecast synth --cashflow "Cash Flow.xlsx" --as-of 2026-09-08 --out synthetic/
python -m forecast run --orders synthetic/orders.json --products synthetic/products.json \
    --cashflow "Cash Flow.xlsx" --as-of 2026-09-08 --out out/
```

Tests: `python tests/test_forecast.py` in the forecasting environment (it
skips itself where pandas is absent, so the app's CI does not run it).

## Operational playbook

### Reading the backtest

`backtest_metrics.csv` has one row per model per level, plus `blend` and
`blend+mint`. Read it top down:

* `wrmsse` under 1 at the total level means the model beats a naive
  one-step forecast scaled to the series; the blend should be the lowest
  line, and `blend+mint` should not be worse than `blend` at the top.
* `bias_pct` at the total level is the tracking bias: positive means the
  model runs hot. Anything past a few percent for two runs in a row means
  the store has shifted and the retrain window should be shortened.
* `tracking_signal` past 4 in absolute value is the classic "the forecast
  is consistently on one side" flag.

`blend_weights.json` says who earned the forecast at each level. A model
whose weight is zero everywhere can be dropped from the run.

### New SKU cold start

A variant younger than `cold_start_days` (56) has no lags worth the name.
Three things cover it:

1. `is_new` and `age_days` are features, so once a few launches are in the
   history the GBDTs learn the launch ramp themselves.
2. `coldstart.apply_cold_start` blends the model's bottom forecast with a
   prior: the mean daily net sales of an established series in the same
   category and segment over the last eight weeks, scaled by the square
   root of the variant's price relative to its category median. The lean
   fades linearly with age, so a series is fully its own at 56 days.
3. MinT reconciles the young series with the levels above it, where the
   history is dense, so a wrong prior is pulled toward the category's
   reality rather than compounding.

When a launch is planned, add the variant to the panel with zero rows from
its launch date (the ingestion does this the first day it sells) and the
prior takes over automatically. To seed a launch curve from a comparable
product, put that product's first eight weeks under the new variant's id
in a small CSV and concatenate it before `to_daily_panel`; remove it once
the real history passes 56 days.

### Batch comparison against the cash flow milestones

Nightly, after Shopify's day closes (03:00 UK is safe):

```bash
python -m forecast run --orders orders.json --products products.json \
    --cashflow "Cash Flow.xlsx" --as-of "$(date -v-1d +%F)" --out "out/$(date +%F)"
```

* `variance_monthly.csv`: the open month's `projected_p50` is actual-to-date
  plus the forecast for the rest; `verdict|<scenario>` and `risk|<scenario>`
  are the calls. `high` risk means even P90 misses the target.
* `cash_path_<scenario>.csv`: `below_buffer` and `negative` mark the months
  to act on; the repayment is the effective rate on gross (18% x the Shopify
  share) and stops at the loan.
* `alerts.json` is the payload for whatever posts the alert (the app's
  alert email or a Slack hook); post only `kind: sales` with `risk: high`
  and every `kind: cash` unless the team wants the noise.

Retrain cadence: the run refits every model each night on all history,
which is cheap at this scale. Re-read the weights and metrics weekly. When
the workbook changes (a scenario is revised), the next run picks it up; no
code changes.

### What to hand the model that it does not have yet

Two signals the store has and the panel does not yet carry, in order of
value: marketing spend by day (the workbook budgets it monthly; a daily
line joined on `date` in `FeatureBuilder` is a five-line change) and
stock-outs (a day a variant could not sell is not a zero-demand day; a
`stockout` flag lets the model ignore it). Both go in as known covariates.

## Layout

```
forecast/
  config.py      every knob: target, lags, buckets, folds, thresholds, tag maps
  calendar.py    UK bank holidays, Black Friday, paydays, year-end lull
  cashflow.py    the workbook reader, DayProfile, daily targets, cash mechanics
  ingest.py      JSON / CSV / GraphQL bulk adapters, the daily panel
  features.py    the leak-free feature builder and the encodings
  models/        base, baseline, gbdt (LightGBM, CatBoost), nbeats, ensemble
  coldstart.py   the category prior for young series
  backtest.py    expanding folds, WRMSSE / MAE / bias, interval bands
  reconcile.py   the grouped hierarchy, bottom-up, MinT-shrink
  variance.py    the month-by-month comparison, cash path, alerts, summary
  pipeline.py    the runner and the CLI
  synth.py       a synthetic store shaped by the workbook
tests/test_forecast.py
```
