"""Domain classification lists. All lists configurable via DownloaderConfig."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from yoink_dl.config import DownloaderConfig


@dataclass
class DomainConfig:
    """All domain lists in one place. Populated from DownloaderConfig at startup."""

    # Domains completely blocked
    blacklist: list[str] = field(default_factory=list)

    # Domains that bypass porn keyword checks
    whitelist: list[str] = field(default_factory=list)

    # Domains checked only for keywords, not domain list
    greylist: list[str] = field(default_factory=list)

    # Domains where cookies must NOT be used
    no_cookie: list[str] = field(default_factory=lambda: ["dailymotion.com"])

    # Domains where match_filter (duration/live check) is skipped
    no_filter: list[str] = field(default_factory=list)

    # Domains always routed through the proxy pool
    proxy_domains: list[str] = field(default_factory=list)

    # Domains where query string is always stripped for cache keys
    clean_query: list[str] = field(default_factory=lambda: [
        "tiktok.com", "vimeo.com", "twitch.tv", "instagram.com", "ig.me",
        "dailymotion.com", "twitter.com", "x.com", "ok.ru", "rutube.ru",
        "bilibili.com", "9gag.com", "streamable.com", "archive.org", "ted.com",
    ])

    # TikTok domains (need special handling)
    tiktok: list[str] = field(default_factory=lambda: [
        "tiktok.com", "vm.tiktok.com", "vt.tiktok.com",
        "www.tiktok.com", "m.tiktok.com",
    ])

    # YouTube-only (never fall back to gallery-dl)
    ytdlp_only: list[str] = field(default_factory=lambda: [
        "youtube.com", "youtu.be", "m.youtube.com", "www.youtube.com",
        "music.youtube.com",
    ])

    # Image-board / art sites (prefer gallery-dl)
    gallery_only: list[str] = field(default_factory=lambda: [
        "2ch.su", "4chan.org", "e-hentai.org", "e621.net", "gelbooru.com",
        "kemono.cr", "kemono.party", "coomer.party", "nhentai.net",
        "civitai.com", "wallhaven.cc",
    ])

    # Social media paths that prefer gallery-dl
    gallery_paths: list[str] = field(default_factory=lambda: [
        "vk.com/wall-", "vk.com/album-",
    ])

    # Domains that fall back to gallery-dl after yt-dlp failure
    gallery_fallback: list[str] = field(default_factory=lambda: [
        "instagram.com",
    ])

    @classmethod
    def from_config(cls, cfg: "DownloaderConfig") -> "DomainConfig":
        return cls(
            proxy_domains=cfg.proxy_domains,
        )


def extract_domain(url: str) -> str:
    """Return lowercased netloc with www. stripped."""
    try:
        netloc = urlparse(url).netloc.lower()
        return netloc.removeprefix("www.")
    except Exception:
        return ""


def domain_matches(domain: str, patterns: list[str]) -> bool:
    """True if domain equals or is a subdomain of any pattern."""
    for p in patterns:
        if domain == p or domain.endswith("." + p):
            return True
    return False
