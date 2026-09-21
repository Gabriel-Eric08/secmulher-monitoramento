from fastapi import APIRouter, Response, status

from app.core.dependencies import SessionDep, UsuarioLogado
from app.modules.auth import service
from app.modules.auth.schema import AlterarSenhaEntrada, LoginEntrada, RefreshEntrada, TokenPar
from app.modules.usuarios.schema import UsuarioLeitura
from app.shared.schemas import erros

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post(
    "/login",
    response_model=TokenPar,
    operation_id="auth_login",
    summary="Autenticar (e-mail e senha)",
    description="Devolve `access_token` (curto) e `refresh_token` (longo, uso único).\n\n"
    "Após **5 falhas seguidas** a conta é bloqueada por 15 minutos (`423 CONTA_BLOQUEADA`). "
    "Falhas e sucessos são auditados.\n\n**Permissão:** pública.",
    responses=erros(401, 422, 423),
)
async def login(dados: LoginEntrada, session: SessionDep):
    return await service.login(session, dados.email, dados.senha)


@router.post(
    "/refresh",
    response_model=TokenPar,
    operation_id="auth_refresh",
    summary="Renovar tokens",
    description="Troca um refresh token válido por um **novo par** (o refresh usado é revogado — rotação). "
    "Reapresentar um refresh já usado revoga todas as sessões do usuário.\n\n**Permissão:** pública.",
    responses=erros(401, 422),
)
async def refresh(dados: RefreshEntrada, session: SessionDep):
    return await service.refresh(session, dados.refresh_token)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="auth_logout",
    summary="Encerrar sessão",
    description="Revoga o refresh token informado. Idempotente.\n\n**Permissão:** qualquer usuário autenticado.",
    responses=erros(401, 422),
)
async def logout(dados: RefreshEntrada, session: SessionDep, usuario: UsuarioLogado) -> Response:
    await service.logout(session, usuario, dados.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me",
    response_model=UsuarioLeitura,
    operation_id="auth_me",
    summary="Usuário autenticado",
    description="Dados e perfil do usuário dono do token.\n\n**Permissão:** qualquer usuário autenticado.",
    responses=erros(401),
)
async def me(usuario: UsuarioLogado):
    return usuario


@router.post(
    "/alterar-senha",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="auth_alterar_senha",
    summary="Alterar a própria senha",
    description="Exige a senha atual. Revoga todos os refresh tokens do usuário.\n\n"
    "**Permissão:** qualquer usuário autenticado.",
    responses=erros(401, 409, 422),
)
async def alterar_senha(dados: AlterarSenhaEntrada, session: SessionDep, usuario: UsuarioLogado) -> Response:
    await service.alterar_senha(session, usuario, dados.senha_atual, dados.nova_senha)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
