import os, sys, json, time, asyncio, glob, re, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import xml.etree.ElementTree as ET
SCRATCH = tempfile.mkdtemp(prefix="gizmo-dispatch-tests-")
os.makedirs(SCRATCH, exist_ok=True)
for f in glob.glob(SCRATCH + "/*"):
    (os.remove(f) if os.path.isfile(f) else None)
for d in glob.glob(SCRATCH + "/*/*"):
    os.remove(d)
SECRET = "testsecret-long-enough-for-hmac-please-32b"
os.environ.update({
    "SHOPIFY_STORE": "test-store", "SHOPIFY_ACCESS_TOKEN": "shpat_x", "ANTHROPIC_API_KEY": "x",
    "SHOPIFY_API_SECRET": SECRET,
    "SHIPPING_PATH": SCRATCH + "/shipping.json",
    "WO_SECRET_PATH": SCRATCH + "/wo_secret.json",
    "DISPATCH_STATE_PATH": SCRATCH + "/dispatch_state.json",
    "WO_FAILURES_PATH": SCRATCH + "/wo_failures.json",
    "DISPATCH_LABELS_DIR": SCRATCH + "/labels",
    "PRODUCTION_STATE_PATH": SCRATCH + "/production_state.json",
    "SCHEDULE_PATH": SCRATCH + "/schedule.json",
    "WATCH_PATH": SCRATCH + "/watch.json", "ALERTS_PATH": SCRATCH + "/alerts.json",
    "USAGE_PATH": SCRATCH + "/usage.json", "IMPACT_PATH": SCRATCH + "/impact.json",
    "ANALYSIS_CACHE_PATH": SCRATCH + "/analysis.json",
})
for v in ("WO_METER_NUMBER", "WO_KEY", "WO_PASSWORD"):
    os.environ.pop(v, None)

import jwt
import server, copilot, worldoptions
REAL_SOAP_CALL = worldoptions._soap_call
from starlette.testclient import TestClient

TESTS = []
def test(fn): TESTS.append(fn); return fn
def eq(a, b, msg=""):
    if a != b: raise AssertionError(f"{msg}: {a!r} != {b!r}")
def ok(c, msg=""):
    if not c: raise AssertionError(f"FAIL: {msg}")
def tok():
    now = int(time.time())
    return jwt.encode({"iss": "https://test-store.myshopify.com/admin",
                       "dest": "https://test-store.myshopify.com", "aud": "a",
                       "exp": now + 120, "nbf": now - 5}, SECRET, algorithm="HS256")
def run(coro): return asyncio.get_event_loop().run_until_complete(coro)

# ---- Fake Shopify order + shop ---------------------------------------------
ORDER = {
    "id": 12345, "order_number": 104239, "name": "#104239", "created_at": "2026-08-01T10:00:00Z",
    "email": "buyer@acme.co.uk", "currency": "GBP", "financial_status": "paid",
    "fulfillment_status": None, "cancelled_at": None, "tags": "IP, PC",
    "customer": {"id": 7, "first_name": "Joe", "last_name": "Doe"},
    "shipping_address": {"name": "Joe Doe", "company": "Acme Events Ltd", "address1": "24 Liberty Ave",
                          "address2": "Unit 3", "city": "Manchester", "province_code": "",
                          "zip": "M1 2AB", "country_code": "GB", "phone": "0161 555 0000"},
    "line_items": [{"title": "Custom Gobo", "quantity": 2, "grams": 250, "product_id": 1, "variant_title": ""}],
}
SHOP = {"name": "Projected Image", "address1": "1 Mill St", "city": "Leeds", "zip": "LS1 1AA",
        "country_code": "GB", "phone": "0113 555 1111", "email": "shop@projectedimage.com", "currency": "GBP"}
async def fake_tool_json(registry, name, args):
    if name == "shopify_get_order": return dict(ORDER)
    if name == "shopify_get_shop": return dict(SHOP)
    if name == "shopify_list_orders": return {"orders": []}
    return {}
copilot._tool_json = fake_tool_json

TAG_WRITES = []
async def fake_tag_writer(order_id, tags):
    TAG_WRITES.append((int(order_id), tags)); return {"order": {"id": order_id, "tags": tags}}
FULFILLED = []
async def fake_fulfillment(order_id, tracking_number=None, tracking_company=None, tracking_url=None, notify_customer=True):
    FULFILLED.append({"order_id": order_id, "tracking": tracking_number, "company": tracking_company, "notify": notify_customer})
    return {"ok": True, "fulfillment_id": 555, "status": "success"}
copilot._order_tag_writer = fake_tag_writer
copilot._fulfillment_writer = fake_fulfillment
CANCELED_FULFILLMENTS = []
async def fake_canceler(fulfillment_id):
    CANCELED_FULFILLMENTS.append(int(fulfillment_id)); return {"ok": True}
copilot._fulfillment_canceler = fake_canceler
def reset_dispatch():
    json.dump({"orders": {}}, open(SCRATCH + "/dispatch_state.json", "w"))
    # The failure store accumulates across tests otherwise.
    try:
        os.remove(SCRATCH + "/wo_failures.json")
    except FileNotFoundError:
        pass
def reset_prod():
    json.dump({"orders": {}}, open(SCRATCH + "/production_state.json", "w"))
def mark_made(oid=12345, on=True):
    return post("/api/production-state", {"op": "made", "id": oid, "on": on})
BOX = {"width": 20, "length": 15, "depth": 8, "weight": 0.6}
OPT = {"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging",
       "carrier_name": "UPS", "service_name": "UPS Express", "amount": 12.40, "currency": "GBP"}

# ---- Fake SOAP layer (mock _soap_call, return parsed sample replies) --------
RATE_XML = """<Envelope><Body><GetAllServicesAndRatesResponse>
<GetAllServicesAndRatesResult><Message/><NotificationtType>SUCCESS</NotificationtType><wsRateService>
 <wsAvailableServicesAndRates>
   <wsPackageTypeCode>RoyalMail_Parcel</wsPackageTypeCode><wsServiceCode>ROYALMAIL</wsServiceCode>
   <wsServiceTypeCode>RoyalMail_Tracked_24_Hours</wsServiceTypeCode><wsServiceTypeName>03 Royal Mail Tracked 24</wsServiceTypeName>
   <wsDeliveryDateTime>Wed, 12 Aug 2026&lt;br/&gt;End of business day</wsDeliveryDateTime><wsPickupDateTime>Tue, 11 Aug 2026&lt;br/&gt;15:00 PM</wsPickupDateTime>
   <wsQuoteDetails><BaseCharge>3.80</BaseCharge><FuelSurcharge>0.90</FuelSurcharge><VATCharge>0.50</VATCharge><TotalNetCharge>5.20</TotalNetCharge><ServiceType>ROYALMAIL</ServiceType></wsQuoteDetails>
   <wsCollectionDropOffShops><wsDropOffShop><Description>Post Office Central</Description><Street>High St</Street><HouseNo>12</HouseNo><City>Leeds</City><PostCode>LS1 2AB</PostCode><Distance>0.4</Distance><DistanceUnit>mi</DistanceUnit><ParcelShopNumber>PO123</ParcelShopNumber></wsDropOffShop></wsCollectionDropOffShops>
 </wsAvailableServicesAndRates>
 <wsAvailableServicesAndRates>
   <wsPackageTypeCode>DHL_NonDocument</wsPackageTypeCode><wsServiceCode>DHL</wsServiceCode>
   <wsServiceTypeCode>DHL_DOMESTIC_EXPRESS</wsServiceTypeCode><wsServiceTypeName>03 DHL Domestic Express</wsServiceTypeName>
   <wsDeliveryDateTime>Wed, 12 Aug 2026&lt;br/&gt;End of business day</wsDeliveryDateTime>
   <wsQuoteDetails><TotalNetCharge>9.94</TotalNetCharge><VATCharge>1.66</VATCharge><ServiceType>DHL</ServiceType></wsQuoteDetails>
 </wsAvailableServicesAndRates>
 <wsAvailableServicesAndRates>
   <wsPackageTypeCode>UPS_My_Packaging</wsPackageTypeCode><wsServiceCode>UPS</wsServiceCode>
   <wsServiceTypeCode>UPS_Express</wsServiceTypeCode><wsServiceTypeName>UPS Express</wsServiceTypeName>
   <wsDeliveryDateTime>By 12:00</wsDeliveryDateTime>
   <wsQuoteDetails><TotalNetCharge>12.40</TotalNetCharge><ServiceType>UPS</ServiceType></wsQuoteDetails>
 </wsAvailableServicesAndRates>
</wsRateService></GetAllServicesAndRatesResult></GetAllServicesAndRatesResponse></Body></Envelope>"""
BOOK_XML = """<Envelope><Body><DoShipmentResponse><DoShipmentResult>
 <CollectionDateNumber>CDN123</CollectionDateNumber>
 <Labels>
   <ShippingLabel><Image>JVBERi0xLjQK</Image><ImageLength>10</ImageLength><IsThermalPrint>false</IsThermalPrint><LabelType>PDF</LabelType><LabelURL/></ShippingLabel>
 </Labels>
 <MasterTrackingNo>WO1234567890</MasterTrackingNo><Message>Booked</Message>
 <NotificationtType>SUCCESS</NotificationtType><Warning/>
</DoShipmentResult></DoShipmentResponse></Body></Envelope>"""
VOID_XML = """<Envelope><Body><VoidShipmentResponse><VoidShipmentResult>
 <Message>Cancelled</Message><NotificationtType>SUCCESS</NotificationtType>
</VoidShipmentResult></VoidShipmentResponse></Body></Envelope>"""
FAIL_XML = """<Envelope><Body><GetAllServicesAndRatesResponse><GetAllServicesAndRatesResult>
 <Message>invalid_client</Message><NotificationtType>FAILED</NotificationtType>
</GetAllServicesAndRatesResult></GetAllServicesAndRatesResponse></Body></Envelope>"""

AP_XML = """<Envelope><Body><GetAllServicesAndRatesResponse>
<GetAllServicesAndRatesResult><Message/><NotificationtType>SUCCESS</NotificationtType><wsRateService>
 <wsAvailableServicesAndRates>
   <wsPackageTypeCode>UPS_My_Packaging</wsPackageTypeCode><wsServiceCode>65AP</wsServiceCode>
   <wsServiceTypeCode>UPS_Express_Saver_AP</wsServiceTypeCode><wsServiceTypeName>65 Express Saver Access Point</wsServiceTypeName>
   <wsDeliveryDateTime>Wed, 12 Aug 2026&lt;br/&gt;End of business day</wsDeliveryDateTime>
   <wsQuoteDetails><BaseCharge>6.20</BaseCharge><VATCharge>1.24</VATCharge><TotalNetCharge>7.44</TotalNetCharge></wsQuoteDetails>
   <wsDeliveryDropOffShops><wsDropOffShop><Description>Corner Shop</Description><HouseNo>7</HouseNo><Street>Market St</Street><City>Manchester</City><PostCode>M1 3AA</PostCode><ParcelShopNumber>UPS991</ParcelShopNumber></wsDropOffShop></wsDeliveryDropOffShops>
 </wsAvailableServicesAndRates>
 <wsAvailableServicesAndRates>
   <wsPackageTypeCode>UPS_My_Packaging</wsPackageTypeCode><wsServiceCode>65</wsServiceCode>
   <wsServiceTypeCode>UPS_Express_Saver</wsServiceTypeCode><wsServiceTypeName>65 Express Saver</wsServiceTypeName>
   <wsDeliveryDateTime>Wed, 12 Aug 2026&lt;br/&gt;12:00</wsDeliveryDateTime>
   <wsQuoteDetails><TotalNetCharge>10.49</TotalNetCharge></wsQuoteDetails>
 </wsAvailableServicesAndRates>
</wsRateService></GetAllServicesAndRatesResult></GetAllServicesAndRatesResponse></Body></Envelope>"""

NOSIG_XML = RATE_XML.replace("<TotalNetCharge>9.94</TotalNetCharge>",
                             "<TotalNetCharge>9.10</TotalNetCharge>")

SOAP_MODE = {"fail": False, "calls": []}
async def fake_soap_call(service, action, inner, retryable=True):
    SOAP_MODE["calls"].append((service, inner))
    if SOAP_MODE["fail"]:
        return ET.fromstring(FAIL_XML)
    if service == "RateService":
        if "IsDeliveryDropoffRequired" in inner:
            return ET.fromstring(AP_XML)
        if "No_Signature_Required" in inner:
            return ET.fromstring(NOSIG_XML)
        return ET.fromstring(RATE_XML)
    if service == "ShipmentService": return ET.fromstring(BOOK_XML)
    if service == "VoidService": return ET.fromstring(VOID_XML)
    return ET.fromstring("<Envelope><Body/></Envelope>")
worldoptions._soap_call = fake_soap_call

client = TestClient(server.mcp.streamable_http_app())
def post(path, body):
    copilot._rl_hits.clear(); copilot._rl_global.clear()   # the suite outpaces the app's rate limiter
    return client.post(path, json=body, headers={"Authorization": "Bearer " + tok()})

# =========================== unit: envelope construction ====================
@test
def t_envelope_wellformed_and_ordered():
    worldoptions.set_credentials(meter="M1", key="K1", password="P1", plugin="Web_Service")
    # capture the real envelope by temporarily using the real builder path
    inner_holder = {}
    async def capture(service, action, inner, retryable=True):
        inner_holder["xml"] = worldoptions._envelope(inner)
        return ET.fromstring(RATE_XML)
    saved = worldoptions._soap_call
    worldoptions._soap_call = capture
    try:
        run(worldoptions.quote({"city": "Leeds", "postcode": "LS1 1AA", "country": "gb"},
                               {"city": "Manchester", "postcode": "M1 2AB", "country": "gb"},
                               [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}]))
    finally:
        worldoptions._soap_call = saved
    xml = inner_holder["xml"]
    ET.fromstring(xml)   # must be well-formed
    ok("<m:MeterNumber>M1</m:MeterNumber>" in xml, "meter in auth")
    ok("<m:Key>K1</m:Key>" in xml, "key in auth")
    ok("GB" in xml, "country upper-cased")
    ok(xml.index("<m:Key>") < xml.index("<m:MeterNumber>") < xml.index("<m:Password>"), "auth alphabetical")
    ok("<rs:Weight>0.6</rs:Weight>" in xml, "quote uses Weight")

@test
def t_quote_normalize():
    worldoptions.set_credentials(meter="M1")
    res = run(worldoptions.quote({"postcode": "LS1 1AA", "country": "GB"},
                                 {"postcode": "M1 2AB", "country": "GB"},
                                 [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}]))
    eq(len(res["options"]), 3, "three options")
    eq(res["options"][0]["amount"], 5.20, "cheapest first (RoyalMail)")
    eq(res["options"][0]["service_type_code"], "RoyalMail_Tracked_24_Hours", "service code")
    eq(res["options"][0]["package_type_code"], "RoyalMail_Parcel", "package code carried for booking")
    eq(res["options"][0]["carrier_name"], "ROYALMAIL", "carrier")
    eq(res["options"][1]["amount"], 9.94, "DHL next")
    eq(res["options"][1]["carrier_name"], "DHL", "carrier")
    eq(res["options"][2]["amount"], 12.40, "UPS dearest")

@test
def t_quote_failed_reply_raises():
    worldoptions.set_credentials(meter="M1")
    SOAP_MODE["fail"] = True
    try:
        run(worldoptions.quote({"postcode": "x", "country": "GB"}, {"postcode": "y", "country": "GB"},
                               [{"width": 1, "length": 1, "depth": 1, "weight": 1}]))
        ok(False, "should have raised")
    except worldoptions.WorldOptionsError as e:
        ok("invalid_client" in str(e) or "Key and Password" in str(e), "carries WO message (raw or translated)")
    finally:
        SOAP_MODE["fail"] = False

@test
def t_book_normalize():
    worldoptions.set_credentials(meter="M1")
    opt = {"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging",
           "carrier_name": "UPS", "service_name": "UPS Express", "amount": 12.40}
    s = run(worldoptions.book(opt, {"postcode": "LS1 1AA", "country": "GB", "company": "PI"},
                              {"postcode": "M1 2AB", "country": "GB", "company": "Acme"},
                              [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}], reference="#104239"))
    eq(s["tracking_number"], "WO1234567890", "tracking")
    eq(s["labels"][0]["type"], "base64pdf", "base64 pdf label")
    eq(s["carrier_name"], "UPS", "carrier")

@test
def t_book_envelope_uses_Wt():
    worldoptions.set_credentials(meter="M1")
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner; return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        run(worldoptions.book({"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
                              {"postcode": "LS1 1AA", "country": "GB"}, {"postcode": "M1 2AB", "country": "GB"},
                              [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}]))
    finally:
        worldoptions._soap_call = saved
    ok("<sd:Wt>0.6</sd:Wt>" in holder["xml"], "booking uses Wt not Weight")
    ok("<sd:ServiceTypeCode>UPS_Express</sd:ServiceTypeCode>" in holder["xml"], "service code sent")
    ok("<sd:ServiceType>UPS</sd:ServiceType>" in holder["xml"], "carrier sent")

@test
def t_cancel():
    worldoptions.set_credentials(meter="M1")
    r = run(worldoptions.cancel("WO1234567890"))
    eq(r["canceled"], True, "canceled")

@test
def t_validate():
    worldoptions.set_credentials(meter="M1")
    r = run(worldoptions.validate())
    eq(r["ok"], True, "validate ok")

# =========================== routes: config =================================
@test
def t_config_creds_write_only():
    r = post("/api/shipping/config", {"op": "set", "meter_number": "METER-9999", "key": "KEY-abc", "password": "PW-xyz",
                                      "origin": {"street": "1 Mill St", "postcode": "LS1 1AA", "country": "GB", "city": "Leeds", "company": "PI"}})
    eq(r.status_code, 200, r.text)
    body = r.json()
    dump = json.dumps(body)
    ok("METER-9999" not in dump and "KEY-abc" not in dump and "PW-xyz" not in dump, "no creds echoed")
    eq(body["config"]["connected"], True, "connected")
    eq(body["config"]["meter_last4"], "9999", "meter last4")
    eq(body["config"]["has_key"], True, "has key flag")
    eq(body["config"]["has_password"], True, "has password flag")
    disk = json.load(open(SCRATCH + "/wo_secret.json"))
    eq(disk["meter"], "METER-9999", "meter persisted")
    eq(disk["key"], "KEY-abc", "key persisted")

@test
def t_config_get_no_secrets():
    r = post("/api/shipping/config", {"op": "get"})
    body = r.json()["config"]
    ok("key" not in body and "password" not in body and "meter" not in body, "no raw secrets")
    eq(body["origin"]["city"], "Leeds", "origin persisted")
    eq(body["plugin_code"], "Web_Service", "default plugin")

@test
def t_validate_route():
    r = post("/api/shipping/validate", {})
    eq(r.status_code, 200, r.text)
    eq(r.json()["ok"], True, "validates via test quote")

# =========================== routes: quote/book/label/cancel ================
@test
def t_quote_route():
    r = post("/api/dispatch/quote", {"order_id": 12345, "box": {"width": 20, "length": 15, "depth": 8, "weight": 0.6}})
    eq(r.status_code, 200, r.text)
    body = r.json()
    # three door services, plus the cheaper no-signature price for the one carrier
    # that actually has a no-signature service
    eq(len(body["options"]), 4, "shop services hidden by default")
    eq(len([o for o in body["options"] if o.get("no_signature")]), 1, "one no-signature row")
    eq(body["destination"]["postcode"], "M1 2AB", "dest")

@test
def t_quote_bad_box():
    r = post("/api/dispatch/quote", {"order_id": 12345, "box": {"width": 0, "length": 15, "depth": 8, "weight": 0}})
    eq(r.status_code, 400, "bad box")
    ok("above zero" in r.json()["error"], "message")

@test
def t_book_defers_fulfilment_until_made():
    reset_dispatch(); reset_prod()
    TAG_WRITES.clear(); FULFILLED.clear()
    r = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
    eq(r.status_code, 200, r.text)
    body = r.json()
    eq(body["ok"], True, "booked")
    eq(body["shipment"]["tracking_number"], "WO1234567890", "tracking")
    eq(body["awaiting_made"], True, "flagged as waiting on Mark made")
    eq(len(FULFILLED), 0, "booking must NOT fulfil an unmade order")
    joined = " ".join(t[1].lower() for t in TAG_WRITES)
    ok("dispatched" not in joined, "not tagged Dispatched while unmade")
    st = json.load(open(SCRATCH + "/dispatch_state.json"))["orders"]["12345"]
    eq(st["fulfilled"], False, "state says unfulfilled")
    eq(st["notify"], True, "email choice stored for later")
    ok(os.path.isfile(SCRATCH + "/labels/12345.json"), "label saved for reprint")

    # Marking made is what ships it.
    TAG_WRITES.clear()
    r2 = mark_made()
    eq(r2.status_code, 200, r2.text)
    b2 = r2.json()
    eq(b2["fulfilled"], True, "made fulfils when a label is booked")
    eq(b2["notified"], True, "customer emailed at made")
    ok("Fulfilled in Shopify" in (b2.get("ship_note") or ""), "explains what happened")
    eq(len(FULFILLED), 1, "exactly one fulfillment")
    eq(FULFILLED[0]["tracking"], "WO1234567890", "booked tracking used")
    eq(FULFILLED[0]["company"], "UPS", "carrier name mapped for Shopify")
    last = TAG_WRITES[-1][1].lower()
    ok("dispatched" in last, "now tagged Dispatched")
    ok("ip" not in [t.strip() for t in last.split(",")], "IP dropped")
    st = json.load(open(SCRATCH + "/dispatch_state.json"))["orders"]["12345"]
    eq(st["fulfilled"], True, "state records the fulfilment")
    eq(st["fulfillment_id"], 555, "fulfillment id kept for unwinding")

@test
def t_made_is_idempotent():
    # Re-marking made must not fulfil (or email) twice.
    FULFILLED.clear()
    r = mark_made()
    eq(r.status_code, 200, r.text)
    eq(len(FULFILLED), 0, "no second fulfillment")

@test
def t_made_first_then_dispatch_fulfils():
    reset_dispatch(); reset_prod()
    FULFILLED.clear(); TAG_WRITES.clear()
    mark_made()                      # made with no label yet: just IP -> PC
    eq(len(FULFILLED), 0, "nothing to fulfil without a label")
    r = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
    eq(r.status_code, 200, r.text)
    eq(r.json()["awaiting_made"], False, "already made, so it ships now")
    eq(len(FULFILLED), 1, "dispatch fulfils an already-made order")
    ok("dispatched" in TAG_WRITES[-1][1].lower(), "tagged Dispatched")

@test
def t_untick_made_unwinds_the_fulfilment():
    reset_dispatch(); reset_prod()
    CANCELED_FULFILLMENTS.clear(); TAG_WRITES.clear()
    post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
    mark_made()
    r = mark_made(on=False)
    eq(r.status_code, 200, r.text)
    eq(CANCELED_FULFILLMENTS, [555], "Shopify fulfillment cancelled")
    st = json.load(open(SCRATCH + "/dispatch_state.json"))["orders"]["12345"]
    eq(st["fulfilled"], False, "state reverted")
    ok(st.get("tracking_number"), "label still booked")
    last = TAG_WRITES[-1][1].lower()
    ok("dispatched" not in last, "Dispatched removed")
    ok("ip" in [t.strip() for t in last.split(",")], "back in production")

@test
def t_book_no_option():
    r = post("/api/dispatch/book", {"order_id": 12345, "option": {}, "box": {"width": 20, "length": 15, "depth": 8, "weight": 0.6}})
    eq(r.status_code, 400, "no option -> error")
    ok("selected" in r.json()["error"], "message")

@test
def t_label_reprint():
    r = post("/api/dispatch/label", {"order_id": 12345})
    eq(r.status_code, 200, r.text)
    eq(r.json()["labels"][0]["type"], "base64pdf", "stored label returned")

@test
def t_label_missing():
    r = post("/api/dispatch/label", {"order_id": 99999})
    eq(r.status_code, 404, "no label -> 404")

@test
def t_cancel_route():
    r = post("/api/dispatch/cancel", {"order_id": 12345, "tracking_number": "WO1234567890"})
    eq(r.status_code, 200, r.text)
    st = json.load(open(SCRATCH + "/dispatch_state.json"))["orders"]
    eq(st["12345"]["canceled"], True, "state canceled")

@test
def t_dispatch_state_in_labels():
    res = run(copilot.run_production_labels({}, order_id=12345))
    ok("dispatch" in res, "dispatch map")
    eq(res["dispatch"]["12345"]["tracking_number"], "WO1234567890", "tracking flows to UI")

@test
def t_status_shipping_row():
    r = post("/api/status", {})
    sh = r.json()["shipping"]
    eq(sh["ok"], True, "connected")
    eq(sh["fulfillment"], True, "fulfillment wired")

@test
def t_backup_excludes_secret():
    r = post("/api/backup", {})
    eq(r.status_code, 200, "backup ok")
    import io, zipfile
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    ok(not any("wo_secret" in n for n in names), "WO secret excluded")
    ok(any("shipping.json" in n for n in names), "shipping config backed up")

@test
def t_env_creds_win():
    os.environ["WO_METER_NUMBER"] = "ENV-METER"
    try:
        copilot._wo_boot()
        r = post("/api/shipping/config", {"op": "set", "meter_number": "TRY-OVERRIDE"})
        eq(r.status_code, 400, "env creds protect against UI change")
        ok("server" in r.json()["error"], "explains env")
    finally:
        os.environ.pop("WO_METER_NUMBER", None)
        copilot._wo_boot()

@test
def t_collection_window_config():
    r = post("/api/shipping/config", {"op": "set", "ready_time": "14:00", "close_time": "17:30"})
    eq(r.status_code, 200, r.text)
    eq(r.json()["config"]["ready_time"], "14:00", "ready persisted")
    eq(r.json()["config"]["close_time"], "17:30", "close persisted")
    r = post("/api/shipping/config", {"op": "set", "ready_time": "2pm"})
    eq(r.status_code, 400, "bad format rejected")
    ok("HH:MM" in r.json()["error"], "format message")
    r = post("/api/shipping/config", {"op": "set", "ready_time": "18:00", "close_time": "17:30"})
    eq(r.status_code, 400, "ready after close rejected")
    r = post("/api/shipping/config", {"op": "set", "ready_time": "", "close_time": ""})
    eq(r.status_code, 200, "clearing allowed")
    eq(r.json()["config"]["ready_time"], "", "cleared")

@test
def t_book_envelope_collection_window():
    worldoptions.set_credentials(meter="M1")
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner; return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        run(worldoptions.book({"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
                              {"postcode": "LS1 1AA", "country": "GB"}, {"postcode": "M1 2AB", "country": "GB"},
                              [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}],
                              ready_time="14:00", close_time="17:30"))
        xml = holder["xml"]
        # The block carries more than the window now (TransportationPayor lives here),
        # so the assertion is on the values and their order, not the exact string.
        ok("<wo:CloseTime>17:30</wo:CloseTime>" in xml, "close time sent")
        ok("<wo:ReadyTime>14:00</wo:ReadyTime>" in xml, "ready time sent")
        ok(xml.index("<wo:CloseTime>") < xml.index("<wo:ReadyTime>"),
           "billing block in schema sequence, CloseTime before ReadyTime")
        ok(xml.index("AuthenticationDetail") < xml.index("BillingDetail") < xml.index("RecipientsDetails"),
           "BillingDetail between auth and recipient (alphabetical request order)")
        # Without a window the block is STILL sent: it used to be dropped entirely,
        # but TransportationPayor lives inside it and its enum starts at
        # Bill_To_Receiver, so an absent block invoiced the customer for carriage.
        run(worldoptions.book({"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
                              {"postcode": "LS1 1AA", "country": "GB"}, {"postcode": "M1 2AB", "country": "GB"},
                              [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}]))
        ok("<wo:TransportationPayor>Bill_To_Sender</wo:TransportationPayor>" in holder["xml"],
           "no window, but the payor is still stated")
        # Learned from their live validator ("Ready date should be in format -
        # dd/MM/yyyy"): format checks run on PRESENT values, so an unset time is
        # OMITTED, never sent as "".
        ok("<wo:CloseTime>" not in holder["xml"], "an unset window is absent, not an empty string")
    finally:
        worldoptions._soap_call = saved

@test
def t_book_route_passes_window():
    reset_dispatch()
    post("/api/shipping/config", {"op": "set", "ready_time": "09:30", "close_time": "17:00"})
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder.setdefault("xmls", []).append(inner); return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        opt = {"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS", "amount": 12.4}
        r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": {"width": 20, "length": 15, "depth": 8, "weight": 0.6}})
        eq(r.status_code, 200, r.text)
        # The window is a preference now, not the literal sent: booking after 09:30
        # must roll the ready-from forward or WO rejects it as being in the past.
        # The route must send exactly what _collection_ready computes for this cfg.
        want_d, want_t = copilot._collection_ready({"ready_time": "09:30", "close_time": "17:00"})
        xml = holder["xmls"][-1]
        ok("<wo:ReadyTime>%s</wo:ReadyTime>" % want_t in xml,
           "ready time is the computed future slot (" + want_t + ")")
        ok("<wo:ReadyDate>%s</wo:ReadyDate>" % want_d in xml,
           "ready date matches (" + want_d + ")")
    finally:
        worldoptions._soap_call = saved
        post("/api/shipping/config", {"op": "set", "ready_time": "", "close_time": ""})

@test
def t_shopify_carrier_mapping():
    eq(worldoptions.shopify_carrier("ROYALMAIL"), "Royal Mail", "royal mail")
    eq(worldoptions.shopify_carrier("EVRISEND"), "Evri", "evri")
    eq(worldoptions.shopify_carrier("DHLPARCEL"), "DHL", "dhl parcel")
    eq(worldoptions.shopify_carrier("UPS"), "UPS", "ups")
    # It used to pass an unknown code through. Shopify prints tracking_company
    # verbatim in the customer's shipping email, so a raw enum went to the customer.
    eq(worldoptions.shopify_carrier("SOMETHINGNEW"), "", "an unknown code is not a company name")

@test
def t_collection_option_envelope():
    worldoptions.set_credentials(meter="M1")
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner; return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        run(worldoptions.book({"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
                              {"postcode": "LS1 1AA", "country": "GB"}, {"postcode": "M1 2AB", "country": "GB"},
                              [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}],
                              ready_time="09:00", close_time="17:00",
                              collection_option="I_Have_Daily_Collection"))
        xml = holder["xml"]
        ok("<wo:CollectionOptions>I_Have_Daily_Collection</wo:CollectionOptions>" in xml, "collection option sent")
        ok(xml.index("CloseTime") < xml.index("CollectionOptions") < xml.index("ReadyTime"), "alphabetical in BillingDetail")
        # invalid values are dropped, not sent
        run(worldoptions.book({"service_type_code": "UPS_Standard", "package_type_code": "P", "carrier_name": "UPS"},
                              {"postcode": "a", "country": "GB"}, {"postcode": "b", "country": "GB"},
                              [{"width": 1, "length": 1, "depth": 1, "weight": 1}],
                              collection_option="Bogus_Value"))
        ok("CollectionOptions" not in holder["xml"], "bogus option dropped")
    finally:
        worldoptions._soap_call = saved

@test
def t_collection_option_config():
    r = post("/api/shipping/config", {"op": "set", "collection_option": "I_Have_Daily_Collection"})
    eq(r.status_code, 200, r.text)
    eq(r.json()["config"]["collection_option"], "I_Have_Daily_Collection", "persisted")
    ok("I_Am_Going_To_Drop_Off_My_Packages" in r.json()["config"]["collection_options"], "options listed for UI")
    r = post("/api/shipping/config", {"op": "set", "collection_option": "Nonsense"})
    eq(r.status_code, 400, "whitelist enforced")
    post("/api/shipping/config", {"op": "set", "collection_option": "I_Need_To_Book_A_Collection"})

@test
def t_currency_fallback_and_international():
    global ORDER
    saved_order = ORDER
    ORDER = {**ORDER, "currency": "SEK",
             "shipping_address": {**ORDER["shipping_address"], "country_code": "DE"}}
    try:
        r = post("/api/dispatch/quote", {"order_id": 12345, "box": {"width": 20, "length": 15, "depth": 8, "weight": 0.6}})
        eq(r.status_code, 200, r.text)
        body = r.json()
        eq(body["international"], True, "non-GB flagged international")
        ok("SEK" in body["currency_note"], "currency fallback noted")
        eq(body["currency"], "GBP", "fell back to an accepted currency")
    finally:
        ORDER = saved_order

@test
def t_fulfillment_gets_mapped_carrier():
    reset_dispatch()
    FULFILLED.clear()
    async def cap(service, action, inner, retryable=True):
        return ET.fromstring(BOOK_XML.replace("UPS", "UPS"))
    # book with a Royal Mail option; fulfillment company must be "Royal Mail"
    reset_prod()
    opt = {"service_type_code": "RoyalMail_Tracked_24_Hours", "package_type_code": "RoyalMail_Parcel",
           "carrier_name": "ROYALMAIL", "service_name": "Tracked 24", "amount": 5.2}
    r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": {"width": 20, "length": 15, "depth": 8, "weight": 0.6}})
    eq(r.status_code, 200, r.text)
    mark_made()   # fulfilment happens here now
    eq(FULFILLED[-1]["company"], "Royal Mail", "Shopify-recognizable carrier name")

@test
def t_booking_never_retries():
    import httpx as _hx
    calls = {"n": 0}
    MODE = {"err": "connect"}
    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k):
            calls["n"] += 1
            if MODE["err"] == "connect": raise _hx.ConnectError("down")
            raise _hx.ReadTimeout("slow")   # request left the machine, reply lost
    saved_client = worldoptions.httpx.AsyncClient
    saved_soap = worldoptions._soap_call
    worldoptions.httpx.AsyncClient = FakeClient
    try:
        worldoptions._soap_call = REAL_SOAP_CALL
        worldoptions.set_credentials(meter="M1")
        # Connect error on a booking: nothing was sent, ONE attempt, safe message.
        MODE["err"] = "connect"; calls["n"] = 0
        try:
            run(worldoptions._soap_call("ShipmentService", "act", "<x/>", retryable=False))
            ok(False, "should raise")
        except worldoptions.WorldOptionsError as e:
            ok("nothing was booked" in str(e), "connect error -> nothing booked: " + str(e))
        eq(calls["n"], 1, "booking connect error: ONE attempt")
        # Post-send timeout on a booking: MAY have gone through, still ONE attempt, warn.
        MODE["err"] = "timeout"; calls["n"] = 0
        try:
            run(worldoptions._soap_call("ShipmentService", "act", "<x/>", retryable=False))
            ok(False, "should raise")
        except worldoptions.WorldOptionsError as e:
            ok("MAY still have gone through" in str(e), "read timeout -> double-charge warning")
        eq(calls["n"], 1, "booking timeout: ONE attempt")
        # A quote retries three times.
        MODE["err"] = "timeout"; calls["n"] = 0
        try:
            run(worldoptions._soap_call("RateService", "act", "<x/>", retryable=True))
        except worldoptions.WorldOptionsError:
            pass
        eq(calls["n"], 3, "quote: three attempts")
    finally:
        worldoptions.httpx.AsyncClient = saved_client
        worldoptions._soap_call = saved_soap

@test
def t_already_dispatched_guard():
    reset_dispatch()
    opt = {"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS", "amount": 12.4}
    box = {"width": 20, "length": 15, "depth": 8, "weight": 0.6}
    r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": box})
    eq(r.status_code, 200, "first booking ok")
    r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": box})
    eq(r.status_code, 400, "second booking refused")
    ok("already dispatched" in r.json()["error"], "explains")
    # force does NOT override a live dispatch record
    r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": box, "force": True})
    eq(r.status_code, 400, "force cannot override a live shipment")
    # after cancel, rebooking is allowed
    post("/api/dispatch/cancel", {"order_id": 12345, "tracking_number": "WO1234567890"})
    r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": box})
    eq(r.status_code, 200, "rebook after cancel allowed")

@test
def t_refunded_blocked():
    global ORDER
    saved = ORDER
    ORDER = {**ORDER, "financial_status": "refunded"}
    reset_dispatch()
    try:
        r = post("/api/dispatch/quote", {"order_id": 12345, "box": {"width": 20, "length": 15, "depth": 8, "weight": 0.6}})
        eq(r.status_code, 400, "quote refused")
        ok("refunded" in r.json()["error"], "quote message")
        r = post("/api/dispatch/book", {"order_id": 12345, "option": {"service_type_code": "UPS_Standard", "package_type_code": "P", "carrier_name": "UPS"}, "box": {"width": 20, "length": 15, "depth": 8, "weight": 0.6}})
        eq(r.status_code, 400, "book refused")
        ok("refunded" in r.json()["error"], "book message")
    finally:
        ORDER = saved

@test
def t_fulfilled_needs_force():
    global ORDER
    saved = ORDER
    ORDER = {**ORDER, "fulfillment_status": "fulfilled"}
    reset_dispatch()
    opt = {"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"}
    box = {"width": 20, "length": 15, "depth": 8, "weight": 0.6}
    try:
        r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": box})
        eq(r.status_code, 400, "fulfilled refused without force")
        eq(r.json().get("needs_force"), True, "needs_force flag")
        r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": box, "force": True})
        eq(r.status_code, 200, "force books")
    finally:
        ORDER = saved

@test
def t_cancel_unwinds_shopify():
    reset_dispatch()
    CANCELED_FULFILLMENTS.clear(); TAG_WRITES.clear()
    opt = {"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS", "amount": 12.4}
    box = {"width": 20, "length": 15, "depth": 8, "weight": 0.6}
    reset_prod()
    r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": box})
    eq(r.status_code, 200, "booked")
    mark_made()   # this is what fulfils
    st = json.load(open(SCRATCH + "/dispatch_state.json"))["orders"]["12345"]
    eq(st["fulfillment_id"], 555, "fulfillment id stored")
    TAG_WRITES.clear()
    global ORDER
    saved = ORDER
    ORDER = {**ORDER, "tags": "Dispatched"}   # what the order looks like after a real dispatch
    try:
        r = post("/api/dispatch/cancel", {"order_id": 12345, "tracking_number": "WO1234567890"})
    finally:
        ORDER = saved
    eq(r.status_code, 200, "cancel ok")
    eq(CANCELED_FULFILLMENTS, [555], "Shopify fulfillment cancelled")
    ok("re-dispatch" in (r.json().get("note") or ""), "note explains re-dispatch")
    ok(TAG_WRITES, "tags reverted")
    last = TAG_WRITES[-1][1].lower()
    ok("pc" in [t.strip() for t in last.split(",")], "back in To ship (PC)")
    ok("dispatched" not in last, "Dispatched removed")

@test
def t_shipping_paid_in_shape():
    global ORDER
    saved = ORDER
    ORDER = {**ORDER, "shipping_lines": [{"title": "Standard Delivery", "price": "4.95"}]}
    try:
        res = run(copilot.run_production_labels({}, order_id=12345))
        sp = res["orders"][0].get("shipping_paid")
        eq(sp["title"], "Standard Delivery", "title")
        eq(sp["price"], "4.95", "price")
    finally:
        ORDER = saved

@test
def t_next_day_collection_enum():
    r = post("/api/shipping/config", {"op": "set", "collection_option": "I_Need_To_Book_A_Collection_For_Next_Day"})
    eq(r.status_code, 200, "next-day accepted")
    post("/api/shipping/config", {"op": "set", "collection_option": "I_Need_To_Book_A_Collection"})

@test
def t_breakdown_and_shops_parsed():
    worldoptions.set_credentials(meter="M1")
    res = run(worldoptions.quote({"postcode": "LS1 1AA", "country": "GB"},
                                 {"postcode": "M1 2AB", "country": "GB"},
                                 [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}]))
    op0 = res["options"][0]
    labels = [b["label"] for b in op0["breakdown"]]
    ok("Base charge" in labels, "base charge in breakdown: " + str(labels))
    ok("Fuel surcharge" in labels, "fuel in breakdown")
    ok(all(b["label"] != "Total net charge" for b in op0["breakdown"]), "total excluded")
    eq(op0["shops"][0]["id"], "PO123", "shop id")
    eq(op0["shops"][0]["street"], "12 High St", "houseno + street")
    ok("0.4" in op0["shops"][0]["distance"], "distance")

@test
def t_multibox_and_value_envelope():
    worldoptions.set_credentials(meter="M1")
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner; return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        run(worldoptions.book({"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
                              {"postcode": "LS1 1AA", "country": "GB"}, {"postcode": "M1 2AB", "country": "GB"},
                              [{"width": 20, "length": 15, "depth": 8, "weight": 0.6, "custom_value": 62.5},
                               {"width": 30, "length": 22, "depth": 15, "weight": 1.2, "custom_value": 62.5}]))
        xml = holder["xml"]
        eq(xml.count("<sd:wsShippingDetail.PackageDetail>"), 2, "two parcels")
        ok("<sd:ItemNumber>1</sd:ItemNumber>" in xml and "<sd:ItemNumber>2</sd:ItemNumber>" in xml, "item numbers")
        eq(xml.count("<sd:CustomValue>62.5</sd:CustomValue>"), 2, "declared value on both")
    finally:
        worldoptions._soap_call = saved

@test
def t_customs_envelope():
    worldoptions.set_credentials(meter="M1")
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner; return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    customs = {"eori": "GB123456789000", "vat": "GB999", "export_reason": "Sale",
               "duties_payor": "Duties_To_Be_Paid_By_Receiver", "trade_term": "DAP",
               "invoice_number": "#104239", "receiver_tax_id": "DE-TAX-1",
               "goods": [{"description": "Glass projection gobo", "quantity": 2, "unit_price": 62.5,
                          "hs": "70200080", "country": "GB"}],
               "total_value": 125.0}
    try:
        run(worldoptions.book({"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
                              {"postcode": "LS1 1AA", "country": "GB"}, {"postcode": "10115", "country": "DE", "city": "Berlin"},
                              [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}],
                              customs=customs, insurance="125.00", signature="UPS_Adult"))
        xml = holder["xml"]
        ok(xml.index("<wo:AdditionalShipmentDetail>") < xml.index("<wo:AuthenticationDetail>"), "customs FIRST in request")
        ok("<ad:EORINumber>GB123456789000</ad:EORINumber>" in xml, "EORI")
        ok("<ad:CommercialInvoiceType>Help_Me_Generate</ad:CommercialInvoiceType>" in xml, "invoice type default")
        ok("<ad:ExportReason>Sale</ad:ExportReason>" in xml, "export reason")
        ok("<ad:wsAddlShipmentDetail.GoodsDetail>" in xml, "goods line")
        g = xml[xml.index("<ad:wsAddlShipmentDetail.GoodsDetail>"):]
        ok(g.index("CountryCode") < g.index("Description") < g.index("HTSNumber") < g.index("ItemNumber")
           < g.index("Quantity") < g.index("UnitPrice") < g.index("<ad:Wt>") if "<ad:Wt>" in g else True, "goods field order")
        ok("<ad:TotalCustomValue>125</ad:TotalCustomValue>" in xml, "total value")
        ok("<wo:DutiesPayor>Duties_To_Be_Paid_By_Receiver</wo:DutiesPayor>" in xml, "duties in billing")
        ok("<wo:DeliverySignatureType>UPS_Adult</wo:DeliverySignatureType>" in xml, "signature in billing")
        ok("<sd:Insurance>125.00</sd:Insurance>" in xml, "insurance in shipping")
        ok("<sd:SenderVatNo>GB999</sd:SenderVatNo>" in xml, "sender VAT")
        ok("<ad:ReceiverTaxId>DE-TAX-1</ad:ReceiverTaxId>" in xml, "receiver tax id")
    finally:
        worldoptions._soap_call = saved

@test
def t_dropoff_envelope():
    worldoptions.set_credentials(meter="M1")
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner; return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        run(worldoptions.book({"service_type_code": "Evri_DI_Ship_to_Shop_UK", "package_type_code": "Evri_Parcel", "carrier_name": "EVRISEND"},
                              {"postcode": "LS1 1AA", "country": "GB"}, {"postcode": "M1 2AB", "country": "GB"},
                              [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}],
                              dropoff_shop={"id": "PO123", "name": "Post Office Central", "street": "12 High St",
                                            "city": "Leeds", "postcode": "LS1 2AB"}))
        xml = holder["xml"]
        ok("<sd:CollectionDropOffInfo>" in xml, "dropoff info block")
        ok("<sd:DropOffId>PO123</sd:DropOffId>" in xml, "shop id")
        ok("<sd:IsCollectionDropoffRequired>true</sd:IsCollectionDropoffRequired>" in xml, "dropoff flag")
        ok(xml.index("CollectionDropOffInfo") < xml.index("<sd:CollectionType>"), "XSD order: dropoff first")
        # bogus signature is dropped silently
        run(worldoptions.book({"service_type_code": "UPS_Standard", "package_type_code": "P", "carrier_name": "UPS"},
                              {"postcode": "a", "country": "GB"}, {"postcode": "b", "country": "GB"},
                              [{"width": 1, "length": 1, "depth": 1, "weight": 1}], signature="Bogus_Sig"))
        ok("DeliverySignatureType" not in holder["xml"], "bogus signature dropped")
    finally:
        worldoptions._soap_call = saved

@test
def t_quote_insurance_dropoff_envelope():
    worldoptions.set_credentials(meter="M1")
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner; return ET.fromstring(RATE_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        run(worldoptions.quote({"postcode": "LS1 1AA", "country": "GB"}, {"postcode": "M1 2AB", "country": "GB"},
                               [{"width": 20, "length": 15, "depth": 8, "weight": 0.6, "custom_value": 100}],
                               insurance="150.00", collection_dropoff=True))
        xml = holder["xml"]
        ok("<rs:Insurance>150.00</rs:Insurance>" in xml, "insurance in quote")
        ok("<rs:IsCollectionDropoffRequired>true</rs:IsCollectionDropoffRequired>" in xml, "dropoff flag in quote")
        ok(xml.index("<rs:Insurance>") < xml.index("<rs:IsCollectionDropoffRequired>") < xml.index("<rs:PackageDetails>"), "quote XSD order")
        ok("<rs:CustomValue>100</rs:CustomValue>" in xml, "quote declared value")
    finally:
        worldoptions._soap_call = saved

@test
def t_multibox_route():
    reset_dispatch()
    r = post("/api/dispatch/quote", {"order_id": 12345, "boxes": [
        {"width": 20, "length": 15, "depth": 8, "weight": 0.6},
        {"width": 30, "length": 22, "depth": 15, "weight": 1.2}]})
    eq(r.status_code, 200, r.text)
    eq(r.json()["boxes"], 2, "two boxes quoted")
    eq(r.json()["weight"], 1.8, "summed weight")
    r = post("/api/dispatch/quote", {"order_id": 12345, "boxes": [{"width": 0, "length": 1, "depth": 1, "weight": 1}, {"width": 1, "length": 1, "depth": 1, "weight": 1}]})
    eq(r.status_code, 400, "bad box in list rejected")
    ok("Box 1" in r.json()["error"], "names the bad box")

@test
def t_intl_booking_requires_customs():
    global ORDER
    saved = ORDER
    ORDER = {**ORDER, "shipping_address": {**ORDER["shipping_address"], "country_code": "DE"},
             "line_items": [{"title": "Custom Gobo", "quantity": 2, "grams": 250, "product_id": 1,
                             "variant_title": "", "price": "62.50"}]}
    reset_dispatch()
    post("/api/shipping/config", {"op": "set", "eori": ""})
    opt = {"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"}
    box = {"width": 20, "length": 15, "depth": 8, "weight": 0.6}
    try:
        r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": box})
        eq(r.status_code, 400, "no EORI -> refused")
        ok("EORI" in r.json()["error"], "explains EORI")
        post("/api/shipping/config", {"op": "set", "eori": "GB123456789000"})
        r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": box})
        eq(r.status_code, 400, "no goods lines -> refused")
        ok("customs" in r.json()["error"].lower(), "explains goods")
        holder = {}
        async def cap(service, action, inner, retryable=True):
            holder["xml"] = inner; return ET.fromstring(BOOK_XML)
        saved_soap = worldoptions._soap_call; worldoptions._soap_call = cap
        try:
            r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": box,
                "customs": {"lines": [{"description": "Glass gobo", "quantity": 2, "unit_price": 62.5, "hs": "70200080"}]}})
            eq(r.status_code, 200, r.text)
            eq(r.json()["international"], True, "flagged international")
            ok("<ad:EORINumber>GB123456789000</ad:EORINumber>" in holder["xml"], "EORI from settings")
            ok("<ad:TotalCustomValue>125</ad:TotalCustomValue>" in holder["xml"], "total from lines")
            ok("<sd:CustomValue>125</sd:CustomValue>" in holder["xml"], "declared value from order items")
        finally:
            worldoptions._soap_call = saved_soap
    finally:
        ORDER = saved
        post("/api/shipping/config", {"op": "set", "eori": ""})

@test
def t_config_intl_fields():
    r = post("/api/shipping/config", {"op": "set", "eori": "GB1", "vat_number": "GB2", "default_hs_code": "700200",
                                      "export_reason": "Sale", "duties_payor": "Duties_To_Be_Paid_By_Sender", "trade_term": "DAP"})
    eq(r.status_code, 200, r.text)
    cfgj = r.json()["config"]
    eq(cfgj["eori"], "GB1", "eori")
    eq(cfgj["duties_payor"], "Duties_To_Be_Paid_By_Sender", "duties")
    ok("UPS" in cfgj["signature_options"], "signature groups exposed")
    r = post("/api/shipping/config", {"op": "set", "export_reason": "Nonsense"})
    eq(r.status_code, 400, "bad export reason rejected")
    post("/api/shipping/config", {"op": "set", "eori": "", "duties_payor": "Duties_To_Be_Paid_By_Receiver"})

@test
def t_carrier_enum_canonical():
    eq(worldoptions.canonical_carrier("palletways"), "Palletways", "case-normalized")
    eq(worldoptions.canonical_carrier("EXFREIGHT"), "EXFreight", "exfreight casing")
    eq(worldoptions.canonical_carrier("evri"), "", "bare Evri is not a member")
    eq(worldoptions.canonical_carrier("EVRISEND"), "EVRISEND", "evrisend ok")
    # _carrier_from maps an Evri_* service code to EVRISEND
    eq(worldoptions._carrier_from("Evri_DI_Ship_to_Shop_UK", ""), "EVRISEND", "evri prefix -> EVRISEND")
    eq(worldoptions._carrier_from("PALLETWAYS_Std", ""), "Palletways", "palletways prefix canonical")

@test
def t_book_omits_invalid_enums():
    worldoptions.set_credentials(meter="M1")
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner; return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        # rate-only package type + carrier that only prefix-resolves
        run(worldoptions.book({"service_type_code": "Evri_DI_Ship_to_Shop_UK", "package_type_code": "Any_NonDocument", "carrier_name": "EVRI"},
                              {"postcode": "a", "country": "GB"}, {"postcode": "b", "country": "GB"},
                              [{"width": 1, "length": 1, "depth": 1, "weight": 1}]))
        xml = holder["xml"]
        ok("<sd:ServiceType>EVRISEND</sd:ServiceType>" in xml, "carrier canonicalized to EVRISEND")
        # It used to be omitted. PackageTypeCode is a NON-NILLABLE enum, so omitting
        # it does not send nothing: WCF substitutes the first member, Fedex_Box, on
        # an Evri booking. The carrier's own packaging is sent instead.
        ok("<sd:PackageTypeCode>Evri_Parcel</sd:PackageTypeCode>" in xml,
           "rate-only package type replaced with the carrier's own, not left to default")
        # a valid package type IS sent
        run(worldoptions.book({"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
                              {"postcode": "a", "country": "GB"}, {"postcode": "b", "country": "GB"},
                              [{"width": 1, "length": 1, "depth": 1, "weight": 1}]))
        ok("<sd:PackageTypeCode>UPS_My_Packaging</sd:PackageTypeCode>" in holder["xml"], "valid package type kept")
    finally:
        worldoptions._soap_call = saved

@test
def t_export_type_from_reason():
    worldoptions.set_credentials(meter="M1")
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner; return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        for reason, want in [("Repair", "Temporary"), ("Return", "Re_export"), ("Sale", "Permanent")]:
            run(worldoptions.book({"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
                                  {"postcode": "a", "country": "GB"}, {"postcode": "b", "country": "DE"},
                                  [{"width": 1, "length": 1, "depth": 1, "weight": 1}],
                                  customs={"eori": "GB1", "export_reason": reason,
                                           "goods": [{"description": "x", "quantity": 1, "unit_price": 5}], "total_value": 5}))
            ok("<ad:ExportType>" + want + "</ad:ExportType>" in holder["xml"], f"{reason}->{want}")
    finally:
        worldoptions._soap_call = saved

@test
def t_label_types_png_and_unknown():
    def cls(lt):
        return worldoptions._classify_label(ET.fromstring(
            "<ShippingLabel><Image>QUJD</Image><LabelType>" + lt + "</LabelType></ShippingLabel>"))
    eq(cls("PNG")["type"], "base64png", "png")
    eq(cls("PDF")["type"], "base64pdf", "pdf")
    eq(cls("ZPL")["type"], "base64bin", "zpl -> bin, not fake pdf")
    eq(cls("")["type"], "base64pdf", "empty -> pdf default")

@test
def t_spread_value_remainder():
    boxes = copilot._spread_value([{}, {}, {}], 100.0)
    vals = [b["custom_value"] for b in boxes]
    eq(round(sum(vals), 2), 100.0, "spread sums to total")
    eq(vals[-1], round(100.0 - round(100/3, 2) * 2, 2), "remainder on last box")

@test
def t_one_bad_price_does_not_zero_order():
    o = {"line_items": [{"title": "A", "quantity": 2, "price": "62.50"},
                        {"title": "B", "quantity": 1, "price": "not-a-number"},
                        {"title": "C", "quantity": 3, "price": "10.00"}]}
    eq(copilot._order_goods_value(o), 155.0, "bad line skipped, others counted")

@test
def t_plugin_code_whitelist():
    r = post("/api/shipping/config", {"op": "set", "plugin_code": "Shopify"})
    eq(r.status_code, 200, "valid plugin accepted")
    eq(r.json()["config"]["plugin_code"], "Shopify", "persisted")
    ok("Web_Service" in r.json()["config"]["plugin_codes"], "list exposed")
    r = post("/api/shipping/config", {"op": "set", "plugin_code": "web service"})
    eq(r.status_code, 400, "typo rejected")
    post("/api/shipping/config", {"op": "set", "plugin_code": "Web_Service"})

@test
def t_intl_customs_total_drives_boxes():
    global ORDER
    saved = ORDER
    ORDER = {**ORDER, "shipping_address": {**ORDER["shipping_address"], "country_code": "DE"},
             "line_items": [{"title": "Custom Gobo", "quantity": 2, "price": "62.50"}]}
    reset_dispatch()
    post("/api/shipping/config", {"op": "set", "eori": "GB123456789000"})
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner; return ET.fromstring(BOOK_XML)
    saved_soap = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        r = post("/api/dispatch/book", {"order_id": 12345,
            "option": {"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
            "boxes": [{"width": 20, "length": 15, "depth": 8, "weight": 0.6},
                      {"width": 20, "length": 15, "depth": 8, "weight": 0.6}],
            "customs": {"lines": [{"description": "Gobo", "quantity": 2, "unit_price": 90, "hs": "70200080"}]}})
        eq(r.status_code, 200, r.text)
        xml = holder["xml"]
        ok("<ad:TotalCustomValue>180</ad:TotalCustomValue>" in xml, "dossier total from lines")
        # two boxes, declared values sum to 180 (90 each)
        import re as _re
        cvals = [float(x) for x in _re.findall(r"<sd:CustomValue>([\d.]+)</sd:CustomValue>", xml)]
        eq(round(sum(cvals), 2), 180.0, "box declared values sum to the customs total, not the order price")
        ok("<ad:Wt>" in xml, "goods line carries a weight, not implicit 0")
    finally:
        worldoptions._soap_call = saved_soap
        ORDER = saved
        post("/api/shipping/config", {"op": "set", "eori": ""})

@test
def t_dispatched_tag_survives_fulfilment():
    """Regression: tagging must happen BEFORE the fulfilment, or _sync_order_tags
    sees a now-fulfilled order, treats it as dead and silently skips the write -
    leaving the order out of the Dispatched queue forever."""
    global ORDER
    saved = ORDER
    reset_dispatch(); reset_prod(); TAG_WRITES.clear(); FULFILLED.clear()
    # A fulfilment writer that flips the order to fulfilled, like Shopify does.
    async def flipping_fulfillment(order_id, tracking_number=None, tracking_company=None,
                                   tracking_url=None, notify_customer=True):
        global ORDER
        FULFILLED.append({"order_id": order_id, "tracking": tracking_number,
                          "company": tracking_company, "notify": notify_customer})
        ORDER = {**ORDER, "fulfillment_status": "fulfilled"}
        return {"ok": True, "fulfillment_id": 555, "status": "success"}
    saved_writer = copilot._fulfillment_writer
    copilot._fulfillment_writer = flipping_fulfillment
    try:
        post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
        TAG_WRITES.clear()
        r = mark_made()
        eq(r.status_code, 200, r.text)
        eq(r.json()["fulfilled"], True, "fulfilled")
        ok(TAG_WRITES, "a tag write happened at all")
        ok(any("dispatched" in t[1].lower() for t in TAG_WRITES),
           "Dispatched tag actually written: " + str(TAG_WRITES))
    finally:
        copilot._fulfillment_writer = saved_writer
        ORDER = saved

@test
def t_failed_fulfilment_reverts_the_tag():
    reset_dispatch(); reset_prod(); TAG_WRITES.clear()
    async def refusing(order_id, **kw):
        return {"ok": False, "reason": "permission", "detail": "needs write_fulfillments"}
    saved_writer = copilot._fulfillment_writer
    copilot._fulfillment_writer = refusing
    try:
        post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
        TAG_WRITES.clear()
        r = mark_made()
        eq(r.status_code, 200, r.text)
        eq(r.json()["fulfilled"], False, "not fulfilled")
        last = TAG_WRITES[-1][1].lower()
        ok("dispatched" not in last, "Dispatched reverted after the failure: " + last)
        ok("pc" in [t.strip() for t in last.split(",")], "left as made")
    finally:
        copilot._fulfillment_writer = saved_writer

@test
def t_live_data_shapes_are_cleaned():
    """World Options puts display HTML and product codes inside data fields."""
    eq(worldoptions._wo_lines("Wed, 12 Aug 2026<br/>End of business day"),
       ["Wed, 12 Aug 2026", "End of business day"], "html split")
    eq(worldoptions._wo_lines("A&amp;B<br>C"), ["A&B", "C"], "entities + bare br")
    eq(worldoptions._tidy_time("15:00 PM"), "15:00", "bogus meridiem dropped")
    eq(worldoptions._tidy_time("9:30 AM"), "9:30 AM", "genuine am/pm kept")
    import datetime as _dt
    yr = _dt.datetime.now(_dt.timezone.utc).year
    eq(worldoptions._tidy_date("Wed, 12 Aug %d" % yr), "Wed 12 Aug", "this year's year dropped")
    eq(worldoptions._tidy_date("Wed, 12 Aug %d" % (yr + 1)), "Wed 12 Aug %d" % (yr + 1), "other year kept")
    # carrier hidden inside the service name is found; the chip word is not repeated
    eq(worldoptions.carrier_from_text("03 DHL Domestic Express"), "DHL", "carrier from name")
    eq(worldoptions._split_service_name("03 DHL Domestic Express", "DHL"), ("03", "Domestic Express"), "code + name split")
    eq(worldoptions._split_service_name("65 Express Saver", ""), ("65", "Express Saver"), "unknown carrier keeps name")
    eq(worldoptions.carrier_from_text("Groups pickups"), "", "no false UPS match inside words")
    eq(worldoptions.carrier_display("EVRISEND"), "Evri", "display name")

@test
def t_quote_options_expose_clean_fields():
    worldoptions.set_credentials(meter="M1")
    res = run(worldoptions.quote({"postcode": "LS1 1AA", "country": "GB"},
                                 {"postcode": "M1 2AB", "country": "GB"},
                                 [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}]))
    rm = [o for o in res["options"] if "Tracked" in o["service_name"]][0]
    eq(rm["carrier_name"], "ROYALMAIL", "carrier resolved from the name")
    eq(rm["carrier_label"], "Royal Mail", "friendly label")
    eq(rm["service_name"], "Tracked 24", "code and carrier word stripped")
    eq(rm["product_code"], "03", "product code kept separately")
    eq(rm["delivery_date"], "Wed 12 Aug", "delivery date cleaned")
    eq(rm["delivery_time"], "End of business day", "delivery time split out")
    eq(rm["pickup_time"], "15:00", "pickup time de-meridiemed")
    ok("<br" not in json.dumps(res), "no HTML anywhere in the payload")

@test
def t_quote_declares_package_and_shipment_type():
    """WCF gives an omitted enum its FIRST member: without these, every quote went
    out as a Fedex_Box on an Export shipment, hiding domestic services."""
    worldoptions.set_credentials(meter="M1")
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner; return ET.fromstring(RATE_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        run(worldoptions.quote({"postcode": "LS1 1AA", "country": "GB"},
                               {"postcode": "M1 2AB", "country": "GB"},
                               [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}],
                               shipment_mode="Domestic"))
        xml = holder["xml"]
        ok("<rs:PackageType>Any_NonDocument</rs:PackageType>" in xml, "generic parcel type sent")
        ok("<rs:ShipmentType>Domestic</rs:ShipmentType>" in xml, "domestic mode sent")
        # XSD sequence order inside wsShippingDetails
        ok(xml.index("<rs:PackageDetails>") < xml.index("<rs:PackageType>")
           < xml.index("<rs:ServiceName>") < xml.index("<rs:ServiceTypeName>")
           < xml.index("<rs:ShipmentType>"), "fields in XSD sequence order")
    finally:
        worldoptions._soap_call = saved

@test
def t_shipment_mode_follows_the_countries():
    global ORDER
    saved = ORDER
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder.setdefault("xmls", []).append(inner); return ET.fromstring(RATE_XML)
    saved_soap = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
        ok("<rs:ShipmentType>Domestic</rs:ShipmentType>" in holder["xmls"][-1], "GB->GB is Domestic")
        ORDER = {**ORDER, "shipping_address": {**ORDER["shipping_address"], "country_code": "DE"}}
        post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
        ok("<rs:ShipmentType>Export</rs:ShipmentType>" in holder["xmls"][-1], "GB->DE is Export")
    finally:
        worldoptions._soap_call = saved_soap
        ORDER = saved

@test
def t_options_carry_vat_split():
    worldoptions.set_credentials(meter="M1")
    res = run(worldoptions.quote({"postcode": "LS1 1AA", "country": "GB"},
                                 {"postcode": "M1 2AB", "country": "GB"},
                                 [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}]))
    op = res["options"][0]
    ok(op["vat"] is not None, "VAT captured")
    eq(round(op["amount_ex_vat"] + op["vat"], 2), op["amount"], "ex VAT + VAT == total")
    # every option's split must reconcile, including any without a VAT line
    for o in res["options"]:
        if o["amount"] is None:
            continue
        eq(round(o["amount_ex_vat"] + (o["vat"] or 0), 2), o["amount"], "split reconciles: " + o["service_name"])

@test
def t_unprint_undoes_a_print():
    reset_prod(); TAG_WRITES.clear()
    r = post("/api/production-state", {"op": "printed", "ids": [12345]})
    eq(r.status_code, 200, r.text)
    st = json.load(open(SCRATCH + "/production_state.json"))["orders"]
    ok(st.get("12345", {}).get("printed_at"), "printed stamped")
    r = post("/api/production-state", {"op": "unprinted", "ids": [12345]})
    eq(r.status_code, 200, r.text)
    st = json.load(open(SCRATCH + "/production_state.json"))["orders"]
    ok(not (st.get("12345") or {}).get("printed_at"), "stamp cleared")
    last = TAG_WRITES[-1][1].lower()
    ok("unprocessed" in last, "back to Unprocessed: " + last)
    r = post("/api/production-state", {"op": "unprinted", "ids": []})
    eq(r.status_code, 400, "no ids rejected")

@test
def t_failed_dispatched_tag_is_reported():
    reset_dispatch(); reset_prod()
    async def refusing_tags(order_id, tags):
        raise RuntimeError("shopify said no")
    saved = copilot._order_tag_writer
    try:
        post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
        copilot._order_tag_writer = refusing_tags
        r = mark_made()
        eq(r.status_code, 200, r.text)
        b = r.json()
        eq(b["fulfilled"], True, "still fulfilled")
        ok("Dispatched tag did not save" in (b.get("ship_note") or ""),
           "operator is told the tag failed: " + str(b.get("ship_note")))
        ok(b.get("tag_note"), "tag_note surfaced rather than discarded")
    finally:
        copilot._order_tag_writer = saved

@test
def t_pickup_point_services_are_surfaced():
    """The cheaper Access Point services only come back when the quote asks to
    deliver to a shop, so the route must run BOTH quotes and merge them."""
    reset_dispatch(); reset_prod()
    post("/api/shipping/config", {"op": "set", "show_parcelshop": True})
    r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
    eq(r.status_code, 200, r.text)
    opts = r.json()["options"]
    codes = [o["service_type_code"] for o in opts]
    ok("UPS_Express_Saver_AP" in codes, "the cheaper Access Point service is offered: " + str(codes))
    eq(codes.count("UPS_Express_Saver"), 1, "the door service is not duplicated")
    ap = [o for o in opts if o["service_type_code"] == "UPS_Express_Saver_AP"][0]
    eq(ap["delivery_dropoff"], True, "flagged as collect-from-shop")
    eq(ap["delivery_shops"][0]["name"], "Corner Shop", "the shop is named")
    eq(opts[0]["amount"], min(o["amount"] for o in opts if o["amount"]), "still cheapest first")
    # a door option must never be mislabelled
    door = [o for o in opts if o["service_type_code"] == "UPS_Express_Saver"][0]
    eq(door["delivery_dropoff"], False, "door service not flagged")
    post("/api/shipping/config", {"op": "set", "show_parcelshop": False})

@test
def t_booking_an_access_point_sends_the_shop():
    reset_dispatch(); reset_prod()
    holder = {}
    async def cap(service, action, inner, retryable=True):
        if service == "ShipmentService":
            holder["xml"] = inner; return ET.fromstring(BOOK_XML)
        return ET.fromstring(AP_XML if "IsDeliveryDropoffRequired" in inner else RATE_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        opt = {"service_type_code": "UPS_Express_Saver_AP", "package_type_code": "UPS_My_Packaging",
               "carrier_name": "UPS", "service_name": "Express Saver Access Point", "amount": 7.44,
               "delivery_dropoff": True,
               "delivery_shops": [{"id": "UPS991", "name": "Corner Shop", "street": "7 Market St",
                                    "city": "Manchester", "postcode": "M1 3AA"}]}
        r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": BOX})
        eq(r.status_code, 200, r.text)
        xml = holder["xml"]
        ok("<sd:DeliveryDropOffInfo>" in xml, "shop block sent")
        ok("<sd:DropOffId>UPS991</sd:DropOffId>" in xml, "shop id sent")
        ok("<sd:IsDeliveryDropoffRequired>true</sd:IsDeliveryDropoffRequired>" in xml, "flag sent")
        ok(xml.index("<sd:CustomerReference>") < xml.index("<sd:DeliveryDropOffInfo>")
           < xml.index("<sd:PackageDetails>"), "XSD sequence order kept")
        eq(r.json()["delivery_shop"]["name"], "Corner Shop", "reported back for the UI")
    finally:
        worldoptions._soap_call = saved

@test
def t_access_point_without_a_shop_is_refused():
    reset_dispatch(); reset_prod()
    opt = {"service_type_code": "UPS_Express_Saver_AP", "package_type_code": "UPS_My_Packaging",
           "carrier_name": "UPS", "delivery_dropoff": True, "delivery_shops": []}
    r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": BOX})
    eq(r.status_code, 400, "refused rather than shipping nowhere")
    ok("did not return a shop" in r.json()["error"], "explains why")

@test
def t_one_failed_quote_does_not_lose_the_other():
    reset_dispatch(); reset_prod()
    async def half(service, action, inner, retryable=True):
        if service == "RateService" and "IsDeliveryDropoffRequired" in inner:
            raise worldoptions.WorldOptionsError("pickup points unavailable")
        return ET.fromstring(RATE_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = half
    try:
        r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
        eq(r.status_code, 200, "door quote still returned")
        ok(len(r.json()["options"]) >= 1, "options present")
    finally:
        worldoptions._soap_call = saved

@test
def t_parcelshop_services_are_hidden_by_default():
    reset_dispatch(); reset_prod()
    SOAP_MODE["calls"].clear()          # only judge the calls this test makes
    r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
    eq(r.status_code, 200, r.text)
    body = r.json()
    eq(body["show_parcelshop"], False, "hidden by default")
    codes = [o["service_type_code"] for o in body["options"]]
    ok(not any(x.endswith("_AP") for x in codes), "no Access Point services: " + str(codes))
    ok(not any("ParcelShop" in (o.get("service_full") or "") for o in body["options"]),
       "no ParcelShop services by name")
    # the second (pickup-point) quote is not even requested when hidden
    rate_calls = [i for (s, i) in SOAP_MODE["calls"] if s == "RateService"]
    ok(not any("IsDeliveryDropoffRequired" in i for i in rate_calls),
       "no pickup-point request is made when the setting is off")

@test
def t_parcelshop_can_be_switched_on():
    post("/api/shipping/config", {"op": "set", "show_parcelshop": True})
    r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
    codes = [o["service_type_code"] for o in r.json()["options"]]
    ok(any(x.endswith("_AP") for x in codes), "shown when asked for: " + str(codes))
    post("/api/shipping/config", {"op": "set", "show_parcelshop": False})

@test
def t_diagnose_reports_what_each_setting_returns():
    r = post("/api/dispatch/diagnose", {"order_id": 12345, "box": BOX})
    eq(r.status_code, 200, r.text)
    d = r.json()
    labels = [row["label"] for row in d["rows"]]
    ok("As the app quotes now" in labels, "baseline row present")
    ok(any("signature" in l.lower() for l in labels), "signature variants tried")
    ok(any("UPS only" in l for l in labels), "per-carrier variant tried")
    # the pickup-point variant finds services the baseline did not
    codes = [x["code"] for x in d["extra_found"]]
    ok("UPS_Express_Saver_AP" in codes,
       "reports the service that only appears under another setting: " + str(d["extra_found"]))
    ok(all(x["name"].strip() for x in d["extra_found"]), "every reported service is named, not a bare code")
    base = d["rows"][0]["services"]
    ok(base and all(not s.get("new") for s in base), "baseline rows are never marked new")

@test
def t_diagnose_sends_the_signature_flag():
    holder = {"xmls": []}
    async def cap(service, action, inner, retryable=True):
        if service == "RateService":
            holder["xmls"].append(inner)
            return ET.fromstring(AP_XML if "IsDeliveryDropoffRequired" in inner else RATE_XML)
        return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        post("/api/dispatch/diagnose", {"order_id": 12345, "box": BOX})
        joined = " ".join(holder["xmls"])
        ok("<rs:SignatureType>Fedex_No_Signature_Required</rs:SignatureType>" in joined, "signature variant sent")
        ok("<rs:ServiceName>UPS</rs:ServiceName>" in joined, "UPS-only variant sent")
        ok("<rs:PackageType>UPS_My_Packaging</rs:PackageType>" in joined, "packaging variant sent")
        # SignatureType must come last in the XSD sequence
        one = [x for x in holder["xmls"] if "SignatureType" in x][0]
        ok(one.index("<rs:ShipmentType>") < one.index("<rs:SignatureType>"), "XSD order kept")
    finally:
        worldoptions._soap_call = saved

@test
def t_cheaper_no_signature_option_is_offered():
    reset_dispatch(); reset_prod()
    r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
    eq(r.status_code, 200, r.text)
    opts = r.json()["options"]
    ns = [o for o in opts if o.get("no_signature")]
    eq(len(ns), 1, "one cheaper no-signature row: " + str([(o["service_name"], o["amount"]) for o in opts]))
    eq(ns[0]["amount"], 9.10, "the cheaper price")
    eq(ns[0]["saves_vs_signed"], 0.84, "saving shown")
    eq(ns[0]["carrier_name"], "DHL", "only a carrier with a no-signature service is offered")
    eq(ns[0]["signature_type"], "DHL_No_Signature_Required",
       "carries THAT CARRIER's own literal, not the one the sweep was quoted with")
    # the signed version is still there, and cheapest-first still holds
    ok(any(o["service_type_code"] == ns[0]["service_type_code"] and not o.get("no_signature") for o in opts),
       "the normal priced version is kept too")
    amounts = [o["amount"] for o in opts if o["amount"] is not None]
    eq(amounts, sorted(amounts), "still cheapest first")

@test
def t_no_signature_is_not_offered_when_it_is_not_cheaper():
    global NOSIG_XML
    saved = NOSIG_XML
    try:
        globals()["NOSIG_XML"] = RATE_XML       # identical prices
        r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
        opts = r.json()["options"]
        eq([o for o in opts if o.get("no_signature")], [], "no pointless duplicate rows")
    finally:
        globals()["NOSIG_XML"] = saved

@test
def t_booking_reproduces_the_quoted_signature():
    reset_dispatch(); reset_prod()
    holder = {}
    async def cap(service, action, inner, retryable=True):
        if service == "ShipmentService":
            holder["xml"] = inner; return ET.fromstring(BOOK_XML)
        return ET.fromstring(RATE_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        opt = {"service_type_code": "DHL_DOMESTIC_EXPRESS", "package_type_code": "DHL_NonDocument",
               "carrier_name": "DHL", "service_name": "Domestic Express", "amount": 9.10,
               "no_signature": True, "signature_type": "DHL_No_Signature_Required"}
        r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": BOX})
        eq(r.status_code, 200, r.text)
        ok("<wo:DeliverySignatureType>DHL_No_Signature_Required</wo:DeliverySignatureType>" in holder["xml"],
           "the quoted signature setting is sent back so the charge matches")
    finally:
        worldoptions._soap_call = saved

@test
def t_carrier_is_resolved_from_every_signal_world_options_gives():
    # Their own carrier field wins outright.
    eq(worldoptions._carrier_from("UPS_Standard", "DHL"), "DHL", "explicit ServiceType wins")
    # Then the service code prefix.
    eq(worldoptions._carrier_from("UPS_Express_Saver", ""), "UPS", "service code prefix")
    # Then the package type, which names the carrier on every real option.
    eq(worldoptions._carrier_from("", "", "UPS_My_Packaging", "11 Standard"), "UPS", "package type")
    eq(worldoptions._carrier_from("", "", "DHL_NonDocument", "03 Domestic Express"), "DHL", "package type")
    eq(worldoptions._carrier_from("", "", "Fedex_Your_Packaging", "13 First"), "FEDEX", "package type")
    eq(worldoptions._carrier_from("", "", "RoyalMail_Parcel", "Tracked 24"), "ROYALMAIL", "package type")
    # Last, a carrier word inside the service text.
    eq(worldoptions._carrier_from("", "", "", "03 DHL Domestic Express"), "DHL", "carrier named in the text")

@test
def t_underscored_codes_no_longer_defeat_the_text_search():
    # \b does not match between a letter and an underscore, so every one of these
    # used to come back empty and the option showed no carrier at all.
    for text, want in [("UPS_Standard", "UPS"), ("DHL_DOMESTIC_EXPRESS_1200", "DHL"),
                       ("Evri_Next_Day", "EVRISEND"), ("DX_Express", "DXEXPRESS"),
                       ("TNT_Express", "TNT"), ("DPD_Next_Day", "DPD"),
                       ("DSV_LTL", "DSV"), ("UKMAIL_NonDocument", "UKMAIL")]:
        eq(worldoptions.carrier_from_text(text), want, "carrier found in " + text)

@test
def t_every_resolvable_carrier_has_a_readable_name():
    seen = set()
    for code in (worldoptions._CARRIERS + worldoptions.SERVICE_COMPANY_ENUM
                 + list(worldoptions._PREFIX_TO_ENUM.values())):
        cr = worldoptions._prefix_carrier(code) or worldoptions.canonical_carrier(code) or code
        if cr in ("ALL", "") or cr in seen:
            continue
        seen.add(cr)
        shown = worldoptions.carrier_display(cr)
        ok(shown and shown != cr.upper() or cr in ("UPS", "DHL", "TNT", "DPD", "DSV"),
           "carrier " + cr + " reads as " + repr(shown) + ", not a raw enum")

@test
def t_quote_names_the_carrier_for_every_live_option():
    reset_dispatch(); reset_prod()
    r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
    eq(r.status_code, 200, r.text)
    for o in r.json()["options"]:
        ok(o["carrier_label"], "option " + repr(o["service_name"]) + " names its carrier")

@test
def t_the_page_can_name_every_carrier_the_server_can_resolve():
    # The page keeps its own map for booked orders. A carrier the server resolves
    # but the page cannot name would show the merchant a raw enum like EVRICORPORATE.
    html = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "static", "index.html"), encoding="utf-8").read()
    block = re.search(r"const CARRIER_LABELS = \{(.*?)\};", html, re.S)
    ok(block, "found CARRIER_LABELS on the page")
    page = dict(re.findall(r"(\w+): '([^']+)'", block.group(1)))
    for code, name in worldoptions.CARRIER_DISPLAY.items():
        eq(page.get(code), name, "page names " + code + " the same way the server does")


# A quote reply shaped the way this account has NEVER been proven to answer: no
# wsQuoteDetails/ServiceType, no carrier prefix on the code, names like "11 Standard".
# The fixtures elsewhere assume the friendly shape; this one asserts what happens
# when that assumption is wrong, which is the case nobody would notice until it hit.
BLIND_XML = """<Envelope><Body><GetAllServicesAndRatesResponse>
<GetAllServicesAndRatesResult><Message/><NotificationtType>SUCCESS</NotificationtType><wsRateService>
 <wsAvailableServicesAndRates>
   <wsPackageTypeCode>Any_NonDocument</wsPackageTypeCode><wsServiceCode>11</wsServiceCode>
   <wsServiceTypeCode>11</wsServiceTypeCode><wsServiceTypeName>11 Standard</wsServiceTypeName>
   <wsDeliveryDateTime>Thu, 13 Aug 2026&lt;br/&gt;End of business day</wsDeliveryDateTime>
   <wsQuoteDetails><TotalNetCharge>7.31</TotalNetCharge><VATCharge>1.22</VATCharge></wsQuoteDetails>
 </wsAvailableServicesAndRates>
 <wsAvailableServicesAndRates>
   <wsPackageTypeCode>Any_NonDocument</wsPackageTypeCode><wsServiceCode>03</wsServiceCode>
   <wsServiceTypeCode>03</wsServiceTypeCode><wsServiceTypeName>03 DHL Domestic Express</wsServiceTypeName>
   <wsDeliveryDateTime>Thu, 13 Aug 2026&lt;br/&gt;End of business day</wsDeliveryDateTime>
   <wsQuoteDetails><TotalNetCharge>9.94</TotalNetCharge><VATCharge>1.66</VATCharge></wsQuoteDetails>
 </wsAvailableServicesAndRates>
</wsRateService></GetAllServicesAndRatesResult></GetAllServicesAndRatesResponse></Body></Envelope>"""

@test
def t_an_account_that_names_no_carrier_degrades_honestly():
    async def blind(service, action, inner, retryable=True):
        return ET.fromstring(BLIND_XML if service == "RateService" else BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = blind
    try:
        reset_dispatch(); reset_prod()
        r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
        eq(r.status_code, 200, r.text)
        opts = {o["service_name"]: o for o in r.json()["options"]}
        # The name spells DHL out, so that one is still known.
        eq(opts["Domestic Express"]["carrier_label"], "DHL", "carrier read from the name")
        # Nothing anywhere names the carrier of "11 Standard". It must come back
        # EMPTY rather than guessed, so the page can say so instead of inventing one.
        eq(opts["Standard"]["carrier_label"], "", "no carrier is admitted, not invented")
        eq(opts["Standard"]["product_code"], "11", "their code survives for the operator")
    finally:
        worldoptions._soap_call = saved

@test
def t_a_service_code_outside_the_enum_is_refused_before_the_charge():
    # Booking's ServiceTypeCode is typed to wsServiceTypes. A code outside it cannot
    # be booked, and finding that out from WCF costs a round trip against real money.
    reset_dispatch(); reset_prod()
    called = {"n": 0}
    async def counting(service, action, inner, retryable=True):
        called["n"] += 1
        return ET.fromstring(BOOK_XML if service == "ShipmentService" else RATE_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = counting
    try:
        r = post("/api/dispatch/book", {"order_id": 12345, "box": BOX,
                                        "option": {"service_type_code": "11", "amount": 7.31,
                                                   "carrier_name": "UPS", "service_name": "Standard"}})
        eq(r.status_code, 400, r.text)
        ok(r.json().get("error"), "refused: " + json.dumps(r.json())[:200])
        ok("does not recognise" in r.json()["error"], "says why")
        eq(called["n"], 0, "nothing was sent to World Options")
    finally:
        worldoptions._soap_call = saved

@test
def t_every_bookable_service_maps_to_a_carrier_with_a_readable_name():
    # 145 of the 146 wsServiceTypes members carry their carrier as a prefix; ALL is
    # the exception and means "any carrier", never an answer to who is carrying it.
    eq(len(worldoptions.SERVICE_TYPES_ENUM), 146, "the whole enum is present")
    for code in worldoptions.SERVICE_TYPES_ENUM:
        if code == "ALL":
            continue
        cr = worldoptions.SERVICE_CARRIER[worldoptions._squash(code)]
        ok(cr, code + " resolves to a carrier")
        shown = worldoptions.carrier_display(cr)
        ok(shown and shown != cr.upper() or cr in ("UPS", "DHL", "TNT", "DPD", "DSV"),
           code + " reads as " + repr(shown) + ", not the raw enum " + cr)
    eq(worldoptions.canonical_carrier("ALL"), "", "ALL is never a carrier answer")

@test
def t_a_broken_dispatch_store_stops_the_booking_rather_than_double_charging():
    reset_dispatch(); reset_prod()
    with open(os.environ["DISPATCH_STATE_PATH"], "w", encoding="utf-8") as fh:
        fh.write("{not json at all")
    copilot._poisoned_stores.discard(os.environ["DISPATCH_STATE_PATH"])
    called = {"n": 0}
    async def counting(service, action, inner, retryable=True):
        called["n"] += 1
        return ET.fromstring(BOOK_XML if service == "ShipmentService" else RATE_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = counting
    try:
        r = post("/api/dispatch/book", {"order_id": 12345, "box": BOX, "option": OPT})
        eq(r.status_code, 400, r.text)
        ok(r.json().get("error"), "refused rather than risk a second charge")
        eq(called["n"], 0, "nothing was booked")
    finally:
        worldoptions._soap_call = saved
        copilot._poisoned_stores.discard(os.environ["DISPATCH_STATE_PATH"])
        reset_dispatch()

@test
def t_a_carrier_that_cannot_be_booked_by_name_is_still_named():
    # UKMail runs 13 services but is not a wsServiceCompanyTypes member, so the
    # request may never name it. That must not mean the merchant and the customer
    # are told nothing about who has the parcel.
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner
        return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        addr = {"name": "A", "street": "1 St", "city": "M", "postcode": "M1 1AA",
                "country": "GB", "phone": "1", "email": "a@b.c"}
        r = run(worldoptions.book({"service_type_code": "UKMail_Express_UK"}, addr, addr,
                                  [{"width": 10, "length": 10, "depth": 10, "weight": 1}]))
        ok("<sd:ServiceType>" not in holder["xml"], "an unbookable carrier is not sent")
        eq(r["carrier_name"], "", "nothing invalid is claimed as the booking carrier")
        eq(r["carrier_known"], "UKMAIL", "but we still know who has it")
        eq(r["carrier_label"], "UKMail", "and the merchant reads a real name")
        eq(worldoptions.shopify_carrier(r["carrier_known"]), "UK Mail",
           "and the customer's email names a real company")
    finally:
        worldoptions._soap_call = saved

@test
def t_a_company_name_is_never_invented_for_a_customer_email():
    eq(worldoptions.shopify_carrier(""), "", "no carrier, no company")
    eq(worldoptions.shopify_carrier("SOMETHING_NEW"), "", "an unknown code is not a company")
    eq(worldoptions.shopify_carrier("GLOBALTRANZ"), "GlobalTranz", "a known one is spelled properly")

# The saved WSDL is the contract's ground truth: two tests walk it directly so a
# schema change surfaces as a failing test, not a failed booking.
XSD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "wsdl") + os.sep

def _xsd_sequence(tname):
    import glob
    for f in glob.glob(XSD_DIR + "wo_xsd*.xml"):
        s = open(f, encoding="utf-8").read()
        m = re.search(r'<xs:complexType name="%s">(.*?)</xs:complexType>' % re.escape(tname), s, re.S)
        if m:
            return [re.search(r'name="([^"]+)"', e).group(1)
                    for e in re.findall(r"<xs:element[^>]*/>", m.group(1))]
    return []

@test
def t_booking_envelope_matches_the_schema_sequence():
    # WCF's DataContractSerializer requires the declared order. This walks the real
    # XSDs rather than a copy of them, so a hand-edited envelope cannot drift.
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner
        return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        addr = {"name": "A", "company": "C", "street": "1 St", "city": "M",
                "postcode": "M1 1AA", "country": "GB", "phone": "1", "email": "a@b.c"}
        run(worldoptions.book({"service_type_code": "UPS_Standard",
                               "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
                              addr, addr, [{"width": 20, "length": 15, "depth": 8, "weight": 0.5}]))
        x = holder["xml"]
        for block, prefix, tname in [("RecipientsDetails", "m", "wsRecipient"),
                                     ("SendersDetails", "m", "wsSender"),
                                     ("ShippingDetail", "sd", "wsShippingDetail")]:
            order = _xsd_sequence(tname)
            ok(order, "found " + tname + " in the XSDs")
            body = re.search(r"<wo:%s>(.*?)</wo:%s>" % (block, block), x, re.S)
            ok(body, "envelope carries " + block)
            # Flatten out nested types (each parcel, each drop-off shop): their
            # children belong to their own complexType, not this sequence.
            flat = re.sub(r"<sd:wsShippingDetail\.\w+>.*?</sd:wsShippingDetail\.\w+>", "",
                          body.group(1), flags=re.S)
            flat = re.sub(r"<sd:(CollectionDropOffInfo|DeliveryDropOffInfo)>.*?</sd:\1>", "",
                          flat, flags=re.S)
            got = re.findall(r"<%s:(\w+)>" % prefix, flat)
            unknown = [g for g in got if g not in order]
            eq(unknown, [], block + " sends only elements the schema declares")
            idx = [order.index(g) for g in got if g in order]
            eq(idx, sorted(idx), block + " is in schema sequence order")
    finally:
        worldoptions._soap_call = saved

@test
def t_nothing_the_service_reads_as_text_arrives_null():
    # "Value cannot be null. Parameter name: input" is what .NET throws when a null
    # string reaches a parse or regex helper. A UK consumer address has no county
    # and no company, so those fields were absent and therefore null.
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner
        return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        bare = {"name": "Jo", "street": "10 Nethercote Ave", "city": "Manchester",
                "postcode": "M23 1LL", "country": "GB", "phone": "07000", "email": "jo@x.co"}
        run(worldoptions.book({"service_type_code": "UPS_Standard",
                               "package_type_code": "Any_NonDocument", "carrier_name": "UPS"},
                              bare, bare, [{"width": 20, "length": 15, "depth": 8, "weight": 0.5}]))
        x = holder["xml"]
        for el in ("Company", "State_Code", "State", "CustomerReference", "Description",
                   "LabelDeliveryMethod", "NumberOfPiecesOnAllPallets", "SenderVatNo"):
            ok(re.search(r"<(?:m|sd):%s>" % el, x), el + " is sent, not omitted into a null")
        # A rate-only package type must not fall through to the enum's first member.
        eq(re.findall(r"<sd:PackageTypeCode>([^<]*)<", x), ["UPS_My_Packaging"],
           "the carrier's own packaging, not Fedex_Box by default")
    finally:
        worldoptions._soap_call = saved

@test
def t_a_rejected_booking_logs_its_envelope_without_credentials():
    x = ("<m:Key>secret-key</m:Key><m:Password>hunter2</m:Password>"
         "<m:MeterNumber>1239999</m:MeterNumber><sd:City>Leeds</sd:City>")
    red = worldoptions._redacted(x)
    for bad in ("secret-key", "hunter2", "1239999"):
        ok(bad not in red, bad + " is not in the log")
    # City is redacted too now: with the address lines it completes a customer's
    # location in a file that outlives the failure. The SHAPE survives, which is
    # what the panel is read for.
    ok("<sd:City>" in red, "the element survives so the shape can be read")
    ok("Leeds" not in red, "but the value does not")

def _xsd_nillable_strings(tname):
    import glob
    for f in glob.glob(XSD_DIR + "wo_xsd*.xml"):
        s = open(f, encoding="utf-8").read()
        m = re.search(r'<xs:complexType name="%s">(.*?)</xs:complexType>' % re.escape(tname), s, re.S)
        if m:
            return [re.search(r'name="([^"]+)"', e).group(1)
                    for e in re.findall(r"<xs:element[^>]*/>", m.group(1))
                    if 'nillable="true"' in e and "xs:string" in e]
    return []

@test
def t_no_nillable_string_reaches_the_service_as_null():
    # In WCF an omitted nillable string deserializes to null, and their code runs
    # string work on it: that is what "Value cannot be null. Parameter name: input"
    # was. Driven off the real XSDs so a new field in a future WSDL shows up here
    # rather than as a failed booking. Date and account-number fields are listed as
    # deliberate exceptions: "" would fail a parse that a null is likelier to skip.
    # ReadyDate proved the rule live: "" fails their dd/MM/yyyy format check while
    # an absent optional member passes. Format-shaped fields are real or absent.
    OMIT_ON_PURPOSE = {"ReadyDate", "DutiesAccNumber", "TransportationAccNumber"}
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner
        return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        # The shape that produced the live failure: a UK consumer, no county,
        # no company, no insurance, with a collection window set.
        bare = {"name": "Jo", "street": "10 Nethercote Ave", "city": "Manchester",
                "postcode": "M23 1LL", "country": "GB", "phone": "07000", "email": "jo@x.co"}
        run(worldoptions.book({"service_type_code": "UPS_Standard",
                               "package_type_code": "Any_NonDocument", "carrier_name": "UPS"},
                              bare, bare, [{"width": 20, "length": 15, "depth": 8, "weight": 0.5}],
                              ready_time="14:00", close_time="17:30"))
        x = holder["xml"]
        for block, prefix, tname in [("RecipientsDetails", "m", "wsRecipient"),
                                     ("SendersDetails", "m", "wsSender"),
                                     ("ShippingDetail", "sd", "wsShippingDetail"),
                                     ("BillingDetail", "wo", "wsBillingDetail")]:
            body = re.search(r"<wo:%s>(.*?)</wo:%s>" % (block, block), x, re.S)
            ok(body, block + " is in the envelope")
            for el in _xsd_nillable_strings(tname):
                if el in OMIT_ON_PURPOSE:
                    continue
                ok(re.search(r"<%s:%s>" % (prefix, el), body.group(1)),
                   block + "." + el + " is sent, so it cannot arrive as null")
    finally:
        worldoptions._soap_call = saved

@test
def t_the_merchant_pays_for_the_carriage_not_the_customer():
    # TransportationPayorTypes begins with Bill_To_Receiver, so saying nothing bills
    # the CUSTOMER for the shipping. It is stated explicitly on every booking.
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner
        return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        a = {"name": "A", "street": "1 St", "city": "M", "postcode": "M1 1AA",
             "country": "GB", "phone": "1", "email": "a@b.c"}
        for kw in ({}, {"ready_time": "14:00", "close_time": "17:30"}):
            run(worldoptions.book({"service_type_code": "UPS_Standard",
                                   "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
                                  a, a, [{"width": 1, "length": 1, "depth": 1, "weight": 1}], **kw))
            ok("<wo:TransportationPayor>Bill_To_Sender</wo:TransportationPayor>" in holder["xml"],
               "the merchant's account pays, collection window set: " + str(bool(kw)))
    finally:
        worldoptions._soap_call = saved

@test
def t_a_booking_without_a_service_or_packaging_is_refused():
    called = {"n": 0}
    async def counting(service, action, inner, retryable=True):
        called["n"] += 1
        return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = counting
    try:
        a = {"name": "A", "street": "1 St", "city": "M", "postcode": "M1 1AA",
             "country": "GB", "phone": "1", "email": "a@b.c"}
        box = [{"width": 1, "length": 1, "depth": 1, "weight": 1}]
        # No service at all: WCF would have taken the enum's first member.
        try:
            run(worldoptions.book({}, a, a, box)); ok(False, "empty service code refused")
        except worldoptions.WorldOptionsError as e:
            ok("No courier service was chosen" in str(e), "says what is wrong: " + str(e)[:60])
        eq(called["n"], 0, "nothing reached World Options")
    finally:
        worldoptions._soap_call = saved

@test
def t_every_bookable_carrier_has_packaging_we_can_name():
    # PackageTypeCode is a non-nillable enum whose first member is Fedex_Box, so an
    # unnamed packaging is not "unset", it is FedEx packaging on someone else's
    # booking. book() refuses rather than let that happen; this proves the refusal
    # is a backstop and not something the merchant can actually hit.
    carriers = {worldoptions.SERVICE_CARRIER[worldoptions._squash(s)]
                for s in worldoptions.SERVICE_TYPES_ENUM if s != "ALL"}
    for cr in sorted(carriers):
        pkg = worldoptions.CARRIER_PACKAGE_TYPE.get(cr.upper())
        ok(pkg, cr + " has packaging mapped")
        ok(pkg in worldoptions.PACKAGE_TYPES_ENUM, cr + " maps to a real wsPackageTypes member: " + str(pkg))

@test
def t_the_failure_log_hides_the_customer_not_the_shape():
    x = ('<m:Email>jo@x.co</m:Email><m:Phone>07000</m:Phone><m:Address1>10 Nethercote</m:Address1>'
         '<m:Company></m:Company><m:Key>k</m:Key><sd:City>Manchester</sd:City>')
    red = worldoptions._redacted(x)
    for bad in ("jo@x.co", "07000", "10 Nethercote", ">k<"):
        ok(bad not in red, repr(bad) + " is not in the log")
    ok("<m:Company></m:Company>" in red, "an EMPTY field still reads as empty, which is the point")
    ok("<m:Email>***</m:Email>" in red, "a filled field reads as filled")

@test
def t_a_rejected_booking_hands_back_the_evidence():
    # The whole point: a failure must be readable at the dispatch desk, not only in
    # a server log somebody else has to go and find.
    reset_dispatch(); reset_prod()
    async def refuse(service, action, inner, retryable=True):
        if service == "ShipmentService":
            raise worldoptions.WorldOptionsError(
                "Value cannot be null.\r\nParameter name: input",
                raw="Value cannot be null.\r\nParameter name: input")
        return ET.fromstring(RATE_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = refuse
    try:
        r = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
        body = r.json()
        ok(body.get("error"), "the failure is reported")
        tech = body.get("tech") or {}
        ok(tech.get("reply"), "their exact words come back, for World Options support")
        ok("Parameter name: input" in tech["reply"], "verbatim, not paraphrased")
        ok(tech.get("request"), "and the request that caused it")
        ok("<sd:ServiceTypeCode>" in tech["request"], "the request is the real envelope")
        eq(tech.get("order"), "12345", "tied to the order")
        ok(tech.get("when"), "and timestamped")
        # Nothing private in what we hand over.
        for bad in ("testsecret", "shpat_"):
            ok(bad not in json.dumps(tech), bad + " is not in the detail")
        # And it survives the window being closed.
        rows = copilot._load_wo_failures()
        eq(len(rows), 1, "kept on disk")
        eq(rows[0]["order"], "12345", "the stored copy is the same failure")
    finally:
        worldoptions._soap_call = saved

@test
def t_the_booking_auth_block_sends_its_optional_strings_but_the_quote_is_untouched():
    # Quoting demonstrably works, so its envelope is left exactly as it is.
    # ShipmentService is different code and may read fields RateService never does.
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder[service] = inner
        return ET.fromstring(BOOK_XML if service == "ShipmentService" else RATE_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        a = {"name": "A", "street": "1 St", "city": "M", "postcode": "M1 1AA",
             "country": "GB", "phone": "1", "email": "a@b.c"}
        box = [{"width": 1, "length": 1, "depth": 1, "weight": 1}]
        run(worldoptions.quote(a, a, box))
        run(worldoptions.book({"service_type_code": "UPS_Standard",
                               "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
                              a, a, box))
        for el in ("SubUserKey", "WebLeadCompanyName", "WebLeadPostalCode"):
            ok("<m:%s>" % el in holder["ShipmentService"], el + " is sent when booking")
            ok("<m:%s>" % el not in holder["RateService"], el + " is NOT added to the quote")
    finally:
        worldoptions._soap_call = saved

@test
def t_a_signature_literal_never_crosses_carriers():
    # wsSignatureTypes has no no-signature member for UPS at all. Sending FedEx's on
    # a UPS booking is what produced "Value cannot be null. Parameter name: input":
    # their service looks up its own mapping, finds nothing, and throws.
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner
        return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        a = {"name": "A", "street": "1 St", "city": "M", "postcode": "M1 1AA",
             "country": "GB", "phone": "1", "email": "a@b.c"}
        box = [{"width": 1, "length": 1, "depth": 1, "weight": 1}]
        # UPS has no equivalent: the setting is dropped, not translated.
        run(worldoptions.book({"service_type_code": "UPS_Standard",
                               "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
                              a, a, box, signature="Fedex_No_Signature_Required"))
        ok("Fedex_" not in holder["xml"], "no FedEx literal rides on a UPS booking")
        ok("<wo:DeliverySignatureType>" not in holder["xml"], "and nothing invalid is invented")
        # DHL does have one: the intent survives in DHL's own wording.
        run(worldoptions.book({"service_type_code": "DHL_DOMESTIC_EXPRESS",
                               "package_type_code": "DHL_NonDocument", "carrier_name": "DHL"},
                              a, a, box, signature="Fedex_No_Signature_Required"))
        ok("<wo:DeliverySignatureType>DHL_No_Signature_Required</wo:DeliverySignatureType>"
           in holder["xml"], "translated into the booked carrier's own literal")
    finally:
        worldoptions._soap_call = saved

@test
def t_no_signature_is_only_offered_where_it_can_be_bought():
    # Every carrier gets cheaper prices in the no-signature sweep, but only FedEx
    # and DHL can actually be booked without one. Offering the rest is a saving
    # that vanishes at the till, or a booking that fails.
    for code in worldoptions.NO_SIGNATURE_BY_CARRIER:
        ok(worldoptions.NO_SIGNATURE_BY_CARRIER[code] in worldoptions.SIGNATURE_OPTIONS[code],
           code + "'s no-signature literal is one of its own options")
    eq(worldoptions.NO_SIGNATURE_BY_CARRIER.get("UPS"), None, "UPS has none, and none is invented")
    reset_dispatch(); reset_prod()
    r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
    for o in r.json()["options"]:
        if o.get("no_signature"):
            ok(o["carrier_name"] in worldoptions.NO_SIGNATURE_BY_CARRIER,
               "offered only for " + o["carrier_name"] + ", which can be booked that way")

@test
def t_ready_from_is_never_in_the_past():
    # "Invalid Date, Parcel Ready From": the settings window is a preference, not
    # the answer. Booking after the window opens must roll the time forward, and
    # booking after close (or on a weekend) must roll to the next working day.
    from datetime import datetime as dt
    from zoneinfo import ZoneInfo
    L = ZoneInfo("Europe/London")
    cfg = {"ready_time": "14:00", "close_time": "17:30"}
    eq(copilot._collection_ready(cfg, dt(2026, 8, 12, 10, 0, tzinfo=L)),
       ("12/08/2026", "14:00"), "before the window: the window stands")
    eq(copilot._collection_ready(cfg, dt(2026, 8, 12, 15, 20, tzinfo=L)),
       ("12/08/2026", "16:00"), "past the window start: rolled forward, still today")
    eq(copilot._collection_ready(cfg, dt(2026, 8, 12, 18, 0, tzinfo=L)),
       ("13/08/2026", "14:00"), "after close: next day")
    eq(copilot._collection_ready(cfg, dt(2026, 8, 14, 17, 45, tzinfo=L)),
       ("17/08/2026", "14:00"), "friday evening: monday, not saturday")
    eq(copilot._collection_ready(cfg, dt(2026, 8, 15, 11, 0, tzinfo=L)),
       ("17/08/2026", "14:00"), "saturday: monday")
    d, t = copilot._collection_ready({}, dt(2026, 8, 12, 15, 20, tzinfo=L))
    eq((d, t), ("12/08/2026", "16:00"), "no window configured still yields a sane future slot")

BOOK_URL_XML = BOOK_XML.replace(
    "<ShippingLabel><Image>JVBERi0xLjQK</Image><ImageLength>10</ImageLength><IsThermalPrint>false</IsThermalPrint><LabelType>PDF</LabelType><LabelURL/></ShippingLabel>",
    "<ShippingLabel><Image/><ImageLength>0</ImageLength><IsThermalPrint>false</IsThermalPrint><LabelType/><LabelURL>/GetLabel.ashx?id=42</LabelURL></ShippingLabel>")

@test
def t_a_label_link_is_downloaded_into_a_file_at_booking():
    # Their LabelURL can be relative. Opened from inside the admin it resolves
    # against THIS app and shows our 404 ("Not Found"), so the server downloads
    # the file once and stores the bytes instead of the link.
    reset_dispatch(); reset_prod()
    async def cap(service, action, inner, retryable=True):
        return ET.fromstring(BOOK_URL_XML if service == "ShipmentService" else RATE_XML)
    async def fake_fetch(url):
        eq(url, "/GetLabel.ashx?id=42", "handed the link as WO sent it")
        return {"type": "base64pdf", "value": "JVBERi0xLjQK", "label_type": "PDF",
                "source_url": "https://service.worldoptions.co.uk/GetLabel.ashx?id=42"}
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    saved_fetch = worldoptions.fetch_label; worldoptions.fetch_label = fake_fetch
    try:
        r = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
        eq(r.status_code, 200, r.text)
        lbls = r.json()["dispatch"].get("labels") or r.json().get("labels") or []
        stored = copilot._load_dispatch_labels(12345)
        eq(stored[0]["type"], "base64pdf", "stored as the FILE, not the link: " + str(stored[0].get("type")))
    finally:
        worldoptions._soap_call = saved; worldoptions.fetch_label = saved_fetch

@test
def t_a_stored_link_label_heals_itself_on_reprint():
    # The order booked BEFORE this fix has a dead link on disk. Opening its label
    # downloads the real file and saves it back.
    reset_dispatch(); reset_prod()
    copilot._save_dispatch_labels(777, [{"type": "url", "value": "/GetLabel.ashx?id=9"}])
    async def fake_fetch(url):
        return {"type": "base64pdf", "value": "JVBERi0xLjQK", "label_type": "PDF"}
    saved_fetch = worldoptions.fetch_label; worldoptions.fetch_label = fake_fetch
    try:
        r = post("/api/dispatch/label", {"order_id": 777})
        eq(r.status_code, 200, r.text)
        eq(r.json()["labels"][0]["type"], "base64pdf", "served as a file")
        eq(copilot._load_dispatch_labels(777)[0]["type"], "base64pdf", "and healed on disk")
    finally:
        worldoptions.fetch_label = saved_fetch

@test
def t_an_unfetchable_link_is_kept_not_lost():
    reset_dispatch(); reset_prod()
    copilot._save_dispatch_labels(778, [{"type": "url", "value": "/GetLabel.ashx?id=9"}])
    async def dead_fetch(url):
        return {}
    saved_fetch = worldoptions.fetch_label; worldoptions.fetch_label = dead_fetch
    try:
        r = post("/api/dispatch/label", {"order_id": 778})
        eq(r.json()["labels"][0]["type"], "url", "the link survives when the download fails")
    finally:
        worldoptions.fetch_label = saved_fetch

@test
def t_label_urls_only_fetch_from_world_options():
    eq(worldoptions._label_url("https://evil.example.com/a.pdf"), "", "foreign hosts refused")
    ok(worldoptions._label_url("/x.pdf").startswith("https://service.worldoptions.co.uk/"),
       "relative links resolve against their service host")
    eq(worldoptions._label_from_bytes(b"<html>Not Found</html>"), {},
       "an HTML error page is never saved as a label")

@test
def t_pdf_labels_gain_print_images():
    # A REAL one-page PDF made on the spot: the truncated fixture bytes would only
    # prove the failure path.
    import base64 as b64, io
    import pypdfium2
    doc = pypdfium2.PdfDocument.new(); doc.new_page(288, 432)
    buf = io.BytesIO(); doc.save(buf)
    real_pdf = b64.b64encode(buf.getvalue()).decode()
    out = copilot._with_print_images([{"type": "base64pdf", "value": real_pdf}])
    imgs = out[0].get("print_images") or []
    eq(len(imgs), 1, "one page, one image")
    ok(b64.b64decode(imgs[0]).startswith(b"\x89PNG"), "a real PNG")
    # Broken bytes degrade to no images, never an error: Download still works.
    out2 = copilot._with_print_images([{"type": "base64pdf", "value": "JVBERi0xLjQK"}])
    eq(out2[0].get("print_images"), None, "unrenderable PDF stays downloadable")

@test
def t_reprint_attaches_print_images_and_saves_them():
    import base64 as b64, io
    import pypdfium2
    doc = pypdfium2.PdfDocument.new(); doc.new_page(288, 432)
    buf = io.BytesIO(); doc.save(buf)
    real_pdf = b64.b64encode(buf.getvalue()).decode()
    reset_dispatch(); reset_prod()
    copilot._save_dispatch_labels(779, [{"type": "base64pdf", "value": real_pdf}])
    r = post("/api/dispatch/label", {"order_id": 779})
    eq(r.status_code, 200, r.text)
    ok(r.json()["labels"][0].get("print_images"), "images served for printing")
    ok(copilot._load_dispatch_labels(779)[0].get("print_images"), "and saved back")

@test
def t_customs_lines_carry_the_cost_price_and_the_products_own_hs_code():
    # The user's example: a 200 watt projector, cost 425.00, HS 9008.50.00. Both
    # live on the variant's INVENTORY ITEM in Shopify, and customs declares what
    # the goods are worth to the merchant, not what the customer paid.
    reset_dispatch(); reset_prod()
    order = {"id": 12345, "name": "#12345", "currency": "GBP", "email": "c@x.co",
             "total_price": "780.00",
             "shipping_address": {"first_name": "A", "last_name": "B", "address1": "1 Rue",
                                  "city": "Paris", "zip": "75001", "country_code": "FR",
                                  "phone": "0033", "name": "A B"},
             "line_items": [
                 {"id": 1, "title": "Projected Image 200 Watt Gobo Projector", "quantity": 1, "price": "780.00",
                  "variant_id": 111},
                 {"id": 2, "title": "Custom Gobo", "quantity": 2, "price": "45.00",
                  "variant_id": None},
             ]}
    async def tools(registry, name, args):
        if name == "shopify_get_order":
            return order
        if name == "shopify_get_variant":
            eq(args["variant_id"], 111, "only the real variant is looked up")
            return {"id": 111, "inventory_item_id": 9001}
        if name == "shopify_get_inventory_items":
            eq(args["ids"], "9001", "batched by inventory item id")
            return {"inventory_items": [{"id": 9001, "cost": "425.00",
                                         "harmonized_system_code": "9008.50.00",
                                         "country_code_of_origin": "GB"}]}
        return {}
    saved = copilot._tool_json; copilot._tool_json = tools
    try:
        r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
        eq(r.status_code, 200, r.text)
        body = r.json()
        ok(body.get("international"), "France is international")
        items = body.get("customs_items") or []
        eq(len(items), 2, "every real line is present")
        proj = items[0]
        eq(proj["cost"], "425.00", "the COST price, not the 780.00 sale price")
        eq(proj["hs_code"], "9008.50.00", "the product's own HS code")
        eq(proj["origin"], "GB", "origin from Shopify")
        gobo = items[1]
        eq(gobo["cost"], "", "no variant -> no cost")
        # The house value rules: gobos are custom work declared at SALE value
        # (no missing-cost warning for them); stocked goods at COST.
        eq(gobo["unit_value"], "45.00", "a gobo is declared at its sale price")
        eq(gobo["value_basis"], "sale", "and that is by design")
        eq(gobo["needs_cost"], False, "so no missing-cost nag for a gobo")
        eq(gobo["hs_code"], "9002.20.000", "every gobo is 9002.20.000")
        eq(proj["unit_value"], "425.00", "a projector is declared at cost")
        eq(proj["value_basis"], "cost", "explicitly")
        # Origin rules: Shopify's own value wins (the projector's inventory item
        # says GB here); with nothing in Shopify, the merchant's blanket rule
        # applies: projectors are made in China, gobos (everything else) in the UK.
        eq(proj["origin"], "GB", "Shopify origin wins when set")
        eq(gobo["origin"], "GB", "a gobo with no Shopify origin is UK")
    finally:
        copilot._tool_json = saved

@test
def t_domestic_quotes_do_not_pay_for_customs_lookups():
    reset_dispatch(); reset_prod()
    called = []
    real = copilot._tool_json
    async def spy(registry, name, args):
        called.append(name)
        return await real(registry, name, args)
    copilot._tool_json = spy
    try:
        r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
        eq(r.status_code, 200, r.text)
        eq(r.json().get("customs_items"), [], "no customs payload on a GB order")
        ok("shopify_get_variant" not in called, "no variant reads for a domestic parcel")
    finally:
        copilot._tool_json = real

@test
def t_every_tool_the_customs_lookup_uses_is_registered():
    # _tool_json swallows a missing registry entry into {"_failed": True}, so a
    # tool that exists in server.py but not in COPILOT_TOOLS fails SILENTLY and
    # the customs card quietly falls back to sale prices. Pin the registration.
    for name in ("shopify_get_order", "shopify_get_variant", "shopify_get_inventory_items"):
        ok(name in server.COPILOT_TOOLS, name + " is in the registry copilot actually uses")

@test
def t_projectors_default_to_china_when_shopify_has_no_origin():
    reset_dispatch(); reset_prod()
    order = {"id": 12345, "name": "#12345", "currency": "GBP", "email": "c@x.co",
             "shipping_address": {"first_name": "A", "last_name": "B", "address1": "1 Rue",
                                  "city": "Paris", "zip": "75001", "country_code": "FR",
                                  "phone": "0033", "name": "A B"},
             "line_items": [
                 {"id": 1, "title": "Projected Image 200 Watt LED Gobo Projector", "quantity": 1,
                  "price": "780.00", "variant_id": 111},
                 {"id": 2, "title": "Wedding Gobo 16", "quantity": 1,
                  "price": "45.00", "variant_id": 222},
             ]}
    async def tools(registry, name, args):
        if name == "shopify_get_order":
            return order
        if name == "shopify_get_variant":
            return {"id": args["variant_id"], "inventory_item_id": 9000 + args["variant_id"]}
        if name == "shopify_get_inventory_items":
            # Shopify knows the cost but NOT the origin for either product.
            return {"inventory_items": [
                {"id": 9111, "cost": "425.00", "harmonized_system_code": "9008.50.00"},
                {"id": 9222, "cost": "12.00", "harmonized_system_code": ""},
            ]}
        return {}
    saved = copilot._tool_json; copilot._tool_json = tools
    try:
        r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
        items = r.json().get("customs_items") or []
        eq(items[0]["origin"], "CN", "a projector with no Shopify origin is China")
        eq(items[1]["origin"], "GB", "a gobo with no Shopify origin is the UK")
        # A stocked product with no cost is the ONLY missing-cost flag.
        eq(items[0]["needs_cost"], False, "projector has a cost, no flag")
        eq(items[1]["needs_cost"], False, "gobo declares sale value by design, no flag")
        eq(items[1]["hs_code"], "9002.20.000", "gobo HS filled even with none in Shopify")
    finally:
        copilot._tool_json = saved

@test
def t_gobo_projectors_are_projectors_not_gobos():
    # The regression the merchant caught live: projector products are NAMED
    # "Projected Image ... Gobo Projector", so a naive "contains gobo" rule
    # declared every projector at sale value. Projector wins the classification.
    reset_dispatch(); reset_prod()
    order = {"id": 12345, "name": "#12345", "currency": "GBP", "email": "c@x.co",
             "shipping_address": {"first_name": "A", "last_name": "B", "address1": "1 Rue",
                                  "city": "Paris", "zip": "75001", "country_code": "FR",
                                  "phone": "0033", "name": "A B"},
             "line_items": [
                 {"id": 1, "title": "Projected Image 200 Watt Gobo Projector",
                  "quantity": 1, "price": "780.00", "variant_id": 111},
             ]}
    async def tools(registry, name, args):
        if name == "shopify_get_order":
            return order
        if name == "shopify_get_variant":
            return {"id": 111, "inventory_item_id": 9111}
        if name == "shopify_get_inventory_items":
            return {"inventory_items": [{"id": 9111, "cost": "425.00",
                                         "harmonized_system_code": "9008.50.00"}]}
        return {}
    saved = copilot._tool_json; copilot._tool_json = tools
    try:
        r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
        it = (r.json().get("customs_items") or [])[0]
        eq(it["unit_value"], "425.00", "COST, despite the word Gobo in the name")
        eq(it["value_basis"], "cost", "classified as a stocked product")
        eq(it["hs_code"], "9008.50.00", "its own HS code, not the gobo blanket")
        eq(it["origin"], "CN", "projector origin rule still applies")
    finally:
        copilot._tool_json = saved

@test
def t_shopify_address_lines_stay_separate_and_within_the_courier_cap():
    # Order 104240: "Momentum Logistics Park" and "Unit 1 Ash Drive" arrived as
    # separate Shopify lines and were being merged into one over-long Address1.
    # Couriers cap each line at 35 characters.
    eq(worldoptions._address_lines("Momentum Logistics Park", "Unit 1 Ash Drive"),
       ("Momentum Logistics Park", "Unit 1 Ash Drive", ""),
       "two clean lines pass through untouched")
    a1, a2, a3 = worldoptions._address_lines("Unit 1 Ash Drive Momentum Logistics Park", "")
    ok(all(len(x) <= 35 for x in (a1, a2, a3)), "an over-long single line wraps within the cap")
    eq((a1 + " " + a2).strip(), "Unit 1 Ash Drive Momentum Logistics Park", "no words lost")
    # And it reaches the envelope as three real elements.
    holder = {}
    async def cap_call(service, action, inner, retryable=True):
        holder["xml"] = inner
        return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap_call
    try:
        d = {"name": "A", "street": "Momentum Logistics Park", "street2": "Unit 1 Ash Drive",
             "city": "Washington", "postcode": "NE38 0LT", "country": "GB",
             "phone": "1", "email": "a@b.c"}
        run(worldoptions.book({"service_type_code": "UPS_Standard",
                               "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
                              d, d, [{"width": 1, "length": 1, "depth": 1, "weight": 1}]))
        x = holder["xml"]
        ok("<m:Address1>Momentum Logistics Park</m:Address1>" in x, "line one intact")
        ok("<m:Address2>Unit 1 Ash Drive</m:Address2>" in x, "line two intact, NOT merged")
    finally:
        worldoptions._soap_call = saved

@test
def t_ship_to_carries_both_shopify_lines():
    shaped = copilot._ship_to({"shipping_address": {
        "address1": "Momentum Logistics Park", "address2": "Unit 1 Ash Drive",
        "city": "Washington", "zip": "NE38 0LT", "country_code": "GB", "name": "A B"}})
    eq(shaped["street"], "Momentum Logistics Park", "line one")
    eq(shaped["street2"], "Unit 1 Ash Drive", "line two, separate")

@test
def t_a_failed_reply_still_carries_the_envelope():
    # "Could not create SSL/TLS secure channel" came back as a FAILED reply, and
    # the panel claimed the request was never sent. It was: their server answered.
    reset_dispatch(); reset_prod()
    FAILED_BOOK = """<Envelope><Body><DoShipmentResponse><DoShipmentResult>
     <Message>The request was aborted: Could not create SSL/TLS secure channel.*|**|*1</Message>
     <NotificationtType>FAILED</NotificationtType>
    </DoShipmentResult></DoShipmentResponse></Body></Envelope>"""
    async def failing(service, action, inner, retryable=True):
        return ET.fromstring(FAILED_BOOK if service == "ShipmentService" else RATE_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = failing
    try:
        r = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
        body = r.json()
        ok(body.get("error"), "the failure is reported")
        tech = body.get("tech") or {}
        ok("SSL/TLS" in (tech.get("reply") or ""), "their words verbatim")
        ok(tech.get("request"), "the envelope IS captured for an answered failure")
        eq(tech.get("sent"), True, "and it says the request was sent")
    finally:
        worldoptions._soap_call = saved

@test
def t_a_transient_failed_reply_is_retried_exactly_once():
    reset_dispatch(); reset_prod()
    copilot.WO_RETRY_WAIT_SECS = 0          # no real sleeping in tests
    SSL_FAIL = """<Envelope><Body><DoShipmentResponse><DoShipmentResult>
     <Message>The request was aborted: Could not create SSL/TLS secure channel.*|**|*1</Message>
     <NotificationtType>FAILED</NotificationtType>
    </DoShipmentResult></DoShipmentResponse></Body></Envelope>"""
    calls = {"n": 0}
    async def flaky(service, action, inner, retryable=True):
        if service != "ShipmentService":
            return ET.fromstring(RATE_XML)
        calls["n"] += 1
        return ET.fromstring(SSL_FAIL if calls["n"] == 1 else BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = flaky
    try:
        r = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
        eq(r.status_code, 200, r.text)
        ok(r.json().get("dispatch", {}).get("tracking_number") or r.json().get("tracking_number"),
           "second attempt booked: " + r.text[:120])
        eq(calls["n"], 2, "exactly one retry")
    finally:
        worldoptions._soap_call = saved

@test
def t_a_validation_failure_is_never_retried():
    reset_dispatch(); reset_prod()
    copilot.WO_RETRY_WAIT_SECS = 0
    VAL_FAIL = """<Envelope><Body><DoShipmentResponse><DoShipmentResult>
     <Message>Ready date should be in format - dd/MM/yyyy.</Message>
     <NotificationtType>FAILED</NotificationtType>
    </DoShipmentResult></DoShipmentResponse></Body></Envelope>"""
    calls = {"n": 0}
    async def refusing(service, action, inner, retryable=True):
        if service != "ShipmentService":
            return ET.fromstring(RATE_XML)
        calls["n"] += 1
        return ET.fromstring(VAL_FAIL)
    saved = worldoptions._soap_call; worldoptions._soap_call = refusing
    try:
        r = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
        ok(r.json().get("error"), "reported")
        eq(calls["n"], 1, "a deterministic refusal is not retried")
    finally:
        worldoptions._soap_call = saved

@test
def t_a_post_send_silence_is_never_retried():
    # The first attempt may have booked and charged; a retry could double-book.
    reset_dispatch(); reset_prod()
    copilot.WO_RETRY_WAIT_SECS = 0
    calls = {"n": 0}
    async def silent(service, action, inner, retryable=True):
        if service != "ShipmentService":
            return ET.fromstring(RATE_XML)
        calls["n"] += 1
        raise worldoptions.WorldOptionsError(
            "World Options did not reply in time. The shipment MAY still have been "
            "booked; check your World Options portal before trying again.")
    saved = worldoptions._soap_call; worldoptions._soap_call = silent
    try:
        r = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
        ok(r.json().get("error"), "reported")
        eq(calls["n"], 1, "NEVER retried when the outcome is unknown")
    finally:
        worldoptions._soap_call = saved

@test
def t_manifest_lists_the_days_bookings_with_margin():
    reset_dispatch(); reset_prod()
    # Book one (the mock order carries Standard Delivery shipping paid).
    r = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
    eq(r.status_code, 200, r.text)
    from datetime import datetime as dt
    from zoneinfo import ZoneInfo
    today = dt.now(ZoneInfo("Europe/London")).date().isoformat()
    m = post("/api/dispatch/manifest", {"date": today}).json()
    eq(len(m["rows"]), 1, "one booking today")
    row = m["rows"][0]
    ok(row["order_name"].startswith("#"), "order name stored with the entry: " + row["order_name"])
    ok(row["tracking"], "tracking present")
    eq(row["amount_ex_vat"], OPT.get("amount_ex_vat"), "ex VAT carried" if OPT.get("amount_ex_vat") else "no ex VAT on this option")
    eq(m["totals"]["shipments"], 1, "counted")
    # An empty day is an empty manifest, not an error.
    e = post("/api/dispatch/manifest", {"date": "2001-01-01"}).json()
    eq(e["rows"], [], "empty day")
    b = post("/api/dispatch/manifest", {"date": "nonsense"})
    eq(b.status_code, 400, "bad date refused plainly")

@test
def t_label_fetching_cannot_be_pointed_at_anything_but_world_options():
    # A URL that arrives in THEIR reply must never send this server fetching an
    # arbitrary address, including on a redirect.
    worldoptions.set_credentials(meter="1", key="k", password="p")
    for bad, why in [
        ("https://evil.example.com/x.pdf", "a foreign host"),
        ("https://service.worldoptions.co.uk@evil.com/x.pdf", "a userinfo trick"),
        ("http://169.254.169.254/latest/meta-data/", "cloud metadata"),
        ("https://127.0.0.1/x.pdf", "loopback"),
        ("file:///etc/passwd", "a file url"),
        ("https://10.0.0.5/x.pdf", "a private range"),
    ]:
        eq(worldoptions._label_url(bad), "", why + " is refused")
    ok(worldoptions._label_url("https://service.worldoptions.co.uk/a.pdf"), "their own host is allowed")
    eq(worldoptions._label_url("http://service.worldoptions.co.uk/a.pdf"),
       "https://service.worldoptions.co.uk/a.pdf", "http is upgraded, not trusted")
    ok(worldoptions._label_url("/x.pdf").startswith("https://service.worldoptions.co.uk/"),
       "a relative link resolves to their service host")

@test
def t_a_redirect_off_their_hosts_is_not_followed():
    # httpx's own follow_redirects would jump anywhere; every hop is re-validated.
    hops = []
    class FakeResp:
        def __init__(self, status, headers=None, content=b""):
            self.status_code = status; self.headers = headers or {}; self.content = content
    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url):
            hops.append(url)
            if "worldoptions" in url:
                return FakeResp(302, {"location": "http://169.254.169.254/latest/meta-data/"})
            return FakeResp(200, {}, b"SHOULD NEVER BE FETCHED")
    saved = worldoptions.httpx.AsyncClient
    worldoptions.httpx.AsyncClient = FakeClient
    try:
        status, body, final = run(worldoptions._get_label_bytes(
            "https://service.worldoptions.co.uk/a.pdf", 5.0))
        eq(body, b"", "nothing was fetched from the redirect target")
        eq(len(hops), 1, "the off-allowlist hop was never requested")
        ok("169.254" not in " ".join(hops), "metadata was never contacted")
    finally:
        worldoptions.httpx.AsyncClient = saved

@test
def t_an_oversized_label_is_refused_rather_than_rendered():
    eq(copilot._pdf_print_images("A" * 24_000_001), [], "a huge base64 blob is not decoded")

@test
def t_print_cors_credentials_go_only_to_this_shop():
    # Every Shopify merchant owns a *.myshopify.com origin, so a wildcard on that
    # suffix handed credentialed CORS to every store on Shopify.
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "copilot.py"), encoding="utf-8").read()
    ok('origin.endswith(".myshopify.com")' not in src,
       "no bare *.myshopify.com origin match remains")
    ok("own_shop and origin == own_shop" in src, "only this shop's own domain matches")

@test
def t_dependencies_are_pinned_and_the_mcp_fix_is_in():
    reqs = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "requirements.txt"), encoding="utf-8").read()
    for line in reqs.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        ok("==" in line, "pinned exactly: " + line)
    ok("mcp[cli]==1.28.1" in reqs,
       "mcp is on the release that fixes session hijacking (PYSEC-2026-3481/2/3)")

@test
def t_app_errors_are_recorded_and_surfaced():
    # A 500 in the dispatch flow used to be invisible unless somebody was watching
    # the server log, which at a dispatch desk means never.
    copilot.ERRORS_PATH = SCRATCH + "/app_errors.json"
    try:
        os.remove(copilot.ERRORS_PATH)
    except FileNotFoundError:
        pass
    copilot._record_error("booking a courier", ValueError("boom"))
    rows = copilot._recent_errors(24)
    eq(len(rows), 1, "recorded")
    eq(rows[0]["where"], "booking a courier", "says where")
    ok("ValueError: boom" in rows[0]["error"], "and what")
    # It must never itself raise inside an error path.
    copilot.ERRORS_PATH = "/nonexistent-dir-xyz/errors.json"
    copilot._record_error("somewhere", RuntimeError("x"))   # must not raise
    copilot.ERRORS_PATH = SCRATCH + "/app_errors.json"

@test
def t_weekly_snapshot_writes_once_a_week_and_excludes_credentials():
    copilot.BACKUP_STATE_PATH = SCRATCH + "/backup_state.json"
    copilot.BACKUP_SNAPSHOT_DIR = SCRATCH + "/snapshots"
    for f in glob.glob(copilot.BACKUP_SNAPSHOT_DIR + "/*.zip"):
        os.remove(f)
    try:
        os.remove(copilot.BACKUP_STATE_PATH)
    except FileNotFoundError:
        pass
    ok(copilot._weekly_snapshot(), "writes the first time")
    made = glob.glob(copilot.BACKUP_SNAPSHOT_DIR + "/*.zip")
    eq(len(made), 1, "one snapshot on disk")
    eq(copilot._weekly_snapshot(), False, "and not again within the week")
    import zipfile
    names = zipfile.ZipFile(made[0]).namelist()
    ok(names, "the zip has contents")
    for n in names:
        ok("wo_secret" not in n and "google_oauth" not in n,
           "no credential file in a snapshot: " + n)

@test
def t_the_shopify_api_version_is_supported():
    # 2024-10 fell out of Shopify's 12-month support window, and an unsupported
    # version is silently served from the oldest supported one.
    import server as srv
    ok(srv.API_VERSION >= "2025-10", "on a supported version, not " + srv.API_VERSION)

@test
def t_customs_values_are_remembered_per_product():
    # The store prices custom gobos through option dropdowns, so their base price
    # is zero and every international order needed the real value typed in again.
    copilot.CUSTOMS_MEMORY_PATH = SCRATCH + "/customs_memory.json"
    try:
        os.remove(copilot.CUSTOMS_MEMORY_PATH)
    except FileNotFoundError:
        pass
    copilot._remember_customs([
        {"key": "v111", "unit_price": 425.0, "hs": "9008.50.00", "country": "CN",
         "description": "Projector"},
        {"key": "t create your own gobo", "unit_price": 38.5, "hs": "9002.20.000",
         "country": "GB", "description": "Custom gobo"},
        {"key": "v999", "unit_price": 0, "hs": "", "country": "GB"},   # zero: not worth remembering
        {"key": "", "unit_price": 12.0},                                # no key: nothing to file under
    ])
    mem = copilot._load_customs_memory()
    eq(sorted(mem), ["t create your own gobo", "v111"], "only real values, only keyed ones")
    eq(mem["v111"]["unit_value"], "425.00", "stored to the penny")
    eq(mem["t create your own gobo"]["hs"], "9002.20.000", "and its HS code")

@test
def t_a_remembered_value_beats_the_derived_one():
    copilot.CUSTOMS_MEMORY_PATH = SCRATCH + "/customs_memory.json"
    copilot._remember_customs([{"key": "v111", "unit_price": 500.0, "hs": "9008.50.00",
                                "country": "CN", "description": "Projector"}])
    order = {"id": 12345, "name": "#12345", "currency": "GBP", "email": "c@x.co",
             "shipping_address": {"first_name": "A", "last_name": "B", "address1": "1 Rue",
                                  "city": "Paris", "zip": "75001", "country_code": "FR",
                                  "phone": "0033", "name": "A B"},
             "line_items": [{"id": 1, "title": "Projected Image 200 Watt Gobo Projector",
                             "quantity": 1, "price": "780.00", "variant_id": 111}]}
    async def tools(registry, name, args):
        if name == "shopify_get_order":
            return order
        if name == "shopify_get_variant":
            return {"id": 111, "inventory_item_id": 9111}
        if name == "shopify_get_inventory_items":
            return {"inventory_items": [{"id": 9111, "cost": "425.00",
                                         "harmonized_system_code": "9008.50.00"}]}
        return {}
    saved = copilot._tool_json; copilot._tool_json = tools
    try:
        r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
        it = (r.json().get("customs_items") or [])[0]
        eq(it["unit_value"], "500.00", "what was typed last time, not the 425.00 cost")
        eq(it["value_basis"], "remembered", "and it says so, so it can be corrected knowingly")
        eq(it["key"], "v111", "keyed to the variant so the next order finds it")
    finally:
        copilot._tool_json = saved
        try:
            os.remove(copilot.CUSTOMS_MEMORY_PATH)
        except FileNotFoundError:
            pass

@test
def t_a_booking_records_which_staff_member_made_it():
    reset_dispatch(); reset_prod()
    r = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
    eq(r.status_code, 200, r.text)
    entry = copilot._load_dispatch()["12345"]
    # The test token's `sub` claim is the staff user id Shopify sends.
    ok("by" in entry, "the record has a by field")
    from datetime import datetime as dt
    from zoneinfo import ZoneInfo
    today = dt.now(ZoneInfo("Europe/London")).date().isoformat()
    row = post("/api/dispatch/manifest", {"date": today}).json()["rows"][0]
    ok("by" in row, "and the manifest carries it")

# =========================== run ===========================================
passed = failed = 0
for fn in TESTS:
    try:
        fn(); passed += 1; print(f"  PASS  {fn.__name__}")
    except Exception as e:
        failed += 1; print(f"  FAIL  {fn.__name__}: {e}")
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
