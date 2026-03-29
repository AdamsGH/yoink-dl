"""Download history, admin settings, user settings, stats, retry endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from yoink.core.api.deps import get_current_user, get_db
from yoink.core.api.exceptions import NotFoundError
from yoink.core.api.responses import paginated_response
from yoink.core.auth.rbac import require_role
from yoink.core.db.models import User, UserPermission, UserRole
from yoink_dl.api.schemas import (
    DlAdminSettings,
    DlAdminSettingsPatch,
    DlUserSettingsResponse,
    DlUserSettingsUpdate,
    DownloadLogResponse,
    StatsOverview,
)
from yoink_dl.storage.models import DownloadLog, UserSettings

router = APIRouter(tags=["downloader"])

_AUDIO_DOMAINS = frozenset({
    "soundcloud.com", "bandcamp.com", "music.yandex.ru", "music.yandex.com",
    "open.spotify.com", "music.apple.com", "deezer.com", "tidal.com",
    "last.fm", "audiomack.com", "mixcloud.com",
})

_DL_ADMIN_DEFAULTS: dict[str, str] = {
    "dl.download_retries":      "3",
    "dl.download_timeout":      "1200",
    "dl.max_file_size_gb":      "2.0",
    "dl.rate_limit_per_minute": "5",
    "dl.rate_limit_per_hour":   "30",
    "dl.rate_limit_per_day":    "100",
    "dl.max_playlist_count":    "50",
}


def _media_type(row: DownloadLog) -> str:
    domain = (row.domain or "").lower().removeprefix("www.")
    if domain in _AUDIO_DOMAINS:
        return "audio"
    if row.clip_start is not None or row.clip_end is not None:
        return "clip"
    return "video"


async def _get_dl_admin_settings(request: Request) -> DlAdminSettings:
    from yoink.core.db.repos.bot_settings import BotSettingsRepo  # noqa: PLC0415
    repo: BotSettingsRepo = request.app.state.bot_data["bot_settings_repo"]
    raw: dict[str, str] = {}
    for key, default in _DL_ADMIN_DEFAULTS.items():
        val = await repo.get(key)
        raw[key] = val if val is not None else default

    return DlAdminSettings(
        download_retries=int(raw["dl.download_retries"]),
        download_timeout=int(raw["dl.download_timeout"]),
        max_file_size_gb=float(raw["dl.max_file_size_gb"]),
        rate_limit_per_minute=int(raw["dl.rate_limit_per_minute"]),
        rate_limit_per_hour=int(raw["dl.rate_limit_per_hour"]),
        rate_limit_per_day=int(raw["dl.rate_limit_per_day"]),
        max_playlist_count=int(raw["dl.max_playlist_count"]),
    )


async def _has_pool_access(session: AsyncSession, user: User) -> bool:
    """True when the user may see/use the shared cookie pool."""
    if user.role in (UserRole.admin, UserRole.owner):
        return True
    perm = await session.execute(
        select(UserPermission).where(
            UserPermission.user_id == user.id,
            UserPermission.plugin == "dl",
            UserPermission.feature == "shared_cookies",
        )
    )
    return perm.scalar_one_or_none() is not None


async def _settings_response(session: AsyncSession, user: User) -> DlUserSettingsResponse:
    row = await session.get(UserSettings, user.id)
    if row is None:
        row = UserSettings(user_id=user.id)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    resp = DlUserSettingsResponse.model_validate(row)
    resp.has_pool_access = await _has_pool_access(session, user)
    return resp


@router.get("/downloads/domains", response_model=dict, summary="Distinct domains in my download history")
async def list_my_download_domains(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    rows = (await session.execute(
        select(DownloadLog.domain).where(
            DownloadLog.user_id == current_user.id,
            DownloadLog.domain.isnot(None),
        ).distinct().order_by(DownloadLog.domain)
    )).scalars().all()
    return {"domains": list(rows)}


@router.get("/downloads", response_model=dict, summary="My download history")
async def list_my_downloads(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    domain: str | None = Query(None),
    media_type: str | None = Query(None),
    search: str | None = Query(None),
    period: str | None = Query(None),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    q = select(DownloadLog).where(DownloadLog.user_id == current_user.id)
    if domain:
        q = q.where(DownloadLog.domain == domain)
    if search:
        q = q.where(DownloadLog.url.ilike(f"%{search}%") | DownloadLog.title.ilike(f"%{search}%"))
    if period:
        now = datetime.now(timezone.utc)
        match period:
            case "7d":
                q = q.where(DownloadLog.created_at >= now - timedelta(days=7))
            case "30d":
                q = q.where(DownloadLog.created_at >= now - timedelta(days=30))
            case "90d":
                q = q.where(DownloadLog.created_at >= now - timedelta(days=90))
    total = (await session.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await session.execute(q.order_by(DownloadLog.created_at.desc()).offset(offset).limit(limit))).scalars().all()

    items = []
    for r in rows:
        d = DownloadLogResponse.model_validate(r).model_dump()
        if media_type and _media_type(r) != media_type:
            continue
        d["media_type"] = _media_type(r)
        items.append(d)
    return paginated_response(items, total, offset, limit)


@router.get("/downloads/all", response_model=dict, summary="All users' download history (admin+)")
async def list_all_downloads(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.owner)),
) -> dict:
    total = (await session.execute(select(func.count(DownloadLog.id)))).scalar_one()
    rows = (await session.execute(
        select(DownloadLog).order_by(DownloadLog.created_at.desc()).offset(offset).limit(limit)
    )).scalars().all()
    return paginated_response([DownloadLogResponse.model_validate(r) for r in rows], total, offset, limit)


@router.get("/admin/settings", response_model=DlAdminSettings, summary="Get global downloader settings (admin+)")
async def get_dl_admin_settings(
    request: Request,
    _: User = Depends(require_role(UserRole.admin, UserRole.owner)),
) -> DlAdminSettings:
    return await _get_dl_admin_settings(request)


@router.patch("/admin/settings", response_model=DlAdminSettings, summary="Update global downloader settings (admin+)")
async def update_dl_admin_settings(
    body: DlAdminSettingsPatch,
    request: Request,
    _: User = Depends(require_role(UserRole.admin, UserRole.owner)),
) -> DlAdminSettings:
    from yoink.core.db.repos.bot_settings import BotSettingsRepo  # noqa: PLC0415
    repo: BotSettingsRepo = request.app.state.bot_data["bot_settings_repo"]
    mapping = {
        "download_retries":      "dl.download_retries",
        "download_timeout":      "dl.download_timeout",
        "max_file_size_gb":      "dl.max_file_size_gb",
        "rate_limit_per_minute": "dl.rate_limit_per_minute",
        "rate_limit_per_hour":   "dl.rate_limit_per_hour",
        "rate_limit_per_day":    "dl.rate_limit_per_day",
        "max_playlist_count":    "dl.max_playlist_count",
    }
    for field, key in mapping.items():
        value = getattr(body, field)
        if value is not None:
            await repo.set(key, str(value))
    return await _get_dl_admin_settings(request)


@router.get("/settings", response_model=DlUserSettingsResponse, summary="My downloader settings")
async def get_dl_settings(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DlUserSettingsResponse:
    return await _settings_response(session, current_user)


@router.patch("/settings", response_model=DlUserSettingsResponse, summary="Update my downloader settings")
async def update_dl_settings(
    body: DlUserSettingsUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DlUserSettingsResponse:
    row = await session.get(UserSettings, current_user.id)
    if row is None:
        row = UserSettings(user_id=current_user.id)
        session.add(row)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(row, field, value)
    await session.commit()
    await session.refresh(row)
    return await _settings_response(session, current_user)


@router.get("/stats/overview", response_model=StatsOverview, summary="Downloader stats overview (admin+)")
async def stats_overview(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.owner)),
) -> StatsOverview:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    window_start = now - timedelta(days=days)

    total = (await session.execute(select(func.count()).select_from(DownloadLog))).scalar_one()
    downloads_today = (await session.execute(
        select(func.count()).select_from(DownloadLog).where(DownloadLog.created_at >= today_start)
    )).scalar_one()
    cache_hits_today = (await session.execute(
        select(func.count()).select_from(DownloadLog)
        .where(DownloadLog.status == "cached", DownloadLog.created_at >= today_start)
    )).scalar_one()
    errors_today = (await session.execute(
        select(func.count()).select_from(DownloadLog)
        .where(DownloadLog.status == "error", DownloadLog.created_at >= today_start)
    )).scalar_one()
    top_result = await session.execute(
        select(DownloadLog.domain, func.count().label("count"))
        .where(DownloadLog.domain.isnot(None))
        .group_by(DownloadLog.domain)
        .order_by(func.count().desc())
        .limit(10)
    )
    top_domains = [{"domain": r.domain, "count": r.count} for r in top_result]
    day_col = func.date_trunc("day", DownloadLog.created_at).label("day")
    by_day_result = await session.execute(
        select(day_col, func.count().label("count"))
        .where(DownloadLog.created_at >= window_start)
        .group_by(day_col)
        .order_by(day_col)
    )
    downloads_by_day = [{"date": r.day.strftime("%Y-%m-%d"), "count": r.count} for r in by_day_result]

    return StatsOverview(
        total_downloads=total,
        downloads_today=downloads_today,
        cache_hits_today=cache_hits_today,
        errors_today=errors_today,
        top_domains=top_domains,
        downloads_by_day=downloads_by_day,
    )


@router.post("/downloads/{log_id}/retry", status_code=202, summary="Retry a failed download (admin+)")
async def retry_download(
    log_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    row = await session.get(DownloadLog, log_id)
    if row is None or row.user_id != current_user.id:
        raise NotFoundError(f"Download {log_id} not found")
    return {"status": "queued", "url": row.url, "log_id": log_id}
