from fastapi import APIRouter, Depends, Request

from webapp.api import ApiError
from webapp.deps import ApiDep, User, csrf_protect
from webapp.routes._util import campos, go
from webapp.templating import flash, render

router = APIRouter(prefix="/perfil", dependencies=[Depends(csrf_protect)])


@router.get("")
async def perfil(request: Request, api: ApiDep, user: User):
    me = await api.get("/auth/me")
    return render(request, "perfil/perfil.html", {"me": me, "erros": {}})


@router.post("/senha")
async def alterar_senha(request: Request, api: ApiDep, user: User):
    d = await campos(request, "senha_atual", "nova_senha", "confirmar")
    erros: dict[str, str] = {}
    if d["nova_senha"] != d["confirmar"]:
        erros["confirmar"] = "A confirmação não confere com a nova senha."
    else:
        try:
            await api.post("/auth/alterar-senha", json={"senha_atual": d["senha_atual"] or "", "nova_senha": d["nova_senha"] or ""})
        except ApiError as e:
            erros = e.field_errors
            if e.code == "SENHA_ATUAL_INCORRETA":
                erros["senha_atual"] = e.message
            elif not erros:
                erros["nova_senha"] = e.message
    if erros:
        me = await api.get("/auth/me")
        return render(request, "perfil/perfil.html", {"me": me, "erros": erros}, status=422)
    # a API revoga todos os refresh tokens ao trocar a senha: o usuário entra de novo
    request.session.clear()
    flash(request, "success", "Senha alterada. Entre novamente com a nova senha.")
    return go("/login")
