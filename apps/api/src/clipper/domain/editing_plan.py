from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Seconds = Annotated[float, Field(ge=0)]
Score = Annotated[int, Field(ge=0, le=100)]
Hashtag = Annotated[str, Field(pattern=r"^#[^\s#]{1,39}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TimeRange(StrictModel):
    start_seconds: Seconds
    end_seconds: Seconds

    @model_validator(mode="after")
    def ordered(self) -> TimeRange:
        if self.end_seconds <= self.start_seconds:
            raise ValueError("end_seconds must be greater than start_seconds")
        return self


class Scores(StrictModel):
    overall: Score
    hook: Score
    clarity: Score
    payoff: Score
    visual_interest: Score


class Hook(TimeRange):
    text: Annotated[str, Field(min_length=1, max_length=160)]


class Emphasis(TimeRange):
    words: Annotated[list[str], Field(min_length=1, max_length=12)]
    style: Literal["primary", "warning", "success", "question"]


class EffectType(StrEnum):
    PUNCH_ZOOM = "punch_zoom"
    SLOW_ZOOM = "slow_zoom"
    SOUND_EFFECT = "sound_effect"
    PROGRESS_BAR = "progress_bar"
    SPEAKER_LABEL = "speaker_label"
    QUESTION_CARD = "question_card"
    QUOTE_CARD = "quote_card"


class Effect(StrictModel):
    time_seconds: Seconds
    type: EffectType
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def safe_parameters(self) -> Effect:
        if self.type in {EffectType.PUNCH_ZOOM, EffectType.SLOW_ZOOM}:
            scale = float(self.parameters.get("scale", 1.0))
            duration = float(self.parameters.get("duration_seconds", 0.5))
            self.parameters["scale"] = min(max(scale, 1.0), 1.35)
            self.parameters["duration_seconds"] = min(max(duration, 0.1), 8.0)
        if self.type is EffectType.SOUND_EFFECT:
            volume = float(self.parameters.get("volume_db", -18))
            self.parameters["volume_db"] = min(max(volume, -40), -8)
        return self


class CTA(TimeRange):
    text: Annotated[str, Field(min_length=1, max_length=160)]


class CaptionConfig(StrictModel):
    enabled: bool = True
    position: Literal["top", "middle", "bottom"] = "bottom"
    font_family: Annotated[str, Field(min_length=1, max_length=80)] = "Noto Sans"
    font_size: Annotated[int, Field(ge=28, le=96)] = 58
    text_color: Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")] = "#FFFFFF"
    highlight_color: Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")] = "#D8FF42"
    outline_color: Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")] = "#111111"
    animation: Literal["none", "pop", "karaoke"] = "pop"
    highlighted_words: list[Annotated[str, Field(min_length=1, max_length=40)]] = Field(
        default_factory=list, max_length=24
    )
    max_words_per_line: Annotated[int, Field(ge=2, le=8)] = 5


class EditingPlanV1(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    source: TimeRange
    scores: Scores
    rationale: Annotated[str, Field(min_length=1, max_length=600)]
    suggested_title: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    hashtags: list[Hashtag] = Field(default_factory=list, max_length=8)
    hook: Hook | None = None
    caption_style: Literal["clean", "kinetic_highlight", "karaoke"] = "clean"
    caption_config: CaptionConfig = Field(default_factory=CaptionConfig)
    frame_style: Literal["blurred_background", "center_crop"] = "blurred_background"
    emphasis: list[Emphasis] = Field(default_factory=list, max_length=40)
    effects: list[Effect] = Field(default_factory=list, max_length=40)
    cta: CTA | None = None

    @model_validator(mode="after")
    def relative_timestamps_fit_clip(self) -> EditingPlanV1:
        duration = self.source.end_seconds - self.source.start_seconds
        ranges: list[TimeRange] = [*self.emphasis]
        if self.hook:
            ranges.append(self.hook)
        if self.cta:
            ranges.append(self.cta)
        if any(item.end_seconds > duration for item in ranges):
            raise ValueError("relative timestamp exceeds selected source duration")
        if any(effect.time_seconds > duration for effect in self.effects):
            raise ValueError("effect timestamp exceeds selected source duration")
        return self
