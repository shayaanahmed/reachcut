import json

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class CaptionTranslationError(ValueError):
    """The configured local model could not produce a valid caption translation."""


class TranslationEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    translated_text: str = Field(min_length=1, max_length=20_000)


class OllamaCaptionTranslationProvider:
    """Translate caption text through Ollama while keeping timing in the caption domain."""

    CONTRACT_VERSION = "caption-translation-1"

    def __init__(self, base_url: str, model: str, timeout_seconds: float = 600) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    @property
    def identity(self) -> str:
        return f"ollama:{self.model}:{self.CONTRACT_VERSION}"

    def translate(self, text: str, source_language: str | None, target_language: str) -> str:
        source = source_language or "auto-detected"
        prompt = (
            f"Translate the following captions from {source} to {target_language}. "
            "Preserve names, numbers, tone, meaning, and punctuation. Do not add facts, "
            "commentary, timestamps, markdown, or labels. Return JSON with only "
            f'{{"translated_text":"..."}}. Captions:\n{text}'
        )
        response = httpx.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "think": False,
                "format": TranslationEnvelope.model_json_schema(),
                "options": {"temperature": 0.0},
            },
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
            payload = response.json()
            content = payload.get("response")
            if not isinstance(content, str):
                raise CaptionTranslationError("translation response was not text")
            translated = TranslationEnvelope.model_validate(json.loads(content))
        except (httpx.HTTPError, json.JSONDecodeError, ValidationError) as error:
            raise CaptionTranslationError("local caption translation failed") from error
        return translated.translated_text.strip()
