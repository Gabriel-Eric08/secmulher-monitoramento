import asyncio

from fastapi import APIRouter, Depends, Request

from webapp.api import ApiError
from webapp.deps import ApiDep, Escritor, User, csrf_protect
from webapp.routes._util import avisar_erro, campos, go, local_para_iso, query, safe_next, sem_none
from webapp.templating import flash, render

router = APIRouter(prefix="/eventos", dependencies=[Depends(csrf_protect)])


@router.get("")
async def lista(request: Request, api: ApiDep, user: User):
    params = query(request, "tipo", "mulher_id", "de", "ate", "page", page_size=20)
    res = await api.get("/eventos", **params)
    return render(request, "eventos/lista.html", {"res": res, "f": request.query_params})


@router.get("/novo")
async def novo_form(request: Request, user: Escritor):
    q = request.query_params
    return render(request, "eventos/novo.html", {"mulher_id": q.get("mulher_id", ""), "mulher_nome": q.get("mulher_nome", ""), "form": {}})


@router.post("/novo")
async def novo(request: Request, api: ApiDep, user: Escritor):
    d = await campos(request, "mulher_id", "tipo", "titulo", "descricao", "ocorrido_em")
    if not d["mulher_id"]:
        flash(request, "error", "Escolha a mulher a que o evento se refere.")
        return go("/eventos/novo")
    corpo = sem_none({**d, "ocorrido_em": local_para_iso(d["ocorrido_em"])})
    try:
        ev = await api.post("/eventos", json=corpo)
    except ApiError as e:
        avisar_erro(request, e)
        return go("/eventos/novo")
    flash(request, "success", "Evento registrado.")
    return go(f"/eventos/{ev['id']}")


@router.get("/{evento_id:uid}")
async def detalhe(evento_id: str, request: Request, api: ApiDep, user: User):
    ev = await api.get(f"/eventos/{evento_id}")
    ids = ev["retificado_por"]
    retificacoes, original = await asyncio.gather(
        asyncio.gather(*[api.get(f"/eventos/{i}") for i in ids]),
        api.get(f"/eventos/{ev['corrige_evento_id']}") if ev["corrige_evento_id"] else asyncio.sleep(0),
    )
    return render(request, "eventos/detalhe.html", {"ev": ev, "retificacoes": list(retificacoes), "original": original or None})


@router.post("/{evento_id:uid}/retificar")
async def retificar(evento_id: str, request: Request, api: ApiDep, user: Escritor):
    d = await campos(request, "titulo", "descricao", "ocorrido_em", "next")
    corpo = sem_none({"titulo": d["titulo"], "descricao": d["descricao"], "ocorrido_em": local_para_iso(d["ocorrido_em"])})
    try:
        nova = await api.post(f"/eventos/{evento_id}/retificacoes", json=corpo)
        flash(request, "success", "Retificação registrada. O evento original foi preservado.")
        return go(safe_next(d["next"], f"/eventos/{nova['id']}"))
    except ApiError as e:
        avisar_erro(request, e)
    return go(safe_next(d["next"], f"/eventos/{evento_id}"))
