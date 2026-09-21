import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.dependencies import Escritor, SessionDep, UsuarioLogado
from app.modules.eventos import service
from app.modules.eventos.schema import EventoCriar, EventoFiltros, EventoLeitura, RetificacaoCriar
from app.shared.pagination import Pagina, Paginacao, montar_pagina
from app.shared.schemas import erros

router = APIRouter(prefix="/eventos", tags=["Eventos"])

_IMUTAVEL = (
    "Eventos são **imutáveis**: não existe `PATCH`/`PUT`/`DELETE`. Para corrigir um evento, use "
    "`POST /eventos/{id}/retificacoes`."
)


@router.get(
    "",
    response_model=Pagina[EventoLeitura],
    operation_id="eventos_listar",
    summary="Listar eventos (global)",
    description="Ordenação fixa: `ocorrido_em` desc, `registrado_em` desc.\n\n**Permissão:** qualquer usuário autenticado.",
    responses=erros(401, 422),
)
async def listar(
    session: SessionDep,
    _: UsuarioLogado,
    filtros: Annotated[EventoFiltros, Query()],
    pag: Annotated[Paginacao, Depends()],
):
    items, total = await service.listar(session, filtros, pag)
    return montar_pagina(items, total, pag)


@router.post(
    "",
    response_model=EventoLeitura,
    status_code=status.HTTP_201_CREATED,
    operation_id="eventos_criar",
    summary="Registrar evento",
    description="Registra um fato na linha do tempo. `ocorrido_em` = quando aconteceu (pode ser retroativo, não futuro); "
    "`registrado_em` é sempre do servidor.\n\n"
    "Os tipos `MUDANCA_STATUS`, `DOCUMENTO_ANEXADO` e `RETIFICACAO` são gerados pelo sistema (`422` se enviados).\n\n"
    f"{_IMUTAVEL}\n\n**Permissão:** ADMIN, GESTOR, ATENDENTE.\n\n"
    "Erros de negócio: `409 MULHER_EXCLUIDA`, `422 VINCULO_INVALIDO`.",
    responses=erros(401, 403, 404, 409, 422),
)
async def criar(dados: EventoCriar, response: Response, session: SessionDep, ator: Escritor):
    evento = await service.criar(session, dados, ator)
    response.headers["Location"] = f"/api/v1/eventos/{evento.id}"
    return evento


@router.get(
    "/{evento_id}",
    response_model=EventoLeitura,
    operation_id="eventos_obter",
    summary="Detalhar evento",
    description="Inclui `retificado_por` (IDs das retificações que apontam para este evento).\n\n"
    "**Permissão:** qualquer usuário autenticado.",
    responses=erros(401, 404, 422),
)
async def obter(evento_id: uuid.UUID, session: SessionDep, _: UsuarioLogado):
    return await service.obter(session, evento_id)


@router.post(
    "/{evento_id}/retificacoes",
    response_model=EventoLeitura,
    status_code=status.HTTP_201_CREATED,
    operation_id="eventos_retificar",
    summary="Retificar um evento",
    description="Cria um novo evento do tipo `RETIFICACAO` com `corrige_evento_id` apontando para o original. "
    "O original **não** é alterado. Mulher e vínculo são herdados do original.\n\n"
    "**Permissão:** ADMIN, GESTOR, ATENDENTE.",
    responses=erros(401, 403, 404, 409, 422),
)
async def retificar(
    evento_id: uuid.UUID, dados: RetificacaoCriar, response: Response, session: SessionDep, ator: Escritor
):
    evento = await service.retificar(session, evento_id, dados, ator)
    response.headers["Location"] = f"/api/v1/eventos/{evento.id}"
    return evento
