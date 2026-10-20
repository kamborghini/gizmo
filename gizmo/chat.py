"""The chat loop: one turn of the assistant with its tool rounds, the words
shown for each step while it works, the previews of what a tool returned,
and what happens after an answer (memories kept, follow-ups closed, skills
noted). Moved out of copilot.py (stage 4 of the 14 October audit). Its two
routes stay in add_routes, which builds the tool list they use from the
registry it is handed; the system prompt stays in copilot.py, built from the
shared writing style as the app loads. Read as `assistant.NAME`.
"""
import logging
import os
import re
import json
from datetime import datetime
from typing import Callable, Optional
from gizmo.config import _env_num
from gizmo import ai as claude

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")



MAX_TOOL_ROUNDS    = _env_num(int, os.environ.get("COPILOT_MAX_TOOL_ROUNDS", "12"), "12", "COPILOT_MAX_TOOL_ROUNDS")


_TOOL_LABELS = {
    "shopify_get_shop": "Shop details", "shopify_list_orders": "Orders", "shopify_count_orders": "Order count",
    "shopify_get_order": "Order details", "shopify_list_products": "Products", "shopify_get_product": "Product details",
    "shopify_count_products": "Product count", "shopify_list_customers": "Customers",
    "shopify_search_customers": "Customer search", "shopify_get_customer": "Customer details",
    "shopify_get_customer_orders": "Customer orders", "shopify_list_collections": "Collections",
    "shopify_get_collection_products": "Collection products", "shopify_list_locations": "Locations",
    "shopify_get_inventory_levels": "Inventory levels", "shopify_list_fulfillments": "Fulfilments",
    "shopify_get_variant": "Variant details", "shopify_get_inventory_items": "Inventory items",
    "shopify_list_payouts": "Payouts", "shopify_payout_transactions": "Payout details",
    "shopify_list_disputes": "Disputes", "recon_summary": "Reconciliation summary",
    "recon_exceptions": "Reconciliation exceptions", "recon_exception": "Reconciliation exception",
    "get_search_console_data": "Google Search Console", "get_ga4_data": "Google Analytics 4",
    "seo_fetch_page": "On-page SEO", "seo_fetch_robots": "Search engine rules", "seo_fetch_sitemap": "Sitemap",
}


def _day_words(v) -> str:
    """'2026-08-01T00:00:00Z' as '1 Aug 2026'; anything else as it came."""
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return f"{d.day} {d:%b %Y}"
    except Exception:
        return str(v)[:24]


def _tool_label(name: str, args: Optional[dict] = None) -> str:
    """What a data read was, in words, with the window or search it was
    asked for: two reads of orders used to be labelled 'Orders', 'Orders'."""
    base = _TOOL_LABELS.get(name) or name.replace("shopify_", "").replace("_", " ").strip().capitalize()
    a = args if isinstance(args, dict) else {}
    lo = a.get("created_at_min") or a.get("start_date") or a.get("since")
    hi = a.get("created_at_max") or a.get("end_date") or a.get("until")
    if lo and hi:
        return f"{base}, {_day_words(lo)} to {_day_words(hi)}"
    if lo:
        return f"{base}, from {_day_words(lo)}"
    if a.get("days"):
        return f"{base}, last {a['days']} days"
    q = a.get("query") or a.get("q") or a.get("title")
    if isinstance(q, str) and q.strip():
        return f'{base}, "{q.strip()[:60]}"'
    return base


def _step_word(label: str) -> str:
    """A label inside a sentence: 'Reading orders, payouts', but Google's
    products keep their capitals."""
    return label if label.startswith("Google") else label[:1].lower() + label[1:]


_MONEY_KEYS = {"total_price", "subtotal_price", "total", "amount", "price", "total_spent", "spend",
               "revenue", "net", "fee", "total_discounts", "total_tax"}
_CUR_SIGN = {"GBP": "£", "USD": "$", "EUR": "€"}
# Fields whose value says what it is ('20 Sep 2026', '£1,023.83', 'paid').
_BARE_KEYS = {"created_at", "processed_at", "financial_status", "total_price", "total", "amount"}


def _preview_value(k: str, v, cur: str) -> str:
    if k in _MONEY_KEYS:
        try:
            return f"{_CUR_SIGN.get(cur, '')}{float(v):,.2f}" + ("" if cur in _CUR_SIGN else f" {cur}")
        except (TypeError, ValueError):
            pass
    if isinstance(v, str) and re.match(r"^\d{4}-\d{2}-\d{2}T", v):
        return _day_words(v)
    return str(v)


def _preview_line(r) -> str:
    if not isinstance(r, dict):
        return str(r)[:160]
    cur = str(r.get("currency") or r.get("presentment_currency") or "GBP").upper()
    head = next((str(r[k]) for k in ("name", "title", "query", "page", "email") if r.get(k)), "")
    bits = []
    for k, v in r.items():
        if k in ("name", "title", "query", "page", "id", "admin_graphql_api_id", "currency") or v in (None, "", [], {}):
            continue
        if isinstance(v, (dict, list)):
            continue
        words = "" if k in _BARE_KEYS else k.replace("_", " ").replace("fulfillment", "fulfilment") + " "
        bits.append(f"{words}{_preview_value(k, v, cur)}")
        if len(bits) == 5:
            break
    return (head + (": " if head and bits else "") + ", ".join(bits))[:220] or "(a record)"


def _data_preview(content, limit: int = 900) -> str:
    """What a data read returned, as lines a person can read: a record a
    line, its first fields in words, then how many more. The drill showed
    the first 500 characters of the raw JSON, cut off mid-field."""
    raw = str(content)
    try:
        obj = json.loads(raw)
    except Exception:
        return claude._strip_dashes(raw).strip()[:limit]
    rows = None
    if isinstance(obj, list):
        rows = obj
    elif isinstance(obj, dict):
        lists = [v for v in obj.values() if isinstance(v, list) and v and isinstance(v[0], dict)]
        if len(lists) == 1:
            rows = lists[0]
    if rows is not None:
        if not rows:
            return "Nothing was found."
        lines = [_preview_line(r) for r in rows[:8]]
        if len(rows) > 8:
            lines.append(f"and {len(rows) - 8} more")
    elif isinstance(obj, dict):
        lines = []
        for k, v in obj.items():
            if isinstance(v, (dict, list)) or v in (None, "") or k == "currency":
                continue
            lines.append(f"{k.replace('_', ' ').capitalize()}: {_preview_value(k, v, str(obj.get('currency') or 'GBP').upper())}")
            if len(lines) == 12:
                break
        if not lines:
            return claude._strip_dashes(raw).strip()[:limit]
    else:
        lines = [str(obj)]
    return claude._strip_dashes("\n".join(lines))[:limit]


def _chat_question(history: list) -> str:
    """The merchant's latest question, and the one before it, for choosing
    which saved skills fit this turn."""
    said = [m for m in (history or []) if isinstance(m, dict) and m.get("role") == "user"]
    out = []
    for m in said[-2:]:
        c = m.get("content")
        if isinstance(c, str):
            out.append(c)
        elif isinstance(c, list):
            out += [str(b.get("text") or "") for b in c if isinstance(b, dict) and b.get("type") == "text"]
    return "\n".join(out)[:4000]


def _picked_skills(body: dict) -> list:
    """Skills the person chose for this question (Use in chat, or the
    composer's picker): ids of real skills only."""
    ids = body.get("skills") if isinstance(body, dict) else None
    if not isinstance(ids, list):
        return []
    known = {s.get("id") for s in skillbook._load_skills()}
    return [str(i) for i in ids[:8] if str(i) in known]


def _chat_after(result: dict, history: list, held: bool = False, by: str = "") -> None:
    """What a chat answer asked to keep or close, done after it arrives.
    Notes that were not kept come back to the page, so a rule the merchant
    asked Reactor to remember is offered as a skill instead of vanishing; and
    follow-ups the merchant said are done are closed, and said so. `held`
    (a member's chat) keeps notes waiting for an admin, and says so."""
    st = result.get("structured") if isinstance(result.get("structured"), dict) else {}
    mems = st.pop("remember", None)
    done = st.pop("followups_done", None)
    saw = result.pop("_saw", "")
    if isinstance(mems, list) and mems:
        refused: list = []
        said = memory._chat_said(history)
        last = [m for m in (history or []) if isinstance(m, dict) and m.get("role") == "user"][-1:]
        kept: list = []
        try:
            memory._add_memories(mems, said, saw, source="chat", refused=refused, asked_in=memory._chat_said(last),
                          held=held, by=by, kept=kept)
        except Exception:
            logger.exception("Memory capture failed")
        if held and kept:
            result["held"] = kept[:4]
        # Offered back as a skill only when it is the merchant's own rule: an
        # instruction lifted from an order note or an email the answer read is
        # never put in front of them as something to keep.
        kept_out = [r["text"] for r in refused if r.get("reason") == "instruction"
                    and (not saw or memory._memory_grounded(r["text"], said, saw))]
        if kept_out:
            result["not_kept"] = kept_out[:4]
        # The page reads the notes again only when there may be new ones.
        if len(refused) < len(mems):
            result["noted"] = True
    if isinstance(done, list) and done:
        # Closed only when the merchant's own words name the follow-up; one
        # the answer thinks is done on the strength of what it READ (an order
        # note, an email) is offered to the merchant instead.
        def stems(t: str) -> set:
            # Words by their first four letters (so "called" meets "Call"),
            # and numbers whole (so "Stage Co 9" is not "Stage Co 13").
            t = str(t or "").lower()
            return {w[:4] for w in skillbook._skill_words(t) if not w.isdigit()} | set(re.findall(r"\d+", t))
        said_words = stems(_chat_question(history))
        want = {str(x) for x in done[:20]}
        opened = [m for m in memory._load_memory() if m.get("id") in want and m.get("type") == "followup"
                  and m.get("status") == "open"]
        sure = [m["id"] for m in opened if len(stems(m.get("text", "")) & said_words) >= 2]
        maybe = [{"id": m["id"], "text": m.get("text", "")} for m in opened if m["id"] not in sure]
        try:
            closed = memory._close_followups(sure) if sure else []
        except Exception:
            logger.exception("Follow-up close failed")
            closed = []
        if closed:
            result["followups_closed"] = closed
        if maybe:
            result["followups_maybe"] = maybe[:6]


def _fell_back_words() -> dict:
    """For a chat answer the fallback model gave: who answered and why."""
    fell = claude._ai_fell_back.get()
    if not fell:
        return {}
    return {"fell_back": {"from": claude._model_name(fell["from"]), "to": claude._model_name(fell["to"]), "why": fell["why"]}}


async def run_chat(history: list[dict], dispatch: Callable, data_tools: list[dict],
                   model: str, extra_system: str = "", emit: Optional[Callable] = None,
                   effort: Optional[str] = None, deep: bool = False) -> dict:
    """Run a multi-step tool-use conversation. The final answer is delivered via
    the present_response tool and returned as a structured dict. If `emit` is given,
    it is awaited with progress events ({"type":"step","label":...}) for live streaming."""
    claude._ai_kind.set("chat")
    claude._ai_fell_back.set(None)
    client = claude._anthropic()
    messages = list(history)
    tools_used: list[str] = []
    data_used: list[dict] = []   # for the UI "show the data behind this" drill-down
    # Everything the tools returned this turn, for the memory provenance check.
    # Popped by the caller before the result reaches the browser.
    saw: list[str] = []
    # read_skill is answered here from the skills store: it reads the
    # merchant's own text, never the store's data, and writes nothing.
    all_tools = data_tools + ([skillbook.READ_SKILL_TOOL] if skillbook._load_skills() else []) + [core.PRESENT_RESPONSE_TOOL]
    system = core.SYSTEM_PROMPT + extra_system
    if emit:
        await emit({"type": "step", "label": "Analysing your question"})

    for _ in range(MAX_TOOL_ROUNDS):
        kwargs = {
            "model": model, "max_tokens": claude.MAX_TOKENS, "system": system,
            "tools": all_tools, "messages": messages,
            "output_config": {"effort": effort or core._effort_for(model)},
        }
        if core.THINKING_MODE:  # adaptive thinking: deeper reasoning, model self-paces
            kwargs["thinking"] = {"type": core.THINKING_MODE}
        resp = await claude._xcreate(client,**kwargs)
        fell = claude._ai_fell_back.get()
        if fell:
            # The rest of this answer stays with the model that answered:
            # asking the failed one again each round only fails again.
            model = fell["to"]

        data_uses: list[Any] = []
        present: Optional[dict] = None
        text_parts: list[str] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                if block.name == core.PRESENT_RESPONSE_TOOL["name"]:
                    present = block.input
                else:
                    data_uses.append(block)
        # Append the model's turn verbatim (preserving any thinking blocks, which
        # interleaved thinking requires us to pass back on the next tool round).
        messages.append({"role": "assistant", "content": resp.content})

        if present is not None:
            return {"structured": core._coerce_structured(present), "tools_used": tools_used,
                    "data_used": data_used, "model": model, "_saw": "\n".join(saw), **_fell_back_words()}

        if not data_uses:
            # Ended without present_response — wrap any prose as the summary.
            text = "".join(text_parts).strip()
            stop = getattr(resp, "stop_reason", "")
            if not text and stop == "max_tokens":
                # Thinking counts against the limit, and Deep analysis thinks most.
                text = ("Reactor ran out of room while working this out, before it could answer. "
                        + ("Ask again, narrow the question, or switch Deep analysis off for a shorter think." if deep
                           else "Ask again, or narrow the question."))
            elif not text and stop == "refusal":
                text = "Reactor declined to answer that. Try asking it another way."
            return {"structured": {"summary": text or "Reactor did not send an answer. Ask again."}, "tools_used": tools_used,
                    "data_used": data_used, "model": model, "_saw": "\n".join(saw), **_fell_back_words()}

        if emit:
            labels = sorted({("your skill " + str((tu.input or {}).get("title", "")).strip()) if tu.name == skillbook.READ_SKILL_TOOL["name"]
                             else _step_word(_tool_label(tu.name)) for tu in data_uses})
            await emit({"type": "step", "label": "Reading " + ", ".join(labels)})
        tool_results = []
        for tu in data_uses:
            tools_used.append(tu.name)
            logger.info(f"copilot tool call: {tu.name}")  # name only — inputs may contain PII
            if tu.name == skillbook.READ_SKILL_TOOL["name"]:
                # The merchant's own words: not customer data, so not part of
                # what the memory provenance check treats as borrowed.
                ti = tu.input or {}
                content = skillbook._read_skill(ti.get("title", ""), ti.get("section", ""), ti.get("part"))
                tool_results.append({"type": "tool_result", "tool_use_id": tu.id, "content": content})
                if len(data_used) < 16:
                    plain = re.sub(r"\A<skill[^>]*>\n|\n</skill>\Z", "", content)
                    data_used.append({"tool": tu.name, "label": ("Skill: " + str(ti.get("title", ""))[:80]
                                      + (", " + str(ti.get("section"))[:60] if ti.get("section") else "")
                                      + (", part " + str(ti.get("part"))[:4] if str(ti.get("part") or "1") != "1" else "")),
                                      "preview": claude._strip_dashes(plain)[:900]})
                continue
            content = await dispatch(tu.name, tu.input)
            tool_results.append({"type": "tool_result", "tool_use_id": tu.id, "content": content})
            saw.append(str(content)[:200000])
            if len(data_used) < 16:
                data_used.append({"tool": tu.name, "label": _tool_label(tu.name, tu.input),
                                  "preview": _data_preview(content)})
        messages.append({"role": "user", "content": tool_results})

    return {
        "structured": {"summary": "I read a lot of data but could not finish an answer. "
                                  "Narrow the question and ask again."},
        "tools_used": tools_used, "data_used": data_used, "model": model,
        "_saw": "\n".join(saw), **_fell_back_words(),
    }


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as core.NAME and sibling.NAME, never a copied name.
from gizmo import memory  # noqa: E402
from gizmo import skills as skillbook  # noqa: E402
import copilot as core  # noqa: E402
