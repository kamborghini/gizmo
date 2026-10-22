"""The stock sheet's routes (plan 2a of the stock move): one route per part
of the sheet, each a flat body model and an `op`, all under /api/stock/,
claimed by the "stock" tab in gate._TAB_ROUTES.
"""
import logging
from starlette.requests import Request

from gizmo import stock, stock_sheet
from gizmo import gate
from gizmo import bodies

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")

SHEET_CAP = 2 * 1024 * 1024      # an imported sheet of 5,000 rows fits well inside


class StockSheetBody(bodies.Body):
    """What /api/stock/sheet reads: a line by id, the fields changed and
    what was seen, counts, a new line's fields, a sheet to import, the lines
    to export."""
    id: bodies.Id = None
    changes: bodies.Fields = None
    seen: bodies.Fields = None
    as_count: bodies.Flag = None
    counts: bodies.Records = None
    fields: bodies.Fields = None
    csv: bodies.Text = None
    ids: bodies.Items = None


def _answer(fn, what: str):
    """Run a stock rule and answer it the house way."""
    try:
        return gate._json(fn())
    except stock.Refused as e:
        return gate._json({"error": e.words, **e.extra}, e.status)
    except ValueError as e:
        return gate._json({"error": str(e)}, 400)
    except Exception:
        logger.exception("stock: %s failed", what)
        return gate._json({"error": "That could not be saved. Try again, or tell Cameron if it keeps happening."},
                          500)


def register(mcp, registry):
    """Add the stock sheet's routes to the app."""

    @mcp.custom_route("/api/stock/sheet", methods=["POST"])
    async def stock_sheet_route(request: Request):
        """The stock list: every line with the sheet's figures, editing a
        line, counting, and adding a line."""
        err, body, who = await gate._guard(request, model=StockSheetBody, max_body=SHEET_CAP, cap=SHEET_CAP)
        if err:
            return err
        op = str(body.get("op") or "list")
        if op == "list":
            return _answer(stock_sheet.listing, "listing")
        if op == "edit":
            return _answer(lambda: stock_sheet.edit(who, body.get("id"), body.get("changes") or {},
                                                    body.get("seen") or {}, stock.to_bool(body.get("as_count"))),
                           "an edit")
        if op == "counts":
            as_count = body.get("as_count")
            return _answer(lambda: stock_sheet.counts(who, body.get("counts"),
                                                      True if as_count is None else stock.to_bool(as_count)),
                           "a count")
        if op == "new":
            return _answer(lambda: stock_sheet.new_item(who, body.get("fields") or {}), "a new line")
        return gate._json({"error": "Unknown op."}, 400)
