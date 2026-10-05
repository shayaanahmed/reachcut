"""Stable API router assembled from resource-focused route modules."""

from fastapi import APIRouter

from clipper.api.clips import router as clips_router
from clipper.api.discovery import router as discovery_router
from clipper.api.health import router as health_router
from clipper.api.projects import router as projects_router
from clipper.api.publications import router as publications_router
from clipper.api.social_accounts import router as social_accounts_router

router = APIRouter(prefix="/api")
router.include_router(health_router)
router.include_router(discovery_router)
router.include_router(projects_router)
router.include_router(clips_router)
router.include_router(publications_router)
router.include_router(social_accounts_router)
