from functools import lru_cache

from pydantic import AnyHttpUrl, SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # App settings
    app_name: str = "Lead Intelligence Agent API"
    service_name: str = "lead-intelligence-agent"

    laravel_callback_base_url: AnyHttpUrl = AnyHttpUrl("http://host.docker.internal:8092")

    # Agent settings
    agent_max_candidates: int = Field(default=10, ge=1, le=20)
    agent_max_research: int = Field(default=5, ge=1, le=10)
    contact_max_people: int = Field(default=3, ge=1, le=5)

    # Research settings
    research_max_pages: int = Field(default=4, ge=1, le=6)
    research_max_evidence: int = Field(default=8, ge=1, le=10)

    # OpenAI
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o-mini"

    # Company search providers
    google_places_api_key: SecretStr | None = None
    google_places_base_url: AnyHttpUrl = AnyHttpUrl("https://places.googleapis.com")
    hunter_api_key: SecretStr | None = None
    hunter_base_url: AnyHttpUrl = AnyHttpUrl("https://api.hunter.io")


@lru_cache
def get_settings() -> Settings:
    return Settings()
