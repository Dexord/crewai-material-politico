from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:9b"
    ollama_model_escrita: str = "gemma4:e4b"
    output_dir: str = "data/output"
    estado_dir: str = "data/estado"
    scrape_rate_limit: float = 1.5
    vault_dir: str = "data/vault"
    max_depth: int = 3
    blacklist_alvos: str = ""
    frescor_dias: int = 4
    revisitar_top: int = 10
    revisitar_aleatorio: int = 3
    dedupe_fatos_limiar: float = 0.85


@lru_cache
def get_settings() -> Settings:
    return Settings()
