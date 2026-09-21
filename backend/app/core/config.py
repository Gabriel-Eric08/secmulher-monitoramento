from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SECRET_KEY_PADRAO = "troque-isto-por-um-segredo-longo-e-aleatorio"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    app_name: str = "Histórico de Serviços — Secretaria da Mulher"
    app_version: str = "1.0.0"

    database_url: str = "sqlite+aiosqlite:///./dev.db"

    secret_key: str = SECRET_KEY_PADRAO
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    login_max_tentativas: int = 5
    login_bloqueio_minutos: int = 15

    cors_origins: str = "http://localhost:3000,http://localhost:8080"
    docs_enabled: bool = True

    storage_backend: Literal["local", "s3"] = "local"
    storage_local_path: str = "./storage"
    s3_endpoint: str | None = None
    s3_bucket: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str = "us-east-1"

    max_upload_mb: int = 20

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @model_validator(mode="after")
    def _exigir_segredo_em_producao(self) -> "Settings":
        if self.app_env == "prod" and self.secret_key == SECRET_KEY_PADRAO:
            raise ValueError("SECRET_KEY padrão não pode ser usada em produção.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
