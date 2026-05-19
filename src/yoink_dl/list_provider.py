"""List-users provider for dl plugin.

Registered via register_list_users_provider() in DownloaderPlugin.setup().
Returns dl_count and dl_last_at per user_id for the admin user list.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def dl_list_users_provider(
    session: AsyncSession,
    user_ids: list[int],
    since: datetime | None = None,
) -> dict[int, dict]:
    """Return {user_id: {dl_count, dl_last_at}} for the given user_ids.

    When *since* is provided only downloads after that timestamp are counted
    (used for period-scoped sorting in the admin user list).
    """
    if not user_ids:
        return {}

    from yoink_dl.storage.models import DownloadLog  # noqa: PLC0415

    q = (
        select(
            DownloadLog.user_id,
            func.count().label("dl_count"),
            func.max(DownloadLog.created_at).label("dl_last_at"),
        )
        .where(DownloadLog.user_id.in_(user_ids))
    )
    if since is not None:
        q = q.where(DownloadLog.created_at >= since)
    q = q.group_by(DownloadLog.user_id)

    rows = (await session.execute(q)).all()
    return {r.user_id: {"dl_count": r.dl_count, "dl_last_at": r.dl_last_at} for r in rows}
