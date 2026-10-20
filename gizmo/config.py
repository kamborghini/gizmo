"""Reading settings from the environment, for copilot.py and the modules
moved out of it. Imports nothing from the app, so any module can use it at
import time."""
import logging


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
