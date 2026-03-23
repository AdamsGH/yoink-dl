"""
/keyboard  - choose reply keyboard layout shown after downloads.

Layouts:
  OFF    - no reply keyboard
  1x3    - single column, 3 buttons (Format / Audio / Link)
  2x3    - 2x3 grid (default)
  FULL   - full-width buttons

Stored in user.keyboard field.
"""
from __future__ import annotations

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from yoink_dl.bot.middleware import get_user_repo
from yoink.core.i18n import t

_LAYOUTS = ["OFF", "1x3", "2x3", "FULL"]

_DESCRIPTIONS = {
    "OFF":  "No keyboard",
    "1x3":  "Single column",
    "2x3":  "2×3 grid (default)",
    "FULL": "Full-width buttons",
}


def _keyboard(current: str) -> InlineKeyboardMarkup:
    buttons = []
    for layout in _LAYOUTS:
        check = " ✓" if layout == current else ""
        desc = _DESCRIPTIONS[layout]
        buttons.append(InlineKeyboardButton(
            f"{layout}{check}  - {desc}",
            callback_data=f"keyboard:{layout}",
        ))
    rows = [[b] for b in buttons]
    return InlineKeyboardMarkup(rows)


async def _cmd_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    repo = get_user_repo(context)
    user = await repo.get_or_create(update.effective_user.id)

    # Allow direct: /keyboard 2x3
    if context.args:
        arg = context.args[0].upper()
        if arg in _LAYOUTS:
            user = await repo.update(update.effective_user.id, keyboard=arg)
            await update.message.reply_html(
                t("keyboard.set", user.language, mode=arg)
            )
            return

    await update.message.reply_html(
        f"⌨️ <b>Keyboard layout</b>\nCurrent: <code>{user.keyboard}</code>",
        reply_markup=_keyboard(user.keyboard),
    )


async def _cb_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query: CallbackQuery | None = update.callback_query
    if not query or not update.effective_user or not query.data:
        return
    await query.answer()

    layout = query.data.split(":", 1)[1].upper()
    if layout not in _LAYOUTS:
        return

    repo = get_user_repo(context)
    user = await repo.update(update.effective_user.id, keyboard=layout)

    if layout == "OFF":
        text = t("keyboard.hidden", user.language)
    else:
        text = t("keyboard.set", user.language, mode=layout)

    await query.edit_message_text(text, parse_mode="HTML")


def register(app: Application) -> None:
    app.add_handler(CommandHandler("keyboard", _cmd_keyboard))
    app.add_handler(CallbackQueryHandler(_cb_keyboard, pattern=r"^keyboard:"))
