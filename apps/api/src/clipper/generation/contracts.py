from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

AspectRatio = Literal["9:16", "16:9", "1:1"]
GenerationQuality = Literal["draft", "1080p"]
VideoTemplateId = Literal[
    "cinematic_story",
    "animated_adventure",
    "anime_story",
    "stylized_3d",
    "dark_mystery",
    "documentary_realism",
]
CameraMotion = Literal[
    "none",
    "static",
    "focus_shift",
    "dolly_in",
    "dolly_out",
    "dolly_left",
    "dolly_right",
    "jib_up",
    "jib_down",
]
JobStatus = Literal["queued", "planning", "rendering", "finishing", "complete", "failed"]


class StoryCharacter(BaseModel):
    """A reusable identity anchor that must remain unchanged between scenes."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    name: str = Field(min_length=1, max_length=80)
    role: str = Field(min_length=1, max_length=120)
    appearance_anchor: str = Field(min_length=20, max_length=700)
    wardrobe_anchor: str = Field(min_length=5, max_length=400)
    voice_anchor: str = Field(min_length=5, max_length=300)


class StoryCrop(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: float = Field(default=0, ge=0, lt=1)
    y: float = Field(default=0, ge=0, lt=1)
    width: float = Field(default=1, ge=0.1, le=1)
    height: float = Field(default=1, ge=0.1, le=1)

    @model_validator(mode="after")
    def inside_frame(self) -> StoryCrop:
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("crop must stay inside the source frame")
        return self


class StoryScene(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=1, le=20)
    title: str = Field(min_length=1, max_length=100)
    story_beat: str = Field(min_length=8, max_length=500)
    narration: str = Field(default="", max_length=500)
    visual_prompt: str = Field(min_length=40, max_length=2_500)
    character_ids: list[str] = Field(default_factory=list, max_length=6)
    crop: StoryCrop | None = None
    trim_start_seconds: float = Field(default=0, ge=0, le=10)
    trim_end_seconds: float | None = Field(default=None, gt=0, le=10)
    playback_speed: float = Field(default=1, ge=0.5, le=2)
    opening_frame: str = Field(default="", max_length=700)
    ending_frame: str = Field(default="", max_length=700)
    camera_motion: CameraMotion = "none"
    duration_seconds: Literal[5, 10] = 5
    seed: int = Field(ge=0, le=2_147_483_647)

    @model_validator(mode="after")
    def valid_edit_window(self) -> StoryScene:
        end = self.trim_end_seconds if self.trim_end_seconds is not None else self.duration_seconds
        if not self.trim_start_seconds < end <= self.duration_seconds:
            raise ValueError("scene edit window must be inside the generated clip")
        return self

    @property
    def output_duration_seconds(self) -> float:
        end = self.trim_end_seconds if self.trim_end_seconds is not None else self.duration_seconds
        return (end - self.trim_start_seconds) / self.playback_speed


class StoryPlan(BaseModel):
    """Structured direction produced by Ollama and reviewed before GPU rendering."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=140)
    logline: str = Field(min_length=10, max_length=350)
    visual_style: str = Field(min_length=20, max_length=700)
    negative_prompt: str = Field(min_length=10, max_length=900)
    continuity_notes: str = Field(default="", max_length=1200)
    hook_caption: str = Field(default="", max_length=100)
    end_caption: str = Field(default="", max_length=100)
    characters: list[StoryCharacter] = Field(default_factory=list, max_length=8)
    scenes: list[StoryScene] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_continuity(self) -> StoryPlan:
        ids = [character.id for character in self.characters]
        if len(ids) != len(set(ids)):
            raise ValueError("character ids must be unique")
        valid_ids = set(ids)
        for expected_index, scene in enumerate(self.scenes, start=1):
            if scene.index != expected_index:
                raise ValueError("scene indexes must be contiguous and start at 1")
            if not scene.character_ids and self.characters:
                description = f"{scene.visual_prompt} {scene.story_beat}".casefold()
                # Recover dropped references only for characters actually mentioned in the shot.
                role_nouns = [
                    character.role.casefold().split()[-1] for character in self.characters
                ]
                scene.character_ids = []
                for character, noun in zip(self.characters, role_nouns, strict=True):
                    aliases = [character.id.replace("_", " "), character.name, character.role]
                    if role_nouns.count(noun) == 1 and noun not in {
                        "character",
                        "person",
                        "hero",
                        "protagonist",
                        "villain",
                    }:
                        aliases.append(noun)
                    if any(
                        re.search(r"\b" + re.escape(alias.casefold()) + r"\b", description)
                        for alias in aliases
                    ):
                        scene.character_ids.append(character.id)
                scene.character_ids = scene.character_ids[:6]
            unknown = set(scene.character_ids) - valid_ids
            if unknown:
                raise ValueError(f"scene {scene.index} references unknown characters")
        return self

    @property
    def duration_seconds(self) -> int:
        return sum(scene.duration_seconds for scene in self.scenes)

    @property
    def output_duration_seconds(self) -> float:
        return sum(scene.output_duration_seconds for scene in self.scenes)


@dataclass(frozen=True)
class StoryPlanningRequest:
    story: str
    template: VideoTemplateId
    aspect_ratio: AspectRatio
    target_duration_seconds: int
    template_guidance: str = ""
    shot_mode: Literal["auto", "continuous", "story"] = "auto"
    narration_enabled: bool = False


@dataclass(frozen=True)
class SceneGenerationRequest:
    prompt: str
    negative_prompt: str
    aspect_ratio: AspectRatio
    quality: GenerationQuality
    duration_seconds: Literal[5, 10]
    camera_motion: CameraMotion
    seed: int
    reference_image: Path | None = None


@dataclass(frozen=True)
class SceneGenerationResult:
    output: Path
    provider: str
    width: int
    height: int


class StoryDirector(Protocol):
    def plan(self, request: StoryPlanningRequest) -> StoryPlan: ...


class VideoGenerationProvider(Protocol):
    @property
    def identity(self) -> str: ...

    def generate_scene(
        self, request: SceneGenerationRequest, output: Path
    ) -> SceneGenerationResult: ...

    def generate_character_reference(self, prompt: str, output: Path, seed: int) -> Path: ...


class VideoGenerationBusyError(RuntimeError):
    """The renderer is occupied; preserve the job and retry when its slot is free."""
