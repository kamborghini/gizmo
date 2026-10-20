"""The stores' shared pieces, moved out of copilot.py as each area needs
them at import time. The rest of the store (the one writer, the loaders, the
poison guard) is still in copilot.py."""


class StoreUnwritable(RuntimeError):
    """A store the poison guard has paused. The one writer raises this; a
    caller that would rather stay silent checks _store_writable first and
    says why, which is what every writer already did."""
