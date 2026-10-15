"""Local story-to-video contracts and reusable visual story templates."""

from clipper.generation.contracts import (
    AspectRatio,
    CameraMotion,
    GenerationQuality,
    JobStatus,
    SceneGenerationRequest,
    SceneGenerationResult,
    StoryCharacter,
    StoryDirector,
    StoryPlan,
    StoryPlanningRequest,
    StoryScene,
    VideoGenerationBusyError,
    VideoGenerationProvider,
    VideoTemplateId,
)
from clipper.generation.templates import VIDEO_TEMPLATES, VideoTemplateDefinition

__all__ = [
    "VIDEO_TEMPLATES",
    "AspectRatio",
    "CameraMotion",
    "GenerationQuality",
    "JobStatus",
    "SceneGenerationRequest",
    "SceneGenerationResult",
    "StoryCharacter",
    "StoryDirector",
    "StoryPlan",
    "StoryPlanningRequest",
    "StoryScene",
    "VideoGenerationBusyError",
    "VideoGenerationProvider",
    "VideoTemplateDefinition",
    "VideoTemplateId",
]
