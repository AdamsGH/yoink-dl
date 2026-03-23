"""Tests for clip spec parsing."""
from __future__ import annotations

import pytest

from yoink_dl.url.clip import ClipSpec, extract_t_param, parse_clip_spec, parse_time


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
