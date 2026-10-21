"""The way to Shopify: _tool_json reads through the tool registry, and the
capabilities server.py hands to add_routes (the order tag, fulfilment,
payment terms and order writers, the scope, tax id, forecast, install,
customer and product readers, the API version) are kept here.

Moved out of copilot.py (stage 4 of the 14 October audit); part of the floor,
so it imports nothing above it. Read as `shopify.NAME`; add_routes stores the
capabilities on this module.
"""
import logging
import re
import json

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")



async def _tool_json(registry: dict, name: str, args: dict) -> dict:
    func, model = registry[name]
    raw = None
    try:
        raw = await func(model(**(args or {})))
        return json.loads(raw)
    except Exception:
        # Signal failure rather than an empty result: callers must not report a
        # throttled/errored fetch as a real zero (that produces false alerts).
        # What the tool said is kept, so a caller can tell "not there" from
        # "not answered".
        logger.warning("shopify tool %s failed; treating as unavailable", name)
        return {"_failed": True, "_said": str(raw or "")[:300]}


def _shopify_gone(d) -> bool:
    """A read that Shopify answered with "no such thing" (a deleted order), as
    opposed to one that was not answered. Retrying the first never helps."""
    said = str((d or {}).get("_said") or (d or {}).get("error") or "") if isinstance(d, dict) else ""
    return bool(re.search(r"resource not found|\b404\b", said, re.I))
_order_tag_writer = None
_payment_terms_writer = None
_scope_reader = None
_tax_id_reader = None
_product_meta_reader = None
_forecast_reader = None   # the forecast job's four store reads, made with the app's credential
_install_checker = None   # "installed" / "gone" / "unknown": asked before a shop/redact erases
_customer_checker = None  # "live" / "gone" / "unknown": asked before a customers/redact erases
# The Shopify version the server talks to, handed over by add_routes. Never
# found by the server's module name: production starts `python server.py`,
# which Python files under __main__, so a lookup by name finds nothing there.
_api_version = ""
_order_writer = None
_fulfillment_writer = None
_fulfillment_canceler = None
_webhook_ensurer = None


def _ok(d) -> bool:
    """True when a _tool_json result is real data (not a swallowed failure)."""
    return isinstance(d, dict) and not d.get("_failed")
