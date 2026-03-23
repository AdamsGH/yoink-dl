"""
/mediainfo  - toggle sending mediainfo reports after each download.
"""
from __future__ import annotations

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from yoink_dl.bot.middleware import get_user_repo
from yoink.core.i18n import t


def _keyboard(enabled: bool) -> InlineKeyboardMarkup:
    if enabled:
        label = "❌ Disable"
        data = "mediainfo:off"
    else:
        label = "✅ Enable"
        data = "mediainfo:on"
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=data)]])


async def _cmd_mediainfo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    repo = get_user_repo(context)
    user = await repo.get_or_create(update.effective_user.id)
    status = t("common.enabled", user.language) if user.mediainfo else t("common.disabled", user.language)
    await update.message.reply_html(
        f"ℹ️ Mediainfo: {status}",
        reply_markup=_keyboard(user.mediainfo),
    )


async def _cb_mediainfo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query: CallbackQuery | None = update.callback_query
    if not query or not update.effective_user:
        return
    await query.answer()

    enabled = (query.data or "").split(":", 1)[1] == "on"
    repo = get_user_repo(context)
    user = await repo.update(update.effective_user.id, mediainfo=enabled)

    text = t("mediainfo.enabled", user.language) if enabled else t("mediainfo.disabled", user.language)
    await query.edit_message_text(text, parse_mode="HTML")


def register(app: Application) -> None:
    app.add_handler(CommandHandler("mediainfo", _cmd_mediainfo))
    app.add_handler(CallbackQueryHandler(_cb_mediainfo, pattern=r"^mediainfo:"))
