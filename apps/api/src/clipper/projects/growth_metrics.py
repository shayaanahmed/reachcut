"""Refresh supported post counters periodically, even when no web page is open."""

from collections.abc import Mapping
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from clipper.persistence import Publication, RuntimeSetting, SocialAccount, now_utc
from clipper.projects.publications import PublicationService
from clipper.publishing import CredentialStore, MetricsAdapter


def refresh_growth_metrics(
    session: Session,
    service: PublicationService,
    adapters: Mapping[str, MetricsAdapter],
    credentials: CredentialStore,
) -> int:
    count = 0
    posts = session.scalars(
        select(Publication)
        .where(Publication.status == "published", Publication.platform.in_(list(adapters)))
        .order_by(Publication.created_at.desc())
    ).all()
    for post in posts:
        account = (
            session.get(SocialAccount, post.social_account_id) if post.social_account_id else None
        )
        if not account or not account.is_active or account.connection_status != "connected":
            continue
        key = "growth-metrics:" + post.id
        previous = session.get(RuntimeSetting, key)
        if previous and now_utc() - datetime.fromisoformat(previous.value) < timedelta(minutes=30):
            continue
        try:
            service.sync_metrics(session, post.id, adapters, credentials)
        except Exception:
            session.rollback()  # Isolate one provider failure and back off before retrying it.
        previous = session.get(RuntimeSetting, key)
        if previous:
            previous.value = now_utc().isoformat()
        else:
            session.add(RuntimeSetting(key=key, value=now_utc().isoformat()))
        session.commit()
        count += 1
        if count >= 5:
            break
    return count
