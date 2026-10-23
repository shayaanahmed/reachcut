from sqlalchemy import select
from sqlalchemy.orm import Session

from clipper.persistence import now_utc
from clipper.persistence.models import AccountIssue, PostManagement, PublicationAccountLink
from clipper.providers.publishing_http import safe_provider_error


def record_account_issue(session: Session, account_id: str, error: Exception) -> None:
    row = session.get(AccountIssue, account_id)
    if row is None:
        row = AccountIssue(account_id=account_id)
        session.add(row)
    row.message, row.recorded_at = safe_provider_error(str(error)), now_utc()
    session.commit()


def clear_account_issue(session: Session, account_id: str) -> None:
    row = session.get(AccountIssue, account_id)
    if row:
        unresolved = session.scalar(
            select(PostManagement.publication_id)
            .join(
                PublicationAccountLink,
                PublicationAccountLink.publication_id == PostManagement.publication_id,
            )
            .where(
                PublicationAccountLink.social_account_id == account_id,
                PostManagement.state == "failed",
                PostManagement.error == row.message,
            )
            .limit(1)
        )
        if unresolved:
            return  # Read permission succeeding does not resolve a failed write permission.
        session.delete(row)
        session.commit()
