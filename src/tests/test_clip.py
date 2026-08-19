"""Tests for clip spec parsing."""
from __future__ import annotations

import pytest

from yoink_dl.config import DownloaderConfig
from yoink_dl.download.ytdlp import build_ytdlp_opts
from yoink_dl.storage.repos import UserSettings
from yoink_dl.url.clip import ClipSpec, extract_t_param, parse_clip_spec, parse_time
from yoink_dl.url.resolver import Engine, ResolvedUrl


class TestParseTime:
    def test_plain_seconds(self):
        assert parse_time("120") == 120

    def test_mm_ss(self):
        assert parse_time("02:30") == 150

    def test_hh_mm_ss(self):
        assert parse_time("01:30:00") == 5400

    def test_zero(self):
        assert parse_time("0") == 0

    def test_leading_zeros(self):
        assert parse_time("00:05:10") == 310


class TestExtractTParam:
    def test_t_seconds(self):
        assert extract_t_param("https://youtu.be/abc?t=120") == 120

    def test_t_hms(self):
        assert extract_t_param("https://youtu.be/abc?t=1h2m3s") == 3723

    def test_start_param(self):
        assert extract_t_param("https://example.com/v?start=60") == 60

    def test_no_t(self):
        assert extract_t_param("https://youtu.be/abc") is None

    def test_t_minutes_only(self):
        assert extract_t_param("https://youtu.be/abc?t=5m") == 300


class TestParseClipSpec:
    def test_url_with_t_and_duration(self):
        url = "https://youtu.be/abc?t=60"
        clip = parse_clip_spec(url, f"{url} 30")
        assert clip == ClipSpec(start_sec=60, end_sec=90)

    def test_url_with_t_and_end_time(self):
        url = "https://youtu.be/abc?t=60"
        clip = parse_clip_spec(url, f"{url} 01:30")
        assert clip == ClipSpec(start_sec=60, end_sec=90)

    def test_two_times(self):
        url = "https://example.com/video"
        clip = parse_clip_spec(url, f"{url} 00:15:10 60")
        assert clip == ClipSpec(start_sec=910, end_sec=970)

    def test_two_timestamps(self):
        url = "https://example.com/video"
        clip = parse_clip_spec(url, f"{url} 00:15:10 00:16:10")
        assert clip == ClipSpec(start_sec=910, end_sec=970)

    def test_no_clip_info(self):
        url = "https://example.com/video"
        assert parse_clip_spec(url, url) is None

    def test_missing_start_raises(self):
        url = "https://example.com/video"
        with pytest.raises(ValueError, match="Start time missing"):
            parse_clip_spec(url, f"{url} 60")

    def test_duration_property(self):
        clip = ClipSpec(start_sec=10, end_sec=70)
        assert clip.duration_sec == 60


class TestClipDownloaderOptions:
    def test_ffmpeg_reconnects_timed_out_media_streams(self, tmp_path):
        resolved = ResolvedUrl(
            url="https://youtu.be/abc",
            engine=Engine.YTDLP,
            domain="youtu.be",
            use_proxy=False,
        )
        config = DownloaderConfig(
            ffmpeg_read_timeout=45,
            ffmpeg_reconnect_delay_max=12,
            ffmpeg_reconnect_delay_total_max=34,
            ffmpeg_reconnect_max_retries=3,
        )

        opts = build_ytdlp_opts(
            resolved,
            UserSettings(user_id=1),
            tmp_path,
            app_settings=config,
            clip=ClipSpec(start_sec=60, end_sec=90),
        )

        assert opts["external_downloader_args"]["ffmpeg_i"] == [
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_on_network_error", "1",
            "-reconnect_on_http_error", "5xx",
            "-reconnect_delay_max", "12",
            "-reconnect_delay_total_max", "34",
            "-reconnect_max_retries", "3",
            "-rw_timeout", "45000000",
        ]
        assert opts["extractor_args"]["youtube"]["player_client"] == ["web_embedded"]

    def test_regular_youtube_download_keeps_default_player_clients(self, tmp_path):
        resolved = ResolvedUrl(
            url="https://youtu.be/abc",
            engine=Engine.YTDLP,
            domain="youtu.be",
            use_proxy=False,
        )

        opts = build_ytdlp_opts(
            resolved,
            UserSettings(user_id=1),
            tmp_path,
            app_settings=DownloaderConfig(),
        )

        assert "youtube" not in opts["extractor_args"]

    def test_non_youtube_clip_keeps_default_player_clients(self, tmp_path):
        resolved = ResolvedUrl(
            url="https://example.com/video",
            engine=Engine.YTDLP,
            domain="example.com",
            use_proxy=False,
        )

        opts = build_ytdlp_opts(
            resolved,
            UserSettings(user_id=1),
            tmp_path,
            app_settings=DownloaderConfig(),
            clip=ClipSpec(start_sec=60, end_sec=90),
        )

        assert "youtube" not in opts["extractor_args"]
