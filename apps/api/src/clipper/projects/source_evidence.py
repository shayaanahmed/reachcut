"""Cache source observations against the exact media, clip ranges and vision model."""

import json
from pathlib import Path

from sqlalchemy.orm import Session

from clipper.domain.editing_plan import EditingPlanV1
from clipper.persistence import Clip, RuntimeSetting
from clipper.projects.runtime_settings import RuntimeConfiguration
from clipper.providers.source_evidence import describe_source


def visual_evidence(session: Session, clip: Clip, runtime: RuntimeConfiguration) -> str:
    plan = EditingPlanV1.model_validate(clip.plan)
    spans = plan.source_slices or [plan.source]
    ranges = [(s.start_seconds, s.end_seconds) for s in spans]
    identity = {
        "version": 1,
        "media": clip.project.media_sha256,
        "ranges": ranges,
        "model": runtime.model_for("visual_review"),
        "server": runtime.ollama_base_url,
    }
    key = "clip-source-evidence:" + clip.id
    saved = session.get(RuntimeSetting, key)
    fingerprint = json.dumps(identity, sort_keys=True)
    if saved:
        payload = json.loads(saved.value)
        if payload.get("fingerprint") == fingerprint:
            return str(payload["observation"])
    source = Path(clip.project.source_path)
    try:
        observation = describe_source(
            runtime.ollama_base_url, runtime.model_for("visual_review"), source, ranges
        )
    except Exception as error:
        raise ValueError(
            "No speech was detected and source frames could not be analyzed. "
            "Check the visual review model in Settings and retry. " + str(error)[:300]
        ) from error
    payload = json.dumps({"fingerprint": fingerprint, "observation": observation})
    if saved:
        saved.value = payload
    else:
        session.add(RuntimeSetting(key=key, value=payload))
    session.commit()
    return observation
