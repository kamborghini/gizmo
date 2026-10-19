"""Prophet on the regular orders, day by day, where it is installed.

Prophet (Meta's forecasting library) fits a trend that can bend, a yearly
season and a weekly pattern to a DAILY series. It was measured on the shop's
own months with a rolling-origin backtest that gave every model only what
existed at each cut-off (`python -m forecast evaluate` repeats it):

- Fitted to the whole month's money it was far behind the plain methods: the
  big quoted orders arrive when they arrive, and a model of rhythm reads them
  as rhythm. So it is never offered that way.
- Fitted to the orders under BIG_ORDER by day, with big orders added back as
  big_level, it came closest of the methods measured, and the average of it
  with "Big orders counted apart" came next. Both leads were smaller than the
  noise on the months there were to judge them on, and the range drawn
  around them held fewer of the months that came in than the range around
  "Big orders counted apart".
- Tuned month by month on each cut-off's own past (changepoint and season
  strengths, England's bank holidays and a Christmas shutdown, multiplicative
  seasons), it did no better than its defaults, so these are its defaults,
  with the yearly season always on.

So the two methods exist, are tested, and can be measured again at any time,
but the nightly image does not carry Prophet (see requirements-prophet.in for
switching them on). Where it is installed they are scored and ranked like
every other method, never wired in; where it is absent, the panel is exactly
what it was, and where it fails, its two rows say why and are not ranked.
"""
from __future__ import annotations

import logging
import warnings
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

PROPHET_NAME = "Daily trend and season, big orders apart"
HYBRID_NAME = "Last year and daily trend, averaged"

# Prophet's own defaults, except the yearly season, which its "auto" turns off
# below two years of days (the backtest's early folds have less than that), and
# no sampled intervals: the panel draws every method's range from its own
# backtest misses (simple.band_width), Prophet's included.
SETTINGS = dict(changepoint_prior_scale=0.05, seasonality_mode="additive",
                seasonality_prior_scale=10.0, yearly_seasonality=10,
                weekly_seasonality=True, daily_seasonality=False,
                uncertainty_samples=0)

MIN_DAYS = 365           # a year of days, or there is no season to fit

PROPHET_ABOUT = (
    "It forecasts the orders under £2,000 day by day with Prophet, a method built by Meta's "
    "data scientists for business figures with a weekly rhythm and a yearly season: it fits a "
    "trend that can bend where trading changed, the season and the week, then adds the days up "
    "into months. Big orders are added as a typical month of them over the last year. It misleads "
    "when trading turns sharply in the last few months, because it only lets the trend bend in "
    "the earlier part of the history.")
PROPHET_BEST_AT = "Best at: a steady weekly and yearly pattern under a trend that has shifted over time."
HYBRID_ABOUT = (
    "It averages two forecasts of the orders under £2,000: last year's same month, scaled by "
    "how this year is trading, and the day by day trend and season. Big orders are added as a "
    "typical month of them over the last year. Two methods that go wrong in different ways can "
    "partly cancel each other out. It misleads when both lean the same way.")
HYBRID_BEST_AT = "Best at: steady months, when neither method on its own has clearly earned the lead."


def _prophet():
    """The class, with its chatter quietened: cmdstanpy logs every fit, and
    Prophet logs that the plotting library it never uses here is absent."""
    logging.getLogger("prophet.plot").setLevel(logging.CRITICAL)   # its "failed" is an ERROR
    from prophet import Prophet
    # cmdstanpy sets its own level the first time it is asked for its logger
    # when nothing above it has a handler, so ask first, then quieten it.
    from cmdstanpy.utils import get_logger
    get_logger()
    for name in ("cmdstanpy", "prophet", "prophet.models"):
        logging.getLogger(name).setLevel(logging.ERROR)
    return Prophet


def available() -> bool:
    try:
        _prophet()
    except Exception:
        return False
    return True


def regular_months(daily_small: pd.Series, first: pd.Period, through: pd.Period, h: int) -> pd.Series:
    """Prophet fitted to the regular orders' days from the start of `first` to
    the end of `through`, its daily forecast summed into the `h` months after.

    Nothing after `through` is read, so a backtest fold cut at `through`
    cannot see past itself, and the month in progress never reaches it."""
    Prophet = _prophet()
    end = through.to_timestamp(how="end").normalize()
    s = daily_small[(daily_small.index >= first.start_time) & (daily_small.index <= end)].astype(float)
    if len(s) < MIN_DAYS:
        raise ValueError(f"{len(s)} days of regular orders; {MIN_DAYS} are needed")
    if s.index[-1] < end:
        raise ValueError(f"the regular orders stop on {s.index[-1].date()}, before {end.date()}")
    months = pd.period_range(through + 1, periods=h, freq="M")
    days = pd.date_range(months[0].start_time, months[-1].end_time.normalize(), freq="D")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = Prophet(**SETTINGS)
        model.fit(pd.DataFrame({"ds": s.index, "y": s.values}))
        yhat = model.predict(pd.DataFrame({"ds": days}))["yhat"].to_numpy(dtype=float)
    per = pd.Series(yhat, index=days).groupby(days.to_period("M")).sum()
    # A month cannot take negative money, however low a quiet stretch drags the line.
    return per.reindex(months).clip(lower=0.0).astype(float)


def prophet_models(big: pd.Series, daily_small: pd.Series) -> List[Tuple[str, Callable, str, str]]:
    """The two sources, or nothing at all when Prophet is absent. Both share
    one fit per cut-off: the backtest asks each the same question."""
    if not available():
        return []
    from .simple import BIG_ORDER, big_level, big_orders_apart
    fits: Dict[tuple, pd.Series] = {}

    def regular(y: pd.Series, h: int) -> pd.Series:
        key = (str(y.index[0]), str(y.index[-1]), h)
        if key not in fits:
            fits[key] = regular_months(daily_small, y.index[0], y.index[-1], h)
        return fits[key]

    def by_day(y: pd.Series, h: int) -> Tuple[pd.Series, str]:
        level = big_level(big.reindex(y.index).fillna(0.0))
        return regular(y, h) + level, \
            f"orders under {BIG_ORDER:,.0f} by day; big orders {level:,.0f} a month"

    def averaged(y: pd.Series, h: int) -> Tuple[pd.Series, str]:
        # Both carry the same big-order month, so averaging the totals is
        # averaging the two forecasts of the regular orders. A month either
        # cannot give is a month this cannot give.
        last_year, _ = big_orders_apart(y, h, big)
        daily, _ = by_day(y, h)
        return (last_year + daily) / 2, "last year and the daily trend, averaged; big orders apart"

    by_day.__name__, averaged.__name__ = "prophet_by_day", "prophet_averaged"
    return [(PROPHET_NAME, by_day, PROPHET_ABOUT, PROPHET_BEST_AT),
            (HYBRID_NAME, averaged, HYBRID_ABOUT, HYBRID_BEST_AT)]


def self_check() -> None:
    """Fit once on two invented years, so an image that carries Prophet can
    prove its compiled model actually runs there. The nightly image does not
    carry it; switching it on adds `python -m forecast.prophet_source` to the
    image check in .github/workflows/tests.yml (see requirements-prophet.in)."""
    days = pd.date_range("2024-01-01", "2025-12-31", freq="D")
    rng = np.random.default_rng(0)
    y = pd.Series(800 + 200 * np.sin(2 * np.pi * days.dayofyear / 365.25) + rng.normal(0, 50, len(days)), index=days)
    out = regular_months(y, pd.Period("2024-01", "M"), pd.Period("2025-12", "M"), 2)
    if not (len(out) == 2 and np.all(np.isfinite(out.values)) and 10_000 < float(out.iloc[0]) < 40_000):
        raise RuntimeError(f"Prophet ran but its forecast is not believable: {out.to_dict()}")
    print("prophet ok:", {str(k): round(float(v)) for k, v in out.items()})


if __name__ == "__main__":
    self_check()
