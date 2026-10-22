# Dashboards seed for the browser suite. Proven 14 Oct 2026 against the
# dispatch setup. Runs AFTER the test_dispatch.py prelude, in its own copy of
# the prelude's names (seed/__init__.py: copilot, server, client,
# post, ensure_auth, tok, SCRATCH ...), never in the prelude's globals. Everything is invented:
# people, companies, emails at example.com / example.org, phones 01632 960xxx.
# Nothing reaches the network: the outside systems (Shopify and the connector
# service) are stood in for in process.
#
# Sections (each a function, called in order by seed_dashboards()):
#   SHARED      the fake Shopify store (c)
#   forecast    workbook by route (a), the forecast package's own nightly maths, run posted to the hook (a)
#   connector   a fake connector HTTP service on 127.0.0.1 (c), CONNECTOR_URL pointed at it
#   liability   nothing extra: it reads the fake Shopify live on every page load
# (The report tabs and Reconciliation, seeded here until 22 Oct 2026, are gone.)
import copy as _dcopy, io as _dio, json as _djson, os as _dos, random as _drandom, re as _dre
import tempfile as _dtemp, threading as _dthreading, time as _dtime, zipfile as _dzip
from datetime import datetime as _ddt, timedelta as _dtd, timezone as _dtz, date as _ddate
from http.server import BaseHTTPRequestHandler as _DHandler, ThreadingHTTPServer as _DServer

DASH = {"log": []}
_NOW = _ddt.now(_dtz.utc).replace(microsecond=0)
_R = _drandom.Random(20261014)


def _iso(dt):
    return dt.astimezone(_dtz.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _p(x):
    return f"{x:.2f}"


# =============================================================================
# SHARED: the fake Shopify store (c). Installed as copilot._tool_json and
# LEFT INSTALLED while serving: Liability and the Production Manager read it
# live, and Chat's payout reads answer from it.
# Anything it does not hold goes to the prelude's fake (ORDER 12345, SHOP).
# =============================================================================
_VENDORS = ["Lumenworks", "Brightline Optics", "Northlight Supply"]
_PRODUCTS_DEF = [
    # (title, type, vendor, status, [(variant, price, inventory or None)], words, alt_ok, tags, created_days_ago)
    ("Custom Glass Gobo (1 colour)", "Gobo", 0, "active", [("Size A", 89, None), ("Size B", 79, None), ("Size D", 69, None), ("Size E", 59, None)], 140, True, "custom, glass", 960),
    ("Custom Glass Gobo (full colour)", "Gobo", 0, "active", [("Size A", 149, None), ("Size B", 139, None), ("Size D", 129, None)], 120, True, "custom, glass, colour", 960),
    ("Steel Gobo", "Gobo", 0, "active", [("Standard", 29, None)], 35, False, "steel", 955),
    ("LED Gobo Projector 30W", "Projector", 1, "active", [("Black", 399, 9), ("White", 399, 5)], 160, True, "projector, indoor", 950),
    ("Outdoor Gobo Projector 80W IP65", "Projector", 1, "active", [("Black", 899, 3)], 180, True, "projector, outdoor", 940),
    ("Mini Gobo Projector 15W", "Projector", 1, "active", [("Black", 199, 0)], 60, True, "projector, compact", 935),
    ("Gobo Holder", "Accessory", 2, "active", [("M size", 12, 120), ("B size", 14, 85), ("A size", 16, 40)], 22, False, "holder", 930),
    ("Projection Lens 36 degree", "Accessory", 2, "active", [("Standard", 49, 22)], 55, True, "lens", 930),
    ("Wall Mount Bracket", "Accessory", 2, "active", [("Standard", 39, 2)], 0, False, "mounting", 930),
    ("Gobo Rotator Unit", "Accessory", 1, "active", [("Standard", 179, 6)], 75, True, "rotator, effects", 700),
    ("Walkway Safety Sign Gobo", "Gobo", 0, "active", [("Size B", 95, None)], 110, True, "safety, signage", 650),
    ("Colour Filter Pack", "Accessory", 2, "active", [("Pack of 6", 24, 40)], 40, True, "filters", 600),
    ("DMX Controller Mini", "Accessory", 2, "draft", [("Standard", 119, 9)], 30, False, "dmx", 90),
    ("Extension Cable 5 m", "Accessory", 2, "active", [("5 m", 15, 60)], 18, True, "cable", 500),
    ("Snowflake Effect Gobo", "Gobo", 0, "archived", [("Size B", 45, None)], 65, True, "seasonal", 760),
    ("Neon Effect Gobo", "Gobo", 0, "active", [("Size B", 119, None)], 95, True, "custom, effects", 120),
]
_LOREM = ("Made to order in our workshop from your artwork, checked by a person before it is cut, "
          "and sent out with a proof you can approve. Suits indoor and outdoor projectors, holds "
          "fine detail and keeps its colour under long running hours. Ask us about sizes, fixtures "
          "and lead times for event dates, and we will match the glass to the projector you have. ").split()


def _body(words):
    if not words:
        return ""
    out = []
    while len(out) < words:
        out += _LOREM
    return "<p>" + " ".join(out[:words]) + "</p>"


def _build_products():
    prods = []
    vid = 4100000001
    for i, (title, ptype, vend, status, variants, words, alt_ok, tags, ago) in enumerate(_PRODUCTS_DEF):
        pid = 8100000001 + i
        handle = _dre.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        created = _NOW - _dtd(days=ago + (130 if ago >= 900 else 0))   # the first lines predate the history
        vs = []
        for (vt, price, inv) in variants:
            v = {"id": vid, "product_id": pid, "title": vt, "price": _p(price), "sku": f"SKU-{vid % 100000}"}
            if inv is not None:
                v["inventory_quantity"] = inv
                v["inventory_management"] = "shopify"
            vs.append(v)
            vid += 1
        prods.append({
            "id": pid, "title": title, "handle": handle, "status": status, "product_type": ptype,
            "vendor": _VENDORS[vend], "tags": tags, "body_html": _body(words),
            "created_at": _iso(created), "updated_at": _iso(_NOW - _dtd(days=(i * 7) % 60 + 1)),
            "published_at": _iso(created) if status == "active" else None,
            # No image src anywhere: the browser would fetch it from the network.
            "image": None,
            "images": [{"id": pid * 10 + k, "alt": (title if (alt_ok or k == 0) and k < 2 else "")} for k in range(3)],
            "variants": vs,
        })
    return prods


_B2B = [  # (company, first, last, sector tag or "", city)
    ("Harbourside Events Ltd", "Priya", "Shah", "Events", "Bristol"),
    ("Bright Night Productions", "Tom", "Ellery", "Events", "Manchester"),
    ("Moorgate Weddings", "Grace", "Holloway", "Events", "York"),
    ("Stagecraft Hire Co", "Dev", "Patel", "Events", "Leicester"),
    ("Copperleaf Interiors", "Amelia", "Ward", "Retail", "Bath"),
    ("Fenwick Lane Boutique", "Jonah", "Reid", "Retail", "Durham"),
    ("Oak and Ember Home", "Sofia", "Marsh", "Retail", "Norwich"),
    ("Northfield Academy Trust", "Helen", "Carver", "Education", "Sheffield"),
    ("Riverside College", "Marcus", "Bell", "Education", "Nottingham"),
    ("St Aldric's School", "Ruth", "Okafor", "Education", "Reading"),
    ("The Lantern Rooms", "Callum", "Fraser", "Hospitality", "Edinburgh"),
    ("Saltmarsh Hotel Group", "Nadia", "Hussain", "Hospitality", "Brighton"),
    ("Quayside Bistro", "Leo", "Brennan", "Hospitality", "Cardiff"),
    ("Kestrel Logistics Ltd", "Owen", "Pryce", "Warehouse", "Coventry"),
    ("Brackenfield Distribution", "Sian", "Morgan", "Warehouse", "Swindon"),
    ("Halden Freight", "Ravi", "Kapoor", "Warehouse", "Hull"),
    ("Larkspur Theatre Company", "Isla", "Fenn", "", "Exeter"),       # trade, never tagged: the radar's case
]
_FIRST = ["Ella", "Sam", "Maya", "Ben", "Chloe", "Liam", "Zara", "Noah", "Hannah", "Oscar", "Ruby", "Ethan",
          "Freya", "Arjun", "Lucy", "Jack", "Amira", "Theo", "Isabel", "Max", "Poppy", "Kai", "Nina", "Felix",
          "Orla", "Rhys", "Leah", "Tariq", "Elsie", "Hugo"]
_LAST = ["Turner", "Whitlock", "Collins", "Ashworth", "Danvers", "Porter", "Bhatt", "Fielder", "Gray", "Lindqvist",
         "Sinclair", "Moss", "Doyle", "Mehta", "Pembridge", "Thornbury", "Saleh", "Marchetti", "Crane", "Fairburn",
         "Hale", "Nakamura", "Quill", "Ambrose", "Varga", "Penhaligon", "Odell", "Rasmussen", "Keane", "Lowther"]
_CITIES = ["Leeds", "Glasgow", "Oxford", "Plymouth", "Belfast", "Derby", "Lincoln", "Chester", "Aberdeen", "Ipswich"]
_PROSPECTS = ["Daniel Rourke", "Megan Fitch", "Yusuf Arslan"]
_STREETS = ["Lantern Yard", "Copper Row", "Kiln Lane", "Weavers Court", "Mill Race Road", "Beacon Walk",
            "Foundry Street", "Harbour Mews", "Orchard Rise", "Chapel Wharf"]


def _addr(name, company, city, n):
    return {"name": name, "company": company or None, "address1": f"{(n * 7) % 90 + 2} {_STREETS[n % len(_STREETS)]}",
            "address2": "", "city": city, "province_code": "", "zip": f"ZZ{n % 9 + 1} {n % 9 + 1}QX",
            "country_code": "GB", "phone": f"01632 960{n % 1000:03d}"}


def _build_customers():
    cust = []
    cid = 6100000001
    for i, (co, fn, ln, tag, city) in enumerate(_B2B):
        email = f"{fn.lower()}.{ln.lower()}@example.org"
        cust.append({"id": cid, "first_name": fn, "last_name": ln, "email": email, "tags": tag,
                     "state": "enabled", "kind": "b2b", "weight": 3.0 if tag in ("Events", "Warehouse") else 2.0,
                     "default_address": _addr(f"{fn} {ln}", co, city, i + 1), "phone": f"01632 960{100 + i:03d}"})
        cid += 1
    cid = 6100009001
    for i, nm in enumerate(_PROSPECTS):
        fn, ln = nm.split(" ", 1)
        cust.append({"id": cid, "first_name": fn, "last_name": ln, "email": f"{fn.lower()}.{ln.lower()}@example.com",
                     "tags": "", "state": "enabled", "kind": "prospect", "weight": 0.0,
                     "default_address": _addr(nm, "", "Carlisle", 80 + i), "phone": f"01632 960{300 + i:03d}",
                     "created_at": _iso(_NOW - _dtd(days=3 + i * 6))})
        cid += 1
    return cust


_SEASON = {1: 0.8, 2: 0.85, 3: 0.95, 4: 1.0, 5: 1.0, 6: 0.95, 7: 0.9, 8: 0.85, 9: 1.05, 10: 1.35, 11: 1.5, 12: 1.2}
_HISTORY_DAYS = 1040  # ~34 months: the forecast backtest scores its models only past ~28 whole months


def _line(prod, var, qty, lid):
    return {"id": lid, "product_id": prod["id"], "variant_id": var["id"], "title": prod["title"],
            "variant_title": var["title"], "name": prod["title"] + " - " + var["title"],
            "quantity": qty, "price": var["price"], "sku": var.get("sku"), "grams": 250, "properties": []}


def _new_consumer(customers, n):
    """A shopper met at checkout: most buy once, some come back."""
    while True:
        fn, ln = _R.choice(_FIRST), _R.choice(_LAST)
        if not any(c["first_name"] == fn and c["last_name"] == ln for c in customers):
            break
    c = {"id": 6100001001 + n, "first_name": fn, "last_name": ln, "email": f"{fn.lower()}.{ln.lower()}@example.com",
         "tags": "", "state": "enabled", "kind": "person", "weight": 0.0,
         "default_address": _addr(f"{fn} {ln}", "", _CITIES[n % len(_CITIES)], 40 + n), "phone": f"01632 960{(200 + n) % 1000:03d}"}
    customers.append(c)
    return c


def _build_orders(products, customers):
    trade = [c for c in customers if c["kind"] == "b2b"]
    tweights = [c["weight"] for c in trade]
    people = []
    sellable = [p for p in products if p["status"] != "draft"]
    pweights = {"Gobo": 5.0, "Projector": 1.2, "Accessory": 2.0}
    orders, seq, lid = [], 0, 7100000001
    start = (_NOW - _dtd(days=_HISTORY_DAYS)).replace(hour=0, minute=0, second=0)
    for d in range(_HISTORY_DAYS + 1):
        day = start + _dtd(days=d)
        if day.date() > _NOW.date():
            break
        t = d / _HISTORY_DAYS
        rate = (0.7 + 0.7 * t) * _SEASON[day.month] * (0.55 if day.weekday() >= 5 else 1.1)
        n = sum(1 for _ in range(4) if _R.random() < rate / 4)
        for _k in range(n):
            when = day + _dtd(hours=_R.randint(7, 20), minutes=_R.randint(0, 59))
            if when > _NOW - _dtd(minutes=30):
                continue
            if _R.random() < 0.42:
                c = _R.choices(trade, tweights)[0]
            elif people and _R.random() < 0.3:
                c = _R.choice(people[-60:])            # a returning shopper, usually a recent one
            else:
                c = _new_consumer(customers, len(people)); people.append(c)
            # Archived lines stopped selling ten months ago; nothing sells before it was listed.
            pool = [p for p in sellable if p["created_at"] <= _iso(when)
                    and not (p["status"] == "archived" and when > _NOW - _dtd(days=300))]
            items = []
            for _j in range(_R.choice([1, 1, 1, 2, 2, 3])):
                pr = _R.choices(pool, [pweights[p["product_type"]] for p in pool])[0]
                var = _R.choice(pr["variants"])
                qty = _R.choice([1, 1, 1, 2, 2, 3, 4]) * (2 if c["kind"] == "b2b" and pr["product_type"] == "Gobo" else 1)
                items.append(_line(pr, var, qty, lid)); lid += 1
            orders.append(_mk_order(seq, when, c, items))
            seq += 1
    DASH["next_seq"], DASH["next_lid"] = seq, lid
    return orders


def _mk_order(seq, when, c, items, **over):
    sub = sum(float(li["price"]) * li["quantity"] for li in items)
    ship = 0.0 if sub >= 150 else 6.95
    total = round(sub + ship, 2)
    co = (c.get("default_address") or {}).get("company") or ""
    addr = dict(c["default_address"])
    age = (_NOW - when).days
    o = {
        "id": 5200000001 + seq, "order_number": 101001 + seq, "name": f"#{101001 + seq}",
        "created_at": _iso(when), "updated_at": _iso(min(_NOW, when + _dtd(days=2))),
        "email": c["email"], "currency": "GBP", "presentment_currency": "GBP",
        "financial_status": "paid", "fulfillment_status": "fulfilled" if age > 2 else None,
        "cancelled_at": None, "test": False, "tags": "", "note": "", "taxes_included": True,
        "total_price": _p(total), "current_total_price": _p(total), "subtotal_price": _p(sub),
        "total_tax": _p(round(total / 6, 2)), "total_outstanding": "0.00",
        "payment_gateway_names": ["shopify_payments"],
        "customer": {"id": c["id"], "first_name": c["first_name"], "last_name": c["last_name"],
                     "email": c["email"], "tags": c["tags"], "default_address": dict(addr)},
        "billing_address": dict(addr), "shipping_address": dict(addr),
        "shipping_lines": [{"title": "Tracked 24" if ship else "Free delivery", "price": _p(ship)}],
        "line_items": items, "refunds": [],
    }
    if co:
        o["company"] = {"name": co}
    o.update(over)
    return o


def _liability_orders(customers):
    """Credit orders still owed, tagged the way the shop tags them (LIABILITY_TAGS)."""
    by_co = {(c.get("default_address") or {}).get("company"): c for c in customers}
    prods = {p["title"]: p for p in DASH["products"]}
    def it(title, vi, qty):
        p = prods[title]; li = _line(p, p["variants"][vi], qty, DASH["next_lid"]); DASH["next_lid"] += 1; return li
    plan = [  # company, tag, terms days (None = assumed), created days ago, items, financial_status, outstanding share
        ("Kestrel Logistics Ltd", "Purchase order unpaid", 30, 98, [("Walkway Safety Sign Gobo", 0, 8), ("LED Gobo Projector 30W", 0, 1)], "pending", 1.0),
        ("Northfield Academy Trust", "Procurement unpaid", 30, 52, [("Custom Glass Gobo (full colour)", 1, 4), ("Gobo Holder", 1, 4)], "pending", 1.0),
        ("Harbourside Events Ltd", "Purchase order unpaid", 14, 20, [("Custom Glass Gobo (1 colour)", 0, 5), ("Projection Lens 36 degree", 0, 1)], "pending", 1.0),
        ("Harbourside Events Ltd", "Purchase order unpaid", 14, 9, [("Custom Glass Gobo (1 colour)", 1, 2), ("Steel Gobo", 0, 2)], "pending", 1.0),
        ("Saltmarsh Hotel Group", "Bank transfer unpaid", None, 12, [("Outdoor Gobo Projector 80W IP65", 0, 1), ("Custom Glass Gobo (1 colour)", 0, 1)], "pending", 1.0),
        ("Riverside College", "Procurement unpaid", 30, 35, [("LED Gobo Projector 30W", 1, 2), ("Custom Glass Gobo (1 colour)", 2, 2)], "partially_paid", 0.5),
        ("Brackenfield Distribution", "Bank transfer unpaid", 7, 3, [("Walkway Safety Sign Gobo", 0, 3), ("Wall Mount Bracket", 0, 1)], "pending", 1.0),
        ("Copperleaf Interiors", "Bank transfer unpaid", 30, 40, [("Neon Effect Gobo", 0, 2)], "paid", 0.0),   # settled, still tagged
    ]
    out = []
    for co, tag, terms, ago, items, fin, share in plan:
        c = by_co[co]
        when = (_NOW - _dtd(days=ago)).replace(hour=10, minute=15, second=0)
        o = _mk_order(DASH["next_seq"], when, c, [it(*x) for x in items])
        DASH["next_seq"] += 1
        total = float(o["total_price"])
        o.update(tags=tag, financial_status=fin, payment_gateway_names=["Bank Deposit" if "Bank" in tag else "Purchase order"],
                 total_outstanding=_p(round(total * share, 2)))
        if terms:
            o["payment_terms"] = {"payment_terms_name": f"Net {terms}", "payment_terms_type": "NET",
                                  "due_in_days": terms,
                                  "payment_schedules": [{"due_at": _iso(when + _dtd(days=terms))}]}
        out.append(o)
    return out


def _decorate_orders(orders):
    """A few cancellations and partial refunds, newest window first."""
    recent = [o for o in orders if (_NOW - _ddt.fromisoformat(o["created_at"])).days < 150
              and o["financial_status"] == "paid" and not o["tags"]]
    for o in recent[5:7]:
        o.update(cancelled_at=_iso(_ddt.fromisoformat(o["created_at"]) + _dtd(hours=5)),
                 financial_status="voided", fulfillment_status=None)
    for k, o in enumerate(recent[20:80:12]):
        amt = round(min(45.0 + k * 12.5, float(o["total_price"]) / 2), 2)
        when = _ddt.fromisoformat(o["created_at"]) + _dtd(days=6)
        o["refunds"] = [{"id": 9100000001 + k, "created_at": _iso(when),
                         "transactions": [{"kind": "refund", "status": "success", "amount": _p(amt)}]}]
        o["financial_status"] = "partially_refunded"
        o["current_total_price"] = _p(float(o["total_price"]) - amt)


def _finish_customers(customers, orders):
    agg = {}
    for o in orders:
        if o.get("cancelled_at"):
            continue
        a = agg.setdefault(o["customer"]["id"], {"n": 0, "spent": 0.0, "first": o["created_at"], "last": o["created_at"]})
        a["n"] += 1
        a["spent"] += float(o["current_total_price"])
        a["first"] = min(a["first"], o["created_at"]); a["last"] = max(a["last"], o["created_at"])
    for c in customers:
        a = agg.get(c["id"])
        c["orders_count"] = a["n"] if a else 0
        c["total_spent"] = _p(a["spent"]) if a else "0.00"
        if a:
            c["created_at"] = _iso(_ddt.fromisoformat(a["first"]) - _dtd(days=2))
            c["updated_at"] = a["last"]
        else:
            c.setdefault("created_at", _iso(_NOW - _dtd(days=10)))
            c["updated_at"] = c["created_at"]


def _payouts():
    """Weekly Shopify Payments payouts over the last 70 days (paid), plus one in transit."""
    out = []
    for w in range(10):
        day = (_NOW - _dtd(days=5 + 7 * w)).date()
        amt = round(1400 + 380 * ((w * 37) % 7) + 17.16 * w, 2)
        out.append({"id": 7700000001 + w, "date": day.isoformat(), "amount": _p(amt), "currency": "GBP", "status": "paid"})
    out.insert(0, {"id": 7700000099, "date": (_NOW + _dtd(days=1)).date().isoformat(), "amount": "1288.40",
                   "currency": "GBP", "status": "scheduled"})
    return out


DASH["products"] = _build_products()
DASH["customers"] = _build_customers()
DASH["orders"] = _build_orders(DASH["products"], DASH["customers"])
DASH["orders"] += _liability_orders(DASH["customers"])
DASH["orders"].sort(key=lambda o: o["id"])
_decorate_orders(DASH["orders"])
_finish_customers(DASH["customers"], DASH["orders"])
DASH["customers"].sort(key=lambda c: c["id"])
DASH["payouts"] = _payouts()


def _when(v):
    try:
        t = _ddt.fromisoformat(str(v).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=_dtz.utc)
    except ValueError:
        return None


def _page(rows, args):
    since = int(args.get("since_id") or 0)
    rows = [r for r in rows if int(r["id"]) > since]
    if args.get("ids"):
        want = {int(x) for x in str(args["ids"]).split(",") if x.strip()}
        rows = [r for r in rows if int(r["id"]) in want]
    for k, op in (("created_at_min", "ge"), ("created_at_max", "le"), ("updated_at_min", "uge")):
        if args.get(k):
            lim = _when(args[k])
            key = "updated_at" if op == "uge" else "created_at"
            rows = [r for r in rows if _when(r.get(key)) and ((_when(r[key]) >= lim) if op in ("ge", "uge") else (_when(r[key]) <= lim))]
    rows.sort(key=lambda r: int(r["id"]))
    lim = int(args.get("limit") or 50)
    return [_dcopy.deepcopy(r) for r in rows[:lim]]


DASH["prev_tool_json"] = shopify._tool_json


async def dash_tool_json(registry, name, args):
    args = args or {}
    if name == "shopify_list_orders":
        rows = DASH["orders"]
        st = str(args.get("status") or "any")
        if st == "open":
            rows = [o for o in rows if not o.get("cancelled_at") and o.get("fulfillment_status") != "fulfilled"]
        elif st == "closed":
            rows = [o for o in rows if o.get("fulfillment_status") == "fulfilled"]
        elif st == "cancelled":
            rows = [o for o in rows if o.get("cancelled_at")]
        if args.get("financial_status") and args["financial_status"] != "any":
            rows = [o for o in rows if o.get("financial_status") == args["financial_status"]]
        mine = _page(rows, args)
        if not mine and not args.get("since_id") and not args.get("ids"):
            return await DASH["prev_tool_json"](registry, name, args)
        return {"orders": mine}
    if name == "shopify_get_order":
        oid = int(args.get("order_id") or 0)
        hit = next((o for o in DASH["orders"] if o["id"] == oid), None)
        return _dcopy.deepcopy(hit) if hit else await DASH["prev_tool_json"](registry, name, args)
    if name == "shopify_list_customers":
        return {"customers": _page(DASH["customers"], args)}
    if name == "shopify_list_products":
        rows = DASH["products"]
        if args.get("status"):
            rows = [p for p in rows if p["status"] == args["status"]]
        return {"products": _page(rows, args)}
    if name == "shopify_count_products":
        return {"count": len(DASH["products"])}
    if name == "shopify_get_product":
        pid = int(args.get("product_id") or 0)
        hit = next((p for p in DASH["products"] if p["id"] == pid), None)
        return _dcopy.deepcopy(hit) if hit else {}
    if name == "shopify_list_payouts":
        return {"payouts": _dcopy.deepcopy(DASH["payouts"])}
    if name == "shopify_payout_transactions":
        pid = int(args.get("payout_id") or 0)
        p = next((x for x in DASH["payouts"] if x["id"] == pid), None)
        fee = round(float(p["amount"]) * 0.019 + 0.2, 2) if p else 0
        return {"transactions": [{"type": "charge", "fee": _p(fee)}]}
    if name == "shopify_list_disputes":
        return {"disputes": []}
    return await DASH["prev_tool_json"](registry, name, args)


shopify._tool_json = dash_tool_json


def _ok(r, what):
    if r.status_code != 200:
        raise RuntimeError(what + " -> " + str(r.status_code) + " " + r.text[:300])
    return r.json()


# =============================================================================
# forecast: the cash flow workbook uploaded through the page's own route (a),
# read back through the service's door, parsed by the forecast package's own
# CashFlowModel.from_workbook, then the nightly service's maths (forecast/
# nightly.py main, minus its network) run on the fake store's orders and each
# run posted to /hooks/forecast/results (a). Four runs: three month-ends and
# yesterday, so the record of who was right has closed months in it.
# =============================================================================
def _month_starts(first, n):
    y, m, out = first.year, first.month, []
    for _ in range(n):
        out.append(_ddt(y, m, 1))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def _cash_by_month():
    tot = {}
    for o in DASH["orders"]:
        if o.get("cancelled_at"):
            continue
        k = o["created_at"][:7]
        tot[k] = tot.get(k, 0.0) + float(o["current_total_price"])
    return tot


def _workbook_bytes():
    import openpyxl
    cur = _ddt(_NOW.year, _NOW.month, 1)
    # The plan year starts five months before this one, so this month is inside it.
    ps = cur
    for _ in range(5):
        ps = (ps - _dtd(days=1)).replace(day=1)
    plan = _month_starts(ps, 12)
    a1 = _month_starts(_ddt(ps.year - 2, ps.month, 1), 12)
    a2 = _month_starts(_ddt(ps.year - 1, ps.month, 1), 12)
    cash = _cash_by_month()
    def sales(total):
        net = total / 1.2 - 40
        return [round(net, 2), 40.0, round(total - total / 1.2, 2), round(total, 2)]
    wb = openpyxl.Workbook()
    ws = wb.active; ws.title = "Assumptions"
    for row in (("Repayment rate", 0.18), ("Shopify deductible", 0.817), ("Total loan to repay", 30000), ("Cash buffer", 5000)):
        ws.append(row)
    cf = wb.create_sheet("Cash Flow")
    def block(label, months, totals):
        cf.append([label, "Month"] + months)
        rows = [sales(t) for t in totals]
        for j, name in enumerate(("Net Sales", "Shipping", "Taxes", "Total Sales")):
            cf.append([None, name] + [r[j] for r in rows])
        cf.append([])
    last = [cash.get(m.strftime("%Y-%m"), 0.0) for m in a2]
    block("Actual year one", a1, [cash.get(m.strftime("%Y-%m"), 0.0) for m in a1])
    block("Actual year two", a2, last)
    block("Projected Algorithm 1", plan, [round(v * 1.08 + 400, 2) for v in last])
    block("Projected Algorithm 2", plan, [round(v * 1.22 + 900, 2) for v in last])
    for n, k in ((1, 1.08), (2, 1.22)):
        fs = wb.create_sheet(f"Algorithm {n} Flow")
        fs.append(["Line"] + plan)
        gross = [round(v * k + 500, 2) for v in last]
        fs.append(["Shopify advance"] + [20000.0] + [0.0] * 11)
        fs.append(["Gross sales"] + gross)
        fs.append(["Base monthly overheads"] + [round(sum(last) / 12 * 0.72, 2)] * 12)
        fs.append(["Glass"] + [round(g * 0.04, 2) for g in gross])
        fs.append(["Projector stock"] + [round(g * 0.06, 2) for g in gross])
        fs.append(["Marketing"] + [950.0] * 12)
        fs.append(["Unexpected"] + [round(g * 0.03, 2) for g in gross])
        fs.append(["Shopify repayment"] + [round(g * 0.147, 2) for g in gross])
        fs.append(["Working capital"] + [0.0] * 12)
        fs.append(["Starting loan"] + [30000.0] * 12)
    buf = _dio.BytesIO(); wb.save(buf)
    return buf.getvalue()


def _fc_orders():
    return [{"created_at": o["created_at"], "order_total": float(o["current_total_price"]), "test": False,
             "cancelled_at": o.get("cancelled_at"), "financial_status": o["financial_status"]} for o in DASH["orders"]]


def _fc_run(as_of, cf, hook):
    from forecast.cpu import apply_thread_limits
    apply_thread_limits()
    import pandas as pd
    from forecast.cashflow import DayProfile
    from forecast.config import Config
    from forecast.ingest import daily_cash, monthly_cash
    from forecast.simple import BIG_ORDER, band_width, daily_frame, pick_opinions, sanity_forecasts
    from forecast.variance import VarianceEngine
    from forecast import nightly as fcn
    orders = [o for o in _fc_orders() if o["created_at"][:10] <= as_of.isoformat()]
    since = (as_of - _dtd(days=1830)).replace(day=1)
    months = monthly_cash(orders, as_of, since)
    big = monthly_cash(orders, as_of, since, min_total=BIG_ORDER)
    actual_daily = daily_cash(orders, as_of)
    # The regular orders by day are what the Prophet methods read. The image
    # does not carry Prophet, so neither does this world: handed the days, a
    # machine that has it installed (make install does) would seed a page
    # production never shows, and differ from CI's.
    daily_small = None
    cfg = Config(as_of=as_of, horizon_days=90)
    first = pd.Period(as_of, freq="M")
    last = max((pd.Period(m, freq="M") for m in cf.projection_months()), default=first)
    need = max(1, (last.year - first.year) * 12 + (last.month - first.month) + 1)
    record = _ok(client.get("/hooks/forecast/ledger", headers=hook), "forecast ledger").get("results") or []
    sanity = sanity_forecasts(months, horizon=min(need, 18), results=record, big=big, daily_small=daily_small)
    if not sanity.get("available"):
        raise RuntimeError("forecast: " + str(sanity.get("reason")))
    opinions = pick_opinions(sanity)
    primary = opinions[0]
    eng = VarianceEngine(cfg, cf)
    fdaily = daily_frame(primary, as_of, DayProfile.fit(actual_daily))
    mv = eng.monthly_view(actual_daily, fdaily)
    cv = {n: eng.cash_view(mv, n) for n in cf.scenario_names if n in cf.flows}
    alerts = eng.alerts(mv, cv)
    fcn._year_per_source(sanity, mv, cf)
    payload = fcn._payload(cfg, cf, sanity, opinions, mv, cv, alerts, eng.summary(mv, cv, alerts), actual_daily, fdaily)
    payload["seen_through"] = str(months.index[-1])
    payload["in_use"] = fcn._in_use(primary, mv, band_width(primary))
    body = _djson.loads(_djson.dumps(payload, default=str))
    r = client.post("/hooks/forecast/results", json=body, headers=hook)
    _ok(r, "forecast results " + as_of.isoformat())
    return payload


def seed_forecast():
    from forecast.cashflow import CashFlowModel
    from zoneinfo import ZoneInfo
    import base64 as _b64
    tok_ = forecasting.FORECAST_INGEST_TOKEN
    if not tok_:
        raise RuntimeError("FORECAST_INGEST_TOKEN must be set before the prelude (launch.py sets it)")
    hook = {"X-Forecast-Token": tok_}
    _ok(post("/api/forecast/workbook", {"name": "Cash Flow plan.xlsx",
                                        "data_b64": _b64.b64encode(_workbook_bytes()).decode()}), "workbook upload")
    r = client.get("/hooks/forecast/workbook", headers=hook)
    if r.status_code != 200:
        raise RuntimeError("workbook fetch " + str(r.status_code))
    with _dtemp.NamedTemporaryFile(suffix=".xlsx", dir=SCRATCH, delete=False) as fh:
        fh.write(r.content)
    cf = CashFlowModel.from_workbook(fh.name)
    today = _ddt.now(ZoneInfo("Europe/London")).date()
    ends = []
    m1 = today.replace(day=1)
    for _ in range(3):
        m1 = (m1 - _dtd(days=1)).replace(day=1)
    for k in range(3):
        nxt = (m1 + _dtd(days=32)).replace(day=1)
        ends.append(nxt - _dtd(days=1))
        m1 = nxt
    runs = []
    for as_of in ends + [today - _dtd(days=1)]:
        runs.append(_fc_run(as_of, cf, hook))
    DASH["forecast_runs"] = [(p["as_of"], len(p["monthly"]), (p.get("sanity") or {}).get("best")) for p in runs]


# =============================================================================
# connector (Xero sync): the connector is its own HTTP service, so it is stood
# in for by one (c): a ThreadingHTTPServer on 127.0.0.1, port chosen by the OS,
# answering the seven GET doors with the shapes the connector's src/server.ts
# returns, and refusing every POST. CONNECTOR_URL points the app at it, so the
# app's real _connector_call (httpx) runs.
# =============================================================================
def _sync_result(dry, fetched, inv, cn=0, ct=0, inxero=0, **kw):
    r = {"dryRun": dry, "ordersFetched": fetched, "deferred": 0,
         "contacts": {"created": ct, "failed": 0, "skippedExisting": max(0, fetched - ct), "skippedSynced": 0},
         "invoices": {"created": inv, "failed": 0, "quarantined": 0, "skippedSynced": inxero, "skippedNoContact": 0,
                      "skippedTest": 0, "skippedCancelled": 0, "voided": 0, "updated": 0, "updateBlocked": 0,
                      "skippedInXero": 0, "quarantinedStanding": 0},
         "creditNotes": {"created": cn, "failed": 0, "quarantined": 0, "skippedSynced": 0, "skippedNoContact": 0,
                         "quarantinedStanding": 0},
         "warnings": []}
    for k, v in kw.items():
        r["invoices"][k] = v
    return r


def _connector_state():
    def at(mins):
        return (_NOW - _dtd(minutes=mins)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    spec = [  # minutes ago, dryRun, orders read, invoices, credit notes, contacts, already in Xero
        (26, False, 4, 3, 0, 1, 1), (190, False, 3, 2, 1, 0, 1), (372, True, 6, 5, 0, 1, 1),
        (1210, False, 5, 4, 0, 2, 1), (1505, False, 2, 1, 1, 0, 1), (2890, False, 6, 5, 0, 1, 1),
        (3020, True, 6, 5, 0, 1, 1), (4310, False, 3, 3, 0, 1, 0)]
    runs = []
    for k, (mins, dry, n, inv, cn, ct, inx) in enumerate(spec):
        runs.append({"id": f"run-{9000 - k}", "startedAt": at(mins + 1), "finishedAt": at(mins), "durationMs": 41000 + 900 * k,
                     "dryRun": dry, "ok": True, "result": _sync_result(dry, n, inv, cn, ct, inx)})
    last = runs[0]
    status = {"running": False, "lastError": None, "ledger": {"synced": 418, "failed": 0, "quarantined": 0, "total": 418},
              "quarantineCount": 0, "lastRun": last, "tagJob": None,
              "config": {"shop": "test-store.myshopify.com", "reconcileMode": "warn", "dryOnly": False,
                         "shopifyAuth": "client_credentials"}}
    health = {"autoRun": None, "lastRunAt": last["finishedAt"], "lastRunId": last["id"], "lastRunDryRun": False,
              "line": "4 orders checked, 4 documents created", "needsAttention": False, "problems": [],
              "standing": {"quarantined": 0, "deferred": 0},
              "guards": {"maxDocsPerRun": 50, "runawayAbortAbove": 200, "reconcileMode": "warn", "reconcileTolerance": 0.05}}
    autorun = {"enabled": True, "intervalMinutes": 10, "lastTickAt": at(4), "nextTickAt": (_NOW + _dtd(minutes=6)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
               "ticks": 1287, "lastOutcome": "Nothing new to send"}
    health["autoRun"] = autorun
    settings = {"RECONCILE_MODE": "warn", "RECONCILE_TOLERANCE": "0.05", "MAX_DOCS_PER_RUN": "50", "RUNAWAY_ABORT_ABOVE": "200",
                "ORDERS_SINCE": (_NOW - _dtd(days=60)).date().replace(day=1).isoformat(), "XERO_SALES_ACCOUNT_CODE": "200",
                "XERO_TAX_TYPE_STANDARD": "OUTPUT2", "XERO_TAX_TYPE_ZERO": "ZERORATEDOUTPUT",
                "CUSTOMER_REF_METAFIELD_NAMESPACE": "custom", "CUSTOMER_REF_METAFIELD_KEY": "po_reference",
                "AUTO_RUN_INTERVAL_MINUTES": "10",
                "hasShopifyToken": True, "hasXeroClientId": True, "hasXeroClientSecret": True}
    recent = [o for o in DASH["orders"] if not o.get("cancelled_at")][-12:]
    ledger = [{"kind": "invoice", "key": o["name"], "status": "synced", "xeroId": f"XI-{o['order_number']}",
               "syncedAt": at(30 + 60 * k)} for k, o in enumerate(reversed(recent))]
    return {"/api/status": status, "/api/runs": runs, "/api/health": health, "/api/autorun": autorun,
            "/api/settings": settings, "/api/quarantine": [], "/api/ledger": ledger}


class _ConnHandler(_DHandler):
    def _send(self, code, body):
        raw = _djson.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        st = DASH["connector_state"]
        DASH["connector_hits"].append(("GET", path))
        if path in st:
            self._send(200, st[path])
        else:
            self._send(404, {"error": "No such door on the seed's connector: " + path})
    def do_POST(self):
        DASH["connector_hits"].append(("POST", self.path))
        self._send(409, {"error": "The seed's connector writes nothing."})
    def log_message(self, *a):
        pass


def seed_connector():
    DASH["connector_state"] = _connector_state()
    DASH["connector_hits"] = []
    srv = _DServer(("127.0.0.1", 0), _ConnHandler)
    _dthreading.Thread(target=srv.serve_forever, daemon=True, name="dash-connector").start()
    DASH["connector_server"] = srv
    _dos.environ["CONNECTOR_URL"] = "http://127.0.0.1:%d" % srv.server_address[1]
    _dos.environ.pop("CONNECTOR_TOKEN", None)


# =============================================================================
# The background scheduler would, 60 s after the first page load, poll the
# connector into alerts and run the watchdog against the fake store (in a
# control run on 14 Oct 2026 it also reached for Xero, which it no longer
# does). The suite keeps it off: marked as started, it never starts.
# =============================================================================
def seed_scheduler_off():
    scheduler._scheduler_started = True


def seed_dashboards():
    t0 = _dtime.time()
    seed_scheduler_off()
    seed_forecast()
    seed_connector()
    DASH["seconds"] = round(_dtime.time() - t0, 1)
    return DASH
