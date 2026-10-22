# ---- The perimeter, swept ---------------------------------------------------

def _api_routes():
    """Every /api route the app registers, with the methods it accepts."""
    import io as _io
    text = copilot_source()
    out = []
    for m in re.finditer(r'custom_route\("(/api/[^"]+)",\s*methods=\[([^\]]*)\]', text):
        methods = re.findall(r'"([A-Z]+)"', m.group(2))
        out.append((m.group(1), methods or ["POST"]))
    return sorted(set((p, tuple(ms)) for p, ms in out))


@test
def t_no_api_route_answers_without_a_session():
    """The hardening audit asserted every route was gated. It was asserted by
    reading, not by a test, so nothing stopped the next route from arriving
    ungated. This calls all of them.

    401 or 403 both count as refused. What must never happen is a 200: that is
    an endpoint answering an anonymous caller."""
    routes = _api_routes()
    ok(len(routes) > 90, f"the sweep found the routes ({len(routes)})")
    # The door itself has to answer an anonymous caller: /state is how the
    # client learns whether to show setup or a login at all, /setup and /login
    # are how you get a session, and /logout without one is a no-op.
    ANON_BY_DESIGN = {"/api/auth/state", "/api/auth/setup",
                      "/api/auth/login", "/api/auth/logout"}
    answered = []
    for path, methods in routes:
        if path in ANON_BY_DESIGN:
            continue
        method = "POST" if "POST" in methods else methods[0]
        gate._rl_hits.clear(); gate._rl_global.clear()
        try:
            r = client.request(method, path, json={},
                               headers={"Authorization": "Bearer " + tok()})
        except Exception as e:
            answered.append(f"{path} raised {type(e).__name__}")
            continue
        if r.status_code == 200:
            answered.append(f"{method} {path} -> 200")
    ok(not answered, "routes that answered an unauthenticated caller: " + str(answered[:8]))


@test
def t_no_api_route_skips_the_pre_checks():
    """_pre_checks is where the body cap, the rate limiter and the TAB gate all
    live. A handler that reaches _authorize without it is authenticated but
    ungated - it would serve a tab the account was never given."""
    import io as _io
    text = copilot_source()
    # Delegation counts. The mail, CRM, files, team and work routes reach
    # _pre_checks through a shared guard rather than calling it inline, and
    # asserting the literal call would flag forty correct handlers - the test
    # has to accept the effect, not insist on one spelling of it.
    # Named, not discovered: _spend_guard is an AI-budget check, not an auth
    # one, and sweeping every *_guard would assert something untrue of it.
    guards = {"_guard",   # the one door: rate window, session, rank, AI slot, body
              "_mail_guard", "_crm_guard", "_team_guard", "_files_guard",
              # The login door. The auth routes answer anonymously by design,
              # but they still go through the rate limiter and the body cap -
              # a login endpoint without those is a brute-force target.
              "_auth_guard"}
    ok(all(("def " + g + "(") in text for g in guards),
       "the auth guards are all still there")
    for g in guards:
        seg = text[text.index("def " + g + "("):][:1400]
        # A guard proves itself by running the checks, or by delegating to the
        # one door that does - which is what the four domain guards do now.
        ok("_pre_checks" in seg or "await _guard(request" in seg or "await gate._guard(request" in seg,
           f"{g} runs the rate limiter and the body cap, or delegates to the door")
        # The login door is the one guard that does NOT authorize: there is no
        # session yet when you are asking to make one. Everything behind it must.
        if g != "_auth_guard":
            ok("_authorize" in seg or "await _guard(request" in seg or "await gate._guard(request" in seg,
               f"{g} authenticates the caller")
    bad = []
    for m in re.finditer(r'custom_route\("(/api/[^"]+)"[^)]*\)\s*\n\s*async def (\w+)', text):
        path, fn = m.group(1), m.group(2)
        body = text[m.end():]
        nxt = body.find("\n    @mcp.custom_route")
        body = body[:nxt] if nxt > 0 else body[:6000]
        if "_pre_checks" in body or any(g + "(" in body for g in guards):
            continue
        bad.append(f"{path} ({fn})")
    ok(not bad, "handlers that neither check nor delegate: " + str(bad))


