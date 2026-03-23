"""
Progress reporting via status message edits.

yt-dlp runs in a thread pool, so progress hooks are sync.
They put updates into a per-message Queue; a PTB JobQueue job
drains it every second and calls edit_message_text.

Usage:
    tracker = ProgressTracker(status_message)
    opts["progress_hooks"] = [tracker.ytdlp_hook]
    # after download starts upload:
    tracker.set_phase("upload")
    # PTB send_* progress= callback:
    await bot.send_video(..., progress=tracker.ptb_upload_cb)
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from queue import Queue, Empty
from typing import TYPE_CHECKING

from telegram import Message

from yoink_dl.utils.formatting import humanbytes

if TYPE_CHECKING:
    from telegram.ext import Application

logger = logging.getLogger(__name__)


def _progress_bar(pct: float, width: int = 10) -> str:
    filled = int(width * pct / 100)
    return "█" * filled + "░" * (width - filled)

_THROTTLE_SEC = 3.0   # minimum seconds between edits per message
_MIN_PCT_DELTA = 5.0  # don't edit if progress changed less than this %
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


@dataclass
class _Update:
    text: str
    ts: float


class ProgressTracker:
    """
    One tracker per download job. Thread-safe: yt-dlp hooks write from
    a thread pool, PTB job reads from the event loop.
    """

    def __init__(self, message: Message) -> None:
        self._message = message
        self._queue: Queue[_Update] = Queue()
        self._last_sent_ts: float = 0.0
        self._last_text: str = ""
        self._last_pct: float = -1.0
        self._phase: str = "download"

    def set_phase(self, phase: str) -> None:
        self._phase = phase

    def ytdlp_hook(self, d: dict) -> None:
        """yt-dlp progress_hook - called from thread pool."""
        if d.get("status") != "downloading":
            return
        try:
            downloaded = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            speed = d.get("speed") or 0
            eta = d.get("eta") or 0

            if total > 0:
                pct = downloaded / total * 100
                if abs(pct - self._last_pct) < _MIN_PCT_DELTA and pct < 99.0:
                    return
                text = f"Downloading {pct:.0f}%"
                if eta:
                    text += f", eta {eta}s"
            else:
                pct = -1.0
                pct_str = _ANSI_RE.sub("", d.get("_percent_str", "?%").strip())
                text = f"Downloading {pct_str}"

            self._last_pct = pct
            self._queue.put_nowait(_Update(text=text, ts=time.monotonic()))
        except Exception as e:
            logger.debug("ytdlp_hook error: %s", e)

    async def ptb_upload_cb(self, current: int, total: int) -> None:
        """
        PTB progress callback for send_video/send_document.
        Called directly from the upload coroutine with real byte counts.
        """
        try:
            if total > 0:
                pct = current / total * 100
                if abs(pct - self._last_pct) < _MIN_PCT_DELTA and pct < 99.0:
                    return
                now = time.monotonic()
                if now - self._last_sent_ts < _THROTTLE_SEC:
                    return
                bar = _progress_bar(pct)
                text = f"Uploading {bar} {pct:.0f}%\n{humanbytes(current)} / {humanbytes(total)}"
                self._last_pct = pct
                self._last_sent_ts = now
                await self._message.edit_text(text)
        except Exception:
            pass

    async def uploading_pulse(self, file_size: int = 0) -> None:
        """Fallback: show static upload status if progress cb isn't available."""
        text = f"Uploading {humanbytes(file_size)}…" if file_size else "Uploading…"
        try:
            await self._message.edit_text(text)
        except Exception:
            pass
        await asyncio.sleep(86400)

    async def flush(self) -> None:
        """Drain queue and edit message if throttle allows. Called by the job."""
        latest: _Update | None = None
        try:
            while True:
                latest = self._queue.get_nowait()
        except Empty:
            pass

        if latest is None:
            return

        now = time.monotonic()
        if now - self._last_sent_ts < _THROTTLE_SEC:
            return
        if latest.text == self._last_text:
            return

        try:
            await self._message.edit_text(latest.text)
            self._last_sent_ts = now
            self._last_text = latest.text
        except Exception:
            pass


# Global registry: message_id -> ProgressTracker
# Registered when job starts, removed when done.
_registry: dict[int, ProgressTracker] = {}


def register(tracker: ProgressTracker) -> None:
    _registry[tracker._message.message_id] = tracker


def unregister(tracker: ProgressTracker) -> None:
    _registry.pop(tracker._message.message_id, None)


async def _flush_job(context: object) -> None:
    """PTB JobQueue callback - runs every second."""
    for tracker in list(_registry.values()):
        await tracker.flush()


def setup_job(app: "Application") -> None:
    """Register the flush job. Call once at startup."""
    app.job_queue.run_repeating(_flush_job, interval=1.0, first=1.0, name="progress_flush")



