"""Jinja2: ambiente, filtros de formatação (pt-BR) e `render()` com o contexto comum das páginas."""

import secrets
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from webapp.config import get_settings

BASE = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE / "templates"))


def _tz() -> timezone | ZoneInfo:
    try:
        return ZoneInfo(get_settings().timezone)
    except ZoneInfoNotFoundError:  # sem tzdata no SO: usa UTC-3 (Brasília)
        return timezone(timedelta(hours=-3))


def _parse(valor: Any) -> datetime | None:
    if not valor:
        return None
    if isinstance(valor, datetime):
        dt = valor
    else:
        try:
            dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def dt(valor: Any, formato: str = "%d/%m/%Y %H:%M") -> str:
    d = _parse(valor)
    return d.astimezone(_tz()).strftime(formato) if d else "—"


def dia(valor: Any) -> str:
    if not valor:
        return "—"
    if isinstance(valor, date) and not isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y")
    texto = str(valor)
    if len(texto) == 10:  # AAAA-MM-DD (data pura, sem fuso)
        try:
            return date.fromisoformat(texto).strftime("%d/%m/%Y")
        except ValueError:
            return texto
    return dt(valor, "%d/%m/%Y")


def ha(valor: Any) -> str:
    d = _parse(valor)
    if not d:
        return "—"
    seg = (datetime.now(timezone.utc) - d).total_seconds()
    if seg < 0:
        return "agora"
    for limite, unidade, div in ((60, "", 1), (3600, "min", 60), (86400, "h", 3600), (86400 * 30, "d", 86400)):
        if seg < limite:
            return "agora" if not unidade else f"há {int(seg // div)} {unidade}"
    return dia(valor)


def cpf(valor: str | None) -> str:
    if not valor or len(valor) != 11 or not valor.isdigit():
        return valor or "—"
    return f"{valor[:3]}.{valor[3:6]}.{valor[6:9]}-{valor[9:]}"


def cep(valor: str | None) -> str:
    if not valor or len(valor) != 8 or not valor.isdigit():
        return valor or "—"
    return f"{valor[:5]}-{valor[5:]}"


def tamanho(n: int | None) -> str:
    if n is None:
        return "—"
    valor = float(n)
    for unidade in ("B", "KB", "MB", "GB"):
        if valor < 1024 or unidade == "GB":
            return f"{valor:.0f} {unidade}" if unidade == "B" else f"{valor:.1f} {unidade}".replace(".", ",")
        valor /= 1024
    return str(n)


def iniciais(nome: str | None) -> str:
    partes = [p for p in (nome or "?").split() if p]
    return (partes[0][0] + (partes[-1][0] if len(partes) > 1 else "")).upper()


def vazio(valor: Any) -> Any:
    return valor if valor not in (None, "") else "—"


for _nome, _fn in {"dt": dt, "dia": dia, "ha": ha, "cpf": cpf, "cep": cep, "tamanho": tamanho, "iniciais": iniciais, "vazio": vazio}.items():
    templates.env.filters[_nome] = _fn

# ---------- apresentação por domínio ----------
STATUS_CLASSE = {
    "SOLICITADO": "st-solicitado",
    "EM_ANALISE": "st-analise",
    "EM_ATENDIMENTO": "st-atendimento",
    "SUSPENSO": "st-suspenso",
    "CONCLUIDO": "st-concluido",
    "CANCELADO": "st-cancelado",
}
STATUS_ICONE = {
    "SOLICITADO": "bi-inbox",
    "EM_ANALISE": "bi-search",
    "EM_ATENDIMENTO": "bi-heart-pulse",
    "SUSPENSO": "bi-pause-circle",
    "CONCLUIDO": "bi-check2-circle",
    "CANCELADO": "bi-x-circle",
}
EVENTO_ICONE = {
    "ATENDIMENTO": "bi-chat-heart",
    "ENCAMINHAMENTO": "bi-send",
    "CONTATO": "bi-telephone",
    "VISITA": "bi-house-heart",
    "MUDANCA_STATUS": "bi-arrow-left-right",
    "DOCUMENTO_ANEXADO": "bi-paperclip",
    "OBSERVACAO": "bi-sticky",
    "RETIFICACAO": "bi-pencil-square",
    "OUTRO": "bi-circle",
}
ACAO_CLASSE = {
    "CREATE": "ac-criar", "UPDATE": "ac-editar", "DELETE": "ac-excluir", "RESTORE": "ac-criar",
    "STATUS_CHANGE": "ac-status", "UPLOAD": "ac-arquivo", "DOWNLOAD": "ac-arquivo",
    "READ_SENSITIVE": "ac-leitura", "LOGIN": "ac-login", "LOGIN_FAILED": "ac-excluir", "LOGOUT": "ac-login",
}
templates.env.globals.update(
    STATUS_CLASSE=STATUS_CLASSE, STATUS_ICONE=STATUS_ICONE, EVENTO_ICONE=EVENTO_ICONE, ACAO_CLASSE=ACAO_CLASSE
)

PERFIS = {
    "escrita": {"ADMIN", "GESTOR", "ATENDENTE"},
    "gestao": {"ADMIN", "GESTOR"},
    "admin": {"ADMIN"},
    "auditoria": {"ADMIN", "GESTOR", "AUDITOR"},
}


def csrf_token(request: Request) -> str:
    if "csrf" not in request.session:
        request.session["csrf"] = secrets.token_urlsafe(32)
    return request.session["csrf"]


def flash(request: Request, tipo: str, mensagem: str) -> None:
    """Mensagem exibida (toast) na próxima página renderizada. tipo: success | error | warning | info."""
    fila = request.session.get("_flash", [])
    fila.append({"tipo": tipo, "msg": mensagem})
    request.session["_flash"] = fila[-5:]


def _rotulo_factory(meta: dict[str, Any] | None):
    def rot(lista: str, valor: str | None) -> str:
        if valor is None:
            return "—"
        for o in (meta or {}).get(lista, []):
            if o["valor"] == valor:
                return o["rotulo"]
        return valor

    return rot


def _qs_factory(request: Request):
    def qs(**alterar: Any) -> str:
        """Query string atual com alterações (valor None remove). Mudar filtros volta para a página 1."""
        params = {k: v for k, v in request.query_params.items()}
        if "page" not in alterar and alterar:
            params.pop("page", None)
        for k, v in alterar.items():
            if v is None or v == "":
                params.pop(k, None)
            else:
                params[k] = str(v)
        return ("?" + urlencode(params)) if params else "?"

    return qs


def contexto(request: Request, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    if "session" not in request.scope:  # ex.: handler de 500 (fora do SessionMiddleware)
        request.scope["session"] = {}
    user = request.session.get("user")
    perfil = user["perfil"] if user else None
    ctx: dict[str, Any] = {
        "request": request,
        "user": user,
        "can": {k: perfil in v for k, v in PERFIS.items()},
        "flash": request.session.pop("_flash", []),
        "meta": getattr(request.app.state, "meta", None),
        "rot": _rotulo_factory(getattr(request.app.state, "meta", None)),
        "qs": _qs_factory(request),
        "csrf": csrf_token(request),
        "app_name": get_settings().app_name,
        "path": request.url.path,
    }
    ctx.update(extra or {})
    return ctx


def render(request: Request, nome: str, extra: dict[str, Any] | None = None, status: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(request, nome, contexto(request, extra), status_code=status)
