"""The chat's routes: a chat turn, the same turn streamed step by step, and the
usage panel's figures. Gathered from add_routes (stage 4 of the 14 October
audit) where the first stood, once add_routes handed the chat module its
tools; their paths are literal, so no request changes hands.
"""
import logging
import json
import asyncio
import anthropic
from starlette.requests import Request
from starlette.responses import StreamingResponse
from gizmo import ai as claude

import copilot as core
from gizmo import chat as assistant
from gizmo import gate
from gizmo import knowledge
from gizmo import memory
from gizmo import skills as skillbook
from gizmo import profile as store_profile
from gizmo import team
from gizmo import bodies

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")



class ChatBody(bodies.Body):
    """What /api/chat and /api/chat/stream read (gizmo/bodies.py): the conversation so far (or one message), the Deep switch and the skills picked."""
    messages: bodies.Records = None
    message: bodies.Text = None
    deep: bodies.Flag = None
    skills: bodies.Items = None



class UsageBody(bodies.Body):
    """What /api/usage reads (gizmo/bodies.py): how many days."""
    days: bodies.Whole = None


def register(mcp, registry):
    """Add the chat's routes to the app."""

    @mcp.custom_route("/api/chat", methods=["POST"])
    async def chat(request: Request):
        err, body, _who = await gate._guard(request, ai=True, model=ChatBody)
        if err:
            return err

        history = body.get("messages")
        if not history and body.get("message"):
            history = [{"role": "user", "content": body["message"]}]
        if not history:
            return gate._json({"error": "Provide 'messages' or 'message'"}, 400)
        if not isinstance(history, list) or len(history) > assistant.MAX_MESSAGES:
            return gate._json({"error": "Conversation too long. Start a new chat."}, 400)
        if len(json.dumps(history)) > assistant.MAX_CHAT_CHARS:
            return gate._json({"error": "Message too large."}, 413)

        deep = bool(body.get("deep"))
        model = claude._pick_model(deep)
        extra = (store_profile._profile_to_system(store_profile._load_profile()) + memory._memory_to_system() + knowledge._knowledge_to_system()
                 + skillbook._skills_to_system(assistant._chat_question(history), assistant._picked_skills(body), can_read=True))
        try:
            result = await assistant.run_chat(history, assistant.dispatch_for(_who), assistant._chat_tools, model, extra,
                                    effort=claude._effort_for(model, deep), deep=deep)
        except RuntimeError as e:
            return gate._json({"error": str(e)}, 500)
        except anthropic.APIError as e:
            logger.exception("Anthropic API error")
            return gate._json({"error": claude._ai_error_words(e)}, 502)
        assistant._chat_after(result, history, held=team._team_level(_who) < team.ROLE_LEVELS["admin"], by=team._team_name(_who))
        result["deep"] = deep
        return gate._json(result)

    @mcp.custom_route("/api/chat/stream", methods=["POST"])
    async def chat_stream(request: Request):
        """Server-sent-events variant of /api/chat: emits real tool-step progress as
        the model works, then a final structured result. The client falls back to
        /api/chat if streaming is unavailable."""
        # Authorised BEFORE the AI window is touched: the global AI ceiling is
        # the app's most expensive shared resource, and a caller with no
        # session was spending a slot from it on the way to a 401.
        err, body, _who = await gate._guard(request, ai=True, model=ChatBody)
        if err:
            return err
        history = body.get("messages")
        if not history and body.get("message"):
            history = [{"role": "user", "content": body["message"]}]
        if not history:
            return gate._json({"error": "Provide 'messages' or 'message'"}, 400)
        if not isinstance(history, list) or len(history) > assistant.MAX_MESSAGES:
            return gate._json({"error": "Conversation too long. Start a new chat."}, 400)
        if len(json.dumps(history)) > assistant.MAX_CHAT_CHARS:
            return gate._json({"error": "Message too large."}, 413)

        deep = bool(body.get("deep"))
        model = claude._pick_model(deep)
        extra = (store_profile._profile_to_system(store_profile._load_profile()) + memory._memory_to_system() + knowledge._knowledge_to_system()
                 + skillbook._skills_to_system(assistant._chat_question(history), assistant._picked_skills(body), can_read=True))

        q: asyncio.Queue = asyncio.Queue()

        async def runner():
            try:
                result = await assistant.run_chat(history, assistant.dispatch_for(_who), assistant._chat_tools, model, extra,
                                        emit=q.put, effort=claude._effort_for(model, deep), deep=deep)
                assistant._chat_after(result, history, held=team._team_level(_who) < team.ROLE_LEVELS["admin"],
                            by=team._team_name(_who))
                result["deep"] = deep
                await q.put({"type": "done", "result": result})
            except anthropic.APIError as e:
                logger.exception("Anthropic API error (stream)")
                await q.put({"type": "error", "error": claude._ai_error_words(e)})
            except RuntimeError as e:
                await q.put({"type": "error", "error": str(e)})
            except Exception:
                logger.exception("Chat stream failed")
                await q.put({"type": "error", "error": "Something went wrong. Please try again."})

        async def gen():
            task = asyncio.create_task(runner())
            try:
                # Said at once: the run is under way and being paid for. A page
                # that heard nothing may ask /api/chat instead, and before this
                # an answer with no tool steps was silent until it was done, so
                # one cut off mid-answer was run and billed a second time.
                yield 'data: {"type": "start"}\n\n'
                while True:
                    ev = await q.get()
                    yield "data: " + json.dumps(ev) + "\n\n"
                    if ev.get("type") in ("done", "error"):
                        break
            finally:
                if not task.done():
                    task.cancel()

        headers = {**gate._API_HEADERS, "Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"}
        return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)

    @mcp.custom_route("/api/usage", methods=["POST"])
    async def usage_route(request: Request):
        # AI token usage + estimated cost (measurement, no AI).
        err, _body, _who = await gate._guard(request, body=False)
        if err:
            return err
        body = await gate._read_json_capped(request)
        refused = gate._body_refusal(UsageBody, body)
        if refused:
            return refused
        days = 30
        if isinstance(body, dict):
            try:
                days = max(1, min(365, int(body.get("days", 30))))
            except (TypeError, ValueError):
                days = 30
        return gate._json({"usage": assistant._usage_summary(days)})
