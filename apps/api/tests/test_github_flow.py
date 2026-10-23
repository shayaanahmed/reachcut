"""The repository story is saved before any template is selected."""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from test_short_studio import SOURCE, client, narrative_output

from clipper.api.informative import short_service
from clipper.projects import short_studio as jobs
from clipper.providers.studio_editor import OllamaStudioEditor
from clipper.providers.studio_narrative import Narrative
from clipper.shorts.frames import frame_sequences

__all__ = ["client"]


def test_repository_storyboard_precedes_template_and_survives_video_creation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    story = narrative_output()
    story["beats"].pop(3)
    saved = Narrative.model_validate(story)
    draft = Mock(return_value=saved)
    monkeypatch.setattr(OllamaStudioEditor, "draft", draft)
    monkeypatch.setattr("clipper.rendering.frames.validate_frame_layout", lambda *args: [])
    response = client.post(
        "/api/short-studio/ideas",
        json={
            "category": "github",
            "repo_url": SOURCE.url,
            "flow": "storyboard",
            "request_key": "github-story-first",
        },
    )
    assert response.status_code == 200
    job = client.get("/api/short-studio/jobs/" + response.json()["id"]).json()
    assert job["status"] == "ready", job
    brief = job["brief"]
    assert len(brief["storyboard"]) == 5
    assert job["short_id"] == ""
    # Choosing a template must reuse the approved narration instead of calling the writer again.
    monkeypatch.setattr(
        "clipper.providers.studio_editor.write_narrative",
        Mock(side_effect=AssertionError("Template selection must preserve the storyboard")),
    )
    response = client.post(
        "/api/short-studio/storyboards",
        json={
            "brief_id": brief["id"],
            "storyline_id": brief["storyboard_storyline_id"],
            "sequence_id": frame_sequences()[1].id,
            "frame_mode": "manual",
            "auto_produce": True,
            "request_key": "github-template-video",
        },
    )
    assert response.status_code == 200, response.text
    planned = client.get("/api/short-studio/jobs/" + response.json()["id"]).json()
    assert planned["status"] == "ready", planned
    detail = client.get("/api/content-series/episodes/" + planned["short_id"]).json()
    assert [section["text"] for section in detail["short"]["script"]["sections"]] == [
        beat.narration for beat in saved.beats
    ]
    assert detail["short"]["status"] == "queued"
    with jobs.SessionLocal() as session:
        short = short_service.get(session, planned["short_id"])
        assert short.artifacts["studio"]["final_review_required"] is True
        assert short.approved_hash == short_service.approval_hash(short)
    draft.assert_called_once()


def test_autoproduction_requires_a_reviewable_saved_storyboard(client: TestClient) -> None:
    from test_short_studio import start_ideas

    brief = start_ideas(client)["brief"]
    response = client.post(
        "/api/short-studio/storyboards",
        json={
            "brief_id": brief["id"],
            "storyline_id": brief["storylines"][0]["id"],
            "sequence_id": frame_sequences()[0].id,
            "auto_produce": True,
            "request_key": "no-unreviewed-auto-video",
        },
    )
    assert response.status_code == 422
    assert "saved storyboard" in response.json()["detail"]
