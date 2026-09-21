import uuid
from typing import Any

from sqlalchemy import Select, and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.mulheres.model import Mulher
from app.modules.mulheres.schema import MulherFiltros
from app.modules.servicos_mulheres.model import ServicoMulher
from app.shared.utils import normalizar_texto, so_digitos


async def obter(session: AsyncSession, mulher_id: uuid.UUID) -> Mulher | None:
    return await session.get(Mulher, mulher_id)


async def obter_por_cpf(session: AsyncSession, cpf: str) -> Mulher | None:
    return await session.scalar(select(Mulher).where(Mulher.cpf == cpf))


def consulta(filtros: MulherFiltros, incluir_excluidas: bool) -> Select[Any]:
    stmt = select(Mulher)
    if not incluir_excluidas:
        stmt = stmt.where(Mulher.deleted_at.is_(None))
    if filtros.q:
        digitos = so_digitos(filtros.q)
        condicoes = [Mulher.nome_busca.contains(normalizar_texto(filtros.q))]
        if len(digitos) >= 3:
            condicoes.append(Mulher.cpf.contains(digitos))
        stmt = stmt.where(or_(*condicoes))
    if filtros.cpf:
        stmt = stmt.where(Mulher.cpf == so_digitos(filtros.cpf))
    if filtros.cidade:
        stmt = stmt.where(Mulher.cidade.ilike(filtros.cidade))
    if filtros.servico_id or filtros.status:
        cond = [ServicoMulher.mulher_id == Mulher.id]
        if filtros.servico_id:
            cond.append(ServicoMulher.servico_id == filtros.servico_id)
        if filtros.status:
            cond.append(ServicoMulher.status == filtros.status)
        stmt = stmt.where(exists().where(and_(*cond)))
    return stmt
