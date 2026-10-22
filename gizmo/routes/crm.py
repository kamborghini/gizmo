"""The CRM's routes, gathered from add_routes (stage 4 of the 14 October audit)
where its first route stood. No request changes hands: their paths are
literal and no other route answers them (make move-proof checks).
"""
import logging
from starlette.requests import Request
import re
import asyncio
import pipedrive
from gizmo import store as jsonstore
from gizmo import shopify

from gizmo import backup
from gizmo import privacy
from gizmo import activity
from gizmo import crm as salesdesk
from gizmo import gate
from gizmo import mail
from gizmo import team
from gizmo import bodies

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")



class CrmActivityBody(bodies.Body):
    """What /api/crm/activity reads (gizmo/bodies.py): an activity's words,
    when it is due, what it is linked to, who has it, and whether it is done."""
    id: bodies.Id = None
    type: bodies.Text = None
    subject: bodies.Text = None
    deal_id: bodies.Id = None
    person_id: bodies.Id = None
    org_id: bodies.Id = None
    due_date: bodies.Text = None
    due_time: bodies.Text = None
    duration: bodies.Text = None
    note: bodies.Text = None
    priority: bodies.Text = None
    location: bodies.Text = None
    assignee: bodies.Text = None
    done: bodies.Flag = None



class CrmContactBody(bodies.Body):
    """What /api/crm/contact reads (gizmo/bodies.py): a person's or an
    organisation's details, their notes, a merge, a bulk delete, a search."""
    id: bodies.Id = None
    into: bodies.Id = None
    ids: bodies.Items = None
    kind: bodies.Text = None
    q: bodies.Text = None
    name: bodies.Text = None
    label: bodies.Text = None
    org_id: bodies.Id = None
    job_title: bodies.Text = None
    address: bodies.Text = None
    website: bodies.Text = None
    emails: bodies.Items = None
    phones: bodies.Items = None
    email_labels: bodies.Items = None
    phone_labels: bodies.Items = None
    contacts_full: bodies.Flag = None
    shopify_customer_id: bodies.Id = None
    custom: bodies.Fields = None
    text: bodies.Text = None
    note_id: bodies.Id = None



class CrmDealBody(bodies.Body):
    """What /api/crm/deal reads (gizmo/bodies.py): a deal's details, its stage, owner and value, why it was lost, and its notes."""
    id: bodies.Id = None
    title: bodies.Text = None
    person_id: bodies.Id = None
    org_id: bodies.Id = None
    stage_id: bodies.Id = None
    label: bodies.Text = None
    expected_close: bodies.Text = None
    source: bodies.Text = None
    owner: bodies.Id = None
    value: bodies.Number = None
    probability: bodies.Number = None
    custom: bodies.Fields = None
    reason: bodies.Text = None
    comment: bodies.Text = None
    text: bodies.Text = None
    note_id: bodies.Id = None



class CrmImportBody(bodies.Body):
    """What /api/crm/import reads (gizmo/bodies.py): whether to go ahead."""
    go: bodies.Flag = None



class CrmLeadBody(bodies.Body):
    """What /api/crm/lead reads (gizmo/bodies.py): a lead's details, its notes, and the stage it becomes a deal in."""
    id: bodies.Id = None
    person_id: bodies.Id = None
    org_id: bodies.Id = None
    title: bodies.Text = None
    label: bodies.Text = None
    source: bodies.Text = None
    value: bodies.Number = None
    text: bodies.Text = None
    stage_id: bodies.Id = None



class CrmStagesBody(bodies.Body):
    """What /api/crm/stages reads (gizmo/bodies.py): the pipeline's stages, its labels, the reasons a deal is lost, and the follow-up prompt."""
    stages: bodies.Records = None
    labels: bodies.Records = None
    lost_reasons: bodies.Items = None
    followup_popup: bodies.Flag = None



class CrmBoardBody(bodies.Body):
    """What /api/crm/board reads (gizmo/bodies.py): the board the page already holds."""
    rev: bodies.Text = None


def register(mcp, registry):
    """Add the CRM's routes to the app."""




    @mcp.custom_route("/api/crm/import", methods=["POST"])
    async def crm_import_route(request: Request):
        """Copy Pipedrive into gizmo's CRM. Dry run unless told otherwise.

        Read-only against Pipedrive in both modes: this only ever writes into
        gizmo's own store, and only when {"go": true} is sent."""
        err, body, who = await mail._mail_guard(request, model=CrmImportBody)
        if err:
            return err
        if team._team_role(who) != "master":
            return gate._json({"error": "Only the master account can import."}, 403)
        if not pipedrive.configured():
            return gate._json({"error": "No Pipedrive token is set on the server."}, 400)
        go = bool(body.get("go"))
        if go and not jsonstore._store_writable(salesdesk.CRM_PATH):
            return gate._json({"error": "The CRM store is not writable, so nothing was "
                                   "changed. Check Settings, Connections."}, 503)
        try:
            data = await pipedrive.export()
        except pipedrive.PipedriveError as e:
            return gate._json({"error": str(e)}, 400)
        except Exception:
            logger.exception("pipedrive export failed")
            return gate._json({"error": "Could not read the Pipedrive account."}, 502)
        missing = [k for k, v in (data.get("complete") or {}).items() if not v]
        if missing and go:
            return gate._json({"error": "Only part of the Pipedrive account could be read ("
                                   + ", ".join(missing) + "), so nothing was imported. "
                                   "Run the preview and try again."}, 502)
        if go:
            # Checked before the snapshot: a refused import must not deflate
            # the whole volume first, every time it is pressed.
            mail._load_mail()                    # its state decides whether erased people are known
            why = privacy._erase_import_blocker(salesdesk._load_crm())
            if why:
                return gate._json({"error": why}, 503)
            # The one irreversible moment gets a snapshot immediately before it.
            try:
                # OFF the event loop: this deflates the whole data volume, and
                # doing it inline stopped the process serving for as long as
                # it took - including POST /webhooks/orders, which Shopify
                # gives 5 seconds before it starts counting failures.
                await asyncio.to_thread(backup._weekly_snapshot, True)
            except Exception:
                logger.exception("pre-import snapshot failed")
        d = salesdesk._load_crm()
        if not go:
            # The preview works on a COPY. _crm_import_apply updates records
            # that already exist in place, and _load_crm hands out the cached
            # store itself, so a preview over a partial export blanked the
            # contact off every imported deal in memory and the next unrelated
            # CRM write put that on disk.
            import copy as _copy
            d = _copy.deepcopy(d)
        try:
            report = salesdesk._crm_import_apply(d, data, dry=not go)
        except Exception:
            # The apply writes into the cached store as it goes (a preview
            # works on a copy). One that raised partway left a half-made import
            # in memory, which every board served and the next CRM write put on
            # disk: forgotten, as an erasure that raises is (#23).
            logger.exception("pipedrive import failed partway")
            if go:
                jsonstore._forget_store(salesdesk.CRM_PATH)
            return gate._json({"error": "The import stopped partway, so nothing was saved and the CRM "
                                   "is as it was. Try again, or tell Cameron if it keeps happening."}, 500)
        if go:
            salesdesk._write_crm(d)
            activity._track(who, "crm", "imported from Pipedrive",
                   str(report["deals"]["new"]) + " new deals, "
                   + str(report["persons"]["new"]) + " new people")
        return gate._json({"ok": True, "dry_run": not go, "report": report,
                      "account": data.get("account"),
                      "not_migrated": data.get("not_migrated"),
                      "incomplete": missing})

    @mcp.custom_route("/api/crm/pipedrive", methods=["POST"])
    async def crm_pipedrive_route(request: Request):
        """Look at the Pipedrive account, read-only.

        This writes NOTHING, to either system. It exists to answer the
        questions that decide the shape of an import and that nobody can
        answer from outside the account: how many pipelines are really in
        use, which custom fields carry data, how much is archived, and who
        owns what."""
        err, _body, who = await mail._mail_guard(request)
        if err:
            return err
        if team._team_role(who) != "master":
            return gate._json({"error": "Only the master account can look at Pipedrive."}, 403)
        if not pipedrive.configured():
            return gate._json({"error": "No Pipedrive token is set on the server. Add one from an "
                                   "admin's Pipedrive account in the app's hosting settings, "
                                   "then try again.",
                          "configured": False}, 400)
        try:
            out = await pipedrive.survey()
        except pipedrive.PipedriveError as e:
            return gate._json({"error": str(e), "configured": True}, 400)
        except Exception:
            logger.exception("pipedrive survey failed")
            return gate._json({"error": "Could not read the Pipedrive account."}, 502)
        activity._track(who, "crm", "surveyed the Pipedrive account",
               str((out.get("counts") or {}).get("deals", 0)) + " deals")
        return gate._json({"configured": True, **out})

    @mcp.custom_route("/api/crm/board", methods=["POST"])
    async def crm_board_route(request: Request):
        err, body, _who = await salesdesk._crm_guard(request, model=CrmBoardBody)
        if err:
            return err
        try:
            raw, rev = salesdesk._crm_board()
            # The page sends the revision it holds; an unchanged board is not
            # sent again (about 400 KB at production size, every 90 seconds
            # per open tab). A page that sends none, one still open from
            # before this update, gets the whole board as it always did.
            if str((body or {}).get("rev") or "") == rev:
                return gate._json({"same": True, "rev": rev})
            return salesdesk._crm_answer(raw, rev)
        except Exception:
            logger.exception("CRM board failed")
            return gate._json({"error": "Couldn't load the CRM."}, 500)

    @mcp.custom_route("/api/crm/deal", methods=["POST"])
    async def crm_deal_route(request: Request):
        err, body, actor = await salesdesk._crm_guard(request, model=CrmDealBody)
        if err:
            return err
        op = str(body.get("op") or "")
        try:
            d = salesdesk._load_crm()
            if op == "add":
                title = str(body.get("title") or "").strip()[:200]
                person, org = str(body.get("person_id") or ""), str(body.get("org_id") or "")
                # Pipedrive's save rule: a deal needs a person or an organisation.
                if not title:
                    return gate._json({"error": "The deal needs a title."}, 400)
                if not (person and person in d["persons"]) and not (org and org in d["orgs"]):
                    return gate._json({"error": "Link a person or an organisation first: a deal "
                                           "belongs to someone."}, 400)
                if person and person in d["persons"] and not org:
                    org = d["persons"][person].get("org_id") or ""
                stage = str(body.get("stage_id") or "") or (d["stages"][0]["id"] if d["stages"] else "")
                deal = {"id": salesdesk._crm_id(d, "d"), "title": title,
                        "value": 0.0, "currency": "GBP", "stage_id": stage,
                        "person_id": person, "org_id": org,
                        "label": str(body.get("label") or "").strip()[:40],
                        "status": "open", "probability": None,
                        "expected_close": str(body.get("expected_close") or "").strip()[:10],
                        "source": str(body.get("source") or "Manual")[:40],
                        "owner": str(body.get("owner") or actor or "").strip()[:60],
                        "created_at": salesdesk._crm_now(), "updated_at": salesdesk._crm_now(),
                        "stage_entered_at": salesdesk._crm_now(), "touched_at": salesdesk._crm_now(),
                        "notes": [], "changelog": []}
                try:
                    deal["value"] = salesdesk._crm_value(body.get("value"))
                except (TypeError, ValueError):
                    pass
                salesdesk._crm_log(deal, "created", "", deal["title"])
                d["deals"][deal["id"]] = deal
                return salesdesk._crm_ok(d, {"id": deal["id"]}, action="added a deal",
                               detail=deal["title"][:60], who=actor)

            deal = d["deals"].get(str(body.get("id") or ""))
            if not deal:
                return gate._json({"error": "That deal no longer exists."}, 404)
            if op == "detail":
                # A read: the notes and changelog the board payload leaves out.
                # No write, no ledger line. The email history rides along ONLY
                # for accounts that can open the Inbox: a CRM-only login must
                # not read correspondence through the side door of a deal.
                out = {"ok": True, "notes": deal.get("notes") or [],
                       "changelog": deal.get("changelog") or []}
                tabs = team._user_tabs(actor)
                if tabs is None or "mail" in tabs:
                    out["threads"] = salesdesk._crm_deal_threads(d, deal)
                    out["mail_days"] = mail.MAIL_TRACK_DAYS
                return gate._json(out)
            if op == "update":
                salesdesk._crm_deal_fields(body, d, deal)
                salesdesk._crm_touch(deal)
            elif op == "move":
                stage = str(body.get("stage_id") or "")
                if stage not in {s["id"] for s in d["stages"]}:
                    return gate._json({"error": "Unknown stage."}, 400)
                names = {s["id"]: s["name"] for s in d["stages"]}
                salesdesk._crm_log(deal, "stage", names.get(deal.get("stage_id")), names.get(stage))
                deal["stage_id"] = stage
                deal["stage_entered_at"] = salesdesk._crm_now()
                salesdesk._crm_touch(deal)
            elif op == "won":
                deal["status"], deal["won_at"] = "won", salesdesk._crm_now()
                salesdesk._crm_log(deal, "status", "open", "won")
                salesdesk._crm_touch(deal)
            elif op == "lost":
                deal["status"], deal["lost_at"] = "lost", salesdesk._crm_now()
                deal["lost_reason"] = str(body.get("reason") or "").strip()[:100]
                deal["lost_comment"] = str(body.get("comment") or "").strip()[:500]
                salesdesk._crm_log(deal, "status", "open", "lost")
                salesdesk._crm_touch(deal)
            elif op == "reopen":
                # Back to the exact stage it left from: the stage never changed.
                # Unless that stage was deleted meanwhile, in which case the
                # first stage catches it, or the deal would render in no column.
                if deal.get("stage_id") not in {s["id"] for s in d["stages"]} and d["stages"]:
                    salesdesk._crm_log(deal, "stage", deal.get("stage_id"), d["stages"][0]["name"])
                    deal["stage_id"] = d["stages"][0]["id"]
                    deal["stage_entered_at"] = salesdesk._crm_now()
                old = deal.get("status")
                deal["status"] = "open"
                deal.pop("won_at", None); deal.pop("lost_at", None)
                deal.pop("lost_reason", None); deal.pop("lost_comment", None)
                salesdesk._crm_log(deal, "status", old, "open")
                salesdesk._crm_touch(deal)
            elif op == "archive":
                # Pipedrive's third door: not won, not lost, just off the desk.
                # This account had used it 257 times before it had a button.
                # An archive is a gizmo edit like any other — without the flag
                # (and no touch, since archiving must not reset rot) the very
                # next import would quietly put the deal back on the board.
                deal["archived"], deal["archived_at"] = True, salesdesk._crm_now()
                deal["updated_at"], deal["edited_here"] = salesdesk._crm_now(), True
                salesdesk._crm_log(deal, "archive", "", "archived")
            elif op == "unarchive":
                deal.pop("archived", None); deal.pop("archived_at", None)
                salesdesk._crm_log(deal, "archive", "archived", "")
                salesdesk._crm_touch(deal)
            elif op == "delete":
                deal["deleted"], deal["deleted_at"] = True, salesdesk._crm_now()
                deal["edited_here"] = True
            elif op == "restore":
                deal.pop("deleted", None); deal.pop("deleted_at", None)
                # Its stage can have gone while it sat in the bin; an open
                # deal in no column exists nowhere. First column catches it.
                if deal.get("stage_id") not in {s["id"] for s in d["stages"]} and d["stages"]:
                    salesdesk._crm_log(deal, "stage", deal.get("stage_id"), d["stages"][0]["name"])
                    deal["stage_id"] = d["stages"][0]["id"]
                    deal["stage_entered_at"] = salesdesk._crm_now()
            elif op == "note_add":
                text = str(body.get("text") or "").strip()[:salesdesk.CRM_NOTE_CAP]
                if not text:
                    return gate._json({"error": "The note is empty."}, 400)
                deal.setdefault("notes", []).append(
                    {"id": salesdesk._crm_id(d, "n"), "text": text, "at": salesdesk._crm_now(), "pinned": False})
                deal["notes"] = deal["notes"][-500:]
                salesdesk._crm_touch(deal)
            elif op == "note_pin":
                for n in deal.get("notes", []):
                    if n["id"] == str(body.get("note_id") or ""):
                        n["pinned"] = not n.get("pinned")
                salesdesk._crm_touch(deal)
            elif op == "note_del":
                nid = str(body.get("note_id") or "")
                for n in deal.get("notes", []):
                    if n["id"] == nid and n.get("pd_id"):
                        deal.setdefault("pd_deleted_notes", []).append(str(n["pd_id"]))
                deal["notes"] = [n for n in deal.get("notes", []) if n["id"] != nid]
                deal["edited_here"] = True
            else:
                return gate._json({"error": "Unknown operation."}, 400)
            return salesdesk._crm_ok(d, action=("deal " + op).replace("_", " "), detail=(deal.get("title") or "")[:60], who=actor)
        except RuntimeError:
            return gate._json({"error": "The CRM could not be saved. The data volume may be "
                                   "unwritable; check Settings, Connections."}, 500)
        except Exception:
            logger.exception("CRM deal op failed")
            jsonstore._forget_store(salesdesk.CRM_PATH)   # a half-made change must not be served
            return gate._json({"error": "That change could not be made. Check the server logs."}, 500)

    @mcp.custom_route("/api/crm/activity", methods=["POST"])
    async def crm_activity_route(request: Request):
        err, body, actor = await salesdesk._crm_guard(request, model=CrmActivityBody)
        if err:
            return err
        op = str(body.get("op") or "")
        try:
            d = salesdesk._load_crm()
            followup = None
            if op == "add":
                atype = str(body.get("type") or "task")
                if atype not in salesdesk._CRM_ACTIVITY_TYPES:
                    atype = "task"
                deal_id = str(body.get("deal_id") or "")
                person, org = str(body.get("person_id") or ""), str(body.get("org_id") or "")
                # Pipedrive's auto-linking: a deal brings its person and org;
                # a person brings their org; an org alone brings nothing.
                if deal_id and deal_id in d["deals"]:
                    person = person or d["deals"][deal_id].get("person_id") or ""
                    org = org or d["deals"][deal_id].get("org_id") or ""
                elif person and person in d["persons"]:
                    org = org or d["persons"][person].get("org_id") or ""
                act = {"id": salesdesk._crm_id(d, "a"), "type": atype,
                       # The dialog pre-fills the subject with the type name, so
                       # a valid activity is two clicks.
                       "subject": (str(body.get("subject") or "").strip()[:200]
                                   or atype.capitalize()),
                       "deal_id": deal_id, "person_id": person, "org_id": org,
                       "due_date": (str(body.get("due_date") or "").strip()[:10]
                                    if re.fullmatch(r"\d{4}-\d{2}-\d{2}",
                                                    str(body.get("due_date") or "").strip())
                                    else salesdesk._crm_today().isoformat()),
                       "due_time": str(body.get("due_time") or "").strip()[:5],
                       "note": str(body.get("note") or "").strip()[:salesdesk.CRM_NOTE_CAP],
                       "priority": (str(body.get("priority") or "") if str(body.get("priority") or "")
                                    in ("high", "medium", "low") else ""),
                       "location": str(body.get("location") or "").strip()[:200],
                       "assignee": str(body.get("assignee") or actor or "").strip()[:60],
                       "done": bool(body.get("done")),
                       "done_at": salesdesk._crm_now() if body.get("done") else "",
                       "created_at": salesdesk._crm_now(), "updated_at": salesdesk._crm_now()}
                d["activities"][act["id"]] = act
                if deal_id and deal_id in d["deals"]:
                    salesdesk._crm_touch(d["deals"][deal_id])
                return salesdesk._crm_ok(d, {"id": act["id"]}, action="added an activity", detail=(act.get("note") or act.get("type") or "")[:60], who=actor)

            act = d["activities"].get(str(body.get("id") or ""))
            if not act:
                return gate._json({"error": "That activity no longer exists."}, 404)
            if op == "detail":
                # The full note, which the board payload deliberately leaves
                # out. A read: no write, no ledger line.
                return gate._json({"ok": True, "note": act.get("note") or ""})
            if op == "update":
                for f, cap in (("subject", 200), ("due_date", 10), ("due_time", 5),
                               ("note", salesdesk.CRM_NOTE_CAP), ("location", 200),
                               ("assignee", 60), ("duration", 8)):
                    if f in body:
                        act[f] = str(body.get(f) or "").strip()[:cap]
                if "type" in body and str(body["type"]) in salesdesk._CRM_ACTIVITY_TYPES:
                    act["type"] = str(body["type"])
                if "priority" in body and str(body.get("priority") or "") in ("high", "medium", "low", ""):
                    act["priority"] = str(body.get("priority") or "")
                for f in ("deal_id", "person_id", "org_id"):
                    if f in body:
                        act[f] = str(body.get(f) or "")
                act["updated_at"], act["edited_here"] = salesdesk._crm_now(), True
                if act.get("deal_id") and act["deal_id"] in d["deals"]:
                    salesdesk._crm_touch(d["deals"][act["deal_id"]])   # a reschedule is a touch
            elif op == "done":
                # The due date is never rewritten: done three days late still
                # shows its original date in History. done_at is its own stamp.
                act["done"], act["done_at"] = True, salesdesk._crm_now()
                act["updated_at"], act["edited_here"] = salesdesk._crm_now(), True
                deal_id = act.get("deal_id") or ""
                if deal_id and deal_id in d["deals"]:
                    salesdesk._crm_touch(d["deals"][deal_id])
                    still_open = any(a.get("deal_id") == deal_id and not a.get("done")
                                     for a in d["activities"].values())
                    # The follow-up prompt, the heart of activity-based selling:
                    # fires only when the deal's LAST open activity was just
                    # completed, and only nags, never blocks.
                    if (not still_open and d["deals"][deal_id].get("status") == "open"
                            and d["settings"].get("followup_popup", True)):
                        followup = deal_id
            elif op == "undone":
                act["done"], act["done_at"] = False, ""
                act["updated_at"], act["edited_here"] = salesdesk._crm_now(), True
                if act.get("deal_id") and act["deal_id"] in d["deals"]:
                    salesdesk._crm_touch(d["deals"][act["deal_id"]])
            elif op == "delete":
                if act.get("deal_id") and act["deal_id"] in d["deals"]:
                    salesdesk._crm_touch(d["deals"][act["deal_id"]])
                # An imported activity leaves a tombstone, or the next import
                # would put it straight back.
                if act.get("pd_id"):
                    d.setdefault("pd_deleted_activities", []).append(str(act["pd_id"]))
                    d["pd_deleted_activities"] = d["pd_deleted_activities"][-2000:]
                d["activities"].pop(act["id"], None)
            else:
                return gate._json({"error": "Unknown operation."}, 400)
            return salesdesk._crm_ok(d, {"followup_deal_id": followup} if followup else None, action=("activity " + op).replace("_", " "), who=actor)
        except RuntimeError:
            return gate._json({"error": "The CRM could not be saved. The data volume may be "
                                   "unwritable; check Settings, Connections."}, 500)
        except Exception:
            logger.exception("CRM activity op failed")
            jsonstore._forget_store(salesdesk.CRM_PATH)   # a half-made change must not be served
            return gate._json({"error": "That change could not be made. Check the server logs."}, 500)

    @mcp.custom_route("/api/crm/contact", methods=["POST"])
    async def crm_contact_route(request: Request):
        err, body, actor = await salesdesk._crm_guard(request, model=CrmContactBody)
        if err:
            return err
        op = str(body.get("op") or "")
        try:
            if op == "shopify_search":
                # This returns Shopify customer names, emails and lifetime
                # spend. It is a CUSTOMERS read wearing a CRM route, so an
                # account denied that tab must not reach it from here.
                tabs = team._user_tabs(actor)
                if tabs is not None and "customers" not in tabs:
                    return gate._json({"error": "Searching Shopify customers needs the Customers "
                                           "tab, which is switched off for your account."}, 403)
                q = str(body.get("q") or "").strip()[:80]
                if not q:
                    return gate._json({"matches": []})
                res = await shopify._tool_json(registry, "shopify_search_customers", {"query": q})
                out = []
                for c in (res.get("customers") or [])[:8]:
                    nm = " ".join(x for x in [c.get("first_name"), c.get("last_name")] if x).strip()
                    addr = (c.get("default_address") or {})
                    out.append({"id": c.get("id"), "name": nm or (c.get("email") or "Customer"),
                                "email": c.get("email") or "", "company": addr.get("company") or "",
                                "orders": c.get("orders_count"), "spent": c.get("total_spent")})
                return gate._json({"matches": out})

            d = salesdesk._load_crm()
            if op == "person_add":
                name = str(body.get("name") or "").strip()[:120]
                if not name:
                    return gate._json({"error": "The person needs a name."}, 400)
                p = {"id": salesdesk._crm_id(d, "p"), "name": name,
                     "org_id": str(body.get("org_id") or ""),
                     "emails": [str(e).strip()[:120] for e in (body.get("emails") or []) if str(e).strip()][:8],
                     "phones": [str(x).strip()[:40] for x in (body.get("phones") or []) if str(x).strip()][:8],
                     "label": str(body.get("label") or "").strip()[:40],
                     "job_title": str(body.get("job_title") or "").strip()[:120],
                     "shopify_customer_id": body.get("shopify_customer_id") or None,
                     "created_at": salesdesk._crm_now(), "updated_at": salesdesk._crm_now(), "notes": []}
                d["persons"][p["id"]] = p
                return salesdesk._crm_ok(d, {"id": p["id"]}, action="added a person", detail=(p.get("name") or "")[:60], who=actor)
            if op == "org_add":
                name = str(body.get("name") or "").strip()[:120]
                if not name:
                    return gate._json({"error": "The organisation needs a name."}, 400)
                o = {"id": salesdesk._crm_id(d, "o"), "name": name,
                     "address": str(body.get("address") or "").strip()[:300],
                     "website": str(body.get("website") or "").strip()[:200],
                     "label": str(body.get("label") or "").strip()[:40],
                     "created_at": salesdesk._crm_now(), "updated_at": salesdesk._crm_now(), "notes": []}
                d["orgs"][o["id"]] = o
                return salesdesk._crm_ok(d, {"id": o["id"]}, action="added an organisation", detail=(o.get("name") or "")[:60], who=actor)

            if op in ("person_update", "person_delete", "link_shopify"):
                p = d["persons"].get(str(body.get("id") or ""))
                if not p:
                    return gate._json({"error": "That person no longer exists."}, 404)
                if op == "person_update":
                    for f, cap in (("name", 120), ("label", 40), ("org_id", 40),
                                   ("job_title", 120)):
                        if f in body:
                            p[f] = str(body.get(f) or "").strip()[:cap]
                    if isinstance(body.get("custom"), dict):
                        cust = dict(p.get("custom") or {})
                        for ck, cv in list(body["custom"].items())[:30]:
                            # None-safe, not falsy-safe: 0 is a value, not a delete.
                            ck = str(ck).strip()[:60]
                            cv = ("" if cv is None else str(cv)).strip()[:500]
                            if ck:
                                (cust.__setitem__(ck, cv) if cv else cust.pop(ck, None))
                        p["custom"] = cust
                    # A form that shows ONE email must not be able to delete the
                    # other three. It sends what it displays, so treat that as a
                    # change to the FIRST entry and keep the rest. A form that
                    # shows them ALL says contacts_full, and its list is the
                    # whole truth — including a deliberate prune to one.
                    for f in ("emails", "phones"):
                        if f in body and isinstance(body[f], list):
                            sent = [str(x).strip()[:200] for x in body[f] if str(x).strip()]
                            kept = [str(x).strip()[:200] for x in (p.get(f) or []) if str(x).strip()]
                            if (not body.get("contacts_full")
                                    and len(sent) <= 1 and len(kept) > 1):
                                rest = [x for x in kept[1:] if x.lower() != (sent[0].lower() if sent else "")]
                                p[f] = (sent + rest)[:8]
                            else:
                                p[f] = sent[:8]
                        lf = f[:-1] + "_labels"
                        if lf in body and isinstance(body[lf], list):
                            p[lf] = [str(x).strip()[:20] for x in body[lf]][:8]
                    p["updated_at"], p["edited_here"] = salesdesk._crm_now(), True
                elif op == "link_shopify":
                    p["shopify_customer_id"] = body.get("shopify_customer_id") or None
                    p["updated_at"], p["edited_here"] = salesdesk._crm_now(), True
                else:
                    n = salesdesk._crm_contact_open_ref(d, "persons", p["id"])
                    if n:
                        return gate._json({"error": "This person is on " + str(n)
                                               + " open deal(s) or lead(s). Close or relink those first."}, 400)
                    salesdesk._crm_tombstone_contact(d, "persons", p)
                return salesdesk._crm_ok(d, action=("contact " + op).replace("_", " "), who=actor)
            if op in ("org_update", "org_delete"):
                o = d["orgs"].get(str(body.get("id") or ""))
                if not o:
                    return gate._json({"error": "That organisation no longer exists."}, 404)
                if op == "org_update":
                    for f, cap in (("name", 120), ("label", 40), ("address", 300),
                                   ("website", 200)):
                        if f in body:
                            o[f] = str(body.get(f) or "").strip()[:cap]
                    if isinstance(body.get("custom"), dict):
                        cust = dict(o.get("custom") or {})
                        for ck, cv in list(body["custom"].items())[:30]:
                            ck = str(ck).strip()[:60]
                            cv = ("" if cv is None else str(cv)).strip()[:500]
                            if ck:
                                (cust.__setitem__(ck, cv) if cv else cust.pop(ck, None))
                        o["custom"] = cust
                    o["updated_at"], o["edited_here"] = salesdesk._crm_now(), True
                else:
                    n = salesdesk._crm_contact_open_ref(d, "orgs", o["id"])
                    if n:
                        return gate._json({"error": "This organisation is on " + str(n)
                                               + " open deal(s) or lead(s). Close or relink those first."}, 400)
                    salesdesk._crm_tombstone_contact(d, "orgs", o)
                return salesdesk._crm_ok(d, action=("contact " + op).replace("_", " "), who=actor)

            if op == "detail":
                # A read: the notes the board payload leaves out.
                kind = "orgs" if str(body.get("kind") or "") == "org" else "persons"
                rec = d[kind].get(str(body.get("id") or ""))
                if not rec:
                    return gate._json({"error": "That contact no longer exists."}, 404)
                return gate._json({"ok": True, "notes": rec.get("notes") or []})

            if op in ("note_add", "note_pin", "note_del"):
                kind = "orgs" if str(body.get("kind") or "") == "org" else "persons"
                rec = d[kind].get(str(body.get("id") or ""))
                if not rec:
                    return gate._json({"error": "That contact no longer exists."}, 404)
                if op == "note_add":
                    text = str(body.get("text") or "").strip()[:salesdesk.CRM_NOTE_CAP]
                    if not text:
                        return gate._json({"error": "The note is empty."}, 400)
                    rec.setdefault("notes", []).append(
                        {"id": salesdesk._crm_id(d, "n"), "text": text, "at": salesdesk._crm_now(), "pinned": False})
                    rec["notes"] = rec["notes"][-500:]
                elif op == "note_pin":
                    for n in rec.get("notes", []):
                        if n["id"] == str(body.get("note_id") or ""):
                            n["pinned"] = not n.get("pinned")
                else:
                    nid = str(body.get("note_id") or "")
                    for n in rec.get("notes", []):
                        if n["id"] == nid and n.get("pd_id"):
                            rec.setdefault("pd_deleted_notes", []).append(str(n["pd_id"]))
                    rec["notes"] = [n for n in rec.get("notes", []) if n["id"] != nid]
                rec["updated_at"], rec["edited_here"] = salesdesk._crm_now(), True
                return salesdesk._crm_ok(d, action=("contact " + op).replace("_", " "), who=actor)

            if op == "bulk_delete":
                # Clearing test/sample contacts in one pass. Master-only and
                # guarded per record: anyone on an OPEN deal is skipped and
                # NAMED, never silently removed from under live pipeline.
                if team._team_role(actor) != "master":
                    return gate._json({"error": "Only the master account can bulk-delete contacts."}, 403)
                kind = "orgs" if str(body.get("kind") or "") == "org" else "persons"
                ref = "org_id" if kind == "orgs" else "person_id"
                ids = [str(i) for i in (body.get("ids") or []) if str(i).strip()][:500]
                if not ids:
                    return gate._json({"error": "Nothing selected."}, 400)
                deleted, skipped = [], []
                for cid in ids:
                    rec = d[kind].get(cid)
                    if not rec:
                        continue
                    if salesdesk._crm_contact_open_ref(d, kind, cid):
                        skipped.append(rec.get("name") or cid)
                        continue
                    salesdesk._crm_tombstone_contact(d, kind, rec)
                    deleted.append(cid)
                if not deleted and skipped:
                    return gate._json({"error": "None deleted: all "
                                           + str(len(skipped)) + " are on open deals."}, 400)
                return salesdesk._crm_ok(d, {"deleted": len(deleted), "skipped": skipped},
                               action="bulk-deleted contacts",
                               detail=str(len(deleted)) + " removed", who=actor)

            if op == "shopify_link_sweep":
                # Bulk fill of every unlinked contact. Master-only, like the
                # import: it writes 2,800 records in one press.
                if team._team_role(actor) != "master":
                    return gate._json({"error": "Only the master account can run the link sweep."}, 403)
                rep = await salesdesk._crm_shopify_link_sweep(registry)
                d = salesdesk._load_crm()
                d["shopify_link_at"] = salesdesk._crm_now()
                salesdesk._write_crm(d)
                if rep["linked"]:
                    activity._track(actor, "crm", "linked contacts to Shopify",
                           str(rep["linked"]) + " matched by email")
                raw, rev = salesdesk._crm_board()
                return salesdesk._crm_answer(raw, rev, {"ok": True, "report": rep})

            if op in ("person_merge", "org_merge"):
                # 1,951 imported people guarantee duplicates, and deleting the
                # spare is blocked while deals point at it — merge is the only
                # honest exit. The WINNER keeps every field it has; the loser
                # fills the gaps, hands over its notes, and every deal, lead
                # and activity that pointed at it is re-pointed. Nothing ends
                # up dangling, because the loser is only removed after.
                kind = "persons" if op == "person_merge" else "orgs"
                ref = "person_id" if op == "person_merge" else "org_id"
                loser = d[kind].get(str(body.get("id") or ""))
                winner = d[kind].get(str(body.get("into") or ""))
                if not loser or not winner:
                    return gate._json({"error": "Both contacts must still exist."}, 404)
                if loser["id"] == winner["id"]:
                    return gate._json({"error": "Pick two different contacts to merge."}, 400)
                for coll in ("deals", "activities", "leads"):
                    for v in d[coll].values():
                        if v.get(ref) == loser["id"]:
                            v[ref] = winner["id"]
                if kind == "orgs":
                    for v in d["persons"].values():
                        if v.get("org_id") == loser["id"]:
                            v["org_id"] = winner["id"]
                for f in ("emails", "phones"):
                    have = [x.lower() for x in (winner.get(f) or [])]
                    keep_v = list(winner.get(f) or [])
                    keep_l = list(winner.get(f[:-1] + "_labels") or [])[:len(keep_v)]
                    keep_l += [""] * (len(keep_v) - len(keep_l))
                    lose_l = list(loser.get(f[:-1] + "_labels") or [])
                    for i, x in enumerate(loser.get(f) or []):
                        if x.lower() not in have and len(keep_v) < 8:
                            keep_v.append(x)
                            keep_l.append(lose_l[i] if i < len(lose_l) else "")
                    winner[f] = keep_v
                    winner[f[:-1] + "_labels"] = keep_l
                for f in ("job_title", "label", "org_id", "address", "website",
                          "shopify_customer_id", "pd_id"):
                    if not winner.get(f) and loser.get(f):
                        winner[f] = loser[f]
                # The winner absorbs the loser's Pipedrive IDENTITY too, and
                # tombstones ride along: without this the next import would
                # recreate the duplicate and re-point its deals back at it.
                merged = list(winner.get("pd_merged_ids") or [])
                for m in [loser.get("pd_id")] + list(loser.get("pd_merged_ids") or []):
                    if m and str(m) != str(winner.get("pd_id") or "") and str(m) not in merged:
                        merged.append(str(m))
                if merged:
                    winner["pd_merged_ids"] = merged
                dead = list(winner.get("pd_deleted_notes") or []) + list(loser.get("pd_deleted_notes") or [])
                if dead:
                    winner["pd_deleted_notes"] = dead
                cust = dict(loser.get("custom") or {})
                cust.update(winner.get("custom") or {})
                if cust:
                    winner["custom"] = cust
                # Chronological, so a cap trims the OLDEST of both histories,
                # never the winner's whole past just for being concatenated first.
                winner.setdefault("notes", []).extend(loser.get("notes") or [])
                winner["notes"] = sorted(winner["notes"], key=lambda n: str(n.get("at") or ""))[-500:]
                winner["updated_at"], winner["edited_here"] = salesdesk._crm_now(), True
                d[kind].pop(loser["id"], None)
                return salesdesk._crm_ok(d, action="merged two contacts",
                               detail=(loser.get("name") or "") + " into " + (winner.get("name") or ""),
                               who=actor)

            return gate._json({"error": "Unknown operation."}, 400)
        except RuntimeError:
            return gate._json({"error": "The CRM could not be saved. The data volume may be "
                                   "unwritable; check Settings, Connections."}, 500)
        except Exception:
            logger.exception("CRM contact op failed")
            jsonstore._forget_store(salesdesk.CRM_PATH)   # a half-made change must not be served
            return gate._json({"error": "That change could not be made. Check the server logs."}, 500)

    @mcp.custom_route("/api/crm/lead", methods=["POST"])
    async def crm_lead_route(request: Request):
        err, body, actor = await salesdesk._crm_guard(request, model=CrmLeadBody)
        if err:
            return err
        op = str(body.get("op") or "")
        try:
            d = salesdesk._load_crm()
            if op == "add":
                person, org = str(body.get("person_id") or ""), str(body.get("org_id") or "")
                if not (person and person in d["persons"]) and not (org and org in d["orgs"]):
                    return gate._json({"error": "Link a person or an organisation first: a lead "
                                           "belongs to someone."}, 400)
                who = (d["persons"].get(person, {}).get("name")
                       or d["orgs"].get(org, {}).get("name") or "New")
                lead = {"id": salesdesk._crm_id(d, "l"),
                        "title": str(body.get("title") or "").strip()[:200] or (who + " lead"),
                        "value": 0.0, "label": str(body.get("label") or "").strip()[:40],
                        "person_id": person, "org_id": org,
                        "source": str(body.get("source") or "Manual")[:40],
                        "archived": False, "seen": False,
                        "created_at": salesdesk._crm_now(), "updated_at": salesdesk._crm_now(), "notes": []}
                try:
                    lead["value"] = salesdesk._crm_value(body.get("value"))
                except (TypeError, ValueError):
                    pass
                d["leads"][lead["id"]] = lead
                return salesdesk._crm_ok(d, {"id": lead["id"]}, action="added a lead", detail=(lead.get("title") or "")[:60], who=actor)

            lead = d["leads"].get(str(body.get("id") or ""))
            if not lead:
                return gate._json({"error": "That lead no longer exists."}, 404)
            if op == "seen":
                lead["seen"] = True
            elif op == "update":
                if lead.get("archived"):
                    return gate._json({"error": "Unarchive the lead before editing it."}, 400)
                for f, cap in (("title", 200), ("label", 40)):
                    if f in body:
                        lead[f] = str(body.get(f) or "").strip()[:cap]
                if "value" in body:
                    try:
                        lead["value"] = salesdesk._crm_value(body.get("value"))
                    except (TypeError, ValueError):
                        pass
                lead["updated_at"] = salesdesk._crm_now()
            elif op == "note_add":
                text = str(body.get("text") or "").strip()[:salesdesk.CRM_NOTE_CAP]
                if not text:
                    return gate._json({"error": "The note is empty."}, 400)
                lead.setdefault("notes", []).append(
                    {"id": salesdesk._crm_id(d, "n"), "text": text, "at": salesdesk._crm_now(), "pinned": False})
            elif op == "archive":
                lead["archived"] = True
            elif op == "unarchive":
                lead["archived"] = False
            elif op == "delete":
                d["leads"].pop(lead["id"], None)
            elif op == "convert":
                # Everything carries over and the lead leaves the inbox: no
                # shadow record stays behind.
                if lead.get("archived"):
                    return gate._json({"error": "Unarchive the lead before converting it."}, 400)
                stage = str(body.get("stage_id") or "") or (d["stages"][0]["id"] if d["stages"] else "")
                deal = {"id": salesdesk._crm_id(d, "d"), "title": lead["title"],
                        "value": lead.get("value") or 0.0, "currency": "GBP",
                        "stage_id": stage, "person_id": lead.get("person_id") or "",
                        "org_id": lead.get("org_id") or "",
                        "label": lead.get("label") or "", "status": "open",
                        "probability": None, "expected_close": "",
                        "source": lead.get("source") or "Manual",
                        "created_at": salesdesk._crm_now(), "updated_at": salesdesk._crm_now(),
                        "stage_entered_at": salesdesk._crm_now(), "touched_at": salesdesk._crm_now(),
                        "notes": lead.get("notes") or [], "changelog": []}
                salesdesk._crm_log(deal, "created", "", "converted from lead")
                d["deals"][deal["id"]] = deal
                d["leads"].pop(lead["id"], None)
                return salesdesk._crm_ok(d, {"id": deal["id"]}, action="converted a lead to a deal", detail=deal["title"][:60], who=actor)
            else:
                return gate._json({"error": "Unknown operation."}, 400)
            return salesdesk._crm_ok(d, action=("" if op == "seen" else ("lead " + op).replace("_", " ")), who=actor)
        except RuntimeError:
            return gate._json({"error": "The CRM could not be saved. The data volume may be "
                                   "unwritable; check Settings, Connections."}, 500)
        except Exception:
            logger.exception("CRM lead op failed")
            jsonstore._forget_store(salesdesk.CRM_PATH)   # a half-made change must not be served
            return gate._json({"error": "That change could not be made. Check the server logs."}, 500)

    @mcp.custom_route("/api/crm/stages", methods=["POST"])
    async def crm_stages_route(request: Request):
        err, body, actor = await salesdesk._crm_guard(request, model=CrmStagesBody)
        if err:
            return err
        # The shared pipeline, the label vocabulary and the lost reasons are
        # the desk's SETTINGS: one member renaming a stage or dropping a label
        # changes the board under everyone. Every sibling that rewrites this
        # store the same way (import, survey, bulk delete, link sweep) is
        # already role-gated; this one was reachable by anyone with the tab.
        if team._team_level(actor) < team.ROLE_LEVELS["admin"]:
            return gate._json({"error": "Only an admin can change the pipeline, its labels "
                                   "or the lost reasons."}, 403)
        try:
            d = salesdesk._load_crm()
            # The route is the CRM's settings desk: stages, labels, lost
            # reasons and the follow-up nag all save here, each key on its own.
            if "labels" in body and "stages" not in body:
                raw = body.get("labels")
                if not isinstance(raw, list) or not raw or len(raw) > 20:
                    return gate._json({"error": "Between 1 and 20 labels."}, 400)
                names, colors = [], {}
                for l in raw:
                    if not isinstance(l, dict) or not str(l.get("name") or "").strip():
                        return gate._json({"error": "Every label needs a name."}, 400)
                    nm = str(l["name"]).strip()[:40]
                    if nm in names:
                        continue
                    names.append(nm)
                    col = str(l.get("color") or "").strip()
                    colors[nm] = col if col in salesdesk._CRM_COLOR_NAMES else "gray"
                # The colour map also paints PERSON and ORG labels, which this
                # editor does not manage: merge, never replace, or saving the
                # deal labels greys out every imported contact chip. Only a
                # deal label actually deleted here leaves the map.
                merged_colors = dict(d.get("label_colors") or {})
                for gone in set(d.get("labels") or []) - set(names):
                    merged_colors.pop(gone, None)
                merged_colors.update(colors)
                d["labels"], d["label_colors"] = names, merged_colors
                return salesdesk._crm_ok(d, action="edited the deal labels", who=actor)
            if "lost_reasons" in body and "stages" not in body:
                raw = body.get("lost_reasons")
                if not isinstance(raw, list) or not raw or len(raw) > 40:
                    return gate._json({"error": "Between 1 and 40 lost reasons."}, 400)
                seen = []
                for r in raw:
                    nm = str(r or "").strip()[:60]
                    if nm and nm not in seen:
                        seen.append(nm)
                if not seen:
                    return gate._json({"error": "Between 1 and 40 lost reasons."}, 400)
                d["lost_reasons"] = seen
                return salesdesk._crm_ok(d, action="edited the lost reasons", who=actor)
            if "followup_popup" in body and "stages" not in body:
                d.setdefault("settings", {})["followup_popup"] = bool(body.get("followup_popup"))
                return salesdesk._crm_ok(d, action="changed the follow-up prompt", who=actor)

            raw = body.get("stages")
            if not isinstance(raw, list) or not raw or len(raw) > 12:
                return gate._json({"error": "A pipeline needs between 1 and 12 stages."}, 400)
            old_by_id = {s["id"]: s for s in (d.get("stages") or [])}
            new = []
            for s in raw:
                if not isinstance(s, dict) or not str(s.get("name") or "").strip():
                    return gate._json({"error": "Every stage needs a name."}, 400)
                sid = str(s.get("id") or "").strip() or salesdesk._crm_id(d, "s")
                try:
                    prob = max(0, min(100, int(s.get("probability", 100))))
                    rot = max(0, min(365, int(s.get("rot_days", 0) or 0)))
                except (TypeError, ValueError):
                    prob, rot = 100, 0
                # The editor shows one rot number; the switch follows it. The
                # imported bookkeeping (pd_id, the stored day count behind a
                # switched-off timer) rides along untouched — stripping it made
                # the next Pipedrive import duplicate every edited stage.
                prev = old_by_id.get(sid) or {}
                row = {"id": sid, "name": str(s["name"]).strip()[:60],
                       "probability": prob, "rot_days": rot,
                       "rot_on": rot > 0,
                       "rot_days_stored": rot if rot > 0 else int(prev.get("rot_days_stored") or 0)}
                if prev.get("pd_id"):
                    row["pd_id"] = prev["pd_id"]
                # An imported stage CHANGED at the desk is gizmo's now, and the
                # import must leave it alone - the same promise deals, people
                # and activities already get.
                changed = any(prev.get(k) != row[k] for k in
                              ("name", "probability", "rot_days", "rot_on"))
                if prev.get("edited_here") or (prev and changed):
                    row["edited_here"] = True
                new.append(row)
            # Pipedrive deletes a stage's deals after a warning. Refusing and
            # asking to move them first loses nothing and cannot surprise:
            # these are real deals, not sample data.
            kept = {s["id"] for s in new}
            orphans = [v for v in d["deals"].values()
                       if not v.get("deleted") and v.get("status") == "open"
                       and v.get("stage_id") not in kept]
            if orphans:
                return gate._json({"error": "That would remove a stage holding "
                                       + str(len(orphans)) + " open deal(s). Move them to "
                                       "another stage first."}, 400)
            d["stages"] = new
            return salesdesk._crm_ok(d, action="edited the pipeline stages", who=actor)
        except RuntimeError:
            return gate._json({"error": "The CRM could not be saved. The data volume may be "
                                   "unwritable; check Settings, Connections."}, 500)
        except Exception:
            logger.exception("CRM stages op failed")
            jsonstore._forget_store(salesdesk.CRM_PATH)   # a half-made change must not be served
            return gate._json({"error": "That change could not be made. Check the server logs."}, 500)
