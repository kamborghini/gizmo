#!/usr/bin/env python3
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
# Whole subtrees, not just the tag: the text inside a <script> is code, and
# unwrapping it into the body would hand the customer's mail client the very
# string the tag was dropped for.
_DROP = ("script", "style", "iframe", "object", "embed", "svg", "math", "template")
_STYLE_OK = ("font-family", "font-size", "color", "text-align")
_STYLE_VAL = re.compile(r"^[a-zA-Z0-9 ,#%.'\"-]+$")   # no url(), no expression(), no escapes
_CID_RX = re.compile(r"^cid:[A-Za-z0-9._@-]+$")


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


def _clean_href(value: str) -> str:
    """An https or mailto address, with its SCHEME normalised to lower case.

    The scheme is the only part that may be case-folded: a path can be
    case-sensitive on the far end, so the rest is left exactly as typed."""
    v = (value or "").strip()
    low = v.lower()
    for scheme in ("https://", "mailto:"):
        if low.startswith(scheme):
            return (scheme + v[len(scheme):])[:2000].replace('"', "%22")
    return ""


class _Sanitiser(HTMLParser):
    def __init__(self, footer: bool):
        super().__init__(convert_charrefs=True)
        self.allowed = _TAGS | (_FOOTER_TAGS if footer else set()) | {"img"}
        self.out, self.skip = [], 0        # skip counts open tags of dropped subtrees

    def handle_starttag(self, tag, attrs):
        if tag in _DROP:
            self.skip += 1
            return
        if self.skip or tag not in self.allowed:
            return
        keep = []
        for k, v in attrs:
            k, v = k.lower(), (v or "")
            if k == "href" and tag == "a":
                href = _clean_href(v)
                if href:
                    keep.append(("href", href))
            elif k == "src" and tag == "img":
                if _CID_RX.match(v.strip()):
                    keep.append(("src", v.strip()))
            elif k == "alt" and tag == "img":
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
        if tag in _DROP:
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


# ---------------------------------------------------------------------------
# The MIME tree
# ---------------------------------------------------------------------------

def _multipart(subtype: str, parts: list):
    """A multipart of `subtype` holding `parts`, assembled rather than converted.

    The stdlib's convenience API only builds the OTHER nesting (an alternative
    holding a related), and refuses make_related on an alternative outright.
    The shape below is the one every mail client agrees about, so the tree is
    built by hand: an empty part, told what it is, with children attached."""
    from email.message import MIMEPart
    m = MIMEPart()
    m["Content-Type"] = "multipart/" + subtype
    for p in parts:
        m.attach(p)
    return m


def _leaf(data: bytes, ctype: str, name: str, cid: str = "", inline: bool = False):
    from email.message import MIMEPart
    maintype, _, subtype = (ctype or "application/octet-stream").partition("/")
    if not subtype:
        maintype, subtype = "application", "octet-stream"
    p = MIMEPart()
    kw = {"maintype": maintype, "subtype": subtype,
          "disposition": "inline" if inline else "attachment"}
    if name:
        kw["filename"] = name
    if cid:
        kw["cid"] = cid
    p.set_content(data, **kw)
    return p


def build_message(*, frm, to, subject, html, text, cc="", bcc="", inline=(), files=(),
                  in_reply_to="", references="", reply=True) -> bytes:
    """The RFC 5322 bytes, with the alternative/related/mixed nesting that every
    client reads the same way. Headers are cleaned of line breaks: each value
    came from data the sender ultimately controls.

    Parts are omitted when they are empty, so a plain reply with no files is
    still just a small multipart/alternative."""
    from email.message import MIMEPart

    def clean(v):
        return " ".join(str(v or "").split())[:998]

    body = MIMEPart()
    body.set_content(text or "")
    body.add_alternative(html or "", subtype="html")
    if inline:
        parts = [body]
        for im in inline:
            cid = str(im.get("cid") or "").strip()
            parts.append(_leaf(im["data"], im.get("type") or "image/png",
                               clean(im.get("name")), cid=f"<{cid}>" if cid else "",
                               inline=True))
        body = _multipart("related", parts)
    if files:
        parts = [body]
        for f in files:
            parts.append(_leaf(f["data"], f.get("type") or "application/octet-stream",
                               clean(f.get("name"))))
        body = _multipart("mixed", parts)

    # The headers go on whatever ended up outermost. MIME-Version is added
    # here rather than by set_content, which strips it from every subpart.
    msg = body
    del msg["MIME-Version"]
    msg["MIME-Version"] = "1.0"
    if frm:
        msg["From"] = clean(frm)
    msg["To"] = clean(to)
    if cc:
        msg["Cc"] = clean(cc)
    if bcc:
        # A header on the built bytes, which Gmail strips before delivery.
        # Written down here so the copy in Sent says who else was written to.
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
    # The module's own policy, the same one the plain-text builder has always
    # used: Gmail normalises the line endings, and matching the existing path
    # keeps one shape of bytes going out of this app rather than two.
    return msg.as_bytes()


# ---------------------------------------------------------------------------
# The footer and the quoted original
# ---------------------------------------------------------------------------

def render_footer(slots: dict, logo_cid: str = "") -> tuple:
    """(html, text) for the shop's footer, from its slots.

    Slots rather than free-form HTML, and the result goes through the same
    sanitiser as everything else: the footer is on every email the shop
    sends, which makes it the last place to trust an unchecked string."""
    s = {k: " ".join(str((slots or {}).get(k) or "").split()) for k in
         ("company", "address", "phone", "website", "legal")}
    lines = [v for v in (s["company"], s["address"], s["phone"], s["website"], s["legal"]) if v]
    if not lines and not logo_cid:
        return "", ""
    cells = []
    if logo_cid:
        cells.append(f'<td style="padding:0 12px 0 0">'
                     f'<img src="cid:{escape(logo_cid, True)}" '
                     f'alt="{escape(s["company"], True)}" width="120"></td>')
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
    cells.append('<td style="font-family:Arial,sans-serif;font-size:13px;color:#0a0a0a">'
                 + "<br>".join(body) + "</td>")
    html = ('<table role="presentation" style="border-collapse:collapse;margin-top:16px"><tr>'
            + "".join(cells) + "</tr></table>")
    return sanitize_html(html, footer=True), "\n".join(lines)


def quote_original(msg: dict) -> tuple:
    """(html, text) of "On <date>, <who> wrote:" and the original beneath it.

    Assembled and sanitised HERE, on the server, so the browser never has to
    render anything that came from outside the shop. An original with no HTML
    is quoted as escaped text rather than repaired into markup."""
    from datetime import datetime
    name = " ".join(str(msg.get("from_name") or "").split())
    addr = " ".join(str(msg.get("from_email") or "").split())
    who = f"{name} <{addr}>" if name else addr
    when = ""
    try:
        when = datetime.fromisoformat(
            str(msg.get("at") or "").replace("Z", "+00:00")).strftime("%-d %b %Y")
    except ValueError:
        pass
    head = f"On {when}, {who} wrote:" if when else f"{who} wrote:"
    inner = (sanitize_html(msg.get("html") or "") if (msg.get("html") or "").strip()
             else escape(msg.get("text") or "").replace("\n", "<br>"))
    html = f'<div class="gizmo-quote"><p>{escape(head)}</p><blockquote>{inner}</blockquote></div>'
    body = msg.get("text") or html_to_text(msg.get("html") or "")
    text = head + "\n" + "\n".join("> " + ln for ln in body.splitlines())
    return html, text
