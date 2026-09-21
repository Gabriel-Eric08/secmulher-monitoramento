import uuid
from datetime import date, datetime

from pydantic import ConfigDict, Field, field_validator

from app.modules.eventos.schema import nao_futuro
from app.modules.servicos.schema import ServicoResumo
from app.shared.enums import StatusServicoMulher
from app.shared.schemas import Esquema


class MulherMinima(Esquema):
    id: uuid.UUID
    nome_completo: str
    nome_social: str | None = None


class VinculoCriar(Esquema):
    servico_id: uuid.UUID = Field(..., description="Serviço do catálogo (deve estar ativo).")
    data_inicio: date | None = Field(None, description="Padrão: hoje.")
    responsavel_id: uuid.UUID | None = Field(None, description="Usuário responsável (deve estar ativo).")
    observacoes: str | None = Field(None, max_length=5000)


class VinculoAtualizar(Esquema):
    """Atualização de dados do vínculo. **Não altera o status** — use `POST .../transicoes`."""

    data_inicio: date | None = None
    responsavel_id: uuid.UUID | None = None
    observacoes: str | None = Field(None, max_length=5000)

    @field_validator("data_inicio")
    @classmethod
    def _nao_nulo(cls, v: date | None) -> date | None:
        if v is None:
            raise ValueError("data_inicio não pode ser nula.")
        return v


class TransicaoCriar(Esquema):
    status_novo: StatusServicoMulher = Field(..., examples=["EM_ANALISE"])
    motivo: str | None = Field(
        None,
        min_length=3,
        max_length=2000,
        description="Justificativa. **Obrigatória** ao ir para `SUSPENSO` ou `CANCELADO`.",
        examples=["Documentação recebida e conferida."],
    )
    ocorrido_em: datetime | None = Field(None, description="Quando a mudança ocorreu de fato (padrão: agora).")

    _v_ocorrido = field_validator("ocorrido_em")(nao_futuro)


class VinculoLeitura(Esquema):
    id: uuid.UUID
    mulher: MulherMinima
    servico: ServicoResumo
    status: StatusServicoMulher = Field(..., description="**Estado atual** do vínculo.")
    data_inicio: date
    data_encerramento: date | None = Field(None, description="Preenchida ao entrar em status final.")
    responsavel_id: uuid.UUID | None
    observacoes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "7e6d5c4b-3a21-4f0e-9d8c-b7a695847362",
                    "mulher": {"id": "9d2e7f10-3a4b-4c5d-8e6f-1a2b3c4d5e6f", "nome_completo": "Maria Souza da Silva", "nome_social": None},
                    "servico": {"id": "5c1f0a7e-2d3b-4c8e-9b1a-7e6d5c4b3a21", "nome": "Acompanhamento psicológico", "categoria": "Saúde"},
                    "status": "EM_ATENDIMENTO",
                    "data_inicio": "2026-03-03",
                    "data_encerramento": None,
                    "responsavel_id": "0b5d5c2e-1f0a-4b7e-9a0e-6f1c2d3e4f50",
                    "observacoes": None,
                    "created_at": "2026-03-03T13:05:00Z",
                    "updated_at": "2026-03-10T14:00:00Z",
                }
            ]
        },
    )


class StatusOpcao(Esquema):
    valor: StatusServicoMulher
    rotulo: str


class TransicoesPermitidas(Esquema):
    status_atual: StatusServicoMulher
    permitidas: list[StatusOpcao] = Field(..., description="Próximos status válidos (vazio se o vínculo está encerrado).")
    exigem_motivo: list[StatusServicoMulher] = Field(..., description="Destinos que exigem `motivo`.")


class VinculoFiltros(Esquema):
    mulher_id: uuid.UUID | None = None
    servico_id: uuid.UUID | None = None
    status: StatusServicoMulher | None = None
    responsavel_id: uuid.UUID | None = None
    data_inicio_de: date | None = None
    data_inicio_ate: date | None = None
