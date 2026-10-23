"""Read existing episode snapshots and assets; niche/style creation has been retired."""

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from clipper.api.informative import WorkflowRoute, serialize, short_service
from clipper.persistence import get_session
from clipper.persistence.models import InformativeShort
from clipper.rendering.episode_art import FONT_FILES, FONTS, render_episode_art
from clipper.rendering.frames import VERSION, render_frame
from clipper.rendering.series import render_source_card, render_thumbnail
from clipper.rendering.template_assets import template_artwork
from clipper.shorts.contracts import fingerprint
from clipper.shorts.frames import sequence_by_id
from clipper.shorts.series import EpisodeSnapshot

router = APIRouter(prefix="/content-series", route_class=WorkflowRoute)


def episode_snapshot(short: InformativeShort) -> EpisodeSnapshot | None:
    raw = short.artifacts.get("series_episode")
    return EpisodeSnapshot.model_validate(raw) if raw else None


@router.get("/fonts/{family}")
def video_font(family: str) -> FileResponse:
    filename = FONT_FILES.get(family)
    if not filename:
        raise LookupError("Video font not found")
    return FileResponse(FONTS / filename, media_type="font/ttf")


@router.get("/episodes/{short_id}")
def episode(short_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    short = short_service.get(session, short_id)
    short_service.sync_generation(session, short)
    snapshot = episode_snapshot(short)
    return {
        "short": serialize(short),
        "episode": snapshot.model_dump(mode="json") if snapshot else None,
    }


@router.get("/episodes/{short_id}/thumbnail")
def episode_thumbnail(short_id: str, session: Session = Depends(get_session)) -> FileResponse:
    short = short_service.get(session, short_id)
    snapshot = episode_snapshot(short)
    if not snapshot:
        raise LookupError("This video has no content-series thumbnail")
    thumbnail = short.artifacts.get("_series_thumbnail")
    generated = thumbnail.get("asset") if isinstance(thumbnail, dict) else None
    if isinstance(generated, str):
        asset = Path(generated).resolve()
        if asset.is_relative_to((short_service.root / short.id).resolve()) and asset.is_file():
            return FileResponse(asset, media_type="image/png", filename="thumbnail.png")
    key = fingerprint(snapshot.plan.headline + snapshot.series.model_dump_json())[:20]
    output = short_service.root / short.id / f"thumbnail-{key}.png"
    render_thumbnail(snapshot.series, snapshot.brief.subject, snapshot.plan.headline, output)
    return FileResponse(output, media_type="image/png", filename="thumbnail.png")


@router.get("/episodes/{short_id}/visuals/{section_id}")
def episode_visual(
    short_id: str, section_id: str, session: Session = Depends(get_session)
) -> FileResponse:
    short = short_service.get(session, short_id)
    snapshot = episode_snapshot(short)
    visual = (
        next((v for v in snapshot.plan.visuals if v.section_id == section_id), None)
        if snapshot
        else None
    )
    if not snapshot or not visual:
        raise LookupError("Storyboard visual not found")
    entry = short.artifacts.get(section_id)
    if (
        isinstance(entry, dict)
        and entry.get("asset")
        and entry.get("asset_kind") == "image"
        and (not entry.get("frame_generated") or entry.get("frame_version") == VERSION)
    ):
        saved = short_service.root / short.id
        asset = Path(entry["asset"]).resolve()
        if asset.is_relative_to(saved.resolve()) and asset.is_file():
            return FileResponse(asset)
    title = next((s.title for s in snapshot.brief.sources if s.id == visual.source_id), "")
    key = fingerprint(
        {"series": snapshot.series.model_dump(), "visual": visual.model_dump(), "renderer": VERSION}
    )[:20]
    output = short_service.root / short.id / f"visual-{key}.png"
    if visual.frame:
        render_frame(
            visual.frame,
            snapshot.style.frame_sequence or sequence_by_id(snapshot.style.id),
            output,
            footer=snapshot.brief.subject,
        )
    elif visual.kind == "illustration":
        # Preview is deliberately distinct from the eventual generated artwork.
        output = output.with_name(output.stem + "-preview.png")
        artwork = template_artwork(short_service.root.parent / "template-artwork", snapshot.style)
        render_episode_art(
            snapshot.series,
            visual,
            output,
            artwork,
            layout=snapshot.style.layout,
            weight=snapshot.style.design.weight if snapshot.style.design else 800,
            uppercase=snapshot.style.design.uppercase if snapshot.style.design else False,
        )
    else:
        render_source_card(snapshot.series, visual, title, output)
    return FileResponse(output, media_type="image/png")
