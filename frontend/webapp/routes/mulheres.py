import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from webapp.api import ApiError
from webapp.deps import ApiDep, Escritor, Gestor, User, csrf_protect
from webapp.routes._util import avisar_erro, campos, go, local_para_iso, query, safe_next, sem_none
from webapp.templating import flash, render

router = APIRouter(dependencies=[Depends(csrf_protect)])

CAMPOS = [
    "nome_completo", "nome_social", "cpf", "rg", "data_nascimento", "telefone", "telefone_alt", "email",
    "logradouro", "numero", "complemento", "bairro", "cidade", "uf", "cep", "observacoes",
]
ABAS = ("visao", "servicos", "linha", "documentos")


# ---------- listagem (aba principal) ----------
@router.get("/")
async def raiz(user: User):
    return go("/mulheres")


@router.get("/mulheres")
async def lista(request: Request, api: ApiDep, user: User):
    params = query(request, "q", "cidade", "servico_id", "status", "page", "sort", page_size=15)
    if request.query_params.get("incluir_excluidas") == "true" and user["perfil"] in ("ADMIN", "GESTOR"):
        params["incluir_excluidas"] = True
    res, servicos, total, *por_status = await asyncio.gather(
        api.get("/mulheres", **params),
        api.get("/servicos", ativo=True, page_size=100),
        api.get("/mulheres", page_size=1),
        *[api.get("/servicos-mulheres", status=s, page_size=1) for s in ("SOLICITADO", "EM_ANALISE", "EM_ATENDIMENTO")],
    )
    cards = {
        "total": total["total"],
        "SOLICITADO": por_status[0]["total"],
        "EM_ANALISE": por_status[1]["total"],
        "EM_ATENDIMENTO": por_status[2]["total"],
    }
    return render(request, "mulheres/lista.html", {"res": res, "servicos": servicos["items"], "cards": cards, "f": request.query_params})


@router.get("/mulheres/buscar")
async def buscar(request: Request, api: ApiDep, user: User):
    """JSON para o seletor de mulher (autocompletar) dos formulários e filtros."""
    q = (request.query_params.get("q") or "").strip()
    if len(q) < 2:
        return JSONResponse([])
    res = await api.get("/mulheres", q=q, page_size=8)
    return JSONResponse(
        [{"id": m["id"], "nome": m["nome_completo"], "sub": m["cpf_mascarado"] or m["cidade"] or ""} for m in res["items"]]
    )


# ---------- cadastro ----------
def _payload(dados: dict[str, str | None], criar: bool) -> dict[str, Any]:
    payload: dict[str, Any] = dict(dados)
    return sem_none(payload) if criar else payload  # na edição, None limpa o campo


def _erros_form(e: ApiError) -> dict[str, str]:
    erros = e.field_errors
    if e.code == "CPF_DUPLICADO":
        erros["cpf"] = e.message
    return erros


@router.get("/mulheres/nova")
async def nova_form(request: Request, user: Escritor):
    return render(request, "mulheres/form.html", {"modo": "criar", "form": {}, "erros": {}})


@router.post("/mulheres/nova")
async def nova(request: Request, api: ApiDep, user: Escritor):
    dados = await campos(request, *CAMPOS)
    try:
        criada = await api.post("/mulheres", json=_payload(dados, True))
    except ApiError as e:
        erros = _erros_form(e)
        if not erros:
            avisar_erro(request, e)
        return render(request, "mulheres/form.html", {"modo": "criar", "form": dados, "erros": erros}, status=422 if e.status < 500 else e.status)
    flash(request, "success", f"{criada['nome_completo']} foi cadastrada.")
    return go(f"/mulheres/{criada['id']}")


@router.get("/mulheres/{mulher_id:uid}/editar")
async def editar_form(mulher_id: str, request: Request, api: ApiDep, user: Escritor):
    mulher = await api.get(f"/mulheres/{mulher_id}")
    form = {c: ("" if mulher.get(c) is None else mulher[c]) for c in CAMPOS}
    return render(request, "mulheres/form.html", {"modo": "editar", "form": form, "erros": {}, "mulher": mulher})


@router.post("/mulheres/{mulher_id:uid}/editar")
async def editar(mulher_id: str, request: Request, api: ApiDep, user: Escritor):
    dados = await campos(request, *CAMPOS)
    try:
        await api.patch(f"/mulheres/{mulher_id}", json=_payload(dados, False))
    except ApiError as e:
        erros = _erros_form(e)
        if not erros:
            avisar_erro(request, e)
        mulher = {"id": mulher_id, "nome_completo": dados["nome_completo"] or ""}
        return render(request, "mulheres/form.html", {"modo": "editar", "form": dados, "erros": erros, "mulher": mulher}, status=422 if e.status < 500 else e.status)
    flash(request, "success", "Cadastro atualizado.")
    return go(f"/mulheres/{mulher_id}")


# ---------- detalhe (abas) ----------
@router.get("/mulheres/{mulher_id:uid}")
async def detalhe(mulher_id: str, request: Request, api: ApiDep, user: User):
    aba = request.query_params.get("aba", "visao")
    aba = aba if aba in ABAS else "visao"
    pode_escrever = user["perfil"] in ("ADMIN", "GESTOR", "ATENDENTE")
    try:
        resumo = await api.get(f"/mulheres/{mulher_id}/resumo", eventos=8)
    except ApiError as e:
        if e.status == 404 and user["perfil"] in ("ADMIN", "GESTOR"):
            excluida = await api.get(f"/mulheres/{mulher_id}", incluir_excluida=True)  # 404 se nunca existiu
            return render(request, "mulheres/excluida.html", {"mulher": excluida})
        raise

    extra: dict[str, Any] = {"resumo": resumo, "mulher": resumo["mulher"], "aba": aba}
    tarefas: dict[str, Any] = {}
    if aba == "linha":
        tarefas["linha"] = api.get(
            f"/mulheres/{mulher_id}/eventos", **query(request, "tipo", "servico_mulher_id", "de", "ate", "page", page_size=15)
        )
    if aba == "documentos":
        tarefas["docs"] = api.get(f"/mulheres/{mulher_id}/documentos", **query(request, "q", "page", page_size=12))
    if pode_escrever and aba in ("visao", "servicos"):
        tarefas["catalogo"] = api.get("/servicos", ativo=True, page_size=100)
    resultados = dict(zip(tarefas, await asyncio.gather(*tarefas.values()), strict=True))
    extra.update(linha=resultados.get("linha"), docs=resultados.get("docs"), catalogo=(resultados.get("catalogo") or {}).get("items", []))
    extra["f"] = request.query_params
    return render(request, "mulheres/detalhe.html", extra)


# ---------- exclusão lógica ----------
@router.post("/mulheres/{mulher_id:uid}/excluir")
async def excluir(mulher_id: str, request: Request, api: ApiDep, user: Gestor):
    motivo = (await campos(request, "motivo"))["motivo"] or ""
    try:
        await api.delete(f"/mulheres/{mulher_id}", motivo=motivo)
    except ApiError as e:
        avisar_erro(request, e)
        return go(f"/mulheres/{mulher_id}")
    flash(request, "success", "Cadastro excluído (exclusão lógica: o histórico foi preservado).")
    return go("/mulheres")


@router.post("/mulheres/{mulher_id:uid}/restaurar")
async def restaurar(mulher_id: str, request: Request, api: ApiDep, user: Gestor):
    try:
        await api.post(f"/mulheres/{mulher_id}/restaurar")
        flash(request, "success", "Cadastro restaurado.")
    except ApiError as e:
        avisar_erro(request, e)
    return go(f"/mulheres/{mulher_id}")


# ---------- ações a partir do detalhe (modais) ----------
@router.post("/mulheres/{mulher_id:uid}/servicos")
async def vincular(mulher_id: str, request: Request, api: ApiDep, user: Escritor):
    d = await campos(request, "servico_id", "data_inicio", "observacoes", "assumir", "next")
    corpo = sem_none({"servico_id": d["servico_id"], "data_inicio": d["data_inicio"], "observacoes": d["observacoes"]})
    if d["assumir"]:
        corpo["responsavel_id"] = user["id"]
    try:
        await api.post(f"/mulheres/{mulher_id}/servicos", json=corpo)
        flash(request, "success", "Serviço vinculado (status inicial: Solicitado).")
    except ApiError as e:
        avisar_erro(request, e)
    return go(safe_next(d["next"], f"/mulheres/{mulher_id}?aba=servicos"))


@router.post("/mulheres/{mulher_id:uid}/eventos")
async def registrar_evento(mulher_id: str, request: Request, api: ApiDep, user: Escritor):
    d = await campos(request, "tipo", "titulo", "descricao", "ocorrido_em", "servico_mulher_id", "next")
    proximo = d.pop("next")
    corpo = sem_none({**d, "ocorrido_em": local_para_iso(d["ocorrido_em"])})
    try:
        await api.post(f"/mulheres/{mulher_id}/eventos", json=corpo)
        flash(request, "success", "Evento registrado na linha do tempo.")
    except ApiError as e:
        avisar_erro(request, e)
    return go(safe_next(proximo, f"/mulheres/{mulher_id}?aba=linha"))


@router.post("/mulheres/{mulher_id:uid}/documentos")
async def anexar_documento(mulher_id: str, request: Request, api: ApiDep, user: Escritor):
    from webapp.routes.documentos import enviar_documento

    return await enviar_documento(request, api, mulher_id, f"/mulheres/{mulher_id}?aba=documentos")
