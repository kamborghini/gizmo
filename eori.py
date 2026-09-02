"""EORI number checking against the European Commission's validation service.

An EORI number is what customs matches a shipment's paperwork against. A wrong
one on a commercial invoice does not bounce back to us: the parcel stops at the
border and the customer is the one who finds out. Checking one before the label
prints is the cheap half of that problem.

WHAT THE SERVICE IS
    A SOAP 1.1 endpoint published by DG TAXUD. Its shape here is not guessed:
    the WSDL was fetched on 2026-09-02 and one live call confirmed the request
    is accepted and what the answer looks like.

        endpoint    https://ec.europa.eu/taxation_customs/dds2/eos/validation
                    /services/validation
        namespace   http://eori.ws.eos.dds.s/
        operation   validateEORI (document/literal, empty SOAPAction)
        request     <validateEORI xmlns="..."><eori>NUM</eori></validateEORI>
        answer      validateEORIResponse > return > result >
                    eori, status, statusDescr, errorReason?, name?, address?,
                    street?, postalCode?, city?, country?

    An earlier guess at the namespace (http://eurodyn.com/eos/validateEORI)
    came back as a SOAP fault naming the operation as invalid, which is exactly
    what a wrong namespace looks like from the outside. Do not "tidy" the
    namespace string above; it is the one the service answers to.

WHY IT IS TREATED AS UNRELIABLE
    The endpoint sits behind a CloudFront edge that, in practice, refuses most
    requests: during this module's design it timed out three times in five, and
    once the WSDL had been read it began answering POSTs with a 403 HTML page
    ("This distribution is not configured to allow the HTTP request method").
    So a non-answer is the NORMAL case, not the exceptional one.

    Every non-answer becomes "unknown", never "invalid". The distinction is the
    whole point of this module: "invalid" tells the merchant to go back to the
    customer and challenge their paperwork, and saying that because Brussels
    was down for a minute would be a wrong instruction about a real shipment.
    "unknown" is also never cached, because caching the absence of an answer
    would turn one bad minute into a day of instant non-answers.

Stdlib plus httpx, nothing else. The network leg is injectable so the tests
never touch the wire.
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

ENDPOINT = ("https://ec.europa.eu/taxation_customs/dds2/eos/validation"
            "/services/validation")
NAMESPACE = "http://eori.ws.eos.dds.s/"
TIMEOUT = 15.0

# The cache lives on the data volume beside the other stores. This module is
# its only writer.
CACHE_PATH = os.environ.get("EORI_CACHE_PATH", "/data/eori_cache.json")
CACHE_HOURS = 24

# 2 letters, then 1..15 alphanumerics. The real numbers are country-specific
# and no two member states agree on a length, so the shape is all that can be
# checked locally; the database settles the rest.
_SHAPE = re.compile(r"^[A-Z]{2}[A-Z0-9]{1,15}$")

# A browser User-Agent. The edge in front of the service is markedly less
# willing to talk to something that announces itself as a script.
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

_ENVELOPE = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
    "<soapenv:Body>"
    '<validateEORI xmlns="' + NAMESPACE + '">'
    "<eori>{number}</eori>"
    "</validateEORI>"
    "</soapenv:Body>"
    "</soapenv:Envelope>"
)


def normalise(number) -> str:
    """Uppercase, with the punctuation people type stripped out.

    Merchants copy these off letterheads and invoices, where they are printed
    with spaces or dots for legibility. The service holds them unpunctuated.
    """
    return re.sub(r"[\s.\-]", "", str(number or "")).upper()


def classify(number) -> str:
    """"gb", "bad", or "eu" — meaning "ask the EU database".

    GB is singled out because it is the one prefix where asking would produce a
    CONFIDENTLY WRONG answer: the EU database stopped holding GB numbers after
    the withdrawal, so a perfectly good GB EORI comes back as invalid. HMRC's
    own service is the authority there.

    Everything else well-formed returns "eu", including third countries such as
    CH that the database does not hold. That is deliberate: the service answers
    "invalid" for a number it has no record of, which is the honest answer, and
    gating on a hard-coded member-state list would instead mean a future
    accession — or a prefix this list simply got wrong — is silently reported
    as malformed rather than checked.
    """
    n = normalise(number)
    if not _SHAPE.match(n):
        return "bad"
    return "gb" if n.startswith("GB") else "eu"


def _text(node) -> str:
    return (node.text or "").strip() if node is not None else ""


def _find(parent, name):
    """First descendant with this local name, whatever namespace it carries.

    The response mixes qualified and unqualified elements (validateEORIResponse
    is in the service's namespace; `return` and `result` beneath it are not),
    which is what the WSDL specifies. Matching on the local name keeps the
    reader honest about that instead of hard-coding two prefixes.
    """
    for el in parent.iter():
        if el.tag.rsplit("}", 1)[-1] == name:
            return el
    return None


def _blank(status: str = "unknown", reason: str = "") -> dict:
    return {"status": status, "name": "", "address": "", "reason": reason}


def _parse_detail(xml_text: str):
    """(result, kind). `kind` says HOW the body was understood, which lets the
    caller decide whether an HTTP status code has anything better to add."""
    import xml.etree.ElementTree as ET

    raw = (xml_text or "").strip()
    if not raw:
        return _blank(reason="The EU EORI database sent an empty answer."), "empty"
    # The edge returns an HTML error page under its own 403. That is a proxy
    # talking, not the service, and it says nothing about the number.
    head = raw[:200].lstrip().lower()
    if head.startswith("<!doctype html") or head.startswith("<html"):
        return _blank(reason="The EU EORI database returned a web page instead of "
                             "an answer."), "html"
    try:
        root = ET.fromstring(raw)
    except Exception:
        return _blank(reason="The EU EORI database sent something that could not be "
                             "read as an answer."), "unreadable"

    # A SOAP fault is the service REFUSING the request - a bad operation name,
    # a throttle, a message it would not accept. Never a verdict on a number.
    fault = _find(root, "Fault")
    if fault is not None:
        detail = _text(_find(fault, "faultstring"))
        # The faultstring is service-internal wording, full of namespaces and
        # full stops; it goes to the log, where it helps, rather than into a
        # sentence the merchant reads.
        logger.warning("EORI: the service refused the request: %s", detail or "(no detail)")
        return _blank(reason="The EU EORI database refused the request."), "fault"

    result = _find(root, "result")
    if result is None:
        # Well-formed, from the right service, and carrying no verdict. The
        # request-level errorDescription is the usual cause.
        note = _text(_find(root, "errorDescription"))
        if note:
            logger.warning("EORI: the service returned no result: %s", note)
        return _blank(reason="The EU EORI database gave no verdict on that "
                             "number."), "noresult"

    code = _text(_find(result, "status"))
    if code == "0":
        parts = [_text(_find(result, k)) for k in ("street", "postalCode", "city", "country")]
        line = ", ".join(p for p in parts if p)
        # Some records carry a single pre-composed address instead of the parts.
        if not line:
            line = _text(_find(result, "address"))
        # A valid number whose trader never consented to publication comes back
        # with every detail withheld. Still valid; just nothing to show.
        return {"status": "valid", "name": _text(_find(result, "name")),
                "address": line, "reason": ""}, "valid"
    if code == "1":
        return {"status": "invalid", "name": "", "address": "", "reason": ""}, "invalid"

    # A status the service has started using and this code has never seen. Not
    # a licence to guess which way it leans.
    logger.warning("EORI: unrecognised status %r (%s)", code,
                   _text(_find(result, "statusDescr")))
    return _blank(reason="The EU EORI database gave an answer this app does not "
                         "recognise."), "noresult"


def parse(xml_text: str) -> dict:
    """{"status", "name", "address", "reason"} from the service's raw XML.

    Separated from the network leg so every answer the service can give - and
    every non-answer the proxy in front of it can give - is a fixture.
    """
    return _parse_detail(xml_text)[0]


# --------------------------------------------------------------------------
# Cache. Definitive answers only, for a day.
# --------------------------------------------------------------------------
_cache_mem = None


def _cache_load() -> dict:
    """{number: {"result": {...}, "at": iso}}."""
    global _cache_mem
    if _cache_mem is None:
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            _cache_mem = d if isinstance(d, dict) else {}
        except FileNotFoundError:
            _cache_mem = {}
        except Exception:
            # A corrupt cache is not worth a failed check. Start empty and
            # leave the file alone for someone to look at.
            logger.exception("EORI: cache unreadable at %s; continuing without it",
                             CACHE_PATH)
            _cache_mem = {}
    return _cache_mem


def _cache_write(d: dict) -> None:
    global _cache_mem
    os.makedirs(os.path.dirname(CACHE_PATH) or ".", exist_ok=True)
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(d, allow_nan=False))
    os.replace(tmp, CACHE_PATH)
    _cache_mem = d


def _cache_get(number: str):
    """The stored answer if it is still fresh, else None."""
    row = _cache_load().get(number)
    if not isinstance(row, dict) or not isinstance(row.get("result"), dict):
        return None
    try:
        at = datetime.fromisoformat(row.get("at") or "")
    except ValueError:
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - at > timedelta(hours=CACHE_HOURS):
        return None
    return row


def _cache_put(number: str, result: dict, at: str) -> None:
    """Best effort. The answer in hand is real whether or not it is kept, so a
    cache that will not write is logged and stepped over rather than raised:
    failing the check would throw away a good answer to protect a speed-up."""
    try:
        d = _cache_load()
        d[number] = {"result": {k: result[k] for k in ("status", "name", "address")},
                     "at": at}
        if len(d) > 5000:
            # Bounded, oldest first. A merchant checks tens of numbers, not
            # thousands; this only ever trips on something pathological.
            for k in sorted(d, key=lambda k: d[k].get("at") or "")[:len(d) - 5000]:
                d.pop(k, None)
        _cache_write(d)
    except Exception:
        logger.exception("EORI: could not cache the answer for %s", number)


# --------------------------------------------------------------------------
# The check itself
# --------------------------------------------------------------------------
async def _default_transport(xml_body: str):
    """POST the envelope. Returns (status_code, text)."""
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as c:
        r = await c.post(ENDPOINT, content=xml_body.encode("utf-8"),
                         headers={"Content-Type": "text/xml; charset=utf-8",
                                  "SOAPAction": '""', "User-Agent": _UA})
    return r.status_code, r.text


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _result(number: str, base: dict, at: str, cached: bool) -> dict:
    return {"number": number, "status": base["status"], "name": base.get("name") or "",
            "address": base.get("address") or "", "checked_at": at,
            "cached": cached, "reason": base.get("reason") or ""}


async def check(number, transport=None) -> dict:
    """Check one number. Never raises for a service problem; see the module docstring.

    `transport` is an async callable(xml_body: str) -> (status_code, text), so
    the tests exercise every answer the service can give without a network.
    """
    n = normalise(number)
    kind = classify(n)
    if kind == "bad":
        raise ValueError("not an EORI-shaped number")
    if kind == "gb":
        # No network call at all. The EU database does not hold GB numbers, so
        # asking would return "invalid" for a number that is perfectly good.
        return _result(n, _blank("not_covered",
                                 "GB numbers are checked by HMRC, not the EU database."),
                       _now(), False)

    hit = _cache_get(n)
    if hit:
        return _result(n, hit["result"], hit["at"], True)

    send = transport or _default_transport
    try:
        code, text = await send(_ENVELOPE.format(number=n))
    except (httpx.TimeoutException, TimeoutError):
        return _result(n, _blank(reason="The EU EORI database did not answer in time."),
                       _now(), False)
    except Exception:
        logger.exception("EORI: the request to the EU service failed")
        return _result(n, _blank(reason="The EU EORI database could not be reached."),
                       _now(), False)

    base, how = _parse_detail(text)
    # An HTTP status only gets to speak when the body itself said nothing
    # useful. A SOAP fault legitimately arrives as HTTP 500, and "the service
    # refused the request" is the better sentence than "HTTP 500".
    if base["status"] == "unknown" and code != 200 and how in ("empty", "unreadable", "noresult"):
        base["reason"] = ("The EU EORI database answered with an error, HTTP %d."
                          % code)

    at = _now()
    if base["status"] in ("valid", "invalid"):
        _cache_put(n, base, at)
    return _result(n, base, at, False)
