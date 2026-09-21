import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from starlette.datastructures import UploadFile

from webapp.api import ApiError
from webapp.deps import ApiDep, Escritor, Gestor, User, csrf_protect
from webapp.routes._util import avisar_erro, campos, go, query, safe_next, sem_none
from webapp.templating import flash, render

router = APIRouter(prefix="/documentos", dependencies=[Depends(csrf_protect)])

CAMPOS_DOC = ("titulo", "tipo", "descricao", "servico_mulher_id", "valido_de", "valido_ate")


async def _arquivo(request: Request) -> tuple[str, Any, str] | None:
    upload = (await request.form()).get("arquivo")
    if not isinstance(upload, UploadFile) or not upload.filename:
        return None
    return upload.filename, upload.file, upload.content_type or "application/octet-stream"


async def enviar_documento(request: Request, api: ApiDep, mulher_id: str, destino: str):
    """Cria documento + versão 1 (usado pelo formulário do detalhe da mulher e por /documentos/novo)."""
    d = await campos(request, *CAMPOS_DOC)
    arquivo = await _arquivo(request)
    if arquivo is None:
        flash(request, "error", "Selecione um arquivo para enviar.")
        return go(destino)
    try:
        doc = await api.post(f"/mulheres/{mulher_id}/documentos", data=sem_none(d), files={"arquivo": arquivo})
    except ApiError as e:
        avisar_erro(request, e)
        return go(destino)
    flash(request, "success", f"Documento “{doc['titulo']}” enviado (versão 1).")
    return go(destino)


@router.get("")
async def lista(request: Request, api: ApiDep, user: User):
    params = query(request, "q", "tipo", "mulher_id", "page", "sort", page_size=15)
    if request.query_params.get("incluir_excluidos") == "true" and user["perfil"] in ("ADMIN", "GESTOR"):
        params["incluir_excluidos"] = True
    res = await api.get("/documentos", **params)
    return render(request, "documentos/lista.html", {"res": res, "f": request.query_params})


@router.get("/novo")
async def novo_form(request: Request, user: Escritor):
    q = request.query_params
    return render(request, "documentos/novo.html", {"mulher_id": q.get("mulher_id", ""), "mulher_nome": q.get("mulher_nome", "")})


@router.post("/novo")
async def novo(request: Request, api: ApiDep, user: Escritor):
    mulher_id = (await campos(request, "mulher_id"))["mulher_id"]
    if not mulher_id:
        flash(request, "error", "Escolha a mulher a que o documento pertence.")
        return go("/documentos/novo")
    return await enviar_documento(request, api, mulher_id, "/documentos")


@router.get("/{doc_id:uid}")
async def detalhe(doc_id: str, request: Request, api: ApiDep, user: User):
    doc, versoes = await asyncio.gather(api.get(f"/documentos/{doc_id}"), api.get(f"/documentos/{doc_id}/versoes", page_size=100))
    return render(request, "documentos/detalhe.html", {"doc": doc, "versoes": versoes["items"]})


@router.post("/{doc_id:uid}/editar")
async def editar(doc_id: str, request: Request, api: ApiDep, user: Escritor):
    d = await campos(request, "titulo", "tipo", "descricao")
    try:
        await api.patch(f"/documentos/{doc_id}", json={"titulo": d["titulo"], "tipo": d["tipo"], "descricao": d["descricao"]})
        flash(request, "success", "Metadados atualizados.")
    except ApiError as e:
        avisar_erro(request, e)
    return go(f"/documentos/{doc_id}")


@router.post("/{doc_id:uid}/versoes")
async def nova_versao(doc_id: str, request: Request, api: ApiDep, user: Escritor):
    d = await campos(request, "motivo", "valido_de", "valido_ate")
    arquivo = await _arquivo(request)
    if arquivo is None:
        flash(request, "error", "Selecione o arquivo da nova versão.")
        return go(f"/documentos/{doc_id}")
    try:
        doc = await api.post(f"/documentos/{doc_id}/versoes", data=sem_none(d), files={"arquivo": arquivo})
        flash(request, "success", f"Nova versão enviada (v{doc['versao_atual']}). A anterior continua disponível.")
    except ApiError as e:
        avisar_erro(request, e)
    return go(f"/documentos/{doc_id}")


@router.post("/{doc_id:uid}/excluir")
async def excluir(doc_id: str, request: Request, api: ApiDep, user: Gestor):
    try:
        await api.delete(f"/documentos/{doc_id}")
        flash(request, "success", "Documento excluído (as versões foram preservadas).")
    except ApiError as e:
        avisar_erro(request, e)
        return go(f"/documentos/{doc_id}")
    return go(safe_next((await campos(request, "next"))["next"], "/documentos"))


@router.post("/{doc_id:uid}/restaurar")
async def restaurar(doc_id: str, request: Request, api: ApiDep, user: Gestor):
    try:
        await api.post(f"/documentos/{doc_id}/restaurar")
        flash(request, "success", "Documento restaurado.")
    except ApiError as e:
        avisar_erro(request, e)
    return go(f"/documentos/{doc_id}")


# ---------- downloads (o front repassa o stream: o token nunca vai para o navegador) ----------
async def _repassar(api: ApiDep, caminho: str) -> StreamingResponse:
    resp = await api.stream(caminho)
    cabecalhos = {k: v for k, v in resp.headers.items() if k.lower() in ("content-disposition", "content-length", "x-content-type-options")}
    return StreamingResponse(
        resp.aiter_raw(),
        media_type=resp.headers.get("content-type"),
        headers=cabecalhos,
        background=BackgroundTask(resp.aclose),
    )


@router.get("/{doc_id:uid}/download")
async def baixar(doc_id: str, api: ApiDep, user: User):
    return await _repassar(api, f"/documentos/{doc_id}/download")


@router.get("/{doc_id:uid}/versoes/{numero:int}/download")
async def baixar_versao(doc_id: str, numero: int, api: ApiDep, user: User):
    return await _repassar(api, f"/documentos/{doc_id}/versoes/{numero}/download")
