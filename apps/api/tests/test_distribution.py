from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from clipper.main import app
from clipper.persistence import (
    Base,
    Clip,
    Project,
    Publication,
    SocialAccount,
    get_session,
    now_utc,
)
from clipper.persistence.models import PublicationDestination
from clipper.projects.distribution import (
    AccountGroupService,
    approve_clips,
    queue_project_publications,
)
from clipper.projects.publications import (
    AutomaticPublicationCreate,
    PublicationService,
    PublicationStateError,
)
from clipper.providers.publishing_http import ProviderAuthenticationError
from clipper.publishing import OAuthConnection


class Credentials:
    def load(self, account_id: str) -> OAuthConnection | None:
        return OAuthConnection(access_token="test-value", external_account_id=account_id)  # noqa: S106

    def save(self, account_id: str, connection: OAuthConnection) -> None:
        pass

    def delete(self, account_id: str) -> None:
        pass


@pytest.fixture
def distribution(make_plan) -> Generator[tuple[Session, Project, list[SocialAccount]], None, None]:  # type: ignore[no-untyped-def]
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        project = Project(
            title="Faith",
            original_filename="source.mp4",
            source_path="/data/source.mp4",
            media_sha256="abc",
            authorization_confirmed_at=now_utc(),
        )
        project.clips = [
            Clip(
                plan=make_plan().model_dump(mode="json"),
                approval_status="approved",
                final_path="/data/final.mp4",
            )
            for _ in range(3)
        ]
        accounts = [
            SocialAccount(platform="youtube", label="Religious YT", connection_status="connected"),
            SocialAccount(
                platform="instagram", label="Religious IG", connection_status="connected"
            ),
            SocialAccount(platform="facebook", label="Art FB", connection_status="disconnected"),
        ]
        session.add_all([project, *accounts])
        session.commit()
        yield session, project, accounts
    engine.dispose()


def test_group_lifecycle_preserves_accounts_and_allows_overlap(distribution) -> None:  # type: ignore[no-untyped-def]
    session, _, accounts = distribution
    service = AccountGroupService()
    first = service.save(session, None, "Religious", "Faith channels", [a.id for a in accounts[:2]])
    second = service.save(session, None, "Tech", "", [accounts[0].id])
    assert accounts[0].id in first.account_ids and accounts[0].id in second.account_ids
    service.save(session, first.id, "Spiritual", "Updated", [accounts[1].id])
    assert first.name == "Spiritual" and first.account_ids == [accounts[1].id]
    with pytest.raises(PublicationStateError, match="already exists"):
        service.save(session, None, " spiritual ", "", [])
    service.delete(session, first.id)
    assert len(service.list_groups(session)) == 1
    assert session.get(SocialAccount, accounts[1].id) is not None


def test_group_rejects_invalid_members_without_losing_existing_members(distribution) -> None:  # type: ignore[no-untyped-def]
    session, _, accounts = distribution
    service = AccountGroupService()
    group = service.save(session, None, "Art", "", [accounts[0].id])
    with pytest.raises(PublicationStateError, match="active"):
        service.save(session, group.id, "Renamed", "", ["missing"])
    assert group.name == "Art" and group.account_ids == [accounts[0].id]


def test_approval_is_atomic_and_scoped_to_project(distribution) -> None:  # type: ignore[no-untyped-def]
    session, project, _ = distribution
    for clip in project.clips:
        clip.approval_status = "pending"
    session.commit()
    with pytest.raises(PublicationStateError):
        approve_clips(session, project.id, [project.clips[0].id, "foreign"])
    assert all(c.approval_status == "pending" for c in project.clips)
    approve_clips(session, project.id, [project.clips[0].id])
    assert [c.approval_status for c in project.clips] == ["approved", "pending", "pending"]
    approve_clips(session, project.id, None)
    assert all(c.approval_status == "approved" for c in project.clips)


def test_bulk_queues_valid_pairs_and_explains_skips_and_duplicates(distribution) -> None:  # type: ignore[no-untyped-def]
    session, project, accounts = distribution
    project.clips[1].approval_status = "pending"
    project.clips[2].final_path = None
    session.commit()
    group = AccountGroupService().save(session, None, "Religious", "", [a.id for a in accounts])
    service = PublicationService()
    queued, skipped = queue_project_publications(
        session, project.id, None, [], group.id, None, Credentials(), service
    )
    assert len(queued) == 2 and len(skipped) == 7
    assert any("Reconnect" in s.reason for s in skipped)
    assert any("Approve" in s.reason for s in skipped)
    assert any("Render" in s.reason for s in skipped)
    session.expire_all()
    repeated, skipped_again = queue_project_publications(
        session, project.id, None, [], group.id, None, Credentials(), service
    )
    assert not repeated and len(skipped_again) == 9
    assert any("Already queued" in s.reason for s in skipped_again)
    assert len(list(session.scalars(select(Publication)))) == 2


def test_failed_publication_releases_destination_for_retry(distribution) -> None:  # type: ignore[no-untyped-def]
    session, project, accounts = distribution
    service = PublicationService()
    request = AutomaticPublicationCreate(accounts[0].id, "Title", "Caption")
    _, queued = service.queue_many(session, project.clips[0].id, [request], Credentials())
    with pytest.raises(PublicationStateError, match="already"):
        service.queue_many(session, project.clips[0].id, [request], Credentials())
    service.mark_failed(session, queued[0][0], "Upload rejected")
    assert session.get(PublicationDestination, queued[0][0]) is None
    session.expire_all()
    _, retry = service.queue_many(session, project.clips[0].id, [request], Credentials())
    assert len(retry) == 1


def test_expired_metrics_token_marks_only_affected_account_disconnected(distribution) -> None:  # type: ignore[no-untyped-def]
    from clipper.persistence.models import PublicationAccountLink

    session, project, accounts = distribution
    post = Publication(
        clip_id=project.clips[0].id,
        platform="instagram",
        status="published",
        post_url="https://instagram.com/reel/test",
    )
    session.add(post)
    session.flush()
    post.account_link = PublicationAccountLink(
        social_account_id=accounts[1].id,
        account_label_snapshot=accounts[1].label,
        account_username_snapshot="",
    )
    session.commit()

    class ExpiredMetrics:
        def metrics(self, *args):  # type: ignore[no-untyped-def]
            raise ProviderAuthenticationError("Reconnect this account")

    with pytest.raises(ProviderAuthenticationError):
        PublicationService().sync_metrics(
            session, post.id, {"instagram": ExpiredMetrics()}, Credentials()
        )
    assert accounts[1].connection_status == "disconnected"
    assert accounts[0].connection_status == "connected"
    assert post.status == "published"


def test_group_and_bulk_api_validation(distribution, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    import clipper.api.distribution as api

    session, project, accounts = distribution

    def override() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_session] = override
    monkeypatch.setattr(api, "credential_store", Credentials())
    calls = []
    monkeypatch.setattr(api, "run_publication_batch", lambda batch: calls.extend(batch))
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/social-account-groups",
                json={"name": "Religious", "account_ids": [accounts[0].id]},
            )
            assert created.status_code == 201
            group_id = created.json()["id"]
            assert (
                client.put(
                    f"/api/social-account-groups/{group_id}",
                    json={"name": "Faith", "account_ids": [accounts[0].id]},
                ).status_code
                == 200
            )
            assert (
                client.post(
                    f"/api/projects/{project.id}/clips/approve-batch", json={"clip_ids": []}
                ).status_code
                == 422
            )
            result = client.post(
                f"/api/projects/{project.id}/publish-batch",
                json={"group_id": group_id, "clip_ids": [project.clips[0].id]},
            )
            assert result.status_code == 202, result.text
            assert result.json()["queued"] == 1 and len(calls) == 1
            assert len(result.json()["project"]["clips"][0]["publications"]) == 1
            assert client.delete(f"/api/social-account-groups/{group_id}").status_code == 204
    finally:
        app.dependency_overrides.clear()


def test_stale_session_cannot_queue_duplicate_destinations(distribution) -> None:  # type: ignore[no-untyped-def]
    session, project, accounts = distribution
    service = PublicationService()
    clip_id, account_id = project.clips[0].id, accounts[0].id
    request = AutomaticPublicationCreate(account_id, "Title", "Caption")
    with Session(session.get_bind()) as stale:
        clip = stale.get(Clip, clip_id)
        assert clip is not None and not clip.publications
        service.queue_many(session, clip_id, [request], Credentials())
        with pytest.raises(PublicationStateError, match="already"):
            service.queue_many(stale, clip_id, [request], Credentials())
    assert len(list(session.scalars(select(Publication)))) == 1


def test_zero_destinations_is_a_safe_background_noop() -> None:
    from clipper.api.dependencies import run_publication_batch

    run_publication_batch([])


def test_metrics_response_updates_loaded_snapshots_without_expiring_session(distribution) -> None:  # type: ignore[no-untyped-def]
    from clipper.persistence.models import PublicationAccountLink
    from clipper.projects.publications import MetricCreate
    from clipper.publishing import ProviderMetrics

    session, project, accounts = distribution
    post = Publication(
        clip_id=project.clips[0].id,
        platform="youtube",
        status="published",
        post_url="https://youtube.com/shorts/test",
    )
    session.add(post)
    session.flush()
    post.account_link = PublicationAccountLink(
        social_account_id=accounts[0].id,
        account_label_snapshot=accounts[0].label,
        account_username_snapshot="",
    )
    session.commit()
    assert not post.metric_snapshots
    service = PublicationService()
    service.record_metrics(session, post.id, MetricCreate(views=10, revenue=5, conversions=2))
    assert len(post.metric_snapshots) == 1

    class Metrics:
        def metrics(self, *args):  # type: ignore[no-untyped-def]
            return ProviderMetrics(external_id="video", views=25, likes=3, comments=1)

    service.sync_metrics(session, post.id, {"youtube": Metrics()}, Credentials())
    assert len(post.metric_snapshots) == 2
    assert post.metric_snapshots[-1].views == 25
    assert post.metric_snapshots[-1].revenue == 5
    assert post.metric_snapshots[-1].conversions == 2
    assert post.provider_publication_id == "video"
