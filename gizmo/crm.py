"""The CRM: the sales desk, modelled on Pipedrive. The store and its kept board,
deals, contacts, leads, activities, stages and labels, website enquiries
filed as leads, a deal's threads, contact tombstones, the Shopify link sweep,
the import, the CRM's part of an erasure, and the door its routes open with.

Moved out of copilot.py (stage 4 of the 14 October audit); its routes are in
gizmo/routes/crm.py. Read as `salesdesk.NAME` (`crm` is a local name).
"""
import logging
from starlette.responses import JSONResponse
from typing import Optional
from starlette.requests import Request
from starlette.responses import Response
import os
import json
import hashlib
from datetime import datetime, timedelta, timezone
from gizmo.config import _env_num
from gizmo import store as jsonstore
from gizmo import shopify

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


CRM_PATH = os.environ.get("CRM_PATH", "/data/crm.json")
# These are a guard against an unbounded file, not a retention policy. They
# were set when the CRM held what somebody typed in by hand; once it holds an
# imported sales history they are the difference between keeping your won/lost
# record and quietly shredding it. Raised, and the eviction below now REFUSES
# to touch anything rather than deleting the oldest.
CRM_DEALS_MAX = _env_num(int, os.environ.get("CRM_DEALS_MAX", "60000"), "60000", "CRM_DEALS_MAX")
CRM_ACTIVITIES_MAX = _env_num(int, os.environ.get("CRM_ACTIVITIES_MAX", "200000"), "200000", "CRM_ACTIVITIES_MAX")
CRM_NOTE_CAP = 20000                # characters per note
CRM_DELETED_KEEP_DAYS = 30          # Pipedrive's restore window
# The website-enquiry subject is attacker-controllable; this bounds how many
# auto-filed CRM deals a spam run can mint in a day. Real volume is single digits.
CRM_ENQUIRY_DAILY_CAP = _env_num(int, os.environ.get("CRM_ENQUIRY_DAILY_CAP", "50"), "50", "CRM_ENQUIRY_DAILY_CAP")

# Pipedrive seeds a new pipeline with these five stages; renaming them to the
# merchant's own language is the first thing the stage editor is for.
_CRM_DEFAULT_STAGES = [
    {"id": "s1", "name": "Qualified", "probability": 100, "rot_days": 0, "rot_on": False},
    {"id": "s2", "name": "Contact Made", "probability": 100, "rot_days": 0, "rot_on": False},
    {"id": "s3", "name": "Demo Scheduled", "probability": 100, "rot_days": 0, "rot_on": False},
    {"id": "s4", "name": "Proposal Made", "probability": 100, "rot_days": 0, "rot_on": False},
    {"id": "s5", "name": "Negotiations Started", "probability": 100, "rot_days": 0, "rot_on": False},
]
_CRM_ACTIVITY_TYPES = ("call", "meeting", "task", "deadline", "email", "lunch")
_CRM_LOST_REASONS = ["Too expensive", "No response", "Went with someone else", "Timing", "Other"]
# Pipedrive ships Hot/Warm/Cold as lead labels and colour chips on deals.
_CRM_LABELS = ["Hot", "Warm", "Cold"]
# Colour names as Pipedrive uses them; the browser maps names to paint. An
# import overlays this with the account's real labels and their real colours.
_CRM_LABEL_COLORS = {"Hot": "red", "Warm": "yellow", "Cold": "blue"}
_CRM_COLOR_NAMES = ("red", "orange", "yellow", "green", "blue", "purple",
                    "pink", "brown", "gray", "dark-gray")


def _crm_default() -> dict:
    return {"seq": 0, "stages": [dict(s) for s in _CRM_DEFAULT_STAGES],
            "deals": {}, "activities": {}, "persons": {}, "orgs": {}, "leads": {},
            "label_colors": dict(_CRM_LABEL_COLORS),
            "lost_reasons": list(_CRM_LOST_REASONS), "labels": list(_CRM_LABELS),
            "settings": {"followup_popup": True}}


def _load_crm() -> dict:
    return jsonstore._load_json_cached(CRM_PATH, "crm", None, prepare=_crm_prepare)


def _crm_prepare(d) -> dict:
    """What every read of the CRM used to do, now done once per file version:
    the seq recovery below walks every id in five collections, which at tens
    of thousands of deals was real work on every request."""
    if not isinstance(d, dict) or "deals" not in d:
        d = _crm_default()
    for k, v in _crm_default().items():
        d.setdefault(k, v)
    # A store whose counter went missing must never restart at 1 and overwrite
    # d1: recover it from the highest id actually present.
    try:
        peak = max((int(str(k)[1:]) for coll in ("deals", "activities", "persons", "orgs", "leads")
                    for k in d.get(coll, {}) if str(k)[1:].isdigit()), default=0)
        d["seq"] = max(int(d.get("seq") or 0), peak)
    except (TypeError, ValueError):
        pass
    # A store imported before the edit-protection existed has records but no
    # stamp. Draw the line HERE: everything before this moment is fair game
    # for the next import (the data predates the protection and cannot be
    # told apart from import writes), and every edit made from now on carries
    # the edited_here flag, which the import honours forever.
    if "pd_imported_at" not in d and any(v.get("pd_id") for v in d.get("deals", {}).values()):
        d["pd_imported_at"] = _crm_now()
    return d


def _write_crm(d: dict) -> None:
    """Atomic write with the house poison guard. Raises when the store cannot
    be written: the CRM is the only record these deals exist, so a silent
    no-op would lose real pipeline."""
    if not jsonstore._store_writable(CRM_PATH):
        jsonstore._forget_store(CRM_PATH)
        raise RuntimeError("CRM store is not writable")
    # The board is found again by the file's key, and a file rewritten inside
    # one tick of the clock at the same size can come back with the same key.
    _crm_board_forget()
    jsonstore._write_json_store(CRM_PATH, "crm", d)


def _crm_value(x) -> float:
    """A finite, non-negative money amount, or ValueError. NaN and Infinity
    parse as floats but are not JSON, so they must never reach the store."""
    import math
    v = round(float(x or 0), 2)
    if not math.isfinite(v):
        raise ValueError("not a finite amount")
    return max(0.0, v)


def _crm_id(d: dict, prefix: str) -> str:
    d["seq"] = int(d.get("seq") or 0) + 1
    return f"{prefix}{d['seq']}"


def _crm_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _crm_today():
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Europe/London")).date()


def _crm_log(deal: dict, field: str, old, new) -> None:
    """The changelog Pipedrive keeps per deal: stage, value, label, contact and
    expected close changes, plus the lifecycle events."""
    if old == new:
        return
    deal.setdefault("changelog", []).append(
        {"at": _crm_now(), "field": field, "from": old, "to": new})
    deal["changelog"] = deal["changelog"][-100:]


def _crm_touch(deal: dict) -> None:
    """Any edit resets rotting; Pipedrive's rule, including note and activity
    writes, and deliberately ignoring how far out the next activity is.
    The edited_here flag is PERMANENT: once a record is worked on in gizmo,
    no Pipedrive import ever overwrites it again. A timestamp guard looked
    equivalent but was not — the import re-stamps its own high-water mark, so
    a timestamp only protected an edit for one import cycle."""
    deal["touched_at"] = deal["updated_at"] = _crm_now()
    deal["edited_here"] = True


def _crm_next_due_by_deal(activities: dict) -> dict:
    """deal_id -> earliest open due date, in ONE pass over the activities.
    _crm_shape calls the per-deal state for every deal after every write; a
    per-deal scan of all activities made that O(deals x activities), which at
    the imported Pipedrive scale (thousands of deals, tens of thousands of
    activities) is a multi-second event-loop stall on a checkbox tick."""
    out: dict = {}
    for a in activities.values():
        if a.get("done"):
            continue
        due = a.get("due_date") or ""
        if not due:
            continue
        did = a.get("deal_id") or ""
        if did and (did not in out or due < out[did]):
            out[did] = due
    return out


def _crm_activity_state(deal_id: str, next_by_deal: dict, today) -> tuple:
    """(state, next_due) for a deal: the four-colour discipline.
    overdue < today < none < future is also the column sort order, so a deal
    with no next step floats above one that is merely waiting."""
    nxt = next_by_deal.get(deal_id)
    if not nxt:
        return "none", ""
    iso = today.isoformat()
    return ("overdue" if nxt < iso else "today" if nxt == iso else "future"), nxt


_CRM_STATE_RANK = {"overdue": 0, "today": 1, "none": 2, "future": 3}


def _crm_drop_activity(d: dict, ak: str) -> None:
    """An activity gone for good, tombstoned so an import cannot recreate it."""
    apid = str((d["activities"].get(ak) or {}).get("pd_id") or "")
    if apid:
        d.setdefault("pd_deleted_activities", []).append(apid)
        d["pd_deleted_activities"] = d["pd_deleted_activities"][-2000:]
    d["activities"].pop(ak, None)


def _crm_drop_deal(d: dict, k: str) -> None:
    """A deal gone for good, with its activities, and tombstoned.

    The moment the record stops existing is the moment the tombstone has to
    exist instead: without one the next Pipedrive import brings the deal
    straight back, and a deal deleted five weeks ago reappears on the board
    with no explanation. The deal's activities go with it, and each needs its
    own tombstone: with only the deal's, the next import refused the deal and
    recreated every one of its tasks attached to nothing."""
    pid = str((d["deals"].get(k) or {}).get("pd_id") or "")
    if pid:
        d.setdefault("pd_deleted_deals", []).append(pid)
        d["pd_deleted_deals"] = d["pd_deleted_deals"][-5000:]
    d["deals"].pop(k, None)
    for ak in [ak for ak, a in d["activities"].items() if a.get("deal_id") == k]:
        _crm_drop_activity(d, ak)


def _crm_purge(d: dict) -> None:
    """Deleted deals fall out after the 30-day restore window; caps hold."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=CRM_DELETED_KEEP_DAYS)).isoformat()
    dead = [k for k, v in d["deals"].items() if v.get("deleted") and str(v.get("deleted_at") or "") < cutoff]
    for k in dead:
        _crm_drop_deal(d, k)
    # Over the cap, the CRM used to DELETE the oldest closed deals and their
    # activities: silently, with no error, and biting precisely on the won/lost
    # history a business keeps a CRM for. Nothing here deletes a real record any
    # more. Passing the cap is a fault to be reported, not a licence to shred.
    over_d = len(d["deals"]) - CRM_DEALS_MAX
    over_a = len(d["activities"]) - CRM_ACTIVITIES_MAX
    if over_d > 0 or over_a > 0:
        d["over_cap"] = {"deals": max(0, over_d), "activities": max(0, over_a),
                         "at": datetime.now(timezone.utc).isoformat()}
        logger.error("CRM is over its size guard by %d deals / %d activities. Nothing has "
                     "been deleted. Raise CRM_DEALS_MAX / CRM_ACTIVITIES_MAX.", over_d, over_a)
    else:
        d.pop("over_cap", None)


def _crm_slim(rec: dict, drop: tuple) -> dict:
    """A record without its heavy fields, carrying counts instead. At the
    imported scale (2,800 contacts, years of notes) shipping every note and
    changelog line on EVERY response turned a checkbox tick into a megabyte;
    the modal fetches the full record on open instead."""
    out = {k: v for k, v in rec.items() if k not in drop}
    for k in drop:
        if k in ("notes", "changelog"):
            out[k + "_n"] = len(rec.get(k) or [])
    return out


def _crm_shape(d: dict) -> dict:
    """The whole CRM as one payload the tab renders from. Derived state
    (activity colours, rotting, weighted values, badges) is computed here so
    the browser never re-implements the rules."""
    today = _crm_today()
    iso = today.isoformat()
    stages = {s["id"]: s for s in d["stages"]}
    next_by_deal = _crm_next_due_by_deal(d["activities"])   # one pass, not per deal
    deals_out = {}
    for k, v in d["deals"].items():
        if v.get("deleted"):
            continue
        state, next_due = _crm_activity_state(k, next_by_deal, today)
        st = stages.get(v.get("stage_id")) or (d["stages"][0] if d["stages"] else {})
        prob = v.get("probability") if v.get("probability") is not None else st.get("probability", 100)
        # A stage can hold a leftover day count behind a switched-off timer.
        # Honouring the number without the switch turns cards red that the
        # CRM this came from never rotted.
        rot_days = int(st.get("rot_days") or 0) if st.get("rot_on", True) else 0
        rotten = False
        if v.get("status") == "open" and not v.get("archived") and rot_days > 0:
            try:
                touched = datetime.fromisoformat(v.get("touched_at") or v.get("created_at"))
                rotten = (datetime.now(timezone.utc) - touched).days >= rot_days
            except (TypeError, ValueError):
                rotten = False
        deals_out[k] = {**_crm_slim(v, ("deleted", "notes", "changelog")),
                        "activity_state": state, "next_activity": next_due,
                        "effective_probability": prob,
                        "weighted_value": round(float(v.get("value") or 0) * prob / 100.0, 2),
                        "rotten": rotten}
    acts_out = {}
    for k, a in d["activities"].items():
        dl = d["deals"].get(a.get("deal_id") or "")
        if dl and dl.get("deleted"):
            continue
        due = a.get("due_date") or ""
        state = ("done" if a.get("done")
                 else "overdue" if due and due < iso
                 else "today" if due == iso else "future")
        # Slim, like deals and contacts: a 20,000-character note per activity,
        # times every activity in the account, was serialised to the browser on
        # every checkbox tick. The modal fetches the full note on open.
        acts_out[k] = {**_crm_slim(a, ("note",)), "state": state,
                       "note_preview": str(a.get("note") or "")[:160]}
    # An archived deal's leftover to-dos must not nag: archiving is how a
    # quiet deal leaves the desk without polluting the lost reasons.
    badge = sum(1 for a in acts_out.values()
                if a["state"] in ("overdue", "today")
                and not (d["deals"].get(a.get("deal_id") or "") or {}).get("archived"))
    new_leads = sum(1 for l in d["leads"].values() if not l.get("archived") and not l.get("seen"))
    trash = sorted((v for v in d["deals"].values() if v.get("deleted")),
                   key=lambda v: str(v.get("deleted_at") or ""), reverse=True)
    return {"stages": d["stages"], "deals": deals_out, "activities": acts_out,
            "persons": {k: _crm_slim(p, ("notes",)) for k, p in d["persons"].items()},
            "orgs": {k: _crm_slim(o, ("notes",)) for k, o in d["orgs"].items()},
            "leads": d["leads"],
            "lost_reasons": d["lost_reasons"], "labels": d["labels"],
            "label_colors": d.get("label_colors") or dict(_CRM_LABEL_COLORS),
            "settings": d["settings"], "today": iso,
            "badge": badge, "new_leads": new_leads,
            "team": _crm_team_list(), "names": team._team_names(),
            "imported_at": d.get("pd_imported_at") or "",
            "trash": len(trash),
            "trash_items": [{"id": v["id"], "title": v.get("title") or "",
                             "value": v.get("value") or 0,
                             "deleted_at": v.get("deleted_at") or ""}
                            for v in trash[:50]]}


# The board, built once per version of what it is built from (the 2026-10-12
# speed audit, S1): every read rebuilt and serialised the whole board on the
# one event loop, about 50 ms at production size while every other request
# waited, and each open CRM tab read it again every 90 seconds. _crm_shape
# reads the CRM store, the users store (the team list and its names), today's
# London date (what is due) and the clock (a deal rots N days after it was
# last touched), so the key holds each: the two stores by their file (a write,
# a restore or a hand repair is a new file), the date, and the hour, which is
# as late as a rotting flag can come. A write warms it with the board it built.
# What is kept is the board as sent, serialised once, and its revision is a
# fingerprint of those bytes, not of the key: the key also moves on every
# sign-in and wrong password (both write the users store) and stays put across
# an update that shapes the same files another way, and a page is only ever
# told "same" when what it would be sent is the same.
_crm_board_cache: dict = {"key": None, "raw": None, "rev": ""}


def _crm_board_forget() -> None:
    _crm_board_cache.update(key=None, raw=None, rev="")


def _crm_store_forgotten(path: str) -> None:
    """The store forgot a cached copy. If it was the CRM's, the kept board may
    have been built from the store in memory after a change that was then
    never saved, so it goes with it."""
    if path == CRM_PATH:
        _crm_board_forget()


jsonstore.when_forgotten(_crm_store_forgotten)


def _crm_board_key():
    return (jsonstore._stat_key(CRM_PATH), jsonstore._stat_key(team.USERS_PATH), _crm_today().isoformat(),
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H"))


def _crm_board_build(d: dict, key) -> tuple:
    """(raw, revision) for the store `d`, kept under `key`, which the caller
    takes BEFORE building (taken after, a board built in one hour or day was
    kept under the next). It is kept only when `d` is the store as read for
    that key: a read that failed hands back an empty CRM from a file that has
    not changed, and a kept empty board would be served until the next write."""
    raw = gate._json_dumps_like_starlette(_crm_shape(d))
    rev = hashlib.blake2b(raw, digest_size=8).hexdigest()
    hit = jsonstore._json_cache.get(CRM_PATH)
    if (key[0] is not None and CRM_PATH not in jsonstore._poisoned_stores
            and hit is not None and hit[0] == key[0] and hit[1] is d):
        _crm_board_cache.update(key=key, raw=raw, rev=rev)
    return raw, rev


def _crm_board() -> tuple:
    """(raw, revision): the shaped CRM as JSON bytes, built only when
    something it is built from has changed."""
    key = _crm_board_key()
    c = _crm_board_cache
    if key[0] is not None and c["key"] == key:
        return c["raw"], c["rev"]
    return _crm_board_build(_load_crm(), key)


def _crm_answer(raw: bytes, rev: str, head: Optional[dict] = None) -> Response:
    """An answer that carries the board: `head` and the revision, with the
    board's own bytes spliced in as "crm"."""
    return gate._json_spliced({**(head or {}), "rev": rev}, "crm", raw)


def _crm_team_list() -> list:
    """Accounts that can open the CRM tab: the owner pick-list. Small on
    purpose — a name and an id, nothing an account page holds."""
    rows = []
    try:
        for uid, u in team._load_users()["users"].items():
            if u.get("deleted") or not u.get("active", True):
                continue
            tabs = team._user_tabs(uid)
            if tabs is not None and "crm" not in tabs:
                continue
            rows.append({"uid": uid, "name": u.get("name") or u.get("username") or ""})
    except Exception:
        logger.exception("CRM team list failed")
    rows.sort(key=lambda r: r["name"].lower())
    return rows


def _crm_deal_fields(body: dict, d: dict, deal: dict) -> None:
    """Apply the editable deal fields from a request, logging what Pipedrive's
    changelog logs: stage, value, label, contacts, expected close."""
    for field, cast in (("title", lambda x: str(x).strip()[:200]),
                        ("value", _crm_value),
                        ("label", lambda x: str(x).strip()[:40]),
                        ("expected_close", lambda x: str(x).strip()[:10]),
                        ("person_id", lambda x: str(x).strip()[:40]),
                        ("org_id", lambda x: str(x).strip()[:40]),
                        ("owner", lambda x: str(x).strip()[:60]),
                        ("probability", lambda x: (None if x in (None, "") else max(0, min(100, int(x)))))):
        if field in body:
            try:
                new = cast(body.get(field))
            except (TypeError, ValueError):
                continue
            if field in ("value", "label", "expected_close", "person_id", "org_id", "owner"):
                _crm_log(deal, field, deal.get(field), new)
            deal[field] = new
    # Custom fields ride as one dict: names from Pipedrive or typed here,
    # values always text. An empty value removes the field from this deal.
    if isinstance(body.get("custom"), dict):
        cust = dict(deal.get("custom") or {})
        for k, v in list(body["custom"].items())[:30]:
            # None-safe, not falsy-safe: 0 is a value, not a delete.
            k = str(k).strip()[:60]
            v = ("" if v is None else str(v)).strip()[:500]
            if not k or cust.get(k, "") == v:
                continue
            _crm_log(deal, k, cust.get(k, ""), v)
            if v:
                cust[k] = v
            else:
                cust.pop(k, None)
        deal["custom"] = cust


def _crm_enquiry_stage(d: dict) -> str:
    """The 'Contact Made' column by name, however the pipeline spells it;
    an enquiry with no such column still lands somewhere visible."""
    for s in d.get("stages") or []:
        if str(s.get("name") or "").strip().lower() == "contact made":
            return s["id"]
    for s in d.get("stages") or []:
        if "contact" in str(s.get("name") or "").lower():
            return s["id"]
    return d["stages"][0]["id"] if d.get("stages") else ""


def _crm_file_enquiry(t: dict, parsed: dict) -> str:
    """One enquiry thread into the CRM. Idempotent by thread id: a sync that
    dies between the CRM write and the mail write must not file it twice."""
    d = _load_crm()
    for v in d["deals"].values():
        if v.get("mail_thread_id") == t.get("id") and not v.get("deleted"):
            return v["id"]
    email = str(parsed.get("email") or t.get("from_email") or "").strip()[:200]
    name = str(parsed.get("name") or t.get("from_name") or email or "Website enquiry").strip()[:120]
    phone = str(parsed.get("phone") or "").strip()[:40]
    company = str(parsed.get("company") or "").strip()[:120]
    org_id = ""
    if company:
        org = next((o for o in d["orgs"].values()
                    if str(o.get("name") or "").lower() == company.lower()), None)
        if org is None:
            org = {"id": _crm_id(d, "o"), "name": company, "address": "", "website": "",
                   "label": "", "created_at": _crm_now(), "updated_at": _crm_now(), "notes": []}
            d["orgs"][org["id"]] = org
        org_id = org["id"]
    person = None
    if email:
        low = email.lower()
        person = next((p for p in d["persons"].values()
                       if any(str(e).lower() == low for e in (p.get("emails") or []))), None)
    if person is None:
        person = {"id": _crm_id(d, "p"), "name": name, "org_id": org_id,
                  "emails": [email] if email else [],
                  "phones": [phone] if phone else [],
                  "label": "", "shopify_customer_id": None,
                  "created_at": _crm_now(), "updated_at": _crm_now(), "notes": []}
        d["persons"][person["id"]] = person
    else:
        # A known customer enquiring again. Everything here was parsed out of
        # an email ANYONE can send to the public shared address while claiming
        # to be them, so it does not touch the existing record: no appended
        # phone number, no org, and above all no edited_here stamp, which is
        # permanent and would freeze that contact against every future
        # Pipedrive import. The claim lives in the deal's note instead, where
        # a human can act on it.
        pass
    stage = _crm_enquiry_stage(d)
    note = str(parsed.get("message") or t.get("snippet") or "").strip()[:CRM_NOTE_CAP]
    # Details the form claimed that were NOT written onto the contact record
    # ride in the note, so nothing is lost and nothing is trusted.
    claimed = [x for x in (("phone " + phone) if phone else "",
                           ("company " + company) if company else "") if x]
    if claimed:
        note = (note + "\n\nGiven on the form: " + ", ".join(claimed)).strip()[:CRM_NOTE_CAP]
    deal = {"id": _crm_id(d, "d"), "title": (name + " - website enquiry")[:200],
            "value": 0.0, "currency": "GBP", "stage_id": stage,
            "person_id": person["id"], "org_id": org_id or person.get("org_id") or "",
            "label": "", "status": "open", "probability": None,
            "expected_close": "", "source": "Website form", "owner": "",
            "mail_thread_id": str(t.get("id") or ""),
            "created_at": _crm_now(), "updated_at": _crm_now(),
            "stage_entered_at": _crm_now(), "touched_at": _crm_now(),
            "notes": ([{"id": _crm_id(d, "n"), "text": note, "at": _crm_now(),
                        "pinned": False}] if note else []),
            "changelog": []}
    _crm_log(deal, "created", "", "from the website form")
    d["deals"][deal["id"]] = deal
    _crm_purge(d)
    _write_crm(d)
    activity._track("", "crm", "filed a website enquiry", deal["title"][:60])
    return deal["id"]


def _crm_deal_threads(d: dict, deal: dict) -> list:
    """The email history behind a deal: every shared-inbox thread whose
    correspondent is the deal's linked person (any of their addresses), plus
    the thread the deal was born from if it came off the website form. Compact
    rows only - subject, snippet, state - the full conversation stays behind
    the Inbox, where reading marks it read and viewers are counted."""
    person = d.get("persons", {}).get(deal.get("person_id") or "") or {}
    addrs = {str(e).lower() for e in (person.get("emails") or []) if str(e).strip()}
    born = str(deal.get("mail_thread_id") or "")
    if not addrs and not born:
        return []
    try:
        store = mail._load_mail()
    except Exception:
        return []
    rows = []
    for t in store.get("threads", {}).values():
        # The thread's COUNTERPARTY, not "somebody in this thread once". Gmail
        # groups a forward or a cc into whatever thread it lands in, so
        # matching any message sender put another customer's whole
        # conversation - their subject, their snippet, their owner - into this
        # deal's history, where a rep reads it as this customer's. from_email
        # is already the first sender who is not us, which is exactly the test.
        hit = (t.get("id") == born or str(t.get("from_email") or "").lower() in addrs)
        if not hit:
            continue
        rows.append({"id": t.get("id"), "subject": t.get("subject") or "(no subject)",
                     "snippet": t.get("snippet") or "", "last_at": t.get("last_at") or "",
                     "msg_count": t.get("msg_count") or 0,
                     "state": t.get("state") or "", "unread": bool(t.get("unread")),
                     "owner_name": team._team_name(t.get("owner")) if t.get("owner") else ""})
    rows.sort(key=lambda r: r["last_at"], reverse=True)
    return rows[:20]


def _crm_contact_open_ref(d: dict, kind: str, cid: str) -> int:
    """How many OPEN deals or leads still point at this contact. Leads are a
    first-class reference (a lead must belong to someone), so a contact held
    only by a live enquiry must not be deletable out from under it."""
    ref = "person_id" if kind == "persons" else "org_id"
    # A BINNED deal counts too. It is not gone, it is restorable for 30 days -
    # and a deal restored to find its person and organisation deleted from
    # under it is a deal nobody can ring back.
    deals = sum(1 for v in d["deals"].values()
                if v.get(ref) == cid and v.get("status") == "open")
    leads = sum(1 for l in d["leads"].values()
                if l.get(ref) == cid and not l.get("archived"))
    return deals + leads


def _crm_tombstone_contact(d: dict, kind: str, rec: dict) -> None:
    """Remove a contact AND remember its Pipedrive id(s), so a later import
    cannot resurrect it - the same anti-resurrection discipline merge, notes
    and activities already use."""
    store_key = "pd_deleted_persons" if kind == "persons" else "pd_deleted_orgs"
    for pid in [rec.get("pd_id")] + list(rec.get("pd_merged_ids") or []):
        if pid:
            d.setdefault(store_key, []).append(str(pid))
    if d.get(store_key):
        d[store_key] = d[store_key][-20000:]
    d[kind].pop(rec["id"], None)


async def _crm_shopify_link_sweep(registry: dict, max_pages: int = 40) -> dict:
    """Fill in person.shopify_customer_id by email, in bulk. One paginated
    customer crawl indexed in memory, then a single pass over the people -
    2,800 per-contact searches would take twenty minutes of rate limit; this
    takes a dozen requests.

    Rules that keep it safe to run nightly forever: an EXISTING link is never
    touched (a hand-made link outranks a guess); a person whose addresses
    match two DIFFERENT customers is skipped and counted, never guessed; and
    neither updated_at nor edited_here is stamped - a link is an enrichment,
    and stamping 2,800 contacts would freeze them all against a final
    Pipedrive import."""
    report = {"customers": 0, "linked": 0, "already": 0, "ambiguous": 0, "unmatched": 0,
              "complete": True, "problem": ""}
    by_email: dict = {}
    since = 0
    pages = 0
    for _ in range(max_pages):
        res = await shopify._tool_json(registry, "shopify_list_customers",
                               {"limit": 250, "since_id": since, "fields": "id,email"})
        # A swallowed failure must never read as "no more customers". _tool_json
        # returns {"_failed": True} for a throttle, a 5xx or a timeout, and
        # without this a 429 on page three ended the crawl, reported success,
        # and counted every remaining contact as having no Shopify customer.
        if not core._ok(res):
            report["complete"] = False
            report["problem"] = ("Shopify stopped answering partway through, so this is "
                                 "only part of your customers. Run it again in a moment.")
            break
        rows = (res or {}).get("customers") or []
        if not rows:
            break
        pages += 1
        for c in rows:
            e = str(c.get("email") or "").strip().lower()
            if e and c.get("id"):
                if e in by_email and by_email[e] != c["id"]:
                    by_email[e] = None   # two customers share this email: never guess
                elif e not in by_email:
                    by_email[e] = c["id"]
            try:
                since = max(since, int(c.get("id") or 0))
            except (TypeError, ValueError):
                pass
        if len(rows) < 250:
            break
    else:
        # Ran out of pages rather than customers: the one exit that used to
        # carry no signal at all, so the rest were silently "unmatched".
        report["complete"] = False
        report["problem"] = ("More customers than this sweep reads in one go ("
                             + str(max_pages * 250) + "). The rest are not linked yet.")
    report["customers"] = len(by_email)
    if not by_email:
        return report
    d = _load_crm()
    changed = False
    for p in d.get("persons", {}).values():
        if p.get("shopify_customer_id"):
            report["already"] += 1
            continue
        addrs = [str(x).strip().lower() for x in (p.get("emails") or [])]
        # None in by_email marks an address two customers share: it makes the
        # match ambiguous rather than silently linking whichever paginated last.
        matched = [e for e in addrs if e in by_email]
        hits = {by_email[e] for e in matched}
        if any(by_email[e] is None for e in matched) or len(hits) > 1:
            report["ambiguous"] += 1
        elif not hits:
            report["unmatched"] += 1
        else:
            p["shopify_customer_id"] = next(iter(hits))
            report["linked"] += 1
            changed = True
    if changed:
        _write_crm(d)
    return report


async def _crm_shopify_link_nightly(registry: dict) -> None:
    """The scheduler's once-a-day pass, stamped in the CRM store so a redeploy
    or restart never doubles it up. Quiet on failure: linking is enrichment,
    and the next day gets another chance."""
    try:
        d = _load_crm()
        if not d.get("persons"):
            return
        last = str(d.get("shopify_link_at") or "")
        if last:
            try:
                if (datetime.now(timezone.utc)
                        - datetime.fromisoformat(last)).total_seconds() < 20 * 3600:
                    return
            except ValueError:
                pass
        rep = await _crm_shopify_link_sweep(registry)
        d = _load_crm()
        d["shopify_link_at"] = _crm_now()
        _write_crm(d)
        if rep["linked"]:
            activity._track("", "crm", "linked contacts to Shopify",
                   str(rep["linked"]) + " matched by email")
        logger.info("crm: shopify link sweep %s", rep)
    except Exception:
        logger.exception("crm: shopify link sweep failed")
        jsonstore._forget_store(CRM_PATH)   # a half-made change must not be served


def _crm_link_order_customer(order: dict) -> None:
    """A single arriving order links its customer on the spot, so a brand-new
    enquirer who converts is linked the day they order, not tomorrow night.
    Same rules as the sweep: never overwrite, never guess."""
    try:
        cust = order.get("customer") or {}
        cid = cust.get("id")
        email = str(order.get("email") or cust.get("email") or "").strip().lower()
        if not cid or not email:
            return
        d = _load_crm()
        changed = False
        for p in d.get("persons", {}).values():
            if p.get("shopify_customer_id"):
                continue
            if any(str(x).strip().lower() == email for x in (p.get("emails") or [])):
                p["shopify_customer_id"] = cid
                changed = True
        if changed:
            _write_crm(d)
    except Exception:
        logger.exception("crm: order-customer link failed")
        jsonstore._forget_store(CRM_PATH)   # a half-made change must not be served


_crm_bg_tasks: set = set()


async def _crm_link_order_later(body_txt: str) -> None:
    """Link an arriving order's customer AFTER the webhook has been answered,
    but on the EVENT LOOP - never in a thread.

    The CRM store's entire safety story is that one writer runs at a time:
    every route loads, mutates and writes without awaiting in between, so two
    writes cannot interleave. A worker thread runs in genuine parallel with
    the loop, so it can read the store, have a route write a won deal
    underneath it, and then install its own stale snapshot - or truncate the
    store outright, because _write_crm's temp path is shared. Deferring to the
    loop keeps the receiver fast (the ack is already sent) and keeps the
    single-writer rule intact."""
    try:
        _crm_link_order_customer(json.loads(body_txt))
    except Exception:
        logger.exception("crm: order-customer link failed")
        jsonstore._forget_store(CRM_PATH)   # a half-made change must not be served


def _crm_link_order_soon(body_txt: str) -> None:
    core._spawn_bg(_crm_link_order_later(body_txt))


def _crm_erase_links(d: dict, pids: set, orgs_touched=()) -> tuple:
    """What hangs off contacts being erased (already tombstoned by the caller):
    their own deals go (a website enquiry, a deal with no organisation), with
    their tasks; an organisation's deal stays without them as its contact, and
    so do its tasks; an organisation that existed only because of them goes;
    their leads go. Returns (records erased, mail threads that were theirs)."""
    erased, threads = 0, set()
    orgs_touched = {str(x) for x in (orgs_touched or ()) if isinstance(x, (str, int))}
    if not pids:
        return erased, threads
    for k in [k for k, v in (d.get("deals") or {}).items() if str(v.get("person_id") or "") in pids]:
        deal = d["deals"][k]
        if deal.get("mail_thread_id"):
            threads.add(str(deal["mail_thread_id"]))
        own = (str(deal.get("source") or "") == "Website form" or deal.get("mail_thread_id")
               or not str(deal.get("org_id") or "").strip())
        if str(deal.get("org_id") or "").strip():
            orgs_touched.add(str(deal["org_id"]))
        if own:
            _crm_drop_deal(d, k)
        else:
            # An organisation's deal is the organisation's record: a won or
            # lost deal is the history a CRM is kept for, and this person was
            # only its contact. It stays, without them in it, and is NOT
            # frozen against the import: Pipedrive's later changes still
            # arrive, and every import takes the person out again.
            deal["person_id"] = ""
        erased += 1
    for ak in [ak for ak, a in (d.get("activities") or {}).items() if str(a.get("person_id") or "") in pids]:
        act = d["activities"][ak]
        if str(act.get("deal_id") or "") in (d.get("deals") or {}):
            act["person_id"] = ""
        else:
            _crm_drop_activity(d, ak)
    for rec_org in orgs_touched:
        org = (d.get("orgs") or {}).get(rec_org)
        if org and not org.get("pd_id") \
                and not any(str(p.get("org_id") or "") == rec_org for p in d["persons"].values()) \
                and not any(str(v.get("org_id") or "") == rec_org for v in d["deals"].values()):
            org["id"] = rec_org
            _crm_tombstone_contact(d, "orgs", org)
    for lid in [k for k, v in (d.get("leads") or {}).items() if str(v.get("person_id") or "") in pids]:
        if d["leads"][lid].get("mail_thread_id"):
            threads.add(str(d["leads"][lid]["mail_thread_id"]))
        d["leads"].pop(lid, None)
        erased += 1
    return erased, threads

# ---- CRM routes -------------------------------------------------------
async def _crm_guard(request: Request):
    """(error_response, body, who). The CRM is buttons in the app's own UI,
    so it uses the same session auth as everything else; the AI never sees
    it. Shaped like _guard, which is what every other door here returns.

    The caller used to be stashed in a dict shared by every CRM route and
    read back further down the handler. That held only while no `await`
    ever appeared between the guard and the read - true when it was
    written, and by the end one route was reading it 101 lines later with
    nothing enforcing the rule. Returning it makes the guarantee
    structural: a handler can only use the caller it was handed."""
    err, body, who = await gate._guard(request)
    if err:
        return err, None, ""
    return None, body, who

def _crm_ok(d: dict, extra: Optional[dict] = None, action: str = "",
            detail: str = "", who: str = "") -> JSONResponse:
    _crm_purge(d)
    _write_crm(d)
    if action:
        activity._track(who, "crm", action, detail)
    raw, rev = _crm_board_build(d, _crm_board_key())
    return _crm_answer(raw, rev, {"ok": True, **(extra or {})})

def _crm_import_apply(d: dict, data: dict, dry: bool) -> dict:
    """Merge a Pipedrive export into the CRM store.

    Idempotent by construction: every imported record keeps its Pipedrive
    id, and a second run finds that id and UPDATES rather than making a
    second copy. Anything typed into gizmo by hand has no Pipedrive id and
    is never touched.

    With dry=True nothing is written and the counts describe exactly what
    a real run would do."""
    report = {"stages": {"new": 0, "updated": 0}, "orgs": {"new": 0, "updated": 0},
              "persons": {"new": 0, "updated": 0}, "deals": {"new": 0, "updated": 0},
              "activities": {"new": 0, "updated": 0}, "notes": {"added": 0},
              "custom_values": 0,
              "kept": {"deals": 0, "persons": 0, "orgs": 0},
              "kept_edited": {"deals": 0, "persons": 0, "orgs": 0, "activities": 0,
                              "stages": 0},
              "problems": []}

    def index(coll):
        # A merge absorbs the loser's Pipedrive identity: its rows must
        # keep resolving to the winner, or the next import would recreate
        # the duplicate and re-point every deal back at it.
        ix = {}
        for k, v in d[coll].items():
            if v.get("pd_id"):
                ix[str(v["pd_id"])] = k
            for m in (v.get("pd_merged_ids") or []):
                ix[str(m)] = k
        return ix

    # Records with no pd_id were typed in here; they survive untouched.
    for coll, key in (("deals", "deals"), ("persons", "persons"), ("orgs", "orgs")):
        report["kept"][key] = len([1 for v in d[coll].values() if not v.get("pd_id")])

    # A record EDITED IN GIZMO also survives untouched: without this rule,
    # pressing Import reverts every stage move, every won, and every
    # ticked task back to whatever Pipedrive last knew — months of work
    # undone by one button. The flag is set by every gizmo write and never
    # cleared: once worked on here, a record is gizmo's. The timestamp
    # fallback covers edits made before the flag existed.
    last_import = str(d.get("pd_imported_at") or "")

    def edited_here(rec) -> bool:
        if rec is None:
            return False
        if rec.get("edited_here"):
            return True
        return bool(last_import and str(rec.get("updated_at") or "") > last_import)

    # --- stages: the imported pipeline replaces the imported stages, in
    # Pipedrive's order. Stages MADE IN GIZMO (no pd_id) are kept, after
    # the imported ones: dropping them would orphan every deal that had
    # been moved into them, silently, off the board.
    by_pd = {str(s.get("pd_id")): s for s in (d.get("stages") or []) if s.get("pd_id")}
    new_stages, seen_stage = [], {}
    for i, st in enumerate(data.get("stages") or []):
        prev = by_pd.get(st["pd_id"])
        sid = prev["id"] if prev else ("s_pd" + st["pd_id"])
        seen_stage[st["pd_id"]] = sid
        if prev and prev.get("edited_here"):
            # The import's whole promise is that gizmo-side work survives.
            # Stages were the one exception: a renamed stage, a retuned
            # probability or a rot timer set at the desk was rebuilt from
            # Pipedrive on every run, silently.
            new_stages.append(dict(prev))
            report["kept_edited"]["stages"] = report["kept_edited"].get("stages", 0) + 1
            continue
        new_stages.append({"id": sid, "name": st["name"] or ("Stage " + str(i + 1)),
                           "probability": st.get("probability") if st.get("probability") is not None else 100,
                           "rot_on": bool(st.get("rot_on")),
                           "rot_days": int(st.get("rot_days") or 0),
                           "rot_days_stored": int(st.get("rot_days_stored") or 0),
                           "pd_id": st["pd_id"]})
        report["stages"]["updated" if prev else "new"] += 1
    # Any old stage still holding deals rides along — gizmo-made stages,
    # and stages Pipedrive itself deleted. Binned deals count too: a deal
    # restored inside its 30-day window must land back in a real column.
    if new_stages:
        final_ids = {s["id"] for s in new_stages}
        holdovers = [s for s in (d.get("stages") or [])
                     if s["id"] not in final_ids
                     and any(v.get("stage_id") == s["id"] for v in d["deals"].values())]
        new_stages = new_stages + holdovers
    if len(new_stages) > 12:
        report["problems"].append(
            "Pipedrive has " + str(len(new_stages)) + " stages and this board holds 12. "
            "The extra ones would have nowhere to go.")
    if not dry and new_stages:
        d["stages"] = new_stages

    org_ix, person_ix, deal_ix = index("orgs"), index("persons"), index("deals")
    org_of, person_of, deal_of = {}, {}, {}
    # Contacts deleted here are tombstoned: a later import must not
    # resurrect them, the way it already refuses deleted notes/activities.
    dead_orgs = set(d.get("pd_deleted_orgs") or [])
    dead_persons = set(d.get("pd_deleted_persons") or [])

    # People erased on request, and what the import does about them: they are
    # never brought back as a contact, and their name, addresses and numbers
    # are taken out of everything it writes, every time, because Pipedrive
    # keeps the organisation deals they were on and keeps updating them. A
    # Pipedrive contact is recognised as erased only by the address the
    # erasure was asked for (the CRM's keyed marks, and the mailbox's list,
    # which also holds erasures from before the marks existed), or by the
    # Pipedrive id their contact had. By id alone, its words are learned only
    # when one of them is already known as theirs: an id now holding somebody
    # else must not make that person erased. What live contacts hold is
    # theirs too, and is left alone.
    erased_pd = {str(x) for x in (d.get("erased_pd_persons") or [])}
    try:
        mail_gone = [a for a in (mail._load_mail().get("redacted") or []) if isinstance(a, str)]
    except Exception:
        logger.exception("crm import: could not read the erased addresses from the mailbox")
        mail_gone = []
    blocker = privacy._erase_import_blocker(d)
    if blocker:
        report["problems"].append(blocker)
    base = privacy._erase_scrubber(d, requests=mail_gone)
    found: dict = {}                    # Pipedrive id -> their words, as Pipedrive has them now
    payload_people = [p for p in (data.get("persons") or []) if str(p.get("pd_id") or "")]
    for p in payload_people:
        pd = str(p["pd_id"])
        if base is None:
            break
        words = privacy._erase_words_of(p)
        if any(base.knows("req", e) for e in (p.get("emails") or [])):
            found[pd] = words
        elif pd in erased_pd and any(base.knows(k, c) for k, c, _n in privacy._erase_canon(p.get("name")) if k == "name"):
            # By id, only with their NAME: an id Pipedrive gave to their
            # successor keeps the firm's switchboard and office@ address,
            # which must not make the successor erased.
            found[pd] = words
    # A duplicate of them (same name AND a shared address or number) is them
    # too: in Pipedrive, where it still arrives as its own contact, and in the
    # CRM, where Pipedrive may have merged it into theirs.
    if found:
        for p in payload_people:
            pd = str(p["pd_id"])
            if pd not in found and any(privacy._erase_same_person(privacy._erase_words_of(p), w) for w in list(found.values())):
                found[pd] = privacy._erase_words_of(p)
    held = {pd: person_ix[pd] for pd in found
            if person_ix.get(pd) and person_ix[pd] in (d.get("persons") or {})}
    if found:
        for gid, rec in (d.get("persons") or {}).items():
            if gid not in held.values() and any(privacy._erase_same_person(privacy._erase_words_of(rec), w)
                                                 for w in list(found.values())):
                held["dup:" + gid] = gid
    held_ids = set(held.values())
    learned: list = []
    for words in found.values():
        learned.extend(words)
    for gid in held_ids:
        learned.extend(privacy._erase_words_of(d["persons"][gid]))
    alive = privacy._erase_alive([p for p in payload_people if str(p["pd_id"]) not in found]
                         + [p for k, p in (d.get("persons") or {}).items()
                            if k not in held_ids and str(p.get("pd_id") or "") not in erased_pd],
                         [o.get("name") for o in (data.get("orgs") or [])]
                         + [o.get("name") for o in (d.get("orgs") or {}).values()])
    scrub_fn = privacy._erase_scrubber(d, words=learned, alive=alive, requests=mail_gone)
    linked_pd = set(found) | erased_pd
    # Their organisations: the one they were the contact for is theirs to
    # clean, whatever a namesake elsewhere is called.
    linked_org_pd = {str(p.get("org_pd_id")) for p in payload_people
                     if str(p["pd_id"]) in found and p.get("org_pd_id")}
    scrubbed_keys: set = set()
    report["erased"] = {"people": len(found), "scrubbed": 0}

    def scrub(v, linked=False, key=None):
        """Their details out of one imported text, noting the record it is in."""
        if scrub_fn is None or not isinstance(v, str) or not v:
            return v
        out = scrub_fn(v, linked)
        if out != v and key:
            scrubbed_keys.add(key)
        return out

    def scrub_custom(c, linked=False, key=None):
        return {ck: scrub(cv, linked, key) for ck, cv in (c or {}).items()}

    dead_persons |= set(found)

    # --- organisations, then people, then deals, then their activities and
    # notes: each one links to the one before, so the order is the order.
    for o in data.get("orgs") or []:
        if o["pd_id"] in dead_orgs:
            continue
        gid = org_ix.get(o["pd_id"])
        rec = d["orgs"].get(gid) if gid else None
        if rec is not None and edited_here(rec):
            report["kept_edited"]["orgs"] = report["kept_edited"].get("orgs", 0) + 1
            org_of[o["pd_id"]] = gid
            continue
        if rec is None:
            gid = "o_pd" + o["pd_id"]
            rec = {"id": gid, "notes": []}
            report["orgs"]["new"] += 1
        else:
            report["orgs"]["updated"] += 1
        report["custom_values"] += len(o.get("custom") or {})
        o_linked = str(o.get("pd_id") or "") in linked_org_pd
        rec.update({"name": o["name"], "address": scrub(o["address"], o_linked, ("orgs", gid)),
                    "website": o.get("website", ""),
                    "label": o.get("label") or rec.get("label", ""),
                    "custom": scrub_custom(o.get("custom") or rec.get("custom") or {}, o_linked, ("orgs", gid)),
                    "created_at": o["created_at"] or rec.get("created_at") or _crm_now(),
                    "updated_at": o["updated_at"] or _crm_now(), "pd_id": o["pd_id"]})
        rec.setdefault("notes", [])
        org_of[o["pd_id"]] = gid
        if not dry:
            d["orgs"][gid] = rec

    for p in data.get("persons") or []:
        if p["pd_id"] in dead_persons:
            continue
        gid = person_ix.get(p["pd_id"])
        rec = d["persons"].get(gid) if gid else None
        if rec is not None and edited_here(rec):
            report["kept_edited"]["persons"] += 1
            person_of[p["pd_id"]] = gid
            continue
        if rec is None:
            gid = "p_pd" + p["pd_id"]
            rec = {"id": gid, "notes": [], "shopify_customer_id": None}
            report["persons"]["new"] += 1
        else:
            report["persons"]["updated"] += 1
        report["custom_values"] += len(p.get("custom") or {})
        rec.update({"name": p["name"], "emails": p["emails"], "phones": p["phones"],
                    "email_labels": p.get("email_labels") or [],
                    "phone_labels": p.get("phone_labels") or [],
                    "job_title": scrub(p.get("job_title", ""), key=("persons", gid)),
                    "org_id": org_of.get(p["org_pd_id"], rec.get("org_id", "")),
                    "label": p.get("label") or rec.get("label", ""),
                    "custom": scrub_custom(p.get("custom") or rec.get("custom") or {}, key=("persons", gid)),
                    "created_at": p["created_at"] or rec.get("created_at") or _crm_now(),
                    "updated_at": p["updated_at"] or _crm_now(), "pd_id": p["pd_id"]})
        rec.setdefault("notes", [])
        rec.setdefault("shopify_customer_id", None)
        person_of[p["pd_id"]] = gid
        if not dry:
            d["persons"][gid] = rec

    lost_reasons = set(d.get("lost_reasons") or [])
    dead_deals = set(d.get("pd_deleted_deals") or [])
    for dl in data.get("deals") or []:
        if dl["pd_id"] in dead_deals:
            continue          # deleted here means deleted, not "until next import"
        gid = deal_ix.get(dl["pd_id"])
        rec = d["deals"].get(gid) if gid else None
        if rec is not None and edited_here(rec):
            report["kept_edited"]["deals"] += 1
            deal_of[dl["pd_id"]] = gid
            continue
        if rec is None:
            gid = "d_pd" + dl["pd_id"]
            rec = {"id": gid, "notes": [], "changelog": []}
            report["deals"]["new"] += 1
        else:
            report["deals"]["updated"] += 1
        report["custom_values"] += len(dl.get("custom") or {})
        dl_linked = str(dl.get("person_pd_id") or "") in linked_pd
        closed = dl.get("won_at") if dl["status"] == "won" else dl.get("lost_at")
        # won_at is what the Insights tab reads. Folding it into closed_at
        # made an imported sales history report "no wins yet".
        rec.update({
            "title": scrub(dl["title"], dl_linked, ("deals", gid)), "value": dl["value"], "currency": dl["currency"],
            "stage_id": seen_stage.get(dl["stage_pd_id"])
                        or (d["stages"][0]["id"] if d.get("stages") else ""),
            "person_id": person_of.get(dl["person_pd_id"], ""),
            "org_id": org_of.get(dl["org_pd_id"], ""),
            "status": dl["status"], "probability": dl.get("probability"),
            "expected_close": dl["expected_close"],
            "lost_reason": scrub(dl["lost_reason"], dl_linked, ("deals", gid)), "source": dl["source"],
            "archived": dl["archived"],
            "created_at": dl["created_at"] or _crm_now(),
            "updated_at": dl["updated_at"] or _crm_now(),
            "stage_entered_at": dl["stage_entered_at"] or dl["created_at"] or _crm_now(),
            "closed_at": closed or "",
            "won_at": dl.get("won_at") or "", "lost_at": dl.get("lost_at") or "",
            "label": dl.get("label", rec.get("label", "")),
            "custom": scrub_custom(dl.get("custom") or rec.get("custom") or {}, dl_linked, ("deals", gid)),
            "touched_at": dl["updated_at"] or dl["created_at"] or _crm_now(),
            "pd_id": dl["pd_id"],
        })
        rec.setdefault("notes", [])
        rec.setdefault("changelog", [])
        if rec.get("lost_reason") and "[erased]" not in rec["lost_reason"]:
            lost_reasons.add(rec["lost_reason"][:60])
        deal_of[dl["pd_id"]] = gid
        if not dry:
            d["deals"][gid] = rec
    if not dry:
        d["lost_reasons"] = sorted(lost_reasons)[:40]
        # Their label names and colours, not the three this app shipped with:
        # a label the board cannot colour renders as a grey dot. Deal labels
        # feed the deal picker; person and org label colours join the map so
        # every chip paints, whichever entity it sits on.
        labs = [v.get("name") for v in (data.get("labels") or {}).values() if v.get("name")]
        if labs:
            d["labels"] = labs[:20]
        colors = dict(d.get("label_colors") or {})
        colors.update({k: v for k, v in (data.get("label_colors") or {}).items() if k and v})
        colors.update({v["name"]: v.get("color", "")
                       for v in (data.get("labels") or {}).values() if v.get("name")})
        if colors:
            d["label_colors"] = colors

    act_ix = index("activities")
    dead_acts = set(d.get("pd_deleted_activities") or [])
    for a in data.get("activities") or []:
        if a["pd_id"] in dead_acts:
            continue
        if a.get("deal_pd_id") and a["deal_pd_id"] in dead_deals:
            continue      # its deal was deleted here: the task does not come back without it
        gid = act_ix.get(a["pd_id"])
        rec = d["activities"].get(gid) if gid else None
        if rec is not None and edited_here(rec):
            report["kept_edited"]["activities"] += 1
            continue
        if rec is None:
            gid = "a_pd" + a["pd_id"]
            rec = {"id": gid}
            report["activities"]["new"] += 1
        else:
            report["activities"]["updated"] += 1
        a_linked = str(a.get("person_pd_id") or "") in linked_pd
        rec.update({
            "type": a["type"], "subject": scrub(a["subject"], a_linked, ("activities", gid)),
            "deal_id": deal_of.get(a["deal_pd_id"], ""),
            "person_id": person_of.get(a["person_pd_id"], ""),
            "org_id": org_of.get(a["org_pd_id"], ""),
            # An activity with no due date stays undated. Giving it one
            # makes the app invent a job: either overdue today, or a task
            # that was never scheduled appearing in somebody's week.
            "due_date": a["due_date"] or "",
            "due_time": a["due_time"], "note": scrub(a["note"][:CRM_NOTE_CAP], a_linked, ("activities", gid)),
            "location": scrub(a["location"], a_linked, ("activities", gid)), "priority": "",
            # Likewise a done date: stamping today would drop years of
            # completed work into "activities completed, last 30 days".
            "done": a["done"], "done_at": a["done_at"] or "",
            "duration": a.get("duration", ""),
            "created_at": a["created_at"] or _crm_now(), "pd_id": a["pd_id"],
        })
        if not dry:
            d["activities"][gid] = rec

    for n in data.get("notes") or []:
        if not n["text"]:
            continue
        coll = gid = None
        if n["deal_pd_id"] and deal_of.get(n["deal_pd_id"]):
            coll, gid = "deals", deal_of[n["deal_pd_id"]]
        elif str(n.get("person_pd_id") or "") in linked_pd:
            # Their own note ("only ring her after 5pm: she is a carer") names
            # nobody, so no scrub can catch it; with their contact gone it
            # used to land on the organisation. It stays out.
            continue
        elif n["person_pd_id"] and person_of.get(n["person_pd_id"]):
            coll, gid = "persons", person_of[n["person_pd_id"]]
        elif n["org_pd_id"] and org_of.get(n["org_pd_id"]):
            coll, gid = "orgs", org_of[n["org_pd_id"]]
        if coll is None:
            continue
        # In a preview a record this import would create is not there yet.
        target = d[coll].get(gid)
        if target is None and not dry:
            continue
        report["notes"]["added"] += 1
        # Deleted here means deleted: the tombstone stops every later
        # import from quietly resurrecting a note somebody removed. Checked
        # in the preview too, so what it counts is what the run does.
        if target is not None and (
                any(str(x.get("pd_id")) == n["pd_id"] for x in (target.get("notes") or []))
                or n["pd_id"] in set(target.get("pd_deleted_notes") or [])):
            continue
        text = scrub(n["text"][:CRM_NOTE_CAP], str(n.get("person_pd_id") or "") in linked_pd, (coll, gid))
        if dry:
            continue
        target.setdefault("notes", []).append(
            {"id": _crm_id(d, "n"), "at": n["at"] or _crm_now(), "by": "",
             "text": text, "pinned": bool(n.get("pinned")), "pd_id": n["pd_id"]})

    # A contact recognised as erased that the CRM already holds (brought back
    # by an import before this one, or a duplicate Pipedrive merged into
    # theirs) is erased here too, the way an erasure does it. Then every
    # record the CRM keeps is swept, desk-edited ones included, so nothing
    # that names an erased person survives an import either.
    held_orgs = {str(d["persons"][g].get("org_id")) for g in held_ids
                 if g in d["persons"] and d["persons"][g].get("org_id")}
    linked_orgs = held_orgs | {org_of[x] for x in linked_org_pd if org_of.get(x)}
    held_words = {g: (privacy._erase_words_of(d["persons"][g]),
                      [x for x in [d["persons"][g].get("pd_id")] + list(d["persons"][g].get("pd_merged_ids") or []) if x])
                  for g in held_ids if g in d["persons"]}
    if not dry:
        for gid in held_ids:
            rec = d["persons"].get(gid)
            if rec is not None:
                rec["id"] = gid
                _crm_tombstone_contact(d, "persons", rec)
    scrubbed_keys |= privacy._erase_sweep(d, scrub_fn, linked_people=held_ids, apply=not dry,
                                  linked_orgs=linked_orgs, skip_people=held_ids)
    if not dry:
        _gone, threads = _crm_erase_links(d, held_ids, held_orgs)
        if threads:
            logger.info("crm import: %d mail thread(s) belonged to a contact erased on request", len(threads))
        known_dead = set(d.get("pd_deleted_persons") or [])
        for words, ids in held_words.values():
            privacy._erase_remember(d, words, ids, shared=alive)
        for pd, words in found.items():
            privacy._erase_remember(d, words, [pd], shared=alive)
            if pd not in known_dead:
                d.setdefault("pd_deleted_persons", []).append(pd)
                known_dead.add(pd)
    report["erased"]["scrubbed"] = len(scrubbed_keys)
    report["erased"]["removed"] = len(held_ids)

    after = {"deals": len(d["deals"]) + (report["deals"]["new"] if dry else 0),
             "activities": len(d["activities"]) + (report["activities"]["new"] if dry else 0)}
    if after["deals"] > CRM_DEALS_MAX or after["activities"] > CRM_ACTIVITIES_MAX:
        report["problems"].append(
            "This would put the CRM over its size guard. Nothing would be deleted, "
            "but the limits should be raised first.")
    report["totals"] = after
    if not dry:
        d["pd_imported_at"] = _crm_now()
    return report


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as core.NAME and sibling.NAME, never a copied name.
from gizmo import activity  # noqa: E402
from gizmo import gate  # noqa: E402
from gizmo import mail  # noqa: E402
from gizmo import team  # noqa: E402
import copilot as core  # noqa: E402
from gizmo import privacy  # noqa: E402
