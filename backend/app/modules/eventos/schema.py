import uuid
from datetime import datetime, timedelta
from typing import Any

from pydantic import ConfigDict, Field, field_validator

from app.modules.mulheres.schema import MulherMinima
from app.modules.usuarios.schema import UsuarioResumo
from app.shared.enums import TIPOS_EVENTO_SISTEMA, TipoEvento
from app.shared.schemas import Esquema
from app.shared.utils import ensure_utc, utcnow

_TOLERANCIA_RELOGIO = timedelta(minutes=5)


def nao_futuro(v: datetime | None) -> datetime | None:
    if v is None:
        return None
    v = ensure_utc(v)
    if v > utcnow() + _TOLERANCIA_RELOGIO:
        raise ValueError("`ocorrido_em` não pode estar no futuro.")
    return v


class _EventoBase(Esquema):
    tipo: TipoEvento = Field(
        ...,
        description="Tipo do evento. `MUDANCA_STATUS`, `DOCUMENTO_ANEXADO` e `RETIFICACAO` são gerados pelo sistema "
        "e **não** podem ser criados aqui.",
        examples=["VISITA"],
    )
    titulo: str = Field(..., min_length=3, max_length=200, examples=["Visita domiciliar"])
    descricao: str | None = Field(None, max_length=10000, examples=["Visita realizada, sem intercorrências."])
    ocorrido_em: datetime | None = Field(
        None,
        description="Quando o fato **aconteceu** (pode ser retroativo, nunca futuro). Padrão: agora. "
        "Sem fuso é tratado como UTC.",
        examples=["2026-03-08T14:00:00Z"],
    )
    servico_mulher_id: uuid.UUID | None = Field(None, description="Vínculo relacionado (opcional).")
    metadados: dict[str, Any] | None = Field(None, description="Dados livres estruturados (opcional).")

    _v_ocorrido = field_validator("ocorrido_em")(nao_futuro)

    @field_validator("tipo")
    @classmethod
    def _tipo_permitido(cls, v: TipoEvento) -> TipoEvento:
        if v in TIPOS_EVENTO_SISTEMA:
            raise ValueError(f"O tipo {v.value} é gerado pelo sistema e não pode ser criado manualmente.")
        return v


class EventoCriar(_EventoBase):
    mulher_id: uuid.UUID = Field(..., description="Mulher a que o evento se refere.")


class EventoCriarAninhado(_EventoBase):
    """Corpo de `POST /mulheres/{mulher_id}/eventos` (a mulher vem da URL)."""


class RetificacaoCriar(Esquema):
    titulo: str | None = Field(None, min_length=3, max_length=200, description="Padrão: `Retificação: <título original>`.")
    descricao: str = Field(..., min_length=3, max_length=10000, description="O texto corrigido / a correção.")
    ocorrido_em: datetime | None = Field(None, description="Padrão: agora.")

    _v_ocorrido = field_validator("ocorrido_em")(nao_futuro)


class EventoLeitura(Esquema):
    id: uuid.UUID
    mulher_id: uuid.UUID
    mulher: MulherMinima = Field(..., description="Mulher a que o evento se refere (id e nome).")
    servico_mulher_id: uuid.UUID | None
    tipo: TipoEvento
    titulo: str
    descricao: str | None
    ocorrido_em: datetime = Field(..., description="Quando o fato aconteceu.")
    registrado_em: datetime = Field(..., description="Quando foi registrado no sistema (relógio do servidor).")
    registrado_por: UsuarioResumo = Field(..., validation_alias="autor")
    corrige_evento_id: uuid.UUID | None = Field(None, description="Preenchido em retificações: evento original.")
    retificado_por: list[uuid.UUID] = Field(
        default_factory=list,
        validation_alias="retificacoes",
        description="IDs das retificações que apontam para este evento.",
    )
    metadados: dict[str, Any] | None

    @field_validator("retificado_por", mode="before")
    @classmethod
    def _ids(cls, v: Any) -> Any:
        return [e.id if hasattr(e, "id") else e for e in v]

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
                    "mulher_id": "9d2e7f10-3a4b-4c5d-8e6f-1a2b3c4d5e6f",
                    "mulher": {"id": "9d2e7f10-3a4b-4c5d-8e6f-1a2b3c4d5e6f", "nome_completo": "Maria Souza da Silva", "nome_social": None},
                    "servico_mulher_id": "7e6d5c4b-3a21-4f0e-9d8c-b7a695847362",
                    "tipo": "MUDANCA_STATUS",
                    "titulo": "Status alterado: SOLICITADO → EM_ANALISE",
                    "descricao": "Documentação recebida.",
                    "ocorrido_em": "2026-03-05T13:00:00Z",
                    "registrado_em": "2026-03-05T13:00:01Z",
                    "registrado_por": {"id": "0b5d5c2e-1f0a-4b7e-9a0e-6f1c2d3e4f50", "nome": "Ana Lima"},
                    "corrige_evento_id": None,
                    "retificado_por": [],
                    "metadados": {"status_anterior": "SOLICITADO", "status_novo": "EM_ANALISE"},
                }
            ]
        },
    )


class EventoFiltros(Esquema):
    mulher_id: uuid.UUID | None = None
    servico_mulher_id: uuid.UUID | None = None
    tipo: TipoEvento | None = None
    de: datetime | None = Field(None, description="`ocorrido_em` a partir de (inclusive).")
    ate: datetime | None = Field(None, description="`ocorrido_em` até (inclusive).")
    registrado_por: uuid.UUID | None = None


class EventoFiltrosAninhado(Esquema):
    """Filtros da linha do tempo de uma mulher (`mulher_id` vem da URL)."""

    servico_mulher_id: uuid.UUID | None = None
    tipo: TipoEvento | None = None
    de: datetime | None = Field(None, description="`ocorrido_em` a partir de (inclusive).")
    ate: datetime | None = Field(None, description="`ocorrido_em` até (inclusive).")
