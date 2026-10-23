"""Extract timestamped samples from the rendered cut for a vision review."""

import base64
import io
from pathlib import Path

import cv2
from PIL import Image, ImageDraw


def review_samples(video: Path, timings: list[tuple[float, float]]) -> list[str]:
    capture = cv2.VideoCapture(str(video))
    try:
        if not capture.isOpened() or not timings:
            raise ValueError("Could not open the rendered video for AI review")
        result = []
        for index, (start, end) in enumerate(timings):
            sheet = Image.new("RGB", (540, 510), "#111111")
            draw = ImageDraw.Draw(sheet)
            for column, fraction in enumerate((0.45, 0.85)):
                timestamp = start + (end - start) * fraction
                capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
                ok, pixels = capture.read()
                if not ok:
                    raise ValueError(f"Could not sample scene {index + 1} for AI review")
                frame = Image.fromarray(cv2.cvtColor(pixels, cv2.COLOR_BGR2RGB))
                frame.thumbnail((270, 480))
                sheet.paste(frame, (column * 270 + (270 - frame.width) // 2, 30))
                draw.text(
                    (column * 270 + 8, 8), f"Scene {index + 1} / {timestamp:.1f}s", fill="white"
                )
            buffer = io.BytesIO()
            sheet.save(buffer, "JPEG", quality=85)
            result.append(base64.b64encode(buffer.getvalue()).decode())
        return result
    finally:
        capture.release()
