"""The whole catalogue, read page by page, for the loan-unit picker. The
Products tab that was its first reader went with the report tabs (22 Oct
2026). Read as `catalog.NAME` (`products` is a local name in several
functions).
"""
import logging
from gizmo import shopify

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


async def _all_products(registry: dict, fields: str) -> tuple:
    """Every product in the catalogue, paged by since_id: (products, ok, truncated).

    ok is False when any page failed, and what came before it is returned
    only so a caller can say how far it got. truncated is True only when the
    page cap stopped the read AND a further product exists. Its callers once
    read a single page of 250 and missed every product after it."""
    products, since_id, pages = [], 0, 0
    while True:
        data = await shopify._tool_json(registry, "shopify_list_products",
                                {"limit": 250, "since_id": since_id, "fields": fields})
        if not shopify._ok(data):
            return products, False, False
        batch = data.get("products", []) or []
        products += batch
        pages += 1
        if len(batch) < 250:
            return products, True, False
        since_id = max(int(p.get("id") or 0) for p in batch)
        if pages >= orderbook.ORDER_PAGE_CAP:
            more = await shopify._tool_json(registry, "shopify_list_products",
                                    {"limit": 1, "since_id": since_id, "fields": "id"})
            return products, True, bool(shopify._ok(more) and more.get("products"))


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as sibling.NAME, never a copied name.
from gizmo import orderbook  # noqa: E402
