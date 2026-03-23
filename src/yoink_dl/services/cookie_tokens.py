"""Short-lived single-use tokens for browser extension cookie submission."""
from __future__ import annotations

import secrets
import threading
from datetime import datetime, timedelta, timezone

TTL = 600  # seconds

_store: dict[str, dict] = {}
_lock = threading.Lock()


def generate(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=TTL)
    with _lock:
        _evict()
        _store[token] = {"user_id": user_id, "expires_at": expires_at}
    return token


def consume(token: str) -> int | None:
    """Validate and consume a token. Returns user_id or None if invalid/expired."""
    with _lock:
        entry = _store.pop(token, None)
    if not entry:
        return None
    if entry["expires_at"] < datetime.now(timezone.utc):
        return None
    return entry["user_id"]


def _evict() -> None:
    now = datetime.now(timezone.utc)
    expired = [t for t, v in _store.items() if v["expires_at"] < now]
    for t in expired:
        del _store[t]
