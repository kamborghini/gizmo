"""The dispatch suite: the server through its routes, built exactly as it is
served (server.build_app(), real middleware), against scratch stores and
stand-ins for every outside system; nothing reaches /data or the network.

Its tests are in sections under tests/dispatch/, a file per stretch of the
suite as it grew, cut where its banners stood and between tests in the longest
stretches. Run in one namespace in the order below, they are exactly the one
file this was until stage 6 of the 14 October audit: the harness first, the
runner last (t_the_suite_is_in_sections). A new test goes at the end of the
section whose subject it shares, or of the last section.

    python tests/test_dispatch.py              every test
    ONLY=part_of_a_name python tests/...       the tests whose names contain it
    VERBOSE=1 python tests/...                 the app's log as it comes
"""
import os

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dispatch")
SECTIONS = [
    'harness.py',                        # the setup every test runs in: environment, scratch stores, stand-ins, helpers
    'dispatch-envelopes.py',             # unit: envelope construction
    'dispatch-config.py',                # routes: config
    'dispatch-routes-1.py',              # routes: quote/book/label/cancel (part 1 of 3)
    'dispatch-routes-2.py',              # routes: quote/book/label/cancel (part 2 of 3)
    'dispatch-routes-3.py',              # routes: quote/book/label/cancel (part 3 of 3)
    'order-sweep-snapshot.py',           # Order sweep snapshot
    'custom-shipments.py',               # Custom address dispatch
    'chase-desk.py',                     # Chase desk
    'live-desk-webhooks.py',             # Live desk webhooks
    'per-person-colour.py',              # Per-person colour
    'second-factor.py',                  # Second factor
    'logs-off-the-box.py',               # Shipping logs off the box
    'token-encryption-at-rest.py',       # Token encryption at rest
    'shopify-permissions.py',            # What the app is allowed to ask Shopify for
    'perimeter.py',                      # The perimeter, swept
    'size-list-permission-gate.py',      # Size-list permission gate, at the route
    'shopify-privacy-webhooks.py',       # Shopify privacy webhooks
    'crm.py',                            # CRM
    'stock-bridge.py',                   # Stock bridge (gizmo -> zeta)
    'unprocessed-queue.py',              # Unprocessed queue
    'app-shell.py',                      # The app shell
    'files.py',                          # files: the R2 file store
    'accounts.py',                       # accounts: the app's own auth
    'page-layouts.py',                   # Page layouts: each person's own arrangement of a screen's cards
    'shared-inbox.py',                   # shared inbox
    'mail-sending-1.py',                 # Sending, not just drafting (part 1 of 2)
    'mail-sending-2.py',                 # Sending, not just drafting (part 2 of 2)
    'payment-terms.py',                  # payment terms
    'order-edit.py',                     # order edit
    'audit-batch-4.py',                  # Audit batch 4: the chat tool gate, memory provenance, and three data traps
    'audit-batch-5.py',                  # Audit batch 5: ambiguous writes, a long print run, and two unbounded reads
    'net-30-payment-terms.py',           # NET-30, now that write_payment_terms is actually granted: the paths past the permiss
    'reconciliation-engine-1.py',        # Reconciliation engine: the auditor must itself be auditable (part 1 of 3)
    'reconciliation-engine-2.py',        # Reconciliation engine: the auditor must itself be auditable (part 2 of 3)
    'reconciliation-engine-3.py',        # Reconciliation engine: the auditor must itself be auditable (part 3 of 3)
    'two-mailboxes-1.py',                # Two mailboxes: the sales inbox and the accounts mailbox must never mix (part 1 of 2)
    'two-mailboxes-2.py',                # Two mailboxes: the sales inbox and the accounts mailbox must never mix (part 2 of 2)
    'size-list-flagged-models.py',       # resolving a flagged model from inside the app
    'eori-checker.py',                   # EORI checker
    'mail-footer-and-sign-off.py',       # mail: footer, sign-off, saved replies
    'mail-composer.py',                  # mail: the composer's server half
    'hardening-1.py',                    # security hardening and the September additions (part 1 of 2)
    'hardening-2.py',                    # security hardening and the September additions (part 2 of 2)
    'bug-audit-2026-09-19-lows.py',      # The 2026-09-19 bug audit, the lows (B33, B36-B46)
    'bug-audit-2026-09-19-highs.py',     # The 2026-09-19 bug audit (docs/bugs/2026-09-19-bug-audit.md): the highs and the patt
    'bug-audit-2026-09-22-p2s-1.py',     # The 2026-09-22 bug audit (docs/bugs/2026-09-22-bug-audit.md): the P2s, each pinned b
    'bug-audit-2026-09-22-p2s-2.py',     # The 2026-09-22 bug audit (docs/bugs/2026-09-22-bug-audit.md): the P2s, each pinned b
    'bug-audit-2026-09-22-p3s.py',       # The 2026-09-22 bug audit, the P3s
    'claude-opus-5-5.py',                # Claude Opus 5.5, 24 September 2026: it thinks on every request, refuses a forced too
    'speed-timing-and-compression.py',   # speed: live timing, compression, the loop
    'speed-review-of-15.py',             # review of #15
    'speed-order-snapshot.py',           # speed: the order snapshot survives a known change
    'speed-review-order-cache.py',       # review of the order-cache change
    'speed-review-recheck.py',           # re-check of the review fixes
    'speed-crm-board.py',                # speed: the CRM board, built once per version
    'speed-files.py',                    # speed: Files, instant actions
    'speed-inbox.py',                    # speed: the Inbox, lighter
    'speed-production-manager.py',       # speed: the Production Manager's follow-up calls
    'split-guards.py',                   # Moving code out of copilot.py without a test going blind
    'split-dispatch-module.py',          # Dispatch in its own module (stage 4, piece 1)
    'stages-4-to-6.py',                  # the floor (stage 4, piece 2), and the stages 4 to 6 tests after it
    'stock-foundation.py',               # Stock in Reactor: the stores, the figures, the move (plan 1 of 4)
    'stock-sheet.py',                    # Stock in Reactor: the sheet, served (plan 2a)
    'stock-buying.py',                   # Stock in Reactor: buying, orders and deliveries (plan 2a)
    'stock-overview.py',                 # Stock in Reactor: quarters, settings, warnings, history (plan 2a)
    'runner.py',                         # the runner's own toy tests, and the runner
]


def source() -> str:
    """The whole suite as one text, in order: what a check of the suite reads."""
    return "".join(open(os.path.join(DIR, name), encoding="utf-8").read() for name in SECTIONS)


if __name__ == "__main__":
    suite = {"__name__": "__main__", "__file__": os.path.abspath(__file__), "suite_source": source}
    for name in SECTIONS:
        path = os.path.join(DIR, name)
        exec(compile(open(path, encoding="utf-8").read(), path, "exec"), suite)
