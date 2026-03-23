"""DL plugin formatting utilities."""
from __future__ import annotations

from yoink.core.utils.formatting import format_size, humantime  # noqa: F401  re-exported

humanbytes = format_size  # legacy alias used in progress.py


def progress_bar(current: int, total: int, width: int = 10) -> str:
    """Return a text progress bar: ████████░░ 80%"""
    if total <= 0:
        return "░" * width + " 0%"
    ratio = min(current / total, 1.0)
    filled = int(ratio * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"{bar} {ratio * 100:.0f}%"
