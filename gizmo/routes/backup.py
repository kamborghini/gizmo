"""The backup routes: the download and the restore. Gathered from add_routes
(stage 4 of the 14 October audit) where the first stood; their paths are
literal, so no request changes hands.
"""
import logging
import os
import json
import base64
import asyncio
from datetime import datetime, timezone
import perf
import google_mail
import xero as xero_api
from starlette.requests import Request
from starlette.responses import Response
from gizmo import store as jsonstore

import copilot as core
from gizmo import backup
from gizmo import activity
from gizmo import dispatch as desk
from gizmo import files as fileserver
from gizmo import gate
from gizmo import privacy
from gizmo import team
from gizmo import webdav
from gizmo import scheduler
from gizmo import bodies

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")



class RestoreBody(bodies.Body):
    """What /api/restore reads (gizmo/bodies.py): the backup, and whether only to check it."""
    zip: bodies.Text = None
    check: bodies.Flag = None


def register(mcp, registry):
    """Add the backup and restore routes to the app."""

    @mcp.custom_route("/api/restore", methods=["POST"])
    async def restore_route(request: Request):
        """Master-only: put a downloaded backup zip back onto the volume. This
        is how the shop survives a lost volume or moves the service between
        regions: fresh volume, first-run setup, restore, sign back in. Only
        the volume's own JSON/CSV files are accepted, by basename, so a
        crafted zip cannot write anywhere else."""
        perf.no_record()        # long by design: out of the slowest-routes table
        big = 120 * 1024 * 1024
        err, _body, who = await gate._guard(request, max_body=big, body=False)
        if err:
            return err
        if team._team_role(who) != "master":
            return gate._json({"error": "Only the master admin can restore a backup."}, 403)
        body = await gate._read_json_capped(request, cap=big)
        if body is None:
            return gate._json({"error": "That file is too large (120 MB cap)."}, 413)
        refused = gate._body_refusal(RestoreBody, body)
        if refused:
            return refused
        import io as _io
        import zipfile as _zip
        try:
            blob = base64.b64decode(str(body.get("zip") or ""), validate=True)
            zf = _zip.ZipFile(_io.BytesIO(blob))
        except Exception:
            return gate._json({"error": "That is not a readable backup zip."}, 400)
        data_dir = os.path.dirname(scheduler.SCHEDULE_PATH) or "/data"
        # Only what the backup itself writes, and never live credentials or
        # sessions: the same exclusions the backup applies, applied again.
        blocked = {os.path.basename(desk.WO_SECRET_PATH), os.path.basename(team.SESSIONS_PATH),
                   os.path.basename(getattr(google_mail, "TOKEN_PATH", "gmail_oauth.json")),
                   os.path.basename(getattr(xero_api, "TOKEN_PATH", "xero_oauth.json")),
                   os.path.basename(getattr(google_mail, "FINANCE_TOKEN_PATH",
                                            "gmail_finance_oauth.json"))} | backup._RETIRED_FILES
        # (name, target_dir) for every restorable entry; everything else named
        # in the manifest as skipped, so nothing ever vanishes silently.
        todo, skipped = [], []
        built_at = built_full = ""    # to the second for people; in full to order events by
        for info in zf.infolist():
            if info.is_dir():
                continue
            base = os.path.basename(info.filename)
            if info.filename == "manifest.json":
                try:
                    built_full = str(json.loads(zf.read(info)).get("built_at") or "")
                    built_at = built_full[:19]
                except Exception:
                    pass  # an unreadable manifest leaves the backup's date blank; the restore goes on
                continue
            if info.filename.startswith("volume/"):
                target = data_dir
            elif info.filename.startswith("volume-labels/"):
                target = desk.DISPATCH_LABELS_DIR
            elif info.filename.startswith("repo-data/"):
                skipped.append(base + " (ships with the app's code)")
                continue
            else:
                skipped.append(info.filename + " (not part of a backup)")
                continue
            if not base or base in blocked or not base.lower().endswith((".json", ".jsonl", ".csv", ".bak")):
                skipped.append(base + " (never restored)")
                continue
            # The SAME ceiling the backup packs to. A smaller one here meant the
            # backup dutifully carried the CRM and the mailbox and the restore
            # dropped them - the two stores the backup exists for - and called
            # the result a success. A store too big to restore fails the WHOLE
            # restore: a partial restore of the desk is not a restore.
            if info.file_size > backup.BACKUP_FILE_MAX:
                return gate._json({"error": base + " is larger than this app will restore ("
                                       + str(info.file_size // (1024 * 1024)) + "MB). Nothing "
                                       "has been changed. Raise the backup file size limit in the "
                                       "app's hosting settings and try again."}, 400)
            todo.append((info, base, target))
        if not todo:
            return gate._json({"error": "Nothing in that zip looked like this app's backup."}, 400)
        if body.get("check"):
            # Dry run: the exact manifest, nothing written.
            return gate._json({"ok": True, "check": True, "backup_built_at": built_at,
                          "would_restore": sorted(b for _, b, _t in todo),
                          "skipped": sorted(skipped)})
        # Doors first, then writes: sessions drop BEFORE anything is written,
        # so no new request can race the restore (this request already holds
        # its authorisation), and the files lock is held through the writes so
        # an upload in flight commits before us, never after us.
        team._write_sessions({})
        webdav._dav_auth_cache.clear()
        restored_names = []
        # Live state, not data: an erasure owed now and how long the store
        # has been out of reach now. Restoring the pre-redact archive brought
        # back the owed record it was taken under, and the old outage stamp,
        # and the next hour erased the restored data again.
        live_priv: dict = {}
        live_watch = scheduler._load_watch()
        live_watch = live_watch if isinstance(live_watch, dict) else {}
        def _drop_all_caches():
            # Every memory copy, from the one list: the loan register was
            # missing from the hand-kept one here, so a restored loans.json
            # was overwritten by the pre-restore register on the next loan.
            jsonstore._drop_memory_stores()
            activity._events_dirty = False
            webdav._dav_auth_cache.clear()
            jsonstore._json_cache.clear()
        async with fileserver._files_lock:
            # Read here, with nothing left to await before the writes, so a
            # privacy request that arrives while the restore waits for the
            # lock is not lost.
            _pl = privacy._load_privacy_log()
            if privacy.PRIVACY_LOG_PATH not in jsonstore._poisoned_stores:
                live_priv.update(_pl)
            try:
                for info, base, target in todo:
                    payload = zf.read(info)
                    os.makedirs(target, exist_ok=True)
                    tmp = os.path.join(target, base + ".tmp")
                    with open(tmp, "wb") as fh:
                        fh.write(payload)
                    os.replace(tmp, os.path.join(target, base))
                    jsonstore._poisoned_stores.discard(os.path.join(target, base))
                    restored_names.append(base)
            except Exception:
                # NOT just OSError: zf.read() decompresses, so a truncated or
                # corrupted member raises BadZipFile / zlib.error / RuntimeError,
                # none of which are OSError - and those escaped this handler,
                # leaving a half-restored volume with the pre-restore world
                # still live in memory and no cache drop.
                logger.exception("restore failed mid-write")
                # Disk is part-new: memory must never serve (or later flush)
                # the pre-restore world over it.
                _drop_all_caches()
                return gate._json({"error": "The backup could not be read all the way through, so "
                                       "the restore stopped part-way. The data volume now holds "
                                       "a mix: restore again from a known-good backup before "
                                       "using the app."}, 500)
            # A backup is a photograph of an earlier clock. Ages must not be
            # trusted: an upload that was mid-flight at backup time would read
            # as days-stale and the sweep would DELETE its bytes, and old
            # trash would purge instantly. Everything time-sensitive restarts
            # its clock now, and the doomed list is cleared: an orphaned
            # object in the bucket costs pennies, a wrong deletion is forever.
            try:
                _drop_all_caches()   # memory must re-read the RESTORED disk here
                fd = fileserver._load_files()
                nown = datetime.now(timezone.utc).isoformat()
                for v in fd["files"].values():
                    if v.get("status") == "pending":
                        v["status"] = "trashed"
                        v["trashed_at"] = nown
                    elif v.get("trashed_at"):
                        v["trashed_at"] = nown
                fd["doomed"] = []
                fileserver._write_files(fd)
            except Exception:
                logger.exception("restore: files-clock normalisation failed")
            try:
                if live_priv:
                    try:
                        privacy._keep_live_privacy(live_priv, built_full)
                    except Exception:
                        logger.exception("restore: merging the live privacy requests failed")
                w = scheduler._load_watch()
                w = w if isinstance(w, dict) else {}
                for k in ("shopify_down", "probe_fails"):
                    if k in live_watch:
                        w[k] = live_watch[k]
                    else:
                        w.pop(k, None)
                scheduler._save_watch(w)
            except Exception:
                logger.exception("restore: keeping the live erasure and outage records failed")
        restored = len(restored_names)
        # Every memory copy now lies; drop them all and start from disk truth.
        _drop_all_caches()
        team._write_sessions({})          # already empty; re-assert against the restored disk
        # Written AFTER the caches are dropped, so it lands in the RESTORED
        # ledger: the history now on the volume is the backup's, and this is
        # the line that says where it came from and who did it. Without it the
        # jump backwards in the audit trail has no explanation in the trail.
        activity._track(who, "settings", "restored a backup",
               f"{restored} files; the history before this line is from the backup"
               + (f" built {built_at}" if built_at else ""))
        activity._events_flush()
        logger.warning("backup restored by %s: %d files; all sessions dropped", who, restored)
        return gate._json({"ok": True, "restored": restored, "backup_built_at": built_at,
                      "files": sorted(restored_names), "skipped": sorted(skipped),
                      "note": "Everyone signs in again now, with the accounts from the "
                              "backup. Two things never travel in a backup and need "
                              "re-entering once: the World Options courier credentials "
                              "in Settings, and the Google connection if you use it."})

    @mcp.custom_route("/api/backup", methods=["POST"])
    async def backup_route(request: Request):
        """Everything the app has learned lives as files on one volume; this hands
        the merchant a zip of it. JSON and CSV only, fonts and code excluded."""
        perf.no_record()        # long by design: out of the slowest-routes table
        err, _body, who = await gate._guard(request, body=False)
        if err:
            return err
        # Master only, matching /api/restore. The zip deliberately carries the
        # accounts register, so an admin could take home every password hash
        # (including the master's) and grind it offline - while not being
        # trusted to restore. Export and restore now need the same standing.
        if team._team_role(who) != "master":
            return gate._json({"error": "Only the master account can download a backup, because "
                                   "it contains the accounts register."}, 403)
        body = await gate._read_json_capped(request)
        if body is None:
            return gate._json({"error": "Request too large."}, 413)
        # Off the event loop, as the pre-import snapshot is: deflating the
        # whole volume inline stopped every request and webhook for seconds.
        buf, added = await asyncio.to_thread(backup._build_backup_zip)
        if not added:
            return gate._json({"error": "Nothing to back up yet."}, 404)
        backup._note_backup("download")
        activity._track(who, "settings", "downloaded a backup")
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return Response(buf.getvalue(), media_type="application/zip",
                        headers={**gate._API_HEADERS,
                                 "Content-Disposition": f"attachment; filename=reactor-backup-{stamp}.zip"})
