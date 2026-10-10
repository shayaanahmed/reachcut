from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from clipper.config import Settings
from clipper.persistence import Base
from clipper.projects import RuntimeSettingsService


def test_runtime_settings_are_persisted() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    service = RuntimeSettingsService(Settings(data_dir=Path("data")))

    with Session(engine) as session:
        updated = service.update(
            session,
            ollama_base_url="http://mini-pc.local:11434/",
            editorial_model="qwen3:14b",
        )
        loaded = service.get(session)

    assert updated.ollama_base_url == "http://mini-pc.local:11434"
    assert loaded == updated
