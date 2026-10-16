import shutil
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from clipper.domain.editing_plan import ClipType
from clipper.media import StoredUpload
from clipper.persistence import Project, now_utc
from clipper.persistence.models import ProjectJob

ACTIVE_PROJECT_STATUSES = {"queued", "downloading", "processing", "cancel_requested"}


class ProjectQueue:
    """Durable FIFO requests, drained by the application's single project worker."""

    def enqueue(
        self,
        session: Session,
        project: Project,
        language: str | None = None,
        clip_types: tuple[ClipType, ...] = (),
        source_url: str | None = None,
        *,
        retry: bool = False,
    ) -> ProjectJob:
        job = session.get(ProjectJob, project.id)
        if job and job.status in {"queued", "running"}:
            return job
        if project.status in {"processing", "downloading", "cancel_requested"}:
            raise ValueError("project is already processing")
        if not job:
            job = ProjectJob(project=project)
            session.add(job)
        if not retry:
            job.language = language
            job.clip_types = [item.value for item in clip_types]
        if source_url:
            job.source_url = source_url
        job.status = "queued"
        job.phase = "Waiting to start"
        job.error = None
        job.enqueued_at = now_utc()
        project.status = "queued"
        session.commit()
        return job

    def cancel(self, session: Session, project: Project) -> None:
        cancelled = session.execute(
            update(ProjectJob)
            .where(ProjectJob.project_id == project.id, ProjectJob.status == "queued")
            .values(status="cancelled", phase="Cancelled")
        )
        if cancelled.rowcount:  # type: ignore[attr-defined]
            project.status = "cancelled"
        else:
            session.refresh(project)
            if project.status in ACTIVE_PROJECT_STATUSES:
                project.status = "cancel_requested"
        session.commit()

    def recover(self, session: Session) -> None:
        """Called once at startup, before the worker can execute any jobs."""
        # Projects created before the durable queue have no worker to acknowledge
        # a stop request after a restart. Keep their artifacts and expose Resume.
        for project in session.scalars(
            select(Project).where(
                Project.status.in_(ACTIVE_PROJECT_STATUSES),
                ~Project.job.has(),
            )
        ):
            project.status = "cancelled"
            for stage in project.stages:
                if stage.status == "running":
                    stage.status = "cancelled"
                    stage.error = None
        for job in session.scalars(select(ProjectJob).where(ProjectJob.status == "running")):
            if job.project.status == "cancel_requested":
                job.status = "cancelled"
                job.phase = "Cancelled"
                job.project.status = "cancelled"
            else:
                job.status = "queued"
                job.phase = "Resuming interrupted work"
                job.project.status = "queued"
        session.commit()

    def run_next(
        self,
        session: Session,
        download: Callable[[str, Path], StoredUpload],
        analyze: Callable[[Session, str, str | None, tuple[ClipType, ...]], None],
    ) -> str | None:
        job = session.scalar(
            select(ProjectJob)
            .where(ProjectJob.status == "queued")
            .order_by(ProjectJob.enqueued_at, ProjectJob.project_id)
            .limit(1)
        )
        if not job:
            return None
        claimed = session.execute(
            update(ProjectJob)
            .where(ProjectJob.project_id == job.project_id, ProjectJob.status == "queued")
            .values(status="running", phase="Preparing media")
        )
        if not claimed.rowcount:  # type: ignore[attr-defined]
            session.rollback()
            return None
        project = job.project
        project.status = "processing"
        session.commit()
        try:
            if job.source_url and not project.media_sha256:
                job.phase = "Downloading video"
                project.status = "downloading"
                session.commit()
                # Each attempt gets its own directory, including after a hard restart.
                target = Path(project.source_path).parent / f"import-{uuid4()}"
                try:
                    stored = download(job.source_url, target)
                    session.refresh(project)
                    if project.status == "cancel_requested":
                        raise InterruptedError("Project stopped")
                    # Keep the source directly inside the owned source directory.
                    destination = target.parent / stored.path.name
                    stored.path.replace(destination)
                    project.source_path = str(destination)
                    project.original_filename = destination.name
                    project.media_sha256 = stored.sha256
                    session.commit()
                finally:
                    shutil.rmtree(target, ignore_errors=True)
            session.refresh(project)
            if project.status == "cancel_requested":
                raise InterruptedError("Project stopped")
            job.phase = "Analyzing video"
            project.status = "processing"
            session.commit()
            analyze(session, project.id, job.language, tuple(ClipType(t) for t in job.clip_types))
            session.refresh(project)
            if project.status == "cancel_requested":
                raise InterruptedError("Project stopped")
            job.status = "completed"
            job.phase = "Ready for review"
        except InterruptedError:
            session.rollback()
            project.status = "cancelled"
            job.status = "cancelled"
            job.phase = "Cancelled"
        except Exception as error:
            session.rollback()
            project.status = "failed"
            job.status = "failed"
            job.phase = "Needs attention"
            job.error = str(error)[:1000]
        session.commit()
        return project.id
