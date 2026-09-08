"""New SKUs have no lags. Until a series is cold_start_days old its forecast
leans on a prior: the mean daily net sales of an established series in the
same category and segment over the last eight weeks, scaled by the new
variant's price relative to its category's median price (a dearer item
sells fewer units for similar revenue, so the revenue prior moves less than
a unit prior would). The lean fades linearly with age, and the 'is_new'
and 'age_days' features let the GBDTs learn the launch ramp themselves once
a few launches are in the history."""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd

from .config import Config
from .ingest import KEY


def category_priors(panel: pd.DataFrame, cfg: Config, as_of, window: int = 56) -> Dict[Tuple[str, str], float]:
    end = pd.Timestamp(as_of)
    p = panel[(panel["date"] > end - pd.Timedelta(days=window)) & (panel["date"] <= end)]
    first = panel.groupby(KEY)["date"].min()
    established = first[first <= end - pd.Timedelta(days=cfg.cold_start_days)].index
    p = p.set_index(KEY)
    p = p[p.index.isin(established)].reset_index()
    if p.empty:
        return {}
    per_series = p.groupby(["category"] + KEY)[cfg.target].mean().reset_index()
    return per_series.groupby(["category", "segment"])[cfg.target].mean().to_dict()


def apply_cold_start(bottom: pd.DataFrame, panel: pd.DataFrame, cfg: Config, as_of) -> pd.DataFrame:
    """bottom: date, variant_id, segment, p50 (the model's bottom forecast).
    Blends in the prior for young series; returns the same frame."""
    end = pd.Timestamp(as_of)
    priors = category_priors(panel, cfg, as_of)
    if not priors:
        return bottom
    meta = panel.groupby(KEY).agg(first=("date", "min"), category=("category", "first"), price=("price", "last")).reset_index()
    cat_price = panel.groupby("category")["price"].median().to_dict()
    meta["age"] = (end - meta["first"]).dt.days
    young = meta[meta["age"] < cfg.cold_start_days]
    if young.empty:
        return bottom
    out = bottom.copy()
    for _, r in young.iterrows():
        prior = priors.get((r["category"], r["segment"]))
        if prior is None:
            continue
        rel = (r["price"] / cat_price.get(r["category"], r["price"])) if cat_price.get(r["category"]) else 1.0
        prior *= float(np.clip(rel, 0.5, 2.0)) ** 0.5
        alpha = float(np.clip(r["age"] / cfg.cold_start_days, 0.0, 1.0))
        mask = (out["variant_id"] == r["variant_id"]) & (out["segment"] == r["segment"])
        out.loc[mask, "p50"] = alpha * out.loc[mask, "p50"] + (1 - alpha) * prior
    return out
