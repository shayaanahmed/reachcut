"""Saved content-series blueprints and source-grounded episode storyboards."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field, model_validator

from clipper.shorts.contracts import Evidence, Script, ShortSettings, Strict
from clipper.shorts.discovery import SocialReference
from clipper.shorts.frames import FrameContent, FrameSequence

Text = Annotated[str, Field(min_length=1, max_length=700)]
HeadlineFont = Literal["Bricolage Grotesque", "Anton", "Space Grotesk", "Syne", "Fraunces"]
TemplateLayout = Literal["poster", "split", "spotlight", "kinetic", "editorial", "cards"]


class TemplatePreviewScene(Strict):
    heading: str = Field(min_length=1, max_length=100, pattern=r"^[^ \n\t\r]+( [^ \n\t\r]+){0,7}$")
    body: str = Field(min_length=1, max_length=300, pattern=r"^[^ \n\t\r]+( [^ \n\t\r]+){0,19}$")
    duration_seconds: float = Field(default=2.4, gt=0, le=30)


class TemplateDesign(Strict):
    background: str = Field(default="#101827", pattern=r"^#[0-9a-fA-F]{6}$")
    accent: str = Field(default="#B4F5CD", pattern=r"^#[0-9a-fA-F]{6}$")
    foreground: str = Field(default="#FFFFFF", pattern=r"^#[0-9a-fA-F]{6}$")
    font: HeadlineFont = "Bricolage Grotesque"
    weight: int = Field(default=800, ge=400, le=900)
    uppercase: bool = False
    background_prompt: str = Field(default="", max_length=1600)
    background_asset_id: str = Field(default="", pattern=r"^(builtin-[a-z0-9-]+|[a-f0-9]{64})?$")
    visual_direction: str = Field(default="", max_length=700)
    font_reason: str = Field(default="", max_length=500)
    niche_reason: str = Field(default="", max_length=700)
    suitable_for: list[str] = Field(default_factory=list, max_length=6)
    reuse_background: bool = True
    preview_scenes: list[TemplatePreviewScene] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def readable_palette(self) -> "TemplateDesign":
        def luminance(color: str) -> float:
            channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
            linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

        a, b = sorted([luminance(self.foreground), luminance(self.background)])
        if (b + 0.05) / (a + 0.05) < 4.5:
            raise ValueError("Foreground and background need at least 4.5:1 text contrast")
        return self


class FontLook(Strict):
    name: str = Field(min_length=1, max_length=80)
    font: HeadlineFont
    weight: int = Field(ge=400, le=900)
    uppercase: bool
    reason: Text


class FontLooks(Strict):
    looks: list[FontLook] = Field(min_length=2, max_length=4)


class TemplateMatch(Strict):
    template_id: str = Field(min_length=1, max_length=64)
    reason: Text


class TemplateMatches(Strict):
    matches: list[TemplateMatch] = Field(default_factory=list, max_length=6)


class ThumbnailDesign(Strict):
    layout: Literal["split", "centered", "terminal"] = "split"
    background: str = Field(default="#101827", pattern=r"^#[0-9a-fA-F]{6}$")
    accent: str = Field(default="#8B7CFF", pattern=r"^#[0-9a-fA-F]{6}$")
    foreground: str = Field(default="#FFFFFF", pattern=r"^#[0-9a-fA-F]{6}$")
    label: str = Field(default="", max_length=50)
    headline_template: str = Field(default="{headline}", min_length=1, max_length=120)


class StyleBeat(Strict):
    heading: str = Field(min_length=1, max_length=80)
    visual: Literal["source", "code", "diagram", "recording"] = "source"
    direction: Text


class SeriesStyle(Strict):
    id: str = Field(default_factory=lambda: str(uuid4()), pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    name: str = Field(min_length=1, max_length=100)
    hook_template: str = Field(min_length=3, max_length=200)
    pacing: str = Field(min_length=3, max_length=300)
    caption_style: Literal["clean", "bold", "minimal"] = "clean"
    beats: list[StyleBeat] = Field(min_length=3, max_length=6)
    reference_ids: list[str] = Field(default_factory=list, max_length=10)
    basis: Literal["starter", "custom", "reference-inspired"] = "custom"
    layout: TemplateLayout = "poster"
    design: TemplateDesign | None = None
    frame_sequence: FrameSequence | None = None

    @model_validator(mode="after")
    def matching_preview_scenes(self) -> "SeriesStyle":
        if (
            self.design
            and self.design.preview_scenes
            and len(self.design.preview_scenes) != len(self.beats)
        ):
            raise ValueError("Template preview scenes must match its story beats")
        return self


class SeriesConfig(Strict):
    name: str = Field(min_length=2, max_length=80)
    purpose: str = Field(min_length=10, max_length=1200)
    audience: str = Field(
        default="Curious everyday people, including people with no technical background",
        min_length=3,
        max_length=500,
    )
    artwork_mode: Literal["designed", "ollama"] = "designed"
    image_model: str = Field(default="x/flux2-klein:4b", min_length=1, max_length=120)
    headline_font: HeadlineFont = "Bricolage Grotesque"
    active_template_id: str = Field(default="", max_length=64)
    settings: ShortSettings = Field(
        default_factory=lambda: ShortSettings(duration=45, narration_mode="voicebox")
    )
    thumbnail: ThumbnailDesign = Field(default_factory=ThumbnailDesign)


class ContentSeries(SeriesConfig):
    id: str = Field(default_factory=lambda: str(uuid4()))
    styles: list[SeriesStyle] = Field(default_factory=list, max_length=40)
    references: list[SocialReference] = Field(default_factory=list, max_length=60)
    notices: list[str] = Field(default_factory=list)
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    @model_validator(mode="after")
    def unique_styles(self) -> "ContentSeries":
        if len({style.id for style in self.styles}) != len(self.styles):
            raise ValueError("Style IDs must be unique")
        return self


class EpisodeAngle(Strict):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    title: str = Field(min_length=3, max_length=150)
    hook: str = Field(min_length=3, max_length=200)
    focus: Text


class EpisodeAngles(Strict):
    angles: list[EpisodeAngle] = Field(min_length=2, max_length=6)

    @model_validator(mode="after")
    def unique_angles(self) -> "EpisodeAngles":
        if len({angle.id for angle in self.angles}) != len(self.angles):
            raise ValueError("Angle IDs must be unique")
        return self


class EpisodeBrief(EpisodeAngles):
    id: str = Field(default_factory=lambda: str(uuid4()))
    series_id: str
    subject: str = Field(min_length=1, max_length=200)
    source_url: str = ""
    notes: str = Field(default="", max_length=12000)
    sources: list[Evidence] = Field(default_factory=list, max_length=6)
    notices: list[str] = Field(default_factory=list)


class EpisodeVisual(Strict):
    frame: FrameContent | None = None
    section_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    kind: Literal["source", "code", "diagram", "recording", "illustration"] = "source"
    heading: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=1000)
    source_id: str = Field(default="", max_length=80)
    quote: str = Field(default="", max_length=1000)
    art_prompt: str = Field(default="", max_length=1600)
    role: Literal["hook", "purpose", "example", "how", "outcome", "cta"] = "purpose"


class EpisodeConcept(Strict):
    """The viewer's takeaway, independent of the particular repository or niche."""

    problem: Text
    purpose: Text
    benefit: Text
    how_it_works: Text
    possible_result: Text
    limitation: Text


class EpisodePlan(Strict):
    title: str = Field(min_length=3, max_length=150)
    headline: str = Field(min_length=3, max_length=80)
    script: Script
    visuals: list[EpisodeVisual] = Field(min_length=3, max_length=6)
    # Optional only for loading previously saved storyboards.
    concept: EpisodeConcept | None = None
    editorial_version: str = ""
    editorial_notes: list[str] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def matching_sections(self) -> "EpisodePlan":
        if [v.section_id for v in self.visuals] != [s.id for s in self.script.sections]:
            raise ValueError("Every script section needs one matching visual in the same order")
        return self


class EpisodeSnapshot(Strict):
    series: ContentSeries
    brief: EpisodeBrief
    angle: EpisodeAngle
    style: SeriesStyle
    plan: EpisodePlan
    request_signature: str


class StyleSuggestions(Strict):
    styles: list[SeriesStyle] = Field(min_length=2, max_length=4)


def starter_angles(subject: str) -> list[EpisodeAngle]:
    return [
        EpisodeAngle(id=key, title=title, hook=hook, focus=focus)
        for key, title, hook, focus in [
            (
                "problem",
                f"What makes {subject} interesting?"[:150],
                f"What makes {subject} worth knowing?"[:200],
                "Choose a source-supported insight relevant to this niche purpose and audience.",
            ),
            (
                "quickstart",
                f"Understand {subject}, step by step"[:150],
                f"Here is {subject}, step by step."[:200],
                "Introduce the subject and walk through its relevant details or documented steps.",
            ),
            (
                "audience",
                f"One thing to know about {subject}"[:150],
                f"What should you know about {subject}?"[:200],
                "Explore a source-supported question about this subject for the series audience.",
            ),
        ]
    ]
