"""The AI client: which Claude model and how much effort, the client, the call
and its fallbacks, the usage record, the daily spend cap, failure notes, and
the dash filter every model answer passes through. Moved out of copilot.py
(stage 4 of the 14 October audit); part of the floor, so it imports nothing
above it. Read as `claude.NAME` (`ai` and `store` are local names in copilot.py).
"""
import logging
import os
import re
import json
import time
import base64
import types
import asyncio
from datetime import datetime, timezone
import contextvars
from typing import Any, Optional
import anthropic
import perf

from gizmo import errors
from gizmo import store as jsonstore
from gizmo.config import _env_num

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
# Model tiers. Claude Opus 5.5 everywhere by default; the env vars let a
# cheaper tier (e.g. claude-sonnet-5-5) take everyday chat without a code change.
MODEL_FAST = os.environ.get("ANTHROPIC_MODEL_FAST") or os.environ.get("ANTHROPIC_MODEL") or "claude-opus-5-5"
MODEL_DEEP = os.environ.get("ANTHROPIC_MODEL_DEEP", "claude-opus-5-5")
# Asked once, with the same request, when the model above fails at Anthropic
# (unavailable to the account, overloaded, limited, or refusing the request),
# so a question is answered and says so rather than failing. "off" disables.
MODEL_FALLBACK = os.environ.get("ANTHROPIC_MODEL_FALLBACK", "claude-opus-4-8")
MAX_TOKENS         = _env_num(int, os.environ.get("COPILOT_MAX_TOKENS", "16000"), "16000", "COPILOT_MAX_TOKENS")  # headroom for rich output at high effort (non-streaming-safe)
USAGE_PATH         = os.environ.get("USAGE_PATH", "/data/usage.json")          # AI token-usage + cost log (measurement)
USAGE_MAX          = _env_num(int, os.environ.get("USAGE_MAX", "5000"), "5000", "USAGE_MAX")                  # max usage events retained
DAILY_COST_CAP     = _env_num(float, os.environ.get("DAILY_COST_CAP", "25"), "25", "DAILY_COST_CAP")             # hard $/day AI ceiling (0 disables)
# Anthropic list prices, $ per 1M tokens (input, output). Cache write 1.25x input;
# cache read 0.1x input unless _CACHE_READ_RATE says otherwise.
_MODEL_PRICE = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
_CACHE_READ_RATE = {"claude-opus-5-5": 0.05}

def _pick_model(deep: bool) -> str:
    """The Deep-analysis toggle is authoritative: on → deep model, off → fast
    model. Both are Opus 5.5 unless a setting says otherwise, and then the
    toggle is the effort (see _effort_for)."""
    return MODEL_DEEP if deep else MODEL_FAST


def _cap_effort(model: str, eff: str) -> str:
    """The cautious rule, for when the Models API cannot be asked: xhigh and
    max only on a model named Opus."""
    if "opus" not in (model or "").lower() and eff in ("max", "xhigh"):
        return "high"
    return eff


# What each model accepts, from Anthropic's Models API, read once per model.
# A hand-kept list of which model takes which effort went stale: it capped
# every non-Opus model at high, so a Sonnet 5.5 Deep run was cut short, while
# letting xhigh through to Opus 4.6, which has max but not xhigh, and sending
# Haiku 4.5 an effort and adaptive thinking, neither of which it takes.
_EFFORT_LADDER = ("low", "medium", "high", "xhigh", "max")
_MODEL_CAPS: dict = {}            # model -> (asked_at, caps or None)
_MODEL_CAPS_RETRY = 600.0         # a failed read is asked again after this


async def _model_caps(client, model: str):
    """{"efforts": (levels it takes, low to max), "adaptive": bool}, or None
    when the Models API could not be asked (then the cautious rule applies)."""
    now = time.monotonic()
    hit = _MODEL_CAPS.get(model)
    if hit and (hit[1] is not None or now - hit[0] < _MODEL_CAPS_RETRY):
        return hit[1]
    caps = None
    try:
        info = await client.models.retrieve(model)
        c = info.capabilities
        c = c.model_dump() if hasattr(c, "model_dump") else dict(c or {})
        # The API may answer with no capabilities at all (the field is
        # nullable). That says nothing about the model, so it is unknown,
        # asked again later, never "takes nothing": that reading would strip
        # effort and thinking from every request on it until a restart.
        if not isinstance(c.get("effort"), dict) or not isinstance(c.get("thinking"), dict):
            raise ValueError("the answer named no effort or thinking capabilities")
        eff = c["effort"]
        caps = {"efforts": tuple(lvl for lvl in _EFFORT_LADDER
                                 if eff.get("supported") and (eff.get(lvl) or {}).get("supported")),
                "adaptive": bool(((c["thinking"].get("types") or {})
                                  .get("adaptive") or {}).get("supported"))}
    except Exception as e:
        logger.info("model capabilities for %s unavailable (%s); using the cautious effort rule",
                    model, type(e).__name__)
    _MODEL_CAPS[model] = (now, caps)
    return caps


def _fit_effort(caps, model: str, eff: str):
    """The effort to send: as asked if the model takes it, else the nearest
    level below that it does, or none at all for a model that takes none."""
    if caps is None:
        return _cap_effort(model, eff)
    have = caps["efforts"]
    if not have:
        return None
    if eff in have:
        return eff
    want = _EFFORT_LADDER.index(eff) if eff in _EFFORT_LADDER else _EFFORT_LADDER.index("high")
    below = [lvl for lvl in have if _EFFORT_LADDER.index(lvl) <= want]
    return below[-1] if below else have[0]


async def _fit_to_model(client, kwargs: dict) -> dict:
    """kwargs as its model will accept them: the effort fitted, and adaptive
    thinking dropped for a model without it. A new dict only when something
    changes, so the caller's own request is never altered under it."""
    oc = kwargs.get("output_config")
    effort = oc.get("effort") if isinstance(oc, dict) else None
    adaptive = (kwargs.get("thinking") or {}).get("type") == "adaptive"
    if not effort and not adaptive:
        return kwargs
    model = str(kwargs.get("model") or "")
    caps = await _model_caps(client, model)
    out = kwargs
    if effort:
        fitted = _fit_effort(caps, model, effort)
        if fitted != effort:
            rest = {k: v for k, v in oc.items() if k != "effort"}
            out = dict(kwargs)
            if fitted:
                out["output_config"] = {**rest, "effort": fitted}
            elif rest:
                out["output_config"] = rest
            else:
                out.pop("output_config")
    if adaptive and caps is not None and not caps["adaptive"]:
        out = dict(out) if out is kwargs else out
        out.pop("thinking")
    return out


# ---------------------------------------------------------------------------
# Claude tool-use loop
# ---------------------------------------------------------------------------
_client: Optional[anthropic.AsyncAnthropic] = None


def _anthropic() -> anthropic.AsyncAnthropic:
    global _client
    if not ANTHROPIC_API_KEY:
        # The setting's name is for the log; the page gets plain words.
        logger.error("ANTHROPIC_API_KEY is not set")
        raise RuntimeError(
            "Reactor's AI is not set up yet: the server has no Anthropic key. An admin needs to add it."
        )
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _client
_ai_kind: "contextvars.ContextVar[str]" = contextvars.ContextVar("ai_kind", default="ai")


def _price_for(model: str, inp: int, out: int, cache_read: int = 0, cache_write: int = 0) -> float:
    pi, po = _MODEL_PRICE.get(model, (5.0, 25.0))
    cr = _CACHE_READ_RATE.get(model, 0.10)
    return round((inp * pi + cache_write * pi * 1.25 + cache_read * pi * cr + out * po) / 1_000_000, 6)


def _log_usage(kind: str, model: str, usage, estimated: bool = False) -> None:
    """Append one model call's token usage + estimated cost. Best-effort; never raises.
    `estimated` marks a call that was sent and never answered, charged from
    its size (see _xcreate_once)."""
    if usage is None:
        return
    try:
        inp = int(getattr(usage, "input_tokens", 0) or 0)
        out = int(getattr(usage, "output_tokens", 0) or 0)
        cr = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        cw = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
        rec = {"at": datetime.now(timezone.utc).isoformat(), "kind": kind, "model": model,
               "in": inp, "out": out, "cache_read": cr, "cache_write": cw,
               "cost": _price_for(model, inp, out, cr, cw)}
        if estimated:
            rec["estimated"] = True
        _spend_today()                      # ensure the day bucket is current
        _spend["cost"] += rec["cost"]       # keep the daily cap in sync without re-reading
        events = jsonstore._load_json_store(USAGE_PATH, "events", [])
        if not jsonstore._store_writable(USAGE_PATH):
            return
        events.append(rec)
        events = events[-USAGE_MAX:]
        jsonstore._write_json_store(USAGE_PATH, "events", events)
        # Monthly rollup survives the event log trimming itself: the pricing
        # dataset must not evaporate at USAGE_MAX.
        rollup_path = os.path.join(os.path.dirname(USAGE_PATH) or ".", "usage_rollup.json")
        roll = jsonstore._load_json_store(rollup_path, None, {})
        if not isinstance(roll, dict):
            roll = {}
        if not jsonstore._store_writable(rollup_path):
            return
        mk = rec["at"][:7]
        m = roll.setdefault(mk, {"runs": 0, "in": 0, "out": 0, "cost": 0.0, "by_kind": {}})
        m["runs"] += 1
        m["in"] += inp
        m["out"] += out
        m["cost"] = round(m["cost"] + rec["cost"], 6)
        k = m["by_kind"].setdefault(kind, {"runs": 0, "cost": 0.0})
        k["runs"] += 1
        k["cost"] = round(k["cost"] + rec["cost"], 6)
        jsonstore._write_json_store(rollup_path, None, roll)
    except Exception:
        logger.exception("usage log failed")


_spend = {"day": "", "cost": 0.0}


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _spend_today() -> float:
    """Today's AI spend. Recomputed from the usage log when the day rolls over or the
    process restarts, so a redeploy cannot silently reset the cap."""
    day = _utc_day()
    if _spend["day"] != day:
        total = 0.0
        try:
            with open(USAGE_PATH, "r", encoding="utf-8") as fh:
                for e in json.load(fh).get("events", []):
                    if (e.get("at") or "").startswith(day):
                        total += float(e.get("cost") or 0)
        except Exception:
            total = 0.0
        _spend["day"], _spend["cost"] = day, total
    return _spend["cost"]


# What the calls sent and not yet answered may cost, held against the cap
# while they run (audit R-005, chain R-C3). The cap was read before a call
# and charged after it, so twenty calls sent together all passed at $24.99,
# and a call cancelled on the way (the browser closing a chat stream) was
# never charged at all.
_spend_pending = {"cost": 0.0}


# A document or image is billed by what it shows, not by the size of its
# base64: a PDF page is its text plus a picture of the page, and an image is
# scaled down before it is read. Counting a scan's base64 as text reserved
# $15 for one 8 MB invoice and turned everyone's chat away while it was read.
PDF_PAGE_TOKENS = 3000       # generous: a dense page's text and its image
PDF_BYTES_PER_PAGE = 60_000  # when the page count cannot be read from the file
PDF_MAX_PAGES = 100          # the most pages one request may carry
IMAGE_TOKENS = 1600          # the most an image costs once scaled to fit
_PDF_PAGE_OBJ = re.compile(rb"/Type\s*/Page(?![A-Za-z])")


def _media_tokens(block: dict) -> int:
    """Input tokens for one image or document block, estimated from what it is."""
    if block.get("type") == "image":
        return IMAGE_TOKENS
    src = block.get("source") if isinstance(block.get("source"), dict) else {}
    data = src.get("data")
    if src.get("type") == "text" and isinstance(data, str):
        return len(data) // 3
    if src.get("type") == "base64" and isinstance(data, str):
        try:
            raw = base64.b64decode(data, validate=False)
        except (ValueError, TypeError):
            raw = b""
        # A scan's pages sit in compressed object streams, where they cannot
        # be counted; its size stands in, generously.
        pages = len(_PDF_PAGE_OBJ.findall(raw)) or -(-len(raw) // PDF_BYTES_PER_PAGE)
        return max(1, min(PDF_MAX_PAGES, pages)) * PDF_PAGE_TOKENS
    return 20 * PDF_PAGE_TOKENS   # a file by reference: size unknown


def _estimate_chars(v, media: list) -> int:
    """Characters of everything sent, with each image and document counted
    into `media` as tokens instead of by its encoded bytes."""
    if isinstance(v, dict):
        if v.get("type") in ("image", "document") and isinstance(v.get("source"), dict):
            media.append(_media_tokens(v))
            return 0
        return sum(len(str(k)) + _estimate_chars(x, media) for k, x in v.items())
    if isinstance(v, (list, tuple)):
        return sum(_estimate_chars(x, media) for x in v)
    if isinstance(v, str):
        return len(v)
    return len(str(v)) if v is not None else 0


def _call_estimate(kwargs: dict) -> tuple:
    """(input tokens, cost) as an upper estimate for one call: three
    characters to a token over the text sent, documents and images by what
    they show, and the whole output allowance."""
    media: list = []
    chars = sum(_estimate_chars(kwargs.get(k), media) for k in ("system", "messages", "tools"))
    inp = chars // 3 + sum(media)
    out = int(kwargs.get("max_tokens") or MAX_TOKENS)
    return inp, _price_for(kwargs.get("model", ""), inp, out)


def _spend_guard(reserve: float = 0.0) -> None:
    if DAILY_COST_CAP > 0 and _spend_today() + _spend_pending["cost"] + reserve > DAILY_COST_CAP:
        logger.warning("DAILY_COST_CAP of %.2f reached", DAILY_COST_CAP)
        raise RuntimeError(
            "Reactor has used today's AI budget, so it will answer again tomorrow. "
            "This is a safety limit, and an admin can raise it."
        )


# Models that refuse a forced tool call (tool_choice "tool" or "any") with a
# 400: Opus 5.5 thinks on every request and chooses its own tools. A model
# found refusing at run time joins the set, so one pinned by a setting that
# this list does not know costs one refused request (not billed), not every one.
_UNFORCED_MODELS: set = {"claude-opus-5-5"}


def _can_force_tool(model: str) -> bool:
    m = (model or "").lower()
    return not any(x in m for x in _UNFORCED_MODELS)


def _forces_tool(kwargs: dict) -> bool:
    c = kwargs.get("tool_choice")
    return isinstance(c, dict) and c.get("type") in ("tool", "any")


def _unforce(kwargs: dict) -> str:
    """Turn a forced tool call into one the model accepts: tool_choice goes
    back to auto and the instructions say which tool carries the answer.
    Returns the tool's name ("" when any tool would do)."""
    choice = kwargs.pop("tool_choice", None) or {}
    name = str(choice.get("name") or "") if choice.get("type") == "tool" else ""
    ask = (f"Give your answer by calling the {name} tool, once. Do not answer in plain text."
           if name else "Give your answer by calling one of your tools. Do not answer in plain text.")
    system = kwargs.get("system")
    if isinstance(system, list):
        kwargs["system"] = system + [{"type": "text", "text": ask}]
    else:
        kwargs["system"] = ((system or "") + "\n\n" + ask).strip()
    return name


def _model_name(model: str) -> str:
    """claude-opus-5-5 as the page writes it: Claude Opus 5.5."""
    m = re.fullmatch(r"(?:anthropic\.)?claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?(?:[-@]\d{8})?", (model or "").strip().lower())
    if not m:
        return model or "the AI model"
    return "Claude " + m.group(1).title() + " " + m.group(2) + ("." + m.group(3) if m.group(3) else "")


def _ai_said(e: Exception) -> str:
    """Anthropic's own message for a failed call, on one line and short."""
    body = getattr(e, "body", None)
    err = body.get("error") if isinstance(body, dict) else None
    msg = err.get("message", "") if isinstance(err, dict) else ""
    msg = re.sub(r"\s+", " ", str(msg or getattr(e, "message", "") or e)).strip()
    return _strip_dashes(msg[:240])


def _ai_error_words(e: Exception, advice: bool = True) -> str:
    """What the page says when an AI call failed: which kind of failure it
    was, with Anthropic's own words where they tell it apart, and what to do
    (left off where another model answered, and there is nothing to do).
    Every failure used to read "The AI service returned an error", so a
    refused request, a model the account cannot use and a busy service
    looked the same."""
    def say(why, then=""):
        return why + (" " + then if advice and then else "")
    if isinstance(e, anthropic.APITimeoutError):
        return say("The AI service took too long to answer.", "Please try again.")
    if isinstance(e, anthropic.APIConnectionError):
        return say("Reactor could not reach the AI service.", "Please try again.")
    status = getattr(e, "status_code", 0) or 0
    said = _ai_said(e)
    if status == 401:
        return say("The AI service did not accept Reactor's key.", "An admin needs to check it.")
    if status == 413:
        return say("That was too much to send in one go.", "Start a new chat, or ask about less at once.")
    if status == 429:
        return say("Reactor had reached the AI service's limit for its account.", "Wait a minute and ask again.")
    if status == 529 or status >= 500:
        return say("The AI service was busy or down.", "Please try again shortly.")
    if status == 404:
        return "The AI service does not offer that model to Reactor's account. Anthropic said: " + said
    if said:
        return "The AI service refused the request. Anthropic said: " + said
    return say("The AI service returned an error.", "Please try again.")


# The latest AI failure, for Settings' Claude AI row: the page tells the
# person who asked, once; this keeps it for whoever looks next.
_AI_LAST_FAIL: dict = {}
# Set by _xcreate when the fallback model answered, for run_chat to say so.
_ai_fell_back: "contextvars.ContextVar[Optional[dict]]" = contextvars.ContextVar("ai_fell_back", default=None)


# What each kind of AI call is, in the words Settings shows.
_AI_KIND_WORDS = {"chat": "answering in Chat", "skill_read": "reading a skill", "learn": "learning the store",
                  "overview": "the overview", "seo": "the SEO audit", "keywords": "the keyword analysis",
                  "keyword_scan": "the keyword scan", "customers": "the customer analysis",
                  "product": "a product plan", "recon": "checking the accounts", "address": "reading an address",
                  "draft": "drafting an email reply"}


def _note_ai_failure(model: str, e: Exception, answered_by: str = "") -> None:
    """Kept for Settings' Claude AI row, and, when no model answered, in the
    app's error store with Anthropic's full reply for the developer."""
    _AI_LAST_FAIL.clear()
    _AI_LAST_FAIL.update({"at": datetime.now(timezone.utc).isoformat(), "model": _model_name(model),
                          "why": _ai_error_words(e, advice=False), "answered_by": _model_name(answered_by) if answered_by else "",
                          "kind": _ai_kind.get("ai")})
    if not answered_by:
        errors._record_error("asking the AI: " + _AI_KIND_WORDS.get(_ai_kind.get("ai"), "an AI task"), e)


def _fallback_for(model: str, e: Exception) -> str:
    """The model to ask instead, or "" when asking another cannot help: a key
    the service refused, or a request too big for any model."""
    fb = (MODEL_FALLBACK or "").strip()
    if not fb or fb.lower() in ("off", "none", "0") or fb.lower() == (model or "").lower():
        return ""
    if (getattr(e, "status_code", 0) or 0) in (401, 413):
        return ""
    return fb


@perf.timed("ai")           # Server-Timing: how long this request waited on Claude
async def _xcreate(client, **kwargs):
    """Every model call. A forced tool call is asked for in words on a model
    that refuses to be forced, and asked for once more if the answer came
    back as prose, so each caller still finds its tool block. A call the
    model fails at Anthropic is asked of the fallback model once, and the
    failure is kept for the usage panel either way."""
    perf.no_record()        # long by design: out of the slowest-routes table
    must = None
    if _forces_tool(kwargs) and not _can_force_tool(kwargs.get("model", "")):
        must = _unforce(kwargs)
    try:
        try:
            resp = await _xcreate_once(client, kwargs)
        except anthropic.BadRequestError as e:
            model = str(kwargs.get("model") or "").lower()
            if not (_forces_tool(kwargs) and model and "tool_choice" in str(e)):
                raise
            logger.warning("model %s refuses a forced tool; asking for it instead", model)
            _UNFORCED_MODELS.add(model)
            must = _unforce(kwargs)
            resp = await _xcreate_once(client, kwargs)
    except anthropic.APIStatusError as e:
        model = str(kwargs.get("model") or "")
        fb = _fallback_for(model, e)
        logger.warning("model %s failed (%s): %s%s", model, getattr(e, "status_code", ""), _ai_said(e),
                       "; asking " + fb if fb else "")
        if not fb:
            _note_ai_failure(model, e)
            raise
        alt = dict(kwargs)
        alt["model"] = fb
        if _forces_tool(alt) and not _can_force_tool(fb):
            must = _unforce(alt)
        try:
            resp = await _xcreate_once(client, alt)
        except anthropic.APIError as e2:
            logger.warning("fallback %s failed too: %s", fb, _ai_said(e2))
            _note_ai_failure(model, e)
            raise e
        _note_ai_failure(model, e, fb)
        _ai_fell_back.set({"from": model, "to": fb, "why": _ai_error_words(e, advice=False)})
        kwargs = alt
    except anthropic.APIError as e:
        _note_ai_failure(str(kwargs.get("model") or ""), e)
        raise
    if must is not None and getattr(resp, "stop_reason", "") == "end_turn" and not any(
            getattr(b, "type", "") == "tool_use" and (not must or getattr(b, "name", "") == must)
            for b in (getattr(resp, "content", None) or [])):
        # Its own reply goes back as it came, thinking included: the model
        # rejects an edited or dropped thinking block.
        more = dict(kwargs)
        more["messages"] = list(kwargs.get("messages") or []) + [
            {"role": "assistant", "content": resp.content},
            {"role": "user", "content": (f"Send that answer now by calling the {must} tool." if must
                                         else "Send that answer now by calling one of your tools.")}]
        try:
            resp = await _xcreate_once(client, more)
        except anthropic.APIError as e3:
            _note_ai_failure(str(kwargs.get("model") or ""), e3)
            raise
    return resp


async def _xcreate_once(client, kwargs: dict):
    """Wrapper around messages.create that enforces the daily spend cap, logs
    token usage + cost per call, and turns on prompt caching for every call:
    the big system prompt (profile + memory + skills + store knowledge) and the
    tool schemas are identical across the many rounds of a chat loop, so caching
    them stops the same tokens being bought again on every round."""
    kwargs = await _fit_to_model(client, kwargs)
    est_in, est = _call_estimate(kwargs)
    _spend_guard(est)
    system = kwargs.get("system")
    if isinstance(system, str) and len(system) > 2048:
        kwargs["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    tools = kwargs.get("tools")
    if isinstance(tools, list) and tools and isinstance(tools[-1], dict) and "cache_control" not in tools[-1]:
        kwargs["tools"] = tools[:-1] + [{**tools[-1], "cache_control": {"type": "ephemeral"}}]
    kind, model = _ai_kind.get("ai"), kwargs.get("model", "")
    _spend_pending["cost"] += est
    try:
        resp = await getattr(client.messages, "create")(**kwargs)
    except (asyncio.CancelledError, anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
        # Sent and not answered: it may still have been run and billed, so
        # the cap counts what was sent. A timeout is counted in full, output
        # allowance and all: it comes after the service has worked for
        # minutes, very likely to the end. A stop or a dropped line counts
        # its input only, or pressing Stop would spend the day's allowance.
        # A refusal the service answered with (an APIStatusError) is not
        # billed, and is not counted.
        out = int(kwargs.get("max_tokens") or MAX_TOKENS) if isinstance(e, anthropic.APITimeoutError) else 0
        _log_usage(kind, model, types.SimpleNamespace(input_tokens=est_in, output_tokens=out), estimated=True)
        raise
    finally:
        _spend_pending["cost"] = max(0.0, _spend_pending["cost"] - est)
    _log_usage(kind, model, getattr(resp, "usage", None))
    return resp


def _strip_dashes(obj: Any) -> Any:
    """Remove em/en dashes from any model-generated text before it reaches the UI.
    The prompts already instruct against them; this is the guarantee. En dash to
    hyphen (ranges), em dash to a comma."""
    if isinstance(obj, str):
        s = obj.replace("–", "-")
        s = re.sub(r"\s*—\s*", ", ", s)
        return s
    if isinstance(obj, dict):
        return {k: _strip_dashes(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_strip_dashes(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# The effort every call asks for, and the chat's thinking mode.
# ---------------------------------------------------------------------------
# Effort (low|medium|high|xhigh|max). Opus 5.5 thinks on every request and
# effort is how much: "high" spends what a task needs and is every call's
# level; "max" has no limit and is what Deep analysis in chat asks for. Every
# call stops at MAX_TOKENS with its thinking counted, which "max" can reach
# on a long report, so the reports stay at the everyday level.
ANTHROPIC_EFFORT = os.environ.get("ANTHROPIC_EFFORT", "high")
ANTHROPIC_EFFORT_DEEP = os.environ.get("ANTHROPIC_EFFORT_DEEP", "max")
# Extended thinking for the interactive chat loop. "adaptive" lets the model
# decide when and how deeply to reason (fast on simple questions, deep on hard
# ones). Set ANTHROPIC_THINKING=off to disable if ever needed.
THINKING_MODE = os.environ.get("ANTHROPIC_THINKING", "adaptive").strip().lower()
if THINKING_MODE in ("off", "none", "disabled", "0", ""):
    THINKING_MODE = ""


def _effort_for(model: str, deep: bool = False) -> str:
    """The everyday effort, or Deep analysis's, as configured. What the model
    behind it accepts is settled where every request goes out (_fit_to_model)."""
    return ANTHROPIC_EFFORT_DEEP if deep else ANTHROPIC_EFFORT
