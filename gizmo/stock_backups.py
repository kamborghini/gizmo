"""The stock sheet's own backups, restoring one, and the nightly job.

A stock backup holds every field of every line, the supplier contacts and
the settings (the stock app's held the lines only, and its restore left
reorder levels, barcodes and on-order figures as they were: flaw 4). A
restore is the master's, takes a safety backup first, and never removes
history: it writes a line for every field it puts back. It keeps the
production bookings, day sheets and orders: bookings and sheets made after
the backup are applied again, and each line's on-order figure follows the
orders still open, so glass used since and orders placed since are neither
forgotten nor counted twice.

The stock app's own backups are kept as the encrypted files they are, an
archive: listed and downloadable, never restored here, never pruned.

The nightly job runs on the first scheduler tick of each London day once
the stock sheet has moved in: one snapshot (one only after downtime, as a
missed day cannot be rebuilt exactly), one backup, and change snapshots
older than 30 days removed.
"""
import base64
import json
from datetime import datetime, timedelta, timezone

from gizmo import clock, stock, stock_store

KEEP_NEWEST = 30           # always kept, however old
KEEP_DAYS = 7              # past the newest thirty, kept while this young
KEEP_MOST = 200            # never more than this many
CHANGE_SNAPSHOT_DAYS = 30
SYSTEM = {"user": "system", "person": None}
# What a restore puts back on a line: every field but its id, its on-order
# figure (which follows the orders kept) and its own timestamps.
RESTORED_FIELDS = ("key", "category", "sub_category", "size", "notes", "written_off", "barcode", "supplier",
                   "currency", "unit_cost", "unit_cost_gbp", "start", "received", "used", "current",
                   "reorder_point", "reorder_qty")


def _instant(iso):
    try:
        t = datetime.fromisoformat(str(iso))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _prune(now: datetime) -> int:
    """The stock app's retention: past the thirty newest and older than a
    week, or past two hundred, a backup goes. Its own archive stays."""
    ours = [b for b in stock_store.list_backups() if b.get("format") == "stock-1"]
    ours.sort(key=lambda b: (_instant(b["at"]) or now, b["id"]), reverse=True)
    gone = 0
    for n, b in enumerate(ours):
        if (n >= KEEP_NEWEST and (_instant(b["at"]) or now) < now - timedelta(days=KEEP_DAYS)) or n >= KEEP_MOST:
            gone += stock_store.delete_backup(b["id"])
    return gone


def make_backup(who: dict) -> dict:
    with stock._lock:
        st = stock.state()
        if not st["settings"].get("live_since"):
            # Checked before anything is written: a backup made ahead of the
            # move would take a number the converted backups need.
            raise stock.Refused(409, "Stock has not moved into Reactor yet.")
        items = stock.items_in_order(st["items"])
        now = datetime.now(timezone.utc)
        content = {"items": items, "suppliers": st["suppliers"].get("suppliers") or [],
                   "settings": {"meta": dict(st["settings"].get("meta") or {})}}
        backup = dict(content, id=max((b["id"] for b in stock_store.list_backups()), default=0) + 1,
                      at=now.isoformat(), filename=f"stock-{now.strftime('%Y%m%d-%H%M%S')}.json", format="stock-1",
                      by=who["user"], person=who["person"], item_count=len(items),
                      size_bytes=len(json.dumps(content)))
        stock_store.write_backup(backup)
        _prune(now)
        stock.commit(st, changed=set(), history=[stock.history_row(
            who, "backup", detail=f"backup #{backup['id']} ({len(items)} items)")])
        return {k: backup[k] for k in ("id", "at", "filename", "size_bytes", "item_count", "format")}


def backups() -> dict:
    rows = sorted(stock_store.list_backups(), key=lambda b: (_instant(b.get("at")) or datetime.min.replace(
        tzinfo=timezone.utc), b["id"]), reverse=True)[:60]
    return {"backups": [{k: b.get(k) for k in ("id", "at", "filename", "size_bytes", "item_count", "format", "by")}
                        for b in rows]}


def _find(backup_id) -> dict:
    b = next((x for x in stock_store.list_backups() if str(x.get("id")) == str(backup_id)), None)
    if not b:
        raise stock.Refused(404, "That backup was not found.")
    return b


def download(backup_id) -> tuple:
    """(the file's bytes, its name): one of ours as its JSON, one of the
    stock app's as the encrypted file it always was."""
    b = _find(backup_id)
    if b.get("format") == "legacy-fernet":
        return base64.b64decode(b.get("token") or ""), b.get("filename") or f"stock-{b['id']}.json.enc"
    return json.dumps(b).encode("utf-8"), b.get("filename") or f"stock-{b['id']}.json"


def restore(uid: str, backup_id) -> dict:
    if team._team_role(uid) != "master":
        raise stock.Refused(403, "Only the master admin can restore stock.")
    b = _find(backup_id)
    if b.get("format") != "stock-1":
        raise stock.Refused(400, "This older backup is kept as an archive and cannot be restored here.")
    who = stock.actor(uid)
    safety = make_backup(who)
    with stock._lock:
        st = stock.state()
        pre = stock.take_snapshot(st, "manual", who, "pre-restore safety snapshot")
        doc, history, fields = st["items"], [], 0
        lines = doc.setdefault("items", {})
        for saved in b.get("items") or []:
            it = lines.get(str(saved["id"]))
            if it is None:                       # a line the sheet no longer has comes back as it was
                it = lines[str(saved["id"])] = dict(saved)
                doc["next_id"] = max(doc.get("next_id") or 1, saved["id"] + 1)
                history.append(stock.history_row(who, "create", item_key=saved["key"], item_id=saved["id"],
                                                 detail=f"restore: {saved['category']} {saved['size']}".strip()))
                continue
            for f in RESTORED_FIELDS:
                if f not in saved or it.get(f) == saved[f]:
                    continue
                if f == "key" and any(o["key"] == saved["key"] and o["id"] != it["id"] for o in lines.values()):
                    raise stock.Refused(409, f"The line {saved['key']} cannot be put back: another line now has that "
                                             "name. Rename it first, then restore again.")
                history.append(stock.history_row(who, "restore", item_key=saved.get("key") or it["key"], item_id=it["id"], field=f,
                                                 old=it.get(f), new=saved[f]))
                it[f] = saved[f]
                fields += 1
        for it in lines.values():
            awaited = sum(stock_orders.outstanding(l) for o in st["orders"].get("orders") or []
                          for l in o["lines"] if l["item_id"] == it["id"])
            if (it.get("on_order") or 0) != awaited:
                history.append(stock.history_row(who, "restore", item_key=it["key"], item_id=it["id"], field="on_order",
                                                 old=it.get("on_order"), new=awaited,
                                                 detail="on order follows the orders still open"))
                it["on_order"] = awaited
        st["suppliers"]["suppliers"] = list(b.get("suppliers") or [])
        st["suppliers"]["next_id"] = max([st["suppliers"].get("next_id") or 1] +
                                         [c.get("id", 0) + 1 for c in st["suppliers"]["suppliers"]])
        history.append(stock.history_row(who, "restore", field="suppliers", detail="restored supplier contacts"))
        st["settings"]["meta"] = dict((b.get("settings") or {}).get("meta") or {})
        history.append(stock.history_row(who, "restore", field="settings", detail="restored settings"))
        reapplied = _reapply_since(st, who, _instant(b["at"]), history)
        history.append(stock.history_row(who, "restore", detail=f"restored backup #{b['id']} from {b['at']}"))
        after = stock.take_snapshot(st, "restore", who, f"restored backup #{b['id']}", prev=pre)
        stock.commit(st, changed={"items", "suppliers", "settings", "alerts"}, history=history, snapshots=[pre, after])
        return {"restored": len(b.get("items") or []), "fields": fields, "reapplied": reapplied,
                "safety_backup_id": safety["id"]}


def _reapply_since(st: dict, who: dict, since, history: list) -> int:
    """The production bookings and day sheets made after the backup, applied
    again by the changes each recorded; the shelf never below 0."""
    lines = st["items"]["items"]
    by_key = {it["key"]: it for it in lines.values()}

    def line_of(ln):
        return lines.get(str(ln.get("item_id"))) or by_key.get(ln.get("item_key"))

    done = 0
    for booking in st["bridge"].get("bookings") or []:
        at = _instant(booking.get("at"))
        if not (since and at and at > since):
            continue
        for ln in booking.get("lines") or []:
            it = line_of(ln)
            if not it:
                continue
            old = it["current"]
            it["current"] = max(0, it["current"] - int(ln.get("current_delta") or 0))
            it["used"] = min(stock.INT_MAX, it["used"] + int(ln.get("used_delta", ln.get("qty")) or 0))
            history.append(stock.history_row(who, "use", item_key=it["key"], item_id=it["id"], field="current", old=old, new=it["current"],
                                             detail=f"re-applied after restore: made {booking.get('order_name') or ''}"))
        done += 1
    for sheet in st["bridge"].get("sheets") or []:
        at = _instant(sheet.get("at"))
        if not (since and at and at > since):
            continue
        for ch in sheet.get("applied") or []:
            it = line_of(ch)
            if not it:
                continue
            old = it["current"]
            it["current"] = max(0, min(stock.INT_MAX, it["current"] + int(ch.get("current_change") or 0)))
            it["used"] = max(0, min(stock.INT_MAX, it["used"] + int(ch.get("used_change") or 0)))
            history.append(stock.history_row(who, "sheet", item_key=it["key"], item_id=it["id"], field="current", old=old, new=it["current"],
                                             detail=f"re-applied after restore: usage sheet {sheet.get('day') or ''}"))
        done += 1
    return done


def nightly_tick(now: datetime = None) -> bool:
    """The first tick of each London day: one snapshot, one backup, old change
    snapshots removed. True when it ran."""
    now = now or datetime.now(timezone.utc)
    if not stock.is_live():
        return False
    today = clock._london_day(now.isoformat())
    with stock._lock:
        st = stock.state()
        if (st["settings"].get("nightly") or {}).get("date") == today:
            return False
        snap = stock.take_snapshot(st, "scheduled", SYSTEM, "nightly")
        st["settings"]["nightly"] = {"date": today, "at": stock.now_iso()}
        stock.commit(st, changed={"settings", "alerts"}, snapshot=snap)
    make_backup(SYSTEM)
    stock_store.prune_change_snapshots((now - timedelta(days=CHANGE_SNAPSHOT_DAYS)).date().isoformat())
    return True


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as sibling.NAME, never a copied name.
from gizmo import team  # noqa: E402
from gizmo import stock_orders  # noqa: E402
