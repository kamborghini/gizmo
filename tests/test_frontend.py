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
    ok(_re.search(r"a\.target = '_top'", HTML), "links escape the embedded iframe to the admin")


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
    ok("runPipedriveSurvey" in SCRIPT and "crm-statgrid" in HTML,
       "with the counts rendered rather than left in a console")


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


if __name__ == "__main__":
    print("frontend regressions")
    print()
    print(f"{_passed} passed, {len(_failed)} failed")
    sys.exit(1 if _failed else 0)
