import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from clipper.api.projects import project_or_404
from clipper.config import settings
from clipper.media import MediaError
from clipper.persistence import get_session
from clipper.persistence.models import SourceWorkflowRun
from clipper.projects.source_workflows import WorkflowRequest, create_workflow

router = APIRouter()


def response(run: SourceWorkflowRun) -> dict[str, object]:
    return {
        "id": run.id,
        "source_project_id": run.source_project_id,
        "source_title": run.source_title,
        "target_project_id": run.target_project_id,
        "kind": run.kind,
        "target_language": run.target_language,
        "scopes": run.scopes,
        "clip_ids": run.clip_ids,
        "status": run.status,
        "error": run.error,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


@router.get("/projects/{project_id}/workflows")
def workflows(project_id: str, session: Session = Depends(get_session)) -> object:
    source = project_or_404(session, project_id)
    transcript = source.transcript
    return {
        "speech_available": bool(transcript.get("segments")) if transcript else None,
        "runs": [
            response(run)
            for run in session.scalars(
                select(SourceWorkflowRun)
                .where(
                    or_(
                        SourceWorkflowRun.source_project_id == project_id,
                        SourceWorkflowRun.target_project_id == project_id,
                    )
                )
                .order_by(SourceWorkflowRun.created_at.desc())
                .limit(100)
            )
        ],
    }


@router.post("/projects/{project_id}/workflows", status_code=202)
def start_workflow(
    project_id: str,
    payload: str = Form(),
    narration: UploadFile | None = File(default=None),
    session: Session = Depends(get_session),
) -> object:
    source = project_or_404(session, project_id)
    try:
        request = WorkflowRequest.model_validate(json.loads(payload))
        run = create_workflow(
            session,
            source,
            request,
            settings.data_dir / "projects",
            narration.file if narration else None,
            narration.filename or "narration.wav" if narration else "narration.wav",
        )
    except (ValidationError, json.JSONDecodeError) as error:
        raise HTTPException(
            422, "Check the workflow, target language and selected options"
        ) from error
    except (ValueError, OSError, MediaError) as error:
        raise HTTPException(409, str(error)) from error
    return response(run)


@router.post("/workflow-runs/{run_id}/retry", status_code=202)
def retry_workflow(run_id: UUID, session: Session = Depends(get_session)) -> object:
    from clipper.projects.queue import ProjectQueue

    run = session.get(SourceWorkflowRun, str(run_id))
    if not run or run.status not in {"failed", "cancelled"}:
        raise HTTPException(409, "Only failed or paused runs can be retried")
    target = project_or_404(session, run.target_project_id)
    if target.job and target.job.status in {"queued", "running"}:
        raise HTTPException(409, "This output already has a run in progress")
    if (
        run.kind == "metadata"
        and run.clip_ids
        and not set(run.clip_ids).issubset({clip.id for clip in target.clips})
    ):
        raise HTTPException(
            409, "Selected clips were removed; start a workflow with existing clips"
        )
    run.status, run.error, run.finished_at = "queued", None, None
    ProjectQueue().enqueue(
        session,
        target,
        processing_mode=(
            "clips" if run.kind == "clips" else "language" if run.kind == "language" else "metadata"
        ),
    )
    return response(run)
