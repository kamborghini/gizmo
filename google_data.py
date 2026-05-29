#!/usr/bin/env python3
"""
Google Search Console + GA4 connector.

Auth is OAuth (the merchant connects their OWN Google account once, via a
secret-gated URL; we store the resulting refresh token under /data). A
service-account path is kept as a dormant fallback, but Google currently has a
bug that blocks granting newly-created service accounts access to GSC/GA4, so
OAuth is the supported path.

Env:
  GOOGLE_OAUTH_CLIENT_ID      OAuth 2.0 Web client id
  GOOGLE_OAUTH_CLIENT_SECRET  OAuth 2.0 Web client secret
  GOOGLE_CONNECT_SECRET       gate for the one-time connect URL
  GA4_PROPERTY_ID             GA4 property id, e.g. "123456789"
  GSC_SITE_URL                e.g. "https://acme.com/" or "sc-domain:acme.com"
  GOOGLE_SERVICE_ACCOUNT_JSON (optional, dormant fallback)
Everything is read-only. Unconfigured → is_configured() is False and the app
behaves exactly as before.
"""
import os
import json
import time
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode

import httpx

logger = logging.getLogger("shopify_mcp.google")

OAUTH_CLIENT_ID     = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")
CONNECT_SECRET      = os.environ.get("GOOGLE_CONNECT_SECRET", "")
GA4_PROPERTY_ID     = os.environ.get("GA4_PROPERTY_ID", "").replace("properties/", "").strip()
GSC_SITE_URL        = os.environ.get("GSC_SITE_URL", "").strip()
GOOGLE_SA_JSON      = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
OAUTH_TOKEN_PATH    = os.environ.get("GOOGLE_OAUTH_TOKEN_PATH", "/data/google_oauth.json")

SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
]
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
AUTH_ENDPOINT  = "https://accounts.google.com/o/oauth2/v2/auth"

_sa_creds = None                       # cached service-account credentials
_access: dict = {"token": "", "exp": 0.0}  # cached OAuth access token


class GoogleAPIError(Exception):
    """Carries Google's own error message so the UI can show the real cause."""


# ---------------------------------------------------------------------------
# Connection state
# ---------------------------------------------------------------------------

def oauth_client_configured() -> bool:
    return bool(OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET)


def _load_refresh_token() -> str:
    try:
        with open(OAUTH_TOKEN_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh).get("refresh_token", "")
    except Exception:
        return ""


def save_refresh_token(token: str) -> None:
    os.makedirs(os.path.dirname(OAUTH_TOKEN_PATH) or ".", exist_ok=True)
    tmp = OAUTH_TOKEN_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"refresh_token": token, "connected_at": datetime.now(timezone.utc).isoformat()}, fh)
    os.replace(tmp, OAUTH_TOKEN_PATH)
    _access["token"], _access["exp"] = "", 0.0  # invalidate cache


def oauth_connected() -> bool:
    return bool(_load_refresh_token())


def _auth_available() -> bool:
    return oauth_connected() or bool(GOOGLE_SA_JSON)


def gsc_configured() -> bool:
    """True when we can actually query Search Console right now."""
    return _auth_available() and bool(GSC_SITE_URL)


def ga4_configured() -> bool:
    return _auth_available() and bool(GA4_PROPERTY_ID)


def gsc_enabled() -> bool:
    """True when the admin intends to use GSC (site set) — for tool registration."""
    return bool(GSC_SITE_URL)


def ga4_enabled() -> bool:
    return bool(GA4_PROPERTY_ID)


def is_configured() -> bool:
    return gsc_configured() or ga4_configured()


def status() -> dict:
    return {
        "oauth_client": oauth_client_configured(),
        "connected": oauth_connected(),
        "gsc_site": GSC_SITE_URL or None,
        "ga4_property": GA4_PROPERTY_ID or None,
        "gsc_ready": gsc_configured(),
        "ga4_ready": ga4_configured(),
    }


# ---------------------------------------------------------------------------
# OAuth flow helpers
# ---------------------------------------------------------------------------

def consent_url(redirect_uri: str, state: str) -> str:
    params = {
        "client_id": OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",          # force a refresh token every time
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTH_ENDPOINT}?{urlencode(params)}"


async def exchange_code(code: str, redirect_uri: str) -> bool:
    """Exchange an authorization code for tokens; persist the refresh token."""
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.post(TOKEN_ENDPOINT, data={
            "client_id": OAUTH_CLIENT_ID, "client_secret": OAUTH_CLIENT_SECRET,
            "code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri,
        })
    if r.status_code != 200:
        logger.warning(f"OAuth code exchange failed: {r.status_code} {r.text[:200]}")
        return False
    data = r.json()
    rt = data.get("refresh_token")
    if not rt:
        logger.warning("OAuth exchange returned no refresh_token (already consented? use prompt=consent).")
        return False
    save_refresh_token(rt)
    return True


# ---------------------------------------------------------------------------
# Token minting (OAuth preferred, service-account fallback)
# ---------------------------------------------------------------------------

def _sa_refresh_sync() -> str:
    global _sa_creds
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    if _sa_creds is None:
        _sa_creds = service_account.Credentials.from_service_account_info(
            json.loads(GOOGLE_SA_JSON), scopes=SCOPES)
    if not _sa_creds.valid:
        _sa_creds.refresh(Request())
    return _sa_creds.token


async def _token() -> str:
    # OAuth access token (cached until ~1 min before expiry).
    rt = _load_refresh_token()
    if rt:
        if _access["token"] and time.monotonic() < _access["exp"]:
            return _access["token"]
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.post(TOKEN_ENDPOINT, data={
                "client_id": OAUTH_CLIENT_ID, "client_secret": OAUTH_CLIENT_SECRET,
                "refresh_token": rt, "grant_type": "refresh_token",
            })
        if r.status_code != 200:
            raise RuntimeError("Google OAuth token refresh failed. Reconnect Google.")
        data = r.json()
        _access["token"] = data["access_token"]
        _access["exp"] = time.monotonic() + int(data.get("expires_in", 3600)) - 60
        return _access["token"]
    if GOOGLE_SA_JSON:
        return await asyncio.to_thread(_sa_refresh_sync)
    raise RuntimeError("Google is not connected.")


async def _post(url: str, body: dict) -> dict:
    token = await _token()
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.post(url, headers={"Authorization": f"Bearer {token}"}, json=body)
        if r.status_code >= 400:
            # Surface Google's own error message — it's specific and actionable
            # (e.g. "<API> has not been used in project N before or it is disabled…",
            # or "User does not have sufficient permission for site '…'").
            try:
                detail = r.json().get("error", {}).get("message", "") or r.text[:300]
            except Exception:
                detail = r.text[:300]
            logger.warning(f"Google API {r.status_code}: {detail}")
            raise GoogleAPIError(detail.strip()[:400] or f"HTTP {r.status_code}")
        return r.json()


def _date_range(days: int, lag_days: int = 0) -> tuple[str, str]:
    end = datetime.now(timezone.utc).date() - timedelta(days=lag_days)
    return (end - timedelta(days=days)).isoformat(), end.isoformat()


# ---------------------------------------------------------------------------
# Search Console
# ---------------------------------------------------------------------------

def _gsc_url() -> str:
    return f"https://www.googleapis.com/webmasters/v3/sites/{quote(GSC_SITE_URL, safe='')}/searchAnalytics/query"


async def gsc_overview(days: int = 28) -> dict:
    if not gsc_configured():
        return {}
    start, end = _date_range(days, lag_days=2)
    try:
        data = await _post(_gsc_url(), {"startDate": start, "endDate": end, "dataState": "all"})
        rows = data.get("rows", [])
        if not rows:
            return {"clicks": 0, "impressions": 0, "ctr": 0, "position": None, "range_days": days}
        r = rows[0]
        return {"clicks": int(r.get("clicks", 0)), "impressions": int(r.get("impressions", 0)),
                "ctr": round(r.get("ctr", 0) * 100, 2), "position": round(r.get("position", 0), 1),
                "range_days": days}
    except GoogleAPIError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.warning(f"GSC overview failed: {e}")
        return {"error": "Could not fetch Search Console data."}


async def gsc_top_queries(days: int = 28, limit: int = 15) -> dict:
    if not gsc_configured():
        return {}
    start, end = _date_range(days, lag_days=2)
    try:
        data = await _post(_gsc_url(), {"startDate": start, "endDate": end, "dimensions": ["query"],
                                        "rowLimit": limit, "dataState": "all"})
        out = [{"query": (r.get("keys") or [""])[0], "clicks": int(r.get("clicks", 0)),
                "impressions": int(r.get("impressions", 0)), "ctr": round(r.get("ctr", 0) * 100, 2),
                "position": round(r.get("position", 0), 1)} for r in data.get("rows", [])]
        return {"queries": out, "range_days": days}
    except GoogleAPIError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.warning(f"GSC queries failed: {e}")
        return {"error": "Could not fetch Search Console queries."}


# ---------------------------------------------------------------------------
# GA4 (Data API)
# ---------------------------------------------------------------------------

def _ga4_url() -> str:
    return f"https://analyticsdata.googleapis.com/v1beta/properties/{GA4_PROPERTY_ID}:runReport"


async def ga4_summary(days: int = 28) -> dict:
    if not ga4_configured():
        return {}
    try:
        totals = await _post(_ga4_url(), {
            "dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "yesterday"}],
            "metrics": [{"name": "sessions"}, {"name": "totalRevenue"}, {"name": "engagedSessions"}],
        })
        row = (totals.get("rows") or [{}])
        vals = (row[0].get("metricValues") if row and row[0] else []) or []
        sessions = int(float(vals[0]["value"])) if len(vals) > 0 else 0
        revenue = round(float(vals[1]["value"]), 2) if len(vals) > 1 else 0.0
        engaged = int(float(vals[2]["value"])) if len(vals) > 2 else 0

        chan = await _post(_ga4_url(), {
            "dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "yesterday"}],
            "dimensions": [{"name": "sessionDefaultChannelGroup"}],
            "metrics": [{"name": "sessions"}],
            "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
            "limit": 5,
        })
        channels = [{"channel": (r.get("dimensionValues") or [{}])[0].get("value", "Other"),
                     "sessions": int(float((r.get("metricValues") or [{}])[0].get("value", 0)))}
                    for r in chan.get("rows", [])]
        return {"sessions": sessions, "revenue": revenue, "engaged_sessions": engaged,
                "top_channels": channels, "range_days": days}
    except GoogleAPIError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.warning(f"GA4 summary failed: {e}")
        return {"error": "Could not fetch GA4 data."}


# ---------------------------------------------------------------------------
# Monthly time series (for trend charts)
# ---------------------------------------------------------------------------

async def ga4_timeseries(days: int = 760) -> dict:
    """Monthly sessions, revenue, engaged sessions and pageviews for up to ~24 months
    (GA4 'yearMonth'), plus a channel breakdown over the whole range."""
    if not ga4_configured():
        return {}
    days = max(28, min(int(days), 760))
    out: dict = {}
    try:
        data = await _post(_ga4_url(), {
            "dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "yesterday"}],
            "dimensions": [{"name": "yearMonth"}],
            "metrics": [{"name": "sessions"}, {"name": "totalRevenue"},
                        {"name": "engagedSessions"}, {"name": "screenPageViews"}],
            "orderBys": [{"dimension": {"dimensionName": "yearMonth"}}],
            "limit": 100,
        })
        sessions, revenue, engaged, pageviews = [], [], [], []
        for r in data.get("rows", []):
            ym = (r.get("dimensionValues") or [{}])[0].get("value", "")   # "202501"
            if len(ym) != 6:
                continue
            label = f"{ym[:4]}-{ym[4:]}"
            v = r.get("metricValues") or []
            g = lambda i: float(v[i]["value"]) if len(v) > i else 0.0
            sessions.append({"label": label, "value": int(g(0))})
            revenue.append({"label": label, "value": round(g(1), 2)})
            engaged.append({"label": label, "value": int(g(2))})
            pageviews.append({"label": label, "value": int(g(3))})
        out = {"sessions": sessions, "revenue": revenue, "engaged": engaged, "pageviews": pageviews}
    except GoogleAPIError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.warning(f"GA4 timeseries failed: {e}")
        return {}
    try:
        ch = await _post(_ga4_url(), {
            "dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "yesterday"}],
            "dimensions": [{"name": "sessionDefaultChannelGroup"}],
            "metrics": [{"name": "sessions"}],
            "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
            "limit": 8,
        })
        out["channels"] = [{"label": (r.get("dimensionValues") or [{}])[0].get("value", "Other"),
                            "value": int(float((r.get("metricValues") or [{}])[0].get("value", 0)))}
                           for r in ch.get("rows", [])]
    except Exception:
        pass
    return out


async def gsc_timeseries(days: int = 480) -> dict:
    """Monthly clicks + impressions, aggregated from daily rows. GSC keeps ~16 months."""
    if not gsc_configured():
        return {}
    days = max(28, min(int(days), 480))
    start, end = _date_range(days, lag_days=2)
    try:
        data = await _post(_gsc_url(), {"startDate": start, "endDate": end,
                                        "dimensions": ["date"], "rowLimit": 500, "dataState": "all"})
        clicks_m: dict = {}
        impr_m: dict = {}
        pos_w: dict = {}    # sum(position * impressions) per month, for an impression-weighted avg
        for r in data.get("rows", []):
            d = (r.get("keys") or [""])[0]    # "YYYY-MM-DD"
            if len(d) < 7:
                continue
            mk = d[:7]
            c = int(r.get("clicks", 0)); imp = int(r.get("impressions", 0))
            clicks_m[mk] = clicks_m.get(mk, 0) + c
            impr_m[mk] = impr_m.get(mk, 0) + imp
            pos_w[mk] = pos_w.get(mk, 0.0) + float(r.get("position", 0)) * imp
        ks = sorted(clicks_m.keys())
        clicks = [{"label": k, "value": clicks_m[k]} for k in ks]
        impressions = [{"label": k, "value": impr_m[k]} for k in ks]
        ctr = [{"label": k, "value": round(clicks_m[k] / impr_m[k] * 100, 2) if impr_m[k] else 0} for k in ks]
        position = [{"label": k, "value": round(pos_w[k] / impr_m[k], 1) if impr_m[k] else 0} for k in ks]
        return {"clicks": clicks, "impressions": impressions, "ctr": ctr, "position": position}
    except GoogleAPIError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.warning(f"GSC timeseries failed: {e}")
        return {}


# ---------------------------------------------------------------------------
# Per-page (per-product) queries, filtered by URL path
# ---------------------------------------------------------------------------

async def gsc_page_queries(page_path: str, days: int = 28, limit: int = 10) -> dict:
    """Search Console performance for one page (path 'contains' match): totals plus
    the top queries that page ranks for."""
    if not gsc_configured():
        return {}
    start, end = _date_range(days, lag_days=2)
    flt = [{"filters": [{"dimension": "page", "operator": "contains", "expression": page_path}]}]
    try:
        tot = await _post(_gsc_url(), {"startDate": start, "endDate": end, "dataState": "all",
                                       "dimensionFilterGroups": flt})
        rows = tot.get("rows", [])
        totals = {}
        if rows:
            r = rows[0]
            totals = {"clicks": int(r.get("clicks", 0)), "impressions": int(r.get("impressions", 0)),
                      "ctr": round(r.get("ctr", 0) * 100, 2), "position": round(r.get("position", 0), 1)}
        q = await _post(_gsc_url(), {"startDate": start, "endDate": end, "dimensions": ["query"],
                                     "rowLimit": limit, "dataState": "all", "dimensionFilterGroups": flt})
        queries = [{"query": (r.get("keys") or [""])[0], "clicks": int(r.get("clicks", 0)),
                    "impressions": int(r.get("impressions", 0)), "ctr": round(r.get("ctr", 0) * 100, 2),
                    "position": round(r.get("position", 0), 1)} for r in q.get("rows", [])]
        return {"totals": totals, "queries": queries, "range_days": days}
    except GoogleAPIError as e:
        return {"error": str(e)[:300]}
    except Exception as e:
        logger.warning(f"GSC page queries failed: {e}")
        return {"error": "Could not fetch Search Console data for this page."}


async def ga4_page(path: str, days: int = 28) -> dict:
    """GA4 sessions + revenue for pages whose path contains the given fragment."""
    if not ga4_configured():
        return {}
    try:
        data = await _post(_ga4_url(), {
            "dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "yesterday"}],
            "metrics": [{"name": "sessions"}, {"name": "totalRevenue"}],
            "dimensionFilter": {"filter": {"fieldName": "pagePath",
                                           "stringFilter": {"matchType": "CONTAINS", "value": path}}},
        })
        row = (data.get("rows") or [{}])
        vals = (row[0].get("metricValues") if row and row[0] else []) or []
        return {"sessions": int(float(vals[0]["value"])) if len(vals) > 0 else 0,
                "revenue": round(float(vals[1]["value"]), 2) if len(vals) > 1 else 0.0,
                "range_days": days}
    except GoogleAPIError as e:
        return {"error": str(e)[:300]}
    except Exception as e:
        logger.warning(f"GA4 page failed: {e}")
        return {"error": "Could not fetch GA4 data for this page."}
