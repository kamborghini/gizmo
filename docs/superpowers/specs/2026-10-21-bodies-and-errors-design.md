# Request bodies checked at the door, and errors that say why they are quiet

**Approved 21 Oct 2026.** Stage 5, piece 1 of the 14 October engineering
audit (request models on write routes; the error-handling triage, A4).
Cameron approved all three parts.

## Why

Measured on main 4cb6e6f, after stage 4:

- **Errors.** 434 broad handlers (`except Exception` or bare) across
  `copilot.py`, the `gizmo` package, `server.py` and the integrations: 407 log,
  answer, raise or fall back; 27 swallow the error silently (`pass`,
  `continue`, a bare `return`), 24 of them with no comment saying why.
- **Request bodies.** 131 of 151 routes are POST; 93 read body fields, 349
  distinct reads, each route checking its own. A probe inside the suite's
  sandbox sent 1,361 requests, one field at a time set to the wrong type (an
  object), across 83 write routes:
  - 7 routes answered with a server error: memory (delete, set_status),
    reconciliation exceptions (limit, min_pence), shipping settings (boxes),
    impact (add), production state (made), skills (delete), What's new
    (seen);
  - 10 routes answered 200 and kept the object as text: CRM activities (seven
    fields), CRM contacts (person and organisation names), Files folders, Size
    list rules (in the live overrides file), store knowledge, the chase log,
    loan units, the mail sign-off (in the accounts file), privacy answers, What's
    new requests.
- The page never sends a wrong type, so nobody has seen these; they are what a
  stray script, an old tab or a typo in the browser's console would do.

## What changes

1. **Silent errors say why, and new ones cannot hide.** `tools/broad_excepts.py`
   classifies every broad handler; a test fails on a silent one with no comment
   saying why. Each of the 24 is read and gets its reason, a log line, or a
   narrower exception, whichever is true of it.
2. **Bodies checked at the door.** `gizmo/bodies.py` (on the floor): `Body`, a
   pydantic model whose named fields are checked and whose other fields pass
   through, and the field kinds (text, a number, yes or no, a list, a set of
   fields) with their plain words. `gate._guard(request, model=...)` checks the
   body before the route sees it, one model or one per `op`; a wrong type is a
   400 naming the field ("The title sent must be text."). The route reads the
   body as before. The models accept what the page sends today. First on the
   seven routes that broke.
3. **The routes that kept junk get models, and the rest are counted.** The ten
   above. A test lists every write route that reads body fields without a model;
   the list may only shrink. `docs/API.md` gains a Body column naming each
   route's model.

A release note, "Requests checked at the door": "Every change the app is
asked to make is now checked field by field before it is made, so a request
with a field of the wrong kind is refused with a reason instead of failing or
being saved as nonsense. Nothing looks different."

## Not in this piece

Models for the other write routes (later pieces, area by area); the dispatch
suite's log noise (A6, stage 6); any change to what a route does with a body it
accepts.
