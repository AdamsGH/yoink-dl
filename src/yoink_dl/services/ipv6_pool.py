"""IPv6 address pool for per-request source address rotation."""
from __future__ import annotations

import ipaddress
import random
import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class IPv6Binding:
    address: str  # e.g. "2a05:3580:d917:9801::a3f2"

    def as_ytdlp(self) -> str:
        """yt-dlp source_address option value."""
        return self.address

    def as_gallery_dl(self) -> list[str]:
        """gallery-dl CLI args."""
        return ["--source-address", self.address]


class IPv6Pool:
    """
    Picks random IPv6 addresses from a configured prefix.
    The prefix must be routed to this host (local route in kernel table).

    Usage:
        pool = IPv6Pool("2a05:3580:d917:9801::/64")
        binding = pool.get()
        ydl_opts["source_address"] = binding.as_ytdlp()
    """

    def __init__(self, cidr: str) -> None:
        self._network = ipaddress.IPv6Network(cidr, strict=False)
        self._lock = threading.Lock()
        # Exclude network address (::0) and commonly used static addresses (::1)
        self._first = 2
        self._last = int(self._network.num_addresses) - 1

    @classmethod
    def from_settings(cls, settings: "DownloaderConfig") -> "IPv6Pool | None":  # type: ignore[name-defined]
        from yoink_dl.config import DownloaderConfig
        if not settings.ipv6_cidr:
            return None
        return cls(settings.ipv6_cidr)

    def get(self) -> IPv6Binding:
        """Return a random address from the pool."""
        offset = random.randint(self._first, self._last)
        addr = self._network.network_address + offset
        return IPv6Binding(address=str(addr))

    def __bool__(self) -> bool:
        return True
