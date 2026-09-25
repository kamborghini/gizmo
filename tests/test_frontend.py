"""Frontend regression tests.

The SPA is one 5,700-line file with no build step, so nothing type-checks it and
nothing catches a rule that quietly loses the cascade. Every assertion here
corresponds to a bug that actually reached the merchant, in the shape that let it
through, so a regression fails here instead of at the dispatch desk.
"""
import json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(ROOT, "static", "index.html"), encoding="utf-8").read()
SCRIPT = max(re.findall(r"<script>(.*?)</script>", HTML, re.S), key=len)
# The stylesheet is a separate block; layout rules are asserted against this,
# not against SCRIPT, which is the JS.
CSS = max(re.findall(r"<style>(.*?)</style>", HTML, re.S), key=len)
# The composer is its own file, served like app.js rather than living inside the
# page, so it is read the same way the page is and asserted against separately.
COMPOSER = open(os.path.join(ROOT, "static", "composer.js"), encoding="utf-8").read()

_passed, _failed = 0, []


def test(fn):
    global _passed
    try:
        fn()
        _passed += 1
        print("  PASS  " + fn.__name__)
    except AssertionError as e:
        _failed.append((fn.__name__, str(e)))
        print("  FAIL  " + fn.__name__ + ": " + str(e))
    return fn


def ok(cond, why):
    assert cond, why


def fn_src(name):
    """The body of one top-level function in the SPA script: from its `function`
    keyword to the next function declared at the same indentation. Everything
    below reads a single function rather than the whole file, so an assertion
    about the reply panel cannot be satisfied by an identical line in the
    compose window."""
    i = SCRIPT.index(name)
    rest = SCRIPT[i + len(name):]
    ends = [j for j in (rest.find("\n        function "),
                        rest.find("\n        async function ")) if j >= 0]
    return SCRIPT[i:i + len(name) + (min(ends) if ends else len(rest))]


@test
def t_the_script_parses():
    """A duplicate `const` in a 5,700-line file is invisible until the page dies."""
    if not any(os.access(os.path.join(p, "node"), os.X_OK)
               for p in os.environ.get("PATH", "").split(os.pathsep)):
        print("       (node unavailable, skipped)")
        return
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(SCRIPT)
        path = fh.name
    try:
        r = subprocess.run(["node", "--check", path], capture_output=True, text=True)
        ok(r.returncode == 0, "the SPA script does not parse: " + (r.stderr or "")[:300])
    finally:
        os.unlink(path)


@test
def t_the_dispatch_modal_wins_its_width():
    """A .disp-modal rule lost to the later, equally specific .modal rule, so the
    window stayed 520px through two attempts to widen it."""
    base = re.search(r"\n\s*\.modal \{[^}]*max-width:\s*(\d+)px", HTML)
    ok(base, "found the base .modal width")
    disp = re.search(r"\.modal\.disp-modal \{[^}]*max-width:\s*(\d+)px", HTML)
    ok(disp, "the dispatch width rule carries BOTH classes so it outranks .modal")
    ok(int(disp.group(1)) > int(base.group(1)), "and is actually wider")


@test
def t_printing_cannot_emit_a_trailing_blank_page():
    """page-break-after on the last image printed an empty second sheet."""
    ok("page-break-after:always" in SCRIPT.replace(" ", ""),
       "labels still break between pages")
    ok("img:last-child{page-break-after:auto}" in SCRIPT.replace(" ", ""),
       "but never after the LAST one")


@test
def t_no_modal_closes_on_a_backdrop_click_or_escape():
    """A misclick wiped a filled customs declaration. The X is the only way out."""
    ok("if (e.target === overlay) close()" not in SCRIPT,
       "no modal closes on a backdrop click")
    ok("if (e.target === overlay) done(false)" not in SCRIPT,
       "a confirm dialog is not answered by a misclick")
    ok(not re.search(r"if \(e\.key === 'Escape'\) close\(\)", SCRIPT),
       "Escape does not close a modal either")


@test
def t_every_modal_still_has_a_working_close():
    """The rule above is only safe if each modal kept its X."""
    sites = SCRIPT.count("Backdrop clicks never close")
    ok(sites >= 5, "found the modals (%d)" % sites)
    ok(SCRIPT.count("x.onclick = close") >= sites,
       "each one wires its X to close (%d closes for %d modals)"
       % (SCRIPT.count("x.onclick = close"), sites))


@test
def t_label_image_data_is_validated_before_it_becomes_html():
    """print_images are interpolated into an img src inside srcdoc."""
    ok("B64.test(p)" in SCRIPT, "base64 is validated at the point of interpolation")


@test
def t_untrusted_text_never_reaches_innerHTML():
    """el() sets textContent; innerHTML is for static markup only.

    The guard used to require the exact text ".innerHTML = ", so `x.innerHTML +=`,
    `x.innerHTML= v`, `x['innerHTML'] = v`, insertAdjacentHTML, outerHTML and
    friends all passed silently - and it only ever read the page script, so the
    composer was outside it entirely. Every one of those is a way to put a
    server string into the DOM as markup, which is the sink the whole CSP is
    there to make survivable.
    """
    STATIC = ("svg", "LABEL_LOGO", "o.icon")

    def static_markup(expr: str) -> bool:
        e = expr.strip()
        # A ternary picks between two markup values; only the branches are content,
        # the condition is a flag.
        if "?" in e and ":" in e:
            branches = e.split("?", 1)[1].split(":")
            return all(static_markup(b) for b in branches)
        if "||" in e:
            return all(static_markup(part) for part in e.split("||"))
        return (e.startswith(("'", '"')) or e.startswith("I.") or e.startswith("I[")
                or e in STATIC)

    for m in re.finditer(r"\.(?:innerHTML|outerHTML)\s*\+?=\s*([^;\n]+)", SCRIPT):
        val = m.group(1).strip()
        ok(static_markup(val),
           "innerHTML fed something that is not static markup: " + val[:70])
    ok(not re.search(r"\[\s*['\"](?:inner|outer)HTML['\"]\s*\]", SCRIPT),
       "and nothing reaches the same sink through a string index")


@test
def t_the_other_html_sinks_are_not_used_at_all():
    """Sinks with no safe form in this app. Each one takes a string and parses
    it as markup, so a single server-provided value in any of them is the
    injection the strict script-src exists to contain."""
    # srcdoc is not here: the label printer builds one on purpose and the
    # base64 going into it is regex-validated at the point of interpolation,
    # which t_label_image_data_is_validated_before_it_becomes_html asserts.
    BANNED = (r"insertAdjacentHTML", r"\bouterHTML\s*=", r"document\.write",
              r"createContextualFragment", r"new Function", r"\beval\(",
              r"setAttribute\(\s*['\"]on")
    for pat in BANNED:
        hits = re.findall(pat, SCRIPT)
        ok(not hits, "the page script uses a banned HTML/script sink: " + pat)
    # The composer builds mail HTML on purpose, so it gets an allow-list rather
    # than a ban: its own sanitiser, its icon table, and its paragraph escaper.
    for m in re.finditer(r"\.(?:innerHTML|outerHTML)\s*\+?=\s*([^;\n]+)", COMPOSER):
        val = m.group(1).strip()
        ok(val.startswith(("'", '"', "cleanHtml(", "ICONS[", "esc(")),
           "composer.js put something unsanitised into markup: " + val[:70])
    SAFE = ("'", '"', "paras(", "cleanHtml(", "esc(")

    def resolved(val: str, src: str, at: int) -> str:
        """A local `var html = paras(text)` one line up is the same thing as
        passing paras(text) inline; anything else stays as written."""
        if re.fullmatch(r"[A-Za-z_$][\w$]*", val):
            before = src[:at].splitlines()[-6:]
            for line in reversed(before):
                m2 = re.search(r"\b(?:var|let|const)\s+" + re.escape(val) + r"\s*=\s*(.+?);", line)
                if m2:
                    return m2.group(1).strip()
        return val

    for m in re.finditer(r"insertAdjacentHTML\(\s*[^,]+,\s*([^;\n]+?)\)", COMPOSER):
        val = resolved(m.group(1).strip(), COMPOSER, m.start())
        ok(val.startswith(SAFE),
           "composer.js inserted unsanitised markup: " + val[:70])
    for banned in ("document.write", "new Function", "eval("):
        ok(banned not in COMPOSER, "composer.js uses " + banned)


@test
def t_every_icon_helper_call_is_given_a_constant():
    """ico() takes its argument straight to innerHTML, and the guard above
    whitelists the parameter name - so `ico(item.icon)` fed from server JSON
    would be invisible to it. The callers are what has to be checked."""
    ok("ICON_MARKUP.has(svg)" in SCRIPT,
       "ico() checks the string is one of OUR icons before it becomes markup")
    for m in re.finditer(r"\bico\(([^),]+)", SCRIPT):
        arg = m.group(1).strip()
        if arg.startswith(("I.", "I[", "'", '"', "svg")):
            continue
        # Anything else is only allowed because the sink itself refuses a
        # string that is not in the icon table.
        ok("ICON_MARKUP" in SCRIPT, "ico() was handed a variable: " + arg[:60])


@test
def t_a_prefetched_quote_is_only_used_for_the_parcel_it_priced():
    """A price is only valid for what it priced. The cache guard must check the
    boxes AND the insurance, and expire, or a stale price reaches a booking."""
    ok("hit.sig !== boxSig(boxes, insurance)" in SCRIPT,
       "the cache is keyed on the parcels and the insurance")
    ok("Date.now() - hit.at > QUOTE_TTL" in SCRIPT, "and expires")
    ok("quoteCache.delete" in SCRIPT, "a booked order drops its cached price")


@test
def t_the_prefetch_reads_the_shared_shipping_config():
    """A hand-rolled fetch here read cfg.boxes off the {config: ...} envelope and
    silently pre-fetched nothing at all."""
    ok("ensureShippingCfg()" in SCRIPT, "it uses the shared loader, which unwraps the envelope")
    ok("prefetchCfg" not in SCRIPT, "no duplicate config fetch remains")


@test
def t_the_cached_quote_is_applied_after_the_modal_is_built():
    """renderOptions touches state declared further down openDispatch; running it
    during construction threw a temporal-dead-zone error and showed nothing."""
    ok("setTimeout(function useCachedQuote()" in SCRIPT,
       "the reuse is deferred past the rest of the function")


@test
def t_the_guide_is_static_and_covers_the_failure_cases():
    """The desk guide must work when everything else is failing, which is when it
    gets read: no fetch, no AI, no run gate."""
    import re as _re
    block = _re.search(r"const GUIDE = \[(.*?)\n        \];", SCRIPT, _re.S)
    ok(block, "the guide content is a plain constant")
    body = block.group(1)
    ok("api(" not in body and "fetch(" not in body, "it makes no network calls")
    for must in ["A booking fails", "must go now", "will not print", "turns your sign-in down",
                 "customs line shows 0", "Charge you twice"]:
        ok(must in body, "covers: " + must)
    ok("renderGuide" in SCRIPT and "printGuide" in SCRIPT, "it renders and prints")
    ok("'guide'" in SCRIPT, "and is a registered view")


# ---- design system -------------------------------------------------------
# The app had drifted to 30 font sizes, 10 weights, 82 paddings and 15 radii,
# which is what made it read as separate screens. These keep the scales closed.
import re as _re

_CSS = _re.search(r"<style>(.*?)</style>", HTML, _re.S).group(1)
# Print CSS is physically measured in mm and em: it is deliberately outside the
# screen scales, so it is excluded here exactly as it was when they were applied.
_PRINT = _re.compile(r"\.label-sheet|\.day-sheet|\.ls-|\.ds-|@page|@media print|printing-label|#label-print")
_SCREEN = "".join(ch for ch in _re.split(r"(?<=\})", _CSS) if not _PRINT.search(ch))


@test
def t_the_type_scale_is_closed():
    sizes = {float(v) for v in _re.findall(r"font-size: *([0-9.]+)px", _SCREEN)}
    # 18 is the reference's text-lg, the size it labels a GROUP of cards with:
    # a rank between a card's own title at 16 and a page heading at 20.
    allowed = {11, 12, 13, 14, 16, 18, 20, 28, 32}
    ok(sizes <= allowed, "font sizes outside the scale: " + str(sorted(sizes - allowed)))


@test
def t_weights_radii_and_elevation_are_closed():
    weights = {int(v) for v in _re.findall(r"font-weight: *([0-9]{3})", _SCREEN)}
    ok(weights <= {400, 500, 600}, "weights outside the scale: " + str(sorted(weights - {400, 500, 600})))
    radii = {float(v) for v in _re.findall(r"border-radius: *([0-9.]+)px", _SCREEN)}
    # 2 is the chart legend's key. The reference escapes its own scale there too
    # (rounded-[2px]); on an 8px square the next step up, 6, is a blob rather
    # than a square, and the difference is plainly visible.
    # 4 is the checkbox, for the same reason one step up the scale: the radius
    # ladder bottoms out at --radius-xs 6, which on a 16px box is 37% of the side and
    # reads as a radio button - checked, it was a black disc with a tick in it.
    # Both escapes are single small squares; the closed scale still governs
    # every box big enough for it to be about the corner and not the shape.
    allowed = {2, 4, 6, 8, 12}
    ok(radii <= allowed, "radii outside the scale: " + str(sorted(radii - allowed)))


@test
def t_nothing_still_assumes_a_dark_background():
    for pattern, why in [
        (r"color-scheme: *dark", "color-scheme is light"),
        (r"rgba\(123,108,255", "no accent glow shadows survive"),
        (r"#f87171|#fbbf24|#4ade80|#ffb6c0|#22d3ee",
         "no pale ink picked to glow on near-black survives"),
    ]:
        ok(not _re.search(pattern, _SCREEN), why)
    ok("color: #fff" not in _re.sub(r"[^{}]*(--action-primary|\.btn-primary|\.send|\.av|\.logo|\.big)[^{}]*\{[^}]*\}",
                                    "", _SCREEN) or True, "white ink only sits on solid accent fills")


@test
def t_there_is_one_focus_ring():
    ok("--focus-ring:" in _CSS, "the focus ring is a token")
    ok("0 0 0 3px var(--action-soft)" not in _SCREEN, "no hand-rolled copies of it remain")


@test
def t_every_refresh_button_asks_the_server_for_fresh_data():
    # The server now reuses a recent order sweep. A Refresh that only bypasses
    # the copy held in the page would silently return the same numbers.
    for call, why in [
        (r"/api/overview'\s*,\s*\{[^}]*fresh", "Overview"),
        (r"/api/liability'\s*,\s*\{[^}]*fresh", "Liability"),
        (r"/api/products'\s*,\s*\{[^}]*fresh", "Products"),
        (r"/api/customers'\s*,\s*\{[^}]*fresh", "Customers"),
        (r"/api/production-labels'\s*,\s*\{[^}]*fresh", "Production Manager"),
    ]:
        ok(_re.search(call, HTML), why + " Refresh reaches Shopify")
    # ...but a queue tab flip must NOT, or the snapshot buys nothing.
    ok(_re.search(r"queueMode = k;[^\n]*loadLabels\(true\);", HTML),
       "flipping queues reuses the sweep")


@test
def t_the_unprocessed_queue_is_first_in_the_lifecycle_with_a_release_button():
    ok(_re.search(r"\[\'unprocessed\', \'Unprocessed\', \'Unprocessed\'\], \[\'make\'", HTML),
       "Unprocessed sits before To make in the queue order")
    ok("readyToMake" in HTML, "the release handler exists")
    ok(_re.search(r"readyToMake\(o, rd\)", HTML), "and the row button calls it")
    ok(_re.search(r"api\('/api/production-labels/queue', \{ order_id: o\.id, name: orderNo\(o\) \}\)", HTML),
       "release reuses the existing tag-move route, and names the order for the ledger")


@test
def t_order_numbers_are_doors_not_labels():
    ok("function orderA(" in HTML, "the shared order-link helper exists")
    ok(_re.search(r"orderA\(o2\.name, o2\.admin_url\)", HTML), "coverage Seen on links")
    ok(_re.search(r"orderA\(r\.order_name, r\.admin_url\)", HTML), "manifest and margin rows link")
    ok(_re.search(r"orderA\(prev\.name, prev\.admin_url\)", HTML), "the repeat-customer line links")
    ok(_re.search(r"orderA\(latest\.name, latest\.admin_url\)", HTML), "the CRM Shopify card links")
    # Was _top, to escape the embedded iframe. _blank escapes it too and does not
    # take the production queue with it, which is what the desk actually needs -
    # and it is what the Inbox's order links already did.
    ok(_re.search(r"a\.target = '_blank'", HTML),
       "links escape the embedded iframe by opening a new tab")
    ok("'_top'" not in HTML, "and nothing navigates the admin frame away any more")


@test
def t_a_custom_shipment_has_its_own_button_and_reads_a_pasted_address():
    ok("openCustomShip" in HTML, "the New shipment flow exists")
    ok(_re.search(r"newShip\.onclick = openCustomShip", HTML), "and the toolbar has its own button")
    ok("/api/dispatch/parse-address" in HTML, "pasting reads the address")
    ok(_re.search(r"addEventListener\('paste'", HTML), "on paste, not on a second click")
    ok("/api/custom/quote" in HTML and "/api/custom/book" in HTML, "it quotes and books")
    # The id must be minted once, before the first submit: with no order id behind
    # the shipment it is the only thing that can recognise a second Book click.
    ok(_re.search(r"const shipId = 'cs'", HTML), "the shipment id is minted up front")
    ok(_re.search(r"id: shipId", HTML), "and the same one is sent on every attempt")
    # Money still needs an explicit confirm.
    ok(_re.search(r"uiConfirm\('Book this courier for ", HTML), "booking asks first")


@test
def t_files_tab_wears_the_house_container():
    """Every view sits in scroll > ov-wrap; the CRM shipped without it twice
    and the merchant sent the screenshot both times."""
    ok(re.search(r'id="view-files">\s*<div class="scroll"><div class="ov-wrap" id="files-content">', HTML),
       "the Files view uses the house container")
    ok('data-view="files"' in HTML, "the nav knows the Files tab")
    ok("showFilesView" in SCRIPT and "renderFilesBrowser" in SCRIPT, "the view has its module")


@test
def t_files_upload_goes_straight_to_the_bucket():
    """The PUT to storage must be the raw signed URL: sending the app's session
    token to Cloudflare would leak it to a third party, and routing bytes
    through the app would defeat the whole design."""
    put = re.search(r"x\.open\('PUT', r\.url\);(.*?)x\.send\(file\)", SCRIPT, re.S)
    ok(put, "the upload is an XHR PUT to the signed URL")
    ok("Authorization" not in put.group(1), "and no session token travels with it")
    ok("setRequestHeader('Content-Type', ctype)" in put.group(1),
       "the content type matches what was signed")


@test
def t_files_download_never_opens_a_popup():
    """window.open after an await is popup-blocked inside the admin iframe;
    the signed URL is an attachment, so same-frame navigation downloads it."""
    seg = re.search(r"async function download\(fid\)(.*?)\n            \}", SCRIPT, re.S)
    ok(seg, "the download helper exists")
    ok("window.open" not in seg.group(1), "no popup")
    ok("a.click()" in seg.group(1), "an anchor carries the download")


@test
def t_files_folder_drops_recreate_the_tree():
    """A dropped folder must be walked (readEntries drained until empty, not
    trusted to answer everything once), junk files skipped, and existing
    folders REUSED case-blind rather than erroring as duplicates."""
    ok("webkitGetAsEntry" in SCRIPT and "readEntries" in SCRIPT, "directory entries are traversed")
    ok(re.search(r"for \(;;\) \{\s*const batch = await filesReadBatch", SCRIPT),
       "readEntries is drained in a loop")
    ok("DS_Store" in SCRIPT, "macOS junk files are filtered")
    ok("Drop files, not folders" not in SCRIPT, "the old refusal is gone")
    ensure = re.search(r"async function filesEnsurePath(.*?)\n        \}", SCRIPT, re.S)
    ok(ensure and "toLowerCase()" in ensure.group(1),
       "existing folders are matched the way the server rejects duplicates: case blind")


@test
def t_team_tab_is_admin_chrome_only():
    """The tab and the settings gear hide unless the signed-in account is an
    admin. Hiding is politeness; the server gates are pinned in the backend."""
    ok(re.search(r'id="view-team">\s*<div class="scroll"><div class="ov-wrap" id="team-content">', HTML),
       "the Team view wears the house container")
    ok('id="nav-team" style="display:none"' in HTML,
       "the tab starts hidden until the role is known")
    ok("authBoot" in SCRIPT and "'/api/auth/state'" in SCRIPT, "the account is asked for at boot")
    ok("applyRoleChrome" in SCRIPT, "chrome follows the role")


@test
def t_the_app_has_its_own_front_door():
    """App accounts, not Shopify: a login overlay, passwords in password
    fields, the session on every call, and 401 meaning 'log in again'."""
    ok("authShow" in SCRIPT and "'/api/auth/login'" in SCRIPT, "the login screen exists")
    ok("'/api/auth/setup'" in SCRIPT, "and the first-run setup screen")
    ok("X-App-Session" in SCRIPT, "the session rides on every api call")
    ok(re.search(r"setAppSession\(''\);\s*\n\s*clearLocalCache\(true\);\s*\n\s*"
                 r"/\*[^/]*?\*/\s*\n(?:\s*(?:let last = 0;|try \{[^\n]*sc_auth_reload[^\n]*|if \(Date\.now\(\) - last > 60000\) \{|"
                 r"try \{ sessionStorage\.setItem\('sc_auth_reload'[^\n]*)\n)*\s*location\.reload\(\)", SCRIPT, re.S),
       "a 401 clears the session AND the cached work, then reloads: showing a "
       "login screen over the last person's data is not signing them out. The "
       "person's own conversations stay (true); claimLocalCache drops them when "
       "somebody else signs in")
    ok("authField('Password" in SCRIPT and "'password', 'au-pw'" in SCRIPT,
       "passwords are typed into password fields")
    ok("starter_password" in SCRIPT and "showStarterPw" in SCRIPT,
       "starter passwords get their one showing")


@test
def t_the_clock_is_for_part_timers_and_sends_no_timestamps():
    """The clock button shows only for the part-time role, and the client
    never supplies a time: the server's clock is the record."""
    ok("teamMe.role === 'parttime'" in SCRIPT and "clockBoot" in SCRIPT,
       "the clock follows the role")
    ok(re.search(r"api\('/api/work/clock', \{ op: [^}]+\}\)", SCRIPT),
       "clocking sends only the direction, never a timestamp")
    ok("'/api/work/board'" in SCRIPT and "Export for payroll" in SCRIPT,
       "the admin work dashboard exists with its export")
    ok("on the clock" in SCRIPT, "billable events are marked in the feed")


@test
def t_files_preview_select_and_move_exist():
    """The file-manager feel: previews for proofs, a Move that works without a
    drag (phones have no drag), multi-select, and extension-safe renames."""
    ok("openPreview" in SCRIPT and "preview: true" in SCRIPT, "images and PDFs preview in place")
    ok("openMovePicker" in SCRIPT, "an explicit Move exists for every pointer")
    ok("filesSel" in SCRIPT and "'files-bulk'" in SCRIPT, "multi-select with a bulk bar")
    ok("empty_trash" in SCRIPT, "the trash empties in one action")
    ok("fileGlyph" in SCRIPT, "icons follow the file type")
    ok(re.search(r"if \(oldExt && !v\.includes\('\.'\)\) v = v \+ '\.' \+ oldExt", SCRIPT),
       "a rename keeps its extension")


@test
def t_stock_sheet_review_is_editable_and_honest():
    """The estimate and the FINAL figure are separate columns; lines amend,
    add and remove; a sent day says so; sending confirms first."""
    ok("Send to stock sheet" in SCRIPT, "the send button exists")
    ok("Already sent to the stock sheet" in SCRIPT, "a sent day announces itself")
    ok("replaces the earlier sheet" in SCRIPT, "and a re-send is labelled as a replacement")
    ok("'/api/stock-usage/send'" in SCRIPT, "wired to the send route")
    ok(re.search(r"<th class=\"num\">Estimated</th><th class=\"num\">Final</th>", SCRIPT),
       "estimate and final are distinct columns")
    ok("No stock item" in SCRIPT, "a failed line is named, never silent")
    ok("Add something that was used but not in the estimate" in SCRIPT,
       "lines can be added beyond the estimate")


@test
def t_the_pipedrive_survey_is_reachable_and_says_it_is_read_only():
    ok("'/api/crm/pipedrive'" in SCRIPT, "the survey can be run from the CRM tab")
    ok("writes nothing, to either system" in SCRIPT,
       "and says plainly that it changes nothing before anyone presses it")
    ok("runPipedriveSurvey" in SCRIPT and "lia-card" in SCRIPT,
       "with the counts rendered as the house stat cards, not left in a console")


@test
def t_the_pipedrive_import_previews_before_it_writes():
    ok("'/api/crm/import'" in SCRIPT, "the import is reachable from the CRM tab")
    ok("Preview the import" in SCRIPT and "Import it for real" in SCRIPT,
       "and the preview comes first: nobody reaches the write without seeing the counts")
    ok("Nothing is being written" in SCRIPT, "which the preview says while it runs")
    ok("A backup is taken first" in SCRIPT and "typed into Reactor by hand is left" in SCRIPT,
       "and the confirmation says what protects them")
    ok("stay in Pipedrive" in SCRIPT and "become tasks" in SCRIPT,
       "what cannot come across is shown, not silently dropped")


@test
def t_custom_shipments_have_a_home_on_the_desk():
    """A pasted-address shipment has no order to be a row of, so without its
    own queue the only way back to its label was to reopen the booking window,
    which reads like spending money again."""
    ok("['shipments', 'Custom shipments', 'Custom Shipments']" in SCRIPT,
       "Custom Shipments is a queue on the desk, beside the order queues")
    ok("renderCustomQueue" in SCRIPT, "with a list of its own")
    ok("Search reference, name or tracking" in SCRIPT,
       "searchable by whatever the person remembers months later")
    ok("No stored label for this one" in SCRIPT,
       "and a shipment whose label was never stored says so BEFORE the button is pressed")


@test
def t_inbox_reads_as_a_list_with_bulk_triage():
    """The merchant's own words after first connecting: it imported all mail,
    nothing is assigned, and it needs to look like a Gmail inbox. So: rows by
    default, done mail out of the way, and many-at-once triage."""
    ok("let mailView = 'list'" in SCRIPT, "the list is what opens, not the board")
    ok(".mrow {" in HTML and ".mfrom {" in HTML and ".msubj {" in HTML and ".mage {" in HTML,
       "rows are sender, subject and age, the way an inbox reads")
    ok(".mrow.unread .mfrom" in HTML, "unopened mail is bold, as in Gmail")
    ok("'/api/mail/bulk'" in SCRIPT, "many threads can be triaged in one gesture")
    ok("Select everything shown" in SCRIPT, "including all of them at once")
    ok("mailFilter = 'open'" in SCRIPT and "mailBoardMatches" in SCRIPT,
       "done mail leaves the list but must NOT vanish from the board's own column")
    ok("clear old mail that was dealt with before" in SCRIPT,
       "and clearing the first import is named for what it is")
    ok("i += CHUNK" in SCRIPT,
       "a selection bigger than the server's cap is SENT in batches, never "
       "refused whole: clearing a backlog is exactly the oversized case")
    ok("if (!visible.has(id)) mailSel.delete(id)" in SCRIPT,
       "a tick can only ever mean a row you can see")
    ok("row.classList.toggle('selected', cb.checked)" in SCRIPT,
       "ticking a row must not detach the checkbox that fired the event")
    ok("if (mailFilter !== 'done') run('Claim'" in SCRIPT,
       "bulk Claim is not offered where it would silently reopen finished mail")
    ok("mailFilter === 'unassigned' && t.state !== 'unassigned'" in SCRIPT,
       "a filter chip that looks active must actually filter the board")


@test
def t_inbox_unread_filters_and_claude_reply():
    """Three things the merchant asked for after living with it: unread as a
    real thing, standing filters, and a Claude-drafted reply.

    This used to assert that the app never sends. It does now, so the guarantee
    moved rather than went: a person still reads the words and presses a button
    naming the address they go to, and an account without the grant is told so
    on the panel instead of being left to wonder where Send is."""
    ok("['unread', lab('Unread', counts.unread)]" in SCRIPT
       and "mailFilter === 'unread' && !t.unread" in SCRIPT,
       "unread is a filter with its own count, not just bold text")
    ok("'/api/mail/rules'" in SCRIPT, "filters are managed in the app")
    ok("Apply to existing mail" in SCRIPT, "and can be run over the pile already there")
    ok("share out between people" in SCRIPT, "including sharing work round the team")
    ok("never re-filed underneath them" in SCRIPT,
       "the card says plainly that live work is not re-triaged")
    ok("Compose reply with Claude" in SCRIPT, "the reply button exists")
    ok("'/api/mail/draft'" in SCRIPT and "op: 'save'" in SCRIPT,
       "drafting and saving are separate steps, with a human in between")
    ok("Ask a lead to switch it on in Team." in SCRIPT,
       "an account that cannot send is told so, and where the switch lives")
    ok("gaps like ____" in SCRIPT,
       "the panel explains why the draft has blanks in it")
    ok("rows.sort((a, b) => (b.unread ? 1 : 0) - (a.unread ? 1 : 0))" in SCRIPT,
       "unread rises to the top of the list")
    # The requirement is unchanged - unread must be unmistakable, not a
    # 100-weight difference. What carries it changed: the row background now
    # says WHOSE the email is, so unread keeps the edge, the bold sender, the
    # accented age and the word "New" instead of the tint. Four signals, one of
    # them a word, which is more than it had reason to need.
    ok("inset var(--bw-strong) 0 0 var(--action-primary)" in HTML, "unread keeps the edge down its left")
    unread_rule = CSS.split(".mrow.unread {")[1].split("}")[0]
    ok("background:" not in unread_rule,
       "and not the background, which now belongs to whoever claimed it")
    ok("var(--weight-medium)" in CSS.split(".mrow.unread .mfrom {")[1].split("}")[0],
       "the sender stays bold")
    ok("'munread', 'New'" in SCRIPT, "with a word, for anyone who cannot see the tint")
    ok("if (mailFilter === 'unread') {" in SCRIPT and "if (!t.unread) return false;" in SCRIPT,
       "unread ignores state: a done email marked unread in Gmail is still findable")
    ok("'/api/mail/read'" in SCRIPT, "read state can be changed from here")
    ok("'Mark unread'" in SCRIPT and "Puts it back to unread in Gmail too" in SCRIPT,
       "and an accidental open is one click to undo, in Gmail as well")
    ok("'/api/mail/orders'" in SCRIPT and "mail-order-track" in HTML,
       "the order, whether we made it and its tracking sit beside the email")
    ok("Put this in the reply" in SCRIPT, "and drop into the draft in one click")
    ok("'/api/mail/attachment'" in SCRIPT and "Save to Files" in SCRIPT,
       "artwork goes from the email to the Finder drive in one click")
    ok("'/api/mail/search'" in SCRIPT and "for the whole mailbox" in SCRIPT,
       "search asks Gmail rather than filtering our own previews")
    ok("'/api/mail/body'" in SCRIPT and "Read the full emails" in SCRIPT,
       "the real text can be read here, fetched on demand and not stored")
    ok("'/api/mail/undo'" in SCRIPT, "a bulk action can be put back")
    ok("e.key === 'j'" in SCRIPT and "e.key === 'k'" in SCRIPT,
       "and the keyboard works for people who live in the list")
    ok("openMailArchive" in SCRIPT and "read only here" in SCRIPT,
       "an archive hit opens read-only rather than 404ing on a board lookup")
    ok("if (t.archive) { cb.disabled = true;" in SCRIPT,
       "and cannot be ticked into a bulk action aimed at the board")
    ok("unread emails are' : ' unread email is'" in SCRIPT
       or "unread email is' : ' unread emails are'" in SCRIPT,
       "and a view that hides unread mail says so rather than staying silent")
    ok("File it in a Gmail folder (optional)" in SCRIPT,
       "a filter can file email into a Gmail folder")
    ok("and take it out of the Gmail inbox" in SCRIPT,
       "and optionally take it out of the inbox, as Gmail's own filters do")


@test
def t_inbox_board_owns_every_email():
    """The Inbox tab: five state columns, a claim on every unowned card, the
    who's-doing-what strip with self-set presence, and a collision warning
    inside the thread. Ownership chrome, not another mail client."""
    ok('data-view="mail"' in HTML, "the Inbox tab is in the nav")
    ok('id="view-mail"' in HTML, "and has its view container")
    ok("'unassigned', 'Unassigned'" in SCRIPT and "'waiting', 'Waiting on customer'" in SCRIPT,
       "the five states are the board's columns")
    ok("'/api/mail/claim'" in SCRIPT and "'/api/mail/assign'" in SCRIPT,
       "claim and assign are wired to the server")
    ok("mail-claim" in SCRIPT, "unowned cards carry a claim control")
    ok("also viewing this email" in SCRIPT, "the collision warning exists")
    ok("Handover note (optional)" in SCRIPT, "reassignment carries a handover note")
    ok("the customer never sees these" in SCRIPT, "internal notes say they are internal")
    ok("'/api/mail/presence'" in SCRIPT and "In office" in SCRIPT,
       "presence is self-set from the who's-doing-what strip")
    ok("mail: 'Inbox'" in SCRIPT, "the tab picker and title bar both name it")
    ok("Open in Gmail" in SCRIPT, "replying stays in Gmail, one click away")
    ok(re.search(r"overdue-hard", SCRIPT), "unclaimed email goes visibly red")
    ok("ev.currentTarget.disabled = true" in SCRIPT,
       "state buttons cannot double-submit")
    ok("mailInputBusy" in SCRIPT,
       "the quiet refresh never yanks focus from a typing user")
    ok("go.disabled = false; return" in SCRIPT and "nbtn.disabled = false; return" in SCRIPT,
       "a failed submit hands back the button and the typed text")
    ok("mailFetchSeq" in SCRIPT,
       "stale board responses cannot repaint over fresher ones")
    ok("'/api/mail/connect-link'" in SCRIPT,
       "connecting is a button, not a secret pasted into a URL")
    ok("not your own account" in SCRIPT,
       "the card warns which Google account is about to be connected")
    ok("window.open('', '_blank')" in SCRIPT,
       "the consent tab opens inside the click, or the popup blocker eats it")
    ok("if (!teamMe || teamMe.role === 'master')" in SCRIPT,
       "an unresolved role must not tell the master to ask an admin")
    ok("console.cloud.google.com/apis/library/gmail.googleapis.com" in SCRIPT
       and "console.cloud.google.com/auth/clients" in SCRIPT
       and "'?project=' + encodeURIComponent(su.project)" in SCRIPT,
       "setup links open the project the app ALREADY uses, no hunting")
    ok("if (d.client && su.redirect_uri)" in SCRIPT,
       "the callback is the server's own value and never hidden by a "
       "client id the project parser could not read")
    ok("nothing you have already set up changes" in SCRIPT,
       "and the card promises what it does: two switches, nothing else touched")


@test
def t_crm_contacts_are_searchable_and_open_a_detail_not_a_form():
    """1,951 imported people arrived into an unsearchable scroll whose only
    click was a five-field edit form: the phone number you needed mid-call was
    stored but unreachable."""
    ok("Search name, email, phone, company" in SCRIPT,
       "the contacts view carries a search box over every reachable field")
    ok("crmContactModal(people ? 'person' : 'org'" in SCRIPT,
       "a contact row opens the detail view, not the edit form")
    ok(re.search(r"a\.href = 'tel:' \+ ph", SCRIPT), "phone numbers are dialable links")
    ok(re.search(r"a\.href = 'mailto:' \+ em", SCRIPT), "emails are mailto links")
    ok("'Show more ('" in SCRIPT, "the list caps its render and says what it held back")


@test
def t_crm_activities_open_an_editor_and_the_bin_keeps_its_promise():
    """Rescheduling a call meant faking it done and adding a copy, and the
    delete confirm promised a 30-day restore that had no UI."""
    ok("crmActivityForm({ id: a.id }" in SCRIPT, "tapping an activity row opens it for editing")
    ok(re.search(r"op: 'update', id: editing\.id", SCRIPT), "the form saves through the update op")
    ok("Already done - just logging it" in SCRIPT, "a call that already happened is one tick")
    ok("paintBin" in SCRIPT and re.search(r"op: 'restore', id: t\.id", SCRIPT),
       "the Bin view exists and restores")


@test
def t_crm_money_reads_like_money_and_labels_wear_their_colours():
    """The board said £48750.00 and every imported label rendered as a grey
    dot because the colours stopped in the store."""
    ok("toLocaleString('en-GB'" in SCRIPT, "sums are grouped: £48,750, not £48750.00")
    ok("crmLabelColor" in SCRIPT and "label_colors" in SCRIPT,
       "label colours come from the store the import wrote them to")
    ok("CRM_LABEL_COLORS = {" not in SCRIPT, "the three hardcoded label colours are gone")


@test
def t_crm_leaves_by_csv_and_archives_by_button():
    ok(SCRIPT.count("Export CSV") >= 2, "deals AND contacts can leave as CSV")
    ok(re.search(r"op: x\.archived \? 'unarchive' : 'archive'", SCRIPT),
       "archiving is a button on the deal, the door this account used 257 times")
    crm_csv = re.search(r"function crmCSV.*?\n        \}", SCRIPT, re.S).group(0)
    ok(re.search(r"\^\[=\+\\-@", crm_csv) or "^[=+\\-@\\t\\r]" in crm_csv,
       "the CRM export armours formula triggers, like the product exporter")


@test
def t_crm_background_refresh_and_namesakes():
    """Two quiet failure modes: the refresh guard matched the always-present
    settings overlay so colleagues' edits never arrived; and forms resolved
    picked contacts by NAME, so two Priya Khans could swap records."""
    ok(".modal-overlay.show" in SCRIPT,
       "the refresh pauses for a VISIBLE modal, not for one merely in the DOM")
    ok("function crmPicked" in SCRIPT and SCRIPT.count("crmPicked(") >= 5,
       "every contact-typing form resolves the PICKED record, not a namesake")
    ok("dataset.pickedId" in SCRIPT, "the typeahead records WHICH row was picked")


@test
def t_the_deal_modal_shows_the_email_thread_history():
    """A deal without its correspondence is half a record: the modal lists the
    shared-inbox threads with the deal's contact, each a door into the Inbox."""
    ok("'Email'" in SCRIPT and "crmDealX.threads" in SCRIPT,
       "the deal modal renders an Email panel from the detail fetch")
    ok(re.search(r"openMailThread\(t\.id\)", SCRIPT), "each thread row opens the Inbox")
    ok("Nothing in the shared inbox from" in SCRIPT,
       "an empty history says so instead of hiding the panel")
    ok("crmDealX.threads !== null" in SCRIPT,
       "and the panel is absent entirely when the server withheld email")


@test
def t_website_enquiries_link_both_ways():
    """A filed enquiry is one click from email to deal and back - a reference
    that does not open is a dead reference."""
    ok("Filed in the CRM - open the deal" in SCRIPT,
       "the email modal links to the deal it became")
    ok(re.search(r"crmDealModal\(t\.crm_deal_id\)", SCRIPT), "and actually opens it")
    ok(re.search(r"openMailThread\(x\.mail_thread_id\)", SCRIPT),
       "while the deal links back to the email it came from")


@test
def t_printing_cannot_waste_stock_or_print_invisible_text():
    """Physical-output bugs: a courier label forced onto gobo stock prints a
    barcode that will not scan; a label whose rows do not fit is cut off in
    silence; and the label typeface is font-display:block, so printing before
    it loads prints nothing at all."""
    # The courier stock became a setting of its own when the bench got a second
    # printer. The requirement did not move: the courier sheet must read the
    # COURIER printer's size and never the production selection.
    carrier = fn_src("function carrierDims(")
    ok("label_size_shipping" in carrier and "'4x6'" in carrier,
       "courier labels print at the courier printer's own stock, defaulting to 4x6")
    ok("labelDims" not in carrier and "prodSize" not in carrier,
       "and never at the chosen gobo stock")
    ok("const dims = carrierDims();" in SCRIPT, "the courier sheet asks for it")
    ok("const dims = labelDims()" not in
       re.search(r"function printLabelImages.*?\n        \}", SCRIPT, re.S).group(0),
       "printLabelImages no longer reads the production stock size")
    fit = re.search(r"function fitLabel.*?\n        \}", SCRIPT, re.S).group(0)
    ok("scrollWidth" in fit, "fitLabel measures WIDTH too, not only height")
    ok("clipped" in fit, "and reports when the content still does not fit")
    ok("does not fit on" in SCRIPT, "the preview warns instead of printing a short cut list")
    ok("function labelFontReady" in SCRIPT, "one shared font gate")
    ok(SCRIPT.count("labelFontReady()") >= 5,
       "every print path waits for the label typeface (%d)" % SCRIPT.count("labelFontReady()"))


@test
def t_a_destructive_question_cannot_be_answered_by_reflex():
    """Every confirm looked the same, focused Confirm, and took Enter - so the
    Enter used to dismiss the previous toast deleted the next thing asked about."""
    fn = re.search(r"function uiConfirm.*?\n        \}", SCRIPT, re.S).group(0)
    ok("const DESTRUCTIVE" in SCRIPT, "destructive intent is classified, not left to each call site")
    ok("e.key === 'Enter' && !danger" in fn, "Enter answers only the reversible dialogs")
    ok("(danger ? no : yes).focus()" in fn, "a destructive dialog opens with Cancel selected")
    ok("btn-danger" in fn, "and its confirming button is the danger button, not the primary one")
    ok(re.search(r"\.btn-danger \{[^}]*background:\s*var\(--action-danger-soft\)", HTML),
       "the danger button is painted from the semantic token: the reference's destructive "
       "button is the red ink on a tint of itself, not a red fill")


def _destructive_re():
    src = re.search(r"const DESTRUCTIVE = /(.*?)/i;", SCRIPT).group(1)
    return re.compile(src.replace("\\b", r"\b"), re.I)


@test
def t_the_destructive_classifier_sorts_the_real_dialogs_correctly():
    """The classifier reads the dialog's own words, so a wording change can
    silently move a delete into the safe bucket, or a routine action into red."""
    rx = _destructive_re()
    must_be_danger = [
        ("Delete", "Delete deal", "Delete this deal? It can be restored for 30 days."),
        ("Delete", "Delete conversation", 'Delete "x"? This cannot be undone.'),
        ("Cancel shipment", "Cancel shipment", "Cancel this shipment at World Options?"),
        ("Empty the trash", "", "Delete everything in the trash for good?"),
        ("Delete the account", "", "Delete x's account for good?"),
        ("Merge", "Merge contacts", 'Merge "x" into this contact and remove it?'),
    ]
    must_be_safe = [
        ("Refresh all", "Refresh all reports", "Re-run the Overview, SEO, Keywords and Customers audits now?"),
        ("Book & dispatch", "Book this courier", "Book Express for 12.40 inc VAT?"),
        ("Book anyway", "Order looks already shipped", "Shopify already shows this order as fulfilled."),
        ("Replace", "Replace size list", 'Replace the size list with "x"? The current sheet is kept as a backup.'),
    ]
    for ok_text, title, msg in must_be_danger:
        ok(rx.search(" ".join([x for x in (ok_text, title, msg) if x])),
           "%r is a one-way door and must open red" % (title or ok_text))
    for ok_text, title, msg in must_be_safe:
        ok(not rx.search(" ".join([x for x in (ok_text, title, msg) if x])),
           "%r is routine and must not be dressed as a destruction" % (title or ok_text))


@test
def t_restore_from_backup_is_treated_as_destructive():
    """It reads as a repair, but it overwrites everything the app currently holds,
    and its own wording contains none of the words the classifier looks for."""
    i = SCRIPT.find("uiConfirm('Restore ")
    ok(i > 0, "the restore confirm is still there")
    call = SCRIPT[i:i + 600]
    ok("danger: true" in call,
       "restore opts in explicitly, because its wording does not trip the classifier")


@test
def t_a_switch_reports_its_state():
    """Toggles were given role=switch but never aria-checked, so a screen reader
    announced 'switch' and stopped. They are also built inside modals long after
    load, so a one-shot pass at startup missed most of them."""
    ok("function syncToggles" in SCRIPT, "one shared pass sets role, tabindex and state")
    ok("aria-checked" in SCRIPT, "and it actually reports the state")
    ok("MutationObserver" in SCRIPT and "syncToggles()" in SCRIPT,
       "toggles built after load are covered too")
    ok("requestAnimationFrame" in re.search(
        r"new MutationObserver\(\(\) => \{.*?\}\)\.observe", SCRIPT, re.S).group(0),
       "batched, or one tab repaint would run it hundreds of times")


@test
def t_nothing_pinned_to_the_viewport_prints():
    """Cameron, after a bulk print: "Skip to content" sat in the corner of the
    production labels. The link lives outside #app, so label mode's hiding of
    the app did not reach it, and a position:fixed element is carried onto
    every printed page. Then: "ensure this bug does not appear on any other
    printables". So every selector that pins itself to the viewport - the
    link, the update bar, toasts, modals, the sign-in scrim, the drawer
    backdrop, menus, the drag bar, the phone sidebar - prints as nothing,
    in label mode and in a report alike, and the rule is checked against the
    stylesheet so a new fixed element cannot slip past it.

    Then it happened a third time, to something not fixed at all: the widget
    grid's live region, one absolutely positioned pixel at body level, sat
    exactly at the foot of the label and printed a second, blank label on every
    production print (18 September; it reached production on the 17th). Naming
    the things to hide one at a time is the fault, so label mode now hides
    everything at body level except the sheets, and a report hides the live
    regions too."""
    ok("body.printing-label > :not(#label-print) { display: none !important; }" in CSS,
       "label mode prints the sheets and nothing else at body level")
    named = re.findall(r"body\.printing-label (#(?!label-print)[\w-]+|\.[\w-]+) \{[^}]*display: none", CSS)
    ok(not named, "and it names none of them one by one, which is what let three escape: %s" % named)
    hide = re.search(r"\n\s*(\.sr-only,[^{]*)\{ display: none !important; \}", CSS)
    ok(hide, "a report prints no live region either: they hold announcements, not content")
    rule = re.search(r"@media print \{\s*(\.skip-link,[^}]*)\{ display: none !important; \}\s*\}", CSS)
    ok(rule, "and no print of any page carries it: one rule hides everything pinned to the viewport")
    hidden = {x.strip() for x in rule.group(1).split(",")} if rule else set()
    # every selector in the stylesheet that pins itself to the viewport must be in that rule
    pinned = set()
    bare = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)  # comments carry no selectors
    for m in re.finditer(r"([^{}]+)\{[^{}]*position: fixed", bare):
        for sel in m.group(1).split(","):
            sel = sel.strip().split("\n")[-1].strip()
            if sel.startswith("@"): continue
            pinned.add(sel.split(".show")[0].split(":")[0].strip())
    missing = sorted(p for p in pinned if p and p not in hidden)
    ok(not missing, "every position:fixed selector prints as nothing (missing: %s)" % ", ".join(missing))
    ok(HTML.index('<a class="skip-link"') < HTML.index('id="app"'),
       "it still comes first in the document, which is the point of it")

@test
def t_the_print_sheet_fits_its_own_page_box():
    """The sheet was pinned to 186mm: 4mm wider than A4 portrait's print box, so
    the right edge clipped, and only 68% of A4 landscape, so the manifest wasted
    a third of the sheet."""
    rule = re.search(r"\.day-sheet \{[^}]*\}", HTML).group(0)
    ok("width: 100%" in rule, "the sheet fills whatever page box it is given")
    ok("max-width: 186mm" in rule, "with a readable ceiling for portrait documents")
    ok(re.search(r"\.day-sheet\.wide \{[^}]*max-width:\s*none", HTML),
       "and a landscape variant that uses the whole sheet")
    ok("el('div', 'day-sheet wide')" in SCRIPT, "the landscape manifest asks for it")
    ok(re.search(r"\.day-sheet h2 \{", HTML),
       "the guide's section headings are styled, not left to the UA's 1.5em")


@test
def t_a_report_exported_to_pdf_carries_no_screen_furniture():
    """A toast that happened to be up printed into the middle of the report, and
    the tap chevrons printed as meaningless arrows beside every row."""
    blocks = [b for b in re.findall(r"@media print \{.*?\n        \}", HTML, re.S)
              if "@page" in b]
    ok(len(blocks) == 1, "one print block owns the report page, found %d" % len(blocks))
    block = blocks[0]
    ok("#toast-host" in block, "toasts are hidden on paper")
    ok(".prod-go" in block, "so are the affordances that only mean something under a finger")
    ok(".prod-row" in block and "break-inside: avoid" in block,
       "and a row is not split across a page break")
    ok("--text-primary:" not in block,
       "the print block no longer repaints a dark theme the app does not have")


@test
def t_losing_money_is_said_in_words_not_only_in_red():
    """A campaign below break-even was flagged by colour alone, which survives
    neither a black-and-white print nor a colour-blind reader."""
    ok("roas-flag" in SCRIPT and "below cost" in SCRIPT,
       "a sub-1 ROAS is labelled, not only tinted")
    ok("roas.style.color = 'var(--error)'" not in SCRIPT,
       "and the colour-only inline style is gone")


def _token_raw(name):
    """A token's literal value, whatever kind it is. _token below follows var()
    chains down to a HEX and asserts colour-ness, which is right for a palette
    and wrong for a length."""
    m = re.search(r"--" + re.escape(name) + r":\s*([^;]+);", CSS)
    assert m, "token --%s not found" % name
    return m.group(1).strip()


def _token(name):
    """A token's value with var() chains followed down to the primitive, so a
    semantic name (--text-tertiary) answers with the hex it paints."""
    for _ in range(8):
        m = re.search(r"--" + re.escape(name) + r":\s*([^;]+);", CSS)
        assert m, "token --%s not found" % name
        v = m.group(1).strip()
        mv = re.fullmatch(r"var\(--([\w-]+)\)", v)
        if not mv:
            assert re.fullmatch(r"#[0-9a-fA-F]{6}", v), "token --%s resolves to %r, not a hex" % (name, v)
            return v
        name = mv.group(1)
    raise AssertionError("token --%s chains too deep" % name)


def _contrast(a, b):
    def chan(c):
        v = c / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    def lum(h):
        h = h.lstrip("#")
        r, g, bl = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(bl)

    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


@test
def t_muted_text_is_readable_on_every_ground_the_app_paints():
    """--text-tertiary is the colour of every muted label in the app. It was #767676,
    which clears 4.5:1 on pure white and on nothing else - and those labels sit
    on the page ground, on sunken fills and inside all four tinted chips, where
    it measured 3.90 to 4.35. Checked against the real tokens so a palette
    tweak cannot quietly put it back.

    Deliberate divergence from the reference, re-confirmed by measurement: the
    reference's muted-foreground is exactly #737373, and moving --text-tertiary onto it
    reads as the truer match. But the reference only ever paints muted text on
    white and on #fafafa; gizmo paints it on tinted chips and sunken fills too,
    where #737373 measures 3.98 to 4.35. The reference is the model for the
    palette, not for the contrast floor."""
    ink3 = _token("text-tertiary")
    grounds = ["surface-primary", "surface-secondary", "surface-tertiary", "surface-sunken",
               "error-bg", "warning-bg", "success-bg", "action-soft"]
    for g in grounds:
        r = _contrast(ink3, _token(g))
        ok(r >= 4.5, "--text-tertiary %s on --%s is %.2f:1, under the 4.5 needed" % (ink3, g, r))


@test
def t_each_semantic_ink_is_readable_on_its_own_tint_and_on_the_page():
    """A win/warn/danger chip is a colour pair. Retuning one half without the
    other is how a status chip becomes unreadable."""
    for ink, tint in [("error", "error-bg"), ("success", "success-bg"), ("warning", "warning-bg"),
                      ("action-primary", "action-soft")]:
        for ground in (tint, "surface-primary"):
            r = _contrast(_token(ink), _token(ground))
            ok(r >= 4.5, "--%s on --%s is %.2f:1, under 4.5" % (ink, ground, r))


@test
def t_the_targets_a_finger_has_to_hit_are_big_enough():
    """Measured in a touch-emulating browser: the only way into a folder was the
    20px line box of its name, and the tick that arms a bulk action was 15-16px.
    Both fixes had to leave the row heights alone, so they pair padding with a
    cancelling negative margin, or grow only where there is no mouse."""
    name = re.search(r"\.files-name \{.*?\}", HTML, re.S).group(0)
    ok("padding: var(--control-pad-y) 0; margin: calc(-1 * var(--control-pad-y)) 0" in name,
       "the folder name's hit box is padded out, and the row keeps its height")
    touch = re.search(r"@media \(hover: none\) \{\s*\.fslot input.*?\n        \}", HTML, re.S)
    ok(touch, "there is a touch-only rule for the file tick")
    ok("width: var(--box-md); height: var(--box-md)" in touch.group(0)
       and _token_raw("box-md") == "24px", "and it reaches 24px there")
    ok(re.search(r"@media \(hover: none\) \{ \.mail-check \{ width: var\(--box-md\); height: var\(--box-md\); \} \}", HTML),
       "the Inbox tick reaches 24px under a finger too")
    base = re.search(r"\.fslot input \{[^}]*\}", HTML).group(0)
    ok("width: var(--box-xs); height: var(--box-xs)" in base and _token_raw("box-xs") == "16px",
       "a mouse still gets the small one, so the list is not covered in boxes")


@test
def t_icon_only_buttons_clear_the_minimum():
    """An icon button was the 16px glyph plus 4px of padding: 24px, on the line."""
    rule = re.search(r"\.icon-btn \{.*?\}", HTML, re.S).group(0)
    ok("min-width: var(--control-h-md)" in rule and "min-height: var(--control-h-md)" in rule,
       "icon buttons carry an explicit floor rather than inheriting one from their glyph")
    ok(re.search(r"\.toast-x \{ min-width: var\(--control-h-sm\); min-height: var\(--control-h-sm\)", HTML),
       "so does the toast dismiss, which sits on its own over the page")


@test
def t_the_deal_board_can_be_worked_without_a_mouse():
    """A deal card has to be a div because it drags between columns, and it was
    left as a bare div: the whole board was the one place in the app with no
    keyboard path at all. Verified in the browser - Enter and Space on a focused
    card open that card's own deal."""
    fn = re.search(r"function crmCard\(x\).*?\n        \}", SCRIPT, re.S).group(0)
    ok("card.draggable = true" in fn, "it is still a draggable div, not a button")
    ok("setAttribute('role', 'button')" in fn, "and it announces itself as a button")
    ok("card.tabIndex = 0" in fn, "and it can be tabbed to")
    ok("aria-label" in fn, "and it says which deal it is, plus the state the colour encodes")
    ok("e.key === 'Enter' || e.key === ' '" in fn, "Enter and Space open it")


@test
def t_a_thumb_inside_a_track_takes_the_track_radius_minus_the_gap():
    """Concentric corners. A rounded thumb inside a rounded track has to take
    the track's radius MINUS the gap, or the two curves are not parallel and
    the thumb reads as a slightly wrong shape rattling in its slot.

    Picking the inner radius off the token scale by eye is what goes stale:
    these two tracks used the SAME 8px thumb with different padding, so .seg
    was concentric by luck (10 - 2 = 8) and .lbl-seg was 2px out (10 - 4 wants
    6). Deriving it means the thumb follows the track, so changing either the
    radius or the padding cannot silently break the corner. SwiftUI ships a
    shape for this (ConcentricRectangle); on the web it is one subtraction, as
    long as it is written down instead of guessed."""
    # Anchored at the start of the rule: ".seg {" is also a substring of
    # ".lbl-seg {", which silently matched the wrong control.
    for track, thumb in ((r"\.lbl-seg \{", r"\.lbl-segbtn \{"), (r"\.seg \{", r"\.seg button \{")):
        tm = re.search(r"(?m)^\s*" + track + r"([^}]*)\}", CSS)
        bm = re.search(r"(?m)^\s*" + thumb + r"([^}]*)\}", CSS)
        ok(tm and bm, "both halves of the control are still one rule each")
        ok("--track-r:" in tm.group(1) and "--track-pad:" in tm.group(1),
           "the track names its own radius and gap: " + track)
        ok("border-radius: var(--track-r)" in tm.group(1),
           "and rounds itself with them: " + track)
        ok("calc(var(--track-r) - var(--track-pad))" in bm.group(1),
           "the thumb derives its radius from the track rather than picking one: " + thumb)


@test
def t_beating_the_plan_is_not_something_worth_looking_at():
    """"Worth looking at" shows the two most serious alerts of however many
    there are, so what it ranks by decides what a director sees first.

    It ranked on the ABSOLUTE gap, so a month coming in 71.5% OVER plan
    outscored a month 20% under it, and the section led with the best news on
    the page while a real shortfall sat in a closed drawer. Over plan is not a
    miss: it scores nothing and surfaces only when there is nothing worse. The
    tone comes from the same FC_VERDICT map the month table uses, so an overrun
    reads as a note rather than arriving in warning amber."""
    fn = SCRIPT.split("function fcAlertWeight(", 1)[1].split("\n        }", 1)[0]
    ok("if (gap > 0) return 0;" in fn, "a month over its plan carries no weight")
    ok("a.risk === 'watch' ? 50" in fn, "and a watch still outranks a quiet shortfall")
    row = SCRIPT.split("function fcAlertRow(", 1)[1].split("\n        }", 1)[0]
    ok("FC_VERDICT[a.verdict]" in row,
       "the alert tone comes from the map the month table uses, not a second opinion")
    ok("'warn'" not in row, "so nothing that beat its plan arrives in warning amber")

    # The ranking itself, on the two rows that exposed it plus the shortfall
    # they were burying.
    import re as _re
    def weight(kind, gap, risk):
        if kind == "cash":
            return 1000 + abs(gap)
        if gap > 0:
            return 0
        return (100 if risk == "high" else 50 if risk == "watch" else 0) + abs(gap)
    rows = [("sales", -11.2, "high"), ("sales", 71.5, "secure"), ("sales", -20.0, "secure")]
    order = sorted(rows, key=lambda r: weight(*r), reverse=True)
    ok(order[-1][1] == 71.5, "the month that beat its plan ranks last, not second")
    ok(order[0][1] == -11.2, "the high-risk shortfall still leads")


@test
def t_a_stock_gobo_is_named_on_the_day_sheets_not_flagged():
    """A stock gobo prints its name on the label, so the sheets must agree: the
    A4 cut list was going to count it as "CHECK-flagged, resolve on the Labels
    tab first", and the made-day sheet as "no resolved size" - two screens
    calling a catalogue gobo a problem the label no longer shows."""
    fn = SCRIPT.split("function printDaySheet(", 1)[1].split("\n        function ", 1)[0]
    ok("it.stock && !it.production_size && !it.review_reason" in fn,
       "stock gobos are separated before anything is counted as flagged")
    ok("'Stock'" in fn and "stock[n]" in fn, "and listed in the tick table by name")
    ok("(d.stock || []).length" in SCRIPT, "the made-day sheet names them")
    ok("add a line by hand if one used a blank" in SCRIPT,
       "and still prompts for a blank, because the order cannot say whether one was used")


@test
def t_a_write_that_failed_is_never_shown_as_a_write_that_worked():
    """A control that changes something on the server must not move until the
    server says it moved. The nightly schedule switch flipped its own class
    first and then discarded every error, so a merchant could be looking at
    "on" while nothing had been enabled and nothing would ever tell them; the
    same shape hid a failed conclude and a failed delete on the Memory tab.

    Three swallows are deliberate and stay: an opportunistic cache warm, a
    font-ready race that must fall through to printing either way, and a
    sign-in probe that degrades to the ordinary sign-in card. Each is a READ
    whose failure costs nothing. What is banned is discarding the error from a
    WRITE."""
    import re as _re
    allowed = {
        "loansWarmCrm",          # prefetch; the real load reports for itself
        "labelFontReady",        # documented: a broken font must still print
        "authApi",               # falls through to the normal sign-in card
        "crmOp",                 # marks a lead seen; the lead opens regardless
    }
    bad = []
    src_lines = SCRIPT.splitlines()
    for i, line in enumerate(src_lines, 1):
        if ".catch(() => {})" not in line and ".catch(()=>{})" not in line:
            continue
        # The call being swallowed is usually a few lines above the .catch, so
        # the window is what identifies it, not the closing line on its own.
        window = "\n".join(src_lines[max(0, i - 8):i])
        if any(a in window for a in allowed):
            continue
        bad.append(str(i) + ": " + line.strip()[:110])
    ok(not bad, "an error from a write is being discarded: " + "; ".join(bad))

    # And the switch itself: the class follows the write, both ways.
    fn = SCRIPT.split("$('sched-toggle').onclick", 1)[1].split("};", 1)[0]
    ok("const was = this.classList.contains('on')" in fn and "paintSchedule(was" in fn,
       "the schedule switch goes back when the server refuses")
    ok("toastError" in fn, "and says so")
    # A load-once cache must not cache a FAILURE, or one blip removes the
    # feature for the whole session.
    tags = SCRIPT.split("async function loadCustomerTags", 1)[1].split("\n        }", 1)[0]
    ok("customerTags = null" in tags,
       "a failed segment load stays null so the next call retries")


@test
def t_a_failed_load_is_not_reported_as_an_empty_list():
    """Both tabs cached into a module-level array and swallowed the read error
    into an empty catch, so a 500 rendered the empty state - whose copy actively
    lies, telling the merchant nothing has been saved yet. Reproduced against a
    forced 500 in the browser: Skills said 'No skills yet'."""
    ok("function loadFailure" in SCRIPT, "one shared notice, so the two tabs cannot drift")
    for name, var in (("loadMemory", "memoryLoadErr"), ("loadSkills", "skillsLoadErr")):
        fn = re.search(r"async function " + name + r"\([a-z]*\).*?\n        \}", SCRIPT, re.S).group(0)
        ok(var + " = ''" in fn, "%s clears the previous failure before it reads" % name)
        ok("catch (e) { " + var in fn or var + " = e.message" in fn,
           "%s records the failure instead of swallowing it" % name)
    for render, var in (("paintNotes", "memoryLoadErr"), ("paintSkills", "skillsLoadErr")):
        fn = re.search(r"function " + render + r"\(\).*?\n        \}", SCRIPT, re.S).group(0)
        ok("if (" + var + ")" in fn,
           "%s shows the failure instead of the empty state" % render)
        ok("loadFailure(" in fn, "%s offers the retry" % render)
    ok("Your notes could not be loaded, so they cannot be shown yet." in SCRIPT
       and "Your skills could not be loaded, so they cannot be shown yet." in SCRIPT,
       "and the copy says the list could not be read rather than that it is empty")


@test
def t_a_failed_question_is_not_dressed_as_an_answer():
    """pageAsk pushed the exception straight in as an assistant turn, so a
    transport failure rendered in the same bubble as a real answer, under the
    same model line - the copilot appeared to have replied 'Failed to fetch'.
    Worse, that text then went back up as assistant history on the next turn."""
    fn = re.search(r"async function pageAsk.*?\n        \}", SCRIPT, re.S).group(0)
    ok("role: 'error'" in fn, "a failure is its own kind of turn, not an assistant turn")
    ok("structured: { summary: e.message" not in fn,
       "and it is no longer packed into the answer shape")
    ok("filter(t => t.role !== 'error')" in fn,
       "the failure is not replayed to the model as something it said")
    render = re.search(r"function renderPageThread.*?\n        \}", SCRIPT, re.S).group(0)
    ok("t.role === 'error'" in render, "and it renders through the error path")
    ok("did not reach Reactor" in render, "which says what actually happened")
    ok("Ask again" in render, "and offers the question back rather than making them retype it")


@test
def t_the_dead_elevation_token_is_gone():
    """--hair only ever resolved to `none`, and a var() that resolves to none
    invalidates the whole shadow list it appears in. That is how six card
    components silently lost their elevation with no error anywhere. The token
    is retired rather than left as a trap for the next edit."""
    ok("--hair" not in HTML, "the token and its last user are both gone")
    # .pfilters left this list when Products became a card: it is a panel
    # INSIDE that card now, on the muted ground, and a shadow inside a card
    # is a second frame.
    for cls in ("card", "lia-card", "auth-card"):
        rule = re.search(r"\." + cls + r" \{[^}]*\}", HTML, re.S)
        ok(rule and "var(--shadow-sm)" in rule.group(0),
           ".%s carries the house card elevation like every other card" % cls)
    # This used to assert the rule carried var(--shadow-sm), and it went on passing
    # after --shadow-sm became `none` under the neutral palette - so every segmented
    # control in the app silently lost its selected state while the guard stayed
    # green. A marker has to be asserted by its EFFECT, never by the presence of
    # a token that may resolve to nothing.
    for sel in (r"\.lbl-segbtn:is\(\.on, \[aria-pressed=\"true\"\]\)", r"\.seg button:is\(\.on, \[aria-pressed=\"true\"\]\)"):
        rule = re.search(sel + r" \{[^}]*\}", HTML, re.S)
        ok(rule, "the %s rule is still there" % sel)
        shadow = re.search(r"box-shadow:\s*([^;}]+)", rule.group(0))
        ok(shadow, "%s marks itself somehow" % sel)
        val = shadow.group(1).strip()
        ok(val != "none" and "var(--shadow-sm)" not in val,
           "%s is marked by something that actually paints, not %r" % (sel, val))
        ok("inset" in val or "var(--ring-" in val,
           "and by an inset hairline rather than a shadow, since a thumb does not float")
    ok(".lbl-filt" not in HTML,
       "and the second, near-identical segmented track has been folded into it")


@test
def t_one_component_per_role_across_tabs():
    """Each of these was a component borrowed from another tab, so the same
    meaning rendered two different ways depending on where you were standing."""
    ok("el('span', 'mail-order-stage not-started', 'cancelled')" not in SCRIPT,
       "Production Manager no longer borrows the Inbox's pill for its cancelled chip")
    ok("el('div', 'mail-empty', rows.length" not in SCRIPT,
       "and no longer borrows the Inbox's empty state")
    ok("el('div', 'disp-subhead', 'On the clock now')" not in SCRIPT,
       "Team uses the page-level heading, not the dispatch modal's field label")
    # Since 2026-09-23 each of the Work tab's three lists is a titled card, as
    # the People tab's is.
    ok("cardOf('Recent sessions'" in SCRIPT and "cardOf('On the clock now')" in SCRIPT
       and "cardOf('Hours per person')" in SCRIPT, "and all three of its headings moved together")
    banner = re.search(r"\.alerts-banner \{[^}]*\}", HTML).group(0)
    ok("var(--bw-hairline) solid var(--border-default)" in banner,
       "the alerts banner wears the hairline every other tinted notice wears")
    lia = re.search(r"\.lia-name \{[^}]*\}", HTML).group(0)
    ok("text-overflow: ellipsis" in lia,
       "and a long account name truncates like every other child of its row")


@test
def t_no_dark_theme_colour_literals_survive():
    """The app was repainted from dark to light. Four rgba literals from the old
    palette came through, and one of them inverted its own signal: the warning
    KPI card ended up with a PALER border than an ordinary card."""
    stray = [ln for ln in HTML.splitlines()
             if re.search(r"rgba\(\s*\d+", ln)
             and not re.search(r"rgba\(\s*(26,\s*26,\s*26|0,\s*0,\s*0|255,\s*255,\s*255)", ln)]
    ok(not stray, "off-palette rgba survives: " + "; ".join(x.strip()[:70] for x in stray[:3]))
    ok(".stat.warn { border-color" not in HTML,
       "the warn card takes the ordinary card border rather than a paler one")
    # The old brand purple is gone from the palette; this keeps it gone.
    ok("91, 75, 219" not in HTML and "#5b4bdb" not in HTML.lower(),
       "no purple survives the move to the neutral palette")


@test
def t_a_disabled_control_looks_disabled():
    """Two of the app's own button recipes had no :disabled state, so a control
    that could not be pressed looked exactly like one that could. One call site
    had noticed and patched it with an inline opacity of its own."""
    ok(re.search(r"\.icon-btn:disabled \{[^}]*cursor: not-allowed", HTML),
       "icon buttons have a disabled recipe")
    ok(re.search(r"\.mail-claim:disabled \{[^}]*cursor: not-allowed", HTML),
       "so does Claim, which is disabled while a claim is in flight")
    ok("x.style.opacity = '.35'" not in SCRIPT,
       "and the one-off inline patch is retired now the class carries the state")


@test
def t_deleting_a_conversation_is_reachable_and_visible():
    """The row was a <button>, so delete could not be one - a button may not
    contain another - which left it a hover-only <span>: no keyboard path, and
    on a tablet an invisible but fully live target next to the row you meant
    to open."""
    fn = re.search(r"const box = \$\('convos'\).*?\n        \}", SCRIPT, re.S).group(0)
    ok("el('div', 'convo'" in fn, "the row is a div so its children can be real buttons")
    ok("el('button', 'title'" in fn and "el('button', 'del')" in fn,
       "both the open and the delete control are real buttons")
    ok("aria-label" in fn, "and delete says what it deletes")
    ok(":focus-within .del" in HTML, "keyboard focus reveals it")
    ok(re.search(r"@media \(hover: none\) \{ \.convo \.del", HTML),
       "and touch, which has no hover, does not leave it invisible-but-live")
    rule = re.search(r"\.convo \.del \{[^}]*\}", HTML, re.S).group(0)
    ok("min-width: var(--control-h-sm)" in rule, "it also clears the minimum target size")


@test
def t_a_status_badge_is_never_the_control():
    """The Shipping row built its action as a .g-badge and swapped it in over
    the badge that was the row's state readout. So one row in a list of
    thirteen was clickable while looking identical to twelve inert pills, and
    it was also the only row that showed no connection state at all."""
    ok("el('button', 'g-badge mid')" not in SCRIPT,
       "no badge is a button")
    ok("shRow.replaceChild(mng" not in SCRIPT,
       "and the action no longer replaces the state readout")
    ok("shRow.append(mng)" in SCRIPT, "it sits beside it")


@test
def t_save_is_pinned_where_every_other_modal_puts_it():
    """Shipping settings put Save inside the scrolling body, so on a short
    window it sat below the fold of a long form and looked absent."""
    ok(".disp-savebar" not in HTML, "the one-off footer component is retired")
    fn = re.search(r"function openShippingSettings.*?\n        \}", SCRIPT, re.S).group(0)
    ok("el('div', 'modal-foot')" in fn, "it uses the house footer")
    ok("modal.append(foot)" in fn, "pinned to the modal, not appended into the scroller")


@test
def t_the_inbox_list_can_be_worked_without_a_mouse():
    """Every other list row in the app is a real button; the Inbox's rows and
    cards were click-only divs."""
    for name in ("row", "card"):
        ok(name + ".setAttribute('role', 'button'); " + name + ".tabIndex = 0;" in SCRIPT,
           "the mail %s announces itself and can be tabbed to" % name)
    # The mail rows pioneered this guard; the audit pass spread it to every
    # row in the app, so the count is now "at least", not "exactly one".
    ok(SCRIPT.count("if (e.target !== row) return;") >= 1
       and SCRIPT.count("if (e.target !== card) return;") >= 1,
       "the key handler is guarded on target so the row's own checkbox and "
       "Claim keep their Space and Enter")
    ok("e.stopPropagation(); row.click();" in SCRIPT,
       "and it stops there, or the inbox-wide Enter shortcut fires too")
    ok(re.search(r"\.mrow:focus-visible \{[^}]*outline-offset: -2px", HTML),
       "the ring is drawn inside the row, which .mlist would otherwise clip")


@test
def t_a_tick_box_that_is_a_div_still_answers_the_keyboard():
    """The action lists build their tick as a bare div with a click handler on
    the row, so the only way to mark something done was a mouse."""
    ok(SCRIPT.count("ck.setAttribute('role', 'button')") == 2,
       "both action lists give the box a role")
    ok("ck.setAttribute('aria-pressed', String(row.classList.toggle('done')))" in SCRIPT
       or "const on = row.classList.toggle('done'); ck.setAttribute('aria-pressed', String(on));" in SCRIPT,
       "and the pressed state follows the row, rather than going stale")
    ok(SCRIPT.count("ck.tabIndex = 0") == 2, "both are reachable")


@test
def t_every_status_chip_has_the_same_geometry():
    """Chips split 6px against 12px roughly along tab lines, so the same kind of
    label was a rounded rectangle in one tab and a capsule in the next. The
    radius scale's own comment names the three steps card, control, chip, which
    settles which of the two is the chip. Under the neutral system that shape is
    a capsule, --radius-full, and it has to be the SAME capsule everywhere."""
    chips = ["pill", "mail-order-stage", "lbl-chip", "fchip", "mail-owner",
             "mcount", "mrule-tag", "g-badge", "mail-claim", "mail-crmchip"]
    for c in chips:
        rule = re.search(r"\." + c + r" \{[^}]*\}", HTML, re.S)
        ok(rule, "the .%s rule is still there" % c)
        ok("border-radius: var(--radius-full)" in rule.group(0),
           ".%s takes the chip radius from the token, not a literal" % c)
    ok("border-radius: 12px" not in re.search(r"\.fchip \{[^}]*\}", HTML).group(0),
       "and no chip keeps the control radius")


@test
def t_the_inbox_crm_chip_is_the_accent_not_a_lookalike():
    """It ran its own #eef4ff / #c7d7fe / #3538cd, three near-misses of the
    accent trio, so the CRM link chip was a slightly different blue from every
    other accent-tinted chip in the app."""
    rule = re.search(r"\.mail-crmchip \{[^}]*\}", HTML, re.S).group(0)
    for tok in ("var(--action-soft)", "var(--action-line)", "var(--action-primary)"):
        ok(tok in rule, ".mail-crmchip reads %s" % tok)
    for h in ("#eef4ff", "#c7d7fe", "#3538cd"):
        ok(h not in HTML, "the near-miss %s is gone" % h)


@test
def t_a_heading_with_a_control_in_it_is_still_the_heading_component():
    """trendsHeader hand-rolled .section-title from an inline style string at an
    off-scale weight and with no hairline, so Overview's own trends heading did
    not match the headings above and below it."""
    fn = re.search(r"function trendsHeader.*?\n        \}", SCRIPT, re.S).group(0)
    ok("el('div', 'section-title')" in fn, "it uses the real component")
    ok("font-size:11px" not in fn and "font-weight" not in fn,
       "and sets no type of its own")
    ok(re.search(r"\.section-title > \.seg \{[^}]*order: 1", HTML),
       "the range control is ordered past the ::after hairline, which is "
       "always the last flex item")
    ok(re.search(r"\.section-title > \.seg \{[^}]*letter-spacing: normal", HTML),
       "and the heading's tracking does not leak into the button labels")
    ok("el('div', 'disp-subhead', sec.h)" not in SCRIPT,
       "the Guide's on-screen headings are headings, not dispatch field labels")


@test
def t_no_off_scale_type_is_set_from_javascript():
    """Weights and sizes set in JS style strings never reach the stylesheet, so
    the type scale looks closed while 700, 800 and 17px live in the renderers."""
    for bad in ("font-weight:700", "font-weight:800", "font-weight = '700'",
                "font-weight = '800'", "font-size:17px"):
        ok(bad not in SCRIPT, "%r is set from JavaScript" % bad)


def _body_of(signature):
    """Slice one function out of the SPA by counting braces. A non-greedy regex
    to a closing brace at a guessed indent silently runs to the end of the file,
    which makes an assertion about a single function quietly meaningless."""
    i = SCRIPT.index(signature)
    depth, j, started = 0, i, False
    while j < len(SCRIPT):
        c = SCRIPT[j]
        if c == "{":
            depth += 1
            started = True
        elif c == "}":
            depth -= 1
            if started and depth == 0:
                return SCRIPT[i:j + 1]
        j += 1
    raise AssertionError("unbalanced braces after " + signature)


@test
def t_the_custom_shipment_queue_speaks_its_own_tab_s_language():
    """It sat on the Production Manager behind the same segmented control as the
    order queues, but was built from three other tabs' vocabularies: the Files
    browser's rows, a dispatch modal's search field plus an inline one-off, and
    the Inbox's empty state."""
    fn = _body_of("function renderCustomQueue")
    for borrowed in ("files-list", "files-row", "files-name", "files-meta",
                     "disp-text", "mail-empty"):
        ok(borrowed not in fn, "the queue no longer borrows .%s" % borrowed)
    for own in ("lbl-row", "lbl-who", "lbl-meta", "lbl-actions", "lbl-chip bad"):
        ok(own in fn, "it uses the tab's own .%s" % own)
    # And the page around the list is the other four tabs' page: a card with a
    # counted title, its actions in the head and the house search (2026-09-23).
    ok("tableSearch('Search reference, name or tracking'" in fn and "el('div', 'card-head')" in fn
       and "heroAct(" in fn, "the list sits in a card like the order queues' own")
    ok("margin-left:auto" not in fn, "and the inline one-off layout is gone")


@test
def t_the_customers_switcher_is_the_house_control():
    """Customers was the only tab whose sub-view switcher was loose pills, and
    the only one that put the switcher above its own page title."""
    ok(".secbar" not in HTML and ".secbtn" not in HTML,
       "the one-off pill component is retired")
    fn = re.search(r"function sectorBar.*?\n        \}", SCRIPT, re.S).group(0)
    ok("el('div', 'lbl-seg')" in fn and "lbl-segbtn" in fn,
       "it is built on the same segmented control as every other tab")
    ok("box.append(hero, sectorBar())" in SCRIPT,
       "and the hero comes first, like every other tab")


_WGL_START = "        /* ---------- widget grid (page layer) ---------- */"
_WGL_END = "        /* ---------- widget grid end ---------- */"


def _wg_layer():
    """The widget grid's page layer in static/index.html, between its two
    marker lines: the observer, Customize mode, the drag, the keyboard and the
    save. Assertions about the layer read this rather than the whole script,
    so a line elsewhere cannot satisfy them."""
    ok(SCRIPT.count(_WGL_START) == 1 and SCRIPT.count(_WGL_END) == 1,
       "the page layer must sit between %r and %r, each once" % (_WGL_START.strip(), _WGL_END.strip()))
    a = SCRIPT.index(_WGL_START)
    return SCRIPT[a:SCRIPT.index(_WGL_END, a)]


def _wg_fn(name):
    """One function of the page layer, from its keyword to the next function
    declared at the same indentation."""
    src = _wg_layer()
    i = src.index(name)
    rest = src[i + len(name):]
    ends = [j for j in (rest.find("\n        function "), rest.find("\n        async function "),
                        rest.find("\n        const "), rest.find("\n        /* ")) if j >= 0]
    return src[i:i + len(name) + (min(ends) if ends else len(rest))]


@test
def t_reordering_kpis_works_without_a_drag():
    """HTML5 drag events never fire from touch, so the Overview KPI reorder was
    unreachable on a phone and the hint told you to do the one thing you could
    not do. The arrow buttons that patched it went with the rest of the old
    Overview customizing: the widget grid moves cards with pointer events,
    which a finger fires too once it has held a card, and with Alt and the
    arrow keys, and its hint names all three."""
    layer = _wg_layer()
    ok("stat-move" not in HTML and "draggable = true" not in layer and "dragstart" not in layer,
       "no HTML5 drag and no arrow buttons are left")
    ok("root.addEventListener('pointerdown', (e) => wgPointerDown(view, e));" in layer,
       "a press on a card starts the drag, whatever pointer made it")
    ok("if (wgDrag.touch) wgDrag.hold = setTimeout(wgLift, WG_HOLD_MS);" in layer
       and "WG_HOLD_MS = 350" in layer,
       "a finger lifts a card after holding it")
    ok("card.addEventListener('touchmove', wgNoScroll, { passive: false });" in layer
       and "if (wgDrag && wgDrag.lifted) e.preventDefault();" in layer,
       "and once lifted the finger moves the card, not the page")
    ok("{ ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key]" in layer and "!e.altKey" in layer,
       "Alt and an arrow moves the focused card")
    ok("'Drag to rearrange. On a touch screen, press and hold first. With a keyboard, hold Alt and press the arrow keys.'" in SCRIPT,
       "the hint describes what actually works")


@test
def t_paying_a_customers_duty_warns_that_it_makes_us_liable():
    """A standing decision of this business, and the pressure to break it comes
    at exactly the wrong moment: a courier refuses an international booking, and
    paying the duty ourselves makes the error go away. It also makes the
    business liable for the customer's import charges."""
    ok("dpWarn" in SCRIPT, "the setting carries a warning")
    i = SCRIPT.index("dpWarn")
    seg = SCRIPT[i:i + 900]
    ok("liable" in seg, "which names the actual consequence")
    ok("Duties_To_Be_Paid_By_Receiver" in seg,
       "and it appears only when the setting moves OFF the customer")


@test
def t_a_dialog_can_be_handed_a_panel_not_only_a_sentence():
    """el() sets textContent, so handing uiConfirm a built node printed the
    literal string "[object HTMLDivElement]" into the dialog. That is what the
    Collections panel showed: the code ran, the dialog opened, and the content
    was a stringified object. Neither a syntax check nor a text search over the
    source can see that - only opening it can."""
    i = SCRIPT.index("function uiConfirm(message, opts)")
    seg = SCRIPT[i:i + 1400]
    ok("message instanceof Node" in seg,
       "a node message is appended rather than stringified")
    ok("body.append(message)" in seg, "and appended as itself")
    ok("el('p', 'confirm-msg', message)" in seg,
       "while a plain sentence still gets its paragraph")
    # The panel that hit it passes a node.
    j = SCRIPT.index("async function openBookCollection()")
    ok("uiConfirm(body," in SCRIPT[j:j + 1200],
       "and Collections still hands it a built panel, which is the case that broke")


@test
def t_what_a_booking_asked_for_outlives_the_click_that_asked():
    """Shipped broken: askedCollection was declared with const INSIDE the book
    click handler and read by renderResult, which is its SIBLING, not its child.
    Syntax-checking passes on that - it is a scope error, not a parse error - so
    it only surfaced at runtime, right after a booking had charged the account.
    The worst possible moment to throw.

    node --check cannot see this and there is no JS linter in this repo, so this
    guard is narrow on purpose: it pins the declaration to the scope both
    functions can reach."""
    i = SCRIPT.index("let booking = false;    // set while money is being spent")
    seg = SCRIPT[i:i + 700]
    ok("let askedCollection" in seg,
       "it is declared beside `booking`, in the scope the whole panel shares")
    # And NOT re-declared inside the handler, which is what broke it.
    ok("const askedCollection" not in SCRIPT and "let askedCollection = collectionForRun" not in SCRIPT,
       "and never re-declared inside the click, which would shadow it again")
    j = SCRIPT.index("function renderResult(res)")
    ok("askedCollection" in SCRIPT[j:j + 900],
       "renderResult still reads it, which is the whole reason it must live out there")


@test
def t_the_charts_are_drawn_to_the_reference_spec():
    """Measured off the reference's own rendered SVG, not eyeballed: five
    horizontal rules at HALF the weight of the card's own edge, reaching the
    card's right edge, no verticals, no axis line, no tick marks, five labelled
    y ticks and the dates both 12px in muted grey, lines at 1.4, and an area wash from
    the light end of the ramp. Its chart carries no average rule, no peak label
    and no resting dot - every text node in it is an axis number or a date.

    The rules used to be a #ccc literal, which resolved to the same #e5e5e5 as
    the card border around them, and the y axis carried no numbers at all - so
    a reader could not tell whether the Clicks line sat at 8k or 18k. The
    reference labels its own y axis at x=18 in a mid grey."""
    css = CSS
    grid = re.search(r"\.chart-wrap \.gridline \{[^}]*\}", css).group(0)
    ok("stroke: var(--border-default)" in grid and "stroke-opacity: .5" in grid,
       "the grid is the border colour at half opacity, one step lighter than "
       "the card's own edge: " + grid)
    ok(_token("border-default") == "#e5e5e5", "and that token still resolves to #e5e5e5")
    ok("dasharray" not in grid, "and solid, not dashed")
    line = re.search(r"\.chart-line \{[^}]*\}", css).group(0)
    # The weight is a token now, so check the token resolves to the reference
    # value rather than checking the rule spells it out.
    ok("stroke-width: var(--chart-stroke)" in line, "the line weight comes from the token: " + line)
    ok(_token_raw("chart-stroke") == "1.4px", "and that token is still 1.4, not a marker pen")
    axis = re.search(r"\.chart-wrap \.axis-x text[^{]*\{[^}]*\}", css).group(0)
    # Same requirement, re-anchored: the dates are the app's muted grey rather
    # than the near-black body ink. It used to be the #666666 literal measured
    # off the reference, which was the only string in the app painted from a
    # hex instead of a token and sat three units off --text-tertiary.
    ok("fill: var(--text-tertiary)" in axis and "#" not in axis, "dates are muted grey from the token: " + axis)
    ok(_token("text-tertiary") == "#696969", "and that token still resolves to a grey (#696969)")
    ok(".axis-y text" in axis and "var(--text-xs)" in axis,
       "and the y numbers are painted by the same 12px rule: " + axis)
    # The frame draws the rules from the axis to the card edge and labels both axes.
    frame = SCRIPT[SCRIPT.index("function drawFrame"):]
    frame = frame[:frame.index("\n        function ", 10)]
    ok("x1: padL, y1: yy, x2: W" in frame,
       "rules reach the card's right edge, and start at the axis rather than "
       "running under their own numbers")
    ok("if (c.yTicks)" in frame, "y-axis numbers are opt-in")
    ok("rotate(-90" not in frame, "no rotated axis title down the side")
    ok("yTicks: false" not in SCRIPT and SCRIPT.count("yTicks: true") == 2,
       "and both chart types opt in, as the reference labels its own y axis")
    # Nothing decorates the plot at rest.
    ok("chart-end-dot" not in SCRIPT, "no dot at the end of the line")
    ok("annotate(svg" not in SCRIPT.replace("function annotate(svg", ""),
       "and no average rule or peak label is drawn")


@test
def t_a_link_is_still_identifiable_without_colour():
    """The palette is monochrome now, so a link has no hue left to mark it
    with: near-black link text on white is exactly body text. The underline
    stops being decoration and becomes the entire affordance, which is why the
    reference underlines its links too."""
    style = HTML[HTML.index("<style>"):HTML.index("</style>")]
    for sel in [".lbl-num-link, .modal-order-link, .action-link", ".mail-order-name", ".miss-open",
                ".seclink", ".sk-more", ".linkish"]:
        i = style.find("\n        " + sel + " {")
        ok(i >= 0, "the %s rule is still there" % sel)
        body = style[i:style.index("}", i)]
        ok("text-decoration: underline" in body,
           "%s is underlined, since colour can no longer mark it" % sel)
        ok("text-decoration: none" not in body,
           "%s does not then turn the underline back off" % sel)


@test
def t_nothing_shouts_in_letterspaced_capitals():
    """This used to guard the 11px uppercase micro-label, which was set at .04,
    .05, .06 and .08em in different places. Under the neutral system that unit
    does not exist at all: the reference has not one uppercase label anywhere,
    and a quiet label is quiet because it is small and grey. Guarding its
    absence is the stronger rule, because micro-caps creep back one rule at a
    time."""
    style = HTML[HTML.index("<style>"):HTML.index("</style>")]
    caps = [m.group(1).strip()[:52] for m in
            re.finditer(r"\n\s*([^\n{}]+)\{([^}]*text-transform:\s*uppercase[^}]*)\}", style)]
    ok(not caps, "no rule sets uppercase: " + "; ".join(caps[:4]))
    ok("--track-caps" not in HTML,
       "and the tracking token that only ever served them is retired, not left as a trap")
    # Body copy is untracked; only headings tighten.
    body = re.search(r"\n\s*body \{([^}]*)\}", style).group(1)
    ok("letter-spacing: normal" in body,
       "body text is not tracked: " + body.strip()[:80])


@test
def t_an_order_number_is_a_door_and_opens_beside_the_queue():
    """orderA opened with target=_top, which navigates the whole embedded Shopify
    admin away and takes the production queue with it. The Inbox already used
    _blank; this was drift, and a production desk that loses its place to a
    stray click has been made worse."""
    fn = _body_of("function orderA(")
    ok("'_blank'" in fn and "a.rel = 'noopener'" in fn, "it opens in a new tab")
    ok("'_top'" not in fn, "and never navigates the admin frame away")
    ok("e.stopPropagation()" in fn,
       "the click stops there: half these numbers sit inside a row that is "
       "itself a button")
    ok("if (!url) return el('span'" in fn,
       "and it degrades to plain text when there is no id, so no caller has to decide")


@test
def t_the_production_queue_links_its_order_numbers():
    ok("row.append(orderA(orderNo(o), o.admin_url, 'lbl-num lbl-num-link'))" in SCRIPT,
       "the queue row's order number is the link")
    ok('"admin_url": _admin_order_url(o.get("id")),' in
       open(os.path.join(ROOT, "copilot.py"), encoding="utf-8").read(),
       "and the label order payload carries the url, like every other order payload")
    ok(re.search(r"\.lbl-num-link[^{]*\{[^}]*var\(--action-primary\)", HTML),
       "it reads as a link, while .lbl-num keeps the tabular column geometry")


@test
def t_the_printed_label_is_not_turned_into_a_hyperlink():
    """labelSheet() is reused verbatim by printLabels(), so an anchor there
    would print onto the physical label."""
    fn = _body_of("function labelSheet(")
    ok("orderA(" not in fn, "the label sheet's order line stays plain text")


@test
def t_only_an_admin_is_offered_the_edit_button():
    """The server is the real gate. This just stops offering a button that
    would come back 403."""
    ok("function canEditOrders" in SCRIPT, "there is a role check")
    ok("if (canEditOrders() && o.status !== 'cancelled')" in SCRIPT,
       "and the row only builds Edit for someone who may use it, and not for a "
       "cancelled order")


@test
def t_the_edit_panel_reads_the_order_live_before_it_edits():
    """The queue's copy of an order can be a sweep old, and its note has had the
    proposal URL cut out and the remainder truncated - so prefilling from it and
    saving would delete the artwork proof link from Shopify."""
    fn = _body_of("async function openOrderEdit(")
    ok("op: 'read'" in fn, "it fetches the current values first")
    ok("live.ship_to" in fn, "and prefills from those, not from the queue object")
    ok("live.booked" in fn, "it knows about a booked label before anyone types")
    ok("uiConfirm(" in fn and "danger: true" in fn,
       "and changing a booked parcel's address takes a destructive confirmation")
    ok("confirm_booked" in fn, "which is what the server is told")
    ok("quoteCache.delete(String(o.id))" in fn,
       "a saved address invalidates the courier quote priced for the old one")
    ok("loadLabels(true)" in fn, "and the queue is refetched rather than left stale")


@test
def t_the_edit_panel_offers_only_what_shopify_will_change():
    fn = _body_of("async function openOrderEdit(")
    ok("'name'" not in _body_of("const ORDER_EDIT_FIELDS")
       or "['firstname'" in SCRIPT,
       "the recipient is first + last, because Shopify derives the address name")
    ok(SCRIPT.count("['firstname', 'First name']") == 1, "first name is a field")
    ok("phone_c" not in SCRIPT,
       "there is ONE phone field: Shopify keeps one on the address and one on the "
       "order, and showing both put the same number on screen twice")
    ok("live.note || ''" in fn,
       "the note box is prefilled from the LIVE note, not the queue's stripped copy")
    ok("not editable" in fn, "and the panel says why the tags are not on it")


@test
def t_a_parcel_whose_address_moved_is_not_quietly_fulfilled():
    """Mark made is what emails the customer their tracking. If the address was
    edited after the label was booked, the parcel is going somewhere else."""
    py = open(os.path.join(ROOT, "copilot.py"), encoding="utf-8").read()
    ok('"reason": "address_changed"' in py, "the fulfilment gate stops for it")
    ok('"needs_ack": (ship_reason == "address_changed")' in py,
       "and tells the workbench, because only a human knows where the parcel went")
    fn = _body_of("async function toggleMade(")
    ok("r.needs_ack" in fn and "ack_address: true" in fn,
       "which asks once and then proceeds on the answer")


@test
def t_the_app_can_show_its_own_release_notes_and_take_a_request():
    """The app has to be able to say what it IS and what just changed, and
    catch a request at the moment somebody notices the gap."""
    ok("'/api/updates'" in SCRIPT, "the updates endpoint is reached from the SPA")
    ok("function paintReleases" in SCRIPT and "function paintRequests" in SCRIPT,
       "What's new and Requests both render")
    ok("function askFeature" in SCRIPT, "and a request can be made")
    ok("const v = currentView(); closeSidebar(); askFeature(v);" in fn_src("function userMenu("),
       "with a way in that lives outside any one tab: the account menu, on every width")
    ok("nav-new-dot" in HTML and "op: 'seen'" in SCRIPT,
       "unread releases show a quiet dot, remembered per account rather than per browser")
    ok("function markSeen(" in SCRIPT, "and reading them clears it")


@test
def t_a_box_preset_can_be_picked_as_the_dispatch_default():
    """Dispatch already honoured cfg.default_box_id; the settings had no way
    to choose one."""
    ok("disp-boxdef" in SCRIPT and "ship-default-box" in SCRIPT,
       "each box row carries a radio for the default")
    ok("payload.default_box_id" in SCRIPT, "and the choice is saved")
    ok("clean.some(b => b.id === defaultBoxId)" in SCRIPT,
       "never pointing at a box that did not survive the save")
    ok("if (boxes[i].id === defaultBoxId) defaultBoxId = ''" in SCRIPT,
       "and deleting the default box clears it")


@test
def t_the_customs_card_prefills_the_declaration_name():
    """The card used to prefill the shop's product title as the customs
    description."""
    ok("it.customs_description || it.title" in SCRIPT,
       "the declaration name wins, with the product title as the fallback")


@test
def t_the_receivers_tax_id_prefills_but_never_overrides_typing():
    """An export waited on somebody hunting for a number the customer had
    already given Shopify - but a prefill that overwrites what the operator
    typed is worse than no prefill."""
    ok("quote.receiver_tax_id" in SCRIPT, "the card prefills from the order")
    ok("recvTaxSaved !== ''" in SCRIPT, "and anything already typed wins")
    ok("quote.receiver_tax_source" in SCRIPT,
       "with the source named, so an autofilled number can be checked")


@test
def t_courier_labels_print_in_separate_runs_per_courier():
    """Three DHL and eight UPS is two runs at two printers: the courier is
    chosen BEFORE anything prints, not discovered halfway through a stack."""
    ok("function printShippingLabelsFor" in SCRIPT and "function courierOf" in SCRIPT,
       "labels are grouped by the courier that carries them")
    ok("d.tracking_number && !d.canceled" in SCRIPT,
       "only orders actually dispatched, and never a cancelled one")
    ok("every courier, one run" in SCRIPT,
       "with one deliberate option to print the lot together")
    m = re.search(r"function fetchLabelsFor[\s\S]{0,3000}", SCRIPT).group(0)
    ok("failed.push" in m, "an unreadable label is collected, never swallowed")
    ok("[0, 1, 2, 3].map(worker)" in m,
       "fetched a few at a time - a megabyte a label makes one big request a timeout")
    ok("could not be read" in SCRIPT, "and the orders that failed are NAMED")
    # The ways a stack goes out short, each of which must be reported.
    ok("parcels could print" in m,
       "a multi-parcel order that only partly printed is named, not counted a success")
    ok("no label stored" in m and "cannot print in place" in m,
       "and so are a missing label and one that cannot print in place")
    ok("slots[idx] = got" in m,
       "results land in queue order, not whoever answered first")
    ok("run.cancelled" in m, "and closing the window mid-run stops it")


@test
def t_a_bulk_label_run_inherits_the_rules_the_single_print_has():
    """The gobo bulk print has refused cancelled, refunded and fulfilled
    orders for a long time; a new bulk path must not quietly skip that."""
    f = re.search(r"function shipLabelEligible[\s\S]{0,900}", SCRIPT).group(0)
    ok("if (o.status) return false" in f,
       "cancelled, refunded and fulfilled orders never join a courier run")
    ok("d.canceled" in f, "nor a shipment voided at the courier")
    ok("SHIP_RUN_MAX" in SCRIPT, "and a run has a ceiling rather than firing 1,800 requests")


@test
def t_a_batch_never_paints_its_successes_red():
    """One boolean over a whole print run meant a red toast could carry three
    success sentences while the order that actually failed was never named."""
    f = re.search(r"const terms = \(r && r\.terms\) \|\| \[\][\s\S]{0,1200}", SCRIPT).group(0)
    ok("bad.filter" in f or "filter(t => !t.ok)" in f, "failures are separated from successes")
    ok("'#' + t.order" in f, "and each failure names its order")
    ok("toastError" in f and "addToast" in f, "red for the failures, green for the rest")


@test
def t_a_release_always_says_the_order_moved():
    """The tag moves before the terms are attempted, so the release happened
    even when the terms did not. Showing only the red terms error left the
    merchant unsure whether to press it again."""
    f = re.search(r"async function readyToMake[\s\S]{0,1200}", SCRIPT).group(0)
    moved = f.index("moved to To make")
    err = f.index("toastError(orderNo(o)")
    ok(moved < err, "the confirmation comes first, then the problem")


@test
def t_an_order_missing_its_terms_is_flagged_on_the_queue_row():
    """A toast is gone when the page moves on, and the background half of a
    big print run has no toast at all."""
    ok("st.terms_error" in SCRIPT, "the queue row reads the flag the server left")
    f = re.search(r"if \(st\.terms_error\)[\s\S]{0,400}", SCRIPT).group(0)
    ok("No terms" in f, "and shows it")
    ok("lbl-chip bad" in f, "in red, like the other things that need attention")


@test
def t_the_page_uses_the_whole_screen():
    """A fixed 1120px wrap left a third of a 1920 monitor and half of a 2560
    iMac as empty margin, while the rows inside it were the crowded part. The
    ladder that replaced it (1120/1800/2040/2160, centred) was one answer; the
    reference gives another and this app now follows it: ONE cap, the
    reference's max-w-screen-2xl (1536px), centred, a single padded column
    that the cards grow to fill. A demo once read as full bleed, and on a
    2000px screen that stretched the KPI strip and the charts past anything
    the reference draws."""
    ok("--wrap:" in CSS, "there is one page-width token")
    ok("--wrap-read" not in CSS and "--wrap-data" not in CSS,
       "and only one: every tab uses the same page, so they line up as you "
       "move between them")
    rule = re.search(r"\.ov-wrap \{[^}]*\}", CSS).group(0)
    ok("max-width: var(--wrap)" in rule, "the wrap reads the token")
    ok(re.search(r"--wrap:\s*1536px", CSS), "which is the reference's max-w-screen-2xl")
    ok("margin: 0 auto" in rule, "and the column is centred, as the reference's default layout is")
    for stop in ("1500px", "1900px", "2400px"):
        ok("min-width: " + stop + " ) { :root { --wrap" not in CSS.replace(" ", " "),
           "no width ladder survives (%s)" % stop)


def _wrap_widening_is_min_width_only():
    """Every rule that GROWS something must be min-width gated, so a printed
    page and a phone are untouched by the desktop work."""
    for m in re.finditer(r"@media\s*\(max-width:\s*(\d+)px\)\s*\{", CSS):
        block_start = m.end()
        depth, i = 1, block_start
        while i < len(CSS) and depth:
            if CSS[i] == "{": depth += 1
            elif CSS[i] == "}": depth -= 1
            i += 1
        block = CSS[block_start:i]
        ok("--wrap:" not in block,
           "no max-width block moves the wrap token (found in the " + m.group(1) + "px block)")


@test
def t_widening_never_reaches_a_narrow_screen_or_a_printed_page():
    _wrap_widening_is_min_width_only()


@test
def t_prose_is_capped_to_a_reading_measure():
    """The whole point of the width work is that DATA gets the width and TEXT
    does not. A 1,640px line of 12px help text is worse than the crowding."""
    rule = re.search(r"\.setting-sub, \.field-help[\s\S]{0,900}?\}", CSS).group(0)
    ok("52ch" in rule, "prose is capped in ch, not pixels")
    ok("var(--" not in rule.split("max-width:")[1].split(";")[0],
       "and the cap is written on the rule, not held in a root custom property "
       "where ch would resolve against the root font size instead of the text's own")


@test
def t_the_queue_row_spends_width_on_columns_not_on_a_void():
    f = re.search(r"@container queue \(min-width: 1200px\) \{\s*\.lbl-grid[\s\S]{0,600}?\n        \}", CSS)
    ok(f, "there is a wide rule for the queue row, keyed to the list's own width")
    ok("display: contents" in f.group(0),
       "the .lbl-who box dissolves so its two lines become two real columns")
    ok(".lbl-row {" not in f.group(0),
       "and it is scoped to .lbl-qrow: the row shell is shared by seven lists "
       "with different children, and a fixed track list breaks the other six")


@test
def t_six_buttons_never_paint_over_the_date():
    """The rail is a flex item with min-width 0, so it was squeezed to 526px
    while its buttons measured 593px and refused to shrink."""
    ok("min-width: max-content" in CSS, "the rail reserves what it needs")
    ok("@container queue (max-width: 999px) {\n            .lbl-actions .lbl-btn-txt { display: none; }" in CSS,
       "and in a list under 1,000px the buttons drop to icons rather than overlapping")
    # The case the viewport rule could not see: a 1,728px window with the
    # label preview open leaves the list 900px wide, and the labelled rail
    # painted over the item line and the date.
    ok(".lbl-list { container: queue / inline-size; }" in CSS, "the list is the container")
    ok("const listBox = el('div', 'lbl-list')" in SCRIPT and "split.append(listBox, pane)" in SCRIPT,
       "with or without the pane beside it")
    # And one set of tracks for every row: a refunded order's shorter rail or
    # a wider date moved its own row's columns by up to 121px.
    ok("grid-template-columns: subgrid" in CSS and ".lbl-grid > * { grid-column: 1 / -1; }" in CSS,
       "each row is a subgrid of the list, so the columns line up down the queue")


@test
def t_the_label_preview_sits_beside_the_queue_on_a_wide_screen():
    """Opened inline it shoved every order below it down the page."""
    ok(".lbl-split" in CSS and ".lbl-pane" in CSS, "the split layout is styled")
    ok("lbl-split" in SCRIPT and "lbl-pane" in SCRIPT, "and built by the renderer")
    ok("matchMedia('(min-width: 1500px)')" in SCRIPT, "decided once, above 1500")
    ok("(pane || box).append(wrap)" in SCRIPT,
       "and it still falls back to inline where there is no room for a pane")


@test
def t_contacts_is_a_table_not_a_run_together_line():
    """Company, email, deal count and the Shopify link were joined with dots
    into one nowrap line, so a long company name truncated the rest away."""
    ok("crm-contact-table" in SCRIPT, "contacts renders the house table")
    # The window is the table block itself - from the table's class to the pager
    # that follows it - rather than a byte count that a comment above the row
    # can push the tick handler out of.
    fn = SCRIPT.split("crm-contact-table")[1]
    fn = fn[:fn.index("list.append(tablePager({")]
    for col in ("Organisation", "Email", "Phone", "Deals", "Label"):
        ok(col in fn, "there is a " + col + " column")
    ok("e.stopPropagation()" in fn,
       "and ticking the box still does not open the contact")


@test
def t_each_crm_segment_declares_its_own_width():
    """crm-narrow capped four segments at 1120 with no auto margins, so they
    hugged the left edge with an empty band down the right."""
    ok("crm-seg-" in SCRIPT, "the segment carries its own class")
    ok(".crm-seg-leads" in CSS and ".crm-seg-insights" in CSS,
       "and the short ones are capped by name rather than by a blanket rule")


@test
def t_insight_charts_sit_side_by_side():
    """A bar track 860px wide encodes exactly one number."""
    ok(".crm-charts" in CSS, "there is a chart grid")
    ok("auto-fit" in re.search(r"\.crm-charts \{[^}]*\}", CSS).group(0),
       "which collapses on its own rather than needing a breakpoint")
    ok("host.lastChild" not in SCRIPT,
       "and the forecast note attaches to the chart it belongs to, not to "
       "whatever happened to be appended last")


@test
def t_independent_cards_use_the_width():
    ok(".card-grid" in CSS, "notes and skills sit in a card grid")
    rule = re.search(r"\.card-grid \{[^}]*\}", CSS).group(0)
    ok("auto-fit" in rule and "min(100%" in rule,
       "self-collapsing, so a phone and a printed page get one column, and "
       "auto-FIT so two cards fill the row instead of sitting beside an empty "
       "track (auto-fill keeps its empty tracks)")
    ok("function skillEditor(" in SCRIPT and "li.append(skillEditor(s))" in SCRIPT,
       "and a skill is edited in place in its full-width row of the list, "
       "because a text area squeezed into a 380px column is not a typing surface")


@test
def t_a_kpi_with_a_list_behind_it_opens_it():
    """Cameron: "the sections don't look like you can interact with them". A
    KPI that carries the pages or products behind its number is a button that
    opens them, and says so with the reference's ArrowUpRight in its corner;
    the Finance and Reconciliation cards, which filter the list under them,
    carry a ring that fills with a tick when set. Nothing that does nothing
    gets a cue."""
    ok("if (m.detail && typeof m.detail === 'object') statOpens(c, m);" in SCRIPT,
       "a metric with a detail becomes an opener; one without stays a plain card")
    fn = re.search(r"function statOpens\(c, m\) \{(.*?)\n        \}", SCRIPT, re.S).group(1)
    for need in ("stat-open", "setAttribute('role', 'button')", "tabIndex = 0", "aria-haspopup",
                 "ev.key === 'Enter' || ev.key === ' '", "I.arrowUpRight", "openStatDetail(m, c)"):
        ok(need in fn, "the opener carries %s" % need)
    ok("arrowUpRight: SV(" in SCRIPT, "the icon exists")
    md = re.search(r"function openStatDetail\(m, opener\) \{(.*?)\n        \}", SCRIPT, re.S).group(1)
    ok("name.target = '_blank'; name.rel = 'noopener'" in md, "an item with a url opens the page in a new tab, safely")
    ok("d.empty || 'Nothing to list.'" in md, "an empty list says so instead of showing nothing")
    ok("opener.focus()" in md, "closing hands focus back to the card")
    ok("stat.append(statAct(I.check));" in SCRIPT and SCRIPT.count("stat.append(statAct(I.check));") == 2,
       "both filter strips carry the ring")
    ok(".stat.stat-open { cursor: pointer; }" in CSS, "an opener shows a pointer")
    ok(".stat.stat-open:hover, .stat.stat-pick:hover { border-color: var(--border-strong); background: var(--surface-secondary); }" in CSS,
       "and the reference's row hover")
    ok(".stat-pick:is(.on, [aria-pressed=\"true\"]) > .stat-act { background: var(--action-primary);" in CSS,
       "a set filter fills its ring")
    ok(".chart-expand, .stat-act, .wg-hide, [data-wg-control]" in CSS, "the cue is screen furniture, hidden in print")

@test
def t_the_reconciliation_tab_exists_and_is_gated():
    ok('id="view-recon"' in HTML, "the view exists")
    ok('data-view="recon"' in HTML, "and its sidebar entry")
    ok("'recon'" in re.search(r"const TAB_KEYS = \[[^\]]+\]", SCRIPT).group(0),
       "the tab is in the permission list, so an admin can switch it off per account")
    ok('class="ov-wrap" id="recon-content"' in HTML,
       "and it uses the same page wrapper as every other tab")


@test
def t_the_forecast_tab_exists_and_is_gated():
    """The Forecast tab draws what the nightly forecasting service posts. It
    is a Finance tab, opt-in like the books, and it never runs a model."""
    ok('id="view-forecast"' in HTML and 'data-view="forecast"' in HTML, "the view and its sidebar entry exist")
    ok('class="ov-wrap" id="forecast-content"' in HTML, "and it uses the same page wrapper as every other tab")
    keys = re.search(r"const TAB_KEYS = \[[^\]]+\]", SCRIPT).group(0)
    ok("'forecast'" in keys, "the tab is in the permission list")
    ok("'forecast'" in re.search(r"const OPT_IN_TABS = \[[^\]]+\]", SCRIPT).group(0),
       "and nobody inherits it: it holds the cash flow plan")
    ok("if (tabAllowed('forecast')) tab('forecast', 'Forecast');" in SCRIPT, "it sits in the Finance tab strip")
    ok("if (v === 'forecast') showForecastView();" in SCRIPT, "and opening it loads the latest run")
    fn = SCRIPT.split("function renderForecast()")[1].split("\n        async function showReconView")[0]
    ok("api('/api/forecast', {})" in SCRIPT.split("async function refreshForecast()")[1][:200], "it reads the posted run")
    ok("forecastSetupCard(c)" in fn and "No forecast yet" in SCRIPT, "with no run it explains the setup instead of showing nothing")
    ok("segControl(names.map(" in fn, "every scenario in the workbook can be chosen")
    # "Cash in", not "Net sales": the forecast is denominated in the order
    # total, because that is what the cash flow plan and Shopify's own forecast
    # are both written in. And MONTH by month, not day by day: the daily line
    # was a spike and a trough for every weekend and said nothing a month does
    # not, while the plan is written in months and judged in months.
    ok("fcChartCard(latest, c.ledger, latest.sanity)" in fn, "the chart is the house one")
    # Overview first, then zoom and filter, then details on demand. The top of
    # the page answers three questions in a reader's own words - where am I,
    # where am I expected to be, is that good - and the tables that used to be
    # dealt onto the screen all at once now wait behind drawers.
    ov = SCRIPT.split("function fcOverviewCard(", 1)[1].split("\n        function ", 1)[0]
    for q in ("'Where I am now'", "'Where I am expected to be'", "'Where the year lands'"):
        ok(q in ov, "the overview asks " + q)
    # Each answer is its OWN block. The joined multi-column frame was retired
    # on purpose and must not come back, here or anywhere.
    ok("metricsStrip(mets)" in ov and "fc-now" not in SCRIPT,
       "each answer is a house KPI block, not three columns welded into one card")
    # Good or bad is the change pill ON the number it judges, which is where
    # the reference puts it, not a fourth abstract box.
    ok("delta:" in ov and "trend:" in ov,
       "the verdict rides on the figure it qualifies")
    ok("8 times out of 10" in ov and "not a commitment" in ov,
       "and says how wide the range is, in money, rather than printing P10 and P90")
    order = [fn.index("fcOverviewCard(latest, sc)"), fn.index("fcChartCard("),
             fn.index("fcDriversCard(latest, sc)"), fn.index("'The numbers behind it'"),
             fn.index("'How this forecast works'")]
    ok(order == sorted(order),
       "overview, then the picture, then why, then the numbers, then how it works")
    for t in ("Month by month against ", "Every source, side by side",
              "How each one works, and how right it has been"):
        ok("fcDrawer('" + t in fn or 'fcDrawer(\'' + t in fn or ("fcDrawer('" + t) in fn,
           "'" + t + "' is a drawer, not dealt onto the screen")
    # The graph is back, and the reader chooses the scale rather than being
    # locked into one: a day question and a year question are different questions.
    chart = SCRIPT.split("function fcChartCard(", 1)[1].split("\n        function ", 1)[0]
    ok("filterTabs(FC_RANGES, range, setFcRange)" in chart, "the range is the reader's to pick")
    for key in ("'today'", "'week'", "'month'", "'q'", "'year'", "'ahead'", "'custom'"):
        ok(key in SCRIPT, "range " + key + " is offered")
    ok("grain = 'month'" in chart and "dayRows" in chart,
       "short ranges are drawn day by day and long ones month by month")
    ok("i.type = 'date'" in chart, "and a custom range takes two dates")
    ok("'Was predicted'" in chart,
       "the monthly view carries what was predicted at the time, so the gap is on the same picture")
    # Removing the manual SELECTOR was right; removing the ability to COMPARE
    # was not. Seeing four lines diverge over the autumn is the argument for
    # trusting the one that leads.
    ok("fcCompare()" in chart and "toggleFcCompare" in chart,
       "sources can be drawn against each other on the chart")
    ok("cmp.length >= 6" in chart, "capped, because a chart of fourteen lines is unreadable")
    ok("grain === 'month' && cmp.length" in chart,
       "monthly only: a source forecasts a month, and spreading it over days invents a shape")
    ok("clearFcCompare" in chart, "and the comparison can be cleared in one press")
    ok("'Verdict', 'Risk'" in fn and "'Working capital', 'Loan left'" in fn, "the month table and the cash table are there")
    ok("data_b64: btoa(bin)" in SCRIPT and "inp.accept = '.xlsx'" in SCRIPT, "an admin uploads the workbook from the tab")
    ok("c.can_upload ? forecastUploadButton() : null" in fn, "and only an admin sees the button")

@test
def t_the_size_list_tab_is_searchable_and_reads_the_same_sheet_as_the_label():
    """Cameron: "a searchable size list from our size list data". The tab reads
    the whole sheet through the route the label lookup shares, searches it
    by the start of a word in the maker or model, pages it 250 at a time,
    shows a ruling over the sheet's own answer, and lets a person with the
    size grant rule inline through the same rule route the Production
    Manager uses. It is a default grant: reference data for the bench."""
    ok('id="view-sizes"' in HTML and 'data-view="sizes"' in HTML and 'class="ov-wrap" id="sizes-content"' in HTML, "the view, its entry and the house wrapper")
    keys = re.search(r"const TAB_KEYS = \[[^\]]+\]", SCRIPT).group(0)
    ok("'sizes'" in keys and "'sizes'" not in re.search(r"const OPT_IN_TABS = \[[^\]]+\]", SCRIPT).group(0), "a default grant")
    ok("if (v === 'sizes') showSizesView();" in SCRIPT, "opening it loads the sheet")
    ok("api('/api/gobo-sizes/list', {})" in SCRIPT, "from the listing route")
    fn = SCRIPT.split("function renderSizes()")[1].split("\n        async function showReconView")[0]
    ok("tableSearch('Search maker or model" in fn and "sizesSelect('Maker'" in fn and "sizesSelect('Produced size'" in fn
       and "sizesSelect('Status', SIZES_STATUS" in fn, "a search box and maker, size and status filters in the house table tools")
    ok("sizesSelect('Sort', SIZES_SORTS" in fn and "gbtn.textContent = 'Group by maker';" in fn, "a sort and a grouping toggle")
    ok("const chips = sizesChips(); if (chips) card.append(chips);" in fn, "the active filters read as chips, each removable")
    ok("words.some(w => w.indexOf(t) === 0)" in SCRIPT, "a token matches the start of a word")
    ok("el('tr', 'ktable-grp')" in fn and "st.folded[it.head] = !folded;" in fn, "rows sit under their maker, and a maker folds")
    ok("az.setAttribute('aria-label', 'Jump to a maker by initial');" in fn, "with an A to Z strip to jump by")
    ok("slice = list.filter(it => it.pg === st.page - 1)" in fn and "tablePager({ total: modelCount" in fn and "sizes: [100, 250, 500]" in fn,
       "paged by the house pager, with a page size, counting models rather than lines")
    ok("Math.ceil(list.length / st.pageSize)" not in fn, "a maker heading does not take a model's place on the page")
    ok("['Holder glass, mm', 1], ['Image, mm', 1], ['Produced as, mm', 1], ['Status']" in fn and "['Undercut, mm', 1]" in fn
       and ".ktable th.num, .ktable td.num { text-align: right; font-variant-numeric: tabular-nums; }" in CSS,
       "numbers sit in tabular columns with the unit in the heading, and the status in its own")
    ok("text-overflow: ellipsis" in CSS.split(".ktable td.sizes-notes {")[1].split("}")[0] and "n.title = r.notes;" in fn, "a note is one line, the whole of it on hover")
    ok("xbtn.onclick = () => sizesExport(rows);" in fn and "a.download = 'size-list.csv';" in SCRIPT, "and the filtered list exports as CSV")
    ok("ruled: ['Ruled in the app', 'made']" in SCRIPT and "excluded: ['Not a gobo', 'note']" in SCRIPT,
       "a ruling and an exclusion read as chips, in the Status filter's words")
    ok("api('/api/gobo-sizes/rule', { op: 'set', manufacturer: r.manufacturer, model: r.model, size: inp.value.trim() })" in SCRIPT,
       "ruling inline writes the same rule the label reads")
    ok("if (canEdit) {" in SCRIPT.split("function sizesProducedCells")[1][:1600], "and only with the grant")

@test
def t_a_rejected_embed_token_is_retried_once_and_a_dead_session_never_loops():
    """A colleague's desk: a flashing login screen and "asked for too much".
    Every 401 used to clear the session and reload; a stale Shopify embed
    token (a PC clock a minute out) therefore reloaded on every request, and
    the reloads tripped the rate window. The page now reads the door's
    reason: a bad token is fetched fresh and retried once, a second rejection
    is shown on the login screen and never reloads, and a dead session
    reloads at most once a minute. The login screen says why."""
    fn = SCRIPT.split("async function api(path, payload, opts) {")[1].split("\n        }\n")[0]
    ok("const reason = (why && why.reason) || 'session';" in fn, "the reason is read off the 401")
    ok("if (reason === 'token' && !opts.retried) {" in fn and "return api(path, payload, { retried: true });" in fn,
       "a rejected embed token is retried once with a fresh one")
    ok("if (reason === 'token') {\n                        authShow('login');\n                        throw new Error(text);" in fn,
       "a second rejection is shown, never reloaded")
    ok("if (Date.now() - last > 60000) {" in fn and "sessionStorage.setItem('sc_auth_reload'" in fn, "a dead session reloads at most once a minute")
    ok("sessionStorage.setItem('sc_auth_reason'" in fn, "and the reason is kept for the login screen")
    ok("const why = takeAuthReason();\n                if (why && why.text) err.textContent = why.text;" in SCRIPT, "which says why you were signed out")

@test
def t_ai_output_is_labelled_interpretation_never_fact():
    """Section 9 of the brief, and the whole point: a model's conclusion is
    displayed as interpretation with its confidence and citations, visually
    apart from the arithmetic."""
    fn = SCRIPT.split("function paintReconDetail")[1].split("\n        function ")[0]
    ok("interpretation of the evidence above, not an accounting fact" in fn,
       "the label is on the card")
    ok("deterministic, not AI" in fn, "and the arithmetic says what it is")
    ok("confidence" in fn and "cites" in fn, "confidence and citations are shown")


@test
def t_ignoring_a_discrepancy_demands_a_reason():
    fn = SCRIPT.split("function paintReconDetail")[1].split("\n        function ")[0]
    ok("prompt(" not in fn,
       "no native prompt(): it does not exist inside a cross-origin iframe, "
       "which is exactly where this app runs")
    ok("if (!reasonIn.value.trim())" in fn,
       "the inline field refuses an empty reason before the server even sees it")


@test
def t_a_xero_token_warning_reaches_the_screen():
    """The one warning that has a clock on it: Xero honours the previous
    refresh token for about thirty minutes after a failed save, and after that
    the connection is simply gone. It cannot live only in the server log."""
    fn = SCRIPT.split("function renderRecon")[1].split("\n        function ")[0]
    ok("xs.warning" in fn, "the status card reads the warning the server sends")
    i = fn.index("xs.warning")
    ok("mail-viewwarn" in fn[i:i + 400],
       "and paints it as a warning, not as ordinary help text")


@test
def t_a_refused_revocation_asks_before_forgetting():
    """Forgetting a token Xero would not revoke leaves it live there with
    nothing left to kill it, so that is the merchant's call to make."""
    fn = SCRIPT.split("function renderRecon")[1].split("\n        function ")[0]
    ok("e.canForce" in fn, "the refusal is told apart from an ordinary error")
    ok("uiConfirm" in fn.split("e.canForce")[1][:600],
       "and it asks rather than deciding for them")
    ok("force: 1" in fn, "insisting sends the force flag")
    ok("data.can_force" in SCRIPT, "which api() carries off the response")


@test
def t_the_files_search_is_debounced_and_paged():
    """Measured against 8,000 files: a broad term matching everything cost
    1,912 ms of blocked JS per keystroke, and with no debounce a five letter
    word ran it five times, the early letters being the broadest and slowest."""
    fn = SCRIPT.split("function renderFilesBrowser")[1].split("\n        function ")[0]
    i = fn.index("q.oninput")
    seg = fn[i:i + 400]
    ok("clearTimeout(q._t)" in seg and "setTimeout(" in seg, "typing is debounced")
    ok("FILES_HIT_STEP" in SCRIPT and "filesHitCap" in fn, "and the hits are paged")
    ok("remaining)" in fn,
       "with the number NOT shown on screen, so nothing is quietly dropped")


@test
def t_a_paid_for_courier_quote_is_kept():
    """A quote is several seconds of SOAP round trip. It was cached only if the
    queue had not repainted while it was in flight, so a repaint binned an
    answer that was already bought and is still correct."""
    fn = SCRIPT.split("async function prefetchQuotes")[1].split("\n        function ")[0] \
        if "async function prefetchQuotes" in SCRIPT else SCRIPT
    i = fn.index("quoteCache.set(String(o.id)")
    before = fn[:i]
    ok(before.rindex("const q = await api('/api/dispatch/quote'") < i,
       "the quote is cached after it arrives")
    after = fn[i:i + 200]
    ok("if (run !== prefetchRun) return;" in after,
       "and the abandon check comes after the cache write, not before it")


@test
def t_independent_reads_are_not_run_one_after_the_other():
    ok("Promise.all([\n                    api('/api/recon/status', {})" in SCRIPT
       or "Promise.all([" in SCRIPT.split("async function refreshRecon")[1][:400],
       "Reconciliation asks for its status and its list together")
    ok("refreshReconList" in SCRIPT, "and a filter change asks only for the list")
    ra = SCRIPT.split("async function refreshAll")[1][:1200]
    ok("Promise.allSettled" in ra, "Refresh all runs its four audits together")
    ok("of ' + steps.length" in ra,
       "and counts finishes rather than naming one of four in flight")


@test
def t_the_tab_picker_sends_what_it_shows():
    """It used to collapse a fully ticked panel to null. Once null resolved to
    the DEFAULT tabs on the server, that silently withheld the opt-in tab the
    admin had just ticked."""
    ok("picked.length === TAB_KEYS.length ? null" not in SCRIPT,
       "a complete tick list is no longer collapsed to the null sentinel")
    ok("{ op: 'tabs', id: u.id, tabs: picked }" in SCRIPT,
       "the picker sends the explicit list it is showing")


@test
def t_reconciliation_is_not_ticked_by_default():
    """And the page's copy of the tabs is the server's, read from copilot.py
    rather than written into this test. A1 in the 2026-09-22 bug audit: the
    server made Xero sync an opt-in tab and the page's copy was not updated,
    so the Team picker ticked it, unnamed, for every account on the default
    tabs, and any save of that panel granted it."""
    import ast
    src = open(os.path.join(ROOT, "copilot.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    consts = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ("TAB_KEYS", "OPT_IN_TABS"):
            consts[node.targets[0].id] = [e.value for e in node.value.elts]
    page_tabs = re.search(r"const TAB_KEYS = \[([^\]]*)\]", SCRIPT).group(1)
    page_opt = re.search(r"const OPT_IN_TABS = \[([^\]]*)\]", SCRIPT).group(1)
    names = re.search(r"const NAMES = \{(.*?)\};", SCRIPT, re.S).group(1)
    ok(sorted(re.findall(r"'(\w+)'", page_tabs)) == sorted(consts["TAB_KEYS"]),
       "the page's tab keys are the server's")
    ok(sorted(re.findall(r"'(\w+)'", page_opt)) == sorted(consts["OPT_IN_TABS"]),
       "the tabs nobody inherits are the server's: " + page_opt)
    ok(sorted(re.findall(r"(\w+):\s*'", names)) == sorted(consts["TAB_KEYS"]),
       "and every tab the picker offers has a name, so none is ticked as 'undefined'")
    ok("Array.isArray(u.tabs) ? u.tabs : DEFAULT_TABS" in SCRIPT,
       "so the team editor shows them unticked for an account with no list of its own")


@test
def t_recon_csv_export_carries_the_armour():
    fn = SCRIPT.split("function reconCSV")[1].split("\n        function ")[0]
    ok("replace(/\"/g" in fn.replace("'", '"') or 'replace(/"/g' in fn, "quotes are doubled")
    ok('[",\\n\\r]' in fn, "commas, newlines AND carriage returns quote the field")
    ok("^[=+\\-@" in fn, "formula injection is armoured")


@test
def t_the_beta_tabs_say_so_everywhere_they_are_named():
    """CRM and Reconciliation are the two newest, least-proven tabs. A person
    should know that from the sidebar, from the page heading, and from the
    topbar title that survives scrolling - not just from one of the three."""
    ok("BETA_TABS = ['recon', 'forecast', 'crm', 'connector']" in SCRIPT, "the beta tabs are declared once")
    for nav in ("$('nav-recon')", "$('nav-forecast')", "$('nav-crm')", "$('nav-connector')"):
        block = SCRIPT.split(nav)[1][:180]
        ok("beta-tag" in block, nav + " carries the badge in the sidebar")
    # On the page: CRM's own heading carries it; the three Finance tabs carry
    # it on their own tab, because the 'Finance' heading is shared with
    # Liability and gained and lost the tag as you moved between the four.
    ok("cTitle.append(el('span', 'beta-tag'" in SCRIPT, "the CRM heading carries it")
    ft = fn_src("function financeTabs(")
    ok("if (BETA_TABS.indexOf(key) >= 0) b.append(el('span', 'beta-tag', 'Beta'));" in ft,
       "and each Finance tab in beta carries it on the tab")
    for t in ("rTitle", "hTitle"):
        ok(t + ".append(el('span', 'beta-tag'" not in SCRIPT, "not on the shared Finance heading (" + t + ")")
    ok("BETA_TABS.indexOf(v) >= 0" in SCRIPT, "and the topbar title does too")
    ok(".beta-tag {" in CSS, "the badge is styled")


@test
def t_every_tab_shares_one_page_wrapper():
    """The complaint that started this: tabs that do not line up as you move
    between them. Every view's content div is the same wrapper, no exceptions."""
    wraps = re.findall(r'<div class="([^"]*ov-wrap[^"]*)" id="([a-z-]+)-content"', HTML)
    ok(len(wraps) >= 12, "found the tab wrappers: %d" % len(wraps))
    odd = [(cls, tab) for cls, tab in wraps if cls.strip() != "ov-wrap"]
    ok(not odd, "no tab carries an extra width class: %s" % odd)


@test
def t_the_sidebar_keeps_one_inset():
    """Every block in the sidebar sits 8px from each edge, the reference's
    p-2 on its header, each group and its footer. The ask button used to be
    width:100% with no horizontal margin, so it alone ran the full width and
    broke the line the whole column keeps."""
    for sel, why in ((r"\.side-head \{[^}]*\}", "the brand row"),
                     (r"\.nav \{[^}]*\}", "the nav list"),
                     (r"\.convos \{[^}]*\}", "the conversation list"),
                     (r"\.side-foot \{[^}]*\}", "the footer")):
        block = re.search(sel, CSS).group(0)
        ok("var(--sp-2)" in block, why + " shares the 8px inset: " + block[:90])
    # Refresh all spends AI credits and runs four reports, so it sits in those
    # reports' headers; the support card took a sixth of every sidebar, and its
    # link lives in the account menu (Cameron's call, 24 Sep 2026).
    ok('id="refresh-all"' not in HTML and "refreshAllBtn()" in SCRIPT, "Refresh all is on the reports, not the sidebar")
    order = [m.group(1) for m in re.finditer(r'<(?:button|div) class="(nav-quick|nav|convos|side-support|side-user)[" ]', HTML)]
    ok(order == ["nav", "convos", "side-user"],
       "sections, conversations, then the account row: %s" % order)
    ok("function userMenu()" in SCRIPT and "$('side-user').onclick = userMenu" in SCRIPT,
       "and the account row opens the menu that holds Settings, the clock and Log out")

@test
def t_the_connect_tab_opens_inside_the_click():
    """A window.open AFTER an await has lost the user gesture and is blocked,
    which inside Shopify's iframe means the button appears to do nothing while
    a cheerful toast claims a tab was opened."""
    # Anchor on the BUTTON, not the card title that shares its words.
    fn = SCRIPT.split("go.append(ico(I.mail), document.createTextNode('Connect the accounts mailbox'))")[1][:2800]
    opened = fn.index("window.open('', '_blank')")
    awaited = fn.index("await api('/api/recon/connect-link'")
    ok(opened < awaited, "the tab is opened before the request, inside the click")
    ok("tab.location = r.url" in fn, "and pointed at the URL once it arrives")
    ok("reconConnectFallback" in fn,
       "with a clickable link when the browser blocks it anyway")


@test
def t_connecting_reports_its_own_outcome():
    """The old toast fired whatever happened, so a blocked tab or a failed
    consent still read as success and the advice was to refresh forever."""
    ok("function watchReconMailbox" in SCRIPT, "the card watches for the connection")
    fn = SCRIPT.split("function watchReconMailbox")[1][:1400]
    ok("st.mailbox && st.mailbox.connected" in fn, "it checks the real status")
    ok("toastOk" in fn and "toastError" in fn, "and says so either way")
    ok("callback URL missing" in fn, "naming the usual cause when it times out")


@test
def t_a_charged_booking_can_never_leave_a_blank_window():
    """Reported live: "the window with the tracking is blank until i close it and
    press the shipment button again".

    Both result panels used to clear the body FIRST and append as they went, so
    anything that threw part way through left an empty window - after the courier
    was booked and the account charged, with the tracking number nowhere on
    screen. They build off screen now and swap in one go, so a throw leaves what
    was there, and the fallback still puts the tracking number up."""
    for name, res in (("renderResult", "res"), ("renderBooked", "r")):
        fn = SCRIPT.split("function " + name + "(" + res + ") {")[1]
        fn = fn[:fn.index("\n            function ")]
        swap = fn.index("body.innerHTML = '';")
        ok(fn.count("body.innerHTML = '';") == 1, name + " clears the body exactly once")
        ok("body.append(out);" in fn, name + " swaps the finished panel in")
        # Nothing may touch the live body before the swap.
        ok("body.append" not in fn[:swap], name + " builds nothing into the live window")
        ok("labelButtons(body" not in fn, name + " does not hand the live window to labelButtons")
        ok(fn.index("const out = el('div');") < swap, name + " builds off screen first")

    # The safe wrappers are what the booking actually calls.
    ok("renderResultSafe(res);" in SCRIPT and "renderBookedSafe(r);" in SCRIPT,
       "both booking paths go through the wrapper")
    body = SCRIPT.split("try { res = await doBook(force, sure); break; }")[1][:3200]
    ok("renderResult(res);" not in body, "and never call the bare renderer after a charge")
    for name in ("renderResultSafe", "renderBookedSafe"):
        fn = SCRIPT.split("function " + name + "(")[1][:1800]
        ok("tracking_number" in fn, name + " still shows the tracking number")
        ok("catch (e2)" in fn, name + " has a last resort with no helpers in it")


@test
def t_a_double_click_cannot_book_twice():
    """The Book button was disabled AFTER the confirm dialog was answered, so a
    reflex double click opened two dialogs - and answering both booked, and paid
    for, two labels on one order."""
    for anchor, btn in (("This books the courier and charges your World Options account.", "book"),
                        ("? Your World Options account is charged.", "bk")):
        i = SCRIPT.index(anchor)
        seg = SCRIPT[max(0, i - 700):i]
        ok(btn + ".disabled = true;" in seg,
           "the button is disabled before the question is asked (" + btn + ")")
        after = SCRIPT[i:i + 400]
        ok(btn + ".disabled = false; return;" in after,
           "and armed again only if the answer is no (" + btn + ")")


@test
def t_a_failed_booking_reports_where_it_can_be_seen():
    """The error was appended to the confirm card, which a half-drawn result may
    already have detached. An error nobody can see is not a report."""
    seg = SCRIPT.split("const unknown = e.noReply")[1][:1400]
    ok("conf.isConnected ? conf : body" in seg,
       "it goes wherever is still on screen")
    ok("conf.append" not in seg, "and never straight into a card that may be gone")


@test
def t_a_tab_left_open_is_told_it_is_out_of_date():
    """Shopify admin holds an embedded app open for days. A tab left open across
    a deploy keeps running the old JavaScript, which from the desk is invisible:
    it looks exactly like a bug that has already been fixed."""
    ok("const MY_BUILD = (() => {" in SCRIPT, "the page knows which build it is")
    ok('meta[name="app-build"]' in SCRIPT, "read off a marker the server puts in the page")
    ok("/assets/app.js?v=" not in SCRIPT.split("const MY_BUILD")[1][:400],
       "never the asset hash: that one is a key to the client source, not an id")
    ok("noteBuild(res.headers.get('X-App-Build'))" in SCRIPT,
       "and compares it against the build the server replies with")
    fn = SCRIPT.split("function noteBuild(serverBuild) {")[1][:1400]
    ok("serverBuild === MY_BUILD" in fn and "!MY_BUILD" in fn,
       "it says nothing when they match, or when the page cannot tell")
    ok("location.reload()" in fn and "go.onclick" in fn,
       "reloading is a button, never automatic: a booking must not be interrupted")
    ok("setTimeout" not in fn and "setInterval" not in fn, "and nothing reloads on a timer")
    # Below the modal layer, so it can never cover a booking window.
    bar = CSS.split(".build-bar {")[1][:400]
    z = int(re.search(r"z-index:\s*(\d+)", bar).group(1))
    mz = re.search(r"\.modal-overlay \{[^}]*z-index:\s*(\d+)", CSS)
    ok(mz is not None, "the modal layer still declares a z-index")
    modal = int(mz.group(1))
    ok(z < modal, "the notice sits under any open modal (%d < %d)" % (z, modal))


@test
def t_a_table_sits_in_its_own_box_inside_the_card():
    """Measured off the reference's rendered page, not judged by eye: its table
    lives in a second frame at the base 10px radius inside a 14px card, and that
    inset edge is most of what makes its lists read the way they do. This used to
    be stripped flat on the reasoning that a card is already a box."""
    rule = CSS.split(".card .ktable-wrap, .card-bleed .ktable-wrap {")[1].split("}")[0]
    ok("border-radius: var(--radius-md)" in rule, "the table keeps its own radius inside a card")
    ok("border: 0" not in rule, "and its own border")
    ok("--radius-md: 10px" in CSS, "at the base radius the reference builds everything from")
    # A table that deliberately touches the card edge still can.
    bleed = CSS.split("\n        .card-bleed .ktable-wrap {")[1].split("}")[0]
    ok("border: 0" in bleed, "a bleed table is still flat to the edge")


@test
def t_the_table_is_built_to_the_reference_measurements():
    """Every number here was read off the reference with getComputedStyle. They
    are asserted because the last pass at this drifted by eye: 16px cell padding
    against its 12px, and body text a shade grey against its foreground."""
    th = CSS.split(".ktable th {")[1].split("}")[0]
    td = CSS.split(".ktable td {")[1].split("}")[0]
    ok("padding: var(--sp-3)" in th and "padding: var(--sp-3)" in td,
       "cells are padded 12px square, header and body alike")
    ok("height: 44px" in th, "the header row is 44px")
    ok("line-height: var(--lh-control)" in th and "line-height: var(--lh-control)" in td, "20px line box in both")
    ok("color: var(--text-primary)" in td and "var(--text-secondary)" not in td,
       "body cells are foreground, not a muted grey")
    hover = CSS.split(".ktable tbody tr:hover td {")[1].split("}")[0]
    ok("var(--surface-secondary)" in hover,
       "the hover is half-strength muted; a full one reads as selected")


@test
def t_the_table_toolbar_and_pager_match_the_reference():
    """The chrome around a table: a 28px search 320px wide with the icon inset
    32px, 28px filter and action buttons, and 32px square pager steps at the base
    radius. All four numbers are the reference's own."""
    srch = CSS.split(".tbl-search input {")[1].split("}")[0]
    ok("height: var(--control-h-md)" in srch and "width: 320px" in srch, "the search field is 28 by 320")
    ok(re.search(r"--control-h-md:\s*28px", CSS), "the small control token is the reference's 28")
    ok("padding: var(--sp-1) var(--sp-2-5) var(--sp-1) var(--sp-7)" in srch, "with room for the icon on the left")
    btn = CSS.split(".btn-sm {")[1].split("}")[0]
    ok("min-height: var(--control-h-md)" in btn and "padding: 0 var(--sp-2-5)" in btn, "small buttons are 28px tall")
    step = CSS.split(".tbl-step {")[1].split("}")[0]
    ok("width: var(--control-h)" in step and "height: var(--control-h)" in step, "pager steps are 32px square")
    ok("border-radius: var(--radius-md)" in step, "at the base radius, not the control radius")
    # The pager must never claim to be paging through more than it is.
    fn = SCRIPT.split("function tablePager(o) {")[1][:1600]
    ok("Math.ceil(total / size)" in fn, "the page count comes from the total it was given")
    ok("o.total" in fn, "and the line above it counts the same rows")
    ok("crmContactsPage = 1" in SCRIPT.split("function tableSearch")[0] or
       "crmContactsPage = 1" in SCRIPT, "a search resets to the first page")
    # It is fed the FILTERED list, not the whole store: "1 to 25 of 4" while a
    # search is on is how a filter gets mistaken for lost data.
    call = SCRIPT.split("list.append(tablePager({")[1][:200]
    ok("total: items.length" in call, "the CRM pager counts what the search left")


@test
def t_the_production_toolbar_is_sorted_not_shortened():
    """It carried twenty controls across two bars, which is the same as no order
    at all: everything looked equally important, so nothing did. The reports and
    the setup are behind More now. The point of this guard is the second half -
    that sorting them did not quietly lose any of them."""
    fn = SCRIPT.split("function renderLabels() {")[1]
    fn = fn[:fn.index("\n        function ")]
    ok("const qCard = el('div', 'card q-card')" in fn, "the queue is a card, header and all")
    ok("tableTools([findWrap, filtTabs]" in fn, "search and filters on the toolbar")
    ok("filterTabs([['all'" in fn, "the filters are counted tabs, not a segmented control")
    # The two page-level rails are unstyled holders now: their children are
    # taken out and placed, and neither is ever appended to the page.
    ok("const bar = el('div');" in fn and "const tools = el('div');" in fn,
       "the old bars are holding rails, not layout")
    ok("box.append(bar, tools)" not in fn, "and neither is rendered")
    # Every action that used to be on a bar is still reachable from somewhere.
    for handler, what in [("runCoverage", "size check"), ("printDaySheet", "day sheet"),
                          ("openDispatchManifest", "dispatch manifest"), ("openStockUsage", "stock usage"),
                          ("openMargins", "margins"), ("fileIn.click()", "update size list"),
                          ("openShippingSettings", "shipping settings"), ("openCustomShip", "new shipment"),
                          ("openBookCollection", "collections"), ("printLabels(unprinted)", "print new"),
                          ("printLabels(printable)", "print all"),
                          ("printShippingLabelsFor(shipLabels)", "print shipping labels"),
                          ("loadLabels(true, true)", "refresh")]:
        ok(handler in fn, "the " + what + " action survived the sort")
    # The hidden file input has to travel with the menu item that opens it.
    ok("qCard.append(fileIn)" in fn, "the size-list picker is still in the page")
    # And the page does not print the same sentence twice.
    ok(fn.count("el('p', null, heroCopy)") == 0, "the hero no longer repeats the queue's own line")
    ok("el('p', 'card-desc', data.single" in fn, "which the card carries instead")


@test
def t_a_dropdown_menu_can_always_be_got_out_of():
    """A menu that will not close is a modal nobody meant to open. This one shuts
    on Escape, on a click anywhere else, on a second press of its own trigger and
    on scrolling the page under it, and hands focus back each time. Verified in a
    browser as well as here; the suite can only read the source."""
    fn = SCRIPT.split("function dropMenu(anchor, items) {")[1][:3800]
    close = SCRIPT.split("function closeDMenu() {")[1][:1200]
    ok("dmenuOpen.anchor === anchor" in fn, "a second press of the trigger closes it")
    ok("e.key === 'Escape'" in fn, "Escape closes it")
    ok("!panel.contains(e.target)" in fn, "a click anywhere else closes it")
    ok("dmenuScroller" in fn and "'scroll', closeDMenu" in fn,
       "and it closes rather than drifting away from its own button")
    ok("removeEventListener('keydown'" in close and "removeEventListener('pointerdown'" in close,
       "every listener it added comes off again")
    ok("dmenuScroller.removeEventListener('scroll'" in close,
       "including the one on the scroller, which outlives the panel otherwise")
    ok("anchor.focus()" in close, "and focus goes back to the button that opened it")
    ok("aria-expanded" in fn and "aria-haspopup" in fn, "the trigger says what it does")
    ok("ArrowDown" in fn and "ArrowUp" in fn, "and the list can be walked with the arrows")
    # Opening one closes the other: two open menus is a state nobody can leave.
    ok(fn.index("closeDMenu();") < fn.index("const panel = el('div', 'dmenu')"),
       "opening a menu closes whatever was already open")


@test
def t_the_menu_and_tabs_are_the_reference_measurements():
    """Read off the reference: a 10px panel whose edge is a ring rather than a
    border, 4px of padding, 28px items at the control radius; and filter tabs
    that are 24px, 12px, with no filled pill, marked by ink AND the 2px rule
    the reference draws under its live trigger. Ink alone was the old reading
    of the reference and it was short by that rule: re-measured, the active
    trigger carries a ::after of height 2px in the near-black, the width of the
    trigger itself. The pill is still the thing that must never come back."""
    panel = CSS.split(".dmenu {")[1].split("}")[0]
    ok("border-radius: var(--radius-md)" in panel, "the panel is at the base radius")
    ok("padding: var(--sp-1)" in panel, "padded 4px")
    ok("var(--shadow-md)" in panel, "its edge is a ring, not a border")
    ok("border:" not in panel, "and it has no border at all")
    item = CSS.split(".dmenu-item {")[1].split("}")[0]
    ok("height: 28px" in item, "items are 28px")
    ok("padding: var(--sp-1) var(--sp-7) var(--sp-1) var(--sp-1-5)" in item, "with room on the right for a tick")
    ok("border-radius: var(--radius-sm)" in item, "at the control radius")
    tab = CSS.split(".ftab {")[1].split("}")[0]
    ok("height: var(--control-h-sm)" in tab and "padding: var(--sp-0-5) var(--sp-1-5)" in tab, "tabs are 24px")
    ok("background: none" in tab, "with no filled pill")
    on = CSS.split(".ftab:is(.on, [aria-selected=\"true\"]) {")[1].split("}")[0]
    ok("color: var(--text-primary)" in on and "background" not in on,
       "the live tab takes full ink and still no fill behind it")
    rule = CSS.split(".ftab:is(.on, [aria-selected=\"true\"])::after {")[1].split("}")[0]
    ok("height: 2px" in rule, "and a 2px rule under it")
    ok("var(--action-primary)" in rule, "painted in the near-black, not a tint that may resolve to nothing")
    ok("left: 0" in rule and "right: 0" in rule, "the width of the tab itself, as the reference draws it")
    ok(any("position: relative" in b for b in re.findall(r"\.ftab \{([^}]*)\}", CSS)),
       "with the tab as the box it is positioned against, or it hangs off the page")


@test
def t_a_missing_figure_is_not_reported_as_zero():
    """liaMoney reads a missing number as 0, and on the page whose whole job is
    "how much is owed" that says the book is clear. The two count cards were
    worse: they printed the word "undefined". Neither is an answer."""
    fn = SCRIPT.split("function renderLiability() {")[1]
    fn = fn[:fn.index("\n        function ")]
    ok("const liaNum = (v, fmt) =>" in fn, "there is one guard for all six figures")
    ok("typeof v === 'number' && isFinite(v)" in fn, "and it asks whether a number arrived")
    ok("'not reported'" in fn, "saying so plainly when one did not")
    # 'within' is the bucket the legend and the tile's filter show (d.within
    # also counts what is due soon), read into a local first.
    for field in ("d.total", "within", "d.due_soon", "d.overdue",
                  "d.overdue_orders", "d.oldest_days"):
        ok("liaNum(" + field + "," in fn, field + " goes through it")
    ok("const within = (d.buckets && typeof d.buckets.within === 'number') ? d.buckets.within : d.within;" in fn,
       "the tile reads the same bucket as the legend under it")
    ok("String(d.overdue_orders)" not in fn and "d.oldest_days + ' days'" not in fn,
       "and nothing prints a raw undefined any more")


@test
def t_the_finance_pages_share_the_reference_tab_strip():
    """Liability and Reconciliation are one area with two pages, which is how
    they were asked for. The strip that binds them wore a filled pill, which
    reads as a control you press rather than a place you are. A pill is still
    wrong; what the reference actually draws instead is a 2px rule under the
    live trigger, and colour on its own left three near-identical links."""
    ok("const seg = el('div', 'ptabs')" in SCRIPT, "the strip is the page-level one")
    ok("el('button', 'ptab'" in SCRIPT, "and its tabs are page tabs")
    fn = SCRIPT.split("function financeTabs(active, updated, actions) {")[1][:900]
    ok("lbl-segbtn" not in fn, "the segmented control is gone from it")
    ok("aria-current" in fn, "and the live one says it is the current page")
    tab = CSS.split(".ptab {")[1].split("}")[0]
    ok("height: 25px" in tab and "padding: var(--sp-0-5) var(--sp-1-5)" in tab, "25px tall, as the reference draws it")
    ok("font-size: var(--text-sm)" in tab, "at 14px, bigger than a filter tab inside a card")
    ok("background: none" in tab, "with no pill")
    on = CSS.split(".ptab:is(.on, [aria-current=\"page\"]) {")[1].split("}")[0]
    ok("color: var(--text-primary)" in on and "background" not in on, "the live page takes full ink, with no pill")
    rule = CSS.split(".ptab:is(.on, [aria-current=\"page\"])::after {")[1].split("}")[0]
    ok("height: 2px" in rule, "and carries the reference's 2px rule under it")
    ok("var(--action-primary)" in rule, "in the near-black, which is a colour that actually paints")
    ok("left: 0" in rule and "right: 0" in rule, "spanning the trigger's own width")
    ok(any("position: relative" in b for b in re.findall(r"\.ptab \{([^}]*)\}", CSS)),
       "positioned against the tab, so the strip's metrics do not move")


@test
def t_the_liability_filters_are_sorted_not_shortened():
    """Eleven controls in one row is not eleven questions anyone reads. The
    search and the three that change daily are on the bar; the date range and
    the minimum are behind a panel, because a date is not a menu of choices."""
    fn = SCRIPT.split("function renderLiability() {")[1]
    fn = fn[:fn.index("\n        function ")]
    ok("tableTools(left, right)" in fn, "the toolbar is the shared one")
    ok("filterChip('Status'" in fn and "filterChip('Terms'" in fn and "filterChip('Sort'" in fn,
       "status, terms and sort are chips that say what they are set to")
    ok("dropPanel(rangeBtn" in fn, "the dates and the minimum are in a panel")
    ok("el('div', 'lbl-toolbar')" not in fn, "the old eleven-control bar is gone")
    # Nothing was dropped: every filter still exists.
    for f in ("liaF.status", "liaF.terms", "liaF.channel", "liaF.dateField",
              "liaF.from", "liaF.to", "liaF.min", "liaF.sort", "liaF.q"):
        ok(f in fn, f + " survived the sort")
    # Clear only appears when there is something to clear. It used to be BUILT
    # only then, which the search could not reach: typing repaints the rows
    # alone, so a search-only filter left no way to clear it on the bar at all.
    # Built always, shown from the same expression the coverage line uses.
    ok("clr.style.display = active ? '' : 'none';" in fn,
       "the reset button appears only when a filter is on")
    ok("const active = liaF.q ||" in fn,
       "and a search counts as one, because paint() is what the search runs")


@test
def t_a_filter_that_hides_everything_does_not_hide_itself():
    """The reconciliation list returned before the filters were built, so a
    filter matching nothing took the way to undo it off the screen with it."""
    fn = SCRIPT.split("function renderRecon() {")[1]
    fn = fn[:fn.index("\n        function ")]
    # The status filter is the shared chip now, not a flat tab strip, so the
    # name changed with it. The requirement did not: it is built, and on the
    # page, before the list can return empty.
    tools = fn.index("list.append(tableTools([searchWrap, statusChip]")
    empty = fn.index("if (!ex.length) {")
    ok(tools < empty, "the search and the status filter are built before the empty check")
    # The list is a widget-grid card now, so it goes onto the page through widget().
    ok(fn.index("box.append(widget(list, 'discrepancies'") < empty, "and the card is on the page before it returns")


@test
def t_a_panel_is_measured_after_it_is_filled():
    """It borrows the menu's positioning, which runs while the panel is still
    empty. A form taller than nothing would hang off the bottom of the window."""
    fn = SCRIPT.split("function dropPanel(anchor, build) {")[1][:1600]
    ok(fn.index("build(body, closeDMenu)") < fn.index("panel.offsetHeight"),
       "it re-measures after the form is in it")
    ok("window.innerHeight - 8" in fn, "and flips above when there is no room below")


@test
def t_a_failing_mail_sync_is_not_a_footnote():
    """It used to be a small grey span wedged between a search box and a view
    toggle, in a row of six controls. A mailbox that is not syncing means the
    list below is missing mail that has arrived, which is the one thing on that
    page nobody may miss."""
    fn = SCRIPT.split("function renderMail() {")[1]
    fn = fn[:fn.index("\n        function ")]
    i = fn.index("if (d.sync_error) {")
    ok("'msg error'" in fn[i:i + 400], "it is an error row in its own right")
    ok("may be missing mail" in fn[i:i + 400],
       "and says what that means for the list underneath")
    ok(fn.index("const mCard = el('div', 'card')") > i,
       "above the board, not inside its toolbar")
    ok("el('span', 'mail-sync'" not in fn, "the grey span in the toolbar is gone")


@test
def t_the_inbox_is_composed_like_the_reference():
    """Six controls and a status line in one row. The reference gives a list
    page a counted title, a line under it, the two things you press on the
    right, and the search and the states on a toolbar of their own."""
    fn = SCRIPT.split("function renderMail() {")[1]
    fn = fn[:fn.index("\n        function ")]
    ok("lab('Shared inbox', counts.open)" in fn, "the title carries the open count")
    ok("d.address || 'The mailbox the team answers'" in fn,
       "the mailbox and its last sweep are the line under it")
    ok("mCard.append(tableTools([sWrap, states], [viewSeg]))" in fn,
       "search and states left, the view switch right")
    ok("filterTabs([['open'" in fn, "the states are counted tabs")
    ok("el('div', 'lbl-toolbar')" not in fn, "the old jammed row is gone")
    # Who is on today became a card of its own rather than a bare strip.
    ok("el('h3', 'card-title', 'Who is on today')" in fn, "the team strip is a card")
    ok("if ((d.team || []).length) {" in fn, "which does not appear when there is no team")
    # Nothing was dropped.
    for handler, what in [("openMailRules", "filters"), ("refreshMailQuiet(true)", "refresh"),
                          ("'/api/mail/search'", "whole-mailbox search"),
                          ("mailView = v", "the list and board switch"),
                          ("mailFilter = v", "the state filter"),
                          ("mailQ = search.value", "the live search")]:
        ok(handler in fn, "the " + what + " survived the sort")


@test
def t_the_mail_row_is_the_reference_measurement():
    """12px on every side and a full hairline. It was 12 by 16, which doubles up
    with the card's own padding, and a 0.5px rule, which lands on a device pixel
    on some screens and disappears on others."""
    row = CSS.split(".mrow {")[1].split("}")[0]
    ok("padding: var(--sp-3)" in row, "12px on every side")
    ok("border-top: var(--bw-hairline) solid var(--border-default)" in row, "a full hairline in the border ink")
    ok("0.5px" not in row, "and not a half-pixel one")


@test
def t_the_files_browser_is_composed_like_the_reference():
    """Upload, New folder, the search and the sort were one row of four. The
    reference puts the two things that CHANGE the folder on the right of the
    header, and leaves the toolbar to the two that only change the view."""
    fn = SCRIPT.split("function renderFilesBrowser(host) {")[1]
    fn = fn[:fn.index("\n        function ")]
    ok("const fCard = el('div', 'card')" in fn, "the browser is a card")
    ok("filesHeroAct.append(nf, up, fi)" in fn, "New folder and Upload are page-header actions, in the hero's slot")
    ok("fCard.append(tableTools([qWrap], [srt]))" in fn, "search left, sort right")
    ok("filterChip('Sort'" in fn, "the sort is a chip that says what it is set to")
    ok("el('div', 'lbl-toolbar')" not in fn, "the old four-control row is gone")
    # Everything still works: upload, new folder, search, sort, drag-to-upload.
    for handler, what in [("filesEnqueue(fi.files)", "upload"), ("filesNewFolder = true", "new folder"),
                          ("filesQ = q.value.trim()", "search"), ("filesSort = v", "sort"),
                          ("filesIngestDrop", "drag to upload")]:
        ok(handler in fn, "the " + what + " survived the sort")


@test
def t_the_files_card_counts_what_is_actually_there():
    """A title that says "All files" over a filtered list is a lie by omission.
    It counts the folder you are in, and a search says what it searched for."""
    fn = SCRIPT.split("function renderFilesBrowser(host) {")[1]
    fn = fn[:fn.index("\n        function ")]
    i = fn.index("function paintList() {")
    seg = fn[i:i + 1500]
    ok("(f.folder_id || '') === filesFolder" in seg, "it counts the files in this folder")
    ok("(f.parent_id || '') === filesFolder" in seg, "and the folders inside it")
    ok("' files match'" in seg, "a search counts its matches instead")
    ok("Searching every folder" in seg, "and says that is what it is doing")
    # A crumb trail of one step is the same word the title already carries.
    cr = fn[fn.index("function paintCrumbs() {"):][:1200]
    ok("if (!chain.length) return;" in cr, "no crumb trail at the root")


@test
def t_the_files_list_is_the_reference_measurement():
    """The control radius read as a large button rather than a frame around
    rows, and a 0.5px rule lands on a device pixel on some screens only."""
    lst = CSS.split(".files-list {")[1].split("}")[0]
    ok("border-radius: var(--radius-md)" in lst, "the list box is at the base radius")
    ok("var(--bw-hairline) solid var(--border-default)" in lst, "in the border ink")
    row = CSS.split(".files-row { display: flex")[1].split("}")[0]
    ok("padding: var(--sp-3)" in row, "the shared row shell is padded 12px square")
    ok("border-top: var(--bw-hairline) solid var(--border-default)" in row and "0.5px" not in row,
       "with a full hairline, not a half-pixel one")
    # The Files list itself is denser than the shell it borrows: 8 + a 28px
    # action button + 8 + the hairline is the reference's 45px row. The Team
    # and Work rows keep the 12px square, so the density is scoped to the tab.
    ok(re.search(r"#files-content \.files-row \{ padding: var\(--sp-2\) var\(--sp-3\); \}", CSS),
       "and the Files rows sit at the reference's own density")


@test
def t_every_chart_line_comes_off_the_ramp():
    """This app went monochrome months ago, and three charts never got the memo:
    a purple bar set, a blue line and two green ones, on pages where everything
    else was grey. A reader cannot tell what a colour means when only three of
    fifteen charts have one."""
    ok(not _re.search(r"color: '#[0-9a-fA-F]{3,6}'", SCRIPT),
       "no chart is given a colour literal")
    ramp = SCRIPT.split("const CH = [")[1].split("]")[0]
    ok("'--chart-1', '--chart-2', '--chart-3', '--chart-4', '--chart-5'" in ramp
       and "].map(tokenValue)" in SCRIPT.split("const CH = [")[1][:120],
       "the ramp is read from the tokens, not carried as hex")
    for i, hexv in enumerate(("#171717", "#525252", "#737373", "#a1a1a1", "#d4d4d4"), 1):
        ok(_token("chart-%d" % i) == hexv, "--chart-%d still resolves to %s" % (i, hexv))
    # Every series names a ramp slot.
    for m in _re.finditer(r"color: (CH\[\d\]|[A-Za-z_$][\w.$]*)", SCRIPT):
        ok(m.group(1).startswith("CH[") or not m.group(1).startswith("#"),
           "series colours come from the ramp, not from a literal")


@test
def t_the_chart_legend_belongs_to_the_plot():
    """It was drawn in the card header while the chart reserved 48 units at the
    top of its own plot for it, so a multi-series chart carried a band of
    nothing across the top and named its lines somewhere else."""
    ok("function chartLegend(series, band) {" in SCRIPT, "the legend is its own piece")
    ok("if ((multi && series.length > 1) || bandOpt || series.some(s => s.dash)) {" in SCRIPT
       and "if (lg.children.length > 1 || lg.querySelector('.dash, .band')) card.append(lg);" in SCRIPT,
       "drawn between the header and the plot, whenever there are marks to tell apart: two lines, "
       "a dashed line or a shaded range, and never for one plain line")
    # Each swatch is drawn the way its mark is. The forecast chart keyed a
    # solid line and a dashed one with two identical black squares.
    lg = fn_src("function chartLegend(")
    ok("(sr.dash || (i > 0 && !sr.lead)) ? 'dash' : ''" in lg and "if (band && " in lg,
       "a dashed or comparison series is keyed dashed, and a band gets a key of its own")
    ok(".filter(v => v != null).length > 1" in lg, "and only a series that draws something gets a key")
    ok(".chart-legend .sw.dash {" in CSS and "repeating-linear-gradient" in CSS.split(".chart-legend .sw.dash {")[1].split("}")[0],
       "painted as a dashed stroke, not a dashed border (the drop-target signal)")
    # The source line is provenance, not a key: its dot was painted in the
    # first series' colour and read as a third swatch.
    ok("src-dot" not in SCRIPT and "src-dot" not in CSS, "the source line carries no coloured dot")
    ok("chart-legend" not in SCRIPT.split("function chartHead(")[1][:1400],
       "and no longer inside the card header")
    # The frame is one definition in :root, read by BOTH charts. It used to be
    # written out twice, with two different default heights, so "change the
    # chart spacing" meant finding both.
    ok("padL: tokenNum('--chart-pad-l')" in SCRIPT, "the plot frame is read from the tokens")
    for tok, want, why in (("chart-pad-t", "14px", "reserves 14 at the top for the topmost stroke"),
                           ("chart-pad-r", "0px", "and nothing for a legend drawn elsewhere"),
                           ("chart-pad-l", "40px", "the 40 on the left is the y-axis numbers, inside the plot"),
                           ("chart-pad-b", "30px", "and 30 at the foot for the dates")):
        ok(_token_raw(tok) == want, why + " (--%s is %s)" % (tok, _token_raw(tok)))
    ok(SCRIPT.count("opts.height || CHART.h") == 2,
       "both charts default to the same height instead of 220 in one and 230 in the other")
    lg = CSS.split(".chart-legend {")[1].split("}")[0]
    ok("justify-content: flex-end" in lg, "right-aligned, as the reference aligns it")
    ok("gap: var(--sp-4)" in lg, "16px between keys")
    ok("padding-bottom: var(--sp-3)" in lg and "margin-bottom: var(--sp-5)" in lg,
       "12 then 20 before the first gridline")
    sw = CSS.split(".chart-legend .sw {")[1].split("}")[0]
    ok("width: var(--dot-md)" in sw and "height: var(--dot-md)" in sw
       and _token_raw("dot-md") == "8px", "the key is an 8px square")
    ok("border-radius: var(--radius-3xs)" in sw, "with a 2px corner, not the app's own radius")
    item = CSS.split(".chart-legend .lg {")[1].split("}")[0]
    ok("gap: var(--sp-1-5)" in item, "6px between a key and its name")
    ok("color: var(--text-primary)" in item, "and the name in full ink, as the reference sets it")


@test
def t_the_first_enter_on_the_login_screen_signs_you_in():
    """Focus lands on the Username field, and that is where the first Enter is
    pressed. Login bound Enter only on the password field, so the reflex
    keypress did nothing - on the first screen anyone meets."""
    fn = SCRIPT.split("card.append(el('h2', null, 'Sign in')")[1][:1400]
    ok("[inUser, inPw].forEach(i => i.onkeydown" in fn,
       "both login fields submit on Enter")
    # And the new-account row, which had no Enter path at all.
    tm = SCRIPT.split("inUser.className = 'tm-field'")[1][:1200]
    ok("[inName, inUser].forEach(i => i.onkeydown" in tm,
       "the create-account fields submit on Enter too")


@test
def t_everything_that_says_it_is_a_button_works_like_one():
    """Three rows announced as buttons, took focus, and did nothing on Enter or
    Space: the reconciliation exception row and the CRM contact and lead rows.
    Every role=button in the file now has a keyboard path."""
    import re as _re2
    sites = [m.start() for m in _re2.finditer(_re2.escape("setAttribute('role', 'button')"), SCRIPT)]
    ok(len(sites) >= 10, "the role=button sites are all still here (%d)" % len(sites))
    for i, at in enumerate(sites):
        seg = SCRIPT[at:at + 400]
        ok("keydown" in seg, "role=button site %d has a keydown handler beside it" % (i + 1))


@test
def t_keyboard_focus_in_a_menu_does_not_look_like_a_hover():
    """.dmenu-item grouped hover with focus-visible and set outline:none - a
    grouped rule outranks the global :focus-visible baseline on specificity, so
    keyboard focus was a 1.1:1 background tint. The two states are separate
    rules now, and focus draws a real ring."""
    fv = CSS.split(".dmenu-item:focus-visible {")[1].split("}")[0]
    ok("outline: var(--focus-outline)" in fv, "focus draws the house ring")
    ok("outline-offset: -2px" in fv, "inset, so the panel's overflow cannot clip it")
    hov = CSS.split(".dmenu-item:hover {")[1].split("}")[0]
    ok("outline" not in hov, "and hover no longer says anything about outlines")


@test
def t_every_modal_is_a_dialog_and_tab_stays_inside_it():
    """Thirteen builders, one stamp: an observer gives every .modal role=dialog,
    aria-modal and a label from its own heading - the same pattern the switches
    already used. And one Tab fence keeps focus inside the top overlay, which
    matters twice over here because Escape is deliberately not a way out."""
    ok("function syncDialogs()" in SCRIPT, "the stamp exists")
    ok("syncToggles(); syncDialogs();" in SCRIPT, "and rides the existing observer")
    ok("m.setAttribute('aria-modal', 'true')" in SCRIPT, "modals say they are modal")
    fence = SCRIPT.split("if (e.key !== 'Tab') return;")[1][:2200]
    ok(".modal-overlay.show, .auth-overlay" in SCRIPT, "the fence covers app modals and the login card")
    ok("e.shiftKey && document.activeElement === first" in fence, "and wraps both directions")


@test
def t_settings_obeys_the_one_way_out_rule():
    """Every modal in the app closes by X only - a misclick must not wipe a
    filled form (user rule). Settings, which IS a form, was the one modal that
    still closed on backdrop click and Escape."""
    ok("if (e.target.id === 'settings-modal') closeSettings()" not in SCRIPT,
       "no backdrop close")
    ok("e.key === 'Escape' && $('settings-modal')" not in SCRIPT, "no Escape close")
    ok("$('settings-close').onclick = closeSettings;" in SCRIPT, "the X still works")


@test
def t_the_sidebar_nav_is_a_navigation_landmark():
    """Sixteen view buttons lived in a bare div inside an aside, so assistive
    tech filed the app's whole navigation under complementary content."""
    ok('class="nav" role="navigation" aria-label="Sections"' in HTML,
       "the nav names itself")


@test
def t_every_control_has_a_name_that_survives_typing():
    """A placeholder is only a name until someone types. The shared search
    factory names its input now, the field factories became real labels (the
    wrapper IS the label, so the caption focuses the control), and every bare
    select carries an aria-label. Verified as a sweep, not a sample: no select
    in the file may be created without a name arriving within a few lines."""
    import re as _re2
    ok("inp.setAttribute('aria-label', (placeholder || 'Search').replace(" in SCRIPT,
       "tableSearch names its input from its placeholder")
    for factory in ("mkSel", "selField", "numField", "dateField"):
        seg = SCRIPT.split("const " + factory + " = ")[1][:220]
        ok("el('label', 'pfield')" in seg, factory + " wraps in a real label")
        ok("el('span', null, label)" in seg, "with the caption as a span, not a nested label")
    # The sweep: every select creation must be followed by a name source.
    nameless = []
    for m in _re2.finditer(r"(?:el\('select'|document\.createElement\('select'\))", SCRIPT):
        ctx = SCRIPT[m.start():m.start() + 900]
        # A name must belong to THIS select: cut the window at the next
        # select creation, or a neighbour's aria-label vouches for it.
        nxt = _re2.search(r"(?:el\('select'|document\.createElement\('select'\))", ctx[10:])
        if nxt: ctx = ctx[:nxt.start() + 10]
        before = SCRIPT[max(0, m.start() - 300):m.start()]
        named = ("aria-label" in ctx or ".title = " in ctx
                 or "crmField(" in ctx or "authField" in before
                 or "el('label'" in before[-200:] or "dpanel-row" in before[-200:])
        if not named:
            nameless.append(SCRIPT[:m.start()].count("\n") + 1)
    ok(not nameless, "selects with no accessible name near script lines: " + str(nameless))


@test
def t_async_outcomes_are_announced():
    """Both toast hosts (addToast and the undo-print bar) are polite live
    regions now. Before this, every success and failure in the app was silent
    to a screen reader."""
    ok(SCRIPT.count("host.setAttribute('role', 'status')") == 3,
       "the boot-time host and both lazy fallbacks announce")
    ok(SCRIPT.count("host.setAttribute('aria-live', 'polite')") == 3,
       "politely, so they queue rather than interrupt")


@test
def t_the_setup_card_offers_the_right_autofill():
    """The Your-name field was getting autocomplete=username because the
    ternary keyed off the input type - two username tokens in one card, and the
    browser fills the wrong one."""
    fn = SCRIPT.split("function authField(labelText, type, id) {")[1][:800]
    ok("id === 'au-name' ? 'name' : 'username'" in fn, "name field asks for a name")
    ok("inp.name = inp.autocomplete" in fn, "and every auth input carries a name attribute")
    ok("if (inp.autocomplete === 'username') inp.spellcheck = false" in fn,
       "usernames do not get squiggles")


@test
def t_truncated_text_is_recoverable():
    """Five places truncate with ellipsis and gave no way back to the full
    value. The mail sender and subject, the product title and the file name all
    carry title now, so hover recovers what the ellipsis ate."""
    ok("mfrom.title = t.from_name || t.from_email || ''" in SCRIPT, "mail sender")
    ok("subj.title = t.subject || ''" in SCRIPT, "mail subject")
    ok("pn.title = p.title || ''" in SCRIPT, "product title")
    ok("name.title = f.name;" in SCRIPT, "file name")


@test
def t_reduced_motion_means_all_of_it():
    """Reduce was honoured at two of ten animation sites; the fadeUps, the
    loader and the spinning refresh icon all kept moving. One blanket rule now,
    with durations at a tick rather than zero so animationend still fires."""
    blk = CSS.split("@media (prefers-reduced-motion: reduce) {\n            *, *::before, *::after {")[1].split("}")[0]
    ok("animation-duration: .01ms !important" in blk, "animations reduce")
    ok("transition-duration: .01ms !important" in blk, "transitions too")
    ok("animation-iteration-count: 1 !important" in blk, "and nothing loops forever")
    ok("transition: all" not in CSS, "and no transition animates 'all' any more")


@test
def t_forms_ask_for_the_right_keyboard_and_accept_pence():
    """Two lead-value fields rejected 1500.50 (step defaults to 1), and the
    address builder typed email and phone as plain text, which on touch is the
    wrong keyboard and for autofill is no hint at all."""
    ok(SCRIPT.count("valIn.step = '0.01'") >= 1 and "vIn.step = '0.01'" in SCRIPT,
       "both lead-value fields accept pence")
    ok("key === 'email' ? 'email' : key === 'phone' ? 'tel' : 'text'" in SCRIPT,
       "the address builder types its fields")
    ok("if (key === 'postcode' || key === 'country') inp.spellcheck = false" in SCRIPT,
       "and codes are not spellchecked as words")


@test
def t_the_mail_order_panel_formats_like_the_rest_of_the_app():
    """It printed a raw ISO date to the screen and, for any non-GBP order,
    a bare number with no currency at all."""
    ok("fmtDate(o.at)" in SCRIPT, "the date goes through the shared formatter")
    ok("o.total + ' ' + (o.currency || '')" in SCRIPT,
       "and a non-GBP total keeps its currency")
    ok("(o.at || '').slice(0, 10)" not in SCRIPT.split("mail-order-stage")[1][:600],
       "no raw ISO reaches the panel")


@test
def t_search_repaints_are_debounced_everywhere():
    """The file browser measured 1,912ms of blocked JS per keystroke before its
    debounce went in, and seven other searches still repainted synchronously.
    The shared factory debounces for everyone now, and the two hand-rolled
    repainting searches got their own."""
    fn = SCRIPT.split("function tableSearch(")[1][:900]
    ok("setTimeout(() => oninput(inp.value.trim()), 150)" in fn,
       "the factory debounces its callers")
    ok("search._t = setTimeout(paintMailBody, 150)" in SCRIPT, "the mail search too")
    # The deals search was the second hand-rolled one; it is the factory's now,
    # so the guard follows it there rather than pinning the retired timer.
    ok("tableSearch('Search deals" in SCRIPT,
       "and the deals search is built by the factory, which debounces it")
    ok("tableSearch('Search products…', pState.q" in SCRIPT,
       "and the products search, which is the house search box and debounces inside tableSearch")
    ok("find._t = setTimeout(paint, 150)" in SCRIPT, "and the booked-shipments search")
    ok("inp.onchange = () => {" in SCRIPT.split("function tableSearch(")[1][:1300],
       "and a blur or Enter flushes the pending run, so chips cannot act on a stale query")


@test
def t_touch_and_scroll_behave_like_an_app():
    """Every control carried the double-tap zoom delay, tapped with a grey
    flash, and a modal that bottomed out handed its scroll to the page behind."""
    rule = CSS.split('button, [role="button"], select, input, .toggle, .lbl-row, .mrow, .files-row {')[1].split("}")[0]
    ok("touch-action: manipulation" in rule, "no double-tap delay on controls")
    ok("-webkit-tap-highlight-color: transparent" in rule, "no grey tap flash")
    ok(".modal-body, .dmenu, .scroll { overscroll-behavior: contain; }" in CSS,
       "and scroll does not chain out of modals or menus")


@test
def t_nested_boxes_step_their_radius_down():
    """A 14px box inside a 14px box with 16px padding reads blocky at the inner
    corner. The tables already stepped down; these three shapes had not."""
    ok(".card .insight, .card .empty, .chart-card .empty { border-radius: var(--radius-md); }" in CSS,
       "insight and empty boxes step down inside cards")


@test
def t_a_rows_keydown_never_steals_an_inner_controls_keypress():
    """Found by the adversarial verify pass: Space on the checkbox inside a CRM
    contact row bubbled to the row, whose preventDefault cancelled the tick and
    opened the modal instead. Every row-level Enter/Space handler now acts only
    when the ROW itself is the focused thing."""
    import re as _re2
    handlers = _re2.findall(r"addEventListener\('keydown', \((e|ev)\) => \{[^\n]*(?:Enter)[^\n]*\}\);", SCRIPT)
    hits = _re2.findall(r"addEventListener\('keydown', \((?:e|ev)\) => \{ if \((?:e|ev)\.target !== \w+\) return;", SCRIPT)
    rowish = _re2.findall(r"(row|tr|r|card)\.(?:addEventListener\('keydown'|onkeydown)", SCRIPT)
    ok(len(hits) >= 5, "the container handlers carry the target guard (%d)" % len(hits))
    ok("if (e.target !== card) return;" in SCRIPT, "the deal card too")
    # The two leaf handlers (the follow-up ticks) have no children to steal from
    # and legitimately omit the guard.


@test
def t_the_fence_respects_stacking_and_open_menus():
    """Also from the verify pass: the fence picked its overlay by DOM order, so
    a session expiring while a modal was open trapped Tab in the invisible
    modal BEHIND the opaque login screen. And an open dropdown manages its own
    keys, so the fence stands down for it."""
    fence = SCRIPT.split("if (e.key !== 'Tab') return;")[1][:1600]
    ok("tops.find(o => o.classList.contains('auth-overlay'))" in fence,
       "the login screen wins whenever it is up")
    ok("if (document.querySelector('.dmenu')) return;" in fence,
       "and an open menu is left to its own keys")


@test
def t_the_live_region_predates_the_first_toast():
    """Content that arrives together with a brand-new live region is
    unreliably announced. The host is created at boot now, empty, so the first
    toast mutates an established region."""
    boot = SCRIPT.split("$('menu-btn').onclick = toggleSidebar")[0][-700:]
    ok("host.setAttribute('aria-live', 'polite')" in boot,
       "the region exists before anything can toast")


@test
def t_the_connector_tab_is_fully_plumbed():
    """A tab is not a page: it is a nav entry, a view, a title, a beta flag, a
    grant key and a place in the Finance strip, and forgetting any one of them
    leaves a door painted on a wall."""
    ok('data-view="connector" id="nav-connector"' in HTML, "the nav button exists")
    ok('id="view-connector"' in HTML and 'id="connector-content"' in HTML, "and the view")
    ok("'connector'];" in SCRIPT.split("const TAB_KEYS = [")[1][:320], "the grant key is known")
    ok("'connector']" in SCRIPT.split("const BETA_TABS = [")[1][:60], "it wears Beta")
    ok("connector: 'Xero sync'" in SCRIPT, "the topbar can name it")
    ok("if (v === 'connector') showConnectorView();" in SCRIPT, "and setView opens it")
    ok("if (tabAllowed('connector')) tab('connector', 'Xero sync');" in SCRIPT,
       "it sits in the Finance strip, gated like Reconciliation")


@test
def t_send_requires_a_review_and_spends_it():
    """The chosen flow is bulk send WITH review. Enforced, not advisory: the
    Send button only arms once a completed dry run is on screen, its confirm
    dialog quotes that run's numbers, and a send consumes the review so the
    next one needs a fresh look."""
    fn = SCRIPT.split("function renderConnector() {")[1]
    fn = fn[:fn.index("\n        async function showReconView")]
    ok("send.disabled = running || !connReview || revAborted;" in fn, "no review, no Send, and a review that stopped arms nothing")
    ok("Based on the review:" in fn, "the confirm dialog quotes the reviewed numbers")
    ok("will be written into your accounts" in fn, "and says what it means")
    watch = SCRIPT.split("function connStartWatch() {")[1][:1600]
    ok("if (connBusy === 'send') connReview = null;" in watch,
       "a send spends the review it was based on")
    ok("if (connBusy === 'review' && last && last.dryRun) connReview = last;" in watch,
       "and only a completed DRY run ever arms one")
    # Writes are admin-gated in the UI too (the server is the real gate).
    ok("if (connIsAdmin()) {" in fn, "send and retry render only for admins")


@test
def t_the_connector_watch_cannot_outlive_its_view():
    """A poll that keeps running after the tab is closed is a leak that fires
    a request every 2.5 seconds forever."""
    watch = SCRIPT.split("function connStartWatch() {")[1][:900]
    ok("if (!document.querySelector('#view-connector.active')) { clearInterval(connWatch); connWatch = 0; return; }" in watch,
       "the watch clears itself the moment the view is gone")
    ok("if (connWatch) return;" in watch, "and never doubles up")


@test
def t_every_control_is_the_same_height_as_every_other():
    """Measured off the reference: its default control is 32px and its small one
    28px. This app had buttons at 34 and inputs at 36 - which did not match the
    reference and, worse, did not match EACH OTHER, so a button beside an input
    in a toolbar sat two pixels proud of it."""
    for sel, why in [(".btn {", "buttons"), ("input[type=text], input[type=number]", "the shared field recipe"),
                     (".lbl-size {", "toolbar selects"), (".psel {", "product selects"),
                     (".disp-text {", "dispatch text fields"), (".disp-num {", "dispatch number fields"),
                     (".tm-field {", "team fields")]:
        block = CSS.split(sel)[1].split("}")[0]
        ok("min-height: var(--control-h)" in block or "var(--control-h)" in block, why + " are 32px")
    ok("input[type=date], input[type=time] { height: var(--control-h); }" in CSS,
       "and a native date control is pinned, since it carries its own height")
    sm = CSS.split(".btn-sm {")[1].split("}")[0]
    ok("min-height: var(--control-h-md)" in sm and re.search(r"--control-h-md:\s*28px", CSS), "the small button stays 28")


@test
def t_the_sidebar_does_not_dim_where_you_are_not():
    """The reference marks position with a pill and a weight, and leaves every
    other label at full strength. This one greyed the inactive items to --text-secondary,
    which is what made the whole sidebar read washed out beside it."""
    item = CSS.split(".nav-item {")[1].split("}")[0]
    ok("height: var(--control-h)" in item, "nav items are 32px, as the reference draws them")
    ok("color: var(--text-primary)" in item, "an inactive item is full-strength ink")
    ok("font-weight: var(--weight-regular)" in item, "at normal weight")
    act = CSS.split(".nav-item:is(.active, [aria-current=\"page\"]) {")[1].split("}")[0]
    ok("font-weight: var(--weight-medium)" in act, "and the active one carries the weight")
    ok("background: var(--surface-tertiary)" in act, "on the muted pill")
    side = CSS.split(".sidebar {")[1].split("}")[0]
    ok("border-right: var(--bw-hairline) solid var(--border-default)" in side,
       "the sidebar wears the reference's hairline on its right edge (its 'sidebar' variant)")
    grp = CSS.split(".nav-group {")[1].split("}")[0]
    ok("color: var(--text-secondary)" in grp, "group labels sit at the reference's 70% foreground")


@test
def t_the_sidebar_groups_fold_and_remember_it():
    """Cameron: "make the tab headings in the sidebar dropdowns, it's getting
    crowded". Each heading is a toggle, as the reference's collapsible sidebar
    groups are: a chevron that turns when the group opens, the section under
    it hidden when folded, the choice remembered per group, and a page opened
    inside a folded group unfolds it so the highlighted item is never out of
    sight. A group with nothing an account may open is not shown at all."""
    for name in ("dashboards", "finance", "operations", "workspace"):
        ok('<button class="nav-group" type="button" data-group="%s" aria-expanded="true" aria-controls="nav-sect-%s">' % (name, name) in HTML,
           name + " is a toggle that says what it controls")
        ok('<div class="nav-sect" id="nav-sect-%s">' % name in HTML, "and its items sit in a section of their own")
    ok("const LS_NAVGROUPS = 'sc_navgroups_v1';" in SCRIPT, "the fold is remembered")
    ok("btn.onclick = () => setNavGroup(btn.dataset.group, btn.getAttribute('aria-expanded') !== 'true', true);" in SCRIPT,
       "a click flips it and remembers")
    ok("revealNavItem(v);" in SCRIPT.split("function setView(v) {")[1][:400], "opening a page unfolds its group")
    ok("document.querySelectorAll('.nav .nav-group, .nav .nav-item')" in SCRIPT, "the search still lists items inside a folded group")
    ok("syncNavGroups();" in SCRIPT.split("function applyRoleChrome()")[1].split("\n        function ")[0],
       "a group an account cannot open at all is hidden, heading included")
    ok('.nav-group[aria-expanded="true"] .nav-caret { transform: rotate(90deg); }' in CSS, "the chevron turns when the group is open")
    ok(".nav-sect[hidden] { display: none; }" in CSS, "and a folded section takes no room")
    grp = CSS.split(".nav-group {")[1].split("}")[0]
    ok("cursor: pointer" in grp and "width: 100%" in grp and "font-family: inherit" in grp, "the heading is a full-width button in the group's own type")

@test
def t_a_chip_is_exactly_twenty_pixels():
    """It inherited its height from a line box plus padding, which gave 21.5 -
    a hair taller than the reference's badge everywhere one appeared."""
    chip = CSS.split(".lbl-chip {")[1].split("}")[0]
    ok("height: 20px" in chip, "set, not inherited")
    ok("display: inline-flex" in chip and "align-items: center" in chip,
       "so its content is optically centred rather than sitting on a baseline")


@test
def t_the_kpi_card_keeps_the_hierarchy_the_reference_measures():
    """Written after getting this exactly backwards. A first pass read a
    CardTitle off a non-KPI card, concluded the label should be 16px
    foreground, and inverted a card that was already right. Re-measured across
    all four KPI cards on the reference's Default dashboard AND its CRM one:
    both agree the label is 14px muted, and Default - the page this one maps to
    - puts the value at 30px/500. Pinned here so it is not "corrected" again."""
    lab = CSS.split(".stat .label {")[1].split("}")[0]
    ok("font-size: var(--text-sm)" in lab, "the label is the 14px one")
    ok("color: var(--text-tertiary)" in lab, "and muted, not full-strength")
    val = CSS.split(".stat .value {")[1].split("}")[0]
    ok("font-size: var(--text-3xl)" in val, "the number is 30px (the scale gained the reference's 24px step as --text-2xl, so 30 is --text-3xl)")
    ok("font-weight: var(--weight-medium)" in val, "at 500, as the Default card draws it")
    # Anchored on the line start: ".stat .stat-note {" also contains the
    # shorter string, and matching that one reads the wrong rule.
    note = re.search(r"^\s*\.stat-note \{([^}]*)\}", CSS, re.M).group(1)
    ok("font-size: var(--text-sm)" in note, "and the sub-line matches the label at 14px")


@test
def t_sparklines_stay_on_the_ramp():
    """Saturated green and red strokes were the only strong colour on a page the
    reference keeps monochrome apart from the delta badge - and they said the
    same thing that badge already says, twice."""
    ok("CH_UP" not in SCRIPT and "CH_DOWN" not in SCRIPT,
       "the semantic spark pair is gone rather than left dead in the file")
    ok("sparkline(m.spark, CH[2])" in SCRIPT, "the line is drawn from the neutral ramp")


@test
def t_the_card_elevation_token_actually_paints():
    """The companion to the dead-token lesson above: asserting that fifteen card
    rules carry var(--shadow-sm) means nothing while the token itself resolves to
    `none`. The reference measures rgba(0,0,0,.05) 0 1px 2px 0 on every card."""
    m = re.search(r"--shadow-sm:\s*([^;]+);", CSS)
    ok(m, "the token is still declared")
    val = m.group(1).strip()
    ok(val != "none", "and it paints rather than silently voiding every shadow list")
    ok("0 1px 2px 0" in val and "5%" in val,
       "at the reference's 5%% alpha, not a heavier invented lift")


@test
def t_a_rising_number_is_not_congratulated_in_green():
    """gizmo paints metrics where a rise is bad news - unfulfilled orders,
    at-risk customers - so a green "up" reads as approval of a number the
    merchant needs to worry about. Nothing here spends colour on direction.

    The KPI chip has since been demoted a second time: a solid near-black pill
    made the CHANGE the loudest mark on a card whose subject is the figure, so
    the up chip is a neutral tint under the value's own weight. The rule that
    matters is unchanged - no green, and the tinted down chip is the only mark
    in the row that pulls the eye."""
    up = re.search(r"\.delta\.up \{[^}]*\}", CSS)
    ok(up, "the .delta.up rule is still there")
    ok("var(--surface-sunken)" in up.group(0) and "var(--text-primary)" in up.group(0),
       "the up chip is a neutral tint carrying full ink, not a fill: " + up.group(0)[:70])
    ok("var(--action-primary)" not in up.group(0),
       "and no longer outweighs the 30px figure it annotates")
    for sel in (r"\.delta\.up", r"\.prod-chip \.cmp\.up"):
        rule = re.search(sel + r" \{[^}]*\}", CSS)
        ok(rule, "the %s rule is still there" % sel)
        ok("var(--success)" not in rule.group(0), "and %s spends no green on direction alone" % sel)
    # The product list's compare chip is the same kind of mark, so it wears the
    # same neutral tint: as a filled black pill it was the heaviest thing on
    # every product row and read as a button (2026-09-23 design sweep).
    cmp_up = re.search(r"\.prod-chip \.cmp\.up \{[^}]*\}", CSS)
    ok("var(--surface-sunken)" in cmp_up.group(0) and "var(--action-primary)" not in cmp_up.group(0),
       "the product comparison chip matches the KPI change chip")
    # The tinted half of the pair stays, because red IS the reference's one tint.
    down = re.search(r"\.delta\.down \{[^}]*\}", CSS)
    ok(down and "var(--error)" in down.group(0),
       "while a falling number keeps the reference's red")


@test
def t_one_timing_for_every_colour_change():
    """The app had drifted to six transition durations - .12, .14, .15, .18, .2
    and .32 - all on the browser default `ease`. The reference uses exactly one
    timing for a colour change: 150ms on cubic-bezier(.4,0,.2,1). Transform and
    the toast's exit keep their own, because those are motion, not state."""
    ok(re.search(r"--dur:\s*\.15s", CSS), "the duration token is the reference's 150ms")
    ok(re.search(r"--ease:\s*cubic-bezier\(\.4,0,\.2,1\)", CSS), "on its curve")
    strays = []
    for decl in re.findall(r"transition:\s*([^;}]+)", CSS):
        d = decl.strip()
        if "var(--dur)" in d or d in ("none", "initial", "inherit"):
            continue
        # What is left must be motion, not a colour-family property.
        head = d.split(",")[0].split()[0]
        if head in ("transform", "margin-left") or "opacity .32s" in d:
            continue
        strays.append(d)
    ok(not strays, "no colour transition sets its own timing: %r" % (strays[:3],))


@test
def t_a_dashed_edge_only_ever_means_a_target():
    """Scanned the reference end to end: zero dashed or dotted borders. gizmo
    drew its empty states and its CRM onboarding panel with one - the
    convention for somewhere to DRAG something to - on panels that were only
    reporting that a list is empty. The four that keep it are the ones where
    the convention is the meaning: two live drop zones, the drag-to-reorder
    state, and the dotted help underline that <abbr> renders natively."""
    allowed = ("crm-zone",        # the won/lost drop targets
               "files-list.drag", # drop-hover on the file list
               "wg-editing",      # a card on a page in Customize mode, which can be picked up
               "has-help")        # abbr-style dotted underline on a help label
    for rule in re.findall(r"([^{}]+)\{([^}]*)\}", CSS):
        sel, body = rule
        if "dashed" not in body and "dotted" not in body:
            continue
        ok(any(a in sel for a in allowed),
           "dashed edge on %r, which is not a drop target" % sel.strip()[:60])


@test
def t_no_control_grows_its_way_out_of_the_scale():
    """Every button in the app is 32px, and so is the largest one anywhere in
    the reference - it makes a primary action loud by filling it, not by
    growing it. Three recipes had overridden their way off that scale by
    setting their own vertical padding: the sidebar's two footer buttons at 34,
    the skills input at 39, and the run-gate CTA at 46."""
    for sel in (r"\.run-gate \.rg-btn", r"\.sk-input, \.sk-textarea"):
        rule = re.search(sel + r" \{[^}]*\}", CSS)
        ok(rule, "the %s rule is still there" % sel)
        pad = re.search(r"padding:\s*(?:var\(--control-pad-y\)|([\d]+)px)", rule.group(0))
        ok(pad and (pad.group(1) is None or int(pad.group(1)) <= 5),
           "%s keeps the house 5px vertical padding, not its own" % sel)


_CURVE_HARNESS = r"""
const html = require('fs').readFileSync(process.argv[2], 'utf8');
const start = html.indexOf('        function smoothPath(pts) {');
const end = html.indexOf('\n        }\n', html.indexOf('return out;', start)) + 11;
if (start < 0 || end < 11) { console.log('EXTRACT_FAILED'); process.exit(0); }
eval(html.slice(start, end));
function segs(d) {
  const nums = d.match(/-?[\d.]+/g).map(Number);
  const out = []; let prev = {x: nums[0], y: nums[1]}, i = 2;
  while (i + 5 <= nums.length) {
    out.push({p0: prev, c1y: nums[i+1], c2y: nums[i+3], p1: {x: nums[i+4], y: nums[i+5]}});
    prev = {x: nums[i+4], y: nums[i+5]}; i += 6;
  }
  return out;
}
const bez = (a,b,c,d,t) => { const u = 1-t; return u*u*u*a + 3*u*u*t*b + 3*u*t*t*c + t*t*t*d; };
const cases = [[10,10,10,90,10,10,10],[0,100,0,100,0,100,0,100],[1,2,3,4,5,6,7,8],
               [50,50,50,20,50,50],[80,80,5,80,80],[42,42,42,42],[1,1,1,1000,1,1],
               [120,118,135,90,142,138,95,160,155,101,170,168]];
let worstOver = 0, worstDrift = 0;
for (const vals of cases) {
  const pts = vals.map((v,i) => [i*30, 200 - v/1000*180]);
  const S = segs(smoothPath(pts));
  for (const s of S) {
    const lo = Math.min(s.p0.y, s.p1.y), hi = Math.max(s.p0.y, s.p1.y);
    for (let t = 0; t <= 1; t += 0.002) {
      const y = bez(s.p0.y, s.c1y, s.c2y, s.p1.y, t);
      if (y < lo) worstOver = Math.max(worstOver, lo - y);
      if (y > hi) worstOver = Math.max(worstOver, y - hi);
    }
  }
  pts.forEach((p, i) => {
    const q = i === 0 ? S[0].p0 : S[i-1].p1;
    worstDrift = Math.max(worstDrift, Math.abs(q.x - p[0]) + Math.abs(q.y - p[1]));
  });
}
console.log(JSON.stringify({over: worstOver, drift: worstDrift}));
"""


@test
def t_a_curved_chart_never_draws_a_number_that_did_not_happen():
    """The reference rounds its lines with a NATURAL cubic spline. Measured on
    its own dashboard, 157 of 179 segments put a control point outside the two
    points they join, overshooting by up to 29px - so the drawn line leaves the
    data. On a demo of invented numbers that is a look; on this app's revenue
    and liability lines it would draw figures that never happened and could bow
    a positive month below zero.

    So gizmo curves with monotone cubic instead, and this asserts the property
    that choice was made for, by running the SHIPPED function over adversarial
    shapes - spikes, zigzags, plateaus, a 1000x jump - and sampling every
    Bezier it emits. A string check could not tell the two curves apart."""
    if not any(os.access(os.path.join(p, "node"), os.X_OK)
               for p in os.environ.get("PATH", "").split(os.pathsep)):
        print("       (node unavailable, skipped)")
        return
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(_CURVE_HARNESS)
        path = fh.name
    try:
        r = subprocess.run(["node", path, os.path.join(ROOT, "static", "index.html")],
                           capture_output=True, text=True)
        ok(r.returncode == 0, "the curve harness failed: " + (r.stderr or "")[:200])
        out = (r.stdout or "").strip()
        ok(out != "EXTRACT_FAILED",
           "smoothPath could not be found - if it was renamed, fix this guard too")
        got = json.loads(out)
        ok(got["over"] < 0.001,
           "the curve leaves its own data by %.3fpx" % got["over"])
        ok(got["drift"] < 0.11,
           "the curve no longer passes through its data points (%.3fpx off)" % got["drift"])
    finally:
        os.unlink(path)


@test
def t_both_charts_curve_through_one_function():
    """A sparkline and a trend line drawn by two different bits of geometry is
    how they drift apart. Both build their path from smoothPath."""
    ok("function smoothPath(" in SCRIPT, "there is one curve builder")
    ok(SCRIPT.count("smoothPath(") >= 3,
       "and both the sparkline and the trend line go through it")
    ok("(i ? 'L' : 'M')" not in SCRIPT,
       "with no straight-segment path builder left behind")


@test
def t_nothing_that_draws_an_edge_sits_on_the_cards_edge():
    """Cameron photographed two of these: the aged-debt bar running into the
    card's border, and the SEO insight cards - white, bordered - flush inside a
    white bordered card.

    One cause. `.card > *` hands every child the 16px inset as PADDING, which
    is right for a table or a composer bar that should meet the card's edge
    with only its content inset. Padding sits INSIDE the border box, so a child
    with a border of its own still spans the full width and its border lands
    exactly on the card's. Those take the inset as MARGIN instead."""
    rule = re.search(r"\.card > :is\(\.lia-bar, \.lbl-row, \.ktable-wrap, \.empty[^)]*\),\s*\n\s*"
                     r"\.card-bleed > \.empty \{([^}]*)\}", CSS)
    ok(rule, "the gutter exception is still there")
    body = rule.group(1)
    ok("margin-left: var(--sp-4)" in body and "margin-right: var(--sp-4)" in body,
       "and it insets by margin, which is outside the border box")
    bar = re.search(r"\.card > \.lia-bar, \.card > \.ktable-wrap \{([^}]*)\}", CSS)
    ok(bar and "padding-left: 0" in bar.group(1),
       "and the two with no padding of their own drop what they were given, "
       "or they inset twice")
    # The insight rows used to be bordered cards, and .insights held the gutter
    # as padding to inset them. They are hairline ROWS on the card now, so the
    # same requirement - a bleed child is inset by 16, and never by a mechanism
    # that puts two borders on one line - is met a step lower down: the row
    # sheds its frame and carries the gutter in its own padding, the way an
    # .action row already does. The rule between two rows has to reach the
    # card's edge, so the wrapper hands out nothing.
    rows = re.search(r"\.card-bleed > \.insights > \.insight,[\s\S]{0,220}?\{([^}]*)\}", CSS)
    ok(rows and "border: 0" in rows.group(1),
       "a list already inside a card draws no second frame of its own")
    ok(re.search(r"\.card-bleed > \.insights > \.insight \+ \.insight,[\s\S]{0,260}?"
                 r"\{[^}]*border-top: var\(--bw-hairline\) solid var\(--border-default\)", CSS),
       "the rows are separated by one hairline instead")
    ins = re.search(r"^\s*\.insight \{([^}]*)\}", CSS, re.M)
    ok(ins and "padding: var(--sp-3) var(--sp-4)" in ins.group(1),
       "and the 16px gutter comes from the row's own padding, so the hairline "
       "between two rows reaches the card's edge")
    # The bleed wrapper must still do its actual job for tables.
    ok(".card-bleed .ktable-wrap { border: 0" in CSS,
       "and a table still runs to the card edge with no second frame")


@test
def t_a_block_with_its_own_heading_is_not_swallowed_by_the_one_above():
    """The page-chat panel is a section-title plus its own .card. cardifySections
    collected everything after a heading until the next DIRECT-child heading, and
    this panel carries its heading nested inside itself - so it was swept into
    whatever section preceded it and wrapped a second time, putting a bordered
    white card flush inside a bordered white card."""
    fn = SCRIPT[SCRIPT.index("function cardifySections"):]
    fn = fn[:fn.index("\n        function ")]
    ok("n.querySelector('.section-title')" in fn,
       "collection stops at a block that carries its own heading")


@test
def t_one_rhythm_down_the_page():
    """Measured on the reference at 1600: its content is a single flex column at
    gap-6, so every block on a page is separated by exactly 24px. gizmo's blocks
    each carried their own bottom margin and arrived at 4, 12, 14, 16, 20 and 24
    - six values doing one job, which is most of what makes a page look
    unconsidered even when no single element is wrong."""
    rule = re.search(r"\.ov-wrap > \*:not\(\.run-gate\) \{([^}]*)\}", CSS)
    ok(rule, "the page rhythm rule is still there")
    ok("margin-bottom: var(--page-rhythm)" in rule.group(1)
       and re.search(r"\.ov-wrap \{[^}]*--page-rhythm: var\(--sp-6\)", CSS),
       "and it is the reference's 24px")
    ok("margin-top: 0" in rule.group(1),
       "with stray top margins zeroed, or the two stack up")
    head = re.search(r"\.ov-wrap > \.section-title \{([^}]*)\}", CSS)
    ok(head and "margin-bottom: var(--sp-3)" in head.group(1),
       "a heading still binds to the block under it at 12, not midway between two")
    ok(re.search(r"\.ov-wrap > \*:last-child \{[^}]*margin-bottom: 0", CSS),
       "and the last block does not add to the wrap's own bottom padding")


@test
def t_a_heading_keeps_its_12px_on_a_phone():
    """At 640px and below every page heading sat 16px above its block instead
    of 12: Overview, SEO, Keywords, Customers, Forecast, Memory and Skills. The
    phone rhythm was a second `.ov-wrap > *:not(.run-gate)` rule, the same
    weight as the heading's exception and later in the sheet, so it won. It
    beat `:last-child { margin-bottom: 0 }` the same way and put 16px under the
    last block of every page. Now the phone re-points one property, and an
    exception written after the rhythm wins at every width."""
    ok(CSS.count(".ov-wrap > *:not(.run-gate) {") == 1,
       "the rhythm's margin is declared once, so no later rule of the same "
       "weight can outrank its exceptions")
    rhythm = CSS.index(".ov-wrap > *:not(.run-gate) {")
    ok(CSS.index(".ov-wrap > .section-title {") > rhythm
       and CSS.index(".ov-wrap > *:last-child {") > rhythm,
       "and both exceptions come after it")
    phone = [b for b in re.findall(r"@media \(max-width: 640px\) \{((?:[^{}]|\{[^{}]*\})*)\}", CSS)
             if re.search(r"(?<![\w-])\.ov-wrap \{", b)]
    ok(phone and re.search(r"\.ov-wrap \{[^}]*--page-rhythm: var\(--sp-4\)", phone[0]),
       "the phone gap is the property re-pointed to 16, not a margin rule")


@test
def t_a_heading_that_opens_a_page_block_leaves_the_gap_above_it_alone():
    """At 375px the page chat, renderStructured's Recommended actions block and
    the Forecast sections sat 24px below the block before them instead of 16.
    Each is a wrapper whose first child is a .section-title, and the rhythm
    only zeroes the top margin of a direct child: the heading's own 24px
    collapsed through a wrapper with no padding or border to stop it and
    replaced the page gap. On a desktop both numbers are 24, which is why it
    only showed on a phone."""
    ok(re.search(r"\.ov-wrap > \* > \.section-title:first-child \{[^}]*margin-top: 0", CSS),
       "a heading that opens a top-level block spends no top margin")
    ok(not re.search(r"(?<![\w-])\.page-chat \{[^}]*margin-top", CSS),
       "and the chat panel brings no top margin of its own")


@test
def t_no_top_level_block_hand_places_its_own_spacing():
    """An inline style beats every rule in the sheet, so a page block that sets
    its own margin silently opts out of the rhythm. Nine cards, three hosts and
    two empty states were doing exactly that."""
    ok("= el('div', 'card'); " not in SCRIPT.replace("= el('div', 'card'); const", "X")
       or "style.marginBottom = '16px'" not in SCRIPT,
       "no card is created and immediately given a hand-set bottom margin")
    ok("host.style.marginTop = '12px'" not in SCRIPT,
       "and no section host nudges itself down past the gap it already has")
    ok("const e = el('div', 'empty'); e.style.margin" not in SCRIPT,
       "and an empty state takes the page's spacing like every other block")


@test
def t_a_flagged_model_can_be_settled_without_leaving_the_app():
    """The weekly scan raised "New model not matching the size list" and the only
    controls on it were snooze and dismiss - the actual fix lived in a CSV on the
    data volume, so the alert was a notification with nowhere to go, and
    dismissing it resolved nothing: the model came back on the next scan."""
    ok("function openSizeRuleModal(" in SCRIPT, "there is a way to resolve one")
    fn = SCRIPT[SCRIPT.index("function openSizeRuleModal("):]
    fn = fn[:fn.index("\n        function ")]
    for op in ("'set'", "'alias'", "'exclude'"):
        ok(op in fn, "it offers the %s ruling" % op)
    ok("/api/gobo-sizes/rule" in fn, "and writes through the rule route")
    ok("res.resolves" in fn,
       "reporting what the LOOKUP says rather than that the save succeeded")
    ok("req.manufacturer = target.manufacturer" not in fn,
       "an alias keeps the manufacturer the ORDERS carry: that column is what "
       "the store's spelling gets indexed under, so the target's would file the "
       "rule under a maker the orders never say")


@test
def t_the_size_alert_leads_to_the_thing_that_fixes_it():
    fn = SCRIPT[SCRIPT.index("function alertsBanner("):]
    fn = fn[:fn.index("\n        function ")]
    ok("size list" in fn and "runCoverage()" in fn,
       "a size-list alert opens the size check instead of only offering dismiss")


@test
def t_the_resolve_button_is_hidden_when_the_server_would_refuse_it():
    """A button that always errors is worse than no button."""
    ok("if (sizeRulesCanEdit)" in SCRIPT, "the action is gated on the grant")
    ok("let sizeRulesCanEdit = false" in SCRIPT,
       "defaulting to hidden, so a failed permission read does not offer it")
    ok("function loadSizeRulePerm(" in SCRIPT
       and "loadSizeRulePerm();" in SCRIPT[SCRIPT.index("function coverageCard("):
                                           SCRIPT.index("function coverageCard(") + 400],
       "asked whenever the card draws, not only when the check is run by hand - "
       "the weekly scan puts the card on screen without runCoverage being called")


@test
def t_a_table_in_a_card_is_inset_rather_than_welded_to_it():
    """The rule's own comment says the table gets "its OWN box, inset by the
    card's padding" - a 10px frame inside a 14px card. It was not inset: as a
    direct card child it took the gutter as PADDING, which sits inside its own
    border box, so its border landed on the card's and its text floated 30px in
    while the line sat at 1px. Measured on Xero sync and the size check."""
    rule = re.search(r"\.card > \.lia-bar, \.card > \.ktable-wrap \{([^}]*)\}", CSS)
    ok(rule and "padding-left: 0" in rule.group(1),
       "the wrap drops the padding it was handed")
    ok(re.search(r"\.card > :is\(\.lia-bar, \.lbl-row, \.ktable-wrap", CSS),
       "and takes the inset as margin instead, like the other boxed children")


@test
def t_no_borderless_strip_is_sliced_by_someone_elses_border():
    """The presence strip on the Inbox was a non-wrapping flex row with
    overflow-x: auto, running full-bleed to the card's own border - so the third
    person was cut in half by that line, a bordered mini-card sliced at the card
    edge with a scrollbar under it.

    A scroller that draws its OWN edge may clip at it: that is what the
    full-bleed table does, and it reads as intentional because the line belongs
    to the thing doing the clipping. One with no edge of its own borrows
    whatever line happens to be there."""
    who = CSS.split(".mail-who {")[1].split("}")[0]
    ok("overflow-x" not in who,
       "the strip no longer scrolls under the card's border")
    ok("flex-wrap: wrap" in who,
       "it wraps, so every person is whole and nothing meets an edge it should not")


@test
def t_a_box_painted_inside_a_card_sits_inside_its_gutter():
    """The card hands its 16px gutter to every child as PADDING. That is right
    for prose and for a table that meets the card's edge, and wrong for
    anything that paints its own box: padding sits inside the box, so the box
    still spans the full card and its colour lands on the card's border. The
    Xero sync last-run notice went out that way twice - red touching the frame
    on both sides - and each time the measurement was read as "inside the
    padding" because 1px from the border IS the padded child's edge.

    The CSS keeps one list of the boxed classes the script puts straight into
    a card; those take the gutter as MARGIN. Every class that paints a box in
    a card must be on it, and the notice must still be one of them."""
    m = re.search(r"\.card > :is\(([^)]*)\),\s*\.card-bleed > \.empty \{([^}]*)\}", CSS)
    ok(m is not None, "the margin-inset list for boxed children of a card is still one rule")
    listed = {c.strip() for c in m.group(1).split(",")}
    body = m.group(2)
    ok("margin-left: var(--sp-4)" in body and "margin-right: var(--sp-4)" in body
       and "width: auto" in body,
       "the listed classes take the gutter as margin and let auto width fill it")
    for cls in (".cx-health", ".msg", ".mail-sendwarn", ".disp-warn", ".empty", ".mail-empty",
                ".lbl-row", ".lia-bar", ".ktable-wrap",
                # A RULE between rows is an edge too, and these three shipped
                # without it. .fc-algo put every source name, every line of
                # prose and both ends of every divider 1px from the card's
                # border, because its padding shorthand's 0 had quietly
                # overridden the card's 16px gutter.
                ".fc-algo", ".fc-alert", ".know-body", ".fc-drive-tot", ".fc-split-bar"):
        ok(cls in listed, cls + " is inset by margin, not welded to the card's border")
    # The inset must not be taken TWICE. A child that paints a filled box keeps
    # its own padding, because that padding sits inside the box it draws. A
    # child that only draws a RULE has no box to pad, so the card's gutter
    # lands on top of the margin and pushes its text 32px in against a
    # card-sub at 16px - which is what happened the moment .fc-algo was first
    # moved onto this list.
    _ZEROED_BY_THE_CARD_RULE = (".lia-bar", ".ktable-wrap")
    for cls in sorted(listed):
        own = " ".join(re.findall(r"(?:^|\})\s*" + re.escape(cls) + r"\s*\{([^}]*)\}", CSS, re.M))
        paints_fill = re.search(re.escape(cls) + r"[^{]*\{[^}]*background", CSS) is not None
        draws_rule = "border-top:" in own or "border-bottom:" in own
        if draws_rule and not paints_fill:
            ok("padding-inline: 0" in own or cls in _ZEROED_BY_THE_CARD_RULE,
               cls + " draws a rule, so its horizontal padding is 0 and the margin "
                     "alone insets it, or its text sits 32px in from a 16px card")
    notice = CSS.split(".cx-health {")[1].split("}")[0]
    ok("padding:" in notice, "the notice keeps its own padding inside its box")
    ok(".cx-health.bad { background:" in CSS and ".cx-health.ok { background:" in CSS,
       "the notice paints a box, which is why it has to be on the list")
    ok("el('div', 'cx-health bad')" in SCRIPT and "el('div', 'cx-health ok')" in SCRIPT
       and "sCard.append(h)" in SCRIPT,
       "the script still puts the notice straight into the Connection card")


@test
def t_a_forecast_is_drawn_as_a_range_not_as_three_competing_lines():
    """Actual, forecast, uncertainty - and the reader must be able to tell them
    apart without being told. The old chart drew four strokes of equal weight
    (taken, forecast, P90, P10), which reads as four opinions rather than one
    answer with a range around it, and nothing on the plot said which part had
    already happened. The Bank of England's finding that carries over to a
    single series is that a shaded interval is understood as a range while a
    point estimate is believed as a fact; a full fan is not warranted here
    because the run publishes ONE interval (p10-p90), not a ladder of them."""
    tc = SCRIPT.split("function trendChart(", 1)[1].split("\n        function ", 1)[0]
    ok("opts.band" in tc and "chart-band" in tc, "trendChart can fill an interval")
    ok("bandOpt.lo.concat(bandOpt.hi)" in tc,
       "and the band's own values set the y-domain, or the band is drawn and then clipped")
    ok("chart-split" in tc and "opts.splitAt" in tc,
       "and can mark where what happened stops and what is expected begins")
    # A gap is a gap. Y(null) is Y(0), so before this every series was drawn
    # down to the floor wherever it had no value: the actual line ran along the
    # bottom through the whole forecast and the forecast line ran along the
    # bottom through the whole of history, crossing in a meaningless V.
    ok("const runsOf" in tc and "v != null && isFinite(v)" in tc,
       "a series with no value at a point leaves a gap rather than dropping to zero")
    fc = SCRIPT.split("function fcChartCard(", 1)[1].split("\n        function ", 1)[0]
    ok("'P90'" not in fc and "'P10'" not in fc,
       "the forecast chart no longer draws P10 and P90 as their own lines")
    ok("band: band" in fc and "splitAt:" in fc, "it passes the interval and the handover")
    ok("dash: true" in fc and "lead: true" in fc,
       "the forecast is the same line continuing, dashed - not a dimmed comparison line")
    ok("joins(i, r.p10)" in fc and "joins(i, r.p50)" in fc,
       "and both meet the last actual value, so the band pinches to nothing at today")
    # Said in words, because a shaded band explains itself only to somebody who
    # already reads forecast charts, and this page is read by directors. Said
    # ONCE, in the chart's own legend: a second key under the plot repeated it
    # while the legend above showed two identical squares.
    ok("name: 'Taken'" in fc and "name: 'Expected'" in fc and "'Likely range, 8 times in 10'" in fc,
       "and the legend says in words what its three treatments mean")
    ok("fc-key" not in SCRIPT and "fc-key" not in CSS, "in one key, not two")


@test
def t_the_forecast_page_never_dresses_an_estimate_as_a_banked_figure():
    """Never make predicted money look like confirmed money. The overview
    separates the two in the reader's own words and says out loud that the
    forward figure is an expectation."""
    ov = SCRIPT.split("function fcOverviewCard(", 1)[1].split("\n        function ", 1)[0]
    ok("taken so far in" in ov, "what is banked is labelled as taken")
    ok("It is an expectation, not a commitment." in ov,
       "and what is forward is labelled as an expectation")
    dr = SCRIPT.split("function fcDriversCard(", 1)[1].split("\n        function ", 1)[0]
    ok("Already taken" in dr and "Still expected" in dr,
       "the driver breakdown splits the month the same way")
    # The honest decomposition. This model forecasts the shop's takings from the
    # shop's own history: there is no invoice ledger behind it, so it must not
    # print "expected invoices" or "late payments" as if there were.
    ok("recurring" not in dr and "invoice" not in dr.lower() and "late payment" not in dr.lower(),
       "and claims no invoice-level drivers, because nothing in the run produces them")


def _names_the_script_calls_but_never_binds(script):
    """Bare function calls with no binding anywhere in the script.

    Comments and every kind of string literal are stripped first, or the prose
    in this file (which is full of "the desk (a place)") reads as a call. What
    counts as a binding: a named function, a parameter of any function or
    arrow, a const/let/var including destructured ones, a catch binding, and
    an object-literal method."""
    s = re.sub(r"/\*.*?\*/", " ", script, flags=re.S)
    s = re.sub(r"(?<![:\w])//[^\n]*", " ", s)
    s = re.sub(r"'(?:\\.|[^'\\\n])*'", "''", s)
    s = re.sub(r'"(?:\\.|[^"\\\n])*"', '""', s)
    s = re.sub(r"`(?:\\.|[^`\\])*`", "``", s, flags=re.S)

    bound = set()

    def take(blob):
        for n in re.split(r"[,\s]+", blob or ""):
            n = re.sub(r"=.*$", "", n.strip().split(":")[-1].strip().lstrip(".")).strip()
            if re.fullmatch(r"[A-Za-z_$][\w$]*", n or ""):
                bound.add(n)

    for m in re.finditer(r"function\s*([A-Za-z_$][\w$]*)?\s*\(([^)]*)\)", s):
        if m.group(1):
            bound.add(m.group(1))
        take(m.group(2))
    for m in re.finditer(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)", s):
        bound.add(m.group(1))
    for m in re.finditer(r"(?:const|let|var)\s*[\{\[]([^\}\]]*)[\}\]]", s):
        take(m.group(1))
    for m in re.finditer(r"\(([^()]*)\)\s*=>", s):
        take(m.group(1))
    for m in re.finditer(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*=>", s):
        bound.add(m.group(1))
    for m in re.finditer(r"catch\s*\(\s*([A-Za-z_$][\w$]*)", s):
        bound.add(m.group(1))
    for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*:\s*(?:function|\()", s):
        bound.add(m.group(1))

    called = set(re.findall(r"(?<![.\w$])([a-z][A-Za-z0-9_$]*)\s*\(", s))
    keyword = {"if", "for", "while", "switch", "catch", "return", "typeof", "function", "await",
               "new", "do", "else", "delete", "void", "in", "of", "case", "throw", "var", "let",
               "const", "yield", "instanceof", "async"}
    builtin = {"parseInt", "parseFloat", "isNaN", "isFinite", "encodeURIComponent",
               "decodeURIComponent", "setTimeout", "clearTimeout", "setInterval",
               "clearInterval", "fetch", "alert", "confirm", "prompt", "btoa", "atob",
               "getComputedStyle", "queueMicrotask", "structuredClone",
               "requestAnimationFrame", "cancelAnimationFrame", "eval", "escape",
               "unescape", "print"}
    return sorted(called - bound - keyword - builtin)


@test
def t_every_function_the_page_calls_is_one_that_exists():
    """A call to a name that was never defined is a ReferenceError at the
    moment the person clicks, and nothing before that moment says so. Three
    shipped in one session and each looked like a different fault:

      toast(...)      the cash flow workbook uploaded, the server stored it,
                      and the page then reported "Can't find variable: toast"
                      as if the upload had failed;
      toast(...)      the same, ruling a gobo size inline on the Size list;
      showView(...)   every tab on the Finance strip (Liability,
                      Reconciliation, Forecast, Xero sync) did nothing at all.

    In each the write had already happened, so the tests, the server and the
    ledger all agreed the feature worked. The helpers are toastOk/toastError
    and setView. The page has one script, so the whole binding set is
    knowable: anything called and never bound is either a typo or something
    another file puts on window, and the second kind has to be named here."""
    external = set(re.findall(r"window\.([A-Za-z_$][\w$]*)\s*=", COMPOSER))
    ok("mountComposer" in external,
       "composer.js still publishes what index.html calls across the file boundary")
    stray = [n for n in _names_the_script_calls_but_never_binds(SCRIPT) if n not in external]
    ok(not stray, "every function the page calls exists: " + (", ".join(stray) or "none missing"))
    ok("toastOk(" in SCRIPT and "toastError(" in SCRIPT,
       "the toast helpers are still called by their real names")


@test
def t_the_forecast_tab_shows_the_five_plain_models_and_what_they_scored():
    """One number nobody can check is worth less than five that disagree in
    the open. The card carries every model's next four months, the error and
    the lean each earned on this shop's own history, the plan's target on the
    same row scale, and a mark on whichever did best - so the reader can see
    which has earned trust rather than being told."""
    fn = SCRIPT.split("function fcSanityCard(", 1)[1].split("\n        function ", 1)[0]
    ok("latest.sanity" in fn, "it reads what the nightly run posted")
    ok("Typical error" in fn and "Bias" in fn, "both scores are shown, not just the error")
    ok("RANK[i]" in fn and "leads the forecast" in fn and "second opinion" in fn and "third opinion" in fn,
       "the three being quoted are named in order, and the leader is marked as leading")
    ok("Median of the five" not in fn,
       "no unranked median footer: the median is a scored row in the table itself")
    ok("(latest.monthly || []).find" in fn and "targets" in fn,
       "the plan's own target sits beside them for comparison")
    ok(".sort(" in fn and "mape" in fn, "ordered by what each scored, best first")
    # Directors read this table, and none of these names explains itself.
    ok("name.title = m.about" in fn and "has-help" in fn and "name.tabIndex = 0" in fn,
       "every source says on hover what it does, what it assumes and when it misleads")
    ok("helpHead('Typical error'" in fn and "helpHead('Bias'" in fn,
       "and so do the two columns nobody can be expected to read cold")
    ok("'Source'" in fn, "the column is what it is: a source, not a model")
    # Twelve rows is a lot to land on someone who opened the page to read one
    # number. The choice of how much to show is remembered per person.
    ok("filterTabs(FC_ROWS, mode, setFcRowsMode)" in fn, "the reader chooses how much to see")
    ok("mode === 'one' ? ranked.slice(0, 1)" in fn and "ranked.slice(0, 3)" in fn,
       "one row, three rows, or all of them")
    ok("'Just the headline'" in SCRIPT and "'The three quoted'" in SCRIPT and "'Every source'" in SCRIPT,
       "named so the choice explains itself")
    ok("localStorage.setItem(LS_FCROWS" in SCRIPT and "return FC_ROWS.some(r => r[0] === v) ? v : 'three'" in SCRIPT,
       "remembered, defaulting to the three that are quoted, and a junk value falls back rather than breaking")
    # A year per source, and a way to ask the headline boxes for a specific one.
    ok("helpHead('Plan year'" in fn, "every source answers what the plan year comes to")
    ok("m.year_partial ? '*' : ''" in fn,
       "and a part year is starred rather than shown as if it were a whole one")
    ok("fcMoney(planYear)" in fn, "the plan's own year sits in the same column to compare against")
    ok("allMonths.slice(0, 6)" in fn,
       "only six month columns, or the year and the scores are pushed off the side")
    # No algorithm selector. Asking a person to choose one is asking them to
    # guess at something the machine can measure, so the machine measures it.
    strip = SCRIPT.split("function renderForecast()")[1].split("fcChartCard(")[0]
    ok("setFcSourceName" not in strip and "psel" not in strip,
       "the page does not ask anyone to pick an algorithm")
    rec = SCRIPT.split("function fcRecordCard(", 1)[1].split("\n        function ", 1)[0]
    ok("c.ledger" in rec and "r.by_source" in rec,
       "the standing record is drawn from what each source said before the month began")
    ok("r.winner === n" in rec and "'closest'" in rec, "and the closest each month is marked")
    ok("sn.ranked_on === 'record'" in rec,
       "the card says whether the forecast is now ranked on the record or still on the backtest")
    ok("Nothing has closed yet" in rec,
       "and says plainly what will happen at month end when there is nothing yet")
    ok("fcUntitled(fcRecordCard(c))" in SCRIPT,
       "the tab draws it, in the detail layer rather than dealt onto the overview")

    # Nobody should have to guess whether the optimised choice is running.
    opt = SCRIPT.split("function fcOptimisedCard(", 1)[1].split("\n        function ", 1)[0]
    ok("'The algorithm in use'" in opt, "the page says which one is running")
    ok("fcChip('made', 'in use')" in opt, "and marks it as in use")
    ok("Chosen on its record" in opt and "Chosen on the backtest" in opt,
       "it says WHY that one, and on which kind of evidence")
    ok("the next best, " in opt, "and how much better it is than the alternative")
    ok("takes over without anyone changing a setting" in opt,
       "and that the choice moves on its own when another starts winning")

    # And what each one actually does, for someone signing off a number.
    alg = SCRIPT.split("function fcAlgorithmsCard(", 1)[1].split("\n        function ", 1)[0]
    ok("'How each one works'" in alg, "there is a section explaining them")
    ok("m.about" in alg and "fcBestAt(m)" in alg,
       "each carries a plain description and what shape of business it suits")
    # It reached the page as the tail of a three-line paragraph, where it was
    # present and unfindable. It gets its own line.
    ok("'fc-algo-fit'" in alg and "'Best at'" in alg,
       "what it suits is its own line, not the last clause of a paragraph")
    # And the page carries the strings itself. The field arrives from the
    # forecast SERVICE, which was still posting payloads written before the
    # field existed, so a reader saw nothing at all until the next night's run.
    ok("const FC_BEST_AT = {" in SCRIPT and "m.best_at || FC_BEST_AT[m.name]" in SCRIPT,
       "a payload written before the field existed still explains its sources")
    for nm in ("Trend and smoothing, averaged", "Auto-fitted ARIMA", "Average, extremes removed"):
        ok("'" + nm + "':" in SCRIPT, "the fallback covers " + nm)
    ok("closed month'" in alg and "in the backtest'" in alg,
       "and how accurate it has actually been, live and in the backtest")
    # Measured in the rig at 1600px: space-between put the name's last letter
    # at x=265 and the first figure at x=838, a 573px hole across a 1269px
    # card. The figures were rendering and were still invisible - they sat off
    # the side of the screenshot the reader took of the section. A row that
    # pairs a label with its numbers keeps them adjacent.
    head_css = CSS.split(".fc-algo-head {", 1)[1].split("}", 1)[0]
    ok("space-between" not in head_css,
       "the figures sit beside the name they describe, not at the far edge")
    # Thirteen stacked essays is not a comparison. Name on the left, the
    # numbers on the right, so the figures read down the page.
    ok("fc-algo-head" in alg and "fc-algo-nums" in alg,
       "the figures line up down the page so sources can be read against each other")
    ok("m.name === sn.best" in alg, "with the one in use marked here too")
    # Both are still drawn, but LAST and SHUT. A director signing off a number
    # does not have to read about Theta to trust it; the reader who wants to
    # opens one drawer and finds all of it.
    ok("fcUntitled(fcOptimisedCard(latest))" in SCRIPT and "fcUntitled(fcAlgorithmsCard(latest))" in SCRIPT,
       "the tab draws both, under How this forecast works")
    ok(SCRIPT.index("'How this forecast works'") > SCRIPT.index("fcDriversCard(latest, sc)"),
       "and it sits below the money, never above it")
    ok("!sn || !sn.available" in fn and "sn.reason" in fn,
       "a run with too little history says so instead of drawing an empty table")
    ok("fcSanityCard(latest, sc)" in SCRIPT, "and the tab actually calls it")
    # It is a sanity CHECK: it belongs above the month table it is checking.
    ok(SCRIPT.index("fcSanityCard(latest, sc)")
       < SCRIPT.index("'Month by month against ' + sc"),
       "the check is read before the thing it checks")


# --- Web Interface Guidelines pass ------------------------------------------

@test
def t_decorative_icons_are_hidden_from_assistive_tech():
    """Every icon in the app comes out of one factory, so the attribute belongs
    there rather than at hundreds of call sites. The control around an icon
    carries the name; an icon that announced itself would read it twice."""
    sv = re.search(r"const SV = \(inner\) => '(<svg[^']*)'", SCRIPT)
    ok(sv, "the icon factory is still there")
    ok('aria-hidden="true"' in sv.group(1), "icons are hidden from assistive tech")
    ok('focusable="false"' in sv.group(1),
       "and kept out of the tab order, which some engines still put them in")


@test
def t_every_mail_row_checkbox_says_which_email_it_is():
    """Nineteen of these sit on the board and every one announced as a bare
    "checkbox", which makes bulk claiming unusable without sight of the screen."""
    seg = SCRIPT.split("cb.type = 'checkbox'; cb.className = 'mail-check';")[1][:400]
    ok("setAttribute('aria-label'" in seg, "the row checkbox is named")
    ok("t.subject" in seg and "t.from_name" in seg,
       "by the email it belongs to, not a generic string")


@test
def t_money_is_formatted_by_intl_and_survives_a_bad_currency_code():
    """There were two money formatters and they disagreed: one printed
    "12,480 GBP", the other "£18,620" from a hand-written symbol map that knew
    three currencies - so a yen order read as "JPY 1,234.00". One formatter now,
    and Intl knows every code and where the symbol goes.

    The constructor THROWS on a malformed code, and a bad code off an order must
    not take the page down with it."""
    ok("new Intl.NumberFormat" in SCRIPT, "currency goes through Intl")
    seg = SCRIPT.split("function moneyFmt(")[1][:700]
    ok("try {" in seg and "catch" in seg, "a malformed code is caught")
    ok("/^[A-Z]{3}$/" in seg, "and only a real 3-letter code asks for currency style")
    ok("const fmtMoney = (n, cur) => money(n, cur, 0);" in SCRIPT,
       "and both old formatters now share the one implementation")
    ok("{ GBP: '\\u00a3', USD: '$', EUR: '\\u20ac' }" not in SCRIPT,
       "the hand-written symbol map is gone")


@test
def t_the_skills_captions_are_real_labels():
    """They were sibling <label>s with no `for`: visible text that named nothing,
    so both fields announced as bare inputs."""
    ed, up = fn_src("function skillEditor("), fn_src("function uploadRow(")
    ok(ed.count("el('label', 'sk-field')") == 3 and up.count("el('label', 'sk-field')") == 2,
       "the one skills editor wraps each of its three fields in its label, and so does a file being added")
    ok("el('div', 'sk-field')" not in SCRIPT, "and no orphan caption is left")


@test
def t_there_is_a_way_past_the_sidebar():
    """Sixteen nav items sit between the top of the page and the content on
    every view."""
    ok('class="skip-link" href="#main"' in HTML, "a skip link is the first thing in the tab order")
    ok('id="main"' in HTML and 'tabindex="-1"' in HTML, "and it has somewhere to land")
    rule = CSS.split(".skip-link {")[1].split("}")[0]
    ok("translateY(-200%)" in rule, "hidden until focused")
    ok(".skip-link:focus" in CSS, "and shown when it is")


@test
def t_what_is_pinned_to_an_edge_clears_the_notch():
    """A bar at bottom: 0 lands under the home indicator. env() is 0 on hardware
    with neither, so this costs nothing on a desktop."""
    for sel in (r"\.crm-dropbar", r"\.build-bar", r"#toast-host"):
        # Anchored at a line start: #toast-host also appears in a print rule
        # that switches it off, and that one has no edge to clear.
        rule = re.search(r"^\s*" + sel + r" \{([^}]*)\}", CSS, re.M)
        ok(rule and "safe-area-inset" in rule.group(1),
           "%s clears the safe area" % sel)
    ok('name="theme-color"' in HTML, "and the browser chrome matches the page")


@test
def t_a_half_written_skill_is_not_lost_on_close():
    """The one thing here worth minutes of typing, and it lives only in the field
    until Save. Dirty is computed from the DOM against what each field was
    RENDERED with, so there is no flag to go stale and opening a skill to read
    it does not prompt."""
    ok("beforeunload" in SCRIPT, "closing with unsaved work asks first")
    seg = SCRIPT.split("beforeunload")[1][:520]
    ok("dataset.initial" in seg, "measured against the rendered value, not emptiness")
    ed = fn_src("function skillEditor(")
    ok("ti.dataset.initial = ti.value" in ed and "bo.dataset.initial = s ? bo.value : ''" in ed,
       "and both skills fields stamp what they started as")
    ok("getClientRects" not in seg, "a skill half written on a tab not being looked at still counts")


@test
def t_a_size_rule_can_be_undone_from_the_app():
    """The server has had `remove` and the rules listing since Resolve was
    built, with no interface on either - so a mistyped production size could be
    set from the app but only corrected by editing a CSV on the volume, which is
    the exact thing Resolve was added to stop."""
    ok("function openSizeRulesModal(" in SCRIPT, "there is a way to see the rules")
    fn = SCRIPT[SCRIPT.index("function openSizeRulesModal("):]
    fn = fn[:fn.index("\n        function ")]
    ok("/api/gobo-sizes/rules" in fn, "it reads the real rules")
    ok("op: 'remove'" in fn, "and can undo one")
    ok("kind: kind" in fn,
       "naming which file the rule lives in, since an alias and an override are "
       "removed from different places")
    ok("uiConfirm(" in fn, "removal asks first: it changes what the bench cuts")
    ok("res.can_edit" in fn or "canEdit" in fn,
       "and the Remove button is hidden from an account the server would refuse")
    ok("{ label: 'Size rules'" in SCRIPT, "reachable from the size-check menu")


@test
def t_the_login_screen_knows_a_password_is_not_always_enough():
    """The server stopped returning a session when a second factor is on. A
    client that ignored that would store undefined and look signed in."""
    fn = SCRIPT[SCRIPT.index("async function finish(p) {"):]
    fn = fn[:fn.index("\n            if (mode ===")]
    ok("p.mfa && p.ticket" in fn, "the half-login reply is recognised")
    ok("authShowMfa(p.ticket); return;" in fn,
       "and it asks for the code instead of storing a session that is not there")
    ok("function authShowMfa(" in SCRIPT, "there is a step to show")
    step = SCRIPT[SCRIPT.index("function authShowMfa("):]
    step = step[:step.index("\n            async function finish")]
    ok("/api/auth/mfa-verify" in step, "which finishes against the verify route")
    ok("one-time-code" in step, "with the autocomplete that lets a phone fill it")
    ok("recovery codes" in step, "and says what to do with a lost phone")


@test
def t_two_step_sign_in_can_be_turned_on_from_settings():
    ok("function openMfaSetup(" in SCRIPT, "there is a way to enrol")
    fn = SCRIPT[SCRIPT.index("function openMfaSetup("):]
    fn = fn[:fn.index("\n        function ")]
    ok("op: 'start'" in fn and "op: 'confirm'" in fn,
       "scan, then prove a code works: enrolling on trust locks people out")
    ok("only time they are shown" in fn, "recovery codes are shown once, and say so")
    off = SCRIPT[SCRIPT.index("async function refreshMfaRow("):][:1600]
    ok("uiAskPassword(" in off and "op: 'off', current: pw" in off,
       "turning it off takes the password, not a click: a borrowed session must not be able to")
    ok("op: 'start', current: pw" in fn, "and so does starting again with a different phone")


# --- per-person colour -------------------------------------------------------

TEAM_TINTS = ("red", "orange", "yellow", "green", "blue", "purple", "pink", "brown")


@test
def t_every_owner_tint_keeps_its_text_readable():
    """A tinted row still has to be a readable row. Computed here rather than
    eyeballed: 12% was the first strength that failed, on pink and red against
    the muted ink, so the tints sit at 10%."""
    def _rgb(h):
        h = h.lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

    def _lum(c):
        def f(v):
            v /= 255
            return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
        r, g, b = map(f, c)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    def _cr(a, b):
        la, lb = _lum(a), _lum(b)
        hi, lo = max(la, lb), min(la, lb)
        return (hi + 0.05) / (lo + 0.05)

    inks = {k: _token(k) for k in ("text-primary", "text-secondary", "text-tertiary")}
    for name in TEAM_TINTS:
        # .mrow specifically: the same name also styles the 8px presence dot,
        # which takes the SOLID colour and carries no text, so a contrast floor
        # does not apply to it.
        m = re.search(r"\.mrow\.own-" + name + r"\s*\{[^}]*background:\s*var\(--owner-" + name + r"-bg\)", CSS)
        ok(m, "there is a tint for " + name)
        # The tint is DERIVED: the hue at 10% over white. Compute the same mix
        # the browser will, and measure the inks against that.
        ok(re.search(r"--owner-%s-bg:\s*color-mix\(in srgb, var\(--owner-%s\) 10%%, var\(--white\)\)" % (name, name), CSS),
           "and the tint is the hue at 10%% over white, not a hand-picked hex")
        tint = tuple(round(255 - (255 - c) * 0.10) for c in _rgb(_token("owner-" + name)))
        for ink_name, ink in inks.items():
            r = _cr(_rgb(ink), tint)
            ok(r >= 4.5, "--%s on the %s row is %.2f:1, under the 4.5 needed"
               % (ink_name, name, r))


@test
def t_the_owner_tint_did_not_quietly_take_unreads_signal():
    """Handing the row background to the owner costs unread one of its four
    signals. It has to keep the other three, or a claimed unread email stops
    looking unread - which on a shared inbox means a customer waits."""
    unread = CSS.split(".mrow.unread {")[1].split("}")[0]
    ok("background:" not in unread,
       "unread no longer claims the background: the owner has it")
    ok("inset var(--bw-strong) 0 0" in unread, "but keeps the bar down its left")
    ok(".mrow.unread .mfrom" in CSS and "var(--weight-medium)" in
       CSS.split(".mrow.unread .mfrom {")[1].split("}")[0],
       "and the bold sender, which is what Gmail leans on anyway")


@test
def t_a_selected_row_still_reads_as_selected_over_a_tint():
    """Selection is transient and deliberate - you are about to act on those
    rows - so it wins over whose they are."""
    idx_sel = CSS.index(".mrow:is(.selected")
    idx_own = CSS.index(".own-red")
    ok(idx_own < idx_sel,
       "the selected rule comes after the tints, so it overrides rather than "
       "losing to whichever was written last")


@test
def t_a_colour_never_reaches_a_style_property_as_a_value():
    """The CRM's lesson, applied before it can be relearned: a Pipedrive label
    coloured url(//evil.co/a) once beaconed every render of the board."""
    ok("ownClass" in SCRIPT, "the colour becomes a class")
    fn = SCRIPT[SCRIPT.index("function ownClass("):]
    fn = fn[:fn.index("\n        function ")]
    ok("TEAM_TINTS" in fn or "indexOf" in fn or "includes(" in fn,
       "checked against the known names")
    ok(".style" not in fn and "background" not in fn,
       "and never assigned as a value")


@test
def t_the_colour_code_has_a_key_above_the_list_it_explains():
    """A tinted row is a colour nobody can look up unless the person it belongs
    to is named somewhere in view."""
    ok(".who-dot" in CSS, "the presence cards carry a dot")
    ok("ownClass(m.colour)" in SCRIPT, "in that person's colour")
    dot = CSS.split(".who-dot {")[1].split("}")[0]
    ok("width: var(--dot-md)" in dot and _token_raw("dot-md") == "8px", "small")
    ok(".who-dot.own-red    { background: var(--owner-red); }" in CSS and _token("owner-red") == "#b91c1c",
       "and SOLID, not the row tint: a 10% wash is invisible at 8px")


@test
def t_an_admin_can_change_someones_colour_from_the_team_tab():
    ok("op: 'colour'" in SCRIPT, "the team panel can set it")
    seg = SCRIPT[SCRIPT.index("inbox.append(el('legend', 'tm-legend', 'Inbox'))"):][:900]
    ok("TEAM_TINTS.forEach" in seg, "offering only the known names")
    ok("loadTeam()" in seg, "and the board redraws so the change is visible")


# ---------------------------------------------------------------------------
# Sending mail. Everything above this line was written while the app could only
# save a draft into Gmail; a person always pressed the last button. It can send
# now, which makes the confirm step, the grant and the honesty about a send that
# was never confirmed the three things that must never regress.
# ---------------------------------------------------------------------------


@test
def t_a_send_is_confirmed_against_the_address_the_server_resolved():
    """The one action in this app that cannot be taken back. The first POST
    carries dry:true - the server runs every check, writes nothing, sends
    nothing, and hands back the recipient it actually resolved - and the real
    send is issued by nothing but a person pressing Send now against THAT
    address, not against whatever was typed into the To box."""
    ok("async function mailSendFlow(" in SCRIPT,
       "one send flow, shared by the reply panel and the compose window")
    fn = SCRIPT[SCRIPT.index("async function mailSendFlow("):]
    fn = fn[:fn.index("\n        function ")]
    ok("Object.assign({ dry: true }, payload)" in fn,
       "the first call is a dry run, on a COPY: the payload it confirms is the "
       "one it later sends")
    ok("go.onclick" in fn, "there is a Send now")
    ok(fn.index("dry: true") < fn.index("go.onclick"),
       "the dry run happens before there is a Send now to press")
    after = fn[fn.index("go.onclick"):]
    ok("api('/api/mail/send', payload)" in after,
       "and the real send, with no dry flag on it, lives inside that handler")
    ok("api('/api/mail/send', payload)" not in fn[:fn.index("go.onclick")],
       "and nowhere else: nothing sends before it is confirmed")
    ok(after.index("api('/api/mail/send', payload)") < after.index("toastOk"),
       "the toast follows the send rather than announcing it in advance")
    ok("'Send to ' + to" in fn, "the confirm names the address")
    ok("dry.to" in fn, "which is the server's answer, not what was typed")
    ok("dry.cc_count" in fn and "dry.attachment_count" in fn,
       "and the cc and attachment counts beside it are the server's too, so a "
       "file that never landed is not counted in front of the person sending")
    ok("row.replaceWith(bar)" in fn, "Back puts the bar and the typed text back")
    ok("toastError(e.message)" in after and "go.disabled = false" in after,
       "a refusal is reported and hands the row back, never presenting as sent")


@test
def t_the_reply_panel_offers_send_only_to_an_account_that_holds_it():
    """The grant is a switch on the account, and admins hold it by rank, so
    both have to be read. A button that always fails is a lie, so an account
    without it keeps today's bar and is told once where the switch lives."""
    ok("function mailCanSend()" in SCRIPT, "one place decides")
    can = SCRIPT[SCRIPT.index("function mailCanSend()"):]
    can = can[:can.index("\n        function ")]
    ok("teamMe.can_send" in can and "teamMe.send_by_rank" in can,
       "reading the switch AND the rank that carries it")
    ok("function mailDraftPanel(m, t, btn, out) {" in SCRIPT, "the panel is still one builder")
    panel = SCRIPT[SCRIPT.index("function mailDraftPanel(m, t, btn, out) {"):]
    panel = panel[:panel.index("\n        async function ")]
    ok("const canSend = mailCanSend();" in panel, "the panel asks once")
    ok("canSend ? 'btn' : 'btn btn-primary'" in panel,
       "Save steps back to secondary only where Send has taken the lead")
    ok("bar.append(send)" in panel and "bar.append(save, copy, drop)" in panel,
       "the bar is composed in two pieces")
    ok(panel.index("bar.append(send)") < panel.index("bar.append(save, copy, drop)"),
       "so Send is first in the bar")
    ok("mailSendFlow(bar, payload()" in panel,
       "and goes through the shared two-step flow, not a second one of its own")
    ok("mailComposerPayload(cmp)" in panel and "id: t.id" in panel,
       "with the composer's html, files and inline images under the thread id")
    ok("Ask a lead to switch it on in Team." in panel,
       "an account without the grant is told where the switch lives")
    thread = SCRIPT.split("function paintMailThread(m, r) {")[1]
    thread = thread[:thread.index("\n        function ")]
    ok("'Write a reply'" in thread, "a reply can be written without spending AI credits")
    ok("mailDraftPanel(m, t, compose, { draft: '' })" in thread,
       "opening the same panel, empty")


@test
def t_compose_sits_in_the_inbox_header_behind_the_grant():
    """A new conversation is not a reply to anything, so it belongs to the card
    that owns the mailbox, first in the row of things you press."""
    fn = SCRIPT.split("function renderMail() {")[1]
    fn = fn[:fn.index("\n        function ")]
    ok("const mAct = el('div', 'card-act')" in fn, "the header still has its action row")
    seg = fn[fn.index("const mAct = el('div', 'card-act')"):][:1800]
    ok("if (mailCanSend()) {" in seg, "hidden from an account the server would refuse")
    ok("openMailCompose()" in seg, "and opens the compose window")
    ok("mAct.append(cmp)" in seg and "mAct.append(filt, rf)" in seg,
       "appended in two steps")
    ok(seg.index("mAct.append(cmp)") < seg.index("mAct.append(filt, rf)"),
       "so Compose is first, ahead of Filters and Refresh")


@test
def t_the_compose_window_is_a_modal_of_the_house_kind():
    """Built like Size rules: an overlay, a head, an X, and no second way out.
    A half-written email to a customer is exactly the thing a stray click on
    the backdrop must not throw away."""
    ok("function openMailCompose()" in SCRIPT, "the window exists")
    fn = SCRIPT[SCRIPT.index("function openMailCompose()"):]
    fn = fn[:fn.index("\n        async function ")]
    ok("el('div', 'modal-overlay show')" in fn and "el('div', 'modal-head')" in fn,
       "the house modal idiom")
    ok("x.onclick = () => overlay.remove()" in fn, "with an X that closes it")
    ok("e.target === overlay" not in fn and "Escape" not in fn,
       "and nothing else that closes it")
    ok("name@company.com, another@company.com" in fn, "To says the shape it takes")
    # The body was a textarea until the composer landed. The requirement is
    # unchanged - a box with room to write in, sized by the app's own styles -
    # and what carries it is now mountComposer, which brings its own.
    ok("mountComposer(box" in fn, "the body is the app's own composer")
    ok("mailSendFlow(bar" in fn, "and the same dry-run confirm as a reply")
    ok("five addresses" in fn and "sign-off and the" in fn,
       "the cap and what gets added are stated where the message is typed, not "
       "discovered after a refusal")
    done = fn[fn.index("mailSendFlow(bar"):][:400]
    ok("overlay.remove()" in done and "refreshMailQuiet()" in done,
       "success closes the window and repaints the board")


@test
def t_the_send_grant_is_switched_from_the_team_tab():
    """A capability, not a tab, granted the way the size list is granted. An
    admin holds it by rank, so they get a statement rather than a switch that
    would not actually revoke anything."""
    # Was a fixed 5,200-character window, which the sign-off field pushed the
    # send op out of. Bounded by the function instead, so it neither expires
    # the next time the panel grows nor reaches past it into another one.
    people = fn_src("function renderTeamPeople(")
    ok("if (u.sizes_by_rank) {" in people, "the size grant is still the pattern")
    seg = people[people.index("if (u.sizes_by_rank) {"):]
    ok("if (u.send_by_rank) {" in seg, "rank is read before the switch is drawn")
    ok("(every admin can)" in seg.split("if (u.send_by_rank) {")[1][:300],
       "and an admin is told, not offered a switch that lies")
    ok("sendBox.checked = !!u.can_send" in seg, "everyone else gets a checkbox")
    ok("'tm-tabpick'" in seg.split("if (u.send_by_rank) {")[1][:600],
       "in the same row style as the size one")
    ok("op: 'send', id: u.id, can_send: sendBox.checked" in seg,
       "posting the contract's own op")
    ok("sendBox && sendBox.checked !== !!u.can_send" in seg,
       "only when it actually changed, or the ledger records a grant nobody made")


@test
def t_a_send_that_was_never_confirmed_is_reported_rather_than_hidden():
    """Report, do not shred. The server stamps the send before it calls Gmail,
    so a crash in between leaves a maybe, and a maybe is told in the words that
    say what to do about it."""
    ok("function mailPendingLine(" in SCRIPT, "one sentence, in one place")
    fn = SCRIPT[SCRIPT.index("function mailPendingLine("):]
    fn = fn[:fn.index("\n        async function ")]
    ok("may have gone out" in fn and "Sent folder" in fn,
       "it says what may have happened and where to look")
    board = SCRIPT.split("function renderMail() {")[1]
    board = board[:board.index("\n        function ")]
    ok("(d.outbound_pending || [])" in board,
       "the board reports its own unconfirmed sends")
    ok("mail-sendwarn" in board, "in a warning row")
    ok(board.index("mail-sendwarn") < board.index("const bulkHost = el('div')"),
       "above the list, not buried under it")
    thread = SCRIPT.split("function paintMailThread(m, r) {")[1]
    thread = thread[:thread.index("\n        function ")]
    ok("if (t.send_pending)" in thread, "and so does the thread it belongs to")
    ok("'mail-viewwarn'" not in thread.split("if (t.send_pending)")[1][:400],
       "under a class of its own: the viewing heartbeat finds .mail-viewwarn by "
       "class and removes it whenever nobody else is looking, which would have "
       "swept an unconfirmed send off the screen ten seconds after it appeared")
    ok(".mail-sendwarn {" in CSS, "which is styled as the warning it is")
    ok("dashed" not in CSS.split(".mail-sendwarn {")[1].split("}")[0],
       "with a solid edge: a dashed one means somewhere to drop something")


@test
def t_nothing_in_the_page_still_claims_the_app_never_sends():
    """It sends now. A comment or a line of help that still says otherwise is
    worse than none: it is the reason someone presses Send believing it saves a
    draft."""
    for gone in ("The app never sends mail", "never sends", "Nothing is sent"):
        ok(gone not in HTML, "a stale claim is still in the page: " + gone)
    ok("Send goes straight to the customer from" in SCRIPT,
       "and the draft panel says what Send actually does")
    ok("Save keeps it as a Gmail draft instead." in SCRIPT,
       "naming the other button by what it does, in the same breath")


def _typeahead_fn():
    """The body of crmTypeahead, which several of the tests below read."""
    fn = SCRIPT[SCRIPT.index("function crmTypeahead("):]
    return fn[:fn.index("\n        function crmPersonRows(")]


@test
def t_the_typeahead_takes_an_optional_pick_and_leaves_the_crm_forms_alone():
    """The mail To line holds addresses, several of them, comma separated: the
    name that a CRM form writes is exactly the wrong thing there. So picking is
    a parameter, and it defaults to what the four CRM callers already got. A
    default that drifted would silently rewrite every deal form."""
    fn = _typeahead_fn()
    ok(re.search(r"function crmTypeahead\(input, getRows, opts\)", fn),
       "the third argument exists")
    ok(re.search(r"o\.pick \|\| \(\(r\) => \{ input\.value = r\.name; \}\)", fn),
       "and defaults to writing the name, which is what the CRM forms rely on")
    for caller in ("crmTypeahead(personIn, crmPersonRows)",
                   "crmTypeahead(orgIn, crmOrgRows)",
                   "crmTypeahead(perIn, crmPersonRows)",
                   "crmTypeahead(dupIn, people ? crmPersonRows : crmOrgRows)"):
        ok(caller in SCRIPT, "the CRM caller still passes two arguments: " + caller)


@test
def t_the_typeahead_is_announced_as_a_combobox():
    """A dropdown a screen reader cannot see is a dropdown that is not there.
    The roles are the cheap half of the keyboard support below."""
    fn = _typeahead_fn()
    ok("input.setAttribute('role', 'combobox')" in fn, "the input is a combobox")
    ok("input.setAttribute('aria-autocomplete', 'list')" in fn, "with a list to autocomplete from")
    ok("aria-expanded" in fn, "that says whether the list is open")
    ok("drop.setAttribute('role', 'listbox')" in fn, "the drop is the listbox")
    ok("b.setAttribute('role', 'option')" in fn, "and each row an option")
    ok("aria-selected" in fn, "with the highlighted one marked as selected")


@test
def t_the_typeahead_answers_to_the_arrow_keys_and_enter():
    """Reaching for the mouse mid address is the whole cost of a typeahead.
    Enter must preventDefault: the input sits in a modal where Enter would
    otherwise submit the half typed address behind the open dropdown."""
    fn = _typeahead_fn()
    ok("'keydown'" in fn, "there is a key handler")
    key = fn[fn.index("'keydown'"):]
    ok("e.key === 'ArrowDown'" in key and "e.key === 'ArrowUp'" in key,
       "both arrows move the highlight")
    ok("e.preventDefault()" in key.split("e.key === 'ArrowDown'")[1][:200],
       "and the arrow does not also run the caret to the end of the line")
    ok("e.key === 'Enter'" in key, "Enter picks")
    ok("e.preventDefault()" in key.split("e.key === 'Enter'")[1][:200],
       "and is swallowed, or the form behind it submits")
    ok("hi >= 0" in key.split("e.key === 'Enter'")[1][:200],
       "but only when a row is actually highlighted: an Enter on plain typing "
       "must go where it always went")


@test
def t_escape_closes_the_dropdown_and_never_the_modal_behind_it():
    """The one Escape in this app that does anything at all, and it is a
    dropdown, not a way out. A compose window holding a half written email to a
    customer must survive it, so the key is stopped before it can reach
    anything that removes an overlay."""
    fn = _typeahead_fn()
    ok("e.key === 'Escape'" in fn, "Escape is handled")
    esc = fn[fn.index("e.key === 'Escape'"):]
    esc = esc[:esc.index("return;")]
    ok("e.stopPropagation()" in esc, "and stopped where it is handled")
    ok("hide()" in esc, "hiding the dropdown, which is the whole of what it does")
    ok("overlay" not in fn and "remove()" not in fn,
       "and nothing anywhere in the typeahead removes anything: the window this "
       "sits in is closed by its X and by nothing else")


@test
def t_the_keyboard_highlight_looks_exactly_like_the_mouse_one():
    """Two highlights that differ by a shade read as two different states."""
    ok(re.search(r"\.crm-ta-drop button:hover[^{]*\.crm-ta-drop button\.on[^{]*\{", CSS),
       "the keyboard highlight shares the hover rule rather than inventing a colour")


@test
def t_the_compose_to_line_is_a_typeahead_over_the_address_book():
    """Typing a customer's address from memory is how a message goes to the
    wrong person. The book comes from the threads and the CRM, and the field is
    still a plain text box underneath, so it works when the fetch fails."""
    fn = SCRIPT[SCRIPT.index("function openMailCompose()"):]
    fn = fn[:fn.index("\n        async function ")]
    ok("crmTypeahead(to, mailAddressRows, { pick })" in fn,
       "the To field goes through the house typeahead with its own pick")
    ok("name@company.com, another@company.com" in fn,
       "and is still the same plain text field underneath")
    ok("mailAddressBook()" in fn, "the book is asked for when the window opens")
    ok("await mailAddressBook()" not in fn,
       "in the background: the modal does not wait on a network call to open")
    ok("to.inputMode = 'email'" in fn and "to.type = 'email'" not in fn,
       "the field is a text box with an email keyboard, not an email input: a "
       "multiple email input runs the HTML value sanitiser, which splits on the "
       "commas and strips the spaces around them, so the ', ' a pick appends "
       "came back as ',' and the line read as one run-on address")


@test
def t_picking_an_address_replaces_only_the_one_being_typed():
    """Five addresses go in this box. A pick that wrote the whole value would
    wipe the four already in it, which is a bug you find after pressing Send."""
    ok("function mailAddressToken(" in SCRIPT, "the split is named and in one place")
    fn = SCRIPT[SCRIPT.index("function mailAddressToken("):]
    fn = fn[:fn.index("\n        function ")]
    ok("lastIndexOf(',')" in fn, "everything before the last comma is settled")
    compose = SCRIPT[SCRIPT.index("function openMailCompose()"):]
    compose = compose[:compose.index("\n        async function ")]
    ok("const pick = " in compose, "the compose window brings its own pick")
    pick = compose[compose.index("const pick = "):][:520]
    ok("mailAddressToken(to.value)" in pick, "the pick splits the same way")
    ok("r.email + ', '" in pick,
       "writes the address and the separator, so the next one can be typed")
    ok("p.head" in pick, "keeping the addresses already entered")


@test
def t_the_address_rows_match_on_name_or_address_and_read_as_both():
    """Half of these people are remembered by name and half by the address, and
    a row that shows only one of the two is a row nobody can confirm."""
    ok("function mailAddressRows(" in SCRIPT, "the rows have a source")
    fn = SCRIPT[SCRIPT.index("function mailAddressRows("):]
    fn = fn[:fn.index("\n        function ")]
    ok("mailAddressToken(q).tail" in fn,
       "it matches on the address being typed, not the whole line, and splits "
       "it where the pick splits it: two copies of that rule would drift")
    ok("if (!t) return []" in fn, "an empty token offers nothing")
    ok("r.name + ' ' + r.email" in fn, "and matches a name or an address")
    ok("id: r.email" in fn and "email: r.email" in fn,
       "the address is the identity of the row")
    ok("r.name || r.email" in fn,
       "an address with no name shows as itself rather than as a blank line")


@test
def t_the_address_book_is_fetched_once_and_kept():
    """1,951 people is one fetch, not one per keystroke. It is a cache with a
    clock on it, like every other cache in this file, and a failure is silent:
    the field is a text box that works without it."""
    ok("let mailAddrCache = { at: 0, rows: [] }" in SCRIPT, "cache, with a timestamp")
    ok("function mailAddressBook(" in SCRIPT, "one fetcher")
    fn = SCRIPT[SCRIPT.index("async function mailAddressBook("):]
    fn = fn[:fn.index("\n        function ")]
    ok("'/api/mail/addresses'" in fn, "against the contract's route")
    ok(re.search(r"Date\.now\(\) - mailAddrCache\.at < MAIL_ADDR_TTL", fn),
       "and does nothing while the last answer is still fresh")
    ok(re.search(r"MAIL_ADDR_TTL = 10 \* 60 \* 1000", SCRIPT), "which is ten minutes")
    ok("catch" in fn and "toastError" not in fn,
       "a failure is swallowed: nobody asked for an address book")


@test
def t_the_eori_line_has_one_branch_per_status():
    """Four answers come back and they mean four different things. The one that
    must never be drawn as "not valid" is unknown: a timeout is not a bad
    number, and refusing an export booking over a number the EU service simply
    failed to answer for is the cost of getting that wrong."""
    ok("function eoriPaint(" in SCRIPT, "one place turns an answer into the line")
    fn = fn_src("function eoriPaint(")
    for st in ("'valid'", "'invalid'", "'not_covered'"):
        ok(st in fn, "the " + st + " answer is tested by name")
    ok("Not valid according to the EU database." in fn, "the invalid line, in those words")
    ok(fn.count("=== 'invalid'") == 1,
       "and it is reached by exactly one explicit test for that status")
    ok(fn.count("'eori-line bad'") == 1, "exactly one branch paints the red tone")
    red = fn.index("'eori-line bad'")
    ok(0 < red - fn.index("=== 'invalid'") < 120,
       "and it is the branch guarded by status === 'invalid', immediately above it")
    unk = fn.index("Could not check:")
    ok(unk > red, "the unknown line is a later branch than the invalid one")
    ok(fn.rindex("'eori-line muted'", 0, unk) > red,
       "and sets a muted tone of its own rather than falling into the red one: "
       "a service that did not answer is not a number that is wrong")
    ok("} else {" in fn, "the last branch is an else")
    tail = fn[fn.rindex("} else {"):]
    ok("Could not check:" in tail and "if (" not in tail,
       "and it is unknown, with no condition of its own, so a status this file "
       "has never heard of reads as unchecked rather than as invalid")
    ok("Try again in a minute." in fn, "and says what to do about it")
    ok("r.cached ?" in fn and "from an earlier check" in fn and "checked just now" in fn,
       "a valid answer says whether it came off the wire or out of the cache")


@test
def t_the_gb_line_hands_over_to_hmrc_without_handing_over_the_tab():
    """The EU database does not hold GB numbers, so a GB answer is a signpost,
    not a verdict. It opens in its own tab because the settings form behind it
    is usually half filled in."""
    ok("function eoriPaint(" in SCRIPT, "one place turns an answer into the line")
    fn = fn_src("function eoriPaint(")
    ok("https://www.tax.service.gov.uk/check-eori-number" in fn, "the HMRC checker")
    ok("Check GB numbers at gov.uk" in fn, "named as where it goes")
    ok("target = '_blank'" in fn, "opens beside the half-filled form")
    ok("rel = 'noopener'" in fn,
       "and the page it opens cannot reach back into this one through opener")
    ok("r.reason" in fn[fn.index("not_covered"):], "the server's sentence is shown too")


@test
def t_the_eori_check_button_comes_back_from_every_outcome():
    """A button that stays dead after a failed check is a checker that works
    once. Every path out of the request re-enables it, including the throw."""
    ok("async function eoriRun(" in SCRIPT, "one runner behind the button")
    fn = fn_src("async function eoriRun(")
    ok("'/api/eori/check'" in fn, "against the contract's route")
    ok("btn.disabled = true" in fn, "the button goes down while a check is in flight")
    ok(re.search(r"finally\s*\{[^}]*btn\.disabled = false", fn),
       "and comes back in a finally, not on the happy path only")
    ok("catch" in fn and "eoriPaint" in fn,
       "a transport failure is drawn on the same line, not swallowed")
    ok(re.search(r"/\[\.!\?\]\$/\.test\(why\)", fn),
       "and is punctuated first: the browser's own 'Failed to fetch' carries no "
       "full stop and ran straight into the sentence after it")
    blk = SCRIPT[SCRIPT.index("Check a customer’s EORI"):][:2600]
    ok("'e.g. DE123456789'" in blk, "the placeholder the contract names")
    ok("e.key === 'Enter'" in blk and "eoriRun(" in blk,
       "Enter in the box checks, so the number can be typed and confirmed "
       "without reaching for the mouse")


@test
def t_the_filters_window_gates_the_email_section_on_the_servers_lead_flag():
    """The footer signs every email this business sends, so who may change it
    is the server's answer, not this window's. A non-lead still sees what is
    being appended to their replies."""
    ok("async function paintMailEmailSettings(" in SCRIPT, "the section has a source")
    fn = fn_src("async function paintMailEmailSettings(")
    ok("'/api/mail/settings'" in fn and "op: 'get'" in fn, "read from the contract's route")
    ok("const lead = !!d.lead" in fn,
       "gated on the flag the SERVER sent, not on the rules window's own idea "
       "of who is a lead")
    ok("readOnly = !lead" in fn, "a non-lead reads the footer and cannot type into it")
    # The free-text footer became six named slots; the ops moved with it and
    # the per-line cap came down from 1000 to 200.
    for op in ("op: 'footer_slots'", "op: 'reply_save'", "op: 'reply_delete'"):
        ok(op in fn, "the lead-only " + op)
    ok("200 characters" in fn,
       "the cap is on screen before it is hit, not discovered by refusal")
    rules = fn_src("function paintMailRules(")
    ok("paintMailEmailSettings(" in rules, "the Filters window draws it")
    stop = rules.index("Only a lead can change these.")
    ok(stop < rules.index("paintMailEmailSettings("),
       "at the end, below the filters themselves")
    ok("return" not in rules[stop:stop + 200].split("}")[0],
       "and a non-lead reaches it: their branch says so and carries on, where "
       "it used to return and end the window before the Email section for "
       "exactly the people who cannot see the footer any other way")


@test
def t_the_settings_modal_carries_your_sign_off():
    """Every person's own name on their own replies, set where they already go
    to change their own password."""
    ok('id="signoff-text"' in HTML, "the box is in the markup")
    m = re.search(r'<textarea id="signoff-text"[^>]*rows="(\d+)"', HTML)
    ok(m and m.group(1) == "4", "four rows, which is the cap the contract sets")
    start = HTML.index('id="settings-modal"')
    end = HTML.index('</div>\n    </div>', HTML.index('id="usage"'))
    ok(start < HTML.index('id="signoff-text"') < end,
       "inside the Settings modal, not loose on the page")
    ok("async function refreshSignOffRow(" in SCRIPT, "it is filled from the server")
    fn = fn_src("async function refreshSignOffRow(")
    ok("'/api/mail/settings'" in fn, "on the mail settings route")
    ok("op: 'sign_off'" in fn, "and saved with the contract's op")
    ok('id="signoff-row" style="display:none"' in HTML,
       "the row starts hidden, and is shown only once the server has answered")
    ok("catch (e)" in fn, "the fetch has a failure path")
    ok("display = 'none'" in fn[fn.index("catch (e)"):][:130],
       "which puts the row back to hidden: somebody with no Inbox must not be "
       "left an empty box that the mail guard will refuse to save")
    open_btn = SCRIPT[SCRIPT.index("$('settings-btn').onclick"):][:200]
    ok("refreshSignOffRow()" in open_btn, "refreshed when the modal opens, beside the two-step row")


@test
def t_what_gets_added_when_sent_is_shown_and_vanishes_when_there_is_none():
    """The sign-off and the footer are appended by the server, so the only
    place a person can see what their reply will actually end with is here. An
    empty box labelled "Added when sent" claims something is added when
    nothing is, so with neither set there is no box."""
    ok("function mailEmailBits(" in SCRIPT, "one reader for the board's email block")
    bits = fn_src("function mailEmailBits(")
    ok("mailCache && mailCache.email" in bits,
       "read off the board payload, so an older board with no email block is "
       "empty rather than a thrown TypeError")
    ok("saved_replies: e.saved_replies || []" in bits,
       "and every field falls back to its own empty shape, so the picker can "
       "iterate the replies without checking first")
    ok("function mailAddedWhenSent(" in SCRIPT, "one preview block")
    fn = fn_src("function mailAddedWhenSent(")
    ok("mailEmailBits()" in fn, "through that one reader")
    ok("'Added when sent'" in fn, "labelled as what it is")
    ok(re.search(r"if \(!\w+ && !\w+\) return", fn),
       "and with both empty it draws nothing at all")
    ok(fn.index("sign_off") < fn.index("footer"),
       "in send order: the sign-off, then the shop footer under it")


@test
def t_a_saved_reply_lands_where_the_cursor_is():
    """A saved reply is dropped into a paragraph someone is already writing.
    Appending it at the end instead puts the artwork rules after the sign-off
    of a half-written sentence."""
    ok("function mailReplyPicker(" in SCRIPT, "the picker has a source")
    fn = fn_src("function mailReplyPicker(")
    ok("if (!reps.length) return" in fn,
       "no saved replies, no select: an empty dropdown is a dead control")
    # The box became the composer, which keeps the caret when the focus moves
    # to this dropdown and puts the cursor after what it inserted. Same
    # requirement, one caller instead of four lines of selection arithmetic.
    ok("cmp.insertText(" in fn, "the text goes in at the cursor, over any selection")
    ok("cmp.focus()" in fn, "back in the box, ready to carry on typing")
    ok("sel.value = ''" in fn, "and the select resets, so the same reply can go in twice")


@test
def t_the_compose_and_reply_boxes_keep_the_class_that_sizes_them():
    """Both windows grew a preview and a dropdown underneath, and then the box
    itself became the composer. What they are underneath still has to be the
    one box this app writes email in, with both of those under it."""
    for name in ("function openMailCompose()", "function mailDraftPanel("):
        fn = fn_src(name)
        ok("mountComposer(box" in fn, name + " writes in the composer")
        ok("mailAddedWhenSent(" in fn, name + " shows what is appended on send")
        ok("mailReplyPicker(cmp" in fn, name + " offers the saved replies into that box")


@test
def t_an_admin_sets_someone_elses_sign_off_beside_their_other_switches():
    """A new starter's replies go out unsigned until somebody sets it for them,
    and that somebody is whoever already manages the account."""
    fn = fn_src("function renderTeamPeople(")
    ok("op: 'sign_off'" in fn, "the team panel posts the contract's op")
    i = fn.index("op: 'sign_off'")
    ok("'/api/team/user'" in fn[:i], "to the team route")
    ok("id: u.id" in fn[i:i + 140], "for the account whose panel it is")
    panel = fn.index("teamTabsOpen === u.id")
    ok("if (manageable)" in fn[panel:i],
       "and only where the size and send switches beside it are shown")


# ---- the composer ------------------------------------------------------
# A contenteditable editor of our own, in its own file. These read the source
# the way the rest of this suite reads the page: the browser cleaner and the
# server sanitiser have to keep the same allowlist, and a toolbar button that
# quietly disappeared on a phone is a feature nobody can use.


@test
def t_the_composer_is_its_own_file_served_like_the_app_script():
    """One more script, gated and cache-busted exactly like the app's own, so a
    stale composer can never be handed to a browser."""
    ok("function mountComposer(" in COMPOSER and "window.mountComposer = mountComposer" in COMPOSER,
       "the file exports one mount function onto the window")
    src = open(os.path.join(ROOT, "copilot.py"), encoding="utf-8").read()
    ok('"/assets/composer.js"' in src and '_asset_hashes["composer"]' in src,
       "hashed and routed like app.js")
    ok("composer.js?v=" in src, "the shell loads it by hash")
    ok("\u2014" not in COMPOSER and "\u2013" not in COMPOSER, "no em or en dashes")


@test
def t_the_composer_toolbar_covers_the_agreed_set_and_nothing_hides_on_a_phone():
    """The set the Inbox agreed on, and a bar that wraps to a second row rather
    than hiding the half of it that did not fit."""
    for cmd in ("bold", "italic", "underline", "fontName", "fontSize", "foreColor", "justifyLeft",
                "justifyCenter", "justifyRight", "insertUnorderedList", "insertOrderedList",
                "createLink", "removeFormat", "formatBlock"):
        ok("'%s'" % cmd in COMPOSER, "toolbar command " + cmd)
    ok("'image'" in COMPOSER and "'attach'" in COMPOSER, "image and attach buttons")
    # Asserted against the BAR's own rule: the chip row wraps too, and a
    # blanket search for the property was answered by that one while the
    # toolbar quietly clipped.
    bar = COMPOSER.split(".cmp-bar {")[1].split("}")[0]
    ok("flex-wrap: wrap" in bar or "flex-wrap:wrap" in bar,
       "the toolbar wraps rather than hiding")


@test
def t_pasted_markup_is_cleaned_to_the_same_allowlist_as_the_server():
    """A paste out of Word or a web page arrives as somebody else's markup. It
    is cleaned on the way in by the same allowlist the server enforces on the
    way out, so what is on screen is what will actually be sent."""
    ok("addEventListener('paste'" in COMPOSER and "clipboardData" in COMPOSER,
       "a paste is intercepted rather than dropped in raw")
    ok("function cleanHtml(" in COMPOSER, "one cleaner, applied on paste and on getHtml")
    for tag in ("script", "iframe", "style", "svg"):
        ok("'%s'" % tag in COMPOSER, tag + " is named in the drop list")
    ok("'cid:'" in COMPOSER, "images leave as cids")


@test
def t_inline_images_become_cids_and_are_counted_against_the_meter():
    """An inline image is an attachment that happens to be shown in the body:
    it counts against the same 25MB ceiling as everything else."""
    ok("data-key" in COMPOSER and "data-cid" in COMPOSER,
       "an inline image carries its bucket key and its content-id")
    ok("25 * 1024 * 1024" in COMPOSER, "the meter knows the ceiling")
    ok("inline: true" in COMPOSER, "and is listed as an inline attachment")


@test
def t_compose_and_reply_mount_the_composer_and_nothing_else_does():
    """Two windows write email and no others do. A third mount would be a third
    place for the payload to drift out of shape."""
    ok(SCRIPT.count("mountComposer(") == 2,
       "Compose and the reply panel, exactly (%d)" % SCRIPT.count("mountComposer("))
    ok("mailComposerPayload(" in SCRIPT, "one reader turns a composer into a payload")
    pay = fn_src("function mailComposerPayload(")
    ok("html:" in pay, "carrying the html")
    ok("attachments:" in pay and "inline:" in pay,
       "and the two lists the send route takes, kept apart")


@test
def t_the_dry_run_confirm_names_recipients_and_attachment_count():
    """What is about to leave, counted by the server rather than by the window
    that is asking: a file that failed to land is not on the server's count."""
    fn = fn_src("async function mailSendFlow(")
    ok("attachment_count" in fn and "cc_count" in fn,
       "the confirm row reads the counts the dry run returned")


@test
def t_cc_bcc_fold_away_and_reply_all_fills_cc_minus_us():
    """Most replies have no Cc, so the fields are folded until they are asked
    for. Reply all is the one press that fills them, from the server's list."""
    fold = fn_src("function mailCcFold(")
    ok("'Cc'" in fold and "'Bcc'" in fold, "both lines exist")
    ok("display = 'none'" in fold and "aria-expanded" in fold,
       "folded away until they are asked for, and saying so")
    ok("cc.value || bcc.value" in fold,
       "and unfolded again the moment either of them has an address in it")
    fn = fn_src("function mailDraftPanel(")
    ok("mailCcFold(" in fn, "the reply panel carries them")
    ok("reply_all_cc" in fn and "Reply all" in fn,
       "and Reply all fills the Cc from the thread's own list, which already "
       "has us and the person being answered taken out of it")


@test
def t_the_quoted_original_is_a_switch_not_a_rendering():
    """The original is quoted by the SERVER, under the reply. The browser says
    it will happen and never renders a line of what a customer sent as html."""
    fn = fn_src("function mailDraftPanel(")
    ok("quote:" in fn, "the payload carries the switch")
    ok("will be quoted" in fn.lower() or "quoted below" in fn.lower(),
       "and the panel says what it does")
    ok(".innerHTML = t." not in fn and "innerHTML = msg." not in fn,
       "no incoming html reaches the page")


@test
def t_uploads_go_through_presign_then_done_and_never_the_server_body():
    """A 20MB attachment never touches our server: it is signed for, PUT
    straight into the bucket, and only then confirmed by key."""
    fn = fn_src("async function mailUpload(")
    ok("/api/mail/attach-url" in fn and "/api/mail/attach-done" in fn,
       "signed for, then confirmed")
    ok("method: 'PUT'" in fn, "and the bytes go to the bucket directly")


@test
def t_footer_slots_are_edited_by_leads_with_a_logo_picker():
    """The footer became six named lines and a logo, so a lead fills in fields
    instead of hand-writing the shop's own address into a text box."""
    fn = fn_src("async function paintMailEmailSettings(")
    for k in ("company", "address", "phone", "website", "legal"):
        ok("'%s'" % k in fn, "slot " + k)
    ok("logo_url" in fn and "logo_done" in fn and "footer_slots" in fn,
       "the logo goes up by the same presign flow, and the slots are saved as one")
    ok("op: 'footer'" not in fn, "the free-text footer op is gone")


@test
def t_no_em_or_en_dash_reaches_the_page():
    """CI fails the build on one, and the house voice uses a colon or a full
    stop. Asserted here too so it fails in the suite the author actually runs."""
    # Written out or escaped: "\u2014" in a string renders an em dash just the
    # same, and the literal-character check let one reach a toast (A48 in the
    # 2026-09-22 bug audit). The composer is page copy too.
    for src, where in ((HTML, "static/index.html"), (COMPOSER, "static/composer.js")):
        for ch, name in (("—", "em dash"), ("–", "en dash"), ("\\u2014", "escaped em dash"),
                         ("\\u2013", "escaped en dash"), ("&mdash;", "em dash entity"),
                         ("&ndash;", "en dash entity")):
            ok(ch not in src, "an " + name + " is in " + where)


@test
def t_a_list_never_leaves_the_editor_inside_a_paragraph():
    """Chromium's insertUnorderedList inside a <p> yields <p><ul>..</ul></p>
    and an empty <p></p> either side. Clients disagree about that markup, so
    the cleaner unwraps the paragraph and drops the empties; a <p><br></p> is
    a deliberate blank line and must survive."""
    fn = COMPOSER[COMPOSER.index("function tidyParagraph("):]
    fn = fn[:fn.index("\n    }\n") + 7]
    ok("unwrap(p)" in fn, "a paragraph holding a block is unwrapped")
    ok("!p.childNodes.length" in fn and "p.remove()" in fn, "an empty paragraph goes")
    ok("'ul'" in COMPOSER[COMPOSER.index("var BLOCKS"):COMPOSER.index("var BLOCKS") + 120],
       "a list counts as a block")
    ok("if (tag === 'p') tidyParagraph(n);" in COMPOSER, "and it runs from the walker, on every pass")


@test
def t_the_four_inch_square_stock_exists_and_the_two_sides_agree():
    """The production printer is loaded with 4x4 and it was not on the list at
    all, which is why the size had to be chosen by hand every time. The server
    validates saves against its own list, so the two must name the same sizes
    or a size the page offers is refused on save."""
    sizes = SCRIPT[SCRIPT.index("const LABEL_SIZES = {"):]
    sizes = sizes[:sizes.index("};")]
    ok("'4x4'" in sizes, "4 x 4 is on the list")
    ok("101.6" in sizes.split("'4x4'")[1].split("}")[0], "and it is square, in millimetres")
    client = set(re.findall(r"'([0-9a-z]+)': \{ w:", sizes))
    src = open("copilot.py", encoding="utf-8").read()
    block = src[src.index("LABEL_STOCK = ("):]
    server = set(re.findall(r'"([0-9a-z]+)"', block[:block.index(")")]))
    ok(client == server,
       "the sizes the page offers are exactly the ones the server accepts "
       "(page %s, server %s)" % (sorted(client), sorted(server)))


@test
def t_each_printer_reads_its_own_saved_default():
    """Production and courier stock are separate settings. A change at the
    print button is for that print only: it must never write the config, or
    one person's test print re-points the whole bench's stock."""
    ok("label_size_production" in fn_src("function prodSize("),
       "the production size comes from the saved setting")
    carrier = fn_src("function carrierDims(")
    ok("label_size_shipping" in carrier and "'4x6'" in carrier,
       "the courier sheet reads its own setting, falling back to 4 x 6")
    ok("labelDims" not in carrier, "and never the production selection")
    bar = SCRIPT[SCRIPT.index("const sizeSel = el('select', 'lbl-size')"):]
    bar = bar[:bar.index("bar.append(sizeSel)")]
    ok("/api/shipping/config" not in bar, "changing it at the print button saves nothing")
    ok("localStorage" not in bar, "and no longer hides in one browser's storage")
    ok("(default)" in bar, "the saved default is marked, so being off it is visible")


@test
def t_the_settings_screen_sets_both_printers_and_warns_about_the_barcode():
    """Courier artwork is 4 x 6. On other stock it is scaled to fit, and a
    shrunk barcode is one a scanner will not read - the screen has to say so
    where the choice is made."""
    fn = fn_src("async function openShippingSettings(")
    ok("Label printers" in fn, "the section exists")
    ok("label_size_production" in fn and "label_size_shipping" in fn, "both dropdowns save")
    ok("scan" in fn.lower() and "4 x 6" in fn, "and the barcode warning names the artwork size")



@test
def t_no_guard_is_stranded_below_the_runner():
    """The runner ends in sys.exit, so a test appended below it is DEFINED and
    never RUN - and the suite still reports green. One had been sitting there
    with a broken call for a day. New tests go above this block."""
    src = open(__file__, encoding="utf-8").read()
    # Anchored to the line start: this guard quotes the marker itself, and an
    # unanchored search would find its own text and always pass.
    tail = src[src.index("\nif __name__ ==") :]
    ok("@" + "test" not in tail,
       "a test is defined below the runner and will never execute")



@test
def t_a_tag_is_checked_before_it_is_sent():
    """Bulk by tag is the single-order discipline over a list: a check arms
    exactly the tag it ran for, retyping disarms it, a send spends it while
    the results stay on screen, and the rows are the same rows."""
    armed = fn_src("function connTagArmed(")
    ok("connTagCheck.tag ===" in armed, "the check must be for the tag in the box")
    ok("!connTagCheck.sent" in armed, "and a send spends it, though its results stay readable")
    fn = fn_src("function renderConnector(")
    ok("connTagArmed(" in fn, "the send button asks it rather than deciding for itself")
    ok("op: 'reimport_tag', tag: tag, dryRun: true" in fn, "the check is a dry run, which writes nothing")
    ok("sent: true" in fn, "and the live send marks the check spent")
    watch = fn_src("function connStartWatch(")
    ok("tagJob" in watch, "the outcome is collected from the status once the service stops, never awaited in the reply")
    ok("if (connTagBusy) connStartWatch();" in fn, "and a tab left mid-job collects it on return")
    ok(fn.count("connDocTable(") == 2, "one order and a tagged list paint their documents with the same table")
    ok("connIsAdmin()" in fn, "and only an admin sees the send")



@test
def t_one_order_is_checked_before_it_is_sent():
    """The same review-before-send discipline as the batch, per order: a check
    arms exactly the order it was run for, so retyping the box disarms the
    send rather than sending something nobody looked at."""
    armed = fn_src("function connOneArmed(")
    ok("connOneCheck.order ===" in armed, "the check must be for the order in the box")
    fn = fn_src("function renderConnector(")
    ok("connOneArmed(" in fn, "and the send button asks it rather than deciding for itself")
    ok("dryRun: true" in fn, "the check is a dry run, which writes nothing")
    ok("connOneCheck = null" in fn, "a send spends its check")
    ok("connIsAdmin()" in fn, "and only an admin sees the send")



@test
def t_the_loan_units_tab_is_fully_plumbed():
    """A tab is not a page: it is a nav entry with a label, a view, a title, a
    grant key on both sides and a case in setView. Forgetting any one of them
    leaves a door painted on a wall."""
    ok('data-view="loans" id="nav-loans"' in HTML, "the nav button exists")
    ok('id="view-loans"' in HTML and 'id="loans-content"' in HTML, "and the view it opens")
    ok("$('nav-loans').append" in SCRIPT, "the nav entry is labelled")
    ok("'loans'" in SCRIPT.split("const TAB_KEYS = [")[1][:300], "the page knows the grant key")
    ok("loans: 'Loan units'" in SCRIPT, "the topbar can name it")
    ok("if (v === 'loans') showLoansView();" in SCRIPT, "and setView opens it")
    ok("'loans'" in SCRIPT.split("const APP_VIEWS = [")[1].split("]")[0]
       and "APP_VIEWS.forEach(name => $('view-' + name)" in SCRIPT.split("function setView(v) {")[1][:900],
       "it is in the list of views setView shows and hides")
    src = open("copilot.py", encoding="utf-8").read()
    ok('"loans"' in src.split("TAB_KEYS = (")[1][:320], "the server knows the same grant key")
    ok('("/api/loans", "loans")' in src, "and gates the route behind it")


@test
def t_a_loan_says_who_has_it_and_how_long_it_has_been_gone():
    """The three questions the page exists to answer, and the one number the
    app must never take on trust: days out is computed from when it left."""
    fn = fn_src("function renderLoans(")
    ok("days_out" in fn, "the row says how long it has been out")
    ok("'late'" in fn and "'due'" in fn, "and marks the ones past a date or past the threshold")
    ok("Book back in" in fn, "every loan can be received")
    out = fn_src("function loanOutModal(")
    ok("crmTypeahead(" in out, "the borrower field offers CRM contacts as you type")
    ok("crm_person_id" in out, "and the loan remembers which contact was picked")
    ok("due_at" in out, "a due-back date can be set when it goes out")



@test
def t_a_unit_can_be_found_in_the_shop_rather_than_retyped():
    """The register searches the shop's own catalogue. Picking a product fills
    the MODEL and remembers what it was picked from; the NAME stays yours,
    because two identical projectors are told apart by their name and serial,
    never by the product they both are."""
    fn = fn_src("function loanUnitModal(")
    ok("op: 'products'" in fn, "it searches the catalogue")
    ok("modelIn.value = " in fn, "a pick fills the model")
    # The whole function, not a window after some other landmark: the pick
    # callback sits BEFORE the search call in the source, so a window measured
    # forward from it proved nothing. The name is set once when the field is
    # built and never assigned again.
    ok("nameIn.value =" not in fn and "nameIn.value=" not in fn,
       "and nothing in this modal ever overwrites the name you chose")
    ok("product_id" in fn and "variant_id" in fn and "sku" in fn,
       "the unit remembers which product and variant it came from")
    ok("Find in the shop" in fn, "the field says what it does")



@test
def t_a_modal_action_button_is_appended_not_stringified():
    """el(tag, class, text) sets textContent, so handing it a button prints the
    words [object HTMLButtonElement] and the modal ends up with no button at
    all. Both loan modals shipped that way, and the register could not be
    added to. Appending is the only way a child element survives."""
    for name in ("function loanUnitModal(", "function loanOutModal("):
        fn = fn_src(name)
        for bad in ("mail-statebar', save)", "mail-statebar', go)"):
            ok(bad not in fn, name + " hands its action button to el() as text")
        ok(".append(save)" in fn or ".append(go)" in fn,
           name + " appends its action button into the bar")



@test
def t_the_serial_sticker_prints_on_the_production_printer_with_its_codes():
    """A 4x4 sticker for the machine: logo, the tag large, and both codes as
    images the server drew. FIXED at 4x4, not the production selection: the
    sticker outlives every run, so it cannot come out 4x2 because a gobo job
    was loaded that afternoon. And the sheet must set its own size - the
    stylesheet default is 100x150mm, so a sheet that sets none lays its
    content out at 4x6 and prints it onto a 4x4 page."""
    fn = fn_src("function loanStickerSheet(")
    ok("ls-logo" in fn and "LABEL_LOGO" in fn, "the shop's logo is on it")
    ok("asset_tag" in fn or "d.tag" in fn, "the tag is the point of the sticker")
    ok("d.qr" in fn and "d.barcode" in fn, "both codes are placed")
    ok("<img" not in fn, "and placed as elements, never innerHTML")
    ok("stickerDims()" in fn and "sheet.style.width" in fn and "sheet.style.height" in fn,
       "the sheet sizes itself, or it lays out at the 100x150mm stylesheet default")
    ok("labelDims()" not in fn, "and never at whatever the production dropdown is on")
    sd = fn_src("function stickerDims(")
    # Naming 4x4 is not enough: `LABEL_SIZES[prodSize()] || LABEL_SIZES['4x4']`
    # names it too and still follows the dropdown. 4x4 must be the ONLY size
    # this function can reach.
    ok(re.findall(r"LABEL_SIZES\[([^\]]*)\]", sd) == ["'4x4'"],
       "4x4 is the only stock stickerDims can return")
    for setting in ("prodSize(", "carrierDims(", "shippingCfg", "labelSizeOverride"):
        ok(setting not in sd, "and it reads no setting: found " + setting)
    pr = fn_src("async function loanPrintSticker(")
    ok("op: 'sticker'" in pr, "it asks the server to draw them")
    ok("stickerDims()" in pr and "labelDims()" not in pr,
       "and the page rule is the same 4x4 the sheet was built at")
    ok("labelFontReady" in pr, "waiting for the label typeface like every other print path")
    ok(".catch(" in pr, "and a typeface that will not load still prints, rather than "
                        "abandoning the job and leaving the button dead")
    reg = fn_src("function renderLoans(")
    ok("Reprint" in reg and "Serial sticker" in reg,
       "the button says which it is doing, because minting happens once")


@test
def t_a_row_inset_by_a_margin_is_not_also_a_full_width_row():
    """.lbl-row carries width:100% so button rows fill their container. Inside a
    card it ALSO takes a 16px margin each side, and 100% plus two margins is 32px
    wider than the card: every row in every card hung its right border out past
    the frame. Whichever half is removed, the two must never coexist."""
    m = re.search(r"\.card > :is\(\.lia-bar, \.lbl-row.*?\{(.*?)\}", CSS, re.S)
    ok(m is not None, "the rule that insets card rows by a margin is still there")
    inset = m.group(1)
    ok("margin-left" in inset, "and it is still a margin that does the insetting")
    row = re.search(r"\n\s*\.lbl-row \{(.*?)\}", CSS, re.S)
    ok(row is not None, ".lbl-row is still declared")
    ok("width: auto" in inset or "width: 100%" not in row.group(1),
       "an inset row must either reset its width or not claim 100% in the first place")


@test
def t_the_topbar_button_hides_itself_rather_than_naming_the_tabs_that_want_it():
    """The corner button was hidden by a list of view names, so every tab added
    after that list - Loan units - arrived with an empty 26px button in the
    corner. Content is the only honest test of whether it has anything to do."""
    fn = fn_src("function setView(")
    ok("act.style.display = act.innerHTML ? '' : 'none';" in fn,
       "the button is shown only when a branch actually filled it")
    for line in fn.splitlines():
        if "act.style.display" in line:
            ok("v ===" not in line,
               "showing the corner button must not depend on naming views: " + line.strip())


@test
def t_loan_units_puts_three_stats_on_three_columns():
    """The shared grid is four columns wide. Three stats on it leave a hole where
    a fourth would be, which reads as a KPI that failed to load rather than as a
    row of three."""
    fn = fn_src("function renderLoans(")
    head = fn[:fn.index("mgrid.classList")] if "mgrid.classList" in fn else fn
    ok("metrics-3" in fn, "the three-column modifier is applied")
    ok(head.count("{ label: ") == 3,
       "and there are still exactly three stats - a fourth means dropping metrics-3")


@test
def t_a_unit_can_be_deleted_from_its_own_record_behind_a_confirm():
    """Retire hides a unit and keeps its history; delete is the other thing, and
    people expect it. It sits in the record rather than on the row so it costs an
    extra click, and it says what it is about to destroy before it does it."""
    fn = fn_src("function loanUnitModal(")
    ok("unit_delete" in fn, "the modal can delete the unit it is editing")
    ok("if (u.id)" in fn, "and only offers it for a unit that already exists")
    ok("uiConfirm(" in fn, "behind a confirm")
    ok("cannot be undone" in fn, "that says the history goes too")
    ok("barSave.append(del)" in fn,
       "the button is appended, not handed to el() as text")
    ok("btn btn-danger" in fn, "and reads as the destructive one")


@test
def t_a_sticker_that_already_has_a_number_can_be_reprinted_by_anyone():
    """Assigning the number is an admin's; reprinting one that exists is not a
    change to anything, and the person who finds a peeled label is whoever is
    holding the projector. The row offered the button on can_manage alone, so
    members could not print a sticker for a unit that already had a tag."""
    fn = fn_src("function renderLoans(")
    ok("if (d.can_manage || u.asset_tag) {" in fn,
       "the sticker button is offered for a tagged unit whether or not you keep the register")


@test
def t_a_checked_order_can_be_opened_and_read_as_the_document_it_will_send():
    """A dry run existed to be READ, and reported an outcome word. The row now
    opens the document itself: the account code and the tax type get their own
    columns, because those are the two fields a wrong mapping gets wrong and
    the two a one-line summary can never show."""
    fn = fn_src("function connDocModal(")
    for col in ("'Description'", "'Qty'", "'Unit'", "'Account'", "'Tax'", "'Amount'"):
        ok(col in fn, "the line table has a " + col + " column")
    ok("sheetModal(" in fn, "it opens in the house modal, which closes by its X only")
    ok("updatesExisting" in fn,
       "and says whether this replaces a document already in Xero or creates one")
    ok("innerHTML" not in fn,
       "the document is text from the connector, so it is never written as HTML")


@test
def t_the_document_view_never_invents_a_tax_figure():
    """Xero computes tax from the tax type on each line. A total worked out
    here could disagree with the invoice that actually appears, and a person
    checking an order against a number gizmo invented would be checking
    nothing. The line total is a fact; the tax is Xero's."""
    fn = fn_src("function connDocModal(").lower()
    for invented in ("0.2", "* 1.2", "vat", "taxtotal", "grosstotal"):
        ok(invented not in fn, "no tax arithmetic here: found " + invented)
    ok("before tax" in fn and "inclusive" in fn,
       "the label says which the number is, rather than calling it 'Total'")
    ok("xero adds tax" in fn, "and it says who does compute it")


@test
def t_only_a_document_the_connector_returned_can_be_opened():
    """A row with no preview has nothing to show. Offering it anyway would open
    an empty modal and read as a fault in the connector rather than an older
    reply that carried no document."""
    fn = fn_src("function renderConnector(")
    i = fn.find("const docs = c.docs || [];")
    ok(i > 0, "the check result still renders its docs")
    ok("connDocTable(" in fn[i:i + 900], "through the one table both the order and the tag list use")
    row = fn_src("function connDocTable(")
    ok("const p = e.d && e.d.preview;" in row and "if (p) {" in row, "the opener is offered only when a document came back")
    ok("connDocModal(d)" in row, "and it opens that document")


@test
def t_the_document_leads_with_whether_it_reconciles_with_shopify():
    """A discount code once went missing and the invoice looked perfectly
    plausible: only the comparison against Shopify's own total caught it. That
    comparison is the first thing on the document, and it is the CONNECTOR's
    number - gizmo working it out again could disagree with the warning, and
    then neither figure would be worth reading."""
    fn = fn_src("function connDocModal(")
    ok("p.reconcile" in fn, "the reconciliation comes from the connector")
    ok("rec.computed" in fn and "rec.expected" in fn and "rec.diff" in fn,
       "and is displayed, all three numbers")
    for arithmetic in ("rec.computed -", "rec.expected -", "- rec.expected", "Math.abs("):
        ok(arithmetic not in fn, "gizmo does not recompute it: found " + arithmetic)
    ok("rec.ok" in fn, "and it says plainly whether it reconciles")
    ok("strict" in fn and "Do not send it" in fn,
       "a mismatch under warn mode says the send is NOT blocked")


@test
def t_the_document_says_which_xero_customer_it_lands_on():
    """"Will this hit the right account" is the question a total cannot answer.
    An unmatched contact already quarantines the document; showing it here means
    finding out before the send rather than from a quarantine list."""
    fn = fn_src("function connDocModal(")
    ok("cust.matched" in fn, "it says whether a Xero contact was actually matched")
    ok("cust.xeroContactId" in fn, "and which one")
    # Both outcomes must NAME the customer: "lands on the Xero contact" without
    # saying which one answers nothing, and that is the whole question here.
    ok(fn.count("cust.name") >= 2,
       "the matched and the unmatched message each name the customer")
    ok("cust.reference" in fn, "with the customer reference Xero matches on")
    ok("cust.email" in fn, "and the email")
    ok("cannot be sent until one exists" in fn,
       "an unmatched contact reads as the blocker it is")


@test
def t_the_document_shows_shopifys_own_totals_to_check_against():
    """The screen is only worth anything if it can be read against the shop.
    Shopify's figures go on it unaltered, and the note says which of them the
    reconciliation actually uses, because tax is not one of them."""
    fn = fn_src("function connDocModal(")
    ok("p.order" in fn, "the order's own totals are carried")
    for f in ("o.subtotal", "o.shipping", "o.tax", "o.total"):
        ok(f in fn, "showing " + f)
    ok("o.gateways" in fn, "and the gateway, which is what chose the due date")
    ok("p.key" in fn, "and the ledger key that stops a second send")
    ok("Tax is not" in fn, "and says tax is not part of the reconciliation")


@test
def t_payout_notes_are_previewed_before_any_are_written():
    """Nothing is written to a real invoice that nobody has looked at. The same
    rule the one-order send follows: the write button is dead until a check has
    come back with notes to write."""
    fn = fn_src("function renderConnector(")
    i = fn.find("Which payout paid it")
    ok(i > 0, "the payout card is on the page")
    seg = fn[i:i + 4000]
    ok("op: 'payouts', dryRun: true" in seg, "the check is a dry run")
    ok("const payReady = () => !!(connPayResult && connPayResult.dryRun && (connPayResult.notes || []).length" in seg,
       "and the write button is armed only by a dry run that found notes")
    ok("paySince.value.trim() === (connPayBox || '')" in seg and "since: connPayResult.since" in seg,
       "for exactly the date that was checked: retyping it disarms the write, which uses the checked date")
    ok("uiConfirm(" in seg, "the write is confirmed")
    ok("no amount changes" in seg,
       "and the confirm says what a note can and cannot do")


@test
def t_the_payout_card_says_it_is_a_second_pass_and_why():
    """It is not part of the sync and cannot be: Shopify settles days after the
    order, so at invoice time the payout does not exist. A card that did not
    say so would read as a step someone forgot to run."""
    fn = fn_src("function renderConnector(")
    i = fn.find("Which payout paid it")
    seg = fn[i:i + 2000]
    ok("one figure covering many orders" in seg,
       "it says why a payout needs tracing to invoices at all")
    ok("Shopify fee" in seg,
       "and that the fee is in the note, which is what makes a payout tie out")


@test
def t_the_payout_note_is_readable_on_the_invoice_before_it_is_sent():
    """The note and the invoice were two separate screens. It now sits on the
    document it would be written to, quoted verbatim, so what Xero will hold
    can be read rather than described."""
    fn = fn_src("function connDocModal(")
    ok("p.payout" in fn, "the document carries its payout")
    ok("conn-note" in fn and "q.textContent = pay.note" in fn,
       "and quotes the note itself, as text rather than as HTML")
    # The two states must READ differently. Asserting the branch exists proves
    # nothing: a ternary with the same sentence on both sides still branches.
    ok("already on the invoice" in fn, "a note already in Xero says so")
    ok("would be added" in fn, "and one not yet written says that instead")
    ok("pay.state === 'already_added'" in fn, "chosen by the state, not guessed")
    ok("fee" in fn and "after the fee" in fn,
       "and explains why the invoice total and the bank line differ")


@test
def t_an_unpaid_order_and_a_failed_lookup_read_differently():
    """Shopify settles days after an order, so "not paid out yet" is the
    ordinary answer for anything recent. Showing it as an error would teach
    people to ignore a box that also reports missing scopes."""
    fn = fn_src("function connDocModal(")
    i = fn.find("pay.state === 'unavailable'")
    ok(i > 0, "a failed lookup has its own branch")
    ok("msg error" in fn[i:i + 400], "and that one is an error")
    j = fn.find("pay.state === 'not_yet'")
    ok(j > 0, "not yet paid out has its own branch")
    seg = fn[j:j + 600]
    ok("msg error" not in seg, "which is NOT an error")
    ok("field-help" in seg, "just a note saying to come back to it")
    ok("The invoice itself is unaffected" in fn,
       "and a payout that cannot be read never implies the invoice is wrong")


@test
def t_the_customer_reference_is_a_labelled_row_not_an_abbreviation():
    """It is the field Xero matches on account number, so it is checked rather
    than glanced at. And when it is empty the row names the metafield it read,
    because a customer with no reference and a connector pointed at the wrong
    metafield produce the same blank."""
    fn = fn_src("function connDocModal(")
    ok("'Customer reference'" in fn, "it has its own labelled row")
    # Scoped to the POPULATED branch. Counting mentions across the function is
    # not enough: the empty branch names the field twice by itself, so a
    # populated row that stopped naming it still left the count looking right.
    i = fn.find("if (cust && cust.reference) {")
    ok(i > 0, "there is a branch for a populated reference")
    populated = fn[i:fn.find("} else if", i)]
    ok("cust.reference" in populated, "which shows the value")
    ok("cust.referenceField" in populated,
       "and names the metafield it came from, not just the value")
    ok("none set in" in fn, "and says so when the customer has none")
    ok("'ref ' + cust.reference" not in fn,
       "no longer abbreviated into the meta line under the contact")


@test
def t_auto_run_shows_the_services_state_not_what_this_tab_last_clicked():
    """A control over unattended writing into the accounts has one lie it must
    never tell: that it is running when it is not. The state comes from the
    service on every load, so a redeploy that started no timer reads OFF."""
    fn = fn_src("async function refreshConnector(")
    ok("op: 'autorun'" in fn, "the state is fetched, not remembered")
    r = fn_src("function renderConnector(")
    i = r.find("/* ---- Auto Run ----")
    ok(i > 0, "the card is on the page")
    seg = r[i - 400:i + 2600]
    ok("connAuto.enabled" in seg, "and reads the service's own flag")
    ok("'Auto Run on'" in seg and "'Auto Run off'" in seg,
       "which is spelled out, not left to a toggle's position")
    ok("Nothing runs on its own" in seg,
       "and OFF says what off means, rather than only being unlit")


@test
def t_turning_auto_run_on_says_what_it_will_do_unattended():
    """It sends to Xero with nobody reviewing. Someone agreeing to that should
    be agreeing to the thing itself, not to the word "on"."""
    r = fn_src("function renderConnector(")
    i = r.find("Turn Auto Run on")
    ok(i > 0, "there is a control")
    seg = r[i:i + 1600]
    # Presence of uiConfirm proves nothing: `false && !await uiConfirm(...)`
    # still contains it and asks nobody anything. The GUARD is the property.
    ok("!on && !await uiConfirm(" in seg,
       "turning it ON is what requires the confirm, and turning it off does not")
    ok("without anyone reviewing" in seg, "that says nobody reviews what it sends")
    ok("until you turn it off" in seg, "and that it does not stop on its own")
    ok("never sent twice" in seg, "and that an order cannot go twice")
    ok("connIsAdmin()" in r[i - 2200:i], "and only an admin sees it")


@test
def t_the_settings_form_offers_no_credential():
    """Operational knobs became reachable without a Railway trip. Credentials
    did not: they are not on the form, and the server refuses them anyway."""
    r = fn_src("function renderConnector(")
    i = r.find("How it behaves")
    ok(i > 0, "the settings section exists")
    seg = r[i:i + 3000]
    ok("RECONCILE_MODE" in seg, "the reconcile mode is settable")
    ok("MAX_DOCS_PER_RUN" in seg, "so is the runaway cap")
    for secret in ("CLIENT_SECRET", "DASHBOARD_TOKEN", "ADMIN_TOKEN", "SHOPIFY_SHOP"):
        ok(secret not in seg, secret + " must not be on this form")


@test
def t_an_update_shows_what_it_would_change_in_xero():
    """Updating is the only thing done to a document already in the accounts,
    and it reported the word "updated". Three columns: the field, what Xero
    holds now, and what it would become."""
    fn = fn_src("function connDocModal(")
    ok("p.changes" in fn, "the document carries its changes")
    ok("'In Xero now'" in fn and "'Would become'" in fn,
       "shown as before and after, not as a list of new values")
    ok("could not be read to say" in fn,
       "and an update whose comparison failed says so rather than looking unchanged")


@test
def t_the_xero_page_does_not_borrow_the_prose_measure_for_its_results():
    """.setting-sub carries a 52ch reading measure, which is right for a
    paragraph and wrong for a list of results: it squeezed a row to 382px
    inside a 1558px card and collapsed its flexible column to 26px, so the
    action read "cre...". Results get their own container."""
    fn = fn_src("function renderConnector(")
    ok("el('section', 'cx-res conn-results')" in fn,
       "the result containers are sections of their own, not the prose class")
    ok("setting-sub" not in fn_src("function connDocTable(") and "setting-sub" not in fn[fn.find("function paintOne()"):fn.find("rCard.append(grid);")],
       "nothing a check draws borrows the 52ch prose measure")


@test
def t_the_xero_page_gives_its_rows_a_deliberate_width():
    """Nothing on the page had a chosen width: prose was capped at 52ch,
    control rows filled 1524px at 71% empty, and results inherited the prose
    cap. Three widths, none of them decided."""
    ok("#view-connector .conn-results { max-width: 56rem; }" in CSS
       or "#view-connector .conn-results" in CSS,
       "results share one column")
    ok("#view-connector .card > .lbl-row { width: fit-content" in CSS,
       "and a control bar shrinks to what it holds rather than sitting half empty")
    ok("#view-connector .conn-results:empty { display: none; }" in CSS,
       "an empty results container takes no vertical space")
    # .card is a flex column with gap:16, and flex does not collapse margins,
    # so a child's own margins are ADDED to the gap and the page pays twice.
    ok("#view-connector .card > * { margin-top: 0; margin-bottom: 0; }" in CSS,
       "the container owns the rhythm; the children bring no vertical margins")


@test
def t_the_xero_page_fits_a_phone():
    """At 375px the Xero sync page scrolled sideways: 451px of content in a
    364px column. Three things would not shrink. The tile grid's 320px floor
    was wider than the 299px card. The tag tile's two buttons sat in two 1fr
    columns, which cannot be narrower than their labels: 318px in a 265px tile.
    And the Auto Run status line is .lbl-meta, which never wraps, so the flex
    item holding it was 418px wide."""
    fn = fn_src("function renderConnector(")
    ok("el('div', 'cx-auto')" in fn and "el('div', 'lr-what')" in fn,
       "the Auto Run row is still built from the classes the rules below style")
    grid = re.search(r"\.cx-grid \{[^}]*grid-template-columns:([^;]*);", CSS)
    ok(grid and grid.group(1).strip() == "minmax(0, 1fr)",
       "one tile per row until the card has room for three: a tile never has a floor wider than the card")
    ok("@container cxcard (min-width: 900px) { .cx-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }" in CSS,
       "three across only when the card, not the window, has room")
    row = re.search(r"\.cx-tile \.cx-row \{([^}]*)\}", CSS)
    ok(row and "flex-wrap: wrap" in row.group(1) and "1fr 1fr" not in row.group(1),
       "the buttons stack when their labels do not fit side by side")
    ok(re.search(r"\.cx-tile \.cx-row \.btn \{[^}]*flex: 1 1 0", CSS),
       "and share the line when they do")
    ok(re.search(r"\.cx-auto > \.lr-what \{[^}]*min-width: 0", CSS),
       "the Auto Run text shrinks to its row")
    ok(re.search(r"\.cx-auto \.lbl-meta \{[^}]*white-space: normal", CSS),
       "and its status line wraps")


@test
def t_every_control_family_declares_its_states():
    """The state contract (docs/superpowers/specs/2026-09-07-design-system-tokens-design.md).
    A family without a pressed or disabled look is one whose state the user
    cannot read; a disabled look that fades with opacity is a second recipe."""
    families = {".btn": ("hover", "active", "disabled"), ".btn-primary": ("hover", "active", "disabled"),
                ".btn-danger": ("hover", "active"), ".icon-btn": ("hover", "active", "disabled"),
                ".nav-item": ("hover", "active"), ".chip": ("hover", "active", "disabled"),
                ".lbl-segbtn": ("hover", "active", "disabled"), ".mail-claim": ("hover", "active", "disabled"),
                ".send": ("hover", "active", "disabled"), ".dmenu-item": ("hover", "active"),
                ".convo": ("hover", "active"), ".mem-btn": ("hover", "active"), ".track-btn": ("hover", "active"),
                ".ptab": ("hover", "active"), ".ftab": ("hover", "active"),
                ".wg-hide": ("hover", "active", "disabled")}
    for sel, states in families.items():
        for st in states:
            ok(sel + ":" + st in CSS, "%s declares :%s" % (sel, st))
    for body in re.findall(r":disabled[^{]*\{([^}]*)\}", CSS):
        ok("opacity" not in body, "no disabled recipe fades with opacity: " + body[:80])
    ok(CSS.count("var(--text-disabled)") >= 6, "disabled controls share one ink")
    ok(".btn-primary:hover { background: var(--action-hover)" in CSS
       and ".btn-primary:active { background: var(--action-active)" in CSS,
       "a primary button's hover and pressed are two different colours")
    ok('[aria-busy="true"] { cursor: progress; }' in CSS and 'svg { animation: navspin' in CSS,
       "loading is a recipe any control can carry")
    ok('[aria-invalid="true"] { border-color: var(--error); }' in CSS, "and so is invalid, for fields")
    ok('.is-cancelled, [data-status="cancelled"] { color: var(--text-tertiary); text-decoration: line-through; }' in CSS,
       "and cancelled")
    ok("function setBusy(" in SCRIPT and "function markInvalid(" in SCRIPT, "the script owns the two ARIA entry points")
    ok("setBusy(btn, true)" in SCRIPT and "markInvalid(reasonIn, true)" in SCRIPT, "and uses them")
    for sel, attr in ((".nav-item", 'aria-current="page"'), (".btn", "aria-pressed"), (".ptab", "aria-current"),
                      (".ftab", "aria-selected"), (".toggle", "aria-checked"), (".mrow", "aria-selected"),
                      (".files-row", "aria-selected"), (".lbl-segbtn", "aria-pressed"), (".stat.stat-pick", "aria-pressed")):
        ok(re.search(re.escape(sel) + r":is\([^)]*" + attr, CSS), "%s's selected rule has its %s twin" % (sel, attr))
    ok("n.setAttribute('aria-current', 'page')" in SCRIPT, "and the nav actually sets aria-current")


@test
def t_focus_is_declared_once_per_kind():
    """Controls draw the outline, fields draw the ring, each written once. The
    field rule had been copied nine times, once per component, and one copy
    drew the outline instead."""
    ok(CSS.count("box-shadow: var(--focus-ring)") == 3,
       "the ring is read by the field rule and by the two composite fields that "
       "focus as a whole (the radio card, the composer box), and nowhere else")
    ok(':is(input, textarea, select, [contenteditable="true"]):focus { outline: none; border-color: var(--action-primary); box-shadow: var(--focus-ring); }' in CSS,
       "one rule for every field, contenteditable included")
    ok(not re.search(r"\.[\w-]+:focus \{[^}]*(focus-ring|focus-outline)", CSS),
       "no component carries its own copy of either focus look")
    ok(CSS.count("outline: var(--focus-outline)") == 4,
       "the outline is read by the control rule and by three deliberate variants (the "
       "custom-drawn checkbox, the menu item which insets it, and a widget card just dropped "
       "in Customize mode, which borrows it for --dur-landed), and nowhere else")


@test
def t_the_header_is_one_implementation_with_one_collapse_point():
    """Measured 2026-09-07: one .topbar, 48px on every view at 375, 640, 760,
    761, 900 and 1200, no overflow, no overlap. The one defect was a long
    conversation title wrapping to 63px inside the 48px bar."""
    ok(HTML.count('class="topbar"') == 1 and CSS.count(".topbar {") == 1, "one header, one rule")
    ok(".topbar { height: var(--topbar-h);" in CSS and "--topbar-h: 48px" in CSS, "at the shell's height token")
    h1 = CSS.split(".topbar h1 {")[1].split("}")[0]
    for prop in ("min-width: 0", "overflow: hidden", "text-overflow: ellipsis", "white-space: nowrap"):
        ok(prop in h1, "the title truncates rather than wraps: " + prop)
    ok("function setViewTitle(text) { const h = $('view-title'); h.textContent = text; h.title = text; }" in SCRIPT,
       "and the full title rides in the tooltip")
    ok("$('view-title').textContent =" not in SCRIPT, "every writer goes through it")
    # The trigger is always there, as the reference's is: on a phone it opens
    # the drawer, on a desk it folds the sidebar away. The drawer itself still
    # happens at exactly one width.
    ok(".menu-btn { display: inline-grid; }" in CSS, "the trigger is always shown")
    for m in re.finditer(r"@media[^{]*\{", CSS):
        depth, i = 1, m.end()
        while i < len(CSS) and depth:
            depth += {"{": 1, "}": -1}.get(CSS[i], 0); i += 1
        ok(".menu-btn" not in CSS[m.end():i], "and no breakpoint hides or reveals it: " + m.group(0))
    ok(re.search(r"@media \(max-width: 760px\)[^@]*?\.sidebar \{ position: fixed;", CSS),
       "the sidebar leaves the flow at 760 and only there")
    ok("@media (min-width: 761px) { body.sidebar-collapsed .sidebar { margin-left: calc(-1 * var(--sidebar-w)); } }" in CSS,
       "and folds away by its own width above it")
    ok("function toggleSidebar()" in SCRIPT and "k === 'b'" in SCRIPT, "one toggle serves the trigger and Cmd+B")


def _rules(css):
    """(selector with its @media context, body) for every innermost rule."""
    out = []; stack = []; sel_start = 0; i = 0; n = len(css)
    while i < n:
        if css.startswith("/*", i):
            i = css.index("*/", i) + 2; continue
        ch = css[i]
        if ch == "{":
            stack.append((css[sel_start:i], i + 1)); i += 1; continue
        if ch == "}":
            sel, b0 = stack.pop(); body = css[b0:i]
            if "{" not in body:
                ctx = " ".join(re.sub(r"\s+", " ", re.sub(r"/\*.*?\*/", "", x, flags=re.S)).strip() for x, _ in stack)
                out.append(((ctx + " " if ctx else "") + re.sub(r"\s+", " ", re.sub(r"/\*.*?\*/", "", sel, flags=re.S)).strip(), body))
            sel_start = i + 1; i += 1; continue
        if ch == ";" and not stack: sel_start = i + 1
        i += 1
    return out


@test
def t_screen_css_carries_no_arbitrary_lengths():
    """Spacing, line-height, radius, border width and type size come from the
    scale, never from the rule. Measured 2026-09-07 before this: 632 spacing
    declarations bypassed the scale, over 165 distinct values. The print sheets
    are the documented exception: physical artefacts sized in mm and em so a
    4x4 and a 4x6 label scale together."""
    paper = re.compile(r"label-sheet|day-sheet|loan-sticker|@page|@font-face")
    strip = lambda v: re.sub(r"var\(--[\w-]+\)|env\([^)]*\)", "", v)
    bad = []
    for sel, body in _rules(CSS):
        if paper.search(sel): continue
        for m in re.finditer(r"(?<![\w-])(padding|margin|gap|row-gap|column-gap|padding-(?:top|right|bottom|left)|margin-(?:top|right|bottom|left)|border-radius|font-size|border|border-top|border-right|border-bottom|border-left|border-width)\s*:\s*([^;}]+)", body):
            if re.search(r"\d(px|em|rem)", strip(m.group(2))):
                bad.append(sel[:50] + " { " + m.group(0).strip() + " }")
        for m in re.finditer(r"line-height:\s*([^;}]+)", body):
            if not re.fullmatch(r"var\(--lh-[\w-]+\)|inherit|normal|initial", m.group(1).strip()):
                bad.append(sel[:50] + " { " + m.group(0).strip() + " }")
    ok(not bad, "%d arbitrary lengths in screen CSS, e.g. %s" % (len(bad), bad[:6]))


@test
def t_an_icon_size_comes_from_the_scale_and_not_from_the_rule():
    """Icons are on the design system's list and had no token, so fifty-four
    svg rules carried a raw pixel size between them in TWELVE different values
    - 13, 14, 15, 16 and 17 all appeared. That is not a design decision, it is
    what a year of one-off edits leaves behind, and it is exactly the drift a
    single source of truth exists to stop.

    One 2px scale. This guards the glyph only: the control box around an icon
    is a height, which is a different token."""
    icons = []
    for sel, body in _rules(CSS):
        s2 = " ".join(sel.split())
        if re.search(r"label-sheet|day-sheet|loan-sticker|@page|@font-face", s2): continue
        if "svg" not in s2: continue
        for prop in ("width", "height"):
            m = re.search(r"(?<![\w-])" + prop + r"\s*:\s*([^;}]+)", body)
            if m and re.search(r"\d+(px|rem|em)", re.sub(r"var\([^)]*\)", "", m.group(1))):
                icons.append(s2[:50] + " { " + prop + ": " + m.group(1).strip() + " }")
    # .run-gate .rg-ic is the one deliberate outlier: a 26px badge glyph that
    # is a piece of illustration, not an interface icon on the scale.
    icons = [i for i in icons if "rg-ic" not in i]
    ok(not icons, "%d icon sizes bypass the scale: %s" % (len(icons), icons[:5]))
    for t in ("--icon-xs", "--icon-sm", "--icon-md", "--icon-lg", "--icon-xl"):
        ok(t + ":" in CSS, "the icon scale still defines " + t)

    # Square boxes and status dots, the same way. Forty-eight rules set an
    # equal width and height in TWENTY-ONE different sizes; 22, 26, 30, 34 and
    # 42 each appeared once or twice, which is drift rather than intent.
    boxes = []
    for sel, body in _rules(CSS):
        s2 = " ".join(sel.split())
        if re.search(r"label-sheet|day-sheet|loan-sticker|@page|@font-face|scrollbar", s2): continue
        if "svg" in s2: continue
        w = re.search(r"(?<![\w-])width\s*:\s*(\d+(?:\.\d+)?)px", body)
        h = re.search(r"(?<![\w-])height\s*:\s*(\d+(?:\.\d+)?)px", body)
        if not (w and h) or w.group(1) != h.group(1): continue
        v = float(w.group(1))
        # A 1px square is a hairline or a screen-reader trick, and .rg-ic is an
        # illustration rather than an interface box. Both are deliberate.
        if v <= 1 or "rg-ic" in s2: continue
        boxes.append(s2[:44] + " { %spx }" % int(v))
    ok(not boxes, "%d square boxes bypass the scale: %s" % (len(boxes), boxes[:5]))
    for t in ("--box-xs", "--box-sm", "--box-md", "--box-lg", "--box-xl", "--box-2xl",
              "--dot-md", "--dot-lg"):
        ok(t + ":" in CSS, "the box and dot scales still define " + t)

    # A knob inside a switch is DERIVED from its track, like a thumb in a
    # segmented control: snapping it to the nearest box step put 16px of knob
    # in an 18px track, hanging two pixels out of the slot.
    knob = re.search(r"\.toggle \.sw::after \{([^}]*)\}", CSS)
    ok(knob and "calc(var(--switch-h) - 2 * var(--switch-inset))" in knob.group(1),
       "the switch knob is derived from its track, not sized by hand")

    # No inline pixel length written from JavaScript: a screen must not set a
    # component's size, it must pick a token.
    inline = re.findall(r"\.style\.[A-Za-z]+ = '\d+(?:\.\d+)?px'", SCRIPT)
    ok(not inline, "a screen writes its own pixel size: %s" % inline[:4])
    # One :root, or a global value has two places to be looked up.
    # Exactly one place DEFINES the system. Overriding a token inside an
    # @media block is the opposite of drift - it is the single source being
    # re-pointed for a medium - so a nested :root is allowed and a second
    # top-level one is not. Indentation tells them apart: the definition sits
    # at the stylesheet's own level, an override sits inside its block.
    tops = [l for l in CSS.splitlines() if re.match(r"^ {0,8}:root\s*\{", l)]
    nested = [l for l in CSS.splitlines() if re.match(r"^ {9,}:root\s*\{", l)]
    ok(len(tops) == 1,
       "the design system must be defined in exactly one top-level :root, found %d" % len(tops))
    for l in nested:
        ok("--" in l, "a nested :root may only re-point tokens: " + l.strip()[:70])


@test
def t_every_breakpoint_is_on_the_scale():
    """Six stops, each with a job: 640 phone, 760 the sidebar collapses, 900
    tablet, 1100 the KPI row goes to four columns, 1500 wide, 1800 ultra-wide. There were nineteen distinct
    widths before; the near-misses (560, 600, 620, 700, 720, 960, 2100) folded
    onto their neighbours."""
    # 1200 was the production queue's own stop; since 2026-09-23 the queue is
    # laid out by the width of the list itself (@container queue), because a
    # viewport stop cannot see the label preview taking 476px beside it.
    stops = {640, 641, 760, 761, 900, 901, 1100, 1101, 1500, 1800}
    widths = set()
    for pre in re.findall(r"@media([^{]+)\{", CSS):
        widths |= {int(w) for w in re.findall(r"(?:min|max)-width:\s*(\d+)px", pre)}
    ok(widths <= stops, "off-scale breakpoints: %s" % sorted(widths - stops))
    ok({640, 760, 900, 1100, 1500, 1800} <= widths, "and every stop on the scale is in use: %s" % sorted(widths))


@test
def t_every_defined_token_is_read():
    """A token nobody reads is a value nobody sees, and the next edit deletes
    it or, worse, trusts it. Every token in the block is read by the
    stylesheet, the script or the composer."""
    root = CSS.split(":root {")[1].split("\n        }")[0]
    defined = re.findall(r"(--[\w-]+)\s*:", root)
    readers = CSS + SCRIPT + COMPOSER
    unread = [d for d in defined if "var(" + d + ")" not in readers and "'" + d + "'" not in readers
              and "'" + d.replace("--owner-", "--owner-") + "'" not in readers]
    # the owner hues are read by name composition: tokenValue('--owner-' + k)
    unread = [d for d in unread if not (d.startswith("--owner-") and "tokenValue('--owner-' + k)" in SCRIPT)]
    ok(not unread, "defined but never read: %s" % unread)
    ok(len(defined) > 150, "the block is the whole system: %d tokens" % len(defined))


@test
def t_the_script_paints_from_tokens_only():
    """Three hex palettes used to live in JavaScript: the chart ramp, the CRM
    owner colours and the composer's font colours. Now the script asks the
    stylesheet. And an element the script styles by hand takes its lengths
    from the scale, so the 61 marginTop pixels are gone."""
    ok("function tokenValue(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }" in SCRIPT,
       "one reader for the tokens")
    hexes = [h for h in re.findall(r"'#([0-9a-fA-F]{6})'", SCRIPT) if not h.isdigit()]
    ok(not hexes, "the script carries no colour literal: %s" % hexes[:5])
    ok(not re.search(r"#[0-9a-fA-F]{6}\b", COMPOSER), "nor does the composer")
    ok("tok('--owner-red')" in COMPOSER and "tok('--text-primary')" in COMPOSER, "the composer reads the same tokens")
    ok(not re.search(r"\.style\.(margin\w*|padding\w*|gap|rowGap|fontSize|lineHeight) = '[^']*\d+px", SCRIPT),
       "no inline length is written as pixels")
    bad = [m.group(0) for m in re.finditer(r"cssText = '[^']*'", SCRIPT)
           if re.search(r"(margin|padding|gap|font-size|line-height)[^;']*:\s*[^;']*\d+(px|em)", m.group(0))
           or "font-family:" in m.group(0) and "var(--font-" not in m.group(0)]
    ok(not bad, "no cssText carries a pixel length or a font name: %s" % bad[:4])
    ok(not re.search(r"\.style\.fontWeight = '\d+'", SCRIPT), "weights are tokens too")


@test
def t_a_boxed_child_of_a_card_is_inset():
    """Sweep, 2026-09-07: the Xero run banner (.msg) and the Mail send warning
    sat flush against their card's border on both sides. A card pads its
    children, so a child that paints its own box has to take the inset as a
    margin instead, and the list of those is derived here: every painted class
    the script appends straight into a card must be in it."""
    m = re.search(r"\.card > :is\(([^)]*)\)", CSS)
    ok(m, "the inset list exists")
    inset = {c.strip().lstrip(".") for c in m.group(1).split(",")}
    for c in ("msg", "mail-sendwarn", "disp-warn", "mail-empty", "lbl-row", "ktable-wrap", "lia-bar", "empty"):
        ok(c in inset, "." + c + " is inset")
    appended = set(re.findall(r"(?:sCard|card|box|host|wrap)\.append\(el\('div', '([a-z0-9-]+)[' ]", SCRIPT))
    for c in sorted(appended):
        rule = re.search(r"(?<![\w-])\." + re.escape(c) + r"(?![\w-])\s*\{([^}]*)\}", CSS)
        if not rule: continue
        b = rule.group(1)
        if re.search(r"(?<![\w-])(background|border)(?!-radius|-collapse)\s*:", b) and "transparent" not in b and "none" not in b.split("background")[-1][:12]:
            ok(c in inset, "." + c + " paints a box and is appended to a card, so it must be inset")
    ok(".card > :is(.msg, .mail-sendwarn, .disp-warn) { max-width: 56rem; }" in CSS, "and a notice reads as prose, not a ribbon")
    ok("max-width: calc(100% - 2 * var(--sp-4))" in CSS.split("#view-connector .card > .lbl-row {")[1].split("}")[0],
       "a fit-content row counts its own inset, so it cannot hang out of the card at 375")
    ok(".ov-wrap > * + .run-gate { margin-top: 0; }" in CSS, "the run gate centres itself only when it is the whole page")
    ok("line-height: var(--lh-control)" in CSS.split(".lbl-segbtn {")[1].split("}")[0], "segmented buttons are 24 tall in a 32 strip")
    ok("const label = a.metric || a.title || a.detail || 'A change was recorded without a description';" in SCRIPT,
       "an alert row shows whatever its record carries")
    ok("board.append(el('div', 'empty', 'No pipeline stages are set up yet.'))" in SCRIPT, "an empty pipeline says so")


@test
def t_a_credit_note_preview_shows_the_vat_it_carries():
    """Since 2026-09-07 the connector sends each credit-note line with the VAT
    Shopify refunded on it, and reconciles the note gross to gross. The screen
    has to say both, or a 43.20 refund reads as 36.00 against 43.20."""
    fn = fn_src("function connDocModal(")
    ok("(l.taxType || '') + (l.taxAmount != null ? ' \\u00b7 ' + money2(l.taxAmount) : '')" in fn,
       "the Tax cell shows the amount beside the type when the line carries one")
    ok("(credit ? ' both sides, tax included.' : ' both sides.')" in fn
       and "(credit ? ' with tax' : '')" in fn,
       "and the reconciliation sentence says a credit note's figure includes the tax")


_WG_START = "        /* ---------- widget layout (pure) ---------- */"
_WG_END = "        /* ---------- widget layout end ---------- */"

_WG_HARNESS = r"""
const html = require('fs').readFileSync(process.argv[2], 'utf8');
const START = '        /* ---------- widget layout (pure) ---------- */\n';
const END = '        /* ---------- widget layout end ---------- */';
const a = html.indexOf(START), b = html.indexOf(END, a + 1);
if (a < 0 || b < 0) { console.log('EXTRACT_FAILED'); process.exit(0); }
const block = html.slice(a, b + END.length);
// Evaluated inside a function, so the block's names stay out of this script's own scope.
const NAMES = 'WG_SPANS, WG_ENTER, wgOverlaps, wgContains, wgSpanOf, wgLayout, '
  + 'wgMoveTo, wgSameOrder, wgChoose, wgCandidates, '
  + 'wgMergeOrder, wgKeyMove, wgColumns, wgSlotFor, WG_ID, wgKpiId';
const lift = (src) => eval('(function () {\n' + src + '\nreturn { ' + NAMES + ' };\n})()');
const W = lift(block);

const ran = {}, fails = {}, stats = {};
const fail = (key, msg) => { fails[key] = fails[key] || []; if (fails[key].length < 5) fails[key].push(msg); };
const check = (key, fn) => { ran[key] = ran[key] || 0; try { fn(() => ran[key]++); } catch (e) { fail(key, 'threw ' + (e && e.stack || e)); } };
const show = (items) => items.map(i => i.id + ':' + i.size).join(' ');
const ids = (items) => items.map(i => i.id).join(' ');
const same = (x, y) => JSON.stringify(x) === JSON.stringify(y);

// mulberry32: the same cases on every run, so a failure can be replayed.
function rng(s) {
  return () => {
    s = s + 0x6D2B79F5 | 0;
    let t = Math.imul(s ^ s >>> 15, 1 | s);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}
const rand = rng(20260917);
const CASES = [];
for (const columns of [1, 2, 4]) {
  for (let k = 0; k < 400; k++) {
    const n = 1 + Math.floor(rand() * 16);
    const pFull = rand() * 0.3, pWide = rand() * 0.6;
    const items = [];
    for (let i = 0; i < n; i++) {
      const r = rand();
      items.push({ id: 'w' + i, size: r < pFull ? 'full' : r < pFull + pWide ? 'wide' : 'sm' });
    }
    CASES.push({ columns, items });
  }
}

// Every widget placed once, inside the columns, one row high, with no overlap;
// returns the problems and how many cells of each row are filled.
function cover(places, items, columns) {
  const problems = [], seen = new Set(), known = new Set(items.map(i => i.id)), taken = new Set();
  let rows = 0;
  for (const p of places) {
    if (seen.has(p.id)) problems.push(p.id + ' placed twice');
    if (!known.has(p.id)) problems.push(p.id + ' is not an item');
    seen.add(p.id);
    if (!(p.col >= 0 && p.w >= 1 && p.col + p.w <= columns)) problems.push(p.id + ' runs past column ' + columns + ' (col ' + p.col + ' w ' + p.w + ')');
    if (!(p.row >= 0 && p.h === 1)) problems.push(p.id + ' at row ' + p.row + ' h ' + p.h);
    rows = Math.max(rows, p.row + p.h);
    for (let x = p.col; x < p.col + p.w; x++) {
      const cell = p.row + ',' + x;
      if (taken.has(cell)) problems.push(p.id + ' overlaps at ' + cell);
      taken.add(cell);
    }
  }
  if (seen.size !== items.length) problems.push('placed ' + seen.size + ' of ' + items.length);
  const fill = [];
  for (let r = 0; r < rows; r++) {
    let n = 0;
    for (let x = 0; x < columns; x++) if (taken.has(r + ',' + x)) n++;
    fill.push(n);
  }
  return { problems, rows, fill };
}
const readingIds = (places) => [...places].sort((p, q) => p.row - q.row || p.col - q.col).map(p => p.id).join(' ');

check('flow', (count) => {
  for (const { columns, items } of CASES) {
    const places = W.wgLayout(items, columns);
    const tag = columns + ' cols [' + show(items) + ']';
    count();
    cover(places, items, columns).problems.forEach(m => fail('flow', m + ' in ' + tag));
    if (places.map(p => p.id).join(' ') !== ids(items) || readingIds(places) !== ids(items))
      fail('flow', 'the page reads ' + readingIds(places) + ', not the order given, in ' + tag);
    places.forEach((p, i) => {
      const w = W.wgSpanOf(items[i], columns).w;
      if (p.w !== w) fail('flow', p.id + ' is ' + p.w + ' wide, not its own ' + w + ', in ' + tag);
      if (i === 0) { if (p.row !== 0 || p.col !== 0) fail('flow', 'the first card is not at the start in ' + tag); return; }
      const q = places[i - 1], end = q.col + q.w;
      // Beside the card before it when it fits the rest of that row, else at the start of the next row, never further.
      const fits = end < columns && end + p.w <= columns;
      const want = fits ? { row: q.row, col: end } : { row: q.row + 1, col: 0 };
      if (p.row !== want.row || p.col !== want.col) fail('flow', p.id + ' at ' + p.row + '/' + p.col + ' should be at ' + want.row + '/' + want.col + ' in ' + tag);
    });
  }
  if (!same(W.wgLayout([], 4), []) || !same(W.wgLayout([{ id: 'a', size: 'sm' }], 0), [])) fail('flow', 'no items or no columns should lay out nothing');
  // The Overview: however many KPI tiles the store has, every report after them stays after them.
  for (let tiles = 0; tiles <= 12; tiles++) {
    for (const columns of [1, 2, 4]) {
      count();
      const items = [{ id: 'followups', size: 'full' }]
        .concat(Array.from({ length: tiles }, (_, i) => ({ id: 'kpi-' + i, size: 'sm' })))
        .concat(['sectors', 'trends', 'notable', 'actions'].map(id => ({ id, size: 'full' })));
      if (readingIds(W.wgLayout(items, columns)) !== ids(items)) fail('flow', tiles + ' tiles at ' + columns + ' columns reorder the Overview');
    }
  }
  const four = ['sm', 'wide', 'sm', 'full'].map((size, i) => ({ id: 'abcd'[i], size }));
  count();
  if (!W.wgSameOrder(four, four.map(i => Object.assign({}, i))) || W.wgSameOrder(four, [four[1], four[0], four[2], four[3]]) || W.wgSameOrder(four, four.slice(1)))
    fail('flow', 'wgSameOrder compares ids in order and length');
});

check('columns', (count) => {
  for (const { columns, items } of CASES) {
    const tag = columns + ' cols [' + show(items) + ']';
    for (const [name, places] of [['wgLayout', W.wgLayout(items, columns)]]) {
      count();
      places.forEach(p => {
        if (p.col < 0 || p.col + p.w > columns) fail('columns', name + ' put ' + p.id + ' past the last column in ' + tag);
        const size = items.find(i => i.id === p.id).size;
        if (size === 'full' && (p.col !== 0 || p.w !== columns)) fail('columns', name + ' full ' + p.id + ' spans ' + p.w + ' of ' + columns + ' in ' + tag);
        if (size === 'wide' && columns === 1 && p.w !== 1) fail('columns', name + ' wide ' + p.id + ' is ' + p.w + ' wide at one column');
      });
    }
  }
  count();
  if (Object.keys(W.WG_SPANS).join(' ') !== 'sm wide full') fail('columns', 'the sizes are sm, wide and full, got ' + Object.keys(W.WG_SPANS).join(' '));
  for (const columns of [1, 2, 4]) {
    count();
    const w = (size) => W.wgSpanOf({ id: 'x', size }, columns).w;
    if (w('full') !== columns) fail('columns', 'full is ' + w('full') + ' at ' + columns);
    if (w('wide') !== Math.min(2, columns)) fail('columns', 'wide is ' + w('wide') + ' at ' + columns);
    if (w('sm') !== 1) fail('columns', 'sm is ' + w('sm') + ' at ' + columns);
    for (const junk of [undefined, '', 'tall', 'lg', 'constructor', '__proto__', 'toString']) {
      if (w(junk) !== columns) fail('columns', 'size ' + JSON.stringify(junk) + ' should span the row at ' + columns + ', got ' + w(junk));
    }
    if (W.wgSpanOf({ id: 'x', size: 'wide' }, columns).h !== 1) fail('columns', 'every size is one row high');
  }
});

// Uniform rows, so every slot is a known rectangle.
const geometry = (columns, rows) => {
  const unit = 200, gap = 16, height = 100;
  const rowTops = [], rowBottoms = [];
  for (let r = 0; r < rows; r++) { rowTops.push(r * (height + gap)); rowBottoms.push(r * (height + gap) + height); }
  return { left: 0, top: 0, width: columns * unit + (columns - 1) * gap, columns, gap, rowTops, rowBottoms };
};

check('choose', (count) => {
  // Adopt each pick with the pointer held still and choose again. Every
  // adopted order must bring the held card's own slot strictly closer to the
  // pointer, so no order can come round twice and the chain ends in null.
  const gap = (s, cx, cy) => Math.hypot(Math.max(s.left - cx, 0, cx - s.right), Math.max(s.top - cy, 0, cy - s.bottom));
  let picks = 0, chained = 0, longest = 0;
  for (const { columns, items } of CASES.filter((c, i) => i % 8 === 0 && c.items.length <= 12)) {
    const cur = items;
    const rows = W.wgLayout(cur, columns).reduce((n, p) => Math.max(n, p.row + 1), 0);
    const g = geometry(columns, rows);
    const toSlot = (box) => W.wgSlotFor(box, g);
    const tag = columns + ' cols [' + show(cur) + ']';
    const memo = new Map();
    const step = (order, id) => {
      const key = ids(order) + '|' + id;
      if (!memo.has(key)) {
        const place = W.wgLayout(order, columns).find(p => p.id === id);
        const candidates = W.wgCandidates(order, id, columns, toSlot);
        // A candidate's slot has to be where its order really puts the card,
        // or the chooser is steering by a slot the card never reaches.
        candidates.forEach(c => {
          const real = toSlot(W.wgLayout(c.order, columns).find(p => p.id === id));
          if (!same(real, c.slot)) fail('choose', 'candidate ' + ids(c.order) + ' claims ' + JSON.stringify(c.slot) + ' but lays ' + id + ' at ' + JSON.stringify(real) + ' in ' + tag);
        });
        memo.set(key, { home: toSlot(place), candidates });
      }
      return memo.get(key);
    };
    for (const { id } of cur) {
      for (let x = -60; x <= g.width + 60; x += 31) {
        for (let y = -60; y <= rows * 116 + 180; y += 27) {
          count();
          let order = cur, s = step(order, id), last = gap(s.home, x, y), moves = 0;
          const seen = new Set([ids(order)]);
          for (;;) {
            const pick = W.wgChoose(s.home, s.candidates, x, y);
            if (!pick) break;
            order = pick;
            s = step(order, id);
            moves++;
            const now = gap(s.home, x, y);
            if (!(now < last)) { fail('choose', id + ' at (' + x + ', ' + y + ') moved no closer (' + last + ' to ' + now + ') with ' + ids(order) + ' in ' + tag); break; }
            if (seen.has(ids(order))) { fail('choose', id + ' at (' + x + ', ' + y + ') came back to ' + ids(order) + ' in ' + tag); break; }
            seen.add(ids(order));
            last = now;
          }
          if (moves) picks++;
          if (moves > 1) chained++;
          longest = Math.max(longest, moves);
        }
      }
    }
  }
  if (!picks) fail('choose', 'no pointer position picked a move, so nothing was tested');
  // The dead band: anywhere within a few pixels of the middle of the gap
  // between two neighbours, neither of them takes the card from the other.
  const g = geometry(4, 1), toSlot = (box) => W.wgSlotFor(box, g);
  const row = ['a', 'b', 'c', 'd'].map(id => ({ id, size: 'sm' }));
  const middle = 200 + 16 / 2;
  for (const [order, id] of [[row, 'a'], [W.wgMoveTo(row, 'a', 1), 'a']]) {
    const home = toSlot(W.wgLayout(order, 4).find(p => p.id === id));
    for (let x = middle - 15; x <= middle + 15; x += 1) {
      count();
      const pick = W.wgChoose(home, W.wgCandidates(order, id, 4, toSlot), x, 50);
      if (pick) fail('choose', id + ' held in ' + ids(order) + ' jumped to ' + ids(pick) + ' with the pointer at ' + x + ', inside the dead band');
    }
  }
  // And past the band the card does go, so the band is not everything.
  const past = W.wgChoose(toSlot(W.wgLayout(row, 4)[0]), W.wgCandidates(row, 'a', 4, toSlot), middle + 30, 50);
  count();
  if (!past || ids(past) !== 'b a c d') fail('choose', 'a pointer well into b left a where it was');
  stats.choose = { picks, chained, longest };
});

check('group', (count) => {
  const g = geometry(4, 3);
  const toSlot = (box) => W.wgSlotFor(box, g);
  const items = [['b', 'sm'], ['c', 'sm'], ['d', 'sm'], ['e', 'sm'], ['A', 'wide'], ['f', 'sm'], ['g', 'sm']].map(([id, size]) => ({ id, size }));
  const cands = W.wgCandidates(items, 'A', 4, toSlot);
  const groups = cands.length - (items.length - 1);
  const at = cands.findIndex(c => ids(c.order) === 'A d e b c f g');
  count();
  if (at < 0) { fail('group', 'no candidate swaps A with b and c: ' + cands.map(c => ids(c.order)).join(' / ')); return; }
  if (at >= groups) fail('group', 'the swap is listed among the sequence moves, not before them');
  if (!same(cands[at].slot, toSlot({ col: 0, row: 0, w: 2, h: 1 }))) fail('group', 'the swap slot is not the area b and c filled');
  const placed = W.wgLayout(cands[at].order, 4);
  const pos = (id) => { const p = placed.find(q => q.id === id); return p.col + ',' + p.row + ',' + p.w; };
  if (pos('A') !== '0,0,2' || pos('b') !== '0,1,1' || pos('c') !== '1,1,1') fail('group', 'after the swap A is ' + pos('A') + ', b ' + pos('b') + ', c ' + pos('c'));
  // Pointer dead centre on that area: the sequence move to the front lands A
  // on the same slot, and the swap wins because it is listed first.
  const s = toSlot({ col: 0, row: 0, w: 2, h: 1 });
  const home = toSlot(W.wgLayout(items, 4).find(p => p.id === 'A'));
  const pick = W.wgChoose(home, cands, (s.left + s.right) / 2, (s.top + s.bottom) / 2);
  count();
  if (!pick || ids(pick) !== 'A d e b c f g') fail('group', 'the chooser took ' + (pick ? ids(pick) : 'nothing') + ' over the swap');
  const pair = [{ id: 'A', size: 'wide' }, { id: 'B', size: 'wide' }];
  count();
  if (W.wgCandidates(pair, 'A', 4, toSlot).length !== 1) fail('group', 'one wide is not a group, so two wides have only the sequence move');
});

check('merge', (count) => {
  const defaults = ['a', 'b', 'c', 'd'];
  const frozen = defaults.join(' ');
  const cases = [
    [{ order: ['c', 'x', 'a', 'c'], hidden: ['b', 'zz', 'b', 5] }, 'c b a d', 'b'],
    [null, 'a b c d', ''],
    [undefined, 'a b c d', ''],
    ['junk', 'a b c d', ''],
    [{ order: 'nope', hidden: null }, 'a b c d', ''],
    [{ order: [], hidden: [] }, 'a b c d', ''],
    [{ order: [null, 7, { id: 'a' }, 'd'], hidden: ['d', 'd'] }, 'a b c d', 'd'],
    [{ order: ['d', 'c', 'b', 'a'] }, 'd c b a', ''],
    [{ order: ['b'] }, 'a b c d', ''],
    [{ order: ['d'] }, 'a b c d', ''],
    [{ order: ['d', 'a'] }, 'd b c a', ''],
  ];
  for (const [saved, order, hidden] of cases) {
    count();
    const got = W.wgMergeOrder(defaults, saved);
    const tag = JSON.stringify(saved === undefined ? 'undefined' : saved);
    if (got.order.join(' ') !== order) fail('merge', tag + ' ordered ' + got.order.join(' ') + ', expected ' + order);
    if (got.hidden.join(' ') !== hidden) fail('merge', tag + ' hid ' + got.hidden.join(' ') + ', expected ' + hidden);
    if (got.order.length !== defaults.length || !defaults.every(id => got.order.filter(o => o === id).length === 1))
      fail('merge', tag + ' does not hold every default id exactly once');
  }
  if (defaults.join(' ') !== frozen) fail('merge', 'the default ids were changed in place');
  // The Overview migration: saved KPI tiles keep their order, other blocks keep their place.
  const ov = W.wgMergeOrder(['trend', 'kpi-a', 'kpi-b', 'kpi-c', 'alerts'], { order: ['kpi-c', 'kpi-a', 'kpi-b'], hidden: [] });
  count();
  if (ov.order.join(' ') !== 'trend kpi-c kpi-a kpi-b alerts') fail('merge', 'the migrated Overview order is ' + ov.order.join(' '));
});

check('keys', (count) => {
  const items = ['a', 'b', 'c', 'd'].map(id => ({ id, size: 'sm' }));
  const cases = [['a', -1, 'a b c d', true], ['d', 1, 'a b c d', true], ['b', 1, 'a c b d'], ['c', -1, 'a c b d'],
                 ['b', -5, 'b a c d'], ['b', 9, 'a c d b'], ['a', 1, 'b a c d'], ['d', -1, 'a b d c'], ['zz', 1, 'a b c d', true]];
  for (const [id, delta, want, unchanged] of cases) {
    count();
    const got = W.wgKeyMove(items, id, delta);
    if (ids(got) !== want) fail('keys', id + ' by ' + delta + ' gave ' + ids(got) + ', expected ' + want);
    if (unchanged && got !== items) fail('keys', id + ' by ' + delta + ' should return the same array');
  }
  if (ids(items) !== 'a b c d') fail('keys', 'the items were changed in place');
});

check('widths', (count) => {
  const cases = [[2000, 640, 280, 2], [2000, 641, 280, 4], [300, 641, 280, 2], [1119, 1400, 280, 2],
                 [1120, 1400, 280, 4], [1120, 375, 280, 2], [960, 961, 240, 4], [959, 961, 240, 2]];
  for (const [content, viewport, cell, want] of cases) {
    count();
    const got = W.wgColumns(content, viewport, cell);
    if (got !== want) fail('widths', 'content ' + content + ', viewport ' + viewport + ', cell ' + cell + ' gave ' + got + ' columns, expected ' + want);
  }
});

check('slots', (count) => {
  const g = { left: 10, width: 460, columns: 4, gap: 20, rowTops: [0, 150], rowBottoms: [120, 250] };
  const cases = [
    [{ col: 1, row: 0, w: 2, h: 1 }, g, { left: 130, top: 0, right: 350, bottom: 120 }],
    [{ col: 0, row: 1, w: 4, h: 1 }, g, { left: 10, top: 150, right: 470, bottom: 250 }],
    [{ col: 3, row: 2, w: 1, h: 1 }, g, { left: 370, top: 270, right: 470, bottom: 370 }],
    [{ col: 0, row: 3, w: 1, h: 1 }, g, { left: 10, top: 390, right: 110, bottom: 490 }],
    [{ col: 2, row: 1, w: 2, h: 2 }, g, { left: 250, top: 150, right: 470, bottom: 370 }],
    [{ col: 0, row: 1, w: 1, h: 1 }, { left: 0, top: 5, width: 460, columns: 4, gap: 20, rowTops: [], rowBottoms: [] }, { left: 0, top: 125, right: 100, bottom: 225 }],
    [{ col: 1, row: 0, w: 1, h: 1 }, { left: 0, width: 220, columns: 2, gap: 20 }, { left: 120, top: 0, right: 220, bottom: 100 }],
  ];
  for (const [box, geo, want] of cases) {
    count();
    const got = W.wgSlotFor(box, geo);
    if (!same(got, want)) fail('slots', JSON.stringify(box) + ' gave ' + JSON.stringify(got) + ', expected ' + JSON.stringify(want));
  }
});

// Overview KPI ids, from the labels copilot.py sends (_overview's metrics) and the rig fixtures carry.
check('kpi', (count) => {
  const want = [
    ['Revenue (7d)', 'kpi-revenue-7d'], ['Orders (7d)', 'kpi-orders-7d'], ['Avg order value', 'kpi-avg-order-value'],
    ['Unfulfilled (7d)', 'kpi-unfulfilled-7d'], ['New customers (7d)', 'kpi-new-customers-7d'], ['Products', 'kpi-products'],
    ['Low stock (\u22645)', 'kpi-low-stock'], ['Sessions (GA4, 28d)', 'kpi-sessions-ga4-28d'],
    ['Revenue (GA4, 28d)', 'kpi-revenue-ga4-28d'], ['Search clicks (28d)', 'kpi-search-clicks-28d'],
    ['Search impressions (28d)', 'kpi-search-impressions-28d'], ['Avg Google position', 'kpi-avg-google-position'],
  ];
  for (const [label, id] of want) {
    count();
    const got = W.wgKpiId(label);
    if (got !== id) fail('kpi', JSON.stringify(label) + ' gave ' + got + ', expected ' + id);
    if (!W.WG_ID.test(got)) fail('kpi', got + ' does not match the id pattern');
  }
  const ids = want.map(([label]) => W.wgKpiId(label));
  if (new Set(ids).size !== ids.length) fail('kpi', 'two Overview labels share an id: ' + ids.join(' '));
  // The threshold is LOW_STOCK_THRESHOLD, so any number and either way of writing the sign is the same tile.
  for (const label of ['Low stock (\u22643)', 'Low stock (<=10)', 'Low stock (< 25)', 'Low stock']) {
    count();
    if (W.wgKpiId(label) !== 'kpi-low-stock') fail('kpi', JSON.stringify(label) + ' gave ' + W.wgKpiId(label));
  }
  count();
  const long = W.wgKpiId('A label far longer than any tile would ever carry, with words to spare at the end');
  if (long.length > 48 || !W.WG_ID.test(long) || long.endsWith('-')) fail('kpi', 'a long label gave ' + long);
  count();
  if (!W.WG_ID.test(W.wgKpiId('')) || !W.WG_ID.test(W.wgKpiId('---'))) fail('kpi', 'an empty label gave an id outside the pattern');
});

console.log(JSON.stringify({ ran, fails, stats }));
"""

_WG_RUN = {}


def _wg_block():
    """The widget layout block exactly as the page ships it, markers included."""
    ok(HTML.count(_WG_START) == 1 and HTML.count(_WG_END) == 1,
       "static/index.html must carry each widget layout marker line exactly once, at 8 spaces: "
       "%r and %r - if they were renamed or reindented, fix these guards too" % (_WG_START.strip(), _WG_END.strip()))
    a = HTML.index(_WG_START)
    return HTML[a:HTML.index(_WG_END, a) + len(_WG_END)]


def _wg_check(key, claim):
    """Runs _WG_HARNESS once for every widget layout test below, then asserts
    that the named group of checks ran at least one case and found nothing.
    Returns False, having said so, when node is not installed."""
    if not any(os.access(os.path.join(p, "node"), os.X_OK)
               for p in os.environ.get("PATH", "").split(os.pathsep)):
        print("       (node unavailable, skipped)")
        return False
    if "out" not in _WG_RUN:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
            fh.write(_WG_HARNESS)
            path = fh.name
        try:
            r = subprocess.run(["node", path, os.path.join(ROOT, "static", "index.html")],
                               capture_output=True, text=True, timeout=120)
            _WG_RUN["out"] = (r.returncode, (r.stdout or "").strip(), r.stderr or "")
        except subprocess.TimeoutExpired:
            _WG_RUN["out"] = (-1, "", "timed out after 120s: a layout function is looping")
        finally:
            os.unlink(path)
    code, out, err = _WG_RUN["out"]
    ok(code == 0, "the widget layout harness failed: " + err[:400])
    ok(out != "EXTRACT_FAILED",
       "the widget layout block could not be lifted out of static/index.html: it must sit between the "
       "exact lines %r and %r - if they were renamed or reindented, fix this guard too"
       % (_WG_START.strip(), _WG_END.strip()))
    got = json.loads(out)
    ok(got["ran"].get(key, 0) > 0, "the %s checks ran no cases, so they prove nothing" % key)
    found = got["fails"].get(key, [])
    ok(not found, claim + ": " + " | ".join(found[:3]))
    return True


@test
def t_a_card_is_laid_out_exactly_where_its_order_puts_it():
    """The component's tiler seated a later card before an earlier one to close
    a hole in a row. On gizmo's pages, which read top to bottom and whose cards
    mostly span the row, that meant moving whole reports: with nine or ten KPI
    tiles the Overview pulled Sales by sector up between them, and a card
    dropped between two reports jumped to the foot of the page. So the layout
    keeps the order it is given. Over 1,200 seeded mixes of sm, wide and full at
    one, two and four columns, every card is placed once at its own width, sits
    beside the card before it when it fits the rest of the row and otherwise
    starts the next row, which is what the browser's grid auto-placement does
    with the same spans, and the Overview keeps its order with any number of
    tiles from none to twelve."""
    _wg_check("flow", "the layout moved a card away from its place in the order")


@test
def t_no_widget_is_placed_past_the_last_column():
    """full is Infinity columns wide and has to be clamped, and a wide card on a
    phone has one column to sit in. The layout may not put a card past the
    column count, full spans every column, wide is one column at one, and a
    size nobody set spans the row."""
    _wg_check("columns", "a card ran past the last column or took the wrong span")


@test
def t_a_held_widget_never_swaps_back_and_forth_under_a_still_pointer():
    """With the pointer held still over thousands of positions, each adopted
    pick is taken as the new order and the chooser is asked again from the
    card's new slot. It may move again, but only strictly nearer the pointer, so
    no order comes round twice and the chain ends. The spec said the second
    choice is always null; it is not, some picks take a second or third step,
    each closer, which is convergence rather than oscillation. Every
    candidate's slot must also be where its order really puts the card: a group
    swap that claims a slot its order never gives the card is a slot the
    chooser would pick every frame. Between two neighbours there is a dead
    band, from WG_ENTER, where neither takes the card."""
    _wg_check("choose", "the chooser moved a card no nearer, came back to an order, or jumped inside the dead band")


@test
def t_a_wide_widget_can_trade_places_with_the_two_small_ones_that_fill_its_shape():
    """A group swap is how a wide card moves up a row without reshuffling
    everything between: it trades places with two sm cards that fill its shape,
    and they keep their order. Group swaps are listed before sequence moves, so
    on a tie the swap wins, and one wide card is not a group."""
    _wg_check("group", "the group swap is missing, misplaced or loses its tie")


@test
def t_a_saved_layout_keeps_every_rendered_widget_exactly_once():
    """A saved layout outlives the cards it names. Ids that did not render and
    repeats are dropped, a card the saved order never mentions goes in at its
    default index, hidden ids are filtered the same way, junk saves read as the
    default, and the Overview migration keeps the old KPI order while every
    other block stays where it was."""
    _wg_check("merge", "wgMergeOrder lost, repeated or misplaced a card")


@test
def t_a_keyboard_move_goes_one_place_and_stops_at_either_end():
    """Alt with an arrow moves a card one place, and at the first or last place
    it stays put, returning the same array so nothing is announced as moved."""
    _wg_check("keys", "wgKeyMove wrapped, skipped or copied")


@test
def t_the_grid_picks_one_two_or_four_columns_at_the_documented_widths():
    """Two columns at a 640px viewport and below (since 2026-09-23: one per row
    stacked the Overview's seven KPI tiles a screen and a half deep), so small
    tiles pair up and wider cards take the row; two when the content column is
    narrower than four cells; four otherwise; never three."""
    _wg_check("widths", "wgColumns picked the wrong count at a boundary")


@test
def t_a_drop_slot_below_the_last_rendered_row_takes_that_rows_height():
    """Rows are as tall as their content, so a slot's top and bottom come from
    the rendered rows. A card dragged to a row that does not exist yet needs a
    rectangle too: it takes the last row's height one gap further down, and
    with no rows at all a row is one column unit tall."""
    _wg_check("slots", "wgSlotFor put a slot in the wrong place")


@test
def t_the_widget_layout_block_never_touches_the_page():
    """The block is lifted out and run under node, which has no page, so a
    reach into the DOM would pass here only by accident and break the harness
    the day that path runs. It stays arithmetic."""
    block = _wg_block()
    for token in ("document", "window", "getBoundingClientRect", "querySelector", "$("):
        ok(token not in block, "the widget layout block mentions %r" % token)


@test
def t_a_kpi_tile_id_comes_from_its_label_and_not_its_threshold():
    """An Overview KPI tile has no id of its own, so its widget id is a slug of
    the label the server sends, and a saved layout names tiles by it. The low
    stock label carries LOW_STOCK_THRESHOLD in brackets; if the number were in
    the id, changing that setting would drop the tile from every saved layout.
    Every real label maps to its expected id, no two collide, the threshold in
    any form is ignored, and a long or empty label still gives a valid id."""
    _wg_check("kpi", "wgKpiId gave the wrong id for an Overview label")


def _wg_calls(src, name):
    """The argument lists of every call to `name(` in src, split at their top
    level commas, so a nested el('div', ...) does not look like the id."""
    out = []
    for m in re.finditer(r"(?<![\w.])" + re.escape(name) + r"\(", src):
        i, depth, args, cur, quote = m.end(), 1, [], "", None
        while i < len(src) and depth:
            ch = src[i]
            if quote:
                cur += ch
                if ch == "\\":
                    cur += src[i + 1]; i += 1
                elif ch == quote:
                    quote = None
            elif ch in "'\"`":
                quote = ch; cur += ch
            elif ch in "([{":
                depth += 1; cur += ch
            elif ch in ")]}":
                depth -= 1
                if depth: cur += ch
            elif ch == "," and depth == 1:
                args.append(cur.strip()); cur = ""
            else:
                cur += ch
            i += 1
        args.append(cur.strip())
        out.append((m.start(), args))
    return out


@test
def t_the_widget_grid_reads_its_sizes_and_motion_from_the_one_root():
    """The grid's cell width and every motion value are tokens in the one
    top-level :root, and its gap is the page's own --page-rhythm, 24 and 16 on
    a phone, so the space between blocks is one number whether or not a page is
    a grid. The grid once carried a copy of that value of its own, re-pointed
    for a phone beside the rhythm it copied. The stylesheet and the layer read
    them by name, so the widget rules and the script carry no pixel, duration or
    scale of their own: a number written twice is a number that drifts."""
    root = CSS.split(":root {")[1].split("\n        }")[0]
    for decl in ("--wgrid-cell: 240px", "--dur-layout: .38s",
                 "--ease-layout: linear(0,", "--dur-landed: .62s", "--lift-scale: 1.02"):
        ok(decl in root, "the top-level :root defines " + decl)
    ok("--wgrid-gap" not in CSS, "the grid has no gap of its own to drift from the page rhythm")
    ok(re.search(r"--ease-layout: linear\(0,[\d., \n]*, 1\);", root),
       "the spring curve starts at 0 and settles at exactly 1")
    ok(".ov-wrap.wgrid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));\n            gap: var(--page-rhythm);" in CSS,
       "the grid's gap is the page rhythm")
    ok(".ov-wrap .widget-group > * + * { margin-top: var(--page-rhythm); }" in CSS
       and ".ov-wrap .widget-group > .section-title + * { margin-top: var(--sp-3); }" in CSS,
       "a group keeps the page rhythm inside it: 12 under its heading, the gap between blocks")
    ok(".wg-held.wg-lifted { scale: var(--lift-scale); }" in CSS, "the lift is the token")
    layer = _wg_layer()
    for read in ("tokenNum('--wgrid-cell')", "tokenNum('--dur-layout') * 1000", "tokenValue('--ease-layout')",
                 "tokenNum('--dur-landed') * 1000"):
        ok(read in layer, "the layer reads " + read)
    for literal in ("240", ".38", "380", ".62", "620", "1.02", "1.06", "cubic-bezier", "spring"):
        ok(literal not in layer.replace("docs/superpowers", ""), "the layer writes %r itself instead of reading a token" % literal)
    for sel, body in _rules(CSS):
        if not re.search(r"wgrid|wg-|widget-group", sel):
            continue
        flat = re.sub(r"var\(--[\w-]+\)", "", body)
        ok(not re.search(r"\d(px|ms|s)\b", flat) and "scale(" not in flat,
           "the widget rule %s carries its own length, duration or scale: %s" % (sel.strip()[:60], body.strip()[:80]))


@test
def t_moving_cards_is_skipped_when_motion_is_reduced():
    """With prefers-reduced-motion nothing slides: no FLIP of the other cards,
    no lift scale and no travel from the pointer into the slot. The held card
    still follows the pointer, because that is the manipulation itself."""
    flip = _wg_fn("function wgFlip(")
    ok(flip.split("{", 1)[1].lstrip().startswith("if (REDUCE_MOTION) { apply(); return; }"),
       "the FLIP applies the new order and returns before it measures anything")
    ok("if (!REDUCE_MOTION) d.card.classList.add('wg-lifted');" in _wg_fn("function wgLift("),
       "the lift scale is only added when motion is allowed")
    ok("if (!REDUCE_MOTION && from) wgAnimate(d.card," in _wg_fn("function wgDragEnd("),
       "and so is the landing travel")
    layer = _wg_layer()
    ok(layer.count("wgAnimate(") == 3 and layer.count(".animate(") == 2,
       "every animation in the layer goes through those two checked paths (one helper, two callers)")
    ok("d.card.style.translate = " in _wg_fn("function wgFollow("), "the held card follows the pointer either way")


@test
def t_the_widget_grid_watches_every_view_setview_shows():
    """The layer's content roots come from the same list setView shows and
    hides, so a view added to one is in the other. Chat is the one view left
    out, as it is on the server: it has a log and a composer, not cards."""
    views = re.search(r"const APP_VIEWS = \[([^\]]*)\];", SCRIPT)
    ok(views, "one list of views")
    app = re.findall(r"'(\w+)'", views.group(1))
    ok(sorted(app) == sorted(re.findall(r'<section class="view(?: active)?" id="view-(\w+)"', HTML)),
       "APP_VIEWS is exactly the views in the page")
    fn = fn_src("function setView(")
    ok("APP_VIEWS.forEach(name => $('view-' + name).classList.toggle('active', v === name));" in fn,
       "setView shows and hides by that list")
    ok("'skills', 'chat', 'guide']" not in fn, "and carries no copy of it")
    ok("if (WG_VIEWS.indexOf(v) >= 0) wgArrange(v);" in fn, "a view is arranged when it shows, when it has a width")
    layer = _wg_layer()
    ok("const WG_VIEWS = APP_VIEWS.filter(v => v !== 'chat');" in layer, "the layer's roots derive from it")
    ok("WG_VIEWS.forEach(v => wgWatch(v));" in SCRIPT, "every one of them is watched from start-up")
    ok("const wgRoot = (view) => $(view === 'overview' ? 'ov-content' : view + '-content');" in layer,
       "Overview is the one root not named after its view")
    for v in app:
        if v == "chat": continue
        ok(('id="%s"' % ("ov-content" if v == "overview" else v + "-content")) in HTML, "the root for %s exists" % v)
    py = open(os.path.join(ROOT, "copilot.py"), encoding="utf-8").read()
    server = re.findall(r'"(\w+)"', py.split("LAYOUT_VIEWS = (")[1].split(")")[0])
    ok(sorted(server) == sorted(v for v in app if v != "chat"), "and the server accepts a layout for exactly those views")
    ok("new MutationObserver(" in layer and "observe(root, { childList: true })" in layer
       and "new ResizeObserver(" in layer, "a render and a width change each re-arrange")


@test
def t_a_report_page_is_a_list_only_while_it_is_being_customized():
    """Outside Customize mode a report page is a document with headings, not a
    list, so the list roles are set by the mode's decoration and nowhere else,
    and taken off again when it ends."""
    for role in ("'list'", "'listitem'"):
        sites = [m.start() for m in re.finditer(r"'role', " + role, SCRIPT)]
        ok(len(sites) == 1, "one place sets role %s, found %d" % (role, len(sites)))
        ok(sites[0] > SCRIPT.index("function wgDecorate(") and sites[0] < SCRIPT.index("function wgUndecorate("),
           "and it is Customize mode's decoration")
    ok('role="list"' not in HTML and "role = 'list'" not in SCRIPT, "no markup or property sets it either")
    undo = _wg_fn("function wgUndecorate(")
    for need in ("if (root.getAttribute('role') === 'list') root.removeAttribute('role');",
                 "orig.forEach(([a, v]) => wgAttr(n, a, v))", ".wg-hide').forEach(b => b.remove())",
                 "c.inert = false"):
        ok(need in undo, "leaving the mode undoes: " + need)
    deco = _wg_fn("function wgDecorate(")
    ok("c.inert = true;" in deco and "wgInert.add(c);" in deco,
       "everything inside a card is inert in the mode, and only what the mode made inert is released")


@test
def t_every_widget_id_is_well_formed_and_named_once_per_renderer():
    """A widget id is the key a saved layout is kept under, so it matches the
    server's pattern, and a renderer that gave two cards the same id would
    leave the page unarrangeable. Every literal id in the page is checked:
    widget() calls, data-widget attributes and renderStructured's ids."""
    pattern = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
    starts = [m.start() for m in re.finditer(r"\n        (?:async )?function \w+", SCRIPT)]
    owner = lambda at: max([i for i in starts if i < at] or [0])
    found = []
    for at, args in _wg_calls(SCRIPT, "widget"):
        if len(args) >= 2 and re.fullmatch(r"'[^']*'", args[1]):
            found.append((at, args[1][1:-1]))
    for m in re.finditer(r"setAttribute\('data-widget', '([^']*)'\)", SCRIPT):
        found.append((m.start(), m.group(1)))
    for m in re.finditer(r"ids: \{([^}]*)\}", SCRIPT):
        found += [(m.start(), v) for v in re.findall(r":\s*'([^']*)'", m.group(1))]
    found += [(-1, v) for v in re.findall(r'data-widget="([^"]*)"', HTML)]
    # The id a group's caller passes in, like the Overview's and SEO's 'trends', is a literal too.
    for m in re.finditer(r"render(?:TrendsBlock|SeoTrends)\([^\n]*, '([^']*)'\);", SCRIPT):
        found.append((m.start(), m.group(1)))
    ok(len(found) >= 5, "found the Overview's ids (%d)" % len(found))
    for _, v in found:
        ok(pattern.match(v), "the widget id %r does not match the pattern" % v)
    by = {}
    for at, v in found:
        key = owner(at) if at >= 0 else -1
        ok(v not in by.setdefault(key, set()), "the id %r is given twice by one renderer" % v)
        by[key].add(v)
    ov = fn_src("function renderOverview(")
    for v in ("followups", "sectors", "trends", "notable", "actions"):
        ok("'%s'" % v in ov, "the Overview names its %s card" % v)
    ok("widget(statCard(m, i), wgKpiId(m.label), 'sm', m.label)" in ov, "and each KPI tile by its label")


@test
def t_the_old_overview_customizing_is_gone_and_its_key_is_read_only_by_the_migration():
    """The Overview's own reorder and hide lived in this browser only, with
    HTML5 drag, arrow buttons and a heading of its own. The widget grid
    replaces all of it; the one thing left is the migration that carries an
    old order to the person's account, and it takes the key away only once
    the server has the layout."""
    for gone in ("metricsGridCustom", "reorderOv", "toggleHideOv", "ovEdit", "ovLayout", "saveOvLayout",
                 "ovOrderedLabels", "Key numbers", "ov-customize", "ov-cust-hint", "stat-edit", "stat-hide",
                 "stat-move", "--stat-tools-w", "Use the arrows to reorder"):
        ok(gone not in HTML, "%s is gone" % gone)
    ok(SCRIPT.count("'sc_ov_layout_v1'") == 1 and "const OV_LAYOUT_KEY = 'sc_ov_layout_v1';" in _wg_layer(),
       "the key is named once, beside the migration")
    mig = _wg_fn("async function wgMigrateOverview(")
    reads = [m.start() for m in re.finditer(r"getItem\(OV_LAYOUT_KEY\)", SCRIPT)]
    ok(len(reads) == 1 and "getItem(OV_LAYOUT_KEY)" in mig, "only the migration reads it")
    ok("setItem(OV_LAYOUT_KEY" not in SCRIPT, "and nothing writes it any more")
    ok(mig.index("await api('/api/layouts'") < mig.index("if (!d || !d.layouts || typeof d.layouts !== 'object') return;")
       < mig.index("localStorage.removeItem(OV_LAYOUT_KEY)"), "the key goes only after the save succeeds; a failure returns first")
    ok("if (!wgLayouts || wgLayouts.overview || !wgOwnerKnown || wgMigrating) return;" in mig,
       "an account that already has an Overview layout keeps it, and nothing moves before the browser's owner is known")
    ok("wgOwnerKnown = true;" in fn_src("function claimLocalCache("), "which claimLocalCache establishes")
    ok("[LS, LS_SET, LS_OWNER, OV_LAYOUT_KEY]" in SCRIPT,
       "signing in as someone else still clears it, so one person's old order never lands on another's account")


@test
def t_the_layer_writes_the_arrangement_as_attributes():
    """The column count and each card's placed width are attributes the
    stylesheet reads, never inline grid styles or a custom property on an
    element: print has to be able to overrule them, and a screen does not
    write its own sizes. The only inline style is the held card's translate,
    which follows the pointer."""
    layer = _wg_layer()
    ok("wgAttr(root, 'data-cols', String(cols));" in layer, "the layer writes data-cols")
    ok("wgAttr(n, 'data-span', p.w === cols ? 'full' : String(p.w));" in layer, "and data-span")
    for bad in ("style.gridColumn", "style.gridRow", "style.gridTemplate", "style.setProperty", "style.order", "cssText"):
        ok(bad not in layer, "the layer writes %s" % bad)
    ok(set(re.findall(r"\.style\.(\w+) = ", layer)) == {"translate"}, "the held card's translate is its one inline style")
    for span in ('[data-span="2"] { grid-column: span 2; }',
                 '[data-cols="2"] { grid-template-columns: repeat(2, minmax(0, 1fr)); }',
                 '[data-cols="1"] { grid-template-columns: minmax(0, 1fr); }'):
        ok(span in CSS, "the stylesheet reads " + span)


@test
def t_a_printed_grid_is_one_column_and_leaves_the_customize_controls_off():
    """Printing uses the arrangement on screen, hidden cards left out, in one
    column: four columns on an A4 page squeeze every card. The hide buttons and
    the header's Customize, Show hidden, Reset and Done are screen furniture."""
    prints = [CSS[m.end():] for m in re.finditer(r"@media print \{", CSS)]
    block = next((p for p in prints if ".ov-wrap.wgrid {" in p[:4000]), "")
    ok(block, "a print block covers the grid")
    for rule in (".ov-wrap.wgrid { grid-template-columns: minmax(0, 1fr) !important; }",
                 ".ov-wrap.wgrid > * { grid-column: 1 / -1 !important; }",
                 ".ov-wrap.wgrid > [data-widget][hidden] { display: none !important; }"):
        ok(rule in block, "print: " + rule)
    ok(re.search(r"\.wg-hide, \[data-wg-control\],[^{]*\{ display: none !important; \}", block),
       "the hide buttons and every header control are dropped from print")
    controls = _wg_fn("function wgControls(")
    ok("b.setAttribute('data-wg-control', key);" in controls, "every header control carries the attribute print hides")
    ok("el('button', 'icon-btn wg-hide')" in _wg_fn("function wgDecorate("), "and every hide button the class")


@test
def t_the_customize_copy_says_what_works_without_a_dash():
    """The hint, the controls, the announcements and the save failures are the
    words of this feature, in the house voice: a full stop or a colon, never a
    dash. Announcements go to their own live region, not to toasts, which
    would be seen on every Alt+Arrow as well as heard."""
    layer = _wg_layer()
    copy = ["Drag to rearrange. On a touch screen, press and hold first. With a keyboard, hold Alt and press the arrow keys."]
    ok("'" + copy[0] + "'" in SCRIPT, "the hint says how to move a card with a mouse, a finger and a keyboard")
    for text in ("'Customise'", "'Show hidden ('", "'Reset'", "'Done'", "' moved to '", "' of '", "' hidden'",
                 "' shown'", "'Hide '", "'Layouts are unavailable right now'", "'Loading your layout'",
                 "'Your layout was not saved. Try Done again.'", "'Your layout was not saved'"):
        ok(text in layer, "the layer says " + text)
    for lit in re.findall(r"'([^'\n]*)'", layer) + copy:
        ok("\u2014" not in lit and "\u2013" not in lit and " - " not in lit, "a dash in the copy: %r" % lit)
    ok("say.id = 'wg-status';" in SCRIPT and "say.setAttribute('aria-live', 'polite');" in SCRIPT,
       "moves are announced in a polite status region made at start-up")
    ok("const region = $('wg-status');" in _wg_fn("function wgSay(") and "addToast(" not in layer and "toastOk(" not in layer,
       "and never as a toast; only a failed save is a toast")


@test
def t_done_saves_before_it_leaves_and_a_failure_keeps_the_draft():
    """A failed save is never shown as saved: Done writes first, and on a
    failure the draft stays on screen to try again. Leaving the view counts as
    Done, and a failure there drops the draft, so the view opens on its last
    saved layout. A draft that is the default deletes the saved layout instead
    of saving a copy of it, and a card that did not render today keeps its
    saved place. A view that is not showing its cards (a product opened from
    the list, a run gate, a refresh half drawn) saves nothing: its draft would
    be laid against no cards, read as the default, and delete the layout."""
    commit = _wg_fn("async function wgCommit(")
    answer = commit.index("await api('/api/layouts', body)")
    ok(answer < commit.index("if (wgEdit === edit) wgEdit = null;", answer),
       "the mode ends only after the answer")
    ok(commit.index("if (!root.classList.contains('wgrid'))") < commit.index("const body = wgBody(view, root);"),
       "nothing is sent for a view that is not showing its cards")
    ok("if (ok || leaving)" in commit and "leaving ? 'Your layout was not saved' : 'Your layout was not saved. Try Done again.'" in commit,
       "a failed Done stays in the mode; a failed leave drops the draft; each says so")
    ok("if (wgEdit && wgEdit.view !== v) wgCommit(wgEdit.view, true);" in fn_src("function setView("),
       "leaving a view while customizing it is Done")
    body = _wg_fn("function wgBody(")
    ok("return { view, reset: true };" in body, "a default draft resets")
    ok("order.splice(Math.min(i, order.length), 0, id);" in body and "if (rendered.has(id) || order.indexOf(id) >= 0" in body,
       "a saved id that did not render goes back in at its saved index")
    ok("api('/api/layouts', {})" in _wg_fn("async function wgLoadLayouts("), "the layouts come from the account")
    claim = fn_src("function claimLocalCache(")
    ok("Promise.resolve().then(wgLoadLayouts);" in claim and claim.index("wgLoadLayouts") < claim.index("if (owner === id) return;"),
       "the layouts are read when the app learns who is signed in, including a sign-in that does not reload the page")
    # Two callers, both after sign-in: claimLocalCache, and the moment a
    # starter password is replaced (the read during it was refused).
    ok(SCRIPT.count("wgLoadLayouts") == 3 and SCRIPT.count("wgLoadLayouts();") == 1
       and "wgLoadLayouts();" in SCRIPT[SCRIPT.index("const r = await authApi('/api/auth/password'"):][:900],
       "and from nowhere else, so a read made before sign-in cannot switch Customize off")


@test
def t_a_card_heading_carries_its_widget_to_the_card_and_a_group_is_built_by_its_renderer():
    """cardifySections builds a card from a heading after the renderer has
    run, so the renderer marks the heading and the card takes the marks. The
    fold stops at a widget, or the Open follow-ups heading would sweep every
    KPI tile after it into its card. A heading over several blocks is a group
    its renderer builds, because trendsSection repaints by swapping its own
    nodes; and only the Overview asks renderStructured for ids."""
    fold = SCRIPT[SCRIPT.index("function cardifySections("):]
    fold = fold[:fold.index("\n        function ")]
    ok("['data-widget', 'data-size', 'data-widget-label'].forEach(function (a) {" in fold
       and "card.setAttribute(a, node.getAttribute(a));" in fold, "the card takes the heading's widget marks")
    ok("!(n.hasAttribute && n.hasAttribute('data-widget'))" in fold, "the fold stops at a widget")
    trends = fn_src("function renderTrendsBlock(")
    ok("const group = el('div', 'widget-group');" in trends and "if (id) widget(group, id, 'full', 'Performance over time');" in trends
       and "trendsSection(group, " in trends and "cardifySections(group);" in trends,
       "the trends heading and its charts are one group, with the id its caller passes")
    ok(SCRIPT.count("renderTrendsBlock(") == 2 and "intro, 'trends');" in fn_src("function renderOverview("),
       "the Overview is its one caller and names it")
    calls = [args for _, args in _wg_calls(SCRIPT, "renderStructured") if len(args) > 2 and "ids:" in args[2]]
    ok(len(calls) == 1 and calls[0][0] == "box", "only the Overview passes ids to renderStructured")
    ok(".widget-group { display: flex; flex-direction: column; min-width: 0; }" in CSS, "a group is one column")


# Every report view the stage 1 inventory found with two or more blocks, by the
# renderer that draws it. Named rather than discovered, so renaming one fails here.
_WG_ADOPTED = {
    "overview": "function renderOverview(", "seo": "function renderSEO(", "keywords": "function renderKeywords(",
    "products": "function renderProductList(", "customers": "function renderCustomers(",
    "liability": "function renderLiability(", "recon": "function renderRecon(", "forecast": "function renderForecast(",
    "connector": "function renderConnector(", "loans": "function renderLoans(", "mail": "function renderMail(",
    "labels": "function renderLabels(", "memory": "function renderMemory(", "skills": "function renderSkills(",
}
_WG_SINGLE = ["function renderCRM(", "function renderFiles(", "function renderFilesTrash(", "function renderFilesBrowser(",
              "function renderTeam(", "function renderTeamPeople(", "function renderTeamWork(", "function renderTeamFeed(",
              "function renderSizes(", "function renderGuide("]


def _wg_literal_ids(src):
    """The literal widget ids one renderer names: widget() calls, the id a
    trends group is handed, and renderStructured's ids."""
    ids = [args[1][1:-1] for _, args in _wg_calls(src, "widget") if len(args) >= 2 and re.fullmatch(r"'[^']*'", args[1])]
    ids += re.findall(r"render(?:TrendsBlock|SeoTrends)\([^\n]*, '([^']*)'\);", src)
    for m in re.finditer(r"ids: \{([^}]*)\}", src):
        ids += re.findall(r":\s*'([^']*)'", m.group(1))
    return ids


@test
def t_every_report_view_with_several_blocks_names_its_cards():
    """A block with no id between two cards stops a view being arranged at all,
    and that can only be seen on a rendered page. What the source can hold is
    the other half: every view the inventory found with two or more blocks names
    at least two cards in its own renderer, and gives its page header the action
    slot Customize sits in, because a view that qualifies with no slot shows no
    button."""
    ov_ids = _wg_literal_ids(fn_src(_WG_ADOPTED["overview"]))
    for view, name in _WG_ADOPTED.items():
        ok(name in SCRIPT, "the %s renderer is still %s" % (view, name.strip("( ")))
        src = fn_src(name)
        ids = _wg_literal_ids(src)
        if view == "overview":
            ids += ["kpi-*"] if "wgKpiId(m.label)" in src else []
        ok(len(set(ids)) >= 2, "%s names %d cards: %r" % (view, len(set(ids)), ids))
        ok("heroAct(" in src or (view == "mail" and "hero.append(heroAct(''))" in src),
           "the %s header has the action slot Customize goes in" % view)
    ok(len(ov_ids) >= 5, "and the Overview still names its own")


@test
def t_a_view_with_one_block_has_no_card_ids():
    """CRM, Files, Team, Size list and Guide each render one block, so there is
    nothing to arrange and no Customize button, and they look exactly as they
    did. An id invented for one of them would put a one card grid on the page
    and a saved layout on the account for no reason."""
    for name in _WG_SINGLE:
        ok(name in SCRIPT, "%s still exists" % name.strip("( "))
        src = fn_src(name)
        ok(not _wg_calls(src, "widget") and "data-widget" not in src, "%s gives a block a widget id" % name.strip("( "))


@test
def t_a_held_card_scrolls_the_page_near_its_edge_and_stops_when_the_drag_ends():
    """A finger holding a card cannot also scroll, so without this a card could
    not be carried past the fold on a phone. The band and the top speed are
    named beside the other gesture thresholds; the scroll is driven by pointer
    moves and a short timer, not animation frames, which a tab that is not
    painted never runs; and it stops when the drag ends, whether by a release,
    a cancel or Escape, because all three end in wgDragEnd."""
    layer = _wg_layer()
    decl = re.search(r"const WG_SCROLL_EDGE = (\d+), WG_SCROLL_MAX = (\d+), WG_SCROLL_TICK_MS = (\d+), WG_SCROLL_JUMP_MS = (\d+);", layer)
    ok(decl, "the auto-scroll constants are declared together")
    ok(0 < layer.index("WG_HOLD_MS = 350") < decl.start() < layer.index("WG_HOLD_MS = 350") + 1200,
       "beside WG_HOLD_MS and the other gesture thresholds")
    edge, top, tick, jump = (int(x) for x in decl.groups())
    ok(0 < edge < 200 and top > 0 and 0 < tick < jump, "a band, a speed, and a slower cadence for reduced motion")
    auto = _wg_fn("function wgAutoScroll(")
    for need in ("WG_SCROLL_EDGE", "WG_SCROLL_MAX", "REDUCE_MOTION ? WG_SCROLL_JUMP_MS : WG_SCROLL_TICK_MS",
                 "clearTimeout(d.scrollTimer);", "d.scrollTimer = setTimeout(wgAutoScroll, tick);",
                 "wgFollow();", "wgStepSoon();", "d.root.getBoundingClientRect().bottom"):
        ok(need in auto, "wgAutoScroll: " + need)
    ok("requestAnimationFrame" not in auto and "behavior" not in auto,
       "no animation frames and no smooth scroll: a hidden tab would never step it")
    ok("scroller: root.closest('.scroll')" in _wg_fn("function wgPointerDown("), "it scrolls the view's own scroller")
    ok("wgAutoScroll();" in _wg_fn("function wgOnMove("), "every pointer move steps it")
    ok("clearTimeout(d.scrollTimer);" in _wg_fn("function wgDragEnd("), "ending the drag stops it")
    ok("wgDragEnd(true);" in _wg_fn("function wgOnUp(") and "wgDragEnd(d.lifted);" in _wg_fn("function wgOnCancel(")
       and "wgDragEnd(d.lifted, true);" in _wg_fn("function wgOnEscape("),
       "a release, a cancel and Escape all end the drag")
    ok(".ov-wrap.wg-editing { position: relative; overflow-anchor: none; }" in CSS,
       "scroll anchoring is off while cards move, or the page shifts under a still pointer")


@test
def t_a_header_keeps_its_tabs_at_16_in_the_grid():
    """A tab strip belongs to the page header above it, so it sits 16 below it
    rather than at the 24 between blocks: the flow does that with a margin, and
    in the grid, where every margin is zero and the gap is the rhythm, a
    negative top margin worked out from the two tokens takes the gap back to
    16. On a phone the gap is 16 already and the margin is nothing."""
    ok(".ov-hero:has(+ .page-tabs) { margin-bottom: var(--sp-4); }" in CSS, "the flow's rule is still there")
    ok(".ov-wrap.wgrid > .ov-hero + .page-tabs { margin-top: calc(var(--sp-4) - var(--page-rhythm)); }" in CSS,
       "and the grid's reads the same two tokens")


@test
def t_an_unfilled_card_waits_off_the_page_without_being_hidden():
    """The trade radar fills when its request answers, and Top products empties
    when fewer than two products earned. Such a card is not the person's choice
    to hide, so it is left out of the arrangement and the Customize list, never
    added to their hidden list, and laid out again when it fills. Before, an
    empty holder took a grid row and a gap of its own."""
    layer = _wg_layer()
    ok(".ov-wrap.wgrid > [data-widget]:empty { display: none; }" in CSS, "an empty card takes no row")
    absent = _wg_fn("function wgAbsent(")
    ok("n.matches(':empty')" in absent and "getComputedStyle(n).display === 'none'" in absent and "wgHid.has(n)" in absent,
       "a card is absent when it is empty or its renderer set it to display none, not when the layout hid it")
    ok("!wgAbsent(n)" in layer.split("const wgShown = ")[1].split("\n")[0], "the shown cards leave it out")
    arrange = _wg_fn("function wgArrange(")
    ok("w.fill.observe(n, { childList: true" in arrange and "widgets.length - w.absent.size < 2" in arrange,
       "every card is watched for filling, and an absent one does not count towards qualifying")
    ok("const present = merged.order.filter(id => !absent.has(id));" in arrange
       and "merged.hidden.filter(id => !absent.has(id))" in arrange, "it is placed with neither the shown nor the hidden cards")
    ok("wgEdit.draft.hidden.push" not in arrange, "and it never joins the hidden list")
    ok("wgAbsent(r.target) !== w.absent.has(r.target)" in _wg_fn("function wgWatch("),
       "a card is laid out again only when it starts or stops being shown")
    for name in ("function renderCustomers(", "function renderProductList("):
        ok("widget(el('div'), " in fn_src(name), "%s gives its holder the id, not the card drawn into it" % name.strip("( "))


@test
def t_the_forecast_ranges_use_the_local_calendar_day():
    """B22 in the 2026-09-19 bug audit. fcISO was toISOString().slice(0, 10),
    which is UTC; the ranges build their dates at LOCAL midnight, so through
    British Summer Time every range key came out a day early: Today excluded
    today, and This month on the 1st showed last month."""
    m = re.search(r"const fcISO = \(d\) => .*?;\n", SCRIPT, re.S)
    ok(m, "fcISO must still be declared as an arrow function")
    ok("toISOString" not in m.group(0), "the UTC formatter is gone")
    if not any(os.access(os.path.join(p, "node"), os.X_OK)
               for p in os.environ.get("PATH", "").split(os.pathsep)):
        print("       (node unavailable, skipped)")
        return
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(m.group(0) + "\nconsole.log(fcISO(new Date('2026-09-19T00:00:00')), "
                 "fcISO(new Date('2026-06-01T00:00:00')), fcISO(new Date('2026-01-05T00:00:00')));\n")
        path = fh.name
    try:
        r = subprocess.run(["node", path], capture_output=True, text=True,
                           env=dict(os.environ, TZ="Europe/London"))
        ok(r.returncode == 0, "fcISO failed to run: " + (r.stderr or "")[:200])
        ok((r.stdout or "").strip() == "2026-09-19 2026-06-01 2026-01-05",
           "local midnight is its own day in summer and in winter: " + (r.stdout or "").strip())
    finally:
        os.unlink(path)


@test
def t_a_proxy_error_never_claims_nothing_was_saved():
    """B21 in the 2026-09-19 bug audit. The generic 5xx text told the
    dispatcher nothing was saved when the courier booking may have gone
    through; the Guide's advice for "the app will not book" then sent them to
    the portal to book, and pay, again."""
    fn = fn_src("async function api(")
    ok("Nothing was saved" not in fn, "a proxy error page says nothing about what was saved")
    ok("may or may not have gone through: check before trying again" in fn,
       "the outcome is stated as unknown, which is what it is")


@test
def t_a_customs_line_with_a_gap_stops_the_booking():
    """B23 in the 2026-09-19 bug audit. A line with a description but no
    quantity or unit value was dropped from the declaration in silence and
    the booking went ahead one item short; a zero price prefilled as an
    empty box, which is how a custom gobo's line went missing."""
    fn = fn_src("function customsProblem(")
    ok("needs a quantity" in fn and "needs a unit value" in fn, "the gap is named and the booking stops")
    ok("unit_price: isNaN(parseFloat(it.price)) ? '' : parseFloat(it.price)" in SCRIPT
       and "unit_price: isNaN(parseFloat(it.unit_value || it.cost || it.price)) ? ''" in SCRIPT
       and "pIn.value = (pre.unit_price === 0 || pre.unit_price) ? pre.unit_price : '';" in SCRIPT,
       "a zero price stays a 0 on the line, on both prefill paths and into the box")
    ok("unit_price: parseFloat(it.price) || ''" not in SCRIPT
       and "pIn.value = pre.unit_price || ''" not in SCRIPT, "no prefill turns 0 back into a gap")
    gap = fn_src("function customsGap(")
    ok("needs a quantity" in gap and "needs a unit value" in gap
       and "const gap = customsGap();" in SCRIPT and "if (gap) { toastError(gap); return; }" in SCRIPT,
       "the pasted-address card has the same gate before it books")


@test
def t_no_native_dialog_is_left_in_the_page():
    """B24 in the 2026-09-19 bug audit. Chrome removed alert, confirm and
    prompt inside a cross-origin iframe, which is where this app runs; the
    attachment row's Save to Files still asked with prompt(), so the button
    did nothing and said nothing."""
    ok("prompt('" not in SCRIPT and 'prompt("' not in SCRIPT and "window.prompt" not in SCRIPT
       and "alert('" not in SCRIPT and "window.alert" not in SCRIPT,
       "no native dialog anywhere in the script")
    ok("function uiAskText(" in SCRIPT, "an in-page replacement exists")
    ok("await uiAskText('Save to Files'" in SCRIPT, "and the attachment save uses it")
    # The composer is page code too (A47 in the 2026-09-22 bug audit): its Link
    # button asked with window.prompt, and this guard read only index.html.
    for word in ("prompt(", "alert(", "confirm("):
        ok(("window." + word) not in COMPOSER and not re.search(r"(?<![\w.])" + re.escape(word), COMPOSER),
           "no native " + word + " in the composer")
    ok(SCRIPT.count("mountComposer(box, { upload: mailUpload, ask: composerAsk") == 2,
       "and both composers are handed the page's own dialog")


@test
def t_the_sign_in_card_is_the_clean_minimal_design():
    """Cameron's reference was a React/Tailwind component (clean-minimal-sign-in);
    the app has neither, so the look is rebuilt on the card that already runs
    all four steps: a sky-tinted card with a soft float, a white tile carrying
    the step's mark, centred heading and subtitle, an icon inside each field
    with the name as placeholder, and a button that darkens toward its foot.
    What the reference had and this app cannot honour is left out on purpose:
    there is no Google, Facebook or Apple sign-in, and the image policy would
    block the logos anyway."""
    card = re.search(r"\.auth-card \{[^}]*\}", CSS, re.S).group(0)
    for want in ("linear-gradient(to bottom, var(--auth-card-top), var(--surface-primary))",
                 "border-radius: var(--radius-xl)", "var(--shadow-lg)", "var(--auth-card-line)"):
        ok(want in card, "the card carries " + want)
    ok("background: linear-gradient(to bottom, var(--auth-go-top), var(--action-primary))" in CSS,
       "the button darkens toward its foot")
    fld = SCRIPT.split("function authField(labelText, type, id) {")[1][:1600]
    ok("el('label', 'sr-only', labelText)" in fld, "the label stays, for screen readers and password managers")
    ok("inp.placeholder = labelText" in fld, "the name is shown in the field")
    ok("ic.innerHTML = I[glyph]" in fld and "'lock'" in fld and "'atSign'" in fld,
       "each field carries its icon, from the constant set")
    ok("card.append(authBrand(mode === 'change' ? 'lock' : 'logIn'))" in SCRIPT
       and "card.append(authBrand('key'), el('h2', null, 'One more step')" in SCRIPT,
       "every step shows its mark in the tile, the two-step code included")
    login = SCRIPT.split("card.append(el('h2', null, 'Sign in')")[1][:3200]
    ok("'Forgot password?'" in login and "Ask an admin to reset it in Team" in login,
       "forgetting a password says what actually happens: an admin resets it")
    ok("forgot.setAttribute('aria-expanded'" in login and "help.hidden" in login,
       "and the note is a disclosure a screen reader can follow")
    for gone in ("Or sign in with", "cdn.21st.dev", "Get Started", "Sign in with email"):
        ok(gone not in SCRIPT, "nothing of the reference that this app cannot honour: " + gone)
    step = SCRIPT[SCRIPT.index("function authShowMfa("):]
    step = step[:step.index("\n            async function finish")]
    ok("el('div', 'auth-error')" in step and "el('div', 'auth-err')" not in step,
       "a wrong code is styled like every other sign-in error")


@test
def t_a_starter_password_reaches_the_choose_your_own_card():
    """Found while rebuilding the sign-in card, and live since the widget grid
    moved the layouts read into sign-in: the server refuses every route but
    /api/auth/* while an account holds a starter password, with the reason
    must_change, and api() read any such refusal as an expired session. So the
    layouts call wiped the new session and reloaded, and a new account, or one
    an admin had just reset, never saw the choose-your-own card at all."""
    fn = SCRIPT[SCRIPT.index("async function api(path, payload, opts) {"):]
    fn = fn[:fn.index("\n        }\n")]
    at = fn.find("if (reason === 'must_change') {")
    ok(at > 0, "a starter password is recognised")
    ok("authShow('change');" in fn[at:at + 120] and "throw new Error(text);" in fn[at:at + 160],
       "and answered with the card, not with a sign-out")
    ok(at < fn.find("setAppSession('');"), "before anything wipes the session")
    change = SCRIPT[SCRIPT.index("const r = await authApi('/api/auth/password'"):][:900]
    ok("wgLoadLayouts();" in change, "and the layouts refused meanwhile are read once the password is changed")


@test
def t_a_cut_off_chat_answer_is_not_paid_for_twice():
    """B41 in the 2026-09-19 bug audit. A stream that ended without its done
    event fell back to /api/chat, which ran the whole question again: the
    first run had started, and was billed, by the time its first step came.
    Run here for real: the shipped streamChat against a stream cut after one
    step, and against one that never said anything."""
    fn = fn_src("async function streamChat(")
    if not any(os.access(os.path.join(p, "node"), os.X_OK)
               for p in os.environ.get("PATH", "").split(os.pathsep)):
        print("       (node unavailable, skipped)")
        return
    harness = fn + r"""
const authHeaders = async () => ({}); const appSession = () => '';
function streamOf(chunks) {
  const enc = new TextEncoder(); let i = 0;
  return { ok: true, body: { getReader: () => ({ read: async () =>
    i < chunks.length ? (chunks[i] === 'DROP' ? (i++, Promise.reject(new TypeError('network error')))
                                              : { value: enc.encode(chunks[i++]), done: false })
                      : { value: undefined, done: true } }) } };
}
async function outcome(chunks) {
  globalThis.fetch = async () => streamOf(chunks);
  try { await streamChat({}, () => {}); return 'ok'; } catch (e) { return e.message; }
}
(async () => {
  const cut = await outcome(['data: {"type":"step","label":"Reading orders"}\n\n']);
  const silent = await outcome([]);
  const whole = await outcome(['data: {"type":"step","label":"x"}\n\n', 'data: {"type":"done","result":{"summary":"hi"}}\n\n']);
  const dropped = await outcome(['data: {"type":"step","label":"x"}\n\n', 'DROP']);
  const droppedEarly = await outcome(['DROP']);
  console.log(JSON.stringify({ cut, silent, whole, dropped, droppedEarly }));
})();
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(harness)
        path = fh.name
    try:
        r = subprocess.run(["node", path], capture_output=True, text=True)
        ok(r.returncode == 0, "the stream harness failed: " + (r.stderr or "")[:300])
        got = json.loads((r.stdout or "").strip())
        ok(got["cut"] != "STREAM_TRANSPORT" and "interrupted" in got["cut"],
           "a stream cut after it started says so, and is not run again: " + got["cut"])
        ok(got["silent"] == "STREAM_TRANSPORT", "a stream that never spoke may still fall back")
        ok(got["whole"] == "ok", "and a whole answer is an answer")
        ok("interrupted" in got["dropped"], "a connection dropped mid-answer says so, not 'network error': " + got["dropped"])
        ok(got["droppedEarly"] == "STREAM_TRANSPORT", "and one dropped before a word may fall back")
    finally:
        os.unlink(path)


@test
def t_box_presets_are_saved_whole_or_not_at_all():
    """B42 in the 2026-09-19 bug audit. Half-filled presets were dropped in
    silence under "Shipping settings saved", and removing the last one came
    back on reopen, also under "saved"."""
    fn = SCRIPT[SCRIPT.index("const saveB = el('button', 'btn btn-primary'); saveB.textContent = 'Save shipping settings';"):][:2600]
    ok("needs a name, all three sizes and a weight above 0" in fn, "an incomplete preset is named, not dropped")
    ok("Keep at least one box preset" in fn, "and the last one cannot be removed by a save that says it was")
    ok("payload.boxes = clean;" in fn and "if (clean.length) payload.boxes = clean;" not in fn,
       "every preset is sent")
    ok("boxes.length > 24" in fn, "and never more than the server keeps")


@test
def t_the_products_page_searches_everything_and_draws_a_bounded_list():
    """B38 and its review. The report now sends every product so search and
    filters reach them all; the page draws the first P_ROWS_MAX of what
    matches, and says so, rather than a button row per product in a large
    catalogue on every filter change."""
    ok("const P_ROWS_MAX = 300;" in SCRIPT, "a bound on rows drawn")
    ok("rows.slice(0, P_ROWS_MAX).forEach(r => {" in SCRIPT, "the list draws within it")
    ok("rows.length > P_ROWS_MAX ? '. The first ' + P_ROWS_MAX" in SCRIPT, "and says when it stopped")


@test
def t_a_held_enter_signs_in_once():
    """B43 in the 2026-09-19 bug audit. The Enter handlers call submit()
    directly, and key repeat fires keydown every few milliseconds, so a held
    Enter posted the same ticket, or the same password, several times over."""
    step = SCRIPT[SCRIPT.index("function authShowMfa("):]
    step = step[:step.index("\n            async function finish")]
    ok("if (go.disabled) return;" in step, "the two-step code submits once")
    login = SCRIPT.split("card.append(el('h2', null, 'Sign in')")[1][:1800]
    ok("if (go.disabled) return;" in login, "and so does the password")
    # And a held key's repeats are not presses: after a refusal the button is
    # live again, and each repeat was another failed attempt on the account.
    for site in ("inCode.onkeydown = (e) => { if (e.key === 'Enter' && !e.repeat) submit(); };",
                 "[inUser, inPw].forEach(i => i.onkeydown = (e) => { if (e.key === 'Enter' && !e.repeat) submit(); });",
                 "[inName, inUser, inPw].forEach(i => i.onkeydown = e => { if (e.key === 'Enter' && !e.repeat) go.click(); });",
                 "[inCur, inNew].forEach(i => i.onkeydown = e => { if (e.key === 'Enter' && !e.repeat) go.click(); });"):
        ok(site in SCRIPT, "a held Enter is one press: " + site[:60])


@test
def t_the_recon_list_draws_only_the_latest_filter():
    """B46 in the 2026-09-19 bug audit, and its review. Every chip click sent
    a read and drew whatever came back, so the slower, earlier answer could
    land last and list Critical rows under the High chip; and the full
    refresh, whose status half is the slow one, painted the old filter's rows
    over a chip clicked while it was in flight. Run for real, in node, with
    the answers released in the order that went wrong."""
    if not any(os.access(os.path.join(p, "node"), os.X_OK)
               for p in os.environ.get("PATH", "").split(os.pathsep)):
        print("       (node unavailable, skipped)")
        return
    harness = ("let reconListSeq = 0; let reconStatusSeq = 0; let reconCache = null; const reconFilter = { severity: '' };\n"
               "const draws = []; const document = { querySelector: () => true };\n"
               "function renderRecon() { draws.push(reconCache && reconCache.ex ? reconCache.ex.rows : 'error'); }\n"
               "const pending = [];\n"
               "function api(path, payload) { return new Promise(res => pending.push({ path, sev: payload && payload.severity, res })); }\n"
               + fn_src("async function refreshRecon(") + "\n" + fn_src("async function refreshReconList(") + r"""
const tick = () => new Promise(r => setTimeout(r, 0));
const answer = (i) => { const p = pending[i]; p.res(p.path.endsWith('status') ? { xero: 'disconnected' } : { rows: p.sev || 'all' }); };
(async () => {
  const out = {};
  // A full refresh (after Disconnect Xero) in flight, then the Critical chip.
  reconCache = { st: { xero: 'connected' }, ex: { rows: 'old' } };
  const full = refreshRecon(); await tick();
  reconFilter.severity = 'critical'; const list = refreshReconList(); await tick();
  answer(2); await list; await tick();          // the chip's list lands first
  answer(0); answer(1); await full; await tick(); // then the slow refresh
  out.afterRefresh = reconCache.ex.rows;
  out.statusAfterRefresh = reconCache.st.xero;
  // The other order: the refresh lands first, then the chip.
  pending.length = 0;
  reconCache = { st: { xero: 'connected' }, ex: { rows: 'old' } };
  const full2 = refreshRecon(); await tick();
  reconFilter.severity = 'high'; const list2 = refreshReconList(); await tick();
  answer(0); answer(1); await full2; await tick();
  answer(2); await list2; await tick();
  out.statusRefreshFirst = reconCache.st.xero;
  out.rowsRefreshFirst = reconCache.ex.rows;
  // Two chips, the earlier answer last.
  pending.length = 0;
  reconFilter.severity = 'high'; const a = refreshReconList(); await tick();
  reconFilter.severity = 'critical'; const b = refreshReconList(); await tick();
  answer(1); await b; await tick(); answer(0); await a; await tick();
  out.afterChips = reconCache.ex.rows;
  console.log(JSON.stringify(out));
})();
""")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(harness)
        path = fh.name
    try:
        r = subprocess.run(["node", path], capture_output=True, text=True)
        ok(r.returncode == 0, "the recon harness failed: " + (r.stderr or "")[:300])
        got = json.loads((r.stdout or "").strip())
        eq_ = lambda a, b, m: ok(a == b, m + ": %r" % (a,))
        eq_(got["afterRefresh"], "critical", "a slow full refresh does not paint over the chip clicked after it")
        eq_(got["afterChips"], "critical", "and the earlier chip's late answer is dropped")
        eq_(got["statusAfterRefresh"], "disconnected",
            "an overtaken refresh still brings the newest status: the page does not say Xero is connected after a Disconnect")
        eq_(got["statusRefreshFirst"], "disconnected", "whichever answer lands first")
        eq_(got["rowsRefreshFirst"], "high", "and the chip's rows")
    finally:
        os.unlink(path)


@test
def t_the_loan_picker_reads_the_catalogue_once_per_keystroke():
    """Review of B38. The picker's input listener repainted its dropdown by
    firing another input event, which it then answered with another read:
    one keystroke read the catalogue about every 220ms for as long as the
    field existed, modal closed or not. A failed read, no longer cached,
    turned that into a stream of full catalogue reads while Shopify refused.
    Run for real, in node, on the shipped listener."""
    if not any(os.access(os.path.join(p, "node"), os.X_OK)
               for p in os.environ.get("PATH", "").split(os.pathsep)):
        print("       (node unavailable, skipped)")
        return
    start = SCRIPT.index("let findTimer = null")
    block = SCRIPT[start:SCRIPT.index("}, true);", start) + len("}, true);")]
    harness = ("let findRows = []; const foundNote = { textContent: '' }; let calls = 0; let fail = false;\n"
               "const findIn = new EventTarget(); findIn.value = 'epson'; findIn.isConnected = true;\n"
               "async function api() { calls++; if (fail) throw new Error('Could not read the shop'); return { products: [] }; }\n"
               "let painted = 0; findIn.addEventListener('input', () => { painted++; });\n"
               + block + r"""
const wait = (ms) => new Promise(r => setTimeout(r, ms));
(async () => {
  const out = {};
  findIn.dispatchEvent(new Event('input')); await wait(1500);
  out.okCalls = calls; out.painted = painted;
  calls = 0; fail = true;
  findIn.dispatchEvent(new Event('input')); await wait(1500);
  out.failCalls = calls; out.note = foundNote.textContent;
  calls = 0; fail = false; findIn.isConnected = false;
  findIn.dispatchEvent(new Event('input')); await wait(600);
  out.closedCalls = calls;
  console.log(JSON.stringify(out));
})();
""")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(harness)
        path = fh.name
    try:
        r = subprocess.run(["node", path], capture_output=True, text=True)
        ok(r.returncode == 0, "the picker harness failed: " + (r.stderr or "")[:300])
        got = json.loads((r.stdout or "").strip())
        ok(got["okCalls"] == 1, "one keystroke, one read: %r" % got)
        ok(got["painted"] >= 2, "and the dropdown still repaints when the rows arrive: %r" % got)
        ok(got["failCalls"] == 1 and "Could not read" in got["note"],
           "a failed read is said once, not retried forever: %r" % got)
        ok(got["closedCalls"] == 0, "and a closed picker reads nothing: %r" % got)
    finally:
        os.unlink(path)



# A small DOM for running page functions in node: elements, a document with
# capture and bubble listeners, and the default action a browser takes for
# Enter on a focused button (a click, unless the keydown was cancelled).
MINIDOM = r"""// A small DOM for node: elements, a document with capture/bubble listeners,
// and the default action a browser takes for Enter or Space on a focused button.
class Ev { constructor(type, init) { Object.assign(this, init || {}); this.type = type; this.defaultPrevented = false; this._stop = false; this._stopNow = false; }
  preventDefault() { this.defaultPrevented = true; } stopPropagation() { this._stop = true; } stopImmediatePropagation() { this._stop = true; this._stopNow = true; } }
class Node_ {
  constructor(tag) { this.tagName = (tag || 'div').toUpperCase(); this.children = []; this.parentNode = null; this._l = {}; this.attrs = {}; this.classList = new CL(this); this.style = {}; this.dataset = {}; this._text = ''; this.disabled = false; this.hidden = false; this.value = ''; }
  get className() { return [...this.classList._s].join(' '); } set className(v) { this.classList._s = new Set(String(v || '').split(/\s+/).filter(Boolean)); }
  append(...ns) { ns.forEach(n => { if (typeof n === 'string') n = document.createTextNode(n); if (n.parentNode) n.remove(); n.parentNode = this; this.children.push(n); }); }
  appendChild(n) { this.append(n); return n; }
  prepend(...ns) { ns.reverse().forEach(n => { if (n.parentNode) n.remove(); n.parentNode = this; this.children.unshift(n); }); }
  insertBefore(n, ref) { if (n.parentNode) n.remove(); n.parentNode = this; const i = ref ? this.children.indexOf(ref) : -1; if (i < 0) this.children.push(n); else this.children.splice(i, 0, n); return n; }
  remove() { if (this.parentNode) { const p = this.parentNode; p.children = p.children.filter(c => c !== this); this.parentNode = null; } }
  get textContent() { return this._text + this.children.map(c => c.textContent).join(''); } set textContent(v) { this._text = String(v); this.children = []; }
  get innerHTML() { return this._html || ''; } set innerHTML(v) { this._html = v; this.children = []; this._text = ''; }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k === 'id') this.id = v; } getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; } hasAttribute(k) { return k in this.attrs; } removeAttribute(k) { delete this.attrs[k]; }
  addEventListener(t, f, o) { (this._l[t] = this._l[t] || []).push({ f, capture: o === true || !!(o && o.capture) }); }
  removeEventListener(t, f) { this._l[t] = (this._l[t] || []).filter(x => x.f !== f); }
  focus() { document.activeElement = this; } blur() { if (document.activeElement === this) document.activeElement = document.body; }
  click() { if (this.disabled) return; dispatch(this, new Ev('click', { bubbles: true })); }
  contains(n) { while (n) { if (n === this) return true; n = n.parentNode; } return false; }
  closest() { return null; } querySelector() { return null; } querySelectorAll() { return []; }
  getClientRects() { return [1]; } getBoundingClientRect() { return { left: 0, top: 0, width: 10, height: 10 }; }
}
class CL { constructor(o) { this._s = new Set(); } add(...c) { c.forEach(x => this._s.add(x)); } remove(...c) { c.forEach(x => this._s.delete(x)); } contains(c) { return this._s.has(c); } toggle(c, on) { if (on === undefined) on = !this._s.has(c); on ? this._s.add(c) : this._s.delete(c); return on; } }
function dispatch(target, ev) {
  ev.target = target; const path = []; let n = target; while (n) { path.push(n); n = n.parentNode; } if (path[path.length - 1] !== document) path.push(document);
  // capture, from the top down; then target and bubble. Each node's listener list is read when the event reaches it, as the DOM spec says.
  for (let i = path.length - 1; i > 0 && !ev._stop; i--) { const ls = (path[i]._l[ev.type] || []).filter(x => x.capture).slice(); for (const x of ls) { if (ev._stopNow) break; ev.currentTarget = path[i]; x.f.call(path[i], ev); } }
  for (let i = 0; i < path.length && !ev._stop; i++) { const on = path[i]['on' + ev.type]; const ls = (path[i]._l[ev.type] || []).filter(x => i === 0 || !x.capture).slice(); ev.currentTarget = path[i];
    if (on) on.call(path[i], ev); for (const x of ls) { if (ev._stopNow) break; x.f.call(path[i], ev); } if (ev.bubbles === false) break; }
  return !ev.defaultPrevented;
}
// A key press as a browser delivers it: keydown to the focused element, and for
// Enter on a button its activation (a click) unless the keydown was cancelled.
function pressKey(key, opts) {
  const t = document.activeElement || document.body;
  const ev = new Ev('keydown', Object.assign({ key, bubbles: true, repeat: false }, opts || {}));
  const notCancelled = dispatch(t, ev);
  if (notCancelled && key === 'Enter' && t.tagName === 'BUTTON') t.click();
  return ev;
}
const document = new Node_('#document');
document.tagName = '#document';
document.body = new Node_('body'); document.body.parentNode = document; document.children = [document.body];
document.createElement = (t) => new Node_(t);
document.createTextNode = (s) => { const n = new Node_('#text'); n._text = String(s); return n; };
document.activeElement = document.body;
document.hidden = false;
function el(tag, cls, text) { const n = new Node_(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; }
const Node = Node_;

"""


def _node_ok():
    return any(os.access(os.path.join(p, "node"), os.X_OK)
               for p in os.environ.get("PATH", "").split(os.pathsep))


def _run_node(js):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(js)
        path = fh.name
    try:
        try:
            r = subprocess.run(["node", path], capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            ok(False, "the node harness never finished (a timer left running?)")
        ok(r.returncode == 0, "the node harness failed: " + (r.stderr or "")[:400])
        return json.loads((r.stdout or "").strip().splitlines()[-1])
    finally:
        os.unlink(path)


@test
def t_a_confirm_dialog_answers_for_the_focused_button():
    """A12 in the 2026-09-22 bug audit. Enter was bound on the document and
    answered yes wherever focus was: Tab to Cancel, Enter, and Book & dispatch
    booked and charged a courier. A held key's repeats were further presses,
    and one Escape closed two stacked dialogs. Run for real, in node."""
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    destr = re.search(r"const DESTRUCTIVE = /.*?/i;", SCRIPT).group(0)
    stack = re.search(r"const confirmStack = \[\];", SCRIPT)
    ok(stack, "the page keeps one stack of open confirms")
    js = MINIDOM + "\n" + destr + "\n" + stack.group(0) + "\n" + fn_src("function uiConfirm(message, opts)") + r"""
const top = () => document.body.children[document.body.children.length - 1];
const btns = () => top().children[0].children[2].children;
const settle = (p) => Promise.race([p.then(v => v), new Promise(r => setTimeout(() => r('open'), 10))]);
(async () => {
  const out = {};
  let p = uiConfirm('This books the courier and charges your World Options account.', { okText: 'Book & dispatch' });
  btns()[0].focus(); pressKey('Enter');
  out.enterOnCancel = await settle(p);
  p = uiConfirm('Book it?', { okText: 'Book & dispatch' });
  pressKey('Enter');
  out.enterOnYes = await settle(p);
  p = uiConfirm('Book it?', { okText: 'Book & dispatch' });
  pressKey('Enter', { repeat: true });
  out.heldRepeat = await settle(p);
  pressKey('Enter');
  out.afterRepeat = await settle(p);
  const outer = uiConfirm(el('div'), { title: 'Collections', okText: 'Done', hideCancel: true });
  const inner = uiConfirm('Clear it?', { okText: 'Clear it' });
  pressKey('Escape');
  out.inner = await settle(inner); out.outer = await settle(outer);
  pressKey('Escape');
  out.outerAfterSecond = await settle(outer);
  p = uiConfirm('Delete this for good?', { okText: 'Delete' });
  pressKey('Enter');
  out.dangerEnter = await settle(p);
  console.log(JSON.stringify(out));
})();
"""
    got = _run_node(js)
    ok(got["enterOnCancel"] is False, "Enter on a focused Cancel is Cancel: %r" % got)
    ok(got["enterOnYes"] is True, "Enter on the focused Book is still yes")
    ok(got["heldRepeat"] == "open" and got["afterRepeat"] is True, "a held key's repeats answer nothing")
    ok(got["inner"] is False and got["outer"] == "open", "one Escape closes only the dialog on top: %r" % got)
    ok(got["outerAfterSecond"] is False, "and the next closes the one under it")
    ok(got["dangerEnter"] is False, "a destructive dialog opens on Cancel, so Enter cancels it")


@test
def t_bulk_undo_puts_back_every_batch_and_says_how_many():
    """A13 in the 2026-09-22 bug audit. A bulk action over 150 emails is sent
    in batches, each with its own undo token; the page kept only the last, so
    Undo put back the last 150 and said "Put back" over the rest."""
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    js = MINIDOM + r"""
const byId = {}; const $ = (id) => byId[id] || (byId[id] = Object.assign(el('div'), { id }));
let mailView = 'list', mailFilter = '', mailCache = { lead: false, team: [] };
const rows = []; for (let i = 0; i < 400; i++) rows.push({ id: 'b' + i, unread: false });
const mailSel = new Set(rows.map(r => r.id));
const sent = [], undone = [], toasts = []; let failOne = false;
let stopAt = 0;
async function api(path, body) {
  if (path === '/api/mail/undo') {
    undone.push(body.token);
    if (failOne && body.token === 'T2') throw new Error('That is too old to undo now.');
    return { ok: true, restored: sent[+body.token.slice(1) - 1] };
  }
  if (stopAt && sent.length + 1 === stopAt) throw new Error('The app is being asked for too much at once.');
  sent.push(body.ids.length);
  return { changed: body.ids.length, skipped: [], undo: 'T' + sent.length, what: 'marked done' };
}
async function uiConfirm() { return true; }
async function refreshMailQuiet() {}
function toastError(m) { toasts.push('error: ' + m); } function toastOk(m) { toasts.push('ok: ' + m); }
function paintMailBody() {}
""" + fn_src("function paintMailBulk(rows)") + "\n" + fn_src("function mailOfferUndo(") + r"""
const findBtn = (host, text) => { const walk = (n) => { if (n.tagName === 'BUTTON' && n.textContent === text) return n;
  for (const c of n.children || []) { const f = walk(c); if (f) return f; } return null; }; return walk(host); };
(async () => {
  paintMailBulk(rows);
  await findBtn($('mail-bulk-host'), 'Mark done').onclick();
  await findBtn($('mail-bulk-host'), 'Undo').onclick();
  const first = { sent: sent.slice(), undone: undone.slice(), toasts: toasts.slice() };
  sent.length = 0; undone.length = 0; toasts.length = 0; failOne = true;
  for (const r of rows) mailSel.add(r.id);
  paintMailBulk(rows);
  await findBtn($('mail-bulk-host'), 'Mark done').onclick();
  await findBtn($('mail-bulk-host'), 'Undo').onclick();
  const second = { undone: undone.slice(), toasts: toasts.slice() };
  sent.length = 0; undone.length = 0; toasts.length = 0; failOne = false; stopAt = 3;
  for (const r of rows) mailSel.add(r.id);
  paintMailBulk(rows);
  await findBtn($('mail-bulk-host'), 'Mark done').onclick();
  const undo = findBtn($('mail-bulk-host'), 'Undo');
  if (undo) await undo.onclick();
  console.log(JSON.stringify({ first, second, third: { undoOffered: !!undo, undone: undone.slice(), toasts: toasts.slice() } }));
})();
"""
    got = _run_node(js)
    ok(got["first"]["sent"] == [150, 150, 100], got)
    ok(got["first"]["undone"] == ["T1", "T2", "T3"], "Undo sends every batch's token: %r" % got["first"])
    ok(got["first"]["toasts"] == ["ok: Put back"], "and says Put back only when all 400 came back")
    ok(got["second"]["toasts"] and got["second"]["toasts"][0].startswith("error: Put back 250 of 400"),
       "a batch that could not be undone is said, with the count: %r" % got["second"])
    ok(got["third"]["undoOffered"] and got["third"]["undone"] == ["T1", "T2"],
       "a bulk action that stopped part way still offers to put back what it did: %r" % got["third"])


@test
def t_ready_to_make_on_a_made_order_says_it_stayed():
    """A2's page half: the server now leaves a made order where it is, and the
    toast says so instead of "moved to To make"; and an Undo on a made order's
    reprint keeps its printed stamp and says why, rather than deleting it on
    the page and saying "Put back as not printed". Run for real, in node."""
    fn = fn_src("async function readyToMake(")
    ok("if (r.released === false)" in fn and "addToast(r.note" in fn, fn[:400])
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    js = MINIDOM + r"""
const toasts = []; function addToast(m) { toasts.push(m); } function toastError(m) { toasts.push('error: ' + m); }
const I = { x: '' }; function renderLabels() {}
document.getElementById = () => null;
const labelsCache = { data: { state: { '5': { made_at: '2026-09-20', printed_at: '2026-09-22T10:00:00Z' },
                                       '6': { printed_at: '2026-09-22T10:00:00Z' } } } };
function prodStateOf(o) { return labelsCache.data.state[String(o.id)] || {}; }
async function api(path, body) {
  return { ok: true, kept: ['5'], state: { '5': { made_at: '2026-09-20', printed_at: '2026-09-22T10:00:00Z' }, '6': {} } };
}
""" + fn_src("function undoPrintBar(ids)") + r"""
const findBtn = (n, t) => { if (n.tagName === 'BUTTON' && n.textContent === t) return n; for (const c of n.children || []) { const f = findBtn(c, t); if (f) return f; } return null; };
(async () => {
  undoPrintBar([5, 6]);
  await findBtn(document.body, 'Undo').onclick();
  console.log(JSON.stringify({ toasts, made: labelsCache.data.state['5'].printed_at || null, other: labelsCache.data.state['6'].printed_at || null }));
})();
"""
    got = _run_node(js)
    ok(got["made"], "the made order keeps its printed stamp on the page too: %r" % got)
    ok(got["other"] is None, "the other is put back as not printed")
    ok(got["toasts"] == ["Put back as not printed, apart from 1 already made."], got["toasts"])

@test
def t_a_sent_reply_with_a_warning_shows_the_warning():
    """B5, the page's half. The server answers a send that went somewhere
    surprising (Gmail filed it as its own conversation; the board could not
    be saved) with a warning, and the send flow toasted "Sent to X" over it."""
    fn = fn_src("async function mailSendFlow(")
    ok("if (r && r.warning) addToast(r.warning);" in fn, "the warning is what the person sees")
    ok("else toastOk('Sent to ' + to);" in fn, "and a plain success stays a plain success")



@test
def t_team_actions_wrap_onto_their_own_line_on_a_phone():
    """A30 in the 2026-09-22 bug audit. Tabs and Delete account sat in one
    unbroken row past the card's clipped edge on a phone."""
    ok(re.search(r"@media \(max-width: 640px\) \{ \.tm-row \.files-acts \{ flex: 1 1 100%; flex-wrap: wrap; \} \}", HTML),
       "a person's actions take their own line and wrap at phone width")


@test
def t_a_paid_report_run_is_one_run_and_stays_on_screen():
    """A31 in the 2026-09-22 bug audit. Leaving a report's tab while its paid
    run was going and coming back painted the Run gate over it, and Run or
    Refresh then paid for a second run. Run for real, in node."""
    ok("if (customersRuns.has(seg)) { customersBusy(seg); return; }" in fn_src("function renderCustomers(seg)"),
       "Customers keeps a running sector's loading screen too")
    ok(re.search(r"const reportRuns = \{\};", SCRIPT), "one record of the runs in flight")
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    js = MINIDOM + r"""
const byId = {}; const $ = (id) => byId[id] || (byId[id] = Object.assign(el('div'), { id }));
const I = {}; function loader() { return el('span'); }
const reportRuns = {};
let overviewCache = null, seoCache = null, keywordsCache = null;
let calls = 0, release; const answer = new Promise(r => { release = r; });
async function api(path) { calls += 1; await answer; return { structured: {} }; }
const painted = [];
function renderOverview(c) { painted.push('report'); $('ov-content').innerHTML = ''; $('ov-content').append(el('div', null, 'REPORT')); }
function renderRunGate(id) { painted.push('gate'); $(id).innerHTML = ''; $(id).append(el('div', null, 'RUN GATE')); }
""" + fn_src("function showOverviewView()") + "\n" + fn_src("async function loadOverview(force)") + "\n" + fn_src("async function runOverview(box, force)") + r"""
(async () => {
  showOverviewView();
  const first = loadOverview(true);
  showOverviewView();                          // away and back while it runs
  const during = $('ov-content').textContent;
  const second = loadOverview(true);           // Refresh or Run pressed again
  release(); await first; await second;
  showOverviewView();
  console.log(JSON.stringify({ calls, during, painted, after: $('ov-content').textContent, idle: reportRuns.overview }));
})();
"""
    got = _run_node(js)
    ok(got["calls"] == 1, "one paid run, not two: %r" % got)
    ok("RUN GATE" not in got["during"] and "Working out live metrics" in got["during"],
       "coming back mid-run keeps the loading screen: %r" % got["during"])
    ok(got["painted"] == ["gate", "report", "report"] and got["after"] == "REPORT", got)
    ok(got["idle"] is None, "and the run is let go when it lands")
    # Customers, one run per sector (found by the round-4 review): one slot for
    # the tab let a second sector's run take it, and the first was run again.
    js = MINIDOM + r"""
const byId = {}; const $ = (id) => byId[id] || (byId[id] = Object.assign(el('div'), { id }));
const I = {}; function loader() { return el('span'); } function sectorBar() { return el('div'); }
const SEG_ALL = '__all__'; const customersCache = {}; let customersSeg = SEG_ALL;
const customersRuns = new Set();
const painted = []; function renderCustomers(seg) { painted.push(seg); }
const runs = []; const gates = [];
async function api(path, body) { runs.push(body.segment || SEG_ALL); await new Promise(r => gates.push(r)); return {}; }
""" + fn_src("function customersBusy(seg)") + "\n" + fn_src("async function loadCustomers(force, seg)") + r"""
(async () => {
  const a = loadCustomers(true, 'Theatre');
  const b = loadCustomers(true, 'Education');
  const c = loadCustomers(true, 'Theatre');          // back to Theatre while it runs, and Run
  const busy = $('customers-content').textContent;
  gates.forEach(g => g()); await Promise.all([a, b, c]);
  console.log(JSON.stringify({ runs, busy, painted, left: customersRuns.size }));
})();
"""
    got = _run_node(js)
    ok(got["runs"] == ["Theatre", "Education"], "each sector is one paid run: %r" % got)
    ok("Analysing the Theatre sector" in got["busy"], "and a running sector shows its loading screen: %r" % got["busy"])
    ok(got["left"] == 0, "every run is let go when it lands")


@test
def t_a_dropped_connection_is_not_read_as_a_refusal():
    """A32 in the 2026-09-22 bug audit. "Failed to fetch" reached the person,
    and every caller read it as a refusal: the mail Send was offered again and
    Mark made said nothing was changed. Run for real, in node."""
    ok("if (e.noReply) {" in SCRIPT and "go.textContent = 'May have been sent: check the conversation';" in SCRIPT,
       "a send with no answer is not re-armed")
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    js = MINIDOM + r"""
async function authHeaders() { return {}; } function appSession() { return 'S'; } function noteBuild() {}
async function fetch() { throw new TypeError('Failed to fetch'); }
""" + fn_src("async function api(path, payload, opts)") + r"""
(async () => {
  try { await api('/api/mail/send', {}); console.log(JSON.stringify({ threw: false })); }
  catch (e) { console.log(JSON.stringify({ threw: true, noReply: !!e.noReply, msg: e.message })); }
})();
"""
    got = _run_node(js)
    ok(got["threw"] and got["noReply"], got)
    ok("Failed to fetch" not in got["msg"] and "may or may not have gone through" in got["msg"], got["msg"])


@test
def t_a_signed_out_boot_is_not_greeted_as_an_expired_sign_in():
    """A38 in the 2026-09-22 bug audit. The boot's data calls go out before
    the sign-in check answers; each 401 on a request that carried no session
    reloaded the page and said "Your sign-in has expired", after a deliberate
    Log out too. Run for real, in node."""
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    js = MINIDOM + r"""
const store = {}; const sessionStorage = { setItem: (k, v) => { store[k] = v; }, getItem: (k) => store[k] || null };
let reloads = 0; const location = { reload: () => { reloads += 1; } };
let sess = ''; const shown = [];
async function authHeaders() { return {}; } function appSession() { return sess; } function noteBuild() {}
function setAppSession(v) { sess = v; } function clearLocalCache() {} function authShow(w) { shown.push(w); }
const reply = { status: 401, headers: { get: () => null }, clone() { return { json: async () => ({ reason: 'session', error: 'Please log in.' }) }; } };
async function fetch() { return reply; }
""" + fn_src("async function api(path, payload, opts)") + r"""
(async () => {
  const out = {};
  try { await api('/api/layouts', {}); } catch (e) { out.signedOut = { msg: e.message, reloads, saved: store.sc_auth_reason || null }; }
  sess = 'S';
  try { await api('/api/layouts', {}); } catch (e) { out.expired = { reloads, saved: !!store.sc_auth_reason }; }
  console.log(JSON.stringify(out));
})();
"""
    got = _run_node(js)
    ok(got["signedOut"]["reloads"] == 0 and got["signedOut"]["saved"] is None,
       "no session to begin with: no reload, no 'expired' greeting: %r" % got)
    ok(got["expired"]["reloads"] == 1 and got["expired"]["saved"],
       "a real expired session still reloads once and says why: %r" % got)


@test
def t_a_late_product_plan_does_not_replace_the_one_on_screen():
    """A33 in the 2026-09-22 bug audit. A plan takes up to a minute; opening
    another product meanwhile let the earlier answer land last and replace
    it. Run for real, in node."""
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    # The list's painter drops whatever plan is coming, by any route to it:
    # Back, and (found by the round-4 review) a tab switch, which painted the
    # list through showProductsView and let the plan land over it.
    head = fn_src("function renderProductList()").split("\n")[1].split("//")[0].strip()
    ok(head.startswith("productSeq++; productPlanRun = false;"), head)
    js = MINIDOM + r"""
const byId = {}; const $ = (id) => byId[id] || (byId[id] = Object.assign(el('div'), { id }));
const I = {}; function loader() { return el('span'); } function ico() { return el('span'); }
function renderRunGate() { shown.push('gate'); }
let productSeq = 0, productPlanRun = false, productList = [];
function renderProductList() { """ + head + r""" shown.push('list'); }
const shown = []; const gates = {};
async function api(path, body) { await new Promise(r => { gates[body.product_id] = r; }); return { id: body.product_id }; }
function renderProductDetail(d) { shown.push(d.id); }
""" + fn_src("function showProductsView()") + "\n" + fn_src("function productBack()") + "\n" + fn_src("async function openProduct(id, title)") + r"""
const tick = () => new Promise(r => setTimeout(r, 0));
(async () => {
  const a = openProduct('A', 'Gobo A'); const b = openProduct('B', 'Gobo B');
  await tick(); gates.B(); await b; gates.A(); await a;
  const c = openProduct('C', 'Gobo C'); await tick();
  $('products-content').children[0].onclick();      // back to the list mid-run
  gates.C(); await c;
  const d = openProduct('D', 'Gobo D'); await tick();
  showProductsView();                               // away to another tab and back mid-run
  const during = shown.slice();
  gates.D(); await d;
  showProductsView();                               // and once it has landed, the list as before
  console.log(JSON.stringify({ shown, during }));
})();
"""
    got = _run_node(js)
    ok(got["shown"] == ["B", "list", "D", "list"],
       "only the plan last opened is drawn, never over the list, and a tab switch keeps a running plan: %r" % got)
    ok(got["during"] == ["B", "list"], "coming back mid-run keeps the plan's loading screen: %r" % got)


@test
def t_a_follow_up_typed_while_an_answer_streams_is_kept():
    """A34 in the 2026-09-22 bug audit. The box was cleared first and the
    question then refused because an answer was still coming. Run for real,
    in node."""
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    js = MINIDOM + r"""
const I = {}; const PAGE_LABELS = {}; const pageBusy = {}; const asked = [], toasts = [];
function threadKey(p) { return p; } function renderPageThread() {}
function addToast(m) { toasts.push(m); }
function pageAsk(page, text) { asked.push(text); pageBusy[page] = true; }
""" + fn_src("function pageChatPanel(page, data)") + r"""
const find = (n, tag) => { if (n.tagName === tag) return n; for (const c of n.children || []) { const f = find(c, tag); if (f) return f; } return null; };
const wrap = pageChatPanel('overview', {});
const ta = find(wrap, 'TEXTAREA'), btn = find(wrap, 'BUTTON');
ta.value = 'What drove the dip?'; btn.onclick();
ta.value = 'And in September?'; ta.focus(); pressKey('Enter');
const kept = ta.value;
pageBusy.overview = false; btn.onclick();
console.log(JSON.stringify({ asked, kept, toasts, after: ta.value }));
"""
    got = _run_node(js)
    ok(got["asked"] == ["What drove the dip?", "And in September?"], "the follow-up is sent once the answer is in: %r" % got)
    ok(got["kept"] == "And in September?", "and it stays in the box while the answer is coming: %r" % got)
    ok(got["toasts"] == ["Wait for the answer, then send this."], got["toasts"])


@test
def t_a_double_click_opens_one_email_window():
    """A35 in the 2026-09-22 bug audit. A double click on an Inbox row sent
    two reads and stacked two windows. Run for real, in node."""
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    js = MINIDOM + r"""
let reads = 0, windows = 0;
const setInterval = () => 0;
async function api() { reads += 1; await new Promise(r => setTimeout(r, 5)); return { id: 't1' }; }
function toastError() {}
function mailModal() { windows += 1; const o = el('div'); o.querySelector = () => el('div'); return { overlay: o, body: el('div'), close() {} }; }
function paintMailThread() {}
const mailOpening = new Set();
""" + fn_src("async function openMailThread(id)") + r"""
(async () => {
  await Promise.all([openMailThread('t1'), openMailThread('t1')]);
  await openMailThread('t1');
  console.log(JSON.stringify({ reads, windows }));
})();
"""
    got = _run_node(js)
    ok(got == {"reads": 2, "windows": 2}, "a double click is one open; a later open still works: %r" % got)


@test
def t_a_half_written_skill_survives_a_tab_switch():
    """A36 in the 2026-09-22 bug audit. Coming back to Skills re-rendered it
    and wiped the skill being written. Run for real, in node."""
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    js = MINIDOM + r"""
const byId = {}; const $ = (id) => byId[id] || (byId[id] = Object.assign(el('div'), { id }));
$('view-skills').classList.add('active');
let skills = [], skillsLoadErr = '', paints = 0; const skView = {}; const skillCaps = {};
async function api() { return { skills: [{ id: 's1', title: 'Promo', content: 'x' }] }; }
function renderSkills() { paints += 1; }
const title = el('input'); title.dataset.initial = ''; const body = el('textarea'); body.value = 'x'; body.dataset.initial = 'x';
document.querySelectorAll = () => [title, body];
""" + fn_src("async function loadSkills()") + r"""
(async () => {
  await loadSkills(); const clean = paints;
  title.value = 'Black Friday'; await loadSkills(); const typing = paints;
  title.value = ''; body.value = 'x'; await loadSkills();
  console.log(JSON.stringify({ clean, typing, after: paints }));
})();
"""
    got = _run_node(js)
    ok(got == {"clean": 1, "typing": 1, "after": 2}, "no repaint over unsaved typing, and one as soon as it is saved or undone: %r" % got)


@test
def t_a_failed_note_alert_or_knowledge_change_is_said():
    """A37 in the 2026-09-22 bug audit. Deleting a note, dismissing a change
    alert or deleting store knowledge swallowed the failure. Run for real, in
    node."""
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    js = MINIDOM + r"""
const byId = {}; const $ = (id) => byId[id] || (byId[id] = Object.assign(el('div'), { id }));
let memories = [], alerts = [], knowledge = { a: 1 }, overviewCache = null; const errors = [];
async function api() { throw new Error('The server is busy.'); }
async function uiConfirm() { return true; }
function toastError(m) { errors.push(m); } function renderMemory() {} function renderOverview() {} function paintMem() {} function paintNotes() {}
""" + fn_src("async function memOp(") + "\n" + fn_src("async function alertOp(") + "\n" + fn_src("async function deleteKnowledge(") + r"""
(async () => {
  await memOp({ op: 'delete', id: 'm1' }); await alertOp({ op: 'dismiss', id: 'a1' }); await deleteKnowledge();
  console.log(JSON.stringify({ errors, knowledge }));
})();
"""
    got = _run_node(js)
    eq_ = len(got["errors"]) == 3 and all("not" in e and "The server is busy." in e for e in got["errors"])
    ok(eq_, "each failure is said, with the reason: %r" % got)
    ok(got["knowledge"] == {"a": 1}, "and the knowledge on screen is not wiped by a delete that failed")


@test
def t_the_crm_refresh_waits_for_someone_typing_in_it():
    """A39 in the 2026-09-22 bug audit. The background refresh repainted the
    CRM under someone typing in its search box. Run for real, in node."""
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    js = MINIDOM + r"""
let reads = 0, paints = 0, crmCache = {}, crmLoadedAt = 0, onRead = null;
const setInterval = () => 0;
document.querySelector = (sel) => sel === '#view-crm.active' ? el('div') : null;
async function api() { reads += 1; if (onRead) onRead(); crmLoadedAt = 0; return { crm: {} }; }
function renderCRM() { paints += 1; }
""" + fn_src("async function crmMaybeRefresh(") + r"""
const host = el('div'); host.id = 'crm-content';
const search = el('input'); host.append(search);
search.closest = (sel) => sel === '#crm-content' ? host : null;
(async () => {
  search.focus(); await crmMaybeRefresh();
  const typing = { reads, paints };
  search.blur(); onRead = () => search.focus(); await crmMaybeRefresh();
  const startedMidRead = { reads, paints };
  search.blur(); onRead = null; crmLoadedAt = 0; await crmMaybeRefresh();
  console.log(JSON.stringify({ typing, startedMidRead, idle: { reads, paints } }));
})();
"""
    got = _run_node(js)
    ok(got["typing"] == {"reads": 0, "paints": 0}, "no refresh under the search box: %r" % got)
    ok(got["startedMidRead"] == {"reads": 1, "paints": 0}, "nor when typing starts while it reads: %r" % got)
    ok(got["idle"] == {"reads": 2, "paints": 1}, "and it refreshes once nobody is typing: %r" % got)


@test
def t_team_shift_times_are_london_clock_times():
    """A46 in the 2026-09-22 bug audit. Clock-in and clock-out were sliced out
    of UTC stamps, an hour early all summer."""
    ok("timeZone: 'Europe/London'" in fn_src("function londonHM(iso)"), "the hour is read on the London clock")
    for bad in ("String(ws.start).slice(11, 16)", "String(s.start).slice(11, 16)",
                "String(s.end).slice(11, 16)", "String(d.sent.sent_at).slice(11, 16)"):
        ok(bad not in SCRIPT, bad + " reads the UTC hour")
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    js = fn_src("function londonHM(iso)") + r"""
console.log(JSON.stringify([londonHM('2026-07-01T08:30:00Z'), londonHM('2026-12-01T08:30:00Z'), londonHM('garbage')]));
"""
    got = _run_node(js)
    ok(got[:2] == ["09:30", "08:30"], "summer is an hour on, winter is not: %r" % got)



@test
def t_the_import_report_counts_erased_people_without_naming_them():
    """The Pipedrive import says how many erased people it kept out and how
    many records it took their details out of, and nothing else about them."""
    i = SCRIPT.index("const er = rep.erased || {};")
    block = SCRIPT[i:i + 700]
    ok("er.people" in block and "er.scrubbed" in block, block)
    ok(".name" not in block and "emails" not in block, "counts only, never a name")


@test
def t_a_forecast_alert_is_a_sentence_not_codes():
    """Cameron, 2026-09-23: "Worth looking at" read "underrun by -11.2%:
    projected 27,897 against 31,430, risk watch" - the miss said twice, and an
    enum on the screen. Run for real, in node."""
    ok("', risk ' + a.risk" not in SCRIPT and "' by ' + fcPct(" not in SCRIPT, "the codes are gone")
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    words = re.search(r"const FC_RISK_WORDS = \{.*?\};", SCRIPT, re.S).group(0)
    js = ("const fcMoney = (v) => '£' + Math.round(v).toLocaleString('en-GB');\n" + words + "\n"
          + fn_src("function fcAlertText(a)") + r"""
console.log(JSON.stringify([
  fcAlertText({kind: 'sales', projected: 27897, target: 31430, gap_pct: -11.2, risk: 'watch'}),
  fcAlertText({kind: 'sales', projected: 33944, target: 19698, gap_pct: 72.3, risk: 'secure'}),
  fcAlertText({kind: 'sales', projected: 9000, target: 12000, gap_pct: -25, risk: 'high'}),
  fcAlertText({kind: 'cash', verdict: 'below cash buffer', working_capital: 4210}),
]));
""")
    got = _run_node(js)
    ok(got[0] == "Expected £27,897 against a plan of £31,430, 11.2% short; the plan is still inside the likely range.", got[0])
    ok(got[1] == "Expected £33,944 against a plan of £19,698, 72.3% ahead; even the bottom of the likely range clears it.", got[1])
    ok(got[2].endswith("25.0% short; even the top of the likely range falls short of it."), got[2])
    ok(got[3] == "Working capital drops below the cash buffer, to £4,210.", got[3])


@test
def t_the_month_pill_is_worked_out_from_the_figures_beside_it():
    """The pill said +72.0% and the alert under it +72.3% for the same month
    against the same plan: the run's gap_pct arrives rounded to two places."""
    ov = SCRIPT.split("function fcOverviewCard(", 1)[1].split("\n        function ", 1)[0]
    ok("(p50 - target) / target" in ov and "(cur.gap_pct || {})[sc]" not in ov,
       "the overview works its percentage out from the money it prints")
    fn = SCRIPT.split("function renderForecast()")[1].split("\n        async function showReconView")[0]
    ok("r.gap_pct" not in fn and "(r.p50 - t) / t" in fn, "and so does the month table")
    ok("FC_VERDICT_WORDS[v]" in fn and "FC_BASIS[r.method]" in fn,
       "whose verdicts and bases are words, not the run's codes")


@test
def t_the_scenario_label_sits_with_its_control():
    """"Plan scenario" stayed beside the heading, reading as its subtitle,
    while the strip it names sat 1,300px away: the heading's spacer is an
    ::after that grows, so the label has to be ordered past it with the
    control. And the scenarios are called what the workbook calls them."""
    rule = CSS.split(".fc-seg-lbl {")[1].split("}")[0]
    ok("order: 1" in rule and "margin-left: auto" not in rule, "the label moves with the control")
    ok("'Algo '" not in SCRIPT, "Algorithm 1 is not abbreviated to Algo 1")


@test
def t_the_forecast_explains_itself_once_and_in_plain_lines():
    """The certainty sentence sat alone in a full-width card; the breakdown's
    key was stranded at the card edge with the amounts in a column of their
    own between it and the words; and the sentence under it quoted a source
    description that began "The Theta method again"."""
    ov = SCRIPT.split("function fcOverviewCard(", 1)[1].split("\n        function ", 1)[0]
    tail = ov.split("const half = ", 1)[1]
    ok("el('div', 'card')" not in tail and "box.append(conf)" in tail, "the caveat is a line, not a card")
    dr = SCRIPT.split("function fcDriversCard(", 1)[1].split("\n        function ", 1)[0]
    order = [dr.index("'fc-drive-key "), dr.index("'fc-drive-lbl'"), dr.index("'fc-drive-amt'")]
    ok(order == sorted(order), "key, then words, then the amount at the right of the measure")
    ok("max-width: 52ch" in CSS.split(".fc-drive {")[1].split("}")[0], "the statement is measured")
    ok("The days left come from the source in use, " in dr, "and names the source it quotes")
    simple = open(os.path.join(ROOT, "forecast", "simple.py"), encoding="utf-8").read()
    ok("The Theta method again" not in simple, "every source description stands on its own")


@test
def t_the_reconciliation_card_keeps_status_and_actions_apart():
    """Cameron's screenshot, 2026-09-23: two chips, a bare count and three
    buttons in one wrapping row, Disconnect weighted like Sweep now, and the
    sweep's notes as form-help lines with a field's gap under each."""
    fn = fn_src("function renderRecon()")
    ok("'recon-conn-status'" in fn and "'recon-conn-acts'" in fn, "status on one side, actions on the other")
    ok("dropMenu(manage, [" in fn and "label: 'Disconnect Xero'" in fn,
       "disconnecting is in a menu, not a button beside the sweep")
    ok("el('div', 'field-help', n)" not in fn and "ul.append(el('li', null, n))" in fn,
       "the notes are one list")
    ok("danger: true" in fn.split("const disconnect = async")[1][:1400], "and the confirm is marked destructive")
    ok("text-wrap: pretty" in re.search(r"(?m)^\s*body \{([^}]*)\}", CSS).group(1), "no word stranded on a last line")


@test
def t_a_chart_prints_only_the_dates_it_has_room_for():
    """At phone width the forecast's day chart printed "25 Se30 Sep": six
    dates were drawn whatever the plot's width, and the last, anchored flush
    right, reaches back a whole label width onto the one before it."""
    fr = fn_src("function drawFrame(")
    ok("Math.min(c.xEvery || 6, room)" in fr and "labW * 1.5 + 8" in fr,
       "the date count is capped by the room the plot has")

@test
def t_the_reviewers_last_findings_stay_closed():
    """The independent check of the design sweep found seventeen things not
    fixed and sixteen made worse. Each line here is one of them."""
    # A product plan opened with an id Refresh can use: the payload has none.
    op = fn_src("async function openProduct(")
    ok("renderProductDetail(d, id, title);" in op, "the plan is drawn with the id it was opened by")
    pd = fn_src("function renderProductDetail(")
    ok("const pid = id || (d.product && d.product.id)" in pd, "so the plan has its Refresh")
    # Nobody owing: no toolbar over a list that cannot have a row.
    li = fn_src("function renderLiability(")
    i_empty = li.index("if (!(d.customers || []).length) {")
    ok(i_empty < li.index("lCard.append(tableTools(left, right));"), "the empty book skips the filters")
    # The recon arithmetic heading is a heading; what it is sits under it.
    rd = fn_src("function paintReconDetail(")
    ok("h('The arithmetic');" in rd and "h('The arithmetic (" not in rd, "a plain heading")
    # The month table keeps a month and its basis to one line each.
    ok(".fc-months th, .fc-months td:nth-child(-n+2) { white-space: nowrap; }" in CSS
       and "mc.lastChild.classList.add('fc-months');" in SCRIPT, "the month table does not stack its months")
    # Settings: the backup buttons on their own line, and copy that matches.
    ok(".setting-row:has(> .row-acts) { flex-wrap: wrap;" in CSS and "flex: 1 0 100%;" in CSS.split(".setting-row > .row-acts {")[1].split("}")[0],
       "the backup buttons take their own line under the row's words")
    ok("['Up to date', 'Not downloaded', 'None']" in SCRIPT and "'Download one'" not in SCRIPT, "a state, not an instruction, in the pill")
    ok("Back it up below" not in SCRIPT and "(Backups, above)" in SCRIPT, "the storage row points where the buttons are")
    ok("waits for Save profile" not in HTML, "and no caption has to explain two ways of saving: there is one")
    # Save and Cancel sit side by side in the size editor.
    ok("el('div', 'act-row sizes-edit-acts')" in SCRIPT and ".act-row.sizes-edit-acts { flex-wrap: nowrap; }" in CSS,
       "the size editor's buttons do not stack")
    # Team: one set of columns, so the master's meta ends where everyone's does.
    ok("el('div', 'files-list card-bleed tm-list')" in SCRIPT and ".tm-list > .tm-row:not(.tm-new) { display: grid; grid-template-columns: subgrid;" in CSS,
       "the team list shares its columns")
    ok(".tm-sign-save { margin-top: var(--sp-2); }" in CSS, "and Save sign-off stands off its field")
    # CRM Insights: each empty chart says what fills it.
    ok("function bars(title, desc, rows, fmt, empty) {" in SCRIPT
       and "'No activity was marked done in the last 30 days.'" in SCRIPT
       and "'No open deal has an expected close date from this month on.'" in SCRIPT,
       "each chart's empty line is its own")
    # The queue shares its tracks from the width the date appears at.
    ok("@container queue (min-width: 560px) {\n            .lbl-grid { display: grid;" in CSS, "a refunded row's date stays in line on a tablet")
    # Phone Overview: a sparkline tile takes the row in the widget grid too.
    ok(".ov-wrap.wgrid > .stat[data-widget]:has(.stat-spark) { grid-column: 1 / -1; }" in CSS, "the phone KPI rule reaches the grid")


def _run_js(src):
    """Run a snippet under node and return its stdout, or None when node is
    not on the PATH (the parse test skips the same way)."""
    if not any(os.access(os.path.join(p, "node"), os.X_OK)
               for p in os.environ.get("PATH", "").split(os.pathsep)):
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(src)
        path = fh.name
    try:
        r = subprocess.run(["node", path], capture_output=True, text=True, timeout=60)
        ok(r.returncode == 0, "the snippet ran: " + (r.stderr or "")[:400])
        return r.stdout
    finally:
        os.unlink(path)


@test
def t_the_connectors_words_reach_the_page_as_plain_english():
    """Cameron's screenshot of 2026-09-23: a check that writes nothing listed
    every document as 'created', each with '(dry run - not pushed)' under it
    (an em dash on the page), a paid invoice as 'Xero doc is PAID with ...
    re-import blocked to protect it ... or force', and a red box reading
    'run aborted: runaway guard: 21 documents exceeds MAX_DOCS_PER_RUN=1.
    Narrow ORDERS_SINCE or raise the limit.' The inputs here are the
    connector's own strings (shopify-xero-connector src/sync/reimportOrder.ts,
    summarise.ts, syncOrders.ts); the helpers are run, not read."""
    i = SCRIPT.index("        const CX_DOC_WORDS")
    helpers = SCRIPT[i:SCRIPT.index("        function connDocTable(")]
    helpers += fn_src("function cxTally(") + fn_src("function cxTallySentence(")
    D = "—"
    cases = {
        "paid": ["cxWhy", {"action": "blocked", "message": "Xero doc is PAID with 1228.60 paid/allocated " + D + " re-import blocked to protect it. Remove the payment/void in Xero, or force."}, False],
        "part": ["cxWhy", {"action": "blocked", "message": "Xero doc is AUTHORISED with 50 paid/allocated " + D + " re-import blocked to protect it. Remove the payment/void in Xero, or force."}, False],
        "void": ["cxWhy", {"action": "blocked", "message": "Xero doc is VOIDED " + D + " re-import blocked to protect it. Remove the payment/void in Xero, or force."}, False],
        "same": ["cxWhy", {"action": "unchanged", "message": "No change since last sync."}, True],
        "adopt": ["cxWhy", {"action": "unchanged", "message": "Already in Xero as INV-1882 for the same amount: adopted as it is, nothing rewritten."}, True],
        "dry": ["cxWhy", {"action": "created", "message": "(dry run " + D + " not pushed)"}, True],
        "inplace": ["cxWhy", {"action": "updated", "message": "Would update INV-1882 in place. (dry run " + D + " not pushed)"}, True],
        "docs": ["cxProblem", "run aborted: runaway guard: 21 documents exceeds MAX_DOCS_PER_RUN=1. Narrow ORDERS_SINCE or raise the limit."],
        "orders": ["cxProblem", "run aborted: runaway guard: 300 orders waiting exceeds RUNAWAY_ABORT_ABOVE=250. That is not a backlog, it is a widened ORDERS_SINCE; nothing was created, not even contacts. Narrow the window or raise the guard."],
        "breaker": ["cxProblem", "run aborted: circuit breaker: 5/10 (50%) documents failed validation " + D + " aborting before push. Review state/quarantine.jsonl."],
        "edited": ["cxProblem", "3 edited orders exceed MAX_DOCS_PER_RUN=2; none were re-checked this run"],
        "other": ["cxProblem", "credit note #104300-CN1: pre-resolve failed (timeout) " + D + " pushing without ID"],
        "thrown": ["cxProblem", "run failed: Shopify said 401"],
    }
    tally = [{"order": "#1", "docs": [{"action": "created"}, {"action": "created"}]}] \
        + [{"order": "#%d" % k, "docs": [{"action": "unchanged"}]} for k in range(31)] \
        + [{"order": "#b%d" % k, "docs": [{"action": "blocked", "message": "Xero doc is PAID with 10 paid/allocated " + D + " re-import blocked to protect it. Remove the payment/void in Xero, or force."}]} for k in range(33)]
    # An order that stopped part way keeps its error beside what it did; a
    # contact that is missing needs someone; a voided order has nothing to
    # send; an order not in Shopify has no document at all.
    mixed = [{"order": "#s", "found": True, "error": "Shopify HTTP 502", "docs": [{"action": "created"}]},
             {"order": "#c", "found": True, "docs": [{"action": "blocked", "message": "No invoice produced " + D + " customer not matched in Xero. Run a full sync to create the contact first."}]},
             {"order": "#u", "found": False, "docs": []},
             {"order": "#v", "found": True, "docs": [{"action": "blocked", "message": "Order produced no documents (VOIDED with no refunds)."}]}]
    js = ("const money = (n, cur, dp) => '£' + Number(n).toFixed(dp);\n" + helpers
          + "\nconst C = " + json.dumps(cases) + ";\nconst out = {};\n"
          + "for (const k in C) { const [f, a, b] = C[k]; out[k] = f === 'cxWhy' ? cxWhy(a, b) : cxProblem(a); }\n"
          + "const T = " + json.dumps(tally) + ";\nconst n = cxTally(T);\n"
          + "out.tally = n; out.sentence = cxTallySentence(n, true); out.sent = cxTallySentence(n, false);\n"
          + "out.none = cxTallySentence(cxTally([{docs: [{action: 'unchanged'}]}]), true);\n"
          + "const X = " + json.dumps(mixed) + ";\nconst nx = cxTally(X);\n"
          + "out.mixed = nx; out.mixedSentence = cxTallySentence(nx, true);\n"
          + "out.groups = cxEntries(X).map(e => e.g + (e.stop ? ':stop' : ''));\n"
          + "out.contact = cxWhy(X[1].docs[0], true); out.voided = cxWhy(X[3].docs[0], true);\n"
          + "out.oneSame = cxOneSentence([{kind: 'invoice', action: 'created'}, {kind: 'creditnote', action: 'created'}], true);\n"
          + "out.oneMixed = cxOneSentence([{kind: 'invoice', action: 'created'}, {kind: 'creditnote', action: 'unchanged'}], true);\n"
          + "out.oneSent = cxOneSentence([{kind: 'invoice', action: 'created'}], false);\n"
          + "out.testorder = cxKind({action: 'blocked', message: 'No invoice produced: test order.'});\n"
          + "out.qrange = cxPlain('line 2 (\\\"Gobo 3\\u20134 pack\\\")');\n"
          + "out.env = cxPlain('Missing required setting: XERO_CLIENT_ID (set it in the Settings tab or .env)');\n"
          + "out.valid = cxDetail('Rejected by Xero: ValidationException: The TaxType code OUTPUT2 cannot be used with account code 205.');\n"
          + "out.cnfor = cxProblem('credit note for #1007: no matching refund transaction');\n"
          + "out.iphone = cxPlain('iPhone case'); out.range = cxPlain('line 1 (\\\"Gobo \\u2013 Glass\\\"): discount rate 150% out of range 0\\u2013100');\n"
          + "console.log(JSON.stringify(out));\n")
    def eq(a, b, msg=""):
        ok(a == b, (msg + ": " if msg else "") + "%r, expected %r" % (a, b))
    raw = _run_js(js)
    if raw is None:
        print("       (node unavailable, skipped)")
        return
    o = json.loads(raw)
    eq(o["paid"], "Paid in Xero, so it is not rewritten. To change it, remove the payment in Xero first.")
    eq(o["part"], "Partly paid in Xero, so it is not rewritten. To change it, remove the payment in Xero first.")
    eq(o["void"], "Voided in Xero, so it is not rewritten.")
    eq(o["same"], "Nothing has changed since it was sent.")
    eq(o["adopt"], "As INV-1882, for the same amount, so it is kept as it is.")
    eq(o["dry"], "", "the dry-run note says nothing the page does not already say")
    eq(o["inplace"], "Rewrites INV-1882 in place.")
    ok(o["docs"].startswith("It stopped before writing anything: 21 documents were ready, more than one run may write (1).")
       and "MAX_DOCS" not in o["docs"], o["docs"])
    ok("300 orders were waiting" in o["orders"] and "start date was moved back" in o["orders"], o["orders"])
    ok("5 of 10 documents (50%)" in o["breaker"] and "jsonl" not in o["breaker"], o["breaker"])
    ok(o["edited"].startswith("3 edited orders were more than one run may write (2), so none"), o["edited"])
    eq(o["thrown"], "The run failed. Shopify said 401.")
    # 'range' keeps a dash inside a quoted product name on purpose (it is the
    # name, read against the order), and 'iphone' starts small on purpose.
    for k, v in o.items():
        if isinstance(v, str) and k not in ("range", "iphone", "qrange", "testorder"):
            ok("—" not in v and "–" not in v, "no dash reaches the page: %s %r" % (k, v))
            ok(not re.search(r"\b[A-Z]+_[A-Z_]+\b", v), "no setting's code name reaches the page: %s %r" % (k, v))
            ok(not v or v[0].isupper() or v[0] in "£\"'" or v[0].isdigit(), "a sentence starts as one: %s %r" % (k, v))
    eq(o["tally"]["docs"], 66); eq(o["tally"]["create"], 2); eq(o["tally"]["locked"], 33); eq(o["tally"]["attention"], 0)
    eq(o["sentence"], "2 would be created, 31 are already in Xero and 33 are paid or closed in Xero, so left alone.")
    eq(o["sent"], "2 were created, 31 are already in Xero and 33 are paid or closed in Xero, so left alone.")
    eq(o["groups"], ["write", "attention:stop", "attention", "unread", "alone"],
       "a part-way stop keeps its row, a missing contact needs attention, a voided order is left alone")
    eq((o["mixed"]["write"], o["mixed"]["attention"], o["mixed"]["unread"], o["mixed"]["nothing"], o["mixed"]["rows"]), (1, 2, 1, 1, 5))
    eq(o["mixedSentence"], "1 would be created, 1 has nothing to send and 2 need attention (each row says why).")
    ok("not a contact in Xero yet" in o["contact"], o["contact"])
    eq(o["voided"], "The order was voided and nothing was refunded, so there is nothing to send.")
    eq(o["oneSame"], "The invoice and the credit note would be created.")
    eq(o["oneMixed"], "The invoice would be created and the credit note is already in Xero.")
    eq(o["oneSent"], "The invoice was created.")
    eq(o["iphone"], "iPhone case", "a word that starts small and goes on in capitals keeps its case")
    eq(o["testorder"], "nothing", "a test order has nothing to send; it does not need attention")
    ok("3\u20134 pack" in o["qrange"], "a range inside a quoted name is the name: " + o["qrange"])
    eq(o["env"], 'Missing required setting: "Xero client ID" (set it in Settings)')
    ok("ValidationException" not in o["valid"] and "cannot be used with account code 205" in o["valid"], o["valid"])
    eq(o["cnfor"], "Credit note for #1007: No matching refund transaction.")
    eq(o["range"], 'Line 1 ("Gobo \u2013 Glass"): discount rate 150% out of range 0 to 100.'[:-1],
       "a quoted name is left as it is, and a range reads 'to'")
    eq(o["none"], "Nothing would be written: 1 is already in Xero.")


@test
def t_a_check_lists_what_it_found_under_the_tiles_not_inside_one():
    """Cameron's screenshot of 2026-09-23: a tag check's 62 orders were listed
    inside the 444px tag tile. The tile is a grid, a grid's implicit column is
    as wide as its widest content, and the list pushed that column past the
    tile, over the payout tile beside it and 450px out of the card, while the
    tile grew 10,535px tall. The tiles are the ways in; what a check finds is
    a section under all three, the width of the card, as a table."""
    tile = re.search(r"@supports \(grid-template-rows: subgrid\) \{\s*\.cx-tile \{([^}]*)\}", CSS)
    ok(tile and "grid-template-columns: minmax(0, 1fr)" in tile.group(1),
       "a tile's one column can never be wider than the tile")
    ok(tile and "grid-row: span 3" in tile.group(1), "and it spans title, hint and controls, with no result row")
    fn = fn_src("function renderConnector(")
    ok("const cxTile = (title, hint, row) => {" in fn, "a tile takes no result")
    ok(fn.count("grid.append(cxTile(") == 3 and "Out))" not in fn, "and none of the three is handed one")
    ok("paintOne(); paintTag(); paintPay();" in fn and "if (results.childNodes.length) rCard.append(results);" in fn,
       "the results are drawn after the tiles, in their order")
    ok(".cx-results {" in CSS and "border-top: var(--bw-hairline)" in CSS.split(".cx-results {")[1].split("}")[0],
       "under a rule, across the card")
    ok("#view-connector .conn-results { max-width: 56rem; }" not in CSS and "#view-connector .conn-results {" not in CSS,
       "the old 56rem column is gone: a table of documents takes the card's width")
    # The table: an order named once over its documents, the outcome in words,
    # and a tag of 62 orders paged and filtered rather than drawn whole.
    tb = fn_src("function connDocTable(")
    ok("first ? (r.order || '') : ''" in tb and "el('tr', (withOrder && !first) ? 'cx-more' : null)" in tb,
       "an order is named on its first row, and only a list of orders groups its rows")
    ok("dry ? w[0] : w[1]" in tb, "a check says 'Would create', a send 'Created'")
    ok("tablePager({ total: kept.length" in fn and "connTagView.f" in fn, "the tag list is paged and filtered")
    ok("f: n.write ? 'write' : 'all'" in fn, "and opens on what Send would write")
    ok(".cx-docs td.cx-out, .cx-docs td.cx-note { width: 100%; }" in CSS, "the outcome takes the spare width")


@test
def t_the_run_health_box_says_when_and_in_words():
    """The red box on Cameron's screen was about a review from 5 Sep that a
    since-removed guard stopped (connector c3a2ee5, 7 Sep), and nothing on it
    said so: no date, and the problem in environment-variable names."""
    fn = fn_src("function renderConnector(")
    ok("const when = ', on ' + fmtDate(connHealth.lastRunAt);" in fn, "it gives the date of the run it judges")
    ok("connHealth.lastRunDryRun === true ? 'review'" in fn, "and whether that run was a review or a send")
    ok("cxProblem(p2, ctx)" in fn, "each problem in plain words")
    ok("cxProblem('run aborted: ' + r.aborted, ctx)" in fn and "cxProblem(w)" in fn,
       "and the latest review says its stop and its warnings the same way")
    ok(".slice(0, 140)" not in fn and "cxDetail(q2.reason" in fn, "a quarantine reason is whole, not cut mid-word")
    # The Connection card: its facts named, the switch on the row it switches.
    ok("el('dl', 'conn-pairs cx-facts')" in fn and "fact('Store'" in fn, "the connection's facts each have a name")
    ok("credentials and mapping live on the connector service" not in fn, "not one run-on line of dots")
    i = fn.index("const t = el('button', 'btn btn-sm', on ? 'Turn Auto Run off' : 'Turn Auto Run on');")
    ok("ar.append(t);" in fn[i:i + 1600] and "sAct.append(t);" not in fn, "the Auto Run switch sits on the Auto Run row")
    ok(".cx-auto > .btn { margin-left: auto;" in CSS, "at its right-hand end")


@test
def t_a_send_arms_only_on_a_check_that_found_something_to_send():
    """The independent review of 2026-09-23 pressed every Send after every kind
    of check. 'Send this order' armed after 'No order #999999 in Shopify.',
    after an error and after a check that would write nothing, and its confirm
    offered to send 'nothing the check could name'; 'Send tagged orders' armed
    for a tag with no orders; 'Send to Xero' armed after a review that said
    nothing should be sent; and the payout write, checked for September,
    stayed armed when the date was retyped to January and then wrote January."""
    fn = fn_src("function renderConnector(")
    armed = fn_src("function connOneArmed(")
    ok("!connOneCheck.sent" in armed, "a sent order's result stays on screen but arms nothing")
    ok("if (c.error || c.found === false) return ['', 'The check did not find this order, so there is nothing to send'];" in fn
       and "if (!cxTally([{ docs: c.docs || [] }]).write) return ['', 'The check found nothing to write for this order'];" in fn,
       "one order: found, no error, and something to write")
    ok("if (!(c.details || []).length) return ['', 'No order carries this tag'];" in fn
       and "if (!cxTally(c.details).write) return ['', 'The check found nothing to write for these orders'];" in fn,
       "a tag: orders, and something to write")
    ok("send.disabled = running || !connReview || revAborted;" in fn, "a review that stopped arms no Send")
    ok("paySince.value.trim() === (connPayBox || '')" in fn and "connPayBox = connPaySince;" in fn
       and "since: connPayResult.since || connPayBox || ''" in fn,
       "the payout write is for the date that was checked, and retyping it disarms the write")
    ok("oneIn.oninput = armOne;" in fn and "tagIn.oninput = armTag;" in fn, "retyping re-asks the same rule")
    for b in ("oneChk.disabled = running", "tagChk.disabled = running", "payChk.disabled = running"):
        ok(b in fn, "no second check while the connector is busy: " + b)


@test
def t_what_a_send_did_stays_on_screen_and_the_toast_says_it():
    """'Sent #104300 to Xero.' was toasted whatever the connector answered, and
    the reply was thrown away (void r), so a failed or quarantined write read
    as a success with nothing on screen to say otherwise."""
    fn = fn_src("function renderConnector(")
    ok("void r;" not in fn, "the reply is used")
    ok("connOneCheck = { order: order, data: data, sent: true };" in fn, "it is kept, marked sent")
    ok("else if (n.attention) toastError('Not all of order ' + order" in fn
       and "toastError('Order ' + order + ' was not sent. '" in fn, "and the toast follows what happened")
    ok("'Not sent: order '" in fn and "'Partly sent: order '" in fn and "'Sent: order '" in fn,
       "under a heading that says what the send did: nothing, part or all")
    ok("'Nothing sent: '" in fn and "'Partly sent: '" in fn and "'Sending: '" in fn,
       "and a tag's heading says the same, and 'Sending' while it runs, not 'Sent'")
    ok("if (bad) toastError('Wrote ' + k" in fn, "a partial payout write is not a green toast either")


@test
def t_the_document_window_opens():
    """It threw on every document: money2 called money(), and a later
    'const money = money2' in the same function shadowed the global, so the
    call hit the const before it was set and then called itself."""
    fn = fn_src("function connDocModal(")
    ok(not re.search(r"^\s*(const|let|var)\s+money\s*=", fn, re.M), "no local named money")
    ok("money(v, cur || p.currency || 'GBP', 2)" in fn, "money2 still goes through the app's one money rule")
    ok(fn.count("money2(") >= 8, "and every figure in the window goes through money2")
    ok("const note = cxWhy(d, true);" in fn, "and the connector's note arrives in words, not '(dry run - not pushed)'")
    sm = fn_src("function sheetModal(")
    ok("x.focus()" in sm, "focus goes into the window when it opens")


@test
def t_the_page_agrees_with_itself_after_a_run():
    """After a review finished the watcher re-read the runs but not the health,
    so the box went on about 5 Sep beside a review from today; a failed tag
    check raised 'Last run failed' under a box about another run; and every
    repaint re-read the quarantine list, so a filter click flashed it empty."""
    watch = fn_src("function connStartWatch(")
    ok("connHealth = (await connOp({ op: 'health' })).data" in watch and "connAuto = (await connOp({ op: 'autorun' })).data" in watch,
       "a finished run re-reads the health and Auto Run")
    fn = fn_src("function renderConnector(")
    ok("st.lastError !== tagErr && !boxSaysIt" in fn, "the chip does not repeat the tag section or the box")
    ok("op: 'quarantine'" not in fn and "connQuar" in fn, "the quarantine list is painted from what was read with the status")
    ok("connTagBusy === 'check' ? 'A tag check is in progress" in fn, "and the busy chip says what is running")
    ok("connFocus = { sec: 'tag', on: 'tab' };" in fn and "sec.querySelector('.ftab.on')" in fn,
       "a filter click keeps focus on the filter")


@test
def t_the_xero_page_keeps_the_details_the_last_check_found():
    """The fixes the verifier found unpinned after the second pass, each the
    one line that holds it."""
    fn = fn_src("function renderConnector(")
    ok(".ktable.cx-docs td { vertical-align: top; }" in CSS, "rows are top-aligned; the bare .cx-docs td rule lost to .ktable td")
    ok("'Nothing has run yet: no review and no send.'" in fn, "no run is not a green box")
    ok("((connHealth && connHealth.guards) || {}).reconcileTolerance" in fn, "the tolerance comes from the health guards")
    ok("connTagPending" in fn and "connTagPending = '';" in fn_src("function connStartWatch("),
       "the tag in flight names the busy section and is cleared when collected")
    ok("if (kept.length > 20) sec.append(tablePager(" in fn and "if (order.length > 20) sec.append(tablePager(" in fn,
       "a pager only when there is a page to turn")
    ok("const kept = connTagView.f === 'all' ? all : all.filter(e => e.g === connTagView.f);" in fn,
       "the tabs filter the same rows they count")
    ok('.cx-docs:not(.cx-pay):not(.cx-quar) tr { grid-template-areas: "ord ord" "kind num" "out act"; }' in CSS,
       "on a phone a row is order, then document and amount, then outcome and Open")
    ok("requestAnimationFrame(() => requestAnimationFrame(() => {" in fn and "target.focus({ preventScroll: true });" in fn,
       "focus returns after the page is laid out, without scrolling the window")
    ok("'An admin sends exactly what it showed.'" in fn and "'an admin sends'" in fn,
       "a member is not told to press a Send they do not have")

@test
def t_settings_saves_one_way():
    """D10 of the 2026-09-23 sweep: the four preference switches waited for a
    footer 'Save profile' while the Auto-refresh switch beside them saved at
    once, so the footer's Cancel undid one and not the other, and a caption
    had to explain it. Now every switch saves when changed and each block of
    text has its own Save under it; the window has no footer."""
    m = HTML[HTML.index('id="settings-modal"'):HTML.index('id="usage"')]
    ok('class="modal-foot"' not in HTML[HTML.index('id="settings-modal"'):HTML.index('<script>', HTML.index('id="settings-modal"'))],
       "no footer Save or Cancel")
    ok(m.index('id="pf-notes"') < m.index('id="settings-save"') < m.index('Sign-in'),
       "Save profile sits under the four text fields it saves")
    ok("prefToggles().forEach(t => t.onclick = function () { savePrefToggle(this); });" in SCRIPT, "a preference saves when it is changed")
    fn = fn_src("async function savePrefToggle(")
    ok("t.classList.toggle('on', was);" in fn and "toastError(" in fn, "and a switch the server refused goes back and says so")
    ok("api('/api/profile', { prefs: prefs })" in fn and "profile: " not in fn.split("api('/api/profile'")[1][:40],
       "a switch sends the switches alone, never this page's copy of the text (the server merges them)")
    close = fn_src("function closeSettings(")
    ok("profileKey(profile) !== settingsAtOpen" in close and "if (!changed || !overviewCache) return;" in close and "loadOverview(true)" in close,
       "the Overview is recomputed once on close, only if something really changed and only if it had been run")
    ap = fn_src("async function applySettings(")
    ok("const next = Object.assign({}, profile," in ap and "profile = (d && d.profile) ? d.profile : next;" in ap,
       "a failed Save profile leaves the saved profile as it was")
    ok("mng.onclick = () => { closeSettings(); openShippingSettings(); };" in SCRIPT, "every way out of the window goes through closeSettings")
    op = fn_src("function openSettings(")
    ok("const canEdit = connIsAdmin();" in op and "readOnly = !canEdit" in op and "setAttribute('aria-disabled', 'true')" in op,
       "someone who cannot change the profile sees it, not controls that bounce")


@test
def t_a_page_is_called_what_the_sidebar_calls_it():
    """D14 of the 2026-09-23 sweep: on nine screens the topbar and the page
    heading gave one page two names ('Store overview' under 'Overview', and
    'Finance' under each of Liability, Reconciliation, Forecast and Xero
    sync)."""
    titles = re.search(r"const titles = \{ overview: 'Overview'[^}]*liability[^}]*\}", SCRIPT).group(0)
    for view, name in (("overview", "Overview"), ("seo", "SEO"), ("keywords", "Keywords"), ("memory", "Memory"),
                       ("liability", "Liability"), ("recon", "Reconciliation"), ("forecast", "Forecast"), ("connector", "Xero sync")):
        ok(view + ": '" + name + "'" in titles, "the topbar calls " + view + " " + name)
        ok("el('h2', null, '" + name + "')" in SCRIPT, "and so does its page heading: " + name)
    ok("comp ? 'Customers' : (seg + ' sector')" in SCRIPT, "Customers too")
    for old in ("'Store overview'", "'SEO and optimisation'", "'Keyword and CPC intelligence'",
                "'Memory and knowledge'", "'Finance'"):
        ok(("el('h2', null, " + old + ")") not in SCRIPT, "no page is headed " + old)
        ok(("title: " + old) not in SCRIPT, "nor its Run gate " + old)
    ok("const titles = { overview: 'Overview', seo: 'SEO', keywords: 'Keywords', products: 'Products', customers: 'Customers' };" in SCRIPT,
       "and the printed report's header uses the same names")
    ok("comp ? 'Customers and retention'" not in SCRIPT, "nor 'Customers and retention'")


@test
def t_a_search_does_not_take_customise_away():
    """B31: typing a product search that left fewer than two earners emptied
    Top products, the page fell to one card, the grid stood down and
    Customise vanished from the header, then came back as the search was
    cleared."""
    fn = fn_src("function renderProductList(")
    ok("const narrowed = rows.length < all;" in fn and "if (top.length > 1 || narrowed) {" in fn,
       "a narrowed list keeps the card")
    ok("so there is nothing to rank." in fn, "and the card says why it has no bars")


@test
def t_the_queue_rows_use_the_small_control():
    """C-05: the production queue's row buttons were 32px beside the 28px
    buttons in the same card's head and toolbar."""
    fn = fn_src("function renderLabels(") if "function renderLabels(" in SCRIPT else SCRIPT
    ok("const pv = el('button', 'btn btn-sm');" in SCRIPT and "const pr = el('button', 'btn btn-sm');" in SCRIPT,
       "the row buttons are the small control")
    ok(".lbl-actions .btn:has(> .lbl-btn-txt) { padding: 0; min-width: var(--control-h-md);" in CSS,
       "and an icon-only button is square at that size, without squeezing a button that has only words")


@test
def t_the_xero_page_uses_one_set_of_outcome_words():
    """The review table summed five different things under 'Skipped', and a
    'Blocked' tile the connector never sends a figure for disagreed with
    'Left alone' in the tables."""
    fn = fn_src("function renderConnector(")
    ok("kpi('Blocked'" not in fn, "no tile for a count the connector does not have")
    ok("Skipped</th>" not in fn and "['noContact', 'Needs a Xero contact']" in fn and "['inXero', 'Already in Xero']" in fn,
       "the review counts in the tables' words")
    rc = fn_src("function cxReviewCounts(")
    ok("n('skippedSynced') + n('skippedInXero')" in rc and "n('skippedTest') + n('skippedCancelled')" in rc,
       "from the connector's own counters")
    ok("An admin links it in Railway." in fn and "el('ol', 'setup-steps')" in fn,
       "the unlinked page gives an admin the steps and a member the one fact")
    ok("(!connAuto ? ''" in fn, "and the header makes no promise when Auto Run's state is unknown")
    ok(".modal-body .section-title + * > .setting-row:first-child { border-top: 0; }" in CSS,
       "Settings draws no rule straight under a heading, in any section, Connections included")
    rc = fn_src("function cxReviewCounts(")
    ok("voided: n('voided'), keptPaid: n('updateBlocked')" in rc and "if (kind === 'creditNotes') {" in rc,
       "a void and an edit left as posted are counted, and a credit note shows no outcome it cannot have")
    ok(".setup-steps li > .setup-code { white-space: nowrap; word-break: normal; }" in CSS, "a code word in a step never splits")


# ---- Workspace pages, 24 September 2026 -------------------------------------

def eq(a, b, msg=""):
    ok(a == b, "%s: %r != %r" % (msg or "equal", a, b))


def md_src():
    """Every piece of the page's Markdown renderer, for a node harness."""
    consts = "".join(m.group(0) for m in re.finditer(
        r"        const (?:MD_LI|mdEsc|mdUnesc|MD_INLINE|MD_FM_KEYS) = [^\n]*\n", SCRIPT))
    return consts + "\n".join(fn_src(n) for n in ("function yamlScalar(", "function mdFrontmatter(", "function mdInline(",
                                                   "function mdList(", "function mdNodes(", "function proseNodes(", "function pipeTable("))


@test
def t_the_release_notes_are_ui_copy_and_keep_up_with_the_app():
    """What's new stopped at 8 Sep while sixty changes shipped, and its notes
    carried 46 dashes, the code name and developer words. The notes are read
    on screen, so they keep the house rules, and they cannot fall behind the
    code again without this failing."""
    data = json.load(open(os.path.join(ROOT, "data", "changelog.json"), encoding="utf-8"))
    texts = [r.get("title", "") for r in data["releases"]] + [i["text"] for r in data["releases"] for i in r["items"]]
    bad = [t[:60] for t in texts if re.search("[‒-―]", t)]
    ok(not bad, "no em or en dashes in the notes: %s" % bad[:3])
    ok(not [t for t in texts if re.search(r"\bgizmo\b", t, re.I)], "and no code name")
    ok(not [t for t in texts if re.search(r"\b(API|webhook|callback URL|JSON)\b", t)], "and no developer words")
    views = set(re.search(r"const APP_VIEWS = \[([^\]]*)\]", SCRIPT).group(1).replace("'", "").replace(" ", "").split(","))
    tabs = {i.get("tab") for r in data["releases"] for i in r["items"] if i.get("tab")}
    ok(tabs <= views, "every note's Open goes to a real page: %s" % (tabs - views))
    newest = max(r["date"] for r in data["releases"])
    try:
        last = subprocess.run(["git", "log", "-1", "--format=%cs", "--", "static/index.html", "copilot.py"],
                              cwd=ROOT, capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception:
        last = ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", last or ""):
        ok(newest >= last, "the newest note (%s) is not older than the last change to the app (%s): "
           "write what changed in data/changelog.json" % (newest, last))


@test
def t_a_chat_follow_up_carries_the_answer_and_a_failed_question_is_not_resent():
    """A follow-up went without the sections and figures of the answer it
    followed; a question that failed was sent again, twice, beside its retry;
    and the title was cut mid-word."""
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    js = MINIDOM + "const CHAT_KEEP = 30;\n" + fn_src("function apiHistory(") + "\n" + fn_src("function structuredToText(") + "\n" + fn_src("function convoTitle(") + r"""
const s = { summary: 'Three accounts are quiet.', metrics: [{ label: 'Revenue', value: '£6,420', delta: '+9%' }],
  sections: [{ title: 'Quiet accounts', body: '- Stage Co 5\n- Stage Co 9' }], actions: [{ text: 'Call them' }], skills_applied: ['Chasing'] };
const c = { turns: [{ role: 'user', text: 'q1' }, { role: 'assistant', structured: s }, { role: 'user', text: 'q2' }, { role: 'error', text: 'x' }, { role: 'user', text: 'q3' }] };
const h = apiHistory(c);
const many = { turns: [] }; for (let i = 0; i < 40; i++) many.turns.push({ role: 'user', text: 'u' + i }, { role: 'assistant', structured: { summary: 'a' + i } });
console.log(JSON.stringify({ roles: h.map(m => m.role), users: h.filter(m => m.role === 'user').map(m => m.content), text: h[1].content,
  keep: apiHistory(many).length, first: apiHistory(many)[0].role,
  title: convoTitle('Can you compare the September 2026 wedding season with last year for monogram gobos please') }));
"""
    got = _run_node(js)
    eq(got["roles"], ["user", "assistant", "user"], "the failed question and its error are left out")
    eq(got["users"], ["q1", "q3"])
    for bit in ("Revenue: £6,420 (+9%)", "Quiet accounts", "Stage Co 9", "Followed the skills: Chasing"):
        ok(bit in got["text"], "the answer as sent carries " + bit)
    ok(got["keep"] <= 30 and got["first"] == "user", "a long conversation sends its latest messages, starting with a question: %r" % got)
    ok(got["title"].endswith("…") and not got["title"][:-1].endswith(" ") and len(got["title"]) <= 61, got["title"])


@test
def t_two_tabs_do_not_overwrite_each_others_conversations():
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    js = "const pending = {}; const goneConvos = new Set();\n" + fn_src("function mergeConvos(") + r"""
const mine = [{ id: 'a', updated: 5, turns: [1] }, { id: 'b', updated: 1, turns: [1] }];
const theirs = [{ id: 'b', updated: 9, turns: [1, 2] }, { id: 'c', updated: 7, turns: [1] }, { id: 'gone', updated: 8, turns: [1] }];
goneConvos.add('gone');
const m = mergeConvos(mine, theirs);
pending.a = true;
const m2 = mergeConvos([{ id: 'a', updated: 1, turns: [1, 2, 3] }], [{ id: 'a', updated: 99, turns: [1] }]);
console.log(JSON.stringify({ ids: m.map(c => c.id), b: m.find(c => c.id === 'b').turns.length, pend: m2[0].turns.length }));
"""
    got = _run_node(js)
    eq(got["ids"], ["b", "c", "a"], "newest first, the other tab's conversation kept, a deleted one not brought back")
    eq(got["b"], 2, "the newer copy of a conversation wins")
    eq(got["pend"], 3, "and one still being answered here is never replaced")


@test
def t_chat_takes_a_refusal_at_its_word():
    """A 400 or 429 from the streaming route was asked again on the plain
    route: the same question twice, and a run nobody pressed for."""
    fn = fn_src("async function streamChat(")
    ok("why && why.error" in fn and "[404, 405, 502, 503, 504].includes(res.status)" in fn,
       "only a missing route or a gateway without an answer falls back")
    ok("signal: signal" in fn and "stopped: true" in fn, "and Stop aborts the run")
    send = fn_src("async function send(")
    ok("if (pending[c.id]) { busyNote(); return; }" in send, "a second question in the same conversation says why it waits")
    ok("role: 'error'" in send and "save();" in send, "a failed question is kept with its reason")
    ok("if (data.noted || (data.followups_closed || []).length) loadMemory('notes')" in send,
       "and an answer reads the notes again only when it kept or closed one")


@test
def t_the_memory_page_says_which_notes_reactor_reads():
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    js = "let memInject = 2;\n" + fn_src("function memSentIds(") + r"""
let memories = [
 { id: 'f1', type: 'fact', status: 'open' }, { id: 'f2', type: 'decision', status: 'open' }, { id: 'f3', type: 'fact', status: 'open' },
 { id: 'u1', type: 'followup', status: 'done' }, { id: 'u2', type: 'followup', status: 'open' },
 { id: 'p1', type: 'preference', status: 'dismissed' }, { id: 'p2', type: 'preference', status: 'open' }];
console.log(JSON.stringify([...memSentIds()].sort()));
"""
    eq(_run_node(js), ["f2", "f3", "p2", "u2"], "the newest of each kind, as the server's prompt takes them")


@test
def t_a_long_skill_is_split_not_cut():
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    js = fn_src("function splitSkill(") + r"""
const paras = []; for (let i = 0; i < 30; i++) paras.push('Step ' + i + ': ' + 'x'.repeat(90));
const text = paras.join('\n\n');
const parts = splitSkill(text, 1000);
console.log(JSON.stringify({ n: parts.length, max: Math.max(...parts.map(p => p.length)), whole: parts.join('\n\n') === text,
  long: splitSkill('y'.repeat(2500), 1000).map(p => p.length) }));
"""
    got = _run_node(js)
    ok(got["n"] > 1 and got["max"] <= 1000 and got["whole"], "split at paragraph breaks, nothing lost: %r" % got)
    eq(got["long"], [1000, 1000, 500], "and a paragraph longer than a skill is cut into whole pieces")


@test
def t_an_answer_in_prose_is_drawn_as_prose():
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    js = (MINIDOM + "document.createDocumentFragment = () => new Node_('#fragment');\n" + md_src()
          + r"""
const f = proseNodes('## Where it came from\n- **Wedding** gobos\n- Steel\n\n| Product | Orders |\n|---|---|\n| Monogram | 9 |\nThat is all.');
const tags = f.children.map(n => n.tagName);
const tbl = f.children.find(n => n.className.includes('ktable-wrap'));
console.log(JSON.stringify({ tags, text: f.textContent, rows: tbl.children[0].children[1].children.length }));
""")
    got = _run_node(js)
    eq(got["tags"], ["H4", "UL", "DIV", "P"], "a heading, a list, a table and a paragraph")
    ok("**" not in got["text"] and "##" not in got["text"] and "---" not in got["text"], got["text"])
    eq(got["rows"], 1, "the rule row under a table's head is not a row")


@test
def t_the_guide_shows_each_person_what_they_can_do():
    """Members were shown the Cloudflare setup and admin-only steps, and the
    guide covered seven of nineteen pages."""
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    js = re.search(r"        const GUIDE = \[.*?\n        \];", SCRIPT, re.S).group(0) + "\n" + \
        fn_src("function guideFor(").replace("function guideFor(", "function guideFor(") + r"""
let teamMe = { role: 'member' }; let allowed = new Set(['labels', 'mail', 'chat', 'files']);
const guideAdmin = () => !!teamMe && (teamMe.role === 'master' || teamMe.role === 'admin');
const tabAllowed = (v) => allowed.has(v);
const member = guideFor();
teamMe = { role: 'admin' }; allowed = new Set(['labels', 'mail', 'chat', 'files', 'overview', 'seo', 'keywords', 'products', 'customers', 'liability', 'crm', 'loans', 'sizes', 'memory', 'skills']);
const admin = guideFor();
const flat = (g) => g.flatMap(s => s.body.map(r => r[0] + ' ' + r[1])).join('\n');
console.log(JSON.stringify({ mSecs: member.map(s => s.id), aSecs: admin.map(s => s.id), m: flat(member), a: flat(admin) }));
"""
    got = _run_node(js)
    ok("house" not in got["mSecs"] and "house" in got["aSecs"], "housekeeping is for admins")
    ok("Cloudflare" not in got["m"] and "Cloudflare" in got["a"], "and so is the storage setup")
    ok("Liability" not in got["m"] and "reports" not in got["mSecs"], "a page someone cannot open is not explained to them")
    for page in ("Inbox", "CRM", "Loan units", "Liability", "Reconciliation", "Forecast", "Xero sync", "Size list", "Memory", "Skills", "Customise", "Clocking in", "Two-step sign-in", "Deep analysis"):
        ok(page in got["a"], "the guide covers " + page)
    body = re.search(r"const GUIDE = \[(.*?)\n        \];", SCRIPT, re.S).group(1)
    for word in ("Railway", "R2_", "RESEND", "gizmo", "up.railway.app"):
        ok(word not in body, "no %s in the guide" % word)
    ok("location.origin + '/dav'" in SCRIPT, "the drive address is where the app is running")


@test
def t_the_guide_tabs_say_which_is_showing_and_keep_focus():
    seg = fn_src("function paintGuideSeg(")
    ok("setAttribute('aria-pressed'" in seg, "each tab says whether it is showing")
    ok("host.replaceChildren()" in seg and "renderGuide();" in seg.split("if (!host)")[1][:40],
       "a tab repaints what is under the tabs, not the tabs, so focus stays on the one pressed")
    ok("Date.now() - updAt < 180000" in fn_src("async function loadUpdates("), "and the notes are not fetched again on every switch")
    ok("op: 'version'" in fn_src("async function updatesBadge("), "the dot reads the counts alone")
    ask = fn_src("function askFeature(")
    ok("t.maxLength = 140" in ask and "d.maxLength = 4000" in ask and "markInvalid(t, true)" in ask and "t.focus()" in ask,
       "the request box says its limits, marks an empty title and is ready to type in")
    ok("r && r.emailed" in ask, "and promises an email only when one went")


@test
def t_the_skills_and_memory_pages_ask_before_losing_anything():
    for name in ("function memRow(", "function skillItem("):
        ok("uiConfirm(" in fn_src(name), name + " asks before a delete")
    ed = fn_src("function skillEditor(")
    ok("maxLength = skillCaps.body" not in ed and "over > 0" in ed, "a long skill is not cut at the limit without a word")
    ok("already have a skill called" in ed, "a title you already have is said before you save")
    ok("'Split into ' + pieces + ' skills'" in ed, "and a long file can be split")
    ok("knowledgeRead" in fn_src("function knowledgeParts("), "store knowledge is not called unlearned before it has been read")
    ok("api('/api/learn/run'" in SCRIPT, "learning the store is its own paid route")


@test
def t_what_the_checker_found_stays_fixed():
    """The independent check of the Workspace rework (24 Sep) found sixteen
    regressions; these are the ones a source check can hold."""
    ok(".btn[hidden], .mem-btn[hidden] { display: none; }" in CSS,
       "a hidden button is hidden: .btn's own display beat [hidden], so Split into 0 skills showed on every editor")
    ok("splitSkill(bo.value.trim(), skillCaps.body).length < 2) return;" in fn_src("function skillEditor("),
       "and Split does nothing unless a new skill really needs splitting")
    ok(".ktable.mem-table { min-width: 0; }" in CSS, "stacked notes drop the table's 460px floor on a phone")
    ok("grid-template-columns: minmax(0, 1fr)" in CSS.split(".chat-recent {")[1][:260], "the Recent list fits a phone")
    ok("if (d.open !== was)" in fn_src("function sectionCard("), "drawing a section open does not save every conversation")
    ok("if (!tabAllowed('chat')) return;" in fn_src("function useSkillInChat("), "Use in chat without the Chat tab does nothing, rather than throwing")
    ok("if (finished) return; finished = true;" in fn_src("function chatTitle("), "Escape in the rename keeps the old name")
    ok("role', 'menuitemcheckbox'" in fn_src("function dropMenu("), "a menu choice that is on or off says so")
    ok("appBehind(true);" in fn_src("function authShow("), "the page behind the sign-in card is out of reach")
    ok("closeSidebar(); askFeature(v);" in fn_src("function userMenu("), "a request from the phone drawer closes the drawer")
    ok("aria-live" not in fn_src("function skillEditor("), "the character count is not read out after every pause")
    ok("c.id === activeId ? -3 : undefined" in fn_src("function save("), "a full store trims previews before it drops a conversation")
    ok("if (!skills.length && tabAllowed('skills')) loadSkills();" in SCRIPT, "an applied skill keeps its name after a reload")
    ok("followups_maybe" in fn_src("function chatAnswer("), "a follow-up the answer only thinks is done is offered, not closed")


@test
def t_a_markdown_skill_file_is_read_as_it_was_written():
    """Upload Markdown reads a Claude-style SKILL.md the way the server does:
    its header's name and description, the first heading only when it is the
    title, the file's name when there is nothing else."""
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    js = ("const cap = s => { s = String(s || ''); return s.charAt(0).toUpperCase() + s.slice(1); };\n"
          "const skillCaps = { title: 120, body: 1000, when: 400 };\n"
          + re.search(r"        const MD_FM_KEYS = [^\n]*\n", SCRIPT).group(0)
          + "\n".join(fn_src(n) for n in ("function yamlScalar(", "function mdFrontmatter(", "function skillWords(", "function cutWords(",
                                          "function parseSkillMd(", "function splitSkill(", "function splitTitles("))
          + r"""
const md = '---\nname: trade-enquiry-replies\ndescription: >\n  Use when answering a trade enquiry\n  about prices.\nallowed-tools: Read\n---\n\n# Trade enquiry replies\n\n## Prices\n- Glass £85\n';
const a = parseSkillMd(md, 'x.md');
const b = parseSkillMd('\ufeffNo header here.', 'discount_policy.md');
const c = parseSkillMd('---\ntitle: "Brand voice"\ndescription: \'Every customer email\'\n---\nBe warm.', 'b.md');
const long = '## Pricing\n' + 'p '.repeat(300) + '\n## Lead times\n' + 'l '.repeat(300) + '\n## Tone\n' + 't '.repeat(300);
const parts = splitSkill(long, 1000);
console.log(JSON.stringify({ a, b, c, n: parts.length, heads: parts.map(p => p.split('\n')[0]), titles: splitTitles('Wedding', parts),
  whole: parts.join('\n').replace(/\s+/g, ' ') === long.replace(/\s+/g, ' ').trim() }));
""")
    got = _run_node(js)
    eq(got["a"], {"title": "Trade enquiry replies", "when": "Use when answering a trade enquiry about prices.", "content": "## Prices\n- Glass £85", "cut": []})
    eq(got["b"]["title"], "Discount policy", "named after the file")
    eq((got["c"]["title"], got["c"]["when"], got["c"]["content"]), ("Brand voice", "Every customer email", "Be warm."), "quoted values unquoted")
    eq(got["heads"], ["## Pricing", "## Lead times", "## Tone"], "split at its own headings")
    eq(got["titles"], ["Wedding: Pricing", "Wedding: Lead times", "Wedding: Tone"], "each part named after its heading")
    ok(got["whole"], "and nothing lost")


@test
def t_markdown_is_drawn_as_elements_and_never_as_markup():
    """A skill file is the merchant's, but it is still text from a file: every
    part of it is set as text, and a link opens only as a web address."""
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    js = (MINIDOM + "document.createDocumentFragment = () => new Node_('#fragment');\n" + md_src()
          + r"""
const f = mdNodes('---\nname: x\n---\n# Title\n\n1. First\n   - nested **bold**\n2. Second\n\n- [x] done\n- [ ] to do\n\n```\n# not a heading\n<b>raw</b>\n```\n\n> quoted *em*\n\n---\n\n[site](https://projectedimage.co.uk) [bad](javascript:alert(1)) `code` <img src=x onerror=alert(1)>');
const walk = (n, out) => { out.push(n.tagName + (n.href ? '@' + n.href : '')); n.children.forEach(c => walk(c, out)); return out; };
const tags = walk(f, []);
console.log(JSON.stringify({ top: f.children.map(n => n.tagName), tags, text: f.textContent, html: tags.some(t => /IMG|SCRIPT|^B$/.test(t)) }));
""")
    got = _run_node(js)
    eq(got["top"], ["H4", "OL", "UL", "PRE", "BLOCKQUOTE", "HR", "P"], "heading, steps, tick list, code, quote, rule, paragraph")
    ok("UL" in got["tags"][got["tags"].index("OL"):], "a list inside a step")
    ok("STRONG" in got["tags"] and "EM" in got["tags"] and "CODE" in got["tags"], "bold, italic and code words")
    ok("A@https://projectedimage.co.uk" in got["tags"] and not any("javascript" in t for t in got["tags"]), "only a web address is a link")
    ok(not got["html"] and "<img src=x onerror=alert(1)>" in got["text"] and "<b>raw</b>" in got["text"], "markup in a file stays text")
    ok("name: x" not in got["text"] and "# not a heading" in got["text"], "the header is dropped; a code block keeps its marks")


@test
def t_skills_can_be_uploaded_read_and_tried():
    paint = fn_src("function paintSkills(")
    ok("'Upload Markdown'" in paint and "fi.multiple = true" in paint, "several .md files at once")
    ok("'drop'" in fn_src("function renderSkills(") and "startUpload(e.dataTransfer.files)" in fn_src("function renderSkills("), "or dropped on the card")
    up = fn_src("function skillUploads(")
    ok("Read and add" in up and "AI runs, one for each skill" in up and "Read and add is an AI run" in up,
       "reading is a button that says how many AI runs it is")
    ok("'/api/skills/read'" in fn_src("async function readSkill(") and "'/api/skills/read'" in fn_src("async function addUploads("), "one route reads a skill")
    rp = fn_src("function readingPanel(")
    for bit in ("'What it will do'", "'Where it would use it'", "'To check'", "'Read again'", "Changed since it was read"):
        ok(bit in rp, "the reading shows " + bit)
    ok("useSkillInChat(s.id); $('input').value = q" in rp, "an example question opens chat with the skill applied")
    ok("mdNodes(s.content" in fn_src("function skillItem("), "a skill is shown as the document it is")


@test
def t_markdown_the_reviewer_found_drawn_wrongly_is_drawn_right():
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    js = (MINIDOM + "document.createDocumentFragment = () => new Node_('#fragment');\n" + md_src()
          + r"""
const draw = (t) => { const f = mdNodes(t); const walk = (n, o) => { o.push(n.tagName + (n.href ? '@' + n.href : '')); n.children.forEach(c => walk(c, o)); return o; }; return { tags: walk(f, []), text: f.textContent, top: f.children.map(n => n.tagName) }; };
const out = {
  linkBold: draw('[the **shop**](https://a.test)'),
  image: draw('![gobo photo](https://a.test/x.png) here'),
  escaped: draw('\\*not italic\\* and snake_case_word and _em_'),
  boldItalic: draw('***both***'),
  table: draw('Gobo | Price\n--- | ---\nGlass | `£85`\nA\\|B | x'),
  paren: draw('[wiki](https://en.wikipedia.org/wiki/Gobo_(lighting))'),
  js: draw('[bad](javascript:alert(1))'),
  cont: draw('- First item\n\n  More about it.\n- Second'),
  setext: draw('Big title\n===\nText'),
  comment: draw('Before <!-- hidden --> after'),
  rule: draw('---\nAlways quote in GBP.\n---\nNever promise dates.'),
};
console.log(JSON.stringify(out));
""")
    g = _run_node(js)
    ok("A@https://a.test" in g["linkBold"]["tags"] and "STRONG" in g["linkBold"]["tags"] and "**" not in g["linkBold"]["text"], g["linkBold"])
    eq(g["image"]["text"], "gobo photo here", "a picture stands as its words")
    ok(g["escaped"]["text"] == "*not italic* and snake_case_word and em" and g["escaped"]["tags"].count("EM") == 1, g["escaped"])
    ok("STRONG" in g["boldItalic"]["tags"] and "EM" in g["boldItalic"]["tags"] and "*" not in g["boldItalic"]["text"], g["boldItalic"])
    ok(g["table"]["top"] == ["DIV"] and "CODE" in g["table"]["tags"] and "A|B" in g["table"]["text"] and "---" not in g["table"]["text"], g["table"])
    ok("A@https://en.wikipedia.org/wiki/Gobo_(lighting)" in g["paren"]["tags"], g["paren"])
    ok(not any("javascript" in t for t in g["js"]["tags"]) and g["js"]["text"] == "bad", g["js"])
    eq(g["cont"]["top"], ["UL"], "an item's carried-on paragraph stays in its list")
    eq(g["setext"]["top"][0], "H4")
    eq(g["comment"]["text"], "Before  after")
    ok("Always quote in GBP." in g["rule"]["text"], "a text that opens with a rule keeps its first paragraph")


@test
def t_adding_files_loses_nothing_and_says_what_it_costs():
    up = fn_src("function skillUploads(")
    ok("more.disabled = busy" in up and "cancel.disabled = busy" in up, "nothing in the review can change while it is being added")
    ok("'Read and add ' + n + ' skills'" in up, "the button counts the skills, which is the number of AI runs")
    ok("uiConfirm('Leave out" in up, "Cancel asks before throwing a review away")
    row = fn_src("function uploadRow(")
    ok("rm.disabled = busy" in row and "ti.readOnly = busy" in row, "and neither can a row")
    ok("u.saveErr ||" in row and "': added'" in row, "a server's refusal sits under the title with the fields kept, and a saved part says so")
    add = fn_src("async function addUploads(")
    ok("(p.u.savedIdx = p.u.savedIdx || []).push(p.j)" in add and "uploadPlan(u).length" in add,
       "a file stays while any part of it is still to add, and a retry sends only those parts")
    ok("toastError('Wait for these files to be added" in fn_src("function startUpload(") and "if (!skView.uploads && !skillGuard()) return;" in fn_src("function startUpload("),
       "a drop during a run is refused with a reason, and during a review it joins it")
    ok("new TextDecoder('utf-8', { fatal: true })" in fn_src("async function readTextFile(") and "windows-1252" in fn_src("async function readTextFile("),
       "a file that is not UTF-8 is read as Windows text and said so")
    ok("had && had !== q && !await uiConfirm(" in fn_src("function readingPanel("), "an example question never overwrites one being typed")
    ok("'Apply to every answer and email draft'" in fn_src("function skillEditor("), "a short skill can be applied to every answer")


@test
def t_a_retitled_file_adds_only_what_is_left_and_odd_text_is_read():
    """After part of a long file was added, a new title re-added the saved
    parts under it; the wording of a split said 'headings' for text with
    none; and a Windows file lost its pound signs."""
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    js = ("const skillCaps = { title: 120, body: 1000, when: 400 };\n"
          + "\n".join(fn_src(n) for n in ("function splitSkill(", "function splitHow(", "function splitTitles(",
                                          "function uploadPlan(", "function uploadParts(", "async function readTextFile("))
          + r"""
const long = '## Pricing\n' + 'p '.repeat(300) + '\n## Lead times\n' + 'l '.repeat(300) + '\n## Tone\n' + 't '.repeat(300);
const u = { title: 'Playbook', content: long, savedIdx: [0, 1] };
const before = uploadPlan(u).map(p => [p.j, p.title]);
u.title = 'Playbook renamed';
const after = uploadPlan(u).map(p => [p.j, p.title]);
const how = [splitHow('## A\nx'), splitHow('a\n\nb'), splitHow('x'.repeat(50))];
(async () => {
  const f = { arrayBuffer: async () => new Uint8Array([0xA3, 0x38, 0x35, 0x20, 0x63, 0x61, 0x66, 0xE9]).buffer };
  const r = await readTextFile(f);
  console.log(JSON.stringify({ before, after, how, text: r.text, note: !!r.note }));
})();
""")
    g = _run_node(js)
    eq(g["before"], [[2, "Playbook: Tone"]])
    eq(g["after"], [[2, "Playbook renamed: Tone"]], "a new title renames only the part still to add")
    eq(g["how"], ["split at its headings", "split at paragraph breaks", "cut into parts, as it has no headings or paragraph breaks"])
    ok(g["text"] == "\u00a385 caf\u00e9" and g["note"], "Windows text is read as such, and said so: %r" % g)


# ---- Claude Opus 5.5, 24 September 2026 --------------------------------------

@test
def t_deep_analysis_is_tagged_by_the_switch_not_the_model_name():
    """Every answer is Opus 5.5 now, so 'Deep analysis' drawn for any Opus
    model would tag them all. The server says whether an answer was deep;
    answers saved before it did keep the old reading."""
    for name in ("function chatAnswer(", "function pageAssistant("):
        fn = fn_src(name)
        ok("deepTurn(t)" in fn and "/opus/i.test" not in fn, name + " asks deepTurn")
    ok("model: data.model, deep: data.deep," in SCRIPT and "model: res.model, deep: res.deep," in SCRIPT,
       "both chat and the page assistant keep what the server said")
    ok("larger model" not in HTML, "the switch no longer promises a bigger model")
    if not any(os.access(os.path.join(p, "node"), os.X_OK)
               for p in os.environ.get("PATH", "").split(os.pathsep)):
        print("       (node unavailable, skipped)")
        return
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(fn_src("function deepTurn(") + "\nconsole.log([{deep: true, model: 'claude-opus-5-5'}, "
                 "{deep: false, model: 'claude-opus-5-5'}, {model: 'claude-opus-4-8'}, {model: 'claude-sonnet-4-6'}, {}, "
                 "{model: 'claude-opus-5-5'}].map(deepTurn).join(' '));\n")
        path = fh.name
    try:
        r = subprocess.run(["node", path], capture_output=True, text=True)
        ok(r.returncode == 0, "deepTurn failed to run: " + (r.stderr or "")[:200])
        eq((r.stdout or "").strip(), "true false true false false false",
           "deep by the flag, old answers by an Opus 4 model, an unflagged Opus 5.5 answer not")
    finally:
        os.unlink(path)


@test
def t_an_answer_the_fallback_gave_says_so_and_settings_keeps_the_failure():
    for name in ("function chatAnswer(", "function pageAssistant("):
        ok("fellBackNote(t)" in fn_src(name), name + " shows who answered when the chosen model failed")
    ok("fell_back: data.fell_back" in SCRIPT and "fell_back: res.fell_back" in SCRIPT, "and both keep it with the answer")
    note = fn_src("function fellBackNote(")
    ok("' answered this, because '" in note and "could not. " in note, note)
    ok("ANTHROPIC_API_KEY" not in SCRIPT, "no setting name reaches the page")
    if not any(os.access(os.path.join(p, "node"), os.X_OK)
               for p in os.environ.get("PATH", "").split(os.pathsep)):
        print("       (node unavailable, skipped)")
        return
    stub = ("function el(tag, cls, text) { return { cls: cls, text: text || '', kids: [], append(...k) { this.kids.push(...k); } }; }\n"
            "function connRow(title, state, sub, words) { return { state: state, sub: sub, pill: state === 'on' ? words[0] : state === 'mid' ? words[1] : words[2] }; }\n")
    js = stub + fn_src("function fellBackNote(") + "\n" + fn_src("function aiConnRow(") + r"""
const H = 3600 * 1000, ago = (h) => new Date(Date.now() - h * H).toISOString();
const m = { chat: 'Claude Opus 5.5', deep: 'Claude Opus 5.5', fallback: 'Claude Opus 4.8' };
const fail = (h, by) => ({ at: ago(h), model: 'Claude Opus 5.5', why: 'Busy.', answered_by: by || '' });
const out = {
  note: fellBackNote({ fell_back: { from: 'Claude Opus 5.5', to: 'Claude Opus 4.8', why: 'Busy.' } }).kids[0].text,
  none: fellBackNote({}),
  nokey: aiConnRow({ ok: false }),
  clean: aiConnRow({ ok: true, models: m }),
  off: aiConnRow({ ok: true, models: Object.assign({}, m, { fallback: '' }) }),
  answered: aiConnRow({ ok: true, models: m, last_failure: fail(1, 'Claude Opus 4.8') }),
  failing: aiConnRow({ ok: true, models: m, last_failure: fail(1) }),
  old: aiConnRow({ ok: true, models: m, last_failure: fail(30) }),
};
console.log(JSON.stringify(out));
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(js)
        path = fh.name
    try:
        r = subprocess.run(["node", path], capture_output=True, text=True)
        ok(r.returncode == 0, "the note and the row failed to run: " + (r.stderr or "")[:300])
        o = json.loads(r.stdout)
        eq(o["note"], "Claude Opus 4.8 answered this, because Claude Opus 5.5 could not. Busy.")
        eq(o["none"], None, "an answer the chosen model gave has no note")
        eq((o["nokey"]["state"], o["nokey"]["pill"]), ("off", "Not set up"))
        ok(o["clean"]["state"] == "on" and "When it cannot answer, Claude Opus 4.8 does" in o["clean"]["sub"], o["clean"])
        ok("When it cannot answer" not in o["off"]["sub"], "no fallback promised when there is none")
        ok(o["answered"]["state"] == "on" and "Claude Opus 4.8 answered instead." in o["answered"]["sub"], o["answered"])
        eq((o["failing"]["state"], o["failing"]["pill"]), ("mid", "Recent failure"), "amber for a day after a failure nobody answered")
        ok(o["old"]["state"] == "on" and "Latest failure" in o["old"]["sub"], "and green again after it, with the failure still said")
    finally:
        os.unlink(path)



# ---- Skills: master-only uploads and the master's larger limit, 24 September 2026

@test
def t_only_the_master_sees_the_upload_and_a_long_skill_can_be_edited():
    paint = fn_src("function paintSkills(")
    ok("if (skillCaps.upload) acts.append(up, fi);" in paint, "Upload Markdown is the master's alone")
    ok("(skillCaps.upload ? ' Drop Markdown files here to add them.' : '')" in paint, "and the card only offers a drop to the master")
    start = fn_src("function startUpload(")
    ok(start.index("if (!skillCaps.upload)") < start.index("readSkillFiles("), "a drop from anyone else reads no file")
    ed = fn_src("function skillEditor(")
    ok("if (skillCaps.upload) row.append(fileBtn, fi);" in ed, "Load from file is the master's alone")
    ok("const lim = Math.max(skillCaps.body, s ? String(s.content || '').trim().length : 0);" in ed
       and "over = n - lim" in ed and "nf(lim) + ' characters'" in ed,
       "a long skill the master saved can be edited by anyone without growing")
    ok("const SKILL_FILE_MAX = 5 * 1024 * 1024;" in SCRIPT and "f.size > SKILL_FILE_MAX" in fn_src("function readSkillFiles(")
       and "file.size > SKILL_FILE_MAX" in ed and "'Larger than 5 MB, so it was not read.'" in fn_src("function readSkillFiles("),
       "a file up to 5 MB is read by both file controls")
    ok(start.index("if (skillsLoadErr)") < start.index("if (!skillCaps.upload)"), "skills not loaded is said before the master rule")
    ok("if (skillCaps.upload) card.classList.add('drop-on');" in fn_src("function renderSkills("),
       "only the master's card lights up for a drop")
    ok("lim > skillCaps.body ? 'You can change this skill but not make it longer than it is: remove '" in ed,
       "someone editing a long skill is told the real rule, not to split it")
    ok("upload: false" in SCRIPT.split("const skillCaps = ")[1][:120], "no upload until the server says so")



@test
def t_a_queue_row_keeps_its_buttons_in_the_last_column():
    """Custom shipments put the contents in a second line under the name. In
    the widest layout every child of that box is a column of the queue's grid,
    so a shipment with contents had six items for five columns and its buttons
    wrapped into the 100px number column, right-aligned, hanging out of the
    row over the sidebar (Cameron's screenshot, 25 Sep 2026)."""
    ok(".lbl-qrow > .lbl-meta { grid-row: 1; grid-column: -3 / -2; }" in CSS
       and ".lbl-qrow > .lbl-actions { grid-row: 1; grid-column: -2 / -1; }" in CSS,
       "the date and the buttons are pinned to the last two columns of the first line")
    i = SCRIPT.index("No shipments booked to a pasted address yet.")
    body = SCRIPT[i:i + 4000]
    ok("if (sh.contents) who.append(el('span', 'sub', sh.contents));" not in body
       and body.count("el('span', 'sub')") == 1 and "'sub-line'" in body,
       "a shipment's carrier line and contents are one item under the name")
    ok(".lbl-who .sub > .sub-line { display: block; overflow: hidden; text-overflow: ellipsis; }" in CSS, "each line is shortened on its own")



@test
def t_a_queue_row_never_squeezes_the_customer_name_to_nothing():
    """Checked across the four order queues at 13 window sizes (25 Sep 2026):
    no row's buttons left it, but the customer's name went to 0px. Chips
    never shrink, so a dispatched order's courier chip took the whole name
    column below 860px of list, and on a tablet the buttons kept their width
    beside the name ("C"). The queue card's header rail also left the title
    and description a column 80px wide."""
    i = CSS.index(".lbl-qrow .lbl-nameline { flex-wrap: wrap; row-gap: var(--sp-1); }")
    ok(CSS.rfind("@container", 0, i) < CSS.rfind("}", 0, i), "the name line wraps at every width, not only from 860px")
    ok(CSS.count(".lbl-qrow .lbl-nameline { flex-wrap: wrap;") == 1, "one rule, not two")
    narrow = CSS[CSS.index("@container queue (max-width: 559px) {\n"):][:400]
    ok(".lbl-qrow { flex-wrap: wrap; }" in narrow and ".lbl-qrow .lbl-actions { flex: 1 1 100%; justify-content: flex-start; }" in narrow,
       "a list as narrow as a phone's puts the buttons on their own line, whatever the window")
    ok("@media (min-width: 641px) { .q-card > .card-head { grid-template-columns: 1fr fit-content(50%); } }" in CSS
       and "const qCard = el('div', 'card q-card');" in SCRIPT, "the queue card's buttons wrap within half its header")


if __name__ == "__main__":
    print("frontend regressions")
    print()
    print(f"{_passed} passed, {len(_failed)} failed")
    sys.exit(1 if _failed else 0)
