"""yt-dlp wrapper - options builder, info extraction, download."""
from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import yt_dlp

from yoink_dl.config import DownloaderConfig as Settings
from yoink_dl.services.proxy import ProxyConfig
from yoink_dl.storage.repos import UserSettings
from yoink_dl.url.resolver import ResolvedUrl
from yoink_dl.url.clip import ClipSpec
from yoink_dl.utils.errors import DownloadError, LiveStreamError, FileTooLargeError

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ytdlp")


def _domain_from_url(url: str) -> str:
    from urllib.parse import urlparse
    host = urlparse(url).netloc.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def build_format_string(settings: UserSettings) -> str:
    """
    Build yt-dlp format string from user settings.
    quality: best | ask | 720 | 1080 | 4k | 8k | <format-id>
    codec: avc1 | av01 | vp9
    container: mp4 | mkv
    """
    quality = settings.quality
    codec = settings.codec
    container = settings.container

    # Always-ask handled upstream (quality menu), here we get resolved quality
    if quality == "ask":
        quality = "best"

    height_map = {"4k": 2160, "8k": 4320}
    height = height_map.get(quality.lower()) if quality.lower() in height_map else None

    if height is None and quality.rstrip("p").isdigit():
        height = int(quality.rstrip("p"))

    if height is None:
        # best quality
        if codec == "av01":
            fmt = f"bestvideo[vcodec^=av01]+bestaudio/bestvideo+bestaudio/best"
        elif codec == "vp9":
            fmt = "bestvideo[vcodec^=vp9]+bestaudio/bestvideo+bestaudio/best"
        else:
            fmt = "bestvideo[vcodec^=avc1]+bestaudio/bestvideo+bestaudio/best"
    else:
        if codec == "av01":
            fmt = (
                f"bestvideo[height={height}][vcodec^=av01]+bestaudio"
                f"/bestvideo[height<={height}][vcodec^=av01]+bestaudio"
                f"/bestvideo[height<={height}]+bestaudio"
                f"/best[height<={height}]/best"
            )
        elif codec == "vp9":
            fmt = (
                f"bestvideo[height={height}][vcodec^=vp9]+bestaudio"
                f"/bestvideo[height<={height}][vcodec^=vp9]+bestaudio"
                f"/bestvideo[height<={height}]+bestaudio"
                f"/best[height<={height}]/best"
            )
        else:
            fmt = (
                f"bestvideo[height={height}][vcodec^=avc1]+bestaudio"
                f"/bestvideo[height<={height}][vcodec^=avc1]+bestaudio"
                f"/bestvideo[height<={height}]+bestaudio"
                f"/best[height<={height}]/best"
            )

    # Prefer mp4/mkv container
    if container == "mkv":
        fmt += f"/bestvideo+bestaudio"

    return fmt


def build_ytdlp_opts(
    resolved: ResolvedUrl,
    settings: UserSettings,
    download_dir: Path,
    cookie_path: Path | None = None,
    proxy: ProxyConfig | None = None,
    app_settings: Settings | None = None,
    extra_opts: dict[str, Any] | None = None,
    info_only: bool = False,
    clip: "ClipSpec | None" = None,
    use_browser_cookies: bool = False,
) -> dict[str, Any]:
    """Build complete yt-dlp options dict."""

    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "geo_bypass": True,
        "check_certificate": False,
        "live_from_start": True,
        "extractor_args": {
            "generic": {"impersonate": ["chrome"]},
            "youtubetab": {"skip": ["authcheck"]},
        },
        "referer": resolved.url,
        "js_runtimes": {"node": {}},
    }

    if info_only:
        opts.update({
            "skip_download": True,
            "forcejson": True,
            "simulate": True,
            "extract_flat": False,
        })
        if resolved.is_playlist and resolved.playlist_start is not None:
            start = resolved.playlist_start
            end = resolved.playlist_end
            if end is not None and end != start:
                if start < 0 or (end is not None and end < 0):
                    opts["playlist_items"] = f"{start}:{end}"
                elif start > (end or 0):
                    opts["playlist_items"] = f"{start}:{end}:-1"
                else:
                    opts["playlist_items"] = f"{start}:{end}"
            else:
                opts["playlist_items"] = str(start)
    else:
        # Download opts
        opts["outtmpl"] = str(download_dir / "%(title).80s.%(ext)s")
        opts["format"] = build_format_string(settings)
        opts["merge_output_format"] = settings.container

        # Apply match_filter for live stream / duration check
        if resolved.apply_match_filter and app_settings:
            max_dur = getattr(app_settings, "max_video_duration", 0)
            if max_dur > 0:
                opts["match_filter"] = yt_dlp.utils.match_filter_func(
                    f"duration <= {max_dur}"
                )

    # Playlist items for download too
    if resolved.is_playlist and resolved.playlist_start is not None and not info_only:
        start = resolved.playlist_start
        end = resolved.playlist_end
        if end is not None and end != start:
            opts["playlist_items"] = f"{start}:{end}"
        else:
            opts["playlist_items"] = str(start)

    # Cookies  - DB file takes priority; fall back to live browser profile
    if cookie_path and cookie_path.exists() and resolved.use_cookies:
        opts["cookiefile"] = str(cookie_path)
    elif use_browser_cookies and resolved.use_cookies and app_settings and app_settings.browser_profile_path:
        profile = app_settings.browser_profile_path
        domains = app_settings.browser_cookie_domains
        domain = _domain_from_url(resolved.url)
        if not domains or any(domain == d or domain.endswith("." + d) for d in domains):
            opts["cookiesfrombrowser"] = ("chromium", profile, None, None)

    # Proxy
    if proxy:
        opts["proxy"] = proxy.as_ytdlp()

    # PO Token (YouTube)
    if app_settings and app_settings.youtube_pot_enabled:
        _add_pot(opts, resolved.url, app_settings)

    # User custom args (from /args command)
    _apply_user_args(opts, settings.args_json)

    # Clip / time range
    clips: list[ClipSpec] = []
    if clip:
        clips = [clip]
    elif extra_opts and extra_opts.get("_clips"):
        clips = extra_opts.pop("_clips")

    if clips and not info_only:
        opts["download_ranges"] = yt_dlp.utils.download_range_func(
            [], [[c.start_sec, c.end_sec] for c in clips]
        )
        opts["force_keyframes_at_cuts"] = True
        opts["external_downloader"] = "native"
        # android client is incompatible with native downloader + download_ranges;
        # restrict to web only for clip downloads
        ea = opts.setdefault("extractor_args", {})
        yt_clients = ea.get("youtube", {}).get("player_client")
        if yt_clients and "android" in yt_clients:
            ea["youtube"]["player_client"] = ["web"]

    # Extra opts (caller overrides)
    if extra_opts:
        opts.update(extra_opts)

    return opts


def _add_pot(opts: dict[str, Any], url: str, settings: Settings) -> None:
    """Add PO token provider extractor args for YouTube via yt-dlp-get-pot plugin.

    player_client=web,android: web handles signature/n-challenge solving;
    android provides a fallback for videos that return "not available" on web-only
    (typically age-restricted or regionally limited content without cookies).
    """
    if not any(d in url for d in ("youtube.com", "youtu.be")):
        return
    ea = opts.setdefault("extractor_args", {})
    ea.setdefault("youtubepot-bgutilhttp", {})["base_url"] = [settings.youtube_pot_url]
    ea.setdefault("youtube", {})["player_client"] = ["web", "android"]


def _apply_user_args(opts: dict[str, Any], args: dict[str, Any]) -> None:
    """Map user's /args settings to yt-dlp options."""
    mapping = {
        "geo_bypass": "geo_bypass",
        "write_automatic_sub": "writeautomaticsub",
        "extract_flat": "extract_flat",
        "retries": "retries",
        "fragment_retries": "fragment_retries",
        "concurrent_fragments": "concurrent_fragment_downloads",
        "audio_format": "postprocessors",  # handled separately
        "http_headers": "http_headers",
    }
    for user_key, ytdlp_key in mapping.items():
        if user_key in args and user_key != "audio_format":
            opts[ytdlp_key] = args[user_key]

    if args.get("referer"):
        opts["referer"] = args["referer"]
    if args.get("user_agent"):
        opts["http_headers"] = {
            **opts.get("http_headers", {}),
            "User-Agent": args["user_agent"],
        }


async def extract_info(
    opts: dict[str, Any],
    url: str,
) -> dict[str, Any]:
    """Run yt-dlp extract_info in a thread, return info dict."""
    loop = asyncio.get_running_loop()

    def _run() -> dict[str, Any]:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if info is None:
            raise DownloadError("yt-dlp returned no info")
        # Flatten playlist: use first entry
        if isinstance(info, dict) and "entries" in info:
            entries = list(info.get("entries") or [])
            if entries:
                first = entries[0]
                first["_playlist_entries"] = entries
                first["_playlist_title"] = info.get("title", "")
                return first
        return info  # type: ignore[return-value]

    try:
        return await loop.run_in_executor(_executor, _run)
    except yt_dlp.utils.DownloadError as e:
        err = str(e)
        if "live" in err.lower() or "is live" in err.lower():
            raise LiveStreamError()
        raise DownloadError(error=err) from e


async def download(
    opts: dict[str, Any],
    url: str,
) -> list[Path]:
    """Run yt-dlp download in a thread, return list of downloaded file paths."""
    download_dir = Path(opts.get("outtmpl", "./dl/%(title)s.%(ext)s")).parent
    before = set(download_dir.glob("*")) if download_dir.exists() else set()

    loop = asyncio.get_running_loop()

    def _run() -> None:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ret = ydl.download([url])
        if ret != 0:
            raise DownloadError(error=f"yt-dlp exited with code {ret}")

    try:
        await loop.run_in_executor(_executor, _run)
    except yt_dlp.utils.DownloadError as e:
        raise DownloadError(error=str(e)) from e

    after = set(download_dir.glob("*"))
    new_files = sorted(after - before, key=lambda p: p.stat().st_mtime)
    return [f for f in new_files if f.is_file() and not f.name.endswith((".part", ".ytdl"))]
