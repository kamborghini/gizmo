"""The hierarchy and its reconciliation.

The bottom grain is variant x segment. Two trees sum from it: the product
tree (variant -> product -> category -> total) and the segment tree (segment
-> total), which makes this a grouped hierarchy, not a strict one. A summing
matrix S maps the bottom vector to every series at every level, and both
bottom-up and MinT are expressed through it, so whatever is reconciled sums
cleanly to the top line the cash flow model is measured on.

MinT (Wickramasuriya, Athanasopoulos and Hyndman 2019) with the Schafer-
Strimmer shrinkage of the in-sample residual covariance; WLS on the diagonal
when there are too few residual rows for a covariance to mean anything.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from .ingest import KEY


@dataclass
class Hierarchy:
    bottom: List[Tuple[str, str]]            # (variant_id, segment), fixed order
    rows: List[Tuple[str, str]]              # (level, name) for every row of S, aggregates first
    S: np.ndarray                            # (n_rows, n_bottom)
    levels: Dict[str, List[int]]             # level -> row indices

    @classmethod
    def from_keys(cls, keys: pd.DataFrame) -> "Hierarchy":
        k = keys.drop_duplicates(KEY).reset_index(drop=True)
        bottom = [(str(v), str(s)) for v, s in zip(k["variant_id"], k["segment"])]
        n = len(bottom)
        pos = {b: i for i, b in enumerate(bottom)}
        agg_rows: List[Tuple[str, str, List[int]]] = [("total", "Total", list(range(n)))]

        def members(col: str) -> List[Tuple[str, List[int]]]:
            out = []
            for name, grp in k.groupby(col, sort=True):
                out.append((str(name), [pos[(str(v), str(s))] for v, s in zip(grp["variant_id"], grp["segment"])]))
            return out

        for level, col in (("category", "category"), ("segment", "segment"), ("product", "product_id"), ("variant", "variant_id")):
            for name, idx in members(col):
                agg_rows.append((level, name, idx))
        rows = [(lvl, name) for lvl, name, _ in agg_rows] + [("bottom", f"{v}|{s}") for v, s in bottom]
        S = np.zeros((len(rows), n))
        for r, (_, _, idx) in enumerate(agg_rows):
            S[r, idx] = 1.0
        S[len(agg_rows):, :] = np.eye(n)
        levels: Dict[str, List[int]] = {}
        for r, (lvl, _) in enumerate(rows):
            levels.setdefault(lvl, []).append(r)
        return cls(bottom=bottom, rows=rows, S=S, levels=levels)

    @property
    def n_bottom(self) -> int:
        return len(self.bottom)

    def aggregate(self, bottom_matrix: np.ndarray) -> np.ndarray:
        """(T, n_bottom) -> (T, n_rows): bottom-up through S."""
        return np.asarray(bottom_matrix) @ self.S.T

    bottom_up = aggregate

    def row_index(self, level: str, name: str) -> int:
        return self.rows.index((level, name))

    def frame(self, matrix: np.ndarray, dates: pd.DatetimeIndex, value: str = "value") -> pd.DataFrame:
        """A long frame: date, level, name, value."""
        out = []
        for r, (lvl, name) in enumerate(self.rows):
            out.append(pd.DataFrame({"date": dates, "level": lvl, "name": name, value: matrix[:, r]}))
        return pd.concat(out, ignore_index=True)

    def mint(self, y_hat: np.ndarray, residuals: np.ndarray, nonneg: bool = True) -> np.ndarray:
        """Reconcile base forecasts for every row. y_hat (T, n_rows); residuals
        (R, n_rows) in-sample one-step errors of the same base forecasts."""
        S = self.S
        R = np.asarray(residuals, dtype=float)
        R = R[~np.isnan(R).any(axis=1)]
        n_rows = S.shape[0]
        if R.shape[0] >= 3 * n_rows:
            W = shrink_covariance(R)
        else:
            v = np.nanvar(R, axis=0) if R.shape[0] > 1 else np.ones(n_rows)
            W = np.diag(np.where(v > 0, v, np.nanmean(v[v > 0]) if (v > 0).any() else 1.0))
        W = W + 1e-8 * np.eye(n_rows)
        Winv_S = np.linalg.solve(W, S)                 # W^-1 S
        M = S.T @ Winv_S                               # S' W^-1 S
        G = np.linalg.solve(M, Winv_S.T)               # (S' W^-1 S)^-1 S' W^-1
        bottom = (G @ np.asarray(y_hat, dtype=float).T).T   # (T, n_bottom)
        if nonneg:
            bottom = np.clip(bottom, 0, None)
        return self.aggregate(bottom)


def shrink_covariance(R: np.ndarray) -> np.ndarray:
    """Ledoit-Wolf style shrinkage toward the diagonal, with the Schafer-Strimmer
    estimate of the shrinkage intensity computed on correlations."""
    n, p = R.shape
    X = R - R.mean(axis=0)
    cov = X.T @ X / max(n - 1, 1)
    sd = np.sqrt(np.clip(np.diag(cov), 1e-12, None))
    Xs = X / sd
    corr = Xs.T @ Xs / max(n - 1, 1)
    # variance of each correlation estimate
    var_r = ((Xs[:, :, None] * Xs[:, None, :]) ** 2).sum(axis=0) / max(n - 1, 1) ** 2 * n / max(n - 1, 1)
    off = ~np.eye(p, dtype=bool)
    denom = float((corr[off] ** 2).sum())
    lam = 1.0 if denom <= 0 else float(np.clip(var_r[off].sum() / denom, 0.0, 1.0))
    return lam * np.diag(np.diag(cov)) + (1 - lam) * cov
