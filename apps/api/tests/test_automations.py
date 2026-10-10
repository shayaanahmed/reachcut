from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from clipper.domain.editing_plan import EditingPlanV1
from clipper.persistence import Base, Clip, Project, SocialAccount, now_utc
from clipper.projects import AutomationCreate, AutomationService, PublicationService
from clipper.publishing import OAuthConnection, PublishedPost, PublishRequest


class FakeCredentials:
    def load(self, account_id: str) -> OAuthConnection | None:
        return OAuthConnection(access_token=f"token-{account_id}")

    def save(self, account_id: str, connection: OAuthConnection) -> None:
        raise AssertionError("credentials should not change")

    def delete(self, account_id: str) -> None:
        raise AssertionError("credentials should not be deleted")


class FakePublisher:
    def __init__(self) -> None:
        self.requests: list[PublishRequest] = []

    def publish(self, request: PublishRequest, connection: OAuthConnection) -> PublishedPost:
        self.requests.append(request)
        return PublishedPost(post_url="https://example.com/published")

    def refresh(
        self,
        external_id: str,
        connection: OAuthConnection,
        account_username: str,
    ) -> PublishedPost:
        raise AssertionError("refresh is not used")


def test_best_clip_pipeline_publishes_only_highest_score(
    make_plan: Callable[..., EditingPlanV1],
    tmp_path: Path,
) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    service = AutomationService()
    publisher = FakePublisher()

    with Session(engine) as session:
        project = Project(
            id="project-1",
            title="Interview",
            original_filename="source.mp4",
            source_path=str(tmp_path / "source.mp4"),
            media_sha256="a" * 64,
            authorization_confirmed_at=now_utc(),
            status="review",
        )
        account = SocialAccount(
            id="account-1",
            platform="youtube",
            label="Channel",
            connection_status="connected",
        )
        session.add_all(
            [
                project,
                account,
                Clip(
                    id="clip-low",
                    project=project,
                    plan=make_plan(score=55).model_dump(mode="json"),
                    approval_status="approved",
                    final_path=str(tmp_path / "low.mp4"),
                ),
                Clip(
                    id="clip-high",
                    project=project,
                    plan=make_plan(score=94).model_dump(mode="json"),
                    approval_status="approved",
                    final_path=str(tmp_path / "high.mp4"),
                ),
            ]
        )
        session.commit()
        pipeline = service.create(
            session,
            AutomationCreate(
                name="Best only",
                project_id=project.id,
                social_account_ids=(account.id,),
                clip_selection="best",
                clip_types=(),
                schedule="once",
                next_run_at=now_utc() - timedelta(minutes=1),
            ),
        )

        completed = service.execute_due(
            session,
            object(),  # type: ignore[arg-type]
            PublicationService(),
            {"youtube": publisher},
            FakeCredentials(),
        )

        session.refresh(pipeline)
        assert completed == [pipeline.id]
        assert pipeline.status == "completed"
        assert len(publisher.requests) == 1
        assert publisher.requests[0].media_path.name == "high.mp4"

        paused = service.set_active(session, pipeline.id, active=False)
        assert paused.status == "paused"
        assert (
            service.execute_due(
                session,
                object(),  # type: ignore[arg-type]
                PublicationService(),
                {"youtube": publisher},
                FakeCredentials(),
                pipeline_id=pipeline.id,
            )
            == []
        )

        reactivated = service.set_active(session, pipeline.id, active=True)
        assert reactivated.status == "active"
