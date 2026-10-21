"""The overview and customer reports: the analysis cache (each report's last
result and what changed since), the overview's figures, trends and sector
sales, customers and retention, the reorder radar and sector tags, and the
money and gather helpers they share with SEO. Moved out of copilot.py (stage
4 of the 14 October audit); its routes are in gizmo/routes/analytics.py.
Read as `analytics.NAME` (`reports` is a local name in a dispatch route).
"""
import logging
import os
import re
import json
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
import google_data
from gizmo.config import _env_num
from gizmo import store as jsonstore
from gizmo import ai as claude
from gizmo import shopify
from gizmo import orderbook

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


# History windows for trend charts + product analytics. Up to 24 months of
# Shopify order history is paginated for the Products tab and product detail;
# Google (GA4/GSC) timeseries are single calls. ORDER_PAGE_CAP bounds how many
# 250-order pages we will page through so the request stays responsive.
TREND_MONTHS = _env_num(int, os.environ.get("TREND_MONTHS", "24"), "24", "TREND_MONTHS")
ANALYSIS_CACHE_PATH      = os.environ.get("ANALYSIS_CACHE_PATH", "/data/analysis_cache.json")  # last result per AI tab
ANALYSIS_CACHE_MAX_BYTES = _env_num(int, os.environ.get("ANALYSIS_CACHE_MAX_BYTES", "800000"), "800000", "ANALYSIS_CACHE_MAX_BYTES")  # per-entry size guard


# ---------------------------------------------------------------------------
# Analysis cache: the last result of each AI tab (overview/seo/keywords/
# customers), persisted so reopening the app shows it instantly without
# spending tokens. The merchant clicks Refresh on a tab to recompute.
# ---------------------------------------------------------------------------


_ANALYSIS_KINDS = ("overview", "seo", "keywords", "customers")


def _load_analysis_cache() -> dict:
    data = jsonstore._load_json_store(ANALYSIS_CACHE_PATH, None, {})
    return data if isinstance(data, dict) else {}


def _parse_num(v):
    """Best-effort number out of a formatted metric value ('$12,345', '24%', '1.2k', '3x')."""
    s = str(v).strip().lower().replace(",", "")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return None
    num = float(m.group(0))
    # Apply a k/m multiplier ONLY when it directly abuts the digits and is not the start
    # of a word. Otherwise a currency code hijacks it: "0.42 MXN" -> 420000, "1234 KRW"
    # -> 1,234,000. Note "3.2x" (ROAS) must stay 3.2.
    mult = re.match(r"([km])(?![a-z])", s[m.end():])
    if mult:
        num *= 1000 if mult.group(1) == "k" else 1_000_000
    return num


def _metric_snapshot(result: dict) -> dict:
    """A compact {label: number} snapshot of a result's KPIs, for run-over-run diffs."""
    snap = {}
    for m in (result.get("metrics") or []):
        if isinstance(m, dict) and m.get("label"):
            n = _parse_num(m.get("value"))
            if n is not None:
                snap[str(m["label"])] = n
    if isinstance(result.get("score"), (int, float)):
        snap["SEO score"] = float(result["score"])
    return {"at": datetime.now(timezone.utc).isoformat(), "metrics": snap}


def _compute_changes(cur: dict, prev: dict) -> list:
    """Per-metric deltas for labels present in both snapshots (skips unchanged)."""
    out = []
    for label, c in cur.items():
        if label in prev:
            p = prev[label]
            if c == p:
                continue
            pct = None if not p else round((c - p) / abs(p) * 100, 1)
            out.append({"label": label, "prev": p, "cur": c, "pct": pct})
    return out


def _with_changes(result: dict, prev_snap: dict, new_snap: dict) -> dict:
    """Attach 'changes' + 'changes_since' to a result, computed vs the previous run."""
    if prev_snap and prev_snap.get("at"):
        return {**result, "changes": _compute_changes(new_snap.get("metrics", {}),
                                                       prev_snap.get("metrics", {})),
                "changes_since": prev_snap["at"]}
    return result


def _save_analysis(kind: str, result: dict) -> dict:
    """Persist the latest result for a tab and return it augmented with run-over-run
    changes. Best-effort: never raises, so a disk problem can't break the response."""
    if kind not in _ANALYSIS_KINDS or not isinstance(result, dict) or result.get("error"):
        return result
    try:
        snap = _metric_snapshot(result)
        cache = _load_analysis_cache()
        prev = (cache.get(kind) or {}).get("snapshot") or {}
        result = _with_changes(result, prev, snap)
        blob = json.dumps(result, default=str)
        if len(blob) > ANALYSIS_CACHE_MAX_BYTES:
            logger.warning("analysis cache: %s result too large (%d bytes); not caching", kind, len(blob))
            return result
        cache[kind] = {"result": json.loads(blob), "at": datetime.now(timezone.utc).isoformat(), "snapshot": snap}
        if not jsonstore._store_writable(ANALYSIS_CACHE_PATH):
            return result
        jsonstore._write_json_store(ANALYSIS_CACHE_PATH, None, cache)
    except Exception:
        logger.exception("analysis cache: failed to save %s", kind)
    return result


def _save_customer_segment(seg_key: str, result: dict) -> dict:
    """Persist a customer audit per sector (key '__all__' for the comprehensive run) and
    return it augmented with run-over-run changes. Best-effort: never raises."""
    if not isinstance(result, dict) or result.get("error"):
        return result
    key = str(seg_key)[:80]
    try:
        snap = _metric_snapshot(result)
        cache = _load_analysis_cache()
        segs = cache.get("customers_segments")
        if not isinstance(segs, dict):
            segs = {}
        prev = (segs.get(key) or {}).get("snapshot") or {}
        result = _with_changes(result, prev, snap)
        blob = json.dumps(result, default=str)
        if len(blob) > ANALYSIS_CACHE_MAX_BYTES:
            logger.warning("analysis cache: customers/%s result too large; not caching", seg_key)
            return result
        segs[key] = {"result": json.loads(blob), "at": datetime.now(timezone.utc).isoformat(), "snapshot": snap}
        if len(segs) > 24:  # keep the most recently refreshed sectors
            segs = dict(sorted(segs.items(), key=lambda kv: kv[1].get("at", ""), reverse=True)[:24])
        cache["customers_segments"] = segs
        if not jsonstore._store_writable(ANALYSIS_CACHE_PATH):
            return result
        jsonstore._write_json_store(ANALYSIS_CACHE_PATH, None, cache)
    except Exception:
        logger.exception("analysis cache: failed to save customer segment %s", seg_key)
    return result


# ---------------------------------------------------------------------------
# Overview — live KPIs (computed deterministically) + AI insight pass
# ---------------------------------------------------------------------------


def _money(amount: float, currency: str) -> str:
    """Whole units the way the page writes money: '£1,735', never '1,735 GBP'.
    The KPI tiles took this string as it came while the charts, tables and
    product pages beside them formatted with the page's own £ rule, so one
    screen printed the same currency two ways."""
    try:
        sign = "-" if amount < 0 else ""
        sym = core._CURRENCY_SIGNS.get((currency or "").upper())
        body = f"{abs(amount):,.0f}"
        return f"{sign}{sym}{body}" if sym else f"{sign}{body} {currency}".strip()
    except Exception:
        return f"{amount} {currency}".strip()


def _delta(cur: float, prev: float) -> tuple[Optional[str], str]:
    if prev <= 0:
        return (None, "flat")
    change = (cur - prev) / prev * 100
    trend = "up" if change > 1 else "down" if change < -1 else "flat"
    return (f"{'+' if change >= 0 else ''}{change:.0f}%", trend)


async def _ret(value=None):
    """A pre-resolved coroutine so optional calls can still join an asyncio.gather()."""
    return value


async def _compute_metrics(registry: dict, track_inventory: bool = True) -> tuple[list[dict], dict]:
    now = datetime.now(timezone.utc)
    d7, d14 = (now - timedelta(days=7)).isoformat(), (now - timedelta(days=14)).isoformat()
    metrics: list[dict] = []

    # Pull every independent input at once (Shopify reads + Google), then compute.
    ga4_on, gsc_on = google_data.ga4_configured(), google_data.gsc_configured()
    # Both weeks from one paged read, split by date: a single page of 250 per
    # week cut a busy week off, and only the AI was told ("up to 250").
    m14: dict = {}
    shop, o14, custr, cntr, prodr, ga, gsc = await asyncio.gather(
        shopify._tool_json(registry, "shopify_get_shop", {}),
        orderbook._paginate_orders(registry, days=14, meta=m14,
                         fields="id,created_at,total_price,current_total_price,cancelled_at,test,"
                                "financial_status,fulfillment_status,line_items"),
        shopify._tool_json(registry, "shopify_list_customers", {"created_at_min": d7, "limit": 250}),
        shopify._tool_json(registry, "shopify_count_products", {}),
        core._all_products(registry, "id,title,variants") if track_inventory else _ret(([], True, False)),
        google_data.ga4_summary(28) if ga4_on else _ret({}),
        google_data.gsc_overview(28) if gsc_on else _ret({}),
    )
    shop = shop or {}
    currency = shop.get("currency", "")
    orders_ok = not m14.get("failed")
    week_start = now - timedelta(days=7)

    def _placed(o):
        try:
            t = datetime.fromisoformat(str(o.get("created_at") or "").replace("Z", "+00:00"))
            return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    o7 = [o for o in o14 if orderbook._order_counts(o) and (_placed(o) or now) >= week_start]
    op = [o for o in o14 if orderbook._order_counts(o) and _placed(o) is not None and _placed(o) < week_start]
    rev7 = sum(orderbook._order_revenue(o) for o in o7)
    revp = sum(orderbook._order_revenue(o) for o in op)
    n7, npv = len(o7), len(op)
    aov = rev7 / n7 if n7 else 0
    unfulfilled = sum(1 for o in o7 if o.get("fulfillment_status") in (None, "partial", "unfulfilled"))

    # Only publish a metric when its source fetch actually succeeded. A throttled or
    # errored Shopify call must not surface as a real 0 (it would poison the saved
    # snapshot and fire a bogus "-100%" change alert on the next run).
    stale: list[str] = []
    rev_delta, rev_trend = _delta(rev7, revp)
    ord_delta, ord_trend = _delta(n7, npv)
    if orders_ok:
        metrics.append({"label": "Revenue (7d)", "value": _money(rev7, currency), "delta": rev_delta, "trend": rev_trend})
        metrics.append({"label": "Orders (7d)", "value": str(n7), "delta": ord_delta, "trend": ord_trend})
        metrics.append({"label": "Average order value (7d)", "value": _money(aov, currency)})
        metrics.append({"label": "Unfulfilled (7d)", "value": str(unfulfilled), "tone": "warn" if unfulfilled else None})
    else:
        stale.append("orders")

    new_cust = len(custr.get("customers", []))
    if shopify._ok(custr):
        metrics.append({"label": "New customers (7d)", "value": str(new_cust)})
    else:
        stale.append("customers")

    total_products = cntr.get("count")
    if shopify._ok(cntr) and total_products is not None:
        metrics.append({"label": "Products", "value": str(total_products)})

    low = []
    # Every product, not the first 250: the low-stock count read one page.
    products, prod_ok, _prod_cut = prodr
    if track_inventory and not prod_ok:
        stale.append("inventory")
    elif track_inventory:
        low = [
            {"product": p.get("title"), "variant": v.get("title"), "qty": v.get("inventory_quantity")}
            for p in products for v in p.get("variants", [])
            if isinstance(v.get("inventory_quantity"), int) and v["inventory_quantity"] <= core.LOW_STOCK_THRESHOLD
        ]
        metrics.append({"label": f"Low stock (≤{core.LOW_STOCK_THRESHOLD})", "value": str(len(low)),
                        "tone": "warn" if low else None})

    from collections import Counter
    units = Counter()
    for o in o7:
        for li in o.get("line_items", []):
            if li.get("title"):
                units[li["title"]] += li.get("quantity") or 0

    context = {
        "shop": {"name": shop.get("name"), "currency": currency},
        "last_7d": {"revenue": round(rev7, 2), "orders": n7, "aov": round(aov, 2),
                    "unfulfilled": unfulfilled, "new_customers": new_cust},
        "prev_7d": {"revenue": round(revp, 2), "orders": npv},
        "catalog": ({"total_products": total_products, "low_stock_count": len(low),
                     "low_stock_examples": low[:8]} if track_inventory
                    else {"total_products": total_products, "inventory": "not tracked, unlimited stock"}),
        "top_products_7d": [{"title": t, "units": q} for t, q in units.most_common(5)],
        "note": ("Order figures are complete for both weeks." if not m14.get("truncated") else
                 "The order read stopped at its page limit, so the busiest days may be missing."),
    }
    if stale:
        context["data_warning"] = (
            "These Shopify reads failed on this run and are NOT included: " + ", ".join(stale)
            + ". Do not treat the missing areas as zero; say the data was unavailable.")

    # Real traffic + search performance (only when Google is connected).
    if ga4_on and ga and not ga.get("error"):
        metrics.append({"label": "Sessions (GA4, 28d)", "value": f"{ga['sessions']:,}"})
        metrics.append({"label": "Revenue (GA4, 28d)", "value": _money(ga["revenue"], currency)})
        context["ga4_28d"] = ga
    elif ga4_on and isinstance(ga, dict) and ga.get("error"):
        context["ga4_28d"] = ga
    if gsc_on and gsc and not gsc.get("error"):
        metrics.append({"label": "Search clicks (28d)", "value": f"{gsc['clicks']:,}"})
        metrics.append({"label": "Search impressions (28d)", "value": f"{gsc['impressions']:,}"})
        if gsc.get("position") is not None:
            metrics.append({"label": "Avg Google position", "value": str(gsc["position"])})
        context["search_console_28d"] = gsc
    elif gsc_on and isinstance(gsc, dict) and gsc.get("error"):
        context["search_console_28d"] = gsc

    return [m for m in metrics if m.get("value") is not None], context


async def _sector_sales(registry: dict, days: int = 28) -> list:
    """Revenue / orders / AOV for the period, split by customer-account tag (the
    merchant's sectors). Returns [] when no tags are in use. Never raises."""
    try:
        cmeta: dict = {}
        ometa: dict = {}
        customers, orders = await asyncio.gather(
            _paginate_customers(registry, meta=cmeta),
            orderbook._orders_snapshot(registry, days=days,
                             fields="id,total_price,current_total_price,created_at,customer,"
                                    "cancelled_at,test,financial_status", meta=ometa),
        )
        if cmeta.get("failed") or ometa.get("failed"):
            return []        # no split rather than a split of zeros
        tags = _detect_sector_tags(customers)
        if not tags:
            return []
        cid_tags = {}
        for c in customers:
            cid = c.get("id")
            if cid is not None:
                cid_tags[cid] = [t.lower() for t in _customer_tags(c)]
        wanted = {t["tag"].lower(): t["tag"] for t in tags}
        agg = {t["tag"]: {"sector": t["tag"], "revenue": 0.0, "orders": 0} for t in tags}
        for o in orders:
            if not orderbook._order_counts(o):
                continue
            cid = (o.get("customer") or {}).get("id")
            rev = orderbook._order_revenue(o)
            # Attribute each order to ONE sector (the highest-ranked matching tag), so a
            # customer tagged e.g. "Wholesale, VIP" cannot count their revenue twice and
            # the sector rows still sum to at most store revenue.
            for lt in cid_tags.get(cid, []):
                if lt in wanted:
                    a = agg[wanted[lt]]
                    a["revenue"] += rev
                    a["orders"] += 1
                    break
        out = [{"sector": t["tag"], "revenue": round(agg[t["tag"]]["revenue"], 2),
                "orders": agg[t["tag"]]["orders"],
                "aov": round(agg[t["tag"]]["revenue"] / agg[t["tag"]]["orders"], 2) if agg[t["tag"]]["orders"] else 0,
                "days": days} for t in tags]
        out.sort(key=lambda x: x["revenue"], reverse=True)
        return out
    except Exception:
        logger.exception("sector sales failed")
        return []


async def run_overview(registry: dict, extra_system: str = "", track_inventory: bool = True) -> dict:
    claude._ai_kind.set("overview")
    metrics, context = await _compute_metrics(registry, track_inventory)
    client = claude._anthropic()
    msg = ("Current store KPIs (computed live):\n" + json.dumps(context, indent=2, default=str)
           + "\n\nGive the executive overview now by calling present_response.")
    # Fetch the chart data + sector sales WHILE the model writes the analysis (free wall-clock).
    resp, trends, sector_sales = await asyncio.gather(
        claude._xcreate(client,
            model=claude.MODEL_DEEP, max_tokens=claude.MAX_TOKENS, system=prompts.OVERVIEW_SYSTEM + extra_system,
            tools=[prompts.PRESENT_RESPONSE_TOOL], tool_choice={"type": "tool", "name": prompts.PRESENT_RESPONSE_TOOL["name"]},
            messages=[{"role": "user", "content": msg}],
            output_config={"effort": core._effort_for(claude.MODEL_DEEP)},
        ),
        _overview_trends(registry),
        _sector_sales(registry),
    )
    structured = assistant._coerce_structured(prompts._report_answer(resp, "the overview"))
    structured.pop("metrics", None)  # UI shows the computed metrics, not Claude's echo
    currency = (context.get("shop") or {}).get("currency", "")
    return {"metrics": metrics, "structured": structured, "trends": trends,
            "currency": currency, "sector_sales": sector_sales}


async def _overview_trends(registry: dict) -> dict:
    """Monthly revenue + sessions + search clicks for the trend charts. Prefers
    Google (single cheap calls, up to 24/16 months); falls back to Shopify orders
    for revenue when Google is not connected. Always degrades to {} gracefully."""
    trends: dict = {}
    months = orderbook._month_axis(min(TREND_MONTHS, 12))
    ga4_on, gsc_on = google_data.ga4_configured(), google_data.gsc_configured()
    # Fetch the Shopify order history and both Google timeseries at once.
    orders, ts, gts = await asyncio.gather(
        orderbook._orders_snapshot(registry, days=len(months) * 31),
        google_data.ga4_timeseries(min(TREND_MONTHS, 24) * 31) if ga4_on else _ret({}),
        google_data.gsc_timeseries(480) if gsc_on else _ret({}),
        return_exceptions=True,
    )
    # Shopify monthly revenue + orders + average order value.
    try:
        if isinstance(orders, Exception):
            raise orders
        rev = {mk: 0.0 for mk in months}
        cnt = {mk: 0 for mk in months}
        for o in orders:
            if not orderbook._order_counts(o):
                continue
            mk = orderbook._month_key(o.get("created_at"))
            if mk in rev:
                rev[mk] += orderbook._order_revenue(o)
                cnt[mk] += 1
        if any(rev[mk] for mk in months):
            trends["revenue"] = [{"label": mk, "value": round(rev[mk], 2)} for mk in months]
            trends["orders"] = [{"label": mk, "value": cnt[mk]} for mk in months]
            # A month with no orders has no average order value. Zero drew the
            # line down to the floor for every quiet month, and the card's
            # mean of monthly ratios counted those zeros: 261 against a real
            # 1,024 for the year.
            trends["aov"] = [{"label": mk, "value": round(rev[mk] / cnt[mk], 2) if cnt[mk] else None} for mk in months]
    except Exception:
        logger.exception("overview shopify trends failed")
    # Google Analytics 4: sessions, pageviews, engaged, channel mix (+ revenue fallback).
    try:
        if ga4_on and isinstance(ts, dict) and not ts.get("error"):
            for k in ("sessions", "pageviews", "engaged"):
                if ts.get(k):
                    trends[k] = ts[k]
            if ts.get("channels"):
                trends["channels"] = ts["channels"]
            if "revenue" not in trends and ts.get("revenue") and any(p.get("value") for p in ts["revenue"]):
                trends["revenue"] = ts["revenue"]
    except Exception:
        logger.exception("overview ga4 trends failed")
    # Search Console: clicks, impressions, CTR, average position.
    try:
        if gsc_on and isinstance(gts, dict) and not gts.get("error"):
            for k in ("clicks", "impressions", "ctr", "position"):
                if gts.get(k):
                    trends[k] = gts[k]
    except Exception:
        logger.exception("overview gsc trends failed")
    return trends


# ---------------------------------------------------------------------------
# Customers & retention analytics (from Shopify customers + orders)
# ---------------------------------------------------------------------------


async def _paginate_customers(registry: dict, max_pages: int = orderbook.ORDER_PAGE_CAP,
                              meta: Optional[dict] = None) -> list:
    fields = "id,first_name,last_name,email,orders_count,total_spent,created_at,updated_at,state,tags,default_address"
    out: list = []
    since_id, pages = 0, 0
    failed = truncated = False
    while pages < max_pages:
        res = await shopify._tool_json(registry, "shopify_list_customers",
                               {"limit": 250, "since_id": since_id, "fields": fields})
        if not shopify._ok(res):
            failed = True
            break
        batch = res.get("customers", [])
        if not batch:
            break
        out += batch
        pages += 1
        if len(batch) < 250:
            break
        since_id = max((c.get("id") or 0) for c in batch)
        if pages >= max_pages:
            truncated = True
    if meta is not None:
        meta["failed"], meta["truncated"] = failed, truncated
    return out


async def run_reorder_radar(registry: dict) -> dict:
    """Two lists from data the app already reads, no AI. (1) Overdue repeat
    accounts: customers with a rhythm of orders whose next one has not arrived;
    what they bought last makes the nudge concrete. (2) Untagged likely-B2B
    customers, so the sector analytics see the whole trade side."""
    om, cm = {}, {}
    orders, customers = await asyncio.gather(
        orderbook._orders_snapshot(registry, days=540, fields="id,name,created_at,customer,line_items", meta=om),
        _paginate_customers(registry, meta=cm))
    if om.get("failed") or cm.get("failed"):
        return {"error": "Couldn't read all your orders and customers from Shopify just now. "
                "The radar would be incomplete, so it is not shown. Try again in a moment."}
    if not isinstance(orders, list):
        orders = []
    cust_by_id = {c.get("id"): c for c in customers if c.get("id")}
    hist: dict = {}
    for o in orders:
        cid = (o.get("customer") or {}).get("id")
        if cid:
            hist.setdefault(cid, []).append(o)
    now = datetime.now(timezone.utc)
    overdue = []
    for cid, os_ in hist.items():
        if len(os_) < 2:
            continue
        os_.sort(key=lambda o: str(o.get("created_at") or ""))
        dates = []
        for o in os_:
            try:
                d = datetime.fromisoformat(str(o.get("created_at")).replace("Z", "+00:00"))
                dates.append(d if d.tzinfo else d.replace(tzinfo=timezone.utc))
            except Exception:
                pass
        if len(dates) < 2:
            continue
        gaps = sorted(max(1, (b - a).days) for a, b in zip(dates, dates[1:]))
        med = gaps[len(gaps) // 2]
        if med < 14 or med > 400:
            continue   # no meaningful rhythm to be overdue against
        since = (now - dates[-1]).days
        if since < med * 1.5:
            continue
        lasto = os_[-1]
        last_items = []
        for li in (lasto.get("line_items") or []):
            title = str(li.get("title") or "").strip()
            if production._label_skip_item(title):
                continue
            mfr = production._strip_price(production._item_prop(li, "Manufacturer"))
            model = production._strip_price(production._item_model(li, mfr))
            last_items.append(" ".join(x for x in [mfr, model] if x) or title)
            if len(last_items) >= 3:
                break
        c = cust_by_id.get(cid, {})
        comp = str((c.get("default_address") or {}).get("company") or "").strip()
        person = (str(c.get("first_name") or "").strip() + " " + str(c.get("last_name") or "").strip()).strip()
        overdue.append({
            "name": comp or person or str(c.get("email") or "Customer"),
            "email": str(c.get("email") or ""),
            "orders": len(os_), "median_days": med, "days_since": since,
            "overdue_by": since - med,
            "last_order": str(lasto.get("name") or ""), "last_at": lasto.get("created_at"),
            "last_items": last_items,
        })
    overdue.sort(key=lambda r: -r["overdue_by"])
    b2b = []
    for c in customers:
        if _customer_tags(c):
            continue
        comp = str((c.get("default_address") or {}).get("company") or "").strip()
        oc = int(c.get("orders_count") or 0)
        if not comp and oc < 3:
            continue
        person = (str(c.get("first_name") or "").strip() + " " + str(c.get("last_name") or "").strip()).strip()
        try:
            spent = float(c.get("total_spent") or 0)
        except (TypeError, ValueError):
            spent = 0.0
        b2b.append({"name": comp or person or str(c.get("email") or "Customer"),
                    "email": str(c.get("email") or ""), "orders": oc, "spent": spent,
                    "reason": ("Company name on file" if comp else str(oc) + " orders, never tagged")})
    b2b.sort(key=lambda r: -r["spent"])
    return {"overdue": overdue[:25], "untagged_b2b": b2b[:20],
            "customers_seen": len(customers), "orders_seen": len(orders),
            "truncated": bool(om.get("truncated") or cm.get("truncated"))}


def _customer_tags(c) -> list:
    """Normalize a customer's tags (Shopify REST returns a comma-joined string)."""
    t = c.get("tags")
    if isinstance(t, str):
        return [x.strip() for x in t.split(",") if x.strip()]
    return [str(x).strip() for x in (t or []) if str(x).strip()]


def _detect_sector_tags(customers: list, cap: int = 12) -> list:
    """Distinct customer tags actually in use, most common first (the merchant's sectors)."""
    counts: dict = {}
    for c in customers:
        for t in _customer_tags(c):
            counts[t] = counts.get(t, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))
    return [{"tag": t, "count": n} for t, n in ranked[:cap]]


async def run_customers(registry: dict, extra_system: str = "", segment: Optional[str] = None) -> dict:
    """Customer + retention intelligence: LTV, new vs returning, repeat rate, RFM-style
    segments, churn risk, top customers, and a new-customers trend, with an AI plan.
    With `segment` (a customer tag) the figures are filtered to that sector; otherwise the
    analysis covers all customers and compares the sectors."""
    claude._ai_kind.set("customers")
    months = orderbook._month_axis(12)
    cmeta: dict = {}
    ometa: dict = {}
    shop, all_customers, orders = await asyncio.gather(
        shopify._tool_json(registry, "shopify_get_shop", {}),
        _paginate_customers(registry, meta=cmeta),
        orderbook._orders_snapshot(registry, days=len(months) * 31, fields="id,created_at,customer", meta=ometa),
    )
    # A read that failed is not a store with no customers: analysed as one,
    # it showed zeros, paid the model to explain them, and saved them as the
    # baseline the next run's changes were measured from.
    if cmeta.get("failed") or ometa.get("failed"):
        return {"error": "Couldn't read all your customers and orders from Shopify just now "
                         "(it may be busy). The figures would be wrong, so nothing was worked "
                         "out and no AI credits were used. Try again in a moment."}
    shop = shop or {}
    currency = shop.get("currency", "")
    sector_tags = _detect_sector_tags(all_customers)
    seg_norm = (segment or "").strip()
    if seg_norm:
        low = seg_norm.lower()
        customers = [c for c in all_customers if low in [t.lower() for t in _customer_tags(c)]]
    else:
        customers = all_customers
    now = datetime.now(timezone.utc)

    last_order: dict = {}
    for o in orders:
        cid = (o.get("customer") or {}).get("id")
        if not cid:
            continue
        try:
            dt = datetime.fromisoformat((o.get("created_at") or "").replace("Z", "+00:00"))
        except Exception:
            continue
        if cid not in last_order or dt > last_order[cid]:
            last_order[cid] = dt

    seg: dict = {k: [] for k in ("champions", "loyal", "new", "at_risk", "one_time", "prospects")}
    new_by_month = {mk: 0 for mk in months}
    purchasers = repeat = 0
    spend_total = 0.0
    top: list = []
    cutoff30 = (now - timedelta(days=30)).isoformat()
    new_30 = 0
    for c in customers:
        oc = int(c.get("orders_count") or 0)
        try:
            ts = float(c.get("total_spent") or 0)
        except (TypeError, ValueError):
            ts = 0.0
        created = c.get("created_at") or ""
        if created[:7] in new_by_month:
            new_by_month[created[:7]] += 1
        if created >= cutoff30:
            new_30 += 1
        if oc >= 1:
            purchasers += 1
            spend_total += ts
        if oc >= 2:
            repeat += 1
        lo = last_order.get(c.get("id"))
        ds = (now - lo).days if lo else None
        name = (((c.get("first_name") or "") + " " + (c.get("last_name") or "")).strip()) or (c.get("email") or "Customer")
        rec = {"name": name, "email": c.get("email"), "orders": oc, "spent": round(ts, 2), "days_since": ds}
        top.append(rec)
        if oc == 0:
            seg["prospects"].append(rec)
        elif oc >= 3:
            (seg["champions"] if (ds is not None and ds <= 90) else seg["at_risk"]).append(rec)
        elif oc == 2:
            (seg["loyal"] if (ds is not None and ds <= 120) else seg["at_risk"]).append(rec)
        else:
            (seg["new"] if (ds is not None and ds <= 60) else seg["one_time"]).append(rec)

    top.sort(key=lambda x: x["spent"], reverse=True)
    total = len(customers)
    repeat_rate = round(repeat / purchasers * 100, 1) if purchasers else 0.0
    avg_ltv = round(spend_total / purchasers, 2) if purchasers else 0.0
    seg_defs = [("champions", "Champions", "3+ orders, active in 90 days"),
                ("loyal", "Loyal", "2 orders, active"),
                ("new", "New", "First order in last 60 days"),
                ("at_risk", "At risk", "Repeat buyers who have gone quiet"),
                ("one_time", "One and done", "One older order, no repeat"),
                ("prospects", "Prospects", "Account created, no orders yet")]
    segments = [{"key": k, "name": n, "desc": d, "count": len(seg[k]),
                 "revenue": round(sum(r["spent"] for r in seg[k]), 2)} for k, n, d in seg_defs]
    metrics = [
        {"label": "Customers", "value": f"{total:,}"},
        {"label": "Repeat rate", "value": (f"{repeat_rate:g}" if float(repeat_rate).is_integer() else f"{repeat_rate:.1f}") + "%"},
        {"label": "Average lifetime value", "value": _money(avg_ltv, currency)},
        {"label": "New (30d)", "value": f"{new_30:,}"},
        {"label": "At risk", "value": f"{len(seg['at_risk']):,}", "tone": "warn" if seg["at_risk"] else None},
    ]
    trends = {"new_customers": [{"label": mk, "value": new_by_month[mk]} for mk in months]}
    totals = {"customers": total, "purchasers": purchasers, "repeat_rate_pct": repeat_rate,
              "avg_ltv": avg_ltv, "new_30d": new_30, "lifetime_revenue": round(spend_total, 2)}
    # Comprehensive runs compute a compact per-sector comparison from the raw tags.
    sector_comparison = []
    if not seg_norm:
        for tg in sector_tags:
            low = tg["tag"].lower()
            sub = [c for c in all_customers if low in [t.lower() for t in _customer_tags(c)]]
            pur = sum(1 for c in sub if int(c.get("orders_count") or 0) >= 1)
            rep = sum(1 for c in sub if int(c.get("orders_count") or 0) >= 2)
            sp = sum(float(c.get("total_spent") or 0) for c in sub if int(c.get("orders_count") or 0) >= 1)
            sector_comparison.append({"sector": tg["tag"], "customers": len(sub),
                                      "repeat_rate": round(rep / pur * 100, 1) if pur else 0.0,
                                      "avg_ltv": round(sp / pur, 2) if pur else 0.0,
                                      "lifetime_revenue": round(sp, 2)})
    context = {"currency": currency, "totals": totals,
               "segments": [{k: s[k] for k in ("name", "count", "revenue")} for s in segments],
               "top_customers": top[:15]}
    if seg_norm:
        context["sector"] = seg_norm
        msg = ("Customer and retention data for the '" + seg_norm + "' customer sector, filtered to customers "
               "carrying that tag (collected live):\n" + json.dumps(context, indent=2, default=str)
               + "\n\nEvery figure here is for the '" + seg_norm + "' sector only. Produce a retention-focused, "
                 "money-ranked plan for THIS sector via present_response: lead with the highest-value `actions` "
                 "(win back at-risk repeat buyers, convert one-time into repeat, lift repeat rate and lifetime "
                 "value), each with supporting numbers and expected impact; use `insights` for who the best "
                 "customers in this sector are and where retention leaks. Quantify in money or percent.")
    else:
        context["sector_comparison"] = sector_comparison
        context["note"] = ("Customers and orders are paginated up to a cap; very large stores may be truncated. "
                           "Some customers carry no sector tag or several.")
        msg = ("Store-wide customer and retention data, with a per-sector breakdown by customer tag (collected "
               "live):\n" + json.dumps(context, indent=2, default=str)
               + "\n\nProduce a comprehensive, money-ranked retention plan via present_response that COMPARES the "
                 "sectors in `sector_comparison`: state which sector has the strongest and weakest retention and "
                 "lifetime value, where the biggest revenue opportunity sits, and give per-sector actions. Use "
                 "`insights` for the key cross-sector findings and `actions` for prioritized moves, each with "
                 "expected impact in money or percent.")
    client = claude._anthropic()
    resp = await claude._xcreate(client,
        model=claude.MODEL_DEEP, max_tokens=claude.MAX_TOKENS, system=prompts.OVERVIEW_SYSTEM + extra_system,
        tools=[prompts.PRESENT_RESPONSE_TOOL], tool_choice={"type": "tool", "name": prompts.PRESENT_RESPONSE_TOOL["name"]},
        messages=[{"role": "user", "content": msg}],
        output_config={"effort": core._effort_for(claude.MODEL_DEEP)},
    )
    structured = assistant._coerce_structured(prompts._report_answer(resp, "the customer analysis"))
    structured.pop("metrics", None)
    return {"metrics": metrics, "structured": structured, "currency": currency,
            "segments": segments, "top_customers": top[:25], "trends": trends, "totals": totals,
            "segment": seg_norm or None, "sector_comparison": sector_comparison, "sector_tags": sector_tags}


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as core.NAME and sibling.NAME, never a copied name.
from gizmo import production  # noqa: E402
from gizmo import prompts  # noqa: E402
import copilot as core  # noqa: E402
from gizmo import chat as assistant  # noqa: E402
