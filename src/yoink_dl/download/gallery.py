"""
gallery-dl download engine.

Handles image/gallery URLs: Instagram, Twitter/X, Reddit, Pixiv,
DeviantArt, Kemono, imageboards, etc.

Returns a list of downloaded file paths. Files are grouped by album/post
so the caller can send them as Telegram media groups (up to 10 at a time).
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="gallery_dl")

# gallery-dl binary name inside the container
_BINARY = "gallery-dl"


class GalleryDlError(Exception):
    pass


def _run_gallery_dl(
    url: str,
    download_dir: Path,
    cookie_path: Path | None = None,
    proxy: str | None = None,
    playlist_start: int | None = None,
    playlist_end: int | None = None,
) -> list[Path]:
    """
    Blocking gallery-dl invocation. Runs in thread pool.
    Returns list of downloaded file paths sorted by filename.
    """
    cmd: list[str] = [
        _BINARY,
        "--quiet",
        "--directory", str(download_dir),
        "--filename", "{num:>04}_{filename}.{extension}",
    ]

    if cookie_path and cookie_path.exists():
        cmd += ["--cookies", str(cookie_path)]

    if proxy:
        cmd += ["--proxy", proxy]

    if playlist_start is not None:
        rng = f"{playlist_start}-{playlist_end}" if playlist_end is not None else f"{playlist_start}-"
        cmd += ["--range", rng]

    cmd.append(url)

    logger.info("gallery-dl cmd: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode not in (0, 1):  # 1 = partial success (some items skipped)
        raise GalleryDlError(
            f"gallery-dl exited {result.returncode}: {result.stderr.strip()[:200]}"
        )

    files = sorted(
        (f for f in download_dir.rglob("*") if f.is_file()),
        key=lambda f: f.name,
    )
    return files


async def download_gallery(
    url: str,
    download_dir: Path,
    cookie_path: Path | None = None,
    proxy: str | None = None,
    playlist_start: int | None = None,
    playlist_end: int | None = None,
) -> list[Path]:
    """Async wrapper around gallery-dl. Raises GalleryDlError on failure."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _executor,
        _run_gallery_dl,
        url,
        download_dir,
        cookie_path,
        proxy,
        playlist_start,
        playlist_end,
    )


def is_available() -> bool:
    """Check if gallery-dl binary is installed."""
    import shutil
    return shutil.which(_BINARY) is not None
