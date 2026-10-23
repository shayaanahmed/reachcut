"""Stable API router assembled from resource-focused route modules."""

from fastapi import APIRouter

from clipper.api.automations import router as automations_router
from clipper.api.clips import router as clips_router
from clipper.api.content_series import router as content_series_router
from clipper.api.distribution import router as distribution_router
from clipper.api.growth import router as growth_router
from clipper.api.health import router as health_router
from clipper.api.informative import router as informative_router
from clipper.api.projects import router as projects_router
from clipper.api.publications import router as publications_router
from clipper.api.settings import router as settings_router
from clipper.api.short_studio import router as short_studio_router
from clipper.api.social_accounts import router as social_accounts_router
from clipper.api.source_workflows import router as source_workflows_router
from clipper.api.video_generation import router as video_generation_router

router = APIRouter(prefix="/api")
router.include_router(automations_router)
router.include_router(health_router)
router.include_router(projects_router)
router.include_router(clips_router)
router.include_router(distribution_router)
router.include_router(publications_router)
router.include_router(settings_router)
router.include_router(social_accounts_router)
router.include_router(video_generation_router)

router.include_router(informative_router)

router.include_router(content_series_router)

router.include_router(short_studio_router)

router.include_router(growth_router)

router.include_router(source_workflows_router)
