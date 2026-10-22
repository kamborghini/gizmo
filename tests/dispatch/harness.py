import os, sys, json, time, asyncio, glob, re, tempfile, base64, secrets, logging
import atexit, shutil, signal
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import xml.etree.ElementTree as ET
SCRATCH = tempfile.mkdtemp(prefix="gizmo-dispatch-tests-")
# Every run made one of these and nothing removed it, until 1,744 of them
# (298 MB) filled the disk on 12 October 2026 and a run failed 80 tests on
# "No space left on device". It goes when this interpreter exits - pass, fail,
# Ctrl-C or a kill - and never sooner: the design rigs exec everything above
# the first test and serve from this folder for as long as they are up. It is
# registered before the app is imported because exit handlers run last-first,
# so the app's own exit flush (the activity ledger) still has a folder to land
# in. KEEP_SCRATCH=1 leaves it behind for a look afterwards.
_SCRATCH_PID = os.getpid()
def _drop_scratch():
    if os.getpid() != _SCRATCH_PID:
        return
    if os.environ.get("KEEP_SCRATCH") == "1":
        print("scratch kept: " + SCRATCH, file=sys.stderr)
    else:
        shutil.rmtree(SCRATCH, ignore_errors=True)
atexit.register(_drop_scratch)
# A plain kill (a timed-out run, a rig stopped from another shell) ends Python
# without its exit handlers, so SIGTERM is made an ordinary exit. uvicorn puts
# this handler back and raises the signal again once a rig has shut down.
if signal.getsignal(signal.SIGTERM) == signal.SIG_DFL:
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(128 + signum))
os.makedirs(SCRATCH, exist_ok=True)
for f in glob.glob(SCRATCH + "/*"):
    (os.remove(f) if os.path.isfile(f) else None)
for d in glob.glob(SCRATCH + "/*/*"):
    os.remove(d)
SECRET = "testsecret-long-enough-for-hmac-please-32b"
os.environ.update({
    "SHOPIFY_STORE": "test-store", "SHOPIFY_ACCESS_TOKEN": "shpat_x", "ANTHROPIC_API_KEY": "x",
    "SHOPIFY_API_SECRET": SECRET,
    # First-run setup needs the one-time code set on the server (audit chain R-C5).
    "SETUP_CODE": "harness-setup-code-0123456789",
    "SHIPPING_PATH": SCRATCH + "/shipping.json",
    "WO_SECRET_PATH": SCRATCH + "/wo_secret.json",
    "DISPATCH_STATE_PATH": SCRATCH + "/dispatch_state.json",
    "WO_FAILURES_PATH": SCRATCH + "/wo_failures.json",
    "DISPATCH_LABELS_DIR": SCRATCH + "/labels",
    "PRODUCTION_STATE_PATH": SCRATCH + "/production_state.json",
    "FORECAST_PATH": SCRATCH + "/forecast.json",
    "SCHEDULE_PATH": SCRATCH + "/schedule.json",
    "WATCH_PATH": SCRATCH + "/watch.json", "ALERTS_PATH": SCRATCH + "/alerts.json",
    "USAGE_PATH": SCRATCH + "/usage.json", "IMPACT_PATH": SCRATCH + "/impact.json",
    "ANALYSIS_CACHE_PATH": SCRATCH + "/analysis.json",
    # Off by default here: most tests swap _tool_json to return a different
    # store per test, and a snapshot shared across them would answer with the
    # previous test's orders. The tests that exercise the cache turn it on.
    "ORDER_CACHE_SECS": "0",
    "CHASE_LOG_PATH": SCRATCH + "/chase_log.json",
    "CRM_PATH": SCRATCH + "/crm.json",
    "FILES_PATH": SCRATCH + "/files.json",
    "USERS_PATH": SCRATCH + "/users.json",
    "ACTIVITY_PATH": SCRATCH + "/activity.json",
    "SESSIONS_PATH": SCRATCH + "/sessions.json",
    "WORK_PATH": SCRATCH + "/worklog.json",
    "GOBO_SIZES_LIVE": SCRATCH + "/gobo-sizes.csv",
    "USAGE_SHEETS_PATH": SCRATCH + "/usage_sheets.json",
    "PROFILE_PATH": SCRATCH + "/store_profile.json",
    "LAYOUTS_PATH": SCRATCH + "/layouts.json",
    "KNOWLEDGE_PATH": SCRATCH + "/store_knowledge.json",
    "ZETA_SYNC_PATH": SCRATCH + "/zeta_sync.json",
    "MAILBOX_PATH": SCRATCH + "/mailbox.json",
    "GMAIL_TOKEN_PATH": SCRATCH + "/gmail_oauth.json",
    "GMAIL_FINANCE_TOKEN_PATH": SCRATCH + "/gmail_finance_oauth.json",
    "FEEDBACK_PATH": SCRATCH + "/feedback.json",
    "RECON_PATH": SCRATCH + "/recon.json",
    "RECON_CACHE_PATH": SCRATCH + "/recon_cache.json",
    "RECON_DOCS_PATH": SCRATCH + "/recon_docs.json",
    "XERO_TOKEN_PATH": SCRATCH + "/xero_oauth.json",
    "COLLECTIONS_PATH": SCRATCH + "/collections.json",
    "PRIVACY_LOG_PATH": SCRATCH + "/privacy_log.json",
    "EORI_CACHE_PATH": SCRATCH + "/eori_cache.json",
    "LOANS_PATH": SCRATCH + "/loans.json",
    # The stock sheet's stores, one file each at the top of the data folder.
    "STOCK_ITEMS_PATH": SCRATCH + "/stock_items.json",
    "STOCK_HISTORY_PATH": SCRATCH + "/stock_history.jsonl",
    "STOCK_SNAPSHOTS_SCHEDULED_PATH": SCRATCH + "/stock_snap_scheduled.jsonl",
    "STOCK_SNAPSHOTS_CHANGES_PREFIX": SCRATCH + "/stock_snap_changes_",
    "STOCK_PERIODS_PATH": SCRATCH + "/stock_periods.json",
    "STOCK_ALERTS_PATH": SCRATCH + "/stock_alerts.json",
    "STOCK_SUPPLIERS_PATH": SCRATCH + "/stock_suppliers.json",
    "STOCK_SETTINGS_PATH": SCRATCH + "/stock_settings.json",
    "STOCK_BRIDGE_PATH": SCRATCH + "/stock_bridge.json",
    "STOCK_BACKUP_PREFIX": SCRATCH + "/stock_backup_",
    "STOCK_PEOPLE_PATH": SCRATCH + "/stock_people.json",
    # The two size-rule files decide the glass an order is cut from, and
    # they live in the REPO data dir rather than on the volume. Without
    # these redirects any test that saved a rule would edit the
    # merchant's real overrides - which is why the route had no test.
    "GOBO_OVERRIDES_PATH": SCRATCH + "/gobo-overrides.csv",
    "GOBO_ALIASES_PATH": SCRATCH + "/gobo-aliases.csv",
    # And the VOLUME copies the editor writes, which win over the seeds above.
    "GOBO_OVERRIDES_LIVE": SCRATCH + "/live/gobo-overrides.csv",
    "GOBO_ALIASES_LIVE": SCRATCH + "/live/gobo-aliases.csv",
})
# Seed the scratch rule files from the repo's real ones, so the size lookup
# behaves exactly as it does in production (a Source Four Junior really is
# ruled to 66mm by an override row) while every WRITE lands in the scratch
# dir instead of the merchant's file.
import shutil as _sh
for _src, _dst in ((os.path.join(os.path.dirname(__file__), "..", "data", "gobo-overrides.csv"),
                    os.environ["GOBO_OVERRIDES_PATH"]),
                   (os.path.join(os.path.dirname(__file__), "..", "data", "gobo-aliases.csv"),
                    os.environ["GOBO_ALIASES_PATH"])):
    try:
        _sh.copyfile(_src, _dst)
    except OSError:
        pass

for v in ("WO_METER_NUMBER", "WO_KEY", "WO_PASSWORD"):
    os.environ.pop(v, None)

# The suite never reaches the network. Twenty-five tests did, quietly: Gmail
# syncs posted their dummy refresh token to Google, the Settings status and the
# customs quote asked the test store's real Shopify address, and a label test
# fetched from the courier. Each passed only because the outside world answered
# the way it happened to that day. Now every name lookup and every connection
# outside this machine is refused, and the test that tried fails, naming the
# host; a test that needs an outside answer gives itself one. Installed before
# the app is imported, so an import-time attempt is refused too. A proxy
# setting would carry traffic out through a local port, so none is inherited.
import socket as _socket, ipaddress as _ipaddress, errno
for _v in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy",
           "ANTHROPIC_BASE_URL"):
    os.environ.pop(_v, None)
NET_REACHED = []
def _is_local(h):
    if h in ("localhost", "testserver"):
        return True
    try:
        return _ipaddress.ip_address(h.split("%", 1)[0]).is_loopback
    except ValueError:
        return False
_REAL_GETADDRINFO = _socket.getaddrinfo
def _no_network(host, *a, **k):
    h = host.decode() if isinstance(host, bytes) else str(host or "")
    if _is_local(h):
        return _REAL_GETADDRINFO(host, *a, **k)
    NET_REACHED.append(h)
    raise _socket.gaierror(_socket.EAI_NONAME, "the test suite does not reach the network: " + h)
_socket.getaddrinfo = _no_network
# An address given as numbers skips the lookup (asyncio connects to it
# directly), so the connection itself is checked as well.
_REAL_CONNECT, _REAL_CONNECT_EX = _socket.socket.connect, _socket.socket.connect_ex
def _outside(address):
    return isinstance(address, tuple) and address and not _is_local(str(address[0]))
def _no_connect(self, address):
    if _outside(address):
        NET_REACHED.append(str(address[0]))
        raise ConnectionRefusedError("the test suite does not reach the network: " + str(address[0]))
    return _REAL_CONNECT(self, address)
def _no_connect_ex(self, address):
    if _outside(address):
        NET_REACHED.append(str(address[0]))
        return errno.ECONNREFUSED
    return _REAL_CONNECT_EX(self, address)
_socket.socket.connect, _socket.socket.connect_ex = _no_connect, _no_connect_ex

import jwt
# Each test's log lines are held, and shown only under its FAIL line: the app
# logs a great deal on the paths the tests take on purpose, and printed, it
# buried the one failure that mattered (audit A6). VERBOSE=1 streams them, as
# the suite always did. Set before server.py is imported, so its basicConfig
# finds a handler already on the root and adds none; INFO, as it would have.
import io as _io
_TEST_LOG = _io.StringIO()
if not os.environ.get("VERBOSE"):
    _held_log = logging.StreamHandler(_TEST_LOG)
    _held_log.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.getLogger().addHandler(_held_log)
    logging.getLogger().setLevel(logging.INFO)
import server, copilot, worldoptions, pipedrive
import pagesource
from tools.sources import copilot_source, COPILOT_FILES
from gizmo import dispatch as desk
from gizmo import store as jsonstore
from gizmo import errors
from gizmo import ai as claude
from gizmo import activity, gate, team
from gizmo import background
from gizmo import orderbook, production, shopify, size_list
from gizmo import crm as salesdesk, mail
from gizmo import files as fileserver
from gizmo import webdav
from gizmo import privacy
from gizmo import loans
from gizmo import work
from gizmo import skills as skillbook
from gizmo import memory
from gizmo import knowledge
from gizmo import chat as assistant
from gizmo import prompts
from gizmo import seo
from gizmo import analytics
from gizmo import scheduler
from gizmo import updates
from gizmo import impact
from gizmo import backup
from gizmo import liability
from gizmo import reconciliation
from gizmo import xero_sync as xerosync
from gizmo import forecasting
from gizmo import rendering
from gizmo import profile as store_profile
from gizmo import layouts
from gizmo import oauth
from gizmo import status as appstatus
from gizmo import clock
from gizmo import products as catalog
from gizmo import config
import xero as xero_api
REAL_SOAP_CALL = worldoptions._soap_call
from starlette.testclient import TestClient

TESTS = []
def test(fn): TESTS.append(fn); return fn
def eq(a, b, msg=""):
    if a != b: raise AssertionError(f"{msg}: {a!r} != {b!r}")
def ok(c, msg=""):
    if not c: raise AssertionError(f"FAIL: {msg}")
def tok(sub=None):
    now = int(time.time())
    claims = {"iss": "https://test-store.myshopify.com/admin",
              "dest": "https://test-store.myshopify.com", "aud": "a",
              "exp": now + 120, "nbf": now - 5}
    if sub is not None:
        claims["sub"] = str(sub)
    return jwt.encode(claims, SECRET, algorithm="HS256")
_RUN_LOOP = None


def run(coro):
    """Run a coroutine on the suite's own loop. Python 3.14 has no implicit
    loop to borrow (3.12 already warned that asking for one was going away),
    and asyncio.run() elsewhere closes whatever loop is current, so the suite
    keeps its own and makes another only if that one was closed."""
    global _RUN_LOOP
    if _RUN_LOOP is None or _RUN_LOOP.is_closed():
        _RUN_LOOP = asyncio.new_event_loop()
    asyncio.set_event_loop(_RUN_LOOP)
    return _RUN_LOOP.run_until_complete(coro)

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
REAL_TOOL_JSON = shopify._tool_json
shopify._tool_json = fake_tool_json

TAG_WRITES = []
async def fake_tag_writer(order_id, tags):
    TAG_WRITES.append((int(order_id), tags)); return {"order": {"id": order_id, "tags": tags}}
FULFILLED = []
async def fake_fulfillment(order_id, tracking_number=None, tracking_company=None, tracking_url=None, notify_customer=True):
    FULFILLED.append({"order_id": order_id, "tracking": tracking_number, "company": tracking_company, "notify": notify_customer})
    return {"ok": True, "fulfillment_id": 555, "status": "success"}
shopify._order_tag_writer = fake_tag_writer
shopify._fulfillment_writer = fake_fulfillment
CANCELED_FULFILLMENTS = []
async def fake_canceler(fulfillment_id):
    CANCELED_FULFILLMENTS.append(int(fulfillment_id)); return {"ok": True}
shopify._fulfillment_canceler = fake_canceler
def reset_dispatch():
    json.dump({"orders": {}}, open(SCRATCH + "/dispatch_state.json", "w"))
    # A booking left unresolved by one test is not another test's business.
    try:
        os.remove(SCRATCH + "/booking_intents.json")
    except FileNotFoundError:
        pass
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

# The app AS SERVED, middleware and all - not a bare inner app that would let
# the suite pass over a stack the merchant never runs.
client = TestClient(server.build_app())
# The real install check asks Shopify whether the app is installed; the suite
# never does (with a network it got 401 for the dummy token and read it as an
# uninstall). A test that needs an answer sets its own.
async def _install_unknown():
    return "unknown"
shopify._install_checker = _install_unknown
async def _customer_unknown(cid, email):
    return "unknown"
shopify._customer_checker = _customer_unknown
# Shopify's answer to the suite's dummy token is a refusal, and that is what the
# two other readers the routes call on their own give back here: the Settings
# permissions read (an error, never a scope reported missing) and the customs
# tax id (empty, so the operator types it). Twelve tests asked the test store's
# real address for these. A test that needs an answer sets its own.
async def _scopes_refused(max_age=900.0):
    return {"scopes": [], "missing": {}, "error": "Shopify refused the suite's dummy token"}
shopify._scope_reader = _scopes_refused
async def _tax_id_refused(order_id):
    return {"tax_id": "", "source": "", "error": "Shopify refused the suite's dummy token"}
shopify._tax_id_reader = _tax_id_refused
# The products read in one GraphQL call (the fourth speed audit item, X7): the
# suite's dummy token is refused, so the per-product reads the tests stub stand.
async def _product_meta_refused(product_ids):
    raise RuntimeError("Shopify refused the suite's dummy token")
shopify._product_meta_reader = _product_meta_refused
# Google, likewise. The Gmail syncs that tests start post their dummy refresh
# token to Google's token door, which refuses it; here that door gives the same
# refusal word for word (asked once, 2 October 2026) and nothing else on Google
# answers at all. Every Gmail and Search Console function stays real; a test
# that wants Gmail to answer stubs _call or _token as before, and a test that
# swaps httpx.AsyncClient for its own transport still wins.
import httpx as _httpx
import google_mail as _google_mail, google_data as _google_data
def _google_offline(request):
    if request.url.host == "oauth2.googleapis.com" and request.url.path == "/token":
        return _httpx.Response(400, json={"error": "invalid_request",
                                          "error_description": "Could not determine client ID from request."})
    raise _httpx.ConnectError("the test suite does not reach " + request.url.host, request=request)
class _RoutedHttpx:
    """A module's httpx, with every AsyncClient it makes answered by one handler."""
    def __init__(self, handler):
        self._handler = handler
    def __getattr__(self, name):
        return getattr(_httpx, name)
    def AsyncClient(self, *a, **k):
        k.setdefault("transport", _httpx.MockTransport(self._handler))
        return _httpx.AsyncClient(*a, **k)
_google_mail.httpx = _google_data.httpx = _RoutedHttpx(_google_offline)
APP_AUTH = {"session": "", "master": ""}
MASTER_PW = "test-password-123"
def ensure_auth():
    """The app owns its accounts now: every request needs a session. The
    harness lazily creates/logs into the master account the first time."""
    if APP_AUTH["session"]:
        return APP_AUTH["session"]
    gate._rl_hits.clear(); gate._rl_global.clear()
    h = {"Authorization": "Bearer " + tok()}
    st = client.post("/api/auth/state", json={}, headers=h).json()
    if st.get("setup"):
        r = client.post("/api/auth/setup", json={"name": "Cameron", "username": "cameron",
                                                 "password": MASTER_PW,
                                                 "setup_code": os.environ["SETUP_CODE"]}, headers=h).json()
    else:
        r = client.post("/api/auth/login", json={"username": "cameron",
                                                 "password": MASTER_PW}, headers=h).json()
    APP_AUTH["session"], APP_AUTH["master"] = r["session"], r["me"]["id"]
    return APP_AUTH["session"]
def post(path, body):
    gate._rl_hits.clear(); gate._rl_global.clear()   # the suite outpaces the app's rate limiter
    return client.post(path, json=body, headers={"Authorization": "Bearer " + tok(),
                                                 "X-App-Session": ensure_auth()})
def post_s(session, path, body):
    gate._rl_hits.clear(); gate._rl_global.clear()
    return client.post(path, json=body, headers={"Authorization": "Bearer " + tok(),
                                                 "X-App-Session": session})

