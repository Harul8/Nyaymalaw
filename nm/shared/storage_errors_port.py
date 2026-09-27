"""Expected sealed-object failures, reachable without importing a concrete adapter."""


class StoredObjectUnreadable(RuntimeError):
    """Stored ciphertext or its key cannot be read; never absence or plaintext fallback."""


class StoredObjectScopeRefused(RuntimeError):
    """An object belongs to a different key scope; distinct from ordinary corruption."""
