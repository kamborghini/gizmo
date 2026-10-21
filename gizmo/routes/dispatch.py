"""The dispatch desk's routes: shipping settings, the EORI check, pasted
addresses, one-off shipments, and the desk's collections, quote, diagnose,
book, label, manifest, margin and cancel.

Moved whole out of copilot.add_routes (stage 4 of the 14 October audit).
add_routes calls register() where they stood, so the route table keeps its
order. They read the desk as desk.NAME and copilot.py as core.NAME.
"""
import logging
import re
import json
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import eori
try:
    import worldoptions
except Exception:                     # keep the app booting if the connector is unavailable
    worldoptions = None
from starlette.requests import Request

import copilot as core
from gizmo import orderbook
from gizmo import production
from gizmo import shopify
from gizmo import dispatch as desk
from gizmo import activity
from gizmo import gate
from gizmo import team
from gizmo import ai as claude

# The same logger as copilot.py's, so the routes' log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


def register(mcp, registry):
    """Add the desk's 16 routes to the app."""
    @mcp.custom_route("/api/shipping/config", methods=["POST"])
    async def shipping_config_route(request: Request):
        """Get or set shipping settings. The API key is write-only: it is saved
        server-side and never returned; the UI only ever sees connected + last4."""
        err, body, who = await gate._guard(request)
        if err:
            return err
        op = str(body.get("op") or "get").lower()
        if op != "set":
            return gate._json({"config": desk._shipping_public(desk._load_shipping())})
        if team._team_level(who) < team.ROLE_LEVELS["admin"]:
            return gate._json({"error": "Only an admin can change the shipping settings."}, 403)
        cfg = desk._load_shipping()
        if "origin" in body:
            cfg["origin"] = desk._clean_origin(body.get("origin"))
        if "boxes" in body:
            cleaned = desk._clean_boxes(body.get("boxes"))
            if cleaned:
                cfg["boxes"] = cleaned
        if "default_box_id" in body:
            # Only a box that actually exists once this save has landed. A
            # pointer at a deleted preset would send the dispatch panel looking
            # for a parcel that is not there; empty means "the first one".
            want = str(body.get("default_box_id") or "")[:40]
            have = {str(b.get("id") or "") for b in (cfg.get("boxes") or [])}
            cfg["default_box_id"] = want if want in have else ""
        if "notify_customer" in body:
            cfg["notify_customer"] = bool(body.get("notify_customer"))
        for tkey in ("ready_time", "close_time"):
            if tkey in body:
                tv = str(body.get(tkey) or "").strip()
                if tv and not desk._TIME_RE.match(tv):
                    return gate._json({"error": "Collection times must be in 24-hour HH:MM form, "
                                           "e.g. 14:00."}, 400)
                cfg[tkey] = tv
        if str(cfg.get("ready_time") or "") and str(cfg.get("close_time") or "") \
                and cfg["ready_time"] >= cfg["close_time"]:
            return gate._json({"error": "The collection ready time must be before the close time."}, 400)
        if body.get("collection_option"):
            co = str(body.get("collection_option")).strip()
            if worldoptions and co not in worldoptions.COLLECTION_OPTIONS:
                return gate._json({"error": "Unknown collection arrangement."}, 400)
            cfg["collection_option"] = co
        for lkey in ("label_size_production", "label_size_shipping"):
            if lkey in body:
                want = str(body.get(lkey) or "").strip()
                if want not in desk.LABEL_STOCK:
                    # Refused rather than coerced: a silent fallback would print
                    # a run on the wrong stock and nobody would know why.
                    return gate._json({"error": "That is not a label size this app can print."}, 400)
                cfg[lkey] = want
        for skey, cap in (("eori", 30), ("vat_number", 30), ("default_hs_code", 20), ("trade_term", 20)):
            if skey in body:
                cfg[skey] = str(body.get(skey) or "").strip()[:cap]
        if body.get("export_reason"):
            er = str(body.get("export_reason")).strip()
            if worldoptions and er not in worldoptions.EXPORT_REASONS:
                return gate._json({"error": "Unknown export reason."}, 400)
            cfg["export_reason"] = er
        if body.get("duties_payor"):
            dp = str(body.get("duties_payor")).strip()
            if worldoptions and dp not in worldoptions.DUTIES_PAYORS:
                return gate._json({"error": "Unknown duties choice."}, 400)
            cfg["duties_payor"] = dp
        if isinstance(body.get("collection_by_carrier"), dict):
            # Only carriers we recognise, only arrangements the courier offers.
            # An empty value means "no rule for this one", which falls back to
            # the standing setting rather than being stored as a blank.
            valid_c = {c["code"] for c in (worldoptions.carrier_choices() if worldoptions else [])}
            valid_a = set(worldoptions.COLLECTION_OPTIONS if worldoptions else [])
            clean = {}
            for k, v in body["collection_by_carrier"].items():
                code, arr = str(k).strip().upper(), str(v or "").strip()
                if code in valid_c and arr in valid_a:
                    clean[code] = arr
            cfg["collection_by_carrier"] = clean
        if body.get("currency"):
            cfg["currency"] = str(body.get("currency"))[:3].upper()
        if body.get("plugin_code"):
            pcv = str(body.get("plugin_code")).strip()
            if worldoptions and pcv not in worldoptions.PLUGIN_CODES:
                return gate._json({"error": "Unknown plugin code."}, 400)
            cfg["plugin_code"] = pcv or "Web_Service"
        if body.get("base_url"):
            base = str(body.get("base_url")).strip()[:200]
            if base.startswith("http://") or base.startswith("https://"):
                cfg["base_url"] = base.rstrip("/")
                if worldoptions:
                    worldoptions.set_base_url(cfg["base_url"])
        desk._save_shipping(cfg)
        activity._track(who, "settings", "changed shipping settings",
               "courier credentials updated" if any(k in body for k in ("meter_number", "key", "password"))
               else "origin, boxes or preferences")
        # Credentials: only persist non-empty values, and only when not env-managed.
        if worldoptions and any(k in body for k in ("meter_number", "key", "password")):
            if desk._wo_creds_from_env():
                return gate._json({"error": "World Options credentials are set on the server "
                                       "and can't be changed from here."}, 400)
            meter = body.get("meter_number"); key = body.get("key"); pw = body.get("password")
            meter = str(meter).strip() if isinstance(meter, str) and meter.strip() else None
            key = str(key).strip() if isinstance(key, str) and key.strip() else None
            pw = str(pw).strip() if isinstance(pw, str) and pw.strip() else None
            if meter or key or pw:
                desk._save_wo_creds(meter=meter, key=key, password=pw)
        if worldoptions:
            desk._wo_boot()   # re-push creds + plugin + base into the client
        return gate._json({"config": desk._shipping_public(desk._load_shipping()), "ok": True})

    @mcp.custom_route("/api/shipping/validate", methods=["POST"])
    async def shipping_validate_route(request: Request):
        """Confirm the World Options credentials work by pricing a tiny test parcel
        (read-only; never charges)."""
        err, body, _who = await gate._guard(request)
        if err:
            return err
        if not worldoptions or not worldoptions.configured():
            return gate._json({"ok": False, "error": "No credentials set."}, 200)
        try:
            res = await worldoptions.validate()
            return gate._json({"ok": bool(res.get("ok")), "message": res.get("message") or "",
                          "error": ("" if res.get("ok") else res.get("message") or "")})
        except Exception:
            logger.exception("shipping validate failed")
            return gate._json({"ok": False, "error": "Couldn't reach World Options."}, 200)

    @mcp.custom_route("/api/eori/check", methods=["POST"])
    async def eori_check_route(request: Request):
        """Check a customer's EORI number against the EU's validation service.

        Gated like the shipping settings, because it is the same job: getting
        the customs paperwork right before a parcel leaves. The answer is only
        ever advisory - see eori.py for why an unreachable service must read as
        "unknown" here and never as "invalid"."""
        err, body, who = await gate._guard(request)
        if err:
            return err
        raw = body.get("number")
        kind = eori.classify(raw)
        if kind == "bad":
            return gate._json({"error": "That is not an EORI number. They start with a "
                                   "two-letter country code, for example "
                                   "DE123456789012345."}, 400)
        # Our own ceiling, separate from the per-client one in _pre_checks. The
        # EU service publishes a request limit and answers a flood with nothing
        # at all, so the thing being protected here is not this app: it is our
        # ability to get an answer out of Brussels for the next hour.
        if not gate._window_ok(desk._eori_hits, desk.EORI_MAX_PER_MIN, time.monotonic()):
            return gate._json({"error": "Slow down: too many checks in a minute."}, 429)
        try:
            res = await eori.check(raw)
        except Exception:
            # eori.check answers rather than raises for every service problem,
            # so reaching here means a bug on our side. It still must not read
            # as a verdict on the customer's number.
            logger.exception("EORI check failed")
            return gate._json({"error": "The EORI check could not be run."}, 502)
        # Worth a ledger line: it names a third party we asked about a customer,
        # and "we checked and it came back invalid" is a claim someone may later
        # have to stand behind.
        activity._track(who, "settings", "checked an EORI number",
               res["number"] + " - " + res["status"])
        return gate._json(res)

    @mcp.custom_route("/api/dispatch/parse-address", methods=["POST"])
    async def parse_address_route(request: Request):
        """Turn a pasted block of text into address fields. Free, and local unless
        the local pass cannot place something."""
        err, body, _who = await gate._guard(request)
        if err:
            return err
        text = str(body.get("text") or "")[:4000]
        if not text.strip():
            return gate._json({"error": "Paste an address first."}, 400)
        local = desk._parse_address(text)
        if local["confident"] or not claude.ANTHROPIC_API_KEY:
            return gate._json({"address": local["address"], "source": "local",
                          "note": ("" if local["confident"] else
                                   "Some of this could not be read. Check every field.")})
        try:
            ai = await desk._ai_address(text)
        except Exception as e:
            logger.exception("AI address parse failed")
            return gate._json({"address": local["address"], "source": "local",
                          "note": "Some of this could not be read. Check every field."})
        # Prefer Claude's reading, but never let it blank a field the local pass
        # did find: it is the one that read the text literally.
        merged = dict(local["address"])
        for k, v in ai.items():
            if str(v or "").strip():
                merged[k] = v
        return gate._json({"address": merged, "source": "ai",
                      "note": "Read with AI because the layout was unusual. Check every field."})

    @mcp.custom_route("/api/custom/quote", methods=["POST"])
    async def custom_quote_route(request: Request):
        """Price couriers to a pasted address. Free / read-only, no charge."""
        err, body, _who = await gate._guard(request)
        if err:
            return err
        dest = desk._clean_address(body.get("address") or {})
        boxes, err = desk._clean_parcel_list(body)
        if err:
            return gate._json({"error": err}, 400)
        try:
            declared = float(body.get("declared") or 0)
        except (TypeError, ValueError):
            declared = 0.0
        try:
            res = await desk.run_custom_quote(registry, dest, boxes,
                                         insurance=desk._insurance_amount(body), declared=declared)
            return gate._json(res, 400 if res.get("error") else 200)
        except Exception:
            logger.exception("custom quote failed")
            return gate._json({"error": "Couldn't get courier quotes. Check the server logs."}, 500)

    @mcp.custom_route("/api/custom/book", methods=["POST"])
    async def custom_book_route(request: Request):
        """Book a courier to a pasted address. THIS SPENDS MONEY."""
        err, body, who = await gate._guard(request)
        if err:
            return err
        option = body.get("option")
        if not isinstance(option, dict):
            return gate._json({"error": "Pick a courier service first."}, 400)
        boxes, err = desk._clean_parcel_list(body)
        if err:
            return gate._json({"error": err}, 400)
        try:
            declared = float(body.get("declared") or 0)
        except (TypeError, ValueError):
            declared = 0.0
        try:
            desk._book_confirmed.set(bool(body.get("confirm_unknown")))
            res = await desk.run_custom_book(
                registry, str(body.get("id") or ""), option,
                desk._clean_address(body.get("address") or {}), boxes,
                insurance=desk._insurance_amount(body),
                reference=str(body.get("reference") or ""),
                contents=str(body.get("contents") or ""),
                declared=declared,
                customs_body=(body.get("customs") if isinstance(body.get("customs"), dict) else None),
                signature=str(body.get("signature") or ""), by=str(who or ""),
                # Only an admin can ask for this. A member's request is not an
                # error - the shipment simply books the way a member's always
                # has, visible to the desk.
                admin_only=(bool(body.get("admin_only"))
                            and team._team_level(who) >= team.ROLE_LEVELS["admin"]))
            if not res.get("error"):
                svc = str(option.get("service") or "").strip()[:40]
                activity._track(who, "dispatch", "booked a custom shipment",
                       (str(body.get("reference") or "pasted address")[:30]
                        + (" · " + svc if svc else "")))
            return gate._json(res, 400 if res.get("error") else 200)
        except Exception:
            logger.exception("custom booking failed")
            return gate._json({"error": "The booking failed. It MAY still have been booked and "
                                   "charged: check your World Options portal before trying again."}, 500)

    @mcp.custom_route("/api/custom/list", methods=["POST"])
    async def custom_list_route(request: Request):
        """Pasted-address shipments already booked. Read-only.

        These have no order to be a row of, so without this they are only
        reachable from inside the booking window: a person looking for last
        month's label had to press a button that reads like "spend money
        again". They get their own queue on the desk instead."""
        err, body, _who = await gate._guard(request)
        if err:
            return err
        try:
            limit = max(1, min(int(body.get("limit") or 200), 500))
        except (TypeError, ValueError):
            limit = 200
        # An admin sees the hidden ones; everyone else is never told they
        # exist, which is the whole point of the mark.
        may = team._team_level(_who) >= team.ROLE_LEVELS["admin"]
        rows = desk._custom_shipments(limit, include_private=may)
        q = str(body.get("q") or "").strip().lower()[:80]
        if q:
            rows = [r for r in rows if q in " ".join(str(r.get(k) or "") for k in
                    ("reference", "customer", "tracking", "carrier", "contents")).lower()]
        # Whether the label is still on disk decides whether Reprint can work,
        # so say it here rather than letting the button fail.
        for r in rows:
            r["has_label"] = bool(desk._load_dispatch_labels(r.get("id")))
        # So the page knows whether to draw the control at all. The server is
        # the gate either way: /api/custom/visibility refuses the rest.
        return gate._json({"shipments": rows, "can_hide": may})

    @mcp.custom_route("/api/custom/visibility", methods=["POST"])
    async def custom_visibility_route(request: Request):
        """Keep one pasted-address shipment to admins, or let it back out.

        Admin-rank only, both to set and to clear: a member who could clear it
        could read everything it was hidden for, and a member who could set it
        could hide a shipment from the people who have to send it."""
        err, body, who = await gate._guard(request, min_level=team.ROLE_LEVELS["admin"])
        if err:
            return err
        key = str(body.get("id") or "")
        on = bool(body.get("admin_only"))
        ok, why = desk._set_custom_private(key, on)
        if not ok:
            return gate._json({"error": why}, 400)
        activity._track(who, "dispatch",
                        "hid a custom shipment from the team" if on
                        else "showed a custom shipment to the team", key[:60])
        return gate._json({"ok": True, "admin_only": on})

    @mcp.custom_route("/api/dispatch/collections", methods=["POST"])
    async def dispatch_collections_route(request: Request):
        """What is coming, and from whom, on a given day.

        World Options cannot be asked this. Their service exposes exactly three
        operations - DoShipment, GetAllServicesAndRates and VoidShipment - so
        there is nothing to query. This is gizmo's own record of the collections
        IT booked, which is why the panel says so rather than implying it read
        the courier's diary."""
        err, body, who = await gate._guard(request)
        if err:
            return err
        day = str(body.get("date") or "")[:10] or desk._dispatch_today()
        cfg = desk._load_shipping()
        # The courier's own confirmations for the day, less anything cleared.
        booked = desk._collections_for(day)
        by_carrier = cfg.get("collection_by_carrier")
        by_carrier = by_carrier if isinstance(by_carrier, dict) else {}
        rows = []
        for c in (worldoptions.carrier_choices() if worldoptions else []):
            code = c["code"]
            arrangement = str(by_carrier.get(code) or "").strip() or str(cfg.get("collection_option") or "")
            row = desk._collection_row(booked.get(code))
            scheduled = row.get("date") == day
            rows.append({
                "carrier": code, "label": c["label"], "arrangement": arrangement,
                "arrangement_label": desk.COLLECTION_MESSAGES.get(arrangement, arrangement),
                "configured": code in by_carrier,
                "scheduled": scheduled,
                "booked_at": row.get("at") if scheduled else "",
                "order": row.get("order") if scheduled else "",
                "service": row.get("service") if scheduled else "",
                # World Options' own collection reference, off the booking reply.
                "ref": (booked.get(code) or {}).get("ref", "") if scheduled else "",
                "ref_date": (booked.get(code) or {}).get("ref_date", "") if scheduled else "",
                "ref_time": (booked.get(code) or {}).get("ref_time", "") if scheduled else "",
                # Nothing is coming and nothing needs to: they call anyway.
                "standing": arrangement in ("I_Have_Daily_Collection",
                                            "I_Already_Have_Collection_Scheduled"),
            })
        if body.get("op") == "clear":
            code = str(body.get("carrier") or "").strip().upper()
            if team._team_level(who) < team.ROLE_LEVELS["admin"]:
                return gate._json({"error": "Only an admin can clear a collection."}, 403)
            if code:
                # A marker, not a deletion: the booking that secured this
                # collection is still on the dispatch record and would simply
                # re-assert it on the next read.
                d = desk._load_collections()
                d[code] = {"date": day, "cleared": True,
                           "at": datetime.now(timezone.utc).isoformat()}
                desk._write_collections(d)
                activity._track(who, "dispatch", "cleared a collection", code + " for " + day)
                return gate._json({"ok": True, "cleared": code})
        return gate._json({"date": day, "rows": rows,
                      "note": "Collections World Options confirmed on the booking, by their own "
                              "reference. Their service cannot be asked what is scheduled, so a "
                              "collection booked in their portal rather than here will not show."})

    @mcp.custom_route("/api/dispatch/quote", methods=["POST"])
    async def dispatch_quote_route(request: Request):
        """Price couriers for one order. Free / read-only, no charge."""
        err, body, _who = await gate._guard(request)
        if err:
            return err
        try:
            oid = int(body.get("order_id") or 0)
        except (TypeError, ValueError, OverflowError):
            oid = 0
        if not oid:
            return gate._json({"error": "No order id given."}, 400)
        boxes, perr = desk._clean_parcel_list(body)
        if perr:
            return gate._json({"error": perr}, 400)
        try:
            res = await desk.run_dispatch_quote(registry, oid, boxes, insurance=desk._insurance_amount(body))
            return gate._json(res, 400 if res.get("error") else 200)
        except Exception:
            logger.exception("dispatch quote route failed")
            return gate._json({"error": "Couldn't get courier quotes."}, 500)

    @mcp.custom_route("/api/dispatch/diagnose", methods=["POST"])
    async def dispatch_diagnose_route(request: Request):
        """Why is a courier service missing? Quotes the same parcel several ways
        and reports what each returns. Free and read-only."""
        err, body, _who = await gate._guard(request)
        if err:
            return err
        try:
            oid = int(body.get("order_id") or 0)
        except (TypeError, ValueError, OverflowError):
            oid = 0
        if not oid:
            return gate._json({"error": "No order id given."}, 400)
        boxes, perr = desk._clean_parcel_list(body)
        if perr:
            return gate._json({"error": perr}, 400)
        try:
            res = await desk.run_dispatch_diagnose(registry, oid, boxes)
            return gate._json(res, 400 if res.get("error") else 200)
        except Exception:
            logger.exception("dispatch diagnose failed")
            return gate._json({"error": "Couldn't run the service check."}, 500)

    @mcp.custom_route("/api/dispatch/book", methods=["POST"])
    async def dispatch_book_route(request: Request):
        """Book the chosen courier (CHARGES the WO account), fulfill + tag."""
        err, body, _who = await gate._guard(request)
        if err:
            return err
        try:
            oid = int(body.get("order_id") or 0)
        except (TypeError, ValueError, OverflowError):
            oid = 0
        if not oid:
            return gate._json({"error": "No order id given."}, 400)
        option = body.get("option") if isinstance(body.get("option"), dict) else {}
        boxes, perr = desk._clean_parcel_list(body)
        if perr:
            return gate._json({"error": perr}, 400)
        notify = body.get("notify")
        notify = None if notify is None else bool(notify)
        customs_body = body.get("customs") if isinstance(body.get("customs"), dict) else None
        try:
            co = str(body.get("collection_option") or "").strip()
            if co and worldoptions and co not in worldoptions.COLLECTION_OPTIONS:
                return gate._json({"error": "That is not a collection arrangement World Options offers."}, 400)
            desk._book_confirmed.set(bool(body.get("confirm_unknown")))
            res = await desk.run_dispatch_book(registry, oid, option, boxes, notify=notify,
                                          force=bool(body.get("force")),
                                          insurance=desk._insurance_amount(body),
                                          signature=str(body.get("signature") or "")[:60],
                                          customs_body=customs_body, by=_who,
                                          collection_option=co)
            if not res.get("error"):
                nm = re.sub(r"[^#\w-]", "", str(body.get("name") or ""))[:20] or f"order {oid}"
                svc = str(option.get("service") or "").strip()[:40]
                activity._track(_who, "dispatch", "booked a courier", (nm + (" · " + svc if svc else "")))
            return gate._json(res, 400 if res.get("error") else 200)
        except Exception:
            logger.exception("dispatch book route failed")
            return gate._json({"error": "Something went wrong while booking. It MAY still have been "
                                   "booked and charged: press Refresh, and check this order in "
                                   "your World Options portal before trying again."}, 500)

    @mcp.custom_route("/api/dispatch/label", methods=["POST"])
    async def dispatch_label_route(request: Request):
        """Return the stored label(s) for an already-dispatched order (reprint).
        Read-only; the SOAP API has no fetch-by-tracking service, so labels are
        kept from the booking."""
        err, body, _who = await gate._guard(request)
        if err:
            return err
        # Either a Shopify order or a pasted-address shipment: both keep their
        # label in the same place, so reprint is one path.
        oid = desk._shipment_key(body)
        if not oid:
            return gate._json({"error": "No shipment given."}, 400)
        # A hidden shipment's label carries the name and address it was hidden
        # for, and an id is guessable in a way the queue's rows are not, so the
        # same answer as a shipment that does not exist.
        if (desk._is_private((desk._load_dispatch() or {}).get(str(oid)))
                and team._team_level(_who) < team.ROLE_LEVELS["admin"]):
            return gate._json({"error": "No stored label for this shipment. It may have been dispatched "
                                   "before labels were saved, or on another device."}, 404)
        labels = desk._load_dispatch_labels(oid)
        if not labels:
            return gate._json({"error": "No stored label for this shipment. It may have been dispatched "
                                   "before labels were saved, or on another device."}, 404)
        # Self-heal: an order booked while labels were stored as LINKS gets the real
        # file downloaded on its next open, and the fix is saved back.
        tech = None
        if any(isinstance(l, dict) and l.get("type") == "url" for l in labels):
            resolved = await desk._resolve_label_links(labels)
            if resolved != labels:
                labels = resolved
                try:
                    desk._save_dispatch_labels(oid, labels)
                except Exception:
                    logger.exception("could not save the resolved labels for order %s", oid)
            still = [l for l in labels if isinstance(l, dict) and l.get("type") == "url"]
            if still and worldoptions:
                # The link would not download. Report what it is and what it answers,
                # so the failure is readable at the desk instead of a mystery tab.
                reports = []
                for l in still[:3]:
                    try:
                        reports.append(await worldoptions.label_link_report(l.get("value")))
                    except Exception as e:
                        reports.append({"url": str(l.get("value"))[:300], "problem": repr(e)[:200]})
                tech = {"reply": json.dumps(reports, indent=1)[:2000],
                        "when": datetime.now(timezone.utc).isoformat(), "order": str(oid)}
                logger.error("label link would not download for order %s: %s", oid, tech["reply"])
                desk._record_wo_failure(tech)
        try:
            withimgs = desk._with_print_images(labels)
            if withimgs != labels:
                labels = withimgs
                desk._save_dispatch_labels(oid, labels)
        except Exception:
            logger.exception("label render on reprint failed for order %s", oid)
        out = {"ok": True, "labels": labels}
        if tech:
            out["tech"] = tech
        return gate._json(out)

    @mcp.custom_route("/api/dispatch/manifest", methods=["POST"])
    async def dispatch_manifest_route(request: Request):
        """Everything booked on one day (Europe/London): the driver handover list
        and the sheet to check the World Options invoice against. Read-only."""
        err, body, _who = await gate._guard(request)
        if err:
            return err
        want = str((body or {}).get("date") or "").strip()
        london = ZoneInfo("Europe/London")
        if want:
            try:
                day = datetime.strptime(want, "%Y-%m-%d").date()
            except ValueError:
                return gate._json({"error": "Date must be YYYY-MM-DD."}, 400)
        else:
            day = datetime.now(london).date()
        # The handover sheet is printable by anyone signed in, so it is the
        # other place a hidden shipment would have named its customer, its
        # address and its tracking number.
        may = team._team_level(_who) >= team.ROLE_LEVELS["admin"]
        rows = []
        for oid, e in desk._load_dispatch().items():
            ts = str(e.get("dispatched_at") or "")
            if not ts or not e.get("tracking_number"):
                continue
            if not may and desk._is_private(e):
                continue
            try:
                when = datetime.fromisoformat(ts)
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if when.astimezone(london).date() != day:
                continue
            rows.append({
                "order_id": oid,
                "admin_url": orderbook._admin_order_url(oid),
                "order_name": e.get("order_name") or ("#" + str(oid)),
                "customer": e.get("customer") or "",
                "carrier": (e.get("carrier_label")
                            or (worldoptions.carrier_display(e.get("carrier_name") or "")
                                if worldoptions else "") or ""),
                "service": e.get("service_name") or "",
                "tracking": e.get("tracking_number") or "",
                "collection_ref": (worldoptions.parse_collection(e.get("collection_date"))["ref"]
                                   if worldoptions else (e.get("collection_date") or "")),
                "amount": e.get("amount"),
                "amount_ex_vat": e.get("amount_ex_vat"),
                "shipping_paid": e.get("shipping_paid") or "",
                "currency": e.get("currency") or "GBP",
                "canceled": bool(e.get("canceled")),
                "international": bool(e.get("international")),
                "time": when.astimezone(london).strftime("%H:%M"),
                "by": e.get("by") or "",
            })
        rows.sort(key=lambda r: r["time"])
        live = [r for r in rows if not r["canceled"]]

        def _counted(key):
            return [float(r[key]) for r in live
                    if r.get(key) not in (None, "") and str(r[key]).replace(".", "", 1).replace("-", "", 1).isdigit()]
        def _tot(key):
            vals = _counted(key)
            return round(sum(vals), 2) if vals else None
        # This sheet exists to be checked against the World Options invoice, so
        # a total that quietly leaves out the shipments whose price is unknown
        # is worse than no total: it reconciles, and it is wrong. Say how many
        # rows are behind each figure.
        missing = len(live) - len(_counted("amount"))
        return gate._json({"ok": True, "date": day.isoformat(), "rows": rows,
                      "totals": {"shipments": len(live),
                                 "priced": len(_counted("amount")),
                                 "unpriced": missing,
                                 "totals_note": (str(missing) + " shipment(s) have no price yet, "
                                                 "so these totals do not cover them."
                                                 if missing else ""),
                                 "courier_inc_vat": _tot("amount"),
                                 "courier_ex_vat": _tot("amount_ex_vat"),
                                 "customer_paid": _tot("shipping_paid")}})

    @mcp.custom_route("/api/margin", methods=["POST"])
    async def margin_route(request: Request):
        """What dispatched orders actually made. Read-only, no AI."""
        err, body, _who = await gate._guard(request)
        if err:
            return err
        try:
            days = int((body or {}).get("days") or 30)
        except (TypeError, ValueError):
            days = 30
        try:
            return gate._json(await desk.run_margin_report(registry, days))
        except Exception:
            logger.exception("margin report failed")
            return gate._json({"error": "Could not build the margin report."}, 500)

    @mcp.custom_route("/api/dispatch/cancel", methods=["POST"])
    async def dispatch_cancel_route(request: Request):
        """Cancel a booked shipment at World Options (best-effort)."""
        err, body, _who = await gate._guard(request)
        if err:
            return err
        if not worldoptions or not worldoptions.configured():
            return gate._json({"error": "World Options is not connected."}, 400)
        tn = str(body.get("tracking_number") or "").strip()
        if not tn:
            return gate._json({"error": "No tracking number given."}, 400)
        oid = desk._shipment_key(body)
        # The tracking number and the order key arrive as two INDEPENDENT
        # client values, and the shipment modal is built once at open time. A
        # stale tab could therefore void T1 and stamp "cancelled" onto T2 - a
        # live, paid label - which then unblocks a third booking. Bind them:
        # the number must be the order's CURRENT shipment. The whole exchange
        # runs under the dispatch lock, the same one the booking path holds,
        # so a cancel cannot interleave with a book.
        async with orderbook._dispatch_lock(oid or tn):
            if oid:
                cur = (desk._load_dispatch().get(str(oid)) or {})
                # Someone who cannot see a shipment cannot void its label
                # either. Reaching here means both the key and the tracking
                # number were guessed, which the filtered list, manifest and
                # label make implausible rather than impossible; a cancel
                # spends the booking, so it does not rely on that.
                if (desk._is_private(cur)
                        and team._team_level(_who) < team.ROLE_LEVELS["admin"]):
                    return gate._json({"error": "No shipment given."}, 400)
                have = str(cur.get("tracking_number") or "").strip()
                if have and have != tn:
                    return gate._json({"error": "That tracking number is not this order's current "
                                           "shipment - it was re-booked since this page was "
                                           "opened. Refresh and try again."}, 409)
            try:
                res = await worldoptions.cancel(tn)
            except worldoptions.WorldOptionsError as e:
                return gate._json({"error": str(e)}, 400)
            except Exception:
                logger.exception("dispatch cancel failed")
                return gate._json({"error": "Couldn't cancel the shipment."}, 500)
            return await _finish_cancel(oid, tn, res, _who)

    async def _finish_cancel(oid, tn, res, _who):
        note = ""
        if oid:
            entry = (desk._load_dispatch().get(str(oid)) or {})
            def _mark_cancelled(e):
                e["canceled"] = True
                return e
            try:
                desk._update_dispatch(oid, _mark_cancelled)
            except desk.DispatchStoreUnwritable:
                logger.exception("could not record the cancellation of %s", oid)
                return gate._json({"error": "The shipment was cancelled at World Options, but that "
                                       "could not be recorded here. Do NOT re-book yet: check "
                                       "the data volume, then refresh."}, 500)
            activity._track(_who, "dispatch", "cancelled a shipment",
                   (entry.get("order_name") or str(oid))[:30])
            # A pasted-address shipment has no order behind it: the void at World
            # Options is the whole cancellation, and there is nothing in Shopify to
            # put back. Everything below this line is order repair.
            if desk._is_adhoc(oid):
                return gate._json({"ok": True, "note": note, "canceled": True})
            # Undo what the booking did in Shopify, so the customer is not left
            # with dead tracking and the order can be re-dispatched cleanly.
            fid = entry.get("fulfillment_id")
            if fid and shopify._fulfillment_canceler is not None:
                try:
                    fc = await shopify._fulfillment_canceler(int(fid))
                    orderbook._orders_changed([oid])   # fulfillment_status is a swept field
                    if fc.get("ok"):
                        # The fulfilment is genuinely gone, so the record must stop
                        # claiming otherwise: a stale fulfillment_id makes a later
                        # un-mark-made cancel a dead fulfilment and tell the operator
                        # to go and undo something that no longer exists.
                        def _undo_fulfilment(e):
                            e["fulfilled"] = False
                            e["notified"] = False
                            e.pop("fulfillment_id", None)
                            return e
                        try:
                            desk._update_dispatch(oid, _undo_fulfilment)
                        except desk.DispatchStoreUnwritable:
                            logger.exception("could not clear the fulfilment for order %s", oid)
                        note = ("The Shopify fulfillment was cancelled too; re-dispatching "
                                "will re-fulfill with the new tracking.")
                    else:
                        note = ("Shipment cancelled, but the Shopify fulfillment could not be undone ("
                                + (fc.get("detail") or "unknown reason")
                                + "). Cancel it in Shopify so the customer's tracking is not left dead.")
                except Exception:
                    logger.exception("fulfillment cancel failed for order %s", oid)
                    note = ("Shipment cancelled, but the Shopify fulfillment could not be undone. "
                            "Cancel it in Shopify so the customer's tracking is not left dead.")
            elif entry.get("fulfilled"):
                note = ("Shipment cancelled. The order is still marked fulfilled in Shopify; "
                        "cancel that fulfillment in Shopify so the tracking is not left dead.")
            # Put the order back in the queue it actually belongs to: an order that
            # was never made must return to production, not claim to be made.
            was_made = bool((production._load_prod_state().get(str(oid)) or {}).get("made_at"))
            try:
                await orderbook._sync_order_tags(registry, oid,
                                       add=(orderbook.MADE_TAG if was_made else production.PRODUCTION_TAG,),
                                       remove=(desk.DISPATCHED_TAG, *desk.LEGACY_DISPATCHED_TAGS))
            except Exception:
                logger.exception("tag revert after cancel failed for order %s", oid)
        return gate._json({"ok": True, "shipment": res, "note": note})
