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

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import Application, CommandHandler, ContextTypes

from yoink.core.bot.access import AccessPolicy, require_access
from yoink.core.db.models import UserRole
from yoink.core.i18n import t
from yoink_dl.bot.middleware import get_user_repo
from yoink_dl.url.clip import ClipSpec, parse_clip_spec
from yoink_dl.url.extractor import extract_url

FORCE_MODE_KEY = "force_mode"

_RANGE_RE = re.compile(r"^(-?\d+)(?:-(-?\d+))?$")


def _looks_like_clip(url: str, tokens: list[str]) -> bool:
    """Heuristic: clip wins over playlist range when URL has a start marker or a
    HH:MM token is present. Prevents `/video 5 URL` from being misread as
    `clip=5s` and `/video URL?t=301 5:10` from being misread as playlist range.
    """
    from yoink_dl.url.clip import extract_t_param

    if extract_t_param(url) is not None:
        return True
    return any(":" in tok for tok in tokens)


def _parse_args(context_args: list[str]) -> tuple[str | None, int | None, int | None]:
    """
    Parse command arguments into (url, start, end).

    Accepted patterns:
      <url>            -> (url, None, None)
      <range> <url>    -> (url, start, end)
      <url> <range>    -> (url, start, end)

    Range formats: 1-5, -5 (last 5), 3 (item 3 only).

    Playlist range is suppressed when the args look like a clip spec (URL has
    ?t= or any token contains ':'); clip parsing then runs in the caller.
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

    non_url = [tok for tok in context_args if tok is not url]
    if _looks_like_clip(url, non_url):
        return url, None, None

    if range_token is None:
        return url, None, None

    m = _RANGE_RE.match(range_token)
    assert m
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) is not None else None

    if end is None and start >= 0:
        end = start  # single item

    return url, start, end


async def _parse_clip(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
) -> tuple[ClipSpec | None, bool]:
    """Parse a clip spec from the original message text.

    Returns (clip, ok). `ok` is False when the user typed an invalid spec and
    an error reply was sent; the caller should bail out.
    """
    msg = update.message
    if msg is None or not msg.text:
        return None, True
    try:
        return parse_clip_spec(url, msg.text), True
    except ValueError as e:
        lang = "en"
        if update.effective_user:
            u = await get_user_repo(context).get_or_create(update.effective_user.id)
            lang = u.language
        await msg.reply_text(t("url_handler.invalid_time", lang, error=e))
        return None, False


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

    if context.user_data is None:
        return
    if url:
        clip, ok = await _parse_clip(update, context, url)
        if not ok:
            return
        context.user_data[FORCE_MODE_KEY] = "audio"
        from yoink_dl.url.pipeline import run_download as _run_download
        await _run_download(update, context, url, clip=clip, playlist_start=start, playlist_end=end)
        context.user_data.pop(FORCE_MODE_KEY, None)
    elif _is_group(update):
        await update.message.reply_html("Usage: <code>/audio &lt;url&gt;</code>")
        context.user_data[FORCE_MODE_KEY] = "audio"
    else:
        context.user_data[FORCE_MODE_KEY] = "audio"
        await update.message.reply_html(
            "🎵 Send me a URL to extract audio.\n"
            "<i>Tip: <code>/audio 1-5 URL</code> for a playlist range.</i>",
        )


@require_access(_USER_POLICY)
async def _cmd_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    url, start, end = _parse_args(context.args or [])
    if not url:
        url = extract_url(update.message)

    if context.user_data is None:
        return
    if url:
        clip, ok = await _parse_clip(update, context, url)
        if not ok:
            return
        context.user_data.pop(FORCE_MODE_KEY, None)
        from yoink_dl.url.pipeline import run_download as _run_download
        await _run_download(update, context, url, clip=clip, playlist_start=start, playlist_end=end)
    elif _is_group(update):
        await update.message.reply_html("Usage: <code>/video &lt;url&gt;</code>")
    else:
        await update.message.reply_html(
            "📹 Send me a URL to download as video.\n"
            "<i>Tip: <code>/video 1-5 URL</code> for a playlist range.</i>",
        )


@require_access(_USER_POLICY)
async def _cmd_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    url, _, _ = _parse_args(context.args or [])
    if not url:
        url = extract_url(update.message)

    if context.user_data is None:
        return
    if url:
        context.user_data[FORCE_MODE_KEY] = "gallery"
        from yoink_dl.url.pipeline import run_download as _run_download
        await _run_download(update, context, url, clip=None)
        context.user_data.pop(FORCE_MODE_KEY, None)
    elif _is_group(update):
        await update.message.reply_html("Usage: <code>/image &lt;url&gt;</code>")
        context.user_data[FORCE_MODE_KEY] = "gallery"
    else:
        context.user_data[FORCE_MODE_KEY] = "gallery"
        await update.message.reply_html(
            "🖼️ Send me a URL to download images.",
        )


def register(app: Application) -> None:
    app.add_handler(CommandHandler("audio", _cmd_audio))
    app.add_handler(CommandHandler("video", _cmd_video))
    app.add_handler(CommandHandler("image", _cmd_image))
