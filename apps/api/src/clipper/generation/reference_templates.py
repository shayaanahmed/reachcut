"""Validated, reusable direction extracted from example clips."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from clipper.generation.contracts import VideoTemplateId


class TemplateBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    base_template: VideoTemplateId
    format: str = Field(min_length=1, max_length=100)
    tags: list[Annotated[str, Field(min_length=1, max_length=60)]] = Field(
        min_length=1, max_length=12
    )
    visual_style: str = Field(min_length=20, max_length=700)
    camera: str = Field(min_length=10, max_length=500)
    pacing: str = Field(min_length=10, max_length=500)
    story_structure: str = Field(min_length=10, max_length=700)
    caption_style: str = Field(min_length=1, max_length=300)
    suitable_for: str = Field(min_length=10, max_length=500)


class ReferenceTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[0-9a-f]{32}$")
    name: str = Field(min_length=1, max_length=100)
    source_url: str | None = None
    source_category: str | None = None
    status: Literal["pending", "ready", "failed"] = "pending"
    blueprint: TemplateBlueprint | None = None
    duration_seconds: float = 0
    error: str | None = None
    analysis_model: str | None = None
    video_url: str | None = None
    poster_url: str | None = None


class TemplateMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    reason: str = Field(min_length=10, max_length=500)
