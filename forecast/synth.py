"""A synthetic store for smoke tests and demos, shaped by the workbook.

Monthly net sales follow the workbook's actual months where it has them and
a scenario after that, spread over days by a weekday shape; units per
variant are Poisson draws around each variant's revenue share; orders carry
segments in the store's mix, trade discounts, a Black Friday and a January
sale, a few refunds, and two SKUs launched late so the cold start has
something to do. Output is the Admin-shaped JSON the ingestion reads.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .calendar import black_friday
from .cashflow import CashFlowModel

# (product_id, title, category, [(variant_id, variant_title, price, weight)])
CATALOGUE = [
    ("p_gobo_1c", "Custom glass gobo (1 colour)", "Gobo",
     [("v_g1_a", "Size A", 89.0, 0.22), ("v_g1_b", "Size B", 79.0, 0.30), ("v_g1_d", "Size D", 69.0, 0.18), ("v_g1_e", "Size E", 59.0, 0.10)]),
    ("p_gobo_full", "Custom glass gobo (full colour)", "Gobo",
     [("v_gf_a", "Size A", 149.0, 0.12), ("v_gf_b", "Size B", 139.0, 0.16), ("v_gf_d", "Size D", 129.0, 0.08)]),
    ("p_gobo_steel", "Steel gobo", "Gobo", [("v_gs", "Standard", 29.0, 0.35)]),
    ("p_proj_30", "Gobo projector 30W LED", "Projector", [("v_p30b", "Black", 399.0, 0.05), ("v_p30w", "White", 399.0, 0.03)]),
    ("p_proj_80", "Gobo projector 80W outdoor", "Projector", [("v_p80", "Black", 899.0, 0.02)]),
    ("p_proj_15", "Gobo projector 15W mini", "Projector", [("v_p15", "Black", 199.0, 0.06)]),
    ("p_holder", "Gobo holder", "Accessory", [("v_h_m", "M size", 12.0, 0.25), ("v_h_b", "B size", 14.0, 0.20), ("v_h_a", "A size", 16.0, 0.12)]),
    ("p_lens", "Projector lens", "Accessory", [("v_l19", "19 degree", 49.0, 0.05), ("v_l36", "36 degree", 49.0, 0.05)]),
    ("p_frame", "Wall mount frame", "Accessory", [("v_fr", "Standard", 39.0, 0.06)]),
    ("p_cable", "Extension cable", "Accessory", [("v_cab5", "5 m", 15.0, 0.10)]),
]
# launched this many days before as_of
LAUNCHES = [
    (120, ("p_gobo_neon", "Neon effect gobo", "Gobo", [("v_gn", "Size B", 119.0, 0.08)])),
    (40, ("p_proj_50", "Gobo projector 50W", "Projector", [("v_p50", "Black", 549.0, 0.03)])),
]
SEGMENTS = [("Trade", 0.45), ("Weddings", 0.30), ("Venues", 0.15), ("Retail", 0.10)]
DOW = np.array([1.15, 1.20, 1.20, 1.15, 1.05, 0.65, 0.60])
FALLBACK_SEASON = {1: 0.9, 2: 0.95, 3: 1.0, 4: 0.9, 5: 1.1, 6: 1.1, 7: 0.5, 8: 0.55, 9: 1.0, 10: 1.5, 11: 1.4, 12: 0.6}


def month_targets(cashflow: Optional[CashFlowModel], months: pd.DatetimeIndex, scenario: str, scenario_scale: float) -> Dict[pd.Timestamp, float]:
    out: Dict[pd.Timestamp, float] = {}
    act = cashflow.actuals.set_index("month")["net_sales"] if cashflow is not None else pd.Series(dtype=float)
    sc = cashflow.scenarios[scenario].set_index("month")["net_sales"] if cashflow is not None and scenario in cashflow.scenarios else pd.Series(dtype=float)
    base = float(act.mean()) if len(act) else 30000.0
    for m in months:
        if m in act.index:
            out[m] = float(act[m])
        elif m in sc.index:
            out[m] = float(sc[m]) * scenario_scale
        else:
            out[m] = base * FALLBACK_SEASON[m.month]
    return out


def synthetic_orders(as_of: date, days: int = 830, cashflow: Optional[CashFlowModel] = None,
                     scenario: str = "Algorithm 3", scenario_scale: float = 0.93, seed: int = 7) -> Tuple[List[dict], Dict[str, dict]]:
    rng = np.random.default_rng(seed)
    start = as_of - timedelta(days=days - 1)
    dates = pd.date_range(start, as_of, freq="D")
    months = pd.DatetimeIndex(sorted({d.to_period("M").to_timestamp() for d in dates}))
    targets = month_targets(cashflow, months, scenario, scenario_scale)
    catalogue = [(pid, t, c, vs, None) for pid, t, c, vs in CATALOGUE]
    for days_before, (pid, t, c, vs) in LAUNCHES:
        catalogue.append((pid, t, c, vs, as_of - timedelta(days=days_before)))
    variants = []
    for pid, title, cat, vs, launch in catalogue:
        for vid, vt, price, w in vs:
            variants.append({"product_id": pid, "title": title, "category": cat, "variant_id": vid, "variant_title": vt,
                             "price": price, "w": w, "launch": launch})
    products = {pid: {"product_type": cat} for pid, _, cat, _, _ in catalogue}
    rev_w = np.array([v["w"] * v["price"] for v in variants])
    seg_names = [s for s, _ in SEGMENTS]; seg_p = np.array([p for _, p in SEGMENTS])
    bf = {black_friday(y) for y in range(start.year, as_of.year + 1)}
    orders: List[dict] = []
    oid = 1000
    lid = 50000
    pending_refunds: List[dict] = []
    for d in dates:
        m = d.to_period("M").to_timestamp()
        mdays = pd.date_range(m, m + pd.offsets.MonthEnd(0), freq="D")
        w = DOW[mdays.dayofweek]
        day_rev = targets[m] * DOW[d.dayofweek] / w.sum()
        promo, disc_rate = None, 0.0
        if min(abs((d.date() - b).days) for b in bf) <= 3:
            day_rev *= 1.8; promo, disc_rate = "BLACKFRIDAY", 0.15
        elif d.month == 1 and 2 <= d.day <= 14:
            day_rev *= 1.15; promo, disc_rate = "JANSALE", 0.10
        day_rev *= float(rng.lognormal(0, 0.18))
        lines = []
        active = [i for i, v in enumerate(variants) if not v["launch"] or d.date() >= v["launch"]]
        share = rev_w[active] / rev_w[active].sum()      # the day's revenue is shared among what is on sale
        for i, v in zip(active, (variants[i] for i in active)):
            ramp = 1.0
            if v["launch"]:
                ramp = min(1.0, ((d.date() - v["launch"]).days + 1) / 28)
            lam = day_rev * share[active.index(i)] * ramp / v["price"] / 0.95   # 0.95: trade discounts and refunds net off
            q = int(rng.poisson(lam))
            while q > 0:
                take = int(min(q, rng.integers(1, 4)))
                lines.append((v, take)); q -= take
        rng.shuffle(lines)
        while lines:
            n = int(min(len(lines), rng.integers(1, 4)))
            seg = seg_names[int(rng.choice(len(seg_names), p=seg_p))]
            tags = [seg.lower()] if seg != "Retail" else []
            o = {"id": oid, "name": f"#{oid}", "created_at": datetime(d.year, d.month, d.day, int(rng.integers(8, 19))).isoformat() + "Z",
                 "financial_status": "paid", "tags": ", ".join(tags), "customer": {"tags": ""}, "line_items": [], "refunds": []}
            if promo:
                o["discount_codes"] = [{"code": promo}]
            for v, q in lines[:n]:
                rate = disc_rate + (0.10 if seg == "Trade" else 0.0)
                o["line_items"].append({"id": lid, "product_id": v["product_id"], "variant_id": v["variant_id"], "sku": v["variant_id"].upper(),
                                        "title": v["title"], "variant_title": v["variant_title"], "quantity": q, "price": v["price"],
                                        "total_discount": round(q * v["price"] * rate, 2)})
                if rng.random() < 0.02:
                    pending_refunds.append({"order": oid, "line": lid, "qty": 1, "amount": v["price"] * (1 - rate),
                                            "at": d + pd.Timedelta(days=int(rng.integers(5, 21)))})
                lid += 1
            lines = lines[n:]
            orders.append(o); oid += 1
    by_id = {o["id"]: o for o in orders}
    for r in pending_refunds:
        if r["at"].date() <= as_of:
            by_id[r["order"]]["refunds"].append({"created_at": r["at"].isoformat(), "refund_line_items": [
                {"quantity": r["qty"], "subtotal": round(r["amount"], 2), "line_item": {"id": r["line"]}}]})
    return orders, products


def write_synthetic(out_dir: str, as_of: date, cashflow: Optional[CashFlowModel] = None, **kw) -> Tuple[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    orders, products = synthetic_orders(as_of, cashflow=cashflow, **kw)
    op, pp = os.path.join(out_dir, "orders.json"), os.path.join(out_dir, "products.json")
    with open(op, "w") as fh:
        json.dump({"orders": orders}, fh)
    with open(pp, "w") as fh:
        json.dump(products, fh)
    return op, pp
