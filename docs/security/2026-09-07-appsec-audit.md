# Application security audit — 2026-09-07

A full-system audit of gizmo (Starlette app, single-file SPA, JSON stores on a
Railway volume) and the shopify-xero-connector, from the perspective of a
senior application-security engineer. It supersedes nothing: the registers of
2026-09-02 and 2026-09-04 were read first, their claims re-tested against the
code as it is today, and the two that no longer held are findings below.

Frameworks applied: OWASP ASVS L3, NIST SSDF, NIST 800-53 / CIS Controls,
NIST 800-207, OWASP SAMM.

**Alignment, not compliance.** Everything here describes controls implemented
and verified by test. Compliance or certification claims require an assessor.

**This report does not say the application is secure.** It says what was
examined, what was found, what was fixed, what was left, and what remains
exposed. Four things were found that the previous registers described as
already handled.

---

## 1. Current security posture

What is genuinely good, and was re-verified rather than assumed:

- **One central lock, deny by default.** `_tab_denied` maps every `/api/`
  route to a tab and refuses anything unmapped that is not on an explicit open
  list — a new route added without deciding who may call it is refused loudly
  in testing rather than served. Role checks are server-side; the UI gates are
  decoration over them.
- **No cookies anywhere.** The session is a random 32-byte token stored as a
  SHA-256 hash server-side and sent as a custom header, so there is no CSRF
  surface to defend and the store file cannot impersonate anyone.
- **Passwords and recovery codes are scrypt.** TOTP secrets are sealed with
  AES-GCM at rest, and the vault re-seals what is *already* on the volume at
  boot rather than only future writes.
- **Webhooks authenticate by HMAC over the streamed body**, with a hard byte
  cap, a shop-domain check and delivery-id de-duplication.
- **The AI is read-only and tab-gated.** No write capability joins any tool
  registry; a person denied the Customers tab cannot walk in through Chat.
- **DOM hygiene in the SPA is real.** Of 317 `innerHTML` writes, every one is
  constant markup or an icon constant; `el()` is `textContent`; received email
  is never rendered as HTML at all; the composer uses an inert `DOMParser`
  with an allow-list mirroring the server's.
- **Every outbound call has a timeout; every pagination loop is bounded**;
  request bodies are capped on bytes actually read, not on a header.
- **Git history is clean.** All 413 commits, 2,562 blobs, scanned for fifteen
  credential shapes: only test fixtures and documented placeholders.
- **CI runs least-privilege** (`contents: read`), actions pinned by SHA,
  blocking dependency audit, CycloneDX SBOM, bandit, credential sweep.
  `pip-audit` and `npm audit` are both clean today.
- **The connector fails closed**: no `DASHBOARD_TOKEN`, no service.

## 2. Critical

**None found.** No unauthenticated path to customer data, to money, or to the
accounts was identified in this pass. That is a statement about what this
audit examined, not a guarantee: the highest-value target — a staff session
token in `localStorage` — is protected by a Content-Security-Policy whose
weakness is finding M1 below, and no external testing has ever been run
against this application (§9).

## 3. High

| ID | Finding | Status |
|---|---|---|
| **H1** | **The second factor could be removed by the session it protects.** `/api/auth/mfa` `op=off` deleted MFA behind a session alone, and `start`/`confirm` re-bound it to a new phone the same way. A stolen or borrowed session token could therefore permanently remove the control that exists for exactly that event — or silently bind the attacker's own authenticator. No password, no re-authentication, one request. | **Fixed** |
| **H2** | **An erasure the next sync undid.** `customers/redact` popped the CRM person and the mail threads. The Pipedrive importer already refuses to recreate contacts deleted by hand (it consults a tombstone list); redaction never wrote one, so the next import restored the person. Gmail still holds the correspondence and the sync looks back 730 days, so a deleted thread was simply "not in threads" and was re-fetched within minutes. `privacy_log.json` recorded a UK GDPR Art. 17 erasure that did not stick. | **Fixed** |
| **H3** | **Nothing gates a deploy.** `main` has no branch protection and no rulesets; CI triggers on `push` to `main`, which is the branch Railway auto-deploys. A red suite, a failed dependency audit, a bandit hit or a credential caught by the sweep all deploy anyway. Every CI control in every register is advisory until this is closed. | **Open — Cameron** |
| **H4** | **MFA is TOTP, not phishing-resistant** (carried from O1), and **the audit ledger still lives on the volume it audits** until `LOG_DRAIN_URL` is set (carried from O2). | **Open — Cameron** |

## 4. Medium and low

| ID | Sev | Finding | Status |
|---|---|---|---|
| M1 | Med | **`script-src` trusted every Shopify host.** `https://cdn.shopify.com` is where App Bridge lives *and* where Shopify serves every store's uploaded Files — and Files accepts `.js`. Anyone with a free development store could host JavaScript on a host this CSP trusted. `img-src https:` and `connect-src https://*.myshopify.com` gave a compromised page two exfiltration channels, the second registrable by anyone for the price of a trial signup. | Fixed |
| M2 | Med | **One person's work survived into the next person's session.** Chat history (including AI answers over orders and customers) and the store profile live in `localStorage`; sign-out cleared only the session token, and in-memory caches were never dropped. On a shared dispatch PC the next account saw the previous person's conversations. | Fixed |
| M3 | Med | **A TOTP code from a phone one step ahead could be replayed.** The stored counter was `used_counter()` — the current step — not the counter the code actually matched, so a code from a phone 30 seconds fast was accepted, and accepted again once the clock caught up. | Fixed |
| M4 | Med | **No per-account limit on wrong second-factor codes.** Five misses ended a ticket, but a ticket costs one correct password and tickets were mintable eight a minute — so whoever had the password got a fresh five, indefinitely, each miss writing two rows into a fixed-size audit ledger. | Fixed |
| M5 | Med | **The courier credentials were the one long-lived credential in plaintext**, outside the vault and outside the boot re-seal, while the vault's own documentation said it covered them all. They book shipments on the merchant's account. The file was also chmod'd *after* the write, not opened 0600. | Fixed |
| M6 | Med | **The log drain could drop audit events and ship secrets.** It scrubbed the *serialised* event, so a redaction could produce invalid JSON — `json.loads` then raised, the caller swallowed it, and the audit row never left the box. Its patterns missed `key: <value>`, `"secret": "..."` and the break-glass password line. | Fixed |
| M7 | Med | **Wrong drive passwords cost a scrypt each, 300/minute.** WebDAV's ceiling is deliberately generous for Finder; each unauthenticated miss ran a full scrypt on the event loop before failing. | Fixed |
| M8 | Med | **Deleting files for good had no rank check.** `destroy` and `empty_trash` — the only file operations with no undo — were open to any account with the Files tab. | Fixed |
| M9 | Med | **The orders webhook answered 200 to any signed topic.** A privacy topic delivered to the wrong endpoint would be acknowledged as handled, and Shopify does not retry a 200. | Fixed |
| M10 | Med | **The credential sweep skipped `tests/` wholesale.** `test_dispatch.py` is 800 KB; a real key pasted into it would never have been flagged. | Fixed |
| M11 | Med | **The connector bearer token would travel anywhere `CONNECTOR_URL` pointed**, including a typo'd plain `http://` host. Same for `LOG_DRAIN_TOKEN`. | Fixed |
| M12 | Med | **A chunked WebDAV upload spooled to disk before the quota was checked**, so a client sending no `Content-Length` could fill the container's disk with bytes that were always going to be refused. | Fixed |
| M13 | Med | **Sessions slid forever.** A session used once a day never expired, and neither would a stolen one. | Fixed |
| M14 | Med | **Authenticated JSON carried no `Cache-Control`.** On a shared machine the browser's disk and back-forward caches outlive the session. | Fixed |
| M15 | Med | **CI gaps**: bandit never read `pipedrive.py`; Dependabot watched neither the Docker base image nor the extensions' npm lockfile; `pip-audit` was installed unpinned on a blocking step. | Fixed |
| L1 | Low | The static guard against untrusted markup matched only the exact text `.innerHTML = ` and only read the page script — `+=`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `new Function` and the whole of `composer.js` passed it silently. `ico()` also trusted its caller. | Fixed |
| L2 | Low | The OAuth landing pages set no `frame-ancestors`. | Fixed |
| L3 | Low | The chat streaming route never received the app session, so it 401'd on every turn and the page silently fell back — after the request had already spent a slot in the global AI window. | Fixed |
| L4 | Low | A refused tab (403) left no audit row; the payouts and disputes chat tools were absent from the tool-to-tab map; an unreachable `data:` URL branch could hand a courier-supplied string to `window.open`; the EORI SOAP client followed redirects; the pre-redact archive never expired. | Fixed |
| L5 | Low | Four captured SOAP fault dumps and a 116 KB synthetic fixture were tracked and shipped in the image; `.dockerignore` did not exclude `.env`. | Fixed |
| L6 | Low | Google Fonts is a third-party call on every page open, and the two CSP hosts that exist only for it. | Open — §8 |

## 5. Threat model

**Assets.** Shopify Admin credentials and the scopes behind them (orders,
customers, fulfilment, payouts). Gmail (two mailboxes), Xero, Pipedrive,
World Options and Resend credentials. Customer PII in JSON stores: names,
addresses, emails, order history, mail bodies, attachments, CRM notes. The
audit ledger and the idempotency ledgers. The users store. Availability of the
dispatch desk during business hours.

**Actors.** Staff at four ranks, trusted for their rank and not beyond it. The
connector service. Shopify, Google, Xero, the courier, Resend. The anonymous
internet, which can reach the SPA, `/api`, `/dav` and `/mcp` on the public
Railway domain. A phished or malware-infected staff device. CI and Railway,
either of which can put code into production.

**Trust boundaries.**

1. Browser → `/api` and `/dav`. Session token (Bearer from `localStorage`) or
   HTTP Basic for the drive; authorised per route, deny by default.
2. Browser → R2 bucket, via presigned URLs; CSP `connect-src` pinned to the
   account endpoint.
3. Claude.ai → `/mcp`, bearer-gated, 503 when unset. Read-only tools.
4. Shopify → webhooks, HMAC over the raw body; privacy topics drive redaction.
5. gizmo → connector, private Railway network, bearer plus a header for writes.
6. gizmo → Google / Xero / Pipedrive / courier / Resend, tokens sealed at rest
   and excluded from backups.
7. GitHub → Railway: push to `main` deploys. **CI is advisory** (H3).
8. Operator → Railway console: env vars, volume, logs. Outside the codebase.

**Realistic attack paths.**

- Phished password → TOTP is the only remaining factor, and it is
  phishable in real time (H4). Before this pass, one request from the
  resulting session removed it permanently (H1).
- A markup sink anywhere in the SPA → session token out of `localStorage` →
  full staff session. The CSP is what makes this survivable, and its
  `script-src` trusted uploads from any Shopify store (M1).
- A shared browser between shifts → the previous person's AI answers over the
  customer list (M2).
- A malicious file through the drive or Files → served back or opened on a
  staff machine. Mitigated by extension gating, `nosniff` and the byte-sniff
  verdict.
- A bad or malicious commit → `main` → production, with no gate (H3).
- Supply chain: pinned dependencies, clean audits, SHA-pinned actions; base
  images pinned by tag only.

## 6. Recommended security architecture

The shape is already right; four things would change its class.

1. **Make identity phishing-resistant.** WebAuthn/passkeys as the second
   factor, TOTP kept only as a fallback for a lost device. This is the single
   change that most reduces real risk here, because the realistic entry is a
   phished password, not a broken control.
2. **Make the pipeline the gate, not the observer.** A ruleset on `main`
   requiring the `tests` check, and/or Railway's "wait for CI". Every control
   in three registers is advisory without it.
3. **Get the evidence off the box.** `LOG_DRAIN_URL` set, so the audit ledger
   survives losing the volume it lives on and a deletion cannot also delete
   its own record.
4. **Keep one authorization choke point and one credential path.** Both exist
   (`_tab_denied`; the token vault). This pass closed the two places that had
   drifted outside them — the second-factor settings and the courier file.
   New code joins them rather than repeating them.

## 7. Changes implemented

Four commits, `2060c8f`, `1bda39d`, `3c82b66`, `d656085`. 704 dispatch tests
and 282 frontend guards pass, 26 of them written for this pass — one per
finding, asserting the behaviour that was wrong rather than the fix that was
applied.

**Identity and access.** Turning the second factor off, or re-enrolling a new
phone, requires the account password. Wrong passwords at the login, the
password change and the second-factor settings share one counter and one
escalating lock (the password change previously had its own flat 15 minutes;
the settings had no counter). The stored TOTP counter is the one the code
matched, so a code from a fast phone cannot be replayed. Ten wrong codes pause
the account, and those refusals are coalesced in the ledger the way wrong
passwords already were. An admin can reset a lost second factor at the same
rank rule as a password reset. Sessions expire 30 days after they were minted,
however recently used. WebDAV refuses a client after twenty wrong passwords a
minute, before scrypt runs. `destroy` and `empty_trash` are admin-only. The
payouts and disputes tools sit behind the recon tab. Refused tabs are logged,
bounded to twenty an hour.

**Data and secrets.** Redaction now tombstones the CRM person and records the
address in the mailbox, so neither the importer nor the sync brings them back.
The pre-redact archive is deleted after 30 days and the retention is stated in
the privacy note. A restore writes a provenance line into the restored ledger.
Courier credentials are sealed, written 0600 from creation, and covered by the
boot re-seal. The log drain walks the event rather than its serialised text,
catches the phrasings people actually write, refuses a non-https sink, and
never carries the break-glass password.

**Boundaries.** `script-src` is path-scoped to `cdn.shopify.com/shopifycloud/`
with no wildcard host; `img-src` and `connect-src` name only what the page
actually uses. OAuth pages refuse framing. The orders webhook takes order
topics only. A chunked drive upload cannot spool past what the quota could
accept. The EORI client refuses redirects. The connector token will not travel
to a plain-http host. Authenticated JSON is `no-store`.

**The browser.** Cached work is stamped with whose it is and dropped when
somebody else signs in; sign-out and session expiry reload rather than
painting a login screen over the last person's data. `ico()` accepts only our
own icon markup. The static guards cover every HTML sink and `composer.js`.
The streaming chat call sends the session, and the route authorises before
spending an AI slot.

**Pipeline.** bandit reads `pipedrive.py`; Dependabot watches Docker and npm;
`pip-audit` is pinned; the credential sweep reads the tests against a named
fixture allow-list — verified by pasting a token-shaped string into a test
file and watching the sweep fail.

## 8. Changes deliberately not implemented

- **Binding vault envelopes to their field (AAD).** Proposed so a sealed value
  cannot be transplanted between fields or users. The only actor who could do
  that already has write access to `/data` — and can therefore rewrite
  `users.json` wholesale, including the scrypt hash of a password they choose.
  The binding buys nothing against the actor who could use it, and the upgrade
  path (v1 envelopes re-sealed at boot) breaks every live OAuth connection on
  a single mismatched call site. Not worth the failure mode.
- **Blocking `activity.json` and `privacy_log.json` at restore.** Proposed so
  a crafted zip cannot overwrite the audit trail. Restore is the documented
  recovery path for a lost volume, and the suite asserts history survives that
  move; blocking these would mean recovering the desk and losing its evidence.
  Restore is master-only, and a master can already read everything. Instead
  the restore writes a line into the restored ledger saying where the history
  came from and who restored it.
- **Removing the commit SHA from `/healthz`.** It exists so "is the deploy
  live" is an exact check rather than an inference from a 200. The repository
  is private and the hash is not actionable on its own.
- **Stripping the customer domain from `data/gobo-overrides.csv`.** That row
  is production sizing data — it is why one customer's Ayrton Diablo gobos are
  cut at 25 mm. It is a company's public web domain in a B2B sizing rule, and
  removing it would change what the bench cuts.
- **Removing the `window.__demo` debug hooks.** Same-origin script can already
  do everything they expose; they are a convenience, not a capability.
- **Self-hosting Geist instead of Google Fonts (L6).** It is a real privacy
  item — every staff open sends an IP to Google, and two CSP hosts exist only
  for it — but it needs the font files under the hashed-asset contract and a
  licence note. Left open rather than done badly.
- **Branch protection, non-root containers, digest-pinned base images.**
  Console or build changes that are not mine to make (§9).

## 9. Remaining risks

| Risk | Why it stands | Owner |
|---|---|---|
| **A red build still deploys** (H3) | No ruleset on `main`, no "wait for CI" in Railway | Cameron |
| **A phished password plus a phished code is a full session** (H4/O1) | TOTP is not phishing-resistant. Passkeys are a decision, not a patch | Cameron |
| **The audit ledger can still be lost with the volume** (O2) | `LOG_DRAIN_URL` unset. The drain is now trustworthy when it is set — that was M6 | Cameron |
| **Whoever is first through the door after a volume loss becomes master** | `/api/auth/setup` bootstraps the first account from any Shopify staff session when `users.json` is absent. That is also the only recovery path. A `SETUP_ALLOWED` env flag would close it at the cost of needing a console change before recovery | Cameron (decision) |
| **Containers run as root; base images pinned by tag** (O4/O5) | Dropping privileges without proving volume ownership would break `/data` writes | Cameron + build |
| **No DAST, no external testing, no VDP contact** (O8/O9) | Nothing has ever attacked this application from outside. Everything in this report is code review and unit tests | Cameron |
| **XSS remains the highest-impact class** | The session lives in `localStorage`, so any markup sink is account takeover. The CSP is now tight and the guards are broad, but neither is proof | build |
| **The CSP change is unverified in production** | `script-src` no longer allows arbitrary `*.shopify.com`. App Bridge loads one script from `cdn.shopify.com/shopifycloud/` and the code says it builds no others — but only a real browser enforces CSP. Watch the console on the first open after deploy | build |
| **Long-lived static credentials, no rotation calendar** (O7) | Unchanged | Cameron |
| **Volume encryption at rest unconfirmed** (O10) | Platform-dependent, not visible from the code | Cameron |

**Recurring items** (unchanged from 09-04, plus one): dependency audit and
SBOM every push; Dependabot weekly, now including Docker and npm; quarterly
credential rotation once O7 has a calendar; quarterly restore test; **and a
check that a deploy cannot outrun a red build**, which is the item that makes
all the others enforceable.
