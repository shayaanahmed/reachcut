"""Independent outputs from immutable source media, with durable run lineage."""

import copy
import os
import shutil
from pathlib import Path
from typing import BinaryIO, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from clipper.media import safe_filename, store_upload
from clipper.media.metadata import media_metadata
from clipper.persistence import Clip, Project
from clipper.persistence.models import SourceWorkflowRun
from clipper.projects.queue import ACTIVE_PROJECT_STATUSES, ProjectQueue


class WorkflowRequest(BaseModel):
    idempotency_key: UUID
    kind: Literal["clips", "full", "metadata", "language"]
    clip_ids: list[str] = Field(default_factory=list, max_length=200)
    target_language: str | None = Field(default=None, pattern=r"^[a-z]{2,3}(?:-[A-Za-z]{2,8})?$")
    scopes: list[Literal["metadata", "subtitles", "narration"]] = Field(default=["metadata"])

    @model_validator(mode="after")
    def language_options(self) -> "WorkflowRequest":
        if self.kind == "language" and (not self.target_language or not self.scopes):
            raise ValueError("Choose a target language and at least one language option")
        if self.kind in {"clips", "full"} and self.clip_ids:
            raise ValueError("Clip selection applies to metadata refreshes and language versions")
        if self.kind != "language" and (self.target_language or self.scopes != ["metadata"]):
            raise ValueError("Language options only apply to language versions")
        return self


def copy_media(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def create_workflow(
    session: Session,
    source: Project,
    request: WorkflowRequest,
    root: Path,
    narration: BinaryIO | None = None,
    narration_name: str = "narration.wav",
) -> SourceWorkflowRun:
    existing = session.get(SourceWorkflowRun, str(request.idempotency_key))
    if existing:
        if (
            existing.source_project_id != source.id
            or existing.kind != request.kind
            or existing.target_language != request.target_language
            or set(existing.scopes) != set(request.scopes)
            or set(existing.clip_ids) != set(request.clip_ids)
        ):
            raise ValueError(
                "This request key belongs to a different workflow; start a new request"
            )
        return existing
    requested = set(request.clip_ids)
    if not requested.issubset({clip.id for clip in source.clips}):
        raise ValueError("Select clips belonging to this source")
    clips = [clip for clip in source.clips if not requested or clip.id in requested]
    if request.kind == "metadata" and not clips:
        raise ValueError("There are no existing clips. Choose Prepare full video instead.")
    if request.kind == "language" and "narration" in request.scopes:
        if not narration or len(clips) > 1:
            raise ValueError(
                "Upload translated narration and select exactly one clip (or the full source)"
            )
    elif narration:
        raise ValueError("Choose Replace narration before uploading audio")
    if source.status in ACTIVE_PROJECT_STATUSES:
        raise ValueError(
            "Wait for the active source pipeline to finish before starting another workflow"
        )
    media = Path(source.source_path)
    if not media.is_file():
        raise ValueError("Source media is not available")
    target = source
    owned_root: Path | None = None
    try:
        if request.kind == "metadata":
            claim = session.execute(
                update(Project)
                .where(Project.id == source.id, Project.status.not_in(ACTIVE_PROJECT_STATUSES))
                .values(status="queued")
            )
            if claim.rowcount != 1:  # type: ignore[attr-defined]
                raise ValueError("This source already has a workflow in progress")
        if request.kind != "metadata":
            id = str(uuid4())
            owned_root = root / id
            stored = owned_root / "source" / safe_filename(source.original_filename)
            copy_media(media, stored)
            suffix = {
                "clips": "clips",
                "full": "full video",
                "language": request.target_language or "language",
            }[request.kind]
            target = Project(
                id=id,
                title=f"{source.title[:160]} · {suffix}",
                original_filename=source.original_filename,
                source_path=str(stored),
                media_sha256=source.media_sha256,
                authorization_confirmed_at=source.authorization_confirmed_at,
                duration_seconds=source.duration_seconds,
                media_info=copy.deepcopy(source.media_info),
                transcript=copy.deepcopy(source.transcript),
            )
            session.add(target)
            session.flush()
            if request.kind == "language":
                for original in clips:
                    clone = Clip(
                        project=target, plan=copy.deepcopy(original.plan), approval_status="pending"
                    )
                    session.add(clone)
                    session.flush()
                    original_root = Path(source.source_path).parent / "clips" / original.id
                    clone_root = stored.parent / "clips" / clone.id
                    if (original_root / "assets").is_dir():
                        shutil.copytree(
                            original_root / "assets", clone_root / "assets", dirs_exist_ok=True
                        )
                    if original.final_path and Path(original.final_path).is_file():
                        clone_root.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(Path(original.final_path), clone_root / "final.mp4")
                        clone.final_path = str(clone_root / "final.mp4")
        run = SourceWorkflowRun(
            id=str(request.idempotency_key),
            source_project_id=source.id,
            target_project_id=target.id,
            source_title=source.title,
            kind=request.kind,
            target_language=request.target_language,
            clip_ids=request.clip_ids,
            scopes=request.scopes,
        )
        if narration:
            audio = (
                Path(target.source_path).parent / "workflow-audio" / safe_filename(narration_name)
            )
            store_upload(narration, audio, 200 * 1024 * 1024)
            info = media_metadata(audio)
            if not any(stream.get("codec_type") == "audio" for stream in info.get("streams", [])):
                raise ValueError("The narration file must contain an audio stream")
            run.narration_path = str(audio)
        session.add(run)
        # Commit the output and its job together; retry never creates a second output.
        ProjectQueue().enqueue(
            session,
            target,
            processing_mode=(
                "clips"
                if request.kind == "clips"
                else "language"
                if request.kind == "language"
                else "metadata"
            ),
        )
        return run
    except Exception:
        session.rollback()
        if owned_root:
            shutil.rmtree(owned_root, ignore_errors=True)
        raise


def active_workflow(session: Session, project_id: str) -> SourceWorkflowRun | None:
    return session.scalar(
        select(SourceWorkflowRun)
        .where(
            SourceWorkflowRun.target_project_id == project_id,
            SourceWorkflowRun.status.in_(["queued", "running"]),
        )
        .order_by(SourceWorkflowRun.created_at.desc())
        .limit(1)
    )
