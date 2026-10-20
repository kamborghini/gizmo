# Seed for the operations screens of the browser suite: Production Manager,
# (Proven 14 Oct 2026 against the dispatch setup; joined to the dashboards'
# Shopify store the same day: see the note above ops_shopify.)
# Size list (rule dialog), CRM, Loan units, Inbox and Files.
#
# Runs AFTER the harness prelude of tests/test_dispatch.py, in the prelude's own
# globals (post, copilot, worldoptions, SCRATCH, OPT, BOX, _RoutedHttpx, ...),
# exactly where launch.py would run it before serving. Every person, company,
# address, email and phone number here is invented (example.com/.org, Ofcom
# drama range 01632 960xxx). Dates are relative to now, so the suite does not
# rot as the calendar moves.
#
# Each section says which kind of seed it is:
#   (a) the app's own route via post(...)
#   (b) the store's own writer
#   (c) an in-process stand-in for a system the app reaches over the network
#       (Shopify, World Options, Gmail, R2). Never real network.

# ============================ SHARED ========================================
import base64 as _b64, email.utils as _eut, itertools as _it, re as _re
import xml.etree.ElementTree as _ET
import httpx as _hx
from datetime import datetime as _dt, timedelta as _td, timezone as _tz
import google_mail as _gmail

_NOW = _dt.now(_tz.utc)
def _at(days_ago=0, hours_ago=0, hour=None):
    t = _NOW - _td(days=days_ago, hours=hours_ago)
    if hour is not None:
        t = t.replace(hour=hour, minute=12, second=0, microsecond=0)
    return t
def _iso(t):
    return t.isoformat().replace("+00:00", "Z")
def _day(days):            # a London-ish calendar date, days from today (negative = past)
    return (_NOW + _td(days=days)).date().isoformat()
def _ok200(r, what):
    if r.status_code != 200:
        raise RuntimeError(f"seed step failed: {what}: {r.status_code} {r.text[:300]}")
    return r.json()

# -- Team (a): three invented colleagues who can own email, deals and loans.
#    POST /api/team/user {"op": "create"} exactly as make_user() in the tests.
OPS_TEAM = {}
# Another group's seed may already have made them: reuse by username.
_existing = {u.get("username"): uid for uid, u in team._load_users()["users"].items() if not u.get("deleted")}
for _name, _uname, _role in (("Priya Hale", "priya", "admin"), ("Owen Marsh", "owen", "member"),
                             ("Grace Okafor", "grace", "member")):
    if _uname in _existing:
        OPS_TEAM[_uname] = _existing[_uname]
        continue
    _j = _ok200(post("/api/team/user", {"op": "create", "name": _name, "username": _uname, "role": _role}),
                "create " + _uname)
    OPS_TEAM[_uname] = [u["id"] for u in _j["users"] if u["username"] == _uname][0]
OPS_MASTER = APP_AUTH["master"]

# ============================ SHOPIFY STAND-IN (c) ===========================
# One in-memory store answers every Shopify read the operations screens make
# (copilot._tool_json, the seam the tests swap), and the tag writer moves an
# order's tags in that store, so Mark made / booking leave it where Shopify
# would. Names it does not know fall through to whatever was installed before
# (the prelude's fake, or another group's stand-in).
OPS_SHOP = {"name": "Lumenfield Test Shop", "address1": "4 Foundry Lane", "city": "Leeds",
            "zip": "LS9 8ZZ", "country_code": "GB", "phone": "01632 960001",
            "email": "shop@example.com", "currency": "GBP"}
_CUSTOMERS = {
    501: ("Hannah", "Wren", "hannah.wren@example.com"),
    502: ("Marcus", "Bell", "marcus@hartwell-events.example.com"),
    503: ("Nadia", "Kerr", "nadia.kerr@example.org"),
    504: ("Tom", "Ashby", "tom@saltmarsh-brewing.example.com"),
    505: ("Freya", "Lund", "freya.lund@example.com"),
    506: ("Callum", "Reid", "callum@northgate-playhouse.example.org"),
    507: ("Imogen", "Shaw", "imogen.shaw@example.com"),
    508: ("Arjun", "Mehta", "arjun@quayside-expo.example.com"),
    509: ("Zara", "Pike", "zara.pike@example.org"),
    510: ("Leo", "Fenwick", "leo@fernhill-academy.example.org"),
}
_ADDR = {
    501: ("", "12 Orchard Row", "", "York", "YO1 9ZZ"),
    502: ("Hartwell Events Ltd", "Unit 7, Calder Works", "Wharf Road", "Wakefield", "WF1 9ZZ"),
    503: ("", "3 Linnet Close", "", "Bristol", "BS3 9ZZ"),
    504: ("Saltmarsh Brewing Co", "The Old Maltings", "Quay Street", "Whitby", "YO21 9ZZ"),
    505: ("", "28 Heather Lane", "", "Harrogate", "HG1 9ZZ"),
    506: ("Northgate Playhouse", "1 Playhouse Yard", "", "Durham", "DH1 9ZZ"),
    507: ("", "9 Mill Cottages", "", "Kendal", "LA9 9ZZ"),
    508: ("Quayside Exhibitions", "Hall B, Riverside Centre", "", "Hull", "HU1 9ZZ"),
    509: ("", "41 Larch Avenue", "", "Norwich", "NR2 9ZZ"),
    510: ("Fernhill Academy", "Fernhill Road", "", "Leeds", "LS6 9ZZ"),
}
_PRODUCTS = {   # product_id -> (option names, product type)
    9101: (["Glass Type"], "Custom Gobos"),
    9102: (["Gobo Size"], "Gobo"),
    9103: ([], "Projector"),
    9104: (["Glass Type"], "Custom Gobos"),
}
_li_ids = _it.count(77001)
def _line(title, qty, price, pid, mfr=None, model=None, glass=None, extra=None, vt="", sku=""):
    props = []
    if mfr: props.append({"name": "Manufacturer", "value": mfr})
    if model: props.append({"name": "Model", "value": model})
    if glass: props.append({"name": "Glass Type", "value": glass})
    for k, v in (extra or {}).items():
        props.append({"name": k, "value": v})
    return {"id": next(_li_ids), "title": title, "name": title + (" - " + vt if vt else ""),
            "quantity": qty, "current_quantity": qty, "price": price, "grams": 90,
            "product_id": pid, "variant_id": pid * 10 + 1, "variant_title": vt, "sku": sku,
            "properties": props}
def _order(oid, num, cust, tags, days_ago, lines, ship=("Royal Mail Tracked 24", "4.95"), note=""):
    f, l, em = _CUSTOMERS[cust]
    co, a1, a2, city, pc = _ADDR[cust]
    addr = {"name": f + " " + l, "first_name": f, "last_name": l, "company": co, "address1": a1,
            "address2": a2, "city": city, "province_code": "", "zip": pc, "country_code": "GB",
            "country": "United Kingdom", "phone": "01632 960" + str(100 + cust % 100)}
    total = sum(float(x["price"]) * x["quantity"] for x in lines) + float(ship[1])
    return {"id": oid, "order_number": num, "name": "#" + str(num),
            "created_at": _iso(_at(days_ago, hour=9 + oid % 8)), "email": em, "currency": "GBP",
            "financial_status": "paid", "fulfillment_status": None, "cancelled_at": None,
            "tags": tags, "note": note, "taxes_included": True,
            "total_price": "%.2f" % total, "current_total_price": "%.2f" % total,
            "customer": {"id": cust, "first_name": f, "last_name": l, "email": em},
            "billing_address": dict(addr), "shipping_address": dict(addr), "line_items": lines,
            "shipping_lines": [{"title": ship[0], "price": ship[1], "discounted_price": ship[1]}]}

OPS_ORDERS = {o["id"]: o for o in [
    # Unprocessed: waiting to be released to the bench
    _order(880101, 210401, 509, "Unprocessed", 0, [
        _line("Custom Gobo", 2, "39.00", 9101, "Robe", "Forte", "Monochrome Glass - Original")]),
    _order(880102, 210402, 505, "Unprocessed", 1, [
        _line("Wedding Monogram Gobo", 1, "45.00", 9101, "Chauvet", "Rogue R2 Spot", "Colour Glass - Original",
              extra={"Wedding Date": _day(26)})]),
    # To make (IP)
    _order(880201, 210388, 502, "IP", 2, [
        _line("Custom Gobo", 4, "39.00", 9101, "Ayrton", "Khamsin", "Monochrome Glass - Original",
              extra={"Date Required": _day(2)}),
        _line("Custom Gobo", 2, "39.00", 9101, "Ayrton", "Domino Profile", "Monochrome Glass - Copy")],
        ship=("DPD Next Day", "9.50")),
    _order(880202, 210391, 506, "IP", 3, [
        _line("Custom Gobo", 1, "52.00", 9104, "Martin", "MAC Encore Performance", "Colour Glass - Original")]),
    _order(880203, 210395, 501, "IP", 4, [
        _line("Stars Gobo", 1, "18.00", 9102, vt="B Size"),
        _line("Custom Gobo", 1, "39.00", 9101, "Robe", "Moonbeam Profile 300", "Monochrome Glass - Original")]),
    _order(880204, 210397, 507, "IP", 5, [
        _line("Wedding Names Gobo", 1, "45.00", 9101, "Chauvet", "Rogue R2 Spot", "Monochrome Glass - Original",
              extra={"Wedding Date": _day(9)})]),
    _order(880205, 210399, 510, "IP", 6, [
        _line("Custom Gobo", 3, "39.00", 9101, "Ayrton", "Huracan Profile", "Monochrome Glass - Original"),
        _line("40W LED Gobo Projector", 1, "289.00", 9103, vt="40W with Rain Hood")],
        ship=("UPS Express", "14.40")),
    # To ship (PC)
    _order(880301, 210371, 504, "PC", 8, [
        _line("Custom Gobo", 6, "35.00", 9101, "Ayrton", "Eurus Profile", "Monochrome Glass - Original")],
        ship=("UPS Express", "14.40")),
    _order(880302, 210374, 503, "PC", 9, [
        _line("Custom Gobo", 1, "39.00", 9101, "Ayrton", "Ghibli", "Colour Glass - Original")]),
    _order(880303, 210377, 508, "PC", 10, [
        _line("Custom Gobo", 2, "39.00", 9101, "Ayrton", "Perseo Profile", "Monochrome Glass - Original")],
        ship=("DPD Next Day", "9.50")),
    # Complete (booked and fulfilled below through the dispatch route)
    _order(880401, 210351, 502, "PC", 15, [
        _line("Custom Gobo", 2, "39.00", 9101, "Ayrton", "Mistral", "Monochrome Glass - Original")]),
    _order(880402, 210356, 506, "PC", 14, [
        _line("Custom Gobo", 1, "39.00", 9101, "Ayrton", "Levante", "Monochrome Glass - Original")]),
]}

def _ops_tags(o):
    return [t.strip() for t in str(o.get("tags") or "").split(",") if t.strip()]

# The Production Manager's orders join the dashboards' store, so every screen
# reads one shop: list and get go to dash_tool_json, which pages DASH["orders"];
# the rest below is this stand-in's own. The same dicts are shared, so the
# tag writer's changes are seen by both. updated_at is set so a "changed
# since" read (updated_at_min) finds them as it finds the dashboards' orders.
for _o in OPS_ORDERS.values():
    _o.setdefault("updated_at", _o["created_at"])
DASH["orders"].extend(OPS_ORDERS.values())
DASH["orders"].sort(key=lambda o: int(o["id"]))

_OPS_PREV_TOOL_JSON = shopify._tool_json
async def ops_shopify(registry, name, args):
    args = args or {}
    if name == "shopify_get_shop":
        return dict(OPS_SHOP)
    if name == "shopify_get_customer_orders":
        cid = int(args.get("customer_id") or 0)
        mine = [dict(o) for o in OPS_ORDERS.values() if (o.get("customer") or {}).get("id") == cid]
        # a repeat customer has history beyond this queue
        if cid in (502, 506):
            mine.append({"id": 870000 + cid, "name": "#20" + str(cid), "created_at": _iso(_at(140))})
        return {"orders": mine}
    if name == "shopify_get_product":
        pid = int(args.get("product_id") or 0)
        if pid in _PRODUCTS:
            names, ptype = _PRODUCTS[pid]
            return {"id": pid, "options": [{"name": n} for n in names], "product_type": ptype}
    return await _OPS_PREV_TOOL_JSON(registry, name, args)
shopify._tool_json = ops_shopify

_OPS_PREV_TAGS = shopify._order_tag_writer
async def ops_tag_writer(order_id, tags):
    o = OPS_ORDERS.get(int(order_id))
    if o is not None:
        o["tags"] = tags
    return await _OPS_PREV_TAGS(order_id, tags)
shopify._order_tag_writer = ops_tag_writer

_OPS_PREV_FULFIL = shopify._fulfillment_writer
async def ops_fulfil(order_id, tracking_number=None, tracking_company=None, tracking_url=None, notify_customer=True):
    o = OPS_ORDERS.get(int(order_id))
    if o is not None:
        o["fulfillment_status"] = "fulfilled"
    return await _OPS_PREV_FULFIL(order_id, tracking_number, tracking_company, tracking_url, notify_customer)
shopify._fulfillment_writer = ops_fulfil

# World Options (c): the prelude's fake SOAP answers every booking with one
# tracking number; this gives each booking its own, so the lists read true.
# The prelude's label is nine bytes of "%PDF-1.4", which the app's label
# renderer logs as an ERROR; a real one-page 4x6 PDF, made in-process, is not.
import io as _io, pypdfium2 as _pdfium
_lp = _pdfium.PdfDocument.new(); _lp.new_page(288, 432); _lb = _io.BytesIO(); _lp.save(_lb)
OPS_LABEL_PDF = _b64.b64encode(_lb.getvalue()).decode()
_OPS_PREV_SOAP = worldoptions._soap_call
_ops_trk = _it.count(4471)
async def ops_soap(service, action, inner, retryable=True):
    root = await _OPS_PREV_SOAP(service, action, inner, retryable)
    if service == "ShipmentService":
        n = next(_ops_trk)
        for el_ in root.iter("MasterTrackingNo"):
            el_.text = "1Z9F" + str(n).zfill(4) + "6600" + str(n % 97).zfill(4)
        for el_ in root.iter("Image"):
            el_.text = OPS_LABEL_PDF
        for el_ in root.iter("ImageLength"):
            el_.text = str(len(OPS_LABEL_PDF))
    return root
worldoptions._soap_call = ops_soap

# ============================ CRM ===========================================
# All (a): POST /api/crm/contact|deal|activity|lead with the payloads crm_seed()
# and t_a_lead_converts... use; then (b) the store's writer back-dates won/lost
# deals so Insights has months to chart (the tests age the store by hand too).
def _crm(path, body, what):
    return _ok200(post(path, body), what)
OPS_ORGS = {}
for _n, _addr_, _web in (("Hartwell Events Ltd", "Unit 7, Calder Works, Wakefield WF1 9ZZ", "hartwell-events.example.com"),
                         ("Northgate Playhouse", "1 Playhouse Yard, Durham DH1 9ZZ", "northgate-playhouse.example.org"),
                         ("Saltmarsh Brewing Co", "The Old Maltings, Whitby YO21 9ZZ", "saltmarsh-brewing.example.com"),
                         ("Quayside Exhibitions", "Riverside Centre, Hull HU1 9ZZ", "quayside-expo.example.com"),
                         ("Fernhill Academy", "Fernhill Road, Leeds LS6 9ZZ", "fernhill-academy.example.org"),
                         ("Copperbeck Hotels", "Lakeside Drive, Keswick CA12 9ZZ", "copperbeck.example.com"),
                         ("Brindlewood Logistics", "Gateway 4, Doncaster DN4 9ZZ", "brindlewood.example.com"),
                         ("Larkmoor Venues", "The Barn, Larkmoor, Malton YO17 9ZZ", "larkmoor.example.org")):
    OPS_ORGS[_n] = _crm("/api/crm/contact", {"op": "org_add", "name": _n, "address": _addr_, "website": _web},
                        "org " + _n)["id"]
OPS_PEOPLE = {}
for _n, _org, _em, _ph, _job in (
        ("Marcus Bell", "Hartwell Events Ltd", "marcus@hartwell-events.example.com", "01632 960301", "Production manager"),
        ("Callum Reid", "Northgate Playhouse", "callum@northgate-playhouse.example.org", "01632 960302", "Head of lighting"),
        ("Tom Ashby", "Saltmarsh Brewing Co", "tom@saltmarsh-brewing.example.com", "01632 960303", "Marketing lead"),
        ("Arjun Mehta", "Quayside Exhibitions", "arjun@quayside-expo.example.com", "01632 960304", "Operations director"),
        ("Leo Fenwick", "Fernhill Academy", "leo@fernhill-academy.example.org", "01632 960305", "Site manager"),
        ("Sophie Varga", "Copperbeck Hotels", "sophie.varga@copperbeck.example.com", "01632 960306", "Events coordinator"),
        ("Ben Hollis", "Brindlewood Logistics", "ben.hollis@brindlewood.example.com", "01632 960307", "Health and safety manager"),
        ("Megan Clay", "Larkmoor Venues", "megan@larkmoor.example.org", "01632 960308", "Venue manager"),
        ("Hannah Wren", "", "hannah.wren@example.com", "01632 960309", ""),
        ("Isaac Thorne", "", "isaac.thorne@example.org", "01632 960310", "Freelance lighting designer")):
    OPS_PEOPLE[_n] = _crm("/api/crm/contact", {"op": "person_add", "name": _n, "org_id": OPS_ORGS.get(_org, ""),
                                               "emails": [_em], "phones": [_ph], "job_title": _job},
                          "person " + _n)["id"]
OPS_DEALS = {}
for _t, _who, _val, _stage, _label, _close, _owner in (
        ("Hartwell: 40 branded gobos for autumn tour", "Marcus Bell", 1560, "s4", "Hot", _day(12), "priya"),
        ("Northgate panto window projection", "Callum Reid", 2350, "s3", "Warm", _day(30), "owen"),
        ("Saltmarsh taproom logo projector", "Tom Ashby", 640, "s2", "Warm", _day(21), "grace"),
        ("Quayside expo floor wayfinding", "Arjun Mehta", 4800, "s5", "Hot", _day(7), "priya"),
        ("Fernhill walkway safety signs", "Leo Fenwick", 3200, "s1", "Cold", _day(60), "owen"),
        ("Copperbeck wedding package", "Sophie Varga", 1180, "s3", "", _day(45), "grace"),
        ("Brindlewood forklift zone projectors", "Ben Hollis", 7600, "s4", "Hot", _day(18), "priya"),
        ("Larkmoor barn gobo set", "Megan Clay", 520, "s2", "", "", "owen"),
        ("Isaac: touring rig spares", "Isaac Thorne", 890, "s1", "Warm", _day(40), "grace")):
    _id = _crm("/api/crm/deal", {"op": "add", "title": _t, "person_id": OPS_PEOPLE[_who], "value": _val,
                                 "stage_id": _stage, "label": _label, "expected_close": _close,
                                 "owner": OPS_TEAM.get(_owner, "")}, "deal " + _t)["id"]
    OPS_DEALS[_t] = _id
# Won and lost history (a) for Insights, then back-dated (b).
_HIST = []
for _i, (_t, _who, _val, _won, _reason) in enumerate((
        ("Hartwell spring roadshow gobos", "Marcus Bell", 980, True, ""),
        ("Northgate summer season gobos", "Callum Reid", 1420, True, ""),
        ("Saltmarsh beer festival projector", "Tom Ashby", 760, True, ""),
        ("Quayside trade show logos", "Arjun Mehta", 2100, True, ""),
        ("Copperbeck lobby projector", "Sophie Varga", 1350, True, ""),
        ("Fernhill open day signs", "Leo Fenwick", 450, False, "Timing"),
        ("Brindlewood pilot unit", "Ben Hollis", 1900, False, "Went with someone else"),
        ("Larkmoor Christmas gobos", "Megan Clay", 300, False, "Too expensive"),
        ("Hartwell festival rig", "Marcus Bell", 2600, True, ""))):
    _id = _crm("/api/crm/deal", {"op": "add", "title": _t, "person_id": OPS_PEOPLE[_who], "value": _val,
                                 "stage_id": "s4"}, "deal " + _t)["id"]
    _crm("/api/crm/deal", {"op": "won", "id": _id} if _won else
         {"op": "lost", "id": _id, "reason": _reason, "comment": "Seeded history"}, "close " + _t)
    _HIST.append((_id, _won, (3, 24, 38, 52, 70, 33, 61, 88, 105)[_i]))
_d = salesdesk._load_crm()
for _id, _won, _ago in _HIST:
    _deal = _d["deals"][_id]
    _closed = _at(_ago, hour=15)
    _made = _closed - _td(days=24 + _ago % 17)
    for _k in ("created_at", "stage_entered_at", "touched_at"):
        _deal[_k] = _made.isoformat()
    _deal["updated_at"] = _closed.isoformat()
    _deal["won_at" if _won else "lost_at"] = _closed.isoformat()
for _t, _id in OPS_DEALS.items():   # open deals were made over the last few weeks
    _made = _at(5 + (len(_t) * 7) % 40, hour=10)
    for _k in ("created_at", "stage_entered_at"):
        _d["deals"][_id][_k] = _made.isoformat()
salesdesk._write_crm(_d)
# Activities (a): POST /api/crm/activity op add (t_the_card_icon_follows_the_next_activity...).
for _t, _type, _subject, _due, _done, _who in (
        ("Hartwell: 40 branded gobos for autumn tour", "call", "Confirm artwork sign-off", _day(-2), False, "priya"),
        ("Northgate panto window projection", "meeting", "Site visit for window throw", _day(0), False, "owen"),
        ("Saltmarsh taproom logo projector", "email", "Send revised quote", _day(1), False, "grace"),
        ("Quayside expo floor wayfinding", "deadline", "Proposal due", _day(3), False, "priya"),
        ("Fernhill walkway safety signs", "task", "Draft sign layout", _day(-5), False, "owen"),
        ("Copperbeck wedding package", "call", "Talk through monogram options", _day(6), False, "grace"),
        ("Brindlewood forklift zone projectors", "meeting", "Demo at the Doncaster depot", _day(9), False, "priya"),
        ("Quayside expo floor wayfinding", "call", "Intro call", _day(-12), True, "priya"),
        ("Hartwell: 40 branded gobos for autumn tour", "email", "Sent sample photos", _day(-8), True, "priya"),
        ("Isaac: touring rig spares", "lunch", "Catch up at the trade show", _day(14), False, "grace")):
    _crm("/api/crm/activity", {"op": "add", "type": _type, "deal_id": OPS_DEALS[_t], "subject": _subject,
                               "due_date": _due, "done": _done, "assignee": OPS_TEAM.get(_who, ""),
                               "note": "Seeded: " + _subject.lower() + "."}, "activity " + _subject)
# Leads (a): POST /api/crm/lead op add (t_a_lead_converts_into_a_deal...).
for _org_or_person, _title, _val, _label, _src in (
        ("Copperbeck Hotels", "Second hotel: lobby gobo", 600, "Warm", "Website"),
        ("Isaac Thorne", "Rental stock enquiry", 1200, "Hot", "Phone"),
        ("Larkmoor Venues", "Outdoor projector for courtyard", 900, "Cold", "Website"),
        ("Hannah Wren", "Engagement party monogram", 120, "", "Email")):
    _body = {"op": "add", "title": _title, "value": _val, "label": _label, "source": _src}
    if _org_or_person in OPS_ORGS:
        _body["org_id"] = OPS_ORGS[_org_or_person]
    else:
        _body["person_id"] = OPS_PEOPLE[_org_or_person]
    _crm("/api/crm/lead", _body, "lead " + _title)

# ============================ PRODUCTION MANAGER =============================
# Shipping settings (a): POST /api/shipping/config op set, payload as
# t_config_creds_write_only and t_a_box_preset_can_be_made_the_dispatch_default.
_ok200(post("/api/shipping/config", {"op": "set", "meter_number": "METER-9999", "key": "KEY-abc",
                                     "password": "PW-xyz",
                                     "origin": {"company": "Lumenfield Test Shop", "street": "4 Foundry Lane",
                                                "city": "Leeds", "postcode": "LS9 8ZZ", "country": "GB",
                                                "phone": "01632 960001", "email": "shop@example.com"},
                                     "boxes": [{"id": "small", "name": "Gobo mailer", "width": 20, "length": 15,
                                                "depth": 5, "weight": 0.2},
                                               {"id": "big", "name": "Projector box", "width": 40, "length": 30,
                                                "depth": 25, "weight": 1.4}],
                                     "default_box_id": "small"}), "shipping config")
# Printed stamps (b): the store's own writer, as the print path calls it.
production._mark_printed([880201, 880202, 880301, 880302, 880303, 880401, 880402])
# Made (b): the made stamp writer (the route also fulfils and books glass at
# the stock app; the stamp is all the queue reads).
for _oid in (880301, 880302, 880303, 880401, 880402):
    production._mark_made(_oid, True)
# Complete (a): two made orders booked through the real dispatch route; a made
# order with a label fulfils on booking, and ops_tag_writer files it as Complete.
for _oid in (880401, 880402):
    _ok200(post("/api/dispatch/book", {"order_id": _oid, "option": OPT, "box": BOX}), "book %d" % _oid)
# One To-make order already has its courier label booked ahead of Mark made
# (its tracking shows on the row; it fulfils when it is marked made).
_ok200(post("/api/dispatch/book", {"order_id": 880201, "option": OPT, "box": BOX}), "book 880201")

# ============================ CUSTOM SHIPMENTS ==============================
# Custom shipments (a): POST /api/custom/book with the body custom_body() builds
# in the tests (id/option/address/box/reference/contents/declared), invented addresses.
OPS_CUSTOM = [
    ("csops000001", "Replacement gobo", "Glass gobo",
     {"name": "Ruth Calder", "company": "Elmstead Community Hall", "street": "2 Chapel Walk", "street2": "",
      "city": "Ripon", "state": "", "postcode": "HG4 9ZZ", "country": "GB", "phone": "01632 960210",
      "email": "ruth.calder@example.org"}),
    ("csops000002", "Loan projector return label", "LED gobo projector",
     {"name": "Dev Patel", "company": "Brightwater Studios", "street": "Unit 3, Tannery Yard", "street2": "",
      "city": "Sheffield", "state": "", "postcode": "S1 9ZZ", "country": "GB", "phone": "01632 960211",
      "email": "dev@brightwater.example.com"}),
    ("csops000003", "Sample pack", "Gobo samples",
     {"name": "Alice Moreton", "company": "", "street": "17 Windmill Hill", "street2": "",
      "city": "Lincoln", "state": "", "postcode": "LN1 9ZZ", "country": "GB", "phone": "01632 960212",
      "email": "alice.moreton@example.com"}),
]
for _sid, _ref, _what, _addr in OPS_CUSTOM:
    _r = _ok200(post("/api/custom/book", {"id": _sid, "option": OPT, "address": _addr, "box": dict(BOX),
                                          "reference": _ref, "contents": _what, "declared": 85}),
                "custom book " + _sid)
    if _sid == "csops000003":   # one cancelled, as t_cancelling_a_custom_shipment... does it
        _ok200(post("/api/dispatch/cancel", {"id": _r["id"], "tracking_number": _r["dispatch"]["tracking_number"]}),
               "cancel " + _sid)

# ============================ LOAN UNITS =====================================
# (a) POST /api/loans unit_save / sticker / out / back, payloads as
# t_a_loan_unit_goes_out_once_and_comes_back; then (b) _load_loans/_write_loans
# back-dates out_at exactly as t_a_loan_is_late_by_its_date_and_only_amber... does.
OPS_UNITS = {}
for _n, _model, _serial, _notes in (
        ("Loan 1", "40W LED Gobo Projector", "LP40-2291", "Rain hood in the case."),
        ("Loan 2", "40W LED Gobo Projector", "LP40-2307", ""),
        ("Loan 3", "80W LED Outdoor Gobo Projector", "LP80-1184", "Spare lens in the side pocket."),
        ("Loan 4", "80W LED Outdoor Gobo Projector", "LP80-1190", ""),
        ("Loan 5", "Rotating Gobo Projector 150W", "RG150-0412", "Needs a 13A socket within 3 m."),
        ("Loan 6", "Battery Gobo Projector 20W", "BG20-0077", "Charger and two spare batteries.")):
    OPS_UNITS[_n] = _ok200(post("/api/loans", {"op": "unit_save", "name": _n, "model": _model,
                                               "serial": _serial, "notes": _notes}), "unit " + _n)["unit"]["id"]
for _n in ("Loan 1", "Loan 2", "Loan 3", "Loan 5"):
    _ok200(post("/api/loans", {"op": "sticker", "unit_id": OPS_UNITS[_n]}), "sticker " + _n)
# A loan that went out and came back (History has something in it).
_l = _ok200(post("/api/loans", {"op": "out", "unit_id": OPS_UNITS["Loan 4"], "who_name": "Saltmarsh Brewing Co",
                                "crm_org_id": OPS_ORGS["Saltmarsh Brewing Co"], "phone": "01632 960303",
                                "due_at": _day(-20), "note": "Beer festival weekend."}), "loan out 4")["loan"]
_ok200(post("/api/loans", {"op": "back", "loan_id": _l["id"], "note": "Back clean, lens fine."}), "loan back 4")
_OUT = {}
for _n, _who, _org, _person, _due, _note in (
        ("Loan 1", "Hartwell Events Ltd", "Hartwell Events Ltd", "Marcus Bell", _day(10), "Autumn tour test rig."),
        ("Loan 3", "Quayside Exhibitions", "Quayside Exhibitions", "Arjun Mehta", _day(-4), "Trade show trial."),
        ("Loan 5", "Isaac Thorne", "", "Isaac Thorne", "", "Open-ended: rental trial."),
        ("Loan 6", "Copperbeck Hotels", "Copperbeck Hotels", "Sophie Varga", _day(3), "Wedding fair.")):
    _OUT[_n] = _ok200(post("/api/loans", {"op": "out", "unit_id": OPS_UNITS[_n], "who_name": _who,
                                          "crm_org_id": OPS_ORGS.get(_org, ""), "crm_person_id": OPS_PEOPLE.get(_person, ""),
                                          "phone": "01632 9604" + str(len(_OUT)).zfill(2), "due_at": _due,
                                          "note": _note}), "loan out " + _n)["loan"]["id"]
_ld = copilot._load_loans()
for _n, _days in (("Loan 1", 6), ("Loan 3", 19), ("Loan 5", 41), ("Loan 6", 2)):
    _ld["loans"][_OUT[_n]]["out_at"] = _at(_days, hour=11).isoformat()
for _lo in _ld["loans"].values():
    if _lo.get("back_at"):
        _lo["out_at"] = _at(35, hour=9).isoformat()
        _lo["back_at"] = _at(27, hour=16).isoformat()
copilot._write_loans(_ld)
# Loan 2 stays on the shelf; Loan 4 is back on the shelf with history.

# ============================ INBOX (Gmail stand-in, c) ======================
# Google's token door and the Gmail REST API answered in-process at the
# transport (the same _RoutedHttpx seam the prelude uses to refuse Google), so
# the app's real google_mail client and its real sync build the board.
# Anything it does not know (send, drafts) is refused, so nothing can send.
OPS_MAILBOX = "sales@example.com"
_GM = {"threads": {}, "labels": {"Label_1": "Reactor/Owned"}}
def _gm_msg(tid, mid, frm, to, subject, when, text, unread=False, files=()):
    name, addr = frm
    body = _b64.urlsafe_b64encode(text.encode()).decode().rstrip("=")
    parts = [{"partId": "0", "mimeType": "text/plain", "filename": "", "headers": [],
              "body": {"size": len(text), "data": body}}]
    for i, (fname, mime, size) in enumerate(files):
        parts.append({"partId": str(i + 1), "mimeType": mime, "filename": fname,
                      "headers": [{"name": "Content-Disposition", "value": 'attachment; filename="%s"' % fname}],
                      "body": {"size": size, "attachmentId": "att-%s-%d" % (mid, i)}})
    return {"id": mid, "threadId": tid, "labelIds": ["INBOX"] + (["UNREAD"] if unread else []),
            "snippet": text[:120], "internalDate": str(int(when.timestamp() * 1000)),
            "payload": {"mimeType": "multipart/mixed", "filename": "",
                        "headers": [{"name": "From", "value": "%s <%s>" % (name, addr) if name else addr},
                                    {"name": "To", "value": to}, {"name": "Subject", "value": subject},
                                    {"name": "Date", "value": _eut.format_datetime(when)}],
                        "parts": parts}}
_US = ("Lumenfield Sales", OPS_MAILBOX)
OPS_THREADS = [  # (thread id, subject, [(from, hours ago, text, files)], unread)
    ("19a0c1d2e3f40001", "Artwork for the autumn tour gobos",
     [(("Marcus Bell", "marcus@hartwell-events.example.com"), 30, "Hi, attached are the four logos for the tour. Can we have proofs by Friday?", (("hartwell-tour-logos.pdf", "application/pdf", 482113),)),
      (_US, 28, "Thanks Marcus, proofs to follow tomorrow.", ()),
      (("Marcus Bell", "marcus@hartwell-events.example.com"), 3, "Proofs look great, one small change on logo 3.", ())], True),
    ("19a0c1d2e3f40002", "Quote request: window projection for panto",
     [(("Callum Reid", "callum@northgate-playhouse.example.org"), 50, "Could you quote for two outdoor projectors and a snowflake gobo set?", ())], False),
    ("19a0c1d2e3f40003", "Where is my order #210399?",
     [(("Leo Fenwick", "leo@fernhill-academy.example.org"), 6, "Hello, just checking when our order will ship, we need it for open day.", ())], True),
    ("19a0c1d2e3f40004", "Wedding monogram: date change",
     [(("Imogen Shaw", "imogen.shaw@example.com"), 9, "Our wedding has moved forward a week, is that still okay for the gobo?", ())], True),
    ("19a0c1d2e3f40005", "Loan projector return",
     [(("Arjun Mehta", "arjun@quayside-expo.example.com"), 70, "The loan unit is packed, can you send a return label?", ()),
      (_US, 66, "Label on its way, thank you Arjun.", ())], False),
    ("19a0c1d2e3f40006", "Invoice copy please",
     [(("Accounts Team", "accounts@brindlewood.example.com"), 2, "Please send a copy of invoice for order #210351.", ())], True),
    ("19a0c1d2e3f40007", "Forklift zone projector demo",
     [(("Ben Hollis", "ben.hollis@brindlewood.example.com"), 120, "Can you bring a demo unit to our Doncaster depot?", ()),
      (_US, 118, "Booked in for next week.", ()),
      (("Ben Hollis", "ben.hollis@brindlewood.example.com"), 20, "Great, see you then. Gate 4.", ())], False),
    ("19a0c1d2e3f40008", "Gobo size for an older fixture",
     [(("Isaac Thorne", "isaac.thorne@example.org"), 4, "Which size gobo fits a Moonbeam Profile 300? It is not on your list.", ())], True),
    ("19a0c1d2e3f40009", "Thanks for the quick turnaround",
     [(("Nadia Kerr", "nadia.kerr@example.org"), 100, "Gobo arrived today and looks perfect, thank you!", ())], False),
    ("19a0c1d2e3f40010", "Taproom logo artwork",
     [(("Tom Ashby", "tom@saltmarsh-brewing.example.com"), 14, "Here is the vector logo, white on black.", (("saltmarsh-logo.svg", "image/svg+xml", 23110),))], True),
]
for _tid, _subject, _msgs, _unread in OPS_THREADS:
    _raw = []
    for _i, (_frm, _h, _text, _files) in enumerate(_msgs):
        _to = OPS_MAILBOX if _frm != _US else _msgs[0][0][1]
        _raw.append(_gm_msg(_tid, "%s-m%d" % (_tid, _i), _frm, _to, _subject, _at(hours_ago=_h), _text,
                            unread=_unread and _i == len(_msgs) - 1 and _frm != _US, files=_files))
    _GM["threads"][_tid] = {"historyId": "8800" + _tid[-2:], "messages": _raw, "unread": _unread}

_OPS_GM_PREV = _gmail.httpx
def _ops_gmail(request):
    host, path, method = request.url.host, request.url.path, request.method
    if host == "oauth2.googleapis.com" and path == "/token":
        return _hx.Response(200, json={"access_token": "ops-seed-access", "expires_in": 3600, "token_type": "Bearer"})
    base = "/gmail/v1/users/me/"
    if host == "gmail.googleapis.com" and path.startswith(base):
        sub = path[len(base):]
        if method == "GET" and sub == "threads":
            q = request.url.params.get("q", "")
            rows = [(tid, t) for tid, t in _GM["threads"].items() if "is:unread" not in q or t["unread"]]
            return _hx.Response(200, json={"threads": [{"id": tid, "snippet": t["messages"][-1]["snippet"],
                                                        "historyId": t["historyId"]} for tid, t in rows],
                                           "resultSizeEstimate": len(rows)})
        m = _re.fullmatch(r"threads/([^/]+)", sub)
        if method == "GET" and m and m.group(1) in _GM["threads"]:
            t = _GM["threads"][m.group(1)]
            return _hx.Response(200, json={"id": m.group(1), "historyId": t["historyId"], "messages": t["messages"]})
        if method == "GET" and sub == "labels":
            return _hx.Response(200, json={"labels": [{"id": k, "name": v} for k, v in _GM["labels"].items()]})
        if method == "POST" and sub == "labels":
            lid = "Label_%d" % (len(_GM["labels"]) + 1)
            _GM["labels"][lid] = json.loads(request.content)["name"]
            return _hx.Response(200, json={"id": lid, "name": _GM["labels"][lid]})
        if method == "POST" and _re.fullmatch(r"threads/[^/]+/modify", sub):
            return _hx.Response(200, json={})
    raise _hx.ConnectError("the operations seed's Gmail stand-in does not answer " + method + " " + host + path,
                           request=request)
_gmail.httpx = _RoutedHttpx(_ops_gmail)
_gmail._pool_drop()
_gmail.save_connection("rt-ops-seed", OPS_MAILBOX)
mail._mail_mem = None
# The real sync (a), through the board route's Refresh, exactly as
# t_mail_sync_pipeline_and_history_short_circuit drives it.
_board = _ok200(post("/api/mail/board", {"force": True}), "mail sync")
if len(_board.get("threads") or []) != len(OPS_THREADS):
    raise RuntimeError("mail sync brought %d threads, expected %d: %s" % (
        len(_board.get("threads") or []), len(OPS_THREADS), _board.get("sync_error")))
# Owners, states and notes (a): /api/mail/assign, /api/mail/state, /api/mail/note
# with the payloads of t_mail_claim_is_first_come_single_owner and t_mail_state_moves_are_owner_or_lead_only.
for _tid, _owner, _state, _note in (
        ("19a0c1d2e3f40001", "priya", "progress", "Proof v2 going out today."),
        ("19a0c1d2e3f40002", "owen", "assigned", ""),
        ("19a0c1d2e3f40005", "grace", "waiting", "Return label sent, waiting for collection."),
        ("19a0c1d2e3f40007", "priya", "progress", "Demo booked for next Tuesday."),
        ("19a0c1d2e3f40009", "grace", "done", ""),
        ("19a0c1d2e3f40010", "owen", "assigned", "")):
    _ok200(post("/api/mail/assign", {"id": _tid, "uid": OPS_TEAM[_owner]}), "assign " + _tid)
    if _state != "assigned":
        _ok200(post("/api/mail/state", {"id": _tid, "state": _state}), "state " + _tid)
    if _note:
        _ok200(post("/api/mail/note", {"id": _tid, "text": _note}), "note " + _tid)

# Who is on today: the master's presence through its route (a), payload as
# t_mail_notes_presence_and_team_panel; the colleagues' through the users
# store's writer (b), since the route only sets the caller's own.
_ok200(post("/api/mail/presence", {"presence": "office"}), "presence")
_ud = team._load_users()
for _uname, _p in (("priya", "office"), ("owen", "home"), ("grace", "out")):
    _ud["users"][OPS_TEAM[_uname]]["presence"] = _p
team._write_users(_ud)

# ============================ FILES (R2 stand-in, c) =========================
# The bucket is the in-process FakeS3 the tests use (copied from
# tests/test_dispatch.py, class FakeS3), configured the way with_files() does;
# folders and files are then made through the real routes (a): /api/files/folder
# op add, /api/files/upload-url + the object landing + /api/files/complete, and
# /api/files/file op trash (t_files_upload_flow..., t_files_trash_restore...).
class OpsFakeS3:
    def __init__(self):
        self.objects, self.cors, self.bucket_exists = {}, None, False
    def head_bucket(self, Bucket):
        if not self.bucket_exists:
            raise RuntimeError("404 no bucket")
    def create_bucket(self, Bucket):
        self.bucket_exists = True
    def put_bucket_cors(self, Bucket, CORSConfiguration):
        self.cors = CORSConfiguration
    def generate_presigned_url(self, op, Params, ExpiresIn):
        return "https://fake-r2.test/%s?op=%s&exp=%s" % (Params["Key"], op, ExpiresIn)
    def _size(self, Key):
        v = self.objects[Key]
        return len(v) if isinstance(v, (bytes, bytearray)) else int(v)
    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise RuntimeError("404 no object")
        return {"ContentLength": self._size(Key)}
    def get_object(self, Bucket, Key, Range=None):
        import io
        if Key not in self.objects:
            raise KeyError(Key)
        v = self.objects[Key]
        if isinstance(v, (bytes, bytearray)):
            data = bytes(v)
        else:
            ext = Key.rsplit(".", 1)[-1].lower() if "." in Key else ""
            magic = {"pdf": b"%PDF-1.4\n", "png": b"\x89PNG\r\n\x1a\n", "jpg": b"\xff\xd8\xff\xe0",
                     "jpeg": b"\xff\xd8\xff\xe0", "gif": b"GIF89a", "webp": b"RIFF\x00\x00\x00\x00WEBP"}.get(ext, b"")
            data = (magic + b"x" * int(v))[:max(int(v), len(magic))]
        if Range:
            a, b = _re.match(r"bytes=(\d+)-(\d+)", Range).groups()
            data = data[int(a):int(b) + 1]
        return {"Body": io.BytesIO(data), "ContentLength": len(data)}
    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)
    def delete_objects(self, Bucket, Delete):
        for o in (Delete or {}).get("Objects") or []:
            self.objects.pop(o.get("Key"), None)
        return {}
    def upload_fileobj(self, Fileobj, Bucket, Key):
        self.objects[Key] = len(Fileobj.read())
OPS_S3 = OpsFakeS3()
fileserver.R2_ACCOUNT_ID, fileserver.R2_ACCESS_KEY_ID, fileserver.R2_SECRET_ACCESS_KEY = "acct", "ak", "sk"
fileserver._files_s3_client = OPS_S3
fileserver._files_ready.update({"bucket": False, "cors": False, "error": ""})
fileserver._files_mem = None
OPS_FOLDERS = {}
def _folder(name, parent=""):
    r = post("/api/files/folder", {"op": "add", "name": name, "parent_id": OPS_FOLDERS.get(parent, "")})
    OPS_FOLDERS[name] = _ok200(r, "folder " + name)["id"]
for _f, _p in (("Artwork", ""), ("Customer proofs", "Artwork"), ("Stock gobos", "Artwork"),
               ("Product photos", ""), ("Invoices", ""), ("Templates", ""), ("2026", "Invoices")):
    _folder(_f, _p)
OPS_FILES = {}
def _file(name, size, mime, folder=""):
    up = _ok200(post("/api/files/upload-url", {"name": name, "size": size, "type": mime,
                                               "folder_id": OPS_FOLDERS.get(folder, "")}), "upload-url " + name)
    OPS_S3.objects[up["url"].split("?")[0].replace("https://fake-r2.test/", "")] = size
    _ok200(post("/api/files/complete", {"id": up["id"]}), "complete " + name)
    OPS_FILES[name] = up["id"]
for _n, _s, _m, _f in (
        ("hartwell-tour-proof-v2.pdf", 482113, "application/pdf", "Customer proofs"),
        ("northgate-snowflake-proof.pdf", 221904, "application/pdf", "Customer proofs"),
        ("saltmarsh-logo-mono.png", 88231, "image/png", "Customer proofs"),
        ("stars-b-size.png", 40210, "image/png", "Stock gobos"),
        ("leaf-breakup-b-size.png", 51877, "image/png", "Stock gobos"),
        ("LED-40W-front.jpg", 1204551, "image/jpeg", "Product photos"),
        ("LED-80W-outdoor.jpg", 1688020, "image/jpeg", "Product photos"),
        ("rotating-150W-side.jpg", 990112, "image/jpeg", "Product photos"),
        ("INV-210351.pdf", 61220, "application/pdf", "2026"),
        ("INV-210356.pdf", 60118, "application/pdf", "2026"),
        ("gobo-artwork-template.pdf", 152330, "application/pdf", "Templates"),
        ("wedding-monogram-template.pdf", 143002, "application/pdf", "Templates"),
        ("price-list-2026.pdf", 210004, "application/pdf", ""),
        ("old-price-list-2025.pdf", 208870, "application/pdf", "")):
    _file(_n, _s, _m, _f)
_ok200(post("/api/files/file", {"op": "trash", "id": OPS_FILES["old-price-list-2025.pdf"]}), "trash old price list")
# Who uploaded what, and when (b): the files store's own writer, so the Owner
# and Modified columns are not all one person on one day.
_fd = fileserver._load_files()
_owners = [OPS_MASTER, OPS_TEAM["priya"], OPS_TEAM["owen"], OPS_TEAM["grace"]]
for _i, (_n, _fid) in enumerate(sorted(OPS_FILES.items())):
    _rec = _fd["files"][_fid]
    _when = _at(2 + (_i * 11) % 60, hour=9 + _i % 8).isoformat()
    _rec["by"] = _owners[_i % len(_owners)]
    _rec["created_at"] = _rec["uploaded_at"] = _when
for _i, _fid in enumerate(OPS_FOLDERS.values()):
    _fd["folders"][_fid]["created_at"] = _at(70 + _i * 5, hour=10).isoformat()
fileserver._write_files(_fd)

print("operations seed: %d orders, %d custom shipments, %d deals, %d units, %d threads, %d files"
      % (len(OPS_ORDERS), len(OPS_CUSTOM), len(OPS_DEALS) + len(_HIST), len(OPS_UNITS),
         len(OPS_THREADS), len(OPS_FILES)), flush=True)
