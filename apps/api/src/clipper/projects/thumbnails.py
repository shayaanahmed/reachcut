from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import structlog
from sqlalchemy.orm import Session

from clipper.domain.editing_plan import EditingPlanV1, ThumbnailConfig, ThumbnailTemplate
from clipper.domain.transcript import Transcript
from clipper.persistence import Clip, Project
from clipper.projects.artifacts import ClipArtifactService, timeline_words
from clipper.rendering.thumbnails import (
    ThumbnailPlanner,
    ThumbnailRenderer,
    fallback_headline,
)

logger = structlog.get_logger()


class ThumbnailNotFoundError(LookupError):
    pass


class ThumbnailStateError(RuntimeError):
    pass


@dataclass(frozen=True)
class ThumbnailCreate:
    template: ThumbnailTemplate
    headline: str | None = None


class ThumbnailService:
    """Generate and persist a deterministic thumbnail for one clip."""

    def __init__(
        self,
        artifacts: ClipArtifactService,
        renderer: ThumbnailRenderer,
        projects_root: Path,
        *,
        logo_path: Path | None = None,
    ) -> None:
        self._artifacts = artifacts
        self._renderer = renderer
        self._projects_root = projects_root.resolve()
        self._logo_path = logo_path.resolve() if logo_path else None

    def generate(
        self,
        session: Session,
        clip_id: str,
        request: ThumbnailCreate,
        planner: ThumbnailPlanner | None,
    ) -> str:
        clip = session.get(Clip, clip_id)
        if not clip:
            raise ThumbnailNotFoundError("clip not found")
        project = session.get(Project, clip.project_id)
        if not project or not project.transcript:
            raise ThumbnailStateError("project transcript is not available")
        source = self._owned_source(project)
        transcript = Transcript.model_validate(project.transcript)
        plan = EditingPlanV1.model_validate(clip.plan)
        candidates = self._renderer.sample_candidates(source, plan)
        headline = request.headline.strip() if request.headline else ""
        selected_index = 0
        if planner is not None:
            try:
                choice = planner.plan(
                    [self._renderer.jpeg_bytes(candidate) for candidate in candidates],
                    transcript=self._transcript_excerpt(transcript, plan),
                    suggested_title=fallback_headline(plan),
                    template=request.template,
                )
                selected_index = choice.frame_index
                headline = headline or choice.headline.strip()
            except Exception as error:
                logger.warning(
                    "thumbnail_planner_fallback",
                    clip_id=clip.id,
                    error_category=type(error).__name__,
                )
        selected = candidates[selected_index]
        headline = self._headline(headline or fallback_headline(plan))
        root = source.parent / "clips" / clip.id
        output = root / "thumbnail.png"
        self._renderer.render(
            selected,
            headline,
            request.template,
            output,
            logo_path=self._logo_path,
        )
        updated_plan = plan.model_copy(
            update={
                "thumbnail": ThumbnailConfig(
                    template=request.template,
                    headline=headline,
                    frame_time_seconds=selected.source_time_seconds,
                    generated=True,
                )
            }
        )
        self._artifacts.write(project, clip, updated_plan, transcript)
        clip.plan = updated_plan.model_dump(mode="json")
        session.commit()
        return project.id

    def resolve(self, session: Session, clip_id: str) -> Path:
        clip = session.get(Clip, clip_id)
        if not clip:
            raise ThumbnailNotFoundError("thumbnail not found")
        project = session.get(Project, clip.project_id)
        if not project:
            raise ThumbnailNotFoundError("thumbnail not found")
        source = self._owned_source(project)
        expected = source.parent / "clips" / clip.id / "thumbnail.png"
        try:
            resolved = expected.resolve(strict=True)
        except OSError as error:
            raise ThumbnailNotFoundError("thumbnail not found") from error
        if resolved != expected or not resolved.is_file():
            raise ThumbnailNotFoundError("thumbnail not found")
        return resolved

    def _owned_source(self, project: Project) -> Path:
        try:
            source = Path(project.source_path).resolve(strict=True)
        except OSError as error:
            raise ThumbnailStateError("project source path is unavailable") from error
        expected_root = self._projects_root / project.id
        if source.parent.parent != expected_root or not source.is_file():
            raise ThumbnailStateError("project source path is outside its owned directory")
        return source

    @staticmethod
    def _transcript_excerpt(transcript: Transcript, plan: EditingPlanV1) -> str:
        words = timeline_words(transcript, plan.source_slices or [plan.source])
        return " ".join(word.text for word in words)[:5000]

    @staticmethod
    def _headline(value: str) -> str:
        words = " ".join(value.split()).split()
        return " ".join(words[:10])[:80].strip() or "A MOMENT WORTH SHARING"
