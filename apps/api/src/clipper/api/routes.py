"""Stable API router assembled from resource-focused route modules."""

from fastapi import APIRouter

from clipper.api.clips import router as clips_router
from clipper.api.health import router as health_router
from clipper.api.projects import router as projects_router

router = APIRouter(prefix="/api")
router.include_router(health_router)
router.include_router(projects_router)
router.include_router(clips_router)
