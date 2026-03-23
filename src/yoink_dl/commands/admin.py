"""DL plugin admin commands: /uncache, /reload_cache, /get_log, /usage.

General admin commands (block/unblock/ban_time/broadcast/runtime) live in
yoink.core.bot.admin and are registered by core regardless of active plugins.

Usage:
  /uncache <url>
  /reload_cache
  /get_log <user_id> [limit]
  /usage [user_id]
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from yoink.core.bot.access import AccessPolicy, require_access
from yoink.core.db.models import UserRole
from yoink.core.i18n import t
from yoink_dl.bot.middleware import get_session_factory, get_settings, get_user_repo
from yoink_dl.storage.models import DownloadLog
from yoink_dl.utils.formatting import format_size

logger = logging.getLogger(__name__)

_ADMIN_POLICY = AccessPolicy(min_role=UserRole.admin, silent_deny=True)


@require_access(_ADMIN_POLICY)
async def _cmd_uncache(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    args = context.args or []
    if not args:
        await update.message.reply_html(
            "Usage: <code>/uncache &lt;url&gt;</code>"
        )
        return
    url = args[0]
    file_cache = context.bot_data.get("file_cache")
    if not file_cache:
        await update.message.reply_text("Cache not available.")
        return

    from yoink_dl.storage.repos import make_cache_key
    from yoink_dl.url.normalizer import normalize
    from yoink_dl.url.domains import DomainConfig

    settings = get_settings(context)
    domain_cfg = DomainConfig.from_config(settings)
    normalized = normalize(url, domain_cfg)
    key = make_cache_key(normalized)
    removed = await file_cache.delete(key)

    if removed:
        await update.message.reply_html(f"✅ Cache cleared for:\n<code>{url}</code>")
    else:
        await update.message.reply_html(f"⚠️ No cache entry found for:\n<code>{url}</code>")


@require_access(_ADMIN_POLICY)
async def _cmd_reload_cache(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    file_cache = context.bot_data.get("file_cache")
    if not file_cache:
        await update.message.reply_text("Cache not available.")
        return
    await update.message.reply_html(t("admin.cache_reloaded", "en"))


@require_access(_ADMIN_POLICY)
async def _cmd_get_log(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    args = context.args or []
    if not args or not args[0].isdigit():
        await update.message.reply_html(
            "Usage: <code>/get_log &lt;user_id&gt; [limit]</code>"
        )
        return

    target_id = int(args[0])
    limit = int(args[1]) if len(args) > 1 and args[1].isdigit() else 10
    limit = min(limit, 50)

    session_factory = get_session_factory(context)
    async with session_factory() as session:
        result = await session.execute(
            select(DownloadLog)
            .where(DownloadLog.user_id == target_id)
            .order_by(DownloadLog.created_at.desc())
            .limit(limit)
        )
        logs = result.scalars().all()

    if not logs:
        await update.message.reply_html(
            t("admin.no_logs", "en", user_id=target_id)
        )
        return

    lines = [t("admin.logs_title", "en", user_id=target_id)]
    for log in logs:
        ts = log.created_at.strftime("%Y-%m-%d %H:%M")
        size = format_size(log.file_size) if log.file_size else "?"
        title = (log.title or log.url or "")[:60]
        status_icon = "✅" if log.status == "ok" else "❌"
        lines.append(f"{status_icon} <code>{ts}</code> {size}\n   {title}")

    text = "\n\n".join(lines)
    for chunk in [text[i : i + 4000] for i in range(0, len(text), 4000)]:
        await update.message.reply_html(chunk)


@require_access(_ADMIN_POLICY)
async def _cmd_usage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    args = context.args or []
    target_id = (
        int(args[0])
        if args and args[0].isdigit()
        else (update.effective_user.id if update.effective_user else 0)
    )

    session_factory = get_session_factory(context)
    async with session_factory() as session:
        total_result = await session.execute(
            select(func.count(), func.coalesce(func.sum(DownloadLog.file_size), 0))
            .where(DownloadLog.user_id == target_id)
            .where(DownloadLog.status == "ok")
        )
        total_count, total_size = total_result.one()

        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today_result = await session.execute(
            select(func.count())
            .where(DownloadLog.user_id == target_id)
            .where(DownloadLog.created_at >= today_start)
            .where(DownloadLog.status == "ok")
        )
        today_count = today_result.scalar() or 0

    lang = (
        await get_user_repo(context).get_or_create(update.effective_user.id)  # type: ignore[union-attr]
    ).language
    lines = [
        t("usage.title", lang),
        t("usage.downloads", lang, count=total_count),
        t("usage.total_size", lang, size=format_size(total_size or 0)),
        t("usage.today", lang, count=today_count),
    ]
    if target_id != update.effective_user.id:  # type: ignore[union-attr]
        lines.insert(1, f"User: <code>{target_id}</code>")

    await update.message.reply_html("\n".join(lines))


def register(app: Application) -> None:
    app.add_handler(CommandHandler("uncache", _cmd_uncache))
    app.add_handler(CommandHandler("reload_cache", _cmd_reload_cache))
    app.add_handler(CommandHandler("get_log", _cmd_get_log))
    app.add_handler(CommandHandler("usage", _cmd_usage))
