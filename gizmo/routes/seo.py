"""The SEO and keyword routes: the SEO audit, keywords, and the keyword scan of
an outside page. Gathered from add_routes (stage 4 of the 14 October audit)
where the first stood; their paths are literal, so no request changes hands.
"""
import logging
import re
import anthropic
from starlette.requests import Request
from gizmo import ai as claude

import copilot as core
from gizmo import analytics
from gizmo import gate
from gizmo import knowledge
from gizmo import memory
from gizmo import skills as skillbook
from gizmo import seo

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


def register(mcp, registry):
    """Add the SEO and keyword routes to the app."""

    @mcp.custom_route("/api/seo", methods=["POST"])
    async def seo_route(request: Request):
        err, body, _who = await gate._guard(request, ai=True)
        if err:
            return err
        extra = core._profile_to_system(core._load_profile()) + memory._memory_to_system() + knowledge._knowledge_to_system() + skillbook._skills_to_system("SEO audit search pages meta titles descriptions product pages")
        try:
            result = await seo.run_seo_audit(registry, extra)
        except RuntimeError as e:
            return gate._json({"error": str(e)}, 500)
        except anthropic.APIError as e:
            logger.exception("Anthropic API error (seo)")
            return gate._json({"error": claude._ai_error_words(e)}, 502)
        except Exception:
            logger.exception("SEO audit failed")
            return gate._json({"error": "Couldn't run the SEO audit. Check the server logs."}, 500)
        result = analytics._save_analysis("seo", result)
        return gate._json(result)

    @mcp.custom_route("/api/keywords", methods=["POST"])
    async def keywords_route(request: Request):
        err, body, _who = await gate._guard(request, ai=True)
        if err:
            return err
        extra = core._profile_to_system(core._load_profile()) + memory._memory_to_system() + knowledge._knowledge_to_system() + skillbook._skills_to_system("keywords search terms CPC Google Ads competitors")
        try:
            res = await seo.run_keywords(registry, extra)
            res = analytics._save_analysis("keywords", res)
            return gate._json(res)
        except anthropic.APIError as e:
            logger.exception("Anthropic API error (keywords)")
            return gate._json({"error": claude._ai_error_words(e)}, 502)
        except RuntimeError as e:
            # The day's AI budget, a missing key, or a report that did not finish: said as it is.
            return gate._json({"error": str(e)}, 500)
        except Exception:
            logger.exception("Keyword analysis failed")
            return gate._json({"error": "Couldn't run the keyword analysis. Check the server logs."}, 500)

    @mcp.custom_route("/api/keyword-scan", methods=["POST"])
    async def keyword_scan_route(request: Request):
        err, body, _who = await gate._guard(request, ai=True)
        if err:
            return err
        url = (body.get("url") or "").strip()
        if not url:
            return gate._json({"error": "Enter a URL to scan."}, 400)
        if not re.match(r"^https?://", url, re.I):
            url = "https://" + url
        if len(url) > 2048:
            return gate._json({"error": "That URL is too long."}, 400)
        extra = core._profile_to_system(core._load_profile()) + memory._memory_to_system() + knowledge._knowledge_to_system() + skillbook._skills_to_system("keyword scan competitors ranking search")
        try:
            return gate._json(await seo.run_keyword_scan(registry, url, extra))
        except RuntimeError as e:
            return gate._json({"error": str(e)}, 400)
        except anthropic.APIError as e:
            logger.exception("Anthropic API error (keyword-scan)")
            return gate._json({"error": claude._ai_error_words(e)}, 502)
        except Exception:
            logger.exception("Keyword scan failed")
            return gate._json({"error": "Couldn't scan that URL. Check that it is a public web page."}, 500)
