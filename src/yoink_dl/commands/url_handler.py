"""
URL message handlers. Wires PTB message handlers to the download pipeline.

Download logic lives in yoink_dl.url.pipeline.
"""
from __future__ import annotations

import logging
import time

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from yoink.core.bot.access import AccessPolicy, require_access
from yoink.core.db.models import UserRole
from yoink.core.i18n import t
from yoink_dl.bot.middleware import get_user_repo
from yoink_dl.url.clip import ClipSpec, extract_t_param, parse_clip_spec
from yoink_dl.url.extractor import extract_url
from yoink_dl.url.pipeline import run_download
from yoink_dl.utils.safe_telegram import delete_many

logger = logging.getLogger(__name__)

_AWAITING_CLIP_END = "awaiting_clip_end"

_URL_POLICY = AccessPolicy(
    min_role=UserRole.user,
    check_group_enabled=True,
    check_thread_policy=True,
    silent_deny=True,
)


def _get_thread_id(update: Update) -> int | None:
    msg = update.message
    if msg and msg.is_topic_message:
        return msg.message_thread_id
    return None


def _fmt_sec(secs: int) -> str:
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


@require_access(_URL_POLICY)
async def _handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    user_id = update.effective_user.id

    msg_age = time.time() - update.message.date.timestamp()
    if msg_age > 30:
        logger.debug("Dropping stale message (age=%.0fs) from user %d", msg_age, user_id)
        return

    if context.user_data.get(_AWAITING_CLIP_END):
        await _handle_clip_end_time(update, context)
        return

    from yoink_dl.commands.cut import handle_cut_input as _cut_input
    if await _cut_input(update, context):
        return

    from yoink_dl.commands.ask_menu import handle_time_input as _am_input
    if await _am_input(update, context):
        return

    if not _has_bare_url(update.message):
        return

    url = extract_url(update.message)
    if not url:
        return

    text = update.message.text or ""

    lang = "en"
    user_settings_lang = await get_user_repo(context).get_or_create(update.effective_user.id)
    lang = user_settings_lang.language

    try:
        clip = parse_clip_spec(url, text)
    except ValueError as e:
        await update.message.reply_text(t("url_handler.invalid_time", lang, error=e))
        return

    if clip is None:
        t_sec = extract_t_param(url)
        if t_sec is not None:
            context.user_data[_AWAITING_CLIP_END] = {"url": url, "start_sec": t_sec}
            await update.message.reply_text(
                t("url_handler.clip_end_prompt", lang, start=_fmt_sec(t_sec)),
                parse_mode=ParseMode.HTML,
            )
            return

    user_repo = get_user_repo(context)
    user_settings_pre = await user_repo.get_or_create(user_id)
    if user_settings_pre.quality == "ask" and not context.user_data.get("force_mode"):
        from yoink_dl.commands.ask_menu import show_menu as _show_menu
        await _show_menu(update, context, url)
        return

    await run_download(update, context, url, clip)


async def _handle_clip_end_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.user_data.pop(_AWAITING_CLIP_END)
    url: str = data["url"]
    start_sec: int = data["start_sec"]
    text = (update.message.text or "").strip()  # type: ignore[union-attr]

    lang = "en"
    if update.effective_user:
        u = await get_user_repo(context).get_or_create(update.effective_user.id)
        lang = u.language

    try:
        from yoink_dl.url.clip import parse_time
        end_sec = parse_time(text) if ":" in text else start_sec + int(text)
    except (ValueError, TypeError):
        await update.message.reply_text(t("url_handler.clip_invalid_time", lang))  # type: ignore[union-attr]
        return

    if end_sec <= start_sec:
        await update.message.reply_text(t("url_handler.clip_end_before_start", lang))  # type: ignore[union-attr]
        return

    await run_download(update, context, url, ClipSpec(start_sec=start_sec, end_sec=end_sec))


def _has_bare_url(msg: object) -> bool:
    """Return True if the message contains a bare URL entity (not TEXT_LINK).

    Music cards produced by yoink-music only contain TEXT_LINK entities
    (hyperlinked platform names). A downloadable URL pasted by a user always
    appears as a bare URL entity. This lets us skip music cards without
    maintaining a list of music CDN/platform domains.
    """
    from telegram import Message as TGMessage
    if not isinstance(msg, TGMessage):
        return False
    return any(
        e.type.name == "URL"
        for e in (msg.entities or [])
    )


@require_access(_URL_POLICY)
async def _handle_inline_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle URL messages inserted via inline mode in group chats."""
    msg = update.effective_message
    if not msg or not msg.via_bot:
        return
    if msg.via_bot.id != context.bot.id:
        return
    if not _has_bare_url(msg):
        return
    await _handle_url(update, context)


@require_access(_URL_POLICY)
async def _handle_group_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle URL replies to bot ForceReply prompts in group chats."""
    if not update.message or not update.effective_user:
        return
    reply = update.message.reply_to_message
    if not reply or not reply.from_user or not reply.from_user.is_bot:
        return
    me = await context.bot.get_me()
    if reply.from_user.id != me.id:
        return

    url = extract_url(update.message)
    if not url:
        return

    chat_id = update.message.chat_id
    ids_to_delete: list[int] = [update.message.message_id]
    prompt_info: dict | None = context.user_data.pop("_group_prompt", None)
    if prompt_info and prompt_info.get("chat_id") == chat_id:
        if prompt_info.get("prompt_id"):
            ids_to_delete.append(prompt_info["prompt_id"])
        if prompt_info.get("command_id"):
            ids_to_delete.append(prompt_info["command_id"])

    await delete_many(context.bot, chat_id, ids_to_delete)
    await run_download(update, context, url, clip=None)


def register(app: Application) -> None:
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, _handle_url)
    )
    _groups = filters.ChatType.GROUP | filters.ChatType.SUPERGROUP
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.REPLY & _groups,
            _handle_group_reply,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.ViaBot(allow_empty=True) & _groups,
            _handle_inline_group,
        ),
        group=1,
    )
