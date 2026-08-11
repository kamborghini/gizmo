#!/usr/bin/env python3
"""
World Options SOAP web service connector - shipping: quote, book, label, cancel.

Isolated on purpose: every World-Options-specific request lives in this file and
the rest of the app speaks our own normalized shapes, so the courier provider
can be swapped by editing one module.

This talks to World Options' WCF SOAP web service (BasicHttpBinding, SOAP 1.1,
document/literal) at http://service.worldoptions.co.uk:
  * RateService.svc  / GetAllServicesAndRates  -> quote couriers (free)
  * ShipmentService.svc / DoShipment           -> book a shipment (charges)
  * VoidService.svc  / VoidShipment            -> cancel a shipment

Auth is a per-request AuthenticationDetail block: MeterNumber (+ optional Key,
Password) and a PluginCode. Credentials come from env or are set at runtime via
set_credentials(); they are persisted server-side, never echoed, and kept out of
logs, URLs and backups.

Envelopes are built by hand (no zeep): the module stays async + dependency-free,
and the WSDL's schema imports point at an internal host a WSDL parser could not
resolve anyway. Full contract: docs/worldoptions-api.md.
"""
import os
import asyncio
import logging
from xml.sax.saxutils import escape as _xml_escape
import xml.etree.ElementTree as ET

import httpx

logger = logging.getLogger("shopify_mcp.worldoptions")

DEFAULT_BASE = "https://service.worldoptions.co.uk"
# The REST Ecommerce host is a different API; if it ever ends up configured as the
# SOAP base (e.g. a value persisted by an earlier build) it must be rejected.
_REST_HOST = "ecommerce.worldoptions.com"

_state = {
    "meter":    os.environ.get("WO_METER_NUMBER", "").strip(),
    "key":      os.environ.get("WO_KEY", "").strip(),
    "password": os.environ.get("WO_PASSWORD", "").strip(),
    "plugin":   os.environ.get("WO_PLUGIN_CODE", "Web_Service").strip() or "Web_Service",
    "base_url": (os.environ.get("WO_BASE_URL", DEFAULT_BASE) or DEFAULT_BASE).rstrip("/"),
}
_gate = asyncio.Semaphore(4)

# SOAP / DataContract namespaces. Element names take the namespace of the type
# that DECLARES them (elementFormDefault=qualified), so a child of a type in
# namespace X is emitted with X's prefix even if its own type lives elsewhere.
NS = {
    "s":   "http://schemas.xmlsoap.org/soap/envelope/",
    "tem": "http://tempuri.org/",
    "wo":  "http://schemas.datacontract.org/2004/07/WOWebServices",
    "m":   "http://schemas.datacontract.org/2004/07/WOWebServices.Model",
    "rs":  "http://schemas.datacontract.org/2004/07/WOWebServices.Model.wsRateShipmentDetails",
    "sd":  "http://schemas.datacontract.org/2004/07/WOWebServices.Model.wsShippingDetails",
    "g":   "http://schemas.datacontract.org/2004/07/WOModel.GlobalTypes",
    "gt":  "http://schemas.datacontract.org/2004/07/WOWebServices.Model.wsGlobalTypes",
    "lbl": "http://schemas.datacontract.org/2004/07/WOModel.ShippingLabel",
}

# Map a booking service code (wsServiceTypes) onto its carrier (wsServiceCompanyTypes),
# used only as a fallback when the quote reply does not name the carrier itself.
_CARRIERS = ["DHLPARCEL", "DHL", "FEDEX", "UPS", "TNT", "PALLETWAYS", "YODEL",
             "DXEXPRESS", "HERMES", "DSV", "EXFREIGHT", "GLOBALTRANZ", "CITYSPRINT",
             "EVRISEND", "EVRICORPORATE", "EVRI", "TUFFNELLS", "ROYALMAIL", "DPD"]

# WO's carrier enum -> the carrier names Shopify recognizes. Shopify only builds a
# working tracking link in the customer's shipping email when tracking_company is
# one of its known names; "ROYALMAIL" or "EVRISEND" would leave the email linkless.
SHOPIFY_CARRIER_NAMES = {
    "ROYALMAIL": "Royal Mail", "DPD": "DPD", "EVRISEND": "Evri", "EVRICORPORATE": "Evri",
    "EVRI": "Evri", "HERMES": "Evri", "UPS": "UPS", "FEDEX": "FedEx", "TNT": "TNT",
    "DHL": "DHL Express", "DHLPARCEL": "DHL", "YODEL": "Yodel", "CITYSPRINT": "CitySprint",
    "DXEXPRESS": "DX", "TUFFNELLS": "Tuffnells", "PALLETWAYS": "Palletways", "DSV": "DSV",
}


def shopify_carrier(carrier_code: str) -> str:
    """A Shopify-recognizable tracking company for a WO carrier enum value."""
    up = (carrier_code or "").strip().upper()
    return SHOPIFY_CARRIER_NAMES.get(up, (carrier_code or "").strip())


# Collection arrangements the merchant can declare (CollectionOptionTypes enum).
# When the element is omitted WCF assumes the FIRST value (book a new collection),
# which double-books for accounts that already have a daily driver.
COLLECTION_OPTIONS = [
    "I_Need_To_Book_A_Collection",
    "I_Need_To_Book_A_Collection_For_Next_Day",
    "I_Have_Daily_Collection",
    "I_Already_Have_Collection_Scheduled",
    "I_Am_Going_To_Drop_Off_My_Packages",
]


class WorldOptionsError(Exception):
    """Carries World Options' own message so the UI can show the real cause."""


# ---------------------------------------------------------------------------
# Connection state
# ---------------------------------------------------------------------------
def configured() -> bool:
    return bool(_state["meter"] or _state["key"])


def base_url() -> str:
    return _state["base_url"]


def set_credentials(meter=None, key=None, password=None, plugin=None) -> None:
    """Set any provided credential (None leaves it unchanged; '' clears it)."""
    if meter is not None:
        _state["meter"] = (meter or "").strip()
    if key is not None:
        _state["key"] = (key or "").strip()
    if password is not None:
        _state["password"] = (password or "").strip()
    if plugin is not None:
        _state["plugin"] = (plugin or "").strip() or "Web_Service"


def set_base_url(url) -> None:
    b = ((url or DEFAULT_BASE).strip() or DEFAULT_BASE).rstrip("/")
    # Never point the SOAP client at the REST host (a stale value from an earlier build).
    if _REST_HOST in b:
        b = DEFAULT_BASE
    _state["base_url"] = b


def meter_last4() -> str:
    v = _state["meter"] or _state["key"]
    return v[-4:] if len(v) >= 4 else ("set" if v else "")


def plugin_code() -> str:
    return _state["plugin"]


def has_key() -> bool:
    return bool(_state["key"])


def has_password() -> bool:
    return bool(_state["password"])


# ---------------------------------------------------------------------------
# XML building
# ---------------------------------------------------------------------------
def _t(prefix: str, name: str, value) -> str:
    """One element `<prefix:name>escaped</prefix:name>`, or '' when value is blank."""
    if value is None or value == "":
        return ""
    return f"<{prefix}:{name}>{_xml_escape(str(value))}</{prefix}:{name}>"


def _b(prefix: str, name: str, value: bool) -> str:
    return f"<{prefix}:{name}>{'true' if value else 'false'}</{prefix}:{name}>"


def _num(v) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "0"
    return str(int(f)) if f == int(f) else repr(f)


def _auth_block() -> str:
    # wsAuthenticationDetail children, alphabetical: Key, MeterNumber, Password, PluginCode.
    return ("<wo:AuthenticationDetail>"
            + _t("m", "Key", _state["key"])
            + _t("m", "MeterNumber", _state["meter"])
            + _t("m", "Password", _state["password"])
            + _t("m", "PluginCode", _state["plugin"] or "Web_Service")
            + "</wo:AuthenticationDetail>")


def _envelope(inner: str) -> str:
    decls = " ".join(f'xmlns:{p}="{u}"' for p, u in NS.items())
    return ('<?xml version="1.0" encoding="utf-8"?>'
            f'<s:Envelope {decls}><s:Header/><s:Body>{inner}</s:Body></s:Envelope>')


# ---------------------------------------------------------------------------
# XML parsing (namespace-agnostic: match by local name)
# ---------------------------------------------------------------------------
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _find(elem, name):
    if elem is None:
        return None
    for e in elem.iter():
        if _local(e.tag) == name:
            return e
    return None


def _findall_direct(elem, name):
    """Immediate-child-ish search: all descendants with the local name (WCF trees
    are shallow enough that this is unambiguous for our reply shapes)."""
    return [e for e in (elem.iter() if elem is not None else []) if _local(e.tag) == name]


def _text(elem, name, default=""):
    e = _find(elem, name)
    return (e.text or default) if e is not None else default


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
async def _soap_call(service: str, action: str, inner: str, retryable: bool = True) -> ET.Element:
    """retryable=False for operations that SPEND MONEY (DoShipment): a timed-out
    booking may have succeeded server-side, so auto-retrying could charge twice.
    Those surface the error and let the merchant check before trying again."""
    if not configured():
        raise WorldOptionsError("World Options is not connected. Add your Meter Number in Settings.")
    url = f"{_state['base_url']}/{service}.svc"
    headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{action}"'}
    payload = _envelope(inner).encode("utf-8")
    attempts = 3 if retryable else 1
    async with _gate:
        last_exc = None
        for attempt in range(attempts):
            try:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    resp = await client.post(url, content=payload, headers=headers, timeout=45.0)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_exc = e
                if attempt >= attempts - 1:
                    break
                await asyncio.sleep(min(2 ** attempt, 6))
                continue
            return _parse(resp, url)
    if not retryable:
        raise WorldOptionsError(
            "The booking request did not get a reply from World Options. It MAY still have gone "
            "through: check your World Options portal for a new shipment before booking again, "
            "or you could be charged twice.")
    raise WorldOptionsError(
        f"Could not reach World Options ({type(last_exc).__name__ if last_exc else 'network error'}). "
        "Try again in a moment.")


def _friendly_fault(reason: str) -> str:
    """Translate World Options' auth exceptions into merchant-readable guidance.
    Their backend exchanges the web service Key + Password for an OAuth access
    token, so the OAuth error names say exactly what is wrong: invalid_request =
    credentials missing from the login, invalid_client = credentials wrong."""
    low = (reason or "").lower()
    if "access token" in low and "invalid_request" in low:
        return ("World Options needs your web service Key and Password as well as the Meter "
                "Number; the login went out without them. Add them in Shipping settings. If you "
                "don't have a Key and Password, ask World Options for your web service (API) "
                "credentials.")
    if "invalid_client" in low:
        return ("World Options rejected the web service Key and Password. Double-check both in "
                "Shipping settings, or ask World Options to confirm your web service credentials.")
    if "woauthenticationexception" in low:
        return "World Options could not log you in: " + (reason or "")[:250]
    return ("World Options rejected the request: " + (reason or "SOAP fault"))[:400]


def _parse(resp: httpx.Response, url: str = "") -> ET.Element:
    # A 404 (or other non-fault error) usually means the wrong endpoint, not a real
    # SOAP reply. Say so, and name the host so a misconfiguration is obvious.
    if resp.status_code == 404:
        raise WorldOptionsError(
            f"World Options did not recognise the service address ({url or _state['base_url']}). "
            "This usually means the wrong web-service URL. Expected the shipping web service at "
            f"{DEFAULT_BASE}.")
    try:
        root = ET.fromstring(resp.content)
    except Exception:
        raise WorldOptionsError(f"World Options returned an unreadable response (HTTP {resp.status_code}).")
    fault = _find(root, "Fault")
    if fault is not None:
        reason = _text(fault, "Text") or _text(fault, "faultstring") or "SOAP fault"
        raise WorldOptionsError(_friendly_fault(reason))
    if resp.status_code >= 400:
        raise WorldOptionsError(f"World Options error (HTTP {resp.status_code}).")
    return root


def _reply_status(reply, context: str):
    """Raise on a FAILED reply, carrying WO's Message. Returns the (message, notif)."""
    notif = (_text(reply, "NotificationtType") or "").strip().upper()
    msg = _text(reply, "Message").strip()
    if notif == "FAILED":
        low = msg.lower()
        if "access token" in low or "authenticationexception" in low or "invalid_client" in low:
            raise WorldOptionsError(_friendly_fault(msg))
        raise WorldOptionsError(msg or f"World Options could not {context}.")
    return msg, notif


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------
def _carrier_from(service_code: str, quote_service_type: str) -> str:
    qt = (quote_service_type or "").strip().upper()
    if qt:
        return qt
    up = (service_code or "").upper()
    for c in _CARRIERS:
        if up.startswith(c):
            return c
    return ""


def _dec(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Public operations
# ---------------------------------------------------------------------------
async def quote(origin: dict, destination: dict, boxes: list,
                currency: str = "GBP", residential: bool = False) -> dict:
    """Free, read-only price check across all carriers. Returns {options[]}."""
    o, d = origin or {}, destination or {}
    pkgs = ""
    for i, b in enumerate(boxes or [], start=1):
        pkgs += ("<rs:wsShippingDetails.PackageDetail>"
                 + _t("rs", "Breadth", _num(b.get("width")))
                 + _t("rs", "CustomValue", "0")
                 + _t("rs", "Height", _num(b.get("depth")))
                 + _t("rs", "ItemNumber", str(i))
                 + _t("rs", "Length", _num(b.get("length")))
                 + _t("rs", "Weight", _num(b.get("weight")))
                 + "</rs:wsShippingDetails.PackageDetail>")
    inner = (
        "<tem:GetAllServicesAndRates><tem:request>"
        + _auth_block()
        # RecipientDetails (wsDeliveryDetail), alpha
        + "<wo:RecipientDetails>"
        + _t("m", "DeliveryCity", d.get("city"))
        + _t("m", "DeliveryCountryCode", (d.get("country") or "").upper())
        + _t("m", "DeliveryPostCode", d.get("postcode"))
        + _t("m", "DeliveryState", d.get("state"))
        + _b("m", "IsResidential", bool(residential))
        + "</wo:RecipientDetails>"
        # SenderDetails (wsCollectionDetail), alpha
        + "<wo:SenderDetails>"
        + _t("m", "CollectionCity", o.get("city"))
        + _t("m", "CollectionCountryCode", (o.get("country") or "").upper())
        + _t("m", "CollectionCountryState", o.get("state"))
        + _t("m", "CollectionPostCode", o.get("postcode"))
        + "</wo:SenderDetails>"
        # ShippingDetails (wsShippingDetails), alpha (only fields we set)
        + "<wo:ShippingDetails>"
        + f"<rs:PackageDetails>{pkgs}</rs:PackageDetails>"
        + _t("rs", "ServiceName", "ALL")
        + _t("rs", "ServiceTypeName", "ALL")
        + "</wo:ShippingDetails>"
        + "</tem:request></tem:GetAllServicesAndRates>"
    )
    root = await _soap_call("RateService", "http://tempuri.org/IRateService/GetAllServicesAndRates", inner)
    reply = _find(root, "GetAllServicesAndRatesResult")
    if reply is None:
        raise WorldOptionsError("World Options returned no rate result.")
    _reply_status(reply, "price this shipment")
    cur = (currency or "GBP")[:3].upper()
    options = []
    for opt in _findall_direct(reply, "wsAvailableServicesAndRates"):
        qd = _find(opt, "wsQuoteDetails")
        amount = _dec(_text(qd, "TotalNetCharge")) if qd is not None else None
        service_code = _text(opt, "wsServiceTypeCode")
        carrier = _carrier_from(service_code, _text(qd, "ServiceType") if qd is not None else "")
        options.append({
            "service_type_code": service_code,
            "service_code":      _text(opt, "wsServiceCode"),
            "package_type_code": _text(opt, "wsPackageTypeCode"),
            "carrier_name":      carrier,
            "service_name":      _text(opt, "wsServiceTypeName") or service_code,
            "amount":            amount,
            "currency":          cur,
            "delivery":          _text(opt, "wsDeliveryDateTime"),
            "pickup":            _text(opt, "wsPickupDateTime"),
        })
    options.sort(key=lambda x: (x["amount"] is None, x["amount"] if x["amount"] is not None else 0))
    return {"options": options, "currency": cur}


def _recipient_block(d: dict) -> str:
    # wsRecipient, alpha: Address1,Address2,Address3,City,Company,Country_Code,Email,
    # Fax,Name,Phone,PhoneDialCode,Postalcode,Residential,State_Code
    name = d.get("name") or " ".join(x for x in [d.get("firstname"), d.get("lastname")] if x).strip()
    return ("<wo:RecipientsDetails>"
            + _t("m", "Address1", d.get("street"))
            + _t("m", "City", d.get("city"))
            + _t("m", "Company", d.get("company"))
            + _t("m", "Country_Code", (d.get("country") or "").upper())
            + _t("m", "Email", d.get("email"))
            + _t("m", "Name", name or d.get("company"))
            + _t("m", "Phone", d.get("phone"))
            + _t("m", "Postalcode", d.get("postcode"))
            + _b("m", "Residential", not (d.get("company") or "").strip())
            + _t("m", "State_Code", d.get("state"))
            + "</wo:RecipientsDetails>")


def _sender_block(o: dict) -> str:
    # wsSender, alpha: Address1,Address2,Address3,City,Company,CountryCode,Email,
    # Name,Phone,PhoneDialCode,PostalCode,State
    name = o.get("name") or " ".join(x for x in [o.get("firstname"), o.get("lastname")] if x).strip()
    return ("<wo:SendersDetails>"
            + _t("m", "Address1", o.get("street"))
            + _t("m", "City", o.get("city"))
            + _t("m", "Company", o.get("company"))
            + _t("m", "CountryCode", (o.get("country") or "").upper())
            + _t("m", "Email", o.get("email"))
            + _t("m", "Name", name or o.get("company"))
            + _t("m", "Phone", o.get("phone"))
            + _t("m", "PostalCode", o.get("postcode"))
            + _t("m", "State", o.get("state"))
            + "</wo:SendersDetails>")


def _classify_label(lbl: ET.Element) -> dict:
    url = _text(lbl, "LabelURL").strip()
    if url:
        return {"type": "url", "value": url}
    img = _text(lbl, "Image").strip()
    if img:
        lt = (_text(lbl, "LabelType") or "").upper()
        kind = "base64pdf" if "PDF" in lt or not lt else ("base64png" if "PNG" in lt else "base64pdf")
        return {"type": kind, "value": img}
    return {}


async def book(option: dict, origin: dict, destination: dict, boxes: list,
               currency: str = "GBP", reference: str = "",
               ready_time: str = "", close_time: str = "",
               collection_option: str = "") -> dict:
    """Book (and CHARGE) the chosen quote option. Returns tracking + labels.
    ready_time/close_time (HH:MM) describe the collection window and
    collection_option the arrangement (COLLECTION_OPTIONS); sent in the
    booking's BillingDetail when set."""
    option = option or {}
    service_code = option.get("service_type_code") or ""
    carrier = (option.get("carrier_name") or _carrier_from(service_code, "")).upper()
    pkg_type = option.get("package_type_code") or ""
    cur = (currency or "GBP")[:3].upper()
    pkgs = ""
    for i, b in enumerate(boxes or [], start=1):
        pkgs += ("<sd:wsShippingDetail.PackageDetail>"
                 + _t("sd", "Breadth", _num(b.get("width")))
                 + _t("sd", "CustomValue", "0")
                 + _t("sd", "Height", _num(b.get("depth")))
                 + _t("sd", "ItemNumber", str(i))
                 + _t("sd", "Length", _num(b.get("length")))
                 + _t("sd", "Wt", _num(b.get("weight")))
                 + "</sd:wsShippingDetail.PackageDetail>")
    # ShippingDetail (wsShippingDetail), alpha, only fields we set:
    # CollectionType, Currency, CustomerReference, PackageDetails, PackageTypeCode,
    # ServiceType, ServiceTypeCode
    shipping = ("<wo:ShippingDetail>"
                + _t("sd", "CollectionType", "Regular")
                + _t("sd", "Currency", cur)
                + _t("sd", "CustomerReference", (reference or "")[:40])
                + f"<sd:PackageDetails>{pkgs}</sd:PackageDetails>"
                + _t("sd", "PackageTypeCode", pkg_type)
                + _t("sd", "ServiceType", carrier)
                + _t("sd", "ServiceTypeCode", service_code)
                + "</wo:ShippingDetail>")
    # BillingDetail (wsBillingDetail) carries the collection window + arrangement.
    # Children alphabetical: CloseTime, CollectionOptions, ReadyTime. ReadyDate is
    # deliberately not sent (optional; its date format is undocumented, WO defaults it).
    co = (collection_option or "").strip()
    if co and co not in COLLECTION_OPTIONS:
        co = ""
    billing = ""
    if ready_time or close_time or co:
        billing = ("<wo:BillingDetail>"
                   + _t("wo", "CloseTime", close_time)
                   + _t("wo", "CollectionOptions", co)
                   + _t("wo", "ReadyTime", ready_time)
                   + "</wo:BillingDetail>")
    # ShipmentBookingRequest, alpha: AdditionalShipmentDetail, AuthenticationDetail,
    # BillingDetail, RecipientsDetails, SendersDetails, ShippingDetail
    inner = ("<tem:DoShipment><tem:shipment>"
             + _auth_block()
             + billing
             + _recipient_block(destination or {})
             + _sender_block(origin or {})
             + shipping
             + "</tem:shipment></tem:DoShipment>")
    root = await _soap_call("ShipmentService", "http://tempuri.org/IShipmentService/DoShipment", inner,
                            retryable=False)
    reply = _find(root, "DoShipmentResult")
    if reply is None:
        raise WorldOptionsError("World Options returned no booking result.")
    msg, _notif = _reply_status(reply, "book this shipment")
    tracking = _text(reply, "MasterTrackingNo").strip()
    labels = [c for c in (_classify_label(l) for l in _findall_direct(reply, "ShippingLabel")) if c]
    return {
        "tracking_number": tracking,
        "carrier_name":    carrier,
        "service_name":    option.get("service_name") or service_code,
        "service_code":    service_code,
        "amount":          _dec(option.get("amount")),
        "currency":        cur,
        "labels":          labels,
        "warning":         _text(reply, "Warning").strip(),
        "message":         msg,
        "collection_date": _text(reply, "CollectionDateNumber").strip(),
    }


async def cancel(tracking_number: str) -> dict:
    inner = ("<tem:VoidShipment><tem:request>"
             + _auth_block()
             + _t("wo", "TrackingNumber", tracking_number)
             + "</tem:request></tem:VoidShipment>")
    root = await _soap_call("VoidService", "http://tempuri.org/IVoidService/VoidShipment", inner)
    reply = _find(root, "VoidShipmentResult")
    if reply is None:
        raise WorldOptionsError("World Options returned no cancellation result.")
    msg, _notif = _reply_status(reply, "cancel this shipment")
    return {"canceled": True, "message": msg}


async def validate() -> dict:
    """Confirm the credentials work by pricing a tiny domestic test parcel.
    Read-only; never books. Returns {ok, message}."""
    try:
        res = await quote(
            {"city": "Manchester", "postcode": "M1 1AA", "country": "GB"},
            {"city": "London", "postcode": "EC1A 1BB", "country": "GB"},
            [{"width": 20, "length": 15, "depth": 10, "weight": 1.0}],
            currency="GBP", residential=True)
        n = len(res.get("options") or [])
        return {"ok": True, "message": f"{n} service(s) available on a test quote."}
    except WorldOptionsError as e:
        return {"ok": False, "message": str(e)}
