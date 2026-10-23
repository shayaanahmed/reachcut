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
            thumbnail_model="qwen3-vl:8b",
        )
        loaded = service.get(session)

    assert updated.ollama_base_url == "http://mini-pc.local:11434"
    assert updated.thumbnail_model == "qwen3-vl:8b"
    assert loaded == updated


def test_task_models_fallback_and_old_clients_preserve_overrides() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    service = RuntimeSettingsService(Settings(data_dir=Path("data")))
    with Session(engine) as session:
        selected = service.update(
            session,
            ollama_base_url="http://local:11434",
            editorial_model="main",
            thumbnail_model="vision",
            task_models={"growth": "growth-specialist", "translation": "translator"},
            transcription_model="small",
            automatic_growth=False,
        )
        assert selected.model_for("growth") == "growth-specialist"
        assert selected.model_for("metadata") == "main"
        assert selected.model_for("visual_review") == "vision"
        loaded = service.update(
            session,
            ollama_base_url="http://local:11434",
            editorial_model="new-main",
            thumbnail_model="vision",
        )
        assert loaded.model_for("growth") == "growth-specialist"
        assert loaded.transcription_model == "small" and not loaded.automatic_growth
        assert loaded.model_for("scripting") == "new-main"


def test_image_model_override_reaches_illustration_tasks() -> None:
    from clipper.api.informative import short_service

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    service = RuntimeSettingsService(Settings(data_dir=Path("data")))
    with Session(engine) as session:
        assert short_service.effective_image_model(session, "series-choice") == "series-choice"
        service.update(
            session,
            ollama_base_url="http://local:11434",
            editorial_model="main",
            thumbnail_model="vision",
            task_models={"image_generation": "image-choice"},
        )
        assert short_service.effective_image_model(session, "series-choice") == "image-choice"
