"""Music download pipeline for yoink-music plugin.

Downloads a track from YouTube/YouTube Music as MP3, embeds ID3 tags
(title, artist, album art), and returns the path to the file.

Called by yoink-music via optional import - yoink-dl does not depend on
yoink-music, the dependency is one-way (music → dl).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import yt_dlp

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="music_dl")

MAX_FILE_SIZE = 49 * 1024 * 1024  # 49 MB - Telegram bot limit


class MusicDownloadError(Exception):
    pass


class TrackTooLargeError(MusicDownloadError):
    pass


@dataclass
class MusicDownloadResult:
    path: Path
    duration: float | None


def make_music_cache_key(artist: str, title: str) -> str:
    """Stable cache key for a track independent of source platform."""
    normalized = f"{artist.lower().strip()}:{title.lower().strip()}"
    return "music:" + hashlib.sha256(normalized.encode()).hexdigest()[:48]


async def download_track(
    youtube_url: str,
    *,
    proxy: str | None = None,
) -> MusicDownloadResult:
    """Download audio from a YouTube/YTMusic URL as MP3.

    Returns MusicDownloadResult with the path to the MP3 file.
    The caller is responsible for cleanup.
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="yoink_music_"))
    opts: dict = {
        "format": "bestaudio/best",
        "outtmpl": str(tmpdir / "%(id)s.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "quiet": True,
        "no_warnings": True,
        "geo_bypass": True,
    }
    if proxy:
        opts["proxy"] = proxy

    loop = asyncio.get_running_loop()

    def _run() -> dict:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(youtube_url, download=True)
        return info or {}

    try:
        info = await loop.run_in_executor(_executor, _run)
    except yt_dlp.utils.DownloadError as exc:
        raise MusicDownloadError(str(exc)) from exc

    mp3_files = list(tmpdir.glob("*.mp3"))
    if not mp3_files:
        raise MusicDownloadError("yt-dlp produced no MP3 file")

    path = mp3_files[0]
    if path.stat().st_size > MAX_FILE_SIZE:
        path.unlink()
        tmpdir.rmdir()
        raise TrackTooLargeError(f"Track exceeds 49 MB limit")

    duration = float(info.get("duration") or 0) or None
    return MusicDownloadResult(path=path, duration=duration)


def embed_tags(
    path: Path,
    *,
    title: str,
    artist: str,
    thumbnail_url: str | None = None,
) -> None:
    """Embed ID3 tags into an MP3 file using mutagen.

    Silently skips if mutagen is not installed or tagging fails.
    """
    try:
        from mutagen.id3 import ID3, TIT2, TPE1, APIC, ID3NoHeaderError
        import httpx

        try:
            tags = ID3(str(path))
        except ID3NoHeaderError:
            tags = ID3()

        tags["TIT2"] = TIT2(encoding=3, text=title)
        tags["TPE1"] = TPE1(encoding=3, text=artist)

        if thumbnail_url:
            try:
                resp = httpx.get(thumbnail_url, timeout=5, follow_redirects=True)
                if resp.status_code == 200:
                    tags["APIC"] = APIC(
                        encoding=3,
                        mime="image/jpeg",
                        type=3,  # front cover
                        desc="Cover",
                        data=resp.content,
                    )
            except Exception as exc:
                logger.debug("Failed to fetch thumbnail for ID3: %s", exc)

        tags.save(str(path))
        logger.debug("ID3 tags embedded: %r by %r", title, artist)
    except ImportError:
        logger.debug("mutagen not installed, skipping ID3 tags")
    except Exception as exc:
        logger.debug("ID3 tagging failed: %s", exc)
