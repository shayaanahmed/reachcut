"""Reusable scene compositions, independent of subjects and saved niches."""

import json
from pathlib import Path
from typing import Annotated, Literal, cast

from pydantic import Field

from clipper.config import settings
from clipper.shorts.contracts import Strict

FrameKind = Annotated[str, Field(min_length=1, max_length=100)]
VisualType = Literal["workflow", "particles", "search", "folders", "typing", "browser"]
# Word counts guide the editor; character limits and measured wrapping protect the layout.
ShortCopy = Annotated[str, Field(min_length=1, max_length=90)]


class FrameItem(Strict):
    title: str = Field(min_length=1, max_length=45)
    body: str = Field(default="", max_length=90)


class FrameContent(Strict):
    template: FrameKind
    caption: ShortCopy
    eyebrow: str = Field(max_length=35)
    title: str = Field(min_length=1, max_length=65)
    items: list[FrameItem] = Field(default_factory=list, max_length=3)
    query: str = Field(default="", max_length=80)
    duration_seconds: float = Field(default=5, ge=1, le=15)
    visual_type: VisualType = "workflow"


FrameTheme = Literal["neon", "paper", "sunset", "cyan", "amber", "glass", "mono"]


class FrameDefinition(Strict):
    id: FrameKind
    name: str
    description: str
    use: str
    sample: FrameContent
    volume: int = 2


class FrameSequence(Strict):
    id: str
    name: str
    description: str
    background: str
    accent: str
    secondary: str
    font: Literal["Bricolage Grotesque", "Anton", "Space Grotesk", "Syne"]
    frames: list[FrameKind]
    durations: list[float]
    theme: FrameTheme = "neon"


def design_catalogue() -> list[dict[str, object]]:
    path = Path(__file__).parents[1] / "rendering/assets/frames/library/catalogue.json"
    bundled = cast(list[dict[str, object]], json.loads(path.read_text()))
    imported = settings.data_dir / "frame-library.json"
    extra = json.loads(imported.read_text())["frames"] if imported.exists() else []
    return list({str(d["id"]): d for d in [*bundled, *extra]}.values())


# Older designs remain archived for saved video snapshots, outside the active catalogue.
def frame_library() -> list[FrameDefinition]:
    hook = {"kinetic-poster", "hot-take", "newspaper"}
    closing = {"story-poll", "speed-dial", "bento-stats"}
    return [
        FrameDefinition(
            id=cast(FrameKind, design["id"]),
            name=str(design["name"]),
            description=str(design["description"]),
            use=str(design["use"])
            if "use" in design
            else "Hook"
            if design["id"] in hook
            else "Closing"
            if design["id"] in closing
            else "Explain",
            volume=int(str(design["volume"])),
            sample=FrameContent(
                template=cast(FrameKind, design["id"]),
                caption=str(design["caption"]),
                eyebrow="ILLUSTRATIVE SAMPLE",
                duration_seconds=float(str(design.get("duration_seconds", 5))),
                title=str(design["name"]),
                items=(
                    [FrameItem(title="Search"), FrameItem(title="Photo editing")]
                    if design["id"] == "story-poll"
                    else [
                        FrameItem(title="Question", body="Choose a feature to explore"),
                        FrameItem(title="Evidence", body="Read the documented workflow"),
                        FrameItem(title="Your idea", body="Check before you build"),
                    ]
                ),
            ),
        )
        for design in design_catalogue()
    ]


def frame_sequences() -> list[FrameSequence]:
    path = Path(__file__).parents[1] / "rendering/assets/frames/library/sequences.json"
    bundled = json.loads(path.read_text())
    imported = settings.data_dir / "frame-library.json"
    extra = json.loads(imported.read_text())["sequences"] if imported.exists() else []
    return [
        FrameSequence.model_validate(d) for d in {d["id"]: d for d in [*bundled, *extra]}.values()
    ]


def sequence_by_id(sequence_id: str) -> FrameSequence:
    match = next((item for item in frame_sequences() if item.id == sequence_id), None)
    if match is None:
        path = Path(__file__).parents[1] / "rendering/assets/frames/library/retired-sequences.json"
        archived = next(
            (item for item in json.loads(path.read_text()) if item["id"] == sequence_id), None
        )
        if archived:
            return FrameSequence.model_validate(archived)
        raise LookupError("Frame sequence not found")
    return match
