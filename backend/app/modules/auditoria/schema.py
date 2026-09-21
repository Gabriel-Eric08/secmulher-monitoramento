import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.modules.usuarios.schema import UsuarioResumo
from app.shared.enums import AcaoAuditoria
from app.shared.schemas import Esquema


class AuditoriaItemLista(Esquema):
    id: uuid.UUID
    usuario: UsuarioResumo | None = Field(None, description="Nulo em falhas de login de e-mail inexistente.")
    acao: AcaoAuditoria
    entidade: str = Field(..., description="Nome da entidade afetada.", examples=["mulher"])
    entidade_id: uuid.UUID | None
    mulher_id: uuid.UUID | None = Field(None, description="Mulher relacionada (para filtrar tudo de uma mulher).")
    ip: str | None
    request_id: str | None
    created_at: datetime


class AuditoriaLeitura(AuditoriaItemLista):
    antes: dict[str, Any] | None = Field(None, description="Estado do registro antes da mudança.")
    depois: dict[str, Any] | None = Field(None, description="Estado do registro depois da mudança.")
    user_agent: str | None


class AuditoriaFiltros(Esquema):
    usuario_id: uuid.UUID | None = None
    acao: AcaoAuditoria | None = None
    entidade: str | None = Field(None, max_length=50, examples=["servico_mulher"])
    entidade_id: uuid.UUID | None = None
    mulher_id: uuid.UUID | None = None
    de: datetime | None = Field(None, description="Início do período (inclusive), ISO-8601.")
    ate: datetime | None = Field(None, description="Fim do período (inclusive), ISO-8601.")
