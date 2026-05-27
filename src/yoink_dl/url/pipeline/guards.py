"""Pipeline guard phase: rate-limiting and user access checks."""
from __future__ import annotations

from typing import TYPE_CHECKING

from yoink.core.db.models import User, UserRole
from yoink.core.i18n import t
from yoink.core.metrics import metrics
from yoink_dl.storage.repos import RateLimitRepo

if TYPE_CHECKING:
    from telegram import Message
    from telegram.ext import ContextTypes

    from yoink_dl.config import DownloaderConfig


async def check_user_access(
    user_settings: User,
    ctx_group_id: int | None,
    use_message: Message | None,
) -> bool:
    """Return False (and optionally reply) if the user should not proceed."""
    if user_settings.is_blocked:
        return False
    if user_settings.role == UserRole.restricted:
        if ctx_group_id is None and use_message:
            await use_message.reply_html(t("start.pending", user_settings.language))
        return False
    return True


async def check_rate_limit(
    user_id: int,
    settings: DownloaderConfig,
    context: ContextTypes.DEFAULT_TYPE,
    user_settings: User,
    use_message: Message | None,
) -> bool:
    """Return False (and reply) if the user is rate-limited."""
    if user_id == context.bot_data["config"].owner_id:
        return True

    from yoink_dl.bot.middleware import get_session_factory  # noqa: PLC0415

    session_factory = get_session_factory(context)
    rl = RateLimitRepo(session_factory)
    allowed, reason = await rl.check_and_increment(
        user_id=user_id,
        limit_minute=settings.rate_limit_per_minute,
        limit_hour=settings.rate_limit_per_hour,
        limit_day=settings.rate_limit_per_day,
    )
    if not allowed:
        metrics.inc("rate_limited")
        msg_text = t("errors.rate_limited", user_settings.language) + f"\n<i>({reason})</i>"
        if use_message:
            await use_message.reply_html(msg_text)
        return False
    return True
