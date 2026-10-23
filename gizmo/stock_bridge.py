"""The production link's rules in the stock area: the glass an order
consumes, booked when it is marked made; the day's usage sheet; the gobo
lines matched to stock lines; the rulings that settle a line it cannot.

The stock app's own rules, word for word (its app.py /api/sync/*):
- one booking per order: marking made again reverses the earlier booking
  first, un-making reverses it, and neither can count twice;
- the shelf never goes below 0, but the usage counts in full, and the shelf
  that was short is said;
- a booking made in a quarter now closed had its usage banked at the close:
  re-applying or reversing it moves the shelf only;
- a line with a note, an unreadable quantity or one out of bounds is parked
  for a ruling, never guessed; a ruling is remembered for Mono, HM and Ring
  lines (they name their glass), never for Colour (which does not);
- matching: a ruling first (by the line's id, then its name), else Mono and
  HM to their glass by size, Ring to Rings by finished diameter; exactly
  (within 0.001), or the single line within 0.2; a line with no notes first,
  then the lowest id. Which glass Mono and HM are is the stock app's own
  rule, carried by the move into the stock sheet's settings
  (`glass_families`), so no glass or supplier is named in this public code;
  without it those lines park for a ruling.

Every change goes through stock.commit with its history lines and a
snapshot, recorded under the account that made it.
"""
import math
from datetime import datetime, timezone

from gizmo import stock

LINES_MAX = 200
SHEET_LINES_MAX = 100
SHEET_ORDERS_MAX = 300
QTY_MAX = 10000
REMEMBERED = ("mono", "hm", "ring")
PRODUCTION = {"user": "Production", "person": None}


def _who(uid):
    return stock.actor(uid) if uid else PRODUCTION


def _instant(iso):
    try:
        t = datetime.fromisoformat(str(iso))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _line_by_id_or_key(st: dict, item_id, key):
    lines = st["items"]["items"]
    it = lines.get(str(item_id)) if item_id else None
    if it is None and key:
        it = next((x for x in lines.values() if x["key"] == key), None)
    return it


def _ruled_line(st: dict, alias: dict):
    """A ruling's line: by its id first (a rename rewrites the name), and
    only a live one."""
    it = _line_by_id_or_key(st, alias.get("item_id"), alias.get("item_key"))
    return it if (it and not it["written_off"]) else None


def match(st: dict, family: str, size: str):
    alias = next((a for a in st["bridge"].get("aliases") or [] if a["alias"] == f"{family}|{size}"), None)
    if alias:
        it = _ruled_line(st, alias)
        if it:
            return it
    try:
        want = float(size)
    except (TypeError, ValueError):
        return None
    fam = (family or "").strip().lower()
    live = [it for it in st["items"]["items"].values() if not it["written_off"]]
    if fam == "ring":
        candidates, size_of = [it for it in live if it["category"] == "Rings"], (lambda it: it["sub_category"])
    else:
        sub = (st["settings"].get("glass_families") or {}).get(fam)
        if not sub:
            return None
        candidates = [it for it in live if it["category"] == "Glass" and it["sub_category"] == sub]
        size_of = lambda it: it["size"]    # noqa: E731
    exact, near = [], []
    for it in candidates:
        try:
            diff = abs(float(size_of(it)) - want)
        except (TypeError, ValueError):
            continue
        if diff < 0.001:
            exact.append(it)
        elif diff <= 0.2:
            near.append(it)
    hits = exact or (near if len(near) == 1 else [])
    if not hits:
        return None
    hits.sort(key=lambda x: (bool(x["notes"]), x["id"]))
    return hits[0]


def _open_from(st: dict):
    open_ = [p for p in st["periods"].get("periods") or [] if p.get("closed_at") is None]
    if not open_:
        return None
    return max((_instant(p["opened_at"]) for p in open_ if _instant(p["opened_at"])), default=None)


def _in_open_quarter(st: dict, at) -> bool:
    opened, when = _open_from(st), _instant(at)
    if not opened or not when:
        return True
    return when >= opened


def _apply(st: dict, who: dict, it: dict, qty: int, order_name: str, history: list, book_used: bool = True) -> dict:
    """Book qty as used, as counting down does; the shelf floored at 0."""
    old = it["current"]
    take = min(max(0, it["current"]), qty)
    it["current"] -= take
    if book_used:
        it["used"] = min(stock.INT_MAX, it["used"] + qty)
    short = qty - take
    history.append(stock.history_row(
        who, "use", item_key=it["key"], item_id=it["id"], field="current", old=old, new=it["current"],
        detail=(f"made {order_name} · used {qty}" + ("" if book_used else " · usage already banked last quarter")
                + (f" · stock only had {take}" if short else ""))[:480]))
    return {"item_id": it["id"], "item_key": it["key"], "qty": qty, "current_delta": take,
            "used_delta": qty if book_used else 0}


def _reverse(st: dict, who: dict, booking: dict, history: list) -> int:
    """Put back exactly what a booking took: the shelf always, the usage
    only when the booking belongs to the open quarter."""
    same = _in_open_quarter(st, booking.get("at"))
    restored = 0
    for ln in booking.get("lines") or []:
        it = _line_by_id_or_key(st, ln.get("item_id"), ln.get("item_key"))
        if not it:
            continue
        old = it["current"]
        it["current"] = min(stock.INT_MAX, it["current"] + int(ln.get("current_delta") or 0))
        if same:
            it["used"] = max(0, it["used"] - int(ln.get("used_delta", ln.get("qty")) or 0))
        restored += int(ln.get("qty") or 0)
        history.append(stock.history_row(
            who, "use_undo", item_key=it["key"], item_id=it["id"], field="current", old=old, new=it["current"],
            detail=(f"un-made {booking.get('order_name') or ''} · returned {ln.get('qty')}"
                    + ("" if same else " · usage stays banked in the closed quarter"))[:480]))
    return restored


def _next_id(bridge: dict, name: str) -> int:
    ids = bridge.setdefault("next_ids", {})
    n = ids.get(name) or (max((r["id"] for r in bridge.get(name) or []), default=0) + 1)
    ids[name] = n + 1
    return n


def _park(st: dict, order_id: str, order_name: str, alias: str, qty: int, note: str) -> None:
    bridge = st["bridge"]
    bridge.setdefault("parked", []).append({"id": _next_id(bridge, "parked"), "order_id": order_id,
                                            "order_name": order_name, "alias": alias, "qty": qty, "note": note,
                                            "at": stock.now_iso()})


def _order_id(order_id) -> str:
    oid = stock.clean_text(order_id, 40)
    if not oid or not oid.isdigit():
        raise stock.Refused(400, "The order must be a Shopify order number.")
    return oid


def _drop_order(st: dict, order_id: str) -> None:
    bridge = st["bridge"]
    bridge["parked"] = [p for p in bridge.get("parked") or [] if p["order_id"] != order_id]
    bridge["bookings"] = [b for b in bridge.get("bookings") or [] if b["order_id"] != order_id]


def reverse(uid, order_id) -> dict:
    """Un-making an order: what its booking took comes back."""
    oid = _order_id(order_id)
    with stock._lock:
        st = stock.state()
        prior = next((b for b in st["bridge"].get("bookings") or [] if b["order_id"] == oid), None)
        if not prior:
            return {"ok": True, "reversed": 0}      # never booked, or already reversed
        who, history = _who(uid), []
        restored = _reverse(st, who, prior, history)
        _drop_order(st, oid)
        snap = stock.take_snapshot(st, "edit", who, f"un-made {prior.get('order_name') or '#' + oid}")
        stock.commit(st, changed={"items", "bridge", "alerts"}, history=history, snapshot=snap)
        return {"ok": True, "reversed": restored}


def book(uid, order_id, order_name, lines) -> dict:
    """Marking an order made: its glass lines booked, replacing any earlier
    booking for the order, lines it cannot place parked."""
    oid = _order_id(order_id)
    name = stock.clean_text(order_name, 80) or ("#" + oid)
    if not isinstance(lines, list) or len(lines) > LINES_MAX:
        raise stock.Refused(400, "An order can send at most 200 glass lines.")
    with stock._lock:
        st = stock.state()
        who, history = _who(uid), []
        prior = next((b for b in st["bridge"].get("bookings") or [] if b["order_id"] == oid), None)
        book_used = True
        if prior:
            # A booking from a closed quarter had its usage banked at the close.
            book_used = _in_open_quarter(st, prior.get("at"))
            _reverse(st, who, prior, history)
            _drop_order(st, oid)
        applied, parked, units = [], 0, 0
        for ln in lines:
            if not isinstance(ln, dict):
                continue
            family, size = stock.clean_text(ln.get("family"), 60), stock.clean_text(ln.get("size"), 40)
            note = stock.clean_text(ln.get("note"), 300)
            try:
                q = float(ln.get("qty"))
                if not math.isfinite(q):
                    raise ValueError
                qty = int(round(q))
            except (TypeError, ValueError, OverflowError):
                _park(st, oid, name, f"{family}|{size}", 0, "unreadable quantity")
                parked += 1
                continue
            if qty <= 0 or qty > QTY_MAX:
                _park(st, oid, name, f"{family}|{size}", max(0, min(qty, QTY_MAX)), "quantity out of bounds")
                parked += 1
                continue
            it = None if note else match(st, family, size)
            if it is not None:
                applied.append(_apply(st, who, it, qty, name, history, book_used=book_used))
                units += qty
            else:
                _park(st, oid, name, f"{family}|{size}", qty, note or "no matching stock item")
                parked += 1
        bridge = st["bridge"]
        bridge.setdefault("bookings", []).append({"id": _next_id(bridge, "bookings"), "order_id": oid,
                                                  "order_name": name, "at": stock.now_iso(), "lines": applied})
        history.append(stock.history_row(who, "use", field="summary", detail=(
            f"made {name} · {units} blank(s) across {len(applied)} item(s)"
            + (f" · {parked} line(s) parked unmatched" if parked else ""))[:480]))
        snap = stock.take_snapshot(st, "edit", who, f"made {name}")
        stock.commit(st, changed={"items", "bridge", "alerts"}, history=history, snapshot=snap)
        return {"ok": True, "booked": len(applied), "units": units, "parked": parked}


def _sheet_reverse(st: dict, who: dict, sheet: dict, history: list) -> None:
    """Undo exactly what a day sheet applied: the shelf always, the usage
    only when the sheet belongs to the open quarter."""
    same = _in_open_quarter(st, sheet.get("at"))
    for ch in sheet.get("applied") or []:
        it = _line_by_id_or_key(st, ch.get("item_id"), ch.get("item_key"))
        if not it:
            continue
        old = it["current"]
        it["current"] = max(0, min(stock.INT_MAX, it["current"] - int(ch.get("current_change") or 0)))
        if same:
            it["used"] = max(0, min(stock.INT_MAX, it["used"] - int(ch.get("used_change") or 0)))
        history.append(stock.history_row(
            who, "sheet_undo", item_key=it["key"], item_id=it["id"], field="current", old=old, new=it["current"],
            detail=(f"usage sheet {sheet.get('day')} replaced · adjustment undone"
                    + ("" if same else " · usage stays banked in the closed quarter"))[:480]))


def usage_sheet(uid, day, order_ids, lines) -> dict:
    """A day's final figures, applied as the difference from what that
    day's bookings already recorded; one sheet per day, a re-send replacing
    the earlier one. Each line answers with its own status."""
    day = stock.clean_text(day, 10)
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        raise stock.Refused(400, "The day must be a date written YYYY-MM-DD.") from None
    if not isinstance(order_ids, list) or len(order_ids) > SHEET_ORDERS_MAX:
        raise stock.Refused(400, "A day sheet can name at most 300 orders.")
    ids = [stock.clean_text(i, 40) for i in order_ids if stock.clean_text(i, 40).isdigit()]
    if not isinstance(lines, list) or not lines or len(lines) > SHEET_LINES_MAX:
        raise stock.Refused(400, "A day sheet needs between 1 and 100 lines.")
    with stock._lock:
        st = stock.state()
        who, history, bridge = _who(uid), [], st["bridge"]
        prior = next((s for s in bridge.get("sheets") or [] if s["day"] == day), None)
        if prior:
            _sheet_reverse(st, who, prior, history)
            bridge["sheets"] = [s for s in bridge["sheets"] if s["day"] != day]
        booked = {}
        for b in bridge.get("bookings") or []:
            if b["order_id"] in ids:
                for ln in b.get("lines") or []:
                    if ln.get("item_id"):
                        booked[ln["item_id"]] = booked.get(ln["item_id"], 0) + int(ln.get("qty") or 0)
        results, applied, kept = [], [], []
        for ln in lines:
            if not isinstance(ln, dict):
                continue
            family, size = stock.clean_text(ln.get("family"), 60), stock.clean_text(ln.get("size"), 40)
            try:
                est = max(0, min(100000, int(round(float(ln.get("estimated") or 0)))))
            except (TypeError, ValueError, OverflowError):
                est = 0
            try:
                f = float(ln.get("final"))
                if not math.isfinite(f):
                    raise ValueError
                final = int(round(f))
            except (TypeError, ValueError, OverflowError):
                results.append({"family": family, "size": size, "estimated": est, "status": "bad_quantity"})
                continue
            if final < 0 or final > QTY_MAX:
                results.append({"family": family, "size": size, "estimated": est, "final": final,
                                "status": "bad_quantity"})
                continue
            kept.append({"family": family, "size": size, "estimated": est, "final": final})
            it = match(st, family, size)
            if it is None:
                results.append({"family": family, "size": size, "estimated": est, "final": final, "status": "no_item"})
                continue
            already = booked.get(it["id"], 0)
            delta = final - already
            row = {"family": family, "size": size, "estimated": est, "final": final, "already_booked": already,
                   "delta": delta, "item": it["key"]}
            if delta == 0:
                results.append(dict(row, status="matched"))
                continue
            old = it["current"]
            if delta > 0:
                take = min(max(0, it["current"]), delta)
                it["current"] -= take
                it["used"] = min(stock.INT_MAX, it["used"] + delta)
                change = {"item_id": it["id"], "item_key": it["key"], "current_change": -take, "used_change": delta}
                if delta > take:
                    row["short"] = delta - take
            else:
                back = -delta
                it["current"] = min(stock.INT_MAX, it["current"] + back)
                it["used"] = max(0, it["used"] - back)
                change = {"item_id": it["id"], "item_key": it["key"], "current_change": back, "used_change": -back}
            applied.append(change)
            history.append(stock.history_row(
                who, "sheet", item_key=it["key"], item_id=it["id"], field="current", old=old, new=it["current"],
                detail=(f"usage sheet {day}: {family}|{size} final {final}, auto-booked {already}, adjusted {delta:+d}"
                        + (f" · shelf was {row['short']} short" if row.get("short") else ""))[:480]))
            results.append(dict(row, status="adjusted"))
        bridge.setdefault("sheets", []).append({"id": _next_id(bridge, "sheets"), "day": day, "at": stock.now_iso(),
                                                "lines": kept, "applied": applied})
        snap = stock.take_snapshot(st, "edit", who, f"usage sheet {day}") if applied else None
        stock.commit(st, changed={"items", "bridge", "alerts"}, history=history, snapshot=snap)
        return {"ok": True, "day": day, "replaced": bool(prior), "results": results, "adjustments": len(applied)}


# ---- the mapping view and rulings -------------------------------------------------

def catalogue() -> list:
    """Every glass line production can send: read from the size list, as the
    link built it for the stock app."""
    return stock_link._zeta_catalog_combos()


def _size_sort(v: str):
    try:
        return (0, float(v))
    except (TypeError, ValueError):
        return (1, 0.0)


def _options(st: dict) -> list:
    live = [it for it in stock.items_in_order(st["items"]) if not it["written_off"]]
    opts = [{"id": it["id"], "key": it["key"], "name": f"{it['sub_category']} {it['size']}".strip()}
            for it in live if it["category"] == "Glass"]
    opts += [{"id": it["id"], "key": it["key"], "name": f"Ring {it['sub_category']} (glass {it['size']})".strip()}
             for it in live if it["category"] == "Rings"]
    return sorted(opts, key=lambda o: o["name"])


def mapping() -> dict:
    """The whole translation, one row per line production can send: books
    on its own (auto), ruled by hand, decided per order (Colour), or no line
    (unmapped); with the parked lines not in the catalogue."""
    st = stock.state()
    combos = [dict(c) for c in catalogue()]
    seen = {(c["family"], c["size"]) for c in combos}
    parked_counts = {}
    for p in st["bridge"].get("parked") or []:
        fam, _, size = p["alias"].partition("|")
        if (fam, size) not in seen:
            seen.add((fam, size))
            combos.append({"family": fam, "size": size})
        parked_counts[p["alias"]] = parked_counts.get(p["alias"], 0) + 1
    aliases = {a["alias"]: a for a in st["bridge"].get("aliases") or []}
    rows = []
    for c in sorted(combos, key=lambda x: (x["family"], _size_sort(x["size"]))):
        key = f"{c['family']}|{c['size']}"
        ruled_line = _ruled_line(st, aliases[key]) if key in aliases else None
        target = ruled_line or match(st, c["family"], c["size"])
        per_order = c["family"].strip().lower() not in REMEMBERED
        status = "ruled" if ruled_line else "per_order" if per_order else "auto" if target is not None else "unmapped"
        shown = target if (target and (not per_order or ruled_line)) else None
        rows.append({"family": c["family"], "size": c["size"], "alias": key, "status": status,
                     "target": {"id": shown["id"], "key": shown["key"],
                                "name": f"{shown['sub_category']} {shown['size']}".strip()} if shown else None,
                     "parked": parked_counts.get(key, 0)})
    return {"rows": rows, "options": _options(st)}


def parked() -> dict:
    st = stock.state()
    rows = sorted(st["bridge"].get("parked") or [], key=lambda p: (p.get("at") or "", p["id"]))
    return {"parked": [{k: p.get(k) for k in ("id", "order_name", "alias", "qty", "note")} for p in rows],
            "options": _options(st),
            "aliases": [{"alias": a["alias"], "item_id": a.get("item_id"), "item_key": a.get("item_key")}
                        for a in st["bridge"].get("aliases") or []]}


def map_line(uid, alias, item_id, parked_id=None) -> dict:
    """A ruling: this production line is that stock line. It books the
    parked lines with the alias (a Colour ruling, only the one chosen), adds
    them to their orders' bookings so un-making reverses them, and is
    remembered for Mono, HM and Ring lines."""
    alias = stock.clean_text(alias, 160)
    with stock._lock:
        st = stock.state()
        it = st["items"]["items"].get(str(item_id)) if str(item_id or "").isdigit() else None
        if not alias or not it:
            raise stock.Refused(404, "That production line or stock line was not found.")
        if it["written_off"]:
            raise stock.Refused(400, "That stock line is written off; choose a live one.")
        who, history, bridge = _who(uid), [], st["bridge"]
        remember = alias.split("|", 1)[0].strip().lower() in REMEMBERED
        if not remember:
            # A colour line names no glass: each is ruled for its own order,
            # so a ruling without its parked line would book every order's.
            if parked_id in (None, ""):
                raise stock.Refused(400, "Choose the parked line this is for: a colour line is ruled one order at a time.")
            if not any(p["alias"] == alias and str(p["id"]) == str(parked_id) for p in bridge.get("parked") or []):
                raise stock.Refused(400, "That parked line was not found; it may have been ruled already.")
        if remember:
            row = next((a for a in bridge.setdefault("aliases", []) if a["alias"] == alias), None)
            if row:
                row.update(item_id=it["id"], item_key=it["key"])
            else:
                bridge["aliases"].append({"id": _next_id(bridge, "aliases"), "alias": alias, "item_id": it["id"],
                                          "item_key": it["key"], "at": stock.now_iso()})
            history.append(stock.history_row(
                who, "update", item_key=it["key"], item_id=it["id"], field="gizmo_alias", new=alias,
                detail=f"gobo line '{alias}' now books as {it['sub_category']} {it['size']}"))
            parked_id = None
        chosen = [p for p in bridge.get("parked") or [] if p["alias"] == alias
                  and (parked_id is None or str(p["id"]) == str(parked_id))]
        booked = 0
        for p in chosen:
            if p["qty"] > 0:
                applied = _apply(st, who, it, p["qty"], p.get("order_name") or "", history)
                booking = next((b for b in bridge.get("bookings") or [] if b["order_id"] == p["order_id"]), None)
                if booking:
                    booking.setdefault("lines", []).append(applied)
                booked += p["qty"]
        gone = {p["id"] for p in chosen}
        bridge["parked"] = [p for p in bridge.get("parked") or [] if p["id"] not in gone]
        snap = stock.take_snapshot(st, "edit", who, f"mapped gobo line {alias}") if booked else None
        stock.commit(st, changed={"items", "bridge", "alerts"}, history=history, snapshot=snap)
        return {"ok": True, "booked_units": booked}


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as sibling.NAME, never a copied name.
from gizmo import stock_link  # noqa: E402
