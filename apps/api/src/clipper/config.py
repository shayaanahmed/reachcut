from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLIPPER_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    database_url: str = "sqlite:///./data/clipper.db"
    editorial_base_url: str = "http://127.0.0.1:11434"
    editorial_model: str = "qwen3:8b-q4_K_M"
    whisper_model: str = "small"
    max_upload_bytes: int = Field(default=8 * 1024**3, ge=1)
    max_duration_seconds: float = Field(default=6 * 60 * 60, gt=0)


settings = Settings()
