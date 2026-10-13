from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import cv2
import numpy as np

from clipper.domain.editing_plan import EditingPlanV1, ThumbnailTemplate, TimeRange
from clipper.media import MediaError


@dataclass(frozen=True)
class ThumbnailCandidate:
    source_time_seconds: float
    image: np.ndarray[Any, Any]
    quality: float


@dataclass(frozen=True)
class ThumbnailChoice:
    frame_index: int
    headline: str
    rationale: str


class ThumbnailPlanner(Protocol):
    def plan(
        self,
        images: list[bytes],
        *,
        transcript: str,
        suggested_title: str,
        template: ThumbnailTemplate,
    ) -> ThumbnailChoice: ...


class ThumbnailRenderer:
    """Select local video frames and compose deterministic branded thumbnails."""

    WIDTH = 1280
    HEIGHT = 720

    def sample_candidates(
        self,
        source: Path,
        plan: EditingPlanV1,
        *,
        limit: int = 8,
    ) -> list[ThumbnailCandidate]:
        cv2.setNumThreads(1)
        capture = cv2.VideoCapture(str(source))
        if not capture.isOpened():
            raise MediaError("OpenCV could not open the source video for thumbnail generation")
        candidates: list[ThumbnailCandidate] = []
        try:
            for timestamp in self._sample_times(plan, max(limit * 2, 12)):
                capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
                ok, frame = capture.read()
                if not ok:
                    continue
                image = np.asarray(frame, dtype=np.uint8)
                candidates.append(ThumbnailCandidate(timestamp, image, self._quality_score(image)))
        finally:
            capture.release()
        if not candidates:
            raise MediaError("No video frames were available for thumbnail generation")
        return sorted(candidates, key=lambda item: item.quality, reverse=True)[:limit]

    def jpeg_bytes(self, candidate: ThumbnailCandidate) -> bytes:
        preview = self._cover(candidate.image, 640, 360)
        ok, encoded = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 82])
        if not ok:
            raise MediaError("Could not encode a thumbnail candidate")
        return bytes(encoded)

    def render(
        self,
        candidate: ThumbnailCandidate,
        headline: str,
        template: ThumbnailTemplate,
        output: Path,
        *,
        logo_path: Path | None = None,
    ) -> None:
        canvas = self._cover(candidate.image, self.WIDTH, self.HEIGHT)
        if template is ThumbnailTemplate.SPEAKER:
            self._speaker_template(canvas, headline)
        elif template is ThumbnailTemplate.QUESTION:
            self._question_template(canvas, headline)
        elif template is ThumbnailTemplate.CINEMATIC:
            self._cinematic_template(canvas, headline)
        else:
            self._minimal_template(canvas, headline)
        if logo_path and logo_path.is_file():
            self._place_logo(canvas, logo_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(output), canvas):
            raise MediaError("Could not write the generated thumbnail")

    @staticmethod
    def _sample_times(plan: EditingPlanV1, count: int) -> list[float]:
        slices = plan.source_slices or [plan.source]
        duration = sum(item.end_seconds - item.start_seconds for item in slices)
        if duration <= 0:
            return [plan.source.start_seconds]
        positions = [duration * (index + 1) / (count + 1) for index in range(count)]
        return [ThumbnailRenderer._source_time(slices, position) for position in positions]

    @staticmethod
    def _source_time(slices: list[TimeRange], timeline_seconds: float) -> float:
        remaining = timeline_seconds
        for source_slice in slices:
            duration = source_slice.end_seconds - source_slice.start_seconds
            if remaining <= duration:
                return source_slice.start_seconds + remaining
            remaining -= duration
        return slices[-1].end_seconds

    @staticmethod
    def _quality_score(image: np.ndarray[Any, Any]) -> float:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        sharpness = min(float(cv2.Laplacian(gray, cv2.CV_64F).var()) / 450, 1)
        brightness = float(np.mean(gray))
        exposure = max(0.0, 1 - abs(brightness - 128) / 128)
        contrast = min(float(np.std(gray)) / 64, 1)
        return sharpness * 0.55 + exposure * 0.25 + contrast * 0.2

    @staticmethod
    def _cover(image: np.ndarray[Any, Any], width: int, height: int) -> np.ndarray[Any, Any]:
        source_height, source_width = image.shape[:2]
        scale = max(width / source_width, height / source_height)
        resized = cv2.resize(
            image,
            (max(width, round(source_width * scale)), max(height, round(source_height * scale))),
            interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC,
        )
        y = max((resized.shape[0] - height) // 2, 0)
        x = max((resized.shape[1] - width) // 2, 0)
        return resized[y : y + height, x : x + width].copy()

    @staticmethod
    def _overlay(canvas: np.ndarray[Any, Any], color: tuple[int, int, int], alpha: float) -> None:
        layer = np.full_like(canvas, color, dtype=np.uint8)
        cv2.addWeighted(layer, alpha, canvas, 1 - alpha, 0, dst=canvas)

    @staticmethod
    def _horizontal_gradient(
        canvas: np.ndarray[Any, Any],
        *,
        from_left: bool,
        strength: float,
    ) -> None:
        width = canvas.shape[1]
        values = np.linspace(strength, 0, width) if from_left else np.linspace(0, strength, width)
        alpha = np.repeat(values[np.newaxis, :, np.newaxis], canvas.shape[0], axis=0)
        canvas[:] = (canvas * (1 - alpha)).astype(np.uint8)

    def _speaker_template(self, canvas: np.ndarray[Any, Any], headline: str) -> None:
        self._horizontal_gradient(canvas, from_left=True, strength=0.88)
        cv2.rectangle(canvas, (54, 116), (68, 596), (42, 177, 238), -1)
        self._draw_headline(canvas, headline, (94, 230), 660, 2.0, (244, 244, 238))

    def _question_template(self, canvas: np.ndarray[Any, Any], headline: str) -> None:
        self._overlay(canvas, (20, 11, 5), 0.72)
        cv2.rectangle(canvas, (0, 0), (self.WIDTH, 94), (14, 25, 54), -1)
        cv2.rectangle(canvas, (0, 612), (self.WIDTH, self.HEIGHT), (14, 25, 54), -1)
        self._draw_headline(
            canvas,
            headline,
            (100, 250),
            1080,
            2.15,
            (230, 188, 72),
            centered=True,
        )

    def _cinematic_template(self, canvas: np.ndarray[Any, Any], headline: str) -> None:
        self._horizontal_gradient(canvas, from_left=True, strength=0.78)
        cv2.rectangle(canvas, (62, 506), (760, 620), (12, 29, 61), -1)
        self._draw_headline(canvas, headline, (84, 568), 660, 1.72, (244, 244, 238))
        cv2.line(canvas, (84, 640), (420, 640), (42, 177, 238), 7, cv2.LINE_AA)

    def _minimal_template(self, canvas: np.ndarray[Any, Any], headline: str) -> None:
        blurred = cv2.GaussianBlur(canvas, (0, 0), 18)
        cv2.addWeighted(blurred, 0.72, canvas, 0.28, 0, dst=canvas)
        self._overlay(canvas, (31, 20, 8), 0.56)
        cv2.rectangle(canvas, (130, 174), (1150, 548), (14, 25, 54), -1)
        cv2.rectangle(canvas, (130, 174), (1150, 548), (230, 188, 72), 3)
        self._draw_headline(
            canvas,
            headline,
            (180, 300),
            920,
            1.85,
            (244, 244, 238),
            centered=True,
        )

    @staticmethod
    def _draw_headline(
        canvas: np.ndarray[Any, Any],
        headline: str,
        origin: tuple[int, int],
        max_width: int,
        scale: float,
        color: tuple[int, int, int],
        *,
        centered: bool = False,
    ) -> None:
        normalized = " ".join(headline.upper().split())[:80]
        words = normalized.split()
        if not words:
            words = ["YOUR", "NEXT", "STORY"]
        lines: list[str] = []
        line = ""
        for word in words:
            candidate = f"{line} {word}".strip()
            width = cv2.getTextSize(candidate, cv2.FONT_HERSHEY_DUPLEX, scale, 4)[0][0]
            if line and width > max_width:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
        lines = lines[:3]
        line_height = round(86 * scale / 1.8)
        start_y = origin[1] - (len(lines) - 1) * line_height // 2
        for index, text in enumerate(lines):
            size = cv2.getTextSize(text, cv2.FONT_HERSHEY_DUPLEX, scale, 4)[0]
            x = origin[0]
            if centered:
                x = origin[0] + max((max_width - size[0]) // 2, 0)
            y = start_y + index * line_height
            cv2.putText(
                canvas,
                text,
                (x, y),
                cv2.FONT_HERSHEY_DUPLEX,
                scale,
                (4, 8, 18),
                10,
                cv2.LINE_AA,
            )
            cv2.putText(
                canvas,
                text,
                (x, y),
                cv2.FONT_HERSHEY_DUPLEX,
                scale,
                color,
                4,
                cv2.LINE_AA,
            )

    @staticmethod
    def _place_logo(canvas: np.ndarray[Any, Any], logo_path: Path) -> None:
        logo = cv2.imread(str(logo_path), cv2.IMREAD_UNCHANGED)
        if logo is None:
            return
        logo = cv2.resize(logo, (96, 96), interpolation=cv2.INTER_AREA)
        x, y = canvas.shape[1] - 128, 30
        region = canvas[y : y + 96, x : x + 96]
        if logo.shape[2] == 4:
            alpha = logo[:, :, 3:4].astype(np.float32) / 255
            region[:] = (logo[:, :, :3] * alpha + region * (1 - alpha)).astype(np.uint8)
        else:
            region[:] = logo[:, :, :3]


def fallback_headline(plan: EditingPlanV1) -> str:
    source = plan.suggested_title or (plan.hook.text if plan.hook else "A moment worth sharing")
    words = textwrap.shorten(" ".join(source.split()), width=64, placeholder="").split()
    return " ".join(words[:8]) or "A MOMENT WORTH SHARING"
