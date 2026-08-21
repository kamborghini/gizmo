#!/usr/bin/env python3
"""
Pipedrive connector: SURVEY ONLY.

This module reads and never writes. Its whole job, for now, is to answer the
questions nobody can answer from outside the account: how many pipelines are
in use, which custom fields actually carry data, how many deals are archived,
which activity types exist, what currencies appear, and who owns what.

That survey is what decides the shape of the import, so it comes first and on
its own. Nothing here creates, updates or deletes anything in Pipedrive.

Env:
  PIPEDRIVE_API_TOKEN   an ADMIN's personal API token
  PIPEDRIVE_DOMAIN      optional, e.g. "acme" for acme.pipedrive.com
  PIPEDRIVE_API_BASE    test override
"""
import os
import asyncio
import logging
from collections import Counter

import httpx

logger = logging.getLogger("shopify_mcp.pipedrive")

API_TOKEN = os.environ.get("PIPEDRIVE_API_TOKEN", "")
DOMAIN = os.environ.get("PIPEDRIVE_DOMAIN", "").strip().replace(".pipedrive.com", "")
API_BASE = os.environ.get("PIPEDRIVE_API_BASE", "").rstrip("/")

# Endpoints that still only exist on v1. Pipedrive took a batch of v1 routes out
# of support on 1 Aug 2026 but published no v2 replacement for these, so they
# are named here deliberately rather than assumed.
_V1_ONLY = ("notes", "files", "users", "leads", "leadLabels", "activityTypes",
            "dealFields", "personFields", "organizationFields", "currencies")


class PipedriveError(Exception):
    """Carries Pipedrive's own message so the UI can show the real cause."""


def configured() -> bool:
    return bool(API_TOKEN)


def _base(version: str) -> str:
    if API_BASE:
        return f"{API_BASE}/{version}"
    host = f"https://{DOMAIN}.pipedrive.com" if DOMAIN else "https://api.pipedrive.com"
    return f"{host}/{version}"


async def _get(path: str, params: dict = None, version: str = "v2") -> dict:
    """One read. The token goes in a HEADER, never the query string: a token in
    a URL ends up in server logs, proxy logs and browser history."""
    if not API_TOKEN:
        raise PipedriveError("No Pipedrive token is set on the server.")
    url = f"{_base(version)}/{path}"
    headers = {"x-api-token": API_TOKEN, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=30.0) as c:
        for attempt in range(4):
            r = await c.get(url, params=params or {}, headers=headers)
            if r.status_code == 429:
                # Pipedrive's budget resets on a short window; it tells us when.
                wait = float(r.headers.get("retry-after") or (2 ** attempt))
                logger.warning("pipedrive rate limited, waiting %ss", wait)
                await asyncio.sleep(min(wait, 30))
                continue
            break
    if r.status_code == 401:
        raise PipedriveError("Pipedrive refused the token. Check it is current and "
                             "belongs to an administrator.")
    if r.status_code >= 400:
        try:
            detail = r.json().get("error") or r.text[:300]
        except Exception:
            detail = r.text[:300]
        raise PipedriveError(f"Pipedrive said: {str(detail)[:300]}")
    try:
        return r.json()
    except Exception:
        raise PipedriveError("Pipedrive returned something that was not JSON.")


async def _count(path: str, params: dict = None, version: str = "v2",
                 cap: int = 20000) -> tuple:
    """(rows, complete). Walks pages until the end or the cap, and SAYS which,
    because a truncated count that looks complete is how a migration quietly
    misses half an account."""
    rows, cursor, start, pages = [], None, 0, 0
    while pages < 200 and len(rows) < cap:
        p = dict(params or {})
        if version == "v2":
            p["limit"] = 500
            if cursor:
                p["cursor"] = cursor
        else:
            p["limit"] = 500
            p["start"] = start
        data = await _get(path, p, version=version)
        batch = data.get("data") or []
        rows.extend(batch)
        pages += 1
        if version == "v2":
            cursor = ((data.get("additional_data") or {}).get("next_cursor")
                      or data.get("next_cursor"))
            if not cursor:
                return rows, True
        else:
            more = ((data.get("additional_data") or {}).get("pagination") or {})
            if not more.get("more_items_in_collection"):
                return rows, True
            start = more.get("next_start") or (start + len(batch))
        if not batch:
            return rows, True
    return rows, False


async def whoami() -> dict:
    d = await _get("users/me", version="v1")
    u = d.get("data") or {}
    return {"name": u.get("name") or "", "email": u.get("email") or "",
            "admin": bool(u.get("is_admin")), "company": u.get("company_name") or "",
            "domain": u.get("company_domain") or "", "currency": u.get("default_currency") or ""}


def _field_summary(fields: list, rows: list) -> list:
    """Which custom fields actually carry data. A field nobody fills in is not
    a migration problem; a field on 400 deals is."""
    out = []
    for f in fields or []:
        key = str(f.get("key") or "")
        if len(key) != 40:            # 40-hex key = a custom field
            continue
        used = sum(1 for r in rows if str(r.get(key) or "").strip() not in ("", "None"))
        out.append({"name": f.get("name") or key, "key": key,
                    "type": f.get("field_type") or "", "used_on": used,
                    "options": len(f.get("options") or [])})
    out.sort(key=lambda x: -x["used_on"])
    return out


async def survey() -> dict:
    """Everything we need to know before designing the import. Read-only."""
    me = await whoami()
    out: dict = {"account": me, "warnings": []}
    if not me.get("admin"):
        out["warnings"].append(
            "This token belongs to " + (me.get("name") or "someone")
            + ", who is NOT an administrator. A Pipedrive token only sees what that "
              "person sees, so the counts below may be a fraction of the account "
              "and nothing will say so. Use an admin's token.")

    pipelines, _ = await _count("pipelines", version="v1")
    stages, _ = await _count("stages", version="v1")
    users, _ = await _count("users", version="v1")
    deal_fields, _ = await _count("dealFields", version="v1")
    person_fields, _ = await _count("personFields", version="v1")
    act_types, _ = await _count("activityTypes", version="v1")

    deals, deals_all = await _count("deals")
    # Archived deals stopped being returned by the normal endpoint in July 2025
    # and must be asked for by name, or an import silently misses the back
    # catalogue and still looks like it worked.
    try:
        archived, arch_all = await _count("deals", {"archived_status": "archived"})
    except PipedriveError as e:
        out["warnings"].append("Could not read archived deals separately (" + str(e)[:120]
                               + "). They must be checked before any import.")
        archived, arch_all = [], False

    persons, persons_all = await _count("persons")
    orgs, orgs_all = await _count("organizations")
    activities, acts_all = await _count("activities")
    try:
        leads, leads_all = await _count("leads", version="v1")
    except PipedriveError:
        leads, leads_all = [], False

    by_pipeline = Counter(str(d.get("pipeline_id") or "") for d in deals)
    currencies = Counter(str(d.get("currency") or "") for d in deals)
    owners = Counter(str((d.get("owner_id") or d.get("user_id") or "")) for d in deals)
    statuses = Counter(str(d.get("status") or "") for d in deals)
    named_types = {str(t.get("key_string") or t.get("name")): t.get("name")
                   for t in act_types}
    used_types = Counter(str(a.get("type") or "") for a in activities)
    user_names = {str(u.get("id")): u.get("name") or "" for u in users}

    out.update({
        "counts": {
            "deals": len(deals), "deals_complete": deals_all,
            "archived_deals": len(archived), "archived_complete": arch_all,
            "persons": len(persons), "persons_complete": persons_all,
            "organizations": len(orgs), "orgs_complete": orgs_all,
            "activities": len(activities), "activities_complete": acts_all,
            "leads": len(leads), "leads_complete": leads_all,
            "users": len(users), "pipelines": len(pipelines), "stages": len(stages),
        },
        "pipelines": [{"id": str(p.get("id")), "name": p.get("name") or "",
                       "deals": by_pipeline.get(str(p.get("id")), 0),
                       "stages": len([s for s in stages
                                      if str(s.get("pipeline_id")) == str(p.get("id"))])}
                      for p in pipelines],
        "stages": [{"id": str(s.get("id")), "name": s.get("name") or "",
                    "pipeline_id": str(s.get("pipeline_id")),
                    "order": s.get("order_nr"), "probability": s.get("deal_probability"),
                    "rot_days": s.get("rotten_days")} for s in stages],
        "users": [{"id": str(u.get("id")), "name": u.get("name") or "",
                   "email": u.get("email") or "", "active": bool(u.get("active_flag")),
                   "admin": bool(u.get("is_admin")),
                   "deals": owners.get(str(u.get("id")), 0)} for u in users],
        "deal_status": dict(statuses),
        "currencies": dict(currencies),
        "activity_types": [{"key": k, "name": v, "used": used_types.get(k, 0)}
                           for k, v in named_types.items()],
        "custom_fields": {
            "deals": _field_summary(deal_fields, deals),
            "persons": _field_summary(person_fields, persons),
        },
        "owner_names": user_names,
    })

    # The things that decide the shape of the job, said plainly.
    live_pipes = [p for p in out["pipelines"] if p["deals"]]
    if len(live_pipes) > 1:
        out["warnings"].append(
            str(len(live_pipes)) + " pipelines are in use ("
            + ", ".join(p["name"] for p in live_pipes)
            + "). gizmo has ONE flat list of stages, so either it learns pipelines "
              "or all of these collapse onto one board.")
    if len([c for c in currencies if c and c != me.get("currency")]) > 0:
        out["warnings"].append(
            "Deals exist in more than one currency (" + ", ".join(sorted(c for c in currencies if c))
            + "). gizmo treats every value as pounds, so these would import as the "
              "wrong number.")
    used_fields = [f for f in out["custom_fields"]["deals"] if f["used_on"]]
    if used_fields:
        out["warnings"].append(
            str(len(used_fields)) + " custom deal fields carry data, the busiest being "
            + ", ".join(f["name"] for f in used_fields[:5])
            + ". gizmo has no custom fields at all yet.")
    if len([u for u in out["users"] if u["deals"]]) > 1:
        out["warnings"].append(
            "Deals are spread across " + str(len([u for u in out['users'] if u['deals']]))
            + " owners. gizmo's CRM has no owner on anything, so 'my deals' would not exist.")
    for k, label in (("deals", "deals"), ("persons", "people"), ("organizations", "organisations"),
                     ("activities", "activities")):
        if not out["counts"].get(k + "_complete", True) and k != "organizations":
            out["warnings"].append("The " + label + " count hit the survey's ceiling, so the "
                                                    "real number is higher.")
    return out
