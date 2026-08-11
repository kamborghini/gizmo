#!/usr/bin/env python3
"""
World Options Ecommerce REST API connector - shipping: quote, book, label, track.

Isolated on purpose: every World-Options-specific request lives in this file and
the rest of the app speaks our own normalized shapes, so the courier provider
can be swapped by editing one module (see the TrueSpeed routing precedent).

Auth: one merchant API key, sent as the `X-AUTH-TOKEN` header on every call. The
key comes from env WO_API_KEY, or is set at runtime via set_api_key() (the app
persists it server-side, never echoes it back, and keeps it out of logs, URLs
and backups).

Base URL (live, UK): https://ecommerce.worldoptions.com
Full contract notes: docs/worldoptions-api.md
"""
import os
import asyncio
import logging
from urllib.parse import quote as _urlquote

import httpx

logger = logging.getLogger("shopify_mcp.worldoptions")

DEFAULT_BASE = "https://ecommerce.worldoptions.com"

_state = {
    "api_key":  os.environ.get("WO_API_KEY", "").strip(),
    "base_url": (os.environ.get("WO_BASE_URL", DEFAULT_BASE) or DEFAULT_BASE).rstrip("/"),
}
_gate = asyncio.Semaphore(4)          # be polite to WO's API
_RETRY_STATUS = {429, 500, 502, 503, 504}
_carrier_cache: dict = {"at": 0.0, "carriers": None}


class WorldOptionsError(Exception):
    """Carries World Options' own message so the UI can show the real cause."""


# ---------------------------------------------------------------------------
# Connection state
# ---------------------------------------------------------------------------
def configured() -> bool:
    return bool(_state["api_key"])


def base_url() -> str:
    return _state["base_url"]


def set_api_key(key) -> None:
    """Set (or clear, with a falsy value) the X-AUTH-TOKEN key."""
    _state["api_key"] = (key or "").strip()


def set_base_url(url) -> None:
    _state["base_url"] = ((url or DEFAULT_BASE).strip() or DEFAULT_BASE).rstrip("/")


def key_last4() -> str:
    k = _state["api_key"]
    return k[-4:] if len(k) >= 4 else ("set" if k else "")


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def _extract_message(resp: httpx.Response) -> str:
    """Pull the human-readable reason out of an API Platform / Symfony error."""
    try:
        data = resp.json()
    except Exception:
        return (resp.text or "")[:300]
    if isinstance(data, dict):
        for key in ("detail", "hydra:description", "message", "title", "error"):
            v = data.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()[:400]
        viol = data.get("violations")
        if isinstance(viol, list) and viol:
            parts = []
            for x in viol:
                if isinstance(x, dict):
                    parts.append(f"{x.get('propertyPath', '')}: {x.get('message', '')}".strip(": "))
            if parts:
                return ("; ".join(parts))[:400]
    return (resp.text or "")[:300]


async def _request(method: str, path: str, body=None, params=None) -> dict:
    if not _state["api_key"]:
        raise WorldOptionsError("World Options is not connected. Add your API key in Settings.")
    url = _state["base_url"] + path
    headers = {"X-AUTH-TOKEN": _state["api_key"], "Accept": "application/json"}
    async with _gate:
        last_exc = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.request(method, url, headers=headers,
                                                params=params, json=body, timeout=30.0)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_exc = e
                if attempt >= 2:
                    break
                await asyncio.sleep(min(2 ** attempt, 6))
                continue
            if resp.status_code in _RETRY_STATUS and attempt < 2:
                await asyncio.sleep(min(2 ** attempt, 6))
                continue
            return _handle(resp)
    raise WorldOptionsError(
        f"Could not reach World Options ({type(last_exc).__name__ if last_exc else 'network error'}). "
        "Try again in a moment.")


def _handle(resp: httpx.Response) -> dict:
    sc = resp.status_code
    if sc in (401, 403):
        raise WorldOptionsError(
            "World Options rejected the API key (unauthorized). Check the key in Settings.")
    if sc >= 400:
        raise WorldOptionsError(f"World Options error {sc}: {_extract_message(resp)}")
    if sc == 204 or not resp.content:
        return {}
    try:
        return resp.json()
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Address + normalization helpers
# ---------------------------------------------------------------------------
def _addr(a: dict) -> dict:
    """Our internal address dict -> the World Options address block."""
    a = a or {}
    return {
        "name":      str(a.get("name") or "")[:70],
        "company":   str(a.get("company") or "")[:70],
        "firstname": str(a.get("firstname") or "")[:50],
        "lastname":  str(a.get("lastname") or "")[:50],
        "street":    str(a.get("street") or "")[:120],
        "postcode":  str(a.get("postcode") or "")[:20],
        "city":      str(a.get("city") or "")[:60],
        "state":     str(a.get("state") or "")[:60],
        "country":   str(a.get("country") or "")[:2].upper(),
        "phone":     str(a.get("phone") or "")[:30],
        "email":     str(a.get("email") or "")[:120],
    }


def _box(b: dict) -> dict:
    return {
        "width":  float(b.get("width") or 0),
        "length": float(b.get("length") or 0),
        "depth":  float(b.get("depth") or 0),
        "weight": float(b.get("weight") or 0),
    }


def _normalize_rate(data: dict, fallback_currency: str) -> dict:
    """Flatten a Rate resource's grouped priced options into one sorted list.

    A single POST /api/rates returns ONE Rate (top-level `id`) carrying several
    groups of priced carrier+service options; the caller books with the Rate id
    plus the chosen option's `carrier_id` (the RateCarrier id)."""
    rate_id = data.get("id")
    options = []
    for group_key in ("webservicesRates", "internalRates", "customRates", "backupRates"):
        for grp in (data.get(group_key) or []):
            for cs in (grp.get("carriersServices") or []):
                svc = cs.get("carrierService") or {}
                carrier = svc.get("carrier") or {}
                cur = cs.get("currency") or {}
                amount = cs.get("amount")
                options.append({
                    "rate_id":      rate_id,
                    "carrier_id":   cs.get("id"),          # RateCarrier id - the booking selector
                    # The underlying Carrier resource id, kept so that if WO's shipment
                    # `carrier` field turns out to mean the Carrier id (not the RateCarrier
                    # id), book() can switch selectors by changing one line.
                    "wo_carrier_id": carrier.get("id"),
                    "carrier_name": carrier.get("name") or svc.get("name") or "",
                    "carrier_code": carrier.get("code") or "",
                    "service_name": svc.get("name") or "",
                    "service_code": svc.get("code") or "",
                    "amount":       (float(amount) if amount is not None else None),
                    "currency":     cur.get("code") or fallback_currency,
                    "delivery":     str(cs.get("delivery") or ""),
                    "package":      str(cs.get("package") or ""),
                    "group":        group_key,
                    "drop_off":     cs.get("dropOffPoint") or [],
                })
    options.sort(key=lambda o: (o["amount"] is None, o["amount"] if o["amount"] is not None else 0))
    return {"rate_id": rate_id, "options": options}


def _classify_labels(labels) -> list:
    """shippingLabels[] can be URLs or base64 PDF blobs; hand the UI a typed list."""
    out = []
    for lb in (labels or []):
        s = str(lb or "").strip()
        if not s:
            continue
        low = s.lower()
        if low.startswith("http://") or low.startswith("https://"):
            out.append({"type": "url", "value": s})
        elif low.startswith("data:"):
            out.append({"type": "dataurl", "value": s})
        else:
            # Assume a base64-encoded PDF (the common WO shape for label blobs).
            out.append({"type": "base64pdf", "value": s})
    return out


def _normalize_shipment(data: dict) -> dict:
    svc = data.get("carrierService") or {}
    carrier = svc.get("carrier") or {}
    cur = data.get("currency") or {}
    amount = data.get("shippingAmount")
    return {
        "shipment_id":     data.get("id"),
        "tracking_number": str(data.get("trackingNumber") or ""),
        "amount":          (float(amount) if amount is not None else None),
        "currency":        cur.get("code") or "",
        "carrier_name":    carrier.get("name") or svc.get("name") or "",
        "carrier_code":    carrier.get("code") or "",
        "service_name":    svc.get("name") or "",
        "service_code":    svc.get("code") or "",
        "labels":          _classify_labels(data.get("shippingLabels")),
        "canceled":        bool(data.get("canceled")),
        "invoice":         bool(data.get("invoice")),
        "location_id":     str(data.get("locationId") or ""),
    }


# ---------------------------------------------------------------------------
# Public operations
# ---------------------------------------------------------------------------
async def validate() -> dict:
    """Confirm the key works and return light account context for Settings."""
    data = await _request("GET", "/api/customers/info")
    return data if isinstance(data, dict) else {}


async def carriers(force: bool = False) -> list:
    """Cached list of the account's carriers (reference data; rarely changes)."""
    import time
    now = time.monotonic()
    if not force and _carrier_cache["carriers"] is not None and (now - _carrier_cache["at"]) < 3600:
        return _carrier_cache["carriers"]
    data = await _request("GET", "/api/carriers")
    items = data if isinstance(data, list) else (data.get("hydra:member") or data.get("member") or [])
    out = [{"id": c.get("id"), "name": c.get("name"), "code": c.get("code")} for c in items]
    _carrier_cache.update({"at": now, "carriers": out})
    return out


async def quote(origin: dict, destination: dict, boxes: list,
                currency: str = "GBP", residential: bool = False) -> dict:
    """Free, read-only price check. Returns {rate_id, options[]}."""
    body = {
        "origin":      _addr(origin),
        "destination": _addr(destination),
        "boxes":       [_box(b) for b in (boxes or [])],
        "currency":    (currency or "GBP")[:3].upper(),
        "residental":  bool(residential),   # WO's own field spelling
        "packing":     False,               # we send our own boxes; don't repack
    }
    data = await _request("POST", "/api/rates", body=body)
    return _normalize_rate(data if isinstance(data, dict) else {}, body["currency"])


async def book(rate_id, carrier_id, wo_order_id=None) -> dict:
    """Book (and CHARGE) a shipment for a rate + chosen carrier option.
    Returns a normalized shipment with tracking + labels."""
    body = {"rate": int(rate_id), "carrier": int(carrier_id)}
    if wo_order_id is not None:
        body["order"] = int(wo_order_id)
    data = await _request("POST", "/api/shipments", body=body)
    return _normalize_shipment(data if isinstance(data, dict) else {})


async def track(tracking_number: str) -> dict:
    tn = _urlquote(str(tracking_number), safe="")
    data = await _request("GET", f"/api/shipments/{tn}/get")
    return _normalize_shipment(data if isinstance(data, dict) else {})


async def cancel(tracking_number: str) -> dict:
    tn = _urlquote(str(tracking_number), safe="")
    data = await _request("PATCH", f"/api/shipments/{tn}/cancel")
    return _normalize_shipment(data if isinstance(data, dict) else {})
