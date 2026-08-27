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
import re
import html as _htmllib
import asyncio
import logging
from datetime import datetime, timezone
from xml.sax.saxutils import escape as _xml_escape
import xml.etree.ElementTree as ET

import base64
import httpx
import ipaddress
from urllib.parse import urljoin, urlparse

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
# "ALL" is a real enum member, but it means "any carrier" on a request and is never
# an answer to "who is carrying this", so it is kept out of the resolution table.
_CANON_CARRIER = {v.upper(): v for v in SERVICE_COMPANY_ENUM if v != "ALL"}


def canonical_carrier(code: str) -> str:
    """The exact enum literal for a carrier, '' when it is not a member."""
    return _CANON_CARRIER.get((code or "").strip().upper(), "")


# Map a booking service code (wsServiceTypes) onto its carrier, used only as a
# fallback when the quote reply does not name the carrier itself. Prefix EVRI
# maps to EVRISEND (bare 'EVRI' is not an enum member).
_CARRIERS = ["DHLPARCEL", "DHL", "FEDEX", "UPS", "TNT", "PALLETWAYS", "YODEL",
             "DXEXPRESS", "DX_", "HERMES", "DSV", "EXFREIGHT", "EXF_", "GLOBALTRANZ",
             "CITYSPRINT", "EVRISEND", "EVRICORPORATE", "EVRI", "TUFFNELLS", "ROYALMAIL",
             "DPD", "UKMAIL"]
# Prefixes that are not themselves enum members map onto the one that is. UKMail
# is not in wsServiceCompanyTypes at all, so it stays a display-only label.
_PREFIX_TO_ENUM = {"EVRI": "EVRISEND", "PALLETWAYS": "Palletways", "EXFREIGHT": "EXFreight",
                   "EXF_": "EXFreight", "DX_": "DXEXPRESS", "UKMAIL": "UKMAIL"}

# The wsServiceTypes enum, verbatim from the booking WSDL (wo_xsd6). The quote
# reply's wsServiceTypeCode is a plain xs:string, but booking's ServiceTypeCode is
# TYPED to this enum, so a code outside this set cannot be booked at all. 145 of
# the 146 members carry their carrier as a prefix ("UPS_Standard", "DHL_DOMESTIC_
# EXPRESS", "RoyalMail_Tracked_24_Hours"), which is what makes the carrier knowable
# from the service code alone rather than guessed.
SERVICE_TYPES_ENUM = frozenset({
    "ALL", "Fedex_International_First", "Fedex_International_Priority",
    "Fedex_International_Priority_Freight", "FedEx_NextDay", "FedEx_10_AM", "FedEx_9_AM",
    "FedEx_12_Noon", "Fedex_International_Priority_Express", "Fedex_International_Economy",
    "Fedex_Regional_Economy", "Fedex_Regional_Economy_Freight",
    "Fedex_International_Economy_Freight", "FedEx_First", "FedEx_Priority",
    "FedEx_Priority_Express", "UPS_Express", "UPS_Standard", "UPS_Express_Saver",
    "UPS_Express_AP", "UPS_Standard_AP", "UPS_Express_Saver_AP", "DHL_Worldwide_Express",
    "DHL_ECONOMY_SELECT", "DHL_DOMESTIC_EXPRESS", "DHL_WORLDWIDE_EXPRESS_900",
    "DHL_WORLDWIDE_EXPRESS_1200", "DHL_DOMESTIC_EXPRESS_900", "DHL_DOMESTIC_EXPRESS_1200",
    "YODEL_EXPRESS_24", "YODEL_EXPRESS_48", "YODEL_EXPRESS_NI", "YODEL_PRIORITY_1000",
    "YODEL_PRIORITY_1200", "YODEL_SATURDAY_1000", "YODEL_SATURDAY", "YODEL_EXPRESS_ISLE",
    "YODEL_HOME_24", "YODEL_HOME_NI", "YODEL_HOME_24BT", "YODEL_HOME_48", "YODEL_HOME_72",
    "YODEL_HOME_72_NI", "YODEL_HOME_SATURDAY", "YODEL_HOME_EXPRESS_ISLE",
    "YODEL_HOME_PACKET_SERVICE", "TNT_Global_Express", "TNT_Economy_Express",
    "TNT_Economy_Express_1200", "TNT_Next_Day_Delivery", "TNT_Next_Day_1200",
    "TNT_Next_Day_1000", "TNT_Next_Day_0900", "TNT_Saturday_Delivery", "TNT_Saturday_1200",
    "TNT_Saturday_1000", "TNT_Saturday_0900", "TNT_Global_Express_1200",
    "TNT_Global_Express_1000", "TNT_Global_Express_0900", "TNT_AirFrieght_D2D",
    "TNT_AirFrieght_D2A", "UKMail_Express_UK", "UKMail_Express_UK_AM",
    "UKMail_Express_UK_1030AM", "UKMail_Express_UK_0900AM", "UKMail_Express_UK_Saturday",
    "UKMail_Express_UK_Saturday_1030AM", "UKMail_Express_UK_Saturday_0900AM",
    "UKMail_Express_UK_Bagit", "UKMail_Express_UK_AM_Bagit",
    "UKMail_Express_UK_1030AM_Bagit", "UKMail_Express_UK_0900AM_Bagit",
    "UKMail_Express_UK_Saturday_Bagit", "UKMail_European_Road",
    "DXExpress_B2C_Next_Day_Business", "DXExpress_B2C_Next_Day_Business_Pre_12_PM",
    "DXExpress_B2C_Saturday_Delivery", "DXExpress_B2C_Saturday_Pre_12",
    "DXExpress_B2B_Next_Day_Home_Signature",
    "DXExpress_B2B_Next_Day_Home_Signature_Pre_1PM",
    "DXExpress_B2B_Saturday_Delivery_Signature", "DXExpress_B2B_Next_Day_Home_No_Signature",
    "DXExpress_B2B_Saturday_Delivery_Home_No_Signature", "Hermes_Stated_Day_Sunday",
    "Hermes_Next_Day_Service", "Hermes_Signature", "Hermes_Household_Signature",
    "Hermes_UK48", "Hermes_UK24", "Hermes_Returns_Hermes", "Hermes_Parcel_Shop",
    "Hermes_Courier_Collection_48", "Hermes_LL", "Hermes_SUN", "DSV_Domestic",
    "DSV_Europe_By_Road", "EXFreight_Freight", "GlobalTranz_Freight",
    "CitySprint_Priority_Bike", "CitySprint_Priority_Van", "CitySprint_Priority_Transit",
    "CitySprint_PushBike", "CitySprint_Bike", "CitySprint_Small_Van",
    "CitySprint_Large_Van", "Evri_CC_Ship_to_Door_DDP", "Evri_CC_Ship_to_Door_DDU",
    "Evri_CC_Ship_to_Door_UK48", "Evri_CC_Ship_to_Shop_DDP", "Evri_CC_Ship_to_Shop_DDU",
    "Evri_DI_ParcelShop_Returns_UK", "Evri_DI_Ship_to_Door_DDP", "Evri_DI_Ship_to_Door_DDU",
    "Evri_DI_Ship_to_Door_UK_Light_and_Large", "Evri_DI_Ship_to_Door_UK_Sunday",
    "Evri_DI_Ship_to_Door_UK24", "Evri_DI_Ship_to_Door_UK48", "Evri_DI_Ship_to_Shop_DDP",
    "Evri_DI_Ship_to_Shop_DDU", "Evri_DI_Ship_to_Shop_UK", "Evri_DS_Ship_to_Door_UK24",
    "Evri_DS_Ship_to_Door_UK48", "Evri_DS_Ship_to_Door_DDP", "Evri_DS_Ship_to_Door_DDU",
    "Evri_DS_Ship_to_Shop_DDP", "Evri_DS_Ship_to_Shop_DDU", "Tuffnells_Next_Day_Service",
    "Tuffnells_Next_Day_Before_Noon", "Tuffnells_Next_Day_Before_1030",
    "Tuffnells_Next_Day_Before_0930", "Tuffnells_Saturday", "Tuffnells_Saturday_AM",
    "RoyalMail_Tracked_24_Hours", "RoyalMail_Tracked_48_Hours",
    "RoyalMail_Priority_Tracked_Signed", "RoyalMail_Priority_Tracked", "DPD_NextDay",
    "DPD_NextDay_AM", "DPD_NextDay_Noon", "DPD_TwoDay", "DPD_Saturday", "DPD_Saturday_AM",
    "DPD_Saturday_Noon", "DPD_Sunday", "DPD_Sunday_AM",
})

# Longest first, so DHLPARCEL is tested before DHL and EVRICORPORATE before EVRI.
# UKMail runs 13 services but is NOT a wsServiceCompanyTypes member, so it can be
# named on screen and never sent as a booking ServiceType.
_SERVICE_PREFIXES = sorted(
    [("EXFREIGHT", "EXFreight"), ("GLOBALTRANZ", "GLOBALTRANZ"), ("CITYSPRINT", "CITYSPRINT"),
     ("EVRICORPORATE", "EVRICORPORATE"), ("DXEXPRESS", "DXEXPRESS"), ("ROYALMAIL", "ROYALMAIL"),
     ("PALLETWAYS", "Palletways"), ("TUFFNELLS", "TUFFNELLS"), ("DHLPARCEL", "DHLPARCEL"),
     ("UKMAIL", "UKMAIL"), ("HERMES", "HERMES"), ("EVRISEND", "EVRISEND"), ("YODEL", "YODEL"),
     ("FEDEX", "FEDEX"), ("EVRI", "EVRISEND"), ("DHL", "DHL"), ("UPS", "UPS"),
     ("TNT", "TNT"), ("DPD", "DPD"), ("DSV", "DSV")],
    key=lambda p: -len(p[0]))


def _squash(code: str) -> str:
    """'UPS_Express_Saver' -> 'UPSEXPRESSSAVER'. Separators vary between the fields
    World Options fills, so they are removed before any prefix is matched."""
    return re.sub(r"[\s_\-./]+", "", (code or "")).upper()


def _service_carrier(code: str) -> str:
    """The carrier that runs a wsServiceTypes code, by its prefix."""
    up = _squash(code)
    for pre, enum in _SERVICE_PREFIXES:
        if up.startswith(pre):
            return enum
    return ""


# Every bookable service resolved to a carrier at import, so a code World Options
# sends can be answered from a table instead of guessed at.
SERVICE_CARRIER = {_squash(s): _service_carrier(s) for s in SERVICE_TYPES_ENUM if s != "ALL"}
_unmapped = sorted(s for s in SERVICE_TYPES_ENUM if s != "ALL" and not SERVICE_CARRIER.get(_squash(s)))
if _unmapped:  # a new carrier in a future WSDL: name it rather than show a blank
    logger.warning("world options: %d service codes have no carrier prefix: %s",
                   len(_unmapped), ", ".join(_unmapped[:8]))

# How the label should come back. Free text in the XSD with no enum to copy, so
# this matches the LabelType the service itself reports on the reply. Overridable
# without a deploy in case this account expects a different word.
LABEL_DELIVERY = os.environ.get("WO_LABEL_DELIVERY", "").strip()

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

# Each carrier's own "my packaging" member of wsPackageTypes, for when the quote
# reply names a rate-only type that booking will not accept.
CARRIER_PACKAGE_TYPE = {
    "UPS": "UPS_My_Packaging", "FEDEX": "Fedex_Your_Packaging",
    "DHL": "DHL_NonDocument", "DHLPARCEL": "DHL_NonDocument",
    "YODEL": "YODEL_NonDocument", "TNT": "TNT_NonDocument",
    "UKMAIL": "UKMAIL_NonDocument", "DXEXPRESS": "DXExpress_Parcel",
    "HERMES": "Hermes_Parcel", "EVRISEND": "Evri_Parcel", "EVRICORPORATE": "Evri_Parcel",
    "DSV": "DSV_LTL", "EXFREIGHT": "EXF_LTL", "GLOBALTRANZ": "GlobalTranz_LTL",
    "CITYSPRINT": "CitySprint_Parcel", "TUFFNELLS": "Tuffnells_Parcel",
    "ROYALMAIL": "RoyalMail_Parcel", "DPD": "DPD_Parcel",
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
    "EXFREIGHT": "EXFreight", "GLOBALTRANZ": "GlobalTranz", "UKMAIL": "UK Mail",
}


def shopify_carrier(carrier_code: str) -> str:
    """A Shopify-recognizable tracking company for a WO carrier enum value. Falls
    back to the on-screen name rather than the raw enum: Shopify prints whatever it
    is given in the customer's shipping email, and "EVRICORPORATE" is not a company
    anyone has heard of."""
    up = (carrier_code or "").strip().upper()
    if up in SHOPIFY_CARRIER_NAMES:
        return SHOPIFY_CARRIER_NAMES[up]
    if up in CARRIER_DISPLAY:
        return CARRIER_DISPLAY[up]
    return ""


# How a carrier should READ on screen (distinct from the booking enum and from
# the Shopify tracking-company name).
CARRIER_DISPLAY = {
    "ROYALMAIL": "Royal Mail", "DPD": "DPD", "EVRISEND": "Evri", "EVRICORPORATE": "Evri",
    "HERMES": "Evri", "UPS": "UPS", "FEDEX": "FedEx", "TNT": "TNT", "DHL": "DHL",
    "DHLPARCEL": "DHL Parcel", "YODEL": "Yodel", "CITYSPRINT": "CitySprint",
    "DXEXPRESS": "DX", "TUFFNELLS": "Tuffnells", "PALLETWAYS": "Palletways",
    "DSV": "DSV", "EXFREIGHT": "EXFreight", "GLOBALTRANZ": "GlobalTranz",
    "UKMAIL": "UKMail", "EVRI": "Evri",
}


def carrier_display(code: str) -> str:
    return CARRIER_DISPLAY.get((code or "").strip().upper(), (code or "").strip())


# World Options puts DISPLAY HTML inside data fields ("Wed, 12 Aug 2026<br/>End of
# business day"), so every string off the wire is cleaned before it reaches the UI.
_TAG_RE = re.compile(r"<[^>]*>")
_WS_RE = re.compile(r"\s+")


def _wo_lines(s: str) -> list:
    """Split a WO string on its embedded tags into clean text lines."""
    text = _htmllib.unescape(str(s or ""))
    return [_WS_RE.sub(" ", p).strip(" ,;|") for p in _TAG_RE.split(text) if p and p.strip(" ,;|")]


def _tidy_time(s: str) -> str:
    """'15:00 PM' -> '15:00' (WO tacks a meridiem onto 24-hour times)."""
    t = (s or "").strip()
    m = re.match(r"^(\d{1,2}):(\d{2})\s*([AaPp])\.?[Mm]\.?$", t)
    if m and int(m.group(1)) > 12:
        return f"{m.group(1)}:{m.group(2)}"
    return t


def _tidy_date(s: str) -> str:
    """'Wed, 12 Aug 2026' -> 'Wed 12 Aug' (the year only when it is not this one)."""
    d = _WS_RE.sub(" ", (s or "").replace(",", " ")).strip()
    year = str(datetime.now(timezone.utc).year)
    if d.endswith(" " + year):
        d = d[: -(len(year) + 1)].strip()
    return d


# "03 DHL Domestic Express" -> code 03. A ':' is NOT a separator here, or a
# time-definite name like "12:00 Guaranteed" would lose its hour.
_CODE_PREFIX_RE = re.compile(r"^\s*(\d{1,3})[\s.\-]+(?!\d)")
# Carrier names as they appear inside service names, longest/most specific first.
_L = r"(?<![a-z])%s(?![a-z])"
_CARRIER_WORDS = [
    (r"royal\s*mail", "ROYALMAIL"), (r"dhl\s*parcel", "DHLPARCEL"), (_L % "dhl", "DHL"),
    (_L % "ups", "UPS"), (r"fedex|federal\s*express", "FEDEX"), (_L % "tnt", "TNT"),
    (_L % "dpd", "DPD"), (r"evri\s*corporate", "EVRICORPORATE"),
    (_L % "evri", "EVRISEND"), (r"hermes", "HERMES"), (r"yodel", "YODEL"),
    (r"citysprint", "CITYSPRINT"), (r"palletways", "PALLETWAYS"), (r"tuffnells", "TUFFNELLS"),
    (r"globaltranz", "GLOBALTRANZ"), (_L % "dsv", "DSV"),
    (r"dx\s*express", "DXEXPRESS"), (_L % "dx", "DXEXPRESS"),
    (r"uk\s*mail", "UKMAIL"), (r"exfreight", "EXFreight"), (_L % "exf", "EXFreight"),
]


def carrier_from_text(*texts) -> str:
    """Find a carrier named inside any WO string (their service names carry it:
    '03 DHL Domestic Express'). Returns the enum value, or ''."""
    blob = " ".join(str(t or "") for t in texts).lower()
    blob = re.sub(r"[_\-./]+", " ", blob)
    for pat, enum in _CARRIER_WORDS:
        if re.search(pat, blob):
            return enum
    return ""


def _split_service_name(name: str, carrier_code: str) -> tuple:
    """'03 DHL Domestic Express' + DHL -> ('03', 'Domestic Express').
    Strips WO's leading product code and the carrier word the chip already shows."""
    raw = _WS_RE.sub(" ", re.sub(r"_+", " ", str(name or ""))).strip()
    code = ""
    m = _CODE_PREFIX_RE.match(raw)
    if m:
        code, raw = m.group(1), raw[m.end():].strip()
    label = carrier_display(carrier_code)
    for word in sorted(filter(None, {label, carrier_code, (carrier_code or "").title()}),
                       key=len, reverse=True):
        low, w = raw.lower(), word.lower()
        if low.startswith(w) and (len(raw) == len(w) or not raw[len(w)].isalnum()):
            raw = raw[len(word):].strip(" -")
            break
    return code, raw


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
# Only FedEx and DHL have a "no signature" member in wsSignatureTypes. UPS has
# none: its only choices are UPS_Signature_Required and UPS_Adult. So a cheaper
# no-signature price can only be OFFERED, and only booked, for a carrier listed
# here. Sending one carrier's literal on another's service is what "Value cannot
# be null" was: the service looks up its own mapping, finds nothing, and throws.
NO_SIGNATURE_BY_CARRIER = {
    "FEDEX": "Fedex_No_Signature_Required",
    "DHL":   "DHL_No_Signature_Required",
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
    """Carries World Options' own message so the UI can show the real cause, plus
    the request that caused it. The envelope is attached because their errors name
    a .NET parameter, not a field, and without the request there is nothing to
    match it against."""

    def __init__(self, message, envelope: str = "", raw: str = ""):
        super().__init__(message)
        self.envelope = envelope        # redacted, safe to show the merchant
        self.raw = raw                  # their fault text, verbatim


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


def _base_allowed(b: str) -> bool:
    """The SOAP base may only be a World Options host over https. The envelope
    carries the account Key/Password and the recipient's address, so a base
    pointed at an attacker host (or a link-local metadata IP) would exfiltrate
    both on every quote and booking - and that string is settable from the
    Settings form. Host allowlist, not substring: 'worldoptions.co.uk.evil.com'
    must not pass."""
    try:
        from urllib.parse import urlparse
        u = urlparse(b)
        if u.scheme != "https" or not u.hostname:
            return False
        host = u.hostname.lower()
        return host == "worldoptions.co.uk" or host == "worldoptions.com" \
            or host.endswith(".worldoptions.co.uk") or host.endswith(".worldoptions.com")
    except Exception:
        return False


def set_base_url(url) -> None:
    b = ((url or DEFAULT_BASE).strip() or DEFAULT_BASE).rstrip("/")
    # A base that is not a World Options https host (stale REST host, a typo,
    # or a hostile value pasted into Settings) falls back to the default rather
    # than being trusted with the credentials the envelope carries.
    if _REST_HOST in b or not _base_allowed(b):
        b = DEFAULT_BASE
    _state["base_url"] = b


def meter_last4() -> str:
    """The METER number's last four, and only ever that.

    It used to fall back to the API KEY when no meter was set - a supported
    state, since configured() accepts either - so a screen that promises
    "connected + last4" quietly showed four characters of a live secret to
    anyone who can open the shipping settings. A meter is not secret; a key
    is. With no meter there is nothing to show, so it says so."""
    v = _state["meter"]
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


# Credentials AND personal data: the envelope carries the customer's address,
# phone, email and any tax identifiers, none of which belong in a log file. The
# element names are kept so the shape of the request stays readable.
_REDACT_EL_RE = re.compile(
    r"<(m|wo|sd|ad):(Key|Password|MeterNumber|SubUserKey|Email|OtherEmailAddress"
    r"|RecipientEmailAddress|Phone|PhoneDialCode|Fax|Address1|Address2|Address3"
    r"|Name|Company|Postalcode|PostalCode|PostCode|EORINumber|ReceiverTaxId"
    r"|ReceiverCompanyNumber|SenderVatNo|DutiesAccNumber|TransportationAccNumber"
    r"|PersonalMessage|City|State|State_Code|DeliveryCity|DeliveryPostCode"
    r"|CollectionCity|CollectionPostCode)>([^<]*)</\1:\2>")


def _redacted(xml: str) -> str:
    """The envelope with credentials and personal data removed, safe for a log.
    Blank values stay visibly blank: which fields were EMPTY is the whole point of
    reading the thing."""
    def sub(m):
        body = "" if not m.group(3) else "***"
        return f"<{m.group(1)}:{m.group(2)}>{body}</{m.group(1)}:{m.group(2)}>"
    return _REDACT_EL_RE.sub(sub, xml)


def _ts(prefix: str, name: str, value) -> str:
    """Like _t, but ALWAYS emits the element, empty when there is no value. Use for
    free-text fields the service reads unconditionally: a UK address routinely has
    no county and a consumer has no company, and null is not the same as blank."""
    v = "" if value is None else str(value)
    return f"<{prefix}:{name}>{_xml_escape(v)}</{prefix}:{name}>"


# Counties and regions people actually type into an address, and the codes the
# carriers accept for them. Not a world list: the ones this merchant ships to.
_STATE_CODES = {
    # United Kingdom - carriers want the ISO region code, or nothing at all.
    "england": "ENG", "scotland": "SCT", "wales": "WLS", "cymru": "WLS",
    "northern ireland": "NIR",
    # Ireland - ISO 3166-2:IE, which is what Shopify's province_code gives.
    "dublin": "D", "co dublin": "D", "county dublin": "D",
    "cork": "CO", "co cork": "CO", "county cork": "CO",
    "galway": "G", "co galway": "G", "county galway": "G",
    "limerick": "LK", "kerry": "KY", "mayo": "MO", "donegal": "DL",
    "kildare": "KE", "meath": "MH", "wicklow": "WW", "wexford": "WX",
    "waterford": "WD", "clare": "CE", "tipperary": "TA", "kilkenny": "KK",
    "louth": "LH", "sligo": "SO", "westmeath": "WH", "offaly": "OY",
    "laois": "LS", "cavan": "CN", "roscommon": "RN", "monaghan": "MN",
    "carlow": "CW", "longford": "LD", "leitrim": "LM",
    # US states and Canadian provinces, because those are countries where the
    # carrier REQUIRES a subdivision: dropping an unmappable one there would
    # break the address rather than tidy it. Shopify supplies the two-letter
    # code for both, so this is the belt to that braces.
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI",
    "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "alberta": "AB", "british columbia": "BC", "manitoba": "MB",
    "new brunswick": "NB", "newfoundland and labrador": "NL", "nova scotia": "NS",
    "ontario": "ON", "prince edward island": "PE", "quebec": "QC",
    "saskatchewan": "SK", "northwest territories": "NT", "nunavut": "NU",
    "yukon": "YT",
}


# Countries whose carriers genuinely require a subdivision, and validate it
# against their own list. Everywhere else the postcode routes the parcel and a
# subdivision is optional - which matters, because a code the carrier does not
# recognise is REFUSED, while sending none is explicitly fine.
_STATE_REQUIRED = {"US", "CA", "MX", "AU", "BR", "IN", "CN", "JP", "IT", "ES", "AR"}


def _state_code(value, country="") -> str:
    """A state/province the carrier will actually accept, or nothing.

    Carriers cap this field at 5 alphanumeric characters, and reject the whole
    booking when it is longer - "Invalid sold to state province code. Valid
    length is 0 to 5 alphanumeric". A person filling in an address types the
    county the way they say it ("England", "Co. Dublin", "Tyne and Wear"), and
    every one of those is too long.

    So: use it as-is when it already fits, translate it when we know the code,
    and otherwise send NOTHING. Empty is explicitly valid, and for a GB or IE
    address the postcode identifies the destination on its own - whereas a
    truncated "Dubli" would be wrong data dressed up as right."""
    raw = ("" if value is None else str(value)).strip()
    if not raw:
        return ""
    cc = str(country or "").strip().upper()
    if cc and cc not in _STATE_REQUIRED:
        # Measured, not assumed. Every UK order in this store ships on UPS with
        # province "ENG" and goes through; the Irish ones are refused with
        # "Invalid sold to state province code", and the ONE Irish order that
        # shipped went by DHL, which does not run this check. Shopify gives an
        # Irish county the ISO 3166-2 code ("Dublin" -> "D") and UPS does not
        # accept it. The message blames the length, but a one-character code is
        # inside 0 to 5: the operative word is Invalid, and the length note is
        # boilerplate UPS appends either way.
        return ""
    if len(raw) <= 5 and raw.isalnum():
        return raw.upper() if len(raw) <= 3 else raw
    key = re.sub(r"[^a-z ]", "", raw.lower()).replace("  ", " ").strip()
    hit = _STATE_CODES.get(key) or _STATE_CODES.get(key.replace("county ", "").replace("co ", ""))
    if hit:
        return hit
    if cc in _STATE_REQUIRED:
        # Loud, because here it matters: this country's carriers demand a
        # subdivision and we are about to send none.
        logger.error("world options: %s needs a state/province and %r maps to no code "
                     "we know - the address may be refused", cc, raw[:40])
    else:
        logger.info("world options: dropping an unusable state/province %r "
                    "(over 5 characters and not a county we know a code for)", raw[:40])
    return ""


def _b(prefix: str, name: str, value: bool) -> str:
    return f"<{prefix}:{name}>{'true' if value else 'false'}</{prefix}:{name}>"


def _num(v) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "0"
    return str(int(f)) if f == int(f) else repr(f)


def _auth_block(full: bool = False) -> str:
    # wsAuthenticationDetail children, alphabetical: Key, MeterNumber, Password,
    # PluginCode, SubUserKey, WebLeadCompanyName, WebLeadPostalCode.
    # `full` sends the three trailing nillable strings as empty rather than omitting
    # them (omitted = null on the server). Only booking sets it: quoting works as it
    # is, and ShipmentService is different code from RateService.
    return ("<wo:AuthenticationDetail>"
            + _t("m", "Key", _state["key"])
            + _t("m", "MeterNumber", _state["meter"])
            + _t("m", "Password", _state["password"])
            + _t("m", "PluginCode", _state["plugin"] or "Web_Service")
            + (_ts("m", "SubUserKey", "")
               + _ts("m", "WebLeadCompanyName", "")
               + _ts("m", "WebLeadPostalCode", "") if full else "")
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
                # No redirects: a courier SOAP endpoint never legitimately
                # redirects, and following one to an internal/attacker host
                # would carry the credentials and address in the envelope
                # straight there. The base is host-allowlisted; keep it that way.
                async with httpx.AsyncClient(follow_redirects=False) as client:
                    resp = await client.post(url, content=payload, headers=headers, timeout=45.0)
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                # Connection never opened: nothing reached World Options, safe to say so
                # (and safe to retry even for bookings).
                last_exc = e
                if attempt >= attempts - 1 and retryable:
                    break
                if not retryable:
                    err = WorldOptionsError(
                        "Could not connect to World Options; nothing was booked. Try again in a moment.")
                    err.not_sent = True     # nothing reached them: retrying risks nothing
                    raise err
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


SOAP_MAX_BYTES = 24 * 1024 * 1024      # a label reply, not a data feed


def _parse(resp: httpx.Response, url: str = "") -> ET.Element:
    # A 404 (or other non-fault error) usually means the wrong endpoint, not a real
    # SOAP reply. Say so, and name the host so a misconfiguration is obvious.
    if resp.status_code == 404:
        raise WorldOptionsError(
            f"World Options did not recognise the service address ({url or _state['base_url']}). "
            "This usually means the wrong web-service URL. Expected the shipping web service at "
            f"{DEFAULT_BASE}.")
    body = resp.content or b""
    if len(body) > SOAP_MAX_BYTES:
        # Parsing is what turns bytes into memory; refuse before that, not after.
        raise WorldOptionsError(
            f"World Options returned {len(body) // (1024 * 1024)}MB, which is far larger than "
            "any shipping reply. Nothing was processed.")
    try:
        root = ET.fromstring(body)
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
        raise WorldOptionsError(_friendly_fault(reason), raw=reason)
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
        raise WorldOptionsError(msg or f"World Options could not {context}.", raw=msg)
    return msg, notif


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------
_CARRIERS_BY_LENGTH = sorted(_CARRIERS, key=len, reverse=True)


def _prefix_carrier(code: str) -> str:
    """The carrier a code starts with. Separators are removed first: World Options
    writes the same carrier as DHL_Parcel, DHL-Parcel and DHLParcel across fields,
    and a raw startswith would match those against the shorter DHL."""
    up = _squash(code)
    for cr in _CARRIERS_BY_LENGTH:
        bare = cr.rstrip("_")
        if up.startswith(bare):
            return _PREFIX_TO_ENUM.get(cr) or _PREFIX_TO_ENUM.get(bare) or canonical_carrier(bare) or bare
    return ""


def _carrier_from(service_code: str, quote_service_type: str,
                  package_type_code: str = "", service_name: str = "") -> str:
    """Who is actually carrying it. World Options names the carrier in a different
    field on every account, so each signal is tried in order of how much it can be
    trusted: their own carrier field, the service code prefix, the package type
    (UPS_My_Packaging / DHL_NonDocument / Fedex_Your_Packaging always carry it),
    then any carrier word inside the service text."""
    qt = (quote_service_type or "").strip()
    if qt and qt.upper() != "ALL":
        # Recognise it or ignore it. Passing an unrecognised string through made it
        # the carrier name AND blocked every other signal, and it cannot be booked.
        got = canonical_carrier(qt) or _prefix_carrier(qt) or carrier_from_text(qt)
        if got:
            return got
    # The service code is definitive when it is a real wsServiceTypes member.
    got = SERVICE_CARRIER.get(_squash(service_code))
    if got:
        return got
    # Then the service name, which usually spells the carrier out. It is tried
    # before the package type because packaging is not provenance: a DHL Parcel
    # service can be quoted under a plain DHL_NonDocument box.
    return (_prefix_carrier(service_code)
            or carrier_from_text(service_name)
            or _prefix_carrier(package_type_code)
            or carrier_from_text(service_code, package_type_code))


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
                insurance: str = "", collection_dropoff: bool = False,
                shipment_mode: str = "", delivery_dropoff: bool = False,
                signature_type: str = "", service_name: str = "ALL",
                package_type: str = "Any_NonDocument") -> dict:
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
        + _t("m", "DeliveryState", _state_code(d.get("state"), d.get("country")))
        + _b("m", "IsResidential", bool(residential))
        + "</wo:RecipientDetails>"
        # SenderDetails (wsCollectionDetail), alpha
        + "<wo:SenderDetails>"
        + _t("m", "CollectionCity", o.get("city"))
        + _t("m", "CollectionCountryCode", (o.get("country") or "").upper())
        + _t("m", "CollectionCountryState", _state_code(o.get("state"), o.get("country")))
        + _t("m", "CollectionPostCode", o.get("postcode"))
        + "</wo:SenderDetails>"
        # ShippingDetails (wsShippingDetails), XSD sequence order.
        # PackageType and ShipmentType MUST be sent explicitly: WCF gives an
        # omitted enum its FIRST member, which here means every parcel was quoted
        # as a "Fedex_Box" on an "Export" shipment - that silently hides domestic
        # road services such as UPS Standard.
        + "<wo:ShippingDetails>"
        + _t("rs", "Insurance", insurance)
        + (_b("rs", "IsCollectionDropoffRequired", True) if collection_dropoff else "")
        # Access Point services (UPS_Express_Saver_AP and friends) are only offered
        # when the quote asks to deliver to a pickup shop instead of the door.
        + (_b("rs", "IsDeliveryDropoffRequired", True) if delivery_dropoff else "")
        + f"<rs:PackageDetails>{pkgs}</rs:PackageDetails>"
        + _t("rs", "PackageType", package_type or "Any_NonDocument")
        + _t("rs", "ServiceName", service_name or "ALL")
        + _t("rs", "ServiceTypeName", "ALL")
        + _t("rs", "ShipmentType", shipment_mode or "Domestic")
        # SignatureType is a non-nillable enum, so leaving it out means WCF picks
        # its first member (Fedex_Adult). Sending an explicit value is the only
        # way to say "no signature needed", which cheaper tiers may require.
        + _t("rs", "SignatureType", signature_type)
        + "</wo:ShippingDetails>"
        + "</tem:request></tem:GetAllServicesAndRates>"
    )
    try:
        root = await _soap_call("RateService", "http://tempuri.org/IRateService/GetAllServicesAndRates", inner)
    except WorldOptionsError as e:
        e.envelope = _redacted(inner)
        logger.error("world options: rate request rejected: %s\nEnvelope sent:\n%s", e, e.envelope)
        raise
    reply = _find(root, "GetAllServicesAndRatesResult")
    try:
        if reply is None:
            raise WorldOptionsError("World Options returned no rate result.")
        _reply_status(reply, "price this shipment")
    except WorldOptionsError as e:
        # Same rule the booking has followed since it was written: their errors
        # name a .NET parameter rather than a field, so the envelope IS the
        # evidence, and a quote is what fails FIRST. Without this, an operator
        # is told a field is wrong and has no way to see which one.
        e.envelope = _redacted(inner)
        e.sent = True
        logger.error("world options: rate request answered FAILED: %s\nEnvelope sent:\n%s",
                     e, e.envelope)
        raise
    cur = (currency or "GBP")[:3].upper()
    options = []
    for opt in _findall_direct(reply, "wsAvailableServicesAndRates"):
        qd = _find(opt, "wsQuoteDetails")
        amount = _dec(_text(qd, "TotalNetCharge")) if qd is not None else None
        service_code = _text(opt, "wsServiceTypeCode")
        carrier = _carrier_from(service_code,
                                _text(qd, "ServiceType") if qd is not None else "",
                                _text(opt, "wsPackageTypeCode"),
                                _text(opt, "wsServiceTypeName"))
        # Non-zero price components -> a human breakdown, largest first.
        breakdown = []
        vat = None
        if qd is not None:
            for ch in list(qd):
                name = _local(ch.tag)
                if name in _BREAKDOWN_SKIP or name in _BREAKDOWN_META:
                    continue
                v = _dec(ch.text)
                if name == "VATCharge":
                    vat = v or 0.0
                if v:
                    breakdown.append({"label": _pretty_charge(name), "amount": v})
            breakdown.sort(key=lambda x: -abs(x["amount"]))
        def _shops(container_name):
            out = []
            for shop in _findall_direct(_find(opt, container_name), "wsDropOffShop")[:3]:
                out.append({
                    "id":       _text(shop, "ParcelShopNumber"),
                    "name":     _text(shop, "Description"),
                    "street":   (_text(shop, "HouseNo") + " " + _text(shop, "Street")).strip(),
                    "city":     _text(shop, "City"),
                    "postcode": _text(shop, "PostCode"),
                    "distance": (_text(shop, "Distance") + " " + _text(shop, "DistanceUnit")).strip(),
                    "lat":      _text(shop, "Latitude"),
                    "lng":      _text(shop, "Longitude"),
                })
            return out
        delivery_shops = _shops("wsDeliveryDropOffShops")
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
        # WO's own carrier field first; failing that, the carrier named inside the
        # service text ("03 DHL Domestic Express" is all we get on some accounts).
        ws_service_code = _text(opt, "wsServiceCode")
        raw_name = _text(opt, "wsServiceTypeName") or service_code
        if not carrier:
            carrier = carrier_from_text(raw_name, service_code, ws_service_code)
        product_code, nice_name = _split_service_name(raw_name, carrier)
        deliv = _wo_lines(_text(opt, "wsDeliveryDateTime"))
        pick = _wo_lines(_text(opt, "wsPickupDateTime"))
        options.append({
            "service_type_code": service_code,
            "service_code":      ws_service_code,
            "package_type_code": _text(opt, "wsPackageTypeCode"),
            "carrier_name":      carrier,                      # enum, used to book
            "carrier_label":     carrier_display(carrier),     # what the merchant reads
            "service_name":      nice_name or raw_name,
            "service_full":      raw_name,
            "product_code":      product_code,
            "amount":            amount,                       # TotalNetCharge, VAT included
            "vat":               vat,
            "amount_ex_vat":     (None if amount is None else
                                  round(amount - (vat or 0.0), 2)),
            "currency":          cur,
            "delivery_date":     _tidy_date(deliv[0] if deliv else ""),
            "delivery_time":     _tidy_time(deliv[1] if len(deliv) > 1 else ""),
            "pickup_date":       _tidy_date(pick[0] if pick else ""),
            "pickup_time":       _tidy_time(pick[1] if len(pick) > 1 else ""),
            "breakdown":         breakdown[:8],
            "shops":             shops,
            # The signature setting this price was quoted under. Booking must send
            # the same one back or the charge will not match what was shown.
            "signature_type":    signature_type or "",
            # True only when THIS option really goes to a shop: the request flag is
            # not proof, since a pickup-point quote also returns door services.
            "delivery_dropoff":  bool(delivery_shops) or service_code.upper().endswith("_AP"),
            "delivery_shops":    delivery_shops,
        })
    options.sort(key=lambda x: (x["amount"] is None, x["amount"] if x["amount"] is not None else 0))
    # Diagnostics: WO accounts differ in which fields they populate. If a quote
    # comes back without a carrier or without the code we book with, say so once
    # here rather than let it surface as a mystery later.
    blind = [o["service_full"] for o in options if not o["carrier_name"]]
    if blind:
        logger.info("world options: no carrier resolved for %d service(s): %s",
                    len(blind), "; ".join(blind[:6]))
    if any(not o["service_type_code"] for o in options):
        logger.warning("world options: quote options with an EMPTY wsServiceTypeCode - "
                       "booking those would send no service code.")
    return {"options": options, "currency": cur}


ADDRESS_LINE_MAX = 35


def _address_lines(street: str, street2: str = "") -> tuple:
    """(Address1, Address2, Address3). The GIVEN line boundaries are preserved:
    the sender chose them and they usually carry meaning (building, then unit).
    Only a line over the couriers' 35-character cap is wrapped, at a word
    boundary, spilling onto the next slot. A single unbreakable 36+ character
    token is left whole for the courier rather than silently cut mid-word."""
    out = []
    for chunk in (street, street2):
        text = " ".join(str(chunk or "").split())
        if not text:
            continue
        if len(text) <= ADDRESS_LINE_MAX:
            out.append(text)
            continue
        cur = ""
        for w in text.split(" "):
            trial = (cur + " " + w).strip()
            if len(trial) <= ADDRESS_LINE_MAX or not cur:
                cur = trial
            else:
                out.append(cur)
                cur = w
        if cur:
            out.append(cur)
    if len(out) > 3:
        # More text than three capped lines hold: keep the head lines intact,
        # join the tail onto line three and let the courier's validation speak.
        out = [out[0], out[1], " ".join(out[2:])]
    while len(out) < 3:
        out.append("")
    return out[0], out[1], out[2]


def _recipient_block(d: dict) -> str:
    # wsRecipient, alpha: Address1,Address2,Address3,City,Company,Country_Code,Email,
    # Fax,Name,Phone,PhoneDialCode,Postalcode,Residential,State_Code
    name = d.get("name") or " ".join(x for x in [d.get("firstname"), d.get("lastname")] if x).strip()
    a1, a2, a3 = _address_lines(d.get("street"), d.get("street2"))
    return ("<wo:RecipientsDetails>"
            + _ts("m", "Address1", a1)
            + _ts("m", "Address2", a2)
            + _ts("m", "Address3", a3)
            + _ts("m", "City", d.get("city"))
            + _ts("m", "Company", d.get("company"))
            + _ts("m", "Country_Code", (d.get("country") or "").upper())
            + _ts("m", "Email", d.get("email"))
            + _ts("m", "Fax", "")
            + _ts("m", "Name", name or d.get("company"))
            + _ts("m", "Phone", d.get("phone"))
            + _ts("m", "PhoneDialCode", "")
            + _ts("m", "Postalcode", d.get("postcode"))
            + _b("m", "Residential", not (d.get("company") or "").strip())
            + _ts("m", "State_Code", _state_code(d.get("state"), d.get("country")))
            + "</wo:RecipientsDetails>")


def _sender_block(o: dict) -> str:
    # wsSender, alpha: Address1,Address2,Address3,City,Company,CountryCode,Email,
    # Name,Phone,PhoneDialCode,PostalCode,State
    name = o.get("name") or " ".join(x for x in [o.get("firstname"), o.get("lastname")] if x).strip()
    a1, a2, a3 = _address_lines(o.get("street"), o.get("street2"))
    return ("<wo:SendersDetails>"
            + _ts("m", "Address1", a1)
            + _ts("m", "Address2", a2)
            + _ts("m", "Address3", a3)
            + _ts("m", "City", o.get("city"))
            + _ts("m", "Company", o.get("company"))
            + _ts("m", "CountryCode", (o.get("country") or "").upper())
            + _ts("m", "Email", o.get("email"))
            + _ts("m", "Name", name or o.get("company"))
            + _ts("m", "Phone", o.get("phone"))
            + _ts("m", "PhoneDialCode", "")
            + _ts("m", "PostalCode", o.get("postcode"))
            + _ts("m", "State", _state_code(o.get("state"), o.get("country")))
            + "</wo:SendersDetails>")


def _label_from_bytes(raw: bytes, source_url: str = "") -> dict:
    """An inline label from downloaded bytes, typed by what the bytes actually are.
    An HTML page is refused: saving their error page as the label would be worse
    than having no label at all."""
    if not raw:
        return {}
    if raw.startswith(b"%PDF"):
        kind, lt = "base64pdf", "PDF"
    elif raw.startswith(b"\x89PNG"):
        kind, lt = "base64png", "PNG"
    elif raw[:256].lstrip()[:1] in (b"<",):
        return {}
    else:
        kind, lt = "base64bin", ""
    return {"type": kind, "value": base64.b64encode(raw).decode("ascii"),
            "label_type": lt, "source_url": source_url}


def _label_url(url: str) -> str:
    """The absolute https URL a LabelURL really means, or '' when it is not one of
    World Options' own. Their URLs can be relative to the service host, and nothing
    that arrives in a reply may send this server fetching an arbitrary address.
    Applied to EVERY redirect hop, not just the first: validating only the first
    leaves the redirect itself as the way onto an internal address."""
    u = (url or "").strip()
    if not u:
        return ""
    if "://" not in u:
        u = (_state.get("base_url") or DEFAULT_BASE).rstrip("/") + "/" + u.lstrip("/")
    try:
        p = urlparse(u)
    except ValueError:
        return ""
    if p.scheme not in ("http", "https"):
        return ""
    host = (p.hostname or "").lower()
    if not (host in ("worldoptions.co.uk", "worldoptions.com")
            or host.endswith(".worldoptions.co.uk")
            or host.endswith(".worldoptions.com")):
        return ""
    # A bare IP can never be one of their names, and resolving to a private range
    # would mean DNS pointing their host at something internal.
    try:
        ipaddress.ip_address(host)
        return ""
    except ValueError:
        pass
    # Their service is https; an http label link would let a network attacker swap
    # the label for a different address, so it is upgraded rather than trusted.
    if p.scheme == "http":
        u = "https://" + u.split("://", 1)[1]
    return u


async def _get_label_bytes(url: str, timeout: float) -> tuple:
    """(status, bytes, final_url). Redirects are followed BY HAND so every hop is
    re-validated against the allowlist; httpx's own follow would jump anywhere."""
    u = _label_url(url)
    if not u:
        return 0, b"", ""
    async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client:
        for _ in range(4):
            r = await client.get(u)
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                nxt = _label_url(urljoin(u, r.headers["location"]))
                if not nxt:
                    logger.warning("world options: label link redirected off their "
                                   "hosts; refusing to follow")
                    return r.status_code, b"", u
                u = nxt
                continue
            return r.status_code, (r.content or b""), u
    return 0, b"", u


async def label_link_report(url: str) -> dict:
    """What a stored label link is and what it answers, for the evidence panel.
    This exists because 'the label shows Not Found' is undiagnosable without it."""
    raw = (url or "").strip()
    u = _label_url(raw)
    if not u:
        return {"url": raw, "problem": "not a World Options address, refused to fetch"}
    try:
        status, body, final = await _get_label_bytes(u, 20.0)
        looks = ("PDF" if body.startswith(b"%PDF") else
                 "PNG" if body.startswith(b"\x89PNG") else
                 "an HTML page" if body[:256].lstrip()[:1] == b"<" else
                 "nothing" if not body else "unknown bytes")
        return {"url": final or u, "http": status, "bytes": len(body), "content": looks}
    except Exception as e:
        return {"url": u, "problem": str(e)[:200]}


async def fetch_label(url: str) -> dict:
    """Download a LabelURL into an inline label. The link they return may be
    relative, short-lived, or unreachable from inside the admin iframe (a tab
    opened there resolves against the app and 404s), so the bytes are captured
    once, server-side, and kept with the dispatch."""
    u = _label_url(url)
    if not u:
        return {}
    status, body, final = await _get_label_bytes(u, 12.0)
    if status != 200 or not body:
        logger.info("world options: label url answered HTTP %s: %s", status, final or u)
        return {}
    return _label_from_bytes(body[:8_000_000], final or u)


def _classify_label(lbl: ET.Element) -> dict:
    # The reply can carry the file AND a link. The bytes are the label; the link is
    # a convenience that does not survive the admin iframe. Bytes first, always.
    img = _text(lbl, "Image").strip()
    url = _text(lbl, "LabelURL").strip()
    if len(img) > 24_000_000:      # ~18MB decoded: not a shipping label
        logger.warning("world options: label Image is %s chars; ignoring it", len(img))
        img = ""
    if img:
        lt = (_text(lbl, "LabelType") or "").upper()
        if "PNG" in lt:
            kind = "base64png"
        elif "PDF" in lt or not lt:
            kind = "base64pdf"
        else:
            kind = "base64bin"    # ZPL and friends: downloadable, never a fake PDF
        out = {"type": kind, "value": img, "label_type": lt}
        if url:
            out["source_url"] = url
        return out
    if url:
        return {"type": "url", "value": url}
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
            + _ts("ad", "AdditionalComments", str(customs.get("comments") or "")[:200])
            + _t("ad", "CommercialInvoiceType",
                 customs.get("invoice_type") if customs.get("invoice_type") in INVOICE_TYPES else "Help_Me_Generate")
            + _ts("ad", "EORINumber", str(customs.get("eori") or "")[:30])
            + _t("ad", "ExportReason",
                 customs.get("export_reason") if customs.get("export_reason") in EXPORT_REASONS else "Sale")
            + _t("ad", "ExportType",
                 {"Repair": "Temporary", "Exhibition": "Temporary",
                  "Return": "Re_export"}.get(customs.get("export_reason") or "", "Permanent"))
            + (f"<ad:GoodsDetails>{goods}</ad:GoodsDetails>" if goods else "")
            + _ts("ad", "InvoiceNumber", str(customs.get("invoice_number") or "")[:40])
            + _b("ad", "IsPaperLess", True)
            + _ts("ad", "ReceiverCompanyNumber", str(customs.get("receiver_company_number") or "")[:40])
            + _ts("ad", "ReceiverTaxId", str(customs.get("receiver_tax_id") or "")[:40])
            + (_t("ad", "TotalCustomValue", _num(total)) if total else "")
            + _ts("ad", "TradeTerm", str(customs.get("trade_term") or "")[:20])
            + "</wo:AdditionalShipmentDetail>")


async def book(option: dict, origin: dict, destination: dict, boxes: list,
               currency: str = "GBP", reference: str = "",
               ready_time: str = "", close_time: str = "", ready_date: str = "",
               collection_option: str = "", insurance: str = "",
               signature: str = "", dropoff_shop: dict = None,
               customs: dict = None, description: str = "",
               delivery_shop: dict = None, quoted_signature: str = "") -> dict:
    """Book (and CHARGE) the chosen quote option. Returns tracking + labels.
    ready_time/close_time/collection_option describe the collection; insurance
    is the cover amount; signature a SIGNATURE_OPTIONS value; dropoff_shop the
    parcel shop when the merchant drops off; customs the international dossier
    (see _customs_block); description a short contents summary."""
    option = option or {}
    service_code = (option.get("service_type_code") or "").strip()
    if not service_code:
        raise WorldOptionsError("No courier service was chosen. Get fresh quotes and "
                                "pick a service; nothing was booked.")
    if service_code not in SERVICE_TYPES_ENUM:
        near = _service_carrier(service_code)
        raise WorldOptionsError(
            "World Options does not recognise the service code " + service_code
            + (" (" + carrier_display(near) + ")" if near else "")
            + ". Get fresh quotes and pick the service again; nothing was booked.")
    # Emit ONLY exact enum literals: WCF faults on case or membership mismatches,
    # and both elements are optional, so an unknown value is omitted instead.
    carrier = canonical_carrier(option.get("carrier_name") or "") \
        or canonical_carrier(_carrier_from(service_code, "",
                                           option.get("package_type_code") or "",
                                           option.get("service_full") or option.get("service_name") or ""))
    # Who is carrying it, whether or not that carrier may be named on the request.
    known = carrier or _carrier_from(service_code, "",
                                     option.get("package_type_code") or "",
                                     option.get("service_full") or option.get("service_name") or "")
    if not carrier:
        # Not fatal: ServiceTypeCode already pins the exact service, so World Options
        # knows who runs it. Worth recording, because the request cannot name them.
        logger.info("world options: booking %s without a ServiceType%s",
                    service_code or "(no code)",
                    " (" + known + " is not a bookable carrier enum member)" if known else "")
    pkg_type = option.get("package_type_code") or ""
    if pkg_type not in PACKAGE_TYPES_ENUM:
        # PackageTypeCode is a non-nillable enum, so dropping it does NOT send
        # nothing: WCF substitutes the enum's FIRST member, Fedex_Box, which is the
        # wrong packaging on anyone else's booking. The quote reply legitimately
        # carries rate-only values (Any_NonDocument and friends), so the carrier's
        # own "my packaging" type is used instead of leaving it to the default.
        pkg_type = CARRIER_PACKAGE_TYPE.get((known or carrier or "").upper(), "")
        if not pkg_type:
            raise WorldOptionsError(
                "World Options quoted this service with packaging that cannot be booked ("
                + (option.get("package_type_code") or "none given")
                + ") and there is no known packaging for "
                + (carrier_display(known or carrier) or "this carrier")
                + ". Nothing was booked. Pick another service, or send this message on.")
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
                   + _ts("sd", "City", shop.get("city"))
                   + _ts("sd", "Description", shop.get("name"))
                   + _ts("sd", "DropOffId", shop.get("id"))
                   + _ts("sd", "PostCode", shop.get("postcode"))
                   + _ts("sd", "Street", shop.get("street"))
                   + "</sd:CollectionDropOffInfo>")
    # An Access Point service delivers to a shop, so the shop must be named or the
    # parcel has nowhere to go.
    dshop = delivery_shop or {}
    ddrop = ""
    if dshop:
        ddrop = ("<sd:DeliveryDropOffInfo>"
                 + _ts("sd", "City", dshop.get("city"))
                 + _ts("sd", "Description", dshop.get("name"))
                 + _ts("sd", "DropOffId", dshop.get("id"))
                 + _ts("sd", "PostCode", dshop.get("postcode"))
                 + _ts("sd", "Street", dshop.get("street"))
                 + "</sd:DeliveryDropOffInfo>")
    shipping = ("<wo:ShippingDetail>"
                + dropoff
                + _t("sd", "CollectionType", "Regular")
                + _t("sd", "Currency", cur)
                + _ts("sd", "CustomerReference", (reference or "")[:40])
                + ddrop
                + _ts("sd", "Description", (description or "")[:100])
                + _t("sd", "Insurance", insurance or "0")
                + (_b("sd", "IsCollectionDropoffRequired", True) if shop else "")
                + (_b("sd", "IsDeliveryDropoffRequired", True) if dshop else "")
                # XSD sequence positions 12 and 13. Both are free-text strings the
                # service reads while building the label, and we were sending
                # neither, so both arrived null. The label comes back inline in the
                # reply (Image/LabelURL), which is what LABEL_DELIVERY names.
                + _ts("sd", "LabelDeliveryMethod", LABEL_DELIVERY)
                + _ts("sd", "NumberOfPiecesOnAllPallets", str(len(boxes or [])))
                + f"<sd:PackageDetails>{pkgs}</sd:PackageDetails>"
                + _t("sd", "PackageTypeCode", pkg_type)
                + _ts("sd", "SenderVatNo", str((customs or {}).get("vat") or "")[:30])
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
    if sig and sig not in set(SIGNATURE_OPTIONS.get((known or carrier).upper(), [])):
        # Translate an intent quoted under another carrier's wording into this
        # carrier's own, and drop it if this carrier has no equivalent.
        want_none = "no_signature" in sig.lower()
        swapped = NO_SIGNATURE_BY_CARRIER.get((known or carrier).upper(), "") if want_none else ""
        logger.info("world options: signature %r is not %s's; using %r",
                    sig, known or carrier or "this carrier", swapped or "their default")
        sig = swapped
    duties = str((customs or {}).get("duties_payor") or "").strip()
    if duties and duties not in DUTIES_PAYORS:
        duties = ""
    # BillingDetail is ALWAYS sent, because TransportationPayor lives here and its
    # enum begins with Bill_To_Receiver: leaving the block out or leaving the field
    # blank tells World Options to invoice the CUSTOMER for the carriage. The
    # merchant's own account pays, so it is stated on every booking.
    # Free-text children are emitted empty rather than dropped (a dropped nillable
    # string arrives as null); the date and account-number fields stay omitted,
    # because "" would fail a parse that a null is more likely to skip.
    billing = ("<wo:BillingDetail>"
               + _t("wo", "CloseTime", close_time)
               + _t("wo", "CollectionOptions", co)
               + _t("wo", "DeliverySignatureType", sig)
               + _ts("wo", "DutiesAccNumber", "")
               + _t("wo", "DutiesPayor", duties)
               + _ts("wo", "LocationDescription", "")
               + _ts("wo", "OtherEmailAddress", "")
               + _ts("wo", "PersonalMessage", "")
               + _t("wo", "ReadyDate", ready_date)
               + _t("wo", "ReadyTime", ready_time)
               + _ts("wo", "RecipientEmailAddress", "")
               + _ts("wo", "TransportationAccNumber", "")
               + _t("wo", "TransportationPayor", "Bill_To_Sender")
               + "</wo:BillingDetail>")
    # ShipmentBookingRequest in the XSD sequence order: AdditionalShipmentDetail,
    # AuthenticationDetail, BillingDetail, RecipientsDetails, SendersDetails, ShippingDetail
    inner = ("<tem:DoShipment><tem:shipment>"
             + _customs_block(customs or {})
             + _auth_block(full=True)
             + billing
             + _recipient_block(destination or {})
             + _sender_block(origin or {})
             + shipping
             + "</tem:shipment></tem:DoShipment>")
    try:
        root = await _soap_call("ShipmentService", "http://tempuri.org/IShipmentService/DoShipment", inner,
                            retryable=False)
    except WorldOptionsError as e:
        # The service rejected the request itself (rather than the data in it), so
        # the envelope IS the evidence. It goes into the exception as well as the
        # log, because the person who needs it is standing at the dispatch desk.
        e.envelope = _redacted(inner)
        logger.error("world options: DoShipment rejected: %s\nEnvelope sent:\n%s",
                     e, e.envelope)
        raise
    reply = _find(root, "DoShipmentResult")
    try:
        if reply is None:
            # The request was sent and something came back that we cannot read, so
            # the shipment MAY exist. Say so rather than inviting a second booking.
            raise WorldOptionsError(
                "World Options replied to the booking in a form this app could not read. "
                "The shipment MAY still have been booked and charged: check your World "
                "Options portal before trying again.")
        msg, _notif = _reply_status(reply, "book this shipment")
    except WorldOptionsError as e:
        # The request WAS sent and their server answered with an error, which is a
        # different fact from a transport failure: the envelope still is the
        # evidence, and the panel must never claim it was never sent.
        e.envelope = _redacted(inner)
        e.sent = True
        logger.error("world options: DoShipment answered FAILED: %s\nEnvelope sent:\n%s",
                     e, e.envelope)
        raise
    tracking = _text(reply, "MasterTrackingNo").strip()
    raw_labels = _findall_direct(reply, "ShippingLabel")
    labels = [c for c in (_classify_label(l) for l in raw_labels) if c]
    # The exact shape of what came back, kept with the shipment: whether the FILE
    # was in the reply is the whole label question, and it must never again depend
    # on somebody's memory of one booking.
    label_report = [{
        "image_bytes":  len(_text(l, "Image").strip()),
        "image_length": _text(l, "ImageLength").strip(),
        "label_type":   _text(l, "LabelType").strip(),
        "thermal":      _text(l, "IsThermalPrint").strip(),
        "url":          _text(l, "LabelURL").strip()[:200],
    } for l in raw_labels]
    logger.info("world options: booking %s label shape: %s", tracking, label_report)
    return {
        "label_report":    label_report,
        "tracking_number": tracking,
        "carrier_name":    carrier,
        # Who is carrying it, for display and for Shopify's tracking company. Wider
        # than carrier_name, which is only ever the literal the request may contain.
        "carrier_known":   known,
        # What the merchant reads. Stored with the dispatch so an order booked today
        # still names its courier next week without re-deriving it.
        "carrier_label":   carrier_display(known) or option.get("carrier_label") or "",
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
    try:
        msg, _notif = _reply_status(reply, "cancel this shipment")
    except WorldOptionsError as e:
        e.envelope = _redacted(inner)
        e.sent = True
        raise
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
