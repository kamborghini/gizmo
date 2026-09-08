"""The one interface every tabular model speaks."""
from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd


class Forecaster:
    name: str = "base"

    def fit(self, X: pd.DataFrame, y: pd.Series, categorical: List[str], sample_weight: Optional[np.ndarray] = None,
            valid: Optional[tuple] = None) -> "Forecaster":
        raise NotImplementedError

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        raise NotImplementedError

    @staticmethod
    def numeric(X: pd.DataFrame) -> pd.DataFrame:
        """Drop pandas categoricals for models that want a plain matrix."""
        return X[[c for c in X.columns if not str(X[c].dtype) == "category"]].astype(float)
