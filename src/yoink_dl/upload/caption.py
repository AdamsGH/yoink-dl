"""Caption builder for uploaded media."""
from __future__ import annotations

from yoink_dl.config import DownloaderConfig as Settings
from yoink.core.i18n import t

# Telegram caption limit
_MAX_CAPTION = 1024


def build_group_caption(
    url: str,
    requester_name: str,
    requester_id: int,
) -> str:
    """One-line caption for group chat: author mention + source link.

    Kept short intentionally  - group feeds should stay clean.
    Format: «Adams · source»
    """
    safe = _escape_html(requester_name)
    mention = f'<a href="tg://user?id={requester_id}">{safe}</a>'
    source = f'<a href="{url}">source</a>'
    return f"{mention} · {source}"


def build_caption(
    title: str,
    url: str,
    settings: Settings,
    lang: str = "en",
    tags: str = "",
    extra: str = "",
) -> str:
    """
    Build HTML caption for uploaded video/audio.
    Truncates title if needed to fit within Telegram's 1024-char limit.
    """
    managed_by = getattr(settings, "MANAGED_BY", "")
    credits_bots = getattr(settings, "CREDITS_BOTS", "")

    parts: list[str] = []

    if title:
        safe_title = _escape_html(title)
        parts.append(f"<b>{safe_title}</b>")

    if url:
        parts.append(f'<a href="{url}">source</a>')

    if tags:
        parts.append(tags)

    if extra:
        parts.append(extra)

    if managed_by or credits_bots:
        credits = t("common.credits", lang, managed_by=managed_by, credits_bots=credits_bots)
        parts.append(credits)

    caption = "\n\n".join(p for p in parts if p)

    if len(caption) > _MAX_CAPTION:
        # Truncate title and rebuild
        overhead = len(caption) - len(parts[0]) if parts else 0
        budget = _MAX_CAPTION - overhead - 10
        if budget > 0 and title:
            truncated = _escape_html(title[:budget]) + "…"
            parts[0] = f"<b>{truncated}</b>"
        caption = "\n\n".join(p for p in parts if p)
        caption = caption[:_MAX_CAPTION]

    return caption


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
