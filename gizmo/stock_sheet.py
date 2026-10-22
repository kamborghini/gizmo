"""The stock list itself: listing it, editing a line, counting, adding a
line, and (below) importing and exporting the sheet.

Each change is the stock app's own rule, with these fixes: a line is named
by its id, never its key, so a line whose key carries "|#2" can be edited;
an edit carries what the person saw, and a figure someone else changed in
the meantime is refused rather than overwritten; a changed key writes its
own history line, so a line's history can follow it.
"""
import math
import re

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
        rows, before, renamed = [], it["current"], False
        for field, value in wanted.items():
            if it[field] != value:
                renamed = renamed or field in stock.IDENTITY
                rows.append(stock.history_row(
                    who, "update", item_key=it["key"], field=field, old=it[field], new=value,
                    detail="counted" if (as_count and field == "current") else "manual edit"))
                it[field] = value
        if as_count and "current" in wanted:
            drop = before - it["current"]
            if drop > 0 and it["used"] + drop <= stock.INT_MAX:
                rows.append(_usage_row(who, it, drop))
        new_key = stock.item_key(*(it[f] for f in stock.IDENTITY))
        # Only a real change to its name renames a line: an unchanged size sent
        # with the row would otherwise "rename" a |#2 line onto its twin.
        if renamed and new_key != it["key"]:
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


# ---- import and export, in the stock sheet's own layout (flaw 5) -------------
# The shop's spreadsheet: a quarter label on the first row, a header on the
# third, then a row per line, a Totals row at the end. Its columns, by place:
SHEET_HEADER = ["Category", "Colour / Type", "Size", "Notes", "Start", "Received", "Used", "Current",
                "Used Value", "Start Value", "Current Value", "Unit Cost", "Currency", "Supplier",
                "Unit Cost GBP", "Stock Purchased", "Delivered", "Invoice No", "Date", "Written off"]
IMPORT_MAX = 5000
_LEADING_NUMBER = re.compile(r"\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)")


def _parse_float(text: str):
    """JavaScript's parseFloat, as the stock app read its sheet: the number
    at the start of the text, or None."""
    m = _LEADING_NUMBER.match(text)
    return float(m.group(1)) if m else None


def _whole(cell: str) -> int:
    text = cell.replace(",", "").strip()
    n = _parse_float(text) if text else None
    return math.trunc(n) if n is not None else 0


def _number(cell: str):
    text = cell.replace(",", "").strip()
    return _parse_float(text) if text else None


def _money(cell: str):
    """A pounds figure as the sheet writes it ("£1,062.72"). Kept to four
    places, as costs are stored, so an exported cost comes back unchanged."""
    text = cell.replace("£", "").replace(",", "").strip()
    if not text or text == "-":
        return 0
    n = _parse_float(text)
    return n if n is not None else 0


def _unguard(cell: str) -> str:
    """Take off the quote export puts before a cell a spreadsheet would run."""
    return cell[1:] if len(cell) > 1 and cell[0] == "'" and cell[1] in "=+-@" else cell


def _parse_csv(text: str) -> list:
    """The stock app's CSV reader, quote for quote."""
    rows, row, cur, quoted, i = [], [], "", False, 0
    while i < len(text):
        ch = text[i]
        if quoted:
            if ch == '"':
                if i + 1 < len(text) and text[i + 1] == '"':
                    cur += '"'
                    i += 1
                else:
                    quoted = False
            else:
                cur += ch
        elif ch == '"':
            quoted = True
        elif ch == ",":
            row.append(cur)
            cur = ""
        elif ch == "\n":
            row.append(cur)
            rows.append(row)
            row, cur = [], ""
        elif ch != "\r":
            cur += ch
        i += 1
    if cur or row:
        row.append(cur)
        rows.append(row)
    return rows


def read_csv(text: str) -> list:
    """The lines of a stock sheet, read as the stock app read them. A written
    off line is the last column's yes when the sheet has that column (export
    writes it), else "written off" in its notes, as the shop's sheet says it."""
    raw = _parse_csv(text or "")
    if len(raw) < 4:
        raise stock.Refused(400, "That file is not the stock sheet: it needs a quarter label, a header, "
                                 "then a row for each line.")
    out = []
    for r in raw[3:]:
        if not r or not (r[0] or "").strip():
            continue
        if r[0].strip().lower() == "totals":
            continue

        def cell(n):
            return _unguard(r[n] if n < len(r) else "")
        notes = cell(3).strip()
        flag = cell(19).strip().lower()
        out.append({
            "category": cell(0).strip(), "sub_category": cell(1).strip(), "size": cell(2).strip(), "notes": notes,
            "written_off": flag in ("yes", "y", "true", "1") if flag else bool(re.search("written off", notes, re.I)),
            "start": _whole(cell(4)), "received": _whole(cell(5)), "used": _whole(cell(6)), "current": _whole(cell(7)),
            "unit_cost": _number(cell(11)), "currency": cell(12).strip(), "supplier": cell(13).strip(),
            "unit_cost_gbp": _money(cell(14))})
    return out


def _whole_field(field: str, value) -> int:
    """The stock app's import rule for a whole number (blank is 0)."""
    if value in (None, ""):
        return 0
    return stock.coerce(field, value)


def _cost_field(field: str, value):
    if value in (None, ""):
        return None
    return stock.coerce(field, value)


def _plan_import(st: dict, rows: list):
    """What importing `rows` would do, the stock app's apply_rows step by step:
    the lines it would add and every field it would change."""
    if not isinstance(rows, list):
        raise stock.Refused(400, "That sheet could not be read.")
    if len(rows) > IMPORT_MAX:
        raise stock.Refused(400, "A sheet can have at most 5,000 lines.")
    existing = {it["key"]: it for it in st["items"]["items"].values()}
    batch, creates, changes = set(), [], []
    for r in rows:
        def text(f):
            return stock.clean_text(r.get(f, ""), stock.TEXT_FIELDS.get(f, 120))
        if not text("category"):
            continue
        base = stock.item_key(text("category"), text("sub_category"), text("size"), text("notes"))
        key, n = base, 2
        while key in batch:                      # the same line twice in one sheet stays two lines
            key, n = f"{base}|#{n}", n + 1
        batch.add(key)
        fields = {"category": text("category"), "sub_category": text("sub_category"), "size": text("size"),
                  "notes": text("notes"), "written_off": stock.to_bool(r.get("written_off")),
                  "supplier": text("supplier"), "currency": text("currency"),
                  "unit_cost": _cost_field("unit_cost", r.get("unit_cost")),
                  "unit_cost_gbp": _cost_field("unit_cost_gbp", r.get("unit_cost_gbp")) or 0.0,
                  "start": _whole_field("start", r.get("start")), "received": _whole_field("received", r.get("received")),
                  "used": _whole_field("used", r.get("used")), "current": _whole_field("current", r.get("current"))}
        it = existing.get(key)
        if it is None:
            creates.append((key, fields))
        else:
            changes.extend((it, f, it[f], v) for f, v in fields.items() if it[f] != v)
    return creates, changes


def import_preview(text: str) -> dict:
    rows = read_csv(text)
    creates, changes = _plan_import(stock.state(), rows)
    return {"rows": len(rows),
            "creates": [{"category": f["category"], "sub_category": f["sub_category"], "size": f["size"],
                         "written_off": f["written_off"]} for _key, f in creates],
            "changes": [{"id": it["id"], "name": stock_figures.item_name(it), "field": f, "from": old, "to": new}
                        for it, f, old, new in changes]}


def import_apply(uid: str, text: str) -> dict:
    rows = read_csv(text)
    with stock._lock:
        st = stock.state()
        who = stock.actor(uid)
        creates, changes = _plan_import(st, rows)
        doc, now, history = st["items"], stock.now_iso(), []
        for key, fields in creates:
            it = dict(_NEW_LINE, **fields, id=doc.get("next_id") or 1, key=key, created_at=now, updated_at=now)
            doc["items"][str(it["id"])] = it
            doc["next_id"] = it["id"] + 1
            history.append(stock.history_row(who, "create", item_key=key,
                                             detail=f"import: {fields['category']} {fields['size']}".strip()))
        for it, field, old, new in changes:
            it[field] = new
            it["updated_at"] = now
            history.append(stock.history_row(who, "import", item_key=it["key"], field=field, old=old, new=new))
        snap = stock.take_snapshot(st, "import", who, f"{len(creates)} created, {len(changes)} fields updated")
        stock.commit(st, changed={"items", "alerts"}, history=history, snapshot=snap)
        return {"created": len(creates), "updated_fields": len(changes),
                "summary": stock_figures.compute_current(stock.items_in_order(doc))}


def _guard_cell(text: str) -> str:
    """A cell a spreadsheet would run as a formula is written as text."""
    return "'" + text if text and text[0] in "=+-@" else text


def _csv_cell(value) -> str:
    text = "" if value is None else str(value)
    return '"' + text.replace('"', '""') + '"' if any(c in text for c in ',"\n') else text


def export_csv(ids) -> dict:
    """The lines asked for (every line when none are), in the sheet's own
    layout, with the written-off column the import reads back."""
    st = stock.state()
    items = stock.items_in_order(st["items"])
    if ids:
        wanted = {int(i) for i in ids if str(i).strip().lstrip("-").isdigit()}
        items = [i for i in items if i["id"] in wanted]
    open_q = [p for p in st["periods"].get("periods") or [] if p.get("closed_at") is None]
    rows = [[open_q[-1]["label"] if open_q else "Stock"], [], SHEET_HEADER]
    totals = [0, 0, 0, 0, 0.0, 0.0, 0.0]
    for it in items:
        v = stock_figures.item_view(it)
        figures = [it["start"], it["received"], it["used"], it["current"], v["used_value"], v["start_value"],
                   v["current_value"]]
        totals = [a + b for a, b in zip(totals, figures)]
        rows.append([_guard_cell(it["category"]), _guard_cell(it["sub_category"]), _guard_cell(it["size"]),
                     _guard_cell(it["notes"])] + figures +
                    [it["unit_cost"], _guard_cell(it["currency"] or ""), _guard_cell(it["supplier"] or ""),
                     it["unit_cost_gbp"], "", "", "", "", "yes" if it["written_off"] else "no"])
    rows.append(["Totals", "", "", ""] + totals[:4] + [round(t, 2) for t in totals[4:]])
    return {"csv": "\n".join(",".join(_csv_cell(c) for c in r) for r in rows) + "\n",
            "filename": "stock_export.csv"}
