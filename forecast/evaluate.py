"""How good is the forecast, really: `python -m forecast evaluate`.

A rolling-origin evaluation of the monthly panel on a shop's own orders. At
every cut-off the nightly job's own code is run (sanity_forecasts on the
complete months before the cut-off, the big orders before it, the regular
orders' days up to the end of its last month), and everything it says about
the next months is marked against what came in:

- every source and combination, refitted at each cut-off, never shown a month
  after it;
- the panel's own pick (pick_opinions) with the range it would have drawn
  (band_width);
- three baselines any method should beat: the same month last year, last
  month carried forward, and the average of the last twelve months.

Where it differs from a night that really ran:

- The nightly job will not forecast on less than MIN_MONTHS (24) months, and
  its backtest folds start there too, so with about two and a half years of
  history there would be almost nothing to judge. `--first-cut` lowers both
  floors for the replay (20 months by default: with less, "last year,
  adjusted" cannot measure how this year is running against the last). The
  early picks are therefore ranked on fewer and shorter folds than a real
  night's three; the report gives the backtest misses each pick ranked on.
- The record of past nights cannot be replayed (it keeps each method's first
  figure for a month, made whenever that was), so the replay always ranks on
  the backtest, as the nightly does until every method has three closed
  months on its record.

Metrics are on the forecasts, in money: WAPE (total miss over total money,
the headline), MAE, RMSE, bias (total over or under, as a share), MASE (the
miss over the in-sample same-month-last-year miss, so 1.0 is no better than
that), MAPE for comparison with the page, how often the outcome fell inside
the range and how wide the range was. Sources are compared only on the
forecasts every one of them made. A month is forecast from up to `--horizon`
cut-offs, so the forecasts overlap: the report says how many distinct months
they cover, and they are not independent draws.

`--as-before` scores the panel as it was before 19 October 2026 (big orders
as their average month, the range at the plain 80th percentile, and no
Prophet, which it never had), so the change can be measured on the same
history. Measure what ships against it with `--no-prophet`: the nightly
image does not carry Prophet either.

    python -m forecast evaluate --orders orders.json --as-of 2026-10-18 \\
        [--first-cut 20] [--horizon 3] [--csv rows.csv] [--no-prophet] [--as-before]

`orders.json` is a list of orders in the shape the nightly job pulls
(created_at, order_total, and test, cancelled_at and financial_status where
they apply), or {"orders": [...]}.
"""
from __future__ import annotations

import argparse
import json
import math
import warnings
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

PANEL = "The panel's pick"
HISTORY_DAYS = 1830      # what the nightly job pulls by default


@contextmanager
def history_floor(n: int):
    """The panel's minimum history, lowered for a replay and always put back."""
    from . import simple
    old = simple.MIN_MONTHS
    simple.MIN_MONTHS = int(n)
    try:
        yield
    finally:
        simple.MIN_MONTHS = old


@contextmanager
def as_before():
    """The panel's scoring as it was before 19 October 2026: big orders as
    their average month over the last twelve, the range at the plain 80th
    percentile of the backtest's misses. Always put back."""
    from . import simple
    old = simple.big_level, simple._p80
    simple.big_level = lambda b: float(b.astype(float).iloc[-12:].mean()) if len(b) else 0.0
    simple._p80 = lambda misses: float(np.quantile(np.asarray(misses, dtype=float), 0.8))
    try:
        yield
    finally:
        simple.big_level, simple._p80 = old


def _seasonal_naive(y: pd.Series, h: int) -> pd.Series:
    from .simple import _future_index
    idx = _future_index(y, h)
    return pd.Series([y.get(p - 12, np.nan) for p in idx], index=idx, dtype=float)


def _last_month(y: pd.Series, h: int) -> pd.Series:
    from .simple import _future_index
    return pd.Series(float(y.iloc[-1]), index=_future_index(y, h))


def _mean12(y: pd.Series, h: int) -> pd.Series:
    from .simple import _future_index
    return pd.Series(float(y.iloc[-12:].mean()), index=_future_index(y, h))


BASELINES = (("Baseline: same month last year", _seasonal_naive),
             ("Baseline: last month carried forward", _last_month),
             ("Baseline: average of the last 12 months", _mean12))


def series_from_orders(orders: List[dict], as_of: date, history_days: int = HISTORY_DAYS):
    """The three series the nightly job builds, built the same way."""
    from .ingest import daily_cash, monthly_cash
    from .simple import BIG_ORDER
    since = (as_of - timedelta(days=history_days)).replace(day=1)
    monthly = monthly_cash(orders, as_of, since)
    big = monthly_cash(orders, as_of, since, min_total=BIG_ORDER)
    daily_small = daily_cash(orders, as_of, max_total=BIG_ORDER)
    return monthly, big, daily_small


def _scale(train: np.ndarray) -> float:
    """MASE's yardstick: the in-sample miss of the same month last year (of
    last month, before there is a year)."""
    if len(train) > 13:
        return float(np.mean(np.abs(train[12:] - train[:-12])))
    return float(np.mean(np.abs(np.diff(train)))) if len(train) > 1 else float("nan")


def evaluate(monthly: pd.Series, big: Optional[pd.Series] = None, daily_small: Optional[pd.Series] = None,
             first_cut: int = 20, h: int = 3) -> pd.DataFrame:
    """One row per (source, cut-off, month ahead): what it said and what came in.

    `cut` is the number of complete months the panel was given; the months it
    is marked on are the next `h` (fewer at the end of the history)."""
    from .simple import band_width, pick_opinions, sanity_forecasts
    monthly = monthly.dropna().sort_index()
    rows = []
    with history_floor(first_cut), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for k in range(first_cut, len(monthly)):
            train = monthly.iloc[:k]
            end = train.index[-1].to_timestamp(how="end").normalize()
            hh = min(h, len(monthly) - k)
            actual = monthly.iloc[k:k + hh]
            base = {"cut": k, "origin": str(train.index[-1]), "scale": _scale(train.to_numpy(dtype=float))}

            def mark(source, kind, months: Dict[str, Optional[float]], width=None, pick=None):
                for j, (p, a) in enumerate(actual.items()):
                    f = months.get(str(p))
                    if f is None or not math.isfinite(float(f)):
                        continue
                    f = float(f)
                    rows.append({**base, "source": source, "kind": kind, "h": j + 1, "month": str(p),
                                 "actual": float(a), "forecast": f,
                                 "lo": None if width is None else max(0.0, f * (1 - width)),
                                 "hi": None if width is None else f * (1 + width), "pick": pick})

            r = sanity_forecasts(train, horizon=hh,
                                 big=None if big is None else big[big.index <= train.index[-1]],
                                 daily_small=None if daily_small is None else daily_small[daily_small.index <= end])
            for m in r.get("models") or []:
                if not m.get("months"):
                    continue
                scored = (m.get("score") or {}).get("folds")
                mark(m["name"], m.get("kind", "model"), m["months"], band_width(m) if scored else None)
            lead = (pick_opinions(r) or [None])[0]
            if lead is not None:
                n0 = len(rows)
                mark(PANEL, "panel", lead["months"], band_width(lead), pick=lead["name"])
                for row in rows[n0:]:
                    row["ranked_on"] = int((lead.get("score") or {}).get("folds") or 0)
            for name, fn in BASELINES:
                try:
                    f = fn(train, hh)
                except Exception:
                    continue
                mark(name, "baseline", {str(p): v for p, v in f.items()})
    return pd.DataFrame(rows)


def metrics(d: pd.DataFrame) -> Dict[str, float]:
    e = d["forecast"] - d["actual"]
    money = float(d["actual"].sum())
    out = {"n": float(len(d)), "WAPE": float(e.abs().sum() / money) if money else float("nan"),
           "MAE": float(e.abs().mean()), "RMSE": float(math.sqrt((e ** 2).mean())),
           "bias": float(e.sum() / money) if money else float("nan"),
           "MASE": float((e.abs() / d["scale"]).mean()),
           "MAPE": float((e.abs() / d["actual"].where(d["actual"] != 0)).mean())}
    banded = d[d["lo"].notna()]
    out["in range"] = (float(((banded["actual"] >= banded["lo"]) & (banded["actual"] <= banded["hi"])).mean())
                       if len(banded) else float("nan"))
    out["ranged"] = float(len(banded))
    # Half the range's width as a share of the forecast: a range can hold
    # more of the months only by being wider, so the two are read together.
    out["width"] = (float(((banded["hi"] - banded["lo"]) / 2 / banded["forecast"]).mean())
                    if len(banded) else float("nan"))
    out["months"] = float(d["month"].nunique())
    return out


def common(rows: pd.DataFrame) -> tuple:
    """The rows of the sources that answered every (cut-off, month ahead) any
    source answered, and the names of the ones that did not."""
    pairs = rows.groupby(["cut", "h"]).ngroups
    answered = rows.groupby("source").apply(lambda d: d[["cut", "h"]].drop_duplicates().shape[0],
                                            include_groups=False)
    full = answered[answered == pairs].index
    return rows[rows["source"].isin(full)], sorted(set(rows["source"]) - set(full))


def table(rows: pd.DataFrame, by: Optional[str] = None) -> pd.DataFrame:
    keys = ["source", by] if by else "source"
    t = pd.DataFrame({key: metrics(d) for key, d in rows.groupby(keys)}).T
    t.index.names = keys if by else ["source"]
    return t


def _half(month: str) -> str:
    p = pd.Period(month, freq="M")
    return f"{p.year} {'Jan-Jun' if p.month <= 6 else 'Jul-Dec'}"


def report(rows: pd.DataFrame) -> str:
    if rows.empty:
        return "Nothing to evaluate: no cut-off had months after it.\n"
    pct = lambda v: "     -" if not np.isfinite(v) else f"{v * 100:5.1f}%"
    sign = lambda v: "     -" if not np.isfinite(v) else f"{v * 100:+5.1f}%"
    money = lambda v: f"{v:>9,.0f}"
    out = []
    origins = rows.drop_duplicates("cut").sort_values("cut")
    out.append(f"Cut-offs {origins['origin'].iloc[0]} to {origins['origin'].iloc[-1]} "
               f"({len(origins)}), marked on {rows['month'].min()} to {rows['month'].max()}, "
               f"up to {int(rows['h'].max())} months ahead.")

    def full(t, title):
        n, m = int(t["n"].iloc[0]), int(t["months"].iloc[0])
        out.append(f"\n{title} ({n} forecasts of {m} months; lower is better; bias above 0 is too high):\n")
        out.append(f"{'':48} {'WAPE':>6} {'MAE':>9} {'RMSE':>9} {'bias':>6} {'MASE':>5} {'MAPE':>6}"
                   f" {'in range':>13} {'range':>7}")
        for name, r in t.iterrows():
            rng = "" if not np.isfinite(r["in range"]) else f"{int(round(r['in range'] * r['ranged']))} of {int(r['ranged'])}"
            wid = "" if not np.isfinite(r["width"]) else f"+/-{r['width'] * 100:.0f}%"
            out.append(f"{name[:48]:48} {pct(r['WAPE'])} {money(r['MAE'])} {money(r['RMSE'])} "
                       f"{sign(r['bias'])} {r['MASE']:5.2f} {pct(r['MAPE'])} {rng:>13} {wid:>7}")

    def split(d, names, by, label):
        t = table(d, by)
        w, b = t["WAPE"].unstack(by), t["bias"].unstack(by)
        w, b = w.loc[[n for n in names if n in w.index]], b.loc[[n for n in names if n in b.index]]
        out.append(f"\nWAPE (and bias) by {label}:\n")
        out.append(f"{'':48} " + " ".join(f"{str(c):>16}" for c in w.columns))
        for name in w.index:
            out.append(f"{name[:48]:48} " + " ".join(
                f"{pct(w.loc[name, c]) + ' (' + sign(b.loc[name, c]).strip() + ')':>16}" for c in w.columns))

    same, partial = common(rows)
    t = table(same).sort_values("WAPE")
    full(t, "Every source on the same forecasts")
    if partial:
        out.append("\nCould not answer every forecast, so scored on their own only:")
        for name in partial:
            m = metrics(rows[rows["source"] == name])
            out.append(f"  {name[:46]:46} {pct(m['WAPE'])} on {int(m['n'])} forecasts of {int(m['months'])} months")
    d = same.assign(half=same["month"].map(_half))
    split(d, list(t.index), "h", "months ahead")
    split(d, list(t.index), "half", "the half-year marked")
    picks = rows[rows["source"] == PANEL]
    if len(picks):
        # The pick only starts once there are folds to rank on, so it is set
        # against everything else on exactly the forecasts it made.
        on = rows.merge(picks[["cut", "h"]].drop_duplicates(), on=["cut", "h"])
        on, _ = common(on)
        t2 = table(on).sort_values("WAPE")
        full(t2, "The panel's pick against every source on the forecasts it made")
        top = [PANEL] + [n for n in t2.index if n != PANEL][:3]
        d2 = on.assign(half=on["month"].map(_half))
        split(d2, top, "h", "months ahead, the pick and the three closest")
        split(d2, top, "month", "month marked, the pick and the three closest")
        out.append("\nThe panel's pick at each cut-off, and how its months came in:\n")
        for k, dd in picks.groupby("cut"):
            inside = ((dd["actual"] >= dd["lo"]) & (dd["actual"] <= dd["hi"])).sum()
            miss = (dd["forecast"] - dd["actual"]).abs().sum() / dd["actual"].sum()
            out.append(f"  after {dd['origin'].iloc[0]}: {dd['pick'].iloc[0][:44]:44} "
                       f"{pct(miss)} out, {inside} of {len(dd)} inside the range "
                       f"(ranked on {int(dd['ranked_on'].iloc[0])} backtest misses; a real night uses 9)")
        worst = picks.assign(miss=(picks["forecast"] - picks["actual"]) / picks["actual"])
        worst = worst.reindex(worst["miss"].abs().sort_values(ascending=False).index).head(5)
        out.append("\nThe pick's five largest misses:\n")
        for _, r in worst.iterrows():
            out.append(f"  {r['month']} from {r['origin']} ({r['pick'][:40]}): forecast {r['forecast']:,.0f}, "
                       f"came in {r['actual']:,.0f}, {sign(r['miss']).strip()}")
    return "\n".join(out) + "\n"


def load_orders(path: str) -> List[dict]:
    with open(path) as fh:
        data = json.load(fh)
    return data.get("orders", []) if isinstance(data, dict) else data


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m forecast evaluate", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--orders", required=True, help="orders JSON in the shape the nightly job pulls")
    ap.add_argument("--as-of", required=True, help="YYYY-MM-DD, the last day of actuals")
    ap.add_argument("--first-cut", type=int, default=20, help="the fewest complete months a cut-off is given")
    ap.add_argument("--horizon", type=int, default=3, help="months ahead marked at each cut-off")
    ap.add_argument("--history-days", type=int, default=HISTORY_DAYS)
    ap.add_argument("--no-prophet", action="store_true", help="leave out the sources that read the days")
    ap.add_argument("--csv", help="write every marked month here")
    ap.add_argument("--as-before", action="store_true",
                    help="score the panel as it was before 19 October 2026 (no Prophet), to measure the change")
    args = ap.parse_args(argv)
    monthly, big, daily_small = series_from_orders(load_orders(args.orders), date.fromisoformat(args.as_of),
                                                   args.history_days)
    if monthly.empty:
        print("No complete month in the orders file before " + args.as_of + ": nothing to evaluate.")
        return 1
    from contextlib import nullcontext
    with as_before() if args.as_before else nullcontext():
        rows = evaluate(monthly, big, None if (args.no_prophet or args.as_before) else daily_small,
                        first_cut=args.first_cut, h=args.horizon)
    if args.csv:
        rows.to_csv(args.csv, index=False)
    print(f"{len(monthly)} complete months, {monthly.index[0]} to {monthly.index[-1]}.")
    print(report(rows), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
