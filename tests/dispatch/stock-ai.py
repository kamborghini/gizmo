# ---- Stock in Reactor: AI and the chat (plan 2b) --------------------------------
# The stock sheet's insights, a PDF invoice read into a delivery (never
# booked), a purchase order note, through Reactor's own AI client and its
# day's budget; read-only stock tools in the chat. Invented data only.

def _stock_ai_stand_in(answer=None, raises=None, stop="tool_use"):
    """claude._xcreate replaced: records each request, answers a tool call
    (a dict), text (a string), or raises; `stop` is why the answer ended."""
    asked = []
    class Block:
        def __init__(self, kind, name=None, data=None, text=None):
            self.type, self.name, self.input, self.text, self.id = kind, name, data, text, "tu1"
    class Reply:
        def __init__(self, blocks):
            self.content, self.stop_reason, self.usage = blocks, stop, None
    async def fake(client, **kwargs):
        asked.append(kwargs)
        if raises:
            raise raises
        if isinstance(answer, str):
            return Reply([Block("text", text=answer)])
        name = (kwargs.get("tool_choice") or {}).get("name") or (kwargs.get("tools") or [{}])[0].get("name")
        return Reply([Block("tool_use", name=name, data=answer)])
    real = claude._xcreate
    claude._xcreate = fake
    return asked, lambda: setattr(claude, "_xcreate", real)

def _stock_ai(op, **body):
    r = post("/api/stock/ai", dict(body, op=op))
    return r, (r.json() if r.headers.get("content-type", "").startswith("application/json") else {})

@test
def t_stock_insights_are_asked_once_and_kept():
    _stock_live()
    asked, restore = _stock_ai_stand_in({"headline": "Blue 20 runs low — order soon", "health_score": 140,
                                         "findings": [{"title": "Low cover", "detail": "Blue 20 has days left",
                                                       "severity": "warning", "metric": "6 units"}],
                                         "actions": [{"title": "Reorder", "detail": "Order Blue 20", "priority": "high"}]})
    try:
        r, d = _stock_ai("insights")
        eq(r.status_code, 200, r.text)
        eq(len(asked), 1)
        eq(asked[0]["tool_choice"]["name"], "record_insights")
        ok("active_stock_value_gbp" in json.dumps(asked[0]["messages"]), "the sheet's figures are sent")
        ok("for the shop," in asked[0]["system"], "the business is called the shop in the prompt")
        eq(d["health_score"], 100, "kept within 0 to 100")
        ok("—" not in d["headline"], "no dashes reach a person")
        kept = post("/api/stock/overview", {"op": "insights"}).json()
        eq(kept["result"], d, "seen again later")
        ok(kept["at"], kept)
    finally:
        restore()

@test
def t_a_stock_invoice_is_read_but_nothing_is_booked():
    _stock_live()
    before = open(stock_store.STOCK_ITEMS_PATH, "rb").read()
    asked, restore = _stock_ai_stand_in({"supplier": "Invented Glass Co", "invoice_no": "INV-9", "invoice_date": "2026-10-20",
                                         "lines": [{"description": "Blue 20", "qty": 4, "unit_cost": 1.2, "currency": "GBP",
                                                    "key": "Glass|Blue|20|", "confidence": 1.5},
                                                   {"description": "Carriage", "qty": 0, "key": None, "confidence": 1},
                                                   {"description": "Mystery", "qty": 2, "key": "Not|A|Line|", "confidence": 0.4}]})
    try:
        pdf = base64.b64encode(b"%PDF-1.4 invented").decode()
        r, d = _stock_ai("read_invoice", pdf_base64=pdf)
        eq(r.status_code, 200, r.text)
        eq([(l["id"], l["qty"], l["confidence"]) for l in d["lines"]], [(3, 4, 1.0), (None, 2, 0.4)],
           "a key not on the sheet is left unmatched; nothing of 0 is a line")
        eq((d["invoice_no"], d["unmatched"]), ("INV-9", 1))
        eq(asked[0]["tool_choice"]["name"], "record_delivery")
        eq(asked[0]["messages"][0]["content"][0]["type"], "document", "the PDF goes as a document")
        eq(open(stock_store.STOCK_ITEMS_PATH, "rb").read(), before, "nothing is booked by reading")
    finally:
        restore()

@test
def t_a_stock_invoice_that_is_not_a_pdf_is_refused():
    _stock_live()
    asked, restore = _stock_ai_stand_in({})
    try:
        eq(_stock_ai("read_invoice", pdf_base64=base64.b64encode(b"hello").decode())[0].status_code, 400)
        eq(_stock_ai("read_invoice", pdf_base64="not base64 at all!")[0].status_code, 400)
        big = base64.b64encode(b"%PDF-" + b"0" * (9 * 1024 * 1024)).decode()
        ok(_stock_ai("read_invoice", pdf_base64=big)[0].status_code in (400, 413), "over 9 MB")
        eq(asked, [], "refused before any AI call")
    finally:
        restore()

@test
def t_the_stock_po_note_sends_only_the_allowed_fields():
    _stock_live()
    asked, restore = _stock_ai_stand_in("Hello,\nPlease send 20 of Blue 20.\nThanks")
    try:
        r, d = _stock_ai("po_note", supplier="Invented Glass Co", currency="GBP", native_total=24, gbp_total=24,
                         bank="11-22-33 12345678",
                         lines=[{"item": "Blue 20", "qty": 20, "unit_cost": 1.2, "secret": "keep out"}])
        eq(r.status_code, 200, r.text)
        ok(d["note"].startswith("Hello"), d)
        sent = json.dumps(asked[0]["messages"])
        ok("Blue 20" in sent and "11-22-33" not in sent and "keep out" not in sent, "only the allowed fields")
    finally:
        restore()

@test
def t_stock_ai_over_the_days_budget_says_so():
    _stock_live()
    asked, restore = _stock_ai_stand_in(raises=RuntimeError("Reactor has used today's AI budget, so it will answer again tomorrow."))
    try:
        r, d = _stock_ai("insights")
        eq(r.status_code, 429, r.text)
        ok("budget" in d["error"], d)
    finally:
        restore()
    _stock_live(live=False)
    asked, restore = _stock_ai_stand_in({})
    try:
        eq(_stock_ai("insights")[0].status_code, 409, "nothing asked before the move")
        eq(asked, [])
    finally:
        restore()

def _stock_chat(name, args=None, uid=""):
    """One chat tool call through the chat's own registry and its tab gate."""
    return run_async(assistant._build_dispatch(assistant._chat_registry, lambda: uid)(name, args or {}))

def _stock_files():
    return {p: open(p, "rb").read() for p in sorted(glob.glob(SCRATCH + "/stock_*"))}

@test
def t_the_chat_reads_stock_and_never_changes_it():
    names = ("stock_levels", "stock_item_history", "stock_movements", "stock_reorder")
    offered = {t["name"]: t for t in assistant._chat_tools}
    for name in names:
        ok(name in offered and offered[name]["description"], name + " is offered to the chat, described")
        eq(assistant._TOOL_TABS.get(name), "stock", name + " is gated on the stock tab")
    _stock_live()
    recent = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    long_ago = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
    stock_store.append_history([
        _history_row(at=long_ago, action="receive", item_id=9, item_key="Glass|Red|30|", old_value="2", new_value="102"),
        _history_row(at=recent, action="receive", item_id=3, old_value="2", new_value="8", detail="delivery"),
        _history_row(at=recent, action="use", item_id=3, old_value="8", new_value="7", detail="made #1001 · used 1"),
        _history_row(at=recent, action="update", item_id=3, old_value="7", new_value="6", detail="counted"),
        _history_row(at=recent, action="update", item_id=3, field="used", old_value="4", new_value="5",
                     detail="counted down 1, recorded as usage"),
        _history_row(at=recent, action="update", item_id=3, old_value="6", new_value="7", detail="manual edit"),
        _history_row(at=recent, action="update", item_id=9, item_key="Glass|Red|30|", old_value="12", new_value="10",
                     detail="counted"),
        _history_row(at=recent, action="update", item_id=9, item_key="Glass|Red|30|", field="used", old_value="30",
                     new_value="32", detail="counted down 2 \u2014 recorded as usage"),    # as the stock app wrote it
        _history_row(at=recent, action="update", item_id=3, field="supplier", old_value="", new_value="Invented Glass Co")])
    before = _stock_files()

    levels = json.loads(_stock_chat("stock_levels", {"query": "blue 20"}))
    eq(sorted(l["id"] for l in levels["lines"]), [3, 7], "both Blue 20 lines, not Red 30")
    blue = next(l for l in levels["lines"] if l["id"] == 3)
    eq((blue["current"], blue["on_order"], blue["value_gbp"]), (6, 0, 7.5))
    eq(blue["cover_days"], 135, "6 on the shelf at 4 a quarter")
    eq(json.loads(_stock_chat("stock_levels", {"query": "invented glass"}))["matched"], 1, "by supplier")

    hist = json.loads(_stock_chat("stock_item_history", {"item": "3"}))
    eq(hist["line"]["id"], 3)
    eq([r["action"] for r in hist["rows"]], ["update"] * 4 + ["use", "receive"], "newest first, its own lines")
    ok("Several" in _stock_chat("stock_item_history", {"item": "blue 20"}), "two lines match: asked which")
    ok("No stock line" in _stock_chat("stock_item_history", {"item": "green 99"}))

    moves = json.loads(_stock_chat("stock_movements", {"days": 30}))
    eq([(l["id"], l["received"], l["used"], l["corrected"], l["net"]) for l in moves["lines"]],
       [(3, 6, 2, 1, 5), (9, 0, 2, 0, -2)],
       "a count that went down is usage, as the sheet records it; a manual edit is a correction; the old "
       "delivery is outside the window; the supplier edit moves no stock")

    reorder = json.loads(_stock_chat("stock_reorder"))
    eq([i["key"] for s in reorder["suppliers"] for i in s["items"]], ["Glass|Blue|20|"], "6 against a point of 10")

    eq(_stock_files(), before, "the chat wrote nothing")
    ok("Invalid arguments" in _stock_chat("stock_movements", {"days": 0}))
    _stock_live(live=False)
    for name, args in (("stock_levels", {}), ("stock_item_history", {"item": "3"}),
                       ("stock_movements", {}), ("stock_reorder", {})):
        eq(_stock_chat(name, args), "The stock sheet has not moved into Reactor yet.", name)

@test
def t_the_chat_refuses_stock_without_the_tab():
    _stock_live()
    def go():
        ensure_auth()
        uid, _sess, _ = ready_user("Pia", "pia")
        post("/api/team/user", {"op": "tabs", "id": uid, "tabs": ["chat"]})
        out = _stock_chat("stock_levels", {"query": "blue"}, uid=uid)
        ok(out.startswith("Refused") and "the stock sheet" in out and "Blue" not in out, out[:160])
    with_accounts(go)

@test
def t_the_unlimited_stock_rule_speaks_only_of_shopify_products():
    rule = ("Our Shopify products carry unlimited stock: give no inventory or restock advice about them. "
            "The glass stock sheet is tracked separately and its tools may be used.")
    block = store_profile._profile_to_system({"prefs": {"track_inventory": False}})
    ok(rule in block, block)
    ok("We carry unlimited stock" not in block, "the old blanket rule is gone")
    ok(rule not in store_profile._profile_to_system({"prefs": {"track_inventory": True}}), "only when asked for")
    ok("unlimited stock means give no restock advice)" not in prompts.SYSTEM_PROMPT, "the system prompt narrowed too")
    ok("Shopify products" in prompts.SYSTEM_PROMPT)

@test
def t_the_stock_ai_has_room_to_think_and_says_when_cut_short():
    """The model thinks on every request and its thinking counts against the
    answer's room: each call asks for an effort and leaves room for it, and
    an answer cut short is said, never shown as a whole one."""
    _stock_live()
    asked, restore = _stock_ai_stand_in({"headline": "Fine", "health_score": 80, "findings": [], "actions": []})
    try:
        _stock_ai("insights")
        _stock_ai("read_invoice", pdf_base64=base64.b64encode(b"%PDF-1.4 invented").decode())
    finally:
        restore()
    asked2, restore = _stock_ai_stand_in("Hello,\nPlease send 20 of Blue 20.\nThanks")
    try:
        _stock_ai("po_note", supplier="Invented Glass Co", lines=[{"item": "Blue 20", "qty": 20}])
    finally:
        restore()
    for req in asked + asked2:
        ok((req.get("output_config") or {}).get("effort"), "an effort is asked for")
    ok(asked[0]["max_tokens"] >= 12000 and asked[1]["max_tokens"] >= 12000, "room for 200 invoice lines and thinking")
    ok(asked2[0]["max_tokens"] >= 4000, "room for a note and thinking")
    ok(max(a["max_tokens"] for a in asked + asked2) <= 21333, "within what a request without streaming may ask")
    asked3, restore = _stock_ai_stand_in("Hello,\nPlease send", stop="max_tokens")
    try:
        r, d = _stock_ai("po_note", supplier="Invented Glass Co", lines=[{"item": "Blue 20", "qty": 20}])
        eq(r.status_code, 502, r.text)
        ok("note" not in d, "a note cut short is not handed out as a whole one")
    finally:
        restore()
