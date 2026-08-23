import pytest

from clipper.config import Settings


def test_model_runtime_settings_are_loaded_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLIPPER_TRANSCRIPTION_PROVIDER", "faster-whisper")
    monkeypatch.setenv("CLIPPER_WHISPER_MODEL", "small")
    monkeypatch.setenv("CLIPPER_WHISPER_DEVICE", "cuda")
    monkeypatch.setenv("CLIPPER_WHISPER_COMPUTE_TYPE", "float16")
    monkeypatch.setenv("CLIPPER_EDITORIAL_PROVIDER", "ollama")
    monkeypatch.setenv("CLIPPER_EDITORIAL_MODEL", "example-model")
    monkeypatch.setenv("CLIPPER_EDITORIAL_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("CLIPPER_EDITORIAL_NUM_CTX", "4096")
    monkeypatch.setenv("CLIPPER_EDITORIAL_NUM_PREDICT", "1024")
    monkeypatch.setenv("CLIPPER_EDITORIAL_RETRY_NUM_CTX", "8192")
    monkeypatch.setenv("CLIPPER_EDITORIAL_RETRY_NUM_PREDICT", "2048")

    settings = Settings(_env_file=None)

    assert settings.transcription_provider == "faster-whisper"
    assert settings.whisper_model == "small"
    assert settings.whisper_device == "cuda"
    assert settings.whisper_compute_type == "float16"
    assert settings.editorial_provider == "ollama"
    assert settings.editorial_model == "example-model"
    assert settings.editorial_timeout_seconds == 30
    assert settings.editorial_num_ctx == 4096
    assert settings.editorial_num_predict == 1024
    assert settings.editorial_retry_num_ctx == 8192
    assert settings.editorial_retry_num_predict == 2048
