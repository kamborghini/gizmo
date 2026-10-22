# ---- CRM --------------------------------------------------------------------

def reset_crm():
    try:
        os.remove(SCRATCH + "/crm.json")
    except FileNotFoundError:
        pass

def crm_seed():
    """An org, a person in it, and a deal: the minimum living pipeline."""
    reset_crm()
    org = post("/api/crm/contact", {"op": "org_add", "name": "Northern Stage"}).json()["id"]
    per = post("/api/crm/contact", {"op": "person_add", "name": "Sarah Fielding",
                                    "org_id": org, "emails": ["sarah@ns.co.uk"]}).json()["id"]
    deal = post("/api/crm/deal", {"op": "add", "title": "Northern Stage deal",
                                  "person_id": per, "value": 450}).json()["id"]
    return org, per, deal

@test
def t_a_deal_needs_a_person_or_an_organisation():
    # Pipedrive's save rule: a deal belongs to someone; a title alone is not a deal.
    reset_crm()
    r = post("/api/crm/deal", {"op": "add", "title": "Orphan deal"})
    eq(r.status_code, 400, r.text)
    ok("person or an organisation" in r.json()["error"], r.json()["error"])
    org = post("/api/crm/contact", {"op": "org_add", "name": "Acme"}).json()["id"]
    r2 = post("/api/crm/deal", {"op": "add", "title": "Acme deal", "org_id": org})
    eq(r2.status_code, 200, r2.text)

@test
def t_the_card_icon_follows_the_next_activity_and_nothing_scheduled_is_its_own_state():
    # The four-state discipline: overdue red, today green, NOTHING amber, future
    # grey. Having no next step is deliberately its own loud state, and the
    # column sorts overdue, today, none, future.
    from datetime import date, timedelta as td
    _org, _per, deal = crm_seed()
    board = post("/api/crm/board", {}).json()["crm"]
    eq(board["deals"][deal]["activity_state"], "none", "a fresh deal has nothing scheduled")
    today = date.today().isoformat()
    a1 = post("/api/crm/activity", {"op": "add", "type": "call", "deal_id": deal,
                                    "due_date": today}).json()
    eq(a1["crm"]["deals"][deal]["activity_state"], "today", "due today is its own state")
    past = (date.today() - td(days=3)).isoformat()
    a2 = post("/api/crm/activity", {"op": "add", "type": "task", "deal_id": deal,
                                    "due_date": past}).json()
    eq(a2["crm"]["deals"][deal]["activity_state"], "overdue", "the earliest open activity wins")
    eq(a2["crm"]["deals"][deal]["next_activity"], past, "and next_activity is that date")
    eq(a2["crm"]["badge"], 2, "the badge counts overdue plus due today")

@test
def t_completing_the_last_activity_prompts_scheduling_the_next():
    # The follow-up prompt is the product: it fires only when the deal's LAST
    # open activity was completed, and never when another remains.
    _org, _per, deal = crm_seed()
    a1 = post("/api/crm/activity", {"op": "add", "type": "call", "deal_id": deal}).json()["id"]
    a2 = post("/api/crm/activity", {"op": "add", "type": "task", "deal_id": deal}).json()["id"]
    first = post("/api/crm/activity", {"op": "done", "id": a1}).json()
    ok("followup_deal_id" not in first, "another activity remains, so no prompt")
    second = post("/api/crm/activity", {"op": "done", "id": a2}).json()
    eq(second.get("followup_deal_id"), deal, "the last one prompts for the next")
    act = second["crm"]["activities"][a2]
    ok(act["done_at"], "done has its own stamp")
    ok(act["due_date"], "and the due date survives completion untouched")

@test
def t_won_lost_and_reopen_keep_the_stage_and_the_reason():
    _org, _per, deal = crm_seed()
    post("/api/crm/deal", {"op": "move", "id": deal, "stage_id": "s3"})
    lost = post("/api/crm/deal", {"op": "lost", "id": deal, "reason": "Too expensive",
                                  "comment": "Budget cut"}).json()["crm"]["deals"][deal]
    eq(lost["status"], "lost", "lost is a status, not deletion")
    eq(lost["lost_reason"], "Too expensive", "the reason is kept for reporting")
    back = post("/api/crm/deal", {"op": "reopen", "id": deal}).json()["crm"]["deals"][deal]
    eq(back["status"], "open", "reopened")
    eq(back["stage_id"], "s3", "back to the exact stage it left from")
    ok("lost_reason" not in back, "and the reason is cleared")

@test
def t_an_untouched_deal_rots_and_any_touch_resets_it():
    _org, _per, deal = crm_seed()
    stages = post("/api/crm/board", {}).json()["crm"]["stages"]
    stages[0]["rot_days"] = 2
    post("/api/crm/stages", {"stages": stages})
    # Age the deal by hand: the store is plain JSON.
    raw = json.load(open(salesdesk.CRM_PATH))
    from datetime import datetime as dt, timedelta as td, timezone as tz
    raw["crm"]["deals"][deal]["touched_at"] = (dt.now(tz.utc) - td(days=3)).isoformat()
    json.dump(raw, open(salesdesk.CRM_PATH, "w"))
    board = post("/api/crm/board", {}).json()["crm"]
    ok(board["deals"][deal]["rotten"], "three untouched days against a two-day limit rots")
    post("/api/crm/deal", {"op": "note_add", "id": deal, "text": "spoke to Sarah"})
    board2 = post("/api/crm/board", {}).json()["crm"]
    ok(not board2["deals"][deal]["rotten"], "any touch, including a note, resets the rot")

@test
def t_a_stage_holding_open_deals_cannot_be_deleted():
    _org, _per, deal = crm_seed()
    stages = post("/api/crm/board", {}).json()["crm"]["stages"]
    r = post("/api/crm/stages", {"stages": stages[1:]})   # drop s1, which holds the deal
    eq(r.status_code, 400, r.text)
    ok("Move them" in r.json()["error"], r.json()["error"])

@test
def t_a_lead_converts_into_a_deal_carrying_everything_and_leaves_the_inbox():
    reset_crm()
    org = post("/api/crm/contact", {"op": "org_add", "name": "Roundhouse"}).json()["id"]
    lead = post("/api/crm/lead", {"op": "add", "org_id": org, "value": 900,
                                  "label": "Hot"}).json()
    lid = lead["id"]
    eq(lead["crm"]["leads"][lid]["title"], "Roundhouse lead", "the title autofills from the org")
    eq(lead["crm"]["new_leads"], 1, "a fresh lead counts as new until opened")
    post("/api/crm/lead", {"op": "note_add", "id": lid, "text": "met at PLASA"})
    conv = post("/api/crm/lead", {"op": "convert", "id": lid}).json()
    did = conv["id"]
    crm = conv["crm"]
    ok(lid not in crm["leads"], "the lead leaves the inbox, no shadow record")
    deal = crm["deals"][did]
    eq(deal["value"], 900.0, "value carried")
    eq(deal["label"], "Hot", "label carried")
    # The board payload is slim: notes ride as a count, the modal fetches them.
    eq(deal["notes_n"], 1, "the board payload carries the note count, not the note")
    ok("notes" not in deal, "the note text stays out of the board payload")
    detail = post("/api/crm/deal", {"op": "detail", "id": did}).json()
    ok(any("PLASA" in n["text"] for n in detail["notes"]), "notes carried, served by detail")

@test
def t_weighted_value_follows_stage_probability_and_deal_probability_overrides():
    _org, _per, deal = crm_seed()
    stages = post("/api/crm/board", {}).json()["crm"]["stages"]
    stages[0]["probability"] = 50
    post("/api/crm/stages", {"stages": stages})
    b = post("/api/crm/board", {}).json()["crm"]["deals"][deal]
    eq(b["weighted_value"], 225.0, "stage probability halves the weighted value")
    post("/api/crm/deal", {"op": "update", "id": deal, "probability": 10})
    b2 = post("/api/crm/board", {}).json()["crm"]["deals"][deal]
    eq(b2["weighted_value"], 45.0, "a deal-level probability overrides the stage's")

@test
def t_deleting_a_deal_is_a_restorable_bin_not_an_erase():
    _org, _per, deal = crm_seed()
    gone = post("/api/crm/deal", {"op": "delete", "id": deal}).json()["crm"]
    ok(deal not in gone["deals"], "a deleted deal leaves the board")
    eq(gone["trash"], 1, "but sits in the bin")
    back = post("/api/crm/deal", {"op": "restore", "id": deal}).json()["crm"]
    ok(deal in back["deals"], "and restores whole")

@test
def t_a_contact_on_open_deals_cannot_be_deleted():
    _org, per, _deal = crm_seed()
    r = post("/api/crm/contact", {"op": "person_delete", "id": per})
    eq(r.status_code, 400, r.text)
    ok("open deal" in r.json()["error"], r.json()["error"])


@test
def t_a_nonfinite_value_can_never_brick_the_crm_store():
    # Python's json module happily WRITES NaN, which is not JSON, so the next
    # read would poison the store and refuse every write forever. The door
    # refuses it now (stage 5: a value is a number, and these are not finite);
    # the cast behind it still rejects it, and the writer refuses non-finite
    # as a backstop.
    _org, _per, deal = crm_seed()
    for bad in ("NaN", "Infinity", "-Infinity"):
        r = post("/api/crm/deal", {"op": "update", "id": deal, "value": bad})
        eq((r.status_code, r.json().get("error")), (400, "The value sent must be a number."), r.text)
        try:
            salesdesk._crm_value(bad)
            ok(False, "the cast takes " + bad)
        except ValueError:
            pass
    board = post("/api/crm/board", {})
    eq(board.status_code, 200, "the store still reads")
    eq(board.json()["crm"]["deals"][deal]["value"], 450.0, "and the value is untouched")
    json.load(open(salesdesk.CRM_PATH))    # raises if anything non-JSON was written

@test
def t_reopening_into_a_deleted_stage_lands_on_a_live_one():
    _org, _per, deal = crm_seed()
    post("/api/crm/deal", {"op": "move", "id": deal, "stage_id": "s2"})
    post("/api/crm/deal", {"op": "won", "id": deal})
    stages = post("/api/crm/board", {}).json()["crm"]["stages"]
    kept = [s for s in stages if s["id"] != "s2"]
    eq(post("/api/crm/stages", {"stages": kept}).status_code, 200,
       "a stage holding only closed deals may go")
    back = post("/api/crm/deal", {"op": "reopen", "id": deal}).json()["crm"]["deals"][deal]
    eq(back["stage_id"], "s1", "the reopened deal lands on a stage that exists")

@test
def t_rescheduling_an_activity_resets_rotting():
    # Pipedrive's rule: ANY touch resets rot, and rescheduling the next call is
    # exactly how a rotten deal gets worked.
    _org, _per, deal = crm_seed()
    aid = post("/api/crm/activity", {"op": "add", "type": "call", "deal_id": deal}).json()["id"]
    stages = post("/api/crm/board", {}).json()["crm"]["stages"]
    stages[0]["rot_days"] = 2
    post("/api/crm/stages", {"stages": stages})
    raw = json.load(open(salesdesk.CRM_PATH))
    from datetime import datetime as dt, timedelta as td, timezone as tz
    raw["crm"]["deals"][deal]["touched_at"] = (dt.now(tz.utc) - td(days=3)).isoformat()
    json.dump(raw, open(salesdesk.CRM_PATH, "w"))
    ok(post("/api/crm/board", {}).json()["crm"]["deals"][deal]["rotten"], "rotten before")
    post("/api/crm/activity", {"op": "update", "id": aid, "due_date": "2030-01-01"})
    ok(not post("/api/crm/board", {}).json()["crm"]["deals"][deal]["rotten"],
       "a reschedule is a touch, so the rot resets")

@test
def t_the_size_guard_reports_rather_than_shredding_history():
    """This used to DELETE the oldest closed deals and their activities when
    the store passed a cap: silently, and biting precisely on the won/lost
    record a business keeps a CRM for. A size guard is a fault to report, not
    a licence to destroy data."""
    _org, _per, deal = crm_seed()
    aid = post("/api/crm/activity", {"op": "add", "type": "call", "deal_id": deal,
                                     "due_date": "2020-01-01"}).json()["id"]
    post("/api/crm/deal", {"op": "won", "id": deal})
    saved = salesdesk.CRM_DEALS_MAX
    salesdesk.CRM_DEALS_MAX = 0        # as if the store were far over its guard
    try:
        crm = post("/api/crm/contact", {"op": "org_add", "name": "Trigger"}).json()["crm"]
        ok(deal in crm["deals"], "the closed deal is still there")
        ok(aid in crm["activities"], "and so is its history")
        d = salesdesk._load_crm()
        ok(d.get("over_cap"), "the fault is recorded instead")
        ok(d["over_cap"]["deals"] > 0, d["over_cap"])
    finally:
        salesdesk.CRM_DEALS_MAX = saved
        d = salesdesk._load_crm(); d.pop("over_cap", None); salesdesk._write_crm(d)


@test
def t_editing_a_contact_keeps_the_addresses_the_form_cannot_show():
    """The contact form shows ONE email and ONE phone. An imported contact can
    have four. Sending back what the form displays must not delete the rest."""
    pid = post("/api/crm/contact", {"op": "person_add", "name": "Jo Bloggs",
                                    "emails": ["jo@work.com", "jo@home.com", "jo@old.com"],
                                    "phones": ["0191 111", "07700 900"]}).json()["id"]
    # The form round-trips only the first of each, as it does today.
    post("/api/crm/contact", {"op": "person_update", "id": pid, "name": "Jo Bloggs",
                              "emails": ["jo@work.com"], "phones": ["0191 111"]})
    p = salesdesk._load_crm()["persons"][pid]
    eq(p["emails"], ["jo@work.com", "jo@home.com", "jo@old.com"], "the others survived")
    eq(p["phones"], ["0191 111", "07700 900"])
    # Genuinely changing the first one still works, and does not duplicate it.
    post("/api/crm/contact", {"op": "person_update", "id": pid, "name": "Jo Bloggs",
                              "emails": ["jo@new.com"], "phones": ["0191 111"]})
    p = salesdesk._load_crm()["persons"][pid]
    eq(p["emails"], ["jo@new.com", "jo@home.com", "jo@old.com"], "changed, not wiped")
    # And a real multi-value edit still replaces the lot.
    post("/api/crm/contact", {"op": "person_update", "id": pid, "name": "Jo Bloggs",
                              "emails": ["a@b.com", "c@d.com"]})
    eq(salesdesk._load_crm()["persons"][pid]["emails"], ["a@b.com", "c@d.com"])

PD_EXPORT = {
    "account": {"name": "Projected Image", "admin": True, "company": "Projected Image UK Ltd",
                "currency": "GBP"},
    "stages": [{"pd_id": "1", "name": "Enquiry", "order": 1, "probability": 20,
                "rot_on": True, "rot_days": 14, "rot_days_stored": 14},
               {"pd_id": "2", "name": "Quoted", "order": 2, "probability": 60,
                "rot_on": True, "rot_days": 7, "rot_days_stored": 7}],
    "orgs": [{"pd_id": "10", "name": "Lumen Events", "address": "Newcastle",
              "created_at": "2024-02-01T09:00:00Z", "updated_at": "2025-01-01T09:00:00Z"}],
    "persons": [{"pd_id": "20", "name": "Sarah Whitfield", "org_pd_id": "10",
                 "emails": ["sarah@lumen.co.uk", "s.whitfield@lumen.co.uk"],
                 "phones": ["0191 111"], "created_at": "2024-02-01T09:00:00Z",
                 "updated_at": "2025-01-01T09:00:00Z"}],
    "deals": [{"pd_id": "30", "title": "12 steel gobos", "value": 480.0, "currency": "GBP",
               "stage_pd_id": "2", "person_pd_id": "20", "org_pd_id": "10", "status": "won",
               "archived": True, "probability": None, "expected_close": "2024-03-01",
               "lost_reason": "", "created_at": "2024-02-02T09:00:00Z",
               "updated_at": "2024-03-04T09:00:00Z", "stage_entered_at": "2024-02-20T09:00:00Z",
               "won_at": "2024-03-04T09:00:00Z", "lost_at": "", "source": "Pipedrive"},
              {"pd_id": "31", "title": "Glass sample", "value": 60.0, "currency": "GBP",
               "stage_pd_id": "1", "person_pd_id": "20", "org_pd_id": "10", "status": "lost",
               "archived": False, "probability": None, "expected_close": "",
               "lost_reason": "Too expensive", "created_at": "2025-05-05T09:00:00Z",
               "updated_at": "2025-06-06T09:00:00Z", "stage_entered_at": "2025-05-05T09:00:00Z",
               "won_at": "", "lost_at": "2025-06-06T09:00:00Z", "source": "Pipedrive"}],
    "activities": [{"pd_id": "40", "type": "call", "raw_type": "call", "subject": "Chase quote",
                    "deal_pd_id": "30", "person_pd_id": "20", "org_pd_id": "10",
                    "due_date": "2024-02-20", "due_time": "10:00", "note": "rang, no answer",
                    "location": "", "done": True, "done_at": "2024-02-20T11:00:00Z",
                    "created_at": "2024-02-19T09:00:00Z"},
                   {"pd_id": "41", "type": "task", "raw_type": "site", "subject": "Site visit",
                    "deal_pd_id": "31", "person_pd_id": "", "org_pd_id": "",
                    "due_date": "", "due_time": "", "note": "", "location": "",
                    "done": False, "done_at": "", "created_at": "2025-05-06T09:00:00Z"}],
    "notes": [{"pd_id": "50", "deal_pd_id": "30", "person_pd_id": "", "org_pd_id": "",
               "text": "Wants them before the show", "at": "2024-02-10T09:00:00Z"}],
    "complete": {"orgs": True, "persons": True, "deals": True, "archived": True,
                 "activities": True, "notes": True},
    "not_migrated": {"products": 0, "files": 3, "activity_types_flattened": {"site": 1}},
}


def crm_wipe():
    """A clean CRM store. Other tests leave deals behind, and an import test is
    about counts."""
    try:
        os.remove(salesdesk.CRM_PATH)
    except FileNotFoundError:
        pass
    jsonstore._poisoned_stores.discard(salesdesk.CRM_PATH)


@test
def t_pipedrive_export_reads_real_v2_shapes():
    """Every test here faked export() wholesale, so the NORMALISERS were never
    exercised. That is exactly where the wrong archive path, the missing rot
    switch, the dict-shaped location and the lost primary all lived."""
    calls = []
    async def fake_get(path, params=None, version="v2"):
        calls.append((path, version))
        if path == "pipelines":
            return {"data": [{"id": 1, "name": "Sales", "is_deal_probability_enabled": True}]}
        if path == "stages":
            return {"data": [
                {"id": 10, "name": "Enquiry", "order_nr": 1, "deal_probability": 20,
                 "is_deal_rot_enabled": True, "days_to_rotten": 14, "pipeline_id": 1},
                {"id": 11, "name": "Quoted", "order_nr": 2, "deal_probability": 60,
                 "is_deal_rot_enabled": False, "days_to_rotten": 30, "pipeline_id": 1}]}
        if path == "dealFields":
            return {"data": [{"key": "label", "name": "Label", "options": [
                {"id": 5, "label": "Hot", "color": "red"},
                {"id": 6, "label": "Trade", "color": "blue"}]},
                {"key": "a" * 40, "name": "Gobo size", "field_type": "enum",
                 "options": [{"id": 9, "label": "B size"}]},
                {"key": "b" * 40, "name": "Glass type", "field_type": "varchar"}]}
        if path == "personFields":
            return {"data": [{"key": "label_ids", "name": "Label", "options": [
                {"id": 71, "label": "Customer", "color": "green"}]}]}
        if path == "organizationFields":
            return {"data": [{"key": "label_ids", "name": "Label", "options": [
                {"id": 81, "label": "Venue", "color": "purple"}]}]}
        if path == "deals":
            return {"data": [{"id": 30, "title": "Live one", "value": 100, "currency": "GBP",
                              "stage_id": 11, "status": "open", "label_ids": [5, 6],
                              "custom_fields": {"a" * 40: 9, "b" * 40: "Borofloat"}}]}
        if path == "deals/archived":
            return {"data": [{"id": 31, "title": "Old one", "value": 200, "currency": "GBP",
                              "stage_id": 11, "status": "won", "is_archived": True,
                              "won_time": "2024-03-04 09:00:00"}]}
        if path == "persons":
            return {"data": [{"id": 20, "name": "Sarah", "job_title": "Buyer",
                              "label_ids": [71],
                              "emails": [{"value": "second@x.com", "primary": False},
                                         {"value": "main@x.com", "primary": True}],
                              "phones": [{"value": "0191 000", "primary": False, "label": "work"},
                                         {"value": "07700 900", "primary": True, "label": "mobile"}]}]}
        if path == "organizations":
            return {"data": [{"id": 40, "name": "Lumen", "website": "lumen.co.uk",
                              "label_ids": [81],
                              "address": {"value": "Newcastle"}}]}
        if path == "activities":
            return {"data": [{"id": 50, "type": "call", "subject": "Ring back",
                              "location": {"value": "12 High St, Durham"},
                              "duration": "01:00:00", "done": True}]}
        if path == "notes":
            return {"data": [{"id": 60, "deal_id": 30, "content": "<p>Wants it <b>Friday</b></p>",
                              "pinned_to_deal_flag": True, "active_flag": True},
                             {"id": 61, "deal_id": 30, "content": "deleted one",
                              "active_flag": False}]}
        if path == "users/me":
            return {"data": {"name": "Cam", "is_admin": True, "company_name": "PI",
                             "default_currency": "GBP", "company_domain": "pi"}}
        return {"data": []}
    saved = (pipedrive._get, pipedrive.API_TOKEN)
    pipedrive._get, pipedrive.API_TOKEN = fake_get, "t"
    try:
        out = run_async(pipedrive.export())
    finally:
        pipedrive._get, pipedrive.API_TOKEN = saved

    paths = [p for p, v in calls]
    ok("deals/archived" in paths, "the back catalogue has its OWN path: " + str(paths))
    ok(("stages", "v2") in calls and ("pipelines", "v2") in calls,
       "stages and pipelines come from v2, which is the only place they exist now")
    # the rot switch, both ways round
    st = {x["name"]: x for x in out["stages"]}
    eq(st["Enquiry"]["rot_days"], 14, "a stage with rotting ON keeps its days")
    eq(st["Quoted"]["rot_days"], 0,
       "a stage with rotting OFF gets no timer, however stale the number behind it")
    eq(st["Quoted"]["rot_days_stored"], 30, "but the number is kept so it can be switched on")
    ok(out["complete"]["stages"], "an empty stage list would be reported, not shrugged off")
    # archived comes from the deal's own flag
    deals = {d["title"]: d for d in out["deals"]}
    ok(deals["Old one"]["archived"] and not deals["Live one"]["archived"])
    eq(deals["Old one"]["won_at"], "2024-03-04T09:00:00Z", "and its real won date")
    eq(deals["Live one"]["label"], "Hot", "the label is resolved to its name")
    eq(out["not_migrated"]["extra_labels_dropped"], 1,
       "and the second label is counted, not silently dropped")
    # primary first, labels ride separately, never folded into the value
    p = out["persons"][0]
    eq(p["emails"][0], "main@x.com", "the PRIMARY address comes first")
    eq(p["phones"][0], "07700 900", "the phone is the phone, dialable as stored")
    eq(p["phone_labels"][0], "mobile", "its label rides beside it")
    eq(p["job_title"], "Buyer")
    eq(p["label"], "Customer", "a person label resolves against the PERSON field's options")
    eq(out["orgs"][0]["label"], "Venue", "and an org label against the org field's")
    eq(out["label_colors"].get("Customer"), "green")
    eq(out["label_colors"].get("Venue"), "purple")
    # custom fields: nested in v2, enums resolved to their labels
    eq(deals["Live one"]["custom"], {"Gobo size": "B size", "Glass type": "Borofloat"},
       "custom field VALUES arrive, with option ids resolved to words")
    eq(out["orgs"][0]["website"], "lumen.co.uk")
    # location is an object in v2
    eq(out["activities"][0]["location"], "12 High St, Durham",
       "not a Python dict printed into the record")
    eq(out["activities"][0]["duration"], "01:00:00")
    # notes: html stripped, pinned carried, deleted skipped
    eq(len(out["notes"]), 1, "a deleted note is not imported")
    eq(out["notes"][0]["text"], "Wants it Friday")
    ok(out["notes"][0]["pinned"], "and what was pinned stays pinned")

@test
def t_pipedrive_import_previews_then_copies_without_duplicating():
    """The import must be safe to run twice, must not touch anything typed in
    by hand, and must keep the REAL dates or the history it was imported for
    is worthless."""
    def go():
        ensure_auth()
        crm_wipe()
        # Something somebody typed into gizmo before the migration.
        mine = post("/api/crm/contact", {"op": "org_add", "name": "Typed by hand"}).json()["id"]
        async def fake_export(progress=None):
            return dict(PD_EXPORT)
        saved = (pipedrive.export, pipedrive.API_TOKEN)
        pipedrive.export, pipedrive.API_TOKEN = fake_export, "t"
        try:
            # 1. The preview writes NOTHING.
            r = post("/api/crm/import", {})
            eq(r.status_code, 200, r.text)
            j = r.json()
            ok(j["dry_run"])
            eq(j["report"]["deals"]["new"], 2)
            eq(j["report"]["persons"]["new"], 1)
            eq(j["report"]["orgs"]["new"], 1)
            eq(j["report"]["kept"]["orgs"], 1, "the hand-typed org is counted as kept")
            eq(len(salesdesk._load_crm()["deals"]), 0, "and nothing was written")
            # 2. The real run.
            r2 = post("/api/crm/import", {"go": True})
            eq(r2.status_code, 200, r2.text)
            ok(not r2.json()["dry_run"])
            d = salesdesk._load_crm()
            eq(len(d["deals"]), 2)
            eq(len(d["persons"]), 1)
            ok(mine in d["orgs"], "the hand-typed record survived the import")
            won = [x for x in d["deals"].values() if x["pd_id"] == "30"][0]
            eq(won["status"], "won")
            eq(won["created_at"], "2024-02-02T09:00:00Z", "the REAL date, not today")
            eq(won["closed_at"], "2024-03-04T09:00:00Z")
            ok(won["archived"], "the back catalogue is marked as such")
            eq(won["value"], 480.0)
            person = [x for x in d["persons"].values() if x["pd_id"] == "20"][0]
            eq(len(person["emails"]), 2, "both addresses came across")
            eq(d["orgs"][person["org_id"]]["name"], "Lumen Events", "and the links hold")
            eq([x["title"] for x in d["deals"].values() if x["pd_id"] == "30"][0], "12 steel gobos")
            ok("Too expensive" in d["lost_reasons"], "lost reasons are seeded from real data")
            names = [s["name"] for s in d["stages"]]
            eq(names, ["Enquiry", "Quoted"], "the real pipeline replaced the defaults")
            act = [x for x in d["activities"].values() if x["pd_id"] == "41"][0]
            eq(act["due_date"], "",
               "an undated activity stays undated: giving it one invents a job")
            deal30 = [x for x in d["deals"].values() if x["pd_id"] == "30"][0]
            eq(len(deal30["notes"]), 1)
            eq(deal30["notes"][0]["text"], "Wants them before the show")
            # 3. Running it AGAIN updates rather than duplicating.
            r3 = post("/api/crm/import", {"go": True})
            eq(r3.json()["report"]["deals"]["new"], 0, "nothing new the second time")
            eq(r3.json()["report"]["deals"]["updated"], 2)
            d2 = salesdesk._load_crm()
            eq(len(d2["deals"]), 2, "and no duplicates")
            eq(len(d2["persons"]), 1)
            eq(len([n for n in d2["deals"][deal30["id"]]["notes"]]), 1, "nor duplicate notes")
            # 4. What could not come across is reported, never silently dropped.
            eq(r3.json()["not_migrated"]["files"], 3)
            eq(r3.json()["not_migrated"]["activity_types_flattened"], {"site": 1})
        finally:
            pipedrive.export, pipedrive.API_TOKEN = saved
    with_accounts(go)

@test
def t_pipedrive_import_refuses_a_partial_read():
    def go():
        ensure_auth()
        crm_wipe()
        async def half(progress=None):
            bad = dict(PD_EXPORT)
            bad["complete"] = dict(PD_EXPORT["complete"], persons=False)
            return bad
        saved = (pipedrive.export, pipedrive.API_TOKEN)
        pipedrive.export, pipedrive.API_TOKEN = half, "t"
        try:
            r = post("/api/crm/import", {"go": True})
            eq(r.status_code, 502, "half an account is not an import")
            ok("persons" in r.json()["error"], r.text)
            eq(len(salesdesk._load_crm()["deals"]), 0, "and nothing was written")
            ok(post("/api/crm/import", {}).json()["dry_run"], "the preview still runs")
        finally:
            pipedrive.export, pipedrive.API_TOKEN = saved
    with_accounts(go)

@test
def t_pipedrive_import_is_master_only():
    def go():
        ensure_auth()
        _uid, sess, _ = ready_user("Ann", "ann")
        eq(post_s(sess, "/api/crm/import", {}).status_code, 403)
    with_accounts(go)

@test
def t_pipedrive_urls_go_to_the_api_not_the_web_app():
    """Both API versions live under /api/. Without that prefix the request
    lands on the Pipedrive web app, which returns a page of HTML with a 200,
    so the failure reads as a parsing problem rather than a wrong address."""
    saved_dom, saved_base = pipedrive.DOMAIN, pipedrive.API_BASE
    pipedrive.DOMAIN, pipedrive.API_BASE = "", ""
    pipedrive._discovered["domain"] = ""
    try:
        ok(pipedrive._base("v1").endswith("/api/v1"), pipedrive._base("v1"))
        ok(pipedrive._base("v2").endswith("/api/v2"), pipedrive._base("v2"))
        # The account tells us its own domain, so nobody has to configure one.
        pipedrive._discovered["domain"] = "acme"
        eq(pipedrive._base("v2"), "https://acme.pipedrive.com/api/v2")
    finally:
        pipedrive.DOMAIN, pipedrive.API_BASE = saved_dom, saved_base
        pipedrive._discovered["domain"] = ""

@test
def t_pipedrive_html_response_is_explained_not_dumped():
    def go():
        ensure_auth()
        class _R:
            status_code = 200
            headers = {"content-type": "text/html; charset=utf-8"}
            text = "<!DOCTYPE html><html><head><script>var w=localStorage..."
            def json(self): raise ValueError("not json")
        class _C:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, *a, **k): return _R()
        saved = (pipedrive.httpx.AsyncClient, pipedrive.API_TOKEN)
        pipedrive.httpx.AsyncClient = lambda **k: _C()
        pipedrive.API_TOKEN = "t"
        try:
            r = post("/api/crm/pipedrive", {})
            eq(r.status_code, 400, r.text)
            msg = r.json()["error"]
            ok("web page rather than the API" in msg, msg)
            ok("<html" not in msg and "DOCTYPE" not in msg,
               "and the markup itself is never handed to the reader")
        finally:
            pipedrive.httpx.AsyncClient, pipedrive.API_TOKEN = saved
    with_accounts(go)

@test
def t_pipedrive_survey_is_master_only_and_reads_nothing_without_a_token():
    def go():
        ensure_auth()
        _uid, sess, _ = ready_user("Ann", "ann")
        eq(post_s(sess, "/api/crm/pipedrive", {}).status_code, 403,
           "somebody else's CRM is not a member's to survey")
        saved = pipedrive.API_TOKEN
        pipedrive.API_TOKEN = ""
        try:
            r = post("/api/crm/pipedrive", {})
            eq(r.status_code, 400)
            ok("hosting settings" in r.json()["error"] and "Railway" not in r.json()["error"], r.text)
            ok(r.json()["configured"] is False)
        finally:
            pipedrive.API_TOKEN = saved
    with_accounts(go)

@test
def t_pipedrive_survey_names_what_would_not_survive_an_import():
    """The survey exists to answer the questions that decide the job. It has
    to SAY the awkward ones, not just count rows."""
    def go():
        ensure_auth()
        pages = {
            ("users/me", "v1"): {"data": {"name": "Cam", "email": "c@p.com", "is_admin": True,
                                          "company_name": "Projected Image",
                                          "default_currency": "GBP"}},
            ("pipelines", "v2"): {"data": [{"id": 1, "name": "Trade"}, {"id": 2, "name": "Retail"}]},
            ("stages", "v2"): {"data": [{"id": 10, "name": "Qualified", "pipeline_id": 1,
                                         "order_nr": 1, "deal_probability": 50,
                                         "is_deal_rot_enabled": True, "days_to_rotten": 14}]},
            ("users", "v1"): {"data": [{"id": 7, "name": "Ann", "email": "a@p.com",
                                        "active_flag": True, "is_admin": False},
                                       {"id": 8, "name": "Bob", "email": "b@p.com",
                                        "active_flag": True, "is_admin": False}]},
            ("dealFields", "v1"): {"data": [
                {"key": "title", "name": "Title", "field_type": "varchar"},
                {"key": "a" * 40, "name": "Gobo size", "field_type": "varchar"}]},
            ("personFields", "v1"): {"data": []},
            ("activityTypes", "v1"): {"data": [{"key_string": "call", "name": "Call"},
                                               {"key_string": "site", "name": "Site visit"}]},
            ("deals", "v2"): {"data": [
                {"id": 1, "pipeline_id": 1, "currency": "GBP", "owner_id": 7, "status": "won",
                 "custom_fields": {"a" * 40: "B size"}},
                {"id": 2, "pipeline_id": 2, "currency": "EUR", "owner_id": 8, "status": "open"}]},
            ("persons", "v2"): {"data": []},
            ("organizations", "v2"): {"data": []},
            ("activities", "v2"): {"data": [{"id": 5, "type": "site"}]},
            ("leads", "v1"): {"data": []},
            ("leads/archived", "v1"): {"data": [{"id": "l1"}, {"id": "l2"}]},
        }
        async def fake_get(path, params=None, version="v2"):
            if path == "deals/archived":
                return {"data": [{"id": 3, "pipeline_id": 1, "status": "won"}]}
            return pages.get((path, version), {"data": []})
        saved = (pipedrive._get, pipedrive.API_TOKEN)
        pipedrive._get = fake_get
        pipedrive.API_TOKEN = "test-token"    # configured() gates the route
        try:
            r = post("/api/crm/pipedrive", {})
            eq(r.status_code, 200, r.text)
            j = r.json()
            eq(j["account"]["company"], "Projected Image")
            eq(j["counts"]["deals"], 2)
            eq(j["counts"]["archived_deals"], 1, "the back catalogue is counted separately")
            eq(j["counts"]["archived_leads"], 2, "and so are archived leads, which /v1/leads leaves out")
            warn = " ".join(j["warnings"])
            ok("2 pipelines are in use" in warn, warn)
            ok("more than one currency" in warn, warn)
            ok("Gobo size" in warn, warn)
            ok("owner" in warn.lower(), warn)
            eq(j["custom_fields"]["deals"][0]["name"], "Gobo size")
            eq(j["custom_fields"]["deals"][0]["used_on"], 1)
            ok(any(t["name"] == "Site visit" and t["used"] == 1 for t in j["activity_types"]),
               j["activity_types"])
        finally:
            pipedrive._get, pipedrive.API_TOKEN = saved
    with_accounts(go)

@test
def t_reimport_never_reverts_what_was_edited_in_gizmo():
    """The trap: import, work in gizmo for a month, press Import again — and
    every stage move, won and ticked task snaps back to what Pipedrive last
    knew. A record edited HERE since the last import is kept, and said so."""
    def go():
        ensure_auth()
        crm_wipe()
        async def fake_export(progress=None):
            return dict(PD_EXPORT)
        saved = (pipedrive.export, pipedrive.API_TOKEN)
        pipedrive.export, pipedrive.API_TOKEN = fake_export, "t"
        try:
            post("/api/crm/import", {"go": True})
            d = salesdesk._load_crm()
            lost = [x for x in d["deals"].values() if x["pd_id"] == "31"][0]
            act = [x for x in d["activities"].values() if x["pd_id"] == "41"][0]
            # A month of gizmo work: the lost deal reopens, the task gets done.
            post("/api/crm/deal", {"op": "reopen", "id": lost["id"]})
            post("/api/crm/activity", {"op": "done", "id": act["id"]})
            # Pipedrive moves on too.
            changed = dict(PD_EXPORT)
            changed["deals"] = [dict(x, title=x["title"] + " v2") for x in PD_EXPORT["deals"]]
            async def fake2(progress=None):
                return changed
            pipedrive.export = fake2
            r = post("/api/crm/import", {"go": True}).json()
            eq(r["report"]["kept_edited"]["deals"], 1, r["report"])
            eq(r["report"]["kept_edited"]["activities"], 1, r["report"])
            d2 = salesdesk._load_crm()
            mine = [x for x in d2["deals"].values() if x["pd_id"] == "31"][0]
            eq(mine["status"], "open", "the reopen SURVIVED the re-import")
            eq(mine["title"], "Glass sample", "kept whole, not half-merged")
            theirs = [x for x in d2["deals"].values() if x["pd_id"] == "30"][0]
            eq(theirs["title"], "12 steel gobos v2", "an untouched record still updates")
            act2 = [x for x in d2["activities"].values() if x["pd_id"] == "41"][0]
            ok(act2["done"], "the ticked task stays ticked")
            # A THIRD import: the protection must not expire after one cycle.
            # A timestamp guard did exactly that — the import re-stamped its
            # high-water mark past the edit, and import #3 reverted everything.
            post("/api/crm/import", {"go": True})
            d3 = salesdesk._load_crm()
            eq([x for x in d3["deals"].values() if x["pd_id"] == "31"][0]["status"], "open",
               "the edit survives EVERY later import, not just the next one")
            ok([x for x in d3["activities"].values() if x["pd_id"] == "41"][0]["done"])
        finally:
            pipedrive.export, pipedrive.API_TOKEN = saved
    with_accounts(go)

@test
def t_archiving_and_deleting_in_gizmo_survive_the_next_import():
    """Archive never called _crm_touch (touching resets rot), so nothing
    stamped the record and the next import quietly put the deal back on the
    board. Deleted notes and activities were resurrected the same way."""
    def go():
        ensure_auth()
        crm_wipe()
        async def fake_export(progress=None):
            return dict(PD_EXPORT)
        saved = (pipedrive.export, pipedrive.API_TOKEN)
        pipedrive.export, pipedrive.API_TOKEN = fake_export, "t"
        try:
            post("/api/crm/import", {"go": True})
            d = salesdesk._load_crm()
            lost = [x for x in d["deals"].values() if x["pd_id"] == "31"][0]
            deal30 = [x for x in d["deals"].values() if x["pd_id"] == "30"][0]
            act = [x for x in d["activities"].values() if x["pd_id"] == "41"][0]
            post("/api/crm/deal", {"op": "archive", "id": lost["id"]})
            nid = [n for n in deal30["notes"] if n.get("pd_id")][0]["id"]
            post("/api/crm/deal", {"op": "note_del", "id": deal30["id"], "note_id": nid})
            post("/api/crm/activity", {"op": "delete", "id": act["id"]})
            post("/api/crm/import", {"go": True})
            d2 = salesdesk._load_crm()
            ok([x for x in d2["deals"].values() if x["pd_id"] == "31"][0].get("archived"),
               "archived in gizmo stays archived through an import")
            eq([n for n in d2["deals"][deal30["id"]]["notes"] if n.get("pd_id")], [],
               "a deleted imported note leaves a tombstone, not a gap to refill")
            eq([x for x in d2["activities"].values() if x.get("pd_id") == "41"], [],
               "and a deleted imported activity is not resurrected")
        finally:
            pipedrive.export, pipedrive.API_TOKEN = saved
    with_accounts(go)

@test
def t_a_merge_holds_through_the_next_import():
    """The winner absorbs the loser's Pipedrive identity: without that, the
    next import recreated the duplicate and re-pointed its deals back at it."""
    def go():
        ensure_auth()
        crm_wipe()
        async def fake_export(progress=None):
            return dict(PD_EXPORT)
        saved = (pipedrive.export, pipedrive.API_TOKEN)
        pipedrive.export, pipedrive.API_TOKEN = fake_export, "t"
        try:
            post("/api/crm/import", {"go": True})
            d = salesdesk._load_crm()
            imported = [p for p in d["persons"].values() if p["pd_id"] == "20"][0]
            dup = post("/api/crm/contact", {"op": "person_add", "name": "Sarah W."}).json()["id"]
            # Merge the IMPORTED person into the hand-made one: the winner has
            # no pd identity of its own, the loser's must carry across whole.
            post("/api/crm/contact", {"op": "person_merge", "id": imported["id"], "into": dup})
            post("/api/crm/import", {"go": True})
            d2 = salesdesk._load_crm()
            eq(len([p for p in d2["persons"].values() if p.get("name") == "Sarah Whitfield"]), 0,
               "the merged duplicate is NOT recreated by the import")
            keeper = d2["persons"][dup]
            deal = [x for x in d2["deals"].values() if x["pd_id"] == "30"][0]
            eq(deal["person_id"], dup, "and the imported deal points at the keeper")
            ok(keeper.get("edited_here"), "a merge is a gizmo edit, protected like one")
        finally:
            pipedrive.export, pipedrive.API_TOKEN = saved
    with_accounts(go)

@test
def t_label_editor_spares_the_contact_label_colours():
    reset_crm()
    org = post("/api/crm/contact", {"op": "org_add", "name": "Acme"}).json()["id"]
    post("/api/crm/deal", {"op": "add", "title": "Acme deal", "org_id": org})
    # An imported person label sits in the colour map beside the deal labels.
    d = salesdesk._load_crm()
    d["label_colors"]["Repeat customer"] = "green"
    salesdesk._write_crm(d)
    r = post("/api/crm/stages", {"labels": [{"name": "VIP", "color": "purple"}]}).json()
    eq(r["crm"]["label_colors"].get("Repeat customer"), "green",
       "saving the deal labels must not grey out every contact chip")
    eq(r["crm"]["label_colors"]["VIP"], "purple")
    ok("Hot" not in r["crm"]["label_colors"], "but a deleted DEAL label does leave the map")

@test
def t_zero_is_a_custom_value_not_a_deletion():
    _org, _per, deal = crm_seed()
    post("/api/crm/deal", {"op": "update", "id": deal, "custom": {"Discount %": 0}})
    b = post("/api/crm/board", {}).json()["crm"]["deals"][deal]
    eq(b["custom"], {"Discount %": "0"}, "a numeric zero is stored, not silently removed")

@test
def t_restoring_a_deal_whose_stage_vanished_lands_on_the_board():
    _org, _per, deal = crm_seed()
    stages = post("/api/crm/board", {}).json()["crm"]["stages"]
    stages.append({"name": "Waiting", "probability": 100, "rot_days": 0})
    post("/api/crm/stages", {"stages": stages})
    waiting = post("/api/crm/board", {}).json()["crm"]["stages"][-1]["id"]
    post("/api/crm/deal", {"op": "move", "id": deal, "stage_id": waiting})
    post("/api/crm/deal", {"op": "delete", "id": deal})
    # With its only deal binned, the stage can be removed...
    post("/api/crm/stages", {"stages": stages[:-1]})
    back = post("/api/crm/deal", {"op": "restore", "id": deal}).json()["crm"]
    ok(back["deals"][deal]["stage_id"] in {s["id"] for s in back["stages"]},
       "a restored deal must land in a REAL column, not render nowhere")

@test
def t_the_full_contact_form_can_prune_addresses():
    """The single-field compensation guards forms that show one email. The
    detail form shows them all, says so, and its prune must stick."""
    reset_crm()
    per = post("/api/crm/contact", {"op": "person_add", "name": "Multi",
                                    "emails": ["a@x.com", "b@x.com", "c@x.com"]}).json()["id"]
    r = post("/api/crm/contact", {"op": "person_update", "id": per,
                                  "emails": ["a@x.com"], "contacts_full": True}).json()
    eq(r["crm"]["persons"][per]["emails"], ["a@x.com"],
       "the full form's list is the whole truth, prune included")
    # And the one-field compensation still guards forms that DON'T say so.
    post("/api/crm/contact", {"op": "person_update", "id": per,
                              "emails": ["a@x.com", "b@x.com"], "contacts_full": True})
    r2 = post("/api/crm/contact", {"op": "person_update", "id": per,
                                   "emails": ["z@x.com"]}).json()
    eq(sorted(r2["crm"]["persons"][per]["emails"]), ["b@x.com", "z@x.com"],
       "a one-field form still cannot shred the addresses it cannot show")

@test
def t_reimport_spares_stages_made_here_and_the_editor_keeps_their_identity():
    """Two halves of one trap. The stage editor used to strip pd_id, so the
    next import saw strangers and duplicated every stage; and the import used
    to replace the stage list wholesale, dropping gizmo-made stages and
    orphaning their deals off the board."""
    def go():
        ensure_auth()
        crm_wipe()
        async def fake_export(progress=None):
            return dict(PD_EXPORT)
        saved = (pipedrive.export, pipedrive.API_TOKEN)
        pipedrive.export, pipedrive.API_TOKEN = fake_export, "t"
        try:
            post("/api/crm/import", {"go": True})
            stages = post("/api/crm/board", {}).json()["crm"]["stages"]
            # The editor round-trip, exactly as the browser sends it.
            stages.append({"name": "Install booked", "probability": 100, "rot_days": 0})
            r = post("/api/crm/stages", {"stages": stages})
            eq(r.status_code, 200, r.text)
            after = post("/api/crm/board", {}).json()["crm"]["stages"]
            ok(after[0].get("pd_id"), "an imported stage keeps its Pipedrive identity")
            install = after[-1]["id"]
            # A deal moves into the gizmo-made stage...
            d = salesdesk._load_crm()
            lost = [x for x in d["deals"].values() if x["pd_id"] == "31"][0]
            post("/api/crm/deal", {"op": "reopen", "id": lost["id"]})
            post("/api/crm/deal", {"op": "move", "id": lost["id"], "stage_id": install})
            # ...and the next import keeps both the stage and the deal in it.
            r2 = post("/api/crm/import", {"go": True}).json()
            eq(r2["report"]["stages"]["updated"], 2, "the imported stages matched, not duplicated")
            d2 = salesdesk._load_crm()
            names = [s["name"] for s in d2["stages"]]
            eq(names, ["Enquiry", "Quoted", "Install booked"], names)
            mine = [x for x in d2["deals"].values() if x["pd_id"] == "31"][0]
            eq(mine["stage_id"], install, "and the deal is still in it")
            # Last: a stage CHANGED at the desk is gizmo's, like every other
            # record. Stages were the one thing the import still rebuilt.
            stages2 = post("/api/crm/board", {}).json()["crm"]["stages"]
            stages2[0]["name"] = "First contact"
            stages2[0]["probability"] = 35
            post("/api/crm/stages", {"stages": stages2})
            r3 = post("/api/crm/import", {"go": True}).json()
            eq(r3["report"]["kept_edited"]["stages"], 1, r3["report"])
            final = post("/api/crm/board", {}).json()["crm"]["stages"]
            eq(final[0]["name"], "First contact",
               "a renamed stage is not rebuilt from Pipedrive on the next import")
            eq(final[0]["probability"], 35, "nor is a retuned probability")
        finally:
            pipedrive.export, pipedrive.API_TOKEN = saved
    with_accounts(go)

@test
def t_archiving_is_a_third_door_and_quiets_the_nagging():
    # Not won, not lost, off the desk: this account had archived 257 deals
    # before the button existed. An archived deal's to-dos stop counting.
    from datetime import date, timedelta as td
    _org, _per, deal = crm_seed()
    yesterday = (date.today() - td(days=1)).isoformat()
    post("/api/crm/activity", {"op": "add", "type": "task", "deal_id": deal,
                               "due_date": yesterday})
    eq(post("/api/crm/board", {}).json()["crm"]["badge"], 1, "an overdue task nags")
    r = post("/api/crm/deal", {"op": "archive", "id": deal}).json()["crm"]
    ok(r["deals"][deal]["archived"], "archived, still on the payload for its own filter")
    eq(r["badge"], 0, "but its task stops nagging")
    r2 = post("/api/crm/deal", {"op": "unarchive", "id": deal}).json()["crm"]
    ok(not r2["deals"][deal].get("archived"))
    eq(r2["badge"], 1, "and starts again when it returns")

@test
def t_custom_fields_arrive_render_and_edit():
    def go():
        ensure_auth()
        crm_wipe()
        rich = dict(PD_EXPORT)
        rich["deals"] = [dict(PD_EXPORT["deals"][0], custom={"Gobo size": "B size"}),
                         PD_EXPORT["deals"][1]]
        async def fake_export(progress=None):
            return rich
        saved = (pipedrive.export, pipedrive.API_TOKEN)
        pipedrive.export, pipedrive.API_TOKEN = fake_export, "t"
        try:
            r = post("/api/crm/import", {"go": True}).json()
            eq(r["report"]["custom_values"], 1, "the preview counts what arrives")
            crm = post("/api/crm/board", {}).json()["crm"]
            did = [k for k, v in crm["deals"].items() if v.get("pd_id") == "30"][0]
            eq(crm["deals"][did]["custom"], {"Gobo size": "B size"},
               "the value is ON the deal the board ships")
            # Editable, and an empty value removes the field from this deal.
            post("/api/crm/deal", {"op": "update", "id": did,
                                   "custom": {"Gobo size": "E size", "Fitting": "M size"}})
            post("/api/crm/deal", {"op": "update", "id": did, "custom": {"Fitting": ""}})
            crm2 = post("/api/crm/board", {}).json()["crm"]
            eq(crm2["deals"][did]["custom"], {"Gobo size": "E size"})
            log = post("/api/crm/deal", {"op": "detail", "id": did}).json()["changelog"]
            ok(any(c["field"] == "Gobo size" and c["to"] == "E size" for c in log),
               "a custom edit is history like any other")
        finally:
            pipedrive.export, pipedrive.API_TOKEN = saved
    with_accounts(go)

@test
def t_contact_notes_live_behind_detail_and_the_payload_stays_slim():
    _org, per, _deal = crm_seed()
    r = post("/api/crm/contact", {"op": "note_add", "id": per, "text": "prefers glass"}).json()
    p = r["crm"]["persons"][per]
    ok("notes" not in p, "the board payload ships a count, not two years of notes")
    eq(p["notes_n"], 1)
    det = post("/api/crm/contact", {"op": "detail", "id": per}).json()
    eq(det["notes"][0]["text"], "prefers glass")
    nid = det["notes"][0]["id"]
    post("/api/crm/contact", {"op": "note_pin", "id": per, "note_id": nid})
    ok(post("/api/crm/contact", {"op": "detail", "id": per}).json()["notes"][0]["pinned"])
    post("/api/crm/contact", {"op": "note_del", "id": per, "note_id": nid})
    eq(post("/api/crm/contact", {"op": "detail", "id": per}).json()["notes"], [])

@test
def t_merging_a_duplicate_repoints_everything_and_removes_it():
    # 1,951 imported people guarantee duplicates, and delete is blocked while
    # deals point at one: merge is the only honest exit.
    _org, per, _deal = crm_seed()
    dup = post("/api/crm/contact", {"op": "person_add", "name": "S. Fielding",
                                    "emails": ["sf@ns.co.uk"]}).json()["id"]
    deal2 = post("/api/crm/deal", {"op": "add", "title": "Dup deal",
                                   "person_id": dup, "value": 100}).json()["id"]
    r = post("/api/crm/contact", {"op": "person_merge", "id": dup, "into": per})
    eq(r.status_code, 200, r.text)
    crm = r.json()["crm"]
    ok(dup not in crm["persons"], "the duplicate is gone")
    eq(crm["deals"][deal2]["person_id"], per, "its deal now points at the keeper")
    ok("sf@ns.co.uk" in crm["persons"][per]["emails"], "and its email came across")
    eq(post("/api/crm/contact", {"op": "person_merge", "id": per, "into": per}).status_code,
       400, "merging a contact into itself is refused")

@test
def t_labels_lost_reasons_and_the_nag_are_editable_settings():
    reset_crm()
    org = post("/api/crm/contact", {"op": "org_add", "name": "Acme"}).json()["id"]
    post("/api/crm/deal", {"op": "add", "title": "Acme deal", "org_id": org})
    r = post("/api/crm/stages", {"labels": [{"name": "VIP", "color": "purple"},
                                            {"name": "Trade", "color": "not-a-colour"}]}).json()
    eq(r["crm"]["labels"], ["VIP", "Trade"])
    eq(r["crm"]["label_colors"]["VIP"], "purple")
    eq(r["crm"]["label_colors"]["Trade"], "gray", "an unknown colour falls to grey, not garbage")
    r2 = post("/api/crm/stages", {"lost_reasons": ["Too dear", "Ghosted"]}).json()
    eq(r2["crm"]["lost_reasons"], ["Too dear", "Ghosted"])
    r3 = post("/api/crm/stages", {"followup_popup": False}).json()
    eq(r3["crm"]["settings"]["followup_popup"], False)
    eq(post("/api/crm/stages", {"labels": []}).status_code, 400)

@test
def t_deals_and_activities_carry_an_owner():
    _org, per, deal = crm_seed()
    crm = post("/api/crm/board", {}).json()["crm"]
    ok(crm["deals"][deal].get("owner"), "a new deal belongs to whoever added it")
    ok(isinstance(crm.get("team"), list), "and the payload carries the pick-list")
    post("/api/crm/deal", {"op": "update", "id": deal, "owner": "u_ann"})
    a = post("/api/crm/activity", {"op": "add", "type": "call", "deal_id": deal,
                                   "assignee": "u_ann"}).json()
    crm2 = post("/api/crm/board", {}).json()["crm"]
    eq(crm2["deals"][deal]["owner"], "u_ann")
    eq(crm2["activities"][a["id"]]["assignee"], "u_ann")
    log = post("/api/crm/deal", {"op": "detail", "id": deal}).json()["changelog"]
    ok(any(c["field"] == "owner" for c in log), "a handover is history")

@test
def t_the_bin_lists_what_it_holds():
    _org, _per, deal = crm_seed()
    r = post("/api/crm/deal", {"op": "delete", "id": deal}).json()["crm"]
    eq(r["trash"], 1)
    eq(r["trash_items"][0]["id"], deal, "the bin is a list the browser can render")
    ok(r["trash_items"][0]["deleted_at"])

