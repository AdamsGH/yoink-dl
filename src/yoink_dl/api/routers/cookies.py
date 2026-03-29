"""Cookie management endpoints - personal, pool, browser-extension submit."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yoink.core.api.deps import get_current_user, get_db
from yoink.core.api.exceptions import NotFoundError
from yoink.core.auth.rbac import require_role
from yoink.core.db.models import User, UserPermission, UserRole
from yoink_dl.api.schemas import (
    CookieCreate,
    CookieResponse,
    CookieSubmitRequest,
    CookieTokenResponse,
)
from yoink_dl.services import cookie_tokens as ct
from yoink_dl.services.cookies import CookieManager
from yoink_dl.storage.models import Cookie

router = APIRouter(tags=["downloader"])


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


@router.post("/cookies", response_model=CookieResponse, status_code=201, summary="Add cookie by content")
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
    rows = (await session.execute(select(Cookie).order_by(Cookie.domain))).scalars().all()
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
    rows = (await session.execute(q.order_by(Cookie.domain, Cookie.id))).scalars().all()
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
    """Upload a raw Netscape cookie file for the current user."""
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


@router.post("/cookies/{cookie_id}/validate", response_model=CookieResponse, summary="Re-validate cookie by HTTP request to domain")
async def validate_cookie(
    cookie_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CookieResponse:
    """Validate a stored cookie: structural check, then live GET request to the domain."""
    import httpx  # noqa: PLC0415
    from yoink_dl.services.cookies import validate_netscape  # noqa: PLC0415

    row = await session.get(Cookie, cookie_id)
    if row is None:
        raise NotFoundError(f"Cookie {cookie_id} not found")
    if current_user.role not in (UserRole.admin, UserRole.owner) and row.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your cookie")

    content = row.content or ""
    if not validate_netscape(content):
        row.is_valid = False
        await session.commit()
        await session.refresh(row)
        return CookieResponse.model_validate(row)

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

    is_valid = False
    try:
        async with httpx.AsyncClient(
            cookies=jar, follow_redirects=True, timeout=10.0,
            headers={"User-Agent": "Mozilla/5.0 (compatible; YoinkBot/1.0)"},
        ) as client:
            resp = await client.get(f"https://{row.domain}")
            is_valid = resp.status_code not in (401, 403)
    except Exception:
        is_valid = True  # network error - don't mark invalid

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
    if not is_admin and (row.user_id != current_user.id or row.is_pool):
        raise HTTPException(status_code=403, detail="Not your cookie")
    await session.delete(row)
    await session.commit()


@router.post("/cookies/token", response_model=CookieTokenResponse, summary="Generate one-time sync token for browser extension")
async def generate_cookie_token(
    current_user: User = Depends(get_current_user),
) -> CookieTokenResponse:
    """Generate a short-lived token for the browser extension to submit cookies."""
    token = ct.generate(current_user.id)
    return CookieTokenResponse(token=token, expires_in=ct.TTL, submit_url="/api/v1/dl/cookies/submit")


@router.post("/cookies/submit", status_code=204, summary="Submit cookies via one-time sync token (no auth)")
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

    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.now(timezone.utc)

    for domain, cookie_list in body.cookies.items():
        if not cookie_list:
            continue

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
            session.add(Cookie(user_id=user_id, domain=domain, content=content, is_valid=True, is_pool=False))
        else:
            existing.content = content
            existing.is_valid = True
            existing.is_pool = False
            existing.updated_at = now

    await session.commit()
