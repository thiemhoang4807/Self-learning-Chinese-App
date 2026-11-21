from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(Path(__file__).resolve().parents[2] / ".env", ".env"),
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://mandarin:mandarin@127.0.0.1:5432/mandarin"
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-2.5-flash"
    audio_dir: Path = Path("data/audio")
    max_upload_bytes: int = Field(25 * 1024 * 1024, ge=1024, le=50 * 1024 * 1024)
    max_visual_pages: int = Field(24, ge=1, le=50)


settings = Settings()
