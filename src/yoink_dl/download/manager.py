"""Download pipeline orchestrator."""
from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Callable, Coroutine
from typing import Any

from telegram import Message

from yoink_dl.config import DownloaderConfig as Settings
from yoink_dl.services.proxy import ProxyConfig, ProxyManager
from yoink_dl.services.ipv6_pool import IPv6Pool, IPv6Binding
from yoink_dl.storage.repos import UserSettings
from yoink_dl.url.resolver import ResolvedUrl, Engine
from yoink_dl.url.clip import ClipSpec
from yoink_dl.utils.errors import DownloadError, FileTooLargeError
from yoink_dl.utils.formatting import humanbytes
from . import ytdlp as ytdlp_mod
from .gallery import download_gallery, fetch_gallery_title, GalleryDlError, is_available as gallery_available

logger = logging.getLogger(__name__)


@dataclass
class DownloadJob:
    user_id: int
    resolved: ResolvedUrl
    settings: UserSettings
    download_dir: Path
    cookie_path: Path | None = None
    use_browser_cookies: bool = False
    clip: ClipSpec | None = None         # single clip (legacy)
    clips: list[ClipSpec] = field(default_factory=list)  # multi-segment
    audio_only: bool = False
    engine_override: Engine | None = None
    info: dict[str, Any] = field(default_factory=dict)
    files: list[Path] = field(default_factory=list)
    title: str = ""
    duration: float = 0.0
    width: int = 0
    height: int = 0
    thumb: Path | None = None
    status: str = "pending"
    error: str = ""


class DownloadManager:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._proxy = ProxyManager.from_settings(settings)
        self._ipv6 = IPv6Pool.from_settings(settings)

    async def run(
        self,
        job: DownloadJob,
        progress_cb: ProgressCallback | None = None,
    ) -> DownloadJob:
        """
        Execute the full pipeline: extract info -> download -> return job with files.

        Engine routing:
          YTDLP              → yt-dlp only
          GALLERY_DL         → gallery-dl only (images/albums)
          YTDLP_THEN_GALLERY → try yt-dlp first; fall back to gallery-dl on error
        """
        try:
            job.status = "downloading"
            engine = job.engine_override or job.resolved.engine

            if engine == Engine.GALLERY_DL:
                await self._download_gallery(job)
            elif engine == Engine.YTDLP_THEN_GALLERY:
                try:
                    await self._extract_info(job)
                    await self._download(job, progress_cb)
                except (DownloadError, Exception) as e:
                    logger.info(
                        "yt-dlp failed for %s (%s), trying gallery-dl",
                        job.resolved.url, e,
                    )
                    job.files = []
                    await self._download_gallery(job)
            else:
                await self._extract_info(job)
                await self._download(job, progress_cb)

            await self._check_file_sizes(job)
            job.status = "uploading"
        except Exception as e:
            job.status = "error"
            job.error = str(e)
            self._cleanup(job)
            raise
        return job

    async def _extract_info(self, job: DownloadJob) -> None:
        proxy = self._pick_proxy(job)
        ipv6 = self._pick_ipv6(job)
        extra: dict[str, Any] = {}
        if ipv6:
            extra["source_address"] = ipv6.as_ytdlp()
        opts = ytdlp_mod.build_ytdlp_opts(
            resolved=job.resolved,
            settings=job.settings,
            download_dir=job.download_dir,
            cookie_path=job.cookie_path,
            proxy=proxy,
            app_settings=self._settings,
            info_only=True,
            clip=job.clip,
            use_browser_cookies=job.use_browser_cookies,
            extra_opts=extra or None,
        )
        info = await ytdlp_mod.extract_info(opts, job.resolved.url)
        job.info = info
        job.title = info.get("title") or info.get("webpage_url_basename") or ""
        full_duration = float(info.get("duration") or 0)
        # For clips, use the clip duration instead of the full video duration
        if job.clip:
            job.duration = float(job.clip.duration_sec)
        elif full_duration:
            job.duration = full_duration
        logger.info(
            "Info extracted: user=%s url=%s title=%r duration=%.0fs",
            job.user_id, job.resolved.url, job.title, job.duration,
        )

    async def _download(self, job: DownloadJob, progress_cb: ProgressCallback | None) -> None:
        proxy = self._pick_proxy(job)
        ipv6 = self._pick_ipv6(job)
        extra: dict[str, Any] = {}
        if ipv6:
            extra["source_address"] = ipv6.as_ytdlp()
        if job.audio_only:
            extra["format"] = "bestaudio/best"
            extra["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        # Multi-segment clips passed via extra_opts["_clips"]
        if job.clips:
            extra["_clips"] = job.clips
        opts = ytdlp_mod.build_ytdlp_opts(
            resolved=job.resolved,
            settings=job.settings,
            download_dir=job.download_dir,
            cookie_path=job.cookie_path,
            proxy=proxy,
            app_settings=self._settings,
            info_only=False,
            clip=job.clip,
            extra_opts=extra if extra else None,
            use_browser_cookies=job.use_browser_cookies,
        )

        if progress_cb:
            opts["progress_hooks"] = [_make_progress_hook(progress_cb)]

        job.files = await ytdlp_mod.download(opts, job.resolved.url)
        logger.info(
            "Download done: user=%s files=%s",
            job.user_id, [f.name for f in job.files],
        )

    async def _check_file_sizes(self, job: DownloadJob) -> None:
        max_bytes = self._settings.max_file_size_bytes
        for f in job.files:
            size = f.stat().st_size
            if size > max_bytes:
                raise FileTooLargeError(
                    size=humanbytes(size),
                    max_size=humanbytes(max_bytes),
                )

    async def _download_gallery(self, job: DownloadJob) -> None:
        """Run gallery-dl for image/album URLs."""
        if not gallery_available():
            raise DownloadError(error="gallery-dl is not installed on this server")

        proxy_cfg = self._pick_proxy(job)
        proxy_url = proxy_cfg.as_ytdlp() if proxy_cfg else None

        # Fetch title before downloading (non-fatal)
        if not job.title:
            try:
                fetched = await fetch_gallery_title(
                    url=job.resolved.url,
                    cookie_path=job.cookie_path,
                    proxy=proxy_url,
                )
                if fetched:
                    job.title = fetched
            except Exception as exc:
                logger.debug("gallery title fetch failed: %s", exc)

        ipv6 = self._pick_ipv6(job)
        files = await download_gallery(
            url=job.resolved.url,
            download_dir=job.download_dir,
            cookie_path=job.cookie_path,
            proxy=proxy_url,
            source_address=ipv6.as_ytdlp() if ipv6 else None,
            playlist_start=job.resolved.playlist_start,
            playlist_end=job.resolved.playlist_end,
        )

        if not files:
            raise DownloadError(error="No images found at this URL")

        job.files = files
        job.title = job.title or job.resolved.domain
        logger.info(
            "gallery-dl done: user=%s files=%d url=%s",
            job.user_id, len(files), job.resolved.url,
        )

    def _pick_proxy(self, job: DownloadJob) -> ProxyConfig | None:
        # User's own proxy URL takes priority over system proxy
        if job.resolved.custom_proxy_url:
            return ProxyConfig.from_url(job.resolved.custom_proxy_url)
        if not job.resolved.use_proxy:
            return None
        return self._proxy.get()

    def _pick_ipv6(self, job: DownloadJob) -> IPv6Binding | None:
        if not self._ipv6:
            return None
        from yoink_dl.url.domains import domain_matches
        if not domain_matches(job.resolved.domain, self._settings.ipv6_domains):
            return None
        return self._ipv6.get()

    def _cleanup(self, job: DownloadJob) -> None:
        try:
            if job.download_dir.exists():
                shutil.rmtree(job.download_dir, ignore_errors=True)
        except Exception as e:
            logger.warning("Cleanup failed for %s: %s", job.download_dir, e)


def create_download_dir(base: str = "/tmp") -> Path:
    """Create a unique temp directory for a single download job."""
    d = Path(tempfile.mkdtemp(prefix="yoink_", dir=base))
    return d


ProgressCallback = Callable[[int, int], Coroutine[Any, Any, None]]


def _make_progress_hook(cb: ProgressCallback) -> Callable[[dict[str, Any]], None]:
    """Wrap a progress callback for yt-dlp's progress_hooks format.

    Must be called from an async context so the running loop can be
    captured. The hook itself runs in a yt-dlp worker thread.
    """
    loop = asyncio.get_running_loop()

    def hook(d: dict[str, Any]) -> None:
        if d.get("status") == "downloading":
            downloaded = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            try:
                loop.call_soon_threadsafe(asyncio.ensure_future, cb(downloaded, total))
            except Exception:
                pass
    return hook
