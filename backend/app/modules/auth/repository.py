import uuid

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.model import RefreshToken
from app.shared.utils import utcnow


async def revogar_todos_do_usuario(session: AsyncSession, usuario_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.usuario_id == usuario_id, RefreshToken.revogado_em.is_(None))
        .values(revogado_em=utcnow())
    )
