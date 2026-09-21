import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import confirmar
from app.core.security import (
    criar_access_token,
    criar_refresh_token,
    decodificar_token,
    hash_senha,
    verificar_senha,
)
from app.modules.auditoria import service as auditoria
from app.modules.auth import repository
from app.modules.auth.model import RefreshToken
from app.modules.auth.schema import TokenPar
from app.modules.usuarios.model import Usuario
from app.shared.enums import AcaoAuditoria
from app.shared.exceptions import Conflito, ContaBloqueada, NaoAutenticado
from app.shared.utils import ensure_utc, utcnow


async def _emitir_par(session: AsyncSession, usuario: Usuario) -> TokenPar:
    access, expires_in = criar_access_token(usuario.id, usuario.perfil.value)
    refresh, jti, expira_em = criar_refresh_token(usuario.id)
    session.add(RefreshToken(id=jti, usuario_id=usuario.id, expira_em=expira_em))
    return TokenPar(access_token=access, refresh_token=refresh, token_type="bearer", expires_in=expires_in)


async def login(session: AsyncSession, email: str, senha: str) -> TokenPar:
    settings = get_settings()
    usuario = await session.scalar(select(Usuario).where(Usuario.email == email))
    agora = utcnow()

    if usuario and usuario.bloqueado_ate and ensure_utc(usuario.bloqueado_ate) > agora:
        raise ContaBloqueada()

    if not verificar_senha(senha, usuario.senha_hash if usuario else None) or not usuario or not usuario.ativo:
        if usuario:
            usuario.tentativas_falhas += 1
            if usuario.tentativas_falhas >= settings.login_max_tentativas:
                usuario.bloqueado_ate = agora + timedelta(minutes=settings.login_bloqueio_minutos)
                usuario.tentativas_falhas = 0
        await auditoria.registrar(
            session,
            usuario_id=usuario.id if usuario else None,
            acao=AcaoAuditoria.LOGIN_FAILED,
            entidade="usuario",
            entidade_id=usuario.id if usuario else None,
            depois={"email": email},
        )
        await session.commit()  # persiste contador/auditoria antes de responder o erro
        raise NaoAutenticado("E-mail ou senha inválidos.", code="CREDENCIAIS_INVALIDAS")

    usuario.tentativas_falhas = 0
    usuario.bloqueado_ate = None
    usuario.ultimo_login_em = agora
    par = await _emitir_par(session, usuario)
    await auditoria.registrar(
        session, usuario_id=usuario.id, acao=AcaoAuditoria.LOGIN, entidade="usuario", entidade_id=usuario.id
    )
    await session.commit()
    return par


async def _carregar_refresh(session: AsyncSession, token: str) -> tuple[RefreshToken, uuid.UUID]:
    payload = decodificar_token(token, "refresh")
    try:
        jti = uuid.UUID(payload["jti"])
        usuario_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise NaoAutenticado("Token inválido.", code="TOKEN_INVALIDO") from exc
    registro = await session.get(RefreshToken, jti)
    if registro is None or registro.usuario_id != usuario_id:
        raise NaoAutenticado("Token inválido.", code="TOKEN_INVALIDO")
    return registro, usuario_id


async def refresh(session: AsyncSession, refresh_token: str) -> TokenPar:
    registro, usuario_id = await _carregar_refresh(session, refresh_token)
    if registro.revogado_em is not None:
        # Reuso de token já rotacionado/revogado: derruba todas as sessões do usuário.
        await repository.revogar_todos_do_usuario(session, usuario_id)
        await session.commit()
        raise NaoAutenticado("Token inválido.", code="TOKEN_INVALIDO")
    usuario = await session.get(Usuario, usuario_id)
    if usuario is None or not usuario.ativo:
        raise NaoAutenticado("Usuário inexistente ou inativo.", code="USUARIO_INATIVO")
    registro.revogado_em = utcnow()
    par = await _emitir_par(session, usuario)
    await session.commit()
    return par


async def logout(session: AsyncSession, usuario: Usuario, refresh_token: str) -> None:
    try:
        registro, usuario_id = await _carregar_refresh(session, refresh_token)
    except NaoAutenticado:
        registro, usuario_id = None, None  # idempotente: token inválido/expirado = já deslogado
    if registro is not None and usuario_id == usuario.id and registro.revogado_em is None:
        registro.revogado_em = utcnow()
    await auditoria.registrar(
        session, usuario_id=usuario.id, acao=AcaoAuditoria.LOGOUT, entidade="usuario", entidade_id=usuario.id
    )
    await session.commit()


async def alterar_senha(session: AsyncSession, usuario: Usuario, senha_atual: str, nova_senha: str) -> None:
    if not verificar_senha(senha_atual, usuario.senha_hash):
        raise Conflito("A senha atual está incorreta.", code="SENHA_ATUAL_INCORRETA")
    usuario.senha_hash = hash_senha(nova_senha)
    await repository.revogar_todos_do_usuario(session, usuario.id)
    await auditoria.registrar(
        session,
        usuario_id=usuario.id,
        acao=AcaoAuditoria.UPDATE,
        entidade="usuario",
        entidade_id=usuario.id,
        depois={"senha_alterada": True},
    )
    await confirmar(session)
