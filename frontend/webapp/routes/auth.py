from fastapi import APIRouter, Depends, Request

from webapp.api import ApiError
from webapp.deps import ApiDep, csrf_protect
from webapp.routes._util import campos, go, safe_next
from webapp.templating import flash, render

router = APIRouter(dependencies=[Depends(csrf_protect)])


@router.get("/login")
async def login_form(request: Request):
    if request.session.get("access") and request.session.get("user"):
        return go("/")
    return render(request, "login.html", {"next": request.query_params.get("next", ""), "email": ""})


@router.post("/login")
async def login(request: Request, api: ApiDep):
    dados = await campos(request, "email", "senha", "next")
    destino = safe_next(dados["next"], "/")
    try:
        tokens = await api.post("/auth/login", json={"email": dados["email"] or "", "senha": dados["senha"] or ""})
    except ApiError as e:
        return render(
            request, "login.html", {"erro": e.message, "email": dados["email"] or "", "next": destino}, status=e.status
        )
    csrf = request.session.get("csrf")
    request.session.clear()  # nova sessão após autenticar
    request.session["csrf"] = csrf
    request.session["access"], request.session["refresh"] = tokens["access_token"], tokens["refresh_token"]
    me = await api.get("/auth/me")
    request.session["user"] = {"id": me["id"], "nome": me["nome"], "email": me["email"], "perfil": me["perfil"]}
    flash(request, "success", f"Bem-vinda, {me['nome'].split()[0]}!")
    return go(destino)


@router.post("/logout")
async def logout(request: Request, api: ApiDep):
    refresh = request.session.get("refresh")
    if refresh and request.session.get("access"):
        try:
            await api.post("/auth/logout", json={"refresh_token": refresh})
        except Exception:
            pass  # sair sempre deve funcionar no front, mesmo com a API fora do ar
    request.session.clear()
    flash(request, "info", "Você saiu do sistema.")
    return go("/login")
