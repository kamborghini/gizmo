"""Backup: the zip of everything restorable (credentials excluded), the weekly
snapshots and their record. Moved out of copilot.py (stage 4 of the 14
October audit); its routes, the download and the restore, are in
gizmo/routes/backup.py. Read as `backup.NAME`.
"""
import logging
import glob
import os
import json
from datetime import datetime, timedelta, timezone
import google_mail
import xero as xero_api
from gizmo.config import _env_num
from gizmo import store as jsonstore

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


# The repository, where data/ ships with the code. This module is one
# folder down from where copilot.py built this path from its own file.
_REPO = os.path.dirname(os.path.dirname(__file__))


BACKUP_STATE_PATH = os.environ.get("BACKUP_STATE_PATH", "/data/backup_state.json")
BACKUP_SNAPSHOT_DIR = os.environ.get("BACKUP_SNAPSHOT_DIR", "/data/snapshots")
BACKUP_KEEP = 4
# Per-file ceiling inside a backup. It exists so one runaway store cannot make
# the whole archive un-downloadable, NOT as a retention rule: a CRM holding an
# imported sales history will pass 10MB, and the backup meant to protect it
# must not be the thing that quietly stops including it.
BACKUP_FILE_MAX = _env_num(int, os.environ.get("BACKUP_FILE_MAX", str(60 * 1024 * 1024)), str(60 * 1024 * 1024), "BACKUP_FILE_MAX")

# Files of removed features that can still sit on the volume until somebody
# deletes them: old sign-ins' refresh tokens (never in a backup, like every
# credential) and stores nothing reads or scrubs any more. A backup leaves
# them out and a restore refuses them. Named from the settings the removed
# code read, with its defaults, so an overridden path is still caught.
_RETIRED_FILES = frozenset(os.path.basename(os.environ.get(k, d)) for k, d in (
    # The report tabs and the Google data sign-in (22 Oct 2026).
    ("GOOGLE_OAUTH_TOKEN_PATH", "/data/google_oauth.json"),
    ("ANALYSIS_CACHE_PATH", "/data/analysis_cache.json"),
    ("SCHEDULE_PATH", "/data/schedule.json"),
))


def _build_backup_zip():
    """(BytesIO, files_added). Everything restorable, credentials excluded."""
    import io, zipfile
    data_dir = os.path.dirname(scheduler.SCHEDULE_PATH) or "/data"
    repo_data = os.path.join(_REPO, "data")
    # Never export credentials, and give the two roots distinct prefixes so the
    # repo-seed sheet cannot shadow the live uploaded one on restore.
    secrets_excluded = {
        os.path.basename(getattr(google_mail, "TOKEN_PATH", "gmail_oauth.json")),
        os.path.basename(getattr(xero_api, "TOKEN_PATH", "xero_oauth.json")),
        os.path.basename(getattr(google_mail, "FINANCE_TOKEN_PATH", "gmail_finance_oauth.json")),
        os.path.basename(desk.WO_SECRET_PATH),
        # Sessions are transient bearer state: never in a backup. The accounts
        # register IS included, because restoring it is exactly what brings the
        # team back after a lost volume. It holds scrypt hashes and each
        # account's two-step secret, sealed with tokenvault (plain only while
        # the vault key is unset, as every sealed store is). The cash flow
        # workbook rides in forecast.json and is included too, decided
        # 14 Oct 2026: only the master downloads a backup, which already holds
        # the CRM and the inbox, and a restore without it would leave the
        # forecast without its cash flow until somebody uploaded it again.
        os.path.basename(team.SESSIONS_PATH),
    } | _RETIRED_FILES
    buf = io.BytesIO()
    added = 0
    included, skipped = [], []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        # Stored dispatch labels live in their own folder; without them a
        # restored app could not reprint anything dispatched before the move.
        # Newest 60 only: labels are ~1MB each and an uncapped archive could
        # build a backup too large for its own restore.
        label_keep = set()
        if os.path.isdir(desk.DISPATCH_LABELS_DIR):
            try:
                by_age = sorted(os.listdir(desk.DISPATCH_LABELS_DIR),
                                key=lambda n: os.path.getmtime(os.path.join(desk.DISPATCH_LABELS_DIR, n)),
                                reverse=True)
                label_keep = set(by_age[:60])
                for n in by_age[60:]:
                    skipped.append({"name": n, "reason": "older label; newest 60 kept"})
            except OSError:
                pass
        roots = ((data_dir, "volume"), (repo_data, "repo-data"),
                 (desk.DISPATCH_LABELS_DIR, "volume-labels"))
        for root, prefix in roots:
            if not os.path.isdir(root):
                continue
            try:
                names = sorted(os.listdir(root))
            except OSError:
                continue
            for n in names:
                if n in secrets_excluded:
                    continue
                if prefix == "volume-labels" and n not in label_keep:
                    continue
                p = os.path.join(root, n)
                if not os.path.isfile(p) or not n.lower().endswith((".json", ".jsonl", ".csv", ".bak")):
                    continue
                try:
                    size = os.path.getsize(p)
                    if size > BACKUP_FILE_MAX:
                        # Named, never silent: a store that outgrew the backup
                        # is exactly what the merchant must hear about.
                        skipped.append({"name": n, "reason": f"too large ({size // (1024 * 1024)}MB)"})
                        logger.warning("backup skipped %s: %d bytes", n, size)
                        continue
                    z.write(p, prefix + "/" + n)
                    included.append({"name": prefix + "/" + n, "size": size})
                    added += 1
                except OSError:
                    continue
        z.writestr("manifest.json", json.dumps({
            "built_at": datetime.now(timezone.utc).isoformat(),
            "included": included, "skipped": skipped}))
    return buf, added


def _note_backup(kind: str) -> None:
    try:
        st = jsonstore._load_json_store(BACKUP_STATE_PATH, "backup", {}) or {}
        st[kind + "_at"] = datetime.now(timezone.utc).isoformat()
        if jsonstore._store_writable(BACKUP_STATE_PATH):
            jsonstore._write_json_store(BACKUP_STATE_PATH, "backup", st)
    except Exception:
        logger.exception("could not record the backup time")


def _weekly_snapshot(force: bool = False) -> bool:
    """A dated snapshot kept in the volume, newest few retained. This survives a
    bad write or a corrupted store; it does NOT survive losing the volume, which
    is why the app also nags for a real download.

    force=True takes one regardless of when the last was: used immediately
    before something irreversible, like replacing the CRM with an import."""
    try:
        st = jsonstore._load_json_store(BACKUP_STATE_PATH, "backup", {}) or {}
        last = str(st.get("snapshot_at") or "")
        if last and not force:
            try:
                when = datetime.fromisoformat(last)
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                if (datetime.now(timezone.utc) - when).days < 7:
                    return False
            except ValueError:
                pass
        buf, added = _build_backup_zip()
        if not added:
            return False
        os.makedirs(BACKUP_SNAPSHOT_DIR, exist_ok=True)
        # A forced snapshot is the restore point from before something
        # irreversible, so it is named to the second and never replaces
        # anything: named by the day, a second import that day overwrote the
        # only copy of the CRM from before the first. It keeps its own count,
        # so imports cannot push the weekly snapshots out, and it leaves the
        # weekly schedule alone.
        prefix = "pre-import" if force else "snapshot"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ" if force else "%Y-%m-%d")
        path = os.path.join(BACKUP_SNAPSHOT_DIR, f"{prefix}-{stamp}.zip")
        n = 2
        while force and os.path.exists(path):
            path = os.path.join(BACKUP_SNAPSHOT_DIR, f"{prefix}-{stamp}-{n}.zip")
            n += 1
        tmp = path + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(buf.getvalue())
        os.replace(tmp, path)
        old = sorted(glob.glob(os.path.join(BACKUP_SNAPSHOT_DIR, f"{prefix}-*.zip")),
                     key=os.path.getmtime)
        keep = set(old[-BACKUP_KEEP:])
        if force:
            # And the FIRST of each day for a month: kept by count alone, a
            # fifth run of an import deleted the only snapshot from before the
            # first, which is the one a bad import needs.
            since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y%m%d")
            first_of_day: dict = {}
            for f in old:
                day = os.path.basename(f)[len(prefix) + 1:len(prefix) + 9]
                first_of_day.setdefault(day, f)
            keep |= {f for day, f in first_of_day.items() if day >= since}
        for stale in [f for f in old if f not in keep]:
            try:
                os.remove(stale)
            except OSError:
                pass
        _note_backup("pre_import" if force else "snapshot")
        logger.info("weekly snapshot written: %s (%s files)", path, added)
        return True
    except Exception:
        logger.exception("weekly snapshot failed")
        return False


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as core.NAME and sibling.NAME, never a copied name.
from gizmo import dispatch as desk  # noqa: E402
from gizmo import team  # noqa: E402
from gizmo import scheduler  # noqa: E402
import copilot as core  # noqa: E402
