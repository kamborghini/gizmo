"""The scheduler's routes: the alerts. Gathered from
add_routes (stage 4 of the 14 October audit) where the first stood; their
paths are literal, so no request changes hands.
"""
import logging
from starlette.requests import Request

from gizmo import gate
from gizmo import scheduler
from gizmo import bodies

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")



class AlertBody(bodies.Body):
    """What /api/alerts reads (gizmo/bodies.py): the alert to dismiss or delete."""
    id: bodies.Id = None



def register(mcp, registry):
    """Add the alert routes to the app."""

    @mcp.custom_route("/api/alerts", methods=["POST"])
    async def alerts_route(request: Request):
        err, body, _who = await gate._guard(request, model=AlertBody)
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
