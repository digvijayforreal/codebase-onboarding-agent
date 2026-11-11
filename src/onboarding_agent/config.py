"""Application configuration loaded from environment / .env file."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Project root = three levels up from this file:
# src/onboarding_agent/config.py -> src/onboarding_agent -> src -> <root>
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime settings. Values come from environment variables or the .env file."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"

    tavily_api_key: str = ""

    data_dir: str = ".cache"

    host: str = "127.0.0.1"
    port: int = 8000

    @property
    def data_path(self) -> Path:
        """Absolute path to the cache directory, created on access."""
        p = PROJECT_ROOT / self.data_dir
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def repos_path(self) -> Path:
        p = self.data_path / "repos"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def chroma_path(self) -> Path:
        p = self.data_path / "chroma"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def has_groq(self) -> bool:
        return bool(self.groq_api_key and not self.groq_api_key.startswith("your_"))

    @property
    def has_tavily(self) -> bool:
        return bool(self.tavily_api_key and not self.tavily_api_key.startswith("your_"))


settings = Settings()
