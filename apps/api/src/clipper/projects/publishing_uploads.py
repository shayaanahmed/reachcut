import shutil
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from sqlalchemy.orm import Session

from clipper.domain.editing_plan import EditingPlanV1
from clipper.media import MediaError, safe_filename, store_upload
from clipper.media.ingestion import detect_container
from clipper.media.probe import probe_media
from clipper.persistence import Clip, Project, now_utc


def upload_publishing_video(
    session: Session,
    projects_root: Path,
    title: str,
    filename: str,
    stream: BinaryIO,
    max_bytes: int,
    max_duration_seconds: float,
) -> Project:
    """Keep a finished upload as an approved master in the publishing workflow."""
    filename = safe_filename(filename)
    if Path(filename).suffix.lower() != ".mp4":
        raise MediaError("Upload a finished MP4 video for publishing")
    project_id, clip_id = str(uuid4()), str(uuid4())
    root = projects_root.resolve() / project_id
    source = root / "source" / filename
    try:
        stored = store_upload(stream, source, max_bytes)
        with source.open("rb") as uploaded:
            if detect_container(uploaded.read(16)) != "iso-bmff":
                raise MediaError("Upload a finished MP4 video for publishing")
        info = probe_media(source, max_duration_seconds)
        duration = float(str(info["duration_seconds"]))
        plan = EditingPlanV1.model_validate(
            {
                "source": {"start_seconds": 0, "end_seconds": duration},
                "scores": dict.fromkeys(
                    ["overall", "hook", "clarity", "payoff", "visual_interest"], 0
                ),
                "rationale": "Finished video uploaded for publishing without editing.",
                "suggested_title": title.strip()[:100],
                "caption_config": {"enabled": False},
            }
        )
        final = source.parent / "clips" / clip_id / "final.mp4"
        final.parent.mkdir(parents=True)
        shutil.copy2(source, final)
        project = Project(
            id=project_id,
            title=title.strip(),
            original_filename=filename,
            source_path=str(source),
            media_sha256=stored.sha256,
            authorization_confirmed_at=now_utc(),
            status="complete",
            duration_seconds=duration,
            media_info=info,
        )
        session.add(project)
        session.add(
            Clip(
                id=clip_id,
                project=project,
                plan=plan.model_dump(mode="json"),
                approval_status="approved",
                final_path=str(final),
            )
        )
        session.commit()
        return project
    except Exception:
        session.rollback()
        shutil.rmtree(root, ignore_errors=True)
        raise
