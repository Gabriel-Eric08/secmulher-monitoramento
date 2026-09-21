import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.context import obter_contexto
from app.shared.exceptions import AppError

log = logging.getLogger("app.errors")

_CODIGOS_HTTP = {
    400: "REQUISICAO_INVALIDA",
    401: "NAO_AUTENTICADO",
    403: "ACESSO_NEGADO",
    404: "ROTA_NAO_ENCONTRADA",
    405: "METODO_NAO_PERMITIDO",
    413: "ARQUIVO_MUITO_GRANDE",
}


def _envelope(
    status: int, code: str, message: str, details: list[dict[str, Any]] | None = None
) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return JSONResponse(
        status_code=status,
        headers=headers,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or [],
                "request_id": obter_contexto()["request_id"],
            }
        },
    )


async def _app_error(_: Request, exc: AppError) -> JSONResponse:
    return _envelope(exc.status_code, exc.code, exc.message, exc.details)


async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _CODIGOS_HTTP.get(exc.status_code, "ERRO_HTTP")
    return _envelope(exc.status_code, code, str(exc.detail))


async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    details = []
    for err in exc.errors():
        loc = [str(p) for p in err["loc"] if p not in ("body", "query", "path", "form")]
        details.append({"field": ".".join(loc) or None, "issue": err["msg"]})
    return _envelope(422, "VALIDACAO_FALHOU", "Os dados enviados são inválidos.", details)


async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
    log.exception("Erro não tratado", exc_info=exc)
    return _envelope(500, "ERRO_INTERNO", "Erro interno do servidor.")


def registrar_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled)
