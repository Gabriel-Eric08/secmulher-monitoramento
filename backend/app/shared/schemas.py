from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Esquema(BaseModel):
    """Base de todos os schemas da API."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


class ErroDetalhe(Esquema):
    field: str | None = Field(None, description="Campo relacionado ao erro (quando houver).", examples=["cpf"])
    issue: str = Field(..., description="Descrição do problema.", examples=["CPF inválido"])


class ErroCorpo(Esquema):
    code: str = Field(..., description="Código estável de erro, para o front tratar.", examples=["CPF_DUPLICADO"])
    message: str = Field(..., description="Mensagem legível (pt-BR).", examples=["Já existe uma mulher cadastrada com este CPF."])
    details: list[ErroDetalhe] = Field(default_factory=list, description="Detalhes por campo.")
    request_id: str | None = Field(None, description="Identificador da requisição (também no header `X-Request-ID`).")


class ErroResposta(Esquema):
    """Envelope padrão de erro — usado em TODOS os status 4xx/5xx."""

    error: ErroCorpo

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "error": {
                        "code": "SERVICO_MULHER_TRANSICAO_INVALIDA",
                        "message": "Não é possível ir de CONCLUIDO para EM_ATENDIMENTO.",
                        "details": [{"field": "status_novo", "issue": "transição não permitida"}],
                        "request_id": "3f2b1c9e5a7d4c0f8b6a1d2e3c4b5a69",
                    }
                }
            ]
        }
    )


_DESCRICOES = {
    400: "Requisição malformada.",
    401: "Não autenticado (token ausente, inválido ou expirado).",
    403: "Sem permissão para a operação.",
    404: "Recurso não encontrado.",
    405: "Método não permitido para o recurso.",
    409: "Conflito com regra de negócio ou estado atual do recurso.",
    413: "Arquivo maior que o máximo permitido.",
    415: "Tipo de arquivo não permitido.",
    422: "Falha de validação dos dados enviados.",
    423: "Conta temporariamente bloqueada.",
}


def erros(*codigos: int) -> dict[int | str, dict[str, Any]]:
    """Monta o `responses=` de uma rota com o envelope `ErroResposta`."""
    return {c: {"model": ErroResposta, "description": _DESCRICOES[c]} for c in codigos}
