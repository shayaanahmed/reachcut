"""Durable automatic growth preparation for new clips and fresh account evidence."""

import hashlib
import json
from collections.abc import Callable
from datetime import timedelta
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from clipper.domain.editing_plan import EditingPlanV1, Hook
from clipper.editorial.growth import AudienceProfile, AutomaticGrowthDecision, GrowthBrief
from clipper.editorial.publishing_copy import caption_with_tags, complete_hashtags
from clipper.persistence import Clip, MetricSnapshot, Project, Publication, SocialAccount, now_utc
from clipper.persistence.models import (
    ClipGrowthBrief,
    GrowthPreparation,
    PublicationAccountLink,
)
from clipper.projects.growth import generation_context
from clipper.projects.runtime_settings import RuntimeConfiguration


class GrowthInference(Protocol):
    def infer(self, context: dict[str, object]) -> AutomaticGrowthDecision: ...


def choose_account(session: Session, clip: Clip) -> str | None:
    saved = session.get(ClipGrowthBrief, clip.id)
    if saved and not saved.payload.get("automatic") and saved.payload.get("account_id"):
        account_id = str(saved.payload["account_id"])
        account = session.get(SocialAccount, account_id)
        if account and account.is_active:
            return account_id
    # Learn from this clip's actual destination, never an unrelated default account.
    for post in sorted(clip.publications, key=lambda p: p.created_at, reverse=True):
        account = (
            session.get(SocialAccount, post.social_account_id) if post.social_account_id else None
        )
        if account and account.is_active:
            return account.id
    return None


def preparation_key(session: Session, clip: Clip, runtime: RuntimeConfiguration) -> str:
    account_id = choose_account(session, clip)
    latest_ids = select(func.max(MetricSnapshot.id)).group_by(MetricSnapshot.publication_id)
    metrics = (
        session.execute(
            select(
                MetricSnapshot.publication_id,
                MetricSnapshot.views,
                MetricSnapshot.sends,
                MetricSnapshot.opening_retention_percent,
                MetricSnapshot.completion_rate_percent,
                MetricSnapshot.search_views,
            )
            .join(Publication)
            .join(PublicationAccountLink)
            .where(
                PublicationAccountLink.social_account_id == account_id,
                MetricSnapshot.id.in_(latest_ids),
            )
            .order_by(MetricSnapshot.publication_id)
        ).all()
        if account_id
        else []
    )
    # Use content, source spans and measured evidence, excluding generated copy to avoid loops.
    plan = EditingPlanV1.model_validate(clip.plan)
    value = {
        "version": 2,
        "media": clip.project.media_sha256,
        "transcript": clip.project.transcript,
        "source": plan.source.model_dump(),
        "slices": [span.model_dump() for span in plan.source_slices],
        "account": account_id,
        "metrics": [tuple(row) for row in metrics],
        "model": runtime.model_for("growth"),
        "server": runtime.ollama_base_url,
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def request_preparation(session: Session, clip: Clip, *, force: bool = False) -> GrowthPreparation:
    job = session.get(GrowthPreparation, clip.id)
    if job is None:
        job = GrowthPreparation(clip_id=clip.id, status="pending")
        session.add(job)
    elif force and job.status != "working":
        job.status, job.error, job.attempts = "pending", None, 0
        job.fingerprint = ""
    session.commit()
    return job


def prepare_clip(
    session: Session,
    clip: Clip,
    runtime: RuntimeConfiguration,
    provider: GrowthInference,
    apply_edit: Callable[[Session, Clip, EditingPlanV1], None] | None = None,
    *,
    pipeline: bool = False,
) -> GrowthBrief:
    saved = session.get(ClipGrowthBrief, clip.id)
    # Generated preferences are observations of a previous clip, not user instructions.
    brief = (
        GrowthBrief.model_validate(saved.payload)
        if saved and saved.payload.get("automatic") is False
        else GrowthBrief()
    )
    account_id = choose_account(session, clip)
    brief.account_id = account_id
    input_key = preparation_key(session, clip, runtime)
    context = generation_context(session, clip, brief)
    if not context.get("clip_transcript") and not context.get("generated_script"):
        from clipper.projects.source_evidence import visual_evidence

        context["visual_evidence"] = visual_evidence(session, clip, runtime)
    # Previous generated copy must never become evidence for its own topic.
    context.pop("clip_title", None)
    context.pop("clip_description", None)
    account = session.get(SocialAccount, account_id) if account_id else None
    context["account"] = {"platform": account.platform} if account else None
    context["detected_language"] = (clip.project.transcript or {}).get("language")
    decision = provider.infer(context)
    session.refresh(clip)
    session.refresh(clip.project)
    current_job = session.get(GrowthPreparation, clip.id)
    if current_job:
        session.refresh(current_job)
        if current_job.status == "manual":
            current = session.get(ClipGrowthBrief, clip.id)
            if current:
                session.refresh(current)
                return GrowthBrief.model_validate(current.payload)
        if not pipeline and preparation_key(session, clip, runtime) != input_key:
            current_job.status = "pending"
            session.commit()
            return brief
    if clip.project.status not in (
        {"review", "complete", "processing"} if pipeline else {"review", "complete"}
    ):
        raise ValueError("Source processing changed during growth preparation")
    # Existing explicit audience preferences win over inference.
    decision.profile = AudienceProfile.model_validate(
        {
            key: value or getattr(decision.profile, key)
            for key, value in brief.profile.model_dump().items()
        }
    )
    result = brief.model_copy(
        update={
            "profile": decision.profile,
            "target_query": decision.target_query,
            "creative": decision.creative,
            "automatic": True,
        }
    )
    plan = EditingPlanV1.model_validate(clip.plan)
    decision.creative = complete_hashtags(decision.creative, plan.hashtags)
    result.creative = decision.creative
    package = next(
        (
            p
            for p in decision.creative.packages
            if p.platform == (account.platform if account else "youtube")
        ),
        decision.creative.packages[0],
    )
    plan.suggested_title, plan.suggested_description, plan.hashtags = (
        package.title,
        package.caption,
        package.hashtags,
    )
    active_post = any(
        p.status in {"queued", "processing", "published", "uncertain"} for p in clip.publications
    )
    if not clip.final_path and not active_post and apply_edit:
        opening = decision.creative.openings[decision.selected_opening]
        plan.hook = Hook(
            text=opening.opening_line[:160],
            start_seconds=0,
            end_seconds=min(3, plan.timeline_duration),
            render=True,
        )
        plan.thumbnail.headline = package.cover_text[:80]
        plan.thumbnail.generated = False
        apply_edit(session, clip, plan)
    # Metadata is safe to update without invalidating an existing export.
    clip.plan = plan.model_dump(mode="json")
    if saved is None:
        saved = ClipGrowthBrief(clip_id=clip.id)
        session.add(saved)
    saved.payload, saved.updated_at = result.model_dump(mode="json"), now_utc()
    job = session.get(GrowthPreparation, clip.id)
    if job:
        job.status, job.error, job.reasoning = "ready", None, decision.reasoning
        job.fingerprint, job.updated_at = preparation_key(session, clip, runtime), now_utc()
    session.commit()
    return result


def run_next(
    session: Session,
    runtime: RuntimeConfiguration,
    provider: GrowthInference,
    apply_edit: Callable[[Session, Clip, EditingPlanV1], None] | None = None,
) -> str | None:
    clips = session.scalars(
        select(Clip)
        .join(Project)
        .where(Project.status.in_(["review", "complete"]))
        .order_by(Project.created_at.desc(), Clip.id)
    ).all()
    for clip in clips:
        if not runtime.automatic_growth:
            requested = session.get(GrowthPreparation, clip.id)
            if not requested or requested.status != "pending":
                continue
        saved = session.get(ClipGrowthBrief, clip.id)
        job = session.get(GrowthPreparation, clip.id)
        if (
            saved
            and saved.payload.get("automatic") is False
            and (not job or job.status != "pending")
        ):
            continue  # Explicit manual briefs remain editable overrides.
        if (
            clip.publications
            and all(p.status == "published" for p in clip.publications)
            and (not job or job.status != "pending")
        ):
            continue
        key = preparation_key(session, clip, runtime)
        if job and job.status == "ready" and job.fingerprint == key:
            continue
        if job and job.status == "working":
            # The caller owns the cross-process lock: this is interrupted work.
            job.status = "pending"
        if (
            job
            and job.status == "failed"
            and job.fingerprint == key
            and (
                job.attempts >= 3
                or now_utc().replace(tzinfo=None) - job.updated_at.replace(tzinfo=None)
                < timedelta(minutes=2)
            )
        ):
            continue
        if any(p.status in {"processing", "uncertain"} for p in clip.publications):
            continue
        job = job or request_preparation(session, clip)
        if job.fingerprint != key:
            job.attempts = 0
        job.status, job.fingerprint = "working", key
        job.attempts += 1
        job.updated_at = now_utc()
        session.commit()
        try:
            prepare_clip(session, clip, runtime, provider, apply_edit)
        except Exception:
            session.rollback()
            job = session.get(GrowthPreparation, clip.id)
            if job:
                job.status, job.error = (
                    "failed",
                    "AI preparation failed. Check the growth model in Settings and retry.",
                )
                job.updated_at = now_utc()
                session.commit()
        return clip.id
    return None


def automatic_copy(session: Session, clip_id: str, platform: str) -> tuple[str, str] | None:
    saved = session.get(ClipGrowthBrief, clip_id)
    if not saved or saved.payload.get("automatic") is False:
        return None
    brief = GrowthBrief.model_validate(saved.payload)
    if brief.creative:
        package = next((p for p in brief.creative.packages if p.platform == platform), None)
        if package:
            caption = caption_with_tags(
                package.caption, package.hashtags or clip_tags(session, clip_id)
            )
            return package.title, caption[:280] if platform == "x" else caption
    return None


def clip_tags(session: Session, clip_id: str) -> list[str]:
    clip = session.get(Clip, clip_id)
    tags = clip.plan.get("hashtags", []) if clip else []
    return [str(tag) for tag in tags] if isinstance(tags, list) else []
