import asyncio

from fastapi import APIRouter, Depends, Request

from webapp.api import ApiError
from webapp.deps import ApiDep, Escritor, User, csrf_protect
from webapp.routes._util import avisar_erro, campos, go, local_para_iso, query, safe_next, sem_none
from webapp.templating import flash, render

router = APIRouter(prefix="/vinculos", dependencies=[Depends(csrf_protect)])


@router.get("")
async def lista(request: Request, api: ApiDep, user: User):
    params = query(request, "status", "servico_id", "mulher_id", "page", "sort", page_size=15)
    res, servicos = await asyncio.gather(api.get("/servicos-mulheres", **params), api.get("/servicos", page_size=100))
    return render(request, "vinculos/lista.html", {"res": res, "servicos": servicos["items"], "f": request.query_params})


@router.get("/novo")
async def novo_form(request: Request, api: ApiDep, user: Escritor):
    servicos = await api.get("/servicos", ativo=True, page_size=100)
    q = request.query_params
    return render(request, "vinculos/novo.html", {"servicos": servicos["items"], "mulher_id": q.get("mulher_id", ""), "mulher_nome": q.get("mulher_nome", "")})


@router.post("/novo")
async def novo(request: Request, api: ApiDep, user: Escritor):
    d = await campos(request, "mulher_id", "servico_id", "data_inicio", "observacoes", "assumir")
    if not d["mulher_id"] or not d["servico_id"]:
        flash(request, "error", "Escolha a mulher e o serviço.")
        return go("/vinculos/novo")
    corpo = sem_none({"servico_id": d["servico_id"], "data_inicio": d["data_inicio"], "observacoes": d["observacoes"]})
    if d["assumir"]:
        corpo["responsavel_id"] = user["id"]
    try:
        vinculo = await api.post(f"/mulheres/{d['mulher_id']}/servicos", json=corpo)
    except ApiError as e:
        avisar_erro(request, e)
        return go("/vinculos/novo")
    flash(request, "success", "Serviço vinculado (status inicial: Solicitado).")
    return go(f"/vinculos/{vinculo['id']}")


@router.get("/{vinculo_id:uid}")
async def detalhe(vinculo_id: str, request: Request, api: ApiDep, user: User):
    vinculo, eventos, transicoes = await asyncio.gather(
        api.get(f"/servicos-mulheres/{vinculo_id}"),
        api.get(f"/servicos-mulheres/{vinculo_id}/eventos", page_size=50),
        api.get(f"/servicos-mulheres/{vinculo_id}/transicoes-permitidas"),
    )
    return render(request, "vinculos/detalhe.html", {"v": vinculo, "eventos": eventos["items"], "transicoes": transicoes})


@router.post("/{vinculo_id:uid}/editar")
async def editar(vinculo_id: str, request: Request, api: ApiDep, user: Escritor):
    d = await campos(request, "data_inicio", "observacoes", "assumir", "next")
    corpo: dict = {"observacoes": d["observacoes"]}
    if d["data_inicio"]:
        corpo["data_inicio"] = d["data_inicio"]
    if d["assumir"]:
        corpo["responsavel_id"] = user["id"]
    try:
        await api.patch(f"/servicos-mulheres/{vinculo_id}", json=corpo)
        flash(request, "success", "Vínculo atualizado.")
    except ApiError as e:
        avisar_erro(request, e)
    return go(safe_next(d["next"], f"/vinculos/{vinculo_id}"))


@router.post("/{vinculo_id:uid}/transicao")
async def transicao(vinculo_id: str, request: Request, api: ApiDep, user: Escritor):
    d = await campos(request, "status_novo", "motivo", "ocorrido_em", "next")
    corpo = sem_none({"status_novo": d["status_novo"], "motivo": d["motivo"], "ocorrido_em": local_para_iso(d["ocorrido_em"])})
    try:
        v = await api.post(f"/servicos-mulheres/{vinculo_id}/transicoes", json=corpo)
        flash(request, "success", f"Status alterado para {v['status'].replace('_', ' ').title()}.")
    except ApiError as e:
        avisar_erro(request, e)
    return go(safe_next(d["next"], f"/vinculos/{vinculo_id}"))
