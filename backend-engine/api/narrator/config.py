from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class NarratorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ollama_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "llama3.2:3b"
    kokoro_url: str = "http://tts:8880"
    narrator_enabled: bool = False
    narrator_voice: str = "af_bella"
    narrator_audio_dir: str = "/tmp/narr_audio"
    narrator_audio_ttl_s: int = 300
    narrator_mode: str = "auto"   # "auto" | "live" | "static"


@lru_cache
def get_narrator_settings() -> NarratorSettings:
    return NarratorSettings()
