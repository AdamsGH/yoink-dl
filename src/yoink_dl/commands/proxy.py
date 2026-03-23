"""
/proxy  - toggle proxy for downloads.
"""
from __future__ import annotations

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from yoink_dl.bot.middleware import get_settings, get_user_repo
from yoink.core.i18n import t


def _keyboard(enabled: bool, lang: str) -> InlineKeyboardMarkup:
    if enabled:
        label = t("common.toggle_off", lang) + "  - disable"
        data = "proxy:off"
    else:
        label = t("common.toggle_on", lang) + "  - enable"
        data = "proxy:on"
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=data)]])


async def _cmd_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    settings = get_settings(context)
    if not settings.proxy_url:
        repo = get_user_repo(context)
        user = await repo.get_or_create(update.effective_user.id)
        await update.message.reply_html(t("proxy.not_configured", user.language))
        return

    repo = get_user_repo(context)
    user = await repo.get_or_create(update.effective_user.id)
    status = t("common.enabled", user.language) if user.proxy_enabled else t("common.disabled", user.language)
    await update.message.reply_html(
        f"{t('proxy.menu_title', user.language)} {status}",
        reply_markup=_keyboard(user.proxy_enabled, user.language),
    )


async def _cb_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query: CallbackQuery | None = update.callback_query
    if not query or not update.effective_user:
        return
    await query.answer()

    enabled = (query.data or "").split(":", 1)[1] == "on"
    repo = get_user_repo(context)
    user = await repo.update(update.effective_user.id, proxy_enabled=enabled)

    text = t("proxy.enabled", user.language) if enabled else t("proxy.disabled", user.language)
    await query.edit_message_text(text, parse_mode="HTML")


def register(app: Application) -> None:
    app.add_handler(CommandHandler("proxy", _cmd_proxy))
    app.add_handler(CallbackQueryHandler(_cb_proxy, pattern=r"^proxy:"))
