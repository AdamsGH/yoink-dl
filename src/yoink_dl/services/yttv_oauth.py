"""YouTube TV OAuth2 device flow - short-lived in-memory session store."""
from __future__ import annotations

import json
import secrets
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import TypedDict

import httpx

_CLIENT_ID = "861556708454-d6dlm3lh05idd8npek18k6be8ba3oc68.apps.googleusercontent.com"
_CLIENT_SECRET = "SboVhoG9s0rNafixCSGGKXAT"
_SCOPES = "http://gdata.youtube.com https://www.googleapis.com/auth/youtube"

DEVICE_CODE_URL = "https://www.youtube.com/o/oauth2/device/code"
TOKEN_URL = "https://www.youtube.com/o/oauth2/token"

# How long the pending session lives (device codes expire in ~30 min, we use less)
SESSION_TTL = 1800  # seconds

OAUTH_CONTENT_PREFIX = "__oauth2__"


class OAuthTokens(TypedDict):
    access_token: str
    refresh_token: str
    expires_at: str  # ISO


class PendingSession(TypedDict):
    user_id: int
    device_code: str
    interval: int
    expires_at: str  # ISO


_store: dict[str, PendingSession] = {}
_lock = threading.Lock()


def _evict() -> None:
    now = datetime.now(timezone.utc)
    expired = [k for k, v in _store.items() if datetime.fromisoformat(v["expires_at"]) < now]
    for k in expired:
        del _store[k]


async def start_device_flow(user_id: int) -> dict:
    """
    Kick off Google TV device flow. Returns session_id + user-facing fields
    (verification_url, user_code, expires_in, interval).
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            DEVICE_CODE_URL,
            json={
                "client_id": _CLIENT_ID,
                "scope": _SCOPES,
                "device_id": uuid.uuid4().hex,
                "device_model": "ytlr::",
            },
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

    session_id = secrets.token_urlsafe(24)
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=SESSION_TTL)).isoformat()

    with _lock:
        _evict()
        _store[session_id] = {
            "user_id": user_id,
            "device_code": data["device_code"],
            "interval": data.get("interval", 5),
            "expires_at": expires_at,
        }

    return {
        "session_id": session_id,
        "verification_url": data["verification_url"],
        "user_code": data["user_code"],
        "expires_in": data["expires_in"],
        "interval": data.get("interval", 5),
    }


async def poll_device_flow(session_id: str) -> dict:
    """
    Poll Google for the access token.
    Returns one of:
      {"status": "pending"}
      {"status": "expired"}
      {"status": "error", "detail": str}
      {"status": "ok", "user_id": int, "tokens": OAuthTokens}
    """
    with _lock:
        session = _store.get(session_id)

    if session is None:
        return {"status": "expired"}

    if datetime.fromisoformat(session["expires_at"]) < datetime.now(timezone.utc):
        with _lock:
            _store.pop(session_id, None)
        return {"status": "expired"}

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            TOKEN_URL,
            json={
                "client_id": _CLIENT_ID,
                "client_secret": _CLIENT_SECRET,
                "code": session["device_code"],
                "grant_type": "http://oauth.net/grant_type/device/1.0",
            },
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        data = resp.json()

    error = data.get("error")
    if error in ("authorization_pending", "slow_down"):
        return {"status": "pending"}

    if error == "expired_token":
        with _lock:
            _store.pop(session_id, None)
        return {"status": "expired"}

    if error:
        return {"status": "error", "detail": error}

    tokens: OAuthTokens = {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_at": (
            datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 3600))
        ).isoformat(),
    }
    user_id = session["user_id"]

    with _lock:
        _store.pop(session_id, None)

    return {"status": "ok", "user_id": user_id, "tokens": tokens}


async def refresh_tokens(tokens: OAuthTokens) -> OAuthTokens:
    """Exchange a refresh_token for a fresh access_token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            TOKEN_URL,
            json={
                "client_id": _CLIENT_ID,
                "client_secret": _CLIENT_SECRET,
                "refresh_token": tokens["refresh_token"],
                "grant_type": "refresh_token",
            },
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", tokens["refresh_token"]),
        "expires_at": (
            datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 3600))
        ).isoformat(),
    }


def encode_content(tokens: OAuthTokens) -> str:
    """Serialize tokens to the string stored in Cookie.content."""
    return OAUTH_CONTENT_PREFIX + json.dumps(tokens)


def decode_content(content: str) -> OAuthTokens | None:
    """Deserialize tokens from Cookie.content. Returns None if not OAuth content."""
    if not content.startswith(OAUTH_CONTENT_PREFIX):
        return None
    try:
        return json.loads(content[len(OAUTH_CONTENT_PREFIX):])
    except Exception:
        return None


def is_oauth_content(content: str) -> bool:
    return content.startswith(OAUTH_CONTENT_PREFIX)
