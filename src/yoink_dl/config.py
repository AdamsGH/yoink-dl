"""Downloader plugin settings."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class DownloaderConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Limits
    max_file_size_gb: float = 2.0
    download_timeout: int = 1200
    max_playlist_count: int = 50
    rate_limit_per_minute: int = 5
    rate_limit_per_hour: int = 30
    rate_limit_per_day: int = 100
    download_retries: int = 3  # fallback default; runtime value stored in BotSetting dl.download_retries

    # YouTube
    youtube_pot_enabled: bool = True
    youtube_pot_url: str = "http://localhost:4416"
    youtube_cookie_urls: list[str] = []
    youtube_cookie_strategy: str = "round_robin"

    # Per-service cookies
    instagram_cookie_url: str | None = None
    tiktok_cookie_url: str | None = None
    facebook_cookie_url: str | None = None
    twitter_cookie_url: str | None = None

    # Browser profile for automatic cookie extraction
    browser_profile_path: str | None = None
    browser_cookie_domains: list[str] = []

    # IPv6 rotation — prefix must be routed to this host (local route)
    ipv6_cidr: str | None = None
    ipv6_domains: list[str] = []

    # Proxy
    proxy_urls: list[str] = []
    proxy_strategy: str = "round_robin"
    proxy_domains: list[str] = []

    # Bot-specific
    log_channel: int | None = None
    log_exception_channel: int | None = None
    required_channel: str | None = None

    # Inline mode storage: global fallback for ChosenInlineResult pipeline.
    # Per-group overrides are stored in the groups table.
    # If neither is set, videos are sent to the requesting user's DM.
    inline_storage_chat_id: int | None = None
    inline_storage_thread_id: int | None = None

    @property
    def max_file_size_bytes(self) -> int:
        return int(self.max_file_size_gb * 1024 ** 3)

    def browser_cookies_available(self) -> bool:
        """True when a browser profile path is configured and exists on disk."""
        from pathlib import Path
        return bool(self.browser_profile_path and Path(self.browser_profile_path).exists())
