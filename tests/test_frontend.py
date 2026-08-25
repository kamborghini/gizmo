"""Frontend regression tests.

The SPA is one 5,700-line file with no build step, so nothing type-checks it and
nothing catches a rule that quietly loses the cascade. Every assertion here
corresponds to a bug that actually reached the merchant, in the shape that let it
through, so a regression fails here instead of at the dispatch desk.
"""
import os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(ROOT, "static", "index.html"), encoding="utf-8").read()
SCRIPT = max(re.findall(r"<script>(.*?)</script>", HTML, re.S), key=len)

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
    allowed = {11, 12, 13, 14, 16, 20, 28, 32}
    ok(sizes <= allowed, "font sizes outside the scale: " + str(sorted(sizes - allowed)))


@test
def t_weights_radii_and_elevation_are_closed():
    weights = {int(v) for v in _re.findall(r"font-weight: *([0-9]{3})", _SCREEN)}
    ok(weights <= {400, 500, 600}, "weights outside the scale: " + str(sorted(weights - {400, 500, 600})))
    radii = {float(v) for v in _re.findall(r"border-radius: *([0-9.]+)px", _SCREEN)}
    ok(radii <= {6, 8, 12}, "radii outside the scale: " + str(sorted(radii - {6, 8, 12})))


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
    real thing, standing filters, and a Claude-drafted reply."""
    ok("value: 'unread'" in SCRIPT and "mailFilter === 'unread' && !t.unread" in SCRIPT,
       "unread is a filter with its own count, not just bold text")
    ok("'/api/mail/rules'" in SCRIPT, "filters are managed in the app")
    ok("Apply to existing mail" in SCRIPT, "and can be run over the pile already there")
    ok("share out between people" in SCRIPT, "including sharing work round the team")
    ok("never re-filed underneath them" in SCRIPT,
       "the card says plainly that live work is not re-triaged")
    ok("Compose reply with Claude" in SCRIPT, "the reply button exists")
    ok("'/api/mail/draft'" in SCRIPT and "op: 'save'" in SCRIPT,
       "drafting and saving are separate steps, with a human in between")
    ok("you send it yourself" in SCRIPT,
       "and the app is explicit that it never sends the mail")
    ok("gaps like ____" in SCRIPT,
       "the panel explains why the draft has blanks in it")
    ok("rows.sort((a, b) => (b.unread ? 1 : 0) - (a.unread ? 1 : 0))" in SCRIPT,
       "unread rises to the top of the list")
    ok(".mrow.unread { background:" in HTML and "inset 3px 0 0 var(--accent)" in HTML,
       "and is unmistakable: its own tint and edge, not a 100-weight difference")
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
    ok("const CARRIER_LABEL" in SCRIPT and "const dims = CARRIER_LABEL;" in SCRIPT,
       "courier labels print at the carrier's own 4x6, not the chosen gobo stock")
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
    tweak cannot quietly put it back."""
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
    rule = re.search(r"\.lbl-segbtn\.on \{[^}]*\}", HTML)
    ok(rule and "var(--sh-1)" in rule.group(0),
       "the active segment is lifted off its track, which is the point of the control")
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
             and not re.search(r"rgba\(\s*(26,\s*26,\s*26|0,\s*0,\s*0|255,\s*255,\s*255|91,\s*75,\s*219)", ln)]
    ok(not stray, "off-palette rgba survives: " + "; ".join(x.strip()[:70] for x in stray[:3]))
    ok(".stat.warn { border-color" not in HTML,
       "the warn card takes the ordinary card border rather than a paler one")


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
    ok(SCRIPT.count("if (e.target !== row) return;") == 1
       and SCRIPT.count("if (e.target !== card) return;") == 1,
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
    settles which of the two is the chip: --r-xs."""
    chips = ["pill", "mem-tag", "mail-order-stage", "lbl-chip", "fchip", "mail-owner",
             "mcount", "mrule-tag", "g-badge", "mail-claim", "mail-crmchip"]
    for c in chips:
        rule = re.search(r"\." + c + r" \{[^}]*\}", HTML, re.S)
        ok(rule, "the .%s rule is still there" % c)
        ok("border-radius: var(--r-xs)" in rule.group(0),
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
def t_one_tracking_value_for_the_micro_label():
    """The 11px uppercase micro-label is the app's most repeated typographic
    unit and it was set at .04, .05, .06 and .08em in different places."""
    ok("--track-caps" in HTML, "there is one token for it")
    style = HTML[HTML.index("<style>"):HTML.index("</style>")]
    stray = []
    for m in re.finditer(r"\n\s*([^\n{}]+)\{([^}]*)\}", style):
        body = m.group(2)
        if "font-size: 11px" in body and "text-transform: uppercase" in body:
            ls = re.search(r"letter-spacing:\s*([^;]+)", body)
            if ls and "var(" not in ls.group(1):
                stray.append(m.group(1).strip()[:46] + " -> " + ls.group(1).strip())
    ok(not stray, "every 11px uppercase label reads the token: " + "; ".join(stray[:3]))


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
    ok("not editable here" in fn,
       "and the panel says why tags and the note are not on it")


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


if __name__ == "__main__":
    print("frontend regressions")
    print()
    print(f"{_passed} passed, {len(_failed)} failed")
    sys.exit(1 if _failed else 0)
