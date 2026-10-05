from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from clipper.persistence import SocialAccount


def normalized_hashtags(values: tuple[str, ...]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        tag = value.strip().replace(" ", "")
        if not tag:
            continue
        if not tag.startswith("#"):
            tag = f"#{tag}"
        if tag not in normalized:
            normalized.append(tag)
    return normalized


class SocialAccountNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class SocialAccountCreate:
    platform: str
    label: str
    username: str = ""
    profile_url: str | None = None
    default_hashtags: tuple[str, ...] = ()
    default_cta: str = ""
    default_campaign_url: str | None = None
    currency: str = "EUR"
    is_default: bool = False


@dataclass(frozen=True)
class SocialAccountUpdate:
    label: str
    username: str = ""
    profile_url: str | None = None
    default_hashtags: tuple[str, ...] = ()
    default_cta: str = ""
    default_campaign_url: str | None = None
    currency: str = "EUR"
    is_default: bool = False


class SocialAccountService:
    """Manage reusable public account metadata and publishing defaults."""

    def list(self, session: Session, *, include_archived: bool = False) -> list[SocialAccount]:
        statement = select(SocialAccount).order_by(SocialAccount.platform, SocialAccount.label)
        if not include_archived:
            statement = statement.where(SocialAccount.is_active.is_(True))
        return list(session.scalars(statement))

    def create(self, session: Session, request: SocialAccountCreate) -> SocialAccount:
        existing = list(
            session.scalars(
                select(SocialAccount).where(
                    SocialAccount.platform == request.platform,
                    SocialAccount.is_active.is_(True),
                )
            )
        )
        make_default = request.is_default or not existing
        if make_default:
            for account in existing:
                account.is_default = False

        account = SocialAccount(
            platform=request.platform,
            label=request.label.strip(),
            username=request.username.strip().lstrip("@"),
            profile_url=request.profile_url,
            default_hashtags=normalized_hashtags(request.default_hashtags),
            default_cta=request.default_cta.strip(),
            default_campaign_url=request.default_campaign_url,
            currency=request.currency.upper(),
            is_default=make_default,
        )
        session.add(account)
        session.commit()
        return account

    def update(
        self,
        session: Session,
        account_id: str,
        request: SocialAccountUpdate,
    ) -> SocialAccount:
        account = self._account(session, account_id)
        siblings = list(
            session.scalars(
                select(SocialAccount).where(
                    SocialAccount.platform == account.platform,
                    SocialAccount.id != account.id,
                    SocialAccount.is_active.is_(True),
                )
            )
        )
        make_default = request.is_default or not any(sibling.is_default for sibling in siblings)
        if make_default:
            for sibling in siblings:
                sibling.is_default = False

        account.label = request.label.strip()
        account.username = request.username.strip().lstrip("@")
        account.profile_url = request.profile_url
        account.default_hashtags = normalized_hashtags(request.default_hashtags)
        account.default_cta = request.default_cta.strip()
        account.default_campaign_url = request.default_campaign_url
        account.currency = request.currency.upper()
        account.is_default = make_default
        session.commit()
        return account

    def archive(self, session: Session, account_id: str) -> None:
        account = self._account(session, account_id)
        if account.is_default:
            replacement = session.scalar(
                select(SocialAccount)
                .where(
                    SocialAccount.platform == account.platform,
                    SocialAccount.id != account.id,
                    SocialAccount.is_active.is_(True),
                )
                .order_by(SocialAccount.created_at)
            )
            if replacement:
                replacement.is_default = True
        account.is_active = False
        account.is_default = False
        session.commit()

    @staticmethod
    def _account(session: Session, account_id: str) -> SocialAccount:
        account = session.get(SocialAccount, account_id)
        if not account or not account.is_active:
            raise SocialAccountNotFoundError("social account not found")
        return account
