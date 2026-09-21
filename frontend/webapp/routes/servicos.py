from fastapi import APIRouter, Depends, Request

from webapp.api import ApiError
from webapp.deps import ApiDep, Gestor, User, csrf_protect
from webapp.routes._util import avisar_erro, campos, go, query, safe_next, sem_none
from webapp.templating import flash, render

router = APIRouter(prefix="/servicos", dependencies=[Depends(csrf_protect)])


@router.get("")
async def lista(request: Request, api: ApiDep, user: User):
    params = query(request, "q", "categoria", "ativo", "page", "sort", page_size=15)
    res = await api.get("/servicos", **params)
    return render(request, "servicos/lista.html", {"res": res, "f": request.query_params})


@router.get("/novo")
async def novo_form(request: Request, user: Gestor):
    return render(request, "servicos/form.html", {"modo": "criar", "form": {"ativo": True}, "erros": {}})


@router.post("/novo")
async def novo(request: Request, api: ApiDep, user: Gestor):
    d = await campos(request, "nome", "categoria", "descricao")
    try:
        s = await api.post("/servicos", json=sem_none(d))
    except ApiError as e:
        erros = e.field_errors
        if e.code == "SERVICO_DUPLICADO":
            erros["nome"] = e.message
        if not erros:
            avisar_erro(request, e)
        return render(request, "servicos/form.html", {"modo": "criar", "form": d, "erros": erros}, status=422)
    flash(request, "success", f"Serviço “{s['nome']}” cadastrado.")
    return go("/servicos")


@router.get("/{servico_id:uid}/editar")
async def editar_form(servico_id: str, request: Request, api: ApiDep, user: Gestor):
    s = await api.get(f"/servicos/{servico_id}")
    form = {"nome": s["nome"], "categoria": s["categoria"] or "", "descricao": s["descricao"] or "", "ativo": s["ativo"]}
    return render(request, "servicos/form.html", {"modo": "editar", "form": form, "erros": {}, "servico": s})


@router.post("/{servico_id:uid}/editar")
async def editar(servico_id: str, request: Request, api: ApiDep, user: Gestor):
    d = await campos(request, "nome", "categoria", "descricao", "ativo")
    corpo = {"nome": d["nome"], "categoria": d["categoria"], "descricao": d["descricao"], "ativo": bool(d["ativo"])}
    try:
        await api.patch(f"/servicos/{servico_id}", json=corpo)
    except ApiError as e:
        erros = e.field_errors
        if e.code == "SERVICO_DUPLICADO":
            erros["nome"] = e.message
        if not erros:
            avisar_erro(request, e)
        form = {**d, "ativo": bool(d["ativo"])}
        return render(request, "servicos/form.html", {"modo": "editar", "form": form, "erros": erros, "servico": {"id": servico_id, "nome": d["nome"] or ""}}, status=422)
    flash(request, "success", "Serviço atualizado.")
    return go("/servicos")


@router.post("/{servico_id:uid}/ativo")
async def alternar_ativo(servico_id: str, request: Request, api: ApiDep, user: Gestor):
    d = await campos(request, "ativo", "next")
    try:
        s = await api.patch(f"/servicos/{servico_id}", json={"ativo": d["ativo"] == "true"})
        flash(request, "success", f"Serviço “{s['nome']}” {'ativado' if s['ativo'] else 'inativado'}.")
    except ApiError as e:
        avisar_erro(request, e)
    return go(safe_next(d["next"], "/servicos"))
