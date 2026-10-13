from __future__ import annotations

import base64

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from clipper.domain.editing_plan import ThumbnailTemplate
from clipper.rendering.thumbnails import ThumbnailChoice


class ThumbnailPlanningError(RuntimeError):
    pass


class ThumbnailDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frame_index: int = Field(ge=0, le=11)
    headline: str = Field(min_length=1, max_length=80)
    rationale: str = Field(min_length=1, max_length=160)


class OllamaThumbnailProvider:
    """Use a local vision model to choose a frame and write compact thumbnail copy."""

    CONTRACT_VERSION = "thumbnail-planning-1"

    def __init__(self, base_url: str, model: str, timeout_seconds: float = 600) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    @property
    def identity(self) -> str:
        return f"ollama:{self.model}:{self.CONTRACT_VERSION}"

    def plan(
        self,
        images: list[bytes],
        *,
        transcript: str,
        suggested_title: str,
        template: ThumbnailTemplate,
    ) -> ThumbnailChoice:
        if not images:
            raise ThumbnailPlanningError("thumbnail planning requires at least one frame")
        prompt = (
            f"Choose the strongest thumbnail frame from the {len(images)} images, numbered from "
            "0 in the order supplied. Prefer a clear expressive subject, sharp focus, useful "
            "negative space, and an image that honestly represents the clip. Write one compelling "
            "thumbnail headline of 3 to 7 words. Do not use clickbait that the transcript cannot "
            f"support. The customer selected the {template.value!r} template; do not change it. "
            "Return only the requested JSON schema.\n\n"
            f"Suggested clip title: {suggested_title}\n"
            f"Transcript excerpt: {transcript[:3000]}"
        )
        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                            "images": [base64.b64encode(image).decode("ascii") for image in images],
                        }
                    ],
                    "stream": False,
                    "think": False,
                    "format": ThumbnailDecision.model_json_schema(),
                    "options": {"temperature": 0},
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            message = payload.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, str):
                raise ThumbnailPlanningError("local vision model returned no thumbnail plan")
            decision = ThumbnailDecision.model_validate_json(content)
        except ThumbnailPlanningError:
            raise
        except (httpx.HTTPError, ValueError, ValidationError) as error:
            raise ThumbnailPlanningError(
                "local vision model could not plan this thumbnail"
            ) from error
        if decision.frame_index >= len(images):
            raise ThumbnailPlanningError("local vision model selected an unavailable frame")
        return ThumbnailChoice(decision.frame_index, decision.headline, decision.rationale)
