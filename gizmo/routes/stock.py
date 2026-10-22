"""The stock sheet's routes (plan 2a of the stock move): one route per part
of the sheet, each a flat body model and an `op`, all under /api/stock/,
claimed by the "stock" tab in gate._TAB_ROUTES.
"""
import logging
from starlette.requests import Request

from gizmo import stock, stock_orders, stock_quarters, stock_sheet
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


class StockOrdersBody(bodies.Body):
    """What /api/stock/orders reads: an order to place, a line to clear,
    reorder levels to set."""
    supplier: bodies.Text = None
    reference: bodies.Text = None
    currency: bodies.Text = None
    lines: bodies.Records = None
    id: bodies.Id = None
    open_only: bodies.Flag = None
    levels: bodies.Records = None


class StockSuppliersBody(bodies.Body):
    """What /api/stock/suppliers reads: one supplier's contact, or many.
    lead_days is checked by the rule (an empty box is 0, as the stock app
    took it)."""
    supplier: bodies.Text = None
    email: bodies.Text = None
    cc: bodies.Text = None
    contact_name: bodies.Text = None
    subject: bodies.Text = None
    body: bodies.Text = None
    min_order: bodies.Text = None
    contacts: bodies.Records = None


class StockReceiveBody(bodies.Body):
    """What /api/stock/receive reads: one line or a whole delivery taken
    in, a delivery undone, a received line counted against another order."""
    id: bodies.Id = None
    qty: bodies.Number = None
    invoice_no: bodies.Text = None
    date: bodies.Text = None
    order_id: bodies.Id = None
    lines: bodies.Records = None


class StockQuartersBody(bodies.Body):
    """What /api/stock/quarters reads: a name for the open quarter or the
    next, a quarter to download, two to compare."""
    label: bodies.Text = None
    new_label: bodies.Text = None
    id: bodies.Id = None
    left: bodies.Id = None
    right: bodies.Id = None


class StockOverviewBody(bodies.Body):
    """What /api/stock/overview reads: a warning to dismiss; the settings
    (low_stock_days and the two rates are checked by the rule, which takes
    an empty box as no change, as the stock app did)."""
    id: bodies.Id = None


class StockHistoryBody(bodies.Body):
    """What /api/stock/history reads: what to search for, and a line."""
    q: bodies.Text = None
    action: bodies.Text = None
    person: bodies.Id = None
    id: bodies.Id = None
    start: bodies.Text = None
    end: bodies.Text = None
    before: bodies.Whole = None
    limit: bodies.Whole = None


_CONTACT_FIELDS = ("supplier", "email", "cc", "contact_name", "subject", "body", "lead_days", "min_order")


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
        if op == "export":
            return _answer(lambda: stock_sheet.export_csv(body.get("ids") or []), "an export")
        if op == "import_preview":
            return _answer(lambda: stock_sheet.import_preview(str(body.get("csv") or "")), "an import preview")
        if op == "import_apply":
            return _answer(lambda: stock_sheet.import_apply(who, str(body.get("csv") or "")), "an import")
        return gate._json({"error": "Unknown op."}, 400)

    @mcp.custom_route("/api/stock/orders", methods=["POST"])
    async def stock_orders_route(request: Request):
        """Orders placed with suppliers, kept with what is received against
        them; what needs reordering, suggested levels, and setting levels."""
        err, body, who = await gate._guard(request, model=StockOrdersBody)
        if err:
            return err
        op = str(body.get("op") or "list")
        if op == "place":
            return _answer(lambda: stock_orders.place(who, body.get("supplier"), body.get("reference"),
                                                      body.get("currency"), body.get("lines")), "an order")
        if op == "clear":
            return _answer(lambda: stock_orders.clear(who, body.get("id")), "clearing an order")
        if op == "list":
            return _answer(lambda: stock_orders.orders(stock.to_bool(body.get("open_only") or False)), "the orders")
        if op == "reorder":
            return _answer(stock_orders.reorder, "the reorder list")
        if op == "suggest":
            return _answer(stock_orders.suggest, "suggested levels")
        if op == "levels":
            return _answer(lambda: stock_orders.set_levels(who, body.get("levels")), "reorder levels")
        return gate._json({"error": "Unknown op."}, 400)

    @mcp.custom_route("/api/stock/receive", methods=["POST"])
    async def stock_receive_route(request: Request):
        """Taking stock in: one line with its invoice, or a whole delivery,
        each counted against the orders it fills; undoing a delivery."""
        err, body, who = await gate._guard(request, model=StockReceiveBody)
        if err:
            return err
        op = str(body.get("op") or "")
        if op == "one":
            return _answer(lambda: stock_orders.receive_one(who, body.get("id"), body.get("qty"), body.get("invoice_no"),
                                                            body.get("date"), body.get("order_id")), "a receipt")
        if op == "delivery":
            return _answer(lambda: stock_orders.receive_delivery(who, body.get("lines"), body.get("invoice_no"),
                                                                 body.get("date")), "a delivery")
        if op == "rematch":
            return _answer(lambda: stock_orders.rematch(who, body.get("invoice_no"), body.get("id"),
                                                        body.get("order_id")), "changing an order")
        if op == "undo":
            return _answer(lambda: stock_orders.undo_delivery(who, body.get("invoice_no")), "undoing a delivery")
        return gate._json({"error": "Unknown op."}, 400)

    @mcp.custom_route("/api/stock/quarters", methods=["POST"])
    async def stock_quarters_route(request: Request):
        """Quarters: the open one and the closed ones, renaming, closing,
        a closed quarter's list to download, and comparing two."""
        err, body, who = await gate._guard(request, model=StockQuartersBody)
        if err:
            return err
        op = str(body.get("op") or "list")
        if op == "list":
            return _answer(stock_quarters.quarters, "the quarters")
        if op == "rename":
            return _answer(lambda: stock_quarters.rename(who, body.get("label")), "renaming the quarter")
        if op == "close":
            return _answer(lambda: stock_quarters.close(who, body.get("new_label")), "closing the quarter")
        if op == "csv":
            return _answer(lambda: stock_quarters.quarter_csv(body.get("id")), "a quarter's list")
        if op == "compare":
            return _answer(lambda: stock_quarters.compare(body.get("left"), body.get("right") or "current"),
                           "comparing quarters")
        return gate._json({"error": "Unknown op."}, 400)

    @mcp.custom_route("/api/stock/overview", methods=["POST"])
    async def stock_overview_route(request: Request):
        """The overview: "since you were last here", warnings, the figures
        over time, the settings and the exchange rates."""
        err, body, who = await gate._guard(request, model=StockOverviewBody)
        if err:
            return err
        op = str(body.get("op") or "briefing")
        reads = {"briefing": lambda: stock_quarters.briefing(who), "alerts": stock_quarters.alerts,
                 "trends": stock_quarters.trends, "forecast": stock_quarters.forecast,
                 "outlook": stock_quarters.outlook, "settings": stock_quarters.settings, "fx": stock_quarters.fx}
        if op in reads:
            return _answer(reads[op], op)
        if op == "ack":
            return _answer(lambda: stock_quarters.acknowledge(who), "acknowledging")
        if op == "dismiss":
            return _answer(lambda: stock_quarters.dismiss(who, body.get("id")), "dismissing a warning")
        if op == "save_settings":
            return _answer(lambda: stock_quarters.save_settings(who, body.get("low_stock_days"), body.get("fx_usd_gbp"),
                                                                body.get("fx_eur_gbp")), "the settings")
        return gate._json({"error": "Unknown op."}, 400)

    @mcp.custom_route("/api/stock/history", methods=["POST"])
    async def stock_history_route(request: Request):
        """The history of who changed what: searched, or one line's own with
        its forecast and its supplier's delivery time."""
        err, body, who = await gate._guard(request, model=StockHistoryBody)
        if err:
            return err
        op = str(body.get("op") or "search")
        if op == "search":
            return _answer(lambda: stock_quarters.history(body.get("q"), body.get("action"), body.get("person"),
                                                          None, body.get("start"), body.get("end"), body.get("before"),
                                                          body.get("limit")), "the history")
        if op == "item":
            return _answer(lambda: stock_quarters.item_sheet(body.get("id")), "a line's sheet")
        return gate._json({"error": "Unknown op."}, 400)

    @mcp.custom_route("/api/stock/suppliers", methods=["POST"])
    async def stock_suppliers_route(request: Request):
        """Suppliers: their contacts, delivery times, minimum orders and
        message templates, one at a time or all together."""
        err, body, who = await gate._guard(request, model=StockSuppliersBody)
        if err:
            return err
        op = str(body.get("op") or "list")
        if op == "list":
            return _answer(stock_orders.suppliers, "the suppliers")
        if op == "save":
            contact = {f: body[f] for f in _CONTACT_FIELDS if f in body}
            return _answer(lambda: stock_orders.save_supplier(who, contact), "a supplier")
        if op == "save_all":
            return _answer(lambda: stock_orders.save_suppliers(who, body.get("contacts")), "the suppliers")
        if op == "delete":
            return _answer(lambda: stock_orders.delete_supplier(who, body.get("supplier")), "removing a supplier")
        return gate._json({"error": "Unknown op."}, 400)
