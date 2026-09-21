"""Dependências de formulário multipart (FastAPI não combina um modelo `Form()` com `File` no mesmo endpoint).

Cada campo é declarado individualmente (aparece no Swagger) e depois validado pelos schemas do módulo.
"""

import uuid
from datetime import date
from typing import Annotated, Any, TypeVar

from fastapi import Form
from pydantic import BaseModel, ValidationError

from app.modules.documentos.schema import DocumentoCriarAninhadoForm, DocumentoCriarForm, VersaoCriarForm
from app.shared.enums import TipoDocumento
from app.shared.exceptions import ValidacaoFalhou

Titulo = Annotated[str, Form(min_length=3, max_length=200, description="Título do documento.", examples=["Encaminhamento"])]
Tipo = Annotated[TipoDocumento, Form(description="Tipo do documento.", examples=["ENCAMINHAMENTO"])]
Descricao = Annotated[str | None, Form(max_length=5000, description="Descrição (opcional).")]
VinculoId = Annotated[uuid.UUID | None, Form(description="Vínculo relacionado (opcional).")]
EventoId = Annotated[uuid.UUID | None, Form(description="Evento relacionado (opcional).")]
ValidoDe = Annotated[date | None, Form(description="Início da validade (opcional), `AAAA-MM-DD`.")]
ValidoAte = Annotated[date | None, Form(description="Fim da validade (opcional), `AAAA-MM-DD`.")]


M = TypeVar("M", bound=BaseModel)


def _construir(modelo: type[M], **campos: Any) -> M:
    try:
        return modelo(**{k: v for k, v in campos.items() if v not in (None, "")})
    except ValidationError as exc:
        details = [
            {"field": ".".join(str(p) for p in e["loc"]) or None, "issue": e["msg"].removeprefix("Value error, ")}
            for e in exc.errors()
        ]
        raise ValidacaoFalhou("Os dados enviados são inválidos.", details=details) from exc


def form_documento_aninhado(
    titulo: Titulo,
    tipo: Tipo,
    descricao: Descricao = None,
    servico_mulher_id: VinculoId = None,
    evento_id: EventoId = None,
    valido_de: ValidoDe = None,
    valido_ate: ValidoAte = None,
) -> DocumentoCriarAninhadoForm:
    return _construir(
        DocumentoCriarAninhadoForm,
        titulo=titulo,
        tipo=tipo,
        descricao=descricao,
        servico_mulher_id=servico_mulher_id,
        evento_id=evento_id,
        valido_de=valido_de,
        valido_ate=valido_ate,
    )


def form_documento(
    mulher_id: Annotated[uuid.UUID, Form(description="Mulher a que o documento pertence.")],
    titulo: Titulo,
    tipo: Tipo,
    descricao: Descricao = None,
    servico_mulher_id: VinculoId = None,
    evento_id: EventoId = None,
    valido_de: ValidoDe = None,
    valido_ate: ValidoAte = None,
) -> DocumentoCriarForm:
    return _construir(
        DocumentoCriarForm,
        mulher_id=mulher_id,
        titulo=titulo,
        tipo=tipo,
        descricao=descricao,
        servico_mulher_id=servico_mulher_id,
        evento_id=evento_id,
        valido_de=valido_de,
        valido_ate=valido_ate,
    )


def form_versao(
    motivo: Annotated[str, Form(min_length=3, max_length=500, description="Por que há uma nova versão.", examples=["Renovação"])],
    valido_de: ValidoDe = None,
    valido_ate: ValidoAte = None,
) -> VersaoCriarForm:
    return _construir(VersaoCriarForm, motivo=motivo, valido_de=valido_de, valido_ate=valido_ate)
