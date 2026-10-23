"""HTTP-only adapter for the inspected Voicebox backend (no model imports)."""

from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field

from clipper.shorts.contracts import ShortSettings

# Voicebox currently exposes model installation via HTTP, but not its registry's
# language metadata. Fail closed on unknown models. Manifest from backend/backends.
_QWEN_LANGUAGES = ["zh", "en", "ja", "ko", "de", "fr", "ru", "pt", "es", "it"]
MODEL_CAPABILITIES: dict[str, tuple[str, list[str], bool]] = {
    "qwen-tts-1.7B": ("qwen", _QWEN_LANGUAGES, False),
    "qwen-tts-0.6B": ("qwen", _QWEN_LANGUAGES, False),
    "qwen-custom-voice-1.7B": ("qwen_custom_voice", _QWEN_LANGUAGES, True),
    "qwen-custom-voice-0.6B": ("qwen_custom_voice", _QWEN_LANGUAGES, True),
    "luxtts": ("luxtts", ["en"], False),
    "chatterbox-tts": (
        "chatterbox",
        [
            "zh",
            "en",
            "ja",
            "ko",
            "de",
            "fr",
            "ru",
            "pt",
            "es",
            "it",
            "he",
            "ar",
            "da",
            "el",
            "fi",
            "hi",
            "ms",
            "nl",
            "no",
            "pl",
            "sv",
            "sw",
            "tr",
        ],
        False,
    ),
    "chatterbox-turbo": ("chatterbox_turbo", ["en"], False),
    "kokoro": ("kokoro", ["en", "es", "fr", "hi", "it", "pt", "ja", "zh"], False),
    "tada-1b": ("tada", ["en"], False),
    "tada-3b-ml": ("tada", ["en", "ar", "zh", "de", "es", "fr", "it", "ja", "pl", "pt"], False),
}


class VoiceboxError(RuntimeError):
    pass


class Generation(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    status: str
    error: str | None = None


class VoiceboxNarrationProvider:
    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=30)

    def _request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        try:
            response = self.client.request(method, self.base_url + path, **kwargs)  # type: ignore[arg-type]
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as error:
            raise VoiceboxError(
                f"Voicebox returned {error.response.status_code}. Check the profile, "
                "engine and installed model in Voicebox."
            ) from error
        except httpx.HTTPError as error:
            raise VoiceboxError(
                "Voicebox is unreachable. Start the separate service and check "
                "CLIPPER_VOICEBOX_BASE_URL. Interrupted submissions must be "
                "reconciled before retry."
            ) from error

    def capabilities(self) -> dict[str, object]:
        health = self._request("GET", "/health").json()
        profiles = self._request("GET", "/profiles").json()
        models = self._request("GET", "/models/status").json().get("models", [])
        engines: list[dict[str, object]] = []
        for model in models:
            name = model.get("model_name", "")
            capability = MODEL_CAPABILITIES.get(name)
            if capability:
                engine, languages, instructions = capability
                engines.append(
                    {
                        **model,
                        "engine": engine,
                        "languages": languages,
                        "supports_delivery": instructions,
                    }
                )
        return {
            "connected": health.get("status") == "healthy",
            "profiles": profiles,
            "engines": engines,
            "capability_basis": "inspected Voicebox registry; unknown models disabled",
            "language_notice": "Urdu and Urdu-English switching are unverified; upload narration.",
            "cost_usd": 0,
            "estimated_seconds": None,
        }

    def validate(self, settings: ShortSettings) -> None:
        if settings.language in {"ur", "ur-en", "mixed"}:
            raise VoiceboxError("Urdu narration is unverified. Upload your own narration instead.")
        caps = self.capabilities()
        engines = caps["engines"]
        assert isinstance(engines, list)
        matches = [
            e
            for e in engines
            if e["engine"] == settings.engine
            and (
                settings.engine in {"kokoro", "luxtts", "chatterbox", "chatterbox_turbo"}
                or settings.model_size.lower() in e["model_name"].lower()
            )
        ]
        installed = [e for e in matches if e.get("downloaded") and not e.get("downloading")]
        if not installed:
            raise VoiceboxError(
                "Install the selected model explicitly in Voicebox before generation."
            )
        model = installed[0]
        if settings.language not in model["languages"]:
            raise VoiceboxError("Selected engine does not support this language. Upload narration.")
        if settings.delivery and not model["supports_delivery"]:
            raise VoiceboxError("This engine does not support delivery instructions.")
        profiles = caps["profiles"]
        assert isinstance(profiles, list)
        if settings.profile_id not in {p["id"] for p in profiles}:
            raise VoiceboxError(
                "Select an available Voicebox profile in Settings or the video overrides."
            )

    def submit(self, text: str, settings: ShortSettings) -> str:
        self.validate(settings)
        payload = {
            "profile_id": settings.profile_id,
            "text": text,
            "language": settings.language,
            "engine": settings.engine,
            "model_size": settings.model_size,
            "instruct": settings.delivery or None,
            "personality": False,
        }
        return Generation.model_validate(self._request("POST", "/generate", json=payload).json()).id

    def status(self, generation_id: str) -> str:
        result = Generation.model_validate(
            self._request("GET", f"/history/{quote(generation_id, safe='')}").json()
        )
        return result.status

    def audio(self, generation_id: str) -> bytes:
        response = self._request("GET", f"/history/{quote(generation_id, safe='')}/export-audio")
        if not response.content or len(response.content) > 200 * 1024 * 1024:
            raise VoiceboxError("Voicebox returned empty or oversized audio")
        return response.content

    def cancel(self, generation_id: str) -> bool:
        self._request("POST", f"/generate/{quote(generation_id, safe='')}/cancel")
        return self.status(generation_id) == "cancelled"
