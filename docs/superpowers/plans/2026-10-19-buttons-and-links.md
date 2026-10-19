# Buttons, icon buttons and links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every button in the page's script is built by one of three parts, `button()`, `iconButton()` and `link()`; the five icon-button recipes become one in three sizes, the four link styles become one in three sizes, and the sign-in card's links become the house link.

**Architecture:** A new section `static/src/js/part-button.js` (after `js/part-dialog.js` in the manifest) holds the three parts. `button()` and `link()` build today's classes, so ~360 call sites move with no visible change; `iconButton()` builds `icon-btn` plus two new size classes, and the retired recipes' stylesheet rules move onto them. A page-suite guard forbids hand-built buttons of these kinds; a codemod converts the ordinary buttons and checks every conversion keeps its classes.

**Tech Stack:** Plain JavaScript in the page's one scope, CSS sections under `static/src/css`, the page suite (`tests/test_frontend.py` with `MINIDOM`), the browser suite, Pillow (in `.venv`) for the screenshot comparison.

**Spec:** `docs/superpowers/specs/2026-10-19-buttons-and-links-design.md`

## Global Constraints

- Visible change only where the spec says: the toast and alert crosses, the chip cross, the 24 row actions (Memory, chat), and the three sign-in card links (`Start again`, `Sign in as someone else`, `Forgot password?`) becoming caption links. Everything else renders as before.
- Skills' row actions stay 32 (regular) beside "Use in chat".
- Out of scope: `.convo .del`, `chart-expand`, `stat-open-btn`, `pchat-send`, the CRM table names (`dt-link`), the buttons written into `static/src/shell.html`, and renaming `btn-sm` or `seclink`.
- The browser record may not go up anywhere; if it goes down, it is lowered in the pull request and listed.
- Frozen areas untouched (printed labels and print CSS, the Production Manager queue's rows, columns, statuses and actions, the Quote Engine). Buttons inside the queue move to `button()` with identical classes, which changes nothing about the queue.
- One release note dated the merge day; British English, no dashes in UI copy; the repo is public.
- No agents (the initiative's five are spent); the final review is a self-review.
- Branch `refactor/buttons-links` is stacked on `refactor/window-part`; its pull request waits for PR #32 and the window part.

## Review Focus

1. **Script still looking for a retired class** (`.querySelector('.mem-btn.del')`, `.toast-x`): the lookup returns nothing and a row action or a toast close silently stops working. Pinned by Task 2's `t_the_retired_button_recipes_are_gone` (no reference in script or stylesheet) and the browser suite's zero-script-errors check.
2. **A small or tag icon button on a phone** caught by the 40-wide phone rule for icon buttons, so a toast's cross or a chip's cross balloons. Pinned by Task 2's `t_small_icon_buttons_keep_their_size_on_a_phone`.
3. **An icon button with no name**: a call site passing an empty or missing label. Pinned by Task 1's harness test (empty label throws in the part) and Task 2's guard that every `iconButton(` call passes a label.
4. **Skills' row actions shrinking** from 32 to 24 because they used to be `mem-btn`. Pinned by Task 2's `t_skills_row_actions_stay_regular` and the screenshot comparison in Task 5.
5. **A converted ordinary button losing a class or its text** (a text argument with commas, a class string with extra hooks). Pinned by the codemod's own check in Task 4 (every conversion rebuilt and compared token by token) and the screenshot comparison in Task 5.

---

### Task 1: The three parts

**Files:**
- Create: `static/src/js/part-button.js`, CSS additions in `static/src/css/sidebar.css` (where `.icon-btn` lives) and `static/src/css/windows-and-phone.css` (the phone rules)
- Modify: `static/src/manifest.json` (after `"js/part-dialog.js",`), `tests/test_frontend.py`

**Interfaces:**
- Produces:
  - `button(text?: string|null, opts?: { kind?: 'primary'|'danger'|'ghost', small?: boolean, square?: boolean, cls?: string, icon?: string, title?: string }) -> HTMLButtonElement`. Class string, in this order: `btn`, ` btn-sm` if small, ` btn-primary` / ` btn-danger` / ` ghost` for kind, ` btn-icon` if square, then `cls`. With `icon`, the button holds `ico(icon)` then the text node; with `title`, its title.
  - `iconButton(icon: string, label: string, opts?: { size?: 'regular'|'small'|'tag', tone?: 'danger'|'ok', cls?: string }) -> HTMLButtonElement`. Class string: `icon-btn`, ` icon-btn-sm` / ` icon-btn-tag` for size, ` del` / ` ok` for tone, then `cls`. `innerHTML = icon`; `title` and `aria-label` = label. Throws `Error('iconButton needs a label')` when label is empty.
  - `link(text: string, opts?: { size?: 'caption'|'inline'|'go', cls?: string }) -> HTMLButtonElement`. Classes: `linkish` (caption, the default), `seclink` (inline), `link` (go, followed by `ico(I.chev)`), then `cls`.
  - In `tests/test_frontend.py`: `button_part() -> str` (the section's source from `SCRIPT`, between `/* ---------- the button parts ----------` and `/* ---------- the button parts end ---------- */`).

- [ ] **Step 1: Write the failing tests** (after the window-part tests; they need `MINIDOM`, `dialog_harness`-style stand-ins for `I` and `ico`)

`t_the_button_parts_build_todays_classes`: in node with `MINIDOM` plus `globalThis.I = { chev: '<svg/>', x: '<svg/>', trash: '<svg/>' }` and `globalThis.ico = (s) => { const n = el('span', 'ic'); n.innerHTML = s; return n; }` and `button_part()`, assert:
- `button('Save').className == 'btn'`, its text `'Save'`
- `button('Save', { kind: 'primary', small: true }).className == 'btn btn-sm btn-primary'`
- `button(null, { kind: 'danger', cls: 'disp-book' }).className == 'btn btn-danger disp-book'` and its text `''`
- `button(null, { small: true, square: true }).className == 'btn btn-sm btn-icon'`
- `button('Copy', { icon: I.x }).children[0].className == 'ic'` and its text `'Copy'`
- `iconButton(I.x, 'Close').className == 'icon-btn'`, `getAttribute('aria-label') == 'Close'`, `title == 'Close'`
- `iconButton(I.trash, 'Delete note', { size: 'small', tone: 'danger' }).className == 'icon-btn icon-btn-sm del'`
- `iconButton(I.x, 'Remove', { size: 'tag' }).className == 'icon-btn icon-btn-tag'`
- `iconButton(I.x, '')` throws, message contains `needs a label`
- `link('Undo').className == 'linkish'`; `link('Education', { size: 'inline' }).className == 'seclink'`; `link('Show all', { size: 'go' }).className == 'link'` with a last child of class `ic`; `link('Back', { cls: 'auth-back' }).className == 'linkish auth-back'`

`t_icon_buttons_have_three_sizes_from_the_tokens` (stylesheet, no node): `.icon-btn.icon-btn-sm` sets `min-width: var(--control-h-sm)`, `min-height: var(--control-h-sm)`, `padding: 0`, and its svg `var(--icon-sm)`; `.icon-btn.icon-btn-tag` sets `var(--box-sm)` both ways, `padding: 0`, `border-radius: var(--radius-tag)`, svg `var(--icon-xs)`; `@media (hover: hover)` rules `.icon-btn.del:hover` (`var(--error)` on `var(--error-bg)`) and `.icon-btn.ok:hover` (`var(--success)` on `var(--success-bg)`).

`t_small_icon_buttons_keep_their_size_on_a_phone` (stylesheet): inside `@media (max-width: 640px)`, the 40-wide rule reads `.icon-btn:not(.icon-btn-sm, .icon-btn-tag)`, and the invisible 40 target rule's `::after` selector includes `.icon-btn-sm` and `.icon-btn-tag` (with `position: relative` on both).

Run: `ONLY=t_the_button_parts python3 tests/test_frontend.py 2>&1 | tail -2; ONLY=t_icon_buttons_have python3 tests/test_frontend.py 2>&1 | tail -1; ONLY=t_small_icon python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: the first errors in `button_part()` (substring not found); the other two FAIL.

- [ ] **Step 2: Write `static/src/js/part-button.js`** with the three functions above between the two marker comments, a header comment saying what the parts own and pointing at `docs/DESIGN.md`, every line ending in a newline; add it to the manifest after `"js/part-dialog.js",`.

- [ ] **Step 3: Add the CSS** the two stylesheet tests name: the size and tone rules after the `.icon-btn` rules in `sidebar.css`; in `windows-and-phone.css`, change `:is(.icon-btn, .btn-sm.btn-icon, .topbar .icon-btn, .topbar-search) { min-width: var(--control-h-lg); }` to use `.icon-btn:not(.icon-btn-sm, .icon-btn-tag)` in place of `.icon-btn`, and add `.icon-btn-sm, .icon-btn-tag` to the `position: relative` list and to the centred `::after` 40 target list (the one that holds `.toast-x, .alert-x, .sk-chip-x` today; leave those three in place until Task 2 retires them).

- [ ] **Step 4: Run the three tests and the whole page suite**

Run: the commands from Step 1, then `python3 tests/test_frontend.py > /tmp/bl-front.log 2>&1; tail -1 /tmp/bl-front.log`
Expected: three PASS; the suite `0 failed` (nothing uses the parts yet).

- [ ] **Step 5: Commit** (`static/src/js/part-button.js`, `static/src/manifest.json`, the two CSS files, `tests/test_frontend.py`): "The button parts: button(), iconButton() in three sizes, link()".

---

### Task 2: Icon buttons onto the part; five recipes become one

**Files:**
- Modify: every script section that builds `icon-btn`, `mem-btn`, `alert-x`, `toast-x` or `sk-chip-x` (36 sites: `icon-btn` 23 across `crm.js`, `dispatch.js`, `files.js`, `production-manager.js` and others, the window part's X in `part-dialog.js`; `mem-btn` in `memory.js`, `skills.js`, `chat.js`; `alert-x` in `alerts.js`, `production-manager.js`; `toast-x` in `memory.js`, `production-manager.js`; `sk-chip-x` in `chat.js`), the CSS sections that style the retired classes (`memory-and-products.css`, `tables-and-production-manager.css`, `team-toasts-and-motion.css`, `composer.css`, `windows-and-phone.css`), `tests/test_frontend.py`

**Interfaces:**
- Consumes: `iconButton(icon, label, opts)` (Task 1).

- [ ] **Step 1: Write the failing guards**

`t_every_icon_button_is_built_by_the_part`: no script section except `js/part-button.js` contains `el('button', 'icon-btn`, `el('button', 'mem-btn`, `el('button', 'alert-x'`, `el('button', 'toast-x'` or `el('button', 'sk-chip-x'` (name each offending line, as `t_every_window_is_built_and_closed_by_the_part` does); and every `iconButton(` call in the script has a second argument (regex over the joined script: no `iconButton(` followed by a single argument then `)`).

`t_the_retired_button_recipes_are_gone`: `mem-btn`, `alert-x`, `toast-x` and `sk-chip-x` appear nowhere in `SCRIPT` or `CSS` (as a class name: `\b(mem-btn|alert-x|toast-x|sk-chip-x)\b`).

`t_skills_row_actions_stay_regular`: in `fn_src` of the function in `skills.js` that builds the `.sk-acts` row (the one holding today's `skills.js:667` and `:670`), every `iconButton(` call has no `size:` option.

Run each with `ONLY=`; Expected: all three FAIL, naming the sites.

- [ ] **Step 2: Convert each site.** `el('button', '<recipe>[ extra]')` plus its `innerHTML = I.<icon>`, `title` and `aria-label` lines become one `iconButton(I.<icon>, '<label>', { ... })`. The label is the site's existing `title` or `aria-label`; where it has neither, name what it does in two or three words (`Close`, `Delete note`, `Copy reply`). Sizes: `icon-btn` → regular; `mem-btn` in `memory.js` and `chat.js` → `small`; `mem-btn` in `skills.js` (`.sk-acts`) → regular; `alert-x`, `toast-x` → `small`; `sk-chip-x` → `tag`. Tones: `mem-btn del` → `tone: 'danger'`; `mem-btn ok` (if present) → `tone: 'ok'`; other extra classes (`files-more`, `resp-copy`) → `cls`. The window part's X becomes `iconButton(I.x, 'Close')`.

- [ ] **Step 3: Move the retired rules.** In the CSS sections, delete the base rules of `.mem-btn`, `.alert-x`, `.toast-x`, `.sk-chip-x` (their look is now `.icon-btn` in its size); rewrite each contextual rule onto the new classes (`.mem-btn[hidden]` → `.icon-btn[hidden]`; layout rules such as a toast's or an alert's placement of its cross → the same selector with `.icon-btn`); drop the retired names from the phone lists (`:is(.sidebar .icon-btn, .mem-btn, .crm-ticon)`, the `::after` lists, the `position: relative` list); delete `.mem-btn.ok:hover` and `.mem-btn.del:hover` (Task 1's tone rules replace them) and `.sk-acts .mem-btn` (regular is 32). In the script, rewrite every selector that names a retired class (`querySelector('.mem-btn…')` and similar, 19 references) onto `.icon-btn` within the same container, checking each still finds only the buttons it meant.

- [ ] **Step 4: Run the guards, the page suite and the browser suite**

Run: the three `ONLY=` commands; `python3 tests/test_frontend.py > /tmp/bl-front.log 2>&1; tail -1 /tmp/bl-front.log; grep FAIL /tmp/bl-front.log`; then `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN npx playwright test -c tests/browser/playwright.config.js pages.spec.js keyboard.spec.js --reporter=line 2>&1 | grep -vE "^\[WebServer\]" | tail -3`
Expected: three PASS; the page suite `0 failed` after re-pointing any test that pinned a retired class to the same promise kept by the part (ledger each); the browser suite all passed (a run that fails only on "lower the record" means accessibility findings went down: note them for Task 5).

- [ ] **Step 5: Commit**: "Icon buttons built by the part: one recipe in three sizes; mem-btn, alert-x, toast-x and sk-chip-x retired".

---

### Task 3: Links onto the part; the sign-in card's links become the house link

**Files:**
- Modify: the 21 sites in the inventory (`linkish` 11: `dispatch.js`, `inbox.js` ×3, `design-page.js`, `inbox-filters-and-sending.js` ×5, `loans.js`; `seclink` 6: `alerts.js` ×3, `customers.js`, `size-list.js` ×2; `link` 2: `forecast.js`, `icons-and-formats.js`; `auth-link` 3: `team-and-sign-in.js`), `static/src/css` (the `.auth-link` rules), `tests/test_frontend.py`

**Interfaces:**
- Consumes: `link(text, opts)` (Task 1).

- [ ] **Step 1: Write the failing guards**

`t_every_text_link_is_built_by_the_part`: no section except `js/part-button.js` contains `el('button', 'linkish`, `el('button', 'seclink`, `el('button', 'a-metric seclink`, `el('button', 'link'` or `el('button', 'auth-link`.

`t_the_sign_in_card_uses_the_house_link`: `auth-link` appears nowhere in `SCRIPT` or `CSS`; in `team-and-sign-in.js`'s source (via `SCRIPT`), `link('Start again', { cls: 'auth-back' })`, `link('Sign in as someone else', { cls: 'auth-back' })` and `link('Forgot password?')` each appear once.

Run each with `ONLY=`; Expected: both FAIL.

- [ ] **Step 2: Convert the 21 sites.** `linkish` → `link(text)` (extra classes such as `guide-toc-link` → `cls`); `seclink` → `link(text, { size: 'inline' })` (`a-metric` → `cls`; a site that sets `textContent` after building keeps doing so on the returned element); `link` with an appended chevron → `link(text, { size: 'go' })`, dropping the site's own `append(ico(I.chev))`; `auth-link` → `link(text)` with `auth-back` kept as `cls`. Delete the `.auth-link` rules; keep any `.auth-back` layout rule (it now sits on a `linkish`).

- [ ] **Step 3: Run the guards, the page suite and the browser suite** (the commands of Task 2 Step 4). Expected: both PASS, `0 failed`, browser all passed.

- [ ] **Step 4: Commit**: "Text links built by the part; the sign-in card's links are the house link".

---

### Task 4: Ordinary buttons onto `button()`

**Files:**
- Modify: every script section that builds `el('button', 'btn…')` (about 330 sites), `tests/test_frontend.py`
- Create (git-ignored, in the plan's workspace): `codemod-buttons.py`

**Interfaces:**
- Consumes: `button(text, opts)` (Task 1).

- [ ] **Step 1: Write the failing guard** `t_every_ordinary_button_is_built_by_the_part`: no section except `js/part-button.js` contains `el('button', 'btn` (name each line). Run with `ONLY=`; Expected: FAIL, about 330 lines.

- [ ] **Step 2: Write and run the codemod.** For each `el('button', '<cls>'` whose class string's first token is `btn`, find the call's closing parenthesis by counting balanced brackets and skipping string literals, and split its arguments at top-level commas. Map the tokens: `btn` (required, dropped), `btn-sm` → `small: true`, `btn-primary` → `kind: 'primary'`, `btn-danger` → `kind: 'danger'`, `ghost` → `kind: 'ghost'`, `btn-icon` → `square: true`, any other token → `cls` (joined by spaces, in order). Emit `button(<text or null>, { … })`, `button(<text>)` with no options, or `button()` with neither. After each rewrite, rebuild the class string the part would produce and assert its token set equals the original's; stop on the first mismatch and print the site. Report the count converted per file.

Run: `python3 .superpowers/sdd/2026-10-19-buttons-and-links/codemod-buttons.py`
Expected: a per-file count summing to the guard's count, and no mismatch.

- [ ] **Step 3: Run the guard, the page suite, the dispatch suite and the browser suite.** Re-point any page-suite test that pinned `el('button', 'btn…'` text to the `button(` form of the same site (ledger each). Expected: guard PASS; page suite `0 failed`; dispatch `1012 passed, 0 failed`; browser all passed.

- [ ] **Step 4: Commit**: "Ordinary buttons built by button(): about 330 sites, their classes unchanged".

---

### Task 5: Proof, `DESIGN.md`, What's new and the PR

**Files:**
- Modify: `docs/DESIGN.md` (Parts: Buttons, Icon buttons, Links), `data/changelog.json`, `tests/test_frontend.py` (`t_the_design_rules_live_in_one_document` gains the three new guard names)

- [ ] **Step 1: The screenshot comparison.** With `SP` the session scratchpad and `R` this checkout:
`git worktree add $SP/bl-base refactor/window-part`, `ln -s $R/node_modules $SP/bl-base/node_modules`, then in `$SP/bl-base`: `PY=$R/.venv/bin/python BROWSER_RUN=$SP/bl-base-run npx playwright test -c tests/browser/playwright.config.js pages.spec.js`; and in `$R`: `BROWSER_RUN=$SP/bl-head-run npx playwright test -c tests/browser/playwright.config.js pages.spec.js` (both with `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN`). Compare each `shots/*.png` pair with Pillow (`ImageChops.difference(a, b).getbbox()` is `None` when they match) and list the states that differ. Remove the worktree and both run folders afterwards.
Expected: only states that show a changed control differ (Memory and the chat conversation for the row actions; any state showing an alert, a toast or a chip cross); Skills unchanged. Any other differing state is a finding: find the cause and fix it before going on.

- [ ] **Step 2: `docs/DESIGN.md`.** Under Parts, add Buttons (`button()`, kinds, `small` kept as a legacy name until the stylesheet is layered), Icon buttons (the three sizes table from the spec, tones, always named, the phone target) and Links (one link, three sizes, the legacy class each builds), each with its guard names. Add the three guards to `t_the_design_rules_live_in_one_document`'s list: `t_every_icon_button_is_built_by_the_part`, `t_every_text_link_is_built_by_the_part`, `t_every_ordinary_button_is_built_by_the_part`.

- [ ] **Step 3: The release note**, dated the merge day: title "Buttons that match", one `changed` item: "The small buttons that close and act on things, the crosses on messages and chips and the actions in Memory and chat, now look and behave the same everywhere, and every one has a name a screen reader reads out. The sign-in card's links are the house link."

- [ ] **Step 4: `make check`.** Expected: exit 0; the browser record unchanged or lowered (if lowered: `UPDATE_RECORD=1 make test-browser` and list each change).

- [ ] **Step 5: Self-review and push.** Review the branch against `requesting-code-review/code-reviewer.md` and this plan's Review Focus; ledger `Final review: self-review (no agent left in the budget)`. Push the branch. The pull request waits for PR #32 and the window part's: when they have merged, rebase onto `main`, rerun `make check`, open it with the screenshot list, the record and the rulings, and switch on Auto-fix and auto-merge.
