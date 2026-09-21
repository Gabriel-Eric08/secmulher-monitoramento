from typing import Any

from fastapi import APIRouter, Depends, Request

from webapp.deps import ApiDep, Auditor, csrf_protect
from webapp.routes._util import local_para_iso, query
from webapp.templating import render

router = APIRouter(prefix="/auditoria", dependencies=[Depends(csrf_protect)])


def comparar(antes: dict[str, Any] | None, depois: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Linhas `{campo, antes, depois, mudou}` para a tela de detalhe (campos alterados primeiro)."""
    a, d = antes or {}, depois or {}
    linhas = [{"campo": k, "antes": a.get(k), "depois": d.get(k), "mudou": a.get(k) != d.get(k)} for k in sorted(set(a) | set(d))]
    return sorted(linhas, key=lambda x: not x["mudou"])


@router.get("")
async def lista(request: Request, api: ApiDep, user: Auditor):
    params = query(request, "acao", "entidade", "mulher_id", "usuario_id", "page", page_size=20)
    for chave in ("de", "ate"):
        v = request.query_params.get(chave)
        if v:  # <input type=date> → limites do dia (hora local)
            params[chave] = local_para_iso(f"{v}T00:00:00" if chave == "de" else f"{v}T23:59:59")
    res = await api.get("/auditoria", **params)
    return render(request, "auditoria/lista.html", {"res": res, "f": request.query_params})


@router.get("/{registro_id:uid}")
async def detalhe(registro_id: str, request: Request, api: ApiDep, user: Auditor):
    reg = await api.get(f"/auditoria/{registro_id}")
    return render(request, "auditoria/detalhe.html", {"reg": reg, "linhas": comparar(reg.get("antes"), reg.get("depois"))})
