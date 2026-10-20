"""Files: the office file server, without the office. The R2 bucket's client
and its setup, the Files store and its copy in memory, names, kinds and
previews, uploads in flight, quota and usage, the reaper, supersede and
purge, signed links, and the boot clean-up server.py runs. Moved out of
copilot.py (stage 4 of the 14 October audit); its routes are in
gizmo/routes/files.py. Read as `fileserver.NAME` (`files` is a local name in
the inbox and a test).
"""
import logging
import os
import re
import time
import threading
import hashlib
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
from starlette.requests import Request
from starlette.responses import Response
from gizmo.config import _env_num
from gizmo import store as jsonstore

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")




# ---------------------------------------------------------------------------
# Files: the office file server, without the office.
#
# The split that makes it work: NAMES live here, BYTES live in Cloudflare R2.
# The folder tree, filenames, and trash are a JSON store on the volume (backed
# up with everything else, instant to list); the file contents sit in an R2
# bucket, which is durable object storage costing pennies for 50GB. The app
# never carries the bytes: it signs short-lived URLs and the browser talks to
# Cloudflare directly, so dragging a 2GB artwork file in from home moves at
# the home connection's speed, not through Railway.
#
# A record's R2 key is minted once and never renamed: renames and moves are
# metadata edits. Deleting is a 30-day trash (or an explicit "delete now" from
# it); either way the key first moves to a doomed list that is WRITTEN TO DISK
# before any byte dies, and the hourly reaper is the only code that touches
# delete_object, retrying until the bucket confirms.
# ---------------------------------------------------------------------------
R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "").strip()
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
R2_BUCKET = os.environ.get("R2_BUCKET", "gizmo-files").strip()
FILES_PATH = os.environ.get("FILES_PATH", "/data/files.json")
FILES_QUOTA_GB = _env_num(float, os.environ.get("FILES_QUOTA_GB", "50"), "50", "FILES_QUOTA_GB")
FILES_MAX_UPLOAD = 4 * 1024 * 1024 * 1024      # a single presigned PUT tops out near 5GB
FILES_REAP_MAX = _env_num(int, os.environ.get("FILES_REAP_MAX", "4000"), "4000", "FILES_REAP_MAX")     # keys per reaper tick
FILES_REAP_SECONDS = _env_num(float, os.environ.get("FILES_REAP_SECONDS", "20"), "20", "FILES_REAP_SECONDS")  # and its deadline
FILES_TRASH_DAYS = 30
_files_s3_client = None
_files_s3_birth = threading.Lock()   # boto3's default session is not thread-safe to build on
_files_ready = {"bucket": False, "cors": False, "error": "", "at": 0.0}
# Uploads now set the bucket up before taking the store's lock, so three at
# once can reach the setup together; one sets it up and the others wait for
# its answer, rather than each creating the bucket and two reporting failure.
# They wait a few seconds at most: against a storage that hangs, one setup
# runs for up to a minute (short timeouts, but three tries of two calls), and
# an upload is refused sooner than that by the failure that stands.
_files_setup_lock = threading.Lock()
FILES_SETUP_WAIT = 5.0
# One writer at a time: every route that loads, mutates and writes the store
# holds this across the whole exchange. The browser deliberately runs three
# uploads at once, so without it two upload-url calls interleave around their
# await and the later write silently drops the earlier record.
_files_lock = asyncio.Lock()


def _files_configured() -> bool:
    return bool(R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY)


def _files_s3():
    """The S3-protocol client for R2, built once. A seam the tests replace."""
    global _files_s3_client
    with _files_s3_birth:
        if _files_s3_client is None:
            import boto3
            from botocore.config import Config as _BotoConfig
            _files_s3_client = boto3.client(
                "s3",
                # R2_ENDPOINT is a test-rig override; production always derives
                # the real account endpoint.
                endpoint_url=_files_endpoint(),
                aws_access_key_id=R2_ACCESS_KEY_ID,
                aws_secret_access_key=R2_SECRET_ACCESS_KEY,
                region_name="auto",
                # Short timeouts: these calls run while a route (and the store
                # lock) waits, so a hung R2 must fail in seconds, not minutes.
                config=_BotoConfig(signature_version="s3v4", connect_timeout=5,
                                   read_timeout=10, retries={"max_attempts": 2}))
    return _files_s3_client


def _files_ensure_bucket(page_origin: str) -> None:
    """Create the bucket and set its CORS on first use, so the only setup the
    merchant does is pasting three credentials. CORS must allow the app's own
    origin or the browser's direct PUT to Cloudflare is refused before it
    starts. Never raises; failures surface in the status block."""
    if _files_ready["bucket"] and _files_ready["cors"]:
        return
    # A failing bucket is not probed on every presign: one attempt a minute
    # after the last one failed, so a dead R2 costs each upload a quick
    # refusal, not a retry storm.
    if _files_ready["error"] and time.time() - float(_files_ready.get("at") or 0) < 60:
        return
    if not _files_setup_lock.acquire(timeout=FILES_SETUP_WAIT):
        return
    try:
        _files_ensure_bucket_locked(page_origin)
    finally:
        _files_setup_lock.release()


def _files_ensure_bucket_locked(page_origin: str) -> None:
    # Looked at again under the lock: a call that waited here while another
    # set the bucket up, or failed to, takes that answer rather than asking
    # storage a second time.
    if _files_ready["bucket"] and (_files_ready["cors"] or not page_origin) and not _files_ready["error"]:
        return
    if _files_ready["error"] and time.time() - float(_files_ready.get("at") or 0) < 60:
        return
    s3 = _files_s3()
    try:
        if not _files_ready["bucket"]:
            try:
                s3.head_bucket(Bucket=R2_BUCKET)
            except Exception:
                s3.create_bucket(Bucket=R2_BUCKET)
            _files_ready["bucket"] = True
        if not _files_ready["cors"] and page_origin:
            s3.put_bucket_cors(Bucket=R2_BUCKET, CORSConfiguration={
                "CORSRules": [{"AllowedOrigins": [page_origin],
                               "AllowedMethods": ["PUT", "GET"],
                               "AllowedHeaders": ["content-type"],
                               "MaxAgeSeconds": 3600}]})
            _files_ready["cors"] = True
        _files_ready["error"] = ""
    except Exception as e:
        # Stamped when an attempt FAILS, not when it starts: uploads arriving
        # while a retry is still asking storage wait on the lock for its
        # answer, instead of taking the retry for a failure a moment ago.
        _files_ready["at"] = time.time()
        _files_ready["error"] = f"{type(e).__name__}: {e}"[:200]
        logger.warning("files: bucket setup failed: %s", _files_ready["error"])


def _files_default() -> dict:
    return {"seq": 0, "folders": {}, "files": {}, "doomed": []}


_files_mem: Optional[dict] = None


def _let_go_of_files_in_memory(paths) -> list:
    """Let go of the Files store held in memory (see jsonstore.holds_in_memory)."""
    global _files_mem
    if paths is None or FILES_PATH in paths:
        _files_mem = None
        return [FILES_PATH]
    return []


jsonstore.holds_in_memory(_let_go_of_files_in_memory)




def _load_files() -> dict:
    """Disk is the record; memory serves the requests. Finder lists a folder
    many times a minute, and re-parsing the store from disk each time was the
    single biggest cost on the drive."""
    global _files_mem
    if _files_mem is not None:
        return _files_mem
    d = jsonstore._load_json_store(FILES_PATH, "files_store", None)
    if not isinstance(d, dict) or "files" not in d:
        d = _files_default()
    for k, v in _files_default().items():
        d.setdefault(k, v)
    try:
        peak = max((int(str(k)[1:]) for coll in ("folders", "files")
                    for k in d.get(coll, {}) if str(k)[1:].isdigit()), default=0)
        d["seq"] = max(int(d.get("seq") or 0), peak)
    except (TypeError, ValueError):
        pass
    _files_mem = d
    return d


def rescue_misfiled_junk() -> dict:
    """Un-hide files that were only ever "junk" because the pattern was wrong.

    A hidden file is invisible in the Files tab, absent from the ledger, exempt
    from the 30-day trash, and DESTROYED thirty days after it was saved. The old
    pattern matched any name beginning with an underscore, so `_JOB4471.eps`
    saved from Finder had all four of those properties by accident.

    Fixing the pattern only helps files saved from now on: a record already
    marked hidden stays hidden, and stays on course to be reaped. This corrects
    the records, and must run before the reaper next ticks.

    Idempotent, and a no-op once nothing is mis-marked. Never raises: a repair
    that cannot run is a log line, not a deployment that will not start.
    """
    out = {"rescued": 0, "names": []}
    try:
        d = _load_files()
        for f in (d.get("files") or {}).values():
            if not isinstance(f, dict) or not f.get("hidden"):
                continue
            name = str(f.get("name") or "")
            if name and not webdav._DAV_JUNK.match(name):
                f["hidden"] = False
                out["rescued"] += 1
                if len(out["names"]) < 20:
                    out["names"].append(name)
        if out["rescued"]:
            _write_files(d)
            logger.warning("files: un-hid %d file(s) that were never junk; they were "
                           "invisible in the app and due to be deleted 30 days after "
                           "they were saved: %s", out["rescued"], ", ".join(out["names"]))
    except Exception:
        logger.exception("files: could not rescue mis-marked files")
    return out


def _write_files(d: dict) -> None:
    global _files_mem
    try:
        if not jsonstore._store_writable(FILES_PATH):
            raise RuntimeError("files store is not writable")
        jsonstore._write_json_store(FILES_PATH, "files_store", d)
        _files_mem = d
    except Exception:
        _files_mem = None    # memory never outlives a failed write
        raise


def _files_id(d: dict, prefix: str) -> str:
    d["seq"] = int(d.get("seq") or 0) + 1
    return f"{prefix}{d['seq']}"


# Bidi overrides and isolates let a stranger send "artworkfdp.eps" that
# DISPLAYS as "artwork.pdf" on the Finder drive. Names used to come only
# from staff uploads; attachments changed that.
_FILENAME_BAD = re.compile(
    r"[\\/\x00-\x1f\x7f-\x9f\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069\u2028\u2029"
    # Zero-width and soft hyphen: invisible, and NOT stripped as whitespace, so
    # "proof<ZWSP>.pdf" renders in Finder as exactly "proof.pdf".
    r"­\u200b\u200c\u200d⁠\ufeff]")


FILES_UPLOAD_IN_FLIGHT_SECS = 3600


def _files_upload_in_flight(v: dict) -> bool:
    """A pending upload young enough to still be arriving. One abandoned by a
    closed tab stays pending until the two-day purge; treating it as an
    occupant made its folder undeletable while showing empty."""
    if not isinstance(v, dict) or v.get("status") != "pending":
        return False
    try:
        when = datetime.fromisoformat(str(v.get("created_at") or ""))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return (datetime.now(timezone.utc) - when).total_seconds() < FILES_UPLOAD_IN_FLIGHT_SECS


def _files_name_taken(d: dict, folder_id: str, name: str, skip_id: str = "") -> bool:
    """Is an ACTIVE file already called this in this folder? Two active records
    with one name in one folder make the newer unreachable on the Finder drive
    (WebDAV resolves by name), so rename, move and restore have to refuse it -
    the upload paths already supersede on the same condition."""
    want = (name or "").strip().lower()
    fol = str(folder_id or "")
    return any(v.get("status") == "active" and str(k) != str(skip_id)
               and str(v.get("folder_id") or "") == fol
               and str(v.get("name") or "").strip().lower() == want
               for k, v in d.get("files", {}).items())


# What a file IS is read from its first bytes, never from its name or the type
# the browser claimed. Uploads go straight to the bucket, so this is the one
# look the app gets, and it is taken before a record turns active.
_DANGEROUS_EXT = {
    "ade", "adp", "apk", "appx", "bat", "cab", "chm", "cmd", "com", "cpl", "dll", "dmg", "exe",
    "hta", "ins", "isp", "iso", "jar", "js", "jse", "lib", "lnk", "mde", "msc", "msi", "msix",
    "msp", "mst", "nsh", "pif", "ps1", "scr", "sct", "shb", "sys", "vb", "vbe", "vbs", "vxd",
    "wsc", "wsf", "wsh", "reg", "gadget", "application"}
_IMAGE_EXT = {"png": "png", "jpg": "jpeg", "jpeg": "jpeg", "gif": "gif", "webp": "webp"}
_KIND_MIME = {"png": "image/png", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp",
              "pdf": "application/pdf"}
_CLAIM_KIND = {"image/png": "png", "image/jpeg": "jpeg", "image/jpg": "jpeg", "image/gif": "gif",
               "image/webp": "webp", "application/pdf": "pdf"}


def _file_ext(name: str) -> str:
    n = str(name or "")
    return n.rsplit(".", 1)[-1].lower() if "." in n else ""


def _sniff_kind(head: bytes) -> str:
    """The format the first bytes announce, or "" for anything unrecognised."""
    h = bytes(head or b"")
    if h.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if h.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if h[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if h[:4] == b"RIFF" and h[8:12] == b"WEBP":
        return "webp"
    if h.startswith(b"%PDF"):
        return "pdf"
    if h.startswith(b"PK\x03\x04"):
        return "zip"
    if h.startswith(b"MZ"):
        return "exe"
    if h.startswith(b"\x7fELF"):
        return "elf"
    if h[:4] in (b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe",
                 b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe"):
        return "macho"
    if h.startswith(b"#!"):
        return "script"
    t = h.lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if t.startswith((b"<!doctype html", b"<html", b"<script", b"<svg", b"<?xml")):
        return "html"
    return ""


def _file_verdict(name: str, claimed: str, head: bytes) -> tuple:
    """(ok, reason, safe_type). Programs are refused whatever they are called;
    a name or claim that says image or PDF must be backed by matching bytes;
    markup dressed as a picture is refused; and the type the app records is
    the one the bytes justify, so a served preview can never say "image" about
    something that is not one."""
    n = str(name or "")
    ext, kind, cl = _file_ext(n), _sniff_kind(head), str(claimed or "").lower().split(";")[0].strip()
    if ext in _DANGEROUS_EXT:
        return False, f"{n} is a program, not a document.", ""
    if kind in ("exe", "elf", "macho", "script"):
        return False, f"{n} is a program, whatever it is called.", ""
    want = _IMAGE_EXT.get(ext) or ("pdf" if ext == "pdf" else "") or _CLAIM_KIND.get(cl, "")
    if want and kind != want:
        return False, f"{n} does not contain what its name or type says it is.", ""
    if kind == "html" and cl.startswith("image/"):
        return False, f"{n} is markup dressed as a picture.", ""
    safe = _KIND_MIME.get(kind) or ("text/plain" if cl in ("text/html", "application/xhtml+xml",
                                                          "image/svg+xml") else (cl or "application/octet-stream"))
    return True, "", safe


def _files_head_bytes(key: str, n: int = 64) -> bytes:
    """The first n bytes of an object. Blocking; call off the event loop."""
    obj = _files_s3().get_object(Bucket=R2_BUCKET, Key=key, Range=f"bytes=0-{n - 1}")
    return obj["Body"].read(n)


def _files_clean_name(name: str) -> str:
    """A display name that cannot climb paths or break the UI. The R2 key never
    contains it, so this is about honesty on screen, not storage safety."""
    n = _FILENAME_BAD.sub("_", str(name or "")).strip().strip(".")
    return n[:180] or "untitled"


def _files_usage(d: dict) -> int:
    """Space spoken for: active files, the trash (still in the bucket), and
    uploads in flight, so three simultaneous uploads cannot each squeeze
    through the same last gigabyte."""
    return sum(int(f.get("size") or 0) for f in d["files"].values()
               if f.get("status") in ("active", "pending") or f.get("trashed_at"))


def _files_folder_ok(d: dict, folder_id: str) -> bool:
    return folder_id == "" or folder_id in d["folders"]


def _files_supersede(d: dict, fid: str) -> list:
    """The file just completed is THE file of its name in its folder: every
    other active one goes to the bin. Decided at completion, not when the
    upload was reserved: two uploads of one name whose reservations overlapped
    (two people, a drop repeated while a big file was sending, a double Save
    to Files) each saw nothing to replace, and the folder was left with two
    active files of one name, the newer unreachable from Finder."""
    f = d["files"].get(fid) or {}
    name = str(f.get("name") or "").lower()
    folder = str(f.get("folder_id") or "")
    now = datetime.now(timezone.utc).isoformat()
    gone = []
    for k, v in d["files"].items():
        if k != fid and v.get("status") == "active" and not v.get("hidden") \
                and str(v.get("name") or "").lower() == name and str(v.get("folder_id") or "") == folder:
            v["status"], v["trashed_at"] = "trashed", now
            gone.append(k)
    return gone


def _files_purge(d: dict) -> None:
    """Metadata only: trash past its window and uploads that never completed
    move their keys to the doomed list. No byte dies here; the reaper deletes
    from the bucket only after this state has safely reached disk, so a failed
    write can never leave a trash entry whose bytes are already gone."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=FILES_TRASH_DAYS)).isoformat()
    stale_pending = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    doomed = [k for k, f in d["files"].items()
              if (f.get("trashed_at") and f["trashed_at"] < cutoff)
              or (f.get("status") == "pending" and str(f.get("created_at") or "") < stale_pending)
              or (f.get("hidden") and str(f.get("uploaded_at") or "") < cutoff)]
    for k in doomed:
        f = d["files"].pop(k)
        if f.get("r2_key"):
            d.setdefault("doomed", []).append(f["r2_key"])


def _files_reap(d: dict, s3) -> bool:
    """Delete doomed bytes from the bucket; keys stay on the list until the
    bucket confirms, so a failed delete is retried next hour instead of
    orphaning a billed object forever. Returns True when the list changed."""
    done = []
    # Batched, capped and deadlined. One key at a time with no ceiling meant an
    # R2 outage held _files_lock for ~30s per key, stalling Files, the Finder
    # drive and the whole scheduler tick behind a bucket that was not answering.
    todo = list(d.get("doomed") or [])[:FILES_REAP_MAX]
    started = time.monotonic()
    for i in range(0, len(todo), 1000):
        if time.monotonic() - started > FILES_REAP_SECONDS:
            logger.info("files: reaper hit its deadline, %d keys left for the next tick",
                        len(todo) - len(done))
            break
        chunk = todo[i:i + 1000]
        try:
            res = s3.delete_objects(Bucket=R2_BUCKET,
                                    Delete={"Objects": [{"Key": k} for k in chunk],
                                            "Quiet": True})
            failed = {e.get("Key") for e in ((res or {}).get("Errors") or [])}
            done.extend(k for k in chunk if k not in failed)
            if failed:
                logger.warning("files: %d keys refused deletion, next tick retries", len(failed))
        except Exception:
            logger.warning("files: batch delete failed for %d keys, next tick retries", len(chunk))
            break
    if done:
        d["doomed"] = [k for k in d["doomed"] if k not in done]
        return True
    return False


def _files_sent(d: dict) -> tuple:
    """(raw, revision): the store as the page is sent it, and a fingerprint of
    those bytes. The page sends the revision back and an unchanged store is
    not sent again; like the CRM's, it moves only when what would be sent
    moves (the 2026-10-12 speed audit, S9)."""
    raw = gate._json_dumps_like_starlette(_files_shape(d))
    return raw, hashlib.blake2b(raw, digest_size=8).hexdigest()


def _files_delta(d: dict, files=(), folders=()) -> dict:
    """What a page that asked for it (delta) needs to bring its copy of the
    store up to date after a change to these records, shaped exactly as
    _files_shape shapes them: each record as it now shows (None when it no
    longer shows), each one's trash entry likewise, the space used, and the
    two things a page's copy holds that change without a record changing:
    the storage error (an upload is often what finds storage back) and the
    names of the people who uploaded."""
    out = {"files": {}, "trash": {}, "folders": {}, "used": _files_usage(d),
           "setup_error": _files_ready["error"], "names": team._team_names()}
    for k in files:
        v = d["files"].get(k)
        out["files"][k] = v if v and v.get("status") == "active" and not v.get("hidden") else None
        out["trash"][k] = {**v, "id": k} if v and v.get("trashed_at") else None
    for k in folders:
        out["folders"][k] = d["folders"].get(k)
    return out


def _files_shape(d: dict) -> dict:
    used = _files_usage(d)
    return {"folders": d["folders"],
            "files": {k: v for k, v in d["files"].items()
                      if v.get("status") == "active" and not v.get("hidden")},
            "trash": [{**v, "id": k} for k, v in d["files"].items() if v.get("trashed_at")],
            "used": used, "quota": int(FILES_QUOTA_GB * 1024 * 1024 * 1024),
            "names": team._team_names(),   # resolves `by` ids to people at render time
            "configured": _files_configured(), "setup_error": _files_ready["error"]}


def _files_origin() -> str:
    url = (os.environ.get("APP_URL") or "").strip().rstrip("/")
    if not url:
        dom = (os.environ.get("RAILWAY_PUBLIC_DOMAIN") or "").strip()
        url = f"https://{dom}" if dom else ""
    return url


def _files_disposition(name: str, inline: bool = False) -> str:
    """Downloads keep their real filename even when it has accents or symbols:
    a plain-ASCII fallback plus the RFC 5987 encoded form."""
    from urllib.parse import quote
    ascii_name = re.sub(r"[^ -~]", "_", name).replace('"', "'")
    kind = "inline" if inline else "attachment"
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"


# Only these render safely in a browser tab; everything else stays a download.
# SVG is deliberately absent: it can carry scripts, so it never serves inline.
_PREVIEW_MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                 "gif": "image/gif", "webp": "image/webp", "pdf": "application/pdf"}


def _files_preview_mime(name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return _PREVIEW_MIME.get(ext, "")


def _files_endpoint() -> str:
    return os.environ.get("R2_ENDPOINT") or f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"


def _files_sign_put(key: str, ctype: str, size: int = 0, setup: bool = True) -> str:
    """Blocking (network on first use); call off the event loop. A caller
    holding the store's lock passes setup=False, having set the bucket up
    before it took the lock: this then only signs, and never waits on a
    setup (its own, or another upload's retry) with the lock held.

    The signature BINDS the length when one is known: without it the URL
    authorised a PUT of any size R2 accepts, so a client could declare 1KB,
    pass the quota check, and then store gigabytes against a record that says
    1KB - and the presign stayed valid for a quarter of an hour after the
    upload was confirmed, long enough to swap the object afterwards."""
    if setup:
        _files_ensure_bucket(_files_origin())
    if not _files_ready["bucket"]:
        raise RuntimeError(_files_ready["error"] or "bucket unavailable")
    params = {"Bucket": R2_BUCKET, "Key": key, "ContentType": ctype}
    if size > 0:
        params["ContentLength"] = int(size)
    # 15 minutes: the browser PUTs immediately, and a PUT that starts before
    # the deadline may finish after it, so this does not cut off big files.
    # What it does shrink is how long a leaked URL could replay an overwrite.
    return _files_s3().generate_presigned_url(
        "put_object", Params=params, ExpiresIn=900)


def _files_sign_get(key: str, name: str, inline: bool = False) -> str:
    params = {"Bucket": R2_BUCKET, "Key": key,
              "ResponseContentDisposition": _files_disposition(name, inline=inline)}
    if inline:
        # The stored type is whatever the uploader claimed (Finder says
        # octet-stream for everything), so the preview type comes from the
        # extension, and only from the safe list.
        params["ResponseContentType"] = _files_preview_mime(name) or "application/octet-stream"
    return _files_s3().generate_presigned_url("get_object", Params=params, ExpiresIn=300)


def _r2_call(method: str, **kw):
    """One storage call, client and all. For asyncio.to_thread: building the
    client is itself a blocking call (the first use after a deploy imports
    and configures boto3), so `to_thread(_files_s3().get_object, ...)` ran
    that part on the event loop."""
    return getattr(_files_s3(), method)(Bucket=R2_BUCKET, **kw)


def _files_head(key: str):
    """True byte count of what actually landed in the bucket. None means the
    bucket answered 'no such object'; anything else raises, because a storage
    wobble must never be reported as 'your upload vanished'."""
    try:
        return int(_files_s3().head_object(Bucket=R2_BUCKET, Key=key)["ContentLength"])
    except Exception as e:
        resp = getattr(e, "response", None)
        code = str(((resp or {}).get("Error") or {}).get("Code") or "") if isinstance(resp, dict) else ""
        if code in ("404", "NoSuchKey", "NotFound") or "404" in str(e):
            return None
        raise RuntimeError(f"storage head failed: {type(e).__name__}") from e


def _files_tick() -> None:
    """Hourly housekeeping: move expired trash and abandoned uploads to the
    doomed list, persist that, and only then reap doomed bytes from the
    bucket. Blocking; the scheduler runs it in a thread under the store lock."""
    # A COPY: this runs in a worker thread while event-loop readers iterate
    # the shared store, and popping entries under them raises "dictionary
    # changed size during iteration" in whichever request happened to be
    # reading. The swap at the end is a single assignment, which is atomic.
    import copy as _copy
    d = _copy.deepcopy(_load_files())
    before = (len(d["files"]), len(d.get("doomed") or []))
    _files_purge(d)
    if (len(d["files"]), len(d["doomed"])) != before:
        if not jsonstore._store_writable(FILES_PATH):
            return                          # nothing deleted unless the pop is durable
        _write_files(d)
    if _files_configured() and d.get("doomed"):
        if _files_reap(d, _files_s3()) and jsonstore._store_writable(FILES_PATH):
            _write_files(d)
    # Once a day, on the same tick: outgoing attachments are bucket-only, so
    # they have no record here to expire and need their own sweep.
    if time.monotonic() - mail._mail_sweep_last["t"] > 86400:
        mail._mail_sweep_last["t"] = time.monotonic()
        try:
            mail._mail_sweep_attachments()
        except Exception:
            logger.warning("mail: the attachment sweep did not finish; next tick retries")
        try:
            privacy._redact_archive_reap()
        except Exception:
            logger.warning("privacy: the pre-redact archive sweep did not finish")
_FILES_STORE_FAIL = ("The change could not be saved. The data volume may be "
                     "unwritable; check Settings, Connections.")

# ---- Files routes -----------------------------------------------------
# The office file server, minus the office. These routes only ever handle
# names and signed URLs; the bytes go browser-to-bucket directly.
async def _files_guard(request: Request):
    return await gate._guard(request)

def _files_ok(d: dict, extra: Optional[dict] = None, action: str = "",
              detail: str = "", who: str = "", delta: Optional[dict] = None) -> Response:
    """Save, then answer the whole store with its revision; or, for a page
    that asked (delta), only what changed, which it patches into its copy."""
    _write_files(d)
    if action:
        activity._track(who, "files", action, detail)
    if delta is not None:
        return gate._json({"ok": True, **(extra or {}), "delta": delta})
    raw, rev = _files_sent(d)
    return gate._json_spliced({"ok": True, **(extra or {}), "rev": rev}, "store", raw)


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as core.NAME and sibling.NAME, never a copied name.
from gizmo import activity  # noqa: E402
from gizmo import gate  # noqa: E402
from gizmo import mail  # noqa: E402
from gizmo import team  # noqa: E402
from gizmo import webdav  # noqa: E402
import copilot as core  # noqa: E402
from gizmo import privacy  # noqa: E402
