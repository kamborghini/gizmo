"""The Xero sync settings route, moved from add_routes (stage 4 of the 14
October audit) where it stood.
"""
import logging
import re
from urllib.parse import urlparse
import httpx
from starlette.requests import Request

from gizmo import activity
from gizmo import gate
from gizmo import team
from gizmo import xero_sync as xerosync
from gizmo import bodies

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")



class ConnectorBody(bodies.Body):
    """What /api/connector reads (gizmo/bodies.py): the Xero sync's settings, a run's options, and what to look up."""
    status: bodies.Text = None
    kind: bodies.Text = None
    enabled: bodies.Flag = None
    fields: bodies.Fields = None
    since: bodies.Text = None
    dryRun: bodies.Flag = None
    limit: bodies.Whole = None
    order: bodies.Text = None
    tag: bodies.Text = None
    force: bodies.Flag = None


# The connector's acts that are an admin's, with what a member hears. True
# where a dry run is anyone's: it writes nothing, by the service's documented
# promise, so it is the same act as a review.
_ADMIN_ACTS = {
    "autorun_set": ("Only an admin can turn Auto Run on or off.", False),
    "settings_save": ("Only an admin can change the connector's settings.", False),
    "payouts": ("Only an admin can write notes onto Xero invoices.", True),
    "reimport": ("Only an admin can send documents to Xero.", True),
    "reimport_tag": ("Only an admin can send documents to Xero.", True),
    "send": ("Only an admin can send documents to Xero.", False),
    "retry": ("Only an admin can send documents to Xero.", False),
}


def register(mcp, registry):
    """Add the Xero sync settings route to the app."""



    @mcp.custom_route("/api/connector", methods=["POST"])
    async def connector_route(request: Request):
        """The Xero connector tab's whole API. op says what; the service does it."""
        err, body, who = await gate._guard(request)
        if err:
            return err
        op = str(body.get("op") or "status")
        # The rank before the body: a member hears they may not, not which
        # field was of the wrong kind.
        act = _ADMIN_ACTS.get(op)
        if act and team._team_level(who) < team.ROLE_LEVELS["admin"]:
            message, dry_is_anyones = act
            if not (dry_is_anyones and bool(body.get("dryRun"))):
                return gate._json({"error": message}, 403)
        refused = gate._body_refusal(ConnectorBody, body)
        if refused:
            return refused
        if not xerosync._connector_url():
            return gate._json({"available": False,
                          "note": "The connector service is not linked yet. Add its private "
                                  "address and token in the app's hosting settings."})
        # A URL with a scheme and a port but NO HOST. Railway resolves a
        # ${{service.VARIABLE}} reference to an empty string when it cannot
        # find that service, so "http://${{wrong.RAILWAY_PRIVATE_DOMAIN}}:8899"
        # arrives here as "http://:8899". Left to httpx that surfaces as
        # UnsupportedProtocol, which describes the symptom and hides the cause.
        if not urlparse(xerosync._connector_url()).hostname:
            return gate._json({"available": True,
                          "error": "The connector's address has no hostname in it (" + xerosync._connector_url()
                                   + "). A reference to another service's private domain "
                                     "resolves to nothing when the hosting cannot find the "
                                     "service it names, leaving just the scheme and the port. Copy "
                                     "the connector's private domain from its Settings, "
                                     "Networking, Private Networking and type it in full."},
                         502)
        try:
            if op in xerosync._CONNECTOR_READS:
                method, path = xerosync._CONNECTOR_READS[op]
                params = None
                if op == "ledger":
                    params = {k: str(body[k]) for k in ("status", "kind") if body.get(k)}
                code, data = await xerosync._connector_call(method, path, params)
                out = {"available": True, "data": data} if code < 400 else {"available": True, "error": (data or {}).get("error") or ("Connector error " + str(code))}
                return gate._json(out, 200 if code < 400 else code)
            if op == "review":
                # A dry run: the service maps everything and writes NOTHING,
                # by its own documented promise. Any tab holder may look.
                code, data = await xerosync._connector_call("POST", "/api/sync", {"dryRun": "1"})
                return gate._json({"available": True, "data": data}, code if code >= 400 else 200)
            if op == "autorun_set":
                # Turning the automation on or off. Admin only (_ADMIN_ACTS),
                # and the state lives on the connector's volume rather than
                # here, so gizmo cannot drift out of step with what is
                # actually running.
                on = bool(body.get("enabled"))
                code, data = await xerosync._connector_call("POST", "/api/autorun",
                                                   {"enabled": "true" if on else "false"})
                if code < 400:
                    # The interval the connector says it is using: it is a
                    # setting there (AUTO_RUN_INTERVAL_MINUTES), not ten.
                    mins = data.get("intervalMinutes") if isinstance(data, dict) else None
                    activity._track(who, "connector",
                           "turned Auto Run " + ("on" if on else "off"),
                           ("every " + str(mins or 10) + " minutes") if on else "")
                return gate._json({"available": True, "data": data}, code if code >= 400 else 200)

            if op == "settings_save":
                fields = body.get("fields")
                if not isinstance(fields, dict) or not fields:
                    return gate._json({"error": "Nothing to save."}, 400)
                # Only the settings the page offers. A pass-through would let
                # anything be written into the service's config from a browser.
                clean = {k: ("" if v is None else str(v))[:200]
                         for k, v in fields.items() if k in xerosync._CONNECTOR_SETTABLE}
                if not clean:
                    return gate._json({"error": "None of those are settings this page can change."}, 400)
                # As a JSON body: the connector reads this door's body and
                # nothing else. The page sends only the fields changed in it,
                # from settings read as it opened, because the connector keeps
                # a value the same as its default or variable as no choice,
                # so an unchanged stale value would clear a choice saved on
                # the connector's own tab.
                code, data = await xerosync._connector_call("POST", "/api/settings", json_body=clean)
                if code >= 400:
                    # The connector refused the save (a value out of range,
                    # say) and kept nothing: said as an error, which the page
                    # shows, rather than tucked under data, where the page
                    # read "Saved" over a save that stored nothing at all.
                    why = (data or {}).get("error") if isinstance(data, dict) else None
                    return gate._json({"available": True, "error": why or ("Connector error " + str(code)), "data": data}, code)
                unapplied = []
                try:
                    code2, now = await xerosync._connector_call("GET", "/api/settings")
                    if code2 < 400 and isinstance(now, dict):
                        unapplied = xerosync._connector_settings_unapplied(clean, now)
                except Exception:
                    pass   # the save itself was answered; the page reads the settings again anyway
                kept = sorted(set(clean) - set(unapplied))
                if kept:
                    activity._track(who, "connector", "changed connector settings", ", ".join(kept))
                return gate._json({"available": True, "data": data, "unapplied": unapplied})

            if op == "payouts":
                # Telling an invoice which payout paid it. A DRY RUN lists the
                # notes and writes nothing, so any tab holder may look; writing
                # them touches documents in the accounts and stays an admin's,
                # even though a History note cannot change a figure on one.
                since = str(body.get("since") or "").strip()[:10]
                if since and not re.match(r"^\d{4}-\d{2}-\d{2}$", since):
                    return gate._json({"error": "The date needs to be a date, for example 2026-08-01."}, 400)
                dry = bool(body.get("dryRun"))
                params = {}
                if since:
                    params["since"] = since
                if dry:
                    params["dryRun"] = "1"
                if body.get("limit"):
                    try:
                        params["limit"] = str(max(1, min(200, int(body["limit"]))))
                    except (TypeError, ValueError):
                        pass
                code, data = await xerosync._connector_call("POST", "/api/payouts", params)
                if not dry:
                    activity._track(who, "connector", "wrote payout notes to Xero",
                           "since " + (since or "the last 30 days"))
                return gate._json({"available": True, "data": data}, code if code >= 400 else 200)
            if op == "reimport":
                # One order at a time: how a connector is tested against real
                # books without putting a whole queue through it. A dry run
                # writes nothing, by the service's documented promise, so it is
                # the same act as a review and any tab holder may run it; the
                # send writes into the accounts and stays an admin's.
                order = str(body.get("order") or "").strip()
                if not order:
                    return gate._json({"error": "Say which order to send (e.g. #104300)."}, 400)
                dry = bool(body.get("dryRun"))
                params = {"order": order}
                if dry:
                    params["dryRun"] = "1"
                if body.get("force"):
                    params["force"] = "1"
                code, data = await xerosync._connector_call("POST", "/api/reimport", params)
                if not dry:
                    activity._track(who, "connector", "sent one order to Xero", order)
                return gate._json({"available": True, "data": data}, code if code >= 400 else 200)
            if op == "reimport_tag":
                # Every order carrying a tag, one at a time through the same
                # path as a single send. The tag stays on the orders: it is a
                # label, not a to-do, so the same tag can be sent again and an
                # order already in Xero and unchanged is a lookup, not a write.
                tag = str(body.get("tag") or "").strip()
                if not tag:
                    return gate._json({"error": "Say which tag to send (e.g. xero-price-check)."}, 400)
                dry = bool(body.get("dryRun"))
                params = {"tag": tag}
                if dry:
                    params["dryRun"] = "1"
                if body.get("force"):
                    params["force"] = "1"
                code, data = await xerosync._connector_call("POST", "/api/reimport-tag", params)
                if not dry:
                    activity._track(who, "connector", "sent tagged orders to Xero", tag)
                return gate._json({"available": True, "data": data}, code if code >= 400 else 200)
            if op in ("send", "retry"):
                # These write invoices and credit notes into Xero (_ADMIN_ACTS).
                if op == "send":
                    code, data = await xerosync._connector_call("POST", "/api/sync")
                else:
                    code, data = await xerosync._connector_call("POST", "/api/retry")
                activity._track(who, "connector", "connector " + op)
                return gate._json({"available": True, "data": data}, code if code >= 400 else 200)
            return gate._json({"error": "Unknown op."}, 400)
        except httpx.HTTPError as e:
            logger.warning("connector unreachable: %r", e)
            # Three different faults used to read as one sentence, and each has
            # a different fix: a name that does not resolve, a name that does
            # with nothing listening, and a service that answers too slowly.
            # The host and the failure mode are not secrets - the token is
            # separate - and between them they ARE the diagnosis, so they say
            # it here rather than only in a log nobody reading the tab can see.
            host = xerosync._connector_url() or "(unset)"
            text = str(e).lower()
            unresolved = ("name or service not known" in text
                          or "nodename nor servname" in text
                          or "temporary failure in name resolution" in text
                          or "getaddrinfo" in text)
            if isinstance(e, (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.PoolTimeout)):
                why = ("It accepted the connection but did not reply in time, so the "
                       "service is running and stuck rather than missing. Its own logs "
                       "will say why.")
            elif unresolved:
                why = ("That name does not resolve, so the connector's address points at a "
                       "service the hosting does not have. Check the service name in it: a "
                       "private domain reference that names no service resolves to this app itself.")
            elif isinstance(e, httpx.ConnectError):
                why = ("The name resolves but nothing is listening there. Either the port "
                       "is wrong, or the service is bound to IPv4: the hosting's private "
                       "network is IPv6 only, so the connector has to listen on every "
                       "address (::) to be reachable.")
            else:
                why = "The connection failed (" + type(e).__name__ + ")."
            return gate._json({"available": True,
                          "error": "The connector did not answer at " + host + ". " + why},
                         502)
