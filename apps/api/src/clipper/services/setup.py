from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class OllamaSetupStatus:
    available: bool
    version: str | None
    model_installed: bool
    model_size_bytes: int | None


class OllamaSetupError(RuntimeError):
    """Raised when Ollama cannot complete a first-run setup operation."""


class OllamaUnavailableError(OllamaSetupError):
    """Raised when the local Ollama HTTP service cannot be reached."""


class OllamaSetupService:
    """Inspect and provision the configured Ollama model through its local API."""

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        request_timeout_seconds: float = 5,
        download_timeout_seconds: float = 7_200,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.request_timeout_seconds = request_timeout_seconds
        self.download_timeout_seconds = download_timeout_seconds
        self.transport = transport

    def status(self) -> OllamaSetupStatus:
        try:
            with self._client(self.request_timeout_seconds) as client:
                version_response = client.get("/api/version")
                version_response.raise_for_status()
                tags_response = client.get("/api/tags")
                tags_response.raise_for_status()
                version_payload = version_response.json()
                tags_payload = tags_response.json()
        except (httpx.HTTPError, ValueError, TypeError):
            return OllamaSetupStatus(False, None, False, None)

        if not isinstance(version_payload, dict) or not isinstance(tags_payload, dict):
            return OllamaSetupStatus(False, None, False, None)
        version = version_payload.get("version")
        if not isinstance(version, str):
            version = None

        wanted = self.model.casefold()
        models = tags_payload.get("models", [])
        if not isinstance(models, list):
            models = []
        for model in models:
            if not isinstance(model, dict):
                continue
            names = (model.get("name"), model.get("model"))
            if any(isinstance(name, str) and name.casefold() == wanted for name in names):
                size = model.get("size")
                return OllamaSetupStatus(
                    True,
                    version,
                    True,
                    size if isinstance(size, int) else None,
                )

        return OllamaSetupStatus(True, version, False, None)

    def pull_model(self) -> OllamaSetupStatus:
        try:
            with self._client(self.download_timeout_seconds) as client:
                response = client.post(
                    "/api/pull",
                    json={"model": self.model, "stream": False},
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.ConnectError as error:
            raise OllamaUnavailableError("Ollama is not running on this computer") from error
        except (httpx.HTTPError, ValueError, TypeError) as error:
            raise OllamaSetupError("Ollama could not download the editorial model") from error

        if not isinstance(payload, dict) or payload.get("status") != "success":
            raise OllamaSetupError("Ollama did not confirm the model download")

        status = self.status()
        if not status.available:
            raise OllamaUnavailableError("Ollama stopped before the model could be verified")
        if not status.model_installed:
            raise OllamaSetupError("The editorial model was not found after the download")
        return status

    def _client(self, timeout_seconds: float) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_seconds),
            transport=self.transport,
        )
