"""The Products tab's routes: the product list and a product's page. Gathered
from add_routes (stage 4 of the 14 October audit) where the first stood;
their paths are literal, so no request changes hands.
"""
import logging
import anthropic
from starlette.requests import Request
from gizmo import ai as claude

import copilot as core
from gizmo import gate
from gizmo import knowledge
from gizmo import memory
from gizmo import orderbook
from gizmo import seo
from gizmo import profile as store_profile
from gizmo import products as catalog
from gizmo import bodies

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")



class ProductBody(bodies.Body):
    """What /api/product reads (gizmo/bodies.py): the Shopify product."""
    product_id: bodies.Whole = None



class ProductsBody(bodies.Body):
    """What /api/products reads (gizmo/bodies.py): how many months, and whether to read afresh."""
    months: bodies.Whole = None
    fresh: bodies.Flag = None


def register(mcp, registry):
    """Add the Products tab's routes to the app."""

    @mcp.custom_route("/api/products", methods=["POST"])
    async def products_route(request: Request):
        err, body, _who = await gate._guard(request, model=ProductsBody)
        if err:
            return err
        try:
            months = int(body.get("months") or 0) or None
        except (TypeError, ValueError):
            months = None
        try:
            orderbook._refresh_asked(body)
            return gate._json(await catalog.run_products_list(registry, months))
        except Exception:
            logger.exception("Product list failed")
            return gate._json({"error": "Couldn't load products."}, 500)

    @mcp.custom_route("/api/product", methods=["POST"])
    async def product_route(request: Request):
        err, body, _who = await gate._guard(request, ai=True, model=ProductBody)
        if err:
            return err
        try:
            pid = int(body.get("product_id"))
        except (TypeError, ValueError):
            return gate._json({"error": "A numeric product_id is required."}, 400)
        # The skills are chosen inside run_product_audit, once the product's
        # title, type and tags are known: 'product plan 8123456789' matched nothing.
        extra = store_profile._profile_to_system(store_profile._load_profile()) + memory._memory_to_system() + knowledge._knowledge_to_system()
        try:
            return gate._json(await seo.run_product_audit(registry, pid, extra))
        except RuntimeError as e:
            return gate._json({"error": str(e)}, 400)
        except anthropic.APIError as e:
            logger.exception("Anthropic API error (product)")
            return gate._json({"error": claude._ai_error_words(e)}, 502)
        except Exception:
            logger.exception("Product audit failed")
            return gate._json({"error": "Couldn't analyze this product. Check the server logs."}, 500)
