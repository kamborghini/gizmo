"""The status page's workings: the store report, the last error alert and the
token vault's state. Moved out of copilot.py (stage 4 of the 14 October
audit); its routes, the status page and the health check, are in
gizmo/routes/status.py. Read as `appstatus.NAME`.
"""
import logging
import os
import json
import time
import google_mail
import tokenvault
from gizmo import store as jsonstore

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")




STORE_REPORT_PARSE_MIN = 1024 * 1024     # measure the parse of anything this big


def _store_report(parse: bool = True) -> list:
    """The stores on the volume, largest first, with the cost of reading the
    big ones. Most stores are re-read from disk on every request that needs
    them; the CRM, the dispatch state and the production state each have a
    dozen or more call sites and no cache. Whether that matters is a number,
    not an opinion: this is the number, at boot and in Settings, so the day
    a save on the CRM is slow it is visible before somebody feels it."""
    data_dir = os.path.dirname(scheduler.SCHEDULE_PATH) or "/data"
    out = []
    try:
        names = os.listdir(data_dir)
    except OSError:
        return out
    for n in names:
        if not n.endswith((".json", ".jsonl")):
            continue
        p = os.path.join(data_dir, n)
        try:
            size = os.path.getsize(p)
        except OSError:
            continue
        row = {"name": n, "bytes": size}
        if parse and n.endswith(".json") and size >= STORE_REPORT_PARSE_MIN:
            t0 = time.perf_counter()
            try:
                with open(p, encoding="utf-8") as fh:
                    json.load(fh)
                row["parse_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            except Exception:  # a store that will not parse shows no parse time
                row["parse_ms"] = None
        out.append(row)
    out.sort(key=lambda r: -r["bytes"])
    return out[:12]


_last_error_alert = 0.0


def token_vault_state() -> dict:
    """Whether the secrets on the volume are encrypted, and whether any are not.

    Reads the files rather than trusting that the key is set: a key present but
    a re-seal that never ran would look identical from the environment alone,
    and that is exactly the failure worth catching.
    """
    stores = [
        ("Gmail, sales", google_mail.TOKEN_PATH, "refresh_token"),
    ]
    sealed, plain, present = [], [], 0
    for name, path, field in stores:
        try:
            with open(path, encoding="utf-8") as fh:
                v = (json.load(fh) or {}).get(field)
        except (OSError, ValueError):
            continue
        if not isinstance(v, str) or not v:
            continue
        present += 1
        (sealed if tokenvault.is_sealed(v) else plain).append(name)
    try:
        users = (jsonstore._load_json_store(team.USERS_PATH, "users_store", None) or {}).get("users") or {}
        for rec in users.values():
            if not isinstance(rec, dict):
                continue
            v = rec.get("mfa_secret")
            if isinstance(v, str) and v:
                present += 1
                (sealed if tokenvault.is_sealed(v) else plain).append("A sign-in code secret")
    except Exception:
        pass  # an unreadable accounts file leaves the count as far as it got
    return {"enabled": tokenvault.enabled(), "stored": present,
            "sealed": len(sealed), "plaintext": sorted(set(plain))}


def reseal_secrets_at_rest() -> dict:
    """Encrypt the long-lived secrets already sitting on the volume.

    Setting TOKEN_ENCRYPTION_KEY only changes what is written NEXT. A
    refresh token that is not due to rotate, or an MFA secret that never
    rotates at all, would stay in plaintext indefinitely while the key made it
    look solved - which is worse than knowing it is unencrypted, because
    nobody goes back to check.

    Runs on every boot and is a no-op without a key, or once everything is
    already sealed. Never raises: a store that cannot be re-sealed is worth a
    log line, not a deployment that will not start.
    """
    out = {"enabled": tokenvault.enabled(), "sealed": 0, "stores": {}}
    if not tokenvault.enabled():
        logger.warning("token vault: encryption at rest is OFF. The refresh tokens and "
                       "MFA secrets on the volume are in plaintext. Set "
                       "TOKEN_ENCRYPTION_KEY to encrypt them.")
        return out
    files = [
        ("gmail_sales", google_mail.TOKEN_PATH, ("refresh_token",)),
        ("world_options", desk.WO_SECRET_PATH, ("meter", "key", "password")),
    ]
    for name, path, fields in files:
        try:
            n = tokenvault.reseal_file(path, fields)
        except Exception:
            logger.exception("token vault: could not re-seal %s", name)
            continue
        out["stores"][name] = n
        out["sealed"] += n
    try:
        n = tokenvault.reseal_users(team.USERS_PATH, ("mfa_secret", "mfa_pending"))
        out["stores"]["mfa"] = n
        out["sealed"] += n
        if n:
            # The file on disk changed underneath the cache. Drop it, or the
            # next write puts the plaintext straight back.
            team._users_mem = None
    except Exception:
        logger.exception("token vault: could not re-seal the MFA secrets")
    # Said on every boot, whether or not anything changed. Logging only when a
    # secret was sealed leaves silence meaning two different things - "all
    # already encrypted" and "no key set" - and the deploy log is where someone
    # looks to find out which.
    logger.info("token vault: encryption at rest is ON; %d secret(s) sealed this boot, "
                "%s", out["sealed"],
                "everything else was already sealed" if not out["sealed"] else "")
    return out


def _data_volume_warning() -> str:
    """'' when the data folder sits on a mounted volume, or when the app is
    not running on Railway at all; otherwise what is wrong, in words.

    Nothing checked that the stores were on the durable volume. Without it
    the app runs on the container's own disk, looks healthy, and loses every
    account, dispatch record and note at the next deploy (audit R-018). A
    folder on a volume has the mount point at or above it."""
    if not (os.environ.get("RAILWAY_ENVIRONMENT")  # set by Railway; the volume check runs only there
            or os.environ.get("RAILWAY_PROJECT_ID")):  # set by Railway; the volume check runs only there
        return ""
    d = os.path.realpath(os.path.dirname(team.USERS_PATH) or "/data")
    p = d
    while p and p != os.path.dirname(p):
        if os.path.ismount(p):
            return ""
        p = os.path.dirname(p)
    return ("The data folder is not on a mounted volume, so accounts, dispatch records and everything else "
            "saved here are lost at the next deploy. Attach the volume to this service at " + d + ".")


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as sibling.NAME, never a copied name.
from gizmo import scheduler  # noqa: E402
from gizmo import team  # noqa: E402
from gizmo import dispatch as desk  # noqa: E402
