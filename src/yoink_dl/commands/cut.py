"""
/cut <url>  - interactive clip extraction.

Conversation flow:
  1. /cut <url>               - bot asks for start time
  2. User sends "01:23"       - bot confirms start, asks for end time
  3. User sends "02:45"       - bot shows summary + action buttons
     [✂️ Cut & Download]  [✏️ Change times]  [❌ Cancel]
  4. User taps button         - all intermediate messages deleted, download starts

Alternatively, the full spec can be given inline:
  /cut <url> 01:23 02:45     - skips steps 1-3, downloads immediately
  /cut <url> 01:23 60        - start 01:23, duration 60s

Session stored in context.user_data["cut_session"]:
  {"url", "step", "start_sec", "chat_id", "origin_id", "bot_msg_ids"}
  origin_id:   message_id of the /cut command message (to delete later)
  bot_msg_ids: list of bot message_ids to bulk-delete before download

Pending stored in context.user_data["cut_pending"][token]:
  {"url", "start_sec", "end_sec", "chat_id", "to_delete"}
  to_delete: all message_ids (user + bot) to clean up on go/cancel

Callback data:
  cut:go:<token>      - confirm and download
  cut:edit:<token>    - restart time entry for same URL
  cut:cancel:<token>  - abort
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Literal

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType, ParseMode
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from yoink.core.i18n import t
from yoink_dl.bot.middleware import get_user_repo, is_blocked
from yoink_dl.commands.media import _is_group
from yoink_dl.url.clip import ClipSpec, parse_time
from yoink_dl.url.extractor import extract_url
from yoink_dl.utils.safe_telegram import delete_many

logger = logging.getLogger(__name__)

_SESSION_KEY = "cut_session"
_PENDING_KEY = "cut_pending"
_CB_PREFIX = "cut:"

Step = Literal["start", "end"]


def _fmt(secs: int) -> str:
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _confirm_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✂️ Cut & Download", callback_data=f"{_CB_PREFIX}go:{token}"),
        InlineKeyboardButton("✏️ Change", callback_data=f"{_CB_PREFIX}edit:{token}"),
        InlineKeyboardButton("❌ Cancel", callback_data=f"{_CB_PREFIX}cancel:{token}"),
    ]])


def _parse_url_and_times(args: list[str]) -> tuple[str | None, int | None, int | None]:
    if not args:
        return None, None, None

    url: str | None = None
    time_tokens: list[str] = []

    for token in args:
        if token.startswith(("http://", "https://")):
            url = token
        else:
            time_tokens.append(token)

    if not url:
        return None, None, None

    start: int | None = None
    end: int | None = None

    if len(time_tokens) >= 1:
        try:
            start = parse_time(time_tokens[0])
        except (ValueError, IndexError):
            return url, None, None

    if len(time_tokens) >= 2:
        try:
            val = parse_time(time_tokens[1])
            if ":" not in time_tokens[1] and start is not None and val < start:
                end = start + val
            else:
                end = val
        except (ValueError, IndexError):
            pass

    return url, start, end


async def _cmd_cut(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    if await is_blocked(update.effective_user.id, context):
        return

    url, start, end = _parse_url_and_times(context.args or [])
    if not url:
        url = extract_url(update.message)

    lang = (await get_user_repo(context).get_or_create(update.effective_user.id)).language
    if not url:
        key = "cut.usage_group" if _is_group(update) else "cut.usage_private"
        await update.message.reply_html(t(key, lang))
        return

    # All times inline  - download immediately, no cleanup needed
    if start is not None and end is not None:
        if end <= start:
            await update.message.reply_text(t("cut.end_after_start", lang))
            return
        from yoink_dl.url.pipeline import run_download as _run_download
        await _run_download(update, context, url, ClipSpec(start_sec=start, end_sec=end))
        return

    chat_id = update.message.chat_id
    origin_id = update.message.message_id

    if start is not None:
        prompt = await update.message.reply_html(
            t("cut.prompt_end", lang, start=_fmt(start))
        )
        context.user_data[_SESSION_KEY] = {
            "url": url, "step": "end", "start_sec": start,
            "chat_id": chat_id, "origin_id": origin_id,
            "bot_msg_ids": [prompt.message_id],
        }
        return

    # No times  - open the full interactive menu (ask_menu handles segment editing)
    from yoink_dl.commands.ask_menu import show_menu
    await show_menu(update, context, url)


async def handle_cut_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Handle free-text replies during an interactive cut session.
    Returns True if consumed, False to fall through to url_handler.
    """
    if not update.message or not update.effective_user:
        return False

    session: dict | None = context.user_data.get(_SESSION_KEY)
    if not session:
        return False

    chat_id: int = session["chat_id"]
    if update.message.chat_id != chat_id:
        return False

    text = (update.message.text or "").strip()

    if text.lower() in ("/cancel", "cancel", "отмена"):
        context.user_data.pop(_SESSION_KEY, None)
        to_delete = session.get("bot_msg_ids", []) + [session["origin_id"], update.message.message_id]
        await delete_many(context.bot, chat_id, to_delete)
        return True

    lang = "en"
    if update.effective_user:
        u = await get_user_repo(context).get_or_create(update.effective_user.id)
        lang = u.language

    try:
        value = parse_time(text)
    except (ValueError, TypeError):
        await update.message.reply_html(t("cut.invalid_time", lang))
        return True

    url: str = session["url"]
    step: Step = session["step"]
    bot_msg_ids: list[int] = session.get("bot_msg_ids", [])

    if step == "start":
        prompt = await update.message.reply_html(
            t("cut.prompt_end", lang, start=_fmt(value))
        )
        # Delete user's start message + old bot prompt
        await delete_many(context.bot, chat_id, bot_msg_ids + [update.message.message_id])
        session["step"] = "end"
        session["start_sec"] = value
        session["bot_msg_ids"] = [prompt.message_id]
        return True

    # step == "end"
    start_sec: int = session["start_sec"]
    if value <= start_sec and ":" not in text:
        end_sec = start_sec + value
    else:
        end_sec = value

    if end_sec <= start_sec:
        await update.message.reply_html(
            t("cut.end_before_start_detail", lang, end=_fmt(end_sec), start=_fmt(start_sec))
        )
        return True

    context.user_data.pop(_SESSION_KEY, None)
    token = uuid.uuid4().hex[:12]

    # Delete user's end message + old bot prompt
    await delete_many(context.bot, chat_id, bot_msg_ids + [update.message.message_id])

    duration = end_sec - start_sec
    summary = await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"✂️ <b>Clip summary</b>\n\n"
            f"Start:    <code>{_fmt(start_sec)}</code>\n"
            f"End:      <code>{_fmt(end_sec)}</code>\n"
            f"Duration: <code>{_fmt(duration)}</code>"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=_confirm_keyboard(token),
    )

    context.user_data.setdefault(_PENDING_KEY, {})[token] = {
        "url": url,
        "start_sec": start_sec,
        "end_sec": end_sec,
        "chat_id": chat_id,
        "to_delete": [session["origin_id"], summary.message_id],
    }
    return True


async def _cb_cut(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query: CallbackQuery | None = update.callback_query
    if not query or not query.data or not update.effective_user:
        return
    await query.answer()

    parts = query.data.split(":", 2)
    if len(parts) != 3:
        return
    _, action, token = parts

    pending: dict = context.user_data.get(_PENDING_KEY, {})
    entry = pending.pop(token, None)

    if entry is None:
        await query.edit_message_text("⚠️ Session expired. Send the URL again with /cut.")
        return

    url: str = entry["url"]
    start_sec: int = entry["start_sec"]
    end_sec: int = entry["end_sec"]
    chat_id: int = entry["chat_id"]
    to_delete: list[int] = entry.get("to_delete", [])

    if action == "cancel":
        await delete_many(context.bot, chat_id, to_delete)
        return

    if action == "edit":
        # Delete summary, restart session
        await delete_many(context.bot, chat_id, to_delete)
        prompt = await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"✂️ <b>Cut mode</b>  - enter new times\n"
                f"URL: <code>{url[:60]}{'…' if len(url) > 60 else ''}</code>\n\n"
                "Send <b>start time</b>:\n"
                "<code>01:23</code>  or  <code>83</code> (seconds)"
            ),
            parse_mode=ParseMode.HTML,
        )
        context.user_data[_SESSION_KEY] = {
            "url": url, "step": "start",
            "chat_id": chat_id,
            "origin_id": 0,
            "bot_msg_ids": [prompt.message_id],
        }
        return

    # action == "go"  - fire deletion concurrently with download start
    asyncio.ensure_future(delete_many(context.bot, chat_id, to_delete))

    from yoink_dl.url.pipeline import run_download as _run_download
    await _run_download(
        update, context, url,
        ClipSpec(start_sec=start_sec, end_sec=end_sec),
        target_chat_id=chat_id,
    )


def register(app: Application) -> None:
    app.add_handler(CommandHandler("cut", _cmd_cut))
    app.add_handler(CallbackQueryHandler(_cb_cut, pattern=rf"^{_CB_PREFIX}"))
