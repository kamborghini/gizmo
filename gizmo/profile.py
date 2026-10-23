"""The store profile: what the merchant tells the assistant about the store,
kept and handed to every answer. Moved out of copilot.py (stage 4 of the 14
October audit); its route is in gizmo/routes/profile.py. Read as
`store_profile.NAME` (`profile` is a local name in the overview).
"""
import logging
import os
from gizmo.config import _env_num
from gizmo import store as jsonstore

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


# Server-side store profile. Default path lives under /data so a Railway volume
# mounted there makes it durable across redeploys.
PROFILE_PATH       = os.environ.get("PROFILE_PATH", "/data/store_profile.json")
PROFILE_FIELD_CAP  = _env_num(int, os.environ.get("PROFILE_FIELD_CAP", "6000"), "6000", "PROFILE_FIELD_CAP")




def _load_profile() -> dict:
    # Through the one loader, so an unreadable file pauses the writer: read
    # by hand, a corrupt profile loaded as empty and the next save replaced it.
    d = jsonstore._load_json_store(PROFILE_PATH, None, {})
    return d if isinstance(d, dict) else {}


def _save_profile(data: dict) -> dict:
    data = data or {}
    prefs = data.get("prefs") or {}
    clean = {
        "brand_voice": str(data.get("brand_voice", ""))[:PROFILE_FIELD_CAP],
        "business_goals": str(data.get("business_goals", ""))[:PROFILE_FIELD_CAP],
        "strategy": str(data.get("strategy", ""))[:PROFILE_FIELD_CAP],
        "notes": str(data.get("notes", ""))[:PROFILE_FIELD_CAP],
        "prefs": {
            "track_inventory": bool(prefs.get("track_inventory", True)),
            "concise": bool(prefs.get("concise", False)),
            "proactive": bool(prefs.get("proactive", True)),
            "flag_anomalies": bool(prefs.get("flag_anomalies", True)),
        },
    }
    if not jsonstore._store_writable(PROFILE_PATH):
        return clean
    jsonstore._write_json_store(PROFILE_PATH, None, clean)
    return clean


def _profile_to_system(p: dict) -> str:
    """Compose the stored profile into an authoritative system addendum."""
    if not p:
        return ""
    fields = []
    for key, label in (("brand_voice", "Brand voice"), ("business_goals", "Business goals"),
                       ("strategy", "Overall strategy"), ("notes", "Other notes")):
        val = (p.get(key) or "").strip()
        if val:
            fields.append(f"- {label}: {val}")
    prefs = p.get("prefs") or {}
    rules = []
    if prefs.get("track_inventory") is False:
        rules.append("Our Shopify products carry unlimited stock: give no inventory or restock advice about them. "
                     "The glass stock sheet is tracked separately and its tools may be used.")
    if prefs.get("concise"):
        rules.append("Keep answers concise and skimmable; favor short bullets over prose.")
    if prefs.get("proactive", True):
        rules.append("Always surface 1–3 concrete recommendations or opportunities, even when not asked.")
    if prefs.get("flag_anomalies", True):
        rules.append("Proactively flag anomalies, risks, or unusual changes you notice in the data.")
    if not fields and not rules:
        return ""
    block = "\n\n## Store profile — set by the merchant (authoritative; follow in every answer)\n"
    if fields:
        block += "\n".join(fields) + "\n"
    if rules:
        block += "Preferences:\n" + "\n".join("- " + r for r in rules)
    return block


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as sibling.NAME, never a copied name.
