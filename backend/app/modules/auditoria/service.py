import uuid
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import obter_contexto
from app.modules.auditoria.model import Auditoria
from app.modules.auditoria.schema import AuditoriaFiltros
from app.shared.enums import AcaoAuditoria
from app.shared.exceptions import NaoEncontrado
from app.shared.pagination import PaginacaoOrdenavel, ordenar, paginar


async def registrar(
    session: AsyncSession,
    *,
    usuario_id: uuid.UUID | None,
    acao: AcaoAuditoria,
    entidade: str,
    entidade_id: uuid.UUID | None = None,
    mulher_id: uuid.UUID | None = None,
    antes: dict[str, Any] | None = None,
    depois: dict[str, Any] | None = None,
) -> Auditoria:
    """Grava a auditoria **na mesma transação** da mutação (falha aqui aborta a operação)."""
    ctx = obter_contexto()
    registro = Auditoria(
        usuario_id=usuario_id,
        acao=acao,
        entidade=entidade,
        entidade_id=entidade_id,
        mulher_id=mulher_id,
        antes=antes,
        depois=depois,
        ip=ctx["ip"],
        user_agent=ctx["user_agent"],
        request_id=ctx["request_id"],
    )
    session.add(registro)
    await session.flush()
    return registro


def _filtrar(stmt: Select[Any], f: AuditoriaFiltros) -> Select[Any]:
    if f.usuario_id:
        stmt = stmt.where(Auditoria.usuario_id == f.usuario_id)
    if f.acao:
        stmt = stmt.where(Auditoria.acao == f.acao)
    if f.entidade:
        stmt = stmt.where(Auditoria.entidade == f.entidade)
    if f.entidade_id:
        stmt = stmt.where(Auditoria.entidade_id == f.entidade_id)
    if f.mulher_id:
        stmt = stmt.where(Auditoria.mulher_id == f.mulher_id)
    if f.de:
        stmt = stmt.where(Auditoria.created_at >= f.de)
    if f.ate:
        stmt = stmt.where(Auditoria.created_at <= f.ate)
    return stmt


_ORDENAVEIS = {"created_at": Auditoria.created_at, "acao": Auditoria.acao, "entidade": Auditoria.entidade}


async def listar(
    session: AsyncSession, filtros: AuditoriaFiltros, pag: PaginacaoOrdenavel
) -> tuple[list[Auditoria], int]:
    stmt = _filtrar(select(Auditoria), filtros)
    stmt = ordenar(stmt, pag.sort, _ORDENAVEIS, [Auditoria.created_at.desc()], Auditoria.id)
    return await paginar(session, stmt, pag)


async def obter(session: AsyncSession, auditoria_id: uuid.UUID) -> Auditoria:
    registro = await session.get(Auditoria, auditoria_id)
    if registro is None:
        raise NaoEncontrado("Registro de auditoria não encontrado.", code="AUDITORIA_NAO_ENCONTRADA")
    return registro


async def trilha_entidade(
    session: AsyncSession, entidade: str, entidade_id: uuid.UUID, pag: PaginacaoOrdenavel
) -> tuple[list[Auditoria], int]:
    stmt = select(Auditoria).where(Auditoria.entidade == entidade, Auditoria.entidade_id == entidade_id)
    stmt = ordenar(stmt, pag.sort, _ORDENAVEIS, [Auditoria.created_at.desc()], Auditoria.id)
    return await paginar(session, stmt, pag)
