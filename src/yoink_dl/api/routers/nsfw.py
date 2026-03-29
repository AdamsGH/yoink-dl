"""NSFW rules management - domains, keywords, import/export."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yoink.core.api.deps import get_db
from yoink.core.api.exceptions import NotFoundError
from yoink.core.auth.rbac import require_role
from yoink.core.db.models import User, UserRole
from yoink_dl.api.schemas import (
    NsfwCheckRequest,
    NsfwCheckResponse,
    NsfwDomainCreate,
    NsfwDomainResponse,
    NsfwDomainUpdate,
    NsfwImport,
    NsfwKeywordCreate,
    NsfwKeywordResponse,
    NsfwKeywordUpdate,
)
from yoink_dl.storage.models import NsfwDomain, NsfwKeyword

router = APIRouter(tags=["downloader"])

_MOD = (UserRole.moderator, UserRole.admin, UserRole.owner)


@router.post("/nsfw/check", response_model=NsfwCheckResponse, summary="Check if a URL matches NSFW rules (moderator+)")
async def check_nsfw(
    body: NsfwCheckRequest,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*_MOD)),
) -> NsfwCheckResponse:
    from urllib.parse import urlparse  # noqa: PLC0415
    domain = urlparse(body.url).netloc.lstrip("www.")
    domain_hit = (await session.execute(
        select(NsfwDomain).where(NsfwDomain.domain == domain)
    )).scalar_one_or_none()
    keyword_hits: list[str] = []
    if not domain_hit:
        keywords = (await session.execute(select(NsfwKeyword))).scalars().all()
        keyword_hits = [kw.keyword for kw in keywords if kw.keyword.lower() in body.url.lower()]
    is_nsfw = domain_hit is not None or bool(keyword_hits)
    return NsfwCheckResponse(
        url=body.url,
        is_nsfw=is_nsfw,
        matched_domain=domain_hit.domain if domain_hit else None,
        matched_keywords=keyword_hits,
    )


@router.get("/nsfw/domains", response_model=list[NsfwDomainResponse], summary="List NSFW domains (moderator+)")
async def list_nsfw_domains(
    session: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*_MOD)),
) -> list[NsfwDomainResponse]:
    rows = (await session.execute(select(NsfwDomain).order_by(NsfwDomain.domain))).scalars().all()
    return [NsfwDomainResponse.model_validate(r) for r in rows]


@router.post("/nsfw/domains", response_model=NsfwDomainResponse, status_code=201, summary="Add NSFW domain (moderator+)")
async def add_nsfw_domain(
    body: NsfwDomainCreate,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*_MOD)),
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
    _: User = Depends(require_role(*_MOD)),
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
    _: User = Depends(require_role(*_MOD)),
) -> None:
    row = await session.get(NsfwDomain, domain_id)
    if row is None:
        raise NotFoundError(f"NSFW domain {domain_id} not found")
    await session.delete(row)
    await session.commit()


@router.get("/nsfw/keywords", response_model=list[NsfwKeywordResponse], summary="List NSFW keywords (moderator+)")
async def list_nsfw_keywords(
    session: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*_MOD)),
) -> list[NsfwKeywordResponse]:
    rows = (await session.execute(select(NsfwKeyword).order_by(NsfwKeyword.keyword))).scalars().all()
    return [NsfwKeywordResponse.model_validate(r) for r in rows]


@router.post("/nsfw/keywords", response_model=NsfwKeywordResponse, status_code=201, summary="Add NSFW keyword (moderator+)")
async def add_nsfw_keyword(
    body: NsfwKeywordCreate,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*_MOD)),
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
    _: User = Depends(require_role(*_MOD)),
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
    _: User = Depends(require_role(*_MOD)),
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
    _: User = Depends(require_role(*_MOD)),
) -> dict:
    """Bulk import domains and keywords. Skips duplicates."""
    existing_domains = {r[0] for r in (await session.execute(select(NsfwDomain.domain))).all()}
    existing_keywords = {r[0] for r in (await session.execute(select(NsfwKeyword.keyword))).all()}

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
    _: User = Depends(require_role(*_MOD)),
) -> dict:
    """Export all NSFW domains and keywords as JSON."""
    domains = (await session.execute(select(NsfwDomain).order_by(NsfwDomain.domain))).scalars().all()
    keywords = (await session.execute(select(NsfwKeyword).order_by(NsfwKeyword.keyword))).scalars().all()
    return {
        "domains": [{"domain": d.domain, "note": d.note} for d in domains],
        "keywords": [{"keyword": k.keyword, "note": k.note} for k in keywords],
    }
