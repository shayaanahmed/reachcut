from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np

from clipper.media import MediaError

_REFERENCE_ID = re.compile(r"^[0-9a-f-]{36}\.png$")


class StoryReferenceService:
    def __init__(self, root: Path, max_bytes: int = 20 * 1024**2) -> None:
        self._root = root
        self._max_bytes = max_bytes

    def save(self, content: bytes) -> str:
        if not content or len(content) > self._max_bytes:
            raise MediaError("Reference image must be between 1 byte and 20 MB")
        encoded = np.frombuffer(content, dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image is None or image.shape[0] < 128 or image.shape[1] < 128:
            raise MediaError("Reference must be a valid image at least 128 x 128 pixels")
        reference_id = f"{uuid4()}.png"
        output = self._root.resolve() / reference_id
        output.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(output), image):
            raise MediaError("Could not store the character reference")
        return reference_id

    def resolve(self, reference_id: str | None) -> Path | None:
        if not reference_id:
            return None
        if not _REFERENCE_ID.fullmatch(reference_id):
            raise MediaError("Invalid character reference")
        candidate = self._root.resolve() / reference_id
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as error:
            raise MediaError("Character reference not found") from error
        if resolved.parent != self._root.resolve() or not resolved.is_file():
            raise MediaError("Character reference not found")
        return resolved
