import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import AdminOuGestor, SessionDep, UsuarioLogado
from app.modules.servicos import service
from app.modules.servicos.schema import ServicoAtualizar, ServicoCriar, ServicoFiltros, ServicoLeitura
from app.shared.pagination import Pagina, PaginacaoOrdenavel, montar_pagina
from app.shared.schemas import erros

router = APIRouter(prefix="/servicos", tags=["Serviços"])


@router.get(
    "",
    response_model=Pagina[ServicoLeitura],
    operation_id="servicos_listar",
    summary="Listar serviços do catálogo",
    description="**Permissão:** qualquer usuário autenticado.\n\nOrdenação (`sort`): `nome` (padrão), `categoria`, `created_at`.",
    responses=erros(401, 422),
)
async def listar(
    session: SessionDep,
    _: UsuarioLogado,
    filtros: Annotated[ServicoFiltros, Query()],
    pag: Annotated[PaginacaoOrdenavel, Depends()],
):
    items, total = await service.listar(session, filtros, pag)
    return montar_pagina(items, total, pag)


@router.post(
    "",
    response_model=ServicoLeitura,
    status_code=status.HTTP_201_CREATED,
    operation_id="servicos_criar",
    summary="Cadastrar serviço no catálogo",
    description="**Permissão:** ADMIN, GESTOR.\n\nErros de negócio: `409 SERVICO_DUPLICADO`.",
    responses=erros(401, 403, 409, 422),
)
async def criar(dados: ServicoCriar, session: SessionDep, ator: AdminOuGestor):
    return await service.criar(session, dados, ator)


@router.get(
    "/{servico_id}",
    response_model=ServicoLeitura,
    operation_id="servicos_obter",
    summary="Detalhar serviço",
    description="**Permissão:** qualquer usuário autenticado.",
    responses=erros(401, 404, 422),
)
async def obter(servico_id: uuid.UUID, session: SessionDep, _: UsuarioLogado):
    return await service.obter(session, servico_id)


@router.patch(
    "/{servico_id}",
    response_model=ServicoLeitura,
    operation_id="servicos_atualizar",
    summary="Atualizar, ativar ou inativar serviço",
    description="Não há exclusão: serviços já usados em vínculos são **inativados** (`ativo=false`), "
    "o que impede novos vínculos mas preserva o histórico.\n\n**Permissão:** ADMIN, GESTOR.",
    responses=erros(401, 403, 404, 409, 422),
)
async def atualizar(servico_id: uuid.UUID, dados: ServicoAtualizar, session: SessionDep, ator: AdminOuGestor):
    return await service.atualizar(session, servico_id, dados, ator)
