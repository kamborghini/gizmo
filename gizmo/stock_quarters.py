"""The stock sheet's overview: quarters (close, rename, compare, download),
settings and exchange rates, warnings, "since you were last here", the
history searched and each line's own, and the figures over time.

All the stock app's own behaviour, with three fixes: "since you were last
here" belongs to each Reactor account and carries on from the stock app's
own records of that person; a line's history follows it through a rename;
the outlook counts real days (flaw 8).
"""
import csv
import io
import re
from datetime import datetime, timedelta, timezone

from gizmo import stock, stock_figures, stock_store

CLOSE_GAP_SECONDS = 60       # a second close this soon after one is a double click, not a decision
CLOSED_SHOWN = 40
HISTORY_PAGE_MAX = 300

# The closed quarter's download: the stock app's columns, in its order.
CLOSING_COLUMNS = [
    ("category", "Category"), ("sub_category", "Sub Category"), ("size", "Size"), ("notes", "Notes"),
    ("written_off", "Written Off"), ("start", "Start"), ("received", "Received"), ("used", "Used"),
    ("current", "Current"), ("unit_cost", "Unit Cost"), ("currency", "Currency"), ("supplier", "Supplier"),
    ("unit_cost_gbp", "Unit Cost GBP"), ("start_value", "Start Value"), ("used_value", "Used Value"),
    ("current_value", "Current Value")]


def _instant(iso):
    """A stored time as a moment; one written without a zone is UTC."""
    if not iso:
        return None
    try:
        t = datetime.fromisoformat(str(iso))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _open_quarter(st: dict):
    open_ = [p for p in st["periods"].get("periods") or [] if p.get("closed_at") is None]
    return max(open_, key=lambda p: _instant(p["opened_at"]) or datetime.min.replace(tzinfo=timezone.utc)) if open_ else None


def _closed(st: dict) -> list:
    return sorted((p for p in st["periods"].get("periods") or [] if p.get("closed_at")),
                  key=lambda p: (_instant(p["closed_at"]), p["id"]), reverse=True)


# ---- quarters ------------------------------------------------------------------

def quarters() -> dict:
    st = stock.state()
    cur = _open_quarter(st)
    return {"current": {"label": cur["label"], "opened_at": cur["opened_at"]} if cur else None,
            "history": [{"id": p["id"], "label": p["label"], "closed_at": p["closed_at"],
                         "closing_value_gbp": p["closing_value"], "closing_units": p["closing_units"],
                         "closing_skus": p["closing_skus"], "closing_used_value_gbp": p["closing_used_value"]}
                        for p in _closed(st)[:CLOSED_SHOWN]]}


def rename(uid: str, label) -> dict:
    label = stock.clean_text(label, 120)
    if not label:
        raise stock.Refused(400, "The quarter needs a name.")
    with stock._lock:
        st = stock.state()
        cur = _open_quarter(st)
        if not cur:
            raise stock.Refused(404, "There is no open quarter.")
        old, cur["label"] = cur["label"], label
        row = stock.history_row(stock.actor(uid), "period", detail=f"renamed period '{old}' -> '{label}'")
        stock.commit(st, changed={"periods"}, history=[row])
        return {"label": label}


def close(uid: str, new_label) -> dict:
    """Close the open quarter and open the next: its closing figures and
    every line kept, then every line rolled (current becomes start; received
    and used start again from 0), in one change with its two snapshots."""
    new_label = stock.clean_text(new_label, 120)
    if not new_label:
        raise stock.Refused(400, "The new quarter needs a name.")
    with stock._lock:
        st = stock.state()
        meta = st["settings"].setdefault("meta", {})
        last = _instant(meta.get("last_period_close_at"))
        if last and (datetime.now(timezone.utc) - last).total_seconds() < CLOSE_GAP_SECONDS:
            raise stock.Refused(409, "A quarter was closed moments ago. Closing again is held back for a minute, "
                                     "so it cannot happen twice by accident.")
        who = stock.actor(uid)
        items = stock.items_in_order(st["items"])
        h = stock_figures.compute_current(items)["headline"]
        cur = _open_quarter(st)
        old_label = cur["label"] if cur else "(none)"
        now = stock.now_iso()
        if cur:
            cur.update(closed_at=now, closing_value=h["active_stock_value_gbp"], closing_units=h["active_units"],
                       closing_skus=h["active_skus"], closing_used_value=h["cogs_used_value_gbp"],
                       closing_data=[stock_figures.item_view(it) for it in items])
        closing = stock.take_snapshot(st, "period_close", who, f"closed {old_label}")
        for it in items:
            it["start"], it["received"], it["used"] = it["current"], 0, 0
        periods = st["periods"]
        periods.setdefault("periods", []).append({
            "id": periods.get("next_id") or 1, "label": new_label, "opened_at": now, "closed_at": None,
            "closing_value": 0.0, "closing_units": 0, "closing_skus": 0, "closing_used_value": 0.0, "note": "",
            "closing_data": None})
        periods["next_id"] = (periods.get("next_id") or 1) + 1
        row = stock.history_row(who, "period", detail=(
            f"closed '{old_label}' (£{h['active_stock_value_gbp']}, {h['active_units']} units, "
            f"{h['active_skus']} SKUs) -> opened '{new_label}'; rolled {len(items)} items current->start, "
            "reset used/received")[:480])
        opening = stock.take_snapshot(st, "period_open", who, f"opened {new_label}", prev=closing)
        meta["last_period_close_at"] = now
        stock.commit(st, changed={"items", "periods", "alerts", "settings"}, history=[row],
                     snapshots=[closing, opening])
        return {"closed": old_label, "opened": new_label, "rolled": len(items),
                "closing_value_gbp": h["active_stock_value_gbp"],
                "summary": stock_figures.compute_current(items)}


def _csv_safe(value) -> str:
    """A cell a spreadsheet would run as a formula is written as text."""
    s = "" if value is None else str(value)
    return "'" + s if s and (s[0] in "=+-@\t\r\n" or s.lstrip()[:1] in "=+-@") else s


def quarter_csv(period_id) -> dict:
    st = stock.state()
    p = next((q for q in st["periods"].get("periods") or [] if str(q["id"]) == str(period_id)), None)
    if not p:
        raise stock.Refused(404, "That quarter was not found.")
    rows = p.get("closing_data") if isinstance(p.get("closing_data"), list) else []
    if not rows:
        raise stock.Refused(404, "This quarter has no closing list to download.")
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([c[1] for c in CLOSING_COLUMNS])
    for r in rows:
        w.writerow([_csv_safe(r.get(k, "")) for k, _ in CLOSING_COLUMNS])
    name = re.sub(r"[^A-Za-z0-9 ._-]", "-", p["label"] or "").strip()[:80] or "period"
    return {"csv": out.getvalue(), "filename": name + ".csv"}


def compare(left, right) -> dict:
    """Two quarters side by side: "current" (the live sheet) or a quarter's id.
    The left defaults to the last closed quarter."""
    st = stock.state()
    items = stock.items_in_order(st["items"])
    periods = st["periods"].get("periods") or []
    if left in (None, ""):
        last = _closed(st)
        left = last[0]["id"] if last else "current"

    def side(ref):
        if ref in (None, "") or str(ref) == "current":
            return stock_figures.side_live(items, periods)
        p = next((q for q in periods if str(q["id"]) == str(ref)), None)
        return stock_figures.side_period(p) if p else None

    a, b = side(left), side(right)
    if not a or not b:
        raise stock.Refused(404, "That quarter was not found.")
    return stock_figures.compare(a, b)


# ---- settings and exchange rates ----------------------------------------------------

def settings() -> dict:
    st = stock.state()
    meta = st["settings"].get("meta") or {}
    rates = stock_figures.fx_rates(stock.items_in_order(st["items"]), meta)
    try:
        days = int(meta.get("low_stock_days") or 21)
    except (TypeError, ValueError):
        days = 21
    return {"low_stock_days": days, "fx_usd_gbp": rates.get("USD"), "fx_eur_gbp": rates.get("EUR")}


def save_settings(uid: str, low_stock_days=None, fx_usd_gbp=None, fx_eur_gbp=None) -> dict:
    with stock._lock:
        st = stock.state()
        meta = st["settings"].setdefault("meta", {})
        changed = []
        if low_stock_days is not None:
            if isinstance(low_stock_days, bool):
                raise stock.Refused(400, "Low stock days must be a number.")
            try:
                days = max(1, min(int(float(low_stock_days)), 365))
            except (TypeError, ValueError, OverflowError):
                raise stock.Refused(400, "Low stock days must be a number.") from None
            meta["low_stock_days"] = str(days)
            changed.append(f"low-stock {days}d")
        for cur, value in (("usd", fx_usd_gbp), ("eur", fx_eur_gbp)):
            if value in (None, ""):
                continue
            words = f"The {cur.upper()} rate must be a number above 0 and below 100."
            if isinstance(value, bool):
                raise stock.Refused(400, words)
            try:
                rate = float(value)
            except (TypeError, ValueError):
                raise stock.Refused(400, words) from None
            if not 0 < rate < 100:
                raise stock.Refused(400, words)
            meta[f"fx_{cur}_gbp"] = str(round(rate, 6))
            changed.append(f"{cur.upper()}->GBP {round(rate, 4)}")
        if changed:
            row = stock.history_row(stock.actor(uid), "update", detail="settings: " + ", ".join(changed))
            stock.commit(st, changed={"settings"}, history=[row])
    return settings()


def fx() -> dict:
    st = stock.state()
    return stock_figures.fx_revaluation(stock.items_in_order(st["items"]), st["settings"].get("meta") or {})


# ---- warnings -----------------------------------------------------------------------

def alerts() -> dict:
    rows = [a for a in stock.state()["alerts"].get("alerts") or [] if not a.get("dismissed")]
    rows.sort(key=lambda a: (_instant(a["at"]) or datetime.min.replace(tzinfo=timezone.utc), a["id"]), reverse=True)
    return {"alerts": [{k: a.get(k) for k in ("id", "at", "kind", "severity", "message", "item_key")}
                       for a in rows[:100]]}


def dismiss(uid: str, alert_id) -> dict:
    try:
        aid = int(alert_id)
    except (TypeError, ValueError):
        aid = 0
    if aid <= 0:
        raise stock.Refused(400, "Which warning?")
    with stock._lock:
        st = stock.state()
        a = next((x for x in st["alerts"].get("alerts") or [] if x["id"] == aid), None)
        if a:
            who = stock.actor(uid)
            a.update(dismissed=True, dismissed_by=who["user"], dismissed_person=who["person"])
            stock.commit(st, changed={"alerts"})
    return {"ok": True}


# ---- since you were last here ----------------------------------------------------------

def _since(st: dict, uid: str):
    """The later of this person's own acknowledgement and, for the stock
    app usernames they were, that app's last sign-in and acknowledgement."""
    marks = [_instant((st["settings"].get("acks") or {}).get(str(uid)))]
    people = stock_store.load_people()
    meta = st["settings"].get("meta") or {}
    for name, account in (people.get("people") or {}).items():
        if str(account) == str(uid):
            marks.append(_instant(((people.get("logins") or {}).get(name) or {}).get("prev_login")))
            marks.append(_instant(meta.get(f"briefing_ack_{name}")))
    marks = [m for m in marks if m]
    return max(marks) if marks else None


def briefing(uid: str) -> dict:
    st = stock.state()
    since = _since(st, uid)
    if not since:
        return {"since": None}
    items = stock.items_in_order(st["items"])
    before = [s for s in stock.snapshots() if (_instant(s.get("taken_at")) or since) <= since]
    then = max(before, key=lambda s: (_instant(s["taken_at"]), s["id"])) if before else None
    value_then = (then.get("totals") or {}).get("active_value_gbp") if then and isinstance(then.get("totals"), dict) else None
    value_now = stock_figures.compute_current(items)["headline"]["active_stock_value_gbp"]
    counts = {"update": 0, "receive": 0, "create": 0, "period": 0}
    for row in stock.history_index().rows:
        at = _instant(row.get("at"))
        if at and at >= since and row.get("action") in counts:
            counts[row["action"]] += 1
    new_alerts = sum(1 for a in st["alerts"].get("alerts") or [] if (_instant(a.get("at")) or since) >= since)
    return {"since": since.isoformat(), "value_now": value_now, "value_then": value_then,
            "value_delta": round(value_now - value_then, 2) if value_then is not None else None,
            "edits": counts["update"], "receives": counts["receive"], "creates": counts["create"],
            "period": counts["period"], "new_alerts": new_alerts,
            "reorder_lines": stock_figures.reorder_suggestions(items)["total_lines"]}


def acknowledge(uid: str) -> dict:
    with stock._lock:
        st = stock.state()
        st["settings"].setdefault("acks", {})[str(uid)] = stock.now_iso()
        stock.commit(st, changed={"settings"})
    return {"ok": True}


# ---- the history -----------------------------------------------------------------------

def _who(row: dict, names: dict) -> str:
    return names.get(str(row.get("person"))) or row.get("user") or ""


def _day(value):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def history(q=None, action=None, person=None, item_id=None, start=None, end=None, before=None, limit=None) -> dict:
    """The history, newest first, a page at a time (`before` the last id seen)."""
    try:
        limit = max(1, min(int(limit or 100), HISTORY_PAGE_MAX))
    except (TypeError, ValueError):
        limit = 100
    line, find = None, None
    if item_id not in (None, ""):
        st = stock.state()
        it = (st["items"].get("items") or {}).get(str(item_id))
        if not it:
            raise stock.Refused(404, "That stock line was not found.")
        line, find = it["id"], stock.line_finder(st["items"])
    lo, hi = _day(start), _day(end)
    hi = hi + timedelta(days=1) if hi else None
    needle = (q or "").strip().casefold()
    names = team._team_names()
    out, more = [], False
    for row in reversed(stock.history_index().rows):
        if before not in (None, "") and row.get("id", 0) >= int(before):
            continue
        if action and row.get("action") != action:
            continue
        if person and str(row.get("person")) != str(person):
            continue
        if find is not None and find(row) != line:
            continue
        at = _instant(row.get("at"))
        if (lo and (not at or at < lo)) or (hi and (not at or at >= hi)):
            continue
        if needle and needle not in " ".join(str(row.get(k) or "") for k in
                                             ("user", "action", "item_key", "field", "old_value", "new_value",
                                              "detail")).casefold():
            continue
        if len(out) == limit:
            more = True
            break
        out.append(dict(row, who=_who(row, names)))
    return {"rows": out, "more": more}


def item_sheet(item_id) -> dict:
    """One line: as it is, its own forecast, its supplier's delivery time,
    and its history under every name it has had (newest 200)."""
    st = stock.state()
    it = (st["items"].get("items") or {}).get(str(item_id))
    if not it:
        raise stock.Refused(404, "That stock line was not found.")
    items = stock.items_in_order(st["items"])
    kept = stock.snapshot_summary()
    row = next((f for f in stock_figures.forecast_from(items, kept.series, kept.values())["items"]
                if f["key"] == it["key"]), None)
    contact = next((c for c in st["suppliers"].get("suppliers") or [] if c["supplier"] == (it["supplier"] or "")), None)
    return {"item": stock_figures.item_view(it), "forecast": row, "lead_days": (contact or {}).get("lead_days") or 0,
            "history": history(item_id=it["id"], limit=200)["rows"]}


# ---- over time ----------------------------------------------------------------------------

def trends() -> dict:
    return stock_figures.trends(stock.snapshots())


def forecast() -> dict:
    kept = stock.snapshot_summary()
    return stock_figures.forecast_from(stock.items_in_order(stock.state()["items"]), kept.series, kept.values())


def outlook() -> dict:
    return stock_figures.outlook(stock.snapshots()) or {"value_now": None, "per_day": None, "projected": None,
                                                        "days": 30}


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as sibling.NAME, never a copied name.
from gizmo import team  # noqa: E402
