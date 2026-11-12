"""Reading settings from the environment, for copilot.py and the modules
moved out of it. Imports nothing from the app, so any module can use it at
import time."""
import logging
import os


def _env_num(cast, raw, default, name):
    """A numeric setting, read forgivingly: a value set but not a number
    ("60s", "$25", "") is logged and the default used. Parsed bare, one typo
    in Railway crashed the whole app at import, and the log blamed the chat."""
    try:
        return cast(raw)
    except (TypeError, ValueError):
        logging.getLogger("shopify_mcp").warning(
            "setting %s=%r is not a number; using the default %s", name, raw, default)
        return cast(default)


# App Bridge identity = the app's Client ID + secret. Accept either the
# SHOPIFY_API_KEY/SECRET names or the SHOPIFY_CLIENT_ID/SECRET names (same values).
SHOPIFY_API_KEY    = os.environ.get("SHOPIFY_API_KEY") or os.environ.get("SHOPIFY_CLIENT_ID", "")
SHOPIFY_API_SECRET = os.environ.get("SHOPIFY_API_SECRET") or os.environ.get("SHOPIFY_CLIENT_SECRET", "")
SHOPIFY_STORE      = os.environ.get("SHOPIFY_STORE", "")        # used to pin session tokens to this shop
# Only while the app's client secret is being rotated: the old one. Shopify
# keeps signing session tokens and webhooks with the old secret until it is
# revoked (webhooks for up to an hour after), so it is accepted for CHECKING
# them in that window; it never signs anything and never asks for a token.
# Unset the rest of the time.
SHOPIFY_API_SECRET_PREVIOUS = os.environ.get("SHOPIFY_CLIENT_SECRET_PREVIOUS", "")  # the old app secret, only during a rotation


def shopify_secrets() -> list[str]:
    """The secrets a session token or a webhook may be signed with: the app's
    own, then the previous one during a rotation."""
    return [s for s in (SHOPIFY_API_SECRET, SHOPIFY_API_SECRET_PREVIOUS) if s]


_previous_secret_seen: set[str] = set()


def note_previous_secret(what: str) -> None:
    """Logged the first time, after each start, that a session token or a
    webhook arrives signed with the old secret: a sign Shopify has not
    switched yet, so it is not yet time to drop the previous one."""
    if what not in _previous_secret_seen:
        _previous_secret_seen.add(what)
        logging.getLogger("shopify_mcp").info("rotation: a %s was signed with the previous app secret", what)
# Public base URL (e.g. https://your-app.up.railway.app). When set, the Google
# OAuth redirect URI is derived from it rather than the request Host header.
APP_BASE_URL       = os.environ.get("APP_BASE_URL", "").strip()
# The recovery key for a one-time connect link (the Inbox's mailbox walk):
# a link carrying it may start the walk without a signed-in admin.
CONNECT_SECRET     = os.environ.get("GOOGLE_CONNECT_SECRET", "")
