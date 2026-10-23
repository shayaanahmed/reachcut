"""Recover interrupted work only while holding the shared hardware process lock."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from clipper.persistence.models import InformativeShort
from clipper.shorts.service import ShortService


def run_next(session: Session, service: ShortService) -> str | None:
    for generated in session.scalars(
        select(InformativeShort).where(InformativeShort.status == "generating")
    ):
        service.sync_generation(session, generated)
    for interrupted in session.scalars(
        select(InformativeShort).where(
            InformativeShort.status.in_(["producing", "cancel_requested"])
        )
    ):
        interrupted.status = "cancelled" if interrupted.status == "cancel_requested" else "queued"
        interrupted.phase = "Recovered interrupted production; reusing completed sections"
    session.commit()
    short = session.scalar(
        select(InformativeShort)
        .where(InformativeShort.status == "queued")
        .order_by(InformativeShort.created_at)
        .limit(1)
    )
    if not short:
        return None
    try:
        service.produce(session, short)
    except Exception as error:
        # produce persists recoverable error details; never automatically retry failures.
        if short.status not in {"failed", "cancelled"}:
            short.status, short.error = (
                "failed",
                str(error)[:1000] or "Production interrupted; retry",
            )
            session.commit()
    return short.id
