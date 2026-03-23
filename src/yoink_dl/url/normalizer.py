"""URL normalization - strip tracking params, resolve Google redirects, clean for cache keys."""
from __future__ import annotations

import re
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode, unquote

from .domains import DomainConfig, extract_domain, domain_matches

# Tracking params stripped from all URLs
_TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "ref", "igshid", "si", "feature",
})


def normalize(url: str, domain_cfg: DomainConfig | None = None) -> str:
    """
    Full normalization pipeline:
    1. Resolve Google redirect wrappers
    2. Strip tracking params
    3. Strip range tags (*1*5)
    4. Apply domain-specific rules
    """
    if not url or not isinstance(url, str):
        return ""

    url = _resolve_google_redirect(url)
    url = _strip_range_tags(url)
    url = _strip_tracking_params(url)

    if domain_cfg:
        url = _apply_domain_rules(url, domain_cfg)

    return url


def normalize_for_cache(url: str, domain_cfg: DomainConfig | None = None) -> str:
    """
    Aggressive normalization for cache key generation.
    Strips everything non-essential so the same video
    maps to the same cache key regardless of tracking noise.
    """
    url = normalize(url, domain_cfg)
    parsed = urlparse(url)
    domain = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path
    query_params = parse_qs(parsed.query)

    # YouTube watch - keep only 'v'
    if domain in ("youtube.com", "www.youtube.com") and path == "/watch":
        v = query_params.get("v", [None])[0]
        new_q = urlencode({"v": v}) if v else ""
        return urlunparse(("https", "www.youtube.com", path, "", new_q, ""))

    # YouTube playlist - keep only 'list'
    if domain in ("youtube.com", "www.youtube.com") and path == "/playlist":
        lst = query_params.get("list", [None])[0]
        new_q = urlencode({"list": lst}) if lst else ""
        return urlunparse(("https", "www.youtube.com", path, "", new_q, ""))

    # YouTube shorts / youtu.be / live - strip all params
    if domain in ("youtube.com", "www.youtube.com", "youtu.be") and (
        path.startswith("/shorts/")
        or path.startswith("/live/")
        or path.endswith("/live")
    ):
        return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))
    if domain == "youtu.be":
        return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))

    # TikTok - strip all params
    if "tiktok.com" in domain:
        return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))

    # Domains in clean_query list - strip params
    if domain_cfg and domain_matches(domain, domain_cfg.clean_query):
        return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))

    # Everything else - strip fragment only
    return urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, parsed.query, ""))


def extract_range(text: str) -> tuple[str, int | None, int | None]:
    """
    Extract playlist range from URL with *start*end tags.
    Returns (clean_url, start, end). start/end are None if no range.

    Examples:
      "https://x.com/playlist*1*5"  -> ("https://x.com/playlist", 1, 5)
      "https://x.com/vid*-1*-5"    -> ("https://x.com/vid", -1, -5)
    """
    m = re.search(r"\*(-?\d+)\*(-?\d+)$", text)
    if m:
        clean = text[: m.start()]
        return clean, int(m.group(1)), int(m.group(2))
    return text, None, None


def is_playlist_url(text: str) -> bool:
    """True if text contains a *start*end range tag."""
    return bool(re.search(r"\*-?\d+\*-?\d+", text))


# -- internal helpers --

def _resolve_google_redirect(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.endswith("google.com") and parsed.path.startswith("/url"):
        qs = parse_qs(parsed.query)
        target = qs.get("q") or qs.get("url")
        if target:
            return unquote(target[0])
    return url


def _strip_range_tags(url: str) -> str:
    return re.sub(r"\*-?\d+\*-?\d+$", "", url)


def _strip_tracking_params(url: str) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    cleaned = {k: v for k, v in qs.items() if k not in _TRACKING_PARAMS}
    new_q = urlencode(cleaned, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_q, parsed.fragment))


def _apply_domain_rules(url: str, cfg: DomainConfig) -> str:
    """Pornhub: keep full path+query. TikTok: strip all params."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower().removeprefix("www.")

    if domain.endswith(".pornhub.com") or domain == "pornhub.com":
        # Keep everything, just normalize scheme
        return urlunparse(("https", "pornhub.com", parsed.path, parsed.params, parsed.query, ""))

    return url
