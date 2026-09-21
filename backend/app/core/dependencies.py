import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.core.security import decodificar_token
from app.modules.usuarios.model import Usuario
from app.shared.enums import PerfilUsuario
from app.shared.exceptions import AcessoNegado, NaoAutenticado

_bearer = HTTPBearer(
    scheme_name="BearerAuth",
    auto_error=False,
    bearerFormat="JWT",
    description="Token de acesso obtido em `POST /api/v1/auth/login`. Envie `Authorization: Bearer <access_token>`.",
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Unidade de trabalho por requisição. O `service` decide o commit."""
    async with SessionLocal() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    credenciais: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: SessionDep,
) -> Usuario:
    if credenciais is None:
        raise NaoAutenticado()
    payload = decodificar_token(credenciais.credentials, "access")
    try:
        usuario_id = uuid.UUID(payload["sub"])
    except ValueError as exc:
        raise NaoAutenticado("Token inválido.", code="TOKEN_INVALIDO") from exc
    usuario = await session.get(Usuario, usuario_id)
    if usuario is None or not usuario.ativo:
        raise NaoAutenticado("Usuário inexistente ou inativo.", code="USUARIO_INATIVO")
    return usuario


def require_perfil(*perfis: PerfilUsuario) -> Callable[..., Awaitable[Usuario]]:
    """Dependência que exige autenticação e um dos perfis informados; devolve o usuário."""

    async def _dep(usuario: Annotated[Usuario, Depends(get_current_user)]) -> Usuario:
        if usuario.perfil not in perfis:
            raise AcessoNegado()
        return usuario

    return _dep


P = PerfilUsuario

# Aliases de permissão (ver matriz em .claude/backend.md §6)
UsuarioLogado = Annotated[Usuario, Depends(get_current_user)]
SoAdmin = Annotated[Usuario, Depends(require_perfil(P.ADMIN))]
AdminOuGestor = Annotated[Usuario, Depends(require_perfil(P.ADMIN, P.GESTOR))]
Escritor = Annotated[Usuario, Depends(require_perfil(P.ADMIN, P.GESTOR, P.ATENDENTE))]
LeitorAuditoria = Annotated[Usuario, Depends(require_perfil(P.ADMIN, P.GESTOR, P.AUDITOR))]
