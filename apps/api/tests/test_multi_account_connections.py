import json
from collections.abc import Generator
from dataclasses import asdict
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import clipper.api.social_accounts as routes
from clipper.main import app
from clipper.persistence import Base, SocialAccount, get_session
from clipper.persistence.models import OAuthAccountSelection
from clipper.projects.publishing_connections import (
    AccountSelectionRequired,
    PublishingConnectionError,
    PublishingConnectionService,
)
from clipper.providers.credentials import EncryptedCredentialStore
from clipper.publishing import OAuthConnection


class MultiPageClient:
    configured = True

    def __init__(self, candidates: list[OAuthConnection]) -> None:
        self.candidates = candidates

    def authorization_url(self, state: str) -> str:
        return "https://provider.example/authorize?" + urlencode({"state": state})

    def exchange_code(self, code: str, state: str = "") -> OAuthConnection:
        raise AssertionError("Must discover all destinations")

    def exchange_code_candidates(self, code: str, state: str = "") -> list[OAuthConnection]:
        return self.candidates


def connection(external_id: str, username: str) -> OAuthConnection:
    return OAuthConnection(
        access_token=f"private-token-{external_id}",
        external_account_id=external_id,
        display_name=username,
        username=username,
        parent_page_id=f"page-{external_id}",
        parent_page_name=f"Page {username}",
    )


def state(service: PublishingConnectionService, platform: str = "instagram") -> str:
    return parse_qs(urlparse(service.authorization_url_for_platform(platform)).query)["state"][0]


def test_choose_second_destination_and_keep_first_credentials_isolated(tmp_path: Path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    credentials = EncryptedCredentialStore(tmp_path)
    first, second = connection("ig-1", "first"), connection("ig-2", "second")
    client = MultiPageClient([first, second])
    service = PublishingConnectionService({"instagram": client}, credentials)
    with Session(engine) as session:
        with pytest.raises(AccountSelectionRequired) as required:
            service.complete_authorization(session, "instagram", state(service), "code")
        assert list(session.scalars(select(SocialAccount))) == []
        pending = service.pending_selection(session, required.value.selection_token)
        public = json.dumps(asdict(pending))
        assert "private-token" not in public and "access_token" not in public
        encrypted = session.scalar(select(OAuthAccountSelection))
        assert encrypted and "private-token" not in encrypted.encrypted_payload
        assert [item.external_account_id for item in pending.candidates] == ["ig-1", "ig-2"]
        selected = service.select_account(session, required.value.selection_token, "ig-2")
        assert selected.username == "second"
        assert selected.external_account_id == "ig-2"
        assert selected.parent_page_name == "Page second"
        assert credentials.load(selected.id) == second
        with pytest.raises(PublishingConnectionError, match="already used"):
            service.select_account(session, required.value.selection_token, "ig-1")
        with pytest.raises(AccountSelectionRequired) as next_selection:
            service.complete_authorization(session, "instagram", state(service), "code")
        first_account = service.select_account(
            session, next_selection.value.selection_token, "ig-1"
        )
        assert first_account.id != selected.id
        assert credentials.load(selected.id) == second
        assert credentials.load(first_account.id) == first
        assert sum(account.is_default for account in session.scalars(select(SocialAccount))) == 1


def test_reconnect_uses_bound_identity_even_after_disconnect_and_page_reordering(
    tmp_path: Path,
) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    credentials = EncryptedCredentialStore(tmp_path)
    first, second = connection("ig-1", "first"), connection("ig-2", "second")
    client = MultiPageClient([second])
    service = PublishingConnectionService({"instagram": client}, credentials)
    with Session(engine) as session:
        account = service.complete_authorization(session, "instagram", state(service), "code")
        service.disconnect(session, account.id)
        assert credentials.load(account.id) is None
        assert account.external_account_id == "ig-2"
        client.candidates = [first, second]
        reconnect_state = parse_qs(urlparse(service.authorization_url(session, account.id)).query)[
            "state"
        ][0]
        reconnected = service.complete_authorization(session, "instagram", reconnect_state, "code")
        assert reconnected.id == account.id
        assert credentials.load(account.id) == second
        assert account.username == "second"
        client.candidates = [first]
        with pytest.raises(PublishingConnectionError, match="saved connection was not changed"):
            service.complete_authorization(session, "instagram", reconnect_state, "code")
        assert credentials.load(account.id) == second


def test_unknown_choice_cannot_consume_selection_or_overwrite_accounts(tmp_path: Path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    credentials = EncryptedCredentialStore(tmp_path)
    client = MultiPageClient([connection("one", "same-name"), connection("two", "same-name")])
    service = PublishingConnectionService({"instagram": client}, credentials)
    with Session(engine) as session:
        with pytest.raises(AccountSelectionRequired) as required:
            service.complete_authorization(session, "instagram", state(service), "code")
        token = required.value.selection_token
        with pytest.raises(PublishingConnectionError, match="returned by this authorization"):
            service.select_account(session, token, "not-authorized")
        one = service.select_account(session, token, "one")
        with pytest.raises(AccountSelectionRequired) as required:
            service.complete_authorization(session, "instagram", state(service), "code")
        two = service.select_account(session, required.value.selection_token, "two")
        assert one.id != two.id
        assert credentials.load(one.id) == client.candidates[0]


def test_selection_callback_and_api_never_return_tokens(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    service = PublishingConnectionService(
        {"instagram": MultiPageClient([connection("one", "first"), connection("two", "second")])},
        EncryptedCredentialStore(tmp_path),
    )
    monkeypatch.setattr(routes, "publishing_connections", service)

    def sessions() -> Generator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    try:
        with TestClient(app) as client:
            callback = client.get(
                "/api/oauth/instagram/callback",
                params={"state": state(service), "code": "code"},
                follow_redirects=False,
            )
            assert callback.status_code == 303
            token = parse_qs(urlparse(callback.headers["location"]).query)["connection_selection"][
                0
            ]
            endpoint = f"/api/social-account-selections/{token}"
            choices = client.get(endpoint)
            assert choices.status_code == 200
            assert "private-token" not in choices.text
            assert "access_token" not in choices.text
            invalid = client.post(endpoint, json={"external_account_id": "not-authorized"})
            assert invalid.status_code == 409
            selected = client.post(endpoint, json={"external_account_id": "two"})
            assert selected.status_code == 200
            assert selected.json()["username"] == "second"
            assert selected.json()["external_account_id"] == "two"
            assert "private-token" not in selected.text
            assert client.post(endpoint, json={"external_account_id": "one"}).status_code == 409
            assert len(client.get("/api/social-accounts").json()) == 1
    finally:
        app.dependency_overrides.clear()


def test_binding_survives_archival_and_discovered_reconnect_reuses_history(tmp_path: Path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    credentials = EncryptedCredentialStore(tmp_path)
    client = MultiPageClient([connection("one", "profile")])
    service = PublishingConnectionService({"instagram": client}, credentials)
    with Session(engine) as session:
        account = service.complete_authorization(session, "instagram", state(service), "code")
        account_id = account.id
        service.disconnect(session, account_id)
        account.is_active = False
        account.is_default = False
        session.commit()
        reactivated = service.complete_authorization(session, "instagram", state(service), "code")
        assert reactivated.id == account_id
        assert reactivated.is_active and reactivated.is_default
        assert len(list(session.scalars(select(SocialAccount)))) == 1


def test_existing_binding_is_not_relearned_from_replaced_credentials(tmp_path: Path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    credentials = EncryptedCredentialStore(tmp_path)
    client = MultiPageClient([connection("one", "profile")])
    service = PublishingConnectionService({"instagram": client}, credentials)
    with Session(engine) as session:
        account = service.complete_authorization(session, "instagram", state(service), "code")
        credentials.save(account.id, connection("two", "other"))
        assert (
            "account_identity_mismatch" in service.connection_readiness(session, account.id).issues
        )
        service.backfill_identities(session)
        assert account.external_account_id == "one"
        client.candidates = [connection("two", "other"), connection("one", "profile")]
        reconnect_state = parse_qs(urlparse(service.authorization_url(session, account.id)).query)[
            "state"
        ][0]
        service.complete_authorization(session, "instagram", reconnect_state, "code")
        assert credentials.load(account.id) == connection("one", "profile")


def test_adding_another_does_not_silently_refresh_only_existing_meta_destination(
    tmp_path: Path,
) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    service = PublishingConnectionService(
        {"instagram": MultiPageClient([connection("one", "existing")])},
        EncryptedCredentialStore(tmp_path),
    )
    with Session(engine) as session:
        existing = service.complete_authorization(session, "instagram", state(service), "code")
        with pytest.raises(AccountSelectionRequired) as selection:
            service.complete_authorization(session, "instagram", state(service), "code")
        choices = service.pending_selection(session, selection.value.selection_token)
        assert len(choices.candidates) == 1
        assert choices.candidates[0].already_connected
        assert existing.external_account_id == "one"


def test_expired_selection_cannot_save_an_account(tmp_path: Path) -> None:
    import time

    from clipper.providers.credentials import CredentialStoreError

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    credentials = EncryptedCredentialStore(tmp_path)
    service = PublishingConnectionService(
        {"instagram": MultiPageClient([connection("one", "first"), connection("two", "second")])},
        credentials,
    )
    with Session(engine) as session:
        with pytest.raises(AccountSelectionRequired) as selection:
            service.complete_authorization(session, "instagram", state(service), "code")
        reference = credentials.open_state(selection.value.selection_token)
        expired = (
            credentials._cipher()
            .encrypt_at_time(reference.encode(), int(time.time()) - 601)
            .decode()
        )
        with pytest.raises(CredentialStoreError, match="expired"):
            service.select_account(session, expired, "two")
        assert list(session.scalars(select(SocialAccount))) == []
