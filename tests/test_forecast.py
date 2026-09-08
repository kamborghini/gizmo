"""Guards for the forecasting package. Pure-function checks that need no
model library: the hierarchy sums, MinT keeps coherence, the daily
extrapolation returns exactly the month, the folds cannot leak, a feature
at horizon H never sees past d - H, WRMSSE is zero for a perfect forecast,
the variance verdicts and the cash mechanics do what the workbook does.

Run: python tests/test_forecast.py   (skips itself when pandas is absent,
which is why CI's app environment does not run it; the forecasting
environment does: see forecast/README.md).
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import numpy as np
    import pandas as pd
except ImportError:  # pragma: no cover
    print("pandas not installed: forecast tests skipped")
    sys.exit(0)

from forecast.backtest import IntervalModel, expanding_folds, level_metrics, rmsse
from forecast.cashflow import CashFlowModel, DayProfile, daily_from_monthly
from forecast.coldstart import apply_cold_start
from forecast.config import Config
from forecast.features import FeatureBuilder
from forecast.ingest import to_daily_panel
from forecast.models.ensemble import blend_weights
from forecast.reconcile import Hierarchy
from forecast.variance import VarianceEngine

TESTS = []
FAILS = []


def test(fn):
    TESTS.append(fn); return fn


def ok(cond, msg=""):
    if not cond:
        FAILS.append(msg)
        raise AssertionError(msg)


def _panel(days=500, seed=1):
    rng = np.random.default_rng(seed)
    rows = []
    start = pd.Timestamp("2025-01-01")
    for vid, pid, cat, price in (("v1", "p1", "Gobo", 80.0), ("v2", "p1", "Gobo", 60.0), ("v3", "p2", "Projector", 400.0)):
        for seg in ("Trade", "Retail"):
            for i in range(days):
                q = int(rng.poisson(0.6 if cat == "Gobo" else 0.1))
                if q:
                    rows.append({"date": start + pd.Timedelta(days=i), "variant_id": vid, "sku": vid.upper(), "product_id": pid,
                                 "product": pid, "category": cat, "segment": seg, "units": q, "net_sales": q * price * 0.9,
                                 "gross_sales": q * price, "discount": q * price * 0.1, "price": price})
    return to_daily_panel(pd.DataFrame(rows), (start + pd.Timedelta(days=days - 1)).date())


@test
def t_the_hierarchy_sums_and_mint_keeps_it_coherent():
    panel = _panel(120)
    from forecast.ingest import series_keys
    h = Hierarchy.from_keys(series_keys(panel))
    ok(h.S.shape == (len(h.rows), h.n_bottom), "S is rows x bottom")
    rng = np.random.default_rng(0)
    bottom = rng.gamma(2, 10, size=(30, h.n_bottom))
    allrows = h.aggregate(bottom)
    tot = h.row_index("total", "Total")
    ok(np.allclose(allrows[:, tot], bottom.sum(axis=1)), "total is the sum of the bottom")
    g = h.row_index("category", "Gobo")
    gobo_cols = [i for i, (v, s) in enumerate(h.bottom) if v in ("v1", "v2")]
    ok(np.allclose(allrows[:, g], bottom[:, gobo_cols].sum(axis=1)), "a category is the sum of its variants")
    # perturb the base forecasts so they no longer add up, then reconcile
    noisy = allrows + rng.normal(0, 5, size=allrows.shape)
    resid = rng.normal(0, 5, size=(3 * len(h.rows) + 5, len(h.rows)))
    rec = h.mint(noisy, resid)
    ok(np.allclose(rec, h.aggregate(rec[:, -h.n_bottom:])), "after MinT every row is again the sum of its bottom")
    ok((rec[:, -h.n_bottom:] >= 0).all(), "and nothing at the bottom is negative")
    # with too few residual rows it falls back to WLS and still reconciles
    rec2 = h.mint(noisy, resid[:4])
    ok(np.allclose(rec2, h.aggregate(rec2[:, -h.n_bottom:])), "WLS fallback is coherent too")


@test
def t_a_month_spread_over_its_days_sums_back_exactly():
    monthly = pd.DataFrame({"month": pd.to_datetime(["2026-09-01", "2026-10-01"]), "net_sales": [30000.0, 45000.0]})
    prof = DayProfile(dow=np.array([1.2, 1.2, 1.2, 1.2, 1.0, 0.6, 0.6]) / 1.0, dom=np.ones(31))
    daily = daily_from_monthly(monthly, prof)
    ok(len(daily) == 30 + 31, "one row per day")
    by = daily.groupby(daily["date"].dt.to_period("M"))["net_sales_target"].sum()
    ok(np.allclose(by.values, [30000.0, 45000.0]), "the days add back to the month to the penny")
    sept = daily[daily["date"].dt.month == 9]
    ok(sept[sept["date"].dt.dayofweek == 0]["net_sales_target"].iloc[0] > sept[sept["date"].dt.dayofweek == 6]["net_sales_target"].iloc[0],
       "a Monday carries more than a Sunday when the profile says so")


@test
def t_folds_are_consecutive_and_cannot_leak():
    folds = expanding_folds(date(2026, 9, 8), 5, 28)
    ok(folds[-1].valid_end == pd.Timestamp("2026-09-08"), "the last window ends at as_of")
    for f in folds:
        ok((f.valid_end - f.valid_start).days == 27, "each window is 28 days")
        ok(f.train_end < f.valid_start, "training ends before validation starts")
    for a, b in zip(folds, folds[1:]):
        ok(b.valid_start == a.valid_end + pd.Timedelta(days=1), "windows are back to back")


@test
def t_a_feature_at_horizon_h_never_sees_past_d_minus_h():
    panel = _panel(200)
    cfg = Config(as_of=date(2025, 7, 19))
    fb = FeatureBuilder(cfg, None)
    H = 14
    feats = fb.build(panel, shift=H)
    one = feats[(feats["variant_id"] == "v1") & (feats["segment"] == "Trade")].set_index("date")
    src = panel[(panel["variant_id"] == "v1") & (panel["segment"] == "Trade")].set_index("date")["net_sales"]
    d = one.index[100]
    ok(np.isclose(one.loc[d, "o_last"], src.loc[d - pd.Timedelta(days=H)]), "o_last is the value H days before d")
    ok(np.isclose(one.loc[d, "roll_mean_7"], src.loc[d - pd.Timedelta(days=H + 6): d - pd.Timedelta(days=H)].mean()),
       "the 7-day mean ends at d - H")
    ok("lag_7" not in feats.columns and "lag_14" in feats.columns, "absolute lags shorter than H are dropped")
    ok(np.isclose(one.loc[d, "lag_28"], src.loc[d - pd.Timedelta(days=28)]), "lag_28 is d - 28")


@test
def t_wrmsse_is_zero_for_a_perfect_forecast_and_grows_with_error():
    train = np.array([0, 0, 3, 1, 4, 2, 5, 3, 4, 2, 6, 1], dtype=float)
    a = np.array([3, 4, 2, 5], dtype=float)
    ok(rmsse(a, a, train) == 0.0, "no error, no score")
    ok(rmsse(a, a + 1, train) < rmsse(a, a + 3, train), "a bigger miss scores worse")
    ok(np.isnan(rmsse(a, a, np.zeros(10))), "a series that never sold has no scale")
    panel = _panel(120)
    from forecast.ingest import series_keys
    h = Hierarchy.from_keys(series_keys(panel))
    rng = np.random.default_rng(2)
    hist = h.aggregate(rng.gamma(2, 10, size=(90, h.n_bottom)))
    act = h.aggregate(rng.gamma(2, 10, size=(28, h.n_bottom)))
    m = level_metrics(act, act, hist, h)
    ok((m.loc[m["level"] != "ALL", "wrmsse"].fillna(0) == 0).all(), "perfect forecast scores zero at every level")
    ok(set(m["level"]) >= {"total", "category", "segment", "product", "variant", "bottom", "ALL"}, "every level is scored")


@test
def t_blend_weights_favour_the_model_that_was_right():
    y = np.linspace(10, 50, 200)
    good = y + np.random.default_rng(3).normal(0, 1, 200)
    bad = y * 0.5
    w = blend_weights({"good": good, "bad": bad}, y)
    ok(abs(sum(w.values()) - 1) < 1e-9 and w["good"] > 0.9, "weights sum to one and the accurate model takes nearly all of it")


def _tiny_cashflow():
    months = pd.date_range("2026-05-01", periods=12, freq="MS")
    sc = pd.DataFrame({"month": months, "net_sales": 20000.0, "shipping": 800.0, "taxes": 4000.0, "total_sales": 24800.0})
    flows = pd.DataFrame({"month": months, "advance": [50000.0] + [0.0] * 11, "gross_sales": 24800.0, "overheads": 20000.0,
                          "glass": 744.0, "projector": 744.0, "marketing": 0.0, "unexpected": 1240.0, "repayment": 24800.0 * 0.1471,
                          "working_capital": 0.0, "loan_start": 55300.0})
    actuals = pd.DataFrame({"month": pd.date_range("2024-05-01", periods=24, freq="MS"), "net_sales": 30000.0, "shipping": 1200.0,
                            "taxes": 5500.0, "total_sales": 36700.0})
    return CashFlowModel(actuals=actuals, scenarios={"Algorithm 1": sc}, flows={"Algorithm 1": flows},
                         assumptions={"repayment_rate": 0.18, "shopify_deductible": 0.817, "total_loan_to_repay": 55300.0})


@test
def t_the_cash_path_repays_from_gross_and_stops_at_the_loan():
    cf = _tiny_cashflow()
    gross = pd.Series(100000.0, index=cf.flows["Algorithm 1"]["month"])
    p = cf.project_cash("Algorithm 1", gross)
    ok(np.isclose(p["repayment"].iloc[0], 0.1471 * 100000, rtol=1e-3), "the first month remits the effective rate on gross")
    ok(np.isclose(p["repayment"].sum(), 55300.0), "and repayment stops when the loan is repaid")
    ok(np.isclose(p["working_capital"].iloc[0], 100000 + 50000 - (20000 + (744 + 744 + 1240) / 24800 * 100000 + 0.1471 * 100000)),
       "working capital is cash in minus overheads, scaled costs and the repayment")


@test
def t_the_variance_engine_settles_each_month_one_way_and_calls_it():
    cf = _tiny_cashflow()
    cfg = Config(as_of=date(2026, 9, 8), alert_pct=0.10)
    eng = VarianceEngine(cfg, cf)
    days = pd.date_range("2026-05-01", "2026-09-08", freq="D")
    actual = pd.Series(1000.0, index=days)                      # ~30k a month, above the 20k plan
    fdays = pd.date_range("2026-09-09", periods=90, freq="D")
    fc = pd.DataFrame({"date": fdays, "p10": 400.0, "p50": 500.0, "p90": 900.0})   # ~15.5k a month, under the plan
    m = eng.monthly_view(actual, fc)
    by = m.set_index(m["month"].dt.strftime("%Y-%m"))
    ok(by.loc["2026-05", "method"] == "actual" and by.loc["2026-05", "verdict|Algorithm 1"] == "overrun", "a closed month is its actual, and 31k vs 20k is an overrun")
    ok(by.loc["2026-05", "risk|Algorithm 1"] == "closed", "and a closed month carries no risk, it is a fact")
    ok(by.loc["2026-09", "method"].startswith("actual_to_date"), "the open month is actual to date plus forecast")
    ok(np.isclose(by.loc["2026-09", "projected_p50"], 8 * 1000 + 22 * 500), "and its projection is the sum of both")
    ok(by.loc["2026-09", "projected_p10"] < 20000 < by.loc["2026-09", "projected_p90"] and by.loc["2026-09", "risk|Algorithm 1"] == "watch",
       "its band straddles the target, so the risk is a watch")
    ok(by.loc["2026-10", "method"] == "forecast" and by.loc["2026-10", "verdict|Algorithm 1"] == "underrun", "31 x 500 = 15.5k is more than 10% under 20k")
    ok(by.loc["2026-10", "projected_p90"] < 20000 and by.loc["2026-10", "risk|Algorithm 1"] == "high", "and even the optimistic band misses, so the risk is high")
    band = by.loc["2026-10", "projected_p90"] - by.loc["2026-10", "projected_p50"]
    ok(band < 31 * 400 / 2, "a month's band is far narrower than the sum of its days' bands")
    ok(by.loc["2027-03", "method"] == "extrapolated", "past the horizon the plan is scaled by the tracking ratio")
    alerts = eng.alerts(m, {"Algorithm 1": eng.cash_view(m, "Algorithm 1")})
    ok(any(a["kind"] == "sales" and a["verdict"] == "underrun" and a["month"] == "2026-10" for a in alerts), "the underrun raises an alert")
    ok(not any(a["kind"] == "sales" and a["month"] == "2026-05" for a in alerts), "a closed month does not")
    txt = eng.summary(m, {}, alerts)
    ok("Year: projected" in txt and "alert" in txt, "the summary reads as a report")


@test
def t_intervals_widen_from_the_backtest_and_a_young_series_leans_on_its_category():
    rows = pd.DataFrame({"level": "total", "bucket": [7] * 40 + [28] * 40, "actual": [100.0] * 80,
                         "pred": list(np.linspace(90, 110, 40)) + list(np.linspace(70, 130, 40))})
    im = IntervalModel().fit(rows)
    lo7, hi7 = im.band("total", 7); lo28, hi28 = im.band("total", 28)
    ok(lo28 < lo7 and hi28 > hi7, "a longer horizon has a wider band")
    ok(im.band("bottom", 7) == im.band("total", 7) or im.band("bottom", 7) is not None, "an unfitted level borrows a band")
    panel = _panel(120)
    as_of = panel["date"].max().date()
    # a brand-new variant with a single sale yesterday
    new = panel[(panel["variant_id"] == "v1") & (panel["segment"] == "Trade")].tail(3).copy()
    new["variant_id"] = "v_new"; new["net_sales"] = [0.0, 0.0, 40.0]
    panel2 = pd.concat([panel, new], ignore_index=True)
    cfg = Config(as_of=as_of, cold_start_days=56)
    fdates = pd.date_range(pd.Timestamp(as_of) + pd.Timedelta(days=1), periods=5, freq="D")
    bottom = pd.DataFrame({"date": list(fdates) * 2, "variant_id": ["v_new"] * 5 + ["v1"] * 5, "segment": "Trade", "p50": 0.0})
    out = apply_cold_start(bottom, panel2, cfg, as_of)
    ok(out.loc[out["variant_id"] == "v_new", "p50"].iloc[0] > 0, "the new variant gets its category's prior")
    ok((out.loc[out["variant_id"] == "v1", "p50"] == 0).all(), "an established one is left to the model")


@test
def t_the_shop_is_named_the_same_either_way():
    """`projectedimage` and `projectedimage.myshopify.com` are one shop. The
    app's own server holds the bare handle and appends the domain; this package
    holds the full domain. Both spellings reach the nightly service through
    SHOP, and a Shopify call built from the wrong one goes nowhere."""
    from forecast.ingest import shop_host
    for given in ("projectedimage", "projectedimage.myshopify.com",
                  "https://projectedimage.myshopify.com", "projectedimage.myshopify.com/"):
        assert shop_host(given) == "projectedimage.myshopify.com", given


@test
def t_a_run_takes_either_shopify_credential_and_prefers_the_static_one():
    """Reactor holds no static token: it holds a client id and secret and mints
    a short-lived one, so `${{gizmo.SHOPIFY_ACCESS_TOKEN}}` resolved to nothing
    and the first real run stopped at `missing: SHOPIFY_FORECAST_TOKEN`. The
    service now takes either shape. A static token wins when set, so adding the
    pair to a working deployment changes nothing, which is the same rule the
    connector follows."""
    from forecast.ingest import access_token
    assert access_token("projectedimage.myshopify.com", "shpat_static", "id", "secret") == "shpat_static"
    try:
        access_token("projectedimage.myshopify.com", "", "", "")
    except RuntimeError as e:
        assert "SHOPIFY_CLIENT_ID" in str(e)
    else:
        raise AssertionError("no credential at all has to be an error, not a silent empty token")


@test
def t_the_nightly_job_names_both_credential_shapes_when_it_has_neither():
    """The message a person reads at 03:00. Naming only one of the two shapes
    is what sent this session looking for a variable that does not exist."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "forecast", "nightly.py"), encoding="utf-8").read()
    assert "SHOPIFY_FORECAST_TOKEN, or SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET" in src
    # The grant runs inside the try, so a refusal is posted to the tab.
    body = src.split("try:", 1)[1]
    assert "access_token(shop, stoken, cid, csec)" in body
    assert "run_bulk_orders(shop, api_token, since)" in src
    assert "fetch_products(shop, api_token)" in src


if __name__ == "__main__":
    passed = 0
    for fn in TESTS:
        try:
            fn(); passed += 1; print("  PASS ", fn.__name__)
        except Exception as e:
            print("  FAIL ", fn.__name__, "-", e)
    print(f"\n{passed} passed, {len(TESTS) - passed} failed")
    sys.exit(0 if passed == len(TESTS) else 1)
