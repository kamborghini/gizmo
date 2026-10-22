# ---- Per-person colour ------------------------------------------------------

@test
def t_a_new_account_gets_a_colour_without_anyone_choosing_one():
    """It has to work with no setup, or nobody turns it on and the Inbox stays
    a wall of identical rows."""
    def go():
        ensure_auth()
        uid, _sess, _pw = ready_user("Colour One", "colourone")
        board = post("/api/team/board", {}).json()
        me = [u for u in board["users"] if u["id"] == uid][0]
        ok(me.get("colour"), "the account has a colour")
        ok(me["colour"] in team.TEAM_COLOUR_NAMES,
           f"and it is one of the known names, got {me.get('colour')!r}")
    with_accounts(go)


@test
def t_colours_do_not_repeat_until_the_palette_runs_out():
    """Two people sharing a colour defeats the whole point of glancing at a
    row and knowing whose it is."""
    def go():
        ensure_auth()
        seen = []
        for i in range(len(team.TEAM_COLOUR_NAMES)):
            uid, _s, _p = ready_user(f"Person {i}", f"person{i}")
            board = post("/api/team/board", {}).json()
            seen.append([u for u in board["users"] if u["id"] == uid][0]["colour"])
        eq(len(set(seen)), len(seen), f"every one is different: {seen}")
    with_accounts(go)


@test
def t_only_an_admin_changes_someone_elses_colour():
    def go():
        ensure_auth()
        uid, sess, _pw = ready_user("Colour Two", "colourtwo")
        eq(post("/api/team/user", {"op": "colour", "id": uid, "colour": "purple"}
                ).status_code, 200, "an admin can")
        board = post("/api/team/board", {}).json()
        eq([u for u in board["users"] if u["id"] == uid][0]["colour"], "purple")
        other, osess, _p = ready_user("Colour Three", "colourthree")
        eq(post_s(osess, "/api/team/user", {"op": "colour", "id": uid, "colour": "red"}
                  ).status_code, 403, "a member cannot recolour a colleague")
    with_accounts(go)


@test
def t_a_colour_that_is_not_on_the_palette_is_refused():
    """The CRM learned this one the hard way: a raw colour string reached
    style.background and a Pipedrive label coloured url(//evil.co/a) beaconed
    every render of the board. Only known names, ever."""
    def go():
        ensure_auth()
        uid, _sess, _pw = ready_user("Colour Four", "colourfour")
        for bad in ("url(//evil.co/a)", "#ff0000", "javascript:alert(1)", "", "gray-ish"):
            r = post("/api/team/user", {"op": "colour", "id": uid, "colour": bad})
            eq(r.status_code, 400, f"{bad!r} must be refused, got {r.status_code}")
        board = post("/api/team/board", {}).json()
        ok([u for u in board["users"] if u["id"] == uid][0]["colour"]
           in team.TEAM_COLOUR_NAMES, "and the colour it had is untouched")
    with_accounts(go)


