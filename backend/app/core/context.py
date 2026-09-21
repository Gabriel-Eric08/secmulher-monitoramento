"""Contexto da requisição (request_id, ip, user-agent), lido pela auditoria e pelos logs."""

from contextvars import ContextVar
from typing import TypedDict


class ContextoRequisicao(TypedDict):
    request_id: str | None
    ip: str | None
    user_agent: str | None


_vazio: ContextoRequisicao = {"request_id": None, "ip": None, "user_agent": None}
_contexto: ContextVar[ContextoRequisicao] = ContextVar("contexto_requisicao", default=_vazio)


def definir_contexto(ctx: ContextoRequisicao) -> None:
    _contexto.set(ctx)


def obter_contexto() -> ContextoRequisicao:
    return _contexto.get()
