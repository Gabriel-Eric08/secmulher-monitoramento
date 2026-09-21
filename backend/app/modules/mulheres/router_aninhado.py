"""Rotas aninhadas em `/mulheres/{mulher_id}/...` — atalhos que compõem os services de outros módulos.

Aparecem na tag "Mulheres" do Swagger. Operações sobre um item específico ficam no recurso raiz.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.dependencies import Escritor, SessionDep, UsuarioLogado
from app.core.storage import StorageBackend, get_storage
from app.modules.documentos import service as documentos
from app.modules.documentos.forms import form_documento_aninhado
from app.modules.documentos.router import ArquivoUpload
from app.modules.documentos.schema import DocumentoCriarAninhadoForm, DocumentoFiltros, DocumentoLeitura
from app.modules.eventos import service as eventos
from app.modules.eventos.schema import EventoCriar, EventoCriarAninhado, EventoFiltros, EventoFiltrosAninhado, EventoLeitura
from app.modules.mulheres import service as mulheres
from app.modules.servicos_mulheres import service as vinculos
from app.modules.servicos_mulheres.schema import VinculoCriar, VinculoLeitura
from app.shared.pagination import Pagina, Paginacao, PaginacaoOrdenavel, montar_pagina
from app.shared.schemas import erros

router = APIRouter(prefix="/mulheres/{mulher_id}", tags=["Mulheres"])


@router.get(
    "/servicos",
    response_model=Pagina[VinculoLeitura],
    operation_id="mulheres_servicos_listar",
    summary="Vínculos (serviços) da mulher",
    description="Ordenação (`sort`): `created_at` (padrão, desc), `data_inicio`, `status`, `updated_at`.\n\n"
    "**Permissão:** qualquer usuário autenticado.",
    responses=erros(401, 404, 422),
)
async def listar_servicos(
    mulher_id: uuid.UUID,
    session: SessionDep,
    _: UsuarioLogado,
    pag: Annotated[PaginacaoOrdenavel, Depends()],
):
    items, total = await vinculos.listar_da_mulher(session, mulher_id, pag)
    return montar_pagina(items, total, pag)


@router.post(
    "/servicos",
    response_model=VinculoLeitura,
    status_code=status.HTTP_201_CREATED,
    operation_id="mulheres_servicos_criar",
    summary="Vincular serviço à mulher",
    description="Cria o vínculo com status inicial `SOLICITADO` e o evento correspondente na linha do tempo.\n\n"
    "**Permissão:** ADMIN, GESTOR, ATENDENTE.\n\n"
    "Erros de negócio: `409 VINCULO_ABERTO_EXISTENTE`, `409 SERVICO_INATIVO`, `409 MULHER_EXCLUIDA`, "
    "`422 RESPONSAVEL_INVALIDO`.",
    responses=erros(401, 403, 404, 409, 422),
)
async def criar_servico(
    mulher_id: uuid.UUID, dados: VinculoCriar, response: Response, session: SessionDep, ator: Escritor
):
    vinculo = await vinculos.criar(session, mulher_id, dados, ator)
    response.headers["Location"] = f"/api/v1/servicos-mulheres/{vinculo.id}"
    return vinculo


@router.get(
    "/eventos",
    response_model=Pagina[EventoLeitura],
    operation_id="mulheres_eventos_listar",
    summary="Linha do tempo da mulher",
    description="Eventos do mais recente ao mais antigo (`ocorrido_em` desc). A leitura é auditada (`READ_SENSITIVE`).\n\n"
    "**Permissão:** qualquer usuário autenticado.",
    responses=erros(401, 404, 422),
)
async def listar_eventos(
    mulher_id: uuid.UUID,
    session: SessionDep,
    ator: UsuarioLogado,
    filtros: Annotated[EventoFiltrosAninhado, Query()],
    pag: Annotated[Paginacao, Depends()],
):
    await mulheres.obter_para_leitura(session, mulher_id, ator)
    items, total = await eventos.listar(
        session, EventoFiltros(mulher_id=mulher_id, **filtros.model_dump()), pag
    )
    return montar_pagina(items, total, pag)


@router.post(
    "/eventos",
    response_model=EventoLeitura,
    status_code=status.HTTP_201_CREATED,
    operation_id="mulheres_eventos_criar",
    summary="Registrar evento para a mulher",
    description="Igual a `POST /eventos`, com a mulher vinda da URL. Tipos gerados pelo sistema (`MUDANCA_STATUS`, "
    "`DOCUMENTO_ANEXADO`, `RETIFICACAO`) são rejeitados (`422`).\n\n**Permissão:** ADMIN, GESTOR, ATENDENTE.",
    responses=erros(401, 403, 404, 409, 422),
)
async def criar_evento(
    mulher_id: uuid.UUID, dados: EventoCriarAninhado, response: Response, session: SessionDep, ator: Escritor
):
    evento = await eventos.criar(session, EventoCriar(mulher_id=mulher_id, **dados.model_dump()), ator)
    response.headers["Location"] = f"/api/v1/eventos/{evento.id}"
    return evento


@router.get(
    "/documentos",
    response_model=Pagina[DocumentoLeitura],
    operation_id="mulheres_documentos_listar",
    summary="Documentos da mulher",
    description="Ordenação (`sort`): `created_at` (padrão, desc), `titulo`, `tipo`.\n\n**Permissão:** qualquer usuário autenticado.",
    responses=erros(401, 404, 422),
)
async def listar_documentos(
    mulher_id: uuid.UUID,
    session: SessionDep,
    ator: UsuarioLogado,
    pag: Annotated[PaginacaoOrdenavel, Depends()],
    q: Annotated[str | None, Query(max_length=100, description="Busca no título.")] = None,
):
    await mulheres.obter_ou_404(session, mulher_id)
    items, total = await documentos.listar(session, DocumentoFiltros(mulher_id=mulher_id, q=q), pag, ator)
    return montar_pagina(items, total, pag)


@router.post(
    "/documentos",
    response_model=DocumentoLeitura,
    status_code=status.HTTP_201_CREATED,
    operation_id="mulheres_documentos_criar",
    summary="Anexar documento à mulher (upload)",
    description="`multipart/form-data`. Igual a `POST /documentos`, com a mulher vinda da URL.\n\n"
    "**Permissão:** ADMIN, GESTOR, ATENDENTE.",
    responses=erros(401, 403, 404, 409, 413, 415, 422),
)
async def criar_documento(
    mulher_id: uuid.UUID,
    dados: Annotated[DocumentoCriarAninhadoForm, Depends(form_documento_aninhado)],
    arquivo: ArquivoUpload,
    response: Response,
    session: SessionDep,
    storage: Annotated[StorageBackend, Depends(get_storage)],
    ator: Escritor,
):
    documento = await documentos.criar(session, storage, mulher_id, dados, arquivo, ator)
    response.headers["Location"] = f"/api/v1/documentos/{documento.id}"
    return documento
