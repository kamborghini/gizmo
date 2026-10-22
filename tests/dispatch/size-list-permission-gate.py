# ---- Size-list permission gate, at the route -------------------------------
# The helper (_may_edit_sizes) was already covered. These exercise the ROUTE,
# because a gate is only worth what the HTTP layer actually enforces - and this
# one decides the glass a real order is cut from.

@test
def t_saving_a_size_rule_needs_a_session():
    r = bare("/api/gobo-sizes/rule",
             {"op": "set", "manufacturer": "Showtec", "model": "NoAuth", "size": "37.5"})
    eq(r.status_code, 401, "no session, no entry")


@test
def t_a_member_without_the_grant_is_refused_by_the_route():
    """Seeing the Labels tab is not the same as deciding what the bench cuts."""
    def go():
        ensure_auth()
        _uid, sess, _pw = ready_user("Sam Bench", "sambench")
        r = post_s(sess, "/api/gobo-sizes/rule",
                   {"op": "set", "manufacturer": "Showtec", "model": "Ungranted", "size": "37.5"})
        eq(r.status_code, 403, r.text)
        ok("size list" in r.json().get("error", ""), "and told where the grant comes from")
        # The refusal must be real: nothing reached the file.
        rows = size_list._gobo_rule_rows("override")
        eq(any(x["Model"] == "Ungranted" for x in rows), False,
           "a refused request writes nothing")
    with_accounts(go)


@test
def t_the_same_member_can_save_once_an_admin_grants_it():
    def go():
        ensure_auth()
        uid, sess, _pw = ready_user("Pat Trusted", "pattrusted")
        eq(post_s(sess, "/api/gobo-sizes/rule",
                  {"op": "set", "manufacturer": "Showtec", "model": "Granted", "size": "37.5"}
                  ).status_code, 403, "refused before the grant")
        eq(post("/api/team/user", {"op": "sizes", "id": uid, "can_sizes": True}).status_code, 200)
        r = post_s(sess, "/api/gobo-sizes/rule",
                   {"op": "set", "manufacturer": "Showtec", "model": "Granted", "size": "37.5"})
        eq(r.status_code, 200, r.text)
        eq(r.json().get("resolves"), True, "and the model now resolves")
    with_accounts(go)


@test
def t_an_admin_holds_the_grant_by_rank():
    """Admins are not toggled - the team op refuses to, so the route must let
    them through on rank alone or the two disagree."""
    def go():
        ensure_auth()
        r = post("/api/gobo-sizes/rule",
                 {"op": "set", "manufacturer": "Showtec", "model": "ByRank", "size": "25"})
        eq(r.status_code, 200, r.text)
    with_accounts(go)


@test
def t_the_rules_route_reports_the_grant_for_the_asking_account():
    """The button is hidden on this answer, so a wrong answer either hides a
    control that works or offers one the server will refuse."""
    def go():
        ensure_auth()
        _uid, sess, _pw = ready_user("Ida Reader", "idareader")
        mine = post("/api/gobo-sizes/rules", {}).json()
        eq(mine.get("can_edit"), True, "the master can edit")
        theirs = post_s(sess, "/api/gobo-sizes/rules", {}).json()
        eq(theirs.get("can_edit"), False, "a plain member cannot")
        ok(isinstance(theirs.get("overrides"), list),
           "but may still READ the rules - knowing why a model resolves is part "
           "of reading the size check")
    with_accounts(go)


@test
def t_the_route_refuses_a_size_that_is_not_a_size():
    """Whatever is stored is what the bench reads off the label."""
    def go():
        ensure_auth()
        for bad in ("", "abc", "0", "-3", "501"):
            r = post("/api/gobo-sizes/rule",
                     {"op": "set", "manufacturer": "Showtec", "model": "BadSize", "size": bad})
            eq(r.status_code, 400, f"{bad!r} must be refused, got {r.status_code}")
        rows = size_list._gobo_rule_rows("override")
        eq(any(x["Model"] == "BadSize" for x in rows), False, "and none of them were saved")
    with_accounts(go)


@test
def t_the_route_refuses_an_alias_onto_a_model_that_is_not_on_the_sheet():
    """A dead alias loads as a warning and leaves the model unresolved, so it
    would look like a fix while changing nothing."""
    def go():
        ensure_auth()
        r = post("/api/gobo-sizes/rule",
                 {"op": "alias", "manufacturer": "Showtec", "model": "Whatever",
                  "list_model": "No Such Projector Anywhere"})
        eq(r.status_code, 400, r.text)
        ok("not on the size list" in r.json().get("error", ""), "and says why")
    with_accounts(go)


@test
def t_the_model_search_answers_from_the_real_sheet():
    """The alias picker searches this. It has to return models that actually
    exist, or the picker offers targets that would load as dead rules."""
    def go():
        ensure_auth()
        r = post("/api/gobo-sizes/models", {"q": "pointe"})
        eq(r.status_code, 200, r.text)
        hits = r.json().get("models") or []
        ok(hits, "a model on the sheet is found")
        ok(all("pointe" in (m["manufacturer"] + " " + m["model"]).lower() for m in hits),
           "and every hit actually matches the term")
        # Whatever comes back must be usable as an alias target, which is the
        # only reason this endpoint exists.
        first = hits[0]
        _entry, reason = size_list._gobo_lookup(first["manufacturer"], first["model"])
        eq(reason, None, "the top hit resolves, so aliasing onto it is not a dead rule")
        eq((post("/api/gobo-sizes/models", {"q": "x"}).json().get("models")), [],
           "a one-character term searches nothing rather than returning the sheet")
    with_accounts(go)


