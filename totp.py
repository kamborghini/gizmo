"""Time-based one-time codes (RFC 6238) and recovery codes.

Stdlib only. TOTP is HMAC-SHA1 over a 30-second counter truncated to six
digits, and adding a dependency for thirty lines of hmac would be a worse
trade than writing them - every extra package is another thing that can ship a
supply-chain problem into an app that books real money.

SHA-1 is correct here and not a lapse: RFC 6238's default, and what every
authenticator app implements. It is a MAC over a counter, not a collision
resistant hash, and the security comes from the shared secret.

Three things this does that a naive implementation skips, each of them the
difference between a second factor and the appearance of one:

  * Comparison is constant-time. A byte-by-byte compare leaks the code.
  * A code is refused once its counter has been used. Otherwise a code read
    over someone's shoulder, or out of a proxy log, stays good for its whole
    window.
  * Recovery codes are stored hashed, so the file cannot hand anyone the way
    back in, and each one is spent on use.
"""
import base64
import hashlib
import hmac
import os
import secrets
import struct
import time

STEP = 30          # seconds per code, the RFC default every app assumes
DIGITS = 6
SKEW = 1           # steps either side; phones drift, but two is a free minute


def new_secret() -> str:
    """A fresh base32 secret, the format authenticator apps expect."""
    return base64.b32encode(os.urandom(20)).decode("ascii").rstrip("=")


def provisioning_uri(secret: str, account: str, issuer: str = "gizmo") -> str:
    """The otpauth:// URI behind the QR code."""
    from urllib.parse import quote
    label = quote(f"{issuer}:{account}")
    return (f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}"
            f"&algorithm=SHA1&digits={DIGITS}&period={STEP}")


def _counter_code(secret: str, counter: int) -> str:
    pad = "=" * (-len(secret) % 8)
    key = base64.b32decode(secret.upper() + pad, casefold=True)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    val = struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF
    return str(val % (10 ** DIGITS)).zfill(DIGITS)


def code(secret: str, at: float = None) -> str:
    return _counter_code(secret, int((at if at is not None else time.time()) // STEP))


def verify(secret: str, given: str, at: float = None, last_counter=None):
    """True when the code is good. False otherwise - including for a counter
    that has already been spent.

    last_counter is the highest counter this account has already used. Passing
    it is what stops a replay inside the same 30-second window."""
    given = str(given or "").strip().replace(" ", "")
    if not given.isdigit() or len(given) != DIGITS or not secret:
        return False
    now = int((at if at is not None else time.time()) // STEP)
    for delta in range(-SKEW, SKEW + 1):
        c = now + delta
        if last_counter is not None and c <= int(last_counter):
            continue        # already spent: a code is good once
        if hmac.compare_digest(_counter_code(secret, c), given):
            return True
    return False


def used_counter(at: float = None) -> int:
    return int((at if at is not None else time.time()) // STEP)


# --- recovery codes ---------------------------------------------------------

def recovery_codes(n: int = 8) -> list:
    """Human-typeable, and long enough that guessing is not a strategy."""
    alpha = "abcdefghjkmnpqrstuvwxyz23456789"     # no l/1/o/0 to read back wrong
    out = []
    for _ in range(n):
        raw = "".join(secrets.choice(alpha) for _ in range(10))
        out.append(raw[:5] + "-" + raw[5:])
    return out


def hash_recovery(code_: str) -> str:
    """scrypt, salted per code. These are as good as a password."""
    salt = os.urandom(16)
    dk = hashlib.scrypt(str(code_).strip().lower().replace("-", "").encode(),
                        salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return base64.b64encode(salt).decode() + ":" + base64.b64encode(dk).decode()


def check_recovery(given: str, hashes: list) -> int:
    """Index of the code that matched, or -1. The caller removes it: a recovery
    code is spent on use."""
    given = str(given or "").strip().lower().replace("-", "")
    if not given:
        return -1
    for i, h in enumerate(hashes or []):
        try:
            salt_b64, dk_b64 = str(h).split(":", 1)
            dk = hashlib.scrypt(given.encode(), salt=base64.b64decode(salt_b64),
                                n=2 ** 14, r=8, p=1, dklen=32)
            if hmac.compare_digest(dk, base64.b64decode(dk_b64)):
                return i
        except Exception:
            continue
    return -1
