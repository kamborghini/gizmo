"""The order book's routes: an order's edit and Shopify's orders webhook. Moved
from add_routes (stage 4 of the 14 October audit) where the first stood;
their paths are literal, so no request changes hands.
"""
import logging
import json
import time
import hmac
import base64
import hashlib
from starlette.requests import Request
from starlette.responses import PlainTextResponse

import copilot as core
from gizmo import activity
from gizmo import gate
from gizmo import orderbook
from gizmo import crm as salesdesk
from gizmo import team
from gizmo import shopify

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


def register(mcp, registry):
    """Add the order book's routes to the app."""

    @mcp.custom_route("/webhooks/orders", methods=["POST"])
    async def order_webhook(request: Request):
        """Shopify's order events. The HMAC is the whole authentication: the
        body is signed with the app secret, so a valid signature can only come
        from Shopify. No session token (Shopify has none) and no rate limiter
        (a burst of genuine orders must never be answered 429, because repeated
        failures make Shopify silently delete the subscription)."""
        if not core.SHOPIFY_API_SECRET:
            return PlainTextResponse("Unauthorized", status_code=401)
        # Streamed with a hard cap, NOT request.body(): the signature can only be
        # checked after the body is read, so this read happens for anyone, and a
        # chunked upload with no Content-Length would otherwise buffer without
        # limit into memory on an endpoint that deliberately has no rate limiter.
        total, chunks = 0, []
        try:
            async for chunk in request.stream():
                total += len(chunk)
                if total > orderbook.WEBHOOK_MAX_BYTES:
                    return PlainTextResponse("Too large", status_code=413)
                chunks.append(chunk)
        except Exception:
            return PlainTextResponse("Bad request", status_code=400)
        raw = b"".join(chunks)
        sent = request.headers.get("x-shopify-hmac-sha256", "")
        want = base64.b64encode(hmac.new(core.SHOPIFY_API_SECRET.encode("utf-8"),
                                         raw, hashlib.sha256).digest()).decode("ascii")
        if not sent or not hmac.compare_digest(want, sent):
            return PlainTextResponse("Unauthorized", status_code=401)
        # Signed, but for the wrong store: refuse rather than act on it.
        shop = str(request.headers.get("x-shopify-shop-domain") or "")
        if core.SHOPIFY_STORE and not shop.lower().startswith(core.SHOPIFY_STORE.split(".")[0].lower() + "."):
            return PlainTextResponse("Unauthorized", status_code=401)
        # Signed by us, for us, but this door is the ORDERS door. A privacy or
        # app topic delivered here would be acknowledged 200 and dropped, which
        # is how a redaction request goes missing: Shopify counts a 200 as
        # handled. Say plainly it was sent to the wrong endpoint.
        topic = str(request.headers.get("x-shopify-topic") or "")
        if topic and not topic.startswith("orders/"):
            logger.warning("webhook: %s was delivered to the orders endpoint", topic)
            return PlainTextResponse("Wrong endpoint for this topic", status_code=422)
        delivery = str(request.headers.get("x-shopify-webhook-id") or "")
        if delivery and not orderbook._webhook_note_delivery(delivery):
            return PlainTextResponse("ok", status_code=200)   # a redelivery, already handled
        # The order this event is about is read again from Shopify on the next
        # load; the payload names it and is never used as state. One that
        # cannot be read retires every snapshot, as every event used to.
        try:
            _event_order = json.loads(raw).get("id")
            if not _event_order:
                raise ValueError("no order id")
            orderbook._orders_changed([_event_order])
        except Exception:
            orderbook._bust_orders()
        orderbook._webhook_state["last_at"] = time.time()
        orderbook._webhook_state["last_topic"] = str(request.headers.get("x-shopify-topic") or "")
        orderbook._webhook_state["version"] = str(request.headers.get("x-shopify-api-version") or "")[:16]
        orderbook._webhook_state["count"] += 1
        try:
            # Deferred, so the whole-store scan never stalls the receiver (a
            # slow ack makes Shopify retry and eventually delete the
            # subscription) - but deferred onto the LOOP, not a thread, so it
            # cannot interleave with a CRM route mid-write.
            salesdesk._crm_link_order_soon(raw.decode("utf-8", "replace"))
        except Exception:
            pass   # the webhook's ack must never hinge on enrichment
        return PlainTextResponse("ok", status_code=200)

    @mcp.custom_route("/api/order/edit", methods=["POST"])
    async def order_edit_route(request: Request):
        """Read or change the delivery address and contact details on a placed
        order.

        Two things are deliberately NOT editable here.

        Tags: the queues are tag-driven and Shopify's order update REPLACES the
        whole tag list rather than merging it, so one save from a panel holding a
        stale list would silently strip IP, Complete or "Purchase order unpaid" -
        the last of which drops the order out of the chase list entirely, with no
        bucket anywhere to catch it. Tag changes keep going through the
        read-merge-write path under the same per-order lock.

        The note: the order object this panel comes from has had the proposal URL
        stripped out of its note and the remainder cut to 500 characters, so
        writing it back would delete the artwork proof link from Shopify for good.

        Admin and up. The labels tab is the tab part-time workshop staff are given
        so they can print and dispatch, and a new account gets every tab until
        somebody sets its permissions - so the tab alone is not a gate for
        rewriting where a paid order ships. This matches the other writes on this
        tab that change a shared record of truth (the size list, shipping setup).
        """
        err, _body, _who = await gate._guard(request, body=False)
        if err:
            return err
        uid = team._live_uid(request)
        if team._team_level(uid) < team.ROLE_LEVELS["admin"]:
            return gate._json({"error": "Only an admin can change an order."}, 403)
        body = await gate._read_json_capped(request)
        if body is None:
            return gate._json({"error": "Request too large."}, 413)
        oid = str(body.get("order_id") or "").strip()
        if not oid.isdigit():
            return gate._json({"error": "Which order?"}, 400)
        if str(body.get("op") or "") == "read":
            data, why = await orderbook._order_editable(registry, int(oid))
            if data is None:
                return gate._json({"error": why}, 400)
            return gate._json(data)
        done, why, changed, name, warn = await orderbook._edit_order(registry, int(oid), body)
        if not done:
            return gate._json({"error": why or "The order couldn't be changed."}, 400)
        if changed:
            # The field NAMES, not the values: the ledger is a board the whole
            # team reads and a customer's address does not belong on it. The
            # order name comes from the order the route actually read, never
            # from the request body, so a ledger line cannot name one order for
            # a write that landed on another.
            activity._track(_who, "orders", "edited order " + (name or oid), ", ".join(changed))
        return gate._json({"ok": True, "changed": changed, "warnings": warn})

    @mcp.custom_route("/api/customer-history", methods=["POST"])
    async def customer_history_route(request: Request):
        # How many times this label's customer has ordered before. Read-only.
        err, body, _who = await gate._guard(request)
        if err:
            return err
        try:
            cid = int(body.get("customer_id") or 0)
        except (TypeError, ValueError, OverflowError):
            cid = 0
        if not cid:
            return gate._json({"error": "No customer id given."}, 400)
        try:
            data = await shopify._tool_json(registry, "shopify_get_customer_orders",
                                    {"customer_id": cid, "limit": 50, "status": "any"})
            if not shopify._ok(data):
                return gate._json({"error": "Couldn't read that customer's orders."}, 502)
            orders = sorted((data.get("orders") or []), key=lambda o: str(o.get("created_at") or ""), reverse=True)
            return gate._json({"count": len(orders),
                          "recent": [{"name": o.get("name"), "created_at": o.get("created_at"),
                                      "admin_url": orderbook._admin_order_url(o.get("id"))}
                                     for o in orders[:3]]})
        except Exception:
            logger.exception("Customer history failed")
            return gate._json({"error": "Couldn't read customer history."}, 500)
