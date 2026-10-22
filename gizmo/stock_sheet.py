"""The stock list itself: listing it, editing a line, counting, adding a
line, and (below) importing and exporting the sheet.

Each change is the stock app's own rule, with these fixes: a line is named
by its id, never its key, so a line whose key carries "|#2" can be edited;
an edit carries what the person saw, and a figure someone else changed in
the meantime is refused rather than overwritten; a changed key writes its
own history line, so a line's history can follow it.
"""
from gizmo import stock, stock_figures


def _view(it: dict) -> dict:
    return stock_figures.item_view(it)


def _line(st: dict, item_id) -> dict:
    try:
        it = (st["items"].get("items") or {}).get(str(int(item_id)))
    except (TypeError, ValueError):
        it = None
    if not it:
        raise stock.Refused(404, "That stock line was not found.")
    return it


def listing() -> dict:
    st = stock.state()
    items = stock.items_in_order(st["items"])
    rows = sorted(items, key=lambda i: (i["category"], i["sub_category"], i["id"]))
    return {"items": [_view(i) for i in rows], "summary": stock_figures.compute_current(items),
            "live": bool(st["settings"].get("live_since"))}


def _usage_row(who: dict, it: dict, drop: int) -> dict:
    """A count that lands lower than the figure means stock left the shelf:
    the drop is usage, so the forecasts and warnings see it."""
    old = it["used"]
    it["used"] += drop
    return stock.history_row(who, "update", item_key=it["key"], field="used", old=old, new=it["used"],
                             detail=f"counted down {drop}, recorded as usage")


def edit(uid: str, item_id, changes: dict, seen: dict, as_count: bool) -> dict:
    with stock._lock:
        st = stock.state()
        it = _line(st, item_id)
        who = stock.actor(uid)
        wanted = {f: stock.coerce(f, v) for f, v in (changes or {}).items() if f in stock.EDITABLE}
        for field in wanted:
            if field not in (seen or {}):
                continue
            try:
                was = stock.coerce(field, seen[field])
            except ValueError:
                was = seen[field]
            if was != it[field]:
                raise stock.Refused(
                    409, f"{stock.FIELD_WORDS[field]} on this line was changed to {it[field]} since you "
                         "opened it, by someone else or another screen. Check it and save again.",
                    {"item": _view(it)})
        rows, before = [], it["current"]
        for field, value in wanted.items():
            if it[field] != value:
                rows.append(stock.history_row(
                    who, "update", item_key=it["key"], field=field, old=it[field], new=value,
                    detail="counted" if (as_count and field == "current") else "manual edit"))
                it[field] = value
        if as_count and "current" in wanted:
            drop = before - it["current"]
            if drop > 0 and it["used"] + drop <= stock.INT_MAX:
                rows.append(_usage_row(who, it, drop))
        new_key = stock.item_key(*(it[f] for f in stock.IDENTITY))
        if any(f in wanted for f in stock.IDENTITY) and new_key != it["key"]:
            if any(o["key"] == new_key and o["id"] != it["id"] for o in st["items"]["items"].values()):
                raise stock.Refused(409, "Another stock line already has that category, colour, size and notes.")
            rows.append(stock.history_row(who, "update", item_key=new_key, field="key", old=it["key"],
                                          new=new_key, detail="renamed"))
            it["key"] = new_key
        if rows:
            it["updated_at"] = stock.now_iso()
            snap = stock.take_snapshot(st, "edit", who, f"edited {it['category']} {it['size']}")
            stock.commit(st, changed={"items", "alerts"}, history=rows, snapshot=snap)
        return {"item": _view(it), "applied": len(rows),
                "summary": stock_figures.compute_current(stock.items_in_order(st["items"]))}


def counts(uid: str, counts: list, as_count: bool = True) -> dict:
    """A screenful of counts in one go: one change, one snapshot."""
    if not isinstance(counts, list) or not counts or len(counts) > 500:
        raise stock.Refused(400, "Send between 1 and 500 counts at a time.")
    with stock._lock:
        st = stock.state()
        who = stock.actor(uid)
        wanted = {}
        for c in counts:
            if not isinstance(c, dict):
                raise stock.Refused(400, "Every count needs a stock line and a figure.")
            wanted[_line(st, c.get("id"))["id"]] = stock.coerce("current", c.get("current"))
        rows, saved = [], 0
        for item_id, value in wanted.items():
            it = st["items"]["items"][str(item_id)]
            if it["current"] == value:
                continue
            old = it["current"]
            it["current"] = value
            it["updated_at"] = stock.now_iso()
            saved += 1
            rows.append(stock.history_row(who, "update", item_key=it["key"], field="current", old=old, new=value,
                                          detail="counted" if as_count else "manual edit"))
            if as_count and value < old and it["used"] + (old - value) <= stock.INT_MAX:
                rows.append(_usage_row(who, it, old - value))
        if saved:
            snap = stock.take_snapshot(st, "edit", who, f"counted {saved} line(s)")
            stock.commit(st, changed={"items", "alerts"}, history=rows, snapshot=snap)
        return {"saved": saved, "items": [_view(st["items"]["items"][str(i)]) for i in wanted],
                "summary": stock_figures.compute_current(stock.items_in_order(st["items"]))}


_NEW_LINE = {"sub_category": "", "size": "", "notes": "", "written_off": False, "barcode": "", "supplier": "",
             "currency": "", "unit_cost": None, "unit_cost_gbp": 0.0, "start": 0, "received": 0, "used": 0,
             "current": 0, "reorder_point": 0, "reorder_qty": 0, "on_order": 0}


def new_item(uid: str, fields: dict) -> dict:
    wanted = {f: stock.coerce(f, v) for f, v in (fields or {}).items() if f in stock.EDITABLE}
    category = (wanted.get("category") or "").strip()
    if not category:
        raise stock.Refused(400, "A stock line needs a category.")
    with stock._lock:
        st = stock.state()
        who = stock.actor(uid)
        key = stock.item_key(category, wanted.get("sub_category", ""), wanted.get("size", ""),
                             wanted.get("notes", ""))
        if any(o["key"] == key for o in st["items"]["items"].values()):
            raise stock.Refused(409, "A stock line with that category, colour, size and notes already exists.")
        doc = st["items"]
        now = stock.now_iso()
        it = dict(_NEW_LINE, **wanted, id=doc.get("next_id") or 1, key=key, created_at=now, updated_at=now)
        doc["items"][str(it["id"])] = it
        doc["next_id"] = it["id"] + 1
        row = stock.history_row(who, "create", item_key=key, detail=f"new item {category} {wanted.get('size', '')}")
        snap = stock.take_snapshot(st, "edit", who, f"added {category} {wanted.get('size', '')}")
        stock.commit(st, changed={"items", "alerts"}, history=[row], snapshot=snap)
        return {"item": _view(it), "summary": stock_figures.compute_current(stock.items_in_order(doc))}
