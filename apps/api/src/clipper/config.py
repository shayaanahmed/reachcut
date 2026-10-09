from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLIPPER_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    database_url: str = "sqlite:///./data/clipper.db"
    transcription_provider: Literal["faster-whisper"] = "faster-whisper"
    whisper_model: str = "large-v3-turbo"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    editorial_provider: Literal["ollama"] = "ollama"
    editorial_base_url: str = "http://127.0.0.1:11434"
    editorial_model: str = "qwen3:8b-q4_K_M"
    editorial_timeout_seconds: float = Field(default=600, gt=0)
    editorial_model_download_timeout_seconds: float = Field(default=7_200, gt=0)
    editorial_num_ctx: int = Field(default=8_192, ge=1)
    editorial_num_predict: int = Field(default=2_048, ge=1)
    editorial_retry_num_ctx: int = Field(default=16_384, ge=1)
    editorial_retry_num_predict: int = Field(default=4_096, ge=1)
    tracking_provider: Literal["opencv", "disabled"] = "opencv"
    tracking_sample_interval_seconds: float = Field(default=0.5, ge=0.1, le=5)
    max_upload_bytes: int = Field(default=8 * 1024**3, ge=1)
    max_secondary_media_bytes: int = Field(default=2 * 1024**3, ge=1)
    max_duration_seconds: float = Field(default=6 * 60 * 60, gt=0)
    web_port: int = Field(default=3_000, ge=1, le=65_535)
    web_base_url: str = "http://127.0.0.1:3000"
    local_agent_token: str = Field(default="", repr=False)
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_redirect_uri: str = "http://127.0.0.1:8000/api/oauth/youtube/callback"
    meta_graph_version: str = "v24.0"
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    tiktok_redirect_uri: str = ""
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_redirect_uri: str = "http://127.0.0.1:8000/api/oauth/meta/callback"
    x_client_id: str = ""
    x_client_secret: str = ""
    x_redirect_uri: str = "http://127.0.0.1:8000/api/oauth/x/callback"
    yt_dlp_repository: Path | None = Path("../yt-dlp")
    yt_dlp_timeout_seconds: float = Field(default=3_600, gt=0)
    yt_dlp_allowed_hosts: str = (
        "youtube.com,youtu.be,vimeo.com,tiktok.com,twitch.tv,instagram.com,"
        "facebook.com,x.com,twitter.com"
    )

    @property
    def media_import_hosts(self) -> tuple[str, ...]:
        return tuple(host.strip() for host in self.yt_dlp_allowed_hosts.split(",") if host.strip())


settings = Settings()
