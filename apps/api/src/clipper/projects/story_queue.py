from sqlalchemy import select
from sqlalchemy.orm import Session

from clipper.persistence.models import StoryDraft


class StoryQueue:
    def list(self, session: Session) -> list[StoryDraft]:
        return list(
            session.scalars(select(StoryDraft).order_by(StoryDraft.created_at, StoryDraft.id))
        )

    def get(self, session: Session, draft_id: str) -> StoryDraft:
        draft = session.get(StoryDraft, draft_id)
        if not draft:
            raise LookupError("Queued story not found")
        return draft

    def save(
        self, session: Session, story: str, settings: dict[str, object], draft_id: str | None = None
    ) -> StoryDraft:
        draft = self.get(session, draft_id) if draft_id else StoryDraft()
        draft.story = story
        draft.settings = settings
        session.add(draft)
        session.commit()
        return draft

    def delete(self, session: Session, draft_id: str) -> None:
        session.delete(self.get(session, draft_id))
        session.commit()
