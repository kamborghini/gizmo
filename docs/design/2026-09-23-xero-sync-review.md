# Xero sync page review, 23 September 2026

Cameron sent a screenshot of the Xero sync page's "Review and send" card and asked "does this look right to you?". It did not: a tag check's 62 orders were listed inside the tag tile, whose grid column grew to fit them and ran over the next tile and out of the card, and the page repeated the connector's engineer wording ("created" on a check that writes nothing, "(dry run - not pushed)", "run aborted: runaway guard: 21 documents exceeds MAX_DOCS_PER_RUN=1").

## How it was checked

- The page was rebuilt (results under the tiles as tables, the connector's words translated), then two independent reviewers took it: one drove every state of the page at 1728, 1440, 1280, 1024 and 390 wide against a connector mock built from the connector's own source, the other read the diff against the connector's real strings and shapes. They returned 53 findings, several of them functional faults older than this change.
- Everything was worked on; a third reviewer re-checked all 53 and found 43 fixed, 9 partly, 1 left on purpose, and 6 new faults. Those were then closed and re-measured with the reviewer's own probes.

## Faults beyond looks, now fixed

- The document window threw on every document it opened (a local `const money = money2` shadowed the app's money rule), so no document could be read.
- Send armed after a check that did not find the order, failed, or found nothing to write; a tag Send armed for a tag with no orders; Send to Xero armed after a review that stopped itself.
- The payout write stayed armed when the checked date was retyped, and then wrote for the new, unchecked date.
- Sending one order threw the reply away and toasted "Sent" over a failed or quarantined write.
- An order that stopped part way lost its error; "Left alone" claimed every such document was paid, though some need a Xero contact first.
- After a review the health box kept describing the old run, and the quarantine list was re-read on every repaint.

## Closed later the same day

- The unlinked page gives an admin numbered steps, each setting as code to copy, and a member one sentence; the header makes no promise while Auto Run's state is unknown.
- The review table uses the document tables' words (Already in Xero, Needs a Xero contact, Nothing to send, Will void, Edited after payment, left as it is) in place of "Skipped", and the "Blocked" tile is gone: the connector's ledger has no such count, so it only ever appeared in the test rig.
- Escape still does not close a window: windows close only by their X (a standing decision).

## The findings

### Code review

| ID | Severity | Finding | Outcome |
|---|---|---|---|
| F1 | high | connDocTable / cxTally (tag results): An order's own error is dropped when that order also has documents. | Fixed. |
| F2 | medium | cxTallySentence / CX_DOC_WORDS.blocked: Every 'blocked' document is summed as '... | Fixed after the check: an invoice's own "test order" message now counts as nothing to send. |
| F3 | medium | paintTag / tagChk.onclick / connStartWatch: While a tag check runs, the new result heading reads 'Orders tagged ""' and the tag box is emptied. | Fixed. |
| F4 | medium | Payout notes: review-before-write (pre-existing, not in the diff): The payout write is not disarmed by retyping the date, and it writes for the date in the box rather than the date that was checked. | Fixed. |
| F5 | medium | One order: review-before-send (pre-existing): Send this order is armed by a check that failed. | Fixed. |
| F6 | medium | One order: send result (pre-existing): The send's reply is thrown away and 'Sent #X to Xero.' is toasted whatever it says. | Fixed. |
| F7 | low | Health box: When there are no runs, the health box reads 'No runs yet..' with two full stops. | Fixed. |
| F8 | low | cxProblem first-letter lower-casing (and a test that locks it in): cxProblem lower-cases the first character of the connector's text after 'It stopped before starting: ', 'The run failed: ' and 'It stopped before writing anything: '. | Fixed. |
| F9 | low | cxPlain dash rule: `.replace(/\s*[‒-―]\s*/g, ', ')` rewrites every en or em dash, including the connector's own number range and dashes inside quoted product names. | Fixed after the check: a range inside a quoted name is left as it is. |
| F10 | low | cxProblem coverage: The phrase Cameron objected to still reaches two surfaces, and environment-variable names outside the five still pass through. | Fixed after the check: ".env" and "ValidationException" no longer reach the page. |
| F11 | low | CSS cascade: `.cx-docs td { vertical-align: top; }` never applies. | Fixed. |
| F12 | low | Accessibility and layout of the new tables: The payout table's fourth column holds the status chip (Written, Failed, To write) and the failure message, but its <th> is empty, so screen readers announce the column with no name. | Fixed. |
| F13 | low | Tag filter tabs and pager: The counts mix units again. | Fixed. |
| F14 | low | cxWhy money: The paid amount's currency comes from d.preview.currency and falls back to GBP. | Fixed. |
| F15 | low | Latest review card: The appended sentence runs on with no full stop, because cxProblem's fallback and preflight outputs do not end in punctuation. | Fixed. |
| F16 | low | cxPlain setting-value regex (latent): The value capture `(=(\S+?))?(?=[\s.,;:)]\|$)` is lazy and stops at the first '.', ':' or ','. | Fixed. |
| F17 | low | New tests: The three new tests fail on the old code (the helpers, the grid rule and the health date are all absent), and the node test skips safely without node, printing '(node unavailable, skipped)' and returning. | Fixed after the check: the remaining fixes are pinned, and the near-tautological test was rewritten. |
| F18 | low | Dead code left by the change: The styles for the removed per-document row are now unused. | Fixed. |
| F19 | low | Connection card facts (pre-existing): The 'When a total disagrees' fact never shows its threshold. | Fixed. |

### Every state, five widths

| ID | Severity | Finding | Outcome |
|---|---|---|---|
| F1 | high | Document window (Open): The document window never shows the document. | Fixed. |
| F2 | high | Arming of the three Send buttons: The primary Send buttons arm when there is nothing safe to send. | Fixed. |
| F3 | high | One order: send: The page throws away the send's reply. | Fixed. |
| F4 | high | Result sentences (cxTallySentence): The summary says every 'Left alone' document is 'left alone because Xero has them paid or closed'. | Fixed. |
| F5 | high | Connection card health box after Run review: When a review finishes, the watcher reloads the runs and the status but not the health or Auto Run data. | Fixed. |
| F6 | high | Connection card: stale red box (the item Cameron flagged): The 5 Sep box now has a date, but it is still the loudest thing on the page, and its advice contradicts the page. | Fixed. |
| F7 | high | Document tables: vertical alignment: The doc tables were meant to top-align, but the rule loses, so every cell is vertically centred. | Fixed. |
| F8 | medium | Column wrapping: tag table and Quarantine: In the tag table, 'Credit note' wraps to two lines ('Credit / note'), while the same document stays on one line in the one-order table. | Fixed. |
| F9 | medium | Payout notes table: The status column has no header and sits last. | Fixed. |
| F10 | medium | Tile row layout: The three tiles do not share one shape. | Fixed. |
| F11 | medium | Busy state during a tag check or send: While a tag check runs, three things go wrong. | Fixed. |
| F12 | medium | Connection chips after a failed tag job: A tag check that fails sets the connector's lastError, so the Connection card shows 'Last run failed' under a box that is about the 5 Sep review, while the runs table lists no new run. | Fixed. |
| F13 | medium | Tag table counts: The tag table counts in three units. | Fixed. |
| F14 | medium | Tag send confirmation: The confirmation dialog says 'The rest are already in Xero or left alone.' when 2 documents would be held back or fail and 2 orders could not be checked. | Fixed after the check: the confirm names the orders that could not be checked, without the parenthesis. |
| F15 | medium | Translating connector words (health, warnings, quarantine): Connector wording leaks through, and the translation layer introduces errors of its own. | Fixed after the check: ValidationException, the Shopify connectivity wording and "Credit note for #n" are said in words. |
| F16 | medium | Latest review for an aborted review: The card opens with a success-green line, 'Reviewed 38 orders · nothing was written. | Fixed. |
| F17 | medium | Run review is far from its result: 'Run review' and 'Send to Xero' sit in the Review and send card head. | Fixed. |
| F18 | medium | Health box with no runs: The box says 'No runs yet..' (two full stops) in a green success box, although nothing has run. | Fixed. |
| F19 | medium | Keyboard and focus: Pressing a filter tab or a pager button rebuilds the page and drops focus to BODY. | Fixed after the check: focus returns after the page is laid out, without scrolling the window. |
| F20 | medium | Payout date box: The date box is free text whose grey ISO placeholder '2026-08-01' reads like a value. | Fixed. |
| F21 | medium | Tag result after a send: Every row after a send has an empty 'Lines total' column and an empty action column, and shows no Xero number. | Fixed. |
| F22 | medium | Unreadable orders in the tag table: For orders that were not found or not read, the 'Not in Shopify' and 'Not checked' chips sit under the Document heading (x=121) while every other chip sits under Outcome (x=212). | Fixed. |
| F23 | medium | Phone tables and tabs: On a phone the doc tables scroll sideways (460px inside 311px) but squeeze Outcome to 117px, so reasons wrap to 4 lines, while the amount and Open start off-screen. | Fixed. |
| F24 | low | Chip colours: 'Would create' is green and 'Would update' is amber on a check where nothing has happened yet. | Fixed. |
| F25 | low | Vocabulary: The page uses different words for the same outcome. | Fixed later the same day: one set of outcome words across the tiles, tables and review. |
| F26 | low | Left alone reason amounts: The reason gives the paid amount including tax ('Paid in Xero (£242.20)') beside a 'Lines total' before tax of £201.83. | Fixed. |
| F27 | low | One order sentence: The summaries are repetitive and mix words with numerals: '2 documents: 2 would be created.' and 'One document. | Fixed. |
| F28 | low | Auto Run line and hero promise: The connector's own line, with its own separator dots, is pasted into the page's dot list, for example '… · 148 checks so far · 12 orders checked, 4 documents created · 2 needing attention'. | Fixed. |
| F29 | low | Pager thresholds: A pager appears when there is nothing to page: '1 to 12 of 12 notes · Rows per page 20 · Page 1 of 1', with all four step buttons disabled. | Fixed. |
| F30 | low | Non-admin view: The hints tell a member to 'then send that order', and the card says 'Send does exactly what the review showed', but a member has no Send buttons. | Fixed after the check: the card and Auto Run line no longer tell a member to send. |
| F31 | low | Unlinked and unreachable states: The unlinked state shows environment variable names in UI copy ('Set CONNECTOR_URL (and CONNECTOR_TOKEN) in Railway'). | Left on purpose. |
| F32 | low | Auto Run toggle wrap: 'Turn Auto Run on' drops onto its own line, right-aligned under a one-line sentence, because the text's max-content plus the button exceeds the row by a few pixels. | Fixed. |
| F33 | low | Quarantine refetch: Every re-render refetches the quarantine list (each tab, page or check), so the quarantine card redraws empty and then refills. | Fixed. |
| F34 | low | Copy: The payout hint 'This notes on each Xero invoice which payout paid it' is ungrammatical. | Fixed. |

### New faults the check found, all fixed

- (medium) The visual F19 focus-restore runs synchronously at the end of renderConnector, before the widget grid has laid out the rebuilt cards.
- (low) 'Sent:' headings claim a send that did not happen, or has not finished.
- (low) Grammar in the tag send summary.
- (low) A one-order result has no row dividers at all.
- (low) Stale CSS comments describe layouts that no longer exist.
- (low) On the phone, the scrolling tab strip clips the focus ring of its first tab.
