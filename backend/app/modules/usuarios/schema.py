import re
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, ConfigDict, EmailStr, Field, field_validator

from app.shared.enums import PerfilUsuario
from app.shared.schemas import Esquema


def _validar_senha(valor: str) -> str:
    if not re.search(r"[A-Za-z]", valor) or not re.search(r"\d", valor):
        raise ValueError("A senha deve conter ao menos uma letra e um número.")
    return valor


Senha = Annotated[
    str,
    Field(min_length=8, max_length=128, description="Mínimo de 8 caracteres, com letra e número.", examples=["Senha1234"]),
    AfterValidator(_validar_senha),
]


class UsuarioCriar(Esquema):
    nome: str = Field(..., min_length=2, max_length=150, examples=["Ana Lima"])
    email: EmailStr = Field(..., examples=["ana.lima@secretaria.gov.br"])
    senha: Senha
    perfil: PerfilUsuario = Field(..., examples=["ATENDENTE"])

    @field_validator("email")
    @classmethod
    def _email_minusculo(cls, v: str) -> str:
        return v.lower()


class UsuarioAtualizar(Esquema):
    nome: str | None = Field(None, min_length=2, max_length=150)
    perfil: PerfilUsuario | None = None
    ativo: bool | None = Field(None, description="`false` desativa o usuário e revoga suas sessões.")


class RedefinirSenha(Esquema):
    nova_senha: Senha


class UsuarioResumo(Esquema):
    """Referência enxuta a um usuário (autoria em eventos, documentos e auditoria)."""

    id: uuid.UUID
    nome: str


class UsuarioLeitura(Esquema):
    id: uuid.UUID
    nome: str
    email: str
    perfil: PerfilUsuario
    ativo: bool
    ultimo_login_em: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "0b5d5c2e-1f0a-4b7e-9a0e-6f1c2d3e4f50",
                    "nome": "Ana Lima",
                    "email": "ana.lima@secretaria.gov.br",
                    "perfil": "ATENDENTE",
                    "ativo": True,
                    "ultimo_login_em": "2026-03-10T14:22:05Z",
                    "created_at": "2026-01-05T12:00:00Z",
                    "updated_at": "2026-03-10T14:22:05Z",
                }
            ]
        },
    )


class UsuarioFiltros(Esquema):
    q: str | None = Field(None, max_length=100, description="Busca por nome ou e-mail (contém).")
    perfil: PerfilUsuario | None = None
    ativo: bool | None = None
