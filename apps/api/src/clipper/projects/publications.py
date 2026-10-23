from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from sqlite3 import Connection as SQLiteConnection

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
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
from clipper.persistence.models import (
    PublicationDestination,
    PublicationFailure,
    PublicationOptions,
    SocialAccountIdentity,
)
from clipper.projects.growth import capture_growth_context
from clipper.projects.growth_automation import automatic_copy
from clipper.providers.publishing_http import (
    ProviderAuthenticationError,
    ProviderPublishingPermissionError,
    ProviderUploadRejected,
    safe_provider_error,
)
from clipper.publishing import (
    CredentialStore,
    MetricsAdapter,
    OAuthConnection,
    PublishingAdapter,
    PublishRequest,
)
from clipper.publishing.contracts import (
    ExistingCredentialStore,
    RenewingCredentialStore,
    TokenRefreshingAdapter,
)
from clipper.publishing.permissions import instagram_publishing_issue


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
    reach: int | None = None
    sends: int | None = None
    average_watch_seconds: float | None = None
    opening_retention_percent: float | None = None
    completion_rate_percent: float | None = None
    search_views: int | None = None
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

    @staticmethod
    def _check_visibility(platform: str, visibility: str) -> None:
        supported = {
            "youtube": {"public", "unlisted", "private"},
            "tiktok": {"public", "friends", "private"},
        }.get(platform, {"public"})
        if visibility not in supported:
            raise PublicationStateError(
                f"{platform} does not support {visibility} visibility through this integration"
            )

    @staticmethod
    def _save_updated_credentials(
        credentials: CredentialStore,
        account_id: str,
        connection: OAuthConnection,
        expected: OAuthConnection,
    ) -> None:
        if isinstance(credentials, ExistingCredentialStore):
            credentials.save_if_present(account_id, connection, expected)
        else:
            credentials.save(account_id, connection)

    @staticmethod
    def _refresh_credentials(
        adapter: object, credentials: CredentialStore, account_id: str, connection: OAuthConnection
    ) -> OAuthConnection:
        if not isinstance(adapter, TokenRefreshingAdapter):
            return connection
        if isinstance(credentials, RenewingCredentialStore):
            return credentials.refresh(account_id, adapter.refresh_connection)
        updated = adapter.refresh_connection(connection)
        credentials.save(account_id, updated)
        return updated

    @staticmethod
    def _check_destination(
        session: Session, account: SocialAccount, connection: OAuthConnection
    ) -> None:
        expected = account.external_account_id
        if expected and expected != connection.external_account_id:
            raise PublicationStateError(
                "Saved credentials belong to a different destination. Reconnect this account."
            )
        if connection.external_account_id:
            owner = session.scalar(
                select(SocialAccountIdentity).where(
                    SocialAccountIdentity.platform == account.platform,
                    SocialAccountIdentity.external_account_id == connection.external_account_id,
                )
            )
            if owner and owner.account_id != account.id:
                raise PublicationStateError(
                    "This destination is linked to another ReachCut account. "
                    "Reconnect the intended account."
                )

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
        capture_growth_context(session, publication, clip.id)
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
        project_id, queued = self.queue_many(session, clip_id, [request], credentials)
        publication_id, queued_request = queued[0]
        try:
            self.publish_queued(session, publication_id, queued_request, adapter, credentials)
        except Exception as error:
            session.rollback()
            self.mark_failed(session, publication_id, str(error))
            raise
        return project_id

    def queue_many(
        self,
        session: Session,
        clip_id: str,
        requests: list[AutomaticPublicationCreate],
        credentials: CredentialStore,
        *,
        commit: bool = True,
        allow_new: bool = False,
    ) -> tuple[str, list[tuple[str, AutomaticPublicationCreate]]]:
        # Roll back a rejected request without discarding other bulk destinations.
        connection = session.connection()
        driver = connection.connection.driver_connection
        # SQLite's legacy transaction mode otherwise commits the outermost
        # SAVEPOINT even when the caller requested commit=False.
        if isinstance(driver, SQLiteConnection) and not driver.in_transaction:
            connection.exec_driver_sql("BEGIN")
        with session.begin_nested():
            result = self._queue_many(session, clip_id, requests, credentials, allow_new=allow_new)
        if commit:
            session.commit()
        return result

    def _queue_many(
        self,
        session: Session,
        clip_id: str,
        requests: list[AutomaticPublicationCreate],
        credentials: CredentialStore,
        *,
        allow_new: bool,
    ) -> tuple[str, list[tuple[str, AutomaticPublicationCreate]]]:
        clip = session.get(Clip, clip_id)
        if not clip:
            raise PublicationNotFoundError("clip not found")
        if clip.approval_status != "approved" or not clip.final_path:
            raise PublicationStateError("clip must be approved and rendered before publishing")
        if clip.project.status in {"queued", "downloading", "processing", "cancel_requested"}:
            raise PublicationStateError(
                "Wait for the project pipeline to finish preparing publishing copy"
            )
        if not requests:
            raise PublicationStateError("select at least one publishing destination")
        account_ids = [request.social_account_id for request in requests]
        if len(set(account_ids)) != len(account_ids):
            raise PublicationStateError("each publishing destination can only be selected once")
        queued: list[tuple[str, AutomaticPublicationCreate]] = []
        for request in requests:
            account = session.get(SocialAccount, request.social_account_id)
            if not account or not account.is_active:
                raise PublicationNotFoundError("social account not found")
            self._check_visibility(account.platform, request.privacy_status)
            connection = credentials.load(account.id)
            if account.connection_status != "connected" or not connection:
                raise PublicationStateError(
                    f"connect this {account.platform} account before publishing"
                )
            self._check_destination(session, account, connection)
            issue = (
                instagram_publishing_issue(connection) if account.platform == "instagram" else None
            )
            if issue:
                raise PublicationStateError(issue)
            paused = session.scalar(
                select(Publication)
                .join(PublicationAccountLink)
                .where(
                    PublicationAccountLink.social_account_id == account.id,
                    Publication.status == "deferred",
                )
                .limit(1)
            )
            if paused:
                raise PublicationStateError(
                    "This destination is paused after an upload restriction. Check the provider, "
                    "then remove the deferred attempt to authorize a manual retry."
                )
            if any(
                publication.social_account_id == account.id
                and publication.status
                in (
                    {"queued", "processing", "deferred", "uncertain"}
                    if allow_new
                    else {"queued", "processing", "published", "deferred", "uncertain"}
                )
                for publication in clip.publications
            ):
                raise PublicationStateError(
                    f"this clip is already queued or published to {account.label}"
                )
            if allow_new:
                old = session.scalar(
                    select(PublicationDestination).where(
                        PublicationDestination.clip_id == clip.id,
                        PublicationDestination.social_account_id == account.id,
                    )
                )
                if old:
                    session.delete(old)
                    session.flush()
            prepared_copy = automatic_copy(session, clip.id, account.platform)
            if prepared_copy:
                request = AutomaticPublicationCreate(
                    social_account_id=request.social_account_id,
                    title=prepared_copy[0],
                    description=prepared_copy[1],
                    privacy_status=request.privacy_status,
                )
            publication = Publication(
                clip=clip,
                platform=account.platform,
                status="queued",
                post_url=None,
                title=request.title.strip(),
                description=request.description.strip(),
                published_at=None,
            )
            session.add(publication)
            capture_growth_context(session, publication, clip.id)
            session.flush()
            session.add(
                PublicationAccountLink(
                    publication_id=publication.id,
                    social_account_id=account.id,
                    account_label_snapshot=account.label,
                    account_username_snapshot=account.username,
                )
            )
            session.add(
                PublicationOptions(
                    publication_id=publication.id, privacy_status=request.privacy_status
                )
            )
            queued.append((publication.id, request))
            session.add(
                PublicationDestination(
                    publication_id=publication.id, clip_id=clip.id, social_account_id=account.id
                )
            )
            try:
                session.flush()
            except IntegrityError as error:
                raise PublicationStateError(
                    "this clip is already queued or published to the selected account"
                ) from error
        return clip.project_id, queued

    def publish_queued(
        self,
        session: Session,
        publication_id: str,
        request: AutomaticPublicationCreate,
        adapter: PublishingAdapter,
        credentials: CredentialStore,
    ) -> str:
        publication = session.get(Publication, publication_id)
        if not publication or not publication.account_link:
            raise PublicationNotFoundError("queued publication not found")
        if publication.status != "queued":
            raise PublicationStateError("publication is no longer queued")
        account = session.get(SocialAccount, publication.account_link.social_account_id)
        if not account or not account.is_active:
            raise PublicationNotFoundError("social account not found")
        self._check_visibility(account.platform, request.privacy_status)
        connection = credentials.load(account.id)
        if account.connection_status != "connected" or not connection:
            raise PublicationStateError(
                f"connect this {account.platform} account before publishing"
            )
        clip = publication.clip
        if clip.approval_status != "approved" or not clip.final_path:
            raise PublicationStateError("clip must be approved and rendered before publishing")
        self._check_destination(session, account, connection)
        # Renewal cannot create a post. Leave the job queued until this succeeds,
        # so a rejected token is a definite failure rather than an uncertain upload.
        try:
            connection = self._refresh_credentials(adapter, credentials, account.id, connection)
        except ProviderAuthenticationError:
            account.connection_status = "disconnected"
            session.commit()
            raise
        self._check_destination(session, account, connection)
        claimed = session.execute(
            update(Publication)
            .where(Publication.id == publication_id, Publication.status == "queued")
            .values(status="processing")
        )
        session.commit()
        if claimed.rowcount != 1:  # type: ignore[attr-defined]
            raise PublicationStateError(
                "Publication is already being processed; do not repeat upload"
            )

        def remember_upload(external_id: str) -> None:
            reference = session.get(PublicationProviderReference, publication.id)
            if reference:
                reference.external_id = external_id
            else:
                publication.provider_reference = PublicationProviderReference(
                    publication_id=publication.id, external_id=external_id
                )
            session.commit()

        try:
            result = adapter.publish(
                PublishRequest(
                    media_path=Path(clip.final_path),
                    title=request.title.strip(),
                    description=request.description.strip(),
                    privacy_status=request.privacy_status,
                    account_username=account.username,
                    duration_seconds=self._clip_duration(clip),
                    on_upload_started=remember_upload,
                ),
                connection,
            )
        except ProviderUploadRejected as error:
            publication.status = "failed"
            publication.failure = PublicationFailure(message=safe_provider_error(str(error)))
            reservation = session.get(PublicationDestination, publication_id)
            if reservation:
                session.delete(reservation)
            if isinstance(error, ProviderPublishingPermissionError):
                account.connection_status = "disconnected"
            session.commit()
            raise
        if result.status == "published" and not result.post_url:
            raise PublicationStateError("publishing provider did not return a post URL")
        if result.updated_connection:
            self._save_updated_credentials(
                credentials, account.id, result.updated_connection, connection
            )
        publication.status = result.status
        publication.post_url = result.post_url
        publication.published_at = now_utc() if result.status == "published" else None
        if result.external_id:
            remember_upload(result.external_id)
        session.commit()
        return clip.project_id

    def mark_failed(self, session: Session, publication_id: str, error: str | None = None) -> None:
        publication = session.get(Publication, publication_id)
        if publication and publication.status in {"queued", "processing"}:
            message = safe_provider_error(error or "Publishing failed before completion.")
            if "uploadLimitExceeded" in message or "quotaExceeded" in message:
                publication.status = "deferred"
                publication.failure = PublicationFailure(message=message)
                session.commit()
                return
            if publication.status == "processing":
                publication.status = "uncertain"
                publication.failure = PublicationFailure(
                    message="Upload result uncertain. Check the destination for an existing video "
                    "before authorizing another upload. " + message
                )
                session.commit()
                return
            reservation = session.get(PublicationDestination, publication_id)
            if reservation:
                session.delete(reservation)
            publication.status = "failed"
            publication.failure = PublicationFailure(
                message=safe_provider_error(error or "Publishing failed before completion.")
            )
            session.commit()

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
        if publication.status not in {"processing", "uncertain"}:
            raise PublicationStateError(
                "Only processing or uncertain uploads need a status refresh"
            )
        initial_status = publication.status
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
        account = session.get(SocialAccount, publication.account_link.social_account_id)
        if not account or not account.is_active or account.connection_status != "connected":
            raise PublicationStateError(
                "Reconnect the original publishing account before refreshing"
            )
        self._check_destination(session, account, connection)
        connection = self._refresh_credentials(
            adapter, credentials, publication.account_link.social_account_id, connection
        )
        self._check_destination(session, account, connection)
        result = adapter.refresh(
            publication.provider_reference.external_id,
            connection,
            publication.account_username or "",
        )
        if result.status == "published" and not result.post_url:
            raise PublicationStateError("publishing provider did not return a post URL")
        changed = session.execute(
            update(Publication)
            .where(Publication.id == publication_id, Publication.status == initial_status)
            .values(status=result.status, post_url=result.post_url)
        )
        if changed.rowcount != 1:  # type: ignore[attr-defined]
            session.rollback()
            raise PublicationStateError("Publication changed during refresh; reload its status")
        if result.updated_connection:
            self._save_updated_credentials(
                credentials,
                publication.account_link.social_account_id,
                result.updated_connection,
                connection,
            )
        if result.external_id:
            publication.provider_reference.external_id = result.external_id
        if result.status == "published":
            publication.published_at = publication.published_at or now_utc()
            publication.failure = None
        elif result.status == "failed":
            publication.failure = PublicationFailure(
                message=safe_provider_error(
                    result.error or "The platform reported that the upload failed."
                )
            )
            reservation = session.get(PublicationDestination, publication_id)
            if reservation:
                session.delete(reservation)
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
                publication=publication,
                views=request.views,
                likes=request.likes,
                comments=request.comments,
                shares=request.shares,
                watch_time_seconds=request.watch_time_seconds,
                reach=request.reach,
                sends=request.sends,
                average_watch_seconds=request.average_watch_seconds,
                opening_retention_percent=request.opening_retention_percent,
                completion_rate_percent=request.completion_rate_percent,
                search_views=request.search_views,
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
        from clipper.projects.account_health import clear_account_issue, record_account_issue

        publication = session.get(Publication, publication_id)
        account_id = publication.social_account_id if publication else None
        try:
            result = self._sync_metrics(session, publication_id, adapters, credentials)
        except Exception as error:
            session.rollback()
            if account_id:
                record_account_issue(session, account_id, error)
            raise
        if account_id:
            clear_account_issue(session, account_id)
        return result

    def _sync_metrics(
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
        account = session.get(SocialAccount, publication.account_link.social_account_id)
        if not account or not account.is_active or account.connection_status != "connected":
            raise PublicationStateError(
                "Reconnect the original publishing account in Settings → Accounts "
                "to resume insights. Saved metrics are preserved."
            )
        connection = credentials.load(account.id)
        if not connection:
            account.connection_status = "disconnected"
            session.commit()
            raise PublicationStateError(
                "The original publishing account credentials are missing. "
                "Reconnect it in Settings → Accounts to resume insights."
            )
        self._check_destination(session, account, connection)
        external_id = (
            publication.provider_reference.external_id if publication.provider_reference else None
        )
        try:
            connection = self._refresh_credentials(adapter, credentials, account.id, connection)
            self._check_destination(session, account, connection)
            metrics = adapter.metrics(external_id, publication.post_url, connection)
        except ProviderAuthenticationError:
            account.connection_status = "disconnected"
            session.commit()
            raise
        if publication.provider_reference:
            publication.provider_reference.external_id = metrics.external_id
        else:
            publication.provider_reference = PublicationProviderReference(
                external_id=metrics.external_id
            )
        previous = publication.metric_snapshots[-1] if publication.metric_snapshots else None
        session.add(
            MetricSnapshot(
                publication=publication,
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
        if publication.status in {"processing", "uncertain"}:
            raise PublicationStateError(
                "This upload may already exist on the platform. "
                "Check it before removing the local record."
            )
        from clipper.persistence.models import PostManagement

        management = session.get(PostManagement, publication_id)
        if management and management.state == "working":
            raise PublicationStateError(
                "Wait for the platform action to finish before removing this record"
            )
        if management is None:
            management = PostManagement(publication_id=publication_id, state="idle")
            session.add(management)
            try:
                session.flush()
            except IntegrityError as error:
                session.rollback()
                raise PublicationStateError("Another action started; refresh this post") from error
        claim = session.execute(
            update(PostManagement)
            .where(
                PostManagement.publication_id == publication_id, PostManagement.state != "working"
            )
            .values(state="working", action="forget")
        )
        if claim.rowcount != 1:  # type: ignore[attr-defined]
            session.rollback()
            raise PublicationStateError("Wait for the platform action to finish")
        if publication.status == "queued":
            cancelled = session.execute(
                update(Publication)
                .where(Publication.id == publication_id, Publication.status == "queued")
                .values(status="cancelled")
            )
            if cancelled.rowcount != 1:  # type: ignore[attr-defined]
                session.rollback()
                raise PublicationStateError("Upload has started; refresh before cancelling")
        project_id = publication.clip.project_id
        reservation = session.get(PublicationDestination, publication_id)
        if reservation:
            session.delete(reservation)
        options = session.get(PublicationOptions, publication_id)
        if options:
            session.delete(options)
        session.delete(management)
        session.delete(publication)
        session.commit()
        return project_id
