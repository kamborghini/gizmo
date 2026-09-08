"""LightGBM and CatBoost, tuned for what retail demand is: many series,
mostly zeros at the bottom, a heavy right tail, high-cardinality keys.

Both use a Tweedie objective: it is the M5 winners' choice for intermittent,
non-negative demand, and it means a bottom-level model never predicts below
zero. LightGBM reads pandas categoricals natively; CatBoost takes the raw
string keys and does its own ordered target statistics, which is exactly the
high-cardinality treatment the product and variant keys want.
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd

from .base import Forecaster

try:
    import lightgbm as lgb
    _HAS_LGB = True
except Exception:  # pragma: no cover - library optional
    _HAS_LGB = False
try:
    import catboost as cb
    _HAS_CB = True
except Exception:  # pragma: no cover
    _HAS_CB = False


def available() -> dict:
    return {"lightgbm": _HAS_LGB, "catboost": _HAS_CB}


LGB_PARAMS = dict(
    objective="tweedie", tweedie_variance_power=1.1, metric="rmse",
    learning_rate=0.03, num_leaves=63, min_data_in_leaf=40, feature_fraction=0.7,
    bagging_fraction=0.8, bagging_freq=1, lambda_l2=1.0, max_bin=255,
    cat_smooth=20, cat_l2=10, verbosity=-1, num_threads=0,
)


class LightGBMForecaster(Forecaster):
    name = "lightgbm"

    def __init__(self, params: Optional[dict] = None, rounds: int = 1200, seed: int = 7):
        if not _HAS_LGB:
            raise RuntimeError("lightgbm is not installed")
        self.params = {**LGB_PARAMS, **(params or {}), "seed": seed}
        self.rounds = rounds
        self.model = None
        self.columns: List[str] = []

    def fit(self, X, y, categorical, sample_weight=None, valid=None):
        self.columns = list(X.columns)
        dtrain = lgb.Dataset(X, label=y.values, weight=sample_weight, categorical_feature=categorical, free_raw_data=False)
        kw = {}
        if valid is not None:
            Xv, yv = valid
            kw["valid_sets"] = [lgb.Dataset(Xv[self.columns], label=yv.values, categorical_feature=categorical, reference=dtrain)]
            kw["callbacks"] = [lgb.early_stopping(60, verbose=False)]
        self.model = lgb.train(self.params, dtrain, num_boost_round=self.rounds, **kw)
        return self

    def predict(self, X):
        return np.clip(self.model.predict(X[self.columns], num_iteration=self.model.best_iteration or None), 0, None)

    def importance(self) -> pd.Series:
        return pd.Series(self.model.feature_importance("gain"), index=self.columns).sort_values(ascending=False)


class CatBoostForecaster(Forecaster):
    name = "catboost"

    def __init__(self, params: Optional[dict] = None, iterations: int = 1200, seed: int = 7):
        if not _HAS_CB:
            raise RuntimeError("catboost is not installed")
        self.params = {"loss_function": "Tweedie:variance_power=1.2", "depth": 6, "learning_rate": 0.05,
                       "l2_leaf_reg": 3.0, "iterations": iterations, "random_seed": seed, "verbose": False,
                       "allow_writing_files": False, "thread_count": -1, **(params or {})}
        self.model = None
        self.columns: List[str] = []
        self.cat_cols: List[str] = []

    def _prep(self, X: pd.DataFrame) -> pd.DataFrame:
        Z = X[self.columns].copy()
        for c in self.cat_cols:
            Z[c] = Z[c].astype(str)
        return Z

    def fit(self, X, y, categorical, sample_weight=None, valid=None):
        self.columns = list(X.columns)
        self.cat_cols = [c for c in categorical if c in self.columns]
        self.model = cb.CatBoostRegressor(**self.params)
        eval_set = None
        if valid is not None:
            Xv, yv = valid
            eval_set = cb.Pool(self._prep(Xv), yv.values, cat_features=self.cat_cols)
        self.model.fit(cb.Pool(self._prep(X), y.values, cat_features=self.cat_cols, weight=sample_weight),
                       eval_set=eval_set, early_stopping_rounds=60 if eval_set is not None else None)
        return self

    def predict(self, X):
        return np.clip(self.model.predict(self._prep(X)), 0, None)
