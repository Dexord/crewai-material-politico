from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:9b"
    output_dir: str = "data/output"
    scrape_rate_limit: float = 1.5
    vault_dir: str = "data/vault"
    max_depth: int = 2
    blacklist_alvos: str = "Flavio Bolsonaro"


@lru_cache
def get_settings() -> Settings:
    return Settings()
