"""User settings repository - merges core User + dl UserSettings ORM into a flat dataclass."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from yoink.core.db.models import BotSetting, User, UserRole
from yoink_dl.storage.models import UserSettings as UserSettingsModel


@dataclass
class UserSettings:
    """Flat dataclass used throughout the download/upload pipeline.

    Merges fields from core User and dl-specific UserSettings ORM model
    into a single immutable view that command handlers can pass around
    without touching the DB session.
    """
    user_id: int
    role: UserRole = UserRole.user
    language: str = "en"
    quality: str = "best"
    codec: str = "avc1"
    container: str = "mp4"
    proxy_enabled: bool = False
    proxy_url: str | None = None
    keyboard: str = "2x3"
    subs_enabled: bool = False
    subs_auto: bool = False
    subs_always_ask: bool = False
    subs_lang: str = "en"
    split_size: int = 2_043_000_000
    nsfw_blur: bool = True
    mediainfo: bool = False
    send_as_file: bool = False
    gallery_zip: bool = False
    use_pool_cookies: bool = True
    args_json: dict[str, Any] = field(default_factory=dict)
    blocked: bool = False
    ban_until: datetime | None = None


def _user_to_settings(user: User, dl: UserSettingsModel | None = None) -> UserSettings:
    """Build a UserSettings dataclass from a core User and optional dl row."""
    now = datetime.now(timezone.utc)
    ban_until = user.ban_until
    if ban_until is not None and ban_until.tzinfo is None:
        ban_until = ban_until.replace(tzinfo=timezone.utc)
    blocked = user.role == UserRole.banned or (ban_until is not None and ban_until > now)
    return UserSettings(
        user_id=user.id,
        role=user.role,
        language=user.language,
        quality=dl.quality if dl else "best",
        codec=dl.codec if dl else "avc1",
        container=dl.container if dl else "mp4",
        proxy_enabled=dl.proxy_enabled if dl else False,
        proxy_url=dl.proxy_url if dl else None,
        keyboard=dl.keyboard if dl else "2x3",
        subs_enabled=dl.subs_enabled if dl else False,
        subs_auto=dl.subs_auto if dl else False,
        subs_always_ask=dl.subs_always_ask if dl else False,
        subs_lang=dl.subs_lang if dl else "en",
        split_size=dl.split_size if dl else 2_043_000_000,
        nsfw_blur=dl.nsfw_blur if dl else True,
        mediainfo=dl.mediainfo if dl else False,
        send_as_file=dl.send_as_file if dl else False,
        gallery_zip=dl.gallery_zip if dl else False,
        use_pool_cookies=dl.use_pool_cookies if dl else True,
        args_json=dl.args_json if dl else {},
        blocked=blocked,
        ban_until=ban_until,
    )


class UserSettingsRepo:
    """Reads core User + dl UserSettings model, exposes a flat UserSettings dataclass.

    This is the single entry point commands use to get per-user settings.
    """

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._sf = session_factory

    async def get_or_create(
        self,
        user_id: int,
        group_id: int | None = None,
        first_name: str | None = None,
        username: str | None = None,
    ) -> UserSettings:
        async with self._sf() as s:
            user = await s.get(User, user_id)
            if user is None:
                role: UserRole | None = None
                if group_id is not None:
                    from yoink.core.db.models import Group  # noqa: PLC0415
                    group = await s.get(Group, group_id)
                    if group is not None:
                        role = group.auto_grant_role
                if role is None:
                    row = await s.get(BotSetting, "bot_access_mode")
                    mode = row.value if row else "open"
                    role = UserRole.restricted if mode == "approved_only" else UserRole.user
                user = User(id=user_id, role=role, first_name=first_name, username=username)
                s.add(user)
                await s.flush()
            else:
                changed = False
                if first_name and user.first_name != first_name:
                    user.first_name = first_name
                    changed = True
                if username and user.username != username:
                    user.username = username
                    changed = True
                if changed:
                    await s.flush()
            dl = await s.get(UserSettingsModel, user_id)
            if dl is None:
                dl = UserSettingsModel(user_id=user_id)
                s.add(dl)
            await s.commit()
            await s.refresh(user)
            await s.refresh(dl)
            return _user_to_settings(user, dl)

    async def is_blocked(self, user_id: int) -> bool:
        async with self._sf() as s:
            user = await s.get(User, user_id)
            if user is None:
                return False
            if user.role == UserRole.banned:
                return True
            if user.ban_until is not None:
                ban_until = user.ban_until
                if ban_until.tzinfo is None:
                    ban_until = ban_until.replace(tzinfo=timezone.utc)
                if ban_until > datetime.now(timezone.utc):
                    return True
                await s.execute(
                    User.__table__.update().where(User.id == user_id).values(ban_until=None)
                )
                await s.commit()
            return False

    _USER_FIELDS = frozenset({"role", "ban_until", "username", "first_name", "language"})

    async def update(self, user_id: int, **kwargs: Any) -> UserSettings:
        """Update user fields, routing core fields to User and dl fields to UserSettings."""
        user_kwargs = {k: v for k, v in kwargs.items() if k in self._USER_FIELDS}
        dl_kwargs = {k: v for k, v in kwargs.items() if k not in self._USER_FIELDS}

        async with self._sf() as s:
            user = await s.get(User, user_id)
            if user is None:
                user = User(id=user_id)
                s.add(user)
                await s.flush()
            for k, v in user_kwargs.items():
                setattr(user, k, v)
            dl = await s.get(UserSettingsModel, user_id)
            if dl is None:
                dl = UserSettingsModel(user_id=user_id)
                s.add(dl)
            for k, v in dl_kwargs.items():
                setattr(dl, k, v)
            if dl_kwargs:
                dl.updated_at = datetime.now(timezone.utc)
            await s.commit()
            await s.refresh(user)
            await s.refresh(dl)
            return _user_to_settings(user, dl)
