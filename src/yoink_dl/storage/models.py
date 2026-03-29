"""Downloader plugin ORM models."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Float, Index,
    Integer, String, Text, UniqueConstraint, ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from yoink.core.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Alias for plugin model discovery
DlBase = Base


class UserSettings(Base):
    """Per-user downloader preferences, extends core User."""
    __tablename__ = "dl_user_settings"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    quality: Mapped[str] = mapped_column(String(32), default="best", nullable=False)
    codec: Mapped[str] = mapped_column(String(16), default="avc1", nullable=False)
    container: Mapped[str] = mapped_column(String(8), default="mp4", nullable=False)
    proxy_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    proxy_url: Mapped[str | None] = mapped_column(String(512))
    keyboard: Mapped[str] = mapped_column(String(8), default="2x3", nullable=False)
    subs_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    subs_auto: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    subs_always_ask: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    subs_lang: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    split_size: Mapped[int] = mapped_column(BigInteger, default=2_043_000_000, nullable=False)
    nsfw_blur: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    mediainfo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    send_as_file: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    gallery_zip: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dm_topic_thread_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    args_json: Mapped[dict] = mapped_column(
        __import__("sqlalchemy").JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class DownloadLog(Base):
    __tablename__ = "download_log"
    __table_args__ = (Index("idx_download_log_user", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str | None] = mapped_column(String(253))
    title: Mapped[str | None] = mapped_column(Text)
    quality: Mapped[str | None] = mapped_column(String(32))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    duration: Mapped[float | None] = mapped_column(Float)
    file_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ok", nullable=False)
    error_msg: Mapped[str | None] = mapped_column(Text)
    group_id: Mapped[int | None] = mapped_column(BigInteger)
    thread_id: Mapped[int | None] = mapped_column(BigInteger)
    message_id: Mapped[int | None] = mapped_column(BigInteger)
    clip_start: Mapped[int | None] = mapped_column(Integer)
    clip_end: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class FileCache(Base):
    __tablename__ = "file_cache"
    __table_args__ = (Index("idx_file_cache_expires", "expires_at"),)

    cache_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    file_id: Mapped[str] = mapped_column(String(256), nullable=False)
    file_type: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    duration: Mapped[float | None] = mapped_column(Float)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RateLimit(Base):
    __tablename__ = "rate_limits"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    window: Mapped[str] = mapped_column(String(16), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Cookie(Base):
    __tablename__ = "cookies"
    __table_args__ = (UniqueConstraint("user_id", "domain"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    domain: Mapped[str] = mapped_column(String(253), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class NsfwDomain(Base):
    __tablename__ = "nsfw_domains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(253), unique=True, nullable=False)
    note: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class NsfwKeyword(Base):
    __tablename__ = "nsfw_keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    note: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
