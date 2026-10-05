from collections.abc import Callable, Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from clipper.domain.editing_plan import EditingPlanV1
from clipper.main import app
from clipper.persistence import Base, Clip, Project, SocialAccount, get_session, now_utc
from clipper.projects import (
    AutomaticPublicationCreate,
    MetricCreate,
    PublicationCreate,
    PublicationService,
    PublicationStateError,
)
from clipper.publishing import OAuthConnection, ProviderMetrics, PublishedPost, PublishRequest


class FakeCredentials:
    def load(self, account_id: str) -> OAuthConnection | None:
        return OAuthConnection(f"opaque-value-for-{account_id}")

    def save(self, account_id: str, connection: OAuthConnection) -> None:
        raise AssertionError("publishing must not replace credentials")

    def delete(self, account_id: str) -> None:
        raise AssertionError("publishing must not delete credentials")


class FakePublisher:
    def __init__(self) -> None:
        self.request: PublishRequest | None = None

    def publish(self, request: PublishRequest, connection: OAuthConnection) -> PublishedPost:
        self.request = request
        assert connection.refresh_token.endswith("account-1")
        return PublishedPost(post_url="https://www.youtube.com/shorts/video-123")

    def refresh(
        self,
        external_id: str,
        connection: OAuthConnection,
        account_username: str,
    ) -> PublishedPost:
        raise AssertionError("completed publications do not need a refresh")


class FakeProcessingPublisher(FakePublisher):
    def publish(self, request: PublishRequest, connection: OAuthConnection) -> PublishedPost:
        return PublishedPost(post_url=None, external_id="pending-1", status="processing")

    def refresh(
        self,
        external_id: str,
        connection: OAuthConnection,
        account_username: str,
    ) -> PublishedPost:
        assert external_id == "pending-1"
        return PublishedPost(
            post_url=f"https://www.tiktok.com/@{account_username}/video/final-1",
            external_id="final-1",
        )


class FakeMetricsAdapter:
    def metrics(
        self,
        external_id: str | None,
        post_url: str | None,
        connection: OAuthConnection,
    ) -> ProviderMetrics:
        assert external_id is None
        assert post_url == "https://youtube.com/shorts/example"
        assert connection.refresh_token.endswith("account-1")
        return ProviderMetrics(
            external_id="example",
            views=275,
            likes=18,
            comments=3,
        )


def add_project_with_clip(
    session: Session,
    make_plan: Callable[..., EditingPlanV1],
    *,
    rendered: bool = True,
) -> Clip:
    project = Project(
        id="project-1",
        title="Tracked project",
        original_filename="source.mp4",
        source_path="/data/project-1/source/source.mp4",
        media_sha256="a" * 64,
        authorization_confirmed_at=now_utc(),
    )
    clip = Clip(
        id="clip-1",
        project=project,
        plan=make_plan().model_dump(mode="json"),
        approval_status="approved",
        final_path="/data/project-1/clips/clip-1/final.mp4" if rendered else None,
    )
    session.add_all([project, clip])
    session.commit()
    return clip


def publication_request(account_id: str | None = None) -> PublicationCreate:
    return PublicationCreate(
        platform="youtube",
        status="published",
        post_url="https://youtube.com/shorts/example",
        title="A useful clip",
        description="#UsefulTips",
        published_at=None,
        social_account_id=account_id,
    )


def test_publication_metrics_preserve_snapshot_history(
    make_plan: Callable[..., EditingPlanV1],
) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    service = PublicationService()

    with Session(engine) as session:
        clip = add_project_with_clip(session, make_plan)
        assert service.create(session, clip.id, publication_request()) == "project-1"
        publication = clip.publications[0]

        service.record_metrics(
            session,
            publication.id,
            MetricCreate(views=100, likes=10, revenue=2.5),
        )
        service.record_metrics(
            session,
            publication.id,
            MetricCreate(views=250, likes=22, revenue=6.0),
        )
        session.refresh(publication)

        assert [item.views for item in publication.metric_snapshots] == [100, 250]
        assert publication.metric_snapshots[-1].revenue == 6.0


def test_provider_metrics_sync_backfills_video_id_and_preserves_manual_business_metrics(
    make_plan: Callable[..., EditingPlanV1],
) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    service = PublicationService()

    with Session(engine) as session:
        clip = add_project_with_clip(session, make_plan)
        session.add(
            SocialAccount(
                id="account-1",
                platform="youtube",
                label="Main channel",
                connection_status="connected",
            )
        )
        session.commit()
        service.create(session, clip.id, publication_request("account-1"))
        publication = clip.publications[0]
        service.record_metrics(
            session,
            publication.id,
            MetricCreate(
                views=10,
                likes=1,
                shares=4,
                affiliate_clicks=2,
                revenue=7.5,
                currency="EUR",
            ),
        )

        project_id = service.sync_metrics(
            session,
            publication.id,
            {"youtube": FakeMetricsAdapter()},
            FakeCredentials(),
        )
        session.refresh(publication)

        assert project_id == "project-1"
        assert publication.provider_publication_id == "example"
        latest = publication.metric_snapshots[-1]
        assert (latest.views, latest.likes, latest.comments) == (275, 18, 3)
        assert latest.shares == 4
        assert latest.affiliate_clicks == 2
        assert latest.revenue == 7.5


def test_publication_requires_an_approved_final_render(
    make_plan: Callable[..., EditingPlanV1],
) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        clip = add_project_with_clip(session, make_plan, rendered=False)
        try:
            PublicationService().create(session, clip.id, publication_request())
        except PublicationStateError as error:
            assert "approved and rendered" in str(error)
        else:
            raise AssertionError("unrendered clip was accepted for publishing")


def test_automatic_publication_uploads_and_records_returned_url(
    make_plan: Callable[..., EditingPlanV1],
) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    publisher = FakePublisher()

    with Session(engine) as session:
        clip = add_project_with_clip(session, make_plan)
        session.add(
            SocialAccount(
                id="account-1",
                platform="youtube",
                label="Main channel",
                connection_status="connected",
                is_default=True,
            )
        )
        session.commit()

        project_id = PublicationService().publish(
            session,
            clip.id,
            AutomaticPublicationCreate(
                social_account_id="account-1",
                title="A useful clip",
                description="#UsefulTips",
                privacy_status="unlisted",
            ),
            publisher,
            FakeCredentials(),
        )

        assert project_id == "project-1"
        assert clip.publications[0].post_url == "https://www.youtube.com/shorts/video-123"
        assert clip.publications[0].social_account_id == "account-1"
        assert publisher.request is not None
        assert publisher.request.privacy_status == "unlisted"


def test_processing_publication_preserves_provider_id_until_url_is_ready(
    make_plan: Callable[..., EditingPlanV1],
) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    publisher = FakeProcessingPublisher()

    with Session(engine) as session:
        clip = add_project_with_clip(session, make_plan)
        session.add(
            SocialAccount(
                id="account-1",
                platform="tiktok",
                label="Main TikTok",
                username="creator",
                connection_status="connected",
                is_default=True,
            )
        )
        session.commit()

        PublicationService().publish(
            session,
            clip.id,
            AutomaticPublicationCreate(
                social_account_id="account-1",
                title="A useful clip",
                description="#UsefulTips",
            ),
            publisher,
            FakeCredentials(),
        )
        publication = clip.publications[0]
        assert publication.status == "processing"
        assert publication.provider_publication_id == "pending-1"

        PublicationService().refresh_publication(
            session,
            publication.id,
            {"tiktok": publisher},
            FakeCredentials(),
        )

        assert publication.status == "published"
        assert publication.post_url == "https://www.tiktok.com/@creator/video/final-1"
        assert publication.provider_publication_id == "final-1"


def test_publication_routes_return_project_performance_data(
    make_plan: Callable[..., EditingPlanV1],
) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        add_project_with_clip(session, make_plan)
        account = SocialAccount(
            id="account-1",
            platform="youtube",
            label="Main channel",
            username="creator",
            is_default=True,
        )
        session.add(account)
        session.commit()

    def session_override() -> Generator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/clips/clip-1/publications",
                json={
                    "platform": "youtube",
                    "social_account_id": "account-1",
                    "post_url": "https://youtube.com/shorts/example",
                    "title": "A useful clip",
                    "description": "#UsefulTips",
                },
            )
            assert created.status_code == 200
            publication = created.json()["clips"][0]["publications"][0]
            assert publication["platform"] == "youtube"
            assert publication["social_account_id"] == "account-1"
            assert publication["account_label"] == "Main channel"

            measured = client.post(
                f"/api/publications/{publication['id']}/metrics",
                json={"views": 1250, "likes": 125, "revenue": 14.5, "currency": "EUR"},
            )
            assert measured.status_code == 200
            snapshots = measured.json()["clips"][0]["publications"][0]["metric_snapshots"]
            assert snapshots[-1]["views"] == 1250
            assert snapshots[-1]["revenue"] == 14.5
    finally:
        app.dependency_overrides.clear()
