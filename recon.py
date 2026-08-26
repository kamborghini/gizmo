"""The reconciliation and investigation engine: Shopify + Xero + Gmail.

One question, asked continuously: what should have happened, what actually
happened, and can the accounting records be PROVEN to reflect it?

Division of labour, and it is strict:
  * Deterministic code does everything arithmetic: totals, differences, date
    windows, matching, duplicate clustering. A sum is never an opinion.
  * The AI (Claude, the deep model, env-upgradable) is only for what genuinely
    needs judgement: reading documents, classifying an already-computed
    discrepancy, proposing an explanation. Every AI conclusion must cite the
    evidence ids it was shown, the citations are validated against the pack,
    and an answer that fails validation is recorded as
    "Insufficient evidence - requires human review", never as a finding.
  * Nothing here writes to Shopify, Xero or Gmail. The engine reads three
    systems and writes ONE local store of exceptions and evidence.

Money is handled in integer pence from the moment it enters. Floats are how
reconciliation tools invent penny discrepancies of their own.

The module is deliberately free of app imports: copilot.py injects the IO it
needs (Shopify registry, Gmail bytes, the AI caller, the mail store) via
configure(), so every check in here runs under test against plain dicts.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Tunables. Env-overridable so materiality is the merchant's call, not code's.
WINDOW_DAYS = int(os.environ.get("RECON_WINDOW_DAYS", "120"))
MATERIAL_PENCE = int(os.environ.get("RECON_MATERIAL_PENCE", "25000"))     # 250.00
TOLERANCE_PENCE = int(os.environ.get("RECON_TOLERANCE_PENCE", "100"))     # 1.00
STALE_UNRECONCILED_DAYS = int(os.environ.get("RECON_STALE_DAYS", "21"))
DOCS_PER_SWEEP = int(os.environ.get("RECON_DOCS_PER_SWEEP", "8"))
DOC_BYTES_MAX = int(os.environ.get("RECON_DOC_BYTES_MAX", str(8 * 1024 * 1024)))
# What to ask the accounts mailbox for. Attachments are where remittances,
# invoices and statements actually live; the words catch the ones sent in the
# body. Gmail's own search does the work, so the app never walks the mailbox.
MAIL_QUERY = os.environ.get(
    "RECON_GMAIL_QUERY",
    "(has:attachment OR remittance OR invoice OR statement OR \"credit note\") "
    "newer_than:{days}d")
THREADS_PER_SWEEP = int(os.environ.get("RECON_THREADS_PER_SWEEP", "40"))
# How many walked threads to remember. Past this the OLDEST are forgotten and
# may be walked again: wasted budget, never a lost document, because a thread
# is only ever skipped when its documents were already read into the store.
SEEN_CAP = int(os.environ.get("RECON_SEEN_CAP", "4000"))
# RETENTION. Every other store in this app prunes; these three held third
# parties' financial records and document text for ever. Nothing is kept
# beyond what a sweep can still reconcile, plus a margin: a record older than
# the window cannot be matched against anything, so keeping it is a liability
# with no use. Resolved discrepancies keep their evidence for a while, because
# the audit trail is the point, then shed it.
CACHE_KEEP_DAYS = int(os.environ.get("RECON_CACHE_KEEP_DAYS", str(WINDOW_DAYS + 60)))
DOCS_KEEP_DAYS = int(os.environ.get("RECON_DOCS_KEEP_DAYS", str(WINDOW_DAYS + 60)))
CLOSED_KEEP_DAYS = int(os.environ.get("RECON_CLOSED_KEEP_DAYS", "365"))
# How far back every sweep FETCHES. Deliberately the same number as the
# retention horizon, and not the shorter check window: whatever is still in the
# cache must still be refetchable. Ask Xero only for the last WINDOW_DAYS and a
# bank line dated before that can never be refreshed - so when the bookkeeper
# finally reconciles it, our copy still says unreconciled and the check goes on
# reporting a discrepancy that was settled weeks ago.
FETCH_DAYS = CACHE_KEEP_DAYS

# Injected by copilot.configure(): the engine owns logic, never transport.
_registry: Optional[dict] = None          # Shopify tool registry
_tool_json: Optional[Callable] = None     # async (registry, name, args) -> dict
_gmail_bytes: Optional[Callable] = None   # async (message_id, attachment_id) -> bytes
# The FINANCE mailbox, not the sales inbox the Inbox tab shows. It is a
# separate Google account with no thread board behind it, so discovery is a
# live Gmail search rather than a walk over a local store.
_mail_connected: Optional[Callable] = None  # () -> bool, is the accounts mailbox linked
_mail_search: Optional[Callable] = None   # async (query, max_results) -> set of thread ids
_mail_thread: Optional[Callable] = None   # async (thread_id) -> parsed thread dict
_ai_call: Optional[Callable] = None       # async (system, messages, tools) -> response
_xero = None                              # the xero module (injected to allow fakes)

_load_store: Optional[Callable] = None    # () -> dict   (RECON_PATH, house store rules)
_write_store: Optional[Callable] = None
_load_cache: Optional[Callable] = None    # () -> dict   (RECON_CACHE_PATH)
_write_cache: Optional[Callable] = None
_load_docs: Optional[Callable] = None     # () -> dict   (RECON_DOCS_PATH)
_write_docs: Optional[Callable] = None

_sweeping = {"on": False, "at": 0.0}      # one sweep at a time, on the event loop


def configure(**kw) -> None:
    g = globals()
    for name, val in kw.items():
        key = "_" + name
        if key not in g:
            raise KeyError("recon.configure: unknown hook " + name)
        g[key] = val


# ---------------------------------------------------------------------------
# Money and matching primitives
# ---------------------------------------------------------------------------

def pence(v: Any) -> Optional[int]:
    """Integer pence or None - never a float, never a guess. Accepts '12.30',
    12.3, '£1,234.56', -5. A value that will not parse is None, and every
    caller treats None as 'unknown', not zero: a sale of unknown value must
    not reconcile as a sale of nothing."""
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace("£", "").replace("$", "").replace("€", "")
    if not s:
        return None
    try:
        return int((Decimal(s) * 100).quantize(Decimal("1")))
    except (InvalidOperation, ValueError):
        return None


def money(p: Optional[int], cur: str = "GBP") -> str:
    if p is None:
        return "unknown"
    sym = {"GBP": "£", "USD": "$", "EUR": "€"}.get(cur, cur + " ")
    neg = "-" if p < 0 else ""
    p = abs(p)
    return f"{neg}{sym}{p // 100}.{p % 100:02d}"


def norm_ref(s: Any) -> str:
    """Invoice/reference normalization for matching: case, punctuation and
    leading zeros are presentation, not identity. 'INV-00142' == 'inv 142'."""
    t = re.sub(r"[^a-z0-9]", "", str(s or "").lower())
    return re.sub(r"^([a-z]*)0+(\d)", r"\1\2", t)


def norm_name(s: Any) -> str:
    t = re.sub(r"[^a-z0-9 ]", "", str(s or "").lower())
    for suffix in (" limited", " ltd", " gmbh", " inc", " llc", " plc", " co", " company"):
        if t.endswith(suffix):
            t = t[: -len(suffix)]
    return " ".join(t.split())


def _day(s: Any) -> str:
    """YYYY-MM-DD out of ISO strings or Xero's /Date(1699999999000+0000)/ form."""
    t = str(s or "")
    m = re.match(r"/Date\((\d+)", t)
    if m:
        return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    return t[:10]


def _days_between(a: str, b: str) -> Optional[int]:
    try:
        da = datetime.strptime(_day(a), "%Y-%m-%d")
        db = datetime.strptime(_day(b), "%Y-%m-%d")
        return abs((da - db).days)
    except ValueError:
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cutoff_day(days: int = WINDOW_DAYS) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Slimmers: what each system contributes to the cache. Verbatim identifiers,
# amounts as pence, and nothing the checks do not need - the cache rides in
# backups and is reloaded on every sweep.
# ---------------------------------------------------------------------------

def slim_order(o: dict) -> dict:
    refunds = []
    for r in (o.get("refunds") or []):
        amt = 0
        for t in (r.get("transactions") or []):
            if t.get("kind") in ("refund", "void") and t.get("status") == "success":
                amt += pence(t.get("amount")) or 0
        refunds.append({"id": r.get("id"), "created_at": _day(r.get("created_at")),
                        "pence": amt})
    return {
        "id": o.get("id"), "name": str(o.get("name") or ""),
        "created_at": _day(o.get("created_at")),
        "total": pence(o.get("total_price")),
        "tax": pence(o.get("total_tax")),
        "currency": str(o.get("currency") or "GBP"),
        "financial_status": str(o.get("financial_status") or ""),
        "cancelled": bool(o.get("cancelled_at")),
        "test": bool(o.get("test")),
        "customer": str(((o.get("customer") or {}).get("first_name") or "") + " "
                        + ((o.get("customer") or {}).get("last_name") or "")).strip(),
        "company": str((((o.get("customer") or {}).get("default_address") or {})
                        .get("company")) or ""),
        "gateways": sorted({str(g) for g in (o.get("payment_gateway_names") or []) if g}),
        "refunds": refunds,
    }


def slim_invoice(v: dict) -> dict:
    return {
        "id": str(v.get("InvoiceID") or ""),
        "number": str(v.get("InvoiceNumber") or ""),
        "type": str(v.get("Type") or ""),                       # ACCREC | ACCPAY
        "status": str(v.get("Status") or ""),
        "contact": str(((v.get("Contact") or {}).get("Name")) or ""),
        "date": _day(v.get("DateString") or v.get("Date")),
        "due": _day(v.get("DueDateString") or v.get("DueDate")),
        "total": pence(v.get("Total")),
        "tax": pence(v.get("TotalTax")),
        "due_pence": pence(v.get("AmountDue")),
        "paid_pence": pence(v.get("AmountPaid")),
        "credited_pence": pence(v.get("AmountCredited")),
        "currency": str(v.get("CurrencyCode") or "GBP"),
        "reference": str(v.get("Reference") or ""),
        "updated": str(v.get("UpdatedDateUTC") or ""),
    }


def slim_payment(p: dict) -> dict:
    inv = p.get("Invoice") or {}
    return {
        "id": str(p.get("PaymentID") or ""),
        "date": _day(p.get("Date")),
        "pence": pence(p.get("Amount")),
        "reference": str(p.get("Reference") or ""),
        "status": str(p.get("Status") or ""),
        "invoice_id": str(inv.get("InvoiceID") or ""),
        "invoice_number": str(inv.get("InvoiceNumber") or ""),
        "contact": str(((inv.get("Contact") or {}).get("Name")) or ""),
        "account": str(((p.get("Account") or {}).get("Code")) or ""),
        "is_reconciled": bool(p.get("IsReconciled")),
    }


def slim_bank_txn(t: dict) -> dict:
    return {
        "id": str(t.get("BankTransactionID") or ""),
        "type": str(t.get("Type") or ""),                       # RECEIVE | SPEND | ...
        "status": str(t.get("Status") or ""),
        "date": _day(t.get("DateString") or t.get("Date")),
        "pence": pence(t.get("Total")),
        "currency": str(t.get("CurrencyCode") or "GBP"),
        "contact": str(((t.get("Contact") or {}).get("Name")) or ""),
        "reference": str(t.get("Reference") or ""),
        "account": str(((t.get("BankAccount") or {}).get("Name")) or ""),
        "is_reconciled": bool(t.get("IsReconciled")),
    }


def slim_credit_note(c: dict) -> dict:
    return {
        "id": str(c.get("CreditNoteID") or ""),
        "number": str(c.get("CreditNoteNumber") or ""),
        "type": str(c.get("Type") or ""),               # ACCRECCREDIT | ACCPAYCREDIT
        "status": str(c.get("Status") or ""),
        "contact": str(((c.get("Contact") or {}).get("Name")) or ""),
        "date": _day(c.get("DateString") or c.get("Date")),
        "total": pence(c.get("Total")),
        "remaining": pence(c.get("RemainingCredit")),
        "currency": str(c.get("CurrencyCode") or "GBP"),
        "reference": str(c.get("Reference") or ""),
    }


def slim_payout(p: dict) -> dict:
    return {
        "id": str(p.get("id") or ""),
        "date": _day(p.get("date")),
        "pence": pence(p.get("amount")),
        "currency": str(p.get("currency") or "GBP"),
        "status": str(p.get("status") or ""),
        "fees_pence": None,      # filled from balance transactions when readable
    }


def slim_dispute(d: dict) -> dict:
    return {
        "id": str(d.get("id") or ""),
        "order_id": str(d.get("order_id") or ""),
        "type": str(d.get("type") or ""),
        "pence": pence(d.get("amount")),
        "currency": str(d.get("currency") or "GBP"),
        "reason": str(d.get("reason") or ""),
        "status": str(d.get("status") or ""),
        "date": _day(d.get("initiated_at") or d.get("evidence_due_by")),
    }


# ---------------------------------------------------------------------------
# Exceptions: creation, identity, evidence
# ---------------------------------------------------------------------------

SEVERITIES = ("critical", "high", "medium", "low")
STATUSES = ("new", "investigating", "explained", "confirmed_error", "corrected", "ignored")


def _exc_id(kind: str, refs: list) -> str:
    """Stable across sweeps: the same underlying facts keep the same id, so a
    status set on Monday survives Tuesday's sweep."""
    return "x" + hashlib.sha1((kind + "|" + "|".join(sorted(str(r) for r in refs)))
                              .encode()).hexdigest()[:12]


def make_exc(kind: str, severity: str, title: str, refs: list, *,
             amount: Optional[int] = None, currency: str = "GBP",
             date: str = "", systems: Optional[list] = None,
             why: str = "", suggestion: str = "",
             evidence: Optional[list] = None,
             computed: Optional[list] = None) -> dict:
    assert severity in SEVERITIES, severity
    return {
        "id": _exc_id(kind, refs), "kind": kind, "severity": severity,
        "title": title, "amount": amount, "currency": currency, "date": date,
        "systems": systems or [], "refs": [str(r) for r in refs],
        "why": why, "suggestion": suggestion,
        "evidence": evidence or [],           # [{eid, system, kind, label, record}]
        "computed": computed or [],           # ["£23,481.72 - £513.76 fees = £22,967.96"]
        "ai": None, "status": "new", "status_note": "",
        "history": [], "created": _now(), "updated": _now(), "stale": False,
    }


def ev(system: str, kind: str, label: str, record: dict, n: int) -> dict:
    """One evidence entry, verbatim. The eid is what the AI must cite."""
    return {"eid": f"E{n}", "system": system, "kind": kind,
            "label": label, "record": record}


def _sev_for_amount(p: Optional[int], base: str) -> str:
    """Materiality raises severity one notch; it never lowers it."""
    if p is not None and abs(p) >= MATERIAL_PENCE:
        return {"high": "critical", "medium": "high", "low": "medium"}.get(base, base)
    return base


# ---------------------------------------------------------------------------
# Deterministic checks. Each takes the cache and returns exceptions. No IO.
# ---------------------------------------------------------------------------

def _live(rec: dict) -> bool:
    """May this Xero record EXPLAIN anything? A voided or deleted record is an
    un-happened one: letting it satisfy a match is how an accidentally voided
    invoice permanently hides a missing sale. (The archetypal false clean:
    reproduced by the review before this filter existed.)"""
    return str(rec.get("status") or "") not in ("VOIDED", "DELETED")


def _order_invoice_index(xinv: dict) -> dict:
    """ACCREC invoices indexed by every normalized token that could name a
    Shopify order: the invoice number, the reference, and any #12345-shaped
    fragments inside either."""
    idx: dict = {}
    for v in xinv.values():
        if v["type"] != "ACCREC" or not _live(v):
            continue
        keys = {norm_ref(v["number"]), norm_ref(v["reference"])}
        for m in re.findall(r"#?\d{4,}", v["number"] + " " + v["reference"]):
            keys.add(norm_ref(m))
        for k in keys:
            if k:
                idx.setdefault(k, []).append(v)
    return idx


def check_orders_vs_invoices(cache: dict) -> list:
    """Every real Shopify sale should be visible in Xero, and at the same
    amount. Matching: order number in the invoice number/reference first, then
    amount + date window + name similarity."""
    out = []
    xinv = cache.get("xero", {}).get("invoices", {})
    orders = cache.get("shopify", {}).get("orders", {})
    idx = _order_invoice_index(xinv)
    by_amount: dict = {}
    for v in xinv.values():
        if v["type"] == "ACCREC" and v["total"] is not None and _live(v):
            by_amount.setdefault((v["total"], v["currency"]), []).append(v)
    claimed: set = set()      # an invoice explains ONE order, not every same-priced one

    for o in orders.values():
        if o["cancelled"] or o["test"]:
            continue
        if o["financial_status"] not in ("paid", "partially_refunded", "partially_paid", "pending"):
            continue
        if o["total"] in (None, 0):
            continue
        hit = None
        for k in (norm_ref(o["name"]), norm_ref(str(o["id"]))):
            if k and idx.get(k):
                hit = idx[k][0]
                break
        if hit is None:
            # Amount + date + name: the invoice may carry its own numbering.
            for v in by_amount.get((o["total"], o["currency"]), []):
                if v["id"] in claimed:
                    continue
                gap = _days_between(o["created_at"], v["date"])
                if gap is not None and gap <= 7:
                    nm = norm_name(o["company"] or o["customer"])
                    if not nm or nm in norm_name(v["contact"]) or norm_name(v["contact"]) in nm:
                        hit = v
                        claimed.add(v["id"])
                        break
        if hit is None:
            sev = _sev_for_amount(o["total"], "high")
            out.append(make_exc(
                "shopify_sale_missing", sev,
                f"Shopify sale {o['name']} ({money(o['total'], o['currency'])}) has no matching Xero invoice",
                [o["id"]], amount=o["total"], currency=o["currency"], date=o["created_at"],
                systems=["shopify", "xero"],
                why=(f"Order {o['name']} is {o['financial_status']} in Shopify, but no ACCREC "
                     "invoice carries its number, and none matches on amount, date and customer."),
                suggestion="Check whether this sale reached Xero at all, or reached it under an unrecognisable reference.",
                evidence=[ev("shopify", "order", f"Order {o['name']}", o, 1)],
                computed=[f"Searched {len(xinv)} Xero invoices for '{o['name']}' and for "
                          f"{money(o['total'], o['currency'])} within 7 days of {o['created_at']}: no match."]))
            continue
        if hit["total"] is not None and o["total"] is not None and hit["total"] != o["total"]:
            diff = o["total"] - hit["total"]
            if abs(diff) > TOLERANCE_PENCE:
                out.append(make_exc(
                    "order_invoice_amount_mismatch", _sev_for_amount(diff, "medium"),
                    f"{o['name']}: Shopify total {money(o['total'], o['currency'])} vs "
                    f"Xero invoice {hit['number'] or hit['id']} {money(hit['total'], hit['currency'])}",
                    [o["id"], hit["id"]], amount=diff, currency=o["currency"],
                    date=o["created_at"], systems=["shopify", "xero"],
                    why="The matched invoice's total differs from the order's total.",
                    suggestion="Compare line items, shipping, discounts and VAT between the two records.",
                    evidence=[ev("shopify", "order", f"Order {o['name']}", o, 1),
                              ev("xero", "invoice", f"Invoice {hit['number'] or hit['id']}", hit, 2)],
                    computed=[f"{money(o['total'], o['currency'])} (Shopify) - "
                              f"{money(hit['total'], hit['currency'])} (Xero) = {money(diff, o['currency'])}"]))
        if (hit.get("tax") is not None and o.get("tax") is not None
                and abs(hit["tax"] - o["tax"]) > TOLERANCE_PENCE):
            tdiff = o["tax"] - hit["tax"]
            out.append(make_exc(
                "order_invoice_tax_mismatch", "medium",
                f"{o['name']}: VAT differs - Shopify {money(o['tax'], o['currency'])} vs "
                f"Xero {money(hit['tax'], hit['currency'])}",
                [o["id"], hit["id"], "tax"], amount=tdiff, currency=o["currency"],
                date=o["created_at"], systems=["shopify", "xero"],
                why="The tax recorded in Xero does not equal the tax Shopify charged.",
                suggestion="Check the tax rate applied on the Xero invoice lines.",
                evidence=[ev("shopify", "order", f"Order {o['name']}", o, 1),
                          ev("xero", "invoice", f"Invoice {hit['number'] or hit['id']}", hit, 2)],
                computed=[f"VAT: {money(o['tax'], o['currency'])} (Shopify) - "
                          f"{money(hit['tax'], hit['currency'])} (Xero) = {money(tdiff, o['currency'])}"]))
    return out


def check_refunds(cache: dict) -> list:
    """A Shopify refund is money leaving; Xero must show it as an ACCREC credit
    note or a refund-shaped bank line."""
    out = []
    orders = cache.get("shopify", {}).get("orders", {})
    notes = cache.get("xero", {}).get("credit_notes", {})
    bank = cache.get("xero", {}).get("bank_transactions", {})
    for o in orders.values():
        for r in o.get("refunds", []):
            if not r["pence"]:
                continue
            hit = None
            for c in notes.values():
                if c["type"] != "ACCRECCREDIT" or c["total"] != r["pence"] or not _live(c):
                    continue
                gap = _days_between(r["created_at"], c["date"])
                if gap is not None and gap <= 10:
                    hit = ("credit note " + (c["number"] or c["id"]), c)
                    break
            if hit is None:
                for t in bank.values():
                    if t["type"] != "SPEND" or t["pence"] != r["pence"] or not _live(t):
                        continue
                    gap = _days_between(r["created_at"], t["date"])
                    if gap is not None and gap <= 10:
                        hit = ("bank payment " + t["id"], t)
                        break
            if hit is None:
                out.append(make_exc(
                    "shopify_refund_missing", _sev_for_amount(r["pence"], "high"),
                    f"Refund of {money(r['pence'], o['currency'])} on {o['name']} has no Xero record",
                    [o["id"], r["id"]], amount=r["pence"], currency=o["currency"],
                    date=r["created_at"], systems=["shopify", "xero"],
                    why=("Shopify refunded this amount, but no ACCREC credit note and no SPEND "
                         "bank transaction matches it within 10 days."),
                    suggestion="Record the refund in Xero, or find where it was recorded under a different amount.",
                    evidence=[ev("shopify", "order", f"Order {o['name']}", o, 1),
                              ev("shopify", "refund", f"Refund on {r['created_at']}",
                                 {**r, "order": o["name"]}, 2)],
                    computed=[f"Searched {len(notes)} credit notes and {len(bank)} bank "
                              f"transactions for {money(r['pence'], o['currency'])} within 10 days "
                              f"of {r['created_at']}: no match."]))
    return out


def check_payouts_vs_bank(cache: dict) -> list:
    """Every Shopify payout must land in the bank, once, at its exact amount.
    (Only runs when the payouts scope is granted and the store uses Shopify
    Payments; otherwise the sweep records that this check could not run.)"""
    out = []
    payouts = cache.get("shopify", {}).get("payouts", {})
    bank = cache.get("xero", {}).get("bank_transactions", {})
    receives: dict = {}
    for t in bank.values():
        if t["type"] == "RECEIVE" and t["pence"] is not None and _live(t):
            receives.setdefault(t["pence"], []).append(t)
    claimed: set = set()
    horizon = _cutoff_day(FETCH_DAYS)
    for p in payouts.values():
        if p["status"] in ("canceled", "failed") or p["pence"] in (None, 0):
            continue
        # Older than the bank lines we hold: "no matching transaction" would
        # only mean "we did not fetch the transaction". Shopify hands back
        # payouts with no window, so without this the check invents a
        # high-severity missing deposit for every payout that outlives the
        # bank data it is matched against.
        if str(p.get("date") or "") < horizon:
            continue
        hit = None
        for t in receives.get(p["pence"], []):
            gap = _days_between(p["date"], t["date"])
            if gap is not None and gap <= 4 and t["id"] not in claimed:
                hit = t
                claimed.add(t["id"])
                break
        if hit is None and p.get("fees_pence"):
            # The spec's own worked example: the deposit differs from the
            # payout by exactly the fees. That is an explanation, not an
            # error, and it is arithmetic, so the deterministic layer says it.
            for adjusted in (p["pence"] - p["fees_pence"], p["pence"] + p["fees_pence"]):
                for t in receives.get(adjusted, []):
                    gap = _days_between(p["date"], t["date"])
                    if gap is not None and gap <= 4 and t["id"] not in claimed:
                        claimed.add(t["id"])
                        out.append(make_exc(
                            "payout_explained_by_fees", "low",
                            f"Payout {p['id']}: the bank shows {money(adjusted, p['currency'])}, "
                            f"which is the payout adjusted by exactly the fees "
                            f"({money(p['fees_pence'], p['currency'])})",
                            [p["id"], t["id"]], amount=p["fees_pence"], currency=p["currency"],
                            date=p["date"], systems=["shopify", "xero"],
                            why="The gap between the payout and the deposit equals the recorded fees to the penny.",
                            suggestion="Confirm the fees are posted to their expense account in Xero.",
                            evidence=[ev("shopify", "payout", f"Payout {p['id']}", p, 1),
                                      ev("xero", "bank_transaction", f"Bank txn {t['id']}", t, 2)],
                            computed=[f"{money(p['pence'], p['currency'])} payout "
                                      f"{'-' if adjusted < p['pence'] else '+'} "
                                      f"{money(p['fees_pence'], p['currency'])} fees = "
                                      f"{money(adjusted, p['currency'])} = the deposit."]))
                        hit = t
                        break
                if hit is not None:
                    break
        if hit is None:
            out.append(make_exc(
                "payout_missing_from_bank", _sev_for_amount(p["pence"], "high"),
                f"Shopify payout of {money(p['pence'], p['currency'])} on {p['date']} "
                "has no matching bank transaction in Xero",
                [p["id"]], amount=p["pence"], currency=p["currency"], date=p["date"],
                systems=["shopify", "xero"],
                why="No RECEIVE bank transaction matches this payout's amount within 4 days.",
                suggestion=("Check the bank feed for the deposit; if it arrived at a different "
                            "amount, fees or a currency conversion may explain the gap."),
                evidence=[ev("shopify", "payout", f"Payout {p['id']}", p, 1)],
                computed=[f"Searched {len(bank)} Xero bank transactions for "
                          f"{money(p['pence'], p['currency'])} within 4 days of {p['date']}: no match."]))
        elif hit.get("is_reconciled") is False:
            out.append(make_exc(
                "payout_bank_unreconciled", "medium",
                f"Bank deposit for payout {p['id']} ({money(p['pence'], p['currency'])}) is not reconciled",
                [p["id"], hit["id"]], amount=p["pence"], currency=p["currency"], date=hit["date"],
                systems=["shopify", "xero"],
                why="The deposit exists but its Xero bank transaction is unreconciled.",
                suggestion="Reconcile the bank line in Xero.",
                evidence=[ev("shopify", "payout", f"Payout {p['id']}", p, 1),
                          ev("xero", "bank_transaction", f"Bank txn {hit['id']}", hit, 2)]))
    return out


def check_stale_unreconciled(cache: dict) -> list:
    """A bank line sitting unreconciled for weeks is where errors hide."""
    out = []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for t in cache.get("xero", {}).get("bank_transactions", {}).values():
        if t["is_reconciled"] or t["status"] == "DELETED" or t["pence"] in (None, 0):
            continue
        age = _days_between(t["date"], today)
        if age is None or age < STALE_UNRECONCILED_DAYS:
            continue
        out.append(make_exc(
            "stale_unreconciled", _sev_for_amount(t["pence"], "low"),
            f"Bank transaction of {money(t['pence'], t['currency'])} from {t['date']} "
            f"is still unreconciled after {age} days",
            [t["id"]], amount=t["pence"], currency=t["currency"], date=t["date"],
            systems=["xero"],
            why=f"Unreconciled for {age} days (threshold {STALE_UNRECONCILED_DAYS}).",
            suggestion="Reconcile it, or investigate why it cannot be matched.",
            evidence=[ev("xero", "bank_transaction", f"Bank txn {t['id']}", t, 1)]))
    return out


def check_duplicates(cache: dict) -> list:
    """Same bill twice is the classic way a supplier gets paid twice. Cluster
    on the normalized invoice number, then on (supplier, amount, close dates)
    for bills whose numbers differ only by typo."""
    out = []
    bills = [v for v in cache.get("xero", {}).get("invoices", {}).values()
             if v["type"] == "ACCPAY" and v["status"] not in ("VOIDED", "DELETED")]
    by_num: dict = {}
    for v in bills:
        k = norm_ref(v["number"])
        if k:
            by_num.setdefault(k, []).append(v)
    for k, group in by_num.items():
        if len(group) < 2:
            continue
        total = sum(v["total"] or 0 for v in group)
        out.append(make_exc(
            "duplicate_bill_number", _sev_for_amount(max(v["total"] or 0 for v in group), "high"),
            f"Bill number '{group[0]['number']}' appears {len(group)} times "
            f"({', '.join(sorted({g['contact'] for g in group}))})",
            [v["id"] for v in group], amount=total, currency=group[0]["currency"],
            date=group[0]["date"], systems=["xero"],
            why="Two or more ACCPAY bills share the same normalized invoice number.",
            suggestion="Void the duplicate, or confirm these are genuinely distinct documents.",
            evidence=[ev("xero", "bill", f"Bill {v['number']} ({v['contact']})", v, i + 1)
                      for i, v in enumerate(group)],
            computed=[f"Normalized number '{k}' matches {len(group)} bills."]))
    seen_pairs: set = set()
    by_contact: dict = {}
    for v in bills:
        by_contact.setdefault((norm_name(v["contact"]), v["total"]), []).append(v)
    for (cname, amt), group in by_contact.items():
        if len(group) < 2 or amt in (None, 0):
            continue
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if norm_ref(a["number"]) == norm_ref(b["number"]) and norm_ref(a["number"]):
                    continue                    # already reported above
                gap = _days_between(a["date"], b["date"])
                if gap is None or gap > 14:
                    continue
                key = tuple(sorted((a["id"], b["id"])))
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                out.append(make_exc(
                    "possible_duplicate_bill", _sev_for_amount(amt, "medium"),
                    f"Two bills from {a['contact'] or 'the same supplier'} for "
                    f"{money(amt, a['currency'])} within {gap} days "
                    f"({a['number'] or 'no number'} / {b['number'] or 'no number'})",
                    [a["id"], b["id"]], amount=amt, currency=a["currency"], date=a["date"],
                    systems=["xero"],
                    why="Same supplier, same amount, days apart, different numbers.",
                    suggestion="Open both bills and compare their line items and source documents.",
                    evidence=[ev("xero", "bill", f"Bill {a['number'] or a['id']}", a, 1),
                              ev("xero", "bill", f"Bill {b['number'] or b['id']}", b, 2)]))
    return out


def check_overpayments(cache: dict) -> list:
    """Payments against one invoice summing past its total: a duplicate
    payment, or a misallocation."""
    out = []
    xinv = cache.get("xero", {}).get("invoices", {})
    by_invoice: dict = {}
    for p in cache.get("xero", {}).get("payments", {}).values():
        if p["status"] == "DELETED" or not p["invoice_id"]:
            continue
        by_invoice.setdefault(p["invoice_id"], []).append(p)
    for inv_id, pays in by_invoice.items():
        v = xinv.get(inv_id)
        if not v or v["total"] in (None, 0):
            continue
        paid = sum(p["pence"] or 0 for p in pays)
        credited = v.get("credited_pence") or 0
        if paid + credited > v["total"] + TOLERANCE_PENCE:
            over = paid + credited - v["total"]
            out.append(make_exc(
                "overpaid_invoice", _sev_for_amount(over, "high"),
                f"Invoice {v['number'] or inv_id} ({v['contact']}) is over-allocated by "
                f"{money(over, v['currency'])}",
                [inv_id], amount=over, currency=v["currency"], date=v["date"],
                systems=["xero"],
                why=f"{len(pays)} payments plus credits exceed the invoice total.",
                suggestion="Look for a duplicated payment or a payment allocated to the wrong invoice.",
                evidence=([ev("xero", "invoice", f"Invoice {v['number'] or inv_id}", v, 1)]
                          + [ev("xero", "payment", f"Payment {p['id']}", p, i + 2)
                             for i, p in enumerate(pays[:8])]),
                computed=[f"Payments {money(paid, v['currency'])} + credits "
                          f"{money(credited, v['currency'])} - invoice total "
                          f"{money(v['total'], v['currency'])} = {money(over, v['currency'])} over."]))
    return out


def check_gmail_docs(cache: dict, docs: dict) -> list:
    """Documents found in Gmail versus the books. Extraction happened earlier
    (deterministic text first, AI on scans); by the time this check runs a doc
    is already plain fields, and matching is arithmetic."""
    out = []
    xinv = cache.get("xero", {}).get("invoices", {})
    payments = cache.get("xero", {}).get("payments", {})
    num_idx: dict = {}
    for v in xinv.values():
        if not _live(v):
            continue
        for k in (norm_ref(v["number"]), norm_ref(v["reference"])):
            if k:
                num_idx.setdefault(k, []).append(v)
    # Credit notes carry their own numbering: a CN filed correctly in Xero
    # must not read as "missing" just because it is not an invoice.
    for c in cache.get("xero", {}).get("credit_notes", {}).values():
        if not _live(c):
            continue
        for k in (norm_ref(c.get("number")), norm_ref(c.get("reference"))):
            if k:
                num_idx.setdefault(k, []).append(c)
    for d in docs.values():
        if d.get("ignored") or d.get("doc_type") in (None, "", "other"):
            continue
        ident = [d.get("source_key") or ""]
        scan = not d.get("verified", True)
        scan_note = ("" if not scan else
                     " NOTE: read by AI from a SCANNED document with no text layer to "
                     "verify against; treat the extracted numbers as a lead, not a fact.")
        base_ev = [ev("gmail", "document",
                      f"{d.get('doc_type')} '{d.get('filename') or d.get('subject')}' "
                      f"from {d.get('from') or 'unknown sender'} on {_day(d.get('date'))}",
                      {k: d.get(k) for k in ("doc_type", "filename", "subject", "from", "date",
                                             "counterparty", "invoice_numbers", "total_pence",
                                             "currency", "extracted_by")}, 1)]
        if d.get("doc_type") in ("supplier_invoice", "customer_invoice", "credit_note"):
            nums = [n for n in (d.get("invoice_numbers") or []) if norm_ref(n)]
            missing = [n for n in nums if norm_ref(n) not in num_idx]
            if nums and len(missing) == len(nums):
                amt = d.get("total_pence")
                # A scan has no text layer to validate the extraction against,
                # so nothing from it may carry more than MEDIUM: an invented
                # invoice number must not mint a critical.
                base_sev = "medium" if scan else _sev_for_amount(amt, "high")
                exc = make_exc(
                    "gmail_doc_missing_from_xero", base_sev,
                    f"{d.get('doc_type', 'document').replace('_', ' ').title()} "
                    f"{nums[0]}{' and others' if len(nums) > 1 else ''} found in Gmail "
                    "but not in Xero",
                    ident + nums, amount=amt, currency=d.get("currency") or "GBP",
                    date=_day(d.get("date")), systems=["gmail", "xero"],
                    why=(f"The document names invoice number(s) {', '.join(nums)}; none of them "
                         f"match any of {len(xinv)} Xero invoice numbers or references."
                         + scan_note),
                    suggestion="Enter the document in Xero, or confirm it was superseded or is not for this business.",
                    evidence=base_ev,
                    computed=[f"Normalized lookups tried: {', '.join(norm_ref(n) for n in nums)}."])
                if scan:
                    exc["basis"] = "ai_extraction"
                out.append(exc)
        if d.get("doc_type") == "remittance":
            rems = _check_remittance(d, base_ev, num_idx, payments)
            if scan:
                for e in rems:
                    e["basis"] = "ai_extraction"
                    if e["severity"] in ("critical", "high"):
                        e["severity"] = "medium"
                    e["why"] += scan_note
            out.extend(rems)
    return out


def _check_remittance(d: dict, base_ev: list, num_idx: dict, payments: dict) -> list:
    """One remittance advice, taken apart: does each referenced invoice exist,
    do the allocation amounts fit, and did a matching payment reach Xero?
    Partial payments and multi-invoice remittances are the normal case."""
    out = []
    ident = [d.get("source_key") or ""]
    cur = d.get("currency") or "GBP"
    total = d.get("total_pence")
    lines = d.get("invoice_lines") or []      # [{number, pence}]
    n = len(base_ev)
    line_sum = sum(l.get("pence") or 0 for l in lines) if lines else None
    computed = []
    if total is not None and line_sum is not None and lines:
        gap = total - line_sum
        computed.append(f"Remittance total {money(total, cur)} - listed invoice lines "
                        f"{money(line_sum, cur)} = {money(gap, cur)}"
                        + ("" if abs(gap) > TOLERANCE_PENCE else " (consistent)"))
    for l in lines:
        v = (num_idx.get(norm_ref(l.get("number"))) or [None])[0]
        if v is None:
            out.append(make_exc(
                "remittance_unknown_invoice", "high",
                f"Remittance from {d.get('counterparty') or d.get('from') or 'unknown'} "
                f"references invoice {l.get('number')} which is not in Xero",
                ident + [l.get("number")], amount=l.get("pence"), currency=cur,
                date=_day(d.get("date")), systems=["gmail", "xero"],
                why="The payer says they paid this invoice; Xero has no invoice with that number.",
                suggestion="Find the invoice (was it raised outside Xero?) or query the payer.",
                evidence=base_ev, computed=computed))
        elif (l.get("pence") is not None and v["due_pence"] is not None
              and v["paid_pence"] is not None
              and l["pence"] not in (v["total"], v["due_pence"], v["paid_pence"])
              and abs(l["pence"] - (v["total"] or 0)) > TOLERANCE_PENCE):
            out.append(make_exc(
                "remittance_amount_mismatch", "medium",
                f"Remittance pays {money(l['pence'], cur)} against invoice "
                f"{l.get('number')} whose total is {money(v['total'], v['currency'])}",
                ident + [l.get("number"), "amt"], amount=l["pence"] - (v["total"] or 0),
                currency=cur, date=_day(d.get("date")), systems=["gmail", "xero"],
                why="The paid amount matches neither the invoice total, the amount due, nor the amount already paid - possibly a partial payment, a deduction, or an error.",
                suggestion="Check for credit notes, early-settlement discounts or short payment.",
                evidence=base_ev + [ev("xero", "invoice", f"Invoice {v['number']}", v, len(base_ev) + 1)],
                computed=computed + [
                    f"Line {money(l['pence'], cur)} vs invoice total {money(v['total'], v['currency'])}, "
                    f"due {money(v['due_pence'], v['currency'])}, paid {money(v['paid_pence'], v['currency'])}."]))
    if total:
        pay_hit = None
        for p in payments.values():
            if p["pence"] == total:
                gap = _days_between(_day(d.get("date")), p["date"])
                if gap is not None and gap <= 14:
                    pay_hit = p
                    break
        if pay_hit is None and lines:
            hits = sum(1 for l in lines
                       if any(p["pence"] == l.get("pence")
                              and norm_ref(p["invoice_number"]) == norm_ref(l.get("number"))
                              for p in payments.values()))
            if hits == len(lines):
                pay_hit = {"split": True}
        if pay_hit is None:
            out.append(make_exc(
                "remittance_payment_missing", _sev_for_amount(total, "high"),
                f"Remittance for {money(total, cur)} from "
                f"{d.get('counterparty') or d.get('from') or 'unknown'} has no matching Xero payment",
                ident + ["pay"], amount=total, currency=cur,
                date=_day(d.get("date")), systems=["gmail", "xero"],
                why=("No single Xero payment equals the remitted total within 14 days, and the "
                     "listed invoices are not each individually settled at their stated amounts."),
                suggestion="Check the bank feed for the receipt and record/allocate the payment.",
                evidence=base_ev, computed=computed))
    return out


def check_disputes(cache: dict) -> list:
    """A chargeback is money leaving with a story attached; the books must
    show it. Matched against SPEND bank lines and ACCREC credit notes."""
    out = []
    bank = cache.get("xero", {}).get("bank_transactions", {})
    notes = cache.get("xero", {}).get("credit_notes", {})
    horizon = _cutoff_day(FETCH_DAYS)
    for d in cache.get("shopify", {}).get("disputes", {}).values():
        if d["status"] in ("won",) or d["pence"] in (None, 0):
            continue                       # a won dispute takes nothing
        if str(d.get("date") or "") < horizon:
            continue                       # older than the books we hold
        hit = False
        for t in bank.values():
            if t["type"] == "SPEND" and t["pence"] == d["pence"] and _live(t):
                gap = _days_between(d["date"], t["date"])
                if gap is not None and gap <= 21:
                    hit = True
                    break
        if not hit:
            for c in notes.values():
                if c["type"] == "ACCRECCREDIT" and c["total"] == d["pence"] and _live(c):
                    gap = _days_between(d["date"], c["date"])
                    if gap is not None and gap <= 21:
                        hit = True
                        break
        if not hit:
            out.append(make_exc(
                "chargeback_missing_from_xero", _sev_for_amount(d["pence"], "high"),
                f"Chargeback of {money(d['pence'], d['currency'])} "
                f"({d['reason'] or d['type'] or 'dispute'}, {d['status']}) has no Xero record",
                [d["id"]], amount=d["pence"], currency=d["currency"], date=d["date"],
                systems=["shopify", "xero"],
                why="No SPEND bank transaction and no credit note matches this dispute's amount within 21 days.",
                suggestion="Record the chargeback (and its fee) in Xero, or confirm it is still pending settlement.",
                evidence=[ev("shopify", "dispute", f"Dispute {d['id']}", d, 1)]))
    return out


def check_xero_orphan_sales(cache: dict) -> list:
    """The other direction of section 7: a sales record in Xero that no
    Shopify order explains. LOW by design - invoicing off-Shopify is
    legitimate - and if MOST invoices are unmatched that is one systemic
    finding about numbering, not hundreds of per-invoice alarms."""
    orders = cache.get("shopify", {}).get("orders", {})
    if not orders:
        return []                          # no Shopify picture; silence beats noise
    xinv = cache.get("xero", {}).get("invoices", {})
    cutoff = _cutoff_day()
    order_keys = set()
    order_amounts = set()
    for o in orders.values():
        order_keys.add(norm_ref(o["name"]))
        order_keys.add(norm_ref(str(o["id"])))
        if o["total"] is not None:
            order_amounts.add((o["total"], o["currency"]))
    candidates = [v for v in xinv.values()
                  if v["type"] == "ACCREC" and v["status"] in ("AUTHORISED", "PAID")
                  and v["date"] >= cutoff and v["total"] not in (None, 0)]
    orphans = []
    for v in candidates:
        keys = {norm_ref(v["number"]), norm_ref(v["reference"])}
        for m in re.findall(r"#?\d{4,}", v["number"] + " " + v["reference"]):
            keys.add(norm_ref(m))
        if keys & order_keys:
            continue
        if (v["total"], v["currency"]) in order_amounts:
            continue                       # amount-matched somewhere; the forward check owns it
        orphans.append(v)
    if candidates and len(orphans) > max(10, len(candidates) * 3 // 10):
        return [make_exc(
            "invoice_numbering_unlinked", "medium",
            f"{len(orphans)} of {len(candidates)} recent Xero sales invoices reference no "
            "Shopify order at all",
            ["systemic"], systems=["shopify", "xero"],
            why=("Most sales invoices carry numbers and references that never mention a "
                 "Shopify order, so per-invoice matching cannot work."),
            suggestion=("If these sales ARE Shopify orders, put the order number in the "
                        "invoice reference; if they are genuinely off-Shopify sales, this "
                        "is expected and can be ignored with a note."),
            evidence=[ev("xero", "invoice", f"Invoice {v['number'] or v['id']}", v, i + 1)
                      for i, v in enumerate(orphans[:8])],
            computed=[f"{len(orphans)} unmatched of {len(candidates)} in the window."])]
    return [make_exc(
        "xero_sale_without_shopify", "low",
        f"Xero invoice {v['number'] or v['id']} ({money(v['total'], v['currency'])}, "
        f"{v['contact'] or 'no contact'}) matches no Shopify order",
        [v["id"]], amount=v["total"], currency=v["currency"], date=v["date"],
        systems=["shopify", "xero"],
        why="No order shares its number, reference or amount. An off-Shopify sale is legitimate; an invented one is not.",
        suggestion="Confirm where this sale came from.",
        evidence=[ev("xero", "invoice", f"Invoice {v['number'] or v['id']}", v, 1)])
        for v in orphans[:40]]


def prune(cache: dict, docs: dict, store: dict) -> list:
    """Drop what can no longer be reconciled. Returns notes, because a tool
    that quietly deletes financial records is worse than one that keeps
    them."""
    notes = []
    cutoff = _cutoff_day(CACHE_KEEP_DAYS)
    # A record an OPEN discrepancy is built from is evidence, not history.
    # Delete it and the next sweep cannot re-detect the finding; the merge sees
    # a check that ran and did not emit it, and marks it "no longer detected".
    # The discrepancy would drop off the board looking resolved, which is the
    # one outcome this tool exists to prevent.
    keep = set()
    for e in (store.get("exceptions") or {}).values():
        if e.get("stale") or e.get("status") not in ("new", "investigating"):
            continue
        for r in (e.get("refs") or []):
            keep.add(str(r))
    gone: list = []

    undated = []

    def _sweep_bucket(rows, datekey):
        if not rows:
            return
        old = []
        for k, v in rows.items():
            if str(k) in keep:
                continue
            day = str(v.get(datekey) or "")[:10]
            if len(day) != 10:
                # No readable date. "" sorts before every cutoff, so the
                # obvious comparison would DESTROY exactly the records we
                # understand least. Keep them and say so: the Shopify payout
                # and dispute buckets carry no API-side date filter, so this
                # is reachable in a way the Xero buckets are not.
                undated.append(str(k))
                continue
            if day < cutoff:
                old.append(k)
        for k in old:
            rows.pop(k, None)
        gone.extend(str(k) for k in old)

    for bucket in ("invoices", "credit_notes", "payments", "bank_transactions"):
        _sweep_bucket(cache.get("xero", {}).get(bucket), "date")
    shop = cache.get("shopify", {})
    _sweep_bucket(shop.get("orders"), "created_at")
    # Payouts and disputes were pulled with no window at all and pruned by
    # nothing, so they outlived the bank lines they are matched against: a
    # payout whose deposit had been dropped read as "no matching bank
    # transaction in Xero" at high severity, for a deposit that was there all
    # along.
    _sweep_bucket(shop.get("payouts"), "date")
    _sweep_bucket(shop.get("disputes"), "date")
    if gone:
        notes.append(f"{len(gone)} records older than {CACHE_KEEP_DAYS} days were dropped from "
                     "the local copy; they are still in Xero and Shopify.")
    if undated:
        notes.append(f"{len(undated)} cached records carry no readable date, so their age "
                     "could not be judged and they were kept.")
    # Remembered so the NEXT sweep can tell "we deleted our copy" from "the
    # discrepancy went away", which are not the same fact and must not share a
    # sentence. Capped: this is a hint for wording, not a second ledger.
    store["retention_dropped"] = sorted(set(gone))[:3000]

    doc_cut = _cutoff_day(DOCS_KEEP_DAYS)
    stale_docs = [k for k, d in docs.items() if _day(d.get("date")) and _day(d.get("date")) < doc_cut]
    for k in stale_docs:
        docs.pop(k, None)
    if stale_docs:
        notes.append(f"{len(stale_docs)} documents older than {DOCS_KEEP_DAYS} days were "
                     "dropped; the originals are untouched in the mailbox.")

    # A settled discrepancy keeps its evidence for a year, then keeps only the
    # story: what it was, what was decided, by whom.
    closed_cut = _cutoff_day(CLOSED_KEEP_DAYS)
    slimmed = 0
    for e in (store.get("exceptions") or {}).values():
        if e.get("status") in ("new", "investigating"):
            continue
        if str(e.get("updated") or "")[:10] >= closed_cut:
            continue
        if e.get("evidence"):
            e["evidence"] = []
            e["evidence_dropped"] = True
            slimmed += 1
        hist = e.get("history") or []
        if len(hist) > 40:
            e["history"] = hist[:5] + hist[-35:]
    if slimmed:
        notes.append(f"{slimmed} settled discrepancies older than {CLOSED_KEEP_DAYS} days kept "
                     "their decision and lost their copied records.")
    return notes


ALL_CHECKS = [check_orders_vs_invoices, check_refunds, check_payouts_vs_bank,
              check_stale_unreconciled, check_duplicates, check_overpayments,
              check_disputes, check_xero_orphan_sales]

# Which exception kinds each check owns. The stale-marking loop only trusts a
# kind whose check actually ran: keep this in step when adding checks (the
# suite asserts every kind ever emitted is claimed by exactly one check).
CHECK_KINDS = {
    "check_orders_vs_invoices": {"shopify_sale_missing", "order_invoice_amount_mismatch",
                                 "order_invoice_tax_mismatch"},
    "check_refunds": {"shopify_refund_missing"},
    "check_payouts_vs_bank": {"payout_missing_from_bank", "payout_bank_unreconciled",
                              "payout_explained_by_fees"},
    "check_stale_unreconciled": {"stale_unreconciled"},
    "check_duplicates": {"duplicate_bill_number", "possible_duplicate_bill"},
    "check_overpayments": {"overpaid_invoice"},
    "check_disputes": {"chargeback_missing_from_xero"},
    "check_xero_orphan_sales": {"xero_sale_without_shopify", "invoice_numbering_unlinked"},
    "check_gmail_docs": {"gmail_doc_missing_from_xero", "remittance_unknown_invoice",
                         "remittance_amount_mismatch", "remittance_payment_missing"},
}


# ---------------------------------------------------------------------------
# Gmail document discovery + extraction
# ---------------------------------------------------------------------------

_FIN_WORDS = re.compile(
    r"(?i)\b(remittance|invoice|statement|credit note|payment advice|"
    r"payment confirmation|purchase order|receipt|refund)\b")
_AMOUNT_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:,\d{3})*\.\d{2})(?!\d)")
_INVNUM_RE = re.compile(r"(?i)\b((?:inv|in|si|pi|cn)[-# ]?\d{3,10}|\d{4,8})\b")


def candidates_in_thread(t: dict, known: set) -> list:
    """The PDF attachments in one fetched thread that we have not read yet.
    Pure: the fetching is the caller's problem, so this is testable against a
    plain dict."""
    out = []
    subject = str(t.get("subject") or "")
    for m in (t.get("messages") or []):
        for f in (m.get("files") or []):
            name = str(f.get("name") or "")
            if not name.lower().endswith(".pdf"):
                continue
            key = f"{m.get('id')}:{f.get('id')}"
            if key in known:
                continue
            out.append({"source_key": key, "thread_id": t.get("id"),
                        "message_id": m.get("id"), "attachment_id": f.get("id"),
                        "filename": name, "size": f.get("size") or 0,
                        "subject": subject,
                        "from": str(m.get("from_email") or t.get("from_email") or ""),
                        "date": str(m.get("at") or t.get("last_at") or "")})
    return out


async def find_doc_candidates(known: set, seen_threads: set,
                              cap: Optional[int] = None) -> tuple:
    """Ask the ACCOUNTS mailbox what has arrived.

    Returns (candidates, threads_read, search_ok, listing_complete).
      * threads_read holds ONLY threads actually fetched: one that raised must
        come back next sweep rather than being written off as looked at.
      * search_ok is False when the mailbox could not be read at all, so the
        caller can say so instead of reporting a clean sweep.
      * listing_complete is False when Gmail had more matches than one listing
        returns, which the merchant is told rather than left to assume.

    Candidates come back NEWEST FIRST. Gmail hands back an unordered set, and
    with a per-sweep budget an arbitrary 40 threads means the newest invoice
    can sit unread behind a year of old post."""
    if _mail_search is None or _mail_thread is None:
        return [], set(), False, True
    # Read at CALL time, not bound as a default: a default argument captures
    # the value at import, so the env setting could never actually be changed.
    cap = THREADS_PER_SWEEP if cap is None else cap
    query = MAIL_QUERY.format(days=WINDOW_DAYS)
    complete_flag: list = []
    try:
        ids = await _mail_search(query, 200, complete_flag)
    except Exception:
        logger.exception("recon: the accounts mailbox search failed")
        return [], set(), False, True
    complete = complete_flag[0] if complete_flag else True
    fresh = [i for i in ids if i not in seen_threads]
    # Gmail thread ids sort by age (they are ordered hex), so the newest are
    # the largest. Sorting by length first keeps that true across id widths.
    fresh.sort(key=lambda i: (len(str(i)), str(i)), reverse=True)
    out, read = [], set()
    for tid in fresh[:cap]:
        try:
            t = await _mail_thread(tid)
        except Exception:
            logger.exception("recon: could not read thread %s", tid)
            continue
        read.add(tid)
        out.extend(candidates_in_thread(t, known))
    out.sort(key=lambda c: str(c.get("date") or ""), reverse=True)
    return out, read, True, complete


def _pdf_text(data: bytes) -> str:
    try:
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(data)
        parts = []
        for i in range(min(len(doc), 12)):
            parts.append(doc[i].get_textpage().get_text_range())
        return "\n".join(parts)
    except Exception:
        logger.exception("recon: pdf text extraction failed")
        return ""


def parse_doc_text(text: str, subject: str = "", sender: str = "") -> dict:
    """Deterministic extraction: regex over the text layer. Good enough for
    born-digital PDFs; scans get the AI pass instead."""
    low = (subject + "\n" + text).lower()
    if "remittance" in low or "payment advice" in low:
        dtype = "remittance"
    elif "credit note" in low:
        dtype = "credit_note"
    elif "statement" in low:
        dtype = "statement"
    elif "invoice" in low:
        dtype = "supplier_invoice"
    else:
        dtype = "other"
    amounts = [pence(a) for a in _AMOUNT_RE.findall(text)]
    amounts = [a for a in amounts if a]
    nums = []
    for m in _INVNUM_RE.findall(text[:6000]):
        if m.lower() not in ("2024", "2025", "2026") and m not in nums:
            nums.append(m)
    return {"doc_type": dtype, "invoice_numbers": nums[:12],
            "total_pence": max(amounts) if amounts else None,
            "amounts": sorted(set(amounts), reverse=True)[:12],
            "currency": "GBP" if "£" in text or "gbp" in low else
                        ("USD" if "$" in text else "EUR" if "€" in text else "GBP"),
            "invoice_lines": [], "counterparty": "", "extracted_by": "text",
            "verified": True}


_DOC_TOOL = {
    "name": "record_document",
    "description": "Record what this financial document actually says. Use null for anything the document does not state. NEVER guess or infer a number that is not printed in the document.",
    "input_schema": {
        "type": "object",
        "properties": {
            "doc_type": {"type": "string", "enum": [
                "remittance", "supplier_invoice", "customer_invoice", "credit_note",
                "statement", "payment_confirmation", "purchase_order", "other"]},
            "counterparty": {"type": "string", "description": "The other business named on the document"},
            "currency": {"type": "string"},
            "total": {"type": ["string", "null"], "description": "The document's principal total, digits exactly as printed"},
            "invoice_numbers": {"type": "array", "items": {"type": "string"}},
            "invoice_lines": {"type": "array", "items": {"type": "object", "properties": {
                "number": {"type": "string"}, "amount": {"type": ["string", "null"]}},
                "required": ["number"]}},
            "payment_date": {"type": ["string", "null"]},
            "payment_reference": {"type": ["string", "null"]},
            "notes": {"type": "string"},
        },
        "required": ["doc_type", "currency", "invoice_numbers"],
    },
}

_DOC_SYSTEM = (
    "You read one financial document for a reconciliation audit. Report ONLY what is "
    "printed in the document. Copy numbers digit for digit. If a field is not stated, "
    "return null for it. You are recording evidence, not interpreting it: no guesses, "
    "no derived values, no filling in of blanks.")


async def extract_doc(candidate: dict) -> Optional[dict]:
    """Fetch one attachment and turn it into fields. Text layer first (free,
    exact); the AI reads it only when the PDF is a scan - and anything the AI
    returns that the text layer COULD have shown is cross-checked against it."""
    if _gmail_bytes is None:
        return None
    if candidate.get("size") and candidate["size"] > DOC_BYTES_MAX:
        return {**candidate, "doc_type": "other", "ignored": True,
                "note": "attachment larger than the size cap"}
    try:
        data = await _gmail_bytes(candidate["message_id"], candidate["attachment_id"])
    except Exception:
        logger.exception("recon: attachment fetch failed for %s", candidate.get("source_key"))
        return None
    # The same PDF forwarded twice is one document, not two discrepancies:
    # content-hash it, and a repeat records where else it arrived.
    digest = hashlib.sha1(data).hexdigest()
    if _load_docs is not None:
        for k, other in _load_docs().items():
            if other.get("sha1") == digest and k != candidate.get("source_key"):
                return {**candidate, "sha1": digest, "doc_type": "other", "ignored": True,
                        "duplicate_of": k,
                        "note": "same content as a document already read"}
    candidate = {**candidate, "sha1": digest}
    # OFF the event loop: pypdfium2 chewing an 8MB scan is pure CPU, and this
    # process also answers Shopify's order webhook inside a 5-second window.
    text = await asyncio.to_thread(_pdf_text, data)
    if len(text.strip()) >= 120:
        parsed = parse_doc_text(text, candidate.get("subject", ""), candidate.get("from", ""))
        # The text layer told us the type; a remittance's allocation table is
        # worth an AI read even when text exists, because its rows are the one
        # structure regex cannot be trusted to pair up correctly.
        if parsed["doc_type"] == "remittance" and _ai_call is not None:
            ai = await _ai_extract(data, text)
            if ai:
                parsed = _merge_extractions(parsed, ai, text)
        return {**candidate, **parsed, "text_chars": len(text)}
    if _ai_call is None:
        return {**candidate, "doc_type": "other", "ignored": True,
                "note": "scanned document and no AI configured"}
    ai = await _ai_extract(data, "")
    if not ai:
        return {**candidate, "doc_type": "other", "ignored": True,
                "note": "extraction failed"}
    # WHITELISTED, never splatted: the model's dict must not be able to
    # overwrite source_key, message ids or provenance, and its amounts are
    # PARSED into pence here, not trusted as fields.
    return {**candidate, **_scan_fields(ai), "extracted_by": "ai",
            "verified": False, "text_chars": 0}


def _scan_fields(ai: dict) -> dict:
    lines = []
    for l in (ai.get("invoice_lines") or [])[:12]:
        if l.get("number"):
            lines.append({"number": str(l["number"])[:40], "pence": pence(l.get("amount"))})
    return {"doc_type": str(ai.get("doc_type") or "other"),
            "counterparty": str(ai.get("counterparty") or "")[:120],
            "currency": str(ai.get("currency") or "GBP")[:3],
            "total_pence": pence(ai.get("total")),
            "invoice_numbers": [str(n)[:40] for n in (ai.get("invoice_numbers") or [])[:12]],
            "invoice_lines": lines,
            "payment_reference": str(ai.get("payment_reference") or "")[:60]}


def _text_has_amount(text: str, p: Optional[int]) -> bool:
    """Does this exact amount appear in the document, ANCHORED? A bare
    substring test let a hallucinated 500.00 validate against the 1500.00
    that was really printed. Digit boundaries on both sides, thousands
    separators optional."""
    if p is None:
        return True                       # nothing claimed, nothing to confirm
    flat = re.sub(r"[\s,£$€]", "", text)
    digits = f"{abs(p) // 100}.{abs(p) % 100:02d}"
    return re.search(r"(?<![\d.])" + re.escape(digits) + r"(?![\d])", flat) is not None


def _text_has_ref(text: str, num: Any) -> bool:
    """Does this reference appear, as a WHOLE token? norm-substring matching
    let 'INV-1' validate against 'INV-142'. The pattern allows separators
    between the reference's own characters (INV 142 / INV-142 / inv142) but
    demands boundaries at both ends."""
    cleaned = re.sub(r"[^A-Za-z0-9]", "", str(num or ""))
    if not cleaned:
        return False
    body = r"[\W_]{0,2}".join(re.escape(c) for c in cleaned)
    return re.search(r"(?<![A-Za-z0-9])" + body + r"(?![0-9])", text, re.I) is not None


def _merge_extractions(parsed: dict, ai: dict, text: str) -> dict:
    """AI output is only trusted where the text layer can confirm it: an
    amount or invoice number the AI reports that does not appear in the text,
    anchored and whole, is dropped, and the drop is recorded."""
    dropped = []
    lines = []
    for l in (ai.get("invoice_lines") or []):
        amt = pence(l.get("amount"))
        if _text_has_ref(text, l.get("number")) and _text_has_amount(text, amt):
            lines.append({"number": str(l.get("number")), "pence": amt})
        else:
            dropped.append(str(l.get("number") or l.get("amount")))
    out = dict(parsed)
    out["doc_type"] = ai.get("doc_type") or parsed["doc_type"]
    out["counterparty"] = str(ai.get("counterparty") or "")[:120]
    out["invoice_lines"] = lines
    ai_total = pence(ai.get("total"))
    if ai_total is not None and _text_has_amount(text, ai_total):
        out["total_pence"] = ai_total
    if ai.get("invoice_numbers"):
        confirmed = [n for n in ai["invoice_numbers"] if _text_has_ref(text, n)]
        if confirmed:
            out["invoice_numbers"] = confirmed[:12]
    out["extracted_by"] = "text+ai"
    if dropped:
        out["ai_dropped"] = dropped[:8]
    return out


async def _ai_extract(pdf_bytes: bytes, text: str) -> Optional[dict]:
    import base64
    content: list = []
    if text:
        content.append({"type": "text", "text": "Document text layer:\n" + text[:30000]})
    else:
        content.append({"type": "document", "source": {
            "type": "base64", "media_type": "application/pdf",
            "data": base64.b64encode(pdf_bytes).decode()}})
    content.append({"type": "text", "text": "Record this document with the record_document tool."})
    try:
        resp = await _ai_call(_DOC_SYSTEM, [{"role": "user", "content": content}],
                              [_DOC_TOOL], {"type": "tool", "name": "record_document"})
        for block in resp.content:
            if getattr(block, "type", "") == "tool_use":
                d = dict(block.input)
                d["total"] = d.get("total")
                return d
    except Exception:
        logger.exception("recon: AI document extraction failed")
    return None


# ---------------------------------------------------------------------------
# AI investigation of one exception
# ---------------------------------------------------------------------------

_VERDICT_TOOL = {
    "name": "record_verdict",
    "description": "Record your conclusion about this discrepancy, citing only the evidence ids you were given.",
    "input_schema": {
        "type": "object",
        "properties": {
            "classification": {"type": "string", "enum": [
                "genuine_error", "timing_difference", "accounting_adjustment",
                "explained", "insufficient_evidence"]},
            "explanation": {"type": "string"},
            "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
            "cites": {"type": "array", "items": {"type": "string"},
                      "description": "Evidence ids (E1, E2...) your explanation rests on"},
            "recommended_action": {"type": "string"},
        },
        "required": ["classification", "explanation", "confidence", "cites"],
    },
}

_INVESTIGATE_SYSTEM = (
    "You are an independent financial auditor investigating ONE discrepancy between "
    "Shopify, Xero and Gmail records. You are given the discrepancy, the deterministic "
    "arithmetic already computed, and a set of evidence records, each with an id.\n"
    "Rules, absolute:\n"
    "- Reason ONLY from the evidence provided. If it does not support a conclusion, "
    "classify as insufficient_evidence.\n"
    "- Cite the evidence ids your explanation depends on. An uncited claim is worthless.\n"
    "- Never invent transactions, amounts, references or explanations.\n"
    "- A timing difference needs the dates in evidence to actually support it.\n"
    "- Confidence above 85 requires the arithmetic to close exactly.\n"
    "- You are read-only: recommend actions for a human, never claim to have acted.")


async def investigate(exc: dict, cache: dict) -> dict:
    """Run the AI over one exception. Facts and arithmetic ride along; the
    model's job is the interpretation layer, clearly labelled as such."""
    if _ai_call is None:
        return {"classification": "insufficient_evidence", "confidence": 0,
                "explanation": "AI is not configured on this server.", "cites": [],
                "at": _now(), "model": ""}
    pack = list(exc.get("evidence") or [])
    n = len(pack)
    for extra in _related_evidence(exc, cache, start=n + 1):
        pack.append(extra)
    lines = [f"DISCREPANCY: {exc['title']}",
             f"Why flagged: {exc['why']}",
             "Deterministic arithmetic (already computed, trust it):"]
    lines += ["  " + c for c in (exc.get("computed") or ["(none)"])]
    lines.append("\nEVIDENCE:")
    for e in pack:
        lines.append(f"[{e['eid']}] ({e['system']} {e['kind']}) {e['label']}:\n"
                     + json.dumps(e["record"], default=str)[:2000])
    try:
        resp = await _ai_call(_INVESTIGATE_SYSTEM,
                              [{"role": "user", "content": "\n".join(lines)[:180000]}],
                              [_VERDICT_TOOL], {"type": "tool", "name": "record_verdict"})
    except Exception:
        logger.exception("recon: investigation failed for %s", exc.get("id"))
        return {"classification": "insufficient_evidence", "confidence": 0,
                "explanation": "The AI call failed; requires human review.", "cites": [],
                "at": _now(), "model": ""}
    verdict = None
    for block in resp.content:
        if getattr(block, "type", "") == "tool_use":
            verdict = dict(block.input)
    if not verdict:
        verdict = {"classification": "insufficient_evidence", "confidence": 0,
                   "explanation": "The model returned no structured verdict.", "cites": []}
    # Validation IS the safety layer: citations must exist, and a confident
    # answer with no valid citations is downgraded, not believed.
    valid_ids = {e["eid"] for e in pack}
    verdict["cites"] = [c for c in (verdict.get("cites") or []) if c in valid_ids]
    if not verdict["cites"] and verdict.get("classification") != "insufficient_evidence":
        verdict["classification"] = "insufficient_evidence"
        verdict["confidence"] = 0
        verdict["explanation"] = ("Insufficient evidence - requires human review. "
                                  "(The model cited no valid evidence.)")
    verdict["confidence"] = max(0, min(100, int(verdict.get("confidence") or 0)))
    verdict["at"] = _now()
    verdict["model"] = str(getattr(resp, "model", "") or "")
    verdict["evidence_shown"] = sorted(valid_ids)
    return verdict


def _related_evidence(exc: dict, cache: dict, start: int) -> list:
    """Nearby records the checks did not attach but an investigator would pull:
    bank lines and payments within 10% of the amount and 10 days of the date."""
    out = []
    amt, date = exc.get("amount"), exc.get("date")
    if not amt or not date:
        return out
    n = start
    for t in cache.get("xero", {}).get("bank_transactions", {}).values():
        if t["pence"] and abs(abs(t["pence"]) - abs(amt)) <= max(abs(amt) // 10, 500):
            gap = _days_between(date, t["date"])
            if gap is not None and gap <= 10:
                out.append(ev("xero", "bank_transaction",
                              f"Nearby bank txn {t['id']} ({money(t['pence'], t['currency'])} on {t['date']})",
                              t, n))
                n += 1
        if n - start >= 6:
            break
    return out


# ---------------------------------------------------------------------------
# The sweep: sync all three systems, run every check, merge into the store
# ---------------------------------------------------------------------------

async def sweep(deep_docs: bool = True) -> dict:
    """One full pass. Serialized: the stores follow the house single-writer
    rule, and two sweeps interleaving would double-report everything."""
    if _sweeping["on"]:
        return {"ok": False, "note": "A sweep is already running."}
    _sweeping["on"] = True
    _sweeping["at"] = time.time()
    try:
        return await _sweep_inner(deep_docs)
    finally:
        _sweeping["on"] = False


async def _sweep_inner(deep_docs: bool) -> dict:
    cache = _load_cache()
    store = _load_store()
    docs = _load_docs()
    notes: list = []

    # --- Xero, incrementally ------------------------------------------------
    if _xero is not None and _xero.connected():
        marks = store.setdefault("watermarks", {})
        stamp = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        x = cache.setdefault("xero", {})
        for name, fetch, slimmer, key in (
                ("invoices", _xero.list_invoices, slim_invoice, "id"),
                ("payments", _xero.list_payments, slim_payment, "id"),
                ("bank_transactions", _xero.list_bank_transactions, slim_bank_txn, "id"),
                ("credit_notes", _xero.list_credit_notes, slim_credit_note, "id")):
            try:
                # The SAME window for all four. Invoices used to be the only
                # one filtered by date, so the first sweep pulled the whole
                # history of payments, bank lines and credit notes to check
                # four months of them.
                rows = await fetch(since=_cutoff_day(FETCH_DAYS),
                                   modified_since=marks.get(name))
                bucket = x.setdefault(name, {})
                truncated = False
                for r in rows:
                    if r.get("_truncated"):
                        truncated = True
                        continue
                    s = slimmer(r)
                    if s[key]:
                        bucket[s[key]] = s
                if truncated:
                    # Advance the watermark to the LAST ROW RECEIVED (the crawl
                    # is ordered UpdatedDateUTC ASC), so the next sweep walks
                    # forward through the backlog instead of refetching the
                    # same first pages forever and never reaching the rest.
                    last = next((r.get("UpdatedDateUTC") for r in reversed(rows)
                                 if isinstance(r, dict) and r.get("UpdatedDateUTC")), "")
                    if last:
                        try:
                            ms = int(re.search(r"/Date\((\d+)", str(last)).group(1))
                            marks[name] = datetime.fromtimestamp(
                                ms / 1000, tz=timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
                        except (AttributeError, ValueError):
                            pass
                    notes.append(f"Xero {name}: the crawl hit its page cap; this sweep is "
                                 "partial and the next one continues from where it stopped.")
                else:
                    marks[name] = stamp
            except Exception as e:
                notes.append(f"Xero {name} could not be read: {str(e)[:120]}")
                logger.exception("recon sweep: xero %s failed", name)
    else:
        notes.append("Xero is not connected; the accounts side of every check is missing.")

    # --- Shopify orders, whole window (the registry pages by since_id) ------
    if _registry is not None and _tool_json is not None:
        try:
            fetched, since_id = 0, 0
            bucket = cache.setdefault("shopify", {}).setdefault("orders", {})
            while fetched < 1500:
                d = await _tool_json(_registry, "shopify_list_orders", {
                    "limit": 250, "status": "any", "since_id": since_id or None,
                    "created_at_min": _cutoff_day(FETCH_DAYS) + "T00:00:00Z"})
                if d.get("_failed"):
                    notes.append("Shopify orders could not be read; sale checks ran on the cached copy.")
                    break
                rows = d.get("orders") or []
                for o in rows:
                    s = slim_order(o)
                    if s["id"]:
                        bucket[str(s["id"])] = s
                        since_id = max(since_id, int(s["id"]))
                fetched += len(rows)
                if len(rows) < 250:
                    break
        except Exception as e:
            notes.append(f"Shopify orders sync failed: {str(e)[:120]}")
            logger.exception("recon sweep: shopify orders failed")
        # Payouts: present only when the scope is granted and the store uses
        # Shopify Payments. Absence is recorded, never silently skipped.
        try:
            d = await _tool_json(_registry, "shopify_list_payouts", {})
            if d.get("_failed") or d.get("available") is False:
                cache.setdefault("shopify", {}).setdefault("payouts", {})
                notes.append("Shopify payouts are not readable (scope not granted, or the store "
                             "does not use Shopify Payments); payout checks did not run.")
            else:
                bucket = cache.setdefault("shopify", {}).setdefault("payouts", {})
                for p in d.get("payouts") or []:
                    s = slim_payout(p)
                    if s["id"]:
                        bucket[s["id"]] = s
                # Fees per payout, bounded per sweep: the fee is what explains
                # the classic payout-vs-bank gap, and it is arithmetic.
                todo = [p for p in bucket.values() if p.get("fees_pence") is None][:20]
                for p in todo:
                    ft = await _tool_json(_registry, "shopify_payout_transactions",
                                          {"payout_id": int(p["id"])} if str(p["id"]).isdigit() else {})
                    if ft.get("_failed") or ft.get("available") is False:
                        break
                    fees = sum(abs(pence(t.get("fee")) or 0)
                               for t in (ft.get("transactions") or []))
                    p["fees_pence"] = fees
            d2 = await _tool_json(_registry, "shopify_list_disputes", {})
            if not (d2.get("_failed") or d2.get("available") is False):
                bucket2 = cache.setdefault("shopify", {}).setdefault("disputes", {})
                for row in d2.get("disputes") or []:
                    sd = slim_dispute(row)
                    if sd["id"]:
                        bucket2[sd["id"]] = sd
        except KeyError:
            notes.append("Payout tools are not on this server build.")

    # --- The accounts mailbox, a bounded batch per sweep --------------------
    mailbox_linked = bool(_mail_connected()) if _mail_connected else (_mail_search is not None)
    if _mail_search is not None and mailbox_linked and deep_docs:
        try:
            known = set(docs.keys())
            seen = set(store.get("seen_threads") or [])
            found = await find_doc_candidates(known, seen)
            cands, walked, search_ok, complete = found
            if not search_ok:
                # A mailbox that cannot be read has checked NO documents. Saying
                # nothing here reads as "no missing invoices", which is the one
                # thing this tool must never imply.
                notes.append("The accounts mailbox could not be read this sweep, so no "
                             "remittances, supplier invoices or statements were checked.")
            batch = cands[:DOCS_PER_SWEEP]
            queued = {c["thread_id"] for c in cands[DOCS_PER_SWEEP:] if c.get("thread_id")}
            failed: set = set()
            for c in batch:
                d = await extract_doc(c)
                if d:
                    docs[c["source_key"]] = d
                else:
                    # Extraction failed: the document is NOT read, so its thread
                    # must come back. Marking it seen would drop an invoice
                    # permanently and silently.
                    failed.add(c.get("thread_id"))
            if failed:
                notes.append(f"{len(failed)} document(s) could not be read this sweep and "
                             "will be retried.")
            store["seen_threads"] = sorted((seen | walked) - queued - failed)[-SEEN_CAP:]
            if len(cands) > DOCS_PER_SWEEP:
                notes.append(f"{len(cands) - DOCS_PER_SWEEP} more documents from the accounts "
                             "mailbox are queued for later sweeps.")
            if not complete:
                notes.append("The accounts mailbox has more matching mail than one sweep "
                             "lists; the backlog is worked through a batch at a time.")
        except Exception:
            logger.exception("recon sweep: accounts mailbox scan failed")
            notes.append("The accounts mailbox scan failed part-way; documents may be missing.")
    elif deep_docs:
        notes.append("The accounts mailbox is not connected, so no remittances, supplier "
                     "invoices or statements were checked this sweep.")

    # --- Checks (pure functions over the cache) -----------------------------
    # THE RULE THAT KEEPS THE TOOL TRUSTED: a failed read is not an empty
    # ledger. With no Xero invoices in the cache at all, "every order is
    # missing from Xero" is a statement about our connection, not their books,
    # and a morning of 300 false criticals is how a merchant learns to ignore
    # the one real one.
    xero_has_data = bool(cache.get("xero", {}).get("invoices"))
    fresh: dict = {}
    ran_kinds: set = set()          # only a check that RAN may stale its findings
    checks_to_run = list(ALL_CHECKS)
    if not xero_has_data:
        checks_to_run = [c for c in checks_to_run
                         if c not in (check_orders_vs_invoices, check_refunds,
                                      check_payouts_vs_bank)]
        notes.append("The Xero cache is empty, so the missing-sale, refund and payout "
                     "checks were SKIPPED rather than reporting everything as missing.")
    for check in checks_to_run:
        try:
            for e in check(cache):
                fresh[e["id"]] = e
            ran_kinds |= CHECK_KINDS.get(check.__name__, set())
        except Exception:
            logger.exception("recon check %s crashed", check.__name__)
            notes.append(f"The {check.__name__} check crashed; its findings are missing "
                         "from this sweep.")
    try:
        for e in check_gmail_docs(cache, docs):
            fresh[e["id"]] = e
        ran_kinds |= CHECK_KINDS["check_gmail_docs"]
    except Exception:
        logger.exception("recon check_gmail_docs crashed")

    # --- Merge: statuses and AI verdicts survive; disappearance is recorded -
    # RELOAD first: this function has been awaiting network for possibly
    # minutes, and a person may have set statuses through the routes in that
    # time. Merging into the snapshot from the top of the sweep would clobber
    # them - the same lost-update the investigate op already guards against.
    marks = store.get("watermarks", {})
    seen_now = store.get("seen_threads")
    store = _load_store()
    store["watermarks"] = {**store.get("watermarks", {}), **marks}
    # Everything this sweep learned has to cross the reload, not just the
    # watermarks: seen_threads decides which mail is walked next time, and
    # dropping it here left the crawl rereading its first 40 threads forever.
    if seen_now is not None:
        store["seen_threads"] = seen_now
    existing = store.setdefault("exceptions", {})
    for xid, e in fresh.items():
        old = existing.get(xid)
        if old:
            e["status"], e["status_note"] = old["status"], old["status_note"]
            e["history"], e["ai"] = old["history"], old["ai"]
            e["created"] = old["created"]
        existing[xid] = e
    for xid, old in list(existing.items()):
        # A crashed or skipped check contributed nothing to `fresh`, and its
        # OLD findings must not read as resolved because of it: "the check did
        # not run" and "the discrepancy went away" are different facts, and a
        # dashboard that confuses them shows a clean board on a broken morning.
        if old.get("kind") not in ran_kinds:
            continue
        if xid not in fresh and not old.get("stale"):
            # Third case, alongside the two above: our own retention pass
            # deleted the records this was built from. That is not evidence of
            # anything having been fixed, and it must not be written as if it
            # were.
            dropped_local = set(store.get("retention_dropped") or [])
            expired = dropped_local and any(str(r) in dropped_local
                                            for r in (old.get("refs") or []))
            old["stale"] = True
            old["updated"] = _now()
            if expired:
                old["retention_dropped"] = True
            old["history"] = (old.get("history") or []) + [{
                "at": _now(), "by": "sweep", "from": old["status"], "to": old["status"],
                "note": ("The records behind this passed the retention window and were deleted "
                         "from the local copy, so the latest sweep could not look for it again. "
                         "That is not a sign it was resolved.") if expired else
                        "No longer detected by the latest sweep; kept for the audit trail."}]

    try:
        notes.extend(prune(cache, docs, store))
    except Exception:
        # It mutates as it goes, so "nothing was deleted" is a guess, and the
        # wrong one: whatever it had already dropped stays dropped.
        logger.exception("recon: pruning failed")
        notes.append("The retention pass failed part way through this sweep. Anything it had "
                     "already removed from the local copy is gone from it; nothing was "
                     "touched in Xero, Shopify or the mailbox.")
    store["last_sync"] = _now()
    store["last_notes"] = notes[:12]
    counts = {s: 0 for s in SEVERITIES}
    for e in existing.values():
        if not e.get("stale") and e["status"] in ("new", "investigating"):
            counts[e["severity"]] += 1
    store["open_counts"] = counts
    _write_cache(cache)
    _write_docs(docs)
    _write_store(store)
    return {"ok": True, "notes": notes, "open_counts": counts,
            "exceptions": len([e for e in existing.values() if not e.get("stale")]),
            "docs": len(docs)}
