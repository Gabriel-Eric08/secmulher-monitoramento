from pydantic import ConfigDict, EmailStr, Field, field_validator

from app.modules.usuarios.schema import Senha
from app.shared.schemas import Esquema


class LoginEntrada(Esquema):
    email: EmailStr = Field(..., examples=["ana.lima@secretaria.gov.br"])
    senha: str = Field(..., min_length=1, max_length=128, examples=["Senha1234"])

    @field_validator("email")
    @classmethod
    def _minusculo(cls, v: str) -> str:
        return v.lower()


class RefreshEntrada(Esquema):
    refresh_token: str = Field(..., description="Refresh token recebido no login ou no último refresh.")


class AlterarSenhaEntrada(Esquema):
    senha_atual: str = Field(..., min_length=1, max_length=128)
    nova_senha: Senha


class TokenPar(Esquema):
    access_token: str = Field(..., description="JWT de curta duração; enviar em `Authorization: Bearer`.")
    refresh_token: str = Field(..., description="Token de longa duração, uso único (rotacionado a cada refresh).")
    token_type: str = Field("bearer", examples=["bearer"])
    expires_in: int = Field(..., description="Validade do access token, em segundos.", examples=[1800])

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "token_type": "bearer",
                    "expires_in": 1800,
                }
            ]
        }
    )
