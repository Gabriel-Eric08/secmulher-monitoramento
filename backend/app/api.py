"""Agrega os routers da API v1."""

from fastapi import APIRouter

from app.modules.auditoria.router import router as auditoria
from app.modules.auth.router import router as auth
from app.modules.documentos.router import router as documentos
from app.modules.eventos.router import router as eventos
from app.modules.meta.router import router as meta
from app.modules.mulheres.router import router as mulheres
from app.modules.mulheres.router_aninhado import router as mulheres_aninhado
from app.modules.servicos.router import router as servicos
from app.modules.servicos_mulheres.router import router as servicos_mulheres
from app.modules.usuarios.router import router as usuarios

api_v1 = APIRouter()
for r in (
    auth,
    usuarios,
    mulheres,
    mulheres_aninhado,
    servicos,
    servicos_mulheres,
    eventos,
    documentos,
    auditoria,
    meta,
):
    api_v1.include_router(r)
