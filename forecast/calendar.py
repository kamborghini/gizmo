"""Known-in-advance calendar signal for a UK retailer: weekdays, bank
holidays, the pre-Christmas trade window, Black Friday, paydays. Everything
here is a pure function of the date, so it is safe at any horizon."""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd


def easter(year: int) -> date:
    """Anonymous Gregorian algorithm."""
    a = year % 19; b, c = divmod(year, 100); d, e = divmod(b, 4); f = (b + 8) // 25
    g = (b - f + 1) // 3; h = (19 * a + b - d - g + 15) % 30; i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7; m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _observed(d: date) -> date:
    # A holiday on a weekend is taken on the next weekday.
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _last_monday(year: int, month: int) -> date:
    d = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
    while d.weekday() != 0:
        d -= timedelta(days=1)
    return d


def _first_monday(year: int, month: int) -> date:
    d = date(year, month, 1)
    while d.weekday() != 0:
        d += timedelta(days=1)
    return d


@lru_cache(maxsize=None)
def uk_bank_holidays(year: int) -> frozenset:
    e = easter(year)
    days = {
        _observed(date(year, 1, 1)), e - timedelta(days=2), e + timedelta(days=1),
        _first_monday(year, 5), _last_monday(year, 5), _last_monday(year, 8),
    }
    xmas, boxing = _observed(date(year, 12, 25)), _observed(date(year, 12, 26))
    if boxing == xmas:
        boxing = _observed(boxing + timedelta(days=1))
    days.update({xmas, boxing})
    return frozenset(days)


def black_friday(year: int) -> date:
    d = date(year, 11, 1)
    fridays = [d + timedelta(days=i) for i in range(30) if (d + timedelta(days=i)).weekday() == 4]
    return fridays[3]


def calendar_frame(dates: pd.DatetimeIndex) -> pd.DataFrame:
    """One row per date with the calendar features. Deterministic and cheap,
    so it is rebuilt rather than cached."""
    idx = pd.DatetimeIndex(dates).normalize().unique().sort_values()
    years = range(idx.min().year - 1, idx.max().year + 2)
    hols = sorted({h for y in years for h in uk_bank_holidays(y)})
    hol_idx = pd.DatetimeIndex(hols)
    bf = {black_friday(y) for y in years}
    out = pd.DataFrame(index=idx)
    out["dow"] = idx.dayofweek
    out["dom"] = idx.day
    out["month"] = idx.month
    out["weekofyear"] = idx.isocalendar().week.values.astype(int)
    out["is_weekend"] = (idx.dayofweek >= 5).astype(int)
    out["is_holiday"] = idx.isin(hol_idx).astype(int)
    # distance to the nearest holiday either side, capped: a lead-up and a hangover
    pos = np.searchsorted(hol_idx.values, idx.values)
    nxt = hol_idx.values[np.minimum(pos, len(hol_idx) - 1)]
    prv = hol_idx.values[np.maximum(pos - 1, 0)]
    out["days_to_holiday"] = np.minimum((nxt - idx.values).astype("timedelta64[D]").astype(int).clip(0), 14)
    out["days_since_holiday"] = np.minimum((idx.values - prv).astype("timedelta64[D]").astype(int).clip(0), 14)
    bf_days = pd.DatetimeIndex(sorted(bf))
    d_bf = np.array([min(abs((pd.Timestamp(d) - b).days) for b in bf_days) for d in idx])
    out["is_black_friday_week"] = (d_bf <= 3).astype(int)
    out["is_jan_sale"] = ((idx.month == 1) & (idx.day >= 2) & (idx.day <= 14)).astype(int)
    # the trade lull between mid December and the first working week of January
    out["is_year_end_lull"] = (((idx.month == 12) & (idx.day >= 15)) | ((idx.month == 1) & (idx.day <= 5))).astype(int)
    # payday window: the last working day of the month and the three days after
    month_end = idx + pd.offsets.MonthEnd(0)
    out["is_payday_window"] = ((month_end - idx).days <= 1).astype(int) | (idx.day <= 3).astype(int)
    # smooth annual seasonality for models that like it continuous
    doy = idx.dayofyear.values
    out["sin_year"] = np.sin(2 * np.pi * doy / 365.25)
    out["cos_year"] = np.cos(2 * np.pi * doy / 365.25)
    out["sin_week"] = np.sin(2 * np.pi * idx.dayofweek / 7)
    out["cos_week"] = np.cos(2 * np.pi * idx.dayofweek / 7)
    return out
