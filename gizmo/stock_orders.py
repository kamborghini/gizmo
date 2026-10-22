"""Buying stock: orders placed with suppliers, what needs reordering, the
suppliers themselves, and (below) receiving deliveries.

The stock app kept no orders: placing one only added to each line's
on-order figure, so an order left no record but a number (flaw 7). Here
every order is kept: its supplier, lines, quantities, prices, reference,
who placed it and when, and what has been received against each line. A
line's on-order figure always equals what its open orders still await;
placing, receiving, clearing and undoing keep the two together.

Suppliers' contact details are business data behind the stock tab only,
and never written into the history (flaw 2: editing them together keeps
every field the request leaves out).
"""
import re

from gizmo import stock, stock_figures

LINES_MAX = 300
LEVELS_MAX = 1000
CONTACTS_MAX = 200
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _line(st: dict, item_id) -> dict:
    try:
        it = (st["items"].get("items") or {}).get(str(int(item_id)))
    except (TypeError, ValueError):
        it = None
    if not it:
        raise stock.Refused(404, "That stock line was not found.")
    return it


def _qty(value) -> int:
    """A quantity to order or receive: a whole number above 0."""
    try:
        q = int(round(float(value)))
    except (TypeError, ValueError, OverflowError):
        raise stock.Refused(400, "Every quantity must be a number.") from None
    if q <= 0:
        raise stock.Refused(400, "Quantities must be above 0.")
    return q


def outstanding(line: dict) -> int:
    return max(0, line["qty"] - line.get("received", 0) - line.get("cleared", 0))


def _summary(st: dict) -> dict:
    return stock_figures.compute_current(stock.items_in_order(st["items"]))


# ---- placing and clearing orders ---------------------------------------------

def place(uid: str, supplier, reference, currency, lines) -> dict:
    if not isinstance(lines, list) or not lines or len(lines) > LINES_MAX:
        raise stock.Refused(400, "An order needs between 1 and 300 lines.")
    supplier = stock.clean_text(supplier, 120)
    reference = stock.clean_text(reference, 60)
    with stock._lock:
        st = stock.state()
        who = stock.actor(uid)
        wanted, prices = {}, {}
        for ln in lines:
            if not isinstance(ln, dict):
                raise stock.Refused(400, "Every order line needs a stock line and a quantity.")
            it = _line(st, ln.get("id"))
            wanted[it["id"]] = wanted.get(it["id"], 0) + _qty(ln.get("qty"))
            if ln.get("unit_cost") not in (None, ""):
                prices[it["id"]] = stock.coerce("unit_cost", ln.get("unit_cost"))
        items = st["items"]["items"]
        if any((items[str(i)]["on_order"] or 0) + q > stock.INT_MAX for i, q in wanted.items()):
            raise stock.Refused(400, "That quantity is too large.")
        orders = st["orders"]
        order = {"id": orders.get("next_id") or 1, "supplier": supplier, "reference": reference,
                 "currency": stock.clean_text(currency, 8), "at": stock.now_iso(), "by": who["user"],
                 "person": who["person"], "before_move": False, "lines": []}
        history = []
        for item_id, q in wanted.items():
            it = items[str(item_id)]
            old = it["on_order"] or 0
            it["on_order"] = old + q
            order["lines"].append({"item_id": item_id, "item_key": it["key"], "qty": q,
                                   "unit_cost": prices.get(item_id), "unit_cost_gbp": it["unit_cost_gbp"],
                                   "received": 0, "cleared": 0, "receipts": []})
            history.append(stock.history_row(
                who, "ordered", item_key=it["key"], field="on_order", old=old, new=it["on_order"],
                detail=f"ordered {q}" + (f" from {supplier}" if supplier else "") + (f" · ref {reference}" if reference else "")))
        orders.setdefault("orders", []).append(order)
        orders["next_id"] = order["id"] + 1
        stock.commit(st, changed={"items", "orders"}, history=history)
        return {"order": order, "ordered": len(wanted), "units": sum(wanted.values()),
                "items": [stock_figures.item_view(items[str(i)]) for i in wanted], "summary": _summary(st)}


def clear(uid: str, item_id) -> dict:
    """An on-order quantity that never came (or was logged in error)."""
    with stock._lock:
        st = stock.state()
        it = _line(st, item_id)
        if not it["on_order"]:
            raise stock.Refused(400, "Nothing is on order for that line.")
        who = stock.actor(uid)
        old = it["on_order"]
        it["on_order"] = 0
        for order in st["orders"].get("orders") or []:
            for line in order["lines"]:
                if line["item_id"] == it["id"]:
                    line["cleared"] = line.get("cleared", 0) + outstanding(line)
        row = stock.history_row(who, "ordered", item_key=it["key"], field="on_order", old=old, new=0,
                                detail="cleared outstanding order")
        stock.commit(st, changed={"items", "orders"}, history=[row])
        return {"item": stock_figures.item_view(it), "summary": _summary(st)}


def _shown(order: dict) -> dict:
    lines = [dict(l, outstanding=outstanding(l)) for l in order["lines"]]
    return dict(order, lines=lines, open=any(l["outstanding"] for l in lines))


def orders(open_only: bool = False) -> dict:
    """Open orders oldest first, then (unless only the open ones are asked
    for) the latest fifty done."""
    shown = [_shown(o) for o in stock.state()["orders"].get("orders") or []]
    open_ = sorted((o for o in shown if o["open"]), key=lambda o: o["at"])
    done = [] if open_only else sorted((o for o in shown if not o["open"]), key=lambda o: o["at"], reverse=True)[:50]
    return {"orders": open_ + done}


# ---- reordering ----------------------------------------------------------------

def reorder() -> dict:
    return stock_figures.reorder_suggestions(stock.items_in_order(stock.state()["items"]))


def _leads(st: dict) -> dict:
    return {c["supplier"]: (c.get("lead_days") or 0) for c in st["suppliers"].get("suppliers") or []}


def suggest() -> dict:
    st = stock.state()
    return stock_figures.suggest_reorder_points(stock.items_in_order(st["items"]), _leads(st))


def set_levels(uid: str, levels) -> dict:
    if not isinstance(levels, list) or not levels or len(levels) > LEVELS_MAX:
        raise stock.Refused(400, "Send between 1 and 1,000 levels at a time.")
    with stock._lock:
        st = stock.state()
        who = stock.actor(uid)
        plan = {}
        for lv in levels:
            if not isinstance(lv, dict):
                raise stock.Refused(400, "Every level needs a stock line.")
            it = _line(st, lv.get("id"))
            plan[it["id"]] = (stock.coerce("reorder_point", lv.get("reorder_point")),
                              stock.coerce("reorder_qty", lv.get("reorder_qty")))
        history = []
        for item_id, (point, qty) in plan.items():
            it = st["items"]["items"][str(item_id)]
            if (it["reorder_point"], it["reorder_qty"]) == (point, qty):
                continue
            history.append(stock.history_row(
                who, "update", item_key=it["key"], field="reorder_point", old=f"{it['reorder_point']}/{it['reorder_qty']}",
                new=f"{point}/{qty}", detail="reorder level set"))
            it["reorder_point"], it["reorder_qty"] = point, qty
            it["updated_at"] = stock.now_iso()
        if history:
            stock.commit(st, changed={"items"}, history=history)
        return {"updated": len(history), "summary": _summary(st)}


# ---- suppliers -------------------------------------------------------------------

_CONTACT_BLANK = {"email": "", "cc": "", "contact_name": "", "subject": "", "body": "", "lead_days": 0,
                  "min_order": "", "updated_at": None}


def _clean_emails(raw, cap: int = 400) -> str:
    """Copy addresses: only ones that look like addresses, each once."""
    out, seen = [], set()
    for part in re.split(r"[,;]", str(raw or "")):
        e = stock.clean_text(part, 200)
        if e and _EMAIL.match(e) and e.lower() not in seen:
            seen.add(e.lower())
            out.append(e)
    return ", ".join(out)[:cap]


def suppliers() -> dict:
    """Every supplier on the live lines with its saved contact (if any) and
    what is due from it, then saved contacts no line names any more."""
    st = stock.state()
    items = stock.items_in_order(st["items"])
    names = sorted({(i["supplier"] or "Unknown") for i in items if not i["written_off"]}, key=str.lower)
    contacts = {c["supplier"]: c for c in st["suppliers"].get("suppliers") or []}
    due = {s["supplier"]: {"lines": s["lines"], "order_value_gbp": s["order_value_gbp"]}
           for s in stock_figures.reorder_suggestions(items)["suppliers"]}
    rows = []
    for n in names:
        c = contacts.get(n)
        r = dict(c) if c else dict(_CONTACT_BLANK, supplier=n)
        r["has_contact"] = c is not None
        r["due"] = due.get(n, {"lines": 0, "order_value_gbp": 0})
        rows.append(r)
    for n, c in contacts.items():
        if n not in names:
            rows.append(dict(c, has_contact=True, orphan=True, due={"lines": 0, "order_value_gbp": 0}))
    return {"suppliers": rows}


def _apply_contact(st: dict, who: dict, contact: dict) -> tuple:
    """One contact saved into `st`: the fields the request carries replace
    the stored ones, the rest are kept. Returns (contact, created, history row)."""
    if not isinstance(contact, dict):
        raise stock.Refused(400, "Every supplier needs a name.")
    name = stock.clean_text(contact.get("supplier"), 120)
    if not name:
        raise stock.Refused(400, "Every supplier needs a name.")
    doc = st["suppliers"]
    row = next((c for c in doc.setdefault("suppliers", []) if c["supplier"] == name), None)
    created = row is None
    if created:
        row = dict(_CONTACT_BLANK, id=doc.get("next_id") or 1, supplier=name)
        doc["suppliers"].append(row)
        doc["next_id"] = row["id"] + 1
    if "email" in contact:
        email = stock.clean_text(contact.get("email"), 200)
        if email and not _EMAIL.match(email):
            raise stock.Refused(400, f"The email address for {name} does not look right.")
        row["email"] = email
    if "cc" in contact:
        row["cc"] = _clean_emails(contact.get("cc"))
    for field, cap in (("contact_name", 120), ("subject", 300), ("body", 4000), ("min_order", 120)):
        if field in contact:
            row[field] = stock.clean_text(contact.get(field), cap)
    if "lead_days" in contact:
        try:
            days = int(round(float(contact.get("lead_days") or 0)))
        except (TypeError, ValueError, OverflowError):
            days = 0
        row["lead_days"] = max(0, min(365, days))
    row["updated_at"] = stock.now_iso()
    # The action is recorded, never the address: contact details stay out of the history.
    line = stock.history_row(who, "update", field="supplier_contact",
                             detail=f"{'added' if created else 'updated'} email contact for {name}")
    return row, created, line


def save_supplier(uid: str, contact: dict) -> dict:
    with stock._lock:
        st = stock.state()
        row, created, line = _apply_contact(st, stock.actor(uid), contact)
        stock.commit(st, changed={"suppliers"}, history=[line])
        return {"contact": row, "created": created}


def save_suppliers(uid: str, contacts) -> dict:
    """Every supplier edited in one go (flaw 2: what a row leaves out is kept)."""
    if not isinstance(contacts, list) or not contacts or len(contacts) > CONTACTS_MAX:
        raise stock.Refused(400, "Send between 1 and 200 suppliers at a time.")
    with stock._lock:
        st = stock.state()
        who = stock.actor(uid)
        lines = [_apply_contact(st, who, c)[2] for c in contacts]
        stock.commit(st, changed={"suppliers"}, history=lines)
        return {"saved": len(lines)}


def delete_supplier(uid: str, supplier) -> dict:
    name = stock.clean_text(supplier, 120)
    with stock._lock:
        st = stock.state()
        doc = st["suppliers"]
        kept = [c for c in doc.get("suppliers") or [] if c["supplier"] != name]
        if len(kept) == len(doc.get("suppliers") or []):
            raise stock.Refused(404, "There is no saved contact for that supplier.")
        doc["suppliers"] = kept
        line = stock.history_row(stock.actor(uid), "delete", field="supplier_contact",
                                 detail=f"removed email contact for {name}")
        stock.commit(st, changed={"suppliers"}, history=[line])
        return {"ok": True}
