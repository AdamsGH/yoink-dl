"""Typed bot errors. Every user-facing error has an i18n key."""
from __future__ import annotations


class BotError(Exception):
    """Base class. message_key points to an i18n key in locales/*.yml."""
    def __init__(self, message_key: str = "errors.unknown", **kwargs: object) -> None:
        self.message_key = message_key
        self.kwargs = kwargs
        super().__init__(message_key)


class DownloadError(BotError):
    def __init__(self, error: str = "", **kwargs: object) -> None:
        super().__init__("errors.download_failed", error=error, **kwargs)


class CookieError(BotError):
    def __init__(self, **kwargs: object) -> None:
        super().__init__("errors.cookie_required", **kwargs)


class GeoBlockedError(BotError):
    def __init__(self, **kwargs: object) -> None:
        super().__init__("errors.geo_blocked", **kwargs)


class PrivateContentError(BotError):
    def __init__(self, **kwargs: object) -> None:
        super().__init__("errors.private_content", **kwargs)


class FileTooLargeError(BotError):
    def __init__(self, size: str = "", max_size: str = "", **kwargs: object) -> None:
        super().__init__("download.file_too_large", size=size, max_size=max_size, **kwargs)


class LiveStreamError(BotError):
    def __init__(self, **kwargs: object) -> None:
        super().__init__("download.live_stream", **kwargs)


class UnsupportedUrlError(BotError):
    def __init__(self, **kwargs: object) -> None:
        super().__init__("download.unsupported", **kwargs)


class BlacklistedDomainError(BotError):
    def __init__(self, **kwargs: object) -> None:
        super().__init__("download.blacklisted", **kwargs)


class RateLimitError(BotError):
    def __init__(self, seconds: int = 0, **kwargs: object) -> None:
        super().__init__("common.flood_wait", seconds=seconds, **kwargs)


class NsfwError(BotError):
    def __init__(self, cost: int = 0, **kwargs: object) -> None:
        super().__init__("nsfw.paid_required", cost=cost, **kwargs)


class AdminOnlyError(BotError):
    def __init__(self, **kwargs: object) -> None:
        super().__init__("admin.access_denied", **kwargs)


class UserBlockedError(BotError):
    def __init__(self, **kwargs: object) -> None:
        super().__init__("common.access_denied", **kwargs)
