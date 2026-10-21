# The chat routes and the shop settings

**Approved 21 Oct 2026.** Stage 4, piece 15 of the 14 October engineering
audit, its end. Cameron approved all three parts. Nothing anyone sees changes.

## Why

On piece 14's branch (copilot.py 1,453 lines):

- **The chat routes** (`/api/chat`, `/api/chat/stream`) read two things
  `add_routes` builds from the registry it is handed: the chat's tools and
  `dispatch_for`, which binds each turn's asker to the tool gate. So they could
  not move. `add_routes` already hands the Shopify write capabilities to
  `gizmo/shopify.py` the same way it could hand these to the chat module; only
  `server.py` calls it, once.
- **The usage route** reads nothing `add_routes` builds.
- **The shop settings** (the app's client id and secret, the shop, the public
  base address) are read through `core.` by fifteen modules. The frozen print
  routes read the secret and the base address, which no test patches, so
  `copilot.py` may keep them as copies; tests patch the shop, which no frozen
  route reads. `copilot.py` binds `gizmo.config` only for `_env_num`, not by
  its module name, and the tool adds only to a module `copilot.py` binds.

## What changes

1. **The chat's tools on the chat module**: `add_routes` sets
   `assistant._chat_registry` and `assistant._chat_tools` once; `dispatch_for`
   becomes a chat module function, still binding the asker per turn. A
   declared change. Pinned first through the chat route: a member without the
   Customers tab is refused the customer tools inside their own turn. The two
   tests that describe the old shape (the per-run gate's text, the nested
   helpers' list) say the new one.
2. **The chat, chat stream and usage routes out**: `gizmo/routes/chat.py`.
3. **The shop settings to the floor**: `gizmo/config.py`; `copilot.py` keeps
   `SHOPIFY_API_SECRET` and `APP_BASE_URL` as copies for the frozen print
   routes. The tool learns to bind an existing module `copilot.py` does not
   bind by name yet (its toy test first).

A release note, "The chat's routes and the shop settings on their own": "The
chat's routes, the usage panel's and the shop's own settings now each live
with the rest of their area, so a change elsewhere cannot upset them. Nothing
looks different."

## Not in this piece

The stock bridge and its routes, the frozen print routes and their font, logo
and CORS helpers, `_spawn_bg`, `STORE_CONTEXT_CAP` (read by nothing; stage
6).
