"""Five plain forecasts of the monthly total, as a sanity check on the big one.

The M5-style model in `pipeline.py` predicts every product on every day and
adds them up. That is the right shape for a shop selling many units of stable
lines daily. It is the wrong shape for this business, where a handful of
quoted projector deals decide whether a month is good and one order can be a
tenth of it, and it forecast October - the best month of the year - at a
quarter of what October has ever been.

So: five models a person can check by eye, on ONE series, the monthly total.
They disagree with each other, and where they disagree is itself the answer:
December's two years were 53,648 and 15,444, and the spread says so.

Backtested on Projected Image's own history, the SIMPLEST is the best. Last
year's same month scaled by this year's run rate came in at 28.7% typical
error and +2.7% bias; Holt-Winters and Theta over-forecast by a fifth to a
quarter, because two and a half years is not enough history to learn a
seasonality from. That ranking is computed on every run, not assumed here,
and it is shown beside the numbers so the reader can see which has earned
trust on their own data.
"""
from __future__ import annotations

import warnings
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

MIN_MONTHS = 24          # two full years, or a seasonal model has nothing to learn
DEFAULT_HORIZON = 4


def _ratio_to_last_year(y: pd.Series, back: int = 8) -> float:
    """How this year is running against the same months last year."""
    if len(y) < back + 12:
        return 1.0
    prev = y.iloc[-back - 12:-12].sum()
    return float(y.iloc[-back:].sum() / prev) if prev > 0 else 1.0


def _future_index(y: pd.Series, h: int) -> pd.PeriodIndex:
    return pd.period_range(y.index[-1] + 1, periods=h, freq="M")


def last_year_times_run_rate(y: pd.Series, h: int) -> Tuple[pd.Series, str]:
    """Last year's same month, scaled by how this year is running against it."""
    r = _ratio_to_last_year(y)
    idx = _future_index(y, h)
    return pd.Series([y.get(p - 12, np.nan) * r for p in idx], index=idx, dtype=float), \
        f"last year x {r:.2f}"


def seasonal_share(y: pd.Series, h: int) -> Tuple[pd.Series, str]:
    """A typical month from the last year, split by each month's usual share."""
    df = pd.DataFrame({"v": y.values, "m": [p.month for p in y.index]})
    share = df.groupby("m")["v"].mean()
    share = share / share.mean()
    level = float(y.iloc[-12:].mean())
    idx = _future_index(y, h)
    return pd.Series([level * float(share.get(p.month, 1.0)) for p in idx], index=idx, dtype=float), \
        f"{level:,.0f} a month, shared out"


def _holt_winters(y: pd.Series, h: int, trend: Optional[str]) -> Tuple[pd.Series, str]:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = ExponentialSmoothing(y.values, trend=trend, damped_trend=bool(trend),
                                   seasonal="add", seasonal_periods=12,
                                   initialization_method="estimated").fit()
        out = fit.forecast(h)
    return pd.Series(out, index=_future_index(y, h), dtype=float), \
        ("with a damped trend" if trend else "level and season only")


def holt_winters_flat(y: pd.Series, h: int) -> Tuple[pd.Series, str]:
    """Exponential smoothing: a level and a season, no trend."""
    return _holt_winters(y, h, None)


def holt_winters_trend(y: pd.Series, h: int) -> Tuple[pd.Series, str]:
    """The same, allowed a trend that flattens out rather than running away."""
    return _holt_winters(y, h, "add")


def theta(y: pd.Series, h: int) -> Tuple[pd.Series, str]:
    """The Theta method: average a straight line through the de-seasonalised
    history with a simple smoothing of it, then put the season back. It won
    the M3 competition being exactly this simple."""
    from statsmodels.tsa.holtwinters import SimpleExpSmoothing
    df = pd.DataFrame({"v": y.values, "m": [p.month for p in y.index]})
    f = df.groupby("m")["v"].mean()
    f = f / f.mean()
    season = np.array([float(f.get(p.month, 1.0)) for p in y.index])
    season[season == 0] = 1.0
    d = y.values / season
    n = len(d)
    b, a = np.polyfit(np.arange(n), d, 1)
    line = a + b * (n + np.arange(h))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ses = SimpleExpSmoothing(d, initialization_method="estimated").fit().forecast(h)
    idx = _future_index(y, h)
    out = (line + ses) / 2 * np.array([float(f.get(p.month, 1.0)) for p in idx])
    return pd.Series(out, index=idx, dtype=float), f"trend {b:+,.0f} a month"


MODELS = (
    ("Last year x run rate", last_year_times_run_rate),
    ("Seasonal share of year", seasonal_share),
    ("Holt-Winters, flat", holt_winters_flat),
    ("Holt-Winters, trend", holt_winters_trend),
    ("Theta", theta),
)


def _score(y: pd.Series, fn, folds: int = 3, h: int = 3) -> Dict[str, Optional[float]]:
    """Fit to each of the last few cut-offs and score the months that followed.

    Typical error AND bias, because they say different things: a model can be
    close on average and still lean high every single month, which is what
    quietly turns a plan green."""
    errs: List[float] = []
    for k in range(folds, 0, -1):
        cut = len(y) - h - k + 1
        if cut < MIN_MONTHS:
            continue
        try:
            f, _ = fn(y.iloc[:cut], h)
        except Exception:
            continue
        act = y.iloc[cut:cut + h]
        common = f.index.intersection(act.index)
        a = act[common].values
        e = (f[common].values - a) / np.where(a == 0, np.nan, a)
        errs += [v for v in e if np.isfinite(v)]
    if not errs:
        return {"mape": None, "bias": None, "worst": None, "folds": 0}
    arr = np.array(errs)
    return {"mape": float(np.mean(np.abs(arr))), "bias": float(np.mean(arr)),
            "worst": float(np.max(np.abs(arr))), "folds": len(errs)}


def sanity_forecasts(monthly: pd.Series, horizon: int = DEFAULT_HORIZON) -> dict:
    """Every model's next `horizon` months, each with its backtest score.

    `monthly` must hold COMPLETE months only: the month in progress would drag
    every model down by however much of it has not happened yet, which is the
    single easiest way to make a forecast look like a collapse."""
    monthly = monthly.dropna().sort_index()
    if len(monthly) < MIN_MONTHS:
        return {"available": False,
                "reason": f"{len(monthly)} complete months of history; {MIN_MONTHS} are needed "
                          "before a seasonal model can say anything.",
                "history": [], "models": []}
    out = []
    for name, fn in MODELS:
        try:
            f, note = fn(monthly, horizon)
        except Exception as e:            # one model failing must not lose the rest
            out.append({"name": name, "error": f"{type(e).__name__}: {e}"[:200]})
            continue
        out.append({"name": name, "note": note,
                    "months": {str(p): (None if not np.isfinite(v) else round(float(v), 2))
                               for p, v in f.items()},
                    "score": _score(monthly, fn)})
    months = [str(p) for p in _future_index(monthly, horizon)]
    stack = np.array([[m["months"].get(k) for k in months]
                      for m in out if m.get("months")], dtype=float)
    median = {k: (None if np.all(np.isnan(stack[:, i])) else round(float(np.nanmedian(stack[:, i])), 2))
              for i, k in enumerate(months)} if len(stack) else {}
    ranked = [m for m in out if (m.get("score") or {}).get("mape") is not None]
    best = min(ranked, key=lambda m: m["score"]["mape"])["name"] if ranked else None
    return {"available": True, "months": months, "models": out, "median": median, "best": best,
            "history": [{"month": str(p), "value": round(float(v), 2)}
                        for p, v in monthly.tail(24).items()]}
