# ---------------------------------------------------------------------------
# Claude Opus 5.5, 24 September 2026: it thinks on every request, refuses a
# forced tool call and prices cache reads at 0.05x. Pinned by behaviour.
# ---------------------------------------------------------------------------

class _OpusFake:
    """A client whose messages.create records each call and answers from a
    script: a list of replies, or exceptions to raise."""
    def __init__(self, script):
        self.calls, self.script = [], list(script)
        fake = self
        class _M:
            async def create(self, **kw):
                fake.calls.append(kw)
                nxt = fake.script.pop(0)
                if isinstance(nxt, Exception):
                    raise nxt
                return nxt
        self.messages = _M()


class _OpusBlock:
    def __init__(self, type_, **kw):
        self.type = type_
        for k, v in kw.items():
            setattr(self, k, v)


class _OpusResp:
    def __init__(self, blocks, stop="end_turn"):
        self.content, self.stop_reason, self.usage = blocks, stop, None


def _opus_run(model, script, **kw):
    fake = _OpusFake(script)
    saved = claude._spend_guard
    claude._spend_guard = lambda *a, **k: None
    try:
        resp = _run(claude._xcreate(fake, model=model, max_tokens=100, system="Read the order.",
                                     messages=[{"role": "user", "content": "Order 1"}],
                                     tools=[{"name": "record", "input_schema": {"type": "object"}}], **kw))
    finally:
        claude._spend_guard = saved
    return fake, resp


@test
def t_each_request_takes_the_effort_its_model_accepts():
    """Each tier's effort was capped at 'high' for any model not named Opus, on
    a guess that xhigh and max are Opus only. Sonnet 5.5 takes the whole ladder,
    so a Deep run on it was cut short; Opus 4.6 has max but not xhigh, so xhigh
    on it was refused; Haiku 4.5 takes neither an effort nor adaptive thinking,
    so every call on it failed over. Each request now fits what Anthropic's
    Models API says its model accepts, asked once per model."""
    import types as _types
    def caps(efforts, adaptive=True):
        return _types.SimpleNamespace(capabilities={
            "effort": {"supported": bool(efforts),
                       **{lvl: {"supported": lvl in efforts} for lvl in claude._EFFORT_LADDER}},
            "thinking": {"supported": True, "types": {"adaptive": {"supported": adaptive},
                                                      "enabled": {"supported": True}}}})
    table = {"claude-sonnet-5-5": caps(("low", "medium", "high", "xhigh", "max")),
             "claude-opus-4-6": caps(("low", "medium", "high", "max")),
             "claude-haiku-4-5": caps((), adaptive=False),
             "claude-opus-5-5": _types.SimpleNamespace(capabilities=None)}
    asked = []
    def send(model, **kw):
        fake = _OpusFake([_OpusResp([_OpusBlock("text", text="ok")])])
        async def retrieve(m):
            asked.append(m)
            if m not in table:
                raise RuntimeError("the Models API is unreachable")
            return table[m]
        fake.models = _types.SimpleNamespace(retrieve=retrieve)
        saved = claude._spend_guard
        claude._spend_guard = lambda *a, **k: None
        try:
            _run(claude._xcreate(fake, model=model, max_tokens=100,
                                  messages=[{"role": "user", "content": "Order 1"}], **kw))
        finally:
            claude._spend_guard = saved
        return fake.calls[0]
    claude._MODEL_CAPS.clear()
    try:
        eq(send("claude-sonnet-5-5", output_config={"effort": "max"})["output_config"], {"effort": "max"},
           "a Sonnet 5.5 Deep run keeps max")
        eq(send("claude-opus-4-6", output_config={"effort": "xhigh"})["output_config"], {"effort": "high"},
           "xhigh steps down to the next level a model has")
        eq(send("claude-opus-4-6", output_config={"effort": "max"})["output_config"], {"effort": "max"})
        h = send("claude-haiku-4-5", output_config={"effort": "high"}, thinking={"type": "adaptive"})
        ok("output_config" not in h and "thinking" not in h, "Haiku is sent neither: %r" % h)
        eq(asked.count("claude-opus-4-6"), 1, "each model is asked once")
        eq(send("claude-sonnet-9", output_config={"effort": "max"})["output_config"], {"effort": "high"},
           "with the Models API unreachable, the cautious rule as before")
        # An answer with no capabilities (the field may be null) is unknown:
        # the cautious rule, not "takes nothing", and asked again later.
        o = send("claude-opus-5-5", output_config={"effort": "max"}, thinking={"type": "adaptive"})
        eq((o.get("output_config"), o.get("thinking")), ({"effort": "max"}, {"type": "adaptive"}),
           "a null answer leaves effort and thinking as asked for")
        eq(claude._MODEL_CAPS["claude-opus-5-5"][1], None, "and is kept only as unknown, to be asked again")
        mine = {"effort": "xhigh"}
        send("claude-opus-4-6", output_config=mine)
        eq(mine, {"effort": "xhigh"}, "and the request the caller built is not altered under it")
        eq(claude._effort_for("claude-sonnet-5-5", True), claude.ANTHROPIC_EFFORT_DEEP,
           "the tier's effort is asked for as configured")
    finally:
        claude._MODEL_CAPS.clear()


@test
def t_opus_5_5_is_the_default_and_counted_at_its_price():
    src = copilot_source()
    ok('or "claude-opus-5-5"\n' in src and 'os.environ.get("ANTHROPIC_MODEL_DEEP", "claude-opus-5-5")' in src,
       "both tiers default to Opus 5.5")
    # $4 in, $20 out, cache reads at 0.05x input, writes at 1.25x.
    eq(claude._price_for("claude-opus-5-5", 1_000_000, 1_000_000, 1_000_000, 1_000_000), 4 + 20 + 0.2 + 5.0)
    eq(claude._price_for("claude-opus-4-8", 0, 0, 1_000_000, 0), 0.5, "other models keep 0.1x")


@test
def t_a_forced_tool_on_opus_5_5_is_asked_for_in_words():
    tool = _OpusBlock("tool_use", name="record", input={"total": 5}, id="t1")
    fake, resp = _opus_run("claude-opus-5-5", [_OpusResp([_OpusBlock("thinking", thinking="", signature="s"), tool], "tool_use")],
                           tool_choice={"type": "tool", "name": "record"})
    eq(len(fake.calls), 1)
    ok("tool_choice" not in fake.calls[0], "Opus 5.5 refuses a forced tool, so none is sent")
    ok("calling the record tool" in str(fake.calls[0]["system"]), "the instructions name the tool instead")
    ok(resp.content[1] is tool, "and the caller finds its tool block after the thinking")


@test
def t_a_prose_answer_is_asked_once_more_for_the_tool():
    think = _OpusBlock("thinking", thinking="", signature="s")
    prose = _OpusResp([think, _OpusBlock("text", text="The total is 5.")])
    tool = _OpusResp([_OpusBlock("tool_use", name="record", input={"total": 5}, id="t1")], "tool_use")
    fake, resp = _opus_run("claude-opus-5-5", [prose, tool], tool_choice={"type": "tool", "name": "record"})
    eq(len(fake.calls), 2, "one more request, not a failed report")
    msgs = fake.calls[1]["messages"]
    ok(msgs[-2]["role"] == "assistant" and msgs[-2]["content"] is prose.content,
       "its own reply goes back as it came, thinking included")
    ok("calling the record tool" in msgs[-1]["content"], msgs[-1])
    ok(resp is tool)
    # A reply that ran out of room, or refused, is not asked again.
    fake, resp = _opus_run("claude-opus-5-5", [_OpusResp([think], "max_tokens")],
                           tool_choice={"type": "tool", "name": "record"})
    eq(len(fake.calls), 1)


@test
def t_a_model_that_can_be_forced_still_is():
    fake, _ = _opus_run("claude-opus-4-8", [_OpusResp([_OpusBlock("tool_use", name="record", input={}, id="t")], "tool_use")],
                        tool_choice={"type": "tool", "name": "record"})
    eq(fake.calls[0]["tool_choice"], {"type": "tool", "name": "record"})
    eq(fake.calls[0]["system"], "Read the order.")


@test
def t_a_model_found_refusing_a_forced_tool_is_remembered():
    import httpx
    refused = copilot.anthropic.BadRequestError(
        'tool_choice: type "tool" and "any" are not supported for this model.',
        response=httpx.Response(400, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")), body=None)
    good = _OpusResp([_OpusBlock("tool_use", name="record", input={}, id="t")], "tool_use")
    saved = set(claude._UNFORCED_MODELS)
    last = dict(claude._AI_LAST_FAIL)
    try:
        fake, resp = _opus_run("claude-next-9", [refused, good], tool_choice={"type": "tool", "name": "record"})
        eq(len(fake.calls), 2)
        ok("tool_choice" not in fake.calls[1] and resp is good, "retried without forcing")
        ok(not claude._can_force_tool("claude-next-9"), "and not forced again")
        other = copilot.anthropic.BadRequestError("messages: too long", response=refused.response, body=None)
        fb = claude.MODEL_FALLBACK
        claude.MODEL_FALLBACK = "off"
        try:
            _opus_run("claude-next-8", [other], tool_choice={"type": "tool", "name": "record"})
            ok(False, "any other refusal is not taken for a forced-tool one")
        except copilot.anthropic.BadRequestError:
            pass
        finally:
            claude.MODEL_FALLBACK = fb
        ok(claude._can_force_tool("claude-next-8"), "and the model is still forced")
    finally:
        claude._UNFORCED_MODELS.clear(); claude._UNFORCED_MODELS.update(saved)
        claude._AI_LAST_FAIL.clear(); claude._AI_LAST_FAIL.update(last)


@test
def t_deep_analysis_is_more_thinking_and_the_answer_says_it_was_deep():
    seen = []
    async def answer(history, dispatch, tools, model, extra, emit=None, effort=None, deep=False):
        seen.append((model, effort))
        return {"structured": {"summary": "hi"}, "model": model}
    def go():
        ensure_auth()
        _a, sess, _p = ready_user("Dee Deep", "deed", role="admin")
        saved = assistant.run_chat
        assistant.run_chat = answer
        gate._rl_global.clear()
        try:
            r = post_s(sess, "/api/chat", {"message": "hello", "deep": True})
            eq(r.json()["deep"], True)
            r = post_s(sess, "/api/chat", {"message": "hello"})
            eq(r.json()["deep"], False)
            eq(seen[0][1], claude._effort_for(claude.MODEL_DEEP, True))
            eq(seen[1][1], claude._effort_for(claude.MODEL_FAST, False))
            r = post_s(sess, "/api/chat/stream", {"message": "hello", "deep": True})
            done = [json.loads(l[5:]) for l in r.text.split("\n") if l.startswith("data:")][-1]
            eq(done["result"]["deep"], True, "the stream's answer says so too")
        finally:
            assistant.run_chat = saved
    with_accounts(go)
    if not os.environ.get("ANTHROPIC_EFFORT_DEEP") and not os.environ.get("ANTHROPIC_EFFORT"):
        eq(claude._effort_for("claude-opus-5-5", True), "max")
        eq(claude._effort_for("claude-opus-5-5"), "high")



# A chat question failed on Opus 5.5 with "The AI service returned an error"
# and nothing said why. Each failure now says what it was, and a request the
# chosen model fails at Anthropic is asked of the fallback model once.

def _api_status(code, message="nope", err_type="invalid_request_error"):
    import httpx
    resp = httpx.Response(code, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    body = {"type": "error", "error": {"type": err_type, "message": message}}
    cls = {400: copilot.anthropic.BadRequestError, 401: copilot.anthropic.AuthenticationError,
           404: copilot.anthropic.NotFoundError, 429: copilot.anthropic.RateLimitError}.get(code, copilot.anthropic.APIStatusError)
    return cls(message, response=resp, body=body)


@test
def t_an_ai_failure_says_what_it_was():
    w = claude._ai_error_words
    ok("does not offer that model" in w(_api_status(404, "model: claude-opus-5-5", "not_found_error"))
       and "model: claude-opus-5-5" in w(_api_status(404, "model: claude-opus-5-5")), "a model the account cannot use")
    ok("limit" in w(_api_status(429, "rate limited", "rate_limit_error")) and "ask again" in w(_api_status(429)))
    ok("ask again" not in w(_api_status(429), advice=False), "an answered question is not told to ask again")
    ok("busy or down" in w(_api_status(529, "Overloaded", "overloaded_error")) and "busy or down" in w(_api_status(500)))
    ok("key" in w(_api_status(401, "invalid x-api-key", "authentication_error")))
    ok("Anthropic said: messages.1: bad thing" in w(_api_status(400, "messages.1: bad thing")), "a refused request in Anthropic's words")
    ok("—" not in w(_api_status(400, "a — b")), "no dash reaches the page")
    import httpx
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    ok("too long" in w(copilot.anthropic.APITimeoutError(request=req)))
    ok("could not reach" in w(copilot.anthropic.APIConnectionError(request=req)))
    eq(claude._model_name("claude-opus-5-5"), "Claude Opus 5.5")
    eq(claude._model_name("claude-sonnet-5"), "Claude Sonnet 5")
    eq(claude._model_name("claude-haiku-4-5-20251001"), "Claude Haiku 4.5")
    eq(claude._model_name("anthropic.claude-opus-4-8"), "Claude Opus 4.8")
    src = copilot_source()
    ok('"The AI service returned an error. Please try again."}' not in src and src.count("_ai_error_words(e)}") >= 11,
       "every AI route says the reason")


@test
def t_a_model_that_fails_is_answered_by_the_fallback_and_says_so():
    good = _OpusResp([_OpusBlock("tool_use", name="record", input={"total": 5}, id="t")], "tool_use")
    saved = (claude.MODEL_FALLBACK, dict(claude._AI_LAST_FAIL), errors.ERRORS_PATH)
    try:
        claude.MODEL_FALLBACK = "claude-opus-4-8"
        errors.ERRORS_PATH = SCRATCH + "/app_errors_fallback.json"
        try:
            os.remove(errors.ERRORS_PATH)
        except FileNotFoundError:
            pass
        fake, resp = _opus_run("claude-opus-5-5", [_api_status(404, "model: claude-opus-5-5", "not_found_error"), good],
                               tool_choice={"type": "tool", "name": "record"}, output_config={"effort": "max"})
        eq([c["model"] for c in fake.calls], ["claude-opus-5-5", "claude-opus-4-8"])
        ok(resp is good, "the fallback's answer is the answer")
        eq(claude._AI_LAST_FAIL["model"], "Claude Opus 5.5")
        eq(claude._AI_LAST_FAIL["answered_by"], "Claude Opus 4.8")
        ok("does not offer that model" in claude._AI_LAST_FAIL["why"])
        eq(len(errors._recent_errors(1)), 0, "a failure another model answered is not an app error")
        # A non-Opus fallback is not sent an effort it would refuse.
        claude.MODEL_FALLBACK = "claude-sonnet-4-6"
        fake, _ = _opus_run("claude-opus-5-5", [_api_status(529, "Overloaded"), good], output_config={"effort": "max"})
        eq(fake.calls[1]["output_config"], {"effort": "high"})
        # Both fail: the chosen model's failure is the one raised.
        claude.MODEL_FALLBACK = "claude-opus-4-8"
        try:
            _opus_run("claude-opus-5-5", [_api_status(404, "model: claude-opus-5-5"), _api_status(529, "Overloaded")])
            ok(False, "raised")
        except copilot.anthropic.APIStatusError as e:
            eq(e.status_code, 404)
        eq(claude._AI_LAST_FAIL["answered_by"], "")
        # A refused key is refused by any model: no second request.
        try:
            _opus_run("claude-opus-5-5", [_api_status(401, "invalid x-api-key")])
            ok(False, "raised")
        except copilot.anthropic.AuthenticationError:
            pass
        # Switched off, a failure is raised as it came.
        claude.MODEL_FALLBACK = "off"
        try:
            fake, _ = _opus_run("claude-opus-5-5", [_api_status(529, "Overloaded")])
            ok(False, "raised")
        except copilot.anthropic.APIStatusError:
            pass
        # Nobody answered that one, so it is in the app's error store too.
        rows = errors._recent_errors(1)
        ok(len(rows) == 3 and all(r["where"].startswith("asking the AI: ") and "_" not in r["where"] for r in rows)
           and "Overloaded" in rows[0]["error"], "each unanswered failure reaches the app errors, labelled in words: %r" % rows)
    finally:
        claude.MODEL_FALLBACK, errors.ERRORS_PATH = saved[0], saved[2]
        claude._AI_LAST_FAIL.clear(); claude._AI_LAST_FAIL.update(saved[1])


@test
def t_a_chat_that_fell_back_stays_on_the_fallback_and_says_why():
    fake = _OpusFake([
        _api_status(404, "model: claude-opus-5-5", "not_found_error"),
        _OpusResp([_OpusBlock("thinking", thinking="", signature="s"),
                   _OpusBlock("tool_use", name="shopify_get_shop", input={}, id="tu1")], "tool_use"),
        _OpusResp([_OpusBlock("tool_use", name="present_response", input={"summary": "Fine."}, id="tu2")], "tool_use"),
    ])
    saved = (claude._client, claude._spend_guard, claude.MODEL_FALLBACK, dict(claude._AI_LAST_FAIL))
    claude._client, claude._spend_guard, claude.MODEL_FALLBACK = fake, (lambda *a, **k: None), "claude-opus-4-8"
    async def dispatch(name, args):
        return '{"name": "Shop"}'
    try:
        r = _run(assistant.run_chat([{"role": "user", "content": "How is the shop?"}], dispatch,
                                  [{"name": "shopify_get_shop", "input_schema": {"type": "object"}}], "claude-opus-5-5",
                                  effort="max"))
        eq([c["model"] for c in fake.calls], ["claude-opus-5-5", "claude-opus-4-8", "claude-opus-4-8"],
           "the failed model is not asked again every round")
        eq(r["structured"]["summary"], "Fine.")
        eq(r["model"], "claude-opus-4-8")
        eq(r["fell_back"]["to"], "Claude Opus 4.8")
        eq(r["fell_back"]["from"], "Claude Opus 5.5")
        ok("does not offer that model" in r["fell_back"]["why"], r["fell_back"])
        # A run that did not fall back says nothing about it.
        fake.script = [_OpusResp([_OpusBlock("tool_use", name="present_response", input={"summary": "Hi."}, id="t")], "tool_use")]
        r = _run(assistant.run_chat([{"role": "user", "content": "Hi"}], dispatch, [], "claude-opus-5-5"))
        ok("fell_back" not in r, r)
    finally:
        claude._client, claude._spend_guard, claude.MODEL_FALLBACK = saved[:3]
        claude._AI_LAST_FAIL.clear(); claude._AI_LAST_FAIL.update(saved[3])


@test
def t_a_failed_chat_tells_the_page_the_reason():
    async def refused(history, dispatch, tools, model, extra, emit=None, effort=None, deep=False):
        raise _api_status(400, "messages.0: something the model refused")
    def go():
        ensure_auth()
        _a, sess, _p = ready_user("Rae Reason", "raer", role="admin")
        saved = assistant.run_chat
        assistant.run_chat = refused
        gate._rl_global.clear()
        try:
            r = post_s(sess, "/api/chat", {"message": "hello"})
            eq(r.status_code, 502)
            ok("Anthropic said: messages.0: something the model refused" in r.json()["error"], r.json())
            r = post_s(sess, "/api/chat/stream", {"message": "hello"})
            last = [json.loads(l[5:]) for l in r.text.split("\n") if l.startswith("data:")][-1]
            ok(last["type"] == "error" and "Anthropic said" in last["error"], last)
        finally:
            assistant.run_chat = saved
    with_accounts(go)



@test
def t_settings_is_told_which_model_answers_and_its_latest_failure():
    saved = dict(claude._AI_LAST_FAIL)
    def go():
        ensure_auth()
        _a, sess, _p = ready_user("Ada Status", "adas", role="admin")
        claude._AI_LAST_FAIL.clear()
        claude._AI_LAST_FAIL.update({"at": "2026-09-24T13:05:00+00:00", "model": "Claude Opus 5.5",
                                      "why": "Reactor has reached the AI service's limit for its account.", "answered_by": "Claude Opus 4.8"})
        ai = post_s(sess, "/api/status", {}).json()["ai"]
        eq(ai["models"]["chat"], claude._model_name(claude.MODEL_FAST))
        eq(ai["last_failure"]["answered_by"], "Claude Opus 4.8")
    try:
        with_accounts(go)
    finally:
        claude._AI_LAST_FAIL.clear(); claude._AI_LAST_FAIL.update(saved)


@test
def t_a_chat_that_ran_out_of_room_or_was_declined_says_so():
    """Opus 5.5 thinks on every request and the thinking counts against the
    token limit: a Deep analysis that used it all ended as "Reactor did not
    send an answer", like a refusal did."""
    saved = (claude._client, claude._spend_guard)
    claude._spend_guard = lambda *a, **k: None
    async def dispatch(name, args):
        return "{}"
    try:
        for stop, words in (("max_tokens", "ran out of room"), ("refusal", "declined to answer")):
            claude._client = _OpusFake([_OpusResp([_OpusBlock("thinking", thinking="", signature="s")], stop)])
            r = _run(assistant.run_chat([{"role": "user", "content": "Everything, in depth"}], dispatch, [], "claude-opus-5-5"))
            ok(words in r["structured"]["summary"], (stop, r["structured"]))
    finally:
        claude._client, claude._spend_guard = saved


# Cameron, 24 Sep 2026: "make the size of the uploadable MD skills larger but
# only allow uploads from the master account".

@test
def t_only_the_master_uploads_skills_and_its_limit_is_larger():
    saved = _ws_stores()
    def go():
        ensure_auth()
        _a, sess, _p = ready_user("Mo Member", "momem", role="admin")
        # An admin who is not the master: the usual limit, and no uploads.
        r = post_s(sess, "/api/skills", {})
        eq((r.json()["caps"]["body"], r.json()["caps"]["upload"]), (skillbook.SKILL_BODY_CAP, False))
        r = post_s(sess, "/api/skills", {"op": "add", "title": "From a file", "content": "Reply the same day.", "file": "replies.md"})
        eq(r.status_code, 403, r.text)
        ok("Only the master account can upload" in r.json()["error"], r.text)
        ok(not [x for x in skillbook._load_skills() if x["title"] == "From a file"], "nothing was saved")
        r = post_s(sess, "/api/skills", {"op": "add", "title": "Typed", "content": "Reply the same day."})
        eq(r.status_code, 200, "writing a skill by hand is unchanged")
        r = post_s(sess, "/api/skills", {"op": "add", "title": "Too long", "content": "x" * (skillbook.SKILL_BODY_CAP + 1)})
        eq(r.status_code, 400)
        ok("limit of " + f"{skillbook.SKILL_BODY_CAP:,}" in r.json()["error"], r.text)
        # The master: the larger limit, uploads, and a body over the usual request limit.
        big = ("## Part\n" + ("Trade £85 " + "£" * 50 + "\n") * 40) * 80
        big = big[:skillbook.SKILL_UPLOAD_CAP - 10].strip()
        ok(len(json.dumps({"content": big}, ensure_ascii=False).encode("utf-8")) > gate.MAX_BODY_BYTES
           and len(big) > skillbook.SKILL_BODY_CAP * 4, "over the usual request limit: %d" % len(big))
        r = post("/api/skills", {"op": "add", "title": "Trade book", "content": big, "file": "trade-book.md"})
        eq(r.status_code, 200, r.text[:300])
        sk = [x for x in r.json()["skills"] if x["title"] == "Trade book"][0]
        eq((len(sk["content"]), sk["file"]), (len(big.strip()), "trade-book.md"))
        r = post("/api/skills", {"op": "add", "title": "Too big", "content": "x" * (skillbook.SKILL_UPLOAD_CAP + 1)})
        eq(r.status_code, 400)
        # From anyone else, a body that size is read but not saved: their limit is the usual one.
        pad = "£\n" * 90000
        ok(len(json.dumps({"content": pad}, ensure_ascii=False).encode("utf-8")) > gate.MAX_BODY_BYTES)
        r = post_s(sess, "/api/skills", {"op": "add", "title": "Padded", "content": pad})
        eq(r.status_code, 400, r.text[:200])
        # And nobody sends more than a skill at the master's limit could need.
        r = post_s(sess, "/api/skills", {"op": "add", "title": "Huge", "content": "x" * (skillbook.SKILLS_BODY_MAX + 10)})
        eq(r.status_code, 413)
        # Someone else may edit the master's long skill, but not make it longer.
        sid = sk["id"]
        r = post_s(sess, "/api/skills", {"op": "update", "id": sid, "title": "Trade book", "content": big.replace("£85", "£90", 1)})
        eq(r.status_code, 200, r.text[:300])
        r = post_s(sess, "/api/skills", {"op": "update", "id": sid, "title": "Trade book", "content": big + "\nOne more rule."})
        eq(r.status_code, 400, "grown past what it was")
    try:
        with_accounts(go)
    finally:
        _ws_restore(saved)


@test
def t_a_skill_longer_than_one_read_is_read_in_parts_to_the_end():
    saved = _ws_stores()
    try:
        # One long stretch with no headings: it used to stop after one read.
        text = "\n\n".join("Paragraph %d. Trade gobos take four days." % i for i in range(4000))
        ok(len(text) > skillbook.SKILL_READ_CAP * 3)
        skillbook._add_skill("Long notes", text, cap=skillbook.SKILL_UPLOAD_CAP)
        pieces = skillbook._read_parts(text)
        ok(all(len(p) <= skillbook.SKILL_READ_CAP for p in pieces) and len(pieces) >= 4, [len(p) for p in pieces])
        eq("\n\n".join(pieces), text, "cut at paragraph breaks, nothing lost")
        one = skillbook._read_skill("Long notes")
        ok('part="1 of ' + str(len(pieces)) + '"' in one and "Read part 2 with read_skill" in one, one[-200:])
        last = skillbook._read_skill("Long notes", "", len(pieces))
        ok("Paragraph 3999." in last and "That is the end of it" in last, last[-200:])
        eq(skillbook._read_skill("Long notes", "", 999), last, "a part past the end is the last one")
        eq(skillbook._read_skill("Long notes", "", "two"), one, "a part that is not a number is the first")
        # A section longer than one read, the same way.
        skillbook._add_skill("Sectioned", "# Intro\nShort.\n# Rules\n" + text, cap=skillbook.SKILL_UPLOAD_CAP)
        sec2 = skillbook._read_skill("Sectioned", "Rules", 2)
        ok('section="Rules" part="2 of' in sec2 and "read part 3 of it" in sec2, sec2[:200])
        ok(not skillbook._read_skill("Sectioned", "Intro").count("part="), "a short section has no parts")
        # The brief says there are more headings than it lists.
        many = "\n".join("## Heading %d\nRule %d." % (i, i) for i in range(60))
        skillbook._add_skill("Many headings", many)
        b = skillbook._skill_brief_block([x for x in skillbook._load_skills() if x["title"] == "Many headings"][0], True, "")
        ok("and 20 more, found by reading it part by part" in b, b[-300:])
        ok('"part"' in json.dumps(skillbook.READ_SKILL_TOOL), "the tool can be asked for a part")
    finally:
        _ws_restore(saved)


@test
def t_the_close_read_sees_all_of_a_long_skill():
    saved = _ws_stores()
    seen = {}
    class _Tu:
        type, name = "tool_use", "present_skill_reading"
        def __init__(self, inp): self.input = inp
    class _R:
        def __init__(self, blocks): self.content, self.stop_reason = blocks, "tool_use"
    async def fake_x(client, **kw):
        seen.update(kw)
        return _R([_Tu({"when": "Trade.", "rules": ["Quote."], "examples": [], "questions": []})])
    sx = claude._xcreate; claude._xcreate = fake_x
    try:
        text = "Opening rule.\n\n" + "Filler line about glass.\n" * 5000 + "\nTHE LAST RULE: never discount steel."
        ok(len(text) > 100000)
        skillbook._add_skill("Whole manual", text, cap=skillbook.SKILL_UPLOAD_CAP)
        sk = [x for x in skillbook._load_skills() if x["title"] == "Whole manual"][0]
        _run(skillbook.run_skill_reading(sk, skillbook._load_skills()))
        ok("THE LAST RULE: never discount steel." in seen["messages"][0]["content"],
           "the reading is of the whole text it is then marked as having read")
    finally:
        claude._xcreate = sx
        _ws_restore(saved)



# The second review of the Opus 5.5 change, and the review of the larger skills.

@test
def t_a_report_that_did_not_finish_keeps_the_last_one_and_says_why():
    """Opus 5.5 cannot be made to call present_response and its thinking
    counts toward the limit: a report that stopped without it saved "Keyword
    analysis ready." over the last good one, and the page showed no error."""
    good = _OpusResp([_OpusBlock("thinking", thinking="", signature="s"),
                      _OpusBlock("tool_use", name="present_response", id="t1",
                                 input={"summary": "Three keywords carry 60% of clicks."})], "tool_use")
    saved = (claude._client, claude._spend_guard)
    claude._spend_guard = lambda *a, **k: None
    def go():
        ensure_auth()
        _a, sess, _p = ready_user("Kay Words", "kayw", role="admin")
        claude._client = _OpusFake([good])
        eq(post_s(sess, "/api/keywords", {}).status_code, 200)
        for stop, words in (("max_tokens", "ran out of room"), ("refusal", "declined"), ("end_turn", "did not finish")):
            claude._client = _OpusFake([_OpusResp([_OpusBlock("thinking", thinking="", signature="s")], stop)] * 2)
            r = post_s(sess, "/api/keywords", {})
            ok(r.status_code == 500 and words in r.json()["error"] and "last one is kept" in r.json()["error"], (stop, r.text[:200]))
            cache = json.load(open(analytics.ANALYSIS_CACHE_PATH)).get("keywords", {})
            eq(cache.get("result", {}).get("structured", {}).get("summary"), "Three keywords carry 60% of clicks.",
               "the last good report is kept")
        # A budget refusal is said as it is on the keyword and customer reports too.
        def spent(*a, **k):
            raise RuntimeError("Reactor has used today's AI budget.")
        claude._spend_guard = spent
        for path in ("/api/keywords", "/api/customers"):
            r = post_s(sess, path, {})
            ok("today's AI budget" in r.json().get("error", ""), (path, r.text[:200]))
    try:
        with_accounts(go)
    finally:
        claude._client, claude._spend_guard = saved


@test
def t_the_fallback_is_asked_as_it_can_be_and_a_failed_nudge_is_noted():
    saved = (claude.MODEL_FALLBACK, dict(claude._AI_LAST_FAIL), errors.ERRORS_PATH, set(claude._UNFORCED_MODELS))
    try:
        errors.ERRORS_PATH = SCRATCH + "/app_errors_nudge.json"
        # A fallback that refuses forcing is asked in words, not forced.
        claude.MODEL_FALLBACK = "claude-opus-5-5"
        good = _OpusResp([_OpusBlock("tool_use", name="record", input={}, id="t")], "tool_use")
        fake, resp = _opus_run("claude-sonnet-4-6", [_api_status(529, "Overloaded"), good],
                               tool_choice={"type": "tool", "name": "record"})
        eq([c["model"] for c in fake.calls], ["claude-sonnet-4-6", "claude-opus-5-5"])
        eq(fake.calls[0]["tool_choice"], {"type": "tool", "name": "record"})
        ok("tool_choice" not in fake.calls[1] and "calling the record tool" in str(fake.calls[1]["system"]),
           "the refusing fallback is not forced")
        # A nudge that fails is noted, and no model is said to have answered.
        claude.MODEL_FALLBACK = "claude-opus-4-8"
        prose = _OpusResp([_OpusBlock("text", text="Five.")])
        try:
            _opus_run("claude-opus-5-5", [prose, _api_status(529, "Overloaded")], tool_choice={"type": "tool", "name": "record"})
            ok(False, "raised")
        except copilot.anthropic.APIStatusError:
            pass
        eq((claude._AI_LAST_FAIL["model"], claude._AI_LAST_FAIL["answered_by"]), ("Claude Opus 5.5", ""))
    finally:
        claude.MODEL_FALLBACK, _l, errors.ERRORS_PATH, _u = saved
        claude._AI_LAST_FAIL.clear(); claude._AI_LAST_FAIL.update(saved[1])
        claude._UNFORCED_MODELS.clear(); claude._UNFORCED_MODELS.update(saved[3])


@test
def t_settings_names_a_fallback_only_where_one_would_be_asked():
    saved = (claude.MODEL_FALLBACK, claude.MODEL_FAST, claude.MODEL_DEEP)
    def go():
        ensure_auth()
        _a, sess, _p = ready_user("Fen Fallback", "fenf", role="admin")
        claude.MODEL_FALLBACK = "off"
        eq(post_s(sess, "/api/status", {}).json()["ai"]["models"]["fallback"], "")
        claude.MODEL_FALLBACK = claude.MODEL_FAST = claude.MODEL_DEEP = "claude-opus-4-8"
        eq(post_s(sess, "/api/status", {}).json()["ai"]["models"]["fallback"], "", "a model is not its own fallback")
        claude.MODEL_FAST = claude.MODEL_DEEP = "claude-opus-5-5"
        eq(post_s(sess, "/api/status", {}).json()["ai"]["models"]["fallback"], "Claude Opus 4.8")
    try:
        with_accounts(go)
    finally:
        claude.MODEL_FALLBACK, claude.MODEL_FAST, claude.MODEL_DEEP = saved


@test
def t_out_of_room_advice_matches_the_switch_and_a_fallback_is_said_on_every_ending():
    saved = (claude._client, claude._spend_guard, claude.MODEL_FALLBACK, dict(claude._AI_LAST_FAIL))
    claude._spend_guard = lambda *a, **k: None
    async def dispatch(name, args):
        return "{}"
    try:
        out = lambda: _OpusResp([_OpusBlock("thinking", thinking="", signature="s")], "max_tokens")
        claude._client = _OpusFake([out()])
        r = _run(assistant.run_chat([{"role": "user", "content": "Everything"}], dispatch, [], "claude-opus-5-5"))
        ok("ran out of room" in r["structured"]["summary"] and "Deep analysis" not in r["structured"]["summary"],
           "no advice to switch off what is already off")
        claude._client = _OpusFake([out()])
        r = _run(assistant.run_chat([{"role": "user", "content": "Everything"}], dispatch, [], "claude-opus-5-5", deep=True))
        ok("switch Deep analysis off" in r["structured"]["summary"], r["structured"])
        claude.MODEL_FALLBACK = "claude-opus-4-8"
        claude._client = _OpusFake([_api_status(529, "Overloaded"), out()])
        r = _run(assistant.run_chat([{"role": "user", "content": "Everything"}], dispatch, [], "claude-opus-5-5"))
        eq(r.get("fell_back", {}).get("to"), "Claude Opus 4.8", "the ran-out ending says who answered too")
    finally:
        claude._client, claude._spend_guard, claude.MODEL_FALLBACK = saved[:3]
        claude._AI_LAST_FAIL.clear(); claude._AI_LAST_FAIL.update(saved[3])


@test
def t_a_long_catalogue_is_read_in_reads_of_the_stated_size():
    """A 199,000-character catalogue with thousands of headings sent every
    heading after part 1, a reply of 143,000 characters."""
    saved = _ws_stores()
    try:
        text = "\n".join("### Gobo GB-%05d\nSteel, 37.5 mm, £%d." % (i, 20 + i % 30) for i in range(5000))[:199000]
        skillbook._add_skill("Catalogue", text, cap=skillbook.SKILL_UPLOAD_CAP)
        for args in (("Catalogue",), ("Catalogue", "", 2), ("Catalogue", "Delivery times"), ("Catalogue", "Gobo GB-000")):
            got = skillbook._read_skill(*args)
            ok(len(got) <= skillbook.SKILL_READ_CAP + 3000, (args, len(got)))
        miss = skillbook._read_skill("Catalogue", "Gobo GB-99999")
        ok(" more" in miss and "Read it by part to see them all" in miss, miss[-200:])
        ok(skillbook._read_skill("Catalogue", "", float("inf")) == skillbook._read_skill("Catalogue"), "a part of infinity is the first")
        ok(skillbook._read_skill("Catalogue", "", True) == skillbook._read_skill("Catalogue"), "and so is a part of True")
    finally:
        _ws_restore(saved)


@test
def t_someone_else_may_change_a_long_skill_but_not_replace_it():
    # An admin: members no longer write skills at all (audit R-003).
    saved = _ws_stores()
    def go():
        ensure_auth()
        _a, sess, _p = ready_user("Rex Replace", "rexr", role="admin")
        manual = "\n\n".join("## Section %d\n%s" % (i, ("Glass gobos take four days. " * 30)) for i in range(200))[:180000]
        r = post("/api/skills", {"op": "add", "title": "Trade manual", "content": manual, "file": "trade-manual.md"})
        sid = [x for x in r.json()["skills"] if x["title"] == "Trade manual"][0]["id"]
        other = ("Discount policy text. " * 9000)[:len(manual.strip()) - 5]
        r = post_s(sess, "/api/skills", {"op": "update", "id": sid, "title": "Trade manual", "content": other})
        eq(r.status_code, 400, "a paste over the whole of it is the master's to do")
        ok("only the master" in r.json()["error"], r.text)
        edited = manual.replace("four days", "five days", 50)
        eq(post_s(sess, "/api/skills", {"op": "update", "id": sid, "title": "Trade manual", "content": edited}).status_code, 200,
           "changing parts of it is fine")
        r = post_s(sess, "/api/skills", {"op": "update", "id": sid, "title": "Trade manual", "content": edited + "\nMore."})
        eq(r.status_code, 400)
        ok("not make it longer than it is" in r.json()["error"], r.text)
    try:
        with_accounts(go)
    finally:
        _ws_restore(saved)


@test
def t_a_long_header_is_read_in_linear_time_and_the_index_holds_a_bounded_amount():
    head = "---\nname: x\ndescription: >\n" + " a\n" * 300000 + "---\nBody."
    t0 = time.time()
    meta, body = skillbook._split_frontmatter(head)
    ok(time.time() - t0 < 1.0, "a header of 900,000 characters parses in under a second: %.2fs" % (time.time() - t0))
    eq((meta["name"], body), ("x", "Body."))
    eq(skillbook._split_frontmatter("---\nname: Trade\ndescription: |\n  Line one\n  Line two\n---\nB")[0]["description"],
       "Line one\nLine two", "a literal value keeps its lines")
    eq(skillbook._split_frontmatter("---\nname: Trade\ndescription: Plain\n  and more\n---\nB")[0]["description"],
       "Plain and more", "a plain value carried on indented lines is one line")
    saved = (dict(skillbook._SKILL_INDEX), skillbook._SKILL_INDEX_CHARS)
    try:
        skillbook._SKILL_INDEX.clear(); skillbook._SKILL_INDEX_CHARS = 0
        for i in range(30):
            skillbook._skill_index(("Rule %d. " % i) * 30000)
        ok(skillbook._SKILL_INDEX_CHARS <= 5_000_000, skillbook._SKILL_INDEX_CHARS)
    finally:
        skillbook._SKILL_INDEX.clear(); skillbook._SKILL_INDEX.update(saved[0]); skillbook._SKILL_INDEX_CHARS = saved[1]


@test
def t_the_connector_settings_list_holds_only_what_the_connector_keeps():
    """Live fault, 2026-10-07: SHOP_TIMEZONE was on the list the Xero sync page
    may change, but the connector neither accepts nor returns it, so a save of
    it was dropped there while the page said "Saved"."""
    ok("SHOP_TIMEZONE" not in xerosync._CONNECTOR_SETTABLE, "not offered, so never 'saved'")
    ok({"RECONCILE_MODE", "ORDERS_SINCE", "MAX_DOCS_PER_RUN"} <= xerosync._CONNECTOR_SETTABLE, "the real knobs stay")
    ok("AUTO_RUN_INTERVAL_MINUTES" in xerosync._CONNECTOR_SETTABLE, "Auto Run's interval is one of them (connector 2026-10-21)")
    ok("AUTO_RUN_INTERVAL_MINUTES" in xerosync._CONNECTOR_NUMERIC, "kept as a number there, so 010 reads back as 10")


@test
def t_a_settings_save_the_connector_refuses_is_an_error_not_a_save():
    """Review of 2026-10-21: the connector refuses a whole save for one value
    out of range (an Auto Run interval of 2, say) and keeps nothing. The page
    read that reply, error tucked under data, as "Saved", and anything else
    changed in the same save was silently dropped."""
    ensure_auth()
    real_call = xerosync._connector_call
    async def fake(method, path, params=None, json_body=None):
        return 400, {"error": 'AUTO_RUN_INTERVAL_MINUTES must be a whole number from 5 to 1440 (got "2")'}
    xerosync._connector_call = fake
    old_url = os.environ.get("CONNECTOR_URL")
    os.environ["CONNECTOR_URL"] = "http://conn.railway.internal:8899"
    try:
        r = post("/api/connector", {"op": "settings_save", "fields": {"AUTO_RUN_INTERVAL_MINUTES": "2", "RECONCILE_MODE": "strict"}})
        eq(r.status_code, 400)
        eq(r.json().get("error"), 'AUTO_RUN_INTERVAL_MINUTES must be a whole number from 5 to 1440 (got "2")',
           "the reason is the error itself, which the page shows")
        async def silent(method, path, params=None, json_body=None):
            return 502, None
        xerosync._connector_call = silent
        r2 = post("/api/connector", {"op": "settings_save", "fields": {"RECONCILE_MODE": "strict"}})
        eq(r2.json().get("error"), "Connector error 502", "and a refusal with no reason still says it failed")
    finally:
        xerosync._connector_call = real_call
        if old_url is None:
            os.environ.pop("CONNECTOR_URL", None)
        else:
            os.environ["CONNECTOR_URL"] = old_url


@test
def t_turning_auto_run_on_records_the_interval_the_connector_uses():
    """The interval is a connector setting, AUTO_RUN_INTERVAL_MINUTES (5 to
    1440), so 'every 10 minutes' in the activity log was only true by default."""
    ensure_auth()
    real_call = xerosync._connector_call
    async def fake(method, path, params=None):
        return 200, {"enabled": True, "intervalMinutes": 30, "ticks": 0}
    xerosync._connector_call = fake
    old_url = os.environ.get("CONNECTOR_URL")
    os.environ["CONNECTOR_URL"] = "http://conn.railway.internal:8899"
    try:
        before = len(activity._load_events())
        eq(post("/api/connector", {"op": "autorun_set", "enabled": True}).status_code, 200)
        new = [e for e in activity._load_events()[before:] if e.get("area") == "connector"]
        eq([(e["action"], e["detail"]) for e in new], [("turned Auto Run on", "every 30 minutes")])
    finally:
        xerosync._connector_call = real_call
        if old_url is None:
            os.environ.pop("CONNECTOR_URL", None)
        else:
            os.environ["CONNECTOR_URL"] = old_url



@test
def t_a_refusal_never_overwrites_a_reconnect_that_landed_meanwhile():
    """Review N2, 2026-10-07: recording a refused refresh token in the token
    file must not write over a fresh consent that landed while the refresh was
    in flight (the consent callback writes outside the refresh lock), or the
    new token is lost and the page goes red again after saying connected."""
    saved = (xero_api.httpx.AsyncClient, xero_api.RETRY_WAITS,
             xero_api.CLIENT_ID, xero_api.CLIENT_SECRET)
    xero_api.RETRY_WAITS = (0.0, 0.0)
    xero_api.CLIENT_ID = xero_api.CLIENT_SECRET = "demo"

    class _R:
        status_code = 400
        text = "refused"
        def json(self): return {"error": "invalid_grant"}

    class _C:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, **kw):
            # The consent walk lands while Xero is answering the old refresh.
            xero_api._write_token({"refresh_token": "rt-fresh", "tenant_id": "t1",
                                   "tenant_name": "Projected Image", "connected_at": time.time()})
            return _R()
    xero_api.httpx.AsyncClient = lambda *a, **k: _C()
    try:
        xero_api._write_token({"refresh_token": "rt-dead", "tenant_id": "t1"})
        xero_api._state["access"] = ""
        xero_api._state["access_exp"] = 0.0
        xero_api._state["token_error"] = ""
        err = None
        try:
            run(xero_api._access_token())
        except Exception as e:
            err = e
        ok(err is not None, "the refresh with the old token still fails")
        d = xero_api._load_token()
        eq(d.get("refresh_token"), "rt-fresh", "the fresh consent's token is kept")
        ok("refused_at" not in d, "and is not marked refused")
        ok(xero_api.status().get("needs_reconnect") is False, "so the page shows the link as good: %r" % xero_api.status())
    finally:
        (xero_api.httpx.AsyncClient, xero_api.RETRY_WAITS,
         xero_api.CLIENT_ID, xero_api.CLIENT_SECRET) = saved
        xero_api._state["token_error"] = ""
        xero_api.disconnect()



DOOR_WITH_SHOPS_XML = """<Envelope><Body><GetAllServicesAndRatesResponse>
<GetAllServicesAndRatesResult><Message/><NotificationtType>SUCCESS</NotificationtType><wsRateService>
 <wsAvailableServicesAndRates>
   <wsPackageTypeCode>UPS_My_Packaging</wsPackageTypeCode><wsServiceCode>11</wsServiceCode>
   <wsServiceTypeCode>UPS_Standard</wsServiceTypeCode><wsServiceTypeName>11 Standard</wsServiceTypeName>
   <wsDeliveryDateTime>Tue, 13 Oct 2026&lt;br/&gt;End of business day</wsDeliveryDateTime>
   <wsQuoteDetails><TotalNetCharge>15.35</TotalNetCharge></wsQuoteDetails>
 </wsAvailableServicesAndRates>
 <wsAvailableServicesAndRates>
   <wsPackageTypeCode>DHL_NonDocument</wsPackageTypeCode><wsServiceCode>W</wsServiceCode>
   <wsServiceTypeCode>DHL_ECONOMY_SELECT</wsServiceTypeCode><wsServiceTypeName>W Economy Select</wsServiceTypeName>
   <wsDeliveryDateTime>Tue, 13 Oct 2026&lt;br/&gt;End of business day</wsDeliveryDateTime>
   <wsQuoteDetails><TotalNetCharge>19.35</TotalNetCharge><ServiceType>DHL</ServiceType></wsQuoteDetails>
   <wsDeliveryDropOffShops><wsDropOffShop><Description>DHL ServicePoint Dame St</Description><HouseNo>4</HouseNo><Street>Dame St</Street><City>Dublin</City><PostCode>D02 X285</PostCode><ParcelShopNumber>DUB017</ParcelShopNumber></wsDropOffShop></wsDeliveryDropOffShops>
 </wsAvailableServicesAndRates>
</wsRateService></GetAllServicesAndRatesResult></GetAllServicesAndRatesResponse></Body></Envelope>"""


@test
def t_a_door_service_that_lists_nearby_shops_is_still_a_door_service():
    """Live fault, 2026-10-09: DHL vanished from an Irish order's courier list.
    Missing a service? showed World Options returning ten services, DHL among
    them, while the window showed four. A door quote's DHL and FedEx Economy
    services had started carrying a list of nearby pickup shops, and Reactor read
    any shop list as "delivered to a shop", so with shop services switched off it
    hid them. A service is collect-from-a-shop only when shop delivery was asked
    for or its code says Access Point."""
    reset_dispatch(); reset_prod(); _ship_cfg()
    post("/api/shipping/config", {"op": "set", "show_parcelshop": False})

    async def door(service, action, inner, retryable=True):
        return ET.fromstring(DOOR_WITH_SHOPS_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = door
    try:
        r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
        eq(r.status_code, 200, r.text)
        body = r.json()
        eq(body["show_parcelshop"], False, "shop services are switched off, as live")
        codes = [o["service_type_code"] for o in body["options"]]
        ok("DHL_ECONOMY_SELECT" in codes, "DHL is offered: " + str(codes))
        dhl = [o for o in body["options"] if o["service_type_code"] == "DHL_ECONOMY_SELECT"][0]
        eq(dhl["delivery_dropoff"], False, "to the door, not to a shop")
        eq(dhl["delivery_shops"], [], "and carries no shop for the window to say the customer collects from")
    finally:
        worldoptions._soap_call = saved


