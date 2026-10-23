"""Manage an existing provider post without re-uploading media."""

import json
from collections.abc import Mapping
from typing import Literal

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from clipper.editorial.publishing_copy import caption_with_tags
from clipper.persistence import Clip, Publication, SocialAccount, now_utc
from clipper.persistence.models import PostChange, PostManagement, PublicationDestination
from clipper.projects.account_health import clear_account_issue, record_account_issue
from clipper.projects.growth_automation import automatic_copy
from clipper.projects.publications import (
    PublicationNotFoundError,
    PublicationService,
    PublicationStateError,
)
from clipper.projects.stages import StageRunner
from clipper.providers.publishing_http import safe_provider_error
from clipper.publishing import CredentialStore, PublishingAdapter
from clipper.publishing.contracts import PostDeleter, PostUpdater
from clipper.publishing.permissions import instagram_deletion_issue


def suggested_copy(session: Session, post: Publication) -> tuple[str, str]:
    return clip_copy(session, post.clip, post.platform, post.title)


def clip_copy(
    session: Session, clip: Clip, platform: str, fallback_title: str = ""
) -> tuple[str, str]:
    prepared = automatic_copy(session, clip.id, platform)
    plan = clip.plan
    raw_tags = plan.get("hashtags", [])
    tags = [str(tag) for tag in raw_tags] if isinstance(raw_tags, list) else []
    if not tags:
        try:
            for item in json.loads(
                StageRunner.artifact_path(clip.project, "generate_metadata").read_text()
            ):
                if item.get("clip_id") == clip.id:
                    tags = [str(tag) for tag in item.get("hashtags", [])][:5]
                    break
        except (OSError, ValueError, TypeError):
            pass
    title, description = prepared or (
        str(plan.get("suggested_title") or fallback_title or "New clip")[:100],
        str(plan.get("suggested_description") or ""),
    )
    caption = caption_with_tags(description, tags)
    return title, caption[:280] if platform == "x" else caption


def connection_issue(
    session: Session, post: Publication, credentials: CredentialStore
) -> str | None:
    account = session.get(SocialAccount, post.social_account_id) if post.social_account_id else None
    if not account or not account.is_active or account.connection_status != "connected":
        return "Reconnect the original publishing account before managing this post."
    try:
        connection = credentials.load(account.id)
    except Exception:
        return "Saved authorization could not be read. Reconnect this account in Accounts."
    if not connection:
        return "Reconnect this account to restore its saved authorization."
    if post.platform == "youtube" and not set(connection.granted_scopes or ()).intersection(
        {
            "https://www.googleapis.com/auth/youtube.force-ssl",
            "https://www.googleapis.com/auth/youtube",
        }
    ):
        return (
            "YouTube post-management permission is missing or unverified. "
            "Reconnect this channel and grant the requested permissions; your draft will be kept."
        )
    return None


def deletion_issue(session: Session, post: Publication, credentials: CredentialStore) -> str | None:
    if post.platform != "instagram":
        return None
    if not post.provider_publication_id:
        return "No original Instagram media ID was saved. Delete this post directly on Instagram."
    try:
        connection = credentials.load(post.social_account_id) if post.social_account_id else None
    except Exception:
        connection = None
    if not connection:
        return "Reconnect the original Instagram account before deleting this post."
    return instagram_deletion_issue(connection)


def capabilities(adapter: object, platform: str) -> dict[str, object]:
    return {
        "update": isinstance(adapter, PostUpdater),
        "delete": isinstance(adapter, PostDeleter),
        "title": platform == "youtube",
        "explanation": {
            "youtube": (
                "Update title and description in place. "
                "Older connections may need Reconnect for management permission."
            ),
            "facebook": (
                "Update the Reel caption in place; "
                "title and video replacement are unavailable here."
            ),
            "instagram": (
                "Caption editing is unavailable through this integration. "
                "Open Instagram to edit it. "
                "Deletion needs the original media ID, instagram_manage_contents permission "
                "and a Facebook User access token."
            ),
            "tiktok": (
                "This integration cannot edit or delete existing TikTok posts. "
                "Open TikTok to manage the post."
            ),
            "x": (
                "Editing in place is unavailable here. "
                "You can delete an existing post or open X to manage it."
            ),
        }.get(platform, "Manage this post on its platform."),
    }


def manage_post(
    session: Session,
    publication_id: str,
    action: Literal["update", "delete"],
    adapters: Mapping[str, PublishingAdapter],
    credentials: CredentialStore,
    *,
    title: str = "",
    description: str = "",
) -> str:
    post = session.get(Publication, publication_id)
    if not post:
        raise PublicationNotFoundError("Publication not found")
    if post.status != "published":
        raise PublicationStateError("Only a published post can be updated or deleted remotely")
    if action == "update" and post.clip.project.status in {
        "queued",
        "downloading",
        "processing",
        "cancel_requested",
    }:
        raise PublicationStateError(
            "Wait for the project pipeline to finish preparing publishing copy"
        )
    adapter = adapters.get(post.platform)
    if not adapter or not capabilities(adapter, post.platform)[action]:
        raise PublicationStateError(
            "This action is unavailable for this platform. Open the original post to manage it."
        )
    account = session.get(SocialAccount, post.social_account_id) if post.social_account_id else None
    if not account or not account.is_active or account.connection_status != "connected":
        raise PublicationStateError(
            "Reconnect the original account in Accounts to manage this post"
        )
    connection = credentials.load(account.id)
    if not connection:
        raise PublicationStateError("Reconnect the original publishing account")
    issue = connection_issue(session, post, credentials)
    if not issue and action == "delete":
        issue = deletion_issue(session, post, credentials)
    if issue:
        error = PublicationStateError(issue)
        record_account_issue(session, account.id, error)
        raise error
    PublicationService._check_destination(session, account, connection)
    row = session.get(PostManagement, post.id)
    if row is None:
        row = PostManagement(publication_id=post.id, state="idle")
        session.add(row)
        try:
            session.commit()
        except IntegrityError as error:
            session.rollback()
            raise PublicationStateError(
                "Another action already owns this post; refresh its status"
            ) from error
    claimed = session.execute(
        update(PostManagement)
        .where(PostManagement.publication_id == post.id, PostManagement.state != "working")
        .values(state="working", action=action, error=None, updated_at=now_utc())
    )
    session.commit()
    if claimed.rowcount != 1:  # type: ignore[attr-defined]
        raise PublicationStateError(
            "This post already has an action in progress. "
            "Check the platform before retrying interrupted work."
        )
    before: dict[str, object] = {
        "title": post.title,
        "description": post.description,
        "status": post.status,
    }
    try:
        connection = PublicationService._refresh_credentials(
            adapter, credentials, account.id, connection
        )
        PublicationService._check_destination(session, account, connection)
        issue = connection_issue(session, post, credentials)
        if issue:
            raise PublicationStateError(issue)
        if action == "update" and isinstance(adapter, PostUpdater):
            adapter.update_post(
                post.provider_publication_id, post.post_url, title, description, connection
            )
            if post.platform == "youtube":
                post.title = title
            post.description = description
        elif action == "delete" and isinstance(adapter, PostDeleter):
            adapter.delete_post(post.provider_publication_id, post.post_url, connection)
            post.status = "deleted"
            reservation = session.get(PublicationDestination, post.id)
            if reservation:
                session.delete(reservation)
        row = session.get(PostManagement, post.id)
        assert row is not None
        row.state, row.error, row.updated_at = "succeeded", None, now_utc()
        session.add(
            PostChange(
                publication_id=post.id,
                action=action,
                before=before,
                after={"title": post.title, "description": post.description, "status": post.status},
            )
        )
        session.commit()
    except Exception as error:
        session.rollback()
        row = session.get(PostManagement, publication_id)
        if row:
            row.state, row.error, row.updated_at = (
                "failed",
                safe_provider_error(str(error)),
                now_utc(),
            )
            session.commit()
        record_account_issue(session, account.id, error)
        raise
    clear_account_issue(session, account.id)
    return post.clip.project_id
