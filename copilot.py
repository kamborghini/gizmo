#!/usr/bin/env python3
"""
Reactor — an embedded Shopify admin chat backed by Claude.

This module adds an in-admin chat experience to the existing MCP server:
  GET  /            -> serves the chat page (App Bridge when embedded)
  POST /api/chat    -> runs a Claude tool-use loop over the store's data

It REUSES the Shopify tool functions already defined in server.py (passed in
as a registry), so there is one source of truth for Shopify API access.

Auth (embedded-only): every API request must carry a verified Shopify session
token (Bearer JWT from App Bridge). There is no password fallback.

Required env vars:
  ANTHROPIC_API_KEY     Claude API key (sk-ant-...). Required to chat.
  ANTHROPIC_MODEL       Optional. Defaults to claude-opus-5-5.
  SHOPIFY_API_KEY       App client ID. Enables App Bridge + session-token auth.
  SHOPIFY_API_SECRET    App client secret. Verifies session tokens.
"""
import glob
import os
import sys
import re
import html
import json
import time
import hmac
import threading
import atexit
import base64
import hashlib
import socket
import unicodedata
import bisect
import types
import asyncio
import logging
import secrets
import ipaddress
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import contextvars
from typing import Any, Callable, Optional
from urllib.parse import urlparse, urljoin, quote

import anthropic
import httpx
import jwt
import eori
import perf
import pagesource
import mailmime
import google_mail
import pipedrive
from gizmo import background
try:
    import worldoptions
except Exception:                     # keep the app booting if the connector is unavailable
    worldoptions = None
from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse

import logdrain
import tokenvault
import totp
# Moved out of this file (stage 4 of the 14 October audit): the dispatch desk
# and its routes. Read as desk.NAME; they read this file as core.NAME.
from gizmo.config import _env_num
from gizmo.store import StoreUnwritable
from gizmo import store as jsonstore
from gizmo import errors
from gizmo import ai as claude
from gizmo import dispatch as desk
# The printed labels' route is frozen byte for byte (t_the_printed_sheets_do_not_change),
# so it reads these two by their own names. A copy is safe only for a name no
# test patches and nothing rebinds, which t_no_test_patches_a_name_nobody_reads checks.
from gizmo.dispatch import LABEL_STOCK_MM, _load_dispatch
from gizmo.routes import dispatch as routes_dispatch
# Moved out of this file (stage 4): accounts and sign-in, the door, the
# activity log. Read as team.NAME, gate.NAME, activity.NAME, except eight it
# reads by their own names: the six the frozen print route reads, and _guard
# and _json, the door every route here opens with and the answer it gives (a
# copy is safe only for a name no test patches and nothing rebinds, which
# t_no_test_patches_a_name_nobody_reads checks).
from gizmo import activity, gate, team
from gizmo.team import _live_uid, _uid_has_tab, _verify_session_token
from gizmo.gate import _API_HEADERS, _guard, _json, _pre_checks
from gizmo.activity import _track
from gizmo.routes import team as routes_team
# Moved out of this file (stage 4): the way to Shopify, the order book,
# production and the Size list. Read as shopify., orderbook., production.,
# size_list., except the five the frozen print route reads, by their own names.
from gizmo import orderbook, production, shopify, size_list
from gizmo.production import _LABEL_LOGO_SVG, _load_prod_state, _mark_printed, _release_bg, run_production_labels
# Moved out of this file (stage 4): the CRM and the shared inbox, with their
# routes. Read as salesdesk.NAME (crm is a local name) and mail.NAME.
from gizmo import crm as salesdesk, mail
from gizmo.routes import crm as routes_crm, mail as routes_mail
# Moved out of this file (stage 4): Files (the office file server on the R2 bucket) and the Finder drive, with their routes.
from gizmo import files as fileserver
from gizmo import webdav
from gizmo.routes import files as routes_files
# Moved out of this file (stage 4): customer-data erasure, the loan register and work sessions, with their routes.
from gizmo import privacy
from gizmo import loans
from gizmo import work
from gizmo.routes import privacy as routes_privacy
from gizmo.routes import loans as routes_loans
from gizmo.routes import work as routes_work
# The stock sheet (the stock move, plan 2a), with its routes.
from gizmo.routes import stock as routes_stock
# Moved out of this file (stage 4): the routes of production, the Size list and the order book, following their areas.
from gizmo.routes import production as routes_production
from gizmo.routes import size_list as routes_size_list
from gizmo.routes import orderbook as routes_orderbook
# Moved out of this file (stage 4): skills, memory, store knowledge and the chat loop, the first three with their routes.
from gizmo import skills as skillbook
from gizmo import memory
from gizmo import knowledge
from gizmo import chat as assistant
from gizmo.routes import skills as routes_skills
from gizmo.routes import memory as routes_memory
from gizmo.routes import knowledge as routes_knowledge
# Moved out of this file (stage 4): the AI's instructions. (SEO and keywords and the overview and customer reports were removed on 22 Oct 2026.)
from gizmo import prompts
# Moved out of this file (stage 4): the scheduler and alerts, release notes and requests, impact tracking and backup, with their routes.
from gizmo import scheduler
from gizmo import updates
from gizmo import impact
from gizmo import backup
from gizmo.routes import scheduler as routes_scheduler
from gizmo.routes import updates as routes_updates
from gizmo.routes import impact as routes_impact
from gizmo.routes import backup as routes_backup
# Moved out of this file (stage 4): the chase desk and credit terms, the Xero sync settings and the forecast hooks, with their routes. (Reconciliation was removed on 22 Oct 2026.)
from gizmo import liability
from gizmo import xero_sync as xerosync
from gizmo import forecasting
from gizmo.routes import liability as routes_liability
from gizmo.routes import xero_sync as routes_xero_sync
from gizmo.routes import forecasting as routes_forecasting
# Moved out of this file (stage 4): the page and its assets, the store profile and layouts, the sign-in walks' states and page, and the status page, with their routes.
from gizmo import rendering
from gizmo import profile as store_profile
from gizmo import layouts
from gizmo import oauth
from gizmo import status as appstatus
from gizmo.routes import rendering as routes_rendering
from gizmo.routes import profile as routes_profile
from gizmo.routes import layouts as routes_layouts
from gizmo.routes import status as routes_status
# Moved out of this file (stage 4): the London clock, which the whole app reads.
from gizmo import clock
# Moved out of this file (stage 4): the chat's, the stream's and the usage panel's routes.
from gizmo import config
from gizmo.routes import chat as routes_chat
from gizmo.config import APP_BASE_URL, SHOPIFY_API_SECRET
logger = logging.getLogger("shopify_mcp.copilot")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
STORE_CONTEXT_CAP  = _env_num(int, os.environ.get("STORE_CONTEXT_CAP", "4000"), "4000", "STORE_CONTEXT_CAP")


# ---------------------------------------------------------------------------
# Stock bridge: the glass a Mark made consumes flows into the stock app.
#
# Zeta (the stock app) is the shelf's ledger; this desk is where the shelf
# actually empties. Marking an order made resolves its items into glass lines
# (the same resolution the day sheet uses) and pushes them to zeta, which
# books them exactly like a count-down: stock falls, usage rises, the reorder
# engine sees it. Un-marking pushes a reversal. Zeta is idempotent per order,
# so a repeat or a retry can never double-book.
#
# The push must never hold the workbench hostage: Mark made succeeds locally
# first, and a failed push (zeta down, network blip) parks the order id in a
# pending store on the volume that the scheduler retries every tick.
# ---------------------------------------------------------------------------
ZETA_URL = os.environ.get("ZETA_URL", "").strip().rstrip("/")
ZETA_SYNC_TOKEN = os.environ.get("ZETA_SYNC_TOKEN", "").strip()
ZETA_SYNC_PATH = os.environ.get("ZETA_SYNC_PATH", "/data/zeta_sync.json")
ZETA_DRAIN_MAX = _env_num(int, os.environ.get("ZETA_DRAIN_MAX", "40"), "40", "ZETA_DRAIN_MAX")        # retries per tick
ZETA_DRAIN_SECONDS = _env_num(float, os.environ.get("ZETA_DRAIN_SECONDS", "45"), "45", "ZETA_DRAIN_SECONDS")  # and its deadline
ZETA_MAX_TRIES = _env_num(int, os.environ.get("ZETA_MAX_TRIES", "20"), "20", "ZETA_MAX_TRIES")        # then park for a human
_zeta_last = {"ok_at": 0.0, "error": ""}


def _zeta_configured() -> bool:
    return bool(ZETA_URL and ZETA_SYNC_TOKEN)


def _load_zeta_pending() -> dict:
    return jsonstore._load_json_store(ZETA_SYNC_PATH, "pending", {}) or {}


_zeta_locks: dict = {}


def _zeta_lock(order_id) -> "asyncio.Lock":
    """One lock per order: a drain retry and a fresh click for the same order
    must serialise, or an in-flight stale booking could land after a newer
    reversal and leave the stock app holding glass for an un-made order."""
    key = str(order_id)
    lock = _zeta_locks.get(key)
    if lock is None:
        if len(_zeta_locks) > 500:
            for k in [k for k, l in _zeta_locks.items() if not l.locked()][:250]:
                _zeta_locks.pop(k, None)
        lock = _zeta_locks[key] = asyncio.Lock()
    return lock


def _write_zeta_pending(p: dict) -> bool:
    """True when the queue actually reached disk. The caller's wording depends
    on it: promising "the app will keep retrying" over a write that silently
    failed would turn a lost booking into a reassuring toast."""
    try:
        if not jsonstore._store_writable(ZETA_SYNC_PATH):
            return False
        jsonstore._write_json_store(ZETA_SYNC_PATH, "pending", p)
        return True
    except Exception:
        logger.exception("stock bridge: could not save the pending queue")
        return False


_ZETA_LINE_KEYS = ("size", "family", "qty", "note")


def _zeta_lines(lines: list) -> list:
    """Usage lines in the stock app's own contract and nothing more. The lines
    carry fields for this app's screens (which rows are stock gobos, by name);
    an external endpoint that validates strictly would refuse a push over one
    extra key, and a refused push parks the order for retry indefinitely."""
    return [{k: ln[k] for k in _ZETA_LINE_KEYS if k in ln} for ln in lines]


async def _zeta_send(op: str, order_id, order_name: str, lines: list) -> dict:
    """One push to zeta. Separate so tests can stand in a fake transport."""
    async with httpx.AsyncClient(timeout=10.0) as cl:
        r = await cl.post(ZETA_URL + "/api/sync/consumption",
                          headers={"Authorization": "Bearer " + ZETA_SYNC_TOKEN},
                          json={"op": op, "order_id": str(order_id),
                                "order_name": order_name, "lines": lines})
        r.raise_for_status()
        return r.json()


USAGE_SHEETS_PATH = os.environ.get("USAGE_SHEETS_PATH", "/data/usage_sheets.json")


async def _zeta_send_sheet(payload: dict) -> dict:
    """One usage sheet to zeta. Separate so tests can stand in a fake."""
    async with httpx.AsyncClient(timeout=20.0) as cl:
        r = await cl.post(ZETA_URL + "/api/sync/usage-sheet",
                          headers={"Authorization": "Bearer " + ZETA_SYNC_TOKEN},
                          json=payload)
        r.raise_for_status()
        return r.json()


async def _zeta_push(registry: dict, order_id, op: str) -> str:
    """Book or reverse one order at the stock app. Returns '' on success or a
    short note for the operator; failure always parks the order for retry."""
    if not _zeta_configured():
        return ""
    async with _zeta_lock(order_id):
        return await _zeta_push_locked(registry, order_id, op)


async def _zeta_push_locked(registry: dict, order_id, op: str) -> str:
    try:
        if op == "book":
            res = await run_production_labels(registry, order_id=int(order_id))
            orders = (res or {}).get("orders") or []
            if not orders:
                raise RuntimeError("order could not be read")
            o = orders[0]
            await _zeta_send("book", order_id, str(o.get("name") or ""), _zeta_lines(_usage_lines(o)))
        else:
            await _zeta_send("reverse", order_id, "", [])
        # The queue is reloaded AT write time, never carried across the await:
        # a concurrent push's outcome must not be overwritten by this one's
        # stale snapshot of the queue.
        pending = _load_zeta_pending()
        pending.pop(str(order_id), None)
        _write_zeta_pending(pending)
        _zeta_last["ok_at"], _zeta_last["error"] = time.time(), ""
        return ""
    except Exception as e:
        # The op recorded is the LATEST intent: made-then-unmade while zeta is
        # down must end as a reverse, not replay a stale book.
        pending = _load_zeta_pending()
        pending[str(order_id)] = {"op": op, "at": salesdesk._crm_now(),
                                  "tries": int((pending.get(str(order_id)) or {}).get("tries") or 0) + 1}
        parked = _write_zeta_pending(pending)
        _zeta_last["error"] = f"{type(e).__name__}: {e}"[:200]
        logger.warning("stock bridge: %s for order %s failed (%s); %s",
                       op, order_id, type(e).__name__,
                       "queued for retry" if parked else "AND THE QUEUE COULD NOT BE SAVED")
        if not parked:
            errors._record_error("booking made glass at the stock app", e)
            return ("The stock app was not updated AND the retry could not be saved. "
                    "Adjust this order's stock by hand, or press Mark made again later.")
        return "The stock app could not be updated just now; the app will keep retrying."


def _zeta_catalog_combos() -> list:
    """Every consumption line this app can produce. Sheet sizes pass through
    the bezel rule first: an 86 or 100 order sends 64.9 glass plus a ring, so
    the catalogue lists those lines, never 86 glass that will not exist."""
    sheet = sorted({str(e.get("production_size") or "").strip()
                    for entries in (size_list._gobo_sizes().get("by_model") or {}).values()
                    for e in entries if str(e.get("production_size") or "").strip()},
                   key=lambda v: (float(v) if v.replace(".", "", 1).isdigit() else 9999))
    glass, rings = [], []
    for sz in sheet:
        cut = _BEZEL_UP.get(sz)
        if cut:
            rings.append(sz)
            if cut not in glass and cut not in sheet:
                glass.append(cut)
        else:
            glass.append(sz)
    combos = [{"family": fam, "size": sz} for sz in glass for fam in ("Mono", "HM", "Colour")]
    combos += [{"family": "Ring", "size": sz} for sz in rings]
    return combos


async def _zeta_send_catalog() -> None:
    """Publish the catalogue so the stock app's mapping view shows the whole
    translation rather than only the lines that have already parked."""
    combos = _zeta_catalog_combos()
    async with httpx.AsyncClient(timeout=10.0) as cl:
        r = await cl.post(ZETA_URL + "/api/sync/catalog",
                          headers={"Authorization": "Bearer " + ZETA_SYNC_TOKEN},
                          json={"combos": combos[:500]})
        r.raise_for_status()


async def _zeta_drain(registry: dict) -> None:
    """Retry everything parked, once per scheduler tick. Never raises.

    The op is re-read from the store under the order's lock, never taken from
    this loop's snapshot: while one retry was in flight the merchant may have
    changed their mind, and the LATEST intent is the only one that may run."""
    if not _zeta_configured():
        return
    # Capped and deadlined. Each retry is a full Shopify order read plus a
    # POST, so an unbounded backlog monopolised the hourly tick and starved
    # every other scheduled job behind it.
    started = time.monotonic()
    for oid in list(_load_zeta_pending().keys())[:ZETA_DRAIN_MAX]:
        if time.monotonic() - started > ZETA_DRAIN_SECONDS:
            logger.info("stock bridge: drain hit its deadline; the rest waits for the next tick")
            break
        try:
            async with _zeta_lock(oid):
                entry = _load_zeta_pending().get(str(oid))
                if not entry:
                    continue   # settled by a fresh click while we waited
                # An entry that has failed this many times is not going to
                # settle by being retried forever. Park it as needing a human
                # and stop spending the tick on it - it stays in the store, so
                # nothing is lost and Settings can still show it.
                pend = _load_zeta_pending()
                cur = pend.get(str(oid)) or entry
                tries = int(cur.get("tries") or 0)
                if tries >= ZETA_MAX_TRIES:
                    if not cur.get("stuck"):
                        cur["stuck"] = True
                        pend[str(oid)] = cur
                        _write_zeta_pending(pend)
                        logger.error("stock bridge: %s parked after %d attempts", oid, tries)
                    continue
                # A failed attempt is counted once, by _zeta_push_locked. The
                # drain counted it too, so every tick was two tries and an
                # order was parked for a human after ten attempts, not twenty.
                await _zeta_push_locked(registry, oid, str(entry.get("op") or "book"))
        except Exception:
            logger.exception("stock bridge: drain failed for %s", oid)


# An 86mm or 100mm gobo is not cut from 86 or 100 glass: it is a 64.9mm blank
# bezelled up to the ordered diameter by a ring. The usage lines must say what
# the bench actually consumes, or the stock sheet drifts one ring and one
# mis-sized blank at a time.
_BEZEL_UP = {"86": "64.9", "100": "64.9"}   # ordered size -> the glass it is cut from


def _usage_lines(shaped_order: dict) -> list:
    """One shaped label order as consumption lines.

    Resolvable items become {size, family, qty}; a bezelled size becomes TWO
    lines, the glass blank it is cut from plus the ring that brings it up to
    the ordered diameter. Anything the size lookup flagged for review, or that
    carries no size, becomes {size, family, qty, note} so the caller can show
    it rather than silently dropping glass. The same resolution feeds the day
    sheet and the stock-app push, so the two can never disagree about what a
    day's making consumed."""
    out = []
    for it in shaped_order.get("items", []):
        # Ruled not a gobo: nothing is cut, so no glass is used and there is
        # nothing to resolve. Not a line of any kind, here or in the stock app.
        if it.get("not_gobo"):
            continue
        qty = int(it.get("quantity") or 1)
        # Original vs Copy is the same physical blank: group stock by the
        # glass family ("Mono - Original" and "Mono - Copy" -> "Mono").
        family = re.split(r"\s+-\s+", it.get("glass_type") or "")[0].strip() or "(type not recorded)"
        if it.get("stock") and not it.get("production_size") and not it.get("review_reason"):
            # Named, not sized, and not a problem: carried by name rather than
            # as "no size resolved". The stock app gets the row shape it has
            # always had (see _zeta_lines); the name travels in the note.
            name = str(it.get("title") or "stock gobo")[:160]
            out.append({"size": "", "family": family, "qty": qty,
                        "note": ("stock gobo: " + name)[:200], "stock": name})
            continue
        if it.get("review_reason") or not it.get("production_size"):
            out.append({"size": str(it.get("production_size") or ""), "family": family,
                        "qty": qty, "note": str(it.get("review_reason") or "no size resolved")[:200]})
            continue
        size = str(it["production_size"])
        glass = _BEZEL_UP.get(size)
        if glass:
            out.append({"size": glass, "family": family, "qty": qty})
            out.append({"size": size, "family": "Ring", "qty": qty})
        else:
            out.append({"size": size, "family": family, "qty": qty})
    return out


def _usage_row_order(r: dict) -> tuple:
    """Largest glass first, then by family; a size that is not a number (a
    sheet cell edited to "TBC") goes last instead of taking the whole day
    sheet down with it, which one float() of it used to do."""
    try:
        return (0, -float(r["size"]), str(r["glass"]))
    except (TypeError, ValueError):
        return (1, 0.0, str(r.get("size") or ""), str(r.get("glass") or ""))


async def run_stock_usage(registry: dict, date_str: str) -> dict:
    """Estimated stock used on one day: every order whose Mark made stamp falls
    inside the selected day (UK time), its items resolved through the same size
    lookup the labels print with, summed by glass size + type. Items that don't
    resolve are listed separately, never silently dropped. No AI."""
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Europe/London")
    try:
        day = datetime.strptime(str(date_str or ""), "%Y-%m-%d").date()
    except ValueError:
        return {"error": "Pick a valid date."}
    start = datetime.combine(day, datetime.min.time(), tzinfo=tz)
    end = start + timedelta(days=1)
    # Live state plus the archive of evicted made stamps, so a past day still
    # sees orders that fell out of the capped live state.
    stamps = {oid: e.get("made_at") for oid, e in _load_prod_state().items() if e.get("made_at")}
    for oid, ma in production._archived_made(set()).items():
        stamps.setdefault(oid, ma)
    made_ids = []
    for oid, raw in stamps.items():
        try:
            made = datetime.fromisoformat(raw)
            if made.tzinfo is None:
                made = made.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        if start <= made.astimezone(tz) < end:
            made_ids.append(int(oid))
    made_ids = made_ids[:150]
    st_once, dp_once = _load_prod_state(), _load_dispatch()
    fetched = await asyncio.gather(*[run_production_labels(registry, order_id=i,
                                                           state=st_once, dispatch=dp_once)
                                     for i in made_ids], return_exceptions=True)
    rows: dict = {}
    unresolved: dict = {}
    stock: dict = {}
    orders_in, pieces, fetch_failed, unread, gone = [], 0, 0, [], []
    for oid, res in zip(made_ids, fetched):
        if isinstance(res, dict) and res.get("missing"):
            # Shopify no longer has it (a deleted test order). Asking again
            # will not bring it back, so it is left out of the sheet rather
            # than holding the day's sheet for good; its own booking stands.
            gone.append(oid)
            continue
        if not isinstance(res, dict) or not res.get("orders"):
            fetch_failed += 1   # a made order whose fetch was throttled/failed
            unread.append(oid)
            continue
        for o in (res.get("orders") or []):
            orders_in.append(str(o.get("name") or ""))
            for line in _usage_lines(o):
                pieces += line["qty"]
                if line.get("stock"):
                    stock[line["stock"]] = stock.get(line["stock"], 0) + line["qty"]
                    continue
                if line.get("note"):
                    nm = str(o.get("name") or "")
                    unresolved[nm] = unresolved.get(nm, 0) + line["qty"]
                    continue
                key = (line["size"], line["family"])
                r = rows.setdefault(key, {"size": line["size"], "glass": line["family"], "qty": 0})
                r["qty"] += line["qty"]
    out_rows = sorted(rows.values(), key=_usage_row_order)
    return {"date": day.isoformat(), "orders": len(orders_in), "order_names": orders_in[:60],
            "order_ids": [i for i in made_ids if i not in gone], "pieces": pieces, "rows": out_rows,
            "fetch_failed": fetch_failed, "unread_ids": unread, "gone_ids": gone,
            "unresolved": [{"name": k, "qty": v} for k, v in sorted(unresolved.items())],
            "stock": [{"name": k, "qty": v} for k, v in sorted(stock.items())]}


# ---------------------------------------------------------------------------
# Work after a request: a coroutine run once the answer has gone, holding a
# reference so it is not collected before it runs.
# ---------------------------------------------------------------------------


def _spawn_bg(coro) -> bool:
    """The printed-label route's name for background.spawn (gizmo/background.py):
    that route's source is frozen, so it keeps calling this, which hands on."""
    return background.spawn(coro)

# ---------------------------------------------------------------------------
# Route registration (mounted onto the existing MCP server app)
# ---------------------------------------------------------------------------
_font_cache: dict = {}


def _brand_svg(name: str):
    # Projected Image's wordmark, from projectedimage.com, served like the
    # label typeface. It has no script in it, and the response forbids any all
    # the same, in case it is ever opened on its own rather than as an image.
    key = "brand:" + name
    if key not in _font_cache:
        try:
            with open(os.path.join(os.path.dirname(__file__), "data", "brand", name), "rb") as fh:
                _font_cache[key] = fh.read()
        except OSError:
            return PlainTextResponse("Not found", status_code=404)
    return Response(_font_cache[key], media_type="image/svg+xml",
                    headers={**_API_HEADERS, "Cache-Control": "public, max-age=86400",
                             "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"})


_PRINT_ORIGINS = {"https://extensions.shopifycdn.com", "https://admin.shopify.com"}

def _print_cors(request: Request) -> dict:
    origin = request.headers.get("origin") or ""
    base = {"Access-Control-Allow-Headers": "Authorization, Content-Type",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Max-Age": "600"}
    own_shop = f"https://{config.SHOPIFY_STORE}.myshopify.com" if config.SHOPIFY_STORE else ""
    if origin in _PRINT_ORIGINS or (own_shop and origin == own_shop):
        return {**base, "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true", "Vary": "Origin"}
    # Vary here too: without it a shared cache could store this wildcard
    # reply and serve it back to an allowlisted origin, breaking the
    # credentialed print action until the cache expired.
    return {**base, "Access-Control-Allow-Origin": "*", "Vary": "Origin"}


def add_routes(mcp, registry: dict, order_tag_writer=None, fulfillment_writer=None,
               fulfillment_canceler=None, webhook_ensurer=None,
               payment_terms_writer=None, order_writer=None,
               scope_reader=None, tax_id_reader=None, forecast_reader=None,
               install_checker=None, customer_checker=None, product_meta_reader=None,
               api_version: str = "") -> None:
    # The write capabilities the server hands over. None of them ever joins any
    # tool registry: the AI can read the store; only the app's own print / Mark
    # made / Dispatch actions can touch tags or fulfillments.
    shopify._api_version = api_version
    shopify._product_meta_reader = product_meta_reader
    shopify._customer_checker = customer_checker
    shopify._scope_reader = scope_reader
    shopify._forecast_reader = forecast_reader
    shopify._install_checker = install_checker
    shopify._tax_id_reader = tax_id_reader
    shopify._order_tag_writer = order_tag_writer
    shopify._fulfillment_writer = fulfillment_writer
    shopify._fulfillment_canceler = fulfillment_canceler
    shopify._webhook_ensurer = webhook_ensurer
    shopify._payment_terms_writer = payment_terms_writer
    shopify._order_writer = order_writer
    desk._wo_boot()
    # The Shopify tools: the registry this app was handed.
    chat_registry = dict(registry)
    tools = assistant._build_tools(chat_registry)
    # The chat's tools, from the registry this app was handed, kept on the chat
    # module as the write capabilities are kept on shopify: the chat routes read
    # them there, and assistant.dispatch_for binds each turn's asker.
    assistant._chat_registry = chat_registry
    assistant._chat_tools = tools

    logger.info(f"Copilot enabled — embedded-only; models: fast={claude.MODEL_FAST}, deep={claude.MODEL_DEEP}; "
                f"effort={claude.ANTHROPIC_EFFORT}, deep effort={claude.ANTHROPIC_EFFORT_DEEP}; max_tokens={claude.MAX_TOKENS}; tools: {len(tools)}")
    if not claude.ANTHROPIC_API_KEY:
        logger.warning("Copilot: ANTHROPIC_API_KEY not set. Chat will return an error until it is.")
    if not SHOPIFY_API_SECRET:
        logger.warning("Copilot: SHOPIFY_API_SECRET/CLIENT_SECRET not set. All API routes are locked "
                       "(session tokens can't be verified).")
    if not config.SHOPIFY_API_KEY:
        logger.warning("Copilot: SHOPIFY_API_KEY/CLIENT_ID not set. Session-token audience (aud) will "
                       "NOT be verified. Set it so tokens are validated against this app.")
    if not config.SHOPIFY_STORE:
        logger.warning("Copilot: SHOPIFY_STORE not set. Session tokens will NOT be pinned to a specific "
                       "shop (dest is unverified). Set SHOPIFY_STORE to lock the app to your store.")

    # The page and its assets (gizmo/routes/rendering.py), gathered where the first stood.
    routes_rendering.register(mcp, registry)

    # The order book's routes (gizmo/routes/orderbook.py), gathered where the first stood.
    routes_orderbook.register(mcp, registry)

    # The forecast's routes (gizmo/routes/forecasting.py), gathered where the first stood.
    routes_forecasting.register(mcp, registry)

    # The privacy routes (gizmo/routes/privacy.py), gathered where the first stood.
    routes_privacy.register(mcp, registry)

    # The status page and the health check (gizmo/routes/status.py), gathered where the first stood.
    routes_status.register(mcp, registry)

    # The chat's routes (gizmo/routes/chat.py), gathered where the first stood.
    routes_chat.register(mcp, registry)

    # The store profile's route (gizmo/routes/profile.py).
    routes_profile.register(mcp, registry)

    # The layouts route (gizmo/routes/layouts.py).
    routes_layouts.register(mcp, registry)

    # The memory route (gizmo/routes/memory.py).
    routes_memory.register(mcp, registry)

    # The skills' routes (gizmo/routes/skills.py), gathered where the first stood.
    routes_skills.register(mcp, registry)

    # The What's new route (gizmo/routes/updates.py).
    routes_updates.register(mcp, registry)

    # The schedule and alert routes (gizmo/routes/scheduler.py), gathered where the first stood.
    routes_scheduler.register(mcp, registry)

    # The impact route (gizmo/routes/impact.py).
    routes_impact.register(mcp, registry)

    # The store knowledge's routes (gizmo/routes/knowledge.py), gathered where the first stood.
    routes_knowledge.register(mcp, registry)

    # Production's routes (gizmo/routes/production.py), gathered where the first stood.
    routes_production.register(mcp, registry)

    # The Size list's routes (gizmo/routes/size_list.py), gathered where the first stood.
    routes_size_list.register(mcp, registry)

    # The shared inbox's routes (gizmo/routes/mail.py), gathered where the first
    # stood; their paths are literal, so no request changes hands.
    routes_mail.register(mcp, registry)

    # The backup and restore routes (gizmo/routes/backup.py), gathered where the first stood.
    routes_backup.register(mcp, registry)

    # The Liability routes (gizmo/routes/liability.py), gathered where the first stood.
    routes_liability.register(mcp, registry)

    # The CRM's routes (gizmo/routes/crm.py), gathered where the first
    # stood; their paths are literal, so no request changes hands.
    routes_crm.register(mcp, registry)

    # The Files routes and the Finder drive's (gizmo/routes/files.py), gathered where the first
    # stood; no other path starts with /dav, so no request changes hands.
    routes_files.register(mcp, registry)







    # The sign-in and team routes (gizmo/routes/team.py), registered here so
    # the route table keeps its order.
    routes_team.register(mcp, registry)

    # The loan register's route (gizmo/routes/loans.py).
    routes_loans.register(mcp, registry)

    # The work sessions' routes (gizmo/routes/work.py), gathered where the first stood.
    routes_work.register(mcp, registry)
    routes_stock.register(mcp, registry)

    @mcp.custom_route("/api/stock-usage", methods=["POST"])
    async def stock_usage_route(request: Request):
        # Glass blanks consumed by everything marked Made on one day. Read-only, no AI.
        err, body, _who = await _guard(request)
        if err:
            return err
        try:
            res = await run_stock_usage(registry, str(body.get("date") or ""))
            if not res.get("error"):
                # The day's send record rides along, so the page can say
                # "already sent" instead of letting a double-send surprise.
                sheets = jsonstore._load_json_store(USAGE_SHEETS_PATH, "sheets", {})
                if isinstance(sheets, dict) and res.get("date") in sheets:
                    rec = dict(sheets[res["date"]])
                    rec.pop("result", None)
                    res["sent"] = rec
            return _json(res, 400 if res.get("error") else 200)
        except Exception:
            logger.exception("Stock usage failed")
            return _json({"error": "Couldn't build the stock usage list."}, 500)

    @mcp.custom_route("/api/stock-usage/send", methods=["POST"])
    async def stock_usage_send_route(request: Request):
        """The reviewed day sheet goes to the stock app as FINAL figures. The
        stock app applies only the difference against what the automatic
        per-order bookings already recorded, so this can never double-count;
        re-sending a day REPLACES its previous sheet. Every line comes back
        with its own status, and the send is recorded here for the record of
        final-versus-estimate."""
        err, body, who = await _guard(request)
        if err:
            return err
        if not _zeta_configured():
            return _json({"error": "The stock app isn't connected: its address and sync "
                                   "token are not set on the server."}, 400)
        date_str = str(body.get("date") or "")
        raw = body.get("lines")
        if not isinstance(raw, list) or not raw or len(raw) > 100:
            return _json({"error": "The sheet needs between 1 and 100 lines."}, 400)
        lines = []
        for ln in raw:
            if not isinstance(ln, dict):
                continue
            family = str(ln.get("family") or "").strip()[:60]
            size = str(ln.get("size") or "").strip()[:40]
            try:
                final = int(round(float(ln.get("final"))))
                est = max(0, int(round(float(ln.get("estimated") or 0))))
            except (TypeError, ValueError, OverflowError):
                return _json({"error": f"The quantity for {family} {size} is not a number."}, 400)
            if not family or not size:
                return _json({"error": "Every line needs a glass type and a size."}, 400)
            if final < 0 or final > 10000:
                return _json({"error": f"The quantity for {family} {size} must be between "
                                       "0 and 10,000."}, 400)
            lines.append({"family": family, "size": size, "estimated": est, "final": final})
        if not lines:
            return _json({"error": "The sheet needs at least one line."}, 400)
        # The day's covered orders are recomputed HERE: the sheet's deltas are
        # measured against these orders' automatic bookings, and that list is
        # not something a page should be trusted to supply.
        try:
            usage = await run_stock_usage(registry, date_str)
        except Exception:
            logger.exception("stock usage recompute failed")
            return _json({"error": "Couldn't rebuild the day's order list."}, 500)
        if usage.get("error"):
            return _json({"error": usage["error"]}, 400)
        # FINAL figures replace what the per-order bookings recorded, for every
        # order named in the sheet. An order that could not be read has no
        # glass in these lines, so sending it would un-book what it used.
        if usage.get("fetch_failed"):
            n = int(usage.get("fetch_failed") or 0)
            ids = ", ".join(str(i) for i in (usage.get("unread_ids") or [])[:10])
            return _json({"error": f"{n} made order{'' if n == 1 else 's'} could not be read from "
                                   f"Shopify just now (order id {ids}), so the day's figures are "
                                   "incomplete. Nothing was sent; refresh the sheet in a moment and "
                                   "send it then."}, 409)
        payload = {"sheet_id": "day-" + usage["date"], "day": usage["date"],
                   "order_ids": [str(i) for i in (usage.get("order_ids") or [])],
                   "lines": lines}
        try:
            result = await _zeta_send_sheet(payload)
        except Exception as e:
            logger.warning("usage sheet send failed: %s", e)
            return _json({"error": "The stock app didn't accept the sheet. Nothing was "
                                   "recorded; check it is up and try again."}, 502)
        rec = {"sent_at": datetime.now(timezone.utc).isoformat(), "by": who,
               "lines": lines, "result": result, "replaced": bool(result.get("replaced"))}
        try:
            sheets = jsonstore._load_json_store(USAGE_SHEETS_PATH, "sheets", {})
            if not isinstance(sheets, dict):
                sheets = {}
            sheets[usage["date"]] = rec
            if jsonstore._store_writable(USAGE_SHEETS_PATH):
                jsonstore._write_json_store(USAGE_SHEETS_PATH, "sheets", sheets)
        except Exception:
            logger.exception("usage sheet record failed (the stock app HAS the sheet)")
        _track(who, "production", "sent a stock sheet",
               f"{usage['date']} · {len(lines)} line(s)"
               + (" · replaced the earlier send" if result.get("replaced") else ""))
        gone = usage.get("gone_ids") or []
        return _json({"ok": True, "sent": {"sent_at": rec["sent_at"], "by": who,
                                           "replaced": rec["replaced"]},
                      "result": result,
                      "note": (f"{len(gone)} made order{'' if len(gone) == 1 else 's'} Shopify no "
                               f"longer has (order id {', '.join(str(i) for i in gone[:10])}) "
                               f"{'was' if len(gone) == 1 else 'were'} left out of the sheet; "
                               "the glass booked for it stays booked." if gone else "")})





    # The dispatch desk's routes (gizmo/routes/dispatch.py), registered here
    # so the route table keeps its order.
    routes_dispatch.register(mcp, registry)


    @mcp.custom_route("/fonts/bricolage.woff2", methods=["GET"])
    async def label_font(request: Request):
        # The label typeface (Bricolage Grotesque, OFL). Public static bytes, no
        # data and no auth, cached hard so the print frame gets it instantly.
        if "woff2" not in _font_cache:
            try:
                with open(os.path.join(os.path.dirname(__file__), "data", "fonts", "bricolage.woff2"), "rb") as fh:
                    _font_cache["woff2"] = fh.read()
            except OSError:
                return PlainTextResponse("Not found", status_code=404)
        return Response(_font_cache["woff2"], media_type="font/woff2",
                        headers={**_API_HEADERS, "Cache-Control": "public, max-age=31536000, immutable"})



    @mcp.custom_route("/brand/logo.svg", methods=["GET"])
    async def brand_logo(request: Request):
        # The brand's own colours: dark lettering, for a light ground.
        return _brand_svg("projected-image-logo.svg")

    @mcp.custom_route("/brand/logo-light.svg", methods=["GET"])
    async def brand_logo_light(request: Request):
        # The same mark with white lettering, for the sidebar's ink frame,
        # where the dark lettering would vanish. The teal shield is unchanged.
        return _brand_svg("projected-image-logo-light.svg")

    @mcp.custom_route("/print/production-labels/sign", methods=["POST", "OPTIONS"])
    async def sign_label_doc(request: Request):
        """The print-action extension calls this with the merchant's id token and gets
        back a short-lived signed URL for the label document, which the admin's print
        preview can load without a session. 5 minute expiry."""
        cors = _print_cors(request)
        if request.method == "OPTIONS":
            return PlainTextResponse("", headers=cors)
        pre = _pre_checks(request)
        if pre:
            return pre
        # The print action runs INSIDE Shopify's order page, where App Bridge
        # gives the extension an id token and nothing else - it cannot carry
        # the app's own session (different origin, no shared storage). So the
        # embed token is the perimeter here: it proves the caller is signed
        # into THIS store's Shopify admin. _authorize additionally demands an
        # app session, which no extension can ever satisfy, so requiring it
        # made every print action 401 - the feature was dead, and a test that
        # only checked for the word "Unauthorized" kept quiet about it.
        # When a session IS present (the app's own UI) it is honoured below,
        # so in-app callers still meet the Production Manager tab check.
        if not SHOPIFY_API_SECRET:
            return JSONResponse({"error": "Unauthorized"}, status_code=401, headers={**_API_HEADERS, **cors})
        tok = ""
        auth_hdr = request.headers.get("authorization", "")
        if auth_hdr.startswith("Bearer "):
            tok = auth_hdr[7:]
        try:
            _verify_session_token(tok)
        except Exception:
            logger.warning("print-labels sign: 401 (auth header present=%s, origin=%s)",
                           bool(auth_hdr), request.headers.get("origin"))
            return JSONResponse({"error": "Unauthorized"}, status_code=401, headers={**_API_HEADERS, **cors})
        # The admin print-action extension runs in Shopify's own frame and
        # cannot carry an app session, so a session here cannot be REQUIRED.
        # What a session-less URL may DO is limited instead: see below, it
        # renders the document and stamps nothing.
        signer = _live_uid(request)
        if signer and not _uid_has_tab(signer, "labels"):
            return JSONResponse({"error": "Production Manager is switched off for your account."},
                                status_code=403, headers={**_API_HEADERS, **cors})
        body = await gate._read_json_capped(request)
        if body is None:
            return JSONResponse({"error": "Request too large."}, status_code=413, headers={**_API_HEADERS, **cors})
        raw_ids = str(body.get("ids") or "")[:2000]
        raw_size = str(body.get("size") or "4x6")
        if raw_size not in desk.LABEL_STOCK:
            raw_size = "4x6"
        # The action opens on the production printer's saved stock: which roll
        # is loaded is a shop setting, not something chosen at the print button.
        prod_size = desk._load_shipping().get("label_size_production")
        if prod_size not in desk.LABEL_STOCK:
            prod_size = desk._SHIPPING_DEFAULT["label_size_production"]
        if not raw_ids.strip():
            return JSONResponse({"error": "No order ids given."}, status_code=400, headers={**_API_HEADERS, **cors})
        exp = int(time.time()) + 300
        # A URL minted WITHOUT a gizmo account behind it is read-only. It can
        # still render the label document (whoever holds an embed token can
        # already read these orders in Shopify itself), but it cannot stamp
        # them printed or release them into production - which is a real
        # workflow change, and was reachable by anyone denied the tab.
        mode = "rw" if signer else "ro"
        sig = hmac.new(SHOPIFY_API_SECRET.encode(),
                       f"{raw_ids}|{exp}|{mode}".encode(), hashlib.sha256).hexdigest()
        base = (APP_BASE_URL.rstrip("/") if APP_BASE_URL
                else f"https://{request.headers.get('host', '')}")
        path = (f"/print/production-labels?ids={quote(raw_ids, safe='')}"
                f"&exp={exp}&mode={mode}&sig={sig}")
        logger.info("print-labels sign: ok ids=%s size=%s opens=%s", raw_ids[:120], raw_size, prod_size)
        return JSONResponse({"url": base + path, "path": path, "expires_in": 300, "size": prod_size},
                            headers={**_API_HEADERS, **cors})

    @mcp.custom_route("/print/production-labels", methods=["GET", "OPTIONS"])
    async def print_labels_doc(request: Request):
        """Printable label document for the admin print-action extensions. The admin's
        print modal loads this URL directly (with the embedded id_token appended, the
        same way it loads the app page) and shows it in the print preview, so the
        merchant prints without ever leaving the order. Accepts ?ids=<order ids or
        GIDs, comma separated> and optional ?size=4x2|4x3|4x4|4x6|2x4|a4."""
        if request.method == "OPTIONS":
            return PlainTextResponse("", headers=_print_cors(request))
        pre = _pre_checks(request)
        if pre:
            return pre

        logger.info("print-labels doc: ids=%s auth=%s origin=%s",
                    str(request.query_params.get("ids") or "")[:120],
                    "sig" if request.query_params.get("sig") else ("id_token" if request.query_params.get("id_token") else ("bearer" if request.headers.get("authorization") else "none")),
                    request.headers.get("origin"))
        doc_headers = {**_API_HEADERS, **_print_cors(request), "Cache-Control": "no-store"}

        def deny(msg: str):
            return HTMLResponse("<p style='font:14px sans-serif;padding:20px'>" + html.escape(msg) + "</p>",
                                status_code=401, headers=doc_headers)

        # Auth, any of three ways: a short-lived HMAC-signed URL (minted by the sign
        # endpoint for the print-action extensions; the admin's preview frame carries
        # no session of its own), the embedded id_token query param, or a bearer token.
        authed = False
        qp = request.query_params
        raw_ids = str(qp.get("ids") or "")
        exp_s, sig = str(qp.get("exp") or ""), str(qp.get("sig") or "")
        mode = "rw" if str(qp.get("mode") or "") == "rw" else "ro"
        if exp_s and sig and SHOPIFY_API_SECRET:
            try:
                # The mode is INSIDE the signature, so it cannot be upgraded by
                # editing the query string.
                expect = hmac.new(SHOPIFY_API_SECRET.encode(),
                                  f"{raw_ids}|{exp_s}|{mode}".encode(), hashlib.sha256).hexdigest()
                authed = int(exp_s) > time.time() and hmac.compare_digest(sig, expect)
            except (TypeError, ValueError):
                authed = False
        may_write = (not authed) or mode == "rw"
        doc_who = ""
        if not authed:
            token = qp.get("id_token") or ""
            if not token:
                auth = request.headers.get("authorization", "")
                if auth.startswith("Bearer "):
                    token = auth[7:]
            if not token or not SHOPIFY_API_SECRET:
                return deny("Unauthorized. Open this from your Shopify admin.")
            try:
                _verify_session_token(token)
            except Exception:
                return deny("Unauthorized. Open this from your Shopify admin.")
            # The embed token proves the request comes from inside the store's
            # Shopify admin, but NOT which gizmo account, so the Production
            # Manager tab restriction cannot be enforced from it alone. The
            # session-less entry is the SIGNED url (minted by /sign, which is
            # itself labels-gated); a bare id_token must carry a valid app
            # session with the labels tab, or a labels-denied Shopify admin
            # could hand-drive this URL to read orders and release them to
            # production. Earlier this check only ran "if doc_who" - so
            # omitting the header skipped it entirely.
            # A LIVE account only: _session_uid alone would accept a session
            # belonging to a switched-off, deleted, or still-on-its-starter-
            # password account, which every other route refuses.
            # REQUIRE the session, do not merely tolerate one. The previous
            # form ("if doc_who and not ...") described this rule in its
            # comment but never enforced it: with no x-app-session header
            # _live_uid returns "", the `and` short-circuits, and the check
            # was skipped entirely - so a Shopify admin whose gizmo account
            # was switched off, or explicitly denied this tab, could hand-drive
            # this URL with the id_token Shopify puts in the app frame, read
            # every order on it, and release them all to production.
            # The genuinely session-less caller is the admin print-action
            # extension, which does NOT come through here: it mints a signed
            # URL from /sign and arrives on the authed branch above.
            doc_who = _live_uid(request)
            if not doc_who:
                return deny("Open this from inside the app, or use the print button "
                            "on the order in Shopify.")
            if not _uid_has_tab(doc_who, "labels"):
                return deny("Production Manager is switched off for your account.")

        ids = []
        for part in str(request.query_params.get("ids") or "").split(","):
            m = re.search(r"(\d+)\s*$", part.strip())
            if m:
                ids.append(int(m.group(1)))
        requested = len(list(dict.fromkeys(ids)))
        ids = list(dict.fromkeys(ids))[:50]
        if not ids:
            return HTMLResponse("<p style='font:14px sans-serif;padding:20px'>No orders were selected.</p>",
                                headers=doc_headers)

        w, h = LABEL_STOCK_MM.get(str(request.query_params.get("size") or "4x6"), LABEL_STOCK_MM["4x6"])

        st_once, dp_once = _load_prod_state(), _load_dispatch()
        results = await asyncio.gather(*[run_production_labels(registry, order_id=i,
                                                               state=st_once, dispatch=dp_once)
                                         for i in ids], return_exceptions=True)
        orders, got_ids = [], set()
        for r in results:
            if isinstance(r, dict) and r.get("orders"):
                orders.append(r["orders"][0])
                got_ids.add(r["orders"][0].get("id"))
        dropped = [i for i in ids if i not in got_ids]
        # Rendering the print document IS the print moment for the admin print
        # extensions; stamp these orders as printed (best-effort, never raises)
        # and move their tags along in the background so the document itself
        # renders without waiting on Shopify writes.
        printed_ids = [o["id"] for o in orders if o.get("id")] if may_write else []
        stamped_ok = _mark_printed(printed_ids)
        if printed_ids and stamped_ok:
            _track(doc_who, "production", "printed labels",
                   str(len(printed_ids)) + (" order" if len(printed_ids) == 1 else " orders")
                   + " from the admin print action")
        if printed_ids:
            # A FULL release, not just the tag move: an account order that
            # reaches production still needs its 30-day terms, and half a
            # release is the state nobody notices until the invoice is due.
            # In practice this is unreachable from the print-action extensions,
            # which cannot carry an app session and so always get a read-only
            # URL; it fires only for a caller that came with its own token.
            _spawn_bg(_release_bg(registry, printed_ids))
        esc = html.escape
        sheets = []
        for o in orders:
            # The merchant's own label design: logo, big company name, "Order:" line,
            # then one-line item rows of qty+size in bold, a glass-type chip, and the
            # artwork title in quotes. Size comes from the sheet lookup.
            items = []
            for it in o.get("items", []):
                qty = esc(str(it.get("quantity", 1)))
                if it.get("review_reason"):
                    # Flagged rows may wrap: the reason must be readable, never ellipsized.
                    items.append("<li class='row'><div class='it wrap'><span class='iqs'>" + qty + "x</span>"
                                 + "<span class='chip fl'>CHECK</span><span class='desc'>"
                                 + esc(it["review_reason"]) + "</span></div></li>")
                    continue
                size = esc(it.get("production_size", ""))
                chip = ("<span class='chip'>" + esc(it["glass_type"]) + "</span>") if it.get("glass_type") else ""
                art = it.get("artwork", it.get("title", ""))
                # A row with no size (a projector, an accessory, a stock gobo)
                # has nothing to line up with: its name starts after the
                # count and wraps, rather than being cut short after a gap.
                row = ("<li class='row'><div class='" + ("it" if size else "it named wrap") + "'><span class='iqs'>"
                       + qty + "x"
                       + ((" " + size + "mm") if size else "") + "</span>" + chip
                       + (("<span class='desc'>&quot;" + esc(art) + "&quot;</span>") if art else "")
                       + "</div>")
                if it.get("size_note"):
                    row += "<div class='ctx'>" + esc(it["size_note"]) + "</div>"
                items.append(row + "</li>")
            status = o.get("status") or ""
            dead = ("<div class='dead'>DO NOT MAKE - " + esc(status.upper()) + "</div>"
                    if status in ("cancelled", "refunded") else "")
            # Deadline the customer gave, always visible when known; only its
            # emphasis changes as it gets close. Never a word about importance.
            pri = (("<span class='due" + (" soon" if o.get("due_soon") else "") + "'>Required by: "
                    + esc(o["due_label"]) + "</span>") if o.get("due_label") else "")
            note = (("<div class='onote'><b>Note:</b> " + esc(o["note"]) + "</div>")
                    if o.get("note") else "")
            sheets.append(
                "<div class='sheet'>" + dead + "<div class='top'>"
                + "<div class='logo'>" + _LABEL_LOGO_SVG + "</div>"
                + "<div class='company'>" + esc(o.get("display_name", "")) + "</div>"
                + "<div class='ono'>Order: " + esc(str(o.get("name") or ("#" + str(o.get("order_number", ""))))) + pri + "</div></div>"
                + "<ul class='items'>" + "".join(items) + "</ul>" + note
                + "<div class='rate'><div class='rt'><div class='r1'>&#9733;&#9733;&#9733;&#9733;&#9733; 5 Star Service</div>"
                + "<div class='r2'>Leave us a review on <b>Trustpilot</b></div></div></div></div>")
        if not sheets:
            return HTMLResponse("<p style='font:14px sans-serif;padding:20px'>Those orders could not be found.</p>",
                                headers=doc_headers)
        if dropped:
            # A throttled or failed fetch must never silently vanish an order from
            # a batch print: lead with a loud sheet naming the missing ones.
            names = ", ".join("#" + str(i) for i in dropped[:20])
            sheets.insert(0, ("<div class='sheet'><div class='dead'>" + str(len(dropped))
                              + " SELECTED ORDER(S) COULD NOT BE LOADED</div>"
                              + "<div class='onote'>Shopify may have been busy. Reprint these from the orders "
                              + "list: " + esc(names) + "</div></div>"))
        if requested > len(ids):
            # Never let a bulk print silently drop orders past the 50-order cap.
            sheets.insert(0, ("<div class='sheet'><div class='dead'>ONLY " + str(len(ids)) + " OF "
                              + str(requested) + " SELECTED ORDERS ARE IN THIS PRINT</div>"
                              + "<div class='onote'>Print the rest in a second batch from the orders list.</div></div>"))

        compact = h <= 60
        portrait = str(request.query_params.get("orient") or "") == "portrait"
        page_w, page_h = (h, w) if portrait else (w, h)
        rot_css = (".pw { width: " + str(page_w) + "mm; height: " + str(page_h) + "mm; overflow: hidden;"
                   " page-break-after: always; break-after: page; }"
                   ".pw:last-child { page-break-after: auto; break-after: auto; }"
                   ".pw .sheet { transform: rotate(90deg) translateY(-" + str(h) + "mm); transform-origin: top left;"
                   " page-break-after: auto; break-after: auto; }") if portrait else ""
        doc = ("<!DOCTYPE html><html><head><meta charset='utf-8'><title>Production labels</title><style>"
               "@page { size: " + str(page_w) + "mm " + str(page_h) + "mm; margin: 0; }"
               "@font-face { font-family: 'Bricolage Grotesque'; font-style: normal; font-weight: 200 800;"
               " font-stretch: 75% 100%; font-display: block; src: url('/fonts/bricolage.woff2') format('woff2'); }"
               "* { box-sizing: border-box; margin: 0; padding: 0; }"
               "body { font-family: 'Bricolage Grotesque', -apple-system, 'Segoe UI', Roboto, Arial, sans-serif; background: #fff; color: #000; }"
               ".sheet { width: " + str(w) + "mm; height: " + str(h) + "mm; padding: " + ("3.5mm 4mm" if compact else "5mm 5.5mm") + ";"
               " overflow: hidden; page-break-after: always; break-after: page; font-size: " + ("13px" if compact else "15px") + ";"
               # White and printed as such, so nothing laid under a label shows through it.
               " background: #fff; -webkit-print-color-adjust: exact; print-color-adjust: exact;"
               " line-height: 1.22; }"
               ".sheet:last-child { page-break-after: auto; break-after: auto; }"
               # Header per the merchant's design: logo over a big company name and a
               # quiet "Order:" line, closed with the heavy 2px rule; item separators
               # stay hairline #ddd like their original.
               ".top { border-bottom: 2px solid #111; padding-bottom: .95em; margin-bottom: .9em; }"
               ".logo { margin-bottom: .7em; } .logo svg.lg { height: 3.4em; width: auto; max-width: 70%; display: block; }"
               ".company { font-size: 1.68em; font-weight: 700; line-height: 1.15; overflow-wrap: break-word; }"
               ".ono { font-size: 1em; color: #333; margin-top: .3em; font-variant-numeric: tabular-nums; }"
               "ul.items { list-style: none; }"
               ".row { border-bottom: 1px solid #ddd; padding: .45em 0; page-break-inside: avoid; break-inside: avoid; }"
               ".row:last-child { border-bottom: none; }"
               ".it { display: flex; align-items: baseline; gap: .7em; font-size: .9em;"
               " white-space: nowrap; overflow: hidden; }"
               ".iqs { font-weight: 700; flex: none; font-variant-numeric: tabular-nums; min-width: 5.6em; }"
               # Chips stay plain black outlines: printers strip backgrounds by default and
               # tiny reversed type bleeds shut on thermal heads.
               ".chip { font-size: .85em; font-weight: 600; letter-spacing: .03em; text-transform: uppercase;"
               " padding: .08em .55em; border: 1px solid #111; border-radius: 2px; flex: none; }"
               ".chip.fl { border-width: 2px; font-weight: 800; }"
               ".desc { color: #333; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; }"
               # Flagged rows may wrap so the reason stays readable.
               ".it.wrap { white-space: normal; overflow: visible; } .it.wrap .desc { overflow: visible; text-overflow: clip; }"
               ".it.named .iqs { min-width: 0; }"
               ".ctx { font-size: .78em; color: #222; margin-top: .12em; padding-left: 1.6em; }"
               # A dead order must be unmissable at arm's length.
               ".dead { border: 3px solid #000; font-size: 1.68em; font-weight: 800; letter-spacing: .04em;"
               " text-align: center; padding: .35em .4em; margin-bottom: .7em; }"
               ".due { font-size: .85em; font-weight: 600; color: #333; margin-left: .7em; }"
               ".due.soon { color: #000; font-weight: 800; border: 2px solid #000;"
               " padding: .08em .55em; border-radius: 2px; }"
               ".onote { font-size: .9em; font-weight: 500; color: #111; margin-top: .55em; overflow-wrap: break-word; }"
               ".onote b { font-weight: 800; }"
               # The strip follows the last item rather than pinning to the label's bottom edge.
               ".sheet.shed .rate { display: none; }"
               ".rate { margin-top: .6em; padding-top: .35em; border-top: 1px solid #ddd;"
               " display: flex; align-items: center; justify-content: flex-start; }"
               ".rate .rt { font-size: .68em; font-weight: 500; text-align: left; }"
               ".rate .r1 { font-weight: 800; font-size: 1.06em; }"
               ".rate b { font-weight: 800; }"
               + rot_css
               # The same rules as the app's label print (30 September): something on
               # a bench machine put 66px of its own into the page and every label
               # printed with a blank after it. So nothing beside body prints, and
               # the labels' box is laid against the top of the page in front of
               # anything else, so nothing else put into the page can add a page
               # (unless it is taller than the run), push a label down or cut one
               # off. The script below
               # turns the laying on except in WebKit, where A4 runs laid this way
               # crept up the page a little more on every label.
               + "@media print { html > :not(head):not(body) { display: none !important; }"
               " html.lay, html.lay body { position: static !important; }"
               " html.lay #labels { position: absolute !important; top: 0 !important; left: 0 !important; z-index: 2147483647 !important; } }"
               + "</style></head><body><div id='labels'>"
               + ("".join("<div class='pw'>" + sh + "</div>" for sh in sheets) if portrait else "".join(sheets))
               + "</div>"
               # Same shrink-to-fit as the app's preview: step the base font down until the
               # whole order fits its label. Measured only after the label typeface has
               # loaded (2s cap), or the metrics would be the fallback font's.
               + "<script>(function(){if(navigator.vendor!=='Apple Computer, Inc.')document.documentElement.classList.add('lay');"
               "function fit(){document.querySelectorAll('.sheet').forEach(function(s){"
               "s.style.fontSize='';s.classList.remove('shed');"
               "var b=parseFloat(getComputedStyle(s).fontSize)||13,z=b,soft=b*0.75,f=b*0.6;"
               "while(s.scrollHeight>s.clientHeight&&z>soft){z-=0.5;s.style.fontSize=z+'px';}"
               "if(s.scrollHeight>s.clientHeight){s.classList.add('shed');"
               "while(s.scrollHeight>s.clientHeight&&z>f){z-=0.5;s.style.fontSize=z+'px';}}});}"
               "fit();if(document.fonts&&document.fonts.load){Promise.race(["
               "document.fonts.load(\"15px 'Bricolage Grotesque'\"),"
               "new Promise(function(r){setTimeout(r,2000);})]).then(fit,fit);}})();</script>"
               + "</body></html>")
        return HTMLResponse(doc, headers=doc_headers)

    # The Xero sync settings route (gizmo/routes/xero_sync.py).
    routes_xero_sync.register(mcp, registry)

