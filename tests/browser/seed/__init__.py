"""Fill every screen of the browser suite's world with invented data.

Three recipes, each proven on 14 Oct 2026 against the dispatch setup, run in
this order: dashboards (the fake Shopify store, the saved reports,
reconciliation, the forecast, the Xero connector), workspace (accounts, the
work clock, the activity ledger, memory, skills, requests, chat), operations
(the Production Manager's orders joined to the same store, custom shipments,
the CRM, loan units, the Inbox, Files).

Each recipe runs in its own copy of the setup's names, never in the setup's
own globals: their helpers share names (_p, _iso, _NOW, _when ...), and a
function looks its helpers up when it is called, so a later recipe's _when
silently became the dashboards' date parser while the Production Manager
read its orders. No recipe rebinds a setup name, so a copy loses nothing.
The one thing that crosses is the dashboards' Shopify store (DASH), which the
operations recipe joins its orders to.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def _run(world, name, **shared):
    path = os.path.join(HERE, name + ".py")
    ns = dict(world)
    ns.update(shared, __name__="browser_seed_" + name, __file__=path)
    exec(compile(open(path, encoding="utf-8").read(), path, "exec"), ns)
    return ns


def seed(world):
    dash = _run(world, "dashboards")
    dash["seed_dashboards"]()          # dashboards.py defines it; the other two run as they load
    _run(world, "workspace")
    ops = _run(world, "operations", DASH=dash["DASH"])
    world["DASH"], world["OPS_ORDERS"] = dash["DASH"], ops["OPS_ORDERS"]
    with open(os.path.join(world["SCRATCH"], "workspace_browser_seed.json"), encoding="utf-8") as fh:
        browser = json.load(fh)
    return {"localStorage": browser["localStorage"], "orders": len(dash["DASH"]["orders"]),
            "ops_orders": len(ops["OPS_ORDERS"])}
