"""The status page's workings: the store report, the last error alert and the
token vault's state. Moved out of copilot.py (stage 4 of the 14 October
audit); its routes, the status page and the health check, are in
gizmo/routes/status.py. Read as `appstatus.NAME`.
"""
import logging
import os
import json
import time
import google_data
import google_mail
import xero as xero_api
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
            except Exception:
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
        ("Gmail, finance", google_mail.FINANCE_TOKEN_PATH, "refresh_token"),
        ("Google data", google_data.OAUTH_TOKEN_PATH, "refresh_token"),
        ("Xero", xero_api.TOKEN_PATH, "refresh_token"),
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
        pass
    return {"enabled": tokenvault.enabled(), "stored": present,
            "sealed": len(sealed), "plaintext": sorted(set(plain))}


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as core.NAME and sibling.NAME, never a copied name.
from gizmo import scheduler  # noqa: E402
from gizmo import team  # noqa: E402
import copilot as core  # noqa: E402
