# Hardening register — 2026-09-04

A delta audit against the register of 2026-09-02, covering everything added
since: the loan-unit register and its asset stickers, the Xero connector's
per-order review, payout notes, Auto Run, the in-app settings path, the
token-vault re-seal, and the connector's own pipeline.

Frameworks applied: OWASP ASVS L3 (application), NIST SSDF (pipeline),
NIST 800-53 / CIS Controls (infrastructure and operations), OWASP SAMM
(process), NIST 800-207 (zero trust).

**Alignment, not compliance.** Everything below describes controls implemented
and verified. Claims of compliance or certification require an assessor.

---

## Headline

The posture is **asymmetric**, and it was pointing the wrong way.

gizmo — which cannot write to the accounts — had two suites in CI, a blocking
dependency audit, a CycloneDX SBOM, bandit SAST, a credential sweep and
Dependabot. The connector — which holds the Shopify and Xero credentials and
posts invoices into the ledger — had none of those tests running, no SBOM, no
Dependabot, a dependency gate set to `high` with three moderate advisories
open beneath it, and an API that served everything to anyone who could reach
it whenever `DASHBOARD_TOKEN` happened to be unset.

Seven findings, all on the connector, all now closed (`9ba062d`).

---

## Fixed in this pass

| ID | Severity | Absent control | Evidence | Fix |
|---|---|---|---|---|
| N1 | **High** | Deny-by-default authorization (ASVS 4.1, 800-207 per-request authz) | `app.use("/api")` read `const required = process.env.DASHBOARD_TOKEN; if (required) {...}` — unset meant no authentication on any route, on the service that writes to the accounts | Missing token now returns 503 and names what to set. Configuration absent closes the door rather than removing it |
| N2 | **High** | Test gate in CI (SSDF PW.7/PW.8) | `.github/workflows/tests.yml` ran typecheck, build, audit and `verify` — never `npm test`. 74 tests asserting the discount fix, the shop-timezone date, and Auto Run's off-by-default rule were unenforced | `npm test` is a blocking step |
| N3 | Medium | Dependency gate at a useful threshold (SSDF PW.4, CIS 16.11) | `--audit-level=high` with three moderate advisories open: body-parser request-size enforcement bypass, two `qs` parser-limit bypasses — on a service parsing JSON off the network | Gate lowered to `moderate`; `qs` pinned to `^6.16.0` via `overrides`, a minor bump inside express's own range. `npm audit` now reports 0 |
| N4 | Medium | Credentials never in URLs (ASVS 3.5, privacy) | The guard accepted `?token=<secret>`, writing a long-lived credential into access logs, proxy logs and Referer headers. gizmo never used it | Authorization header only |
| N5 | Medium | Constant-time secret comparison (ASVS 2.9) | `req.headers.authorization === \`Bearer ${required}\`` | `crypto.timingSafeEqual` over SHA-256 of both sides, so an unequal length cannot throw and become a length oracle |
| N6 | Low | Input validation anchored (ASVS 5.1) | `/^\d{4}-\d{2}-\d{2}/` on the payouts `since` parameter was unanchored; only a downstream `.slice(0,10)` prevented injection into Shopify's search syntax | Anchored. The slice stays as defence, not as the control |
| N7 | Medium | SBOM and dependency updates (SSDF PS.3, PW.4) | No SBOM and no Dependabot on the connector | CycloneDX SBOM produced and retained per run; Dependabot for npm, Docker and Actions |

**Also closed today, from the previous register:**

**O3 — OAuth refresh tokens at rest.** `TOKEN_ENCRYPTION_KEY` is set, and the
vault now re-seals what was *already* on the volume at boot rather than only
sealing future writes — a distinction that would otherwise have left a
rarely-rotated Xero token and every never-rotating MFA secret in plaintext
while the key made the problem look solved. Settings → Connections reports the
state by reading the files, not the environment variable.

---

## Verified as holding

Checked against the current code, not assumed from the previous register.

- **Deny-by-default on gizmo's routes.** `_tab_denied` refuses any unmapped
  `/api/` path; the three new connector operations (`autorun_set`,
  `settings_save`, `payouts`) sit behind the tab gate, and each writing
  operation is additionally admin-gated server-side, with tests that fail if
  the gate is removed.
- **The settings path is not a pass-through.** `settings_save` writes only keys
  on `_CONNECTOR_SETTABLE`; the shop domain, the Xero organisation and every
  credential are absent from the form *and* refused by the server. The form is
  a convenience; the allow-list is the boundary.
- **Strict CSP.** `script-src 'self' https://cdn.shopify.com https://*.shopify.com`
  with no `'unsafe-inline'`, `object-src 'none'`, `base-uri 'self'`,
  `frame-ancestors` computed per request. The asset-tag QR and barcode are
  server-drawn `data:` images specifically so no CDN script was needed.
- **No injection in the new UI.** Every `innerHTML` assignment in today's code
  is a static table header; all external data — Xero documents, payout notes,
  connector settings — is placed with `textContent` or as form values.
- **Shopify search-syntax injection.** Order names reach Shopify through
  `JSON.stringify`, which quotes and escapes them.
- **Xero query injection.** `getInvoiceSnapshot` and `getCreditNoteSnapshot`
  use `escapeXeroWhere`.
- **Rate limiting** applies to the new gizmo endpoints via `_pre_checks`.
- **Audit logging.** Turning Auto Run on or off, changing connector settings
  and writing payout notes each `_track` a line naming the person.

---

## Still open

| ID | Severity | Gap | Owner |
|---|---|---|---|
| O1 | High | MFA is TOTP, not phishing-resistant. Passkey proposal awaiting a yes or no | Cameron (decision) |
| O2 | High | The audit ledger lives on the volume it audits until `LOG_DRAIN_URL` is set | Cameron |
| N8 | Medium | **The connector container runs as root** and mounts the volume holding the idempotency ledger. Same class as gizmo's O4 | Cameron + build |
| N9 | Medium | **No SAST on the connector.** gizmo runs bandit; the TypeScript service has no equivalent | build |
| N10 | Medium | **`MAX_DOCS_PER_RUN` defaults to 1000 while Auto Run is unattended.** Currently set to 2 for testing; if that is cleared, an automatic run could push a thousand documents with nobody watching | Cameron |
| N11 | Low | The connector has no equivalent of gizmo's `tools/sweep_tree.py` credential and invisible-character scan | build |
| O4 | Medium | gizmo container runs as root (written risk acceptance stands) | Cameron + build |
| O5 | Medium | Base images not pinned by digest — `python:3.12-slim` and `node:20-slim` | build |
| O6 | Medium | DNS rebinding window in the external scan | build |
| O7 | Medium | Long-lived static credentials with no rotation calendar | Cameron |
| O8 | Medium | No DAST | build |
| O9 | Medium | No continuous penetration testing programme, no VDP contact | Cameron |
| O10 | Low | Volume encryption at rest relies on the platform; unconfirmed in the console | Cameron |
| O11 | Low | No `pip --require-hashes` | build |

**N8 deliberately not fixed here.** Dropping to a non-root user without first
proving the volume ownership works would break writes to `/data` — and that
ledger is the only thing standing between a re-run and duplicate invoices in
your accounts. It needs an entrypoint that chowns and drops, proven on a
scratch service. Breaking the ledger would be worse than running as root.

---

## Regulatory overlays

The honest answer for this business is that most of the named regimes do not
apply, and saying so is more useful than pretending otherwise.

| Regime | Applies | Why |
|---|---|---|
| **UK GDPR / DPA 2018** | **Yes** | Customer names, addresses, emails and order histories throughout. The relevant controls — minimisation, access control, encryption at rest, audit logging, breach detection — are the ones in this register |
| PCI DSS | No | Neither service ever sees a card number. Shopify Payments handles cards; the connector reads order totals and payout amounts only. The shop's own obligation stays with Shopify's SAQ-A model |
| HIPAA | No | No health data |
| FedRAMP / CMMC | No | No US government or defence customers |
| NIS2 / DORA | No | Not an essential entity, not a financial entity |
| SOC 2 / ISO 27001 | Only on demand | Nothing requires them today. If a trade customer ever asks, this register and its predecessor are the evidence base to start from |

**One GDPR note from this pass:** the new alert email sends order numbers and
failure descriptions through Resend. That is a processor receiving business
data; worth recording in the processor list, and worth keeping customer names
out of alert bodies — which the current wording already does.

---

## Recurring items

- Dependency audit and SBOM: every push, both repositories (now true of both).
- Dependabot: weekly, both repositories.
- Credential rotation: quarterly, once O7 has a calendar.
- Restore test: confirm a backup restores, quarterly.
- Re-assess this register: after the next substantial feature, or in 90 days.
