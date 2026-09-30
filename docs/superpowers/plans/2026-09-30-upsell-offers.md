# Upsell Offers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Cameron's standing rule caps sub-agents at 5 for the whole task, Task 20's reviewer included**, so a subagent-driven run uses at most 4 implementer agents (for example: Phases 1 and 2; Phase 3; Phase 4; Phases 5 to 7) plus that one reviewer, or runs inline.

**Goal:** An admin-only Upsell page in Reactor that publishes upgrade offers (for customers whose gobo orders name a poor-quality projector) and projector warranties into a Shopify thank-you and order status page extension, with the codes, warranty products, register, results and production handling behind them.

**Architecture:** Reactor keeps the offers in a JSON store, turns them into one rules document and publishes it as the shop's `$app`/`upsell` metafield, after creating the discount codes and warranty products it points at. A new checkout UI extension (two entry files, one shared `offers.js`) reads the order's lines and the rules and shows at most two cards whose buttons start a new checkout by cart link. Reactor reads the resulting orders from its orders webhook and an hourly tick.

**Tech Stack:** Python 3 / Starlette (`copilot.py`, `server.py`), the single-file SPA `static/index.html` (plain JavaScript), Shopify Admin GraphQL 2026-07 (`server.API_VERSION`), a Shopify checkout UI extension (Preact, Polaris web components `s-*`, `@shopify/ui-extensions`), node for JS tests.

**Spec:** `docs/superpowers/specs/2026-09-30-upsell-offers-design.md` (read it first; this plan argues from it).

**Checked:** an earlier draft was built end to end (Tasks 1 to 19) in a scratch worktree on 2026-09-30 and reviewed against the spec and code; every correction is folded in here, and the changed server, page and extension code was run again there (the upsell tests, the page suite, both bundles, and the type check on both targets).

## Global Constraints

- **Quote Engine:** Reactor never changes, hooks into or adds to the Quote Engine, its quotes or its draft orders. It reads orders only once the customer has paid.
- **UI copy and release notes:** British English; no em or en dashes; never setting or environment variable names; never the words "Railway" or "gizmo"; release notes never say API, webhook, callback URL or JSON.
- **Every commit touching `copilot.py` or `static/index.html`** needs a `data/changelog.json` note dated on or after that commit (`t_the_release_notes_are_ui_copy_and_keep_up_with_the_app`). Use one note for the whole feature, added in Task 1 and extended as tasks land.
- **`make check` passes before any push.** Pushing to `main` deploys to production. **Do not push** until Cameron says so.
- **Commit messages** end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Running Python:** `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python ...`.
- **Shopify writes** go only through writers defined in `server.py`, handed to `copilot.add_routes` as keywords, and never added to `COPILOT_TOOLS`.
- **Admin GraphQL version:** 2026-07 (`server.API_VERSION`). Every operation in this plan was validated against the Admin schema on 2026-09-30.
- **Extension api_version:** the current stable when built (2026-10 from 2026-10-01 17:00 UTC; never below 2026-01). Compiled bundle must stay under 64 KB compressed.
- **Rules document:** capped at 100 KB (`UPSELL_DOC_MAX`); Shopify's `json` metafield limit is 128 KB.
- **Warranty SKUs:** `WTY-<projector product id digits>-<years>`, for example `WTY-8856159682856-2`.
- **Cover** starts the day after the standard guarantee ends, counted from the covered order's fulfilment date (its order date while unfulfilled).
- **Warranty products** are created taxable, UNLISTED, `requiresShipping: false`, `tracked: false`, and put on sale in the Online Store **by Cameron by hand** (no publications permission).
- **Tests:** new server tests go in `tests/test_dispatch.py` (run one with `ONLY=<name>` after Task 1); new page and extension tests go at the **end** of `tests/test_frontend.py`, just above `if __name__ == "__main__":`, where `eq`, `_node_ok` and `MINIDOM` are defined.
- **Server tests run coroutines with `run_async(...)`, never `run(...)`:** an earlier test's `asyncio.run()` leaves the thread without a loop, so `run(...)` passes alone under `ONLY=` and fails in the full suite. Every test that calls `upsell_reset()` is decorated `@upsell_test` under `@test` (Task 9), which puts back the scope reader `upsell_reset()` replaced.
- **Page tests never crash the page suite:** `tests/test_frontend.py`'s `ok(cond, why)` needs its reason, and its `@test` decorator catches only `AssertionError`. So every `ok` has two arguments, and a test checks a function or file exists (`"function x(" in SCRIPT`, `os.path.isfile(...)`) before calling `fn_src`, `.index` or `open` on it.
- **"Run it to see it fail" steps use `tail -3`:** the FAIL line is third from last (FAIL, a blank line, the summary).
- **No literal invisible characters** in any tracked file, this plan included: `tools/sweep_tree.py` fails on them. Write them as `\u` escapes.

---

## File Structure

| File | Responsibility |
|---|---|
| `copilot.py` (new section "Upsell offers", placed just above the WebDAV section; not after `_write_loans`, since the loans code continues after it and `make env-doc` files variables under the nearest banner above them) | Stores, fixture keys, size-list scan, rules document, publish engine, `/api/upsell`, tick, order notes, register, line classification helpers |
| `copilot.py` (edits) | `add_routes` keyword, `_OPEN_API`, `LAYOUT_VIEWS`, `_label_skip_item` call sites, `run_production_labels` filter, `_sync_order_tags`/`_release_tags` refusal, orders webhook spawn, `_scheduler_loop`, `_redact_customer`, `_redact_scope`, `_redact_shop`, customer history and inbox order rows |
| `server.py` | `UPSELL_OPS`: the eight Shopify reads and writes; `REQUIRED_WRITE_SCOPES`; the `add_routes` call |
| `shopify.app.toml` | `write_discounts`, `write_products` added to scopes |
| `static/index.html` | Nav button, `view-upsell` section, `APP_VIEWS`, `setView` hook, the Upsell page, guide section, cover lines on the label history and inbox |
| `extensions/upsell-offers/` (new) | `shopify.extension.toml`, `package.json`, `src/offers.js` (pure logic, no imports), `src/Cards.jsx`, `src/ThankYou.jsx`, `src/OrderStatus.jsx` |
| `tests/upsell_spellings.json` (new) | The fixture spellings both tidies must agree on |
| `tests/test_dispatch.py`, `tests/test_frontend.py` | Tests |
| `tools/ext_bundle_check.py` (new), `Makefile`, `package-lock.json` | Bundle size check, local only when esbuild is installed (the npm workspace puts it in the root `node_modules`) |
| `data/changelog.json`, `docs/ENVIRONMENT.md` | Release note; regenerated environment reference |

---

## Phase 1: Foundations and the shared logic

### Task 1: Run one server test by name, and open the release note

**Files:**
- Modify: `tests/test_dispatch.py` (the runner loop at the end of the file)
- Modify: `data/changelog.json` (top of `releases`)

**Interfaces:**
- Produces: `ONLY=<substring> python tests/test_dispatch.py` runs only the tests whose name contains the substring. Every later task uses it.

- [ ] **Step 1: Add the filter to the runner**

Replace the start of the final loop in `tests/test_dispatch.py`:

```python
for fn in TESTS:
    # A fresh client per test, for the per-client SIGN-IN ceiling only. The
```

with:

```python
# ONLY=<part of a name> runs just the matching tests: the whole suite takes
# about five minutes, which is too long to wait for one red test.
_ONLY = os.environ.get("ONLY", "")
for fn in TESTS:
    if _ONLY and _ONLY not in fn.__name__:
        continue
    # A fresh client per test, for the per-client SIGN-IN ceiling only. The
```

- [ ] **Step 2: Check it**

Run: `ONLY=t_label_missing env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>&1 | tail -2`
Expected: `1 passed, 0 failed` (not `t_label_reprint`, which needs a label booked by earlier tests)

- [ ] **Step 3: Open the feature's release note**

Insert at the top of `"releases"` in `data/changelog.json` (keep the file's one-space indent; set `date` to the day of the commit):

```json
  {
   "date": "2026-10-01",
   "title": "Upsell offers",
   "items": [
    {
     "kind": "added",
     "text": "A new Upsell page for admins, being built: it will offer customers with an entry-level projector an upgrade, and projector buyers a warranty, on the page Shopify shows after they pay.",
     "tab": "upsell"
    }
   ]
  },
```

The `tab` value is checked against `APP_VIEWS`, which gains `upsell` in Task 15. Until then leave `"tab"` out, and add it in Task 15.

- [ ] **Step 4: Commit**

```bash
git add tests/test_dispatch.py data/changelog.json
git commit -m "Tests: ONLY runs one server test by name; open the Upsell release note

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Reactor's fixture key, pinned by a shared spelling list

**Files:**
- Create: `tests/upsell_spellings.json`
- Modify: `copilot.py` (new "Upsell offers" section, just above the WebDAV section)
- Test: `tests/test_dispatch.py`

**Interfaces:**
- Consumes: `_item_prop(li, name)`, `_item_model(li, manufacturer)`, `_strip_price(v)`, `_norm_key(v)` (existing, copilot.py ~5999, ~6049, ~5241, ~5461)
- Produces: `copilot._upsell_line_key(li: dict) -> str`, the tidied `maker|model` of a REST order line (`{"properties": [{"name", "value"}]}`), `""` when either part is missing. `tests/upsell_spellings.json`: a list of `{"why": str, "attrs": [[name, value], ...], "key": str}`.

- [ ] **Step 1: Write the spelling list**

Create `tests/upsell_spellings.json` exactly as below. Invisible characters are written as `\u` escapes: `tools/sweep_tree.py` fails the tree on literal ones.

```json
[
 {"why": "plain maker and model", "attrs": [["Manufacturer", "Chauvet DJ"], ["Model", "GoboZap"]], "key": "chauvet dj|gobozap"},
 {"why": "a price on the maker and on the model", "attrs": [["Manufacturer", "Robe - £5"], ["Model", "Spot 160 (+£12.50)"]], "key": "robe|spot 160"},
 {"why": "two prices, removed one at a time", "attrs": [["Manufacturer", "Martin £5 £2"], ["Model", "Mac 250"]], "key": "martin|mac 250"},
 {"why": "the maker's own dropdown instead of Model", "attrs": [["Manufacturer", "American DJ"], ["American DJ Models", "Ikon Profile"]], "key": "american dj|ikon profile"},
 {"why": "the maker's dropdown matched by prefix, not by word", "attrs": [["Manufacturer", "Chauvet"], ["Other Models", "X"], ["Chauvet DJ Models", "Intimidator Spot"]], "key": "chauvet|intimidator spot"},
 {"why": "no dropdown for the maker: the first other one", "attrs": [["Manufacturer", "Acme"], ["Robe Models", "Spot 160"], ["Martin Models", "Mac 250"]], "key": "acme|spot 160"},
 {"why": "an empty Model falls through to the dropdowns", "attrs": [["Manufacturer", "Robe"], ["Model", ""], ["Robe Models", "Spot 250"]], "key": "robe|spot 250"},
 {"why": "the first matching property wins even when empty", "attrs": [["Manufacturer", ""], ["manufacturer", "Robe"], ["Model", "Spot 160"]], "key": ""},
 {"why": "property names compared tidied", "attrs": [["  MANUFACTURER ", "Robe"], ["model", " Spot   160 "]], "key": "robe|spot 160"},
 {"why": "spacing, tabs, a non-breaking space and case", "attrs": [["Manufacturer", "  CHAUVET\tDJ "], ["Model", "Gobo\u00a0Zap"]], "key": "chauvet dj|gobo zap"},
 {"why": "a full-width digit in a price", "attrs": [["Manufacturer", "Robe £\uff15"], ["Model", "Spot"]], "key": "robe|spot"},
 {"why": "an Arabic-Indic digit in a price", "attrs": [["Manufacturer", "Robe £\u0665"], ["Model", "Spot"]], "key": "robe|spot"},
 {"why": "whitespace only Python counts", "attrs": [["Manufacturer", "\u0085Robe\u001f"], ["Model", "Spot\u001c160"]], "key": "robe|spot 160"},
 {"why": "a byte order mark is not whitespace to Python", "attrs": [["Manufacturer", "\ufeffRobe"], ["Model", "Spot"]], "key": "\ufeffrobe|spot"},
 {"why": "no model at all", "attrs": [["Manufacturer", "Robe"]], "key": ""},
 {"why": "Model other is kept as written", "attrs": [["Manufacturer", "Chauvet"], ["Model", "other"]], "key": "chauvet|other"},
 {"why": "a dropdown with an empty value is skipped", "attrs": [["Manufacturer", "Robe"], ["Robe Models", ""], ["Martin Models", "Mac 250"]], "key": "robe|mac 250"}
]
```

- [ ] **Step 2: Write the failing test**

Append to `tests/test_dispatch.py` (anywhere among the `@test` functions, before the runner):

```python
@test
def t_the_upsell_key_is_the_labels_own_reading_of_a_fixture():
    """The extension matches an order's fixture against spellings Reactor has
    resolved, so both must read a line identically. This list is the contract:
    the extension's own test reads the same file and must give the same keys."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "upsell_spellings.json")
    cases = json.load(open(path, encoding="utf-8"))
    ok(len(cases) >= 17, "the spelling list is all there")
    for c in cases:
        li = {"properties": [{"name": k, "value": v} for k, v in c["attrs"]]}
        eq(copilot._upsell_line_key(li), c["key"], c["why"])
```

- [ ] **Step 3: Run it to see it fail**

Run: `ONLY=t_the_upsell_key env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>&1 | tail -3`
Expected: `FAIL ... module 'copilot' has no attribute '_upsell_line_key'`

- [ ] **Step 4: Implement**

Add a new section just above the `# WebDAV: the Files store as a native Finder drive` banner in `copilot.py` (not after `_write_loans`: the loans code continues after it, and `make env-doc` files each variable under the nearest banner above it):

```python
# --------------------------------------------------------------------------
# Upsell offers
#
# Spec: docs/superpowers/specs/2026-09-30-upsell-offers-design.md
#
# Reactor keeps the offers, publishes one rules document into the shop's app
# settings, and a thank-you page extension decides on its own which card to
# show. The extension has no way to ask Reactor anything, so the fixture key
# below exists twice: here, and in extensions/upsell-offers/src/offers.js.
# tests/upsell_spellings.json holds the two to the same answers.
# --------------------------------------------------------------------------
def _upsell_line_key(li: dict) -> str:
    """The fixture a line names, tidied exactly as the labels read it:
    "maker|model", or "" when either part is missing."""
    maker = _strip_price(_item_prop(li, "Manufacturer"))
    model = _strip_price(_item_model(li, maker))
    if not maker or not model:
        return ""
    return _norm_key(maker) + "|" + _norm_key(model)
```

- [ ] **Step 5: Run it to see it pass**

Run: `ONLY=t_the_upsell_key env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>&1 | tail -2`
Expected: `1 passed, 0 failed`

- [ ] **Step 6: Commit**

```bash
git add tests/upsell_spellings.json tests/test_dispatch.py copilot.py
git commit -m "Upsell: the fixture key, read exactly as the labels read a line, pinned by a shared spelling list

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The extension's fixture key, held to the same list

**Files:**
- Create: `extensions/upsell-offers/src/offers.js`
- Test: `tests/test_frontend.py` (end of file)

**Interfaces:**
- Consumes: `tests/upsell_spellings.json` (Task 2)
- Produces (in `offers.js`, ES module, no imports): `norm(s) -> string`, `stripPrice(v) -> string`, `lineKey(attributes: {key, value}[]) -> string`

- [ ] **Step 1: Write the failing test**

Add at the end of `tests/test_frontend.py`, above `if __name__ == "__main__":`:

```python
UPSELL_JS = os.path.join(ROOT, "extensions", "upsell-offers", "src", "offers.js")


def _run_upsell_js(tail: str) -> str:
    """offers.js with a test appended, run as an ES module in bare node."""
    src = open(UPSELL_JS, encoding="utf-8").read()
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False, encoding="utf-8") as fh:
        fh.write(src + "\n" + tail)
        path = fh.name
    try:
        r = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        ok(r.returncode == 0, "offers.js did not run: " + (r.stderr or "")[:400])
        return (r.stdout or "").strip()
    finally:
        os.unlink(path)


@test
def t_the_extension_reads_a_fixture_exactly_as_reactor_does():
    """Approach B puts the fixture tidy in two places. Reactor's is pinned to
    tests/upsell_spellings.json by its own test; this pins the extension's to
    the same file, so the two cannot drift apart."""
    ok(os.path.isfile(UPSELL_JS), "the extension's logic lives in one module")
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    cases = json.load(open(os.path.join(ROOT, "tests", "upsell_spellings.json"), encoding="utf-8"))
    out = _run_upsell_js("const cases = " + json.dumps(cases) + ";\n"
                         "console.log(JSON.stringify(cases.map(c => lineKey(c.attrs.map(([key, value]) => ({ key, value }))))));")
    got = json.loads(out)
    for c, g in zip(cases, got):
        eq(g, c["key"], c["why"])
    js = open(UPSELL_JS, encoding="utf-8").read()
    ok(not re.search(r"^\s*import\b", js, re.M), "offers.js has no imports, so node can run it as it is")
```

- [ ] **Step 2: Run it to see it fail**

Run: `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_frontend.py 2>&1 | grep -E "reads_a_fixture|passed,"`
Expected: `FAIL  t_the_extension_reads_a_fixture_exactly_as_reactor_does: the extension's logic lives in one module`

- [ ] **Step 3: Implement**

Create `extensions/upsell-offers/src/offers.js`:

```js
// Upsell offers: the logic both pages share. No imports, on purpose: Reactor's
// tests run this file in bare node, and the page entries import it.
//
// The fixture tidy below must give exactly the key Reactor's _upsell_line_key
// gives (copilot.py), character for character, so it copies Python's rules
// rather than JavaScript's: Python's whitespace (which counts \x1c-\x1f and
// \x85, and not the byte order mark), Python's \d (every Unicode digit), and
// the price-suffix pattern _PRICE_SUFFIX_RE. tests/upsell_spellings.json is
// the contract both sides are tested against.
const PYWS = '\\t\\n\\x0b\\x0c\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000';
const WS_RUN = new RegExp('[' + PYWS + ']+', 'gu');
const WS_EDGE = new RegExp('^[' + PYWS + ']+|[' + PYWS + ']+$', 'gu');
const S = '[' + PYWS + ']';
const PRICE_TAIL = new RegExp('[' + PYWS + '\\-|,\\u00b7]*[\\(\\[]?' + S + '*[+\\-]?' + S + '*[\\u00a3$\\u20ac]'
  + S + '*\\p{Nd}[\\p{Nd},]*(?:\\.\\p{Nd}+)?' + S + '*[\\)\\]]?' + S + '*$', 'u');

function pyStrip(s) {
  return String(s || '').replace(WS_EDGE, '');
}

export function norm(s) {
  return pyStrip(s).toLowerCase().replace(WS_RUN, ' ');
}

export function stripPrice(v) {
  let s = pyStrip(v);
  for (;;) {
    const cut = pyStrip(s.replace(PRICE_TAIL, ''));
    if (cut === s) return s;
    s = cut;
  }
}

function prop(attrs, name) {
  const want = norm(name);
  for (const a of attrs || []) {
    if (a && typeof a === 'object' && norm(a.key) === want) return pyStrip(a.value);
  }
  return '';
}

function itemModel(attrs, maker) {
  const v = prop(attrs, 'Model');
  if (v) return v;
  const nm = norm(maker);
  let fallback = '';
  for (const a of attrs || []) {
    if (!a || typeof a !== 'object') continue;
    const name = norm(a.key);
    const val = pyStrip(a.value);
    if (!val || !(name.endsWith(' models') || name.endsWith(' model'))) continue;
    if (nm && name.startsWith(nm)) return val;
    fallback = fallback || val;
  }
  return fallback;
}

export function lineKey(attrs) {
  const maker = stripPrice(prop(attrs, 'Manufacturer'));
  const model = stripPrice(itemModel(attrs, maker));
  if (!maker || !model) return '';
  return norm(maker) + '|' + norm(model);
}
```

- [ ] **Step 4: Run it to see it pass**

Run: `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_frontend.py 2>&1 | grep -E "reads_a_fixture|passed,"`
Expected: `PASS  t_the_extension_reads_a_fixture_exactly_as_reactor_does` and `0 failed`.
If a case fails, fix `offers.js` to match Python, never the other way round: the labels already read orders the Python way.

- [ ] **Step 5: Commit**

```bash
git add extensions/upsell-offers/src/offers.js tests/test_frontend.py
git commit -m "Upsell extension: the fixture key, copying Python's rules, held to the shared spelling list

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Which cards the extension shows, and their links

**Files:**
- Modify: `extensions/upsell-offers/src/offers.js`
- Test: `tests/test_frontend.py` (end of file)

**Interfaces:**
- Consumes: `lineKey` (Task 3)
- Produces (in `offers.js`):
  - `digits(gid) -> string`: the trailing digits of a `gid://shopify/Product/123`, or of a bare id.
  - `cartLink(shopUrl, variant, qty, params: [key, value][]) -> string`
  - `chooseCards(input) -> {upgrade, warranty}`, where `input` is `{rules, lines, currency, company, orderId, orderDate, nowMs, covered, cancelled, today, shopUrl}`; `lines` are `{productId, variantId, sku, title, quantity, unitPrice, attributes}`; `upgrade` is `{id, headline, body, title, image, price, priceAfter, off, code, href}`; `warranty` is `{productId, title, qty, termsUrl, lengths: [{years, price, href}]}`.

- [ ] **Step 1: Write the failing test**

Add at the end of `tests/test_frontend.py`, above `if __name__ == "__main__":`:

```python
@test
def t_the_extension_picks_its_cards_by_the_spec():
    """Section 3 of the spec, run from the extension's own source: the guards,
    which upgrade wins, which projector gets the warranty, the window, the end
    date, the covered list, and links whose every value is encoded."""
    if not _node_ok():
        print("       (node unavailable, skipped)")
        return
    tail = r"""
const RULES = {
  v: 1, currency: 'GBP', prices_include_tax: false, tz: 'Europe/London',
  upgrades: [
    { id: 'u1', keys: ['chauvet dj|gobozap'], headline: 'H1', body: 'B1', code: 'K7Q2M9TX', off: '15%', ends: '2026-12-31',
      product: { id: '100', variant: '1001', title: '20 Watt', image: 'i.png', price: '335.00', price_after: '284.75' } },
    { id: 'u2', keys: ['chauvet dj|gobozap', 'robe|spot 160'], headline: 'H2', body: 'B2', code: 'ZZ', off: '£50', ends: '',
      product: { id: '200', variant: '2001', title: '40 Watt', image: '', price: '590.00', price_after: '540.00' } }
  ],
  warranties: {
    '100': { skus: ['P220'], title: '20 Watt', standard_years: 1,
             lengths: [{ years: 1, variant: '9001', price: '29.00' }, { years: 2, variant: '9002', price: '49.00' }] },
    '300': { skus: [], title: '80 Watt', standard_years: 1, lengths: [{ years: 1, variant: '9101', price: '79.00' }] }
  },
  warranty_window_days: 30, terms_url: 'https://x.test/terms'
};
const gobo = (maker, model) => ({ productId: 'gid://shopify/Product/5', variantId: '', sku: '', title: 'Gobo', quantity: 1,
  unitPrice: 49, attributes: [{ key: 'Manufacturer', value: maker }, { key: 'Model', value: model }] });
const proj = (pid, price, qty, sku) => ({ productId: pid ? 'gid://shopify/Product/' + pid : '', variantId: '', sku: sku || '',
  title: 'Projector', quantity: qty || 1, unitPrice: price, attributes: [] });
const base = { rules: RULES, currency: 'GBP', company: false, orderId: '777', orderDate: '2026-10-01T10:00:00Z',
  nowMs: Date.parse('2026-10-02T10:00:00Z'), covered: null, cancelled: false, today: '2026-10-02', shopUrl: 'https://shop.test/' };
const run = (o) => chooseCards(Object.assign({}, base, o));
const out = {};
out.first = run({ lines: [gobo('Chauvet DJ', 'GoboZap')] }).upgrade;
out.second = run({ lines: [gobo('Robe', 'Spot 160')] }).upgrade;
out.ended = run({ lines: [gobo('Chauvet DJ', 'GoboZap')], today: '2027-01-01' }).upgrade;
out.hasRecommended = run({ lines: [gobo('Robe', 'Spot 160'), proj('200', 590)] }).upgrade;
out.hasProjector = run({ lines: [gobo('Chauvet DJ', 'GoboZap'), proj('300', 1095)] }).upgrade;
out.company = run({ lines: [gobo('Chauvet DJ', 'GoboZap')], company: true });
out.euro = run({ lines: [gobo('Chauvet DJ', 'GoboZap')], currency: 'EUR' });
out.cancelled = run({ lines: [proj('100', 335)], cancelled: true });
out.norules = run({ lines: [proj('100', 335)], rules: null });
out.warranty = run({ lines: [proj('100', 335, 2), proj('300', 1095)] }).warranty;
out.bySku = run({ lines: [proj('', 330, 1, 'P220')] }).warranty;
out.covered = run({ lines: [proj('100', 335), proj('300', 1095)], covered: ['300'] }).warranty;
out.late = run({ lines: [proj('100', 335)], orderDate: '2026-08-01T10:00:00Z' }).warranty;
out.link = cartLink('https://shop.test/', '9001', 2, [['attributes[reactor_after]', '#12'], ['discount', ''], ['x', 'a b&c']]);
out.digits = [digits('gid://shopify/Product/8856159682856'), digits('42'), digits('')];
console.log(JSON.stringify(out));
"""
    got = json.loads(_run_upsell_js(tail))
    eq(got["first"]["id"], "u1", "the first listed upgrade whose key matches wins")
    eq(got["first"]["href"],
       "https://shop.test/cart/1001:1?discount=K7Q2M9TX&attributes%5Breactor_offer%5D=u1&attributes%5Breactor_after%5D=777",
       "the upgrade link: variant, code, the offer and the covered order, every value encoded")
    eq((got["first"]["price"], got["first"]["priceAfter"]), ("335.00", "284.75"), "prices before and after the code")
    eq(got["second"]["id"], "u2", "another key of a later upgrade")
    eq(got["ended"]["id"], "u2", "past its end date an upgrade is skipped, and the next that matches shows")
    eq(got["hasRecommended"], None, "no upgrade when the order already has the recommended projector")
    eq(got["hasProjector"], None, "no upgrade when the order has any projector with a warranty")
    eq(got["company"], {"upgrade": None, "warranty": None}, "nothing for a company buyer")
    eq(got["euro"], {"upgrade": None, "warranty": None}, "nothing in another currency")
    eq(got["cancelled"], {"upgrade": None, "warranty": None}, "nothing on a cancelled order")
    eq(got["norules"], {"upgrade": None, "warranty": None}, "nothing without rules")
    w = got["warranty"]
    eq(w["productId"], "300", "the warranty is for the dearest projector on the order")
    eq(w["qty"], 1, "for as many units as that line has")
    eq([L["years"] for L in w["lengths"]], [1], "its lengths")
    eq(w["lengths"][0]["href"],
       "https://shop.test/cart/9101:1?attributes%5Breactor_offer%5D=warranty&attributes%5Breactor_after%5D=777",
       "a warranty link carries no code")
    eq(got["bySku"]["productId"], "100", "a quoted line with no product is found by its SKU")
    eq(got["covered"]["productId"], "100", "a covered projector is not offered again")
    eq(got["late"], None, "no warranty past the window")
    eq(got["link"], "https://shop.test/cart/9001:2?attributes%5Breactor_after%5D=%2312&x=a%20b%26c",
       "empty values are left out and the rest encoded")
    eq(got["digits"], ["8856159682856", "42", ""], "ids are compared as digits")
```

- [ ] **Step 2: Run it to see it fail**

Run: `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_frontend.py 2>&1 | grep -E "picks_its_cards|passed,"`
Expected: `FAIL ... offers.js did not run: ... chooseCards is not defined`

- [ ] **Step 3: Implement**

Append to `extensions/upsell-offers/src/offers.js`:

```js
export function digits(gid) {
  const m = String(gid || '').match(/(\d+)\s*$/);
  return m ? m[1] : '';
}

function amount(v) {
  const n = Number(v);
  return isFinite(n) ? n : 0;
}

export function cartLink(shopUrl, variant, qty, params) {
  const base = String(shopUrl || '').replace(/\/+$/, '');
  const q = (params || [])
    .filter(([, v]) => v !== '' && v != null)
    .map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(String(v)))
    .join('&');
  return base + '/cart/' + encodeURIComponent(String(variant)) + ':' + Math.max(1, Number(qty) || 1)
    + (q ? '?' + q : '');
}

// Spec section 3. Anything unexpected shows nothing: a shopper never sees an
// error from this, only an offer or no offer.
export function chooseCards(input) {
  const out = { upgrade: null, warranty: null };
  const r = input && input.rules;
  if (!r || typeof r !== 'object' || !input.shopUrl) return out;
  if (input.cancelled || input.company) return out;
  if (r.currency && input.currency !== r.currency) return out;
  const lines = Array.isArray(input.lines) ? input.lines : [];
  const warranties = r.warranties && typeof r.warranties === 'object' ? r.warranties : {};
  const bySku = {};
  for (const pid of Object.keys(warranties)) {
    for (const s of warranties[pid].skus || []) bySku[String(s)] = pid;
  }
  const projectorOf = (ln) => {
    const pid = digits(ln.productId);
    if (pid && warranties[pid]) return pid;
    return ln.sku && bySku[ln.sku] ? bySku[ln.sku] : '';
  };
  const after = String(input.orderId || '');

  const hasProjector = lines.some((ln) => projectorOf(ln));
  if (!hasProjector) {
    const keys = new Set(lines.map((ln) => lineKey(ln.attributes)).filter(Boolean));
    for (const u of Array.isArray(r.upgrades) ? r.upgrades : []) {
      if (!u || !u.product || !Array.isArray(u.keys)) continue;
      if (u.ends && input.today && input.today > u.ends) continue;
      if (lines.some((ln) => digits(ln.productId) === String(u.product.id))) continue;
      if (!u.keys.some((k) => keys.has(k))) continue;
      out.upgrade = {
        id: u.id, headline: u.headline || '', body: u.body || '', title: u.product.title || '',
        image: u.product.image || '', price: u.product.price || '', priceAfter: u.product.price_after || '',
        off: u.off || '', code: u.code || '',
        href: cartLink(input.shopUrl, u.product.variant, 1,
          [['discount', u.code || ''], ['attributes[reactor_offer]', u.id], ['attributes[reactor_after]', after]]),
      };
      break;
    }
  }

  const windowDays = Number(r.warranty_window_days) || 0;
  const t = Date.parse(input.orderDate || '');
  const age = isNaN(t) ? null : Math.floor((Number(input.nowMs) - t) / 86400000);
  if (windowDays > 0 && age !== null && age <= windowDays) {
    const covered = new Set((input.covered || []).map(String));
    let best = null;
    for (const ln of lines) {
      const pid = projectorOf(ln);
      if (!pid || covered.has(pid)) continue;
      const w = warranties[pid];
      if (!w || !Array.isArray(w.lengths) || !w.lengths.length) continue;
      if (!best || amount(ln.unitPrice) > amount(best.ln.unitPrice)) best = { ln, pid, w };
    }
    if (best) {
      const qty = Math.max(1, Number(best.ln.quantity) || 1);
      out.warranty = {
        productId: best.pid, title: best.w.title || best.ln.title || '', qty, termsUrl: r.terms_url || '',
        lengths: best.w.lengths.map((L) => ({
          years: L.years, price: L.price,
          href: cartLink(input.shopUrl, L.variant, qty,
            [['attributes[reactor_offer]', 'warranty'], ['attributes[reactor_after]', after]]),
        })),
      };
    }
  }
  return out;
}
```

- [ ] **Step 4: Run it to see it pass**

Run: `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_frontend.py 2>&1 | grep -E "picks_its_cards|reads_a_fixture|passed,"`
Expected: both `PASS`, `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add extensions/upsell-offers/src/offers.js tests/test_frontend.py
git commit -m "Upsell extension: which cards show and their cart links, by the spec's rules

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Phase 2: Reactor's stores, fixture scan and rules document

### Task 5: The two stores

**Files:**
- Modify: `copilot.py` (Upsell section)
- Modify: `tests/test_dispatch.py` (the harness `os.environ.update({...})` block near the top)
- Modify: `docs/ENVIRONMENT.md` (regenerated)
- Test: `tests/test_dispatch.py`

**Interfaces:**
- Produces:
  - `UPSELL_PATH`, `WARRANTY_PATH` (module constants)
  - `_upsell_default() -> dict`, `_load_upsell() -> dict`, `_write_upsell(d) -> None`
  - `_warranty_default() -> dict`, `_load_warranties() -> dict`, `_write_warranties(d) -> None` (owner-only)
  - Upsell store shape: `{"offers": [], "warranties": {}, "settings": {"window_days": 30, "terms_url": "", "vat_note": "", "xero_account": "", "trial_projector_id": ""}, "made": {"codes": {}, "warranty_products": {}}, "scan": {}, "scan_at": "", "published": {"at": "", "by": "", "fingerprint": "", "config": None, "doc": None, "trial": False}, "drift": [], "problems": [], "tick_at": "", "last_error": ""}`
  - Offer shape: `{"id", "row_id", "row": {"manufacturer", "model"}, "product_id", "off_kind": "percent"|"amount", "off", "ends", "code", "headline", "body", "on"}`
  - Warranty config shape (keyed by projector product id digits): `{"on", "standard_years", "skus": [], "lengths": {"1": {"on", "price"}, "2": {...}, "3": {...}}}`
  - Register shape: `{"sales": {<warranty order id>: {...}}, "results": {<order id>: {...}}}` (fields in Task 12)

- [ ] **Step 1: Point the harness at scratch copies**

In `tests/test_dispatch.py`, inside `os.environ.update({...})`, after `"LOANS_PATH": SCRATCH + "/loans.json",` add:

```python
    "UPSELL_PATH": SCRATCH + "/upsell.json",
    "WARRANTY_PATH": SCRATCH + "/warranties.json",
```

- [ ] **Step 2: Write the failing test**

```python
@test
def t_the_upsell_stores_start_empty_and_keep_what_is_written():
    """Offers and the warranty register are stores like any other: a default
    when there is no file, a round trip, the register owner-only because it
    names customers, and a broken file never written over."""
    for p in (copilot.UPSELL_PATH, copilot.WARRANTY_PATH):
        try:
            os.remove(p)
        except FileNotFoundError:
            pass
        copilot._forget_store(p)
        copilot._poisoned_stores.discard(p)
    d = copilot._load_upsell()
    eq(d["offers"], [], "no offers yet")
    eq(d["settings"]["window_days"], 30, "a 30-day warranty window by default")
    d["offers"].append({"id": "u1"})
    d["settings"]["terms_url"] = "https://x.test/terms"
    copilot._write_upsell(d)
    d2 = copilot._load_upsell()
    eq(d2["offers"], [{"id": "u1"}])
    eq((d2["settings"]["window_days"], d2["settings"]["terms_url"]), (30, "https://x.test/terms"),
       "a saved setting keeps the defaults beside it")
    w = copilot._load_warranties()
    eq(w, {"sales": {}, "results": {}})
    w["sales"]["9"] = {"email": "a@b.test"}
    copilot._write_warranties(w)
    eq(copilot._load_warranties()["sales"]["9"]["email"], "a@b.test")
    eq(os.stat(copilot.WARRANTY_PATH).st_mode & 0o777, 0o600,
       "the register names customers, so it is owner-only")
    open(copilot.UPSELL_PATH, "w").write("{broken")
    copilot._forget_store(copilot.UPSELL_PATH)
    copilot._load_upsell()
    try:
        copilot._write_upsell(copilot._upsell_default())
        ok(False, "a broken store was written over")
    except copilot.StoreUnwritable:
        pass
    os.remove(copilot.UPSELL_PATH)
    copilot._forget_store(copilot.UPSELL_PATH)
    copilot._poisoned_stores.discard(copilot.UPSELL_PATH)
    os.remove(copilot.WARRANTY_PATH)
    copilot._forget_store(copilot.WARRANTY_PATH)
```

- [ ] **Step 3: Run it to see it fail**

Run: `ONLY=t_the_upsell_stores env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>&1 | tail -3`
Expected: `FAIL ... no attribute 'UPSELL_PATH'`

- [ ] **Step 4: Implement**

Add to the Upsell section of `copilot.py`, above `_upsell_line_key`:

```python
UPSELL_PATH = os.environ.get("UPSELL_PATH", "/data/upsell.json")
WARRANTY_PATH = os.environ.get("WARRANTY_PATH", "/data/warranties.json")


def _upsell_default() -> dict:
    return {"offers": [], "warranties": {},
            "settings": {"window_days": 30, "terms_url": "", "vat_note": "", "xero_account": "",
                         "trial_projector_id": ""},
            "made": {"codes": {}, "warranty_products": {}},
            "scan": {}, "scan_at": "",
            "published": {"at": "", "by": "", "fingerprint": "", "config": None, "doc": None,
                          "trial": False},
            "drift": [], "problems": [], "tick_at": "", "last_error": ""}


def _load_upsell() -> dict:
    """The offers, the ids of what Reactor made in Shopify, and what was last
    published. A key missing from the file keeps its default."""
    d = _load_json_store(UPSELL_PATH, "upsell", None)
    base = _upsell_default()
    if not isinstance(d, dict):
        return base
    for k, v in base.items():
        got = d.get(k)
        if isinstance(v, dict) and isinstance(got, dict):
            v.update(got)
        elif isinstance(v, list) and isinstance(got, list):
            base[k] = got
        elif isinstance(v, str) and isinstance(got, str):
            base[k] = got
    return base


def _write_upsell(d: dict) -> None:
    _write_json_store(UPSELL_PATH, "upsell", d)


def _warranty_default() -> dict:
    return {"sales": {}, "results": {}}


def _load_warranties() -> dict:
    d = _load_json_store(WARRANTY_PATH, "warranties", None)
    base = _warranty_default()
    if isinstance(d, dict):
        for k in base:
            if isinstance(d.get(k), dict):
                base[k] = d[k]
    return base


def _write_warranties(d: dict) -> None:
    """Owner-only: each sale carries the customer's name and email."""
    _write_json_store(WARRANTY_PATH, "warranties", d, private=True)
```

- [ ] **Step 5: Run it to see it pass, and regenerate the environment reference**

Run: `ONLY=t_the_upsell_stores env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>&1 | tail -2`
Expected: `1 passed, 0 failed`

Run: `make env-doc && git diff docs/ENVIRONMENT.md`
Expected: one new section, `## copilot.py - Upsell offers`, holding exactly two rows, `UPSELL_PATH` and `WARRANTY_PATH`, and nothing else moved. If other variables moved into it, the section banner is in the wrong place (Task 2 Step 4).

Run: `ONLY=t_backup_is_exhaustive env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>&1 | grep -cE "UPSELL_PATH|WARRANTY_PATH"`
Expected: `0`: both stores sit at the top of the data folder, so the backup already carries them. (Run alone, this test still fails for six older stores, such as `MEMORY_PATH`, that only earlier tests point at the scratch folder; it passes in the full suite.)

- [ ] **Step 6: Commit**

```bash
git add copilot.py tests/test_dispatch.py docs/ENVIRONMENT.md
git commit -m "Upsell: the offers store and the owner-only warranty register

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Which fixtures customers use, and which spellings stand for a row

**Files:**
- Modify: `copilot.py` (Upsell section)
- Test: `tests/test_dispatch.py`

**Interfaces:**
- Consumes: `_upsell_line_key` (Task 2); `_gobo_lookup(manufacturer, model, cache) -> (entry, reason)`, `_gobo_sizes()` (existing; `cache["excludes"]` is a set of `(norm maker, norm model)` rulings)
- Produces:
  - `_upsell_row_id(manufacturer, model_cell) -> str`
  - `_upsell_clean_row(maker, model, cache) -> Optional[dict]`: the size-list entry, only when there is no doubt
  - `_upsell_scan(orders, cache) -> {row_id: {"row": {"manufacturer", "model"}, "keys": [sorted], "customers": int, "checkout": int, "last": iso}}`: `checkout` counts the customers with at least one matching order paid through the online checkout (any payment gateway other than `manual`), who are the ones the thank-you page reaches
  - `_upsell_fixture_ranking(scan, limit=200) -> [{"row_id", "manufacturer", "model", "customers", "last", "spellings"}]`

- [ ] **Step 1: Write the failing test**

```python
@test
def t_upsell_spellings_count_only_when_the_size_list_has_no_doubt():
    """A spelling becomes a key only when the size list places it on one row
    without a doubt: not a not-a-gobo ruling (the lookup alone would say Rogue
    R2 Spot for the ruled-out Rogue R2 Spot Metal), and for a value naming
    several models, every part on the same row (the lookup answers Spot 160
    for 'Spot 160, Spot 250' and for 'Spot 160 / VL4000 Beamwash')."""
    c = copilot._gobo_sizes()
    row = copilot._upsell_clean_row
    e = row("Robe", "Spot 160", c)
    eq((e["manufacturer"], e["model"]), ("Robe", "Spot 160"), "a clean spelling stands for its row")
    eq(row("Chauvet", "Rogue R2 Spot Metal", c), None, "ruled not a gobo: never a fixture")
    eq(row("Robe", "Spot 160, Spot 250", c), None, "a value naming two rows counts for neither")
    eq(row("Robe", "Spot 160 / VL4000 Beamwash", c), None, "a part the size list cannot place spoils the value")
    eq(row("Chauvet", "other", c), None, "Model: other matches nothing")

    def li(mk, md):
        return {"properties": [{"name": "Manufacturer", "value": mk}, {"name": "Model", "value": md}]}
    orders = [
        {"id": 1, "created_at": "2026-09-01T10:00:00Z", "customer": {"id": 11},
         "payment_gateway_names": ["shopify_payments"],
         "line_items": [li("Robe", "Spot 160"), li("ETC", "Source Four Junior")]},
        {"id": 2, "created_at": "2026-09-05T10:00:00Z", "customer": {"id": 12},
         "payment_gateway_names": ["manual"],
         "line_items": [li("ROBE", " spot  160 ")]},
        {"id": 3, "created_at": "2026-09-06T10:00:00Z", "customer": {"id": 11},
         "line_items": [li("Robe", "Spot 160 - £5")]},
        {"id": 4, "created_at": "2026-09-07T10:00:00Z", "customer": {"id": 13},
         "cancelled_at": "2026-09-08T00:00:00Z", "line_items": [li("Robe", "Spot 160")]},
        {"id": 5, "created_at": "2026-09-08T10:00:00Z", "customer": {"id": 14},
         "line_items": [li("Chauvet", "Rogue R2 Spot Metal")]},
    ]
    scan = copilot._upsell_scan(orders, c)
    rid = copilot._upsell_row_id("Robe", "Spot 160")
    eq(scan[rid]["keys"], ["robe|spot 160"], "every spelling of the row, tidied")
    eq(scan[rid]["customers"], 2, "two customers use it; a cancelled order does not count")
    eq(scan[rid]["checkout"], 1, "one of them paid through the online checkout; the other was marked paid by staff")
    eq(scan[rid]["last"], "2026-09-06T10:00:00Z")
    ok(copilot._upsell_row_id("Chauvet", "Rogue R2 Spot") not in scan, "the ruled-out spelling adds nothing")
    rank = copilot._upsell_fixture_ranking(scan)
    eq([r["manufacturer"] for r in rank], ["Robe", "ETC"], "ranked by customers")
    eq((rank[0]["model"], rank[0]["spellings"]), ("Spot 160", 1))
    ok(all("@" not in json.dumps(v) for v in scan.values()), "no customer's address is kept")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_upsell_spellings env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>&1 | tail -3`
Expected: `FAIL ... no attribute '_upsell_clean_row'`

- [ ] **Step 3: Implement**

Add below `_upsell_line_key`:

```python
def _upsell_row_id(manufacturer: str, model_cell: str) -> str:
    """A size-list row, by its maker and its whole model cell."""
    return _norm_key(manufacturer) + "|" + _norm_key(model_cell)


def _upsell_clean_row(maker: str, model: str, cache: dict) -> Optional[dict]:
    """The size-list row a fixture spelling stands for, only when there is no
    doubt. A wrong key would show a customer an upgrade from a projector they
    do not own, so every doubt means no key."""
    if not maker or not model:
        return None
    if (_norm_key(maker), _norm_key(model)) in (cache.get("excludes") or set()):
        return None
    entry, reason = _gobo_lookup(maker, model, cache)
    if not entry or reason:
        return None
    rid = _upsell_row_id(entry.get("manufacturer", ""), entry.get("model", ""))
    parts = [p.strip() for p in re.split(r"[,/]", model) if p.strip()]
    if len(parts) > 1:
        for p in parts:
            e2, r2 = _gobo_lookup(maker, p, cache)
            if not e2 or r2 or _upsell_row_id(e2.get("manufacturer", ""), e2.get("model", "")) != rid:
                return None
    return entry


def _upsell_scan(orders: list, cache: dict) -> dict:
    """{row id: {row, keys, customers, last}} from the fixtures gobo orders
    name. Counts customers, never keeps who they are."""
    acc: dict = {}
    for o in orders or []:
        if o.get("cancelled_at"):
            continue
        who = str((o.get("customer") or {}).get("id") or o.get("email") or "").strip().lower()
        at = str(o.get("created_at") or "")
        for li in o.get("line_items") or []:
            key = _upsell_line_key(li)
            if not key:
                continue
            maker = _strip_price(_item_prop(li, "Manufacturer"))
            model = _strip_price(_item_model(li, maker))
            entry = _upsell_clean_row(maker, model, cache)
            if not entry:
                continue
            rid = _upsell_row_id(entry["manufacturer"], entry["model"])
            a = acc.setdefault(rid, {"row": {"manufacturer": entry["manufacturer"], "model": entry["model"]},
                                     "keys": set(), "who": set(), "online": set(), "last": ""})
            a["keys"].add(key)
            if who:
                a["who"].add(who)
                gateways = [str(g).strip().lower() for g in (o.get("payment_gateway_names") or [])]
                if any(g and g != "manual" for g in gateways):
                    a["online"].add(who)
            a["last"] = max(a["last"], at)
    return {rid: {"row": a["row"], "keys": sorted(a["keys"]), "customers": len(a["who"]),
                  "checkout": len(a["online"]), "last": a["last"]}
            for rid, a in acc.items()}


def _upsell_fixture_ranking(scan: dict, limit: int = 200) -> list:
    rows = [{"row_id": rid, "manufacturer": v["row"]["manufacturer"], "model": v["row"]["model"],
             "customers": v["customers"], "last": v["last"], "spellings": len(v["keys"])}
            for rid, v in (scan or {}).items()]
    rows.sort(key=lambda r: (-r["customers"], r["manufacturer"].lower(), r["model"].lower()))
    return rows[:limit]
```

- [ ] **Step 4: Run it to see it pass**

Run: `ONLY=t_upsell_spellings env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>&1 | tail -2`
Expected: `1 passed, 0 failed`

- [ ] **Step 5: Commit**

```bash
git add copilot.py tests/test_dispatch.py
git commit -m "Upsell: the fixtures customers use, and spellings that count only when the size list has no doubt

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: The rules document

**Files:**
- Modify: `copilot.py` (Upsell section)
- Test: `tests/test_dispatch.py`

**Interfaces:**
- Consumes: store shapes (Task 5), scan keys (Task 6)
- Produces:
  - `UPSELL_DOC_MAX = 100 * 1024`, `UPSELL_TRIAL_KEY = "reactor trial|trial"`
  - `_gid_digits(v) -> str`
  - `_upsell_money(v) -> str` ("335.00" or "")
  - `_upsell_price_after(price, kind, off) -> str`, `_upsell_off_text(kind, off) -> str`
  - `_upsell_build_doc(cfg, keys, facts, made, *, trial=False, now=None) -> (doc, problems)` where `cfg = {"offers", "warranties", "settings"}`, `keys = {row_id: [keys]}`, `facts = {product digits: {"status", "on_sale", "title", "image", "variants": [{"id", "sku", "price", "available"}]}}` (the shape `UPSELL_OPS["product_facts"]` returns in Task 8), `made = store["made"]`; `problems = [{"offer"|"warranty": id, "text": str}]`
  - `_upsell_doc_json(doc) -> str`, `_upsell_fingerprint(doc) -> str`

- [ ] **Step 1: Write the failing test**

```python
UPSELL_CFG = {
    "offers": [
        {"id": "u1", "row_id": "robe|spot 160", "row": {"manufacturer": "Robe", "model": "Spot 160"},
         "product_id": "100", "off_kind": "percent", "off": "15", "ends": "2026-12-31",
         "code": "K7Q2M9TX", "headline": "H", "body": "B", "on": True},
        {"id": "u2", "row_id": "robe|spot 250", "row": {"manufacturer": "Robe", "model": "Spot 250"},
         "product_id": "200", "off_kind": "amount", "off": "50", "ends": "",
         "code": "ZZZZZZ", "headline": "H2", "body": "", "on": True},
        {"id": "u3", "row_id": "robe|spot 160", "row": {"manufacturer": "Robe", "model": "Spot 160"},
         "product_id": "300", "off_kind": "percent", "off": "10", "ends": "",
         "code": "OFFOFF", "headline": "", "body": "", "on": False}],
    "warranties": {
        "100": {"on": True, "standard_years": 1, "skus": ["P220"],
                "lengths": {"1": {"on": True, "price": "29"}, "2": {"on": True, "price": "49"},
                            "3": {"on": False, "price": "69"}}},
        "300": {"on": True, "standard_years": 1, "skus": [],
                "lengths": {"1": {"on": True, "price": "79"}}}},
    "settings": {"window_days": 30, "terms_url": "https://x.test/terms",
                 "vat_note": "Our own promise, standard rated", "xero_account": "4010"}}
UPSELL_FACTS = {
    "100": {"status": "ACTIVE", "on_sale": True, "title": "20 Watt", "image": "i.png",
            "variants": [{"id": "1001", "sku": "P220", "price": "335.00", "available": True}]},
    "200": {"status": "DRAFT", "on_sale": False, "title": "40 Watt", "image": "",
            "variants": [{"id": "2001", "sku": "", "price": "590.00", "available": True}]},
    "300": {"status": "ACTIVE", "on_sale": True, "title": "80 Watt", "image": "",
            "variants": [{"id": "3001", "sku": "", "price": "1095.00", "available": True}]},
    "9100": {"status": "UNLISTED", "on_sale": True, "title": "Extended warranty, 20 Watt", "image": "",
             "variants": [{"id": "9001", "sku": "WTY-100-1", "price": "29.00", "available": True},
                          {"id": "9002", "sku": "WTY-100-2", "price": "49.00", "available": True}]},
    "9300": {"status": "UNLISTED", "on_sale": False, "title": "Extended warranty, 80 Watt", "image": "",
             "variants": [{"id": "9101", "sku": "WTY-300-1", "price": "79.00", "available": True}]}}
UPSELL_MADE = {
    "codes": {"u1": {"id": "gid://shopify/DiscountCodeNode/1", "code": "K7Q2M9TX"},
              "u2": {"id": "gid://shopify/DiscountCodeNode/2", "code": "ZZZZZZ"}},
    "warranty_products": {
        "100": {"id": "gid://shopify/Product/9100",
                "variants": {"1": "gid://shopify/ProductVariant/9001", "2": "gid://shopify/ProductVariant/9002"}},
        "300": {"id": "gid://shopify/Product/9300", "variants": {"1": "gid://shopify/ProductVariant/9101"}}}}


@test
def t_the_rules_document_carries_only_what_can_be_sold():
    """Spec section 2: an offer reaches the document only when it is on, its
    projector is active, on sale and available, its code exists and a
    customer's order names its fixture; a warranty only when its product is on
    sale and the launch checks are recorded. Everything left out is said."""
    keys = {"robe|spot 160": ["robe|spot 160"], "robe|spot 250": []}
    doc, problems = copilot._upsell_build_doc(UPSELL_CFG, keys, UPSELL_FACTS, UPSELL_MADE,
                                              now="2026-10-01T10:00:00+00:00")
    eq([u["id"] for u in doc["upgrades"]], ["u1"], "only the offer that is on, on sale and has spellings")
    u = doc["upgrades"][0]
    eq(u["product"], {"id": "100", "variant": "1001", "title": "20 Watt", "image": "i.png",
                      "price": "335.00", "price_after": "284.75"})
    eq((u["code"], u["off"], u["ends"], u["keys"]), ("K7Q2M9TX", "15%", "2026-12-31", ["robe|spot 160"]))
    eq(list(doc["warranties"]), ["100"], "the 80 Watt's warranty product is not on sale yet")
    eq(doc["warranties"]["100"], {"skus": ["P220"], "title": "20 Watt", "standard_years": 1,
                                  "lengths": [{"years": 1, "variant": "9001", "price": "29.00"},
                                              {"years": 2, "variant": "9002", "price": "49.00"}]})
    eq((doc["v"], doc["currency"], doc["prices_include_tax"], doc["tz"], doc["warranty_window_days"],
        doc["terms_url"], doc["published"]),
       (1, "GBP", False, "Europe/London", 30, "https://x.test/terms", "2026-10-01T10:00:00+00:00"))
    texts = [p["text"] for p in problems]
    ok(any("Projector unavailable" in t for t in texts), "the draft projector is said")
    ok(any("Put on sale in Shopify first" in t for t in texts), "the warranty not on sale is said")
    cfg2 = json.loads(json.dumps(UPSELL_CFG))
    cfg2["settings"]["vat_note"] = ""
    doc2, problems2 = copilot._upsell_build_doc(cfg2, keys, UPSELL_FACTS, UPSELL_MADE)
    eq(doc2["warranties"], {}, "no warranty before the VAT answer and the Xero code are recorded")
    ok(any("VAT" in p["text"] for p in problems2), "and the page says why")
    cfg3 = json.loads(json.dumps(UPSELL_CFG))
    cfg3["settings"]["trial_projector_id"] = "100"
    doc3, _ = copilot._upsell_build_doc(cfg3, keys, UPSELL_FACTS, UPSELL_MADE, trial=True)
    eq([x["keys"] for x in doc3["upgrades"]], [[copilot.UPSELL_TRIAL_KEY]], "a trial matches only the staff fixture")
    eq((doc3.get("trial"), list(doc3["warranties"])), (True, ["100"]), "and only the staff test projector's warranty")
    doc4, problems4 = copilot._upsell_build_doc(UPSELL_CFG, keys, UPSELL_FACTS, UPSELL_MADE, trial=True)
    eq(doc4["warranties"], {}, "no staff test projector chosen: no warranty in a trial, since a real "
                               "projector's warranty would reach every real buyer of it")
    ok(any("staff test projector" in p["text"] for p in problems4), "and the page says why")
    ok(len(copilot._upsell_doc_json(doc).encode("utf-8")) < copilot.UPSELL_DOC_MAX, "a small document is under the cap")
    later = dict(doc, published="2026-10-02T00:00:00+00:00")
    eq(copilot._upsell_fingerprint(doc), copilot._upsell_fingerprint(later),
       "the publish time alone does not make a document new")
    eq(copilot._upsell_off_text("amount", "50"), "£50.00")
    eq(copilot._upsell_price_after("590.00", "amount", "50"), "540.00")
    eq(copilot._upsell_price_after("40.00", "amount", "50"), "0.00", "never below nothing")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_the_rules_document env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>&1 | tail -3`
Expected: `FAIL ... no attribute '_upsell_build_doc'`

- [ ] **Step 3: Implement**

Add below `_upsell_fixture_ranking` (`hashlib` is already imported in `copilot.py`):

```python
UPSELL_DOC_MAX = 100 * 1024          # Shopify's json metafield limit is 128 KB
UPSELL_TRIAL_KEY = "reactor trial|trial"


def _gid_digits(v) -> str:
    m = re.search(r"(\d+)\s*$", str(v or ""))
    return m.group(1) if m else ""


def _upsell_money(v) -> str:
    try:
        return "%.2f" % round(float(str(v).replace(",", "").replace("£", "")) + 1e-9, 2)
    except (TypeError, ValueError):
        return ""


def _upsell_price_after(price, kind: str, off) -> str:
    try:
        p, o = float(price), float(off)
    except (TypeError, ValueError):
        return ""
    if kind == "percent":
        return _upsell_money(p * (1 - o / 100.0))
    return _upsell_money(max(0.0, p - o))


def _upsell_off_text(kind: str, off) -> str:
    if kind == "percent":
        return _upsell_money(off).rstrip("0").rstrip(".") + "%"
    return "£" + _upsell_money(off)


def _upsell_build_doc(cfg: dict, keys: dict, facts: dict, made: dict, *,
                      trial: bool = False, now: Optional[str] = None) -> tuple:
    """(doc, problems): spec section 2. Only what can be sold goes in; every
    offer or warranty left out is said, so the page can say why."""
    problems: list = []
    settings = cfg.get("settings") or {}
    doc = {"v": 1, "published": now or datetime.now(timezone.utc).isoformat(),
           "currency": "GBP", "prices_include_tax": False, "tz": "Europe/London",
           "upgrades": [], "warranties": {},
           "warranty_window_days": int(settings.get("window_days") or 30),
           "terms_url": str(settings.get("terms_url") or "")}
    if trial:
        doc["trial"] = True
    for off in cfg.get("offers") or []:
        if not off.get("on"):
            continue
        oid = off.get("id", "")
        f = facts.get(str(off.get("product_id") or ""))
        if not f or f.get("status") != "ACTIVE" or not f.get("on_sale"):
            problems.append({"offer": oid, "text": "Projector unavailable: it is not active and on sale "
                                                   "in the Online Store."})
            continue
        v = next((x for x in f.get("variants") or [] if x.get("available")), None)
        if not v:
            problems.append({"offer": oid, "text": "Projector unavailable: none of it can be bought."})
            continue
        code = ((made.get("codes") or {}).get(oid) or {}).get("code") or ""
        if not code:
            problems.append({"offer": oid, "text": "Its code is not in Shopify yet."})
            continue
        ks = [UPSELL_TRIAL_KEY] if trial else list((keys or {}).get(off.get("row_id")) or [])
        if not ks:
            problems.append({"offer": oid, "text": "No customer's order names this fixture yet, "
                                                   "so nobody would see it."})
            continue
        price = _upsell_money(v.get("price"))
        doc["upgrades"].append({
            "id": oid, "keys": ks, "headline": off.get("headline") or "", "body": off.get("body") or "",
            "product": {"id": str(off["product_id"]), "variant": str(v["id"]), "title": f.get("title") or "",
                        "image": f.get("image") or "", "price": price,
                        "price_after": _upsell_price_after(price, off.get("off_kind"), off.get("off"))},
            "code": code, "off": _upsell_off_text(off.get("off_kind"), off.get("off")),
            "ends": off.get("ends") or ""})
        if trial:
            break
    # A trial's warranty is for the staff test projector only: the extension
    # offers a warranty to every order holding its projector, so a real
    # projector's warranty in a trial would reach real buyers.
    trial_pid = str(settings.get("trial_projector_id") or "")
    if trial and not trial_pid:
        problems.append({"warranty": "", "text": "A trial carries a warranty only for the staff test "
                                                 "projector: choose it under Before warranties go live."})
    for pid, w in sorted((cfg.get("warranties") or {}).items()):
        if trial and pid != trial_pid:
            continue
        lens = [(y, L) for y, L in sorted((w.get("lengths") or {}).items()) if (L or {}).get("on")]
        if not w.get("on") or not lens:
            continue
        if not settings.get("vat_note") or not settings.get("xero_account"):
            problems.append({"warranty": pid, "text": "Warranties wait for the VAT answer and the Xero "
                                                      "account code to be recorded."})
            continue
        mw = (made.get("warranty_products") or {}).get(pid) or {}
        wf = facts.get(_gid_digits(mw.get("id")))
        if not wf:
            problems.append({"warranty": pid, "text": "Its warranty product is not in Shopify yet."})
            continue
        if wf.get("status") not in ("ACTIVE", "UNLISTED") or not wf.get("on_sale"):
            problems.append({"warranty": pid, "text": "Put on sale in Shopify first: the warranty product "
                                                      "is not in the Online Store."})
            continue
        lengths = []
        for y, _L in lens:
            vid = _gid_digits((mw.get("variants") or {}).get(str(y)))
            vf = next((x for x in wf.get("variants") or [] if str(x.get("id")) == vid), None) if vid else None
            if vf:
                lengths.append({"years": int(y), "variant": vid, "price": _upsell_money(vf.get("price"))})
        if not lengths:
            problems.append({"warranty": pid, "text": "None of its lengths is in Shopify yet."})
            continue
        doc["warranties"][pid] = {"skus": [str(s) for s in (w.get("skus") or [])],
                                  "title": (facts.get(pid) or {}).get("title") or "",
                                  "standard_years": int(w.get("standard_years") or 0),
                                  "lengths": lengths}
    return doc, problems


def _upsell_doc_json(doc: dict) -> str:
    return json.dumps(doc, separators=(",", ":"), ensure_ascii=False, sort_keys=True)


def _upsell_fingerprint(doc: dict) -> str:
    """What the shopper would see, without the moment it was published."""
    body = {k: v for k, v in (doc or {}).items() if k != "published"}
    return hashlib.sha256(_upsell_doc_json(body).encode("utf-8")).hexdigest()[:16]
```

- [ ] **Step 4: Run it to see it pass**

Run: `ONLY=t_the_rules_document env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>&1 | tail -2`
Expected: `1 passed, 0 failed`

- [ ] **Step 5: Commit**

```bash
git add copilot.py tests/test_dispatch.py
git commit -m "Upsell: the rules document, carrying only what can be sold and saying what it left out

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Phase 3: Shopify, publishing, and the page's route

### Task 8: The Shopify reads and writes (`server.UPSELL_OPS`) and the two permissions

**Files:**
- Modify: `server.py` (imports; new section before the `copilot.add_routes` call; `REQUIRED_WRITE_SCOPES`; the `add_routes` call)
- Modify: `copilot.py` (`add_routes` signature and globals; new global `_upsell_ops`)
- Modify: `shopify.app.toml` (scopes)
- Test: `tests/test_dispatch.py` (new test; update `t_the_app_asks_for_no_scope_it_cannot_use`)

**Interfaces:**
- Produces `server.UPSELL_OPS`, a dict of async callables, each returning plain dicts and never raising for expected failures:
  - `"app_key"() -> str`: the installed app's client id
  - `"shop_id"() -> str`: `gid://shopify/Shop/...`
  - `"product_facts"(ids: list[str digits]) -> {digits: {"status", "on_sale", "title", "image", "variants": [{"id", "sku", "price", "available"}]}}`
  - `"projectors"() -> [{"id": digits, ...same fact fields}]`: every product of type Projector
  - `"code_state"(discount_gid) -> {"exists": bool, "status", "ends", "code", "uses"}`
  - `"code_upsert"(discount_gid or None, spec) -> {"ok", "id", "reason", "detail"}`, where `spec = {"code", "title", "product_id", "old_product_id", "kind": "percent"|"amount", "off", "ends": "YYYY-MM-DD"|""}`
  - `"code_end"(discount_gid) -> {"ok", "reason", "detail"}`
  - `"warranty_upsert"(product_gid or None, spec) -> {"ok", "id", "variants": {"1": variant_gid, ...}, "reason", "detail"}`, where `spec = {"projector_id", "title", "lengths": [{"years", "price"}]}`
  - `"metafield_set"(owner_gid, key, value_json) -> {"ok", "reason", "detail"}` (namespace `$app`, type `json`)
- Produces `copilot._upsell_ops` (set by `add_routes(upsell_ops=...)`).

- [ ] **Step 1: Write the failing test**

```python
@test
def t_the_upsell_writes_are_the_ones_the_spec_names():
    """Spec section 5, checked on the wire: the code is for one projector, once
    per customer, combines with nothing and ends at the end of its day in
    London; a warranty is UNLISTED, needs no shipping, is not tracked, is
    taxable and carries WTY- SKUs; the rules go to the app's own namespace; a
    create whose answer is lost is looked for before it is called a failure.
    And the app asks for the two permissions these need."""
    import httpx as _hx
    sent = []
    replies = []
    async def fake_request(method, path, params=None, body=None, _retried=False, idempotent=None):
        sent.append({"body": body, "idempotent": idempotent})
        r = replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    real = server._request
    server._request = fake_request
    try:
        replies[:] = [{"data": {"discountCodeBasicCreate": {"codeDiscountNode": {"id": "gid://shopify/DiscountCodeNode/1"},
                                                            "userErrors": []}}}]
        r = run_async(server.UPSELL_OPS["code_upsert"](None, {"code": "K7Q2M9TX", "title": "Upgrade offer: Robe Spot 160",
                                                         "product_id": "100", "old_product_id": "",
                                                         "kind": "percent", "off": "15", "ends": "2026-12-31"}))
        eq(r, {"ok": True, "id": "gid://shopify/DiscountCodeNode/1"})
        d = sent[-1]["body"]["variables"]["d"]
        eq(d["context"], {"all": "ALL"}, "every buyer may use it")
        eq(d["customerGets"]["value"], {"percentage": 0.15})
        eq(d["customerGets"]["items"], {"products": {"productsToAdd": ["gid://shopify/Product/100"]}})
        eq((d["appliesOncePerCustomer"], d["combinesWith"]),
           (True, {"orderDiscounts": False, "productDiscounts": False, "shippingDiscounts": False}))
        eq(d["endsAt"], "2026-12-31T23:59:59+00:00", "the end of that day in London (GMT in December)")
        ok(d.get("startsAt"), "starts now")
        replies[:] = [_hx.ReadTimeout("slow"),
                      {"data": {"codeDiscountNodeByCode": {"id": "gid://shopify/DiscountCodeNode/2"}}}]
        r = run_async(server.UPSELL_OPS["code_upsert"](None, {"code": "ZZZZZZ", "title": "t", "product_id": "200",
                                                         "old_product_id": "", "kind": "amount", "off": "50",
                                                         "ends": ""}))
        eq((r["ok"], r["id"]), (True, "gid://shopify/DiscountCodeNode/2"), "a lost answer is looked for")
        d = sent[-2]["body"]["variables"]["d"]
        eq((d["customerGets"]["value"], d["endsAt"]),
           ({"discountAmount": {"amount": "50.00", "appliesOnEachItem": False}}, None))
        replies[:] = [{"data": {"productSet": {"product": {"id": "gid://shopify/Product/9100", "variants": {"nodes": [
            {"id": "gid://shopify/ProductVariant/9001", "sku": "WTY-100-1"},
            {"id": "gid://shopify/ProductVariant/9002", "sku": "WTY-100-2"}]}}, "userErrors": []}}}]
        r = run_async(server.UPSELL_OPS["warranty_upsert"](None, {"projector_id": "100", "title": "Extended warranty, 20 Watt",
                                                             "lengths": [{"years": 1, "price": "29.00"},
                                                                         {"years": 2, "price": "49.00"}]}))
        eq(r, {"ok": True, "id": "gid://shopify/Product/9100",
               "variants": {"1": "gid://shopify/ProductVariant/9001", "2": "gid://shopify/ProductVariant/9002"}})
        inp = sent[-1]["body"]["variables"]["input"]
        eq((inp["status"], inp["productType"]), ("UNLISTED", "Warranty"))
        eq([v["sku"] for v in inp["variants"]], ["WTY-100-1", "WTY-100-2"])
        v = inp["variants"][0]
        eq((v["taxable"], v["inventoryPolicy"], v["inventoryItem"]),
           (True, "CONTINUE", {"requiresShipping": False, "tracked": False}))
        eq(v["optionValues"], [{"optionName": "Length", "name": "1 year"}])
        eq(sent[-1]["body"]["variables"]["identifier"], None, "a new product has no identifier")
        replies[:] = [{"data": {"metafieldsSet": {"metafields": [{"id": "x"}], "userErrors": []}}}]
        r = run_async(server.UPSELL_OPS["metafield_set"]("gid://shopify/Shop/1", "upsell", "{}"))
        eq(r["ok"], True)
        m = sent[-1]["body"]["variables"]["m"][0]
        eq((m["namespace"], m["key"], m["type"], m["ownerId"]), ("$app", "upsell", "json", "gid://shopify/Shop/1"))
        replies[:] = [{"data": {"nodes": [{"id": "gid://shopify/Product/100", "title": "20 Watt", "status": "ACTIVE",
                                           "onlineStoreUrl": "https://x.test/p", "featuredMedia": {"preview": {"image": {"url": "i.png"}}},
                                           "variants": {"nodes": [{"id": "gid://shopify/ProductVariant/1001", "sku": "P220",
                                                                   "price": "335.00", "availableForSale": True}]}}, None]}}]
        f = run_async(server.UPSELL_OPS["product_facts"](["100", "999"]))
        eq(f, {"100": {"status": "ACTIVE", "on_sale": True, "title": "20 Watt", "image": "i.png",
                       "variants": [{"id": "1001", "sku": "P220", "price": "335.00", "available": True}]}},
           "a product Shopify no longer has is simply absent")
        eq(sent[-1]["idempotent"], True, "reads may be repeated")
    finally:
        server._request = real
    for s in ("write_discounts", "write_products"):
        ok(s in server.REQUIRED_WRITE_SCOPES, s + " is named where Settings checks what the app may do")
    toml = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shopify.app.toml"), encoding="utf-8").read()
    scopes = set(re.search(r'scopes = "([^"]*)"', toml).group(1).split(","))
    ok({"write_discounts", "write_products"} <= scopes, "and the app asks for them")
    ok("write_publications" not in scopes and "read_publications" not in scopes,
       "warranty products are put on sale by hand: no publications permission")
    ok(copilot._upsell_ops is not None, "the server hands the writers to the routes")
    ok(not any("upsell" in k for k in server.COPILOT_TOOLS), "and never to the AI")
```

In `t_the_app_asks_for_no_scope_it_cannot_use`, add the two scopes to `need`:

```python
    need = {"read_orders", "write_orders", "read_customers", "read_products",
            "read_fulfillments", "write_fulfillments", "read_inventory",
            "read_files", "read_shipping", "read_all_orders",
            "write_discounts", "write_products"}
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_the_upsell_writes env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>&1 | tail -3`
Expected: `FAIL ... module 'server' has no attribute 'UPSELL_OPS'`

- [ ] **Step 3: Add the scopes**

In `shopify.app.toml`, append `,write_discounts,write_products` to the end of the `scopes = "..."` string.

In `server.py`, add to `REQUIRED_WRITE_SCOPES`:

```python
    "write_discounts": "making and ending the Upsell page's offer codes",
    "write_products": "making the warranty products the Upsell page sells",
```

- [ ] **Step 4: Implement the writers**

In `server.py`, add to the imports at the top:

```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
```

Add this section immediately above `try:\n    import copilot\n    copilot.add_routes(`:

```python
# ---------------------------------------------------------------------------
# Upsell offers: the Shopify reads and writes behind Reactor's Upsell page.
# Handed to copilot.add_routes as `upsell_ops` and never to COPILOT_TOOLS: the
# AI reads the store; only an admin pressing Publish makes these writes. Each
# returns a plain dict and never raises for the expected failures.
# ---------------------------------------------------------------------------
_UPSELL_PRODUCT_FIELDS = ("id title status onlineStoreUrl featuredMedia { preview { image { url } } } "
                          "variants(first: 20) { nodes { id sku price availableForSale } }")
_UPSELL_CODE_CREATE = ("mutation($d: DiscountCodeBasicInput!) { discountCodeBasicCreate(basicCodeDiscount: $d) "
                       "{ codeDiscountNode { id } userErrors { field message code } } }")
_UPSELL_CODE_UPDATE = ("mutation($id: ID!, $d: DiscountCodeBasicInput!) { discountCodeBasicUpdate(id: $id, "
                       "basicCodeDiscount: $d) { codeDiscountNode { id } userErrors { field message code } } }")
_UPSELL_CODE_BY_CODE = "query($code: String!) { codeDiscountNodeByCode(code: $code) { id } }"
_UPSELL_CODE_READ = ("query($id: ID!) { codeDiscountNode(id: $id) { id codeDiscount { ... on DiscountCodeBasic "
                     "{ status endsAt asyncUsageCount codes(first: 1) { nodes { code } } } } } }")
_UPSELL_PRODUCT_SET = ("mutation($input: ProductSetInput!, $identifier: ProductSetIdentifiers) { productSet("
                       "synchronous: true, input: $input, identifier: $identifier) { product { id variants(first: 10) "
                       "{ nodes { id sku } } } userErrors { field message code } } }")
_UPSELL_BY_SKU = "query($q: String!) { productVariants(first: 5, query: $q) { nodes { id sku product { id } } } }"
_UPSELL_MF_SET = ("mutation($m: [MetafieldsSetInput!]!) { metafieldsSet(metafields: $m) { metafields { id } "
                  "userErrors { field message code } } }")


def _upsell_tail(v) -> str:
    m = re.search(r"(\d+)\s*$", str(v or ""))
    return m.group(1) if m else ""


def _upsell_fact(node: dict) -> dict:
    img = (((((node.get("featuredMedia") or {}).get("preview") or {}).get("image") or {}).get("url")) or "")
    return {"status": str(node.get("status") or ""), "on_sale": bool(node.get("onlineStoreUrl")),
            "title": str(node.get("title") or ""), "image": img,
            "variants": [{"id": _upsell_tail(v.get("id")), "sku": str(v.get("sku") or ""),
                          "price": str(v.get("price") or ""), "available": bool(v.get("availableForSale"))}
                         for v in (((node.get("variants") or {}).get("nodes")) or [])]}


async def _upsell_gql(query: str, variables: dict, repeatable: bool = False) -> dict:
    return await _request("POST", "graphql.json", idempotent=repeatable,
                          body={"query": query, "variables": variables})


def _upsell_errors(payload: dict, key: str) -> str:
    rows = (((payload.get("data") or {}).get(key) or {}).get("userErrors")) or []
    msgs = [str(e.get("message") or "") for e in rows]
    msgs += [str((e or {}).get("message") or e) for e in (payload.get("errors") or [])]
    return "; ".join(m for m in msgs if m)[:300]


def _upsell_price(v) -> str:
    try:
        return "%.2f" % round(float(str(v).replace(",", "")) + 1e-9, 2)
    except (TypeError, ValueError):
        return "0.00"


async def upsell_app_key() -> str:
    d = await _upsell_gql("query { currentAppInstallation { app { apiKey } } }", {}, repeatable=True)
    return str(((((d.get("data") or {}).get("currentAppInstallation") or {}).get("app") or {}).get("apiKey")) or "")


async def upsell_shop_id() -> str:
    d = await _upsell_gql("query { shop { id } }", {}, repeatable=True)
    return str(((d.get("data") or {}).get("shop") or {}).get("id") or "")


async def upsell_product_facts(ids: list) -> dict:
    out: dict = {}
    gids = ["gid://shopify/Product/" + str(i) for i in ids if str(i).isdigit()]
    for i in range(0, len(gids), 50):
        d = await _upsell_gql("query($ids: [ID!]!) { nodes(ids: $ids) { ... on Product { "
                              + _UPSELL_PRODUCT_FIELDS + " } } }", {"ids": gids[i:i + 50]}, repeatable=True)
        for n in ((d.get("data") or {}).get("nodes") or []):
            if n and n.get("id"):
                out[_upsell_tail(n["id"])] = _upsell_fact(n)
    return out


async def upsell_projectors() -> list:
    out, after = [], None
    for _ in range(10):
        d = await _upsell_gql("query($q: String!, $after: String) { products(first: 100, query: $q, after: $after) "
                              "{ nodes { " + _UPSELL_PRODUCT_FIELDS + " } pageInfo { hasNextPage endCursor } } }",
                              {"q": "product_type:Projector", "after": after}, repeatable=True)
        page = (d.get("data") or {}).get("products") or {}
        out += [dict(_upsell_fact(n), id=_upsell_tail(n.get("id"))) for n in (page.get("nodes") or [])]
        info = page.get("pageInfo") or {}
        if not info.get("hasNextPage"):
            break
        after = info.get("endCursor")
    return out


async def upsell_code_state(discount_id: str) -> dict:
    d = await _upsell_gql(_UPSELL_CODE_READ, {"id": discount_id}, repeatable=True)
    node = (d.get("data") or {}).get("codeDiscountNode") or {}
    cd = node.get("codeDiscount") or {}
    codes = ((cd.get("codes") or {}).get("nodes")) or []
    return {"exists": bool(node.get("id")), "status": str(cd.get("status") or ""),
            "ends": str(cd.get("endsAt") or ""), "code": str((codes[0] if codes else {}).get("code") or ""),
            "uses": int(cd.get("asyncUsageCount") or 0)}


def _upsell_code_input(spec: dict, *, create: bool) -> dict:
    if spec["kind"] == "percent":
        value = {"percentage": round(float(spec["off"]) / 100.0, 4)}
    else:
        value = {"discountAmount": {"amount": _upsell_price(spec["off"]), "appliesOnEachItem": False}}
    products = {"productsToAdd": ["gid://shopify/Product/" + str(spec["product_id"])]}
    old = str(spec.get("old_product_id") or "")
    if old and old != str(spec["product_id"]):
        products["productsToRemove"] = ["gid://shopify/Product/" + old]
    ends = None
    if spec.get("ends"):
        ends = (datetime.fromisoformat(spec["ends"] + "T23:59:59")
                .replace(tzinfo=ZoneInfo("Europe/London")).isoformat())
    d = {"title": spec["title"], "code": spec["code"],
         "customerGets": {"value": value, "items": {"products": products}},
         "appliesOncePerCustomer": True,
         "combinesWith": {"orderDiscounts": False, "productDiscounts": False, "shippingDiscounts": False},
         "endsAt": ends}
    if create:
        d["startsAt"] = datetime.now(timezone.utc).isoformat()
        d["context"] = {"all": "ALL"}
    return d


async def upsell_code_upsert(discount_id: Optional[str], spec: dict) -> dict:
    try:
        if discount_id:
            # An update sets the same fields again, so it is safe to repeat.
            d = await _upsell_gql(_UPSELL_CODE_UPDATE, {"id": discount_id,
                                                        "d": _upsell_code_input(spec, create=False)},
                                  repeatable=True)
            err = _upsell_errors(d, "discountCodeBasicUpdate")
            return {"ok": False, "reason": "refused", "detail": err} if err else {"ok": True, "id": discount_id}
        d = await _upsell_gql(_UPSELL_CODE_CREATE, {"d": _upsell_code_input(spec, create=True)})
        err = _upsell_errors(d, "discountCodeBasicCreate")
        if err:
            return {"ok": False, "reason": "refused", "detail": err}
        node = ((d.get("data") or {}).get("discountCodeBasicCreate") or {}).get("codeDiscountNode") or {}
        return {"ok": True, "id": str(node.get("id") or "")}
    except (httpx.TimeoutException, httpx.TransportError) as e:
        if discount_id:
            # Finding the code would only prove it exists, not that the change
            # landed; not recording it means the next publish tries again.
            return {"ok": False, "reason": "unknown", "detail": type(e).__name__}
        # The answer to a create was lost, not necessarily the code: look for it.
        try:
            f = await _upsell_gql(_UPSELL_CODE_BY_CODE, {"code": spec["code"]}, repeatable=True)
            node = (f.get("data") or {}).get("codeDiscountNodeByCode") or {}
            if node.get("id"):
                return {"ok": True, "id": str(node["id"])}
        except Exception:
            pass
        return {"ok": False, "reason": "unknown", "detail": type(e).__name__}
    except Exception as e:
        return {"ok": False, "reason": "error", "detail": str(e)[:200]}


async def upsell_code_end(discount_id: str) -> dict:
    try:
        d = await _upsell_gql(_UPSELL_CODE_UPDATE, {"id": discount_id,
                                                    "d": {"endsAt": datetime.now(timezone.utc).isoformat()}})
        err = _upsell_errors(d, "discountCodeBasicUpdate")
        return {"ok": not err, "reason": "refused" if err else "", "detail": err}
    except Exception as e:
        return {"ok": False, "reason": "error", "detail": str(e)[:200]}


def _upsell_warranty_input(spec: dict) -> dict:
    def name(y: int) -> str:
        return "%d year%s" % (y, "" if y == 1 else "s")
    lengths = sorted(spec["lengths"], key=lambda L: int(L["years"]))
    return {"title": spec["title"], "productType": "Warranty", "status": "UNLISTED",
            "vendor": "Projected Image", "tags": ["reactor-warranty"],
            "productOptions": [{"name": "Length", "values": [{"name": name(int(L["years"]))} for L in lengths]}],
            "variants": [{"optionValues": [{"optionName": "Length", "name": name(int(L["years"]))}],
                          "price": _upsell_price(L["price"]),
                          "sku": "WTY-%s-%d" % (spec["projector_id"], int(L["years"])),
                          "taxable": True, "inventoryPolicy": "CONTINUE",
                          "inventoryItem": {"requiresShipping": False, "tracked": False}}
                         for L in lengths]}


def _upsell_variant_map(nodes: list) -> dict:
    out = {}
    for v in nodes or []:
        m = re.match(r"WTY-\d+-(\d+)$", str(v.get("sku") or ""))
        if m:
            out[m.group(1)] = str(v.get("id") or "")
    return out


async def upsell_warranty_upsert(product_id: Optional[str], spec: dict) -> dict:
    ident = {"id": product_id} if product_id else None
    try:
        d = await _upsell_gql(_UPSELL_PRODUCT_SET, {"input": _upsell_warranty_input(spec), "identifier": ident})
        err = _upsell_errors(d, "productSet")
        if err:
            return {"ok": False, "reason": "refused", "detail": err}
        p = ((d.get("data") or {}).get("productSet") or {}).get("product") or {}
        return {"ok": True, "id": str(p.get("id") or ""),
                "variants": _upsell_variant_map(((p.get("variants") or {}).get("nodes")) or [])}
    except (httpx.TimeoutException, httpx.TransportError) as e:
        try:
            first = sorted(spec["lengths"], key=lambda L: int(L["years"]))[0]
            f = await _upsell_gql(_UPSELL_BY_SKU, {"q": "sku:WTY-%s-%d" % (spec["projector_id"], int(first["years"]))},
                                  repeatable=True)
            nodes = ((f.get("data") or {}).get("productVariants") or {}).get("nodes") or []
            if nodes:
                pid = str(((nodes[0].get("product") or {}).get("id")) or "")
                return {"ok": False, "reason": "unknown", "id": pid,
                        "detail": "Shopify did not answer; the product is there, and the next publish finishes it."}
        except Exception:
            pass
        return {"ok": False, "reason": "unknown", "detail": type(e).__name__}
    except Exception as e:
        return {"ok": False, "reason": "error", "detail": str(e)[:200]}


async def upsell_metafield_set(owner_id: str, key: str, value: str) -> dict:
    try:
        d = await _upsell_gql(_UPSELL_MF_SET, {"m": [{"ownerId": owner_id, "namespace": "$app", "key": key,
                                                      "type": "json", "value": value}]}, repeatable=True)
        err = _upsell_errors(d, "metafieldsSet")
        return {"ok": not err, "reason": "refused" if err else "", "detail": err}
    except Exception as e:
        return {"ok": False, "reason": "error", "detail": str(e)[:200]}


UPSELL_OPS = {"app_key": upsell_app_key, "shop_id": upsell_shop_id, "product_facts": upsell_product_facts,
              "projectors": upsell_projectors, "code_state": upsell_code_state,
              "code_upsert": upsell_code_upsert, "code_end": upsell_code_end,
              "warranty_upsert": upsell_warranty_upsert, "metafield_set": upsell_metafield_set}
```

In the `copilot.add_routes(...)` call, add `upsell_ops=UPSELL_OPS` after `customer_checker=shopify_customer_state`.

- [ ] **Step 5: Receive them in copilot**

In `copilot.py`, near `_order_writer = None` (~6089) add:

```python
_upsell_ops = None        # server.UPSELL_OPS: the Upsell page's Shopify reads and writes
```

Change the `add_routes` signature's last line to:

```python
               install_checker=None, customer_checker=None, upsell_ops=None) -> None:
```

and in its body, beside the other globals:

```python
    global _upsell_ops
    _upsell_ops = upsell_ops
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `ONLY=t_the_upsell_writes env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>&1 | tail -2` and `ONLY=t_the_app_asks_for_no_scope env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>&1 | tail -2`
Expected: `1 passed, 0 failed` each.

- [ ] **Step 7: Commit**

```bash
git add server.py copilot.py shopify.app.toml tests/test_dispatch.py
git commit -m "Upsell: the Shopify reads and writes behind the page, and the two permissions they need

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Publishing: additions, the rules, then removals

**Files:**
- Modify: `copilot.py` (Upsell section)
- Test: `tests/test_dispatch.py`

**Interfaces:**
- Consumes: `_upsell_ops` (Task 8), `_upsell_build_doc`, `_upsell_doc_json`, `_upsell_fingerprint` (Task 7), `_upsell_scan` (Task 6), stores (Task 5), `_scope_reader` (existing global), `_paginate_orders` (existing)
- Produces:
  - `UPSELL_NEEDED_SCOPES = ("write_discounts", "write_products")`
  - `_upsell_client_id() -> str` (from `shopify.app.toml`)
  - `async _upsell_gate() -> str` ("" or a plain reason)
  - `async _upsell_refresh_scan(registry) -> None` (full-history read into `store["scan"]`)
  - `_upsell_keys(d) -> {row_id: [keys]}`
  - `_upsell_code_spec(offer, made_entry) -> dict`, `_upsell_warranty_spec(pid, w, projector_title) -> dict`, `_upsell_spec_key(spec) -> str`
  - `async _upsell_publish(registry, who, *, execute: bool, trial: bool = False) -> {"ok", "steps": [str], "problems": [...], "error"?, "size"?, "published"?}`
  - `_upsell_lock` (an `asyncio.Lock`)

- [ ] **Step 1: Write the fake and the failing test**

Add near the other fakes at the top of `tests/test_dispatch.py`, after `copilot._customer_checker = _customer_unknown`:

```python
UPSELL_CALLS = []
UPSELL_FAKE = {"fail": set(), "app_key": None, "facts": None}
REAL_SCOPE_READER = copilot._scope_reader
async def _u_app_key():
    return UPSELL_FAKE["app_key"] if UPSELL_FAKE["app_key"] is not None else copilot._upsell_client_id()
async def _u_shop_id():
    return "gid://shopify/Shop/1"
async def _u_facts(ids):
    UPSELL_CALLS.append(("facts", tuple(sorted(ids))))
    src = UPSELL_FAKE["facts"] or {}
    return {k: v for k, v in src.items() if k in ids}
async def _u_projectors():
    return [dict(v, id=k) for k, v in (UPSELL_FAKE["facts"] or {}).items() if not k.startswith("9")]
async def _u_code_state(gid):
    UPSELL_CALLS.append(("code_state", gid))
    return {"exists": True, "status": "ACTIVE", "ends": "", "code": "", "uses": 0}
async def _u_code_upsert(gid, spec):
    UPSELL_CALLS.append(("code_upsert", gid, spec["code"]))
    if "code" in UPSELL_FAKE["fail"]:
        return {"ok": False, "reason": "refused", "detail": "Code must be unique"}
    return {"ok": True, "id": gid or "gid://shopify/DiscountCodeNode/" + spec["code"]}
async def _u_code_end(gid):
    UPSELL_CALLS.append(("code_end", gid))
    return {"ok": True}
async def _u_warranty_upsert(gid, spec):
    UPSELL_CALLS.append(("warranty_upsert", gid, spec["projector_id"]))
    made = {"100": ("9100", {"1": "9001", "2": "9002"}), "300": ("9300", {"1": "9101"})}[spec["projector_id"]]
    return {"ok": True, "id": "gid://shopify/Product/" + made[0],
            "variants": {y: "gid://shopify/ProductVariant/" + v for y, v in made[1].items()}}
async def _u_metafield_set(owner, key, value):
    UPSELL_CALLS.append(("metafield_set", owner, key, json.loads(value)))
    if "rules" in UPSELL_FAKE["fail"]:
        return {"ok": False, "reason": "refused", "detail": "Value too large"}
    return {"ok": True}
UPSELL_FAKE_OPS = {"app_key": _u_app_key, "shop_id": _u_shop_id, "product_facts": _u_facts,
                   "projectors": _u_projectors, "code_state": _u_code_state, "code_upsert": _u_code_upsert,
                   "code_end": _u_code_end, "warranty_upsert": _u_warranty_upsert,
                   "metafield_set": _u_metafield_set}
async def _u_scopes(max_age=900.0):
    return {"scopes": ["write_orders", "write_discounts", "write_products"], "missing": {}, "error": ""}


def upsell_reset(cfg=None, facts=None):
    """A clean Upsell store with UPSELL_CFG's offers, and the fake Shopify."""
    UPSELL_CALLS.clear()
    UPSELL_FAKE.update({"fail": set(), "app_key": None, "facts": facts or UPSELL_FACTS})
    if hasattr(copilot, "_upsell_projectors_cache"):      # exists from Task 10
        copilot._upsell_projectors_cache.update({"at": 0.0, "rows": []})
    copilot._upsell_ops = UPSELL_FAKE_OPS
    copilot._scope_reader = _u_scopes
    for p in (copilot.UPSELL_PATH, copilot.WARRANTY_PATH):
        try:
            os.remove(p)
        except FileNotFoundError:
            pass
        copilot._forget_store(p)
    d = copilot._upsell_default()
    c = json.loads(json.dumps(cfg or UPSELL_CFG))
    d["offers"], d["warranties"], d["settings"] = c["offers"], c["warranties"], c["settings"]
    d["scan"] = {"robe|spot 160": {"row": {"manufacturer": "Robe", "model": "Spot 160"},
                                   "keys": ["robe|spot 160"], "customers": 2, "last": "2026-09-06T10:00:00Z"}}
    d["scan_at"] = datetime.now(timezone.utc).isoformat()
    copilot._write_upsell(d)
    return d


def upsell_test(fn):
    """For a test that calls upsell_reset(): whatever happens, put back the
    real scope reader after it, so later tests do not see every permission
    granted. Goes under @test, so the name ONLY= matches is kept."""
    @functools.wraps(fn)
    def wrapped():
        try:
            fn()
        finally:
            copilot._scope_reader = REAL_SCOPE_READER
    return wrapped
```

(`UPSELL_CFG` and `UPSELL_FACTS` are the module-level constants added in Task 7's test; move them above these fakes so they are defined first. If `datetime`/`timezone` or `functools` are not yet imported in the test file, add `from datetime import datetime, timezone` and `import functools` to its imports.)

Then the test:

```python
@test
@upsell_test
def t_publishing_adds_first_publishes_then_removes():
    """Spec section 8: codes and warranty products before the rules document,
    ending an old code only after it; nothing half done on a failure; every
    step that landed recorded, so a repeat does not make anything twice."""
    upsell_reset()
    r = run_async(copilot._upsell_publish({}, "cameron", execute=False))
    ok(r["ok"], r)
    ok(any("K7Q2M9TX" in s for s in r["steps"]), "the preview says which code it makes")
    ok(not [c for c in UPSELL_CALLS if c[0] in ("code_upsert", "warranty_upsert", "metafield_set")],
       "the preview writes nothing")
    UPSELL_CALLS.clear()
    r = run_async(copilot._upsell_publish({}, "cameron", execute=True))
    ok(r["ok"], r)
    kinds = [c[0] for c in UPSELL_CALLS if c[0] != "facts"]
    eq(kinds, ["code_upsert", "warranty_upsert", "warranty_upsert", "metafield_set"],
       "codes and warranty products first, then the rules")
    rules = [c for c in UPSELL_CALLS if c[0] == "metafield_set"][0]
    eq((rules[1], rules[2]), ("gid://shopify/Shop/1", "upsell"))
    eq([u["id"] for u in rules[3]["upgrades"]], ["u1"])
    eq(sorted(rules[3]["warranties"]), ["100"], "the 80 Watt's warranty waits until it is on sale")
    d = copilot._load_upsell()
    eq(d["made"]["codes"]["u1"]["id"], "gid://shopify/DiscountCodeNode/K7Q2M9TX")
    ok(d["published"]["at"] and d["published"]["fingerprint"], "what was published is recorded")
    UPSELL_CALLS.clear()
    run_async(copilot._upsell_publish({}, "cameron", execute=True))
    eq([c[0] for c in UPSELL_CALLS if c[0] != "facts"], ["metafield_set"],
       "a repeat with nothing changed makes nothing again")
    d = copilot._load_upsell()
    d["offers"][0]["on"] = False
    copilot._write_upsell(d)
    UPSELL_CALLS.clear()
    run_async(copilot._upsell_publish({}, "cameron", execute=True))
    eq([c[0] for c in UPSELL_CALLS if c[0] != "facts"], ["metafield_set", "code_end"],
       "an offer turned off: the rules first, then its code is ended")
    eq(copilot._load_upsell()["made"]["codes"]["u1"].get("ended"), True)
    d = copilot._load_upsell()
    d["offers"][0]["on"] = True
    copilot._write_upsell(d)
    UPSELL_CALLS.clear()
    run_async(copilot._upsell_publish({}, "cameron", execute=True))
    eq([c[:2] for c in UPSELL_CALLS if c[0] == "code_upsert"],
       [("code_upsert", "gid://shopify/DiscountCodeNode/K7Q2M9TX")],
       "an offer switched back on starts its old code again rather than making a second with the same text")
    eq(copilot._load_upsell()["made"]["codes"]["u1"].get("ended"), None, "and it is no longer marked ended")
    upsell_reset()
    UPSELL_FAKE["fail"].add("code")
    r = run_async(copilot._upsell_publish({}, "cameron", execute=True))
    ok(not r["ok"] and "K7Q2M9TX" in r["error"], "a failed code stops the publish and says which")
    ok(not [c for c in UPSELL_CALLS if c[0] == "metafield_set"], "and the rules are not touched")
    upsell_reset()
    UPSELL_FAKE["fail"].add("rules")
    r = run_async(copilot._upsell_publish({}, "cameron", execute=True))
    ok(not r["ok"], "a refused rules document fails the publish")
    ok(not [c for c in UPSELL_CALLS if c[0] == "code_end"], "and nothing is removed")
    ok(copilot._load_upsell()["made"]["codes"].get("u1"), "but the code that landed is remembered")
    upsell_reset()
    UPSELL_FAKE["app_key"] = "someone-else"
    r = run_async(copilot._upsell_publish({}, "cameron", execute=True))
    ok(not r["ok"] and "different app" in r["error"], "rules written to another app's settings would never show")
    upsell_reset()
    async def few(max_age=900.0):
        return {"scopes": ["write_orders"], "missing": {}, "error": ""}
    copilot._scope_reader = few
    r = run_async(copilot._upsell_publish({}, "cameron", execute=True))
    ok(not r["ok"] and r["error"].startswith("Waiting for Shopify permission"), r)
    upsell_reset()
    r = run_async(copilot._upsell_publish({}, "cameron", execute=True, trial=True))
    rules = [c for c in UPSELL_CALLS if c[0] == "metafield_set"][0][3]
    eq(([u["keys"] for u in rules["upgrades"]], rules.get("trial")), ([[copilot.UPSELL_TRIAL_KEY]], True))
    eq(copilot._load_upsell()["published"]["trial"], True)
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_publishing_adds env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>&1 | tail -3`
Expected: `FAIL ... no attribute '_upsell_publish'`

- [ ] **Step 3: Implement**

Add to the Upsell section of `copilot.py`:

```python
UPSELL_NEEDED_SCOPES = ("write_discounts", "write_products")
_upsell_lock = asyncio.Lock()


def _upsell_client_id() -> str:
    """The app the extension belongs to, from the config shipped with the code."""
    try:
        import tomllib
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "shopify.app.toml"), "rb") as fh:
            return str(tomllib.load(fh).get("client_id") or "")
    except Exception:
        return ""


async def _upsell_gate() -> str:
    """'' when publishing may go ahead, else the plain reason it may not."""
    if _upsell_ops is None:
        return "Publishing is not switched on on this server."
    if _scope_reader is not None:
        try:
            got = await _scope_reader()
        except Exception:
            got = {"scopes": []}
        scopes = set(got.get("scopes") or [])
        if not scopes:
            return "Shopify did not say what the app may do just now. Try again in a minute."
        if not all(s in scopes for s in UPSELL_NEEDED_SCOPES):
            return ("Waiting for Shopify permission: approve the app's new permissions on the store "
                    "(making offer codes and warranty products), then try again.")
    want = _upsell_client_id()
    if not want:
        return "The app's own configuration could not be read, so where the offers would land is not known."
    try:
        have = await _upsell_ops["app_key"]()
    except Exception:
        return "Shopify could not be reached. Try again in a minute."
    if not have:
        return "Shopify did not say which app this is. Try again in a minute."
    if have != want:
        return ("Reactor is connected to Shopify through a different app from the one that shows the "
                "offers, so they would never appear. Check the store connection before publishing.")
    return ""


def _upsell_keys(d: dict) -> dict:
    return {rid: list(v.get("keys") or []) for rid, v in (d.get("scan") or {}).items()}


async def _upsell_refresh_scan(registry: dict) -> None:
    """Every gobo order's fixture, read from the whole order history. The
    usual page cap (30 pages) would cut a long history short, and it pages
    from the oldest, so the newest customers would be the ones lost."""
    meta: dict = {}
    orders = await _paginate_orders(registry, days=3650, max_pages=400,
                                    fields="id,created_at,email,customer,line_items,cancelled_at,payment_gateway_names",
                                    meta=meta)
    if meta.get("failed"):
        raise RuntimeError("Shopify did not answer for the whole order history.")
    if meta.get("truncated"):
        raise RuntimeError("The order history is longer than Reactor reads at once.")
    scan = _upsell_scan(orders, _gobo_sizes())
    d = _load_upsell()
    d["scan"], d["scan_at"] = scan, datetime.now(timezone.utc).isoformat()
    _write_upsell(d)


def _upsell_spec_key(spec: dict) -> str:
    """What Shopify should hold, not how Reactor gets there: old_product_id
    only says which product to take off an existing code, and it changes once
    the first save is recorded, so counting it would resend every code on
    every publish."""
    body = {k: v for k, v in spec.items() if k != "old_product_id"}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def _upsell_code_spec(off: dict, made: Optional[dict]) -> dict:
    row = off.get("row") or {}
    return {"code": str(off.get("code") or ""),
            "title": ("Upgrade offer: " + " ".join(x for x in (row.get("manufacturer"), row.get("model")) if x))[:120],
            "product_id": str(off.get("product_id") or ""),
            "old_product_id": str((made or {}).get("product_id") or ""),
            "kind": off.get("off_kind") or "percent", "off": str(off.get("off") or ""),
            "ends": off.get("ends") or ""}


def _upsell_warranty_spec(pid: str, w: dict, projector_title: str) -> dict:
    """Every length that has a price, on or off: a length switched off keeps its
    variant, so switching it back on never has to make one."""
    short = re.sub(r"\s+", " ", re.sub(r"(?i)\b(gobo|projector)s?\b", "", projector_title)).strip(" ,")
    lengths = [{"years": int(y), "price": _upsell_money((L or {}).get("price"))}
               for y, L in sorted((w.get("lengths") or {}).items())
               if _upsell_money((L or {}).get("price")) not in ("", "0.00")]
    # Never "projector" in the title: the forecast files any title with that
    # word under Projector.
    return {"projector_id": str(pid),
            "title": (("Extended warranty, " + short) if short else "Extended warranty")[:120],
            "lengths": lengths}


def _upsell_fail(msg: str) -> dict:
    d = _load_upsell()
    d["last_error"] = msg
    _write_upsell(d)
    return {"ok": False, "error": msg}


async def _upsell_publish(registry: dict, who: str, *, execute: bool, trial: bool = False) -> dict:
    """Spec sections 5 and 8. A preview when execute is False: what it would do,
    and nothing written. Additions go before the rules document and removals
    after it; any failure leaves the last published rules in place and says
    what failed; every addition that lands is recorded at once, so a repeat
    finds it instead of making it again."""
    gate = await _upsell_gate()
    if gate:
        return {"ok": False, "error": gate}
    async with _upsell_lock:
        d = _load_upsell()
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(d.get("scan_at") or "")).total_seconds()
        except ValueError:
            age = None
        if registry and (age is None or age > 86400):
            # Keys are built from the whole order history at Publish; the hourly
            # check only adds to them.
            try:
                await _upsell_refresh_scan(registry)
                d = _load_upsell()
            except Exception:
                return {"ok": False, "error": "The orders could not be read to find customers' fixtures. "
                                              "Try again in a minute."}
        cfg = {"offers": d["offers"], "warranties": d["warranties"], "settings": d["settings"]}
        made = d["made"]
        ops = _upsell_ops
        ids = {str(o.get("product_id") or "") for o in cfg["offers"] if o.get("on")} | set(cfg["warranties"])
        ids |= {_gid_digits(m.get("id")) for m in made["warranty_products"].values()}
        try:
            facts = await ops["product_facts"](sorted(i for i in ids if i))
        except Exception:
            return {"ok": False, "error": "Shopify could not be reached to check the products. Try again in a minute."}
        steps: list = []
        adds: list = []
        ends: list = []
        for off in cfg["offers"]:
            if not off.get("on"):
                continue
            f = facts.get(str(off.get("product_id") or ""))
            if not f or f.get("status") != "ACTIVE" or not f.get("on_sale"):
                continue                      # _upsell_build_doc says why
            old = made["codes"].get(off["id"]) or {}
            spec = _upsell_code_spec(off, old)
            key = _upsell_spec_key(spec)
            if not old.get("id"):
                adds.append(("code", off["id"], None, spec, key))
                steps.append("Make the offer code " + spec["code"] + " (" + spec["title"] + ")")
            elif old.get("ended") or old.get("spec") != key:
                # An ended code is started again, never made anew: Shopify
                # keeps ended codes, so a second with the same text is refused.
                adds.append(("code", off["id"], old["id"], spec, key))
                steps.append(("Start the offer code again " if old.get("ended") else "Change the offer code ")
                             + spec["code"])
        live = {o["id"] for o in cfg["offers"] if o.get("on")}
        for oid, m in made["codes"].items():
            if oid not in live and m.get("id") and not m.get("ended"):
                ends.append((oid, m))
                steps.append("End the offer code " + str(m.get("code") or ""))
        s = cfg["settings"]
        for pid, w in sorted(cfg["warranties"].items()):
            if not w.get("on") or not s.get("vat_note") or not s.get("xero_account"):
                continue
            spec = _upsell_warranty_spec(pid, w, (facts.get(pid) or {}).get("title") or "")
            if not spec["lengths"]:
                continue
            key = _upsell_spec_key(spec)
            old = made["warranty_products"].get(pid) or {}
            if not old.get("id"):
                adds.append(("warranty", pid, None, spec, key))
                steps.append("Make the warranty product " + spec["title"]
                             + ", then put it on sale in the Online Store yourself")
            elif old.get("spec") != key:
                adds.append(("warranty", pid, old["id"], spec, key))
                steps.append("Change the warranty product " + spec["title"])
        steps.append("Publish the offers to the thank-you and order status pages" + (" as a trial" if trial else ""))
        if not execute:
            doc, problems = _upsell_build_doc(cfg, _upsell_keys(d), facts, made, trial=trial)
            return {"ok": True, "steps": steps, "problems": problems,
                    "size": len(_upsell_doc_json(doc).encode("utf-8"))}
        for kind, ident, existing, spec, key in adds:
            if kind == "code":
                r = await ops["code_upsert"](existing, spec)
                if not r.get("ok"):
                    return _upsell_fail("The offer code " + spec["code"] + " could not be saved in Shopify ("
                                        + str(r.get("detail") or r.get("reason") or "no answer")
                                        + "). Nothing was published.")
                made["codes"][ident] = {"id": r["id"], "code": spec["code"], "product_id": spec["product_id"],
                                        "spec": key}
            else:
                r = await ops["warranty_upsert"](existing, spec)
                if not r.get("ok"):
                    if r.get("id") and not existing:
                        made["warranty_products"][ident] = {"id": r["id"], "variants": {}, "spec": ""}
                        _write_upsell(d)
                    return _upsell_fail("The warranty product " + spec["title"] + " could not be saved in Shopify ("
                                        + str(r.get("detail") or r.get("reason") or "no answer")
                                        + "). Nothing was published.")
                made["warranty_products"][ident] = {"id": r["id"], "variants": r.get("variants") or {}, "spec": key}
            _write_upsell(d)
        wids = [_gid_digits(m.get("id")) for m in made["warranty_products"].values() if m.get("id")]
        if wids:
            try:
                facts.update(await ops["product_facts"](wids))
            except Exception:
                pass
        doc, problems = _upsell_build_doc(cfg, _upsell_keys(d), facts, made, trial=trial)
        body = _upsell_doc_json(doc)
        if len(body.encode("utf-8")) > UPSELL_DOC_MAX:
            return _upsell_fail("The offers are too large to publish (over 100 KB). Turn some off, or remove "
                                "old offers, and try again.")
        try:
            shop = await ops["shop_id"]()
            r = await ops["metafield_set"](shop, "upsell", body)
        except Exception as e:
            r = {"ok": False, "detail": type(e).__name__}
        if not r.get("ok"):
            return _upsell_fail("The offers could not be published (" + str(r.get("detail") or "no answer")
                                + "). What was shown before stays.")
        for oid, m in ends:
            er = await ops["code_end"](m["id"])
            if er.get("ok"):
                m["ended"] = True
            else:
                problems.append({"offer": oid, "text": "The old code " + str(m.get("code") or "")
                                 + " could not be ended. End it in Shopify's Discounts."})
        d["published"] = {"at": doc["published"], "by": who, "fingerprint": _upsell_fingerprint(doc),
                          "config": json.loads(json.dumps(cfg)), "doc": doc, "trial": bool(trial)}
        d["problems"], d["last_error"] = problems, ""
        _write_upsell(d)
        _track(who, "upsell", "published the offers" + (" as a trial" if trial else ""),
               "%d upgrade(s), %d warranty model(s)" % (len(doc["upgrades"]), len(doc["warranties"])))
        return {"ok": True, "steps": steps, "problems": problems, "published": doc["published"]}
```

- [ ] **Step 4: Run it to see it pass**

Run: `ONLY=t_publishing_adds env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>&1 | tail -2`
Expected: `1 passed, 0 failed`

- [ ] **Step 5: Commit**

```bash
git add copilot.py tests/test_dispatch.py
git commit -m "Upsell: publishing makes codes and warranty products, then the rules, then ends what went

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: The page's route, `/api/upsell` (admins only)

**Files:**
- Modify: `copilot.py` (Upsell section; the route inside `add_routes`; `_OPEN_API`)
- Test: `tests/test_dispatch.py`

**Interfaces:**
- Consumes: Tasks 5 to 9
- Produces:
  - `_upsell_new_code() -> str` (8 characters from `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`)
  - `_upsell_clean_offers(items, d) -> (offers, error)`, `_upsell_clean_warranties(items, projector_ids) -> (warranties, error)`, `_upsell_clean_settings(s) -> (settings, error)`
  - `async _upsell_projector_list() -> list` (the `projectors` op, cached 10 minutes)
  - `_upsell_row_search(q) -> [{"row_id", "manufacturer", "model"}]`
  - `_upsell_results() -> {"offers": {id: {"card", "typed", "revenue", "last"}}, "warranties": {"sold", "revenue", "last"}}`, `_upsell_needs_look() -> list`
  - `async _upsell_view() -> dict`: the page's whole state (shape in the code)
  - `POST /api/upsell` with `op` in `get`, `scan`, `rows`, `mark`, `save`, `replace_code`, `plan`, `publish` (and `sale` in Task 12, `drift` in Task 13). Errors answer `{"error": "..."}` with 400 (bad input), 409 (publish refused) or 503 (store unreadable).

- [ ] **Step 1: Write the failing test**

```python
@test
@upsell_test
def t_the_upsell_page_is_an_admins_and_checks_what_it_is_given():
    """The page changes what shoppers see, so only an admin may use it; every
    value is checked before it is kept; and a model that is one of our own
    projectors with warranties on cannot be marked poor quality."""
    def go():
        ensure_auth()
        upsell_reset()
        _uid, sess, _ = ready_user("Lee", "lee-upsell")
        eq(post_s(sess, "/api/upsell", {"op": "get"}).status_code, 403, "a member may not open it")
        v = post("/api/upsell", {"op": "get"}).json()
        eq(v["gate"], "", "the fake Shopify grants everything")
        eq([o["id"] for o in v["offers"]], ["u1", "u2", "u3"])
        eq(v["offers"][0]["reach"], 2, "an offer says how many customers use its fixture")
        eq(v["offers"][0]["spellings"], ["robe|spot 160"], "and every spelling it matches")
        eq(v["offers"][0]["row_gone"], False, "and whether its fixture is still on the size list")
        eq(v["fixtures"][0]["model"], "Spot 160")
        eq(sorted(p["id"] for p in v["projectors"]), ["100", "200", "300"])
        eq(v["published"]["current"], False, "nothing published yet")
        r = post("/api/upsell", {"op": "mark", "row_id": "robe|spot 160"}).json()
        new = r["offers"][-1]
        ok(re.fullmatch(r"[A-HJ-NP-Z2-9]{8}", new["code"]), "a new offer gets a random 8-character code")
        eq((new["on"], new["off_kind"], new["row"]["model"]), (False, "percent", "Spot 160"), "and starts switched off")
        rows = post("/api/upsell", {"op": "rows", "q": "source four junior"}).json()["rows"]
        ok(any(x["manufacturer"] == "ETC" for x in rows), "the size list can be searched for a model nobody has ordered for")
        r = post("/api/upsell", {"op": "mark", "manufacturer": "Projected Image", "model": "20 Watt LED"})
        eq(r.status_code, 400, "our own projector cannot be marked poor quality while warranties are on")
        bad = json.loads(json.dumps(v["offers"]))
        bad[0]["off"] = "95"
        r = post("/api/upsell", {"op": "save", "offers": bad})
        eq(r.status_code, 400)
        ok("90%" in r.json()["error"], r.json())
        bad = json.loads(json.dumps(v["offers"]))
        bad[1]["code"] = bad[0]["code"]
        eq(post("/api/upsell", {"op": "save", "offers": bad}).status_code, 400, "two offers cannot share a code")
        good = json.loads(json.dumps(v["offers"]))
        good[0]["headline"] = "A brighter projector"
        eq(post("/api/upsell", {"op": "save", "offers": good}).status_code, 200)
        eq(copilot._load_upsell()["offers"][0]["headline"], "A brighter projector")
        w = json.loads(json.dumps(v["warranties"]))
        w["100"]["lengths"]["3"] = {"on": True, "price": ""}
        eq(post("/api/upsell", {"op": "save", "warranties": w}).status_code, 400, "a length switched on needs a price")
        s = dict(v["settings"], terms_url="http://x.test/terms")
        eq(post("/api/upsell", {"op": "save", "settings": s}).status_code, 400, "the terms link must be https")
        old = copilot._load_upsell()["offers"][0]["code"]
        post("/api/upsell", {"op": "replace_code", "id": "u1"})
        ok(copilot._load_upsell()["offers"][0]["code"] != old, "a code can be replaced")
        r = post("/api/upsell", {"op": "plan"}).json()
        ok(r["ok"] and r["steps"], r)
        r = post("/api/upsell", {"op": "publish"})
        eq(r.status_code, 200, r.text[:300])
        eq(post("/api/upsell", {"op": "get"}).json()["published"]["current"], True, "what is saved is what is live")
    with_accounts(go)
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_the_upsell_page_is env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>&1 | tail -3`
Expected: `FAIL ... 404` or `'/api/upsell' refused` (the route does not exist yet).

- [ ] **Step 3: Implement the helpers**

Add to the Upsell section:

```python
UPSELL_OWN_BRAND = "projected image"
_UPSELL_CODE_RE = re.compile(r"[A-Z0-9]{6,20}")
_UPSELL_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_upsell_projectors_cache: dict = {"at": 0.0, "rows": []}


def _upsell_new_code() -> str:
    return "".join(secrets.choice(_UPSELL_ALPHABET) for _ in range(8))


def _upsell_known_rows(d: dict) -> dict:
    rows = {rid: v.get("row") for rid, v in (d.get("scan") or {}).items()}
    for o in d.get("offers") or []:
        if o.get("row_id") and isinstance(o.get("row"), dict):
            rows.setdefault(o["row_id"], o["row"])
    return rows


def _upsell_clean_offers(items, d: dict) -> tuple:
    if not isinstance(items, list) or len(items) > 50:
        return None, "Up to 50 offers."
    rows = _upsell_known_rows(d)
    out, codes = [], set()
    for o in items:
        if not isinstance(o, dict):
            return None, "An offer was not readable."
        rid = str(o.get("row_id") or "")
        row = rows.get(rid)
        if not row:
            return None, "Pick the fixture again: that one is no longer known."
        kind = o.get("off_kind")
        if kind not in ("percent", "amount"):
            return None, "Choose a percentage or an amount off."
        off = _upsell_money(o.get("off"))
        if not off or float(off) <= 0 or (kind == "percent" and float(off) > 90):
            return None, "The discount must be more than nothing, and no more than 90%."
        ends = str(o.get("ends") or "")
        if ends and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", ends):
            return None, "The end date is not a date."
        code = str(o.get("code") or "").strip().upper()
        if not _UPSELL_CODE_RE.fullmatch(code):
            return None, "A code is 6 to 20 capital letters and numbers."
        if code in codes:
            return None, "Each offer needs its own code."
        codes.add(code)
        pid = re.sub(r"\D", "", str(o.get("product_id") or ""))
        headline = str(o.get("headline") or "").strip()[:80]
        on = bool(o.get("on"))
        if on and not pid:
            return None, "Choose the projector to recommend before switching this offer on."
        if on and not headline:
            return None, "Give the card a headline before switching it on."
        out.append({"id": str(o.get("id") or "") or "u" + secrets.token_hex(3), "row_id": rid,
                    "row": {"manufacturer": str(row.get("manufacturer") or "")[:120],
                            "model": str(row.get("model") or "")[:200]},
                    "product_id": pid, "off_kind": kind, "off": off, "ends": ends, "code": code,
                    "headline": headline, "body": str(o.get("body") or "").strip()[:200], "on": on})
    return out, ""


def _upsell_clean_warranties(items, projector_ids: set) -> tuple:
    if not isinstance(items, dict) or len(items) > 100:
        return None, "The warranties were not readable."
    out = {}
    for pid, w in items.items():
        pid = re.sub(r"\D", "", str(pid))
        if not pid or not isinstance(w, dict):
            return None, "A warranty was not readable."
        if projector_ids and pid not in projector_ids:
            return None, "A warranty is for a projector the shop no longer has."
        try:
            sy = int(w.get("standard_years") or 0)
        except (TypeError, ValueError):
            sy = -1
        if not 0 <= sy <= 10:
            return None, "The standard guarantee is between 0 and 10 years."
        lengths = {}
        for y in ("1", "2", "3"):
            L = (w.get("lengths") or {}).get(y) or {}
            price = _upsell_money(L.get("price")) if str(L.get("price") or "").strip() else ""
            on = bool(L.get("on"))
            if on and (not price or float(price) <= 0):
                return None, "Give each warranty length that is switched on a price."
            lengths[y] = {"on": on, "price": price}
        skus = [str(s).strip()[:40] for s in (w.get("skus") or []) if str(s).strip()][:10]
        out[pid] = {"on": bool(w.get("on")), "standard_years": sy, "skus": skus, "lengths": lengths}
    return out, ""


def _upsell_clean_settings(s) -> tuple:
    if not isinstance(s, dict):
        return None, "The settings were not readable."
    try:
        window = int(s.get("window_days") or 30)
    except (TypeError, ValueError):
        window = 0
    if not 1 <= window <= 60:
        return None, "The warranty window is between 1 and 60 days."
    terms = str(s.get("terms_url") or "").strip()
    if terms and (not terms.startswith("https://") or len(terms) > 300):
        return None, "The terms link must start with https://."
    xero = str(s.get("xero_account") or "").strip()
    if xero and not re.fullmatch(r"[A-Za-z0-9-]{1,20}", xero):
        return None, "The Xero account code is letters, numbers and dashes."
    return {"window_days": window, "terms_url": terms,
            "vat_note": str(s.get("vat_note") or "").strip()[:200], "xero_account": xero,
            # The staff test projector a trial's warranty is for (Task 7).
            "trial_projector_id": re.sub(r"\D", "", str(s.get("trial_projector_id") or ""))[:20]}, ""


async def _upsell_projector_list() -> list:
    if _upsell_ops is None:
        return []
    now = time.monotonic()
    if now - _upsell_projectors_cache["at"] > 600 or not _upsell_projectors_cache["rows"]:
        try:
            _upsell_projectors_cache.update({"at": now, "rows": await _upsell_ops["projectors"]()})
        except Exception:
            logger.exception("upsell: projectors unreadable")
    return list(_upsell_projectors_cache["rows"])


def _upsell_row_search(q: str) -> list:
    words = _norm_key(q).split()
    if not words:
        return []
    out, seen = [], set()
    for _lm, _rw, e in (_gobo_sizes().get("rows") or []):
        hay = _norm_key(e.get("manufacturer", "") + " " + e.get("model", ""))
        if all(w in hay for w in words):
            rid = _upsell_row_id(e.get("manufacturer", ""), e.get("model", ""))
            if rid not in seen:
                seen.add(rid)
                out.append({"row_id": rid, "manufacturer": e.get("manufacturer", ""), "model": e.get("model", "")})
        if len(out) >= 20:
            break
    return out


def _upsell_results() -> dict:
    w = _load_warranties()
    offers: dict = {}
    wr = {"sold": 0, "revenue": 0.0, "last": ""}
    for r in (w.get("results") or {}).values():
        if r.get("trial"):
            continue                          # spec section 9: trial orders are left out
        net = max(0.0, float(r.get("total") or 0) - float(r.get("refunded") or 0))
        if r.get("offer") == "warranty":
            wr["sold"] += 1
            wr["revenue"] += net
            wr["last"] = max(wr["last"], str(r.get("at") or ""))
            continue
        o = offers.setdefault(str(r.get("offer") or ""), {"card": 0, "typed": 0, "revenue": 0.0, "last": ""})
        o["card" if r.get("via") == "card" else "typed"] += 1
        o["revenue"] += net
        o["last"] = max(o["last"], str(r.get("at") or ""))
    for o in offers.values():
        o["revenue"] = _upsell_money(o["revenue"])
    wr["revenue"] = _upsell_money(wr["revenue"])
    return {"offers": offers, "warranties": wr}


def _upsell_needs_look() -> list:
    """Sales waiting for an admin: ones that failed the checks, and covers
    whose projector came back, whose warranty needs refunding (spec section 7)."""
    return [dict(s, id=k) for k, s in sorted((_load_warranties().get("sales") or {}).items())
            if s.get("status") in ("needs_look", "returned")]


async def _upsell_view() -> dict:
    d = _load_upsell()
    cfg = {"offers": d["offers"], "warranties": d["warranties"], "settings": d["settings"]}
    pub = d["published"]
    current = bool(pub.get("at")) and (json.dumps(pub.get("config"), sort_keys=True)
                                       == json.dumps(cfg, sort_keys=True))
    scan = d.get("scan") or {}
    rows_now = {_upsell_row_id(e.get("manufacturer", ""), e.get("model", ""))
                for _lm, _rw, e in (_gobo_sizes().get("rows") or [])}
    return {"offers": [dict(o, reach=int((scan.get(o.get("row_id")) or {}).get("customers") or 0),
                            reach_checkout=int((scan.get(o.get("row_id")) or {}).get("checkout") or 0),
                            spellings=list((scan.get(o.get("row_id")) or {}).get("keys") or []),
                            row_gone=o.get("row_id") not in rows_now)
                       for o in d["offers"]],
            "warranties": d["warranties"], "settings": d["settings"],
            "fixtures": _upsell_fixture_ranking(scan, 60), "scan_at": d["scan_at"],
            "projectors": await _upsell_projector_list(),
            "published": {"at": pub.get("at") or "", "by": _team_name(pub.get("by")) if pub.get("by") else "",
                          "trial": bool(pub.get("trial")), "current": current},
            "problems": d["problems"], "drift": d["drift"], "last_error": d["last_error"],
            "gate": await _upsell_gate(), "results": _upsell_results(), "needs_look": _upsell_needs_look()}
```

- [ ] **Step 4: Implement the route**

Add `"/api/upsell"` to the end of `_OPEN_API` (its routes refuse non-admins themselves), then add this route inside `add_routes`, next to `/api/privacy`:

```python
    @mcp.custom_route("/api/upsell", methods=["POST"])
    async def upsell_route(request: Request):
        """The Upsell page: an admin's, since it changes what shoppers see."""
        err, body, who = await _guard(request, min_level=ROLE_LEVELS["admin"])
        if err:
            return err
        op = str(body.get("op") or "get")
        _load_upsell()
        if UPSELL_PATH in _poisoned_stores:
            return _json({"error": "The upsell settings cannot be read just now. Check the server's storage, "
                                   "or restore the latest backup."}, 503)
        try:
            if op == "get":
                return _json(await _upsell_view())
            if op == "scan":
                try:
                    async with _upsell_lock:
                        await _upsell_refresh_scan(registry)
                except Exception:
                    return _json({"error": "The orders could not be read just now. Try again in a minute."}, 502)
                return _json(await _upsell_view())
            if op == "rows":
                return _json({"rows": _upsell_row_search(str(body.get("q") or "")[:80])})
            if op == "mark":
                async with _upsell_lock:
                    d = _load_upsell()
                    rid = str(body.get("row_id") or "")
                    row = _upsell_known_rows(d).get(rid)
                    if not row:
                        hit = next((x for x in _upsell_row_search(str(body.get("manufacturer") or "") + " "
                                                                  + str(body.get("model") or ""))
                                    if _norm_key(x["manufacturer"]) == _norm_key(body.get("manufacturer"))
                                    and _norm_key(x["model"]) == _norm_key(body.get("model"))), None)
                        if hit:
                            rid, row = hit["row_id"], {"manufacturer": hit["manufacturer"], "model": hit["model"]}
                        elif body.get("manufacturer") and body.get("model"):
                            row = {"manufacturer": str(body["manufacturer"])[:120], "model": str(body["model"])[:200]}
                            rid = _upsell_row_id(row["manufacturer"], row["model"])
                    if not row:
                        return _json({"error": "That fixture is not on the size list."}, 400)
                    if (_norm_key(row.get("manufacturer")) == UPSELL_OWN_BRAND
                            and any(w.get("on") for w in d["warranties"].values())):
                        return _json({"error": "That is one of the shop's own projectors, which carry warranties. "
                                               "It cannot also be offered an upgrade away from."}, 400)
                    d["offers"].append({"id": "u" + secrets.token_hex(3), "row_id": rid, "row": row, "product_id": "",
                                        "off_kind": "percent", "off": "10.00", "ends": "", "code": _upsell_new_code(),
                                        "headline": "Time for a brighter projector?", "body": "", "on": False})
                    _write_upsell(d)
                _track(who, "upsell", "marked a fixture as poor quality", row["manufacturer"] + " " + row["model"])
                return _json(await _upsell_view())
            if op == "save":
                async with _upsell_lock:
                    d = _load_upsell()
                    if "offers" in body:
                        offers, e = _upsell_clean_offers(body.get("offers"), d)
                        if e:
                            return _json({"error": e}, 400)
                        d["offers"] = offers
                    if "warranties" in body:
                        ids = {p["id"] for p in await _upsell_projector_list()}
                        ws, e = _upsell_clean_warranties(body.get("warranties"), ids)
                        if e:
                            return _json({"error": e}, 400)
                        d["warranties"] = ws
                    if "settings" in body:
                        st, e = _upsell_clean_settings(body.get("settings"))
                        if e:
                            return _json({"error": e}, 400)
                        d["settings"] = st
                    _write_upsell(d)
                _track(who, "upsell", "changed the offers", ", ".join(k for k in ("offers", "warranties", "settings")
                                                                    if k in body))
                return _json(await _upsell_view())
            if op == "replace_code":
                async with _upsell_lock:
                    d = _load_upsell()
                    off = next((o for o in d["offers"] if o.get("id") == str(body.get("id") or "")), None)
                    if not off:
                        return _json({"error": "That offer is not there any more."}, 404)
                    off["code"] = _upsell_new_code()
                    _write_upsell(d)
                _track(who, "upsell", "replaced an offer code", off["code"])
                return _json(await _upsell_view())
            if op in ("plan", "publish"):
                r = await _upsell_publish(registry, who, execute=(op == "publish"), trial=bool(body.get("trial")))
                return _json(r, 200 if r.get("ok") else 409)
            return _json({"error": "Unknown request."}, 400)
        except StoreUnwritable:
            return _json({"error": "The upsell settings could not be saved just now. Nothing was changed."}, 503)
```

- [ ] **Step 5: Run it to see it pass**

Run: `ONLY=t_the_upsell_page_is env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>&1 | tail -2`
Expected: `1 passed, 0 failed`

- [ ] **Step 6: Commit**

```bash
git add copilot.py tests/test_dispatch.py
git commit -m "Upsell: the page's route, admins only, checking every value before it is kept

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Phase 4: Orders, production and the hourly job

### Task 11: A warranty line is never made or sent

**Files:**
- Modify: `copilot.py` (new helpers beside `_label_skip_item` ~6021; nine call sites; `run_production_labels` ~6947; `_sync_order_tags` ~6126; `_release_tags` ~6433)
- Test: `tests/test_dispatch.py`

**Interfaces:**
- Produces:
  - `UPSELL_WTY_RE = re.compile(r"^WTY-(\d+)-(\d+)$")`
  - `_is_warranty_line(li) -> bool`
  - `_line_is_charge(li) -> bool` (a shipping charge or a warranty)
  - `_warranty_only(o) -> bool`
  - `_release_refusal(o) -> str`
  - `_sync_order_tags(..., refuse=None)`: when `refuse(order)` returns a reason, nothing is written and `(False, reason)` comes back

- [ ] **Step 1: Write the failing test**

```python
@test
def t_a_warranty_line_is_never_made_or_sent():
    """Spec section 7: a WTY- line is treated like a shipping charge everywhere
    (label, weight, customs, the waybill), an order of nothing but warranties
    never shows in a queue, and releasing one to the bench is refused."""
    wl = {"id": 71, "title": "Extended warranty, 20 Watt LED", "sku": "WTY-100-2", "quantity": 1,
          "current_quantity": 1, "grams": 500, "price": "49.00", "product_id": 9100, "variant_title": "2 years",
          "properties": []}
    gobo = dict(ORDER["line_items"][0], price="49.00")
    ok(copilot._line_is_charge(wl) and not copilot._line_is_charge(gobo))
    ok(copilot._line_is_charge({"title": "Additional shipping charge"}), "the shipping charge still is one")
    eq(copilot._warranty_only({"line_items": [wl]}), True)
    eq(copilot._warranty_only({"line_items": [wl, gobo]}), False)
    eq(copilot._warranty_only({"line_items": [wl, {"title": "Additional shipping charge"}]}), True)
    eq(copilot._warranty_only({"line_items": []}), False)
    mixed, gobo_only = dict(ORDER, line_items=[gobo, wl]), dict(ORDER, line_items=[gobo])
    shaped = copilot._shape_label_order(mixed, {}, cache=copilot._gobo_sizes(), types={})
    eq(len(shaped["items"]), 1, "the label shows the gobo only")
    eq(copilot._order_weight_kg(mixed), copilot._order_weight_kg(gobo_only), "a warranty weighs nothing")
    eq(copilot._order_goods_value(mixed), copilot._order_goods_value(gobo_only), "and declares nothing to customs")
    ok("warranty" not in copilot._goods_summary(mixed).lower(), "and is not on the waybill")
    only = dict(ORDER, id=801, tags="Unprocessed", line_items=[wl])
    async def tj(registry, name, args):
        if name == "shopify_list_orders":
            return {"orders": [only, dict(ORDER, id=802, tags="Unprocessed")]}
        if name == "shopify_get_order":
            return dict(only)
        return await fake_tool_json(registry, name, args)
    copilot._tool_json = tj
    try:
        r = run_async(copilot.run_production_labels({}, tag=copilot.UNPROCESSED_TAG, days=30, fresh=True))
        eq([o["id"] for o in r["orders"]], [802], "a warranty-only order never shows in a queue")
        TAG_WRITES.clear()
        okd, note, released = run_async(copilot._release_tags({}, 801))
        eq((okd, released), (False, False))
        ok("only a warranty" in note, note)
        eq(TAG_WRITES, [], "and nothing was written")
    finally:
        copilot._tool_json = fake_tool_json
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "copilot.py"), encoding="utf-8").read()
    eq(len(re.findall(r"_label_skip_item\(", src)), 3,
       "every line check goes through _line_is_charge: the title rule appears only in its own definition, "
       "in _line_is_charge and in _warranty_only")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_a_warranty_line env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>&1 | tail -3`
Expected: `FAIL ... no attribute '_line_is_charge'`

- [ ] **Step 3: Add the helpers**

Below `_label_skip_item` in `copilot.py`:

```python
UPSELL_WTY_RE = re.compile(r"^WTY-(\d+)-(\d+)$")


def _is_warranty_line(li: dict) -> bool:
    """A warranty the Upsell page sells: Reactor sets its SKU, WTY-<projector>-<years>."""
    return bool(UPSELL_WTY_RE.match(str(li.get("sku") or "").strip()))


def _line_is_charge(li: dict) -> bool:
    """Charges, not things to build or send: the shipping charge, or a warranty."""
    return _label_skip_item(str(li.get("title") or li.get("name") or "")) or _is_warranty_line(li)


def _warranty_only(o: dict) -> bool:
    """Nothing on the order to make or send: warranties, and at most a shipping charge."""
    items = [li for li in (o.get("line_items") or [])
             if not _label_skip_item(str(li.get("title") or li.get("name") or ""))]
    return bool(items) and all(_is_warranty_line(li) for li in items)


def _release_refusal(o: dict) -> str:
    if _warranty_only(o):
        return "That order is only a warranty: there is nothing to make or send."
    return ""
```

- [ ] **Step 4: Switch every line check to it**

Replace each of these at the listed call sites only (~6672, ~6760, ~6828, ~7341, ~7642, ~9087). Do not use a file-wide replace: the two copies inside `_line_is_charge` and `_warranty_only`, added in Step 3, match too, and replacing the one in `_line_is_charge` makes it call itself forever:

```python
_label_skip_item(str(li.get("title") or li.get("name") or ""))
```

with `_line_is_charge(li)`. At ~7760 the same expression sits inside `if not ...`; replace it the same way. In `_goods_summary` (~7369) change `if not t or _label_skip_item(t):` to `if not t or _line_is_charge(li):`, and in the overdue-customer loop (~9976) change `if _label_skip_item(title):` to `if _line_is_charge(li):`. Afterwards `grep -n "_label_skip_item(" copilot.py` shows exactly three: its definition, the call inside `_line_is_charge`, and the one inside `_warranty_only`.

- [ ] **Step 5: Leave warranty-only orders out of the queues, and refuse to release them**

In `run_production_labels`, change:

```python
    tagged = [o for o in orders if any(_has_tag(o, t) for t in want)]
```

to:

```python
    tagged = [o for o in orders if any(_has_tag(o, t) for t in want) and not _warranty_only(o)]
```

In `_sync_order_tags`, add `refuse=None` to the signature after `outcome`:

```python
async def _sync_order_tags(registry: dict, order_id, add=(), remove=(), unless=(),
                           allow_dead: bool = False, outcome: Optional[dict] = None,
                           refuse=None) -> tuple:
```

and immediately after the `if not _ok(o) or not o.get("id"):` check add:

```python
            if refuse is not None:
                why = refuse(o)
                if why:
                    return False, why
```

In `_release_tags`, pass it:

```python
    okd, note = await _sync_order_tags(registry, order_id, add=[PRODUCTION_TAG],
                                       remove=[UNPROCESSED_TAG],
                                       unless=(MADE_TAG, DISPATCHED_TAG, *LEGACY_DISPATCHED_TAGS),
                                       outcome=out, refuse=_release_refusal)
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `ONLY=t_a_warranty_line env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>&1 | tail -2`
Expected: `1 passed, 0 failed`. Then run the whole suite once (`env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>&1 | tail -1`), because nine call sites changed: expected `0 failed`.

- [ ] **Step 7: Commit**

```bash
git add copilot.py tests/test_dispatch.py
git commit -m "Upsell: a warranty line is never made, weighed, declared or sent, and a warranty-only order is never released

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Results, the warranty register, refunds, and warranty-only orders fulfilled

**Files:**
- Modify: `copilot.py` (Upsell section; the orders webhook ~18933; the `/api/upsell` route)
- Test: `tests/test_dispatch.py`

**Interfaces:**
- Consumes: `_is_warranty_line`, `_warranty_only`, `UPSELL_WTY_RE` (Task 11); stores (Task 5); `_upsell_ops["metafield_set"]` (Task 8); `UPSELL_NEEDED_SCOPES`, `upsell_test` (Task 9); existing `_scope_reader`, `_line_qty(li)`, `_fulfillment_writer`, `_dispatch_move_tags`, `_tool_json`, `_spawn_bg`
- Produces:
  - `_upsell_attrs(o) -> {name: value}` from `note_attributes`
  - `_upsell_line_projector(li, d) -> str` (projector id digits, by product id or listed SKU)
  - `_upsell_add_years(day, years) -> str`, `_upsell_cover(covered_order, standard_years, years) -> (start, end)`
  - `async _upsell_check_sale(registry, o, li, pid, years, after, d) -> sale`
  - `async _upsell_flag_order(order_id) -> None`: sets the covered order's `$app`/`warranty` to the JSON list of covered projector ids
  - `async _upsell_note_order(registry, o) -> None` (one at a time under `_upsell_note_lock`, which also guards the route's `sale` op; the body is `_upsell_note_order_locked`)
  - `_upsell_note_order_soon(registry, body_txt) -> None` (webhook hand-off)
  - Sale record: `{"order_id", "order_name", "email", "customer", "projector_id", "years", "qty", "covered_order_id", "covered_order_name", "status": "active"|"needs_look"|"accepted"|"void"|"returned", "reason", "start", "end", "total", "at"}`, keyed `"<order id>:<line id>"`
  - Result record: `{"offer": offer id|"warranty", "via": "card"|"typed", "total", "refunded", "cancelled", "at", "trial"}`, keyed by order id; `total` and `refunded` are before VAT and shipping (`subtotal_price`, `current_subtotal_price`)
  - `/api/upsell` op `sale` with `{"id", "decision": "accept"|"refunded"}`

- [ ] **Step 1: Write the failing test**

```python
@test
@upsell_test
def t_a_warranty_counts_only_for_its_own_customers_projector():
    """Spec section 7: a warranty sale is checked before it counts (same
    customer, a projector of that model still on the order, not already
    covered, inside the window); anything else waits for an admin; cover runs
    from the day after the standard guarantee, counted from dispatch; refunds
    void it; a warranty-only order is fulfilled without a shipping email; and
    offer sales are counted by card or by a code typed by hand."""
    upsell_reset()
    d = copilot._load_upsell()
    d["made"]["codes"]["u1"] = {"id": "gid://shopify/DiscountCodeNode/1", "code": "K7Q2M9TX", "product_id": "100"}
    copilot._write_upsell(d)
    covered = dict(ORDER, id=5001, name="#105001", email="buyer@acme.co.uk", created_at="2026-10-01T10:00:00Z",
                   line_items=[{"id": 1, "title": "20 Watt LED Gobo Projector", "product_id": 100, "sku": "P220",
                                "quantity": 1, "current_quantity": 1, "price": "335.00"}],
                   fulfillments=[{"created_at": "2026-10-03T09:00:00Z", "status": "success"}])
    def wty(oid, email="buyer@acme.co.uk", at="2026-10-05T10:00:00Z", after="5001", qty=1, attrs=True):
        return dict(ORDER, id=oid, name="#10%d" % oid, email=email, created_at=at, financial_status="paid",
                    fulfillment_status=None, tags="Unprocessed",
                    subtotal_price="49.00", current_subtotal_price="49.00" if qty else "0.00",
                    note_attributes=([{"name": "reactor_offer", "value": "warranty"},
                                      {"name": "reactor_after", "value": after}] if attrs else []),
                    line_items=[{"id": 9, "title": "Extended warranty, 20 Watt LED", "sku": "WTY-100-2",
                                 "quantity": 1, "current_quantity": qty, "price": "49.00", "product_id": 9100}])
    orders = {5001: covered}
    async def tj(registry, name, args):
        if name == "shopify_get_order":
            await asyncio.sleep(0)            # a real read gives way to other work
            return dict(orders.get(int(args["order_id"]), {}))
        return await fake_tool_json(registry, name, args)
    copilot._tool_json = tj
    try:
        FULFILLED.clear(); TAG_WRITES.clear()
        good = wty(6001)
        orders[6001] = good
        run_async(copilot._upsell_note_order({}, good))
        s = copilot._load_warranties()["sales"]["6001:9"]
        eq((s["status"], s["covered_order_name"], s["years"]), ("active", "#105001", 2))
        eq((s["start"], s["end"]), ("2027-10-04", "2029-10-03"),
           "cover starts the day after a year's guarantee from dispatch on 3 Oct, and runs two years")
        flags = [c for c in UPSELL_CALLS if c[0] == "metafield_set"]
        eq((flags[-1][1], flags[-1][2], flags[-1][3]), ("gid://shopify/Order/5001", "warranty", ["100"]),
           "the covered order stops offering it")
        eq(copilot._load_warranties()["results"]["6001"]["offer"], "warranty")
        eq(FULFILLED[-1]["notify"], False, "a warranty-only order is fulfilled without a shipping email")
        ok(any(o == 6001 and "Complete" in t for o, t in TAG_WRITES), "and moved to Complete")
        for oid, kw, why in ((6002, {"email": "someone@else.test"}, "another customer"),
                             (6003, {"at": "2026-12-01T10:00:00Z"}, "window"),
                             (6004, {}, "already covered"),
                             (6005, {"attrs": False}, "without the thank-you page")):
            o = wty(oid, **kw)
            orders[oid] = o
            run_async(copilot._upsell_note_order({}, o))
            s = copilot._load_warranties()["sales"]["%d:9" % oid]
            eq(s["status"], "needs_look", why)
            ok(why in s["reason"], s["reason"])
        eq(len([c for c in UPSELL_CALLS if c[0] == "metafield_set"]), len(flags), "none of those flags an order")
        refunded = wty(6001, qty=0)
        orders[6001] = refunded
        run_async(copilot._upsell_note_order({}, refunded))
        eq(copilot._load_warranties()["sales"]["6001:9"]["status"], "void", "a refunded warranty voids its cover")
        eq([c for c in UPSELL_CALLS if c[0] == "metafield_set"][-1][3], [], "and the order offers it again")
        eq(copilot._load_warranties()["results"]["6001"]["refunded"], "49.00")
        a, b = wty(6101), wty(6102)
        a["line_items"][0]["sku"] = b["line_items"][0]["sku"] = "WTY-100-1"
        a["email"] = b["email"] = "someone@else.test"
        async def both():
            await asyncio.gather(copilot._upsell_note_order({}, a), copilot._upsell_note_order({}, b))
        run_async(both())
        ok({"6101:9", "6102:9"} <= set(copilot._load_warranties()["sales"]), "two warranty orders at once are both kept")
        pending = wty(6103)
        pending["financial_status"] = "pending"
        run_async(copilot._upsell_note_order({}, pending))
        ok("6103:9" not in copilot._load_warranties()["sales"] and "6103" not in copilot._load_warranties()["results"],
           "an unpaid order starts no sale and no result")
        orders[6006] = wty(6006)
        run_async(copilot._upsell_note_order({}, orders[6006]))
        eq(copilot._load_warranties()["sales"]["6006:9"]["status"], "active", "the unit is free again after the refund")
        run_async(copilot._upsell_note_order({}, dict(covered, cancelled_at="2026-10-20T10:00:00Z")))
        eq(copilot._load_warranties()["sales"]["6006:9"]["status"], "returned", "a covered order cancelled marks its cover")
        ok(any(x["id"] == "6006:9" for x in copilot._upsell_needs_look()), "and the page lists it for an admin")
        up = dict(ORDER, id=7001, subtotal_price="284.75", current_subtotal_price="284.75",
                  note_attributes=[{"name": "reactor_offer", "value": "u1"}],
                  discount_codes=[{"code": "K7Q2M9TX"}], line_items=[covered["line_items"][0]])
        typed = dict(up, id=7002, note_attributes=[])
        run_async(copilot._upsell_note_order({}, up))
        run_async(copilot._upsell_note_order({}, typed))
        res = copilot._load_warranties()["results"]
        eq((res["7001"]["offer"], res["7001"]["via"]), ("u1", "card"))
        eq((res["7002"]["offer"], res["7002"]["via"]), ("u1", "typed"), "a code typed by hand counts apart")
        def go():
            ensure_auth()
            r = post("/api/upsell", {"op": "sale", "id": "6005:9", "decision": "accept"})
            eq(r.status_code, 200, r.text[:200])
            eq(copilot._load_warranties()["sales"]["6005:9"]["status"], "accepted")
            post("/api/upsell", {"op": "sale", "id": "6002:9", "decision": "refunded"})
            eq(copilot._load_warranties()["sales"]["6002:9"]["status"], "void")
            r = post("/api/upsell", {"op": "sale", "id": "6006:9", "decision": "accept"})
            eq(r.status_code, 400, "a returned cover cannot be accepted, only marked refunded")
            post("/api/upsell", {"op": "sale", "id": "6006:9", "decision": "refunded"})
            eq(copilot._load_warranties()["sales"]["6006:9"]["status"], "void")
        with_accounts(go)
    finally:
        copilot._tool_json = fake_tool_json
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_a_warranty_counts env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>&1 | tail -3`
Expected: `FAIL ... no attribute '_upsell_note_order'`

- [ ] **Step 3: Implement**

Add to the Upsell section (`timedelta` is already imported in `copilot.py`; if not, add it to the `datetime` import):

```python
def _upsell_attrs(o: dict) -> dict:
    return {str(a.get("name") or ""): str(a.get("value") or "")
            for a in (o.get("note_attributes") or []) if isinstance(a, dict)}


def _upsell_line_projector(li: dict, d: dict) -> str:
    ws = d.get("warranties") or {}
    pid = re.sub(r"\D", "", str(li.get("product_id") or ""))
    if pid and pid in ws:
        return pid
    sku = str(li.get("sku") or "").strip()
    return next((p for p, w in ws.items() if sku and sku in (w.get("skus") or [])), "")


def _upsell_add_years(day: str, years: int) -> str:
    y, m, dd = (int(x) for x in day.split("-"))
    try:
        return datetime(y + years, m, dd).date().isoformat()
    except ValueError:                        # 29 February
        return datetime(y + years, m, 28).date().isoformat()


def _upsell_cover(covered: dict, standard_years: int, years: int) -> tuple:
    """(start, end): from the day after the standard guarantee ends, counted
    from the covered order's first fulfilment (its order date while it has
    none), for the chosen number of years."""
    dates = sorted(str(f.get("created_at") or "")[:10] for f in (covered.get("fulfillments") or [])
                   if f.get("created_at") and f.get("status") in (None, "success"))
    base = dates[0] if dates else str(covered.get("created_at") or "")[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", base):
        return "", ""
    std_end = _upsell_add_years(base, standard_years)
    start = (datetime.fromisoformat(std_end) + timedelta(days=1)).date().isoformat()
    return start, _upsell_add_years(std_end, years)


def _upsell_when(v) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


async def _upsell_check_sale(registry: dict, o: dict, li: dict, pid: str, years: int,
                             after: str, d: dict) -> dict:
    """Spec section 7: a warranty counts only for its own customer's projector,
    once per unit, inside the window. Anything else waits for an admin."""
    cust = o.get("customer") or {}
    email = str(o.get("email") or "").strip().lower()
    sale = {"order_id": str(o.get("id")), "order_name": str(o.get("name") or ""), "email": email,
            "customer": " ".join(x for x in (cust.get("first_name"), cust.get("last_name")) if x).strip(),
            "projector_id": pid, "years": years, "qty": max(1, _line_qty(li)),
            "covered_order_id": re.sub(r"\D", "", after or ""), "covered_order_name": "",
            "status": "needs_look", "reason": "", "start": "", "end": "",
            "total": _upsell_money(li.get("price")), "at": str(o.get("created_at") or "")}
    if not sale["covered_order_id"]:
        sale["reason"] = "Bought without the thank-you page's link, so the projector it covers is not known."
        return sale
    try:
        cov = await _tool_json(registry, "shopify_get_order", {"order_id": int(sale["covered_order_id"])})
    except Exception:
        cov = {}
    if not _ok(cov) or not cov.get("id"):
        sale["reason"] = "The order it names could not be found."
        return sale
    sale["covered_order_name"] = str(cov.get("name") or "")
    if not email or str(cov.get("email") or "").strip().lower() != email:
        sale["reason"] = "It names another customer's order."
        return sale
    if cov.get("cancelled_at"):
        sale["reason"] = "The order it covers was cancelled."
        return sale
    # The window before the units: a late sale is late whatever else is true.
    window = int((d.get("settings") or {}).get("window_days") or 30)
    a, b = _upsell_when(o.get("created_at")), _upsell_when(cov.get("created_at"))
    gap = (a - b).days if a and b else window + 1
    if gap > window:
        sale["reason"] = "Bought %d days after the order it covers, past the %d-day window." % (gap, window)
        return sale
    units = sum(_line_qty(x) for x in (cov.get("line_items") or []) if _upsell_line_projector(x, d) == pid)
    if units <= 0:
        sale["reason"] = "That order has no projector this warranty is for."
        return sale
    taken = sum(int(s.get("qty") or 0) for s in _load_warranties()["sales"].values()
                if s.get("covered_order_id") == sale["covered_order_id"] and s.get("projector_id") == pid
                and s.get("status") in ("active", "accepted"))
    if taken + sale["qty"] > units:
        sale["reason"] = "Every unit on that order is already covered."
        return sale
    std = int(((d.get("warranties") or {}).get(pid) or {}).get("standard_years") or 0)
    sale["start"], sale["end"] = _upsell_cover(cov, std, years)
    sale["status"] = "active"
    return sale


async def _upsell_flag_order(order_id: str) -> None:
    """The covered order's $app/warranty: the projector ids now covered, so its
    order status page stops offering them. Built from the register, not read
    back from Shopify."""
    if _upsell_ops is None or not order_id:
        return
    pids = sorted({s["projector_id"] for s in _load_warranties()["sales"].values()
                   if s.get("covered_order_id") == order_id and s.get("status") in ("active", "accepted")})
    try:
        await _upsell_ops["metafield_set"]("gid://shopify/Order/" + order_id, "warranty", json.dumps(pids))
    except Exception:
        logger.exception("upsell: could not flag order %s", order_id)


_upsell_note_lock = asyncio.Lock()


async def _upsell_note_order(registry: dict, o: dict) -> None:
    """One order at a time: the register is read, checked against Shopify and
    written back, and two at once would each drop the other's sale."""
    async with _upsell_note_lock:
        await _upsell_note_order_locked(registry, o)


async def _upsell_note_order_locked(registry: dict, o: dict) -> None:
    """What an arriving or changed order means for the offers."""
    oid = str(o.get("id") or "")
    if not oid or _upsell_ops is None:
        return
    # Spec section 8: nothing is registered or fulfilled until Shopify has
    # granted every new permission (the answer is cached for 15 minutes).
    if _scope_reader is not None:
        try:
            granted = set((await _scope_reader()).get("scopes") or [])
        except Exception:
            granted = set()
        if not all(s in granted for s in UPSELL_NEEDED_SCOPES):
            return
    # Orders are read only once paid (the Quote Engine rule): an unpaid order
    # starts no result and no sale, though one already recorded still follows
    # its refunds and cancellation.
    paid = str(o.get("financial_status") or "") in ("paid", "partially_paid", "partially_refunded", "refunded")
    d = _load_upsell()
    made_codes = {str(m.get("code") or "").upper(): k for k, m in (d["made"].get("codes") or {}).items()}
    attrs = _upsell_attrs(o)
    offer = attrs.get("reactor_offer", "")
    codes = [str(c.get("code") or "").upper() for c in (o.get("discount_codes") or []) if isinstance(c, dict)]
    by_code = next((made_codes[c] for c in codes if c in made_codes), "")
    wlines = [li for li in (o.get("line_items") or []) if _is_warranty_line(li)]
    w = _load_warranties()
    seen = set(w["sales"])
    changed, touched = False, set()
    # Before VAT and shipping, as the Results card says: the shop's prices
    # exclude VAT, and total_price would add both.
    total = float(o.get("subtotal_price") or 0)
    cur = o.get("current_subtotal_price")
    current = float(cur if cur not in (None, "") else total)
    if (wlines or (offer and offer != "warranty") or by_code) and (paid or oid in w["results"]):
        rec = {"offer": "warranty" if wlines else (offer if offer and offer != "warranty" else by_code),
               "via": "card" if offer else "typed", "total": _upsell_money(total),
               "refunded": _upsell_money(max(0.0, total - current)), "cancelled": bool(o.get("cancelled_at")),
               "at": str(o.get("created_at") or ""),
               # Spec section 9: trial orders are left out of Results.
               "trial": bool((w["results"].get(oid) or {}).get("trial")) or bool(d["published"].get("trial"))}
        if w["results"].get(oid) != rec:
            w["results"][oid], changed = rec, True
    for li in wlines:
        m = UPSELL_WTY_RE.match(str(li.get("sku") or "").strip())
        pid, years = m.group(1), int(m.group(2))
        sid = oid + ":" + str(li.get("id") or pid)
        sale = w["sales"].get(sid)
        if sale is None and not paid:
            continue
        if sale is None:
            sale = await _upsell_check_sale(registry, o, li, pid, years, attrs.get("reactor_after", ""), d)
            w["sales"][sid], changed = sale, True
            if sale["status"] == "active":
                touched.add(sale["covered_order_id"])
        if sale.get("status") in ("active", "accepted", "needs_look") and (o.get("cancelled_at") or _line_qty(li) <= 0):
            if sale["status"] in ("active", "accepted"):
                touched.add(sale.get("covered_order_id") or "")
            sale["status"], sale["reason"], changed = "void", "The warranty was refunded or cancelled.", True
    for sale in w["sales"].values():
        if sale.get("covered_order_id") == oid and sale.get("status") in ("active", "accepted"):
            still = any(_upsell_line_projector(x, d) == sale.get("projector_id") and _line_qty(x) > 0
                        for x in (o.get("line_items") or []))
            if o.get("cancelled_at") or not still:
                sale["status"] = "returned"
                sale["reason"] = "The projector it covers was returned or its order cancelled: refund the warranty."
                changed = True
                touched.add(oid)
    if changed:
        # An erasure is synchronous and takes no lock, so it may have run while
        # Shopify was being asked: what it removed stays removed, and what it
        # noted stays noted.
        now_sales = _load_warranties()["sales"]
        for k in [k for k in w["sales"] if k in seen and k not in now_sales]:
            w["sales"].pop(k)
        for k, s0 in now_sales.items():
            if s0.get("redacted_request_at") and k in w["sales"]:
                w["sales"][k].setdefault("redacted_request_at", s0["redacted_request_at"])
        _write_warranties(w)
    for t in sorted(x for x in touched if x):
        await _upsell_flag_order(t)
    if (_warranty_only(o) and str(o.get("financial_status") or "") == "paid" and not o.get("cancelled_at")
            and str(o.get("fulfillment_status") or "") != "fulfilled" and _fulfillment_writer is not None):
        r = await _fulfillment_writer(int(oid), notify_customer=False)
        if r.get("ok") or r.get("reason") == "nothing_to_fulfill":
            await _dispatch_move_tags(registry, oid, allow_dead=True)


def _upsell_note_order_soon(registry: dict, body_txt: str) -> None:
    async def later():
        try:
            await _upsell_note_order(registry, json.loads(body_txt))
        except Exception:
            logger.exception("upsell: order note failed")
    _spawn_bg(later())
```

In the orders webhook, right after `_crm_link_order_soon(raw.decode("utf-8", "replace"))` inside the same `try:`, add:

```python
            _upsell_note_order_soon(registry, raw.decode("utf-8", "replace"))
```

In the `/api/upsell` route, before the final `return _json({"error": "Unknown request."}, 400)`, add:

```python
            if op == "sale":
                # The register's own lock: an order arriving now must not
                # write over this decision, nor this over its sale.
                async with _upsell_note_lock:
                    sid = str(body.get("id") or "")
                    sale = _load_warranties()["sales"].get(sid) or {}
                    cov = {}
                    if (body.get("decision") == "accept" and sale.get("status") == "needs_look"
                            and not sale.get("start") and sale.get("covered_order_id")):
                        # Cover counts from the covered order's dispatch when it
                        # is known, as for any other sale (spec section 7).
                        try:
                            cov = await _tool_json(registry, "shopify_get_order",
                                                   {"order_id": int(sale["covered_order_id"])})
                        except Exception:
                            cov = {}
                    # Read again after asking Shopify: an erasure takes no lock.
                    w = _load_warranties()
                    sale = w["sales"].get(sid)
                    if not sale or sale.get("status") not in ("needs_look", "returned"):
                        return _json({"error": "That sale is not waiting any more."}, 404)
                    if body.get("decision") == "accept" and sale["status"] == "needs_look":
                        sale["status"], sale["reason"] = "accepted", "Accepted by " + (_team_name(who) or "an admin")
                        if not sale.get("start"):
                            std = int((_load_upsell()["warranties"].get(sale["projector_id"]) or {})
                                      .get("standard_years") or 0)
                            if not _ok(cov) or not cov.get("id"):
                                cov = {"created_at": str(sale.get("at") or "")[:10]
                                       or datetime.now(timezone.utc).date().isoformat()}
                            sale["start"], sale["end"] = _upsell_cover(cov, std, int(sale["years"]))
                    elif body.get("decision") == "refunded":
                        sale["status"], sale["reason"] = "void", "Refunded by " + (_team_name(who) or "an admin")
                    else:
                        return _json({"error": "Accept it, or say it was refunded." if sale["status"] == "needs_look"
                                      else "Say it was refunded once the warranty is refunded in Shopify."}, 400)
                    _write_warranties(w)
                    if sale["status"] == "accepted":
                        await _upsell_flag_order(sale.get("covered_order_id") or "")
                _track(who, "upsell", "settled a warranty sale", sale.get("order_name", "") + " " + sale["status"])
                return _json(await _upsell_view())
```

- [ ] **Step 4: Run it to see it pass**

Run: `ONLY=t_a_warranty_counts env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>&1 | tail -2`
Expected: `1 passed, 0 failed`

- [ ] **Step 5: Commit**

```bash
git add copilot.py tests/test_dispatch.py
git commit -m "Upsell: results by card or typed code, a checked warranty register, refunds voiding cover, warranty-only orders fulfilled quietly

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 13: The hourly check: new spellings, prices, drift and missed orders

**Files:**
- Modify: `copilot.py` (Upsell section; `_scheduler_loop` ~11366; the `/api/upsell` route)
- Test: `tests/test_dispatch.py`

**Interfaces:**
- Consumes: Tasks 5 to 12; existing `_paginate_orders`, `_add_alerts`, `_send_alert_email`, `_track`
- Produces:
  - `UPSELL_TICK_SECS = 3300`
  - `async _upsell_refresh_published() -> None`: rebuilds the document from the **last published config** with fresh keys and facts, and writes it only when the fingerprint changed
  - `async _upsell_check_drift() -> None`: fills `store["drift"]` with `{"id", "kind": "code"|"warranty", "ref", "text", "shopify": {...}}`
  - `async _upsell_tick(registry, shopify_up: bool) -> None`
  - `/api/upsell` op `drift` with `{"id", "choice": "keep"|"restore"}`

- [ ] **Step 1: Write the failing test**

```python
@test
@upsell_test
def t_the_hourly_upsell_check_keeps_what_shoppers_see_current():
    """Spec sections 6 and 8: once something is published, the hourly job adds
    new spellings and follows price changes without an admin, from the last
    published offers only; flags a code deleted in Shopify with a choice; and
    runs at most once an hour."""
    upsell_reset()
    run_async(copilot._upsell_tick({}, True))
    eq([c for c in UPSELL_CALLS if c[0] == "metafield_set"], [], "nothing runs before anything is published")
    upsell_reset()
    run_async(copilot._upsell_publish({}, "cameron", execute=True))
    d = copilot._load_upsell()
    d["tick_at"] = ""
    d["offers"][0]["headline"] = "An unpublished edit"
    copilot._write_upsell(d)
    facts = json.loads(json.dumps(UPSELL_FACTS))
    facts["100"]["variants"][0]["price"] = "299.00"
    UPSELL_FAKE["facts"] = facts
    now = datetime.now(timezone.utc).isoformat()
    fresh = dict(ORDER, id=8001, created_at=now, customer={"id": 99}, line_items=[
        {"id": 1, "title": "Gobo", "properties": [{"name": "Manufacturer", "value": "Robe"},
                                                   {"name": "Model", "value": "Spot-160"}]}])
    async def tj(registry, name, args):
        if name == "shopify_list_orders":
            return {"orders": [fresh]}
        return await fake_tool_json(registry, name, args)
    copilot._tool_json = tj
    try:
        UPSELL_CALLS.clear()
        run_async(copilot._upsell_tick({}, True))
        sets = [c for c in UPSELL_CALLS if c[0] == "metafield_set" and c[2] == "upsell"]
        eq(len(sets), 1, "one refreshed publish")
        u = sets[0][3]["upgrades"][0]
        eq(u["keys"], ["robe|spot 160", "robe|spot-160"], "a new spelling of the row is added")
        eq(u["product"]["price"], "299.00", "and the new price")
        eq(u["headline"], "H", "but not an admin's unpublished edit")
        eq(copilot._load_upsell()["published"]["config"]["offers"][0]["headline"], "H")
        UPSELL_CALLS.clear()
        run_async(copilot._upsell_tick({}, True))
        eq(UPSELL_CALLS, [], "at most once an hour")
        async def gone(gid):
            return {"exists": False, "status": "", "ends": "", "code": "", "uses": 0}
        UPSELL_FAKE_OPS["code_state"] = gone
        d = copilot._load_upsell()
        d["tick_at"] = ""
        copilot._write_upsell(d)
        run_async(copilot._upsell_tick({}, True))
        drift = copilot._load_upsell()["drift"]
        eq([x["id"] for x in drift], ["code:u1"])
        ok("deleted in Shopify" in drift[0]["text"], drift[0]["text"])
    finally:
        copilot._tool_json = fake_tool_json
        UPSELL_FAKE_OPS["code_state"] = _u_code_state
    def go():
        ensure_auth()
        eq(post("/api/upsell", {"op": "drift", "id": "code:u1", "choice": "restore"}).status_code, 200)
        eq(copilot._load_upsell()["drift"], [])
        ok(not copilot._load_upsell()["made"]["codes"]["u1"].get("id"), "the code will be made again")
        UPSELL_CALLS.clear()
        post("/api/upsell", {"op": "publish"})
        ok(any(c[0] == "code_upsert" and c[1] is None for c in UPSELL_CALLS), "and the next publish makes it")
    with_accounts(go)


@test
@upsell_test
def t_an_oversized_rules_document_is_refused_and_the_refresh_raises_an_alert():
    """Spec section 8, size: Publish refuses a document over the cap, and an
    automatic refresh that would go over keeps the last rules and raises an alert."""
    upsell_reset()
    real_max = copilot.UPSELL_DOC_MAX
    try:
        copilot.UPSELL_DOC_MAX = 200
        r = run_async(copilot._upsell_publish({}, "cameron", execute=True))
        ok(not r["ok"] and "100 KB" in r["error"], r)
        ok(not [c for c in UPSELL_CALLS if c[0] == "metafield_set"], "nothing was published")
        copilot.UPSELL_DOC_MAX = real_max
        run_async(copilot._upsell_publish({}, "cameron", execute=True))
        facts = json.loads(json.dumps(UPSELL_FACTS))
        facts["100"]["title"] = "20 Watt, renamed"
        UPSELL_FAKE["facts"] = facts
        copilot.UPSELL_DOC_MAX = 200
        UPSELL_CALLS.clear()
        run_async(copilot._upsell_refresh_published())
        ok(not [c for c in UPSELL_CALLS if c[0] == "metafield_set"], "the last rules stay")
        ok("100 KB" in copilot._load_upsell()["last_error"], "the page says why")
        ok(any(a.get("tab") == "upsell" for a in copilot._load_alerts()), "and an alert is raised")
    finally:
        copilot.UPSELL_DOC_MAX = real_max
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_the_hourly_upsell env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>&1 | tail -3`
Expected: `FAIL ... no attribute '_upsell_tick'`

- [ ] **Step 3: Implement**

Add to the Upsell section:

```python
UPSELL_TICK_SECS = 3300


def _upsell_fact_ids(cfg: dict, made: dict) -> list:
    ids = {str(o.get("product_id") or "") for o in (cfg.get("offers") or []) if o.get("on")}
    ids |= set(cfg.get("warranties") or {})
    ids |= {_gid_digits(m.get("id")) for m in (made.get("warranty_products") or {}).values()}
    return sorted(i for i in ids if i)


async def _upsell_refresh_published() -> None:
    """Machine-kept fields only: keys, prices, titles, images, availability,
    rebuilt from the LAST PUBLISHED offers. An admin's change needs Publish."""
    d = _load_upsell()
    pub = d["published"]
    cfg = pub.get("config")
    if not cfg:
        return
    facts = await _upsell_ops["product_facts"](_upsell_fact_ids(cfg, d["made"]))
    doc, problems = _upsell_build_doc(cfg, _upsell_keys(d), facts, d["made"], trial=bool(pub.get("trial")))
    if _upsell_fingerprint(doc) == pub.get("fingerprint"):
        return
    body = _upsell_doc_json(doc)
    if len(body.encode("utf-8")) > UPSELL_DOC_MAX:
        msg = ("The upsell offers grew past 100 KB, so what shoppers see was not brought up to date. "
               "Turn some offers off and publish again.")
        if d["last_error"] != msg:
            d["last_error"] = msg
            _write_upsell(d)
            _add_alerts([{"tab": "upsell", "tab_label": "Upsell", "metric": msg, "pct": None}])
            await _send_alert_email("Reactor: the upsell offers could not be brought up to date", [msg])
        return
    r = await _upsell_ops["metafield_set"](await _upsell_ops["shop_id"](), "upsell", body)
    if not r.get("ok"):
        logger.warning("upsell: refresh refused: %s", r.get("detail"))
        return
    d = _load_upsell()
    d["published"].update({"at": doc["published"], "fingerprint": _upsell_fingerprint(doc), "doc": doc})
    d["problems"] = problems
    _write_upsell(d)
    _track("", "upsell", "brought the offers up to date", "new spellings, prices or availability")


async def _upsell_check_drift() -> None:
    d = _load_upsell()
    out = []
    for oid, m in (d["made"].get("codes") or {}).items():
        if m.get("ended") or not m.get("id"):
            continue
        st = await _upsell_ops["code_state"](m["id"])
        code = str(m.get("code") or "")
        if not st.get("exists"):
            out.append({"id": "code:" + oid, "kind": "code", "ref": oid,
                        "text": "The offer code " + code + " was deleted in Shopify.", "shopify": {"gone": True}})
        elif st.get("code") and st["code"].upper() != code.upper():
            out.append({"id": "code:" + oid, "kind": "code", "ref": oid,
                        "text": "The offer code " + code + " was changed in Shopify to " + st["code"] + ".",
                        "shopify": {"code": st["code"].upper()}})
    wids = {pid: _gid_digits(m.get("id")) for pid, m in (d["made"].get("warranty_products") or {}).items()}
    facts = await _upsell_ops["product_facts"](sorted(v for v in wids.values() if v)) if wids else {}
    for pid, wid in wids.items():
        f = facts.get(wid)
        if not f:
            out.append({"id": "warranty:" + pid, "kind": "warranty", "ref": pid,
                        "text": "A warranty product was deleted in Shopify.", "shopify": {"gone": True}})
            continue
        want = {y: L.get("price") for y, L in ((d["warranties"].get(pid) or {}).get("lengths") or {}).items()
                if L.get("price")}
        have = {}
        for v in f.get("variants") or []:
            m2 = UPSELL_WTY_RE.match(str(v.get("sku") or ""))
            if m2:
                have[m2.group(2)] = _upsell_money(v.get("price"))
        diff = {y: have[y] for y in want if y in have and have[y] != _upsell_money(want[y])}
        if diff:
            out.append({"id": "warranty:" + pid, "kind": "warranty", "ref": pid,
                        "text": f.get("title", "A warranty") + ": its price was changed in Shopify.",
                        "shopify": {"prices": diff}})
    d = _load_upsell()
    d["drift"] = out
    _write_upsell(d)


async def _upsell_tick(registry: dict, shopify_up: bool) -> None:
    """Hourly, after something is published: new spellings of marked fixtures,
    fresh prices and availability, Shopify-side edits flagged, and any order
    the webhook missed noted. Quiet on failure; the next hour tries again."""
    if not shopify_up or _upsell_ops is None:
        return
    try:
        async with _upsell_lock:
            d = _load_upsell()
            last = _upsell_when(d.get("tick_at"))
            if last and (datetime.now(timezone.utc) - last).total_seconds() < UPSELL_TICK_SECS:
                return
            d["tick_at"] = datetime.now(timezone.utc).isoformat()
            _write_upsell(d)
        if not (d["published"].get("at") and d["published"].get("config")) or await _upsell_gate():
            return
        # A plain read, not the shared snapshot: forcing that every hour would
        # throw away every screen's cached orders.
        orders = await _paginate_orders(
            registry, days=3,
            fields="id,name,created_at,email,customer,line_items,cancelled_at,note_attributes,discount_codes,"
                   "subtotal_price,current_subtotal_price,financial_status,fulfillment_status,fulfillments,tags,"
                   "payment_gateway_names")
        fresh = _upsell_scan(orders, _gobo_sizes())
        async with _upsell_lock:
            d = _load_upsell()
            for rid, v in fresh.items():
                cur = d["scan"].setdefault(rid, {"row": v["row"], "keys": [], "customers": 0, "checkout": 0,
                                                 "last": ""})
                cur["keys"] = sorted(set(cur["keys"]) | set(v["keys"]))
                cur["last"] = max(cur["last"], v["last"])
            _write_upsell(d)
        for o in orders:
            await _upsell_note_order(registry, o)
        async with _upsell_lock:
            await _upsell_check_drift()
            await _upsell_refresh_published()
    except Exception:
        logger.exception("upsell: hourly check failed")
```

In `_scheduler_loop`, after `await _connector_watch()` add:

```python
            await _upsell_tick(registry, shopify_up)
```

In the `/api/upsell` route, before the final `return _json({"error": "Unknown request."}, 400)`, add:

```python
            if op == "drift":
                async with _upsell_lock:
                    d = _load_upsell()
                    item = next((x for x in d["drift"] if x.get("id") == str(body.get("id") or "")), None)
                    if not item:
                        return _json({"error": "That is not waiting any more."}, 404)
                    keep = body.get("choice") == "keep"
                    if item["kind"] == "code":
                        m = d["made"]["codes"].get(item["ref"]) or {}
                        off = next((o for o in d["offers"] if o.get("id") == item["ref"]), None)
                        if keep and item["shopify"].get("code") and off:
                            off["code"] = m["code"] = item["shopify"]["code"]
                            m["spec"] = _upsell_spec_key(_upsell_code_spec(off, m))
                        elif keep and off:
                            # The discount is gone from Shopify: switching the
                            # offer back on makes a new one.
                            off["on"] = False
                            m["ended"] = True
                            m.pop("id", None)
                        else:
                            m["spec"] = ""
                            if item["shopify"].get("gone"):
                                m.pop("id", None)
                    else:
                        m = d["made"]["warranty_products"].get(item["ref"]) or {}
                        w = d["warranties"].get(item["ref"]) or {}
                        if keep and item["shopify"].get("prices"):
                            for y, price in item["shopify"]["prices"].items():
                                w.setdefault("lengths", {}).setdefault(y, {"on": False})["price"] = price
                            m["spec"] = ""
                        elif keep and w:
                            w["on"] = False
                        else:
                            m["spec"] = ""
                            if item["shopify"].get("gone"):
                                d["made"]["warranty_products"].pop(item["ref"], None)
                    d["drift"] = [x for x in d["drift"] if x is not item]
                    _write_upsell(d)
                _track(who, "upsell", "kept Shopify's change" if keep else "put Reactor's back", item["text"])
                return _json(await _upsell_view())
```

- [ ] **Step 4: Run it to see it pass**

Run: `ONLY=t_the_hourly_upsell env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>&1 | tail -2` and `ONLY=t_an_oversized_rules env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>&1 | tail -2`
Expected: `1 passed, 0 failed` each

- [ ] **Step 5: Commit**

```bash
git add copilot.py tests/test_dispatch.py
git commit -m "Upsell: an hourly check keeps prices and spellings current, flags Shopify-side edits, and notes missed orders

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Erasure, and where staff see cover

**Files:**
- Modify: `copilot.py` (`_redact_customer` ~15497, `_redact_scope` ~15640, `_redact_shop` ~15097, the Upsell section, `/api/customer-history` ~20290, `_mail_orders_for` ~21265, `_upsell_tick`)
- Modify: `static/index.html` (`histFill` ~17270, the CRM contact's Shopify card ~23223, the inbox order row ~26355, `privacyReach` ~29448)
- Test: `tests/test_dispatch.py`, `tests/test_frontend.py`

**Interfaces:**
- Produces:
  - `_upsell_cover_text(order_ids) -> {order id: "Covered by a 2-year warranty until 3 Oct 2029"}` (active or accepted sales, cover not ended)
  - `/api/customer-history` answer gains `"cover": [{"name", "text"}]`; each `_mail_orders_for` row gains `"cover": str`
  - `_redact_scope(...)` answer gains `"warranty_kept": int`

- [ ] **Step 1: Write the failing tests**

In `tests/test_dispatch.py`:

```python
@test
@upsell_test
def t_a_warranty_record_outlives_an_erasure_only_while_its_cover_runs():
    """Spec section 7: the register is a contract Reactor must honour, so an
    erasure keeps a record whose cover still runs (noted) and erases the rest;
    the erasure preview says so; the shop's erasure removes both stores; and
    staff see the cover beside the order."""
    upsell_reset()
    w = copilot._load_warranties()
    w["sales"] = {
        "1:9": {"email": "keep@x.test", "status": "active", "start": "2027-10-04", "end": "2099-10-03",
                "covered_order_id": "5001", "years": 2, "projector_id": "100"},
        "2:9": {"email": "keep@x.test", "status": "void", "end": "", "covered_order_id": "5002"},
        "3:9": {"email": "keep@x.test", "status": "active", "start": "2019-01-01", "end": "2020-01-01",
                "covered_order_id": "5003", "years": 1, "projector_id": "100"}}
    copilot._write_warranties(w)
    eq(copilot._upsell_cover_text(["5001", "5003", "9"]),
       {"5001": "Covered by a 2-year warranty until 3 Oct 2099"}, "only cover that still runs is shown")
    sc = copilot._redact_scope("keep@x.test")
    eq(sc.get("warranty_kept"), 1, "the preview says one record stays")
    r = copilot._redact_customer("keep@x.test")
    ok(r["retained"] >= 1)
    sales = copilot._load_warranties()["sales"]
    eq(sorted(sales), ["1:9"], "ended and void records are erased")
    ok(sales["1:9"].get("redacted_request_at"), "the kept one is noted")
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "copilot.py"), encoding="utf-8").read()
    shop = src[src.index("def _redact_shop"):src.index("def _redact_shop") + 4000]
    ok("UPSELL_PATH" in shop and "WARRANTY_PATH" in shop, "the shop's erasure removes both stores")
```

In `tests/test_frontend.py` (end of file):

```python
@test
def t_staff_see_warranty_cover_beside_the_order():
    ok("d.cover" in fn_src("function histFill("), "the label's customer line shows cover")
    ok("o.cover" in SCRIPT[SCRIPT.index("const row = el('div', 'mail-order');"):][:3000],
       "and so does the inbox's order list")
    ok("h.cover" in SCRIPT[SCRIPT.index("api('/api/customer-history', { customer_id: p.shopify_customer_id })"):][:900],
       "and the Shopify card on a CRM contact")
    ok("warranty_kept" in fn_src("function privacyReach("), "the erasure preview says cover records stay")
```

- [ ] **Step 2: Run them to see them fail**

Run: `ONLY=t_a_warranty_record env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>&1 | tail -3` and the frontend suite.
Expected: FAIL (`_upsell_cover_text` missing; `d.cover` not found).

- [ ] **Step 3: Implement the server side**

Add to the Upsell section:

```python
def _upsell_cover_text(order_ids) -> dict:
    today = _london_today().isoformat()
    out = {}
    for s in _load_warranties()["sales"].values():
        oid = str(s.get("covered_order_id") or "")
        if oid in {str(x) for x in order_ids} and s.get("status") in ("active", "accepted") \
                and str(s.get("end") or "") >= today:
            end = datetime.fromisoformat(s["end"])
            out[oid] = "Covered by a %d-year warranty until %d %s" % (int(s.get("years") or 1), end.day,
                                                                     end.strftime("%b %Y"))
    return out
```

In `_redact_customer`, in the "retained, and noted" part, after the dispatch `try/except`, add:

```python
    try:
        wr = _load_warranties()
        today = _london_today().isoformat()
        hit = False
        for sid, s in list(wr["sales"].items()):
            if str(s.get("email") or "").strip().lower() != addr:
                continue
            hit = True
            if s.get("status") in ("active", "accepted") and str(s.get("end") or "") >= today:
                # A cover still running is a contract we must honour: kept, noted.
                s.setdefault("redacted_request_at", stamp)
                retained += 1
            else:
                wr["sales"].pop(sid)
                erased += 1
        if hit:
            _write_warranties(wr)
    except Exception:
        logger.exception("redact: warranties")
        failed.append("the warranty register")
```

In `_redact_scope`, add to the dict it returns (beside `"contacts"`):

```python
                "warranty_kept": sum(1 for s in _load_warranties()["sales"].values()
                                     if str(s.get("email") or "").strip().lower() in {a.lower() for a in [addr] + others}
                                     and s.get("status") in ("active", "accepted")
                                     and str(s.get("end") or "") >= _london_today().isoformat()),
```

In `_redact_shop`, add `UPSELL_PATH, WARRANTY_PATH` to the `stores = (...)` tuple.

In `_upsell_tick`, after `for o in orders: await _upsell_note_order(registry, o)`, erase kept records whose cover has ended:

```python
        async with _upsell_note_lock:
            wr = _load_warranties()
            today = _london_today().isoformat()
            gone = [k for k, s in wr["sales"].items()
                    if s.get("redacted_request_at") and str(s.get("end") or "") < today]
            if gone:
                for k in gone:
                    wr["sales"].pop(k)
                _write_warranties(wr)
```

In `/api/customer-history`, replace the `return _json({"count": ..., "recent": [...]})` with:

```python
            cover = _upsell_cover_text([o.get("id") for o in orders])
            return _json({"count": len(orders),
                          "recent": [{"name": o.get("name"), "created_at": o.get("created_at"),
                                      "admin_url": _admin_order_url(o.get("id"))}
                                     for o in orders[:3]],
                          "cover": [{"name": o.get("name"), "text": cover[str(o.get("id"))]}
                                    for o in orders if str(o.get("id")) in cover]})
```

In `_mail_orders_for`, compute `cover = _upsell_cover_text([o.get("id") for o in orders])` before the loop, and add to each row: `"cover": cover.get(oid, ""),`.

- [ ] **Step 4: Implement the page side**

In `histFill`, before its closing brace, add:

```js
            (d.cover || []).forEach(c => {
                h.append(document.createTextNode(' · ' + c.name + ': ' + c.text));
            });
```

In the Shopify card on a CRM contact (the second reader of `/api/customer-history`, ~23223: `api('/api/customer-history', { customer_id: p.shopify_customer_id }).then(h => { ... })`), after its `if (latest) { ... }` block, add:

```js
                    (h.cover || []).forEach(c => line.append(document.createTextNode(' · ' + c.name + ': ' + c.text)));
```

In the inbox order row, after the `if (o.tracking) { ... }` block, add:

```js
                if (o.cover) row.append(el('div', 'mail-order-meta', o.cover));
```

In `privacyReach`, change the function so every answer gains the kept-cover sentence:

```js
        function privacyReach(sc) {
            if (!sc || sc.unreadable) return 'The CRM cannot be read just now, so what this would erase is not known.';
            if (sc.contacts == null) return '';
            const kept = sc.warranty_kept
                ? ' ' + (sc.warranty_kept === 1 ? 'One warranty record stays until its cover ends.'
                    : sc.warranty_kept + ' warranty records stay until their cover ends.')
                : '';
            const n = sc.contacts || 0;
            if (!n) return 'No contact in the CRM has this address; email threads from it go.' + kept;
            let t = 'Erases ' + (n === 1 ? 'one contact' : n + ' contacts') + ' in the CRM';
            if (sc.likely_duplicates) t += ', ' + (sc.likely_duplicates === 1 ? 'one of them only because it looks'
                : sc.likely_duplicates + ' of them only because they look') + ' like the same person';
            if (sc.other_addresses) t += (n === 1 ? ', which holds ' : ', which hold ') + (sc.other_addresses === 1 ? 'one other address' : sc.other_addresses + ' other addresses');
            return t + ', with their deals, leads and email threads.' + kept;
        }
```

- [ ] **Step 5: Run the tests to see them pass**

Run the two tests again, then the whole of both suites (erasure and customer history have many existing tests).
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add copilot.py static/index.html tests/test_dispatch.py tests/test_frontend.py
git commit -m "Upsell: warranty cover kept through an erasure only while it runs, and shown to staff beside the order

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
## Phase 5: The Upsell page

All page code lives in `static/index.html` in a new block placed after the Team page's functions (`renderTeamFeed`, ~28501). It uses the page's existing helpers: `$`, `el(tag, cls, text)`, `ico`, `I`, `api(path, payload)` (throws with the server's `error` text), `loader`, `heroAct`, `widget(el, id, span, label)`, `metricsGrid`, `fmtDate`, `setBusy`, `uiConfirm`, `toastOk`, `toastError`. UI copy follows the Global Constraints. The script must not write colour literals or pixel lengths (`t_the_script_paints_from_tokens_only`); styles go in the stylesheet using tokens.

### Task 15: Register the page (admins only), its shell and its guide

**Files:**
- Modify: `static/index.html` (nav, section, `APP_VIEWS`, nav label, `applyRoleChrome`, `setView`, the `GUIDE` list, the new page block)
- Modify: `copilot.py` (`LAYOUT_VIEWS`)
- Modify: `data/changelog.json` (add `"tab": "upsell"` to the Upsell note)
- Test: `tests/test_frontend.py` (end of file)

**Interfaces:**
- Produces (page globals): `upsellCache`, `showUpsellView()`, `loadUpsell(quiet)`, `upsellOp(payload, okMsg) -> Promise<bool>`, `upsellStatus(d) -> string`, `renderUpsell()`. Later tasks add one card each by calling their function from `renderUpsell`.

- [ ] **Step 1: Write the failing test**

```python
@test
def t_the_upsell_page_is_registered_for_admins_only():
    """The page changes what shoppers see: admins only, like Team, and
    registered in every list that keeps the views in step."""
    ok("'upsell'" in re.search(r"const APP_VIEWS = \[([^\]]*)\];", SCRIPT).group(1), "a view")
    ok('<section class="view" id="view-upsell">' in HTML and 'id="upsell-content"' in HTML, "with its root")
    ok('id="nav-upsell" style="display:none"' in HTML, "its button hidden until the role is known")
    ok("$('nav-upsell').style.display = lvl >= 2 ? '' : 'none';" in fn_src("function applyRoleChrome("),
       "and shown to admins only")
    ok("if (v === 'upsell') showUpsellView();" in fn_src("function setView("), "opening it shows it")
    ok("async function loadUpsell(" in SCRIPT, "the page has a loader")
    ok("async function loadUpsell(" in SCRIPT and "api('/api/upsell', { op: 'get' })" in fn_src("async function loadUpsell("),
       "and it reads its state from the route")
    ok("{ id: 'upsell', h: 'Upsell offers', admin: true" in SCRIPT, "the guide explains it to admins")
    py = open(os.path.join(ROOT, "copilot.py"), encoding="utf-8").read()
    ok('"upsell"' in py.split("LAYOUT_VIEWS = (")[1].split(")")[0], "and the server keeps its layout")
```

- [ ] **Step 2: Run it to see it fail**

Run: `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_frontend.py 2>&1 | grep -E "registered_for_admins|passed,"`
Expected: a `FAIL` line for the new test, then the `passed,` summary (the suite runs to the end)

- [ ] **Step 3: Register it**

In the nav, after `<button class="nav-item" data-view="team" id="nav-team" style="display:none"></button>` (~4716):

```html
                    <button class="nav-item" data-view="upsell" id="nav-upsell" style="display:none"></button>
```

After the Team section (~4826):

```html
            <!-- Upsell -->
            <section class="view" id="view-upsell">
                <div class="scroll"><div class="ov-wrap" id="upsell-content"></div></div>
            </section>
```

In `APP_VIEWS` (~5985), add `'upsell'` after `'team'`. After `$('nav-team').append(ico(I.userCheck), document.createTextNode('Team'));` (~5171):

```js
        $('nav-upsell').append(ico(I.trendUp), document.createTextNode('Upsell'));
```

In `applyRoleChrome`, after the `nav-team` line:

```js
            $('nav-upsell').style.display = lvl >= 2 ? '' : 'none';
```

In `setView`, after `if (v === 'team') showTeamView();`:

```js
            if (v === 'upsell') showUpsellView();
```

In `copilot.py`'s `LAYOUT_VIEWS`, add `"upsell"` after `"team"`.

In `GUIDE`, before `{ id: 'house', ...`:

```js
            { id: 'upsell', h: 'Upsell offers', admin: true, body: [
                ['What it does', 'Offers an upgrade to customers whose gobo orders name a projector you have marked as poor quality, and a warranty to people who have just bought a projector. Both appear on the page Shopify shows after they pay, and on their order status page.'],
                ['Marking a fixture', 'Upsell, Your customers’ fixtures lists the projectors named on gobo orders, most used first. Mark as poor quality starts an offer: choose the projector to recommend, the discount and the wording, then switch it on.'],
                ['Warranties', 'Set each projector’s standard guarantee and a price for each length you offer. Reactor makes the warranty products in Shopify; put each one on sale in the Online Store yourself, then publish again.'],
                ['Publishing', 'Check what publishing does lists every change first. Nothing reaches shoppers until you publish, and the Upsell offers block must be added once in Shopify’s checkout and accounts editor.'],
                ['Results', 'Sales through a card and sales with a code typed by hand are counted apart: a typed code may mean it has been shared. Views are not counted.'],
            ]},
```

- [ ] **Step 4: The page shell**

Add the new page block after `renderTeamFeed`:

```js
        /* ==================================================================
           Upsell: an upgrade for customers whose gobo orders name a projector
           marked poor quality, and a warranty for projector buyers, shown on
           the page Shopify shows after payment. Admins only: it changes what
           shoppers see. Spec: docs/superpowers/specs/2026-09-30-upsell-offers-design.md
           ================================================================== */
        let upsellCache = null;
        function showUpsellView() { if (upsellCache) renderUpsell(); else loadUpsell(); }
        async function loadUpsell(quiet) {
            const box = $('upsell-content');
            if (!quiet) { box.innerHTML = ''; box.append(el('div', 'thinking'), loader()); }
            try { upsellCache = await api('/api/upsell', { op: 'get' }); }
            catch (e) {
                box.innerHTML = '';
                const m = el('div', 'msg error'); m.append(el('div', 'bubble', e.message || 'Could not read the upsell settings.'));
                box.append(m);
                return;
            }
            renderUpsell();
        }
        /* One request, one repaint; a refusal says why and changes nothing. */
        async function upsellOp(payload, okMsg) {
            try {
                upsellCache = await api('/api/upsell', payload);
                if (okMsg) toastOk(okMsg);
                renderUpsell();
                return true;
            } catch (e) { toastError(e.message || 'That did not work.'); return false; }
        }
        function upsellStatus(d) {
            const p = d.published || {};
            if (!p.at) return 'Nothing is published yet, so shoppers see no offers.';
            const when = fmtDate(p.at) + (p.by ? ' by ' + p.by : '');
            if (p.trial) return 'A trial is published (' + when + '): only the staff test fixture sees an offer.';
            return p.current ? 'Shoppers see what is here, published ' + when + '.'
                : 'Changes here are not published yet. Shoppers still see what was published ' + when + '.';
        }
        function renderUpsell() {
            const d = upsellCache || {}; const box = $('upsell-content'); box.innerHTML = '';
            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.trendUp;
            const htext = el('div');
            htext.append(el('h2', null, 'Upsell'), el('p', null, upsellStatus(d)));
            hero.append(badge, htext, heroAct('')); box.append(hero);
            if (d.gate || d.last_error) {
                const c = el('div', 'card');
                const h = el('div', 'card-head');
                h.append(el('h3', 'card-title', d.gate ? 'Publishing is waiting' : 'The last publish did not finish'),
                    el('p', 'card-desc', d.gate || d.last_error));
                c.append(h);
                box.append(widget(c, 'notice', 'full', 'Notice'));
            }
        }
```

In `data/changelog.json`, add `"tab": "upsell"` to the Upsell note's item.

- [ ] **Step 5: Run the frontend suite to see it pass**

Run: `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_frontend.py 2>&1 | grep -E "FAIL|passed,"`
Expected: `0 failed` (`t_the_widget_grid_watches_every_view_setview_shows` passes too: the view is in `APP_VIEWS`, the page, and `LAYOUT_VIEWS`).

- [ ] **Step 6: Commit**

```bash
git add static/index.html copilot.py data/changelog.json tests/test_frontend.py
git commit -m "Upsell page: registered for admins only, with its shell and a guide section

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 16: Upgrade offers on the page

**Files:**
- Modify: `static/index.html` (stylesheet; the Upsell page block; `renderUpsell`)
- Test: `tests/test_frontend.py` (end of file)

**Interfaces:**
- Consumes: `upsellOp`, `upsellCache` (Task 15); `/api/upsell` ops `get`, `scan`, `rows`, `mark`, `save`, `replace_code` (Task 10); view fields `fixtures`, `offers` (with `reach`, `spellings`), `projectors`, `problems`, `scan_at`
- Produces: `upField(label, input) -> element`, `upsellOffersCard(box, d)`, `upsellOfferRow(o, projectors, problem) -> element`

- [ ] **Step 1: Write the failing test**

```python
@test
def t_the_upsell_page_marks_fixtures_and_edits_offers():
    ok("function upsellOffersCard(" in SCRIPT and "function upsellOfferRow(" in SCRIPT,
       "the offers card and its rows exist")
    card = fn_src("function upsellOffersCard(")
    row = fn_src("function upsellOfferRow(")
    for want in ("Your customers’ fixtures", "Mark as poor quality", "op: 'mark'", "op: 'rows'", "op: 'scan'",
                 "op: 'save', offers"):
        ok(want in card, "the offers card: " + want)
    for want in ("op: 'replace_code'", "Spellings matched", "maxLength = 80", "maxLength = 200",
                 "opt.disabled = !p.on_sale || p.status !== 'ACTIVE'", "through the online checkout",
                 "o.row_gone"):
        ok(want in row, "an offer row: " + want)
    ok("upsellOffersCard(box, d);" in fn_src("function renderUpsell("), "the page draws the offers card")
    ok("sel.setAttribute('aria-label', 'Projector to recommend')" in row
       and "kind.setAttribute('aria-label', 'Kind of discount')" in row, "both selects have a name of their own")
    ok(".up-offer {" in CSS and ".up-fields {" in CSS, "and its styles are in the sheet")
```

- [ ] **Step 2: Run it to see it fail**

Run: `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_frontend.py 2>&1 | grep -E "marks_fixtures|passed,"`
Expected: a `FAIL` line for the new test, then the `passed,` summary (the suite runs to the end)

- [ ] **Step 3: Add the styles**

At the end of the main stylesheet (before `</style>`):

```css
        /* Upsell page */
        .up-offer { border-top: var(--bw-hairline) solid var(--border-default); padding: var(--sp-3) 0; display: grid; gap: var(--sp-2); }
        .up-offer-top { display: flex; align-items: center; justify-content: space-between; gap: var(--sp-2); flex-wrap: wrap; }
        .up-fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr)); gap: var(--sp-2); }
        .up-field { display: grid; gap: var(--sp-1); font-size: var(--text-sm); }
        .up-field-label { color: var(--text-secondary); font-size: var(--text-xs); }
        .up-fixtures, .up-search { display: grid; gap: var(--sp-2); margin-bottom: var(--sp-4); }
        .up-bad { color: var(--error); font-size: var(--text-sm); }
        .up-steps { margin: var(--sp-2) 0; padding-left: var(--sp-5); font-size: var(--text-sm); }
        .up-preview { border: var(--bw-hairline) solid var(--border-default); border-radius: var(--radius-md);
            padding: var(--sp-3); display: grid; gap: var(--sp-1); max-width: 28rem; }
```

- [ ] **Step 4: The card and its rows**

Add to the Upsell page block:

```js
        function upField(label, input) {
            const w = el('label', 'up-field');
            w.append(el('span', 'up-field-label', label), input);
            return w;
        }
        function upsellOffersCard(box, d) {
            const card = el('div', 'card');
            const head = el('div', 'card-head');
            head.append(el('h3', 'card-title', 'Upgrade offers'),
                el('p', 'card-desc', 'Customers whose gobo orders name a projector you mark here are offered the one you recommend, with a code, after they pay.'));
            card.append(head);
            const fx = el('div', 'up-fixtures');
            fx.append(el('div', 'setting-title', 'Your customers’ fixtures'));
            const marked = new Set((d.offers || []).map(o => o.row_id));
            const list = (d.fixtures || []).slice(0, 12);
            if (!list.length) fx.append(el('div', 'empty', d.scan_at
                ? 'No gobo order names a fixture the size list knows yet.' : 'The orders have not been read yet.'));
            list.forEach(f => {
                const r = el('div', 'lbl-row');
                const what = el('div', 'lr-what');
                what.append(el('div', null, f.manufacturer + ' ' + f.model),
                    el('div', 'lbl-meta', f.customers + (f.customers === 1 ? ' customer' : ' customers')
                        + (f.last ? ' · last ordered ' + fmtDate(f.last) : '')));
                r.append(what);
                if (marked.has(f.row_id)) r.append(el('span', 'lbl-meta', 'Marked'));
                else {
                    const b = el('button', 'btn btn-sm', 'Mark as poor quality');
                    b.onclick = () => upsellOp({ op: 'mark', row_id: f.row_id }, 'Offer added, switched off until you finish it.');
                    r.append(b);
                }
                fx.append(r);
            });
            const again = el('button', 'linkish', d.scan_at ? 'Read the orders again' : 'Read the orders');
            again.onclick = async () => { setBusy(again, true); await upsellOp({ op: 'scan' }); };
            fx.append(again);
            const srch = el('div', 'up-search');
            const q = document.createElement('input');
            q.type = 'search'; q.className = 'tm-field'; q.placeholder = 'Find a model on the size list';
            q.setAttribute('aria-label', 'Find a model on the size list');
            const hits = el('div');
            let timer = null;
            q.oninput = () => {
                clearTimeout(timer);
                timer = setTimeout(async () => {
                    hits.replaceChildren();
                    if (q.value.trim().length < 2) return;
                    try {
                        const r = await api('/api/upsell', { op: 'rows', q: q.value });
                        (r.rows || []).forEach(x => {
                            const b = el('button', 'linkish', x.manufacturer + ' ' + x.model);
                            b.onclick = () => upsellOp({ op: 'mark', row_id: x.row_id, manufacturer: x.manufacturer, model: x.model }, 'Offer added.');
                            hits.append(b);
                        });
                        if (!(r.rows || []).length) hits.append(el('div', 'lbl-meta', 'Nothing on the size list matches.'));
                    } catch (e) { hits.append(el('div', 'up-bad', e.message)); }
                }, 250);
            };
            srch.append(q, hits);
            fx.append(srch);
            card.append(fx);
            const offers = (d.offers || []).map(o => Object.assign({}, o));
            const probs = {};
            (d.problems || []).forEach(p => { if (p.offer) probs[p.offer] = p.text; });
            if (!offers.length) card.append(el('div', 'empty', 'No offers yet. Mark a fixture above to start one.'));
            offers.forEach(o => card.append(upsellOfferRow(o, d.projectors || [], probs[o.id])));
            if (offers.length) {
                const save = el('button', 'btn btn-primary', 'Save offers');
                save.onclick = async () => {
                    setBusy(save, true);
                    if (!await upsellOp({ op: 'save', offers }, 'Offers saved. Publish to show them.')) setBusy(save, false);
                };
                card.append(save);
            }
            box.append(widget(card, 'offers', 'full', 'Upgrade offers'));
        }
        function upsellOfferRow(o, projectors, problem) {
            const row = el('div', 'up-offer');
            const top = el('div', 'up-offer-top');
            const on = document.createElement('input'); on.type = 'checkbox'; on.checked = !!o.on;
            on.onchange = () => { o.on = on.checked; };
            const onL = el('label', 'up-field-label'); onL.append(on, document.createTextNode(' Switched on'));
            const reach = (o.reach || 0) + ((o.reach || 0) === 1 ? ' customer' : ' customers')
                + (o.reach ? ', ' + (o.reach_checkout || 0) + ' through the online checkout' : '');
            top.append(el('div', 'setting-title', ((o.row && o.row.manufacturer) || '') + ' ' + ((o.row && o.row.model) || '')),
                el('span', 'lbl-meta', reach), onL);
            row.append(top);
            if (o.row_gone) row.append(el('div', 'up-bad', 'This fixture is no longer on the size list, so no new spelling of it will be matched.'));
            const f = el('div', 'up-fields');
            const sel = document.createElement('select'); sel.className = 'lbl-size';
            sel.setAttribute('aria-label', 'Projector to recommend');
            const none = el('option', null, 'Choose the projector to recommend'); none.value = ''; sel.append(none);
            projectors.forEach(p => {
                const opt = el('option', null, p.title + (p.on_sale && p.status === 'ACTIVE' ? '' : ' (not on sale)'));
                opt.value = p.id;
                opt.disabled = !p.on_sale || p.status !== 'ACTIVE';
                if (p.id === o.product_id) opt.selected = true;
                sel.append(opt);
            });
            sel.onchange = () => { o.product_id = sel.value; };
            const kind = document.createElement('select'); kind.className = 'lbl-size';
            kind.setAttribute('aria-label', 'Kind of discount');
            [['percent', '% off'], ['amount', '£ off']].forEach(([v, t]) => {
                const opt = el('option', null, t); opt.value = v; if (o.off_kind === v) opt.selected = true; kind.append(opt);
            });
            kind.onchange = () => { o.off_kind = kind.value; };
            const off = document.createElement('input'); off.type = 'number'; off.min = '0'; off.step = '0.01';
            off.className = 'tm-field'; off.value = o.off || ''; off.oninput = () => { o.off = off.value; };
            const ends = document.createElement('input'); ends.type = 'date'; ends.className = 'tm-field';
            ends.value = o.ends || ''; ends.onchange = () => { o.ends = ends.value; };
            const code = document.createElement('input'); code.className = 'tm-field'; code.value = o.code || '';
            code.oninput = () => { code.value = code.value.toUpperCase(); o.code = code.value; };
            const headline = document.createElement('input'); headline.className = 'tm-field'; headline.maxLength = 80;
            headline.value = o.headline || ''; headline.oninput = () => { o.headline = headline.value; };
            const body = document.createElement('textarea'); body.className = 'tm-field'; body.maxLength = 200; body.rows = 2;
            body.value = o.body || ''; body.oninput = () => { o.body = body.value; };
            f.append(upField('Recommend', sel), upField('Discount', kind), upField('Amount', off),
                upField('Ends (optional)', ends), upField('Code', code), upField('Headline', headline), upField('One line more', body));
            row.append(f);
            const acts = el('div', 'up-offer-top');
            const rep = el('button', 'linkish', 'Replace code');
            rep.onclick = () => upsellOp({ op: 'replace_code', id: o.id }, 'New code made. Publish to use it; the old one stops.');
            acts.append(rep);
            row.append(acts);
            if (problem) row.append(el('div', 'up-bad', problem));
            const sp = document.createElement('details');
            sp.append(el('summary', 'lbl-meta', 'Spellings matched (' + (o.spellings || []).length + ')'));
            (o.spellings || []).forEach(k => sp.append(el('div', 'lbl-meta', k.replace('|', ' · '))));
            row.append(sp);
            return row;
        }
```

In `renderUpsell`, at the end, add:

```js
            upsellOffersCard(box, d);
```

- [ ] **Step 5: Run the frontend suite to see it pass**

Run: `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_frontend.py 2>&1 | grep -E "FAIL|passed,"`
Expected: `0 failed` (including `t_a_boxed_child_of_a_card_is_inset` and `t_the_script_paints_from_tokens_only`).

- [ ] **Step 6: Commit**

```bash
git add static/index.html tests/test_frontend.py
git commit -m "Upsell page: your customers' fixtures, marking one as poor quality, and editing its offer

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 17: Warranties and the launch checks on the page

**Files:**
- Modify: `static/index.html` (the Upsell page block; `renderUpsell`)
- Test: `tests/test_frontend.py` (end of file)

**Interfaces:**
- Consumes: `upField`, `upsellOp` (Tasks 15 and 16); view fields `warranties`, `projectors`, `settings`, `problems`
- Produces: `upsellWarrantiesCard(box, d)`

- [ ] **Step 1: Write the failing test**

```python
@test
def t_the_upsell_page_prices_warranties_per_projector():
    ok("function upsellWarrantiesCard(" in SCRIPT, "the warranties card exists")
    card = fn_src("function upsellWarrantiesCard(")
    for want in ("Standard guarantee (years)", "op: 'save', warranties", "op: 'save', settings",
                 "Staff test projector for a trial", "trial_projector_id",
                 "What the warranty is, as your accountant confirmed", "Xero account code for warranty sales",
                 "put each on sale in the Online Store yourself", "['1', '2', '3']"):
        ok(want in card, "the warranties card: " + want)
    ok("upsellWarrantiesCard(box, d);" in fn_src("function renderUpsell("), "the page draws the warranties card")
```

- [ ] **Step 2: Run it to see it fail**

Run: `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_frontend.py 2>&1 | grep -E "prices_warranties|passed,"`
Expected: a `FAIL` line for the new test, then the `passed,` summary (the suite runs to the end)

- [ ] **Step 3: Implement**

```js
        function upsellWarrantiesCard(box, d) {
            const card = el('div', 'card');
            const head = el('div', 'card-head');
            head.append(el('h3', 'card-title', 'Warranties'),
                el('p', 'card-desc', 'Offered after someone buys a projector, priced per model. Once Reactor has made a warranty product, put each on sale in the Online Store yourself, then publish again.'));
            card.append(head);
            const ws = JSON.parse(JSON.stringify(d.warranties || {}));
            const probs = {};
            (d.problems || []).forEach(p => { if (p.warranty) probs[p.warranty] = p.text; });
            const projectors = d.projectors || [];
            if (!projectors.length) card.append(el('div', 'empty', 'No projector products were found in the shop.'));
            projectors.forEach(p => {
                const w = ws[p.id] = ws[p.id] || { on: false, standard_years: 1, skus: [],
                    lengths: { '1': { on: false, price: '' }, '2': { on: false, price: '' }, '3': { on: false, price: '' } } };
                const row = el('div', 'up-offer');
                const top = el('div', 'up-offer-top');
                const on = document.createElement('input'); on.type = 'checkbox'; on.checked = !!w.on;
                on.onchange = () => { w.on = on.checked; };
                const onL = el('label', 'up-field-label'); onL.append(on, document.createTextNode(' Offer a warranty'));
                top.append(el('div', 'setting-title', p.title), onL);
                row.append(top);
                const f = el('div', 'up-fields');
                const std = document.createElement('input'); std.type = 'number'; std.min = '0'; std.max = '10';
                std.className = 'tm-field'; std.value = String(w.standard_years == null ? 1 : w.standard_years);
                std.oninput = () => { w.standard_years = Number(std.value || 0); };
                f.append(upField('Standard guarantee (years)', std));
                ['1', '2', '3'].forEach(y => {
                    const L = w.lengths[y] = w.lengths[y] || { on: false, price: '' };
                    const wrap = el('div', 'up-field');
                    const cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = !!L.on;
                    cb.onchange = () => { L.on = cb.checked; };
                    const lab = el('label', 'up-field-label'); lab.append(cb, document.createTextNode(' ' + y + ' extra year' + (y === '1' ? '' : 's')));
                    const price = document.createElement('input'); price.type = 'number'; price.min = '0'; price.step = '0.01';
                    price.className = 'tm-field'; price.value = L.price || ''; price.setAttribute('aria-label', 'Price for ' + y + ' extra year' + (y === '1' ? '' : 's'));
                    price.oninput = () => { L.price = price.value; };
                    wrap.append(lab, price);
                    f.append(wrap);
                });
                const skus = document.createElement('input'); skus.className = 'tm-field';
                skus.value = (w.skus || []).join(', ');
                skus.oninput = () => { w.skus = skus.value.split(',').map(s => s.trim()).filter(Boolean); };
                f.append(upField('SKUs its quoted lines use', skus));
                row.append(f);
                if (probs[p.id]) row.append(el('div', 'up-bad', probs[p.id]));
                card.append(row);
            });
            if (projectors.length) {
                const save = el('button', 'btn btn-primary', 'Save warranties');
                save.onclick = async () => {
                    setBusy(save, true);
                    if (!await upsellOp({ op: 'save', warranties: ws }, 'Warranties saved. Publish to show them.')) setBusy(save, false);
                };
                card.append(save);
            }
            const s = Object.assign({}, d.settings || {});
            const checks = el('div', 'up-offer');
            checks.append(el('div', 'setting-title', 'Before warranties go live'),
                el('div', 'lbl-meta', 'No warranty is published until both of these are recorded.'));
            const f2 = el('div', 'up-fields');
            const vat = document.createElement('input'); vat.className = 'tm-field'; vat.maxLength = 200;
            vat.value = s.vat_note || ''; vat.oninput = () => { s.vat_note = vat.value; };
            const xero = document.createElement('input'); xero.className = 'tm-field'; xero.maxLength = 20;
            xero.value = s.xero_account || ''; xero.oninput = () => { s.xero_account = xero.value; };
            const win = document.createElement('input'); win.type = 'number'; win.min = '1'; win.max = '60';
            win.className = 'tm-field'; win.value = String(s.window_days || 30); win.oninput = () => { s.window_days = Number(win.value || 30); };
            const terms = document.createElement('input'); terms.type = 'url'; terms.className = 'tm-field';
            terms.placeholder = 'https://'; terms.value = s.terms_url || ''; terms.oninput = () => { s.terms_url = terms.value; };
            /* A trial's warranty goes on this projector only, never a real one,
               which every real buyer of it would be offered. */
            const tp = document.createElement('select'); tp.className = 'lbl-size';
            tp.setAttribute('aria-label', 'Staff test projector for a trial');
            tp.append(new Option('None chosen', ''));
            projectors.forEach(p => tp.append(new Option(p.title, p.id)));
            tp.value = s.trial_projector_id || '';
            tp.onchange = () => { s.trial_projector_id = tp.value; };
            f2.append(upField('What the warranty is, as your accountant confirmed', vat),
                upField('Xero account code for warranty sales', xero),
                upField('Days after the order a warranty is offered', win),
                upField('Link to your warranty terms', terms),
                upField('Staff test projector for a trial', tp));
            checks.append(f2,
                el('div', 'lbl-meta', 'A trial offers a warranty only on the staff test projector: a product of type Projector, unlisted, that no customer sees, with a warranty set above.'));
            const save2 = el('button', 'btn', 'Save these');
            save2.onclick = async () => {
                setBusy(save2, true);
                if (!await upsellOp({ op: 'save', settings: s }, 'Saved.')) setBusy(save2, false);
            };
            checks.append(save2);
            card.append(checks);
            box.append(widget(card, 'warranties', 'full', 'Warranties'));
        }
```

In `renderUpsell`, after `upsellOffersCard(box, d);` add `upsellWarrantiesCard(box, d);`.

- [ ] **Step 4: Run the frontend suite to see it pass**

Run: `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_frontend.py 2>&1 | grep -E "FAIL|passed,"`
Expected: `0 failed`

- [ ] **Step 5: Commit**

```bash
git add static/index.html tests/test_frontend.py
git commit -m "Upsell page: warranty prices per projector, and the checks before warranties go live

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 18: Preview, publish, Shopify-side changes and results on the page

**Files:**
- Modify: `static/index.html` (the Upsell page block; `renderUpsell`)
- Test: `tests/test_frontend.py` (end of file)

**Interfaces:**
- Consumes: `/api/upsell` ops `plan`, `publish`, `drift`, `sale`; view fields `offers`, `warranties`, `projectors`, `drift`, `results`, `needs_look`, `gate`
- Produces: `upsellPreview(d) -> element`, `upsellPublishCard(box, d)`, `upsellResultsCard(box, d)`

- [ ] **Step 1: Write the failing test**

```python
@test
def t_the_upsell_page_previews_checks_then_publishes():
    ok(all(("function " + f + "(") in SCRIPT for f in ("upsellPreview", "upsellPublishCard", "upsellResultsCard")),
       "the preview, publish and results functions exist")
    pub = fn_src("function upsellPublishCard(")
    for want in ("Check what publishing does", "op: 'plan'", "op: 'publish'", "uiConfirm(", "Publish as a trial",
                 "op: 'drift'", "choice: 'keep'", "choice: 'restore'", "check.disabled = !!d.gate"):
        ok(want in pub, "the publish card: " + want)
    ok("+ VAT" in fn_src("function upsellPreview("), "the preview shows prices as the card will")
    res = fn_src("function upsellResultsCard(")
    for want in ("Views are not counted", "typed", "op: 'sale'", "decision: 'accept'", "decision: 'refunded'",
                 "s.status === 'needs_look'", "before VAT"):
        ok(want in res, "the results card: " + want)
    r = fn_src("function renderUpsell(")
    ok(0 <= r.find("upsellPublishCard(box, d);") < r.find("upsellResultsCard(box, d);"),
       "the page draws publishing above the results")
```

- [ ] **Step 2: Run it to see it fail**

Run: `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_frontend.py 2>&1 | grep -E "previews_checks|passed,"`
Expected: a `FAIL` line for the new test, then the `passed,` summary (the suite runs to the end)

- [ ] **Step 3: Implement**

```js
        /* Drawn from the saved offers, as the thank-you page will show them.
           Prices are as the store sells them, without VAT, so they say so. */
        function upsellPreview(d) {
            const wrap = el('div', 'up-fixtures');
            const byId = {};
            (d.projectors || []).forEach(p => { byId[p.id] = p; });
            const money = (v) => '£' + Number(v || 0).toFixed(2) + ' + VAT';
            const on = (d.offers || []).filter(o => o.on && byId[o.product_id]);
            if (on.length) {
                const o = on[0], p = byId[o.product_id];
                const price = Number(((p.variants || [])[0] || {}).price || 0);
                const after = o.off_kind === 'percent' ? price * (1 - Number(o.off || 0) / 100) : Math.max(0, price - Number(o.off || 0));
                const c = el('div', 'up-preview');
                c.append(el('div', 'setting-title', o.headline || 'Headline'), el('div', 'lbl-meta', o.body || ''),
                    el('div', null, p.title), el('div', 'lbl-meta', money(price) + ', ' + money(after) + ' with code ' + o.code));
                wrap.append(c);
            }
            const w = Object.entries(d.warranties || {}).find(([pid, x]) => x.on && byId[pid]);
            if (w) {
                const [pid, x] = w;
                const c = el('div', 'up-preview');
                c.append(el('div', 'setting-title', 'Add a warranty for your ' + byId[pid].title));
                ['1', '2', '3'].filter(y => x.lengths && x.lengths[y] && x.lengths[y].on).forEach(y => {
                    c.append(el('div', 'lbl-meta', y + ' extra year' + (y === '1' ? '' : 's') + ': ' + money(x.lengths[y].price)));
                });
                wrap.append(c);
            }
            if (!wrap.children.length) wrap.append(el('div', 'empty', 'Nothing is switched on yet.'));
            return wrap;
        }
        function upsellPublishCard(box, d) {
            const card = el('div', 'card');
            const head = el('div', 'card-head');
            head.append(el('h3', 'card-title', 'Publish'),
                el('p', 'card-desc', 'Shoppers see nothing new until you publish. Check first: Reactor lists every change it will make in Shopify.'));
            card.append(head, upsellPreview(d));
            const trialL = el('label', 'up-field-label');
            const trial = document.createElement('input'); trial.type = 'checkbox';
            trialL.append(trial, document.createTextNode(' Publish as a trial (only the staff test fixture sees an offer)'));
            const check = el('button', 'btn', 'Check what publishing does');
            check.disabled = !!d.gate;
            const out = el('div');
            check.onclick = async () => {
                setBusy(check, true);
                try {
                    const r = await api('/api/upsell', { op: 'plan', trial: trial.checked });
                    out.replaceChildren();
                    const ul = el('ul', 'up-steps');
                    (r.steps || []).forEach(s => ul.append(el('li', null, s)));
                    out.append(ul);
                    (r.problems || []).forEach(p => out.append(el('div', 'up-bad', p.text)));
                    const go = el('button', 'btn btn-primary', 'Publish to Shopify');
                    go.onclick = async () => {
                        if (!await uiConfirm('Publish these offers to the page Shopify shows after payment?',
                            { title: 'Publish offers', okText: 'Publish' })) return;
                        setBusy(go, true);
                        try {
                            const pr = await api('/api/upsell', { op: 'publish', trial: trial.checked });
                            upsellCache = await api('/api/upsell', { op: 'get' });
                            toastOk((pr.problems || []).length ? 'Published. Some offers are held back: see why below.' : 'Published.');
                            renderUpsell();
                        } catch (e) { toastError(e.message); setBusy(go, false); }
                    };
                    out.append(go);
                } catch (e) { out.replaceChildren(el('div', 'up-bad', e.message)); }
                finally { setBusy(check, false); }
            };
            card.append(trialL, check, out);
            (d.drift || []).forEach(x => {
                const r = el('div', 'lbl-row');
                r.append(el('div', 'lr-what', x.text));
                const keep = el('button', 'btn btn-sm', 'Keep Shopify’s');
                keep.onclick = () => upsellOp({ op: 'drift', id: x.id, choice: 'keep' }, 'Kept. Publish to settle it.');
                const back = el('button', 'btn btn-sm', 'Put Reactor’s back');
                back.onclick = () => upsellOp({ op: 'drift', id: x.id, choice: 'restore' }, 'The next publish puts it back.');
                r.append(keep, back);
                card.append(r);
            });
            box.append(widget(card, 'publish', 'full', 'Publish'));
        }
        function upsellResultsCard(box, d) {
            const res = d.results || {}, w = res.warranties || {}, offers = res.offers || {};
            const card = el('div', 'card');
            const head = el('div', 'card-head');
            head.append(el('h3', 'card-title', 'Results'),
                el('p', 'card-desc', 'Views are not counted: the page Shopify shows never reports back. Revenue is after refunds, before VAT and shipping, and leaves out trial orders.'));
            card.append(head);
            let typed = 0;
            Object.values(offers).forEach(o => { typed += o.typed || 0; });
            const g = metricsGrid([
                { label: 'Warranties sold', value: String(w.sold || 0), note: w.last ? 'last ' + fmtDate(w.last) : 'none yet' },
                { label: 'Warranty revenue', value: '£' + (w.revenue || '0.00'), note: 'before VAT' },
                { label: 'Codes typed by hand', value: String(typed), note: typed ? 'may have been shared' : 'none' }]);
            g.classList.add('metrics-3');
            card.append(g);
            (d.offers || []).forEach(o => {
                const r = offers[o.id];
                if (!r) return;
                const row = el('div', 'lbl-row');
                row.append(el('div', 'lr-what', (o.row ? o.row.manufacturer + ' ' + o.row.model : o.id)),
                    el('span', 'lbl-meta', r.card + ' by card, ' + r.typed + ' typed, £' + r.revenue
                        + (r.last ? ', last ' + fmtDate(r.last) : '')));
                card.append(row);
            });
            if ((d.needs_look || []).length) {
                card.append(el('div', 'setting-title', 'Warranty sales that need a look'));
                d.needs_look.forEach(s => {
                    const row = el('div', 'lbl-row');
                    const what = el('div', 'lr-what');
                    what.append(el('div', null, (s.order_name || '') + ' · ' + (s.customer || s.email || '')), el('div', 'up-bad', s.reason || ''));
                    row.append(what);
                    /* A returned cover can only be refunded; a sale that failed
                       the checks can also be accepted. */
                    if (s.status === 'needs_look') {
                        const acc = el('button', 'btn btn-sm', 'Accept');
                        acc.onclick = () => upsellOp({ op: 'sale', id: s.id, decision: 'accept' }, 'Accepted: the cover counts.');
                        row.append(acc);
                    }
                    const ref = el('button', 'btn btn-sm', 'Refunded');
                    ref.onclick = () => upsellOp({ op: 'sale', id: s.id, decision: 'refunded' }, 'Marked refunded.');
                    row.append(ref);
                    card.append(row);
                });
            }
            box.append(widget(card, 'results', 'full', 'Results'));
        }
```

In `renderUpsell`, after `upsellWarrantiesCard(box, d);` add:

```js
            upsellPublishCard(box, d);
            upsellResultsCard(box, d);
```

- [ ] **Step 4: Run both suites**

Run: `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_frontend.py 2>&1 | grep -E "FAIL|passed,"`
Expected: `0 failed`

- [ ] **Step 5: Look at it**

With a local rig of the app (the memory notes describe the fixture-Shopify rig), sign in as an admin, open Upsell, and take screenshots at desktop width and at 375px. Check: nothing overflows sideways at 375px; the fixture list, an offer row, the warranty rows and the publish card read cleanly; a member account has no Upsell button. If no rig is available, say so in the hand-over rather than claiming it was seen.

- [ ] **Step 6: Commit**

```bash
git add static/index.html tests/test_frontend.py
git commit -m "Upsell page: a preview, a checked publish, Shopify-side changes to settle, and results

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
## Phase 6: The Shopify extension

### Task 19: The "Upsell offers" extension

**Files:**
- Create: `extensions/upsell-offers/shopify.extension.toml`, `extensions/upsell-offers/package.json`
- Create: `extensions/upsell-offers/src/Cards.jsx`, `src/ThankYou.jsx`, `src/OrderStatus.jsx`
- Create: `tools/ext_bundle_check.py`
- Modify: `Makefile` (`.PHONY` and the `check` target)
- Modify: `package-lock.json` (the root lock; the npm workspace install changes it)
- Test: `tests/test_frontend.py` (end of file)

**Interfaces:**
- Consumes: `chooseCards`, `digits` (Task 4); the rules document (Task 7); the `$app`/`warranty` order metafield (Task 12)
- Produces: the extension, and `make ext-size`

- [ ] **Step 1: Write the failing test**

```python
@test
def t_the_extension_has_one_entry_per_page_and_guards_the_order_status_view():
    """Spec section 3: one entry file per target, as Shopify requires, both
    deciding through offers.js; the order status page shows nothing on a
    cancelled order or the signed-out view; buttons say what they do."""
    base = os.path.join(ROOT, "extensions", "upsell-offers")
    for f in ("shopify.extension.toml", "src/ThankYou.jsx", "src/OrderStatus.jsx", "src/Cards.jsx"):
        ok(os.path.isfile(os.path.join(base, f)), "the extension has " + f)
    toml = open(os.path.join(base, "shopify.extension.toml"), encoding="utf-8").read()
    ok('target = "purchase.thank-you.block.render"' in toml and 'module = "./src/ThankYou.jsx"' in toml,
       "the thank-you page has its own entry")
    ok('target = "customer-account.order-status.block.render"' in toml and 'module = "./src/OrderStatus.jsx"' in toml,
       "and so does the order status page")
    ok(toml.count("[[extensions.metafields]]") == 2 and 'key = "upsell"' in toml and 'key = "warranty"' in toml,
       "it reads the rules and the covered list")
    ok("network_access" not in toml and "api_access" not in toml, "no network calls and no store queries")
    ty = open(os.path.join(base, "src", "ThankYou.jsx"), encoding="utf-8").read()
    os_ = open(os.path.join(base, "src", "OrderStatus.jsx"), encoding="utf-8").read()
    cards = open(os.path.join(base, "src", "Cards.jsx"), encoding="utf-8").read()
    for src in (ty, os_):
        ok("from './offers.js'" in src and "chooseCards(" in src, "each entry decides through offers.js")
    ok("covered: null" in ty, "the thank-you page has no order metafields")
    for want in ("!order.processedAt", "cancelled: !!order.cancelledAt", "entries === undefined"):
        ok(want in os_, "the order status page guard: " + want)
    for want in ("accessibilityLabel=", 'target="_blank"', "Choose a length first", 'label="Warranty length"',
                 "alt={", "+ VAT"):
        ok(want in cards, "the cards: " + want)
    mk = open(os.path.join(ROOT, "Makefile"), encoding="utf-8").read()
    ok(re.search(r"^check:.*\bext-size\b", mk, re.M), "make check measures the bundle when it can")
```

- [ ] **Step 2: Run it to see it fail**

Run: `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_frontend.py 2>&1 | grep -E "one_entry_per_page|passed,"`
Expected: a `FAIL` line ending `the extension has shopify.extension.toml`, then the `passed,` summary (the suite runs to the end)

- [ ] **Step 3: The extension's config**

`extensions/upsell-offers/shopify.extension.toml` (leave out `uid`: the Shopify CLI writes it on the first deploy; if the CLI refuses, generate a checkout UI extension named `upsell-offers` with `shopify app generate extension` and move these files into it):

```toml
api_version = "2026-10"

[[extensions]]
name = "Upsell offers"
handle = "upsell-offers"
type = "ui_extension"
description = "An upgrade or a warranty, offered after payment"

[[extensions.targeting]]
module = "./src/ThankYou.jsx"
target = "purchase.thank-you.block.render"

[[extensions.targeting]]
module = "./src/OrderStatus.jsx"
target = "customer-account.order-status.block.render"

[[extensions.metafields]]
namespace = "$app"
key = "upsell"

[[extensions.metafields]]
namespace = "$app"
key = "warranty"
```

If the build happens before 2026-10-01 17:00 UTC, use `api_version = "2026-07"` and `"~2026.7.4"` below.

The package is pinned by version range, not by a dist-tag such as `"2026-10"`: the repo's root `package.json` makes `extensions/*` npm workspaces, and npm counts a tag as satisfied by whatever version is already hoisted (the print extensions' 2026.4.x), so a tag fetches nothing. Use `"~2026.10.0"` once Shopify has published 2026.10.0 to npm (`npm view @shopify/ui-extensions versions --json | tail -5`; on 2026-09-30 only release candidates existed), else `"~2026.7.4"` with `api_version = "2026-07"`. Nothing imports the package at run time; it is for the types.

`extensions/upsell-offers/package.json`:

```json
{
  "name": "upsell-offers",
  "private": true,
  "version": "1.0.0",
  "license": "UNLICENSED",
  "dependencies": {
    "preact": "^10.10.0",
    "@shopify/ui-extensions": "~2026.10.0"
  },
  "devDependencies": {
    "esbuild": "^0.28.0"
  }
}
```

- [ ] **Step 4: The cards and the shared helpers**

`extensions/upsell-offers/src/Cards.jsx`:

```jsx
/** @jsxImportSource preact */
// Draws what offers.js decided. Nothing here chooses an offer.
import { useEffect, useState } from 'preact/hooks';

// A Shopify signal as a value that re-renders when it changes.
export function useValue(sig) {
  const [v, setV] = useState(sig ? sig.value : undefined);
  useEffect(() => (sig && typeof sig.subscribe === 'function' ? sig.subscribe((x) => setV(x)) : undefined), [sig]);
  return v;
}

export function toLines(lines) {
  return (lines || []).map((ln) => {
    const m = ln.merchandise || {};
    const qty = Number(ln.quantity) || 1;
    const total = Number((ln.cost && ln.cost.totalAmount && ln.cost.totalAmount.amount) || 0);
    return {
      productId: (m.product && m.product.id) || '', variantId: m.id || '', sku: m.sku || '', title: m.title || '',
      quantity: qty, unitPrice: total / qty,
      attributes: (ln.attributes || []).map((a) => ({ key: a.key, value: a.value })),
    };
  });
}

function entry(entries, type, key) {
  return (entries || []).find((x) => x && x.target && x.target.type === type && x.metafield && x.metafield.key === key);
}

export function rulesFrom(entries) {
  const e = entry(entries, 'shop', 'upsell');
  if (!e) return null;
  try { return JSON.parse(e.metafield.value); } catch (err) { return null; }
}

export function coveredFrom(entries) {
  const e = entry(entries, 'order', 'warranty');
  if (!e) return [];
  try { const v = JSON.parse(e.metafield.value); return Array.isArray(v) ? v.map(String) : []; } catch (err) { return []; }
}

export function londonToday(rules) {
  try {
    return new Intl.DateTimeFormat('en-CA', { timeZone: (rules && rules.tz) || 'Europe/London' }).format(new Date());
  } catch (err) {
    return new Date().toISOString().slice(0, 10);
  }
}

export function Offers({ cards, rules, format }) {
  if (!cards || (!cards.upgrade && !cards.warranty)) return null;
  const vat = rules && rules.prices_include_tax === false ? ' + VAT' : '';
  const money = (v) => format(v) + vat;
  return (
    <s-stack direction="block" gap="base">
      {cards.upgrade ? <Upgrade u={cards.upgrade} money={money} /> : null}
      {cards.warranty ? <Warranty w={cards.warranty} money={money} /> : null}
    </s-stack>
  );
}

function Upgrade({ u, money }) {
  const label = 'See the ' + u.title + ' for ' + money(u.priceAfter) + ' with code ' + u.code + ', in a new checkout';
  return (
    <s-section heading={u.headline}>
      <s-stack direction="block" gap="small-200">
        {u.body ? <s-text>{u.body}</s-text> : null}
        <s-stack direction="inline" gap="base" alignItems="center">
          {u.image ? <s-product-thumbnail src={u.image} alt={u.title} /> : null}
          <s-stack direction="block" gap="small-300">
            <s-text type="strong">{u.title}</s-text>
            <s-text>{money(u.priceAfter) + ' with code ' + u.code + ' (usually ' + money(u.price) + ')'}</s-text>
          </s-stack>
        </s-stack>
        <s-button href={u.href} target="_blank" accessibilityLabel={label}>See the offer</s-button>
      </s-stack>
    </s-section>
  );
}

function Warranty({ w, money }) {
  const [years, setYears] = useState('');
  const chosen = w.lengths.find((L) => String(L.years) === years);
  const each = w.qty > 1 ? ' each' : '';
  return (
    <s-section heading={'Add a warranty for your ' + w.title}>
      <s-stack direction="block" gap="small-200">
        <s-choice-list label="Warranty length" name="warranty-length" values={years ? [years] : []}
          onChange={(e) => {
            // Typed as a plain Event; the element that changed is the choice list.
            const list = /** @type {{ values?: string[] }} */ (/** @type {unknown} */ (e.currentTarget));
            setYears(((list && list.values) || [])[0] || '');
          }}>
          {w.lengths.map((L) => (
            <s-choice key={String(L.years)} value={String(L.years)}>
              {L.years + ' extra year' + (L.years === 1 ? '' : 's') + ', ' + money(L.price) + each}
            </s-choice>
          ))}
        </s-choice-list>
        {w.termsUrl ? <s-link href={w.termsUrl} target="_blank">Warranty terms</s-link> : null}
        {chosen ? (
          // Keys, so Preact makes a new button rather than reusing the
          // disabled one (which kept its disabled attribute in the simulation).
          <s-button key="add" href={chosen.href} target="_blank"
            accessibilityLabel={'Add a ' + chosen.years + '-year warranty for your ' + w.title + ' for '
              + money(chosen.price) + each + ', in a new checkout'}>
            Add the warranty
          </s-button>
        ) : (
          <s-button key="choose" disabled>Choose a length first</s-button>
        )}
      </s-stack>
    </s-section>
  );
}
```

- [ ] **Step 5: The two entries**

`extensions/upsell-offers/src/ThankYou.jsx`:

```jsx
/** @jsxImportSource preact */
import { render } from 'preact';
import { chooseCards, digits } from './offers.js';
import { Offers, useValue, toLines, rulesFrom, londonToday } from './Cards.jsx';

export default async () => {
  render(<ThankYou />, document.body);
};

function ThankYou() {
  const entries = useValue(shopify.appMetafields);
  const lines = useValue(shopify.lines);
  const conf = useValue(shopify.orderConfirmation);
  const total = useValue(shopify.cost.totalAmount);
  const company = useValue(shopify.buyerIdentity && shopify.buyerIdentity.purchasingCompany);
  const rules = rulesFrom(entries);
  const cards = chooseCards({
    rules, lines: toLines(lines), currency: total && total.currencyCode, company: !!company,
    orderId: digits(conf && conf.order && conf.order.id), orderDate: new Date().toISOString(), nowMs: Date.now(),
    covered: null, cancelled: false, today: londonToday(rules), shopUrl: shopify.shop.storefrontUrl,
  });
  return <Offers cards={cards} rules={rules} format={(v) => shopify.i18n.formatCurrency(Number(v))} />;
}
```

`extensions/upsell-offers/src/OrderStatus.jsx`:

```jsx
/** @jsxImportSource preact */
import { render } from 'preact';
import { chooseCards, digits } from './offers.js';
import { Offers, useValue, toLines, rulesFrom, coveredFrom, londonToday } from './Cards.jsx';

export default async () => {
  render(<OrderStatus />, document.body);
};

function OrderStatus() {
  const order = useValue(shopify.order);
  const entries = useValue(shopify.appMetafields);
  const lines = useValue(shopify.lines);
  const total = useValue(shopify.cost.totalAmount);
  const company = useValue(shopify.buyerIdentity && shopify.buyerIdentity.purchasingCompany);
  // The signed-out view leaves these undefined: show nothing rather than guess.
  if (!order || !order.processedAt || entries === undefined) return null;
  const rules = rulesFrom(entries);
  const cards = chooseCards({
    rules, lines: toLines(lines), currency: total && total.currencyCode, company: !!company,
    orderId: digits(order.id), orderDate: order.processedAt, nowMs: Date.now(),
    covered: coveredFrom(entries), cancelled: !!order.cancelledAt, today: londonToday(rules),
    shopUrl: shopify.shop.storefrontUrl,
  });
  return <Offers cards={cards} rules={rules} format={(v) => shopify.i18n.formatCurrency(Number(v))} />;
}
```

- [ ] **Step 6: The bundle check**

`tools/ext_bundle_check.py`:

```python
"""Bundle the Upsell offers extension with esbuild and check each entry
against Shopify's 64 KB compressed limit. Local only: it needs esbuild
installed, which CI does not do, and says so rather than failing when it is
missing."""
import gzip
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIMIT = 64 * 1024


def main() -> int:
    ext = os.path.join(ROOT, "extensions", "upsell-offers")
    # The repo's package.json makes extensions/* npm workspaces, so an install
    # (from the root or from the extension's folder) puts esbuild in the ROOT
    # node_modules; the extension's own folder is checked first all the same.
    esbuild = next((p for p in (os.path.join(ext, "node_modules", ".bin", "esbuild"),
                                os.path.join(ROOT, "node_modules", ".bin", "esbuild")) if os.path.exists(p)), "")
    if not esbuild:
        print("upsell-offers: esbuild is not installed, so the bundle was not measured "
              "(npm install --workspace extensions/upsell-offers at the repo root to measure it)")
        return 0
    bad = 0
    for entry in ("src/ThankYou.jsx", "src/OrderStatus.jsx"):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "bundle.js")
            r = subprocess.run([esbuild, os.path.join(ext, entry), "--bundle", "--format=esm", "--minify",
                                "--jsx=automatic", "--jsx-import-source=preact", "--outfile=" + out,
                                "--log-level=warning"], capture_output=True, text=True)
            if r.returncode:
                print(entry + " does not build: " + r.stderr[:400])
                bad += 1
                continue
            size = len(gzip.compress(open(out, "rb").read(), 9))
            print("%s: %d bytes compressed (limit %d)" % (entry, size, LIMIT))
            bad += size > LIMIT
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
```

In `Makefile`, add `ext-size` to `.PHONY`, add the target, and add it to `check`'s prerequisites (its two recipe lines stay):

```make
.PHONY: help install run test test-frontend test-forecast sweep sast env-doc check ext-size
```

```make
ext-size:
	$(PY) tools/ext_bundle_check.py

check: test-frontend test-forecast sweep sast ext-size
	$(PY) tools/env_reference.py --check
	$(PY) tests/test_dispatch.py
```

- [ ] **Step 7: Run everything**

Run: `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_frontend.py 2>&1 | grep -E "FAIL|passed,"` → `0 failed`.
Run: `npm install --workspace extensions/upsell-offers && make ext-size` (at the repo root) → both entries build, each far under 65536 bytes compressed (expect about 8 KB). The install lands in the root `node_modules` and changes the root `package-lock.json`; the lock file is committed below.

Type-check the JSX against Shopify's types once, outside the repo (esbuild does not type-check, and neither does the Shopify CLI). In a scratch folder, `npm install @shopify/ui-extensions@<the version in package.json> preact@10 typescript@5`, then make one folder per target holding a copy of `src/` and, as the CLI writes it, a `shopify.d.ts` that types the `shopify` global per module. For the thank-you page:

```ts
import '@shopify/ui-extensions/preact';
declare module './src/ThankYou.jsx' {
  const shopify: import('@shopify/ui-extensions/purchase.thank-you.block.render').Api;
  const globalThis: { shopify: typeof shopify };
}
declare module './src/Cards.jsx' {
  const shopify: import('@shopify/ui-extensions/purchase.thank-you.block.render').Api;
  const globalThis: { shopify: typeof shopify };
}
```

and the same for the order status page with `./src/OrderStatus.jsx` and `customer-account.order-status.block.render`. With a `tsconfig.json` of `{"compilerOptions": {"allowJs": true, "checkJs": true, "noEmit": true, "jsx": "react-jsx", "jsxImportSource": "preact", "module": "esnext", "moduleResolution": "bundler", "target": "es2022", "skipLibCheck": true}, "include": ["shopify.d.ts", "src/Cards.jsx", "src/offers.js", "src/<the entry>.jsx"]}`, `tsc -p .` must exit 0 in both folders. (Checked on 2026-09-30 against 2026.7.4: without the cast in the choice list's `onChange`, it fails with `Property 'values' does not exist on type 'EventTarget'`.)

Simulated render (spec section 9), also outside the repo, as was done for the print extensions: in the same scratch folder add `@remote-dom/core` and `esbuild`. Bundle each entry as `import T from './src/ThankYou.jsx'; shopify.extend('purchase.thank-you.block.render', (...a) => T(...a));` (and the same for OrderStatus with its target) with `esbuild --bundle --format=iife --jsx=automatic --jsx-import-source=preact`. Run it under a sim that defines `s-stack`, `s-section` (heading), `s-text` (type), `s-product-thumbnail` (src, alt), `s-button` (href, target, accessibilityLabel, disabled), `s-link` (href, target), `s-choice-list` (label, name, values, with a change event that sets values) and `s-choice` (value) as RemoteElements, with a fake `shopify` (appMetafields, lines, orderConfirmation, order, cost.totalAmount, buyerIdentity.purchasingCompany, shop.storefrontUrl, i18n.formatCurrency). Check: an upgrade card with its link and alt text; a warranty card whose button says Choose a length first until the list's change event picks a length, then a link whose label names the product, length and price, with no stray `disabled`; and nothing for no rules, a covered projector, a cancelled order and the signed-out view. The hand-over says the sim guesses the host's element definitions.

- [ ] **Step 8: Commit**

```bash
git add extensions/upsell-offers tools/ext_bundle_check.py Makefile tests/test_frontend.py package-lock.json
git commit -m "Upsell offers extension: one entry per page deciding through offers.js, accessible cards, and a bundle size check

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(`node_modules/` is already ignored by `.gitignore`, at the root and in the extension's folder.)

---

## Phase 7: Finish and hand over

### Task 20: Release note, the whole check, and Cameron's steps

**Files:**
- Modify: `data/changelog.json`
- Create: `docs/upsell-release.md`
- Modify: the memory notes (outside the repo)

- [ ] **Step 1: Finish the release note**

Replace the Upsell note's items with (keeping the date as the last commit's day):

```json
    {
     "kind": "added",
     "text": "A new Upsell page for admins. Mark the projectors on your customers' gobo orders that are poor quality, choose the projector to recommend and a discount, and those customers see the offer on the page Shopify shows after they pay, and on their order status page.",
     "tab": "upsell"
    },
    {
     "kind": "added",
     "text": "Warranties for projector buyers, priced per model with a choice of lengths, offered on the same pages. Reactor keeps a record of every warranty sold and shows the cover beside the order. Nothing shows to shoppers until the Upsell offers block is added in Shopify and you publish.",
     "tab": "upsell"
    }
```

- [ ] **Step 2: Write Cameron's steps**

Create `docs/upsell-release.md`:

```markdown
# Releasing the Upsell offers

Everything below is yours to do; Reactor cannot do it, and nothing shows to shoppers until the last step.

1. **Accountant:** confirm the warranty is Projected Image's own repair promise and its VAT treatment, and
   choose the Xero account code for warranty sales. If you sell projectors to consumers, ask whether the
   2005 Extended Warranties Order applies: if it does, the warranty's price and length must also be shown on
   the projector's product page before any warranty is offered.
2. **Deploy the app:** `shopify app deploy --no-release`, read the listed changes (they include every
   extension and app setting changed since the last deploy), then release when the bench is quiet.
3. **Approve the new permissions** on the store when Shopify asks (making discount codes and products).
4. **Customer accounts:** in Shopify, Settings, Customer accounts, check the store uses the new customer
   accounts; on legacy accounts the order status card never shows.
5. **Place the block:** Settings, Checkout, Customize: add "Upsell offers" once on the Thank you page and once
   on the Order status page.
6. **Make a staff test projector:** a product of type Projector, status Unlisted, on sale in the Online Store,
   never shown to customers. A trial offers a warranty only on this projector, never on a real one.
7. **On the Upsell page:** record the VAT answer and the Xero code, set warranty prices (including one for the
   staff test projector, chosen as the staff test projector under Before warranties go live), mark fixtures
   and set up offers, then Check what publishing does, and publish **as a trial** first. If the first publish
   fails with a permission message about the offers' settings, stop and tell Claude: the shop setting may
   need a permission of its own.
8. **Put each warranty product on sale** in the Online Store (Products, the warranty, Sales channels), then
   publish again. Open Upsell afterwards: the first warranty's row must no longer say Put on sale in Shopify
   first. If it still does, stop and tell Claude (Reactor reads the product's Online Store link, and an
   unlisted product may not report one).
9. **Trial order:** place a staff order whose gobo line names the trial fixture (Manufacturer "Reactor trial",
   Model "trial"), check both cards on the thank-you and order status pages (also with the keyboard only
   and at 200% zoom), buy through each, then refund
   both orders. **To decide with Claude before this step:** how to place an order carrying that fixture,
   since the storefront's gobo form may only offer fixed choices. Both trial orders are left out of Results.
10. **Publish for real.**
```

- [ ] **Step 3: The whole check**

Run: `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN make check`
Expected: every stage passes (page, forecast and main tests; tree sweep; environment reference; security scan; bundle size or its "not installed" line). One existing timing test, `t_a_strangers_email_or_pdf_cannot_hold_the_event_loop`, can fail when the machine is busy (seen at a load average of about 15); if it fails, run it alone with `ONLY=` before treating it as real.

- [ ] **Step 4: An independent review of the whole diff**

Dispatch one reviewer (the last of the 5 agents the whole task may use) over `git diff main...HEAD` with the spec and this plan, asking for defects only, each with a reproduction. Fix what it finds, with a test first for each, and run `make check` again.

- [ ] **Step 5: Commit, and stop before pushing**

```bash
git add data/changelog.json docs/upsell-release.md
git commit -m "Upsell: release note and Cameron's release steps

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Do not push. Tell Cameron it is ready, what was checked and what was not (the live cards, the trial), and point them to `docs/upsell-release.md`.

- [ ] **Step 6: Memory**

Add a memory note `gizmo_upsell_offers.md`: where the feature lives, the decisions (approach B, hand-published warranty products, no Quote Engine), the fixture tidy contract and its test, the publish order, and what is still Cameron's (their release steps). Link it from `MEMORY.md`.
