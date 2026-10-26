"""Moving the stock sheet in (plan 4 of the stock move), the owner's: the
stock app's export (tools/stock_move/export_from_stock_app.py) arrives in
parts, each stock app username is matched to a Reactor account, a check has
the converter (tools/stock_import.py) convert it into a folder of its own and
prove it, changing nothing, and a move has the converter install exactly what
it proved. The stock sheet goes live here, last: a move that stops part way
leaves it where it was, and runs again.

The converter runs as a child process because it switches the stock stores'
folder for its whole process (stock_store.rooted), which must never happen
inside the running server. A check or a move runs on a worker thread with its
state on disk, so a page that closes can come back to it, and a run left
running by a process that has gone (a restart) says it was interrupted.
"""
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone

from gizmo import stock, stock_store, team

logger = logging.getLogger("shopify_mcp.copilot")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "stock_import.py")
EXPORT_CAP = 256 * 1024 * 1024     # far more than a stock sheet should ever hold
PART_CAP = 4 * 1024 * 1024         # of text, per part the page sends
RUN_SECONDS = 30 * 60              # a check or a move that takes longer is stopped
NAMES_SECONDS = 10 * 60            # reading the names out of a large export

_worker = None                     # the thread running a check or a move, in this process
_starting = threading.Lock()       # one start at a time


def move_dir() -> str:
    """Beside the stock stores, in a folder of its own that is never taken
    for a stock store (those are named stock_...)."""
    return os.path.join(os.path.dirname(stock_store.STOCK_SETTINGS_PATH), "stock-move")


def _path(name: str) -> str:
    return os.path.join(move_dir(), name)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(name: str):
    try:
        with open(_path(name), encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, ValueError):
        return None


def _private(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = path + ".writing"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def _write(name: str, doc) -> None:
    _private(_path(name), json.dumps(doc))


def _write_run(run: dict) -> None:
    _write("run.json", run)


def _owner(uid: str) -> None:
    if team._team_role(uid) != "master":
        raise stock.Refused(403, "Only the owner can move the stock sheet in.")


def _not_live() -> None:
    if stock.is_live():
        raise stock.Refused(409, "The stock sheet has already moved in.")


def _running() -> bool:
    run = _read("run.json")
    return bool(run and run.get("state") == "running" and _worker is not None and _worker.is_alive())


def _tool(args: list, timeout: int) -> tuple:
    """(exit code, what it printed, what it said went wrong): the converter, as a child."""
    r = subprocess.run([sys.executable, TOOL] + args, capture_output=True, text=True, timeout=timeout,
                       env=dict(os.environ))
    return r.returncode, r.stdout, r.stderr


def _said(err: str) -> str:
    """The converter's refusal, as a sentence."""
    line = next((l for l in reversed((err or "").strip().splitlines()) if l.startswith("refused: ")), "")
    line = line[len("refused: "):].strip()
    return (line[:1].upper() + line[1:]).rstrip(".") + "." if line else ""


def _forget_upload() -> None:
    for name in ("export.partial", "export.json", "upload.json"):
        try:
            os.remove(_path(name))
        except FileNotFoundError:
            pass


def _exported_at() -> str:
    """When the export was made, read from its first lines (the exporter writes it near the top)."""
    try:
        with open(_path("export.json"), encoding="utf-8") as fh:
            m = re.search(r'"exported_at"\s*:\s*"([^"]+)"', fh.read(65536))
        return m.group(1) if m else ""
    except OSError:
        return ""


# ---- the export, in parts ------------------------------------------------------------

def receive_part(uid: str, upload, index, total, text, sha256) -> dict:
    """One part of the export, in order. The last checks the whole against its
    checksum and has the converter read the names in it."""
    _owner(uid)
    _not_live()
    if _running():
        raise stock.Refused(409, "A check or a move is running: wait for it to finish.")
    upload, text = str(upload or ""), text if isinstance(text, str) else ""
    if not upload or not isinstance(index, int) or not isinstance(total, int) or not 0 <= index < total:
        raise stock.Refused(400, "That is not a part of an export the page is sending.")
    data = text.encode("utf-8")
    if len(data) > PART_CAP:
        raise stock.Refused(400, "That part of the export is over 4 MB: the page sends smaller ones.")
    meta = _read("upload.json")
    if index == 0:
        _forget_upload()
        meta = {"upload": upload, "total": total, "next": 0, "bytes": 0, "done": False}
        _private(_path("export.partial"), "")
    elif not meta or meta.get("done") or (meta.get("upload"), meta.get("total"), meta.get("next")) != (upload, total, index):
        _forget_upload()
        raise stock.Refused(409, "That part of the export came out of order: send the export again.")
    if meta["bytes"] + len(data) > EXPORT_CAP:
        _forget_upload()
        raise stock.Refused(413, "That export is over 256 MB, far more than the stock sheet holds: check it is the right file.")
    with open(_path("export.partial"), "ab") as fh:
        fh.write(data)
    meta["bytes"] += len(data)
    meta["next"] = index + 1
    if index + 1 < total:
        _write("upload.json", meta)
        return {"received": index + 1, "total": total}
    digest = hashlib.sha256()
    with open(_path("export.partial"), "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != str(sha256 or "").lower():
        _forget_upload()
        raise stock.Refused(400, "The export did not arrive whole: send it again.")
    os.replace(_path("export.partial"), _path("export.json"))
    code, out, err = _tool(["--export", _path("export.json"), "--list-people"], NAMES_SECONDS)
    if code != 0:
        _forget_upload()
        said = _said(err)
        if said.lower().startswith("not a stock export"):
            raise stock.Refused(400, "That file is not a stock export: make it with the stock app's exporter.")
        raise stock.Refused(400, said or "That file could not be read as the stock app's export.")
    meta.update(done=True, sha256=digest.hexdigest(), names=json.loads(out), exported_at=_exported_at(), at=_now(), by=uid)
    _write("upload.json", meta)
    return status(uid)


# ---- a check, and the move ---------------------------------------------------------------

def start(uid: str, kind: str, people) -> dict:
    """Start a check (convert and prove; nothing changes) or the move (the
    same, then install and go live), on a worker thread."""
    global _worker
    _owner(uid)
    if kind not in ("check", "move"):
        raise stock.Refused(400, "Unknown op.")
    _not_live()
    with _starting:
        if _running():
            raise stock.Refused(409, "A check or a move is already running: wait for it to finish.")
        meta = _read("upload.json")
        if not (meta and meta.get("done")):
            raise stock.Refused(409, "Send the stock app's export first.")
        people = {str(k): str(v) for k, v in (people or {}).items()}
        names = meta.get("names") or {}
        missing = sorted((set(names.get("history") or []) | set(names.get("logins") or [])) - set(people))
        if missing:
            raise stock.Refused(400, "Match every stock app name to a Reactor account: " + ", ".join(missing) + ".")
        users = team._load_users()["users"]
        unknown = sorted(n for n, a in people.items() if a not in users or users[a].get("deleted"))
        if unknown:
            raise stock.Refused(400, "Matched to an account that does not exist: " + ", ".join(unknown) + ".")
        if kind == "move":
            last = _read("run.json") or {}
            if not (last.get("kind") == "check" and last.get("state") == "passed"
                    and last.get("sha256") == meta.get("sha256") and last.get("people") == people):
                raise stock.Refused(409, "Check this export first: a move needs a passing check of the same export, "
                                         "matched to the same people.")
        run = {"kind": kind, "state": "running", "at": _now(), "by": uid, "sha256": meta.get("sha256"), "people": people}
        _write_run(run)
        _worker = threading.Thread(target=_execute, args=(run,), name="stock-move", daemon=True)
        _worker.start()
    return status(uid)


def _execute(run: dict) -> None:
    """The converter, then (for a move that it proved and installed) going live.
    Its outcome is written to disk whatever happens."""
    folder = _path("run-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f") + "-" + run["kind"])
    people, report = os.path.join(folder, "people.json"), os.path.join(folder, "report.json")
    try:
        _private(people, json.dumps(run["people"]))
        args = ["--export", _path("export.json"), "--people", people, "--out", os.path.join(folder, "stores"),
                "--json-report", report] + (["--install"] if run["kind"] == "move" else [])
        code, _out, err = _tool(args, RUN_SECONDS)
        try:
            with open(report, encoding="utf-8") as fh:
                got = json.load(fh)
        except (FileNotFoundError, ValueError):
            got = {}
        found = got.get("differences") or []
        run.update(differences=found[:50], more=max(0, len(found) - 50), counts=got.get("counts"))
        if code == 0 and run["kind"] == "check":
            run["state"] = "passed"
        elif code == 0:
            _go_live(run)
            run["state"] = "done"
        elif code == 1:
            run.update(state="failed", words=f"{len(found)} difference{'' if len(found) == 1 else 's'} between the "
                                             "export and what Reactor would hold, so nothing was moved.")
        else:
            run.update(state="refused", words=_said(err) or "The converter stopped without saying why. The server's log has it.")
            if code != 2 and code != 3:
                logger.error("stock move: the converter stopped (%s): %s", code, (err or "")[-2000:])
    except subprocess.TimeoutExpired:
        run.update(state="failed", words="It took longer than 30 minutes, so it was stopped and nothing was moved.")
    except Exception as e:
        logger.exception("stock move: the %s did not finish", run["kind"])
        run.update(state="failed", words=f"It did not finish ({type(e).__name__}). The server's log has the detail.")
    finally:
        run["finished_at"] = _now()
        _write_run(run)


def _go_live(run: dict) -> None:
    """After the converter has installed what it proved: the moment of going
    live (last of the stores), the Stock tab for each person matched, the
    bookings that never reached the stock app tried again here, the first
    stock backup and the history line."""
    from gizmo import activity, stock_backups, stock_link
    uid = run["by"]
    with stock._lock:
        stock.forget_memory()
        settings = stock_store.load_settings()
        at = stock.now_iso()
        settings["live_since"] = at
        settings["moved_in"] = {"at": at, "by": uid, "sha256": run["sha256"], "people": run["people"],
                                "counts": run.get("counts")}
        stock_store.write_settings(settings)
    d = team._load_users()
    granted = []
    for acct in sorted(set(run["people"].values())):
        u = d["users"].get(acct)
        if not u or u.get("deleted") or u.get("role") == "master":
            continue
        tabs = list(u["tabs"]) if isinstance(u.get("tabs"), list) else list(team.DEFAULT_TABS)
        if "stock" not in tabs:
            u["tabs"] = tabs + ["stock"]
            granted.append(acct)
    if granted:
        team._write_users(d)
        for acct in granted:
            activity._track(uid, "team", "changed tab access",
                            f"{team._team_name(acct)} can open the Stock tab (the stock sheet moved in)")
    pending = stock_link._load_zeta_pending()
    for entry in pending.values():
        entry["tries"] = 0
        entry.pop("stuck", None)
    if pending:
        stock_link._write_zeta_pending(pending)
    who = stock.actor(uid)
    try:
        stock_backups.make_backup(who)
    except Exception:
        logger.exception("stock move: the first stock backup was not made")
    counts = run.get("counts") or {}
    with stock._lock:
        st = stock.state()
        stock.commit(st, changed=set(), history=[stock.history_row(
            who, "moved_in", detail=f"moved in from the stock app: {counts.get('items', 0)} lines, "
                                    f"{counts.get('history', 0)} history entries")])


# ---- where it stands -------------------------------------------------------------------

def status(uid: str) -> dict:
    """Everything the window shows: live or not, the export received, the
    names to match and the accounts to match them to, the last run, and the
    bookings queued for the stock app."""
    from gizmo import stock_link
    _owner(uid)
    run = _read("run.json")
    if run and run.get("state") == "running" and not (_worker is not None and _worker.is_alive()):
        run.update(state="interrupted", words="Reactor restarted while this was running, so it did not finish. Run it again.")
        _write_run(run)
    meta = _read("upload.json")
    done = bool(meta and meta.get("done"))
    settings = stock_store.load_settings()
    users = team._load_users()["users"]
    pending = stock_link._load_zeta_pending()
    moved = settings.get("moved_in")
    if isinstance(moved, dict):
        moved = dict(moved, by_name=team._team_name(moved.get("by")) or "")
    return {"live": bool(settings.get("live_since")), "moved_in": moved,
            "upload": {k: meta.get(k) for k in ("bytes", "sha256", "exported_at", "at")} if done else None,
            "names": meta.get("names") if done else None,
            "accounts": sorted(({"id": k, "name": u.get("name") or u.get("username") or k, "username": u.get("username") or ""}
                                for k, u in users.items() if not u.get("deleted")), key=lambda a: a["name"].lower()),
            "run": run, "queue": {"pending": len(pending), "stuck": sum(1 for e in pending.values() if e.get("stuck"))}}
