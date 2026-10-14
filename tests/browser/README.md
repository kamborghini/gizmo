# The browser suite

Every screen of Reactor in Chromium, at phone (390), laptop (1280) and wide
(1920) sizes, inside an invented world. It sees what the other suites cannot:
script errors, layout, accessibility and the keyboard.

## Running it

Once:

```bash
npm ci
npx playwright install chromium
```

Then `make test-browser` (also part of `make check`). It runs the suite's own
unit tests, proves the seeded world without a browser (`test_world.py`), then
starts the app (`serve.py`) and opens every screen. One screen:
`npx playwright test -c tests/browser/playwright.config.js -g "crm~leads"`.

## What fails a run

On every screen at every size, these must be zero: a script error, a failed
request to the app, a request to any other host, a write, sideways scroll,
and content spilling out of its panel.

Accessibility (axe, WCAG 2.2 A and AA) and the panel rules are counted per
rule and held by a ratchet in `record/`. A run fails if a count goes up (a new
problem) and if it goes down without the record being lowered (a fixed problem
the record would still allow, which would let a later one hide).

Three windows are opened by keyboard alone (`keyboard.spec.js`): focus moves
in, Escape leaves the window open (the app's rule: a window holding work
closes only by its X), Tab stays inside, the X closes it, and focus goes back.

## Reading a failure

- The message names the screen, the size and the check.
- Screenshots of every screen are in `.run/shots/`; the report is
  `.run/report/index.html`.
- In CI, download the `browser-run` artefact; a test that needed its retry has
  a trace: `npx playwright show-trace <path>/trace.zip`.

## Updating the record

After fixing a problem, lower the record:

```bash
BROWSER_EXPECTED_STATES=108 UPDATE_RECORD=1 make test-browser
```

A partial run never rewrites it. The diff of `record/*.json` goes in the pull
request; a count only goes up with the reason written there. Fonts render
differently on a Mac and on CI's Linux, so when the two disagree, CI's
`observed-a11y.json` / `observed-panels.json` in the artefact is the truth:
copy it into `record/`.

## Adding a screen

One entry in `screens.js`. Its steps must end by waiting for content only the
seed puts there, so an empty state is never measured by mistake (a unit test
checks every screen waits). Never click anything that writes: Save, Print,
Mark made, Dispatch, Send, Claim, Delete, Won, Lost, a checkbox that completes.
Opening a tab, a row or a window is fine. `BROWSER_EXPECTED_STATES` is the
number of screens times three.

## Adding data

The world is seeded in `seed/` before the app is served: the app's own routes
first, a store's own writer second, an in-process stand-in for an outside
system (Shopify, Google, Gmail, the file bucket, the Xero connector, the AI)
last. Each recipe runs in its own namespace; only the Shopify store (`DASH`)
is shared. Everything is invented: people and companies made up, email at
`example.com` / `example.org` (or their subdomains), phones in the 01632 960xxx
drama range. A page-suite test enforces it. Add a seeded text for the new data
to `test_world.py`.
