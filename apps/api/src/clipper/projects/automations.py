from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from clipper.domain.editing_plan import ClipType, EditingPlanV1
from clipper.editorial import recommend_for_publishing
from clipper.persistence import (
    AutomationPipeline,
    Clip,
    Project,
    Publication,
    PublicationAccountLink,
    SocialAccount,
    now_utc,
)
from clipper.projects.clips import ClipService
from clipper.projects.publications import AutomaticPublicationCreate, PublicationService
from clipper.publishing import CredentialStore, PublishingAdapter


class AutomationNotFoundError(LookupError):
    pass


class AutomationStateError(RuntimeError):
    pass


@dataclass(frozen=True)
class AutomationCreate:
    name: str
    project_id: str
    social_account_ids: tuple[str, ...]
    clip_selection: str
    clip_types: tuple[ClipType, ...]
    schedule: str
    next_run_at: datetime
    title_template: str = "{clip_title}"
    description_template: str = "{hashtags}"


class AutomationService:
    def list_pipelines(self, session: Session) -> list[AutomationPipeline]:
        return list(
            session.scalars(
                select(AutomationPipeline).order_by(AutomationPipeline.created_at.desc())
            )
        )

    def create(self, session: Session, request: AutomationCreate) -> AutomationPipeline:
        if not session.get(Project, request.project_id):
            raise AutomationNotFoundError("project not found")
        if not request.social_account_ids:
            raise AutomationStateError("select at least one publishing account")
        accounts = [session.get(SocialAccount, item) for item in request.social_account_ids]
        if any(account is None or not account.is_active for account in accounts):
            raise AutomationNotFoundError("one or more social accounts were not found")
        if any(account and account.connection_status != "connected" for account in accounts):
            raise AutomationStateError("connect every selected account before scheduling")
        scheduled = self._aware(request.next_run_at)
        pipeline = AutomationPipeline(
            name=request.name.strip(),
            project_id=request.project_id,
            social_account_ids=list(dict.fromkeys(request.social_account_ids)),
            clip_selection=request.clip_selection,
            clip_types=[item.value for item in request.clip_types],
            schedule=request.schedule,
            next_run_at=scheduled,
            title_template=request.title_template.strip() or "{clip_title}",
            description_template=request.description_template.strip() or "{hashtags}",
        )
        session.add(pipeline)
        session.commit()
        session.refresh(pipeline)
        return pipeline

    def delete(self, session: Session, pipeline_id: str) -> None:
        pipeline = session.get(AutomationPipeline, pipeline_id)
        if not pipeline:
            raise AutomationNotFoundError("automation pipeline not found")
        session.delete(pipeline)
        session.commit()

    def set_active(self, session: Session, pipeline_id: str, *, active: bool) -> AutomationPipeline:
        pipeline = session.get(AutomationPipeline, pipeline_id)
        if not pipeline:
            raise AutomationNotFoundError("automation pipeline not found")
        if pipeline.status == "running":
            raise AutomationStateError("a running pipeline cannot be deactivated")
        previous_status = pipeline.status
        if active:
            pipeline.status = "active"
            pipeline.last_error = None
            if (
                previous_status in {"completed", "failed"}
                or self._aware(pipeline.next_run_at) < now_utc()
            ):
                pipeline.next_run_at = now_utc()
        else:
            pipeline.status = "paused"
        session.commit()
        session.refresh(pipeline)
        return pipeline

    def execute_due(
        self,
        session: Session,
        clip_service: ClipService,
        publication_service: PublicationService,
        adapters: Mapping[str, PublishingAdapter],
        credentials: CredentialStore,
        *,
        pipeline_id: str | None = None,
        analyze_project: Callable[[str, tuple[ClipType, ...]], None] | None = None,
    ) -> list[str]:
        now = now_utc()
        query = select(AutomationPipeline).where(AutomationPipeline.status == "active")
        if pipeline_id:
            query = query.where(AutomationPipeline.id == pipeline_id)
        else:
            query = query.where(AutomationPipeline.next_run_at <= now)
        completed_ids: list[str] = []
        for pipeline in session.scalars(query):
            self._execute_one(
                session,
                pipeline,
                clip_service,
                publication_service,
                adapters,
                credentials,
                analyze_project,
            )
            completed_ids.append(pipeline.id)
        return completed_ids

    def _execute_one(
        self,
        session: Session,
        pipeline: AutomationPipeline,
        clip_service: ClipService,
        publication_service: PublicationService,
        adapters: Mapping[str, PublishingAdapter],
        credentials: CredentialStore,
        analyze_project: Callable[[str, tuple[ClipType, ...]], None] | None,
    ) -> None:
        pipeline.status = "running"
        pipeline.last_error = None
        session.commit()
        try:
            project = session.get(Project, pipeline.project_id)
            if not project:
                raise AutomationStateError("project is unavailable")
            selected_clip_types = tuple(ClipType(item) for item in pipeline.clip_types)
            if project.status in {"created", "failed"} and analyze_project:
                analyze_project(project.id, selected_clip_types)
                session.expire_all()
                project = session.get(Project, pipeline.project_id)
            if not project or project.status != "review":
                raise AutomationStateError("project analysis is not ready")
            clips = list(
                session.scalars(select(Clip).where(Clip.project_id == pipeline.project_id))
            )
            selected_types = set(pipeline.clip_types)
            if selected_types:
                clips = [
                    clip
                    for clip in clips
                    if EditingPlanV1.model_validate(clip.plan).clip_type.value in selected_types
                ]
            if not clips:
                raise AutomationStateError("no generated clips match this pipeline")
            clips.sort(key=self._score, reverse=True)
            if pipeline.clip_selection == "best":
                clips = clips[:1]
            accounts = [session.get(SocialAccount, item) for item in pipeline.social_account_ids]
            if any(account is None or not account.is_active for account in accounts):
                raise AutomationStateError("a selected publishing account is unavailable")
            for clip in clips:
                if pipeline.auto_approve and clip.approval_status != "approved":
                    clip_service.set_approval(session, clip.id, True)
                if not clip.final_path:
                    clip_service.render_final(session, clip.id)
                plan = EditingPlanV1.model_validate(clip.plan)
                fields = {
                    "clip_title": plan.suggested_title
                    or (plan.hook.text if plan.hook else "ReachCut clip"),
                    "project_title": project.title,
                    "clip_type": plan.clip_type.value,
                    "hashtags": " ".join(plan.hashtags),
                }
                title = self._format(pipeline.title_template, fields)[:100]
                description = self._format(pipeline.description_template, fields)[:5000]
                for account in accounts:
                    assert account is not None
                    already_published = session.scalar(
                        select(Publication.id)
                        .join(PublicationAccountLink)
                        .where(
                            Publication.clip_id == clip.id,
                            PublicationAccountLink.social_account_id == account.id,
                            Publication.status.in_(["processing", "published"]),
                        )
                    )
                    if already_published:
                        continue
                    adapter = adapters.get(account.platform)
                    if not adapter:
                        raise AutomationStateError(
                            f"automatic publishing is not configured for {account.platform}"
                        )
                    publication_service.publish(
                        session,
                        clip.id,
                        AutomaticPublicationCreate(
                            social_account_id=account.id,
                            title=title,
                            description=description,
                        ),
                        adapter,
                        credentials,
                    )
            refreshed = session.get(AutomationPipeline, pipeline.id)
            assert refreshed is not None
            refreshed.last_run_at = now_utc()
            refreshed.status = "completed" if refreshed.schedule == "once" else "active"
            if refreshed.schedule == "daily":
                refreshed.next_run_at = self._aware(refreshed.next_run_at) + timedelta(days=1)
            elif refreshed.schedule == "weekly":
                refreshed.next_run_at = self._aware(refreshed.next_run_at) + timedelta(days=7)
            session.commit()
        except Exception as error:
            session.rollback()
            failed = session.get(AutomationPipeline, pipeline.id)
            if failed:
                failed.status = "failed"
                failed.last_run_at = now_utc()
                failed.last_error = str(error)[:1000]
                session.commit()

    @staticmethod
    def _score(clip: Clip) -> int:
        return recommend_for_publishing(EditingPlanV1.model_validate(clip.plan)).score

    @staticmethod
    def _format(template: str, fields: dict[str, str]) -> str:
        rendered = template
        for key, value in fields.items():
            rendered = rendered.replace("{" + key + "}", value)
        return rendered

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
