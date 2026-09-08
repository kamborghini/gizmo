"""The pipeline, end to end:

  Shopify actuals ----> daily panel (variant x segment x day)
  Cash Flow.xlsx  ----> monthly actuals + scenarios ----> daily baseline (DayProfile)
                                     |
        features at each horizon bucket (leak-free shifts)
                                     |
        backtest: 5 expanding folds x buckets x models -> OOF preds, WRMSSE,
                  NNLS blend weights per level, interval bands, MinT residuals
                                     |
        forecast: refit on all history, blend, cold-start lean, MinT reconcile,
                  intervals -> every level, every day of the horizon
                                     |
        variance: month by month vs Shopify actuals and every scenario,
                  cash path through the scenario's mechanics, alerts

python -m forecast run --orders orders.json --products products.json \
    --cashflow "Cash Flow.xlsx" --as-of 2026-09-08 --out out/
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .backtest import IntervalModel, expanding_folds, level_metrics
from .cashflow import CashFlowModel, DayProfile, daily_from_monthly, month_start
from .coldstart import apply_cold_start
from .config import Config
from .features import CATEGORICALS, Encodings, FeatureBuilder, extend_for_forecast
from .ingest import KEY, read_orders_json, read_shopify_export_csv, series_keys, to_daily_panel
from .models import (CatBoostForecaster, LightGBMForecaster, SeasonalLevel, blend, blend_weights,
                     gbdt_available, nbeats_available)
from .reconcile import Hierarchy
from .variance import VarianceEngine

log = logging.getLogger("forecast")
AGG_LEVELS = ("total", "category", "segment", "product")
CAT_COLS = ["cat_" + c for c in CATEGORICALS]


def bucket_of(h: int, buckets) -> Optional[int]:
    for lo, hi in buckets:
        if lo <= h <= hi:
            return hi
    return None


class Runner:
    def __init__(self, cfg: Config, panel: pd.DataFrame, cashflow: Optional[CashFlowModel], out_dir: Path,
                 scenario: Optional[str] = None):
        self.cfg, self.panel, self.cf, self.out = cfg, panel, cashflow, Path(out_dir)
        self.out.mkdir(parents=True, exist_ok=True)
        self.keys = series_keys(panel)
        self.hier = Hierarchy.from_keys(self.keys)
        self.pos = {b: i for i, b in enumerate(self.hier.bottom)}
        self.total_daily = panel.groupby("date")[cfg.target].sum()
        self.profile = DayProfile.fit(self.total_daily)
        self.scenario = scenario or (cashflow.scenario_names[0] if cashflow and cashflow.scenario_names else None)
        self.daily_target = self._daily_target()
        self.builder = FeatureBuilder(cfg, self.daily_target)
        self.weights: Dict[str, Dict[str, float]] = {}
        self.intervals = IntervalModel(cfg.interval_quantiles)
        self.residuals: Optional[np.ndarray] = None
        self.metrics: Optional[pd.DataFrame] = None
        self.importance: Optional[pd.Series] = None
        self._feature_cache: Dict[Tuple[str, int], pd.DataFrame] = {}

    # ------------------------------------------------------------------ setup
    def _daily_target(self) -> Optional[pd.DataFrame]:
        """Monthly figures for every month the panel or the horizon touches:
        the workbook's actual where it has one, the store's own total before
        that, the chosen scenario after. Spread over days by the profile."""
        hist_m = self.total_daily.groupby(self.total_daily.index.to_period("M")).sum()
        hist_m.index = hist_m.index.to_timestamp()
        end = pd.Timestamp(self.cfg.as_of) + pd.Timedelta(days=self.cfg.horizon_days + 31)
        months = pd.date_range(month_start(self.total_daily.index.min()), month_start(end), freq="MS")
        rows = []
        act = self.cf.actuals.set_index("month")["net_sales"] if self.cf is not None else pd.Series(dtype=float)
        sc = (self.cf.scenarios[self.scenario].set_index("month")["net_sales"]
              if self.cf is not None and self.scenario in (self.cf.scenarios if self.cf else {}) else pd.Series(dtype=float))
        for m in months:
            if m in act.index:
                v = float(act[m])
            elif m in sc.index:
                v = float(sc[m])
            elif m in hist_m.index:
                v = float(hist_m[m])
            else:
                v = float(hist_m.tail(12).mean()) if len(hist_m) else 0.0
            rows.append({"month": m, "net_sales": v})
        return daily_from_monthly(pd.DataFrame(rows), self.profile)

    # ------------------------------------------------------------------ matrices
    def _bottom_matrix(self, df: pd.DataFrame, dates: pd.DatetimeIndex, col: str) -> np.ndarray:
        M = np.zeros((len(dates), self.hier.n_bottom))
        di = {d: i for i, d in enumerate(dates)}
        d = df[df["date"].isin(dates)]
        rows = d["date"].map(di).values
        cols = [self.pos[(str(v), str(s))] for v, s in zip(d["variant_id"], d["segment"])]
        np.add.at(M, (rows, cols), d[col].fillna(0).values)
        return M

    def _history_rows(self, upto: pd.Timestamp) -> Tuple[pd.DatetimeIndex, np.ndarray]:
        dates = pd.date_range(self.panel["date"].min(), upto, freq="D")
        return dates, self.hier.aggregate(self._bottom_matrix(self.panel[self.panel["date"] <= upto], dates, self.cfg.target))

    # ------------------------------------------------------------------ features
    def _features(self, panel: pd.DataFrame, shift: int, train_end: pd.Timestamp) -> Tuple[pd.DataFrame, List[str]]:
        feats = self.builder.build(panel, shift)
        train_rows = feats[(feats["date"] <= train_end) & feats[self.cfg.target].notna()]
        enc = Encodings.fit(train_rows, self.cfg.target)
        feats = enc.apply(feats)
        return feats, self.builder.feature_columns(feats)

    def _fit_models(self, tr: pd.DataFrame, es: pd.DataFrame, cols: List[str]) -> Dict[str, object]:
        # Refunds net off the actuals (and the scorecard) but a demand model
        # learns from what sold: Tweedie needs a non-negative label.
        y_tr, y_es = tr[self.cfg.target].clip(lower=0), es[self.cfg.target].clip(lower=0)
        models: Dict[str, object] = {"seasonal_level": SeasonalLevel().fit(tr[cols], y_tr, CAT_COLS)}
        avail = gbdt_available()
        if self.cfg.use_lightgbm and avail["lightgbm"]:
            models["lightgbm"] = LightGBMForecaster(seed=self.cfg.seed).fit(tr[cols], y_tr, CAT_COLS, valid=(es[cols], y_es))
        if self.cfg.use_catboost and avail["catboost"]:
            models["catboost"] = CatBoostForecaster(seed=self.cfg.seed).fit(tr[cols], y_tr, CAT_COLS, valid=(es[cols], y_es))
        return models

    @staticmethod
    def _split_es(train: pd.DataFrame, train_end: pd.Timestamp, days: int = 28):
        cut = train_end - pd.Timedelta(days=days)
        return train[train["date"] <= cut], train[train["date"] > cut]

    def _nbeats(self, upto: pd.Timestamp, horizon: int) -> Optional[Tuple[List[int], np.ndarray]]:
        if not (self.cfg.use_nbeats and nbeats_available()):
            return None
        dates, hist = self._history_rows(upto)
        idx = [r for lvl in AGG_LEVELS for r in self.hier.levels.get(lvl, [])]
        Y = hist[:, idx]
        if Y.shape[0] < 56 + horizon + 14:
            return None
        try:
            from .models.nbeats import run_isolated
            return idx, run_isolated(Y, lookback=56, horizon=horizon, epochs=25, seed=self.cfg.seed)   # (n_idx, horizon)
        except Exception as e:           # pragma: no cover - torch runtime issues
            log.warning("nbeats skipped: %s", e)
            return None

    # ------------------------------------------------------------------ backtest
    def backtest(self) -> pd.DataFrame:
        cfg, y = self.cfg, self.cfg.target
        folds = expanding_folds(cfg.as_of, cfg.cv_folds, cfg.cv_window_days)
        buckets = cfg.buckets_for(cfg.cv_window_days)
        oof: List[pd.DataFrame] = []
        nb_fold: Dict[int, Tuple[List[int], np.ndarray]] = {}
        for f in folds:
            t0 = time.time()
            sub = self.panel[self.panel["date"] <= f.valid_end]
            for lo, hi in buckets:
                feats, cols = self._features(sub, hi, f.train_end)
                train = feats[(feats["date"] <= f.train_end) & feats["roll_mean_28"].notna()]
                tr, es = self._split_es(train, f.train_end)
                h = (feats["date"] - f.train_end).dt.days
                valid = feats[(h >= lo) & (h <= hi) & (feats["date"] <= f.valid_end)]
                models = self._fit_models(tr, es, cols)
                for name, m in models.items():
                    oof.append(pd.DataFrame({"date": valid["date"].values, "variant_id": valid["variant_id"].values,
                                             "segment": valid["segment"].values, "model": name, "fold": f.k,
                                             "h": h[valid.index].values, "pred": m.predict(valid[cols])}))
                if name == "lightgbm" or "lightgbm" in models:
                    self.importance = models["lightgbm"].importance()
            nb = self._nbeats(f.train_end, cfg.cv_window_days)
            if nb is not None:
                nb_fold[f.k] = nb
            log.info("fold %d trained (%.0fs): train to %s, valid %s..%s", f.k, time.time() - t0,
                     f.train_end.date(), f.valid_start.date(), f.valid_end.date())
        oof_df = pd.concat(oof, ignore_index=True)
        model_names = sorted(oof_df["model"].unique())
        # per fold: actual and per-model matrices over all rows
        actual_all, base_all, per_model_all, nb_all, hs = [], [], {n: [] for n in model_names}, [], []
        interval_rows = []
        for f in folds:
            dates = pd.date_range(f.valid_start, f.valid_end, freq="D")
            actual = self.hier.aggregate(self._bottom_matrix(self.panel, dates, y))
            per_model = {n: self.hier.aggregate(self._bottom_matrix(oof_df[(oof_df["fold"] == f.k) & (oof_df["model"] == n)], dates, "pred"))
                         for n in model_names}
            nbm = np.full_like(actual, np.nan)
            if f.k in nb_fold:
                idx, pred = nb_fold[f.k]
                nbm[:, idx] = pred[:, :len(dates)].T
            actual_all.append(actual); per_model_all = {n: per_model_all[n] + [per_model[n]] for n in model_names}
            nb_all.append(nbm); hs.append(np.arange(1, len(dates) + 1))
        A = np.vstack(actual_all); NB = np.vstack(nb_all); H = np.concatenate(hs)
        PM = {n: np.vstack(per_model_all[n]) for n in model_names}
        # blend weights per level from OOF
        self.weights = {}
        base = np.zeros_like(A)
        for lvl, idx in self.hier.levels.items():
            cands = {n: PM[n][:, idx].ravel() for n in model_names}
            if lvl in AGG_LEVELS and not np.isnan(NB[:, idx]).all():
                cands["nbeats"] = NB[:, idx].ravel()
            w = blend_weights(cands, A[:, idx].ravel())
            self.weights[lvl] = w
            base[:, idx] = blend({n: (PM[n][:, idx] if n != "nbeats" else np.nan_to_num(NB[:, idx])) for n in w}, w)
        self.residuals = A - base
        # metrics: each model bottom-up, the blend, and the reconciled blend
        _, train_hist = self._history_rows(folds[0].train_end)
        rows = []
        for n in model_names:
            m = level_metrics(A, PM[n], train_hist, self.hier); m.insert(0, "model", n); rows.append(m)
        m = level_metrics(A, base, train_hist, self.hier); m.insert(0, "model", "blend"); rows.append(m)
        rec = self.hier.mint(base, self.residuals)
        m = level_metrics(A, rec, train_hist, self.hier); m.insert(0, "model", "blend+mint"); rows.append(m)
        self.metrics = pd.concat(rows, ignore_index=True)
        # intervals from the blend, by level and bucket
        for lvl, idx in self.hier.levels.items():
            for r in idx:
                interval_rows.append(pd.DataFrame({"level": lvl, "bucket": [bucket_of(int(h), buckets) for h in H],
                                                   "actual": A[:, r], "pred": base[:, r]}))
        self.intervals.fit(pd.concat(interval_rows, ignore_index=True))
        return self.metrics

    # ------------------------------------------------------------------ forecast
    def forecast(self) -> pd.DataFrame:
        cfg, y = self.cfg, self.cfg.target
        as_of = pd.Timestamp(cfg.as_of)
        ext = extend_for_forecast(self.panel, cfg.as_of, cfg.horizon_days, cfg)
        buckets = cfg.buckets_for(cfg.horizon_days)
        preds: List[pd.DataFrame] = []
        for lo, hi in buckets:
            feats, cols = self._features(ext, hi, as_of)
            train = feats[(feats["date"] <= as_of) & feats[y].notna() & feats["roll_mean_28"].notna()]
            tr, es = self._split_es(train, as_of)
            h = (feats["date"] - as_of).dt.days
            fut = feats[(h >= lo) & (h <= hi)]
            models = self._fit_models(tr, es, cols)
            if "lightgbm" in models:
                self.importance = models["lightgbm"].importance()
            for name, m in models.items():
                preds.append(pd.DataFrame({"date": fut["date"].values, "variant_id": fut["variant_id"].values,
                                           "segment": fut["segment"].values, "model": name, "pred": m.predict(fut[cols])}))
        pred_df = pd.concat(preds, ignore_index=True)
        dates = pd.date_range(as_of + pd.Timedelta(days=1), as_of + pd.Timedelta(days=cfg.horizon_days), freq="D")
        model_names = sorted(pred_df["model"].unique())
        PM = {n: self._bottom_matrix(pred_df[pred_df["model"] == n], dates, "pred") for n in model_names}
        wb = self.weights.get("bottom") or {n: 1.0 / len(model_names) for n in model_names}
        bottom = blend({n: PM[n] for n in model_names if n in wb}, wb)
        # cold start: young series lean on their category prior
        long = pd.DataFrame({"date": np.repeat(dates, self.hier.n_bottom),
                             "variant_id": [b[0] for _ in dates for b in self.hier.bottom],
                             "segment": [b[1] for _ in dates for b in self.hier.bottom], "p50": bottom.ravel()})
        long = apply_cold_start(long, self.panel, cfg, cfg.as_of)
        bottom = long["p50"].values.reshape(len(dates), self.hier.n_bottom)
        base = self.hier.aggregate(bottom)
        # aggregate levels: blend the bottom-up models with N-BEATS where it earned weight
        nb = self._nbeats(as_of, cfg.horizon_days)
        if nb is not None:
            idx, pred = nb
            NB = np.full_like(base, np.nan); NB[:, idx] = pred[:, :len(dates)].T
            agg_models = {n: self.hier.aggregate(PM[n]) for n in model_names}
            for lvl in AGG_LEVELS:
                w = self.weights.get(lvl)
                if not w or "nbeats" not in w:
                    continue
                ridx = self.hier.levels[lvl]
                cands = {n: (agg_models[n][:, ridx] if n != "nbeats" else np.nan_to_num(NB[:, ridx])) for n in w if n in agg_models or n == "nbeats"}
                base[:, ridx] = blend(cands, w)
        rec = self.hier.mint(base, self.residuals) if self.residuals is not None else base
        # intervals
        hs = np.arange(1, len(dates) + 1)
        out = []
        for r, (lvl, name) in enumerate(self.hier.rows):
            lo = np.array([self.intervals.band(lvl, bucket_of(int(h), buckets) or buckets[-1][1])[0] for h in hs])
            hi = np.array([self.intervals.band(lvl, bucket_of(int(h), buckets) or buckets[-1][1])[1] for h in hs])
            out.append(pd.DataFrame({"date": dates, "h": hs, "level": lvl, "name": name, "p50": rec[:, r],
                                     "p10": rec[:, r] * lo, "p90": rec[:, r] * hi, "base": base[:, r]}))
        self.forecast_long = pd.concat(out, ignore_index=True)
        return self.forecast_long

    # ------------------------------------------------------------------ variance
    def variance(self) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame], List[dict], str]:
        if self.cf is None:
            return pd.DataFrame(), {}, [], "no cash flow model supplied"
        eng = VarianceEngine(self.cfg, self.cf)
        total = self.forecast_long[self.forecast_long["level"] == "total"][["date", "p10", "p50", "p90"]]
        monthly = eng.monthly_view(self.total_daily, total)
        cash = {name: eng.cash_view(monthly, name) for name in self.cf.scenario_names if name in self.cf.flows}
        alerts = eng.alerts(monthly, cash)
        return monthly, cash, alerts, eng.summary(monthly, cash, alerts)

    # ------------------------------------------------------------------ run
    def run(self) -> str:
        t0 = time.time()
        log.info("panel: %d rows, %d series, %s..%s", len(self.panel), self.hier.n_bottom,
                 self.panel["date"].min().date(), self.panel["date"].max().date())
        self.backtest()
        self.metrics.to_csv(self.out / "backtest_metrics.csv", index=False)
        (self.out / "blend_weights.json").write_text(json.dumps(self.weights, indent=2))
        log.info("backtest done (%.0fs)", time.time() - t0)
        fc = self.forecast()
        fc.to_csv(self.out / "forecast_daily.csv", index=False)
        monthly_fc = (fc.assign(month=fc["date"].dt.to_period("M").astype(str))
                        .groupby(["month", "level", "name"], as_index=False)[["p10", "p50", "p90"]].sum())
        monthly_fc.to_csv(self.out / "forecast_monthly.csv", index=False)
        if self.importance is not None:
            self.importance.to_csv(self.out / "feature_importance.csv", header=["gain"])
        monthly, cash, alerts, summary = self.variance()
        if len(monthly):
            monthly.to_csv(self.out / "variance_monthly.csv", index=False)
            for name, path in cash.items():
                path.to_csv(self.out / f"cash_path_{name.replace(' ', '_')}.csv", index=False)
            (self.out / "alerts.json").write_text(json.dumps(alerts, indent=2, default=str))
        (self.out / "summary.txt").write_text(summary)
        log.info("done (%.0fs): %s", time.time() - t0, self.out)
        return summary


# ---------------------------------------------------------------------- CLI
def load_panel(args, cfg: Config) -> pd.DataFrame:
    products = None
    if args.products:
        products = json.loads(Path(args.products).read_text())
    if args.orders:
        rows = read_orders_json(args.orders, cfg, products)
    elif args.csv:
        rows = read_shopify_export_csv(args.csv, cfg)
    else:
        raise SystemExit("give --orders orders.json or --csv export.csv")
    return to_daily_panel(rows, cfg.as_of)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m forecast", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="backtest, forecast and variance report")
    run.add_argument("--orders", help="orders JSON in the Admin shape")
    run.add_argument("--products", help="products JSON: {product_id: {product_type}}")
    run.add_argument("--csv", help="the admin's orders CSV export instead of --orders")
    run.add_argument("--cashflow", help="the Cash Flow workbook")
    run.add_argument("--as-of", required=True, help="YYYY-MM-DD, the last day of actuals")
    run.add_argument("--out", default="forecast_out")
    run.add_argument("--scenario", help="which scenario feeds the baseline feature (default: the first)")
    run.add_argument("--horizon", type=int, default=90)
    run.add_argument("--folds", type=int, default=5)
    run.add_argument("--no-lightgbm", action="store_true"); run.add_argument("--no-catboost", action="store_true")
    run.add_argument("--no-nbeats", action="store_true")
    syn = sub.add_parser("synth", help="write a synthetic store shaped by the workbook")
    syn.add_argument("--cashflow"); syn.add_argument("--as-of", required=True); syn.add_argument("--out", default="synthetic")
    syn.add_argument("--days", type=int, default=830); syn.add_argument("--scenario", default="Algorithm 3")
    syn.add_argument("--scale", type=float, default=0.93)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    as_of = date.fromisoformat(args.as_of)
    cf = CashFlowModel.from_workbook(args.cashflow) if args.cashflow else None
    if args.cmd == "synth":
        from .synth import write_synthetic
        op, pp = write_synthetic(args.out, as_of, cf, days=args.days, scenario=args.scenario, scenario_scale=args.scale)
        print(op); print(pp)
        return 0
    cfg = Config(as_of=as_of, horizon_days=args.horizon, cv_folds=args.folds, use_lightgbm=not args.no_lightgbm,
                 use_catboost=not args.no_catboost, use_nbeats=not args.no_nbeats)
    panel = load_panel(args, cfg)
    runner = Runner(cfg, panel, cf, Path(args.out), scenario=args.scenario)
    print(runner.run())
    return 0
