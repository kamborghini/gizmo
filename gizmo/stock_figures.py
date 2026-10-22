"""The stock sheet's figures, worked out exactly as the stock app works them
out: a port of its analytics, function by function, over plain records
instead of a database session.

Every formula, every rounding point and every ordering is the stock app's,
because the converter proves each figure against the stock app's own to the
penny. Python's round is kept (half to even on binary floats: 2.675 rounds
to 2.67), as are the places the stock app reads a column with `or 0`.

The order the items arrive in matters, as it does there: a sort keeps tied
lines in the order they came, and money is summed in that order. Callers
pass items in id order, which is the order the export pins the stock app's
reads to. The one place the stock app's order is chance (the movers in a
comparison come out of a set) is taken in key order here.

Pure: no store, no clock, nothing from the app.
"""
import math
from datetime import datetime, timezone

DEFAULT_FX = {"USD": 0.79, "EUR": 0.86}
QUARTER_DAYS = 90
LOW_STOCK_DAYS = 21  # flag items forecast to run out within this many days
SAFETY_DAYS = 14     # buffer on top of a supplier's lead time when proposing a reorder point


# ---- one line --------------------------------------------------------------

def item_name(item: dict) -> str:
    return " ".join(b for b in (item.get("sub_category"), item.get("size")) if b).strip()


# Written-off stock is carried at ZERO book value (matches the source sheet);
# its real sunk cost is reported separately via unit_cost_gbp.
def current_value(item: dict) -> float:
    return 0.0 if item["written_off"] else round(item["current"] * (item["unit_cost_gbp"] or 0), 2)


def used_value(item: dict) -> float:
    return 0.0 if item["written_off"] else round(item["used"] * (item["unit_cost_gbp"] or 0), 2)


def start_value(item: dict) -> float:
    return 0.0 if item["written_off"] else round(item["start"] * (item["unit_cost_gbp"] or 0), 2)


def item_view(item: dict) -> dict:
    """The line as the stock app hands it out (its Item.to_dict)."""
    return {
        "id": item["id"], "key": item["key"], "category": item["category"],
        "sub_category": item["sub_category"], "size": item["size"], "notes": item["notes"],
        "name": item_name(item), "written_off": item["written_off"], "barcode": item["barcode"],
        "supplier": item["supplier"], "currency": item["currency"], "unit_cost": item["unit_cost"],
        "unit_cost_gbp": item["unit_cost_gbp"], "start": item["start"], "received": item["received"],
        "used": item["used"], "current": item["current"], "reorder_point": item["reorder_point"],
        "reorder_qty": item["reorder_qty"], "on_order": item["on_order"],
        "start_value": start_value(item), "used_value": used_value(item), "current_value": current_value(item),
        "updated_at": item.get("updated_at"),
    }


def _label(item: dict) -> str:
    return f"{item['category']} / {item_name(item)}"


def _instant(iso: str) -> datetime:
    t = datetime.fromisoformat(iso)
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _r2(n: float) -> float:
    return round(n, 2)


# ---- comparing two quarters ------------------------------------------------

def side_live(items: list, periods: list = None) -> dict:
    """The live sheet as one side of a comparison, labelled by the open quarter."""
    open_ = [p for p in (periods or []) if p.get("closed_at") is None]
    cp = max(open_, key=lambda p: _instant(p["opened_at"])) if open_ else None
    return {"label": (cp["label"] + " (live)") if cp else "Current (live)", "items": [item_view(i) for i in items]}


def side_period(period: dict) -> dict:
    """A quarter as it was when it closed."""
    data = period.get("closing_data")
    return {"label": period["label"] + " (closed)", "items": data if isinstance(data, list) else []}


def _agg(items):
    active = [d for d in items if not d.get("written_off")]
    wo = [d for d in items if d.get("written_off")]
    return {
        "active_value": round(sum(d.get("current_value", 0) for d in active), 2),
        "active_units": sum(d.get("current", 0) for d in active),
        "used_units": sum(d.get("used", 0) for d in active),
        "used_value": round(sum(d.get("used_value", 0) for d in active), 2),
        "dead_value": round(sum(d.get("current_value", 0) for d in active if d.get("used", 0) == 0), 2),
        "wo_sunk": round(sum((d.get("unit_cost_gbp") or 0) * d.get("current", 0) for d in wo), 2),
        "skus": len(active),
    }


def _movers(left_items: list, right_items: list) -> list:
    """Every line's change between the two sides, unsorted and uncut."""
    lm = {d["key"]: d for d in left_items if d.get("key")}
    rm = {d["key"]: d for d in right_items if d.get("key")}
    movers = []
    for k in sorted(set(lm) | set(rm)):
        a, b = lm.get(k, {}), rm.get(k, {})
        ref = b or a
        movers.append({
            "item": f"{ref.get('category', '')} / {ref.get('name', '')}".strip(" /"),
            "value_left": round(a.get("current_value", 0), 2), "value_right": round(b.get("current_value", 0), 2),
            "value_delta": round(b.get("current_value", 0) - a.get("current_value", 0), 2),
            "cur_left": a.get("current", 0), "cur_right": b.get("current", 0),
            "cur_delta": b.get("current", 0) - a.get("current", 0)})
    return movers


def compare(left: dict, right: dict) -> dict:
    """Two sides (side_live or side_period): aggregates, per-category value
    change, and the biggest movers by value and by units."""
    L, R = left, right
    if not L or not R:
        return {"error": "period not found"}

    def by_cat(items):
        c = {}
        for d in items:
            if not d.get("written_off"):
                c[d["category"]] = c.get(d["category"], 0) + d.get("current_value", 0)
        return c

    lc, rc = by_cat(L["items"]), by_cat(R["items"])
    by_category = [{"category": k, "left": round(lc.get(k, 0), 2), "right": round(rc.get(k, 0), 2),
                    "delta": round(rc.get(k, 0) - lc.get(k, 0), 2)} for k in sorted(set(lc) | set(rc))]
    movers = _movers(L["items"], R["items"])
    return {
        "left": {"label": L["label"], "agg": _agg(L["items"])},
        "right": {"label": R["label"], "agg": _agg(R["items"])},
        "by_category": by_category,
        "top_value_movers": sorted(movers, key=lambda m: -abs(m["value_delta"]))[:15],
        "top_unit_movers": sorted(movers, key=lambda m: -abs(m["cur_delta"]))[:15],
    }


# ---- foreign exchange ------------------------------------------------------

def implied_rate(items: list, currency: str):
    """The native-to-sterling rate baked into the booked costs, averaged over
    active lines in that currency."""
    rs = [i["unit_cost_gbp"] / i["unit_cost"] for i in items
          if not i["written_off"] and i["currency"] == currency and (i["unit_cost"] or 0) > 0
          and (i["unit_cost_gbp"] or 0) > 0]
    return round(sum(rs) / len(rs), 4) if rs else None


def fx_rates(items: list, meta: dict) -> dict:
    out = {}
    for cur in ("USD", "EUR"):
        m = meta.get(f"fx_{cur.lower()}_gbp", "")
        try:
            out[cur] = float(m) if m else (implied_rate(items, cur) or DEFAULT_FX[cur])
        except (ValueError, TypeError):
            out[cur] = implied_rate(items, cur) or DEFAULT_FX[cur]
    return out


def fx_revaluation(items: list, meta: dict) -> dict:
    """Active stock restated at today's rate against the rate booked at purchase."""
    rates = fx_rates(items, meta)
    cur = {}
    not_reval = 0.0
    for i in items:
        if i["written_off"]:
            continue
        if (i["unit_cost"] or 0) > 0 and i["current"] > 0 and i["currency"] in rates:
            d = cur.setdefault(i["currency"], {"booked": 0.0, "today": 0.0, "units": 0})
            d["booked"] += i["current"] * (i["unit_cost_gbp"] or 0)
            d["today"] += i["current"] * i["unit_cost"] * rates[i["currency"]]
            d["units"] += i["current"]
        else:
            not_reval += current_value(i)
    currencies, tb, tt = [], 0.0, 0.0
    for c, d in cur.items():
        booked, today = round(d["booked"], 2), round(d["today"], 2)
        tb += booked; tt += today
        currencies.append({"currency": c, "rate": rates[c], "units": d["units"],
                           "booked_gbp": booked, "today_gbp": today,
                           "drift_gbp": round(today - booked, 2),
                           "drift_pct": round(100 * (today - booked) / booked, 1) if booked else 0})
    currencies.sort(key=lambda x: -abs(x["drift_gbp"]))
    tb, tt = round(tb, 2), round(tt, 2)
    return {"rates": rates, "currencies": currencies,
            "total_booked_gbp": tb, "total_today_gbp": tt,
            "total_drift_gbp": round(tt - tb, 2),
            "total_drift_pct": round(100 * (tt - tb) / tb, 1) if tb else 0,
            "not_revalued_gbp": round(not_reval, 2)}


# ---- reordering ------------------------------------------------------------

def reorder_suggestions(items: list) -> dict:
    """Active lines at or below their reorder point, counting stock already
    on order, grouped by supplier with a suggested quantity (the line's own,
    or enough to reach twice the point)."""
    due = [i for i in items
           if not i["written_off"] and i["reorder_point"] > 0
           and (i["current"] + (i["on_order"] or 0)) <= i["reorder_point"]]
    rows = []
    for i in due:
        qty = i["reorder_qty"] if i["reorder_qty"] > 0 else max(2 * i["reorder_point"] - i["current"], i["reorder_point"])
        rows.append({
            "key": i["key"], "item": _label(i), "category": i["category"],
            "supplier": i["supplier"] or "Unknown", "current": i["current"], "reorder_point": i["reorder_point"],
            "on_order": i["on_order"] or 0,
            "shortfall": max(i["reorder_point"] - i["current"], 0), "suggested_qty": qty,
            "unit_cost": i["unit_cost"], "unit_cost_gbp": i["unit_cost_gbp"], "currency": i["currency"],
            "order_value_gbp": round(qty * (i["unit_cost_gbp"] or 0), 2)})
    groups = {}
    for r in rows:
        groups.setdefault(r["supplier"], []).append(r)
    suppliers = [{"supplier": k, "lines": len(v),
                  "order_value_gbp": round(sum(x["order_value_gbp"] for x in v), 2),
                  "items": sorted(v, key=lambda x: (x["current"], x["item"]))}
                 for k, v in groups.items()]
    suppliers.sort(key=lambda x: -x["order_value_gbp"])
    return {"suppliers": suppliers, "total_lines": len(rows),
            "total_order_value_gbp": round(sum(r["order_value_gbp"] for r in rows), 2)}


def suggest_reorder_points(items: list, lead_by_supplier: dict = None) -> dict:
    """A reorder point and quantity for every line that sells: cover the
    supplier's lead time plus a safety buffer, and order a quarter's worth
    at a time, rounded up to tens."""
    lead_by_supplier = lead_by_supplier or {}
    out = []
    for i in items:
        if i["written_off"] or i["used"] <= 0:
            continue
        daily = i["used"] / QUARTER_DAYS
        lead = lead_by_supplier.get(i["supplier"] or "", 0) or 0
        cover_days = lead + SAFETY_DAYS if lead else LOW_STOCK_DAYS
        point = max(1, math.ceil(daily * cover_days))
        qty = max(point, math.ceil(daily * QUARTER_DAYS))
        qty = int(math.ceil(qty / 10.0) * 10) if qty >= 10 else qty
        if point == i["reorder_point"] and qty == i["reorder_qty"]:
            continue
        out.append({"key": i["key"], "item": _label(i), "category": i["category"],
                    "supplier": i["supplier"] or "Unknown", "current": i["current"], "used": i["used"],
                    "cover_days": cover_days, "lead_days": lead,
                    "reorder_point": point, "reorder_qty": qty,
                    "current_point": i["reorder_point"], "current_qty": i["reorder_qty"]})
    out.sort(key=lambda x: (x["supplier"].lower(), -x["used"]))
    return {"suggestions": out, "safety_days": SAFETY_DAYS}


# ---- the sheet now ---------------------------------------------------------

def compute_current(items: list) -> dict:
    active = [i for i in items if not i["written_off"]]
    wo = [i for i in items if i["written_off"]]

    def s(rows, attr):
        return sum(r[attr] for r in rows)

    active_val = _r2(sum(current_value(i) for i in active))
    wo_sunk = _r2(sum((i["unit_cost_gbp"] or 0) * i["current"] for i in wo))
    start_units = s(active, "start")
    used_units = s(active, "used")

    cat = {}
    for i in active:
        d = cat.setdefault(i["category"], {"skus": 0, "units": 0, "val": 0.0, "used_val": 0.0})
        d["skus"] += 1; d["units"] += i["current"]; d["val"] += current_value(i); d["used_val"] += used_value(i)
    by_cat = sorted(
        [{"category": k, "skus": v["skus"], "units": v["units"], "value_gbp": _r2(v["val"]),
          "pct_of_value": _r2(100 * v["val"] / active_val) if active_val else 0,
          "used_value_gbp": _r2(v["used_val"])} for k, v in cat.items()],
        key=lambda x: -x["value_gbp"])

    sup, cur = {}, {}
    for i in active:
        sup[i["supplier"] or "Unknown"] = sup.get(i["supplier"] or "Unknown", 0) + current_value(i)
        cur[i["currency"] or "?"] = cur.get(i["currency"] or "?", 0) + current_value(i)
    by_sup = sorted([{"name": k, "value_gbp": _r2(v)} for k, v in sup.items()], key=lambda x: -x["value_gbp"])
    by_cur = sorted([{"name": k, "value_gbp": _r2(v),
                      "pct": _r2(100 * v / active_val) if active_val else 0} for k, v in cur.items()],
                    key=lambda x: -x["value_gbp"])

    woc = {}
    for i in wo:
        d = woc.setdefault(i["category"], {"units": 0, "sunk": 0.0})
        d["units"] += i["current"]; d["sunk"] += (i["unit_cost_gbp"] or 0) * i["current"]
    wo_by_cat = sorted([{"category": k, "units": v["units"], "sunk_gbp": _r2(v["sunk"])}
                        for k, v in woc.items()], key=lambda x: -x["sunk_gbp"])

    reorder = sorted([{"item": _label(i), "key": i["key"], "current": i["current"],
                       "used": i["used"], "cover_quarters": _r2(i["current"] / i["used"]), "value_gbp": current_value(i)}
                      for i in active if i["used"] > 0], key=lambda x: x["cover_quarters"])
    dead = sorted([{"item": _label(i), "key": i["key"], "units": i["current"],
                    "value_gbp": current_value(i)} for i in active if i["used"] == 0 and current_value(i) > 0],
                  key=lambda x: -x["value_gbp"])
    top = sorted([{"item": _label(i), "key": i["key"], "units": i["current"],
                   "value_gbp": current_value(i)} for i in active], key=lambda x: -x["value_gbp"])

    return {
        "headline": {
            "active_stock_value_gbp": active_val, "active_units": s(active, "current"),
            "active_skus": len(active), "start_units": start_units, "used_units": used_units,
            "cogs_used_value_gbp": _r2(sum(used_value(i) for i in active)),
            "sell_through_pct": _r2(100 * used_units / start_units) if start_units else 0,
        },
        "write_offs": {"skus": len(wo), "units": s(wo, "current"),
                       "estimated_sunk_cost_gbp": wo_sunk, "by_category": wo_by_cat},
        "dead_stock": {"skus": len(dead), "tied_up_value_gbp": _r2(sum(d["value_gbp"] for d in dead)),
                       "top": dead[:12]},
        "by_category": by_cat, "by_supplier": by_sup, "by_currency": by_cur,
        "reorder_candidates": reorder[:15], "top_value_items": top[:12],
    }


def totals_for_snapshot(items: list) -> dict:
    """The compact totals kept on each snapshot for the trend charts."""
    c = compute_current(items)
    return {
        "active_value_gbp": c["headline"]["active_stock_value_gbp"],
        "active_units": c["headline"]["active_units"],
        "used_units": c["headline"]["used_units"],
        "wo_units": c["write_offs"]["units"],
        "wo_sunk_gbp": c["write_offs"]["estimated_sunk_cost_gbp"],
        "dead_value_gbp": c["dead_stock"]["tied_up_value_gbp"],
        "by_category": {x["category"]: x["value_gbp"] for x in c["by_category"]},
    }


# ---- over time -------------------------------------------------------------

def _oldest_first(snapshots: list) -> list:
    return sorted(snapshots, key=lambda s: _instant(s["taken_at"]))


def _totals(snap: dict) -> dict:
    t = snap.get("totals")
    return t if isinstance(t, dict) else {}


def trends(snapshots: list, limit: int = 365) -> dict:
    snaps = _oldest_first(snapshots)[-limit:]
    series = [{"at": sn.get("taken_at"), "reason": sn.get("reason"), **_totals(sn)} for sn in snaps]
    return {"points": series, "count": len(series)}


def _linreg(ys: list) -> float:
    """Slope per step via least squares; 0 if <2 points."""
    n = len(ys)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    return sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / denom


def forecast(items: list, snapshots: list) -> dict:
    """Days to stock-out for each line from how fast `current` fell across the
    snapshots, or the quarter's run rate (used / 90) when history is thin."""
    live = {i["key"]: i for i in items if not i["written_off"]}
    snaps = _oldest_first(snapshots)

    series = {}
    for sn in snaps:
        at = _instant(sn["taken_at"])
        for si in sn.get("items") or []:
            series.setdefault(si["item_key"], []).append((at, si["current"]))

    out = []
    for key, it in live.items():
        daily = None
        pts = series.get(key, [])
        if len(pts) >= 2:
            (t0, c0), (t1, c1) = pts[0], pts[-1]
            days = max((t1 - t0).total_seconds() / 86400.0, 1e-6)
            drop = c0 - c1
            if days >= 1 and drop > 0:
                daily = drop / days
        if daily is None:
            daily = (it["used"] / QUARTER_DAYS) if it["used"] > 0 else 0.0
        dts = (it["current"] / daily) if daily > 0 else None
        out.append({
            "key": key, "item": _label(it), "current": it["current"],
            "daily_use": round(daily, 3),
            "days_to_stockout": round(dts, 1) if dts is not None else None,
            "value_gbp": current_value(it), "basis": "history" if len(pts) >= 2 else "run-rate",
        })
    runs_out = sorted([o for o in out if o["days_to_stockout"] is not None],
                      key=lambda x: x["days_to_stockout"])

    vals = [_totals(sn).get("active_value_gbp", 0) for sn in snaps]
    slope = _linreg(vals)
    # Only projected once there is enough history; a couple of points would
    # extrapolate a single edit into a meaningless number.
    projected_30 = round(vals[-1] + slope * 30, 2) if len(snaps) >= 5 else None

    return {
        "items": out, "soonest_stockouts": runs_out[:20],
        "value_trend_per_step_gbp": round(slope, 2),
        "value_now_gbp": vals[-1] if vals else None,
        "value_projected_next_30_steps_gbp": projected_30,
        "history_points": len(snaps),
    }


def detect_anomalies(items: list, meta: dict, prev_totals: dict = None) -> list:
    """Stock-outs, low stock and negative stock on each line, and a large
    swing in value since the previous snapshot."""
    alerts = []
    try:
        low_days = int(meta.get("low_stock_days", str(LOW_STOCK_DAYS)) or LOW_STOCK_DAYS)
    except (ValueError, TypeError):
        low_days = LOW_STOCK_DAYS
    active = [i for i in items if not i["written_off"]]

    for i in active:
        if i["current"] < 0:
            alerts.append({"kind": "anomaly", "severity": "critical", "item_key": i["key"],
                           "message": f"Negative stock on {_label(i)}: {i['current']}"})
        elif i["current"] == 0 and i["used"] > 0:
            alerts.append({"kind": "stockout", "severity": "warning", "item_key": i["key"],
                           "message": f"Out of stock: {_label(i)} (used {i['used']} this period)"})
        elif i["used"] > 0:
            cover_days = (i["current"] / (i["used"] / QUARTER_DAYS)) if i["used"] > 0 else None
            if cover_days is not None and cover_days < low_days:
                alerts.append({"kind": "low_stock", "severity": "warning", "item_key": i["key"],
                               "message": f"Low stock: {_label(i)} ~{round(cover_days)} days left "
                                          f"({i['current']} on hand)"})

    if prev_totals:
        now_val = sum(current_value(i) for i in active)
        prev_val = prev_totals.get("active_value_gbp", 0)
        if prev_val > 0:
            change = (now_val - prev_val) / prev_val
            if abs(change) >= 0.15:
                d = "dropped" if change < 0 else "rose"
                alerts.append({"kind": "large_change", "severity": "info", "item_key": "",
                               "message": f"Active stock value {d} {abs(round(change*100))}% "
                                          f"(£{round(prev_val)} → £{round(now_val)}) since last snapshot"})
    return alerts
