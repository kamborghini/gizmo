"""The memory route, moved from add_routes (stage 4 of the 14 October audit)
where it stood.
"""
import logging
from starlette.requests import Request
from gizmo import store as jsonstore

import copilot as core
from gizmo import memory
from gizmo import activity
from gizmo import gate
from gizmo import team

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


def register(mcp, registry):
    """Add the memory route to the app."""

    @mcp.custom_route("/api/memory", methods=["POST"])
    async def memory_route(request: Request):
        err, body, who = await gate._guard(request)
        if err:
            return err
        op = body.get("op")
        # A file that could not be read loads as empty, and a write to it is
        # held back to protect it: answering as usual showed 'No notes yet'
        # and let an add look saved when it was not. Say so instead.
        memory._load_memory()
        if memory.MEMORY_PATH in jsonstore._poisoned_stores:
            return gate._json({"error": "Your saved notes could not be read, so nothing can be shown or changed "
                                   "until they are repaired. Tell Cameron."}, 503)
        out: dict = {}
        # Notes are read into every answer and report for every account, so
        # adding, correcting and deleting them is an admin's call. Marking a
        # follow-up done changes no words, and stays open (audit R-003).
        if op in ("add", "update", "delete") and team._team_level(who) < team.ROLE_LEVELS["admin"]:
            return gate._json({"error": "Only an admin can add, correct or delete notes."}, 403)
        try:
            if op == "add" and isinstance(body.get("items"), list):
                refused: list = []
                memory._add_memories(body["items"], refused=refused)
                if refused:
                    out["not_kept"] = [r["text"] for r in refused]
                activity._track(who, "memory", "added to memory", str(len(body["items"])) + " item(s)")
            elif op == "set_status" and body.get("id"):
                status = str(body.get("status") or "done")
                if team._team_level(who) < team.ROLE_LEVELS["admin"]:
                    # Dismissing takes a note out of every answer, and keeping
                    # or reopening one puts it in (audit R-003).
                    note = next((m for m in memory._load_memory() if m.get("id") == str(body["id"])), None)
                    if not memory._member_may_set(note, status):
                        return gate._json({"error": "Only an admin can change that note."}, 403)
                was = next((m.get("status") for m in memory._load_memory() if m.get("id") == str(body["id"])), None)
                memory._update_memory(body["id"], status)
                activity._track(who, "memory", "kept a note waiting for an admin" if was == "pending" and status == "open"
                       else "changed a memory's status", status)
            elif op == "update" and body.get("id"):
                try:
                    memory._edit_memory(body["id"], body.get("text", ""), body.get("type", ""))
                except ValueError as e:
                    if str(e) == "instruction":
                        return gate._json({"error": "That reads like an instruction, and notes are kept to facts "
                                               "about the business. Save it as a skill instead.",
                                      "as_skill": True}, 400)
                    return gate._json({"error": str(e)}, 400)
                activity._track(who, "memory", "edited a note")
            elif op == "delete" and body.get("id"):
                memory._delete_memory(body["id"])
                activity._track(who, "memory", "deleted a memory")
        except Exception:
            logger.exception("Memory op failed")
            return gate._json({"error": "Your notes could not be saved. Try again, or tell Cameron if it keeps "
                                   "happening."}, 500)
        return gate._json({"memories": memory._load_memory(), "inject": memory.MEMORY_INJECT, **out})
