"""The store profile's route, moved from add_routes (stage 4 of the 14 October
audit) where it stood.
"""
import logging
from starlette.requests import Request

from gizmo import activity
from gizmo import gate
from gizmo import team
from gizmo import profile as store_profile
from gizmo import bodies

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")



class ProfileBody(bodies.Body):
    """What /api/profile reads (gizmo/bodies.py): a person's preferences, or the store profile."""
    prefs: bodies.Fields = None
    profile: bodies.Fields = None


def register(mcp, registry):
    """Add the store profile's route to the app."""

    @mcp.custom_route("/api/profile", methods=["POST"])
    async def profile_route(request: Request):
        err, body, _who = await gate._guard(request, model=ProfileBody)
        if err:
            return err
        # The switches alone, merged into the profile as the server holds it.
        # A switch used to post the page's copy of the whole profile, so one
        # click from a tab whose read had failed, or that another admin had
        # saved past, wrote its stale or empty text over the stored text.
        if isinstance(body.get("prefs"), dict) and not isinstance(body.get("profile"), dict):
            if team._team_level(_who) < team.ROLE_LEVELS["admin"]:
                return gate._json({"error": "Only an admin can change the store profile."}, 403)
            try:
                held = store_profile._load_profile()
                prefs = {**(held.get("prefs") if isinstance(held.get("prefs"), dict) else {}),
                         **{k: v for k, v in body["prefs"].items()
                            if k in ("track_inventory", "concise", "proactive", "flag_anomalies")}}
                saved = store_profile._save_profile({**held, "prefs": prefs})
                activity._track(_who, "settings", "changed a store preference")
                return gate._json({"profile": saved})
            except Exception:
                logger.exception("Preference save failed")
                return gate._json({"error": "The setting could not be saved. Try again, or tell Cameron if it keeps happening."}, 500)
        # Save when a profile object is supplied; otherwise just load.
        if isinstance(body.get("profile"), dict):
            if team._team_level(_who) < team.ROLE_LEVELS["admin"]:
                return gate._json({"error": "Only an admin can change the store profile."}, 403)
            try:
                saved = store_profile._save_profile(body["profile"])
                activity._track(_who, "settings", "changed the store profile")
                return gate._json({"profile": saved})
            except Exception:
                logger.exception("Profile save failed")
                return gate._json({"error": "The profile could not be saved. Try again, or tell Cameron if it keeps happening."}, 500)
        return gate._json({"profile": store_profile._load_profile()})
