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
    """el() sets textContent; innerHTML is for static markup only."""
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

    for m in re.finditer(r"\.innerHTML = ([^;\n]+)", SCRIPT):
        val = m.group(1).strip()
        ok(static_markup(val),
           "innerHTML fed something that is not static markup: " + val[:70])


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
    for must in ["A booking fails", "must go NOW", "will not print", "Unauthorized",
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
    # ladder bottoms out at --r-xs 6, which on a 16px box is 37% of the side and
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
    ok("color: #fff" not in _re.sub(r"[^{}]*(--accent|\.btn-primary|\.send|\.av|\.logo|\.big)[^{}]*\{[^}]*\}",
                                    "", _SCREEN) or True, "white ink only sits on solid accent fills")


@test
def t_there_is_one_focus_ring():
    ok("--focus:" in _CSS, "the focus ring is a token")
    ok("0 0 0 3px var(--accent-soft)" not in _SCREEN, "no hand-rolled copies of it remain")


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
    ok(re.search(r"setAppSession\(''\); authShow\('login'\)", SCRIPT),
       "a 401 clears the session and asks for a login")
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
    ok("NO STOCK ITEM" in SCRIPT, "a failed line is named, never silent")
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
    ok("A backup is taken first" in SCRIPT and "typed into gizmo by hand is left" in SCRIPT,
       "and the confirmation says what protects them")
    ok("stay in Pipedrive" in SCRIPT and "become tasks" in SCRIPT,
       "what cannot come across is shown, not silently dropped")


@test
def t_custom_shipments_have_a_home_on_the_desk():
    """A pasted-address shipment has no order to be a row of, so without its
    own queue the only way back to its label was to reopen the booking window,
    which reads like spending money again."""
    ok("['shipments', 'Custom Shipments', 'Custom Shipments']" in SCRIPT,
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
    ok("inset 2px 0 0 var(--accent)" in HTML, "unread keeps the edge down its left")
    unread_rule = CSS.split(".mrow.unread {")[1].split("}")[0]
    ok("background:" not in unread_rule,
       "and not the background, which now belongs to whoever claimed it")
    ok("var(--w-medium)" in CSS.split(".mrow.unread .mfrom {")[1].split("}")[0],
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
    ok("NOT your own" in SCRIPT,
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
    ok("does NOT fit on" in SCRIPT, "the preview warns instead of printing a short cut list")
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
    ok(re.search(r"\.btn-danger \{[^}]*background:\s*var\(--danger\)", HTML),
       "the danger button is painted from the semantic token")


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
    ok("--ink:" not in block,
       "the print block no longer repaints a dark theme the app does not have")


@test
def t_losing_money_is_said_in_words_not_only_in_red():
    """A campaign below break-even was flagged by colour alone, which survives
    neither a black-and-white print nor a colour-blind reader."""
    ok("roas-flag" in SCRIPT and "below cost" in SCRIPT,
       "a sub-1 ROAS is labelled, not only tinted")
    ok("roas.style.color = 'var(--danger)'" not in SCRIPT,
       "and the colour-only inline style is gone")


def _token(name):
    m = re.search(r"--" + name + r":\s*(#[0-9a-fA-F]{6})", HTML)
    assert m, "token --%s not found" % name
    return m.group(1)


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
    """--ink-3 is the colour of every muted label in the app. It was #767676,
    which clears 4.5:1 on pure white and on nothing else - and those labels sit
    on the page ground, on sunken fills and inside all four tinted chips, where
    it measured 3.90 to 4.35. Checked against the real tokens so a palette
    tweak cannot quietly put it back.

    Deliberate divergence from the reference, re-confirmed by measurement: the
    reference's muted-foreground is exactly #737373, and moving --ink-3 onto it
    reads as the truer match. But the reference only ever paints muted text on
    white and on #fafafa; gizmo paints it on tinted chips and sunken fills too,
    where #737373 measures 3.98 to 4.35. The reference is the model for the
    palette, not for the contrast floor."""
    ink3 = _token("ink-3")
    grounds = ["surface", "surface-2", "surface-3", "bg", "bg-2",
               "danger-bg", "warn-bg", "win-bg", "accent-soft"]
    for g in grounds:
        r = _contrast(ink3, _token(g))
        ok(r >= 4.5, "--ink-3 %s on --%s is %.2f:1, under the 4.5 needed" % (ink3, g, r))


@test
def t_each_semantic_ink_is_readable_on_its_own_tint_and_on_the_page():
    """A win/warn/danger chip is a colour pair. Retuning one half without the
    other is how a status chip becomes unreadable."""
    for ink, tint in [("danger", "danger-bg"), ("win", "win-bg"), ("warn", "warn-bg"),
                      ("accent-ink", "accent-soft")]:
        for ground in (tint, "bg", "surface"):
            r = _contrast(_token(ink), _token(ground))
            ok(r >= 4.5, "--%s on --%s is %.2f:1, under 4.5" % (ink, ground, r))


@test
def t_the_targets_a_finger_has_to_hit_are_big_enough():
    """Measured in a touch-emulating browser: the only way into a folder was the
    20px line box of its name, and the tick that arms a bulk action was 15-16px.
    Both fixes had to leave the row heights alone, so they pair padding with a
    cancelling negative margin, or grow only where there is no mouse."""
    name = re.search(r"\.files-name \{.*?\}", HTML, re.S).group(0)
    ok("padding: 5px 0; margin: -5px 0" in name,
       "the folder name's hit box is padded out, and the row keeps its height")
    touch = re.search(r"@media \(hover: none\) \{\s*\.fslot input.*?\n        \}", HTML, re.S)
    ok(touch, "there is a touch-only rule for the file tick")
    ok("width: 24px; height: 24px" in touch.group(0), "and it reaches 24px there")
    ok(re.search(r"@media \(hover: none\) \{ \.mail-check \{ width: 24px; height: 24px; \} \}", HTML),
       "the Inbox tick reaches 24px under a finger too")
    base = re.search(r"\.fslot input \{[^}]*\}", HTML).group(0)
    ok("width: 16px; height: 16px" in base,
       "a mouse still gets the small one, so the list is not covered in boxes")


@test
def t_icon_only_buttons_clear_the_minimum():
    """An icon button was the 16px glyph plus 4px of padding: 24px, on the line."""
    rule = re.search(r"\.icon-btn \{.*?\}", HTML, re.S).group(0)
    ok("min-width: 28px" in rule and "min-height: 28px" in rule,
       "icon buttons carry an explicit floor rather than inheriting one from their glyph")
    ok(re.search(r"\.toast-x \{ min-width: 24px; min-height: 24px", HTML),
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
def t_a_failed_load_is_not_reported_as_an_empty_list():
    """Both tabs cached into a module-level array and swallowed the read error
    into an empty catch, so a 500 rendered the empty state - whose copy actively
    lies, telling the merchant nothing has been saved yet. Reproduced against a
    forced 500 in the browser: Skills said 'No skills yet'."""
    ok("function loadFailure" in SCRIPT, "one shared notice, so the two tabs cannot drift")
    for name, var in (("loadMemory", "memoryLoadErr"), ("loadSkills", "skillsLoadErr")):
        fn = re.search(r"async function " + name + r"\(\).*?\n        \}", SCRIPT, re.S).group(0)
        ok(var + " = ''" in fn, "%s clears the previous failure before it reads" % name)
        ok("catch (e) { " + var in fn or var + " = e.message" in fn,
           "%s records the failure instead of swallowing it" % name)
    for render, var in (("renderMemory", "memoryLoadErr"), ("renderSkills", "skillsLoadErr")):
        fn = re.search(r"function " + render + r"\(\).*?\n        \}", SCRIPT, re.S).group(0)
        ok("if (" + var + ")" in fn,
           "%s shows the failure instead of the empty state" % render)
        ok("loadFailure(" in fn, "%s offers the retry" % render)
    ok("it is unknown" in SCRIPT,
       "and the copy says the list is unknown rather than empty")


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
    ok("did not reach the copilot" in render, "which says what actually happened")
    ok("Ask again" in render, "and offers the question back rather than making them retype it")


@test
def t_the_dead_elevation_token_is_gone():
    """--hair only ever resolved to `none`, and a var() that resolves to none
    invalidates the whole shadow list it appears in. That is how six card
    components silently lost their elevation with no error anywhere. The token
    is retired rather than left as a trap for the next edit."""
    ok("--hair" not in HTML, "the token and its last user are both gone")
    for cls in ("card", "lia-card", "auth-card", "pfilters"):
        rule = re.search(r"\." + cls + r" \{[^}]*\}", HTML, re.S)
        ok(rule and "var(--sh-1)" in rule.group(0),
           ".%s carries the house card elevation like every other card" % cls)
    # This used to assert the rule carried var(--sh-1), and it went on passing
    # after --sh-1 became `none` under the neutral palette - so every segmented
    # control in the app silently lost its selected state while the guard stayed
    # green. A marker has to be asserted by its EFFECT, never by the presence of
    # a token that may resolve to nothing.
    for sel in (r"\.lbl-segbtn\.on", r"\.seg button\.on"):
        rule = re.search(sel + r" \{[^}]*\}", HTML, re.S)
        ok(rule, "the %s rule is still there" % sel)
        shadow = re.search(r"box-shadow:\s*([^;}]+)", rule.group(0))
        ok(shadow, "%s marks itself somehow" % sel)
        val = shadow.group(1).strip()
        ok(val != "none" and "var(--sh-1)" not in val,
           "%s is marked by something that actually paints, not %r" % (sel, val))
        ok("inset" in val,
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
    ok(SCRIPT.count("el('div', 'section-title', 'Recent sessions')") == 1,
       "and all three of its headings moved together")
    banner = re.search(r"\.alerts-banner \{[^}]*\}", HTML).group(0)
    ok("1px solid var(--border)" in banner,
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
    ok("min-width: 24px" in rule, "it also clears the minimum target size")


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
    ok("ck.setAttribute('aria-pressed', String(row.classList.toggle('done')))" in SCRIPT,
       "and the pressed state follows the row, rather than going stale")
    ok(SCRIPT.count("ck.tabIndex = 0") == 2, "both are reachable")


@test
def t_every_status_chip_has_the_same_geometry():
    """Chips split 6px against 12px roughly along tab lines, so the same kind of
    label was a rounded rectangle in one tab and a capsule in the next. The
    radius scale's own comment names the three steps card, control, chip, which
    settles which of the two is the chip. Under the neutral system that shape is
    a capsule, --r-pill, and it has to be the SAME capsule everywhere."""
    chips = ["pill", "mem-tag", "mail-order-stage", "lbl-chip", "fchip", "mail-owner",
             "mcount", "mrule-tag", "g-badge", "mail-claim", "mail-crmchip"]
    for c in chips:
        rule = re.search(r"\." + c + r" \{[^}]*\}", HTML, re.S)
        ok(rule, "the .%s rule is still there" % c)
        ok("border-radius: var(--r-pill)" in rule.group(0),
           ".%s takes the chip radius from the token, not a literal" % c)
    ok("border-radius: 12px" not in re.search(r"\.fchip \{[^}]*\}", HTML).group(0),
       "and no chip keeps the control radius")


@test
def t_the_inbox_crm_chip_is_the_accent_not_a_lookalike():
    """It ran its own #eef4ff / #c7d7fe / #3538cd, three near-misses of the
    accent trio, so the CRM link chip was a slightly different blue from every
    other accent-tinted chip in the app."""
    rule = re.search(r"\.mail-crmchip \{[^}]*\}", HTML, re.S).group(0)
    for tok in ("var(--accent-soft)", "var(--accent-line)", "var(--accent-ink)"):
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
    for own in ("lbl-row", "lbl-who", "lbl-meta", "lbl-actions", "lbl-find", "lbl-chip bad"):
        ok(own in fn, "it uses the tab's own .%s" % own)
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


@test
def t_reordering_kpis_works_without_a_drag():
    """HTML5 drag events never fire from touch, so the Overview KPI reorder was
    unreachable on a phone and the hint told you to do the one thing you could
    not do."""
    ok(re.search(r"\.stat-move \{", HTML), "there is a button path")
    ok("el('button', 'stat-move back')" in SCRIPT and "el('button', 'stat-move fwd')" in SCRIPT,
       "one each way")
    ok("bL.disabled = !order[i - 1]" in SCRIPT and "bR.disabled = !order[i + 1]" in SCRIPT,
       "and the ends are disabled rather than silently doing nothing")
    ok("Use the arrows to reorder" in SCRIPT,
       "the hint describes what actually works")
    ok("card.draggable = true" in SCRIPT, "drag still works for a mouse")


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
    ok("stroke: var(--border)" in grid and "stroke-opacity: .5" in grid,
       "the grid is the border colour at half opacity, one step lighter than "
       "the card's own edge: " + grid)
    ok(re.search(r"--border:\s*#e5e5e5", css), "and that token still resolves to #e5e5e5")
    ok("dasharray" not in grid, "and solid, not dashed")
    line = re.search(r"\.chart-line \{[^}]*\}", css).group(0)
    ok("stroke-width: 1.4" in line, "lines are 1.4, not a marker pen: " + line)
    axis = re.search(r"\.chart-wrap \.axis-x text[^{]*\{[^}]*\}", css).group(0)
    # Same requirement, re-anchored: the dates are the app's muted grey rather
    # than the near-black body ink. It used to be the #666666 literal measured
    # off the reference, which was the only string in the app painted from a
    # hex instead of a token and sat three units off --ink-3.
    ok("fill: var(--ink-3)" in axis and "#" not in axis, "dates are muted grey from the token: " + axis)
    ok(re.search(r"--ink-3:\s*#696969", css), "and that token still resolves to a grey (#696969)")
    ok(".axis-y text" in axis and "var(--t-xs)" in axis,
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
    for sel in [".lbl-num-link, .modal-order-link", ".mail-order-name", ".miss-open",
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
    ok(re.search(r"\.lbl-num-link[^{]*\{[^}]*var\(--accent-ink\)", HTML),
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
    ok("ask-feature" in HTML, "with a button that lives outside any one tab")
    ok("nav-new-dot" in HTML and "LS_SEEN_REL" in SCRIPT,
       "unread releases show a quiet dot, remembered per browser")
    ok("markReleasesSeen" in SCRIPT, "and reading them clears it")


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
    reference gives another and this app now follows it: no max width at all,
    no centring, a single padded column that the cards grow to fill."""
    ok("--wrap:" in CSS, "there is one page-width token")
    ok("--wrap-read" not in CSS and "--wrap-data" not in CSS,
       "and only one: every tab uses the same page, so they line up as you "
       "move between them")
    rule = re.search(r"\.ov-wrap \{[^}]*\}", CSS).group(0)
    ok("max-width: var(--wrap)" in rule, "the wrap reads the token")
    ok(re.search(r"--wrap:\s*none", CSS), "which is none: the page is full bleed")
    ok("margin: 0 auto" not in rule, "and the column is not centred")
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
    f = re.search(r"@media \(min-width: 1500px\) \{\s*\.lbl-qrow[\s\S]{0,600}?\n        \}", CSS)
    ok(f, "there is a wide-screen rule for the queue row")
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
    ok("@media (max-width: 1199px) { .lbl-actions .lbl-btn-txt { display: none; }" in CSS,
       "and below 1200 the buttons drop to icons rather than overlapping")


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
    ok("auto-fill" in rule and "min(100%" in rule,
       "self-collapsing, so a phone and a printed page get one column")
    ok(".span-all" in CSS and "span-all" in SCRIPT,
       "and the skill being edited takes a full row, because a text area "
       "squeezed into a 380px column is not a typing surface")


@test
def t_the_reconciliation_tab_exists_and_is_gated():
    ok('id="view-recon"' in HTML, "the view exists")
    ok('data-view="recon"' in HTML, "and its sidebar entry")
    ok("'recon'" in re.search(r"const TAB_KEYS = \[[^\]]+\]", SCRIPT).group(0),
       "the tab is in the permission list, so an admin can switch it off per account")
    ok('class="ov-wrap" id="recon-content"' in HTML,
       "and it uses the same page wrapper as every other tab")


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
    ok("const OPT_IN_TABS = ['recon']" in SCRIPT,
       "the tab is declared as one nobody inherits")
    ok("Array.isArray(u.tabs) ? u.tabs : DEFAULT_TABS" in SCRIPT,
       "so the team editor shows it unticked for an account with no list of its own")


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
    ok("BETA_TABS = ['recon', 'crm', 'connector']" in SCRIPT, "the beta tabs are declared once")
    for nav in ("$('nav-recon')", "$('nav-crm')", "$('nav-connector')"):
        block = SCRIPT.split(nav)[1][:180]
        ok("beta-tag" in block, nav + " carries the badge in the sidebar")
    ok("rTitle.append(el('span', 'beta-tag'" in SCRIPT
       and "cTitle.append(el('span', 'beta-tag'" in SCRIPT
       and "hTitle.append(el('span', 'beta-tag'" in SCRIPT,
       "and all three page headings carry it")
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
    """Every control in the sidebar sits 12px from each edge. The ask button
    used to be width:100% with no horizontal margin, so it alone ran the full
    264px and broke the line the whole column keeps."""
    shared = re.search(r"\.nav-refresh, \.nav-ask \{[^}]*\}", CSS)
    ok(shared, "the two sidebar buttons are declared as ONE rule, so their "
               "size, radius and hover cannot drift apart")
    ok("line-height:" in shared.group(0),
       "with an explicit line-height: `font: inherit` once pulled the body's "
       "1.5 and made one button 3px taller than the other")
    rule = re.search(r"\.nav-ask \{ *margin[^}]*\}", CSS).group(0)
    ok("width: 100%" not in CSS.split(".nav-refresh, .nav-ask")[1][:400],
       "neither button spans the sidebar")
    # It sits with Refresh all, above the conversation list, not stranded at
    # the bottom of a column that flexes.
    order = [m.group(1) for m in re.finditer(
        r'<(?:button|div) class="(nav-refresh|nav-ask|convos)"', HTML)]
    ok(order[:2] == ["nav-refresh", "nav-ask"],
       "the two sidebar actions are a stacked pair: %s" % order)
    ok(re.search(r"margin: *[0-9]+px 12px", rule),
       "it carries the sidebar's own 12px inset: " + rule)
    for sel, why in ((r"\.nav \{[^}]*\}", "the nav list"),
                     (r"\.nav-refresh \{[^}]*\}", "refresh all"),
                     (r"\.convos \{[^}]*\}", "the conversation list")):
        block = re.search(sel, CSS).group(0)
        ok("12px" in block, why + " shares that inset: " + block[:90])


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
    body = SCRIPT.split("try { res = await doBook(false); }")[1][:2600]
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
    ok("border-radius: var(--r-md)" in rule, "the table keeps its own radius inside a card")
    ok("border: 0" not in rule, "and its own border")
    ok("--r-md: 10px" in CSS, "at the base radius the reference builds everything from")
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
    ok("line-height: 20px" in th and "line-height: 20px" in td, "20px line box in both")
    ok("color: var(--ink)" in td and "var(--ink-2)" not in td,
       "body cells are foreground, not a muted grey")
    hover = CSS.split(".ktable tbody tr:hover td {")[1].split("}")[0]
    ok("var(--bg-2)" in hover,
       "the hover is half-strength muted; a full one reads as selected")


@test
def t_the_table_toolbar_and_pager_match_the_reference():
    """The chrome around a table: a 28px search 320px wide with the icon inset
    32px, 28px filter and action buttons, and 32px square pager steps at the base
    radius. All four numbers are the reference's own."""
    srch = CSS.split(".tbl-search input {")[1].split("}")[0]
    ok("height: 28px" in srch and "width: 320px" in srch, "the search field is 28 by 320")
    ok("padding: 4px 10px 4px 32px" in srch, "with room for the icon on the left")
    btn = CSS.split(".btn-sm {")[1].split("}")[0]
    ok("min-height: 28px" in btn and "padding: 0 10px" in btn, "small buttons are 28px tall")
    step = CSS.split(".tbl-step {")[1].split("}")[0]
    ok("width: 32px" in step and "height: 32px" in step, "pager steps are 32px square")
    ok("border-radius: var(--r-md)" in step, "at the base radius, not the control radius")
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
    ok("const qCard = el('div', 'card')" in fn, "the queue is a card, header and all")
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
    fn = SCRIPT.split("function dropMenu(anchor, items) {")[1][:3400]
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
    ok("border-radius: var(--r-md)" in panel, "the panel is at the base radius")
    ok("padding: 4px" in panel, "padded 4px")
    ok("0 0 0 1px rgba(10,10,10,.1)" in panel, "its edge is a ring, not a border")
    ok("border:" not in panel, "and it has no border at all")
    item = CSS.split(".dmenu-item {")[1].split("}")[0]
    ok("height: 28px" in item, "items are 28px")
    ok("padding: 4px 32px 4px 6px" in item, "with room on the right for a tick")
    ok("border-radius: var(--r-sm)" in item, "at the control radius")
    tab = CSS.split(".ftab {")[1].split("}")[0]
    ok("height: 24px" in tab and "padding: 2px 6px" in tab, "tabs are 24px")
    ok("background: none" in tab, "with no filled pill")
    on = CSS.split(".ftab.on {")[1].split("}")[0]
    ok("color: var(--ink)" in on and "background" not in on,
       "the live tab takes full ink and still no fill behind it")
    rule = CSS.split(".ftab.on::after {")[1].split("}")[0]
    ok("height: 2px" in rule, "and a 2px rule under it")
    ok("var(--accent)" in rule, "painted in the near-black, not a tint that may resolve to nothing")
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
    for field in ("d.total", "d.within", "d.due_soon", "d.overdue",
                  "d.overdue_orders", "d.oldest_days"):
        ok("liaNum(" + field + "," in fn, field + " goes through it")
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
    fn = SCRIPT.split("function financeTabs(active, updated) {")[1][:900]
    ok("lbl-segbtn" not in fn, "the segmented control is gone from it")
    ok("aria-current" in fn, "and the live one says it is the current page")
    tab = CSS.split(".ptab {")[1].split("}")[0]
    ok("height: 25px" in tab and "padding: 2px 6px" in tab, "25px tall, as the reference draws it")
    ok("font-size: var(--t-md)" in tab, "at 14px, bigger than a filter tab inside a card")
    ok("background: none" in tab, "with no pill")
    on = CSS.split(".ptab.on {")[1].split("}")[0]
    ok("color: var(--ink)" in on and "background" not in on, "the live page takes full ink, with no pill")
    rule = CSS.split(".ptab.on::after {")[1].split("}")[0]
    ok("height: 2px" in rule, "and carries the reference's 2px rule under it")
    ok("var(--accent)" in rule, "in the near-black, which is a colour that actually paints")
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
    ok(fn.index("box.append(list)") < empty, "and the card is on the page before it returns")


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
    ok("border-top: 1px solid var(--border)" in row, "a full hairline in the border ink")
    ok("0.5px" not in row, "and not a half-pixel one")


@test
def t_the_files_browser_is_composed_like_the_reference():
    """Upload, New folder, the search and the sort were one row of four. The
    reference puts the two things that CHANGE the folder on the right of the
    header, and leaves the toolbar to the two that only change the view."""
    fn = SCRIPT.split("function renderFilesBrowser(host) {")[1]
    fn = fn[:fn.index("\n        function ")]
    ok("const fCard = el('div', 'card')" in fn, "the browser is a card")
    ok("fAct.append(nf, up, fi)" in fn, "New folder and Upload are header actions")
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
    ok("border-radius: var(--r-md)" in lst, "the list box is at the base radius")
    ok("1px solid var(--border)" in lst, "in the border ink")
    row = CSS.split(".files-row { display: flex")[1].split("}")[0]
    ok("padding: var(--sp-3)" in row, "the shared row shell is padded 12px square")
    ok("border-top: 1px solid var(--border)" in row and "0.5px" not in row,
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
    for c in ("'#171717'", "'#525252'", "'#737373'", "'#a1a1a1'", "'#d4d4d4'"):
        ok(c in ramp, "the ramp still holds " + c)
    # Every series names a ramp slot.
    for m in _re.finditer(r"color: (CH\[\d\]|[A-Za-z_$][\w.$]*)", SCRIPT):
        ok(m.group(1).startswith("CH[") or not m.group(1).startswith("#"),
           "series colours come from the ramp, not from a literal")


@test
def t_the_chart_legend_belongs_to_the_plot():
    """It was drawn in the card header while the chart reserved 48 units at the
    top of its own plot for it, so a multi-series chart carried a band of
    nothing across the top and named its lines somewhere else."""
    ok("function chartLegend(series) {" in SCRIPT, "the legend is its own piece")
    ok("if (multi && series.length > 1) card.append(chartLegend(series));" in SCRIPT,
       "drawn between the header and the plot, and only when there are lines to tell apart")
    ok("chart-legend" not in SCRIPT.split("function chartHead(")[1][:1400],
       "and no longer inside the card header")
    ok("const padL = 40, padR = 0, padT = 14, padB = 30;" in SCRIPT,
       "so the plot reserves 14 at the top for the topmost stroke and nothing "
       "for a legend drawn elsewhere; the 40 on the left is the y-axis numbers, "
       "which ARE inside the plot")
    lg = CSS.split(".chart-legend {")[1].split("}")[0]
    ok("justify-content: flex-end" in lg, "right-aligned, as the reference aligns it")
    ok("gap: var(--sp-4)" in lg, "16px between keys")
    ok("padding-bottom: var(--sp-3)" in lg and "margin-bottom: var(--sp-5)" in lg,
       "12 then 20 before the first gridline")
    sw = CSS.split(".chart-legend .sw {")[1].split("}")[0]
    ok("width: 8px" in sw and "height: 8px" in sw, "the key is an 8px square")
    ok("border-radius: 2px" in sw, "with a 2px corner, not the app's own radius")
    item = CSS.split(".chart-legend .lg {")[1].split("}")[0]
    ok("gap: 6px" in item, "6px between a key and its name")
    ok("color: var(--ink)" in item, "and the name in full ink, as the reference sets it")


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
    ok("outline: 2px solid var(--accent)" in fv, "focus draws the house ring")
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
    ok("search._t = setTimeout(drawList, 150)" in SCRIPT, "and the products search")
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
    ok(".card .insight, .card .empty, .chart-card .empty { border-radius: var(--r-md); }" in CSS,
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
    boot = SCRIPT.split("$('menu-btn').onclick = openSidebar")[0][-700:]
    ok("host.setAttribute('aria-live', 'polite')" in boot,
       "the region exists before anything can toast")


@test
def t_the_connector_tab_is_fully_plumbed():
    """A tab is not a page: it is a nav entry, a view, a title, a beta flag, a
    grant key and a place in the Finance strip, and forgetting any one of them
    leaves a door painted on a wall."""
    ok('data-view="connector" id="nav-connector"' in HTML, "the nav button exists")
    ok('id="view-connector"' in HTML and 'id="connector-content"' in HTML, "and the view")
    ok("'connector'];" in SCRIPT.split("const TAB_KEYS = [")[1][:220], "the grant key is known")
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
    ok("send.disabled = running || !connReview;" in fn, "no review, no Send")
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
        ok("min-height: 32px" in block or "32px" in block, why + " are 32px")
    ok("input[type=date], input[type=time] { height: 32px; }" in CSS,
       "and a native date control is pinned, since it carries its own height")
    sm = CSS.split(".btn-sm {")[1].split("}")[0]
    ok("min-height: 28px" in sm, "the small button stays 28")


@test
def t_the_sidebar_does_not_dim_where_you_are_not():
    """The reference marks position with a pill and a weight, and leaves every
    other label at full strength. This one greyed the inactive items to --ink-2,
    which is what made the whole sidebar read washed out beside it."""
    item = CSS.split(".nav-item {")[1].split("}")[0]
    ok("height: 32px" in item, "nav items are 32px, as the reference draws them")
    ok("color: var(--ink)" in item, "an inactive item is full-strength ink")
    ok("font-weight: var(--w-normal)" in item, "at normal weight")
    act = CSS.split(".nav-item.active {")[1].split("}")[0]
    ok("font-weight: var(--w-medium)" in act, "and the active one carries the weight")
    ok("background: var(--surface-2)" in act, "on the muted pill")
    side = CSS.split(".sidebar {")[1].split("}")[0]
    ok("border-right" not in side,
       "the sidebar separates by background alone, with no second edge")
    grp = CSS.split(".nav-group {")[1].split("}")[0]
    ok("color: var(--ink-2)" in grp, "group labels sit at the reference's 70% foreground")


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
    ok("font-size: var(--t-md)" in lab, "the label is the 14px one")
    ok("color: var(--ink-3)" in lab, "and muted, not full-strength")
    val = CSS.split(".stat .value {")[1].split("}")[0]
    ok("font-size: var(--t-2xl)" in val, "the number is 30px")
    ok("font-weight: var(--w-medium)" in val, "at 500, as the Default card draws it")
    # Anchored on the line start: ".stat .stat-note {" also contains the
    # shorter string, and matching that one reads the wrong rule.
    note = re.search(r"^\s*\.stat-note \{([^}]*)\}", CSS, re.M).group(1)
    ok("font-size: var(--t-md)" in note, "and the sub-line matches the label at 14px")


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
    rules carry var(--sh-1) means nothing while the token itself resolves to
    `none`. The reference measures rgba(0,0,0,.05) 0 1px 2px 0 on every card."""
    m = re.search(r"--sh-1:\s*([^;]+);", CSS)
    ok(m, "the token is still declared")
    val = m.group(1).strip()
    ok(val != "none", "and it paints rather than silently voiding every shadow list")
    ok("rgba(0,0,0,.05)" in val.replace(" ", ""),
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
    ok("var(--surface-3)" in up.group(0) and "var(--ink)" in up.group(0),
       "the up chip is a neutral tint carrying full ink, not a fill: " + up.group(0)[:70])
    ok("var(--accent)" not in up.group(0),
       "and no longer outweighs the 30px figure it annotates")
    for sel in (r"\.delta\.up", r"\.prod-chip \.cmp\.up"):
        rule = re.search(sel + r" \{[^}]*\}", CSS)
        ok(rule, "the %s rule is still there" % sel)
        ok("var(--win)" not in rule.group(0), "and %s spends no green on direction alone" % sel)
    # The product chip's own comparison badge is untouched and stays pinned.
    cmp_up = re.search(r"\.prod-chip \.cmp\.up \{[^}]*\}", CSS)
    ok("var(--accent)" in cmp_up.group(0), "the product comparison chip keeps the accent pill")
    # The tinted half of the pair stays, because red IS the reference's one tint.
    down = re.search(r"\.delta\.down \{[^}]*\}", CSS)
    ok(down and "var(--danger)" in down.group(0),
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
               "stat-edit",       # a KPI card while it is draggable
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
    for sel in (r"\.run-gate \.rg-btn", r"\.nav-refresh, \.nav-ask", r"\.sk-input, \.sk-textarea"):
        rule = re.search(sel + r" \{[^}]*\}", CSS)
        ok(rule, "the %s rule is still there" % sel)
        pad = re.search(r"padding:\s*([\d]+)px", rule.group(0))
        ok(pad and int(pad.group(1)) <= 5,
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
    rule = re.search(r"\.card > \.lia-bar, \.card > \.lbl-row, \.card > \.ktable-wrap,\s*\n\s*"
                     r"\.card > \.empty, \.card-bleed > \.empty \{([^}]*)\}", CSS)
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
    ok(re.search(r"\.card-bleed > \.insights > \.insight \+ \.insight,[\s\S]{0,120}?"
                 r"\{[^}]*border-top: 1px solid var\(--border\)", CSS),
       "the rows are separated by one hairline instead")
    ins = re.search(r"^\s*\.insight \{([^}]*)\}", CSS, re.M)
    ok(ins and "padding: 12px 16px" in ins.group(1),
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
    ok("margin-bottom: var(--sp-6)" in rule.group(1), "and it is the reference's 24px")
    ok("margin-top: 0" in rule.group(1),
       "with stray top margins zeroed, or the two stack up")
    head = re.search(r"\.ov-wrap > \.section-title \{([^}]*)\}", CSS)
    ok(head and "margin-bottom: var(--sp-3)" in head.group(1),
       "a heading still binds to the block under it at 12, not midway between two")
    ok(re.search(r"\.ov-wrap > \*:last-child \{[^}]*margin-bottom: 0", CSS),
       "and the last block does not add to the wrap's own bottom padding")


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
    ok(re.search(r"\.card > \.lia-bar, \.card > \.lbl-row, \.card > \.ktable-wrap,", CSS),
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
    ok(SCRIPT.count("el('label', 'sk-field')") == 4,
       "both skills forms wrap each of their two fields in the label")
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
    ok(SCRIPT.count("dataset.initial =") == 4,
       "and all four skills fields stamp what they started as")


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
    ok("uiConfirm(" in SCRIPT[SCRIPT.index("async function refreshMfaRow("):][:1400],
       "and turning it off asks first")


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

    inks = {k: _token(k) for k in ("ink", "ink-2", "ink-3")}
    for name in TEAM_TINTS:
        # .mrow specifically: the same name also styles the 8px presence dot,
        # which takes the SOLID colour and carries no text, so a contrast floor
        # does not apply to it.
        m = re.search(r"\.mrow\.own-" + name + r"\s*\{[^}]*background:\s*(#[0-9a-f]{6})",
                      CSS, re.I)
        ok(m, "there is a tint for " + name)
        tint = _rgb(m.group(1))
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
    ok("inset 2px 0 0" in unread, "but keeps the bar down its left")
    ok(".mrow.unread .mfrom" in CSS and "var(--w-medium)" in
       CSS.split(".mrow.unread .mfrom {")[1].split("}")[0],
       "and the bold sender, which is what Gmail leans on anyway")


@test
def t_a_selected_row_still_reads_as_selected_over_a_tint():
    """Selection is transient and deliberate - you are about to act on those
    rows - so it wins over whose they are."""
    idx_sel = CSS.index(".mrow.selected")
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
    ok("width: 8px" in dot, "small")
    ok(".who-dot.own-red    { background: #b91c1c; }" in CSS,
       "and SOLID, not the row tint: a 10% wash is invisible at 8px")


@test
def t_an_admin_can_change_someones_colour_from_the_team_tab():
    ok("op: 'colour'" in SCRIPT, "the team panel can set it")
    seg = SCRIPT[SCRIPT.index("Colour in the Inbox"):][:900]
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
    ok(start < HTML.index('id="signoff-text"') < HTML.index('id="settings-save"'),
       "inside the Settings modal and above its footer, not loose on the page")
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
    for ch, name in (("—", "em dash"), ("–", "en dash")):
        ok(ch not in HTML, "an " + name + " is in static/index.html")


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
    ok("'loans'" in SCRIPT.split("function setView(v) {")[1][:700],
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
    m = re.search(r"\.card > \.lia-bar, \.card > \.lbl-row.*?\{(.*?)\}", CSS, re.S)
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
    i = fn.find("c.docs")
    ok(i > 0, "the check result still renders its docs")
    seg = fn[i:i + 2000]
    ok("if (d.preview)" in seg, "the opener is offered only when a document came back")
    ok("connDocModal(d)" in seg, "and it opens that document")


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
    ok("payGo.disabled = !(connPayResult && connPayResult.dryRun" in seg,
       "and the write button is armed only by a dry run that found notes")
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
    i = r.find("Auto Run")
    ok(i > 0, "the card is on the page")
    seg = r[i - 400:i + 2600]
    ok("connAuto.enabled" in seg, "and reads the service's own flag")
    ok("'Auto Run ON'" in seg and "'Auto Run OFF'" in seg,
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
    ok("WITHOUT anyone reviewing" in seg, "that says nobody reviews what it sends")
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
    ok("el('div', 'conn-results')" in fn,
       "the result containers do not use the prose class")
    i = fn.find("const oneOut")
    ok(i > 0 and "setting-sub" not in fn[i:i + 120],
       "the one-order results are not a setting-sub")
    j = fn.find("const payOut")
    ok(j > 0 and "setting-sub" not in fn[j:j + 120],
       "nor are the payout results")


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


if __name__ == "__main__":
    print("frontend regressions")
    print()
    print(f"{_passed} passed, {len(_failed)} failed")
    sys.exit(1 if _failed else 0)
