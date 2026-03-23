"""
/clean  - selectively reset user data back to defaults.

Each button resets one specific setting. "Reset all" resets everything.
No confirmation dialog  - instant action with toast via callback answer().
"""
from __future__ import annotations

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from yoink_dl.bot.middleware import get_user_repo
from yoink.core.i18n import t

_ITEMS = [
    ("format",    "🎬 Format & quality"),
    ("lang",      "🌐 Language"),
    ("proxy",     "🔀 Proxy"),
    ("split",     "✂️ Split size"),
    ("subs",      "📝 Subtitles"),
    ("nsfw",      "🔞 NSFW blur"),
    ("mediainfo", "ℹ️ Mediainfo"),
    ("keyboard",  "⌨️ Keyboard"),
    ("args",      "🔧 Custom args"),
]

_DEFAULTS = {
    "format":    {"quality": "best", "codec": "avc1", "container": "mp4"},
    "lang":      {"language": "en"},
    "proxy":     {"proxy_enabled": False},
    "split":     {"split_size": 2_043_000_000},
    "subs":      {"subs_enabled": False, "subs_auto": False, "subs_always_ask": False, "subs_lang": "en"},
    "nsfw":      {"nsfw_blur": True},
    "mediainfo": {"mediainfo": False},
    "keyboard":  {"keyboard": "2x3"},
    "args":      {"args_json": {}},
}


def _keyboard() -> InlineKeyboardMarkup:
    rows = []
    for key, label in _ITEMS:
        rows.append([InlineKeyboardButton(label, callback_data=f"clean:{key}")])
    rows.append([InlineKeyboardButton("🧹 Reset everything", callback_data="clean:all", style="destructive")])
    return InlineKeyboardMarkup(rows)


async def _cmd_clean(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    repo = get_user_repo(context)
    user = await repo.get_or_create(update.effective_user.id)
    await update.message.reply_html(
        "🧹 <b>Clean data</b>\n\nChoose what to reset to defaults:",
        reply_markup=_keyboard(),
    )


async def _cb_clean(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query: CallbackQuery | None = update.callback_query
    if not query or not update.effective_user or not query.data:
        return

    key = query.data.split(":", 1)[1]
    repo = get_user_repo(context)
    uid = update.effective_user.id

    if key == "all":
        all_defaults: dict = {}
        for d in _DEFAULTS.values():
            all_defaults.update(d)
        user = await repo.update(uid, **all_defaults)
        await query.answer(t("clean.all_done", user.language), show_alert=False)
        await query.edit_message_text(t("clean.all_done", user.language), parse_mode="HTML")
        return

    if key in _DEFAULTS:
        user = await repo.update(uid, **_DEFAULTS[key])
        label = next(l for k, l in _ITEMS if k == key)
        msg = t("clean.done", user.language, what=label)
        await query.answer(msg, show_alert=False)
        # Keep the menu visible after resetting individual item
        await query.edit_message_reply_markup(_keyboard())
    else:
        await query.answer()


def register(app: Application) -> None:
    app.add_handler(CommandHandler("clean", _cmd_clean))
    app.add_handler(CallbackQueryHandler(_cb_clean, pattern=r"^clean:"))
