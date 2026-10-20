# Skills, memory, store knowledge and the chat loop

**Approved 20 Oct 2026.** Stage 4, piece 8 of the 14 October engineering
audit. Cameron approved all three parts. Nothing anyone sees changes.

## Why

Measured with a `tools/move_area.py` dry run on piece 7's branch (e7ec20a):

- **Skills** (loading and saving, frontmatter, ranking, the reading pass,
  what goes into the AI's instructions): 53 statements, 687 lines, 2 routes;
  borrows only `_effort_for`. `skills` is a local in five functions, so the
  module is read as `skillbook`.
- **Memory** (adding, editing, follow-ups, the grounding check): 21
  statements, 227 lines, 1 route; borrows nothing. **Store knowledge** (what
  was learned from the store's site, and the learn run): 11 statements, 97
  lines, 2 routes.
- **The chat loop** (`run_chat`, the step words, the data previews, what
  happens after an answer): 16 statements, 295 lines. Its two routes read
  `tools` and `chat_registry`, which `add_routes` builds from the registry it
  is handed, so they stay where they are.
- The dry run did not flag that: the tool counted only `add_routes`'
  parameters and nested functions as names a moved route may not read, not
  the values it assigns. Moved, the chat routes would have failed only when a
  request came in.
- Five section headings in `copilot.py` now sit over code that is not theirs
  (Work sessions, Loan units, CRM, Shared inbox, Website enquiries): earlier
  moves took their sections and left a few unrelated statements behind them.

## What changes

1. **Skills out**: `gizmo/skills.py` (read as `skillbook`) and
   `gizmo/routes/skills.py` (`/api/skills`, `/api/skills/read`).
2. **Memory and store knowledge out**: `gizmo/memory.py` (`memory`),
   `gizmo/knowledge.py` (`knowledge`), `gizmo/routes/memory.py`
   (`/api/memory`), `gizmo/routes/knowledge.py` (`/api/learn`,
   `/api/learn/run`).
3. **The chat loop out**: `gizmo/chat.py` (read as `assistant`). The chat
   routes stay in `add_routes`. The chat's system prompt stays in
   `copilot.py`: it is built from the shared writing style as the app loads.
   The move tool refuses a route that reads any value `add_routes` binds
   (its toy test first).

Also: the five stranded headings say what is under them now (comments only).

A pure move: the settings of each area move with it, nothing is declared.
A release note: "Skills, memory and chat on their own": "The assistant's
skills, its memory, what it has learned about the store and the chat itself
now each live on their own, so a change elsewhere cannot upset them. Nothing
looks different."

## Not in this piece

The chat routes and the tool list they use, the store profile, the analysis
cache, impact tracking, AI usage and cost, the AI report tabs (overview, SEO,
keywords, customers), the release notes, the scheduler, reconciliation, the
Xero connector, the stock bridge, the frozen print routes.
