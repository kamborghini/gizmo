"""Production's routes: the label list, the queue, missing production, label
coverage, and the production state. Moved from add_routes (stage 4 of the 14
October audit) where the first stood; their paths are literal, so no request
changes hands. The printed-label routes stay in add_routes, their bytes
pinned.
"""
import logging
import re
from starlette.requests import Request
from gizmo import store as jsonstore

import copilot as core
from gizmo import activity
from gizmo import dispatch as desk
from gizmo import gate
from gizmo import mail
from gizmo import orderbook
from gizmo import production

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


def register(mcp, registry):
    """Add production's routes to the app."""

    @mcp.custom_route("/api/production-labels", methods=["POST"])
    async def production_labels_route(request: Request):
        # Orders carrying the production tag, shaped for printing. Shopify read, no AI.
        err, body, _who = await gate._guard(request)
        if err:
            return err
        tag = str(body.get("tag") or "").strip()[:60] or None
        try:
            days = int(body.get("days") or 0) or None
        except (TypeError, ValueError, OverflowError):
            days = None
        try:
            order_id = int(body.get("order_id") or 0) or None
        except (TypeError, ValueError, OverflowError):
            order_id = None
        # Refresh means the merchant wants the truth, usually because they just
        # edited something in the Shopify admin: skip the order snapshot.
        fresh = bool(body.get("fresh"))
        try:
            return gate._json(await production.run_production_labels(registry, tag=tag, days=days,
                                                     order_id=order_id, fresh=fresh))
        except Exception:
            logger.exception("Production labels failed")
            return gate._json({"error": "Couldn't load production orders. Check the server logs."}, 500)

    @mcp.custom_route("/api/production-state", methods=["POST"])
    async def production_state_route(request: Request):
        # Printed and made stamps per order. Local JSON on the volume, no AI.
        err, body, _who = await gate._guard(request)
        if err:
            return err
        op = str(body.get("op") or "")
        try:
            if op == "printed":
                ids = [int(i) for i in (body.get("ids") or []) if str(i).strip().isdigit()][:100]
                stamped = production._mark_printed(ids) if ids else True
                if ids and stamped:
                    activity._track(_who, "production", "printed labels",
                           str(len(ids)) + (" order" if len(ids) == 1 else " orders"))
                # Printing moves the order into production: Unprocessed -> IP.
                # That IS a release, so an account order's 30-day clock starts
                # here too - this is the ordinary way an order reaches the
                # workbench, and it used to be the path that forgot.
                notes, terms, terms_notes, terms_bad = [], [], [], False
                # Inline for a normal run; the tail is paced in the background.
                # Each order is a tag GET+PUT plus up to three GraphQL calls,
                # so a 60-order batch done inline outlives the browser's patience.
                head, tail = ids[:mail.RELEASE_INLINE_MAX], ids[mail.RELEASE_INLINE_MAX:]
                for oid in head:
                    seen: dict = {}
                    okd, note, released = await production._release_tags(registry, oid, seen)
                    if not okd and note:
                        notes.append(note)
                        continue
                    if not released:
                        continue      # a reprint of a made or shipped order is not a release
                    tn = await production._net30_on_release(registry, oid, order=seen.get("order"))
                    if tn["account"]:
                        # Per ORDER. Flattened to one boolean and the first
                        # three notes, a batch could show a red toast whose
                        # text was three success sentences while the order that
                        # actually failed was never named.
                        terms.append({"order": oid, "ok": tn["ok"], "note": tn["note"]})
                    if tn["note"]:
                        terms_notes.append(tn["note"])
                    if tn["account"] and not tn["ok"]:
                        terms_bad = True
                queued = len(tail) if tail and core._spawn_bg(production._release_bg(registry, tail)) else 0
                if tail and not queued:
                    # No loop to defer to (never true in a route, but say so
                    # rather than promise a pass that never started).
                    logger.error("release tail of %d orders could not be scheduled", len(tail))
                # The summary keeps the FAILURES, never a truncation that
                # happens to be all successes.
                bad_notes = [t["note"] for t in terms if not t["ok"]]
                return gate._json({"ok": True, "state": {str(i): production._load_prod_state().get(str(i), {}) for i in ids},
                              "terms": terms,
                              "terms_note": ("  ".join((bad_notes or terms_notes)[:3])
                                             if (bad_notes or terms_notes) else ""),
                              "terms_ok": not terms_bad,
                              "tag_note": (notes[0] if notes else ""),
                              "queued": queued,
                              "state_note": ("" if stamped else "Printed stamps couldn't be saved; "
                                             "the list may show these as unprinted after a reload.")})
            if op == "unprinted":
                # Undo for a print that never happened (wrong stock loaded, dialog
                # cancelled). Clears the stamp and puts the order back to Unprocessed.
                ids = [int(i) for i in (body.get("ids") or []) if str(i).strip().isdigit()][:60]
                if not ids:
                    return gate._json({"error": "No orders given."}, 400)
                state = production._load_prod_state()
                shipped_ids = desk._load_dispatch()
                past = {oid for oid in ids
                        if (state.get(str(oid)) or {}).get("made_at")
                        or (shipped_ids.get(str(oid)) or {}).get("fulfilled")}
                for oid in ids:
                    entry = state.get(str(oid))
                    if entry and oid not in past:
                        entry.pop("printed_at", None)
                        if not entry:
                            state.pop(str(oid), None)
                try:
                    production._write_prod_state(state)
                except production.ProdStateUnwritable:
                    return gate._json({"error": "The print stamps could not be cleared. Check the "
                                           "data volume in Settings, Connections."}, 503)
                activity._track(_who, "production", "undid a print",
                       str(len(ids)) + (" order" if len(ids) == 1 else " orders"))
                notes = []
                for oid in ids:
                    # A made or shipped order's print was a reprint, not a
                    # release, so there is no move to undo: sending it back to
                    # Unprocessed put a made order on course for To make again.
                    if oid in past:
                        continue
                    okd, note = await orderbook._sync_order_tags(registry, oid,
                                                       add=[orderbook.UNPROCESSED_TAG], remove=[production.PRODUCTION_TAG],
                                                       unless=(orderbook.MADE_TAG, desk.DISPATCHED_TAG,
                                                               *desk.LEGACY_DISPATCHED_TAGS))
                    if not okd and note:
                        notes.append(note)
                return gate._json({"ok": True,
                              "state": {str(i): production._load_prod_state().get(str(i), {}) for i in ids},
                              # Made or shipped: its print was a reprint, left as it is.
                              "kept": sorted(str(i) for i in past),
                              "tag_note": (notes[0] if notes else "")})
            if op == "made":
                oid = int(body.get("id") or 0)
                if not oid:
                    return gate._json({"error": "No order id given."}, 400)
                on = bool(body.get("on", True))
                # BEFORE anything is fulfilled at Shopify or booked at the stock
                # app: if the stamp cannot be saved, stop here rather than doing
                # the irreversible half and reporting success.
                try:
                    state = production._mark_made(oid, on)
                except production.ProdStateUnwritable:
                    logger.exception("made: production state unwritable for %s", oid)
                    return gate._json({"error": "The made stamp could not be saved, so nothing "
                                           "was fulfilled or booked. Check the data volume "
                                           "in Settings, Connections, then try again."}, 503)
                nm = re.sub(r"[^#\w-]", "", str(body.get("name") or ""))[:20] or f"order {oid}"
                activity._track(_who, "production", "marked made" if on else "un-marked made", nm)
                # Made is the moment an order actually ships: if a courier label is
                # already booked, THIS is what fulfils Shopify and emails tracking.
                ship_note, fulfilled, notified, ship_reason = "", False, False, ""
                if on:
                    # Under the dispatch lock, the same one the booking path
                    # holds: _fulfill_if_ready reads the record, then awaits
                    # three Shopify calls before writing it back, so a booking
                    # and a Mark-made racing here both saw "not fulfilled" and
                    # both fulfilled - two fulfilments, two tracking emails.
                    # (The lock is taken HERE, not inside the helper: the
                    # booking path already holds it and asyncio locks are not
                    # reentrant.)
                    async with orderbook._dispatch_lock(oid):
                        ready = await orderbook._fulfill_if_ready(
                            registry, oid, ack_address=bool(body.get("ack_address")))
                    ship_reason = str(ready.get("reason") or "")
                    fulfilled, notified = ready["fulfilled"], ready["notified"]
                    if fulfilled:
                        # _fulfill_if_ready already moved the tags to Dispatched - unless
                        # that write failed, which is exactly what must be reported.
                        okd, note = (not ready["tag_note"]), ready["tag_note"]
                        if ship_reason == "already_fulfilled":
                            # Nothing was created here, so nothing was emailed
                            # from here: the toast used to say the customer was.
                            ship_note = ("Shopify already had this order fulfilled, so no new "
                                         "fulfilment or tracking email went from here; it is "
                                         "filed as complete.")
                        else:
                            ship_note = ("Fulfilled in Shopify with the booked tracking"
                                         + (" and the customer was emailed." if notified else "."))
                        if not okd:
                            ship_note += (" The Dispatched tag did not save, so this order will "
                                          "keep showing in To make. Add the tag in Shopify.")
                    elif ready.get("reason") == "unknown":
                        # It may have shipped: its tags are left as the dispatch
                        # step set them, and the note says to look in Shopify.
                        okd, note = True, ""
                        ship_note = ready["detail"]
                    else:
                        okd, note = await orderbook._sync_order_tags(registry, oid, add=[orderbook.MADE_TAG],
                                                           remove=[production.PRODUCTION_TAG])
                        if ready["reason"] not in ("no_label",):
                            ship_note = ready["detail"]
                else:
                    ship_note = await orderbook._unfulfill_dispatch(registry, oid)
                    okd, note = await orderbook._sync_order_tags(registry, oid, add=[production.PRODUCTION_TAG],
                                                       remove=[orderbook.MADE_TAG, desk.DISPATCHED_TAG, *desk.LEGACY_DISPATCHED_TAGS])
                # The shelf's ledger: made books the glass at the stock app,
                # un-made returns it. Local state is already saved, so a bridge
                # failure only queues a retry, never blocks the workbench.
                stock_note = await core._zeta_push(registry, oid, "book" if on else "reverse")
                return gate._json({"ok": True, "state": {str(oid): state.get(str(oid), {})},
                              "dispatch": {str(oid): desk._load_dispatch().get(str(oid), {})},
                              "fulfilled": fulfilled, "notified": notified,
                              "ship_note": ship_note, "stock_note": stock_note,
                              # The one reason the workbench can answer: the
                              # address moved after the label was booked, and
                              # only a human knows where the parcel really went.
                              "needs_ack": (ship_reason == "address_changed"),
                              "tag_note": ("" if okd else note)})
            return gate._json({"error": "Unknown op."}, 400)
        except Exception:
            logger.exception("Production state update failed")
            jsonstore._forget_store(production.PRODUCTION_STATE_PATH)   # a half-made change must not be served
            return gate._json({"error": "Couldn't update production state."}, 500)

    @mcp.custom_route("/api/production-labels/queue", methods=["POST"])
    async def labels_queue_route(request: Request):
        # One-click intake from the missed-orders strip: tag the order into
        # production through the same guarded writer the print path uses.
        err, body, _who = await gate._guard(request)
        if err:
            return err
        try:
            oid = int(body.get("order_id") or 0)
        except (TypeError, ValueError, OverflowError):
            oid = 0
        if not oid:
            return gate._json({"error": "No order id given."}, 400)
        try:
            # The one guarded release: an order already made or shipped stays
            # where it is. An Undo on a made order's reprint used to leave it
            # tagged Unprocessed, and this button then put it back in To make.
            seen: dict = {}
            okd, note, released = await production._release_tags(registry, oid, seen)
            # This button sits on the missed-orders strip, and pressing it
            # says that row may be wrong: an order cancelled or tagged in
            # Shopify's admin before the app heard of it is read here, moves
            # nothing and writes nothing, so no change was recorded and the
            # kept strip would bring the row straight back. Saying the order
            # changed also stops a strip scan already reading Shopify from
            # keeping what it saw, and has the queues read it again.
            production._missing_cache.clear()
            orderbook._orders_changed([oid])
            if not okd:
                return gate._json({"error": note or "Couldn't tag the order."}, 502)
            nm = re.sub(r"[^#\w-]", "", str(body.get("name") or ""))[:20] or f"order {oid}"
            if not released:
                return gate._json({"ok": True, "released": False, "po_unpaid": False, "terms_note": "",
                              "terms_ok": True,
                              "note": f"{nm} is already made, so it stays where it is."})
            activity._track(_who, "production", "released to make", nm)
            # Best-effort and SAID OUT LOUD either way: the release is the
            # primary action and must not fail with it, but a purchase order
            # silently missing its payment terms is an unpaid invoice nobody
            # chases. Shared with the print path so every release behaves alike.
            terms = await production._net30_on_release(registry, oid, order=seen.get("order"))
            if terms["account"] and terms["ok"]:
                activity._track(_who, "production", "put an account order on 30-day terms", nm)
            return gate._json({"ok": True, "po_unpaid": terms["account"],
                          "terms_note": terms["note"], "terms_ok": terms["ok"]})
        except Exception:
            logger.exception("Queue tagging failed")
            return gate._json({"error": "Couldn't tag the order."}, 500)

    @mcp.custom_route("/api/production-labels/missing", methods=["POST"])
    async def labels_missing_route(request: Request):
        # Paid gobo orders that never got the production tag. Shopify read, no AI.
        err, body, _who = await gate._guard(request)
        if err:
            return err
        try:
            res = await production.run_missing_production(registry)
            return gate._json(res, 502 if res.get("error") else 200)
        except Exception:
            logger.exception("Missing-production scan failed")
            return gate._json({"error": "Couldn't check for untagged orders."}, 500)

    @mcp.custom_route("/api/production-labels/coverage", methods=["POST"])
    async def labels_coverage_route(request: Request):
        # Size-list coverage over recent orders. Shopify read, no AI.
        err, body, _who = await gate._guard(request)
        if err:
            return err
        try:
            n = int(body.get("orders") or 200)
        except (TypeError, ValueError, OverflowError):
            n = 200
        try:
            res = await core.run_label_coverage(registry, n)
            return gate._json(res, 502 if res.get("error") else 200)
        except Exception:
            logger.exception("Label coverage failed")
            return gate._json({"error": "Couldn't check size coverage. Check the server logs."}, 500)
