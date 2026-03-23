"""
/video, /audio, /image  - force a specific download mode.

Private chat:
  /audio               - sets force_mode, waits for next URL message
  /audio <url>         - immediately download as audio
  /audio 1-5 <url>     - playlist items 1-5

Group chat:
  /video <url>         - download as video (URL required; no waiting state)
  /audio <url>         - download as audio
  /image <url>         - download images via gallery-dl
"""
from __future__ import annotations

import re

from telegram import ForceReply, Update
from telegram.constants import ChatType
from telegram.ext import Application, CommandHandler, ContextTypes

from yoink.core.bot.access import AccessPolicy, require_access
from yoink.core.db.models import UserRole
from yoink_dl.url.extractor import extract_url

FORCE_MODE_KEY = "force_mode"

_RANGE_RE = re.compile(r"^(-?\d+)(?:-(-?\d+))?$")


def _parse_args(context_args: list[str]) -> tuple[str | None, int | None, int | None]:
    """
    Parse command arguments into (url, start, end).

    Accepted patterns:
      <url>            -> (url, None, None)
      <range> <url>    -> (url, start, end)
      <url> <range>    -> (url, start, end)

    Range formats: 1-5, -5 (last 5), 3 (item 3 only).
    """
    if not context_args:
        return None, None, None

    url: str | None = None
    range_token: str | None = None

    for token in context_args:
        if token.startswith(("http://", "https://")):
            url = token
        elif _RANGE_RE.match(token):
            range_token = token

    if url is None:
        return None, None, None

    if range_token is None:
        return url, None, None

    m = _RANGE_RE.match(range_token)
    assert m
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) is not None else None

    if end is None and start >= 0:
        end = start  # single item

    return url, start, end


def _is_group(update: Update) -> bool:
    chat = update.effective_chat
    return chat is not None and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


_USER_POLICY = AccessPolicy(min_role=UserRole.user, silent_deny=True)


@require_access(_USER_POLICY)
async def _cmd_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    url, start, end = _parse_args(context.args or [])
    if not url:
        url = extract_url(update.message)

    if url:
        context.user_data[FORCE_MODE_KEY] = "audio"
        from yoink_dl.url.pipeline import run_download as _run_download
        await _run_download(update, context, url, clip=None, playlist_start=start, playlist_end=end)
        context.user_data.pop(FORCE_MODE_KEY, None)
    elif _is_group(update):
        prompt = await update.message.reply_html(
            "Usage: <code>/audio &lt;url&gt;</code>",
            reply_markup=ForceReply(
                input_field_placeholder="https://...",
                selective=True,
            ),
        )
        context.user_data[FORCE_MODE_KEY] = "audio"
        context.user_data["_group_prompt"] = {
            "prompt_id": prompt.message_id,
            "command_id": update.message.message_id,
            "chat_id": update.message.chat_id,
        }
    else:
        context.user_data[FORCE_MODE_KEY] = "audio"
        await update.message.reply_html(
            "🎵 Send me a URL to extract audio.\n"
            "<i>Tip: <code>/audio 1-5 URL</code> for a playlist range.</i>",
            reply_markup=ForceReply(input_field_placeholder="https://..."),
        )


@require_access(_USER_POLICY)
async def _cmd_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    url, start, end = _parse_args(context.args or [])
    if not url:
        url = extract_url(update.message)

    if url:
        context.user_data.pop(FORCE_MODE_KEY, None)
        from yoink_dl.url.pipeline import run_download as _run_download
        await _run_download(update, context, url, clip=None, playlist_start=start, playlist_end=end)
    elif _is_group(update):
        prompt = await update.message.reply_html(
            "Usage: <code>/video &lt;url&gt;</code>",
            reply_markup=ForceReply(
                input_field_placeholder="https://...",
                selective=True,
            ),
        )
        context.user_data["_group_prompt"] = {
            "prompt_id": prompt.message_id,
            "command_id": update.message.message_id,
            "chat_id": update.message.chat_id,
        }
    else:
        await update.message.reply_html(
            "📹 Send me a URL to download as video.\n"
            "<i>Tip: <code>/video 1-5 URL</code> for a playlist range.</i>",
            reply_markup=ForceReply(input_field_placeholder="https://..."),
        )


@require_access(_USER_POLICY)
async def _cmd_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    url, _, _ = _parse_args(context.args or [])
    if not url:
        url = extract_url(update.message)

    if url:
        context.user_data[FORCE_MODE_KEY] = "gallery"
        from yoink_dl.url.pipeline import run_download as _run_download
        await _run_download(update, context, url, clip=None)
        context.user_data.pop(FORCE_MODE_KEY, None)
    elif _is_group(update):
        prompt = await update.message.reply_html(
            "Usage: <code>/image &lt;url&gt;</code>",
            reply_markup=ForceReply(
                input_field_placeholder="https://...",
                selective=True,
            ),
        )
        context.user_data[FORCE_MODE_KEY] = "gallery"
        context.user_data["_group_prompt"] = {
            "prompt_id": prompt.message_id,
            "command_id": update.message.message_id,
            "chat_id": update.message.chat_id,
        }
    else:
        context.user_data[FORCE_MODE_KEY] = "gallery"
        await update.message.reply_html(
            "🖼️ Send me a URL to download images.",
            reply_markup=ForceReply(input_field_placeholder="https://..."),
        )


def register(app: Application) -> None:
    app.add_handler(CommandHandler("audio", _cmd_audio))
    app.add_handler(CommandHandler("video", _cmd_video))
    app.add_handler(CommandHandler("image", _cmd_image))
