# Email Composer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compose and Reply in the Inbox produce Gmail-grade email: formatted HTML with a plain-text twin, attachments, inline images, a slotted footer with the logo, CC/BCC and the quoted original, all sanitised on the server and sent through Gmail's upload endpoint.

**Architecture:** A zero-dependency `contenteditable` editor in `static/composer.js` (served by its own hash-versioned route) produces HTML; `mailmime.py` sanitises it, derives the text twin, renders the footer and the quote, and assembles the MIME tree; `google_mail.py` gains a multipart upload call; `copilot.py`'s send and draft routes take the richer payload, fetch attachment bytes from the bucket, refuse anything missing or oversized, and keep the durable-stamp-before-Gmail rule.

**Tech Stack:** Python 3.12 stdlib (`html.parser`, `email.message`), httpx, boto3 (existing R2 client), vanilla JS.

**Spec:** `docs/superpowers/specs/2026-09-02-email-composer-design.md`

## Global Constraints

- No em dashes and no en dashes in `static/index.html` or `static/composer.js` (CI fails the build).
- Single-writer stores: load, mutate, write, no `await` between. Durable write BEFORE any external call.
- A failed or partial operation never presents as success. Sanitiser strips, never repairs. A missing or oversized attachment refuses the whole send.
- Attachment ceiling 25MB total per message (`MAIL_ATTACH_MAX = 25 * 1024 * 1024`). Inline image ceiling 5MB each.
- Modals close via X only. Nothing from an incoming email is rendered as HTML in the browser.
- New dependencies: none. Scripts load only from gizmo itself (`script-src 'self'`).
- Tests are functions named `t_...` decorated `@test` in `tests/test_dispatch.py` (server) and `tests/test_frontend.py` (browser source guards), run with `.venv/bin/python tests/test_dispatch.py` and `python3 tests/test_frontend.py`. Assertion helpers are `eq(a, b, msg)` and `ok(x, msg)`. Mail fixtures: `ensure_auth()`, `ready_user(name, username) -> (uid, sess, pw)`, `_gm.save_connection("rt-test", MBOX)`, `_seed_thread(tid, subject=...)`, `post(path, body)` (master session), `post_s(sess, path, body)`, `with_mail(go)`. Files fixtures: `FakeS3` and `with_files(go, s3=None)`.
- Commit after every task with a short human title in the repo's voice; never commit a red suite.

---

### Task 1: mailmime.sanitize_html and html_to_text

**Files:**
- Create: `mailmime.py`
- Test: `tests/test_dispatch.py` (append near the mail tests)

**Interfaces:**
- Produces: `sanitize_html(html: str, footer: bool = False) -> str`; `html_to_text(html: str) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
@test
def t_the_sanitiser_strips_every_known_injection_and_keeps_formatting():
    import mailmime
    keep = '<p>Hi <b>Jo</b>, <i>thanks</i> <u>again</u>.</p><ul><li>one</li></ul>' \
           '<a href="https://example.com/x">site</a> <span style="color:#b91c1c">red</span>'
    eq(mailmime.sanitize_html(keep), keep, "allowed markup passes through untouched")
    vectors = [
        '<script>alert(1)</script>', '<img src="https://evil.co/a.png">',
        '<a href="javascript:alert(1)">x</a>', '<p onclick="alert(1)">x</p>',
        '<img src="data:image/png;base64,AAAA">', '<svg onload="alert(1)"></svg>',
        '<span style="background:url(//evil.co/a)">x</span>', '<iframe src="https://x"></iframe>',
        '<style>p{color:red}</style>', '<a href="HTTPS://ok.com" onmouseover="x">ok</a>',
    ]
    for v in vectors:
        out = mailmime.sanitize_html(v)
        for bad in ("script", "onclick", "onload", "onmouseover", "javascript:", "evil.co",
                    "data:", "iframe", "<style", "url("):
            ok(bad not in out, f"{bad!r} survived in {out!r} from {v!r}")
    eq(mailmime.sanitize_html('<a href="HTTPS://ok.com" onmouseover="x">ok</a>'),
       '<a href="https://ok.com">ok</a>', "a good link keeps its href and loses the handler")
    eq(mailmime.sanitize_html('<img src="cid:logo1" alt="logo" width="120">'),
       '<img src="cid:logo1" alt="logo" width="120">', "content-id images are the only images")
    ok("<table" not in mailmime.sanitize_html("<table><tr><td>x</td></tr></table>"),
       "tables are not for customer bodies")
    ok("<table" in mailmime.sanitize_html("<table><tr><td>x</td></tr></table>", footer=True),
       "but the footer renderer may use them")

@test
def t_the_text_twin_reads_like_the_email():
    import mailmime
    html = '<p>Hi Jo,</p><p>Two things:</p><ul><li>artwork</li><li>sizes</li></ul>' \
           '<p>See <a href="https://example.com/x">the guide</a>.</p><br>Thanks'
    eq(mailmime.html_to_text(html),
       "Hi Jo,\n\nTwo things:\n\n- artwork\n- sizes\n\nSee the guide (https://example.com/x).\n\nThanks")
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python tests/test_dispatch.py 2>&1 | grep -E "FAIL|passed"`
Expected: both FAIL with `ModuleNotFoundError: mailmime` (create an empty `mailmime.py` and re-run so they fail on the assertion, not the import).

- [ ] **Step 3: Implement**

```python
"""Everything that turns what the composer produced into what leaves the shop.

Pure: no network, no store. The sanitiser is the guarantee behind every
outgoing message; the browser's cleaner is only a courtesy to the person
typing. It strips and never repairs: a tag it does not know is gone, an
attribute it does not allow is gone, and the message is whatever is left.
"""
import re
from html import escape
from html.parser import HTMLParser

_TAGS = {"p", "br", "div", "span", "b", "strong", "i", "em", "u", "a", "ul", "ol", "li",
         "h1", "h2", "h3", "blockquote", "font"}
_FOOTER_TAGS = {"table", "tr", "td"}
_VOID = {"br", "img"}
_STYLE_OK = ("font-family", "font-size", "color", "text-align")
_STYLE_VAL = re.compile(r"^[a-zA-Z0-9 ,#%.'\"-]+$")   # no url(), no expression(), no escapes


def _clean_style(value: str) -> str:
    keep = []
    for decl in (value or "").split(";"):
        if ":" not in decl:
            continue
        k, v = decl.split(":", 1)
        k, v = k.strip().lower(), v.strip()
        if k in _STYLE_OK and _STYLE_VAL.match(v) and "url" not in v.lower():
            keep.append(f"{k}:{v}")
    return ";".join(keep)


class _Sanitiser(HTMLParser):
    def __init__(self, footer: bool):
        super().__init__(convert_charrefs=True)
        self.allowed = _TAGS | (_FOOTER_TAGS if footer else set()) | {"img"}
        self.out, self.skip = [], 0        # skip counts open tags of dropped subtrees

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "iframe", "object", "embed", "svg", "math", "template"):
            self.skip += 1
            return
        if self.skip or tag not in self.allowed:
            return
        keep = []
        for k, v in attrs:
            k, v = k.lower(), (v or "")
            if k == "href" and tag == "a":
                low = v.strip().lower()
                if low.startswith("https://") or low.startswith("mailto:"):
                    keep.append(("href", v.strip()[:2000].replace('"', "%22")))
            elif k == "src" and tag == "img":
                if v.strip().lower().startswith("cid:") and re.match(r"^cid:[A-Za-z0-9._@-]+$", v.strip()):
                    keep.append(("src", v.strip()))
            elif k in ("alt",) and tag == "img":
                keep.append((k, v[:200]))
            elif k in ("width", "height") and tag == "img" and v.isdigit():
                keep.append((k, v))
            elif k == "style":
                cs = _clean_style(v)
                if cs:
                    keep.append(("style", cs))
            elif k in ("color", "face", "size") and tag == "font" and _STYLE_VAL.match(v):
                keep.append((k, v))
        if tag == "img" and not any(k == "src" for k, _ in keep):
            return                          # an image with no cid source is nothing
        attr = "".join(f' {k}="{escape(v, quote=True)}"' for k, v in keep)
        self.out.append(f"<{tag}{attr}>")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "iframe", "object", "embed", "svg", "math", "template"):
            self.skip = max(0, self.skip - 1)
            return
        if self.skip or tag not in self.allowed or tag in _VOID:
            return
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(escape(data, quote=False))


def sanitize_html(html: str, footer: bool = False) -> str:
    p = _Sanitiser(footer)
    p.feed(str(html or ""))
    p.close()
    return "".join(p.out)


def html_to_text(html: str) -> str:
    """A readable twin for text-only clients, from the CLEAN html."""
    s = sanitize_html(html)
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"<li>", "- ", s)
    s = re.sub(r"</li>", "\n", s)
    s = re.sub(r"</(p|div|h1|h2|h3|blockquote|ul|ol)>", "\n\n", s)
    s = re.sub(r'<a href="([^"]+)">(.*?)</a>', lambda m: f"{m.group(2)} ({m.group(1)})", s)
    s = re.sub(r"<[^>]+>", "", s)
    from html import unescape
    s = unescape(s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()
```

- [ ] **Step 4: Run to verify they pass** (`.venv/bin/python tests/test_dispatch.py 2>&1 | tail -1`, expect the count up by 2, 0 failed)

- [ ] **Step 5: Mutation check** the sanitiser: back up, allow `onclick` through, run, confirm the vector test fails, restore, `diff -q`.

- [ ] **Step 6: Commit** `git add mailmime.py tests/test_dispatch.py && git commit -m "What leaves the shop is what the sanitiser allows"`

---

### Task 2: mailmime.build_message

**Files:**
- Modify: `mailmime.py`
- Test: `tests/test_dispatch.py`

**Interfaces:**
- Produces: `build_message(*, frm: str, to: str, subject: str, html: str, text: str, cc: str = "", bcc: str = "", inline: list = (), files: list = (), in_reply_to: str = "", references: str = "", reply: bool = True) -> bytes`. `inline` items: `{"cid": str, "name": str, "type": "image/png", "data": bytes}`; `files` items: `{"name": str, "type": str, "data": bytes}`. Subject gets `Re: ` when `reply` and it lacks one. Bcc is a header on the built bytes (Gmail strips it on send).

- [ ] **Step 1: Write the failing test**

```python
@test
def t_the_message_is_a_proper_mime_tree_with_a_text_twin_and_cids():
    import mailmime
    from email import message_from_bytes
    raw = mailmime.build_message(
        frm="sales@shop.test", to="jo@customer.test", cc="pat@customer.test", subject="Your gobos",
        html='<p>Hi <b>Jo</b></p><img src="cid:img1" alt="proof">', text="Hi Jo\n[image: proof]",
        inline=[{"cid": "img1", "name": "proof.png", "type": "image/png", "data": b"\x89PNG..."}],
        files=[{"name": "quote.pdf", "type": "application/pdf", "data": b"%PDF-1.4"}],
        in_reply_to="<abc@mail>", references="<zzz@mail>")
    m = message_from_bytes(raw)
    eq(m["Subject"], "Re: Your gobos"); eq(m["Cc"], "pat@customer.test")
    eq(m["In-Reply-To"], "<abc@mail>"); eq(m["References"], "<zzz@mail> <abc@mail>")
    eq(m.get_content_type(), "multipart/mixed")
    related, pdf = m.get_payload()
    eq(related.get_content_type(), "multipart/related")
    alt, img = related.get_payload()
    eq(alt.get_content_type(), "multipart/alternative")
    plain, htmlpart = alt.get_payload()
    eq(plain.get_content_type(), "text/plain"); eq(htmlpart.get_content_type(), "text/html")
    ok("Hi Jo" in plain.get_content(), "the text twin is the first alternative")
    eq(img["Content-ID"], "<img1>"); eq(img.get_content_disposition(), "inline")
    eq(pdf.get_filename(), "quote.pdf"); eq(pdf.get_content_disposition(), "attachment")
    plain_only = message_from_bytes(mailmime.build_message(
        frm="sales@shop.test", to="jo@customer.test", subject="Re: x", html="<p>hi</p>", text="hi", reply=False))
    eq(plain_only.get_content_type(), "multipart/alternative", "no attachments, no outer wrappers")
    eq(plain_only["Subject"], "Re: x", "reply=False adds nothing and strips nothing")
```

- [ ] **Step 2: Run to verify it fails** (AttributeError: build_message; stub `def build_message(**k): return b""` so it fails on the assertion).

- [ ] **Step 3: Implement**

```python
def build_message(*, frm, to, subject, html, text, cc="", bcc="", inline=(), files=(),
                  in_reply_to="", references="", reply=True) -> bytes:
    """The RFC 5322 bytes, with the alternative/related/mixed nesting that every
    client reads the same way. Headers are cleaned of line breaks: each value
    came from data the sender ultimately controls."""
    from email.message import EmailMessage
    clean = lambda v: " ".join(str(v or "").split())[:998]
    msg = EmailMessage()
    if frm:
        msg["From"] = clean(frm)
    msg["To"] = clean(to)
    if cc:
        msg["Cc"] = clean(cc)
    if bcc:
        msg["Bcc"] = clean(bcc)
    s = clean(subject)
    if reply:
        s = s if s[:3].lower() == "re:" else ("Re: " + s if s else "Re:")
    msg["Subject"] = s
    if in_reply_to:
        irt = clean(in_reply_to)
        msg["In-Reply-To"] = irt
        refs = clean(references).split()
        if irt not in refs:
            refs.append(irt)
        msg["References"] = " ".join(refs)
    msg.set_content(text or "")
    msg.add_alternative(html or "", subtype="html")
    if inline:
        htmlpart = msg.get_payload()[-1]
        for im in inline:
            maintype, subtype = (im.get("type") or "application/octet-stream").split("/", 1)
            htmlpart.add_related(im["data"], maintype=maintype, subtype=subtype,
                                 cid=f"<{im['cid']}>", filename=clean(im.get("name")),
                                 disposition="inline")
    for f in files:
        maintype, subtype = (f.get("type") or "application/octet-stream").split("/", 1)
        msg.add_attachment(f["data"], maintype=maintype, subtype=subtype, filename=clean(f.get("name")))
    return msg.as_bytes()
```

Note: `EmailMessage.add_related` on the html part turns the alternative's html leaf into multipart/related; `add_attachment` on the top turns it into multipart/mixed. Verify the nesting the test asserts; if the stdlib nests related OUTSIDE alternative (it does when you call `add_related` on the top-level message), the code above calling it on the html part is what keeps the spec's shape.

- [ ] **Step 4: Run to verify it passes**
- [ ] **Step 5: Commit** `git commit -am "One MIME shape every client reads the same way"`

---

### Task 3: mailmime.render_footer and quote_original

**Files:**
- Modify: `mailmime.py`
- Test: `tests/test_dispatch.py`

**Interfaces:**
- Produces: `render_footer(slots: dict, logo_cid: str = "") -> tuple[str, str]` (html, text); slots keys `company, address, phone, website, legal`, all strings. `quote_original(msg: dict) -> tuple[str, str]` where `msg` has `from_name, from_email, at (iso), html, text`.

- [ ] **Step 1: Write the failing tests**

```python
@test
def t_the_footer_renders_its_slots_and_nothing_else():
    import mailmime
    html, text = mailmime.render_footer(
        {"company": "Projected Image UK Ltd", "address": "Unit 4, Bristol", "phone": "0117 000 0000",
         "website": "https://projectedimage.co.uk", "legal": "Registered in England 01234567"},
        logo_cid="logo1")
    ok('<img src="cid:logo1"' in html and "<table" in html, "logo by cid, in an email-safe table")
    ok('href="https://projectedimage.co.uk"' in html)
    ok("<script" not in mailmime.render_footer({"company": "<script>x</script>"})[0])
    eq(text, "Projected Image UK Ltd\nUnit 4, Bristol\n0117 000 0000\nhttps://projectedimage.co.uk\n"
             "Registered in England 01234567")
    eq(mailmime.render_footer({}), ("", ""), "no slots, no footer")

@test
def t_the_quoted_original_carries_its_formatting_and_a_header_line():
    import mailmime
    html, text = mailmime.quote_original({
        "from_name": "Sarah Parker", "from_email": "sarah@northlight.test",
        "at": "2026-09-02T09:15:00+00:00",
        "html": '<p>Can you <b>rush</b> it?</p><script>x</script>', "text": "Can you rush it?"})
    ok(html.startswith('<div class="gizmo-quote"><p>On 2 Sep 2026, Sarah Parker &lt;sarah@northlight.test&gt; wrote:</p><blockquote'))
    ok("<b>rush</b>" in html and "<script" not in html)
    eq(text, "On 2 Sep 2026, Sarah Parker <sarah@northlight.test> wrote:\n> Can you rush it?")
    h2, t2 = mailmime.quote_original({"from_name": "", "from_email": "x@y.test", "at": "", "html": "", "text": "plain only"})
    ok("<blockquote>plain only</blockquote>" in h2 and "x@y.test wrote:" in h2, "text-only originals quote as text")
```

- [ ] **Step 2: Run to verify they fail** (stub both to return `("", "")`).

- [ ] **Step 3: Implement**

```python
def render_footer(slots: dict, logo_cid: str = "") -> tuple:
    from html import escape
    s = {k: " ".join(str((slots or {}).get(k) or "").split()) for k in
         ("company", "address", "phone", "website", "legal")}
    lines = [v for v in (s["company"], s["address"], s["phone"], s["website"], s["legal"]) if v]
    if not lines and not logo_cid:
        return "", ""
    cells = []
    if logo_cid:
        cells.append(f'<td style="padding:0 12px 0 0"><img src="cid:{escape(logo_cid, True)}" alt="{escape(s["company"], True)}" width="120"></td>')
    body = []
    if s["company"]:
        body.append(f'<b>{escape(s["company"])}</b>')
    for k in ("address", "phone"):
        if s[k]:
            body.append(escape(s[k]))
    if s["website"]:
        w = s["website"] if s["website"].lower().startswith("https://") else "https://" + s["website"]
        body.append(f'<a href="{escape(w, True)}">{escape(s["website"])}</a>')
    if s["legal"]:
        body.append(f'<span style="color:#696969">{escape(s["legal"])}</span>')
    cells.append('<td style="font-family:Arial,sans-serif;font-size:13px;color:#0a0a0a">' + "<br>".join(body) + "</td>")
    html = '<table role="presentation" style="border-collapse:collapse;margin-top:16px"><tr>' + "".join(cells) + "</tr></table>"
    return sanitize_html(html, footer=True), "\n".join(lines)


def quote_original(msg: dict) -> tuple:
    from html import escape
    from datetime import datetime
    name = " ".join(str(msg.get("from_name") or "").split())
    addr = " ".join(str(msg.get("from_email") or "").split())
    who = f"{name} <{addr}>" if name else addr
    when = ""
    try:
        when = datetime.fromisoformat(str(msg.get("at") or "").replace("Z", "+00:00")).strftime("%-d %b %Y")
    except ValueError:
        pass
    head = f"On {when}, {who} wrote:" if when else f"{who} wrote:"
    inner = sanitize_html(msg.get("html") or "") if (msg.get("html") or "").strip() else escape(msg.get("text") or "").replace("\n", "<br>")
    html = f'<div class="gizmo-quote"><p>{escape(head)}</p><blockquote>{inner}</blockquote></div>'
    text = head + "\n" + "\n".join("> " + ln for ln in (msg.get("text") or html_to_text(msg.get("html") or "")).splitlines())
    return html, text
```

- [ ] **Step 4: Run to verify they pass**
- [ ] **Step 5: Commit** `git commit -am "The footer from its slots, the original quoted safely"`

---

### Task 4: google_mail upload call, raw bytes on send and draft, html on read_thread

**Files:**
- Modify: `google_mail.py` (`read_thread` ~534, `create_draft` ~627, `send_message` ~651)
- Test: `tests/test_dispatch.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `read_thread(...)` messages gain `"html": str` (the message's text/html part, capped at 200000 chars, "" when none). `send_message(..., raw_bytes: bytes = None)` and `create_draft(..., raw_bytes: bytes = None)`: when `raw_bytes` is given, the message is posted through `_upload_call(path, meta, raw_bytes, acct)`; the return shapes are unchanged. Module-level `_upload_post` is the injectable network leg: `async _upload_post(url, headers, body) -> (status, json)`.

- [ ] **Step 1: Write the failing tests**

```python
@test
def t_a_built_message_goes_through_gmails_upload_door_with_its_thread():
    captured = {}
    async def fake_post(url, headers, body):
        captured.update(url=url, headers=headers, body=body)
        return 200, {"id": "m9", "threadId": "t1"}
    async def fake_token(acct=None):
        return "tok"
    saved = (_gm._upload_post, _gm._token)
    _gm._upload_post, _gm._token = fake_post, fake_token
    try:
        out = _run(_gm.send_message("t1", "jo@c.test", "Hi", "", raw_bytes=b"From: a\r\n\r\nbody"))
        eq(out, {"id": "m9", "thread_id": "t1"})
        ok(captured["url"].endswith("/upload/gmail/v1/users/me/messages/send?uploadType=multipart"))
        ok(captured["headers"]["Content-Type"].startswith("multipart/related; boundary="))
        ok(b'{"threadId": "t1"}' in captured["body"] and b"message/rfc822" in captured["body"]
           and b"From: a\r\n\r\nbody" in captured["body"], "metadata then the raw message")
        _run(_gm.send_message("", "jo@c.test", "Hi", "", raw_bytes=b"x", new=True))
        ok(b"threadId" not in captured["body"], "a new message names no thread")
        _run(_gm.create_draft("t1", "jo@c.test", "Hi", "", raw_bytes=b"x"))
        ok(captured["url"].endswith("/upload/gmail/v1/users/me/drafts?uploadType=multipart"))
        ok(b'{"message": {"threadId": "t1"}}' in captured["body"], "a draft wraps the thread in message")
    finally:
        _gm._upload_post, _gm._token = saved

@test
def t_read_thread_keeps_the_html_of_a_message_for_quoting():
    async def fake_get(tid, acct=None):
        return {"id": tid, "messages": [{"id": "m1", "payload": {"headers": [
            {"name": "From", "value": "Jo <jo@c.test>"}, {"name": "Subject", "value": "x"}],
            "mimeType": "text/html", "body": {"data": _b64url("<p>Hi <b>there</b></p>")}},
            "internalDate": "1756800000000"}]}
    saved = _gm.get_thread; _gm.get_thread = fake_get
    try:
        msgs = _run(_gm.read_thread("t1"))["messages"]
        eq(msgs[0]["html"], "<p>Hi <b>there</b></p>")
        eq(msgs[0]["text"], "Hi there")
    finally:
        _gm.get_thread = saved
```

`_run` is the suite's asyncio runner and `_b64url` its base64url helper; both exist near the other Gmail tests (grep `def _run(` and `def _b64url(`; add `_b64url` if absent: `base64.urlsafe_b64encode(s.encode()).decode()`).

- [ ] **Step 2: Run to verify they fail**

- [ ] **Step 3: Implement**

```python
async def _upload_post(url: str, headers: dict, body: bytes):
    async with httpx.AsyncClient(timeout=120.0) as c:
        r = await c.post(url, headers=headers, content=body)
    try:
        data = r.json()
    except Exception:
        data = {"error": {"message": r.text[:300]}}
    return r.status_code, data


async def _upload_call(path: str, meta: dict, raw: bytes, acct: Account = SALES) -> dict:
    """Gmail's upload door: a multipart/related body carrying the JSON metadata
    (thread) and the raw RFC 822 message. It takes messages up to 35MB where
    the JSON door stops well short of that."""
    import json as _json, secrets
    token = await _token(acct)
    boundary = "gizmo" + secrets.token_hex(12)
    body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{_json.dumps(meta)}\r\n--{boundary}\r\nContent-Type: message/rfc822\r\n\r\n").encode() \
           + raw + f"\r\n--{boundary}--".encode()
    url = f"{API_BASE}/upload/gmail/v1/users/me/{path}?uploadType=multipart"
    status, data = await _upload_post(url, {"Authorization": f"Bearer {token}",
                                            "Content-Type": f"multipart/related; boundary={boundary}"}, body)
    if status >= 400:
        raise GmailError(str(((data or {}).get("error") or {}).get("message") or f"HTTP {status}"))
    return data or {}
```

In `send_message`, before the existing JSON post: `if raw_bytes is not None: meta = {} if new else {"threadId": thread_id}; out = await _upload_call("messages/send", meta, raw_bytes); landed = ...` then the SAME landed-thread check and return shape as the JSON path. In `create_draft`: `meta = {"message": ({"threadId": thread_id} if thread_id else {})}; out = await _upload_call("drafts", meta, raw_bytes)`; keep the landed check and `replaces` handling. In `read_thread`, alongside `"text"`, add `"html": (found.get("html") or "")[:200000]` (`found` is the dict `_walk_body` fills; read the function and place it where `text` is computed).

- [ ] **Step 4: Run to verify they pass**
- [ ] **Step 5: Commit** `git commit -am "Gmail's upload door, and the html kept for quoting"`

---

### Task 5: Footer slots, migration, logo upload

**Files:**
- Modify: `copilot.py` (`_mail_default` ~9442, the load migration beside the existing `email` block, `_mail_email_block`, `/api/mail/settings` route)
- Test: `tests/test_dispatch.py`

**Interfaces:**
- Produces: mail store `email` block is `{"footer_slots": {"logo_key", "company", "address", "phone", "website", "legal"}, "saved_replies": [...]}`; the old `footer` string migrates into `legal` on load and the key is dropped. `/api/mail/settings {op: "footer_slots", slots: {...}}` lead-only, each slot capped 200 chars, `website` must be empty or start with `https://` or be a bare domain. `/api/mail/settings {op: "logo_url", name, size, type}` lead-only, returns `{url, key}` for a presigned PUT into `mail/footer/logo-<hex>.<ext>` (png, jpg, gif, webp only, size <= 1MB) and `{op: "logo_done", key}` verifies by HEAD and stores `logo_key`. `_mail_email_block(store, uid)` now returns `{"footer_slots", "footer_html", "footer_text", "sign_off", "saved_replies"}` where `footer_html`/`footer_text` come from `mailmime.render_footer(slots, "logo" if logo_key else "")` (preview only; the logo shows as `cid:logo`, which the browser preview replaces with a signed GET URL it fetches via `{op: "logo_view"}` -> `{url}`).

- [ ] **Step 1: Write the failing tests**

```python
@test
def t_the_old_footer_moves_into_the_legal_slot_and_leads_edit_the_slots():
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        st = copilot._load_mail(); st["email"] = {"footer": "Reg 01234567", "saved_replies": []}
        copilot._write_mail(st)
        j = post("/api/mail/board", {}).json()
        eq(j["email"]["footer_slots"]["legal"], "Reg 01234567", "the free-text footer is not lost")
        ok("footer" not in copilot._load_mail()["email"], "and the old key is gone")
        r = post("/api/mail/settings", {"op": "footer_slots", "slots": {"company": "PI Ltd", "website": "projectedimage.co.uk", "phone": "x" * 300}})
        eq(r.status_code, 400, "a slot over 200 chars is refused, not truncated silently")
        r = post("/api/mail/settings", {"op": "footer_slots", "slots": {"company": "PI Ltd", "website": "projectedimage.co.uk"}})
        eq(r.status_code, 200)
        j = post("/api/mail/board", {}).json()["email"]
        eq(j["footer_slots"]["company"], "PI Ltd")
        ok("<b>PI Ltd</b>" in j["footer_html"] and "PI Ltd" in j["footer_text"], "the board carries the rendered preview")
        _uid, sess, _ = ready_user("Ann", "ann")
        eq(post_s(sess, "/api/mail/settings", {"op": "footer_slots", "slots": {"company": "x"}}).status_code, 403)
    with_mail(go)

@test
def t_the_logo_lands_in_its_own_prefix_and_only_as_an_image():
    def go():
        ensure_auth(); _gm.save_connection("rt-test", MBOX)
        r = post("/api/mail/settings", {"op": "logo_url", "name": "logo.exe", "size": 1000, "type": "application/x-msdownload"})
        eq(r.status_code, 400)
        r = post("/api/mail/settings", {"op": "logo_url", "name": "logo.png", "size": 2 * 1024 * 1024, "type": "image/png"})
        eq(r.status_code, 400, "over 1MB is not a logo")
        r = post("/api/mail/settings", {"op": "logo_url", "name": "logo.png", "size": 40000, "type": "image/png"})
        eq(r.status_code, 200, r.text); key = r.json()["key"]
        ok(key.startswith("mail/footer/logo-") and key.endswith(".png"))
        s3.objects[key] = b"x" * 40000
        eq(post("/api/mail/settings", {"op": "logo_done", "key": key}).status_code, 200)
        eq(copilot._load_mail()["email"]["footer_slots"]["logo_key"], key)
        eq(post("/api/mail/settings", {"op": "logo_done", "key": "files/other.png"}).status_code, 400, "keys outside the footer prefix are refused")
    s3 = FakeS3(); s3.bucket_exists = True
    with_files(lambda: with_mail(go), s3=s3)
```

- [ ] **Step 2: Run to verify they fail**

- [ ] **Step 3: Implement** in `copilot.py`: change `_mail_default` to `"email": {"footer_slots": {"logo_key": "", "company": "", "address": "", "phone": "", "website": "", "legal": ""}, "saved_replies": []}`; in the load-time migration block (where `em = _mail_mem.get("email")` runs) add:

```python
        if "footer" in em:
            # The free-text footer became slots. Its text was mostly the legal
            # line, so that is where it lands; a lead can move it in a minute.
            slots = em.setdefault("footer_slots", {})
            slots.setdefault("legal", str(em.pop("footer") or "")[:200])
        em.setdefault("footer_slots", {}).update({k: em["footer_slots"].get(k, "") for k in
                                                 ("logo_key", "company", "address", "phone", "website", "legal")})
```

`_mail_email_block`:

```python
def _mail_email_block(store: dict, uid) -> dict:
    em = store.get("email") or {}
    slots = em.get("footer_slots") or {}
    html, text = mailmime.render_footer(slots, "logo" if slots.get("logo_key") else "")
    return {"footer_slots": {k: slots.get(k, "") for k in ("logo_key", "company", "address", "phone", "website", "legal")},
            "footer_html": html, "footer_text": text, "sign_off": _mail_sign_off(uid),
            "saved_replies": list(em.get("saved_replies") or [])}
```

Settings route ops (lead-only, after the existing `op == "footer"` which is REMOVED):

```python
        if op == "footer_slots":
            raw = body.get("slots") or {}
            if not isinstance(raw, dict):
                return _json({"error": "Slots must be an object."}, 400)
            slots = em.setdefault("footer_slots", {})
            for k in ("company", "address", "phone", "website", "legal"):
                if k in raw:
                    v = " ".join(str(raw.get(k) or "").split())
                    if len(v) > 200:
                        return _json({"error": f"The {k} line is over 200 characters."}, 400)
                    if k == "website" and v and not (v.lower().startswith("https://") or re.match(r"^[a-z0-9.-]+\.[a-z]{2,}(/.*)?$", v.lower())):
                        return _json({"error": "The website needs to be an https address or a plain domain."}, 400)
                    slots[k] = v
            _write_mail(store)
            return _json({"ok": True, "footer_slots": slots})
        if op == "logo_url":
            name = str(body.get("name") or "logo").strip()
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            ctype = str(body.get("type") or "")
            if ext not in ("png", "jpg", "jpeg", "gif", "webp") or not ctype.startswith("image/"):
                return _json({"error": "The logo has to be a PNG, JPG, GIF or WebP image."}, 400)
            size = int(body.get("size") or 0)
            if not 0 < size <= 1024 * 1024:
                return _json({"error": "The logo has to be under 1MB."}, 400)
            key = f"mail/footer/logo-{secrets.token_hex(8)}.{ext}"
            return _json({"url": _files_sign_put(key, ctype, size), "key": key})
        if op == "logo_done":
            key = str(body.get("key") or "")
            if not re.match(r"^mail/footer/logo-[0-9a-f]{16}\.(png|jpe?g|gif|webp)$", key):
                return _json({"error": "That is not a logo upload."}, 400)
            try:
                size = _files_head(key)
            except Exception:
                return _json({"error": "Storage did not answer; try again."}, 502)
            if not size or size > 1024 * 1024:
                return _json({"error": "The logo did not land, or is over 1MB."}, 400)
            em.setdefault("footer_slots", {})["logo_key"] = key
            _write_mail(store)
            return _json({"ok": True, "key": key})
        if op == "logo_view":
            key = (em.get("footer_slots") or {}).get("logo_key") or ""
            return _json({"url": _files_sign_get(key, "logo", inline=True) if key else ""})
```

Use the module's existing presign-PUT helper (grep `generate_presigned_url("put_object"` for its wrapper name; the plan calls it `_files_sign_put(key, ctype, size)`; if the real one has a different signature, adapt the two call sites, never the tests). Add `import mailmime` at the top of `copilot.py` beside `import eori`.

- [ ] **Step 4: Run to verify they pass** (the earlier footer tests `t_mail_board_carries_the_footer_and_the_callers_own_signoff` and any asserting `email.footer` must be updated to `footer_slots.legal` / `footer_text`; that is a mechanism change with the requirement intact, say so in the commit).
- [ ] **Step 5: Commit** `git commit -am "The footer becomes slots, with a logo"`

---

### Task 6: Attachments: presign into mail/, verify, cap, prefix rules, sweep

**Files:**
- Modify: `copilot.py`
- Test: `tests/test_dispatch.py`

**Interfaces:**
- Produces: constants `MAIL_ATTACH_MAX = 25 * 1024 * 1024`, `MAIL_INLINE_MAX = 5 * 1024 * 1024`. Routes: `POST /api/mail/attach-url {name, size, type, inline: bool}` (send grant required) -> `{url, key}` presigned PUT into `mail/<uid>/<hex>-<safe name>`; `POST /api/mail/attach-done {key}` -> `{ok, key, name, size, type}` after HEAD (refuses missing, refuses > MAIL_ATTACH_MAX, inline > MAIL_INLINE_MAX or non-image). Helper `_mail_attachment_ok(key: str, uid: str) -> bool` (key is under `mail/<uid>/` or is an active Files record's `r2_key`). Helper `async _mail_fetch_parts(keys: list, uid: str) -> (files, inline, total)` reading bytes via `_files_s3().get_object` and raising `ValueError(reason)` on any missing, disallowed or oversized part. `_mail_sweep_attachments()` deletes `mail/<uid>/` objects older than 30 days, never `mail/footer/`; call it from the existing Files housekeeping (grep the trash sweep, `_files_sweep` or similar) once a day.

- [ ] **Step 1: Write the failing tests**

```python
@test
def t_attachments_upload_into_the_mail_prefix_behind_the_grant_and_within_the_cap():
    def go():
        ensure_auth(); _gm.save_connection("rt-test", MBOX)
        uid, sess, _ = ready_user("Ann", "ann")
        eq(post_s(sess, "/api/mail/attach-url", {"name": "q.pdf", "size": 1000, "type": "application/pdf"}).status_code, 403)
        post("/api/team/user", {"op": "send", "id": uid, "can_send": True})
        r = post_s(sess, "/api/mail/attach-url", {"name": "../../q.pdf", "size": 1000, "type": "application/pdf"})
        eq(r.status_code, 200, r.text); key = r.json()["key"]
        ok(key.startswith(f"mail/{uid}/") and ".." not in key and key.endswith("-q.pdf"))
        eq(post_s(sess, "/api/mail/attach-url", {"name": "big.zip", "size": 26 * 1024 * 1024, "type": "application/zip"}).status_code, 400)
        eq(post_s(sess, "/api/mail/attach-url", {"name": "x.pdf", "size": 1000, "type": "application/pdf", "inline": True}).status_code, 400, "inline must be an image")
        s3.objects[key] = b"%PDF" + b"x" * 996
        r = post_s(sess, "/api/mail/attach-done", {"key": key})
        eq(r.status_code, 200); eq(r.json()["size"], 1000); eq(r.json()["name"], "q.pdf")
        eq(post_s(sess, "/api/mail/attach-done", {"key": key + ".nope"}).status_code, 400, "a key that never landed")
        eq(post_s(sess, "/api/mail/attach-done", {"key": "mail/u-other/abc-x.pdf"}).status_code, 400, "someone else's prefix")
    s3 = FakeS3(); s3.bucket_exists = True
    with_files(lambda: with_mail(go), s3=s3)

@test
def t_fetching_parts_refuses_the_whole_set_when_one_is_missing_or_too_big():
    def go():
        ensure_auth()
        uid, _sess, _ = ready_user("Ann", "ann")
        k1, k2 = f"mail/{uid}/aa-a.pdf", f"mail/{uid}/bb-b.png"
        s3.objects[k1] = b"%PDF"; s3.objects[k2] = b"\x89PNG"
        files, inline, total = _run(copilot._mail_fetch_parts([{"key": k1}], uid, inline_keys=[{"key": k2, "cid": "img1"}]))
        eq([f["name"] for f in files], ["a.pdf"]); eq(inline[0]["cid"], "img1"); eq(total, 8)
        try:
            _run(copilot._mail_fetch_parts([{"key": k1}, {"key": f"mail/{uid}/cc-gone.pdf"}], uid))
            ok(False, "a missing part must refuse the set")
        except ValueError as e:
            ok("gone.pdf" in str(e))
        s3.objects[f"mail/{uid}/dd-huge.bin"] = b"x" * (copilot.MAIL_ATTACH_MAX + 1)
        try:
            _run(copilot._mail_fetch_parts([{"key": f"mail/{uid}/dd-huge.bin"}], uid)); ok(False)
        except ValueError as e:
            ok("25MB" in str(e))
        try:
            _run(copilot._mail_fetch_parts([{"key": "files/other/x.pdf"}], uid)); ok(False)
        except ValueError as e:
            ok("not one of your" in str(e).lower() or "allowed" in str(e).lower())
    s3 = FakeS3(); s3.bucket_exists = True
    with_files(lambda: with_mail(go), s3=s3)
```

Add to `FakeS3` in the test file: `def get_object(self, Bucket, Key): self._guard("get_object"); import io; if Key not in self.objects: raise KeyError(Key); return {"Body": io.BytesIO(self.objects[Key]), "ContentLength": len(self.objects[Key])}` and make `head_object` answer from `self.objects` if it does not already.

- [ ] **Step 2: Run to verify they fail**
- [ ] **Step 3: Implement** the constants, the two routes (guard: `_mail_guard` then `_may_send_mail`), `_mail_attachment_ok`, `_mail_fetch_parts`:

```python
async def _mail_fetch_parts(files: list, uid: str, inline_keys: list = None):
    """Bytes for every part, or a ValueError naming the first part that cannot
    be sent. All or nothing: a message with a file quietly missing looks sent
    and is not what the person read before pressing Send."""
    out_files, out_inline, total = [], [], 0
    def _name(key): return key.rsplit("/", 1)[-1].split("-", 1)[-1] if "-" in key.rsplit("/", 1)[-1] else key.rsplit("/", 1)[-1]
    async def _read(key):
        if not _mail_attachment_ok(key, uid):
            raise ValueError(f"{_name(key)} is not one of your uploads.")
        try:
            obj = await asyncio.to_thread(_files_s3().get_object, Bucket=R2_BUCKET, Key=key)
            data = await asyncio.to_thread(obj["Body"].read)
        except Exception as e:
            raise ValueError(f"{_name(key)} is missing from storage.") from e
        return data
    for f in (files or []):
        key = str(f.get("key") or "")
        data = await _read(key)
        total += len(data)
        if total > MAIL_ATTACH_MAX:
            raise ValueError("Attachments come to more than 25MB in total.")
        out_files.append({"name": str(f.get("name") or _name(key))[:200], "type": str(f.get("type") or "application/octet-stream"), "data": data})
    for im in (inline_keys or []):
        key = str(im.get("key") or "")
        data = await _read(key)
        if len(data) > MAIL_INLINE_MAX:
            raise ValueError(f"{_name(key)} is over 5MB, too large for an inline image.")
        total += len(data)
        if total > MAIL_ATTACH_MAX:
            raise ValueError("Attachments come to more than 25MB in total.")
        out_inline.append({"cid": re.sub(r"[^A-Za-z0-9._-]", "", str(im.get("cid") or ""))[:64] or "img", "name": _name(key), "type": str(im.get("type") or "image/png"), "data": data})
    return out_files, out_inline, total
```

- [ ] **Step 4: Run to verify they pass**
- [ ] **Step 5: Mutation check:** make `_mail_fetch_parts` skip a missing key instead of raising; the refusal test must fail; restore.
- [ ] **Step 6: Commit** `git commit -am "Attachments: all of them or none of them"`

---

### Task 7: The send and draft routes take the richer message

**Files:**
- Modify: `copilot.py` (`/api/mail/send` ~13496+, `/api/mail/draft` op save ~13139+)
- Test: `tests/test_dispatch.py`

**Interfaces:**
- Consumes: Tasks 1 to 6.
- Produces: both routes accept `html` (string; when present it is the body and `text` is ignored except for the legacy plain path), `cc`, `bcc` (comma lists, validated like `to`, cc+bcc <= 10 addresses), `attachments: [{key, name, type}]`, `inline: [{key, cid, type}]`, `quote: bool` (reply only, default true). The dry run returns `{"ok", "dry", "to", "cc_count", "attachment_count", "kind"}`. The stamp (`send_pending` / `outbound_pending`) records `attachments: [{name, size}]`. Successful sends record `sent_attachments` on the thread. The final body is: sanitised html + sign-off (as `<p>` lines) + footer html, with the quoted original last for replies; the text twin mirrors it.

- [ ] **Step 1: Write the failing tests**

```python
@test
def t_a_rich_reply_goes_out_sanitised_with_its_twin_footer_and_quote():
    def go():
        ensure_auth(); _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1", subject="Rush job")
        uid, sess, _ = ready_user("Ann", "ann"); post("/api/team/user", {"op": "send", "id": uid, "can_send": True})
        post("/api/team/user", {"op": "sign_off", "id": uid, "text": "Ann\nSales desk"})
        post("/api/mail/settings", {"op": "footer_slots", "slots": {"company": "PI Ltd", "legal": "Reg 1"}})
        async def fake_read(tid, per_msg_chars=4000):
            return {"id": tid, "messages": [{"id": "m1", "from_name": "Jo", "from_email": "jo@c.test", "reply_to": "", "to": MBOX, "cc": "pat@c.test",
                     "subject": "Rush job", "message_id": "<abc@mail>", "references": "", "at": "2026-09-01T10:00:00+00:00",
                     "text": "Can you rush it?", "html": "<p>Can you <b>rush</b> it?</p>"}]}
        captured = {}
        async def fake_send(thread_id, to_addr, subject, body_text, in_reply_to="", references="", cc="", new=False, raw_bytes=None):
            captured.update(thread_id=thread_id, to=to_addr, raw=raw_bytes); return {"id": "m2", "thread_id": thread_id}
        saved = (_gm.read_thread, _gm.send_message); _gm.read_thread, _gm.send_message = fake_read, fake_send
        try:
            k = f"mail/{uid}/aa-quote.pdf"; s3.objects[k] = b"%PDF-1.4"
            body = {"id": "t1", "html": '<p>Hi <b>Jo</b></p><script>x</script>', "cc": "pat@c.test",
                    "attachments": [{"key": k, "name": "quote.pdf", "type": "application/pdf"}]}
            d = post_s(sess, "/api/mail/send", dict(body, dry=True)).json()
            eq(d["to"], "jo@c.test"); eq(d["cc_count"], 1); eq(d["attachment_count"], 1)
            ok("raw" not in captured, "a dry run sends nothing")
            r = post_s(sess, "/api/mail/send", body); eq(r.status_code, 200, r.text)
            from email import message_from_bytes
            m = message_from_bytes(captured["raw"])
            eq(m["Cc"], "pat@c.test"); eq(m["In-Reply-To"], "<abc@mail>")
            html = next(p for p in m.walk() if p.get_content_type() == "text/html").get_content()
            ok("<script" not in html and "<b>Jo</b>" in html)
            ok("Ann<br>Sales desk" in html or "<p>Ann<br>Sales desk</p>" in html, "sign-off as lines")
            ok("<b>PI Ltd</b>" in html and "Reg 1" in html, "footer slots rendered")
            ok('class="gizmo-quote"' in html and "<b>rush</b>" in html and html.index("PI Ltd") < html.index("gizmo-quote"), "quote last")
            text = next(p for p in m.walk() if p.get_content_type() == "text/plain").get_content()
            ok("Hi Jo" in text and "Ann\nSales desk" in text and "PI Ltd" in text and "> Can you rush it?" in text)
            eq([p.get_filename() for p in m.walk() if p.get_content_disposition() == "attachment"], ["quote.pdf"])
            t = copilot._load_mail()["threads"]["t1"]
            eq(t["sent_attachments"], [{"name": "quote.pdf", "size": 8}])
            r = post_s(sess, "/api/mail/send", dict(body, attachments=[{"key": f"mail/{uid}/zz-gone.pdf"}]))
            eq(r.status_code, 400); ok("gone.pdf" in r.json()["error"]); eq(t.get("send_pending"), None)
            r = post_s(sess, "/api/mail/send", dict(body, quote=False)); m = message_from_bytes(captured["raw"])
            ok("gizmo-quote" not in next(p for p in m.walk() if p.get_content_type() == "text/html").get_content())
        finally:
            _gm.read_thread, _gm.send_message = saved
    s3 = FakeS3(); s3.bucket_exists = True
    with_files(lambda: with_mail(go), s3=s3)

@test
def t_a_new_rich_message_and_a_draft_share_the_same_assembly():
    def go():
        ensure_auth(); _gm.save_connection("rt-test", MBOX)
        captured = {}
        async def fake_send(thread_id, to_addr, subject, body_text, in_reply_to="", references="", cc="", new=False, raw_bytes=None):
            captured["send"] = raw_bytes; return {"id": "m3", "thread_id": "t9"}
        async def fake_draft(thread_id, to_addr, subject, body_text, in_reply_to="", references="", cc="", replaces="", raw_bytes=None):
            captured["draft"] = raw_bytes; return {"id": "d1", "thread_id": thread_id}
        async def fake_get(tid, acct=None):
            return {"id": tid, "messages": []}
        saved = (_gm.send_message, _gm.create_draft, _gm.get_thread); _gm.send_message, _gm.create_draft, _gm.get_thread = fake_send, fake_draft, fake_get
        try:
            r = post("/api/mail/send", {"to": "jo@c.test", "bcc": "me@c.test", "subject": "Hello", "html": "<p><i>Hi</i></p>"})
            eq(r.status_code, 200, r.text)
            from email import message_from_bytes
            m = message_from_bytes(captured["send"]); eq(m["Subject"], "Hello"); eq(m["Bcc"], "me@c.test")
            _seed_thread("t1", subject="x")
            async def fake_read(tid, per_msg_chars=4000):
                return {"id": tid, "messages": [{"id": "m1", "from_name": "Jo", "from_email": "jo@c.test", "reply_to": "", "subject": "x", "message_id": "<a@m>", "references": "", "at": "", "text": "hi", "html": ""}]}
            _gm.read_thread = fake_read
            r = post("/api/mail/draft", {"id": "t1", "op": "save", "html": "<p>Draft <u>here</u></p>"})
            eq(r.status_code, 200, r.text)
            ok(b"<u>here</u>" in captured["draft"], "a draft carries the formatting too")
        finally:
            _gm.send_message, _gm.create_draft, _gm.get_thread = saved
    with_mail(go)
```

- [ ] **Step 2: Run to verify they fail**
- [ ] **Step 3: Implement.** Add a pure assembler in `copilot.py`:

```python
def _mail_compose_body(html: str, text: str, sign_off: str, footer_html: str, footer_text: str,
                       quote: tuple = None) -> tuple:
    """(html, text) of what leaves: the person's words, their sign-off, the shop
    footer, then the quoted original. Same order in both twins."""
    from html import escape
    h = mailmime.sanitize_html(html) if (html or "").strip() else "".join(f"<p>{escape(p)}</p>" for p in (text or "").split("\n\n") if p.strip())
    t = mailmime.html_to_text(h)
    so = (sign_off or "").strip()
    if so:
        h += "<p>" + "<br>".join(escape(ln) for ln in so.splitlines()) + "</p>"
        t += "\n\n" + so
    if footer_html:
        h += footer_html; t += "\n\n" + footer_text
    if quote:
        h += quote[0]; t += "\n\n" + quote[1]
    return h, t
```

In the send route (reply branch): after the recipient resolution, parse `cc`/`bcc` with `_mail_clean_addresses` (cap 10 total, mailbox refused), `attachments`/`inline` lists (each item's `key` validated via `_mail_attachment_ok`; on the dry run just validate keys exist by HEAD and sum sizes), build `quote = mailmime.quote_original(parent) if body.get("quote", True) else None`, get footer via `_mail_email_block`, then `html, text = _mail_compose_body(...)`. Dry run returns the counts. Real send: stamp (with `attachments: [{name, size}]`), write, then `files, inline, total = await _mail_fetch_parts(...)` inside try/except ValueError -> clear stamp, write, 400 with the reason; then `raw = mailmime.build_message(frm=addr, to=to_addr, cc=cc, bcc=bcc, subject=..., html=html, text=text, inline=inline, files=files, in_reply_to=..., references=..., reply=True)`; `await google_mail.send_message(..., raw_bytes=raw)`. On success record `sent_attachments`. The new-message branch is the same with `reply=False`, no quote, no in_reply_to. The draft save op mirrors the reply branch and calls `create_draft(..., raw_bytes=raw)`. The old `_mail_outgoing_text` plain path stays only for callers that send `text` without `html` (Claude's draft comes as text and is turned into paragraphs by `_mail_compose_body`).

- [ ] **Step 4: Run to verify they pass** (earlier send tests that asserted on `body_text` reaching the fake sender must now read the html/text out of `raw_bytes`; update those assertions, requirement unchanged).
- [ ] **Step 5: Mutation checks:** drop the sanitiser call in `_mail_compose_body` (script survives); drop the stamp clearing on ValueError; both must fail tests; restore.
- [ ] **Step 6: Commit** `git commit -am "Send and draft carry formatting, files, footer and the original"`

---

### Task 8: The thread exposes recipients for Reply all

**Files:**
- Modify: `copilot.py` (`/api/mail/thread` route)
- Test: `tests/test_dispatch.py`

**Interfaces:**
- Produces: `/api/mail/thread` gains `"reply_all_cc": "<comma list>"`: every address on the latest customer message's To and Cc plus its From, minus the mailbox and minus the reply target, deduped, lowercased.

- [ ] **Step 1: Test**

```python
@test
def t_reply_all_offers_everyone_but_us_and_the_person_we_answer():
    def go():
        ensure_auth(); _gm.save_connection("rt-test", MBOX); _seed_thread("t1", subject="x")
        async def fake_read(tid, per_msg_chars=4000):
            return {"id": tid, "messages": [{"id": "m1", "from_name": "Jo", "from_email": "jo@c.test", "reply_to": "",
                     "to": f"{MBOX}, pat@c.test", "cc": "Sam <sam@c.test>, jo@c.test", "subject": "x", "message_id": "<a@m>", "references": "", "at": "", "text": "hi", "html": ""}]}
        saved = _gm.read_thread; _gm.read_thread = fake_read
        try:
            j = post("/api/mail/thread", {"id": "t1"}).json()
            eq(j["reply_all_cc"], "pat@c.test, sam@c.test")
        finally:
            _gm.read_thread = saved
    with_mail(go)
```

- [ ] **Step 2 to 4:** fail, implement with `email.utils.getaddresses` over `to`/`cc`/`from_email` of the latest message not from the mailbox, filter, dedupe, sort by first appearance; pass.
- [ ] **Step 5: Commit** `git commit -am "Reply all knows who else was on the message"`

---

### Task 9: composer.js and its route

**Files:**
- Create: `static/composer.js`
- Modify: `copilot.py` (`_page_parts` ~7804 to hash and serve it; `_asset_response` kinds; the shell's script tags ~7834), `tests/test_frontend.py`
- Test: `tests/test_frontend.py` (source guards over `static/composer.js`), plus a rig walk

**Interfaces:**
- Produces: `window.mountComposer(host, opts) -> handle` with `opts = {html: "", onChange: fn, signUrl: async (key) => url}` and handle `{getHtml(), setHtml(html), insertText(text), attachments(), addAttachment({key,name,size,type}), removeAttachment(key), focus(), el}`. The editor emits inline images as `<img src="<signed url>" data-key="mail/..." data-cid="img<n>">`; `getHtml()` rewrites them to `<img src="cid:img<n>">` and lists them under `attachments()` with `inline: true`. Served at `/assets/composer.js?v=<hash>` exactly like `app.js`; the shell loads it after `app.js`.

- [ ] **Step 1: Frontend guards (write first)** in `tests/test_frontend.py`, reading `static/composer.js` into `COMPOSER`:

```python
@test
def t_the_composer_is_its_own_file_served_like_the_app_script():
    ok("function mountComposer(" in COMPOSER and "window.mountComposer = mountComposer" in COMPOSER)
    src = open("copilot.py", encoding="utf-8").read()
    ok('"/assets/composer.js"' in src and '_asset_hashes["composer"]' in src, "hashed and routed like app.js")
    ok("composer.js?v=" in src, "the shell loads it by hash")
    ok("—" not in COMPOSER and "–" not in COMPOSER, "no em or en dashes")

@test
def t_the_composer_toolbar_covers_the_agreed_set_and_nothing_hides_on_a_phone():
    for cmd in ("bold", "italic", "underline", "fontName", "fontSize", "foreColor", "justifyLeft", "justifyCenter",
                "justifyRight", "insertUnorderedList", "insertOrderedList", "createLink", "removeFormat", "formatBlock"):
        ok(f"'{cmd}'" in COMPOSER, f"toolbar command {cmd}")
    ok("'image'" in COMPOSER and "'attach'" in COMPOSER, "image and attach buttons")
    ok("flex-wrap: wrap" in COMPOSER or "flex-wrap:wrap" in COMPOSER, "the toolbar wraps rather than hiding")

@test
def t_pasted_markup_is_cleaned_to_the_same_allowlist_as_the_server():
    ok("addEventListener('paste'" in COMPOSER and "clipboardData" in COMPOSER)
    ok("function cleanHtml(" in COMPOSER, "one cleaner, applied on paste and on getHtml")
    for tag in ("script", "iframe", "style", "svg"):
        ok(f"'{tag}'" in COMPOSER, f"{tag} is named in the drop list")
    ok("'cid:'" in COMPOSER or 'cid:' in COMPOSER, "images leave as cids")

@test
def t_inline_images_become_cids_and_are_counted_against_the_meter():
    ok("data-key" in COMPOSER and "data-cid" in COMPOSER)
    ok("25 * 1024 * 1024" in COMPOSER, "the meter knows the ceiling")
    ok("inline: true" in COMPOSER)
```

- [ ] **Step 2: Run** `python3 tests/test_frontend.py` and see the four fail on "file not found" first (create an empty `static/composer.js` so they fail on assertions).

- [ ] **Step 3: Write `static/composer.js`.** Shape (write it in full; the essentials that the guards and the spec require):

```js
/* gizmo composer: a contenteditable editor with the toolbar the Inbox agreed
   on. Zero dependencies. The browser cleaner here is a courtesy; the server
   sanitiser is the guarantee, so the two allowlists must stay identical. */
(function () {
    const TAGS = new Set(['p','br','div','span','b','strong','i','em','u','a','ul','ol','li','h1','h2','h3','blockquote','font','img']);
    const DROP = new Set(['script','style','iframe','object','embed','svg','math','template']);
    const STYLE_OK = ['font-family','font-size','color','text-align'];
    const MAX_TOTAL = 25 * 1024 * 1024;
    const FONTS = ['Arial','Georgia','Verdana','Trebuchet MS','Courier New'];
    const SIZES = [['Small','2'],['Normal','3'],['Large','5'],['Huge','7']];
    const COLOURS = ['#0a0a0a','#525252','#b91c1c','#c2410c','#15803d','#1d4ed8','#7e22ce','#be185d'];

    function cleanHtml(html) {          /* DOMParser, walk, rebuild by allowlist */
        const doc = new DOMParser().parseFromString('<body>' + html + '</body>', 'text/html');
        const walk = (node) => { ...drop DROP subtrees, unwrap unknown tags keeping children,
            keep href only https:/mailto:, keep img src only cid: or data-key (rewritten later),
            keep style only STYLE_OK without "url("... };
        walk(doc.body); return doc.body.innerHTML;
    }
    function mountComposer(host, opts) {
        opts = opts || {};
        const wrap = el('div', 'cmp'); const bar = el('div', 'cmp-bar');   /* .cmp-bar { display:flex; flex-wrap: wrap } */
        const area = el('div', 'cmp-area'); area.contentEditable = 'true'; area.innerHTML = cleanHtml(opts.html || '');
        const files = [];                 /* {key,name,size,type,inline,cid} */
        const meter = el('div', 'cmp-meter');
        const cmd = (name, arg) => { area.focus(); document.execCommand(name, false, arg); changed(); };
        [['bold','B'],['italic','I'],['underline','U']].forEach(([c,l]) => bar.append(btn(l, () => cmd(c))));
        bar.append(select(FONTS, v => cmd('fontName', v)), select(SIZES, v => cmd('fontSize', v)), colours(v => cmd('foreColor', v)));
        [['justifyLeft'],['justifyCenter'],['justifyRight'],['insertUnorderedList'],['insertOrderedList']].forEach(([c]) => bar.append(btn(icon(c), () => cmd(c))));
        bar.append(btn('Link', () => { const u = prompt('Link address (https://...)'); if (u && /^https:\/\//i.test(u)) cmd('createLink', u); }));
        bar.append(btn('Quote', () => cmd('formatBlock', 'blockquote')), btn('Clear', () => cmd('removeFormat')));
        bar.append(btn('image', () => pick(true)), btn('attach', () => pick(false)));
        area.addEventListener('keydown', e => { if ((e.metaKey || e.ctrlKey) && !e.shiftKey) { const k = e.key.toLowerCase();
            if (k === 'b') { e.preventDefault(); cmd('bold'); } else if (k === 'i') { e.preventDefault(); cmd('italic'); }
            else if (k === 'u') { e.preventDefault(); cmd('underline'); } else if (k === 'k') { e.preventDefault(); bar.querySelector('[data-cmd=link]').click(); } } });
        area.addEventListener('paste', e => { const html = e.clipboardData.getData('text/html'); if (html) { e.preventDefault(); document.execCommand('insertHTML', false, cleanHtml(html)); changed(); } });
        function getHtml() {           /* rewrite data-key images to cid:, register inline files */
            const clone = area.cloneNode(true);
            clone.querySelectorAll('img[data-key]').forEach(img => { img.setAttribute('src', 'cid:' + img.dataset.cid); img.removeAttribute('data-key'); img.removeAttribute('data-cid'); });
            return cleanHtml(clone.innerHTML);
        }
        function insertText(text) { area.focus(); document.execCommand('insertHTML', false, text.split(/\n\n+/).map(p => '<p>' + esc(p).replace(/\n/g, '<br>') + '</p>').join('')); changed(); }
        ... addAttachment / removeAttachment / meter ("x of 25MB", refuse over MAX_TOTAL) / pick() calls opts.upload(file, inline) which the page supplies (it runs the presign flow) and returns {key,name,size,type,url}; inline images insert <img src=url data-key=key data-cid=...>.
        host.append(wrap); return { getHtml, setHtml, insertText, attachments: () => files.slice(), addAttachment, removeAttachment, focus: () => area.focus(), el: wrap };
    }
    window.mountComposer = mountComposer;
})();
```

The CSS for `.cmp*` goes in the same file as a `<style>` injected once (`document.head.append`) using the app's tokens (`var(--sp-2)`, `var(--r-sm)`, `var(--ink-3)`, `.btn`-like buttons). Serving: in `_page_parts`, read `static/composer.js`, hash it into `_asset_hashes["composer"]`, add it to the `assets` dict as `("application/javascript", blob)`, and emit `<script src="/assets/composer.js?v=..."></script>` after the app script; add the route:

```python
    @mcp.custom_route("/assets/composer.js", methods=["GET"])
    async def composer_js(request: Request):
        return _asset_response("composer", request.query_params.get("v", ""))
```

The rig (`scratchpad/rig/serve.py`) must also serve `/assets/composer.js` by reading `static/composer.js`; add it there for verification only.

- [ ] **Step 4: Run the frontend suite** (green with the new count) and open the rig: the script loads (`window.mountComposer` is a function in the console).
- [ ] **Step 5: Commit** `git add static/composer.js copilot.py tests/test_frontend.py && git commit -m "A composer of our own"`

---

### Task 10: Mount the composer in Compose and Reply, with everything around it

**Files:**
- Modify: `static/index.html` (`openMailCompose` ~16151, `mailDraftPanel` ~16253, `mailComposeDraft` ~16227, `mailSendFlow` ~16018, `mailAddedWhenSent` ~16110, `mailReplyPicker` ~16123, the Filters window Email section, the settings sign-off row is unchanged)
- Test: `tests/test_frontend.py`, rig walk

**Interfaces:**
- Consumes: `mountComposer` (Task 9), the send/draft payloads (Task 7), `reply_all_cc` (Task 8), `footer_slots`/`footer_html`/`logo_view` (Task 5), `attach-url`/`attach-done` (Task 6).
- Produces: `mailUpload(file, inline) -> Promise<{key,name,size,type,url}>` (presign, PUT, done, then `download-url`-style signed GET for images via `attach-done`'s returned `url`); `mailComposerPayload(handle) -> {html, attachments: [{key,name,type}], inline: [{key,cid,type}]}`.

- [ ] **Step 1: Frontend guards (write first)**

```python
@test
def t_compose_and_reply_mount_the_composer_and_nothing_else_does():
    eq(SCRIPT.count("mountComposer("), 2, "Compose and the reply panel, exactly")
    ok("mailComposerPayload(" in SCRIPT and "'html'" in fn_src("function mailComposerPayload(") or "html:" in fn_src("function mailComposerPayload("))

@test
def t_the_dry_run_confirm_names_recipients_and_attachment_count():
    fn = fn_src("async function mailSendFlow(")
    ok("attachment_count" in fn and "cc_count" in fn, "the confirm row reads the counts the dry run returned")

@test
def t_cc_bcc_fold_away_and_reply_all_fills_cc_minus_us():
    fn = fn_src("function mailDraftPanel(")
    ok("Cc" in fn and "Bcc" in fn and "reply_all_cc" in fn and "Reply all" in fn)

@test
def t_the_quoted_original_is_a_switch_not_a_rendering():
    fn = fn_src("function mailDraftPanel(")
    ok("quote:" in fn and "will be quoted" in fn.lower() or "quoted below" in fn.lower())
    ok(".innerHTML = t." not in fn and "innerHTML = msg." not in fn, "no incoming html reaches the page")

@test
def t_uploads_go_through_presign_then_done_and_never_the_server_body():
    fn = fn_src("async function mailUpload(")
    ok("/api/mail/attach-url" in fn and "/api/mail/attach-done" in fn and "method: 'PUT'" in fn)

@test
def t_footer_slots_are_edited_by_leads_with_a_logo_picker():
    fn = fn_src("async function paintMailEmailSettings(")
    for k in ("company", "address", "phone", "website", "legal"):
        ok(f"'{k}'" in fn, f"slot {k}")
    ok("logo_url" in fn and "logo_done" in fn and "footer_slots" in fn)
    ok("'footer'" not in fn or "op: 'footer'" not in fn, "the free-text footer op is gone")
```

- [ ] **Step 2: Run to see them fail**
- [ ] **Step 3: Implement** in `static/index.html`:
  - `mailUpload(file, inline)`: POST `attach-url` -> `fetch(url, {method: 'PUT', body: file, headers: {'Content-Type': file.type}})` -> POST `attach-done` -> resolve `{key, name, size, type, url}` (the `url` from `attach-done` for inline images; add `url` to that route's 200 for images: `_files_sign_get(key, name, inline=True)`).
  - `mailComposerPayload(h)`: `{html: h.getHtml(), attachments: h.attachments().filter(a => !a.inline).map(a => ({key, name, type})), inline: h.attachments().filter(a => a.inline).map(a => ({key, cid, type}))}`.
  - `openMailCompose`: replace the textarea with `const cmp = mountComposer(box, {upload: mailUpload})`; keep To (typeahead), Subject; add a "Cc / Bcc" link that reveals two inputs; Send goes through `mailSendFlow(bar, Object.assign({to, cc, bcc, subject}, mailComposerPayload(cmp)), ...)`; `mailReplyPicker` takes the handle and calls `cmp.insertText(text)`; `mailAddedWhenSent` renders the sign-off as text and the footer from `mailCache.email.footer_html` into a sandboxed preview: it is OUR rendered footer (server-sanitised, from slots), inserted with innerHTML after replacing `cid:logo` with the signed URL from `logo_view`; nothing from a customer is in it.
  - `mailDraftPanel`: same mount; `out.draft` (Claude's text) goes in via `cmp.insertText`; Cc/Bcc fold; "Reply all" checkbox fills Cc from `t.reply_all_cc` (from the thread payload); the collapsed line "The original message will be quoted below your reply" with a checkbox bound to `quote`; the Send dry run shows "Send to jo@c.test, 1 cc, 2 attachments?".
  - `mailSendFlow`: the confirm text uses `dry.to`, `dry.cc_count`, `dry.attachment_count`.
  - `paintMailEmailSettings`: five slot inputs + Save, a logo picker (file input -> `logo_url` -> PUT -> `logo_done`, then shows it via `logo_view`), the saved-replies list unchanged.
  - The rig gets canned `attach-url` (`{'url': 'http://localhost:8777/rig-put', 'key': 'mail/u1/aa-q.pdf'}`), a `do_PUT` that answers 200, `attach-done` (`{'ok': True, 'key': ..., 'name': 'q.pdf', 'size': 1000, 'type': 'application/pdf', 'url': ''}`), `logo_view`, `reply_all_cc` on `/api/mail/thread`, and `footer_slots`/`footer_html` on the board.
- [ ] **Step 4: Run the frontend suite green; rig walk** at 1600 and 375: Compose -> type, bold a word, add a list, attach a file (meter reads "1 KB of 25MB"), Cc fold, dry run confirm text, Send; thread -> Write a reply -> Reply all fills Cc, quote switch present, Send; Filters -> Email -> slots + logo. Zero console errors.
- [ ] **Step 5: Commit** `git commit -am "Compose and Reply, the way Gmail does it"`

---

### Task 11: Final gate (orchestrator)

- [ ] Joint run of both suites after the last edit; dash ban across `static/index.html` and `static/composer.js`; `git diff tests/ | grep '^-def t_'` empty.
- [ ] Rig walk of Compose and Reply at 1600 and 375 with an attachment and an inline image; the footer preview shows the logo.
- [ ] Push; CI green; memory note; spec status updated to "shipped".
