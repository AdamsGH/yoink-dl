"""Client for the youtubei-service Node.js sidecar."""
from __future__ import annotations

import logging
import urllib.parse
from pathlib import Path

import httpx

from yoink_dl.services.yttv_oauth import OAuthTokens

logger = logging.getLogger(__name__)

_DEFAULT_URL = "http://yoink-youtubei:9173"


def _svc_url() -> str:
    import os
    return os.environ.get("YOUTUBEI_SERVICE_URL", _DEFAULT_URL)


async def download_via_youtubei(
    url: str,
    tokens: OAuthTokens,
    download_dir: Path,
    quality: str = "best",
    audio_only: bool = False,
    start_sec: int | None = None,
    end_sec: int | None = None,
) -> tuple[list[Path], OAuthTokens, str]:
    """
    Download a YouTube video via youtubei-service.
    Returns (list_of_files, possibly_refreshed_tokens, title).
    """
    payload = {
        "url": url,
        "tokens": {
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "expiry_date": tokens["expires_at"],
        },
        "quality": quality,
        "audio_only": audio_only,
    }
    if start_sec is not None:
        payload["start_sec"] = start_sec
    if end_sec is not None:
        payload["end_sec"] = end_sec

    svc = _svc_url()
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=280, write=30, pool=10)) as client:
        resp = await client.post(f"{svc}/download", json=payload)

    if resp.status_code != 200:
        try:
            detail = resp.json().get("error", resp.text[:200])
        except Exception:
            detail = resp.text[:200]
        raise RuntimeError(f"youtubei-service error: {detail}")

    # Check for refreshed tokens in response header
    updated_tokens = tokens
    raw_updated = resp.headers.get("x-updated-tokens")
    if raw_updated:
        import json
        try:
            new_creds = json.loads(raw_updated)
            updated_tokens = OAuthTokens(
                access_token=new_creds["access_token"],
                refresh_token=new_creds.get("refresh_token", tokens["refresh_token"]),
                expires_at=new_creds.get("expiry_date", tokens["expires_at"]),
            )
        except Exception:
            pass

    # Determine filename from Content-Disposition
    cd = resp.headers.get("content-disposition", "")
    filename = "video.mp4"
    if "filename=" in cd:
        filename = cd.split("filename=")[-1].strip().strip('"')

    title_header = resp.headers.get("x-file-title", "")
    if title_header:
        filename = urllib.parse.unquote(title_header) + Path(filename).suffix

    out_path = download_dir / filename
    out_path.write_bytes(resp.content)

    title = urllib.parse.unquote(title_header) if title_header else out_path.stem
    logger.info("youtubei download done: %s -> %s", url, out_path)
    return [out_path], updated_tokens, title


async def get_info_via_youtubei(url: str, tokens: OAuthTokens) -> dict:
    """Fetch basic video info without downloading."""
    svc = _svc_url()
    params = {
        "url": url,
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "expiry_date": tokens["expires_at"],
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{svc}/info", params=params)
    resp.raise_for_status()
    return resp.json()
