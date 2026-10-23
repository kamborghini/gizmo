"""The stock link: the glass a Mark made consumes, booked at the stock sheet;
the day's usage sheet; the glass catalogue; and the retry queue that keeps a
booking the stock sheet could not take. Moved out of copilot.py with the
stock move (the stock area holds it now); its routes (the day sheet) are in
gizmo/routes/stock_link.py. Read as `stock_link.NAME`.
"""
import logging
import os
import re
import time
import asyncio
from datetime import datetime, timedelta, timezone
import httpx
from gizmo.config import _env_num
from gizmo import store as jsonstore
from gizmo import errors
from gizmo.dispatch import _load_dispatch
from gizmo import production, size_list
from gizmo.production import _load_prod_state, run_production_labels
from gizmo import crm as salesdesk

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")




# ---------------------------------------------------------------------------
# Stock bridge: the glass a Mark made consumes flows into the stock app.
#
# Zeta (the stock app) is the shelf's ledger; this desk is where the shelf
# actually empties. Marking an order made resolves its items into glass lines
# (the same resolution the day sheet uses) and pushes them to zeta, which
# books them exactly like a count-down: stock falls, usage rises, the reorder
# engine sees it. Un-marking pushes a reversal. Zeta is idempotent per order,
# so a repeat or a retry can never double-book.
#
# The push must never hold the workbench hostage: Mark made succeeds locally
# first, and a failed push (zeta down, network blip) parks the order id in a
# pending store on the volume that the scheduler retries every tick.
# ---------------------------------------------------------------------------
ZETA_URL = os.environ.get("ZETA_URL", "").strip().rstrip("/")
ZETA_SYNC_TOKEN = os.environ.get("ZETA_SYNC_TOKEN", "").strip()
ZETA_SYNC_PATH = os.environ.get("ZETA_SYNC_PATH", "/data/zeta_sync.json")
ZETA_DRAIN_MAX = _env_num(int, os.environ.get("ZETA_DRAIN_MAX", "40"), "40", "ZETA_DRAIN_MAX")        # retries per tick
ZETA_DRAIN_SECONDS = _env_num(float, os.environ.get("ZETA_DRAIN_SECONDS", "45"), "45", "ZETA_DRAIN_SECONDS")  # and its deadline
ZETA_MAX_TRIES = _env_num(int, os.environ.get("ZETA_MAX_TRIES", "20"), "20", "ZETA_MAX_TRIES")        # then park for a human
_zeta_last = {"ok_at": 0.0, "error": ""}


def _zeta_configured() -> bool:
    """The link has somewhere to book: the stock app, or (once the stock
    sheet has moved in) Reactor's own stock sheet."""
    return bool(ZETA_URL and ZETA_SYNC_TOKEN) or stock.is_live()


def _load_zeta_pending() -> dict:
    return jsonstore._load_json_store(ZETA_SYNC_PATH, "pending", {}) or {}


_zeta_locks: dict = {}


def _zeta_lock(order_id) -> "asyncio.Lock":
    """One lock per order: a drain retry and a fresh click for the same order
    must serialise, or an in-flight stale booking could land after a newer
    reversal and leave the stock app holding glass for an un-made order."""
    key = str(order_id)
    lock = _zeta_locks.get(key)
    if lock is None:
        if len(_zeta_locks) > 500:
            for k in [k for k, l in _zeta_locks.items() if not l.locked()][:250]:
                _zeta_locks.pop(k, None)
        lock = _zeta_locks[key] = asyncio.Lock()
    return lock


def _write_zeta_pending(p: dict) -> bool:
    """True when the queue actually reached disk. The caller's wording depends
    on it: promising "the app will keep retrying" over a write that silently
    failed would turn a lost booking into a reassuring toast."""
    try:
        if not jsonstore._store_writable(ZETA_SYNC_PATH):
            return False
        jsonstore._write_json_store(ZETA_SYNC_PATH, "pending", p)
        return True
    except Exception:
        logger.exception("stock bridge: could not save the pending queue")
        return False


_ZETA_LINE_KEYS = ("size", "family", "qty", "note")


def _zeta_lines(lines: list) -> list:
    """Usage lines in the stock app's own contract and nothing more. The lines
    carry fields for this app's screens (which rows are stock gobos, by name);
    an external endpoint that validates strictly would refuse a push over one
    extra key, and a refused push parks the order for retry indefinitely."""
    return [{k: ln[k] for k in _ZETA_LINE_KEYS if k in ln} for ln in lines]


async def _zeta_send(op: str, order_id, order_name: str, lines: list) -> dict:
    """One push to zeta. Separate so tests can stand in a fake transport."""
    async with httpx.AsyncClient(timeout=10.0) as cl:
        r = await cl.post(ZETA_URL + "/api/sync/consumption",
                          headers={"Authorization": "Bearer " + ZETA_SYNC_TOKEN},
                          json={"op": op, "order_id": str(order_id),
                                "order_name": order_name, "lines": lines})
        r.raise_for_status()
        return r.json()


USAGE_SHEETS_PATH = os.environ.get("USAGE_SHEETS_PATH", "/data/usage_sheets.json")


async def _zeta_send_sheet(payload: dict) -> dict:
    """One usage sheet to zeta. Separate so tests can stand in a fake."""
    async with httpx.AsyncClient(timeout=20.0) as cl:
        r = await cl.post(ZETA_URL + "/api/sync/usage-sheet",
                          headers={"Authorization": "Bearer " + ZETA_SYNC_TOKEN},
                          json=payload)
        r.raise_for_status()
        return r.json()


async def _zeta_push(registry: dict, order_id, op: str, who=None) -> str:
    """Book or reverse one order at the stock sheet (Reactor's own once it
    has moved in, else the stock app). Returns '' on success or a short note
    for the operator; failure always parks the order for retry, with the
    account that asked, so the retry is recorded under them."""
    if not _zeta_configured():
        return ""
    async with _zeta_lock(order_id):
        return await _zeta_push_locked(registry, order_id, op, who)


async def _deliver(op: str, order_id, order_name: str, lines: list, who=None) -> None:
    """In Reactor once the stock sheet has moved in; at the stock app before."""
    if stock.is_live():
        if op == "book":
            await asyncio.to_thread(stock_bridge.book, who, str(order_id), order_name, lines)
        else:
            await asyncio.to_thread(stock_bridge.reverse, who, str(order_id))
        return
    await _zeta_send(op, order_id, order_name, lines)


async def _zeta_push_locked(registry: dict, order_id, op: str, who=None) -> str:
    try:
        if op == "book":
            res = await run_production_labels(registry, order_id=int(order_id))
            orders = (res or {}).get("orders") or []
            if not orders:
                raise RuntimeError("order could not be read")
            o = orders[0]
            await _deliver("book", order_id, str(o.get("name") or ""), _zeta_lines(_usage_lines(o)), who)
        else:
            await _deliver("reverse", order_id, "", [], who)
        # The queue is reloaded AT write time, never carried across the await:
        # a concurrent push's outcome must not be overwritten by this one's
        # stale snapshot of the queue.
        pending = _load_zeta_pending()
        pending.pop(str(order_id), None)
        _write_zeta_pending(pending)
        _zeta_last["ok_at"], _zeta_last["error"] = time.time(), ""
        return ""
    except Exception as e:
        # The op recorded is the LATEST intent: made-then-unmade while zeta is
        # down must end as a reverse, not replay a stale book.
        pending = _load_zeta_pending()
        pending[str(order_id)] = {"op": op, "at": salesdesk._crm_now(), "by": who,
                                  "tries": int((pending.get(str(order_id)) or {}).get("tries") or 0) + 1}
        parked = _write_zeta_pending(pending)
        _zeta_last["error"] = f"{type(e).__name__}: {e}"[:200]
        logger.warning("stock bridge: %s for order %s failed (%s); %s",
                       op, order_id, type(e).__name__,
                       "queued for retry" if parked else "AND THE QUEUE COULD NOT BE SAVED")
        where = "The stock sheet" if stock.is_live() else "The stock app"
        if not parked:
            errors._record_error("booking made glass at the stock sheet", e)
            return (f"{where} was not updated AND the retry could not be saved. "
                    "Adjust this order's stock by hand, or press Mark made again later.")
        return f"{where} could not be updated just now; the app will keep retrying."


def _zeta_catalog_combos() -> list:
    """Every consumption line this app can produce. Sheet sizes pass through
    the bezel rule first: an 86 or 100 order sends 64.9 glass plus a ring, so
    the catalogue lists those lines, never 86 glass that will not exist."""
    sheet = sorted({str(e.get("production_size") or "").strip()
                    for entries in (size_list._gobo_sizes().get("by_model") or {}).values()
                    for e in entries if str(e.get("production_size") or "").strip()},
                   key=lambda v: (float(v) if v.replace(".", "", 1).isdigit() else 9999))
    glass, rings = [], []
    for sz in sheet:
        cut = _BEZEL_UP.get(sz)
        if cut:
            rings.append(sz)
            if cut not in glass and cut not in sheet:
                glass.append(cut)
        else:
            glass.append(sz)
    combos = [{"family": fam, "size": sz} for sz in glass for fam in ("Mono", "HM", "Colour")]
    combos += [{"family": "Ring", "size": sz} for sz in rings]
    return combos


async def _zeta_send_catalog() -> None:
    """Publish the catalogue so the stock app's mapping view shows the whole
    translation rather than only the lines that have already parked. Once
    the stock sheet has moved in, its mapping reads the catalogue itself."""
    if stock.is_live():
        return
    combos = _zeta_catalog_combos()
    async with httpx.AsyncClient(timeout=10.0) as cl:
        r = await cl.post(ZETA_URL + "/api/sync/catalog",
                          headers={"Authorization": "Bearer " + ZETA_SYNC_TOKEN},
                          json={"combos": combos[:500]})
        r.raise_for_status()


async def _zeta_drain(registry: dict) -> None:
    """Retry everything parked, once per scheduler tick. Never raises.

    The op is re-read from the store under the order's lock, never taken from
    this loop's snapshot: while one retry was in flight the merchant may have
    changed their mind, and the LATEST intent is the only one that may run."""
    if not _zeta_configured():
        return
    # Capped and deadlined. Each retry is a full Shopify order read plus a
    # POST, so an unbounded backlog monopolised the hourly tick and starved
    # every other scheduled job behind it.
    started = time.monotonic()
    for oid in list(_load_zeta_pending().keys())[:ZETA_DRAIN_MAX]:
        if time.monotonic() - started > ZETA_DRAIN_SECONDS:
            logger.info("stock bridge: drain hit its deadline; the rest waits for the next tick")
            break
        try:
            async with _zeta_lock(oid):
                entry = _load_zeta_pending().get(str(oid))
                if not entry:
                    continue   # settled by a fresh click while we waited
                # An entry that has failed this many times is not going to
                # settle by being retried forever. Park it as needing a human
                # and stop spending the tick on it - it stays in the store, so
                # nothing is lost and Settings can still show it.
                pend = _load_zeta_pending()
                cur = pend.get(str(oid)) or entry
                tries = int(cur.get("tries") or 0)
                if tries >= ZETA_MAX_TRIES:
                    if not cur.get("stuck"):
                        cur["stuck"] = True
                        pend[str(oid)] = cur
                        _write_zeta_pending(pend)
                        logger.error("stock bridge: %s parked after %d attempts", oid, tries)
                    continue
                # A failed attempt is counted once, by _zeta_push_locked. The
                # drain counted it too, so every tick was two tries and an
                # order was parked for a human after ten attempts, not twenty.
                await _zeta_push_locked(registry, oid, str(entry.get("op") or "book"), entry.get("by"))
        except Exception:
            logger.exception("stock bridge: drain failed for %s", oid)


# An 86mm or 100mm gobo is not cut from 86 or 100 glass: it is a 64.9mm blank
# bezelled up to the ordered diameter by a ring. The usage lines must say what
# the bench actually consumes, or the stock sheet drifts one ring and one
# mis-sized blank at a time.
_BEZEL_UP = {"86": "64.9", "100": "64.9"}   # ordered size -> the glass it is cut from


def _usage_lines(shaped_order: dict) -> list:
    """One shaped label order as consumption lines.

    Resolvable items become {size, family, qty}; a bezelled size becomes TWO
    lines, the glass blank it is cut from plus the ring that brings it up to
    the ordered diameter. Anything the size lookup flagged for review, or that
    carries no size, becomes {size, family, qty, note} so the caller can show
    it rather than silently dropping glass. The same resolution feeds the day
    sheet and the stock-app push, so the two can never disagree about what a
    day's making consumed."""
    out = []
    for it in shaped_order.get("items", []):
        # Ruled not a gobo: nothing is cut, so no glass is used and there is
        # nothing to resolve. Not a line of any kind, here or in the stock app.
        if it.get("not_gobo"):
            continue
        qty = int(it.get("quantity") or 1)
        # Original vs Copy is the same physical blank: group stock by the
        # glass family ("Mono - Original" and "Mono - Copy" -> "Mono").
        family = re.split(r"\s+-\s+", it.get("glass_type") or "")[0].strip() or "(type not recorded)"
        if it.get("stock") and not it.get("production_size") and not it.get("review_reason"):
            # Named, not sized, and not a problem: carried by name rather than
            # as "no size resolved". The stock app gets the row shape it has
            # always had (see _zeta_lines); the name travels in the note.
            name = str(it.get("title") or "stock gobo")[:160]
            out.append({"size": "", "family": family, "qty": qty,
                        "note": ("stock gobo: " + name)[:200], "stock": name})
            continue
        if it.get("review_reason") or not it.get("production_size"):
            out.append({"size": str(it.get("production_size") or ""), "family": family,
                        "qty": qty, "note": str(it.get("review_reason") or "no size resolved")[:200]})
            continue
        size = str(it["production_size"])
        glass = _BEZEL_UP.get(size)
        if glass:
            out.append({"size": glass, "family": family, "qty": qty})
            out.append({"size": size, "family": "Ring", "qty": qty})
        else:
            out.append({"size": size, "family": family, "qty": qty})
    return out


def _usage_row_order(r: dict) -> tuple:
    """Largest glass first, then by family; a size that is not a number (a
    sheet cell edited to "TBC") goes last instead of taking the whole day
    sheet down with it, which one float() of it used to do."""
    try:
        return (0, -float(r["size"]), str(r["glass"]))
    except (TypeError, ValueError):
        return (1, 0.0, str(r.get("size") or ""), str(r.get("glass") or ""))


async def run_stock_usage(registry: dict, date_str: str) -> dict:
    """Estimated stock used on one day: every order whose Mark made stamp falls
    inside the selected day (UK time), its items resolved through the same size
    lookup the labels print with, summed by glass size + type. Items that don't
    resolve are listed separately, never silently dropped. No AI."""
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Europe/London")
    try:
        day = datetime.strptime(str(date_str or ""), "%Y-%m-%d").date()
    except ValueError:
        return {"error": "Pick a valid date."}
    start = datetime.combine(day, datetime.min.time(), tzinfo=tz)
    end = start + timedelta(days=1)
    # Live state plus the archive of evicted made stamps, so a past day still
    # sees orders that fell out of the capped live state.
    stamps = {oid: e.get("made_at") for oid, e in _load_prod_state().items() if e.get("made_at")}
    for oid, ma in production._archived_made(set()).items():
        stamps.setdefault(oid, ma)
    made_ids = []
    for oid, raw in stamps.items():
        try:
            made = datetime.fromisoformat(raw)
            if made.tzinfo is None:
                made = made.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        if start <= made.astimezone(tz) < end:
            made_ids.append(int(oid))
    made_ids = made_ids[:150]
    st_once, dp_once = _load_prod_state(), _load_dispatch()
    fetched = await asyncio.gather(*[run_production_labels(registry, order_id=i,
                                                           state=st_once, dispatch=dp_once)
                                     for i in made_ids], return_exceptions=True)
    rows: dict = {}
    unresolved: dict = {}
    stock: dict = {}
    orders_in, pieces, fetch_failed, unread, gone = [], 0, 0, [], []
    for oid, res in zip(made_ids, fetched):
        if isinstance(res, dict) and res.get("missing"):
            # Shopify no longer has it (a deleted test order). Asking again
            # will not bring it back, so it is left out of the sheet rather
            # than holding the day's sheet for good; its own booking stands.
            gone.append(oid)
            continue
        if not isinstance(res, dict) or not res.get("orders"):
            fetch_failed += 1   # a made order whose fetch was throttled/failed
            unread.append(oid)
            continue
        for o in (res.get("orders") or []):
            orders_in.append(str(o.get("name") or ""))
            for line in _usage_lines(o):
                pieces += line["qty"]
                if line.get("stock"):
                    stock[line["stock"]] = stock.get(line["stock"], 0) + line["qty"]
                    continue
                if line.get("note"):
                    nm = str(o.get("name") or "")
                    unresolved[nm] = unresolved.get(nm, 0) + line["qty"]
                    continue
                key = (line["size"], line["family"])
                r = rows.setdefault(key, {"size": line["size"], "glass": line["family"], "qty": 0})
                r["qty"] += line["qty"]
    out_rows = sorted(rows.values(), key=_usage_row_order)
    return {"date": day.isoformat(), "orders": len(orders_in), "order_names": orders_in[:60],
            "order_ids": [i for i in made_ids if i not in gone], "pieces": pieces, "rows": out_rows,
            "fetch_failed": fetch_failed, "unread_ids": unread, "gone_ids": gone,
            "unresolved": [{"name": k, "qty": v} for k, v in sorted(unresolved.items())],
            "stock": [{"name": k, "qty": v} for k, v in sorted(stock.items())]}


async def _send_sheet(payload: dict, who=None) -> dict:
    """The day's sheet: applied in Reactor once the stock sheet has moved
    in, sent to the stock app before."""
    if stock.is_live():
        return await asyncio.to_thread(stock_bridge.usage_sheet, who, payload["day"], payload["order_ids"],
                                       payload["lines"])
    return await _zeta_send_sheet(payload)


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as sibling.NAME, never a copied name.
from gizmo import stock  # noqa: E402
from gizmo import stock_bridge  # noqa: E402
