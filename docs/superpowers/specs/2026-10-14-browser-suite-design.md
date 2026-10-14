# The browser suite: every screen in a real browser on every pull request

Stage 1 of the 14 October engineering audit. Approved in conversation on
14 Oct 2026: approach A (Playwright on Node, serving the real app), existing
accessibility problems recorded and ratcheted, not fixed first.

## Why

Nothing runs the page in a browser before it ships. The page suite reads the
source as text and runs extracted functions in node: it cannot see layout,
and a string check passes on a selector that never matches. On 13 Oct a
table rule that matched nothing passed all 608 page checks and was caught
only by measuring in the local rig. The rig works, but it is local,
uncommitted (some of its fixtures were captured from real data and the repo
is public) and run by hand. Every later stage of the audit (splitting the
page's source, the shared parts layer, the backend split) moves code that
draws screens, so this suite comes first.

## Goals

1. Every screen opens in Chromium on every pull request, at three sizes, and
   the pull request fails on a script error, a failed request to the app,
   sideways scrolling or content spilling out of its panel.
2. The panel rules from the 13 Oct build are measured in the browser, not
   pinned as text.
3. Accessibility is checked against WCAG 2.2 AA with axe, as a ratchet: today's
   problems are recorded; a pull request fails if it adds one, and fails if it
   removes one without lowering the record, so the record only ever tightens.
4. A few keyboard journeys are proven: a dialog takes focus, Escape closes
   it, focus returns to what opened it.
5. Nothing in the suite comes from the business: all data is invented and
   committed, and the browser reaches no host but the app.
6. The API routes are listed in a generated `docs/API.md` that CI keeps
   current, as `docs/ENVIRONMENT.md` already is.

## Non-goals

- Pixel-for-pixel screenshot comparison. Fonts and anti-aliasing differ
  between macOS and the Linux runners, so stored images would churn. Every
  run uploads its screenshots for a person to look at instead.
- Firefox and WebKit. Chromium only for now; the admin embeds the app in the
  merchant's browser, and the layout code has no engine-specific paths.
- The Shopify admin frame and App Bridge itself. The suite gives the page a
  stand-in `window.shopify` exactly as the rig does.
- Fixing the accessibility problems found. That is stage 3's work, done at
  the source by the shared parts.
- Any visible change to the app. If the suite finds a script error, a failed
  request or sideways scrolling on a screen today, the fix lands in this
  stage with a release note; the panel-rule and accessibility findings go on
  the record instead.

## How it works

### Serving the app

`tests/browser/serve.py` starts the real app the way `make run` does, inside
the dispatch suite's own world: it executes the dispatch suite's setup (every
line of `tests/test_dispatch.py` before its first `@test`) so the app gets
the suite's scratch stores, its fake Shopify, its invented accounts and its
network block, then runs `server.build_app()` under uvicorn on
`127.0.0.1:$PORT` (default 8930). The local rig has run the app this way since
September. The script fails loudly if the setup marker is missing rather
than serving a half-built world.

It then mints an embed token valid for the whole run (the suite's own token
helper with a longer expiry), signs the master account in through
`/api/auth/login`, and writes `{token, session}` to a file in its scratch
directory that the browser specs read. Nothing is written to the repo.

### The browser side

| File | Role |
|---|---|
| `tests/browser/playwright.config.js` | Three projects: phone 390x844, laptop 1280x800, wide 1920x1080. `webServer` runs `serve.py`. One retry in CI with a trace kept on retry. |
| `tests/browser/support.js` | Sign-in (the stand-in `window.shopify` and the session in `localStorage`, as the rig does), the network fence, the font route, the helpers that reach a screen (`nav`, `tab`, `queue`, `clickText`, `waitText`, `esc`), and `settle` (fonts loaded, no request in flight, two animation frames). |
| `tests/browser/screens.js` | The screen list: id, view, how to reach the state, and which fixtures it routes. |
| `tests/browser/probes.js` | The in-page measures: sideways scroll, overflow out of a panel, and the panel rules. |
| `tests/browser/pages.spec.js` | For each screen at each size: reach it, assert no script error and no failed app request, run the probes and axe, compare with the record, save a screenshot. |
| `tests/browser/keyboard.spec.js` | The dialog journeys. |
| `tests/browser/record.js` | Reads and compares the record; rewrites it when asked. |
| `tests/browser/record/a11y.json`, `record/panels.json` | The ratchet records. |
| `tests/browser/fixtures/` | Invented answers for routes the dispatch world does not fill (below), and a committed Inter font file with its OFL licence. |

**The network fence.** Every request to a host other than the app is
answered or aborted in the browser. Google Fonts is answered with the
committed Inter file, so text measures the same on every machine and the
run needs no internet. App Bridge's script is aborted (the stand-in replaces
it). Anything else is aborted and fails the test that caused it, naming the
host.

**Data.** Corrected 14 Oct after a probe: the bare dispatch world shows the
empty state on almost every screen (only the Size list and the Guide have
content), so the suite seeds its own world before serving. `tests/browser/seed/`
runs in the same process after the dispatch setup and before uvicorn starts,
and fills every screen through the app's real code:

- **The app's own routes first** (`post(...)` with payloads from the dispatch
  tests): accounts, the CRM, loan units, custom shipments, memory, skills,
  requests.
- **A store's own writer** where no route writes it: the work clock, the
  activity ledger, the Xero token for reconciliation.
- **An in-process stand-in for an outside system** only where the app reaches
  one over the network: one fake Shopify store (about a thousand orders over
  three years, customers, products, payouts, and the Production Manager's
  queue orders), Google's search and analytics answers and a fake storefront,
  used only while the saved reports are produced, the AI (the same, only while
  seeding: every report on screen is a real saved run of the app's own code
  over invented answers), Gmail, the file storage bucket, and the Xero
  connector service (a loopback HTTP server in the same process).

The background scheduler stays off for the whole run; left on, it reaches for
Xero within a minute. Chat conversations live only in the browser, so the
seed writes them to the auth file and the browser puts them in
`localStorage` before the page loads. Two screens write as they paint (What's
new and Requests mark themselves seen; Customise saves a layout when it
closes): the browser swallows exactly those writes, so screens running in
parallel never change each other.

Every person, company, address and figure in the seed is made up. A page-suite
test fails if the suite contains an email address outside the example domains,
a phone number outside the 01632 960xxx drama range, or the shop's own name
(read off the code's own default, so the test does not carry it).

The forecast's run is produced by the forecast package itself, so the
browser job installs `forecast/requirements-service.txt` beside the app's
lock, from its hashes.

### The screens

The 32 states the panels review covered plus the Guide's Design page, 33 in all, each at three sizes: Overview, SEO,
Keywords, Products, Customers, Liability, Reconciliation, Forecast, Xero
sync, Production Manager (queue, an order open, Custom shipments), the Size
list, CRM (Leads, Activities, Insights, Contacts), Loan units, Inbox, Files,
Team (People, Work, Activity), Memory, Skills, Chat (new and a conversation),
the Guide (contents, What's new, Requests, Design), and Customise on
Customers and on Overview; plus three dialogs measured like a screen (a CRM
deal, a loan unit, and a size rule opened from the Production Manager's Size
check), 36 states in all. Adding a screen is one entry in `screens.js`.

Frozen areas are measured, never touched: the Production Manager's queue and
the printed label are screens in the list like any other, and nothing in the
suite clicks Print, Mark made, Dispatch or any button that writes.

### What fails a pull request

| Check | On day one | After |
|---|---|---|
| A script error, an unhandled rejection, or a failed request to the app | must be zero | must be zero |
| A request to any other host | must be zero | must be zero |
| Sideways page scroll, or content wider than its panel | must be zero | must be zero |
| Panel rules: each section a panel, panels side by side the same height, the gap between them, no panel inside a panel, tables running to their panel's edge | recorded | ratchet |
| axe, WCAG 2.2 A and AA rules, every impact level | recorded | ratchet |
| Keyboard: three dialogs (a CRM deal, a loan unit, a size rule from the Production Manager's Size check) take focus, close on Escape and hand focus back, without saving anything | must pass | must pass |

**The ratchet.** A record is `{screen@size: {rule: count}}`. A run fails if
any count is above the record (a new problem) or below it (a fixed problem
the record still allows, which would let a later regression hide in the
slack). `UPDATE_RECORD=1 make test-browser` rewrites the record from the run;
the diff of `record/*.json` in the pull request shows a reviewer exactly what
changed. Counting by rule, not by element selector, keeps the record stable
when markup moves without the problem changing.

### Commands and CI

- `make test-browser` runs the suite locally. It skips with a note when the
  node modules or Chromium are missing (as `make ext-check` does) and prints
  the one command that installs them. `make check` runs it.
- `package.json` gains two dev dependencies, pinned exactly: `@playwright/test`
  1.63.0 (the version the local rig already runs) and `@axe-core/playwright`
  4.13.0. Dev dependencies never reach the image, and `npm audit --omit=dev`
  is unchanged.
- `.github/workflows/tests.yml` gains a `browser` job beside `test`: install
  the Python lock, the forecast service's lock and the node modules, `npx playwright install --with-deps
  chromium`, run the suite, and upload the screenshots, the HTML report and
  any traces as an artefact, always, pass or fail.
- **Cameron's setting:** the `browser` job blocks a merge only once it is
  added to the "Protect main" ruleset's required checks (today: `test`,
  `images`, `forecast`). I add it with one API call once the job has passed
  on its own pull request, with Cameron's yes, or Cameron adds it in the
  repository's settings.

### The API route list

`tools/route_reference.py` reads every `@mcp.custom_route` in `copilot.py`
and `server.py` and writes `docs/API.md`: path, methods, handler, the tab
that opens it (from `_TAB_ROUTES` / `_OPEN_API`), the guard it opens with and
that guard's rank, AI slot and body cap, and the first sentence of the
handler's docstring. `--check` fails when the file is stale; CI runs it beside
the environment reference check, `make api-doc` regenerates it, and a dispatch
test pins that it is current, as the environment reference's does.

## Documentation

- `docs/ARCHITECTURE.md`: a "Tests" section naming the three suites and what
  each can and cannot see; "How to add" gains "a screen" (one entry in
  `screens.js`) and "a route" gains `make api-doc`.
- `tests/browser/README.md`: running it, reading a failure (the trace and the
  screenshot), updating the record, adding a fixture.
- The README's developer commands gain `make test-browser` and `make api-doc`.

## Acceptance

1. On the stage's pull request, CI's `browser` job is green with the records
   committed, and the artefact holds a screenshot of every screen at every
   size.
2. The 13 Oct bug is caught: on a scratch branch, reverting that fix (the
   `:is()` selector that never matched) makes the panel-rule check fail on
   the tables it moved. Not committed; recorded in the pull request.
3. A deliberately thrown error in one screen's render, and a deliberate
   `width: 2000px` on one panel, each fail the run with the screen and size
   named. Also scratch-only.
4. The ratchet is proven both ways by a test of `record.js`: a higher count
   fails, a lower count fails with "lower the record", an equal count passes.
5. `docs/API.md` lists all 150 routes; editing a route's guard without
   regenerating fails CI.
6. No request leaves the machine during a run (the fence's own log is
   empty).
7. `make check` stays green, and its local run time is reported before and
   after.

## Risks

- **Timing flakes.** Screens load data asynchronously. `settle` waits on the
  app's own signals (no request in flight, fonts loaded, two frames), never on
  a fixed sleep; CI keeps one retry with a trace, and a test that needed its
  retry is reported as flaky in the run summary rather than hidden.
- **The setup it borrows.** `serve.py` executes the dispatch suite's setup.
  If that setup changes shape, the browser job fails at start-up with a
  message naming the marker it could not find, never by serving a partial
  world.
- **Run time.** Thirty-six states at three sizes is 108 page
  states. Projects run in parallel workers; the budget is under eight minutes
  in CI, and the run time is reported in the pull request.

## Agent budget

The initiative's five-agent cap stands. This stage plans one fresh reviewer
for the finished branch.
