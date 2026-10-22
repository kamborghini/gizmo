"""The layouts route, moved from add_routes (stage 4 of the 14 October audit)
where it stood.
"""
import logging
from starlette.requests import Request

from gizmo import layouts
from gizmo import gate
from gizmo import team
from gizmo import bodies

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")



class LayoutBody(bodies.Body):
    """What /api/layouts reads (gizmo/bodies.py): the screen, its cards' order and hidden ones, or a reset."""
    view: bodies.Text = None
    reset: bodies.Flag = None
    order: bodies.Items = None
    hidden: bodies.Items = None


def register(mcp, registry):
    """Add the layouts route to the app."""

    @mcp.custom_route("/api/layouts", methods=["POST"])
    async def layouts_route(request: Request):
        """The caller's own card layouts: {} reads them all, a view with an
        order and a hidden list saves that screen's, a view with reset true
        removes it. On no tab, like the profile: arranging the cards of a
        screen you can already open is not a permission of its own. The
        account is only ever the session the door returns, never a name in
        the body, so nobody can read or change another person's layout. Not
        tracked: arranging cards is not an event the team needs in its log."""
        err, body, who = await gate._guard(request, max_body=layouts.LAYOUT_MAX_BODY, cap=layouts.LAYOUT_MAX_BODY, model=LayoutBody)
        if err:
            return err
        if not who:
            return gate._json({"error": team.AUTH_REFUSALS["session"], "reason": "session"}, 401)
        # Any of these keys makes it a change, so a save that forgot its view
        # is told so instead of quietly answered with a read.
        if not any(k in body for k in ("view", "order", "hidden", "reset")):
            return gate._json({"layouts": layouts._layouts_for(who)})
        problem, view, layout = layouts._clean_layout_change(body)
        if problem:
            return gate._json({"error": problem}, 400)
        try:
            async with layouts._layouts_lock:
                mine = layouts._save_layout(who, view, layout)
        except Exception:
            logger.exception("Layout save failed")
            return gate._json({"error": "The layout could not be saved. Try again, or tell Cameron if it keeps happening."}, 500)
        return gate._json({"layouts": mine})
