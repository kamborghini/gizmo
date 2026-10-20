"""The loan register's route, moved from add_routes (stage 4 of the 14 October
audit) where it stood.
"""
import logging
import re
from datetime import datetime, timezone
from starlette.requests import Request

import copilot as core
from gizmo import loans
from gizmo import activity
from gizmo import gate
from gizmo import team

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


def register(mcp, registry):
    """Add the loan register's route to the app."""

    @mcp.custom_route("/api/loans", methods=["POST"])
    async def loans_route(request: Request):
        """Loan projectors: the register of what the shop owns, and where each
        one is. Lending and receiving is the bench's daily job; the register
        itself is an admin's, because it is an asset list."""
        err, body, who = await gate._guard(request)
        if err:
            return err
        op = str(body.get("op") or "board")
        admin = team._team_level(who) >= team.ROLE_LEVELS["admin"]
        keeper = gate._json({"error": "Only an admin can change the unit register."}, 403)
        d = loans._load_loans()

        if op == "board":
            return gate._json(loans._loans_board(d, who))
        if op == "history":
            return gate._json({"history": loans._loan_history(d, str(body.get("unit_id") or ""))})
        if op == "products":
            q = " ".join(str(body.get("q") or "").split()).lower()
            try:
                rows = await loans._loan_product_rows(registry)
            except Exception:
                logger.exception("loans: the catalogue could not be read")
                return gate._json({"error": "Could not read the shop's products just now. "
                                       "You can still type the model in by hand."}, 502)
            if q:
                rows = [r for r in rows if q in r["title"].lower()
                        or q in r["sku"].lower() or q in r["vendor"].lower()]
            return gate._json({"products": rows[:20]})

        if op == "unit_save":
            if not admin:
                return keeper
            name = " ".join(str(body.get("name") or "").split())[:80]
            if not name:
                return gate._json({"error": "Give the unit a name, for example Loan 3."}, 400)
            uid = str(body.get("unit_id") or "")
            u = (d["units"].get(uid) or {}) if uid else {}
            if uid and not u:
                return gate._json({"error": "That unit is no longer in the register."}, 404)
            if not uid:
                uid = loans._loan_id(d, "u")
                u = {"created_at": datetime.now(timezone.utc).isoformat()}
            u.update({"name": name,
                      "model": " ".join(str(body.get("model") or "").split())[:120],
                      "serial": " ".join(str(body.get("serial") or "").split())[:60],
                      "notes": str(body.get("notes") or "").strip()[:400]})
            # What it was picked from, when it was picked from the shop. The
            # NAME still identifies which one: two units can be the same
            # product, and only the name and serial tell them apart.
            for k in ("product_id", "variant_id", "sku"):
                if k in body:
                    u[k] = " ".join(str(body.get(k) or "").split())[:60]
            # asset_tag is deliberately NOT in that list. It is printed on a
            # sticker stuck to the machine; a tag that could be edited here
            # would make the register lie about the metal in front of you.
            if "retired" in body:
                u["retired"] = bool(body.get("retired"))
            d["units"][uid] = u
            loans._write_loans(d)
            activity._track(who, "loans", "saved a loan unit", name)
            return gate._json({"ok": True, "unit": dict(u, id=uid)})

        if op == "sticker":
            uid = str(body.get("unit_id") or "")
            u = d["units"].get(uid)
            if not u:
                return gate._json({"error": "That unit is no longer in the register."}, 404)
            tag = str(u.get("asset_tag") or "")
            # MINTING is a change to the register and so an admin's: the number
            # goes on the metal and never comes off. A REPRINT is not a change
            # at all - it redraws a number that is already the truth - and the
            # person who needs one is whoever is holding a projector with a
            # peeling label, not whoever happens to be at a desk. Gating both
            # behind admin was one rule doing two jobs.
            if not tag and not admin:
                return gate._json({"error": "That unit has no asset tag yet, and assigning one "
                                       "is an admin's. Ask for it to be tagged, then "
                                       "anyone can reprint the sticker."}, 403)
            if not tag:
                tag = loans._loan_mint_tag(d)
                u["asset_tag"] = tag
                d["units"][uid] = u
                loans._write_loans(d)
                activity._track(who, "loans", "minted an asset tag", tag + " for " + (u.get("name") or ""))
            try:
                codes = loans._loan_codes(tag)
            except Exception:
                logger.exception("loans: could not draw the sticker codes")
                # The tag is minted and saved either way: it is the number on
                # the register now, and a drawing failure must not leave the
                # unit tagless on a retry with a different number.
                return gate._json({"error": "The tag is " + tag + ", but its codes could not be "
                                       "drawn just now. Try printing again."}, 502)
            return gate._json({"ok": True, "tag": tag, "qr": codes["qr"],
                          "barcode": codes["barcode"],
                          "unit": {"id": uid, "name": u.get("name") or "",
                                   "model": u.get("model") or "",
                                   "serial": u.get("serial") or "",
                                   "sku": u.get("sku") or ""}})

        if op == "unit_retire":
            if not admin:
                return keeper
            uid = str(body.get("unit_id") or "")
            u = d["units"].get(uid)
            if not u:
                return gate._json({"error": "That unit is no longer in the register."}, 404)
            # Retiring a unit that is with a customer would lose the only
            # record of where a projector went.
            if any(not lo.get("back_at") and str(lo.get("unit_id")) == uid
                   for lo in d["loans"].values()):
                return gate._json({"error": "That one is out with someone. Book it back in first."}, 400)
            u["retired"] = not bool(body.get("unretire"))
            d["units"][uid] = u
            loans._write_loans(d)
            activity._track(who, "loans", "retired a loan unit" if u["retired"] else "returned a unit to the register",
                   u.get("name") or "")
            return gate._json({"ok": True})

        if op == "unit_delete":
            if not admin:
                return keeper
            uid = str(body.get("unit_id") or "")
            u = d["units"].get(uid)
            if not u:
                return gate._json({"error": "That unit is no longer in the register."}, 404)
            # Retiring keeps the history; deleting is the other thing, and it is
            # the whole thing. A unit still out with someone goes too, because
            # the person at the keyboard can see that on the row and asked
            # anyway - but the audit line says what went with it, so the fact
            # that a projector was at a customer survives the register.
            gone = [lid for lid, lo in d["loans"].items()
                    if str(lo.get("unit_id")) == uid]
            open_with = next((lo.get("who_name") or "someone" for lo in d["loans"].values()
                              if str(lo.get("unit_id")) == uid and not lo.get("back_at")), "")
            for lid in gone:
                d["loans"].pop(lid, None)
            d["units"].pop(uid, None)
            loans._write_loans(d)
            activity._track(who, "loans", "deleted a loan unit",
                   (u.get("name") or "") + (" [" + str(u.get("asset_tag")) + "]"
                                            if u.get("asset_tag") else "")
                   + " with " + str(len(gone)) + " loan record(s)"
                   + (", was out with " + open_with if open_with else ""))
            return gate._json({"ok": True, "loans_removed": len(gone)})

        if op == "out":
            uid = str(body.get("unit_id") or "")
            u = d["units"].get(uid)
            if not u:
                return gate._json({"error": "Pick a unit from the register."}, 400)
            if u.get("retired"):
                return gate._json({"error": "That unit is retired. Put it back in the register first."}, 400)
            open_now = next((lo for lo in d["loans"].values()
                             if str(lo.get("unit_id")) == uid and not lo.get("back_at")), None)
            if open_now:
                return gate._json({"error": "That unit is already out with "
                                       + (open_now.get("who_name") or "someone")
                                       + ". Book it back in first."}, 400)
            who_name = " ".join(str(body.get("who_name") or "").split())[:120]
            if not who_name:
                return gate._json({"error": "Say who it is going to."}, 400)
            due = str(body.get("due_at") or "").strip()[:10]
            if due and not re.match(r"^\d{4}-\d{2}-\d{2}$", due):
                return gate._json({"error": "The due date needs to be a date."}, 400)
            lid = loans._loan_id(d, "l")
            d["loans"][lid] = {
                "unit_id": uid, "who_name": who_name,
                "crm_person_id": str(body.get("crm_person_id") or "")[:40],
                "crm_org_id": str(body.get("crm_org_id") or "")[:40],
                "phone": " ".join(str(body.get("phone") or "").split())[:40],
                "note": str(body.get("note") or "").strip()[:400],
                "due_at": due, "out_at": datetime.now(timezone.utc).isoformat(),
                "out_by": who, "back_at": "", "back_by": ""}
            loans._write_loans(d)
            activity._track(who, "loans", "loaned out a unit",
                   (u.get("name") or "") + " to " + who_name)
            return gate._json({"ok": True, "loan": dict(d["loans"][lid], id=lid)})

        if op == "back":
            lid = str(body.get("loan_id") or "")
            lo = d["loans"].get(lid)
            if not lo:
                return gate._json({"error": "That loan is not on the board."}, 404)
            if lo.get("back_at"):
                return gate._json({"error": "That one is already booked back in."}, 400)
            lo["back_at"] = datetime.now(timezone.utc).isoformat()
            lo["back_by"] = who
            if body.get("note"):
                lo["note"] = (str(lo.get("note") or "") + "\n" + str(body.get("note"))).strip()[:400]
            loans._write_loans(d)
            activity._track(who, "loans", "booked a unit back in",
                   (d["units"].get(str(lo.get("unit_id")), {}).get("name") or ""))
            return gate._json({"ok": True})

        if op == "settings":
            if not admin:
                return keeper
            try:
                days = int(body.get("chase_days"))
            except (TypeError, ValueError):
                return gate._json({"error": "The chase threshold is a number of days."}, 400)
            if not 1 <= days <= 365:
                return gate._json({"error": "Pick between 1 and 365 days."}, 400)
            d.setdefault("settings", {})["chase_days"] = days
            loans._write_loans(d)
            activity._track(who, "loans", "changed the loan chase threshold", str(days) + " days")
            return gate._json({"ok": True, "settings": d["settings"]})

        return gate._json({"error": "Unknown op."}, 400)
