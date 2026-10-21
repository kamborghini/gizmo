"""The Products tab: the whole catalogue read page by page, and the product
list with its units and revenue by month, stock and facets. Moved out of
copilot.py (stage 4 of the 14 October audit), where it sat in the stock
bridge's section without reading anything of the bridge's; its routes, the
list and a product's page, are in gizmo/routes/products.py. Read as
`catalog.NAME` (`products` is a local name in several functions).
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from gizmo.config import _env_num
from gizmo import shopify

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


LOW_STOCK_THRESHOLD = _env_num(int, os.environ.get("LOW_STOCK_THRESHOLD", "5"), "5", "LOW_STOCK_THRESHOLD")
PRODUCT_TREND_MONTHS = _env_num(int, os.environ.get("PRODUCT_TREND_MONTHS", "12"), "12", "PRODUCT_TREND_MONTHS")


# ---------------------------------------------------------------------------
# Every product in the catalogue, paged (the overview, the SEO audit and the
# loan-unit picker read it too), and the Products tab's list.
# ---------------------------------------------------------------------------


async def _all_products(registry: dict, fields: str) -> tuple:
    """Every product in the catalogue, paged by since_id: (products, ok, truncated).

    ok is False when any page failed, and what came before it is returned
    only so a caller can say how far it got. truncated is True only when the
    page cap stopped the read AND a further product exists. Four callers read
    a single page of 250 and no more: the Products tab, the SEO audit, the
    Overview's low-stock count and the loan-unit picker."""
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


async def run_products_list(registry: dict, months_window: Optional[int] = None) -> dict:
    """Rich product dataset for the Products tab: catalog fields + per-month units &
    revenue buckets (so the UI can filter, sort and compare any period entirely
    client-side) + facet lists. Order history is paginated up to `months_window`
    (default PRODUCT_TREND_MONTHS, capped at 24) and bounded by ORDER_PAGE_CAP."""
    months_window = min(max(int(months_window or PRODUCT_TREND_MONTHS), 1), 24)
    months = orderbook._month_axis(months_window)
    fields = ("id,title,handle,status,image,variants,product_type,vendor,tags,"
              "created_at,updated_at,published_at")
    # Paged, and a failure is said rather than shown as an empty catalogue:
    # one unchecked page read a throttled answer as a store with no products,
    # and a store past 250 lost the rest without a word.
    products, ok, truncated = await _all_products(registry, fields)
    if not ok:
        return {"error": "Shopify did not answer the product list, so nothing is shown rather "
                         "than an empty or partial catalogue. Try again in a moment."}
    shop = await shopify._tool_json(registry, "shopify_get_shop", {})
    currency = shop.get("currency", "")

    orders = [o for o in await orderbook._orders_snapshot(registry, days=len(months) * 31) if orderbook._order_counts(o)]
    bucket = orderbook._orders_product_monthly(orders, months)
    cutoff28 = datetime.now(timezone.utc) - timedelta(days=28)
    units28: dict = {}
    rev28: dict = {}
    for o in orders:
        try:
            created = datetime.fromisoformat((o.get("created_at") or "").replace("Z", "+00:00"))
        except Exception:
            created = None
        if not (created and created >= cutoff28):
            continue
        for li in o.get("line_items", []):
            pid = li.get("product_id")
            if not pid:
                continue
            q = li.get("quantity") or 0
            units28[pid] = units28.get(pid, 0) + q
            rev28[pid] = rev28.get(pid, 0.0) + float(li.get("price") or 0) * q

    vendors: set = set()
    types: set = set()
    out = []
    for p in products:
        pid = p.get("id")
        img = p.get("image") or {}
        variants = p.get("variants") or []
        price = None
        for v in variants:
            try:
                price = float(v.get("price"))
                break
            except (TypeError, ValueError):
                continue
        inv_vals = [v.get("inventory_quantity") for v in variants if isinstance(v.get("inventory_quantity"), int)]
        inventory = sum(inv_vals) if inv_vals else None
        stock = ("untracked" if inventory is None else
                 "out" if inventory <= 0 else
                 "low" if inventory <= LOW_STOCK_THRESHOLD else "in")
        tags = p.get("tags")
        tags = [t.strip() for t in tags.split(",") if t.strip()] if isinstance(tags, str) else (tags or [])
        b = bucket.get(pid, {"units": {}, "revenue": {}})
        monthly = {mk: {"units": b["units"].get(mk, 0), "revenue": round(b["revenue"].get(mk, 0.0), 2)}
                   for mk in months if b["units"].get(mk) or b["revenue"].get(mk)}
        if p.get("vendor"):
            vendors.add(p["vendor"])
        if p.get("product_type"):
            types.add(p["product_type"])
        out.append({
            "id": pid, "title": p.get("title"), "handle": p.get("handle"), "status": p.get("status"),
            "image": img.get("src") if isinstance(img, dict) else None,
            "price": price, "vendor": p.get("vendor") or "", "product_type": p.get("product_type") or "",
            "tags": tags, "created_at": p.get("created_at"), "updated_at": p.get("updated_at"),
            "published_at": p.get("published_at"), "inventory": inventory, "stock_status": stock,
            "units_28d": units28.get(pid, 0), "revenue_28d": round(rev28.get(pid, 0.0), 2),
            "monthly": monthly,
        })
    out.sort(key=lambda x: (x["units_28d"], x["revenue_28d"]), reverse=True)  # best sellers first by default
    # Every product read, not the best-selling 250: the page searches and
    # filters on what it is sent, so a product past the 250th could not be
    # found even by name. `truncated` says when the page cap stopped the read.
    return {"currency": currency, "months": months,
            "vendors": sorted(vendors), "product_types": sorted(types),
            "products": out, "truncated": truncated}


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as core.NAME and sibling.NAME, never a copied name.
from gizmo import orderbook  # noqa: E402
import copilot as core  # noqa: E402
