"""
/split  - set max file size before bot splits into parts.
"""
from __future__ import annotations

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from yoink_dl.bot.middleware import get_user_repo
from yoink.core.i18n import t
from yoink_dl.utils.formatting import format_size

_PRESETS: list[tuple[str, int]] = [
    ("500mb",   500 * 1024 * 1024),
    ("1gb",     1024 * 1024 * 1024),
    ("1_5gb",   1536 * 1024 * 1024),
    ("2gb",     2_043_000_000),   # default  - Telegram bot API limit
]


def _keyboard(current: int, lang: str) -> InlineKeyboardMarkup:
    buttons = []
    for key, size in _PRESETS:
        label = t(f"split.buttons.{key}", lang)
        check = " ✓" if current == size else ""
        buttons.append(InlineKeyboardButton(f"{label}{check}", callback_data=f"split:{size}"))
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(rows)


async def _cmd_split(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    repo = get_user_repo(context)
    user = await repo.get_or_create(update.effective_user.id)
    await update.message.reply_html(
        t("split.choose", user.language),
        reply_markup=_keyboard(user.split_size, user.language),
    )


async def _cb_split(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query: CallbackQuery | None = update.callback_query
    if not query or not update.effective_user:
        return
    await query.answer()

    try:
        size = int((query.data or "").split(":", 1)[1])
    except (ValueError, IndexError):
        return

    repo = get_user_repo(context)
    user = await repo.update(update.effective_user.id, split_size=size)

    await query.edit_message_text(
        t("split.set", user.language, size=format_size(size)),
        parse_mode="HTML",
    )


def register(app: Application) -> None:
    app.add_handler(CommandHandler("split", _cmd_split))
    app.add_handler(CallbackQueryHandler(_cb_split, pattern=r"^split:\d+$"))
