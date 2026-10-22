"""The What's new route: the release notes, requests and what each person has
read. Moved from add_routes (stage 4 of the 14 October audit) where it
stood.
"""
import logging
from datetime import datetime, timezone
from starlette.requests import Request

from gizmo import activity
from gizmo import gate
from gizmo import team
from gizmo import scheduler
from gizmo import updates
from gizmo import bodies

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")



class UpdatesBody(bodies.Body):
    """What /api/updates reads (gizmo/bodies.py): a feature request, a
    request's triage, and what this person has read."""
    title: bodies.Text = None
    detail: bodies.Text = None
    where: bodies.Text = None
    id: bodies.Id = None
    state: bodies.Text = None
    note: bodies.Text = None
    releases: bodies.Whole = None
    requests: bodies.Flag = None


def register(mcp, registry):
    """Add the What's new route to the app."""

    @mcp.custom_route("/api/updates", methods=["POST"])
    async def updates_route(request: Request):
        """What's new + the desk's feature requests. Deliberately open to every
        signed-in account and NOT tab-gated: release notes are how a part-time
        member learns what changed under them, and the request box is worth
        most from the people who never get asked."""
        err, body, who = await gate._guard(request, model=UpdatesBody)
        if err:
            return err
        op = str(body.get("op") or "")
        try:
            d = updates._load_feedback()
            if op == "request":
                title = str(body.get("title") or "").strip()[:140]
                detail = str(body.get("detail") or "").strip()[:4000]
                if not title:
                    return gate._json({"error": "Give the request a one-line title."}, 400)
                d["seq"] = int(d.get("seq") or 0) + 1
                item = {"id": "r" + str(d["seq"]), "title": title, "detail": detail,
                        "by": who, "state": "open", "note": "",
                        "where": str(body.get("where") or "")[:20],
                        "at": datetime.now(timezone.utc).isoformat()}
                d.setdefault("items", []).insert(0, item)
                d["items"] = d["items"][:500]
                updates._write_feedback(d)
                activity._track(who, "updates", "asked for a feature", title[:60])
                # Best-effort: a request nobody reads is a suggestion box with
                # no lid. Never blocks the save, and the page is told whether it
                # went: it promised an email to Cameron that was never sent when
                # alert email is not set up.
                emailed = False
                try:
                    emailed = bool(await scheduler._send_alert_email(
                        "Reactor: " + (team._team_name(who) or "someone") + " asked for a feature",
                        [title, detail or "(no detail given)"]
                        + (["Asked from the " + item["where"] + " page."] if item["where"] else [])))
                except Exception:  # the page is told the email did not go (emailed)
                    emailed = False
                return gate._json({"ok": True, "item": item, "emailed": emailed})
            if op == "state":
                # Triage. Admin+, because it speaks for the whole desk.
                if team._team_level(who) < team.ROLE_LEVELS["admin"]:
                    return gate._json({"error": "Only an admin can triage requests."}, 403)
                rid = str(body.get("id") or "")
                state = str(body.get("state") or "")
                if state not in updates.FEEDBACK_STATES:
                    return gate._json({"error": "Unknown state."}, 400)
                hit = next((x for x in d.get("items", []) if x.get("id") == rid), None)
                if not hit:
                    return gate._json({"error": "That request no longer exists."}, 404)
                hit["state"] = state
                if "note" in body:
                    hit["note"] = str(body.get("note") or "").strip()[:400]
                    hit["note_by"] = who if hit["note"] else ""
                hit["state_at"] = datetime.now(timezone.utc).isoformat()
                updates._write_feedback(d)
                activity._track(who, "updates", "marked a request " + state, (hit.get("title") or "")[:60])
                return gate._json({"ok": True, "item": hit})
            if op == "delete":
                if team._team_level(who) < team.ROLE_LEVELS["admin"]:
                    return gate._json({"error": "Only an admin can remove requests."}, 403)
                rid = str(body.get("id") or "")
                d["items"] = [x for x in d.get("items", []) if x.get("id") != rid]
                updates._write_feedback(d)
                return gate._json({"ok": True})
            # What this person has read, kept on their account: it was a date
            # in one browser, so on the shared bench computer the first person
            # to open What's new cleared the dot for everyone, and a second
            # release on a day already read never lit it at all.
            seen = d.setdefault("seen", {}).get(who) or {}
            if op == "seen":
                now = datetime.now(timezone.utc).isoformat()
                if body.get("releases") is not None:
                    seen["releases"] = int(body.get("releases") or 0)
                if body.get("requests"):
                    seen["requests"] = now
                d["seen"][who] = seen
                updates._write_feedback(d)
                return gate._json({"ok": True, "seen": seen})
            mine_answered = sum(1 for x in d.get("items", []) if x.get("by") == who
                                and (x.get("state_at") or "") > (seen.get("requests") or ""))
            new_for_triage = sum(1 for x in d.get("items", []) if x.get("state") == "open"
                                 and (x.get("at") or "") > (seen.get("requests") or ""))
            can_triage = team._team_level(who) >= team.ROLE_LEVELS["admin"]
            unread = {"releases": max(0, len(updates._load_changelog()) - int(seen.get("releases") or 0)),
                      "requests": mine_answered + (new_for_triage if can_triage else 0)}
            if op == "version":
                # The dot's own read: the counts alone, not every note and request.
                return gate._json({"ok": True, "version": updates._app_version(), "unread": unread, "seen": seen})
            return gate._json({"ok": True, "releases": updates._load_changelog(),
                          "version": updates._app_version(), "unread": unread, "seen": seen,
                          "requests": d.get("items", [])[:200],
                          "names": team._team_names(), "me": who,
                          "can_triage": can_triage})
        except (RuntimeError, OSError):
            # A read-only or full volume is a SAVE failure with a cause the
            # merchant can act on, not a "check the logs".
            return gate._json({"error": "That could not be saved: the app's storage would not take it. "
                                   "Try again, or tell Cameron if it keeps happening."}, 500)
        except Exception:
            logger.exception("updates route failed")
            return gate._json({"error": "That could not be done. Try again, or tell Cameron if it keeps happening."}, 500)
