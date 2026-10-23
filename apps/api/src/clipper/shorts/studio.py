"""Two simple creation paths: a public repo URL or an Ollama tech-trick suggestion."""

from typing import Literal
from uuid import uuid4

from pydantic import Field, model_validator

from clipper.shorts.contracts import Evidence, ShortSettings, Strict
from clipper.shorts.frames import FrameKind, FrameSequence, FrameTheme
from clipper.shorts.series import (
    ContentSeries,
    SeriesStyle,
    StyleBeat,
    TemplateDesign,
    ThumbnailDesign,
)

Category = Literal["github", "tech-tricks"]


class StoryStep(Strict):
    """Documented action, before its wording is adapted to a screen label."""

    title: str = Field(min_length=1, max_length=80)
    body: str = Field(default="", max_length=200)


class Storyline(Strict):
    id: str
    title: str = Field(min_length=3, max_length=100)
    hook: str = Field(min_length=3, max_length=160)
    focus: str = Field(min_length=10, max_length=500)
    payoff: str = Field(min_length=5, max_length=250)
    source_id: str = Field(min_length=1, max_length=80)
    example: str = Field(default="", max_length=300)
    steps: list[StoryStep] = Field(default_factory=list, max_length=3)
    prerequisite: str = Field(default="", max_length=180)


class StoryboardBeat(Strict):
    narration: str = Field(min_length=8, max_length=300)
    caption: str = Field(min_length=3, max_length=65)
    title: str = Field(min_length=1, max_length=40)
    visual: str = Field(min_length=10, max_length=180)
    excerpt_id: str
    choices: list[str] = Field(default_factory=list, max_length=2)


class StudioBrief(Strict):
    id: str = Field(default_factory=lambda: str(uuid4()))
    category: Category
    subject: str
    repo_url: str = ""
    context: str = ""
    analysis: str
    sources: list[Evidence]
    storylines: list[Storyline] = Field(min_length=3, max_length=3)
    notices: list[str] = Field(default_factory=list)
    storyboard: list[StoryboardBeat] = Field(default_factory=list, max_length=6)
    storyboard_storyline_id: str = ""
    storyboard_notes: list[str] = Field(default_factory=list)


class IdeaRequest(Strict):
    flow: Literal["storylines", "storyboard"] = "storylines"
    category: Category
    repo_url: str = Field(default="", max_length=2048)
    context: str = Field(default="", max_length=1000)
    previous_brief_id: str = Field(default="", max_length=80)
    request_key: str = Field(min_length=8, max_length=100)

    @model_validator(mode="after")
    def valid_input(self) -> "IdeaRequest":
        if self.category == "github" and not self.repo_url.strip():
            raise ValueError("Paste a public GitHub repository URL")
        if self.category == "tech-tricks" and self.repo_url:
            raise ValueError("Tech tricks do not need a repository URL")
        return self


class StoryboardRequest(Strict):
    auto_produce: bool = False
    brief_id: str = Field(min_length=1, max_length=80)
    storyline_id: str = Field(min_length=1, max_length=80)
    sequence_id: str = Field(min_length=1, max_length=80)
    request_key: str = Field(min_length=8, max_length=100)
    feedback: str = Field(default="", max_length=2000)
    theme: FrameTheme | None = None
    frame_mode: Literal["manual", "ai"] = "manual"
    frames: list[FrameKind] | None = Field(default=None, min_length=5, max_length=6)
    source_short_id: str = Field(default="", max_length=80)


def episode_settings(category: Category, sequence: FrameSequence) -> ContentSeries:
    """Immutable episode defaults; these are not user-managed or persisted niches."""
    return ContentSeries(
        id=category,
        name="Exciting GitHub repos" if category == "github" else "Tech tricks",
        purpose=(
            "Explain what the subject does, how it helps and what someone could "
            "achieve, through a relatable, source-supported story."
        ),
        audience=(
            "Developers and non-developers; curious people with no assumed technical knowledge"
        ),
        artwork_mode="ollama",
        headline_font=sequence.font,
        settings=ShortSettings(
            duration=30,
            narration_mode="none",
            caption_font=sequence.font,
            accent=sequence.accent,
            allow_explanation_cards=True,
        ),
        thumbnail=ThumbnailDesign(
            background=sequence.background, accent=sequence.accent, foreground="#E6EDF3"
        ),
    )


def episode_style(sequence: FrameSequence) -> SeriesStyle:
    return SeriesStyle(
        id=sequence.id,
        name=sequence.name,
        frame_sequence=sequence,
        hook_template="What could you do with {subject}?",
        pacing=sequence.description,
        beats=[
            StyleBeat(
                heading=kind.title(),
                visual="diagram",
                direction="Use the selected scene composition and source-grounded plain language.",
            )
            for kind in sequence.frames
        ],
        design=TemplateDesign(
            background=sequence.background,
            accent=sequence.accent,
            foreground="#E6EDF3",
            font=sequence.font,
            reuse_background=False,
        ),
    )
