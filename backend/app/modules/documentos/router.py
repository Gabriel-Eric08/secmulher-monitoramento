import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from app.core.dependencies import AdminOuGestor, Escritor, SessionDep, UsuarioLogado
from app.core.storage import StorageBackend, get_storage
from app.modules.documentos import service
from app.modules.documentos.forms import form_documento, form_versao
from app.modules.documentos.model import DocumentoVersao
from app.modules.documentos.schema import (
    DocumentoAtualizar,
    DocumentoCriarForm,
    DocumentoFiltros,
    DocumentoLeitura,
    DocumentoVersaoLeitura,
    VersaoCriarForm,
)
from app.shared.pagination import Pagina, PaginacaoOrdenavel, montar_pagina
from app.shared.schemas import erros

router = APIRouter(prefix="/documentos", tags=["Documentos"])

StorageDep = Annotated[StorageBackend, Depends(get_storage)]
ArquivoUpload = Annotated[UploadFile, File(description="Arquivo (PDF, JPG, PNG, DOC/DOCX ou XLSX). Máx. `MAX_UPLOAD_MB`.")]

_UPLOAD_REGRAS = (
    "Limite de tamanho: `MAX_UPLOAD_MB` (padrão 20 MB → `413`). O tipo é validado pelo **conteúdo** do arquivo, "
    "não pela extensão (`415`). O SHA-256 é calculado durante o upload."
)
_DOWNLOAD_RESPONSE = {
    200: {
        "description": "Conteúdo binário do arquivo (`Content-Disposition: attachment`).",
        "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
    }
}


def _resposta_download(versao: DocumentoVersao, stream) -> StreamingResponse:
    ascii_nome = versao.nome_arquivo.encode("ascii", "ignore").decode() or "arquivo"
    ascii_nome = ascii_nome.replace('"', "")
    return StreamingResponse(
        stream,
        media_type=versao.mime_type,
        headers={
            "Content-Disposition": f"attachment; filename=\"{ascii_nome}\"; filename*=UTF-8''{quote(versao.nome_arquivo)}",
            "Content-Length": str(versao.tamanho_bytes),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "",
    response_model=Pagina[DocumentoLeitura],
    operation_id="documentos_listar",
    summary="Listar documentos",
    description="Cada item traz os metadados da **versão atual**.\n\nOrdenação (`sort`): `created_at` (padrão, desc), `titulo`, `tipo`.\n\n"
    "**Permissão:** qualquer usuário autenticado (`incluir_excluidos` só ADMIN/GESTOR).",
    responses=erros(401, 403, 422),
)
async def listar(
    session: SessionDep,
    ator: UsuarioLogado,
    filtros: Annotated[DocumentoFiltros, Query()],
    pag: Annotated[PaginacaoOrdenavel, Depends()],
):
    items, total = await service.listar(session, filtros, pag, ator)
    return montar_pagina(items, total, pag)


@router.post(
    "",
    response_model=DocumentoLeitura,
    status_code=status.HTTP_201_CREATED,
    operation_id="documentos_criar",
    summary="Criar documento com a 1ª versão (upload)",
    description="`multipart/form-data`: campos do formulário + arquivo em `arquivo`. Cria o documento, a versão 1 e o "
    f"evento `DOCUMENTO_ANEXADO`. {_UPLOAD_REGRAS}\n\n**Permissão:** ADMIN, GESTOR, ATENDENTE.\n\n"
    "Erros de negócio: `409 MULHER_EXCLUIDA`, `422 VINCULO_INVALIDO`, `422 EVENTO_INVALIDO`, `422 ARQUIVO_VAZIO`.",
    responses=erros(401, 403, 404, 409, 413, 415, 422),
)
async def criar(
    dados: Annotated[DocumentoCriarForm, Depends(form_documento)],
    arquivo: ArquivoUpload,
    response: Response,
    session: SessionDep,
    storage: StorageDep,
    ator: Escritor,
):
    documento = await service.criar(session, storage, dados.mulher_id, dados, arquivo, ator)
    response.headers["Location"] = f"/api/v1/documentos/{documento.id}"
    return documento


@router.get(
    "/{documento_id}",
    response_model=DocumentoLeitura,
    operation_id="documentos_obter",
    summary="Detalhar documento (metadados + versão atual)",
    description="**Permissão:** qualquer usuário autenticado (ADMIN/GESTOR também veem excluídos).",
    responses=erros(401, 404, 422),
)
async def obter(documento_id: uuid.UUID, session: SessionDep, ator: UsuarioLogado):
    return await service.obter_para_ator(session, documento_id, ator)


@router.patch(
    "/{documento_id}",
    response_model=DocumentoLeitura,
    operation_id="documentos_atualizar",
    summary="Atualizar metadados do documento",
    description="Apenas `titulo`, `tipo` e `descricao`. O arquivo só muda por `POST /documentos/{id}/versoes`.\n\n"
    "**Permissão:** ADMIN, GESTOR, ATENDENTE.",
    responses=erros(401, 403, 404, 422),
)
async def atualizar(documento_id: uuid.UUID, dados: DocumentoAtualizar, session: SessionDep, ator: Escritor):
    return await service.atualizar(session, documento_id, dados, ator)


@router.delete(
    "/{documento_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="documentos_excluir",
    summary="Excluir documento (exclusão lógica)",
    description="O documento some das listagens padrão, mas **todas as versões e arquivos são preservados**.\n\n"
    "**Permissão:** ADMIN, GESTOR.",
    responses=erros(401, 403, 404, 422),
)
async def excluir(documento_id: uuid.UUID, session: SessionDep, ator: AdminOuGestor) -> Response:
    await service.excluir(session, documento_id, ator)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{documento_id}/restaurar",
    response_model=DocumentoLeitura,
    operation_id="documentos_restaurar",
    summary="Restaurar documento excluído",
    description="**Permissão:** ADMIN, GESTOR.\n\nErro de negócio: `409 DOCUMENTO_NAO_EXCLUIDO`.",
    responses=erros(401, 403, 404, 409, 422),
)
async def restaurar(documento_id: uuid.UUID, session: SessionDep, ator: AdminOuGestor):
    return await service.restaurar(session, documento_id, ator)


@router.get(
    "/{documento_id}/versoes",
    response_model=Pagina[DocumentoVersaoLeitura],
    operation_id="documentos_versoes_listar",
    summary="Histórico de versões",
    description="Da mais recente para a mais antiga. Todas as versões continuam acessíveis.\n\n**Permissão:** qualquer usuário autenticado.",
    responses=erros(401, 404, 422),
)
async def listar_versoes(
    documento_id: uuid.UUID,
    session: SessionDep,
    ator: UsuarioLogado,
    pag: Annotated[PaginacaoOrdenavel, Depends()],
):
    items, total = await service.listar_versoes(session, documento_id, ator, pag)
    return montar_pagina(items, total, pag)


@router.post(
    "/{documento_id}/versoes",
    response_model=DocumentoLeitura,
    status_code=status.HTTP_201_CREATED,
    operation_id="documentos_versoes_criar",
    summary="Enviar nova versão",
    description="`multipart/form-data`. **Nunca sobrescreve**: cria a versão N+1, move a versão atual e cria o evento "
    f"`DOCUMENTO_ANEXADO`. {_UPLOAD_REGRAS}\n\n**Permissão:** ADMIN, GESTOR, ATENDENTE.\n\n"
    "Erros de negócio: `409 VERSAO_IDENTICA` (mesmo SHA-256 da versão atual), `409 VERSAO_CONCORRENTE`, `409 MULHER_EXCLUIDA`.",
    responses=erros(401, 403, 404, 409, 413, 415, 422),
)
async def criar_versao(
    documento_id: uuid.UUID,
    dados: Annotated[VersaoCriarForm, Depends(form_versao)],
    arquivo: ArquivoUpload,
    session: SessionDep,
    storage: StorageDep,
    ator: Escritor,
):
    return await service.nova_versao(session, storage, documento_id, dados, arquivo, ator)


@router.get(
    "/{documento_id}/versoes/{numero}",
    response_model=DocumentoVersaoLeitura,
    operation_id="documentos_versoes_obter",
    summary="Metadados de uma versão",
    description="**Permissão:** qualquer usuário autenticado.",
    responses=erros(401, 404, 422),
)
async def obter_versao(documento_id: uuid.UUID, numero: int, session: SessionDep, ator: UsuarioLogado):
    return await service.obter_versao(session, documento_id, numero, ator)


@router.get(
    "/{documento_id}/download",
    operation_id="documentos_download",
    summary="Baixar a versão atual",
    description="Stream do arquivo. O download **sempre passa pela API** e é auditado (`DOWNLOAD`).\n\n"
    "**Permissão:** qualquer usuário autenticado.",
    response_class=StreamingResponse,
    responses={**_DOWNLOAD_RESPONSE, **erros(401, 404, 422)},
)
async def baixar_atual(documento_id: uuid.UUID, session: SessionDep, storage: StorageDep, ator: UsuarioLogado):
    versao, stream = await service.preparar_download(session, storage, documento_id, None, ator)
    return _resposta_download(versao, stream)


@router.get(
    "/{documento_id}/versoes/{numero}/download",
    operation_id="documentos_versoes_download",
    summary="Baixar uma versão específica",
    description="Stream do arquivo da versão. Auditado (`DOWNLOAD`).\n\n**Permissão:** qualquer usuário autenticado.",
    response_class=StreamingResponse,
    responses={**_DOWNLOAD_RESPONSE, **erros(401, 404, 422)},
)
async def baixar_versao(
    documento_id: uuid.UUID, numero: int, session: SessionDep, storage: StorageDep, ator: UsuarioLogado
):
    versao, stream = await service.preparar_download(session, storage, documento_id, numero, ator)
    return _resposta_download(versao, stream)
