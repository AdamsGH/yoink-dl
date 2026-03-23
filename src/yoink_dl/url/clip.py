"""
Clip spec parsing - extract start/end times from URL and message text.

Supported input formats:
  URL 60           -> start from URL ?t=, duration 60s
  URL 00:15:10 60  -> start 00:15:10, duration 60s
  URL 00:15:10 00:16:10  -> start 00:15:10, end 00:16:10
  URL?t=1511 60    -> start 1511s, duration 60s
  URL?t=1511 00:26:00  -> start 1511s, end 00:26:00
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse, parse_qs


@dataclass
class ClipSpec:
    start_sec: int
    end_sec: int

    @property
    def duration_sec(self) -> int:
        return self.end_sec - self.start_sec


def parse_time(s: str) -> int:
    """
    Parse a time string to seconds.
    If it contains ':', treat as HH:MM:SS / MM:SS.
    Otherwise treat as plain integer seconds.
    """
    s = s.strip()
    if ":" in s:
        parts = s.split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        else:
            raise ValueError(f"Invalid time format: {s!r}")
    else:
        return int(s)


def extract_t_param(url: str) -> int | None:
    """Extract ?t= or &t= parameter from URL as seconds."""
    try:
        qs = parse_qs(urlparse(url).query)
        for key in ("t", "start"):
            if key in qs:
                val = qs[key][0]
                # Could be plain seconds or e.g. 25m10s
                m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?", val)
                if m and any(m.groups()):
                    h = int(m.group(1) or 0)
                    mn = int(m.group(2) or 0)
                    sc = int(m.group(3) or 0)
                    return h * 3600 + mn * 60 + sc
                return int(val)
    except (ValueError, AttributeError):
        pass
    return None


def parse_clip_spec(url: str, message_text: str) -> ClipSpec | None:
    """
    Parse ClipSpec from message text after the URL.

    Returns None if no clip info found.
    Raises ValueError if format is invalid.
    """
    # Strip the URL from the start of the message to get the remainder
    text = message_text.strip()
    # Remove the URL portion
    url_end = text.find(url)
    if url_end != -1:
        remainder = text[url_end + len(url):].strip()
    else:
        remainder = text.strip()

    t_param = extract_t_param(url)

    if not remainder:
        # No extra tokens - only useful if URL has ?t=
        # Caller should ask for end time
        return None

    tokens = remainder.split()

    if len(tokens) == 1:
        # One token: could be duration or end time
        token = tokens[0]
        if t_param is None:
            raise ValueError("Start time missing")
        start = t_param
        if ":" in token:
            end = parse_time(token)
        else:
            end = start + parse_time(token)
        return ClipSpec(start_sec=start, end_sec=end)

    if len(tokens) >= 2:
        # Two tokens: start end_or_duration  (URL has no ?t= or it's ignored)
        start = parse_time(tokens[0])
        token2 = tokens[1]
        if ":" in token2:
            end = parse_time(token2)
        else:
            end = start + parse_time(token2)
        return ClipSpec(start_sec=start, end_sec=end)

    return None
