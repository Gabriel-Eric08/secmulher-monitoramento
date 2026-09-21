import uuid
from dataclasses import dataclass
from tempfile import SpooledTemporaryFile
from typing import BinaryIO
import hashlib
import re
from pathlib import PurePath
from collections.abc import AsyncIterator

import filetype
from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import confirmar
from app.core.storage import StorageBackend
from app.modules.auditoria import service as auditoria
from app.modules.documentos.model import Documento, DocumentoVersao
from app.modules.documentos.schema import (
    DocumentoAtualizar,
    DocumentoCriarAninhadoForm,
    DocumentoFiltros,
    VersaoCriarForm,
)
from app.modules.eventos import service as eventos
from app.modules.eventos.model import Evento
from app.modules.mulheres import service as mulheres
from app.modules.usuarios.model import Usuario
from app.shared.enums import AcaoAuditoria, PerfilUsuario, TipoEvento
from app.shared.exceptions import (
    AcessoNegado,
    ArquivoMuitoGrande,
    Conflito,
    NaoEncontrado,
    TipoArquivoNaoPermitido,
    ValidacaoFalhou,
)
from app.shared.pagination import PaginacaoOrdenavel, ordenar, paginar
from app.shared.utils import serializar_modelo, utcnow

CHUNK = 64 * 1024
MIMES_PERMITIDOS = frozenset(
    {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
)
_ORDENAVEIS = {"created_at": Documento.created_at, "titulo": Documento.titulo, "tipo": Documento.tipo}
_VER_EXCLUIDOS = {PerfilUsuario.ADMIN, PerfilUsuario.GESTOR}


@dataclass
class ArquivoRecebido:
    conteudo: BinaryIO
    sha256: str
    tamanho: int
    mime: str
    nome: str

    def fechar(self) -> None:
        self.conteudo.close()


def _nome_seguro(nome: str | None) -> str:
    base = PurePath((nome or "arquivo").replace("\\", "/")).name
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip()
    return (base or "arquivo")[:255]


async def receber_upload(arquivo: UploadFile) -> ArquivoRecebido:
    """Lê o upload em streaming: limita o tamanho, calcula SHA-256 e detecta o MIME pelo conteúdo."""
    limite = get_settings().max_upload_bytes
    temp: BinaryIO = SpooledTemporaryFile(max_size=8 * 1024 * 1024)  # type: ignore[assignment]
    sha = hashlib.sha256()
    tamanho = 0
    cabecalho = b""
    try:
        while bloco := await arquivo.read(CHUNK):
            tamanho += len(bloco)
            if tamanho > limite:
                raise ArquivoMuitoGrande(
                    f"Arquivo maior que o máximo permitido ({get_settings().max_upload_mb} MB)."
                )
            if len(cabecalho) < 8192:
                cabecalho += bloco[: 8192 - len(cabecalho)]
            sha.update(bloco)
            temp.write(bloco)
        if tamanho == 0:
            raise ValidacaoFalhou("O arquivo enviado está vazio.", code="ARQUIVO_VAZIO")
        tipo = filetype.guess(cabecalho)
        mime = tipo.mime if tipo else None
        if mime not in MIMES_PERMITIDOS:
            raise TipoArquivoNaoPermitido(
                "Tipo de arquivo não permitido. Aceitos: PDF, JPG, PNG, DOC/DOCX e XLSX."
            )
        temp.seek(0)
        return ArquivoRecebido(temp, sha.hexdigest(), tamanho, mime, _nome_seguro(arquivo.filename))
    except BaseException:
        temp.close()
        raise


def _chave(mulher_id: uuid.UUID, documento_id: uuid.UUID, numero: int, sha256: str) -> str:
    return f"mulheres/{mulher_id}/documentos/{documento_id}/v{numero}-{sha256[:12]}"


async def _carregar(session: AsyncSession, documento_id: uuid.UUID) -> Documento | None:
    return await session.scalar(
        select(Documento).where(Documento.id == documento_id).execution_options(populate_existing=True)
    )


async def obter(session: AsyncSession, documento_id: uuid.UUID, *, incluir_excluido: bool = False) -> Documento:
    documento = await _carregar(session, documento_id)
    if documento is None or (documento.deleted_at is not None and not incluir_excluido):
        raise NaoEncontrado("Documento não encontrado.", code="DOCUMENTO_NAO_ENCONTRADO")
    return documento


async def obter_para_ator(session: AsyncSession, documento_id: uuid.UUID, ator: Usuario) -> Documento:
    return await obter(session, documento_id, incluir_excluido=ator.perfil in _VER_EXCLUIDOS)


async def listar(
    session: AsyncSession, filtros: DocumentoFiltros, pag: PaginacaoOrdenavel, ator: Usuario
) -> tuple[list[Documento], int]:
    if filtros.incluir_excluidos and ator.perfil not in _VER_EXCLUIDOS:
        raise AcessoNegado("Apenas ADMIN e GESTOR podem incluir documentos excluídos.")
    stmt = select(Documento)
    if not filtros.incluir_excluidos:
        stmt = stmt.where(Documento.deleted_at.is_(None))
    if filtros.mulher_id:
        stmt = stmt.where(Documento.mulher_id == filtros.mulher_id)
    if filtros.servico_mulher_id:
        stmt = stmt.where(Documento.servico_mulher_id == filtros.servico_mulher_id)
    if filtros.tipo:
        stmt = stmt.where(Documento.tipo == filtros.tipo)
    if filtros.q:
        stmt = stmt.where(Documento.titulo.ilike(f"%{filtros.q}%"))
    stmt = ordenar(stmt, pag.sort, _ORDENAVEIS, [Documento.created_at.desc()], Documento.id)
    return await paginar(session, stmt, pag)


async def contar_da_mulher(session: AsyncSession, mulher_id: uuid.UUID) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(Documento)
            .where(Documento.mulher_id == mulher_id, Documento.deleted_at.is_(None))
        )
        or 0
    )


async def _validar_relacionados(
    session: AsyncSession, mulher_id: uuid.UUID, servico_mulher_id: uuid.UUID | None, evento_id: uuid.UUID | None
) -> None:
    await eventos.validar_vinculo(session, mulher_id, servico_mulher_id)
    if evento_id is not None:
        evento = await session.get(Evento, evento_id)
        if evento is None or evento.mulher_id != mulher_id:
            raise ValidacaoFalhou(
                "O evento informado não existe ou não pertence a esta mulher.",
                code="EVENTO_INVALIDO",
                details=[{"field": "evento_id", "issue": "não pertence à mulher"}],
            )


async def _gravar_e_confirmar(
    session: AsyncSession, storage: StorageBackend, arquivo: ArquivoRecebido, chave: str, *, conflito: tuple[str, str]
) -> None:
    """Salva o arquivo e faz o commit; se o commit falhar, remove o arquivo órfão do storage."""
    await storage.save(chave, arquivo.conteudo)
    try:
        await confirmar(session, code=conflito[0], message=conflito[1])
    except BaseException:
        await storage.delete(chave)
        raise


async def criar(
    session: AsyncSession,
    storage: StorageBackend,
    mulher_id: uuid.UUID,
    dados: DocumentoCriarAninhadoForm,
    upload: UploadFile,
    ator: Usuario,
) -> Documento:
    await mulheres.exigir_ativa(session, mulher_id)
    await _validar_relacionados(session, mulher_id, dados.servico_mulher_id, dados.evento_id)
    arquivo = await receber_upload(upload)
    try:
        documento = Documento(
            mulher_id=mulher_id,
            servico_mulher_id=dados.servico_mulher_id,
            evento_id=dados.evento_id,
            titulo=dados.titulo,
            tipo=dados.tipo,
            descricao=dados.descricao,
            versao_atual=1,
            created_by=ator.id,
        )
        session.add(documento)
        await session.flush()
        chave = _chave(mulher_id, documento.id, 1, arquivo.sha256)
        versao = DocumentoVersao(
            documento_id=documento.id,
            numero=1,
            nome_arquivo=arquivo.nome,
            mime_type=arquivo.mime,
            tamanho_bytes=arquivo.tamanho,
            sha256=arquivo.sha256,
            storage_key=chave,
            valido_de=dados.valido_de,
            valido_ate=dados.valido_ate,
            motivo="Versão inicial",
            criado_por=ator.id,
        )
        session.add(versao)
        await session.flush()
        eventos.registrar_interno(
            session,
            mulher_id=mulher_id,
            servico_mulher_id=dados.servico_mulher_id,
            tipo=TipoEvento.DOCUMENTO_ANEXADO,
            titulo=f"Documento anexado: {documento.titulo}",
            descricao=f"{arquivo.nome} (versão 1)",
            usuario_id=ator.id,
            metadados={"documento_id": str(documento.id), "versao": 1},
        )
        await auditoria.registrar(
            session,
            usuario_id=ator.id,
            acao=AcaoAuditoria.UPLOAD,
            entidade="documento",
            entidade_id=documento.id,
            mulher_id=mulher_id,
            depois={**serializar_modelo(documento), "versao": serializar_modelo(versao)},
        )
        await _gravar_e_confirmar(
            session, storage, arquivo, chave, conflito=("CONFLITO", "Conflito ao gravar o documento.")
        )
    finally:
        arquivo.fechar()
    return await obter(session, documento.id)


async def atualizar(
    session: AsyncSession, documento_id: uuid.UUID, dados: DocumentoAtualizar, ator: Usuario
) -> Documento:
    documento = await obter(session, documento_id)
    campos = dados.model_dump(exclude_unset=True)
    if not campos:
        return documento
    antes = serializar_modelo(documento)
    for chave, valor in campos.items():
        setattr(documento, chave, valor)
    await session.flush()
    await auditoria.registrar(
        session,
        usuario_id=ator.id,
        acao=AcaoAuditoria.UPDATE,
        entidade="documento",
        entidade_id=documento.id,
        mulher_id=documento.mulher_id,
        antes=antes,
        depois=serializar_modelo(documento),
    )
    await confirmar(session)
    return await obter(session, documento.id)


async def excluir(session: AsyncSession, documento_id: uuid.UUID, ator: Usuario) -> None:
    documento = await obter(session, documento_id)
    antes = serializar_modelo(documento)
    documento.deleted_at = utcnow()
    documento.deleted_by = ator.id
    await session.flush()
    await auditoria.registrar(
        session,
        usuario_id=ator.id,
        acao=AcaoAuditoria.DELETE,
        entidade="documento",
        entidade_id=documento.id,
        mulher_id=documento.mulher_id,
        antes=antes,
        depois=serializar_modelo(documento),
    )
    await confirmar(session)


async def restaurar(session: AsyncSession, documento_id: uuid.UUID, ator: Usuario) -> Documento:
    documento = await obter(session, documento_id, incluir_excluido=True)
    if documento.deleted_at is None:
        raise Conflito("O documento não está excluído.", code="DOCUMENTO_NAO_EXCLUIDO")
    antes = serializar_modelo(documento)
    documento.deleted_at = None
    documento.deleted_by = None
    await session.flush()
    await auditoria.registrar(
        session,
        usuario_id=ator.id,
        acao=AcaoAuditoria.RESTORE,
        entidade="documento",
        entidade_id=documento.id,
        mulher_id=documento.mulher_id,
        antes=antes,
        depois=serializar_modelo(documento),
    )
    await confirmar(session)
    return await obter(session, documento.id)


async def nova_versao(
    session: AsyncSession,
    storage: StorageBackend,
    documento_id: uuid.UUID,
    dados: VersaoCriarForm,
    upload: UploadFile,
    ator: Usuario,
) -> Documento:
    """Nunca sobrescreve: cria a versão N+1 e move o ponteiro `versao_atual`."""
    documento = await obter(session, documento_id)
    await mulheres.exigir_ativa(session, documento.mulher_id)
    arquivo = await receber_upload(upload)
    try:
        if documento.versao and documento.versao.sha256 == arquivo.sha256:
            raise Conflito(
                "O arquivo enviado é idêntico à versão atual.", code="VERSAO_IDENTICA"
            )
        ultimo = await session.scalar(
            select(func.max(DocumentoVersao.numero)).where(DocumentoVersao.documento_id == documento.id)
        )
        numero = (ultimo or 0) + 1
        chave = _chave(documento.mulher_id, documento.id, numero, arquivo.sha256)
        versao = DocumentoVersao(
            documento_id=documento.id,
            numero=numero,
            nome_arquivo=arquivo.nome,
            mime_type=arquivo.mime,
            tamanho_bytes=arquivo.tamanho,
            sha256=arquivo.sha256,
            storage_key=chave,
            valido_de=dados.valido_de,
            valido_ate=dados.valido_ate,
            motivo=dados.motivo,
            criado_por=ator.id,
        )
        session.add(versao)
        antes = serializar_modelo(documento)
        documento.versao_atual = numero
        documento.updated_at = utcnow()
        await session.flush()
        eventos.registrar_interno(
            session,
            mulher_id=documento.mulher_id,
            servico_mulher_id=documento.servico_mulher_id,
            tipo=TipoEvento.DOCUMENTO_ANEXADO,
            titulo=f"Nova versão de documento: {documento.titulo}",
            descricao=f"{arquivo.nome} (versão {numero}). Motivo: {dados.motivo}",
            usuario_id=ator.id,
            metadados={"documento_id": str(documento.id), "versao": numero},
        )
        await auditoria.registrar(
            session,
            usuario_id=ator.id,
            acao=AcaoAuditoria.UPLOAD,
            entidade="documento",
            entidade_id=documento.id,
            mulher_id=documento.mulher_id,
            antes=antes,
            depois={**serializar_modelo(documento), "versao": serializar_modelo(versao)},
        )
        await _gravar_e_confirmar(
            session,
            storage,
            arquivo,
            chave,
            conflito=("VERSAO_CONCORRENTE", "Outra versão foi enviada ao mesmo tempo. Tente novamente."),
        )
    finally:
        arquivo.fechar()
    return await obter(session, documento.id)


async def listar_versoes(
    session: AsyncSession, documento_id: uuid.UUID, ator: Usuario, pag: PaginacaoOrdenavel
) -> tuple[list[DocumentoVersao], int]:
    documento = await obter_para_ator(session, documento_id, ator)
    stmt = (
        select(DocumentoVersao)
        .where(DocumentoVersao.documento_id == documento.id)
        .order_by(DocumentoVersao.numero.desc())
    )
    return await paginar(session, stmt, pag)


async def obter_versao(
    session: AsyncSession, documento_id: uuid.UUID, numero: int, ator: Usuario
) -> DocumentoVersao:
    documento = await obter_para_ator(session, documento_id, ator)
    versao = await session.scalar(
        select(DocumentoVersao).where(DocumentoVersao.documento_id == documento.id, DocumentoVersao.numero == numero)
    )
    if versao is None:
        raise NaoEncontrado("Versão não encontrada.", code="VERSAO_NAO_ENCONTRADA")
    return versao


async def preparar_download(
    session: AsyncSession,
    storage: StorageBackend,
    documento_id: uuid.UUID,
    numero: int | None,
    ator: Usuario,
) -> tuple[DocumentoVersao, AsyncIterator[bytes]]:
    """Valida, **audita o download** e devolve a versão + stream do arquivo."""
    documento = await obter_para_ator(session, documento_id, ator)
    versao = await obter_versao(session, documento_id, numero or documento.versao_atual, ator)
    if not await storage.exists(versao.storage_key):
        raise NaoEncontrado("O arquivo desta versão não está disponível no storage.", code="ARQUIVO_INDISPONIVEL")
    await auditoria.registrar(
        session,
        usuario_id=ator.id,
        acao=AcaoAuditoria.DOWNLOAD,
        entidade="documento",
        entidade_id=documento.id,
        mulher_id=documento.mulher_id,
        depois={"versao": versao.numero, "nome_arquivo": versao.nome_arquivo, "sha256": versao.sha256},
    )
    await session.commit()
    return versao, storage.open(versao.storage_key)
