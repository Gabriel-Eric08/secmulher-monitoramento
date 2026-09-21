import uuid
from datetime import datetime

from pydantic import ConfigDict, Field

from app.shared.schemas import Esquema


class ServicoCriar(Esquema):
    nome: str = Field(..., min_length=2, max_length=150, examples=["Acompanhamento psicológico"])
    descricao: str | None = Field(None, max_length=5000, examples=["Atendimento psicológico individual."])
    categoria: str | None = Field(None, max_length=100, examples=["Saúde"])


class ServicoAtualizar(Esquema):
    nome: str | None = Field(None, min_length=2, max_length=150)
    descricao: str | None = Field(None, max_length=5000)
    categoria: str | None = Field(None, max_length=100)
    ativo: bool | None = Field(None, description="`false` impede novos vínculos com este serviço.")


class ServicoResumo(Esquema):
    id: uuid.UUID
    nome: str
    categoria: str | None = None


class ServicoLeitura(Esquema):
    id: uuid.UUID
    nome: str
    descricao: str | None
    categoria: str | None
    ativo: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "5c1f0a7e-2d3b-4c8e-9b1a-7e6d5c4b3a21",
                    "nome": "Acompanhamento psicológico",
                    "descricao": "Atendimento psicológico individual.",
                    "categoria": "Saúde",
                    "ativo": True,
                    "created_at": "2026-01-05T12:00:00Z",
                    "updated_at": "2026-01-05T12:00:00Z",
                }
            ]
        },
    )


class ServicoFiltros(Esquema):
    q: str | None = Field(None, max_length=100, description="Busca por nome (contém).")
    categoria: str | None = Field(None, max_length=100)
    ativo: bool | None = None
