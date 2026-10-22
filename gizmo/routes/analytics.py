"""The report routes: the overview, the analysis cache, the reorder radar,
customers and customer tags. Gathered from add_routes (stage 4 of the 14
October audit) where the first stood; their paths are literal, so no request
changes hands.
"""
import logging
import anthropic
from starlette.requests import Request
from gizmo import ai as claude

from gizmo import profile as store_profile
from gizmo import analytics
from gizmo import gate
from gizmo import knowledge
from gizmo import memory
from gizmo import orderbook
from gizmo import skills as skillbook
from gizmo import team
from gizmo import bodies

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")



class CustomersBody(bodies.Body):
    """What /api/customers reads (gizmo/bodies.py): the segment, and whether to read afresh."""
    segment: bodies.Text = None
    fresh: bodies.Flag = None



class OverviewBody(bodies.Body):
    """What /api/overview reads (gizmo/bodies.py): whether to read afresh."""
    fresh: bodies.Flag = None


def register(mcp, registry):
    """Add the report routes to the app."""

    @mcp.custom_route("/api/overview", methods=["POST"])
    async def overview(request: Request):
        err, body, _who = await gate._guard(request, ai=True, model=OverviewBody)
        if err:
            return err
        profile = store_profile._load_profile()
        extra = store_profile._profile_to_system(profile) + memory._memory_to_system() + knowledge._knowledge_to_system() + skillbook._skills_to_system("overview report revenue orders customers products stock")
        track = (profile.get("prefs") or {}).get("track_inventory", True)
        try:
            orderbook._refresh_asked(body)
            result = await analytics.run_overview(registry, extra, bool(track))
        except RuntimeError as e:
            return gate._json({"error": str(e)}, 500)
        except anthropic.APIError as e:
            logger.exception("Anthropic API error (overview)")
            return gate._json({"error": claude._ai_error_words(e)}, 502)
        except Exception:
            logger.exception("Overview failed")
            return gate._json({"error": "Couldn't build the overview. Check the server logs."}, 500)
        result = analytics._save_analysis("overview", result)
        return gate._json(result)

    @mcp.custom_route("/api/cache", methods=["POST"])
    async def cache_route(request: Request):
        # Returns the last saved result of each AI tab so the app can show it
        # instantly on open. Read-only, no AI, no body needed.
        err, _body, who = await gate._guard(request, body=False)
        if err:
            return err
        cache = analytics._load_analysis_cache()
        # This one route carries several tabs' cached results, so the tab map
        # cannot gate it wholesale: filter each section to what this account
        # may open, or a tab restriction would leak here.
        allowed = team._user_tabs(who)
        def ok_tab(tab):
            return allowed is None or tab in allowed
        out = {k: cache[k] for k in ("overview", "seo", "keywords")
               if ok_tab(k) and isinstance(cache.get(k), dict) and "result" in cache[k]}
        if ok_tab("customers") and isinstance(cache.get("customers_segments"), dict):
            out["customers_segments"] = cache["customers_segments"]
        return gate._json(out)

    @mcp.custom_route("/api/reorder-radar", methods=["POST"])
    async def reorder_radar_route(request: Request):
        # Overdue repeat accounts + untagged trade customers. Shopify read, no AI.
        err, body, _who = await gate._guard(request)
        if err:
            return err
        try:
            return gate._json(await analytics.run_reorder_radar(registry))
        except Exception:
            logger.exception("Reorder radar failed")
            return gate._json({"error": "Couldn't build the trade radar."}, 500)

    @mcp.custom_route("/api/customers", methods=["POST"])
    async def customers_route(request: Request):
        err, body, _who = await gate._guard(request, ai=True, model=CustomersBody)
        if err:
            return err
        segment = (body.get("segment") or "").strip()[:80]
        extra = store_profile._profile_to_system(store_profile._load_profile()) + memory._memory_to_system() + knowledge._knowledge_to_system() + skillbook._skills_to_system("customers retention sectors trade repeat lifetime value")
        try:
            orderbook._refresh_asked(body)
            res = await analytics.run_customers(registry, extra, segment=segment or None)
            if res.get("error"):
                return gate._json(res, 502)      # nothing worked out, nothing saved
            res = analytics._save_customer_segment(segment or "__all__", res)
            return gate._json(res)
        except anthropic.APIError as e:
            logger.exception("Anthropic API error (customers)")
            return gate._json({"error": claude._ai_error_words(e)}, 502)
        except RuntimeError as e:
            # The day's AI budget, a missing key, or a report that did not finish: said as it is.
            return gate._json({"error": str(e)}, 500)
        except Exception:
            logger.exception("Customer analysis failed")
            return gate._json({"error": "Couldn't run the customer analysis. Check the server logs."}, 500)

    @mcp.custom_route("/api/customer-tags", methods=["POST"])
    async def customer_tags_route(request: Request):
        # Auto-detect the customer-account tags in use (the merchant's sectors). No AI.
        err, _body, _who = await gate._guard(request, body=False)
        if err:
            return err
        try:
            cm: dict = {}
            customers = await analytics._paginate_customers(registry, meta=cm)
            if cm.get("failed") and not customers:
                return gate._json({"error": "Couldn't read your customers from Shopify just now."}, 502)
            return gate._json({"tags": analytics._detect_sector_tags(customers), "total": len(customers)})
        except Exception:
            logger.exception("customer-tags failed")
            return gate._json({"error": "Couldn't read your customer tags."}, 500)
