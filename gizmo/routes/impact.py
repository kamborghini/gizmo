"""The impact route, moved from add_routes (stage 4 of the 14 October audit)
where it stood.
"""
import logging
import time
import secrets
from starlette.requests import Request

import copilot as core
from gizmo import impact
from gizmo import gate
from gizmo import memory
from gizmo import team
from gizmo import bodies

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")



class ImpactBody(bodies.Body):
    """What /api/impact reads (gizmo/bodies.py): the change to track, or one
    tracked change's id."""
    text: bodies.Text = None
    source: bodies.Text = None
    id: bodies.Id = None


def register(mcp, registry):
    """Add the impact route to the app."""

    @mcp.custom_route("/api/impact", methods=["POST"])
    async def impact_route(request: Request):
        err, body, who = await gate._guard(request, model=ImpactBody)
        if err:
            return err
        op = body.get("op") or "list"
        try:
            # Snapshots take seconds; take them BEFORE loading the list so the
            # load-mutate-write has no await inside it to lose concurrent changes.
            snap = cur = None
            out_held = False
            if op == "add":
                if not (body.get("text") or "").strip():
                    return gate._json({"error": "Nothing to track."}, 400)
                # Pressed twice, or from an answer drawn again: the change
                # already being tracked is the answer, not a second copy.
                want = (body.get("text") or "").strip()[:300]
                twin = next((x for x in impact._load_impact() if x.get("text") == want and x.get("status") != "concluded"), None)
                if twin:
                    return gate._json({"item": twin, "already": True})
                snap = await impact._impact_snapshot(registry)
            elif op == "conclude" and body.get("id"):
                cur = await impact._impact_snapshot(registry)
            items = impact._load_impact()
            if op == "add":
                text = (body.get("text") or "").strip()[:300]
                if not text:
                    return gate._json({"error": "Nothing to track."}, 400)
                added = {"id": secrets.token_hex(5), "text": text,
                         "source": str(body.get("source") or "copilot")[:24],
                         "baseline": snap, "started_at": snap["at"], "status": "tracking",
                         "by_uid": str(who or ""), "by": team._team_name(who) if who else ""}
                items.insert(0, added)
                items = impact._write_impact(items)
                return gate._json({"item": added, "impact": impact._impact_with_deltas(items, snap), "current": snap})
            elif op in ("delete", "conclude") and body.get("id"):
                # Yours, or an admin's to settle: a member could otherwise
                # drop an admin's change, or conclude it into a note that
                # waits, where the admin's own Conclude could no longer reach.
                mine = next((x for x in items if x.get("id") == body["id"]), None)
                if mine is not None and team._team_level(who) < team.ROLE_LEVELS["admin"] \
                        and not (mine.get("by_uid") and mine.get("by_uid") == str(who or "")):
                    return gate._json({"error": "Only an admin or the person who tracked it can change that."}, 403)
            if op == "delete" and body.get("id"):
                items = impact._write_impact([x for x in items if x.get("id") != body["id"]])
            elif op == "conclude" and body.get("id"):
                for x in items:
                    if x.get("id") == body["id"] and x.get("status") != "concluded":
                        x["status"] = "concluded"
                        x["concluded_at"] = cur["at"]
                        x["final"] = cur
                        try:
                            # The learning quotes the change's own words, so
                            # it waits for an admin when a member wrote them
                            # or concluded it; a change from before anyone
                            # was recorded waits too (R-003).
                            tracker = str(x.get("by_uid") or "")
                            held = (team._team_level(who) < team.ROLE_LEVELS["admin"]
                                    or not tracker or team._team_level(tracker) < team.ROLE_LEVELS["admin"])
                            memory._add_memories([{"type": "insight", "text": impact._impact_learning_text(x, cur)}],
                                          source="tracked change", held=held,
                                          by=(x.get("by") or team._team_name(who) or "a tracked change") if held else "")
                            if held:
                                out_held = True
                        except Exception:
                            logger.exception("impact learning capture failed")
                items = impact._write_impact(items)
        except Exception:
            logger.exception("Impact op failed")
            return gate._json({"error": "Tracked changes could not be updated. Try again, or tell Cameron if it keeps happening."}, 500)
        # Nothing tracked needs no figures: the list read took a fresh 28-day
        # Shopify (and Google) snapshot on every Memory visit and after every
        # chat answer. Figures read in the last five minutes are reused.
        if not items:
            return gate._json({"impact": [], "current": {}, "held": out_held})
        now = time.monotonic()
        if op == "list" and impact._impact_snap_cache.get("snap") and now - impact._impact_snap_cache.get("t", 0) < 300:
            current = impact._impact_snap_cache["snap"]
        else:
            current = cur or snap or await impact._impact_snapshot(registry)
            impact._impact_snap_cache.update({"t": now, "snap": current})
        return gate._json({"impact": impact._impact_with_deltas(items, current), "current": current, "held": out_held})
