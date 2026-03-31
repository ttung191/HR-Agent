from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "HR Agent"
    app_version: str = "2.0.0"

    database_url: str = Field(default="sqlite:///./hr_agent.db")
    api_base_url: str = Field(default="http://127.0.0.1:8000")
    streamlit_base_url: str = Field(default="http://127.0.0.1:8501")

    min_text_length: int = 120
    max_upload_size_mb: int = 15

    enable_ocr_fallback: bool = True
    debug: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()