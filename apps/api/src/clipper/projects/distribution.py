from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from clipper.persistence import Clip, Project, SocialAccount
from clipper.persistence.models import SocialAccountGroup, SocialAccountGroupMember
from clipper.projects.publications import (
    AutomaticPublicationCreate,
    PublicationNotFoundError,
    PublicationService,
    PublicationStateError,
)
from clipper.providers.credentials import CredentialStoreError
from clipper.publishing import CredentialStore


class AccountGroupService:
    def list_groups(self, session: Session) -> list[SocialAccountGroup]:
        return list(session.scalars(select(SocialAccountGroup).order_by(SocialAccountGroup.name)))

    def save(
        self,
        session: Session,
        group_id: str | None,
        name: str,
        description: str,
        account_ids: list[str],
    ) -> SocialAccountGroup:
        name = name.strip()
        if not name:
            raise PublicationStateError("group name cannot be blank")
        group = session.get(SocialAccountGroup, group_id) if group_id else None
        if group_id and not group:
            raise PublicationNotFoundError("social account group not found")
        duplicate = session.scalar(
            select(SocialAccountGroup).where(SocialAccountGroup.name_key == name.casefold())
        )
        if duplicate and duplicate.id != group_id:
            raise PublicationStateError("a group with this name already exists")
        accounts = list(
            session.scalars(
                select(SocialAccount).where(
                    SocialAccount.id.in_(set(account_ids)), SocialAccount.is_active.is_(True)
                )
            )
        )
        if len(accounts) != len(set(account_ids)):
            raise PublicationStateError("group members must be active social accounts")
        if group is None:
            group = SocialAccountGroup(name=name, name_key=name.casefold())
            session.add(group)
        group.name = name
        group.name_key = name.casefold()
        group.description = description.strip()
        existing = {member.account_id: member for member in group.members}
        group.members = [
            existing.get(account.id) or SocialAccountGroupMember(account_id=account.id)
            for account in accounts
        ]
        session.commit()
        return group

    def delete(self, session: Session, group_id: str) -> None:
        group = session.get(SocialAccountGroup, group_id)
        if not group:
            raise PublicationNotFoundError("social account group not found")
        session.delete(group)
        session.commit()


def selected_clips(session: Session, project_id: str, clip_ids: list[str] | None) -> list[Clip]:
    project = session.get(Project, project_id)
    if not project:
        raise PublicationNotFoundError("project not found")
    clips = project.clips
    if clip_ids is not None:
        requested = set(clip_ids)
        if not requested or not requested.issubset({clip.id for clip in clips}):
            raise PublicationStateError("select clips belonging to this project")
        clips = [clip for clip in clips if clip.id in requested]
    if not clips:
        raise PublicationStateError("this project has no generated clips")
    return clips


def approve_clips(session: Session, project_id: str, clip_ids: list[str] | None) -> None:
    for clip in selected_clips(session, project_id, clip_ids):
        clip.approval_status = "approved"
    session.commit()


@dataclass(frozen=True)
class BulkPublishSkip:
    clip_id: str
    account_id: str
    reason: str


def queue_project_publications(
    session: Session,
    project_id: str,
    clip_ids: list[str] | None,
    account_ids: list[str],
    group_id: str | None,
    platform: str | None,
    credentials: CredentialStore,
    service: PublicationService,
) -> tuple[list[tuple[str, AutomaticPublicationCreate]], list[BulkPublishSkip]]:
    clips = selected_clips(session, project_id, clip_ids)
    if sum((bool(account_ids), bool(group_id), bool(platform))) != 1:
        raise PublicationStateError("choose accounts, a social group, or a platform")
    if group_id:
        group = session.get(SocialAccountGroup, group_id)
        if not group:
            raise PublicationNotFoundError("social account group not found")
        account_ids = group.account_ids
    statement = select(SocialAccount).where(SocialAccount.is_active.is_(True))
    statement = (
        statement.where(SocialAccount.platform == platform)
        if platform
        else statement.where(SocialAccount.id.in_(set(account_ids)))
    )
    accounts = list(session.scalars(statement.order_by(SocialAccount.label)))
    if not accounts:
        raise PublicationStateError("this destination has no active social accounts")
    if account_ids and not group_id and len(accounts) != len(set(account_ids)):
        raise PublicationStateError("one or more selected accounts are no longer active")
    if len(accounts) * len(clips) > 1000:
        raise PublicationStateError("select at most 1,000 clip and account combinations at once")
    queued: list[tuple[str, AutomaticPublicationCreate]] = []
    skipped: list[BulkPublishSkip] = []
    ready: set[str] = set()
    for account in accounts:
        try:
            connection = credentials.load(account.id)
            if connection and account.connection_status == "connected":
                service._check_destination(session, account, connection)
                ready.add(account.id)
        except (CredentialStoreError, PublicationStateError):
            # One damaged connection must not block all other destinations.
            continue
    for clip in clips:
        requests: list[AutomaticPublicationCreate] = []
        for account in accounts:
            reason = None
            if clip.approval_status != "approved":
                reason = "Approve this clip first"
            elif not clip.final_path:
                reason = "Render the final video first"
            elif account.id not in ready:
                reason = "Reconnect this account in Settings → Accounts"
            elif any(
                p.social_account_id == account.id
                and p.status in {"queued", "processing", "published"}
                for p in clip.publications
            ):
                reason = "Already queued or published to this account"
            if reason:
                skipped.append(BulkPublishSkip(clip.id, account.id, reason))
                continue
            title = str(clip.plan.get("suggested_title") or "New short clip")[:100]
            raw_tags = clip.plan.get("hashtags", [])
            clip_tags = (
                [tag for tag in raw_tags if isinstance(tag, str)]
                if isinstance(raw_tags, list)
                else []
            )
            tags = list(dict.fromkeys([*clip_tags, *account.default_hashtags]))
            description = "\n\n".join(
                value
                for value in [
                    title,
                    " ".join(tags),
                    account.default_cta,
                    account.default_campaign_url,
                ]
                if value
            )
            if account.platform == "x":
                description = description[:280]
            requests.append(
                AutomaticPublicationCreate(
                    social_account_id=account.id, title=title, description=description[:5000]
                )
            )
        if requests:
            _, additions = service.queue_many(session, clip.id, requests, credentials, commit=False)
            queued.extend(additions)
    session.commit()
    return queued, skipped
