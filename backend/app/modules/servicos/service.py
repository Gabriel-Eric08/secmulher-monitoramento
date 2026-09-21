import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import confirmar
from app.modules.auditoria import service as auditoria
from app.modules.servicos.model import Servico
from app.modules.servicos.schema import ServicoAtualizar, ServicoCriar, ServicoFiltros
from app.modules.usuarios.model import Usuario
from app.shared.enums import AcaoAuditoria
from app.shared.exceptions import Conflito, NaoEncontrado
from app.shared.pagination import PaginacaoOrdenavel, ordenar, paginar
from app.shared.utils import serializar_modelo

_ORDENAVEIS = {"nome": Servico.nome, "categoria": Servico.categoria, "created_at": Servico.created_at}
_MSG_DUPLICADO = "Já existe um serviço com este nome."


async def listar(
    session: AsyncSession, filtros: ServicoFiltros, pag: PaginacaoOrdenavel
) -> tuple[list[Servico], int]:
    stmt = select(Servico)
    if filtros.q:
        stmt = stmt.where(Servico.nome.ilike(f"%{filtros.q}%"))
    if filtros.categoria:
        stmt = stmt.where(Servico.categoria == filtros.categoria)
    if filtros.ativo is not None:
        stmt = stmt.where(Servico.ativo == filtros.ativo)
    stmt = ordenar(stmt, pag.sort, _ORDENAVEIS, [Servico.nome.asc()], Servico.id)
    return await paginar(session, stmt, pag)


async def obter(session: AsyncSession, servico_id: uuid.UUID) -> Servico:
    servico = await session.get(Servico, servico_id)
    if servico is None:
        raise NaoEncontrado("Serviço não encontrado.", code="SERVICO_NAO_ENCONTRADO")
    return servico


async def _nome_em_uso(session: AsyncSession, nome: str, ignorar_id: uuid.UUID | None = None) -> bool:
    stmt = select(Servico.id).where(Servico.nome == nome)
    if ignorar_id:
        stmt = stmt.where(Servico.id != ignorar_id)
    return await session.scalar(stmt) is not None


async def criar(session: AsyncSession, dados: ServicoCriar, ator: Usuario) -> Servico:
    if await _nome_em_uso(session, dados.nome):
        raise Conflito(_MSG_DUPLICADO, code="SERVICO_DUPLICADO")
    servico = Servico(**dados.model_dump())
    session.add(servico)
    await session.flush()
    await auditoria.registrar(
        session,
        usuario_id=ator.id,
        acao=AcaoAuditoria.CREATE,
        entidade="servico",
        entidade_id=servico.id,
        depois=serializar_modelo(servico),
    )
    await confirmar(session, code="SERVICO_DUPLICADO", message=_MSG_DUPLICADO)
    return servico


async def atualizar(session: AsyncSession, servico_id: uuid.UUID, dados: ServicoAtualizar, ator: Usuario) -> Servico:
    servico = await obter(session, servico_id)
    campos = dados.model_dump(exclude_unset=True)
    if not campos:
        return servico
    if "nome" in campos and await _nome_em_uso(session, campos["nome"], servico.id):
        raise Conflito(_MSG_DUPLICADO, code="SERVICO_DUPLICADO")
    antes = serializar_modelo(servico)
    for chave, valor in campos.items():
        setattr(servico, chave, valor)
    await session.flush()
    await auditoria.registrar(
        session,
        usuario_id=ator.id,
        acao=AcaoAuditoria.UPDATE,
        entidade="servico",
        entidade_id=servico.id,
        antes=antes,
        depois=serializar_modelo(servico),
    )
    await confirmar(session, code="SERVICO_DUPLICADO", message=_MSG_DUPLICADO)
    return servico
