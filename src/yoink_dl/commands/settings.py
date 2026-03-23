"""/settings - overview of all user preferences with quick-access buttons."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes

from yoink.core.bot.access import AccessPolicy, require_access
from yoink.core.db.models import UserRole
from yoink_dl.bot.middleware import get_user_repo
from yoink_dl.utils.formatting import format_size
from yoink.core.i18n.loader import t


def _yn(value: bool, lang: str) -> str:
    return t("common.toggle_on", lang) if value else t("common.toggle_off", lang)


@require_access(AccessPolicy(min_role=UserRole.user, scopes=["private"], silent_deny=True))
async def _cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    repo = get_user_repo(context)
    user = await repo.get_or_create(update.effective_user.id)
    lang = user.language
    text = t(
        "settings.title",
        lang,
        language=lang.upper(),
        quality=user.quality,
        codec=user.codec,
        container=user.container,
        proxy=_yn(user.proxy_enabled, lang),
        keyboard=user.keyboard,
        subs=_yn(user.subs_enabled, lang),
        split_size=format_size(user.split_size),
        nsfw_blur=_yn(user.nsfw_blur, lang),
        mediainfo=_yn(user.mediainfo, lang),
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎬 Format",   callback_data="settings:goto:format"),
            InlineKeyboardButton("🌐 Language", callback_data="settings:goto:lang"),
        ],
        [
            InlineKeyboardButton("🔀 Proxy",  callback_data="settings:goto:proxy"),
            InlineKeyboardButton("✂️ Split",  callback_data="settings:goto:split"),
        ],
        [
            InlineKeyboardButton("📝 Subs",   callback_data="settings:goto:subs"),
            InlineKeyboardButton("🔞 NSFW",   callback_data="settings:goto:nsfw"),
        ],
        [
            InlineKeyboardButton("ℹ️ Mediainfo", callback_data="settings:goto:mediainfo"),
            InlineKeyboardButton("⌨️ Keyboard",  callback_data="settings:goto:keyboard"),
        ],
        [
            InlineKeyboardButton("🔧 Args",    callback_data="settings:goto:args"),
            InlineKeyboardButton("🍪 Cookies", callback_data="settings:goto:cookie"),
        ],
    ])
    await update.message.reply_html(text, reply_markup=keyboard)


async def _cb_settings_goto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delegate settings:goto:* callbacks to the relevant command."""
    query = update.callback_query
    if not query:
        return
    await query.answer()
    target = (query.data or "").split(":")[-1]
    # Simulate a command message by dispatching to the relevant handler
    handlers = {
        "format":    "format",
        "lang":      "lang",
        "proxy":     "proxy",
        "split":     "split",
        "subs":      "subs",
        "nsfw":      "nsfw",
        "mediainfo": "mediainfo",
        "keyboard":  "keyboard",
        "args":      "args",
        "cookie":    "cookie",
    }
    cmd = handlers.get(target)
    if cmd and query.message:
        lang = "en"
        if update.effective_user:
            user = await get_user_repo(context).get_or_create(update.effective_user.id)
            lang = user.language
        await query.message.reply_html(t("settings.use_command", lang, command=cmd))


def register(app: Application) -> None:
    from telegram.ext import CallbackQueryHandler, filters
    app.add_handler(CommandHandler("settings", _cmd_settings, filters=filters.ChatType.PRIVATE))
    app.add_handler(CallbackQueryHandler(_cb_settings_goto, pattern=r"^settings:goto:"))
