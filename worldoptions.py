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
    "ad":  "http://schemas.datacontract.org/2004/07/WOModel.AddlShipmentDetails",
}

# The EXACT wsServiceCompanyTypes enum members (case-sensitive: WCF's serializer
# rejects 'PALLETWAYS'/'EXFREIGHT'). Booking must only ever emit these literals.
SERVICE_COMPANY_ENUM = ["ALL", "DHL", "FEDEX", "UPS", "TNT", "Palletways", "YODEL",
                        "DHLPARCEL", "DXEXPRESS", "HERMES", "DSV", "EXFreight",
                        "GLOBALTRANZ", "CITYSPRINT", "EVRISEND", "EVRICORPORATE",
                        "TUFFNELLS", "ROYALMAIL", "DPD"]
_CANON_CARRIER = {v.upper(): v for v in SERVICE_COMPANY_ENUM}


def canonical_carrier(code: str) -> str:
    """The exact enum literal for a carrier, '' when it is not a member."""
    return _CANON_CARRIER.get((code or "").strip().upper(), "")


# Map a booking service code (wsServiceTypes) onto its carrier, used only as a
# fallback when the quote reply does not name the carrier itself. Prefix EVRI
# maps to EVRISEND (bare 'EVRI' is not an enum member).
_CARRIERS = ["DHLPARCEL", "DHL", "FEDEX", "UPS", "TNT", "PALLETWAYS", "YODEL",
             "DXEXPRESS", "HERMES", "DSV", "EXFREIGHT", "GLOBALTRANZ", "CITYSPRINT",
             "EVRISEND", "EVRICORPORATE", "EVRI", "TUFFNELLS", "ROYALMAIL", "DPD"]
_PREFIX_TO_ENUM = {"EVRI": "EVRISEND", "PALLETWAYS": "Palletways", "EXFREIGHT": "EXFreight"}

# The booking wsPackageTypes enum (wo_xsd6). The QUOTE reply's wsPackageTypeCode is a
# plain string that can carry rate-only values (Any_Document, EX_LTL, ...) which the
# booking enum rejects; anything not in this list is omitted from the booking.
PACKAGE_TYPES_ENUM = {
    "Fedex_Box", "Fedex_Envelope", "Fedex_Pak", "Fedex_Your_Packaging",
    "UPS_My_Packaging", "UPS_Envelope", "DHL_Document", "DHL_NonDocument",
    "YODEL_NonDocument", "YODEL_Document", "TNT_NonDocument", "TNT_Document",
    "TNT_LTL", "UKMAIL_NonDocument", "DXExpress_Parcel", "Hermes_Parcel",
    "DSV_LTL", "EXF_LTL", "EXF_FCL", "GlobalTranz_LTL", "CitySprint_Parcel",
    "Evri_Parcel", "Tuffnells_Parcel", "Tuffnells_Pallet", "RoyalMail_Parcel",
    "DPD_Parcel",
}

# PluginWebServiceCode enum (wo_xsd4): a typo here bricks every request.
PLUGIN_CODES = ["Web_Service", "Magento", "WooCommerce_2_1_12", "WooCommerce_2_2_2",
                "CS_Kart", "Open_Cart", "Shopify", "Wix", "PrestaShop", "Portal"]

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


# Per-carrier signature services (wsSignatureTypes enum, grouped by the carrier
# whose bookings may carry them). Sent only when the merchant picks one.
SIGNATURE_OPTIONS = {
    "FEDEX":     ["Fedex_No_Signature_Required", "Fedex_InDirect", "Fedex_Direct", "Fedex_Adult"],
    "UPS":       ["UPS_Signature_Required", "UPS_Adult"],
    "DHL":       ["DHL_No_Signature_Required", "DHL_Direct", "DHL_Adult", "DHL_Leave_With_Neighbour"],
    "DHLPARCEL": ["DHLParcel_Signature_Required", "DHLParcel_Delivery_To_Neighbour", "DHLParcel_Leave_Safe"],
}
EXPORT_REASONS = ["Sale", "Sample", "Gift", "Repair", "Exhibition", "Personal_Effects", "Return", "Other"]
DUTIES_PAYORS = ["Duties_To_Be_Paid_By_Receiver", "Duties_To_Be_Paid_By_Sender", "Duties_To_Be_Paid_By_Third_Party"]
INVOICE_TYPES = ["Help_Me_Generate", "I_Already_Have_One", "Upload_your_own_PDF_invoice"]

# wsQuoteDetail decimal fields that are genuine price components (for the
# per-option breakdown). Everything else in that type is metadata.
_BREAKDOWN_SKIP = {"TotalNetCharge"}
_BREAKDOWN_META = {"DHLLocalProductCode", "DeliveryDateTime", "ServiceSurchargeCode", "ServiceType",
                   "ServiceTypeMode", "ServiceTypeName", "TransportationType", "serviceId",
                   "IfGenericRates", "IsNetMinimumDiscount", "isOwnAccountRate", "ResellerMarkupPercentage"}


def _pretty_charge(name: str) -> str:
    """FuelSurcharge -> 'Fuel surcharge'; VATCharge -> 'VAT charge' (acronyms kept)."""
    import re as _re
    s = _re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    s = _re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", s)
    words = []
    for i, w in enumerate(s.split()):
        if w.isupper() and len(w) > 1:
            words.append(w)                       # VAT, BFPO, AU stay as acronyms
        else:
            words.append(w.capitalize() if i == 0 else w.lower())
    return " ".join(words)


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
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                # Connection never opened: nothing reached World Options, safe to say so
                # (and safe to retry even for bookings).
                last_exc = e
                if attempt >= attempts - 1 and retryable:
                    break
                if not retryable:
                    raise WorldOptionsError(
                        "Could not connect to World Options; nothing was booked. Try again in a moment.")
                await asyncio.sleep(min(2 ** attempt, 6))
                continue
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
    if "woauthenticationexception" in low or "authentication failed" in low:
        return ("World Options could not log you in. Check the Meter Number, Key and "
                "Password in Shipping settings.")
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
        # Enterprise Library validation faults carry the real reasons in the
        # detail block ("Please provide phone for collection", ...).
        details = [(_text(vd, "Message") or "").strip()
                   for vd in _findall_direct(fault, "ValidationDetail")]
        details = [d for d in details if d]
        if details:
            raise WorldOptionsError("World Options needs more information: " + " ".join(details))
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
        if ("access token" in low or "authenticationexception" in low
                or "invalid_client" in low or "authentication failed" in low):
            raise WorldOptionsError(_friendly_fault(msg))
        raise WorldOptionsError(msg or f"World Options could not {context}.")
    return msg, notif


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------
def _carrier_from(service_code: str, quote_service_type: str) -> str:
    qt = (quote_service_type or "").strip()
    if qt:
        return canonical_carrier(qt) or qt.upper()
    up = (service_code or "").upper()
    for cr in _CARRIERS:
        if up.startswith(cr):
            return _PREFIX_TO_ENUM.get(cr) or canonical_carrier(cr) or cr
    return ""


def _dec(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Public operations
# ---------------------------------------------------------------------------
def _pkg_value(box: dict) -> str:
    v = box.get("custom_value")
    return _num(v) if v else "0"


async def quote(origin: dict, destination: dict, boxes: list,
                currency: str = "GBP", residential: bool = False,
                insurance: str = "", collection_dropoff: bool = False) -> dict:
    """Free, read-only price check across all carriers. Returns {options[]}.
    insurance = the cover amount to include in pricing; collection_dropoff asks
    for tariffs where the merchant drops the parcel at a shop."""
    o, d = origin or {}, destination or {}
    pkgs = ""
    for i, b in enumerate(boxes or [], start=1):
        pkgs += ("<rs:wsShippingDetails.PackageDetail>"
                 + _t("rs", "Breadth", _num(b.get("width")))
                 + _t("rs", "CustomValue", _pkg_value(b))
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
        # ShippingDetails (wsShippingDetails), XSD sequence order
        + "<wo:ShippingDetails>"
        + _t("rs", "Insurance", insurance)
        + (_b("rs", "IsCollectionDropoffRequired", True) if collection_dropoff else "")
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
        # Non-zero price components -> a human breakdown, largest first.
        breakdown = []
        if qd is not None:
            for ch in list(qd):
                name = _local(ch.tag)
                if name in _BREAKDOWN_SKIP or name in _BREAKDOWN_META:
                    continue
                v = _dec(ch.text)
                if v:
                    breakdown.append({"label": _pretty_charge(name), "amount": v})
            breakdown.sort(key=lambda x: -abs(x["amount"]))
        # Drop-off shops offered for this service (nearest first, capped).
        shops = []
        for shop in _findall_direct(_find(opt, "wsCollectionDropOffShops"), "wsDropOffShop")[:3]:
            shops.append({
                "id":       _text(shop, "ParcelShopNumber"),
                "name":     _text(shop, "Description"),
                "street":   (_text(shop, "HouseNo") + " " + _text(shop, "Street")).strip(),
                "city":     _text(shop, "City"),
                "postcode": _text(shop, "PostCode"),
                "distance": (_text(shop, "Distance") + " " + _text(shop, "DistanceUnit")).strip(),
                "lat":      _text(shop, "Latitude"),
                "lng":      _text(shop, "Longitude"),
            })
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
            "breakdown":         breakdown[:8],
            "shops":             shops,
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
        if "PNG" in lt:
            kind = "base64png"
        elif "PDF" in lt or not lt:
            kind = "base64pdf"
        else:
            kind = "base64bin"    # ZPL and friends: downloadable, never a fake PDF
        return {"type": kind, "value": img, "label_type": lt}
    return {}


def _customs_block(customs: dict) -> str:
    """The AdditionalShipmentDetail (customs dossier) for an international booking.
    Children in the XSD sequence order; goods lines likewise."""
    if not customs:
        return ""
    goods = ""
    for i, g in enumerate(customs.get("goods") or [], start=1):
        goods += ("<ad:wsAddlShipmentDetail.GoodsDetail>"
                  + _t("ad", "CountryCode", (g.get("country") or "GB").upper())
                  + _t("ad", "Description", str(g.get("description") or "")[:100])
                  + _t("ad", "HTSNumber", str(g.get("hs") or "")[:20])
                  + _t("ad", "ItemNumber", str(i))
                  + _t("ad", "Quantity", _num(g.get("quantity")))
                  + _t("ad", "UnitPrice", _num(g.get("unit_price")))
                  + _t("ad", "Wt", _num(g.get("weight")))
                  + "</ad:wsAddlShipmentDetail.GoodsDetail>")
    total = customs.get("total_value")
    return ("<wo:AdditionalShipmentDetail>"
            + _t("ad", "AdditionalComments", str(customs.get("comments") or "")[:200])
            + _t("ad", "CommercialInvoiceType",
                 customs.get("invoice_type") if customs.get("invoice_type") in INVOICE_TYPES else "Help_Me_Generate")
            + _t("ad", "EORINumber", str(customs.get("eori") or "")[:30])
            + _t("ad", "ExportReason",
                 customs.get("export_reason") if customs.get("export_reason") in EXPORT_REASONS else "Sale")
            + _t("ad", "ExportType",
                 {"Repair": "Temporary", "Exhibition": "Temporary",
                  "Return": "Re_export"}.get(customs.get("export_reason") or "", "Permanent"))
            + (f"<ad:GoodsDetails>{goods}</ad:GoodsDetails>" if goods else "")
            + _t("ad", "InvoiceNumber", str(customs.get("invoice_number") or "")[:40])
            + _b("ad", "IsPaperLess", True)
            + _t("ad", "ReceiverCompanyNumber", str(customs.get("receiver_company_number") or "")[:40])
            + _t("ad", "ReceiverTaxId", str(customs.get("receiver_tax_id") or "")[:40])
            + (_t("ad", "TotalCustomValue", _num(total)) if total else "")
            + _t("ad", "TradeTerm", str(customs.get("trade_term") or "")[:20])
            + "</wo:AdditionalShipmentDetail>")


async def book(option: dict, origin: dict, destination: dict, boxes: list,
               currency: str = "GBP", reference: str = "",
               ready_time: str = "", close_time: str = "",
               collection_option: str = "", insurance: str = "",
               signature: str = "", dropoff_shop: dict = None,
               customs: dict = None, description: str = "") -> dict:
    """Book (and CHARGE) the chosen quote option. Returns tracking + labels.
    ready_time/close_time/collection_option describe the collection; insurance
    is the cover amount; signature a SIGNATURE_OPTIONS value; dropoff_shop the
    parcel shop when the merchant drops off; customs the international dossier
    (see _customs_block); description a short contents summary."""
    option = option or {}
    service_code = option.get("service_type_code") or ""
    # Emit ONLY exact enum literals: WCF faults on case or membership mismatches,
    # and both elements are optional, so an unknown value is omitted instead.
    carrier = canonical_carrier(option.get("carrier_name") or "") \
        or canonical_carrier(_carrier_from(service_code, ""))
    pkg_type = option.get("package_type_code") or ""
    if pkg_type not in PACKAGE_TYPES_ENUM:
        pkg_type = ""
    cur = (currency or "GBP")[:3].upper()
    pkgs = ""
    for i, b in enumerate(boxes or [], start=1):
        pkgs += ("<sd:wsShippingDetail.PackageDetail>"
                 + _t("sd", "Breadth", _num(b.get("width")))
                 + _t("sd", "CustomValue", _pkg_value(b))
                 + _t("sd", "Height", _num(b.get("depth")))
                 + _t("sd", "ItemNumber", str(i))
                 + _t("sd", "Length", _num(b.get("length")))
                 + _t("sd", "Wt", _num(b.get("weight")))
                 + "</sd:wsShippingDetail.PackageDetail>")
    # ShippingDetail (wsShippingDetail) in the XSD sequence order.
    shop = dropoff_shop or {}
    dropoff = ""
    if shop:
        dropoff = ("<sd:CollectionDropOffInfo>"
                   + _t("sd", "City", shop.get("city"))
                   + _t("sd", "Description", shop.get("name"))
                   + _t("sd", "DropOffId", shop.get("id"))
                   + _t("sd", "PostCode", shop.get("postcode"))
                   + _t("sd", "Street", shop.get("street"))
                   + "</sd:CollectionDropOffInfo>")
    shipping = ("<wo:ShippingDetail>"
                + dropoff
                + _t("sd", "CollectionType", "Regular")
                + _t("sd", "Currency", cur)
                + _t("sd", "CustomerReference", (reference or "")[:40])
                + _t("sd", "Description", (description or "")[:100])
                + _t("sd", "Insurance", insurance)
                + (_b("sd", "IsCollectionDropoffRequired", True) if shop else "")
                + f"<sd:PackageDetails>{pkgs}</sd:PackageDetails>"
                + _t("sd", "PackageTypeCode", pkg_type)
                + _t("sd", "SenderVatNo", str((customs or {}).get("vat") or "")[:30])
                + _t("sd", "ServiceType", carrier)
                + _t("sd", "ServiceTypeCode", service_code)
                + "</wo:ShippingDetail>")
    # BillingDetail (wsBillingDetail): collection window + arrangement + delivery
    # signature + duties election, in the XSD sequence order. ReadyDate is
    # deliberately not sent (optional; its date format is undocumented).
    co = (collection_option or "").strip()
    if co and co not in COLLECTION_OPTIONS:
        co = ""
    sig = (signature or "").strip()
    if sig and sig not in SIGNATURE_OPTIONS.get(carrier.upper(), []):
        sig = ""
    duties = str((customs or {}).get("duties_payor") or "").strip()
    if duties and duties not in DUTIES_PAYORS:
        duties = ""
    billing = ""
    if ready_time or close_time or co or sig or duties:
        billing = ("<wo:BillingDetail>"
                   + _t("wo", "CloseTime", close_time)
                   + _t("wo", "CollectionOptions", co)
                   + _t("wo", "DeliverySignatureType", sig)
                   + _t("wo", "DutiesPayor", duties)
                   + _t("wo", "ReadyTime", ready_time)
                   + "</wo:BillingDetail>")
    # ShipmentBookingRequest in the XSD sequence order: AdditionalShipmentDetail,
    # AuthenticationDetail, BillingDetail, RecipientsDetails, SendersDetails, ShippingDetail
    inner = ("<tem:DoShipment><tem:shipment>"
             + _customs_block(customs or {})
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
