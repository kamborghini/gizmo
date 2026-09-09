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


# --- statsforecast, when the image carries it -------------------------------
# Measured on this shop's own months before being let in, and NONE of them beat
# "last year x run rate": AutoETS returned a flat 27,725 for every month (it
# found no seasonality in 29 points), AutoARIMA swung 70,707 in October to
# 21,712 in December. They are here because more voices are worth having and
# because the ranking is honest about where they come: they earn their place
# from the backtest or they sit at the bottom of the table where the reader can
# see them lose.
def _sf(model_name: str, label: str):
    def run(y: pd.Series, h: int) -> Tuple[pd.Series, str]:
        import statsforecast.models as M
        m = getattr(M, model_name)(season_length=12)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            out = m.forecast(y=y.values.astype(float), h=h)["mean"]
        return pd.Series(np.asarray(out, dtype=float), index=_future_index(y, h)), label
    run.__name__ = "sf_" + model_name.lower()
    run.__doc__ = f"statsforecast {model_name}: {label}."
    return run


def statsforecast_models() -> List[Tuple[str, object]]:
    """The family, or nothing at all when the package is absent. It is an
    optional dependency: the panel must not fail because an image was built
    without it."""
    try:
        import statsforecast  # noqa: F401
    except Exception:
        return []
    return [
        ("Auto-fitted level, trend and season", _sf("AutoETS", "AutoETS"),
         "Tries every combination of level, trend and season, additive or multiplicative, and "
         "keeps whichever fits your history best. With only a few years it often concludes "
         "there is no season at all, which is why it can return the same figure every month.",
         "Best at: letting the data decide the shape when nobody is sure what it is."),
        ("Auto-fitted ARIMA", _sf("AutoARIMA", "AutoARIMA"),
         "The textbook statistical family: it predicts each month from the months before it and "
         "from its own past mistakes, choosing the form automatically. Powerful on long "
         "histories and unstable on short ones.",
         "Best at: months that depend closely on the months immediately before them."),
        ("Auto-fitted trend and smoothing", _sf("AutoTheta", "AutoTheta"),
         "The Theta method again, with its settings chosen automatically rather than fixed.",
         "Best at: a steady direction of travel, found without being told what to look for."),
        ("Auto-fitted complex smoothing", _sf("AutoCES", "AutoCES"),
         "A newer relative of exponential smoothing, built to cope with seasonal patterns that "
         "change shape from year to year.",
         "Best at: a season whose shape shifts from one year to the next."),
    ]


# name -> (function, what it is in plain words). The blurb is written for
# someone reading a board pack, not for someone who already knows the method:
# what it does, what it assumes, and when it misleads. It reaches the page as
# the hover text on the source's name.
MODELS = (
    ("Last year, adjusted for this year", last_year_times_run_rate,
     "Takes the same month last year and scales it by how this year has been trading against "
     "last. It assumes the shape of your year repeats and that the change in level continues. "
     "It misleads when last year's month was itself unusual.",
     "Best at: a repeating yearly shape whose overall level has moved up or down."),
    ("A typical month, shared out", seasonal_share,
     "Takes an average month from the last year and shares the year out by each month's usual "
     "portion of trade. It assumes a steady business with a repeating season. It misleads when "
     "the level of trading has shifted, because it averages the old level back in.",
     "Best at: a steady business with a strong season and little underlying trend."),
    ("Smoothed level and season", holt_winters_flat,
     "Exponential smoothing: a level that updates as each month arrives, plus a repeating "
     "seasonal pattern, and no trend. A standard method since the 1960s. It needs several years "
     "of history to learn a season properly.",
     "Best at: a level that drifts gradually, with the same season each year."),
    ("Smoothed level, season and trend", holt_winters_trend,
     "The same, but also allowed a trend that flattens off rather than running away. More "
     "responsive when direction changes, and more likely to over-read a short run of good or "
     "bad months.",
     "Best at: a business steadily growing or shrinking underneath its season."),
    ("Trend and smoothing, averaged", theta,
     "The Theta method. It strips the season out, averages a straight-line trend with a simple "
     "smoothing of the same history, then puts the season back. It won the M3 forecasting "
     "competition by being exactly this simple.",
     "Best at: a clear underlying direction with seasonal movement on top of it."),
)


def _median(m: np.ndarray) -> np.ndarray:
    return np.nanmedian(m, axis=0)


def _mean(m: np.ndarray) -> np.ndarray:
    return np.nanmean(m, axis=0)


def _trimmed(m: np.ndarray) -> np.ndarray:
    """Drop the highest and the lowest, average the rest: one wild model
    (AutoARIMA put October at 70,707) cannot then carry the answer."""
    if m.shape[0] < 4:
        return np.nanmedian(m, axis=0)
    out = []
    for col in range(m.shape[1]):
        v = np.sort(m[~np.isnan(m[:, col]), col])
        out.append(np.mean(v[1:-1]) if len(v) >= 3 else (np.mean(v) if len(v) else np.nan))
    return np.array(out)


COMBINERS = (
    ("Average of every source", _mean, "the plain mean of every source above",
     "The straight average of every source above. Averaging several forecasts usually beats "
     "most single ones, because their individual mistakes partly cancel out. It cannot correct "
     "a mistake they all share, which is why it is scored here rather than trusted.",
     "Best at: when no single approach is clearly right for the period ahead."),
    ("Middle of every source", _median, "the middle one, so an outlier cannot carry it",
     "The middle value of all the sources. It ignores how far out the extremes are, so a single "
     "wild forecast cannot pull the answer towards it.",
     "Best at: when one source is prone to extreme answers."),
    ("Average, extremes removed", _trimmed, "highest and lowest dropped, then averaged",
     "Drops the highest and the lowest source, then averages what is left. Keeps most of the "
     "benefit of averaging while stopping one outlier from carrying the answer.",
     "Best at: when most sources agree and one or two are far out."),
)


def _folds(y: pd.Series, folds: int = 3, h: int = 3) -> List[Tuple[int, int]]:
    """Cut-offs with enough history behind them and enough months in front."""
    out = []
    for k in range(folds, 0, -1):
        cut = len(y) - h - k + 1
        if cut >= MIN_MONTHS:
            out.append((cut, h))
    return out


def _errors_to_score(errs: List[float]) -> Dict[str, Optional[float]]:
    if not errs:
        return {"mape": None, "bias": None, "worst": None, "folds": 0}
    arr = np.array(errs, dtype=float)
    return {"mape": float(np.mean(np.abs(arr))), "bias": float(np.mean(arr)),
            "worst": float(np.max(np.abs(arr))), "folds": len(errs)}


def _backtest_all(y: pd.Series, models: List[Tuple[str, object]], folds: int, h: int):
    """Every model on every fold, once, so the models AND the combinations of
    them are scored on exactly the same months."""
    per_model: Dict[str, List[float]] = {m[0]: [] for m in models}
    per_combo: Dict[str, List[float]] = {c[0]: [] for c in COMBINERS}
    for cut, hh in _folds(y, folds, h):
        act = y.iloc[cut:cut + hh]
        preds, order = {}, []
        for name, fn, _blurb, _best in models:
            try:
                f, _ = fn(y.iloc[:cut], hh)
            except Exception:
                continue
            common = f.index.intersection(act.index)
            if len(common) != len(act):
                continue
            preds[name] = f[act.index].values.astype(float)
            order.append(name)
        if not preds:
            continue
        a = act.values.astype(float)
        safe = np.where(a == 0, np.nan, a)
        for name in order:
            per_model[name] += [v for v in (preds[name] - a) / safe if np.isfinite(v)]
        stack = np.vstack([preds[n] for n in order])
        for cname, fn, _n, _b, _ba in COMBINERS:
            per_combo[cname] += [v for v in (fn(stack) - a) / safe if np.isfinite(v)]
    return ({n: _errors_to_score(e) for n, e in per_model.items()},
            {n: _errors_to_score(e) for n, e in per_combo.items()})



MIN_LIVE_MONTHS = 3          # before a track record outranks a backtest


def track_record(results: Optional[List[dict]]) -> Dict[str, Dict[str, float]]:
    """What each source has actually been worth on months it could not see.

    The backtest each run computes is retrospective and forgiving: a model is
    refitted to old months and marked on them. This is the standing record -
    what a source SAID about a month while that month was still ahead, marked
    when it closed. It is the harder test and the one worth trusting, once
    there is enough of it."""
    out: Dict[str, Dict[str, float]] = {}
    for r in results or []:
        for name, rec in (r.get("by_source") or {}).items():
            e = rec.get("error")
            if not isinstance(e, (int, float)) or not np.isfinite(e):
                continue
            d = out.setdefault(name, {"n": 0, "abs": 0.0, "sum": 0.0, "wins": 0})
            d["n"] += 1
            d["abs"] += abs(float(e))
            d["sum"] += float(e)
            if r.get("winner") == name:
                d["wins"] += 1
    for name, d in out.items():
        n = d["n"] or 1
        d["mape"] = d["abs"] / n
        d["bias"] = d["sum"] / n
        d["win_rate"] = d["wins"] / n
    return out


def _live_weights(live: Dict[str, Dict[str, float]], names: List[str]) -> Dict[str, float]:
    """Weight by how right each source has actually been: inverse error,
    normalised. A source with no record gets no weight rather than an average
    one, because pretending to know is worse than saying nothing."""
    w = {}
    for n in names:
        d = live.get(n)
        if not d or d.get("n", 0) < MIN_LIVE_MONTHS:
            continue
        w[n] = 1.0 / max(float(d["mape"]), 0.02)
    total = sum(w.values())
    return {k: v / total for k, v in w.items()} if total > 0 else {}


def sanity_forecasts(monthly: pd.Series, horizon: int = DEFAULT_HORIZON,
                     folds: int = 3, fold_h: int = 3,
                     results: Optional[List[dict]] = None) -> dict:
    """Every source's next `horizon` months, plus combinations of them, each
    carrying the score it earned on this shop's own months.

    `monthly` must hold COMPLETE months only: the month in progress would drag
    every model down by however much of it has not happened yet, which is the
    single easiest way to make a forecast look like a collapse.

    Combinations are rows like any other. They are not assumed to be better -
    an average of forecasts that all lean high leans high - so they are marked
    against the same folds and ranked with everyone else."""
    monthly = monthly.dropna().sort_index()
    if len(monthly) < MIN_MONTHS:
        return {"available": False,
                "reason": f"{len(monthly)} complete months of history; {MIN_MONTHS} are needed "
                          "before a seasonal model can say anything.",
                "history": [], "models": []}

    models = list(MODELS) + statsforecast_models()
    mscore, cscore = _backtest_all(monthly, models, folds, fold_h)

    months = [str(p) for p in _future_index(monthly, horizon)]
    out, live_fc = [], {}
    for name, fn, blurb, best_at in models:
        try:
            f, note = fn(monthly, horizon)
        except Exception as e:          # one source failing must not lose the rest
            out.append({"name": name, "kind": "model", "about": blurb, "best_at": best_at,
                        "error": f"{type(e).__name__}: {e}"[:200],
                        "score": mscore.get(name, _errors_to_score([]))})
            continue
        vals = {str(p): (None if not np.isfinite(v) else round(float(v), 2)) for p, v in f.items()}
        live_fc[name] = [vals.get(k) for k in months]
        out.append({"name": name, "kind": "model", "note": note, "about": blurb,
                    "best_at": best_at, "months": vals,
                    "score": mscore.get(name, _errors_to_score([]))})

    stack, live_names = None, list(live_fc.keys())
    if live_fc:
        stack = np.array([[np.nan if v is None else v for v in live_fc[n]] for n in live_names], dtype=float)
        for cname, fn, note, blurb, best_at in COMBINERS:
            vals = fn(stack)
            out.append({"name": cname, "kind": "combination", "note": note, "about": blurb,
                        "best_at": best_at,
                        "months": {k: (None if not np.isfinite(v) else round(float(v), 2))
                                   for k, v in zip(months, vals)},
                        "score": cscore.get(cname, _errors_to_score([]))})

    # A source weighted by what it has ACTUALLY been worth, month by closed
    # month. It only appears once there is a record to weigh with, and it is
    # scored on the same folds as everything else rather than trusted.
    live = track_record(results)
    lw = _live_weights(live, list(live.keys()))
    if stack is not None and lw:
        idx = {n: i for i, n in enumerate(live_names)}
        usable = {n: w for n, w in lw.items() if n in idx}
        tot = sum(usable.values())
        if tot > 0:
            vals = sum(stack[idx[n]] * (w / tot) for n, w in usable.items())
            out.append({"name": "Weighted by track record", "kind": "combination",
                        "note": "each source weighted by how right it has been",
                        "about": "Weights every source by how close it has actually come on the months "
                                 "that have closed since this started running, not by a backtest. The "
                                 "more months there are, the more this reflects what works for this "
                                 "business rather than what works in general.",
                        "best_at": "Best at: this business specifically, once there is a record of "
                                   "which approach keeps coming closest.",
                        "months": {k: (None if not np.isfinite(v) else round(float(v), 2))
                                   for k, v in zip(months, vals)},
                        "score": {"mape": None, "bias": None, "worst": None, "folds": 0},
                        "weights": {n: round(w / tot, 3) for n, w in usable.items()}})

    # Attach the standing record to each source, and rank on it once there is
    # enough of it: a month a source could not see is worth more than a fold
    # it was refitted to.
    closed = max((int(d.get("n", 0)) for d in live.values()), default=0)
    for entry in out:
        d = live.get(entry["name"])
        if d:
            entry["live"] = {"months": int(d["n"]), "mape": round(d["mape"], 4),
                             "bias": round(d["bias"], 4), "wins": int(d["wins"]),
                             "win_rate": round(d["win_rate"], 3)}

    def rank_key(m):
        if closed >= MIN_LIVE_MONTHS and (m.get("live") or {}).get("mape") is not None:
            return (0, m["live"]["mape"])
        sc = (m.get("score") or {}).get("mape")
        return (1, sc if sc is not None else 9.9)

    ranked = [m for m in out if m.get("months")
              and ((m.get("score") or {}).get("mape") is not None or (m.get("live") or {}).get("mape") is not None)]
    ranked.sort(key=rank_key)
    best = ranked[0]["name"] if ranked else None
    ranked_on = "record" if closed >= MIN_LIVE_MONTHS else "backtest"
    median = ({k: (None if not np.isfinite(v) else round(float(v), 2))
               for k, v in zip(months, _median(stack))} if stack is not None else {})
    return {"available": True, "months": months, "models": out, "median": median, "best": best,
            "ranked_on": ranked_on, "closed_months": closed, "sources": len(live_fc),
            "history": [{"month": str(p), "value": round(float(v), 2)}
                        for p, v in monthly.tail(24).items()]}


def pick_opinions(result: dict, n: int = 3) -> List[dict]:
    """The models worth showing, best on this shop's own history first.

    Ranked by the error each earned in the backtest, not by how sophisticated
    it is. On Projected Image the order comes out simplest-first, and that is
    the point: a model is trusted here because it was right, not because of
    what it is called."""
    scored = [m for m in (result.get("models") or []) if (m.get("score") or {}).get("mape") is not None]
    return sorted(scored, key=lambda m: m["score"]["mape"])[:n]


def daily_frame(model: dict, as_of, profile=None) -> "pd.DataFrame":
    """One model's months spread over their days, with a band.

    The variance engine reads a daily line, so a monthly forecast has to
    become one. The spread sums back to the month exactly. The band is the
    model's OWN measured error on this shop's history rather than a number
    chosen to look confident: if it was typically 29% out, the band is 29%
    wide, and December's disagreement between models is a separate signal
    shown beside it."""
    from .cashflow import DayProfile, daily_from_monthly
    months = [(k, v) for k, v in (model.get("months") or {}).items() if v is not None]
    if not months:
        return pd.DataFrame(columns=["date", "p10", "p50", "p90"])
    mdf = pd.DataFrame({"month": [pd.Period(k, freq="M").to_timestamp() for k, _ in months],
                        "p50": [float(v) for _, v in months]}).sort_values("month")
    spread = daily_from_monthly(mdf, profile or DayProfile.uniform(), columns=("p50",))
    spread = spread.rename(columns={"p50_target": "p50"})
    err = float((model.get("score") or {}).get("mape") or 0.3)
    err = min(max(err, 0.10), 0.75)
    spread["p10"] = spread["p50"] * (1 - err)
    spread["p90"] = spread["p50"] * (1 + err)
    start = pd.Timestamp(as_of) + pd.Timedelta(days=1)
    return spread[spread["date"] >= start][["date", "p10", "p50", "p90"]].reset_index(drop=True)
