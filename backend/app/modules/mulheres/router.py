import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.dependencies import AdminOuGestor, Escritor, SessionDep, UsuarioLogado
from app.modules.mulheres import resumo, service
from app.modules.mulheres.schema import (
    MulherAtualizar,
    MulherCriar,
    MulherFiltros,
    MulherItemLista,
    MulherLeitura,
)
from app.shared.pagination import Pagina, PaginacaoOrdenavel, montar_pagina
from app.shared.schemas import erros

router = APIRouter(prefix="/mulheres", tags=["Mulheres"])

_LGPD = "Dado pessoal sensível: a leitura do detalhe é registrada na auditoria (`READ_SENSITIVE`)."


@router.get(
    "",
    response_model=Pagina[MulherItemLista],
    operation_id="mulheres_listar",
    summary="Listar / buscar mulheres",
    description="Itens com CPF e telefone **mascarados**. `q` busca por nome/nome social (sem acento) ou CPF. "
    "Cadastros excluídos logicamente só aparecem com `incluir_excluidas=true` (ADMIN/GESTOR).\n\n"
    "Ordenação (`sort`): `nome_completo` (padrão), `cidade`, `created_at`.\n\n**Permissão:** qualquer usuário autenticado.",
    responses=erros(401, 403, 422),
)
async def listar(
    session: SessionDep,
    ator: UsuarioLogado,
    filtros: Annotated[MulherFiltros, Query()],
    pag: Annotated[PaginacaoOrdenavel, Depends()],
):
    items, total = await service.listar(session, filtros, pag, ator)
    return montar_pagina(items, total, pag)


@router.post(
    "",
    response_model=MulherLeitura,
    status_code=status.HTTP_201_CREATED,
    operation_id="mulheres_criar",
    summary="Cadastrar mulher",
    description="CPF (opcional) é validado e armazenado só com dígitos.\n\n**Permissão:** ADMIN, GESTOR, ATENDENTE.\n\n"
    "Erros de negócio: `409 CPF_DUPLICADO`.",
    responses=erros(401, 403, 409, 422),
)
async def criar(dados: MulherCriar, response: Response, session: SessionDep, ator: Escritor):
    mulher = await service.criar(session, dados, ator)
    response.headers["Location"] = f"/api/v1/mulheres/{mulher.id}"
    return mulher


@router.get(
    "/{mulher_id}",
    response_model=MulherLeitura,
    operation_id="mulheres_obter",
    summary="Detalhar cadastro completo",
    description=f"{_LGPD} Cadastro excluído retorna `404` (ADMIN/GESTOR podem usar `incluir_excluida=true`).\n\n"
    "**Permissão:** qualquer usuário autenticado.",
    responses=erros(401, 404, 422),
)
async def obter(
    mulher_id: uuid.UUID,
    session: SessionDep,
    ator: UsuarioLogado,
    incluir_excluida: Annotated[bool, Query(description="Só tem efeito para ADMIN/GESTOR.")] = False,
):
    return await service.obter_para_leitura(session, mulher_id, ator, incluir_excluida=incluir_excluida)


@router.patch(
    "/{mulher_id}",
    response_model=MulherLeitura,
    operation_id="mulheres_atualizar",
    summary="Atualizar cadastro (parcial)",
    description="Envie só os campos a alterar; `null` limpa um campo opcional. A auditoria guarda `antes` e `depois`.\n\n"
    "**Permissão:** ADMIN, GESTOR, ATENDENTE.\n\nErros de negócio: `409 CPF_DUPLICADO`, `409 MULHER_EXCLUIDA`.",
    responses=erros(401, 403, 404, 409, 422),
)
async def atualizar(mulher_id: uuid.UUID, dados: MulherAtualizar, session: SessionDep, ator: Escritor):
    return await service.atualizar(session, mulher_id, dados, ator)


@router.delete(
    "/{mulher_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="mulheres_excluir",
    summary="Excluir cadastro (exclusão lógica)",
    description="Nada é apagado fisicamente: vínculos, eventos e documentos permanecem. O cadastro some das listagens "
    "e não aceita novos vínculos/eventos/documentos. Exige `motivo`.\n\n**Permissão:** ADMIN, GESTOR.",
    responses=erros(401, 403, 404, 422),
)
async def excluir(
    mulher_id: uuid.UUID,
    session: SessionDep,
    ator: AdminOuGestor,
    motivo: Annotated[str, Query(min_length=3, max_length=500, description="Justificativa da exclusão.")],
) -> Response:
    await service.excluir(session, mulher_id, motivo, ator)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{mulher_id}/restaurar",
    response_model=MulherLeitura,
    operation_id="mulheres_restaurar",
    summary="Restaurar cadastro excluído",
    description="**Permissão:** ADMIN, GESTOR.\n\nErro de negócio: `409 MULHER_NAO_EXCLUIDA`.",
    responses=erros(401, 403, 404, 409, 422),
)
async def restaurar(mulher_id: uuid.UUID, session: SessionDep, ator: AdminOuGestor):
    return await service.restaurar(session, mulher_id, ator)


@router.get(
    "/{mulher_id}/resumo",
    response_model=resumo.MulherResumo,
    operation_id="mulheres_resumo",
    summary="Visão consolidada da mulher",
    description=f"Cadastro + vínculos com **status atual** + últimos eventos + contadores, em uma chamada. {_LGPD}\n\n"
    "**Permissão:** qualquer usuário autenticado.",
    responses=erros(401, 404, 422),
)
async def obter_resumo(
    mulher_id: uuid.UUID,
    session: SessionDep,
    ator: UsuarioLogado,
    eventos: Annotated[int, Query(ge=1, le=50, description="Quantos eventos recentes incluir.")] = 10,
):
    return await resumo.montar(session, mulher_id, ator, eventos)
