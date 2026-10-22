
def _copilot_src(name):
    """The source of a route defined inside add_routes or an area's register(),
    by name. The routes are closures, so they cannot be reached with getattr."""
    src = copilot_source()
    i = src.index("async def " + name + "(")
    j = src.index("\n    @mcp.custom_route", i)
    return src[i:j]


@test
def t_a_size_rule_only_accepts_something_that_is_a_size():
    """Whatever is stored here is what the bench reads off the label, so free
    text is refused rather than kept."""
    for good, want in [("37.5", "37.5"), ("37.5mm", "37.5"), (" 25 ", "25"), ("12.345", "12.35")]:
        got = size_list._clean_gobo_size(good)
        assert got == want, f"{good!r} should clean to {want!r}, got {got!r}"
    for bad in ("", "0", "-3", "abc", "501", None, "37..5", "big"):
        assert size_list._clean_gobo_size(bad) is None, f"{bad!r} is not a production size"


@test
def t_ruling_a_model_out_actually_stops_it_being_reported():
    """The button says "it is not a gobo, stop reporting it". The exclude set only
    ever skipped rows ALREADY on the sheet, so excluding a model that was never
    there did nothing - the weekly scan kept flagging it while the merchant had
    been told the ruling was saved. The scan has to read the same set."""
    sheet = size_list._gobo_sizes()
    assert "excludes" in sheet, "the exclude set reaches the coverage scan at all"
    assert isinstance(sheet.get("excludes"), set), "as a set of (manufacturer, model) keys"
    import inspect as _i
    cov = _i.getsource(production.run_label_coverage)
    assert 'sheet.get("excludes")' in cov, "and the scan consults it before flagging"
    assert "ruled_out" in cov, "counting a ruled-out item apart from a miss"


@test
def t_a_rule_write_is_atomic_backed_up_and_re_read():
    """These two files decide the glass a real order is cut from."""
    import inspect as _i
    src = _i.getsource(size_list._write_gobo_rule_rows)
    assert "os.replace(tmp, path)" in src, "the live file is swapped in atomically"
    assert ".bak" in src, "and the previous generation is kept"
    assert '_gobo_cache["mtime"] = None' in src, (
        "and the next read reloads: a write plus a lookup inside one clock tick "
        "would otherwise answer from the state before the rule was saved")


@test
def t_only_a_granted_account_may_change_what_the_bench_cuts():
    """Seeing the Labels tab is not the same as deciding the glass an order is
    made from. Admins hold it by rank; everyone else needs the grant."""
    import inspect as _i
    src = _i.getsource(team._may_edit_sizes)
    assert 'u.get("can_sizes")' in src, "the per-person grant is what is checked"
    assert 'ROLE_LEVELS["admin"]' in src, "with admins holding it by rank"
    route = _copilot_src("gobo_rule_route")
    assert "_may_edit_sizes(who)" in route, (
        "and the write route refuses anyone without it, not just the button")


@test
def t_a_saved_rule_reports_what_the_lookup_says_not_what_was_asked():
    """A rule can save cleanly and still leave the model unresolved - an alias
    onto a row that is itself ambiguous, for instance. Saying "done" there would
    send a wrong size to the bench."""
    route = _copilot_src("gobo_rule_route")
    assert "_gobo_lookup(mfr, model)" in route, (
        "the reply re-reads through the same lookup the labels print with")
    assert '"resolves":' in route, "and says whether it actually resolves now"


@test
def t_an_alias_may_not_be_written_onto_a_model_that_does_not_exist():
    """The loader logs a dead alias and moves on, so a typo'd target would leave
    the model still unresolved with a rule that looks like a fix."""
    route = _copilot_src("gobo_rule_route")
    assert "_gobo_lookup(mfr, target)" in route, "the target is checked against the sheet"
    assert "would leave the rule dead" in route, "and refused with a reason if it is not there"


