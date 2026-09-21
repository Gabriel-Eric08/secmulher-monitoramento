import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import LeitorAuditoria, SessionDep
from app.modules.auditoria import service
from app.modules.auditoria.schema import AuditoriaFiltros, AuditoriaItemLista, AuditoriaLeitura
from app.shared.pagination import Pagina, PaginacaoOrdenavel, montar_pagina
from app.shared.schemas import erros

router = APIRouter(prefix="/auditoria", tags=["Auditoria"])

_ORD = "Ordenação (`sort`): `created_at` (padrão `-created_at`), `acao`, `entidade`."


@router.get(
    "",
    response_model=Pagina[AuditoriaItemLista],
    operation_id="auditoria_listar",
    summary="Listar registros de auditoria",
    description="Log transversal e **somente leitura** de todas as mutações (e leituras sensíveis).\n\n"
    f"**Permissão:** ADMIN, GESTOR, AUDITOR.\n\n{_ORD}",
    responses=erros(401, 403, 422),
)
async def listar(
    session: SessionDep,
    _: LeitorAuditoria,
    filtros: Annotated[AuditoriaFiltros, Query()],
    pag: Annotated[PaginacaoOrdenavel, Depends()],
):
    items, total = await service.listar(session, filtros, pag)
    return montar_pagina(items, total, pag)


@router.get(
    "/entidades/{entidade}/{entidade_id}",
    response_model=Pagina[AuditoriaItemLista],
    operation_id="auditoria_trilha_entidade",
    summary="Trilha de auditoria de um registro",
    description="Toda a história de auditoria de uma entidade específica (ex.: `mulher`, `servico_mulher`, `documento`).\n\n"
    f"**Permissão:** ADMIN, GESTOR, AUDITOR.\n\n{_ORD}",
    responses=erros(401, 403, 422),
)
async def trilha(
    entidade: str,
    entidade_id: uuid.UUID,
    session: SessionDep,
    _: LeitorAuditoria,
    pag: Annotated[PaginacaoOrdenavel, Depends()],
):
    items, total = await service.trilha_entidade(session, entidade, entidade_id, pag)
    return montar_pagina(items, total, pag)


@router.get(
    "/{auditoria_id}",
    response_model=AuditoriaLeitura,
    operation_id="auditoria_obter",
    summary="Detalhar registro de auditoria",
    description="Inclui `antes` e `depois` (snapshots JSON). Senhas e tokens nunca são registrados.\n\n"
    "**Permissão:** ADMIN, GESTOR, AUDITOR.",
    responses=erros(401, 403, 404, 422),
)
async def obter(auditoria_id: uuid.UUID, session: SessionDep, _: LeitorAuditoria):
    return await service.obter(session, auditoria_id)
