"""
/tags  - show and manage download history tags.

Tags are keywords auto-extracted from downloaded content titles
and stored in the download_log. Shows the most-used tags as
a searchable list. Close button deletes the message.
"""
from __future__ import annotations

import logging
from collections import Counter

from sqlalchemy import select

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from yoink_dl.bot.middleware import get_session_factory, get_user_repo
from yoink.core.i18n import t
from yoink_dl.storage.models import DownloadLog

logger = logging.getLogger(__name__)

_MAX_TAGS = 50
_CLOSE_CB = "tags:close"


def _extract_tags(titles: list[str]) -> list[tuple[str, int]]:
    """
    Naive tag extraction: lowercase words longer than 3 chars,
    skip common stop words, count frequency.
    """
    _STOP = {
        "with", "this", "that", "from", "have", "what", "your",
        "will", "been", "were", "they", "their", "which", "when",
        "official", "video", "audio", "full", "feat", "2024", "2025",
    }
    counter: Counter = Counter()
    for title in titles:
        words = title.lower().replace("-", " ").replace("_", " ").split()
        for w in words:
            w = w.strip(".,!?\"'()")
            if len(w) > 3 and w.isalpha() and w not in _STOP:
                counter[w] += 1
    return counter.most_common(_MAX_TAGS)


async def _cmd_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    uid = update.effective_user.id
    repo = get_user_repo(context)
    user = await repo.get_or_create(uid)
    lang = user.language
    session_factory = get_session_factory(context)

    async with session_factory() as session:
        result = await session.execute(
            select(DownloadLog.title)
            .where(DownloadLog.user_id == uid)
            .where(DownloadLog.title.isnot(None))
            .order_by(DownloadLog.created_at.desc())
            .limit(200)
        )
        titles = [row[0] for row in result.fetchall() if row[0]]

    if not titles:
        await update.message.reply_html(
            "🏷 <b>Tags</b>\n\nNo download history yet.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(t("common.close", lang), callback_data=_CLOSE_CB)
            ]]),
        )
        return

    tag_list = _extract_tags(titles)
    if not tag_list:
        await update.message.reply_html(t("tags.cleared", lang))
        return

    lines = [f"🏷 <b>Your top tags</b> (from {len(titles)} downloads):\n"]
    for word, count in tag_list:
        lines.append(f"<code>{word}</code> × {count}")

    text = "\n".join(lines)
    # Split if too long (Telegram 4096 char limit)
    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]
    close_markup = InlineKeyboardMarkup([[
        InlineKeyboardButton(t("common.close", lang), callback_data=_CLOSE_CB)
    ]])

    for i, chunk in enumerate(chunks):
        markup = close_markup if i == len(chunks) - 1 else None
        await update.message.reply_html(chunk, reply_markup=markup)


async def _cb_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query: CallbackQuery | None = update.callback_query
    if not query:
        return
    await query.answer()
    try:
        await query.message.delete()  # type: ignore[union-attr]
    except Exception:
        await query.edit_message_reply_markup(reply_markup=None)


def register(app: Application) -> None:
    app.add_handler(CommandHandler("tags", _cmd_tags))
    app.add_handler(CallbackQueryHandler(_cb_tags, pattern=rf"^{_CLOSE_CB}$"))
