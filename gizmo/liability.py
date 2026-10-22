"""Liability and the chase desk: the tags that mark an unpaid order, the credit
terms and due date each runs to, the chase log and the chase email, and the
Liability report. Moved out of copilot.py (stage 4 of the 14 October audit);
its routes are in gizmo/routes/liability.py. Read as `liability.NAME`.
"""
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from gizmo.config import _env_num
from gizmo import store as jsonstore

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")




# ---------------------------------------------------------------------------
# Unpaid orders on credit terms: the tags that mark them, the payment channel,
# and the terms and due date each one runs to.
# ---------------------------------------------------------------------------


LIABILITY_TAGS = [t.strip() for t in os.environ.get(
    "LIABILITY_TAGS", "Purchase order unpaid, Bank transfer unpaid, Procurement unpaid").split(",") if t.strip()]


def _liability_channel(tag: str) -> str:
    """Short payment-channel label from the tag: "Bank transfer unpaid" -> "Bank transfer"."""
    return re.sub(r"\s+unpaid$", "", tag, flags=re.I).strip() or tag
LIABILITY_DEFAULT_TERMS = _env_num(int, os.environ.get("LIABILITY_DEFAULT_TERMS", "30"), "30", "LIABILITY_DEFAULT_TERMS")
LIABILITY_DUE_SOON_DAYS = _env_num(int, os.environ.get("LIABILITY_DUE_SOON_DAYS", "7"), "7", "LIABILITY_DUE_SOON_DAYS")
_TERMS_TAG_RE = re.compile(r"\bnet[\s-]*(\d{1,3})\b", re.I)


def _liability_terms(o: dict):
    """(days, label, source, due_date) for one unpaid order. Precedence is
    explicit so terms are never silently invented: (1) Shopify's own payment
    terms on the order, including the exact due date when a schedule exists;
    (2) a Net-N tag on the customer; (3) the shop default, marked "assumed"."""
    created = None
    try:
        created = datetime.fromisoformat(str(o.get("created_at")).replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        pass
    pt = o.get("payment_terms")
    if isinstance(pt, dict):
        label = str(pt.get("payment_terms_name") or "").strip()
        days = pt.get("due_in_days")
        due = None
        for sched in (pt.get("payment_schedules") or []):
            raw = sched.get("due_at")
            if raw:
                try:
                    due = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
                    break
                except ValueError:
                    pass
        if due is None and days is not None and created:
            due = created + timedelta(days=int(days))
        if due is not None:
            return (int(days) if days is not None else None,
                    label or (f"Net {days}" if days is not None else "Terms"), "order", due)
    tags = str((o.get("customer") or {}).get("tags") or "")
    m = _TERMS_TAG_RE.search(tags)
    if m and created:
        n = int(m.group(1))
        return n, f"Net {n}", "customer", created + timedelta(days=n)
    n = LIABILITY_DEFAULT_TERMS
    return n, f"Net {n}", "assumed", (created + timedelta(days=n)) if created else None


# ---------------------------------------------------------------------------
# Chase desk: the weekly session of asking credit customers for money.
#
# The ledger already knows everything the email needs to say; what cost the
# merchant 30 to 60 minutes a week was saying it, from scratch, per account,
# and remembering who was asked last week. So the app composes the email (one
# statement per account, every unpaid order listed, tone stepped by how late
# the oldest one is) and keeps a last-chased stamp. The merchant copies the
# text into their own mail client and stays the sender: nothing here writes to
# Shopify or sends anything.
# ---------------------------------------------------------------------------
CHASE_LOG_PATH = os.environ.get("CHASE_LOG_PATH", "/data/chase_log.json")
CHASE_LOG_MAX = 300


def _load_chase_log() -> dict:
    return jsonstore._load_json_store(CHASE_LOG_PATH, "accounts", {}) or {}


def _mark_chased(key: str, by: str = "") -> dict:
    """Stamp an account as chased now. Returns the entry, or raises on a store
    that cannot be written (the caller turns that into a visible error: a chase
    stamp that silently fails re-creates the double-chasing this exists to stop)."""
    accounts = _load_chase_log()
    accounts[str(key)] = {"at": datetime.now(timezone.utc).isoformat(), "by": str(by or "")[:40]}
    if len(accounts) > CHASE_LOG_MAX:
        drop = sorted(accounts.items(), key=lambda kv: str(kv[1].get("at") or ""))
        accounts = dict(drop[-CHASE_LOG_MAX:])
    if not jsonstore._store_writable(CHASE_LOG_PATH):
        raise RuntimeError("chase log is not writable")
    jsonstore._write_json_store(CHASE_LOG_PATH, "accounts", accounts)
    return accounts[str(key)]


# The signs a chase email writes before an amount; any other currency is
# written as its code after the number.
_CURRENCY_SIGNS = {"GBP": "£", "USD": "$", "EUR": "€"}


def _chase_money(amount: float, currency: str) -> str:
    sym = _CURRENCY_SIGNS.get((currency or "").upper())
    return (f"{sym}{amount:,.2f}" if sym else f"{amount:,.2f} {currency}".strip())


def _chase_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %Y").lstrip("0")
    except (TypeError, ValueError):
        return ""


def _chase_email(c: dict, currency: str) -> dict:
    """The chasing email for one account, composed from its unpaid orders.

    Tone follows the oldest overdue debt: a statement while everything is
    within terms, a nudge in the first week, firmer to thirty days, and a
    formal final reminder beyond that. Never threats, never legalese: these
    are trade customers the merchant wants to keep."""
    orders = c.get("orders") or []
    over = [r for r in orders if r.get("status") == "overdue"]
    worst = max((r.get("days_over") or 0) for r in orders) if orders else 0
    total = _chase_money(c.get("total") or 0.0, currency)
    # The distinction every sentence below has to respect: "outstanding" is the
    # whole account, "overdue" is only the part past its due date. An account
    # often carries both at once, and telling a customer their fresh order is
    # overdue is exactly the dispute a chasing email must not start.
    over_amt = _chase_money(sum(r.get("outstanding") or 0.0 for r in over), currency)
    mixed = bool(over) and len(over) < len(orders)
    name = str(c.get("name") or "").strip() or "there"
    # "the order below" only when the list holds exactly the overdue ones;
    # in a mixed statement the sentence must point at the marked rows.
    which = (("orders marked overdue below have" if len(over) > 1 else "order marked overdue below has")
             if mixed else ("orders below have" if len(over) > 1 else "order below has"))

    if not over:
        tone = "statement"
        subject = f"Statement of account: {total} outstanding"
        opening = ("I hope all is well. A quick statement of what is currently open on your "
                   "account with us. Nothing is overdue; this is just to keep our records aligned.")
        closing = "If anything here does not match your records, do let me know."
    elif worst <= 7:
        tone = "gentle"
        subject = (f"Payment reminder: {over[0]['name']} ({over_amt})"
                   if len(over) == 1 else f"Payment reminder: {over_amt} overdue")
        opening = (f"I hope all is well. A gentle reminder that the {which} "
                   "gone past their due date. I know these things slip; a payment when "
                   "convenient would be much appreciated.")
        closing = "If payment is already on its way, please ignore this and accept my thanks."
    elif worst <= 30:
        tone = "firm"
        subject = f"Overdue account: {over_amt} past due"
        opening = (f"Following up on the {which.replace(' have', ',').replace(' has', ',')} "
                   "now more than a week past due. Could you let me know when payment will "
                   "be made, or if there is a problem with any of these orders that is "
                   "holding it up?")
        closing = ("If something is wrong our end, an invoice you never received or a query "
                   "on an order, tell me and I will sort it straight away.")
    else:
        tone = "final"
        subject = f"Final reminder: {over_amt} overdue"
        opening = ((f"The oldest debt below is now {worst} days past due"
                    if len(over) > 1 or mixed else f"The order below is now {worst} days past due")
                   + " despite earlier reminders. Please arrange payment within the next 7 "
                     "days, or reply with a date I can expect it by. I would much rather "
                     "resolve this together than have to hold future orders on the account.")
        closing = "If there is a genuine difficulty, talk to me; there is usually a way through."

    lines = []
    for r in orders:
        when = _chase_date(r.get("created_at"))
        bits = [f"{r['name']}  ordered {when}" if when else str(r["name"])]
        if r.get("due"):
            bits.append(f"due {_chase_date(r['due'])}")
        bits.append(f"{_chase_money(r.get('outstanding') or 0.0, currency)} outstanding")
        if (r.get("days_over") or 0) > 0 and r.get("status") == "overdue":
            bits.append(f"{r['days_over']} days overdue")
        elif mixed:
            bits.append("not yet due")
        lines.append("  " + ", ".join(bits))

    totals = [f"Total outstanding: {total}"]
    if mixed:
        totals.append(f"Of that, overdue: {over_amt}")
    body = "\n".join([
        f"Hello {name},", "", opening, "",
        *lines, "",
        *totals, "",
        "Please use the order number as the payment reference.",
        closing, "", "Thank you,", "",
    ])
    return {"subject": subject, "body": body, "tone": tone}


async def run_liability(registry: dict) -> dict:
    """Accounts receivable from orders tagged "Purchase order unpaid": what each
    credit customer owes, whether it is inside their payment terms, and which
    debts need chasing first. Plain Shopify read, no AI."""
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("Europe/London")).date()
    fields = ("id,order_number,name,created_at,tags,customer,email,total_price,"
              "total_outstanding,financial_status,currency,cancelled_at,payment_terms,"
              "billing_address,shipping_address")
    meta: dict = {}
    orders = await orderbook._orders_snapshot(registry, days=730, fields=fields, meta=meta)
    if meta.get("failed"):
        # A throttled or errored page must never read as money not owed.
        return {"error": "Couldn't read all your orders from Shopify just now (it may be busy). "
                "The figures would be incomplete, so nothing is shown. Try again in a moment."}
    store = (config.SHOPIFY_STORE or "").split(".")[0]
    rows, stale, currency = [], [], ""
    for o in orders:
        matched = [t for t in LIABILITY_TAGS if orderbook._has_tag(o, t)]
        if not matched or o.get("cancelled_at"):
            continue
        currency = currency or str(o.get("currency") or "")
        try:
            total = float(o.get("total_price") or 0)
        except (TypeError, ValueError):
            total = 0.0
        raw_out = o.get("total_outstanding")
        try:
            outstanding = float(raw_out) if raw_out is not None else total
        except (TypeError, ValueError):
            outstanding = total
        name = str(o.get("name") or "").strip() or ("#" + str(o.get("order_number") or ""))
        admin_url = (f"https://admin.shopify.com/store/{store}/orders/{o.get('id')}" if store else "")
        fin = str(o.get("financial_status") or "").lower()
        if fin in ("paid", "refunded", "voided") or outstanding <= 0.005:
            # Settled but still tagged: a hygiene problem, not a liability.
            stale.append({"name": name, "admin_url": admin_url})
            continue
        days, label, source, due = _liability_terms(o)
        company, person = production._label_party(o)
        cust = (o.get("customer") or {})
        created = None
        try:
            created = datetime.fromisoformat(str(o.get("created_at")).replace("Z", "+00:00")).date()
        except (TypeError, ValueError):
            pass
        days_over = (today - due).days if due else 0
        if due is None:
            status, bucket = "within", ""
        elif days_over > 0:
            status = "overdue"
            bucket = ("1-7" if days_over <= 7 else "8-30" if days_over <= 30
                      else "31-60" if days_over <= 60 else "60+")
        elif (due - today).days <= LIABILITY_DUE_SOON_DAYS:
            status, bucket = "due_soon", ""
        else:
            status, bucket = "within", ""
        rows.append({
            "id": o.get("id"), "name": name, "admin_url": admin_url,
            "customer": company or person or "Customer",
            "customer_key": str(cust.get("id") or company or person or name),
            "created_at": (created.isoformat() if created else ""),
            "age_days": ((today - created).days if created else 0),
            "value": round(total, 2), "paid": round(max(0.0, total - outstanding), 2),
            "outstanding": round(outstanding, 2),
            "terms": label, "terms_source": source,
            "due": (due.isoformat() if due else ""),
            "days_over": max(0, days_over),
            "days_to_due": (max(0, (due - today).days) if due else 0),
            "status": status, "bucket": bucket,
            "channel": _liability_channel(matched[0]),
            "channels": [_liability_channel(t) for t in matched],
            "tags": orderbook._order_tags(o),
            "email": str(o.get("email") or cust.get("email") or ""),
        })
    # Customer roll-up.
    customers: dict = {}
    for r in rows:
        c = customers.setdefault(r["customer_key"], {
            "name": r["customer"], "total": 0.0, "within": 0.0, "due_soon": 0.0,
            "overdue": 0.0, "oldest_days": 0, "terms": set(), "assumed": False, "orders": []})
        c["total"] = round(c["total"] + r["outstanding"], 2)
        key = "overdue" if r["status"] == "overdue" else ("due_soon" if r["status"] == "due_soon" else "within")
        c[key] = round(c[key] + r["outstanding"], 2)
        c["oldest_days"] = max(c["oldest_days"], r["age_days"])
        c["terms"].add(r["terms"])
        c["assumed"] = c["assumed"] or r["terms_source"] == "assumed"
        c["orders"].append(r)
    chase_log = _load_chase_log()
    cust_rows = []
    for key, c in customers.items():
        c["orders"].sort(key=lambda r: (r["due"] or "9999"))
        c["terms"] = (sorted(c["terms"])[0] if len(c["terms"]) == 1 else "Mixed")
        c["key"] = key
        c["email"] = next((r["email"] for r in c["orders"] if r.get("email")), "")
        c["last_chased"] = chase_log.get(key) or None
        # The email is composed here rather than in the browser so the wording
        # is tested alongside the numbers it carries.
        c["chase"] = _chase_email(c, currency or "GBP")
        cust_rows.append(c)
    cust_rows.sort(key=lambda c: (-c["overdue"], -c["total"]))
    buckets = {"within": 0.0, "due_soon": 0.0, "1-7": 0.0, "8-30": 0.0, "31-60": 0.0, "60+": 0.0}
    for r in rows:
        k = r["bucket"] if r["status"] == "overdue" else ("due_soon" if r["status"] == "due_soon" else "within")
        buckets[k] = round(buckets[k] + r["outstanding"], 2)
    channels: dict = {}
    for r in rows:
        channels[r["channel"]] = round(channels.get(r["channel"], 0.0) + r["outstanding"], 2)
    return {
        "tags": LIABILITY_TAGS, "channels": channels, "currency": currency or "GBP",
        "total": round(sum(r["outstanding"] for r in rows), 2),
        "orders": len(rows),
        "within": round(buckets["within"] + buckets["due_soon"], 2),
        "due_soon": buckets["due_soon"],
        "overdue": round(buckets["1-7"] + buckets["8-30"] + buckets["31-60"] + buckets["60+"], 2),
        "overdue_orders": sum(1 for r in rows if r["status"] == "overdue"),
        "oldest_days": max((r["age_days"] for r in rows), default=0),
        "buckets": buckets,
        "customers": cust_rows,
        "stale_tagged": stale[:20],
        "default_terms": LIABILITY_DEFAULT_TERMS,
        "truncated": bool(meta.get("truncated")),
    }


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as sibling.NAME, never a copied name.
from gizmo import orderbook  # noqa: E402
from gizmo import production  # noqa: E402
from gizmo import config  # noqa: E402
