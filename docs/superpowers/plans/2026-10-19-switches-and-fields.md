# Switches, fields and names Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Settings switches become real, named switches and the switch fixers go; every captioned field is built by `field()` with the house label; every control on the measured screens and in the journeys' windows has a name, held by a zero-tolerance browser check.

**Architecture:** `setSwitch()` and `field()` join `static/src/js/part-button.js`'s neighbour section `static/src/js/part-field.js` (after `js/part-button.js` in the manifest); the Settings switches change in `static/src/shell.html`; a codemod converts the four caption families; a naming probe in `tests/browser/probes.js` feeds a new zero-tolerance check in `pages.spec.js` and the keyboard journeys.

**Tech Stack:** Plain JavaScript in the page's one scope, the page suite with `MINIDOM`, the browser suite, Pillow for the screenshot comparison.

**Spec:** `docs/superpowers/specs/2026-10-19-switches-and-fields-design.md`

## Global Constraints

- Visible change only in the captions of the dispatch, new-shipment, edit-order and CRM forms (12 grey to the house label: 14 medium, primary ink). The look of the field itself does not change; the Settings switches look as they do.
- Frozen areas untouched; the print functions byte for byte (`t_the_printed_sheets_do_not_change`).
- The browser record may not go up; the `label` findings go to zero and the record is lowered.
- A release note, dated the merge day, goes in with the first app change (the house rule fails otherwise).
- No agents; the final review is a self-review. Branch `refactor/switches-fields` is stacked on `refactor/buttons-links`; its pull request waits for the three before it.

## Review Focus

1. **A Settings switch for someone who is not an admin**: it shows the setting but must not change it (`aria-disabled`), and pressing it must not flip the look. Pinned by Task 1's `t_a_switch_says_its_state_and_a_locked_one_does_not_move`.
2. **A switch whose save fails**: Settings flips it back; the spoken state must flip back too. Pinned by the same test (`setSwitch` is the only way the code flips one).
3. **A field whose control is added after its caption** (most call sites build the label, then the control): the caption must still name it. Pinned by Task 2's harness test (control appended after `field()` returns).
4. **A field with a help line and an error message under it** (design-page's `field-msg`): the order caption, control, help, message must hold. Pinned by Task 2's harness test.
5. **A control added later by a screen nobody measured**: the browser check only sees what the suite opens. Pinned by Task 3's page-suite check that every input given a placeholder in the script also has an `aria-label` or sits in `field()`.

---

### Task 1: Switches

**Files:** `static/src/js/part-field.js` (create; manifest after `js/part-button.js`), `static/src/shell.html` (the five Settings switches), `static/src/js/settings.js`, `static/src/js/page-observers.js`, `data/changelog.json`, `tests/test_frontend.py`

**Interfaces:**
- Produces: `setSwitch(sw: HTMLElement, on: boolean) -> void` (toggles class `on`, sets `aria-checked`); `switchBtn` unchanged.

- [ ] **Step 1: Failing tests.**
`t_settings_switches_are_named_switches`: in `HTML`, each of `data-pref="track_inventory"`, `data-pref="concise"`, `data-pref="proactive"`, `data-pref="flag_anomalies"` and `id="sched-toggle"` sits on a `<button type="button" class="toggle" role="switch" aria-checked=` element with an `aria-labelledby` pointing at an element whose id exists in `HTML` and whose text is the setting's title.
`t_a_switch_says_its_state_and_a_locked_one_does_not_move` (node, `MINIDOM` + the part): `setSwitch(b, true)` gives class `on` and `aria-checked="true"`; `setSwitch(b, false)` the reverse; and `savePrefToggle` from `settings.js` (`fn_src`) on a switch with `aria-disabled="true"` leaves it as it was (stub `api`, `profile`, `connIsAdmin`).
`t_the_switch_fixers_stay_gone`: no `function syncToggles(`, no `syncToggles()` in `SCRIPT`, no `contains('toggle') && (e.key === 'Enter'`.
Run each with `ONLY=`; Expected: FAIL.

- [ ] **Step 2: Build it.** `setSwitch` in `part-field.js` (between `/* ---------- the field parts ----------` and `/* ---------- the field parts end ---------- */`); the five shell switches become `<button type="button" class="toggle" role="switch" aria-checked="false" aria-labelledby="<title id>" aria-describedby="<sub id>" …><span class="sw"></span></button>`, ids added to their `.setting-title` and `.setting-sub`; in `settings.js` every `classList.toggle('on', …)` on a switch becomes `setSwitch(…)`; in `page-observers.js` delete `syncToggles`, its call, its share of the batched pass (which keeps `syncTableHeads(); syncPanels();`) and the page-wide `.toggle` Enter/Space handler. Add the release note (title "Switches and fields", one `changed` item: "Field captions in the dispatch and CRM forms now match the rest of the app, and every switch, box and tick has a name a screen reader reads out.", dated today).

- [ ] **Step 3: Run** the three tests, the page suite (re-point any test that pinned `syncToggles`, ledgered), and `keyboard.spec.js` (Settings is one of its windows). Expected: PASS; `0 failed`; all journeys pass.

- [ ] **Step 4: Commit.**

---

### Task 2: `field()`

**Files:** `static/src/js/part-field.js`, the 46 caption sites (`pfield` 22, `disp-fld` 15, `disp-addr-f` 4, `sk-field` 5), `static/src/css/dispatch.css` (`disp-fld-lab`, `disp-addr-lab`), `tests/test_frontend.py`

**Interfaces:**
- Produces: `field(caption: string, control?: HTMLElement|null, opts?: { help?: string, cls?: string }) -> HTMLLabelElement` building `<label class="pfield[ cls]"><span>caption</span>[control][<p class="field-help">help</p>]</label>`.

- [ ] **Step 1: Failing tests.**
`t_a_field_is_its_caption_and_its_control` (node): `field('Postcode', inp)` is a `LABEL` of class `pfield` holding a `SPAN` with text `Postcode` then `inp`; `field('Town', null, { cls: 'disp-fld' })` has class `pfield disp-fld` and one child, and a control appended afterwards is its second child; `field('Code', inp, { help: 'Six digits' })` ends with a `P` of class `field-help` and text `Six digits`.
`t_every_captioned_field_is_built_by_the_part`: no section except `js/part-field.js` contains `el('label', 'pfield'`, `el('label', 'disp-fld'`, `el('label', 'disp-addr-f'` or `el('label', 'sk-field'`; `disp-fld-lab` and `disp-addr-lab` appear nowhere in `SCRIPT` or `CSS`.
Run with `ONLY=`; Expected: FAIL.

- [ ] **Step 2: The part and the codemod.** Write `field()`. Codemod each `const X = el('label', '<family>');` whose next statement is `X.append(el('span', <null|'disp-fld-lab'|'disp-addr-lab'>, CAPTION)[, …rest])`: emit `const X = field(CAPTION, null, { cls: '<family>' })` (no `cls` for `pfield`), and keep `X.append(…rest)` when `rest` is not empty. Print each converted site; stop on any site that does not match and convert it by hand. Delete the two caption rules in `dispatch.css`.

- [ ] **Step 3: Run** the two tests, the page suite (re-point tests that quoted the old wrappers, ledgered; load the part into any harness that calls a converted builder), the dispatch suite, and the browser suite. Expected: PASS; `0 failed`; `1012 passed`; browser all passed.

- [ ] **Step 4: Commit.**

---

### Task 3: Every control named

**Files:** `tests/browser/probes.js` (`unnamed(page)`), `tests/browser/pages.spec.js`, `tests/browser/keyboard.spec.js`, the controls the check names (`report-tools.js`, `crm.js`, `production-manager.js`, `dispatch.js`, `settings.js` and the shell's sign-off box), `tests/browser/record/a11y.json`, `tests/test_frontend.py`

- [ ] **Step 1: The check, failing.** `P.unnamed(page)` returns a description of every visible `input` (not hidden or file), `select`, `textarea` and `[role=switch]` whose accessible name is empty (no `labels`, no `aria-label`, no `aria-labelledby`, no `title`; for a button, no words either). `pages.spec.js` asserts `expect(await P.unnamed(page), 'controls with no name').toEqual([])` after the existing checks; `keyboard.spec.js`'s `journey()` asserts the same before pressing Escape. Run `pages.spec.js` and `keyboard.spec.js`; Expected: failures naming the controls in the spec's list.

- [ ] **Step 2: Name them.** CRM Contacts' row checkbox: `aria-label` `'Select ' + c.name`; the report question box: `'Ask a question about this report'`; the CRM deal's note: `'A note about this deal'`; the dispatch manifest and stock usage dates: `'Date'`; stock usage quantity: `'Quantity'`; the paste boxes: `'Paste an address'`; parcel sizes: `'Width in cm'`, `'Length in cm'`, `'Depth in cm'`, `'Weight in kg'` (and the value box by what it holds); shipping-settings credentials and box rows by their captions; the Settings sign-off box by its title (`aria-labelledby`). Rerun until both specs pass.

- [ ] **Step 3: Placeholder guard** `t_no_field_is_named_only_by_its_placeholder`: for each statement in `SCRIPT` that sets `X.placeholder =`, the same function either sets `X.setAttribute('aria-label'` / `aria-labelledby`, or passes `X` to `field(`, or appends `X` into a `field(` result. Name the offenders; fix each the way Step 2 does.

- [ ] **Step 4: Lower the record.** `UPDATE_RECORD=1 make test-browser`; Expected: `a11y.json` loses the `label` counts (30, CRM Contacts) and nothing rises. Commit with the record diff.

---

### Task 4: Proof, `DESIGN.md`, `make check`, push

- [ ] **Step 1: Screenshots.** As in the buttons plan: shoot `pages.spec.js` on `refactor/buttons-links` (a worktree with this checkout's `node_modules` linked) and twice on this branch; compare with Pillow; subtract the states that differ between two identical runs. Expected: only states with a converted caption or a newly named control differ.
- [ ] **Step 2: `docs/DESIGN.md`**: Switches (`switchBtn`, `setSwitch`, the Settings switches, no fixers), Fields (`field()`, the house label, the help line), Names (every control, the browser check); add `t_every_captioned_field_is_built_by_the_part` and `t_the_switch_fixers_stay_gone` to `t_the_design_rules_live_in_one_document`'s guard list and the spec to its spec list.
- [ ] **Step 3: `make check`**, Expected exit 0. **Self-review** against `code-reviewer.md` and the Review Focus; ledger it. Push. The pull request waits for #32, the window part and buttons and links.
