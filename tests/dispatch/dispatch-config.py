# =========================== routes: config =================================
@test
def t_config_creds_write_only():
    r = post("/api/shipping/config", {"op": "set", "meter_number": "METER-9999", "key": "KEY-abc", "password": "PW-xyz",
                                      "origin": {"street": "1 Mill St", "postcode": "LS1 1AA", "country": "GB", "city": "Leeds", "company": "PI"}})
    eq(r.status_code, 200, r.text)
    body = r.json()
    dump = json.dumps(body)
    ok("METER-9999" not in dump and "KEY-abc" not in dump and "PW-xyz" not in dump, "no creds echoed")
    eq(body["config"]["connected"], True, "connected")
    eq(body["config"]["meter_last4"], "9999", "meter last4")
    eq(body["config"]["has_key"], True, "has key flag")
    eq(body["config"]["has_password"], True, "has password flag")
    disk = json.load(open(SCRATCH + "/wo_secret.json"))
    eq(disk["meter"], "METER-9999", "meter persisted")
    eq(disk["key"], "KEY-abc", "key persisted")

@test
def t_config_get_no_secrets():
    r = post("/api/shipping/config", {"op": "get"})
    body = r.json()["config"]
    ok("key" not in body and "password" not in body and "meter" not in body, "no raw secrets")
    eq(body["origin"]["city"], "Leeds", "origin persisted")
    eq(body["plugin_code"], "Web_Service", "default plugin")

@test
def t_validate_route():
    r = post("/api/shipping/validate", {})
    eq(r.status_code, 200, r.text)
    eq(r.json()["ok"], True, "validates via test quote")

