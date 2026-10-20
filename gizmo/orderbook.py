"""The order book: the sweep of recent orders and its cache, the epochs that
say an order changed, the webhook bookkeeping, reading an order (its tags,
status, due date, country, address, lines and weight), tagging under a lock
per order, the per-order dispatch lock, order edits and address checks, the
shop's own record and origin, and fulfilment and its undoing.

Moved out of copilot.py (stage 4 of the 14 October audit). Read as
`orderbook.NAME` (`orders` is a local name in 25 places).
"""
import logging
from typing import Optional
import os
import re
import time
import asyncio
from datetime import datetime, timedelta, timezone
import httpx
try:
    import worldoptions
except Exception:                     # keep the app booting if the connector is unavailable
    worldoptions = None
from gizmo.config import _env_num

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


ORDER_PAGE_CAP = _env_num(int, os.environ.get("ORDER_PAGE_CAP", "30"), "30", "ORDER_PAGE_CAP")


# ---------------------------------------------------------------------------
# Order sweep snapshot
#
# Sweeping the store is the most expensive read this app makes: up to 30 pages
# of 250 orders, chained by since_id so they cannot run in parallel. The
# production queue reruns it on every flip between To make / To ship /
# Complete, and all three tabs ask for the SAME window and fields, differing
# only in a local tag filter. One snapshot therefore serves all three, and a
# tab flip drops from ~30 sequential Shopify calls to none.
#
# Freshness rests on three mechanisms because they cover different mutations:
#   - every write THIS app makes to an order, and Shopify's order webhook,
#     names the order (_orders_changed): each snapshot keeps the rest of the
#     store and reads that order again, by id, before it answers anyone. Each
#     used to retire every snapshot, so one Production Manager action cost two
#     full sweeps (the 2026-10-12 speed audit, X1);
#   - Refresh, and a change nobody can name, still retire every snapshot at
#     once (_bust_orders), as everything did before;
#   - a short TTL bounds how long a change Shopify never told us about can stay
#     invisible: webhooks are at-least-once and occasionally late or lost.
#
# Two things are deliberately NOT cached. A failed sweep, because "nothing
# owed" must never be an artefact of a throttled fetch. And the shaped label
# payload, because production state, dispatch state and the gobo size sheet all
# change it without touching Shopify; those are cheap local reads and stay live.
# ---------------------------------------------------------------------------
# How long a swept order list may be reused. Every queue segment needs the SAME
# sweep, so at 45 seconds a merchant who read one screen before clicking the
# next paid the whole 8-page fan-out again. Correctness does not rest on the
# TTL: an order webhook or a write by the app names its order, which every
# snapshot reads again before it answers (_orders_changed), and Refresh retires
# them all (_bust_orders), so a real change is never waited out.
ORDER_CACHE_SECS = _env_num(int, os.environ.get("ORDER_CACHE_SECS", "180"), "180", "ORDER_CACHE_SECS")
# Distinct (days, fields) sweeps kept. There are about seven in the codebase,
# so with a longer TTL this became the binding constraint rather than the
# clock: at 6, an Overview or Margins run could evict the production queue's
# entry and make the next click cold again.
ORDER_CACHE_MAX  = 8
_orders_cache: dict = {}      # (days, fields) -> {"at", "orders", "meta", "pending"}
_orders_inflight: dict = {}   # (days, fields) -> the Task sweeping, so concurrent misses share one fetch
_orders_refreshing: dict = {}  # (days, fields) -> the Task reading its pending orders again, by id
_orders_flight: dict = {}     # (days, fields) -> ids that changed while that key's sweep was in flight
_orders_epoch = 0             # bumped by every change, named (_orders_changed) or not (_bust_orders)
_orders_full_epoch = 0        # bumped only by _bust_orders: what retires every snapshot
# More changed orders than this at once and one sweep is cheaper than reading
# them again one by one (Shopify's ids filter takes at most 250 a page).
ORDER_REFRESH_MAX = 50


# ---------------------------------------------------------------------------
# Webhooks: how the desk stays live.
#
# Without these the app is blind between reads: the order snapshot has a 45s
# TTL, and an edit made in the Shopify admin (a payment landing, a tag changed,
# a refund) stays invisible until the clock runs out. Shopify POSTs order
# events here instead; each verified event names its order, which every
# snapshot reads again from Shopify before it answers, so the next read of any
# tab reflects reality within seconds. The TTL stays as the backstop, because
# webhooks are at-least-once, unordered and occasionally late; the payload only
# says which order to read again and is never used as state.
# ---------------------------------------------------------------------------
WEBHOOK_MAX_BYTES = 1024 * 1024        # a full order payload, with headroom
# version: the Shopify version the last event was sent in, from its own header.
# The subscriptions keep the version they were made with, which nothing else
# here shows, and an old one silently moves forward when Shopify retires it.
_webhook_state = {"last_at": 0.0, "last_topic": "", "count": 0, "ensured": None, "version": ""}
_webhook_seen: dict = {}               # delivery id -> monotonic time (dedupe)


def _webhook_note_delivery(delivery_id: str) -> bool:
    """True if this delivery is new. Shopify redelivers on any slow response,
    so the same event arriving twice must not read as two events."""
    now = time.monotonic()
    if len(_webhook_seen) > 500:
        cutoff = now - 600
        for k in [k for k, t in _webhook_seen.items() if t < cutoff]:
            _webhook_seen.pop(k, None)
    if delivery_id in _webhook_seen:
        return False
    _webhook_seen[delivery_id] = now
    return True


def _refresh_asked(body: dict) -> bool:
    """True when the merchant pressed Refresh, having discarded the snapshots.

    Refresh has to mean Shopify is re-read: the reports it sits on are the ones
    a merchant checks straight after editing something in the admin, and there
    are no webhooks to tell us about that edit. It clears every window rather
    than just this report's, which costs one extra sweep on whatever is opened
    next and is still no worse than the old behaviour of always sweeping."""
    if not isinstance(body, dict) or not body.get("fresh"):
        return False
    _bust_orders()
    return True


def _bust_orders() -> None:
    """Retire every cached order sweep, finished or still running.

    Called straight after each write this app makes to order tags or fulfilment
    status, which are exactly the fields the queues filter on, and when the
    merchant presses Refresh. Bumping the epoch stops a sweep already in flight
    from storing its result, since that result was taken before the write.

    Clearing _orders_inflight matters just as much: a sweep of two years of
    orders takes long enough that a merchant can edit something in Shopify and
    press Refresh while it is still running. Left joinable, that sweep would
    answer the Refresh with the picture from before their edit, which on the
    liability ledger means chasing an invoice that has just been paid. Anyone
    already awaiting it keeps their own reference and still gets an answer; it
    simply stops being the answer for callers that arrive after the write.

    Still the blunt instrument, deliberately: Refresh, and any change nobody
    can name (an order event whose body cannot be read). Where the app knows
    WHICH order changed it says so with _orders_changed, which keeps the
    snapshots and reads that order again instead (the 2026-10-12 speed audit,
    X1: one Production Manager action used to cost two full sweeps)."""
    global _orders_epoch, _orders_full_epoch
    _orders_epoch += 1
    _orders_full_epoch += 1
    _orders_cache.clear()
    _orders_inflight.clear()
    _orders_refreshing.clear()
    _orders_flight.clear()


def _orders_changed(order_ids) -> None:
    """These orders changed: a write this app has just made to them, or
    Shopify's webhook saying so. Every snapshot is kept, and each of these
    orders is read again from Shopify, by id, before any snapshot is used
    again (_orders_snapshot), so no answer can carry the order as it was.

    That holds for a sweep still in flight too: the ids are recorded against
    it, so its result is kept and then put right rather than thrown away, and
    a caller who joins it after the change is answered with the order as it
    is now. Ids that cannot be read as order ids fall back to _bust_orders."""
    ids = set()
    for i in order_ids or ():
        try:
            ids.add(int(i))
        except (TypeError, ValueError, OverflowError):
            pass
    if not ids or ORDER_CACHE_SECS <= 0:
        # Nothing cached to put right (the cache switched off): detach any
        # sweep in flight, exactly as every change used to.
        _bust_orders()
        return
    global _orders_epoch
    _orders_epoch += 1
    for entry in _orders_cache.values():
        entry["pending"].update(ids)
    for flight in _orders_flight.values():
        flight.update(ids)


async def _sweep_orders(registry: dict, days: int, fields: str, key) -> tuple:
    """One shared sweep: fetches, stores if it is worth storing, and returns
    (orders, meta, ids named as changed while it ran) to every caller waiting
    on it."""
    full_epoch = _orders_full_epoch    # retired by _bust_orders, or not
    flight: set = set()                # orders named as changed while this runs
    _orders_flight[key] = flight
    meta: dict = {}
    try:
        orders = await _paginate_orders(registry, days=days, fields=fields, meta=meta)
        # Store only a complete sweep not retired meanwhile: "nothing owed"
        # must never be a cached artefact of a throttled fetch. Orders named
        # as changed while it ran are stored as pending, to be read again.
        if ORDER_CACHE_SECS > 0 and not meta.get("failed") and _orders_full_epoch == full_epoch:
            _orders_cache[key] = {"at": time.monotonic(), "orders": orders,
                                  "meta": dict(meta), "pending": set(flight), "reading": set()}
            while len(_orders_cache) > ORDER_CACHE_MAX:
                _orders_cache.pop(min(_orders_cache, key=lambda k: _orders_cache[k]["at"]), None)
        return orders, meta, flight
    finally:
        if _orders_flight.get(key) is flight:
            _orders_flight.pop(key, None)
        if _orders_inflight.get(key) is asyncio.current_task():
            _orders_inflight.pop(key, None)


def _order_created(o: dict):
    try:
        t = datetime.fromisoformat(str(o.get("created_at") or "").replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


async def _refresh_orders(registry: dict, key) -> bool:
    """Read a snapshot's pending orders again, by id, and put them in place:
    the order as Shopify has it now, with the same fields the sweep asked
    for, inserted if it is new to the window, dropped if it is gone or older
    than the window. True when the snapshot is current again; False when it
    was dropped (the read failed, too many changed at once, or everything was
    retired meanwhile), and the caller sweeps instead."""
    entry = _orders_cache.get(key)
    if entry is None:
        return False
    ids = sorted(entry["pending"])
    if not ids:
        return True
    if len(ids) > ORDER_REFRESH_MAX or entry["meta"].get("truncated"):
        # Too many for one read, or a sweep the page cap cut short: that holds
        # the oldest orders only, and adding a newer one an event named would
        # make a list no sweep returns. One sweep is the honest answer.
        _orders_cache.pop(key, None)
        return False
    # Taken off the to-read list, but held as being read until they land: a
    # load arriving meanwhile must wait for this read, not take the snapshot
    # for current (_orders_snapshot checks both).
    entry["pending"] = set()
    entry["reading"] = set(ids)
    try:
        return await _refresh_orders_read(registry, key, entry, ids)
    except BaseException:
        if _orders_cache.get(key) is entry:
            _orders_cache.pop(key, None)    # half put right is not put right
        raise


async def _refresh_orders_read(registry: dict, key, entry: dict, ids: list) -> bool:
    days, fields = key
    names = [f for f in fields.split(",") if f]
    full_epoch = _orders_full_epoch
    res = await shopify._tool_json(registry, "shopify_list_orders",
                           {"status": "any", "ids": ",".join(str(i) for i in ids), "limit": 250,
                            "fields": ",".join(names + ([] if "created_at" in names else ["created_at"]))})
    if _orders_full_epoch != full_epoch or _orders_cache.get(key) is not entry:
        return False                   # retired, or replaced, while this was reading
    if not core._ok(res):
        _orders_cache.pop(key, None)   # never leave the old order standing in for the new
        return False
    # The same cut _paginate_orders makes with created_at_min, so an order the
    # sweep would not have returned is not kept either.
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    fresh = {}
    for o in res.get("orders") or []:
        try:
            oid = int(o.get("id"))
        except (TypeError, ValueError):
            continue
        if oid in ids:
            fresh[oid] = o
    rows = {}
    for o in entry["orders"]:
        try:
            rows[int(o.get("id"))] = o
        except (TypeError, ValueError):
            continue
    for oid in ids:
        o = fresh.get(oid)
        made = _order_created(o) if o else None
        if o is None or made is None or made < cutoff:
            rows.pop(oid, None)        # deleted, or outside the window the sweep reads
            continue
        if "created_at" not in names:
            o = {k: v for k, v in o.items() if k != "created_at"}
        rows[oid] = o
    entry["orders"] = [rows[i] for i in sorted(rows)]   # ascending id, as the sweep pages them
    entry["reading"] = set()
    return True


async def _orders_snapshot(registry: dict, days: int,
                           fields: str = "id,created_at,total_price,current_total_price,line_items,"
                                         "cancelled_at,test,financial_status",
                           meta: Optional[dict] = None, force: bool = False) -> list:
    """Orders from the last `days`, reusing a recent sweep when there is one.

    Same contract as _paginate_orders, including the `meta` out-parameter, so
    callers that tell a throttled fetch apart from an empty store keep working.
    `force` is the merchant pressing Refresh: it discards everything first, so
    an edit made in the Shopify admin shows up immediately."""
    key = (int(days), fields)
    if force:
        _bust_orders()   # nothing already running may answer this
    else:
        # Drop anything past its window on the way in. A sweep holds names,
        # addresses and emails; once it is too old to be used it should not
        # still be sitting in memory waiting for someone to ask for that key.
        now = time.monotonic()
        for k, v in list(_orders_cache.items()):
            if now - v["at"] >= ORDER_CACHE_SECS:
                _orders_cache.pop(k, None)

    async def swept() -> tuple:
        """(orders, meta, ids named while it ran, whether THIS caller started
        it). A starter's request predates every change named while its sweep
        ran, so answering it from that sweep is what every read always did; a
        caller that joined a running sweep may have arrived after a change."""
        task = _orders_inflight.get(key)
        mine = task is None or task.done()
        if mine:
            task = asyncio.ensure_future(_sweep_orders(registry, days, fields, key))
            _orders_inflight[key] = task   # no await between the read and the write, so these cannot interleave
        # Shielded: a browser hanging up must not cancel the sweep others are waiting on.
        return (*await asyncio.shield(task), mine)

    async def refreshed() -> None:
        task = _orders_refreshing.get(key)
        if task is None or task.done():
            task = asyncio.ensure_future(_refresh_orders(registry, key))
            _orders_refreshing[key] = task
        await asyncio.shield(task)
        if _orders_refreshing.get(key) is task:
            _orders_refreshing.pop(key, None)

    def answer(orders, m):
        if meta is not None:
            meta.update(m)
        return orders

    # A snapshot with orders named as changed (_orders_changed) is put right,
    # by id, before it answers anyone: it is current only when nothing is
    # pending AND nothing is being read. Bounded: a change landing during each
    # read could otherwise keep this going; after three rounds the answer is
    # one fresh sweep, which is what every read used to be.
    last = None        # a sweep this caller may be answered from (see swept)
    for rnd in range(4):
        hit = _orders_cache.get(key) if ORDER_CACHE_SECS > 0 else None
        if hit is not None and not hit["pending"] and not hit["reading"]:
            return answer(hit["orders"], hit["meta"])
        if rnd == 3:
            break
        if hit is not None:
            if last is not None and (len(hit["pending"]) > ORDER_REFRESH_MAX
                                     or hit["meta"].get("truncated")):
                # Too many changes to read one by one, or a sweep cut short:
                # the caller that started this sweep is answered from it, as
                # it always was, and the changes wait for the next load.
                return answer(*last)
            await refreshed()
            continue
        orders, m, flight, mine = await swept()
        # A joiner of a sweep that saw a change is never answered from it.
        last = (orders, m) if (mine or not flight) else None
        if key not in _orders_cache:
            # Not stored: the cache is off, the sweep failed (said in meta),
            # or everything was retired while it ran. Its callers keep its
            # answer, as they always have, except a caller that joined it
            # while an order was named as changed: that one may hold the
            # order as it was, and sweeps again rather than being answered.
            if last is None and rnd < 2:
                continue
            return answer(orders, m)
    # Still changing after three rounds. One more read by id when that can
    # put the snapshot right, then one fresh sweep, which is what every read
    # used to be (it starts after this caller arrived, so it is current).
    hit = _orders_cache.get(key) if ORDER_CACHE_SECS > 0 else None
    if hit is not None and len(hit["pending"]) <= ORDER_REFRESH_MAX and not hit["meta"].get("truncated"):
        await refreshed()
        hit = _orders_cache.get(key)
        if hit is not None and not hit["pending"] and not hit["reading"]:
            return answer(hit["orders"], hit["meta"])
    _orders_cache.pop(key, None)
    orders, m, _flight, _mine = await swept()
    return answer(orders, m)


async def _paginate_orders(registry: dict, days: int, max_pages: int = ORDER_PAGE_CAP,
                           fields: str = "id,created_at,total_price,line_items",
                           meta: Optional[dict] = None) -> list:
    """Page through orders created in the last `days`, ascending by id (since_id),
    capped at max_pages * 250. Pulls only the requested fields. When `meta` is
    given it is filled with {"failed": bool, "truncated": bool} so money/AR callers
    can tell a throttled or capped fetch apart from a genuinely complete one
    (a swallowed failure must never read as "nothing owed")."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    out: list = []
    since_id, pages = 0, 0
    failed = truncated = False
    while pages < max_pages:
        res = await shopify._tool_json(registry, "shopify_list_orders",
                               {"status": "any", "created_at_min": since, "limit": 250,
                                "since_id": since_id, "fields": fields})
        if not core._ok(res):
            failed = True
            break
        batch = res.get("orders", [])
        if not batch:
            break
        out += batch
        pages += 1
        if len(batch) < 250:
            break
        since_id = max((o.get("id") or 0) for o in batch)
        if pages >= max_pages:
            truncated = True   # more pages existed than the cap allows
    if meta is not None:
        meta["failed"], meta["truncated"] = failed, truncated
    return out




def _orders_product_monthly(orders: list, months: list) -> dict:
    """{product_id: {"units": {mk: int}, "revenue": {mk: float}}} within the months."""
    mset = set(months)
    out: dict = {}
    for o in orders:
        if not core._order_counts(o):
            continue
        mk = core._month_key(o.get("created_at"))
        if mk not in mset:
            continue
        for li in o.get("line_items", []):
            pid = li.get("product_id")
            if not pid:
                continue
            qty = li.get("quantity") or 0
            d = out.setdefault(pid, {"units": {}, "revenue": {}})
            d["units"][mk] = d["units"].get(mk, 0) + qty
            d["revenue"][mk] = d["revenue"].get(mk, 0.0) + float(li.get("price") or 0) * qty
    return out

def _admin_order_url(order_id) -> str:
    """The Shopify admin page for an order. An order number on screen should
    always be a door, not a label."""
    store = (core.SHOPIFY_STORE or "").split(".")[0]
    return (f"https://admin.shopify.com/store/{store}/orders/{order_id}"
            if store and str(order_id or "").isdigit() else "")


def _order_tags(order: dict) -> list:
    raw = order.get("tags")
    if isinstance(raw, str):
        return [t.strip() for t in raw.split(",") if t.strip()]
    return [str(t).strip() for t in (raw or []) if str(t).strip()]


def _has_tag(order: dict, tag: str) -> bool:
    want = (tag or "").strip().lower()
    return any(t.lower() == want for t in _order_tags(order))


UNPROCESSED_TAG = os.environ.get("UNPROCESSED_TAG", "Unprocessed")
MADE_TAG = os.environ.get("MADE_TAG", "PC")
PROPOSAL_HOST = os.environ.get("PROPOSAL_HOST", "quote.projectedimage.com")
_PROPOSAL_RE = re.compile(r"https://" + re.escape(PROPOSAL_HOST) + r"/proof/[A-Za-z0-9]+")
# The tag that marks an order sold on account: releasing one to production is
# the moment its 30-day clock should start ticking in Shopify.
PO_UNPAID_TAG = os.environ.get("PO_UNPAID_TAG", "purchase order unpaid")
_tag_locks: dict = {}
_dispatch_locks: dict = {}


def _dispatch_lock(order_id) -> "asyncio.Lock":
    # Keyed on the string, not int(), so an ad-hoc shipment (adhoc:<uuid>) gets a
    # lock too. int() here used to raise before the lock was even taken, which the
    # route reported as "it MAY have been booked and charged" for a request that
    # never reached World Options.
    key = str(order_id)
    lock = _dispatch_locks.get(key)
    if lock is None:
        if len(_dispatch_locks) > 500:   # ad-hoc ids are one per shipment, so this grows
            for k, l in [(k, l) for k, l in _dispatch_locks.items() if not l.locked()][:250]:
                _dispatch_locks.pop(k, None)
        lock = _dispatch_locks[key] = asyncio.Lock()
    return lock


def _tag_lock(order_id) -> "asyncio.Lock":
    key = int(order_id)
    lock = _tag_locks.get(key)
    if lock is None:
        if len(_tag_locks) > 500:   # one per order ever tagged; prune the idle ones
            for k, l in [(k, l) for k, l in _tag_locks.items() if not l.locked()][:250]:
                _tag_locks.pop(k, None)
        lock = _tag_locks[key] = asyncio.Lock()
    return lock


async def _sync_order_tags(registry: dict, order_id, add=(), remove=(), unless=(),
                           allow_dead: bool = False, outcome: Optional[dict] = None) -> tuple:
    """Move an order along the tag workflow (Unprocessed -> IP -> PC) without
    touching any other tag. Set-based, case-insensitive: re-running an action
    can never duplicate a tag or leave conflicting statuses. Dead orders
    (cancelled, refunded, fulfilled) are left alone. Returns (ok, note).

    The GET-modify-PUT is serialized per order with a lock: without it, the SPA
    stamp and the print doc's background sync (or two quick clicks) could both
    read the same tag string and the second PUT would clobber the first
    (e.g. dropping the just-added IP, or resurrecting Unprocessed)."""
    if shopify._order_tag_writer is None:
        return False, "Tag updates are not enabled on this server."
    try:
        async with _tag_lock(order_id):
            o = await shopify._tool_json(registry, "shopify_get_order", {"order_id": int(order_id)})
            if not core._ok(o) or not o.get("id"):
                return False, "Couldn't read the order to update its tags."
            if outcome is not None:
                outcome["order"] = o      # read once: a release's terms check uses it too
            if _order_status(o) and not allow_dead:
                # Cancelled, refunded or fulfilled: tags stay as they are. The
                # app may be finding this out here, before Shopify's webhook,
                # and the queues and the missed-orders strip go on what they
                # last saw until something says the order changed.
                _orders_changed([order_id])
                return True, ""
            cur = _order_tags(o)
            if unless:
                # An order that already carries one of these is past the move
                # being asked for (a reprint of a made order is not a release).
                keep = {size_list._norm_key(t) for t in unless}
                if any(size_list._norm_key(t) in keep for t in cur):
                    if outcome is not None:
                        outcome["kept"] = True   # told apart from a move, for the caller that cares
                    _orders_changed([order_id])   # past the bench in Shopify: likewise
                    return True, ""
            drop = {size_list._norm_key(t) for t in add} | {size_list._norm_key(t) for t in remove}
            new = [t for t in cur if size_list._norm_key(t) not in drop] + list(add)
            if {size_list._norm_key(t) for t in new} == {size_list._norm_key(t) for t in cur}:
                return True, ""   # already in the right state: no write
            try:
                await shopify._order_tag_writer(int(order_id), ", ".join(new))
            finally:
                # The queues are filtered on tags, so this write changes what a
                # sweep returns. On the way out even if the write raised: a
                # half-applied change must not leave the old order behind.
                _orders_changed([order_id])
            return True, ""
    except httpx.HTTPStatusError as e:
        if e.response is not None and e.response.status_code in (401, 403):
            logger.warning("order tag update refused (%s): the access token lacks write_orders",
                           e.response.status_code)
            return False, ("Tags couldn't update: the app's access token doesn't have the "
                           "write_orders permission yet.")
        logger.exception("order tag update failed")
        return False, "Tags couldn't update: Shopify refused the change."
    except Exception:
        logger.exception("order tag update failed")
        return False, "Tags couldn't update. Check the server logs."


# What the panel may change. `name` is deliberately absent: Shopify derives an
# address's name from first + last, so a form offering "name" would report a
# save and change nothing.
_EDIT_ADDR_KEYS = ("firstname", "lastname", "company", "street", "street2",
                   "city", "state", "postcode", "country", "phone")
_EDIT_EMAIL = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")
# A courier prints each address line in a fixed width. Longer still saves - this
# is Shopify's record, not the label - but the person typing should be told.
COURIER_LINE_CHARS = 35


def _clean_edit_fields(body: dict, current: dict) -> tuple:
    """Validate an edit and merge it over what the order already has.

    Shopify REPLACES the whole shipping address, so a form that posted only the
    fields it happened to show would silently blank the rest. Everything is
    therefore merged over the order's current address before it goes, and a key
    the caller did not send keeps its existing value rather than becoming "".

    The address is then put through the SAME validators the courier booking uses.
    An address that passes here has to pass there minutes later, and the two
    standards drifting apart is how a merchant fixes an address in the app and is
    still refused at the dispatch window.
    """
    out, changed, warn = {}, [], []
    if isinstance(body.get("ship_to"), dict):
        sent = body["ship_to"]
        merged = {k: str(current.get(k) or "") for k in _EDIT_ADDR_KEYS}
        for k in _EDIT_ADDR_KEYS:
            if k in sent:
                merged[k] = str(sent.get(k) or "")
        merged = {k: v for k, v in desk._clean_address(merged).items() if k in _EDIT_ADDR_KEYS}
        why = desk._addr_ready(merged) or desk._country_ready(merged)
        if why:
            return None, why, [], []
        for k in _EDIT_ADDR_KEYS:
            if merged.get(k, "") != str(current.get(k) or ""):
                changed.append(k)
        for k in ("street", "street2"):
            if len(merged.get(k, "")) > COURIER_LINE_CHARS:
                warn.append("The " + ("first" if k == "street" else "second")
                            + " address line is longer than the "
                            + str(COURIER_LINE_CHARS) + " characters a courier label prints.")
        out["ship_to"] = merged
    for k, cap in (("email", 200), ("phone", 60), ("note", 5000)):
        if k in body:
            v = str(body.get(k) or "").strip()[:cap]
            if v != str(current.get(k) or ""):
                changed.append(k)
            out[k] = v
    email = out.get("email", "")
    if email and not _EDIT_EMAIL.match(email):
        return None, "That email address does not look right.", [], []
    return out, "", changed, warn


def _live_booking(order_id) -> dict:
    """The order's courier booking, if one is live. A cancelled shipment is not
    one: the parcel is not moving and the address is free to change."""
    e = desk._load_dispatch().get(str(order_id)) or {}
    return e if (e.get("tracking_number") and not e.get("canceled")) else {}


async def _order_editable(registry: dict, order_id) -> tuple:
    """What the panel prefills from, read LIVE rather than off the queue sweep.

    Three reasons it cannot reuse the order object the Production Manager
    already holds: that object's note has had the proposal URL surgically
    removed and is cut to 500 characters, so round-tripping it would delete the
    artwork proof link from Shopify for good; the sweep is cached for up to 45s
    and the panel then sits open while somebody types; and the guards below have
    to be decided on the order as it is now, not as it was when the queue loaded.
    """
    o = await shopify._tool_json(registry, "shopify_get_order", {"order_id": int(order_id)})
    if not core._ok(o) or not o.get("id"):
        return None, "Couldn't read that order from Shopify."
    booked = _live_booking(order_id)
    return {
        "order_id": o.get("id"),
        "name": o.get("name") or "",
        "ship_to": _ship_to(o),
        # The RAW note. The queue's copy has had the proposal URL cut out of it
        # and the remainder truncated to 500 characters, so prefilling a form
        # from that one and saving would delete the artwork proof link from
        # Shopify for good. Prefilled from here, an untouched note round-trips
        # byte for byte and the link survives because it never left.
        "note": str(o.get("note") or ""),
        "status": _order_status(o),
        "booked": ({"carrier": booked.get("carrier") or "",
                    "service": booked.get("service") or "",
                    "tracking": booked.get("tracking_number") or "",
                    "at": booked.get("dispatched_at") or ""} if booked else None),
    }, ""


_ADDR_COMPARE = ("street", "street2", "postcode", "city", "country")


def _addr_key(a: dict) -> tuple:
    return tuple(" ".join(str((a or {}).get(k) or "").lower().split()) for k in _ADDR_COMPARE)


def _flag_address_divergence(order_id, live: dict) -> None:
    """A live booking cut for a different address than the order now has is
    marked, so the fulfilment path stops instead of emailing tracking for a
    parcel going somewhere else. Only when the booking recorded its address."""
    try:
        e = (desk._load_dispatch().get(str(order_id)) or {})
        booked_at = e.get("booked_address")
        if (e.get("tracking_number") and not e.get("canceled") and not e.get("fulfilled")
                and isinstance(booked_at, dict) and not e.get("address_changed_at")
                and _addr_key(booked_at) != _addr_key(live)):
            desk._update_dispatch(order_id, lambda x: x.update(
                {"address_changed_at": datetime.now(timezone.utc).isoformat()}))
    except Exception:
        logger.exception("could not compare the booked address for %s", order_id)


def _rest_totals(o: dict) -> dict:
    """An order's tax and total from a REST read, in the shape the order writer
    returns them. Not the amount outstanding: GraphQL's is documented as signed
    (negative when the customer is owed), REST's is not, so a note built from a
    REST read says what the totals alone can say."""
    cur = str(o.get("currency") or "")
    def money(key):
        return {"amount": str(o.get(key) or ""), "currency": cur}
    return {"tax": money("current_total_tax"), "total": money("current_total_price"),
            "outstanding": {"amount": "", "currency": cur}}


def _tax_change_note(before: dict, totals: dict) -> str:
    """What an address edit did to the order's tax, said plainly, or ''.

    From Shopify API 2026-10 a new shipping address on an unfulfilled order
    recalculates its tax: a UK address corrected to an export destination, or
    the other way, changes the total and so what the customer owes. Shopify
    makes the change; this says so, rather than leave it to be found."""
    def num(v):
        try:
            return round(float(v), 2)
        except (TypeError, ValueError):
            return None
    was, now = before.get("tax") or {}, totals.get("tax") or {}
    tax_was, tax_now = num(was.get("amount")), num(now.get("amount"))
    if tax_was is None or tax_now is None or tax_was == tax_now:
        return ""
    cur = str(now.get("currency") or was.get("currency") or "")
    def fmt(x):
        return ("\u00a3%.2f" % x) if cur in ("GBP", "") else ("%s %.2f" % (cur, x))
    total_was = num((before.get("total") or {}).get("amount"))
    total_now = num((totals.get("total") or {}).get("amount"))
    # Shopify's amount outstanding after the change, signed: above nothing the
    # customer owes it, below nothing it is theirs to be refunded. It already
    # counts what they paid, which the change in total alone does not.
    owed = num((totals.get("outstanding") or {}).get("amount"))
    msg = ("Shopify recalculated the tax for the new address: " + fmt(tax_was) + " before, "
           + fmt(tax_now) + " now")
    if total_now is not None:
        msg += ", so the order total is " + fmt(total_now)
    if owed is not None:
        if owed > 0:
            return msg + ". The customer now owes " + fmt(owed) + "."
        if owed < 0:
            return msg + ". " + fmt(-owed) + " is due back to them: refund it in Shopify."
        return msg + ". Nothing more is owed either way."
    # No amount outstanding to go on (the order was read back after a lost
    # answer): only the change in total, said as what it might mean.
    if total_was is not None and total_now is not None and total_now != total_was:
        if total_now < total_was:
            return msg + (". If they had paid in full, " + fmt(total_was - total_now)
                          + " is due back to them: check the order in Shopify.")
        return msg + (". If they had paid in full, " + fmt(total_now - total_was)
                      + " more is due: check the order in Shopify.")
    return msg + "."


async def _edit_order(registry: dict, order_id, body: dict) -> tuple:
    """Apply a merchant's edit to a placed order.

    Returns (ok, message, changed, name, warnings).

    Serialized on the same per-order lock the tag writer uses: an edit and a
    Ready-to-make pressed together would otherwise read the same order and race.
    """
    if shopify._order_writer is None:
        return False, "Order edits are not enabled on this server.", [], "", []
    name = ""
    try:
        async with _tag_lock(order_id):
            o = await shopify._tool_json(registry, "shopify_get_order", {"order_id": int(order_id)})
            if not core._ok(o) or not o.get("id"):
                return False, "Couldn't read the order to edit it.", [], "", []
            name = str(o.get("name") or "")
            # A cancelled order is a closed record. Its sibling, the tag writer,
            # makes the same call and leaves finished orders alone.
            dead = _order_status(o)
            if dead in ("cancelled", "refunded"):
                return False, ("That order is " + dead + ", so it is a closed record - "
                               "Shopify will not take changes to it."), [], name, []
            current = dict(_ship_to(o))
            current["note"] = str(o.get("note") or "")
            fields, why, changed, warn = _clean_edit_fields(body, current)
            if fields is None:
                return False, why, [], name, []
            if not changed:
                # Provably wrote nothing, so nothing is stale. Busting here would
                # cost a full store sweep for a save that did not save anything.
                # But a booked label cut for a different address is still worth
                # saying out loud: a retry after a lost answer finds the change
                # already made, and without this the divergence was never marked.
                _flag_address_divergence(order_id, current)
                return True, "", [], name, []
            # The parcel may already be moving under the old address. Changing
            # Shopify does NOT change a label that is printed and booked, so the
            # merchant has to say out loud that they know that.
            if "ship_to" in fields:
                # The order's own province code goes back as a code whatever
                # its shape (Dublin is "D", Tokyo "JP-13"), not as the
                # deprecated free-text province.
                own = str(((o.get("shipping_address") or {}).get("province_code")) or "").strip()
                if own and str(fields["ship_to"].get("state") or "").strip() == own:
                    fields["ship_to"]["state_is_code"] = True
            booked = _live_booking(order_id)
            if booked and "ship_to" in fields and not body.get("confirm_booked"):
                return False, ("A courier label is already booked for this order ("
                               + (booked.get("carrier") or "courier")
                               + " " + (booked.get("tracking_number") or "")
                               + "). Changing the address here does not change that "
                               "label or the courier's booking."), [], name, []
            r = await shopify._order_writer(int(order_id), fields)
            if not r.get("ok") and r.get("reason") == "unknown":
                # The answer was lost, not necessarily the change: read the order
                # and see. "Shopify refused the change" was said over edits that
                # had landed, and the retry then found nothing to do.
                _orders_changed([order_id])
                again = await shopify._tool_json(registry, "shopify_get_order", {"order_id": int(order_id)})
                if core._ok(again) and again.get("id"):
                    now_there = dict(_ship_to(again))
                    now_there["note"] = str(again.get("note") or "")
                    _f2, _w2, still, _warn2 = _clean_edit_fields(body, now_there)
                    if not still:
                        r = {"ok": True, "totals": _rest_totals(again)}
                if not r.get("ok"):
                    return False, ("Shopify did not answer, so it is not known whether the change "
                                   "was made. Open the order in Shopify to check before trying again."), \
                        [], name, []
            if not r.get("ok"):
                reason = str(r.get("reason") or "")
                detail = str(r.get("detail") or "")
                if reason == "permission":
                    return False, ("The order couldn't be changed: the app's access token "
                                   "doesn't have the write_orders permission yet."), [], name, []
                return False, ("Shopify refused the change"
                               + (": " + detail if detail else ".")), [], name, []
            note = _tax_change_note(_rest_totals(o), r.get("totals") or {})
            if note:
                warn = list(warn) + [note]
                changed = list(changed) + ["tax recalculated"]
            if booked and "ship_to" in fields:
                # Mark the divergence so the fulfilment path can refuse rather
                # than email the customer tracking for a parcel addressed
                # somewhere else.
                desk._update_dispatch(order_id, lambda e: e.update(
                    {"address_changed_at": datetime.now(timezone.utc).isoformat()}))
    except Exception:
        # A write may have landed before this raised, so the order is suspect.
        _orders_changed([order_id])
        logger.exception("order edit failed for order %s", order_id)
        return False, "The order couldn't be changed. Check the server logs.", [], name, []
    # The queues read the address straight off the cached sweep, so the order
    # is read again before the snapshot answers anyone.
    _orders_changed([order_id])
    return True, "", changed, name, warn


async def _fulfill_if_ready(registry: dict, order_id, notify: Optional[bool] = None,
                            ack_address: bool = False) -> dict:
    """The single gate for telling Shopify (and the customer) an order shipped.

    Booking a courier label is preparation, not shipping: the gobo may not be
    made yet. So fulfilment fires only when BOTH are true - the order is marked
    made AND a live label is booked - triggered by whichever happens last.
    Idempotent: an already-fulfilled order is a no-op.

    Returns {fulfilled, reason, detail, notified, tag_note}."""
    oid = int(order_id)
    entry = dict(desk._load_dispatch().get(str(oid)) or {})
    made = bool((production._load_prod_state().get(str(oid)) or {}).get("made_at"))
    tracking = str(entry.get("tracking_number") or "").strip()

    if entry.get("fulfilled"):
        return {"fulfilled": True, "reason": "already", "notified": bool(entry.get("notified")),
                "detail": "", "tag_note": ""}
    if not tracking or entry.get("canceled"):
        return {"fulfilled": False, "reason": "no_label", "notified": False,
                "detail": "No courier label is booked for this order yet.", "tag_note": ""}
    if not made:
        return {"fulfilled": False, "reason": "not_made", "notified": False,
                "detail": "Label booked. Shopify is fulfilled and the customer emailed "
                          "when you mark this order made.", "tag_note": ""}
    # An address changed in the Shopify admin never passes through the app's
    # own edit route, so it is compared here too, the last moment before
    # tracking goes out. A failed read does not hold the order: the label and
    # the made gobo are real, and a Shopify outage must not stop the bench.
    booked_at = entry.get("booked_address")
    if (isinstance(booked_at, dict) and not ack_address and not entry.get("address_changed_at")
            and not entry.get("address_acked_at")):
        try:
            live = await shopify._tool_json(registry, "shopify_get_order", {"order_id": oid})
            if core._ok(live) and live.get("id"):
                _flag_address_divergence(oid, _ship_to(live))
                entry = dict(desk._load_dispatch().get(str(oid)) or {})
        except Exception:
            logger.exception("could not read order %s to compare its address", oid)
    # The delivery address was edited AFTER this label was booked. Fulfilling now
    # would email the customer tracking for a parcel that is on its way to the
    # address the label was cut from, while the order page shows the new one -
    # the one moment where saying nothing is worse than stopping.
    if entry.get("address_changed_at") and not ack_address:
        return {"fulfilled": False, "reason": "address_changed", "notified": False,
                "detail": ("The delivery address was changed after this label was booked, "
                           "so the parcel is on its way to the address the label was cut "
                           "from, not the one on the order now. Cancel the shipment and "
                           "book again, or confirm that the parcel went to the right place."),
                "tag_note": ""}
    if entry.get("address_changed_at") and ack_address:
        # Asked and answered. Clear it so the order is not stopped twice, and so
        # a later genuine edit through the app can raise it again; the read of
        # the live order above is not repeated for an answered question.
        try:
            _acked = datetime.now(timezone.utc).isoformat()
            desk._update_dispatch(oid, lambda e: (e.pop("address_changed_at", None),
                                             e.update({"address_acked_at": _acked}), e)[2])
        except Exception:
            logger.exception("could not clear the address-change flag on %s", oid)

    do_notify = entry.get("notify", True) if notify is None else bool(notify)
    # Tag BEFORE fulfilling: _sync_order_tags deliberately skips orders Shopify
    # reports as cancelled/refunded/fulfilled, so a tag written afterwards would
    # be silently dropped and the order would never reach the Dispatched queue.
    tag_ok, tag_note = await production._dispatch_move_tags(registry, oid)
    fulfillment = {"ok": False, "reason": "not_attempted"}
    if shopify._fulfillment_writer is not None:
        try:
            fulfillment = await shopify._fulfillment_writer(
                oid,
                tracking_number=tracking,
                # Shopify only auto-links tracking in the customer email for carrier
                # names it recognizes; WO's enum codes (ROYALMAIL, EVRISEND) are not.
                tracking_company=(worldoptions.shopify_carrier(entry.get("carrier_known")
                                                               or entry.get("carrier_name") or "")
                                  if worldoptions else (entry.get("carrier_name") or "")),
                tracking_url=None,
                notify_customer=do_notify,
            )
            _orders_changed([order_id])   # fulfillment_status is a swept field
        except Exception:
            logger.exception("fulfillment failed for order %s", oid)
            _orders_changed([order_id])   # it may still have landed before the error
            fulfillment = {"ok": False, "reason": "error",
                           "detail": "Shopify fulfillment failed; the label is still valid. "
                                     "You can fulfill the order manually in Shopify."}

    if tag_ok:
        tag_note = ""
    if not fulfillment.get("ok") and fulfillment.get("reason") == "nothing_to_fulfill":
        # Shopify has nothing left to fulfil. If that is because the order is
        # already fulfilled, treat it as done: otherwise the record keeps
        # fulfilled=False, every later pass re-enters and gets the same answer,
        # and the order shows as dispatched-but-unfulfilled for ever while the
        # customer already has their tracking. Read the order to find out; this
        # branch is rare, so the extra call costs nothing in the normal case.
        current = await shopify._tool_json(registry, "shopify_get_order", {"order_id": oid})
        if core._ok(current) and _order_status(current) == "fulfilled":
            logger.info("order %s was already fulfilled in Shopify; recording it", oid)
            fulfillment = {"ok": True, "reason": "already_fulfilled", "fulfillment_id": None,
                           "detail": "already fulfilled in Shopify; no fulfilment or email went from here"}
            # The tag move above skipped it as a dead order, so it sat in To
            # ship under its PC tag for good. It is complete: file it so.
            tag_ok, tag_note = await production._dispatch_move_tags(registry, oid, allow_dead=True)
            if tag_ok:
                tag_note = ""
    # Nothing was created here for an order Shopify already had fulfilled, so
    # no tracking email went from here either, whatever the record was asked.
    sent_here = bool(fulfillment.get("ok")) and fulfillment.get("reason") != "already_fulfilled"
    if not fulfillment.get("ok") and fulfillment.get("reason") != "unknown":
        # Put the order back where it was: it has not shipped after all. Not
        # when the outcome is unknown: it may have shipped, and a revert then
        # put a fulfilled order back in To ship under a "failed" message.
        try:
            await _sync_order_tags(registry, oid, add=(MADE_TAG,),
                                   remove=(desk.DISPATCHED_TAG, *desk.LEGACY_DISPATCHED_TAGS))
        except Exception:
            logger.exception("tag revert after failed fulfillment failed for order %s", oid)
    if fulfillment.get("ok"):
        def _mark_fulfilled(e):
            e.update({"fulfilled": True, "fulfillment_id": fulfillment.get("fulfillment_id"),
                      "notified": bool(do_notify and sent_here),
                      "fulfilled_at": datetime.now(timezone.utc).isoformat()})
            return e
        try:
            desk._update_dispatch(oid, _mark_fulfilled)
        except desk.DispatchStoreUnwritable:
            logger.exception("order %s was fulfilled in Shopify but the dispatch "
                             "record could not be updated", oid)
            tag_note = ((tag_note + " ") if tag_note else "") + (
                "Shopify has the fulfilment, but the app could not save its own copy. "
                "It may still show this order as waiting.")
    return {"fulfilled": bool(fulfillment.get("ok")),
            "reason": fulfillment.get("reason") or ("ok" if fulfillment.get("ok") else "error"),
            "detail": fulfillment.get("detail") or "",
            "notified": bool(do_notify and sent_here),
            "tag_note": tag_note}


async def _unfulfill_dispatch(registry: dict, order_id) -> str:
    """Undo a fulfilment when an order is un-marked made (it is not shipped after
    all). Cancels the Shopify fulfilment so the customer is not left holding live
    tracking. Returns a note for the UI."""
    oid = int(order_id)
    entry = (desk._load_dispatch().get(str(oid)) or {})     # read only, for the guard below
    if not entry.get("fulfilled"):
        return ""
    note = ""
    fid = entry.get("fulfillment_id")
    if fid and shopify._fulfillment_canceler is not None:
        try:
            fc = await shopify._fulfillment_canceler(int(fid))
            _orders_changed([order_id])   # fulfillment_status is a swept field
            note = ("" if fc.get("ok") else
                    "The order is still marked fulfilled in Shopify (" + (fc.get("detail") or "")
                    + "). Cancel that fulfillment in Shopify so the customer is not left with "
                      "tracking for something that has not shipped.")
        except Exception:
            logger.exception("fulfillment cancel failed for order %s", oid)
            _orders_changed([order_id])   # it may still have landed before the error
            note = ("The order is still marked fulfilled in Shopify. Cancel that fulfillment "
                    "there so the customer is not left with tracking for an unshipped order.")
    # Re-read here: the store may have gained a booking while Shopify was thinking,
    # and the snapshot taken above no longer describes what is on disk.
    def _clear(e):
        e["fulfilled"] = False
        e["notified"] = False
        e.pop("fulfillment_id", None)
        return e
    try:
        desk._update_dispatch(oid, _clear)
    except desk.DispatchStoreUnwritable:
        logger.exception("could not clear the fulfilment record for order %s", oid)
        note = ((note + " ") if note else "") + ("The app could not save this change, "
                                                 "so it may still show as fulfilled.")
    return note


def _extract_proposal(note: str) -> tuple:
    """(proposal_url, note_without_it). Only the store's own quote domain is ever
    recognized: an arbitrary URL in a customer note must never become a clickable
    embed. The label prints the cleaned note; the URL becomes the Preview button."""
    m = _PROPOSAL_RE.search(note or "")
    if not m:
        return "", (note or "")
    cleaned = (note or "").replace(m.group(0), "")
    cleaned = re.sub(r"Proposal link:\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return m.group(0), cleaned


def _parse_due_date(v):
    """A customer-typed deadline as a date, or None. The store's option sets write
    "13 August 2026" (Date Required) and "30-08-2026" (Wedding Date); this is a UK
    store, so numeric dates are ALWAYS day-first, never American month-first."""
    s = re.sub(r"\s+", " ", str(v or "").strip())
    if not s:
        return None
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d %B %Y", "%d %b %Y",
                "%d %B %y", "%d %b %y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _order_due(o: dict):
    """The order's completion deadline, from the dates the customer already gave:
    each item's "Date Required" (the explicit deadline) or, failing that, its
    "Wedding Date" (the gobo must exist by the wedding). The earliest date across
    the order's items wins. Returns a date or None."""
    dues = []
    for li in (o.get("line_items") or []):
        if production._label_skip_item(str(li.get("title") or li.get("name") or "")):
            continue
        d = _parse_due_date(production._item_prop(li, "Date Required")) or _parse_due_date(production._item_prop(li, "Wedding Date"))
        if d:
            dues.append(d)
    return min(dues) if dues else None


def _fmt_due(d) -> str:
    """"13 Aug", with the year only when it is not this year."""
    if not d:
        return ""
    out = f"{d.day} {d.strftime('%b')}"
    return out if d.year == core._london_today().year else out + f" {d.year}"


def _order_status(o: dict) -> str:
    """What the workbench must know before making anything: cancelled and refunded
    orders must never be built; fulfilled ones are probably stale tags."""
    if o.get("cancelled_at"):
        return "cancelled"
    if str(o.get("financial_status") or "").lower() in ("refunded", "voided"):
        return "refunded"
    if str(o.get("fulfillment_status") or "").lower() == "fulfilled":
        return "fulfilled"
    return ""


def _order_country(country, postcode) -> str:
    """The country an order is really going to. A customer can choose United
    Kingdom and give a Jersey or Guernsey postcode, and those islands are
    outside the UK customs area: read as GB, the parcel was quoted domestic
    and booked with no declaration. The Isle of Man is inside it, so an IM
    postcode stays GB. The pasted-address parser already knew this (B12)."""
    cc = str(country or "").strip().upper()
    if cc in ("GB", "UK"):
        m = re.match(r"\s*([A-Za-z]{2})[0-9]", str(postcode or ""))
        if m and m.group(1).upper() in ("JE", "GY"):
            return {"JE": "JE", "GY": "GG"}[m.group(1).upper()]
    return str(country or "")


def _ship_to(o: dict) -> dict:
    """The order's delivery address in our internal address shape (for a quote)."""
    a = o.get("shipping_address") or o.get("billing_address") or {}
    cust = o.get("customer") or {}
    return {
        "name":      a.get("name") or "",
        "company":   a.get("company") or "",
        "firstname": a.get("first_name") or cust.get("first_name") or "",
        "lastname":  a.get("last_name") or cust.get("last_name") or "",
        # Shopify's two lines STAY two lines: couriers cap each address line at 35
        # characters, and joining them manufactured over-long lines from good data.
        "street":    str(a.get("address1") or "").strip(),
        "street2":   str(a.get("address2") or "").strip(),
        "postcode":  a.get("zip") or "",
        "city":      a.get("city") or "",
        "state":     a.get("province_code") or a.get("province") or "",
        "country":   _order_country(a.get("country_code"), a.get("zip")),
        "phone":     a.get("phone") or o.get("phone") or cust.get("phone") or "",
        "email":     o.get("email") or cust.get("email") or "",
    }


def _line_qty(li: dict) -> int:
    """How many of a line the customer still has on the order.

    Shopify keeps `quantity` at what was ORDERED. A refund or an order edit
    lowers `current_quantity` and leaves `quantity` alone, so a label read
    from `quantity` printed the refunded gobo, the bench cut it, the stock
    app booked its glass and the customs declaration carried its value.
    Everything that makes, weighs, declares or books glass for a line reads
    this instead. A line with no quantity at all counts as one, as before."""
    q = li.get("current_quantity")
    if q is None:
        q = li.get("quantity")
    if q is None:
        return 1
    try:
        return max(0, int(q))
    except (TypeError, ValueError):
        return 0


def _order_weight_kg(o: dict) -> float:
    """Best-effort parcel weight from Shopify per-item grams (0 when not recorded)."""
    grams = 0.0
    for li in (o.get("line_items") or []):
        if production._label_skip_item(str(li.get("title") or li.get("name") or "")):
            continue
        g = li.get("grams")
        if g:
            grams += float(g) * float(_line_qty(li))
    return round(grams / 1000.0, 3) if grams else 0.0


# The shop's own record: its name, address, phone and email. It changes when
# the merchant edits it in Shopify, which is to say almost never, and it was
# re-fetched on every dispatch quote and every booking - a Shopify round trip
# added to a path where somebody is already waiting on a courier.
#
# Cached ONLY on success. A failed read must never become an answer, so a
# Shopify hiccup falls through to the empty dict exactly as it did before.
_shop_cache: dict = {}
SHOP_CACHE_SECS = _env_num(int, os.environ.get("SHOP_CACHE_SECS", "900"), "900", "SHOP_CACHE_SECS")


async def _shop_record(registry: dict) -> dict:
    hit = _shop_cache.get("v")
    if hit and time.monotonic() - _shop_cache.get("at", 0) < SHOP_CACHE_SECS:
        return hit
    try:
        shop = await shopify._tool_json(registry, "shopify_get_shop", {})
    except Exception:
        shop = {}
    shop = shop if isinstance(shop, dict) and core._ok(shop) else {}
    if shop:
        _shop_cache.update({"v": shop, "at": time.monotonic()})
    return shop


async def _origin_address(registry: dict) -> dict:
    """Our shop's dispatch origin: the saved Settings address, else the Shopify
    shop address as a sensible default."""
    o = dict(desk._load_shipping().get("origin") or {})
    # Always merge per-field with the Shopify shop record: a saved origin that
    # lacks phone/email must not lose the shop's (bookings REQUIRE both).
    shop = await _shop_record(registry)

    return {
        "name":      o.get("name") or shop.get("name") or "",
        "company":   o.get("company") or shop.get("name") or "",
        "firstname": o.get("firstname") or "",
        "lastname":  o.get("lastname") or "",
        "street":    o.get("street") or str(shop.get("address1") or "").strip(),
        "street2":   o.get("street2") or str(shop.get("address2") or "").strip(),
        "postcode":  o.get("postcode") or shop.get("zip") or "",
        "city":      o.get("city") or shop.get("city") or "",
        "state":     o.get("state") or shop.get("province_code") or shop.get("province") or "",
        "country":   o.get("country") or shop.get("country_code") or "",
        "phone":     o.get("phone") or shop.get("phone") or "",
        "email":     o.get("email") or shop.get("email") or "",
    }


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as core.NAME and sibling.NAME, never a copied name.
from gizmo import production  # noqa: E402
from gizmo import shopify  # noqa: E402
from gizmo import size_list  # noqa: E402
from gizmo import dispatch as desk  # noqa: E402
import copilot as core  # noqa: E402
