import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.dependencies import SessionDep, SoAdmin
from app.modules.usuarios import service
from app.modules.usuarios.schema import (
    RedefinirSenha,
    UsuarioAtualizar,
    UsuarioCriar,
    UsuarioFiltros,
    UsuarioLeitura,
)
from app.shared.pagination import Pagina, PaginacaoOrdenavel, montar_pagina
from app.shared.schemas import erros

router = APIRouter(prefix="/usuarios", tags=["Usuários"])


@router.get(
    "",
    response_model=Pagina[UsuarioLeitura],
    operation_id="usuarios_listar",
    summary="Listar usuários",
    description="**Permissão:** ADMIN.\n\nOrdenação (`sort`): `nome` (padrão), `email`, `created_at`.",
    responses=erros(401, 403, 422),
)
async def listar(
    session: SessionDep,
    _: SoAdmin,
    filtros: Annotated[UsuarioFiltros, Query()],
    pag: Annotated[PaginacaoOrdenavel, Depends()],
):
    items, total = await service.listar(session, filtros, pag)
    return montar_pagina(items, total, pag)


@router.post(
    "",
    response_model=UsuarioLeitura,
    status_code=status.HTTP_201_CREATED,
    operation_id="usuarios_criar",
    summary="Criar usuário",
    description="Cria um usuário com senha inicial. **Permissão:** ADMIN.\n\n"
    "Erros de negócio: `409 EMAIL_DUPLICADO`.",
    responses=erros(401, 403, 409, 422),
)
async def criar(dados: UsuarioCriar, session: SessionDep, ator: SoAdmin):
    return await service.criar(session, dados, ator)


@router.get(
    "/{usuario_id}",
    response_model=UsuarioLeitura,
    operation_id="usuarios_obter",
    summary="Detalhar usuário",
    description="**Permissão:** ADMIN.",
    responses=erros(401, 403, 404, 422),
)
async def obter(usuario_id: uuid.UUID, session: SessionDep, _: SoAdmin):
    return await service.obter(session, usuario_id)


@router.patch(
    "/{usuario_id}",
    response_model=UsuarioLeitura,
    operation_id="usuarios_atualizar",
    summary="Atualizar usuário (nome, perfil, ativo)",
    description="Não há exclusão de usuário: para preservar a auditoria, desative com `ativo=false` "
    "(isso revoga as sessões dele). O admin não pode desativar a si mesmo nem mudar o próprio perfil.\n\n"
    "**Permissão:** ADMIN.",
    responses=erros(401, 403, 404, 409, 422),
)
async def atualizar(usuario_id: uuid.UUID, dados: UsuarioAtualizar, session: SessionDep, ator: SoAdmin):
    return await service.atualizar(session, usuario_id, dados, ator)


@router.post(
    "/{usuario_id}/redefinir-senha",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="usuarios_redefinir_senha",
    summary="Redefinir a senha de um usuário",
    description="Define nova senha, desbloqueia a conta e revoga as sessões. **Permissão:** ADMIN.",
    responses=erros(401, 403, 404, 422),
)
async def redefinir_senha(
    usuario_id: uuid.UUID, dados: RedefinirSenha, session: SessionDep, ator: SoAdmin
) -> Response:
    await service.redefinir_senha(session, usuario_id, dados.nova_senha, ator)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
