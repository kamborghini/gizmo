"""Encryption at rest for the third-party refresh tokens.

Four files on the data volume hold long-lived credentials - two Gmail mailboxes,
Google's data API, and Xero. They are 0600, which stops another user on the box
reading them, and does nothing at all about a volume snapshot, a backup that
escapes, or anyone who gets a shell as the app.

What this is NOT: it does not protect a running process. The key is in the
app's environment, so anything that can read the app's memory can read the
tokens. It shrinks the blast radius of a file or snapshot leaking, which is the
realistic failure, and that is all it claims.

Two rules make it safe to switch on mid-life:

  * With no TOKEN_ENCRYPTION_KEY set, every call is a no-op. Existing
    deployments keep working unchanged, and turning the key on later does not
    require a migration step.
  * unseal() accepts a bare token. Files written before the key existed open
    normally, and are re-sealed the next time they are written.

A tampered or wrongly-keyed envelope RAISES. Returning something would send a
corrupted token upstream, which reads as a revoked connection - a confusing
failure a long way from its cause.
"""
import base64
import functools
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

PREFIX = "v1:"
# Fixed, and that is deliberate: the salt has to be identical across restarts or
# the key changes and every stored token becomes unreadable. It is not secret -
# scrypt's cost is what defends the key, and the key is a long random string
# from the environment rather than a password anyone chose.
_SALT = b"gizmo-token-vault-v1"


class VaultError(RuntimeError):
    """A sealed value could not be opened: wrong key, or it was altered."""


@functools.lru_cache(maxsize=1)
def _key():
    """The 32-byte AES key, or None when the app is running unencrypted.

    Cached because scrypt is deliberately slow and this runs on every token
    read. Tests clear it with _key.cache_clear() after changing the env."""
    raw = (os.environ.get("TOKEN_ENCRYPTION_KEY") or "").strip()
    if not raw:
        return None
    return Scrypt(salt=_SALT, length=32, n=2 ** 14, r=8, p=1).derive(raw.encode("utf-8"))


def enabled() -> bool:
    return _key() is not None


def seal(value: str) -> str:
    """Plaintext in, storable string out. Unchanged when no key is configured."""
    if value is None:
        return value
    k = _key()
    if not k:
        return value
    nonce = os.urandom(12)
    ct = AESGCM(k).encrypt(nonce, str(value).encode("utf-8"), None)
    return PREFIX + base64.b64encode(nonce).decode("ascii") + ":" \
        + base64.b64encode(ct).decode("ascii")


def unseal(value: str) -> str:
    """Storable string in, plaintext out.

    A value with no envelope is returned as-is: that is a token written before
    the key was introduced, and refusing it would take a working connection
    down for no security gain."""
    if not isinstance(value, str) or not value.startswith(PREFIX):
        return value
    k = _key()
    if not k:
        # Sealed data and no key. Nothing sensible can be returned, and saying
        # so beats handing back an envelope that looks like a token.
        raise VaultError("This token is encrypted but TOKEN_ENCRYPTION_KEY is not set.")
    try:
        _, nonce_b64, ct_b64 = value.split(":", 2)
        nonce = base64.b64decode(nonce_b64)
        ct = base64.b64decode(ct_b64)
        return AESGCM(k).decrypt(nonce, ct, None).decode("utf-8")
    except (InvalidTag, ValueError, TypeError) as e:
        raise VaultError("This token could not be decrypted: the key has changed, "
                         "or the file was altered.") from e
