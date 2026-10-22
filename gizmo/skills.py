"""Skills: the merchant's own instructions and playbooks for the assistant. The
store and its limits, frontmatter, names and sections, the index, the
ranking for a question, the reading pass that writes when a skill applies,
and what goes into the AI's instructions. Moved out of copilot.py (stage 4
of the 14 October audit); its routes are in gizmo/routes/skills.py. Read as
`skillbook.NAME` (`skills` is a local name in several functions).
"""
import logging
import os
import re
import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional
from gizmo.config import _env_num
from gizmo import store as jsonstore
from gizmo import ai as claude

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


SKILLS_PATH        = os.environ.get("SKILLS_PATH", "/data/store_skills.json")  # merchant-authored skills
SKILLS_MAX         = _env_num(int, os.environ.get("SKILLS_MAX", "200"), "200", "SKILLS_MAX")        # max stored skills
SKILL_TITLE_CAP    = _env_num(int, os.environ.get("SKILL_TITLE_CAP", "120"), "120", "SKILL_TITLE_CAP")   # chars per skill title
SKILL_BODY_CAP     = _env_num(int, os.environ.get("SKILL_BODY_CAP", "40000"), "40000", "SKILL_BODY_CAP")   # chars per skill body
# The master account's limit per skill, and only the master uploads files.
SKILL_UPLOAD_CAP   = max(SKILL_BODY_CAP, _env_num(int, os.environ.get("SKILL_UPLOAD_CAP", "200000"), "200000", "SKILL_UPLOAD_CAP"))
# A request to the skills route may be this large for the master: a skill at
# the limit as JSON, with room for escapes and multi-byte characters.
SKILLS_BODY_MAX    = SKILL_UPLOAD_CAP * 4 + 64 * 1024
SKILLS_INJECT_CAP  = _env_num(int, os.environ.get("SKILLS_INJECT_CAP", "24000"), "24000", "SKILLS_INJECT_CAP")  # max total skill chars injected


# ---------------------------------------------------------------------------
# Skills: merchant-authored instructions and playbooks. Permanent until the
# merchant edits or deletes them; injected into every answer as authoritative
# guidance the copilot follows (distinct from Memory, which the AI manages).
# ---------------------------------------------------------------------------

def _load_skills() -> list[dict]:
    # Through the one loader, for the reason given on _load_memory.
    d = jsonstore._load_json_store(SKILLS_PATH, "skills", [])
    return d if isinstance(d, list) else []


def _write_skills(skills: list[dict]) -> list[dict]:
    if not jsonstore._store_writable(SKILLS_PATH):
        # Hand-written merchant work: preserve the broken file for repair rather
        # than replacing it with whatever loaded as the default.
        return skills
    jsonstore._write_json_store(SKILLS_PATH, "skills", skills)
    return skills


SKILL_WHEN_CAP = 400          # chars in a skill's "when it applies" note
SKILL_READ_CAP = 40000   # read_skill returns at most this much per read; a longer skill is read in parts
SKILL_ALWAYS_CAP = 4000       # a skill applied to every answer stays this short
SKILL_ALWAYS_TOTAL = 8000     # and all of them together, since they go into every answer
_FM_KEYS = ("name", "title", "description", "when", "when_to_use")


def _yaml_scalar(v: str) -> str:
    """One quoted or plain YAML value: a single matching pair of quotes taken
    off, and the quote escaped inside it put back."""
    v = str(v or "").strip()
    if len(v) >= 2 and v[0] == v[-1] == "'":
        return v[1:-1].replace("''", "'")
    if len(v) >= 2 and v[0] == v[-1] == '"':
        return v[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return v


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """A Markdown skill file's header, the YAML block between two '---' lines
    that Claude-style SKILL.md files carry (name, description and so on), and
    the text after it. A leading block is a header only when every line that
    starts at the margin is 'key: value' (or a comment) and one of the keys
    names the skill or says when it applies: a skill that simply opens with a
    rule line lost its first paragraph as a 'header'. Folded ('>') and literal
    ('|') values, and plain or quoted values carried on indented lines, are
    read; anything else in the header is ignored rather than trusted."""
    t = str(text or "").replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    m = re.match(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", t, re.S)
    if not m:
        return {}, t
    lines = m.group(1).split("\n")
    top = [ln for ln in lines if ln.strip() and not ln.startswith((" ", "\t"))]
    if not top or not all(re.match(r"^[A-Za-z_][\w-]*\s*:", ln) or ln.startswith("#") for ln in top):
        return {}, t
    # Each value is gathered as a list and joined once: joining on every
    # line made a long header cost the square of its length.
    raw: dict = {}
    mode: dict = {}
    key = None
    for ln in lines:
        kv = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", ln)
        if kv and not ln.startswith((" ", "\t")):
            key, val = kv.group(1).lower(), kv.group(2).strip()
            mode[key] = val[0] if val in (">", "|", ">-", "|-", ">+", "|+") else "plain"
            raw[key] = [] if mode[key] != "plain" else ([val] if val else [])
        elif ln.startswith("#") or not key:
            continue
        elif ln.strip() and ln.startswith((" ", "\t")):
            raw[key].append(ln.strip())
    raw = {k: ("\n" if mode[k] == "|" else " ").join(v).strip() for k, v in raw.items()}
    if not any(k in raw for k in _FM_KEYS):
        return {}, t
    meta = {k: (_yaml_scalar(v) if mode[k] == "plain" else v) for k, v in raw.items()}
    return meta, t[m.end():]


def _skill_name_words(t: str) -> str:
    """A 'trade-enquiry-replies' name, or a file's name, read as words; a
    name that is all lower case gets a capital, and 'SEO-checklist' keeps its."""
    t = str(t or "").strip()
    if re.fullmatch(r"[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)+", t):
        t = re.sub(r"[-_]+", " ", t)
        if t == t.lower():
            t = t[:1].upper() + t[1:]
    return t


def _cut_words(s: str, n: int) -> str:
    s = str(s or "").strip()
    if len(s) <= n:
        return s
    cut = s[:n]
    k = cut.rfind(" ")
    return (cut[:k] if k > n * 0.6 else cut).rstrip(" ,;:")


def _skill_from_markdown(text: str, filename: str = "") -> dict:
    """{title, when, content} from a Markdown skill: the header's title (as
    written) or name (read as words), else the first '# ' heading, else the
    file's name; its description (or when / when_to_use) as when it applies;
    the rest as the text. A first heading that only repeats the title goes."""
    meta, body = _split_frontmatter(text)
    body = body.strip()
    raw_name = str(meta.get("name") or "").strip()
    title = str(meta.get("title") or "").strip() or _skill_name_words(raw_name)
    h1 = re.match(r"\A#\s+(.+?)\s*#*\s*(?:\n|\Z)", body)
    if not title and h1:
        title = h1.group(1).strip()
    if h1 and title and h1.group(1).strip().lower() in (title.lower(), raw_name.lower()):
        body = body[h1.end():].strip()
    if not title and filename:
        title = _skill_name_words(re.sub(r"\.(md|markdown|txt|text)$", "", str(filename), flags=re.I))
    when = re.sub(r"\s+", " ", str(meta.get("description") or meta.get("when") or meta.get("when_to_use") or "")).strip()
    return {"title": _cut_words(title, SKILL_TITLE_CAP), "when": _cut_words(when, SKILL_WHEN_CAP), "content": body}


def _skill_sections(content: str) -> list[tuple]:
    """(level, heading, start, end) for every Markdown heading in a skill, end
    being where the next heading of the same or a higher level starts. Lines
    inside a fenced code block are not headings, and a fence closes only on
    the kind and length that opened it; a line underlined with '===' is a
    heading too."""
    heads, pos, fence = [], 0, ""
    lines = str(content or "").split("\n")
    for k, line in enumerate(lines):
        f = re.match(r"^\s*(`{3,}|~{3,})", line)
        if f:
            mark = f.group(1)
            if not fence:
                fence = mark
            elif mark[0] == fence[0] and len(mark) >= len(fence) and not line.strip()[len(mark):].strip():
                fence = ""
        elif not fence:
            m = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
            if m:
                heads.append((len(m.group(1)), m.group(2).strip(), pos))
            elif (k + 1 < len(lines) and re.match(r"^\s*={3,}\s*$", lines[k + 1]) and line.strip()
                  and not re.match(r"^\s*([-*+]|\d+[.)]|\|)", line)):
                heads.append((1, line.strip(), pos))
        pos += len(line) + 1
    out = []
    for k, (lvl, h, start) in enumerate(heads):
        end = next((s for (l2, _h, s) in heads[k + 1:] if l2 <= lvl), len(content))
        out.append((lvl, h, start, end))
    return out


def _skill_hash(content: str) -> str:
    """A fingerprint of a skill's text, to tell whether it has changed since
    it was read; not a secret, but the house scanner rightly refuses SHA-1."""
    return hashlib.sha256(str(content or "").encode("utf-8")).hexdigest()[:16]


_SKILL_INDEX: dict = {}
_SKILL_INDEX_CHARS = 0     # text indexed, so long skills cannot grow it without limit


def _skill_index(content: str) -> dict:
    """A skill's sections and word sets, worked out once per text: choosing
    skills recomputed them for every skill on every question, half a second
    on a large store, on the one thread that answers everyone."""
    key = _skill_hash(content)
    hit = _SKILL_INDEX.get(key)
    if hit:
        return hit
    secs = _skill_sections(content)
    deep = [lvl for (lvl, _h, _a, _b) in secs if lvl >= 2]
    level = min(deep) if deep else 1
    parts = [(h, content[a:b]) for (lvl, h, a, b) in secs if lvl == level]
    if not parts:
        parts = [("", p) for p in re.split(r"\n{2,}", content) if p.strip()]
    idx = {"sections": secs, "heads": _skill_words(" ".join(h for (_l, h, _a, _b) in secs)),
           "words": _skill_words(content), "parts": parts,
           "part_words": [(_skill_words(h), _skill_words(t)) for h, t in parts]}
    global _SKILL_INDEX_CHARS
    if len(_SKILL_INDEX) > 600 or _SKILL_INDEX_CHARS + len(content) > 5_000_000:
        _SKILL_INDEX.clear()
        _SKILL_INDEX_CHARS = 0
    _SKILL_INDEX[key] = idx
    _SKILL_INDEX_CHARS += len(content)
    return idx


def _skill_safe(text: str) -> str:
    """A skill's text in the prompt cannot close its own block or open a
    forged one: '<skill', '</SKILL >' and the like lose their shape."""
    return re.sub(r"<(\s*/?)\s*(skill)\b", lambda m: "<" + m.group(1).strip() + " " + m.group(2),
                  str(text or ""), flags=re.I)


def _skill_title_taken(skills: list[dict], title: str, sid: str = "") -> bool:
    """A skill is referred to by its title, in chat and in 'skills followed',
    so two with the same title would be one name for two sets of rules."""
    t = title.strip().lower()
    return any((s.get("title") or "").strip().lower() == t and s.get("id") != sid for s in skills)


def _clean_skill_input(title, content, when, cap: int = 0) -> tuple[str, str, str]:
    """A skill as typed or uploaded. A pasted file that still starts with a
    real Markdown header is read the same way an upload is. `cap` is the
    limit for whoever is saving it (the master's is larger)."""
    title, content, when = str(title or "").strip(), str(content or "").strip(), str(when or "").strip()
    meta, _b = _split_frontmatter(content)
    if meta:
        md = _skill_from_markdown(content)
        content = md["content"]
        title = title or md["title"]
        when = when or md["when"]
    cap = cap or SKILL_BODY_CAP
    if len(content) > cap:
        raise ValueError(f"This skill is {len(content) - cap:,} characters over the limit of "
                         f"{cap:,}. Shorten it, or split it into several skills.")
    return title[:SKILL_TITLE_CAP], content, re.sub(r"\s+", " ", when)[:SKILL_WHEN_CAP]


def _skill_always(always, content: str, skills: Optional[list] = None, sid: str = "") -> bool:
    if not always:
        return False
    if len(content) > SKILL_ALWAYS_CAP:
        raise ValueError(f"A skill applied to every answer can be at most {SKILL_ALWAYS_CAP:,} characters, "
                         f"since it goes into every one. This one is {len(content):,}.")
    others = sum(len(x.get("content") or "") for x in (skills or []) if x.get("always") and x.get("id") != sid)
    if others + len(content) > SKILL_ALWAYS_TOTAL:
        raise ValueError(f"The skills applied to every answer can come to {SKILL_ALWAYS_TOTAL:,} characters in all, "
                         f"and yours already come to {others:,}. Turn one off, or shorten them.")
    return True


def _add_skill(title: str, content: str, when: str = "", file: str = "", always: bool = False,
               cap: int = 0) -> list[dict]:
    title, content, when = _clean_skill_input(title, content, when, cap)
    if not title or not content:
        raise ValueError("A skill needs both a title and some details.")
    skills = _load_skills()
    always = _skill_always(always, content, skills)
    if _skill_title_taken(skills, title):
        raise ValueError(f"You already have a skill called \"{title}\". Give this one a different title.")
    if len(skills) >= SKILLS_MAX:
        raise ValueError(f"You have reached the limit of {SKILLS_MAX} skills. Delete one to add another.")
    now = datetime.now(timezone.utc).isoformat()
    # newest first, so a just-added skill is visible at the top of the list
    s = {"id": secrets.token_hex(5), "title": title, "content": content, "created": now, "updated": now}
    if when:
        s["when"] = when
    if file:
        s["file"] = str(file)[:120]
    if always:
        s["always"] = True
    skills.insert(0, s)
    return _write_skills(skills)


def _update_skill(sid: str, title: str, content: str, when: Optional[str] = None,
                  always: Optional[bool] = None, cap: int = 0) -> list[dict]:
    skills = _load_skills()
    own = next((s for s in skills if s.get("id") == sid), None)
    # Anyone may edit a skill the master made long, as long as it grows no
    # longer than it is: only the master brings in more.
    cap = cap or SKILL_BODY_CAP
    old = str((own or {}).get("content") or "").strip()
    limit = max(cap, len(old))
    try:
        title, content, when_clean = _clean_skill_input(title, content, when, limit)
    except ValueError:
        if limit > cap:
            raise ValueError("You can change this skill, but not make it longer than it is "
                             f"({len(old):,} characters). Only the master account can.")
        raise
    if not title or not content:
        raise ValueError("A skill needs both a title and some details.")
    if len(old) > cap and len(content) > cap:
        # A long skill came from the master: anyone may change parts of it,
        # but a paste over most of it would bring in new text past their own
        # limit, which only the master may.
        same = len(os.path.commonprefix([old, content]))
        tail = len(os.path.commonprefix([old[same:][::-1], content[same:][::-1]]))
        if len(content) - same - tail > cap:
            raise ValueError(f"That replaces more than {cap:,} characters of this skill at once, which only the master "
                             "account can do. Change less of it, or ask the master account to replace it.")
    # Only a title being CHANGED to a taken one is refused: two skills that
    # shared a title before the rule could not otherwise be saved at all.
    changed = not own or str(own.get("title") or "").strip().lower() != title.lower()
    if changed and _skill_title_taken(skills, title, sid):
        raise ValueError(f"You already have a skill called \"{title}\". Give this one a different title.")
    keep_always = bool(own and own.get("always")) if always is None else bool(always)
    keep_always = _skill_always(keep_always, content, skills, sid)
    for s in skills:
        if s.get("id") == sid:
            s["title"], s["content"] = title, content
            if when is not None and when_clean != (s.get("when") or ""):
                # The merchant's own words now, whatever filled it before.
                s.pop("when_from", None)
                if when_clean:
                    s["when"] = when_clean
                else:
                    s.pop("when", None)
            if keep_always:
                s["always"] = True
            else:
                s.pop("always", None)
            s["updated"] = datetime.now(timezone.utc).isoformat()
    return _write_skills(skills)


def _skills_for_page(skills: Optional[list] = None) -> list[dict]:
    """The skills as the page shows them: each reading marked stale when the
    text has changed since the text Reactor read."""
    out = []
    for s in (_load_skills() if skills is None else skills):
        s = dict(s)
        r = s.get("reading")
        if isinstance(r, dict):
            s["reading"] = dict(r, stale=r.get("of") != _skill_hash(s.get("content") or ""))
        out.append(s)
    return out


def _skills_answer(who: str = "") -> "JSONResponse":
    """The skills and the limits for the account asking: the master's skill
    limit is larger, and only the master uploads files."""
    master = team._team_role(who) == "master"
    return gate._json({"skills": _skills_for_page(), "caps": {"title": SKILL_TITLE_CAP,
                                                         "body": SKILL_UPLOAD_CAP if master else SKILL_BODY_CAP,
                                                         "when": SKILL_WHEN_CAP, "always": SKILL_ALWAYS_CAP,
                                                         "inject": SKILLS_INJECT_CAP, "upload": master}})


def _delete_skill(sid: str) -> list[dict]:
    return _write_skills([s for s in _load_skills() if s.get("id") != sid])


# Words that say nothing about which skill a question needs.
_SKILL_STOP = frozenset("""the and for with that this from what which when where have has had are was were
will would could should can our your you they them their there then than into onto about over under
more most some any all each how why who whom does did done not but its it's also just very much many
been being get got make made give given take need want like please tell show find list let know
store shop orders order week month year today last this next""".split())


def _skill_stem(w: str) -> str:
    """A light plural rule, so 'invoice' meets 'invoices' and 'reply' meets
    'replies': the ranking missed the right skill on a plural."""
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and re.search(r"(ch|sh|x|ss)es$", w):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def _skill_words(text: str) -> set:
    return {_skill_stem(w) for w in re.findall(r"[a-z0-9]+", str(text or "").lower())
            if len(w) > 2 and w not in _SKILL_STOP}


def _skill_reading(s: dict) -> dict:
    r = s.get("reading")
    return r if isinstance(r, dict) else {}


def _skill_fresh_reading(s: dict) -> dict:
    r = _skill_reading(s)
    return r if r and r.get("of") == _skill_hash(s.get("content") or "") else {}


def _skill_best_part(content: str, qw: set, budget: int, common: Optional[set] = None) -> str:
    """The parts of a long skill that fit the words of a question: its
    sections by heading, at one level (or its paragraphs when it has none),
    scored by the words they share with it, heading words counting three
    times, and words most of its parts use not at all; the best, in the
    skill's own order, within the budget."""
    idx = _skill_index(content)
    secs, words = idx["parts"], idx["part_words"]
    if not secs or not qw:
        return ""
    df: dict = {}
    for hw, tw in words:
        for w in hw | tw:
            df[w] = df.get(w, 0) + 1
    many = {w for w, n in df.items() if n > max(1, len(secs) // 4)} | (common or set())
    q = qw - many
    scored = []
    for k, ((h, text), (hw, tw)) in enumerate(zip(secs, words)):
        sc = 3 * len(q & hw) + min(len(q & tw), 20)
        if sc > 0:
            scored.append((sc, k))
    scored.sort(key=lambda x: (-x[0], x[1]))
    keep, used = [], 0
    for sc, k in scored:
        t = secs[k][1].strip()
        if used + len(t) > budget:
            if not keep and budget > 400:
                keep.append((k, _cut_words(t, budget)))
            continue
        keep.append((k, t))
        used += len(t)
    keep.sort()
    return "\n\n".join(t for _k, t in keep)


def _skills_ranked(query: str = "", named: Optional[list] = None, by_title: bool = True) -> list[tuple]:
    """(score, skill) for every usable skill, best first. A skill picked for
    this question, marked for every answer, or (in chat) named by its title in
    it, always comes first; then the ones whose title, 'when it applies' note,
    headings, example questions and text share words with the question
    (plurals folded, and words most skills use ignored); then the rest, most
    recently changed first."""
    q = str(query or "")
    ql = q.lower()
    qw = _skill_words(q)
    named = {str(x) for x in (named or [])}
    skills = [s for s in _load_skills() if (s.get("title") or "").strip() and (s.get("content") or "").strip()]
    if len(skills) >= 4:
        df: dict = {}
        for s in skills:
            for w in _skill_words((s.get("title") or "") + " " + _skill_when(s)) | _skill_index(s["content"].strip())["words"]:
                df[w] = df.get(w, 0) + 1
        common = {w for w, n in df.items() if n > len(skills) / 2}
        qw = qw - common
    else:
        common = set()
    out = []
    for s in skills:
        title, content = s["title"].strip(), s["content"].strip()
        score = 0.0
        if s.get("id") in named:
            score += 10000
        if s.get("always") and len(content) <= SKILL_ALWAYS_CAP:
            score += 1000
        if by_title and len(title) >= 4 and title.lower() in ql:
            score += 1000
        # What Reactor read counts only while it matches the text: a skill
        # rewritten about projector hire kept being chosen for glass prices.
        reading = _skill_fresh_reading(s)
        when = " ".join([_skill_when(s), reading.get("when") or ""])
        idx = _skill_index(content)
        examples = " ".join(str(x) for x in (reading.get("examples") or []))
        if len(content) > 8000:
            # A long document shares some word with almost any question: its
            # best section is what counts, not the whole of it.
            best = _skill_best_part(content, qw, 6000, common)
            body_hits = min(len(qw & _skill_words(best)), 12) if best else 0
        else:
            body_hits = min(len(qw & idx["words"]), 12)
        score += (3 * len(qw & _skill_words(title)) + 3 * len(qw & _skill_words(when))
                  + 2 * len(qw & idx["heads"]) + 2 * len(qw & _skill_words(examples)) + body_hits)
        out.append((score, s))
    # Ties (including every score of 0) fall back to the most recently changed.
    out.sort(key=lambda x: x[1].get("updated") or "", reverse=True)
    out.sort(key=lambda x: -x[0])
    return out


def _skill_gist(content: str) -> str:
    """A skill in a line: its first sentence of text, or its first headings
    when it is all headings to begin with."""
    lines = [ln.strip() for ln in content.strip().split("\n") if ln.strip()]
    text = next((ln for ln in lines if not ln.startswith(("#", "|", "```", "~~~", "---"))), "")
    if text:
        first = re.split(r"(?<=[.!?])\s", re.sub(r"^([-*+]|\d+[.)])\s+", "", text), maxsplit=1)[0]
        return (first[:117] + "...") if len(first) > 120 else first
    heads = [re.sub(r"^#+\s*", "", ln) for ln in lines if ln.startswith("#")][:3]
    return "; ".join(heads)


def _skill_when(s: dict) -> str:
    """When a skill applies: the merchant's note, or Reactor's while its
    reading still matches the text."""
    if s.get("when") and s.get("when_from") != "reading":
        return s["when"].strip()
    return (_skill_fresh_reading(s).get("when") or (s.get("when") if _skill_fresh_reading(s) else "") or "").strip()


def _skill_attr(v: str) -> str:
    return str(v or "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", " ")


def _skill_open(s: dict, extra: str = "") -> str:
    """Each skill in a tagged block of its own, its title, when it applies and
    when it last changed as attributes: a skill's own '##' headings sat under a
    '###' title and read as sections of the prompt rather than of the skill."""
    when = _skill_when(s)
    changed = ""
    try:
        d = datetime.fromisoformat(str(s.get("updated") or s.get("created") or ""))
        changed = f"{d.day} {d:%b %Y}"
    except Exception:
        pass  # an unreadable date leaves out when the skill changed
    return ('<skill title="' + _skill_attr(s["title"].strip()) + '"'
            + (' applies="' + _skill_attr(when) + '"' if when else "")
            + (' changed="' + changed + '"' if changed else "")
            + (' always="yes"' if s.get("always") else "") + extra + ">\n")


def _skill_full_block(s: dict) -> str:
    return _skill_open(s) + _skill_safe(s["content"].strip()) + "\n</skill>\n\n"


def _skill_brief_block(s: dict, can_read: bool, query: str = "", part_budget: int = 3000) -> str:
    """A skill not shown in full: when it applies, what Reactor read it as
    asking (while that reading matches the text), its headings, and the parts
    of it that fit the question, so a report or draft with no way to read on
    still gets the section it needs; chat is told to read the rest."""
    content = s["content"].strip()
    rules = [str(x) for x in (_skill_fresh_reading(s).get("rules") or [])][:25]
    all_heads = [h for (_l, h, _a, _b) in _skill_sections(content)]
    heads = all_heads[:40]
    out = _skill_open(s, ' shown="in brief"')
    if can_read:
        out += ("(" + f"{len(content):,}" + " characters, not shown in full here to save room. "
                + ("Read the sections you need with read_skill before you answer.)" if heads
                   else "Read it with read_skill before you answer.)") + "\n")
    else:
        out += "(" + f"{len(content):,}" + " characters; what it asks and the parts that fit are shown.)\n"
    if not rules and not heads:
        g = _skill_when(s) or _skill_gist(content)
        if g:
            out += "In short: " + _skill_safe(g) + "\n"
    if rules:
        out += "What it asks, as you read it before:\n" + "\n".join("- " + _skill_safe(x) for x in rules) + "\n"
    if heads:
        out += ("Its sections: " + _skill_safe("; ".join(heads))
                + (" and " + str(len(all_heads) - len(heads)) + " more" + (", found by reading it part by part" if can_read else "")
                   if len(all_heads) > len(heads) else "") + "\n")
    part = _skill_best_part(content, _skill_words(query), part_budget) if query and part_budget else ""
    if part:
        out += "The parts that fit this question:\n" + _skill_safe(part) + "\n"
    elif not rules and not can_read:
        # No reading, nothing matched, and no way to open it: its opening.
        cut = content[:2500]
        k = cut.rfind("\n#")
        out += _skill_safe((cut[:k] if k > 800 else cut).rstrip()) + "\n(it continues)\n"
    return out + "</skill>\n\n"


def _skills_to_system(query: str = "", named: Optional[list] = None, can_read: bool = False) -> str:
    """The merchant's saved skills for this call: those that fit the question
    in full (or, when one is too long, what it asks, its sections and the
    parts that fit), the rest by title and when they apply. With can_read (chat)
    the model has the read_skill tool and is told to open any listed skill, or
    section, that may apply; a title named in a report's fixed topic is not a
    pick, and skills asked for by name share a limit of their own."""
    ranked = _skills_ranked(query, named, by_title=can_read)
    if not ranked:
        return ""
    body, used, overflow, picked = "", 0, [], []
    for score, s in ranked:
        title = s["title"].strip()
        block = _skill_full_block(s)
        must = score >= 1000          # picked, marked for every answer, or named
        fits = used + len(block) <= SKILLS_INJECT_CAP
        if must:
            if len(block) > SKILL_READ_CAP or used + len(block) > SKILLS_INJECT_CAP + SKILL_READ_CAP:
                block = _skill_brief_block(s, can_read, query, 6000)
        elif fits:
            pass
        elif score > 1:
            block = _skill_brief_block(s, can_read, query, 3000 if can_read else 6000)
            if used + len(block) > SKILLS_INJECT_CAP + 8000:
                overflow.append(s)
                continue
        else:
            overflow.append(s)
            continue
        body += block
        used += len(block)
        if score >= 10000:
            picked.append(title)
    # Nothing fitted and nothing matched: chat is still told the skills are
    # there to read; a report, which cannot read one, gets nothing.
    if not body and not (can_read and overflow):
        return ""
    head = ("\n\n## Saved skills\n"
            "Each <skill> below is one of the merchant's own instructions and playbooks for this business. "
            "They override your general habits, though never what you cannot do: you only read store data, "
            "and you never change orders, issue refunds or discounts, or send email yourself. Before you "
            "answer, decide which skills apply to this question (each says when it applies) and follow those "
            "closely: take their steps in order, use their figures, thresholds, wording, templates and "
            "formats, and meet every rule they set. A skill marked always applies to every answer. When the "
            "merchant names or picks a skill, apply it even if it seems a loose fit. If two skills conflict, "
            "follow the one the merchant named or picked, otherwise the one whose applies note fits the "
            "question more closely, otherwise the more recently changed one, and say which you followed and "
            "what conflicts. "
            + ("Where a skill is shown in brief, call read_skill with its title (and the section you need) "
               "before you answer; never guess what an unshown part says. " if can_read else "")
            + "List the exact title of every skill you followed in `skills_applied`; leave it empty "
            "when none applied, and never list one you only read.\n")
    if picked:
        head += ("The merchant asked you to apply " + (", ".join('"' + _skill_safe(t) + '"' for t in picked))
                 + " to this question.\n")
    out = head + ("\n" + body.rstrip() + "\n" if body else "")
    if overflow:
        out += ("\nOther saved skills, by title and when they apply"
                + (" (call read_skill with the title to read any that may apply before you answer)"
                   if can_read else "") + ":\n"
                + "\n".join("- " + _skill_safe(s["title"].strip()) + ": " + _skill_safe(_skill_when(s) or _skill_gist(s["content"]))
                            for s in overflow) + "\n")
    return out


def _skills_for_draft(query: str) -> str:
    """The saved skills that fit one email, for a reply draft: any marked for
    every answer, then those that share words with the email, the best of them
    in full up to 12,000 characters and the rest within 8,000; a longer one
    comes as what it asks and the parts of it that fit the email, since a
    draft cannot open a skill to read on."""
    body, used, first, extra = "", 0, True, 0
    for score, s in _skills_ranked(str(query or ""), by_title=False):
        if score <= 1:
            break
        always = bool(s.get("always")) and score >= 1000
        block = _skill_full_block(s)
        if always:
            # Skills for every answer have a limit of their own, and take
            # none of the room the email's own skills are given.
            body += block
            continue
        # The larger first slot is for the skill that fits the email best.
        limit = 12000 if first else 8000
        if len(block) > limit:
            block = _skill_brief_block(s, False, query, 3000)
        if first:
            extra = max(0, len(block) - 8000)
        if used and used + len(block) > 8000 + extra:
            continue
        body += block
        used += len(block)
        first = False
    return body.strip()


def _read_parts(text: str, cap: int = 0) -> list[str]:
    """A long text as reads of at most `cap` characters, each ending before a
    heading, else at a blank line, else at a line break, where one falls in
    the second half of the read, so a skill longer than one read, or a long
    stretch of it with no heading, can still be read to its end."""
    cap = cap or SKILL_READ_CAP
    out, rest = [], text.strip()
    while len(rest) > cap:
        cut = rest[:cap]
        k = next((i for i in (cut.rfind(sep) for sep in ("\n#", "\n\n", "\n")) if i > cap // 2), cap)
        out.append(rest[:k].rstrip())
        rest = rest[k:].lstrip("\n")
    out.append(rest)
    return out


def _heads_list(secs: list, first: str = "", n: int = 40) -> str:
    """A skill's headings for read_skill's replies, at most n of them (those
    sharing a word with `first` ahead), so a long catalogue's thousands of
    headings cannot make one reply longer than a read."""
    heads = [x[1] for x in secs]
    if first:
        w = _skill_words(first)
        heads = sorted(heads, key=lambda h: not (_skill_words(h) & w))
    out = "; ".join(heads[:n])
    return out + (" and " + f"{len(heads) - n:,}" + " more" if len(heads) > n else "")


def _read_skill(title: str, section: str = "", part=None) -> str:
    """The read_skill tool: one saved skill, by title (or id), in full or one
    section of it by heading. A part name that fits several headings lists
    them rather than guessing. What is longer than one read comes in parts,
    read one at a time by number."""
    want = str(title or "").strip().lower()
    try:
        n = max(1, int(part or 1)) if not isinstance(part, bool) else 1
    except (TypeError, ValueError, OverflowError):
        n = 1
    for s in _load_skills():
        if not (want and (want == (s.get("title") or "").strip().lower() or want == s.get("id"))):
            continue
        name, content = s["title"].strip(), (s.get("content") or "").strip()
        secs = _skill_sections(content)
        if str(section or "").strip():
            w = str(section).strip().lower().lstrip("#").strip()
            exact = [x for x in secs if x[1].lower() == w]
            some = [x for x in secs if w in x[1].lower()]
            hit = exact[0] if exact else (some[0] if len(some) == 1 else None)
            if hit:
                pieces = _read_parts(content[hit[2]:hit[3]])
                n = min(n, len(pieces))
                return (_skill_open(s, ' section="' + _skill_attr(hit[1]) + '"'
                                    + (' part="' + str(n) + ' of ' + str(len(pieces)) + '"' if len(pieces) > 1 else ""))
                        + _skill_safe(pieces[n - 1])
                        + ("\n(The section goes on: read part " + str(n + 1) + " of it with read_skill.)" if n < len(pieces) else "")
                        + "\n</skill>")
            if len(some) > 1:
                return _skill_safe("Several sections of \"" + name + "\" fit \"" + str(section).strip() + "\": "
                                   + _heads_list(some) + ". Read the one you need by its full heading.")
            return _skill_safe("No section of \"" + name + "\" is called \"" + str(section).strip() + "\". Its sections are: "
                               + (_heads_list(secs, str(section)) or "none, it is one piece of text")
                               + (". Read it by part to see them all" if len(secs) > 40 else ""))
        pieces = _read_parts(content)
        if len(pieces) == 1:
            return _skill_open(s) + _skill_safe(content) + "\n</skill>"
        n = min(n, len(pieces))
        return (_skill_open(s, ' part="' + str(n) + ' of ' + str(len(pieces)) + '"') + _skill_safe(pieces[n - 1])
                + "\n\n(" + ("The rest did not fit in one read. " if n == 1 else "")
                + ("Read part " + str(n + 1) + " with read_skill for what follows" if n < len(pieces) else "That is the end of it")
                + ("; or read a section by its heading: " + _heads_list(secs) if secs and n == 1 else "")
                + ".)\n</skill>")
    names = [s.get("title") for s in _load_skills() if s.get("title")]
    return _skill_safe("No saved skill has that title. The saved skills are: " + "; ".join(names[:60]))


READ_SKILL_TOOL = {
    "name": "read_skill",
    "description": ("Read one of the merchant's saved skills by its exact title: in full, or just one "
                    "section of it by heading (for a long skill). What is longer than one read comes in "
                    "numbered parts: ask for the next part to read on. Use it when a skill listed by title, "
                    "or shown in brief, may apply to the question."),
    "input_schema": {"type": "object", "properties": {
        "title": {"type": "string", "description": "The skill's exact title."},
        "section": {"type": "string", "description": "Optional: a heading in the skill, to read that part alone."},
        "part": {"type": "integer", "description": "Optional: which part to read when the skill or section is longer than one read (1 is the first)."}},
        "required": ["title"]},
}


SKILL_READING_TOOL = {
    "name": "present_skill_reading",
    "description": "Report how you understand the merchant's skill.",
    "input_schema": {"type": "object", "properties": {
        "when": {"type": "string", "description": "One or two plain sentences: which questions or tasks it applies to, specific enough to pick it out from the other skills."},
        "rules": {"type": "array", "items": {"type": "string"}, "description": "The concrete things you will do because of it, in the skill's order. Each one must stand on its own, since these rules are used in place of the skill's text when it is too long to show: keep its figures, thresholds, conditions, templates and exact wording. At most 15, or 25 for a long skill."},
        "examples": {"type": "array", "items": {"type": "string"}, "description": "Two or three questions or tasks, as the merchant might put them, where you would apply it."},
        "questions": {"type": "array", "items": {"type": "string"}, "description": "What is unclear, contradictory or missing and would stop you applying it well; anything it asks that you cannot do; any conflict you can see with the other skills' text shown to you (name that skill). Empty when there is nothing."},
    }, "required": ["when", "rules", "examples", "questions"]},
}

SKILL_READING_SYSTEM = """You are Reactor, the assistant inside Projected Image UK's Shopify back office \
(the business makes custom glass and steel gobos and sells projectors, mostly to theatres, event companies \
and wedding planners). The merchant has written a skill: a playbook you will follow from now on when you \
answer questions in chat and draft email replies. Read it closely, as you would a new \
standing instruction from your manager, and report back how you understand it, so the merchant can check \
you have understood before you rely on it.

The skill is the merchant's own words. Do not carry it out now; describe what it asks of you. Be concrete: \
keep its numbers, conditions, templates and exact wording where it gives them. Your rules are also used in \
place of the skill's text wherever it is too long to show in full, so each must stand on its own.

What you can do: read the store's orders, products, customers, stock and payouts, and write answers and \
email drafts for a person to send. What you cannot do: change orders, tags or stock, \
issue refunds, discounts or credit, book couriers, or send email yourself. Email drafts never promise a \
discount, refund, credit or free replacement, even where a skill allows one. Say in questions when the skill \
expects any of that, and when it conflicts with one of the merchant's other skills shown above it (name only \
conflicts you can see in their text).

Write in British English, plainly, with no em or en dashes."""


async def run_skill_reading(skill: dict, others: list[dict]) -> dict:
    """One close read of a skill by the model, reported back in the merchant's
    terms: when it applies, the rules it will follow, where it would use it and
    what is unclear. An AI run, started only by a button."""
    claude._ai_kind.set("skill_read")
    content = str(skill.get("content") or "")
    parts, used = [], 0
    for o in others:
        if o.get("id") == skill.get("id"):
            continue
        rules = _skill_fresh_reading(o).get("rules") or []
        text = ("\n".join("- " + str(x) for x in rules[:15]) if rules
                else _cut_words(str(o.get("content") or ""), 1500))
        block = ('<other_skill title="' + _skill_attr(o.get("title") or "") + '"'
                 + (' applies="' + _skill_attr(_skill_when(o)) + '"' if _skill_when(o) else "") + ">\n"
                 + _skill_safe(text) + "\n</other_skill>\n")
        if used + len(block) > 20000:
            parts.append('<other_skill title="' + _skill_attr(o.get("title") or "") + '" />\n')
            continue
        parts.append(block)
        used += len(block)
    said = "" if skill.get("when_from") == "reading" else str(skill.get("when") or "")
    msg = ("The merchant's other skills:\n" + ("".join(parts) or "(none)\n") + "\n"
           + "The skill to read, titled \"" + str(skill.get("title") or "") + "\""
           + (" (the merchant says it applies: " + said + ")" if said else "")
           + (". It is long, so up to 25 rules may be needed." if len(content) > 8000 else "")
           + ":\n<skill>\n" + _skill_safe(content[:SKILL_UPLOAD_CAP]) + "\n</skill>\n\nReport how you understand it now.")
    client = claude._anthropic()
    resp = await claude._xcreate(client,
        model=claude.MODEL_DEEP, max_tokens=claude.MAX_TOKENS, system=SKILL_READING_SYSTEM,
        tools=[SKILL_READING_TOOL], tool_choice={"type": "tool", "name": SKILL_READING_TOOL["name"]},
        messages=[{"role": "user", "content": msg}], output_config={"effort": claude._effort_for(claude.MODEL_DEEP)},
    )
    if getattr(resp, "stop_reason", "") == "max_tokens":
        raise RuntimeError("Reactor ran out of room writing up this skill. Try again, or split the skill.")
    got = next((b.input for b in resp.content
                if b.type == "tool_use" and b.name == SKILL_READING_TOOL["name"]), None)
    if not isinstance(got, dict):
        raise RuntimeError("Reactor could not write up how it reads this skill. Try again.")

    def clean(xs, n, k):
        if isinstance(xs, str):
            xs = [xs]
        if not isinstance(xs, list):
            return []
        return [str(x).strip()[:k] for x in xs if isinstance(x, (str, int, float)) and str(x).strip()][:n]
    return claude._strip_dashes({"when": _cut_words(str(got.get("when") or ""), SKILL_WHEN_CAP),
                          "rules": clean(got.get("rules"), 25, 500),
                          "examples": clean(got.get("examples"), 4, 200),
                          "questions": clean(got.get("questions"), 6, 400)})


def _save_skill_reading(sid: str, reading: dict, who: str = "", of: str = "") -> dict:
    """The reading kept on the skill, stamped with the text it READ, so an
    edit made while it was being read, or after, shows it as out of date.
    The skill's 'when it applies' is filled from it while the merchant has
    not written one, and kept up to date on a later reading while it is
    still Reactor's words, never the merchant's."""
    skills = _load_skills()
    hit = next((s for s in skills if s.get("id") == sid), None)
    if not hit:
        raise ValueError("That skill no longer exists.")
    hit["reading"] = dict(reading, of=of or _skill_hash(hit.get("content") or ""),
                          at=datetime.now(timezone.utc).isoformat(), by=team._team_name(who) or "")
    if reading.get("when") and (not (hit.get("when") or "").strip() or hit.get("when_from") == "reading"):
        hit["when"] = reading["when"]
        hit["when_from"] = "reading"
    _write_skills(skills)
    return hit


def _note_skills_applied(data: dict) -> None:
    """Keep only titles of real skills in skills_applied, and record each use
    on the skill (how often, and when last), so the Skills page can say which
    skills Reactor actually follows."""
    raw = data.get("skills_applied")
    if not isinstance(raw, list):
        data.pop("skills_applied", None)
        return
    try:
        skills = _load_skills()
    except Exception:  # skills that cannot be read cannot be matched; the answer goes without the list
        data.pop("skills_applied", None)
        return
    by = {(s.get("title") or "").strip().lower(): s for s in skills}
    names, hit = [], False
    now = datetime.now(timezone.utc).isoformat()
    for t in raw[:12]:
        want = str(t or "").strip().lower()
        s = by.get(want)
        if not s:
            # 'Wedding season playbook (Pricing)' or ': Email templates': a
            # skill cited with the section it followed is still that skill.
            s = next((v for k, v in sorted(by.items(), key=lambda kv: -len(kv[0]))
                      if k and want.startswith(k) and want[len(k):len(k) + 2].strip()[:1] in ("(", ":", "-")), None)
        if s and s["title"] not in names:
            names.append(s["title"])
            s["used"] = int(s.get("used") or 0) + 1
            s["used_at"] = now
            hit = True
    if names:
        data["skills_applied"] = names
    else:
        data.pop("skills_applied", None)
    if hit:
        try:
            _write_skills(skills)
        except Exception:
            logger.exception("skills: could not record which were followed")


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as sibling.NAME, never a copied name.
from gizmo import gate  # noqa: E402
from gizmo import team  # noqa: E402
