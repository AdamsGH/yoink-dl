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
    group_title: str | None = None
    thread_id: int | None
    message_id: int | None
    clip_start: int | None
    clip_end: int | None
    created_at: datetime
    media_type: str = "video"


class CookieResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    domain: str
    is_valid: bool
    is_pool: bool = False
    is_oauth: bool = False
    label: str | None = None
    avatar_url: str | None = None
    validated_at: datetime | None
    created_at: datetime
    updated_at: datetime
    inherited: bool = False

    @classmethod
    def model_validate(cls, obj, **kwargs):  # type: ignore[override]
        from yoink_dl.services.yttv_oauth import is_oauth_content  # noqa: PLC0415
        instance = super().model_validate(obj, **kwargs)
        if hasattr(obj, 'content') and obj.content:
            instance.is_oauth = is_oauth_content(obj.content)
        return instance


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
    use_pool_cookies: bool
    youtube_auth_mode: str = "cookies"
    updated_at: datetime
    # Computed: true when user may see/use the shared cookie pool
    has_pool_access: bool = False


class DlAdminSettings(BaseModel):
    """Global downloader settings stored in BotSetting KV (prefix dl.*)."""
    download_retries: int = 3
    download_timeout: int = 1200
    max_file_size_gb: float = 2.0
    rate_limit_per_minute: int = 5
    rate_limit_per_hour: int = 30
    rate_limit_per_day: int = 100
    max_playlist_count: int = 50


class DlAdminSettingsPatch(BaseModel):
    download_retries: int | None = None
    download_timeout: int | None = None
    max_file_size_gb: float | None = None
    rate_limit_per_minute: int | None = None
    rate_limit_per_hour: int | None = None
    rate_limit_per_day: int | None = None
    max_playlist_count: int | None = None


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


class YttvOAuthStartResponse(BaseModel):
    session_id: str
    verification_url: str
    user_code: str
    expires_in: int
    interval: int


class YttvOAuthPollResponse(BaseModel):
    status: str  # pending | expired | error | ok
    detail: str | None = None


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
    use_pool_cookies: bool | None = None
    youtube_auth_mode: str | None = None
