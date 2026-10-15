# One window part Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every window in Reactor is built, opened and closed by one part, `dialog()`, which owns a window's role, name, X, focus in and back, and Tab fence; the after-the-fact window fixers are deleted; `docs/DESIGN.md` becomes the one current design rulebook.

**Architecture:** A new section `static/src/js/part-dialog.js` (in the one function scope, after `js/choosers.js` in the manifest) holds `dialog()`, `dialogShow()`/`dialogHide()` for the Settings window written into the page, one stack of open windows, and the key handling (Escape for the yes/no question only, the Tab fence). The 23 windows built by hand keep their markup and classes: only their scaffolding is replaced by a `dialog()` call whose result is destructured into the names the builder already used (`overlay`, `modal`, `head`, `x`, `body`), so each builder's own body is untouched. `js/page-observers.js` loses `syncDialogs`, the focus observer and the window Tab fence; the sign-in screen keeps a fence of its own.

**Tech Stack:** Plain JavaScript in the page's one scope, the page suite (`tests/test_frontend.py`, with its node `MINIDOM` harness), the browser suite (Playwright, Chromium).

**Spec:** `docs/superpowers/specs/2026-10-15-window-part-design.md` (approved 15 Oct, approach A; corrected b7288bf: questions and notices keep no X; every close goes through the part).

## Global Constraints

- Nothing on screen changes: same markup, same classes, same stylesheet. The browser suite's record (`tests/browser/record/*.json`) may not go up anywhere; if it goes down, it is lowered in the same pull request and the change listed.
- A window holding work closes only by its X or its own answers (Save, Cancel, Done): never Escape, never a click outside it. The yes/no question (`uiConfirm`) alone answers Escape (No). A question or notice answered by its own buttons has no X, as today.
- Every window closes through the part (`win.close()`); nothing outside `part-dialog.js` builds a `.modal-overlay` or removes one.
- Callers do not change: `uiConfirm`, `uiAskText`, `uiAskPassword`, `sheetModal`, `crmModal` and `mailModal` keep their names, arguments and what they return.
- Frozen areas untouched: the printed labels and print CSS, the Production Manager queue's rows, columns, statuses and actions, the Quote Engine. The queue's windows (edit order, dispatch, size rules) move to the part; nothing in the queue itself changes.
- Every app change carries a release note dated the merge day; British English, no dashes in UI copy; the repo is public (no business name in docs, PR text or commits).
- No agents: the initiative's five are spent. The final review is a self-review, said so plainly.
- The branch `refactor/window-part` is stacked on `refactor/page-source` (PR #32, waiting on GitHub Actions, which is disabled for the repo until Cameron re-enables it). The pull request targets `main` only after #32 merges.

## Review Focus

1. **A window closed by hand** in code written next year (`overlay.remove()`): the part's stack would keep a window that is gone, and Escape or Tab would serve it. Expected: the page suite fails naming the line; and if one slips through, the part forgets a window no longer in the page. Pinned by Task 2's `t_every_window_is_built_and_closed_by_the_part` and Task 1's `t_the_window_part_keeps_one_stack`.
2. **A question opened over a window** (a confirm inside the edit-order window): Escape answers No and the window under it stays open, and focus goes back to the button in that window. Pinned by Task 2's `t_a_question_over_a_window_answers_escape_alone`.
3. **Closing a window that is not on top** (Settings closed while its Manage shipping opens the next window; a window that closes itself after a save while a toast is up): the stack must lose that window and keep the rest in order. Pinned by Task 1's `t_the_window_part_keeps_one_stack`.
4. **A window opened from a dropdown menu** (the Production Manager's More menu): the item that opened it is gone when the window closes; focus must go back to the menu's button. Pinned by Task 4's menu journeys.
5. **A redrawn page under a closing window** (the CRM board redraws as a deal closes): what the window does as it closes must run before focus looks for its opener, or focus lands on a card about to be replaced. Pinned by Task 1's `t_the_window_part_builds_a_named_dialog_with_its_x` (order of onClose and give-back) and the existing `keyboard: crm~deal` journey.

---

### Task 1: The part

**Files:**
- Create: `static/src/js/part-dialog.js`
- Modify: `static/src/manifest.json` (one line), `static/src/js/page-observers.js` (two names move to the part), `tests/test_frontend.py` (two helpers, two tests)

**Interfaces:**
- Produces: `dialog(opts) -> { overlay, modal, head, heading, x, body, foot(), close(), isTop() }` where `opts` is `{ title, size?, overlayClass?, bodyClass?, x?: false, opener?, onEscape?, onClose? }`; `dialogShow(overlay)`, `dialogHide(overlay)`; in `tests/test_frontend.py`: `dialog_part() -> str` (the part's source from `SCRIPT`) and `dialog_harness() -> str` (node stand-ins plus the part, to follow `MINIDOM`).

- [ ] **Step 1: The two test helpers**

In `tests/test_frontend.py`, directly after the `fn_src` function (top of the file), add:

```python
DIALOG_START = "/* ---------- the window part ----------"
DIALOG_END = "/* ---------- the window part end ---------- */"


def dialog_part():
    """The window part's source (static/src/js/part-dialog.js) as the page has it."""
    return SCRIPT[SCRIPT.index(DIALOG_START):SCRIPT.index(DIALOG_END)]
```

and directly after the `_run_node` function (just above `t_a_confirm_dialog_answers_for_the_focused_button`), add:

```python
def dialog_harness():
    """The window part, runnable after MINIDOM: node has no frames, no icons
    and no CSS.escape, so plain stand-ins come first."""
    return ("globalThis.I = globalThis.I || { x: '' };\n"
            "globalThis.requestAnimationFrame = globalThis.requestAnimationFrame || ((f) => setTimeout(f, 0));\n"
            "globalThis.CSS = globalThis.CSS || { escape: (s) => String(s) };\n" + dialog_part())
```

- [ ] **Step 2: Write the failing tests** (after `dialog_harness`)

```python
@test
def t_the_window_part_builds_a_named_dialog_with_its_x():
    """Stage 3, piece 1 (docs/superpowers/specs/2026-10-15-window-part-design.md):
    every window is built by dialog(), which gives it today's markup and
    classes, the dialog role named by its own title, an X named Close that
    closes it, focus inside as it opens, and one footer made when first asked
    for. What a window does as it closes runs before focus looks for its
    opener: the CRM board is redrawn before focus finds the deal's new card."""
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    js = MINIDOM + "\n" + dialog_harness() + r"""
const order = [];
const opener = el('button', 'btn'); document.body.append(opener); opener.focus();
const w = dialog({ title: 'Edit Loan 1', size: 'disp-modal', bodyClass: 'fprev-body', onClose: () => order.push('onClose') });
const out = {
  overlay: w.overlay.className, modal: w.modal.className, body: w.body.className,
  role: w.modal.getAttribute('role'), modalFlag: w.modal.getAttribute('aria-modal'),
  named: w.modal.getAttribute('aria-labelledby') === w.heading.id && w.heading.textContent === 'Edit Loan 1',
  xName: w.x.getAttribute('aria-label'), xLast: w.head.children[w.head.children.length - 1] === w.x,
  focusOnX: document.activeElement === w.x, inPage: w.overlay.parentNode === document.body, top: w.isTop(),
};
const f1 = w.foot(), f2 = w.foot();
out.footOnce = f1 === f2 && f1.className === 'modal-foot' && w.modal.children[2] === f1;
const q = dialog({ title: 'Sure?', x: false });
out.noX = q.x === null && q.head.children.length === 1;
q.close();
w.x.click();
out.closed = w.overlay.parentNode === null && order.join() === 'onClose';
w.close();
out.once = order.length === 1;
console.log(JSON.stringify(out));
"""
    got = _run_node(js)
    ok(got["overlay"] == "modal-overlay show" and got["modal"] == "modal disp-modal" and got["body"] == "modal-body fprev-body",
       "today's classes: %r" % got)
    ok(got["role"] == "dialog" and got["modalFlag"] == "true" and got["named"], "a modal dialog named by its title")
    ok(got["xName"] == "Close" and got["xLast"], "an X named Close, last in the header")
    ok(got["focusOnX"] and got["inPage"] and got["top"], "open, on top, with focus inside")
    ok(got["footOnce"], "one footer, after the body, made when first asked for")
    ok(got["noX"], "a question answered by its own buttons has no X")
    ok(got["closed"] and got["once"], "the X closes it, and closing twice runs its close once")
    part = dialog_part()
    ok(part.index("if (opts.onClose) opts.onClose();") < part.index("dialogGiveBack(rec.opener);"),
       "what the window does as it closes runs before focus looks for its opener")


@test
def t_the_window_part_keeps_one_stack():
    """One stack of open windows, topmost last. Only the window on top hears
    Escape, and only a window that asked for it (the yes/no question) answers
    it; a window closed under another leaves the rest in order; and a window
    removed some other way is forgotten rather than left to swallow the keys."""
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    js = MINIDOM + "\n" + dialog_harness() + r"""
const out = {};
const a = dialog({ title: 'A' });
const b = dialog({ title: 'B', x: false, onEscape: () => b.close() });
pressKey('Escape');
out.bClosedByEscape = b.overlay.parentNode === null && a.overlay.parentNode === document.body && a.isTop();
pressKey('Escape');
out.aIgnoresEscape = a.overlay.parentNode === document.body;
const c = dialog({ title: 'C' });
a.close();
out.closedUnder = c.isTop() && c.overlay.parentNode === document.body;
const d = dialog({ title: 'D' });
d.overlay.remove(); d.overlay.isConnected = false;
out.forgotten = c.isTop();
c.close();
console.log(JSON.stringify(out));
"""
    got = _run_node(js)
    ok(got["bClosedByEscape"], "Escape answers the window on top that asked for it: %r" % got)
    ok(got["aIgnoresEscape"], "and a window holding work ignores it")
    ok(got["closedUnder"], "closing a window under another keeps the one on top")
    ok(got["forgotten"], "a window removed some other way is forgotten")
```

- [ ] **Step 3: Run them to verify they fail**

Run: `ONLY=t_the_window_part python3 tests/test_frontend.py 2>&1 | tail -3`
Expected: an error from `dialog_part()`: `ValueError: substring not found` (the part does not exist yet).

- [ ] **Step 4: Write `static/src/js/part-dialog.js`**

```js
        /* ---------- the window part ----------
           Every window in the app is built here (docs/DESIGN.md, Windows), so
           every window behaves alike because one piece of code makes it, not
           because each copy was careful:
           - it is a dialog, modal, named by its own title;
           - a window holding work has an X named Close and, with its own
             answers (Save, Cancel, Done), no other way out: never Escape, never
             a click outside it, so a slip cannot lose what was typed. A
             question or notice answered by its own buttons has no X
             (x: false), and the yes/no question alone answers Escape
             (onEscape);
           - focus moves in as it opens, and back to what opened it as it
             closes: to that control's redrawn twin when the page was redrawn
             (data-focus-key), never to a field left long before;
           - Tab stays inside the window on top;
           - it closes through close() and nothing else, so the part always
             knows which window is on top.
           It builds the markup windows always had, with the same classes, so
           the stylesheet does not change. */
        const dialogStack = [];   // open windows, topmost last: { overlay, onEscape, opener }
        let dialogSeq = 0;
        const DIALOG_FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
        /* The last control focused outside every window: a click can open a
           window and leave focus on the page behind, or on nothing. */
        let focusOutside = null;
        document.addEventListener('focusin', (e) => {
            if (e.target && e.target.closest && !e.target.closest('.modal-overlay')) focusOutside = e.target;
        });
        /* Focus that left for nowhere (a tap elsewhere; on a phone a tap moves
           no focus) forgets that control: closing a window must not send focus
           back to a field left long before, which on an iPhone raises the
           keyboard. */
        document.addEventListener('focusout', (e) => {
            if (!e.relatedTarget && e.target === focusOutside) focusOutside = null;
        });
        /* The window on top. One removed some other way (which the page suite
           forbids) is forgotten rather than left to swallow the keys. */
        function dialogTop() {
            for (let i = dialogStack.length - 1; i >= 0; i--) {
                if (dialogStack[i].overlay.isConnected === false) dialogStack.splice(i, 1);
                else return dialogStack[i];
            }
            return null;
        }
        function dialogOpener(given) {
            if (given) return given;
            const now = document.activeElement;
            return now && now !== document.body ? now : focusOutside;
        }
        /* A window that focuses nothing of its own gets its X or, with no X,
           its first control. Two frames: a builder that focuses its own field
           does so in the first, and is left alone. */
        function dialogFocusIn(overlay) {
            requestAnimationFrame(() => requestAnimationFrame(() => {
                if (!overlay.isConnected || !overlay.classList.contains('show') || overlay.contains(document.activeElement)) return;
                const to = overlay.querySelector('.modal-head button[aria-label="Close"]')
                    || [...overlay.querySelectorAll(DIALOG_FOCUSABLE)].find(f => !f.disabled && f.getClientRects().length);
                if (to) to.focus();
            }));
        }
        /* Focus back to what opened the window, if nothing else has taken it.
           A page the window redrew as it closed (a CRM deal redraws the board)
           replaced that control: the new one carries the same data-focus-key,
           and focus goes there once it is drawn. */
        function dialogGiveBack(back) {
            if (!back || !back.focus) return;
            const lost = () => !document.activeElement || document.activeElement === document.body
                || document.activeElement.isConnected === false;
            if (back.isConnected) { if (lost()) back.focus(); return; }
            const key = back.dataset && back.dataset.focusKey;
            if (!key) return;
            let tries = 0;
            const look = () => {
                const twin = document.querySelector('[data-focus-key="' + CSS.escape(key) + '"]');
                if (twin) { if (lost()) twin.focus(); return; }
                if (++tries < 60) setTimeout(look, 50);
            };
            look();
        }
        function dialog(opts) {
            const overlay = el('div', 'modal-overlay show' + (opts.overlayClass ? ' ' + opts.overlayClass : ''));
            const modal = el('div', 'modal' + (opts.size ? ' ' + opts.size : ''));
            const head = el('div', 'modal-head');
            const heading = el('h3', null, opts.title);
            heading.id = 'dialog-title-' + (++dialogSeq);
            head.append(heading);
            let x = null;
            if (opts.x !== false) {
                x = el('button', 'icon-btn'); x.innerHTML = I.x;
                x.title = 'Close'; x.setAttribute('aria-label', 'Close');
                head.append(x);
            }
            const body = el('div', 'modal-body' + (opts.bodyClass ? ' ' + opts.bodyClass : ''));
            modal.setAttribute('role', 'dialog');
            modal.setAttribute('aria-modal', 'true');
            modal.setAttribute('aria-labelledby', heading.id);
            modal.append(head, body);
            overlay.append(modal);
            let footEl = null;
            const foot = () => {
                if (!footEl) { footEl = el('div', 'modal-foot'); modal.append(footEl); }
                return footEl;
            };
            const rec = { overlay: overlay, onEscape: opts.onEscape || null, opener: dialogOpener(opts.opener) };
            let open = true;
            const close = () => {
                if (!open) return;
                open = false;
                overlay.remove();
                const at = dialogStack.indexOf(rec);
                if (at >= 0) dialogStack.splice(at, 1);
                /* What the window does as it closes comes first: a page it
                   redraws is redrawn before focus looks for its opener. */
                if (opts.onClose) opts.onClose();
                dialogGiveBack(rec.opener);
            };
            if (x) x.onclick = close;
            dialogStack.push(rec);
            document.body.append(overlay);
            if (x) x.focus(); else dialogFocusIn(overlay);
            return { overlay: overlay, modal: modal, head: head, heading: heading, x: x, body: body, foot: foot,
                     close: close, isTop: () => dialogTop() === rec };
        }
        /* The window written into the page (Settings) opens and closes by its
           show class rather than being built: the same stack, focus and fence. */
        function dialogShow(overlay) {
            if (dialogStack.some(r => r.overlay === overlay)) return;
            const rec = { overlay: overlay, onEscape: null, opener: dialogOpener() };
            overlay.classList.add('show');
            dialogStack.push(rec);
            dialogFocusIn(overlay);
        }
        function dialogHide(overlay) {
            overlay.classList.remove('show');
            const at = dialogStack.findIndex(r => r.overlay === overlay);
            if (at < 0) return;
            const rec = dialogStack.splice(at, 1)[0];
            dialogGiveBack(rec.opener);
        }
        document.addEventListener('keydown', (e) => {
            const top = dialogTop();
            if (!top) return;
            if (e.key === 'Escape') {
                if (top.onEscape) { e.stopPropagation(); top.onEscape(); }
                return;
            }
            if (e.key !== 'Tab') return;
            /* An open menu manages its own keys and closes on any outside
               press; the sign-in screen sits over everything and keeps a fence
               of its own (js/page-observers.js). */
            if (document.querySelector('.dmenu')) return;
            if ([...document.querySelectorAll('.auth-overlay')].some(o => o.getClientRects().length)) return;
            const focusables = [...top.overlay.querySelectorAll(DIALOG_FOCUSABLE)]
                .filter(f => !f.disabled && f.getClientRects().length);
            if (!focusables.length) return;
            const first = focusables[0], last = focusables[focusables.length - 1];
            if (!top.overlay.contains(document.activeElement)) { e.preventDefault(); first.focus(); return; }
            if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
            else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        });
        /* ---------- the window part end ---------- */
```

Every line ends with a newline (the page suite's `t_every_page_section_is_whole_lines`). In `static/src/manifest.json`, add `"js/part-dialog.js",` on the line after `"js/choosers.js",`.

**Move, do not copy, two names.** The page is one function scope, so a second `const DIALOG_FOCUSABLE` or `let focusOutside` would be a redeclaration and the whole script would fail to load. In `static/src/js/page-observers.js`, delete `const DIALOG_FOCUSABLE = ...;`, the comment above `let focusOutside = null;`, that line, and its two listeners (the `focusin` listener that sets `focusOutside` and the `focusout` listener with the "Focus that left for nowhere" comment above it). The old focus observer there (`dialogOpened`, `dialogClosed`) goes on working until Task 3 deletes it: it now reads the part's `focusOutside` and `DIALOG_FOCUSABLE`, which the manifest loads first.

While the old fixers still run (until Task 3), both sets act on windows; each step they take is idempotent (focus the same control, wrap Tab once: after the first handler wraps, the second sees focus on `first` and does nothing), so the page behaves as before.

- [ ] **Step 5: Run the tests**

Run: `ONLY=t_the_window_part python3 tests/test_frontend.py 2>&1 | tail -3; ONLY=t_the_manifest_and python3 tests/test_frontend.py 2>&1 | grep -E "PASS|FAIL"; env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN npx playwright test -c tests/browser/playwright.config.js keyboard.spec.js --reporter=line 2>&1 | grep -vE "^\[WebServer\]" | tail -1`
Expected: `2 passed, 0 failed`; `PASS  t_the_manifest_and_the_sections_agree`; `4 passed` (the page still loads, and the three windows and the touch case behave as before).

- [ ] **Step 6: Commit**

```bash
git add static/src/js/part-dialog.js static/src/js/page-observers.js static/src/manifest.json tests/test_frontend.py
git commit -m "The window part: dialog() builds a named dialog with its X, one stack of open windows, focus in and back, and the Tab fence

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Every window built and closed by the part

**Files:**
- Modify (static/src/js): `crm.js`, `dispatch.js`, `files.js`, `loans.js`, `production-manager.js`, `inbox-filters-and-sending.js`, `settings.js`, `team-and-sign-in.js`, `charts.js`, `structured-response.js`, `memory.js`
- Modify: `tests/test_frontend.py` (one guard, one harness test, five existing tests)

**Interfaces:**
- Consumes: `dialog(opts)` and its result (Task 1); `dialog_part()`, `dialog_harness()` (Task 1).
- Produces: no new names. `sheetModal(title)`, `crmModal(title)`, `mailModal(title)`, `uiConfirm(message, opts)`, `uiAskText(...)`, `uiAskPassword(...)` keep their signatures and results.

- [ ] **Step 1: Write the failing guard** (in `tests/test_frontend.py`, after `t_the_window_part_keeps_one_stack`)

```python
@test
def t_every_window_is_built_and_closed_by_the_part():
    """Windows were built by hand in 23 places, each a copy of one shape with
    its own small differences, and made to behave alike afterwards by fixers.
    dialog() builds them all now; a window built or removed by hand would
    escape its role, its focus and the part's stack."""
    sys.path.insert(0, ROOT)
    import pagesource
    bad = []
    for rel in pagesource.manifest(ROOT)["js"]:
        if rel == "js/part-dialog.js":
            continue
        src = open(os.path.join(ROOT, pagesource.SRC, rel), encoding="utf-8").read()
        for pat, what in ((r"el\('div', 'modal-overlay", "builds a window"), (r"overlay\.remove\(\)", "removes a window by hand")):
            for m in re.finditer(pat, src):
                bad.append("%s:%d %s" % (rel, src[:m.start()].count("\n") + 1, what))
    ok(not bad, "outside the window part: %s" % bad)
```

Run: `ONLY=t_every_window_is_built python3 tests/test_frontend.py 2>&1 | grep -E "PASS|FAIL" | cut -c1-300`
Expected: FAIL, naming about 50 lines across the eleven files.

- [ ] **Step 2: Convert the builders**

In every builder below, replace the **Before** text with the **After** text exactly. `win` is free in all eleven files. Where a builder's own body goes on using `overlay`, `modal`, `head`, `x` or `body`, the destructuring keeps those names, so nothing else in the function changes. Remove each comment that only restated the X-only rule beside the old scaffolding ("Backdrop clicks never close ...", "The X is the only way out (user rule).", "the X is the only way out, as everywhere else"): the part states it once.

**2a. `crm.js` `crmModal`** — replace the whole function:

```js
        function crmModal(title) {
            /* The X is the house window's (dialog()); closing redraws the board
               when the CRM is on screen. The action bar starts empty each time
               it is asked for: a deal repaints its own actions. */
            const win = dialog({ title: title, size: 'disp-modal',
                onClose: () => { if (document.querySelector('#view-crm.active')) renderCRM(); } });
            const foot = () => { const f = win.foot(); f.innerHTML = ''; return f; };
            return { body: win.body, close: win.close, head: win.head, foot: foot };
        }
```

**2b. `dispatch.js` `openOrderEdit`** — Before:

```js
            const overlay = el('div', 'modal-overlay show');
            const modal = el('div', 'modal disp-modal');
            const head = el('div', 'modal-head');
            const h = el('h3', null, 'Edit ');
            h.append(orderA(orderNo(o), o.admin_url, 'modal-order-link'));
            const x = el('button', 'icon-btn'); x.innerHTML = I.x; x.title = 'Close';
            head.append(h, x);
            const body = el('div', 'modal-body');
            modal.append(head, body); overlay.append(modal); document.body.append(overlay);
            const prev = document.activeElement;
            let saving = false;
            const close = () => {
                if (saving) { addToast('The change is still saving. Please wait.'); return; }
                overlay.remove(); if (prev && prev.focus) prev.focus();
            };
            x.onclick = close;   // the X is the only way out: a misclick must not wipe a filled form
            x.focus();
```

After:

```js
            const win = dialog({ title: 'Edit ', size: 'disp-modal' });
            const { overlay, modal, head, x, body } = win;
            const h = win.heading;
            h.append(orderA(orderNo(o), o.admin_url, 'modal-order-link'));
            let saving = false;
            const close = () => {
                if (saving) { addToast('The change is still saving. Please wait.'); return; }
                win.close();
            };
            x.onclick = close;   // the part's X, held while a change is saving
```

and later in the same function replace `overlay.remove(); if (prev && prev.focus) prev.focus();` with `win.close();`.

**2c. `dispatch.js` `openDispatch`** — Before (the first lines of the function body through `x.focus();`):

```js
            const overlay = el('div', 'modal-overlay show');
            const modal = el('div', 'modal disp-modal');
            const head = el('div', 'modal-head');
            const dh = el('h3', null, 'Dispatch · ');
            dh.append(orderA(orderNo(o), o.admin_url, 'modal-order-link'));
            head.append(dh);
            const x = el('button', 'icon-btn'); x.innerHTML = I.x; x.title = 'Close'; head.append(x);
            const body = el('div', 'modal-body');
            modal.append(head, body); overlay.append(modal); document.body.append(overlay);
            const prev = document.activeElement;
```

After:

```js
            const win = dialog({ title: 'Dispatch · ', size: 'disp-modal' });
            const { overlay, modal, head, x, body } = win;
            const dh = win.heading;
            dh.append(orderA(orderNo(o), o.admin_url, 'modal-order-link'));
```

and its close, Before:

```js
            const close = () => {
                if (booking) { addToast('The courier booking is still going through. Please wait.'); return; }
                overlay.remove(); document.removeEventListener('keydown', esc);
                if (prev && prev.focus) prev.focus();
            };
            function esc(e) { /* Escape deliberately does not close either: X only. */ }
            x.onclick = close;
            // Backdrop clicks never close: a misclick must not wipe a filled form.
            // The X is the only way out (user rule).
            document.addEventListener('keydown', esc);
            x.focus();
```

After:

```js
            const close = () => {
                if (booking) { addToast('The courier booking is still going through. Please wait.'); return; }
                win.close();
            };
            x.onclick = close;   // the part's X, held while money is being spent
```

**2d. `dispatch.js` `openCustomShip`** — Before:

```js
            const overlay = el('div', 'modal-overlay show');
            const modal = el('div', 'modal disp-modal');
            const head = el('div', 'modal-head');
            head.append(el('h3', null, 'New shipment'));
            const x = el('button', 'icon-btn'); x.innerHTML = I.x; x.title = 'Close'; head.append(x);
            const body = el('div', 'modal-body');
            modal.append(head, body); overlay.append(modal); document.body.append(overlay);
            const prev = document.activeElement;
            let booking = false;
            const close = () => {
                if (booking) { addToast('The courier booking is still going through. Please wait.'); return; }
                overlay.remove(); if (prev && prev.focus) prev.focus();
            };
            x.onclick = close;   // the X is the only way out: a misclick must not wipe a filled form
            x.focus();
```

After:

```js
            const win = dialog({ title: 'New shipment', size: 'disp-modal' });
            const { overlay, modal, head, x, body } = win;
            let booking = false;
            const close = () => {
                if (booking) { addToast('The courier booking is still going through. Please wait.'); return; }
                win.close();
            };
            x.onclick = close;   // the part's X, held while a booking is going through
```

**2e. `dispatch.js` `openShippingSettings`** — Before:

```js
            const overlay = el('div', 'modal-overlay show');
            const modal = el('div', 'modal disp-modal');
            const head = el('div', 'modal-head');
            head.append(el('h3', null, 'Shipping settings'));
            const x = el('button', 'icon-btn'); x.innerHTML = I.x; x.title = 'Close'; head.append(x);
            const body = el('div', 'modal-body');
            modal.append(head, body); overlay.append(modal); document.body.append(overlay);
            const prev = document.activeElement;
            const close = () => { overlay.remove(); document.removeEventListener('keydown', esc); if (prev && prev.focus) prev.focus(); };
            function esc(e) { /* Escape deliberately does not close either: X only. */ }
            x.onclick = close;
            // Backdrop clicks never close: a misclick must not wipe a filled form.
            // The X is the only way out (user rule).
            document.addEventListener('keydown', esc);
```

After:

```js
            const win = dialog({ title: 'Shipping settings', size: 'disp-modal' });
            const { overlay, modal, head, x, body } = win;
            const close = win.close;
```

(The function goes on building its footer with `el('div', 'modal-foot')` and `modal.append(foot)`; that stays, and `t_save_is_pinned_where_every_other_modal_puts_it` keeps passing.)

**2f. `files.js` `openPreview`** — Before:

```js
            const overlay = el('div', 'modal-overlay show');
            const modal = el('div', 'modal disp-modal');
            const head = el('div', 'modal-head');
            head.append(el('h3', null, f.name));
            const x = el('button', 'icon-btn'); x.innerHTML = I.x; x.title = 'Close';
            const close = () => overlay.remove();
            x.onclick = close;   // Backdrop clicks never close a window here; the X is the way out.
            head.append(x);
            const body = el('div', 'modal-body fprev-body');
```

After:

```js
            const win = dialog({ title: f.name, size: 'disp-modal', bodyClass: 'fprev-body' });
            const { overlay, modal, head, x, body } = win;
            const close = win.close;
```

and replace `modal.append(head, body, foot); overlay.append(modal); document.body.append(overlay);` with `modal.append(foot);`.

**2g. `files.js` `openMovePicker`** — Before:

```js
            const overlay = el('div', 'modal-overlay show confirm-overlay');
            const modal = el('div', 'modal confirm-modal');
            const head = el('div', 'modal-head');
            head.append(el('h3', null, 'Move ' + (ids.length === 1 ? 'file' : ids.length + ' files') + ' to'));
            const x = el('button', 'icon-btn'); x.innerHTML = I.x; x.title = 'Close';
            x.onclick = () => overlay.remove();
            head.append(x);
            const body = el('div', 'modal-body');
```

After:

```js
            const win = dialog({ title: 'Move ' + (ids.length === 1 ? 'file' : ids.length + ' files') + ' to',
                                 size: 'confirm-modal', overlayClass: 'confirm-overlay' });
            const { overlay, modal, head, x, body } = win;
```

then, inside `pick`, replace `overlay.remove();` with `win.close();`, and delete the closing lines `modal.append(head, body);` and `overlay.append(modal); document.body.append(overlay);`.

**2h. `loans.js` `sheetModal`** — replace the whole function:

```js
        function sheetModal(title) {
            return dialog({ title: title, size: 'disp-modal' });
        }
```

(Callers read `.overlay`, `.modal`, `.body` and `.close`; `dialog()` returns all four.)

**2i. `production-manager.js` `openProposal`** — Before:

```js
            const overlay = el('div', 'modal-overlay show');
            const modal = el('div', 'modal cmodal proof-modal');
            const head = el('div', 'modal-head');
            head.append(el('h3', null, 'Proof · ' + orderNo(o)));
            const ext = el('a', 'proof-ext', 'Open in new tab');
            ext.href = o.proposal_url; ext.target = '_blank'; ext.rel = 'noopener';
            head.append(ext);
            const x = el('button', 'icon-btn'); x.innerHTML = I.x; x.title = 'Close'; head.append(x);
            const body = el('div', 'modal-body proof-body');
```

After:

```js
            const win = dialog({ title: 'Proof · ' + orderNo(o), size: 'cmodal proof-modal', bodyClass: 'proof-body' });
            const { overlay, modal, head, x, body } = win;
            const ext = el('a', 'proof-ext', 'Open in new tab');
            ext.href = o.proposal_url; ext.target = '_blank'; ext.rel = 'noopener';
            x.before(ext);
```

and replace the closing block, Before:

```js
            modal.append(head, body); overlay.append(modal); document.body.append(overlay);
            const prev = document.activeElement;
            const close = () => {
                overlay.remove(); document.removeEventListener('keydown', esc);
                if (prev && prev.focus) prev.focus();   // back to where they were
            };
            function esc(e) { /* Escape deliberately does not close either: X only. */ }
            x.onclick = close;
            // Backdrop clicks never close: a misclick must not wipe a filled form.
            // The X is the only way out (user rule).
            document.addEventListener('keydown', esc);
            x.focus();
```

After: nothing (delete it; the part wires the X, focus and the way back).

**2j. `production-manager.js` `openSizeRulesModal`** — Before:

```js
            const overlay = el('div', 'modal-overlay show');
            const modal = el('div', 'modal');
            const head = el('div', 'modal-head');
            const srT = el('h3', null, 'Size rules');
            head.append(srT);
            const x = el('button', 'icon-btn'); x.innerHTML = I.x; x.title = 'Close';
            x.setAttribute('aria-label', 'Close');
            x.onclick = () => overlay.remove();
            head.append(x);
            const body = el('div', 'modal-body');
            modal.append(head, body);
            overlay.append(modal); document.body.append(overlay);
```

After:

```js
            const win = dialog({ title: 'Size rules' });
            const { overlay, modal, head, x, body } = win;
            const srT = win.heading;
```

**2k. `production-manager.js` `openSizeRuleModal`** — Before:

```js
            const overlay = el('div', 'modal-overlay show');
            const modal = el('div', 'modal');
            const head = el('div', 'modal-head');
            head.append(el('h3', null, 'Resolve ' + (row.model || 'this model')));
            const x = el('button', 'icon-btn'); x.innerHTML = I.x; x.title = 'Close';
            head.append(x);
            const body = el('div', 'modal-body');
            const close = () => overlay.remove();
            x.onclick = close;
```

After:

```js
            const win = dialog({ title: 'Resolve ' + (row.model || 'this model') });
            const { overlay, modal, head, x, body } = win;
            const close = win.close;
```

and replace `modal.append(head, body, foot);` followed by `overlay.append(modal); document.body.append(overlay);` with `modal.append(foot);`.

**2l. `production-manager.js` `openMargins`, `openDispatchManifest`, `openStockUsage`** — each opens with the same four lines. Before, for each (title `'Margins'` with `'modal disp-modal'`, `'Dispatch manifest'` with `'modal wide'`, `'Estimated stock usage'` with `'modal'`):

```js
            const overlay = el('div', 'modal-overlay show');
            const modal = el('div', 'modal disp-modal');
            const head = el('div', 'modal-head');
            head.append(el('h3', null, 'Margins'));
            const x = el('button', 'icon-btn'); x.innerHTML = I.x; x.title = 'Close'; head.append(x);
            const body = el('div', 'modal-body');
```

After, respectively:

```js
            const win = dialog({ title: 'Margins', size: 'disp-modal' });
            const { overlay, modal, head, x, body } = win;
```

```js
            const win = dialog({ title: 'Dispatch manifest', size: 'wide' });
            const { overlay, modal, head, x, body } = win;
```

```js
            const win = dialog({ title: 'Estimated stock usage' });
            const { overlay, modal, head, x, body } = win;
```

And their endings. `openMargins` and `openDispatchManifest`, Before:

```js
            modal.append(head, body); overlay.append(modal); document.body.append(overlay);
            const close = () => { overlay.remove(); };
            x.onclick = close;
            load();
```

After: `load();`. `openStockUsage`, Before:

```js
            modal.append(head, body); overlay.append(modal); document.body.append(overlay);
            const close = () => { overlay.remove(); document.removeEventListener('keydown', esc); };
            function esc(e) { /* Escape deliberately does not close either: X only. */ }
            x.onclick = close;
            // Backdrop clicks never close: a misclick must not wipe a filled form.
            // The X is the only way out (user rule).
            document.addEventListener('keydown', esc);
            load();
```

After: `load();`. None of the three uses `close` outside the deleted block (checked while planning).

**2m. `inbox-filters-and-sending.js` `openMailCompose`** — Before:

```js
            const overlay = el('div', 'modal-overlay show');
            const modal = el('div', 'modal');
            const head = el('div', 'modal-head');
            head.append(el('h3', null, 'New email'));
            const x = el('button', 'icon-btn'); x.innerHTML = I.x; x.title = 'Close';
            x.setAttribute('aria-label', 'Close');
            x.onclick = () => overlay.remove();
            head.append(x);
            // X only: a half-written email to a customer is not thrown away by
            // a stray click on the backdrop.
```

After:

```js
            // X only (dialog()): a half-written email to a customer is not
            // thrown away by a stray click on the backdrop.
            const win = dialog({ title: 'New email', bodyClass: 'stack-form' });
            const { overlay, modal, head, x, body } = win;
```

then delete its own `const body = el('div', 'modal-body stack-form');`, `modal.append(head, body);` and `overlay.append(modal); document.body.append(overlay);` lines, and replace `() => { overlay.remove(); refreshMailQuiet(); });` with `() => { win.close(); refreshMailQuiet(); });`.

**2n. `inbox-filters-and-sending.js` `mailModal`** — Before:

```js
            const overlay = el('div', 'modal-overlay show');
            const modal = el('div', 'modal disp-modal');
            const head = el('div', 'modal-head');
            head.append(el('h3', null, title));
            const x = el('button', 'icon-btn'); x.innerHTML = I.x; x.title = 'Close'; head.append(x);
            const body = el('div', 'modal-body');
            modal.append(head, body); overlay.append(modal); document.body.append(overlay);
```

After:

```js
            const win = dialog({ title: title, size: 'disp-modal', onClose: () => {
                if (overlay._timer) clearInterval(overlay._timer);
                if (!document.querySelector('#view-mail.active')) return;
                if (touched || !m.onQuietClose) refreshMailQuiet(); else m.onQuietClose();
            } });
            const { overlay, modal, head, x, body } = win;
```

and the end, Before:

```js
            m.close = () => {
                overlay.remove();
                if (overlay._timer) clearInterval(overlay._timer);
                if (!document.querySelector('#view-mail.active')) return;
                if (touched || !m.onQuietClose) refreshMailQuiet(); else m.onQuietClose();
            };
            x.onclick = m.close;   /* the X is the only way out, as everywhere else */
            return m;
```

After:

```js
            m.close = win.close;
            return m;
```

(`touched` and `m` are declared further down the function; the `onClose` closure reads them when the window closes, after both exist.)

**2o. `settings.js` `openMfaSetup`** — Before:

```js
            const overlay = el('div', 'modal-overlay show');
            const modal = el('div', 'modal');
            const head = el('div', 'modal-head');
            head.append(el('h3', null, 'Two-step sign-in'));
            const x = el('button', 'icon-btn'); x.innerHTML = I.x;
            x.title = 'Close'; x.setAttribute('aria-label', 'Close');
            x.onclick = () => overlay.remove();
            head.append(x);
            const body = el('div', 'modal-body');
            modal.append(head, body); overlay.append(modal); document.body.append(overlay);
```

After:

```js
            const win = dialog({ title: 'Two-step sign-in' });
            const { overlay, modal, head, x, body } = win;
```

then `cancel.onclick = () => overlay.remove();` becomes `cancel.onclick = win.close;` and `done.onclick = () => { overlay.remove(); refreshMfaRow(); };` becomes `done.onclick = () => { win.close(); refreshMfaRow(); };`.

**2p. `team-and-sign-in.js` `showStarterPw`** — Before:

```js
            const overlay = el('div', 'modal-overlay show confirm-overlay');
            const modal = el('div', 'modal confirm-modal');
            const head = el('div', 'modal-head'); head.append(el('h3', null, 'Starter password for ' + name));
            const body = el('div', 'modal-body');
```

After:

```js
            /* A notice with one answer (Done), so no X, like uiConfirm. */
            const win = dialog({ title: 'Starter password for ' + name, size: 'confirm-modal',
                                 overlayClass: 'confirm-overlay', x: false });
            const { body } = win;
```

then `const foot = el('div', 'modal-foot');` becomes `const foot = win.foot();`, `done.onclick = () => overlay.remove();` becomes `done.onclick = win.close;`, and the line `modal.append(head, body, foot); overlay.append(modal); document.body.append(overlay);` is deleted.

**2q. `charts.js` `openChartModal`** — replace the whole function:

```js
        function openChartModal(kind, opts) {
            const builder = CHART_BUILDERS[kind] || CHART_BUILDERS.trend;
            const win = dialog({ title: opts.title || 'Chart', size: 'cmodal', overlayClass: 'chart-modal' });
            /* The modal head already names the chart. Letting the rebuilt card
               print its own title too gave the same word twice, 43px apart, at
               two different weights. The value and the source line stay: the
               head carries neither. */
            win.body.append(builder(Object.assign({}, opts, { height: 360, noExpand: true, title: null })));
        }
```

**2r. `structured-response.js` `openStatDetail`** — Before:

```js
            const overlay = el('div', 'modal-overlay chart-modal show');
            const modal = el('div', 'modal smodal');  /* not .cmodal: the chart modal's 980px cap would win on source order */
            modal.setAttribute('role', 'dialog'); modal.setAttribute('aria-modal', 'true'); modal.setAttribute('aria-label', m.label);
            const head = el('div', 'modal-head'); head.append(el('h3', null, m.label));
            const x = el('button', 'icon-btn'); x.innerHTML = I.x; x.title = 'Close'; head.append(x);
            const body = el('div', 'modal-body');
```

After:

```js
            /* .smodal, not .cmodal: the chart modal's 980px cap would win on source order. */
            const win = dialog({ title: m.label, size: 'smodal', overlayClass: 'chart-modal', opener: opener });
            const { body } = win;
```

and delete the ending, Before:

```js
            modal.append(head, body); overlay.append(modal); document.body.append(overlay);
            // The X is the only way out, like every other modal here (user rule).
            x.onclick = () => { overlay.remove(); if (opener && opener.focus) opener.focus(); };
            x.focus();
```

**2s. `memory.js` `uiConfirm`** — replace the body of the `new Promise(resolve => { ... })` with:

```js
            return new Promise(resolve => {
                /* A question answered by its own buttons: no X, and Escape is
                   No (dialog() hands Escape to the question on top alone). */
                let answer = false;
                const win = dialog({ title: opts.title || 'Please confirm',
                    size: 'confirm-modal' + (danger ? ' confirm-danger' : ''), overlayClass: 'confirm-overlay', x: false,
                    onEscape: () => done(false),
                    onClose: () => { document.removeEventListener('keydown', key); resolve(answer); } });
                const body = win.body;
                /* A message may be a built panel rather than a sentence. el()
                   sets textContent, so handing it a node printed the string
                   "[object HTMLDivElement]" into the dialog - which is what the
                   Collections panel showed. */
                if (message instanceof Node) body.append(message);
                else body.append(el('p', 'confirm-msg', message));
                const foot = win.foot();
                const no = el('button', 'btn'); no.textContent = opts.cancelText || 'Cancel';
                const yes = el('button', 'btn ' + (danger ? 'btn-danger' : 'btn-primary'));
                yes.textContent = opts.okText || 'Confirm';
                /* A panel that only tells you something has one way out, not a
                   choice between two buttons that do the same thing. */
                if (opts.hideCancel) foot.append(yes); else foot.append(no, yes);
                const done = (v) => { answer = v; win.close(); };
                function key(e) {
                    /* Only the window on top answers: two stacked questions
                       each listen on the document. */
                    if (!win.isTop()) return;
                    // Enter is a reflex, so it answers only the reversible dialogs.
                    // A destructive one has to be clicked or tabbed to. And it is
                    // the focused button's answer: with Cancel focused, Enter is
                    // Cancel (it said yes, and booked and charged a courier), and a
                    // held key's repeats are not further presses.
                    if (e.key === 'Enter' && !danger) {
                        e.preventDefault();
                        if (e.repeat) return;
                        done(document.activeElement !== no);
                    }
                }
                no.onclick = () => done(false);
                yes.onclick = () => done(true);
                // A backdrop misclick must not silently answer Cancel; the buttons
                // (or Escape/Enter, which are deliberate) are the only answers.
                document.addEventListener('keydown', key);
                (danger ? no : yes).focus();
            });
```

and delete the line `const confirmStack = [];   // open confirm dialogs, topmost last` above the function.

**2t. `settings.js` `uiAskText` and `uiAskPassword`** — in each, replace the opening, Before (`uiAskText`; `uiAskPassword` is the same apart from its field):

```js
                const overlay = el('div', 'modal-overlay show');
                const modal = el('div', 'modal');
                const head = el('div', 'modal-head');
                head.append(el('h3', null, title));
                const finish = (v) => { overlay.remove(); resolve(v); };
                const x = el('button', 'icon-btn'); x.innerHTML = I.x;
                x.title = 'Close'; x.setAttribute('aria-label', 'Close');
                x.onclick = () => finish(null);
                head.append(x);
                const body = el('div', 'modal-body');
```

After:

```js
                /* A question typed into: it closes by its X or Cancel only. */
                let answer = null;
                const win = dialog({ title: title, onClose: () => resolve(answer) });
                const body = win.body;
                const finish = (v) => { answer = v; win.close(); };
```

then `const foot = el('div', 'modal-foot');` becomes `const foot = win.foot();`, and the line `modal.append(head, body, foot); overlay.append(modal); document.body.append(overlay);` is deleted.

- [ ] **Step 3: Run the guard**

Run: `ONLY=t_every_window_is_built python3 tests/test_frontend.py 2>&1 | grep -E "PASS|FAIL" | cut -c1-300`
Expected: `PASS`. Anything it still names is a site this step missed: convert it the same way.

- [ ] **Step 4: Bring five existing tests and two harnesses in step**

1. `t_every_modal_still_has_a_working_close`: replace its body with

```python
    """The rule above is only safe if each modal kept its X. Every window is
    built by dialog() now, which wires its X to close and names it."""
    part = dialog_part()
    ok("if (x) x.onclick = close;" in part, "the part wires its X to close")
    ok("x.setAttribute('aria-label', 'Close')" in part, "and names it")
```

2. `t_the_compose_window_is_a_modal_of_the_house_kind`: replace the two lines

```python
    ok("el('div', 'modal-overlay show')" in fn and "el('div', 'modal-head')" in fn,
       "the house modal idiom")
    ok("x.onclick = () => overlay.remove()" in fn, "with an X that closes it")
```

with

```python
    ok("dialog({ title: 'New email'" in fn, "built by the window part, whose X closes it")
```

3. The test reading `sm = fn_src("function sheetModal(")` (in the Xero sync window test): replace

```python
    sm = fn_src("function sheetModal(")
    ok("x.focus()" in sm, "focus goes into the window when it opens")
```

with

```python
    ok("dialog({" in fn_src("function sheetModal("), "the house window")
    ok("if (x) x.focus();" in dialog_part(), "and focus goes into the window when it opens")
```

4. `t_a_confirm_dialog_answers_for_the_focused_button`: replace

```python
    stack = re.search(r"const confirmStack = \[\];", SCRIPT)
    ok(stack, "the page keeps one stack of open confirms")
    js = MINIDOM + "\n" + destr + "\n" + stack.group(0) + "\n" + fn_src("function uiConfirm(message, opts)") + r"""
```

with

```python
    ok("const confirmStack" not in SCRIPT, "the window part keeps the one stack of open windows")
    js = MINIDOM + "\n" + dialog_harness() + "\n" + destr + "\n" + fn_src("function uiConfirm(message, opts)") + r"""
```

5. In `t_a_read_mark_the_page_makes_itself_never_outlives_the_board` and `t_closing_an_email_only_read_fetches_nothing`, each harness whose `fn_src` list includes `"function mailModal("`: change `""" + "\n".join(fn_src(f) for f in (` at the start of that list to `""" + dialog_harness() + "\n" + "\n".join(fn_src(f) for f in (`.

Then add, after `t_a_confirm_dialog_answers_for_the_focused_button`:

```python
@test
def t_a_question_over_a_window_answers_escape_alone():
    """A confirm asked from inside a window (the edit-order window asks before
    it cancels a shipment): Escape answers the question, No, and leaves the
    window under it open; a second Escape does nothing to that window."""
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    destr = re.search(r"const DESTRUCTIVE = /.*?/i;", SCRIPT).group(0)
    js = MINIDOM + "\n" + dialog_harness() + "\n" + destr + "\n" + fn_src("function uiConfirm(message, opts)") + r"""
const settle = (p) => Promise.race([p.then(v => v), new Promise(r => setTimeout(() => r('open'), 10))]);
(async () => {
  const out = {};
  const w = dialog({ title: 'Edit #210388', size: 'disp-modal' });
  const p = uiConfirm('Cancel this shipment?', { okText: 'Cancel shipment' });
  pressKey('Escape');
  out.answer = await settle(p);
  out.windowOpen = w.overlay.parentNode === document.body && w.isTop();
  pressKey('Escape');
  out.stillOpen = w.overlay.parentNode === document.body;
  console.log(JSON.stringify(out));
})();
"""
    got = _run_node(js)
    ok(got["answer"] is False, "Escape answers the question No: %r" % got)
    ok(got["windowOpen"], "and the window under it stays open, on top again")
    ok(got["stillOpen"], "and Escape never closes a window holding work")
```

- [ ] **Step 5: Run the page suite**

Run: `python3 tests/test_frontend.py > /tmp/wp-front.log 2>&1; tail -1 /tmp/wp-front.log; grep FAIL /tmp/wp-front.log | cut -c1-200`
Expected: `0 failed`. A failure that reads a builder's old scaffolding text (`el('div', 'modal-overlay show')`, `x.onclick = () => overlay.remove()`, `const prev = document.activeElement`) is a test pinning the old shape: point it at `dialog(` in that function or at `dialog_part()`, keeping what it was protecting. Any other failure is a conversion mistake: fix the conversion, never the test.

- [ ] **Step 6: Commit**

```bash
git add static/src/js tests/test_frontend.py
git commit -m "Every window built and closed by the part: 23 builders on dialog(), their markup and classes unchanged

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Settings on the part; the fixers deleted

**Files:**
- Modify: `static/src/shell.html` (the Settings window's two lines), `static/src/js/settings.js` (open and close), `static/src/js/page-observers.js`, `tests/test_frontend.py`

**Interfaces:**
- Consumes: `dialogShow(overlay)`, `dialogHide(overlay)` (Task 1).

- [ ] **Step 1: Write the failing guard** (after `t_a_question_over_a_window_answers_escape_alone`)

```python
@test
def t_the_window_fixers_stay_gone():
    """The fixers that made hand-built windows behave after they were drawn
    (syncDialogs, the focus observer, the window Tab fence) are gone: dialog()
    owns all of it. The sign-in screen, which is not a window, keeps a fence."""
    ok("function syncDialogs(" not in SCRIPT and "syncDialogs()" not in SCRIPT, "no dialog stamp")
    ok("function dialogOpened(" not in SCRIPT and "const dialogOpeners" not in SCRIPT, "no focus observer")
    ok(SCRIPT.count("let focusOutside") == 1 and "let focusOutside" in dialog_part(), "one record of where focus was, in the part")
    ok(".modal-overlay.show, .auth-overlay" not in SCRIPT, "no window fence outside the part")
    ok("document.querySelectorAll('.auth-overlay')" in SCRIPT[SCRIPT.index("function syncTableHeads("):], "the sign-in screen's own fence")
    ok("dialogShow($('settings-modal'))" in SCRIPT and "dialogHide($('settings-modal'))" in SCRIPT,
       "Settings opens and closes through the part")
    ok('<div class="modal" role="dialog" aria-modal="true" aria-labelledby="settings-title">' in HTML
       and '<h3 id="settings-title">Settings</h3>' in HTML, "and is a dialog named by its title from the start")
```

Run: `ONLY=t_the_window_fixers python3 tests/test_frontend.py 2>&1 | grep -E "PASS|FAIL" | cut -c1-200`
Expected: FAIL ("no dialog stamp").

- [ ] **Step 2: Settings through the part**

`static/src/shell.html`: in the Settings window, `<div class="modal">` (the line after `<div class="modal-overlay" id="settings-modal">`) becomes `<div class="modal" role="dialog" aria-modal="true" aria-labelledby="settings-title">`, and `<h3>Settings</h3>` becomes `<h3 id="settings-title">Settings</h3>`.

`static/src/js/settings.js`: in `openSettings`, `$('settings-modal').classList.add('show');` becomes `dialogShow($('settings-modal'));`; in `closeSettings`, `$('settings-modal').classList.remove('show');` becomes `dialogHide($('settings-modal'));`.

- [ ] **Step 3: Delete the fixers** (`static/src/js/page-observers.js`)

1. In the batched observer, `togglePass = requestAnimationFrame(() => { togglePass = 0; syncToggles(); syncDialogs(); syncTableHeads(); syncPanels(); });` becomes `togglePass = requestAnimationFrame(() => { togglePass = 0; syncToggles(); syncTableHeads(); syncPanels(); });`.
2. Delete the comment `/* Modals are built in thirteen places; the dialog semantics are stamped in one, the same way the switches get theirs above. The label comes from the modal's own heading. */`.
3. Delete `function syncDialogs() { ... }`, the call `syncDialogs();` after it, its comment and the `focusin` listener that calls it (`/* The observer above is rAF-batched ... */` and `document.addEventListener('focusin', (e) => { if (e.target && e.target.closest && e.target.closest('.modal-overlay')) syncDialogs(); });`).
4. Replace the Tab fence (from `/* One Tab fence for whichever modal is on top.` through the end of its `document.addEventListener('keydown', ...)`) with:

```js
        /* The sign-in screen is not a window and sits over everything (a
           session expiring with a window open): Tab stays on it. Windows keep
           their own fence (dialog(), js/part-dialog.js). */
        document.addEventListener('keydown', (e) => {
            if (e.key !== 'Tab') return;
            const auth = [...document.querySelectorAll('.auth-overlay')].find(o => o.getClientRects().length);
            if (!auth) return;
            const focusables = [...auth.querySelectorAll(
                'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')]
                .filter(f => !f.disabled && f.getClientRects().length);
            if (!focusables.length) return;
            const first = focusables[0], last = focusables[focusables.length - 1];
            if (!auth.contains(document.activeElement)) { e.preventDefault(); first.focus(); return; }
            if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
            else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        });
```

5. Delete the focus block, from `/* Focus into a window as it opens, and back to what opened it as it` through the second `MutationObserver` (the one ending `}).observe(o, { attributes: true, attributeFilter: ['class'] }));`): `dialogOpeners`, `DIALOG_FOCUSABLE`, `focusOutside` and its two listeners, `dialogOpened`, `dialogClosed` and both observers all live in the part now.

- [ ] **Step 4: Bring three existing tests in step**

1. `t_every_modal_is_a_dialog_and_tab_stays_inside_it`: replace its body with

```python
    """Every window is built by dialog(), which makes it a modal dialog named by
    its own title; one Tab fence in the part keeps focus inside the window on
    top, which matters twice over here because Escape is deliberately not a
    way out. The sign-in screen keeps a fence of its own."""
    part = dialog_part()
    ok("modal.setAttribute('role', 'dialog');" in part and "modal.setAttribute('aria-modal', 'true');" in part,
       "windows say they are modal dialogs")
    ok("modal.setAttribute('aria-labelledby', heading.id);" in part, "named by their own title")
    fence = part.split("if (e.key !== 'Tab') return;")[1][:1600]
    ok("e.shiftKey && document.activeElement === first" in fence, "and Tab wraps both ways inside the top window")
```

2. In the R13 table-heads test, `"syncToggles(); syncDialogs(); syncTableHeads();"` becomes `"syncToggles(); syncTableHeads();"`.
3. In the panels test, `"syncToggles(); syncDialogs(); syncTableHeads(); syncPanels();"` becomes `"syncToggles(); syncTableHeads(); syncPanels();"`.

- [ ] **Step 5: Run the page suite and the existing keyboard journeys**

Run: `python3 tests/test_frontend.py > /tmp/wp-front.log 2>&1; tail -1 /tmp/wp-front.log; grep FAIL /tmp/wp-front.log | cut -c1-200` then `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN npx playwright test -c tests/browser/playwright.config.js keyboard.spec.js --reporter=line 2>&1 | grep -vE "^\[WebServer\]" | tail -3`
Expected: `0 failed`; `4 passed` (the three windows and the touch case, now carried by the part alone).

- [ ] **Step 6: Commit**

```bash
git add static/src/shell.html static/src/js/settings.js static/src/js/page-observers.js tests/test_frontend.py
git commit -m "Settings opens and closes through the part; the window fixers are deleted, the sign-in screen keeps its own fence

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Every reachable window by keyboard

**Files:**
- Create: `tests/browser/windows.js`
- Modify: `tests/browser/keyboard.spec.js`, `tests/browser/support.js` (the read list), `tests/browser/unit/screens.test.js` (one test)

**Interfaces:**
- Consumes: `SCREENS` (`tests/browser/screens.js`), `S.prepare/watch/open/helpers` (`tests/browser/support.js`).
- Produces: `require('./windows')`: an array of `{ id, before(page, h), opener?: { sel, text? }, menu?: { sel, item } }`.

- [ ] **Step 1: Write the failing unit test** (append to `tests/browser/unit/screens.test.js`)

```js
test('the keyboard journeys name how each window is reached, and no id twice', () => {
  const WINDOWS = require('../windows');
  const ids = new Set();
  assert.ok(WINDOWS.length >= 10, 'at least ten windows beyond the three measured ones');
  for (const w of WINDOWS) {
    assert.ok(!ids.has(w.id), w.id + ' twice'); ids.add(w.id);
    assert.ok(typeof w.before === 'function', w.id + ' says how to get to its screen');
    assert.ok(!!w.opener !== !!w.menu, w.id + ' is opened by a button or by a menu item, one of the two');
  }
});
```

Run: `node --test 'tests/browser/unit/*.test.js' 2>&1 | grep -E "^✖|^ℹ (pass|fail)|Cannot find"`
Expected: FAIL, `Cannot find module '../windows'`.

- [ ] **Step 2: Write `tests/browser/windows.js`**

```js
// Every window the seeded world can open without saving anything, for the
// keyboard journeys (keyboard.spec.js), beyond the three that screens.js
// measures at three sizes. These are not measured, so they are not in the
// record. Each is reached by a button (sel, and the text it starts with) or
// by an item of a dropdown menu (the menu's button, and the item's text):
// closing a window opened from a menu gives focus back to the menu's button.
const labels = async (p, h) => { await h.nav('labels'); await h.waitText('#labels-content', '#210388'); };
const overview = async (p, h) => { await h.nav('overview'); await h.waitText('#ov-content', 'Revenue is up on last week'); };
const mail = async (p, h) => { await h.nav('mail'); await h.waitText('#mail-content', 'Artwork for the autumn tour gobos'); };
const more = item => ({ sel: '#labels-content .more-btn', item });

module.exports = [
  { id: 'pm~size-rules', before: labels, menu: more('Size rules') },
  { id: 'pm~dispatch-manifest', before: labels, menu: more('Dispatch manifest') },
  { id: 'pm~stock-usage', before: labels, menu: more('Stock usage') },
  { id: 'pm~margins', before: labels, menu: more('Margins') },
  { id: 'pm~shipping-settings', before: labels, menu: more('Shipping settings') },
  { id: 'pm~new-shipment', before: labels, opener: { sel: '#labels-content button', text: 'New shipment' } },
  { id: 'pm~edit-order', before: labels, opener: { sel: '#labels-content button[title="Change the delivery address or contact details"]' } },
  { id: 'chart', before: overview, opener: { sel: '#view-overview .chart-expand' } },
  { id: 'figure', before: overview, opener: { sel: '#view-overview .stat-open-btn' } },
  { id: 'settings', before: overview, opener: { sel: '#settings-btn' } },
  { id: 'inbox~compose', before: mail, opener: { sel: '#mail-content button', text: 'Compose' } },
];
```

- [ ] **Step 3: Rewrite `tests/browser/keyboard.spec.js`**

```js
// Windows by keyboard alone, under the app's own rule (the Guide's Design
// page; docs/DESIGN.md, Windows): a window holding work closes only by its X,
// never on Escape, so a slip of the key cannot lose what was typed. So: the
// opener is reached and pressed from the keyboard, focus moves into the
// window, Escape leaves it open, Tab stays inside it, the X pressed from the
// keyboard closes it, and focus goes back to what opened it. Nothing is saved.
// The three windows screens.js measures, then every other window the seeded
// world can open (windows.js).
const { test, expect } = require('@playwright/test');
const S = require('./support');
const SCREENS = require('./screens');
const WINDOWS = require('./windows');

const inside = () => !!document.activeElement && !!document.activeElement.closest('.modal-overlay.show .modal');

async function mark(page, sel, text) {
  await page.evaluate(({ sel, text }) => {
    const e = [...document.querySelectorAll(sel)].filter(x => x.offsetParent || x.getClientRects().length)
      .find(x => !text || (x.innerText || '').trim().startsWith(text));
    if (!e) throw new Error('no opener ' + sel + ' ' + (text || ''));
    e.setAttribute('data-suite-opener', '');
  }, { sel, text });
}

async function openByKeyboard(page, j) {
  if (j.menu) {
    await mark(page, j.menu.sel);
    const btn = page.locator('[data-suite-opener]');
    await btn.focus();
    await page.keyboard.press('Enter');
    await page.waitForSelector('.dmenu');
    for (let i = 0; i < 20; i++) {
      const t = await page.evaluate(() => ((document.activeElement && document.activeElement.innerText) || '').trim());
      if (t.startsWith(j.menu.item)) break;
      await page.keyboard.press('ArrowDown');
    }
    await page.keyboard.press('Enter');
    return;
  }
  await mark(page, j.opener.sel, j.opener.text);
  const opener = page.locator('[data-suite-opener]');
  await opener.focus();
  expect(await opener.evaluate(e => document.activeElement === e), 'the opener can be reached by keyboard').toBe(true);
  await page.keyboard.press('Enter');
}

async function journey(page, w) {
  await page.waitForSelector('.modal-overlay.show .modal');
  await expect.poll(() => page.evaluate(inside), { message: 'focus moved into the window' }).toBe(true);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  await expect(page.locator('.modal-overlay.show'), 'Escape leaves a window open: X only').toHaveCount(1);
  for (let i = 0; i < 12; i++) await page.keyboard.press('Tab');
  expect(await page.evaluate(inside), 'Tab stays inside the window').toBe(true);
  // A window that redraws its page as it closes (a CRM deal redraws the board)
  // replaces its opener; the new control carries the same data-focus-key.
  const key = await page.evaluate(() => { const o = document.querySelector('[data-suite-opener]'); return (o && o.dataset.focusKey) || ''; });
  const x = page.locator('.modal-overlay.show .modal-head :is(button[title="Close"], button[aria-label="Close"])').first();
  await x.focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('.modal-overlay.show')).toHaveCount(0);
  await expect.poll(() => page.evaluate(key => {
    const a = document.activeElement, o = document.querySelector('[data-suite-opener]');
    if (o) return a === o || o.contains(a);
    return !!key && !!a && a.dataset && a.dataset.focusKey === key;
  }, key), { message: 'focus went back to what opened the window' }).toBe(true);
  expect(w.writes, 'the window wrote something').toEqual([]);
  expect(w.errors, 'script errors').toEqual([]);
}

for (const s of SCREENS.filter(x => x.kind === 'dialog')) {
  test(`keyboard: ${s.id}`, async ({ page, context, baseURL }, info) => {
    test.skip(info.project.name !== 'laptop', 'the journeys run once, at laptop size');
    await S.prepare(context, baseURL);
    const w = S.watch(page, baseURL);
    await S.open(page, w);
    await s.before(page, S.helpers(page, w, info.project.name));
    await openByKeyboard(page, { opener: s.opener });
    await journey(page, w);
  });
}

for (const j of WINDOWS) {
  test(`keyboard: ${j.id}`, async ({ page, context, baseURL }, info) => {
    test.skip(info.project.name !== 'laptop', 'the journeys run once, at laptop size');
    await S.prepare(context, baseURL);
    const w = S.watch(page, baseURL);
    await S.open(page, w);
    await j.before(page, S.helpers(page, w, info.project.name));
    await openByKeyboard(page, j);
    await journey(page, w);
  });
}
```

then append, unchanged, the existing touch test (`test('a window opened without focus does not hand it back to a field left earlier', ...)`, from the current file).

- [ ] **Step 4: Run the units and the journeys**

Run: `node --test 'tests/browser/unit/*.test.js' 2>&1 | grep -E "^ℹ (pass|fail)"; env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN npx playwright test -c tests/browser/playwright.config.js keyboard.spec.js --reporter=line > /tmp/wp-kb.log 2>&1; grep -vE "^\[WebServer\]" /tmp/wp-kb.log | grep -E "Error:|^\s+[0-9]+ (passed|failed)|keyboard: .* ─" | head -30`
Expected: units `fail 0`. The journeys will fail on "the window wrote something" for windows that read on opening, naming the request. For each one, read the route's handler in `copilot.py`; when it only reads (the plan's check found these to read: `/api/margin` `{days}`, `/api/dispatch/manifest` `{date}`, `/api/stock-usage` `{date}`, `/api/order/edit` `{op: 'read', order_id}`, `/api/shipping/config` `{op: 'get'}`), add it to `READS` in `tests/browser/support.js`:

```js
  '/api/margin': [R(null, 'days')],
  '/api/dispatch/manifest': [R(null, 'date')],
  '/api/stock-usage': [R(null, 'date')],
  '/api/order/edit': [R('read', 'order_id')],
  '/api/shipping/config': [R('get')],
```

and any other a run names after reading its handler; a route that writes means that journey is dropped, with a ledger ruling. An opener the run cannot find ("no opener ...") is a selector to correct from the screen's own markup, also ledgered. Rerun until the journeys pass.
Expected at the end: `15 passed` (3 + 11 + the touch case), plus the existing skipped sizes.

- [ ] **Step 5: Commit**

```bash
git add tests/browser/windows.js tests/browser/keyboard.spec.js tests/browser/support.js tests/browser/unit/screens.test.js
git commit -m "Browser suite: every window the seeded world can open, by keyboard alone

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `docs/DESIGN.md`, the docs and What's new

**Files:**
- Create: `docs/DESIGN.md`
- Modify: `docs/ARCHITECTURE.md`, `data/changelog.json`, `tests/test_frontend.py` (one test)

- [ ] **Step 1: Write the failing test** (after `t_the_window_fixers_stay_gone`)

```python
@test
def t_the_design_rules_live_in_one_document():
    """The rules were spread over four dated specs, each amending the last.
    docs/DESIGN.md states them as they stand, names where every value lives,
    and lists every part; a new part is added there with its guard."""
    path = os.path.join(ROOT, "docs", "DESIGN.md")
    ok(os.path.exists(path), "docs/DESIGN.md exists")
    doc = open(path, encoding="utf-8").read()
    for heading in ("## Principles", "## Tokens", "## Recipes", "## Layout", "## Parts", "### Windows", "## Adding a part"):
        ok(heading in doc, "it has " + heading)
    ok("static/src/css/tokens.css" in doc and "static/src/js/part-dialog.js" in doc, "it names where values and parts live")
    for spec in ("2026-09-07-design-system-tokens-design.md", "2026-10-05-brand-design-system-design.md",
                 "2026-10-06-reactor-mix-design.md", "2026-10-13-panels-design.md", "2026-10-15-window-part-design.md"):
        ok(spec in doc, "it links " + spec)
    for guard in ("t_every_corner_is_a_role", "t_every_defined_token_is_read", "t_every_window_is_built_and_closed_by_the_part"):
        ok(guard in doc and ("def " + guard + "(") in open(__file__, encoding="utf-8").read(), "it names the guard " + guard)
```

Run: `ONLY=t_the_design_rules python3 tests/test_frontend.py 2>&1 | grep -E "PASS|FAIL"`
Expected: FAIL ("docs/DESIGN.md exists").

- [ ] **Step 2: Write `docs/DESIGN.md`**

```markdown
# Design

The rules Reactor's screens follow, as they stand today. Each rule came from a
dated spec, linked beside it; this page is the current word, and the specs are
the record of how each rule came to be. Values are never written here: they
live in `static/src/css/tokens.css`, and the Guide's Design page draws them
live.

## Principles

- **One source per decision.** Every value is a token in `:root`. Outside it,
  rules use `var(--...)` only; the exceptions are 0, 1px hairlines and
  percentages. Markup carries no style attributes.
  ([tokens](superpowers/specs/2026-09-07-design-system-tokens-design.md),
  [the mix](superpowers/specs/2026-10-06-reactor-mix-design.md) §3)
- **Parts own their behaviour.** A window, and from the later pieces of the
  audit's stage 3 a button, a field, a table and a panel, is built by one
  part that gives it its role, name, keys and focus. Nothing is stamped on
  afterwards. ([windows](superpowers/specs/2026-10-15-window-part-design.md))
- **Numbers first, words on request.** A figure is the biggest thing in its
  block, its label two to four words; explanations sit behind an info button
  or in the Guide. ([the mix](superpowers/specs/2026-10-06-reactor-mix-design.md) §3)
- **Teal means chosen.** The chosen tab, chooser or counter, the open row,
  links, the expected series and the one primary action on a screen.
- **Nothing drawn that the data does not support**, and no illustrations.
- **Every target fits a finger on a phone,** and hover effects only on
  devices that hover.

## Tokens

Three tiers in `static/src/css/tokens.css`: primitives (the only place a hex
value may appear), semantic tokens that components read (text, surface, line,
action, status, data, focus, shadow, type, space, corners), and component
tokens (control heights, the sidebar, the panel).
([tokens](superpowers/specs/2026-09-07-design-system-tokens-design.md),
[brand](superpowers/specs/2026-10-05-brand-design-system-design.md) §5)

The guards in `tests/test_frontend.py` hold them: no colour outside the
primitives, every `var(--x)` defined and every token read
(`t_every_defined_token_is_read`), no raw sizes in screen CSS, every `@media`
width on the scale, the script painting from tokens only
(`t_the_script_paints_from_tokens_only`), and every corner a role
(`t_every_corner_is_a_role`).

## Recipes

- **Corners are roles,** never sizes: control, field, row, card, inset, tag,
  swatch, pop, sheet; round only for a switch, a bar, a dot and the tab
  underline. No pill-shaped buttons, inputs or tabs.
- **One tag:** the tag height and corner, caption type, a tint, no border.
- **One notice:** tinted by its tone, no border, the inset corner.
- **One link:** teal, underlined in a quiet line that turns teal on hover.
- **One change chip:** a tag with the arrow and the percentage, green or red,
  and a hidden "up" or "down" for screen readers. Never colour alone.
- **Selection:** one chosen-control look and one selected-row look (the teal
  wash), the segmented thumb white on a grey well.
([brand](superpowers/specs/2026-10-05-brand-design-system-design.md) §5,
[the mix](superpowers/specs/2026-10-06-reactor-mix-design.md) §4 and §6)

## Layout

- **A grey page and white panels.** Every section of a page sits in a panel
  (the canvas, panel edge, corner, shadow, padding and gap are tokens); the
  page's header, its tabs and its notices stay on the grey.
- **Headings belong inside their panel.** A section's heading, count, info
  button and tools sit at the top inside it.
- **Tables run to their panel's edges,** their outer cells on the panel's
  inset; on a phone a row reads as two lines.
- **Panels side by side are one row** with one top and one bottom edge; when
  a pair stacks, each is as tall as its content.
- **Paper is untouched:** printed labels, A4 and courier sheets keep their own
  rules.
([panels](superpowers/specs/2026-10-13-panels-design.md))

## Parts

### Windows

`dialog()` in `static/src/js/part-dialog.js` builds every window
([spec](superpowers/specs/2026-10-15-window-part-design.md)):

- a modal dialog named by its own title;
- a window holding work has an X named Close and, with its own answers (Save,
  Cancel, Done), no other way out: never Escape, never a click outside it. A
  question or notice answered by its own buttons has no X, and the yes/no
  question (`uiConfirm`) alone answers Escape, with No;
- focus moves in as it opens and back to what opened it as it closes (to the
  redrawn control with the same `data-focus-key` when the page was redrawn);
- Tab stays inside the window on top;
- it closes through the part (`win.close()`) and nothing else.

The Settings window, written into the page, opens and closes with
`dialogShow()` and `dialogHide()`. Guards: `t_every_window_is_built_and_closed_by_the_part`,
`t_the_window_part_keeps_one_stack`, `t_the_window_fixers_stay_gone`, and the
browser suite's keyboard journeys (`tests/browser/keyboard.spec.js`).

## Adding a part

A part lives in its own section, `static/src/js/part-<name>.js`, listed in
`static/src/manifest.json`. It must:

1. build today's markup and classes, so the stylesheet does not change when
   screens move onto it;
2. own its role, name, keys and focus, so nothing is stamped on afterwards;
3. come with a page-suite guard that fails when the thing it builds is built
   by hand anywhere else;
4. come with a keyboard journey in the browser suite when it can be operated;
5. get its section under Parts here.
```

- [ ] **Step 3: Point the docs at it**

`docs/ARCHITECTURE.md`, under "How to add", after the **A page section.** paragraph, add:

```markdown
**A window.** `dialog()` (`static/src/js/part-dialog.js`); never build or
remove a `.modal-overlay` by hand (a page-suite guard fails). The design rules,
windows included, are in `docs/DESIGN.md`.
```

- [ ] **Step 4: The release note**

Insert at the top of `data/changelog.json`'s `releases`, dated the merge day (the date the PR merges; today's date if it merges today):

```json
{"date": "<merge day, YYYY-MM-DD>", "title": "Windows that behave alike", "items": [
 {"kind": "changed", "tab": null, "text": "Every window in the app is now built the same way: each one takes you into it as it opens and puts you back where you were when it closes. Nothing you see changes."}]}
```

- [ ] **Step 5: Run the tests**

Run: `ONLY=t_the_design_rules python3 tests/test_frontend.py 2>&1 | grep -E "PASS|FAIL"; ONLY=t_the_release_notes python3 tests/test_frontend.py 2>&1 | grep -E "PASS|FAIL"`
Expected: both PASS.

- [ ] **Step 6: Commit**

```bash
git add docs/DESIGN.md docs/ARCHITECTURE.md data/changelog.json tests/test_frontend.py
git commit -m "docs/DESIGN.md: the design rules as they stand, the window part first; What's new

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Full checks, the record, self-review and the PR

- [ ] **Step 1: `make check`**

Run: `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN make check > /tmp/wp-check.log 2>&1; echo $?`
Expected: `0`. The browser suite runs strictly against the record: not one count may go up. If the windows' accessibility findings went down, run `UPDATE_RECORD=1 make test-browser`, and the record's diff (only downward) goes in the PR with each change named.

- [ ] **Step 2: Self-review**

No agent is left in the budget. Review the whole branch (`git diff refactor/page-source --stat`, then every changed file) against `requesting-code-review/code-reviewer.md`'s checklist and this plan's Review Focus; for each of the 23 conversions check that the builder's remaining body still finds every name it uses (`overlay`, `modal`, `head`, `x`, `body`, `close`, `prev`, `esc`) and that no `prev` or `esc` is left referenced. Write `Final review: self-review (no agent left in the budget)` in the ledger with what was checked.

- [ ] **Step 3: The PR**

If PR #32 has merged: `git rebase --onto origin/main refactor/page-source refactor/window-part`, rerun `make check`, push, open "Every window built by one part" against `main`, bind it, and switch on Auto-fix and auto-merge. If #32 has not merged (GitHub Actions still disabled), push the branch and stop: report that the PR waits for #32, and open it once #32 is in. The body states: what the part owns; the 23 windows and Settings; what was deleted; the guards; the keyboard journeys (how many windows); the record (unchanged, or lowered with the list); the rulings; and that the review was a self-review.
