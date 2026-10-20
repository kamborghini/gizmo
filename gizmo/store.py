"""The store: every JSON store on the volume is read and written here, through
the one writer (_write_json_store), with the cache, the poison guard and the
private-file writer. Moved out of copilot.py (stage 4 of the 14 October
audit) as the floor every area stands on: it imports nothing from the app
above it (t_the_floor_imports_nothing_above_it), so an area imports it
directly, as `from gizmo import store as jsonstore`.

The store names no area. An area that keeps a copy built from a store asks
to hear when that store is forgotten (when_forgotten): the CRM's kept board.
"""
import logging
import os
import json
from typing import Optional
import perf

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


class StoreUnwritable(RuntimeError):
    """A store the poison guard has paused. The one writer raises this; a
    caller that would rather stay silent checks _store_writable first and
    says why, which is what every writer already did."""


# A store that fails to PARSE (as opposed to not existing) must never be
# overwritten: loaders would hand back an empty default and the next write
# would persist the wipe. Unreadable stores pause their writers instead,
# and /api/status lists them so the problem is visible in Settings.
_poisoned_stores: set = set()


@perf.timed("store")      # Server-Timing: reading a store from disk
def _load_json_store(path: str, key, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        _poisoned_stores.discard(path)
        if key is None:
            return data if isinstance(data, (dict, list)) else default
        return data.get(key, default) if isinstance(data, dict) else default
    except FileNotFoundError:
        _poisoned_stores.discard(path)
        return default
    except Exception:
        if path not in _poisoned_stores:
            logger.exception("store unreadable: %s. Writes to it are paused so the "
                             "broken file is preserved for repair.", path)
        _poisoned_stores.add(path)
        return default


def _store_writable(path: str) -> bool:
    if path in _poisoned_stores:
        logger.error("refusing to overwrite unreadable store %s", path)
        return False
    return True


# path -> (stat key, the object the loader returned). The three busiest stores
# were parsed from disk on every request that needed them - the CRM at up to
# tens of megabytes, on the event loop, twenty times a request cycle. The
# cache is keyed on the FILE (mtime, size, inode), so anything that replaces
# the file - a restore, a test writing it directly, a repair by hand - is a
# miss, and nobody has to remember to invalidate. Two rules keep it honest:
# the writer refreshes the entry after a successful write and forgets it on a
# failed one ("memory never outlives a failed write"), and a caller that
# mutated the object and then could not write must forget it too.
_json_cache: dict = {}
_cached_paths: set = set()   # the stores read through _load_json_cached


def _stat_key(path: str):
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size, st.st_ino)
    except OSError:
        return None


def _load_json_cached(path: str, key, default, prepare=None):
    """_load_json_store with a cache keyed on the file. `prepare` runs once
    per file version, on the miss, and its result is what is cached - for a
    store whose loader normalises what it read."""
    _cached_paths.add(path)
    sk = _stat_key(path)
    hit = _json_cache.get(path)
    if hit is not None and sk is not None and hit[0] == sk:
        return hit[1]
    obj = _load_json_store(path, key, default)
    if prepare is not None:
        obj = prepare(obj)
    if sk is not None and path not in _poisoned_stores:
        _json_cache[path] = (sk, obj)
    return obj


# What else goes when a store's cached copy is forgotten: an area that keeps
# something built from a store (the CRM's kept board) asks to hear, so the
# store names no area. Each is called with the path that was forgotten.
_forget_hooks: list = []


def when_forgotten(fn) -> None:
    """Call fn(path) each time a store's cached copy is forgotten."""
    _forget_hooks.append(fn)


def _forget_store(path: str) -> None:
    """Drop the cached copy: the next read comes from disk."""
    _json_cache.pop(path, None)
    for fn in _forget_hooks:
        fn(path)


# Areas that keep a whole store in memory (a `_mem` copy) say how to let go
# of it: drop(paths) clears each of its copies whose path is in paths (every
# one when paths is None) and returns the paths it let go of. Restore and
# shop/redact replace or remove files under a running process, and a copy
# that outlived its file put the old contents straight back (the mailbox and
# Files after a redact, the loan register after a restore). Each module
# clears its own names, so none reaches into another's.
_holders: list = []


def holds_in_memory(drop) -> None:
    """Register how a module lets go of the stores it holds in memory."""
    _holders.append(drop)


def _drop_memory_stores(paths=None) -> None:
    """Forget the in-memory copy of each store (every one when `paths` is
    None) and its cached parse, so the next read comes from disk."""
    for drop in _holders:
        for path in drop(paths):
            _forget_store(path)


@perf.timed("store")      # Server-Timing: writing a store to disk
def _write_json_store(path: str, key: Optional[str], data, *, private: bool = False) -> None:
    """The one way a store reaches disk.

    Thirty-five hand-written copies of this loop had four safety properties
    between them - the poison guard, allow_nan=False, an atomic replace, and
    owner-only permissions for credential-bearing files - applied to different
    subsets: NaN was refused on four stores, 0600 on three. A store could only
    get every property by every writer remembering every line. Now it gets
    them by calling this.

    `key` wraps the data as {key: data}, the shape the loaders expect; None
    writes the object itself. allow_nan is always False: Python will happily
    WRITE NaN, which is not JSON, and the next read would poison the store."""
    if not _store_writable(path):
        _forget_store(path)
        raise StoreUnwritable(path)
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        payload = json.dumps({key: data} if key is not None else data, allow_nan=False)
        tmp = path + ".tmp"
        if private:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            fh = os.fdopen(fd, "w", encoding="utf-8")
        else:
            fh = open(tmp, "w", encoding="utf-8")
        with fh:
            fh.write(payload)
        os.replace(tmp, path)
    except Exception:
        _forget_store(path)      # memory never outlives a failed write
        raise
    if private:
        try:
            os.chmod(path, 0o600)   # a file written before it was private keeps its mode otherwise
        except OSError:
            pass
    # What was just written IS the store now; a re-parse would only produce
    # an equal object more slowly. Only for the stores read through the cache:
    # kept for every path, each booked label (a file per shipment, about a
    # megabyte with its print images) stayed in memory until the next
    # restart, pruned from disk or not.
    if path in _cached_paths:
        _json_cache[path] = (_stat_key(path), data)
    else:
        _json_cache.pop(path, None)


def _write_private_json(path: str, key: str, d: dict) -> None:
    """Owner-only, and silent when the poison guard refuses. These stores hold
    accounting records, the contents of bank statements and remittances, and
    the exception list built from both: data taken out of Xero and the accounts
    mailbox deserves the same file mode as the tokens that fetched it."""
    if not _store_writable(path):
        return
    _write_json_store(path, key, d, private=True)
