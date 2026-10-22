"""The scheduler and alerts: the alerts and the email that sends them, the
watch, the hourly watchdog, the nightly reconciliation and connector watch,
and the background loop that runs them. The paid report re-runs it once
scheduled went with the report tabs (22 Oct 2026).
Moved out of copilot.py (stage 4 of the 14 October audit); its routes are in
gizmo/routes/scheduler.py. Read as `scheduler.NAME`.
"""
import logging
import os
import json
import time
import asyncio
import secrets
from datetime import datetime, timezone
import httpx
import recon as recon_engine
import xero as xero_api
from gizmo.config import _env_num
from gizmo import store as jsonstore
from gizmo import shopify

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


# The schedule this file held went with the report tabs; the path stays as
# the volume's anchor: backup, status and privacy find /data beside it.
SCHEDULE_PATH      = os.environ.get("SCHEDULE_PATH", "/data/schedule.json")
ALERTS_PATH        = os.environ.get("ALERTS_PATH", "/data/alerts.json")      # alerts the app raises
ALERTS_MAX         = _env_num(int, os.environ.get("ALERTS_MAX", "60"), "60", "ALERTS_MAX")
SCHEDULE_CHECK_SECS = _env_num(int, os.environ.get("SCHEDULE_CHECK_SECS", "900"), "900", "SCHEDULE_CHECK_SECS")       # how often the scheduler wakes to check


def _load_alerts() -> list:
    alerts = jsonstore._load_json_store(ALERTS_PATH, "alerts", [])
    # Records written before the banner's fields were settled carried kind,
    # title and detail, none of which the banner reads, so they rendered as a
    # dot and a tilde. Read them as what they meant rather than shredding them.
    for a in alerts:
        kind = a.get("tab") or a.get("kind") or ""
        if not a.get("tab"):
            a["tab"] = kind
        if not a.get("tab_label"):
            a["tab_label"] = {"connector": "Xero sync"}.get(kind, kind.replace("_", " ").title())
        if not a.get("metric"):
            a["metric"] = a.get("title") or a.get("detail") or "The last run needs attention"
    return alerts


def _write_alerts(alerts: list) -> list:
    if not jsonstore._store_writable(ALERTS_PATH):
        return alerts[:ALERTS_MAX]
    jsonstore._write_json_store(ALERTS_PATH, "alerts", alerts[:ALERTS_MAX])
    return alerts[:ALERTS_MAX]


def _add_alerts(items: list) -> list:
    alerts = _load_alerts()
    now = datetime.now(timezone.utc).isoformat()
    for it in (items or []):
        alerts.insert(0, {"id": secrets.token_hex(5), "at": now, "status": "new", **it})
    return _write_alerts(alerts)


RESEND_API_KEY   = os.environ.get("RESEND_API_KEY", "")
ALERT_EMAIL_TO   = os.environ.get("ALERT_EMAIL_TO", "")
ALERT_EMAIL_FROM = os.environ.get("ALERT_EMAIL_FROM", "Reactor <onboarding@resend.dev>")
WATCH_PATH       = os.environ.get("WATCH_PATH", "/data/watch.json")


async def _send_alert_email(subject: str, lines: list) -> bool:
    """Alerts that only render inside the app are invisible until someone opens it;
    with a Resend key set, they also reach an inbox. Best-effort, never raises."""
    if not (RESEND_API_KEY and ALERT_EMAIL_TO):
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as cx:
            r = await cx.post("https://api.resend.com/emails",
                              headers={"Authorization": "Bearer " + RESEND_API_KEY},
                              json={"from": ALERT_EMAIL_FROM, "to": [ALERT_EMAIL_TO],
                                    "subject": subject, "text": "\n".join(lines)})
        if r.status_code >= 300:
            logger.warning("alert email rejected: %s %s", r.status_code, r.text[:200])
        return r.status_code < 300
    except Exception:
        logger.exception("alert email failed")
        return False


def _load_watch() -> dict:
    return jsonstore._load_json_store(WATCH_PATH, None, {}) or {}


def _save_watch(state: dict) -> None:
    if not jsonstore._store_writable(WATCH_PATH):
        return
    try:
        jsonstore._write_json_store(WATCH_PATH, None, state)
    except Exception:
        logger.exception("watch state write failed")


def _update_alert(aid: str, status: str) -> list:
    alerts = _load_alerts()
    if status == "delete":
        return _write_alerts([a for a in alerts if a.get("id") != aid])
    for a in alerts:
        if a.get("id") == aid:
            a["status"] = status
    return _write_alerts(alerts)


_scheduler_started = False
_watch_last_tick = 0.0


async def _watchdog_tick(registry: dict) -> bool:
    """Hourly, independent of the paid schedule: probe the Shopify connection and
    keep the size-list coverage fresh. Returns True when Shopify is reachable.
    Never raises."""
    global _watch_last_tick
    now = time.time()
    if now - _watch_last_tick < 3600:
        return not _load_watch().get("shopify_down")
    _watch_last_tick = now
    state = _load_watch()
    try:
        shop = await shopify._tool_json(registry, "shopify_get_shop", {})
        up = shopify._ok(shop) and bool(shop.get("name"))
        fails = 0 if up else int(state.get("probe_fails") or 0) + 1
        state["probe_fails"] = fails
        if not up and fails == 3 and not state.get("shopify_down"):
            # Three consecutive hourly failures: this is an outage, not a blip.
            state["shopify_down"] = datetime.now(timezone.utc).isoformat()
            _add_alerts([{"tab": "settings", "tab_label": "Connections",
                          "metric": "Shopify connection is failing; data may be stale", "pct": None}])
            refused = False
            if shopify._install_checker is not None:
                try:
                    refused = (await shopify._install_checker()) == "gone"
                except Exception:  # a check that cannot answer is not an uninstall; the outage alert above stands
                    refused = False
            if refused:
                # Shopify turning the app's own credential away is what an
                # uninstall looks like, and two days after one Shopify has
                # Reactor erase the shop's data: say so while there is time.
                await _send_alert_email("Reactor: Shopify is refusing the app's access to your store",
                                        ["For 3 hours Shopify has refused Reactor's access to your store.",
                                         "If the app was uninstalled, reinstall it now: two days after an",
                                         "uninstall, Shopify has Reactor erase the shop's data from the app.",
                                         "If nobody here uninstalled it, someone holding the app's secret may",
                                         "have: reinstall it and change the secret. If the secret or token was",
                                         "just changed on purpose, give Reactor the new one."])
            else:
                await _send_alert_email("Reactor: Shopify connection is failing",
                                        ["The app has not been able to read your store for 3 hours.",
                                         "Data and labels may be stale until the connection recovers",
                                         "(this usually means the access token was rotated or Shopify",
                                         "had an outage)."])
        if up and state.get("shopify_down"):
            state.pop("shopify_down", None)
            await _send_alert_email("Reactor: Shopify connection recovered",
                                    ["Reads are working again."])
        # The privacy duties first, each on its own: anything later in this
        # tick that raises (the size-list check did, every hour) skipped them.
        # A shop/redact still owed is tried against this tick's own record of
        # how long the store has been out of reach.
        try:
            await privacy._shop_redact_retry(state.get("shopify_down"))
        except Exception:
            logger.exception("shop/redact retry failed")
        try:
            # Shopify is not asked about customers while it cannot be reached.
            await privacy._redact_hold_due(check=up)
        except Exception:
            logger.exception("held customer erasures failed")
        try:
            privacy._redact_retry_pending()      # an admin's erasure a store refused, tried again
        except Exception:
            logger.exception("the retry of an unfinished erasure failed")
        # Weekly size-list coverage: catch a new model going unmatched before a
        # CHECK label surprises the workbench.
        last_cov = state.get("coverage_at")
        due = True
        if last_cov:
            try:
                due = (datetime.now(timezone.utc) - datetime.fromisoformat(last_cov)).days >= 7
            except Exception:  # an unreadable stamp means the check is due
                due = True
        if up and due:
            cov = await core.run_label_coverage(registry, 200)
            if not cov.get("error"):
                keys = sorted(f"{f['manufacturer']}|{f['model']}|{f['reason']}" for f in cov.get("flagged", []))
                prev = set(state.get("coverage_flagged") or [])
                fresh = [k for k in keys if k not in prev]
                state["coverage_at"] = datetime.now(timezone.utc).isoformat()
                state["coverage_flagged"] = keys
                state["coverage_pct"] = cov.get("pct")
                if fresh and prev:   # first-ever run just sets the baseline quietly
                    _add_alerts([{"tab": "labels", "tab_label": "Labels",
                                  "metric": "New model not matching the size list: " + k.split("|")[1], "pct": None}
                                 for k in fresh[:5]])
                    await _send_alert_email("Reactor: new models missing from the size list",
                                            [k.replace("|", " / ") for k in fresh]
                                            + ["", "Open Production Manager and run Size check: each "
                                               "model there can be given a size, pointed at a model "
                                               "already on the list, or ruled out, without editing "
                                               "any file."])
        # Webhook subscriptions are a standing repair, not an install step:
        # Shopify silently deletes one after sustained delivery failure (an
        # outage on our side), so re-assert them every tick.
        if up and shopify._webhook_ensurer is not None:
            try:
                orderbook._webhook_state["ensured"] = await shopify._webhook_ensurer()
                gone = (orderbook._webhook_state["ensured"] or {}).get("foreign_removed") or []
                if gone:
                    # A subscription made with this app's credentials and
                    # pointing at another host copies orders out of the
                    # business: removed by the repair, and said loudly.
                    activity._track(None, "settings", "removed order webhooks pointing outside Reactor", "; ".join(gone))
                    await _send_alert_email("Reactor: removed store notifications that pointed outside the app",
                                            gone + ["", "Each was made with Reactor's own Shopify credentials. "
                                                    "If one was a second copy of Reactor, such as a staging copy, "
                                                    "allow its host name (for example staging.example.com) in the "
                                                    "server's settings. If nobody here made it, treat those "
                                                    "credentials as leaked: change the desktop AI token and the "
                                                    "app secret."])
            except Exception:
                logger.exception("webhook registration failed")
        # Stock-bridge retries: bookings that failed to reach the stock app.
        # Not gated on Shopify being up: reversals need no Shopify read, and a
        # book retry just fails and stays parked if Shopify is still down.
        await core._zeta_drain(registry)
        # And the catalogue, so the stock app's mapping view stays complete as
        # the size sheet evolves. Cheap, idempotent, best-effort.
        if core._zeta_configured():
            try:
                await core._zeta_send_catalog()
            except Exception:
                logger.warning("stock bridge: catalogue push failed; next tick retries")
        # The accounts vanishing after setup means the register was LOST
        # (corrupt file, missing volume): the app will demand first-run setup
        # again. Nobody is silently let in, but the merchant must hear about
        # it, because their team is locked out until setup happens.
        try:
            if state.get("team_established") and team._team_setup_needed():
                last = str(state.get("team_lost_alert_at") or "")
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                if last != today:
                    state["team_lost_alert_at"] = today
                    logger.error("the accounts register is empty after setup; the app will re-run first-run setup")
                    _add_alerts([{"tab": "settings", "tab_label": "Team",
                                  "metric": "The user accounts were lost: the app is asking to be "
                                            "set up again", "pct": None}])
                    await _send_alert_email("Reactor: the user accounts were lost",
                                            ["The list of accounts is empty even though it was set up "
                                             "before (a corrupt file or a missing data volume).",
                                             "The app will show its first-run setup screen; recreate the "
                                             "master account, then the team's accounts."])
            team._sessions_sweep()
            work._work_close_orphans()
            activity._events_flush()   # belt for the debounced ledger writes
        except Exception:
            logger.exception("team register check failed")

        # Files trash past its 30-day window, and uploads that never finished.
        # Not gated on Shopify: the bucket is a different service entirely.
        # Under the store lock: the purge is a read-modify-write like any route.
        try:
            async with fileserver._files_lock:
                await asyncio.to_thread(fileserver._files_tick)
        except Exception:
            logger.exception("files purge failed")
        # MERGE rather than write the snapshot taken minutes ago: this tick has
        # been awaiting Shopify, emails, coverage and the bucket the whole time,
        # and anything written meanwhile (team_established, for one) would be
        # erased by writing our stale copy back wholesale.
        fresh = _load_watch()
        fresh.update(state)
        # A merge keeps what the snapshot no longer has. The outage flag is
        # the one key this tick DELETES, and merging it back meant a recovered
        # connection stayed "down" on disk: a recovered email every hour, the
        # early-return path answering down, and the paid audits skipped on
        # three ticks in four, for as long as the volume lasted.
        if "shopify_down" not in state:
            fresh.pop("shopify_down", None)
        _save_watch(fresh)
        return up or fails < 3
    except Exception:
        logger.exception("watchdog tick failed")
        return True


_recon_nightly_stamp = {"day": ""}


async def _recon_nightly() -> None:
    """One sweep a day, self-stamped like the CRM's. Never raises: a failed
    sweep is a note in the store, not a dead scheduler."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _recon_nightly_stamp["day"] == today:
        return
    if not xero_api.connected():
        return                       # nothing to reconcile against yet
    _recon_nightly_stamp["day"] = today
    try:
        r = await recon_engine.sweep()
        logger.info("recon nightly: %s", json.dumps(r.get("open_counts") or {}))
    except Exception:
        logger.exception("recon nightly sweep failed")


async def _connector_watch() -> None:
    """Tell someone when the Xero connector needs attention.

    A quarantined order is silent: it is not an error anywhere, it simply never
    arrives in the accounts, and nobody finds out until they happen to open the
    tab. With Auto Run on, nobody has a reason to open the tab at all - so the
    automation is exactly what makes this necessary rather than nice.

    Polled, not pushed. gizmo already holds the connector's token and calls
    into it; a webhook the other way would mean that service authenticating
    INTO this one, which is a second credential and a new direction of trust
    for the sake of a few minutes on a message about an accounting run.

    Never raises: the scheduler has other work after this.
    """
    if not xerosync._connector_url():
        return
    try:
        code, data = await xerosync._connector_call("GET", "/api/health")
    except Exception:
        # The service being unreachable is its own alert, but a noisy one
        # during a redeploy. The tab says it plainly; this stays quiet.
        return
    if code >= 400 or not isinstance(data, dict):
        return
    if not data.get("needsAttention"):
        return
    run_id = str(data.get("lastRunId") or "")
    if not run_id:
        return
    state = _load_watch()
    if state.get("connector_run") == run_id:
        return                      # already told them about this one
    problems = [str(p) for p in (data.get("problems") or [])][:12]
    auto = (data.get("autoRun") or {}).get("enabled")
    lines = ["The Xero connector finished a run that needs looking at.", "",
             str(data.get("line") or ""), ""]
    lines += ["- " + p for p in problems]
    lines += ["", "Auto Run is " + ("ON, so this will be retried on the next pass."
                                    if auto else "off; nothing further will happen until someone runs it."),
              "Open Reactor, Finance, Xero sync."]
    # The banner draws tab_label, metric and pct. I gave it kind/title/detail,
    # none of which it reads, so the alert rendered as a bare dot and a tilde -
    # a row that told the reader something was wrong and refused to say what.
    _add_alerts([{"tab": "connector", "tab_label": "Xero sync",
                  "metric": (problems[0] if problems
                             else str(data.get("line") or "the last run needs attention")),
                  "pct": None}])
    await _send_alert_email("Xero connector: " + str(data.get("line") or "run needs attention"), lines)
    # RELOAD after the await. The snapshot above was taken before an SMTP round
    # trip; writing it back wholesale erases anything else the watch store
    # gained meanwhile - team_established among them, and the watchdog's
    # "the accounts were lost" alarm keys off that flag. The single-writer rule
    # this codebase runs on, broken in code I added this morning.
    fresh = _load_watch()
    fresh["connector_run"] = run_id
    _save_watch(fresh)


async def _scheduler_loop(registry: dict) -> None:
    await asyncio.sleep(60)  # let the app settle after boot
    while True:
        try:
            shopify_up = await _watchdog_tick(registry)
            await asyncio.to_thread(backup._weekly_snapshot)   # no-op until a week is up
            if shopify_up:
                await salesdesk._crm_shopify_link_nightly(registry)   # once a day, self-stamped
            # Xero refresh tokens die after 60 unused days, and the books
            # drift silently between sweeps: both are the scheduler's problem.
            await xero_api.keepalive()
            await _recon_nightly()
            await _connector_watch()
        except Exception:
            logger.exception("scheduler loop error")
            try:
                state = _load_watch()
                last = state.get("error_email_at")
                stale = True
                if last:
                    try:
                        stale = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() > 86400
                    except Exception:  # an unreadable stamp means the email is due
                        stale = True
                if stale:   # at most one failure email a day, not one per tick
                    state["error_email_at"] = datetime.now(timezone.utc).isoformat()
                    _save_watch(state)
                    await _send_alert_email("Reactor: background scheduler hit an error",
                                            ["The automatic refresh loop errored; it will keep retrying.",
                                             "If alerts go quiet for days, check the server logs."])
            except Exception:
                pass  # the loop's error is logged above; a failure email that cannot go must never stop the loop
        await asyncio.sleep(SCHEDULE_CHECK_SECS)


def _ensure_scheduler(registry: dict) -> None:
    """Start the background scheduler once, lazily, when an event loop is running."""
    global _scheduler_started
    if _scheduler_started:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _scheduler_started = True
    loop.create_task(_scheduler_loop(registry))
    loop.create_task(mail._mail_loop())


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as core.NAME and sibling.NAME, never a copied name.
from gizmo import backup  # noqa: E402
from gizmo import activity  # noqa: E402
from gizmo import files as fileserver  # noqa: E402
from gizmo import mail  # noqa: E402
from gizmo import orderbook  # noqa: E402
from gizmo import privacy  # noqa: E402
from gizmo import crm as salesdesk  # noqa: E402
from gizmo import team  # noqa: E402
from gizmo import work  # noqa: E402
import copilot as core  # noqa: E402
from gizmo import xero_sync as xerosync  # noqa: E402
