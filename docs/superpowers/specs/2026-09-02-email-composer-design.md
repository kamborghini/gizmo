# Email composer: formatting, attachments, images, replies

Date: 2026-09-02. Status: approved in conversation; awaiting spec review.

## Goal

The Inbox composes email the way Gmail does, from both Compose and Reply:
rich formatting (bold, italic, underline, font, size, colour, alignment,
lists, links, quotes), file attachments from the computer or from Files,
inline images, a footer with the shop's logo, CC/BCC, and the quoted
original beneath a reply. Everything stays behind the existing per-person
send grant and the dry-run confirm step.

## Not in this build

Scheduled send, undo send, emoji picker, confidential mode, rendering of
incoming HTML in the thread view, rich saved replies (they stay plain text
and are inserted as paragraphs). Each is a separate request if wanted.

## Decisions already made

- Editor: hand-built on `contenteditable`, zero dependencies (approach A).
- Footer: fixed slots (logo, company, address, phone, website, legal), not
  free-form HTML.
- The quoted original is assembled and sanitised on the server. The browser
  never renders HTML that came from outside the shop.
- Every outgoing message is sanitised on the server against an allowlist,
  whatever the browser sent.
- Attachment ceiling is Gmail's: 25MB total per message.

## Components

### composer.js (new, browser)

Served as `/assets/composer.js` by a route that mirrors `/assets/app.js`:
content-hashed URL, same session gate, same cache headers. The page loads it
after `app.js`. The security policy (`script-src 'self'`) is unchanged.

Interface:

    const c = mountComposer(host, { html, onChange, attachments });
    c.getHtml()            -> sanitised-on-the-client HTML string
    c.setHtml(html)
    c.insertText(text)     -> at the caret, as paragraphs (saved replies)
    c.attachments()        -> [{key, name, size, type, inline: bool}]
    c.focus()

Toolbar, in one row that wraps to two on narrow screens: bold, italic,
underline | font (Arial, Georgia, Verdana, Trebuchet MS, Courier New) |
size (small, normal, large, huge) | colour (eight swatches plus default) |
align left, centre, right | bullets, numbers | link | image | attach |
quote | clear formatting. Shortcuts Ctrl/Cmd+B, I, U, K. Commands run
through `document.execCommand`; the output is normalised by a client
cleaner that applies the SAME allowlist as the server (a paste from Word or
a web page is cleaned on the way in). The client cleaner is a convenience;
the server one is the guarantee.

Attachments: a chip per file (name, size, remove), and a meter reading
"x of 25MB". Files from the computer upload directly to the bucket by the
existing presigned PUT flow into the `mail/` prefix; "From Files" opens the
existing Files picker and references the file's key. An inline image is the
same upload; the editor shows it from a short-lived signed GET URL of our
own bucket and marks the element `data-key`, which the server rewrites to a
content-id part.

Mounted in exactly three places: Compose (new message), the reply panel
opened by Write a reply, and the reply panel opened by Claude's draft.

### mailmime.py (new, server)

Pure functions, no network:

    sanitize_html(html) -> str
    html_to_text(html) -> str
    render_footer(slots, logo_cid) -> (html, text)
    quote_original(msg) -> (html, text)      # "On <date>, <name> wrote:" + blockquote
    build_message(*, frm, to, cc, bcc, subject, html, text, inline, files,
                  in_reply_to, references) -> bytes   # RFC 5322, ready for base64url

Sanitiser allowlist: p, br, div, span, b, strong, i, em, u, a, ul, ol, li,
h1, h2, h3, blockquote, font, img, table, tr, td (the last three only for the
footer). Attributes: `href` on a (https: or mailto: only), `src` on img
(`cid:` only), `alt`, `width` and `height` on img, `style` restricted to
font-family, font-size, color, text-align. Anything else is removed, never
repaired. Scripts, event handlers, `javascript:` and data URLs cannot
survive it. The plain-text twin is generated from the clean HTML.

MIME shape: multipart/mixed( multipart/related( multipart/alternative(
text/plain, text/html ), inline images ), attachments ). Parts are omitted
when empty, so a plain reply is still a small multipart/alternative.

### google_mail.py

`send_message` and `create_draft` accept the built bytes and use a new
`_upload_call` against Gmail's upload endpoint
(`/upload/gmail/v1/users/me/messages/send?uploadType=multipart`, and the
drafts equivalent), which accepts up to 35MB. The landed-thread check and
the honest "sent but could not attach to this conversation" sentence stay.

### copilot.py

- `/api/mail/send` and `/api/mail/draft op:save` take `html` (and keep
  accepting `text` for the dry run and for older callers), `cc`, `bcc`,
  `attachments: [{key}]`, `inline: [{key, id}]`, `quote: bool`. The dry run
  validates everything including that every attachment key exists in the
  bucket and the total is under 25MB, and returns recipient, cc count and
  attachment count for the confirm row.
- Before assembling, every attachment size is re-read by HEAD. Any missing
  or oversized file refuses the whole send; a message never goes out with a
  file silently dropped.
- The store stamp (`send_pending` / `outbound_pending`) is written before
  Gmail is asked, as today, and now records attachment names and sizes.
- `/api/mail/settings` gains `op: "footer_slots"` (lead-only) and the logo
  upload uses the presign flow into `mail/footer/`. The old free-text
  `footer` migrates into the `legal` slot on first load.
- Reply all: `/api/mail/thread` exposes the original's recipients so the
  browser can fill CC minus the mailbox.
- The 30-day sweep of the `mail/` prefix runs with the existing Files
  housekeeping and never touches `mail/footer/`.

## Data

Mail store `email` block becomes
`{footer_slots: {logo_key, company, address, phone, website, legal},
  saved_replies: [...]}`. Threads gain `sent_attachments: [{name, size}]`.
Users keep `sign_off` as plain text.

## Security

- Server sanitiser is the guarantee; tests carry a vector set (script tags,
  event handlers, javascript: and data: links, remote image beacons, style
  escapes, nested quoting, SVG). A vector that survives is a failing test.
- Inline images and the logo are content-id parts. No outgoing message
  references a remote image, so customers' clients never call home.
- Attachment keys are validated against the `mail/` and Files prefixes; a
  key outside them is refused.
- Nothing from an incoming email is rendered as HTML in the browser.

## Failure honesty

Sanitiser strips, never repairs. Missing or oversized attachment refuses the
send. Gmail failure after the stamp is reported as today. A logo that cannot
be fetched at send time drops to the text footer with a logged warning,
because the footer is decoration and the message is not.

## Testing

Server: sanitiser vector set; html_to_text readability; MIME nesting and
content-id resolution; 25MB cap and missing-file refusal (mutation-checked);
quote assembly from HTML and from text-only originals; footer rendering and
the free-text migration; dry run reports attachment count. Frontend guards:
toolbar commands and shortcuts exist, paste cleaning applies the allowlist,
the meter reflects sizes, CC/BCC fold, the quote switch, the composer is
mounted in exactly three places. Rig walk of Compose and Reply at 1600 and
375 with an attachment and an inline image.

## Rollout

One release, behind the existing send grant. The text footer migrates
automatically. The composer file is content-hashed, so no cache trouble.
