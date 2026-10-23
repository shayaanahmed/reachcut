import json
from unittest.mock import Mock

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from test_publications import (
    FakeCredentials as BaseCredentials,
)
from test_publications import (
    add_project_with_clip,
    publication_request,
)

from clipper.persistence import Base, Publication, SocialAccount
from clipper.persistence.models import AccountIssue, PostManagement, PublicationDestination
from clipper.projects import (
    AutomaticPublicationCreate,
    MetricCreate,
    PublicationService,
    PublicationStateError,
)
from clipper.projects.post_management import capabilities, manage_post
from clipper.providers.meta import FacebookPublishingAdapter, InstagramPublishingAdapter
from clipper.providers.youtube import (
    YouTubeOAuthClient,
    YouTubePublishingAdapter,
)
from clipper.publishing import OAuthConnection


class FakeCredentials(BaseCredentials):
    def load(self, account_id):
        from dataclasses import replace

        return replace(
            super().load(account_id),
            granted_scopes=("https://www.googleapis.com/auth/youtube.force-ssl",),
        )


@pytest.fixture
def post_session(make_plan):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        clip = add_project_with_clip(session, make_plan)
        session.add(
            SocialAccount(
                id="account-1", platform="youtube", label="Channel", connection_status="connected"
            )
        )
        session.commit()
        service = PublicationService()
        service.create(session, clip.id, publication_request("account-1"))
        post = clip.publications[0]
        service.record_metrics(session, post.id, MetricCreate(views=200, likes=12))
        yield session, post, service
    engine.dispose()


class Manager:
    def __init__(self):
        self.calls = []
        self.error = None

    def update_post(self, external_id, post_url, title, description, connection):
        self.calls.append(("update", external_id, post_url, title, description))
        if self.error:
            raise self.error

    def delete_post(self, external_id, post_url, connection):
        self.calls.append(("delete", external_id, post_url))
        if self.error:
            raise self.error


def test_edit_delete_preserve_original_identity_and_metrics(post_session):
    session, post, service = post_session
    original_id, url = post.id, post.post_url
    manager = Manager()
    manage_post(
        session,
        post.id,
        "update",
        {"youtube": manager},
        FakeCredentials(),
        title="New useful title",
        description="Updated caption",
    )
    session.refresh(post)
    assert (post.id, post.post_url) == (original_id, url)
    assert len(post.clip.publications) == 1
    assert post.title == "New useful title"
    assert [metric.views for metric in post.metric_snapshots] == [200]
    assert post.changes[0].before["title"] == "A useful clip"
    assert post.changes[0].after["description"] == "Updated caption"
    manage_post(session, post.id, "delete", {"youtube": manager}, FakeCredentials())
    session.refresh(post)
    assert post.status == "deleted"
    assert len(post.changes) == 2
    assert post.metric_snapshots[0].views == 200
    assert session.get(Publication, original_id) is post
    assert [call[0] for call in manager.calls] == ["update", "delete"]
    assert session.get(PublicationDestination, original_id) is None


def test_failed_action_retains_copy_and_survives_account_page_reload(post_session):
    session, post, service = post_session
    manager = Manager()
    manager.error = ValueError("Permission expired; reconnect account")
    with pytest.raises(ValueError, match="Permission expired"):
        manage_post(
            session,
            post.id,
            "update",
            {"youtube": manager},
            FakeCredentials(),
            title="New",
            description="Changed",
        )
    session.expire_all()
    assert post.title == "A useful clip"
    assert post.status == "published"
    assert post.changes == []
    assert post.management.state == "failed"
    assert "reconnect" in session.get(AccountIssue, "account-1").message
    assert "reconnect" in session.get(SocialAccount, "account-1").health_issue
    manager.error = None
    manage_post(
        session,
        post.id,
        "update",
        {"youtube": manager},
        FakeCredentials(),
        title="New",
        description="Changed",
    )
    assert post.management.state == "succeeded"
    assert session.get(AccountIssue, "account-1") is None


def test_overlapping_platform_actions_and_local_removal_are_rejected(post_session):
    session, post, service = post_session
    manager = Manager()
    session.add(PostManagement(publication_id=post.id, state="working", action="update"))
    session.commit()
    with pytest.raises(PublicationStateError, match="in progress"):
        manage_post(session, post.id, "delete", {"youtube": manager}, FakeCredentials())
    with pytest.raises(PublicationStateError, match="Wait"):
        service.delete(session, post.id)
    assert not manager.calls
    assert session.get(Publication, post.id)


def test_new_post_requires_explicit_opt_in_and_keeps_original(post_session):
    session, original, service = post_session
    request = AutomaticPublicationCreate("account-1", "Separate post", "Caption")
    with pytest.raises(PublicationStateError, match="already queued or published"):
        service.queue_many(session, original.clip_id, [request], FakeCredentials())
    _, queued = service.queue_many(
        session, original.clip_id, [request], FakeCredentials(), allow_new=True
    )
    session.expire_all()
    assert original.status == "published"
    assert len(original.metric_snapshots) == 1
    assert len(original.clip.publications) == 2
    assert queued[0][0] != original.id
    with pytest.raises(PublicationStateError):
        service.queue_many(session, original.clip_id, [request], FakeCredentials(), allow_new=True)


def test_local_remove_never_calls_provider(post_session):
    session, post, service = post_session
    id = post.id
    service.delete(session, id)
    assert session.get(Publication, id) is None
    assert session.get(PostManagement, id) is None


def test_youtube_update_preserves_snippet_fields_and_does_not_upload():
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.path == "/youtube/v3/videos"
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "original",
                            "snippet": {
                                "title": "Old",
                                "description": "Old",
                                "categoryId": "27",
                                "tags": ["education"],
                                "defaultLanguage": "en",
                                "channelId": "owner",
                            },
                        }
                    ]
                },
            )
        if request.method == "PUT":
            body = json.loads(request.content)
            assert body == {
                "id": "original",
                "snippet": {
                    "title": "New",
                    "description": "Caption",
                    "categoryId": "27",
                    "tags": ["education"],
                    "defaultLanguage": "en",
                },
            }
            assert request.url.params["part"] == "snippet"
            return httpx.Response(200, json={"id": "original"})
        assert request.method == "DELETE"
        assert request.url.params["id"] == "original"
        return httpx.Response(204)

    oauth = Mock(spec=YouTubeOAuthClient)
    oauth.access_token.return_value = "access"
    adapter = YouTubePublishingAdapter(
        oauth, client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    connection = OAuthConnection("refresh")
    adapter.update_post("original", None, "New", "Caption", connection)
    adapter.delete_post("original", None, connection)
    assert [call.method for call in calls] == ["GET", "PUT", "DELETE"]


def test_facebook_verifies_caption_and_instagram_does_not_offer_caption_editing():
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.path.endswith("/123456")
        if request.method == "POST":
            assert request.content == b"description=New+caption"
            return httpx.Response(200, json={"success": True})
        return httpx.Response(200, json={"description": "New caption"})

    adapter = FacebookPublishingAdapter(
        "v23.0", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    adapter.update_post(
        "123456",
        None,
        "Title",
        "New caption",
        OAuthConnection(
            "refresh",
            access_token="token",  # noqa: S106 - synthetic token
            external_account_id="page",
        ),
    )
    assert len(calls) == 2
    instagram = InstagramPublishingAdapter("v23.0")
    assert capabilities(instagram, "instagram")["update"] is False


@pytest.fixture
def management_client(post_session, monkeypatch):
    from fastapi.testclient import TestClient

    from clipper.api import publications as routes
    from clipper.main import app
    from clipper.persistence import get_session

    session, post, service = post_session
    engine = session.get_bind()

    def override():
        with Session(engine) as request_session:
            yield request_session

    app.dependency_overrides[get_session] = override
    monkeypatch.setattr(routes, "publishing_adapters", {"youtube": Manager()})
    monkeypatch.setattr(routes, "credential_store", FakeCredentials())
    monkeypatch.setattr(routes, "run_publication_batch", lambda queued: None)
    try:
        with TestClient(app) as client:
            yield client, post.id
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_remote_endpoints_confirm_actions_and_keep_history(management_client):
    client, id = management_client
    assert client.get("/api/publications/missing/management").status_code == 404
    response = client.put(
        f"/api/publications/{id}/remote", json={"title": "Improved", "description": "New copy"}
    )
    assert response.status_code == 200
    posts = response.json()["clips"][0]["publications"]
    assert len(posts) == 1 and posts[0]["id"] == id
    assert posts[0]["title"] == "Improved"
    assert posts[0]["metric_snapshots"][0]["views"] == 200
    assert (
        client.post(f"/api/publications/{id}/delete-remote", json={"confirm": False}).status_code
        == 422
    )
    assert (
        client.post(f"/api/publications/{id}/delete-remote", json={"confirm": True}).status_code
        == 200
    )
    details = client.get(f"/api/publications/{id}/management").json()
    assert details["operation"]["state"] == "succeeded"
    assert [entry["action"] for entry in details["history"]] == ["delete", "update"]


def test_explicit_new_post_endpoint_retains_original(management_client):
    client, id = management_client
    assert (
        client.post(f"/api/publications/{id}/publish-new", json={"confirm": False}).status_code
        == 422
    )
    response = client.post(f"/api/publications/{id}/publish-new", json={"confirm": True})
    assert response.status_code == 202
    posts = response.json()["clips"][0]["publications"]
    assert len(posts) == 2
    assert next(post for post in posts if post["id"] == id)["status"] == "published"
    assert (
        client.get(f"/api/publications/{id}/management").json()["history"][0]["action"]
        == "publish_new"
    )


def test_pending_pipeline_cannot_publish_or_update_old_copy(post_session):
    session, post, service = post_session
    post.clip.project.status = "processing"
    session.commit()
    manager = Manager()
    with pytest.raises(PublicationStateError, match="pipeline to finish"):
        manage_post(
            session,
            post.id,
            "update",
            {"youtube": manager},
            FakeCredentials(),
            title="Old",
            description="Old",
        )
    with pytest.raises(PublicationStateError, match="pipeline to finish"):
        service.queue_many(
            session,
            post.clip_id,
            [AutomaticPublicationCreate("account-1", "Old", "Old")],
            FakeCredentials(),
            allow_new=True,
        )
    assert manager.calls == []


def test_missing_youtube_management_scope_is_actionable_and_never_calls_provider(post_session):
    session, post, service = post_session
    manager = Manager()
    with pytest.raises(PublicationStateError, match="Reconnect this channel"):
        manage_post(
            session,
            post.id,
            "update",
            {"youtube": manager},
            BaseCredentials(),
            title="Latest",
            description="Draft",
        )
    assert manager.calls == []
    assert post.title == "A useful clip"
    assert session.get(AccountIssue, "account-1")


def test_latest_draft_restores_metadata_tags_without_duplicates(post_session, tmp_path):
    from clipper.projects.post_management import clip_copy
    from clipper.projects.stages import StageRunner

    session, post, service = post_session
    clip = post.clip
    clip.project.source_path = str(tmp_path / "source" / "video.mp4")
    clip.plan = {
        **clip.plan,
        "suggested_title": "Latest source title",
        "suggested_description": "Useful Github tool #Github",
        "hashtags": [],
    }
    artifact = StageRunner.artifact_path(clip.project, "generate_metadata")
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps([{"clip_id": clip.id, "hashtags": ["#Github", "#JobSearch"]}]))
    title, description = clip_copy(session, clip, "youtube")
    assert title == "Latest source title"
    assert description.count("#Github") == 1
    assert "#JobSearch" in description


def test_missing_instagram_delete_authorization_blocks_remote_call_and_preserves_post(post_session):
    from clipper.projects.post_management import deletion_issue

    session, post, service = post_session
    post.platform = "instagram"
    from clipper.persistence.models import PublicationProviderReference

    post.provider_reference = PublicationProviderReference(external_id="original-instagram-media")
    account = session.get(SocialAccount, "account-1")
    account.platform = "instagram"
    session.commit()
    manager = Manager()
    assert "instagram_manage_contents" in deletion_issue(session, post, FakeCredentials())
    with pytest.raises(PublicationStateError, match="instagram_manage_contents"):
        manage_post(session, post.id, "delete", {"instagram": manager}, FakeCredentials())
    assert not manager.calls
    assert post.status == "published"
    assert post.metric_snapshots[0].views == 200


def test_management_api_disables_instagram_deletion_before_calling_provider(
    management_client, post_session, monkeypatch
):
    from clipper.api import publications as routes
    from clipper.persistence.models import PublicationProviderReference

    client, id = management_client
    session, post, service = post_session
    post.platform = "instagram"
    post.provider_reference = PublicationProviderReference(external_id="original-instagram-media")
    session.get(SocialAccount, "account-1").platform = "instagram"
    session.commit()
    manager = Manager()
    monkeypatch.setattr(routes, "publishing_adapters", {"instagram": manager})
    details = client.get(f"/api/publications/{id}/management").json()
    assert details["capabilities"]["delete"] is False
    assert details["capabilities"]["deletion_reconnect_required"] is True
    assert "instagram_manage_contents" in details["capabilities"]["deletion_issue"]
    response = client.post(f"/api/publications/{id}/delete-remote", json={"confirm": True})
    assert response.status_code == 409
    assert not manager.calls
    session.refresh(post)
    assert post.status == "published" and post.metric_snapshots[0].views == 200
