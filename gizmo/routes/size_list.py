"""The Size list's routes, moved from add_routes (stage 4 of the 14 October
audit) where the first stood; their paths are literal, so no request changes
hands.
"""
import logging
import os
from datetime import datetime, timezone
from starlette.requests import Request

import copilot as core
from gizmo import activity
from gizmo import gate
from gizmo import size_list
from gizmo import team

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


def register(mcp, registry):
    """Add the Size list's routes to the app."""

    @mcp.custom_route("/api/gobo-sizes/upload", methods=["POST"])
    async def gobo_sizes_upload_route(request: Request):
        """Self-serve size sheet update: validate the CSV hard, keep a .bak of the
        previous sheet, and report the before/after so a bad file can't quietly
        wipe the size list."""
        big = 2 * 1024 * 1024
        err, _body, who = await gate._guard(request, max_body=big, body=False)
        if err:
            return err
        if team._team_level(who) < team.ROLE_LEVELS["admin"]:
            return gate._json({"error": "Only an admin can replace the size list."}, 403)
        body = await gate._read_json_capped(request, cap=big)
        if body is None:
            return gate._json({"error": "That file is too large (2 MB cap)."}, 413)
        text = str(body.get("csv") or "")
        if not text.strip():
            return gate._json({"error": "No CSV content received."}, 400)
        import csv as _csv
        import io as _io
        try:
            rows = list(_csv.DictReader(_io.StringIO(text.lstrip("\ufeff"))))
        except Exception:
            return gate._json({"error": "That file does not parse as a CSV."}, 400)
        headers = set(rows[0].keys()) if rows else set()
        need = {"Manufacturer", "Model", "Closest Production Size (mm)"}
        if not need.issubset(headers):
            return gate._json({"error": "The CSV is missing required columns: "
                          + ", ".join(sorted(need - headers))
                          + ". Export the sheet with the same columns as before."}, 400)
        model_rows = sum(1 for r in rows if str(r.get("Model") or "").strip())
        # A size cell is what the bench reads off the label and what the stock
        # sheet sorts by. Free text there printed as the size and crashed the
        # day's stock usage, so a sheet whose sizes are not sizes is refused,
        # naming the rows. An empty cell stays allowed: it means "no size yet".
        bad = [(i + 2, str(r.get("Model") or "").strip(), str(r.get("Closest Production Size (mm)") or "").strip())
               for i, r in enumerate(rows)
               if str(r.get("Closest Production Size (mm)") or "").strip()
               and size_list._clean_gobo_size(r.get("Closest Production Size (mm)")) is None]
        if bad:
            shown = "; ".join(f"row {n} ({m or 'no model'}): \"{v[:20]}\"" for n, m, v in bad[:5])
            return gate._json({"error": f"{len(bad)} size cell(s) are not a size in mm, so nothing was "
                                   f"changed: {shown}" + (" and more." if len(bad) > 5 else ".")}, 400)
        before = (size_list._gobo_sizes().get("health") or {}).get("models") or 0
        if model_rows < 50 or model_rows < before * 0.5:
            return gate._json({"error": f"That file only has {model_rows} model rows; the current sheet has "
                          f"{before}. Refusing to replace it. If this shrink is intentional, "
                          "send the file to your developer instead."}, 400)
        try:
            os.makedirs(os.path.dirname(size_list.GOBO_SIZES_LIVE) or ".", exist_ok=True)
            if os.path.isfile(size_list.GOBO_SIZES_LIVE):
                # Dated generations, atomically written, newest five kept: one bad
                # upload can never destroy the only recovery copy.
                import shutil
                stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
                btmp = size_list.GOBO_SIZES_LIVE + ".bak.tmp"
                shutil.copyfile(size_list.GOBO_SIZES_LIVE, btmp)
                os.replace(btmp, f"{size_list.GOBO_SIZES_LIVE}.{stamp}.bak")
                baks = sorted(f for f in os.listdir(os.path.dirname(size_list.GOBO_SIZES_LIVE) or ".")
                              if f.startswith(os.path.basename(size_list.GOBO_SIZES_LIVE) + ".") and f.endswith(".bak"))
                for stale_bak in baks[:-5]:
                    try:
                        os.remove(os.path.join(os.path.dirname(size_list.GOBO_SIZES_LIVE) or ".", stale_bak))
                    except OSError:
                        pass
            tmp = size_list.GOBO_SIZES_LIVE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp, size_list.GOBO_SIZES_LIVE)
        except Exception:
            logger.exception("size sheet write failed")
            return gate._json({"error": "Couldn't save the new sheet to the data volume."}, 500)
        health = size_list._gobo_sizes().get("health") or {}
        logger.info("gobo sizes: sheet replaced via upload (%d csv rows, %s model keys)",
                    len(rows), health.get("models"))
        activity._track(who, "sizes", "replaced the size list", f"{len(rows)} rows")
        return gate._json({"ok": True, "rows": len(rows),
                      "models_before": before, "models_after": health.get("models"),
                      "dead_aliases": health.get("dead_aliases", 0)})

    @mcp.custom_route("/api/gobo-sizes/rules", methods=["POST"])
    async def gobo_rules_route(request: Request):
        """The merchant's standing rulings on models, and whether this person may
        change them. Read is open to anyone who can see the tab: knowing why a
        model resolves the way it does is part of reading the size check."""
        err, _body, who = await gate._guard(request, body=False)
        if err:
            return err
        try:
            return gate._json({"overrides": size_list._gobo_rule_rows("override"),
                          "aliases": size_list._gobo_rule_rows("alias"),
                          "can_edit": team._may_edit_sizes(who)})
        except Exception:
            logger.exception("gobo rules read failed")
            return gate._json({"error": "Couldn't read the size rules."}, 500)

    @mcp.custom_route("/api/gobo-sizes/list", methods=["POST"])
    async def gobo_list_route(request: Request):
        """The whole sheet with the rulings over it, for the Size list tab. Read
        is open to anyone who can see the tab, as the rules are: the bench reads
        sizes far more often than anyone changes them."""
        err, _body, who = await gate._guard(request, body=False)
        if err:
            return err
        try:
            return gate._json(size_list._gobo_sheet_listing(who))
        except Exception:
            logger.exception("gobo list read failed")
            return gate._json({"error": "Couldn't read the size list."}, 500)

    @mcp.custom_route("/api/gobo-sizes/check", methods=["POST"])
    async def gobo_check_route(request: Request):
        """What a label prints for a fixture named in free text, for the Size
        list's search. Read only, and open to anyone who can see the tab."""
        err, body, _who = await gate._guard(request)
        if err:
            return err
        q = str(body.get("q") or "").strip()
        if len(q) < 2:
            return gate._json({"error": "Type at least two letters of a fixture."}, 400)
        try:
            return gate._json(size_list._gobo_check(q))
        except Exception:
            logger.exception("gobo check failed")
            return gate._json({"error": "Couldn't check that name against the size list."}, 500)

    @mcp.custom_route("/api/gobo-sizes/models", methods=["POST"])
    async def gobo_models_route(request: Request):
        """Models already on the sheet, for the picker behind 'this is another
        name for'. Searching the real sheet is what stops an alias being written
        onto a model that does not exist, which loads as a dead rule."""
        err, body, _who = await gate._guard(request)
        if err:
            return err
        q = str(body.get("q") or "").strip().lower()
        if len(q) < 2:
            return gate._json({"models": []})
        seen, out = set(), []
        for entry in (size_list._gobo_sizes().get("rows") or []):
            e = entry[2] if isinstance(entry, tuple) else entry
            if not isinstance(e, dict):
                continue
            model, mfr = e.get("model") or "", e.get("manufacturer") or ""
            if not model or q not in (mfr + " " + model).lower():
                continue
            key = (mfr, model)
            if key in seen:
                continue
            seen.add(key)
            out.append({"manufacturer": mfr, "model": model,
                        "size": e.get("production_size") or ""})
            if len(out) >= 25:
                break
        return gate._json({"models": out})

    @mcp.custom_route("/api/gobo-sizes/rule", methods=["POST"])
    async def gobo_rule_route(request: Request):
        """Resolve one flagged model, from inside the app. Four ops: give it a
        size, give it a size for one customer's domain only, point it at a model
        already on the sheet, or say it is not a gobo at all. Each writes one row
        to the rule files the size lookup already reads, so nothing here invents a
        mechanism - it opens the one that existed only as a CSV on the volume."""
        err, _body, who = await gate._guard(request, body=False)
        if err:
            return err
        if not team._may_edit_sizes(who):
            return gate._json({"error": "You do not have access to edit the size list. "
                          "An admin can grant it on the Team tab."}, 403)
        body = await gate._read_json_capped(request)
        if body is None:
            return gate._json({"error": "Request too large."}, 413)
        op = str(body.get("op") or "")
        mfr = str(body.get("manufacturer") or "").strip()[:80]
        model = str(body.get("model") or "").strip()[:120]
        if not model:
            return gate._json({"error": "Which model? A rule with no model would match nothing."}, 400)
        domain = str(body.get("domain") or "").strip().lstrip("@").lower()[:120]
        try:
            if op in ("set", "exclude"):
                if op == "exclude":
                    if domain:
                        return gate._json({"error": "Excluding is for a model outright, "
                                      "not for one customer."}, 400)
                    size = "exclude"
                else:
                    size = size_list._clean_gobo_size(body.get("size"))
                    if not size:
                        return gate._json({"error": "That is not a production size. Give it in "
                                      "millimetres, for example 37.5."}, 400)
                rows = size_list._gobo_rule_rows("override")
                hit = None
                for r in rows:
                    if (size_list._norm_key(r["Manufacturer"]) == size_list._norm_key(mfr)
                            and size_list._norm_key(r["Model"]) == size_list._norm_key(model)
                            and r["Customer Email Domain"].lstrip("@").lower() == domain):
                        hit = r
                        break
                was = hit["Production Size (mm)"] if hit else None
                if hit:
                    hit["Production Size (mm)"] = size
                else:
                    rows.append({"Manufacturer": mfr, "Model": model,
                                 "Customer Email Domain": domain,
                                 "Production Size (mm)": size})
                size_list._write_gobo_rule_rows("override", rows)
                what = ("excluded" if size == "exclude"
                        else f"set to {size} mm" + (f" for @{domain}" if domain else ""))
                activity._track(who, "sizes", "changed a size rule",
                       f"{mfr} {model} {what}" + (f" (was {was})" if was and was != size else ""))
            elif op == "alias":
                target = str(body.get("list_model") or "").strip()[:120]
                if not target:
                    return gate._json({"error": "Which model on the list is it another name for?"}, 400)
                entry, reason = size_list._gobo_lookup(mfr, target)
                if reason:
                    return gate._json({"error": f"\u201c{target}\u201d is not on the size list, so "
                                  "pointing at it would leave the rule dead. Pick from the list, "
                                  "or give this model a size instead."}, 400)
                rows = size_list._gobo_rule_rows("alias")
                for r in rows:
                    if (size_list._norm_key(r["Manufacturer"]) == size_list._norm_key(mfr)
                            and size_list._norm_key(r["Store Model"]) == size_list._norm_key(model)):
                        r["List Model"] = target
                        break
                else:
                    rows.append({"Manufacturer": mfr, "Store Model": model, "List Model": target})
                size_list._write_gobo_rule_rows("alias", rows)
                activity._track(who, "sizes", "changed a size rule",
                       f"{mfr} {model} reads as {target}")
            elif op == "remove":
                kind = "alias" if str(body.get("kind") or "") == "alias" else "override"
                rows = size_list._gobo_rule_rows(kind)
                mcol = "Store Model" if kind == "alias" else "Model"
                keep = [r for r in rows
                        if not (size_list._norm_key(r["Manufacturer"]) == size_list._norm_key(mfr)
                                and size_list._norm_key(r[mcol]) == size_list._norm_key(model)
                                and (kind == "alias"
                                     or r["Customer Email Domain"].lstrip("@").lower() == domain))]
                if len(keep) == len(rows):
                    return gate._json({"error": "That rule is no longer there."}, 400)
                size_list._write_gobo_rule_rows(kind, keep)
                activity._track(who, "sizes", "removed a size rule", f"{mfr} {model}")
            else:
                return gate._json({"error": "Unknown operation."}, 400)
        except Exception:
            logger.exception("gobo rule write failed")
            return gate._json({"error": "Couldn't save that rule to the data volume."}, 500)
        # Re-read through the same lookup the labels print with, so the answer
        # says what the bench will actually see rather than what was intended.
        entry, reason = size_list._gobo_lookup(mfr, model)
        health = size_list._gobo_sizes().get("health") or {}
        return gate._json({"ok": True, "resolves": not reason, "reason": reason or "",
                      "size": (entry.get("production_size") if isinstance(entry, dict) else None),
                      "dead_aliases": health.get("dead_aliases", 0),
                      "overrides": size_list._gobo_rule_rows("override"),
                      "aliases": size_list._gobo_rule_rows("alias")})
