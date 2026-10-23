import pytest

from clipper.config import Settings


def test_voicebox_defaults_to_local_service_port_and_can_be_overridden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLIPPER_VOICEBOX_BASE_URL", raising=False)
    assert Settings(_env_file=None).voicebox_base_url == "http://127.0.0.1:17600"
    monkeypatch.setenv("CLIPPER_VOICEBOX_BASE_URL", "http://voicebox:8000")
    assert Settings(_env_file=None).voicebox_base_url == "http://voicebox:8000"


def test_model_runtime_settings_are_loaded_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLIPPER_TRANSCRIPTION_PROVIDER", "faster-whisper")
    monkeypatch.setenv("CLIPPER_WHISPER_MODEL", "small")
    monkeypatch.setenv("CLIPPER_WHISPER_DEVICE", "cuda")
    monkeypatch.setenv("CLIPPER_WHISPER_COMPUTE_TYPE", "float16")
    monkeypatch.setenv("CLIPPER_EDITORIAL_PROVIDER", "ollama")
    monkeypatch.setenv("CLIPPER_EDITORIAL_MODEL", "example-model")
    monkeypatch.setenv("CLIPPER_THUMBNAIL_MODEL", "example-vision-model")
    monkeypatch.setenv("CLIPPER_EDITORIAL_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("CLIPPER_EDITORIAL_NUM_CTX", "4096")
    monkeypatch.setenv("CLIPPER_EDITORIAL_NUM_PREDICT", "1024")
    monkeypatch.setenv("CLIPPER_EDITORIAL_RETRY_NUM_CTX", "8192")
    monkeypatch.setenv("CLIPPER_EDITORIAL_RETRY_NUM_PREDICT", "2048")
    monkeypatch.setenv("CLIPPER_WEB_PORT", "3001")
    monkeypatch.setenv("CLIPPER_TRACKING_PROVIDER", "disabled")
    monkeypatch.setenv("CLIPPER_TRACKING_SAMPLE_INTERVAL_SECONDS", "1.25")
    monkeypatch.setenv("CLIPPER_MAX_SECONDARY_MEDIA_BYTES", "4096")

    settings = Settings(_env_file=None)

    assert settings.transcription_provider == "faster-whisper"
    assert settings.whisper_model == "small"
    assert settings.whisper_device == "cuda"
    assert settings.whisper_compute_type == "float16"
    assert settings.editorial_provider == "ollama"
    assert settings.editorial_model == "example-model"
    assert settings.thumbnail_model == "example-vision-model"
    assert settings.editorial_timeout_seconds == 30
    assert settings.editorial_num_ctx == 4096
    assert settings.editorial_num_predict == 1024
    assert settings.editorial_retry_num_ctx == 8192
    assert settings.editorial_retry_num_predict == 2048
    assert settings.web_port == 3001
    assert settings.tracking_provider == "disabled"
    assert settings.tracking_sample_interval_seconds == 1.25
    assert settings.max_secondary_media_bytes == 4096
    assert settings.tiktok_redirect_uri == "http://127.0.0.1:8000/api/oauth/tiktok/callback"


def test_instagram_and_facebook_oauth_credentials_are_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLIPPER_INSTAGRAM_APP_ID", "instagram-app")
    monkeypatch.setenv("CLIPPER_INSTAGRAM_APP_SECRET", "instagram-secret")
    monkeypatch.setenv("CLIPPER_INSTAGRAM_LOGIN_CONFIG_ID", "instagram-config")
    monkeypatch.setenv("CLIPPER_INSTAGRAM_REDIRECT_URI", "https://example.test/instagram")
    monkeypatch.setenv("CLIPPER_FACEBOOK_APP_ID", "facebook-app")
    monkeypatch.setenv("CLIPPER_FACEBOOK_APP_SECRET", "facebook-secret")
    monkeypatch.setenv("CLIPPER_FACEBOOK_LOGIN_CONFIG_ID", "facebook-config")
    monkeypatch.setenv("CLIPPER_FACEBOOK_REDIRECT_URI", "https://example.test/facebook")

    settings = Settings(_env_file=None)

    assert settings.instagram_app_id == "instagram-app"
    assert settings.instagram_app_secret == "instagram-secret"  # noqa: S105
    assert settings.instagram_login_config_id == "instagram-config"
    assert settings.instagram_redirect_uri == "https://example.test/instagram"
    assert settings.facebook_app_id == "facebook-app"
    assert settings.facebook_app_secret == "facebook-secret"  # noqa: S105
    assert settings.facebook_login_config_id == "facebook-config"
    assert settings.facebook_redirect_uri == "https://example.test/facebook"


def test_social_oauth_defaults_use_current_graph_api_and_localhost_redirects() -> None:
    settings = Settings(_env_file=None)

    assert settings.graph_api_version == "v26.0"
    assert settings.instagram_redirect_uri == "http://localhost:8000/api/oauth/instagram/callback"
    assert settings.facebook_redirect_uri == "http://localhost:8000/api/oauth/facebook/callback"
