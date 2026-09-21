import uuid
from typing import Any

from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.usuarios.model import Usuario
from app.modules.usuarios.schema import UsuarioFiltros


async def obter(session: AsyncSession, usuario_id: uuid.UUID) -> Usuario | None:
    return await session.get(Usuario, usuario_id)


async def obter_por_email(session: AsyncSession, email: str) -> Usuario | None:
    return await session.scalar(select(Usuario).where(Usuario.email == email))


def consulta(filtros: UsuarioFiltros) -> Select[Any]:
    stmt = select(Usuario)
    if filtros.q:
        termo = f"%{filtros.q}%"
        stmt = stmt.where(or_(Usuario.nome.ilike(termo), Usuario.email.ilike(termo)))
    if filtros.perfil:
        stmt = stmt.where(Usuario.perfil == filtros.perfil)
    if filtros.ativo is not None:
        stmt = stmt.where(Usuario.ativo == filtros.ativo)
    return stmt
