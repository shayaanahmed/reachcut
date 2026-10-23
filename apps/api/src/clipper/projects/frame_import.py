"""Persist uploaded frame collections in the application data directory."""

import json
import threading
from typing import Any
from uuid import uuid4

from clipper.config import settings
from clipper.shorts.frame_import import parse_frame_html
from clipper.shorts.frames import FrameSequence

_lock = threading.Lock()


def import_frame_html(document: str) -> dict[str, Any]:
    collection = parse_frame_html(document)
    for sequence in collection["sequences"]:
        FrameSequence.model_validate(sequence)
    with _lock:
        path = settings.data_dir / "frame-library.json"
        current = json.loads(path.read_text()) if path.exists() else {"frames": [], "sequences": []}
        merged = {
            kind: list({d["id"]: d for d in [*current[kind], *collection[kind]]}.values())
            for kind in ("frames", "sequences")
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".{uuid4().hex}.tmp")
        try:
            temporary.write_text(json.dumps(merged))
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return {"frames": len(collection["frames"]), "sequences": len(collection["sequences"])}
