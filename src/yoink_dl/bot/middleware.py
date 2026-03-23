"""dl-plugin middleware helpers.

Only dl-specific accessors live here.
General helpers (get_session_factory, get_config, guard_admin) are
imported from yoink.core.bot.middleware and re-exported so command
modules have a single import source.
"""
from __future__ import annotations

from telegram.ext import ContextTypes

from yoink.core.bot.middleware import (  # noqa: F401  re-exported
    get_session_factory,
    get_config,
    guard_admin,
)
from yoink_dl.config import DownloaderConfig
from yoink_dl.storage.repos import UserSettingsRepo


def get_dl_config(context: ContextTypes.DEFAULT_TYPE) -> DownloaderConfig:
    return context.bot_data["dl_config"]


# Alias used by most command modules - cleaner than get_dl_config
def get_settings(context: ContextTypes.DEFAULT_TYPE) -> DownloaderConfig:
    return context.bot_data["dl_config"]


def get_user_repo(context: ContextTypes.DEFAULT_TYPE) -> UserSettingsRepo:
    """dl-specific UserSettingsRepo (merges core User + dl UserSettings model)."""
    return context.bot_data["dl_user_repo"]


def get_owner_id(context: ContextTypes.DEFAULT_TYPE) -> int:
    """Owner id lives in CoreSettings stored as bot_data['config']."""
    return context.bot_data["config"].owner_id


async def is_blocked(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    return await get_user_repo(context).is_blocked(user_id)
