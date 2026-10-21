"""The Files routes and the Finder drive's, gathered from add_routes (stage 4
of the 14 October audit) where the first stood. No request changes hands:
the drive's is the one route with a pattern, and no other path starts with
/dav.
"""
import logging
import os
import time
import hashlib
import asyncio
import secrets
from datetime import datetime, timezone
import httpx
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from gizmo import store as jsonstore

import copilot as core
from gizmo import files as fileserver
from gizmo import activity
from gizmo import gate
from gizmo import team
from gizmo import webdav
from gizmo import bodies

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")



class FolderBody(bodies.Body):
    """What /api/files/folder reads (gizmo/bodies.py): a folder's name, where
    it goes, and whether the page wants only what changed."""
    id: bodies.Id = None
    name: bodies.Text = None
    parent_id: bodies.Id = None
    delta: bodies.Flag = None


def register(mcp, registry):
    """Add the Files routes and the Finder drive's to the app."""




    @mcp.custom_route("/api/files/drive", methods=["POST"])
    async def files_drive_route(request: Request):
        """The Finder drive's own password: made, replaced and removed here,
        after a full sign-in (codes included), shown once, kept as a SHA-256.
        The account password no longer opens /dav (audit R-007)."""
        err, body, who = await fileserver._files_guard(request)
        if err:
            return err
        op = str(body.get("op") or "")
        d = team._load_users()
        u = d["users"].get(who)
        if not u:
            return gate._json({"error": "Your account could not be found."}, 404)
        if op in ("create", "remove"):
            if team.USERS_PATH in jsonstore._poisoned_stores:
                return gate._json({"error": "The accounts could not be read, so nothing can change until they are repaired."}, 503)
            pw = ""
            if op == "create":
                pw = secrets.token_urlsafe(18)
                u["dav_pw"] = hashlib.sha256(pw.encode("utf-8")).hexdigest()
                u["dav_pw_at"] = datetime.now(timezone.utc).isoformat()
            else:
                u.pop("dav_pw", None)
                u.pop("dav_pw_at", None)
            try:
                team._write_users(d)
            except RuntimeError:
                return gate._json({"error": "The drive password could not be saved. Try again."}, 500)
            webdav._dav_drop_cache(who)
            activity._track(who, "files", "made a drive password" if pw else "removed their drive password")
            if pw:
                return gate._json({"ok": True, "has": True, "made_at": u["dav_pw_at"], "username": u.get("username") or "",
                              "password": pw})
        return gate._json({"ok": True, "has": bool(u.get("dav_pw")), "made_at": u.get("dav_pw_at") or "",
                      "username": u.get("username") or ""})

    @mcp.custom_route("/api/files/tree", methods=["POST"])
    async def files_tree_route(request: Request):
        err, body, _who = await fileserver._files_guard(request)
        if err:
            return err
        try:
            raw, rev = fileserver._files_sent(fileserver._load_files())
            # A page that holds this revision is told so, not sent the store
            # again. One with none, open from before this update, gets it.
            if str((body or {}).get("rev") or "") == rev:
                return gate._json({"same": True, "rev": rev})
            return gate._json_spliced({"rev": rev}, "store", raw)
        except Exception:
            logger.exception("files tree failed")
            return gate._json({"error": "Couldn't load the files."}, 500)

    @mcp.custom_route("/api/files/folder", methods=["POST"])
    async def files_folder_route(request: Request):
        err, body, _who = await fileserver._files_guard(request, model=FolderBody)
        if err:
            return err
        op = str(body.get("op") or "")
        try:
            async with fileserver._files_lock:
                d = fileserver._load_files()
                if op == "add":
                    name = fileserver._files_clean_name(body.get("name"))
                    parent = str(body.get("parent_id") or "")
                    if not fileserver._files_folder_ok(d, parent):
                        return gate._json({"error": "That folder no longer exists."}, 400)
                    if any(f.get("name", "").lower() == name.lower()
                           and str(f.get("parent_id") or "") == parent
                           for f in d["folders"].values()):
                        return gate._json({"error": "A folder with that name is already here."}, 400)
                    fid = fileserver._files_id(d, "d")
                    d["folders"][fid] = {"name": name, "parent_id": parent,
                                         "created_at": datetime.now(timezone.utc).isoformat()}
                    return fileserver._files_ok(d, {"id": fid}, action="made a folder", detail=name, who=_who,
                                     delta=fileserver._files_delta(d, folders=[fid]) if body.get("delta") else None)
                if op == "rename":
                    fid = str(body.get("id") or "")
                    if fid not in d["folders"]:
                        return gate._json({"error": "That folder no longer exists."}, 400)
                    name = fileserver._files_clean_name(body.get("name"))
                    parent = str(d["folders"][fid].get("parent_id") or "")
                    if any(k != fid and f.get("name", "").lower() == name.lower()
                           and str(f.get("parent_id") or "") == parent
                           for k, f in d["folders"].items()):
                        return gate._json({"error": "A folder with that name is already here."}, 400)
                    old_name = d["folders"][fid]["name"]
                    d["folders"][fid]["name"] = name
                    return fileserver._files_ok(d, action="renamed a folder", detail=f"{old_name} to {name}", who=_who)
                if op == "delete":
                    fid = str(body.get("id") or "")
                    if fid not in d["folders"]:
                        return gate._json({"error": "That folder no longer exists."}, 400)
                    # Finder's own sidecars (.DS_Store, ._name) are hidden: the
                    # tab shows the folder empty, so they must not make it
                    # "not empty" with nothing anyone can remove.
                    if any(str(f.get("parent_id") or "") == fid for f in d["folders"].values()) \
                       or any(str(v.get("folder_id") or "") == fid and v.get("status") == "active"
                              and not v.get("hidden") for v in d["files"].values()):
                        return gate._json({"error": "The folder isn't empty. Move or delete "
                                               "what's inside first."}, 400)
                    # An upload still in flight counts as an occupant: with the
                    # folder gone, the finished file landed in a folder that
                    # did not exist, counted but unreachable. One abandoned
                    # hours ago does not: the folder shows empty, and it is.
                    if any(str(v.get("folder_id") or "") == fid and fileserver._files_upload_in_flight(v)
                           for v in d["files"].values()):
                        return gate._json({"error": "An upload into this folder is still in progress. "
                                               "Wait for it to finish, then try again."}, 400)
                    gone = d["folders"].pop(fid)
                    # The sidecars go with it, their bytes onto the reaper's list.
                    for k in [k for k, v in d["files"].items()
                              if str(v.get("folder_id") or "") == fid and v.get("hidden")]:
                        f = d["files"].pop(k)
                        if f.get("r2_key"):
                            d.setdefault("doomed", []).append(f["r2_key"])
                    return fileserver._files_ok(d, action="deleted a folder", detail=gone.get("name") or "", who=_who)
                return gate._json({"error": "Unknown folder action."}, 400)
        except RuntimeError:
            return gate._json({"error": fileserver._FILES_STORE_FAIL}, 500)
        except Exception:
            logger.exception("files folder op failed")
            return gate._json({"error": "That change could not be made. Check the server logs."}, 500)

    @mcp.custom_route("/api/files/upload-url", methods=["POST"])
    async def files_upload_route(request: Request):
        err, body, who = await fileserver._files_guard(request)
        if err:
            return err
        if not fileserver._files_configured():
            return gate._json({"error": "File storage isn't connected yet. Add the storage keys "
                                   "in the app's hosting settings to switch it on."}, 400)
        name = fileserver._files_clean_name(body.get("name"))
        if fileserver._file_ext(name) in fileserver._DANGEROUS_EXT:
            return gate._json({"error": f"{name} is a program, not a document."}, 400)
        try:
            size = int(body.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        if size <= 0:
            return gate._json({"error": "The file looks empty."}, 400)
        if size > fileserver.FILES_MAX_UPLOAD:
            return gate._json({"error": "That file is over the 4GB single-file limit."}, 400)
        folder = str(body.get("folder_id") or "")
        try:
            # Setting the bucket up is network (the first upload after a
            # deploy, and once a minute while storage is failing), so it runs
            # before the lock is taken: inside it, every other change to Files
            # and the Finder drive waited on storage. Under the lock the
            # signing below is then local work.
            await asyncio.to_thread(fileserver._files_ensure_bucket, fileserver._files_origin())
            async with fileserver._files_lock:
                d = fileserver._load_files()
                if not fileserver._files_folder_ok(d, folder):
                    return gate._json({"error": "That folder no longer exists."}, 400)
                quota = int(fileserver.FILES_QUOTA_GB * 1024 * 1024 * 1024)
                if fileserver._files_usage(d) + size > quota:
                    return gate._json({"error": "That upload would go over the storage space. "
                                           "Empty the trash or remove old files first."}, 400)
                fid = fileserver._files_id(d, "f")
                key = f"{fid}/{name}"
                ctype = str(body.get("type") or "application/octet-stream").strip()[:100] \
                    or "application/octet-stream"
                try:
                    url = await asyncio.to_thread(fileserver._files_sign_put, key, ctype, size, False)
                except RuntimeError as e:
                    logger.warning("files: presign failed: %s", e)
                    return gate._json({"error": "Storage isn't reachable right now. Check the storage "
                                           "keys in the app's hosting settings, then try again."}, 502)
                rec = {"name": name, "folder_id": folder, "size": size,
                       "type": ctype, "r2_key": key, "status": "pending", "by": who,
                       "created_at": datetime.now(timezone.utc).isoformat()}
                # Uploading a name that already lives here REPLACES it, the way
                # a save does: the old version waits in the 30-day trash. The
                # target is pinned server-side, so the client cannot aim the
                # retirement at some other file.
                dup = next((k for k, v in d["files"].items()
                            if v.get("status") == "active" and not v.get("hidden")
                            and str(v.get("folder_id") or "") == folder
                            and v.get("name", "").lower() == name.lower()), None)
                if dup:
                    rec["replaces"] = dup
                d["files"][fid] = rec
                return fileserver._files_ok(d, {"id": fid, "url": url, "replaces": bool(dup)},
                                 delta=fileserver._files_delta(d) if body.get("delta") else None)
        except RuntimeError:
            return gate._json({"error": fileserver._FILES_STORE_FAIL}, 500)
        except Exception:
            logger.exception("files upload-url failed")
            return gate._json({"error": "The upload could not be prepared. Check the server logs."}, 500)

    @mcp.custom_route("/api/files/complete", methods=["POST"])
    async def files_complete_route(request: Request):
        err, body, _who = await fileserver._files_guard(request)
        if err:
            return err
        fid = str(body.get("id") or "")
        try:
            async with fileserver._files_lock:
                d = fileserver._load_files()
                f = d["files"].get(fid)
                if not f or f.get("status") != "pending":
                    return gate._json({"error": "That upload is no longer expected."}, 400)
                key = f["r2_key"]
            # Storage is asked outside the store's lock (the 2026-10-12 speed
            # audit, S9). Held across these two round trips, it made every
            # other change to Files and the Finder drive wait on storage, and
            # a batch's uploads were confirmed one at a time. The record is
            # read again under the lock before anything is kept.
            try:
                true_size = await asyncio.to_thread(fileserver._files_head, key)
            except RuntimeError:
                # A storage wobble is not a lost upload: keep the record
                # pending so a retry can finish the same upload.
                return gate._json({"error": "Storage isn't answering right now. Wait a "
                                       "moment and try again; the upload is not lost."}, 502)
            if true_size is None:
                return gate._json({"error": "The file never arrived in storage. Try the "
                                       "upload again."}, 400)
            try:
                head = await asyncio.to_thread(fileserver._files_head_bytes, key)
            except Exception:
                logger.exception("files: could not read the head of %s", key)
                return gate._json({"error": "Storage did not answer; try again."}, 502)
            refused = ""
            async with fileserver._files_lock:
                d = fileserver._load_files()
                f = d["files"].get(fid)
                # Confirmed by another call (a retry) or gone while storage
                # answered: exactly what a second confirmation was told before.
                if not f or f.get("status") != "pending" or f.get("r2_key") != key:
                    return gate._json({"error": "That upload is no longer expected."}, 400)
                # The browser's claimed size opened the door; what actually
                # landed is what counts against the space.
                f["size"] = true_size
                okv, why, safe = fileserver._file_verdict(f.get("name"), f.get("type"), head)
                if not okv:
                    # Refused whole: the bytes go, the record goes, and the
                    # person is told why rather than left with a phantom file.
                    d["files"].pop(fid, None)
                    fileserver._write_files(d)
                    refused = why
                else:
                    f["type"], f["sniffed"] = safe, fileserver._sniff_kind(head)
                    if true_size > fileserver.FILES_MAX_UPLOAD \
                            or fileserver._files_usage(d) > int(fileserver.FILES_QUOTA_GB * 1024 * 1024 * 1024):
                        fileserver._write_files(d)   # keep the honest size; the sweep clears it
                        return gate._json({"error": "The file is bigger than the storage space "
                                               "allows, so it has not been kept."}, 400)
                    f["status"] = "active"
                    f["uploaded_at"] = datetime.now(timezone.utc).isoformat()
                    if f.get("folder_id") and not fileserver._files_folder_ok(d, str(f.get("folder_id"))):
                        # The folder went while the bytes were in flight. A file
                        # in a folder that does not exist is counted, invisible
                        # and unreachable on the drive; the top level is where a
                        # restore puts one too.
                        f["folder_id"] = ""
                    f.pop("replaces", None)
                    gone = fileserver._files_supersede(d, fid)
                    replaced = " (replaced the previous version)" if gone else ""
                    return fileserver._files_ok(d, action="uploaded a file",
                                     detail=(f"{f.get('name')} ({true_size} bytes)" + replaced)[:200],
                                     who=_who,
                                     delta=fileserver._files_delta(d, [fid] + gone) if body.get("delta") else None)
            try:
                await asyncio.to_thread(fileserver._r2_call, "delete_object", Key=key)
            except Exception:
                logger.warning("files: refused upload %s could not be removed", key)
            activity._track(_who, "files", "refused an upload", refused[:200])
            return gate._json({"error": "Refused: " + refused + " The upload was removed."}, 400)
        except RuntimeError:
            return gate._json({"error": fileserver._FILES_STORE_FAIL}, 500)
        except Exception:
            logger.exception("files complete failed")
            return gate._json({"error": "The upload could not be confirmed. Check the server logs."}, 500)

    @mcp.custom_route("/api/files/download-url", methods=["POST"])
    async def files_download_route(request: Request):
        err, body, _who = await fileserver._files_guard(request)
        if err:
            return err
        fid = str(body.get("id") or "")
        try:
            d = fileserver._load_files()
            f = d["files"].get(fid)
            if not f or f.get("status") == "pending":
                return gate._json({"error": "That file no longer exists."}, 404)
            preview = bool(body.get("preview"))
            mime = fileserver._files_preview_mime(f.get("name") or "")
            if preview and not mime:
                return gate._json({"error": "That file type opens as a download, not a preview."}, 400)
            url = await asyncio.to_thread(
                lambda: fileserver._files_sign_get(f["r2_key"], f.get("name") or "file", inline=preview))
            return gate._json({"ok": True, "url": url, "name": f.get("name"),
                          "preview": preview, "type": (mime if preview else "")})
        except Exception:
            logger.exception("files download-url failed")
            return gate._json({"error": "Storage isn't reachable right now. Try again in a "
                                   "moment."}, 502)

    @mcp.custom_route("/api/files/file", methods=["POST"])
    async def files_file_route(request: Request):
        err, body, _who = await fileserver._files_guard(request)
        if err:
            return err
        op = str(body.get("op") or "")
        fid = str(body.get("id") or "")
        try:
            async with fileserver._files_lock:
                d = fileserver._load_files()
                # Several files at once: the same trash and move, one write.
                raw_ids = body.get("ids")
                if op in ("trash", "move") and isinstance(raw_ids, list):
                    ids = [str(i) for i in raw_ids][:100]
                    folder = str(body.get("folder_id") or "")
                    if op == "move" and not fileserver._files_folder_ok(d, folder):
                        return gate._json({"error": "That folder no longer exists."}, 400)
                    hit, skipped = 0, []
                    for i in ids:
                        v = d["files"].get(i)
                        if not v or v.get("status") != "active":
                            continue
                        if op == "trash":
                            v["status"] = "trashed"
                            v["trashed_at"] = datetime.now(timezone.utc).isoformat()
                        else:
                            # The same check the single move makes. Without
                            # it two active files shared a name in a folder
                            # and the drive, which resolves by name, could
                            # only ever reach the older one.
                            if str(v.get("folder_id") or "") != folder \
                                    and fileserver._files_name_taken(d, folder, v.get("name"), i):
                                skipped.append(str(v.get("name") or ""))
                                continue
                            v["folder_id"] = folder
                        hit += 1
                    if not hit and skipped:
                        return gate._json({"error": ("That folder already holds a file with this name. "
                                                "Rename one of them first." if len(skipped) == 1 else
                                                f"That folder already holds files with {len(skipped)} "
                                                "of those names. Rename them first.")}, 409)
                    if not hit:
                        return gate._json({"error": "None of those files exist any more."}, 400)
                    label = ("1 file" if hit == 1 else f"{hit} files")
                    if skipped:
                        label += f", {len(skipped)} left behind: same name in that folder"
                    return fileserver._files_ok(d, extra=({"skipped": skipped} if skipped else None),
                                     action=("put files in the trash" if op == "trash"
                                             else "moved files"), detail=label, who=_who)
                if op == "empty_trash":
                    if team._team_level(_who) < team.ROLE_LEVELS["admin"]:
                        return gate._json({"error": "Only an admin can delete files for good."}, 403)
                    doomed = [k for k, v in d["files"].items() if v.get("trashed_at")]
                    if not doomed:
                        return gate._json({"error": "The trash is already empty."}, 400)
                    for k in doomed:
                        v = d["files"].pop(k)
                        if v.get("r2_key"):
                            d.setdefault("doomed", []).append(v["r2_key"])
                    return fileserver._files_ok(d, action="emptied the trash",
                                     detail=(f"{len(doomed)} file(s) deleted for good"), who=_who)
                f = d["files"].get(fid)
                if not f or f.get("status") == "pending":
                    return gate._json({"error": "That file no longer exists."}, 400)
                if op == "rename":
                    if f.get("status") != "active":
                        return gate._json({"error": "Restore the file from the trash first."}, 400)
                    old_name = f.get("name") or ""
                    new_name = fileserver._files_clean_name(body.get("name"))
                    if fileserver._file_ext(new_name) in fileserver._DANGEROUS_EXT:
                        return gate._json({"error": f"{new_name} is a program, not a document."}, 400)
                    if fileserver._files_name_taken(d, f.get("folder_id"), new_name, fid):
                        return gate._json({"error": "There is already a file called that in this "
                                               "folder. Rename the other one first."}, 409)
                    f["name"] = new_name
                    return fileserver._files_ok(d, action="renamed a file",
                                     detail=f"{old_name} to {f['name']}", who=_who)
                if op == "move":
                    if f.get("status") != "active":
                        return gate._json({"error": "Restore the file from the trash first."}, 400)
                    folder = str(body.get("folder_id") or "")
                    if not fileserver._files_folder_ok(d, folder):
                        return gate._json({"error": "That folder no longer exists."}, 400)
                    if fileserver._files_name_taken(d, folder, f.get("name"), fid):
                        return gate._json({"error": "That folder already holds a file with this "
                                               "name. Rename one of them first."}, 409)
                    f["folder_id"] = folder
                    return fileserver._files_ok(d, action="moved a file", detail=f.get("name") or "", who=_who)
                if op == "trash":
                    if f.get("status") != "active":
                        return gate._json({"error": "The file is already in the trash."}, 400)
                    f["status"] = "trashed"
                    f["trashed_at"] = datetime.now(timezone.utc).isoformat()
                    return fileserver._files_ok(d, action="put a file in the trash", detail=f.get("name") or "", who=_who)
                if op == "restore":
                    if not f.get("trashed_at"):
                        return gate._json({"error": "The file isn't in the trash."}, 400)
                    if not fileserver._files_folder_ok(d, str(f.get("folder_id") or "")):
                        f["folder_id"] = ""   # its folder went away; restore to the top level
                    if fileserver._files_name_taken(d, f.get("folder_id"), f.get("name"), fid):
                        return gate._json({"error": "A file with this name is already in that "
                                               "folder. Rename it before restoring this one."}, 409)
                    f.pop("trashed_at", None)
                    f["status"] = "active"
                    return fileserver._files_ok(d, action="restored a file from the trash", detail=f.get("name") or "", who=_who)
                if op == "destroy":
                    # "Delete now" from the trash: the record goes at once (so
                    # the space frees), the key joins the doomed list, and the
                    # hourly reaper removes the bytes from the bucket. The
                    # trash is the undo; skipping it is an admin's call.
                    if team._team_level(_who) < team.ROLE_LEVELS["admin"]:
                        return gate._json({"error": "Only an admin can delete files for good."}, 403)
                    if not f.get("trashed_at"):
                        return gate._json({"error": "Only files already in the trash can be "
                                               "deleted for good."}, 400)
                    d["files"].pop(fid)
                    if f.get("r2_key"):
                        d.setdefault("doomed", []).append(f["r2_key"])
                    return fileserver._files_ok(d, action="deleted a file for good", detail=f.get("name") or "", who=_who)
                return gate._json({"error": "Unknown file action."}, 400)
        except RuntimeError:
            return gate._json({"error": fileserver._FILES_STORE_FAIL}, 500)
        except Exception:
            logger.exception("files file op failed")
            return gate._json({"error": "That change could not be made. Check the server logs."}, 500)


    # ---- WebDAV route -----------------------------------------------------
    @mcp.custom_route("/dav{sub_path:path}", methods=["OPTIONS", "PROPFIND", "GET", "HEAD",
                                                      "PUT", "MKCOL", "DELETE", "MOVE",
                                                      "COPY", "LOCK", "UNLOCK"])
    async def dav_route(request: Request):
        method = request.method
        path = request.path_params.get("sub_path") or "/"
        if os.environ.get("DAV_TRACE"):
            logger.info("DAV %s %s len=%s te=%s expect=%s", method, path,
                        request.headers.get("content-length"),
                        request.headers.get("transfer-encoding"),
                        request.headers.get("expect"))
        hdrs = {"DAV": "1, 2", "MS-Author-Via": "DAV"}
        if method == "OPTIONS":
            return Response(status_code=200, headers={**hdrs,
                "Allow": "OPTIONS, PROPFIND, GET, HEAD, PUT, MKCOL, DELETE, MOVE, COPY, LOCK, UNLOCK"})
        # The drive has no Shopify perimeter, so it gets its own rate ceiling:
        # generous for Finder's request storms, a wall against a scanner.
        if not gate._window_ok(gate._rl_hits.setdefault("dav:" + gate._client_key(request), []),
                          max(gate.RATE_MAX_CLIENT, 300), time.monotonic()):
            return Response(status_code=429, headers=hdrs)
        # The ceiling above is generous on purpose. Twenty misses a minute
        # from one client is not Finder retrying a keychain entry: refuse
        # before checking. This, not a lock by username, is what slows guessing.
        auth_hdr = request.headers.get("authorization", "")
        fails = gate._rl_hits.setdefault("davfail:" + gate._client_key(request), [])
        if auth_hdr.startswith("Basic ") and gate._window_hits(fails, time.monotonic()) >= webdav.DAV_FAIL_PER_MIN:
            return Response(status_code=429, headers=hdrs)
        uid, code = webdav._dav_check_auth(auth_hdr)
        if code == 401 and auth_hdr.startswith("Basic "):
            fails.append(time.monotonic())
        if code:
            return Response(status_code=code, headers={**hdrs,
                "WWW-Authenticate": 'Basic realm="Reactor Files"'} if code == 401 else hdrs)
        d = fileserver._load_files()
        kind, kid = webdav._dav_resolve(d, path)

        if method == "PROPFIND":
            depth = request.headers.get("depth", "1")
            if depth not in ("0", "1"):
                return Response(status_code=403, headers=hdrs)
            if kind is None:
                return Response(status_code=404, headers=hdrs)
            parts = []
            if kind == "folder":
                folder_path = webdav._dav_path_of_folder(d, kid)
                used = fileserver._files_usage(d)
                q = (used, max(0, int(fileserver.FILES_QUOTA_GB * 1024 * 1024 * 1024) - used))
                parts.append(webdav._dav_entry_xml(webdav._dav_href_dir(*folder_path),
                                            folder_path[-1] if folder_path else "Files", True,
                                            quota=q))
                if depth == "1":
                    for fid, f in d["folders"].items():
                        if str(f.get("parent_id") or "") == kid:
                            parts.append(webdav._dav_entry_xml(webdav._dav_href_dir(*folder_path, f["name"]),
                                                        f["name"], True, mtime=f.get("created_at") or ""))
                    for k, f in d["files"].items():
                        if f.get("status") == "active" and str(f.get("folder_id") or "") == kid:
                            parts.append(webdav._dav_entry_xml(webdav._dav_href(*folder_path, f["name"]),
                                                        f["name"], False, int(f.get("size") or 0),
                                                        f.get("uploaded_at") or f.get("created_at") or "",
                                                        etag=f"{k}-{f.get('size') or 0}"))
            else:
                f = d["files"][kid]
                fp = webdav._dav_path_of_folder(d, str(f.get("folder_id") or ""))
                parts.append(webdav._dav_entry_xml(webdav._dav_href(*fp, f["name"]), f["name"], False,
                                            int(f.get("size") or 0),
                                            f.get("uploaded_at") or f.get("created_at") or "",
                                            etag=f"{kid}-{f.get('size') or 0}"))
            xml = ('<?xml version="1.0" encoding="utf-8"?>'
                   '<D:multistatus xmlns:D="DAV:">' + "".join(parts) + "</D:multistatus>")
            return Response(xml, status_code=207, media_type="application/xml; charset=utf-8", headers=hdrs)

        if method in ("GET", "HEAD"):
            if kind != "file":
                return Response(status_code=404 if kind is None else 403, headers=hdrs)
            f = d["files"][kid]
            size = int(f.get("size") or 0)
            if method == "HEAD":
                return Response(status_code=200, headers={**hdrs, "Content-Length": str(size)})
            url = await asyncio.to_thread(fileserver._files_sign_get, f["r2_key"], f.get("name") or "file")
            # Tried and measured: a 302 to the signed URL comes back as an
            # EMPTY file from macOS's client, so downloads stream through the
            # app on purpose.
            client = httpx.AsyncClient(timeout=60)
            upstream = await client.send(client.build_request("GET", url), stream=True)
            if upstream.status_code != 200:
                await upstream.aclose(); await client.aclose()
                return Response(status_code=502, headers=hdrs)
            async def gen():
                try:
                    async for chunk in upstream.aiter_bytes(65536):
                        yield chunk
                finally:
                    await upstream.aclose(); await client.aclose()
            return StreamingResponse(gen(), headers={**hdrs, "Content-Length": str(size)},
                                     media_type="application/octet-stream")

        if method == "PUT":
            segs = webdav._dav_split(path)
            if not segs:
                return Response(status_code=403, headers=hdrs)
            name = fileserver._files_clean_name(segs[-1])
            hidden = bool(webdav._DAV_JUNK.match(segs[-1]))
            if hidden:
                # Sidecar names keep their exact dots: stripping them broke
                # the lookup, so Finder re-uploaded a fresh copy every save
                # and the mangled names stopped being dotfiles at all.
                name = fileserver._FILENAME_BAD.sub("_", segs[-1]).strip()[:180] or "untitled"
                if name in (".", ".."):
                    name = "_" + name
            # The WHOLE body is read before the store lock is touched: macOS
            # writes a file and its ._ sidecar at once and keeps the chunked
            # data PUT open until the sidecar answers, so reading under the
            # lock deadlocks the pair (seen live as "zero KB" forever).
            import tempfile as _tf
            # Refuse on the DECLARED length before a byte is spooled. The body
            # has to be read outside the lock (see above), which meant a client
            # could fill the container's disk with a file the quota was always
            # going to reject. Finder sends Content-Length for a real save.
            try:
                declared = int(request.headers.get("content-length") or 0)
            except (TypeError, ValueError):
                declared = 0
            if declared > fileserver.FILES_MAX_UPLOAD:
                return Response(status_code=413, headers=hdrs)
            quota_bytes = int(fileserver.FILES_QUOTA_GB * 1024 * 1024 * 1024)
            async with fileserver._files_lock:
                dq = fileserver._load_files()
                _kq, _fq = webdav._dav_resolve(dq, path)
                # What this save is replacing does not count against the room
                # it needs, or overwriting a large file near the quota would be
                # refused for the space it is about to give back.
                replacing = int(dq["files"][_fq].get("size") or 0) if _kq == "file" else 0
                room = max(0, quota_bytes - fileserver._files_usage(dq) + replacing)
            if declared > room:
                return Response(status_code=507, headers=hdrs)
            # A body with no Content-Length (chunked) still cannot spool more
            # than the store could ever accept: the quota was only checked
            # after the whole thing had been written to the container's disk,
            # so an unlabelled upload could fill the disk with bytes that were
            # always going to be refused.
            ceiling = min(fileserver.FILES_MAX_UPLOAD, room)
            spool = _tf.TemporaryFile()
            try:
                total = 0
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > ceiling:
                        return Response(status_code=507 if total <= fileserver.FILES_MAX_UPLOAD else 413,
                                        headers=hdrs)
                    spool.write(chunk)
                spool.seek(0)
                okv, why, safe_type = fileserver._file_verdict(name, "", spool.read(64))
                spool.seek(0)
                if not okv:
                    activity._track(uid, "files", "refused a WebDAV save", why[:200])
                    return Response(status_code=415, headers=hdrs)
                # Reserve under the lock, upload OUTSIDE it, commit under it
                # again: the lock is held for milliseconds, so several saves
                # upload side by side instead of queueing.
                now = datetime.now(timezone.utc).isoformat()
                async with fileserver._files_lock:
                    d = fileserver._load_files()
                    parent = webdav._dav_walk_folder(d, segs[:-1])
                    if parent is None:
                        return Response(status_code=409, headers=hdrs)
                    _k, _f = webdav._dav_resolve(d, path)
                    existing = _f if _k == "file" else None
                    if existing is None:
                        # a concurrent save of the same new name reuses its
                        # reservation instead of minting a twin
                        existing = next((k for k, f in d["files"].items()
                                         if str(f.get("folder_id") or "") == parent
                                         and f.get("name", "").lower() == name.lower()
                                         and f.get("status") == "pending"), None)
                    quota = int(fileserver.FILES_QUOTA_GB * 1024 * 1024 * 1024)
                    already = int(d["files"][existing].get("size") or 0) if existing else 0
                    if fileserver._files_usage(d) - already + total > quota:
                        return Response(status_code=507, headers=hdrs)
                    supersede = None
                    if existing and hidden:
                        # Junk sidecars overwrite in place; they are never
                        # versioned and never shown.
                        fid, key, fresh = existing, d["files"][existing]["r2_key"], False
                    elif existing and d["files"][existing].get("status") == "pending":
                        fid, key, fresh = existing, d["files"][existing]["r2_key"], False
                    elif existing:
                        # Saving over a real file keeps the old version: the
                        # prior record goes to the 30-day trash on commit and a
                        # fresh key holds the new bytes, matching how the app's
                        # trash protects every other delete.
                        supersede = existing
                        fid = fileserver._files_id(d, "f")
                        key = f"{fid}/{name}"
                        d["files"][fid] = {"name": name, "folder_id": parent, "size": total,
                                           "type": "application/octet-stream", "r2_key": key,
                                           "status": "pending", "by": uid, "created_at": now,
                                           "hidden": hidden}
                        fresh = True
                    else:
                        fid = fileserver._files_id(d, "f")
                        key = f"{fid}/{name}"
                        d["files"][fid] = {"name": name, "folder_id": parent, "size": total,
                                           "type": "application/octet-stream", "r2_key": key,
                                           "status": "pending", "by": uid, "created_at": now,
                                           "hidden": hidden}
                        fresh = True
                    fileserver._write_files(d)
                spool.seek(0)
                try:
                    await asyncio.to_thread(
                        lambda: fileserver._files_s3().upload_fileobj(spool, fileserver.R2_BUCKET, key))
                except Exception:
                    logger.exception("dav put failed")
                    async with fileserver._files_lock:
                        d = fileserver._load_files()
                        if fresh and d["files"].get(fid, {}).get("status") == "pending":
                            d["files"].pop(fid, None)
                            fileserver._write_files(d)
                    return Response(status_code=502, headers=hdrs)
                async with fileserver._files_lock:
                    d = fileserver._load_files()
                    rec = d["files"].get(fid)
                    if rec is not None:
                        rec.update({"size": total, "status": "active", "by": uid,
                                    "uploaded_at": datetime.now(timezone.utc).isoformat()})
                        if rec.get("folder_id") and not fileserver._files_folder_ok(d, str(rec.get("folder_id"))):
                            rec["folder_id"] = ""    # the folder went mid-upload: top level, not nowhere
                        if supersede and supersede in d["files"] and supersede != fid:
                            old = d["files"][supersede]
                            old["status"] = "trashed"
                            old["trashed_at"] = datetime.now(timezone.utc).isoformat()
                        if not rec.get("hidden"):
                            fileserver._files_supersede(d, fid)   # and any other of its name that landed meanwhile
                        fileserver._write_files(d)
            finally:
                spool.close()
            if not hidden:
                activity._track(uid, "files", "updated a file from Finder" if existing
                       else "added a file from Finder", name)
            return Response(status_code=204 if existing else 201, headers=hdrs)

        if method == "MKCOL":
            segs = webdav._dav_split(path)
            if not segs:
                return Response(status_code=403, headers=hdrs)
            async with fileserver._files_lock:
                d = fileserver._load_files()
                if webdav._dav_walk_folder(d, segs) is not None:
                    return Response(status_code=405, headers=hdrs)
                parent = webdav._dav_walk_folder(d, segs[:-1])
                if parent is None:
                    return Response(status_code=409, headers=hdrs)
                fid = fileserver._files_id(d, "d")
                d["folders"][fid] = {"name": fileserver._files_clean_name(segs[-1]), "parent_id": parent,
                                     "created_at": datetime.now(timezone.utc).isoformat()}
                fileserver._write_files(d)
            activity._track(uid, "files", "made a folder from Finder", segs[-1][:60])
            return Response(status_code=201, headers=hdrs)

        if method == "DELETE":
            async with fileserver._files_lock:
                d = fileserver._load_files()
                kind, kid = webdav._dav_resolve(d, path)
                if kind is None:
                    return Response(status_code=404, headers=hdrs)
                if kind == "folder":
                    if not kid:
                        return Response(status_code=403, headers=hdrs)
                    busy = any(str(f.get("parent_id") or "") == kid for f in d["folders"].values()) \
                        or any(str(v.get("folder_id") or "") == kid
                               and (v.get("status") == "active" or fileserver._files_upload_in_flight(v))
                               for v in d["files"].values())
                    if busy:
                        return Response(status_code=403, headers=hdrs)
                    gone = d["folders"].pop(kid)
                    fileserver._write_files(d)
                    activity._track(uid, "files", "deleted a folder from Finder", gone.get("name") or "")
                    return Response(status_code=204, headers=hdrs)
                f = d["files"][kid]
                if f.get("hidden"):
                    d["files"].pop(kid)
                    if f.get("r2_key"):
                        d.setdefault("doomed", []).append(f["r2_key"])
                else:
                    f["status"] = "trashed"
                    f["trashed_at"] = datetime.now(timezone.utc).isoformat()
                fileserver._write_files(d)
            if not f.get("hidden"):
                activity._track(uid, "files", "put a file in the trash from Finder", f.get("name") or "")
            return Response(status_code=204, headers=hdrs)

        if method in ("MOVE", "COPY"):
            from urllib.parse import urlparse, unquote
            dest = request.headers.get("destination", "")
            dpath = unquote(urlparse(dest).path)
            if not dpath.startswith("/dav"):
                return Response(status_code=400, headers=hdrs)
            dsegs = webdav._dav_split(dpath[4:])
            if not dsegs:
                return Response(status_code=403, headers=hdrs)
            async with fileserver._files_lock:
                d = fileserver._load_files()
                kind, kid = webdav._dav_resolve(d, path)
                if kind is None:
                    return Response(status_code=404, headers=hdrs)
                dparent = webdav._dav_walk_folder(d, dsegs[:-1])
                if dparent is None:
                    return Response(status_code=409, headers=hdrs)
                # A sidecar keeps its dots, as on PUT: cleaned, Finder's rename
                # of ._proof.pdf became a visible "_proof.pdf" that no longer
                # resolved as the sidecar, so the next save uploaded a fresh
                # one and the stray sat in the listing until the reaper took it.
                junk = bool(webdav._DAV_JUNK.match(dsegs[-1]))
                if junk:
                    dname = fileserver._FILENAME_BAD.sub("_", dsegs[-1]).strip()[:180] or "untitled"
                    if dname in (".", ".."):
                        dname = "_" + dname
                else:
                    dname = fileserver._files_clean_name(dsegs[-1])
                # Every other naming path refuses a program extension - upload,
                # rename, mail attach, and PUT through _file_verdict. A rename
                # over the drive did not, so a .txt accepted on the way in
                # could become a .bat on a mount every staff Mac has attached.
                if fileserver._file_ext(dname) in fileserver._DANGEROUS_EXT:
                    return Response(status_code=403, headers=hdrs)
                dk, did = webdav._dav_resolve(d, "/".join(dsegs))
                if dk is not None and did != kid:
                    if request.headers.get("overwrite", "T").upper() == "F":
                        return Response(status_code=412, headers=hdrs)
                    if dk == "file":
                        d["files"][did]["status"] = "trashed"
                        d["files"][did]["trashed_at"] = datetime.now(timezone.utc).isoformat()
                    else:
                        return Response(status_code=412, headers=hdrs)
                if kind == "folder":
                    if method == "COPY":
                        return Response(status_code=403, headers=hdrs)
                    hop, guard = dparent, 0
                    while hop and guard < 60:
                        if hop == kid:
                            return Response(status_code=409, headers=hdrs)  # into its own subtree
                        hop = str(d["folders"].get(hop, {}).get("parent_id") or "")
                        guard += 1
                    d["folders"][kid]["name"] = dname
                    d["folders"][kid]["parent_id"] = dparent
                    fileserver._write_files(d)
                    activity._track(uid, "files", "moved a folder from Finder", dname)
                    return Response(status_code=201, headers=hdrs)
                f = d["files"][kid]
                if method == "MOVE":
                    f["name"], f["folder_id"], f["hidden"] = dname, dparent, junk
                    fileserver._write_files(d)
                    activity._track(uid, "files", "moved a file from Finder", dname)
                    return Response(status_code=201, headers=hdrs)
                # COPY was the one write path with no ceiling: a `cp` loop on
                # the mounted drive is a server-side copy, so a 4GB file could
                # be duplicated to the quota's limit without a byte crossing
                # the wire, and the bill is per stored byte.
                if fileserver._files_usage(d) + int(f.get("size") or 0) > int(fileserver.FILES_QUOTA_GB * 1024 * 1024 * 1024):
                    return Response(status_code=507, headers=hdrs)
                nid = fileserver._files_id(d, "f")
                nkey = f"{nid}/{dname}"
                try:
                    await asyncio.to_thread(lambda: fileserver._files_s3().copy_object(
                        Bucket=fileserver.R2_BUCKET, CopySource={"Bucket": fileserver.R2_BUCKET, "Key": f["r2_key"]},
                        Key=nkey))
                except Exception:
                    logger.exception("dav copy failed")
                    return Response(status_code=502, headers=hdrs)
                d["files"][nid] = {**f, "name": dname, "folder_id": dparent, "r2_key": nkey,
                                   "hidden": junk,
                                   "by": uid, "created_at": datetime.now(timezone.utc).isoformat()}
                fileserver._write_files(d)
                activity._track(uid, "files", "copied a file from Finder", dname)
                return Response(status_code=201, headers=hdrs)

        if method == "LOCK":
            # Finder demands class 2 to mount read-write; the lock is a polite
            # fiction over a store that serialises writes itself.
            token = "opaquelocktoken:" + secrets.token_hex(8)
            xml = ('<?xml version="1.0" encoding="utf-8"?>'
                   '<D:prop xmlns:D="DAV:"><D:lockdiscovery><D:activelock>'
                   '<D:locktype><D:write/></D:locktype><D:lockscope><D:exclusive/></D:lockscope>'
                   '<D:depth>0</D:depth><D:timeout>Second-600</D:timeout>'
                   f'<D:locktoken><D:href>{token}</D:href></D:locktoken>'
                   '</D:activelock></D:lockdiscovery></D:prop>')
            return Response(xml, status_code=200, media_type="application/xml; charset=utf-8",
                            headers={**hdrs, "Lock-Token": "<" + token + ">"})
        if method == "UNLOCK":
            return Response(status_code=204, headers=hdrs)
        return Response(status_code=405, headers=hdrs)
