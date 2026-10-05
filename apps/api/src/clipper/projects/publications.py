from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from clipper.persistence import (
    Clip,
    MetricSnapshot,
    Publication,
    PublicationAccountLink,
    PublicationProviderReference,
    SocialAccount,
    now_utc,
)
from clipper.publishing import CredentialStore, MetricsAdapter, PublishingAdapter, PublishRequest


class PublicationNotFoundError(LookupError):
    pass


class PublicationStateError(RuntimeError):
    pass


@dataclass(frozen=True)
class PublicationCreate:
    platform: str
    status: str
    post_url: str | None
    title: str
    description: str
    published_at: datetime | None
    social_account_id: str | None = None


@dataclass(frozen=True)
class MetricCreate:
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    watch_time_seconds: float | None = None
    followers_gained: int = 0
    affiliate_clicks: int = 0
    conversions: int = 0
    revenue: float = 0
    currency: str = "EUR"


@dataclass(frozen=True)
class AutomaticPublicationCreate:
    social_account_id: str
    title: str
    description: str
    privacy_status: str = "public"


class PublicationService:
    """Track where rendered clips were published and their metric history."""

    def create(
        self,
        session: Session,
        clip_id: str,
        request: PublicationCreate,
    ) -> str:
        clip = session.get(Clip, clip_id)
        if not clip:
            raise PublicationNotFoundError("clip not found")
        if clip.approval_status != "approved" or not clip.final_path:
            raise PublicationStateError("clip must be approved and rendered before publishing")
        if request.status == "published" and not request.post_url:
            raise PublicationStateError("published clips require a post URL")

        account = None
        if request.social_account_id:
            account = session.get(SocialAccount, request.social_account_id)
            if not account or not account.is_active:
                raise PublicationNotFoundError("social account not found")
            if account.platform != request.platform:
                raise PublicationStateError(
                    "publication platform must match the selected social account"
                )

        publication = Publication(
            clip_id=clip.id,
            platform=request.platform,
            status=request.status,
            post_url=request.post_url,
            title=request.title.strip(),
            description=request.description.strip(),
            published_at=(request.published_at or now_utc())
            if request.status == "published"
            else request.published_at,
        )
        session.add(publication)
        if account:
            session.flush()
            session.add(
                PublicationAccountLink(
                    publication_id=publication.id,
                    social_account_id=account.id,
                    account_label_snapshot=account.label,
                    account_username_snapshot=account.username,
                )
            )
        session.commit()
        return clip.project_id

    def publish(
        self,
        session: Session,
        clip_id: str,
        request: AutomaticPublicationCreate,
        adapter: PublishingAdapter,
        credentials: CredentialStore,
    ) -> str:
        clip = session.get(Clip, clip_id)
        if not clip:
            raise PublicationNotFoundError("clip not found")
        if clip.approval_status != "approved" or not clip.final_path:
            raise PublicationStateError("clip must be approved and rendered before publishing")
        account = session.get(SocialAccount, request.social_account_id)
        if not account or not account.is_active:
            raise PublicationNotFoundError("social account not found")
        connection = credentials.load(account.id)
        if account.connection_status != "connected" or not connection:
            raise PublicationStateError(
                f"connect this {account.platform} account before publishing"
            )

        result = adapter.publish(
            PublishRequest(
                media_path=Path(clip.final_path),
                title=request.title.strip(),
                description=request.description.strip(),
                privacy_status=request.privacy_status,
                account_username=account.username,
                duration_seconds=self._clip_duration(clip),
            ),
            connection,
        )
        if result.status == "published" and not result.post_url:
            raise PublicationStateError("publishing provider did not return a post URL")
        if result.updated_connection:
            credentials.save(account.id, result.updated_connection)
        publication = Publication(
            clip_id=clip.id,
            platform=account.platform,
            status=result.status,
            post_url=result.post_url,
            title=request.title.strip(),
            description=request.description.strip(),
            published_at=now_utc() if result.status == "published" else None,
        )
        session.add(publication)
        session.flush()
        session.add(
            PublicationAccountLink(
                publication_id=publication.id,
                social_account_id=account.id,
                account_label_snapshot=account.label,
                account_username_snapshot=account.username,
            )
        )
        if result.external_id:
            session.add(
                PublicationProviderReference(
                    publication_id=publication.id,
                    external_id=result.external_id,
                )
            )
        session.commit()
        return clip.project_id

    def refresh_publication(
        self,
        session: Session,
        publication_id: str,
        adapters: Mapping[str, PublishingAdapter],
        credentials: CredentialStore,
    ) -> str:
        publication = session.get(Publication, publication_id)
        if not publication:
            raise PublicationNotFoundError("publication not found")
        if not publication.account_link or not publication.provider_reference:
            raise PublicationStateError("publication has no provider status reference")
        adapter = adapters.get(publication.platform)
        if not adapter:
            raise PublicationStateError(
                f"automatic publishing is not configured for {publication.platform}"
            )
        connection = credentials.load(publication.account_link.social_account_id)
        if not connection:
            raise PublicationStateError("publishing account is no longer connected")
        result = adapter.refresh(
            publication.provider_reference.external_id,
            connection,
            publication.account_username or "",
        )
        if result.updated_connection:
            credentials.save(publication.account_link.social_account_id, result.updated_connection)
        publication.status = result.status
        publication.post_url = result.post_url
        if result.external_id:
            publication.provider_reference.external_id = result.external_id
        if result.status == "published":
            publication.published_at = publication.published_at or now_utc()
        session.commit()
        return publication.clip.project_id

    @staticmethod
    def _clip_duration(clip: Clip) -> float | None:
        source = clip.plan.get("source")
        if not isinstance(source, dict):
            return None
        start = source.get("start_seconds")
        end = source.get("end_seconds")
        if not isinstance(start, int | float) or not isinstance(end, int | float):
            return None
        return float(end - start)

    def record_metrics(
        self,
        session: Session,
        publication_id: str,
        request: MetricCreate,
    ) -> str:
        publication = session.get(Publication, publication_id)
        if not publication:
            raise PublicationNotFoundError("publication not found")
        if publication.status != "published":
            raise PublicationStateError("metrics require a published clip")

        session.add(
            MetricSnapshot(
                publication_id=publication.id,
                views=request.views,
                likes=request.likes,
                comments=request.comments,
                shares=request.shares,
                watch_time_seconds=request.watch_time_seconds,
                followers_gained=request.followers_gained,
                affiliate_clicks=request.affiliate_clicks,
                conversions=request.conversions,
                revenue=request.revenue,
                currency=request.currency.upper(),
            )
        )
        project_id = publication.clip.project_id
        session.commit()
        return project_id

    def sync_metrics(
        self,
        session: Session,
        publication_id: str,
        adapters: Mapping[str, MetricsAdapter],
        credentials: CredentialStore,
    ) -> str:
        publication = session.get(Publication, publication_id)
        if not publication:
            raise PublicationNotFoundError("publication not found")
        if publication.status != "published":
            raise PublicationStateError("metrics require a published clip")
        if not publication.account_link:
            raise PublicationStateError("publication is not linked to a social account")
        adapter = adapters.get(publication.platform)
        if not adapter:
            raise PublicationStateError(
                f"automatic metrics sync is not configured for {publication.platform}"
            )
        connection = credentials.load(publication.account_link.social_account_id)
        if not connection:
            raise PublicationStateError("publishing account is no longer connected")
        external_id = (
            publication.provider_reference.external_id if publication.provider_reference else None
        )
        metrics = adapter.metrics(external_id, publication.post_url, connection)
        if publication.provider_reference:
            publication.provider_reference.external_id = metrics.external_id
        else:
            session.add(
                PublicationProviderReference(
                    publication_id=publication.id,
                    external_id=metrics.external_id,
                )
            )
        previous = publication.metric_snapshots[-1] if publication.metric_snapshots else None
        session.add(
            MetricSnapshot(
                publication_id=publication.id,
                views=metrics.views,
                likes=metrics.likes,
                comments=metrics.comments,
                shares=previous.shares if previous else 0,
                watch_time_seconds=previous.watch_time_seconds if previous else None,
                followers_gained=previous.followers_gained if previous else 0,
                affiliate_clicks=previous.affiliate_clicks if previous else 0,
                conversions=previous.conversions if previous else 0,
                revenue=previous.revenue if previous else 0,
                currency=previous.currency if previous else "EUR",
            )
        )
        project_id = publication.clip.project_id
        session.commit()
        return project_id

    def delete(self, session: Session, publication_id: str) -> str:
        publication = session.get(Publication, publication_id)
        if not publication:
            raise PublicationNotFoundError("publication not found")
        project_id = publication.clip.project_id
        session.delete(publication)
        session.commit()
        return project_id
