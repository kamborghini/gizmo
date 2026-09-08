"""One place for every knob. Everything downstream reads a Config; nothing
reads the environment, so a backtest and a production run are the same code
with a different Config."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Mapping, Sequence, Tuple

# The target is the workbook's own line: Net Sales = gross - discounts - returns,
# excluding shipping and taxes. Units are carried as an auxiliary target so a
# price change can be told apart from a volume change.
TARGET = "net_sales"
AUX_TARGET = "units"

# M5-style lag set. 365 catches last year's same day; the rest catch the recent level.
LAGS: Tuple[int, ...] = (7, 14, 28, 56, 365)
ROLL_WINDOWS: Tuple[int, ...] = (7, 14, 28, 56)
EWMA_SPANS: Tuple[int, ...] = (7, 28)

# Direct multi-horizon: one model per bucket, with the horizon as a feature and
# every lag shifted by the bucket's LONGEST horizon so no row can see its future.
HORIZON_DAYS = 90
HORIZON_BUCKETS: Tuple[Tuple[int, int], ...] = ((1, 7), (8, 14), (15, 28), (29, 56), (57, 90))

# Expanding-window backtest: five consecutive 28-day windows ending at as_of.
CV_FOLDS = 5
CV_WINDOW_DAYS = 28

# Levels, top down. "bottom" is variant x segment, the grain every other level sums from.
LEVELS: Tuple[str, ...] = ("total", "category", "segment", "product", "variant", "bottom")


@dataclass(frozen=True)
class Config:
    as_of: date
    horizon_days: int = HORIZON_DAYS
    horizon_buckets: Sequence[Tuple[int, int]] = HORIZON_BUCKETS
    lags: Sequence[int] = LAGS
    roll_windows: Sequence[int] = ROLL_WINDOWS
    ewma_spans: Sequence[int] = EWMA_SPANS
    cv_folds: int = CV_FOLDS
    cv_window_days: int = CV_WINDOW_DAYS
    target: str = TARGET
    aux_target: str = AUX_TARGET
    # Order or customer tags -> segment. Anything unmatched is the default.
    segment_tags: Mapping[str, str] = field(default_factory=lambda: {
        "trade": "Trade", "b2b": "Trade", "wholesale": "Trade",
        "wedding": "Weddings", "weddings": "Weddings",
        "venue": "Venues", "venues": "Venues", "hospitality": "Venues",
    })
    default_segment: str = "Retail"
    # Product type -> category when the product map has no type. Regexes on the title.
    category_patterns: Mapping[str, str] = field(default_factory=lambda: {
        r"projector": "Projector", r"gobo|glass": "Gobo", r"holder|lens|frame|mount|cable|bracket": "Accessory",
    })
    default_category: str = "Other"
    scenarios: Sequence[str] = ("Algorithm 1", "Algorithm 2", "Algorithm 3")
    alert_pct: float = 0.10          # |gap| beyond this is an over/underrun
    cash_buffer: float = 10_000.0    # working capital below this is a cash-flow risk
    cold_start_days: int = 56        # a series younger than this leans on its category prior
    min_history_days: int = 400      # enough for lag-365 to exist on most rows
    interval_quantiles: Tuple[float, float] = (0.10, 0.90)
    use_lightgbm: bool = True
    use_catboost: bool = True
    use_nbeats: bool = True
    seed: int = 7

    def buckets_for(self, horizon: int) -> Sequence[Tuple[int, int]]:
        """The buckets needed to cover 1..horizon."""
        return tuple(b for b in self.horizon_buckets if b[0] <= horizon)
