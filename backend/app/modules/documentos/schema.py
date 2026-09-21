import uuid
from datetime import date, datetime

from pydantic import ConfigDict, Field, model_validator

from app.modules.mulheres.schema import MulherMinima
from app.shared.enums import TipoDocumento
from app.shared.schemas import Esquema


class DocumentoVersaoLeitura(Esquema):
    numero: int = Field(..., description="Número sequencial da versão (1, 2, 3…).", examples=[2])
    nome_arquivo: str = Field(..., examples=["encaminhamento-2026.pdf"])
    mime_type: str = Field(..., description="Detectado pelo **conteúdo** do arquivo.", examples=["application/pdf"])
    tamanho_bytes: int
    sha256: str = Field(..., description="Hash SHA-256 do conteúdo.")
    valido_de: date | None = Field(None, description="Início da validade do documento nesta versão.")
    valido_ate: date | None = Field(None, description="Fim da validade do documento nesta versão.")
    motivo: str | None = Field(None, description="Por que esta versão foi criada.")
    criado_por: uuid.UUID
    created_at: datetime


class DocumentoLeitura(Esquema):
    id: uuid.UUID
    mulher_id: uuid.UUID
    mulher: MulherMinima = Field(..., description="Mulher dona do documento (id e nome).")
    servico_mulher_id: uuid.UUID | None
    evento_id: uuid.UUID | None
    titulo: str
    tipo: TipoDocumento
    descricao: str | None
    versao_atual: int = Field(..., description="Número da versão vigente.")
    versao: DocumentoVersaoLeitura | None = Field(None, description="Metadados da versão vigente.")
    deleted_at: datetime | None = Field(None, description="Preenchido quando excluído logicamente.")
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "3b8c1d2e-4f5a-4b6c-9d7e-8f9a0b1c2d3e",
                    "mulher_id": "9d2e7f10-3a4b-4c5d-8e6f-1a2b3c4d5e6f",
                    "mulher": {"id": "9d2e7f10-3a4b-4c5d-8e6f-1a2b3c4d5e6f", "nome_completo": "Maria Souza da Silva", "nome_social": None},
                    "servico_mulher_id": None,
                    "evento_id": None,
                    "titulo": "Encaminhamento",
                    "tipo": "ENCAMINHAMENTO",
                    "descricao": None,
                    "versao_atual": 2,
                    "versao": {
                        "numero": 2,
                        "nome_arquivo": "encaminhamento-renovado.pdf",
                        "mime_type": "application/pdf",
                        "tamanho_bytes": 48211,
                        "sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
                        "valido_de": "2026-06-01",
                        "valido_ate": "2026-12-01",
                        "motivo": "Renovação",
                        "criado_por": "0b5d5c2e-1f0a-4b7e-9a0e-6f1c2d3e4f50",
                        "created_at": "2026-06-01T12:00:00Z",
                    },
                    "deleted_at": None,
                    "created_by": "0b5d5c2e-1f0a-4b7e-9a0e-6f1c2d3e4f50",
                    "created_at": "2026-03-03T13:20:00Z",
                    "updated_at": "2026-06-01T12:00:00Z",
                }
            ]
        },
    )


class DocumentoAtualizar(Esquema):
    """Apenas metadados do documento. O arquivo só muda por nova versão."""

    titulo: str | None = Field(None, min_length=3, max_length=200)
    tipo: TipoDocumento | None = None
    descricao: str | None = Field(None, max_length=5000)

    @model_validator(mode="after")
    def _titulo_tipo_nao_nulos(self) -> "DocumentoAtualizar":
        for campo in ("titulo", "tipo"):
            if campo in self.model_fields_set and getattr(self, campo) is None:
                raise ValueError(f"{campo} não pode ser nulo.")
        return self


class _VigenciaForm(Esquema):
    valido_de: date | None = Field(None, description="Início da validade (opcional).")
    valido_ate: date | None = Field(None, description="Fim da validade (opcional).")

    @model_validator(mode="after")
    def _vigencia(self) -> "_VigenciaForm":
        if self.valido_de and self.valido_ate and self.valido_de > self.valido_ate:
            raise ValueError("`valido_de` deve ser anterior ou igual a `valido_ate`.")
        return self


class DocumentoCriarAninhadoForm(_VigenciaForm):
    """Campos de formulário (multipart) para criar um documento; o arquivo vai no campo `arquivo`."""

    titulo: str = Field(..., min_length=3, max_length=200, examples=["Encaminhamento"])
    tipo: TipoDocumento = Field(..., examples=["ENCAMINHAMENTO"])
    descricao: str | None = Field(None, max_length=5000)
    servico_mulher_id: uuid.UUID | None = Field(None, description="Vínculo relacionado (opcional).")
    evento_id: uuid.UUID | None = Field(None, description="Evento relacionado (opcional).")


class DocumentoCriarForm(DocumentoCriarAninhadoForm):
    mulher_id: uuid.UUID = Field(..., description="Mulher a que o documento pertence.")


class VersaoCriarForm(_VigenciaForm):
    """Campos de formulário (multipart) para nova versão; o arquivo vai no campo `arquivo`."""

    motivo: str = Field(..., min_length=3, max_length=500, description="Por que há uma nova versão.", examples=["Renovação"])


class DocumentoFiltros(Esquema):
    mulher_id: uuid.UUID | None = None
    servico_mulher_id: uuid.UUID | None = None
    tipo: TipoDocumento | None = None
    q: str | None = Field(None, max_length=100, description="Busca no título (contém).")
    incluir_excluidos: bool = Field(False, description="Inclui excluídos logicamente. **Só ADMIN/GESTOR.**")
