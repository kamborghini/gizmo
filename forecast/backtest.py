"""Time-based validation and the M5 scorecard.

Folds are consecutive 28-day windows ending at as_of, each trained on
everything before it (expanding window), so a fold never sees a day after
its own start. WRMSSE is the M5 metric: per level, each series' RMSSE
(errors scaled by the series' own one-step variability in training) weighted
by the series' share of net sales in the last 28 training days; the levels
are then averaged, so the top line and the long tail count the same.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from .reconcile import Hierarchy


@dataclass(frozen=True)
class Fold:
    k: int
    train_end: pd.Timestamp
    valid_start: pd.Timestamp
    valid_end: pd.Timestamp


def expanding_folds(as_of, n_folds: int, window: int) -> List[Fold]:
    end = pd.Timestamp(as_of).normalize()
    folds = []
    for i in range(n_folds):
        ve = end - pd.Timedelta(days=window * (n_folds - 1 - i))
        vs = ve - pd.Timedelta(days=window - 1)
        folds.append(Fold(i + 1, vs - pd.Timedelta(days=1), vs, ve))
    return folds


def rmsse(actual: np.ndarray, pred: np.ndarray, train: np.ndarray) -> float:
    t = np.asarray(train, dtype=float)
    nz = np.nonzero(t)[0]
    if len(nz) == 0:
        return np.nan
    t = t[nz[0]:]
    if len(t) < 2:
        return np.nan
    scale = np.mean(np.diff(t) ** 2)
    if scale <= 0:
        return np.nan
    return float(np.sqrt(np.mean((np.asarray(actual) - np.asarray(pred)) ** 2) / scale))


def level_weights(train_rows: np.ndarray, hier: Hierarchy, last_days: int = 28) -> np.ndarray:
    """Per row: its share of its level's net sales over the last training days."""
    recent = np.clip(train_rows[-last_days:], 0, None).sum(axis=0)
    w = np.zeros(len(hier.rows))
    for lvl, idx in hier.levels.items():
        tot = recent[idx].sum()
        w[idx] = recent[idx] / tot if tot > 0 else 1.0 / len(idx)
    return w


def level_metrics(actual: np.ndarray, pred: np.ndarray, train: np.ndarray, hier: Hierarchy) -> pd.DataFrame:
    """actual/pred (Tv, n_rows), train (Tt, n_rows). One row per level."""
    w = level_weights(train, hier)
    out = []
    for lvl, idx in hier.levels.items():
        scores = np.array([rmsse(actual[:, r], pred[:, r], train[:, r]) for r in idx])
        ok = ~np.isnan(scores)
        wl = w[idx][ok]
        wr = float((scores[ok] * wl).sum() / wl.sum()) if wl.sum() > 0 else np.nan
        a, p = actual[:, idx], pred[:, idx]
        err = a - p
        mae = float(np.mean(np.abs(err)))
        tot_a = float(a.sum())
        bias = float((p.sum() - tot_a) / tot_a) if tot_a else np.nan
        mad = float(np.mean(np.abs(err.sum(axis=1))))
        ts = float(err.sum() / mad) if mad > 0 else np.nan
        out.append({"level": lvl, "n_series": len(idx), "wrmsse": wr, "mae": mae, "bias_pct": bias, "tracking_signal": ts})
    df = pd.DataFrame(out)
    df.loc[len(df)] = {"level": "ALL", "n_series": int(df["n_series"].sum()), "wrmsse": float(df["wrmsse"].mean()),
                       "mae": float(df["mae"].mean()), "bias_pct": float(df.loc[df["level"] == "total", "bias_pct"].iloc[0]),
                       "tracking_signal": float(df.loc[df["level"] == "total", "tracking_signal"].iloc[0])}
    return df


class IntervalModel:
    """Empirical prediction intervals from the backtest: per level and horizon
    bucket, the quantiles of actual/forecast on days where the forecast was
    material. Applied multiplicatively to the point forecast, so the band
    widens with the horizon exactly as the backtest said it should."""

    def __init__(self, quantiles: Tuple[float, float] = (0.10, 0.90), floor: float = 1.0):
        self.q = quantiles
        self.floor = floor
        self.table: Dict[Tuple[str, int], Tuple[float, float]] = {}

    def fit(self, rows: pd.DataFrame) -> "IntervalModel":
        """rows: level, bucket, actual, pred."""
        r = rows[rows["pred"] >= self.floor].copy()
        r["ratio"] = r["actual"] / r["pred"]
        for (lvl, b), g in r.groupby(["level", "bucket"]):
            if len(g) >= 20:
                self.table[(lvl, int(b))] = (float(g["ratio"].quantile(self.q[0])), float(g["ratio"].quantile(self.q[1])))
        # a level with no fit borrows the widest band seen
        return self

    def band(self, level: str, bucket: int) -> Tuple[float, float]:
        if (level, bucket) in self.table:
            return self.table[(level, bucket)]
        same = [v for (l, _), v in self.table.items() if l == level]
        if same:
            return min(v[0] for v in same), max(v[1] for v in same)
        allv = list(self.table.values())
        return (min(v[0] for v in allv), max(v[1] for v in allv)) if allv else (0.7, 1.3)
