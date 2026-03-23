"""
Mediainfo report generator.

Runs `mediainfo` CLI on a file and returns a formatted Telegram message.
Uses JSON output for structured parsing, then renders a compact human-readable
report using expandable_blockquote for the technical details section.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_BIN = "mediainfo"
_TIMEOUT = 15


async def get_report(file: Path) -> str | None:
    """
    Run mediainfo on *file* and return an HTML-formatted Telegram message,
    or None if mediainfo is unavailable or fails.

    The message uses <blockquote expandable> so technical details are
    collapsed by default  - the user taps to expand if interested.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            _BIN, "--Output=JSON", str(file),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT)
    except FileNotFoundError:
        logger.debug("mediainfo binary not found")
        return None
    except asyncio.TimeoutError:
        logger.warning("mediainfo timed out for %s", file.name)
        return None
    except Exception as e:
        logger.warning("mediainfo error for %s: %s", file.name, e)
        return None

    if not stdout:
        return None

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return None

    tracks: list[dict] = (data.get("media") or {}).get("track") or []
    if not tracks:
        return None

    sections: list[str] = []
    for track in tracks:
        track_type = track.get("@type", "")
        lines = _render_track(track_type, track)
        if lines:
            sections.append(f"<b>{track_type}</b>\n" + "\n".join(lines))

    if not sections:
        return None

    body = "\n\n".join(sections)
    return f"ℹ️ <b>Mediainfo</b>  - <code>{_esc(file.name)}</code>\n\n<blockquote expandable>{body}</blockquote>"


def _render_track(track_type: str, track: dict) -> list[str]:
    """Pick the most relevant fields per track type."""
    if track_type == "General":
        keys = [
            ("Format",          "Format"),
            ("Format_Profile",  "Profile"),
            ("Duration",        "Duration"),
            ("FileSize",        "Size"),
            ("OverallBitRate",  "Bitrate"),
            ("Encoded_Date",    "Encoded"),
        ]
    elif track_type == "Video":
        keys = [
            ("Format",          "Codec"),
            ("Format_Profile",  "Profile"),
            ("Width",           "Width"),
            ("Height",          "Height"),
            ("FrameRate",       "FPS"),
            ("BitRate",         "Bitrate"),
            ("ColorSpace",      "Color"),
            ("HDR_Format",      "HDR"),
        ]
    elif track_type == "Audio":
        keys = [
            ("Format",          "Codec"),
            ("Channels",        "Channels"),
            ("SamplingRate",    "Sample rate"),
            ("BitRate",         "Bitrate"),
            ("Language",        "Language"),
        ]
    elif track_type == "Text":
        keys = [
            ("Format",          "Format"),
            ("Language",        "Language"),
            ("Title",           "Title"),
        ]
    else:
        return []

    lines: list[str] = []
    for key, label in keys:
        val = track.get(key)
        if not val:
            continue
        val = _format_value(key, str(val))
        lines.append(f"  {label}: <code>{_esc(val)}</code>")
    return lines


def _format_value(key: str, raw: str) -> str:
    """Human-friendly formatting for common fields."""
    if key in ("FileSize",):
        try:
            b = int(raw)
            if b >= 1 << 30:
                return f"{b / (1 << 30):.2f} GiB"
            if b >= 1 << 20:
                return f"{b / (1 << 20):.1f} MiB"
            if b >= 1 << 10:
                return f"{b / (1 << 10):.0f} KiB"
            return f"{b} B"
        except ValueError:
            pass

    if key in ("BitRate", "OverallBitRate"):
        try:
            bps = int(raw)
            if bps >= 1_000_000:
                return f"{bps / 1_000_000:.2f} Mbps"
            if bps >= 1_000:
                return f"{bps / 1_000:.0f} Kbps"
            return f"{bps} bps"
        except ValueError:
            pass

    if key == "Duration":
        try:
            ms = float(raw)
            s = int(ms / 1000) if ms > 1000 else int(ms)
            h, rem = divmod(s, 3600)
            m, sec = divmod(rem, 60)
            return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"
        except ValueError:
            pass

    if key == "SamplingRate":
        try:
            return f"{int(raw):,} Hz"
        except ValueError:
            pass

    if key in ("Width", "Height"):
        try:
            return f"{int(raw)} px"
        except ValueError:
            pass

    return raw


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
