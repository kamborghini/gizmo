# ---- Stock in Reactor: quarters, settings, warnings, history (plan 2a) ---------
# The stock sheet's overview: closing a quarter, comparing two, the settings,
# "since you were last here" per person, warnings, the history searched and
# each line's own, and the outlook in real days (flaw 8). Invented data only.

def _stock_view(path, op, **body):
    r = post("/api/stock/" + path, dict(body, op=op))
    return r, (r.json() if r.headers.get("content-type", "").startswith("application/json") else {})

@test
def t_closing_a_stock_quarter_rolls_every_line_and_keeps_its_closing_list():
    _stock_live()
    before = {k: v["current"] for k, v in stock_store.load_items()["items"].items()}
    r, d = _stock_view("quarters", "close", new_label="Quarter two")
    eq(r.status_code, 200, r.text)
    eq((d["closed"], d["opened"], d["rolled"], d["closing_value_gbp"]), ("Quarter one", "Quarter two", 3, 17.5))
    closed, opened = stock_store.load_periods()["periods"]
    eq((closed["closing_value"], closed["closing_units"], closed["closing_skus"]), (17.5, 20, 3))
    eq(len(closed["closing_data"]), 3, "every line as it closed")
    eq((opened["label"], opened["closed_at"]), ("Quarter two", None))
    for k, it in stock_store.load_items()["items"].items():
        eq((it["start"], it["received"], it["used"]), (before[k], 0, 0), "rolled: " + k)
    ok(stock_store.read_history()[-1]["detail"].startswith(
        "closed 'Quarter one' (£17.5, 20 units, 3 SKUs) -> opened 'Quarter two'; rolled 3 items"),
       stock_store.read_history()[-1]["detail"])
    eq([s["reason"] for s in stock_store.read_snapshots()], ["period_close", "period_open"])

@test
def t_a_stock_quarter_cannot_be_closed_twice_in_a_minute():
    _stock_live()
    eq(_stock_view("quarters", "close", new_label="Quarter two")[0].status_code, 200)
    r, d = _stock_view("quarters", "close", new_label="Quarter three")
    eq(r.status_code, 409, r.text)
    eq(len(stock_store.load_periods()["periods"]), 2, "closed once")

@test
def t_a_closed_stock_quarter_downloads_as_its_closing_list():
    _stock_live()
    _stock_view("quarters", "close", new_label="Quarter two")
    r, d = _stock_view("quarters", "csv", id=1)
    eq(r.status_code, 200, r.text)
    eq(d["filename"], "Quarter one.csv")
    lines = d["csv"].strip().split("\r\n")
    eq(lines[0], "Category,Sub Category,Size,Notes,Written Off,Start,Received,Used,Current,Unit Cost,Currency,"
                 "Supplier,Unit Cost GBP,Start Value,Used Value,Current Value")
    eq(len(lines), 4)
    doc = stock_store.load_periods()
    doc["periods"].append({"id": 5, "label": "Old quarter", "opened_at": "2025-01-01T00:00:00+00:00",
                           "closed_at": "2025-03-31T00:00:00+00:00", "closing_value": 1.0, "closing_units": 1,
                           "closing_skus": 1, "closing_used_value": 0.0, "note": "", "closing_data": None})
    stock_store.write_periods(doc)
    r, d = _stock_view("quarters", "csv", id=5)
    eq(r.status_code, 404, "no closing list to download")
    ok("closing list" in d["error"], d["error"])

@test
def t_stock_compare_any_two_quarters():
    _stock_live()
    _stock_view("quarters", "close", new_label="Quarter two")
    r, d = _stock_view("quarters", "compare")
    eq(r.status_code, 200, r.text)
    eq((d["left"]["label"], d["right"]["label"]), ("Quarter one (closed)", "Quarter two (live)"))
    eq(_stock_view("quarters", "compare", left=99)[0].status_code, 404)
    r, d = _stock_view("quarters", "list")
    eq((d["current"]["label"], [q["label"] for q in d["history"]]), ("Quarter two", ["Quarter one"]))

@test
def t_stock_settings_are_clamped_and_logged():
    _stock_live()
    eq(_stock_view("overview", "save_settings", low_stock_days=0)[1]["low_stock_days"], 1)
    eq(_stock_view("overview", "save_settings", low_stock_days=999)[1]["low_stock_days"], 365)
    eq(_stock_view("overview", "save_settings", fx_usd_gbp=0)[0].status_code, 400)
    r, d = _stock_view("overview", "save_settings", fx_usd_gbp=0.8)
    eq(d["fx_usd_gbp"], 0.8)
    eq(stock_store.load_settings()["meta"]["fx_usd_gbp"], "0.8")
    eq(stock_store.read_history()[-1]["detail"], "settings: USD->GBP 0.8")

@test
def t_since_you_were_last_here_in_stock_is_per_person_and_carries_on():
    _stock_live()
    me = (ensure_auth(), APP_AUTH["master"])[1]
    stock_store.write_people({"people": {"someone": me}, "logins": {"someone": {
        "id": 1, "created_at": None, "last_login": None, "prev_login": "2026-10-01T08:00:00"}}})
    doc = stock_store.load_settings()
    doc["meta"]["briefing_ack_someone"] = "2026-10-05T09:00:00+00:00"
    stock_store.write_settings(doc)
    stock_store.append_history([{"at": "2026-10-04T10:00:00", "user": "someone", "action": "update", "item_key": "",
                                 "field": "", "old_value": "", "new_value": "", "detail": "", "person": me},
                                {"at": "2026-10-06T10:00:00", "user": "someone", "action": "update", "item_key": "",
                                 "field": "", "old_value": "", "new_value": "", "detail": "", "person": me}])
    r, d = _stock_view("overview", "briefing")
    eq(r.status_code, 200, r.text)
    eq((d["since"][:16], d["edits"]), ("2026-10-05T09:00", 1), "the later of the old login and the old acknowledgement")
    eq(_stock_view("overview", "ack")[0].status_code, 200)
    d = _stock_view("overview", "briefing")[1]
    eq(d["edits"], 0, "after acknowledging, only what is new")
    ok(stock_store.load_settings()["acks"][me], "kept under the Reactor account")

@test
def t_dismissing_a_stock_alert_records_who():
    _stock_live()
    stock_store.write_alerts({"alerts": [{"id": 4, "at": "2026-10-01T10:00:00+00:00", "kind": "low_stock",
                                          "severity": "warning", "message": "Low stock", "item_key": "Glass|Blue|20|",
                                          "dismissed": False, "dismissed_by": ""}], "next_id": 5})
    eq([a["id"] for a in _stock_view("overview", "alerts")[1]["alerts"]], [4])
    eq(_stock_view("overview", "dismiss", id=4)[0].status_code, 200)
    a = stock_store.load_alerts()["alerts"][0]
    eq((a["dismissed"], a["dismissed_person"]), (True, APP_AUTH["master"]))
    ok(a["dismissed_by"], "by name")
    eq(_stock_view("overview", "alerts")[1]["alerts"], [])

@test
def t_stock_history_search_filters_and_pages():
    _stock_live()
    rows = [{"at": "2026-10-0%dT10:00:00+00:00" % n, "user": "someone", "action": a, "item_key": k, "field": "current",
             "old_value": "1", "new_value": "2", "detail": dt, "person": None}
            for n, (a, k, dt) in enumerate([("receive", "Glass|Blue|20|", "received 1 · inv X-1"),
                                            ("update", "Glass|Red|30|", "manual edit"),
                                            ("receive", "Glass|Red|30|", "received 2 · inv X-2"),
                                            ("update", "Glass|Blue|20|", "counted"),
                                            ("update", "Glass|Red|30|", "counted")], start=1)]
    stock_store.append_history(rows)
    eq([h["detail"] for h in _stock_view("history", "search", action="receive")[1]["rows"]],
       ["received 2 · inv X-2", "received 1 · inv X-1"], "newest first")
    eq(len(_stock_view("history", "search", q="blue")[1]["rows"]), 2)
    eq(len(_stock_view("history", "search", start="2026-10-02", end="2026-10-03")[1]["rows"]), 2)
    d = _stock_view("history", "search", limit=2)[1]
    eq((len(d["rows"]), d["more"]), (2, True))
    d2 = _stock_view("history", "search", limit=2, before=d["rows"][-1]["id"])[1]
    eq([h["id"] for h in d2["rows"]], [3, 2], "the next page")

@test
def t_a_stock_line_history_follows_its_renames():
    _stock_live()
    stock_store.append_history([{"at": "2026-10-01T10:00:00+00:00", "user": "someone", "action": "update",
                                 "item_key": "Glass|Red|30|", "field": "current", "old_value": "10", "new_value": "12",
                                 "detail": "manual edit", "person": None}])
    post("/api/stock/sheet", {"op": "edit", "id": 9, "changes": {"size": "31"}})
    post("/api/stock/sheet", {"op": "edit", "id": 9, "changes": {"current": 11}})
    r, d = _stock_view("history", "item", id=9)
    eq(r.status_code, 200, r.text)
    eq([(h["field"], h["item_key"]) for h in d["history"]],
       [("current", "Glass|Red|31|"), ("key", "Glass|Red|31|"), ("size", "Glass|Red|30|"), ("current", "Glass|Red|30|")],
       "its rows under both its names, newest first")

@test
def t_the_stock_item_sheet_has_its_forecast_and_lead_time():
    _stock_live()
    post("/api/stock/suppliers", {"op": "save", "supplier": "Invented Glass Co", "lead_days": 7})
    d = _stock_view("history", "item", id=3)[1]
    eq((d["item"]["id"], d["lead_days"]), (3, 7))
    eq(d["forecast"]["basis"], "run-rate", "its own forecast")

@test
def t_the_stock_outlook_counts_real_days():
    _stock_live()
    for n in range(5):
        stock_store.append_snapshot({"taken_at": "2026-10-%02dT00:00:00+00:00" % (1 + 2 * n), "reason": "scheduled",
                                     "by_user": "system", "note": "", "totals": {"active_value_gbp": 100 + 20 * n},
                                     "items": []})
    d = _stock_view("overview", "outlook")[1]
    eq((d["per_day"], d["projected"], d["days"]), (10.0, 480.0, 30), "£10 a day, thirty days on")

@test
def t_closing_a_stock_quarter_raises_no_false_value_swing():
    """The opening snapshot is compared with the closing one taken in the same
    change, as the stock app did, so a close never reports a swing twice."""
    _stock_live()
    stock_store.append_snapshot({"taken_at": "2026-10-01T00:00:00+00:00", "reason": "scheduled", "by_user": "system",
                                 "note": "", "totals": {"active_value_gbp": 100.0}, "items": []})
    _stock_view("quarters", "close", new_label="Quarter two")
    eq([a["kind"] for a in stock_store.load_alerts()["alerts"] if not a["item_key"]], ["large_change"],
       "the swing since the last snapshot, once")
