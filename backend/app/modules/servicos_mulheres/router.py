import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import Escritor, SessionDep, UsuarioLogado
from app.modules.eventos import service as eventos
from app.modules.eventos.schema import EventoFiltros, EventoLeitura
from app.modules.servicos_mulheres import service
from app.modules.servicos_mulheres.schema import (
    TransicaoCriar,
    TransicoesPermitidas,
    VinculoAtualizar,
    VinculoFiltros,
    VinculoLeitura,
)
from app.shared.pagination import Pagina, Paginacao, PaginacaoOrdenavel, montar_pagina
from app.shared.schemas import erros


router = APIRouter(prefix="/servicos-mulheres", tags=["Serviços das Mulheres"])


@router.get(
    "",
    response_model=Pagina[VinculoLeitura],
    operation_id="servicos_mulheres_listar",
    summary="Listar vínculos mulher↔serviço (global)",
    description="Cada item traz o **status atual**. Para criar um vínculo use `POST /mulheres/{mulher_id}/servicos`.\n\n"
    "Ordenação (`sort`): `created_at` (padrão, desc), `data_inicio`, `status`, `updated_at`.\n\n"
    "**Permissão:** qualquer usuário autenticado.",
    responses=erros(401, 422),
)
async def listar(
    session: SessionDep,
    _: UsuarioLogado,
    filtros: Annotated[VinculoFiltros, Query()],
    pag: Annotated[PaginacaoOrdenavel, Depends()],
):
    items, total = await service.listar(session, filtros, pag)
    return montar_pagina(items, total, pag)


@router.get(
    "/{vinculo_id}",
    response_model=VinculoLeitura,
    operation_id="servicos_mulheres_obter",
    summary="Detalhar vínculo (status atual)",
    description="**Permissão:** qualquer usuário autenticado.",
    responses=erros(401, 404, 422),
)
async def obter(vinculo_id: uuid.UUID, session: SessionDep, _: UsuarioLogado):
    return await service.obter(session, vinculo_id)


@router.patch(
    "/{vinculo_id}",
    response_model=VinculoLeitura,
    operation_id="servicos_mulheres_atualizar",
    summary="Atualizar dados do vínculo (sem status)",
    description="Altera `responsavel_id`, `observacoes` e `data_inicio`. **Não altera o status**: "
    "para isso use `POST /servicos-mulheres/{id}/transicoes`. Não há `DELETE` — cancelar é uma transição para `CANCELADO`.\n\n"
    "**Permissão:** ADMIN, GESTOR, ATENDENTE.\n\nErros de negócio: `409 MULHER_EXCLUIDA`, `422 RESPONSAVEL_INVALIDO`.",
    responses=erros(401, 403, 404, 409, 422),
)
async def atualizar(vinculo_id: uuid.UUID, dados: VinculoAtualizar, session: SessionDep, ator: Escritor):
    return await service.atualizar(session, vinculo_id, dados, ator)


@router.post(
    "/{vinculo_id}/transicoes",
    response_model=VinculoLeitura,
    operation_id="servicos_mulheres_transitar",
    summary="Mudar o status do vínculo",
    description="Única forma de alterar o status. Valida a máquina de estados, atualiza o vínculo, cria o evento "
    "`MUDANCA_STATUS` e a auditoria `STATUS_CHANGE` **na mesma transação**.\n\n"
    "```\nSOLICITADO → EM_ANALISE, CANCELADO\nEM_ANALISE → EM_ATENDIMENTO, CANCELADO\n"
    "EM_ATENDIMENTO → SUSPENSO, CONCLUIDO, CANCELADO\nSUSPENSO → EM_ATENDIMENTO, CANCELADO\n"
    "CONCLUIDO, CANCELADO → (finais)\n```\n\n"
    "`motivo` é obrigatório para `SUSPENSO` e `CANCELADO`. Ao entrar em status final, `data_encerramento` é preenchida.\n\n"
    "**Permissão:** ADMIN, GESTOR, ATENDENTE.\n\n"
    "Erros de negócio: `409 SERVICO_MULHER_TRANSICAO_INVALIDA`, `409 MULHER_EXCLUIDA`, `422 MOTIVO_OBRIGATORIO`.",
    responses=erros(401, 403, 404, 409, 422),
)
async def transitar(vinculo_id: uuid.UUID, dados: TransicaoCriar, session: SessionDep, ator: Escritor):
    return await service.transitar(session, vinculo_id, dados, ator)


@router.get(
    "/{vinculo_id}/transicoes-permitidas",
    response_model=TransicoesPermitidas,
    operation_id="servicos_mulheres_transicoes_permitidas",
    summary="Próximos status válidos",
    description="Para o front montar os botões de ação sem duplicar a máquina de estados.\n\n"
    "**Permissão:** qualquer usuário autenticado.",
    responses=erros(401, 404, 422),
)
async def transicoes_permitidas(vinculo_id: uuid.UUID, session: SessionDep, _: UsuarioLogado):
    return service.transicoes_permitidas(await service.obter(session, vinculo_id))


@router.get(
    "/{vinculo_id}/eventos",
    response_model=Pagina[EventoLeitura],
    operation_id="servicos_mulheres_eventos",
    summary="Linha do tempo do vínculo",
    description="Eventos ligados a este vínculo, do mais recente ao mais antigo.\n\n**Permissão:** qualquer usuário autenticado.",
    responses=erros(401, 404, 422),
)
async def eventos_do_vinculo(
    vinculo_id: uuid.UUID,
    session: SessionDep,
    _: UsuarioLogado,
    pag: Annotated[Paginacao, Depends()],
):
    await service.obter(session, vinculo_id)
    items, total = await eventos.listar(session, EventoFiltros(servico_mulher_id=vinculo_id), pag)
    return montar_pagina(items, total, pag)
