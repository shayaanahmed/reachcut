from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from clipper.editorial.growth import GrowthBrief, PostObservation, diagnose
from clipper.main import app
from clipper.persistence import Base, Clip, Project, SocialAccount, get_session, now_utc
from clipper.providers.ollama_growth import OllamaGrowthProvider


def observation(id: str = "current", **kwargs: Any) -> PostObservation:
    values = {
        "publication_id": id,
        "clip_id": "clip-1",
        "project_id": "project-1",
        "title": "Local AI",
        "platform": "youtube",
        "account_id": "account-1",
        "published_at": datetime(2026, 10, 20, tzinfo=UTC),
        "recorded_at": datetime(2026, 10, 22, tzinfo=UTC),
        "views": 200,
    }
    values.update(kwargs)
    return PostObservation.model_validate(values)


def peers() -> list[PostObservation]:
    return [
        observation(
            str(i),
            published_at=datetime(2026, 10, i + 1, tzinfo=UTC),
            recorded_at=datetime(2026, 10, i + 3, tzinfo=UTC),
            views=1000,
            opening_retention_percent=80,
            completion_rate_percent=60,
        )
        for i in range(5)
    ]


def test_diagnosis_uses_account_history_and_measured_retention() -> None:
    post = observation(
        opening_retention_percent=30,
        completion_rate_percent=20,
        reach=100,
        sends=3,
        search_views=20,
    )
    result = diagnose(post, peers())
    assert result["baseline_views"] == 1000
    assert result["relative_views"] == 0.2
    assert result["sends_per_reach"] == 0.03
    assert result["search_share"] == 0.1
    assert len(result["actions"]) == 2


def test_duplicate_snapshots_other_accounts_and_ages_do_not_inflate_baseline() -> None:
    history = peers()[:4]
    history.extend([history[0]] * 10)
    history.extend(
        [
            observation("other-account", account_id="another"),
            observation("other-platform", platform="instagram"),
            observation(
                "young",
                published_at=datetime(2026, 10, 1, tzinfo=UTC),
                recorded_at=datetime(2026, 10, 1, 1, tzinfo=UTC),
            ),
            observation(
                "future",
                published_at=datetime(2026, 10, 25, tzinfo=UTC),
                recorded_at=datetime(2026, 10, 27, tzinfo=UTC),
            ),
        ]
    )
    result = diagnose(observation(), history)
    assert result["baseline_posts"] == 4
    assert result["baseline_views"] is None


def test_missing_zero_and_small_samples_are_not_invented() -> None:
    result = diagnose(observation(views=0, reach=0, sends=0, search_views=0), peers())
    assert result["sends_per_reach"] is None
    assert result["search_share"] is None
    assert result["confidence"] == "tentative"
    assert any("Not measured: opening retention" in line for line in result["findings"])
    assert not any("shorten the middle" in line for line in result["actions"])
    # An explicitly measured zero is meaningful, unlike missing data.
    result = diagnose(observation(opening_retention_percent=0), peers())
    assert any("first frame" in action for action in result["actions"])


@pytest.fixture
def client(make_plan, tmp_path):  # type: ignore[no-untyped-def]
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        project = Project(
            id="project-1",
            title="Local AI",
            original_filename="video.mp4",
            source_path=str(tmp_path / "source.mp4"),
            media_sha256="a" * 64,
            authorization_confirmed_at=now_utc(),
            status="review",
            transcript={
                "language": "en",
                "provider": "test",
                "model": "test",
                "segments": [
                    {
                        "id": 1,
                        "text": "Run AI locally on your own computer.",
                        "start_seconds": 0,
                        "end_seconds": 60,
                        "words": [],
                    }
                ],
            },
        )
        project.clips.append(
            Clip(
                id="clip-1",
                plan=make_plan().model_dump(mode="json"),
                approval_status="approved",
                final_path=str(tmp_path / "final.mp4"),
            )
        )
        session.add_all(
            [
                project,
                SocialAccount(id="account-1", platform="youtube", label="Tech", username="tech"),
            ]
        )
        session.commit()

    def override():  # type: ignore[no-untyped-def]
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_brief_profile_metrics_and_diagnosis_roundtrip(client) -> None:  # type: ignore[no-untyped-def]
    assert client.get("/api/clips/missing/growth").status_code == 404
    initial = client.get("/api/clips/clip-1/growth").json()
    assert initial["brief"]["creative"] is None
    brief = GrowthBrief(account_id="account-1", target_query="Run local AI").model_dump(mode="json")
    brief["profile"]["audience"] = "Developers"
    response = client.put("/api/clips/clip-1/growth", json=brief)
    assert response.status_code == 200
    loaded = client.get("/api/clips/clip-1/growth").json()
    assert loaded["brief"] == brief
    assert loaded["profiles"]["account-1"]["audience"] == "Developers"
    missing = {**brief, "account_id": "missing"}
    assert client.put("/api/clips/clip-1/growth", json=missing).status_code == 404
    assert (
        client.put(
            "/api/clips/clip-1/growth",
            json={
                **brief,
                "evidence": [
                    {
                        "query": "local AI",
                        "source_url": "not a url",
                        "observed_at": "bad",
                        "notes": "",
                    }
                ],
            },
        ).status_code
        == 422
    )
    publication = client.post(
        "/api/clips/clip-1/publications",
        json={
            "platform": "youtube",
            "social_account_id": "account-1",
            "post_url": "https://youtube.com/shorts/test",
            "title": "Local AI",
            "description": "Demo",
        },
    ).json()["clips"][0]["publications"][0]
    path = f"/api/publications/{publication['id']}/metrics"
    assert client.post(path, json={"completion_rate_percent": 101}).status_code == 422
    measured = client.post(
        path,
        json={
            "views": 200,
            "reach": 150,
            "sends": 3,
            "opening_retention_percent": 40,
            "search_views": 20,
        },
    )
    assert measured.status_code == 200
    snapshot = measured.json()["clips"][0]["publications"][0]["metric_snapshots"][0]
    assert snapshot["completion_rate_percent"] is None
    assert snapshot["opening_retention_percent"] == 40
    diagnosis = client.get("/api/growth/insights").json()[0]
    assert diagnosis["sends_per_reach"] == 0.02
    assert diagnosis["baseline_views"] is None


def test_generation_failure_preserves_saved_brief(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    brief = GrowthBrief(target_query="Local AI").model_dump(mode="json")
    client.put("/api/clips/clip-1/growth", json=brief)

    def fail(*args):  # type: ignore[no-untyped-def]
        raise httpx.ConnectError("Ollama is offline")

    monkeypatch.setattr(OllamaGrowthProvider, "generate", fail)
    assert client.post("/api/clips/clip-1/growth/generate", json=brief).status_code == 502
    assert client.get("/api/clips/clip-1/growth").json()["brief"] == brief


def test_existing_database_migration_is_repeatable(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from clipper.persistence import session as persistence

    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    # Simulate the pre-growth metrics table; create_schema must add nullable columns.
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE metric_snapshots (id INTEGER PRIMARY KEY)"))
    monkeypatch.setattr(persistence, "engine", engine)
    persistence.create_schema()
    persistence.create_schema()
    columns = {c["name"]: c for c in inspect(engine).get_columns("metric_snapshots")}
    assert columns["reach"]["nullable"]
    assert "opening_retention_percent" in columns
    engine.dispose()


def creative_payload() -> dict[str, object]:
    return {
        "openings": [
            {"opening_line": f"Opening {i}", "first_frame": f"Frame {i}"} for i in range(3)
        ],
        "packages": [
            {
                "platform": platform,
                "title": "Local AI",
                "caption": "Local demo",
                "cover_text": "Local AI",
                "hashtags": ["#LocalAI"],
            }
            for platform in ["youtube", "instagram", "facebook", "tiktok", "x"]
        ],
        "experiment": "Compare two openings across similar posts",
    }


def test_provider_passes_evidence_and_rejects_incomplete_platform_packages(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import json

    payload = creative_payload()
    captured = {}

    def post(url, **kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs["json"])
        return httpx.Response(
            200, request=httpx.Request("POST", url), json={"response": json.dumps(payload)}
        )

    monkeypatch.setattr(httpx, "post", post)
    provider = OllamaGrowthProvider("http://localhost:11434", "test-model", 10)
    result = provider.generate({"clip_transcript": "Demonstrate local AI", "past_examples": []})
    assert len(result.packages) == 5
    assert "Demonstrate local AI" in captured["prompt"]
    assert "maxLength" not in json.dumps(captured["format"])
    payload["packages"] = payload["packages"][:1]  # type: ignore[index]
    with pytest.raises(ValueError, match="each platform"):
        provider.generate({"clip_transcript": "Local AI demo"})


def test_generated_draft_does_not_replace_saved_brief(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from clipper.editorial.growth import GrowthCreative

    captured = {}

    def generate(self, context):  # type: ignore[no-untyped-def]
        captured.update(context)
        return GrowthCreative.model_validate(creative_payload())

    monkeypatch.setattr(OllamaGrowthProvider, "generate", generate)
    brief = GrowthBrief(account_id="account-1", target_query="Local AI").model_dump(mode="json")
    response = client.post("/api/clips/clip-1/growth/generate", json=brief)
    assert response.status_code == 200
    assert len(response.json()["creative"]["openings"]) == 3
    assert captured["brief"]["target_query"] == "Local AI"
    assert client.get("/api/clips/clip-1/growth").json()["brief"]["creative"] is None


def test_publication_keeps_the_brief_used_at_publish_time(client) -> None:  # type: ignore[no-untyped-def]
    from clipper.persistence.models import PublicationGrowthContext

    brief = GrowthBrief(account_id="account-1", target_query="Original question").model_dump(
        mode="json"
    )
    client.put("/api/clips/clip-1/growth", json=brief)
    response = client.post(
        "/api/clips/clip-1/publications",
        json={
            "platform": "youtube",
            "social_account_id": "account-1",
            "post_url": "https://youtube.com/shorts/original",
            "title": "Submitted title",
            "description": "Submitted caption",
        },
    )
    assert response.status_code == 200
    publication_id = response.json()["clips"][0]["publications"][0]["id"]
    client.put("/api/clips/clip-1/growth", json={**brief, "target_query": "Changed later"})
    for session in app.dependency_overrides[get_session]():
        saved = session.get(PublicationGrowthContext, publication_id)
        assert saved is not None
        assert saved.payload["brief"]["target_query"] == "Original question"
        assert saved.payload["submitted_title"] == "Submitted title"
        assert saved.payload["submitted_description"] == "Submitted caption"
    assert client.delete(f"/api/publications/{publication_id}").status_code == 200
    for session in app.dependency_overrides[get_session]():
        assert session.get(PublicationGrowthContext, publication_id) is None


def test_automatic_growth_populates_applies_and_reuses_preparation(client) -> None:  # type: ignore[no-untyped-def]
    from clipper.editorial.growth import AutomaticGrowthDecision
    from clipper.persistence.models import GrowthPreparation
    from clipper.projects.growth_automation import run_next
    from clipper.projects.runtime_settings import RuntimeConfiguration

    class Inference:
        calls = 0

        def infer(self, context):  # type: ignore[no-untyped-def]
            self.calls += 1
            assert context["source_title"] == "Local AI"
            return AutomaticGrowthDecision.model_validate(
                {
                    "profile": {
                        "audience": "Developers",
                        "niche": "Local AI",
                        "language": "English",
                        "country": "Global",
                    },
                    "target_query": "Run AI locally",
                    "creative": creative_payload(),
                    "selected_opening": 1,
                    "reasoning": "Lead with a clear demonstration",
                }
            )

    provider = Inference()
    applied = []
    runtime = RuntimeConfiguration("http://local", "text", "vision")
    for session in app.dependency_overrides[get_session]():
        clip = session.get(Clip, "clip-1")
        clip.final_path = None
        session.commit()
        assert (
            run_next(session, runtime, provider, lambda s, c, plan: applied.append(plan))
            == "clip-1"
        )
        assert len(applied) == 1
        assert applied[0].hook.text == "Opening 1"
        assert applied[0].hook.render
        assert run_next(session, runtime, provider) is None
        assert provider.calls == 1
        assert session.get(GrowthPreparation, "clip-1").status == "ready"
    data = client.get("/api/clips/clip-1/growth").json()
    assert data["brief"]["profile"]["audience"] == "Developers"
    assert data["brief"]["automatic"] is True
    assert data["preparation"]["reasoning"] == "Lead with a clear demonstration"


def test_automatic_growth_failure_is_durable_and_bounded(client) -> None:  # type: ignore[no-untyped-def]
    from clipper.persistence.models import GrowthPreparation
    from clipper.projects.growth_automation import request_preparation, run_next
    from clipper.projects.runtime_settings import RuntimeConfiguration

    class Offline:
        def infer(self, context):  # type: ignore[no-untyped-def]
            raise httpx.ConnectError("offline")

    runtime = RuntimeConfiguration("http://local", "text", "vision")
    for session in app.dependency_overrides[get_session]():
        assert run_next(session, runtime, Offline()) == "clip-1"
        job = session.get(GrowthPreparation, "clip-1")
        assert job.status == "failed"
        assert job.attempts == 1
        assert run_next(session, runtime, Offline()) is None
        job.updated_at -= timedelta(minutes=3)
        job.attempts = 3
        session.commit()
        assert run_next(session, runtime, Offline()) is None
        request_preparation(session, session.get(Clip, "clip-1"), force=True)
        assert job.status == "pending" and job.attempts == 0


def test_finished_exports_only_receive_publishing_metadata(client) -> None:  # type: ignore[no-untyped-def]
    from clipper.editorial.growth import AutomaticGrowthDecision
    from clipper.projects.growth_automation import run_next
    from clipper.projects.runtime_settings import RuntimeConfiguration

    class Inference:
        def infer(self, context):  # type: ignore[no-untyped-def]
            return AutomaticGrowthDecision.model_validate(
                {
                    "profile": {"audience": "Developers"},
                    "target_query": "Local AI",
                    "creative": creative_payload(),
                    "selected_opening": 0,
                    "reasoning": "Clear topic",
                }
            )

    applied = []
    for session in app.dependency_overrides[get_session]():
        clip = session.get(Clip, "clip-1")
        path, hook = clip.final_path, clip.plan["hook"]
        run_next(
            session,
            RuntimeConfiguration("http://local", "text", "vision"),
            Inference(),
            lambda *args: applied.append(args),
        )
        assert not applied
        assert clip.final_path == path and clip.plan["hook"] == hook
        assert clip.plan["suggested_title"] == "Local AI"


def test_background_metrics_refresh_backs_off_and_identical_views_do_not_reprepare(client) -> None:  # type: ignore[no-untyped-def]
    from clipper.persistence import RuntimeSetting
    from clipper.projects.growth_automation import preparation_key
    from clipper.projects.growth_metrics import refresh_growth_metrics
    from clipper.projects.publications import PublicationService
    from clipper.projects.runtime_settings import RuntimeConfiguration
    from clipper.publishing import OAuthConnection, ProviderMetrics

    class Credentials:
        def load(self, account_id):  # type: ignore[no-untyped-def]
            return OAuthConnection(str(account_id))

        def save(self, *args):  # type: ignore[no-untyped-def]
            pass

        def delete(self, *args):  # type: ignore[no-untyped-def]
            pass

    class Metrics:
        def metrics(self, *args):  # type: ignore[no-untyped-def]
            return ProviderMetrics("example", views=275, likes=10, comments=2)

    response = client.post(
        "/api/clips/clip-1/publications",
        json={
            "platform": "youtube",
            "social_account_id": "account-1",
            "post_url": "https://youtube.com/shorts/example",
            "title": "Local AI",
            "description": "Demo",
        },
    )
    publication_id = response.json()["clips"][0]["publications"][0]["id"]
    runtime = RuntimeConfiguration("http://local", "text", "vision")
    for session in app.dependency_overrides[get_session]():
        session.get(SocialAccount, "account-1").connection_status = "connected"
        session.commit()
        clip = session.get(Clip, "clip-1")
        before = preparation_key(session, clip, runtime)
        service = PublicationService()
        assert refresh_growth_metrics(session, service, {"youtube": Metrics()}, Credentials()) == 1
        first = preparation_key(session, clip, runtime)
        assert first != before
        assert refresh_growth_metrics(session, service, {"youtube": Metrics()}, Credentials()) == 0
        marker = session.get(RuntimeSetting, "growth-metrics:" + publication_id)
        marker.value = (now_utc() - timedelta(minutes=31)).isoformat()
        session.commit()
        assert refresh_growth_metrics(session, service, {"youtube": Metrics()}, Credentials()) == 1
        assert preparation_key(session, clip, runtime) == first


def test_pipeline_growth_is_visible_retries_failures_and_preserves_export(client):
    from clipper.editorial.growth import AutomaticGrowthDecision
    from clipper.persistence.models import GrowthPreparation, StageRun
    from clipper.projects.growth_pipeline import optimize_project
    from clipper.projects.runtime_settings import RuntimeConfiguration

    class Inference:
        fail = True

        def infer(self, context):
            if self.fail:
                raise ValueError("Select a faster growth model and retry")
            return AutomaticGrowthDecision.model_validate(
                {
                    "profile": {
                        "audience": "Developers",
                        "niche": "Local AI",
                        "language": "English",
                        "country": "Global",
                    },
                    "target_query": "Run AI locally",
                    "creative": creative_payload(),
                    "selected_opening": 0,
                    "reasoning": "Clear opening",
                }
            )

    runtime = RuntimeConfiguration("http://local", "text", "vision")
    provider = Inference()
    for session in app.dependency_overrides[get_session]():
        project = session.get(Project, "project-1")
        clip = project.clips[0]
        original_path, original_source = clip.final_path, clip.plan["source"]
        project.status = "processing"
        session.commit()
        with pytest.raises(ValueError, match="faster growth"):
            optimize_project(session, project, runtime, provider)
        preparation = session.get(GrowthPreparation, clip.id)
        assert preparation.status == "failed"
        assert "faster growth" in preparation.error
        stage = (
            session.query(StageRun).filter_by(project_id=project.id, name="optimize_growth").one()
        )
        assert stage.status == "failed"
        provider.fail = False
        optimize_project(session, project, runtime, provider)
        session.refresh(stage)
        assert stage.status == "succeeded"
        assert stage.attempts == 2
        assert stage.progress == 1
        assert preparation.status == "ready"
        assert clip.final_path == original_path
        assert clip.plan["source"] == original_source
        assert clip.growth_brief.payload["profile"]["audience"] == "Developers"
        assert project.status == "processing"


def test_cancelled_pipeline_does_not_start_growth_inference(client):
    from unittest.mock import Mock

    from clipper.projects.growth_pipeline import optimize_project
    from clipper.projects.runtime_settings import RuntimeConfiguration

    provider = Mock()
    for session in app.dependency_overrides[get_session]():
        project = session.get(Project, "project-1")
        project.status = "cancel_requested"
        session.commit()
        with pytest.raises(InterruptedError, match="stopped"):
            optimize_project(
                session, project, RuntimeConfiguration("http://local", "text", "vision"), provider
            )
        assert project.stages[0].status == "cancelled"
        provider.infer.assert_not_called()


def test_automatic_cover_headlines_are_bounded_without_weakening_contract(monkeypatch):
    from clipper.editorial.growth import AutomaticGrowthDecision

    payload = {
        "profile": {"audience": "Developers"},
        "target_query": "Local AI",
        "creative": creative_payload(),
        "selected_opening": 0,
        "reasoning": "Visible demo",
    }
    for package in payload["creative"]["packages"]:
        package["cover_text"] = (
            "A short video showing the actual product interface and its clearly visible controls. "
            * 3
        )

    def post(url, **kwargs):
        return httpx.Response(
            200, json={"response": json.dumps(payload)}, request=httpx.Request("POST", url)
        )

    import json

    monkeypatch.setattr(httpx, "post", post)
    result = OllamaGrowthProvider("http://local", "test", 10).infer(
        {"clip_transcript": "Run AI locally."}
    )
    assert all(len(package.cover_text) <= 100 for package in result.creative.packages)
    invalid = result.model_dump()
    invalid["creative"]["packages"][0]["cover_text"] = "x" * 101
    with pytest.raises(ValueError):
        AutomaticGrowthDecision.model_validate(invalid)


def test_automatic_profile_and_unrelated_default_cannot_contaminate_current_clip(client):
    from clipper.editorial.growth import AutomaticGrowthDecision
    from clipper.persistence.models import ClipGrowthBrief, GrowthProfile
    from clipper.projects.growth_automation import prepare_clip
    from clipper.projects.runtime_settings import RuntimeConfiguration

    class Inference:
        def infer(self, context):
            assert context["brief"]["profile"]["audience"] == ""
            assert context["brief"]["target_query"] == ""
            assert context["brief"]["creative"] is None
            assert context["account"] is None
            assert "clip_description" not in context
            assert "Islamic" not in str(context)
            return AutomaticGrowthDecision.model_validate(
                {
                    "profile": {"audience": "Developers"},
                    "target_query": "Local AI",
                    "creative": creative_payload(),
                    "selected_opening": 0,
                    "reasoning": "Source transcript",
                }
            )

    for session in app.dependency_overrides[get_session]():
        account = session.get(SocialAccount, "account-1")
        account.is_default = True
        session.add(
            GrowthProfile(account_id=account.id, payload={"audience": "Islamic governance"})
        )
        session.add(
            ClipGrowthBrief(
                clip_id="clip-1",
                payload=GrowthBrief(
                    automatic=True,
                    account_id=account.id,
                    target_query="Islamic governance",
                    profile={"audience": "Islamic governance"},
                ).model_dump(mode="json"),
            )
        )
        clip = session.get(Clip, "clip-1")
        clip.plan = {**clip.plan, "suggested_description": "Islamic governance"}
        session.commit()
        brief = prepare_clip(
            session, clip, RuntimeConfiguration("http://local", "text", "vision"), Inference()
        )
        assert brief.profile.audience == "Developers"
        assert session.get(GrowthProfile, account.id).payload["audience"] == "Islamic governance"


def test_silent_clip_uses_source_frames_and_reuses_only_matching_evidence(client, monkeypatch):
    from unittest.mock import Mock

    from clipper.editorial.growth import AutomaticGrowthDecision
    from clipper.projects import source_evidence
    from clipper.projects.growth_automation import prepare_clip
    from clipper.projects.runtime_settings import RuntimeConfiguration

    describe = Mock(
        return_value=(
            '{"identifiable":true,"description":"VoiceStudio interface",'
            '"visible_text":"VoiceStudio"}'
        )
    )
    monkeypatch.setattr(source_evidence, "describe_source", describe)

    class Inference:
        def infer(self, context):
            assert "VoiceStudio interface" in context["visual_evidence"]
            assert context["clip_transcript"] == ""
            return AutomaticGrowthDecision.model_validate(
                {
                    "profile": {"audience": "Software users"},
                    "target_query": "VoiceStudio",
                    "creative": creative_payload(),
                    "selected_opening": 0,
                    "reasoning": "Visible interface",
                }
            )

    for session in app.dependency_overrides[get_session]():
        clip = session.get(Clip, "clip-1")
        clip.project.transcript = None
        session.commit()
        runtime = RuntimeConfiguration("http://local", "text", "vision")
        prepare_clip(session, clip, runtime, Inference())
        prepare_clip(session, clip, runtime, Inference())
        assert describe.call_count == 1
        clip.project.media_sha256 = "b" * 64
        session.commit()
        prepare_clip(session, clip, runtime, Inference())
        assert describe.call_count == 2
