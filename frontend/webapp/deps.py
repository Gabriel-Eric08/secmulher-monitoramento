"""Dependências das rotas: cliente da API, usuário logado, permissão por perfil e proteção CSRF."""

import secrets
import time
from typing import Annotated, Any

from fastapi import Depends, Request

from webapp.api import Api, ApiError, SessionExpired
from webapp.config import get_settings
from webapp.templating import PERFIS

_META_TTL = 600  # os enums só mudam com deploy; 10 min de cache é folgado


def get_api(request: Request) -> Api:
    return Api(request.app.state.http, request.session, get_settings().api_prefix)


ApiDep = Annotated[Api, Depends(get_api)]


async def _garantir_meta(request: Request, api: Api) -> None:
    estado = request.app.state
    if getattr(estado, "meta", None) is None or time.time() - getattr(estado, "meta_em", 0) > _META_TTL:
        estado.meta = await api.get("/meta/enums")
        estado.meta_em = time.time()


async def require_user(request: Request, api: ApiDep) -> dict[str, Any]:
    if not request.session.get("access") or not request.session.get("user"):
        raise SessionExpired()
    await api.ensure_fresh()
    await _garantir_meta(request, api)
    return request.session["user"]


User = Annotated[dict[str, Any], Depends(require_user)]


def exigir(grupo: str):
    """Restringe a rota a um grupo de perfis (`escrita`, `gestao`, `admin`, `auditoria`)."""

    async def _dep(user: User) -> dict[str, Any]:
        if user["perfil"] not in PERFIS[grupo]:
            raise ApiError(403, "ACESSO_NEGADO", "Você não tem permissão para acessar esta página.")
        return user

    return _dep


Escritor = Annotated[dict[str, Any], Depends(exigir("escrita"))]
Gestor = Annotated[dict[str, Any], Depends(exigir("gestao"))]
Admin = Annotated[dict[str, Any], Depends(exigir("admin"))]
Auditor = Annotated[dict[str, Any], Depends(exigir("auditoria"))]


async def csrf_protect(request: Request) -> None:
    """Exige `csrf_token` (campo do formulário) igual ao da sessão em todo POST."""
    if request.method != "POST":
        return
    form = await request.form()
    enviado = str(form.get("csrf_token", ""))
    esperado = request.session.get("csrf", "")
    if not esperado or not secrets.compare_digest(enviado, esperado):
        raise ApiError(403, "CSRF_INVALIDO", "Formulário expirado ou inválido. Recarregue a página e tente de novo.")
