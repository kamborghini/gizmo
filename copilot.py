#!/usr/bin/env python3
"""
Store Copilot — an embedded Shopify admin chat backed by Claude.

This module adds an in-admin chat experience to the existing MCP server:
  GET  /            -> serves the chat page (App Bridge when embedded)
  POST /api/chat    -> runs a Claude tool-use loop over the store's data

It REUSES the Shopify tool functions already defined in server.py (passed in
as a registry), so there is one source of truth for Shopify API access.

Auth (embedded-only): every API request must carry a verified Shopify session
token (Bearer JWT from App Bridge). There is no password fallback.

Required env vars:
  ANTHROPIC_API_KEY     Claude API key (sk-ant-...). Required to chat.
  ANTHROPIC_MODEL       Optional. Defaults to claude-sonnet-4-6.
  SHOPIFY_API_KEY       App client ID. Enables App Bridge + session-token auth.
  SHOPIFY_API_SECRET    App client secret. Verifies session tokens.
"""
import os
import re
import html
import json
import time
import socket
import asyncio
import logging
import secrets
import ipaddress
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
from urllib.parse import urlparse, urljoin

import anthropic
import httpx
import jwt
import google_data
from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse

logger = logging.getLogger("shopify_mcp.copilot")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
# Model tiers. Default to Claude Opus 4.8 (most capable) everywhere; the env vars
# let you re-introduce a faster/cheaper tier (e.g. claude-sonnet-4-6) for chat later.
MODEL_FAST = os.environ.get("ANTHROPIC_MODEL_FAST") or os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-6"
MODEL_DEEP = os.environ.get("ANTHROPIC_MODEL_DEEP", "claude-opus-4-8")
# Effort (Opus-tier knob: low|medium|high|xhigh|max). "max" = maximum capability,
# at higher latency/cost. Dial down here if responses feel slow.
ANTHROPIC_EFFORT = os.environ.get("ANTHROPIC_EFFORT", "max")
# Extended thinking for the interactive chat loop. "adaptive" lets the model
# decide when and how deeply to reason (fast on simple questions, deep on hard
# ones). Set ANTHROPIC_THINKING=off to disable if ever needed.
THINKING_MODE = os.environ.get("ANTHROPIC_THINKING", "adaptive").strip().lower()
if THINKING_MODE in ("off", "none", "disabled", "0", ""):
    THINKING_MODE = ""
LOW_STOCK_THRESHOLD = int(os.environ.get("LOW_STOCK_THRESHOLD", "5"))
# History windows for trend charts + product analytics. Up to 24 months of
# Shopify order history is paginated for the Products tab and product detail;
# Google (GA4/GSC) timeseries are single calls. ORDER_PAGE_CAP bounds how many
# 250-order pages we will page through so the request stays responsive.
TREND_MONTHS = int(os.environ.get("TREND_MONTHS", "24"))
PRODUCT_TREND_MONTHS = int(os.environ.get("PRODUCT_TREND_MONTHS", "12"))
ORDER_PAGE_CAP = int(os.environ.get("ORDER_PAGE_CAP", "30"))
# App Bridge identity = the app's Client ID + secret. Accept either the
# SHOPIFY_API_KEY/SECRET names or the SHOPIFY_CLIENT_ID/SECRET names (same values).
SHOPIFY_API_KEY    = os.environ.get("SHOPIFY_API_KEY") or os.environ.get("SHOPIFY_CLIENT_ID", "")
SHOPIFY_API_SECRET = os.environ.get("SHOPIFY_API_SECRET") or os.environ.get("SHOPIFY_CLIENT_SECRET", "")
SHOPIFY_STORE      = os.environ.get("SHOPIFY_STORE", "")        # used to pin session tokens to this shop
# Public base URL (e.g. https://your-app.up.railway.app). When set, the Google
# OAuth redirect URI is derived from it rather than the request Host header.
APP_BASE_URL       = os.environ.get("APP_BASE_URL", "").strip()

# Headers applied to every API/page response (defense in depth).
_API_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
}

# --- Abuse / cost controls --------------------------------------------------
RATE_WINDOW      = int(os.environ.get("RATE_LIMIT_WINDOW", "60"))      # seconds
RATE_MAX_CLIENT  = int(os.environ.get("RATE_LIMIT_PER_CLIENT", "30"))  # requests/window/client
RATE_MAX_GLOBAL  = int(os.environ.get("RATE_LIMIT_GLOBAL", "150"))     # AI requests/window (cost ceiling)
MAX_BODY_BYTES   = int(os.environ.get("MAX_BODY_BYTES", str(256 * 1024)))  # 256 KB
MAX_MESSAGES     = int(os.environ.get("MAX_MESSAGES", "100"))          # chat history length
MAX_CHAT_CHARS   = int(os.environ.get("MAX_CHAT_CHARS", "100000"))     # total chars in a chat request

MAX_TOOL_ROUNDS    = int(os.environ.get("COPILOT_MAX_TOOL_ROUNDS", "12"))
MAX_TOKENS         = int(os.environ.get("COPILOT_MAX_TOKENS", "16000"))  # headroom for rich output at high effort (non-streaming-safe)
TOOL_RESULT_CAP    = int(os.environ.get("COPILOT_TOOL_RESULT_CAP", "50000"))
STORE_CONTEXT_CAP  = int(os.environ.get("STORE_CONTEXT_CAP", "4000"))
# Server-side store profile. Default path lives under /data so a Railway volume
# mounted there makes it durable across redeploys.
PROFILE_PATH       = os.environ.get("PROFILE_PATH", "/data/store_profile.json")
PROFILE_FIELD_CAP  = int(os.environ.get("PROFILE_FIELD_CAP", "6000"))
MEMORY_PATH        = os.environ.get("MEMORY_PATH", "/data/store_memory.json")
MEMORY_MAX         = int(os.environ.get("MEMORY_MAX", "500"))    # max stored memories
MEMORY_INJECT      = int(os.environ.get("MEMORY_INJECT", "40"))  # max of each kind injected into prompts
KNOWLEDGE_PATH     = os.environ.get("KNOWLEDGE_PATH", "/data/store_knowledge.json")
KNOWLEDGE_CAP      = int(os.environ.get("KNOWLEDGE_CAP", "8000"))     # max stored knowledge chars
IMPACT_PATH        = os.environ.get("IMPACT_PATH", "/data/impact.json")  # tracked-action impact log
IMPACT_MAX         = int(os.environ.get("IMPACT_MAX", "100"))
LEARN_MAX_PAGES    = int(os.environ.get("LEARN_MAX_PAGES", "12"))    # pages crawled when learning
LEARN_PAGE_CHARS   = int(os.environ.get("LEARN_PAGE_CHARS", "3000"))  # text kept per page
SKILLS_PATH        = os.environ.get("SKILLS_PATH", "/data/store_skills.json")  # merchant-authored skills
SKILLS_MAX         = int(os.environ.get("SKILLS_MAX", "200"))        # max stored skills
SKILL_TITLE_CAP    = int(os.environ.get("SKILL_TITLE_CAP", "120"))   # chars per skill title
SKILL_BODY_CAP     = int(os.environ.get("SKILL_BODY_CAP", "6000"))   # chars per skill body
SKILLS_INJECT_CAP  = int(os.environ.get("SKILLS_INJECT_CAP", "24000"))  # max total skill chars injected
ANALYSIS_CACHE_PATH      = os.environ.get("ANALYSIS_CACHE_PATH", "/data/analysis_cache.json")  # last result per AI tab
ANALYSIS_CACHE_MAX_BYTES = int(os.environ.get("ANALYSIS_CACHE_MAX_BYTES", "800000"))  # per-entry size guard

_PAGE_PATH = os.path.join(os.path.dirname(__file__), "static", "index.html")
_page_cache: Optional[str] = None

WRITING_STYLE = ("Write in clear, plain text. Never use em dashes or en dashes anywhere. "
                 "Use commas, periods, or parentheses instead, and 'to' or a hyphen for ranges "
                 "(for example '1 to 2 sentences', 'position 5-15'). Be concise and scannable.")

SYSTEM_PROMPT = """You are Store Copilot, a senior e-commerce analyst and growth strategist embedded in \
the admin of a Shopify store. Your job is to help the merchant make more money with specific, \
evidence-backed analysis, never generic advice.

How you work:
- Ground every claim in real data. Use the read tools to look things up before stating any number, \
name, or recommendation. Never invent figures, product names, or IDs. Call shopify_get_shop when you \
need the store's currency or timezone.
- Gather what you actually need before answering, and request independent tools in parallel. It is \
better to make several tool calls and be precise than to guess. Think step by step about which data \
would change your answer, then go get it.
- Reason across the full funnel and cross-reference every data set you can reach: Shopify commerce \
(orders, products, customers, inventory), Google Analytics (sessions, traffic sources, behavior), and \
Search Console (impressions, clicks, position). The sharpest insights live at the SEAMS between them, \
for example: high search impressions but low clicks (a title or meta problem), strong traffic but weak \
conversion (a page or offer problem), revenue concentrated in a few SKUs (concentration risk), or one \
channel converting far better than the rest (reallocate budget). Diagnose the weakest link, then \
quantify the upside and state the assumption behind your estimate.
- You have READ-ONLY access. You cannot create, update, or delete anything. When a change is needed, \
say exactly what to change and where in the admin, and be clear you cannot perform writes.
- Treat the store profile, your memory, the learned store knowledge, and the merchant's saved skills below as authoritative context. \
Honor stated preferences (for example, unlimited stock means give no restock advice), apply proven \
learnings, and do not re-ask what you already know. Check in on open follow-ups when relevant and close \
them out when the merchant says they are done.
- If the data you would need is missing or a connection (such as Google) is not set up, say so plainly \
and state what to connect, rather than padding with generic tips.

How you answer (IMPORTANT):
- When you have what you need, you MUST deliver your final answer by calling the `present_response` \
tool. Do not write the final answer as plain prose. Everything the merchant sees comes from that call.
- Put the single most important takeaway in `summary` (1 to 2 sentences). Use `metrics` for the key \
numbers, `insights` for notable findings (type them win/warning/opportunity/insight), `sections` for \
supporting detail and your reasoning, `actions` for concrete prioritized recommendations (most impactful \
first, each with its expected revenue or percentage impact), and `followups` for 2 to 4 natural next \
questions.
- Use the `remember` field to persist what will make you more useful next time: durable facts, decisions \
the merchant makes, their preferences, commitments to revisit, and proven learnings about THIS store.
- Only include fields that add value. A simple factual answer can be just `summary` plus a metric. Do \
not pad. Be specific, cite the real figures and where they came from, and quantify impact in money or \
percentages wherever you can.
""" + WRITING_STYLE

OVERVIEW_SYSTEM = """You are a senior Shopify analyst and growth strategist writing an executive \
overview from the store's live KPIs (already computed and provided to you), together with any Google \
Analytics and Search Console figures included.

Find what truly matters in THESE numbers, not generic advice:
- The biggest win, the biggest risk or anomaly, and the single highest-impact opportunity.
- Cross-reference the data sets where you can: reconcile traffic against revenue, search performance \
against sales, new versus returning behavior, and revenue concentration across products.
- Diagnose the weakest link in the funnel (visibility, traffic, conversion, average order value, \
retention) and say which lever moves the needle most.

Deliver everything by calling `present_response`: a one-line `summary` with the headline takeaway, 2 to \
4 `insights` (win/warning/opportunity/insight) that interpret the numbers, 2 to 4 prioritized `actions` \
each tied to an expected revenue or percentage impact, and 3 `followups` the merchant might ask. Do not \
restate every metric, interpret them. Cite the specific figures you are reasoning from, and honor the \
store profile, memory, learned knowledge, and saved skills provided as context.
""" + WRITING_STYLE

# Final-answer tool: forces clean structured output instead of raw markdown.
PRESENT_RESPONSE_TOOL = {
    "name": "present_response",
    "description": (
        "Present your final answer to the merchant as structured UI. Call this once, as your LAST "
        "action, after gathering any data you need. Everything shown to the merchant comes from here."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "The headline answer, 1–2 sentences."},
            "metrics": {
                "type": "array",
                "description": "Key figures to show as stat cards. Omit if not relevant.",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "value": {"type": "string"},
                        "delta": {"type": "string", "description": "Optional change, e.g. '+12%'."},
                        "trend": {"type": "string", "enum": ["up", "down", "flat"]},
                    },
                    "required": ["label", "value"],
                },
            },
            "insights": {
                "type": "array",
                "description": "Notable findings as color-coded callouts.",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["insight", "win", "warning", "opportunity"]},
                        "title": {"type": "string"},
                        "detail": {"type": "string"},
                    },
                    "required": ["type", "title"],
                },
            },
            "sections": {
                "type": "array",
                "description": "Expandable detail sections.",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "body": {"type": "string", "description": "Short paragraphs or '- ' bullet lines."},
                    },
                    "required": ["title", "body"],
                },
            },
            "actions": {
                "type": "array",
                "description": "Concrete recommended actions, most impactful first.",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                    },
                    "required": ["text"],
                },
            },
            "followups": {
                "type": "array",
                "description": "2–4 natural next questions the merchant might ask.",
                "items": {"type": "string"},
            },
            "remember": {
                "type": "array",
                "description": (
                    "Durable things to remember and reuse in FUTURE sessions so you get more tailored "
                    "over time. Record stable store facts ('fact'), decisions the merchant makes "
                    "('decision'), their stated preferences ('preference', e.g. 'wants concise answers', "
                    "'runs unlimited stock so skip restock advice'), commitments to revisit ('followup', "
                    "e.g. 'plans to reorder hoodies Friday'), and proven analytical learnings about THIS "
                    "store ('insight', e.g. 'email converts about 3x better than social here'). Omit "
                    "trivial, ephemeral, or already-obvious details. Leave empty if nothing is worth keeping."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string",
                                 "enum": ["fact", "decision", "followup", "preference", "insight"]},
                        "text": {"type": "string"},
                    },
                    "required": ["type", "text"],
                },
            },
        },
        "required": ["summary"],
    },
}

def _pick_model(deep: bool) -> str:
    """The Deep-analysis toggle is authoritative: on → deep model (Opus 4.8),
    off → fast model (Sonnet 4.6)."""
    return MODEL_DEEP if deep else MODEL_FAST


def _effort_for(model: str) -> str:
    """effort 'max' and 'xhigh' are Opus-tier only and 400 on Sonnet/Haiku —
    cap non-Opus models at 'high' so the request never errors."""
    eff = ANTHROPIC_EFFORT
    if "opus" not in model.lower() and eff in ("max", "xhigh"):
        return "high"
    return eff


def _context_block(context: Optional[str]) -> str:
    """Format ad-hoc custom instructions (legacy single-field) as a system addendum."""
    if not context or not str(context).strip():
        return ""
    text = str(context).strip()[:STORE_CONTEXT_CAP]
    return ("\n\n## Store profile — set by the merchant (authoritative)\n"
            "Follow these preferences and constraints in every answer; never contradict them:\n"
            + text)


def _load_profile() -> dict:
    try:
        with open(PROFILE_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_profile(data: dict) -> dict:
    data = data or {}
    prefs = data.get("prefs") or {}
    clean = {
        "brand_voice": str(data.get("brand_voice", ""))[:PROFILE_FIELD_CAP],
        "business_goals": str(data.get("business_goals", ""))[:PROFILE_FIELD_CAP],
        "strategy": str(data.get("strategy", ""))[:PROFILE_FIELD_CAP],
        "notes": str(data.get("notes", ""))[:PROFILE_FIELD_CAP],
        "prefs": {
            "track_inventory": bool(prefs.get("track_inventory", True)),
            "concise": bool(prefs.get("concise", False)),
            "proactive": bool(prefs.get("proactive", True)),
            "flag_anomalies": bool(prefs.get("flag_anomalies", True)),
        },
    }
    os.makedirs(os.path.dirname(PROFILE_PATH) or ".", exist_ok=True)
    tmp = PROFILE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(clean, fh)
    os.replace(tmp, PROFILE_PATH)
    return clean


def _profile_to_system(p: dict) -> str:
    """Compose the stored profile into an authoritative system addendum."""
    if not p:
        return ""
    fields = []
    for key, label in (("brand_voice", "Brand voice"), ("business_goals", "Business goals"),
                       ("strategy", "Overall strategy"), ("notes", "Other notes")):
        val = (p.get(key) or "").strip()
        if val:
            fields.append(f"- {label}: {val}")
    prefs = p.get("prefs") or {}
    rules = []
    if prefs.get("track_inventory") is False:
        rules.append("We carry unlimited stock — never give inventory, stock-level, or restock advice.")
    if prefs.get("concise"):
        rules.append("Keep answers concise and skimmable; favor short bullets over prose.")
    if prefs.get("proactive", True):
        rules.append("Always surface 1–3 concrete recommendations or opportunities, even when not asked.")
    if prefs.get("flag_anomalies", True):
        rules.append("Proactively flag anomalies, risks, or unusual changes you notice in the data.")
    if not fields and not rules:
        return ""
    block = "\n\n## Store profile — set by the merchant (authoritative; follow in every answer)\n"
    if fields:
        block += "\n".join(fields) + "\n"
    if rules:
        block += "Preferences:\n" + "\n".join("- " + r for r in rules)
    return block


# ---------------------------------------------------------------------------
# Memory — durable facts, decisions, and follow-ups across sessions
# ---------------------------------------------------------------------------

def _load_memory() -> list[dict]:
    try:
        with open(MEMORY_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh).get("memories", [])
    except Exception:
        return []


def _write_memory(memories: list[dict]) -> list[dict]:
    os.makedirs(os.path.dirname(MEMORY_PATH) or ".", exist_ok=True)
    tmp = MEMORY_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"memories": memories}, fh)
    os.replace(tmp, MEMORY_PATH)
    return memories


def _add_memories(items: list[dict]) -> list[dict]:
    memories = _load_memory()
    seen = {m.get("text", "").strip().lower() for m in memories}
    now = datetime.now(timezone.utc).isoformat()
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        text = str(it.get("text", "")).strip()[:800]
        if not text or text.lower() in seen:
            continue
        mtype = it.get("type") if it.get("type") in (
            "fact", "decision", "followup", "preference", "insight") else "fact"
        memories.append({"id": secrets.token_hex(5), "type": mtype, "text": text,
                         "status": "open", "created": now, "updated": now})
        seen.add(text.lower())
    if len(memories) > MEMORY_MAX:  # keep open follow-ups + the most recent of everything else
        keep = [m for m in memories if m.get("type") == "followup" and m.get("status") == "open"][:MEMORY_MAX]
        rest = [m for m in memories if not (m.get("type") == "followup" and m.get("status") == "open")]
        slots = max(0, MEMORY_MAX - len(keep))
        memories = keep + (rest[-slots:] if slots else [])  # slots==0 must yield [], not rest[-0:]
    return _write_memory(memories)


def _update_memory(mid: str, status: str) -> list[dict]:
    memories = _load_memory()
    if status in ("open", "done", "dismissed"):
        for m in memories:
            if m.get("id") == mid:
                m["status"] = status
                m["updated"] = datetime.now(timezone.utc).isoformat()
    return _write_memory(memories)


def _delete_memory(mid: str) -> list[dict]:
    return _write_memory([m for m in _load_memory() if m.get("id") != mid])


# ---------------------------------------------------------------------------
# Skills: merchant-authored instructions and playbooks. Permanent until the
# merchant edits or deletes them; injected into every answer as authoritative
# guidance the copilot follows (distinct from Memory, which the AI manages).
# ---------------------------------------------------------------------------

def _load_skills() -> list[dict]:
    try:
        with open(SKILLS_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh).get("skills", [])
    except Exception:
        return []


def _write_skills(skills: list[dict]) -> list[dict]:
    os.makedirs(os.path.dirname(SKILLS_PATH) or ".", exist_ok=True)
    tmp = SKILLS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"skills": skills}, fh)
    os.replace(tmp, SKILLS_PATH)
    return skills


def _add_skill(title: str, content: str) -> list[dict]:
    title = str(title or "").strip()[:SKILL_TITLE_CAP]
    content = str(content or "").strip()[:SKILL_BODY_CAP]
    if not title or not content:
        raise ValueError("A skill needs both a title and some details.")
    skills = _load_skills()
    if len(skills) >= SKILLS_MAX:
        raise ValueError(f"You have reached the limit of {SKILLS_MAX} skills. Delete one to add another.")
    now = datetime.now(timezone.utc).isoformat()
    # newest first, so a just-added skill is visible at the top of the list
    skills.insert(0, {"id": secrets.token_hex(5), "title": title, "content": content,
                      "created": now, "updated": now})
    return _write_skills(skills)


def _update_skill(sid: str, title: str, content: str) -> list[dict]:
    title = str(title or "").strip()[:SKILL_TITLE_CAP]
    content = str(content or "").strip()[:SKILL_BODY_CAP]
    if not title or not content:
        raise ValueError("A skill needs both a title and some details.")
    skills = _load_skills()
    for s in skills:
        if s.get("id") == sid:
            s["title"], s["content"] = title, content
            s["updated"] = datetime.now(timezone.utc).isoformat()
    return _write_skills(skills)


def _delete_skill(sid: str) -> list[dict]:
    return _write_skills([s for s in _load_skills() if s.get("id") != sid])


def _skills_to_system() -> str:
    skills = _load_skills()
    if not skills:
        return ""
    body, used, overflow = "", 0, []
    for s in skills:
        title = (s.get("title") or "").strip()
        content = (s.get("content") or "").strip()
        if not title or not content:
            continue
        block = f"### {title}\n{content}\n\n"
        if body and used + len(block) > SKILLS_INJECT_CAP:
            overflow.append(title)
            continue
        body += block
        used += len(block)
    if not body:
        return ""
    head = ("\n\n## Skills (instructions and playbooks the merchant saved for you to follow; treat them "
            "as authoritative, apply them whenever relevant, and note the merchant may refer to a skill "
            "by its title)\n")
    out = head + body.rstrip() + "\n"
    if overflow:
        out += ("More saved skills exist (full text in the Skills tab; ask the merchant if one applies): "
                + ", ".join(overflow) + "\n")
    return out


# ---------------------------------------------------------------------------
# Analysis cache: the last result of each AI tab (overview/seo/keywords/
# customers), persisted so reopening the app shows it instantly without
# spending tokens. The merchant clicks Refresh on a tab to recompute.
# ---------------------------------------------------------------------------

_ANALYSIS_KINDS = ("overview", "seo", "keywords", "customers")


def _load_analysis_cache() -> dict:
    try:
        with open(ANALYSIS_CACHE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_analysis(kind: str, result: dict) -> None:
    """Persist the latest result for a tab. Best-effort: never raises, so a
    disk problem can't break the analysis response the merchant is waiting on."""
    if kind not in _ANALYSIS_KINDS or not isinstance(result, dict) or result.get("error"):
        return
    try:
        blob = json.dumps(result, default=str)
        if len(blob) > ANALYSIS_CACHE_MAX_BYTES:
            logger.warning("analysis cache: %s result too large (%d bytes); not caching", kind, len(blob))
            return
        cache = _load_analysis_cache()
        cache[kind] = {"result": json.loads(blob), "at": datetime.now(timezone.utc).isoformat()}
        os.makedirs(os.path.dirname(ANALYSIS_CACHE_PATH) or ".", exist_ok=True)
        tmp = ANALYSIS_CACHE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cache, fh)
        os.replace(tmp, ANALYSIS_CACHE_PATH)
    except Exception:
        logger.exception("analysis cache: failed to save %s", kind)


# ---------------------------------------------------------------------------
# Impact tracking — "close the loop": snapshot headline metrics when a change is
# made, then measure how they moved since. Proves whether advice worked.
# ---------------------------------------------------------------------------

def _load_impact() -> list[dict]:
    try:
        with open(IMPACT_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh).get("items", [])
    except Exception:
        return []


def _write_impact(items: list[dict]) -> list[dict]:
    os.makedirs(os.path.dirname(IMPACT_PATH) or ".", exist_ok=True)
    tmp = IMPACT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"items": items[:IMPACT_MAX]}, fh)
    os.replace(tmp, IMPACT_PATH)
    return items[:IMPACT_MAX]


async def _impact_snapshot(registry: dict) -> dict:
    """A light 28-day headline-metric snapshot (revenue, orders, sessions, search
    clicks). Each source degrades to absent on error, so this never raises."""
    snap: dict = {"at": datetime.now(timezone.utc).isoformat()}
    try:
        orders = await _orders_28d(registry)
        snap["revenue_28d"] = round(sum(float(o.get("total_price") or 0) for o in orders), 2)
        snap["orders_28d"] = len(orders)
    except Exception:
        pass
    try:
        if google_data.ga4_configured():
            ga = await google_data.ga4_summary(28)
            if ga and not ga.get("error") and ga.get("sessions") is not None:
                snap["sessions_28d"] = ga["sessions"]
    except Exception:
        pass
    try:
        if google_data.gsc_configured():
            g = await google_data.gsc_overview(28)
            if g and not g.get("error") and g.get("clicks") is not None:
                snap["clicks_28d"] = g["clicks"]
    except Exception:
        pass
    return snap


_IMPACT_METRICS = [("revenue_28d", "Revenue", True), ("orders_28d", "Orders", False),
                   ("sessions_28d", "Sessions", False), ("clicks_28d", "Search clicks", False)]


def _impact_with_deltas(items: list[dict], current: dict) -> list[dict]:
    out = []
    for it in items:
        base = it.get("baseline") or {}
        deltas = []
        for key, label, _money_flag in _IMPACT_METRICS:
            b, c = base.get(key), current.get(key)
            if isinstance(b, (int, float)) and isinstance(c, (int, float)):
                pct = round((c - b) / b * 100) if b else None
                deltas.append({"key": key, "label": label, "from": b, "to": c, "pct": pct})
        out.append({**it, "deltas": deltas})
    return out


def _impact_learning_text(it: dict, current: dict) -> str:
    base = it.get("baseline") or {}
    b, c = base.get("revenue_28d"), current.get("revenue_28d")
    when = (it.get("started_at") or "")[:10]
    if isinstance(b, (int, float)) and isinstance(c, (int, float)) and b:
        pct = round((c - b) / b * 100)
        direction = "up" if pct > 0 else "down" if pct < 0 else "flat"
        return (f"After '{it.get('text', '')}' (tracked from {when}), 28-day revenue is {direction} "
                f"{abs(pct)}% (from {b:.0f} to {c:.0f}).")
    return f"Tracked the change '{it.get('text', '')}' from {when}."


def _memory_to_system(memories: Optional[list[dict]] = None) -> str:
    memories = _load_memory() if memories is None else memories
    if not memories:
        return ""
    active = [m for m in memories if m.get("status") != "dismissed"]
    open_fu = [m for m in active if m.get("type") == "followup" and m.get("status") == "open"][-MEMORY_INJECT:]
    facts = [m for m in active if m.get("type") in ("fact", "decision")][-MEMORY_INJECT:]
    prefs = [m for m in active if m.get("type") == "preference"][-MEMORY_INJECT:]
    learnings = [m for m in active if m.get("type") == "insight"][-MEMORY_INJECT:]
    if not (open_fu or facts or prefs or learnings):
        return ""
    block = "\n\n## Memory (what you have learned about this store; use it actively for continuity and tailoring)\n"
    if facts:
        block += "Facts and decisions:\n" + "\n".join("- " + m["text"] for m in facts) + "\n"
    if prefs:
        block += "Merchant preferences (always honor these):\n" + "\n".join("- " + m["text"] for m in prefs) + "\n"
    if learnings:
        block += "Proven learnings about this store (apply them):\n" + "\n".join("- " + m["text"] for m in learnings) + "\n"
    if open_fu:
        block += ("Open follow-ups (check in on these when relevant; close them out if done):\n"
                  + "\n".join("- " + m["text"] for m in open_fu))
    return block


# ---------------------------------------------------------------------------
# Store knowledge — learned once from the store's site, kept until deleted
# ---------------------------------------------------------------------------

LEARN_SYSTEM = """You are studying a Shopify merchant's public website (homepage, About and other \
pages, and blog posts) to build a durable knowledge profile the store's AI copilot will reference in \
every future answer. Read the supplied page text and write a clear, factual profile of the business.

Cover, when the content supports it: what the business is and sells, who its customers are, its \
positioning and points of difference, brand voice and tone, key products or collections and their \
selling points, the themes and expertise shown in the blog, and any policies or promises that shape \
how it should be represented. Be specific and use the store's own language. Do not invent anything \
not supported by the content. Write plain prose with short headed sections, no preamble. Never use \
em dashes or en dashes."""


def _load_knowledge() -> dict:
    try:
        with open(KNOWLEDGE_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_knowledge(text: str, sources: list[str]) -> dict:
    data = {"knowledge": text[:KNOWLEDGE_CAP], "sources": sources[:50],
            "learned_at": datetime.now(timezone.utc).isoformat()}
    os.makedirs(os.path.dirname(KNOWLEDGE_PATH) or ".", exist_ok=True)
    tmp = KNOWLEDGE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.replace(tmp, KNOWLEDGE_PATH)
    return data


def _delete_knowledge() -> None:
    try:
        os.remove(KNOWLEDGE_PATH)
    except FileNotFoundError:
        pass


def _knowledge_to_system() -> str:
    k = _load_knowledge()
    text = (k.get("knowledge") or "").strip()
    if not text:
        return ""
    return ("\n\n## Store knowledge (learned from the store's own site; authoritative background "
            "about the business; use it to inform every answer)\n" + text)


async def _discover_content_urls(primary: str, hosts: set, limit: int) -> list[str]:
    """Find homepage + About/other pages + blog posts via the sitemap (SSRF-guarded)."""
    def _is_content(u: str) -> bool:
        return ("/pages/" in u) or ("/blogs/" in u)
    _, sm = await _http_get(f"https://{primary}/sitemap.xml", allowed_hosts=hosts)
    locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", sm or "")
    page_urls = [l for l in locs if _is_content(l)]
    # Shopify's root sitemap is an index; follow the pages/blogs child sitemaps.
    for child in [l for l in locs if l.endswith(".xml") and ("page" in l or "blog" in l)][:4]:
        if urlparse(child).netloc.lower() in hosts:
            _, c = await _http_get(child, allowed_hosts=hosts)
            page_urls += [l for l in re.findall(r"<loc>\s*(.*?)\s*</loc>", c or "") if _is_content(l)]
    out, seen = [], set()
    for u in [f"https://{primary}/"] + page_urls:
        if u in seen or urlparse(u).netloc.lower() not in hosts:
            continue
        seen.add(u); out.append(u)
        if len(out) >= limit:
            break
    return out


async def run_learn(registry: dict) -> dict:
    primary, hosts = await _resolve_domains(registry)
    if not primary:
        raise RuntimeError("Could not resolve the store's domain to learn from.")
    shop = await _tool_json(registry, "shopify_get_shop", {})
    urls = await _discover_content_urls(primary, hosts, LEARN_MAX_PAGES)
    pages = []
    for u in urls:
        st, html = await _http_get(u, allowed_hosts=hosts)
        if not (st and html):
            continue
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
            tag.extract()
        text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))[:LEARN_PAGE_CHARS]
        title = (soup.title.string or "").strip() if soup.title and soup.title.string else u
        if len(text) > 80:
            pages.append({"url": u, "title": title, "text": text})
    if not pages:
        raise RuntimeError("Couldn't read any public pages from the storefront to learn from.")
    corpus = json.dumps({"shop": {"name": shop.get("name"), "domain": primary}, "pages": pages},
                        default=str)[:30000]
    client = _anthropic()
    resp = await client.messages.create(
        model=MODEL_DEEP, max_tokens=MAX_TOKENS, system=LEARN_SYSTEM,
        messages=[{"role": "user", "content": "Store website content:\n" + corpus
                   + "\n\nWrite the store knowledge profile now."}],
        output_config={"effort": _effort_for(MODEL_DEEP)},
    )
    text = _strip_dashes("".join(b.text for b in resp.content if b.type == "text").strip())
    if not text:
        raise RuntimeError("Couldn't synthesize store knowledge. Please try again.")
    return _save_knowledge(text, [p["url"] for p in pages])


# ---------------------------------------------------------------------------
# Anthropic tool schema + dispatch (derived from the injected registry)
# ---------------------------------------------------------------------------
# registry: dict[str, tuple[async_callable, pydantic_model_cls]]

def _build_tools(registry: dict) -> list[dict]:
    """Derive Anthropic tool schemas from the Shopify functions + Pydantic models."""
    tools = []
    for name, (func, model) in registry.items():
        schema = model.model_json_schema()
        schema.pop("title", None)
        tools.append({
            "name": name,
            "description": (func.__doc__ or "").strip(),
            "input_schema": schema,
        })
    return tools


def _build_dispatch(registry: dict) -> Callable:
    async def dispatch(name: str, args: dict) -> str:
        entry = registry.get(name)
        if not entry:
            return f"Unknown tool: {name}"
        func, model = entry
        try:
            payload = model(**(args or {}))
        except Exception as e:
            return f"Invalid arguments for {name}: {e}"
        result = await func(payload)
        result = str(result)
        if len(result) > TOOL_RESULT_CAP:
            result = result[:TOOL_RESULT_CAP] + "\n…[truncated, narrow your query for more]"
        return result
    return dispatch


# ---------------------------------------------------------------------------
# Claude tool-use loop
# ---------------------------------------------------------------------------
_client: Optional[anthropic.AsyncAnthropic] = None


def _anthropic() -> anthropic.AsyncAnthropic:
    global _client
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set on the server. Add it in Railway → Variables."
        )
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _client


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


def _coerce_structured(data: Any) -> dict:
    """Make sure we always hand the UI a dict with at least a summary string,
    with em/en dashes stripped from all text."""
    if not isinstance(data, dict):
        data = {"summary": str(data)}
    if not isinstance(data.get("summary"), str) or not data["summary"].strip():
        data["summary"] = "Here's what I found."
    return _strip_dashes(data)


_TOOL_LABELS = {
    "shopify_get_shop": "Shop details", "shopify_list_orders": "Orders", "shopify_count_orders": "Order count",
    "shopify_get_order": "Order details", "shopify_list_products": "Products", "shopify_get_product": "Product details",
    "shopify_count_products": "Product count", "shopify_list_customers": "Customers",
    "shopify_search_customers": "Customer search", "shopify_get_customer": "Customer details",
    "shopify_get_customer_orders": "Customer orders", "shopify_list_collections": "Collections",
    "shopify_get_collection_products": "Collection products", "shopify_list_locations": "Locations",
    "shopify_get_inventory_levels": "Inventory levels", "shopify_list_fulfillments": "Fulfillments",
    "get_search_console_data": "Google Search Console", "get_ga4_data": "Google Analytics 4",
    "seo_fetch_page": "On-page SEO", "seo_fetch_robots": "robots.txt", "seo_fetch_sitemap": "Sitemap",
}


def _tool_label(name: str) -> str:
    return _TOOL_LABELS.get(name) or name.replace("shopify_", "").replace("_", " ").strip().capitalize()


async def run_chat(history: list[dict], dispatch: Callable, data_tools: list[dict],
                   model: str, extra_system: str = "", emit: Optional[Callable] = None) -> dict:
    """Run a multi-step tool-use conversation. The final answer is delivered via
    the present_response tool and returned as a structured dict. If `emit` is given,
    it is awaited with progress events ({"type":"step","label":...}) for live streaming."""
    client = _anthropic()
    messages = list(history)
    tools_used: list[str] = []
    data_used: list[dict] = []   # for the UI "show the data behind this" drill-down
    all_tools = data_tools + [PRESENT_RESPONSE_TOOL]
    system = SYSTEM_PROMPT + extra_system
    if emit:
        await emit({"type": "step", "label": "Analyzing your question"})

    for _ in range(MAX_TOOL_ROUNDS):
        kwargs = {
            "model": model, "max_tokens": MAX_TOKENS, "system": system,
            "tools": all_tools, "messages": messages,
            "output_config": {"effort": _effort_for(model)},
        }
        if THINKING_MODE:  # adaptive thinking: deeper reasoning, model self-paces
            kwargs["thinking"] = {"type": THINKING_MODE}
        resp = await client.messages.create(**kwargs)

        data_uses: list[Any] = []
        present: Optional[dict] = None
        text_parts: list[str] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                if block.name == PRESENT_RESPONSE_TOOL["name"]:
                    present = block.input
                else:
                    data_uses.append(block)
        # Append the model's turn verbatim (preserving any thinking blocks, which
        # interleaved thinking requires us to pass back on the next tool round).
        messages.append({"role": "assistant", "content": resp.content})

        if present is not None:
            return {"structured": _coerce_structured(present), "tools_used": tools_used,
                    "data_used": data_used, "model": model}

        if not data_uses:
            # Ended without present_response — wrap any prose as the summary.
            text = "".join(text_parts).strip()
            return {"structured": {"summary": text or "(no response)"}, "tools_used": tools_used,
                    "data_used": data_used, "model": model}

        if emit:
            labels = sorted({_tool_label(tu.name) for tu in data_uses})
            await emit({"type": "step", "label": "Reading " + ", ".join(labels)})
        tool_results = []
        for tu in data_uses:
            tools_used.append(tu.name)
            logger.info(f"copilot tool call: {tu.name}")  # name only — inputs may contain PII
            content = await dispatch(tu.name, tu.input)
            tool_results.append({"type": "tool_result", "tool_use_id": tu.id, "content": content})
            if len(data_used) < 16:
                data_used.append({"tool": tu.name, "label": _tool_label(tu.name),
                                  "preview": _strip_dashes(str(content))[:500]})
        messages.append({"role": "user", "content": tool_results})

    return {
        "structured": {"summary": "I gathered a lot of data but couldn't finalize an answer. "
                                  "Please narrow the question and try again."},
        "tools_used": tools_used, "data_used": data_used, "model": model,
    }


# ---------------------------------------------------------------------------
# Overview — live KPIs (computed deterministically) + AI insight pass
# ---------------------------------------------------------------------------

async def _tool_json(registry: dict, name: str, args: dict) -> dict:
    func, model = registry[name]
    try:
        return json.loads(await func(model(**(args or {}))))
    except Exception:
        return {}


def _money(amount: float, currency: str) -> str:
    try:
        return f"{amount:,.0f} {currency}".strip()
    except Exception:
        return f"{amount} {currency}".strip()


def _delta(cur: float, prev: float) -> tuple[Optional[str], str]:
    if prev <= 0:
        return (None, "flat")
    change = (cur - prev) / prev * 100
    trend = "up" if change > 1 else "down" if change < -1 else "flat"
    return (f"{'+' if change >= 0 else ''}{change:.0f}%", trend)


async def _compute_metrics(registry: dict, track_inventory: bool = True) -> tuple[list[dict], dict]:
    now = datetime.now(timezone.utc)
    d7, d14 = (now - timedelta(days=7)).isoformat(), (now - timedelta(days=14)).isoformat()
    metrics: list[dict] = []

    shop = await _tool_json(registry, "shopify_get_shop", {})
    currency = shop.get("currency", "")

    o7 = (await _tool_json(registry, "shopify_list_orders",
                           {"status": "any", "created_at_min": d7, "limit": 250})).get("orders", [])
    op = (await _tool_json(registry, "shopify_list_orders",
                           {"status": "any", "created_at_min": d14, "created_at_max": d7, "limit": 250})).get("orders", [])
    rev7 = sum(float(o.get("total_price") or 0) for o in o7)
    revp = sum(float(o.get("total_price") or 0) for o in op)
    n7, npv = len(o7), len(op)
    aov = rev7 / n7 if n7 else 0
    unfulfilled = sum(1 for o in o7 if o.get("fulfillment_status") in (None, "partial", "unfulfilled"))

    rev_delta, rev_trend = _delta(rev7, revp)
    ord_delta, ord_trend = _delta(n7, npv)
    metrics.append({"label": "Revenue (7d)", "value": _money(rev7, currency), "delta": rev_delta, "trend": rev_trend})
    metrics.append({"label": "Orders (7d)", "value": str(n7), "delta": ord_delta, "trend": ord_trend})
    metrics.append({"label": "Avg order value", "value": _money(aov, currency)})
    metrics.append({"label": "Unfulfilled (7d)", "value": str(unfulfilled), "tone": "warn" if unfulfilled else None})

    new_cust = len((await _tool_json(registry, "shopify_list_customers",
                                     {"created_at_min": d7, "limit": 250})).get("customers", []))
    metrics.append({"label": "New customers (7d)", "value": str(new_cust)})

    total_products = (await _tool_json(registry, "shopify_count_products", {})).get("count")
    if total_products is not None:
        metrics.append({"label": "Products", "value": str(total_products)})

    low = []
    if track_inventory:
        products = (await _tool_json(registry, "shopify_list_products",
                                     {"limit": 250, "fields": "id,title,variants"})).get("products", [])
        low = [
            {"product": p.get("title"), "variant": v.get("title"), "qty": v.get("inventory_quantity")}
            for p in products for v in p.get("variants", [])
            if isinstance(v.get("inventory_quantity"), int) and v["inventory_quantity"] <= LOW_STOCK_THRESHOLD
        ]
        metrics.append({"label": f"Low stock (≤{LOW_STOCK_THRESHOLD})", "value": str(len(low)),
                        "tone": "warn" if low else None})

    from collections import Counter
    units = Counter()
    for o in o7:
        for li in o.get("line_items", []):
            if li.get("title"):
                units[li["title"]] += li.get("quantity") or 0

    context = {
        "shop": {"name": shop.get("name"), "currency": currency},
        "last_7d": {"revenue": round(rev7, 2), "orders": n7, "aov": round(aov, 2),
                    "unfulfilled": unfulfilled, "new_customers": new_cust},
        "prev_7d": {"revenue": round(revp, 2), "orders": npv},
        "catalog": ({"total_products": total_products, "low_stock_count": len(low),
                     "low_stock_examples": low[:8]} if track_inventory
                    else {"total_products": total_products, "inventory": "not tracked — unlimited stock"}),
        "top_products_7d": [{"title": t, "units": q} for t, q in units.most_common(5)],
        "note": "Order figures are based on up to 250 orders per 7-day window.",
    }

    # Real traffic + search performance (only when Google is connected).
    if google_data.ga4_configured():
        ga = await google_data.ga4_summary(28)
        if ga and not ga.get("error"):
            metrics.append({"label": "Sessions (GA4, 28d)", "value": f"{ga['sessions']:,}"})
            metrics.append({"label": "Revenue (GA4, 28d)", "value": _money(ga["revenue"], currency)})
            context["ga4_28d"] = ga
        elif ga.get("error"):
            context["ga4_28d"] = ga
    if google_data.gsc_configured():
        gsc = await google_data.gsc_overview(28)
        if gsc and not gsc.get("error"):
            metrics.append({"label": "Search clicks (28d)", "value": f"{gsc['clicks']:,}"})
            metrics.append({"label": "Search impressions (28d)", "value": f"{gsc['impressions']:,}"})
            if gsc.get("position") is not None:
                metrics.append({"label": "Avg Google position", "value": str(gsc["position"])})
            context["search_console_28d"] = gsc
        elif gsc.get("error"):
            context["search_console_28d"] = gsc

    return [m for m in metrics if m.get("value") is not None], context


async def run_overview(registry: dict, extra_system: str = "", track_inventory: bool = True) -> dict:
    metrics, context = await _compute_metrics(registry, track_inventory)
    client = _anthropic()
    msg = ("Current store KPIs (computed live):\n" + json.dumps(context, indent=2, default=str)
           + "\n\nGive the executive overview now by calling present_response.")
    resp = await client.messages.create(
        model=MODEL_DEEP, max_tokens=MAX_TOKENS, system=OVERVIEW_SYSTEM + extra_system,
        tools=[PRESENT_RESPONSE_TOOL], tool_choice={"type": "tool", "name": PRESENT_RESPONSE_TOOL["name"]},
        messages=[{"role": "user", "content": msg}],
        output_config={"effort": _effort_for(MODEL_DEEP)},
    )
    present = next((b.input for b in resp.content
                    if b.type == "tool_use" and b.name == PRESENT_RESPONSE_TOOL["name"]), None)
    structured = _coerce_structured(present or {"summary": "Here's your store overview."})
    structured.pop("metrics", None)  # UI shows the computed metrics, not Claude's echo
    currency = (context.get("shop") or {}).get("currency", "")
    return {"metrics": metrics, "structured": structured,
            "trends": await _overview_trends(registry), "currency": currency}


async def _overview_trends(registry: dict) -> dict:
    """Monthly revenue + sessions + search clicks for the trend charts. Prefers
    Google (single cheap calls, up to 24/16 months); falls back to Shopify orders
    for revenue when Google is not connected. Always degrades to {} gracefully."""
    trends: dict = {}
    # Shopify monthly revenue + orders + average order value (one bounded order pull).
    try:
        months = _month_axis(min(TREND_MONTHS, 12))
        orders = await _paginate_orders(registry, days=len(months) * 31)
        rev = {mk: 0.0 for mk in months}
        cnt = {mk: 0 for mk in months}
        for o in orders:
            mk = _month_key(o.get("created_at"))
            if mk in rev:
                rev[mk] += float(o.get("total_price") or 0)
                cnt[mk] += 1
        if any(rev[mk] for mk in months):
            trends["revenue"] = [{"label": mk, "value": round(rev[mk], 2)} for mk in months]
            trends["orders"] = [{"label": mk, "value": cnt[mk]} for mk in months]
            trends["aov"] = [{"label": mk, "value": round(rev[mk] / cnt[mk], 2) if cnt[mk] else 0} for mk in months]
    except Exception:
        logger.exception("overview shopify trends failed")
    # Google Analytics 4: sessions, pageviews, engaged, channel mix (+ revenue fallback).
    try:
        if google_data.ga4_configured():
            ts = await google_data.ga4_timeseries(min(TREND_MONTHS, 24) * 31)
            if ts and not ts.get("error"):
                for k in ("sessions", "pageviews", "engaged"):
                    if ts.get(k):
                        trends[k] = ts[k]
                if ts.get("channels"):
                    trends["channels"] = ts["channels"]
                if "revenue" not in trends and ts.get("revenue") and any(p.get("value") for p in ts["revenue"]):
                    trends["revenue"] = ts["revenue"]
    except Exception:
        logger.exception("overview ga4 trends failed")
    # Search Console: clicks, impressions, CTR, average position.
    try:
        if google_data.gsc_configured():
            gts = await google_data.gsc_timeseries(480)
            if gts and not gts.get("error"):
                for k in ("clicks", "impressions", "ctr", "position"):
                    if gts.get(k):
                        trends[k] = gts[k]
    except Exception:
        logger.exception("overview gsc trends failed")
    return trends


# ---------------------------------------------------------------------------
# SEO — knowledge layer + live technical audit
# ---------------------------------------------------------------------------

SEO_SAMPLE_PAGES = int(os.environ.get("SEO_SAMPLE_PAGES", "5"))

SEO_KNOWLEDGE = """## Technical SEO + revenue-optimization expertise (apply this model)
You are the store's optimization intelligence layer. Your job is to help the merchant make more
money by fusing four data sets: technical SEO, Google Search Console (how the store performs in
search), Google Analytics (traffic and on-site behavior), and Shopify commerce (orders, revenue,
products). Find where money is being left on the table and rank fixes by expected revenue impact.

Locate every organic-search issue on the pipeline: Discover, Crawl, Render, Index, Understand,
Rank, Serve. The first four are GATES (binary): if a page cannot be discovered, crawled, rendered,
or indexed, no ranking work matters, so fix gates BEFORE optimizations. Prioritize by
(business impact x confidence) / effort, favoring template and systemic fixes.

High-value cross-referenced opportunities to look for:
- High impressions + low CTR + mid position (roughly 5 to 15) queries: rewrite the title and meta
  to win clicks already being shown. Quantify the click upside.
- Pages or products with strong search/traffic but weak conversion or sales: a merchandising,
  pricing, or page-quality problem, not a traffic problem.
- Best-selling products that rank poorly or lack rich-result schema: protect and grow the winners.
- Traffic with no matching revenue (or vice versa): reconcile GA sessions against Shopify orders.

Correct these on sight:
- robots.txt Disallow is not noindex. Disallow blocks crawling; a disallowed URL can still be
  indexed. To remove from the index: allow crawl plus noindex, then optionally block.
- Canonical is a hint, not a directive. Duplicate content is selection, not a penalty.
- Crawl budget is a non-issue below roughly 100k URLs unless there is severe waste.
- Core Web Vitals (LCP, CLS, INP, not FID) are a minor tiebreaker, not a primary factor.
- Rankings are not traffic, traffic is not revenue. Optimize for the highest business metric.

Shopify-specific traps:
- Faceted/filter and ?variant= URLs create crawl traps and duplicate clusters. Control them via
  canonicals and parameters; do not let them bloat the index.
- Themes and apps can inject accidental noindex or wrong canonicals. Verify the rendered tags.
- Product and collection pages need Product, Offer, and BreadcrumbList JSON-LD. Thin descriptions
  and missing image alt text weaken Understand-stage signals. Collections are topical pillars;
  internal-link them deliberately.

Ground every claim in the supplied data, cite the supporting numbers, name the pipeline stage,
and give dev-ready fixes. Treat Google Search Central, web.dev, and schema.org as ground truth
when an exact threshold or field matters."""

_SEO_HINTS = ("seo", "search engine", "google", "ranking", "rank ", " index", "crawl",
              "robots", "sitemap", "canonical", "meta description", "title tag", "schema",
              "structured data", "keyword", "serp", "backlink", "alt text", "organic")


def _is_seo(messages: list[dict]) -> bool:
    for m in reversed(messages):
        if m.get("role") == "user":
            c = m.get("content")
            text = c if isinstance(c, str) else json.dumps(c)
            return any(h in text.lower() for h in _SEO_HINTS)
    return False


_domains_cache: dict = {}


async def _resolve_domains(registry: dict) -> tuple[str, set]:
    """Return (primary_domain, allowed_hosts) for the store. Cached per process."""
    if _domains_cache.get("primary"):
        return _domains_cache["primary"], _domains_cache["hosts"]
    shop = await _tool_json(registry, "shopify_get_shop", {})
    myshop = shop.get("myshopify_domain") or (f"{SHOPIFY_STORE}.myshopify.com" if SHOPIFY_STORE else "")
    primary = shop.get("domain") or myshop
    hosts = {h.lower() for h in (primary, myshop) if h}
    if primary:
        _domains_cache["primary"], _domains_cache["hosts"] = primary, hosts
    return primary, hosts


async def _http_get(url: str, allowed_hosts: Optional[set] = None) -> tuple[Optional[int], str]:
    """Fetch a URL, following redirects MANUALLY (max 4 hops). When allowed_hosts
    is given, every hop — including the initial URL — must be on that allow-list,
    which blocks redirect-based SSRF (e.g. a page 302-ing to an internal/metadata
    address). Returns (status, text); ("blocked" hops yield the redirect status, "")."""
    try:
        if allowed_hosts is not None and urlparse(url).netloc.lower() not in allowed_hosts:
            return None, ""
        async with httpx.AsyncClient(follow_redirects=False, timeout=15.0,
                                     headers={"User-Agent": "StoreCopilot-SEO/1.0"}) as c:
            for _ in range(4):
                r = await c.get(url)
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                    nxt = urljoin(url, r.headers["location"])
                    if allowed_hosts is not None and urlparse(nxt).netloc.lower() not in allowed_hosts:
                        return r.status_code, ""  # refuse to follow off-allowlist redirect
                    url = nxt
                    continue
                return r.status_code, r.text
            return None, ""  # too many redirects
    except Exception:
        return None, ""


def _parse_seo(html: str) -> dict:
    soup = BeautifulSoup(html or "", "html.parser")
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    desc_el = soup.find("meta", attrs={"name": "description"})
    desc = (desc_el.get("content") or "").strip() if desc_el else ""
    can_el = soup.find("link", attrs={"rel": lambda v: v and "canonical" in (v if isinstance(v, list) else [v])})
    canonical = (can_el.get("href") or "").strip() if can_el else ""
    rb = soup.find("meta", attrs={"name": "robots"})
    robots = (rb.get("content") or "").strip() if rb else ""
    types: list[str] = []
    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(s.string or "")
        except Exception:
            continue
        for it in (data if isinstance(data, list) else [data]):
            t = it.get("@type") if isinstance(it, dict) else None
            types.extend(t if isinstance(t, list) else [t] if t else [])
    imgs = soup.find_all("img")
    missing_alt = sum(1 for i in imgs if not (i.get("alt") or "").strip())
    return {
        "title": title, "title_len": len(title),
        "meta_description": desc, "meta_description_len": len(desc),
        "canonical": canonical, "meta_robots": robots, "noindex": "noindex" in robots.lower(),
        "jsonld_types": sorted({t for t in types if t}),
        "h1_count": len(soup.find_all("h1")),
        "images": len(imgs), "images_missing_alt": missing_alt,
        "word_count": len(soup.get_text(" ", strip=True).split()),
    }


# ---------------------------------------------------------------------------
# Keyword scraper for arbitrary external URLs (SSRF-guarded) + on-page keywords
# ---------------------------------------------------------------------------

EXTERNAL_FETCH_MAX = int(os.environ.get("EXTERNAL_FETCH_MAX", str(600 * 1024)))  # bytes of text kept

_STOPWORDS = set((
    "the a an and or but of to in on for with at by from as is are was were be been being this that "
    "these those it its your you we our us they them their he she his her i me my our ours not no yes "
    "do does did have has had will would can could should may might must shall into over under out up "
    "down off about above below more most some any all each every other than then once here there when "
    "where why how what which who whom whose if else while because so such only own same too very just "
    "get got make made use used new free shop store home page click here read learn back next per via "
    "also one two three com www http https"
).split())


def _host_is_public(host: str) -> bool:
    """True only if every resolved IP for host is a public, routable address.
    Blocks loopback, private, link-local (incl. cloud metadata 169.254.169.254),
    reserved, multicast and unspecified ranges. Used to gate external scraping."""
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            return False
    return True


async def _fetch_external(url: str) -> tuple[Optional[int], str, str]:
    """Fetch an arbitrary http(s) URL with SSRF protection: validates the scheme and
    that the host resolves only to public IPs, on the initial URL AND every redirect
    hop (redirects are followed manually). Returns (status, final_url, text)."""
    for _ in range(5):
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            raise RuntimeError("Enter a full http or https URL.")
        if not await asyncio.to_thread(_host_is_public, p.hostname):
            raise RuntimeError("That address is not allowed (only public websites can be scanned).")
        async with httpx.AsyncClient(follow_redirects=False, timeout=12.0,
                                     headers={"User-Agent": "StoreCopilot-SEO/1.0"}) as c:
            r = await c.get(url)
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
            url = urljoin(url, r.headers["location"])
            continue
        return r.status_code, str(r.url), (r.text or "")[:EXTERNAL_FETCH_MAX]
    raise RuntimeError("Too many redirects.")


def _extract_page_keywords(html_text: str) -> dict:
    """Pull on-page keyword signals: title, meta, headings, and the top single terms
    and two-word phrases by frequency (stopwords removed)."""
    from collections import Counter
    soup = BeautifulSoup(html_text or "", "html.parser")
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    desc_el = soup.find("meta", attrs={"name": "description"})
    desc = (desc_el.get("content") or "").strip() if desc_el else ""
    kw_el = soup.find("meta", attrs={"name": "keywords"})
    meta_kw = (kw_el.get("content") or "").strip() if kw_el else ""
    h1 = [h.get_text(" ", strip=True) for h in soup.find_all("h1")][:10]
    h2 = [h.get_text(" ", strip=True) for h in soup.find_all("h2")][:25]
    h3 = [h.get_text(" ", strip=True) for h in soup.find_all("h3")][:25]
    for t in soup(["script", "style", "noscript"]):
        t.extract()
    text = soup.get_text(" ", strip=True).lower()
    words = re.findall(r"[a-z][a-z'-]{2,}", text)
    toks = [w for w in words if w not in _STOPWORDS and len(w) > 2]
    uni = Counter(toks)
    bigrams = Counter(toks[i] + " " + toks[i + 1] for i in range(len(toks) - 1)
                      if toks[i] not in _STOPWORDS and toks[i + 1] not in _STOPWORDS)
    return {
        "title": title, "title_len": len(title), "meta_description": desc, "meta_keywords": meta_kw,
        "h1": h1, "h2": h2, "h3": h3, "word_count": len(words),
        "top_terms": [{"term": t, "count": c} for t, c in uni.most_common(25)],
        "top_phrases": [{"term": t, "count": c} for t, c in bigrams.most_common(15) if c > 1],
    }


KEYWORD_SYSTEM = """You are a senior search and paid-media strategist for a Shopify store. You turn raw \
keyword and ad data into a money-ranked plan, never generic tips.

Organic (Google Search Console): each query has clicks, impressions, CTR and average position. Find the money:
- Page-2 keywords (position roughly 11 to 20) with real impressions: small ranking gains move them onto \
page 1. Usually the highest-leverage opportunity. Name them.
- High impressions plus low CTR at a decent position: the page ranks but the title and meta are not \
winning the click. Recommend a specific rewrite and quantify the click upside.
- High-intent commercial queries versus informational ones: prioritize the queries buyers use.
- Separate branded from non-branded; non-branded growth is real new demand.

Paid (Google Ads, surfaced through GA4): you may have ad cost, clicks, CPC, conversions and ROAS overall \
and per campaign. Optimize for profit, not clicks:
- High CPC with low conversion or low ROAS: spend is being wasted. Recommend pausing, tightening match \
types, or fixing the landing page, and say which.
- Strong-ROAS campaigns: recommend scaling budget, with the expected return.
- Reconcile paid against organic: where you already rank organically for a term you also pay for, you \
may be able to cut paid spend and keep the traffic.

Ground every claim in the supplied numbers, cite them, and quantify impact in money or percent. Rank \
recommendations by (business impact x confidence) / effort.""" + WRITING_STYLE


async def _seo_product_signals(registry: dict) -> dict:
    data = await _tool_json(registry, "shopify_list_products",
                            {"limit": 250, "fields": "id,title,handle,body_html,images"})
    products = data.get("products", [])
    titles: dict = {}
    thin = no_desc = total_imgs = missing_alt = 0
    for p in products:
        t = (p.get("title") or "").strip().lower()
        titles[t] = titles.get(t, 0) + 1
        wc = len(re.sub("<[^>]+>", " ", p.get("body_html") or "").split())
        if wc == 0:
            no_desc += 1
        elif wc < 50:
            thin += 1
        for img in p.get("images", []):
            total_imgs += 1
            if not (img.get("alt") or "").strip():
                missing_alt += 1
    return {
        "products_sampled": len(products),
        "thin_descriptions": thin, "missing_descriptions": no_desc,
        "duplicate_titles": sum(1 for c in titles.values() if c > 1),
        "images": total_imgs, "images_missing_alt": missing_alt,
        "alt_coverage_pct": round(100 * (total_imgs - missing_alt) / total_imgs) if total_imgs else None,
    }


def _seo_scorecard(signals: dict, rs, ss, pages: list[dict]) -> tuple[int, list[dict]]:
    score = 100
    any_noindex = any(p.get("noindex") for p in pages)
    has_product_schema = any("Product" in (p.get("jsonld_types") or []) for p in pages)
    sitemap_ok, robots_ok = ss == 200, rs == 200
    md_pct = round(100 * sum(1 for p in pages if p.get("meta_description")) / len(pages)) if pages else 0
    alt = signals.get("alt_coverage_pct")
    thin = signals.get("thin_descriptions", 0)
    dup = signals.get("duplicate_titles", 0)

    if any_noindex:        score -= 25
    if not sitemap_ok:     score -= 10
    if not robots_ok:      score -= 5
    if not has_product_schema: score -= 12
    if alt is not None and alt < 90:   score -= min(15, (90 - alt) // 5 * 2)
    if md_pct < 90:        score -= min(12, (90 - md_pct) // 10 * 3)
    if thin:               score -= min(10, thin)
    if dup:                score -= min(10, dup)
    score = max(0, min(100, score))

    metrics = [
        {"label": "SEO score", "value": f"{score}/100", "tone": "warn" if score < 70 else None},
        {"label": "Indexable", "value": "noindex found" if any_noindex else "Yes",
         "tone": "warn" if any_noindex else None},
        {"label": "Sitemap", "value": "OK" if sitemap_ok else "Missing", "tone": None if sitemap_ok else "warn"},
        {"label": "Product schema", "value": "Present" if has_product_schema else "Missing",
         "tone": None if has_product_schema else "warn"},
        {"label": "Meta descriptions", "value": f"{md_pct}% of sampled", "tone": "warn" if md_pct < 90 else None},
        {"label": "Image alt", "value": f"{alt}%" if alt is not None else "n/a",
         "tone": "warn" if (alt is not None and alt < 90) else None},
        {"label": "Thin descriptions", "value": str(thin), "tone": "warn" if thin else None},
        {"label": "Duplicate titles", "value": str(dup), "tone": "warn" if dup else None},
    ]
    return score, metrics


class SeoFetchPageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path_or_url: str = Field(..., description="A path like '/products/handle' or a full URL on THIS store's domain.")


class SeoEmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _build_seo_tools(registry: dict) -> dict:
    async def seo_fetch_page(params: SeoFetchPageInput) -> str:
        """Fetch a page on THIS store's storefront and return its on-page SEO signals: title,
        meta description, canonical, meta robots/noindex, JSON-LD types, H1 count, image alt
        coverage, and word count. Accepts a path like '/products/handle' or a full store URL."""
        primary, hosts = await _resolve_domains(registry)
        if not primary:
            return json.dumps({"error": "Could not resolve the store domain."})
        raw = (params.path_or_url or "").strip()
        if raw.startswith("http"):
            if urlparse(raw).netloc.lower() not in hosts:
                return json.dumps({"error": f"Refused: only this store's domain ({primary}) can be fetched."})
            url = raw
        else:
            url = f"https://{primary}/{raw.lstrip('/')}"
        status, html = await _http_get(url, allowed_hosts=hosts)
        if not status:
            return json.dumps({"error": f"Could not fetch {url}"})
        return json.dumps({"url": url, "status": status, **_parse_seo(html)}, default=str)

    async def seo_check_robots_sitemap(params: SeoEmptyInput) -> str:
        """Fetch this store's robots.txt and sitemap.xml and summarize their health
        (found, whether robots references the sitemap, risky Disallow rules, sitemap size)."""
        primary, hosts = await _resolve_domains(registry)
        rs, rtext = await _http_get(f"https://{primary}/robots.txt", allowed_hosts=hosts)
        ss, stext = await _http_get(f"https://{primary}/sitemap.xml", allowed_hosts=hosts)
        return json.dumps({
            "robots_txt": {"status": rs, "found": rs == 200,
                           "references_sitemap": "sitemap" in (rtext or "").lower(),
                           "disallows_products": "Disallow: /products" in (rtext or ""),
                           "disallows_collections": "Disallow: /collections" in (rtext or ""),
                           "sample": (rtext or "")[:1500]},
            "sitemap_xml": {"status": ss, "found": ss == 200, "child_locs": (stext or "").count("<loc>")},
        }, default=str)

    return {
        "seo_fetch_page": (seo_fetch_page, SeoFetchPageInput),
        "seo_check_robots_sitemap": (seo_check_robots_sitemap, SeoEmptyInput),
    }


# ---------------------------------------------------------------------------
# Google data chat tools (only registered when GSC/GA4 is configured)
# ---------------------------------------------------------------------------

class DaysInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    days: Optional[int] = Field(default=28, ge=1, le=180, description="Look-back window in days.")


def _build_google_tools() -> dict:
    tools: dict = {}
    if google_data.gsc_enabled():
        async def get_search_console_data(params: DaysInput) -> str:
            """Real Google Search Console data for this store: total clicks, impressions, CTR and
            average position, plus the top search queries (with per-query impressions/CTR/position).
            Use this to ground SEO advice in how the store actually performs in Google Search —
            e.g. high-impression, low-CTR, mid-position queries are title/meta rewrite opportunities."""
            if not google_data.gsc_configured():
                return json.dumps({"error": "Google isn't connected yet. Connect it in Settings."})
            days = params.days or 28
            return json.dumps({"overview": await google_data.gsc_overview(days),
                               "top_queries": await google_data.gsc_top_queries(days)}, default=str)
        tools["get_search_console_data"] = (get_search_console_data, DaysInput)

    if google_data.ga4_enabled():
        async def get_ga4_data(params: DaysInput) -> str:
            """Real Google Analytics 4 data for this store: sessions, revenue, engaged sessions and
            the top traffic channels over the window. Use to ground answers about traffic, acquisition
            and on-site performance in real analytics rather than order data alone."""
            if not google_data.ga4_configured():
                return json.dumps({"error": "Google isn't connected yet. Connect it in Settings."})
            return json.dumps(await google_data.ga4_summary(params.days or 28), default=str)
        tools["get_ga4_data"] = (get_ga4_data, DaysInput)

    return tools


async def run_seo_audit(registry: dict, extra_system: str = "") -> dict:
    primary, hosts = await _resolve_domains(registry)
    if not primary:
        raise RuntimeError("Could not resolve the store's domain to audit.")
    signals = await _seo_product_signals(registry)
    rs, rtext = await _http_get(f"https://{primary}/robots.txt", allowed_hosts=hosts)
    ss, stext = await _http_get(f"https://{primary}/sitemap.xml", allowed_hosts=hosts)

    urls = [f"https://{primary}/"]
    sample = await _tool_json(registry, "shopify_list_products", {"limit": SEO_SAMPLE_PAGES, "fields": "handle"})
    urls += [f"https://{primary}/products/{p['handle']}" for p in sample.get("products", []) if p.get("handle")]
    pages = []
    for u in urls[:SEO_SAMPLE_PAGES + 1]:
        st, html = await _http_get(u, allowed_hosts=hosts)
        if st:
            pages.append({"url": u, "status": st, **_parse_seo(html)})

    score, metrics = _seo_scorecard(signals, rs, ss, pages)
    context = {
        "domain": primary, "computed_seo_score": score, "product_signals": signals,
        "robots_txt": {"status": rs, "found": rs == 200, "sample": (rtext or "")[:1000]},
        "sitemap_xml": {"status": ss, "found": ss == 200, "child_locs": (stext or "").count("<loc>")},
        "sampled_pages": pages,
    }

    # Fuse the other data sets so opportunities can be revenue-ranked.
    if google_data.gsc_configured():
        context["search_console"] = {
            "overview": await google_data.gsc_overview(28),
            "top_queries": await google_data.gsc_top_queries(28),
        }
    if google_data.ga4_configured():
        context["analytics"] = await google_data.ga4_summary(28)

    # Shopify commerce context: 28-day revenue, orders, and best sellers.
    shop = await _tool_json(registry, "shopify_get_shop", {})
    since28 = (datetime.now(timezone.utc) - timedelta(days=28)).isoformat()
    o28 = (await _tool_json(registry, "shopify_list_orders",
                            {"status": "any", "created_at_min": since28, "limit": 250})).get("orders", [])
    from collections import Counter
    units: Counter = Counter()
    for o in o28:
        for li in o.get("line_items", []):
            if li.get("title"):
                units[li["title"]] += li.get("quantity") or 0
    context["commerce"] = {
        "currency": shop.get("currency"),
        "revenue_28d": round(sum(float(o.get("total_price") or 0) for o in o28), 2),
        "orders_28d": len(o28),
        "top_products_28d": [{"title": t, "units": q} for t, q in units.most_common(8)],
    }

    client = _anthropic()
    msg = ("Optimization intelligence for this Shopify store (collected live, fusing technical SEO, "
           "Google Search Console, Google Analytics, and Shopify commerce):\n"
           + json.dumps(context, indent=2, default=str)
           + "\n\nProduce the report now via present_response. Goal: help the merchant make more money. "
             "Lead with the highest-impact, revenue-ranked opportunities in `actions` (each with the "
             "supporting numbers and the expected impact). Use `insights` for the most important "
             "performance issues and wins, cross-referencing the data sets. Fix indexation and crawl "
             "gates before optimizations. Be specific and quantify in money or percent wherever you can.")
    resp = await client.messages.create(
        model=MODEL_DEEP, max_tokens=MAX_TOKENS,
        system=OVERVIEW_SYSTEM + "\n\n" + SEO_KNOWLEDGE + extra_system,
        tools=[PRESENT_RESPONSE_TOOL], tool_choice={"type": "tool", "name": PRESENT_RESPONSE_TOOL["name"]},
        messages=[{"role": "user", "content": msg}],
        output_config={"effort": _effort_for(MODEL_DEEP)},
    )
    present = next((b.input for b in resp.content
                    if b.type == "tool_use" and b.name == PRESENT_RESPONSE_TOOL["name"]), None)
    structured = _coerce_structured(present or {"summary": "SEO audit complete."})
    structured.pop("metrics", None)
    seo_trends: dict = {}
    try:
        if google_data.gsc_configured():
            gts = await google_data.gsc_timeseries(480)
            if gts and not gts.get("error"):
                for k in ("clicks", "impressions", "ctr", "position"):
                    if gts.get(k):
                        seo_trends[k] = gts[k]
    except Exception:
        logger.exception("seo trends failed")
    return {"score": score, "metrics": metrics, "structured": structured, "trends": seo_trends}


# ---------------------------------------------------------------------------
# Keyword + CPC intelligence, and the external-URL keyword scanner
# ---------------------------------------------------------------------------

async def run_keywords(registry: dict, extra_system: str = "") -> dict:
    """Fuse Search Console keywords with Google Ads (via GA4) into a money-ranked
    keyword + CPC plan. Returns the AI analysis plus the raw keyword list and ad data
    for the UI tables. Degrades gracefully when Google is not connected."""
    days = 90
    gsc_ok = google_data.gsc_configured()
    ga4_ok = google_data.ga4_configured()
    overview = await google_data.gsc_overview(days) if gsc_ok else {}
    top = await google_data.gsc_top_queries(days, limit=100) if gsc_ok else {}
    ads = await google_data.ga4_ads(days) if ga4_ok else {}
    shop = await _tool_json(registry, "shopify_get_shop", {})
    currency = shop.get("currency", "")
    queries = top.get("queries", []) if isinstance(top, dict) else []

    metrics: list[dict] = []
    if overview and not overview.get("error"):
        metrics.append({"label": "Search clicks (90d)", "value": f"{overview.get('clicks', 0):,}"})
        metrics.append({"label": "Impressions (90d)", "value": f"{overview.get('impressions', 0):,}"})
        if overview.get("ctr") is not None:
            metrics.append({"label": "Avg CTR", "value": f"{overview.get('ctr', 0)}%"})
        if overview.get("position") is not None:
            metrics.append({"label": "Avg position", "value": str(overview.get("position"))})
    if ads and ads.get("totals") and ads.get("has_ads"):
        t = ads["totals"]
        metrics.append({"label": "Ad spend (90d)", "value": _money(t["cost"], currency)})
        metrics.append({"label": "Avg CPC", "value": f"{t['cpc']:.2f} {currency}".strip()})
        if t.get("roas"):
            metrics.append({"label": "ROAS", "value": f"{t['roas']}x"})

    context = {"currency": currency, "range_days": days,
               "search_console_overview": overview, "top_queries": queries,
               "google_ads_via_ga4": ads}
    client = _anthropic()
    msg = ("Keyword and paid-search data for this store (collected live):\n"
           + json.dumps(context, indent=2, default=str)
           + "\n\nProduce a money-ranked keyword and cost-per-click optimization plan via present_response. "
             "Lead with the highest-value opportunities in `actions` (each with the supporting numbers and "
             "expected impact). Use `insights` for the key findings across organic search and paid. Use "
             "`sections` for supporting detail. If paid data is absent, focus on organic and say what to "
             "connect. Be specific and quantify in money or percent.")
    resp = await client.messages.create(
        model=MODEL_DEEP, max_tokens=MAX_TOKENS,
        system=OVERVIEW_SYSTEM + "\n\n" + KEYWORD_SYSTEM + extra_system,
        tools=[PRESENT_RESPONSE_TOOL], tool_choice={"type": "tool", "name": PRESENT_RESPONSE_TOOL["name"]},
        messages=[{"role": "user", "content": msg}],
        output_config={"effort": _effort_for(MODEL_DEEP)},
    )
    present = next((b.input for b in resp.content
                    if b.type == "tool_use" and b.name == PRESENT_RESPONSE_TOOL["name"]), None)
    structured = _coerce_structured(present or {"summary": "Keyword analysis ready."})
    structured.pop("metrics", None)
    return {"metrics": metrics, "structured": structured, "currency": currency,
            "keywords": queries, "ads": ads if (ads and not ads.get("error")) else None,
            "gsc_connected": gsc_ok, "ga4_connected": ga4_ok}


async def run_keyword_scan(registry: dict, url: str, extra_system: str = "") -> dict:
    """Scrape an external URL (SSRF-guarded), extract its on-page keyword targeting,
    and have Claude analyze what it targets and how the merchant can compete."""
    status, final_url, html_text = await _fetch_external(url)
    if not html_text:
        raise RuntimeError("Could not read that page (it returned no readable HTML).")
    extracted = _extract_page_keywords(html_text)
    ours = await google_data.gsc_top_queries(90, limit=40) if google_data.gsc_configured() else {}
    context = {"scanned_url": final_url, "http_status": status, "page": extracted,
               "your_top_queries": (ours.get("queries") if isinstance(ours, dict) else [])}
    client = _anthropic()
    msg = ("On-page keyword extraction from an external URL (treat it as a competitor or reference page):\n"
           + json.dumps(context, indent=2, default=str)
           + "\n\nAnalyze it via present_response. In `summary`, state the page's primary topic and the "
             "keywords it targets. Use `insights` for what it does well and where it is weak. Use `actions` "
             "for specific keywords, topics or pages the merchant should create or optimize to compete, "
             "cross-referencing the merchant's own queries when provided. Be concrete and prioritized.")
    resp = await client.messages.create(
        model=MODEL_DEEP, max_tokens=MAX_TOKENS,
        system=OVERVIEW_SYSTEM + "\n\n" + KEYWORD_SYSTEM + extra_system,
        tools=[PRESENT_RESPONSE_TOOL], tool_choice={"type": "tool", "name": PRESENT_RESPONSE_TOOL["name"]},
        messages=[{"role": "user", "content": msg}],
        output_config={"effort": _effort_for(MODEL_DEEP)},
    )
    present = next((b.input for b in resp.content
                    if b.type == "tool_use" and b.name == PRESENT_RESPONSE_TOOL["name"]), None)
    structured = _coerce_structured(present or {"summary": "Scan complete."})
    structured.pop("metrics", None)
    return {"url": final_url, "extracted": extracted, "structured": structured}


# ---------------------------------------------------------------------------
# Per-product optimization plans
# ---------------------------------------------------------------------------

async def _orders_28d(registry: dict) -> list:
    since = (datetime.now(timezone.utc) - timedelta(days=28)).isoformat()
    return (await _tool_json(registry, "shopify_list_orders",
                             {"status": "any", "created_at_min": since, "limit": 250})).get("orders", [])


def _month_key(iso: Optional[str]) -> str:
    return (iso or "")[:7]            # "2025-01-15T..." -> "2025-01"


def _month_axis(months: int) -> list:
    """Ascending list of the last `months` month keys, ending this month."""
    now = datetime.now(timezone.utc)
    y, m, out = now.year, now.month, []
    for _ in range(max(1, months)):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return list(reversed(out))


async def _paginate_orders(registry: dict, days: int, max_pages: int = ORDER_PAGE_CAP,
                           fields: str = "id,created_at,total_price,line_items") -> list:
    """Page through orders created in the last `days`, ascending by id (since_id),
    capped at max_pages * 250 to stay responsive. Pulls only the requested fields."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    out: list = []
    since_id, pages = 0, 0
    while pages < max_pages:
        batch = (await _tool_json(registry, "shopify_list_orders",
                                  {"status": "any", "created_at_min": since, "limit": 250,
                                   "since_id": since_id, "fields": fields})).get("orders", [])
        if not batch:
            break
        out += batch
        pages += 1
        if len(batch) < 250:
            break
        since_id = max((o.get("id") or 0) for o in batch)
    return out


def _orders_monthly_revenue(orders: list, months: list) -> list:
    idx = {mk: 0.0 for mk in months}
    for o in orders:
        mk = _month_key(o.get("created_at"))
        if mk in idx:
            idx[mk] += float(o.get("total_price") or 0)
    return [{"label": mk, "value": round(idx[mk], 2)} for mk in months]


def _orders_product_monthly(orders: list, months: list) -> dict:
    """{product_id: {"units": {mk: int}, "revenue": {mk: float}}} within the months."""
    mset = set(months)
    out: dict = {}
    for o in orders:
        mk = _month_key(o.get("created_at"))
        if mk not in mset:
            continue
        for li in o.get("line_items", []):
            pid = li.get("product_id")
            if not pid:
                continue
            qty = li.get("quantity") or 0
            d = out.setdefault(pid, {"units": {}, "revenue": {}})
            d["units"][mk] = d["units"].get(mk, 0) + qty
            d["revenue"][mk] = d["revenue"].get(mk, 0.0) + float(li.get("price") or 0) * qty
    return out


async def run_products_list(registry: dict, months_window: Optional[int] = None) -> dict:
    """Rich product dataset for the Products tab: catalog fields + per-month units &
    revenue buckets (so the UI can filter, sort and compare any period entirely
    client-side) + facet lists. Order history is paginated up to `months_window`
    (default PRODUCT_TREND_MONTHS, capped at 24) and bounded by ORDER_PAGE_CAP."""
    months_window = min(max(int(months_window or PRODUCT_TREND_MONTHS), 1), 24)
    months = _month_axis(months_window)
    fields = ("id,title,handle,status,image,variants,product_type,vendor,tags,"
              "created_at,updated_at,published_at")
    data = await _tool_json(registry, "shopify_list_products", {"limit": 250, "fields": fields})
    products = data.get("products", [])
    shop = await _tool_json(registry, "shopify_get_shop", {})
    currency = shop.get("currency", "")

    orders = await _paginate_orders(registry, days=len(months) * 31)
    bucket = _orders_product_monthly(orders, months)
    cutoff28 = datetime.now(timezone.utc) - timedelta(days=28)
    units28: dict = {}
    rev28: dict = {}
    for o in orders:
        try:
            created = datetime.fromisoformat((o.get("created_at") or "").replace("Z", "+00:00"))
        except Exception:
            created = None
        if not (created and created >= cutoff28):
            continue
        for li in o.get("line_items", []):
            pid = li.get("product_id")
            if not pid:
                continue
            q = li.get("quantity") or 0
            units28[pid] = units28.get(pid, 0) + q
            rev28[pid] = rev28.get(pid, 0.0) + float(li.get("price") or 0) * q

    vendors: set = set()
    types: set = set()
    out = []
    for p in products:
        pid = p.get("id")
        img = p.get("image") or {}
        variants = p.get("variants") or []
        price = None
        for v in variants:
            try:
                price = float(v.get("price"))
                break
            except (TypeError, ValueError):
                continue
        inv_vals = [v.get("inventory_quantity") for v in variants if isinstance(v.get("inventory_quantity"), int)]
        inventory = sum(inv_vals) if inv_vals else None
        stock = ("untracked" if inventory is None else
                 "out" if inventory <= 0 else
                 "low" if inventory <= LOW_STOCK_THRESHOLD else "in")
        tags = p.get("tags")
        tags = [t.strip() for t in tags.split(",") if t.strip()] if isinstance(tags, str) else (tags or [])
        b = bucket.get(pid, {"units": {}, "revenue": {}})
        monthly = {mk: {"units": b["units"].get(mk, 0), "revenue": round(b["revenue"].get(mk, 0.0), 2)}
                   for mk in months if b["units"].get(mk) or b["revenue"].get(mk)}
        if p.get("vendor"):
            vendors.add(p["vendor"])
        if p.get("product_type"):
            types.add(p["product_type"])
        out.append({
            "id": pid, "title": p.get("title"), "handle": p.get("handle"), "status": p.get("status"),
            "image": img.get("src") if isinstance(img, dict) else None,
            "price": price, "vendor": p.get("vendor") or "", "product_type": p.get("product_type") or "",
            "tags": tags, "created_at": p.get("created_at"), "updated_at": p.get("updated_at"),
            "published_at": p.get("published_at"), "inventory": inventory, "stock_status": stock,
            "units_28d": units28.get(pid, 0), "revenue_28d": round(rev28.get(pid, 0.0), 2),
            "monthly": monthly,
        })
    out.sort(key=lambda x: (x["units_28d"], x["revenue_28d"]), reverse=True)  # best sellers first by default
    return {"currency": currency, "months": months,
            "vendors": sorted(vendors), "product_types": sorted(types),
            "products": out[:250]}


# ---------------------------------------------------------------------------
# Customers & retention analytics (from Shopify customers + orders)
# ---------------------------------------------------------------------------

async def _paginate_customers(registry: dict, max_pages: int = ORDER_PAGE_CAP) -> list:
    fields = "id,first_name,last_name,email,orders_count,total_spent,created_at,updated_at,state,tags"
    out: list = []
    since_id, pages = 0, 0
    while pages < max_pages:
        batch = (await _tool_json(registry, "shopify_list_customers",
                                  {"limit": 250, "since_id": since_id, "fields": fields})).get("customers", [])
        if not batch:
            break
        out += batch
        pages += 1
        if len(batch) < 250:
            break
        since_id = max((c.get("id") or 0) for c in batch)
    return out


async def run_customers(registry: dict, extra_system: str = "") -> dict:
    """Customer + retention intelligence: LTV, new vs returning, repeat rate, RFM-style
    segments, churn risk, top customers, and a new-customers trend, with an AI plan."""
    shop = await _tool_json(registry, "shopify_get_shop", {})
    currency = shop.get("currency", "")
    customers = await _paginate_customers(registry)
    months = _month_axis(12)
    orders = await _paginate_orders(registry, days=len(months) * 31, fields="id,created_at,customer")
    now = datetime.now(timezone.utc)

    last_order: dict = {}
    for o in orders:
        cid = (o.get("customer") or {}).get("id")
        if not cid:
            continue
        try:
            dt = datetime.fromisoformat((o.get("created_at") or "").replace("Z", "+00:00"))
        except Exception:
            continue
        if cid not in last_order or dt > last_order[cid]:
            last_order[cid] = dt

    seg: dict = {k: [] for k in ("champions", "loyal", "new", "at_risk", "one_time", "prospects")}
    new_by_month = {mk: 0 for mk in months}
    purchasers = repeat = 0
    spend_total = 0.0
    top: list = []
    cutoff30 = (now - timedelta(days=30)).isoformat()
    new_30 = 0
    for c in customers:
        oc = int(c.get("orders_count") or 0)
        try:
            ts = float(c.get("total_spent") or 0)
        except (TypeError, ValueError):
            ts = 0.0
        created = c.get("created_at") or ""
        if created[:7] in new_by_month:
            new_by_month[created[:7]] += 1
        if created >= cutoff30:
            new_30 += 1
        if oc >= 1:
            purchasers += 1
            spend_total += ts
        if oc >= 2:
            repeat += 1
        lo = last_order.get(c.get("id"))
        ds = (now - lo).days if lo else None
        name = (((c.get("first_name") or "") + " " + (c.get("last_name") or "")).strip()) or (c.get("email") or "Customer")
        rec = {"name": name, "email": c.get("email"), "orders": oc, "spent": round(ts, 2), "days_since": ds}
        top.append(rec)
        if oc == 0:
            seg["prospects"].append(rec)
        elif oc >= 3:
            (seg["champions"] if (ds is not None and ds <= 90) else seg["at_risk"]).append(rec)
        elif oc == 2:
            (seg["loyal"] if (ds is not None and ds <= 120) else seg["at_risk"]).append(rec)
        else:
            (seg["new"] if (ds is not None and ds <= 60) else seg["one_time"]).append(rec)

    top.sort(key=lambda x: x["spent"], reverse=True)
    total = len(customers)
    repeat_rate = round(repeat / purchasers * 100, 1) if purchasers else 0.0
    avg_ltv = round(spend_total / purchasers, 2) if purchasers else 0.0
    seg_defs = [("champions", "Champions", "3+ orders, active in 90 days"),
                ("loyal", "Loyal", "2 orders, active"),
                ("new", "New", "First order in last 60 days"),
                ("at_risk", "At risk", "Repeat buyers who have gone quiet"),
                ("one_time", "One and done", "One older order, no repeat"),
                ("prospects", "Prospects", "Account created, no orders yet")]
    segments = [{"key": k, "name": n, "desc": d, "count": len(seg[k]),
                 "revenue": round(sum(r["spent"] for r in seg[k]), 2)} for k, n, d in seg_defs]
    metrics = [
        {"label": "Customers", "value": f"{total:,}"},
        {"label": "Repeat rate", "value": f"{repeat_rate}%"},
        {"label": "Avg lifetime value", "value": _money(avg_ltv, currency)},
        {"label": "New (30d)", "value": f"{new_30:,}"},
        {"label": "At risk", "value": f"{len(seg['at_risk']):,}", "tone": "warn" if seg["at_risk"] else None},
    ]
    trends = {"new_customers": [{"label": mk, "value": new_by_month[mk]} for mk in months]}
    context = {"currency": currency,
               "totals": {"customers": total, "purchasers": purchasers, "repeat_rate_pct": repeat_rate,
                          "avg_ltv": avg_ltv, "new_30d": new_30},
               "segments": [{k: s[k] for k in ("name", "count", "revenue")} for s in segments],
               "top_customers": top[:15],
               "note": "Customers and orders are paginated up to a cap; very large stores may be truncated."}
    client = _anthropic()
    msg = ("Customer and retention data for this store (collected live):\n"
           + json.dumps(context, indent=2, default=str)
           + "\n\nProduce a retention-focused, money-ranked plan via present_response. Lead with the highest-value "
             "actions in `actions` (win back at-risk repeat customers, convert one-time buyers into repeat, lift "
             "repeat rate and lifetime value), each with the supporting numbers and expected impact. Use `insights` "
             "for the key findings about who your best customers are and where retention leaks. Quantify in money or percent.")
    resp = await client.messages.create(
        model=MODEL_DEEP, max_tokens=MAX_TOKENS, system=OVERVIEW_SYSTEM + extra_system,
        tools=[PRESENT_RESPONSE_TOOL], tool_choice={"type": "tool", "name": PRESENT_RESPONSE_TOOL["name"]},
        messages=[{"role": "user", "content": msg}],
        output_config={"effort": _effort_for(MODEL_DEEP)},
    )
    present = next((b.input for b in resp.content
                    if b.type == "tool_use" and b.name == PRESENT_RESPONSE_TOOL["name"]), None)
    structured = _coerce_structured(present or {"summary": "Customer analysis ready."})
    structured.pop("metrics", None)
    return {"metrics": metrics, "structured": structured, "currency": currency,
            "segments": segments, "top_customers": top[:25], "trends": trends, "totals": context["totals"]}


async def run_product_audit(registry: dict, product_id: int, extra_system: str = "") -> dict:
    p = await _tool_json(registry, "shopify_get_product", {"product_id": product_id})
    if not p or not p.get("id"):
        raise RuntimeError("Product not found.")
    handle = p.get("handle") or ""
    path = f"/products/{handle}"
    primary, hosts = await _resolve_domains(registry)

    page = {}
    if primary and handle:
        st, html = await _http_get(f"https://{primary}{path}", allowed_hosts=hosts)
        if st and html:
            page = {"url": f"https://{primary}{path}", "status": st, **_parse_seo(html)}

    gsc = await google_data.gsc_page_queries(path) if google_data.gsc_configured() else {}
    ga = await google_data.ga4_page(path) if google_data.ga4_configured() else {}

    units, rev = 0, 0.0
    for o in await _orders_28d(registry):
        for li in o.get("line_items", []):
            if li.get("product_id") == product_id:
                qty = li.get("quantity") or 0
                units += qty
                rev += float(li.get("price") or 0) * qty
    shop = await _tool_json(registry, "shopify_get_shop", {})
    currency = shop.get("currency", "")
    imgs = p.get("images", []) or []

    context = {
        "product": {
            "title": p.get("title"), "handle": handle, "status": p.get("status"),
            "price": (p.get("variants") or [{}])[0].get("price"),
            "product_type": p.get("product_type"), "tags": p.get("tags"),
            "description_words": len(re.sub("<[^>]+>", " ", p.get("body_html") or "").split()),
            "images": len(imgs),
            "images_missing_alt": sum(1 for i in imgs if not (i.get("alt") or "").strip()),
        },
        "page_seo": page,
        "search_console": gsc,
        "analytics": ga,
        "sales_28d": {"units": units, "revenue": round(rev, 2), "currency": currency},
    }
    client = _anthropic()
    msg = ("Per-product optimization data for one product (collected live):\n"
           + json.dumps(context, indent=2, default=str)
           + "\n\nProduce a focused, money-ranked optimization plan for THIS product via present_response. "
             "Lead with the highest-impact opportunities in `actions` (with the supporting numbers and the "
             "expected impact). Use `insights` for the key findings across search, traffic, sales and on-page "
             "SEO. Be specific to this product and quantify wherever you can.")
    resp = await client.messages.create(
        model=MODEL_DEEP, max_tokens=MAX_TOKENS,
        system=OVERVIEW_SYSTEM + "\n\n" + SEO_KNOWLEDGE + extra_system,
        tools=[PRESENT_RESPONSE_TOOL], tool_choice={"type": "tool", "name": PRESENT_RESPONSE_TOOL["name"]},
        messages=[{"role": "user", "content": msg}],
        output_config={"effort": _effort_for(MODEL_DEEP)},
    )
    present = next((b.input for b in resp.content
                    if b.type == "tool_use" and b.name == PRESENT_RESPONSE_TOOL["name"]), None)
    structured = _coerce_structured(present or {"summary": "Optimization plan ready."})
    structured.pop("metrics", None)

    metrics = []
    if gsc and gsc.get("totals"):
        t = gsc["totals"]
        metrics += [{"label": "Search clicks (28d)", "value": f"{t.get('clicks', 0):,}"},
                    {"label": "Impressions (28d)", "value": f"{t.get('impressions', 0):,}"}]
        if t.get("position"):
            metrics.append({"label": "Avg position", "value": str(t["position"])})
    if ga and not ga.get("error") and ("sessions" in ga):
        metrics.append({"label": "Sessions (28d)", "value": f"{ga.get('sessions', 0):,}"})
    metrics.append({"label": "Units sold (28d)", "value": str(units)})
    metrics.append({"label": "Revenue (28d)", "value": _money(rev, currency)})

    trend = {"units": [], "revenue": []}
    try:
        months = _month_axis(PRODUCT_TREND_MONTHS)
        p_orders = await _paginate_orders(registry, days=len(months) * 31)
        b = _orders_product_monthly(p_orders, months).get(product_id, {"units": {}, "revenue": {}})
        trend = {"units": [{"label": mk, "value": b["units"].get(mk, 0)} for mk in months],
                 "revenue": [{"label": mk, "value": round(b["revenue"].get(mk, 0.0), 2)} for mk in months]}
    except Exception:
        logger.exception("product trend failed")
    return {"product": {"title": p.get("title"), "handle": handle}, "metrics": metrics,
            "structured": structured, "trend": trend, "currency": currency}


# ---------------------------------------------------------------------------
# Auth: Shopify session token only (embedded-only; no password fallback)
# ---------------------------------------------------------------------------

def _verify_session_token(token: str) -> dict:
    if not SHOPIFY_API_SECRET:
        raise RuntimeError("SHOPIFY_API_SECRET not configured")
    claims = jwt.decode(
        token,
        SHOPIFY_API_SECRET,
        algorithms=["HS256"],
        audience=SHOPIFY_API_KEY or None,
        leeway=5,
        options={"require": ["exp", "nbf"], "verify_aud": bool(SHOPIFY_API_KEY)},
    )
    dest = claims.get("dest") or ""
    # Defense in depth: only accept tokens minted for this store.
    if SHOPIFY_STORE:
        expected = f"https://{SHOPIFY_STORE}.myshopify.com"
        if dest != expected:
            raise jwt.InvalidTokenError("session token dest mismatch")
    # Shopify guidance: the issuer and destination must reference the same shop host.
    iss = claims.get("iss") or ""
    if iss and dest:
        ih, dh = urlparse(iss).netloc, urlparse(dest).netloc
        if ih and dh and ih != dh:
            raise jwt.InvalidTokenError("session token iss/dest host mismatch")
    return claims


def _authorize(request: Request) -> tuple[bool, Optional[str]]:
    """Return (ok, who). The only accepted credential is a verified Shopify
    session token (Bearer JWT from App Bridge) — the app is embedded-only."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer ") and SHOPIFY_API_SECRET:
        try:
            claims = _verify_session_token(auth[7:])
            return True, claims.get("dest")
        except Exception as e:
            logger.warning(f"session token rejected: {e}")
    return False, None


# ---------------------------------------------------------------------------
# Page rendering
# ---------------------------------------------------------------------------

def _render_page() -> str:
    global _page_cache
    if _page_cache is None:
        with open(_PAGE_PATH, "r", encoding="utf-8") as fh:
            _page_cache = fh.read()
    # Embedded-only: always load App Bridge (which provides the session token).
    head = (
        f'<meta name="shopify-api-key" content="{SHOPIFY_API_KEY}" />\n'
        '    <script src="https://cdn.shopify.com/shopifycloud/app-bridge.js"></script>'
    ) if SHOPIFY_API_KEY else ""
    return _page_cache.replace("<!--APPBRIDGE-->", head)


_SHOP_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\.myshopify\.com$")


def _frame_headers(request: Request) -> dict:
    """Headers for the chat page: allow the admin iframe (must NOT send
    X-Frame-Options) and block MIME sniffing / referrer leakage."""
    shop = request.query_params.get("shop", "")
    # Only trust a well-formed myshopify domain in the CSP; otherwise fall back
    # to the wildcard so a crafted ?shop= value cannot inject extra frame hosts.
    ancestors = (
        f"https://{shop} https://admin.shopify.com"
        if _SHOP_RE.match(shop) else "https://admin.shopify.com https://*.myshopify.com"
    )
    # Full CSP: lock down sources while allowing exactly what the page needs —
    # App Bridge (cdn.shopify.com), Google Fonts, same-origin API calls, and the
    # store/admin for the embed. 'unsafe-inline' is scoped to the app's own inline
    # script/style; there is no untrusted-data→HTML sink (verified), so this is a
    # sound risk tradeoff vs. the nonce machinery App Bridge can be finicky about.
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.shopify.com https://*.shopify.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com data:; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://*.shopify.com https://*.myshopify.com; "
        "frame-src https://*.shopify.com; "
        "base-uri 'self'; form-action 'self'; object-src 'none'; "
        f"frame-ancestors {ancestors};"
    )
    return {
        "Content-Security-Policy": csp,
        "Cache-Control": "no-store",  # mode (embedded vs password) is env-dependent — never cache it
        **_API_HEADERS,
    }


def _json(data: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status, headers=_API_HEADERS)


# ---------------------------------------------------------------------------
# Abuse / cost controls — in-memory rate limiting + request-size guards
# ---------------------------------------------------------------------------
# Per-process and best-effort (fine at this scale; if the app is ever scaled to
# multiple instances, move this to a shared store like Redis). asyncio is single
# threaded and these helpers never await, so no lock is needed.
_rl_hits: dict[str, list[float]] = {}
_rl_global: list[float] = []
_oauth_states: dict[str, float] = {}   # state nonce -> expiry (Google OAuth connect flow)


def _client_key(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _window_ok(bucket: list[float], limit: int, now: float) -> bool:
    cutoff = now - RATE_WINDOW
    bucket[:] = [t for t in bucket if t >= cutoff]
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True


def _pre_checks(request: Request, ai: bool = False) -> Optional[JSONResponse]:
    """Rate-limit (per-client + global for AI endpoints) and reject oversized bodies."""
    now = time.monotonic()
    if len(_rl_hits) > 5000:  # guard the dict from unbounded growth
        _rl_hits.clear()
    if not _window_ok(_rl_hits.setdefault(_client_key(request), []), RATE_MAX_CLIENT, now):
        return _json({"error": "Too many requests. Please slow down."}, 429)
    if ai and not _window_ok(_rl_global, RATE_MAX_GLOBAL, now):
        return _json({"error": "The assistant is busy right now. Please try again shortly."}, 429)
    cl = request.headers.get("content-length", "")
    if cl.isdigit() and int(cl) > MAX_BODY_BYTES:
        return _json({"error": "Request too large."}, 413)
    return None


async def _read_json_capped(request: Request) -> Optional[dict]:
    """Read + parse the JSON body, enforcing MAX_BODY_BYTES on the bytes ACTUALLY
    read (not just the Content-Length header). Returns {} for empty/invalid bodies,
    or None if the body exceeds the cap (the caller should answer 413). This bounds
    peak memory even for chunked/unlabeled request bodies."""
    total, chunks = 0, []
    try:
        async for chunk in request.stream():
            total += len(chunk)
            if total > MAX_BODY_BYTES:
                return None
            chunks.append(chunk)
    except Exception:
        return {}
    raw = b"".join(chunks)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Route registration (mounted onto the existing FastMCP app)
# ---------------------------------------------------------------------------

def add_routes(mcp, registry: dict) -> None:
    # Shopify tools + live SEO tools + Google data tools (the last only if configured)
    chat_registry = {**registry, **_build_seo_tools(registry), **_build_google_tools()}
    tools = _build_tools(chat_registry)
    dispatch = _build_dispatch(chat_registry)

    logger.info(f"Copilot enabled — embedded-only; models: fast={MODEL_FAST}, deep={MODEL_DEEP}; "
                f"effort={ANTHROPIC_EFFORT}; max_tokens={MAX_TOKENS}; tools: {len(tools)}")
    if not ANTHROPIC_API_KEY:
        logger.warning("Copilot: ANTHROPIC_API_KEY not set. Chat will return an error until it is.")
    if not SHOPIFY_API_SECRET:
        logger.warning("Copilot: SHOPIFY_API_SECRET/CLIENT_SECRET not set. All API routes are locked "
                       "(session tokens can't be verified).")
    if not SHOPIFY_API_KEY:
        logger.warning("Copilot: SHOPIFY_API_KEY/CLIENT_ID not set. Session-token audience (aud) will "
                       "NOT be verified. Set it so tokens are validated against this app.")
    if not SHOPIFY_STORE:
        logger.warning("Copilot: SHOPIFY_STORE not set. Session tokens will NOT be pinned to a specific "
                       "shop (dest is unverified). Set SHOPIFY_STORE to lock the app to your store.")

    @mcp.custom_route("/", methods=["GET"])
    async def index(request: Request):
        # When embedded, only serve the page when it's loaded from Shopify
        # admin (which always appends shop/host/embedded). A direct browser
        # visit has none of those — return nothing so the app is invisible
        # outside the admin. (Real auth is still enforced on /api/chat.)
        if SHOPIFY_API_KEY:
            qp = request.query_params
            if not (qp.get("shop") or qp.get("host") or qp.get("embedded") or qp.get("id_token")):
                return PlainTextResponse("Not Found", status_code=404, headers=_API_HEADERS)
        return HTMLResponse(_render_page(), headers=_frame_headers(request))

    @mcp.custom_route("/healthz", methods=["GET"])
    async def healthz(request: Request):
        return PlainTextResponse("ok")

    @mcp.custom_route("/api/chat", methods=["POST"])
    async def chat(request: Request):
        pre = _pre_checks(request, ai=True)
        if pre:
            return pre
        ok, _who = _authorize(request)
        if not ok:
            return _json({"error": "Unauthorized"}, 401)
        body = await _read_json_capped(request)
        if body is None:
            return _json({"error": "Request too large."}, 413)

        history = body.get("messages")
        if not history and body.get("message"):
            history = [{"role": "user", "content": body["message"]}]
        if not history:
            return _json({"error": "Provide 'messages' or 'message'"}, 400)
        if not isinstance(history, list) or len(history) > MAX_MESSAGES:
            return _json({"error": "Conversation too long. Start a new chat."}, 400)
        if len(json.dumps(history)) > MAX_CHAT_CHARS:
            return _json({"error": "Message too large."}, 413)

        model = _pick_model(bool(body.get("deep")))
        extra = _profile_to_system(_load_profile()) + _memory_to_system() + _knowledge_to_system() + _skills_to_system()
        if _is_seo(history):
            extra += "\n\n" + SEO_KNOWLEDGE
        try:
            result = await run_chat(history, dispatch, tools, model, extra)
        except RuntimeError as e:
            return _json({"error": str(e)}, 500)
        except anthropic.APIError:
            logger.exception("Anthropic API error")
            return _json({"error": "The AI service returned an error. Please try again."}, 502)
        # Persist anything the copilot flagged to remember (then hide it from the UI).
        mems = result.get("structured", {}).pop("remember", None)
        if isinstance(mems, list) and mems:
            try:
                _add_memories(mems)
            except Exception:
                logger.exception("Memory capture failed")
        return _json(result)

    @mcp.custom_route("/api/chat/stream", methods=["POST"])
    async def chat_stream(request: Request):
        """Server-sent-events variant of /api/chat: emits real tool-step progress as
        the model works, then a final structured result. The client falls back to
        /api/chat if streaming is unavailable."""
        pre = _pre_checks(request, ai=True)
        if pre:
            return pre
        ok, _who = _authorize(request)
        if not ok:
            return _json({"error": "Unauthorized"}, 401)
        body = await _read_json_capped(request)
        if body is None:
            return _json({"error": "Request too large."}, 413)
        history = body.get("messages")
        if not history and body.get("message"):
            history = [{"role": "user", "content": body["message"]}]
        if not history:
            return _json({"error": "Provide 'messages' or 'message'"}, 400)
        if not isinstance(history, list) or len(history) > MAX_MESSAGES:
            return _json({"error": "Conversation too long. Start a new chat."}, 400)
        if len(json.dumps(history)) > MAX_CHAT_CHARS:
            return _json({"error": "Message too large."}, 413)

        model = _pick_model(bool(body.get("deep")))
        extra = _profile_to_system(_load_profile()) + _memory_to_system() + _knowledge_to_system() + _skills_to_system()
        if _is_seo(history):
            extra += "\n\n" + SEO_KNOWLEDGE

        q: asyncio.Queue = asyncio.Queue()

        async def runner():
            try:
                result = await run_chat(history, dispatch, tools, model, extra, emit=q.put)
                mems = result.get("structured", {}).pop("remember", None)
                if isinstance(mems, list) and mems:
                    try:
                        _add_memories(mems)
                    except Exception:
                        logger.exception("Memory capture failed")
                await q.put({"type": "done", "result": result})
            except anthropic.APIError:
                logger.exception("Anthropic API error (stream)")
                await q.put({"type": "error", "error": "The AI service returned an error. Please try again."})
            except RuntimeError as e:
                await q.put({"type": "error", "error": str(e)})
            except Exception:
                logger.exception("Chat stream failed")
                await q.put({"type": "error", "error": "Something went wrong. Please try again."})

        async def gen():
            task = asyncio.create_task(runner())
            try:
                while True:
                    ev = await q.get()
                    yield "data: " + json.dumps(ev) + "\n\n"
                    if ev.get("type") in ("done", "error"):
                        break
            finally:
                if not task.done():
                    task.cancel()

        headers = {**_API_HEADERS, "Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"}
        return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)

    @mcp.custom_route("/api/overview", methods=["POST"])
    async def overview(request: Request):
        pre = _pre_checks(request, ai=True)
        if pre:
            return pre
        ok, _who = _authorize(request)
        if not ok:
            return _json({"error": "Unauthorized"}, 401)
        body = await _read_json_capped(request)
        if body is None:
            return _json({"error": "Request too large."}, 413)
        profile = _load_profile()
        extra = _profile_to_system(profile) + _memory_to_system() + _knowledge_to_system() + _skills_to_system()
        track = (profile.get("prefs") or {}).get("track_inventory", True)
        try:
            result = await run_overview(registry, extra, bool(track))
        except RuntimeError as e:
            return _json({"error": str(e)}, 500)
        except anthropic.APIError:
            logger.exception("Anthropic API error (overview)")
            return _json({"error": "The AI service returned an error. Please try again."}, 502)
        except Exception:
            logger.exception("Overview failed")
            return _json({"error": "Couldn't build the overview. Check the server logs."}, 500)
        _save_analysis("overview", result)
        return _json(result)

    @mcp.custom_route("/api/profile", methods=["POST"])
    async def profile_route(request: Request):
        pre = _pre_checks(request)
        if pre:
            return pre
        ok, _who = _authorize(request)
        if not ok:
            return _json({"error": "Unauthorized"}, 401)
        body = await _read_json_capped(request)
        if body is None:
            return _json({"error": "Request too large."}, 413)
        # Save when a profile object is supplied; otherwise just load.
        if isinstance(body.get("profile"), dict):
            try:
                saved = _save_profile(body["profile"])
                return _json({"profile": saved})
            except Exception:
                logger.exception("Profile save failed")
                return _json({"error": "Couldn't save the profile (is a writable volume mounted at /data?)."}, 500)
        return _json({"profile": _load_profile()})

    @mcp.custom_route("/api/seo", methods=["POST"])
    async def seo_route(request: Request):
        pre = _pre_checks(request, ai=True)
        if pre:
            return pre
        ok, _who = _authorize(request)
        if not ok:
            return _json({"error": "Unauthorized"}, 401)
        body = await _read_json_capped(request)
        if body is None:
            return _json({"error": "Request too large."}, 413)
        extra = _profile_to_system(_load_profile()) + _memory_to_system() + _knowledge_to_system() + _skills_to_system()
        try:
            result = await run_seo_audit(registry, extra)
        except RuntimeError as e:
            return _json({"error": str(e)}, 500)
        except anthropic.APIError:
            logger.exception("Anthropic API error (seo)")
            return _json({"error": "The AI service returned an error. Please try again."}, 502)
        except Exception:
            logger.exception("SEO audit failed")
            return _json({"error": "Couldn't run the SEO audit. Check the server logs."}, 500)
        _save_analysis("seo", result)
        return _json(result)

    @mcp.custom_route("/api/keywords", methods=["POST"])
    async def keywords_route(request: Request):
        pre = _pre_checks(request, ai=True)
        if pre:
            return pre
        ok, _who = _authorize(request)
        if not ok:
            return _json({"error": "Unauthorized"}, 401)
        body = await _read_json_capped(request)
        if body is None:
            return _json({"error": "Request too large."}, 413)
        extra = _profile_to_system(_load_profile()) + _memory_to_system() + _knowledge_to_system() + _skills_to_system()
        try:
            res = await run_keywords(registry, extra)
            _save_analysis("keywords", res)
            return _json(res)
        except anthropic.APIError:
            logger.exception("Anthropic API error (keywords)")
            return _json({"error": "The AI service returned an error. Please try again."}, 502)
        except Exception:
            logger.exception("Keyword analysis failed")
            return _json({"error": "Couldn't run the keyword analysis. Check the server logs."}, 500)

    @mcp.custom_route("/api/keyword-scan", methods=["POST"])
    async def keyword_scan_route(request: Request):
        pre = _pre_checks(request, ai=True)
        if pre:
            return pre
        ok, _who = _authorize(request)
        if not ok:
            return _json({"error": "Unauthorized"}, 401)
        body = await _read_json_capped(request)
        if body is None:
            return _json({"error": "Request too large."}, 413)
        url = (body.get("url") or "").strip()
        if not url:
            return _json({"error": "Enter a URL to scan."}, 400)
        if not re.match(r"^https?://", url, re.I):
            url = "https://" + url
        if len(url) > 2048:
            return _json({"error": "That URL is too long."}, 400)
        extra = _profile_to_system(_load_profile()) + _memory_to_system() + _knowledge_to_system() + _skills_to_system()
        try:
            return _json(await run_keyword_scan(registry, url, extra))
        except RuntimeError as e:
            return _json({"error": str(e)}, 400)
        except anthropic.APIError:
            logger.exception("Anthropic API error (keyword-scan)")
            return _json({"error": "The AI service returned an error. Please try again."}, 502)
        except Exception:
            logger.exception("Keyword scan failed")
            return _json({"error": "Couldn't scan that URL. Check that it is a public web page."}, 500)

    @mcp.custom_route("/api/memory", methods=["POST"])
    async def memory_route(request: Request):
        pre = _pre_checks(request)
        if pre:
            return pre
        ok, _who = _authorize(request)
        if not ok:
            return _json({"error": "Unauthorized"}, 401)
        body = await _read_json_capped(request)
        if body is None:
            return _json({"error": "Request too large."}, 413)
        op = body.get("op")
        try:
            if op == "add" and isinstance(body.get("items"), list):
                _add_memories(body["items"])
            elif op == "set_status" and body.get("id"):
                _update_memory(body["id"], body.get("status", "done"))
            elif op == "delete" and body.get("id"):
                _delete_memory(body["id"])
        except Exception:
            logger.exception("Memory op failed")
            return _json({"error": "Couldn't update memory (is a writable volume mounted at /data?)."}, 500)
        return _json({"memories": _load_memory()})

    @mcp.custom_route("/api/skills", methods=["POST"])
    async def skills_route(request: Request):
        pre = _pre_checks(request)
        if pre:
            return pre
        ok, _who = _authorize(request)
        if not ok:
            return _json({"error": "Unauthorized"}, 401)
        body = await _read_json_capped(request)
        if body is None:
            return _json({"error": "Request too large."}, 413)
        op = body.get("op")
        try:
            if op == "add":
                _add_skill(body.get("title", ""), body.get("content", ""))
            elif op == "update" and body.get("id"):
                _update_skill(body["id"], body.get("title", ""), body.get("content", ""))
            elif op == "delete" and body.get("id"):
                _delete_skill(body["id"])
        except ValueError as e:
            return _json({"error": str(e)}, 400)
        except Exception:
            logger.exception("Skills op failed")
            return _json({"error": "Couldn't update skills (is a writable volume mounted at /data?)."}, 500)
        return _json({"skills": _load_skills()})

    @mcp.custom_route("/api/cache", methods=["POST"])
    async def cache_route(request: Request):
        # Returns the last saved result of each AI tab so the app can show it
        # instantly on open. Read-only, no AI, no body needed.
        pre = _pre_checks(request)
        if pre:
            return pre
        ok, _who = _authorize(request)
        if not ok:
            return _json({"error": "Unauthorized"}, 401)
        cache = _load_analysis_cache()
        out = {k: cache[k] for k in _ANALYSIS_KINDS if isinstance(cache.get(k), dict)}
        return _json(out)

    @mcp.custom_route("/api/impact", methods=["POST"])
    async def impact_route(request: Request):
        pre = _pre_checks(request)
        if pre:
            return pre
        ok, _who = _authorize(request)
        if not ok:
            return _json({"error": "Unauthorized"}, 401)
        body = await _read_json_capped(request)
        if body is None:
            return _json({"error": "Request too large."}, 413)
        op = body.get("op") or "list"
        items = _load_impact()
        try:
            if op == "add":
                text = (body.get("text") or "").strip()[:300]
                if not text:
                    return _json({"error": "Nothing to track."}, 400)
                snap = await _impact_snapshot(registry)
                items.insert(0, {"id": secrets.token_hex(5), "text": text,
                                 "source": str(body.get("source") or "copilot")[:24],
                                 "baseline": snap, "started_at": snap["at"], "status": "tracking"})
                items = _write_impact(items)
            elif op == "delete" and body.get("id"):
                items = _write_impact([x for x in items if x.get("id") != body["id"]])
            elif op == "conclude" and body.get("id"):
                cur = await _impact_snapshot(registry)
                for x in items:
                    if x.get("id") == body["id"] and x.get("status") != "concluded":
                        x["status"] = "concluded"
                        x["concluded_at"] = cur["at"]
                        x["final"] = cur
                        try:
                            _add_memories([{"type": "insight", "text": _impact_learning_text(x, cur)}])
                        except Exception:
                            logger.exception("impact learning capture failed")
                items = _write_impact(items)
        except Exception:
            logger.exception("Impact op failed")
            return _json({"error": "Couldn't update impact tracking (is a writable volume mounted at /data?)."}, 500)
        current = await _impact_snapshot(registry)
        return _json({"impact": _impact_with_deltas(items, current), "current": current})

    @mcp.custom_route("/api/learn", methods=["POST"])
    async def learn_route(request: Request):
        pre = _pre_checks(request, ai=True)
        if pre:
            return pre
        ok, _who = _authorize(request)
        if not ok:
            return _json({"error": "Unauthorized"}, 401)
        body = await _read_json_capped(request)
        if body is None:
            return _json({"error": "Request too large."}, 413)
        op = body.get("op")
        if op == "learn":
            try:
                return _json({"knowledge": await run_learn(registry)})
            except RuntimeError as e:
                return _json({"error": str(e)}, 500)
            except anthropic.APIError:
                logger.exception("Anthropic API error (learn)")
                return _json({"error": "The AI service returned an error. Please try again."}, 502)
            except Exception:
                logger.exception("Learn failed")
                return _json({"error": "Couldn't learn the store. Check the server logs."}, 500)
        if op == "delete":
            try:
                _delete_knowledge()
            except Exception:
                logger.exception("Knowledge delete failed")
                return _json({"error": "Couldn't delete the stored knowledge."}, 500)
            return _json({"knowledge": {}})
        return _json({"knowledge": _load_knowledge()})

    @mcp.custom_route("/api/products", methods=["POST"])
    async def products_route(request: Request):
        pre = _pre_checks(request)
        if pre:
            return pre
        ok, _who = _authorize(request)
        if not ok:
            return _json({"error": "Unauthorized"}, 401)
        body = await _read_json_capped(request)
        if body is None:
            return _json({"error": "Request too large."}, 413)
        try:
            months = int(body.get("months") or 0) or None
        except (TypeError, ValueError):
            months = None
        try:
            return _json(await run_products_list(registry, months))
        except Exception:
            logger.exception("Product list failed")
            return _json({"error": "Couldn't load products."}, 500)

    @mcp.custom_route("/api/customers", methods=["POST"])
    async def customers_route(request: Request):
        pre = _pre_checks(request, ai=True)
        if pre:
            return pre
        ok, _who = _authorize(request)
        if not ok:
            return _json({"error": "Unauthorized"}, 401)
        body = await _read_json_capped(request)
        if body is None:
            return _json({"error": "Request too large."}, 413)
        extra = _profile_to_system(_load_profile()) + _memory_to_system() + _knowledge_to_system() + _skills_to_system()
        try:
            res = await run_customers(registry, extra)
            _save_analysis("customers", res)
            return _json(res)
        except anthropic.APIError:
            logger.exception("Anthropic API error (customers)")
            return _json({"error": "The AI service returned an error. Please try again."}, 502)
        except Exception:
            logger.exception("Customer analysis failed")
            return _json({"error": "Couldn't run the customer analysis. Check the server logs."}, 500)

    @mcp.custom_route("/api/product", methods=["POST"])
    async def product_route(request: Request):
        pre = _pre_checks(request, ai=True)
        if pre:
            return pre
        ok, _who = _authorize(request)
        if not ok:
            return _json({"error": "Unauthorized"}, 401)
        body = await _read_json_capped(request)
        if body is None:
            return _json({"error": "Request too large."}, 413)
        try:
            pid = int(body.get("product_id"))
        except (TypeError, ValueError):
            return _json({"error": "A numeric product_id is required."}, 400)
        extra = _profile_to_system(_load_profile()) + _memory_to_system() + _knowledge_to_system() + _skills_to_system()
        try:
            return _json(await run_product_audit(registry, pid, extra))
        except RuntimeError as e:
            return _json({"error": str(e)}, 400)
        except anthropic.APIError:
            logger.exception("Anthropic API error (product)")
            return _json({"error": "The AI service returned an error. Please try again."}, 502)
        except Exception:
            logger.exception("Product audit failed")
            return _json({"error": "Couldn't analyze this product. Check the server logs."}, 500)

    # ----- Google OAuth connect flow (one-time, secret-gated) -------------
    def _redirect_uri(request: Request) -> str:
        # Prefer a configured public base URL (must match the URI registered in
        # Google Cloud) over the attacker-controllable Host header.
        if APP_BASE_URL:
            return APP_BASE_URL.rstrip("/") + "/oauth/google/callback"
        host = request.headers.get("host", "")
        return f"https://{host}/oauth/google/callback"

    def _oauth_page(title: str, msg: str) -> HTMLResponse:
        # Escape both inputs (any reflected query value is neutralized) and ship a
        # locked-down CSP: no scripts at all, only inline styles. Defense in depth.
        t, m = html.escape(str(title)), html.escape(str(msg))
        body = (f"<!doctype html><meta charset=utf-8><title>{t}</title>"
                "<style>body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#f7f7f8;"
                "color:#16161a;display:grid;place-items:center;height:100vh;margin:0}"
                ".c{background:#fff;border:1px solid #e7e7ea;border-radius:14px;padding:28px 32px;"
                "max-width:420px;text-align:center;box-shadow:0 6px 24px -6px rgba(20,20,40,.1)}"
                "h1{font-size:17px;margin:0 0 8px}p{color:#5c5f66;font-size:14px;margin:0}</style>"
                f"<div class=c><h1>{t}</h1><p>{m}</p></div>")
        headers = {"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; "
                   "base-uri 'none'; form-action 'none'", **_API_HEADERS}
        return HTMLResponse(body, headers=headers)

    @mcp.custom_route("/oauth/google/start", methods=["GET"])
    async def google_start(request: Request):
        if not _window_ok(_rl_hits.setdefault("oauth:" + _client_key(request), []), RATE_MAX_CLIENT, time.monotonic()):
            return PlainTextResponse("Too many requests", status_code=429, headers=_API_HEADERS)
        if not google_data.oauth_client_configured():
            return _oauth_page("Not configured", "Set GOOGLE_OAUTH_CLIENT_ID / SECRET on the server first.")
        key = request.query_params.get("key", "")
        if not (google_data.CONNECT_SECRET and key and
                secrets.compare_digest(key, google_data.CONNECT_SECRET)):
            return PlainTextResponse("Forbidden", status_code=403, headers=_API_HEADERS)
        now = time.time()
        for s, exp in list(_oauth_states.items()):  # prune expired
            if exp < now:
                _oauth_states.pop(s, None)
        state = secrets.token_urlsafe(24)
        _oauth_states[state] = now + 900  # 15-minute TTL
        from starlette.responses import RedirectResponse
        return RedirectResponse(google_data.consent_url(_redirect_uri(request), state), status_code=302)

    @mcp.custom_route("/oauth/google/callback", methods=["GET"])
    async def google_callback(request: Request):
        qp = request.query_params
        if qp.get("error"):
            return _oauth_page("Connection cancelled", f"Google returned: {qp.get('error')}")
        state = qp.get("state", "")
        exp = _oauth_states.pop(state, None)  # single-use
        if not state or exp is None or exp < time.time():
            return _oauth_page("Link expired", "That connect link expired or was already used. Start again.")
        code = qp.get("code", "")
        if not code:
            return _oauth_page("Connection failed", "No authorization code returned.")
        try:
            ok = await google_data.exchange_code(code, _redirect_uri(request))
        except Exception:
            logger.exception("Google OAuth exchange error")
            ok = False
        if not ok:
            return _oauth_page("Connection failed", "Couldn't complete the connection. Please try again.")
        return _oauth_page("✅ Connected to Google", "Search Console & Analytics are now linked. "
                           "You can close this tab and return to Store Copilot.")

    @mcp.custom_route("/api/google/status", methods=["POST"])
    async def google_status(request: Request):
        pre = _pre_checks(request)
        if pre:
            return pre
        ok, _who = _authorize(request)
        if not ok:
            return _json({"error": "Unauthorized"}, 401)
        body = await _read_json_capped(request)
        if body is None:
            return _json({"error": "Request too large."}, 413)
        return _json(google_data.status())

    @mcp.custom_route("/api/status", methods=["POST"])
    async def status_route(request: Request):
        """Connection-health summary for the Settings panel: Shopify, AI, and Google."""
        pre = _pre_checks(request)
        if pre:
            return pre
        ok, _who = _authorize(request)
        if not ok:
            return _json({"error": "Unauthorized"}, 401)
        body = await _read_json_capped(request)
        if body is None:
            return _json({"error": "Request too large."}, 413)
        shop_ok, shop_name, currency = False, None, None
        try:
            shop = await _tool_json(registry, "shopify_get_shop", {})
            if shop and shop.get("name"):
                shop_ok, shop_name, currency = True, shop.get("name"), shop.get("currency")
        except Exception:
            pass
        return _json({
            "shopify": {"ok": shop_ok, "name": shop_name, "currency": currency},
            "ai": {"ok": bool(ANTHROPIC_API_KEY)},
            "google": google_data.status(),
        })
