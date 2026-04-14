from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    secret_key: str = "dev-secret-change-in-production"
    redis_url: str = "redis://localhost:6379/0"
    schema_version: str = "0.4"
    debug: bool = False

    night_timer_seconds: int = 60
    day_timer_seconds: int = 180
    vote_timer_seconds: int = 90
    role_deal_timer_seconds: int = 30
    hunter_pending_timer_seconds: int = 30

    redis_game_ttl_seconds: int = 172800  # 48 hours
    max_active_games: int = 100
    database_url: str = "postgresql+asyncpg://werewolf:werewolf@postgres/werewolf"

    # Narrator settings (PRD-008)
    narrator_enabled: bool = False
    ollama_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "llama3.2:3b"
    kokoro_url: str = "http://tts:8880"
    narrator_voice: str = "af_bella"


@lru_cache
def get_settings() -> Settings:
    return Settings()
