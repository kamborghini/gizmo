"""Page layouts: how each person has arranged the cards on a report screen.
Moved out of copilot.py (stage 4 of the 14 October audit); its route is in
gizmo/routes/layouts.py. Read as `layouts.NAME`.
"""
import logging
import os
import re
import asyncio
from gizmo import store as jsonstore

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


LAYOUTS_PATH       = os.environ.get("LAYOUTS_PATH", "/data/layouts.json")    # each person's arrangement of the cards on a screen


# ---------------------------------------------------------------------------
# Page layouts: how each person has arranged the cards on a report screen.
# A layout is an order and a hidden list of card ids, kept per account, so
# rearranging your Overview never moves a colleague's cards and it follows you
# to another machine. The server does not know which cards a screen renders
# and does not try to: the page drops ids it did not render when it merges.
# ---------------------------------------------------------------------------

# Every view the page's setView shows except Chat, which is a log and a
# composer with no cards to arrange.
LAYOUT_VIEWS = ("overview", "seo", "keywords", "products", "customers", "liability",
                "recon", "forecast", "connector", "crm", "loans", "mail", "files", "team",
                "labels", "sizes", "memory", "skills", "guide")
# The page's own card id pattern, matched with fullmatch: with re.match a `$`
# would also accept an id that ends in a newline.
_LAYOUT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
LAYOUT_MAX_IDS = 64
# Two lists of 64 ids at 48 characters each is under 7KB of JSON, so a body
# past 8KB is not something the page sends.
LAYOUT_MAX_BODY = 8 * 1024
# The load, change and write in _save_layout have no await between them, so
# today two saves cannot interleave on the one event loop. The lock keeps that
# true on the day someone adds one, instead of one person's Done silently
# dropping another's layout.
_layouts_lock = asyncio.Lock()


def _load_layouts() -> dict:
    """{uid: {view: {"order": [...], "hidden": [...]}}}, read fresh each time.
    Not the cached loader: _save_layout changes what it is handed, and a
    fresh object means a failed write leaves nothing changed in memory."""
    d = jsonstore._load_json_store(LAYOUTS_PATH, "layouts", {})
    return d if isinstance(d, dict) else {}


def _layouts_for(uid: str) -> dict:
    mine = _load_layouts().get(uid)
    return mine if isinstance(mine, dict) else {}


def _clean_layout_change(body: dict):
    """(problem, view, layout) for a save or a reset. `problem` is the plain
    sentence a 400 carries, empty when the change is sound; `layout` is None
    for a reset. A card named twice keeps the first place it was given."""
    view = body.get("view")
    if not isinstance(view, str) or view not in LAYOUT_VIEWS:
        return "That screen has no layout to save.", "", None
    if "reset" in body:
        if body["reset"] is not True:
            return "Reset is either true or left out.", "", None
        return "", view, None
    layout = {}
    for name in ("order", "hidden"):
        ids = body.get(name)
        if not isinstance(ids, list):
            return "A layout needs an order list and a hidden list.", "", None
        if len(ids) > LAYOUT_MAX_IDS:
            return f"A layout holds at most {LAYOUT_MAX_IDS} cards.", "", None
        clean = []
        for i in ids:
            if not isinstance(i, str) or not _LAYOUT_ID.fullmatch(i):
                return ("A card id is up to 48 lower-case letters, digits and hyphens, "
                        "starting with a letter or digit."), "", None
            if i not in clean:
                clean.append(i)
        layout[name] = clean
    return "", view, layout


def _save_layout(uid: str, view: str, layout) -> dict:
    """Set one person's layout for one view, or remove it when `layout` is
    None, and return that person's whole map. The caller holds _layouts_lock.
    Private: it is one file of everyone's entries, and nothing but the app
    has a reason to read it."""
    d = _load_layouts()
    mine = d.get(uid) if isinstance(d.get(uid), dict) else {}
    if layout is None:
        if view not in mine:
            return mine              # nothing saved for that screen, nothing to write
        mine.pop(view)
    else:
        mine[view] = layout
    if mine:
        d[uid] = mine
    else:
        d.pop(uid, None)             # nothing saved leaves no empty entry behind
    jsonstore._write_json_store(LAYOUTS_PATH, "layouts", d, private=True)
    return mine


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as core.NAME and sibling.NAME, never a copied name.
import copilot as core  # noqa: E402
