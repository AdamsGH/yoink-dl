"""Downloader plugin API - aggregates sub-routers.

Mounted at /api/v1/dl/ by the core API factory.
"""
from fastapi import APIRouter

from yoink_dl.api.routers.cookies import router as cookies_router
from yoink_dl.api.routers.downloads import router as downloads_router
from yoink_dl.api.routers.nsfw import router as nsfw_router

router = APIRouter(tags=["downloader"])
router.include_router(downloads_router)
router.include_router(cookies_router)
router.include_router(nsfw_router)
