"""The scheduler's routes: the schedule and the change alerts. Gathered from
add_routes (stage 4 of the 14 October audit) where the first stood; their
paths are literal, so no request changes hands.
"""
import logging
from starlette.requests import Request

import copilot as core
from gizmo import activity
from gizmo import gate
from gizmo import team
from gizmo import scheduler

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


def register(mcp, registry):
    """Add the schedule and alert routes to the app."""

    @mcp.custom_route("/api/schedule", methods=["POST"])
    async def schedule_route(request: Request):
        # Get or set the automatic-refresh config (off by default).
        err, body, _who = await gate._guard(request)
        if err:
            return err
        try:
            if isinstance(body.get("config"), dict):
                if team._team_level(_who) < team.ROLE_LEVELS["admin"]:
                    return gate._json({"error": "Only an admin can change the schedule."}, 403)
                cfg = scheduler._save_schedule(body["config"])
                activity._track(_who, "settings", "changed the audit schedule")
                if cfg.get("enabled"):
                    scheduler._ensure_scheduler(registry)
            else:
                cfg = scheduler._load_schedule()
        except Exception:
            logger.exception("schedule op failed")
            return gate._json({"error": "The schedule could not be saved. Try again, or tell Cameron if it keeps happening."}, 500)
        return gate._json({"schedule": cfg})

    @mcp.custom_route("/api/alerts", methods=["POST"])
    async def alerts_route(request: Request):
        err, body, _who = await gate._guard(request)
        if err:
            return err
        op = body.get("op")
        try:
            if op == "dismiss" and body.get("id"):
                scheduler._update_alert(body["id"], "seen")
            elif op == "delete" and body.get("id"):
                scheduler._update_alert(body["id"], "delete")
            elif op == "clear":
                scheduler._write_alerts([])
        except Exception:
            logger.exception("alerts op failed")
            return gate._json({"error": "Couldn't update alerts."}, 500)
        return gate._json({"alerts": scheduler._load_alerts()})
