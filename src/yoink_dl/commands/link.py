"""
/link [quality] <url>  - extract direct stream URLs without downloading.

Returns video/audio stream URLs with inline buttons for browser/VLC/MPV.
Quality is optional: best (default), 720, 1080, etc.
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

import yt_dlp

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes

from yoink.core.bot.access import AccessPolicy, require_access
from yoink.core.db.models import UserRole
from yoink_dl.bot.middleware import get_settings, get_user_repo
from yoink.core.i18n import t
from yoink_dl.url.normalizer import normalize
from yoink_dl.url.domains import DomainConfig
from yoink_dl.utils.formatting import humantime

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ytdlp_link")

_USAGE = (
    "<b>/link</b>  - get direct stream URLs without downloading\n\n"
    "<b>Usage:</b>\n"
    "  <code>/link https://youtube.com/watch?v=...</code>\n"
    "  <code>/link 720 https://youtube.com/watch?v=...</code>"
)

_QUALITY_MAP = {
    "best": "bestvideo+bestaudio/best",
    "720":  "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
    "1080": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
    "480":  "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
    "360":  "bestvideo[height<=360]+bestaudio/best[height<=360]/best",
    "audio": "bestaudio/best",
}


def _extract_links(url: str, quality: str, cookie_path: str | None) -> dict:
    """Blocking yt-dlp info extraction  - runs in executor."""
    fmt = _QUALITY_MAP.get(quality, _QUALITY_MAP["best"])
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "format": fmt,
        "geo_bypass": True,
        "check_certificate": False,
    }
    if cookie_path:
        opts["cookiefile"] = cookie_path

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info:
            return {"success": False, "error": "No info returned"}

        result: dict = {
            "success": True,
            "title": info.get("title", ""),
            "duration": info.get("duration", 0),
            "video_url": None,
            "audio_url": None,
        }

        # Requested format may be a merged format or split
        fmt_info = info.get("requested_formats") or []
        if fmt_info:
            for f in fmt_info:
                if f.get("vcodec") not in (None, "none"):
                    result["video_url"] = f.get("url")
                if f.get("acodec") not in (None, "none") and f.get("vcodec") in (None, "none"):
                    result["audio_url"] = f.get("url")
        else:
            direct = info.get("url")
            if info.get("vcodec") not in (None, "none"):
                result["video_url"] = direct
            else:
                result["audio_url"] = direct

        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


@require_access(AccessPolicy(
    min_role=UserRole.user,
    check_group_enabled=True,
    check_thread_policy=True,
    silent_deny=True,
))
async def _cmd_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    args = context.args or []
    if not args:
        await update.message.reply_html(_USAGE)
        return

    # Last arg is always the URL; optional first arg is quality
    url = args[-1]
    quality = args[0].lower() if len(args) >= 2 else "best"

    if not url.startswith(("http://", "https://")):
        user_lang = "en"
        if update.effective_user:
            u = await get_user_repo(context).get_or_create(update.effective_user.id)
            user_lang = u.language
        await update.message.reply_html(t("link.no_url", user_lang) + "\n\n" + _USAGE)
        return

    if quality not in _QUALITY_MAP:
        quality = "best"

    settings = get_settings(context)
    repo = get_user_repo(context)
    user = await repo.get_or_create(update.effective_user.id)
    lang = user.language

    domain_cfg = DomainConfig.from_config(settings)
    url = normalize(url, domain_cfg)

    cookie_mgr = context.bot_data.get("cookie_manager")
    cookie_path: str | None = None
    if cookie_mgr:
        p = await cookie_mgr.get_path_for_url(
            user_id=update.effective_user.id,
            url=url,
            global_user_id=context.bot_data["config"].owner_id,
        )
        if p:
            cookie_path = str(p)

    status = await update.message.reply_html(t("link.fetching", lang))

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(_executor, _extract_links, url, quality, cookie_path)

    if not result.get("success"):
        err = result.get("error", "unknown error")
        await status.edit_text(
            t("link.no_url", lang, error=err[:300]),
            parse_mode="HTML",
        )
        return

    title = result["title"] or url
    duration = result.get("duration") or 0
    video_url: str | None = result.get("video_url")
    audio_url: str | None = result.get("audio_url")

    lines = [t("link.title", lang, title=title)]
    if duration:
        lines.append(f"⏱ Duration: <b>{humantime(duration * 1000)}</b>")
    lines.append(f"🎯 Quality: <b>{quality}</b>")

    if video_url:
        lines.append(f"\n🎬 <b>Video stream:</b>")
        lines.append(f"<code>{video_url[:200]}</code>")
    if audio_url:
        lines.append(f"\n🎵 <b>Audio stream:</b>")
        lines.append(f"<code>{audio_url[:200]}</code>")

    # Inline buttons for direct open
    direct = video_url or audio_url
    buttons: list[list[InlineKeyboardButton]] = []
    if direct:
        buttons.append([InlineKeyboardButton(t("link.browser", lang), url=direct)])
        if video_url:
            vlc_ios = f"vlc://{video_url}"
            vlc_android = f"intent:{video_url}#Intent;package=org.videolan.vlc;end"
            mpv = f"mpv://{video_url}"
            buttons.append([
                InlineKeyboardButton(t("link.vlc_ios", lang), url=vlc_ios),
                InlineKeyboardButton(t("link.vlc_android", lang), url=vlc_android),
            ])
            buttons.append([InlineKeyboardButton(t("link.mpv", lang), url=mpv)])

    markup = InlineKeyboardMarkup(buttons) if buttons else None
    await status.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=markup)


def register(app: Application) -> None:
    app.add_handler(CommandHandler("link", _cmd_link))
