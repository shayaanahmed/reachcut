"""Saved growth briefs and observations from published posts."""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from clipper.domain.editing_plan import EditingPlanV1
from clipper.domain.transcript import Transcript
from clipper.editorial.growth import GrowthBrief, PostObservation, diagnose
from clipper.persistence.models import (
    Clip,
    ClipGrowthBrief,
    Publication,
    PublicationGrowthContext,
    RuntimeSetting,
)


def observations(session: Session) -> list[PostObservation]:
    posts = session.scalars(
        select(Publication)
        .where(Publication.status == "published")
        .options(
            selectinload(Publication.metric_snapshots),
            selectinload(Publication.account_link),
            selectinload(Publication.clip),
        )
    ).all()
    result = []
    for post in posts:
        for metric in post.metric_snapshots:
            result.append(
                PostObservation(
                    publication_id=post.id,
                    clip_id=post.clip_id,
                    project_id=post.clip.project_id,
                    title=post.title,
                    platform=post.platform,
                    account_id=post.social_account_id,
                    published_at=post.published_at or post.created_at,
                    recorded_at=metric.recorded_at,
                    views=metric.views,
                    **{
                        name: getattr(metric, name)
                        for name in (
                            "reach",
                            "sends",
                            "average_watch_seconds",
                            "opening_retention_percent",
                            "completion_rate_percent",
                            "search_views",
                        )
                    },
                )
            )
    return result


def growth_report(
    session: Session, *, clip_id: str | None = None, account_id: str | None = None
) -> list[dict[str, object]]:
    history = observations(session)
    latest: dict[str, PostObservation] = {}
    for item in history:
        previous = latest.get(item.publication_id)
        if previous is None or item.recorded_at >= previous.recorded_at:
            latest[item.publication_id] = item
    return [
        diagnose(item, history)
        for item in latest.values()
        if (clip_id is None or item.clip_id == clip_id)
        and (account_id is None or item.account_id == account_id)
    ]


def generation_context(session: Session, clip: Clip, brief: GrowthBrief) -> dict[str, object]:
    plan = EditingPlanV1.model_validate(clip.plan)
    ranges = plan.source_slices or [plan.source]
    transcript = (
        Transcript.model_validate(clip.project.transcript) if clip.project.transcript else None
    )
    text = (
        " ".join(
            segment.text
            for segment in transcript.segments
            if any(
                segment.end_seconds > span.start_seconds
                and segment.start_seconds < span.end_seconds
                for span in ranges
            )
        )
        if transcript
        else ""
    )
    report = growth_report(session, account_id=brief.account_id) if brief.account_id else []
    ranked = sorted(
        [
            r
            for r in report
            if r["account_id"] == brief.account_id
            and r["clip_id"] != clip.id
            and r["relative_views"] is not None
        ],
        key=lambda r: float(str(r["relative_views"])),
        reverse=True,
    )[:5]
    # Only measured performance crosses clip boundaries. Previous topics and audience
    # guesses are not factual evidence about the current video.
    examples = [
        {key: result[key] for key in ("views", "relative_views", "publication_id", "platform")}
        for result in ranked
    ]
    revision = session.get(RuntimeSetting, "informative-revision:" + clip.project_id)
    generated_script = json.loads(revision.value).get("script") if revision else None
    return {
        "generated_script": generated_script,
        "brief": brief.model_dump(mode="json"),
        "source_title": clip.project.title,
        "clip_title": plan.suggested_title,
        "clip_description": plan.suggested_description,
        "clip_transcript": text[:24000],
        "past_examples": examples,
        "learning_note": "Observational examples only; not evidence of causation or future views.",
    }


def capture_growth_context(session: Session, publication: Publication, clip_id: str) -> None:
    """Freeze the brief with the actual submitted copy, before later edits can change it."""
    saved = session.get(ClipGrowthBrief, clip_id)
    if saved:
        payload: dict[str, object] = {
            "brief": saved.payload,
            "submitted_title": publication.title,
            "submitted_description": publication.description,
        }
        if publication.growth_context:
            publication.growth_context.payload = payload
        else:
            publication.growth_context = PublicationGrowthContext(payload=payload)
