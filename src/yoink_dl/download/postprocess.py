"""
Pre-upload postprocessing pipeline.

Sits between download and send_file. Ensures every video file is
in a format Telegram can play inline before we try to upload it.

Rules (in order):
1. .ts / .webm / .mkv / other non-mp4 video  -> remux to .mp4 (stream copy, lossless)
2. Width or height not divisible by 2         -> scale to nearest even dims (Telegram/H.264 requirement)
3. Audio codec not in AAC/MP3/OPUS            -> transcode audio only, keep video stream
4. Everything else                            -> pass through unchanged

All heavy ops run in a thread executor so the event loop stays free.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="postproc")

# Containers Telegram plays inline as video
_TG_VIDEO_CONTAINERS = frozenset({".mp4", ".m4v"})

# Audio codecs Telegram accepts in mp4 without issues
_TG_AUDIO_CODECS = frozenset({"aac", "mp4a", "mp3", "opus"})

# Video codecs that need re-encoding (Telegram needs H.264 for inline playback)
_NEEDS_TRANSCODE_VCODEC = frozenset({"vp9", "vp8", "av1", "av01", "theora", "hevc", "h265"})


def _probe_streams(path: Path) -> tuple[str, str, int, int, int]:
    """
    Return (vcodec, acodec, width, height, rotation) via ffprobe.
    rotation is the display rotation in degrees (0, 90, 180, 270).
    Falls back to ("", "", 0, 0, 0) on any error.
    """
    import json
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_entries", "stream_side_data",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            return "", "", 0, 0, 0
        data = json.loads(result.stdout)
        vcodec = acodec = ""
        width = height = rotation = 0
        for stream in data.get("streams", []):
            ct = stream.get("codec_type", "")
            if ct == "video" and not vcodec:
                vcodec = stream.get("codec_name", "").lower()
                width = int(stream.get("width") or 0)
                height = int(stream.get("height") or 0)
                # Check side_data for display matrix rotation
                for sd in stream.get("side_data_list", []):
                    if sd.get("side_data_type") == "Display Matrix":
                        rot = int(sd.get("rotation", 0))
                        # rotation in side_data is negative CW, normalize to 0/90/180/270
                        rotation = (-rot) % 360
            elif ct == "audio" and not acodec:
                acodec = stream.get("codec_name", "").lower()
        return vcodec, acodec, width, height, rotation
    except Exception as e:
        logger.warning("ffprobe failed for %s: %s", path.name, e)
        return "", "", 0, 0, 0


def _needs_even_dims(width: int, height: int) -> bool:
    return (width % 2 != 0) or (height % 2 != 0)


def _build_remux_cmd(src: Path, dst: Path) -> list[str]:
    """Stream copy into mp4 - fast, lossless, just changes container."""
    return [
        "ffmpeg", "-y",
        "-i", str(src),
        "-c", "copy",
        "-movflags", "+faststart",  # moov atom at front - better for streaming
        str(dst),
    ]


def _build_transcode_cmd(
    src: Path,
    dst: Path,
    vcodec: str,
    acodec: str,
    width: int,
    height: int,
    rotation: int = 0,
) -> list[str]:
    """
    Transcode to H.264/AAC mp4.
    Only re-encodes what needs to be re-encoded:
    - video: transcode if codec incompatible with Telegram or dims/rotation need fixing
    - audio: transcode only if codec not in accepted list
    - rotation: bake rotation into stream via transpose filter, strip side_data
    """
    needs_venc = vcodec in _NEEDS_TRANSCODE_VCODEC
    needs_aenc = bool(acodec) and not any(acodec.startswith(ok) for ok in _TG_AUDIO_CODECS)
    needs_scale = _needs_even_dims(width, height)
    needs_rotate = rotation in (90, 180, 270)

    # Any video filter requires re-encoding (can't use -c:v copy with -vf)
    needs_venc = needs_venc or needs_scale or needs_rotate

    cmd = ["ffmpeg", "-y", "-i", str(src)]

    if needs_venc:
        vf_parts: list[str] = []
        if needs_rotate:
            # transpose: 1=90CW, 2=90CCW, for 180 use two transposes
            if rotation == 90:
                vf_parts.append("transpose=1")
            elif rotation == 270:
                vf_parts.append("transpose=2")
            elif rotation == 180:
                vf_parts.append("transpose=1,transpose=1")
        if needs_scale:
            vf_parts.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")
        cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "18"]
        if vf_parts:
            cmd += ["-vf", ",".join(vf_parts)]
        # Strip rotation metadata so players don't double-rotate
        if needs_rotate:
            cmd += ["-metadata:s:v:0", "rotate=0"]
    else:
        cmd += ["-c:v", "copy"]

    if needs_aenc:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-c:a", "copy"]

    cmd += ["-movflags", "+faststart", str(dst)]
    return cmd


def _run_ffmpeg(cmd: list[str]) -> bool:
    """Run an ffmpeg command, return True on success."""
    logger.debug("ffmpeg: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        logger.error("ffmpeg failed (exit %d): %s", result.returncode, result.stderr[-500:])
        return False
    return True


def _postprocess_sync(path: Path) -> Path:
    """
    Synchronous postprocessing logic. Returns path to the final file
    (may be the same path if no changes needed, or a new .mp4 path).
    """
    ext = path.suffix.lower()
    is_video = ext in {".mp4", ".mkv", ".webm", ".ts", ".avi", ".mov", ".m4v", ".flv", ".3gp"}

    if not is_video:
        # Audio/image/document - pass through
        return path

    vcodec, acodec, width, height, rotation = _probe_streams(path)

    needs_remux = ext not in _TG_VIDEO_CONTAINERS
    needs_venc = vcodec in _NEEDS_TRANSCODE_VCODEC
    needs_aenc = bool(acodec) and not any(acodec.startswith(ok) for ok in _TG_AUDIO_CODECS)
    needs_scale = width > 0 and height > 0 and _needs_even_dims(width, height)
    needs_rotate = rotation in (90, 180, 270)

    if not (needs_remux or needs_venc or needs_aenc or needs_scale or needs_rotate):
        logger.debug("postprocess: %s needs no changes", path.name)
        return path

    dst = path.with_suffix(".pp.mp4")

    if needs_venc or needs_aenc or needs_scale or needs_rotate:
        reason = []
        if needs_venc:
            reason.append(f"vcodec={vcodec}")
        if needs_aenc:
            reason.append(f"acodec={acodec}")
        if needs_scale:
            reason.append(f"dims {width}x{height} not even")
        if needs_rotate:
            reason.append(f"rotation={rotation}")
        logger.info("postprocess: transcoding %s (%s)", path.name, ", ".join(reason))
        cmd = _build_transcode_cmd(path, dst, vcodec, acodec, width, height, rotation)
    else:
        logger.info("postprocess: remuxing %s (%s -> mp4)", path.name, ext)
        cmd = _build_remux_cmd(path, dst)

    ok = _run_ffmpeg(cmd)
    if not ok or not dst.exists() or dst.stat().st_size == 0:
        logger.warning("postprocess failed for %s, using original", path.name)
        if dst.exists():
            dst.unlink()
        return path

    # Sanity: output should be at least 50% of input size
    if dst.stat().st_size < path.stat().st_size * 0.3:
        logger.warning(
            "postprocess output suspiciously small (%.1f%% of original), using original",
            dst.stat().st_size / path.stat().st_size * 100,
        )
        dst.unlink()
        return path

    logger.info(
        "postprocess: %s -> %s (%.1f MB -> %.1f MB)",
        path.name, dst.name,
        path.stat().st_size / 1e6,
        dst.stat().st_size / 1e6,
    )
    path.unlink(missing_ok=True)
    return dst


async def postprocess(path: Path) -> Path:
    """
    Async wrapper. Run postprocessing in thread pool.
    Returns the (possibly new) path to upload.
    Never raises - returns original path on any failure.
    """
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(_executor, _postprocess_sync, path)
    except Exception as e:
        logger.error("postprocess unexpected error for %s: %s", path.name, e)
        return path


async def postprocess_all(files: list[Path]) -> list[Path]:
    """Postprocess a list of files concurrently."""
    return list(await asyncio.gather(*[postprocess(f) for f in files]))
