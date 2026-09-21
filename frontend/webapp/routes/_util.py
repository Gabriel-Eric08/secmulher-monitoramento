"""Helpers compartilhados pelas rotas."""

from datetime import datetime
from typing import Any

from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.convertors import Convertor, register_url_convertor

from webapp.api import ApiError
from webapp.templating import _tz, flash


class UidConvertor(Convertor[str]):
    """`{id:uid}` casa só UUIDs (evita capturar /nova, /buscar…) e mantém o valor como texto."""

    regex = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"

    def convert(self, value: str) -> str:
        return value

    def to_string(self, value: str) -> str:
        return str(value)


register_url_convertor("uid", UidConvertor())


def go(url: str, status: int = 303) -> RedirectResponse:
    return RedirectResponse(url, status_code=status)


def safe_next(valor: str | None, padrao: str) -> str:
    """Só aceita caminhos locais (evita open redirect)."""
    if valor and valor.startswith("/") and not valor.startswith("//") and "\\" not in valor:
        return valor
    return padrao


async def campos(request: Request, *nomes: str) -> dict[str, str | None]:
    """Lê campos do formulário; texto vazio vira None."""
    form = await request.form()
    out: dict[str, str | None] = {}
    for nome in nomes:
        v = form.get(nome)
        out[nome] = v.strip() if isinstance(v, str) and v.strip() else None
    return out


def sem_none(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


def local_para_iso(valor: str | None) -> str | None:
    """`<input type=datetime-local>` (hora local de Brasília) → ISO-8601 com fuso, para a API."""
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor).replace(tzinfo=_tz()).isoformat()
    except ValueError:
        return valor


def query(request: Request, *chaves: str, **padroes: Any) -> dict[str, Any]:
    """Subconjunto dos parâmetros de query da página (repassados à API), com padrões."""
    out: dict[str, Any] = {c: request.query_params.get(c) for c in chaves}
    for k, v in padroes.items():
        out[k] = out.get(k) or v
    return out


def avisar_erro(request: Request, e: ApiError) -> None:
    """Toast de erro com a mensagem da API (mais os detalhes por campo, se houver)."""
    msg = e.message
    if e.details:
        msg += " " + "; ".join(f"{d.get('field') or ''} {d.get('issue', '')}".strip() for d in e.details)
    flash(request, "error", msg)
