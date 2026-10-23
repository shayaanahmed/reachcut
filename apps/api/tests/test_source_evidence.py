import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from clipper.providers import source_evidence


@pytest.mark.parametrize("field", ["content", "thinking"])
def test_source_observation_uses_only_pixels_and_validates_complete_json(monkeypatch, field):
    monkeypatch.setattr(source_evidence, "review_samples", lambda source, spans: ["sample-image"])

    def post(url, **kwargs):
        body = kwargs["json"]
        assert body["messages"][0]["images"] == ["sample-image"]
        assert "Islamic governance" not in body["messages"][0]["content"]
        assert body["options"]["temperature"] == 0
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "done_reason": "stop",
                "message": {
                    "content": "",
                    field: json.dumps(
                        {
                            "identifiable": True,
                            "description": "An interface for VoiceStudio",
                            "visible_text": "VoiceStudio",
                        }
                    ),
                },
            },
        )

    monkeypatch.setattr(httpx, "post", post)
    result = source_evidence.describe_source("http://local", "vision", Path("video.mp4"), [(0, 30)])
    assert json.loads(result)["visible_text"] == "VoiceStudio"


@pytest.mark.parametrize("content", ["", "I think the video probably shows a product."])
def test_empty_or_unstructured_model_output_cannot_become_source_facts(monkeypatch, content):
    monkeypatch.setattr(source_evidence, "review_samples", lambda source, spans: ["sample"])
    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, **kwargs: httpx.Response(
            200, request=httpx.Request("POST", url), json={"message": {"content": content}}
        ),
    )
    with pytest.raises((ValueError, ValidationError)):
        source_evidence.describe_source("http://local", "vision", Path("video.mp4"), [(0, 30)])
