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
    app_version: str = "3.0.0"
    database_url: str = Field(default="sqlite:///./hr_agent.db")
    api_base_url: str = Field(default="http://127.0.0.1:8000")
    streamlit_base_url: str = Field(default="http://127.0.0.1:8501")
    min_text_length: int = 120
    max_upload_size_mb: int = 15
    enable_ocr_fallback: bool = False
    debug: bool = False

    embedding_backend: str = Field(default="auto")
    embedding_model_name: str = Field(default="sentence-transformers/all-MiniLM-L6-v2")
    embedding_dimension: int = Field(default=384)
    vector_similarity_threshold: float = Field(default=0.15)
    vector_top_k_default: int = Field(default=25)


@lru_cache
def get_settings() -> Settings:
    return Settings()
