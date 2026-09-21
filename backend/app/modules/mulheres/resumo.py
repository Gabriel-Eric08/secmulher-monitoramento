"""Visão consolidada de uma mulher — compõe os services de outros módulos (por isso fora de `service.py`)."""

import uuid

from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documentos import service as documentos
from app.modules.eventos import service as eventos
from app.modules.eventos.schema import EventoFiltros, EventoLeitura
from app.modules.mulheres import service as mulheres
from app.modules.mulheres.schema import MulherLeitura
from app.modules.servicos_mulheres import service as vinculos
from app.modules.servicos_mulheres.schema import VinculoLeitura
from app.modules.usuarios.model import Usuario
from app.shared.pagination import Paginacao, PaginacaoOrdenavel
from app.shared.schemas import Esquema


class MulherResumo(Esquema):
    mulher: MulherLeitura
    servicos: list[VinculoLeitura] = Field(..., description="Vínculos com o **status atual** de cada um.")
    ultimos_eventos: list[EventoLeitura] = Field(..., description="Eventos mais recentes da linha do tempo.")
    total_eventos: int
    total_documentos: int = Field(..., description="Documentos ativos (não excluídos).")


async def montar(session: AsyncSession, mulher_id: uuid.UUID, ator: Usuario, qtd_eventos: int) -> MulherResumo:
    mulher = await mulheres.obter_para_leitura(session, mulher_id, ator)
    lista_vinculos, _ = await vinculos.listar_da_mulher(session, mulher_id, PaginacaoOrdenavel(1, 100, None))
    lista_eventos, total_eventos = await eventos.listar(
        session, EventoFiltros(mulher_id=mulher_id), Paginacao(1, qtd_eventos)
    )
    return MulherResumo(
        mulher=MulherLeitura.model_validate(mulher),
        servicos=[VinculoLeitura.model_validate(v) for v in lista_vinculos],
        ultimos_eventos=[EventoLeitura.model_validate(e) for e in lista_eventos],
        total_eventos=total_eventos,
        total_documentos=await documentos.contar_da_mulher(session, mulher_id),
    )
