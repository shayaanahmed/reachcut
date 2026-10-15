"""Bounded frame sampling for local vision classification."""

import math
from pathlib import Path

import cv2

from clipper.media.errors import MediaError


def sample_template_frames(path: Path) -> tuple[list[bytes], float]:
    capture = cv2.VideoCapture(str(path))
    try:
        fps = capture.get(cv2.CAP_PROP_FPS)
        count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        if not all(math.isfinite(value) and value > 0 for value in (fps, count)):
            raise MediaError("The template must be a readable video")
        duration = count / fps
        if duration > 180:
            raise MediaError("Template clips must be no longer than three minutes")
        frames: list[bytes] = []
        for index in range(8):
            capture.set(cv2.CAP_PROP_POS_FRAMES, int((count - 1) * index / 7))
            ok, frame = capture.read()
            if not ok:
                continue
            height, width = frame.shape[:2]
            scale = min(1.0, 768 / max(height, width))
            frame = cv2.resize(frame, (max(1, int(width * scale)), max(1, int(height * scale))))
            encoded_ok, encoded = cv2.imencode(".jpg", frame)
            if encoded_ok:
                frames.append(encoded.tobytes())
        if len(frames) < 2:
            raise MediaError("Could not sample enough frames from this template")
        return frames, duration
    finally:
        capture.release()
