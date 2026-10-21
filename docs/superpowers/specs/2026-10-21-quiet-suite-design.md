# A test run that shows the failure

**Approved 21 Oct 2026** under Cameron's standing yes for the evening ("assume
I approve anything you need"). Stage 6, piece 1 of the 14 October engineering
audit (A6: the dispatch suite prints about 7,300 lines, mostly expected-path
logs and tracebacks, so a real failure is hard to spot in CI output).

## What changes

1. The dispatch suite holds what the app logs during each test and prints it
   only under that test's FAIL line (the last 80 lines when there are more).
   A passing run prints one line per test and the total. `VERBOSE=1` streams
   every log line as it comes, as the suite always did. The held handler is on
   the root before `server.py` is imported, so its `basicConfig` adds none and
   the level stays INFO.
2. The three regular expressions in `tests/test_frontend.py` written with
   invalid escapes (`"\."`) become raw strings with the same values, which
   ends the SyntaxWarnings every run printed.
3. `docs/ARCHITECTURE.md` and the README say how a run reads and what
   `VERBOSE` and `ONLY` do.

Measured: a full run printed about 6,900 lines; it now prints 1,076 (one per
test, the total, and one RuntimeWarning from a streaming test, left alone).

No release note: nothing in the app changes.
