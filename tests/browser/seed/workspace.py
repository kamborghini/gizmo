# Workspace seed: Team (people, work clock, activity), Memory, Skills, Chat, Guide requests.
# Proven 14 Oct 2026 against the dispatch setup.
# Exec'd in the harness prelude's globals (post, post_s, tok, client, copilot, APP_AUTH,
# SCRATCH, run, ensure_auth ...), after the prelude and BEFORE uvicorn serves the app.
# Every person, company, address and order here is invented.
# Kinds: (a) the app's own routes, (b) a store's own writer, (c) an in-process stand-in
# for an outside system (only the Anthropic model call, and only while seeding).
import json as _j, os as _o, secrets as _sec, types as _types
from datetime import datetime as _dt, timedelta as _td, timezone as _tz
from zoneinfo import ZoneInfo as _ZI

_LDN = _ZI("Europe/London")
_NOW = _dt.now(_tz.utc)
def _iso(d): return d.astimezone(_tz.utc).isoformat()
def _ldn(days_ago, hh, mm):
    """A London wall-clock time `days_ago` days back, as an aware datetime."""
    d = (_NOW.astimezone(_LDN) - _td(days=days_ago)).replace(hour=hh, minute=mm, second=0, microsecond=0)
    return d
WS_SEED = {}

# ---------------------------------------------------------------- prerequisite
# The harness leaves Memory and Skills at their production /data default (see
# _ws_stores in the dispatch suite (tests/dispatch/), which redirects them per test). On a Mac
# /data cannot be made, so every note or skill write answers 500. Same redirect,
# to the run's scratch dir, done once before anything is written.
memory.MEMORY_PATH = SCRATCH + "/store_memory.json"
skillbook.SKILLS_PATH = SCRATCH + "/store_skills.json"
for _p in (memory.MEMORY_PATH, skillbook.SKILLS_PATH):
    jsonstore._poisoned_stores.discard(_p)

ensure_auth()
_WS_MASTER = APP_AUTH["master"]

# ---------------------------------------------------------------- Team: accounts (a)
# make_user / ready_user copied from the dispatch suite (tests/dispatch/; they sit after the
# prelude, so they are not in it): /api/team/user op=create, then the forced
# first-password change through /api/auth/password, then a fresh sign-in.
def _make_user(name, username, role="member"):
    _r = post("/api/team/user", {"op": "create", "name": name, "username": username, "role": role})
    assert _r.status_code == 200, _r.text
    j = _r.json()
    return [u["id"] for u in j["users"] if u["username"] == username][0], j["starter_password"]
def _bare(path, body):                      # bare() from the tests: a Shopify token, no app session
    gate._rl_hits.clear(); gate._rl_global.clear()
    return client.post(path, json=body, headers={"Authorization": "Bearer " + tok()})
def _login(username, pw):
    return _bare("/api/auth/login", {"username": username, "password": pw})
def _ready_user(name, username, role="member", pw="seed-chosen-pw-2026"):
    uid, starter = _make_user(name, username, role)
    team._login_hits.clear()
    s0 = _login(username, starter).json()["session"]
    post_s(s0, "/api/auth/password", {"current": starter, "new": pw})
    team._login_hits.clear()
    return uid, _login(username, pw).json()["session"]

_WS_PEOPLE = {}
for name, username, role in (("Priya Nandakumar", "priya", "admin"),
                             ("Owen Castellano", "owen", "member"),
                             ("Hattie Brennan", "hattie", "member"),
                             ("Jonah Featherstone", "jonah", "parttime"),
                             ("Lena Okafor", "lena", "parttime")):
    _WS_PEOPLE[username] = _ready_user(name, username, role)
# Made and never signed in: "Never logged in", still on its starter password.
_WS_PEOPLE["rufus"] = (_make_user("Rufus Delaney", "rufus", "member")[0], None)
# Made, signed in once, then switched off by the master (op=active, as the page's menu sends it).
_WS_PEOPLE["gemma"] = _ready_user("Gemma Whitlow", "gemma", "member")
assert post("/api/team/user", {"op": "active", "id": _WS_PEOPLE["gemma"][0], "active": False}).status_code == 200
# Hattie opens the bench tabs only (op=tabs, the Tabs panel's Save), and may edit the size list (op=sizes).
assert post("/api/team/user", {"op": "tabs", "id": _WS_PEOPLE["hattie"][0],
                               "tabs": ["labels", "sizes", "crm", "mail", "files"]}).status_code == 200
assert post("/api/team/user", {"op": "sizes", "id": _WS_PEOPLE["hattie"][0], "can_sizes": True}).status_code == 200
_WSU = {k: v[0] for k, v in _WS_PEOPLE.items()}
_WSS = {k: v[1] for k, v in _WS_PEOPLE.items()}
# Last sign-ins spread out (b): the accounts register, through its own writer.
_ud = team._load_users()
for k, days in (("priya", 0.2), ("owen", 1.1), ("hattie", 2.4), ("jonah", 0.15), ("lena", 0.3), ("gemma", 41)):
    _ud["users"][_WSU[k]]["last_login_at"] = _iso(_NOW - _td(days=days))
team._write_users(_ud)

# ---------------------------------------------------------------- Team: the work clock (b) + (a)
# Finished shifts for the two part-timers over the last fortnight, written with the
# work log's own writer in the shape the clock route appends ({id, uid, start, end,
# secs}; a correction adds corrected/corrected_by/corrected_at/note, as /api/work/resolve does).
_w = work._load_work()
_shifts = []
for days_ago, who, (h0, m0), (h1, m1) in (
        (12, "jonah", (9, 0), (13, 30)), (11, "lena", (13, 0), (17, 15)), (10, "jonah", (9, 5), (14, 0)),
        (9, "lena", (8, 45), (12, 50)), (7, "jonah", (9, 0), (13, 10)), (6, "lena", (12, 30), (16, 45)),
        (5, "jonah", (8, 55), (12, 40)), (4, "lena", (9, 0), (13, 0)), (3, "jonah", (9, 10), (15, 20)),
        (2, "lena", (13, 0), (17, 5)), (1, "jonah", (8, 50), (12, 55)), (1, "lena", (12, 0), (16, 30)),
        (0, "lena", (7, 30), (11, 15))):
    a, b = _ldn(days_ago, h0, m0), _ldn(days_ago, h1, m1)
    if b > _NOW: continue
    _shifts.append({"uid": _WSU[who], "start": _iso(a), "end": _iso(b), "secs": int((b - a).total_seconds())})
_shifts.sort(key=lambda s: s["start"])
for i, s in enumerate(_shifts, 1):
    s["id"] = f"w{i}"
# One forgotten clock-out, closed by Priya the next morning (a correction).
_fix = max((x for x in _shifts if x["uid"] == _WSU["jonah"]), key=lambda x: x["secs"])
_fix.update({"corrected": True, "corrected_by": _WSU["priya"],
             "corrected_at": _iso(_dt.fromisoformat(_fix["end"]) + _td(hours=17)),
             "note": "left the bench without clocking out"})
_w["sessions"] = _shifts
_w["seq"] = len(_shifts)
work._write_work(_w)
# Jonah on the clock now: the real clock route with his own session (a), then the
# start moved back three hours, exactly as t_work_the_clock_is_the_servers_and_only_for_parttime does (b).
assert post_s(_WSS["jonah"], "/api/work/clock", {"op": "in"}).status_code == 200
_w = work._load_work()
_open = _w["open"][_WSU["jonah"]]
_open["start"] = _iso(_NOW - _td(hours=3, minutes=10))
work._write_work(_w)

# ---------------------------------------------------------------- Team: the activity ledger (b)
# The ledger's rows as _track writes them ({t, sub, area, action, detail}, "src":
# "system" for no person, "ws" for a part-timer on the clock), backdated across the
# fortnight, appended to the in-memory ledger and flushed by its own _events_flush.
_ev = []
def _e(when, who, area, action, detail="", ws=None, system=False):
    row = {"t": _iso(when), "sub": "" if system else _WSU.get(who, who), "area": area,
           "action": action[:80], "detail": detail[:200]}
    if system: row["src"] = "system"
    if ws: row["ws"] = ws
    _ev.append(row)
_orders = iter(range(2318, 2400))
for s in _shifts:                                   # work done on the clock, stamped with the shift
    a = _dt.fromisoformat(s["start"]); who = "jonah" if s["uid"] == _WSU["jonah"] else "lena"
    _e(a, who, "work", "clocked in", ws=s["id"])
    for k, (area, action) in enumerate((("production", "printed labels"), ("production", "marked made"),
                                        ("production", "marked made"), ("dispatch", "booked a courier"))):
        o = next(_orders)
        _e(a + _td(minutes=35 + 40 * k), who, area, action,
           f"#{o}" + (" · DPD Next Day" if area == "dispatch" else ""), ws=s["id"])
    _e(_dt.fromisoformat(s["end"]), who, "work", "clocked out", work._fmt_secs(s["secs"]))
_e(_dt.fromisoformat(_open["start"]), "jonah", "work", "clocked in", ws=_open["id"])
_e(_dt.fromisoformat(_open["start"]) + _td(minutes=25), "jonah", "production", "marked made", "#2399", ws=_open["id"])
for days_ago, hh, mm, who, area, action, detail in (
        (13, 9, 40, "priya", "settings", "changed shipping settings", "box presets"),
        (12, 10, 5, "owen", "crm", "added a deal", "Marlowe Events · winter ball gobos"),
        (12, 15, 30, "hattie", "files", "uploaded a file", "Holloway Theatre logo v3.pdf"),
        (11, 11, 10, "owen", "crm", "added an activity", "Call back Orchard Lane Church"),
        (10, 9, 20, "priya", "dispatch", "booked a courier", "#2341 · UPS Express"),
        (9, 14, 0, "hattie", "sizes", "changed a size rule", "Kestrel Mini 200 is now 37.5mm"),
        (8, 10, 45, "owen", "chase", "marked an account chased", "Brightwater Venues"),
        (7, 16, 20, "hattie", "files", "uploaded a file", "Fernside Hotel monogram.ai"),
        (6, 9, 15, "priya", "team", "changed a role", "Lena Okafor is now part-time"),
        (5, 11, 30, "owen", "crm", "converted a lead to a deal", "Cobalt Stage Hire"),
        (4, 13, 5, "hattie", "production", "released to make", "#2377"),
        (3, 10, 0, "priya", "settings", "changed a store preference", "concise answers on"),
        (2, 9, 30, "owen", "crm", "added an organisation", "Fernside Hotel"),
        (2, 15, 10, "hattie", "files", "uploaded a file", "Cobalt Stage Hire artwork.png"),
        (1, 11, 45, "priya", "loans", "loaned out a unit", "LU-014 to Brightwater Venues"),
        (0, 8, 5, "", "dispatch", "cleared a collection", "UPS collection for today", )):
    when = _ldn(days_ago, hh, mm)
    if when < _NOW:
        _e(when, who, area, action, detail, system=(who == ""))
_led = activity._load_events()
_led.extend(_ev)
_led.sort(key=lambda r: r.get("t", ""))
activity._events_dirty = True
activity._events_flush()

# ---------------------------------------------------------------- Memory: notes (a) + (b)
# Admin notes through the route (payload shape from t_memory_and_skills_routes_edit_refuse_and_fail_honestly).
_notes = [
    {"type": "fact", "text": "Glass gobos take five working days from artwork approval; steel gobos take three."},
    {"type": "fact", "text": "Trade accounts pay on 30-day terms and get 15% off glass gobos from their third order."},
    {"type": "decision", "text": "Free UK delivery now starts at £60, up from £45, from 1 October."},
    {"type": "decision", "text": "Irish orders ship DHL Express; mainland Europe goes by UPS Standard."},
    {"type": "preference", "text": "Report money in pounds with no pence above £1,000."},
    {"type": "insight", "text": "Wedding venues order most in February and March, about a month before the season."},
    {"type": "followup", "text": "Chase the B-size glass blank reorder with the supplier on Friday."},
    {"type": "followup", "text": "Reply to Marlowe Events about a rotating gobo for their winter ball."},
    {"type": "followup", "text": "Send the revised trade price list to Orchard Lane Church."},
]
_r = post("/api/memory", {"op": "add", "items": _notes})
assert _r.status_code == 200 and not _r.json().get("not_kept"), _r.text
# One follow-up ticked off (op=set_status, the page's tick).
_mid = [m for m in _r.json()["memories"] if m["text"].startswith("Send the revised")][0]["id"]
assert post("/api/memory", {"op": "set_status", "id": _mid, "status": "done"}).status_code == 200
# Notes kept from chat (source "chat") and one from a member's chat waiting for an admin
# (held=True, by=...), through the store's own writer, as _chat_after calls it.
memory._add_memories([{"type": "insight", "text": "Customers who order a projector come back for a second gobo within 60 days about a third of the time."}],
                      source="chat")
memory._add_memories([{"type": "followup", "text": "Holloway Theatre wants a quote for twelve steel gobos before March."}],
                      source="chat", held=True, by="Owen Castellano")
# Spread the Added dates over the summer (b): the same list, rewritten by its writer.
_mem = memory._load_memory()
for k, m in enumerate(_mem):
    t = _iso(_NOW - _td(days=70 - 7 * k, hours=k))
    m["created"] = m["updated"] = t
memory._write_memory(_mem)

# ---------------------------------------------------------------- Memory: store knowledge (b) + (a)
# As t_reading_the_store_knowledge_takes_no_ai_slot_and_it_can_be_corrected: a learned
# copy through _save_knowledge, then a person's correction through /api/learn op=save.
_KNOW = ("## What the business sells\nLED gobo projectors for indoor and outdoor use, custom glass and steel "
         "gobos made to order, and rotating effect wheels.\n\n## Who buys\n- Wedding and event planners\n"
         "- Theatres and schools\n- Shops and shopping centres\n- Warehouses (projected floor signs)\n\n"
         "## How it sells\nOnline, with trade accounts on 30-day terms. Every custom gobo starts with an "
         "artwork proof.\n\n## Delivery\nUK next day for stock items; custom gobos ship three to five working "
         "days after the proof is approved. Ships to Ireland and Europe.\n\n## Tone\nPlain, helpful and practical.")
knowledge._save_knowledge(_KNOW.replace("five", "six"), ["https://halden-lighting.example.org/",
                        "https://halden-lighting.example.org/pages/about",
                        "https://halden-lighting.example.org/collections/custom-gobos",
                        "https://halden-lighting.example.org/pages/delivery"])
_k = knowledge._load_knowledge(); _k["learned_at"] = _iso(_NOW - _td(days=36))
jsonstore._write_json_store(knowledge.KNOWLEDGE_PATH, None, _k)
assert post("/api/learn", {"op": "save", "knowledge": _KNOW}).status_code == 200

# ---------------------------------------------------------------- Memory: tracked changes (b)
# Items in the shape /api/impact op=add writes ({id, text, source, baseline, started_at,
# status, by_uid, by}; a concluded one adds concluded_at and final). The open ones are
# measured against the live 28-day snapshot the read takes from the (fake) Shopify, so
# their baselines are set from that snapshot when it has figures.
impact._impact_snap_cache.clear()
impact._write_impact([{"id": "probe", "text": "probe", "status": "tracking", "baseline": {}}])
_cur = post("/api/impact", {}).json().get("current") or {}
impact._impact_snap_cache.clear()
_rev, _ord = _cur.get("revenue_28d") or 0, _cur.get("orders_28d") or 0
def _base(days_ago, pct_rev, pct_ord):
    if _rev and _ord:
        return {"at": _iso(_NOW - _td(days=days_ago)), "revenue_28d": round(_rev / (1 + pct_rev / 100), 2),
                "orders_28d": max(1, round(_ord / (1 + pct_ord / 100)))}
    return {"at": _iso(_NOW - _td(days=days_ago)), "revenue_28d": 6420.0, "orders_28d": 48}
_b1, _b2 = _base(21, 9, 6), _base(9, -3, 2)
impact._write_impact([
    {"id": _sec.token_hex(5), "text": "Add a spare-gobo bundle to every projector page", "source": "copilot",
     "baseline": _b1, "started_at": _b1["at"], "status": "tracking", "by_uid": _WS_MASTER, "by": "Cameron"},
    {"id": _sec.token_hex(5), "text": "Send a reorder reminder to trade accounts after 90 days", "source": "copilot",
     "baseline": _b2, "started_at": _b2["at"], "status": "tracking", "by_uid": _WSU["priya"], "by": "Priya Nandakumar"},
    {"id": _sec.token_hex(5), "text": "Move delivery times above the fold on custom gobo pages", "source": "copilot",
     "baseline": {"at": _iso(_NOW - _td(days=88)), "revenue_28d": 5210.0, "orders_28d": 41},
     "started_at": _iso(_NOW - _td(days=88)), "status": "concluded",
     "concluded_at": _iso(_NOW - _td(days=32)),
     "final": {"at": _iso(_NOW - _td(days=32)), "revenue_28d": 5815.0, "orders_28d": 45},
     "by_uid": _WS_MASTER, "by": "Cameron"},
])

# ---------------------------------------------------------------- Skills (a) + (b)
# /api/skills op=add, as t_memory_and_skills_routes_edit_refuse_and_fail_honestly (and the
# file-upload form of it, "file", which only the master may send).
_SK = [
    {"title": "Quoting custom gobos", "file": "quoting-custom-gobos.md",
     "when": "Someone asks for a price on a custom glass or steel gobo, or sends artwork.",
     "content": "# Quoting custom gobos\n\nAsk for the projector model first: the gobo size follows from it, and "
                "the size list has the answer.\n\n## Prices\n\n| Gobo | Size | Price |\n|---|---|---|\n"
                "| Steel, one colour | B | £38 |\n| Glass, one colour | B | £62 |\n| Glass, full colour | B | £95 |\n"
                "| Glass, full colour | E | £120 |\n\n## Steps\n\n1. Find the size from the projector model.\n"
                "2. Say whether steel or glass suits the artwork (photos and gradients need glass).\n"
                "3. Give the price and the lead time from proof approval.\n"
                "4. Offer the trade discount from the account's third order."},
    {"title": "Replying to trade accounts",
     "when": "Drafting an email to a trade customer.",
     "content": "Open with the account's first name. Quote trade prices (15% off glass from the third order). "
                "Say the 30-day terms once, near the end. Sign off with the sender's own sign-off."},
    {"title": "Chasing overdue invoices",
     "content": "Step 1: wait seven days past terms. Step 2: a friendly reminder with the invoice attached. "
                "Step 3: after fourteen more days, a phone call from an admin. Never stop an order that is "
                "already made over a late invoice."},
    {"title": "House style", "always": True,
     "content": "British English. Plain words, short sentences. Money in pounds. Dates as 3 Oct 2026."},
]
for sk in _SK:
    _r = post("/api/skills", dict({"op": "add"}, **sk))
    assert _r.status_code == 200, _r.text
_skills = {s["title"]: s["id"] for s in _r.json()["skills"]}
# Reactor's reading of the first skill (the {when, rules, examples, questions} run_skill_reading
# returns), kept with the skill's own writer.
skillbook._save_skill_reading(_skills["Quoting custom gobos"], {
    "when": "A customer asks what a custom gobo costs, or sends artwork for one.",
    "rules": ["Ask for the projector model before quoting.",
              "Use glass for photos and gradients; steel for one-colour logos.",
              "Give the lead time from proof approval, never a date.",
              "Offer 15% trade pricing from the third order."],
    "examples": ["How much is a glass gobo of our logo?", "Can you quote four steel gobos for a Kestrel Mini 200?"],
    "questions": ["Is the £120 full-colour E size price the same for trade?"]}, _WS_MASTER)

# ---------------------------------------------------------------- Guide: requests (a)
# /api/updates op=request and op=state, as t_a_request_says_whether_it_was_emailed_and_the_asker_sees_the_answer.
_REQ = [
    (_WSS["hattie"], "Print the day sheet grouped by glass size", "Saves walking the bench twice for B and E blanks.", "labels", ("planned", "Next week, with the size list's own groups.")),
    (_WSS["owen"], "Show a deal's last email on the CRM card", "", "crm", None),
    (None, "Export tracked changes as a spreadsheet", "For the quarterly review.", "memory", ("shipped", "On Memory now: Export under Tracked changes.")),
    (_WSS["jonah"], "Bigger Print button on a phone", "Hard to hit with gloves on.", "labels", None),
    (_WSS["lena"], "Clock in from the Production Manager", "", "team", ("declined", "Clocking in stays on the account menu, so it is one place for everyone.")),
    (_WSS["priya"], "Warn when a loan unit is overdue by a week", "", "loans", None),
]
for sess, title, detail, where, state in _REQ:
    body = {"op": "request", "title": title, "detail": detail, "where": where}
    _r = post_s(sess, "/api/updates", body) if sess else post("/api/updates", body)
    assert _r.status_code == 200, _r.text
    if state:
        assert post("/api/updates", {"op": "state", "id": _r.json()["item"]["id"], "state": state[0],
                                     "note": state[1]}).status_code == 200
# Spread the asked dates (b): the feedback store, through its writer.
_fb = updates._load_feedback()
for k, it in enumerate(reversed(_fb["items"])):
    it["at"] = _iso(_NOW - _td(days=20 - 3 * k, hours=2))
    if it.get("state_at"): it["state_at"] = _iso(_NOW - _td(days=18 - 3 * k))
updates._write_feedback(_fb)

# The master has read all but the two newest release notes (op=seen, what markSeen sends):
# What's new marks those two New and the Guide carries its dot.
_rel = len(updates._load_changelog())
assert post("/api/updates", {"op": "seen", "releases": max(0, _rel - 2)}).status_code == 200

# ---------------------------------------------------------------- Chat (c), then the browser's own storage
# Conversations live only in the browser (localStorage sc_convos_v1); the server keeps
# none. Each answer is made by the REAL /api/chat route (run_chat, _coerce_structured,
# _note_skills_applied, _chat_after) with the one outside call, the Anthropic model,
# stood in for by a fake _xcreate that returns a present_response tool call (and, for
# one answer, first a read_skill call, which run_chat answers from the skills store).
_ANSWERS = {
    "How did September sales compare with August?": {
        "summary": "September was up on August: more orders, at a slightly lower average.\n"
                   "| Month | Orders | Revenue | Average order |\n|---|---|---|---|\n"
                   "| August | 41 | £5,210 | £127 |\n| September | 48 | £6,420 | £134 |\n\n"
                   "Most of the rise came from wedding venues booking early for spring.",
        "metrics": [{"label": "Revenue", "value": "£6,420", "delta": "+23%", "trend": "up"},
                    {"label": "Orders", "value": "48", "delta": "+17%", "trend": "up"},
                    {"label": "Average order", "value": "£134", "delta": "+6%", "trend": "up"}],
        "insights": [{"type": "win", "title": "Wedding venues booked early", "detail": "Nine venue orders in September against three in August."},
                     {"type": "warning", "title": "Two custom gobos waited on artwork", "detail": "Both are over a week from order with no proof approved."}],
        "sections": [{"title": "By product", "body": "- Custom glass gobos: 21 orders\n- LED projectors: 14 orders\n- Steel gobos: 9 orders\n- Effect wheels: 4 orders"},
                     {"title": "By sector", "body": "- Weddings and events: 46%\n- Theatres and schools: 22%\n- Retail: 18%\n- Warehouses: 14%"}],
        "actions": [{"text": "Email the two customers whose artwork is still waiting", "priority": "high"},
                    {"text": "Feature the spring wedding bundle on the home page", "priority": "medium"}],
        "followups": ["Which products drove the rise?", "How does this compare with last September?"]},
    "And which customers ordered most?": {
        "summary": "Three trade accounts made up a third of September's revenue.",
        "metrics": [{"label": "Top three share", "value": "34%"}],
        "sections": [{"title": "Top customers", "body": "- Marlowe Events: 6 orders, £980\n- Cobalt Stage Hire: 4 orders, £712\n- Brightwater Venues: 3 orders, £498"}],
        "followups": ["Who has not ordered for 90 days?"]},
    "Quote four glass gobos for a Kestrel Mini 200": {
        "summary": "Four full-colour B size glass gobos come to £380, five working days from proof approval.",
        "sections": [{"title": "How it was worked out", "body": "- Kestrel Mini 200 takes a B size gobo\n- Glass, full colour, B size: £95 each\n- Lead time counts from proof approval"}],
        "actions": [{"text": "Ask for the artwork as a PDF or vector file", "priority": "high"}],
        "skills_applied": ["Quoting custom gobos"],
        "followups": ["What would steel cost instead?"]},
    "Which products are low on stock?": {
        "summary": "Two projectors are under their usual two weeks of cover.",
        "insights": [{"type": "warning", "title": "60W LED projector", "detail": "4 left, about 9 days of sales."},
                     {"type": "opportunity", "title": "Effect wheels", "detail": "Plenty in stock and rising interest: worth a feature."}],
        "followups": ["When did we last reorder the 60W?"]},
    "Draft a reply to Orchard Lane Church about delivery": {
        "summary": "Here is a short reply you can send.\n"
                   "Thanks for your order. Your gobos are made and will leave us tomorrow by DPD Next Day, "
                   "so they should be with you on Thursday.",
        "skills_applied": ["Replying to trade accounts"]},
}
def _block(**k): return _types.SimpleNamespace(**k)
async def _fake_xcreate(client, **kwargs):
    msgs = kwargs.get("messages") or []
    asked = [m for m in msgs if m.get("role") == "user" and isinstance(m.get("content"), str)][-1]["content"]
    last = msgs[-1]
    first_round = isinstance(last.get("content"), str)
    if asked.startswith("Quote four glass") and first_round:
        return _block(content=[_block(type="tool_use", name="read_skill", id="toolu_seed_read",
                                      input={"title": "Quoting custom gobos"})], stop_reason="tool_use")
    return _block(content=[_block(type="tool_use", name="present_response", id="toolu_seed_present",
                                  input=_j.loads(_j.dumps(_ANSWERS[asked])))], stop_reason="tool_use")
_real_xcreate = claude._xcreate
claude._xcreate = _fake_xcreate
def _turn(resp, at):
    return {"role": "assistant", "structured": resp.get("structured"), "model": resp.get("model"),
            "deep": resp.get("deep"), "fell_back": resp.get("fell_back"), "data_used": resp.get("data_used"),
            "at": at, "not_kept": resp.get("not_kept"), "held": resp.get("held"),
            "followups_closed": resp.get("followups_closed"), "followups_maybe": resp.get("followups_maybe")}
def _text(s):   # structuredToText, as the page sends an earlier answer back
    out = [s.get("summary") or ""] + [m["label"] + ": " + m["value"] for m in s.get("metrics") or []]
    return "\n".join(x for x in out if x)
_WS_CONVOS = []
try:
    for k, (qs, hours_ago) in enumerate(((["How did September sales compare with August?", "And which customers ordered most?"], 2),
                                         (["Quote four glass gobos for a Kestrel Mini 200"], 26),
                                         (["Which products are low on stock?"], 50),
                                         (["Draft a reply to Orchard Lane Church about delivery"], 75))):
        t0 = _NOW - _td(hours=hours_ago)
        turns, hist = [], []
        for i, q in enumerate(qs):
            at_q = _iso(t0 + _td(minutes=3 * i)); at_a = _iso(t0 + _td(minutes=3 * i, seconds=40))
            hist.append({"role": "user", "content": q})
            _r = post("/api/chat", {"messages": hist, "deep": False, "skills": []})
            assert _r.status_code == 200, _r.text
            turns += [{"role": "user", "text": q, "at": at_q}, _turn(_r.json(), at_a)]
            hist.append({"role": "assistant", "content": _text(_r.json()["structured"])})
        ms = int((t0 + _td(minutes=3 * len(qs))).timestamp() * 1000)
        title = qs[0] if len(qs[0]) <= 60 else qs[0][:57] + "…"
        _WS_CONVOS.append({"id": "seedconvo" + str(k + 1), "title": title, "ts": ms - 60000, "updated": ms, "turns": turns})
finally:
    claude._xcreate = _real_xcreate
WS_SEED.update({"master": _WS_MASTER, "users": _WSU, "convos": _WS_CONVOS})
# What the browser needs: the owner stamp (claimLocalCache keeps the cache only for the
# signed-in account) and the conversations, for a context init script.
with open(SCRATCH + "/workspace_browser_seed.json", "w") as _fh:
    _j.dump({"localStorage": {"sc_cache_owner_v1": _WS_MASTER, "sc_convos_v1": _j.dumps(_WS_CONVOS)}}, _fh)
print("workspace seed: master", _WS_MASTER, "accounts", len(_WSU) + 1, "convos", len(_WS_CONVOS),
      "browser seed", SCRATCH + "/workspace_browser_seed.json", flush=True)
