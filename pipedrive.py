#!/usr/bin/env python3
"""
Pipedrive connector: read the account, never write to it.

Two jobs, both read-only against Pipedrive:

  survey()   answers the questions that decide the shape of an import, so
             nobody has to guess at the account from outside it.
  export()   pulls everything an import needs and normalises it into the
             shapes gizmo's CRM already uses.

Nothing here creates, updates or deletes anything in Pipedrive. Writing
happens only into gizmo's own store, and only when somebody asks for it.

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
# What v1 still serves. Everything else moved to v2, and asking v1 for it
# returns an empty success rather than an error, which is worse than a 404:
# the import reports that it worked and quietly brings nothing.
_V1_ONLY = ("notes", "files", "users", "leads", "leadLabels", "activityTypes",
            "dealFields", "personFields", "organizationFields", "currencies")


class PipedriveError(Exception):
    """Carries Pipedrive's own message so the UI can show the real cause."""


def configured() -> bool:
    return bool(API_TOKEN)


_discovered = {"domain": ""}


def _base(version: str) -> str:
    """Both API versions live under /api/. Without that prefix the request
    lands on the Pipedrive WEB APP, which cheerfully returns a page of HTML
    with a 200, so the failure looks like a parsing problem rather than a
    wrong URL."""
    if API_BASE:
        return f"{API_BASE}/api/{version}"
    dom = DOMAIN or _discovered["domain"]
    host = f"https://{dom}.pipedrive.com" if dom else "https://api.pipedrive.com"
    return f"{host}/api/{version}"


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
    ctype = (r.headers.get("content-type") or "").lower()
    if "json" not in ctype:
        # A page instead of data. Say which page and why, rather than handing
        # somebody a mouthful of markup to puzzle over.
        raise PipedriveError(
            "That request reached a Pipedrive web page rather than the API ("
            + url + "). Usually this means the address or the token is wrong.")
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
    """Who the token belongs to, and which company domain to use for the rest.

    Pipedrive advises requests go to the company's own domain, and the account
    itself is the only thing that knows what that is, so the first call finds
    it and everything afterwards uses it. No configuration required."""
    d = await _get("users/me", version="v1")
    u = d.get("data") or {}
    dom = str(u.get("company_domain") or "").strip()
    if dom and not DOMAIN:
        _discovered["domain"] = dom
    return {"name": u.get("name") or "", "email": u.get("email") or "",
            "admin": bool(u.get("is_admin")), "company": u.get("company_name") or "",
            "domain": dom, "currency": u.get("default_currency") or ""}


def _cf(row: dict, key: str):
    """A custom field's value. In v2 these are NESTED under custom_fields, so
    reading the top level finds nothing and reports an account with no custom
    fields at all: the single claim most likely to force a second migration."""
    v = (row.get("custom_fields") or {}).get(key)
    if v is None:
        v = row.get(key)
    if isinstance(v, dict):
        v = v.get("value", v.get("id"))
    return v


def _field_summary(fields: list, rows: list) -> list:
    """Which custom fields actually carry data. A field nobody fills in is not
    a migration problem; a field on 400 deals is."""
    out = []
    for f in fields or []:
        key = str(f.get("key") or "")
        if len(key) != 40 and key != "label":
            continue
        used = sum(1 for r in rows if str(_cf(r, key) or "").strip() not in ("", "None", "[]"))
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

    pipelines, _ = await _count("pipelines")
    stages, _ = await _count("stages")
    users, _ = await _count("users", version="v1")
    deal_fields, _ = await _count("dealFields", version="v1")
    person_fields, _ = await _count("personFields", version="v1")
    act_types, _ = await _count("activityTypes", version="v1")

    deals, deals_all = await _count("deals")
    # Archived deals stopped being returned by the normal endpoint in July 2025.
    # They live behind their OWN path: "archived_status" is not a parameter in
    # either spec, so passing it returns the live deals again and the back
    # catalogue is missed while the run reports success.
    try:
        archived, arch_all = await _count("deals/archived")
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


# ---------------------------------------------------------------------------
# Export: the account, in gizmo's shapes
# ---------------------------------------------------------------------------

def _iso(v) -> str:
    """Pipedrive hands back "2026-03-04 09:11:22" or an ISO string. gizmo
    stores ISO with a timezone, and a date that silently becomes today is how
    an imported history loses the thing it was imported for."""
    s = str(v or "").strip()
    if not s:
        return ""
    s = s.replace(" ", "T", 1)
    if s.endswith("Z"):
        return s
    return s + "Z" if len(s) == 19 else s


def _day(v) -> str:
    s = str(v or "").strip()
    return s[:10] if len(s) >= 10 else ""


def _num(v) -> float:
    try:
        return round(float(v or 0), 2)
    except (TypeError, ValueError):
        return 0.0


# Pipedrive's built-in activity keys that gizmo already understands. Anything
# else becomes a task, and the export SAYS how many, rather than quietly
# flattening a "Site visit" into something else.
_TYPE_MAP = {"call": "call", "meeting": "meeting", "task": "task",
             "deadline": "deadline", "email": "email", "lunch": "lunch"}


async def export(progress=None) -> dict:
    """Everything an import needs, normalised. Read-only.

    Records keep their Pipedrive id so a second run can update rather than
    duplicate, and so anything imported can always be traced back."""
    def say(msg):
        if progress:
            try:
                progress(msg)
            except Exception:
                pass

    me = await whoami()
    say("reading the pipeline and stages")
    pipes, _ = await _count("pipelines")
    stages, stages_ok = await _count("stages")
    say("reading field definitions")
    try:
        deal_fields, _ = await _count("dealFields", version="v1")
    except PipedriveError:
        deal_fields = []
    try:
        person_fields, _ = await _count("personFields", version="v1")
    except PipedriveError:
        person_fields = []
    try:
        org_fields, _ = await _count("organizationFields", version="v1")
    except PipedriveError:
        org_fields = []
    say("reading organisations")
    orgs, orgs_ok = await _count("organizations")
    say("reading people")
    persons, persons_ok = await _count("persons")
    say("reading deals")
    deals, deals_ok = await _count("deals")
    say("reading archived deals")
    try:
        archived, arch_ok = await _count("deals/archived")
    except PipedriveError:
        archived, arch_ok = [], False
    say("reading activities")
    acts, acts_ok = await _count("activities")
    say("reading notes")
    try:
        notes, notes_ok = await _count("notes", version="v1")
    except PipedriveError:
        notes, notes_ok = [], False
    say("checking products and files")
    try:
        products, _ = await _count("products", cap=500)
    except PipedriveError:
        products = []
    try:
        files, _ = await _count("files", version="v1", cap=2000)
    except PipedriveError:
        files = []

    # Weighting is a PIPELINE switch. With it off Pipedrive shows no weighted
    # value at all, so importing per-stage probabilities would make gizmo print
    # a forecast their CRM never showed them.
    prob_on = True
    for p in pipes:
        if "is_deal_probability_enabled" in p:
            prob_on = bool(p.get("is_deal_probability_enabled"))
            break
        if "deal_probability" in p:
            prob_on = bool(p.get("deal_probability"))
            break

    stage_rows = []
    for st in stages:
        # v2 renamed both halves of the rot timer. Reading only the v1 names
        # silently zeroes every timer; reading only the number without its
        # switch invents timers Pipedrive was not applying.
        rot_on = (st.get("is_deal_rot_enabled") if "is_deal_rot_enabled" in st
                  else st.get("rotten_flag"))
        rot_n = (st.get("days_to_rotten") if "days_to_rotten" in st
                 else st.get("rotten_days"))
        stage_rows.append({
            "pd_id": str(st.get("id")), "name": str(st.get("name") or "")[:60],
            "order": st.get("order_nr") or 0,
            "probability": (st.get("deal_probability") if prob_on else 100),
            "rot_on": bool(rot_on),
            "rot_days": int(rot_n or 0) if rot_on else 0,
            "rot_days_stored": int(rot_n or 0),
            "pipeline_id": str(st.get("pipeline_id") or "")})
    stage_rows.sort(key=lambda x: (x["order"] or 0))

    # Labels are option lists on the built-in "label" field — but each entity
    # keeps its OWN option list: a person label id means nothing in the deal
    # field's options, which is how person and org labels once vanished while
    # the import reported success.
    def _label_map(fields):
        for f in fields:
            if str(f.get("key")) in ("label", "label_ids"):
                return {str(o.get("id")): {"name": str(o.get("label") or "")[:40],
                                           "color": str(o.get("color") or "")[:20]}
                        for o in (f.get("options") or [])}
        return {}

    label_opts = _label_map(deal_fields)
    person_labels = _label_map(person_fields)
    org_labels = _label_map(org_fields)
    label_colors = {}
    for src in (label_opts, person_labels, org_labels):
        for v in src.values():
            if v.get("name"):
                label_colors.setdefault(v["name"], v.get("color", ""))

    def _own_label(row, opts):
        ids = [str(x) for x in (row.get("label_ids") or [])]
        if not ids and row.get("label") not in (None, ""):
            ids = [str(row.get("label"))]
        return opts.get(ids[0], {}).get("name", "") if ids else ""

    _HEX = set("0123456789abcdef")

    def _cf_value(row, f):
        """One custom field's display value: option ids become their labels,
        money keeps its currency, everything else becomes a short string.
        Reads the RAW nested value itself — _cf unwraps dicts, which would
        strip a monetary value's currency before this ever saw it."""
        key = str(f.get("key") or "")
        cf = row.get("custom_fields")
        v = cf.get(key) if isinstance(cf, dict) and key in cf else row.get(key)
        if v in (None, "", [], {}):
            return ""
        ftype = str(f.get("field_type") or "")
        opts = {str(o.get("id")): str(o.get("label") or "")
                for o in (f.get("options") or [])}
        def _oid(x):
            return str(x.get("id", x.get("value", ""))) if isinstance(x, dict) else str(x)
        if ftype == "enum":
            return (opts.get(_oid(v)) or _oid(v))[:200]
        if ftype == "set":
            vals = v if isinstance(v, list) else [v]
            return ", ".join(x for x in ((opts.get(_oid(y)) or _oid(y)) for y in vals) if x)[:300]
        if ftype == "monetary" and isinstance(v, dict):
            cur = str(v.get("currency") or "")
            return (str(v.get("value") or "") + (" " + cur if cur else "")).strip()[:60]
        if isinstance(v, dict):
            got = v.get("value")
            if got in (None, ""):
                got = " ".join(str(x) for x in v.values()
                               if isinstance(x, (str, int, float)) and str(x).strip())
            return str(got or "").strip()[:300]
        if isinstance(v, list):
            return ", ".join(str(x)[:100] for x in v[:10])[:300]
        return str(v).strip()[:300]

    def _custom(row, fields):
        """The row's custom-field values by field NAME, resolved to text.
        A custom field's key is a 40-hex hash; anything else is built in."""
        out = {}
        for f in fields:
            key = str(f.get("key") or "")
            if len(key) != 40 or not set(key) <= _HEX:
                continue
            name = str(f.get("name") or "").strip()[:60]
            if not name:
                continue
            val = _cf_value(row, f)
            if val:
                out[name] = val
            if len(out) >= 20:
                break
        return out

    org_rows = [{"pd_id": str(o.get("id")), "name": str(o.get("name") or "")[:120],
                 "website": str(o.get("website") or "")[:200],
                 "label": _own_label(o, org_labels),
                 "custom": _custom(o, org_fields),
                 "address": str((o.get("address") or "") if isinstance(o.get("address"), str)
                                else (o.get("address") or {}).get("value") or "")[:300],
                 "created_at": _iso(o.get("add_time")),
                 "updated_at": _iso(o.get("update_time"))}
                for o in orgs if o.get("id")]

    def _contacts(row, key):
        """(values, labels), PRIMARY first. gizmo shows the first entry and
        treats it as the address to use, so losing which one Pipedrive marked
        primary means ringing the wrong number. Labels ride in their own list:
        folded into the value string they poison every tel:/mailto use and
        break the Mail tab's address matching."""
        vals = row.get(key)
        prim, rest = [], []
        if isinstance(vals, list):
            for v in vals:
                if isinstance(v, dict):
                    got, is_p = v.get("value"), bool(v.get("primary"))
                    lab = str(v.get("label") or "").strip()[:20]
                else:
                    got, is_p, lab = v, False, ""
                if not got or not str(got).strip():
                    continue
                if lab.lower() in ("work", "email", "phone"):
                    lab = ""
                (prim if is_p else rest).append((str(got).strip()[:200], lab))
        elif vals:
            prim.append((str(vals).strip()[:200], ""))
        seen, out_v, out_l = set(), [], []
        for v, lab in prim + rest:
            k = v.lower()
            if k not in seen:
                seen.add(k)
                out_v.append(v)
                out_l.append(lab)
        return out_v[:8], out_l[:8]

    def _person_row(p):
        emails, email_labels = _contacts(p, "emails")
        if not emails:
            emails, email_labels = _contacts(p, "email")
        phones, phone_labels = _contacts(p, "phones")
        if not phones:
            phones, phone_labels = _contacts(p, "phone")
        return {"pd_id": str(p.get("id")),
                "name": str(p.get("name") or "")[:120],
                "job_title": str(p.get("job_title") or "")[:120],
                "label": _own_label(p, person_labels),
                "custom": _custom(p, person_fields),
                "org_pd_id": str((p.get("org_id") or {}).get("value")
                                 if isinstance(p.get("org_id"), dict) else (p.get("org_id") or "")),
                "emails": emails, "email_labels": email_labels,
                "phones": phones, "phone_labels": phone_labels,
                "created_at": _iso(p.get("add_time")),
                "updated_at": _iso(p.get("update_time"))}

    person_rows = [_person_row(p) for p in persons if p.get("id")]

    seen_deal = set()
    extra_labels = [0]
    deal_rows = []
    for src, is_arch in ((deals, False), (archived, True)):
        for dd in src:
            pid = str(dd.get("id") or "")
            if not pid or pid in seen_deal:
                continue
            seen_deal.add(pid)
            status = str(dd.get("status") or "open")
            lab_ids = [str(x) for x in (dd.get("label_ids") or [])]
            if not lab_ids and dd.get("label") not in (None, ""):
                lab_ids = [str(dd.get("label"))]
            if len(lab_ids) > 1:
                extra_labels[0] += len(lab_ids) - 1
            deal_rows.append({
                "label": label_opts.get(lab_ids[0], {}).get("name", "") if lab_ids else "",
                "pd_id": pid,
                "title": str(dd.get("title") or "Untitled")[:200],
                "value": _num(dd.get("value")),
                "currency": str(dd.get("currency") or me.get("currency") or "GBP")[:8],
                "stage_pd_id": str(dd.get("stage_id") or ""),
                "person_pd_id": str((dd.get("person_id") or {}).get("value")
                                    if isinstance(dd.get("person_id"), dict) else (dd.get("person_id") or "")),
                "org_pd_id": str((dd.get("org_id") or {}).get("value")
                                 if isinstance(dd.get("org_id"), dict) else (dd.get("org_id") or "")),
                "status": status if status in ("open", "won", "lost") else "open",
                # The deal's OWN flag, not which list it arrived in: a deal can
                # be archived and still come back from a live query.
                "archived": bool(dd.get("is_archived")) or bool(dd.get("archive_time")) or is_arch,
                "probability": dd.get("probability"),
                "expected_close": _day(dd.get("expected_close_date")),
                "lost_reason": str(dd.get("lost_reason") or "")[:120],
                "created_at": _iso(dd.get("add_time")),
                "updated_at": _iso(dd.get("update_time")),
                "stage_entered_at": _iso(dd.get("stage_change_time") or dd.get("add_time")),
                "won_at": _iso(dd.get("won_time")),
                "lost_at": _iso(dd.get("lost_time")),
                "source": str(dd.get("origin") or dd.get("source_name") or "Pipedrive")[:40],
                "custom": _custom(dd, deal_fields),
            })

    unmapped_types = {}
    act_rows = []
    for a in acts:
        if not a.get("id"):
            continue
        raw = str(a.get("type") or "task")
        mapped = _TYPE_MAP.get(raw)
        if not mapped:
            unmapped_types[raw] = unmapped_types.get(raw, 0) + 1
            mapped = "task"
        act_rows.append({
            "pd_id": str(a.get("id")),
            "type": mapped, "raw_type": raw,
            "subject": str(a.get("subject") or mapped.capitalize())[:200],
            "deal_pd_id": str(a.get("deal_id") or ""),
            "person_pd_id": str(a.get("person_id") or ""),
            "org_pd_id": str(a.get("org_id") or ""),
            "due_date": _day(a.get("due_date")),
            "due_time": str(a.get("due_time") or "")[:5],
            "note": str(a.get("note") or "")[:20000],
            "location": str((a.get("location") or {}).get("value")
                            if isinstance(a.get("location"), dict)
                            else (a.get("location") or ""))[:200],
            "duration": str(a.get("duration") or "")[:8],
            "done": bool(a.get("done")),
            "done_at": _iso(a.get("marked_as_done_time")),
            "created_at": _iso(a.get("add_time")),
        })

    note_rows = [{"pd_id": str(n.get("id")),
                  "pinned": bool(n.get("pinned_to_deal_flag")
                                 or n.get("pinned_to_person_flag")
                                 or n.get("pinned_to_organization_flag")),
                  "deal_pd_id": str(n.get("deal_id") or ""),
                  "person_pd_id": str(n.get("person_id") or ""),
                  "org_pd_id": str(n.get("org_id") or ""),
                  "text": _strip_note(n.get("content")),
                  "at": _iso(n.get("add_time"))}
                 for n in notes if n.get("id") and n.get("active_flag") is not False]

    return {
        "account": me,
        "stages": stage_rows, "orgs": org_rows, "persons": person_rows,
        "deals": deal_rows, "activities": act_rows, "notes": note_rows,
        "labels": label_opts, "label_colors": label_colors,
        "probability_on": prob_on,
        # stages joins the completeness check deliberately: an empty stage list
        # is not a harmless nothing, it drops every deal into the first column.
        "complete": {"stages": bool(stage_rows), "orgs": orgs_ok, "persons": persons_ok,
                     "deals": deals_ok, "archived": arch_ok, "activities": acts_ok,
                     "notes": notes_ok},
        "not_migrated": {
            "products": len(products),
            "files": len(files),
            "activity_types_flattened": unmapped_types,
            "extra_labels_dropped": extra_labels[0],
        },
    }


def _strip_note(html_text) -> str:
    """Pipedrive notes are HTML. gizmo stores plain text."""
    import re as _re
    import html as _html
    t = str(html_text or "")
    t = _re.sub(r"(?is)<(script|style)[^>]*>.*?(</\1>|$)", " ", t)
    t = _re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</tr>", "\n", t)
    t = _re.sub(r"<[^>]+>", " ", t)
    t = _html.unescape(t)
    return _re.sub(r"[ \t]{2,}", " ", _re.sub(r"\n{3,}", "\n\n", t)).strip()[:20000]
