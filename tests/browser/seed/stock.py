# The stock sheet, moved in: every Stock screen filled with invented stock.
# About thirty lines of glass, rings, projectors and accessories from four
# invented suppliers, two closed quarters and an open one, ninety nightly
# snapshots, a history written in time order (deliveries, made orders, counts,
# edits), warnings in the server's own words, two production lines waiting for
# a ruling, a placed order still to arrive, a backup and a kept AI reading.
# Written through the stock stores, as the move's converter writes them.
import json as _sj
import random as _sr
from datetime import datetime as _sdt, timedelta as _std, timezone as _stz
from gizmo import stock as _stock, stock_backups as _sbk, stock_store as _ss

_SN = _sdt.now(_stz.utc).replace(microsecond=0)
_SRNG = _sr.Random(23)
_Q_OPEN = _SN - _std(days=22)
_iso = lambda t: t.isoformat()

ensure_auth()
_SUSERS = team._load_users()
_SMASTER, _SOWEN = APP_AUTH["master"], team._find_username(_SUSERS, "owen")

_SUP = {"glass": "Northbeam Optics", "colour": "Lumen Colour Works", "rings": "Midland Turned Parts",
        "proj": "Brightway Lighting"}
_SCUR = {"Northbeam Optics": "USD", "Lumen Colour Works": "EUR", "Midland Turned Parts": "GBP", "Brightway Lighting": "USD"}
_SFX = {"USD": 0.79, "EUR": 0.85, "GBP": 1.0}
# (category, sub-category, size, unit cost in pounds, start, received, used, reorder level, order qty, supplier)
_SLINES = []
for size, cost, start, used in (("15.9", 1.10, 80, 46), ("20", 1.25, 140, 98), ("26.5", 1.60, 60, 22),
                                 ("37.5", 2.40, 120, 104), ("53.3", 3.90, 45, 12), ("64.9", 4.80, 70, 31), ("86", 7.20, 18, 3)):
    _SLINES.append(("Glass", "Clear Etch", size, cost, start, _SRNG.choice((0, 50, 100)), used, 30, 100, _SUP["glass"]))
for size, cost, start, used in (("20", 1.90, 40, 18), ("37.5", 3.10, 30, 27), ("53.3", 4.60, 12, 0)):
    _SLINES.append(("Glass", "Heavy Matt", size, cost, start, 0, used, 10, 40, _SUP["glass"]))
for colour in ("Blue 12", "Red 03", "Green 15", "Amber 21", "Purple 30"):
    for size, cost in (("20", 2.20), ("37.5", 3.40)):
        _SLINES.append(("Glass", colour, size, cost, _SRNG.randint(8, 40), 0, _SRNG.choice((0, 2, 5, 9, 14)), 6, 20, _SUP["colour"]))
for bezel, fits, cost in (("86", "64.9", 3.20), ("100", "86", 4.10), ("120", "100", 5.30)):
    _SLINES.append(("Rings", bezel, fits, cost, _SRNG.randint(20, 60), 0, _SRNG.randint(4, 30), 10, 30, _SUP["rings"]))
for model, finish, cost in (("LED80", "White", 182.0), ("LED80", "Black", 182.0), ("LED150", "Black", 298.0),
                            ("LED300", "Black", 612.0)):
    _SLINES.append(("Projector", model, finish, cost, _SRNG.randint(2, 9), _SRNG.choice((0, 2)), _SRNG.randint(1, 5), 2, 4, _SUP["proj"]))
for sub, size, cost in (("Lens hood", "LED150", 24.0), ("Mains adaptor", "24V", 31.5), ("Lens", "30 degree", 46.0),
                        ("Lens", "50 degree", 46.0)):
    _SLINES.append(("Accessories", sub, size, cost, _SRNG.randint(3, 15), 0, _SRNG.randint(0, 6), 0, 0, _SUP["proj"]))
_SWO = [("Glass", "Blue 12", "15.9", 2.20, 14, 0, 0, 0, 0, _SUP["colour"]),
        ("Projector", "LED40", "White", 96.0, 3, 0, 0, 0, 0, _SUP["proj"])]

_SITEMS = []
for _n, (cat, sub, size, gbp, start, received, used, rp, rq, sup) in enumerate(_SLINES + _SWO):
    cur = _SCUR[sup]
    current = max(0, start + received - used)
    _SITEMS.append({"id": _n + 1, "key": _stock.item_key(cat, sub, size, ""), "category": cat, "sub_category": sub,
                    "size": size, "notes": "", "written_off": _n >= len(_SLINES),
                    "barcode": ("DEMO-%04d" % (1000 + _n)) if _n % 5 == 0 else "", "supplier": sup, "currency": cur,
                    "unit_cost": None if cur == "GBP" else round(gbp / _SFX[cur], 2), "unit_cost_gbp": gbp,
                    "start": start, "received": received, "used": used, "current": current, "reorder_point": rp,
                    "reorder_qty": rq, "on_order": rq if (rp and current <= rp * 1.5 and _n % 2 == 0) else 0,
                    "created_at": _iso(_SN - _std(days=140)), "updated_at": _iso(_SN - _std(days=_SRNG.randint(0, 20)))})
_ss.write_items({"items": {str(i["id"]): i for i in _SITEMS}, "next_id": len(_SITEMS) + 1})
_SBYKEY = {i["key"]: i for i in _SITEMS}

def _closing(scale):
    return [{"id": i["id"], "key": i["key"], "category": i["category"], "sub_category": i["sub_category"],
             "size": i["size"], "current": int(i["current"] * scale) + 3, "used": int(i["used"] * 0.8),
             "unit_cost_gbp": i["unit_cost_gbp"], "written_off": i["written_off"],
             "current_value": round((int(i["current"] * scale) + 3) * i["unit_cost_gbp"], 2)} for i in _SITEMS]
_ss.write_periods({"periods": [
    {"id": 1, "label": "Q2 2026", "opened_at": _iso(_Q_OPEN - _std(days=183)), "closed_at": _iso(_Q_OPEN - _std(days=92)),
     "closing_value": 9420.55, "closing_units": 1088, "closing_skus": len(_SLINES), "closing_used_value": 2210.4,
     "note": "", "closing_data": _closing(1.25)},
    {"id": 2, "label": "Q3 2026", "opened_at": _iso(_Q_OPEN - _std(days=91)), "closed_at": _iso(_Q_OPEN - _std(minutes=5)),
     "closing_value": 8873.10, "closing_units": 1012, "closing_skus": len(_SLINES), "closing_used_value": 2496.85,
     "note": "", "closing_data": _closing(1.1)},
    {"id": 3, "label": "Q4 2026", "opened_at": _iso(_Q_OPEN), "closed_at": None, "closing_value": 0.0, "closing_units": 0,
     "closing_skus": 0, "closing_used_value": 0.0, "note": "", "closing_data": None}], "next_id": 4})

# Ninety nightly snapshots: the shelf falling with use, rising with the early deliveries.
for _d in range(90, -1, -1):
    _at = (_SN - _std(days=_d)).replace(hour=0, minute=5, second=0)
    _lines, _val, _units = [], 0.0, 0
    for i in _SITEMS:
        cur = max(0, i["current"] + int(i["used"] * _d / 90.0) - (i["received"] if _d > 40 else 0))
        cv = 0.0 if i["written_off"] else round(cur * i["unit_cost_gbp"], 2)
        if not i["written_off"]:
            _val += cv; _units += cur
        _lines.append({"id": (91 - _d) * 1000 + i["id"], "item_key": i["key"], "category": i["category"],
                       "written_off": i["written_off"], "current": cur, "used": i["used"], "current_value": cv})
    _ss.append_snapshot({"id": 91 - _d, "taken_at": _iso(_at), "reason": "scheduled", "by_user": "system", "note": "",
                         "totals": {"active_value_gbp": round(_val, 2), "active_units": _units}, "items": _lines})

# The history, oldest first: the stock app's usernames beside their Reactor accounts.
_SPEOPLE = {"cameron": _SMASTER, "sam": _SOWEN}
_ss.write_people({"people": dict(_SPEOPLE), "logins": {}})
_SH = []
def _slog(at, user, action, it=None, field="", old="", new="", detail=""):
    _SH.append({"at": _iso(at), "user": user, "action": action, "item_key": it["key"] if it else "", "field": field,
                "old_value": str(old), "new_value": str(new), "detail": detail, "person": _SPEOPLE.get(user),
                **({"item_id": it["id"]} if it else {})})
for _k in range(60):
    it = _SRNG.choice(_SITEMS[:len(_SLINES)])
    at = _SN - _std(hours=_SRNG.randint(2, 21 * 24))
    kind = _SRNG.choice(("use", "use", "use", "count", "receive", "edit"))
    if kind == "use":
        q = _SRNG.randint(1, 4)
        _slog(at, "gizmo", "use", it, "current", it["current"] + q, it["current"], f"made #{1100 + _k} · used {q}")
    elif kind == "count":
        _slog(at, _SRNG.choice(("cameron", "sam")), "update", it, "current", it["current"] + 2, it["current"], "counted")
    elif kind == "receive":
        q = _SRNG.choice((20, 50, 100))
        _slog(at, _SRNG.choice(("cameron", "sam")), "receive", it, "current", max(0, it["current"] - q), it["current"],
              f"received {q} · inv INV-{2400 + _k} · {at.date().isoformat()}")
    else:
        _slog(at, "cameron", "update", it, "reorder_point", 20, it["reorder_point"], "manual edit")
_SORDERED = [i for i in _SITEMS if i["on_order"]]
for it in _SORDERED:
    _slog(_SN - _std(days=4), "cameron", "ordered", it, "on_order", 0, it["on_order"],
          f"ordered {it['on_order']} from {it['supplier']} · ref PO-1027")
_slog(_Q_OPEN, "cameron", "period", None, "", "Q3 2026", "Q4 2026", "closed Q3 2026, opened Q4 2026")
_SH.sort(key=lambda r: r["at"])
_ss.append_history(_SH)

# The order still to arrive: what the lines on order await.
_ss.write_orders({"orders": [{"id": 1, "supplier": _SORDERED[0]["supplier"] if _SORDERED else "", "reference": "PO-1027",
                              "currency": "", "at": _iso(_SN - _std(days=4)), "by": "cameron", "person": _SMASTER,
                              "before_move": True,
                              "lines": [{"item_id": i["id"], "qty": i["on_order"], "received": 0, "cleared": 0} for i in _SORDERED]}],
                  "next_id": 2})

# Warnings, in the server's own words.
_SAL = []
for it in [i for i in _SITEMS[:len(_SLINES)] if i["used"] and i["current"] / (i["used"] / 90.0) < 30][:3]:
    label = it["category"] + " / " + " ".join(b for b in (it["sub_category"], it["size"]) if b)
    if it["current"] == 0:
        kind, msg = "stockout", f"Out of stock: {label} (used {it['used']} this period)"
    else:
        kind, msg = "low_stock", f"Low stock: {label} ~{round(it['current'] / (it['used'] / 90.0))} days left ({it['current']} on hand)"
    _SAL.append({"id": len(_SAL) + 1, "at": _iso(_SN - _std(hours=_SRNG.randint(3, 40))), "kind": kind, "severity": "warning",
                 "message": msg, "item_key": it["key"], "dismissed": False, "dismissed_by": ""})
_SAL.append({"id": len(_SAL) + 1, "at": _iso(_SN - _std(hours=5)), "kind": "large_change", "severity": "info", "item_key": "",
             "message": "Active stock value dropped 16% (£13020 → £10924) since last snapshot", "dismissed": False,
             "dismissed_by": ""})
_ss.write_alerts({"alerts": _SAL, "next_id": len(_SAL) + 1})

# The production link: two lines waiting for a ruling, a ruling, the week's bookings.
_SCE20, _SCE375 = _SBYKEY["Glass|Clear Etch|20|"], _SBYKEY["Glass|Clear Etch|37.5|"]
_ss.write_bridge({
    "bookings": [{"id": k + 1, "order_id": str(6990 + k), "order_name": f"#{1170 + k}", "at": _iso(_SN - _std(days=k)),
                  "lines": [{"item_id": (_SCE375 if k % 2 else _SCE20)["id"], "item_key": (_SCE375 if k % 2 else _SCE20)["key"],
                             "qty": 2, "current_delta": -2, "used_delta": 2}]} for k in range(6)],
    "sheets": [],
    "parked": [{"id": 1, "order_id": "7001", "order_name": "#1188", "alias": "Colour|20", "qty": 2, "note": "",
                "at": _iso(_SN - _std(hours=6))},
               {"id": 2, "order_id": "7002", "order_name": "#1190", "alias": "Mono|17", "qty": 1, "note": "",
                "at": _iso(_SN - _std(hours=3))}],
    "aliases": [{"id": 1, "alias": "Mono|19", "item_id": _SCE20["id"], "item_key": _SCE20["key"], "at": _iso(_SN - _std(days=30))}],
    "next_ids": {"bookings": 7, "sheets": 1, "parked": 3, "aliases": 2}})

# Each supplier's contact.
_ss.write_suppliers({"suppliers": [
    {"id": k + 1, "supplier": name, "email": "orders@" + name.split()[0].lower() + ".example", "cc": "",
     "contact_name": "Order desk", "subject": "Order from the shop",
     "body": "Hello {{contact}},\n\nPlease could you send:\n{{items}}\n\nThank you.", "lead_days": lead, "min_order": mino,
     "updated_at": _iso(_SN - _std(days=40))}
    for k, (name, lead, mino) in enumerate(((_SUP["glass"], 21, "100 units"), (_SUP["colour"], 14, ""),
                                            (_SUP["rings"], 7, "50 units"), (_SUP["proj"], 28, "")))], "next_id": 5})

# Moved in, the Mono and HM glass named, the master last here three days ago, a kept AI reading.
_ss.write_settings({
    "meta": {"low_stock_days": "30", "fx_usd_gbp": "0.79", "fx_eur_gbp": "0.85"},
    "glass_families": {"mono": "Clear Etch", "hm": "Heavy Matt"},
    "live_since": _iso(_Q_OPEN),
    "acks": {str(_SMASTER): _iso(_SN - _std(days=3))},
    "insights": {"at": _iso(_SN - _std(hours=18)), "by": "Cameron", "person": _SMASTER, "result": {
        "headline": "Clear Etch 37.5 and Amber 21 run out first; two projectors hold most of the idle money.",
        "health_score": 68,
        "findings": [
            {"title": "Clear Etch 37.5 is nearly gone", "detail": "16 left against 104 used this quarter, about 14 days of cover.",
             "severity": "critical", "metric": "14 days"},
            {"title": "Money resting in projectors", "detail": "LED300 Black holds stock that has not moved this quarter.",
             "severity": "warning", "metric": "£2,448"},
            {"title": "Rings are well covered", "detail": "Every ring size has more than a quarter of stock at this rate.",
             "severity": "positive", "metric": "1.4 quarters"}],
        "actions": [
            {"title": "Order Clear Etch 37.5 now", "detail": "100 from Northbeam Optics covers the quarter with the 21 day delivery.",
             "priority": "high"},
            {"title": "Hold off LED300 orders", "detail": "Sell through the idle units before buying more.", "priority": "medium"}]}}})
_sbk.make_backup(_stock.actor(_SMASTER))
print("stock seed: %d lines, %d history, %d snapshots" % (len(_SITEMS), len(_SH), 91))
