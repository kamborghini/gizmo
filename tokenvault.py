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
import json
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


def is_sealed(value) -> bool:
    """Whether this stored value is an envelope rather than a bare token."""
    return isinstance(value, str) and value.startswith(PREFIX)


def _write_private(path: str, data) -> None:
    """0600 from the moment it exists, and replaced atomically. A token file
    that is briefly world-readable, or briefly half-written, is the thing this
    whole module exists to prevent."""
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def reseal_file(path: str, fields) -> int:
    """Seal any bare values at `fields` in a JSON file. Returns how many it changed.

    Turning the key on only affects what is written NEXT: a token already on the
    volume stays in plaintext until something happens to rewrite it, which for a
    rarely-refreshed connection can be months. Setting the key would then feel
    like encryption while the file on disk was unchanged, which is worse than
    knowing it is unencrypted.

    Safe to run on every boot: a value already sealed is left exactly as it is,
    and a file that is missing, unreadable or not an object is skipped rather
    than replaced.
    """
    if not enabled():
        return 0
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return 0
    if not isinstance(data, dict):
        return 0
    changed = 0
    for f in fields:
        v = data.get(f)
        if isinstance(v, str) and v and not is_sealed(v):
            data[f] = seal(v)
            changed += 1
    if changed:
        _write_private(path, data)
    return changed


def reseal_users(path: str, fields) -> int:
    """The same, for secrets held per user inside one file (the MFA secrets).

    A user record whose secret cannot be read is left alone rather than
    dropped: locking someone out of their own account is a worse outcome than
    one secret staying as it was.
    """
    if not enabled():
        return 0
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return 0
    users = data.get("users") if isinstance(data, dict) else None
    if not isinstance(users, dict):
        return 0
    changed = 0
    for rec in users.values():
        if not isinstance(rec, dict):
            continue
        for f in fields:
            v = rec.get(f)
            if isinstance(v, str) and v and not is_sealed(v):
                rec[f] = seal(v)
                changed += 1
    if changed:
        _write_private(path, data)
    return changed
