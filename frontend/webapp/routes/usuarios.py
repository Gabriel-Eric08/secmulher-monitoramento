from fastapi import APIRouter, Depends, Request

from webapp.api import ApiError
from webapp.deps import Admin, ApiDep, csrf_protect
from webapp.routes._util import avisar_erro, campos, go, query
from webapp.templating import flash, render

router = APIRouter(prefix="/usuarios", dependencies=[Depends(csrf_protect)])


@router.get("")
async def lista(request: Request, api: ApiDep, user: Admin):
    res = await api.get("/usuarios", **query(request, "q", "perfil", "ativo", "page", page_size=15))
    return render(request, "usuarios/lista.html", {"res": res, "f": request.query_params})


@router.get("/novo")
async def novo_form(request: Request, user: Admin):
    return render(request, "usuarios/form.html", {"modo": "criar", "form": {"perfil": "ATENDENTE"}, "erros": {}})


@router.post("/novo")
async def novo(request: Request, api: ApiDep, user: Admin):
    d = await campos(request, "nome", "email", "senha", "perfil")
    try:
        u = await api.post("/usuarios", json=d)
    except ApiError as e:
        erros = e.field_errors
        if e.code == "EMAIL_DUPLICADO":
            erros["email"] = e.message
        if not erros:
            avisar_erro(request, e)
        return render(request, "usuarios/form.html", {"modo": "criar", "form": {**d, "senha": ""}, "erros": erros}, status=422)
    flash(request, "success", f"Usuário {u['nome']} criado.")
    return go("/usuarios")


@router.get("/{usuario_id:uid}/editar")
async def editar_form(usuario_id: str, request: Request, api: ApiDep, user: Admin):
    u = await api.get(f"/usuarios/{usuario_id}")
    return render(request, "usuarios/form.html", {"modo": "editar", "form": u, "erros": {}, "alvo": u})


@router.post("/{usuario_id:uid}/editar")
async def editar(usuario_id: str, request: Request, api: ApiDep, user: Admin):
    d = await campos(request, "nome", "perfil", "ativo")
    try:
        await api.patch(f"/usuarios/{usuario_id}", json={"nome": d["nome"], "perfil": d["perfil"], "ativo": bool(d["ativo"])})
    except ApiError as e:
        erros = e.field_errors
        if not erros:
            avisar_erro(request, e)
        alvo = await api.get(f"/usuarios/{usuario_id}")
        return render(request, "usuarios/form.html", {"modo": "editar", "form": {**alvo, **d, "ativo": bool(d["ativo"])}, "erros": erros, "alvo": alvo}, status=422)
    flash(request, "success", "Usuário atualizado.")
    return go("/usuarios")


@router.post("/{usuario_id:uid}/senha")
async def redefinir_senha(usuario_id: str, request: Request, api: ApiDep, user: Admin):
    d = await campos(request, "nova_senha")
    try:
        await api.post(f"/usuarios/{usuario_id}/redefinir-senha", json={"nova_senha": d["nova_senha"] or ""})
        flash(request, "success", "Senha redefinida. As sessões abertas do usuário foram encerradas.")
    except ApiError as e:
        avisar_erro(request, e)
    return go(f"/usuarios/{usuario_id}/editar")
