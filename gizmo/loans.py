"""Loan units: the projectors that go out to customers, and where they are. The
register and its copy in memory, the board. Moved out of copilot.py (stage 4
of the 14 October audit); its route is in gizmo/routes/loans.py. Read as
`loans.NAME`.
"""
import logging
import os
import time
import secrets
from datetime import datetime, timezone
from gizmo import store as jsonstore

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


# --------------------------------------------------------------------------
# Loan units: the projectors that go out to customers, and where they are.
# Two objects because they answer different questions. A UNIT is a thing the
# shop owns and keeps forever; a LOAN is one trip it made. Without the unit
# register "where is the demo projector" has no answer, because the same
# machine gets typed six different ways over a year.
# --------------------------------------------------------------------------


LOANS_PATH = os.environ.get("LOANS_PATH", "/data/loans.json")
LOAN_CHASE_DAYS_DEFAULT = 28
_loans_mem = None


def _let_go_of_loans_in_memory(paths) -> list:
    """Let go of the loan register held in memory (see jsonstore.holds_in_memory)."""
    global _loans_mem
    if paths is None or LOANS_PATH in paths:
        _loans_mem = None
        return [LOANS_PATH]
    return []


jsonstore.holds_in_memory(_let_go_of_loans_in_memory)



def _loans_default() -> dict:
    return {"units": {}, "loans": {}, "seq": 0,
            "settings": {"chase_days": LOAN_CHASE_DAYS_DEFAULT}}


def _load_loans() -> dict:
    global _loans_mem
    if _loans_mem is None:
        d = jsonstore._load_json_store(LOANS_PATH, "loans_store", None)
        base = _loans_default()
        if isinstance(d, dict):
            base.update({k: d[k] for k in ("units", "loans", "seq") if k in d})
            if isinstance(d.get("settings"), dict):
                base["settings"].update(d["settings"])
        _loans_mem = base
    return _loans_mem


def _write_loans(d: dict) -> None:
    """Owner-only: it carries customers' names and phone numbers."""
    global _loans_mem
    if not jsonstore._store_writable(LOANS_PATH):
        _loans_mem = None
        raise RuntimeError("the loan register is not writable")
    try:
        jsonstore._write_private_json(LOANS_PATH, "loans_store", d)
    except Exception:
        _loans_mem = None
        raise
    _loans_mem = d


# The shop's catalogue as pickable rows, one per variant. Cached, because the
# Products tab's own loader pulls up to two years of sales history per product
# and hanging a typeahead on that would spend a fortune to answer "which Epson
# is it". One variant per row: a SKU is what tells two identical projectors
# apart, and the product title alone cannot.
_loan_products = {"at": 0.0, "rows": []}
LOAN_PRODUCT_TTL = 600


async def _loan_product_rows(registry) -> list:
    now = time.monotonic()
    if _loan_products["rows"] and now - _loan_products["at"] < LOAN_PRODUCT_TTL:
        return _loan_products["rows"]
    # The whole catalogue, not its first page: a unit made from a product
    # past the 250th could not be picked. A failed read is not cached, so
    # the next open tries again instead of serving an empty list for ten minutes.
    products, ok, _cut = await core._all_products(registry, "id,title,status,vendor,product_type,variants")
    if not ok and not products:
        raise RuntimeError("the product read failed")   # the route says so, not "no matches"
    rows = []
    for prod in products:
        if str(prod.get("status") or "active").lower() == "archived":
            continue
        title = " ".join(str(prod.get("title") or "").split())
        for v in (prod.get("variants") or [{}]):
            vt = " ".join(str(v.get("title") or "").split())
            # Shopify calls a single-variant product's only variant "Default
            # Title"; printing that back at somebody is noise, not information.
            full = title + (" \u00b7 " + vt if vt and vt.lower() != "default title" else "")
            rows.append({"product_id": str(prod.get("id") or ""),
                         "variant_id": str(v.get("id") or ""),
                         "title": full, "sku": str(v.get("sku") or ""),
                         "vendor": " ".join(str(prod.get("vendor") or "").split())})
    if ok:
        _loan_products.update({"at": now, "rows": rows})   # only a complete read is worth keeping
    return rows


def _loan_id(d: dict, prefix: str) -> str:
    d["seq"] = int(d.get("seq") or 0) + 1
    return "%s%d" % (prefix, d["seq"])


def _loan_days_out(out_at: str) -> int:
    try:
        started = datetime.fromisoformat(str(out_at).replace("Z", "+00:00"))
    except ValueError:
        return 0
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return max(0, (datetime.now(timezone.utc) - started).days)


def _loan_state(loan: dict, chase_days: int) -> str:
    """late = past a date somebody set. due = no date, and older than the
    threshold. A loan with no due date is never LATE, however old: nobody
    promised it back, so calling it late would be the app inventing a
    commitment the customer never made."""
    due = str(loan.get("due_at") or "").strip()
    if due:
        return "late" if due < core._london_today().isoformat() else "ok"
    return "due" if _loan_days_out(loan.get("out_at")) > int(chase_days or 0) else "ok"


# No O or 0, no I, L or 1: the tag is read off a sticker in a workshop and
# said down a phone, and those are the characters that come back wrong.
LOAN_TAG_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
LOAN_TAG_LENGTH = 6


def _loan_mint_tag(d: dict) -> str:
    """An asset tag no one can guess or count.

    A running number told anyone who read one sticker roughly how many units
    the shop owns, and what the next one would be. Random instead, and checked
    against every tag already minted: 31^6 is about 900 million, so a clash is
    vanishingly unlikely, and "vanishingly unlikely" is not the same as
    impossible when the failure is two projectors wearing one number."""
    taken = {str(u.get("asset_tag") or "") for u in (d.get("units") or {}).values()}
    for _ in range(200):
        tag = "PI-" + "".join(secrets.choice(LOAN_TAG_ALPHABET)
                              for _ in range(LOAN_TAG_LENGTH))
        if tag not in taken:
            return tag
    # Two hundred collisions in a row is not luck, it is a register so full
    # that the shape is wrong. Longer, rather than handing back a duplicate.
    while True:
        tag = "PI-" + "".join(secrets.choice(LOAN_TAG_ALPHABET)
                              for _ in range(LOAN_TAG_LENGTH + 2))
        if tag not in taken:
            return tag


def _loan_codes(tag: str) -> dict:
    """The QR and the barcode, drawn on the SERVER and handed over as data
    URIs. The page's CSP allows no script from a CDN, so a browser QR library
    could never have run; and a Code 128 pattern table written from memory
    would risk stickers that no scanner reads, discovered weeks later on
    machines already out with customers. Both libraries are pure Python."""
    import base64
    import io as _io
    import segno
    import barcode as _barcode
    from barcode.writer import SVGWriter
    qr = segno.make(tag, error="m").png_data_uri(scale=6, border=2, dark="#111111")
    buf = _io.BytesIO()
    _barcode.get("code128", tag, writer=SVGWriter()).write(
        buf, options={"module_height": 9.0, "font_size": 0, "text_distance": 1,
                      "quiet_zone": 2})
    bc = "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    return {"qr": qr, "barcode": bc}


def _loans_board(d: dict, who: str) -> dict:
    chase = int((d.get("settings") or {}).get("chase_days") or LOAN_CHASE_DAYS_DEFAULT)
    open_by_unit = {}
    for lid, lo in (d.get("loans") or {}).items():
        if not lo.get("back_at"):
            open_by_unit[str(lo.get("unit_id") or "")] = dict(lo, id=lid)
    units, out_rows = [], []
    for uid, u in sorted((d.get("units") or {}).items(),
                         key=lambda kv: str(kv[1].get("name") or "").lower()):
        lo = open_by_unit.get(uid)
        status = "retired" if u.get("retired") else ("out" if lo else "in")
        shape = {"id": uid, "name": u.get("name") or "", "model": u.get("model") or "",
                 "serial": u.get("serial") or "", "notes": u.get("notes") or "",
                 "product_id": u.get("product_id") or "", "variant_id": u.get("variant_id") or "",
                 "sku": u.get("sku") or "", "asset_tag": u.get("asset_tag") or "",
                 "status": status}
        units.append(shape)
        if lo and status == "out":
            out_rows.append({
                "id": lo["id"], "unit": shape,
                "who_name": lo.get("who_name") or "", "phone": lo.get("phone") or "",
                "crm_person_id": lo.get("crm_person_id") or "",
                "crm_org_id": lo.get("crm_org_id") or "",
                "out_at": lo.get("out_at") or "", "due_at": lo.get("due_at") or "",
                "out_by_name": team._team_name(lo.get("out_by") or "") or "",
                "note": lo.get("note") or "",
                "days_out": _loan_days_out(lo.get("out_at")),
                "state": _loan_state(lo, chase)})
    out_rows.sort(key=lambda r: (-r["days_out"], r["unit"]["name"].lower()))
    return {"units": units, "out": out_rows,
            "counts": {"out": len(out_rows),
                       "in": sum(1 for u in units if u["status"] == "in"),
                       "late": sum(1 for r in out_rows if r["state"] == "late")},
            "settings": {"chase_days": chase},
            "can_manage": team._team_level(who) >= team.ROLE_LEVELS["admin"]}


def _loan_history(d: dict, unit_id: str) -> list:
    rows = [dict(lo, id=lid) for lid, lo in (d.get("loans") or {}).items()
            if str(lo.get("unit_id") or "") == str(unit_id)]
    rows.sort(key=lambda r: str(r.get("out_at") or ""), reverse=True)
    return [{"id": r["id"], "who_name": r.get("who_name") or "",
             "out_at": r.get("out_at") or "", "due_at": r.get("due_at") or "",
             "back_at": r.get("back_at") or "", "note": r.get("note") or "",
             "days_out": (_loan_days_out(r.get("out_at")) if not r.get("back_at") else None)}
            for r in rows[:50]]


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as core.NAME and sibling.NAME, never a copied name.
from gizmo import team  # noqa: E402
import copilot as core  # noqa: E402
