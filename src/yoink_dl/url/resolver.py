"""Resolve URL to download engine and parameters."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from .domains import DomainConfig, extract_domain, domain_matches
from .normalizer import normalize


class Engine(Enum):
    YTDLP = auto()
    GALLERY_DL = auto()
    YTDLP_THEN_GALLERY = auto()   # try yt-dlp first, fall back to gallery-dl


@dataclass
class ResolvedUrl:
    url: str                         # normalized URL (range stripped)
    engine: Engine
    domain: str
    playlist_start: int | None = None
    playlist_end: int | None = None
    is_playlist: bool = False
    use_proxy: bool = False
    custom_proxy_url: str | None = None  # user-supplied proxy, overrides use_proxy
    use_cookies: bool = True
    apply_match_filter: bool = True
    extra_opts: dict = field(default_factory=dict)


def resolve(
    url: str,
    domain_cfg: DomainConfig,
    proxy_enabled: bool = False,
    custom_proxy_url: str | None = None,
    playlist_start: int | None = None,
    playlist_end: int | None = None,
) -> ResolvedUrl:
    """
    Determine which engine to use and what options to apply for a given URL.
    """
    clean = normalize(url, domain_cfg)
    domain = extract_domain(clean)

    engine = _pick_engine(domain, clean, domain_cfg)
    use_cookies = not domain_matches(domain, domain_cfg.no_cookie)
    apply_filter = not domain_matches(domain, domain_cfg.no_filter)
    is_playlist = playlist_start is not None

    return ResolvedUrl(
        url=clean,
        engine=engine,
        domain=domain,
        playlist_start=playlist_start,
        playlist_end=playlist_end,
        is_playlist=is_playlist,
        use_proxy=_pick_proxy(domain, domain_cfg, proxy_enabled),
        custom_proxy_url=custom_proxy_url,
        use_cookies=use_cookies,
        apply_match_filter=apply_filter,
    )


def _pick_engine(domain: str, url: str, cfg: DomainConfig) -> Engine:
    if domain_matches(domain, cfg.ytdlp_only):
        return Engine.YTDLP
    if domain_matches(domain, cfg.gallery_only):
        return Engine.GALLERY_DL
    # gallery_paths are URL path-prefixes like "vk.com/wall-", "vk.com/album-"
    # Match only when the URL contains that exact path prefix
    for prefix in cfg.gallery_paths:
        if prefix in url:
            return Engine.GALLERY_DL
    if domain_matches(domain, cfg.gallery_fallback):
        return Engine.YTDLP_THEN_GALLERY
    return Engine.YTDLP


def _pick_proxy(domain: str, cfg: DomainConfig, user_proxy: bool) -> bool:
    return user_proxy or domain_matches(domain, cfg.proxy_domains)
