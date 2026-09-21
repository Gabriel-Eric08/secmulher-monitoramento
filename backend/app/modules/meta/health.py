from typing import Literal

from fastapi import APIRouter, Response
from pydantic import Field
from sqlalchemy import text

from app.core.dependencies import SessionDep
from app.core.storage import get_storage
from app.shared.schemas import Esquema

router = APIRouter(tags=["Sistema"])


class Saude(Esquema):
    status: Literal["ok"] = "ok"


class Prontidao(Esquema):
    status: Literal["ok", "degradado"]
    banco: bool = Field(..., description="Banco de dados respondeu a `SELECT 1`.")
    storage: bool = Field(..., description="Storage de arquivos acessível.")


@router.get(
    "/health",
    response_model=Saude,
    operation_id="sistema_health",
    summary="Liveness",
    description="O processo está de pé. Não consulta dependências. **Permissão:** pública.",
)
async def health() -> Saude:
    return Saude()


@router.get(
    "/health/ready",
    response_model=Prontidao,
    operation_id="sistema_ready",
    summary="Readiness (banco + storage)",
    description="`200` se banco e storage respondem; `503` caso contrário. **Permissão:** pública.",
    responses={503: {"model": Prontidao, "description": "Alguma dependência indisponível."}},
)
async def ready(session: SessionDep, response: Response) -> Prontidao:
    try:
        await session.execute(text("SELECT 1"))
        banco = True
    except Exception:
        banco = False
    try:
        storage = await get_storage().healthcheck()
    except Exception:
        storage = False
    ok = banco and storage
    if not ok:
        response.status_code = 503
    return Prontidao(status="ok" if ok else "degradado", banco=banco, storage=storage)
