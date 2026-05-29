#!/usr/bin/env python3
"""
Google Search Console + GA4 connector (service-account auth).

Single-tenant: the merchant creates a Google service account, grants its email
read access to their GA4 property + Search Console site, and provides:
  GOOGLE_SERVICE_ACCOUNT_JSON  the service-account key (full JSON, as a string)
  GA4_PROPERTY_ID              the GA4 property id, e.g. "123456789"
  GSC_SITE_URL                 e.g. "https://acme.com/" or "sc-domain:acme.com"

Everything is read-only. If not configured, is_configured() is False and the
rest of the app behaves exactly as before.
"""
import os
import json
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx

logger = logging.getLogger("shopify_mcp.google")

GOOGLE_SA_JSON  = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
GA4_PROPERTY_ID = os.environ.get("GA4_PROPERTY_ID", "").replace("properties/", "").strip()
GSC_SITE_URL    = os.environ.get("GSC_SITE_URL", "").strip()

SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
]

_creds = None  # cached google.oauth2 credentials object


def gsc_configured() -> bool:
    return bool(GOOGLE_SA_JSON and GSC_SITE_URL)


def ga4_configured() -> bool:
    return bool(GOOGLE_SA_JSON and GA4_PROPERTY_ID)


def is_configured() -> bool:
    return gsc_configured() or ga4_configured()


def _build_creds():
    """Build (once) service-account credentials from the JSON key. Raises on a
    malformed key so callers can surface a clear message."""
    global _creds
    if _creds is None:
        from google.oauth2 import service_account
        info = json.loads(GOOGLE_SA_JSON)
        _creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return _creds


def _refresh_sync(creds) -> str:
    from google.auth.transport.requests import Request
    if not creds.valid:
        creds.refresh(Request())
    return creds.token


async def _token() -> str:
    creds = _build_creds()
    # creds.refresh makes a blocking network call — keep it off the event loop.
    return await asyncio.to_thread(_refresh_sync, creds)


async def _post(url: str, body: dict) -> dict:
    token = await _token()
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.post(url, headers={"Authorization": f"Bearer {token}"}, json=body)
        if r.status_code == 403:
            raise PermissionError("Google denied access — grant the service-account email read access "
                                  "to this GA4 property / Search Console site.")
        r.raise_for_status()
        return r.json()


def _date_range(days: int, lag_days: int = 0) -> tuple[str, str]:
    end = datetime.now(timezone.utc).date() - timedelta(days=lag_days)
    start = end - timedelta(days=days)
    return start.isoformat(), end.isoformat()


# ---------------------------------------------------------------------------
# Search Console
# ---------------------------------------------------------------------------

def _gsc_url() -> str:
    return f"https://www.googleapis.com/webmasters/v3/sites/{quote(GSC_SITE_URL, safe='')}/searchAnalytics/query"


async def gsc_overview(days: int = 28) -> dict:
    """Aggregate clicks/impressions/CTR/position over the window (GSC lags ~2 days)."""
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
    except PermissionError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.warning(f"GSC overview failed: {e}")
        return {"error": "Could not fetch Search Console data."}


async def gsc_top_queries(days: int = 28, limit: int = 15) -> dict:
    """Top queries by clicks, with impressions/CTR/position — the raw material for
    CTR-opportunity analysis (high impressions + low CTR + mid position)."""
    if not gsc_configured():
        return {}
    start, end = _date_range(days, lag_days=2)
    try:
        data = await _post(_gsc_url(), {"startDate": start, "endDate": end, "dimensions": ["query"],
                                        "rowLimit": limit, "dataState": "all"})
        out = []
        for r in data.get("rows", []):
            out.append({"query": (r.get("keys") or [""])[0], "clicks": int(r.get("clicks", 0)),
                        "impressions": int(r.get("impressions", 0)), "ctr": round(r.get("ctr", 0) * 100, 2),
                        "position": round(r.get("position", 0), 1)})
        return {"queries": out, "range_days": days}
    except PermissionError as e:
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
    """Sessions + revenue totals and the top traffic channels over the window."""
    if not ga4_configured():
        return {}
    start, end = _date_range(days)
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
        channels = [{"channel": (r.get("dimensionValues") or [{}])[0].get("value", "—"),
                     "sessions": int(float((r.get("metricValues") or [{}])[0].get("value", 0)))}
                    for r in chan.get("rows", [])]
        return {"sessions": sessions, "revenue": revenue, "engaged_sessions": engaged,
                "top_channels": channels, "range_days": days}
    except PermissionError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.warning(f"GA4 summary failed: {e}")
        return {"error": "Could not fetch GA4 data."}
