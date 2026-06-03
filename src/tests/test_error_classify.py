"""yt-dlp error string classification into typed BotError subclasses."""
from __future__ import annotations

import pytest

from yoink_dl.download.ytdlp import _classify_ytdlp_error
from yoink_dl.url.pipeline.helpers import _is_retryable
from yoink_dl.utils.errors import (
    AgeRestrictedError,
    ConnectionFailedError,
    GeoBlockedError,
    LiveStreamError,
    NoVideoError,
)


class TestClassifyYtdlpError:
    def test_no_match_returns_none(self) -> None:
        # Unknown messages are left for the generic DownloadError path.
        assert _classify_ytdlp_error("ERROR: something weird happened") is None

    def test_geo(self) -> None:
        with pytest.raises(GeoBlockedError):
            _classify_ytdlp_error("ERROR: not available in your country")

    def test_age(self) -> None:
        with pytest.raises(AgeRestrictedError):
            _classify_ytdlp_error("ERROR: Sign in to confirm your age")

    def test_live(self) -> None:
        with pytest.raises(LiveStreamError):
            _classify_ytdlp_error("ERROR: this is a live stream")

    def test_no_video(self) -> None:
        with pytest.raises(NoVideoError):
            _classify_ytdlp_error(
                "ERROR: [twitter] 123: No video could be found in this tweet"
            )

    def test_connection_timeout(self) -> None:
        with pytest.raises(ConnectionFailedError):
            _classify_ytdlp_error(
                "ERROR: [twitter] 123: Unable to download JSON metadata: "
                "HTTPSConnectionPool(host='api.x.com', port=443): Read timed out."
            )


class TestRetrySemantics:
    def test_connection_failure_is_retryable(self) -> None:
        # Subclasses DownloadError so the retry layer gives it another go.
        assert _is_retryable(ConnectionFailedError()) is True

    def test_no_video_is_not_retryable(self) -> None:
        # Terminal: parsing succeeded, retrying changes nothing.
        assert _is_retryable(NoVideoError()) is False
