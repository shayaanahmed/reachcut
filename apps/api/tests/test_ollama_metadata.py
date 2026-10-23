import json

import httpx
import pytest
from pydantic import ValidationError

from clipper.editorial.publishing_metadata import PublishingMetadata
from clipper.providers.ollama_metadata import MetadataGenerationError, OllamaMetadataProvider

COPY = {
    "suggested_title": "Grow tomatoes at home",
    "suggested_description": "Learn how to grow tomatoes in a small garden.",
    "hashtags": ["#Tomatoes", "#Gardening", "#GrowYourOwn"],
}


def test_metadata_uses_ollama_compatible_schema_with_strict_domain_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def generate(url: str, **kwargs: object) -> httpx.Response:
        assert url == "http://ollama/api/generate"
        body = kwargs["json"]
        assert "pattern" not in body["format"]["properties"]["hashtags"]["items"]
        assert "maxLength" not in body["format"]["properties"]["suggested_description"]
        return httpx.Response(
            200, json={"response": json.dumps(COPY)}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx, "post", generate)
    result = OllamaMetadataProvider("http://ollama", "qwen3:8b").generate(
        "Gardening", "Growing tomatoes."
    )
    assert result.suggested_title == COPY["suggested_title"]
    # A transport-only relaxation must never weaken saved hashtag validation.
    with pytest.raises(ValidationError):
        PublishingMetadata.model_validate({**COPY, "hashtags": ["#Good", "#AlsoGood", "#Bad\tTag"]})


@pytest.mark.parametrize("json_body", [True, False])
def test_metadata_error_includes_ollama_rejection_reason(
    monkeypatch: pytest.MonkeyPatch, json_body: bool
) -> None:
    def reject(url: str, **kwargs: object) -> httpx.Response:
        response = (
            {"json": {"error": "Failed to initialize samplers: failed to parse grammar"}}
            if json_body
            else {"text": "Model failed to load"}
        )
        return httpx.Response(400, **response, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", reject)
    with pytest.raises(
        MetadataGenerationError,
        match="failed to parse grammar" if json_body else "Model failed to load",
    ):
        OllamaMetadataProvider("http://ollama", "qwen3:8b").generate("Video", "Transcript")


def test_metadata_description_remains_bounded_in_domain_validation() -> None:
    with pytest.raises(ValidationError):
        PublishingMetadata.model_validate({**COPY, "suggested_description": "x" * 4001})


def test_nested_ollama_error_reports_the_actual_message(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(url: str, **kwargs: object) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": json.dumps(
                    {
                        "error": {
                            "code": 400,
                            "message": "Failed to initialize samplers: failed to parse grammar",
                        }
                    }
                )
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", reject)
    with pytest.raises(
        MetadataGenerationError,
        match=r"HTTP 400.*Failed to initialize samplers: failed to parse grammar",
    ):
        OllamaMetadataProvider("http://ollama", "qwen3:8b").generate("Video", "Transcript")


def test_filename_without_source_content_never_becomes_a_topic(monkeypatch):
    from unittest.mock import Mock

    post = Mock()
    monkeypatch.setattr(httpx, "post", post)
    with pytest.raises(MetadataGenerationError, match="filename is not enough evidence"):
        OllamaMetadataProvider("http://ollama", "test").generate("Rea 30s", " ")
    post.assert_not_called()
