"""
/search <query>  - search YouTube and pick a result to download.

Shows top 5 results as inline keyboard buttons. User picks one → downloads.
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

import yt_dlp

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from yoink.core.bot.access import AccessPolicy, require_access
from yoink.core.db.models import UserRole
from yoink_dl.bot.middleware import get_settings, get_user_repo
from yoink.core.i18n import t

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ytsearch")

_USAGE = (
    "<b>/search</b>  - search YouTube\n\n"
    "<b>Usage:</b> <code>/search cute cats</code>"
)

_CB_PREFIX = "search_pick:"
_MAX_RESULTS = 5


def _do_search(query: str) -> list[dict]:
    """Blocking yt-dlp search  - runs in thread."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{_MAX_RESULTS}:{query}", download=False)
        if not info:
            return []
        return info.get("entries") or []
    except Exception as e:
        logger.warning("Search failed: %s", e)
        return []


@require_access(AccessPolicy(min_role=UserRole.user, silent_deny=True))
async def _cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_html(_USAGE)
        return

    query = " ".join(context.args)
    user = await get_user_repo(context).get_or_create(user_id)
    lang = user.language

    status = await update.message.reply_html(
        t("search.prompt", lang).replace("{}", f"<b>{query}</b>")
        if "{}" in t("search.prompt", lang)
        else f"🔍 Searching: <b>{query}</b>…"
    )

    loop = asyncio.get_running_loop()
    entries = await loop.run_in_executor(_executor, _do_search, query)

    if not entries:
        await status.edit_text(
            t("search.no_results", lang, query=query), parse_mode="HTML"
        )
        return

    buttons: list[list[InlineKeyboardButton]] = []
    for i, entry in enumerate(entries[:_MAX_RESULTS]):
        title = (entry.get("title") or "Unknown")[:60]
        duration = entry.get("duration") or 0
        dur_str = f"{int(duration // 60)}:{int(duration % 60):02d}" if duration else "?"
        url = entry.get("url") or entry.get("webpage_url") or ""
        if not url:
            continue
        label = f"{i + 1}. {title} [{dur_str}]"
        buttons.append([InlineKeyboardButton(label, callback_data=f"{_CB_PREFIX}{url}", style="primary")])

    if not buttons:
        await status.edit_text(
            t("search.no_results", lang, query=query), parse_mode="HTML"
        )
        return

    await status.edit_text(
        t("search.results_title", lang, query=query),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _cb_search_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User tapped a search result  - trigger download via user_data flag."""
    query: CallbackQuery | None = update.callback_query
    if not query or not query.data:
        return
    await query.answer()

    url = query.data.removeprefix(_CB_PREFIX)
    if not url.startswith(("http://", "https://")):
        await query.answer("Invalid URL", show_alert=True)
        return

    # Delete the search results message
    await query.message.delete()  # type: ignore[union-attr]

    # Send the URL as a new message so the main url_handler picks it up
    if query.message and query.message.chat:
        await context.bot.send_message(
            chat_id=query.message.chat.id,
            text=url,
        )


def register(app: Application) -> None:
    app.add_handler(CommandHandler("search", _cmd_search))
    app.add_handler(CallbackQueryHandler(_cb_search_pick, pattern=rf"^{_CB_PREFIX}"))
