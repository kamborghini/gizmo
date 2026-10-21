"""The Liability routes: the report and marking an account chased. Gathered
from add_routes (stage 4 of the 14 October audit) where the first stood;
their paths are literal, so no request changes hands.
"""
import logging
from starlette.requests import Request

import copilot as core
from gizmo import liability
from gizmo import activity
from gizmo import gate
from gizmo import orderbook
from gizmo import bodies

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")



class ChaseBody(bodies.Body):
    """What /api/liability/chase reads (gizmo/bodies.py): the account chased."""
    key: bodies.Text = None



class LiabilityBody(bodies.Body):
    """What /api/liability reads (gizmo/bodies.py): whether to read afresh."""
    fresh: bodies.Flag = None


def register(mcp, registry):
    """Add the Liability routes to the app."""

    @mcp.custom_route("/api/liability", methods=["POST"])
    async def liability_route(request: Request):
        # Accounts receivable overview. Shopify read, no AI.
        err, body, _who = await gate._guard(request, model=LiabilityBody)
        if err:
            return err
        try:
            orderbook._refresh_asked(body)
            res = await liability.run_liability(registry)
            return gate._json(res, 502 if res.get("error") else 200)
        except Exception:
            logger.exception("Liability failed")
            return gate._json({"error": "Couldn't build the liability view."}, 500)

    @mcp.custom_route("/api/liability/chase", methods=["POST"])
    async def liability_chase_route(request: Request):
        """Stamp an account as chased today. Local state only: the merchant's
        own mail client sends the email, so this records the fact, not the act."""
        err, body, who = await gate._guard(request, model=ChaseBody)
        if err:
            return err
        key = str(body.get("key") or "").strip()[:120]
        if not key:
            return gate._json({"error": "No account given."}, 400)
        try:
            entry = liability._mark_chased(key, by=str(who or ""))
            activity._track(who, "chase", "marked an account chased", key[:60])
            return gate._json({"ok": True, "key": key, "chased": entry})
        except Exception:
            logger.exception("chase stamp failed")
            return gate._json({"error": "The chase could not be recorded. The data volume may be "
                                   "unwritable; check Settings, Connections."}, 500)
