"""The dispatch desk: courier quotes, booking, labels, the manifest,
cancelling, collections, customs, pasted and one-off addresses, the shipping
settings, and the margin report built on what couriers charged.

Moved whole out of copilot.py (stage 4 of the 14 October audit); its routes
are in gizmo/routes/dispatch.py. What it still needs from copilot.py it reads
as core.NAME, never a copied name, so a test that patches copilot.NAME
reaches it here too; t_what_dispatch_borrows lists those names. copilot.py
reads the desk as desk.NAME (two names its frozen print route reads it takes
by name). The desk reads nothing from copilot.py as it loads and imports it
last, so either module can be imported first.
"""
import logging
import glob
import os
import re
import json
import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import contextvars
from typing import Optional
try:
    import worldoptions
except Exception:                     # keep the app booting if the connector is unavailable
    worldoptions = None
import tokenvault

from gizmo.config import _env_num
from gizmo import ai as claude
from gizmo import errors
from gizmo import store as jsonstore
from gizmo.store import StoreUnwritable

# The same logger as copilot.py's, so the desk's log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


# ---------------------------------------------------------------------------
# Shipping / dispatch (World Options SOAP web service) — settings, credentials
# and per-order state. The SOAP client lives in worldoptions.py; this holds the
# merchant's origin address, box presets and preferences, the World Options
# credentials (persisted apart from everything the backup zip touches), and a
# record of what was dispatched.
# ---------------------------------------------------------------------------
SHIPPING_PATH       = os.environ.get("SHIPPING_PATH", "/data/shipping.json")
WO_SECRET_PATH      = os.environ.get("WO_SECRET_PATH", "/data/wo_secret.json")
DISPATCH_STATE_PATH = os.environ.get("DISPATCH_STATE_PATH", "/data/dispatch_state.json")
DISPATCH_LABELS_DIR = os.environ.get(
    "DISPATCH_LABELS_DIR",
    os.path.join(os.path.dirname(DISPATCH_STATE_PATH) or ".", "dispatch_labels"))
DISPATCH_STATE_MAX  = _env_num(int, os.environ.get("DISPATCH_STATE_MAX", "2000"), "2000", "DISPATCH_STATE_MAX")
# Rows leaving the live store go here, whole. A dispatch record is a customs
# declaration and a courier booking - the records the redaction code keeps
# "under a legal obligation" because HMRC can ask for them within six years.
# The live store is capped because the desk reads it on every request; the
# cap used to DROP what it trimmed, so the retention the app promised ended
# at record 2,001. Append-only, one JSON object per line, beside the store.
DISPATCH_ARCHIVE_PATH = os.environ.get(
    "DISPATCH_ARCHIVE_PATH",
    os.path.join(os.path.dirname(DISPATCH_STATE_PATH) or ".", "dispatch_state_archive.jsonl"))
# A booking in flight: written before World Options is asked, cleared once the
# answer is recorded or is a definite refusal. One left behind means the
# process stopped (a deploy, a crash) or the answer was lost between asking and
# recording, so the booking may exist and be charged with no record here: the
# next Book on that shipment is stopped until someone has checked.
BOOKING_INTENT_PATH = os.environ.get(
    "BOOKING_INTENT_PATH",
    os.path.join(os.path.dirname(DISPATCH_STATE_PATH) or ".", "booking_intents.json"))
BOOKING_INTENT_HOURS = 48
_book_confirmed: "contextvars.ContextVar[bool]" = contextvars.ContextVar("book_confirmed", default=False)
DISPATCHED_TAG      = os.environ.get("DISPATCHED_TAG", "Complete")
# Orders finished before the tag was renamed still carry the old word. The queue
# accepts both so history does not vanish from the app; nothing writes the old one.
LEGACY_DISPATCHED_TAGS = ("Dispatched",)

_DEFAULT_BOXES = [
    {"id": "small",  "name": "Small gobo box", "width": 20, "length": 15, "depth": 8,  "weight": 0.5},
    {"id": "medium", "name": "Medium box",     "width": 30, "length": 22, "depth": 15, "weight": 1.0},
    {"id": "large",  "name": "Large box",      "width": 45, "length": 35, "depth": 25, "weight": 3.0},
]
# The label stock each printer is loaded with. Two printers at the bench: gobo
# production labels come off one, courier labels off the other, and the stock
# does not change from day to day - so this is a shop setting, not something
# chosen at the print button. Kept here and offered by the config route so the
# page and the server cannot drift about which sizes exist.
LABEL_STOCK = ("4x2", "4x3", "4x4", "4x6", "2x4", "a4")
# Each stock's width and height in millimetres, for the document Shopify's
# print action opens: it knew five sizes and fell back to 4 x 6 for the rest,
# so the 4 x 4 the production printer is loaded with could not come off it.
LABEL_STOCK_MM = {"4x2": (101.6, 50.8), "4x3": (101.6, 76.2), "4x4": (101.6, 101.6),
                  "4x6": (101.6, 152.4), "2x4": (50.8, 101.6), "a4": (210, 297)}

_SHIPPING_DEFAULT = {
    "origin": {},
    # 4x4 for production, 4x6 for the courier: the sizes actually loaded.
    "label_size_production": "4x4",
    "label_size_shipping": "4x6",
    "boxes": _DEFAULT_BOXES,
    "default_box_id": "small",
    "notify_customer": True,
    "currency": "GBP",
    "plugin_code": "Web_Service",
    "ready_time": "",    # collection window sent with every booking (HH:MM)
    "close_time": "",
    # Collection arrangement: explicit, because omitting it makes WO assume a NEW
    # collection is wanted on every booking (wrong for daily-collection accounts).
    "collection_option": "I_Need_To_Book_A_Collection",
    # How each courier collects, because it differs by courier: UPS may call
    # daily while DHL has to be asked each time. Keyed by the carrier code the
    # quote comes back with. The single setting above answers for any carrier
    # not named here.
    "collection_by_carrier": {},
    # Shop-based services (customer collects, or we drop off) are hidden by
    # default: this merchant ships to the door and has never used parcel shops.
    "show_parcelshop": False,
    # International / customs (used only for non-GB destinations)
    "eori": "",
    "vat_number": "",
    "default_hs_code": "",
    "export_reason": "Sale",
    "duties_payor": "Duties_To_Be_Paid_By_Receiver",
    "trade_term": "",
    "base_url": (worldoptions.DEFAULT_BASE if worldoptions else ""),
}
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
# The only currencies World Options' contract accepts; anything else falls back.
_WO_CURRENCIES = {"GBP", "USD", "EUR", "CAD", "AUD", "NZD", "SGD"}


def _wo_currency(order_currency, cfg: dict) -> str:
    c = str(order_currency or "").strip().upper()
    if c in _WO_CURRENCIES:
        return c
    c2 = str(cfg.get("currency") or "").strip().upper()
    return c2 if c2 in _WO_CURRENCIES else "GBP"
# Which credentials come from the environment (authoritative; never shadowed on disk).
_WO_ENV = {"meter": "WO_METER_NUMBER", "key": "WO_KEY", "password": "WO_PASSWORD"}


def _sane_base(b) -> str:
    """A trustworthy SOAP base URL. Empty, or a stale REST host persisted by an
    earlier build, both fall back to the SOAP default."""
    default = worldoptions.DEFAULT_BASE if worldoptions else ""
    b = str(b or "").strip().rstrip("/")
    if not b or "ecommerce.worldoptions.com" in b:
        return default
    return b


def _load_shipping() -> dict:
    data = jsonstore._load_json_store(SHIPPING_PATH, None, {})
    out = {k: v for k, v in _SHIPPING_DEFAULT.items()}
    if isinstance(data, dict):
        for k in _SHIPPING_DEFAULT:
            if k in data and data[k] is not None:
                out[k] = data[k]
    if not out.get("boxes"):
        out["boxes"] = [dict(b) for b in _DEFAULT_BOXES]
    out["base_url"] = _sane_base(out.get("base_url"))
    return out


def _save_shipping(cfg: dict) -> dict:
    if not jsonstore._store_writable(SHIPPING_PATH):
        return cfg
    keep = {k: cfg.get(k, _SHIPPING_DEFAULT[k]) for k in _SHIPPING_DEFAULT}
    jsonstore._write_json_store(SHIPPING_PATH, None, keep)
    return keep


def _wo_env_creds() -> dict:
    return {k: os.environ.get(env, "").strip() for k, env in _WO_ENV.items()}


def _load_wo_creds() -> dict:
    """The World Options SOAP credentials. Env vars always win over the disk copy,
    per credential."""
    disk = jsonstore._load_json_store(WO_SECRET_PATH, None, {})
    disk = disk if isinstance(disk, dict) else {}
    env = _wo_env_creds()

    def opened(k):
        try:
            return str(tokenvault.unseal(str(disk.get(k) or "")) or "").strip()
        except Exception:
            # Sealed with a key this deployment does not have. Reading it as
            # "not configured" says so in the UI; raising would take booking
            # down with a stack trace nobody can act on.
            logger.error("World Options: the stored %s cannot be decrypted "
                         "(TOKEN_ENCRYPTION_KEY changed?)", k)
            return ""
    return {k: (env[k] or opened(k)) for k in _WO_ENV}


def _wo_creds_from_env() -> bool:
    return any(_wo_env_creds().values())


def _save_wo_creds(meter=None, key=None, password=None) -> bool:
    """Persist any provided credential (None = leave as-is). Never shadows an
    env-provided value."""
    if not jsonstore._store_writable(WO_SECRET_PATH):
        return False
    disk = jsonstore._load_json_store(WO_SECRET_PATH, None, {})
    disk = disk if isinstance(disk, dict) else {}
    env = _wo_env_creds()
    for name, val in (("meter", meter), ("key", key), ("password", password)):
        if val is not None and not env[name]:
            # Sealed like the OAuth tokens and the sign-in secrets. This file
            # was the one long-lived credential the vault did not cover, while
            # its own documentation said it covered them all - and what it
            # holds books shipments on the merchant's courier account.
            disk[name] = tokenvault.seal(str(val).strip())
    os.makedirs(os.path.dirname(WO_SECRET_PATH) or ".", exist_ok=True)
    # 0600 from the moment it exists, not after the replace: the old write
    # left it briefly at whatever the umask allowed.
    tokenvault.write_private(WO_SECRET_PATH, disk)
    return True


def _wo_boot() -> None:
    """Push the persisted credentials + plugin + base URL into the worldoptions
    client at startup."""
    if not worldoptions:
        return
    try:
        c = _load_wo_creds()
        stored = jsonstore._load_json_store(SHIPPING_PATH, None, {})
        cfg = _load_shipping()   # base already sanitized here
        worldoptions.set_credentials(meter=c["meter"], key=c["key"], password=c["password"],
                                     plugin=cfg.get("plugin_code") or "Web_Service")
        worldoptions.set_base_url(cfg.get("base_url") or worldoptions.DEFAULT_BASE)
        # Self-heal: if a stale/wrong base URL is on disk, rewrite the corrected one
        # so it does not keep tripping every request.
        if isinstance(stored, dict) and stored.get("base_url") and \
                _sane_base(stored.get("base_url")) != str(stored.get("base_url")).strip().rstrip("/"):
            _save_shipping(cfg)
    except Exception:
        logger.exception("world options boot failed")


# Booked labels can be big base64 blobs; keep them out of the small state file,
# one JSON per order, so reprinting after a reload still works (the SOAP API has
# no fetch-by-tracking service).
def _pdf_print_images(b64pdf: str) -> list:
    """Each page of a PDF label as a base64 PNG. Browsers cannot reliably print a
    PDF from a hidden frame inside the admin (the viewer prints blank or not at
    all), while an image in an HTML frame prints the same way the production
    labels already do. Conversion failing is never fatal: Download still works."""
    try:
        import base64 as _b64
        import io as _io
        import pypdfium2 as _pdfium
        # A label is a small document. Anything larger arrived from outside this
        # app and is refused rather than decoded into memory.
        if len(b64pdf or "") > 24_000_000:
            logger.warning("label PDF too large to render (%s chars of base64)", len(b64pdf))
            return []
        doc = _pdfium.PdfDocument(_b64.b64decode(b64pdf))
        out = []
        for i in range(min(len(doc), 6)):     # a label sheet, not a document
            page = doc[i]
            # A PDF may declare an enormous page; rendering that at 3x is a memory
            # bomb. Scale down so no page exceeds a sane pixel budget.
            try:
                w, h = page.get_size()
            except Exception:
                w = h = 0
            scale = 3.0
            if w > 0 and h > 0:
                scale = min(3.0, (4000.0 / w), (4000.0 / h))
                scale = max(scale, 0.25)
            pil = page.render(scale=scale).to_pil()   # ~216 dpi: crisp on thermal
            buf = _io.BytesIO()
            pil.save(buf, format="PNG")
            out.append(_b64.b64encode(buf.getvalue()).decode("ascii"))
        return out
    except Exception:
        logger.exception("label PDF could not be rendered for printing")
        return []


def _with_print_images(labels: list) -> list:
    out = []
    for lbl in labels:
        if (isinstance(lbl, dict) and lbl.get("type") == "base64pdf"
                and not lbl.get("print_images")):
            imgs = _pdf_print_images(lbl.get("value") or "")
            if imgs:
                lbl = dict(lbl)
                lbl["print_images"] = imgs
        out.append(lbl)
    return out


async def _resolve_label_links(labels: list) -> list:
    """Swap every url-type label for its downloaded bytes. Their label links are
    unreliable from inside the admin (relative paths resolve against this app and
    404, and the frame mangles opened tabs), so the file itself is what is kept.
    A link that cannot be fetched is kept as-is rather than dropped."""
    out = []
    for lbl in labels:
        if isinstance(lbl, dict) and lbl.get("type") == "url" and worldoptions:
            try:
                got = await worldoptions.fetch_label(lbl.get("value"))
            except Exception:
                logger.exception("label download failed for %s", lbl.get("value"))
                got = {}
            out.append(got or lbl)
        else:
            out.append(lbl)
    return out


DISPATCH_LABELS_MAX = _env_num(int, os.environ.get("DISPATCH_LABELS_MAX", "400"), "400", "DISPATCH_LABELS_MAX")


_ADHOC = "adhoc:"     # shipments with no Shopify order behind them


def _is_adhoc(key) -> bool:
    """True for a shipment booked to a pasted address rather than an order.

    The prefix is what makes an ad-hoc shipment safe to file in the same store as
    real orders: a Shopify order id is all digits, so the two can never collide,
    and every reader that joins to Shopify simply fails to match and moves on."""
    return str(key or "").startswith(_ADHOC)


def _is_private(entry) -> bool:
    """True for a shipment an admin has marked as theirs to see.

    Only ever set on an ad-hoc shipment. An order's dispatch record is read by
    the queues, the margin report and Shopify itself, so hiding one would mean
    hiding the order; a pasted-address shipment belongs to nothing else and can
    be kept to the people who booked it."""
    return bool(isinstance(entry, dict) and entry.get("admin_only"))


def _label_path(key) -> str:
    """Where a shipment's stored label lives. Order ids keep their existing bare
    filename; an ad-hoc key is reduced to characters a filename can hold."""
    k = str(key)
    name = re.sub(r"[^A-Za-z0-9_-]", "_", k)[:60] if _is_adhoc(k) else str(int(k))
    return os.path.join(DISPATCH_LABELS_DIR, name + ".json")


def _save_dispatch_labels(order_id, labels: list) -> None:
    try:
        os.makedirs(DISPATCH_LABELS_DIR, exist_ok=True)
        path = _label_path(order_id)
        jsonstore._write_json_store(path, "labels", labels or [])
        # With print images a label file is ~1MB, and nothing ever pruned this
        # directory. Oldest go first; a months-old label is in the courier's past
        # anyway and its tracking number stays in the dispatch record.
        files = sorted(glob.glob(os.path.join(DISPATCH_LABELS_DIR, "*.json")),
                       key=os.path.getmtime)
        for stale in files[:-DISPATCH_LABELS_MAX] if len(files) > DISPATCH_LABELS_MAX else []:
            try:
                os.remove(stale)
            except OSError:
                pass
    except Exception:
        logger.exception("saving dispatch labels failed for order %s", order_id)


def _dispatch_with_live_labels(entries: dict) -> dict:
    """The queue's dispatch map, with has_label telling the truth. A Reprint
    button that counts labels the volume no longer holds promises a stack it
    cannot print."""
    have = _stored_label_ids()
    out = {}
    for k, v in (entries or {}).items():
        if v.get("has_label") and k not in have:
            v = {**v, "has_label": False}
        out[k] = v
    return out


def _stored_label_ids() -> set:
    """Which shipments still HAVE a label file, from one directory listing.

    has_label is stamped once at booking and never cleared, but the label
    files are pruned oldest-first - so a months-old order can advertise a
    label that is no longer on disk. Reading the directory once is cheap;
    reading every order's file is not."""
    try:
        return {n[:-5] for n in os.listdir(DISPATCH_LABELS_DIR) if n.endswith(".json")}
    except OSError:
        return set()


def _load_dispatch_labels(order_id) -> list:
    try:
        with open(_label_path(order_id), "r", encoding="utf-8") as fh:
            return (json.load(fh) or {}).get("labels") or []
    except (FileNotFoundError, ValueError, OSError):
        return []


WO_FAILURES_PATH = os.environ.get("WO_FAILURES_PATH", "/data/wo_failures.json")
WO_FAILURES_MAX = 10


def _record_wo_failure(tech: dict) -> None:
    """Keep the last few rejected bookings on disk. Closing the window should not
    destroy the only copy of why a dispatch would not go through."""
    try:
        rows = jsonstore._load_json_store(WO_FAILURES_PATH, "failures", [])
        rows = ([tech] + list(rows))[:WO_FAILURES_MAX]
        if jsonstore._store_writable(WO_FAILURES_PATH):
            jsonstore._write_json_store(WO_FAILURES_PATH, "failures", rows)
    except Exception:
        logger.exception("could not record the World Options failure")


def _load_wo_failures() -> list:
    return jsonstore._load_json_store(WO_FAILURES_PATH, "failures", [])


def _load_dispatch() -> dict:
    return jsonstore._load_json_cached(DISPATCH_STATE_PATH, "orders", {})


class DispatchStoreUnwritable(StoreUnwritable):
    """The dispatch record could not be saved. Raised rather than returned, because
    a silent no-op here loses the only record that money was spent."""


def _archive_dispatch_rows(rows: list) -> bool:
    """Append evicted dispatch records to the archive. False when the append
    did not happen, so the caller keeps the rows rather than losing them."""
    try:
        os.makedirs(os.path.dirname(DISPATCH_ARCHIVE_PATH) or ".", exist_ok=True)
        with open(DISPATCH_ARCHIVE_PATH, "a", encoding="utf-8") as fh:
            for oid, rec in rows:
                fh.write(json.dumps({"order_id": str(oid), **(rec or {})}, default=str) + "\n")
        return True
    except Exception:
        logger.exception("dispatch archive append failed")
        return False


def _write_dispatch(orders: dict) -> dict:
    if not jsonstore._store_writable(DISPATCH_STATE_PATH):
        jsonstore._forget_store(DISPATCH_STATE_PATH)
        raise DispatchStoreUnwritable(DISPATCH_STATE_PATH)
    if len(orders) > DISPATCH_STATE_MAX:
        keep = sorted(orders.items(), key=lambda kv: str(kv[1].get("dispatched_at") or ""))
        evicted = keep[:-DISPATCH_STATE_MAX]
        # Archived FIRST, and only trimmed once the archive holds them: a
        # record that cannot be archived stays in the live store, however
        # large that makes it. A wrong deletion here is forever.
        if _archive_dispatch_rows(evicted):
            orders = dict(keep[-DISPATCH_STATE_MAX:])
        else:
            logger.error("dispatch: %d rows are past the cap but could not be archived; "
                         "keeping them in the live store", len(evicted))
    jsonstore._write_json_store(DISPATCH_STATE_PATH, "orders", orders)
    return orders


def _update_dispatch(order_id, mutate) -> dict:
    """Load, change ONE order, write. There must never be an await between the read
    and the write: `_write_dispatch` serialises the whole store, so a snapshot held
    across I/O silently deletes every record written in the meantime. That erased a
    charged booking and re-armed the double-book guard until it was found."""
    d = _load_dispatch()
    entry = dict(d.get(str(order_id)) or {})
    changed = mutate(entry)
    d[str(order_id)] = entry if changed is None else changed
    return _write_dispatch(d)


# Which couriers already have a collection coming, and for which date:
# {"DHL": "2026-08-28"}. Small, durable and separate from the dispatch record,
# which is keyed by order id and would collide.
COLLECTIONS_PATH = os.environ.get("COLLECTIONS_PATH", "/data/collections.json")


def _load_collections() -> dict:
    d = jsonstore._load_json_store(COLLECTIONS_PATH, "collections", {})
    return d if isinstance(d, dict) else {}


def _write_collections(d: dict) -> None:
    jsonstore._write_private_json(COLLECTIONS_PATH, "collections", d)


def _collections_from_dispatch(day: str) -> dict:
    """Collections the COURIER confirmed, per carrier, for one day.

    World Options returns a collection reference on the booking reply
    (CollectionDateNumber), and it is kept on the dispatch record. That is the
    courier's own answer to "is a van coming", so it is worth more than the
    ledger this app keeps alongside it - and it is already there for every
    shipment ever booked, including the ones booked before any of this existed."""
    out: dict = {}
    try:
        for oid, e in (_load_dispatch() or {}).items():
            if not isinstance(e, dict) or not e.get("collection_date"):
                continue
            when = _dmy_to_iso(e.get("ready_date")) or str(e.get("dispatched_at") or "")[:10]
            if when != day:
                continue
            code = str(e.get("carrier_name") or "").strip().upper()
            if not code:
                continue
            at = str(e.get("dispatched_at") or "")
            if code in out and at <= str(out[code].get("at") or ""):
                continue                      # keep the most recent of the day
            # Their reference arrives as date, time and number glued together
            # with literal <br/>. Parsed here so nothing downstream prints it.
            _c = (worldoptions.parse_collection(e.get("collection_date"))
                  if worldoptions else {"ref": str(e.get("collection_date") or ""),
                                        "date": "", "time": ""})
            out[code] = {"date": day, "at": str(e.get("dispatched_at") or ""),
                         "order": str(e.get("order_name") or oid or ""),
                         "service": str(e.get("carrier_label") or e.get("service_name") or ""),
                         "ref": _c["ref"], "ref_date": _c["date"], "ref_time": _c["time"]}
    except Exception:
        logger.exception("could not read collections off the dispatch record")
    return out


def _collections_for(day: str) -> dict:
    """Every collection known for a day: the courier's confirmations off the
    dispatch record, minus any the desk has said has already been and gone.

    The suppression has to live here rather than in the ledger alone, because
    the dispatch record is the stronger source and would simply re-assert a
    cleared collection on the next read."""
    ledger = _load_collections()
    out = dict(ledger)
    out.update(_collections_from_dispatch(day))
    for code, v in (ledger or {}).items():
        if isinstance(v, dict) and v.get("cleared") and str(v.get("date") or "") == day:
            out.pop(code, None)
    return out


def _collection_row(v) -> dict:
    """One ledger entry, whichever shape it was written in. The first version of
    this stored a bare date; anything read here may still be one."""
    if isinstance(v, dict):
        return {"date": str(v.get("date") or ""), "at": str(v.get("at") or ""),
                "order": str(v.get("order") or ""), "service": str(v.get("service") or "")}
    return {"date": str(v or ""), "at": "", "order": "", "service": ""}


def _dispatch_today() -> str:
    """Today, where the parcels are. Every other dispatch date in this app is
    reckoned in Europe/London - the ready window, the next working day - and a
    collection ledger kept in UTC disagrees with all of them for the hour after
    midnight through the summer."""
    return core._london_today().isoformat()


def _dmy_to_iso(dmy: str) -> str:
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", str(dmy or "").strip())
    return "%s-%02d-%02d" % (m.group(3), int(m.group(2)), int(m.group(1))) if m else ""


def _collection_target(arrangement: str, ready_dmy: str = "") -> str:
    """The DAY the collection being asked for is actually for.

    The ready date the courier was given, when there is one. That matters: book
    after the close on a Friday and _collection_ready says Monday, so the van
    comes Monday. Recording it against Friday would leave Monday looking
    uncollected, and the first parcel that morning would book - and pay for - a
    second pickup."""
    iso = _dmy_to_iso(ready_dmy)
    if iso:
        return iso
    day = datetime.now(ZoneInfo("Europe/London")).date()
    if arrangement == "I_Need_To_Book_A_Collection_For_Next_Day":
        day = day + timedelta(days=1)
    return day.isoformat()


def _record_dispatch(order_id, entry: dict) -> dict:
    d = _load_dispatch()
    d[str(order_id)] = entry
    return _write_dispatch(d)


# ---------------------------------------------------------------------------
# Dispatch (World Options): quote couriers, then book + fulfill + tag.
# Quoting is free and read-only; only booking spends money, and it is gated
# behind an explicit merchant confirm in the UI.
# ---------------------------------------------------------------------------
def _addr_ready(a: dict) -> str:
    """'' if a destination address can be quoted, else why not."""
    a = a or {}
    missing = [lbl for key, lbl in (("street", "street"), ("city", "city"),
                                    ("postcode", "postcode"), ("country", "country"))
               if not str(a.get(key) or "").strip()]
    return ("Missing " + ", ".join(missing)) if missing else ""


# ---------------------------------------------------------------------------
# Pasted addresses
#
# A shipment with no Shopify order behind it starts life as a block of text
# copied out of an email. Reading it here is instant, free, works offline and
# gives the same answer every time, and a postcode is a strong enough anchor to
# place the rest of the block around it. Claude is only asked when this pass
# cannot place something, because it is better at the awkward cases and worse
# at being predictable. Either way the merchant sees and can edit every field
# before anything is booked, so no parser ever has the last word on where a
# parcel goes.
# ---------------------------------------------------------------------------

# Country names to the 2-letter ISO codes World Options wants. Not the full ISO
# list: the places this merchant actually ships to, plus the spellings people
# type. Anything unrecognised is left alone for the merchant to correct.
_ISO2 = {
    "united kingdom": "GB", "great britain": "GB", "uk": "GB", "gb": "GB", "england": "GB",
    "scotland": "GB", "wales": "GB", "northern ireland": "GB", "britain": "GB",
    "ireland": "IE", "republic of ireland": "IE", "eire": "IE",
    "united states": "US", "united states of america": "US", "usa": "US", "u.s.a.": "US",
    "us": "US", "america": "US", "canada": "CA", "mexico": "MX",
    "france": "FR", "germany": "DE", "deutschland": "DE", "spain": "ES", "espana": "ES",
    "italy": "IT", "italia": "IT", "netherlands": "NL", "holland": "NL", "the netherlands": "NL",
    "belgium": "BE", "luxembourg": "LU", "portugal": "PT", "switzerland": "CH", "austria": "AT",
    "denmark": "DK", "sweden": "SE", "norway": "NO", "finland": "FI", "iceland": "IS",
    "poland": "PL", "czech republic": "CZ", "czechia": "CZ", "slovakia": "SK", "hungary": "HU",
    "romania": "RO", "bulgaria": "BG", "greece": "GR", "croatia": "HR", "slovenia": "SI",
    "serbia": "RS", "estonia": "EE", "latvia": "LV", "lithuania": "LT", "malta": "MT",
    "cyprus": "CY", "turkey": "TR", "ukraine": "UA",
    "australia": "AU", "new zealand": "NZ", "japan": "JP", "china": "CN", "hong kong": "HK",
    "singapore": "SG", "south korea": "KR", "korea": "KR", "india": "IN", "thailand": "TH",
    "malaysia": "MY", "indonesia": "ID", "philippines": "PH", "vietnam": "VN",
    "united arab emirates": "AE", "uae": "AE", "saudi arabia": "SA", "qatar": "QA",
    "kuwait": "KW", "bahrain": "BH", "oman": "OM", "israel": "IL",
    "south africa": "ZA", "egypt": "EG", "nigeria": "NG", "kenya": "KE", "morocco": "MA",
    "brazil": "BR", "argentina": "AR", "chile": "CL", "colombia": "CO", "peru": "PE",
    # The near ones a UK shipper meets most, and the ones whose first two letters
    # spell a different country: Isle of Man is not Iceland, Guernsey is not Guam.
    "isle of man": "IM", "guernsey": "GG", "jersey": "JE", "channel islands": "GG",
    "gibraltar": "GI", "bermuda": "BM", "pakistan": "PK", "iraq": "IQ", "iran": "IR",
    "costa rica": "CR", "colombia ": "CO", "monaco": "MC", "andorra": "AD",
    "liechtenstein": "LI", "san marino": "SM", "faroe islands": "FO", "greenland": "GL",
}

# GB postcodes are the anchor: the format is unambiguous, so finding one tells us
# both where the postcode is and that the country is GB unless told otherwise.
_UK_POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}[0-9][A-Z0-9]?)\s*([0-9][A-Z]{2})\b", re.I)
# Postcode areas that are not Great Britain: Jersey, Guernsey (with Alderney
# and Sark) and the Isle of Man. No mainland area shares these letters.
_CROWN_POSTCODE_AREAS = {"JE": "JE", "GY": "GG", "IM": "IM"}
_EIRCODE_RE = re.compile(r"\b([A-Z][0-9]{2})\s?([A-Z0-9]{4})\b", re.I)
_US_ZIP_RE = re.compile(r"\b([0-9]{5})(?:-[0-9]{4})?\b")
_GENERIC_PC_RE = re.compile(r"\b([0-9]{4,6})\b")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"\+?[0-9][0-9\s().-]{7,}[0-9]")
_PHONE_LABEL_RE = re.compile(r"^\s*(tel|telephone|phone|mob|mobile|cell|t|m|p)\s*[:.]?\s*", re.I)
_US_STATE_RE = re.compile(r"\b([A-Z]{2})\b\s+[0-9]{5}")
_COMPANY_RE = re.compile(
    r"\b(ltd|limited|llp|plc|inc|incorporated|llc|gmbh|b\.?v|s\.?a|srl|sarl|pty|corp|"
    r"corporation|company|&\s*co|group|events?|productions?|studios?|services|design|"
    r"lighting|theatres?|theaters?|university|college|school|academy|hotel|church|"
    r"council|trust|museum|gallery|centre|center|club|venue|hire|av|media)\b", re.I)
_STREET_RE = re.compile(
    r"\b(road|rd|street|st|lane|ln|avenue|ave|close|way|drive|dr|court|ct|place|pl|"
    r"square|sq|terrace|crescent|cres|grove|gardens?|hill|park|estate|industrial|unit|"
    r"suite|apt|apartment|floor|house|building|block|walk|row|mews|wharf|quay|bank|"
    r"view|rise|vale|green|common|parade|broadway|boulevard|blvd|strasse|straße|"
    r"rue|via|calle|po box)\b", re.I)


def _split_blob(text: str) -> list:
    """The pasted text as address lines. Newlines are the sender's own line
    breaks and are kept; a single-line paste is split on commas instead."""
    lines = [re.sub(r"\s+", " ", ln).strip(" ,;\t") for ln in str(text or "").splitlines()]
    # "Please send to:" and bare "Tel:" are preamble, not address lines.
    lines = [ln for ln in lines if ln and not (ln.endswith(":") and len(ln) < 40)]
    if len(lines) <= 1:
        lines = [p.strip() for p in re.split(r"\s*,\s*", lines[0] if lines else "") if p.strip()]
    return lines[:20]


def _country_code(text: str) -> str:
    """A 2-letter ISO code from whatever the sender wrote, or ''."""
    t = re.sub(r"[^a-z ]", "", str(text or "").strip().lower()).strip()
    if t in _ISO2:
        return _ISO2[t]
    raw = str(text or "").strip()
    if len(raw) == 2 and raw.isalpha():
        return raw.upper()
    return ""


def _find_postcode(line: str, country: str):
    """(postcode, the rest of the line) for the first postcode in a line.

    The hard part is telling a bare-number postcode from a house number, since
    both are just digits. The tell is what FOLLOWS them: a house number leads a
    street ("1200 Kingston Road"), while a numeric postcode either ends the line
    ("New York, NY 10036") or leads a town ("10115 Berlin"). Getting this the
    wrong way round files the house number as the postcode and shifts every
    field along, which is why it is worth the care."""
    for rx in ((_UK_POSTCODE_RE, _EIRCODE_RE) if country in ("GB", "IE", "") else ()):
        m = rx.search(line)
        if m:
            pc = (m.group(1) + " " + m.group(2)).upper()
            return pc, (line[:m.start()] + " " + line[m.end():]).strip(" ,")
    for rx in (_US_ZIP_RE, _GENERIC_PC_RE):
        for m in rx.finditer(line):
            head, tail = line[:m.start()].strip(" ,"), line[m.end():].strip(" ,")
            if not head and _STREET_RE.search(tail):
                continue           # digits leading a street name: a house number
            return m.group(0), (head + " " + tail).strip(" ,")
    return "", line


def _parse_address(text: str) -> dict:
    """A pasted block as the address dict the dispatch path uses, plus how well
    it went. Never raises: an unreadable paste comes back empty for the merchant
    to fill in by hand."""
    out = {k: "" for k in ("name", "company", "firstname", "lastname", "street", "street2",
                           "postcode", "city", "state", "country", "phone", "email")}
    lines = _split_blob(text)
    if not lines:
        return {"address": out, "confident": False, "unplaced": []}

    # Contact details first: they are unambiguous and would otherwise be read as
    # address lines.
    rest = []
    for ln in lines:
        m = _EMAIL_RE.search(ln)
        if m:
            out["email"] = out["email"] or m.group(0)
            ln = (ln[:m.start()] + " " + ln[m.end():]).strip(" ,:")
            ln = re.sub(r"^(e|email|e-mail)\s*[:.]?\s*$", "", ln, flags=re.I).strip()
        stripped = _PHONE_LABEL_RE.sub("", ln)
        m = _PHONE_RE.fullmatch(stripped.strip())
        if m and len(re.sub(r"\D", "", stripped)) >= 9:
            out["phone"] = out["phone"] or stripped.strip()
            continue
        if ln:
            rest.append(ln)

    # Country, if the sender named one, is almost always the last line.
    if rest:
        code = _country_code(rest[-1])
        if code:
            out["country"] = code
            rest = rest[:-1]

    # Postcode, searched from the bottom because that is where it lives.
    for i in range(len(rest) - 1, -1, -1):
        pc, remainder = _find_postcode(rest[i], out["country"])
        if pc:
            out["postcode"] = pc
            st = _US_STATE_RE.search(rest[i])
            if st and out["country"] in ("US", "CA", ""):
                out["state"] = st.group(1)
                remainder = remainder.replace(st.group(1), "").strip(" ,")
            if remainder:
                out["city"] = remainder            # "Manchester M1 2AB" on one line
                rest = rest[:i] + rest[i + 1:]
            else:
                rest = rest[:i] + rest[i + 1:]
                if rest:
                    out["city"] = rest[-1]         # the line above the postcode
                    rest = rest[:-1]
            break

    # A GB-shaped postcode with no country named means GB. Saying so is what makes
    # the common paste land without a round trip to Claude. Unless the area is
    # one of the Crown dependencies, which use the same shape and are outside
    # the UK customs area: "St Helier / Jersey / JE2 3AB" read as GB, confident,
    # and went domestic with no declaration.
    if not out["country"] and out["postcode"] and _UK_POSTCODE_RE.fullmatch(out["postcode"]):
        area = re.match(r"[A-Za-z]{1,2}", out["postcode"]).group(0).upper()
        out["country"] = _CROWN_POSTCODE_AREAS.get(area, "GB")

    # What is left is some combination of a person, a company and street lines.
    # Tagged in place rather than bucketed, because the sender's line order is
    # the label's line order and nothing here may be dropped: a silently lost
    # line is a parcel sent to half an address.
    tagged = []
    for ln in rest:
        started = any(t == "street" for t, _ in tagged)
        # Company is tested first. Plenty of trading names carry a word that also
        # names a street ("Broadway Lighting Inc"), and reading one as an address
        # line loses the company and makes the address residential.
        if not started and not out["company"] and not re.match(r"^\d", ln) and _COMPANY_RE.search(ln):
            out["company"] = ln
            tagged.append(("company", ln))
        elif started or re.match(r"^\d", ln) or _STREET_RE.search(ln):
            tagged.append(("street", ln))
        else:
            tagged.append(("person", ln))

    people = [v for t, v in tagged if t == "person"]
    if people:
        out["name"] = people[0]
        if len(people) > 1 and not out["company"]:
            out["company"] = people[1]     # person, then venue, then the street
    placed = {out["name"], out["company"]}
    # street and street2 stay separate: the courier caps each line at 35 chars and
    # the sender's own break carries meaning (building, then unit).
    addr_lines = [v for t, v in tagged if t == "street" or (t == "person" and v not in placed)]
    out["street"] = addr_lines[0] if addr_lines else ""
    out["street2"] = addr_lines[1] if len(addr_lines) > 1 else ""
    unplaced = addr_lines[2:]
    if unplaced:
        out["street2"] = (out["street2"] + ", " + ", ".join(unplaced)).strip(", ")

    # Confident means "do not bother Claude with this". Being wrong here is the
    # expensive direction, because a confident parse is the one nobody checks.
    confident = not _addr_ready(out) and not unplaced
    if confident and out["country"] == "GB" and not _UK_POSTCODE_RE.fullmatch(out["postcode"]):
        confident = False          # a GB postcode always carries letters
    if confident and out["country"] in set(_CROWN_POSTCODE_AREAS.values()):
        confident = False          # an island address gets a look: customs applies
    return {"address": out, "confident": confident, "unplaced": unplaced}


ADDRESS_TOOL = {
    "name": "present_address",
    "description": "Return the delivery address you read out of the pasted text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "The person the parcel is for. Blank if none."},
            "company": {"type": "string", "description": "The business name. Blank if none."},
            "street": {"type": "string", "description": "First address line, as written."},
            "street2": {"type": "string", "description": "Second address line, or blank."},
            "city": {"type": "string", "description": "Town or city."},
            "state": {"type": "string", "description": "County, state or province. Blank if none."},
            "postcode": {"type": "string", "description": "Postcode or ZIP, as written."},
            "country": {"type": "string", "description": "2-letter ISO code, e.g. GB, US, DE."},
            "phone": {"type": "string", "description": "Contact phone, or blank."},
            "email": {"type": "string", "description": "Contact email, or blank."},
        },
        "required": ["street", "city", "postcode", "country"],
    },
}

ADDRESS_SYSTEM = (
    "You read a delivery address out of text a shipper pasted from an email, and return it as "
    "structured fields for a courier booking.\n"
    "Rules: country is always a 2-letter ISO code. Keep the address lines as the sender wrote "
    "them, do not merge or reorder them, because each line is printed separately on the label. "
    "Leave a field blank if the text does not contain it. Never invent or correct a postcode, a "
    "house number or a street name: a guess here sends a parcel to the wrong place. If the text "
    "holds no address at all, return blanks."
)


async def _ai_address(text: str) -> dict:
    """Claude's reading of a pasted block, for the ones the local pass could not
    place. Plain structured output, no tools that touch the store."""
    claude._ai_kind.set("address")
    client = claude._anthropic()
    resp = await claude._xcreate(
        client, model=claude.MODEL_FAST, max_tokens=4096, system=ADDRESS_SYSTEM,
        tools=[ADDRESS_TOOL], tool_choice={"type": "tool", "name": ADDRESS_TOOL["name"]},
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": "Pasted text:\n\n" + str(text or "")[:4000]}],
    )
    got = next((b.input for b in resp.content
                if b.type == "tool_use" and b.name == ADDRESS_TOOL["name"]), None) or {}
    out = {k: "" for k in ("name", "company", "firstname", "lastname", "street", "street2",
                           "postcode", "city", "state", "country", "phone", "email")}
    for k in out:
        v = got.get(k)
        if isinstance(v, str):
            out[k] = v.strip()[:120]
    out["country"] = _country_code(out["country"]) or out["country"]
    return out


def _clean_box(box: dict):
    """Validated single box, or (None, error)."""
    try:
        b = {"width": float(box.get("width") or 0), "length": float(box.get("length") or 0),
             "depth": float(box.get("depth") or 0), "weight": float(box.get("weight") or 0)}
    except (TypeError, ValueError):
        return None, "Box dimensions and weight must be numbers."
    if min(b["width"], b["length"], b["depth"]) <= 0 or b["weight"] <= 0:
        return None, "Enter a box size (width, length, depth) and weight above zero."
    return b, ""


def _clean_parcel_list(body: dict):
    """The request's parcels: a boxes[] list, or the legacy single box. Returns
    (boxes, error). Capped at 15 parcels per shipment."""
    raw = body.get("boxes")
    if not isinstance(raw, list) or not raw:
        raw = [body.get("box") if isinstance(body.get("box"), dict) else {}]
    if len(raw) > 15:
        return None, "A shipment can carry at most 15 boxes."
    out = []
    for i, rb in enumerate(raw, start=1):
        b, err = _clean_box(rb if isinstance(rb, dict) else {})
        if err:
            return None, (f"Box {i}: {err}" if len(raw) > 1 else err)
        out.append(b)
    return out, ""


def _insurance_amount(body: dict):
    """The requested insurance cover as a string amount, '' when none."""
    v = body.get("insurance")
    try:
        f = float(v or 0)
    except (TypeError, ValueError):
        return ""
    return ("%.2f" % f) if f > 0 else ""


def _line_discount(li: dict) -> float:
    """What was taken off a line. Shopify's `price` is the unit price BEFORE
    discounts; a code or an automatic discount lands in discount_allocations."""
    total = 0.0
    for d in li.get("discount_allocations") or []:
        try:
            total += float((d or {}).get("amount") or 0)
        except (TypeError, ValueError):
            pass
    return total


def _line_unit_net(li: dict) -> Optional[float]:
    """The unit price the customer actually paid, or None when the line has no
    readable price. The discount is spread over the quantity ORDERED, which is
    what Shopify allocated it across; the value of what is still on the order
    is then this times _line_qty."""
    try:
        unit = float(li.get("price") or 0)
    except (TypeError, ValueError):
        return None
    try:
        ordered = int(li.get("quantity") or 0)
    except (TypeError, ValueError):
        ordered = 0
    ordered = ordered or core._line_qty(li) or 1
    return max(0.0, unit - _line_discount(li) / ordered)


def _order_goods_value(o: dict) -> float:
    """Sum of net unit price*qty across real items; a single unparsable price
    skips that LINE, never zeroes the whole order. Net of discounts: a trade
    customer's 20% off was declared, insured and taxed at the border as if it
    had been paid."""
    total = 0.0
    for li in (o.get("line_items") or []):
        if core._label_skip_item(str(li.get("title") or li.get("name") or "")):
            continue
        unit = _line_unit_net(li)
        if unit is None:
            continue
        total += unit * core._line_qty(li)
    return round(total, 2)


def _spread_value(boxes: list, total: float) -> list:
    """Declared value split across the parcels (customs + insurance basis).
    The rounding remainder lands on the last box so the sum equals the total."""
    if not boxes or not total or total <= 0:
        return boxes
    per = round(float(total) / len(boxes), 2)
    for b in boxes[:-1]:
        b["custom_value"] = per
    boxes[-1]["custom_value"] = round(float(total) - per * (len(boxes) - 1), 2)
    return boxes


def _goods_summary(o: dict) -> str:
    """The parcel's contents line on the waybill. Declaration names, not shop
    product names: a waybill reading "Create your own gobo" beside customs
    lines reading "Glass Optical Filter" is one parcel described two ways."""
    titles = []
    for li in (o.get("line_items") or []):
        t = str(li.get("title") or li.get("name") or "").strip()
        if not t or core._label_skip_item(t):
            continue
        t = _customs_title(t)
        if t and t not in titles:
            titles.append(t)
    return ("; ".join(titles))[:100] or "Custom glass gobos"


COST_CACHE_PATH = os.environ.get("COST_CACHE_PATH", "/data/cost_cache.json")
COST_CACHE_DAYS = 14
COST_CACHE_MAX = 2000


async def _variant_costs(registry: dict, variant_ids: list) -> dict:
    """{variant_id: cost} for each variant, cached on disk.

    A cost lives on the variant's inventory item, which needs one lookup to find
    the inventory id and another to read it. Costs change rarely, so caching turns
    a report over a month of orders from hundreds of calls into a handful."""
    want = sorted({int(v) for v in variant_ids if v})
    if not want:
        return {}
    cache = jsonstore._load_json_store(COST_CACHE_PATH, "variants", {}) or {}
    fresh_after = datetime.now(timezone.utc) - timedelta(days=COST_CACHE_DAYS)
    out, stale = {}, []
    for vid in want:
        row = cache.get(str(vid))
        at = str((row or {}).get("at") or "")
        try:
            when = datetime.fromisoformat(at) if at else None
            if when is not None and when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
        except ValueError:
            when = None
        if row and when and when >= fresh_after:
            out[vid] = row.get("cost") or ""
        else:
            stale.append(vid)

    if stale:
        # Two different lifetimes were being treated as one. The COST goes stale
        # after COST_CACHE_DAYS; the variant's inventory_item_id does not - it
        # is a permanent property of the variant, and the cache row already
        # holds it. Re-asking Shopify for it turned every refresh into
        # N + ceil(N/100) calls instead of ceil(N/100).
        known, unknown = [], []
        for vid in stale:
            inv = ((cache.get(str(vid)) or {}).get("inventory_item_id"))
            (known if inv else unknown).append((vid, inv))

        async def _inv_id(vid):
            v = await core._tool_json(registry, "shopify_get_variant", {"variant_id": vid})
            return vid, (v or {}).get("inventory_item_id")
        looked_up = await asyncio.gather(*[_inv_id(v) for v, _ in unknown],
                                         return_exceptions=True)
        pairs = known + [p for p in looked_up if isinstance(p, tuple) and p[1]]
        pairs = [p for p in pairs if p[1]]
        by_inv = {}
        ids = [str(int(p[1])) for p in pairs]
        for i in range(0, len(ids), 100):          # their cap is 100 per call
            chunk = ids[i:i + 100]
            try:
                res = await core._tool_json(registry, "shopify_get_inventory_items",
                                       {"ids": ",".join(chunk)})
                for it in (res or {}).get("inventory_items") or []:
                    by_inv[int(it.get("id") or 0)] = str(it.get("cost") or "")
            except Exception:
                logger.exception("inventory items fetch failed for a cost lookup")
        now = datetime.now(timezone.utc).isoformat()
        for vid, inv in pairs:
            cost = by_inv.get(int(inv), "")
            out[vid] = cost
            cache[str(vid)] = {"cost": cost, "inventory_item_id": int(inv), "at": now}
        try:
            if len(cache) > COST_CACHE_MAX:
                keep = sorted(cache.items(), key=lambda kv: str(kv[1].get("at") or ""))
                cache = dict(keep[-COST_CACHE_MAX:])
            if jsonstore._store_writable(COST_CACHE_PATH):
                jsonstore._write_json_store(COST_CACHE_PATH, "variants", cache)
        except Exception:
            logger.exception("could not save the cost cache")
    return out


CUSTOMS_MEMORY_PATH = os.environ.get("CUSTOMS_MEMORY_PATH", "/data/customs_memory.json")
CUSTOMS_MEMORY_MAX = 400


def _customs_key(li: dict, title: str) -> str:
    """What a remembered customs value is filed under: the variant when Shopify
    gives one, otherwise the product title normalised."""
    vid = li.get("variant_id")
    if vid:
        return "v" + str(vid)
    return "t" + re.sub(r"\s+", " ", str(title or "").strip().lower())[:120]


def _load_customs_memory() -> dict:
    return jsonstore._load_json_store(CUSTOMS_MEMORY_PATH, "items", {}) or {}


def _remember_customs(lines: list) -> None:
    """Keep what the operator actually typed, per product. The store prices custom
    gobos through option dropdowns, so their base price is zero and every
    international order needed the real value typing in by hand; remembering it
    makes the problem solve itself through use."""
    try:
        mem = _load_customs_memory()
        changed = False
        for ln in lines or []:
            key = str((ln or {}).get("key") or "").strip()
            val = (ln or {}).get("unit_price")
            if not key or val in (None, ""):
                continue
            try:
                val = round(float(val), 2)
            except (TypeError, ValueError):
                continue
            if val <= 0:
                continue
            mem[key] = {"unit_value": f"{val:.2f}",
                        "hs": str(ln.get("hs") or "")[:24],
                        "origin": str(ln.get("country") or "")[:2].upper(),
                        "description": str(ln.get("description") or "")[:120],
                        "at": datetime.now(timezone.utc).isoformat()}
            changed = True
        if not changed:
            return
        if len(mem) > CUSTOMS_MEMORY_MAX:
            keep = sorted(mem.items(), key=lambda kv: str(kv[1].get("at") or ""))
            mem = dict(keep[-CUSTOMS_MEMORY_MAX:])
        if jsonstore._store_writable(CUSTOMS_MEMORY_PATH):
            jsonstore._write_json_store(CUSTOMS_MEMORY_PATH, "items", mem)
    except Exception:
        logger.exception("could not remember the customs values")


def _shipping_paid(o: dict, ex_vat: bool = True) -> float:
    """What the customer paid for delivery, over every shipping line: net of
    its discounts (a free-shipping code), and net of VAT when `ex_vat`, which
    is how it is set against a courier's ex VAT cost. One definition for the
    booking panel, the manifest and the margin report, which disagreed."""
    ti = bool(o.get("taxes_included"))
    total = 0.0
    for sl in o.get("shipping_lines") or []:
        net = _ex_vat_line_total({"price": sl.get("price"), "quantity": 1,
                                  "tax_lines": sl.get("tax_lines"),
                                  "discount_allocations": sl.get("discount_allocations")}, ti)
        if not ex_vat:
            for t in sl.get("tax_lines") or []:
                try:
                    net += float((t or {}).get("price") or 0)
                except (TypeError, ValueError):
                    pass
        total += net
    return round(total, 2)


def _ex_vat_line_total(li: dict, taxes_included: bool) -> float:
    """What a line actually earned, net of its discounts and of VAT.

    UK stores usually show tax-inclusive prices, so the gross figure is not
    revenue: the VAT belongs to HMRC, while the cost price it is compared against
    is already net. Mixing the two overstates every margin."""
    try:
        gross = float(li.get("price") or 0) * int(li.get("quantity") or 0)
    except (TypeError, ValueError):
        return 0.0
    for d in li.get("discount_allocations") or []:
        try:
            gross -= float((d or {}).get("amount") or 0)
        except (TypeError, ValueError):
            pass
    if taxes_included:
        for t in li.get("tax_lines") or []:
            try:
                gross -= float((t or {}).get("price") or 0)
            except (TypeError, ValueError):
                pass
    return round(gross, 2)


MARGIN_BACKFILL_MAX = _env_num(int, os.environ.get("MARGIN_BACKFILL_MAX", "60"), "60", "MARGIN_BACKFILL_MAX")   # older orders fetched one by one


async def run_margin_report(registry: dict, days: int = 30) -> dict:
    """What each dispatched order actually made: revenue net of VAT and discounts,
    less what the goods cost and what the courier charged.

    Only dispatched orders appear, because the courier charge is the point of the
    exercise. An order with any item lacking a cost price in Shopify is reported
    as incomplete rather than counted, since a missing cost silently reads as pure
    profit, which is the one wrong answer worth avoiding."""
    days = max(1, min(int(days or 30), 365))
    london = ZoneInfo("Europe/London")
    cut = datetime.now(timezone.utc) - timedelta(days=days)

    dispatched = {}
    for oid, e in (_load_dispatch() or {}).items():
        if not e.get("tracking_number") or e.get("canceled"):
            continue
        # This report is margin per ORDER. A pasted-address shipment has no order,
        # no revenue and no goods cost, so it cannot have a margin. Skipping it
        # here keeps it out of the "could not be loaded from Shopify" rows, which
        # are the app's way of saying real data is missing.
        if _is_adhoc(oid):
            continue
        ts = str(e.get("dispatched_at") or "")
        try:
            when = datetime.fromisoformat(ts)
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if when >= cut:
            dispatched[str(oid)] = (e, when)
    if not dispatched:
        return {"rows": [], "totals": {}, "days": days, "note":
                "No dispatched orders in this period."}

    meta = {}
    orders = await core._orders_snapshot(
        registry, days=days + 14, meta=meta,
        fields=("id,name,created_at,currency,taxes_included,total_price,"
                "subtotal_price,total_discounts,line_items,shipping_lines,customer"))
    by_id = {str(o.get("id")): o for o in orders}
    # Dispatched inside the window but placed before it: a purchase-order
    # customer's job can sit weeks in proofing. The snapshot reaches two weeks
    # past the window; anything older is fetched by itself, so an old order is
    # a margin row rather than a "could not be loaded from Shopify" one that
    # drops its revenue and carriage from the totals.
    # Bounded, and paced by the Shopify request layer, which queues its calls
    # and backs off when rate-limited. An order past the bound is not a load
    # failure and is not reported as one: it says why it is missing.
    older = [k for k in dispatched if k not in by_id]
    unread = set(older[MARGIN_BACKFILL_MAX:])
    # Missing from a list read that failed or stopped at its cap says nothing
    # about an order's age, so only a whole read may give age as the reason.
    read_short = bool(meta.get("failed") or meta.get("truncated"))
    misses = 0
    for oid in older[:MARGIN_BACKFILL_MAX]:
        o = await core._tool_json(registry, "shopify_get_order", {"order_id": int(oid)})
        if core._ok(o) and o.get("id"):
            by_id[oid] = o
            misses = 0
        else:
            misses += 1
            if misses >= 3:   # Shopify is refusing: more single reads only keep it refusing
                break

    variant_ids = []
    for oid in dispatched:
        for li in (by_id.get(oid) or {}).get("line_items") or []:
            if li.get("variant_id"):
                variant_ids.append(li["variant_id"])
    costs = await _variant_costs(registry, variant_ids)

    rows, missing_cost = [], set()
    for oid, (entry, when) in sorted(dispatched.items(), key=lambda kv: kv[1][1]):
        o = by_id.get(oid)
        if not o:
            rows.append({"order_id": oid, "order_name": entry.get("order_name") or ("#" + oid),
                         "admin_url": core._admin_order_url(oid),
                         "incomplete": (f"placed long before this period, and the report reads at most "
                                        f"{MARGIN_BACKFILL_MAX} such orders one by one: choose a shorter period"
                                        if oid in unread and not read_short
                                        else "the order could not be loaded from Shopify")})
            continue
        taxes_included = bool(o.get("taxes_included"))
        revenue = 0.0
        goods_cost = 0.0
        unknown = []
        for li in o.get("line_items") or []:
            if core._label_skip_item(str(li.get("title") or li.get("name") or "")):
                continue
            # What is still on the order. The line's discount and VAT were
            # allocated across the quantity ORDERED, so its net total is scaled
            # by the share that remains; a refunded unit used to stay in both
            # the revenue and the goods cost.
            qty = core._line_qty(li)
            try:
                ordered = int(li.get("quantity") or 0)
            except (TypeError, ValueError):
                ordered = 0
            share = (qty / ordered) if ordered > 0 else (1.0 if qty else 0.0)
            revenue += round(_ex_vat_line_total(li, taxes_included) * min(share, 1.0), 2)
            cost = costs.get(int(li.get("variant_id") or 0) or -1, "")
            try:
                goods_cost += float(cost) * qty
            except (TypeError, ValueError):
                unknown.append(str(li.get("title") or "item"))
        # What the customer paid for delivery, net of VAT, is revenue too.
        ship_rev = _shipping_paid(o, ex_vat=True)
        # Records written before the ex VAT figure was stored only have the gross
        # charge. Using it understates the margin slightly, which is the safe
        # direction, but the row says so rather than quietly mixing the two.
        courier, courier_gross = 0.0, False
        for key, gross in (("amount_ex_vat", False), ("amount", True)):
            try:
                v = float(entry.get(key) or 0)
            except (TypeError, ValueError):
                v = 0.0
            if v:
                courier, courier_gross = v, gross
                break
        row = {
            "order_id": oid,
            "admin_url": core._admin_order_url(oid),
            "order_name": o.get("name") or entry.get("order_name") or ("#" + oid),
            "customer": entry.get("customer") or "",
            "dispatched": when.astimezone(london).strftime("%d %b"),
            "revenue": round(revenue, 2),
            "shipping_charged": round(ship_rev, 2),
            "goods_cost": round(goods_cost, 2),
            "courier_cost": round(courier, 2),
            "courier_inc_vat": courier_gross,
            "currency": o.get("currency") or entry.get("currency") or "GBP",
        }
        if unknown:
            missing_cost.update(unknown)
            row["incomplete"] = ("no cost price for " + ", ".join(sorted(set(unknown))[:3]))
        else:
            row["margin"] = round(revenue + ship_rev - goods_cost - courier, 2)
            row["margin_pct"] = (round(row["margin"] / (revenue + ship_rev) * 100, 1)
                                 if (revenue + ship_rev) > 0 else None)
        rows.append(row)

    counted = [r for r in rows if "margin" in r]
    tot = {
        "orders": len(rows),
        "counted": len(counted),
        "revenue": round(sum(r["revenue"] + r["shipping_charged"] for r in counted), 2),
        "goods_cost": round(sum(r["goods_cost"] for r in counted), 2),
        "courier_cost": round(sum(r["courier_cost"] for r in counted), 2),
        "margin": round(sum(r["margin"] for r in counted), 2),
    }
    tot["margin_pct"] = (round(tot["margin"] / tot["revenue"] * 100, 1)
                         if tot["revenue"] > 0 else None)
    tot["courier_inc_vat_rows"] = sum(1 for r in counted if r.get("courier_inc_vat"))
    return {"rows": rows, "totals": tot, "days": days,
            "missing_cost": sorted(missing_cost)[:12],
            "orders_incomplete": len(rows) - len(counted),
            "fetch_failed": bool(meta.get("failed")),
            "truncated": bool(meta.get("truncated"))}


# What gobos are called on a customs declaration. The shop's own product names
# ("Create your own gobo") mean nothing to a border officer, and this agrees
# with the HS code the same rule applies, 9002.20.000.
CUSTOMS_GOBO_DESCRIPTION = os.environ.get("CUSTOMS_GOBO_DESCRIPTION", "Glass Optical Filter")


def _is_gobo_title(title: str) -> bool:
    """One definition, used by the customs lines AND the waybill's contents
    summary, so a parcel cannot declare itself two different ways.

    The catalog's naming makes the obvious test wrong: projector products read
    "Projected Image ... Gobo Projector", so the word "gobo" appears in
    PROJECTOR names too. Projector wins."""
    low = str(title or "").lower()
    stocked = ("projector" in low) or ("projected image" in low)
    return ("gobo" in low) and not stocked


def _customs_title(title: str) -> str:
    """The shipping paperwork's name for a line: goods, not product names."""
    return CUSTOMS_GOBO_DESCRIPTION if _is_gobo_title(title) else str(title or "").strip()


async def _order_tax_id(o: dict) -> dict:
    """{"receiver_tax_id", "receiver_tax_source"} for an order, or empties.

    Never fatal and never guessed: no id simply means the operator types one
    as they always have."""
    if core._tax_id_reader is None or not o.get("id"):
        return {"receiver_tax_id": "", "receiver_tax_source": ""}
    try:
        got = await core._tax_id_reader(int(o["id"]))
    except Exception:
        logger.exception("tax id lookup failed for order %s", o.get("id"))
        return {"receiver_tax_id": "", "receiver_tax_source": ""}
    return {"receiver_tax_id": str(got.get("tax_id") or "")[:40],
            "receiver_tax_source": str(got.get("source") or "")[:80]}


async def _customs_items(registry: dict, o: dict) -> list:
    """Per-line customs facts from Shopify: the HS code and the UNIT COST both live
    on the variant's inventory item (not the product). Customs declares what the
    goods are worth to the merchant, not what the customer paid, so the cost price
    is the right value; the sale price is only a fallback when no cost is set."""
    lines = [li for li in (o.get("line_items") or [])
             if not core._label_skip_item(str(li.get("title") or li.get("name") or ""))
             and core._line_qty(li) > 0]

    async def _inv_id(li):
        vid = li.get("variant_id")
        if not vid:
            return None
        v = await core._tool_json(registry, "shopify_get_variant", {"variant_id": int(vid)})
        return (v or {}).get("inventory_item_id")

    inv_ids = await asyncio.gather(*[_inv_id(li) for li in lines], return_exceptions=True)
    inv_ids = [i if not isinstance(i, Exception) else None for i in inv_ids]
    by_id = {}
    want = sorted({int(i) for i in inv_ids if i})
    if want:
        try:
            res = await core._tool_json(registry, "shopify_get_inventory_items",
                                   {"ids": ",".join(str(i) for i in want[:100])})
            for it in (res or {}).get("inventory_items") or []:
                by_id[it.get("id")] = it
        except Exception:
            logger.exception("inventory items fetch failed; customs falls back to sale prices")
    mem = _load_customs_memory()
    out = []
    for li, inv in zip(lines, inv_ids):
        item = by_id.get(int(inv)) if inv else None
        cost = str((item or {}).get("cost") or "").strip()
        title = str(li.get("title") or "Item").strip()
        low = title.lower()
        # The catalog's naming: projector products read "Projected Image ... Gobo
        # Projector", so the word "gobo" appears in PROJECTOR names too. Projector
        # wins the classification, or every projector would be declared at sale
        # value under the gobo rule.
        is_stocked = ("projector" in low) or ("projected image" in low)
        is_gobo = _is_gobo_title(title)
        origin = str((item or {}).get("country_code_of_origin") or "").strip().upper()
        if not origin:
            # The merchant's blanket rule when Shopify does not say: projectors are
            # made in China, gobos (and everything else they make) in the UK.
            origin = "CN" if "projector" in low else "GB"
        hs = str((item or {}).get("harmonized_system_code") or "").strip()
        if not hs and is_gobo:
            # House rule: every gobo is 9002.20.000 (mounted optical filter glass).
            hs = "9002.20.000"
        # What the DECLARATION calls it. A customs officer needs the goods, not
        # the shop's product name: "Create your own gobo" means nothing at a
        # border, and the same classification already declares these under
        # 9002.20.000, mounted optical filter glass. The shop title is kept
        # alongside so the app can still name the product to the operator.
        customs_desc = _customs_title(title)
        # The sale price net of the line's discount, as a 2dp string like the
        # rest of the card; Shopify's own string when nothing was taken off.
        price = str(li.get("price") or "")
        if price and _line_discount(li) > 0 and _line_unit_net(li) is not None:
            price = f"{_line_unit_net(li):.2f}"
        # The declared value. Gobos are custom work, declared at their SALE value;
        # stocked goods (projectors and the rest) at COST, falling back to sale
        # when Shopify has no cost recorded, which the card points out.
        if is_gobo:
            unit_value, basis, needs_cost = price, "sale", False
        elif cost:
            unit_value, basis, needs_cost = cost, "cost", False
        else:
            unit_value, basis, needs_cost = price, "sale", True
        key = _customs_key(li, title)
        remembered = mem.get(key) or {}
        try:
            priced = float(price or 0) > 0
        except ValueError:
            priced = False
        if remembered.get("unit_value") and (not is_gobo or not priced):
            # What the operator typed last time beats anything derived: they were
            # looking at the actual goods. Except a gobo with a real sale price:
            # it is declared at what THIS customer paid, and the memory (kept
            # for gobos whose base price is zero) would otherwise hand one
            # customer's discount to the next.
            unit_value, basis, needs_cost = remembered["unit_value"], "remembered", False
        if remembered.get("hs"):
            hs = remembered["hs"]
        if remembered.get("origin"):
            origin = remembered["origin"]
        out.append({
            "key": key,
            "title": title,
            "customs_description": customs_desc,
            "quantity": core._line_qty(li),
            "price": price,
            "cost": cost,
            "unit_value": unit_value,
            "value_basis": basis,
            "needs_cost": needs_cost,
            "hs_code": hs,
            "origin": origin,
        })
    return out


def _wo_tech(e: BaseException, order_id="") -> dict:
    """What World Options was sent and what it said back, safe to show.

    Their errors name a .NET parameter rather than a field, so the request is
    the only way to tell WHICH field they meant. The booking path has handed
    this over since it was written; the quote path threw the exception away and
    kept only str(e), which is how an operator ends up staring at "Invalid sold
    to state province code" with no way to find out which address it means."""
    tech: dict = {}
    if getattr(e, "raw", ""):
        tech["reply"] = str(e.raw)[:2000]
    tech["sent"] = bool(getattr(e, "envelope", "")) or bool(getattr(e, "sent", False))
    if getattr(e, "envelope", ""):
        tech["request"] = str(e.envelope)[:20000]
    if not (tech.get("reply") or tech.get("request")):
        return {}
    tech["when"] = datetime.now(timezone.utc).isoformat()
    tech["order"] = str(order_id)
    return tech



def _is_shop_delivery(x) -> bool:
    """A service that delivers to a pickup shop the customer collects from: one
    World Options flagged for shop delivery, an Access Point code, or a ParcelShop
    or Access Point name (Evri ParcelShop and the like arrive as ordinary door
    quotes). Never offered and never booked: "our customers should never collect
    from shop" (Cameron, 2026-10-09)."""
    if not isinstance(x, dict):
        return False
    if x.get("delivery_dropoff"):
        return True
    code = str(x.get("service_type_code") or "").strip().lower()
    blob = (str(x.get("service_full") or "") + " " + str(x.get("service_name") or "") + " " + code).lower()
    return ("parcelshop" in blob or "parcel shop" in blob or "access point" in blob
            or code.endswith("_ap"))

async def _quote_options(origin: dict, dest: dict, boxes: list, currency: str,
                         insurance: str, cfg: dict) -> tuple:
    """Every courier option for one parcel to one address, as a single priced list.

    Takes plain data and no order, so the queue and a pasted address are priced by
    exactly the same code: a service that appears for one appears for the other.
    Returns (options, currency, error, exception). The exception rides along
    because str(e) drops the envelope, and the envelope is the evidence."""
    residential = not str(dest.get("company") or "").strip()
    dropoff = (cfg.get("collection_option") == "I_Am_Going_To_Drop_Off_My_Packages")
    # The caller has already stamped each box with its declared value.
    # Declaring the wrong shipment mode hides whole service families (a UK-to-UK
    # parcel quoted as an "Export" loses the domestic road services).
    same_country = (str(origin.get("country") or "").upper()
                    == str(dest.get("country") or "").upper())
    mode = "Domestic" if same_country else "Export"
    async def _q(delivery_dropoff: bool):
        return await worldoptions.quote(origin, dest, boxes, currency=currency,
                                        residential=residential, insurance=insurance,
                                        collection_dropoff=dropoff, shipment_mode=mode,
                                        delivery_dropoff=delivery_dropoff)

    # World Options prices with a signature service implied unless one is named, so
    # a second pass asking for no signature can come back cheaper. Both are shown
    # and labelled, because "no signature" changes what the customer gets.
    nosig_variant = "Fedex_No_Signature_Required"
    # Customers never collect from a shop (Cameron, 2026-10-09), so the quote is
    # to the door only: the pickup-shop quote that surfaced Access Point services
    # is never asked for.
    async def _q_nosig():
        return await worldoptions.quote(origin, dest, boxes, currency=currency,
                                        residential=residential, insurance=insurance,
                                        collection_dropoff=dropoff, shipment_mode=mode,
                                        signature_type=nosig_variant)
    try:
        door, nosig = await asyncio.gather(_q(False), _q_nosig(), return_exceptions=True)
    except worldoptions.WorldOptionsError as e:
        return [], currency, str(e), e
    except Exception as e:
        logger.exception("dispatch quote failed")
        errors._record_error("getting courier quotes", e)
        return [], currency, "Couldn't get courier quotes. Check the server logs.", e
    if isinstance(nosig, Exception):
        logger.info("no-signature quote unavailable: %s", nosig)
        nosig = {"options": []}
    if isinstance(door, Exception):
        if isinstance(door, worldoptions.WorldOptionsError):
            return [], currency, str(door), door
        logger.exception("dispatch quote failed", exc_info=door)
        return [], currency, "Couldn't get courier quotes. Check the server logs.", door

    res = dict(door)
    merged = list(door.get("options") or [])
    # A no-signature price only earns a row when it actually beats the normal one.
    priced = {o.get("service_type_code"): o.get("amount") for o in merged
              if o.get("service_type_code") and o.get("amount") is not None}
    for ns in (nosig.get("options") or []):
        code, amt = ns.get("service_type_code"), ns.get("amount")
        if not code or amt is None:
            continue
        base_amt = priced.get(code)
        if base_amt is None or amt >= base_amt - 0.005:
            continue
        own = worldoptions.NO_SIGNATURE_BY_CARRIER.get(
            (ns.get("carrier_name") or "").upper(), "")
        if not own:
            # UPS and the rest have no no-signature service at all, so this price
            # cannot actually be bought. Showing it would be a saving that vanishes
            # at the till, or a booking that fails.
            continue
        ns = dict(ns)
        ns["no_signature"] = True
        ns["signature_type"] = own
        ns["saves_vs_signed"] = round(base_amt - amt, 2)
        merged.append(ns)

    # Never a service the customer collects from a shop, whatever arrives.
    merged = [x for x in merged if not _is_shop_delivery(x)]
    merged.sort(key=lambda x: (x.get("amount") is None, x.get("amount") or 0))
    if not merged:
        return [], currency, ("World Options returned no courier options for this address and parcel. "
                              "Check the postcode and the parcel size, then try again."), None
    return merged, (res.get("currency") or currency), "", None


async def run_dispatch_quote(registry: dict, order_id, boxes: list,
                             insurance: str = "") -> dict:
    """Price couriers for one order to its shipping address. Free / read-only."""
    if not worldoptions or not worldoptions.configured():
        return {"error": "World Options is not connected. Add your credentials in Settings."}

    o, origin = await asyncio.gather(
        core._tool_json(registry, "shopify_get_order", {"order_id": int(order_id)}),
        core._origin_address(registry))
    if not core._ok(o) or not o.get("id"):
        return {"error": "Order not found."}
    if core._order_status(o) == "cancelled":
        return {"error": "This order is cancelled; it should not be dispatched."}
    if core._order_status(o) == "refunded":
        return {"error": "This order was refunded; dispatching it would ship goods the "
                         "customer has been paid back for."}
    dest = core._ship_to(o)
    why = _addr_ready(dest)
    if why:
        return {"error": f"This order's shipping address can't be quoted. {why}. "
                         "Fix the address in Shopify, then try again."}
    why = _addr_ready(origin)
    if why:
        return {"error": f"Your dispatch (origin) address is incomplete. {why}. "
                         "Set it under Settings, Shipping."}
    cfg = _load_shipping()
    currency = _wo_currency(o.get("currency"), cfg)
    dropoff = (cfg.get("collection_option") == "I_Am_Going_To_Drop_Off_My_Packages")
    # Declared value rides on every parcel (customs + insurance + liability basis).
    goods_value = _order_goods_value(o)
    boxes = _spread_value([dict(b) for b in boxes], goods_value)
    options, quoted, err, exc = await _quote_options(origin, dest, boxes, currency, insurance, cfg)
    if err:
        out = {"error": err}
        tech = _wo_tech(exc, order_id) if exc is not None else {}
        if tech:
            out["tech"] = tech
            _record_wo_failure(tech)
        return out
    _collection_plans(cfg, options)
    return {
        "options": options,
        "currency": quoted or currency,
        "destination": {"name": dest.get("company") or " ".join(
            x for x in [dest.get("firstname"), dest.get("lastname")] if x).strip() or dest.get("name"),
            "city": dest.get("city"), "postcode": dest.get("postcode"), "country": dest.get("country")},
        "weight": round(sum(b["weight"] for b in boxes), 3),
        "boxes": len(boxes),
        "goods_value": goods_value,
        "insurance": insurance,
        "dropoff": dropoff,
        "show_parcelshop": False,   # customers never collect from a shop
        "has_eori": bool(cfg.get("eori")),
        "default_hs_code": cfg.get("default_hs_code") or "",
        # Drives the customs-declaration card in the UI; booking refuses an
        # international shipment without an EORI and complete goods lines.
        "international": (str(dest.get("country") or "").upper() not in ("GB", "")),
        "customs_items": (await _customs_items(registry, o)
                          if str(dest.get("country") or "").upper() not in ("GB", "") else []),
        # The receiver's own tax / VAT id, when the customer gave one. Filled
        # in for the operator rather than looked up by hand on every export,
        # and it SAYS where it came from so a wrong one is spottable.
        **(await _order_tax_id(o) if str(dest.get("country") or "").upper() not in ("GB", "")
           else {"receiver_tax_id": "", "receiver_tax_source": ""}),
        "currency_note": ("" if str(o.get("currency") or "").upper() in (currency, "")
                          else f"Quoted in {currency}; the order was paid in {o.get('currency')}."),
    }


# ---------------------------------------------------------------------------
# Custom address dispatch
#
# A parcel that is not a Shopify order: a replacement, a sample, something for a
# supplier. The merchant pastes the address, adds a box and a value, and books.
#
# These shipments are filed in the same dispatch store as orders, under an
# "adhoc:<id>" key. That prefix is the whole safety argument. A Shopify order id
# is all digits, so the two can never collide, which means an ad-hoc shipment
# can never arm the double-book guard on a real order, overwrite its label, move
# its tags, or fulfil it and email that customer somebody else's tracking. Every
# reader that joins to Shopify simply fails to match and moves on, while the
# readers that do not care about orders (the end-of-day manifest, the backup,
# the eviction policy) pick these up for free.
#
# The id is minted by the browser BEFORE the first submit and reused on retry,
# so the double-book guard is real here: without an order id there is nothing
# else to recognise a second click by.
# ---------------------------------------------------------------------------

async def run_custom_quote(registry: dict, dest: dict, boxes: list,
                           insurance: str = "", declared: float = 0.0) -> dict:
    """Price couriers to a pasted address. Free and read-only, no order involved."""
    if not worldoptions or not worldoptions.configured():
        return {"error": "World Options is not connected. Add your credentials in Settings."}
    why = _addr_ready(dest)
    if why:
        return {"error": f"This address can't be quoted yet. {why}."}
    why = _country_ready(dest)
    if why:
        return {"error": why}
    origin = await core._origin_address(registry)
    why = _addr_ready(origin)
    if why:
        return {"error": f"Your dispatch (origin) address is incomplete. {why}. "
                         "Set it under Settings, Shipping."}
    cfg = _load_shipping()
    currency = _wo_currency("", cfg)     # no order to take a currency from: shop setting, then GBP
    # Same fallback the booking uses, or the quote prices a parcel declared at
    # zero and the booking sends one declared at the insured amount.
    if declared <= 0 and insurance:
        try:
            declared = float(insurance)
        except (TypeError, ValueError):
            declared = 0.0
    boxes = _spread_value([dict(b) for b in boxes], declared)
    options, quoted, err, exc = await _quote_options(origin, dest, boxes, currency, insurance, cfg)
    if err:
        out = {"error": err}
        tech = _wo_tech(exc) if exc is not None else {}
        if tech:
            out["tech"] = tech
            _record_wo_failure(tech)
        return out
    international = str(dest.get("country") or "").upper() not in ("GB", "")
    _collection_plans(cfg, options)
    return {
        "options": options,
        "currency": quoted or currency,
        "destination": {"name": dest.get("company") or dest.get("name") or "",
                        "city": dest.get("city"), "postcode": dest.get("postcode"),
                        "country": dest.get("country")},
        "weight": round(sum(float(b.get("weight") or 0) for b in boxes), 3),
        "boxes": len(boxes),
        "goods_value": declared,
        "insurance": insurance,
        "dropoff": (cfg.get("collection_option") == "I_Am_Going_To_Drop_Off_My_Packages"),
        "collection_option": str(cfg.get("collection_option") or ""),
        "collection_options": (worldoptions.COLLECTION_OPTIONS if worldoptions else []),
        "show_parcelshop": False,   # customers never collect from a shop
        "has_eori": bool(cfg.get("eori")),
        "default_hs_code": cfg.get("default_hs_code") or "",
        "international": international,
        # Nothing to prefill: there are no line items behind this parcel, so the
        # customs table is typed by hand.
        "customs_items": [],
        "currency_note": "",
    }


def _custom_id(raw) -> str:
    """The store key for a pasted-address shipment, or '' if it is not one.

    The browser mints this once per shipment so a second Book click is
    recognisable as the same shipment rather than a second parcel."""
    s = str(raw or "").strip()
    if not s.startswith(_ADHOC):
        s = _ADHOC + s
    tail = s[len(_ADHOC):]
    if not tail or not re.fullmatch(r"[A-Za-z0-9_-]{6,60}", tail):
        return ""
    return s


def _clean_address(raw: dict) -> dict:
    """A pasted address as the dict the dispatch path uses: only the keys it
    knows, each trimmed to what a courier label can hold, country as ISO-2."""
    a = raw if isinstance(raw, dict) else {}
    out = {k: re.sub(r"\s+", " ", str(a.get(k) or "")).strip()[:120]
           for k in ("name", "company", "firstname", "lastname", "street", "street2",
                     "postcode", "city", "state", "country", "phone", "email")}
    # Never truncate a country name into a code. "Isle of Man" cut to two letters
    # is IS, which is Iceland, and every wrong answer looks exactly as valid as a
    # right one. What cannot be recognised is left as typed and refused later.
    out["country"] = _country_code(out["country"]) or out["country"]
    return out


def _country_ready(dest: dict) -> str:
    """'' if the destination country is a code a courier will accept, else why not."""
    c = str((dest or {}).get("country") or "").strip()
    if re.fullmatch(r"[A-Za-z]{2}", c):
        return ""
    if not c:
        return "The country is missing."
    return ("\"" + c[:40] + "\" is not a country code. Use the 2-letter code, for example "
            "GB, IE, US or DE, so the parcel is not sent to the wrong country.")


def _shipment_key(body: dict) -> str:
    """The dispatch-store key a request is talking about: a Shopify order id, or a
    pasted-address shipment id. '' when it is neither."""
    key = _custom_id((body or {}).get("id") or "")
    if key:
        return key
    try:
        oid = int((body or {}).get("order_id") or 0)
    except (TypeError, ValueError, OverflowError):
        oid = 0
    return str(oid) if oid else ""


async def run_custom_book(registry: dict, shipment_id: str, option: dict, dest: dict,
                          boxes: list, insurance: str = "", reference: str = "",
                          contents: str = "", declared: float = 0.0,
                          customs_body: Optional[dict] = None, signature: str = "",
                          by: str = "", admin_only: bool = False) -> dict:
    """Book a courier to a pasted address. THIS SPENDS MONEY.

    Deliberately not a branch inside the order booking path: that path exists to
    tag, fulfil and notify a Shopify order, and every one of those must not
    happen here. What is shared is the part that matters, the World Options call
    and the label handling."""
    if not worldoptions or not worldoptions.configured():
        return {"error": "World Options is not connected. Add your credentials in Settings."}
    if not isinstance(option, dict) or not option.get("service_type_code"):
        return {"error": "Pick a courier service first."}
    key = _custom_id(shipment_id)
    if not key:
        return {"error": "This shipment has no id. Close the window and start it again."}
    async with core._dispatch_lock(key):
        return await _custom_book_locked(registry, key, option, dest, boxes, insurance,
                                         reference, contents, declared, customs_body,
                                         signature, by, admin_only)


async def _custom_book_locked(registry: dict, key: str, option: dict, dest: dict,
                              boxes: list, insurance: str, reference: str, contents: str,
                              declared: float, customs_body: Optional[dict],
                              signature: str, by: str, admin_only: bool = False) -> dict:
    book_store = _load_dispatch()
    if DISPATCH_STATE_PATH in jsonstore._poisoned_stores:
        return {"error": "The dispatch record is unreadable, so the app cannot tell whether this "
                         "shipment already has a label. Fix that before booking, or you risk "
                         "paying for a second one."}
    prior = book_store.get(key) or {}
    if prior.get("tracking_number") and not prior.get("canceled"):
        return {"error": "This shipment is already booked with "
                         + (prior.get("carrier_label") or prior.get("carrier_name") or "a courier")
                         + ", tracking " + str(prior.get("tracking_number"))
                         + ". Cancel it first if you need to rebook."}

    why = _addr_ready(dest)
    if why:
        return {"error": f"The delivery address is incomplete. {why}."}
    why = _country_ready(dest)
    if why:
        return {"error": why}
    origin = await core._origin_address(registry)
    why = _addr_ready(origin)
    if why:
        return {"error": f"Your dispatch (origin) address is incomplete. {why}. "
                         "Set it under Settings, Shipping."}
    cfg = _load_shipping()
    currency = _wo_currency("", cfg)
    reference = (str(reference or "").strip() or ("Shipment " + key[len(_ADHOC):][:12]))[:40]

    contact_note = ""
    if not str(origin.get("phone") or "").strip() or not str(origin.get("email") or "").strip():
        return {"error": "World Options needs a phone number and an email address on your "
                         "dispatch address. Add both under Settings, Shipping."}
    if not str(dest.get("phone") or "").strip():
        dest["phone"] = origin.get("phone")
        contact_note = "No phone for the recipient, so yours went on the label."
    if not str(dest.get("email") or "").strip():
        dest["email"] = origin.get("email")
        contact_note = (contact_note + " " if contact_note else "") + \
            "No email for the recipient, so courier updates will come to you rather than them."

    # With no order there are no line items, so the declared value is whatever the
    # merchant typed. Falling back to the insured amount keeps the two consistent:
    # insuring a parcel declared at zero is an argument the insurer wins.
    try:
        declared = float(declared or 0)
    except (TypeError, ValueError):
        declared = 0.0
    if declared <= 0 and insurance:
        try:
            declared = float(insurance)
        except (TypeError, ValueError):
            declared = 0.0
    boxes = _spread_value([dict(b) for b in boxes], declared)

    international = str(dest.get("country") or "").upper() not in ("GB", "")
    customs = None
    if international:
        # Not remembered per product the way an order's lines are: these have no
        # variant behind them, so they would land under a title key and pollute
        # the prices that prefill real orders.
        customs, boxes, why = _customs_dossier(cfg, customs_body, boxes, reference, "shipments")
        if why:
            return {"error": why}
    dropoff_shop, delivery_shop, why = _shops_for(cfg, option)
    if why:
        return {"error": why}

    who = (dest.get("company") or dest.get("name")
           or " ".join(x for x in [dest.get("firstname"), dest.get("lastname")] if x) or "")
    booked = await _book_and_record(
        # There is no order number to file a failure under, so name the
        # shipment by where it was going: an unattributable envelope is no
        # evidence at all.
        key=key, order_label=reference + " to " + str(dest.get("postcode") or ""),
        log_label="custom dispatch",
        option=option, origin=origin, dest=dest, boxes=boxes, cfg=cfg, currency=currency,
        reference=reference, description=(str(contents or "").strip()[:100] or "Goods"),
        insurance=insurance, signature=signature, collection_option="", customs=customs,
        dropoff_shop=dropoff_shop, delivery_shop=delivery_shop, international=international,
        by=by, entry_extra={
            # The manifest prints this, so it must read as something, not as the key.
            "order_name": reference,
            "customer": who,
            # Genuinely unknown rather than zero: nobody paid this app for carriage.
            "shipping_paid": "",
            # There is no order to fulfil and no customer to email, and this
            # field is what would otherwise make that happen later.
            "notify": False,
            "custom": True,
            # Set at the booking, not after it: a shipment that is nobody
            # else's business is hidden from the moment it exists, rather
            # than sitting in the queue until someone remembers to hide it.
            "admin_only": bool(admin_only),
            "contents": str(contents or "").strip()[:100],
            "declared": declared,
            "address": {k: dest.get(k, "") for k in
                        ("name", "company", "street", "street2", "city", "state",
                         "postcode", "country", "phone", "email")},
        })
    if booked.get("error"):
        return booked
    shipment, entry, book_note = booked["shipment"], booked["entry"], booked["book_note"]

    return {
        "ok": True,
        "id": key,
        "shipment": shipment,          # includes labels[] for printing now
        "warning": shipment.get("warning") or "",
        "dispatch": entry,
        "dropoff_shop": dropoff_shop,
        "delivery_shop": delivery_shop,
        "contact_note": contact_note,
        "note": book_note,
    }


def _custom_shipments(limit: int = 40, include_private: bool = True) -> list:
    """Recent pasted-address shipments, newest first. The only way back to one of
    these after the window closes: they are not in the queue, because there is no
    order for them to be a row of.

    `include_private` False drops the ones an admin has kept to admins. It
    defaults to True because this is the store's own reader: the caller that
    knows who is asking is the one that decides."""
    out = []
    for key, e in (_load_dispatch() or {}).items():
        if not _is_adhoc(key) or not isinstance(e, dict):
            continue
        if not include_private and _is_private(e):
            continue
        out.append({"id": key, "reference": e.get("order_name") or "",
                    "admin_only": _is_private(e),
                    "customer": e.get("customer") or "",
                    "carrier": e.get("carrier_label") or e.get("carrier_name") or "",
                    "service": e.get("service_name") or "",
                    "tracking": e.get("tracking_number") or "",
                    "amount": e.get("amount"), "currency": e.get("currency") or "",
                    "at": e.get("dispatched_at") or "",
                    "canceled": bool(e.get("canceled")),
                    "has_label": bool(e.get("has_label")),
                    "address": e.get("address") or {},
                    "contents": e.get("contents") or ""})
    out.sort(key=lambda r: str(r.get("at") or ""), reverse=True)
    return out[:max(1, min(int(limit or 40), 200))]


def _set_custom_private(key, on: bool) -> tuple:
    """Mark one pasted-address shipment admin-only, or let it back out.

    (ok, why). Refuses anything that is not an ad-hoc shipment already on the
    record: an order's key here would hide a real order from the queues that
    have to show it, and a key with nothing behind it would write a record for
    a shipment that was never booked."""
    k = str(key or "")
    if not _is_adhoc(k):
        return False, "Only a custom shipment can be hidden."
    if k not in (_load_dispatch() or {}):
        return False, "That shipment is not on the dispatch record."

    def mutate(entry):
        if on:
            entry["admin_only"] = True
        else:
            entry.pop("admin_only", None)
        return entry

    _update_dispatch(k, mutate)
    return True, ""


# Flag combinations tried when the merchant reports a service they expected but
# cannot see. World Options' rate request is full of non-nillable enums whose
# omitted value is their FIRST member, so a hidden service is nearly always a
# flag we are sending implicitly rather than a fault at their end.
_DIAGNOSE_VARIANTS = [
    ("As the app quotes now", {}),
    ("No signature required (FedEx wording)", {"signature_type": "Fedex_No_Signature_Required"}),
    ("No signature required (DHL wording)", {"signature_type": "DHL_No_Signature_Required"}),
    ("Asking UPS only", {"service_name": "UPS"}),
    ("UPS packaging instead of a generic parcel", {"package_type": "UPS_My_Packaging"}),
]


async def run_dispatch_diagnose(registry: dict, order_id, boxes: list) -> dict:
    """Quote the same parcel several ways and report which services each way
    returns. Read-only and free: it exists so a missing courier service can be
    explained with evidence instead of guessed at."""
    if not worldoptions or not worldoptions.configured():
        return {"error": "World Options is not connected. Add your credentials in Settings."}
    o = await core._tool_json(registry, "shopify_get_order", {"order_id": int(order_id)})
    if not core._ok(o) or not o.get("id"):
        return {"error": "Order not found."}
    dest = core._ship_to(o)
    if _addr_ready(dest):
        return {"error": "This order's shipping address is incomplete, so it cannot be quoted."}
    origin = await core._origin_address(registry)
    if _addr_ready(origin):
        return {"error": "Your dispatch address is incomplete. Set it under Settings, Shipping."}
    cfg = _load_shipping()
    currency = _wo_currency(o.get("currency"), cfg)
    same = (str(origin.get("country") or "").upper() == str(dest.get("country") or "").upper())
    base = {
        "currency": currency,
        "residential": not str(dest.get("company") or "").strip(),
        "shipment_mode": "Domestic" if same else "Export",
        "collection_dropoff": cfg.get("collection_option") == "I_Am_Going_To_Drop_Off_My_Packages",
    }
    goods_value = _order_goods_value(o)

    async def _run(extra):
        bx = _spread_value([dict(b) for b in boxes], goods_value)
        return await worldoptions.quote(origin, dest, bx, **base, **extra)

    results = await asyncio.gather(*[_run(v[1]) for v in _DIAGNOSE_VARIANTS],
                                   return_exceptions=True)
    rows, baseline = [], set()
    for (label, _flags), res in zip(_DIAGNOSE_VARIANTS, results):
        if isinstance(res, Exception):
            rows.append({"label": label, "error": str(res)[:200], "services": []})
            continue
        svcs = [{"name": ((op.get("carrier_label") or "Carrier not named")
                          + " " + (op.get("service_name") or "")).strip(),
                 "code": op.get("service_type_code") or "",
                 "delivery": " ".join(x for x in [op.get("delivery_date"), op.get("delivery_time")] if x),
                 "amount": op.get("amount"), "currency": op.get("currency")}
                for op in (res.get("options") or []) if not _is_shop_delivery(op)]
        svcs.sort(key=lambda s: (s["amount"] is None, s["amount"] or 0))
        if not rows:
            baseline = {s["code"] for s in svcs}
        for s in svcs:
            s["new"] = bool(rows) and s["code"] not in baseline
        rows.append({"label": label, "error": "", "services": svcs})
    named = {}
    for r in rows:
        for s in r["services"]:
            if s.get("new") and s["code"] not in named:
                named[s["code"]] = s["name"]
    extra_found = [{"code": k, "name": named[k]} for k in sorted(named)]
    return {"rows": rows, "extra_found": extra_found,
            "destination": dest.get("postcode"), "weight": round(sum(b["weight"] for b in boxes), 3)}


async def run_dispatch_book(registry: dict, order_id, option: dict, boxes: list,
                            notify: Optional[bool] = None, force: bool = False,
                            insurance: str = "", signature: str = "",
                            customs_body: Optional[dict] = None, by: str = "",
                            collection_option: str = "") -> dict:
    """Book the chosen courier option (this CHARGES the World Options account),
    then move the order's tag to Dispatched and create the Shopify fulfillment
    with tracking. Returns everything the UI needs to confirm what happened.

    Guards, because this spends money: serialized per order (two tabs cannot both
    book), an order with a live dispatch record is refused outright (cancel the
    shipment first), refunded orders are refused, and an order Shopify already
    shows fulfilled needs force=True (it looks already shipped)."""
    if not worldoptions or not worldoptions.configured():
        return {"error": "World Options is not connected. Add your credentials in Settings."}
    if not isinstance(option, dict) or not option.get("service_type_code"):
        return {"error": "A courier option must be selected before booking."}
    async with core._dispatch_lock(order_id):
        return await _dispatch_book_locked(registry, order_id, option, boxes, notify, force,
                                           insurance, signature, customs_body, by,
                                           collection_option)


# Their infrastructure wobbles ("Could not create SSL/TLS secure channel"), and
# a wobble at the desk costs a person a retry loop. One retry is safe ONLY when
# nothing was booked: a connect failure that never reached them, or a reply that
# ANSWERED with FAILED (their server processed and refused, creating nothing).
# A post-send silence is never retried: the first booking may have succeeded.
# Only unambiguous infrastructure failures. A TIMEOUT is deliberately NOT here:
# a timed-out reply is exactly the case where the shipment may have been created,
# which is the one thing a retry must never gamble on.
_WO_TRANSIENT_RE = re.compile(
    r"ssl|tls|secure channel|temporarily unavailable|service unavailable|"
    r"try again later|service is busy|\b50[23]\b", re.I)
# Checked FIRST, and it wins: a timeout, 504 included, is exactly the unknown
# outcome a retry must never gamble on. A relayed "(504) Gateway Timeout" used
# to match the 50x above and was re-sent.
_WO_NEVER_RETRY_RE = re.compile(r"\b504\b|gateway time-?out|timed out|time-?out", re.I)
WO_RETRY_WAIT_SECS = _env_num(int, os.environ.get("WO_RETRY_WAIT_SECS", "15"), "15", "WO_RETRY_WAIT_SECS")


async def _book_with_one_retry(*args, **kwargs):
    try:
        return await worldoptions.book(*args, **kwargs)
    except worldoptions.WorldOptionsError as e:
        if getattr(e, "ambiguous", False):
            raise      # it may have been booked: a second send could be a second charge
        never_reached = bool(getattr(e, "not_sent", False))
        answered_failed = bool(getattr(e, "sent", False))
        said = str(getattr(e, "raw", "") or e)
        transient = bool(_WO_TRANSIENT_RE.search(said)) and not _WO_NEVER_RETRY_RE.search(said)
        if never_reached or (answered_failed and transient):
            logger.warning("world options booking failed (%s); retrying once in %ss: %s",
                           "never reached them" if never_reached else "answered FAILED, transient",
                           WO_RETRY_WAIT_SECS, e)
            await asyncio.sleep(WO_RETRY_WAIT_SECS)
            try:
                return await worldoptions.book(*args, **kwargs)
            except worldoptions.WorldOptionsError as e2:
                e2.retried = True
                raise
        raise


def _collection_ready(cfg: dict, now=None):
    """When the parcel is actually ready for collection, as (dd/MM/yyyy, HH:mm).
    World Options rejects a ready-from in the past ("Invalid Date, Parcel Ready
    From"), so the settings window is a preference, not the answer: booking at
    15:20 against a 14:00 window must say ready from 15:30, and booking after the
    close (or on a weekend) must say the next working day at the window's start."""
    now = now or datetime.now(ZoneInfo("Europe/London"))

    def _hm(s, fallback):
        m = re.match(r"^(\d{1,2}):(\d{2})$", str(s or "").strip())
        return (int(m.group(1)), int(m.group(2))) if m else fallback

    rh, rm = _hm(cfg.get("ready_time"), (9, 0))
    ch, cm = _hm(cfg.get("close_time"), (17, 30))
    ready = now.replace(hour=rh, minute=rm, second=0, microsecond=0)
    close = now.replace(hour=ch, minute=cm, second=0, microsecond=0)
    if ready >= close:  # nonsense window: fall back to a plain business day
        ready = now.replace(hour=9, minute=0, second=0, microsecond=0)
        close = now.replace(hour=17, minute=30, second=0, microsecond=0)

    candidate = ready
    if now >= ready:
        # Already past the window start: ready half an hour out, on a quarter hour.
        bumped = now + timedelta(minutes=30)
        minute = ((bumped.minute + 14) // 15) * 15
        candidate = (bumped.replace(minute=0, second=0, microsecond=0)
                     + timedelta(minutes=minute))
    # Too late for a collection today (none left before close), or a weekend:
    # the next working day, from the window start.
    if candidate >= close or candidate.weekday() >= 5:
        day = candidate if candidate.weekday() >= 5 or candidate < close else candidate
        while True:
            day = (day + timedelta(days=1)).replace(hour=rh, minute=rm,
                                                    second=0, microsecond=0)
            if day.weekday() < 5:
                candidate = day
                break
    return candidate.strftime("%d/%m/%Y"), candidate.strftime("%H:%M")


# How a given courier collects. Configured per carrier because it genuinely
# differs: a daily UPS collection already calls, while DHL has to be asked each
# time. The single setting answers for any carrier nobody has configured.
COLLECTION_MESSAGES = {
    "I_Have_Daily_Collection": "Daily collection scheduled",
    "I_Already_Have_Collection_Scheduled": "A collection is already booked",
    "I_Need_To_Book_A_Collection": "Book a collection for this shipment",
    "I_Need_To_Book_A_Collection_For_Next_Day": "Book a collection for tomorrow",
    "I_Am_Going_To_Drop_Off_My_Packages": "You are dropping this one off",
}


def _collection_for(cfg: dict, carrier: str) -> str:
    by = cfg.get("collection_by_carrier")
    by = by if isinstance(by, dict) else {}
    key = str(carrier or "").strip().upper()
    return str(by.get(key) or "").strip() or str(cfg.get("collection_option") or "")


def _collection_plan(cfg: dict, carrier: str, booked: Optional[dict] = None,
                     ready_dmy: str = "") -> dict:
    """What to ask this courier for, given what has already been asked today.

    Once a collection is booked with DHL, every other DHL parcel that day rides
    the same van. Asking again books - and is charged for - a second pickup, so
    the configured "book a collection" becomes "already scheduled" for the rest
    of the day, on its own, without anyone having to remember."""
    arrangement = _collection_for(cfg, carrier)
    key = str(carrier or "").strip().upper()
    if not arrangement.startswith("I_Need_To_Book_A_Collection"):
        return {"arrangement": arrangement, "already": False,
                "message": COLLECTION_MESSAGES.get(arrangement, "")}
    target = _collection_target(arrangement, ready_dmy)
    if not isinstance(booked, dict):
        booked = _collections_for(target)
    if key and _collection_row(booked.get(key)).get("date") == target:
        when = "tomorrow" if arrangement.endswith("For_Next_Day") else "today"
        return {"arrangement": "I_Already_Have_Collection_Scheduled", "already": True,
                "message": "Collection already booked for " + when}
    return {"arrangement": arrangement, "already": False,
            "message": COLLECTION_MESSAGES.get(arrangement, "")}


def _collection_plans(cfg: dict, options: list) -> None:
    """Stamp every quoted courier with how it collects, and whether a van is
    already coming.

    Two things this has to get right, and the first version got both wrong.

    It asks about the day the BOOKING will use - the ready date the courier is
    given, which after the close is tomorrow - not "today". Comparing against
    today meant a collection booked at half five was recorded for tomorrow and
    then not found, so the next parcel was told to book all over again.

    And it reads the courier's own confirmations off the dispatch record, not
    just this app's ledger. A custom shipment never wrote that ledger, so a
    collection booked from the Shipping tab was invisible here."""
    ready_dmy = _collection_ready(cfg)[0] if cfg else ""
    days: dict = {}
    for o in options or []:
        if not isinstance(o, dict):
            continue
        day = _collection_target(_collection_for(cfg, o.get("carrier_name")), ready_dmy)
        if day not in days:          # read the two stores once per distinct day
            days[day] = _collections_for(day)
        p = _collection_plan(cfg, o.get("carrier_name"), days[day], ready_dmy)
        o["collection_option"] = p["arrangement"]
        o["collection_message"] = p["message"]
        o["collection_already"] = p["already"]


def _record_collection(carrier: str, arrangement: str, ready_dmy: str,
                       order: str = "", service: str = "") -> None:
    """A van is now coming from this carrier. Every other parcel going out with
    them that day rides it, so nothing else asks - and nothing else is charged
    for a second pickup. Called from both booking paths; the custom one used to
    skip it, which is how a booked DHL collection went unnoticed."""
    if not str(arrangement or "").startswith("I_Need_To_Book_A_Collection"):
        return
    code = str(carrier or "").strip().upper()
    if not code:
        return
    try:
        book = _load_collections()
        book[code] = {"date": _collection_target(arrangement, ready_dmy),
                      "at": datetime.now(timezone.utc).isoformat(),
                      "order": str(order or "")[:24],
                      "service": str(service or "")[:60]}
        _write_collections(book)
    except Exception:
        logger.exception("could not record the collection for %s", carrier)


def _customs_dossier(cfg: dict, customs_body: Optional[dict], boxes: list,
                     reference: str, noun: str) -> tuple:
    """(customs, boxes, error) for an international shipment: the goods lines
    from the desk, the settings' EORI/VAT/export defaults, the boxes re-spread
    so the per-parcel declared values sum to the invoice total, and each goods
    line given its weight share. One function for both booking paths, which
    carried two copies of it and would have drifted apart at the next edit.
    `noun` is "orders" or "shipments", for the message a person reads."""
    if not str(cfg.get("eori") or "").strip():
        return None, boxes, ("International " + noun + " need your EORI number. Add it under "
                             "Settings, Shipping, International, then try again.")
    lines = (customs_body or {}).get("lines") if isinstance(customs_body, dict) else None
    goods = []
    for g in (lines or []):
        if not isinstance(g, dict):
            continue
        try:
            q = int(float(g.get("quantity") or 0))
            up = float(g.get("unit_price") or 0)
        except (TypeError, ValueError):
            continue
        desc = str(g.get("description") or "").strip()
        if not desc or q <= 0 or up < 0:
            continue
        goods.append({"description": desc, "quantity": q, "unit_price": round(up, 2),
                      "weight": g.get("weight") or "",
                      "hs": str(g.get("hs") or cfg.get("default_hs_code") or "").strip(),
                      "country": str(g.get("country") or "GB").strip()})
    if not goods:
        return None, boxes, ("International " + noun + " need at least one customs goods line "
                             "(what it is, how many, unit value). Fill in the customs section "
                             "before booking.")
    total = round(sum(g["quantity"] * g["unit_price"] for g in goods), 2)
    # The dossier total is the single source of truth: re-spread the boxes so
    # the per-parcel declared values sum to the invoice total, and give each
    # goods line its weight share (WO rejects nothing, but 0 kg lines make
    # customs paperwork look wrong).
    boxes = _spread_value(boxes, total)
    total_weight = round(sum(float(bx.get("weight") or 0) for bx in boxes), 3)
    total_qty = sum(g["quantity"] for g in goods) or 1
    for g in goods:
        if not g.get("weight"):
            g["weight"] = round(total_weight * g["quantity"] / total_qty, 3)
    customs = {
        "eori": cfg.get("eori"), "vat": cfg.get("vat_number"),
        "invoice_type": "Help_Me_Generate",
        "export_reason": cfg.get("export_reason") or "Sale",
        "duties_payor": cfg.get("duties_payor") or "Duties_To_Be_Paid_By_Receiver",
        "trade_term": cfg.get("trade_term") or "",
        "invoice_number": reference,
        "receiver_tax_id": str((customs_body or {}).get("receiver_tax_id") or "")[:40],
        "receiver_company_number": str((customs_body or {}).get("receiver_company_number") or "")[:40],
        "goods": goods, "total_value": total,
    }
    return customs, boxes, ""


def _shops_for(cfg: dict, option: dict) -> tuple:
    """(dropoff_shop, delivery_shop, error). When the merchant drops off, the
    option's nearest offered shop; when the service delivers to a shop the
    customer collects from, that shop must travel with the booking."""
    dropoff_shop = None
    if cfg.get("collection_option") == "I_Am_Going_To_Drop_Off_My_Packages":
        shops = option.get("shops") or []
        if shops and isinstance(shops[0], dict):
            dropoff_shop = shops[0]
    # Customers never collect from a shop (Cameron, 2026-10-09): such a service
    # is refused here, for the Dispatch window and custom shipments alike,
    # before anything reaches World Options.
    if _is_shop_delivery(option):
        return None, None, ("Reactor never sends a parcel to a pickup shop: customers get it at "
                            "their door. Pick a to-the-door service instead.")
    return dropoff_shop, None, ""


def _intents() -> dict:
    d = jsonstore._load_json_store(BOOKING_INTENT_PATH, "intents", {})
    return d if isinstance(d, dict) else {}


def _intent_set(key, by: str) -> None:
    try:
        d = _intents()
        d[str(key)] = {"at": datetime.now(timezone.utc).isoformat(), "by": str(by or "")[:40]}
        if jsonstore._store_writable(BOOKING_INTENT_PATH):
            jsonstore._write_json_store(BOOKING_INTENT_PATH, "intents", d)
    except Exception:
        logger.exception("booking intent could not be written for %s", key)


def _intent_clear(key) -> None:
    try:
        d = _intents()
        if d.pop(str(key), None) is not None and jsonstore._store_writable(BOOKING_INTENT_PATH):
            jsonstore._write_json_store(BOOKING_INTENT_PATH, "intents", d)
    except Exception:
        logger.exception("booking intent could not be cleared for %s", key)


def _intent_open(key) -> Optional[dict]:
    """An unresolved booking on this shipment within the last two days."""
    rec = _intents().get(str(key))
    if not isinstance(rec, dict):
        return None
    try:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(str(rec.get("at")))
    except ValueError:
        return None
    return rec if age.total_seconds() < BOOKING_INTENT_HOURS * 3600 else None


async def _book_and_record(*, key, order_label: str, log_label: str, option: dict,
                           origin: dict, dest: dict, boxes: list, cfg: dict, currency: str,
                           reference: str, description: str, insurance: str, signature: str,
                           collection_option: str, customs: Optional[dict], dropoff_shop,
                           delivery_shop, international: bool, by: str, entry_extra: dict) -> dict:
    """Book at World Options and write the record: everything about a booking
    that is the same whether a Shopify order or an ad-hoc address is behind it.
    The two paths each carried their own copy - 550 lines that differed in ten
    places, most of them by accident. What differs on purpose stays with the
    caller: what the parcel is and where it goes, what goes into the record
    beyond the booking itself (`entry_extra`), and what happens afterwards.

    `key` is the dispatch record's key (the order id, or the ad-hoc key);
    `order_label` is how a failure names the shipment in the evidence file.

    Returns {"error": ...} up to the moment the courier is booked. After that
    nothing raises and nothing returns an error: the account is charged, and
    a failure reported now would have the operator book a second label."""
    left = _intent_open(key)
    if left and not _book_confirmed.get():
        when = core._london_hm(left.get("at"))
        return {"error": f"A booking for {order_label} was started at {when} and its outcome was "
                         "never recorded (the app stopped, or the answer was lost), so it may "
                         "already exist and be charged. Check your World Options portal for it "
                         "before booking again.", "unknown_booking": True}
    _intent_set(key, by)
    _ready_dmy, _ready_hm = _collection_ready(cfg)
    # What this courier is asked for. A one-off choice at the desk wins;
    # otherwise the courier's own arrangement, softened to "already scheduled"
    # when today has already booked one with them.
    _plan = _collection_plan(cfg, option.get("carrier_name"), None, _ready_dmy)
    _asked_collection = str(collection_option or _plan["arrangement"])
    try:
        shipment = await _book_with_one_retry(
            option, origin, dest, boxes, currency=currency, reference=reference,
            ready_time=_ready_hm, ready_date=_ready_dmy,
            close_time=str(cfg.get("close_time") or ""),
            # A collection rides on a shipment - World Options has no endpoint
            # for booking one on its own - so "book a collection" means asking
            # for one alongside this parcel.
            collection_option=_asked_collection,
            insurance=insurance,
            # The option's own signature wins: it is what the displayed price
            # was quoted under.
            signature=(option.get("signature_type") or signature),
            quoted_signature=(option.get("signature_type") or ""),
            dropoff_shop=dropoff_shop, customs=customs,
            description=description, delivery_shop=delivery_shop)
    except worldoptions.WorldOptionsError as e:
        # Hand the evidence to the person standing at the desk. Their errors
        # name a .NET parameter rather than a field, so the request is the only
        # way to tell which field they meant, and waiting on a developer to
        # read a server log is not a dispatch process.
        msg = str(e)
        relayed_timeout = (not getattr(e, "ambiguous", False) and bool(getattr(e, "sent", False))
                           and bool(_WO_NEVER_RETRY_RE.search(str(getattr(e, "raw", "") or e))))
        if relayed_timeout and "MAY still" not in msg:
            # World Options answered FAILED, but what it relayed is a timeout
            # behind it: the same unknown outcome the retry rule refuses to
            # re-send, so it is not a refusal here either. Read as one, the
            # guard was cleared and Book re-armed, and a second press booked
            # and charged again.
            msg += (" The shipment MAY still have been booked and charged: check your World "
                    "Options portal for a new shipment before booking again.")
        if getattr(e, "retried", False):
            msg += " The app already retried once for you; if this keeps happening it is a World Options outage."
        if not getattr(e, "ambiguous", False) and "MAY still" not in msg:
            _intent_clear(key)          # a definite refusal: nothing was booked
        out = {"error": msg}
        tech = _wo_tech(e, order_label)
        if tech:
            out["tech"] = tech
            _record_wo_failure(tech)
        return out
    except Exception as e:
        logger.exception("%s booking failed", log_label)
        errors._record_error("booking a courier", e)
        tech = {"reply": repr(e)[:2000], "when": datetime.now(timezone.utc).isoformat(),
                "order": order_label}
        _record_wo_failure(tech)
        return {"error": "The booking failed at World Options. Check the server logs; "
                         "no charge is confirmed until a tracking number comes back.",
                "tech": tech}
    if not shipment.get("tracking_number"):
        return {"error": "World Options accepted the request but returned no tracking number. "
                         "Check your World Options portal before retrying so you are not charged twice."}

    # From here the courier is BOOKED and the account is charged. Nothing below
    # may raise: an exception now would be reported as "the booking failed" and
    # the operator would book (and pay for) a second label.
    # Recorded FIRST, as the architecture says: the tracking number before the
    # label download and render, which take seconds, so a process that stops in
    # that window leaves a booked record the guard sees, not a paid-for label
    # with none. The full record replaces it below.
    try:
        _record_dispatch(key, {"tracking_number": shipment["tracking_number"],
                               "carrier_name": shipment.get("carrier_name"),
                               "service_name": shipment.get("service_name"),
                               "amount": shipment.get("amount"), "currency": shipment.get("currency"),
                               "by": str(by or "")[:40],
                               "dispatched_at": datetime.now(timezone.utc).isoformat(),
                               "fulfilled": False, "notified": False, **entry_extra})
        _intent_clear(key)
    except Exception:
        logger.exception("the first record of a booking failed, %s", order_label)
    _record_collection(shipment.get("carrier_name") or option.get("carrier_name"),
                       _asked_collection, _ready_dmy, reference,
                       shipment.get("service_name") or option.get("service_name")
                       or option.get("carrier_label") or "")
    try:
        shipment["labels"] = await _resolve_label_links(shipment.get("labels") or [])
    except Exception:
        logger.exception("label download failed after booking %s; keeping the links", order_label)
    try:
        shipment["labels"] = _with_print_images(shipment.get("labels") or [])
    except Exception:
        logger.exception("label render failed after booking %s; Download still works", order_label)
    try:
        _save_dispatch_labels(key, shipment.get("labels") or [])
    except Exception:
        logger.exception("saving labels failed after a successful booking, %s", order_label)
    entry = {
        "tracking_number": shipment["tracking_number"],
        "carrier_name": shipment.get("carrier_name"),
        "carrier_known": shipment.get("carrier_known") or shipment.get("carrier_name") or "",
        # The readable name is stored beside the booking enum: the queue shows
        # this weeks later, and re-deriving it needs the quote that is long gone.
        "carrier_label": (shipment.get("carrier_label") or option.get("carrier_label")
                          or worldoptions.carrier_display(shipment.get("carrier_name") or "")),
        "service_name": shipment.get("service_name"),
        "service_code": option.get("service_type_code") or "",
        "product_code": option.get("product_code") or "",
        "amount": shipment.get("amount"),
        "amount_ex_vat": option.get("amount_ex_vat"),
        # Which staff member booked it: with one operator this is noise, with
        # two it is the answer to "who booked this and why is it wrong".
        "by": str(by or "")[:40],
        "customer": (dest.get("company") or dest.get("name")
                     or " ".join(x for x in [dest.get("firstname"), dest.get("lastname")] if x) or ""),
        "currency": shipment.get("currency"),
        "dispatched_at": datetime.now(timezone.utc).isoformat(),
        "fulfilled": False,
        "notified": False,
        "has_label": bool(shipment.get("labels")),
        "label_report": shipment.get("label_report") or [],
        "collection_date": shipment.get("collection_date") or "",
        # The day the courier was asked to come. A collection belongs to THIS
        # date, not to the moment the booking happened: book after the close on
        # a Friday and the van comes Monday.
        "ready_date": _ready_dmy,
        "insured": insurance or "",
        "international": international,
        # The address the label was cut for, so an edit made after it (or one
        # whose answer was lost) can be compared with it.
        "booked_address": {k: str((dest or {}).get(k) or "") for k in core._ADDR_COMPARE},
        "dropoff": (dropoff_shop or {}).get("name") or "",
        "delivery_shop": (delivery_shop or {}).get("name") or "",
        **entry_extra,
    }
    book_note = ""
    try:
        _record_dispatch(key, entry)
    except Exception:
        logger.exception("recording the dispatch failed after a successful booking, %s", order_label)
        book_note = ("The label was booked but the app could not save it. Write the tracking "
                     "number down before closing this window.")
    return {"ok": True, "shipment": shipment, "entry": entry, "book_note": book_note}


async def _dispatch_book_locked(registry: dict, order_id, option: dict, boxes: list,
                                notify, force: bool, insurance: str, signature: str,
                                customs_body: Optional[dict], by: str = "",
                                collection_option: str = "") -> dict:
    book_store = _load_dispatch()
    if DISPATCH_STATE_PATH in jsonstore._poisoned_stores:
        return {"error": "The dispatch record cannot be read, so there is no way to tell "
                         "whether this order already has a label. Nothing was booked. "
                         "Check World Options directly and ask your developer to repair "
                         "the file before dispatching again."}
    existing = book_store.get(str(order_id)) or {}
    if existing.get("tracking_number") and not existing.get("canceled"):
        who = (existing.get("carrier_label")
               or worldoptions.carrier_display(existing.get("carrier_name") or "")
               or existing.get("service_name") or "a courier")
        svc = existing.get("service_name") or ""
        return {"error": "This order was already dispatched: " + who
                         + (" " + svc if svc and svc != who else "")
                         + " tracking " + existing.get("tracking_number", "")
                         + ". Cancel that shipment first if you need to rebook."}

    o = await core._tool_json(registry, "shopify_get_order", {"order_id": int(order_id)})
    if not core._ok(o) or not o.get("id"):
        return {"error": "Order not found."}
    if core._order_status(o) == "cancelled":
        return {"error": "This order is cancelled; it should not be dispatched."}
    if core._order_status(o) == "refunded":
        return {"error": "This order was refunded; dispatching it would ship goods the "
                         "customer has been paid back for."}
    if (core._order_status(o) == "fulfilled"
            and not (existing.get("canceled") and not existing.get("fulfilled"))
            and not force):
        return {"error": "Shopify shows this order as already fulfilled, which usually means "
                         "it has shipped. If you are sure, book it from the World Options "
                         "portal, or retry with the confirmation.",
                "needs_force": True}
    dest = core._ship_to(o)
    if _addr_ready(dest):
        return {"error": "This order's shipping address is incomplete; fix it in Shopify first."}
    origin = await core._origin_address(registry)
    if _addr_ready(origin):
        return {"error": "Your dispatch (origin) address is incomplete. Set it under Settings, Shipping."}
    cfg = _load_shipping()
    currency = _wo_currency(o.get("currency"), cfg)
    reference = str(o.get("name") or o.get("order_number") or order_id)

    # World Options validates that BOTH ends carry a phone and an email before it
    # will book. The origin must be complete (it is the merchant's own address);
    # a missing customer phone/email falls back to the shop's, with a note.
    contact_note = ""
    if not str(origin.get("phone") or "").strip() or not str(origin.get("email") or "").strip():
        return {"error": "World Options requires a phone number and email for the collection "
                         "address. Add them to your dispatch address under Shipping settings."}
    fell_back = []
    if not str(dest.get("phone") or "").strip():
        dest["phone"] = origin.get("phone")
        fell_back.append("phone")
    if not str(dest.get("email") or "").strip():
        dest["email"] = origin.get("email")
        fell_back.append("email")
    if fell_back:
        contact_note = ("The customer's order has no " + " or ".join(fell_back)
                        + ", so your shop's was sent as the delivery contact. Courier delivery "
                          "updates will come to you, not the customer.")

    # Declared value on every parcel; the customs goods total overrides it below
    # for international shipments so the invoice and the boxes always agree.
    goods_value = _order_goods_value(o)
    boxes = _spread_value([dict(bx) for bx in boxes], goods_value)

    # International: the customs dossier is REQUIRED, assembled from settings
    # (EORI, VAT, export defaults) + the per-shipment goods lines from the UI.
    international = str(dest.get("country") or "").upper() not in ("GB", "")
    customs = None
    if international:
        lines = (customs_body or {}).get("lines") if isinstance(customs_body, dict) else None
        # Remember what was typed BEFORE the booking is attempted: the values are
        # right whether or not World Options accepts the shipment, and a failed
        # booking is exactly when nobody wants to retype them.
        _remember_customs(lines or [])
        customs, boxes, why = _customs_dossier(cfg, customs_body, boxes, reference, "orders")
        if why:
            return {"error": why}
    dropoff_shop, delivery_shop, why = _shops_for(cfg, option)
    if why:
        return {"error": why}
    do_notify = cfg.get("notify_customer", True) if notify is None else bool(notify)

    booked = await _book_and_record(
        key=int(order_id), order_label=str(order_id), log_label="dispatch",
        option=option, origin=origin, dest=dest, boxes=boxes, cfg=cfg, currency=currency,
        reference=reference, description=_goods_summary(o), insurance=insurance,
        signature=signature, collection_option=collection_option, customs=customs,
        dropoff_shop=dropoff_shop, delivery_shop=delivery_shop, international=international,
        by=by, entry_extra={
            # Who and what, so the end-of-day manifest reads without a Shopify
            # join, and what the customer paid for delivery, so margin is one
            # subtraction.
            "order_name": str(o.get("name") or ("#" + str(order_id))),
            # Net of discounts and of VAT, as the manifest sets it against the
            # courier's ex VAT cost: the list price called a free-shipping
            # order "covered" by the full delivery charge.
            "shipping_paid": ("%.2f" % _shipping_paid(o, ex_vat=True)) if o.get("shipping_lines") else "",
            # The merchant's email choice is made HERE but used when the order
            # is marked made, which is when Shopify is actually told it shipped.
            "notify": do_notify,
        })
    if booked.get("error"):
        return booked
    shipment, entry, book_note = booked["shipment"], booked["entry"], booked["book_note"]

    # Booking a label is preparation, not shipping: fulfilment waits until the
    # order is ALSO marked made. If it already is, this fulfils right now.
    try:
        ready = await core._fulfill_if_ready(registry, int(order_id), notify=do_notify)
    except Exception:
        logger.exception("post-booking fulfilment check failed for order %s", order_id)
        ready = {"fulfilled": False, "reason": "error", "notified": False, "tag_note": "",
                 "detail": "The label was booked. Shopify could not be updated just now; "
                           "press Refresh and mark the order made when you are ready."}
    entry = _load_dispatch().get(str(int(order_id))) or entry
    fulfillment = ({"ok": True, "fulfillment_id": entry.get("fulfillment_id")} if ready["fulfilled"]
                   else {"ok": False, "reason": ready["reason"], "detail": ready["detail"]})

    return {
        "ok": True,
        "shipment": shipment,          # includes labels[] for printing now
        "fulfillment": fulfillment,
        "tag": {"ok": not ready["tag_note"], "note": ready["tag_note"]},
        "notified": bool(ready["notified"]),
        "awaiting_made": (ready["reason"] == "not_made"),
        "warning": shipment.get("warning") or "",
        "dispatch": entry,
        "dropoff_shop": dropoff_shop,
        "delivery_shop": delivery_shop,
        "insured": insurance,
        "international": international,
        "contact_note": contact_note,
        "book_note": book_note,
    }

# -----------------------------------------------------------------------
# Shipping settings + Dispatch (World Options). The courier API key and
# write actions live entirely outside the AI tool registry.
# -----------------------------------------------------------------------
def _shipping_public(cfg: dict) -> dict:
    """Config for the UI: everything EXCEPT the credentials (never echoed)."""
    return {
        "origin": cfg.get("origin") or {},
        "boxes": cfg.get("boxes") or [],
        "default_box_id": cfg.get("default_box_id") or "",
        "notify_customer": bool(cfg.get("notify_customer", True)),
        "currency": cfg.get("currency") or "GBP",
        "plugin_code": cfg.get("plugin_code") or "Web_Service",
        "plugin_codes": (worldoptions.PLUGIN_CODES if worldoptions else []),
        "ready_time": cfg.get("ready_time") or "",
        "close_time": cfg.get("close_time") or "",
        "collection_option": cfg.get("collection_option") or "I_Need_To_Book_A_Collection",
        "show_parcelshop": False,   # customers never collect from a shop
        "collection_options": (worldoptions.COLLECTION_OPTIONS if worldoptions else []),
        "collection_by_carrier": (cfg.get("collection_by_carrier")
                                  if isinstance(cfg.get("collection_by_carrier"), dict) else {}),
        "collection_messages": COLLECTION_MESSAGES,
        "carriers": (worldoptions.carrier_choices() if worldoptions else []),
        "label_size_production": cfg.get("label_size_production") or "4x4",
        "label_size_shipping": cfg.get("label_size_shipping") or "4x6",
        "label_stock": list(LABEL_STOCK),
        "eori": cfg.get("eori") or "",
        "vat_number": cfg.get("vat_number") or "",
        "default_hs_code": cfg.get("default_hs_code") or "",
        "export_reason": cfg.get("export_reason") or "Sale",
        "export_reasons": (worldoptions.EXPORT_REASONS if worldoptions else []),
        "duties_payor": cfg.get("duties_payor") or "Duties_To_Be_Paid_By_Receiver",
        "duties_payors": (worldoptions.DUTIES_PAYORS if worldoptions else []),
        "trade_term": cfg.get("trade_term") or "",
        "signature_options": (worldoptions.SIGNATURE_OPTIONS if worldoptions else {}),
        "base_url": cfg.get("base_url") or "",
        "connected": bool(worldoptions and worldoptions.configured()),
        "meter_last4": (worldoptions.meter_last4() if worldoptions else ""),
        "has_key": bool(worldoptions and worldoptions.has_key()),
        "has_password": bool(worldoptions and worldoptions.has_password()),
        "creds_from_env": _wo_creds_from_env(),
        "available": bool(worldoptions),
    }

def _finite(v, places: int = 2) -> float:
    """A real number or nothing. float("nan") and float("Infinity") both
    parse, survive round(), and save; the file reads back fine, but every
    later GET of the config dies inside JSONResponse (allow_nan=False) and
    the shipping panel cannot be opened again without hand-editing the
    volume."""
    n = round(float(v or 0), places)
    if n != n or n in (float("inf"), float("-inf")):
        raise ValueError("not a finite measurement")
    return n

def _clean_boxes(raw) -> list:
    out = []
    for b in (raw or [])[:24]:
        if not isinstance(b, dict):
            continue
        try:
            box = {
                "id": str(b.get("id") or "")[:40] or ("box%d" % (len(out) + 1)),
                "name": str(b.get("name") or "Box")[:60],
                "width": _finite(b.get("width")),
                "length": _finite(b.get("length")),
                "depth": _finite(b.get("depth")),
                "weight": _finite(b.get("weight"), 3),
            }
        except (TypeError, ValueError):
            continue
        out.append(box)
    return out

def _clean_origin(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    keys = ("name", "company", "firstname", "lastname", "street",
            "postcode", "city", "state", "country", "phone", "email")
    return {k: str(raw.get(k) or "").strip()[:120] for k in keys}


# Last, so the whole desk is defined before copilot.py runs: copilot.py takes
# two names from it as it loads, and either module may be imported first.
import copilot as core  # noqa: E402
