"""Features at a forecast origin, leak-free by construction.

For a horizon bucket whose longest horizon is H, every history-derived
feature for date d is computed from the series up to d - H only: the row
cannot see anything it will not know at forecast time. Known-in-advance
signal (calendar, list price, the cash flow baseline) is taken at d itself.
One model per bucket, so within a bucket the features are slightly older than
they need to be for the shorter horizons; that is the price of a row count
that does not multiply by the bucket width, and M5 winners paid it too.

Groups:
  lags          absolute lags from d that are >= H (7, 14, 28, 56, 364, 365)
  origin        the last value at the origin, rolling mean/std/max, EWMA,
                zero share, days since the last sale
  price         list price, price relative to its trailing 90-day median,
                discount share at the origin (never a same-day flag)
  yoy           the same weeks last year and the store's growth since
  encodings     frequency (sales share) and smoothed target mean per variant,
                product, category, segment, fitted on training rows only
  calendar      weekday, month, holidays, Black Friday, paydays, year-end lull
  cash flow     the daily total target from the workbook, the series' share
                of the total, their product as the series' baseline, and the
                recent level relative to that baseline
  age           days since the first sale, and a new-series flag
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from .calendar import calendar_frame
from .config import Config
from .ingest import KEY

CATEGORICALS = ["variant_id", "product_id", "category", "segment"]
META = ["date", "variant_id", "segment"]


@dataclass
class Encodings:
    """Fitted on training rows; applied to any rows. Target encoding is the
    smoothed mean of the target per key (m = 20 pseudo-observations at the
    global mean); frequency encoding is the key's share of net sales."""
    target_mean: float = 0.0
    te: Dict[str, Dict[str, float]] = field(default_factory=dict)
    fe: Dict[str, Dict[str, float]] = field(default_factory=dict)
    m: float = 20.0

    @classmethod
    def fit(cls, train: pd.DataFrame, target: str, m: float = 20.0) -> "Encodings":
        enc = cls(target_mean=float(train[target].mean()) if len(train) else 0.0, m=m)
        total = float(train[target].clip(lower=0).sum()) or 1.0
        for col in CATEGORICALS:
            g = train.groupby(col)[target]
            n, s = g.count(), g.sum()
            enc.te[col] = ((s + enc.m * enc.target_mean) / (n + enc.m)).to_dict()
            enc.fe[col] = (train.groupby(col)[target].apply(lambda x: x.clip(lower=0).sum()) / total).to_dict()
        return enc

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        for col in CATEGORICALS:
            df["te_" + col] = df[col].map(self.te.get(col, {})).fillna(self.target_mean).astype(float)
            df["fe_" + col] = df[col].map(self.fe.get(col, {})).fillna(0.0).astype(float)
        return df


class FeatureBuilder:
    def __init__(self, cfg: Config, daily_target: Optional[pd.DataFrame] = None):
        """daily_target: date, net_sales_target (the workbook's month spread over
        its days), or None when there is no baseline to lean on."""
        self.cfg = cfg
        self.daily_target = None
        if daily_target is not None and len(daily_target):
            dt = daily_target.copy()
            dt["date"] = pd.to_datetime(dt["date"]).dt.normalize()
            self.daily_target = dt[["date", "net_sales_target"]]

    # ------------------------------------------------------------------
    def build(self, panel: pd.DataFrame, shift: int, encodings: Optional[Encodings] = None) -> pd.DataFrame:
        cfg, y = self.cfg, self.cfg.target
        df = panel.sort_values(KEY + ["date"]).reset_index(drop=True).copy()
        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
        g = df.groupby(KEY, sort=False)
        # --- lags absolute from d, only those the horizon allows
        for k in sorted(set(cfg.lags) | {364}):
            if k >= shift:
                df[f"lag_{k}"] = g[y].shift(k)
        # --- origin-relative: everything computed on the series shifted by H
        ys = g[y].shift(shift)
        df["_ys"] = ys
        gs = df.groupby(KEY, sort=False)["_ys"]
        df["o_last"] = ys
        for w in cfg.roll_windows:
            df[f"roll_mean_{w}"] = gs.transform(lambda s: s.rolling(w, min_periods=1).mean())
            df[f"roll_std_{w}"] = gs.transform(lambda s: s.rolling(w, min_periods=2).std())
        df["roll_max_28"] = gs.transform(lambda s: s.rolling(28, min_periods=1).max())
        for span in cfg.ewma_spans:
            df[f"ewma_{span}"] = gs.transform(lambda s: s.ewm(span=span, min_periods=1).mean())
        df["zero_share_28"] = gs.transform(lambda s: (s.fillna(0) <= 0).astype(float).rolling(28, min_periods=1).mean())
        df["days_since_sale"] = gs.transform(_days_since_positive)
        # units carry a second view of the same history
        us = g[cfg.aux_target].shift(shift)
        df["_us"] = us
        df["units_roll_28"] = df.groupby(KEY, sort=False)["_us"].transform(lambda s: s.rolling(28, min_periods=1).mean())
        # --- price: known at d; its history at the origin
        df["price_med_90"] = g["price"].transform(lambda s: s.shift(shift).rolling(90, min_periods=7).median())
        df["price_rel_90"] = (df["price"] / df["price_med_90"]).replace([np.inf, -np.inf], np.nan)
        disc_share = (df["discount"] / df["gross_sales"].replace(0, np.nan)).fillna(0.0)
        df["_ds"] = disc_share.groupby([df[k] for k in KEY]).shift(shift)
        df["discount_share_28"] = df.groupby(KEY, sort=False)["_ds"].transform(lambda s: s.rolling(28, min_periods=1).mean())
        # No same-day discount flag: a day carries a discount only when something
        # sold, so the flag is the target in disguise, and a future day never has
        # one. Promotions that are known in advance live in the calendar.
        # --- the same weeks last year, and the store's growth since: the
        # seasonal-naive-with-growth anchor every retail model should have
        df["yoy_mean_28"] = g[y].transform(lambda s: s.shift(350).rolling(29, min_periods=7).mean())
        df["yoy_origin_28"] = g[y].transform(lambda s: s.shift(shift + 350).rolling(29, min_periods=7).mean())
        df["yoy_ratio"] = (df["roll_mean_28"] / df["yoy_origin_28"].replace(0, np.nan)).clip(0.2, 5.0)
        df["yoy_projection"] = df["yoy_mean_28"] * df["yoy_ratio"]
        # --- calendar
        cal = calendar_frame(pd.DatetimeIndex(df["date"].unique()))
        df = df.merge(cal, left_on="date", right_index=True, how="left")
        # --- age
        first = g["date"].transform("min")
        df["age_days"] = (df["date"] - first).dt.days
        df["is_new"] = (df["age_days"] < cfg.cold_start_days).astype(int)
        # --- cash flow baseline
        if self.daily_target is not None:
            df = df.merge(self.daily_target, on="date", how="left")
            tot = df.groupby("date")[y].transform("sum")
            df["_tot_s"] = tot.groupby([df[k] for k in KEY]).shift(shift)
            num = df.groupby(KEY, sort=False)["_ys"].transform(lambda s: s.rolling(365, min_periods=28).sum())
            den = df.groupby(KEY, sort=False)["_tot_s"].transform(lambda s: s.rolling(365, min_periods=28).sum())
            df["cf_share"] = (num / den.replace(0, np.nan)).clip(lower=0).fillna(0.0)
            df["cf_target_total"] = df["net_sales_target"].fillna(0.0)
            df["cf_baseline"] = df["cf_target_total"] * df["cf_share"]
            base28 = df.groupby(KEY, sort=False)["cf_baseline"].transform(lambda s: s.shift(shift).rolling(28, min_periods=1).mean())
            df["level_vs_baseline"] = (df["roll_mean_28"] / base28.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
            df = df.drop(columns=["net_sales_target", "_tot_s"])
        else:
            for c in ("cf_share", "cf_target_total", "cf_baseline", "level_vs_baseline"):
                df[c] = np.nan
        # --- encodings and categorical codes
        if encodings is not None:
            df = encodings.apply(df)
        for col in CATEGORICALS:
            df["cat_" + col] = df[col].astype("category")
        df = df.drop(columns=["_ys", "_us", "_ds"])
        df["shift"] = shift
        return df

    def feature_columns(self, df: pd.DataFrame) -> List[str]:
        drop = set(META + CATEGORICALS + ["sku", "product", self.cfg.target, self.cfg.aux_target,
                                          "gross_sales", "discount", "shift"])
        return [c for c in df.columns if c not in drop]


def _days_since_positive(s: pd.Series) -> pd.Series:
    """For each position, days since the last positive value at or before it."""
    out = np.full(len(s), np.nan)
    last = None
    for i, v in enumerate(s.values):
        if v is not None and not np.isnan(v) and v > 0:
            last = i
        out[i] = np.nan if last is None else i - last
    return pd.Series(out, index=s.index)


def extend_for_forecast(panel: pd.DataFrame, as_of, horizon: int, cfg: Config) -> pd.DataFrame:
    """Append the future dates to every series so features can be built for
    them: target NaN, price carried forward, no discount. A series that has
    not sold in 180 days is left behind, as a retired SKU would only add noise
    at the bottom and nothing at the top."""
    end = pd.Timestamp(as_of)
    future = pd.date_range(end + pd.Timedelta(days=1), end + pd.Timedelta(days=horizon), freq="D")
    last = panel.groupby(KEY).agg(last_date=("date", "max"),
                                  last_sale=(cfg.target, lambda s: panel.loc[s.index, "date"][s > 0].max() if (s > 0).any() else pd.NaT))
    frames = [panel]
    for (vid, seg), row in last.iterrows():
        if pd.notna(row["last_sale"]) and (end - row["last_sale"]).days > 180:
            continue
        tail = panel[(panel["variant_id"] == vid) & (panel["segment"] == seg)].iloc[-1]
        fut = pd.DataFrame({"date": future, "variant_id": vid, "segment": seg})
        for c in ("sku", "product_id", "product", "category", "price"):
            fut[c] = tail[c]
        for c in ("units", cfg.target, "gross_sales", "discount"):
            fut[c] = np.nan if c in (cfg.target, "units") else 0.0
        frames.append(fut)
    return pd.concat(frames, ignore_index=True).sort_values(KEY + ["date"]).reset_index(drop=True)
