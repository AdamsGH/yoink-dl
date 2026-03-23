"""
/cookie command - manage per-user Netscape cookie files.

Usage:
  /cookie                     - show current cookies
  /cookie token               - generate a token for the browser extension
  /cookie <domain>            - show cookie status for domain
  /cookie del <domain>        - delete cookie for domain
  /cookie clear               - delete all cookies
  Send a .txt document with /cookie in caption - upload cookie file
  /cookie <url-to-txt-file>   - download and store cookie from URL
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from yoink_dl.bot.middleware import get_settings
from yoink_dl.services import cookie_tokens as ct
from yoink_dl.services.cookies import CookieManager, validate_netscape, _domain_from_url

logger = logging.getLogger(__name__)

_MAX_COOKIE_SIZE = 512 * 1024  # 512 KB


def _get_cookie_mgr(context: ContextTypes.DEFAULT_TYPE) -> CookieManager | None:
    return context.bot_data.get("cookie_manager")


async def _fetch_url(url: str) -> str | None:
    """Download text content from a URL, return None on error."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
            if len(r.content) > _MAX_COOKIE_SIZE:
                return None
            return r.text
    except Exception as e:
        logger.warning("Failed to fetch cookie from %s: %s", url, e)
        return None


async def _handle_cookie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    mgr = _get_cookie_mgr(context)
    if not mgr:
        return

    user_id = update.effective_user.id
    args = context.args or []
    msg = update.message

    # Case: document attached (caption may be "/cookie" or "/cookie <domain>")
    if msg.document:
        await _handle_document(msg, user_id, args, mgr)
        return

    # No args - list all cookies
    if not args:
        domains = await mgr.list_domains(user_id)
        if not domains:
            await msg.reply_text("No cookies stored.")
        else:
            lines = "\n".join(f"• <code>{d}</code>" for d in domains)
            await msg.reply_text(f"Stored cookies:\n{lines}", parse_mode=ParseMode.HTML)
        return

    subcmd = args[0].lower()

    # /cookie token - generate a token for the browser extension
    if subcmd == "token":
        settings = get_settings(context)
        bot_url = getattr(settings, "yoink_domain", None)
        token = ct.generate(user_id)
        ttl_min = ct.TTL // 60
        url_hint = f"\n\n<b>Bot URL:</b> <code>https://{bot_url}</code>" if bot_url else ""
        await msg.reply_html(
            f"🔑 <b>Browser Extension Token</b>\n\n"
            f"<code>{token}</code>\n\n"
            f"Paste this into the extension popup, then click <b>Send Cookies</b>.\n"
            f"Valid for <b>{ttl_min} minutes</b>, single-use.{url_hint}",
        )
        return

    # /cookie clear
    if subcmd == "clear":
        n = await mgr.clear(user_id)
        await msg.reply_text(f"Removed {n} cookie(s).")
        return

    # /cookie del <domain>
    if subcmd == "del" and len(args) >= 2:
        domain = args[1].lower().lstrip(".")
        removed = await mgr.delete(user_id, domain)
        if removed:
            await msg.reply_text(f"Cookie for <code>{domain}</code> removed.", parse_mode=ParseMode.HTML)
        else:
            await msg.reply_text(f"No cookie found for <code>{domain}</code>.", parse_mode=ParseMode.HTML)
        return

    # /cookie <url>
    token = args[0]
    parsed = urlparse(token)
    if parsed.scheme in ("http", "https"):
        await msg.reply_text("Downloading cookie file…")
        content = await _fetch_url(token)
        if not content:
            await msg.reply_text("Failed to download or file too large (max 512 KB).")
            return
        domain = _domain_from_url(token) if len(args) < 2 else args[1].lower().lstrip(".")
        await _store_cookie(msg, user_id, domain, content, mgr)
        return

    # /cookie <domain> - show status
    domain = token.lower().lstrip(".")
    content = await mgr.get_content(user_id, domain)
    if content:
        lines = [l for l in content.splitlines() if l and not l.startswith("#")]
        await msg.reply_text(
            f"Cookie for <code>{domain}</code>: {len(lines)} entries.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await msg.reply_text(f"No cookie for <code>{domain}</code>.", parse_mode=ParseMode.HTML)


async def _handle_document(msg: object, user_id: int, args: list, mgr: CookieManager) -> None:
    from telegram import Message
    msg: Message
    doc = msg.document

    if doc.file_size and doc.file_size > _MAX_COOKIE_SIZE:
        await msg.reply_text("File too large (max 512 KB).")
        return

    # Infer domain from filename or explicit arg
    filename = doc.file_name or ""
    if args:
        domain = args[0].lower().lstrip(".")
    else:
        # e.g. "youtube.com.txt" -> "youtube.com"
        stem = Path(filename).stem.lower()
        domain = stem if "." in stem else None

    if not domain:
        await msg.reply_text(
            "Please specify a domain: send document with caption "
            "<code>/cookie youtube.com</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    tg_file = await doc.get_file()
    fd, tmp_str = tempfile.mkstemp(suffix=".txt", prefix="ck_upload_")
    tmp = Path(tmp_str)
    try:
        os.close(fd)
        await tg_file.download_to_drive(str(tmp))
        content = tmp.read_text(encoding="utf-8", errors="replace")
    finally:
        tmp.unlink(missing_ok=True)

    await _store_cookie(msg, user_id, domain, content, mgr)


async def _store_cookie(msg: object, user_id: int, domain: str, content: str, mgr: CookieManager) -> None:
    from telegram import Message
    msg: Message

    if not validate_netscape(content):
        await msg.reply_text(
            "Invalid cookie file - must be Netscape format.\n"
            "Export from browser using an extension like <i>Get cookies.txt LOCALLY</i>.",
            parse_mode=ParseMode.HTML,
        )
        return

    await mgr.store(user_id, domain, content)
    lines = [l for l in content.splitlines() if l and not l.startswith("#")]
    await msg.reply_text(
        f"Saved cookie for <code>{domain}</code> ({len(lines)} entries).",
        parse_mode=ParseMode.HTML,
    )


def register(app: Application) -> None:
    app.add_handler(CommandHandler("cookie", _handle_cookie))
