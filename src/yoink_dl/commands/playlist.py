"""
/playlist [start-end] <url>  - download a playlist or range of playlist items.

Examples:
  /playlist https://youtube.com/playlist?list=PLxxx       - all items (up to limit)
  /playlist 1-5 https://youtube.com/playlist?list=PLxxx   - items 1 to 5
  /playlist -5 https://youtube.com/playlist?list=PLxxx    - last 5 items
"""
from __future__ import annotations

import logging
import re

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from yoink_dl.bot.middleware import get_settings, get_user_repo, is_blocked
from yoink.core.i18n import t
from yoink_dl.url.domains import DomainConfig
from yoink_dl.url.normalizer import normalize
from yoink_dl.url.resolver import resolve

logger = logging.getLogger(__name__)

_USAGE = (
    "<b>/playlist</b>  - download playlist items\n\n"
    "<b>Usage:</b>\n"
    "  <code>/playlist URL</code>  - all items\n"
    "  <code>/playlist 1-5 URL</code>  - items 1 to 5\n"
    "  <code>/playlist -5 URL</code>  - last 5 items\n\n"
    "<i>Tip: you can also append range to any URL directly:</i>\n"
    "  <code>URL*1*5</code>"
)

_MAX_ITEMS = 20
_RANGE_RE = re.compile(r"^(-?\d+)(?:-(-?\d+))?$")


def _parse_range(token: str) -> tuple[int | None, int | None] | None:
    """Parse '1-5', '-5', '3' into (start, end) or None."""
    m = _RANGE_RE.match(token)
    if not m:
        return None
    a = int(m.group(1))
    b = int(m.group(2)) if m.group(2) else None
    if b is None:
        if a < 0:
            return (a, None)
        return (1, a)
    return (a, b)


async def _cmd_playlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    user_id = update.effective_user.id
    if await is_blocked(user_id, context):
        return

    args = context.args or []
    if not args:
        await update.message.reply_html(_USAGE)
        return

    url = args[-1]
    if not url.startswith(("http://", "https://")):
        user_lang = (await get_user_repo(context).get_or_create(user_id)).language
        await update.message.reply_html(t("playlist.no_url", user_lang) + "\n\n" + _USAGE)
        return

    range_str = args[0] if len(args) >= 2 else None
    playlist_start: int | None = None
    playlist_end: int | None = None

    if range_str:
        parsed = _parse_range(range_str)
        if parsed is None:
            await update.message.reply_html(
                f"❌ Invalid range: <code>{range_str}</code>\n\n" + _USAGE
            )
            return
        playlist_start, playlist_end = parsed

        # Safety cap
        if playlist_start and playlist_end:
            count = abs(playlist_end - playlist_start) + 1
            if count > _MAX_ITEMS:
                await update.message.reply_html(
                    f"❌ Range too large ({count} items). Maximum is {_MAX_ITEMS}."
                )
                return

    settings = get_settings(context)
    domain_cfg = DomainConfig.from_config(settings)
    url = normalize(url, domain_cfg)

    # Encode range into URL using *start*end syntax so url_handler picks it up
    if playlist_start is not None:
        end_part = f"*{playlist_end}" if playlist_end is not None else ""
        tagged_url = f"{url}*{playlist_start}{end_part}"
    else:
        tagged_url = f"{url}*1*{_MAX_ITEMS}"

    # Simulate a text message with the tagged URL so the normal pipeline handles it
    await update.message.reply_html(
        f"📂 Processing playlist: <code>{url}</code>\n"
        f"Range: <b>{playlist_start or 1} – {playlist_end or _MAX_ITEMS}</b>\n\n"
        f"<i>Send the URL directly to download:</i>\n<code>{tagged_url}</code>"
    )


def register(app: Application) -> None:
    app.add_handler(CommandHandler("playlist", _cmd_playlist))
