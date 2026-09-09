"""Shopify actuals in, one tidy daily panel out.

Three adapters produce the same line rows: the admin's orders CSV export, a
JSON dump of orders in the Admin API shape (what the app's own store holds),
and a GraphQL bulk operation against the Admin API for a full history pull.
to_daily_panel then sums them to the bottom grain, variant x segment x day,
and completes the calendar with zeros from each series' first sale, because
lags and rolling windows need every day present, sold or not.
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Mapping, Optional

import numpy as np
import pandas as pd

from .config import Config

log = logging.getLogger("forecast.ingest")

PANEL_COLUMNS = ["date", "variant_id", "sku", "product_id", "product", "category", "segment",
                 "units", "net_sales", "gross_sales", "discount", "price"]
KEY = ["variant_id", "segment"]


def segment_from_tags(tags: Iterable[str], cfg: Config) -> str:
    for t in tags:
        key = str(t).strip().lower()
        for needle, seg in cfg.segment_tags.items():
            if needle in key:
                return seg
    return cfg.default_segment


def category_for(product_type: Optional[str], title: str, cfg: Config) -> str:
    if product_type and str(product_type).strip():
        return str(product_type).strip()
    for pattern, cat in cfg.category_patterns.items():
        if re.search(pattern, title or "", re.I):
            return cat
    return cfg.default_category


def _split_tags(v) -> List[str]:
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    return [t for t in str(v).split(",") if t.strip()]


def _day(v) -> Optional[date]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s[:25] if "T" in s else s[:10]).date()
    except ValueError:
        return pd.Timestamp(s).date()


# ---------------------------------------------------------------- JSON (Admin shape)
def read_orders_json(path, cfg: Config, products: Optional[Mapping[str, dict]] = None) -> pd.DataFrame:
    """Orders as the Admin API returns them (also what the app stores): a list, or
    {"orders": [...]}. Refunds become negative rows on the refund date, which
    is how Shopify's own Net Sales report treats them."""
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    return orders_to_rows(raw.get("orders", raw) if isinstance(raw, dict) else raw, cfg, products)


def orders_to_rows(orders: List[dict], cfg: Config, products: Optional[Mapping[str, dict]] = None) -> pd.DataFrame:
    """The same, from orders already in memory (the nightly service's bulk pull)."""
    products = products or {}
    rows: List[dict] = []
    for o in orders:
        if o.get("test") or o.get("cancelled_at"):
            continue
        if str(o.get("financial_status") or "").lower() in ("voided",):
            continue
        d = _day(o.get("created_at"))
        if d is None:
            continue
        tags = _split_tags(o.get("tags")) + _split_tags((o.get("customer") or {}).get("tags"))
        seg = segment_from_tags(tags, cfg)
        li_by_id: Dict[str, dict] = {}
        for li in o.get("line_items", []):
            qty = float(li.get("quantity") or 0)
            price = float(li.get("price") or 0)
            disc = 0.0
            for al in li.get("discount_allocations") or []:
                disc += float(al.get("amount") or 0)
            if not disc:
                disc = float(li.get("total_discount") or 0)
            pid = str(li.get("product_id") or "")
            vid = str(li.get("variant_id") or li.get("sku") or li.get("title") or "")
            title = li.get("title") or ""
            vtitle = li.get("variant_title") or ""
            pinfo = products.get(pid, {})
            gross = qty * price
            row = {"date": d, "variant_id": vid, "sku": li.get("sku") or "", "product_id": pid or title,
                   "product": title, "category": category_for(pinfo.get("product_type"), title, cfg),
                   "segment": seg, "units": qty, "net_sales": gross - disc, "gross_sales": gross,
                   "discount": disc, "price": price}
            rows.append(row)
            li_by_id[str(li.get("id"))] = row
        for rf in o.get("refunds") or []:
            rd = _day(rf.get("created_at") or rf.get("processed_at")) or d
            for rli in rf.get("refund_line_items") or []:
                src = li_by_id.get(str((rli.get("line_item") or {}).get("id") or rli.get("line_item_id")))
                if not src:
                    continue
                q = float(rli.get("quantity") or 0)
                amt = float(rli.get("subtotal") or (q * src["price"]))
                rows.append({**src, "date": rd, "units": -q, "net_sales": -amt, "gross_sales": -q * src["price"],
                             "discount": 0.0})
    return pd.DataFrame(rows, columns=PANEL_COLUMNS)


# ---------------------------------------------------------------- admin CSV export
def read_shopify_export_csv(path, cfg: Config) -> pd.DataFrame:
    """The admin's Orders export: one row per line item, order fields only on the
    first row of each order. No product ids in this file, so the variant key is
    the SKU (or the line item name) and the product is the name before ' - '."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    order_cols = [c for c in ("Name", "Created at", "Financial Status", "Tags", "Cancelled at") if c in df.columns]
    df[order_cols] = df[order_cols].replace("", np.nan).ffill()
    rows: List[dict] = []
    for _, r in df.iterrows():
        if str(r.get("Cancelled at", "")).strip() not in ("", "nan"):
            continue
        if str(r.get("Financial Status", "")).lower() in ("voided",):
            continue
        d = _day(r.get("Created at"))
        if d is None or not str(r.get("Lineitem name", "")).strip():
            continue
        qty = float(r.get("Lineitem quantity") or 0)
        price = float(r.get("Lineitem price") or 0)
        disc = float(r.get("Lineitem discount") or 0)
        name = str(r.get("Lineitem name", ""))
        product = name.split(" - ")[0].strip()
        sku = str(r.get("Lineitem sku", "")).strip()
        gross = qty * price
        rows.append({"date": d, "variant_id": sku or name, "sku": sku, "product_id": product, "product": product,
                     "category": category_for(None, name, cfg), "segment": segment_from_tags(_split_tags(r.get("Tags")), cfg),
                     "units": qty, "net_sales": gross - disc, "gross_sales": gross, "discount": disc, "price": price})
    return pd.DataFrame(rows, columns=PANEL_COLUMNS)


# ---------------------------------------------------------------- Admin GraphQL bulk pull
# NO refunds here. `Order.refunds` is a LIST and `refundLineItems` is a
# CONNECTION, and a bulk query rejects "a connection field within a list
# field" outright - which is how the first run that reached Shopify died.
# Refunds come from REFUNDED_ORDERS_QUERY below, an ordinary paged query where
# that nesting is allowed. It costs a couple of calls: 31 of the last 3,255
# orders carry a refund.
BULK_ORDERS_QUERY = """
{
  orders(query: "created_at:>=%s") {
    edges { node {
      id name createdAt cancelledAt displayFinancialStatus test tags
      currentTotalPriceSet { shopMoney { amount } }
      customer { tags }
      lineItems { edges { node {
        id sku quantity title variantTitle
        originalUnitPriceSet { shopMoney { amount } }
        totalDiscountSet { shopMoney { amount } }
        discountAllocations { allocatedAmountSet { shopMoney { amount } } }
        variant { id product { id productType } }
      } } }
    } }
  }
}
"""


REFUNDED_ORDERS_QUERY = """
query($q: String!, $after: String) {
  orders(first: 50, after: $after, query: $q) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id
      refunds {
        id createdAt
        refundLineItems(first: 100) {
          nodes { quantity subtotalSet { shopMoney { amount } } lineItem { id } }
        }
      }
    }
  }
}
"""


def fetch_refunds(shop: str, token: str, since: date, api_version: str = "2026-07") -> Dict[str, list]:
    """{order gid: [refund, ...]} for the orders that have any.

    A refund is a negative row on the day it was raised, keyed to the line it
    came off, so the forecast sees a return as demand going away rather than a
    sale that never happened. Bulk cannot carry that shape, and searching for
    the orders that HAVE refunds keeps this to a page or two instead of
    re-reading the whole history."""
    q = (f"created_at:>={since.isoformat()} AND "
         "(financial_status:refunded OR financial_status:partially_refunded)")
    out: Dict[str, list] = {}
    after = None
    pages = 0
    while True:
        data = _gql(shop, token, api_version, REFUNDED_ORDERS_QUERY, {"q": q, "after": after})["orders"]
        for n in data["nodes"]:
            refunds = []
            for rf in n.get("refunds") or []:
                refunds.append({
                    "id": rf.get("id"), "created_at": rf.get("createdAt"),
                    "refund_line_items": [
                        {"quantity": rl.get("quantity"), "subtotal": _money(rl, "subtotalSet"),
                         "line_item": {"id": (rl.get("lineItem") or {}).get("id")}}
                        for rl in ((rf.get("refundLineItems") or {}).get("nodes") or [])],
                })
            if refunds:
                out[n["id"]] = refunds
        pages += 1
        if not data["pageInfo"]["hasNextPage"]:
            break
        after = data["pageInfo"]["endCursor"]
    log.info("refunds: %d orders carry one (%d page%s)", len(out), pages, "" if pages == 1 else "s")
    return out


def shop_host(shop: str) -> str:
    """`projectedimage.myshopify.com` and `projectedimage` both name one shop.
    The app's own server holds the bare handle and builds the domain; this
    package holds the domain and uses it as given. Both spellings arrive here."""
    shop = shop.strip().rstrip("/")
    shop = shop.split("://")[-1]
    return shop if "." in shop else shop + ".myshopify.com"


def access_token(shop: str, token: str = "", client_id: str = "", client_secret: str = "") -> str:
    """The Admin API credential, however this deployment holds one.

    A static token wins when it is set. Otherwise the client id and secret are
    exchanged for a short-lived one through the client_credentials grant, which
    is what Reactor itself does: the app has no static token to lend, so a
    second Shopify app would be a second credential to rotate for no gain. The
    token that comes back carries the app's own scopes, `read_all_orders`
    included, which is what lets a run reach past the sixty days a plain
    `read_orders` token can see."""
    if token:
        return token
    if not (client_id and client_secret):
        raise RuntimeError("no Shopify credential: set SHOPIFY_FORECAST_TOKEN, "
                           "or SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET")
    body = urllib.parse.urlencode({"grant_type": "client_credentials",
                                   "client_id": client_id,
                                   "client_secret": client_secret}).encode()
    req = urllib.request.Request(
        f"https://{shop_host(shop)}/admin/oauth/access_token", data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"the client_credentials grant was refused ({e.code}): "
                           "check SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET") from None
    tok = data.get("access_token")
    if not tok:
        raise RuntimeError("the client_credentials grant returned no access_token")
    return tok


def _gql(shop: str, token: str, api_version: str, query: str, variables: Optional[dict] = None) -> dict:
    req = urllib.request.Request(
        f"https://{shop_host(shop)}/admin/api/{api_version}/graphql.json",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Content-Type": "application/json", "X-Shopify-Access-Token": token})
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read())
    if body.get("errors"):
        raise RuntimeError(str(body["errors"]))
    return body["data"]


def run_bulk_orders(shop: str, token: str, since: date, api_version: str = "2026-07",
                    poll_seconds: int = 5, timeout_s: int = 1800) -> List[dict]:
    """Full history through a bulk operation (the only sane way past a few
    thousand orders). Returns orders in the Admin shape read_orders_json accepts.
    Network code: exercised against a store, not in the unit tests."""
    mutation = """mutation($q: String!) { bulkOperationRunQuery(query: $q) {
        bulkOperation { id status } userErrors { field message } } }"""
    started = _gql(shop, token, api_version, mutation, {"q": BULK_ORDERS_QUERY % since.isoformat()})
    errs = started["bulkOperationRunQuery"]["userErrors"]
    if errs:
        raise RuntimeError(str(errs))
    op_id = started["bulkOperationRunQuery"]["bulkOperation"]["id"]
    log.info("bulk operation %s started, polling every %ss", op_id, poll_seconds)
    # BY ID, not `currentBulkOperation`. Shopify has allowed five concurrent
    # bulk queries per app since 2026-01, and that field is both deprecated and
    # ambiguous once more than one exists: a run whose container was killed
    # leaves its operation going, and the next run polling "current" can watch
    # the wrong one and download a different date range believing it is its own.
    watch = """query($id: ID!) { node(id: $id) { ... on BulkOperation {
        status url errorCode objectCount } } }"""
    url = None
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        cur = _gql(shop, token, api_version, watch, {"id": op_id})["node"]
        if cur["status"] == "COMPLETED":
            log.info("bulk operation completed: %s objects", cur.get("objectCount"))
            url = cur["url"]; break
        if cur["status"] in ("FAILED", "CANCELED", "EXPIRED"):
            raise RuntimeError(f"bulk operation {cur['status']}: {cur.get('errorCode')}")
        # Silence for up to half an hour is indistinguishable from a hang, and
        # that is exactly what it looked like the first time it was run.
        log.info("bulk operation %s: %s objects so far", cur["status"], cur.get("objectCount") or 0)
        time.sleep(poll_seconds)
    if not url:
        raise TimeoutError(f"bulk operation did not finish within {timeout_s}s")
    with urllib.request.urlopen(url, timeout=300) as resp:
        lines = [json.loads(l) for l in resp.read().decode().splitlines() if l.strip()]
    orders = _assemble_bulk(lines)
    log.info("assembled %d orders", len(orders))
    # The half the bulk query is not allowed to carry.
    refunds = fetch_refunds(shop, token, since, api_version)
    for o in orders:
        o["refunds"] = refunds.get(o["id"], [])
    return orders


PRODUCTS_QUERY = """
query($after: String) {
  products(first: 250, after: $after) {
    edges { node { id productType } }
    pageInfo { hasNextPage endCursor }
  }
}
"""


def fetch_products(shop: str, token: str, api_version: str = "2026-07") -> Dict[str, dict]:
    """{product gid: {"product_type": ...}} for the category, paged 250 at a time."""
    out: Dict[str, dict] = {}
    after = None
    while True:
        data = _gql(shop, token, api_version, PRODUCTS_QUERY, {"after": after})["products"]
        for e in data["edges"]:
            n = e["node"]
            out[n["id"]] = {"product_type": n.get("productType") or ""}
        if not data["pageInfo"]["hasNextPage"]:
            return out
        after = data["pageInfo"]["endCursor"]


def _money(node, key) -> float:
    try:
        return float(((node.get(key) or {}).get("shopMoney") or {}).get("amount") or 0)
    except (TypeError, ValueError):
        return 0.0


def _assemble_bulk(lines: List[dict]) -> List[dict]:
    """JSONL from a bulk operation is flat: children carry __parentId. Rebuild
    the nested orders in the shape the JSON adapter reads."""
    orders: Dict[str, dict] = {}
    items: Dict[str, dict] = {}
    for n in lines:
        gid = n.get("id", "")
        parent = n.get("__parentId")
        if gid.startswith("gid://shopify/Order/") and not parent:
            orders[gid] = {"id": gid, "name": n.get("name"), "created_at": n.get("createdAt"),
                           "cancelled_at": n.get("cancelledAt"), "financial_status": (n.get("displayFinancialStatus") or "").lower(),
                           "test": n.get("test"), "tags": n.get("tags") or [], "customer": n.get("customer") or {},
                           # What the customer actually pays: line items less
                           # discounts, plus carriage and VAT. The cash flow plan
                           # is written in these terms ("Gross Sales" feeding
                           # "Total Cash In"), and so is Shopify's own forecast.
                           # `current` rather than the plain total, so a line an
                           # edit removed is not still being counted.
                           "order_total": _money(n, "currentTotalPriceSet"),
                           "line_items": [], "refunds": []}
        elif gid.startswith("gid://shopify/LineItem/") and parent in orders:
            v = n.get("variant") or {}
            p = v.get("product") or {}
            item = {"id": gid, "sku": n.get("sku"), "quantity": n.get("quantity"), "title": n.get("title"),
                    "variant_title": n.get("variantTitle"), "price": _money(n, "originalUnitPriceSet"),
                    "total_discount": _money(n, "totalDiscountSet"),
                    # `totalDiscountSet` is the LINE's own discount and nothing
                    # else. A discount CODE is an ORDER-level discount that
                    # Shopify spreads across the lines, and it lands ONLY in
                    # discountAllocations: on #104335 the line reads a total
                    # discount of 0.00 beside an allocation of 49.50. The bulk
                    # query never asked for them and this assembler had nowhere
                    # to read them from, so the panel counted the discount
                    # as revenue and the model learned to forecast GROSS sales.
                    # Across the last 19 months that is a tenth of the business:
                    # discounts of 61,694 against gross of 588,292.
                    "discount_allocations": [{"amount": _money(a, "allocatedAmountSet")}
                                             for a in (n.get("discountAllocations") or [])],
                    "variant_id": v.get("id"), "product_id": p.get("id"),
                    "product_type": p.get("productType")}
            orders[parent]["line_items"].append(item); items[gid] = item
    # No Refund rows arrive here: the bulk query cannot carry them (see
    # BULK_ORDERS_QUERY) and `fetch_refunds` fills them in afterwards.
    return list(orders.values())



def monthly_cash(orders: List[dict], as_of: date) -> "pd.Series":
    """Cash in by calendar month, COMPLETE months only.

    The month in progress is dropped on purpose. Half a September looks like a
    collapse to any model that is handed it, and every one of them would then
    forecast the rest of the year down from that. The panel's own target is
    line-item NET sales; this is the order total, because it is what the plan
    and Shopify's forecast are both denominated in."""
    rows = []
    for o in orders:
        if o.get("test") or o.get("cancelled_at"):
            continue
        if str(o.get("financial_status") or "").lower() in ("voided",):
            continue
        d = _day(o.get("created_at"))
        if d is None:
            continue
        rows.append((pd.Period(d, freq="M"), float(o.get("order_total") or 0)))
    if not rows:
        return pd.Series(dtype=float)
    ser = pd.DataFrame(rows, columns=["month", "total"]).groupby("month")["total"].sum().sort_index()
    return ser[ser.index < pd.Period(as_of, freq="M")]



def daily_cash(orders: List[dict], as_of: date) -> "pd.Series":
    """Cash in by day, up to and including as_of.

    The month-to-date figure the variance table shows comes from here, so it
    has to be the same money as the forecast it is compared with: the order
    total, not the panel's line-item net."""
    rows = []
    for o in orders:
        if o.get("test") or o.get("cancelled_at"):
            continue
        if str(o.get("financial_status") or "").lower() in ("voided",):
            continue
        d = _day(o.get("created_at"))
        if d is None or d > as_of:
            continue
        rows.append((pd.Timestamp(d), float(o.get("order_total") or 0)))
    if not rows:
        return pd.Series(dtype=float)
    ser = pd.DataFrame(rows, columns=["date", "total"]).groupby("date")["total"].sum().sort_index()
    full = pd.date_range(ser.index.min(), pd.Timestamp(as_of), freq="D")
    return ser.reindex(full, fill_value=0.0)


# ---------------------------------------------------------------- the panel
def to_daily_panel(rows: pd.DataFrame, as_of: date, start: Optional[date] = None) -> pd.DataFrame:
    """Sum line rows to variant x segment x day and complete the calendar with
    zeros from each series' first sale to as_of. Price is the last known unit
    price, carried forward, so a day with no sale still knows what it would
    have sold at."""
    if rows.empty:
        return pd.DataFrame(columns=PANEL_COLUMNS)
    r = rows.copy()
    r["date"] = pd.to_datetime(r["date"]).dt.normalize()
    r = r[r["date"] <= pd.Timestamp(as_of)]
    if start is not None:
        r = r[r["date"] >= pd.Timestamp(start)]
    agg = (r.groupby(["date"] + KEY, as_index=False)
             .agg(sku=("sku", "first"), product_id=("product_id", "first"), product=("product", "first"),
                  category=("category", "first"), units=("units", "sum"), net_sales=("net_sales", "sum"),
                  gross_sales=("gross_sales", "sum"), discount=("discount", "sum"),
                  price=("price", lambda s: float(np.nanmedian([x for x in s if x > 0])) if any(x > 0 for x in s) else np.nan)))
    end = pd.Timestamp(as_of)
    meta = agg.groupby(KEY, as_index=False).agg(sku=("sku", "first"), product_id=("product_id", "first"),
                                                product=("product", "first"), category=("category", "first"),
                                                first=("date", "min"))
    frames = []
    for _, m in meta.iterrows():
        days = pd.date_range(m["first"], end, freq="D")
        frames.append(pd.DataFrame({"date": days, "variant_id": m["variant_id"], "segment": m["segment"]}))
    grid = pd.concat(frames, ignore_index=True)
    panel = grid.merge(agg, on=["date"] + KEY, how="left")
    for c in ("sku", "product_id", "product", "category"):
        panel[c] = panel.groupby(KEY)[c].transform(lambda s: s.ffill().bfill())
    for c in ("units", "net_sales", "gross_sales", "discount"):
        panel[c] = panel[c].fillna(0.0)
    panel["price"] = panel.groupby("variant_id")["price"].transform(lambda s: s.ffill().bfill())
    panel["price"] = panel["price"].fillna(panel["price"].median() if panel["price"].notna().any() else 0.0)
    return panel.sort_values(KEY + ["date"]).reset_index(drop=True)[PANEL_COLUMNS]


def series_keys(panel: pd.DataFrame) -> pd.DataFrame:
    """One row per bottom series with its parents: what the hierarchy is built from."""
    return (panel.groupby(KEY, as_index=False)
                 .agg(product_id=("product_id", "first"), product=("product", "first"), category=("category", "first"),
                      sku=("sku", "first"), first_date=("date", "min")))
