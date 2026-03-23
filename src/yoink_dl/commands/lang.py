"""
/lang  - language selection with inline keyboard.
"""
from __future__ import annotations

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from yoink_dl.bot.middleware import get_user_repo
from yoink.core.i18n import SUPPORTED, t


def _keyboard(current: str) -> InlineKeyboardMarkup:
    buttons = []
    for code in sorted(SUPPORTED):
        label = t(f"lang.buttons.{code}", current)
        check = " ✓" if code == current else ""
        buttons.append(InlineKeyboardButton(f"{label}{check}", callback_data=f"lang:{code}"))
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(rows)


async def _cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    repo = get_user_repo(context)
    user = await repo.get_or_create(update.effective_user.id)
    await update.message.reply_html(
        t("lang.choose", user.language),
        reply_markup=_keyboard(user.language),
    )


async def _cb_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query: CallbackQuery | None = update.callback_query
    if not query or not update.effective_user:
        return
    await query.answer()

    lang_code = (query.data or "").split(":", 1)[1]
    if lang_code not in SUPPORTED:
        return

    repo = get_user_repo(context)
    await repo.update(update.effective_user.id, language=lang_code)

    await query.edit_message_text(
        t("lang.set", lang_code, lang=t(f"lang.buttons.{lang_code}", lang_code)),
        reply_markup=None,
        parse_mode="HTML",
    )


def register(app: Application) -> None:
    app.add_handler(CommandHandler("lang", _cmd_lang))
    app.add_handler(CallbackQueryHandler(_cb_lang, pattern=r"^lang:"))
