"""
FFmpeg/ffprobe utilities.

All operations are async - ffmpeg runs in a thread pool so it never
blocks the event loop. No moviepy dependency - pure subprocess.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ffmpeg")

# Probe

def _probe_sync(path: Path) -> dict:
    """Run ffprobe and return parsed JSON. Raises on failure."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(path),
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr[:300]}")
    return json.loads(result.stdout)


async def probe(path: Path) -> dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _probe_sync, path)


async def get_video_info(path: Path) -> tuple[float, int, int]:
    """
    Return (duration_sec, width, height).
    Falls back to (0, 0, 0) on any error - never raises.
    """
    try:
        info = await probe(path)
        duration = float(info.get("format", {}).get("duration") or 0)
        for stream in info.get("streams", []):
            if stream.get("codec_type") == "video":
                w = int(stream.get("width") or 0)
                h = int(stream.get("height") or 0)
                return duration, w, h
        return duration, 0, 0
    except Exception as e:
        logger.warning("get_video_info failed for %s: %s", path.name, e)
        return 0.0, 0, 0


# Thumbnail

def _make_thumb_sync(video_path: Path, out_path: Path, seek: float = 2.0) -> bool:
    """
    Extract a single frame at `seek` seconds and scale to fit 640px.
    Returns True on success.
    """
    # Get dimensions first to choose scale
    try:
        probe_cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", str(video_path)
        ]
        raw = subprocess.run(probe_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        info = json.loads(raw.stdout) if raw.returncode == 0 else {}
        w, h = 0, 0
        for s in info.get("streams", []):
            if s.get("codec_type") == "video":
                w, h = int(s.get("width") or 0), int(s.get("height") or 0)
                break
    except Exception:
        w, h = 0, 0

    # Scale filter: fit longest side to 640, keep aspect, ensure even dims
    if w > 0 and h > 0:
        if w >= h:
            scale = "scale=640:-2"
        else:
            scale = "scale=-2:640"
    else:
        scale = "scale=640:-2"

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(seek),
        "-i", str(video_path),
        "-vframes", "1",
        "-vf", scale,
        "-q:v", "2",
        str(out_path),
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0 or not out_path.exists():
        # Fallback: black frame
        logger.warning("Thumbnail extraction failed, creating black frame fallback")
        fallback_cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=640x360",
            "-frames:v", "1",
            str(out_path),
        ]
        subprocess.run(fallback_cmd, capture_output=True)
    return out_path.exists() and out_path.stat().st_size > 0


async def make_thumbnail(video_path: Path, out_path: Path | None = None) -> Path | None:
    """
    Extract thumbnail from video. Returns path to .jpg or None on failure.
    out_path defaults to <video_stem>.__thumb.jpg next to the video.
    """
    if out_path is None:
        out_path = video_path.with_suffix(".__thumb.jpg")
    loop = asyncio.get_running_loop()
    ok = await loop.run_in_executor(_executor, _make_thumb_sync, video_path, out_path)
    return out_path if ok else None


# Split

def _split_sync(
    video_path: Path,
    out_dir: Path,
    max_bytes: int,
    duration: float,
    progress_cb: Any | None = None,
) -> list[Path]:
    """
    Split video into parts of at most max_bytes each.
    Uses stream copy - fast, lossless, no re-encoding.
    Returns list of part paths in order.
    """
    if duration <= 0:
        raise ValueError("Cannot split: unknown duration")

    file_size = video_path.stat().st_size
    n_parts = math.ceil(file_size / max_bytes)
    if n_parts < 2:
        return [video_path]

    part_duration = duration / n_parts
    parts: list[Path] = []
    stem = video_path.stem[:60]  # avoid absurdly long names
    ext = video_path.suffix or ".mp4"

    for i in range(n_parts):
        start = i * part_duration
        out = out_dir / f"{stem}_part{i + 1:02d}{ext}"
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{start:.3f}",
            "-i", str(video_path),
            "-t", f"{part_duration:.3f}",
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            str(out),
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        if result.returncode != 0:
            logger.error("Split part %d failed: %s", i + 1, result.stderr[:300])
            # Try to continue with remaining parts
            continue
        if out.exists() and out.stat().st_size > 0:
            parts.append(out)
            logger.info("Split part %d/%d: %s (%.1f MB)", i + 1, n_parts, out.name, out.stat().st_size / 1e6)

    return parts


async def split_video(
    video_path: Path,
    out_dir: Path,
    max_bytes: int,
    duration: float,
) -> list[Path]:
    """
    Split video into chunks of at most max_bytes.
    Returns list of part paths, or [original] if no split needed.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _executor, _split_sync, video_path, out_dir, max_bytes, duration, None
    )


# Subtitle embedding

def _embed_subs_sync(video_path: Path, srt_path: Path, out_path: Path) -> bool:
    """
    Burn subtitles into video with ffmpeg.
    Font: Arial Black, white text, 75% black background.
    Returns True on success, False on failure.
    Atomically replaces video_path with result on success.
    """
    if not srt_path.exists() or srt_path.stat().st_size == 0:
        logger.error("Subtitle file missing or empty: %s", srt_path)
        return False

    # Escape single quotes in path for subtitles filter
    srt_escaped = str(srt_path).replace("'", r"'\''")
    filter_arg = (
        f"subtitles='{srt_escaped}':"
        "force_style='FontName=Arial Black,FontSize=16,"
        "PrimaryColour=&Hffffff,OutlineColour=&H000000,"
        "BackColour=&H80000000,Outline=2,Shadow=1,MarginV=25'"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", filter_arg,
        "-c:a", "copy",
        str(out_path),
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        logger.debug("ffmpeg: %s", line.rstrip())
    proc.wait()

    if proc.returncode != 0:
        logger.error("Subtitle embedding failed (exit %d)", proc.returncode)
        if out_path.exists():
            out_path.unlink()
        return False

    if not out_path.exists() or out_path.stat().st_size == 0:
        logger.error("Output file missing or empty after subtitle embedding")
        return False

    # Sanity check - output should be at least 50% of original
    if out_path.stat().st_size < video_path.stat().st_size * 0.5:
        logger.error("Output suspiciously small, aborting subtitle embed")
        out_path.unlink()
        return False

    # Atomic replace: backup -> rename result -> delete backup
    backup = video_path.with_suffix(".backup")
    try:
        video_path.rename(backup)
        out_path.rename(video_path)
        backup.unlink()
    except Exception as e:
        logger.error("Atomic replace failed: %s", e)
        if backup.exists():
            backup.rename(video_path)
        if out_path.exists():
            out_path.unlink()
        return False

    return True


async def embed_subtitles(video_path: Path, srt_path: Path) -> bool:
    """
    Burn subtitles into video in-place.
    Returns True if successful, False if skipped/failed (non-fatal).
    """
    out_path = video_path.with_suffix(".__subs_temp.mp4")
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _embed_subs_sync, video_path, srt_path, out_path)


# SRT encoding fix

async def fix_srt_encoding(srt_path: Path) -> Path:
    """
    Ensure SRT file is UTF-8. Detects encoding and converts if needed.
    Returns the same path (modified in-place).
    """
    def _fix() -> None:
        try:
            srt_path.read_text(encoding="utf-8")
            return  # Already UTF-8
        except UnicodeDecodeError:
            pass
        # Try chardet detection
        try:
            import chardet
            raw = srt_path.read_bytes()
            detected = chardet.detect(raw)
            enc = detected.get("encoding") or "cp1252"
            text = raw.decode(enc, errors="replace")
            srt_path.write_text(text, encoding="utf-8")
            logger.info("Converted SRT from %s to UTF-8: %s", enc, srt_path.name)
        except Exception as e:
            logger.warning("SRT encoding fix failed: %s", e)

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_executor, _fix)
    return srt_path


# Helpers

def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


# fix missing Any import
from typing import Any
