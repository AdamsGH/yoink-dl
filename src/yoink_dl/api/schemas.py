"""Downloader plugin API schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DownloadLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    url: str
    domain: str | None
    title: str | None
    quality: str | None
    file_size: int | None
    duration: float | None
    file_count: int | None
    status: str
    error_msg: str | None
    group_id: int | None
    thread_id: int | None
    message_id: int | None
    clip_start: int | None
    clip_end: int | None
    created_at: datetime


class CookieResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    domain: str
    is_valid: bool
    created_at: datetime
    updated_at: datetime


class NsfwDomainResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    domain: str
    note: str | None
    created_at: datetime


class NsfwKeywordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    keyword: str
    note: str | None
    created_at: datetime


class NsfwDomainCreate(BaseModel):
    domain: str
    note: str | None = None


class NsfwDomainUpdate(BaseModel):
    domain: str | None = None
    note: str | None = None


class NsfwKeywordCreate(BaseModel):
    keyword: str
    note: str | None = None


class NsfwKeywordUpdate(BaseModel):
    keyword: str | None = None
    note: str | None = None


class NsfwImport(BaseModel):
    domains: list[NsfwDomainCreate] = []
    keywords: list[NsfwKeywordCreate] = []


class CookieCreate(BaseModel):
    domain: str
    content: str


class DlUserSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    quality: str
    codec: str
    container: str
    proxy_enabled: bool
    proxy_url: str | None
    keyboard: str
    subs_enabled: bool
    subs_auto: bool
    subs_always_ask: bool
    subs_lang: str
    split_size: int
    nsfw_blur: bool
    mediainfo: bool
    send_as_file: bool
    gallery_zip: bool
    updated_at: datetime


class StatsOverview(BaseModel):
    total_downloads: int
    downloads_today: int
    cache_hits_today: int
    errors_today: int
    top_domains: list[dict]
    downloads_by_day: list[dict]


class NsfwCheckResponse(BaseModel):
    url: str
    is_nsfw: bool
    matched_domain: str | None = None
    matched_keywords: list[str] = []


class NsfwCheckRequest(BaseModel):
    url: str


class CookieTokenResponse(BaseModel):
    token: str
    expires_in: int  # seconds
    submit_url: str


class CookieSubmitRequest(BaseModel):
    token: str
    # domain -> list of raw cookie objects from chrome.cookies API
    cookies: dict[str, list[dict]]


class DlUserSettingsUpdate(BaseModel):
    quality: str | None = None
    codec: str | None = None
    container: str | None = None
    proxy_enabled: bool | None = None
    proxy_url: str | None = None
    keyboard: str | None = None
    subs_enabled: bool | None = None
    subs_auto: bool | None = None
    subs_always_ask: bool | None = None
    subs_lang: str | None = None
    split_size: int | None = None
    nsfw_blur: bool | None = None
    mediainfo: bool | None = None
    send_as_file: bool | None = None
    gallery_zip: bool | None = None
