import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import confirmar
from app.modules.auditoria import service as auditoria
from app.modules.eventos.model import Evento
from app.modules.eventos.schema import EventoCriar, EventoFiltros, RetificacaoCriar
from app.modules.mulheres import service as mulheres
from app.modules.servicos_mulheres.model import ServicoMulher
from app.modules.usuarios.model import Usuario
from app.shared.enums import AcaoAuditoria, TipoEvento
from app.shared.exceptions import NaoEncontrado, ValidacaoFalhou
from app.shared.pagination import Paginacao, paginar
from app.shared.utils import serializar_modelo, utcnow


async def _carregar(session: AsyncSession, evento_id: uuid.UUID) -> Evento | None:
    """Relê o evento (com autor e retificações) — evita lazy-load em contexto async."""
    return await session.scalar(
        select(Evento).where(Evento.id == evento_id).execution_options(populate_existing=True)
    )


async def obter(session: AsyncSession, evento_id: uuid.UUID) -> Evento:
    evento = await _carregar(session, evento_id)
    if evento is None:
        raise NaoEncontrado("Evento não encontrado.", code="EVENTO_NAO_ENCONTRADO")
    return evento


async def listar(session: AsyncSession, filtros: EventoFiltros, pag: Paginacao) -> tuple[list[Evento], int]:
    stmt = select(Evento)
    if filtros.mulher_id:
        stmt = stmt.where(Evento.mulher_id == filtros.mulher_id)
    if filtros.servico_mulher_id:
        stmt = stmt.where(Evento.servico_mulher_id == filtros.servico_mulher_id)
    if filtros.tipo:
        stmt = stmt.where(Evento.tipo == filtros.tipo)
    if filtros.de:
        stmt = stmt.where(Evento.ocorrido_em >= filtros.de)
    if filtros.ate:
        stmt = stmt.where(Evento.ocorrido_em <= filtros.ate)
    if filtros.registrado_por:
        stmt = stmt.where(Evento.registrado_por == filtros.registrado_por)
    stmt = stmt.order_by(Evento.ocorrido_em.desc(), Evento.registrado_em.desc(), Evento.id)
    return await paginar(session, stmt, pag)


async def contar_da_mulher(session: AsyncSession, mulher_id: uuid.UUID) -> int:
    return await session.scalar(select(func.count()).select_from(Evento).where(Evento.mulher_id == mulher_id)) or 0


async def validar_vinculo(session: AsyncSession, mulher_id: uuid.UUID, servico_mulher_id: uuid.UUID | None) -> None:
    if servico_mulher_id is None:
        return
    vinculo = await session.get(ServicoMulher, servico_mulher_id)
    if vinculo is None or vinculo.mulher_id != mulher_id:
        raise ValidacaoFalhou(
            "O vínculo informado não existe ou não pertence a esta mulher.",
            code="VINCULO_INVALIDO",
            details=[{"field": "servico_mulher_id", "issue": "não pertence à mulher"}],
        )


def registrar_interno(
    session: AsyncSession,
    *,
    mulher_id: uuid.UUID,
    tipo: TipoEvento,
    titulo: str,
    usuario_id: uuid.UUID,
    servico_mulher_id: uuid.UUID | None = None,
    descricao: str | None = None,
    ocorrido_em: datetime | None = None,
    corrige_evento_id: uuid.UUID | None = None,
    metadados: dict[str, Any] | None = None,
) -> Evento:
    """Cria um evento na transação corrente (sem commit/auditoria própria — o chamador audita a operação)."""
    evento = Evento(
        mulher_id=mulher_id,
        servico_mulher_id=servico_mulher_id,
        tipo=tipo,
        titulo=titulo,
        descricao=descricao,
        ocorrido_em=ocorrido_em or utcnow(),
        registrado_por=usuario_id,
        corrige_evento_id=corrige_evento_id,
        metadados=metadados,
    )
    session.add(evento)
    return evento


async def criar(session: AsyncSession, dados: EventoCriar, ator: Usuario) -> Evento:
    await mulheres.exigir_ativa(session, dados.mulher_id)
    await validar_vinculo(session, dados.mulher_id, dados.servico_mulher_id)
    evento = registrar_interno(
        session,
        mulher_id=dados.mulher_id,
        servico_mulher_id=dados.servico_mulher_id,
        tipo=dados.tipo,
        titulo=dados.titulo,
        descricao=dados.descricao,
        ocorrido_em=dados.ocorrido_em,
        usuario_id=ator.id,
        metadados=dados.metadados,
    )
    await session.flush()
    await auditoria.registrar(
        session,
        usuario_id=ator.id,
        acao=AcaoAuditoria.CREATE,
        entidade="evento",
        entidade_id=evento.id,
        mulher_id=evento.mulher_id,
        depois=serializar_modelo(evento),
    )
    await confirmar(session)
    return await obter(session, evento.id)


async def retificar(session: AsyncSession, evento_id: uuid.UUID, dados: RetificacaoCriar, ator: Usuario) -> Evento:
    original = await obter(session, evento_id)
    await mulheres.exigir_ativa(session, original.mulher_id)
    retificacao = registrar_interno(
        session,
        mulher_id=original.mulher_id,
        servico_mulher_id=original.servico_mulher_id,
        tipo=TipoEvento.RETIFICACAO,
        titulo=dados.titulo or f"Retificação: {original.titulo}"[:200],
        descricao=dados.descricao,
        ocorrido_em=dados.ocorrido_em,
        usuario_id=ator.id,
        corrige_evento_id=original.id,
    )
    await session.flush()
    await auditoria.registrar(
        session,
        usuario_id=ator.id,
        acao=AcaoAuditoria.CREATE,
        entidade="evento",
        entidade_id=retificacao.id,
        mulher_id=retificacao.mulher_id,
        depois=serializar_modelo(retificacao),
    )
    await confirmar(session)
    return await obter(session, retificacao.id)
