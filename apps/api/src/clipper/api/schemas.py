from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from clipper.domain.editing_plan import CaptionConfig, EditingPlanV1


class StageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    status: str
    progress: float
    attempts: int
    error: dict[str, object] | None


class ClipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    approval_status: str
    plan: EditingPlanV1
    preview_path: str | None
    final_path: str | None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    original_filename: str
    status: str
    duration_seconds: float | None
    authorization_confirmed_at: datetime
    created_at: datetime
    stages: list[StageResponse]
    clips: list[ClipResponse]


class ApprovalRequest(BaseModel):
    approved: bool


class ProcessRequest(BaseModel):
    language: str | None = Field(default=None, pattern=r"^[a-z]{2}$")


class ClipStyleRequest(BaseModel):
    caption_config: CaptionConfig
    frame_style: Literal["blurred_background", "center_crop"]


class HealthResponse(BaseModel):
    status: str
    ffmpeg: bool
    ffprobe: bool
    editorial_provider: str
    transcription_provider: str
