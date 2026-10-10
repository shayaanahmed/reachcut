from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from clipper.api.dependencies import automation_service, run_automation_cycle
from clipper.api.schemas import (
    AutomationPipelineActiveRequest,
    AutomationPipelineCreateRequest,
    AutomationPipelineResponse,
)
from clipper.persistence import AutomationPipeline, get_session
from clipper.projects import AutomationCreate, AutomationNotFoundError, AutomationStateError

router = APIRouter()


@router.get("/automations", response_model=list[AutomationPipelineResponse])
def automations(session: Session = Depends(get_session)) -> list[AutomationPipeline]:
    return automation_service.list_pipelines(session)


@router.post(
    "/automations",
    response_model=AutomationPipelineResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_automation(
    request: AutomationPipelineCreateRequest,
    session: Session = Depends(get_session),
) -> AutomationPipeline:
    try:
        return automation_service.create(
            session,
            AutomationCreate(
                name=request.name,
                project_id=request.project_id,
                social_account_ids=tuple(request.social_account_ids),
                clip_selection=request.clip_selection,
                clip_types=tuple(request.clip_types),
                schedule=request.schedule,
                next_run_at=request.next_run_at,
                title_template=request.title_template,
                description_template=request.description_template,
            ),
        )
    except AutomationNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except AutomationStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/automations/{pipeline_id}/run", status_code=status.HTTP_202_ACCEPTED)
def run_automation(
    pipeline_id: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    pipeline = session.get(AutomationPipeline, pipeline_id)
    if not pipeline:
        raise HTTPException(status_code=404, detail="automation pipeline not found")
    if pipeline.status == "running":
        raise HTTPException(status_code=409, detail="automation pipeline is already running")
    pipeline.status = "active"
    pipeline.next_run_at = datetime.now(UTC)
    pipeline.last_error = None
    session.commit()
    background_tasks.add_task(run_automation_cycle, pipeline_id)
    return {"status": "queued", "pipeline_id": pipeline_id}


@router.put("/automations/{pipeline_id}/active", response_model=AutomationPipelineResponse)
def set_automation_active(
    pipeline_id: str,
    request: AutomationPipelineActiveRequest,
    session: Session = Depends(get_session),
) -> AutomationPipeline:
    try:
        return automation_service.set_active(session, pipeline_id, active=request.active)
    except AutomationNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except AutomationStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.delete("/automations/{pipeline_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_automation(
    pipeline_id: str,
    session: Session = Depends(get_session),
) -> Response:
    try:
        automation_service.delete(session, pipeline_id)
    except AutomationNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
