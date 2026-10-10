from __future__ import annotations

from enum import StrEnum
from itertools import pairwise
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


class ContentMode(StrEnum):
    AUTO = "auto"
    TALKING_HEAD = "talking_head"
    PODCAST = "podcast"
    GAMEPLAY = "gameplay"
    SPORTS = "sports"
    TUTORIAL = "tutorial"
    REACTION = "reaction"
    PRODUCT = "product"
    NEWS = "news"
    BROLL = "broll"


class ClipType(StrEnum):
    HIGHLIGHT = "highlight"
    FUNNY = "funny"
    ADVICE = "advice"
    INSIGHT = "insight"
    STORY = "story"
    DEBATE = "debate"
    EDUCATIONAL = "educational"
    EMOTIONAL = "emotional"
    PROMOTIONAL = "promotional"


class EnhancementLevel(StrEnum):
    CLEAN = "clean"
    DYNAMIC = "dynamic"
    AGGRESSIVE = "aggressive"


class CaptionPreset(StrEnum):
    CUSTOM = "custom"
    CLEAN = "clean"
    BOLD_VIRAL = "bold_viral"
    KARAOKE = "karaoke"
    PODCAST = "podcast"
    GAMING = "gaming"
    SPORTS = "sports"
    MINIMAL = "minimal"
    NEWS = "news"


class TranslationMode(StrEnum):
    ORIGINAL = "original"
    TRANSLATED = "translated"
    BILINGUAL = "bilingual"


class TrackingStrategy(StrEnum):
    STATIC = "static"
    FACE = "face"
    ACTIVE_SPEAKER = "active_speaker"
    ACTION = "action"
    OBJECT = "object"


class TransitionStyle(StrEnum):
    CUT = "cut"
    FADE = "fade"


class SecondaryMediaKind(StrEnum):
    GAMEPLAY = "gameplay"
    BROLL = "broll"
    REACTION = "reaction"
    SOUND_EFFECT = "sound_effect"
    MUSIC = "music"


class Hook(TimeRange):
    text: Annotated[str, Field(min_length=1, max_length=160)]
    render: bool = False


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
    render: bool = False
    style: Literal["follow", "comment", "part_two", "profile", "product", "campaign"] = "follow"


class CropKeyframe(StrictModel):
    time_seconds: Seconds
    center_x: Annotated[float, Field(ge=0, le=1)] = 0.5
    center_y: Annotated[float, Field(ge=0, le=1)] = 0.5
    confidence: Annotated[float, Field(ge=0, le=1)] = 1.0


class TrackingConfig(StrictModel):
    enabled: bool = False
    strategy: TrackingStrategy = TrackingStrategy.STATIC
    keyframes: Annotated[list[CropKeyframe], Field(max_length=720)] = Field(default_factory=list)

    @model_validator(mode="after")
    def keyframes_are_ordered(self) -> TrackingConfig:
        if any(
            current.time_seconds >= following.time_seconds
            for current, following in pairwise(self.keyframes)
        ):
            raise ValueError("tracking keyframes must be strictly ordered")
        return self


class SecondaryMedia(StrictModel):
    asset_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")]
    filename: Annotated[str, Field(pattern=r"^[A-Za-z0-9._-]{1,180}$")]
    kind: SecondaryMediaKind
    start_seconds: Seconds | None = None
    end_seconds: Seconds | None = None
    muted: bool = True
    loop: bool = True
    volume_db: Annotated[float, Field(ge=-40, le=0)] = -18
    placement: Literal["bottom", "pip", "fullscreen", "audio"] = "bottom"

    @model_validator(mode="after")
    def optional_range_is_complete(self) -> SecondaryMedia:
        if (self.start_seconds is None) != (self.end_seconds is None):
            raise ValueError("secondary media start and end must be supplied together")
        if (
            self.start_seconds is not None
            and self.end_seconds is not None
            and self.end_seconds <= self.start_seconds
        ):
            raise ValueError("secondary media end must be after start")
        return self


class CaptionConfig(StrictModel):
    preset: CaptionPreset = CaptionPreset.CUSTOM
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
    text_override: Annotated[str, Field(min_length=1, max_length=20_000)] | None = None
    source_language: Annotated[str, Field(pattern=r"^[A-Za-z]{2,3}$")] | None = None
    target_language: Annotated[str, Field(pattern=r"^[A-Za-z]{2,3}$")] | None = None
    translation_mode: TranslationMode = TranslationMode.ORIGINAL
    translated_text: Annotated[str, Field(min_length=1, max_length=20_000)] | None = None

    @model_validator(mode="after")
    def translated_mode_has_text(self) -> CaptionConfig:
        if self.translation_mode is not TranslationMode.ORIGINAL and (
            not self.target_language or not self.translated_text
        ):
            raise ValueError("translated captions require a target language and text")
        return self


class EditingPlanV1(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    source: TimeRange
    source_slices: Annotated[list[TimeRange], Field(max_length=12)] = Field(default_factory=list)
    optimization_goal: Literal["views", "revenue"] = "views"
    content_mode: ContentMode = ContentMode.AUTO
    clip_type: ClipType = ClipType.HIGHLIGHT
    enhancement_level: EnhancementLevel = EnhancementLevel.CLEAN
    scores: Scores
    rationale: Annotated[str, Field(min_length=1, max_length=600)]
    suggested_title: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    hashtags: list[Hashtag] = Field(default_factory=list, max_length=8)
    hook: Hook | None = None
    caption_style: Literal["clean", "kinetic_highlight", "karaoke"] = "clean"
    caption_config: CaptionConfig = Field(default_factory=CaptionConfig)
    frame_style: Literal["blurred_background", "center_crop"] = "blurred_background"
    crop_focus_x: Annotated[float, Field(ge=0, le=1)] = 0.5
    crop_focus_y: Annotated[float, Field(ge=0, le=1)] = 0.5
    tracking: TrackingConfig = Field(default_factory=TrackingConfig)
    transition_style: TransitionStyle = TransitionStyle.CUT
    transition_duration_seconds: Annotated[float, Field(ge=0.05, le=1)] = 0.2
    secondary_media: Annotated[list[SecondaryMedia], Field(max_length=12)] = Field(
        default_factory=list
    )
    audio_track_index: Annotated[int, Field(ge=0, le=32)] = 0
    emphasis: list[Emphasis] = Field(default_factory=list, max_length=40)
    effects: list[Effect] = Field(default_factory=list, max_length=40)
    cta: CTA | None = None

    @model_validator(mode="after")
    def relative_timestamps_fit_clip(self) -> EditingPlanV1:
        slices = self.source_slices or [self.source]
        if self.source_slices:
            if slices[0].start_seconds != self.source.start_seconds:
                raise ValueError("source must start at the first source slice")
            if slices[-1].end_seconds != self.source.end_seconds:
                raise ValueError("source must end at the last source slice")
            if any(
                current.end_seconds > following.start_seconds
                for current, following in pairwise(slices)
            ):
                raise ValueError("source_slices must be ordered and non-overlapping")
        duration = sum(item.end_seconds - item.start_seconds for item in slices)
        ranges: list[TimeRange] = [*self.emphasis]
        if self.hook:
            ranges.append(self.hook)
        if self.cta:
            ranges.append(self.cta)
        if any(item.end_seconds > duration for item in ranges):
            raise ValueError("relative timestamp exceeds selected source duration")
        if any(effect.time_seconds > duration for effect in self.effects):
            raise ValueError("effect timestamp exceeds selected source duration")
        if any(item.time_seconds > duration for item in self.tracking.keyframes):
            raise ValueError("tracking keyframe exceeds selected source duration")
        if any(
            item.end_seconds is not None and item.end_seconds > duration
            for item in self.secondary_media
        ):
            raise ValueError("secondary media range exceeds selected source duration")
        return self

    @property
    def timeline_duration(self) -> float:
        """Return rendered duration after optional source gaps are removed."""

        slices = self.source_slices or [self.source]
        return sum(item.end_seconds - item.start_seconds for item in slices)
