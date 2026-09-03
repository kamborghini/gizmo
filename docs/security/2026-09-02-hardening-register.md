# Hardening register, 2026-09-02

Scope: gizmo (Starlette app in copilot.py/server.py, single-file SPA plus
composer.js, Railway container, GitHub CI, R2 bucket, Railway volume).
Frameworks applied as the skill prescribes: OWASP ASVS L3, NIST SSDF,
NIST 800-53 / CIS v8.1, OWASP SAMM, NIST 800-207. Regulatory overlays: no
card data (Shopify holds it), no PHI, no federal data; UK GDPR alignment via
the privacy webhooks and redaction. Alignment, never "compliant".

Evidence was observed, not assumed: route guards enumerated from the source,
headers and session handling read, bandit run, the tree swept, CI read.

## Fixed in this pass (commit follows in history)

| ID | Sev | Gap | Evidence | Fix |
|----|-----|-----|----------|-----|
| G1 | High | Deny-by-default: `_tab_denied` allowed any `/api/` route it had no mapping for | 25 routes unmapped, incl. `/api/eori/` | Unmapped routes refused unless on the explicit `_OPEN_API` list; EORI mapped to the labels tab; test |
| G2 | Med | Raw bidirectional and invisible characters in source (bandit B613) | copilot.py filename regex, CSV BOM literal, index.html BOM | Written as escapes; CI sweep refuses any recurrence |
| G3 | Med | Untrusted XML parsed with stdlib ElementTree (EU EORI answer, World Options answer) | bandit B314 x2 | DOCTYPE/ENTITY refused before the parser sees the body; test |
| G4 | Low | SHA-1 fingerprints read as a security hash (bandit B324) | recon.py x2 | `usedforsecurity=False` |
| G5 | Med | No SAST gate in CI | tests.yml had none | bandit at high severity and high confidence, blocking |
| G6 | Med | No secrets or invisible-character scan in CI | none | `tools/sweep_tree.py`, zero-dependency, blocking |
| G7 | Med | No SBOM per build | none | CycloneDX from pip-audit, uploaded with every run |
| G8 | Med | Actions pinned by tag, not commit | `@v4`, `@v5` | Pinned by SHA with the tag in a comment |
| G9 | Med | No dependency update automation | none | Dependabot for pip and actions, weekly |

## Confirmed present (no change needed)

Session in a header, not a cookie (CSRF has no ambient credential to ride);
32-byte random sessions with expiry, sliding renewal and a per-user cap;
per-account login lockout plus a coalesced noise ledger; per-client rate
limiting on every route and separate ceilings for EORI and DAV; CSP with no
unsafe-inline for scripts, HSTS, nosniff, no-referrer, Permissions-Policy,
frame-ancestors; OAuth connect gated by single-use ticket or connect secret
with namespaced single-use state; SSRF: allow-listed hosts for the store
crawl, public-IP check on every redirect hop for the external scan, fixed
hosts for EORI and R2; presigned uploads bound to size and type, SVG never
inline; attachments only from the caller's own prefix or live Files; server
sanitiser for every outgoing email with a vector test set; page guard that no
untrusted text reaches innerHTML; TOTP with replay protection and hashed
recovery codes; token vault (AES-GCM) and log drain with credential scrubbing
(both inert until their env vars are set, see below); pip-audit blocking in
CI; exact dependency pins including transitive security floors; privacy
webhooks and redaction; retention sweeps.

## Open, with owner

| ID | Sev | Gap | Owner | Action |
|----|-----|-----|-------|--------|
| O1 | High | MFA is TOTP, not phishing-resistant | Cameron (decision), then build | Passkeys (WebAuthn) as a second factor alongside TOTP: enrolment in Settings, assertion at sign-in. ~200 lines with `cryptography` (no new dependency) or the `webauthn` package. Needs a design approval; proposed below. |
| O2 | High | Audit ledger lives on the volume it audits until `LOG_DRAIN_URL` is set | Cameron | Set `LOG_DRAIN_URL` (+ token) in Railway; adjust `logdrain._default_sender` to the provider's shape |
| O3 | High | OAuth refresh tokens rest unencrypted until `TOKEN_ENCRYPTION_KEY` is set | Cameron | `openssl rand -base64 32` into Railway |
| O4 | Med | Container runs as root (written risk acceptance stands) | Cameron + build | Entrypoint that chowns `/data` then drops to an unprivileged user; prove on a scratch service first |
| O5 | Med | Base image not pinned by digest | build | Pin `python:3.12-slim@sha256:...` once a digest is chosen; Dependabot will then bump it |
| O6 | Med | DNS rebinding window in the external scan (resolve, then connect) | build | Resolve once and connect to the checked IP with the host in SNI; or accept: admin-initiated, 12s timeout, redirects re-checked |
| O7 | Med | Long-lived static credentials: Shopify offline token, World Options key, connect secret | Cameron | Rotation calendar (quarterly) recorded in Settings; the app already keeps them write-only |
| O8 | Med | No DAST | build | A ZAP baseline against the rig in CI, nightly, non-blocking to start |
| O9 | Med | No continuous penetration testing program | Cameron | Annual external test plus a standing VDP contact address; record in SAMM |
| O10 | Low | Store files on the volume rely on platform encryption | Cameron | Confirm Railway volume encryption at rest in the console; record |
| O11 | Low | No `pip --require-hashes` | build | Hash-pin once the transitive set is fully enumerated |

## Proposal for O1 (needs your yes)

Passkeys beside the existing TOTP: a person enrols a passkey in Settings
(Touch ID, security key, or phone), sign-in accepts a passkey assertion where
it accepts a TOTP code today, and admins can require a passkey per account
from the Team tab. Recovery codes stay. Origin and RP ID pinned to the app's
host; assertions verified with `cryptography` (ES256/RS256), counters checked
for clones. Same session, same rules after sign-in.

## Regulatory note

PCI DSS: not in scope (no cardholder data touches gizmo; Shopify Payments).
HIPAA and FedRAMP: not applicable. UK GDPR: aligned (lawful basis is the
merchant's; data subject requests via the Shopify privacy webhooks; retention
sweeps; redaction). ISO 27001 / SOC 2: not claimed.
