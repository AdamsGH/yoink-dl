"""Proxy manager - multi-proxy support with round-robin/random selection."""
from __future__ import annotations

import random
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from yoink_dl.config import DownloaderConfig as Settings


@dataclass(frozen=True)
class ProxyConfig:
    url: str  # full URL: http://user:pass@host:port

    @classmethod
    def from_url(cls, url: str) -> "ProxyConfig":
        return cls(url=url)

    @property
    def scheme(self) -> str:
        return urlparse(self.url).scheme

    def as_ytdlp(self) -> str:
        """Return proxy URL in yt-dlp format."""
        return self.url

    def as_requests(self) -> dict[str, str]:
        """Return proxy dict for requests/httpx."""
        return {"http": self.url, "https": self.url}


class ProxyManager:
    def __init__(self, proxies: list[str], strategy: str = "round_robin") -> None:
        self._proxies = [ProxyConfig.from_url(u) for u in proxies if u]
        self._strategy = strategy
        self._index = 0
        self._lock = threading.Lock()

    @classmethod
    def from_settings(cls, settings: "Settings") -> "ProxyManager":
        return cls(proxies=settings.proxy_urls, strategy=settings.proxy_strategy)

    @property
    def available(self) -> bool:
        return len(self._proxies) > 0

    def get(self, index: int | None = None) -> ProxyConfig | None:
        """Return proxy by 1-based index, or pick by strategy when index is None."""
        if not self._proxies:
            return None
        if index is not None:
            if index <= 0:
                return None
            return self._proxies[(index - 1) % len(self._proxies)]
        if self._strategy == "random":
            return random.choice(self._proxies)
        with self._lock:
            proxy = self._proxies[self._index % len(self._proxies)]
            self._index += 1
            return proxy

    def get_for_domain(self, domain: str, proxy_domains: list[str]) -> ProxyConfig | None:
        """Return a proxy for the domain if it matches proxy_domains, else None."""
        from yoink_dl.url.domains import domain_matches
        if domain_matches(domain, proxy_domains):
            return self.get()
        return None
