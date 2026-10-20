"""The store knowledge's routes: reading the store's site, and the knowledge
kept from it. Gathered from add_routes (stage 4 of the 14 October audit)
where the first stood; their paths are literal, so no request changes hands.
"""
import logging
import anthropic
from starlette.requests import Request
from gizmo import store as jsonstore
from gizmo import ai as claude

import copilot as core
from gizmo import knowledge
from gizmo import activity
from gizmo import gate
from gizmo import team

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


def register(mcp, registry):
    """Add the store knowledge's routes to the app."""

    @mcp.custom_route("/api/learn/run", methods=["POST"])
    async def learn_run_route(request: Request):
        # The one AI run on the Memory page, with a door of its own so the
        # paid window is spent by the door like every other paid route.
        err, _body, _who = await gate._guard(request, ai=True, min_level=team.ROLE_LEVELS["admin"])
        if err:
            return err
        try:
            return gate._json({"knowledge": await knowledge.run_learn(registry)})
        except RuntimeError as e:
            return gate._json({"error": str(e)}, 500)
        except anthropic.APIError as e:
            logger.exception("Anthropic API error (learn)")
            return gate._json({"error": claude._ai_error_words(e)}, 502)
        except Exception:
            logger.exception("Learn failed")
            return gate._json({"error": "Reactor could not learn the store this time. Try again, or tell "
                                   "Cameron if it keeps happening."}, 500)

    @mcp.custom_route("/api/learn", methods=["POST"])
    async def learn_route(request: Request):
        # Reading, correcting and deleting what was learned: no AI, so no
        # slot. The plain read took one on every boot, visit and chat answer,
        # and when the window was full the page showed the store as unlearned
        # and offered a paid re-learn over knowledge that was there all along.
        err, body, _who = await gate._guard(request)
        if err:
            return err
        op = body.get("op")
        if op == "learn":
            return gate._json({"error": "Reload the page, then press Learn again."}, 400)
        # Quoted as authoritative background into every answer: an admin's to change (audit R-003).
        if op in ("save", "delete") and team._team_level(_who) < team.ROLE_LEVELS["admin"]:
            return gate._json({"error": "Only an admin can change the store knowledge."}, 403)
        if op == "save":
            # A person correcting what was learned: it is quoted as authoritative
            # background into every answer, and the only fixes were Delete or
            # another paid re-learn that could repeat the mistake.
            text = str(body.get("knowledge") or "").strip()
            if not text:
                return gate._json({"error": "The store knowledge cannot be empty. Delete it instead."}, 400)
            if len(text) > knowledge.KNOWLEDGE_CAP:
                # Refused, not cut: a correction losing its end without a word.
                return gate._json({"error": f"The store knowledge is {len(text) - knowledge.KNOWLEDGE_CAP:,} characters over "
                                       f"its limit of {knowledge.KNOWLEDGE_CAP:,}. Shorten it and save again."}, 400)
            try:
                held = knowledge._load_knowledge()
                data = knowledge._save_knowledge(text, list(held.get("sources") or []))
                data["edited_at"] = data["learned_at"]
                data["learned_at"] = held.get("learned_at") or data["learned_at"]
                data["edited_by"] = team._team_name(_who) or ""
                if jsonstore._store_writable(knowledge.KNOWLEDGE_PATH):
                    jsonstore._write_json_store(knowledge.KNOWLEDGE_PATH, None, data)
                activity._track(_who, "memory", "edited the store knowledge")
                return gate._json({"knowledge": dict(data, cap=knowledge.KNOWLEDGE_CAP)})
            except Exception:
                logger.exception("Knowledge save failed")
                return gate._json({"error": "The store knowledge could not be saved. Try again."}, 500)
        if op == "delete":
            try:
                knowledge._delete_knowledge()
            except Exception:
                logger.exception("Knowledge delete failed")
                return gate._json({"error": "The store knowledge could not be deleted. Try again."}, 500)
            return gate._json({"knowledge": {}})
        return gate._json({"knowledge": dict(knowledge._load_knowledge() or {}, cap=knowledge.KNOWLEDGE_CAP)})
