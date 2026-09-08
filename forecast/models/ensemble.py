"""Out-of-fold blending. The weights are the non-negative least squares fit
of the backtest's OOF predictions to the actuals, per level, normalised to
sum to one: a model earns weight where it was right on days it had not seen.
Inverse-MAE weights when scipy is absent, equal weights when nothing beats
nothing."""
from __future__ import annotations

from typing import Dict

import numpy as np

try:
    from scipy.optimize import nnls
    _HAS_SCIPY = True
except Exception:  # pragma: no cover
    _HAS_SCIPY = False


def blend_weights(oof: Dict[str, np.ndarray], y: np.ndarray) -> Dict[str, float]:
    names = list(oof)
    A = np.column_stack([np.asarray(oof[n], dtype=float) for n in names])
    y = np.asarray(y, dtype=float)
    mask = ~np.isnan(A).any(axis=1) & ~np.isnan(y)
    A, y = A[mask], y[mask]
    if len(y) == 0 or len(names) == 1:
        return {n: 1.0 / len(names) for n in names}
    w = None
    if _HAS_SCIPY:
        # sum-to-one as a heavy penalty row: free NNLS would happily rescale a
        # model that is a fraction of the truth, and the weights are convex
        # combinations, not a regression
        lam = 1e3 * (np.abs(y).mean() + 1e-9)
        A1 = np.vstack([A, lam * np.ones((1, A.shape[1]))])
        y1 = np.concatenate([y, [lam]])
        w, _ = nnls(A1, y1)
    if w is None or w.sum() <= 0:
        mae = np.array([np.mean(np.abs(A[:, i] - y)) + 1e-9 for i in range(len(names))])
        w = 1.0 / mae
    w = w / w.sum()
    return {n: float(v) for n, v in zip(names, w)}


def blend(preds: Dict[str, np.ndarray], weights: Dict[str, float]) -> np.ndarray:
    out = None
    for n, p in preds.items():
        w = weights.get(n, 0.0)
        out = np.asarray(p) * w if out is None else out + np.asarray(p) * w
    return out
