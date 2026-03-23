"""
/nsfw  - NSFW settings for the current user.

Usage:
  /nsfw               - show blur toggle menu
  /nsfw on            - enable blur (spoiler) for NSFW content
  /nsfw off           - disable blur
  /nsfw mark          - mark the next URL you send as NSFW (one-shot)
  /nsfw reload        - (admin) hot-reload NSFW domain/keyword lists from DB
"""
from __future__ import annotations

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from yoink_dl.bot.middleware import get_settings, get_user_repo
from yoink.core.i18n import t


def _keyboard(blur_on: bool, lang: str) -> InlineKeyboardMarkup:
    rows = []
    if blur_on:
        rows.append([InlineKeyboardButton("🔓 Disable blur", callback_data="nsfw:off")])
    else:
        rows.append([InlineKeyboardButton("🔒 Enable blur", callback_data="nsfw:on")])
    rows.append([InlineKeyboardButton("⚠️ Mark next URL as NSFW", callback_data="nsfw:mark")])
    return InlineKeyboardMarkup(rows)


async def _cmd_nsfw(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    repo = get_user_repo(context)
    user = await repo.get_or_create(update.effective_user.id)
    args = context.args or []

    if args:
        arg = args[0].lower()

        if arg in ("on", "off"):
            blur_on = arg == "on"
            await repo.update(update.effective_user.id, nsfw_blur=blur_on)
            text = t("nsfw.blur_on", user.language) if blur_on else t("nsfw.blur_off", user.language)
            await update.message.reply_html(text)
            return

        if arg == "mark":
            context.user_data["force_nsfw"] = True
            await update.message.reply_html(
                "⚠️ <b>Next URL will be treated as NSFW.</b>\n"
                "Send a URL now  - it will be downloaded with spoiler blur if your blur setting is on."
            )
            return

        if arg == "reload":
            settings = get_settings(context)
            if update.effective_user.id != context.bot_data["config"].owner_id:
                await update.message.reply_text("Only the owner can reload NSFW lists.")
                return
            nsfw_checker = context.bot_data.get("nsfw_checker")
            if nsfw_checker:
                counts = await nsfw_checker.reload()
                await update.message.reply_html(
                    f"✅ NSFW lists reloaded: "
                    f"<b>{counts['domains']}</b> domains, "
                    f"<b>{counts['keywords']}</b> keywords"
                )
            return

    status = t("common.enabled", user.language) if user.nsfw_blur else t("common.disabled", user.language)
    await update.message.reply_html(
        f"🔞 <b>NSFW blur:</b> {status}\n\n"
        "When blur is enabled, media from NSFW sources is sent with a spoiler overlay in private chats.\n"
        "In groups, NSFW policy is controlled by the group admin.",
        reply_markup=_keyboard(user.nsfw_blur, user.language),
    )


async def _cb_nsfw(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query: CallbackQuery | None = update.callback_query
    if not query or not update.effective_user:
        return
    await query.answer()
    action = (query.data or "").split(":", 1)[1]

    repo = get_user_repo(context)
    user = await repo.get_or_create(update.effective_user.id)

    if action in ("on", "off"):
        blur_on = action == "on"
        user = await repo.update(update.effective_user.id, nsfw_blur=blur_on)
        text = t("nsfw.blur_on", user.language) if blur_on else t("nsfw.blur_off", user.language)
        await query.edit_message_text(text, parse_mode="HTML")
        return

    if action == "mark":
        context.user_data["force_nsfw"] = True
        await query.edit_message_text(
            "⚠️ <b>Next URL will be treated as NSFW.</b>\nSend a URL now.",
            parse_mode="HTML",
        )
        return


def register(app: Application) -> None:
    app.add_handler(CommandHandler("nsfw", _cmd_nsfw))
    app.add_handler(CallbackQueryHandler(_cb_nsfw, pattern=r"^nsfw:"))
