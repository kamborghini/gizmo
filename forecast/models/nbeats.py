"""N-BEATS (Oreshkin et al. 2020), generic architecture, as one global model
over the aggregated series of a level. It reads a window of the series'
own past and emits the whole horizon at once, so it is the direct-forecasting
counterpart to the GBDTs and the member that sees the shape of a trend rather
than a bag of lags. It is trained on the product, category, segment and
total rows, where the series are dense enough to have a shape; the bottom
grain is left to the GBDTs, and MinT makes the two agree.

PyTorch is optional. Without it the pipeline runs on the GBDTs alone.

It trains in a child process of its own (run_isolated). LightGBM and PyTorch
each bring an OpenMP runtime, and on macOS the second one to start a
parallel region in a process the first has already used deadlocks; a
spawned process gives the network a runtime to itself.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

try:
    import torch
    from torch import nn
    _HAS_TORCH = True
except Exception:  # pragma: no cover
    _HAS_TORCH = False


def available() -> bool:
    return _HAS_TORCH


if _HAS_TORCH:
    class _Block(nn.Module):
        def __init__(self, L: int, H: int, width: int, layers: int):
            super().__init__()
            fc = [nn.Linear(L, width), nn.ReLU()]
            for _ in range(layers - 1):
                fc += [nn.Linear(width, width), nn.ReLU()]
            self.fc = nn.Sequential(*fc)
            self.theta_b = nn.Linear(width, L)
            self.theta_f = nn.Linear(width, H)

        def forward(self, x):
            h = self.fc(x)
            return self.theta_b(h), self.theta_f(h)

    class _NBeats(nn.Module):
        def __init__(self, L: int, H: int, blocks: int = 6, width: int = 256, layers: int = 4):
            super().__init__()
            self.blocks = nn.ModuleList([_Block(L, H, width, layers) for _ in range(blocks)])

        def forward(self, x):
            residual = x
            forecast = torch.zeros(x.shape[0], self.blocks[0].theta_f.out_features, device=x.device)
            for b in self.blocks:
                back, fore = b(residual)
                residual = residual - back
                forecast = forecast + fore
            return forecast


class NBeatsForecaster:
    """fit(series: (T, N)) on the history of N series; predict() -> (N, H)."""
    name = "nbeats"

    def __init__(self, lookback: int = 56, horizon: int = 90, epochs: int = 40, batch: int = 256,
                 lr: float = 1e-3, seed: int = 7, device: Optional[str] = None):
        if not _HAS_TORCH:
            raise RuntimeError("torch is not installed")
        self.L, self.H, self.epochs, self.batch, self.lr, self.seed = lookback, horizon, epochs, batch, lr, seed
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.scale = None

    def _windows(self, Y: np.ndarray):
        T, N = Y.shape
        xs, ys = [], []
        for t in range(self.L, T - self.H + 1):
            xs.append(Y[t - self.L:t].T)          # (N, L)
            ys.append(Y[t:t + self.H].T)          # (N, H)
        X = np.concatenate(xs, axis=0) if xs else np.zeros((0, self.L))
        Yw = np.concatenate(ys, axis=0) if ys else np.zeros((0, self.H))
        return X, Yw

    def fit(self, Y: np.ndarray) -> "NBeatsForecaster":
        import sys
        if "lightgbm" in sys.modules or "catboost" in sys.modules:
            # two OpenMP runtimes in one process: PyTorch's parallel regions
            # deadlock on macOS once a GBDT has used the other one
            torch.set_num_threads(1)
        torch.manual_seed(self.seed); np.random.seed(self.seed)
        Y = np.asarray(Y, dtype=np.float32)
        T, N = Y.shape
        if T < self.L + self.H + 7:
            self.H = max(7, T - self.L - 7)
        # scale each window by its own input mean: the network learns shape, not size
        X, Yw = self._windows(Y)
        if len(X) == 0:
            raise ValueError("not enough history for one window")
        s = X.mean(axis=1, keepdims=True) + 1e-3
        Xn, Yn = X / s, Yw / s
        self.model = _NBeats(self.L, self.H).to(self.device)
        opt = torch.optim.Adam(self.model.parameters(), lr=self.lr)
        Xt = torch.tensor(Xn, dtype=torch.float32, device=self.device)
        Yt = torch.tensor(Yn, dtype=torch.float32, device=self.device)
        n = len(Xt)
        for _ in range(self.epochs):
            perm = torch.randperm(n, device=self.device)
            self.model.train()
            for i in range(0, n, self.batch):
                idx = perm[i:i + self.batch]
                opt.zero_grad()
                loss = torch.mean(torch.abs(self.model(Xt[idx]) - Yt[idx]))   # MAE on scaled windows
                loss.backward()
                nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                opt.step()
        self.last = Y[-self.L:].T   # (N, L)
        return self

    def predict(self) -> np.ndarray:
        self.model.eval()
        x = np.asarray(self.last, dtype=np.float32)
        s = x.mean(axis=1, keepdims=True) + 1e-3
        with torch.no_grad():
            out = self.model(torch.tensor(x / s, dtype=torch.float32, device=self.device)).cpu().numpy()
        return np.clip(out * s, 0, None)


def _worker(Y, lookback, horizon, epochs, seed, q):
    try:
        m = NBeatsForecaster(lookback=lookback, horizon=horizon, epochs=epochs, seed=seed).fit(Y)
        q.put(("ok", m.predict()))
    except Exception as e:  # pragma: no cover
        q.put(("err", repr(e)))


def run_isolated(Y: np.ndarray, lookback: int = 56, horizon: int = 90, epochs: int = 25, seed: int = 7,
                 timeout_s: int = 1800) -> np.ndarray:
    """fit + predict in a spawned process; returns (N, horizon)."""
    import multiprocessing as mp
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    p = ctx.Process(target=_worker, args=(np.asarray(Y, dtype=np.float32), lookback, horizon, epochs, seed, q))
    p.start()
    try:
        status, payload = q.get(timeout=timeout_s)
    except Exception:
        p.terminate(); raise TimeoutError("nbeats did not finish")
    p.join()
    if status != "ok":
        raise RuntimeError(payload)
    return payload

