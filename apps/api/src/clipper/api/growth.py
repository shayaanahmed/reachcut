import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from clipper.api.dependencies import runtime_settings_service
from clipper.config import settings
from clipper.editorial.growth import AudienceProfile, GrowthBrief
from clipper.persistence import Clip, SocialAccount, get_session, now_utc
from clipper.persistence.models import ClipGrowthBrief, GrowthPreparation, GrowthProfile
from clipper.projects.growth import generation_context, growth_report
from clipper.providers.ollama_growth import OllamaGrowthProvider

router = APIRouter()


def clip_or_404(session: Session, clip_id: str) -> Clip:
    clip = session.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(404, "Clip not found")
    return clip


def check_account(session: Session, account_id: str | None) -> None:
    if account_id and session.get(SocialAccount, account_id) is None:
        raise HTTPException(404, "Social account not found")


@router.get("/growth/insights")
def insights(session: Session = Depends(get_session)) -> object:
    return growth_report(session)


@router.get("/clips/{clip_id}/growth")
def read_growth(clip_id: str, session: Session = Depends(get_session)) -> object:
    clip_or_404(session, clip_id)
    saved = session.get(ClipGrowthBrief, clip_id)
    job = session.get(GrowthPreparation, clip_id)
    runtime = runtime_settings_service.get(session)
    return {
        "automatic_enabled": runtime.automatic_growth,
        "preparation": {"status": job.status, "error": job.error, "reasoning": job.reasoning}
        if job
        else None,
        "brief": GrowthBrief.model_validate(saved.payload) if saved else GrowthBrief(),
        "profiles": {
            row.account_id: AudienceProfile.model_validate(row.payload)
            for row in session.scalars(select(GrowthProfile))
        },
        "diagnoses": growth_report(session, clip_id=clip_id),
    }


@router.put("/clips/{clip_id}/growth", response_model=GrowthBrief)
def save_growth(
    clip_id: str, brief: GrowthBrief, session: Session = Depends(get_session)
) -> object:
    clip_or_404(session, clip_id)
    check_account(session, brief.account_id)
    row = session.get(ClipGrowthBrief, clip_id)
    if row is None:
        row = ClipGrowthBrief(clip_id=clip_id)
        session.add(row)
    row.payload = brief.model_dump(mode="json")
    row.updated_at = now_utc()
    if brief.account_id:
        profile = session.get(GrowthProfile, brief.account_id)
        if profile is None:
            profile = GrowthProfile(account_id=brief.account_id)
            session.add(profile)
        profile.payload = brief.profile.model_dump(mode="json")
    if not brief.automatic:
        job = session.get(GrowthPreparation, clip_id)
        if job:
            job.status = "manual"
    session.commit()
    return brief


@router.post("/clips/{clip_id}/growth/generate", response_model=GrowthBrief)
def generate_growth(
    clip_id: str, brief: GrowthBrief, session: Session = Depends(get_session)
) -> object:
    clip = clip_or_404(session, clip_id)
    check_account(session, brief.account_id)
    runtime = runtime_settings_service.get(session)
    try:
        context = generation_context(session, clip, brief)
        if not context.get("clip_transcript") and not context.get("generated_script"):
            from clipper.projects.source_evidence import visual_evidence

            context["visual_evidence"] = visual_evidence(session, clip, runtime)
        context.pop("clip_title", None)
        context.pop("clip_description", None)
        creative = OllamaGrowthProvider(
            runtime.ollama_base_url, runtime.model_for("growth"), settings.editorial_timeout_seconds
        ).generate(context)
    except (httpx.HTTPError, ValueError, KeyError) as error:
        raise HTTPException(
            502,
            "Could not generate growth copy. Check the local model and retry; "
            "your saved brief is unchanged.",
        ) from error
    return brief.model_copy(update={"creative": creative})


@router.post("/clips/{clip_id}/growth/prepare")
def prepare_growth(clip_id: str, session: Session = Depends(get_session)) -> object:
    from clipper.projects.growth_automation import request_preparation

    clip = clip_or_404(session, clip_id)
    request_preparation(session, clip, force=True)
    return read_growth(clip_id, session)
