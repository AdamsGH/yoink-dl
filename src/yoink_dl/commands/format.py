"""
/format  - choose video quality, codec, container.

Callback data scheme:
  fmt:q:<quality>       - set quality preset
  fmt:codec:<codec>     - set codec preference
  fmt:cont:<container>  - set container preference
  fmt:menu              - back to main format menu
"""
from __future__ import annotations

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from yoink_dl.bot.middleware import get_user_repo
from yoink.core.i18n import t
from yoink_dl.storage.repos import UserSettings

_QUALITIES = ["2160", "1440", "1080", "720", "480", "360", "best", "ask"]
_CODECS = ["avc1", "av01", "vp09"]
_CONTAINERS = ["mp4", "mkv"]


def _quality_label(q: str, lang: str) -> str:
    if q == "best":
        return t("format.buttons.best", lang)
    if q == "ask":
        return t("format.buttons.ask", lang)
    return f"{q}p"


def _codec_label(c: str, lang: str) -> str:
    mapping = {
        "avc1": t("format.buttons.codec_avc", lang),
        "av01": t("format.buttons.codec_av1", lang),
        "vp09": t("format.buttons.codec_vp9", lang),
    }
    return mapping.get(c, c)


def _container_label(c: str, lang: str) -> str:
    mapping = {
        "mp4": t("format.buttons.container_mp4", lang),
        "mkv": t("format.buttons.container_mkv", lang),
    }
    return mapping.get(c, c.upper())


def _main_menu(user: UserSettings) -> InlineKeyboardMarkup:
    lang = user.language
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"🎯 Quality: {_quality_label(user.quality, lang)}",
                callback_data="fmt:q:_menu",
            )
        ],
        [
            InlineKeyboardButton(
                f"🎞 Codec: {_codec_label(user.codec, lang)}",
                callback_data="fmt:codec:_menu",
            ),
            InlineKeyboardButton(
                f"📦 Container: {_container_label(user.container, lang)}",
                callback_data="fmt:cont:_menu",
            ),
        ],
    ])


def _quality_menu(current: str, lang: str) -> InlineKeyboardMarkup:
    buttons = []
    for q in _QUALITIES:
        check = " ✓" if q == current else ""
        buttons.append(InlineKeyboardButton(
            f"{_quality_label(q, lang)}{check}", callback_data=f"fmt:q:{q}"
        ))
    rows = [buttons[i:i + 4] for i in range(0, len(buttons), 4)]
    rows.append([InlineKeyboardButton(f"‹ {t('common.back', lang)}", callback_data="fmt:menu")])
    return InlineKeyboardMarkup(rows)


def _codec_menu(current: str, lang: str) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            f"{_codec_label(c, lang)}{' ✓' if c == current else ''}",
            callback_data=f"fmt:codec:{c}",
        )
        for c in _CODECS
    ]
    return InlineKeyboardMarkup([
        buttons,
        [InlineKeyboardButton(f"‹ {t('common.back', lang)}", callback_data="fmt:menu")],
    ])


def _container_menu(current: str, lang: str) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            f"{_container_label(c, lang)}{' ✓' if c == current else ''}",
            callback_data=f"fmt:cont:{c}",
        )
        for c in _CONTAINERS
    ]
    return InlineKeyboardMarkup([
        buttons,
        [InlineKeyboardButton(f"‹ {t('common.back', lang)}", callback_data="fmt:menu")],
    ])


def _status_text(user: UserSettings) -> str:
    return t(
        "format.current",
        user.language,
        quality=_quality_label(user.quality, user.language),
        codec=_codec_label(user.codec, user.language),
        container=_container_label(user.container, user.language),
    )


async def _cmd_format(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    repo = get_user_repo(context)
    user = await repo.get_or_create(update.effective_user.id)
    await update.message.reply_html(_status_text(user), reply_markup=_main_menu(user))


async def _cb_format(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query: CallbackQuery | None = update.callback_query
    if not query or not update.effective_user or not query.data:
        return
    await query.answer()

    repo = get_user_repo(context)
    uid = update.effective_user.id
    parts = query.data.split(":", 2)  # fmt : <type> : <value>

    if len(parts) < 3:
        return

    _, kind, value = parts

    if kind == "menu" or value == "_menu":
        user = await repo.get_or_create(uid)
        if value == "_menu" and kind == "q":
            await query.edit_message_reply_markup(_quality_menu(user.quality, user.language))
        elif value == "_menu" and kind == "codec":
            await query.edit_message_reply_markup(_codec_menu(user.codec, user.language))
        elif value == "_menu" and kind == "cont":
            await query.edit_message_reply_markup(_container_menu(user.container, user.language))
        else:
            await query.edit_message_text(_status_text(user), reply_markup=_main_menu(user), parse_mode="HTML")
        return

    if kind == "q" and value in _QUALITIES:
        user = await repo.update(uid, quality=value)
        if value == "ask":
            msg = t("format.ask_mode", user.language)
        else:
            msg = t("format.set_quality", user.language, quality=_quality_label(value, user.language))
        await query.edit_message_text(msg, reply_markup=_main_menu(user), parse_mode="HTML")

    elif kind == "codec" and value in _CODECS:
        user = await repo.update(uid, codec=value)
        await query.edit_message_text(
            t("format.set_codec", user.language, codec=_codec_label(value, user.language)),
            reply_markup=_main_menu(user),
            parse_mode="HTML",
        )

    elif kind == "cont" and value in _CONTAINERS:
        user = await repo.update(uid, container=value)
        await query.edit_message_text(
            t("format.set_container", user.language, container=_container_label(value, user.language)),
            reply_markup=_main_menu(user),
            parse_mode="HTML",
        )


def register(app: Application) -> None:
    app.add_handler(CommandHandler("format", _cmd_format))
    app.add_handler(CallbackQueryHandler(_cb_format, pattern=r"^fmt:"))
