from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SECRET_PADRAO = "troque-isto-por-um-segredo-longo-e-aleatorio"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Histórico de Serviços"
    app_env: str = "dev"
    api_base_url: str = "http://127.0.0.1:8000"
    api_prefix: str = "/api/v1"
    secret_key: str = SECRET_PADRAO
    cookie_secure: bool = False
    session_max_age_days: int = 7
    timezone: str = "America/Sao_Paulo"

    @model_validator(mode="after")
    def _segredo_em_producao(self) -> "Settings":
        if self.app_env == "prod" and self.secret_key == SECRET_PADRAO:
            raise ValueError("SECRET_KEY padrão não pode ser usada em produção.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
