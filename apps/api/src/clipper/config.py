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
    editorial_num_ctx: int = Field(default=8_192, ge=1)
    editorial_num_predict: int = Field(default=2_048, ge=1)
    editorial_retry_num_ctx: int = Field(default=16_384, ge=1)
    editorial_retry_num_predict: int = Field(default=4_096, ge=1)
    max_upload_bytes: int = Field(default=8 * 1024**3, ge=1)
    max_duration_seconds: float = Field(default=6 * 60 * 60, gt=0)


settings = Settings()
