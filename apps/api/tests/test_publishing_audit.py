"""Regression checks for account isolation and publishing failure boundaries."""

from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from test_distribution import Credentials, distribution

from clipper.main import app
from clipper.persistence import Base, Publication, SocialAccount, get_session
from clipper.persistence.models import PublicationProviderReference, SocialAccountIdentity
from clipper.projects import PublishingConnectionService
from clipper.projects.distribution import queue_project_publications
from clipper.projects.publications import (
    AutomaticPublicationCreate,
    PublicationService,
    PublicationStateError,
)
from clipper.providers.credentials import EncryptedCredentialStore
from clipper.providers.publishing_http import ProviderAuthenticationError
from clipper.publishing import OAuthConnection, PublishedPost

__all__ = ["distribution"]


@pytest.mark.parametrize(
    ("platform", "visibility"),
    [
        ("instagram", "private"),
        ("facebook", "private"),
        ("x", "private"),
        ("youtube", "friends"),
        ("tiktok", "unlisted"),
    ],
)
def test_unsupported_visibility_cannot_be_queued(
    distribution, platform: str, visibility: str
) -> None:
    session, project, accounts = distribution
    accounts[0].platform = platform
    session.commit()
    with pytest.raises(PublicationStateError, match="visibility"):
        PublicationService().queue_many(
            session,
            project.clips[0].id,
            [AutomaticPublicationCreate(accounts[0].id, "Title", "Caption", visibility)],
            Credentials(),
        )
    assert list(session.scalars(select(Publication))) == []


def test_uncommitted_queue_remains_part_of_the_callers_transaction(distribution) -> None:
    session, project, accounts = distribution
    PublicationService().queue_many(
        session,
        project.clips[0].id,
        [AutomaticPublicationCreate(accounts[0].id, "Title", "Caption")],
        Credentials(),
        commit=False,
    )
    session.rollback()
    assert list(session.scalars(select(Publication))) == []


def test_failed_token_renewal_is_retryable_without_an_uncertain_upload(distribution) -> None:
    session, project, accounts = distribution

    class ExpiredPublisher:
        def refresh_connection(self, connection: OAuthConnection) -> OAuthConnection:
            raise ProviderAuthenticationError("Authorization expired; reconnect")

        def publish(self, *args: object) -> None:
            pytest.fail("No upload may be sent after token renewal fails")

    with pytest.raises(ProviderAuthenticationError):
        PublicationService().publish(
            session,
            project.clips[0].id,
            AutomaticPublicationCreate(accounts[0].id, "Title", "Caption"),
            ExpiredPublisher(),
            Credentials(),
        )
    post = session.scalar(select(Publication))
    assert post.status == "failed"
    assert accounts[0].connection_status == "disconnected"


def test_completed_upload_cannot_restore_disconnected_credentials(
    distribution, tmp_path: Path
) -> None:
    session, project, accounts = distribution
    credentials = EncryptedCredentialStore(tmp_path)
    connection = OAuthConnection(external_account_id="intended")
    credentials.save(accounts[0].id, connection)

    class Publisher:
        def publish(self, *args: object) -> PublishedPost:
            credentials.delete(accounts[0].id)
            accounts[0].connection_status = "disconnected"
            session.commit()
            return PublishedPost(
                post_url="https://example.com/completed-post",
                updated_connection=connection,
            )

    PublicationService().publish(
        session,
        project.clips[0].id,
        AutomaticPublicationCreate(accounts[0].id, "Title", "Caption"),
        Publisher(),
        credentials,
    )
    assert session.scalar(select(Publication)).status == "published"
    assert credentials.load(accounts[0].id) is None


def test_completed_upload_does_not_overwrite_a_newer_reconnection(
    distribution, tmp_path: Path
) -> None:
    session, project, accounts = distribution
    credentials = EncryptedCredentialStore(tmp_path)
    original = OAuthConnection(external_account_id="intended")
    reconnected = replace(original, refresh_token="new authorization")  # noqa: S106
    credentials.save(accounts[0].id, original)

    class Publisher:
        def publish(self, *args: object) -> PublishedPost:
            credentials.save(accounts[0].id, reconnected)
            return PublishedPost(
                post_url="https://example.com/completed-post", updated_connection=original
            )

    PublicationService().publish(
        session,
        project.clips[0].id,
        AutomaticPublicationCreate(accounts[0].id, "Title", "Caption"),
        Publisher(),
        credentials,
    )
    assert credentials.load(accounts[0].id) == reconnected


@pytest.mark.parametrize("result_kind", ["deleted_during_refresh", "missing_url"])
def test_status_refresh_preserves_concurrent_deletion_and_requires_a_post_url(
    distribution, result_kind: str
) -> None:
    session, project, accounts = distribution
    service = PublicationService()
    _, queued = service.queue_many(
        session,
        project.clips[0].id,
        [AutomaticPublicationCreate(accounts[0].id, "Title", "Caption")],
        Credentials(),
    )
    post = session.get(Publication, queued[0][0])
    post.status = "processing"
    post.provider_reference = PublicationProviderReference(external_id="original-video")
    session.commit()

    class Refresher:
        def refresh(self, *args: object) -> PublishedPost:
            if result_kind == "deleted_during_refresh":
                post.status = "deleted"
                session.commit()
            return PublishedPost(
                post_url="https://example.com/video" if result_kind != "missing_url" else None
            )

    with pytest.raises(PublicationStateError):
        service.refresh_publication(session, post.id, {"youtube": Refresher()}, Credentials())
    assert post.status == ("deleted" if result_kind == "deleted_during_refresh" else "processing")


def test_rejected_batch_cannot_leave_a_partial_upload_queued(distribution) -> None:
    session, project, accounts = distribution
    with pytest.raises(PublicationStateError, match="connect"):
        PublicationService().queue_many(
            session,
            project.clips[0].id,
            [
                AutomaticPublicationCreate(a.id, "Title", "Caption")
                for a in (accounts[0], accounts[2])
            ],
            Credentials(),
        )
    # A caller's later commit must not dispatch the rejected request's first account.
    session.commit()
    assert list(session.scalars(select(Publication))) == []


@pytest.mark.parametrize("restriction", ["permission", "uncertain", "deferred"])
def test_bulk_publish_keeps_healthy_destinations_when_one_is_restricted(
    distribution, restriction: str
) -> None:
    session, project, accounts = distribution
    service = PublicationService()

    class RestrictedCredentials(Credentials):
        def load(self, account_id: str) -> OAuthConnection:
            return OAuthConnection(
                access_token="fixture",  # noqa: S106
                external_account_id=account_id,
                granted_scopes=()
                if restriction == "permission" and account_id == accounts[1].id
                else None,
            )

    if restriction != "permission":
        _, queued = service.queue_many(
            session,
            project.clips[0].id,
            [AutomaticPublicationCreate(accounts[1].id, "Title", "Caption")],
            Credentials(),
        )
        session.get(Publication, queued[0][0]).status = restriction
        session.commit()
    queued, skipped = queue_project_publications(
        session,
        project.id,
        None,
        [a.id for a in accounts[:2]],
        None,
        None,
        RestrictedCredentials(),
        service,
    )
    assert sum(request.social_account_id == accounts[0].id for _, request in queued) == 3
    assert any(item.account_id == accounts[1].id for item in skipped)
    session.expire_all()
    assert sum(post.platform == "youtube" for post in session.scalars(select(Publication))) == 3


@pytest.mark.parametrize("platform", ["youtube", "tiktok", "x"])
def test_all_bound_platforms_reject_credentials_for_another_destination(
    distribution, platform: str
) -> None:
    session, _, accounts = distribution
    account = accounts[0]
    account.platform = platform
    account.identity = SocialAccountIdentity(platform=platform, external_account_id="intended")
    session.commit()
    with pytest.raises(PublicationStateError, match="different destination"):
        PublicationService._check_destination(
            session, account, OAuthConnection(external_account_id="other")
        )


@pytest.mark.parametrize("state", ["deleted", "failed", "published"])
def test_terminal_posts_cannot_be_reopened_by_status_refresh(distribution, state: str) -> None:
    session, project, accounts = distribution
    service = PublicationService()
    _, queued = service.queue_many(
        session,
        project.clips[0].id,
        [AutomaticPublicationCreate(accounts[0].id, "Title", "Caption")],
        Credentials(),
    )
    post = session.get(Publication, queued[0][0])
    post.status = state
    post.provider_reference = PublicationProviderReference(external_id="original-video")
    session.commit()

    class Refresher:
        def refresh(self, *args: object) -> PublishedPost:
            pytest.fail("Terminal posts must not call the provider")

    with pytest.raises(PublicationStateError):
        service.refresh_publication(session, post.id, {"youtube": Refresher()}, Credentials())
    assert post.status == state


def test_status_refresh_rejects_disconnected_accounts(distribution) -> None:
    session, project, accounts = distribution
    service = PublicationService()
    _, queued = service.queue_many(
        session,
        project.clips[0].id,
        [AutomaticPublicationCreate(accounts[0].id, "Title", "Caption")],
        Credentials(),
    )
    post = session.get(Publication, queued[0][0])
    post.status = "processing"
    post.provider_reference = PublicationProviderReference(external_id="original-video")
    accounts[0].connection_status = "disconnected"
    session.commit()

    class Refresher:
        def refresh(self, *args: object) -> PublishedPost:
            pytest.fail("Disconnected accounts must not call the provider")

    with pytest.raises(PublicationStateError, match="connect"):
        service.refresh_publication(session, post.id, {"youtube": Refresher()}, Credentials())


def test_corrupted_tokens_can_still_be_disconnected(tmp_path: Path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    credentials = EncryptedCredentialStore(tmp_path)
    credentials.save("account", OAuthConnection(external_account_id="intended"))
    (tmp_path / "credentials/account.token").write_text("damaged encrypted data")
    with Session(engine) as session:
        account = SocialAccount(
            id="account", platform="youtube", label="Channel", connection_status="connected"
        )
        account.identity = SocialAccountIdentity(platform="youtube", external_account_id="intended")
        session.add(account)
        session.commit()
        PublishingConnectionService({}, credentials).disconnect(session, account.id)
        assert account.connection_status == "disconnected"
        assert account.external_account_id == "intended"
        assert credentials.load(account.id) is None


def test_disconnect_waits_for_token_rotation_then_removes_rotated_credentials(
    tmp_path: Path,
) -> None:
    credentials = EncryptedCredentialStore(tmp_path)
    credentials.save("account", OAuthConnection(external_account_id="intended"))
    rotating, release, deleting = Event(), Event(), Event()

    def renew(connection: OAuthConnection) -> OAuthConnection:
        rotating.set()
        assert release.wait(5)
        return replace(connection, access_token="rotated")  # noqa: S106 - synthetic token

    def disconnect() -> None:
        deleting.set()
        credentials.delete("account")

    with ThreadPoolExecutor(max_workers=2) as pool:
        refresh = pool.submit(credentials.refresh, "account", renew)
        assert rotating.wait(5)
        removed = pool.submit(disconnect)
        assert deleting.wait(5)
        # Let deletion finish if it is incorrectly unprotected by the rotation lock.
        try:
            removed.result(timeout=0.1)
        except TimeoutError:
            pass
        finally:
            release.set()
        refresh.result(timeout=5)
        removed.result(timeout=5)
    assert credentials.load("account") is None


def test_account_api_rejects_blank_labels(distribution) -> None:
    session, _, accounts = distribution

    def override() -> Generator[Session]:
        yield session

    app.dependency_overrides[get_session] = override
    try:
        with TestClient(app) as client:
            response = client.put(f"/api/social-accounts/{accounts[0].id}", json={"label": " \t "})
        assert response.status_code == 422
        session.refresh(accounts[0])
        assert accounts[0].label == "Religious YT"
    finally:
        app.dependency_overrides.pop(get_session, None)
