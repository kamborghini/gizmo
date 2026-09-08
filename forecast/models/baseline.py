"""A model that is always there: the recent level times a weekday factor.
It is the floor every other model must beat in the backtest, the fallback
when the GBDT libraries are absent, and the prior a cold-start series leans
on before it has a history of its own."""
from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd

from .base import Forecaster


class SeasonalLevel(Forecaster):
    name = "seasonal_level"

    def __init__(self, level_col: str = "ewma_28"):
        self.level_col = level_col
        self.dow_factor = np.ones(7)

    def fit(self, X, y, categorical, sample_weight=None, valid=None):
        lvl = X[self.level_col].fillna(0).values
        dow = X["dow"].values.astype(int)
        for d in range(7):
            m = dow == d
            base = lvl[m].sum()
            self.dow_factor[d] = (y.values[m].sum() / base) if base > 0 else 1.0
        return self

    def predict(self, X):
        lvl = X[self.level_col].fillna(0).values
        return np.clip(lvl * self.dow_factor[X["dow"].values.astype(int)], 0, None)
