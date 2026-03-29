"""Activity provider for the dl plugin - plugs into core activity registry."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from yoink.core.activity import PluginActivity

_MUSIC_DOMAINS = frozenset({
    "open.spotify.com", "spotify.com",
    "music.yandex.ru", "music.yandex.com",
    "deezer.com", "www.deezer.com",
    "music.apple.com", "soundcloud.com", "music.youtube.com",
})
_VIDEO_DOMAINS = frozenset({
    "youtube.com", "youtu.be", "m.youtube.com", "www.youtube.com",
    "tiktok.com", "vimeo.com", "twitch.tv",
    "instagram.com", "ig.me", "twitter.com", "x.com",
    "reddit.com", "redd.it",
})


def _categorize(domain: str | None) -> str:
    if not domain:
        return "other"
    d = domain.lower().removeprefix("www.")
    if d in _MUSIC_DOMAINS:
        return "music"
    if d in _VIDEO_DOMAINS:
        return "video"
    return "other"


async def dl_activity_provider(session: AsyncSession, user_id: int) -> PluginActivity:
    from yoink_dl.storage.models import DownloadLog  # noqa: PLC0415

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)
    base = DownloadLog.user_id == user_id

    total = (await session.execute(
        select(func.count()).select_from(DownloadLog).where(base)
    )).scalar_one()

    today_count = (await session.execute(
        select(func.count()).select_from(DownloadLog)
        .where(base, DownloadLog.created_at >= today_start)
    )).scalar_one()

    week_count = (await session.execute(
        select(func.count()).select_from(DownloadLog)
        .where(base, DownloadLog.created_at >= week_start)
    )).scalar_one()

    last_at = (await session.execute(
        select(func.max(DownloadLog.created_at)).where(base)
    )).scalar_one()

    top_rows = (await session.execute(
        select(DownloadLog.domain, func.count().label("cnt"))
        .where(base, DownloadLog.domain.isnot(None))
        .group_by(DownloadLog.domain)
        .order_by(func.count().desc())
        .limit(5)
    )).all()
    top_domains = [{"domain": r.domain, "count": r.cnt} for r in top_rows]

    cat_rows = (await session.execute(
        select(DownloadLog.domain, func.count().label("cnt"))
        .where(base, DownloadLog.domain.isnot(None))
        .group_by(DownloadLog.domain)
    )).all()
    by_category: dict[str, int] = {"video": 0, "music": 0, "other": 0}
    for r in cat_rows:
        by_category[_categorize(r.domain)] += r.cnt

    return PluginActivity(
        plugin="dl",
        total=total,
        last_at=last_at,
        extra={"today": today_count, "this_week": week_count, "top_domains": top_domains, "by_category": by_category},
    )
