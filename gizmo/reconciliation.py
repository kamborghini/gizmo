"""Reconciliation, the app's side of it: its stores, the AI call the engine
(recon.py) is given, the read-only tools the chat is given, and the Xero
connect walk's redirect address and sign-in tickets. Moved out of copilot.py
(stage 4 of the 14 October audit); its routes, with the Xero connect pair,
are in gizmo/routes/reconciliation.py. Read as `reconciliation.NAME`.
"""
import logging
import os
import re
import json
from typing import Optional
import recon as recon_engine
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import Request
from gizmo import store as jsonstore
from gizmo import ai as claude

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


# ---------------------------------------------------------------------------
# Reconciliation stores + the read-only tools the chat is given
# ---------------------------------------------------------------------------

# Reconciliation engine: exceptions + audit trail, system snapshots, extracted documents.
RECON_PATH         = os.environ.get("RECON_PATH", "/data/recon.json")
RECON_CACHE_PATH   = os.environ.get("RECON_CACHE_PATH", "/data/recon_cache.json")
RECON_DOCS_PATH    = os.environ.get("RECON_DOCS_PATH", "/data/recon_docs.json")


def _load_recon() -> dict:
    d = jsonstore._load_json_store(RECON_PATH, "recon", None)
    return d if isinstance(d, dict) else {"exceptions": {}, "watermarks": {}}


def _write_recon(d: dict) -> None:
    jsonstore._write_private_json(RECON_PATH, "recon", d)


def _load_recon_cache() -> dict:
    d = jsonstore._load_json_store(RECON_CACHE_PATH, "cache", None)
    return d if isinstance(d, dict) else {}


def _write_recon_cache(d: dict) -> None:
    jsonstore._write_private_json(RECON_CACHE_PATH, "cache", d)


def _load_recon_docs() -> dict:
    d = jsonstore._load_json_store(RECON_DOCS_PATH, "docs", None)
    return d if isinstance(d, dict) else {}


def _write_recon_docs(d: dict) -> None:
    jsonstore._write_private_json(RECON_DOCS_PATH, "docs", d)


# The auditor's model: env-pinnable, otherwise the deep model, so upgrading is
# one variable and never a code change.
MODEL_RECON = os.environ.get("ANTHROPIC_MODEL_RECON") or claude.MODEL_DEEP


async def _recon_ai_call(system: str, messages: list, tools: list, tool_choice: dict):
    """The one AI entry point the engine gets: read, reason, answer through a
    forced tool. No registry, no writes, no memory - an auditor with a
    document in one hand and nothing in the other."""
    claude._ai_kind.set("recon")
    client = claude._anthropic()
    return await claude._xcreate(client, model=MODEL_RECON, max_tokens=claude.MAX_TOKENS,
                          system=system, messages=messages, tools=tools,
                          tool_choice=tool_choice,
                          output_config={"effort": claude._effort_for(MODEL_RECON)})


def _recon_open_summary(d: dict) -> tuple:
    """Open discrepancies by severity: how many, and the money at stake (the size
    of each difference whatever its sign, in pence). Open is new or
    investigating and not stale, the sweep's own rule, worked out live so a
    status changed since the sweep is counted as it is now, and a counter's
    figure and its money always agree."""
    counts = {s: 0 for s in recon_engine.SEVERITIES}
    amounts = {s: 0 for s in recon_engine.SEVERITIES}
    for e in (d.get("exceptions") or {}).values():
        if not isinstance(e, dict) or e.get("stale") or e.get("status") not in ("new", "investigating"):
            continue
        sev = e.get("severity")
        if sev not in counts:
            continue
        counts[sev] += 1
        try:
            amounts[sev] += abs(int(e.get("amount") or 0))
        except (TypeError, ValueError):
            pass
    return counts, amounts


def _recon_record(e: dict) -> tuple:
    """The discrepancies table's Record column (12 Oct 2026), from the evidence:
    the record a person would look up, and the other record it disagrees with or
    who it is with. Nothing is invented when there is no evidence."""
    evs = [x for x in (e.get("evidence") or []) if isinstance(x, dict)]
    if not evs:
        return "", ""

    def short(x: dict) -> str:
        r, k = x.get("record") or {}, x.get("kind")
        if k == "order":
            return str(r.get("name") or "")
        if k in ("invoice", "bill"):
            return str(r.get("number") or "")
        if k == "payout":
            return "Payout " + str(r.get("id") or "")
        if k == "dispute":
            return "Dispute " + str(r.get("id") or "")
        if k == "bank_transaction":
            return "Bank line"
        if k == "payment":
            return "Payment"
        if k == "refund":
            return "Refund"
        if k == "document":
            return str(r.get("doc_type") or "document").replace("_", " ").capitalize()
        return str(x.get("label") or "")

    def who(x: dict) -> str:
        r = x.get("record") or {}
        if x.get("kind") == "document":
            m = re.search(r"(?:\bfrom\s+| - )(.+)$", str(r.get("subject") or ""))
            return m.group(1).strip() if m else ""
        return str(r.get("company") or r.get("contact") or r.get("customer") or "")

    rec = short(evs[0])
    other = next((short(x) for x in evs[1:] if x.get("kind") in ("invoice", "bill", "order")
                  and short(x) and short(x) != rec), "")
    return rec, other or who(evs[0])


def _recon_exc_public(e: dict, full: bool = False) -> dict:
    out = {k: e.get(k) for k in ("id", "kind", "severity", "title", "amount", "currency",
                                 "date", "systems", "status", "status_note", "stale",
                                 "created", "updated", "basis")}
    out["amount_disp"] = recon_engine.money(e.get("amount"), e.get("currency") or "GBP")
    out["has_ai"] = bool(e.get("ai"))
    out["record"], out["counterparty"] = _recon_record(e)
    if full:
        out.update({k: e.get(k) for k in ("why", "suggestion", "computed", "evidence",
                                          "ai", "history", "refs")})
    return out


def _recon_filter(exceptions: dict, severity: str = "", status: str = "", q: str = "",
                  min_pence: int = 0, include_stale: bool = False) -> list:
    rows = []
    ql = q.strip().lower()
    for e in exceptions.values():
        if e.get("stale") and not include_stale:
            continue
        if severity and e["severity"] != severity:
            continue
        if status and e["status"] != status:
            continue
        if min_pence and abs(e.get("amount") or 0) < min_pence:
            continue
        if ql and ql not in (e["title"] + " " + e["kind"] + " " + e.get("why", "")).lower():
            continue
        rows.append(e)
    sev_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    rows.sort(key=lambda e: (sev_rank.get(e["severity"], 9), -(abs(e.get("amount") or 0))))
    return rows


class ReconEmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReconExceptionsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    severity: Optional[str] = Field(default=None, description="critical | high | medium | low")
    status: Optional[str] = Field(default=None, description="new | investigating | explained | confirmed_error | corrected | ignored")
    q: Optional[str] = Field(default=None, description="Free-text filter over titles and reasons")
    min_amount: Optional[float] = Field(default=None, description="Only discrepancies of at least this many pounds")


class ReconExceptionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., description="The exception id, e.g. x3fa29bc10d44")


async def recon_summary(params: ReconEmptyInput) -> str:
    """Reconciliation health: open discrepancy counts by severity, the biggest open items, when the books were last swept, and any parts of the last sweep that could not run."""
    d = _load_recon()
    top = [_recon_exc_public(e) for e in _recon_filter(d.get("exceptions", {}))[:10]]
    # Counted live, as the page counts them: the sweep's snapshot goes stale
    # the moment someone marks one Explained (final review M-7).
    return json.dumps({"last_sync": d.get("last_sync") or "never",
                       "open_counts": _recon_open_summary(d)[0],
                       "sweep_notes": d.get("last_notes") or [],
                       "largest_open": top}, default=str)


async def recon_exceptions(params: ReconExceptionsInput) -> str:
    """List reconciliation discrepancies (Shopify vs Xero vs Gmail), filterable by severity, status, text and minimum amount. Amounts are in pence in `amount` and displayed in `amount_disp`."""
    d = _load_recon()
    rows = _recon_filter(d.get("exceptions", {}),
                         severity=str(params.severity or ""),
                         status=str(params.status or ""), q=str(params.q or ""),
                         min_pence=int((params.min_amount or 0) * 100))
    return json.dumps({"count": len(rows),
                       "exceptions": [_recon_exc_public(e) for e in rows[:60]]}, default=str)


async def recon_exception(params: ReconExceptionInput) -> str:
    """One discrepancy in full: the evidence records from each system, the deterministic arithmetic, any AI verdict (clearly labelled interpretation, never fact), and the status history."""
    d = _load_recon()
    e = d.get("exceptions", {}).get(str(params.id))
    if not e:
        return json.dumps({"error": "No exception with that id."})
    return json.dumps(_recon_exc_public(e, full=True), default=str)
_xero_connect_tickets: dict = {}     # ticket -> expiry, for the Xero consent walk
_xero_oauth_states: dict = {}

# ----- Xero connect: the accounts side of the reconciliation engine -----
def _xero_redirect_uri(request: Request) -> str:
    if config.APP_BASE_URL:
        return config.APP_BASE_URL.rstrip("/") + "/oauth/xero/callback"
    host = request.headers.get("host", "")
    return f"https://{host}/oauth/xero/callback"


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as core.NAME and sibling.NAME, never a copied name.
import copilot as core  # noqa: E402
from gizmo import config  # noqa: E402
