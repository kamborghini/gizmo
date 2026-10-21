# Errors that fall back say why

**Approved 21 Oct 2026** under Cameron's standing yes for the evening ("assume
I approve anything you need"). Stage 5, piece 5 of the 14 October engineering
audit (A4, the error-handling triage). Piece 1 (#61) gave a reason or a log
line to every broad handler that let an error go with a `pass`, a `continue` or
a bare `return`, and a test keeps it so.

## Why

The same scan (`tools/broad_excepts.py`) finds 42 more handlers that let the
error go by putting a value in its place: an error body that is not JSON read
as text, an unreadable timestamp read as "due", a size that cannot be read
measured later. 36 say nothing about why. Most are right; three hide a failure
someone would want to find:

- the AI spend cap: a usage log that cannot be read makes the day's spend
  count from nothing, so the cap stops holding for the day;
- erasure marks: a token vault key that cannot be read makes marks without
  their pepper, so they no longer match marks made with it;
- Shopify's privacy webhook: a body that cannot be read leaves a privacy
  request recorded with no customer, and nothing says so.

## What changes

1. The guard widens: a handler that falls back to a value without logging,
   answering or raising is silent too, and says why in a comment on its own
   lines (`t_no_error_is_swallowed_without_a_reason`).
2. 33 get their reason. The three above log a warning; the spend cap's missing
   usage log (the normal first day) is told apart from an unreadable one and
   stays quiet.

A release note, "Fewer quiet failures". Nothing looks different.

## Not in this piece

What any handler does: every fallback value is unchanged.
