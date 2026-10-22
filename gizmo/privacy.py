"""Customer-data erasure: the scrubber, the keys and matching that decide what
belongs to one person, the sweep, shop and customer redaction, the requests
held for an admin, and the privacy log. Moved out of copilot.py (stage 4 of
the 14 October audit); its routes (the privacy settings and Shopify's
privacy webhook) are in gizmo/routes/privacy.py. Read as `privacy.NAME`.
"""
import logging
import os
import re
import time
import hmac
import hashlib
import unicodedata
import bisect
import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
import google_mail
import tokenvault
from gizmo.config import _env_num
from gizmo import store as jsonstore
from gizmo import shopify
import base64
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from gizmo import background

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")




# ---- What an erasure leaves behind, and how it stays out ----------------
# An organisation's deal outlives a contact who asked to be erased: it is the
# organisation's history. Pipedrive still holds the deal, often with their
# name in its title and their number in its notes, and the import keeps
# updating it (stage, value, won), so the name is taken out on EVERY import,
# not once. To do that the app has to recognise the name without keeping it:
# each erased name, address and number is remembered only as a keyed hash,
# never as text. When TOKEN_ENCRYPTION_KEY is set the key comes from it, so a
# copy of the CRM file (a backup, a snapshot) holds hashes without their key.
#
# Two rules keep it from taking what is somebody else's. Only the address the
# erasure was asked for recognises a person (a colleague who shares a
# switchboard number or a sales@ address is not them). And anything a live
# contact also holds (that number, that address, the same name) is theirs
# too, and is left alone, except in the records that were linked to the
# person erased.
_ERASE_EMAIL_RE = re.compile(r"[\w+-][\w.'+-]*@[\w-]+(?:\.[\w-]+)+")
_ERASE_WORD_RE = re.compile(r"[^\W_]+(?:['-][^\W_]+)*")
_ERASE_DIGITS_RE = re.compile(r"\+?\d+")
_ERASE_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.I)
# Tags that end a line of text: a name never runs across them.
_ERASE_BLOCK_TAG_RE = re.compile(r"</?(?:p|br|div|li|ul|ol|tr|td|th|table|h[1-6]|blockquote|pre|hr)\b[^<>]{0,300}>", re.I)
_ERASE_TAG_RE = re.compile(r"</?[a-zA-Z][^<>]{0,300}>")
_ERASE_ENTITY_RE = re.compile(r"&(?:nbsp|#160|#xa0|amp|#38);", re.I)
_ERASE_SPACE_GAP_RE = re.compile(r"[ \t ]+")
_ERASE_SEP_GAP_RE = re.compile(r"[ \t ]*[&+/()\"'\-–—:][ \t ]*")
_ERASE_INITIAL_GAP_RE = re.compile(r"\.[ \t ]*")
_ERASE_REV_GAP_RE = re.compile(r",[ \t ]*")
_ERASE_PHONE_MIN = 7        # shorter digit runs are order numbers and quantities
_ERASE_HONORIFICS = frozenset("mr mrs ms miss mx dr prof sir dame rev".split())
_ERASE_PHONE_LABELS = frozenset(
    "tel telephone phone ph mob mobile m t cell work home office direct dd switchboard "
    "fax ext extension x".split())
# Words that are names AND ordinary English: in a name they count only when
# written with a capital, so "the price will include delivery" and "amber
# glass" are not a contact called Will Price or Amber Glass.
_ERASE_COMMON = frozenset("""
will price rose amber glass stage door grace hope mark bill frank joy dawn may june april
summer autumn winter hunter baker cook young white black green brown gold silver stone wood
hill field ward king lord bishop knight page bell cross lamb fox wolf bird rice long short
little street lane park bank chase dean earl duke reed rush sharp strong swift wise best hall
moss pool well wells banks lake ford marsh hart church chapel mason porter carter turner
walker parker cooper fisher miller taylor steel iron light lighting gobo gobos metal sales
office accounts info team studio events show house theatre art sky star sun rain snow ray
lee dale glen heath brook rock ash holly ivy daisy poppy iris lily olive pearl ruby crystal
faith mercy patience honor honour sterling penny cash case nick pat sue don ben rob jack
""".split())


def _erase_norm(s) -> str:
    s = unicodedata.normalize("NFC", str(s or ""))
    return s.replace("’", "'").replace("‘", "'")


def _erase_phone_canon(digits: str) -> str:
    """One spelling of a UK number: +44 191..., 0044 191..., +44 (0)191...
    and 0191... are the same phone."""
    d = re.sub(r"\D", "", str(digits or ""))
    if d.startswith("00"):
        d = d[2:]
    if d.startswith("440"):
        d = "0" + d[3:]
    elif d.startswith("44") and len(d) == 12:
        d = "0" + d[2:]
    return d


def _erase_phone_of(w: str) -> str:
    """The number in a stored phone value, or "" when it is not one. Labels
    and an extension ("Mob: 07700 900123", "0191 111 2222 ext 4") come off;
    any other word means it is not a phone."""
    core = re.sub(r"(?i)(?:\bext(?:ension)?\.?|\bx|#)\s*\d{1,5}\s*$", "", w)
    words = re.findall(r"[^\W\d_]+", core)
    if any(x.lower() not in _ERASE_PHONE_LABELS for x in words):
        return ""
    core = re.sub(r"[^\W\d_]+\.?:?", " ", core)
    if not re.fullmatch(r"[\d\s().+/-]+", core.strip() or "x"):
        return ""
    d = _erase_phone_canon(core)
    return d if len(d) >= _ERASE_PHONE_MIN else ""


def _erase_canon(word) -> list:
    """What one erased word is, as [(kind, canonical, size)].

    kind is "email", "phone", "name" (in order, 2 words or more) or "rev" (a
    two-word name surname first, which needs a comma in the text). A name
    also counts without its title (Dr, Mrs), without a bracketed or trailing
    part ("Sarah Whitfield (Lumen)", "Sarah Whitfield - Lumen Events"), and,
    for three or four words, as its first and last word. One word alone is
    never a name: it is too likely to be somebody else's."""
    w = _erase_norm(word).strip()
    if not w:
        return []
    if "@" in w:
        low = w.lower()
        return [("email", low, 1)] if _ERASE_EMAIL_RE.fullmatch(low) else []
    if re.search(r"\d", w):
        d = _erase_phone_of(w)
        if d:
            return [("phone", d, 1)]
        # Not a number: a name with a digit in it ("Sarah Whitfield 2", a
        # Pipedrive duplicate; "Sarah Whitfield (Panto 2024)"). Its words
        # are its name, and the verbatim spelling counts too.
    out, seen = [], set()

    def add(toks, short=True):
        while toks and toks[0] in _ERASE_HONORIFICS:
            toks = toks[1:]
        if len(toks) < 2 or len(" ".join(toks)) < 4:
            return
        variants = [toks]
        alpha = [t for t in toks if not t.isdigit()]
        if short and 3 <= len(alpha) <= 4:
            variants.append([alpha[0], alpha[-1]])
        if short and len(alpha) == 2 and alpha != toks:
            variants.append(alpha)
        for v in variants:
            key = " ".join(v)
            if ("name", key) not in seen:
                seen.add(("name", key))
                out.append(("name", key, len(v)))
            if len(v) == 2 and ("rev", v[1] + " " + v[0]) not in seen:
                seen.add(("rev", v[1] + " " + v[0]))
                out.append(("rev", v[1] + " " + v[0], 2))

    add([t.lower() for t in _ERASE_WORD_RE.findall(w)], short=False)   # verbatim, as stored
    # Without a bracketed part, a quoted nickname, or what follows a dash, a
    # slash, a bar or a comma ("Sarah Whitfield, LD", "... / Lumen").
    cleaned = re.sub(r"\([^)]*\)|\"[^\"]*\"|(?<!\w)'[^']*'(?!\w)", " ", w)
    cleaned = re.split(r"\s[-–—|/]\s|,", cleaned)[0]
    add([t.lower() for t in _ERASE_WORD_RE.findall(cleaned)])
    return out


def _erase_alive(people, names=()) -> set:
    """(kind, canonical) for everything live contacts hold (their names, their
    addresses and their numbers) and for other names that are not a person's
    (organisations: a contact stored as "Lumen Events" or "Box Office" is the
    firm's or the role's name, not theirs). What is theirs too is not taken
    out."""
    out = set()
    for p in people:
        for w in _erase_words_of(p):
            for kind, canon, _n in _erase_canon(w):
                out.add((kind, canon))
    for w in names:
        for kind, canon, _n in _erase_canon(w):
            if kind in ("name", "rev"):
                out.add((kind, canon))
    return out


def _erase_split(words) -> tuple:
    """(names, addresses and numbers) of a record's words, canonical."""
    names, ids = set(), set()
    for w in words:
        for kind, canon, _n in _erase_canon(w):
            if kind == "name":
                names.add(canon)
            elif kind in ("email", "phone"):
                ids.add((kind, canon))
    return names, ids


def _erase_same_person(a_words, b_words) -> bool:
    """Two contact records are one person when they have the same name AND
    share an address or a number. Either alone is not enough: a colleague
    shares the switchboard, a namesake shares the name."""
    an, ai = _erase_split(a_words)
    bn, bi = _erase_split(b_words)
    return bool(an & bn) and bool(ai & bi)


def _erase_list(v) -> list:
    """A stored field as a list of values, whatever shape it arrived in."""
    if isinstance(v, (list, tuple)):
        return list(v)
    return [v] if isinstance(v, str) and v else []


def _erase_words_of(p) -> list:
    if not isinstance(p, dict):
        return []
    return [p.get("name")] + _erase_list(p.get("emails")) + _erase_list(p.get("phones"))


def _erase_pepper() -> tuple:
    """(secret, key id) mixed into every mark's key: derived from the token
    vault's key when there is one, so the CRM file alone cannot be brute
    forced; nothing, and the id "none", when there is not."""
    try:
        k = tokenvault._key()
    except Exception as e:
        logger.warning("erasure marks are made without the token vault's pepper: its key could not be read (%s)",
                       type(e).__name__)
        k = None
    if not k:
        return b"", "none"
    pep = hmac.new(k, b"gizmo-erasure-marks-v1", hashlib.sha256).digest()
    return pep, hashlib.sha256(pep).hexdigest()[:12]


def _erase_key(salt: str, pepper: bytes) -> bytes:
    raw = bytes.fromhex(salt)
    return hmac.new(pepper, raw, hashlib.sha256).digest() if pepper else raw


def _erase_hash(key: bytes, kind: str, canon: str) -> str:
    return hmac.new(key, (kind + ":" + canon).encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def _erase_stale_marks(d: dict) -> int:
    """Marks made under a key this process does not have (TOKEN_ENCRYPTION_KEY
    was changed or removed). They can no longer recognise anyone, so an
    import that relied on them would bring erased people back."""
    _pep, kid = _erase_pepper()
    return sum(1 for m in (d.get("erased_marks") or [])
               if isinstance(m, dict) and str(m.get("kid") or "none") not in ("none", kid))


def _erase_import_blocker(d: dict) -> str:
    """Why a Pipedrive import must not run now, or "". Both reasons are the
    same risk: people erased on request coming back."""
    if mail.MAILBOX_PATH in jsonstore._poisoned_stores:
        return ("The mailbox file could not be read, and it holds the list of people erased on "
                "request. Nothing is imported until it is repaired, so nobody who asked to be "
                "erased comes back.")
    stale = _erase_stale_marks(d)
    if stale:
        return ("People erased on request are remembered under a different encryption key "
                "(it was changed or removed in the app's hosting settings), so an import could not keep "
                "them out. Put the previous key back before importing.")
    return ""


def _erase_remember(d: dict, words, pd_ids=(), request: str = "", shared=()) -> None:
    """Keep what is needed to recognise an erased person again, and nothing
    that names them: keyed hashes of their name, addresses and numbers, the
    address the erasure was asked for as the one that recognises them, and
    the Pipedrive ids their contact had. A word a live contact also holds
    (shared: a switchboard, an office@ address, a namesake) is remembered as
    shared, and is taken out only of the records that were theirs, even
    after that contact has gone."""
    salt = str(d.get("erased_salt") or "")
    if not re.fullmatch(r"[0-9a-f]{32}", salt):
        salt = secrets.token_hex(16)
        d["erased_salt"] = salt
        d["erased_marks"] = []          # marks under another salt can never match again
    pepper, kid = _erase_pepper()
    key = _erase_key(salt, pepper)
    marks = [m for m in (d.get("erased_marks") or []) if isinstance(m, dict)]
    have = {(m.get("k"), m.get("h")) for m in marks}

    shared = set(shared or ())
    old_keys = {"none": _erase_key(salt, b"")}
    if pepper:
        old_keys[kid] = key
    was_shared = {(m.get("k"), m.get("h"), str(m.get("kid") or "none")) for m in marks if m.get("s")}

    def put(kind, canon, n, s=False):
        h = _erase_hash(key, kind, canon)
        # Once remembered as shared, always: a mark made again later, when
        # nobody live holds it any more (or under a new key), keeps that.
        s = s or any((kind, _erase_hash(k_, kind, canon), mk) in was_shared for mk, k_ in old_keys.items())
        if (kind, h) not in have:
            have.add((kind, h))
            m = {"k": kind, "h": h, "n": n, "kid": kid}
            if s:
                m["s"] = 1
            marks.append(m)

    for w in words:
        for kind, canon, n in _erase_canon(w):
            put(kind, canon, n, (kind, canon) in shared)
            if kind in ("name", "rev"):
                put("first", canon.split(" ")[0], 1)
    req = _erase_norm(request).strip().lower()
    if req and _ERASE_EMAIL_RE.fullmatch(req):
        put("req", req, 1)
        put("email", req, 1)
    d["erased_marks"] = marks[-40000:]
    ids = [str(x) for x in (d.get("erased_pd_persons") or [])]
    for x in pd_ids:
        if x and str(x) not in ids:
            ids.append(str(x))
    d["erased_pd_persons"] = ids[-20000:]


def _erase_scrubber(d: Optional[dict] = None, words=(), alive=(), requests=()):
    """A function scrub(text, linked=False) that takes every erased name,
    address and number out of a text, or None when there is nothing it could
    take out. It knows the CRM's remembered marks (d), words handed to it in
    the clear (an erasure's own, or a Pipedrive contact recognised as erased),
    and erased addresses that recognise a person (requests: the mailbox's
    list). What live contacts hold (alive) is left alone, except in a record
    that was linked to the person erased (linked=True), where their name is
    theirs whoever else shares it.

    Matching is by whole words: an address as a whole address; a number
    whatever its spacing; a name of two words or more, in order, its words
    apart by spaces, an initial's full stop, or &, +, /, brackets, a dash or a
    colon, never across a new line or a sentence; surname first only with a
    comma. Ordinary words ("Will", "Price") count in a name only with a
    capital. Tags and entities in HTML notes are seen through."""
    known: dict = {}
    for w in words:
        for kind, canon, n in _erase_canon(w):
            known.setdefault(kind, set()).add(canon)
            if kind in ("name", "rev"):
                known.setdefault("first", set()).add(canon.split(" ")[0])
    for r in requests:
        r = _erase_norm(r).strip().lower()
        if r and "@" in r:
            known.setdefault("req", set()).add(r)
            known.setdefault("email", set()).add(r)
    sizes: set = {n for kind, canon, n in
                  [c for w in words for c in _erase_canon(w)] if kind == "name"}
    # Remembered marks, by the key they can be read with: the salt alone for
    # marks made while no TOKEN_ENCRYPTION_KEY was set (still readable once
    # one is), the salt and the key for marks made since. Each hash maps to
    # whether it was shared with a live contact when it was remembered.
    salt = str((d or {}).get("erased_salt") or "")
    pepper, kid = _erase_pepper()
    keys: dict = {}
    if re.fullmatch(r"[0-9a-f]{32}", salt):
        keys["none"] = _erase_key(salt, b"")
        if pepper:
            keys[kid] = _erase_key(salt, pepper)
    hashed: dict = {}                   # key id -> kind -> {hash: shared}
    for m in (d or {}).get("erased_marks") or []:
        if not (isinstance(m, dict) and m.get("k") and m.get("h")):
            continue
        mk = str(m.get("kid") or "none")
        if mk not in keys:
            continue                    # made under a key this process does not have
        hashed.setdefault(mk, {}).setdefault(m["k"], {})[m["h"]] = bool(m.get("s"))
        if m["k"] == "name":
            try:
                sizes.add(int(m.get("n") or 2))
            except (TypeError, ValueError):
                sizes.add(2)

    def has(kind):
        return bool(known.get(kind)) or any(h.get(kind) for h in hashed.values())

    if not any(has(k) for k in ("email", "phone", "name", "rev")):
        return None
    alive = set(alive or ())
    memo: dict = {}
    first_memo: dict = {}

    def lookup(kind: str, canon: str) -> int:
        """0: not an erased word; 1: erased; 2: erased, but it was a live
        contact's too when it was remembered (a switchboard, an office@)."""
        k2 = (kind, canon)
        if k2 not in memo:
            marked = 0
            for mk, by_kind in hashed.items():
                got = by_kind.get(kind)
                if got:
                    h = _erase_hash(keys[mk], kind, canon)
                    if h in got:
                        marked = max(marked, 2 if got[h] else 1)
            # Shared wins: a word handed over in the clear (a recognised
            # contact's number, as Pipedrive has it) is still the firm's
            # switchboard if it was remembered as shared.
            memo[k2] = 2 if marked == 2 else (1 if marked or canon in known.get(kind, ()) else 0)
        return memo[k2]

    def is_known(kind: str, canon: str) -> bool:
        return lookup(kind, canon) > 0

    def applies(kind: str, canon: str, linked: bool) -> bool:
        """An erased word, here: always in a record that was the erased
        person's; elsewhere only if no live contact holds it now and none did
        when it was remembered."""
        hit = lookup(kind, canon)
        if not hit:
            return False
        if linked:
            return True
        return hit == 1 and (kind, canon) not in alive

    size_order = sorted((n for n in sizes if 2 <= n <= 6), reverse=True)

    def caps_ok(raw_tokens) -> bool:
        return all(t[:1].isupper() or t.lower() not in _ERASE_COMMON for t in raw_tokens)

    def gap_ok(gap: str, before: str) -> bool:
        if _ERASE_SPACE_GAP_RE.fullmatch(gap) or _ERASE_SEP_GAP_RE.fullmatch(gap):
            return True
        return len(before) == 1 and bool(_ERASE_INITIAL_GAP_RE.fullmatch(gap))

    def phone_gap_ok(gap: str) -> bool:
        return len(gap) <= 8 and "\n" not in gap and sum(c in "()./-" for c in gap) <= 2 \
            and not gap.strip(" \t ()./-")

    want_email = has("email")
    want_phone = has("phone")
    want_name = bool(size_order or has("rev"))
    done: dict = {}                     # text -> result: an import's sweep meets its own output again

    def scrub(text, linked: bool = False):
        if not isinstance(text, str) or not text:
            return text
        ck = (text, bool(linked))
        if ck in done:
            return done[ck]
        out = _scrub(text, linked)
        if len(done) < 250000:
            done[ck] = out
            if out != text:
                done[(out, bool(linked))] = out
        return out

    def _scrub(text, linked):
        s = unicodedata.normalize("NFC", text) if not unicodedata.is_normalized("NFC", text) else text
        # Two views of the text, both the same length as it, so a match maps
        # straight back. Addresses and numbers are read with the tags left in
        # (an address is often inside them: "Sarah <sarah@...>", a mailto
        # link); names are read with tags blanked, and a paragraph or line
        # break read as the end of a line, which no name runs across.
        ent = s.replace("\u2019", "'").replace("\u2018", "'")
        if "&" in ent:
            ent = _ERASE_ENTITY_RE.sub(
                lambda m: ("&" if m.group(0).lower() in ("&amp;", "&#38;") else " ") + " " * (len(m.group(0)) - 1),
                ent)
        flat = ent
        if "<" in flat:
            flat = _ERASE_BLOCK_TAG_RE.sub(lambda m: "\n" * len(m.group(0)), flat)
            flat = _ERASE_TAG_RE.sub(lambda m: " " * len(m.group(0)), flat)
        spans = []
        masked = []                         # inside an address or a link: not a name
        if "@" in ent:
            for m in _ERASE_EMAIL_RE.finditer(ent):
                masked.append((m.start(), m.end()))
                canon = m.group(0).lower()
                if want_email and applies("email", canon, linked):
                    spans.append((m.start(), m.end()))
        if "http" in ent or "www." in ent or "HTTP" in ent or "WWW." in ent:
            for m in _ERASE_URL_RE.finditer(ent):
                masked.append((m.start(), m.end()))

        masked.sort()
        mask_starts = [m[0] for m in masked]
        mask_reach, far = [], -1
        for _ma, mb in masked:
            far = max(far, mb)
            mask_reach.append(far)

        def in_mask(a, b):
            """Does a..b overlap an address or a link: does any mask that
            starts before b end after a?"""
            k = bisect.bisect_left(mask_starts, b)
            return k > 0 and mask_reach[k - 1] > a

        chains, cur = [], []
        for g in (_ERASE_DIGITS_RE.finditer(ent) if want_phone else ()):
            if cur and phone_gap_ok(ent[cur[-1].end():g.start()]) and not g.group(0).startswith("+"):
                cur.append(g)
            else:
                if cur:
                    chains.append(cur)
                cur = [g]
        if cur:
            chains.append(cur)
        for ch in chains:
            digs = [g.group(0).lstrip("+") for g in ch]
            if sum(len(x) for x in digs) < _ERASE_PHONE_MIN:
                continue
            i = 0
            while i < len(ch):
                hit = None
                for j in range(min(len(ch), i + 6) - 1, i - 1, -1):     # the longest number first
                    raw = "".join(digs[i:j + 1])
                    if not (_ERASE_PHONE_MIN <= len(raw) <= 16):
                        continue
                    num = _erase_phone_canon(raw)
                    if len(num) >= _ERASE_PHONE_MIN and applies("phone", num, linked) \
                            and not in_mask(ch[i].start(), ch[j].end()):
                        hit = j
                        break
                if hit is None:
                    i += 1
                    continue
                spans.append((ch[i].start(), ch[hit].end()))
                i = hit + 1
        has_first = has("first")
        if want_name:
            it = _ERASE_WORD_RE.finditer(flat)
            toks = list(it) if not masked else [t for t in it if not in_mask(t.start(), t.end())]
            low = [t.group(0).lower() for t in toks]
            if has_first:
                starts = []
                for w in low:
                    v = first_memo.get(w)
                    if v is None:
                        v = is_known("first", w) or (w.endswith("'s") and is_known("first", w[:-2]))
                        first_memo[w] = v
                    starts.append(v)
            else:
                starts = [True] * len(toks)
            cand = [i for i, v in enumerate(starts) if v]
            covered = set()

            def name_ok(kind, canon):
                return applies(kind, canon, linked)

            for i in cand:
                if i in covered:
                    continue
                hit = None
                for n in size_order:
                    j = i + n - 1
                    if j >= len(toks):
                        continue
                    if not all(gap_ok(flat[toks[k].end():toks[k + 1].start()], low[k])
                               for k in range(i, j)):
                        continue
                    raw = [t.group(0) for t in toks[i:j + 1]]
                    if not caps_ok(raw):
                        continue
                    words_ = low[i:j + 1]
                    if name_ok("name", " ".join(words_)):
                        hit = (j, toks[j].end())
                        break
                    # "Sarah Whitfield's order": the possessive is part of
                    # the last word to the tokenizer, and stays in the text.
                    if words_[-1].endswith("'s") and name_ok("name", " ".join(words_[:-1] + [words_[-1][:-2]])):
                        hit = (j, toks[j].end() - 2)
                        break
                if hit is None:
                    continue
                a, b = toks[i].start(), hit[1]
                # A bracket opened inside the name closes with it.
                if flat.count("(", a, b) > flat.count(")", a, b) and flat[b:b + 1] == ")":
                    b += 1
                spans.append((a, b))
                covered.update(range(i, hit[0] + 1))
            def name_word_next_to(k, j):
                """A capitalised word right beside token k (j = k-1 or k+1),
                with only spaces between: then k is part of another name."""
                if not (0 <= j < len(toks)) or not toks[j].group(0)[:1].isupper():
                    return False
                a, b = (toks[j].end(), toks[k].start()) if j < k else (toks[k].end(), toks[j].start())
                return bool(_ERASE_SPACE_GAP_RE.fullmatch(flat[a:b]))

            for i in cand:
                if i + 1 >= len(toks) or i in covered or i + 1 in covered:
                    continue
                if not _ERASE_REV_GAP_RE.fullmatch(flat[toks[i].end():toks[i + 1].start()]):
                    continue
                # "Cc: Tom Whitfield, Sarah Jones" is two other people, not
                # Sarah Whitfield surname first.
                if name_word_next_to(i, i - 1) or name_word_next_to(i + 1, i + 2):
                    continue
                if not caps_ok([toks[i].group(0), toks[i + 1].group(0)]):
                    continue
                if name_ok("rev", low[i] + " " + low[i + 1]):
                    spans.append((toks[i].start(), toks[i + 1].end()))
                    covered.update((i, i + 1))
        if not spans:
            return text
        spans.sort()
        merged = [list(spans[0])]
        for a, b in spans[1:]:
            if a <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        out, at = [], 0
        for a, b in merged:
            out.append(s[at:a])
            out.append("[erased]")
            at = b
        out.append(s[at:])
        return "".join(out)

    def knows(kind: str, canon: str) -> bool:
        return is_known(kind, _erase_norm(canon).strip().lower() if kind in ("req", "email") else canon)

    scrub.knows = knows
    return scrub


def _erase_sweep(d: dict, scrub, linked_people=(), apply: bool = True,
                 linked_orgs=(), skip_people=()) -> set:
    """Every free-text field the CRM keeps, through scrub: deal titles, lost
    reasons and comments, notes, changelogs and custom values; tasks; the
    notes, job titles, addresses and custom values of contacts and
    organisations; leads; and the lost-reason list. Names, addresses and
    numbers of live contacts are their own and are not touched. Returns the
    records it changed (or would, with apply=False) as (collection, id).
    Nothing is marked as edited here, so the import keeps updating them."""
    if scrub is None:
        return set()
    changed: set = set()
    linked_people = {str(x) for x in linked_people if x}
    linked_orgs = {str(x) for x in linked_orgs if x}
    skip_people = {str(x) for x in skip_people if x}

    def fix(rec, coll, rid, fields, notes=True, linked=False):
        hit = False
        for f in fields:
            v = rec.get(f)
            if isinstance(v, str) and v:
                nv = scrub(v, linked)
                if nv != v:
                    hit = True
                    if apply:
                        rec[f] = nv
        if notes and isinstance(rec.get("notes"), list):
            for n in rec["notes"]:
                if isinstance(n, dict) and isinstance(n.get("text"), str) and n["text"]:
                    nv = scrub(n["text"], linked)
                    if nv != n["text"]:
                        hit = True
                        if apply:
                            n["text"] = nv
        if isinstance(rec.get("custom"), dict):
            new = {}
            for ck, cv in rec["custom"].items():
                nv = scrub(cv, linked) if isinstance(cv, str) else cv
                if nv != cv:
                    hit = True
                new[ck] = nv
            if apply:
                rec["custom"] = new
        if hit:
            changed.add((coll, rid))

    for k, deal in (d.get("deals") or {}).items():
        lk = str(deal.get("person_id") or "") in linked_people
        fix(deal, "deals", k, ("title", "lost_reason", "lost_comment"), linked=lk)
        for ch in (deal.get("changelog") if isinstance(deal.get("changelog"), list) else []):
            if isinstance(ch, dict):
                for f in ("from", "to"):
                    if isinstance(ch.get(f), str) and ch[f]:
                        nv = scrub(ch[f], lk)
                        if nv != ch[f]:
                            changed.add(("deals", k))
                            if apply:
                                ch[f] = nv
    for k, act in (d.get("activities") or {}).items():
        lk = str(act.get("person_id") or "") in linked_people
        fix(act, "activities", k, ("subject", "note", "location"), notes=False, linked=lk)
    for k, rec in (d.get("persons") or {}).items():
        if k in skip_people:
            continue                    # about to go altogether
        fix(rec, "persons", k, ("job_title",))
    for k, rec in (d.get("orgs") or {}).items():
        # The organisation they were the contact for is theirs to clean,
        # whatever a namesake elsewhere is called.
        fix(rec, "orgs", k, ("address",), linked=k in linked_orgs)
    for k, rec in (d.get("leads") or {}).items():
        fix(rec, "leads", k, ("title",), linked=str(rec.get("person_id") or "") in linked_people)
    reasons = [r for r in (d.get("lost_reasons") or []) if isinstance(r, str)]
    kept = [r for r in reasons if "[erased]" not in r and scrub(r) == r]
    if len(kept) != len(reasons):
        changed.add(("lost_reasons", ""))
        if apply:
            d["lost_reasons"] = kept
    return changed
PRIVACY_LOG_PATH = os.environ.get("PRIVACY_LOG_PATH", "/data/privacy_log.json")


def _load_privacy_log() -> dict:
    """Every privacy request Shopify has sent, and what was done about it.

    Kept because the two halves of a redaction leave different evidence: the
    erased half leaves none by definition, and the retained half is retained on
    purpose. Without this there is no way to show a request was honoured."""
    d = jsonstore._load_json_store(PRIVACY_LOG_PATH, None, {"events": []})
    if not isinstance(d, dict):
        return {"events": []}
    if not isinstance(d.get("events"), list):
        # Only the broken list goes: the requests held for an admin and the
        # erasures owed must not go with it.
        d["events"] = []
    return d


def _privacy_note(topic: str, email: str, customer_id, detail: str) -> None:
    """Append one entry. Single-writer: load, mutate, write, no await between."""
    try:
        d = _load_privacy_log()
        d["events"].append({"at": datetime.now(timezone.utc).isoformat(),
                            "topic": topic, "email": (email or "").lower(),
                            "customer_id": str(customer_id or ""), "detail": detail})
        d["events"] = d["events"][-2000:]
        if jsonstore._store_writable(PRIVACY_LOG_PATH):
            jsonstore._write_json_store(PRIVACY_LOG_PATH, None, d)
    except Exception:
        logger.exception("privacy log write failed")


def _redact_shop() -> dict:
    """Erase the shop's data, 48 hours after an uninstall, as Shopify requires.

    A full backup is written to the volume FIRST. For a single-merchant app the
    "shop" is the merchant's own store, so this fires when they uninstall - and
    an uninstall during testing, or a reinstall, would otherwise take the
    dispatch and customs history with it. The erasure is real either way; the
    archive is what makes a misfire survivable rather than final.

    Credentials are not in the archive (the backup builder excludes them). The
    Gmail grant is dropped here: with the mailbox store empty, the sync
    would otherwise rebuild it from Gmail, every customer thread back inside
    a minute of the privacy log recording the erasure, and reconnecting is
    one sign-in by the master. The courier stays: it holds none of the
    shop's data, and its key is typed in, with nowhere to get it back from
    after a misfire.

    No archive, no erasure: {"wiped": 0, "refused": "archive"}. The caller
    has confirmed the uninstall with Shopify first (the webhook is signed
    with the app's secret, and a holder of that secret can post one), but a
    confirmation can still be wrong, and an erasure with no copy is the one
    mistake nobody can undo. The webhook answers so that Shopify sends it
    again, and each delivery tries the archive again."""
    kept = ""
    try:
        buf, added = backup._build_backup_zip()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        data_dir = os.path.dirname(scheduler.SCHEDULE_PATH) or "/data"
        kept = os.path.join(data_dir, f"pre-redact-backup-{stamp}.zip")
        os.makedirs(data_dir, exist_ok=True)
        with open(kept, "wb") as fh:
            fh.write(buf.getvalue())
        logger.warning("shop/redact: archived %d files to %s before erasing", added, kept)
    except Exception:
        logger.exception("shop/redact: could not archive, so nothing was erased")
        _privacy_note("shop/redact", "", "",
                      "not erased yet: the archive taken first could not be written")
        return {"wiped": 0, "archive": "", "refused": "archive"}
    wiped = 0
    stores = (salesdesk.CRM_PATH, mail.MAILBOX_PATH, desk.DISPATCH_STATE_PATH, liability.CHASE_LOG_PATH,
              desk.COLLECTIONS_PATH, desk.CUSTOMS_MEMORY_PATH, production.PRODUCTION_STATE_PATH,
              production.PRODUCTION_ARCHIVE_PATH, fileserver.FILES_PATH)
    for path in stores:
        try:
            if os.path.isfile(path):
                os.remove(path)
                wiped += 1
        except Exception:
            logger.exception("shop/redact: could not remove %s", path)
    # The memory copies go with the files. Left alone, _load_mail() kept
    # serving the erased threads and the mail loop wrote every one of them
    # back to disk inside a minute; the Files cache did the same on its next
    # tick, so the erasure the privacy log recorded had not happened.
    jsonstore._drop_memory_stores(set(stores))
    for path in stores:
        jsonstore._forget_store(path)
    try:
        google_mail.disconnect(google_mail.SALES)
    except Exception:
        logger.exception("shop/redact: could not drop the mailbox grant")
    _privacy_note("shop/redact", "", "",
                  f"erased {wiped} store(s); archive at {kept or '(none - see logs)'}; "
                  f"the archive is deleted after {REDACT_ARCHIVE_DAYS} days, and weekly "
                  f"snapshots are kept for {backup.BACKUP_KEEP} weeks")
    return {"wiped": wiped, "archive": kept}


def _redact_customer(email: str, customer_id="", retry: bool = False,
                     requested_at: Optional[str] = None) -> dict:
    """Erase what we hold about a person by choice; keep what we hold by law.

    The split is the whole design. CRM records and email threads are
    relationship data with no retention obligation behind them, so they go.
    Dispatch bookings, customs declarations and the made-order archive are
    records HMRC can ask for within six years - erasing those would trade one
    exposure for another, so they stay and carry a note instead. UK GDPR
    Art. 17(3)(b) is what makes the second half lawful, and the note is what
    makes it evidenced."""
    addr = str(email or "").strip().lower()
    if not addr:
        return {"erased": 0, "retained": 0}
    erased = retained = 0
    # A store is erased when its write lands, not before; an unreadable one
    # is not erased at all (its loader hands back an empty default, and
    # "erased 0" was logged as the compliance record). Failures are said, and
    # kept for the hourly retry.
    failed: list = []
    # The person lives in more places than their own contact: the deals and
    # leads filed against them (a website enquiry becomes a deal whose title,
    # notes and phone number are theirs) and the enquiry email, which the
    # storefront sends from the shop's OWN address with theirs only inside
    # it. All of it is relationship data, and all of it goes.
    threads_to_erase: set = set()
    # Their address as a whole address: "sales@firm.co" must not match
    # "sales@firm.co.uk", nor "jo@x.com" match "bjo@x.com".
    names_them = re.compile(r"(?<![\w.+-])" + re.escape(addr) + r"(?![\w-]|\.\w)", re.I)
    their_words: set = {addr}           # what is scrubbed from a record that stays

    # --- erased: the CRM -----------------------------------------------------
    before = erased
    try:
        if salesdesk.CRM_PATH in jsonstore._poisoned_stores:
            raise RuntimeError("the CRM file could not be read")
        d = salesdesk._load_crm()
        pids = set()
        erased_pd: set = set()          # their Pipedrive ids, so the import knows them
        orgs_touched: set = set()
        # Them, and a duplicate of them under another address (same name,
        # and a shared address or number): the one rule, shared with the
        # preview an admin decides on.
        mine, _dupes = _redact_people(d, addr)
        for pid in mine:
            # TOMBSTONED, not just popped. The Pipedrive importer refuses to
            # recreate a contact it has been told is deleted, and it already
            # did that for contacts deleted by hand. An erasure that the next
            # import quietly undid was worse than none: the privacy log said
            # the person was erased, and they were back within the hour.
            rec = d["persons"][pid]
            rec["id"] = pid           # the tombstone pops by the record's own id
            if rec.get("mail_thread_id"):
                threads_to_erase.add(str(rec["mail_thread_id"]))
            their_words.update(str(x).strip() for x in _erase_words_of(rec) if str(x or "").strip())
            if rec.get("org_id"):
                orgs_touched.add(str(rec["org_id"]))
            erased_pd.update(str(x) for x in [rec.get("pd_id")] + list(rec.get("pd_merged_ids") or []) if x)
            salesdesk._crm_tombstone_contact(d, "persons", rec)
            pids.add(pid)
            erased += 1
        # Everything that stays is swept for them, with their own former
        # records (still linked, so still counted as theirs whatever a
        # namesake is called) swept before they are cut loose. Nothing is
        # marked as edited here: the import keeps updating these records,
        # and takes them out again each time.
        alive = _erase_alive((d.get("persons") or {}).values(),
                             [o.get("name") for o in (d.get("orgs") or {}).values()])
        _erase_sweep(d, _erase_scrubber(words=their_words, alive=alive), linked_people=pids,
                     linked_orgs=orgs_touched)
        n, threads = salesdesk._crm_erase_links(d, pids, orgs_touched)
        erased += n
        threads_to_erase |= threads
        # Leads carry person_id, not an email, so matching their email alone
        # never erased one.
        for lid in [k for k, v in (d.get("leads") or {}).items()
                    if str(v.get("email") or "").strip().lower() == addr]:
            if d["leads"][lid].get("mail_thread_id"):
                threads_to_erase.add(str(d["leads"][lid]["mail_thread_id"]))
            d["leads"].pop(lid, None); erased += 1
        # Remembered as keyed hashes only, so every later import can take
        # them out of the organisation deals Pipedrive keeps updating, and can
        # refuse to bring them back as a contact, even one this CRM never held:
        # the address the erasure was asked for is enough.
        _erase_remember(d, their_words, erased_pd, request=addr, shared=alive)
        salesdesk._write_crm(d)
    except Exception:
        logger.exception("redact: CRM")
        jsonstore._forget_store(salesdesk.CRM_PATH)   # a half-made change must not be served
        erased = before
        failed.append("the CRM")

    # --- erased: the mailbox -------------------------------------------------
    before = erased
    try:
        if mail.MAILBOX_PATH in jsonstore._poisoned_stores:
            raise RuntimeError("the mailbox file could not be read")
        store = mail._load_mail()
        threads = store.get("threads") or {}

        def theirs(tid, t):
            """Their conversation: they wrote it, or it is their website
            enquiry (the storefront sends it from the shop's own address, with
            theirs inside and as its Reply-To). Only these are erased and
            blocked; a thread someone ELSE wrote that merely mentions them is
            that person's email, and has the mention scrubbed instead."""
            if tid in threads_to_erase or str(t.get("from_email") or "").strip().lower() == addr:
                return True
            if t.get("enquiry") and names_them.search(str(t.get("snippet") or "")):
                return True
            for m in (t.get("messages") or []):
                if str(m.get("from_email") or "").strip().lower() == addr \
                        or names_them.search(str(m.get("reply_to") or "")):
                    return True
            return False
        for tid in [k for k, t in threads.items() if theirs(k, t)]:
            threads.pop(tid, None); erased += 1
            threads_to_erase.add(tid)
        for t in threads.values():
            if names_them.search(str(t.get("snippet") or "")):
                t["snippet"] = names_them.sub("[erased]", str(t.get("snippet") or ""))
            hx = mail._mail_erased_rx({addr}, header=True)
            for m in (t.get("messages") or []):
                for f in ("snippet", "to", "cc", "reply_to"):
                    if names_them.search(str(m.get(f) or "")):
                        m[f] = (names_them if f == "snippet" else hx).sub("[erased]", str(m.get(f) or ""))
        # And never fetched back: the sync refuses a thread by its sender,
        # and an enquiry's sender is the shop itself.
        gone_t = [x for x in (store.get("redacted_threads") or []) if isinstance(x, str)]
        store["redacted_threads"] = (gone_t + sorted(threads_to_erase - set(gone_t)))[-5000:]
        # The same anti-resurrection rule for the mailbox. Gmail is still
        # holding the correspondence and the sync looks two years back, so a
        # deleted thread was simply "not in threads" and was fetched again on
        # the next pass, minutes later.
        gone = [a for a in (store.get("redacted") or []) if isinstance(a, str)]
        if addr not in gone:
            gone.append(addr)
        store["redacted"] = gone[-5000:]
        mail._write_mail(store)
    except Exception:
        logger.exception("redact: mailbox")
        jsonstore._drop_memory_stores({mail.MAILBOX_PATH})   # a half-made change must not be served
        erased = before
        failed.append("the mailbox")

    # --- retained, and noted -------------------------------------------------
    stamp = requested_at or datetime.now(timezone.utc).isoformat()
    try:
        orders = desk._load_dispatch()
        for rec in orders.values():
            if str(rec.get("email") or "").strip().lower() == addr:
                # When the request came in: the hourly retry of a store that
                # refused must not move it to the time of the retry.
                rec.setdefault("redacted_request_at", stamp)
                retained += 1
        desk._write_dispatch(orders)
    except Exception:
        logger.exception("redact: dispatch")
        jsonstore._forget_store(desk.DISPATCH_STATE_PATH)   # a half-made change must not be served

    # A retry that fails again adds nothing to the record: the first attempt
    # already said what is owed, and an hourly line would bury the log.
    if not (retry and failed):
        _privacy_note("customers/redact", addr, customer_id,
                  ("retried: " if retry else "")
                  + f"erased {erased} relationship record(s); "
                  f"retained {retained} record(s) held under a legal obligation"
                  + ("; NOT YET ERASED from " + " and ".join(failed)
                     + " (that store could not be read or written); retried hourly"
                     if failed else ""))
    if failed or retry:
        _redact_pending_set(addr, customer_id, failed)
    return {"erased": erased, "retained": retained, "failed": failed}


def _redact_pending_set(addr: str, customer_id, failed: list) -> None:
    """Remember an erasure that did not complete, or forget one that has."""
    try:
        d = _load_privacy_log()
        pend = [p for p in (d.get("pending") or []) if isinstance(p, dict) and p.get("email") != addr]
        if failed:
            pend.append({"email": addr, "customer_id": str(customer_id or ""),
                         "stores": failed, "at": datetime.now(timezone.utc).isoformat()})
        if pend != (d.get("pending") or []):
            d["pending"] = pend[-500:]
            if jsonstore._store_writable(PRIVACY_LOG_PATH):
                jsonstore._write_json_store(PRIVACY_LOG_PATH, None, d)
    except Exception:
        logger.exception("privacy log: could not record a pending erasure")


# A customers/redact is signed with the app's secret, and so is every forgery
# by whoever holds it: before this, one post erased any customer's CRM records
# and email threads on the spot. Nothing checkable separates a forgery from
# Shopify's own request (Shopify may or may not still have the customer, and
# many people in the CRM were never Shopify customers at all), and an erasure
# cannot be undone. So each request waits for an admin, in Settings, Privacy
# requests, with what Reactor can tell them beside it: whether Shopify still
# has a customer with any address the erasure would take, how far it reaches
# (worked out when the list is shown, and checked again at the click), and
# whether the same request was stopped before. Shopify sends a genuine one
# ten days after the merchant asks, and allows thirty days to act on it; an
# admin is told at once (in the app and by email, neither naming the person)
# and reminded daily as the thirty days run out. Data requests
# (customers/data_request) wait in the same place until marked answered.
REDACT_DEADLINE_DAYS = 30
REDACT_REMIND_DAYS = 20        # from here on, a daily reminder
REDACT_HELD_MAX = 2000         # more waiting than this is a flood: sent back, and said
REDACT_ASKS_MAX = 1000
REDACT_MAIL_HOURS = 1
REDACT_CHECKS_PER_TICK = 50
REDACT_LIST_MAX = 100          # rows worked out and shown at once
_redact_hold_said: dict = {}
_PRIVACY_ALERT = "Privacy requests are waiting for an admin in Settings"


def _plist(d: dict, key: str) -> list:
    """One of the privacy log's lists, as a list of records whatever was
    stored: a hand-edited or damaged value must not throw away a request."""
    v = d.get(key) if isinstance(d, dict) else None
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def _held_requests(d: Optional[dict] = None) -> list:
    d = _load_privacy_log() if d is None else d
    return [h for h in _plist(d, "held") if h.get("id") and h.get("email")]


def _open_asks(d: Optional[dict] = None) -> list:
    d = _load_privacy_log() if d is None else d
    return [a for a in _plist(d, "asks") if a.get("id") and not a.get("answered")]


def _redact_hold_write(change, key: str = "held") -> bool:
    """Apply change(list) -> list to one list in the privacy log and write it;
    False when it cannot be written (an unreadable log, a full disk)."""
    try:
        d = _load_privacy_log()
        if PRIVACY_LOG_PATH in jsonstore._poisoned_stores or not jsonstore._store_writable(PRIVACY_LOG_PATH):
            return False
        cur = _held_requests(d) if key == "held" else _plist(d, key)
        d[key] = change(cur)
        jsonstore._write_json_store(PRIVACY_LOG_PATH, None, d)
        return True
    except Exception:
        logger.exception("privacy requests: the privacy log could not be written")
        return False


def _privacy_decision(email: str, customer_id, action: str, by: str) -> None:
    """The record of what an admin decided, kept apart from the event log so a
    stream of signed requests cannot push it out."""
    at = datetime.now(timezone.utc).isoformat()
    _redact_hold_write(lambda xs: (xs + [{"at": at, "email": email, "customer_id": str(customer_id or ""),
                                           "action": action, "by": by}])[-5000:], key="decisions")


def _redact_index(d: dict) -> dict:
    """Every CRM person's names, addresses and numbers, worked out once: the
    duplicate rule compares each against everyone taken, and working them out
    again per comparison made a list of waiting requests take minutes."""
    return {k: _erase_split(_erase_words_of(v)) for k, v in (d.get("persons") or {}).items()}


def _redact_people(d: dict, addr: str, index: Optional[dict] = None) -> tuple:
    """(everyone an erasure for this address takes, those it takes only as a
    likely duplicate of them): the CRM people with the address, and anyone
    with the same name and a shared address or number. _redact_customer and
    the Settings preview both read this, so what an admin is shown is what
    goes (the page's figure is checked again at the click)."""
    persons = d.get("persons") or {}
    mine = [k for k, v in persons.items() if isinstance(v, dict) and (
            addr in {str(e).strip().lower() for e in _erase_list(v.get("emails"))}
            or str(v.get("email") or "").strip().lower() == addr)]
    direct = set(mine)
    if not mine:
        return mine, []
    idx = index if index is not None else _redact_index(d)
    for k in persons:
        # Against everyone taken so far, as the erasure always did (the same
        # rule as _erase_same_person, on words worked out once).
        if k in mine:
            continue
        kn, ki = idx.get(k) or (set(), set())
        if kn and ki and any((kn & idx[m][0]) and (ki & idx[m][1]) for m in mine if m in idx):
            mine.append(k)
    return mine, [k for k in mine if k not in direct]


def _redact_scope(addr: str, d: Optional[dict] = None, index: Optional[dict] = None) -> dict:
    """How far an erasure for this address reaches now, the addresses its
    contacts hold, and 'key', a fingerprint of exactly who it takes, which the
    page sends back with Erase ({'unreadable': True} when the CRM cannot be
    read). A caller listing many passes the CRM and its index in once."""
    try:
        if d is None:
            if salesdesk.CRM_PATH in jsonstore._poisoned_stores:
                return {"unreadable": True}
            d = salesdesk._load_crm()
        if salesdesk.CRM_PATH in jsonstore._poisoned_stores:
            return {"unreadable": True}
        mine, dupes = _redact_people(d, addr, index)
        addrs = []
        for k in mine:
            p = (d.get("persons") or {}).get(k) or {}
            for e in list(p.get("emails") or []) + [p.get("email")]:
                e = str(e or "").strip().lower()
                if e and e not in addrs:
                    addrs.append(e)
        others = [a for a in addrs if a != addr]
        key = hashlib.sha256(("|".join(sorted(mine)) + "#" + addr).encode()).hexdigest()[:16]
        return {"contacts": len(mine), "likely_duplicates": len(dupes), "other_addresses": len(others),
                "addresses": [addr] + others, "key": key}
    except Exception:
        logger.exception("customers/redact: the preview could not be read")
        return {"unreadable": True}


def _redact_hold(email: str, customer_id="") -> Optional[dict]:
    """Hold one request for an admin; the held entry ('new' True when this
    call made it), {} when it names nobody we could hold anything about, or
    None when it could not be recorded."""
    addr = str(email or "").strip().lower()
    if not addr or "@" not in addr or len(addr) > 254:
        _privacy_note("customers/redact", addr[:254], customer_id,
                      "no usable email address given, and nothing here is kept by a customer id alone")
        return {}
    d = _load_privacy_log()
    held = _held_requests(d)
    twin = next((h for h in held if h.get("email") == addr), None)
    if twin is not None:
        return {**twin, "new": False}      # the same person asked again: one hold
    if len(held) >= REDACT_HELD_MAX:
        _privacy_note("customers/redact", addr, customer_id,
                      f"not held: more than {REDACT_HELD_MAX} requests already waiting; sent back for Shopify to retry")
        return None
    stopped = next((x for x in reversed(_plist(d, "stopped")) if x.get("email") == addr), None)
    entry = {"id": secrets.token_hex(5), "email": addr, "customer_id": str(customer_id or "")[:40],
             "received": datetime.now(timezone.utc).isoformat(), "shopify": "unknown", "checked_at": "",
             "mailed": False, "stopped_before": (stopped or {}).get("at") or ""}
    if not _redact_hold_write(lambda hs: hs + [entry]):
        return None
    _privacy_note("customers/redact", addr, customer_id, "held for an admin to erase or stop")
    _privacy_alert(force=True)
    return {**entry, "new": True}


def _privacy_alert(force: bool = False) -> None:
    """The in-app notice that something waits in Settings. Put back once a
    day while anything does, as any account can dismiss the banner."""
    try:
        if not (_held_requests() or _open_asks()):
            return
        live = any(isinstance(a, dict) and a.get("metric") == _PRIVACY_ALERT and a.get("status") == "new"
                   for a in scheduler._load_alerts())
        if live:
            return
        last = _redact_hold_said.get("alert")
        if not force and last is not None and time.monotonic() - last < 24 * 3600:
            return
        _redact_hold_said["alert"] = time.monotonic()
        scheduler._add_alerts([{"tab": "settings", "tab_label": "Privacy", "metric": _PRIVACY_ALERT, "pct": None}])
    except Exception:
        logger.exception("privacy requests: the alert could not be added")


def _redact_unrecorded() -> None:
    """A request that could not be held is sent back for Shopify to retry;
    the master hears, at most once an hour, that the log needs attention."""
    now = time.monotonic()
    last = _redact_hold_said.get("unrecorded")
    if last is not None and now - last < 3600:
        return
    _redact_hold_said["unrecorded"] = now
    background.spawn(scheduler._send_alert_email(
        "Reactor: could not record a customer erasure request",
        ["Shopify asked Reactor to erase a customer's records, but Reactor could not record the",
         "request, so it was sent back for Shopify to try again (it does, for a few hours). Check",
         "the server's storage, and deal with the requests waiting in Settings, under Privacy",
         "requests, if there are many."]))


def _redact_hold_set(hid: str, **changes) -> None:
    _redact_hold_write(lambda held: [({**h, **changes} if h["id"] == hid else h) for h in held])


def _redact_hold_drop(hid: str) -> Optional[dict]:
    """Take one request off the list; the entry taken, or None when it had
    already gone (another admin, a moment ago)."""
    taken: list = []

    def change(held):
        taken.extend(h for h in held if h["id"] == hid)
        return [h for h in held if h["id"] != hid]
    if not _redact_hold_write(change):
        return None
    return taken[0] if taken else None


async def _customer_state(h: dict, addresses: Optional[list] = None) -> str:
    """'live' when Shopify still has a customer with this id or with any of
    the addresses the erasure would take, 'gone' when it has none of them,
    'unknown' when it could not be asked about all of them."""
    if shopify._customer_checker is None:
        return "unknown"
    addrs = [a for a in (addresses or [h.get("email")]) if a][:10]
    seen = []
    for k, a in enumerate(addrs):
        try:
            st = await asyncio.wait_for(
                shopify._customer_checker(str(h.get("customer_id") or "") if k == 0 else "", str(a)), 20)
        except Exception:
            logger.warning("customers/redact: the customer check did not answer")
            st = "unknown"
        if st == "live":
            return "live"
        seen.append(st)
    return "gone" if seen and all(x == "gone" for x in seen) else "unknown"


def _privacy_due(received: str) -> Optional[datetime]:
    try:
        at = datetime.fromisoformat(str(received))
    except (ValueError, TypeError):
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)   # a hand-edited date: read as UTC, not a crash
    return at + timedelta(days=REDACT_DEADLINE_DAYS)


def _privacy_mail(reminder: bool = False) -> None:
    """Tell the master what waits: when a request has not been mailed yet (at
    most once every REDACT_MAIL_HOURS), or as a reminder. It names nobody: an
    email outlives the erasure it announces. A request is marked mailed only
    once the email has gone."""
    held, asks = _held_requests(), _open_asks()
    if not (held or asks):
        return
    fresh = any(not x.get("mailed") for x in held + asks)
    if not (fresh or reminder):
        return
    now = time.monotonic()
    last = _redact_hold_said.get("mail")
    if last is not None and now - last < REDACT_MAIL_HOURS * 3600:
        return
    _redact_hold_said["mail"] = now
    dues = [d for d in (_privacy_due(x.get("received") or "") for x in held + asks) if d]
    first = min(dues) if dues else None
    parts = []
    if held:
        parts.append("one customer erasure request" if len(held) == 1 else f"{len(held)} customer erasure requests")
    if asks:
        parts.append("one request for a customer's data" if len(asks) == 1 else f"{len(asks)} requests for customers' data")
    lines = [" and ".join(parts)[0].upper() + " and ".join(parts)[1:]
             + (" is" if len(held) + len(asks) == 1 else " are")
             + " waiting for an admin in Reactor, in Settings, under Privacy requests."]
    if first is not None:
        day = f"{first.day} {first:%b %Y}"
        lines.append(("Shopify's thirty days for the oldest ran out on " if first < datetime.now(timezone.utc)
                      else "Shopify allows thirty days, and the oldest is due by ") + day + ".")
    if held:
        lines += ["", "Shopify sends an erasure request when you erase a customer in Shopify. If nobody here",
                  "did, stop it: only someone holding the app's secret can send one Shopify did not."]
    held_ids, ask_ids = {h["id"] for h in held}, {a["id"] for a in asks}
    subject = "Reactor: privacy requests " + ("still waiting" if reminder else "waiting")
    background.spawn(_privacy_mail_send(subject, lines, held_ids, ask_ids))


async def _privacy_mail_send(subject: str, lines: list, held_ids: set, ask_ids: set) -> None:
    try:
        sent = await scheduler._send_alert_email(subject, lines)
    except Exception:
        logger.exception("privacy requests: the email could not be sent")
        sent = False
    if not sent:
        _redact_hold_said.pop("mail", None)          # the next hour tries again
        return
    _redact_hold_write(lambda hs: [({**h, "mailed": True} if h["id"] in held_ids else h) for h in hs])
    _redact_hold_write(lambda xs: [({**a, "mailed": True} if a.get("id") in ask_ids else a) for a in xs], key="asks")


_redact_checks_running = {"n": 0}


async def _redact_hold_check(hid: str) -> None:
    """After a request is held: ask Shopify about every address the erasure
    would take, for the admin deciding, and tell the master. A few at a time:
    a flood of requests would otherwise spend the store's allowance of
    calls, and the hourly pass checks the rest."""
    h = next((x for x in _held_requests() if x["id"] == hid), None)
    if h is not None and _redact_checks_running["n"] < 3:
        _redact_checks_running["n"] += 1
        try:
            scope = _redact_scope(h["email"])
            st = await _customer_state(h, scope.get("addresses"))
            if st != "unknown":
                _redact_hold_set(hid, shopify=st, checked_at=datetime.now(timezone.utc).isoformat())
        finally:
            _redact_checks_running["n"] -= 1
    _privacy_mail()


async def _redact_hold_due(check: bool = True) -> int:
    """Hourly: refresh what Shopify says about the waiting customers (oldest
    checked first, REDACT_CHECKS_PER_TICK at a time, and not while Shopify is
    down; an answer that could not be had keeps the last one), mail anything
    not yet mailed, keep the in-app notice up, and remind daily once the
    thirty days are running out. Nothing is erased here: only an admin
    erases. How many requests wait."""
    now = datetime.now(timezone.utc)
    _load_privacy_log()
    if PRIVACY_LOG_PATH in jsonstore._poisoned_stores:
        # Nothing waiting can be seen while the log cannot be read: said
        # once a day rather than shown as "Nothing waiting".
        last = _redact_hold_said.get("unreadable")
        if last is None or time.monotonic() - last >= 24 * 3600:
            _redact_hold_said["unreadable"] = time.monotonic()
            background.spawn(scheduler._send_alert_email(
                "Reactor: the privacy requests cannot be read",
                ["Reactor keeps the customer erasure and data requests Shopify sends in a file it cannot",
                 "read just now, so none of them can be shown or reminded about. Check the server's",
                 "storage, or restore the latest backup."]))
        return 0
    crm = None if salesdesk.CRM_PATH in jsonstore._poisoned_stores else salesdesk._load_crm()
    index = _redact_index(crm) if crm is not None and salesdesk.CRM_PATH not in jsonstore._poisoned_stores else None
    if check:
        order = sorted(_held_requests(), key=lambda h: str(h.get("tried_at") or ""))
        for h in order[:REDACT_CHECKS_PER_TICK]:
            scope = _redact_scope(h["email"], crm, index) if index is not None else {}
            st = await _customer_state(h, scope.get("addresses"))
            changes = {"tried_at": now.isoformat()}
            if st != "unknown":
                changes.update(shopify=st, checked_at=now.isoformat())
            if any(x["id"] == h["id"] for x in _held_requests()):
                _redact_hold_set(h["id"], **changes)
    _privacy_alert()
    late = any((_privacy_due(x.get("received") or "") or now) - now
               < timedelta(days=REDACT_DEADLINE_DAYS - REDACT_REMIND_DAYS)
               for x in _held_requests() + _open_asks())
    if late:
        last = _redact_hold_said.get("remind")
        if last is None or time.monotonic() - last >= 24 * 3600:
            _redact_hold_said["remind"] = time.monotonic()
            _redact_hold_said.pop("mail", None)
            _privacy_alert(force=True)
            _privacy_mail(reminder=True)
            return len(_held_requests())
    _privacy_mail()
    return len(_held_requests())


def _redact_hold_erase(h: dict, how: str, by: str = "") -> dict:
    out = _redact_customer(h["email"], h.get("customer_id") or "", requested_at=h.get("received"))
    _privacy_note("customers/redact", h["email"], h.get("customer_id") or "", how)
    _privacy_decision(h["email"], h.get("customer_id"), "erased", by)
    return out


def _redact_hold_stop(h: dict, who_name: str) -> None:
    """Remember a stopped request, so the same one sent again says so."""
    at = datetime.now(timezone.utc).isoformat()
    _redact_hold_write(lambda st: (st + [{"email": h["email"], "at": at, "by": who_name}])[-500:], key="stopped")
    _privacy_note("customers/redact", h["email"], h.get("customer_id") or "",
                  "stopped by " + who_name + ": not asked for, so nothing was erased")
    _privacy_decision(h["email"], h.get("customer_id"), "stopped", who_name)


def _redact_retry_pending() -> int:
    """The hourly retry of erasures a store refused; how many are still owed.
    Shopify is answered 200 once and never asks again, so this is the only
    second attempt there is."""
    try:
        pend = list(_load_privacy_log().get("pending") or [])
    except Exception:
        return 0
    left = 0
    for p in pend:
        if isinstance(p, dict) and p.get("email"):
            out = _redact_customer(p["email"], p.get("customer_id") or "", retry=True)
            left += 1 if out.get("failed") else 0
    return left


# ---------------------------------------------------------------------------
# The pre-redact archive: the undo for an uninstall that was a mistake, kept
# thirty days and then deleted.
# ---------------------------------------------------------------------------


REDACT_ARCHIVE_DAYS = _env_num(int, os.environ.get("REDACT_ARCHIVE_DAYS", "30"), "30", "REDACT_ARCHIVE_DAYS")


def _redact_archive_reap(now: Optional[float] = None) -> int:
    """The pre-redact archive is the undo for an uninstall that was a mistake.
    It is a COMPLETE copy of the store's data, and nothing deleted it, so an
    erasure obligation was met by moving the data into a zip and keeping it
    forever. Thirty days is long enough to notice a misfire."""
    now = now if now is not None else time.time()
    data_dir = os.path.dirname(scheduler.SCHEDULE_PATH) or "/data"
    gone = 0
    try:
        names = os.listdir(data_dir)
    except OSError:
        return 0
    for n in names:
        if not (n.startswith("pre-redact-backup-") and n.endswith(".zip")):
            continue
        p = os.path.join(data_dir, n)
        try:
            if now - os.path.getmtime(p) > REDACT_ARCHIVE_DAYS * 86400:
                os.remove(p)
                gone += 1
                logger.warning("privacy: removed the pre-redact archive %s (older than %d days)",
                               n, REDACT_ARCHIVE_DAYS)
        except OSError:
            continue
    if gone:
        _privacy_note("archive/expire", "", "",
                      f"deleted {gone} pre-redact archive(s) older than {REDACT_ARCHIVE_DAYS} days")
    return gone


# ---------------------------------------------------------------------------
# Shop redaction owed after an uninstall, the requests held for an admin, the
# live privacy records a restore keeps, and the webhook signature check.
# ---------------------------------------------------------------------------
# How long Reactor's own reads of the store must already have been refused
# before a shop/redact may erase. A genuine one comes 48 hours after the
# uninstall, by which time the watchdog (three failed hourly probes) has
# recorded the outage for at least 45; a secret being rotated, or an app made
# to uninstall itself by whoever holds the secret, has no such history yet,
# and the outage email has said "reinstall it" for most of those hours.
SHOP_REDACT_DOWN_HOURS = 40
# A request that could not be acted on yet is owed, kept in the privacy log
# and tried again every hour, so a Shopify outage at the wrong moment cannot
# lose it; the webhook answers 200 once it is recorded.
SHOP_REDACT_MAIL_HOURS = 6
_shop_redact_said: dict = {}   # outcome -> monotonic time it was last emailed / logged


def _shop_owed_set(value: Optional[dict]) -> bool:
    """Record, or clear, the one shop/redact still owed (in the privacy log,
    which survives a restart). False when it could not be written: an
    unreadable log, or a full disk."""
    try:
        d = _load_privacy_log()
        if value is None:
            d.pop("shop_owed", None)
        else:
            d["shop_owed"] = value
        if not jsonstore._store_writable(PRIVACY_LOG_PATH):
            return False
        jsonstore._write_json_store(PRIVACY_LOG_PATH, None, d)
        return True
    except Exception:
        logger.exception("shop/redact: the owed record could not be written")
        return False


async def _shop_redact_attempt(down_since) -> str:
    """One try at an owed shop/redact: 'installed', 'unknown', 'recent',
    'archive' or 'erased'. Erases only when Shopify refuses the app's
    credential AND the app's own reads have been refused for
    SHOP_REDACT_DOWN_HOURS AND the archive was written first."""
    state = "unknown"
    if shopify._install_checker is not None:
        try:
            state = await shopify._install_checker()
        except Exception:
            logger.exception("shop/redact: the install check failed")
    if state == "installed":
        return "installed"
    if state != "gone":
        return "unknown"
    try:
        since = datetime.fromisoformat(str(down_since or ""))
        if datetime.now(timezone.utc) - since < timedelta(hours=SHOP_REDACT_DOWN_HOURS):
            return "recent"
    except (ValueError, TypeError):
        return "recent"
    return "archive" if _redact_shop().get("refused") else "erased"


_SHOP_REDACT_WORDS = {
    "installed": ("refused: the app is still installed, so this did not follow an uninstall; nothing was erased",
                  "Reactor: refused a request to erase the shop's data",
                  ["A signed request asked Reactor to erase the shop's data, but Shopify says the app",
                   "is still installed, so it did not come from an uninstall. Nothing was erased.",
                   "", "Only someone holding the app's secret can sign one. Change the app's secret,",
                   "and give Reactor the new one straight away."]),
    "recent": ("waiting: Shopify refuses the app's access, but not yet for long enough to be an uninstall "
               "two days old; nothing erased, tried again every hour",
               "Reactor: holding a request to erase the shop's data",
               ["Shopify asked Reactor to erase the shop's data, which it does two days after the app",
                "is uninstalled. Shopify is refusing Reactor's access to the store, but not for long",
                "enough yet, so nothing is erased. Reactor checks every hour, and erases only once the",
                "store has been out of its reach for most of two days.",
                "", "If the app should still be installed, reinstall it now. If its secret was just",
                "changed, give Reactor the new one."]),
    "unknown": ("waiting: Shopify could not be asked whether the app is still installed; nothing erased, "
                "tried again every hour",
                "Reactor: holding a request to erase the shop's data",
                ["Shopify asked Reactor to erase the shop's data, but Reactor could not ask Shopify",
                 "whether the app is still installed, so nothing is erased yet. It asks again every hour."]),
    "unrecorded": ("not recorded: the privacy log could not be written; nothing erased, Shopify asked to send it again",
                   "Reactor: could not record a request to erase the shop's data",
                   ["Shopify asked Reactor to erase the shop's data, but Reactor could not record the",
                    "request, so nothing was erased and Shopify was asked to send it again. Check the",
                    "server's storage: until it can be written, the request is not kept."]),
    "archive": ("waiting: the archive taken first could not be written; nothing erased, tried again every hour",
                "Reactor: the shop's data was not erased yet",
                ["Shopify asked for the shop's data to be erased after the app was uninstalled, but the",
                 "archive taken first could not be written, so nothing was erased. Reactor tries again",
                 "every hour; check the server's storage."]),
}


def _shop_redact_settle(outcome: str) -> None:
    """Clear what was owed, or keep it, and say so: in the privacy log and by
    email, each at most once per outcome every SHOP_REDACT_MAIL_HOURS, so a
    stream of signed forgeries can neither flood the log nor spend the email
    allowance the real warnings need."""
    if outcome in ("installed", "erased"):
        _shop_owed_set(None)
    if outcome == "erased":
        return      # _redact_shop wrote its own record
    words = _SHOP_REDACT_WORDS.get(outcome) or _SHOP_REDACT_WORDS["unknown"]
    now = time.monotonic()
    last = _shop_redact_said.get(outcome)
    if last is not None and now - last < SHOP_REDACT_MAIL_HOURS * 3600:
        logger.warning("shop/redact: %s (said already)", outcome)
        return
    _shop_redact_said[outcome] = now
    logger.warning("shop/redact: %s", outcome)
    _privacy_note("shop/redact", "", "", words[0])
    background.spawn(scheduler._send_alert_email(words[1], words[2]))


async def _shop_redact_checked(delivery: str) -> Response:
    """shop/redact, erased only once Shopify has confirmed the uninstall.

    The webhook is signed with the app's secret, and so is every forgery by
    anyone holding it: before this, one forged post erased nine stores and
    disconnected both mailboxes. A genuine one arrives 48 hours after an
    uninstall, when Shopify has long stopped honouring the app's credential,
    so the app records the request as owed, then asks Shopify:

      still installed  refused, and the master is emailed: a signed request
                       that did not follow an uninstall means the secret is
                       out; nothing is owed
      not installed    archived, then erased, but only when the app's own
                       reads have been refused for SHOP_REDACT_DOWN_HOURS
                       and the archive was written
      anything else    owed, said, and tried again every hour by the
                       watchdog (_shop_redact_retry), which a Shopify outage,
                       a restart or a full disk cannot lose

    Answered 200 once the request is recorded: the record, not Shopify's few
    retries, is what makes sure it is honoured. When it cannot be recorded
    (an unreadable privacy log, a full disk) and was not settled at once, it
    is answered 503 with the delivery forgotten, so Shopify sends it again."""
    recorded = False
    try:
        d = _load_privacy_log()
        recorded = isinstance(d.get("shop_owed"), dict) and PRIVACY_LOG_PATH not in jsonstore._poisoned_stores
        if not recorded:
            recorded = _shop_owed_set({"since": datetime.now(timezone.utc).isoformat(), "tries": 0,
                                       "delivery": str(delivery or "")[:80]})
        w = scheduler._load_watch()
        outcome = await _shop_redact_attempt((w if isinstance(w, dict) else {}).get("shopify_down"))
    except Exception:
        logger.exception("shop/redact: the check failed")
        outcome = "unknown"
    if not recorded and outcome not in ("installed", "erased"):
        if delivery:
            orderbook._webhook_seen.pop(delivery, None)
        _shop_redact_settle("unrecorded")
        return PlainTextResponse("retry", status_code=503)
    _shop_redact_settle(outcome)
    return PlainTextResponse("ok", status_code=200)


async def _shop_redact_retry(down_since) -> Optional[str]:
    """The hourly second attempt at an owed shop/redact; its outcome, or None
    when nothing is owed."""
    d = _load_privacy_log()
    owed = d.get("shop_owed")
    if not isinstance(owed, dict):
        return None
    try:
        outcome = await _shop_redact_attempt(down_since)
    except Exception:
        logger.exception("shop/redact retry failed")
        outcome = "unknown"
    if outcome not in ("installed", "erased"):
        d = _load_privacy_log()
        if isinstance(d.get("shop_owed"), dict):
            d["shop_owed"] = {**d["shop_owed"], "tries": int(d["shop_owed"].get("tries") or 0) + 1,
                              "last": outcome, "last_at": datetime.now(timezone.utc).isoformat()}
            if jsonstore._store_writable(PRIVACY_LOG_PATH):
                jsonstore._write_json_store(PRIVACY_LOG_PATH, None, d)
    _shop_redact_settle(outcome)
    return outcome


def _ask_hold(email: str, customer_id="") -> bool:
    """A data request, kept until someone marks it answered: in its own list,
    so neither the event log's limit nor a restore can drop it. False when it
    could not be kept (the log unwritable, or more than REDACT_ASKS_MAX open:
    then the newest is refused, never an older one dropped)."""
    addr = str(email or "").strip().lower()[:254]
    d = _load_privacy_log()
    if PRIVACY_LOG_PATH in jsonstore._poisoned_stores:
        return False
    opened = _open_asks(d)
    if addr and any(a.get("email") == addr for a in opened):
        return True                      # the same person asking again: one entry
    if len(opened) >= REDACT_ASKS_MAX:
        return False
    entry = {"id": secrets.token_hex(5), "email": addr, "customer_id": str(customer_id or "")[:40],
             "received": datetime.now(timezone.utc).isoformat(), "answered": "", "mailed": False}

    def change(asks):
        answered = [a for a in asks if a.get("answered")]
        still = [a for a in asks if not a.get("answered")]
        # Answered ones go first when the list is long; open ones never do.
        return answered[-max(0, REDACT_ASKS_MAX - len(still) - 1):] + still + [entry]
    if not _redact_hold_write(change, key="asks"):
        return False
    _privacy_alert(force=True)
    return True


def _keep_live_privacy(live: dict, built_at: str = "") -> None:
    """After a restore, merge what is owed, waiting and decided now with the
    backup's. A restore replaced the whole privacy log with an older one, so
    requests that came in since were lost, settled ones came back, and the
    record of what was erased went; and onto a fresh volume, with no live log
    at all, taking the live lists as they were wiped the backup's.

      waiting requests  the live ones, and the backup's not settled since
      data requests     the live ones, and the backup's the live list lacks
      stops, answers,   both, without repeats
      decisions, owed
      events            the backup's, and the live ones since it was built
      shop erasure owed as live

    An erasure confirmed since the backup was built is owed again, as the
    restore has just brought that person's records back. Called only when the
    live log could be read: an unreadable one is what a restore repairs."""
    pl = _load_privacy_log()
    old_events = _plist(pl, "events")
    cut = str(built_at or "") or max((str(e.get("at") or "") for e in old_events), default="")
    seen_ev = {(e.get("at"), e.get("topic"), e.get("email"), e.get("detail")) for e in old_events}
    since = [e for e in _plist(live, "events") if str(e.get("at") or "") > cut
             and (e.get("at"), e.get("topic"), e.get("email"), e.get("detail")) not in seen_ev]
    pl["events"] = (old_events + since)[-2000:]
    decisions, seen = [], set()
    for x in _plist(pl, "decisions") + _plist(live, "decisions"):
        key = (x.get("at"), x.get("email"), x.get("action"))
        if key not in seen:
            seen.add(key)
            decisions.append(x)
    pl["decisions"] = decisions[-5000:]

    def settled_since(h: dict) -> bool:
        return any(x.get("email") == h.get("email") and str(x.get("at") or "") >= str(h.get("received") or "")
                   and x.get("action") in ("erased", "stopped") for x in decisions)
    live_held = _held_requests(live)
    ids = {h["id"] for h in live_held}
    emails = {h["email"] for h in live_held}
    pl["held"] = live_held + [h for h in _held_requests(pl) if h["id"] not in ids
                              and h["email"] not in emails and not settled_since(h)]
    live_asks = _plist(live, "asks")
    ask_ids = {a.get("id") for a in live_asks}
    pl["asks"] = live_asks + [a for a in _plist(pl, "asks") if a.get("id") not in ask_ids]
    for k, ident in (("stopped", ("email", "at")), ("answered", ("at",))):
        merged, keys = [], set()
        for x in _plist(pl, k) + _plist(live, k):
            key = tuple(x.get(f) for f in ident)
            if key not in keys:
                keys.add(key)
                merged.append(x)
        pl[k] = merged[-1000:]
    if isinstance(live.get("shop_owed"), dict):
        pl["shop_owed"] = live["shop_owed"]
    else:
        pl.pop("shop_owed", None)
    pend = {p.get("email"): p for p in _plist(pl, "pending") + _plist(live, "pending") if p.get("email")}
    for x in decisions:
        if x.get("action") == "erased" and str(x.get("at") or "") > cut and x.get("email") not in pend:
            pend[x["email"]] = {"email": x["email"], "customer_id": str(x.get("customer_id") or ""),
                                "stores": ["the records a restore brought back"], "at": str(x.get("at") or "")}
    pl["pending"] = list(pend.values())[-500:]
    if jsonstore._store_writable(PRIVACY_LOG_PATH):
        jsonstore._write_json_store(PRIVACY_LOG_PATH, None, pl)


# ---- helpers add_routes kept to itself -------------------------------------
# Forty-two functions were defined inside add_routes, so nothing outside that
# one 8,700-line call could reach them: no test could exercise them directly,
# no other part of the file could reuse them, and reading any of them meant
# scrolling through the route table to find where it was hidden. None of them
# closes over anything add_routes builds - they were nested by habit, not by
# need - so they are plain module functions, checkable as copilot.<name>.
# The six that genuinely do close over the injected tool registry stayed put.


async def _webhook_body(request: Request):
    """(raw_bytes, error_response). The whole authentication for any Shopify
    webhook, in one place rather than copied per topic - the checks here are
    the only thing standing between a POST and a redaction.

    Streamed with a hard cap rather than request.body(): the signature can
    only be checked after the body is read, so this read happens for anyone,
    and a chunked upload with no Content-Length would otherwise buffer
    without limit on an endpoint that deliberately has no rate limiter."""
    if not config.SHOPIFY_API_SECRET:
        return None, PlainTextResponse("Unauthorized", status_code=401)
    total, chunks = 0, []
    try:
        async for chunk in request.stream():
            total += len(chunk)
            if total > orderbook.WEBHOOK_MAX_BYTES:
                return None, PlainTextResponse("Too large", status_code=413)
            chunks.append(chunk)
    except Exception:
        return None, PlainTextResponse("Bad request", status_code=400)
    raw = b"".join(chunks)
    sent = request.headers.get("x-shopify-hmac-sha256", "")
    want = base64.b64encode(hmac.new(config.SHOPIFY_API_SECRET.encode("utf-8"),
                                     raw, hashlib.sha256).digest()).decode("ascii")
    if not sent or not hmac.compare_digest(want, sent):
        return None, PlainTextResponse("Unauthorized", status_code=401)
    shop = str(request.headers.get("x-shopify-shop-domain") or "")
    if config.SHOPIFY_STORE and not shop.lower().startswith(config.SHOPIFY_STORE.split(".")[0].lower() + "."):
        return None, PlainTextResponse("Unauthorized", status_code=401)
    return raw, None


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as sibling.NAME, never a copied name.
from gizmo import dispatch as desk  # noqa: E402
from gizmo import files as fileserver  # noqa: E402
from gizmo import mail  # noqa: E402
from gizmo import production  # noqa: E402
from gizmo import crm as salesdesk  # noqa: E402
from gizmo import config  # noqa: E402
from gizmo import liability  # noqa: E402
from gizmo import backup  # noqa: E402
from gizmo import scheduler  # noqa: E402
from gizmo import orderbook  # noqa: E402
