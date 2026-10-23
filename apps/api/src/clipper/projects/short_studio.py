"""Durable, retryable research/storyboard work for the two-path short studio."""

import logging
import threading
from datetime import UTC, datetime
from typing import Literal
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from clipper.persistence import SessionLocal
from clipper.persistence.models import InformativeShort, RuntimeSetting
from clipper.providers.github_repository import GitHubRepositoryProvider
from clipper.providers.studio_editor import OllamaStudioEditor
from clipper.providers.studio_narrative import Narrative
from clipper.providers.tech_tricks import research_tech_tricks
from clipper.shorts.contracts import Evidence, Script, ShortSettings, Strict, fingerprint
from clipper.shorts.frames import sequence_by_id
from clipper.shorts.series import EpisodeAngle, EpisodeBrief, EpisodeSnapshot
from clipper.shorts.service import ShortService
from clipper.shorts.studio import (
    Category,
    IdeaRequest,
    StoryboardRequest,
    StudioBrief,
    episode_settings,
    episode_style,
)

logger = logging.getLogger(__name__)
_LOCK = threading.Lock()
_WORKER = str(uuid4())


class ResearchRecord(Strict):
    category: Category
    subject: str
    repo_url: str
    context: str
    sources: list[Evidence]
    notices: list[str]


class StudioJob(Strict):
    id: str
    kind: Literal["ideas", "storyboard"]
    signature: str
    status: Literal["queued", "working", "ready", "failed"] = "queued"
    phase: str = "Waiting for Ollama"
    error: str = ""
    ideas_request: IdeaRequest | None = None
    storyboard_request: StoryboardRequest | None = None
    brief: StudioBrief | None = None
    short_id: str = ""
    worker: str = _WORKER
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


def save_job(session: Session, job: StudioJob) -> None:
    key = "studio-job:" + job.id
    row = session.get(RuntimeSetting, key)
    if row:
        row.value = job.model_dump_json()
    else:
        session.add(RuntimeSetting(key=key, value=job.model_dump_json()))
    session.commit()


def get_job(session: Session, job_id: str) -> StudioJob:
    row = session.get(RuntimeSetting, "studio-job:" + job_id, populate_existing=True)
    if not row:
        raise LookupError("Creation task not found")
    job = StudioJob.model_validate_json(row.value)
    if job.worker != _WORKER and job.status in {"queued", "working"}:
        job.status = "failed"
        job.error = "Ollama work was interrupted by a restart. Retry to resume from saved research."
        job.phase = "Needs retry"
        save_job(session, job)
    return job


def create_job(
    session: Session, request: IdeaRequest | StoryboardRequest
) -> tuple[StudioJob, bool]:
    kind: Literal["ideas", "storyboard"] = (
        "ideas" if isinstance(request, IdeaRequest) else "storyboard"
    )
    job_id = str(uuid5(NAMESPACE_URL, "reachcut-studio:" + kind + ":" + request.request_key))
    signature_data = request.model_dump(exclude={"request_key"})
    if signature_data.get("flow") == "storylines":
        signature_data.pop("flow")
    if signature_data.get("auto_produce") is False:
        signature_data.pop("auto_produce")
    signature = fingerprint(signature_data)
    row = session.get(RuntimeSetting, "studio-job:" + job_id)
    if row:
        job = get_job(session, job_id)
        if job.signature != signature:
            raise ValueError("Request key was already used for different inputs")
        if job.status == "failed":
            job.status = "queued"
            job.error = ""
            job.worker = _WORKER
            save_job(session, job)
            return job, True
        return job, False
    job = StudioJob(
        id=job_id,
        kind=kind,
        signature=signature,
        ideas_request=request if isinstance(request, IdeaRequest) else None,
        storyboard_request=request if isinstance(request, StoryboardRequest) else None,
    )
    try:
        save_job(session, job)
    except IntegrityError:
        session.rollback()
        existing = get_job(session, job_id)
        if existing.signature != signature:
            raise ValueError("Request key was already used for different inputs") from None
        return existing, False
    return job, True


def get_brief(session: Session, brief_id: str) -> StudioBrief:
    row = session.get(RuntimeSetting, "studio-brief:" + brief_id)
    if not row:
        raise LookupError("Saved storylines not found")
    return StudioBrief.model_validate_json(row.value)


def save_brief(session: Session, brief: StudioBrief) -> None:
    key = "studio-brief:" + brief.id
    row = session.get(RuntimeSetting, key)
    if row:
        row.value = brief.model_dump_json()
    else:
        session.add(RuntimeSetting(key=key, value=brief.model_dump_json()))
    session.commit()


def run_job(
    job_id: str,
    base_url: str,
    model: str,
    service: ShortService,
    *,
    scripting_model: str | None = None,
) -> None:
    with _LOCK, SessionLocal() as session:
        job = get_job(session, job_id)
        if job.status == "ready":
            return
        try:
            editor = OllamaStudioEditor(base_url, model)
            writer = (
                OllamaStudioEditor(base_url, scripting_model)
                if scripting_model and scripting_model != model
                else editor
            )
            job.status = "working"
            job.phase = "Reading the source documentation"
            save_job(session, job)
            if job.ideas_request:
                request = job.ideas_request
                previous = (
                    get_brief(session, request.previous_brief_id)
                    if request.previous_brief_id
                    else None
                )
                if previous and (
                    previous.category != request.category or previous.repo_url != request.repo_url
                ):
                    raise ValueError("Previous storylines belong to different inputs")
                cached_research = session.get(RuntimeSetting, "studio-research:" + job.id)
                if cached_research:
                    research = ResearchRecord.model_validate_json(cached_research.value)
                else:
                    notices: list[str] = []
                    if request.category == "github":
                        subject, url, sources = GitHubRepositoryProvider().research(
                            request.repo_url
                        )
                    else:
                        sources, notices = research_tech_tricks(
                            len(previous.storylines) if previous else 0
                        )
                        subject, url = "Useful everyday tech tricks", ""
                    research = ResearchRecord(
                        category=request.category,
                        subject=subject,
                        repo_url=url,
                        context=request.context,
                        sources=sources,
                        notices=notices,
                    )
                    session.add(
                        RuntimeSetting(
                            key="studio-research:" + job.id, value=research.model_dump_json()
                        )
                    )
                    session.commit()
                job.phase = "Ollama is finding three engaging storylines"
                save_job(session, job)
                analysis, storylines = editor.ideas(
                    request.category,
                    research.subject,
                    research.sources,
                    request.context,
                    [s.title for s in previous.storylines] if previous else None,
                )
                brief = StudioBrief(
                    category=research.category,
                    id=job.id,
                    subject=research.subject,
                    repo_url=research.repo_url,
                    context=research.context,
                    analysis=analysis,
                    sources=research.sources,
                    storylines=storylines,
                    notices=research.notices,
                )
                if request.category == "github" and request.flow == "storyboard":

                    def draft_progress(phase: str) -> None:
                        job.phase = phase
                        save_job(session, job)

                    job.phase = "Writing a catchy, source-grounded repository storyboard"
                    save_job(session, job)
                    draft = writer.draft(brief, storylines[0], draft_progress)
                    brief.storyboard = draft.beats
                    brief.storyboard_notes = draft.editorial_notes
                    brief.storyboard_storyline_id = storylines[0].id
                save_brief(session, brief)
                job.brief = brief
                job.phase = (
                    "Review your storyboard, then choose a template"
                    if brief.storyboard
                    else "Choose a storyline"
                )
            elif job.storyboard_request:
                plan_request = job.storyboard_request
                brief = get_brief(session, plan_request.brief_id)
                job.brief = brief
                save_job(session, job)
                storyline = next(
                    (s for s in brief.storylines if s.id == plan_request.storyline_id), None
                )
                if not storyline:
                    raise ValueError("Choose one of the saved storylines")
                existing = session.scalar(
                    select(InformativeShort).where(
                        InformativeShort.request_key == "studio:" + job.id
                    )
                )
                if existing and existing.artifacts.get("series_episode"):
                    if plan_request.auto_produce and existing.status == "draft":
                        service.approve_script(session, existing)
                        service.enqueue(session, existing)
                    job.short_id = existing.id
                    job.brief = brief
                    job.status, job.phase = "ready", "Your storyboard is ready"
                    save_job(session, job)
                    return
                if brief.storyboard and plan_request.storyline_id != brief.storyboard_storyline_id:
                    raise ValueError("Use the storyline saved with this storyboard")
                sequence = sequence_by_id(plan_request.sequence_id)
                if brief.storyboard and len(sequence.frames) != len(brief.storyboard):
                    raise ValueError("Choose a template matching the saved storyboard scene count")
                if plan_request.theme:
                    sequence = sequence.model_copy(update={"theme": plan_request.theme})
                if plan_request.frame_mode == "ai":
                    job.phase = "Choosing frames to match your story"
                    save_job(session, job)
                    sequence = sequence.model_copy(
                        update={
                            "frames": writer.choose_frames(
                                storyline, scene_count=len(sequence.frames)
                            )
                        }
                    )
                elif plan_request.frames:
                    sequence = sequence.model_copy(update={"frames": plan_request.frames})
                job.phase = "Ollama is writing and reviewing the complete story"
                save_job(session, job)

                def progress(number: int) -> None:
                    job.phase = f"Designing and checking scene {number} of {len(sequence.frames)}"
                    save_job(session, job)

                def editorial_progress(phase: str) -> None:
                    job.phase = phase
                    save_job(session, job)

                original = None
                if plan_request.source_short_id:
                    original = service.get(session, plan_request.source_short_id)
                    service.editable(original)
                    saved = EpisodeSnapshot.model_validate(original.artifacts["series_episode"])
                    saved.plan.script = Script.model_validate(original.script)
                    plan = writer.plan(
                        brief,
                        storyline,
                        sequence,
                        plan_request.feedback,
                        progress,
                        existing_plan=saved.plan,
                    )
                else:
                    plan = writer.plan(
                        brief,
                        storyline,
                        sequence,
                        plan_request.feedback,
                        progress,
                        on_editorial_progress=editorial_progress,
                        approved_narrative=Narrative(
                            beats=brief.storyboard, editorial_notes=brief.storyboard_notes
                        )
                        if brief.storyboard and not plan_request.feedback
                        else None,
                    )
                series = episode_settings(brief.category, sequence)
                if original:
                    series.settings = ShortSettings.model_validate(original.settings)
                style = episode_style(sequence)
                angles = [
                    EpisodeAngle(id=s.id, title=s.title, hook=s.hook, focus=s.focus)
                    for s in brief.storylines
                ]
                evidence = [s for s in brief.sources if s.id == storyline.source_id]
                legacy_brief = EpisodeBrief(
                    id=brief.id,
                    series_id=brief.category,
                    subject=(brief.subject if brief.category == "github" else storyline.title)[
                        :200
                    ],
                    source_url=brief.repo_url,
                    sources=evidence,
                    angles=angles,
                )
                snapshot = EpisodeSnapshot(
                    series=series,
                    brief=legacy_brief,
                    angle=next(a for a in angles if a.id == storyline.id),
                    style=style,
                    plan=plan,
                    request_signature=job.signature,
                )
                short = service.create(session, plan.title, series.settings, "studio:" + job.id)
                if not short.artifacts.get("series_episode"):
                    short.script = plan.script.model_dump(mode="json")
                    short.sources = [s.model_dump(mode="json") for s in evidence]
                    short.artifacts = {
                        "series_episode": snapshot.model_dump(mode="json"),
                        "studio": {
                            "brief_id": brief.id,
                            "storyline_id": storyline.id,
                            "sequence_id": sequence.id,
                            "final_review_required": bool(brief.storyboard),
                        },
                    }
                    short.phase = (
                        f"Review your {len(sequence.frames)} scenes, then create the video"
                    )
                    session.commit()
                if plan_request.auto_produce:
                    if not brief.storyboard:
                        raise ValueError("Review a saved storyboard before creating the video")
                    service.approve_script(session, short)
                    service.enqueue(session, short)
                job.short_id = short.id
                job.brief = brief
                job.phase = "Your storyboard is ready"
            job.status = "ready"
        except Exception as error:
            session.rollback()
            logger.exception("Short studio task failed: %s", job_id)
            job.status = "failed"
            job.error = str(error)[:1000]
            job.phase = "Your saved work is kept. Retry when ready."
        save_job(session, job)
