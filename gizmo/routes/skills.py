"""The skills' routes: the list and its edits, and reading one skill. Gathered
from add_routes (stage 4 of the 14 October audit) where the first stood;
their paths are literal, so no request changes hands.
"""
import logging
import anthropic
from starlette.requests import Request
from gizmo import store as jsonstore
from gizmo import ai as claude

import copilot as core
from gizmo import activity
from gizmo import gate
from gizmo import team
from gizmo import skills as skillbook
from gizmo import bodies

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")



class SkillBody(bodies.Body):
    """What /api/skills reads (gizmo/bodies.py): a skill's words, when it
    applies, the file it came from, whether it always applies, and its id."""
    id: bodies.Id = None
    title: bodies.Text = None
    content: bodies.Text = None
    when: bodies.Text = None
    file: bodies.Text = None
    always: bodies.Flag = None


def register(mcp, registry):
    """Add the skills' routes to the app."""

    @mcp.custom_route("/api/skills", methods=["POST"])
    async def skills_route(request: Request):
        # Room for a skill at the master's limit from anyone: someone else
        # editing a long skill the master saved sends all of it back. What
        # may be SAVED is decided by the character limits below.
        err, body, who = await gate._guard(request, max_body=skillbook.SKILLS_BODY_MAX, cap=skillbook.SKILLS_BODY_MAX,
                                           model=SkillBody)
        if err:
            return err
        master = team._team_role(who) == "master"
        cap = skillbook.SKILL_UPLOAD_CAP if master else skillbook.SKILL_BODY_CAP
        op = body.get("op")
        # Skills run as instructions in every admin's chat, every report and
        # every email draft, so writing one is an admin's call (audit R-003).
        if op in ("add", "update", "delete") and team._team_level(who) < team.ROLE_LEVELS["admin"]:
            return gate._json({"error": "Only an admin can add, change or delete skills."}, 403)
        if op == "add" and body.get("file") and not master:
            return gate._json({"error": "Only the master account can upload skills from files. Write the skill here instead, "
                                   "or ask the master account to upload it."}, 403)
        skillbook._load_skills()
        if skillbook.SKILLS_PATH in jsonstore._poisoned_stores:
            return gate._json({"error": "Your saved skills could not be read, so nothing can be shown or changed "
                                   "until they are repaired. Tell Cameron."}, 503)
        try:
            if op == "add":
                skillbook._add_skill(body.get("title", ""), body.get("content", ""), body.get("when", ""), body.get("file", ""),
                           bool(body.get("always")), cap=cap)
                activity._track(who, "skills", "added a skill", str(body.get("title") or "")[:60])
            elif op == "update" and body.get("id"):
                skillbook._update_skill(body["id"], body.get("title", ""), body.get("content", ""),
                              body.get("when") if "when" in body else None,
                              bool(body.get("always")) if "always" in body else None, cap=cap)
                activity._track(who, "skills", "edited a skill", str(body.get("title") or "")[:60])
            elif op == "delete" and body.get("id"):
                skillbook._delete_skill(body["id"])
                activity._track(who, "skills", "deleted a skill")
        except ValueError as e:
            return gate._json({"error": str(e)}, 400)
        except Exception:
            logger.exception("Skills op failed")
            return gate._json({"error": "Your skills could not be saved. Try again, or tell Cameron if it keeps "
                                   "happening."}, 500)
        return skillbook._skills_answer(who)

    @mcp.custom_route("/api/skills/read", methods=["POST"])
    async def skills_read_route(request: Request):
        # Reactor reads one skill closely and says how it understands it: an
        # AI run, so it has its own door and spends the AI window there.
        # An admin's to run: the reading's rules and when-note go into every
        # account's answers, like the skill itself (found verifying R-003).
        err, body, who = await gate._guard(request, ai=True, min_level=team.ROLE_LEVELS["admin"])
        if err:
            return err
        skills = skillbook._load_skills()
        if skillbook.SKILLS_PATH in jsonstore._poisoned_stores:
            return gate._json({"error": "Your saved skills could not be read. Tell Cameron."}, 503)
        hit = next((x for x in skills if x.get("id") == str(body.get("id") or "")), None)
        if not hit:
            return gate._json({"error": "That skill no longer exists."}, 404)
        try:
            read_of = skillbook._skill_hash(hit.get("content") or "")    # the text read, not the text at save
            reading = await skillbook.run_skill_reading(hit, skills)
            skillbook._save_skill_reading(hit["id"], reading, who, read_of)
            activity._track(who, "skills", "had a skill read", str(hit.get("title") or "")[:60])
        except (RuntimeError, ValueError) as e:
            return gate._json({"error": str(e)}, 400 if isinstance(e, ValueError) else 500)
        except anthropic.APIError as e:
            logger.exception("Anthropic API error (skill read)")
            return gate._json({"error": claude._ai_error_words(e)}, 502)
        except Exception:
            logger.exception("Skill read failed")
            return gate._json({"error": "Reactor could not read this skill just now. Try again."}, 500)
        return skillbook._skills_answer(who)
