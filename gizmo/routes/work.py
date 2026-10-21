"""The work sessions' routes, gathered from add_routes (stage 4 of the 14
October audit) where the first stood; their paths are literal, so no request
changes hands.
"""
import logging
from datetime import datetime, timezone
from starlette.requests import Request

import copilot as core
from gizmo import clock
from gizmo import activity
from gizmo import gate
from gizmo import team
from gizmo import work

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


def register(mcp, registry):
    """Add the work sessions' routes to the app."""

    # ---- Work routes ------------------------------------------------------
    # The clock. Timestamps are minted HERE, never accepted from the browser.
    @mcp.custom_route("/api/work/clock", methods=["POST"])
    async def work_clock_route(request: Request):
        err, body, who = await gate._guard(request)
        if err:
            return err
        if not work._work_monitored(who):
            return gate._json({"error": "Only part-time accounts clock in and out."}, 400)
        op = str(body.get("op") or "")
        now = datetime.now(timezone.utc)
        try:
            d = work._load_work()
            if op == "in":
                if d["open"].get(who):
                    return gate._json({"error": "You are already clocked in."}, 400)
                d["seq"] = int(d.get("seq") or 0) + 1
                ws = {"id": f"w{d['seq']}", "uid": who, "start": now.isoformat()}
                d["open"][who] = ws
                work._write_work(d)
                activity._track(who, "work", "clocked in")
                return gate._json({"ok": True, "session": ws})
            if op == "out":
                ws = d["open"].pop(who, None)
                if not ws:
                    return gate._json({"error": "You are not clocked in."}, 400)
                ws["end"] = now.isoformat()
                try:
                    ws["secs"] = max(0, int((now - datetime.fromisoformat(ws["start"])).total_seconds()))
                except Exception:
                    ws["secs"] = 0
                # A shift shorter than a minute is a mis-tap, not work. It is
                # dropped rather than appended, because the log is a fixed-size
                # FIFO: without this, anyone could clock in and out a couple of
                # thousand times and quietly evict every real shift for every
                # member of staff from the payroll record.
                if ws["secs"] < work.WORK_MIN_SECS:
                    work._write_work(d)
                    activity._track(who, "work", "clocked out", "under a minute, not recorded")
                    return gate._json({"ok": True, "session": ws, "dropped": True,
                                  "note": "That was under a minute, so it was not added to "
                                          "the work log."})
                d["sessions"].append(ws)
                work._write_work(d)      # which moves anything past the cap to the archive
                activity._track(who, "work", "clocked out", work._fmt_secs(ws["secs"]))
                return gate._json({"ok": True, "session": ws})
            return gate._json({"error": "Unknown clock action."}, 400)
        except RuntimeError:
            return gate._json({"error": "The clock could not be saved. The data volume may be "
                                   "unwritable; check Settings, Connections."}, 500)

    @mcp.custom_route("/api/work/status", methods=["POST"])
    async def work_status_route(request: Request):
        err, _body, who = await gate._guard(request, body=False)
        if err:
            return err
        if not work._work_monitored(who):
            return gate._json({"monitored": False})
        ws = work._work_open_session(who)
        secs = 0
        if ws:
            try:
                secs = max(0, int((datetime.now(timezone.utc)
                                   - datetime.fromisoformat(ws["start"])).total_seconds()))
            except Exception:
                pass  # an unreadable start reads as no time yet, never an error on the clock
        return gate._json({"monitored": True, "clocked_in": bool(ws),
                      "session": ({**ws, "secs": secs} if ws else None)})


    @mcp.custom_route("/api/work/board", methods=["POST"])
    async def work_board_route(request: Request):
        err, packed = await team._team_guard(request, team.ROLE_LEVELS["admin"])
        if err:
            return err
        _who, _body = packed
        try:
            d = work._load_work()
            users = team._load_users()["users"]
            today, week, month = work._day_starts()
            now = datetime.now(timezone.utc)
            open_rows = []
            for uid, ws in d["open"].items():
                try:
                    secs = max(0, int((now - datetime.fromisoformat(ws["start"])).total_seconds()))
                except Exception:
                    secs = 0
                open_rows.append({**ws, "secs": secs})
            events = activity._load_events()
            by_ws: dict = {}
            for e in events:
                if e.get("ws"):
                    by_ws[e["ws"]] = by_ws.get(e["ws"], 0) + 1
            totals = {}
            for uid, u in users.items():
                if u.get("role") != "parttime" or u.get("deleted"):
                    continue
                rows = [s for s in d["sessions"] if s.get("uid") == uid]
                totals[uid] = {"today": work._work_secs(uid, today), "week": work._work_secs(uid, week),
                               "month": work._work_secs(uid, month), "sessions": len(rows),
                               "avg": int(sum(int(s.get("secs") or 0) for s in rows) / len(rows)) if rows else 0}
            recent = d["sessions"][-120:][::-1]
            for s in recent:
                s = s  # sessions carry corrections inline
            return gate._json({"open": open_rows, "sessions": recent, "totals": totals,
                          "event_counts": by_ws, "names": team._team_names()})
        except Exception:
            logger.exception("work board failed")
            return gate._json({"error": "Couldn't load the work board."}, 500)

    @mcp.custom_route("/api/work/resolve", methods=["POST"])
    async def work_resolve_route(request: Request):
        # An admin closing a forgotten clock-out. The original start stands;
        # the correction wears its author and lands on the ledger.
        err, packed = await team._team_guard(request, team.ROLE_LEVELS["admin"])
        if err:
            return err
        who, body = packed
        uid = str(body.get("uid") or "")
        try:
            d = work._load_work()
            ws = d["open"].pop(uid, None)
            if not ws:
                return gate._json({"error": "That person has no open session."}, 400)
            now = datetime.now(timezone.utc)
            ws["end"] = now.isoformat()
            try:
                ws["secs"] = max(0, int((now - datetime.fromisoformat(ws["start"])).total_seconds()))
            except Exception:
                ws["secs"] = 0
            ws["corrected"] = True
            ws["corrected_by"] = who
            ws["corrected_at"] = now.isoformat()
            ws["note"] = str(body.get("note") or "")[:200]
            d["sessions"].append(ws)
            work._write_work(d)
            activity._track(who, "work", "resolved a work session",
                   f"closed {(team._team_name(uid) or uid)}'s open session at {work._fmt_secs(ws['secs'])}")
            return gate._json({"ok": True, "session": ws})
        except RuntimeError:
            return gate._json({"error": "The correction could not be saved. The data volume may "
                                   "be unwritable; check Settings, Connections."}, 500)

    @mcp.custom_route("/api/work/report", methods=["POST"])
    async def work_report_route(request: Request):
        err, packed = await team._team_guard(request, team.ROLE_LEVELS["admin"])
        if err:
            return err
        _who, body = packed
        uid = str(body.get("uid") or "")
        frm = str(body.get("from") or "")[:10]
        to = str(body.get("to") or "")[:10]
        try:
            d = work._load_work()
            # The archive as well as the live log, once each: a shift can be in
            # both if the live write failed after its archive line was made.
            seen_ids: set = set()
            every = []
            for ws in work._work_archived() + list(d["sessions"]):
                k = str(ws.get("id") or "") + "|" + str(ws.get("uid") or "") + "|" + str(ws.get("start") or "")
                if k not in seen_ids:
                    seen_ids.add(k)
                    every.append(ws)
            # The from/to dates are London days, like the sheet's own Date column.
            rows = [s for s in every
                    if (not uid or s.get("uid") == uid)
                    and (not frm or clock._london_day(s.get("start")) >= frm)
                    and (not to or clock._london_day(s.get("start")) <= to)]
            events = activity._load_events()
            counts = {}
            for e in events:
                if e.get("ws"):
                    counts[e["ws"]] = counts.get(e["ws"], 0) + 1
            names = team._team_names()
            total = sum(int(s.get("secs") or 0) for s in rows)
            return gate._json({"sessions": rows, "total_secs": total, "count": len(rows),
                          "event_counts": counts, "csv": work._work_csv(rows, names, counts)})
        except Exception:
            logger.exception("work report failed")
            return gate._json({"error": "Couldn't build the report."}, 500)
