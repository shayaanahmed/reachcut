"""Local vision check for subject relevance before generated artwork enters a short."""

import base64
import io
import json
from pathlib import Path

import httpx
from PIL import Image
from pydantic import Field

from clipper.shorts.contracts import Strict


class ArtworkReview(Strict):
    issues: list[str] = Field(max_length=3)


def review_artwork(base_url: str, model: str, artwork: Path, subject: str) -> list[str]:
    with Image.open(artwork) as source:
        image = source.convert("RGB")
        image.thumbnail((768, 1024))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)
    response = httpx.post(
        base_url.rstrip("/") + "/api/generate",
        json={
            "model": model,
            "stream": False,
            "think": False,
            "images": [base64.b64encode(buffer.getvalue()).decode()],
            "format": ArtworkReview.model_json_schema(),
            "prompt": (
                "Inspect this generated illustration for a short video. "
                "Return issues=[] if the main visible subject matches the brief. "
                "Report only: unrelated main subject, prominent unrelated portrait, "
                "obvious broken anatomy/objects, or unwanted lettering/logos/watermarks. "
                "Do not judge taste, demand actual software screenshots, or claim this "
                "illustration proves the tool was run. It is an illustration. "
                "Brief data: " + json.dumps(subject)
            ),
            "options": {"temperature": 0.1, "num_ctx": 8192, "num_predict": 1000},
        },
        timeout=180,
    )
    response.raise_for_status()
    return ArtworkReview.model_validate_json(response.json()["response"]).issues
