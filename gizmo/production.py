"""Production: its tag and window, the production state (printed, made,
archived), the label builder (run_production_labels and the label's order
shape, product, option and item readers, projectors and the label logo),
release and the tag moves, missing production, and payment terms on release.

Moved out of copilot.py (stage 4 of the 14 October audit). What the bench
prints is pinned by t_the_printed_labels_do_not_change. Read as
`production.NAME`.
"""
import logging
from typing import Optional
import os
import re
import json
import time
import asyncio
from datetime import datetime, timezone
from gizmo.config import _env_num
from gizmo.store import StoreUnwritable
from gizmo import store as jsonstore

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


# ---------------------------------------------------------------------------
# Production labels: orders carrying the production tag, shaped for printing a
# picking/production label (order number, who it is for, and what to build).
# No AI is involved; this is a plain Shopify read.
# ---------------------------------------------------------------------------


PRODUCTION_TAG     = os.environ.get("PRODUCTION_LABEL_TAG", "IP")              # order tag that means "in production"
PRODUCTION_DAYS    = _env_num(int, os.environ.get("PRODUCTION_LABEL_DAYS", "180"), "180", "PRODUCTION_LABEL_DAYS")       # how far back to look for tagged orders

PRODUCTION_STATE_PATH = os.environ.get("PRODUCTION_STATE_PATH", "/data/production_state.json")
PRODUCTION_STATE_MAX = _env_num(int, os.environ.get("PRODUCTION_STATE_MAX", "1000"), "1000", "PRODUCTION_STATE_MAX")


def _load_prod_state() -> dict:
    return jsonstore._load_json_cached(PRODUCTION_STATE_PATH, "orders", {})


PRODUCTION_ARCHIVE_PATH = os.environ.get(
    "PRODUCTION_ARCHIVE_PATH",
    os.path.join(os.path.dirname(PRODUCTION_STATE_PATH) or ".", "production_state_archive.jsonl"))


class ProdStateUnwritable(StoreUnwritable):
    """The production state could not be saved. Raised rather than returned,
    because the caller has usually ALREADY fulfilled Shopify and booked glass
    by this point - reporting success would leave the merchant believing a
    stamp exists that will vanish on the next reload."""


def _write_prod_state(orders: dict) -> dict:
    if not jsonstore._store_writable(PRODUCTION_STATE_PATH):
        jsonstore._forget_store(PRODUCTION_STATE_PATH)
        raise ProdStateUnwritable("the production state store is not writable")
    if len(orders) > PRODUCTION_STATE_MAX:
        # Evict the least-recently-touched entries. Sort by the NEWEST stamp so an
        # order printed months ago but made yesterday is treated as recent, not
        # stale. Any evicted entry that carries a made_at is archived first, so the
        # per-day stock-usage HISTORY it feeds survives the eviction.
        def newest(kv):
            e = kv[1]
            return max(str(e.get("printed_at") or ""), str(e.get("made_at") or ""))
        keep = sorted(orders.items(), key=newest)
        evicted = keep[:-PRODUCTION_STATE_MAX]
        archive = [{"order_id": oid, "made_at": e["made_at"]}
                   for oid, e in evicted if e.get("made_at")]
        if archive:
            try:
                os.makedirs(os.path.dirname(PRODUCTION_ARCHIVE_PATH) or ".", exist_ok=True)
                with open(PRODUCTION_ARCHIVE_PATH, "a", encoding="utf-8") as fh:
                    for rec in archive:
                        fh.write(json.dumps(rec) + "\n")
            except Exception:
                logger.exception("production archive append failed")
        orders = dict(keep[-PRODUCTION_STATE_MAX:])
    jsonstore._write_json_store(PRODUCTION_STATE_PATH, "orders", orders)
    return orders


def _archived_made(order_ids_wanted: set) -> dict:
    """{order_id: made_at} for archived (evicted) made stamps, so stock-usage
    history for a past day still finds orders that fell out of the live state."""
    out: dict = {}
    try:
        with open(PRODUCTION_ARCHIVE_PATH, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                oid, ma = str(rec.get("order_id") or ""), rec.get("made_at")
                if oid and ma:
                    out[oid] = ma   # last write wins (a re-made order)
    except FileNotFoundError:
        pass
    except Exception:
        logger.exception("production archive read failed")
    return out


def _mark_printed(order_ids: list) -> bool:
    """Best-effort: a failed stamp must never break a print. Returns whether the
    stamp actually persisted so callers can say so."""
    try:
        state = _load_prod_state()
        if not jsonstore._store_writable(PRODUCTION_STATE_PATH):
            return False
        now = datetime.now(timezone.utc).isoformat()
        for oid in order_ids:
            entry = state.setdefault(str(oid), {})
            entry["printed_at"] = now
        _write_prod_state(state)
        return True
    except ProdStateUnwritable:
        return False          # the caller already reports this to the merchant
    except Exception:
        logger.exception("production state: printed stamp failed")
        return False


def _mark_made(order_id, on: bool) -> dict:
    state = _load_prod_state()
    entry = state.setdefault(str(order_id), {})
    if on:
        entry["made_at"] = datetime.now(timezone.utc).isoformat()
    else:
        entry.pop("made_at", None)
    if not entry:
        state.pop(str(order_id), None)
    return _write_prod_state(state)


def _label_party(order: dict) -> tuple:
    """(company, person) for the label. A company name wins when the order has one,
    falling back to the customer's own name."""
    ship = order.get("shipping_address") or {}
    bill = order.get("billing_address") or {}
    cust = order.get("customer") or {}
    dflt = cust.get("default_address") or {}
    company = next((str(c).strip() for c in (ship.get("company"), bill.get("company"), dflt.get("company"))
                    if c and str(c).strip()), "")
    person = " ".join(p for p in [str(cust.get("first_name") or "").strip(),
                                  str(cust.get("last_name") or "").strip()] if p).strip()
    if not person:
        person = next((str(n).strip() for n in (ship.get("name"), bill.get("name"), cust.get("email"))
                       if n and str(n).strip()), "")
    return company, person


def _variant_is_real(li: dict) -> bool:
    vt = str(li.get("variant_title") or "").strip()
    return bool(vt) and vt.lower() != "default title"


_PRICE_SUFFIX_RE = re.compile(r"[\s\-|,·]*[\(\[]?\s*[+-]?\s*[£$€]\s*\d[\d,]*(?:\.\d+)?\s*[\)\]]?\s*$")


def _strip_price(v) -> str:
    """Drop a trailing price from an option value: the store's dropdowns price the
    add-ons, so "Monochrome Glass - Original £85" reaches the order as one string.
    A production label never shows prices."""
    s = str(v or "").strip()
    while True:
        cut = _PRICE_SUFFIX_RE.sub("", s).strip()
        if cut == s:
            return s
        s = cut


def _line_options(li: dict, option_names: dict) -> list:
    """Selected options for a line item, as [{name, value}].

    Two sources, both shown: custom line-item properties (already name/value, e.g.
    "Gobo Size"), and variant options, whose names come from the product's option
    definitions so a variant reads "Gobo Size: 20 Watt Range" rather than a bare value."""
    opts: list = []
    seen = set()

    def add(name: str, value: str) -> None:
        name, value = str(name or "").strip(), _strip_price(value)
        if not value:
            return
        key = (name.lower(), value.lower())
        if key in seen:
            return
        seen.add(key)
        opts.append({"name": name, "value": value})

    for p in (li.get("properties") or []):
        if isinstance(p, dict):
            nm = str(p.get("name") or "").strip()
            if nm.startswith("_"):      # Shopify convention for hidden/internal properties
                continue
            add(nm, p.get("value"))

    if _variant_is_real(li):
        values = [v.strip() for v in str(li.get("variant_title")).split(" / ")]
        names = option_names.get(li.get("product_id")) or []
        for i, val in enumerate(values):
            add(names[i] if i < len(names) else "Option", val)
    return opts


# Product option names are a definition, not data: nothing in this app writes
# products, and the merchant changes an option name close to never. Uncached,
# a queue load spent up to 40 Shopify calls re-learning that a gobo has a
# "Gobo Size" option. Held per process, so a redeploy relearns them; a miss is
# harmless anyway (the variant renders as the generic "Option").
OPTION_CACHE_SECS = _env_num(int, os.environ.get("OPTION_CACHE_SECS", "21600"), "21600", "OPTION_CACHE_SECS")   # 6 hours
OPTION_CACHE_MAX  = 500
_option_names_cache: dict = {}   # product_id -> {"at": monotonic, "names": [...]}


def _product_ids(product_ids) -> list:
    """De-duped, blanks out, and bounded at 40: a line past the cap keeps the
    generic text it always had."""
    return [p for p in dict.fromkeys(product_ids) if p][:40]


async def _product_meta(registry: dict, product_ids) -> dict:
    """Map product_id -> {"names": its option names, "type": its product type}.
    One product read answers both, so the option names a label prints and the
    type that tells a stock gobo from a custom one share a cache entry."""
    return await _product_meta_fetch(registry, _product_ids(product_ids))


async def _product_names_and_types(registry: dict, names_ids, type_ids) -> tuple:
    """(option names by product, product types by product) for a queue: each
    list bounded on its own as before, and everything either needs fetched
    in one go. Asked separately, the types were a second round after the
    names (the 2026-10-12 speed audit, X7)."""
    a, b = _product_ids(names_ids), _product_ids(type_ids)
    meta = await _product_meta_fetch(registry, list(dict.fromkeys(a + b)))
    return ({p: meta[p]["names"] for p in a}, {p: meta[p]["type"] for p in b})


async def _product_meta_fetch(registry: dict, ids: list) -> dict:
    if not ids:
        return {}
    now = time.monotonic()
    out, misses = {}, []
    for pid in ids:
        hit = _option_names_cache.get(pid)
        # An entry cached before the type was recorded is a miss, not "no type".
        if hit and (now - hit["at"]) < OPTION_CACHE_SECS and "type" in hit:
            out[pid] = {"names": hit["names"], "type": hit["type"]}
        else:
            misses.append(pid)
    if not misses:
        return out

    async def one(pid):
        d = await shopify._tool_json(registry, "shopify_get_product", {"product_id": pid})
        if not shopify._ok(d):
            return pid, [], "", False
        return (pid, [str(o.get("name") or "").strip() for o in (d.get("options") or [])],
                str(d.get("product_type") or "").strip(), True)

    async def all_at_once():
        # One read for every product missing (the 2026-10-12 speed audit, X7).
        # A product it did not return is blank this time and asked for again
        # next time, as a failed single read was; if the read itself fails,
        # the products are read one at a time as they always were.
        got = {}
        for i in range(0, len(misses), 100):
            got.update(await shopify._product_meta_reader(misses[i:i + 100]))
        return [(pid, got[pid]["names"], got[pid]["type"], True) if pid in got else (pid, [], "", False)
                for pid in misses]

    answers = None
    if shopify._product_meta_reader is not None:
        try:
            answers = await all_at_once()
        except Exception as e:
            logger.warning("products read in one go failed (%s); reading them one at a time", type(e).__name__)
    if answers is None:
        answers = await asyncio.gather(*[one(i) for i in misses])
    for pid, names, ptype, good in answers:
        out[pid] = {"names": names, "type": ptype}
        if good:   # a failed read is not an answer, so it is never cached
            _option_names_cache[pid] = {"at": time.monotonic(), "names": names, "type": ptype}
    while len(_option_names_cache) > OPTION_CACHE_MAX:
        _option_names_cache.pop(min(_option_names_cache,
                                    key=lambda k: _option_names_cache[k]["at"]), None)
    return out


async def _product_option_names(registry: dict, product_ids) -> dict:
    """Map product_id -> its option names (e.g. ["Gobo Size"])."""
    return {pid: m["names"] for pid, m in (await _product_meta(registry, product_ids)).items()}


# The merchant's brand lockup, lifted from their own label tool ("Order Label
# Printing.html"). Attribute quotes normalized to singles for embedding.
_LABEL_LOGO_SVG = "<svg class='lg' xmlns='http://www.w3.org/2000/svg' viewBox='0 0 267.36 51.79'><g><path fill='#111' d='M32.08,2.2c3.79,0,11.01.3,16.85,2.31,5.16,1.77,7.78,4.38,7.78,7.74,0,4.08-4.3,11.34-10.69,18.07-9.12,9.61-20.43,16.85-26.29,16.85-2.14,0-6.42-3.75-10.78-11.97C4.79,27.34,2.2,18.36,2.2,11.76c0-3.74,1.55-4.7,5.07-6l.49-.18c3.39-1.26,9.06-3.38,24.31-3.38M32.08,0C15.7,0,10.05,2.39,6.51,3.7,2.98,5,0,6.4,0,11.76c0,15.11,12.11,37.62,19.73,37.62,6.91,0,18.85-8.03,27.88-17.54,6.53-6.88,11.29-14.66,11.29-19.59C58.91,2.38,43.15,0,32.08,0'/><path fill='#111' d='M80.07,14.81c-.66-.53-1.44-.92-2.35-1.18-.91-.26-1.9-.39-2.97-.39h-3.36s-1.17,0-1.17,0h-2.36s0,18.34,0,18.34h3.53s0-5.53,0-5.53h2.5c1.8,0,3.31-.25,4.53-.74s2.15-1.21,2.78-2.17c.63-.95.94-2.13.94-3.52,0-1.07-.18-2.02-.54-2.82-.36-.81-.87-1.47-1.53-2M77.46,22.33c-.71.56-1.78.83-3.21.83h-2.86v-7.06h3.11c1.37,0,2.39.29,3.04.88.66.58.99,1.46.99,2.63,0,1.26-.36,2.17-1.07,2.72'/><path fill='#111' d='M91.4,16.74c-.76,0-1.42.21-1.97.64-.56.43-1.01,1.09-1.36,2-.35.91-.58,2.09-.69,3.56h-.33s.17-5.86.17-5.86h-3.09s.03,7.14.03,7.14v7.37s3.5,0,3.5,0v-5.73c.06-1.15.22-2.13.49-2.93.27-.81.65-1.42,1.14-1.85.49-.43,1.08-.64,1.76-.64.28,0,.58.04.92.13.33.08.67.21,1,.37l.17-3.81c-.3-.15-.59-.25-.89-.31-.3-.06-.57-.08-.83-.08'/><path fill='#111' d='M107.27,20.11c-.61-1.13-1.46-1.98-2.53-2.56-1.07-.57-2.3-.86-3.67-.86s-2.57.28-3.64.83c-1.07.56-1.93,1.4-2.56,2.53-.63,1.13-.94,2.56-.94,4.28s.31,3.1.92,4.23c.61,1.13,1.46,1.98,2.53,2.56,1.07.57,2.31.86,3.7.86s2.54-.27,3.63-.82c1.08-.55,1.94-1.39,2.56-2.52.62-1.13.93-2.56.93-4.28s-.31-3.12-.92-4.25M104.21,27.1c-.28.71-.67,1.26-1.18,1.63s-1.14.56-1.88.56c-1.15,0-2.05-.44-2.7-1.32-.65-.88-.97-2.11-.97-3.68,0-1,.14-1.86.42-2.57.28-.71.68-1.26,1.2-1.64.52-.38,1.15-.57,1.89-.57s1.41.2,1.96.61c.55.41.96.98,1.25,1.72.29.74.43,1.64.43,2.7,0,1-.14,1.86-.42,2.57'/><path fill='#111' d='M112.25,11.88c-.7,0-1.24.15-1.61.45-.37.3-.56.73-.56,1.31s.19,1.01.56,1.31.91.44,1.61.44,1.24-.15,1.61-.46c.37-.31.56-.73.56-1.26,0-.57-.19-1.01-.56-1.32-.37-.31-.91-.46-1.61-.46'/><path fill='#111' d='M110.5,31.03c0,.93-.2,1.52-.61,1.76-.41.25-1.08.31-2.03.18l.28,3.06c.28.06.54.1.79.14.25.04.5.06.74.06.67,0,1.27-.1,1.81-.31.54-.2,1-.52,1.38-.94.38-.43.67-.97.88-1.63.2-.66.31-1.44.31-2.35v-13.92s-3.53,0-3.53,0v13.95Z'/><path fill='#111' d='M126.39,27.46c-.11.34-.29.65-.53.92-.24.27-.55.49-.93.65-.38.17-.86.25-1.43.25-1.24,0-2.19-.4-2.85-1.21-.6-.73-.91-1.81-.96-3.2l9.79-.12c.13-1.22.08-2.32-.14-3.31-.22-.98-.6-1.83-1.14-2.54-.54-.71-1.23-1.26-2.07-1.64-.84-.38-1.82-.57-2.93-.57-1.17,0-2.19.2-3.06.61-.87.41-1.59.97-2.17,1.7-.57.72-1.01,1.56-1.29,2.52-.29.95-.43,1.98-.43,3.07s.14,2.06.43,2.96c.29.9.73,1.68,1.32,2.34.59.66,1.34,1.17,2.24,1.54.9.37,1.97.56,3.21.56,1.09,0,2.03-.14,2.82-.43.79-.29,1.44-.67,1.94-1.15.51-.48.89-1.04,1.14-1.67.25-.63.39-1.29.43-1.97l-3.2-.33c-.02.35-.08.7-.19,1.04M121.24,20.13c.53-.41,1.18-.61,1.96-.61.72,0,1.32.17,1.81.51.48.34.83.83,1.04,1.47.12.35.18.75.2,1.19l-6.43.1c.06-.34.13-.67.24-.97.26-.73.65-1.3,1.18-1.71'/><path fill='#111' d='M141.43,27.46c-.2.53-.53.96-.97,1.29-.45.33-1.06.5-1.84.5s-1.42-.19-1.97-.56c-.56-.37-.98-.92-1.28-1.65-.3-.73-.44-1.64-.44-2.74,0-.83.08-1.55.25-2.14.17-.59.41-1.09.72-1.49.31-.4.68-.69,1.1-.88.42-.19.88-.28,1.4-.28.59,0,1.11.12,1.54.36.43.24.77.59,1.01,1.06.24.46.36,1.03.36,1.7l3.17-.5c.02-1-.19-1.91-.64-2.72-.44-.82-1.11-1.47-2-1.97-.89-.5-2.02-.75-3.39-.75-1.19,0-2.22.2-3.11.6-.89.4-1.63.95-2.21,1.67-.58.71-1.02,1.54-1.32,2.47-.3.94-.44,1.95-.44,3.04s.14,2.04.43,2.95c.29.91.73,1.7,1.32,2.39.59.69,1.34,1.22,2.25,1.6.91.38,1.97.57,3.2.57,1.09,0,2.04-.15,2.85-.44.81-.3,1.47-.71,2-1.25.53-.54.92-1.16,1.17-1.86.25-.7.37-1.46.35-2.28l-3.22-.33c.02.57-.07,1.13-.28,1.65'/><path fill='#111' d='M152.8,28.75c-.57,0-1.03-.16-1.36-.47-.33-.31-.5-.83-.5-1.56v-6.75h3.67s0-2.89,0-2.89h-3.67v-3.22s-2.08,0-2.08,0l-.14,1.11c-.07.78-.28,1.36-.63,1.75-.34.39-.91.61-1.71.67h-.69s-.03,2.5-.03,2.5h1.84v7.09c0,1.67.37,2.9,1.13,3.71.75.81,1.88,1.21,3.4,1.21.37,0,.77-.03,1.2-.1.43-.07.9-.18,1.42-.35v-3.22c-.26.19-.55.32-.88.4-.33.08-.64.12-.96.12'/><path fill='#111' d='M165.92,27.46c-.11.34-.29.65-.53.92-.24.27-.55.49-.93.65-.38.17-.86.25-1.43.25-1.24,0-2.19-.4-2.85-1.21-.6-.73-.91-1.81-.96-3.2l9.79-.12c.13-1.22.08-2.32-.14-3.31-.22-.98-.6-1.83-1.14-2.54-.54-.71-1.23-1.26-2.07-1.64-.84-.38-1.82-.57-2.93-.57-1.17,0-2.19.2-3.06.61-.87.41-1.59.97-2.17,1.7-.57.72-1.01,1.56-1.29,2.52-.29.95-.43,1.98-.43,3.07s.14,2.06.43,2.96c.29.9.73,1.68,1.32,2.34.59.66,1.34,1.17,2.24,1.54.9.37,1.97.56,3.21.56,1.09,0,2.03-.14,2.82-.43.79-.29,1.44-.67,1.94-1.15.51-.48.89-1.04,1.14-1.67.25-.63.39-1.29.43-1.97l-3.2-.33c-.02.35-.08.7-.19,1.04M160.76,20.13c.53-.41,1.18-.61,1.96-.61.72,0,1.32.17,1.81.51.48.34.83.83,1.04,1.47.12.35.18.75.2,1.19l-6.43.1c.06-.34.13-.67.24-.97.26-.73.65-1.3,1.18-1.71'/><path fill='#111' d='M181.34,12.24v4.34c0,.46.02.98.07,1.54.05.57.11,1.16.19,1.78.08.62.18,1.28.29,1.99h-.36c-.19-1.15-.49-2.11-.9-2.88-.42-.77-.96-1.35-1.63-1.74-.67-.39-1.46-.58-2.39-.58-1.15,0-2.14.3-2.99.89-.84.59-1.49,1.45-1.94,2.57-.45,1.12-.68,2.49-.68,4.1,0,1.71.25,3.13.75,4.28.5,1.15,1.18,2.01,2.04,2.58.86.57,1.84.86,2.93.86.87,0,1.63-.19,2.28-.56.65-.37,1.19-.92,1.61-1.65s.75-1.64.97-2.71h.31s-.11,4.53-.11,4.53h3.09s-.03-6.14-.03-6.14l.03-13.2h-3.53ZM181.34,24.5c0,.56-.08,1.1-.24,1.64-.16.54-.39,1.03-.68,1.47-.3.44-.67.8-1.11,1.06-.45.26-.95.39-1.5.39-.69,0-1.26-.19-1.74-.58-.47-.39-.84-.94-1.1-1.64-.26-.7-.39-1.51-.39-2.42s.13-1.75.39-2.46c.26-.71.63-1.27,1.11-1.68.48-.41,1.06-.61,1.72-.61.46,0,.88.09,1.25.28.37.19.7.43.99.74.29.31.52.66.71,1.06.19.4.33.81.43,1.24.1.43.15.84.15,1.25v.28Z'/><rect fill='#111' x='193.82' y='13.24' width='3.56' height='18.34'/><path fill='#111' d='M220.64,18.41c-.39-.57-.87-1-1.43-1.29-.57-.29-1.23-.43-1.99-.43-.91,0-1.7.22-2.36.65-.67.44-1.21,1.11-1.63,2.02-.42.91-.7,2.08-.85,3.53h-.31c.02-1.37-.11-2.52-.37-3.43-.27-.92-.7-1.61-1.28-2.07-.58-.46-1.34-.69-2.26-.69s-1.65.21-2.29.64c-.64.43-1.15,1.09-1.54,2-.39.91-.67,2.09-.83,3.56h-.33s.17-5.81.17-5.81h-3.03s.03,6.67.03,6.67v7.84s3.53,0,3.53,0v-5.42c0-1.39.14-2.56.43-3.5.29-.95.67-1.66,1.15-2.14s1.04-.72,1.67-.72c.5,0,.91.15,1.24.46.32.31.57.76.74,1.36.17.6.25,1.38.25,2.32v7.64s3.45,0,3.45,0v-5.45c.02-1.33.16-2.47.43-3.4.27-.94.65-1.66,1.14-2.17.49-.51,1.06-.76,1.71-.76.5,0,.91.15,1.24.46.32.31.57.77.72,1.39.16.62.24,1.4.24,2.35v7.59s3.53,0,3.53,0v-8.01c0-1.15-.09-2.15-.28-3.02-.19-.86-.47-1.58-.86-2.15'/><path fill='#111' d='M236.76,27.61c-.02-.67-.03-1.32-.03-1.97v-2.67c0-1.39-.23-2.55-.68-3.49-.45-.94-1.13-1.63-2.02-2.1-.89-.46-1.98-.69-3.28-.69-.78,0-1.54.09-2.28.28-.74.19-1.42.48-2.03.88-.61.4-1.11.93-1.49,1.6-.38.67-.61,1.48-.68,2.45l3.17.5c.06-.72.25-1.29.57-1.71.32-.42.72-.71,1.2-.89.47-.18.96-.26,1.46-.26.8,0,1.43.19,1.9.58.47.39.71.93.71,1.61,0,.31-.09.56-.26.72-.18.17-.5.3-.96.4-.46.1-1.14.24-2.03.4-.87.13-1.69.29-2.45.49-.76.19-1.43.46-2,.81-.57.34-1.02.79-1.33,1.33-.31.55-.47,1.24-.47,2.07,0,.94.19,1.71.58,2.29.39.58.9,1.02,1.54,1.31.64.29,1.35.43,2.13.43.98,0,1.85-.21,2.61-.63.76-.42,1.38-.98,1.86-1.68.48-.7.8-1.49.97-2.36h.25v2.21s0,2.07,0,2.07h3.11c-.02-.65-.03-1.31-.04-1.97s-.02-1.33-.04-2M232.82,27.03c-.26.52-.58.95-.96,1.28-.38.33-.79.58-1.22.75-.44.17-.87.25-1.29.25-.63,0-1.13-.17-1.51-.5-.38-.33-.57-.79-.57-1.36,0-.5.13-.9.4-1.2.27-.3.62-.53,1.06-.69.43-.17.91-.3,1.43-.39.52-.09,1.03-.18,1.54-.26.51-.08.97-.2,1.39-.35.09-.03.16-.08.24-.11v.75c-.07.7-.24,1.32-.5,1.83'/><path fill='#111' d='M250.95,28.3c-.58-.22-1.16-.36-1.74-.4-.57-.05-1.04-.07-1.39-.07h-4.22c-.28,0-.53-.01-.76-.04-.23-.03-.42-.07-.56-.14-.14-.07-.21-.17-.21-.32,0-.17.12-.35.35-.54.23-.19.59-.4,1.07-.62.39.07.75.12,1.08.15.33.03.67.04,1,.04,1.28,0,2.36-.16,3.24-.49.88-.32,1.54-.78,1.99-1.36.44-.58.67-1.25.67-1.99s-.27-1.37-.81-1.88c-.54-.51-1.46-.88-2.78-1.1v-.33s4.81.64,4.81.64v-2.83s-7.23,0-7.23,0c-1.33,0-2.47.2-3.42.6-.95.4-1.67.95-2.17,1.67-.5.71-.75,1.53-.75,2.46,0,1.06.3,1.92.9,2.6.6.68,1.46,1.1,2.57,1.26v.33c-1.17.15-2,.42-2.5.81-.5.39-.75.83-.75,1.33,0,.54.26.94.79,1.21.53.27,1.29.4,2.29.4v.31c-1.3.19-2.28.54-2.93,1.06-.66.52-.99,1.19-.99,2,0,.61.21,1.14.63,1.6.42.45,1.11.81,2.07,1.06.96.25,2.25.37,3.86.37,1.8,0,3.28-.16,4.45-.49,1.17-.33,2.04-.82,2.63-1.49.58-.67.87-1.52.87-2.56,0-.93-.2-1.64-.6-2.15-.4-.51-.89-.88-1.47-1.1M243.35,20.02c.5-.48,1.18-.72,2.03-.72s1.52.24,2.02.72c.49.48.74,1.1.74,1.86s-.24,1.33-.71,1.78c-.47.45-1.14.67-1.99.67-.57,0-1.07-.1-1.5-.31-.43-.2-.75-.5-.99-.88-.23-.38-.35-.81-.35-1.29,0-.74.25-1.35.75-1.84M249.52,32.34c-.28.24-.76.42-1.46.54-.69.12-1.68.18-2.96.18-.72,0-1.35-.03-1.88-.08-.53-.05-.94-.18-1.24-.36-.3-.19-.45-.46-.45-.83s.16-.69.47-.97c.31-.28.87-.54,1.67-.78h3.59c.24,0,.51.01.81.03.3.02.59.07.88.15.29.08.52.22.71.42.19.19.28.48.28.85,0,.33-.14.62-.42.86'/><path fill='#111' d='M264.17,26.41c-.02.35-.08.7-.19,1.04-.11.34-.29.65-.53.92-.24.27-.55.49-.93.65-.38.17-.86.25-1.43.25-1.24,0-2.19-.4-2.85-1.21-.6-.73-.91-1.81-.96-3.2l9.79-.12c.13-1.22.08-2.32-.14-3.31-.22-.98-.6-1.83-1.14-2.54-.54-.71-1.23-1.26-2.07-1.64-.84-.38-1.82-.57-2.93-.57-1.17,0-2.19.2-3.06.61-.87.41-1.59.97-2.17,1.7-.57.72-1.01,1.56-1.29,2.52-.29.95-.43,1.98-.43,3.07s.14,2.06.43,2.96c.29.9.73,1.68,1.32,2.34.59.66,1.34,1.17,2.24,1.54.9.37,1.97.56,3.21.56,1.09,0,2.03-.14,2.82-.43.79-.29,1.44-.67,1.95-1.15.51-.48.89-1.04,1.14-1.67.25-.63.39-1.29.43-1.97l-3.2-.33ZM258.82,20.13c.53-.41,1.18-.61,1.96-.61.72,0,1.32.17,1.81.51.48.34.83.83,1.04,1.47.12.35.18.75.2,1.19l-6.43.1c.06-.34.13-.67.24-.97.26-.73.65-1.3,1.18-1.71'/></g><g><path fill='#111' d='M68.07,49.38v-9.25h2.02v9.25h-2.02ZM69.5,41.81v-1.68h5.27v1.68h-5.27ZM69.5,45.47v-1.51h4.61v1.51h-4.61ZM69.5,49.38v-1.68h5.27v1.68h-5.27Z'/><path fill='#111' d='M75.32,49.38l2.4-3.69-2.38-3.67h2.34l1.28,2.58h.13l1.25-2.58h2.33l-2.33,3.67,2.36,3.69h-2.36l-1.26-2.57h-.11l-1.3,2.57h-2.33Z'/><path fill='#111' d='M83.45,51.51v-9.49h1.75l-.03,2.23h.14c.1-.54.26-.99.48-1.35.21-.36.49-.63.81-.81.33-.18.71-.27,1.16-.27.59,0,1.1.15,1.53.45.43.3.76.74.99,1.31.23.57.34,1.28.34,2.11s-.12,1.55-.35,2.13c-.23.58-.56,1.02-.99,1.31-.43.29-.92.44-1.48.44-.45,0-.84-.09-1.16-.28s-.6-.46-.81-.83c-.22-.36-.37-.82-.48-1.36h-.17c.06.3.1.59.15.88s.07.57.1.85c.02.28.04.54.04.79v1.88h-2.02ZM87.08,47.91c.33,0,.6-.1.82-.29.22-.19.38-.45.49-.78s.16-.7.16-1.11-.06-.8-.17-1.13-.28-.59-.5-.78c-.22-.19-.5-.28-.81-.28-.24,0-.46.05-.66.16s-.37.26-.51.45c-.15.19-.25.42-.33.67-.07.26-.11.54-.11.83v.15c0,.23.03.45.08.66.05.21.12.4.22.57s.21.32.34.46c.14.13.29.23.46.3.17.07.35.11.53.11Z'/><path fill='#111' d='M95.11,49.58c-.65,0-1.2-.09-1.67-.28s-.85-.45-1.15-.79c-.3-.34-.52-.73-.67-1.19s-.22-.95-.22-1.49.07-1.06.22-1.54.36-.91.66-1.28.67-.66,1.11-.87.98-.32,1.58-.32,1.1.1,1.54.3c.44.2.8.49,1.07.86.28.37.46.82.57,1.32.1.51.12,1.07.04,1.69l-5.52.07v-1.12l4.09-.07-.41.63c.05-.45.02-.83-.08-1.14-.1-.31-.26-.55-.48-.71-.22-.16-.5-.24-.83-.24-.36,0-.67.1-.91.29s-.42.46-.54.81c-.12.35-.18.76-.18,1.25,0,.79.15,1.37.46,1.74.3.37.74.56,1.31.56.26,0,.48-.04.66-.11s.32-.17.43-.29c.11-.12.19-.26.24-.43.05-.16.08-.33.08-.51l1.84.2c0,.34-.07.66-.2.97-.12.31-.31.6-.56.85s-.58.45-1,.6-.91.22-1.5.22Z'/><path fill='#111' d='M99.35,49.38v-7.36h1.74l-.04,2.89h.17c.06-.74.17-1.33.34-1.78.17-.45.4-.77.68-.97.28-.2.61-.3.98-.3.13,0,.27.02.43.05.15.03.31.09.47.16l-.1,2.2c-.18-.09-.36-.16-.54-.21s-.35-.07-.5-.07c-.34,0-.62.09-.86.28-.23.19-.42.46-.55.83-.13.36-.2.8-.21,1.32v2.97h-2.02Z'/><path fill='#111' d='M107.89,49.55c-.81,0-1.42-.21-1.82-.64-.4-.43-.6-1.09-.6-1.99v-3.29h-.9v-1.4h.31c.45-.04.77-.17.97-.39s.31-.56.35-1.03l.07-.43h1.18v1.65h1.79v1.64h-1.79v3.1c0,.36.08.61.25.76.17.15.39.23.67.23.16,0,.31-.02.46-.06.15-.04.29-.1.42-.17v1.82c-.28.08-.53.14-.76.17-.22.03-.43.04-.6.04Z'/><path fill='#111' d='M113.33,49.58c-.49,0-.94-.05-1.35-.15-.42-.1-.77-.25-1.07-.46-.3-.21-.53-.47-.69-.79-.16-.32-.25-.71-.25-1.17l1.71-.29c.02.31.1.57.24.77.14.21.34.36.59.46.25.1.56.15.91.15.37,0,.68-.06.91-.18.23-.12.35-.31.35-.56,0-.17-.05-.3-.16-.39s-.28-.18-.51-.25c-.23-.07-.54-.15-.91-.24-.42-.1-.82-.21-1.18-.32-.37-.11-.69-.24-.97-.41-.28-.16-.5-.37-.65-.63s-.23-.58-.23-.96c0-.49.13-.9.39-1.25.26-.35.62-.61,1.09-.81.47-.19,1.02-.29,1.65-.29.58,0,1.11.09,1.58.26s.85.44,1.14.81c.28.37.42.85.41,1.44l-1.71.28c0-.28-.05-.52-.18-.71-.13-.2-.3-.34-.52-.44-.22-.1-.48-.15-.79-.15-.36,0-.65.07-.86.2s-.32.31-.32.53c0,.18.07.32.2.43s.32.2.57.27c.25.08.56.15.93.22.34.07.68.15,1.02.25.35.1.66.23.95.4.29.17.53.39.71.66.18.27.27.62.27,1.04,0,.46-.13.86-.39,1.21-.26.35-.63.61-1.11.79-.48.18-1.07.27-1.76.27Z'/><path fill='#111' d='M121.51,41.25c-.39,0-.69-.08-.9-.25-.21-.16-.31-.4-.31-.72s.1-.57.31-.74c.21-.16.5-.25.9-.25s.71.08.91.25c.21.17.31.41.31.73s-.1.55-.31.71-.51.25-.91.25ZM120.52,49.38v-7.36h2.02v7.36h-2.02Z'/><path fill='#111' d='M123.85,49.38v-7.36h1.71l-.04,2.85h.15c.07-.68.21-1.25.42-1.7.21-.45.48-.79.83-1.01.35-.22.78-.34,1.29-.34.82,0,1.44.28,1.86.84.42.56.62,1.42.62,2.57v4.15h-2.02v-3.91c0-.65-.1-1.14-.29-1.44-.19-.31-.49-.46-.89-.46-.34,0-.63.11-.87.34-.24.22-.43.57-.56,1.02s-.2,1.04-.2,1.74v2.72h-2.02Z'/><path fill='#111' d='M134.99,49.38v-9.25h2.02v9.25h-2.02ZM136.42,46.69v-1.63h1.93c.64,0,1.13-.13,1.46-.38.33-.26.49-.68.49-1.28,0-.55-.15-.96-.45-1.24-.3-.28-.76-.41-1.37-.41h-2.06v-1.61h2.17c.55,0,1.06.07,1.51.2s.86.33,1.19.6c.34.27.6.61.79,1.02.19.41.28.9.28,1.46,0,.71-.16,1.31-.48,1.8-.32.49-.8.86-1.42,1.11-.63.25-1.4.37-2.31.37h-1.72Z'/><path fill='#111' d='M143.3,49.38v-7.36h1.74l-.04,2.89h.17c.06-.74.17-1.33.34-1.78.17-.45.4-.77.68-.97.28-.2.61-.3.98-.3.13,0,.27.02.43.05.15.03.31.09.47.16l-.1,2.2c-.18-.09-.36-.16-.54-.21-.18-.05-.35-.07-.5-.07-.34,0-.62.09-.86.28-.23.19-.42.46-.55.83s-.2.8-.21,1.32v2.97h-2.02Z'/><path fill='#111' d='M152.13,49.58c-.71,0-1.34-.15-1.89-.43-.55-.29-.98-.72-1.29-1.29-.31-.57-.47-1.29-.47-2.14s.16-1.62.48-2.19c.32-.57.75-1,1.31-1.28.56-.28,1.18-.42,1.87-.42s1.35.14,1.9.43.98.71,1.29,1.29c.31.57.47,1.3.47,2.17s-.16,1.62-.48,2.19c-.32.57-.76.99-1.31,1.27-.55.28-1.18.41-1.88.41ZM152.19,48.06c.34,0,.62-.09.86-.26.23-.17.41-.43.53-.76.12-.34.18-.74.18-1.22,0-.51-.07-.95-.2-1.3-.13-.35-.32-.63-.57-.82-.25-.19-.55-.29-.9-.29-.33,0-.61.09-.84.27s-.41.43-.53.77c-.12.34-.18.75-.18,1.23,0,.76.14,1.34.43,1.76s.7.62,1.22.62Z'/><path fill='#111' d='M156.58,51.79c-.1,0-.21,0-.32-.02-.11-.01-.23-.04-.35-.06l-.17-1.72c.42.04.72,0,.9-.14.18-.13.27-.4.27-.81v-7.01h2.02v7.07c0,.48-.05.89-.16,1.23s-.27.63-.48.84c-.21.21-.46.37-.74.48-.29.1-.6.15-.96.15ZM157.89,41.25c-.39,0-.69-.08-.9-.25-.21-.16-.31-.4-.31-.72s.1-.57.31-.74c.21-.16.5-.25.9-.25s.71.08.91.25c.21.17.31.41.31.73s-.1.55-.31.71c-.21.17-.51.25-.91.25Z'/><path fill='#111' d='M163.67,49.58c-.64,0-1.2-.09-1.67-.28-.47-.19-.85-.45-1.15-.79-.3-.34-.52-.73-.67-1.19-.14-.46-.22-.95-.22-1.49s.07-1.06.22-1.54c.15-.49.37-.91.66-1.28.29-.37.67-.66,1.12-.87.45-.21.98-.32,1.58-.32s1.1.1,1.54.3.8.49,1.07.86.46.82.57,1.32c.1.51.12,1.07.04,1.69l-5.52.07v-1.12l4.09-.07-.41.63c.05-.45.02-.83-.08-1.14-.1-.31-.26-.55-.48-.71s-.5-.24-.83-.24c-.36,0-.67.1-.91.29-.24.19-.42.46-.54.81-.12.35-.18.76-.18,1.25,0,.79.15,1.37.46,1.74.3.37.74.56,1.31.56.26,0,.48-.04.66-.11s.32-.17.43-.29c.11-.12.19-.26.24-.43.05-.16.08-.33.08-.51l1.84.2c0,.34-.08.66-.2.97-.12.31-.31.6-.56.85-.25.25-.58.45-1,.6s-.91.22-1.5.22Z'/><path fill='#111' d='M171.37,49.58c-.64,0-1.19-.1-1.65-.29-.47-.19-.85-.46-1.16-.81s-.53-.75-.68-1.21c-.15-.46-.22-.95-.22-1.49s.07-1.05.22-1.53c.15-.48.37-.9.67-1.26.3-.37.68-.65,1.14-.86.46-.21,1.01-.31,1.63-.31.71,0,1.29.13,1.75.39s.8.6,1.02,1.02c.22.42.32.89.29,1.41l-1.79.28c0-.34-.04-.61-.15-.83s-.27-.39-.47-.5-.44-.17-.71-.17c-.24,0-.46.04-.65.13s-.36.23-.5.41c-.14.19-.25.42-.32.71-.07.29-.11.62-.11,1,0,.51.07.95.2,1.3.13.36.33.62.58.8.25.18.56.27.92.27s.65-.08.86-.25c.21-.16.36-.37.44-.63s.12-.52.1-.78l1.84.18c.02.4-.03.78-.15,1.14-.12.36-.31.68-.58.96s-.61.5-1.04.66c-.43.16-.93.24-1.51.24Z'/><path fill='#111' d='M178.29,49.55c-.81,0-1.42-.21-1.82-.64-.4-.43-.6-1.09-.6-1.99v-3.29h-.9v-1.4h.31c.45-.04.77-.17.97-.39s.31-.56.35-1.03l.07-.43h1.18v1.65h1.79v1.64h-1.79v3.1c0,.36.08.61.25.76.17.15.39.23.67.23.16,0,.31-.02.46-.06s.29-.1.42-.17v1.82c-.28.08-.53.14-.76.17s-.43.04-.6.04Z'/><path fill='#111' d='M183.91,49.58c-.64,0-1.2-.09-1.67-.28-.47-.19-.85-.45-1.15-.79-.3-.34-.52-.73-.67-1.19-.14-.46-.22-.95-.22-1.49s.07-1.06.22-1.54c.15-.49.37-.91.66-1.28.29-.37.67-.66,1.12-.87.45-.21.98-.32,1.58-.32s1.1.1,1.54.3.8.49,1.07.86.46.82.57,1.32c.1.51.12,1.07.04,1.69l-5.52.07v-1.12l4.09-.07-.41.63c.05-.45.02-.83-.08-1.14-.1-.31-.26-.55-.48-.71s-.5-.24-.83-.24c-.36,0-.67.1-.91.29-.24.19-.42.46-.54.81-.12.35-.18.76-.18,1.25,0,.79.15,1.37.46,1.74.3.37.74.56,1.31.56.26,0,.48-.04.66-.11s.32-.17.43-.29c.11-.12.19-.26.24-.43.05-.16.08-.33.08-.51l1.84.2c0,.34-.08.66-.2.97-.12.31-.31.6-.56.85-.25.25-.58.45-1,.6s-.91.22-1.5.22Z'/><path fill='#111' d='M190.85,49.58c-.55,0-1.04-.15-1.48-.44-.43-.29-.78-.73-1.03-1.31-.25-.58-.38-1.3-.38-2.17,0-.82.11-1.52.34-2.08.22-.57.55-1,.97-1.3.42-.3.93-.45,1.51-.45.45,0,.84.09,1.18.28.34.19.61.47.82.85.21.38.37.86.47,1.45h.18c-.06-.34-.11-.66-.15-.97s-.08-.61-.1-.88c-.02-.28-.04-.53-.04-.76v-2.23h2.02v9.83h-1.75l.03-2.27h-.15c-.1.54-.26,1-.48,1.37s-.48.64-.81.83-.7.27-1.14.27ZM191.53,47.94c.25,0,.48-.06.68-.17s.37-.27.5-.47c.13-.2.24-.43.32-.69.07-.26.11-.53.11-.82v-.15c0-.22-.03-.44-.08-.66-.05-.21-.12-.41-.22-.59-.09-.18-.21-.33-.34-.46-.13-.13-.28-.23-.45-.31-.17-.08-.35-.11-.53-.11-.33,0-.6.1-.82.3-.22.2-.39.47-.5.8s-.17.71-.17,1.14.06.78.18,1.11c.12.33.29.59.52.79.22.19.49.29.8.29Z'/><path fill='#111' d='M203.09,49.58c-.63,0-1.18-.07-1.66-.21-.48-.14-.89-.34-1.22-.6-.33-.26-.58-.58-.74-.97-.16-.38-.25-.82-.25-1.32l1.86-.45c0,.45.09.81.27,1.09s.43.49.76.62.68.2,1.07.2c.36,0,.66-.04.92-.13.26-.09.46-.21.6-.36.14-.15.21-.33.21-.54,0-.25-.09-.46-.28-.62-.19-.16-.44-.29-.75-.4s-.67-.21-1.06-.3c-.42-.11-.84-.23-1.25-.36-.41-.13-.79-.29-1.12-.5-.34-.21-.61-.47-.81-.79-.2-.32-.3-.73-.3-1.21,0-.58.14-1.08.43-1.49.29-.42.7-.74,1.24-.96.54-.22,1.17-.34,1.89-.34s1.37.12,1.93.36c.56.24.99.58,1.29,1.04.3.45.44,1,.4,1.65l-1.84.37c0-.29-.03-.55-.11-.77-.08-.22-.2-.41-.36-.57-.16-.15-.35-.27-.58-.35-.23-.08-.49-.12-.79-.12-.34,0-.62.05-.86.14-.23.09-.41.22-.53.37-.12.15-.18.33-.18.53,0,.25.09.45.27.6s.43.28.75.38.68.21,1.08.31c.4.09.81.21,1.21.34.41.13.79.3,1.14.51.35.21.63.49.83.83.21.34.31.77.31,1.28,0,.59-.15,1.09-.46,1.5-.31.41-.75.72-1.31.94s-1.24.32-2.01.32Z'/><path fill='#111' d='M208.9,41.25c-.39,0-.69-.08-.9-.25-.21-.16-.31-.4-.31-.72s.1-.57.31-.74c.21-.16.5-.25.9-.25s.71.08.91.25c.21.17.31.41.31.73s-.1.55-.31.71c-.21.17-.51.25-.91.25ZM207.9,49.38v-7.36h2.02v7.36h-2.02Z'/><path fill='#111' d='M214.14,51.68c-.82,0-1.48-.06-1.97-.19-.49-.13-.84-.31-1.05-.54-.21-.23-.32-.51-.32-.83,0-.41.16-.75.49-1,.33-.26.82-.43,1.47-.51v-.14c-.5,0-.89-.07-1.16-.21-.27-.14-.4-.35-.4-.63,0-.26.13-.5.38-.7.25-.21.67-.34,1.25-.39v-.17c-.54-.08-.96-.3-1.27-.64s-.46-.79-.46-1.32c0-.48.13-.9.38-1.25.25-.36.62-.64,1.1-.85.48-.21,1.07-.31,1.76-.31h3.69v1.57l-2.45-.31v.17c.7.1,1.19.28,1.46.52s.41.55.41.91-.11.69-.34.97-.56.51-1,.67c-.44.16-1,.25-1.66.25-.17,0-.34,0-.52-.03-.18-.02-.37-.05-.57-.08-.21.1-.36.2-.46.29-.1.09-.15.17-.15.25,0,.06.03.1.08.13.06.03.13.06.22.07s.2.02.32.02h2.19c.19,0,.43.01.72.04.29.02.59.09.88.21.29.12.54.31.74.57s.3.64.3,1.12c0,.53-.15.97-.44,1.32-.29.35-.74.61-1.35.78-.6.17-1.37.25-2.29.25ZM214.2,49.95c.63,0,1.1-.03,1.42-.08.32-.06.54-.13.67-.24.12-.1.18-.23.18-.38,0-.16-.04-.29-.13-.38-.08-.09-.19-.16-.32-.2-.13-.04-.25-.06-.38-.06-.13,0-.24,0-.34,0h-1.84c-.35.09-.6.2-.74.33-.14.13-.21.27-.21.43,0,.17.07.29.2.38s.33.14.58.17c.25.03.55.04.9.04ZM214.35,45.62c.38,0,.68-.1.88-.31s.31-.49.31-.84-.11-.66-.32-.88-.51-.34-.88-.34-.67.11-.89.34-.33.51-.33.87c0,.23.05.44.15.62.1.18.24.31.42.41.18.09.4.14.67.14Z'/><path fill='#111' d='M219.13,49.38v-7.36h1.71l-.04,2.85h.15c.08-.68.21-1.25.42-1.7.21-.45.48-.79.83-1.01.35-.22.78-.34,1.29-.34.82,0,1.44.28,1.86.84.42.56.62,1.42.62,2.57v4.15h-2.02v-3.91c0-.65-.1-1.14-.29-1.44s-.49-.46-.89-.46c-.34,0-.63.11-.87.34-.24.22-.43.57-.56,1.02s-.2,1.04-.2,1.74v2.72h-2.02Z'/><path fill='#111' d='M229.07,49.58c-.38,0-.74-.07-1.07-.21-.33-.14-.59-.36-.79-.66-.2-.3-.3-.69-.3-1.16,0-.44.08-.8.25-1.07.17-.28.4-.5.69-.67.29-.17.63-.31,1.02-.41.38-.1.79-.18,1.21-.25.44-.08.77-.15,1-.2.23-.05.39-.12.48-.2s.13-.2.13-.35c0-.3-.11-.54-.32-.71s-.51-.26-.88-.26c-.23,0-.46.04-.69.13-.22.08-.41.23-.56.43s-.23.47-.25.82l-1.81-.27c.04-.51.15-.94.35-1.29s.45-.62.77-.83c.32-.21.67-.36,1.06-.45.39-.09.79-.14,1.2-.14.69,0,1.27.13,1.73.38.46.25.81.62,1.04,1.11.23.49.34,1.1.34,1.82v1.32c0,.32,0,.64,0,.97,0,.33.01.66.02.98,0,.32.02.65.03.97h-1.78c0-.33,0-.66,0-1,0-.34,0-.7,0-1.07h-.14c-.08.42-.23.8-.48,1.14-.24.34-.55.62-.93.82-.38.21-.82.31-1.31.31ZM229.88,48.08c.19,0,.38-.04.58-.11s.39-.18.57-.33c.18-.15.33-.35.45-.59.12-.24.2-.53.22-.86v-.59h.35c-.1.11-.25.21-.46.28-.2.08-.42.13-.65.18-.23.04-.47.08-.71.13-.24.04-.46.1-.66.18-.2.08-.36.18-.48.32-.12.13-.18.31-.18.53,0,.27.09.48.27.63.18.15.41.22.69.22Z'/><path fill='#111' d='M237.8,51.68c-.82,0-1.48-.06-1.97-.19-.49-.13-.84-.31-1.05-.54-.21-.23-.32-.51-.32-.83,0-.41.16-.75.49-1,.33-.26.82-.43,1.47-.51v-.14c-.5,0-.89-.07-1.16-.21-.27-.14-.4-.35-.4-.63,0-.26.13-.5.38-.7.25-.21.67-.34,1.25-.39v-.17c-.54-.08-.96-.3-1.27-.64s-.46-.79-.46-1.32c0-.48.13-.9.38-1.25.25-.36.62-.64,1.1-.85.48-.21,1.07-.31,1.76-.31h3.69v1.57l-2.45-.31v.17c.7.1,1.19.28,1.46.52s.41.55.41.91-.11.69-.34.97-.56.51-1,.67c-.44.16-1,.25-1.66.25-.17,0-.34,0-.52-.03-.18-.02-.37-.05-.57-.08-.21.1-.36.2-.46.29-.1.09-.15.17-.15.25,0,.06.03.1.08.13.06.03.13.06.22.07s.2.02.32.02h2.19c.19,0,.43.01.72.04.29.02.59.09.88.21.29.12.54.31.74.57s.3.64.3,1.12c0,.53-.15.97-.44,1.32-.29.35-.74.61-1.35.78-.6.17-1.37.25-2.29.25ZM237.86,49.95c.63,0,1.1-.03,1.42-.08.32-.06.54-.13.67-.24.12-.1.18-.23.18-.38,0-.16-.04-.29-.13-.38-.08-.09-.19-.16-.32-.2-.13-.04-.25-.06-.38-.06-.13,0-.24,0-.34,0h-1.84c-.35.09-.6.2-.74.33-.14.13-.21.27-.21.43,0,.17.07.29.2.38s.33.14.58.17c.25.03.55.04.9.04ZM238.01,45.62c.38,0,.68-.1.88-.31s.31-.49.31-.84-.11-.66-.32-.88-.51-.34-.88-.34-.67.11-.89.34-.33.51-.33.87c0,.23.05.44.15.62.1.18.24.31.42.41.18.09.4.14.67.14Z'/><path fill='#111' d='M245.95,49.58c-.64,0-1.2-.09-1.67-.28-.47-.19-.85-.45-1.15-.79-.3-.34-.52-.73-.67-1.19-.14-.46-.22-.95-.22-1.49s.07-1.06.22-1.54c.15-.49.37-.91.66-1.28.29-.37.67-.66,1.12-.87.45-.21.98-.32,1.58-.32s1.1.1,1.54.3.8.49,1.07.86.46.82.57,1.32c.1.51.12,1.07.04,1.69l-5.52.07v-1.12l4.09-.07-.41.63c.05-.45.02-.83-.08-1.14-.1-.31-.26-.55-.48-.71s-.5-.24-.83-.24c-.36,0-.67.1-.91.29-.24.19-.42.46-.54.81-.12.35-.18.76-.18,1.25,0,.79.15,1.37.46,1.74.3.37.74.56,1.31.56.26,0,.48-.04.66-.11s.32-.17.43-.29c.11-.12.19-.26.24-.43.05-.16.08-.33.08-.51l1.84.2c0,.34-.08.66-.2.97-.12.31-.31.6-.56.85-.25.25-.58.45-1,.6s-.91.22-1.5.22Z'/></g></svg>"


def _item_prop(li: dict, name: str) -> str:
    want = size_list._norm_key(name)
    for p in (li.get("properties") or []):
        if isinstance(p, dict) and size_list._norm_key(p.get("name")) == want:
            return str(p.get("value") or "").strip()
    return ""


def _short_glass(v) -> str:
    """Label-friendly glass type: "Monochrome Glass - Original" prints as
    "Mono - Original", "Colour Glass - Copy" as "Colour - Copy"."""
    s = _strip_price(v)
    s = re.sub(r"\bmonochrome\b", "Mono", s, flags=re.I)
    s = re.sub(r"\s*\bglass\b", "", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip()


# Product titles that carry no information on a label: the customer's own
# artwork has no name on these, so the quoted title line is dropped.
_GENERIC_TITLES = {"create your own gobo"}


def _label_skip_item(title: str) -> bool:
    """Line items that are charges, not things to build: never on a label."""
    return size_list._norm_key(title).startswith("additional shipping charge")


def _item_glass(li: dict) -> str:
    """Glass type for the label: the Glass Type property when present, else
    derived from the SKU or variant, where the store's option sets encode it
    (e.g. SKU "Create your own gobo-Monochrome Glass-copy")."""
    v = _item_prop(li, "Glass Type")
    if v:
        return _short_glass(v)
    hay = (str(li.get("sku") or "") + " " + str(li.get("variant_title") or "")).lower()
    if "monochrome" in hay or re.search(r"\bmono\b", hay):
        fam = "Mono"
    elif "colour" in hay or "color" in hay:
        fam = "Colour"
    elif "heavy matted" in hay or re.search(r"\bhm\b", hay):
        fam = "HM"
    else:
        return ""
    if "copy" in hay:
        return fam + " - Copy"
    if "original" in hay:
        return fam + " - Original"
    return fam


def _item_model(li: dict, manufacturer: str) -> str:
    """The item's model, wherever the store's option sets put it: a plain "Model"
    property, or a per-manufacturer dropdown like "American DJ Models: Ikon
    Profile". The manufacturer's own dropdown wins over any other leftover one."""
    v = _item_prop(li, "Model")
    if v:
        return v
    nmfr = size_list._norm_key(manufacturer)
    fallback = ""
    for p in (li.get("properties") or []):
        if not isinstance(p, dict):
            continue
        name = size_list._norm_key(p.get("name"))
        val = str(p.get("value") or "").strip()
        if not val or not (name.endswith(" models") or name.endswith(" model")):
            continue
        if nmfr and name.startswith(nmfr):
            return val
        fallback = fallback or val
    return fallback


def _line_has_model(li: dict) -> bool:
    """Whether a line names the fixture it is sized for, read exactly the way
    the label reads it. Only lines that do NOT need their product type fetched,
    which keeps that fetch small however long the production queue is."""
    return bool(_strip_price(_item_model(li, _strip_price(_item_prop(li, "Manufacturer")))))


# A gobo the Quote Engine sells with a projector names no fixture of its own:
# its variant says so ("Single Colour Glass Original With Projector (Quote) /
# IH") because its fixture is the projector on the same order (#104453).
_WITH_PROJECTOR_RE = re.compile(r"\bwith projector\b", re.I)
_PROJECTOR_WATTS_RE = re.compile(r"\b(\d{1,3})\s*(?:watt|w)\b", re.I)
PROJECTOR_TYPE = "projector"


def _with_projector_variant(li: dict) -> bool:
    return bool(_WITH_PROJECTOR_RE.search(str(li.get("variant_title") or "") + " " + str(li.get("name") or "")))


def _sold_with_projector(li: dict) -> bool:
    """A With Projector gobo that is cut for the projector on its order. The old
    quote machine wrote the gobo's fixture into one "Note" property instead
    ("Manufacturer: Standard\nStandard Models: B Size"), which nothing here
    reads, and #103894's said B Size beside a 20 Watt: such a line keeps its
    CHECK rather than be cut against what it says."""
    return (_with_projector_variant(li)
            and not re.search(r"(?im)^\s*manufacturer\s*:", _item_prop(li, "Note")))


def _projector_watts(li: dict) -> int:
    """A projector line's wattage ("Projected Image 40 Watt LED Weatherproof
    Gobo Projector" is 40), or 0 for anything else. Read from what the line
    says, not its product type: the type Projector also covers rain hoods,
    lenses, holders and bundles, which name wattages too ("Rain Hood (40W &
    80W)") but never "Gobo Projector"; and the old quote machine sold projectors
    as "Outdoor Gobo Projectors" typed Custom Gobos, named in the variant."""
    if _line_has_model(li) or _with_projector_variant(li):
        return 0
    text = str(li.get("title") or "") + " " + str(li.get("variant_title") or "")
    if "gobo projector" not in text.lower():
        return 0
    m = _PROJECTOR_WATTS_RE.search(text)
    return int(m.group(1)) if m else 0


def _projector_entries(watts: int, cache: dict) -> list:
    """The size list's Projected Image rows naming this wattage ("40/80 Watt
    Range" for a 40 or an 80), rulings applied. Read from the rows rather than
    through the lookup, whose spellings are uneven here: "80 Watt" finds its
    row and "40 Watt" does not. A row is matched by its own name or by the name
    an alias gave it, so pointing "300 Watt" at a row in the size check settles
    a 300 Watt; and a row named for the wattage itself ("40 Watt", made by a
    size rule) wins over a range that includes it, so ruling it decides."""
    exact, ranged, seen = [], [], set()
    for lm, words, e in cache.get("rows") or []:
        model = str(e.get("model") or "")
        own = " ".join(words)
        if lm != "projected image" or ("watt" not in own and "watt" not in model.lower()):
            continue
        if str(watts) not in set(re.findall(r"\d+", own)) | set(re.findall(r"\d+", model)):
            continue
        is_exact = own == "%d watt" % watts
        key = (is_exact, size_list._norm_key(model), str(e.get("production_size") or ""))
        if key not in seen:
            seen.add(key)
            (exact if is_exact else ranged).append(e)
    return exact or ranged


def _projector_size(o: dict, cache: dict) -> dict:
    """What a With Projector gobo on order `o` is cut at (Cameron, 2026-10-02):
    the size of the projector on the same order. {"size", "note", "entry"} when
    every projector on the order agrees; otherwise {"reason"}, the CHECK the
    label prints, with "fix" when a size rule would settle it: the (maker,
    model) of a wattage the size list has no row for."""
    lines = [li for li in (o.get("line_items") or []) if orderbook._line_qty(li) > 0]
    # An upgrade changes which projector the customer gets ("Projector
    # Upgrade", "80 Watt to 200 Watt"): which size is for a person to say.
    if any(not _line_has_model(li) and re.search(r"\bupgrade\b", str(li.get("title") or "") + " "
                                                 + str(li.get("variant_title") or ""), re.I) for li in lines):
        return {"reason": "Sold with a projector, and this order upgrades one: check which size"}
    watts = set()
    for li in lines:
        w = _projector_watts(li)
        if not w:
            continue
        # Our rows are for our projectors. Another maker's (an Evica GP10 is
        # 22.5, not our 10 Watt's 37.5) is for a person to size.
        maker = size_list._gobo_split_maker(str(li.get("title") or ""), cache)[0]
        if maker and size_list._norm_key(maker) != "projected image":
            return {"reason": "Sold with a projector by %s: check its size" % maker}
        watts.add(w)
    watts = sorted(watts)
    if not watts:
        return {"reason": "Sold with a projector, but no projector is on this order"}
    domain = size_list._order_email_domain(o)
    sizes, entry, by_domain = set(), None, False
    for w in watts:
        # A size the size check set for this customer on the wattage itself.
        mine = size_list._gobo_domain_size("Projected Image", "%d Watt" % w, None, domain, cache=cache)
        if mine:
            sizes.add(mine)
            by_domain = True
            continue
        got = set()
        for e in _projector_entries(w, cache):
            d = size_list._gobo_domain_size(e["manufacturer"], e["model"], e, domain, cache=cache)
            by_domain = by_domain or bool(d)
            got.add(d or str(e.get("production_size") or ""))
            entry = entry or e
        if not got or "" in got:
            return {"reason": "No size list row for the %d Watt projector on this order" % w,
                    "fix": ("Projected Image", "%d Watt" % w)}
        if len(got) > 1:
            # The size list's own clash: a rule on the wattage settles it.
            return {"reason": "The size list gives the %d Watt projector two sizes" % w,
                    "fix": ("Projected Image", "%d Watt" % w)}
        sizes |= got
    names = [str(w) for w in watts]
    named = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    if len(sizes) > 1:
        return {"reason": "Sold with a projector: this order has %s Watt projectors, cut at different sizes" % named}
    if by_domain:
        note = "Size for this customer"
    else:
        note = "For the %s Watt projector%s on this order" % (named, "" if len(watts) == 1 else "s")
        if entry and entry.get("review"):
            note += ". " + entry["review"]
    return {"size": sizes.pop(), "note": note, "entry": entry}


async def _release_bg(registry: dict, order_ids: list) -> None:
    """The tail of a big print run: the same tag move and Net-30 attach the
    interactive path does, paced, off the request. A 60-order batch is ~5
    Shopify round-trips each; done inline the browser gives up long before the
    server does, rolls back its printed stamps, and the team's view and Shopify
    then disagree about which orders were released. Never raises."""
    async def once(oid) -> bool:
        try:
            seen: dict = {}
            okd, note, released = await _release_tags(registry, oid, seen)
            if not okd:
                logger.warning("background release: tag refused for order %s: %s", oid, note)
                return False
            if not released:
                return True       # already made or shipped: nothing to release
            # _net30_on_release records its own outcome on the order, so a
            # failure out here is not lost to the log: the queue row shows it.
            await _net30_on_release(registry, oid, order=seen.get("order"))
            return True
        except Exception:
            logger.exception("background release failed for order %s", oid)
            return False

    failed = []
    for oid in order_ids:
        if not await once(oid):
            failed.append(oid)
        await asyncio.sleep(0.6)
    if failed:
        await asyncio.sleep(10)      # let a throttling burst clear, then one retry round
        for oid in failed:
            if not await once(oid):
                logger.error("release still failing for order %s after a retry", oid)
            await asyncio.sleep(0.6)


async def _dispatch_move_tags(registry: dict, order_id, allow_dead: bool = False) -> tuple:
    """Move an order onto the finished tag (Complete): add it, drop the workflow
    tags (Unprocessed / IP / PC). Called while the order is still unfulfilled so
    the write is not skipped as a 'dead' order; allow_dead is for the order
    that turned out to be fulfilled already, which still has to leave To ship.
    Returns (ok, note)."""
    return await orderbook._sync_order_tags(
        registry, order_id,
        add=(desk.DISPATCHED_TAG,),
        remove=(orderbook.UNPROCESSED_TAG, PRODUCTION_TAG, orderbook.MADE_TAG), allow_dead=allow_dead)


async def _release_tags(registry: dict, order_id, seen: Optional[dict] = None) -> tuple:
    """Unprocessed -> IP for an order going to the bench: (ok, note, released).

    An order already made or shipped is left where it is, with released
    False: a reprint of a damaged label from To ship is not a release, and it
    used to put the made order back into To make beside its PC tag and run
    the Net-30 attach a second time. The stamps here are the first check; an
    order that carries PC or Complete in Shopify with no stamp is left alone
    by the sync itself."""
    oid = str(order_id)
    made = bool((_load_prod_state().get(oid) or {}).get("made_at"))
    # Fulfilled, not merely booked: a label is booked before the gobo is
    # made, and an order with a label waiting in To make is still released.
    shipped = bool((desk._load_dispatch().get(oid) or {}).get("fulfilled"))
    if made or shipped:
        return True, "", False
    out: dict = {}
    okd, note = await orderbook._sync_order_tags(registry, order_id, add=[PRODUCTION_TAG],
                                       remove=[orderbook.UNPROCESSED_TAG],
                                       unless=(orderbook.MADE_TAG, desk.DISPATCHED_TAG, *desk.LEGACY_DISPATCHED_TAGS),
                                       outcome=out)
    if seen is not None and out.get("order"):
        seen["order"] = out["order"]
    return okd, note, bool(okd and not out.get("kept"))



def _shape_label_order(o: dict, names: dict, cache: Optional[dict] = None,
                       types: Optional[dict] = None) -> dict:
    """One order in the shape the label UI prints."""
    company, person = _label_party(o)
    domain = size_list._order_email_domain(o)
    due = orderbook._order_due(o)
    cache = cache or size_list._gobo_sizes()   # one sheet snapshot for the whole order
    proposal_url, note_clean = orderbook._extract_proposal(str(o.get("note") or "").strip())
    items = []
    with_projector = None   # what a With Projector gobo is cut at, worked out once
    for li in (o.get("line_items") or []):
        if _label_skip_item(str(li.get("title") or li.get("name") or "")):
            continue
        qty = orderbook._line_qty(li)
        if qty <= 0:
            continue    # refunded or edited off the order: nothing to make
        mfr = _strip_price(_item_prop(li, "Manufacturer"))
        model = _strip_price(_item_model(li, mfr))
        # A projector or a projector accessory (a rain hood, a lens, a bundle)
        # is not cut: it prints by name, with no size and no CHECK, and uses no
        # glass (Cameron, 2026-10-02). #104453 printed its 40 Watt as a second
        # "CHECK No model specified" the bench could not tell from the gobo's.
        ptype = str((types or {}).get(li.get("product_id")) or "").strip().lower()
        projector = not mfr and not model and (ptype == PROJECTOR_TYPE or bool(_projector_watts(li)))
        sold_with = not mfr and not model and not projector and _sold_with_projector(li)
        # A model ruled not a gobo (Resolve, in the Size check) is not cut:
        # no size and no CHECK, printed by its name as a stock gobo is, with a
        # line saying why. The lookup does not read those rulings, and its
        # word-run step found a neighbouring row: Chauvet Rogue R2 Spot Metal,
        # ruled not a gobo, printed 26.5, the Rogue R2 Spot's size.
        not_gobo = projector or (bool(model) and (size_list._norm_key(mfr), size_list._norm_key(model)) in (cache.get("excludes") or set()))
        entry, reason = (None, "") if not_gobo else size_list._gobo_lookup(mfr, model, cache=cache)
        dsize = None if not_gobo else size_list._gobo_domain_size(mfr, model, entry, domain, cache=cache)
        title = str(li.get("title") or li.get("name") or "Item").strip()
        # A stock gobo IS its name. Its fixture usually arrives as free text
        # (Item Notes) or not at all, so "No model specified" put a CHECK on
        # something nobody needed to check - and a flagged row drops the name,
        # so the bench saw two CHECK rows and could not tell Electric Smoke
        # from Smoke & Mirrors. A stock gobo that DOES name its fixture (the
        # wedding gobos do) still goes through the lookup and keeps its size;
        # an unknown product type keeps the CHECK, which is the safe side.
        stock = ptype == size_list.STOCK_GOBO_TYPE
        if stock and not model:
            entry, reason, dsize = None, "", None
        size = dsize or (entry["production_size"] if (entry and not reason) else "")
        size_note = ("Not a gobo" if not_gobo else "Size for this customer" if dsize
                     else (entry["review"] if entry and entry["production_size"] and entry["review"] else ""))
        why = "" if dsize else (reason or "")
        if projector:
            # The variant says which projector or accessory ("40W with Rain
            # Hood", "B Size Glass Gobo Holder"), on the line under the name,
            # which wraps; a bare wattage only repeats the title.
            variant = str(li.get("variant_title") or "").strip()
            size, why = "", ""
            size_note = ("" if not variant or size_list._norm_key(variant) == "default title"
                         or re.fullmatch(r"\d+\s*w(att)?", variant, re.I) else variant)
        elif sold_with:
            # Cut for the projector on the same order; two projector sizes,
            # or none, is for a person to decide, and the CHECK says which.
            if with_projector is None:
                with_projector = _projector_size(o, cache)
            entry = with_projector.get("entry")
            size = with_projector.get("size") or ""
            size_note = with_projector.get("note") or ""
            why = with_projector.get("reason") or ""
        items.append({
            "title": title,
            "artwork": ("" if size_list._norm_key(title) in _GENERIC_TITLES else title),
            "quantity": qty,
            "sku": str(li.get("sku") or "").strip(),
            "options": _line_options(li, names),
            "manufacturer": mfr or (entry["manufacturer"] if entry else ""),
            "model": model,
            "glass_type": _item_glass(li),
            "price": str(li.get("price") or ""),
            "production_size": size,
            "size_note": size_note,
            "review_reason": why,
            "stock": stock,
            "not_gobo": not_gobo,
            "projector": projector,
        })
    return {
        "id": o.get("id"),
        "order_number": o.get("order_number") or str(o.get("name") or "").lstrip("#"),
        "name": o.get("name"),
        "admin_url": orderbook._admin_order_url(o.get("id")),
        "created_at": o.get("created_at"),
        "company": company,
        "customer": person,
        "display_name": company or person or "Customer",
        "is_company": bool(company),
        "status": orderbook._order_status(o),
        "due": (due.isoformat() if due else ""),
        "due_label": orderbook._fmt_due(due),
        "due_soon": bool(due and (due - clock._london_today()).days <= 2),
        "proposal_url": proposal_url,
        "note": note_clean[:500],
        "customer_id": (o.get("customer") or {}).get("id"),
        "items": items,
        # For the Dispatch flow (World Options): where it ships and a weight hint.
        "ship_to": orderbook._ship_to(o),
        "weight_hint": orderbook._order_weight_kg(o),
        "currency": o.get("currency") or o.get("presentment_currency") or "",
        # Total goods value: customs totals, declared values and insurance prefill.
        "goods_value": desk._order_goods_value(o),
        # What the customer paid for delivery, so the courier pick is not blind.
        # What they actually paid: after a free-shipping code, VAT included.
        "shipping_paid": (lambda sl: ({"title": str(sl[0].get("title") or ""),
                                       "price": "%.2f" % desk._shipping_paid(o, ex_vat=False)}
                                      if sl else None))(o.get("shipping_lines") or []),
    }


async def run_production_labels(registry: dict, tag: Optional[str] = None,
                                days: Optional[int] = None,
                                order_id: Optional[int] = None,
                                fresh: bool = False,
                                state: Optional[dict] = None,
                                dispatch: Optional[dict] = None) -> dict:
    """`state` and `dispatch` let a CALLER that is already fetching many orders
    read those two stores once instead of once per order. Printing fifty labels
    re-parsed a 324 KB and a 572 KB store fifty times each: 266 ms of blocking
    parse on the event loop for 5 ms of actual data. Left as None, every path
    behaves exactly as before and reads them fresh."""
    # Deep-link path (the admin's More actions menu): fetch ONE order by id,
    # regardless of tag or age, so the merchant can print for exactly that order.
    if order_id:
        o = await shopify._tool_json(registry, "shopify_get_order", {"order_id": int(order_id)})
        if not shopify._ok(o) or not o.get("id"):
            return {"tag": PRODUCTION_TAG, "days": 0, "count": 0, "orders": [],
                    "error_note": "Order not found.", "missing": shopify._shopify_gone(o)}
        names, types = await _product_names_and_types(
            registry, [li.get("product_id") for li in (o.get("line_items") or []) if _variant_is_real(li)],
            [li.get("product_id") for li in (o.get("line_items") or []) if not _line_has_model(li)])
        shaped = _shape_label_order(o, names, cache=size_list._gobo_sizes(), types=types)
        oid = str(shaped["id"])
        st = state if state is not None else _load_prod_state()
        dp = dispatch if dispatch is not None else desk._load_dispatch()
        return {"tag": PRODUCTION_TAG, "days": 0, "count": 1, "orders": [shaped],
                "state": {oid: st.get(oid, {})},
                "dispatch": {oid: dp.get(oid, {})},
                "single": True}

    tag = (tag or PRODUCTION_TAG).strip() or PRODUCTION_TAG
    days = max(1, min(int(days or PRODUCTION_DAYS), 730))
    fields = ("id,order_number,name,created_at,tags,email,customer,billing_address,"
              "shipping_address,line_items,note,cancelled_at,fulfillment_status,"
              "financial_status,shipping_lines,taxes_included")
    # meta carries {failed, truncated} from the pagination. Without it a sweep
    # that died on page 2 returned the pages it had and the queue rendered as
    # though the missing orders simply did not exist - a short list nobody
    # could tell was short.
    meta = {}
    orders = await orderbook._orders_snapshot(registry, days=days, fields=fields, force=fresh, meta=meta)
    want = [tag] + ([t for t in desk.LEGACY_DISPATCHED_TAGS]
                    if tag.strip().lower() == desk.DISPATCHED_TAG.strip().lower() else [])
    tagged = [o for o in orders if any(orderbook._has_tag(o, t) for t in want)]
    tagged.sort(key=lambda o: str(o.get("created_at") or ""), reverse=True)
    # The flow's three queues counted from the same snapshot (the mix's queue
    # counters, 2026-10-06), so the bench sees every queue's size at once
    # without another Shopify call.
    counts = {key: sum(1 for o in orders if orderbook._has_tag(o, qtag))
              for key, qtag in (("unprocessed", orderbook.UNPROCESSED_TAG), ("make", PRODUCTION_TAG), ("ship", orderbook.MADE_TAG))}

    # Only lines that name no fixture need their product type, so that list
    # stays small however long the queue is; a line past the cap simply keeps
    # the CHECK it had, which is the safe direction.
    names, types = await _product_names_and_types(
        registry,
        [li.get("product_id") for o in tagged for li in (o.get("line_items") or []) if _variant_is_real(li)],
        [li.get("product_id") for o in tagged for li in (o.get("line_items") or []) if not _line_has_model(li)],
    )
    sheet = size_list._gobo_sizes()   # one snapshot for the whole list
    shaped = [_shape_label_order(o, names, cache=sheet, types=types) for o in tagged]
    state = _load_prod_state()
    disp = desk._load_dispatch()
    partial = ""
    if meta.get("failed") or meta.get("truncated"):
        partial = ("Shopify did not answer for the whole window, so this list may be "
                   "missing orders. Press Refresh in a moment.")
    return {"tag": tag, "days": days, "count": len(tagged), "orders": shaped,
            "partial_note": partial, "counts": counts,
            "state": {str(s["id"]): state[str(s["id"])] for s in shaped if str(s["id"]) in state},
            "dispatch": desk._dispatch_with_live_labels(
                {str(s["id"]): disp[str(s["id"])] for s in shaped if str(s["id"]) in disp})}


# The missed-orders answer, per tag, kept until any order is known to have
# changed or two minutes pass (the 2026-10-12 speed audit, X7). Every load of
# the Make queue walked every open order in the shop for it. The app's own
# writes, Shopify's order webhooks and Refresh all move _orders_epoch; the
# two minutes catch anything that does not.
MISSING_CACHE_SECS = 120
_missing_cache: dict = {}


async def run_missing_production(registry: dict, tag: Optional[str] = None) -> dict:
    """Paid, unfulfilled, not-cancelled orders that contain gobo items but never
    got the production tag: the ones that silently never reach the workbench.
    A plain Shopify read, no AI."""
    tag = (tag or PRODUCTION_TAG).strip() or PRODUCTION_TAG
    hit = _missing_cache.get(tag)
    if hit and hit["epoch"] == orderbook._orders_epoch and time.monotonic() - hit["at"] < MISSING_CACHE_SECS:
        return hit["result"]
    # It names customers: once it can no longer be served it is not held,
    # even if the scan below fails.
    _missing_cache.pop(tag, None)
    # Taken before the scan: a change during it makes what it finds stale.
    epoch = orderbook._orders_epoch
    result = await _missing_scan(registry, tag)
    # Kept only if no order changed while it read: one that did (a click on
    # the strip, a webhook) made this answer stale before it landed.
    if not result.get("error") and epoch == orderbook._orders_epoch:
        _missing_cache[tag] = {"at": time.monotonic(), "epoch": epoch, "result": result}
    return result


async def _missing_scan(registry: dict, tag: str) -> dict:
    # Every open order, paged: one page of 100 left the rest unchecked, and
    # the oldest, the ones longest at risk of never reaching the bench, were
    # the ones past it. The page is told when the read stopped at its cap.
    fields = ("id,order_number,name,created_at,tags,cancelled_at,fulfillment_status,"
              "financial_status,line_items,customer,billing_address,shipping_address,note")
    open_orders, since_id, pages, truncated = [], 0, 0, False
    while True:
        res = await shopify._tool_json(registry, "shopify_list_orders",
                               {"status": "open", "limit": 250, "since_id": since_id, "fields": fields})
        if not shopify._ok(res):
            return {"error": "Couldn't read your orders from Shopify. Try again in a moment."}
        batch = res.get("orders") or []
        open_orders += batch
        pages += 1
        if len(batch) < 250:
            break
        since_id = max(int(o.get("id") or 0) for o in batch)
        if pages >= orderbook.ORDER_PAGE_CAP:
            truncated = True
            break
    data = {"orders": open_orders}
    store = (config.SHOPIFY_STORE or "").split(".")[0]
    missing = []
    for o in (data.get("orders") or []):
        # Skip anything anywhere in the workflow: in production (IP), made (PC),
        # or dispatched. Only orders that never entered it are "missing".
        if orderbook._has_tag(o, tag) or orderbook._has_tag(o, orderbook.MADE_TAG) or orderbook._has_tag(o, desk.DISPATCHED_TAG) \
                or any(orderbook._has_tag(o, t) for t in desk.LEGACY_DISPATCHED_TAGS) \
                or orderbook._order_status(o):
            continue
        if str(o.get("financial_status") or "").lower() not in ("paid", "partially_paid", "authorized", "partially_refunded"):
            continue
        gobo = 0
        for li in (o.get("line_items") or []):
            if _label_skip_item(str(li.get("title") or li.get("name") or "")):
                continue
            mfr = _strip_price(_item_prop(li, "Manufacturer"))
            if mfr or _item_model(li, mfr) or _with_projector_variant(li):
                gobo += 1
        if not gobo:
            continue
        company, person = _label_party(o)
        proposal_url, _note = orderbook._extract_proposal(str(o.get("note") or "").strip())
        missing.append({
            "id": o.get("id"),
            "name": str(o.get("name") or "").strip() or ("#" + str(o.get("order_number") or "")),
            "company": company or person or "",
            "proposal_url": proposal_url,
            "created_at": o.get("created_at"),
            "gobo_items": gobo,
            "admin_url": (f"https://admin.shopify.com/store/{store}/orders/{o.get('id')}" if store else ""),
        })
    missing.sort(key=lambda m: str(m.get("created_at") or ""))
    return {"tag": tag, "checked": len(data.get("orders") or []), "missing": missing[:20],
            "missing_total": len(missing), "truncated": truncated}


def _terms_flag(order_id, ok: bool, note: str = "") -> None:
    """Remember, on the order itself, that its payment terms did not attach.

    A toast is gone the moment the page moves on, and the tail of a big print
    run has no toast at all - its failures only ever reached the server log,
    where a dispatch desk never looks. The queue row reads this and shows the
    order in red until the terms are actually on it. Best-effort by design: a
    flag that cannot be saved must never break a release."""
    try:
        state = _load_prod_state()
        entry = state.get(str(order_id)) or {}
        if ok:
            if not entry.get("terms_error"):
                return                      # nothing to clear, nothing to write
            entry.pop("terms_error", None)
            entry.pop("terms_error_at", None)
        else:
            if entry.get("terms_error") == note[:200]:
                return                      # same problem as last time
            entry["terms_error"] = note[:200] or "The 30-day payment terms could not be added."
            entry["terms_error_at"] = datetime.now(timezone.utc).isoformat()
        if not entry:
            state.pop(str(order_id), None)
        else:
            state[str(order_id)] = entry
        if jsonstore._store_writable(PRODUCTION_STATE_PATH):
            _write_prod_state(state)
    except Exception:
        logger.exception("could not record the payment-terms outcome for order %s", order_id)


async def _net30_on_release(registry: dict, order_id, order: Optional[dict] = None) -> dict:
    """Start an account order's 30-day clock when it is released to production.

    Every path that moves Unprocessed -> IP is a release: the Ready-to-make
    button, the missed-orders strip, AND printing the labels (which is the
    ordinary way an order enters the workbench). Attaching terms on only one
    of them meant the normal lifecycle produced an invoice with no due date.
    Returns {"account": was this an account order, "ok": did the terms end up
    right, "note": what to tell the merchant}. A VERDICT, not prose: the
    caller used to decide success by reading the note's first words, so the
    commonest outcome of all - terms UPDATED from due-on-receipt to Net 30 -
    came out as a red failure toast because its sentence starts differently.
    Never raises: the release itself must not fail with this.

    `order` is the order the release's tag move just read, when there was
    one: its account tag and whether it is dead are what this checks, and
    moving the workflow tags changes neither, so it is not read a second
    time (the 2026-10-12 speed audit, X7)."""
    quiet = {"account": False, "ok": True, "note": ""}
    if shopify._payment_terms_writer is None:
        return quiet
    try:
        o = order if isinstance(order, dict) and order.get("id") \
            else await shopify._tool_json(registry, "shopify_get_order", {"order_id": int(order_id)})
        if not shopify._ok(o):
            # A read that FAILED is not proof the order is not on account.
            return {"account": True, "ok": False,
                    "note": "Could not check whether this order needs 30-day payment terms."}
        if not any(size_list._norm_key(t) == size_list._norm_key(orderbook.PO_UNPAID_TAG) for t in orderbook._order_tags(o)):
            return quiet
        # _sync_order_tags leaves DEAD orders alone (cancelled, refunded, already
        # fulfilled) and still answers ok, so the release carried on and put
        # 30-day terms on an order that will never be invoiced - and told the
        # merchant it had been released. Nothing was moved, so nothing is due.
        dead = orderbook._order_status(o)
        if dead:
            return {"account": True, "ok": True,
                    "note": "No payment terms added: this order is " + str(dead) + "."}
    except Exception:
        logger.exception("net30: pre-release order read failed for %s", order_id)
        return {"account": True, "ok": False,
                "note": "Could not check whether this order needs 30-day payment terms."}
    try:
        r = await shopify._payment_terms_writer(int(order_id))
    except Exception:
        logger.exception("net30: attach failed for %s", order_id)
        return {"account": True, "ok": False,
                "note": "Released, but the 30-day payment terms could not be added."}
    finally:
        # The ledger reads payment_terms; it may have landed whatever came back.
        orderbook._orders_changed([order_id])
    _terms_flag(order_id, ok=bool(r.get("ok")), note=str(r.get("detail") or ""))
    if r.get("ok"):
        # Say what actually happened to the order, not what was hoped for. The
        # old wording claimed "already on the order" whenever Shopify refused
        # the create - which it does for ANY order that already carries terms,
        # so an order on due-on-receipt reported as being on 30-day terms.
        if r.get("already"):
            note = "30-day payment terms were already on the order."
        elif r.get("updated"):
            note = ("Payment terms changed from " + str(r.get("was") or "the previous terms")
                    + " to Net 30.")
        else:
            note = "30-day payment terms added."
        return {"account": True, "ok": True, "note": note}
    if r.get("reason") == "unknown":
        # Not a failure: Shopify may have taken them. Still one to look at, so
        # the row stays marked, but in words that do not say they are missing.
        return {"account": True, "ok": False, "unknown": True,
                "note": ("Released. Shopify did not answer about the 30-day payment terms and "
                         "the check afterwards failed too, so it is not known whether they are "
                         "on the order: look at it in Shopify before adding them again.")}
    return {"account": True, "ok": False,
            "note": ("Released, but the 30-day payment terms could not be added: "
                     + str(r.get("detail") or "unknown error"))}


async def run_label_coverage(registry: dict, orders_count: int = 200) -> dict:
    """Do recent orders' gobo items resolve to a production size? The last N orders
    (any status, newest first), every Model run through the exact lookup the labels
    print with, failures grouped by model + reason. A plain Shopify read, no AI."""
    n = max(1, min(int(orders_count or 200), 250))
    data = await shopify._tool_json(registry, "shopify_list_orders",
                            {"status": "any", "limit": n,
                             "fields": "id,order_number,name,created_at,email,customer,line_items"})
    if not shopify._ok(data):
        # A throttled or failed fetch must never read as "everything matches".
        return {"error": "Couldn't read your orders from Shopify. Try again in a moment."}
    orders = (data.get("orders") or [])[:n]
    sheet = size_list._gobo_sizes()   # one snapshot for the whole scan
    items_seen = gobo_items = sized = no_model = ruled_out = 0
    flagged: dict = {}
    def flag(o, oname, mfr, model, reason, order_problem=False):
        f = flagged.setdefault((mfr, model, reason), {"manufacturer": mfr, "model": model or "(blank)",
                                                      "reason": reason, "count": 0, "orders": []})
        if order_problem:
            # Not a gap in the size list: the order itself has to be looked at,
            # so the page offers no size rule for it.
            f["order_problem"] = True
        f["count"] += 1
        if oname not in [x["name"] for x in f["orders"]] and len(f["orders"]) < 3:
            f["orders"].append({"name": oname, "admin_url": orderbook._admin_order_url(o.get("id"))})

    for o in orders:
        oname = str(o.get("name") or "").strip() or ("#" + str(o.get("order_number") or ""))
        domain = size_list._order_email_domain(o)
        with_projector = None
        for li in (o.get("line_items") or []):
            items_seen += 1
            mfr = _strip_price(_item_prop(li, "Manufacturer"))
            model = _strip_price(_item_model(li, mfr))
            if not model and not mfr and _sold_with_projector(li):
                # A gobo sold with a projector names no fixture but is a gobo,
                # sized by the projector on its order exactly as its label is.
                gobo_items += 1
                if with_projector is None:
                    with_projector = _projector_size(o, sheet)
                if with_projector.get("size"):
                    sized += 1
                else:
                    fix = with_projector.get("fix")
                    flag(o, oname, *(fix or ("", "Sold with a projector")), with_projector["reason"],
                         order_problem=not fix)
                continue
            if not model and not mfr:
                # No gobo options at all: an accessory or plain product, not a miss.
                no_model += 1
                continue
            if (size_list._norm_key(mfr), size_list._norm_key(model)) in (sheet.get("excludes") or set()):
                # The merchant has ruled this is not a gobo. Counted apart from
                # both the sized and the flagged: it is not being made, and it is
                # not a gap in the list either.
                ruled_out += 1
                continue
            gobo_items += 1
            entry, reason = size_list._gobo_lookup(mfr, model, cache=sheet)
            if reason and size_list._gobo_domain_size(mfr, model, entry, domain, cache=sheet):
                reason = None
            if not reason:
                sized += 1
                continue
            flag(o, oname, mfr, model, reason)
    rows = sorted(flagged.values(), key=lambda r: -r["count"])[:100]
    return {"orders_scanned": len(orders), "items_seen": items_seen,
            "gobo_items": gobo_items, "sized": sized,
            "flagged_items": gobo_items - sized, "skipped_no_model": no_model,
            "ruled_out": ruled_out,
            "pct": (round(sized * 100.0 / gobo_items, 1) if gobo_items else 100.0),
            "flagged": rows}


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as sibling.NAME, never a copied name.
from gizmo import orderbook  # noqa: E402
from gizmo import shopify  # noqa: E402
from gizmo import size_list  # noqa: E402
from gizmo import dispatch as desk  # noqa: E402
from gizmo import config  # noqa: E402
from gizmo import clock  # noqa: E402
