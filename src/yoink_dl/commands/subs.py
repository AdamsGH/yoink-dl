"""
/subs  - subtitle preferences and standalone subtitle download.

Usage:
  /subs             - open subtitle settings menu
  /subs <url>       - download subtitles only (.srt/.vtt) and send as document

Callback data:
  subs:toggle           - toggle subtitles on/off
  subs:auto:on|off      - toggle auto-generated subs
  subs:lang:<code>      - set subtitle language
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yt_dlp

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from yoink_dl.bot.middleware import get_settings, get_user_repo, is_blocked
from yoink.core.i18n import t
from yoink_dl.storage.repos import UserSettings
from yoink_dl.url.extractor import extract_url

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="subs_dl")

_LANGUAGES = [
    ("en", "🇺🇸 English"),
    ("ru", "🇷🇺 Russian"),
    ("zh", "🇨🇳 Chinese"),
    ("ja", "🇯🇵 Japanese"),
    ("ar", "🇸🇦 Arabic"),
    ("hi", "🇮🇳 Hindi"),
    ("de", "🇩🇪 German"),
    ("fr", "🇫🇷 French"),
    ("es", "🇪🇸 Spanish"),
    ("pt", "🇧🇷 Portuguese"),
]


def _status_text(user: UserSettings) -> str:
    lang = user.language
    lines = []
    lines.append(f"📝 <b>Subtitles</b>")
    lines.append(f"Status: {'<b>ON</b>' if user.subs_enabled else '<b>OFF</b>'}")
    if user.subs_enabled:
        lines.append(f"Language: <code>{user.subs_lang}</code>")
        lines.append(f"Auto-generated: {'ON' if user.subs_auto else 'OFF'}")
    return "\n".join(lines)


def _keyboard(user: UserSettings) -> InlineKeyboardMarkup:
    lang = user.language
    toggle_label = "❌ Disable" if user.subs_enabled else "✅ Enable"
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(toggle_label, callback_data="subs:toggle")],
    ]
    if user.subs_enabled:
        auto_label = f"Auto-generated: {'ON ✓' if user.subs_auto else 'OFF'}"
        rows.append([InlineKeyboardButton(auto_label, callback_data=f"subs:auto:{'off' if user.subs_auto else 'on'}")])
        # Language grid
        lang_buttons = []
        for code, name in _LANGUAGES:
            check = " ✓" if code == user.subs_lang else ""
            lang_buttons.append(InlineKeyboardButton(f"{name}{check}", callback_data=f"subs:lang:{code}"))
        for i in range(0, len(lang_buttons), 2):
            rows.append(lang_buttons[i:i + 2])
    return InlineKeyboardMarkup(rows)


def _do_download_subs(url: str, lang: str, auto: bool, download_dir: Path) -> list[Path]:
    """Blocking yt-dlp subtitle-only download. Runs in thread pool."""
    langs = [lang, f"{lang}-orig"] if lang != "en" else [lang]
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": auto,
        "subtitleslangs": langs,
        "subtitlesformat": "srt/vtt/best",
        "outtmpl": str(download_dir / "%(title).80s.%(ext)s"),
        "geo_bypass": True,
        "check_certificate": False,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

    return [
        f for f in download_dir.glob("*")
        if f.is_file() and f.suffix in (".srt", ".vtt", ".ass", ".ssa")
    ]


async def _download_subs(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str) -> None:
    """Download subtitles for url and send each as a document."""
    user_id = update.effective_user.id  # type: ignore[union-attr]
    repo = get_user_repo(context)
    user = await repo.get_or_create(user_id)

    status = await update.message.reply_html(  # type: ignore[union-attr]
        f"📝 Downloading subtitles…"
    )

    download_dir = Path(tempfile.mkdtemp(prefix="yoink_subs_"))
    loop = asyncio.get_running_loop()
    try:
        files = await loop.run_in_executor(
            _executor,
            _do_download_subs,
            url,
            user.subs_lang or "en",
            user.subs_auto,
            download_dir,
        )
    except Exception as e:
        logger.warning("Subtitle download failed for %s: %s", url, e)
        await status.edit_text("❌ Could not download subtitles for this URL.")
        return

    if not files:
        await status.edit_text(t("subs.not_available", user.language))
        return

    await status.delete()
    for f in sorted(files):
        await update.message.reply_document(  # type: ignore[union-attr]
            document=f.open("rb"),
            filename=f.name,
            caption=f"📝 <code>{f.name}</code>",
            parse_mode=ParseMode.HTML,
        )

    import shutil
    shutil.rmtree(download_dir, ignore_errors=True)


async def _cmd_subs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    if await is_blocked(update.effective_user.id, context):
        return

    # /subs <url>  - standalone subtitle download
    url = extract_url(update.message)
    if url:
        await _download_subs(update, context, url)
        return

    repo = get_user_repo(context)
    user = await repo.get_or_create(update.effective_user.id)
    await update.message.reply_html(_status_text(user), reply_markup=_keyboard(user))


async def _cb_subs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query: CallbackQuery | None = update.callback_query
    if not query or not update.effective_user or not query.data:
        return
    await query.answer()

    repo = get_user_repo(context)
    uid = update.effective_user.id
    parts = query.data.split(":", 2)
    action = parts[1] if len(parts) > 1 else ""

    if action == "toggle":
        user = await repo.get_or_create(uid)
        user = await repo.update(uid, subs_enabled=not user.subs_enabled)

    elif action == "auto" and len(parts) == 3:
        enabled = parts[2] == "on"
        user = await repo.update(uid, subs_auto=enabled)

    elif action == "lang" and len(parts) == 3:
        user = await repo.update(uid, subs_lang=parts[2])

    else:
        return

    await query.edit_message_text(_status_text(user), reply_markup=_keyboard(user), parse_mode="HTML")


def register(app: Application) -> None:
    app.add_handler(CommandHandler("subs", _cmd_subs))
    app.add_handler(CallbackQueryHandler(_cb_subs, pattern=r"^subs:"))
