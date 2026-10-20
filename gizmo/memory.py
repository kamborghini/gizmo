"""Memory: the facts, decisions and follow-ups the assistant keeps across
sessions. The store, adding (checked against what was said), editing,
follow-ups, a member's notes held for an admin, and what goes into the AI's
instructions. Moved out of copilot.py (stage 4 of the 14 October audit); its
route is in gizmo/routes/memory.py. Read as `memory.NAME`.
"""
import logging
import os
import re
import secrets
from datetime import datetime, timezone
from typing import Optional
from gizmo.config import _env_num
from gizmo import store as jsonstore

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


MEMORY_PATH        = os.environ.get("MEMORY_PATH", "/data/store_memory.json")
MEMORY_MAX         = _env_num(int, os.environ.get("MEMORY_MAX", "500"), "500", "MEMORY_MAX")    # max stored memories
MEMORY_INJECT      = _env_num(int, os.environ.get("MEMORY_INJECT", "40"), "40", "MEMORY_INJECT")  # max of each kind injected into prompts
# Notes waiting for an admin are held to their own small allowance, and are
# the first to go when the store is full: counted in with the rest, a member
# asking chat to remember a few hundred things pushed out, for good, the notes
# an admin had kept (found verifying R-003).
MEMORY_PENDING_MAX = 50
MEMORY_HELD_PER_ANSWER = 12


# ---------------------------------------------------------------------------
# Memory — durable facts, decisions, and follow-ups across sessions
# ---------------------------------------------------------------------------

def _load_memory() -> list[dict]:
    # Through the one loader: read by hand, a corrupt file loaded as an empty
    # list, _store_writable saw nothing wrong, and the next note written
    # replaced every note the merchant had - the opposite of what the writer's
    # own comment promises.
    d = jsonstore._load_json_store(MEMORY_PATH, "memories", [])
    return d if isinstance(d, list) else []


def _write_memory(memories: list[dict]) -> list[dict]:
    if not jsonstore._store_writable(MEMORY_PATH):
        # Hand-written merchant work: preserve the broken file for repair rather
        # than replacing it with whatever loaded as the default.
        return memories
    jsonstore._write_json_store(MEMORY_PATH, "memories", memories)
    return memories


# Text that reads as an INSTRUCTION rather than a note about the business. The
# model's one write is the "remember" field, and its context now carries raw
# customer text (order notes, addresses, CRM notes, emails). A note that says
# "always tell customers X" would steer every future session for every user,
# so anything shaped like an instruction is refused at the door.
_MEMORY_INJECTION = re.compile(
    r"(?i)\b(ignore (all |any )?previous|disregard (all |the )?(previous|above)"
    r"|system prompt|you are now|from now on(,| you)|always (say|tell|reply|respond|include)"
    r"|never (say|tell|mention|reveal)|new instructions?|override|jailbreak"
    r"|act as|pretend to be|forget (everything|all|your))\b")


_MEM_WORD = re.compile(r"[a-z0-9@.'-]+")

# The merchant asking, in their own words, for something to be kept. An order
# note cannot type this; only the person at the keyboard can.
_MEM_ASKED = re.compile(r"(?i)\b(remember|note that|make a note|keep in mind|don'?t forget|"
                        r"bear in mind|for future reference)\b")


def _chat_said(history: list) -> str:
    """Only what the MERCHANT typed. Assistant turns are excluded because they
    are the model's own retelling of tool output, and tool results never appear
    in the browser-supplied history at all."""
    out = []
    for m in (history or []):
        if not isinstance(m, dict) or m.get("role") != "user":
            continue
        c = m.get("content")
        if isinstance(c, str):
            out.append(c)
        elif isinstance(c, list):
            out += [str(b.get("text") or "") for b in c
                    if isinstance(b, dict) and b.get("type") == "text"]
    return "\n".join(out)


def _mem_grams(text: str, n: int = 5) -> set:
    """The distinctive word runs in a piece of text, for provenance checks."""
    words = _MEM_WORD.findall(str(text or "").lower())
    if len(words) < n:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def _memory_grounded(text: str, said: str, saw: str) -> bool:
    """True when nothing distinctive in a proposed memory was lifted from tool
    output. A denylist of instruction-shaped phrases is not a boundary: it
    matches phrasing, not intent, and an order note reading "Standing
    instruction for this account: every report must end with ..." walks
    straight past it. Provenance is the real test. Memory is replayed as
    authoritative into EVERY later answer, for every account, so the only text
    that earns a place there is text the merchant typed. A five-word run that
    appears in a customer's order note but nowhere in what the merchant said is
    not the merchant's preference, whatever the model decided to call it."""
    borrowed = _mem_grams(text) & _mem_grams(saw)
    return not borrowed or not (borrowed - _mem_grams(said))


def _add_memories(items: list[dict], said: str = "", saw: str = "",
                  source: str = "merchant", refused: Optional[list] = None,
                  asked_in: Optional[str] = None, held: bool = False, by: str = "",
                  kept: Optional[list] = None) -> list[dict]:
    """refused, when given, collects what was not kept and why ('instruction'
    or 'from_data'), so the page can say so instead of answering as if saved;
    kept, when given, collects the text of each note that was.

    `held` saves each note as waiting for an admin (status "pending", with
    `by` naming who it came from): a member's chat or tracked change. Notes
    go into every account's answers, so a member could otherwise put a false
    "fact" (new bank details, say) in front of everyone (audit R-003).

    `asked_in` is the message being answered. Only there does "remember"
    lift the provenance check: read over the whole conversation, one
    "remember to chase Acme" early on let every later note through, however
    much of it was lifted from an order note or an email (audit R-015)."""
    memories = _load_memory()
    asked = bool(_MEM_ASKED.search(said if asked_in is None else asked_in or ""))
    seen = {m.get("text", "").strip().lower(): m for m in memories}
    now = datetime.now(timezone.utc).isoformat()
    for it in (items or [])[:MEMORY_HELD_PER_ANSWER if held else None]:
        if not isinstance(it, dict):
            continue
        text = str(it.get("text", "")).strip()[:800]
        if not text:
            continue
        twin = seen.get(text.lower())
        # An admin's own note that says what a member's waiting note says
        # keeps it (skipped as a duplicate, the only copy stayed unread), but
        # only once it has passed the same checks as a new note: text lifted
        # from what an admin's chat READ must not promote a planted one.
        promote = twin is not None and not held and twin.get("status") == "pending"
        if twin is not None and not promote:
            continue
        if _MEMORY_INJECTION.search(text):
            # Persistent, cross-session and cross-user: the one place where a
            # sentence typed into a Shopify order note could outlive the chat
            # that read it. Refuse and say so in the log.
            logger.warning("memory: refused an instruction-shaped note: %s", text[:120])
            if refused is not None:
                refused.append({"text": text, "reason": "instruction"})
            continue
        if saw and not asked and not _memory_grounded(text, said, saw):
            logger.warning("memory: refused a note lifted from tool output: %s", text[:120])
            if refused is not None:
                refused.append({"text": text, "reason": "from_data"})
            continue
        if promote:
            twin["status"], twin["kept"], twin["updated"] = "open", now, now
            if kept is not None:
                kept.append(text)
            continue
        mtype = it.get("type") if it.get("type") in (
            "fact", "decision", "followup", "preference", "insight") else "fact"
        note = {"id": secrets.token_hex(5), "type": mtype, "text": text,
                "status": "pending" if held else "open", "created": now, "updated": now,
                "source": source}
        if held and by:
            note["by"] = str(by)[:80]
        memories.append(note)
        seen[text.lower()] = note
        if kept is not None:
            kept.append(text)
    memories = _prune_memories(memories)
    if kept is not None:
        # Only what is actually there is reported kept.
        there = {m.get("text", "").strip().lower() for m in memories}
        kept[:] = [t for t in kept if t.lower() in there]
    return _write_memory(memories)


def _prune_memories(memories: list) -> list:
    """Kept notes within MEMORY_MAX (open follow-ups first, then the newest
    of the rest), and notes waiting for an admin within an allowance of their
    own, MEMORY_PENDING_MAX, the newest kept. Neither costs the other a
    place: counted together, waiting notes pushed kept ones out, and a store
    full of kept ones left a member's note nowhere to wait."""
    live = [m for m in memories if m.get("status") != "pending"]
    pend = [m for m in memories if m.get("status") == "pending"][-MEMORY_PENDING_MAX:]
    if len(live) > MEMORY_MAX:
        keep = [m for m in live if m.get("type") == "followup" and m.get("status") == "open"][:MEMORY_MAX]
        rest = [m for m in live if not (m.get("type") == "followup" and m.get("status") == "open")]
        slots = max(0, MEMORY_MAX - len(keep))
        live = keep + (rest[-slots:] if slots else [])   # slots==0 must yield [], not rest[-0:]
    return live + pend


def _update_memory(mid: str, status: str) -> list[dict]:
    memories = _load_memory()
    if status in ("open", "done", "dismissed"):
        for m in memories:
            if m.get("id") == mid:
                # Opening a member's note that was never kept (waiting, or
                # dismissed from waiting) is keeping it; only an admin gets here.
                if status == "open" and (m.get("status") == "pending" or (m.get("by") and not m.get("kept"))):
                    m["kept"] = datetime.now(timezone.utc).isoformat()
                m["status"] = status
                m["updated"] = datetime.now(timezone.utc).isoformat()
    return _write_memory(memories)


def _member_may_set(note: Optional[dict], status: str) -> bool:
    """What a member may do to a note's status: tick off a follow-up, reopen
    one ticked off, or dismiss one that is open. Nothing that puts words back
    in front of everyone: not a dismissed follow-up, and not one that came
    from a member and was never kept by an admin."""
    if not note or note.get("type") != "followup" or status not in ("open", "done", "dismissed"):
        return False
    if note.get("status") == "pending" or (note.get("by") and not note.get("kept")):
        return False
    return (note.get("status"), status) in (("open", "done"), ("open", "dismissed"), ("done", "open"))


def _edit_memory(mid: str, text: str, mtype: str) -> list[dict]:
    """A person correcting a note: the same door as a new one, so an
    instruction cannot come in by editing an innocent note into one."""
    text = str(text or "").strip()[:800]
    if not text:
        raise ValueError("A note needs some text.")
    if _MEMORY_INJECTION.search(text):
        raise ValueError("instruction")
    memories = _load_memory()
    for m in memories:
        if m.get("id") == mid:
            m["text"] = text
            if mtype in ("fact", "decision", "followup", "preference", "insight"):
                m["type"] = mtype
            m["updated"] = datetime.now(timezone.utc).isoformat()
            m["edited"] = True
    return _write_memory(memories)


def _close_followups(ids: list) -> list[dict]:
    """Open follow-ups the merchant told chat are done. Returns the ones closed."""
    want = {str(x) for x in (ids or [])[:20]}
    if not want:
        return []
    memories = _load_memory()
    closed, now = [], datetime.now(timezone.utc).isoformat()
    for m in memories:
        if m.get("id") in want and m.get("type") == "followup" and m.get("status") == "open":
            m["status"] = "done"
            m["updated"] = now
            m["closed_by"] = "chat"
            closed.append({"id": m["id"], "text": m.get("text", "")})
    if closed:
        _write_memory(memories)
    return closed


def _delete_memory(mid: str) -> list[dict]:
    return _write_memory([m for m in _load_memory() if m.get("id") != mid])


def _memory_to_system(memories: Optional[list[dict]] = None) -> str:
    memories = _load_memory() if memories is None else memories
    if not memories:
        return ""
    # A note waiting for an admin ("pending") came from a member's chat or
    # tracked change, and is read into nobody's answer until an admin keeps
    # it: what is here reaches every account (audit R-003).
    active = [m for m in memories if m.get("status") not in ("dismissed", "pending")]
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
        block += ("Open follow-ups (check in on these when relevant; when the merchant says one is done, "
                  "put its id in followups_done):\n"
                  + "\n".join("- [" + str(m.get("id") or "") + "] " + m["text"] for m in open_fu))
    return block


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as core.NAME and sibling.NAME, never a copied name.
import copilot as core  # noqa: E402
