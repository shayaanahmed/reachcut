from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

import httpx
from sqlalchemy.orm import Session

from clipper.config import Settings
from clipper.persistence import RuntimeSetting

ModelTask = Literal[
    "clip_selection",
    "metadata",
    "growth",
    "research",
    "scripting",
    "translation",
    "visual_review",
    "image_generation",
]
MODEL_TASKS: tuple[ModelTask, ...] = (
    "clip_selection",
    "metadata",
    "growth",
    "research",
    "scripting",
    "translation",
    "visual_review",
    "image_generation",
)
TRANSCRIPTION_MODELS = ("tiny", "base", "small", "medium", "large-v3", "large-v3-turbo")


@dataclass(frozen=True)
class RuntimeConfiguration:
    ollama_base_url: str
    editorial_model: str
    thumbnail_model: str
    task_models: dict[ModelTask, str] = field(default_factory=dict)
    transcription_model: str = "large-v3-turbo"
    automatic_growth: bool = True

    def model_for(self, task: ModelTask) -> str:
        if task == "image_generation":
            return self.task_models.get(task) or "x/flux2-klein:4b"
        return self.task_models.get(task) or (
            self.thumbnail_model if task == "visual_review" else self.editorial_model
        )


class RuntimeSettingsError(ValueError):
    pass


class RuntimeSettingsService:
    OLLAMA_URL = "ollama_base_url"
    EDITORIAL_MODEL = "editorial_model"
    THUMBNAIL_MODEL = "thumbnail_model"
    TASK_MODELS = "task_models"
    TRANSCRIPTION_MODEL = "transcription_model"
    AUTOMATIC_GROWTH = "automatic_growth"

    def __init__(self, defaults: Settings) -> None:
        self._defaults = defaults

    def get(self, session: Session) -> RuntimeConfiguration:
        values = {
            item.key: item.value
            for item in session.query(RuntimeSetting).filter(
                RuntimeSetting.key.in_(
                    [
                        self.OLLAMA_URL,
                        self.EDITORIAL_MODEL,
                        self.THUMBNAIL_MODEL,
                        self.TASK_MODELS,
                        self.TRANSCRIPTION_MODEL,
                        self.AUTOMATIC_GROWTH,
                    ]
                )
            )
        }
        return RuntimeConfiguration(
            ollama_base_url=values.get(self.OLLAMA_URL, self._defaults.editorial_base_url).rstrip(
                "/"
            ),
            editorial_model=values.get(
                self.EDITORIAL_MODEL, self._defaults.editorial_model
            ).strip(),
            thumbnail_model=values.get(
                self.THUMBNAIL_MODEL, self._defaults.thumbnail_model
            ).strip(),
            task_models=json.loads(values.get(self.TASK_MODELS, "{}")),
            transcription_model=values.get(self.TRANSCRIPTION_MODEL, self._defaults.whisper_model),
            automatic_growth=values.get(self.AUTOMATIC_GROWTH, "true") == "true",
        )

    def update(
        self,
        session: Session,
        *,
        ollama_base_url: str,
        editorial_model: str,
        thumbnail_model: str,
        task_models: dict[ModelTask, str] | None = None,
        transcription_model: str | None = None,
        automatic_growth: bool | None = None,
    ) -> RuntimeConfiguration:
        url = ollama_base_url.strip().rstrip("/")
        model = editorial_model.strip()
        vision_model = thumbnail_model.strip()
        if not url.startswith(("http://", "https://")):
            raise RuntimeSettingsError("Ollama URL must begin with http:// or https://")
        if not model:
            raise RuntimeSettingsError("An Ollama model is required")
        if not vision_model:
            raise RuntimeSettingsError("A thumbnail vision model is required")
        extra: list[tuple[str, str]] = []
        if task_models is not None:
            if any(key not in MODEL_TASKS for key in task_models):
                raise RuntimeSettingsError("Unknown model task")
            cleaned = {key: value.strip() for key, value in task_models.items() if value.strip()}
            if any(len(value) > 200 for value in cleaned.values()):
                raise RuntimeSettingsError("Model names must be at most 200 characters")
            extra.append((self.TASK_MODELS, json.dumps(cleaned)))
        if transcription_model is not None:
            if transcription_model not in TRANSCRIPTION_MODELS:
                raise RuntimeSettingsError("Choose a supported Whisper model")
            extra.append((self.TRANSCRIPTION_MODEL, transcription_model))
        if automatic_growth is not None:
            extra.append((self.AUTOMATIC_GROWTH, str(automatic_growth).lower()))
        for key, value in (
            (self.OLLAMA_URL, url),
            (self.EDITORIAL_MODEL, model),
            (self.THUMBNAIL_MODEL, vision_model),
            *extra,
        ):
            setting = session.get(RuntimeSetting, key)
            if setting:
                setting.value = value
            else:
                session.add(RuntimeSetting(key=key, value=value))
        session.commit()
        return self.get(session)

    @staticmethod
    def ollama_models(base_url: str) -> list[str]:
        try:
            response = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=5)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise RuntimeSettingsError(f"Could not connect to Ollama: {error}") from error
        models = payload.get("models", []) if isinstance(payload, dict) else []
        names = {
            str(item.get("name") or item.get("model")).strip()
            for item in models
            if isinstance(item, dict) and (item.get("name") or item.get("model"))
        }
        return sorted(names)
