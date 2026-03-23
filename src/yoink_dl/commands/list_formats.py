"""
/list <url>  - show all available yt-dlp formats for a URL.

Runs yt-dlp --list-formats and sends the result as a .txt document
(output can be very long). Inline buttons highlight audio/video-only IDs.
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yt_dlp

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from yoink_dl.bot.middleware import get_settings, get_user_repo
from yoink.core.i18n import t
from yoink_dl.storage.repos import UserSettings
from yoink_dl.url.normalizer import normalize
from yoink_dl.url.domains import DomainConfig

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ytdlp_list")

_USAGE = (
    "<b>/list</b>  - show all available formats for a URL\n\n"
    "<b>Usage:</b> <code>/list https://youtube.com/watch?v=...</code>"
)


def _run_list_formats(url: str, cookie_path: str | None) -> tuple[bool, str]:
    """Blocking yt-dlp call  - runs in thread executor."""
    buf: list[str] = []

    class _ListLogger:
        def debug(self, msg: str) -> None:
            buf.append(msg)
        def warning(self, msg: str) -> None:
            buf.append(f"[warn] {msg}")
        def error(self, msg: str) -> None:
            buf.append(f"[error] {msg}")

    opts: dict = {
        "quiet": True,
        "no_warnings": False,
        "listformats": True,
        "logger": _ListLogger(),
        "geo_bypass": True,
        "check_certificate": False,
    }
    if cookie_path:
        opts["cookiefile"] = cookie_path

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=False)
        output = "\n".join(buf)
        return True, output
    except Exception as e:
        return False, str(e)


def _parse_format_ids(output: str) -> tuple[list[str], list[str]]:
    """Extract audio-only and video-only format IDs from yt-dlp list output."""
    audio_ids: list[str] = []
    video_ids: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("ID") or stripped.startswith("-"):
            continue
        parts = stripped.split()
        if not parts:
            continue
        fmt_id = parts[0]
        lower = line.lower()
        if "audio only" in lower:
            audio_ids.append(fmt_id)
        elif "video only" in lower:
            video_ids.append(fmt_id)
    return audio_ids, video_ids


async def _cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    if not context.args:
        await update.message.reply_html(_USAGE)
        return

    url = context.args[-1]
    if not url.startswith(("http://", "https://")):
        user_lang = "en"
        if update.effective_user:
            u = await get_user_repo(context).get_or_create(update.effective_user.id)
            user_lang = u.language
        await update.message.reply_html(t("list_formats.no_url", user_lang))
        return

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

    status = await update.message.reply_html(t("list_formats.fetching", lang))

    loop = asyncio.get_running_loop()
    success, output = await loop.run_in_executor(_executor, _run_list_formats, url, cookie_path)

    if not success:
        await status.edit_text(t("list_formats.fetch_error", lang, error=output[:500]), parse_mode="HTML")
        return

    audio_ids, video_ids = _parse_format_ids(output)

    # Build summary caption
    caption_lines = [t("list_formats.title", lang, title=url)]
    if video_ids:
        ids = " ".join(f"<code>{i}</code>" for i in video_ids[:10])
        caption_lines.append(f"🎬 Video-only IDs: {ids}")
    if audio_ids:
        ids = " ".join(f"<code>{i}</code>" for i in audio_ids[:10])
        caption_lines.append(f"🎵 Audio-only IDs: {ids}")
    caption_lines.append(t("list_formats.hint", lang, id=audio_ids[0] if audio_ids else "140"))
    caption = "\n".join(caption_lines)

    # Write to temp file and send as document
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8", prefix="formats_"
    ) as f:
        f.write(f"Formats for: {url}\n")
        f.write("=" * 60 + "\n\n")
        f.write(output)
        f.write("\n\n" + "=" * 60 + "\n")
        f.write("Usage: /format id <format_id> to download specific format\n")
        tmp_path = f.name

    try:
        await status.delete()
        await update.message.reply_document(
            document=open(tmp_path, "rb"),
            filename=f"formats_{update.effective_user.id}.txt",
            caption=caption,
            parse_mode="HTML",
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def register(app: Application) -> None:
    app.add_handler(CommandHandler("list", _cmd_list))
