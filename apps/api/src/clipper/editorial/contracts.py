from dataclasses import dataclass
from typing import Protocol

from clipper.domain.editing_plan import ContentMode, EditingPlanV1
from clipper.domain.transcript import Transcript
from clipper.transcription.contracts import CancellationProbe, ProgressReporter


@dataclass(frozen=True)
class EditorialContext:
    """Project-owned context that helps transcript-only ranking resolve names and pronouns."""

    project_title: str
    original_filename: str
    content_mode: ContentMode = ContentMode.AUTO
    face_coverage: float = 0
    motion_confidence: float = 0


class EditorialLLMProvider(Protocol):
    """Port for selecting ranked highlights from a transcript."""

    @property
    def identity(self) -> str: ...

    def select_candidates(
        self,
        transcript: Transcript,
        target_count: int,
        cancelled: CancellationProbe,
        progress: ProgressReporter,
        context: EditorialContext | None = None,
    ) -> list[EditingPlanV1]: ...
