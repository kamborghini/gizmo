# The page's source in sections, served byte for byte as before

Stage 2 of the 14 October engineering audit. Approved in conversation on
14 Oct 2026: approach A (source files joined by the server at start-up),
over a generated `index.html` (B) and separately served modules (C).

## Why

The whole app is one file, `static/index.html`: 33,761 lines, of which 6,546
are the stylesheet and 26,911 the script. Every change to any screen is an
edit somewhere in that file, found by searching; every pull request's diff is
against it; the audit counted 846 functions in one scope with comment banners
as the only boundaries. The file already falls into sections by its own
banners: the script into about forty, each one contiguous (core helpers, the
widget grid, charts, chat, each report, the Production Manager, Xero sync,
loans, the forecast, the CRM, the Inbox, Files, the Team page, the front
door), the stylesheet into about thirty. Stage 3 (the shared parts layer)
moves code between screens and parts; it needs the sections to be files.

## Goals

1. The page's source lives in `static/src/` as one shell, the stylesheet's
   sections and the script's sections, cut at the file's own banners and kept
   in today's order.
2. The server joins them at start-up into exactly today's page, so the shell,
   the stylesheet and the script it serves, and the content-hash URLs they are
   served under, are byte for byte what they are today.
3. One reader: the server, both test suites, the browser suite and the CI
   checks read the page through it; nothing opens a page file of its own.
4. The layout cannot drift: every file in `static/src/` is in the manifest
   and every manifest entry is a file.

## Non-goals

- Reordering the stylesheet into layers, renaming anything, or moving code
  between sections. Every one of those changes the joined bytes; stage 3 does
  them, under the browser suite.
- Serving sections separately (approach C), a bundler, a build step, or any
  change to what the browser loads.
- `static/composer.js`, which is already its own file and stays where it is.

## The layout

```
static/src/
  manifest.json        {"shell": "shell.html", "css": [...], "js": [...]} in join order
  shell.html           the page with its stylesheet and script bodies replaced by a marker line each
  css/<name>.css       the stylesheet's sections, cut at its banners
  js/<name>.js         the script's sections, cut at its banners
```

**The cut.** Each section is a run of whole lines of today's file, from one
banner up to the line before the next. The first script section starts with
the line `(function () {` and the last ends with `})();`: the script stays one
function scope when joined, exactly as now. Names say what a section holds
(`js/crm.js`, `js/production-manager.js`, `css/forms.css`); a section whose
banner covers two areas is named for both rather than split, because a split
inside a banner would be a judgement call this stage does not make.

**The join.** `shell.html` is today's file with the stylesheet's body (the
lines between `    <style>` and `    </style>`) replaced by the one line
`<!-- @css -->` and the script's body likewise by `<!-- @js -->`. The page is
the shell with each marker line replaced by its sections joined end to end.
Each section ends with a newline, so the join is plain concatenation. The
rule is short enough to implement twice, in Python for the server and the
suites and in JavaScript for the browser suite's probes, and a test holds the
two to the same answer.

**The reader.** `pagesource.py`, a module of its own at the top of the
repository like `tokenvault.py`, with no dependencies: `join(root)` returns
the joined page, read from disk each call, and `python pagesource.py
--sha256` prints its fingerprint. The server's `_page_parts()` calls it
instead of opening `static/index.html` (and caches its split exactly as it
does today, so nothing reads it per request). The test suites get the page
from the same function, not from a file; `tests/browser/page-source.js` is
the JavaScript twin, and its unit test compares its fingerprint with the
module's.

## Proof that nothing changed

In the pull request, with the result written there:

1. The join, on the branch, equals `static/index.html` on `main` byte for
   byte (sha256 of both).
2. The server's split, on the branch, gives the same three parts and the same
   `/assets/app.css?v=` and `/assets/app.js?v=` hashes as on `main`.
3. Every suite passes unchanged in what it asserts: the page suite (610), the
   dispatch suite, the browser suite (119, against the same record).

## Guards that stay

| Guard | Where |
|---|---|
| The manifest lists exactly the files in `static/src/css` and `static/src/js`, each once, and the shell exists with both markers once each | page suite |
| Nothing in the repository opens `static/index.html` or any other page file except the reader | page suite (a scan of the tracked Python, JavaScript, YAML and Makefile) |
| The Python and JavaScript joins give the same text (`pagesource.py --sha256` against the JavaScript join) | browser suite unit test |
| The no-dashes check in CI reads `static/src/` and `static/composer.js` | `.github/workflows/tests.yml` |
| The release-note date guard watches `static/src/` and `copilot.py` | page suite |

## Documentation

`docs/ARCHITECTURE.md` ("The page is one file" becomes "The page is one
script in sections": where a screen's code lives and how to add a section);
`README.md`'s "Where things are"; the browser suite's README where it names
the page file.

## Release note

Nothing on screen changes. One plain item, because every app change carries
one: "Behind the scenes: the app's page is now kept in sections, so a change
to one screen is quicker and safer to make. Nothing you see changes."

## Risks

- **The local design rig** reloads the page by watching `static/index.html`;
  it is uncommitted and is updated by hand to watch `static/src/`.
- **A missed reader.** A tool still opening `static/index.html` after the
  move would fail on a missing file, not misbehave: the scan guard names it
  first.
- **A cut through a line the server's split relies on.** The split looks for
  `    <style>` and `    <script>` markers in the joined page; those lines
  stay in the shell untouched, and proof 2 shows the split's result is
  unchanged.
