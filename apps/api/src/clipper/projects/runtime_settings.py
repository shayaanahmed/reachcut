from __future__ import annotations

from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session

from clipper.config import Settings
from clipper.persistence import RuntimeSetting


@dataclass(frozen=True)
class RuntimeConfiguration:
    ollama_base_url: str
    editorial_model: str


class RuntimeSettingsError(ValueError):
    pass


class RuntimeSettingsService:
    OLLAMA_URL = "ollama_base_url"
    EDITORIAL_MODEL = "editorial_model"

    def __init__(self, defaults: Settings) -> None:
        self._defaults = defaults

    def get(self, session: Session) -> RuntimeConfiguration:
        values = {
            item.key: item.value
            for item in session.query(RuntimeSetting).filter(
                RuntimeSetting.key.in_([self.OLLAMA_URL, self.EDITORIAL_MODEL])
            )
        }
        return RuntimeConfiguration(
            ollama_base_url=values.get(self.OLLAMA_URL, self._defaults.editorial_base_url).rstrip(
                "/"
            ),
            editorial_model=values.get(
                self.EDITORIAL_MODEL, self._defaults.editorial_model
            ).strip(),
        )

    def update(
        self,
        session: Session,
        *,
        ollama_base_url: str,
        editorial_model: str,
    ) -> RuntimeConfiguration:
        url = ollama_base_url.strip().rstrip("/")
        model = editorial_model.strip()
        if not url.startswith(("http://", "https://")):
            raise RuntimeSettingsError("Ollama URL must begin with http:// or https://")
        if not model:
            raise RuntimeSettingsError("An Ollama model is required")
        for key, value in ((self.OLLAMA_URL, url), (self.EDITORIAL_MODEL, model)):
            setting = session.get(RuntimeSetting, key)
            if setting:
                setting.value = value
            else:
                session.add(RuntimeSetting(key=key, value=value))
        session.commit()
        return RuntimeConfiguration(url, model)

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
