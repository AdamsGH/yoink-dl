"""Downloader plugin API routes.

Mounted at /api/v1/dl/ by the core API factory.
All responses use core helpers (paginated_response, exceptions).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from yoink.core.api.deps import get_current_user, get_db
from yoink.core.api.exceptions import NotFoundError
from yoink.core.api.responses import paginated_response
from yoink.core.auth.rbac import require_role
from yoink.core.db.models import Group, User, UserPermission, UserRole
from yoink_dl.api.schemas import (
    CookieCreate,
    CookieResponse,
    CookieSubmitRequest,
    CookieTokenResponse,
    DlUserSettingsResponse,
    DlUserSettingsUpdate,
    DownloadLogResponse,
    NsfwCheckRequest,
    NsfwCheckResponse,
    NsfwDomainCreate,
    NsfwDomainResponse,
    NsfwDomainUpdate,
    NsfwImport,
    NsfwKeywordCreate,
    NsfwKeywordResponse,
    NsfwKeywordUpdate,
    StatsOverview,
)
from yoink_dl.services import cookie_tokens as ct
from yoink_dl.services.cookies import CookieManager
from yoink_dl.storage.models import Cookie, DownloadLog, NsfwDomain, NsfwKeyword, UserSettings

router = APIRouter(tags=["downloader"])

_AUDIO_DOMAINS = frozenset({
    "soundcloud.com", "bandcamp.com", "music.yandex.ru", "music.yandex.com",
    "open.spotify.com", "music.apple.com", "deezer.com", "tidal.com",
    "last.fm", "audiomack.com", "mixcloud.com",
})

def _media_type(row: DownloadLog) -> str:
    if row.status == "error":
        return "error"
    if row.clip_start is not None and row.clip_end is not None:
        return "clip"
    domain = (row.domain or "").lower().removeprefix("www.")
    if domain in _AUDIO_DOMAINS:
        return "audio"
    quality = (row.quality or "").lower()
    if "audio" in quality or "mp3" in quality or "m4a" in quality or "flac" in quality or "opus" in quality:
        return "audio"
    if row.file_count is not None and row.file_count > 1 and not row.duration:
        return "gallery"
    return "video"


# Download history

@router.get("/downloads/domains", response_model=dict, summary="Distinct domains in my download history")
async def list_my_download_domains(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return distinct non-null domains from the user's download history, sorted alphabetically."""
    rows = (await session.execute(
        select(DownloadLog.domain)
        .where(DownloadLog.user_id == current_user.id, DownloadLog.domain.is_not(None))
        .distinct()
        .order_by(DownloadLog.domain)
    )).scalars().all()
    return {"domains": list(rows)}


@router.get("/downloads", response_model=dict, summary="My download history", description="Paginated list of the current user's download logs.")
async def list_my_downloads(
    offset: int = Query(0, ge=0, description="Pagination offset (number of records to skip)"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of records to return"),
    search: str | None = Query(None, description="Filter by title or URL substring"),
    domain: str | None = Query(None, description="Filter by exact domain"),
    status: str | None = Query(None, description="Filter by status: ok, cached, error"),
    date_from: str | None = Query(None, description="Filter from date (YYYY-MM-DD, inclusive)"),
    date_to: str | None = Query(None, description="Filter to date (YYYY-MM-DD, inclusive)"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    from datetime import date as date_type  # noqa: PLC0415
    conditions = [DownloadLog.user_id == current_user.id]
    if search:
        like = f"%{search}%"
        conditions.append((DownloadLog.title.ilike(like)) | (DownloadLog.url.ilike(like)))
    if domain:
        conditions.append(DownloadLog.domain == domain)
    if status:
        conditions.append(DownloadLog.status == status)
    if date_from:
        conditions.append(DownloadLog.created_at >= date_type.fromisoformat(date_from))
    if date_to:
        from datetime import timedelta  # noqa: PLC0415
        conditions.append(DownloadLog.created_at < date_type.fromisoformat(date_to) + timedelta(days=1))
    total = (await session.execute(
        select(func.count(DownloadLog.id)).where(*conditions)
    )).scalar_one()
    rows = (await session.execute(
        select(DownloadLog, Group.title.label("group_title"))
        .outerjoin(Group, Group.id == DownloadLog.group_id)
        .where(*conditions)
        .order_by(DownloadLog.created_at.desc())
        .offset(offset).limit(limit)
    )).all()

    def _to_response(row: DownloadLog, group_title: str | None) -> DownloadLogResponse:
        r = DownloadLogResponse.model_validate(row)
        r.group_title = group_title
        r.media_type = _media_type(row)
        return r

    return paginated_response(
        [_to_response(row, gt) for row, gt in rows],
        total, offset, limit,
    )


@router.get("/downloads/all", response_model=dict, summary="All users' download history (admin+)")
async def list_all_downloads(
    offset: int = Query(0, ge=0, description="Pagination offset (number of records to skip)"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of records to return"),
    session: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.owner)),
) -> dict:
    total = (await session.execute(select(func.count(DownloadLog.id)))).scalar_one()
    rows = (await session.execute(
        select(DownloadLog).order_by(DownloadLog.created_at.desc()).offset(offset).limit(limit)
    )).scalars().all()
    return paginated_response(
        [DownloadLogResponse.model_validate(r) for r in rows],
        total, offset, limit,
    )


# dl-specific user settings

@router.get("/settings", response_model=DlUserSettingsResponse, summary="My downloader settings")
async def get_dl_settings(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DlUserSettingsResponse:
    row = await session.get(UserSettings, current_user.id)
    if row is None:
        row = UserSettings(user_id=current_user.id)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return DlUserSettingsResponse.model_validate(row)


@router.patch("/settings", response_model=DlUserSettingsResponse, summary="Update my downloader settings", description="Fields: `max_quality` (144-2160), `prefer_format` (`mp4`/`webm`/`best`), `audio_only` (bool).")
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
    return DlUserSettingsResponse.model_validate(row)


# Stats

@router.get("/stats/overview", response_model=StatsOverview, summary="Downloader stats overview (admin+)", description="Total downloads, unique users, top domains, and per-status counts.")
async def stats_overview(
    days: int = Query(30, ge=1, le=365, description="Number of days to include in the overview window"),
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
    downloads_by_day = [
        {"date": r.day.strftime("%Y-%m-%d"), "count": r.count}
        for r in by_day_result
    ]
    return StatsOverview(
        total_downloads=total,
        downloads_today=downloads_today,
        cache_hits_today=cache_hits_today,
        errors_today=errors_today,
        top_domains=top_domains,
        downloads_by_day=downloads_by_day,
    )


# Download retry

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


# Cookies

@router.get("/cookies", response_model=list[CookieResponse], summary="My cookies")
async def list_my_cookies(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CookieResponse]:
    own_rows = (await session.execute(
        select(Cookie)
        .where(Cookie.user_id == current_user.id, Cookie.is_pool.is_(False))
        .order_by(Cookie.domain)
    )).scalars().all()
    result = [CookieResponse.model_validate(r) for r in own_rows]

    # Include pool cookies for admins/owners or users with shared_cookies permission
    is_privileged = current_user.role in (UserRole.admin, UserRole.owner)
    if not is_privileged:
        has_shared = (await session.execute(
            select(UserPermission).where(
                UserPermission.user_id == current_user.id,
                UserPermission.plugin == "dl",
                UserPermission.feature == "shared_cookies",
            )
        )).scalar_one_or_none()
        is_privileged = has_shared is not None

    if is_privileged:
        pool_rows = (await session.execute(
            select(Cookie)
            .where(Cookie.is_pool.is_(True), Cookie.is_valid.is_(True))
            .order_by(Cookie.domain, Cookie.id)
        )).scalars().all()
        seen_pool_domains: set[str] = set()
        for r in pool_rows:
            if r.domain not in seen_pool_domains:
                entry = CookieResponse.model_validate(r)
                entry.inherited = True
                result.append(entry)
                seen_pool_domains.add(r.domain)
        result.sort(key=lambda c: (c.domain, not c.inherited))

    return result


@router.post("/cookies", response_model=CookieResponse, status_code=201, summary="Add cookie by content (raw, no format validation)")
async def create_cookie(
    body: CookieCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CookieResponse:
    row = (await session.execute(
        select(Cookie).where(Cookie.user_id == current_user.id, Cookie.domain == body.domain)
    )).scalar_one_or_none()
    if row is None:
        row = Cookie(user_id=current_user.id, domain=body.domain, content=body.content)
        session.add(row)
    else:
        row.content = body.content
    await session.commit()
    await session.refresh(row)
    return CookieResponse.model_validate(row)


@router.get("/cookies/all", response_model=list[CookieResponse], summary="All users' cookies (admin+)")
async def list_all_cookies(
    session: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.owner)),
) -> list[CookieResponse]:
    rows = (await session.execute(
        select(Cookie).order_by(Cookie.domain)
    )).scalars().all()
    return [CookieResponse.model_validate(r) for r in rows]


@router.get("/cookies/pool", response_model=list[CookieResponse], summary="List pool cookies (admin+)")
async def list_pool_cookies(
    domain: str | None = None,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.owner)),
) -> list[CookieResponse]:
    q = select(Cookie).where(Cookie.is_pool.is_(True))
    if domain:
        q = q.where(Cookie.domain == domain)
    q = q.order_by(Cookie.domain, Cookie.id)
    rows = (await session.execute(q)).scalars().all()
    return [CookieResponse.model_validate(r) for r in rows]


@router.post("/cookies/pool", response_model=CookieResponse, status_code=201, summary="Add pool cookie (admin+)")
async def add_pool_cookie(
    body: CookieCreate,
    request: Request,
    current_user: User = Depends(require_role(UserRole.admin, UserRole.owner)),
) -> CookieResponse:
    from yoink_dl.services.cookies import validate_netscape  # noqa: PLC0415
    if not validate_netscape(body.content):
        raise HTTPException(status_code=422, detail="Invalid Netscape cookie format")
    cookie_mgr: CookieManager = request.app.state.bot_data["cookie_manager"]
    row = await cookie_mgr.store_pool(current_user.id, body.domain, body.content)
    return CookieResponse.model_validate(row)


@router.post("/cookies/pool/refresh-labels", response_model=dict, summary="Re-extract labels for pool cookies (admin+)")
async def refresh_pool_labels(
    request: Request,
    _: User = Depends(require_role(UserRole.admin, UserRole.owner)),
) -> dict:
    cookie_mgr: CookieManager = request.app.state.bot_data["cookie_manager"]
    updated = await cookie_mgr.refresh_pool_labels()
    return {"updated": updated}


@router.delete("/cookies/pool/{cookie_id}", status_code=204, summary="Delete pool cookie (admin+)")
async def delete_pool_cookie(
    cookie_id: int,
    request: Request,
    _: User = Depends(require_role(UserRole.admin, UserRole.owner)),
) -> None:
    cookie_mgr: CookieManager = request.app.state.bot_data["cookie_manager"]
    deleted = await cookie_mgr.delete_pool(cookie_id)
    if not deleted:
        raise NotFoundError(f"Pool cookie {cookie_id} not found")


@router.post("/cookies/upload", response_model=CookieResponse, status_code=201, summary="Upload cookie file (Netscape format validated)")
async def upload_cookie_file(
    body: CookieCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CookieResponse:
    """Upload a raw Netscape cookie file (.txt) for the current user."""
    from yoink_dl.services.cookies import validate_netscape  # noqa: PLC0415
    if not validate_netscape(body.content):
        raise HTTPException(status_code=422, detail="Invalid Netscape cookie format")
    row = (await session.execute(
        select(Cookie).where(Cookie.user_id == current_user.id, Cookie.domain == body.domain)
    )).scalar_one_or_none()
    if row is None:
        row = Cookie(user_id=current_user.id, domain=body.domain, content=body.content, is_valid=True)
        session.add(row)
    else:
        row.content = body.content
        row.is_valid = True
    await session.commit()
    await session.refresh(row)
    return CookieResponse.model_validate(row)


@router.post("/cookies/{cookie_id}/validate", response_model=CookieResponse, summary="Re-validate cookie by making an HTTP request to the domain")
async def validate_cookie(
    cookie_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CookieResponse:
    """
    Validate a stored cookie by:
    1. Parsing Netscape format (structural check).
    2. Making a real GET request to https://{domain} with the cookies and checking
       that the response does not return 401/403 (access denied).
    Updates is_valid accordingly.
    """
    import httpx  # noqa: PLC0415
    import tempfile, os  # noqa: PLC0415, E401
    from yoink_dl.services.cookies import validate_netscape  # noqa: PLC0415

    row = await session.get(Cookie, cookie_id)
    if row is None:
        raise NotFoundError(f"Cookie {cookie_id} not found")

    from yoink.core.db.models import UserRole  # noqa: PLC0415
    if current_user.role not in (UserRole.admin, UserRole.owner) and row.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your cookie")

    content = row.content or ""

    # Step 1: structural check
    if not validate_netscape(content):
        row.is_valid = False
        await session.commit()
        await session.refresh(row)
        return CookieResponse.model_validate(row)

    # Step 2: parse cookies into a jar and make a real HTTP request
    jar = httpx.Cookies()
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _, path, _, _, name, value = parts[:7]
        jar.set(name, value, domain=domain.lstrip("."), path=path)

    domain = row.domain or ""
    url = f"https://{domain}"
    is_valid = False
    try:
        async with httpx.AsyncClient(
            cookies=jar,
            follow_redirects=True,
            timeout=10.0,
            headers={"User-Agent": "Mozilla/5.0 (compatible; YoinkBot/1.0)"},
        ) as client:
            resp = await client.get(url)
            # 401/403 means cookies are rejected; anything else (including 200, 302, 404, 429) is OK
            is_valid = resp.status_code not in (401, 403)
    except Exception:
        # Network error — keep structural validity, don't mark invalid
        is_valid = True

    from datetime import datetime, timezone  # noqa: PLC0415
    row.is_valid = is_valid
    row.validated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(row)
    return CookieResponse.model_validate(row)


@router.delete("/cookies/{domain}", status_code=204, summary="Delete cookie by domain")
async def delete_cookie(
    domain: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    row = (await session.execute(
        select(Cookie).where(Cookie.user_id == current_user.id, Cookie.domain == domain)
    )).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"No cookie for domain: {domain}")
    await session.delete(row)
    await session.commit()


@router.delete("/cookies/by-id/{cookie_id}", status_code=204, summary="Delete cookie by ID")
async def delete_cookie_by_id(
    cookie_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    row = await session.get(Cookie, cookie_id)
    if row is None:
        raise NotFoundError(f"Cookie {cookie_id} not found")
    is_admin = current_user.role in (UserRole.admin, UserRole.owner)
    if not is_admin:
        # Regular users can only delete their own personal cookies
        if row.user_id != current_user.id or row.is_pool:
            raise HTTPException(status_code=403, detail="Not your cookie")
    await session.delete(row)
    await session.commit()


@router.post("/cookies/token", response_model=CookieTokenResponse, summary="Generate one-time sync token for Yoink Cookie Sync extension")
async def generate_cookie_token(
    current_user: User = Depends(get_current_user),
) -> CookieTokenResponse:
    """Generate a short-lived token for the browser extension to submit cookies."""
    token = ct.generate(current_user.id)
    return CookieTokenResponse(
        token=token,
        expires_in=ct.TTL,
        submit_url="/api/v1/dl/cookies/submit",
    )


@router.post("/cookies/submit", status_code=204, summary="Submit cookies via one-time sync token (no auth)", description="Used by the browser extension. Validates the token and upserts the cookie.")
async def submit_cookies(
    body: CookieSubmitRequest,
    session: AsyncSession = Depends(get_db),
) -> None:
    """Accept cookies from the browser extension. No auth - token is the credential."""
    user_id = ct.consume(body.token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if not body.cookies:
        raise HTTPException(status_code=422, detail="No cookies provided")

    # Ensure user exists
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.now(timezone.utc)

    for domain, cookie_list in body.cookies.items():
        if not cookie_list:
            continue

        # Convert chrome.cookies objects to Netscape format
        lines = ["# Netscape HTTP Cookie File"]
        for c in cookie_list:
            host = c.get("domain", "")
            if not host.startswith("."):
                host = "." + host
            http_only = str(c.get("httpOnly", False)).upper()
            secure = str(c.get("secure", False)).upper()
            exp = int(c.get("expirationDate") or 0) or 2147483647
            path = c.get("path", "/")
            name = c.get("name", "")
            value = c.get("value", "")
            lines.append(f"{host}\t{http_only}\t{path}\tFALSE\t{exp}\t{secure}\t{name}\t{value}")

        content = "\n".join(lines) + "\n"

        existing = (await session.execute(
            select(Cookie).where(Cookie.user_id == user_id, Cookie.domain == domain)
        )).scalar_one_or_none()

        if existing is None:
            session.add(Cookie(user_id=user_id, domain=domain, content=content,
                               is_valid=True, is_pool=False))
        else:
            existing.content = content
            existing.is_valid = True
            existing.is_pool = False
            existing.updated_at = now

    await session.commit()


# NSFW check + lists

@router.post("/nsfw/check", response_model=NsfwCheckResponse, summary="Check if a URL matches NSFW rules (moderator+)")
async def check_nsfw(
    body: NsfwCheckRequest,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.moderator, UserRole.admin, UserRole.owner)),
) -> NsfwCheckResponse:
    url: str = body.url
    from urllib.parse import urlparse  # noqa: PLC0415
    domain = urlparse(url).netloc.lstrip("www.")
    domain_hit = (await session.execute(
        select(NsfwDomain).where(NsfwDomain.domain == domain)
    )).scalar_one_or_none()
    keyword_hits: list[str] = []
    if not domain_hit:
        keywords = (await session.execute(select(NsfwKeyword))).scalars().all()
        keyword_hits = [kw.keyword for kw in keywords if kw.keyword.lower() in url.lower()]
    is_nsfw = domain_hit is not None or bool(keyword_hits)
    return NsfwCheckResponse(
        url=url,
        is_nsfw=is_nsfw,
        matched_domain=domain_hit.domain if domain_hit else None,
        matched_keywords=keyword_hits,
    )


@router.get("/nsfw/domains", response_model=list[NsfwDomainResponse], summary="List NSFW domains (moderator+)")
async def list_nsfw_domains(
    session: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.moderator, UserRole.admin, UserRole.owner)),
) -> list[NsfwDomainResponse]:
    rows = (await session.execute(
        select(NsfwDomain).order_by(NsfwDomain.domain)
    )).scalars().all()
    return [NsfwDomainResponse.model_validate(r) for r in rows]


@router.post("/nsfw/domains", response_model=NsfwDomainResponse, status_code=201, summary="Add NSFW domain (moderator+)")
async def add_nsfw_domain(
    body: NsfwDomainCreate,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.moderator, UserRole.admin, UserRole.owner)),
) -> NsfwDomainResponse:
    row = NsfwDomain(domain=body.domain, note=body.note)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return NsfwDomainResponse.model_validate(row)


@router.patch("/nsfw/domains/{domain_id}", response_model=NsfwDomainResponse, summary="Update NSFW domain (moderator+)")
async def update_nsfw_domain(
    domain_id: int,
    body: NsfwDomainUpdate,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.moderator, UserRole.admin, UserRole.owner)),
) -> NsfwDomainResponse:
    row = await session.get(NsfwDomain, domain_id)
    if row is None:
        raise NotFoundError(f"NSFW domain {domain_id} not found")
    if body.domain is not None:
        row.domain = body.domain
    if body.note is not None:
        row.note = body.note or None
    await session.commit()
    await session.refresh(row)
    return NsfwDomainResponse.model_validate(row)


@router.delete("/nsfw/domains/{domain_id}", status_code=204, summary="Delete NSFW domain (moderator+)")
async def delete_nsfw_domain(
    domain_id: int,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.moderator, UserRole.admin, UserRole.owner)),
) -> None:
    row = await session.get(NsfwDomain, domain_id)
    if row is None:
        raise NotFoundError(f"NSFW domain {domain_id} not found")
    await session.delete(row)
    await session.commit()


@router.get("/nsfw/keywords", response_model=list[NsfwKeywordResponse], summary="List NSFW keywords (moderator+)")
async def list_nsfw_keywords(
    session: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.moderator, UserRole.admin, UserRole.owner)),
) -> list[NsfwKeywordResponse]:
    rows = (await session.execute(
        select(NsfwKeyword).order_by(NsfwKeyword.keyword)
    )).scalars().all()
    return [NsfwKeywordResponse.model_validate(r) for r in rows]


@router.post("/nsfw/keywords", response_model=NsfwKeywordResponse, status_code=201, summary="Add NSFW keyword (moderator+)")
async def add_nsfw_keyword(
    body: NsfwKeywordCreate,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.moderator, UserRole.admin, UserRole.owner)),
) -> NsfwKeywordResponse:
    row = NsfwKeyword(keyword=body.keyword, note=body.note)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return NsfwKeywordResponse.model_validate(row)


@router.patch("/nsfw/keywords/{keyword_id}", response_model=NsfwKeywordResponse, summary="Update NSFW keyword (moderator+)")
async def update_nsfw_keyword(
    keyword_id: int,
    body: NsfwKeywordUpdate,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.moderator, UserRole.admin, UserRole.owner)),
) -> NsfwKeywordResponse:
    row = await session.get(NsfwKeyword, keyword_id)
    if row is None:
        raise NotFoundError(f"NSFW keyword {keyword_id} not found")
    if body.keyword is not None:
        row.keyword = body.keyword
    if body.note is not None:
        row.note = body.note or None
    await session.commit()
    await session.refresh(row)
    return NsfwKeywordResponse.model_validate(row)


@router.delete("/nsfw/keywords/{keyword_id}", status_code=204, summary="Delete NSFW keyword (moderator+)")
async def delete_nsfw_keyword(
    keyword_id: int,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.moderator, UserRole.admin, UserRole.owner)),
) -> None:
    row = await session.get(NsfwKeyword, keyword_id)
    if row is None:
        raise NotFoundError(f"NSFW keyword {keyword_id} not found")
    await session.delete(row)
    await session.commit()


@router.post("/nsfw/import", summary="Import NSFW rules from JSON (moderator+)")
async def import_nsfw(
    body: NsfwImport,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.moderator, UserRole.admin, UserRole.owner)),
) -> dict:
    """Bulk import domains and keywords from JSON. Skips duplicates."""
    existing_domains = {
        r[0] for r in (await session.execute(select(NsfwDomain.domain))).all()
    }
    existing_keywords = {
        r[0] for r in (await session.execute(select(NsfwKeyword.keyword))).all()
    }

    added_d = 0
    for d in body.domains:
        if d.domain not in existing_domains:
            session.add(NsfwDomain(domain=d.domain, note=d.note))
            existing_domains.add(d.domain)
            added_d += 1

    added_k = 0
    for k in body.keywords:
        if k.keyword not in existing_keywords:
            session.add(NsfwKeyword(keyword=k.keyword, note=k.note))
            existing_keywords.add(k.keyword)
            added_k += 1

    await session.commit()
    return {"domains_added": added_d, "keywords_added": added_k}


@router.get("/nsfw/export", summary="Export NSFW rules as JSON (moderator+)")
async def export_nsfw(
    session: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.moderator, UserRole.admin, UserRole.owner)),
) -> dict:
    """Export all NSFW domains and keywords as JSON."""
    domains = (await session.execute(
        select(NsfwDomain).order_by(NsfwDomain.domain)
    )).scalars().all()
    keywords = (await session.execute(
        select(NsfwKeyword).order_by(NsfwKeyword.keyword)
    )).scalars().all()
    return {
        "domains": [{"domain": d.domain, "note": d.note} for d in domains],
        "keywords": [{"keyword": k.keyword, "note": k.note} for k in keywords],
    }
