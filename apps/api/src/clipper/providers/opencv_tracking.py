from pathlib import Path
from typing import Any

import cv2
import numpy as np

from clipper.rendering.tracking import (
    CropPoint,
    TrackingCancellationProbe,
    TrackingProgressReporter,
    VisualAnalysis,
)


class VisualTrackingError(RuntimeError):
    pass


class OpenCvVisualTrackingProvider:
    """Sample local video frames for face/group and motion-centroid tracking."""

    CONTRACT_VERSION = "opencv-tracking-1"

    def __init__(self, sample_interval_seconds: float = 0.5) -> None:
        self.sample_interval_seconds = max(sample_interval_seconds, 0.1)
        cascade_path = (
            Path(cv2.data.haarcascades)  # type: ignore[attr-defined]
            / "haarcascade_frontalface_default.xml"
        )
        self._face_detector = cv2.CascadeClassifier(str(cascade_path))

    @property
    def identity(self) -> str:
        return f"opencv:{cv2.__version__}:{self.CONTRACT_VERSION}"

    def analyze(
        self,
        source: Path,
        cancelled: TrackingCancellationProbe,
        progress: TrackingProgressReporter,
    ) -> VisualAnalysis:
        cv2.setNumThreads(1)
        capture = cv2.VideoCapture(str(source))
        if not capture.isOpened():
            raise VisualTrackingError("OpenCV could not open the source video")
        fps = max(capture.get(cv2.CAP_PROP_FPS), 1)
        frame_count = max(capture.get(cv2.CAP_PROP_FRAME_COUNT), 1)
        duration = frame_count / fps
        face_points: list[CropPoint] = []
        group_points: list[CropPoint] = []
        action_points: list[CropPoint] = []
        sampled = 0
        frames_with_faces = 0
        previous_gray: np.ndarray[Any, Any] | None = None
        timestamp = 0.0
        try:
            while timestamp <= duration:
                if cancelled():
                    raise InterruptedError("visual tracking cancelled")
                capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
                ok, frame = capture.read()
                if not ok:
                    break
                frame = self._resize(np.asarray(frame, dtype=np.uint8))
                height, width = frame.shape[:2]
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = np.asarray(
                    self._face_detector.detectMultiScale(
                        gray,
                        scaleFactor=1.12,
                        minNeighbors=5,
                        minSize=(24, 24),
                    ),
                    dtype=np.int32,
                )
                if len(faces):
                    frames_with_faces += 1
                    largest = max(faces, key=lambda item: int(item[2]) * int(item[3]))
                    face_points.append(self._box_point(timestamp, largest, width, height))
                    group_points.append(self._group_point(timestamp, faces, width, height))
                if previous_gray is not None:
                    action_points.append(
                        self._motion_point(timestamp, previous_gray, gray, width, height)
                    )
                previous_gray = gray
                sampled += 1
                progress(min(timestamp / max(duration, 0.01), 0.99))
                timestamp += self.sample_interval_seconds
        finally:
            capture.release()
        progress(1.0)
        return VisualAnalysis(
            face_points=tuple(face_points),
            group_points=tuple(group_points),
            action_points=tuple(action_points),
            sampled_frames=sampled,
            frames_with_faces=frames_with_faces,
        )

    @staticmethod
    def _resize(frame: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
        height, width = frame.shape[:2]
        if width <= 480:
            return frame
        scale = 480 / width
        return cv2.resize(frame, (480, max(1, round(height * scale))))

    @staticmethod
    def _box_point(
        timestamp: float,
        box: Any,
        width: int,
        height: int,
    ) -> CropPoint:
        x, y, box_width, box_height = (int(value) for value in box)
        confidence = min((box_width * box_height) / max(width * height * 0.12, 1), 1)
        return CropPoint(
            timestamp,
            (x + box_width / 2) / width,
            (y + box_height / 2) / height,
            confidence,
        )

    @classmethod
    def _group_point(
        cls,
        timestamp: float,
        faces: Any,
        width: int,
        height: int,
    ) -> CropPoint:
        left = min(int(face[0]) for face in faces)
        top = min(int(face[1]) for face in faces)
        right = max(int(face[0] + face[2]) for face in faces)
        bottom = max(int(face[1] + face[3]) for face in faces)
        return cls._box_point(
            timestamp,
            np.array([left, top, right - left, bottom - top], dtype=np.int32),
            width,
            height,
        )

    @staticmethod
    def _motion_point(
        timestamp: float,
        previous: np.ndarray[Any, Any],
        current: np.ndarray[Any, Any],
        width: int,
        height: int,
    ) -> CropPoint:
        difference = cv2.absdiff(previous, current)
        difference = cv2.GaussianBlur(difference, (9, 9), 0)
        _, mask = cv2.threshold(difference, 22, 255, cv2.THRESH_BINARY)
        moments = cv2.moments(mask)
        active = moments["m00"]
        if active <= 0:
            return CropPoint(timestamp, 0.5, 0.5, 0)
        center_x = moments["m10"] / active / width
        center_y = moments["m01"] / active / height
        confidence = min(float(np.count_nonzero(mask)) / max(width * height * 0.12, 1), 1)
        return CropPoint(timestamp, float(center_x), float(center_y), confidence)
