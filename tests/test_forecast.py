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
    # The plan in cash in: total_sales is what the forecast is compared with.
    sc = pd.DataFrame({"month": months, "net_sales": 16200.0, "shipping": 600.0, "taxes": 3200.0, "total_sales": 20000.0})
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
    ok(by.loc["2026-10", "target|Algorithm 1"] == 20000.0,
       "the plan is its cash-in line (Total Sales), the forecast's own money, not its 16,200 of net sales")
    cash = eng.cash_view(m, "Algorithm 1").set_index("month")
    ok(np.isclose(cash.loc[pd.Timestamp("2026-10-01"), "gross_sales"], by.loc["2026-10", "projected_p50"]),
       "the cash path takes the forecast as the cash in it already is, not grossed up a second time")
    # The per-product model forecasts NET sales: it is compared with the
    # plan's net line and put into cash in for the cash path, as before.
    net = VarianceEngine(cfg, cf, money="net")
    mn = net.monthly_view(actual, fc)
    bn = mn.set_index(mn["month"].dt.strftime("%Y-%m"))
    ok(bn.loc["2026-10", "target|Algorithm 1"] == 16200.0, "a net forecast meets the plan's net line")
    r = cf.sales_ratios()
    cn = net.cash_view(mn, "Algorithm 1").set_index("month")
    ok(np.isclose(cn.loc[pd.Timestamp("2026-10-01"), "gross_sales"],
                  bn.loc["2026-10", "projected_p50"] * (1 + r["shipping"] + r["taxes"])),
       "and is put into cash in for the cash path")
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
def t_a_shop_that_is_not_a_shopify_store_is_refused():
    """shop_host kept anything with a dot in it, so a mistyped SHOP such as
    `example.com/x` or `user@host` became the address the job posted to,
    carrying its token (8 Sept second pass). Only a myshopify.com store, or a
    bare handle that becomes one, is ever an address."""
    from forecast.ingest import shop_host
    for given in ("example.com", "evil.com/projectedimage.myshopify.com", "user@projectedimage.myshopify.com",
                  "projectedimage.myshopify.com.evil.com", "projectedimage.myshopify.com:8443",
                  "https://projectedimage.myshopify.com/admin", "", "  ", "-bad.myshopify.com"):
        try:
            got = shop_host(given)
        except ValueError:
            continue
        raise AssertionError("%r became the address %r" % (given, got))


@test
def t_the_job_reads_the_store_through_reactor_and_holds_no_shopify_secret():
    """The job used to take Reactor's client id and secret and mint its own
    Admin API token. That secret also signs every webhook Reactor trusts, so
    a copy on this service was a way to forge a shop/redact and erase
    Reactor's stores (the audit's R-C1). The job now asks Reactor, with the
    FORECAST_INGEST_TOKEN it already holds, and the secret is never read:
    a service that still has it logs that it should go, and it is not
    enough on its own to run."""
    import io, json as _json, logging, urllib.error
    import forecast.ingest as ing
    import forecast.nightly as nightly
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "forecast", "ingest.py"), encoding="utf-8").read()
    assert "client_credentials" not in src and not hasattr(ing, "access_token"), \
        "no path mints a token from the app's secret"
    # ReactorStore: the hook, the token in its header, the op in the body.
    seen = []

    class _Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake(req, timeout=None):
        seen.append((req.full_url, dict(req.header_items()), _json.loads(req.data)))
        return _Resp(_json.dumps({"data": {"edges": [{"node": {"id": "gid://shopify/Product/1",
                                                                 "productType": "Gobo"}}],
                                            "pageInfo": {"hasNextPage": False, "endCursor": None}}}).encode())
    saved = ing.urllib.request.urlopen
    ing.urllib.request.urlopen = fake
    try:
        got = ing.fetch_products(ing.ReactorStore("https://reactor.example/", "tok-123"))
    finally:
        ing.urllib.request.urlopen = saved
    assert got == {"gid://shopify/Product/1": {"product_type": "Gobo"}}, got
    url, headers, body = seen[0]
    assert url == "https://reactor.example/hooks/forecast/shopify", url
    assert headers.get("X-forecast-token") == "tok-123", headers
    assert body == {"op": "products", "after": None}, body
    # A refusal is an error with Reactor's own words, never an empty store.
    def refuse(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {},
                                     io.BytesIO(b'{"error": "Unauthorized"}'))
    ing.urllib.request.urlopen = refuse
    try:
        ing.ReactorStore("https://reactor.example", "wrong").products_page(None)
    except RuntimeError as e:
        assert "401" in str(e) and "Unauthorized" in str(e), e
    else:
        raise AssertionError("a refused read has to fail the run")
    finally:
        ing.urllib.request.urlopen = saved
    # The run: the secret alone is not enough, and it is named for removal.
    records = []

    class _Keep(logging.Handler):
        def emit(self, r): records.append(r.getMessage())
    h = _Keep()
    nightly.log.addHandler(h)
    saved_env = dict(os.environ)
    try:
        for k in ("REACTOR_URL", "FORECAST_INGEST_TOKEN", "SHOPIFY_FORECAST_TOKEN"):
            os.environ.pop(k, None)
        os.environ.update({"SHOP": "projectedimage.myshopify.com",
                           "SHOPIFY_CLIENT_ID": "id", "SHOPIFY_CLIENT_SECRET": "secret"})
        assert nightly.main() == 2, "Reactor's id and secret do not make a run"
    finally:
        os.environ.clear(); os.environ.update(saved_env)
        nightly.log.removeHandler(h)
    text = " ".join(records)
    assert "SHOPIFY_CLIENT_SECRET" in text and "not used" in text and "rotate" in text, text
    assert "REACTOR_URL" in text and "FORECAST_INGEST_TOKEN" in text, text
    nsrc = open(os.path.join(root, "forecast", "nightly.py"), encoding="utf-8").read()
    body = nsrc.split("try:", 1)[1]
    # Chosen inside the try, so a refusal is posted to the tab.
    assert "ShopifyStore(shop, stoken) if stoken else ReactorStore(base, token)" in body
    assert "run_bulk_orders(store, pull_from)" in nsrc and "fetch_products(store)" in nsrc


@test
def t_a_bulk_pull_runs_the_same_through_either_store():
    """run_bulk_orders does not know which store it was handed: it starts the
    bulk query, polls it BY ID, downloads the file, and fills the refunds in
    from their own paged read."""
    import io, json as _json
    import forecast.ingest as ing
    calls = []

    class _Store:
        def bulk_start(self, since):
            calls.append(("start", since.isoformat()))
            return {"bulkOperation": {"id": "gid://shopify/BulkOperation/7", "status": "CREATED"},
                    "userErrors": []}

        def bulk_status(self, op_id):
            calls.append(("status", op_id))
            return {"status": "COMPLETED", "url": "https://files.example/bulk.jsonl", "objectCount": 2}

        def refunds_page(self, since, after):
            calls.append(("refunds", after))
            return {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}

    class _Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    lines = [{"id": "gid://shopify/Order/1", "name": "#1", "createdAt": "2026-09-01T10:00:00Z",
              "currentTotalPriceSet": {"shopMoney": {"amount": "12.00"}}},
             {"id": "gid://shopify/LineItem/9", "__parentId": "gid://shopify/Order/1", "quantity": 1,
              "originalUnitPriceSet": {"shopMoney": {"amount": "10.00"}}}]
    saved = ing.urllib.request.urlopen
    ing.urllib.request.urlopen = lambda url, timeout=None: _Resp("\n".join(_json.dumps(l) for l in lines).encode())
    try:
        orders = ing.run_bulk_orders(_Store(), date(2026, 1, 1), poll_seconds=0)
    finally:
        ing.urllib.request.urlopen = saved
    assert calls == [("start", "2026-01-01"), ("status", "gid://shopify/BulkOperation/7"), ("refunds", None)], calls
    assert len(orders) == 1 and orders[0]["order_total"] == 12.0 and len(orders[0]["line_items"]) == 1, orders


@test
def t_the_plain_models_beat_the_big_one_on_this_shops_history():
    """The five sanity models, on Projected Image's real monthly totals.

    The M5-style model forecast October - their best month, twice over 60k -
    at 16,436. Every one of these lands between 41k and 68k, against Shopify's
    own 50,500 and the plan's 43,715. That is the whole reason they exist."""
    from forecast.simple import sanity_forecasts
    H = [("2024-04",17156.75),("2024-05",45564.36),("2024-06",51515.19),("2024-07",26859.66),
         ("2024-08",24939.21),("2024-09",50974.34),("2024-10",72761.85),("2024-11",77934.11),
         ("2024-12",53647.74),("2025-01",61479.34),("2025-02",38593.05),("2025-03",46374.12),
         ("2025-04",33759.42),("2025-05",65915.05),("2025-06",67172.92),("2025-07",18448.50),
         ("2025-08",21084.64),("2025-09",37922.64),("2025-10",64439.49),("2025-11",53035.69),
         ("2025-12",15444.05),("2026-01",27218.29),("2026-02",33217.03),("2026-03",30689.37),
         ("2026-04",28077.26),("2026-05",30736.02),("2026-06",36912.73),("2026-07",15391.59),
         ("2026-08",27352.36)]
    s = pd.Series([v for _, v in H], index=pd.PeriodIndex([m for m, _ in H], freq="M"), dtype=float)
    r = sanity_forecasts(s, 4)
    assert r["available"] and len(r["models"]) >= 5, r
    # Combinations are rows like any other, ranked on the same folds.
    kinds = {m["kind"] for m in r["models"]}
    assert kinds == {"model", "combination"}, kinds
    combos = [m for m in r["models"] if m["kind"] == "combination"]
    assert len(combos) == 3 and all(c["score"]["mape"] is not None for c in combos), combos
    assert r["months"] == ["2026-09", "2026-10", "2026-11", "2026-12"], r["months"]
    # Every row that produced numbers is in the same ballpark as an October
    # has ever been. AutoETS and AutoTheta come in low (they find no
    # seasonality in 29 points) but nowhere near the 16,436 the old model gave.
    # Every source and every combination explains itself in plain words.
    for m in r["models"]:
        assert m.get("about") and len(m["about"]) > 60, m["name"]
    for m in r["models"]:
        oct_ = (m.get("months") or {}).get("2026-10")
        if oct_ is None:
            continue
        assert 25_000 <= oct_ <= 80_000, f"{m['name']} put October at {oct_}"
    # The simplest model is the best on this history, and it is nearly unbiased.
    # Renamed for the people who read this in a board pack: the names on the
    # page say what a source DOES, and the method is explained on hover.
    assert r["best"] == "Last year, adjusted for this year", r["best"]
    best = [m for m in r["models"] if m["name"] == r["best"]][0]
    assert best["score"]["mape"] < 0.30, best["score"]
    assert abs(best["score"]["bias"]) < 0.05, best["score"]
    # Everything that produced numbers is scored, and the median is a real one.
    assert all(m["score"]["mape"] is not None for m in r["models"] if m.get("months"))
    assert 35_000 <= r["median"]["2026-10"] <= 80_000


@test
def t_a_sanity_model_refuses_rather_than_guesses_without_two_years():
    """A seasonal model given one year has nothing to learn a season from, and
    a number produced anyway would be read as if it meant something."""
    from forecast.simple import sanity_forecasts, MIN_MONTHS
    idx = pd.period_range("2025-09", periods=12, freq="M")
    r = sanity_forecasts(pd.Series(range(12), index=idx, dtype=float))
    assert r["available"] is False and str(MIN_MONTHS) in r["reason"], r
    assert r["models"] == [] and r["history"] == []


@test
def t_an_order_is_counted_on_its_london_day():
    """B47 in the 2026-09-19 bug audit. Shopify's bulk query stamps createdAt
    in UTC; the run's as_of and the plan's months are London days, so through
    British Summer Time the first hour of every day fell on the day before,
    and on the 1st it fell in the month before."""
    from forecast.ingest import _day
    ok(_day("2026-08-31T23:30:00Z") == date(2026, 9, 1), "half past midnight BST on the 1st is the 1st")
    ok(_day("2026-01-31T23:30:00Z") == date(2026, 1, 31), "and in winter nothing moves")
    ok(_day("2026-08-31") == date(2026, 8, 31), "a bare date is taken as it stands")
    ok(_day("2026-08-31T23:30:00.123456+00:00") == date(2026, 9, 1), "fractional seconds included")


@test
def t_the_month_in_progress_never_reaches_a_model():
    """Half a September looks like a collapse. Handed one, every model would
    forecast the rest of the year down from it."""
    from forecast.ingest import monthly_cash
    orders = [{"created_at": "2026-08-05T10:00:00Z", "order_total": "1000"},
              {"created_at": "2026-09-03T10:00:00Z", "order_total": "5"},
              {"created_at": "2026-07-05T10:00:00Z", "order_total": "900"},
              {"created_at": "2026-06-05T10:00:00Z", "order_total": "800", "test": True},
              {"created_at": "2026-05-05T10:00:00Z", "order_total": "700", "cancelled_at": "x"}]
    ser = monthly_cash(orders, date(2026, 9, 8))
    got = {str(p): float(v) for p, v in ser.items()}
    assert got == {"2026-07": 900.0, "2026-08": 1000.0}, got


@test
def t_the_band_on_the_page_is_the_error_the_model_actually_earned():
    """The single most important honesty property of this package: the range
    drawn around a month must be the range the model's own record supports.

    daily_frame paints a band on each day and VarianceEngine._window_band sums
    those days and shrinks the result by sqrt(n / persistence). The daily band
    was the MONTHLY error painted straight on, and then shrunk anyway, so the
    round trip lost a factor of sqrt(days_in_month / 4): a source whose record
    said it is typically 28.7% out was drawn at 10.3%. The month table, the
    "secure"/"high" risk verdicts and every alert are all computed from that
    band, and the tab tells a director it should hold 8 times out of 10."""
    import pandas as pd
    from forecast.simple import daily_frame, BAND_PERSISTENCE_DAYS
    from forecast.cashflow import DayProfile
    from forecast.variance import VarianceEngine
    # The range claims 8 times in 10, so it is drawn at the miss 8 in 10 of
    # the source's past ones stayed within (p80), not at the average miss,
    # which held only about 6 times in 10: September 2026 came in above the
    # range on every day from the 1st to the 22nd. Both sides match even when
    # the daily p10s bottom out at zero, because the month is built from the
    # unclipped daily width.
    for p80 in (0.10, 0.20, 0.287, 0.50, 0.75):
        model = {"name": "t", "score": {"mape": p80 * 0.6, "p80": p80}, "months": {"2026-10": 30000.0}}
        fd = daily_frame(model, pd.Timestamp("2026-09-30"), DayProfile.uniform())
        lo, mid, hi = VarianceEngine._window_band(fd)
        ok(abs((hi - mid) / mid - p80) < 0.005, "a p80 of %.1f%% is drawn at %.1f%%" % (p80 * 100, (hi - mid) / mid * 100))
        ok(abs((mid - lo) / mid - p80) < 0.005, "and the low side matches, clipped days or not")
        ok(float(fd["p10"].min()) >= 0.0, "no day is forecast to take negative money")
    # A run scored before p80 existed still draws at its typical error.
    fd = daily_frame({"name": "t", "score": {"mape": 0.287}, "months": {"2026-10": 30000.0}},
                     pd.Timestamp("2026-09-30"), DayProfile.uniform())
    lo, mid, hi = VarianceEngine._window_band(fd)
    ok(abs((hi - mid) / mid - 0.287) < 0.005, "with no p80 the typical error is the width")
    # One constant, or the round trip silently stops closing.
    import inspect, forecast.variance as _v
    ok("BAND_PERSISTENCE_DAYS" in inspect.getsource(_v),
       "the shrink and the widen share one persistence constant")


@test
def t_every_source_blurb_stands_as_its_own_sentence():
    """The Why card prints a source's blurb straight after its name and a full
    stop, so a blurb that began 'Takes the season out' or 'The same, but'
    read as a sentence with no subject, or pointed at a row that is not
    there."""
    import inspect
    import forecast.simple as fs
    import forecast.prophet_source as fp
    blurbs = [m[2] for m in fs.MODELS] + [c[3] for c in fs.COMBINERS] + [fp.PROPHET_ABOUT, fp.HYBRID_ABOUT]
    try:
        blurbs += [m[2] for m in fs.statsforecast_models()]
    except Exception:
        pass
    for b in blurbs:
        ok(b.startswith(("It ", "The textbook")), "a subject first: %r" % b[:40])
        ok(not b.startswith("The same"), "and no pointer to a neighbour: %r" % b[:40])
    src = inspect.getsource(fs)
    ok('"about": "It weights every method' in src, "the track-record method too")


@test
def t_a_shops_opening_month_is_not_fed_as_a_whole_one():
    """Projected Image opened about 15 April 2024 and that half April went to
    the models as a complete month; on its own it decided which source led.
    A pull that starts before the first month with orders drops that month;
    a pull that starts on the 1st of a trading month keeps it, whole."""
    from forecast.ingest import monthly_cash
    orders = [{"created_at": "2024-04-15T10:00:00Z", "order_total": "500"},
              {"created_at": "2024-05-02T10:00:00Z", "order_total": "3000"},
              {"created_at": "2024-06-20T10:00:00Z", "order_total": "2500"},
              {"created_at": "2024-06-21T10:00:00Z", "order_total": "100"}]
    opened = monthly_cash(orders, date(2024, 7, 3), since=date(2024, 3, 1))
    ok([str(p) for p in opened.index] == ["2024-05", "2024-06"], "the opening month is dropped: %s" % list(opened.index))
    # The history starting in the opening month itself: nothing before it, so
    # it is still the opening half month, and still dropped.
    same = monthly_cash(orders, date(2024, 7, 3), since=date(2024, 4, 1))
    ok([str(p) for p in same.index] == ["2024-05", "2024-06"],
       "a history that starts in the opening month still leaves it out: %s" % list(same.index))
    # Trade in the month before (the extra month the job pulls): the shop was
    # already open, so the first month wanted is whole, and the extra one is
    # not returned.
    traded = [{"created_at": "2024-03-20T10:00:00Z", "order_total": "50"}] + orders
    whole = monthly_cash(traded, date(2024, 7, 3), since=date(2024, 4, 1))
    ok([str(p) for p in whole.index] == ["2024-04", "2024-05", "2024-06"],
       "with trade before it, the first month is whole, and the month before is not fed: %s" % list(whole.index))
    big = monthly_cash(orders, date(2024, 7, 3), since=date(2024, 3, 1), min_total=2000)
    ok(list(big.index) == list(opened.index) and float(big["2024-05"]) == 3000.0 and float(big["2024-06"]) == 2500.0,
       "big orders come on exactly the same months, the small order left out: %s" % big.to_dict())


@test
def t_big_orders_are_counted_apart():
    """'Last year, adjusted' scales last year's whole month, one-off big orders
    included. Orders of 2,000 or more caused 78% of its error on the months it
    could not see in 2026: nine big orders in January 2025 made it forecast
    January 2026 at nearly double. Counted apart, the regular orders follow
    last year and the big ones are the middle of their last twelve months:
    the average let a few exceptional months lift every month after them,
    and put big orders about half as high again as they came in."""
    from forecast.simple import (BIG_ORDERS_ABOUT, BIG_ORDERS_NAME, big_orders_apart,
                                 last_year_times_run_rate, sanity_forecasts)
    idx = pd.period_range("2023-10", "2026-08", freq="M")
    y = pd.Series(20000.0, index=idx)
    big = pd.Series(0.0, index=idx)
    big[pd.Period("2025-09", freq="M")] = 30000.0         # one huge order last September
    y = y + big
    plain, _ = last_year_times_run_rate(y, 1)
    split, note = big_orders_apart(y, 1, big)
    sep = pd.Period("2026-09", freq="M")
    ok(plain[sep] > 40000, "scaling last year's whole month repeats the one-off: %.0f" % plain[sep])
    ok(abs(split[sep] - (20000.0 + 30000.0 / 12)) < 1.0,
       "counted apart: last year's regular month plus, with big orders this rare, their average month: %.0f"
       % split[sep])
    ok("big orders" in note, note)
    # Big orders most months, and one exceptional one: the middle month is
    # the usual one, where the average would carry the exception into every
    # month after it.
    steady = pd.Series(9000.0, index=idx)
    steady[pd.Period("2026-03", freq="M")] = 40000.0
    f, note = big_orders_apart(pd.Series(20000.0, index=idx) + steady, 2, steady)
    ok(all(abs(v - 29000.0) < 1.0 for v in f.values), "the usual big month, not the exception's average: %s" % list(f.values))
    ok("9,000 a month" in note, note)
    from forecast.simple import big_level
    ok(big_level(steady) == 9000.0 and abs(float(steady.iloc[-12:].mean()) - 11583.33) < 0.01,
       "the median where the mean would have been 11,583")
    ok(big_level(pd.Series(dtype=float)) == 0.0, "no big orders on record, none forecast")
    # Big orders in only five months of twelve: the plain middle month is
    # nothing, so it would forecast none at all, every month. The middle of
    # the months that had any, scaled by how many did, is not.
    sparse = pd.Series([10000.0, 0, 0, 10000.0, 0, 0, 10000.0, 0, 10000.0, 0, 0, 10000.0],
                       index=pd.period_range("2025-09", periods=12, freq="M"))
    ok(float(sparse.median()) == 0.0 and abs(big_level(sparse) - 10000.0 * 5 / 12) < 0.01,
       "five months of twelve: 5/12 of a typical big month, %.0f" % big_level(sparse))
    half = sparse.copy(); half.iloc[1] = 4000.0
    ok(abs(big_level(half) - 5000.0) < 0.01 and big_level(half) > big_level(sparse),
       "another month with a big order never lowers it: %.0f" % big_level(half))
    # A backtest fold cut before the big order cannot see it.
    early = y[y.index <= pd.Period("2025-06", freq="M")]
    f, _ = big_orders_apart(early, 3, big)
    ok(all(abs(v - 20000.0) < 1.0 for v in f.values), "a fold cut before the big order knows nothing of it: %s" % list(f.values))
    with_big = sanity_forecasts(y, horizon=2, big=big)
    without = sanity_forecasts(y, horizon=2)
    ok(any(m["name"] == BIG_ORDERS_NAME and m.get("months") for m in with_big["models"]),
       "given the big orders, it is a source like the others, scored and ranked")
    ok(all(m["name"] != BIG_ORDERS_NAME for m in without["models"]), "and absent without them")
    ok(BIG_ORDERS_ABOUT.startswith("It ") and BIG_ORDERS_ABOUT.count(". ") >= 1, "its blurb reads like the others")


@test
def t_the_range_is_the_miss_8_in_10_stayed_within():
    from forecast.simple import _errors_to_score, band_width
    # Ten past forecasts and what came in, September 2026's leader among them.
    pred = np.array([24677.0, 41933.0, 30000.0, 52000.0, 18000.0, 61000.0, 27000.0, 35000.0, 12000.0, 44000.0])
    act = np.array([38741.0, 40000.0, 33000.0, 47000.0, 16000.0, 70000.0, 30000.0, 22000.0, 15444.0, 47000.0])
    errs = list((pred - act) / act)
    spread = list(np.abs(act - pred) / pred)
    sc = _errors_to_score(errs, spread)
    # With ten misses, the ceil(0.8 x 11) = 9th smallest: the split-conformal
    # rule, which never sits inside the plain 80th percentile.
    ok(abs(sc["p80"] - sorted(spread)[8]) < 1e-9,
       "p80 is measured against the forecast the range is drawn around: %s" % sc["p80"])
    ok(sc["p80"] >= float(np.quantile(spread, 0.8)), "and never narrower than the plain percentile")
    inside = np.abs(act - pred) <= sc["p80"] * pred
    ok(inside.sum() >= 8, "so forecast x (1 +/- p80) holds 8 in 10 of what came in: %d" % inside.sum())
    # Measured against the actual instead, the same rule held fewer, and missed
    # on the side September did: a forecast too low.
    wrong = float(np.quantile(np.abs(np.array(errs)), 0.8))
    ok((np.abs(act - pred) <= wrong * pred).sum() < 8, "the old measure did not hold 8 in 10 here")
    ok(sc["p80"] > sc["mape"], "and wider than the average miss")
    ok(band_width({"score": sc}) == sc["p80"], "the range uses it")
    ok(band_width({"score": {"mape": 0.287}}) == 0.287, "a run without it falls back to the typical error")
    ok(band_width({"score": {"p80": 2.0}}) == 0.90 and band_width({"score": {"p80": 0.01}}) == 0.10, "held between 10% and 90%")
    ok(_errors_to_score([])["p80"] is None, "no errors, no width")
    from forecast.simple import _p80
    ok(_p80([0.1, 0.3, 0.2]) == 0.3 and _p80([0.4]) == 0.4, "a handful of misses: the largest")
    ok(_p80(np.arange(1, 10) / 10) == 0.8, "nine misses: the eighth smallest")
    # A source with no backtest of its own (the track-record weighting) is
    # drawn at the same width, read from its misses on the record and
    # measured against its forecast, not at its typical miss.
    from forecast.simple import track_record
    rec = track_record([{"month": m, "by_source": {"w": {"error": e}}}
                        for m, e in (("2026-01", 0.10), ("2026-02", -0.20), ("2026-03", 0.05), ("2026-04", -0.02))])
    want = max(0.10 / 1.10, 0.20 / 0.80, 0.05 / 1.05, 0.02 / 0.98)
    ok(abs(rec["w"]["p80"] - want) < 1e-9, "four misses: the largest, against the forecast: %s" % rec["w"]["p80"])
    ok(band_width({"score": {"mape": None, "p80": None}, "live": {"mape": 0.0925, "p80": rec["w"]["p80"]}}) == rec["w"]["p80"],
       "the weighting's range comes from its record")
    ok(band_width({"score": {"mape": None}, "live": {"mape": 0.05}}) == 0.30, "and a typical miss alone is not a range")


@test
def t_the_run_tells_the_record_which_source_is_in_use():
    """Reactor keeps, for every month, what the forecast in use said and its
    likely range, so a closed month can be shown as what directors were told,
    not as whichever source turned out closest."""
    from forecast.nightly import _in_use
    view = pd.DataFrame({"month": [pd.Timestamp("2026-10-01"), pd.Timestamp("2026-11-01"), pd.Timestamp("2026-12-01")],
                         "projected_p50": [52000.0, 45044.0, float("nan")]})
    got = _in_use({"name": "Big orders counted apart",
                   "months": {"2026-10": 50568.0, "2026-11": 45044.0, "2026-12": float("nan"), "2027-01": None}},
                  view, 0.284)
    ok(got["source"] == "Big orders counted apart", got)
    oct_ = got["months"]["2026-10"]
    ok(oct_["value"] == 50568.0 and abs(oct_["p10"] - 50568 * 0.716) < 0.01 and abs(oct_["p90"] - 50568 * 1.284) < 0.01,
       "its figure and its likely range: %s" % oct_)
    ok(oct_["shown"] == 52000.0, "and what the page showed, money already taken included")
    ok("2026-12" not in got["months"] and "2027-01" not in got["months"], "a month it cannot give is left out, never NaN")
    import json
    json.loads(json.dumps(got, allow_nan=False))


@test
def t_the_words_a_model_shows_on_the_page_say_method_not_source():
    """Cameron approved "method" on the Forecast screen. The combination
    models' own sentences (the Why caption and popover, the Every method
    window) said "source": reworded, while the keys and the model names, which
    are the service's own and key the page, are untouched."""
    import re
    import inspect
    import forecast.simple as fs
    word = re.compile(r"\b[Ss]ources?\b")
    import forecast.prophet_source as fp
    shown = [fs.BIG_ORDERS_ABOUT, fs.BIG_ORDERS_BEST_AT, fp.PROPHET_ABOUT, fp.PROPHET_BEST_AT,
             fp.HYBRID_ABOUT, fp.HYBRID_BEST_AT]
    for m in fs.MODELS:
        shown += [m[2]]
    for c in fs.COMBINERS:
        shown += [c[2], c[3], c[4]]          # note, about, best at: not c[0], the model's name
    for t in shown:
        ok(not word.search(t), "says method: %r" % t[:70])
    src = inspect.getsource(fs)
    ok('"note": "each method weighted' in src and '"about": "It weights every method' in src, "the track-record model too")
    ok(tuple(c[0] for c in fs.COMBINERS) == ("Average of every source", "Middle of every source", "Average, extremes removed"),
       "and the model names are as they were")


def _invented_shop(months=31, seed=7):
    """Orders for an invented shop: regular orders every day with a weekly
    rhythm and a yearly season, and big quoted orders most months. Its first
    month is its opening month, which the panel never sees."""
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2023-06-01")
    end = start + pd.offsets.MonthBegin(months) - pd.Timedelta(days=1)
    orders = []
    for d in pd.date_range(start, end, freq="D"):
        reg = 600 + 250 * np.sin(2 * np.pi * d.dayofyear / 365.25) - (250 if d.weekday() >= 5 else 0) + rng.normal(0, 60)
        orders.append({"created_at": f"{d.date()}T11:00:00Z", "order_total": round(max(reg, 20.0), 2)})
        if d.day in (9, 21) and rng.random() < 0.6:
            orders.append({"created_at": f"{d.date()}T15:00:00Z", "order_total": round(float(rng.uniform(2500, 9000)), 2)})
    return orders, (end + pd.Timedelta(days=5)).date()


def _have_prophet():
    from forecast.prophet_source import available
    if available():
        return True
    print("        (Prophet is not installed here: its checks are skipped; CI installs it)")
    return False


@test
def t_regular_orders_by_day_and_big_orders_add_up_to_the_month():
    """The sources that forecast the regular orders by day must be handed
    exactly the money the big orders are not, or the month they add back up
    to is not the month the panel is marked on."""
    from forecast.ingest import daily_cash, monthly_cash
    from forecast.simple import BIG_ORDER
    orders, as_of = _invented_shop(14)
    orders.append({"created_at": "2023-09-14T10:00:00Z", "order_total": "2000"})        # exactly the line: big
    orders.append({"created_at": "2023-09-14T12:00:00Z", "order_total": "1999.99"})     # a penny under: regular
    orders.append({"created_at": "2023-09-15T12:00:00Z", "order_total": "50", "test": True})
    total = monthly_cash(orders, as_of)
    big = monthly_cash(orders, as_of, min_total=BIG_ORDER)
    small = daily_cash(orders, as_of, max_total=BIG_ORDER)
    whole = daily_cash(orders, as_of)
    ok(list(small.index) == list(whole.index), "the same days as the whole series")
    by_month = small.groupby(small.index.to_period("M")).sum()
    for p in total.index:
        ok(abs(by_month[p] + big[p] - total[p]) < 0.005, "%s: regular %.2f + big %.2f = %.2f" % (p, by_month[p], big[p], total[p]))
    ok(abs(small[pd.Timestamp("2023-09-14")] - (whole[pd.Timestamp("2023-09-14")] - 2000.0)) < 0.005,
       "an order of exactly 2,000 is a big one, a penny under is regular")
    ok(daily_cash([{"created_at": "2026-01-05T10:00:00Z", "order_total": "5000"}], date(2026, 1, 7),
                  max_total=BIG_ORDER).tolist() == [0.0, 0.0, 0.0], "days with only big orders are zeros, not gaps")


@test
def t_prophet_reads_no_day_after_its_cut_off():
    """A backtest fold that can see past its cut-off scores itself on months
    it has already been shown. Prophet is handed days, not months, so the
    cut is its own: everything after the last day of the fold's last month,
    including the month in progress, is never read."""
    if not _have_prophet():
        return
    from forecast.prophet_source import regular_months
    days = pd.date_range("2023-01-01", "2025-02-14", freq="D")
    rng = np.random.default_rng(1)
    y = pd.Series(700 + 200 * np.sin(2 * np.pi * days.dayofyear / 365.25) + rng.normal(0, 40, len(days)), index=days)
    first, through = pd.Period("2023-01", "M"), pd.Period("2024-12", "M")
    seen = regular_months(y, first, through, 2)
    later = y.copy()
    later[later.index > pd.Timestamp("2024-12-31")] *= 50          # a boom it must not know about
    ok(np.allclose(regular_months(later, first, through, 2).values, seen.values, rtol=0, atol=1e-6),
       "what comes after the cut-off changes nothing")
    ok([str(p) for p in seen.index] == ["2025-01", "2025-02"] and (seen > 0).all(), seen.to_dict())
    try:
        regular_months(y[y.index <= pd.Timestamp("2024-12-20")], first, through, 1)
    except ValueError as e:
        ok("stop" in str(e), str(e))
    else:
        raise AssertionError("days that stop short of the cut-off are refused, not read as a quiet end of month")


@test
def t_a_prophet_fold_sees_nothing_after_its_own_cut_off():
    """The backtest refits each Prophet method at three earlier cut-offs and
    scores it there. Changing every day and every big order after the
    history's own last month (the month in progress) must move nothing it
    says or scores; changing them after one fold's cut-off must move nothing
    that fold scored on, so the score of the earliest fold's months is fixed."""
    if not _have_prophet():
        return
    from forecast.evaluate import series_from_orders
    from forecast.prophet_source import HYBRID_NAME, PROPHET_NAME
    from forecast.simple import sanity_forecasts
    orders, as_of = _invented_shop()
    monthly, big, small = series_from_orders(orders, as_of)
    first = sanity_forecasts(monthly, horizon=2, big=big, daily_small=small)
    after = small.copy()
    after[after.index > monthly.index[-1].to_timestamp(how="end")] *= 9      # the month in progress
    big9 = big.copy(); big9[pd.Period("2026-01", "M")] = 1e6                  # a month not yet complete
    again = sanity_forecasts(monthly, horizon=2, big=big9, daily_small=after)
    by1 = {m["name"]: m for m in first["models"]}
    by2 = {m["name"]: m for m in again["models"]}
    for name in (PROPHET_NAME, HYBRID_NAME):
        ok(by1[name]["months"] == by2[name]["months"] and by1[name]["score"] == by2[name]["score"],
           "%s: the month in progress reaches neither its forecast nor its backtest" % name)
    # A fold cut at month k-3 is scored on months k-3..k-1; Prophet's fit for
    # that fold must not move when the days of month k-1 change.
    cut_end = monthly.index[-4].to_timestamp(how="end")
    late = small.copy()
    late[late.index > cut_end] *= 3
    import forecast.prophet_source as fp
    fits = []
    saved = fp.regular_months

    def spy(d, first_, through, h):
        out = saved(d, first_, through, h)
        fits.append((str(through), h, tuple(round(v, 6) for v in out.values)))
        return out
    try:
        fp.regular_months = spy
        sanity_forecasts(monthly, horizon=2, big=big, daily_small=small)
        base_fits = dict(((t, h), v) for t, h, v in fits)
        fits.clear()
        sanity_forecasts(monthly, horizon=2, big=big, daily_small=late)
        late_fits = dict(((t, h), v) for t, h, v in fits)
    finally:
        fp.regular_months = saved
    earliest = str(monthly.index[-4])
    ok((earliest, 3) in base_fits and base_fits[(earliest, 3)] == late_fits[(earliest, 3)],
       "the fold cut at %s fits the same, whatever came after it" % earliest)
    ok(base_fits[(str(monthly.index[-1]), 2)] != late_fits[(str(monthly.index[-1]), 2)],
       "while the fit that is allowed to see those days does move (the check can fail)")


@test
def t_prophet_joins_the_panel_as_two_scored_sources():
    """Handed the regular orders by day, the panel gains Prophet's forecast of
    them (with big orders as the middle of their last twelve months) and the
    average of that with "Big orders counted apart". They are rows like any
    other: backtested on the same folds, ranked, never wired in."""
    from forecast.evaluate import series_from_orders
    from forecast.prophet_source import HYBRID_NAME, PROPHET_NAME
    from forecast.simple import BIG_ORDERS_NAME, sanity_forecasts
    orders, as_of = _invented_shop()
    monthly, big, small = series_from_orders(orders, as_of)
    ok(len(monthly) == 30 and str(monthly.index[0]) == "2023-07", "the opening month is not fed: %s" % monthly.index[0])
    without = sanity_forecasts(monthly, horizon=3, big=big)
    ok(not {PROPHET_NAME, HYBRID_NAME} & {m["name"] for m in without["models"]}, "absent without the days")
    if not _have_prophet():
        return
    r = sanity_forecasts(monthly, horizon=3, big=big, daily_small=small)
    by = {m["name"]: m for m in r["models"]}
    for name in (PROPHET_NAME, HYBRID_NAME):
        m = by.get(name) or {}
        ok(m.get("months") and len(m["months"]) == 3, "%s forecasts: %s" % (name, m.get("error")))
        ok((m.get("score") or {}).get("folds") == 9 and m["score"]["mape"] is not None,
           "%s is scored on the same folds: %s" % (name, m.get("score")))
        ok(name in r["ranking"], "and ranked")
    for k in r["months"]:
        avg = (by[BIG_ORDERS_NAME]["months"][k] + by[PROPHET_NAME]["months"][k]) / 2
        ok(abs(by[HYBRID_NAME]["months"][k] - avg) < 0.02, "the average is the average: %s" % k)
    # An invented shop with a clean season: Prophet should be in the right place.
    for k, v in by[PROPHET_NAME]["months"].items():
        ok(abs(v - float(monthly[pd.Period(k, "M") - 12])) / v < 0.5, "%s is within reach of a year ago: %.0f" % (k, v))


@test
def t_a_prophet_that_fails_leaves_the_rest_of_the_panel_standing():
    """It is an optional library with a compiled model behind it. Missing, it
    leaves the panel exactly as it was; failing, its two rows say so and the
    rest of the run carries on."""
    import forecast.prophet_source as fp
    from forecast.evaluate import series_from_orders
    from forecast.simple import sanity_forecasts
    orders, as_of = _invented_shop()
    monthly, big, small = series_from_orders(orders, as_of)
    base = sanity_forecasts(monthly, horizon=2, big=big)
    saved_av, saved_fit = fp.available, fp.regular_months
    try:
        fp.available = lambda: False
        gone = sanity_forecasts(monthly, horizon=2, big=big, daily_small=small)
        ok([m["name"] for m in gone["models"]] == [m["name"] for m in base["models"]], "absent, the panel is as it was")
        ok(gone["best"] == base["best"] and gone["ranking"] == base["ranking"], "and ranks the same")
        fp.available = lambda: True

        def broken(*a, **k):
            raise RuntimeError("the compiled model would not start")
        fp.regular_months = broken
        failed = sanity_forecasts(monthly, horizon=2, big=big, daily_small=small)
    finally:
        fp.available, fp.regular_months = saved_av, saved_fit
    by = {m["name"]: m for m in failed["models"]}
    for name in (fp.PROPHET_NAME, fp.HYBRID_NAME):
        ok("would not start" in (by[name].get("error") or ""), "the row says why: %s" % by[name])
        ok(name not in failed["ranking"], "and it is not ranked")
    ok(failed["available"] and failed["best"] == base["best"], "the run carries on with everything else")


def _page_source():
    """The page's script: static/index.html, or the sections it is built from."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parts = []
    for base, _dirs, files in os.walk(os.path.join(root, "static")):
        for f in sorted(files):
            if f.endswith((".html", ".js")):
                parts.append(open(os.path.join(base, f), encoding="utf-8").read())
    return "\n".join(parts)


def _page_lead(sn):
    """The page's 'Running now' choice, as fcOptimisedCard makes it (the lines
    are checked against the page itself below)."""
    from functools import cmp_to_key
    rows = [{"m": m, "live": (m.get("live") or {}).get("mape"), "back": (m.get("score") or {}).get("mape")}
            for m in sn["models"] if m.get("months")]
    rows = [x for x in rows if x["live"] is not None or x["back"] is not None]
    on = sn["ranked_on"] == "record"

    def cmp(a, b):
        if on and a["live"] is not None and b["live"] is not None:
            d = a["live"] - b["live"]
        else:
            d = (9 if a["back"] is None else a["back"]) - (9 if b["back"] is None else b["back"])
        return (d > 0) - (d < 0)
    rows = sorted(rows, key=cmp_to_key(cmp))
    if isinstance(sn.get("ranking"), list):              # fcRankFirst: the run's order first, stable
        rows = sorted(rows, key=lambda x: sn["ranking"].index(x["m"]["name"])
                      if x["m"]["name"] in sn["ranking"] else 1e9)
    return rows[0]["m"]["name"] if rows else None


@test
def t_the_numbers_come_from_the_source_the_page_names():
    """Once months have closed, the page ranks on the record and names its
    leader as running. pick_opinions sorted on the backtest regardless, so the
    month table, the cash path and the alerts followed the backtest's leader
    under another method's name. The headline is now the first of the panel's
    own ranking, and that ranking is the page's.

    The record is ranked on only once EVERY scored method has three closed
    months of its own. Counted on the longest record instead, a method added
    later raced on one month against the others' averages, and a lucky month
    put it in charge; and the page, which compares two methods on the record
    only when both have one, named a different method from the one in use."""
    from forecast.evaluate import series_from_orders
    from forecast.simple import pick_opinions, sanity_forecasts
    src = _page_source()
    ok("ranked.sort((a, b) => (onRecord && a.live != null && b.live != null)" in src
       and "? a.live - b.live : ((a.back == null ? 9 : a.back) - (b.back == null ? 9 : b.back)));" in src
       and "const onRecord = sn.ranked_on === 'record';" in src
       and "const order = fcRankFirst(sn, ranked, x => x.m.name);" in src,
       "the page still ranks the way _page_lead copies; if it changed, check the two still agree")
    orders, as_of = _invented_shop()
    monthly, big, _ = series_from_orders(orders, as_of)
    backtest = sanity_forecasts(monthly, horizon=2, big=big)
    scored = [m for m in backtest["models"] if m.get("months") and m["score"]["mape"] is not None]
    worst = max(scored, key=lambda m: m["score"]["mape"])["name"]
    leader = pick_opinions(backtest)[0]["name"]
    ok(worst != leader and leader == backtest["best"] == _page_lead(backtest), "on the backtest: its best, on both")

    def record(months, errors):
        return [{"month": m, "winner": min(errors, key=lambda k: abs(errors[k])),
                 "by_source": {k: {"error": e} for k, e in errors.items()}} for m in months]
    everyone = {m["name"]: 0.30 for m in scored}
    everyone[worst] = 0.02
    three = ("2025-10", "2025-11", "2025-12")
    r = sanity_forecasts(monthly, horizon=2, big=big, results=record(three, everyone))
    ok(r["ranked_on"] == "record" and r["best"] == worst and r["ranking"][0] == worst, r.get("ranking", [])[:3])
    ok(pick_opinions(r)[0]["name"] == worst == _page_lead(r), "the numbers and the page follow the record's leader")
    ok([m["name"] for m in pick_opinions(r, 5)] == r["ranking"][:5], "in the panel's own order")
    old = {k: v for k, v in r.items() if k != "ranking"}
    ok(pick_opinions(old)[0]["name"] == leader, "a run kept from before the ranking still reads")
    # A method one month into its record, however good that month: the record
    # waits for it, on both sides, and the page says how many every method has.
    newcomer = max(scored, key=lambda m: m["score"]["mape"] if m["name"] != worst else -1)["name"]
    lucky = record(three[:2], {k: v for k, v in everyone.items() if k != newcomer}) + \
        record(three[2:], dict(everyone, **{newcomer: 0.001}))
    y = sanity_forecasts(monthly, horizon=2, big=big, results=lucky)
    ok(y["ranked_on"] == "backtest" and y["closed_months"] == 3 and y["record_waiting"] == {newcomer: 1},
       "the months that have closed, and who the record is waiting on: %s %s" % (y["closed_months"], y["record_waiting"]))
    ok(r["record_waiting"] == {} and backtest["record_waiting"] == {}, "and nobody, once it is on the record or before")
    ok(pick_opinions(y)[0]["name"] == y["best"] == leader == _page_lead(y), "one lucky month leads nothing")
    # And the same without the run's order, as an older run reads: the
    # page's own comparison still agrees, because every method is on the
    # record or none is.
    for res in (r, y, backtest):
        bare = {k: v for k, v in res.items() if k != "ranking"}
        ok(_page_lead(bare) == res["ranking"][0], "the page's own sort agrees: %s" % _page_lead(bare))
    # The track-record weighting is built from the sources with a record; with
    # every method on the record it is a row like the rest, young or not, and
    # the page and the panel still agree on who leads.
    weighted = [m for m in r["models"] if m["name"] == "Weighted by track record"]
    ok(weighted and "live" not in weighted[0], "a weighting with no record of its own shows none yet")
    more = record(three + ("2026-01",), dict(everyone, **{"Weighted by track record": 0.0001}))
    w = sanity_forecasts(monthly, horizon=2, big=big, results=more)
    ok(w["ranked_on"] == "record" and pick_opinions(w)[0]["name"] == _page_lead(w), (w["best"], _page_lead(w)))


@test
def t_the_evaluation_marks_each_cut_off_only_on_months_after_it():
    """`python -m forecast evaluate` replays the panel at every cut-off. A
    replay that could see ahead would flatter every source, so each cut-off's
    forecasts must not move when the months after it do."""
    import forecast.simple as fs
    from forecast.evaluate import PANEL, evaluate, history_floor, metrics, report, series_from_orders
    orders, as_of = _invented_shop()
    monthly, big, _ = series_from_orders(orders, as_of)
    rows = evaluate(monthly, big, None, first_cut=24, h=3)
    ok(fs.MIN_MONTHS == 24, "the panel's own floor is put back")
    ok(sorted(rows["cut"].unique()) == list(range(24, 30)), sorted(rows["cut"].unique()))
    ok((rows["month"] > rows["origin"]).all(), "every month marked comes after its cut-off")
    ok(rows.groupby(["source", "cut"])["h"].max().max() == 3 and
       (rows[rows["cut"] == 29]["h"] == 1).all(), "up to three months ahead, fewer at the end")
    picks = rows[rows["source"] == PANEL]
    ok(sorted(picks["cut"].unique()) == [27, 28, 29] and picks["lo"].notna().all(),
       "the panel picks once it has a fold to rank on, with its range")
    ok(set(picks["pick"]) <= set(rows["source"]), "and the pick is one of the rows")
    later = monthly.copy()
    later.iloc[27:] *= 3                     # the last three months, very different
    moved = evaluate(later, big, None, first_cut=24, h=3)
    key = ["source", "cut", "h"]
    a = rows[rows["cut"] <= 27].set_index(key)["forecast"].sort_index()
    b = moved[moved["cut"] <= 27].set_index(key)["forecast"].sort_index()
    ok(a.index.equals(b.index) and np.allclose(a.values, b.values), "no cut-off's forecast saw the months after it")
    # The same with the big orders after a cut-off changed too, from a floor
    # low enough that the compared cut-offs have folds and picks: nothing any
    # of them said moves, the pick and its range included.
    a = evaluate(monthly, big, None, first_cut=22, h=3)
    big2 = big.copy()
    big2.iloc[27:] *= 5
    b = evaluate(later, big2, None, first_cut=22, h=3)
    ka = a[a["cut"] <= 27].set_index(key)[["forecast", "lo", "hi"]].sort_index()
    kb = b[b["cut"] <= 27].set_index(key)[["forecast", "lo", "hi"]].sort_index()
    ok(ka.index.equals(kb.index) and np.allclose(ka.fillna(-1).values, kb.fillna(-1).values),
       "nor did the big orders after it, for any source, the pick or a range")
    ok({25, 26, 27} <= set(a[a["source"] == PANEL]["cut"]), "and the compared cut-offs include picks")
    ok("ranked_on" in a.columns and (a[a["source"] == PANEL]["ranked_on"] > 0).all(), "each pick says what it ranked on")
    # The panel as it was, on the same history: put back afterwards.
    from forecast.evaluate import as_before
    level, p80 = fs.big_level, fs._p80
    with as_before():
        old = evaluate(monthly, big, None, first_cut=24, h=3)
    ok(fs.big_level is level and fs._p80 is p80, "the panel's own scoring is put back")
    oa = old[old["source"] == "Big orders counted apart"].set_index(key)["forecast"]
    na = rows[rows["source"] == "Big orders counted apart"].set_index(key)["forecast"]
    ok(not np.allclose(oa.sort_index().values, na.sort_index().values), "and as it was, big orders were their average")
    perfect = rows.assign(forecast=rows["actual"], lo=rows["actual"], hi=rows["actual"])
    m = metrics(perfect)
    ok(m["WAPE"] == 0 and m["bias"] == 0 and m["MASE"] == 0 and m["in range"] == 1.0, m)
    text = report(rows)
    for part in ("Every source on the same forecasts (", "WAPE (and bias) by months ahead",
                 "WAPE (and bias) by the half-year marked", "The panel's pick at each cut-off",
                 "The panel's pick against every source on the forecasts it made (6 forecasts of 3 months",
                 "WAPE (and bias) by month marked, the pick and the three closest",
                 "The pick's five largest misses", "Baseline: same month last year"):
        ok(part in text, part)
    try:
        with history_floor(5):
            raise KeyError("x")
    except KeyError:
        pass
    ok(fs.MIN_MONTHS == 24, "put back even when the replay fails")


@test
def t_the_evaluate_command_runs_on_an_orders_file():
    import contextlib, io, json as _json, tempfile
    from forecast.pipeline import main
    orders, as_of = _invented_shop()
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "orders.json")
        with open(path, "w") as fh:
            _json.dump({"orders": orders}, fh)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main(["evaluate", "--orders", path, "--as-of", as_of.isoformat(), "--first-cut", "26",
                       "--no-prophet", "--csv", os.path.join(tmp, "rows.csv")])
        rows = pd.read_csv(os.path.join(tmp, "rows.csv"))
    text = out.getvalue()
    ok(rc == 0 and text.startswith("30 complete months, 2023-07 to 2025-12."), text[:200])
    with tempfile.TemporaryDirectory() as tmp:
        empty = os.path.join(tmp, "empty.json")
        with open(empty, "w") as fh:
            _json.dump([], fh)
        out2 = io.StringIO()
        with contextlib.redirect_stdout(out2):
            rc2 = main(["evaluate", "--orders", empty, "--as-of", as_of.isoformat()])
    ok(rc2 == 1 and "nothing to evaluate" in out2.getvalue(), "an empty file says so: %r" % out2.getvalue())
    if _have_prophet():
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "orders.json")
            with open(path, "w") as fh:
                _json.dump(orders, fh)
            out3 = io.StringIO()
            with contextlib.redirect_stdout(out3):
                main(["evaluate", "--orders", path, "--as-of", as_of.isoformat(), "--first-cut", "28", "--as-before"])
        ok("Daily trend" not in out3.getvalue() and "Last year and daily trend" not in out3.getvalue(),
           "as it was is without Prophet, even where Prophet is installed")
    ok("Cut-offs 2025-08 to 2025-11 (4)" in text and "The panel's pick" in text, text[:400])
    ok(set(rows["cut"]) == {26, 27, 28, 29}, "every marked month is in the file")


@test
def t_the_nightly_job_and_the_seeded_world_hand_the_panel_the_regular_days():
    """Prophet's sources only exist when the panel is given the regular orders
    by day. The job builds them from the same orders as the months, and the
    browser suite's seeded world runs the same maths."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for rel in ("forecast/nightly.py", "tests/browser/seed/dashboards.py"):
        src = open(os.path.join(root, rel), encoding="utf-8").read()
        call = src.split("sanity = sanity_forecasts(", 1)[1][:160]
        ok("big=big" in call and "daily_small=daily_small" in call, "%s: %s" % (rel, call))
    nightly = open(os.path.join(root, "forecast/nightly.py"), encoding="utf-8").read()
    ok("daily_small = daily_cash(orders, as_of, max_total=BIG_ORDER)" in nightly,
       "the job hands the days over, so switching Prophet on needs only its lock")
    seed = open(os.path.join(root, "tests/browser/seed/dashboards.py"), encoding="utf-8").read()
    ok("daily_small = None" in seed and "max_total=BIG_ORDER" not in seed,
       "and the seeded world, like the image, has no Prophet, on any machine")
    ok("No method could be scored yet" in nightly and "no source could" not in nightly,
       "a run too young to rank says method, and why")


if __name__ == "__main__":
    passed = 0
    for fn in TESTS:
        try:
            fn(); passed += 1; print("  PASS ", fn.__name__)
        except Exception as e:
            print("  FAIL ", fn.__name__, "-", e)
    print(f"\n{passed} passed, {len(TESTS) - passed} failed")
    sys.exit(0 if passed == len(TESTS) else 1)
