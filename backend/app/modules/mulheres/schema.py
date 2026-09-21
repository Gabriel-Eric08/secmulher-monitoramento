import re
import uuid
from datetime import date, datetime

from pydantic import ConfigDict, EmailStr, Field, field_validator

from app.shared.enums import StatusServicoMulher
from app.shared.schemas import Esquema
from app.shared.utils import mascarar_cpf, mascarar_telefone, so_digitos, utcnow, validar_cpf


class MulherMinima(Esquema):
    """Referência enxuta a uma mulher (usada em vínculos, eventos e documentos)."""

    id: uuid.UUID
    nome_completo: str
    nome_social: str | None = None


class _MulherCampos(Esquema):
    """Campos editáveis do cadastro (validações compartilhadas entre criar e atualizar)."""

    nome_completo: str | None = Field(None, min_length=3, max_length=200, examples=["Maria Souza da Silva"])
    nome_social: str | None = Field(None, max_length=200, examples=["Mariana"])
    cpf: str | None = Field(None, description="Com ou sem máscara; armazenado só com dígitos.", examples=["529.982.247-25"])
    rg: str | None = Field(None, max_length=30)
    data_nascimento: date | None = Field(None, examples=["1990-05-17"])
    telefone: str | None = Field(None, max_length=20, examples=["(11) 91234-5678"])
    telefone_alt: str | None = Field(None, max_length=20)
    email: EmailStr | None = None
    logradouro: str | None = Field(None, max_length=200)
    numero: str | None = Field(None, max_length=20)
    complemento: str | None = Field(None, max_length=100)
    bairro: str | None = Field(None, max_length=100)
    cidade: str | None = Field(None, max_length=100)
    uf: str | None = Field(None, description="Sigla da UF.", examples=["SP"])
    cep: str | None = Field(None, description="Com ou sem máscara.", examples=["01310-100"])
    observacoes: str | None = Field(None, max_length=5000)

    @field_validator("cpf")
    @classmethod
    def _cpf(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        digitos = so_digitos(v)
        if not validar_cpf(digitos):
            raise ValueError("CPF inválido.")
        return digitos

    @field_validator("cep")
    @classmethod
    def _cep(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        digitos = so_digitos(v)
        if len(digitos) != 8:
            raise ValueError("CEP deve ter 8 dígitos.")
        return digitos

    @field_validator("uf")
    @classmethod
    def _uf(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        v = v.upper()
        if not re.fullmatch(r"[A-Z]{2}", v):
            raise ValueError("UF deve ter 2 letras.")
        return v

    @field_validator("data_nascimento")
    @classmethod
    def _nascimento(cls, v: date | None) -> date | None:
        if v is not None and v > utcnow().date():
            raise ValueError("Data de nascimento não pode ser futura.")
        return v


class MulherCriar(_MulherCampos):
    nome_completo: str = Field(..., min_length=3, max_length=200, examples=["Maria Souza da Silva"])


class MulherAtualizar(_MulherCampos):
    """Atualização parcial: envie apenas os campos a alterar. `null` limpa um campo opcional."""

    @field_validator("nome_completo")
    @classmethod
    def _nome_nao_nulo(cls, v: str | None) -> str | None:
        if v is None:
            raise ValueError("nome_completo não pode ser nulo.")
        return v


class MulherLeitura(Esquema):
    id: uuid.UUID
    nome_completo: str
    nome_social: str | None
    cpf: str | None
    rg: str | None
    data_nascimento: date | None
    telefone: str | None
    telefone_alt: str | None
    email: str | None
    logradouro: str | None
    numero: str | None
    complemento: str | None
    bairro: str | None
    cidade: str | None
    uf: str | None
    cep: str | None
    observacoes: str | None
    deleted_at: datetime | None = Field(None, description="Preenchido quando excluída logicamente.")
    motivo_exclusao: str | None = None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "9d2e7f10-3a4b-4c5d-8e6f-1a2b3c4d5e6f",
                    "nome_completo": "Maria Souza da Silva",
                    "nome_social": None,
                    "cpf": "52998224725",
                    "rg": "12.345.678-9",
                    "data_nascimento": "1990-05-17",
                    "telefone": "(11) 91234-5678",
                    "telefone_alt": None,
                    "email": "maria@example.com",
                    "logradouro": "Av. Paulista",
                    "numero": "1000",
                    "complemento": "ap 12",
                    "bairro": "Bela Vista",
                    "cidade": "São Paulo",
                    "uf": "SP",
                    "cep": "01310100",
                    "observacoes": None,
                    "deleted_at": None,
                    "motivo_exclusao": None,
                    "created_by": "0b5d5c2e-1f0a-4b7e-9a0e-6f1c2d3e4f50",
                    "created_at": "2026-03-03T13:00:00Z",
                    "updated_at": "2026-03-03T13:00:00Z",
                }
            ]
        },
    )


class MulherItemLista(Esquema):
    """Resumo para listagens — CPF e telefone **mascarados**."""

    id: uuid.UUID
    nome_completo: str
    nome_social: str | None
    cpf_mascarado: str | None = Field(None, validation_alias="cpf", examples=["***.982.247-**"])
    telefone_mascarado: str | None = Field(None, validation_alias="telefone", examples=["(**) *****-5678"])
    cidade: str | None
    uf: str | None
    deleted_at: datetime | None
    created_at: datetime

    @field_validator("cpf_mascarado")
    @classmethod
    def _m_cpf(cls, v: str | None) -> str | None:
        return mascarar_cpf(v)

    @field_validator("telefone_mascarado")
    @classmethod
    def _m_tel(cls, v: str | None) -> str | None:
        return mascarar_telefone(v)


class MulherFiltros(Esquema):
    q: str | None = Field(
        None, max_length=100, description="Busca por nome/nome social (sem acento, contém) ou por CPF (dígitos)."
    )
    cpf: str | None = Field(None, description="CPF exato (com ou sem máscara).")
    cidade: str | None = Field(None, max_length=100)
    servico_id: uuid.UUID | None = Field(None, description="Mulheres com vínculo com este serviço.")
    status: StatusServicoMulher | None = Field(
        None, description="Mulheres com algum vínculo neste status (combina com `servico_id`)."
    )
    incluir_excluidas: bool = Field(False, description="Inclui excluídas logicamente. **Só ADMIN/GESTOR.**")
