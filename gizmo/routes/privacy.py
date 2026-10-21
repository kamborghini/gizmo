"""The privacy routes: the privacy settings, and Shopify's privacy webhook
(data requests and redactions). Gathered from add_routes (stage 4 of the 14
October audit) where the first stood; their paths are literal, so no request
changes hands.
"""
import logging
import json
import time
from datetime import datetime, timezone
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from gizmo import store as jsonstore

import copilot as core
from gizmo import scheduler
from gizmo import activity
from gizmo import gate
from gizmo import orderbook
from gizmo import crm as salesdesk
from gizmo import team
from gizmo import privacy
from gizmo import bodies

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")



class PrivacyBody(bodies.Body):
    """What /api/privacy reads (gizmo/bodies.py): the request to settle, and
    the confirmation an erasure's reach was read."""
    id: bodies.Id = None
    at: bodies.Text = None
    email: bodies.Text = None
    reach: bodies.Text = None


def register(mcp, registry):
    """Add the privacy routes to the app."""

    @mcp.custom_route("/webhooks/privacy", methods=["POST"])
    async def privacy_webhook(request: Request):
        """Shopify's three mandatory compliance topics, on one receiver.

        Answering 200 is the contract: repeated failures make Shopify retire the
        subscription, and for these topics that is a compliance failure rather
        than a missed refresh. So the work happens behind a try and the ack does
        not depend on it - but it is logged, because an unrecorded redaction is
        indistinguishable from one that never ran. A shop/redact the app
        cannot act on yet is recorded as owed and tried again every hour
        (see _shop_redact_checked)."""
        raw, err = await privacy._webhook_body(request)
        if err is not None:
            return err
        # The hourly retry of an owed erasure lives in the scheduler, and an
        # uninstalled app is not opened, so nothing else may have started it.
        scheduler._ensure_scheduler(registry)
        topic = str(request.headers.get("x-shopify-topic") or "")
        delivery = str(request.headers.get("x-shopify-webhook-id") or "")
        if delivery and not orderbook._webhook_note_delivery(delivery):
            return PlainTextResponse("ok", status_code=200)   # a redelivery
        try:
            body = json.loads(raw.decode("utf-8", "replace")) or {}
        except Exception:
            body = {}
        cust = body.get("customer") or {}
        email = str(cust.get("email") or "")
        cid = cust.get("id") or ""
        try:
            if topic == "customers/redact":
                # Held, not erased on the spot: see _redact_hold. One that
                # cannot be recorded is sent back for Shopify to retry.
                held = privacy._redact_hold(email, cid)
                if held is None:
                    if delivery:
                        orderbook._webhook_seen.pop(delivery, None)
                    privacy._redact_unrecorded()
                    return PlainTextResponse("retry", status_code=503)
                if held and held.get("new"):
                    core._spawn_bg(privacy._redact_hold_check(held["id"]))
            elif topic == "customers/data_request":
                # Supplying the data is a human step on a 30-day clock. The
                # app's job is to receive the request and not lose it.
                privacy._privacy_note(topic, email, cid,
                              "customer asked for their data; supply it within 30 days")
                if not privacy._ask_hold(email, cid):
                    # Not kept: sent back for Shopify to retry, as an erasure is.
                    if delivery:
                        orderbook._webhook_seen.pop(delivery, None)
                    privacy._redact_unrecorded()
                    return PlainTextResponse("retry", status_code=503)
                privacy._privacy_mail()
            elif topic == "shop/redact":
                return await privacy._shop_redact_checked(delivery)
            else:
                privacy._privacy_note(topic or "(none)", email, cid, "unrecognised privacy topic")
        except Exception:
            logger.exception("privacy webhook %s failed", topic)
        return PlainTextResponse("ok", status_code=200)

    @mcp.custom_route("/api/privacy", methods=["POST"])
    async def privacy_requests_route(request: Request):
        """Settings, Privacy requests: the customer erasures Shopify asked for,
        each waiting for an admin to erase or stop (see _redact_hold), and the
        data requests to answer. An admin's: erasing is for good, and stopping
        one keeps a customer's records against what Shopify asked."""
        err, body, who = await gate._guard(request, min_level=team.ROLE_LEVELS["admin"], model=PrivacyBody)
        if err:
            return err
        op = str(body.get("op") or "list")
        notice = ""
        name = team._team_name(who) or "an admin"
        privacy._load_privacy_log()
        if privacy.PRIVACY_LOG_PATH in jsonstore._poisoned_stores:
            return gate._json({"error": "The privacy requests cannot be read just now, so none can be shown. "
                                   "Check the server's storage, or restore the latest backup."}, 503)
        if op == "stop_all":
            # A flood of requests nobody asked for means the app's secret is
            # out; one click settles it, with each stop recorded as usual.
            n = 0
            for h in privacy._held_requests():
                taken = privacy._redact_hold_drop(h["id"])
                if taken is not None:
                    privacy._redact_hold_stop(taken, name)
                    n += 1
            activity._track(who, "privacy", "stopped every waiting erasure request", str(n))
            notice = ("Stopped " + str(n) + (" request." if n == 1 else " requests.")) + " Nothing was erased."
            core._spawn_bg(scheduler._send_alert_email(
                "Reactor: every waiting erasure request was stopped",
                [name + " stopped every waiting request to erase customers' records (" + str(n) + "), as",
                 "nobody asked for them. Change the app's secret, and give Reactor the new one."]))
        if op in ("erase", "stop"):
            hid = str(body.get("id") or "")
            h = next((x for x in privacy._held_requests() if x["id"] == hid), None)
            if h is None:
                return gate._json({"error": "That request is no longer waiting."}, 404)
            if op == "erase":
                scope = privacy._redact_scope(h["email"])
                if scope.get("unreadable"):
                    return gate._json({"error": "The CRM cannot be read just now, so what this would erase is not "
                                           "known. Try again once it can be read."}, 503)
                # Who the admin was shown, checked again at the click: the CRM
                # may have changed since the list was drawn.
                if str(body.get("reach") or "") != scope.get("key"):
                    return gate._json({"error": "What this would erase has changed since the list was shown. "
                                           "Look at it again before erasing."}, 409)
            # Taken off the list first: two admins cannot both act on one.
            h = privacy._redact_hold_drop(hid)
            if h is None:
                return gate._json({"error": "That request is no longer waiting."}, 404)
            if op == "erase":
                out = privacy._redact_hold_erase(h, "erased: confirmed by " + name, name)
                activity._track(who, "privacy", "erased a customer's records on Shopify's request")
                notice = ("Erased, except a part that could not be erased yet: Reactor tries that again every hour."
                          if out.get("failed") else "Erased.")
            else:
                privacy._redact_hold_stop(h, name)
                activity._track(who, "privacy", "stopped an erasure request nobody asked for")
                notice = "Stopped. Nothing was erased."
                last = privacy._redact_hold_said.get("stopped")
                if last is None or time.monotonic() - last >= 6 * 3600:
                    privacy._redact_hold_said["stopped"] = time.monotonic()
                    core._spawn_bg(scheduler._send_alert_email(
                        "Reactor: an erasure request was stopped as not asked for",
                        [name + " stopped a request to erase a customer's records, as nobody asked for it.",
                         "Only someone holding the app's secret can send one that did not come from",
                         "Shopify: change the app's secret, and give Reactor the new one."]))
        elif op == "answered":
            aid, at = str(body.get("id") or ""), str(body.get("at") or "")[:40]
            stamp = datetime.now(timezone.utc).isoformat()
            if aid:
                privacy._redact_hold_write(lambda xs: [({**a, "answered": stamp, "answered_by": name}
                                                if a.get("id") == aid else a) for a in xs], key="asks")
            elif at:
                # One from before data requests had a list of their own.
                privacy._redact_hold_write(lambda xs: (xs + [{"at": at, "by": name}])[-1000:], key="answered")
            privacy._privacy_decision(str(body.get("email") or "")[:254], "", "data request answered", name)
            notice = "Marked answered."
        d = privacy._load_privacy_log()
        now = datetime.now(timezone.utc)

        def due(at: str) -> tuple:
            dd = privacy._privacy_due(at)
            return (dd.isoformat() if dd else "", bool(dd) and dd < now)
        asks = []
        for a in privacy._open_asks(d):
            du, late = due(str(a.get("received") or ""))
            asks.append({"id": a["id"], "email": a.get("email") or "", "customer_id": a.get("customer_id") or "",
                         "at": a.get("received") or "", "due": du, "overdue": late})
        # Data requests recorded before they had a list of their own: from
        # the log, until marked answered, however old.
        answered = {str(x.get("at") or "") for x in (d.get("answered") or []) if isinstance(x, dict)}
        # Anyone with an entry in the list (open or answered) is the list's.
        known = {(str(a.get("email") or ""), "" if a.get("email") else str(a.get("customer_id") or ""))
                 for a in (d.get("asks") or []) if isinstance(a, dict)}
        for e in (d.get("events") or []):
            if (isinstance(e, dict) and e.get("topic") == "customers/data_request"
                    and str(e.get("detail") or "").startswith("customer asked")
                    and str(e.get("at") or "") not in answered
                    and (str(e.get("email") or ""), "" if e.get("email") else str(e.get("customer_id") or ""))
                    not in known):
                du, late = due(str(e.get("at") or ""))
                asks.append({"id": "", "email": e.get("email") or "", "customer_id": str(e.get("customer_id") or ""),
                             "at": e.get("at") or "", "due": du, "overdue": late})
        # The oldest first (the nearest deadline), and only so many worked out
        # at once: a flood of two thousand froze the app for minutes.
        waiting = sorted(privacy._held_requests(d), key=lambda h: str(h.get("received") or ""))
        crm = None if salesdesk.CRM_PATH in jsonstore._poisoned_stores else salesdesk._load_crm()
        index = privacy._redact_index(crm) if crm is not None and salesdesk.CRM_PATH not in jsonstore._poisoned_stores else None
        held = []
        for h in waiting[:privacy.REDACT_LIST_MAX]:
            du, late = due(str(h.get("received") or ""))
            sc = privacy._redact_scope(h["email"], crm, index) if index is not None else {"unreadable": True}
            sc.pop("addresses", None)
            held.append({"id": h["id"], "email": h["email"], "customer_id": h.get("customer_id") or "",
                         "received": h.get("received") or "", "due": du, "overdue": late,
                         "shopify": h.get("shopify") or "unknown", "checked_at": h.get("checked_at") or "",
                         "scope": sc, "stopped_before": h.get("stopped_before") or ""})
        return gate._json({"held": held, "held_more": max(0, len(waiting) - privacy.REDACT_LIST_MAX),
                      "data_requests": asks, "notice": notice, "deadline_days": privacy.REDACT_DEADLINE_DAYS})
