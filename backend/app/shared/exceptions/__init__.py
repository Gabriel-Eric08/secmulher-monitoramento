from typing import Any


class AppError(Exception):
    """Erro de domínio convertido no envelope padrão `ErroResposta` pelos handlers globais."""

    status_code: int = 400
    default_code: str = "ERRO"
    default_message: str = "Erro."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.code = code or self.default_code
        self.details = details or []
        super().__init__(self.message)


class RequisicaoInvalida(AppError):
    status_code = 400
    default_code = "REQUISICAO_INVALIDA"
    default_message = "Requisição inválida."


class NaoAutenticado(AppError):
    status_code = 401
    default_code = "NAO_AUTENTICADO"
    default_message = "Autenticação necessária."


class AcessoNegado(AppError):
    status_code = 403
    default_code = "ACESSO_NEGADO"
    default_message = "Você não tem permissão para esta operação."


class NaoEncontrado(AppError):
    status_code = 404
    default_code = "NAO_ENCONTRADO"
    default_message = "Recurso não encontrado."


class Conflito(AppError):
    status_code = 409
    default_code = "CONFLITO"
    default_message = "A operação conflita com o estado atual do recurso."


class ArquivoMuitoGrande(AppError):
    status_code = 413
    default_code = "ARQUIVO_MUITO_GRANDE"
    default_message = "Arquivo maior que o tamanho máximo permitido."


class TipoArquivoNaoPermitido(AppError):
    status_code = 415
    default_code = "TIPO_ARQUIVO_NAO_PERMITIDO"
    default_message = "Tipo de arquivo não permitido."


class ValidacaoFalhou(AppError):
    status_code = 422
    default_code = "VALIDACAO_FALHOU"
    default_message = "Falha de validação."


class ContaBloqueada(AppError):
    status_code = 423
    default_code = "CONTA_BLOQUEADA"
    default_message = "Conta temporariamente bloqueada por excesso de tentativas."
