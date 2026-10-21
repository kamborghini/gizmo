"""The Size list: the gobo size rules (the sheet on the volume, the overrides
and aliases), and the lookup a label asks for the size a gobo prints at.

Moved out of copilot.py (stage 4 of the 14 October audit). Read as
`size_list.NAME` (`sizes` is a local name in three places).
"""
import logging
from typing import Optional
import os
import re
from datetime import datetime, timezone

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")

# The repository, where the seed rules ship (data/). This module is one
# folder down from where copilot.py built these paths from its own file.
_REPO = os.path.dirname(os.path.dirname(__file__))


# The Shopify product type of a catalogue (stock) gobo. A stock gobo is its own
# name on a label; the custom products ("Custom Gobo", "Custom Gobos") are not,
# and still need a fixture before anything is sized.
STOCK_GOBO_TYPE    = "gobo"
GOBO_SIZES_PATH    = os.environ.get("GOBO_SIZES_PATH",
                                    os.path.join(_REPO, "data", "gobo-sizes.csv"))


_gobo_cache = {"mtime": None, "by_mm": {}, "by_model": {}, "by_mm_loose": {}, "by_model_loose": {},
               "by_mm_digit": {}, "by_model_digit": {}, "rows": [], "domain_rules": []}
GOBO_ALIASES_PATH = os.environ.get("GOBO_ALIASES_PATH",
                                   os.path.join(_REPO, "data", "gobo-aliases.csv"))
GOBO_OVERRIDES_PATH = os.environ.get("GOBO_OVERRIDES_PATH",
                                     os.path.join(_REPO, "data", "gobo-overrides.csv"))
GOBO_SIZES_LIVE = os.environ.get("GOBO_SIZES_LIVE", "/data/gobo-sizes.csv")
# The two rule files the app EDITS. The repo copies are seeds that ship with
# the code; a rule saved in the app has to outlive the container that saved it,
# so it is written to the volume, and the volume copy wins on read - exactly
# how the size sheet already works (_sizes_path). Until this existed the
# editor wrote into the container's own filesystem, which a redeploy replaces.
GOBO_OVERRIDES_LIVE = os.environ.get("GOBO_OVERRIDES_LIVE", "/data/gobo-overrides.csv")
GOBO_ALIASES_LIVE = os.environ.get("GOBO_ALIASES_LIVE", "/data/gobo-aliases.csv")

# The two rule files, and the columns their loaders read. A merchant's ruling on
# a model lives here rather than in the sheet, so replacing the sheet never
# throws the rulings away.
# kind -> (seed in the repo, live copy on the volume, the columns the loader reads)
GOBO_RULE_FILES = {
    "override": (GOBO_OVERRIDES_PATH, GOBO_OVERRIDES_LIVE,
                 ["Manufacturer", "Model", "Customer Email Domain", "Production Size (mm)"]),
    "alias": (GOBO_ALIASES_PATH, GOBO_ALIASES_LIVE, ["Manufacturer", "Store Model", "List Model"]),
}


def _rule_path(kind: str) -> str:
    """The rule file the app READS: the volume copy when there is one, else the
    seed that shipped with the code. Writes always go to the volume copy."""
    seed, live, _header = GOBO_RULE_FILES[kind]
    return live if os.path.isfile(live) else seed


def _gobo_rule_rows(kind: str) -> list:
    """Every row of one rule file, as plain dicts. A missing file is an empty
    list; an unreadable one RAISES, because reporting "no rules" for a file that
    exists would invite the merchant to add a duplicate of a rule already there."""
    header = GOBO_RULE_FILES[kind][2]
    path = _rule_path(kind)
    import csv as _csv
    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            return [{k: str(r.get(k) or "").strip() for k in header}
                    for r in _csv.DictReader(fh)]
    except FileNotFoundError:
        return []


def _write_gobo_rule_rows(kind: str, rows: list) -> None:
    """Atomic, keeping the five most recent generations. These files decide the
    glass a real order is cut from, so a half-written one must never be readable
    and a bad edit must always have something to go back to."""
    _seed, path, header = GOBO_RULE_FILES[kind]
    import csv as _csv
    import io as _io
    import shutil
    buf = _io.StringIO()
    w = _csv.DictWriter(buf, fieldnames=header, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in header})
    text = buf.getvalue()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if os.path.isfile(path):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        btmp = path + ".bak.tmp"
        shutil.copyfile(path, btmp)
        os.replace(btmp, f"{path}.{stamp}.bak")
        base = os.path.basename(path)
        d = os.path.dirname(path) or "."
        baks = sorted(f for f in os.listdir(d)
                      if f.startswith(base + ".") and f.endswith(".bak"))
        for stale in baks[:-5]:
            try:
                os.remove(os.path.join(d, stale))
            except OSError:
                pass
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.replace(tmp, path)
    # Force the next read to reload. The cache keys on mtime, and a write plus a
    # lookup inside the same clock tick would otherwise answer from the state
    # BEFORE the rule was saved - telling the merchant their ruling did nothing.
    _gobo_cache["mtime"] = None


def _sheet_size(raw) -> str:
    """A size cell as the label and the stock sheet use it: the plain number
    when the cell is one ("37.5", "86 mm", "86.0" -> "37.5", "86", "86"), the
    trimmed text otherwise, so a cell nobody can read still shows what it says."""
    txt = str(raw or "").strip()
    return (_clean_gobo_size(txt) or txt) if txt else ""


def _clean_gobo_size(raw) -> Optional[str]:
    """A production size, or None if it is not one. Free text is refused rather
    than stored: whatever is here is what the bench reads off the label."""
    txt = str(raw or "").strip().rstrip("m").rstrip("m").strip()
    if not txt:
        return None
    try:
        v = float(txt)
    except (TypeError, ValueError):
        return None
    if not (v == v) or v <= 0 or v > 500:   # NaN, zero, and nonsense are all not a size
        return None
    out = f"{v:.2f}".rstrip("0").rstrip(".")
    return out or None


def _sizes_path() -> str:
    """The size sheet the app reads: an uploaded copy on the data volume wins;
    the repo file remains the fallback (and the fresh-deploy seed)."""
    return GOBO_SIZES_LIVE if os.path.isfile(GOBO_SIZES_LIVE) else GOBO_SIZES_PATH


def _norm_key(v) -> str:
    return re.sub(r"\s+", " ", str(v or "").strip().lower())


def _loose_key(v) -> str:
    """Punctuation-insensitive key: "Source Four B-Size" == "Source Four (B Size)"."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(v or "").lower())).strip()


def _digit_key(v) -> str:
    """Loose key that also splits letter-digit boundaries, so the store's "EVE E100Z"
    meets the sheet's "EVE E-100Z" ("eve e 100 z" both ways)."""
    return re.sub(r"\s+", " ",
                  re.sub(r"(?<=[a-z])(?=[0-9])|(?<=[0-9])(?=[a-z])", " ", _loose_key(v))).strip()


def _word_run_in(needle: tuple, hay: tuple) -> bool:
    """True when needle appears in hay as a CONTIGUOUS word run. Contiguity is what
    keeps "Source Four B Size" out of "Source Four Effects Gate B Size"."""
    n = len(needle)
    if not n or n > len(hay):
        return False
    return any(hay[i:i + n] == needle for i in range(len(hay) - n + 1))


def _gobo_sizes() -> dict:
    """Model -> production size lookup from the merchant's CSV, reloaded when it,
    the aliases file or the overrides file changes. Multi-model cells ("VR8, VRX,
    VRXSR") index each model. Keys map to LISTS because the sheet genuinely
    repeats some (manufacturer, model) rows with different sizes; those must flag
    for review, never pick-one. Two companion files survive sheet replacements:
    data/gobo-aliases.csv maps spellings the store's dropdowns use ("40W/80W")
    onto sheet models ("40/80 Watt Range"); data/gobo-overrides.csv carries the
    merchant's rulings - fix a model's size (creating the row if the sheet lacks
    it), drop a row entirely (size "exclude"), or set a size that applies only to
    orders from one customer email domain."""
    try:
        sizes_path = _sizes_path()
        mtime = os.path.getmtime(sizes_path)
    except OSError:
        return _gobo_cache
    def _mt(p):
        try:
            return os.path.getmtime(p)
        except OSError:
            return None
    alias_path, override_path = _rule_path("alias"), _rule_path("override")
    # The paths are part of the key: the first save moves a rule file from the
    # seed to the volume, and that switch must reload even if the stamps match.
    mtime = (sizes_path, mtime, alias_path, _mt(alias_path), override_path, _mt(override_path))
    if _gobo_cache["mtime"] == mtime:
        return _gobo_cache
    import csv as _csv
    by_mm, by_model, by_mm_loose, by_model_loose = {}, {}, {}, {}
    by_mm_digit, by_model_digit, rows = {}, {}, []

    def index_model(entry: dict, nm: str, lm: str, model: str):
        key = _norm_key(model)
        if not key:
            return
        by_mm.setdefault((nm, key), []).append(entry)
        by_model.setdefault(key, []).append(entry)
        lkey = _loose_key(model)
        if lkey:
            by_mm_loose.setdefault((lm, lkey), []).append(entry)
            by_model_loose.setdefault(lkey, []).append(entry)
            rows.append((lm, tuple(lkey.split()), entry))
        dkey = _digit_key(model)
        if dkey:
            by_mm_digit.setdefault((lm, dkey), []).append(entry)
            by_model_digit.setdefault(dkey, []).append(entry)

    excludes, sets, domain_rules, dead_aliases = set(), {}, [], 0
    try:
        with open(override_path, newline="", encoding="utf-8-sig") as fh:
            for row in _csv.DictReader(fh):
                mfr = str(row.get("Manufacturer") or "").strip()
                model = str(row.get("Model") or "").strip()
                domain = str(row.get("Customer Email Domain") or "").strip().lstrip("@").lower()
                size = str(row.get("Production Size (mm)") or "").strip()
                key = (_norm_key(mfr), _norm_key(model))
                if not key[1] or not size:
                    continue
                if domain:
                    domain_rules.append({"key": key, "domain": domain, "size": size,
                                         "manufacturer": mfr, "model": model})
                elif size.lower() == "exclude":
                    excludes.add(key)
                else:
                    sets[key] = {"manufacturer": mfr, "model": model, "size": size}
    except FileNotFoundError:
        pass
    except Exception:
        logger.exception("gobo overrides: failed to load %s", override_path)

    try:
        with open(sizes_path, newline="", encoding="utf-8-sig") as fh:
            for row in _csv.DictReader(fh):
                entry = {
                    "manufacturer": str(row.get("Manufacturer") or "").strip(),
                    "model": str(row.get("Model") or "").strip(),
                    # Normalised as it is read: "86 mm" and "86.0" are 86, the key the
                    # bezel rule and the day sheet look up. Kept raw, an "86 mm" line
                    # booked 86mm glass instead of a 64.9 blank and a ring.
                    "production_size": _sheet_size(row.get("Closest Production Size (mm)")),
                    "review": str(row.get("Production Review") or "").strip(),
                }
                nm = _norm_key(entry["manufacturer"])
                lm = _loose_key(entry["manufacturer"])
                for model in entry["model"].split(","):
                    key = (nm, _norm_key(model))
                    if key in excludes:
                        continue
                    ruled = sets.get(key)
                    if ruled:
                        # A ruling on one model of a multi-model row must NOT mutate
                        # the shared entry, or its siblings inherit the wrong size.
                        e = dict(entry)
                        e["production_size"] = ruled["size"]
                        e["review"] = ""
                        index_model(e, nm, lm, model)
                    else:
                        index_model(entry, nm, lm, model)
    except Exception:
        logger.exception("gobo sizes: failed to load %s", sizes_path)
        return _gobo_cache
    # Rulings for models the sheet does not have become rows of their own.
    for key, ruled in sets.items():
        if key not in by_mm:
            entry = {"manufacturer": ruled["manufacturer"], "model": ruled["model"],
                     "production_size": ruled["size"], "review": ""}
            index_model(entry, key[0], _loose_key(ruled["manufacturer"]), ruled["model"])
    try:
        with open(alias_path, newline="", encoding="utf-8-sig") as fh:
            for row in _csv.DictReader(fh):
                mfr = str(row.get("Manufacturer") or "").strip()
                store = str(row.get("Store Model") or "").strip()
                target = str(row.get("List Model") or "").strip()
                hits = (by_mm.get((_norm_key(mfr), _norm_key(target)))
                        or by_model.get(_norm_key(target)) or [])
                for entry in hits:
                    index_model(entry, _norm_key(mfr), _loose_key(mfr), store)
                if not hits:
                    dead_aliases += 1
                    logger.warning("gobo aliases: %r -> %r matches nothing in the size list", store, target)
    except FileNotFoundError:
        pass
    except Exception:
        logger.exception("gobo aliases: failed to load %s", alias_path)
    try:
        sheet_at = datetime.fromtimestamp(os.path.getmtime(sizes_path), timezone.utc).isoformat()
    except OSError:
        sheet_at = None
    _gobo_cache.update({"mtime": mtime, "lookup_memo": {}, "maker_keys": None,
                        "by_mm": by_mm, "by_model": by_model,
                        "by_mm_loose": by_mm_loose, "by_model_loose": by_model_loose,
                        "by_mm_digit": by_mm_digit, "by_model_digit": by_model_digit,
                        "rows": rows, "domain_rules": domain_rules,
                        # Kept, not just counted: a model ruled "not a gobo" has
                        # to stop being reported as a miss, and until this was
                        # here the ruling only skipped SHEET rows - so excluding
                        # a model that was never on the sheet did nothing at all.
                        "excludes": excludes,
                        "health": {"models": len(by_model), "dead_aliases": dead_aliases,
                                   "overrides": len(sets) + len(excludes) + len(domain_rules),
                                   "sheet_at": sheet_at}})
    logger.info("gobo sizes: loaded %d model keys from %s (%d domain rules)",
                len(by_model), sizes_path, len(domain_rules))
    return _gobo_cache


_GOBO_INDEXES = {"strict": ("by_mm", "by_model"), "loose": ("by_mm_loose", "by_model_loose"),
                 "digit": ("by_mm_digit", "by_model_digit")}


def _gobo_resolve_key(cache: dict, manufacturer: str, key: str, which: str, own_only: bool = False):
    """Entries for one candidate key, or ("ambiguous"|None). Manufacturer+model
    first; model alone only when every row with that model is from one maker,
    and not at all when own_only asks for the maker's own rows alone."""
    mm_name, bm_name = _GOBO_INDEXES[which]
    entries = cache[mm_name].get((manufacturer, key)) if manufacturer else None
    if entries:
        return entries, None
    if own_only:
        return None, None
    candidates = cache[bm_name].get(key) or []
    keyfn = _norm_key if which == "strict" else _loose_key
    makers = {keyfn(e["manufacturer"]) for e in candidates}
    if len(makers) == 1:
        return candidates, None
    if len(makers) > 1:
        return None, "ambiguous"
    return None, None


def _gobo_contain(cache: dict, lmfr: str, words: tuple):
    """Rows whose model shares a contiguous word run with the part. Within the
    named maker's own rows both directions match: "viva" inside "Robin Viva",
    "BMFL" as the head of "BMFL Spot". The cross-maker fallback (for maker-name
    mismatches like store "Infinity" vs sheet "Showtec") only matches the store's
    full part INSIDE a sheet model, never the reverse: one-word sheet models like
    "Spot" or "Zoom" would otherwise latch onto anything containing that word.
    Cross-maker matches must also all come from a single maker."""
    if not words:
        return None, None
    hits = [(lm, e) for lm, rw, e in cache["rows"]
            if lm == lmfr and (_word_run_in(words, rw) or _word_run_in(rw, words))] if lmfr else []
    if not hits:
        hits = [(lm, e) for lm, rw, e in cache["rows"] if _word_run_in(words, rw)]
        if len({lm for lm, _ in hits}) > 1:
            return None, "ambiguous"
    return ([e for _, e in hits] or None), None


def _gobo_resolve_part(cache: dict, nmfr: str, lmfr: str, part: str, notes: set):
    """One store-written model name -> matching sheet rows, trying exact keys
    (strict, punctuation-insensitive, digit-boundary), then parenthetical and
    manufacturer-prefix stripping, then word-run containment.

    The order's own maker comes first. Its exact keys are tried before any
    other maker's, and another maker's model by the same name gives way to
    the maker's own models that START with the words named: 'Robe' 'Spot'
    printed Vari-Lite's 'VL4000 Beamwash, Spot' at 37.5, over Robe's own Spot
    160, Spot 250 and Spot 575 at 26.5 (Cameron: "make "robe spot" print
    Robe's size, not Vari-Lite's"). That is all that changed: a name that
    stayed with its own maker answers as it did, so 'Clay Paky' 'Profile'
    still says CHECK rather than pick Profile Plus SV from the many that
    contain the word; and a maker's own models that merely contain the words
    stay after the other maker's exact name, as a store maker can be a
    product family ('EVL' 'EVL Pro 250' is Mad's). Rows that disagree on
    size come back together, so the label says CHECK rather than guess."""
    variants = [(_norm_key(part), "strict"), (_loose_key(part), "loose"), (_digit_key(part), "digit")]
    stripped = re.sub(r"\([^)]*\)", " ", part)
    if stripped.strip() and stripped != part:
        variants += [(_norm_key(stripped), "strict"), (_loose_key(stripped), "loose"),
                     (_digit_key(stripped), "digit")]
    lpart = _loose_key(part)
    unprefixed = lpart[len(lmfr):].strip() if lmfr and lpart.startswith(lmfr + " ") else ""
    if unprefixed:
        variants.append((unprefixed, "loose"))
    keys = [kw for kw in dict.fromkeys(variants) if kw[0]]
    cands = [tuple(c.split()) for c in dict.fromkeys([lpart, _loose_key(stripped)]) if c]
    own_head = None
    if lmfr:
        for key, which in keys:
            entries, _note = _gobo_resolve_key(cache, nmfr if which == "strict" else lmfr, key, which, own_only=True)
            if entries:
                return entries
        own = [(rw, e) for lm, rw, e in cache["rows"] if lm == lmfr]
        # The maker's name typed into the model ('Robe Spot') is searched without it too.
        own_cands = cands + ([tuple(unprefixed.split())] if unprefixed and tuple(unprefixed.split()) not in cands else [])
        for words in own_cands:
            own_head = [e for rw, e in own if rw[:len(words)] == words] or None
            if own_head:
                break
    for key, which in keys:
        entries, note = _gobo_resolve_key(cache, nmfr if which == "strict" else lmfr, key, which)
        if entries:
            if own_head and any(_loose_key(e["manufacturer"]) != lmfr for e in entries):
                return own_head
            return entries
        if note == "ambiguous":
            notes.add("ambiguous")
    for words in cands:
        entries, note = _gobo_contain(cache, lmfr, words)
        if entries:
            return entries
        if note == "ambiguous":
            notes.add("ambiguous")
    return None


def _gobo_lookup(manufacturer: str, model: str, cache: Optional[dict] = None):
    """(entry, review_reason). The store's Model values can bundle several models
    ("ESPRITE, iESPRITE (Not iESPRITE LTL WB)", "Ikon LED / Ikon IR") and spell
    them differently from the sheet ("Source Four (B Size)" vs "Source Four
    B-Size", "Robin Viva" vs "Viva", "EVE E100Z" vs "EVE E-100Z"), so the whole
    value is tried first and then each comma or slash part, through exact keys,
    stripped forms and word-run containment. Never guesses: parts that match
    different sizes, duplicate sheet rows with different sizes, ambiguity and
    misses all come back as review reasons instead of a size."""
    cache = cache or _gobo_sizes()
    raw = str(model or "").strip()
    if not raw:
        return None, "No model specified on this item"
    nmfr, lmfr = _norm_key(manufacturer), _loose_key(manufacturer)
    # A MISS is the expensive case: it falls through every index and ends in a
    # word-run scan of all 2,155 sheet rows, measured at 0.63 ms against 0.008
    # ms for a hit. A small manufacturer sells the same fixtures over and over,
    # so the same miss is paid again for every line item of every order in the
    # queue: 67 ms to shape 900 orders with no misses, 1,799 ms at 30% misses.
    # The memo lives on the sheet cache and is thrown away with it, so a
    # re-uploaded sheet can never be answered from the old one.
    memo = cache.setdefault("lookup_memo", {})
    memo_key = (nmfr, raw)
    if memo_key in memo:
        return memo[memo_key]
    notes: set = set()
    resolved = _gobo_resolve_part(cache, nmfr, lmfr, raw, notes)
    if not resolved:
        parts = [p for p in re.split(r"[,/]", raw) if p.strip()]
        if len(parts) > 1:
            resolved = []
            # "Rogue R2 / R3" means Rogue R3, not any maker's R3: later parts first
            # try the first part's family words ("Rogue") in front of their own.
            head = " ".join(_loose_key(parts[0]).split()[:-1])
            for i, part in enumerate(parts):
                got = _gobo_resolve_part(cache, nmfr, lmfr, head + " " + part, notes) if i and head else None
                resolved.extend(got or _gobo_resolve_part(cache, nmfr, lmfr, part, notes) or [])
    def _out(result):
        memo[memo_key] = result
        return result

    if not resolved:
        if "ambiguous" in notes:
            return _out((None, "Model matches more than one manufacturer in the size list"))
        return _out((None, "Model not found in the size list"))
    sizes = {e["production_size"] for e in resolved}
    if len(sizes) > 1:
        return _out((None, "More than one production size listed for this model"))
    hit = resolved[0]
    if not hit["production_size"]:
        return _out((hit, (hit["review"] or "No production size listed for this model")))
    return _out((hit, None))


def _gobo_sheet_listing(who: Optional[str] = None) -> dict:
    """The whole sheet as the Size list tab shows it: every row with its holder,
    image and production sizes, and the merchant's rulings laid over it (a set
    size, an exclusion, a size for one customer's domain), plus rulings on
    models the sheet does not carry, which are rows of their own. Read from the
    sheet the lookup reads, so the tab and the label never disagree."""
    import csv as _csv
    sets, sets_raw, excl, domains = {}, {}, set(), {}
    for r in _gobo_rule_rows("override"):
        mfr, model = str(r.get("Manufacturer") or "").strip(), str(r.get("Model") or "").strip()
        key = (_norm_key(mfr), _norm_key(model))
        size = str(r.get("Production Size (mm)") or "").strip()
        dom = str(r.get("Customer Email Domain") or "").strip().lstrip("@").lower()
        if not key[1] or not size:
            continue
        sets_raw.setdefault(key, (mfr, model))
        if dom:
            domains.setdefault(key, []).append({"domain": dom, "size": size})
        elif size.lower() == "exclude":
            excl.add(key)
        else:
            sets[key] = size
    aliases = [{"manufacturer": str(r.get("Manufacturer") or ""), "store_model": str(r.get("Store Model") or ""),
                "list_model": str(r.get("List Model") or "")} for r in _gobo_rule_rows("alias")]
    path = _sizes_path()
    rows, seen = [], set()
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for r in _csv.DictReader(fh):
            mfr = str(r.get("Manufacturer") or "").strip()
            model = str(r.get("Model") or "").strip()
            if not model:
                continue
            key = (_norm_key(mfr), _norm_key(model))
            seen.add(key)
            row = {"manufacturer": mfr, "model": model,
                   "glass": str(r.get("Glass Diameter (mm)") or "").strip(),
                   "image": str(r.get("Image Diameter (mm)") or "").strip(),
                   "produced": _sheet_size(r.get("Closest Production Size (mm)")),
                   "undercut": str(r.get("Undercut (mm)") or "").strip(),
                   "review": str(r.get("Production Review") or "").strip(),
                   "notes": str(r.get("Notes") or "").strip()}
            if key in excl:
                row["ruling"] = "exclude"
            elif key in sets:
                row["ruling"] = sets[key]
            if key in domains:
                row["domain_rulings"] = domains[key]
            rows.append(row)
    for key, (mfr, model) in sets_raw.items():
        if key in seen:
            continue
        row = {"manufacturer": mfr, "model": model, "glass": "", "image": "", "produced": "", "undercut": "",
               "review": "", "notes": "Not on the sheet: a ruling made in the app.", "off_sheet": True}
        if key in excl:
            row["ruling"] = "exclude"
        elif key in sets:
            row["ruling"] = sets[key]
        if key in domains:
            row["domain_rulings"] = domains[key]
        rows.append(row)
    rows.sort(key=lambda x: (x["manufacturer"].lower(), x["model"].lower()))
    try:
        updated = datetime.fromtimestamp(os.path.getmtime(path), timezone.utc).isoformat()
    except OSError:
        updated = None
    return {"rows": rows, "aliases": aliases, "count": len(rows),
            "shorthand": {"makers": _GOBO_MAKER_SHORT, "words": _GOBO_WORD_GROUPS},
            "rulings": len(sets) + len(excl) + sum(len(v) for v in domains.values()),
            "sheet": {"live": path == GOBO_SIZES_LIVE, "updated": updated},
            "can_edit": team._may_edit_sizes(who)}


def _order_email_domain(o: dict) -> str:
    email = str(o.get("email") or o.get("contact_email")
                or (o.get("customer") or {}).get("email") or "")
    return email.split("@")[-1].strip().lower() if "@" in email else ""


def _gobo_domain_size(manufacturer: str, model: str, entry, domain: str, cache: Optional[dict] = None):
    """A size ruling that applies only to orders from one customer email domain
    (e.g. Ayrton Diablo prints 25 for dbnaudile.co.uk, 25.5 for everyone else).
    Matched against both the store-written model name and the resolved sheet row."""
    if not domain:
        return None
    keys = {(_norm_key(manufacturer), _norm_key(model))}
    if entry:
        keys.add((_norm_key(entry["manufacturer"]), _norm_key(entry["model"])))
    for r in (cache or _gobo_sizes())["domain_rules"]:
        if r["domain"] == domain and r["key"] in keys:
            return r["size"]
    return None


# Shorthand the trade writes for makers and words, for the Size list's search
# and for reading a maker off the front of a typed name. The store's own
# spellings of a model belong in the aliases file instead, where the label
# reads them too: nothing here changes what a label prints.
# Not "vl" for Vari-Lite: it starts their models (VL2500), and "vl 2500 spot"
# was read as maker Vari-Lite, model "2500 spot", which found another row.
_GOBO_MAKER_SHORT = {"adj": "American DJ", "hes": "High End Systems", "glp": "German Light Products",
                     "rj": "Robert Juliat", "cp": "Clay Paky"}
# Words written either way: any one of a group finds the others.
_GOBO_WORD_GROUPS = [["jr", "jnr", "junior"], ["s4", "source four"],
                     ["1", "one"], ["2", "two"], ["3", "three"], ["4", "four"], ["5", "five"],
                     ["6", "six"], ["7", "seven"], ["8", "eight"], ["9", "nine"], ["10", "ten"]]


def _gobo_maker_keys(cache: dict) -> dict:
    """Loose key -> sheet maker, for every way a typed name can start with a
    maker: its whole name, run together ("claypaky"), a shorthand ("adj"), or
    the first words of its name when no other maker starts the same way
    ("martin" for Martin Professional, "high end" for High End Systems; not
    "light", which starts two) and no model on the sheet has those words
    ("studio" is in High End Systems' Studio Spot 575, so it is not read as
    Studio Due). Built once per sheet snapshot."""
    keys = cache.get("maker_keys")
    if keys is not None:
        return keys
    makers = sorted({e["manufacturer"] for _lm, _w, e in (cache.get("rows") or []) if e.get("manufacturer")})
    by_loose = {_loose_key(m): m for m in makers if _loose_key(m)}
    starts: dict = {}
    for lk in by_loose:
        w = lk.split()
        for n in range(1, len(w)):
            if len(w[0]) >= 3:
                starts.setdefault(" ".join(w[:n]), set()).add(lk)
    keys = {}
    for lk, m in by_loose.items():
        keys[lk] = m
        keys.setdefault(lk.replace(" ", ""), m)
    in_models = {" " + " ".join(w) + " " for _lm, w, _e in (cache.get("rows") or [])}
    for pre, owners in starts.items():
        if len(owners) == 1 and pre not in keys and not any(" " + pre + " " in t for t in in_models):
            keys[pre] = by_loose[next(iter(owners))]
    model_words = {x for _lm, w, _e in (cache.get("rows") or []) for x in w}
    for short, m in _GOBO_MAKER_SHORT.items():
        # A shorthand that starts a model's word is that model's, not a maker.
        if _loose_key(m) in by_loose and not any(x.startswith(short) and x != short for x in model_words):
            keys.setdefault(short, by_loose[_loose_key(m)])
    cache["maker_keys"] = keys
    return keys


def _gobo_split_maker(q: str, cache: dict):
    """(maker, model) when the typed name starts with a maker, the longest one
    that fits, leaving the model as it was written; ("", q) otherwise. At
    least one word is always left for the model."""
    words = _loose_key(q).split()
    keys = _gobo_maker_keys(cache)
    # A maker's name alone ("clay paky") names no model: "clay" and "paky"
    # would be read as a maker and a model.
    if " ".join(words) in keys:
        return "", q
    for n in range(min(4, len(words) - 1), 0, -1):
        maker = keys.get(" ".join(words[:n]))
        if not maker:
            continue
        toks, used, i = q.split(), 0, 0
        while i < len(toks) and used < n:
            used += len(_loose_key(toks[i]).split())
            i += 1
        # A typed word that runs over the maker's end ("High-EndSolaSpot")
        # cannot be cut cleanly: read the whole name as the model instead.
        if used == n and i < len(toks):
            return maker, " ".join(toks[i:])
    return "", q


def _gobo_check(q: str) -> dict:
    """What a label prints for a fixture named in free text, through the very
    lookup the labels print with. The whole name is tried as a model first:
    a maker's name also starts other makers' models (Showtec's Infinity IS
    100, Mad's EVL Pro 250), and the sheet knows those as models. Then the
    maker read off the front and the rest as its model. The first that finds
    a row answers; if none does, the maker's reading gives the reason, being
    the more particular. A name ruled not a gobo prints no size, as the label
    shapes it, and is said to be. The sizes set for one customer come with
    the answer."""
    cache = _gobo_sizes()
    # A memo of its own: a typed name is not an order line, and the label's
    # memo would keep every name anyone typed until the sheet next reloads.
    view = dict(cache)
    view["lookup_memo"] = {}
    q = re.sub(r"\s+", " ", str(q or "")).strip()[:120]
    maker, model = _gobo_split_maker(q, cache)
    if maker and (_norm_key(maker), _norm_key(model)) in (cache.get("excludes") or set()):
        return {"q": q, "manufacturer": maker, "model": model, "match": None, "size": "",
                "reason": "", "excluded": True, "domains": []}
    got = None
    for mfr, mdl in [("", q)] + ([(maker, model)] if maker else []):
        entry, reason = _gobo_lookup(mfr, mdl, cache=view)
        if entry:
            got = (mfr, mdl, entry, reason)
            break
        if got is None or mfr:
            got = (mfr, mdl, entry, reason)
    mfr, mdl, entry, reason = got
    keys = {(_norm_key(mfr), _norm_key(mdl))}
    if entry:
        keys.add((_norm_key(entry["manufacturer"]), _norm_key(entry["model"])))
    domains = [{"domain": r["domain"], "size": r["size"]} for r in cache.get("domain_rules") or [] if r["key"] in keys]
    return {"q": q, "manufacturer": mfr, "model": mdl,
            "match": ({"manufacturer": entry["manufacturer"], "model": entry["model"]} if entry else None),
            "size": (entry["production_size"] if entry and not reason else ""),
            "reason": reason or "", "excluded": False, "domains": domains}


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as core.NAME and sibling.NAME, never a copied name.
import copilot as core  # noqa: E402
from gizmo import team  # noqa: E402
