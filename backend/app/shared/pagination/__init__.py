import math
from collections.abc import Sequence
from typing import Annotated, Any, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.exceptions import RequisicaoInvalida

T = TypeVar("T")


class Pagina(BaseModel, Generic[T]):
    """Envelope padrão de listas paginadas."""

    items: list[T]
    page: int = Field(..., description="Página atual (a partir de 1).", examples=[1])
    page_size: int = Field(..., description="Itens por página.", examples=[20])
    total: int = Field(..., description="Total de itens que satisfazem os filtros.", examples=[134])
    pages: int = Field(..., description="Total de páginas.", examples=[7])


class Paginacao:
    """Dependência de paginação: `?page=1&page_size=20`."""

    def __init__(
        self,
        page: Annotated[int, Query(ge=1, description="Página (a partir de 1).")] = 1,
        page_size: Annotated[int, Query(ge=1, le=100, description="Itens por página (1–100).")] = 20,
    ) -> None:
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaginacaoOrdenavel(Paginacao):
    """Paginação + ordenação: `?sort=-created_at,nome_completo`."""

    def __init__(
        self,
        page: Annotated[int, Query(ge=1, description="Página (a partir de 1).")] = 1,
        page_size: Annotated[int, Query(ge=1, le=100, description="Itens por página (1–100).")] = 20,
        sort: Annotated[
            str | None,
            Query(
                description="Campos separados por vírgula; prefixo `-` = decrescente. "
                "Os campos permitidos estão descritos na rota.",
                examples=["-created_at,nome_completo"],
            ),
        ] = None,
    ) -> None:
        super().__init__(page, page_size)
        self.sort = sort


def ordenar(
    stmt: Select[Any],
    sort: str | None,
    permitidos: dict[str, Any],
    padrao: Sequence[Any],
    desempate: Any,
) -> Select[Any]:
    """Aplica `sort` validando contra uma lista de campos permitidos."""
    colunas: list[Any] = []
    if sort:
        for parte in sort.split(","):
            parte = parte.strip()
            if not parte:
                continue
            decrescente = parte.startswith("-")
            nome = parte.lstrip("+-")
            if nome not in permitidos:
                raise RequisicaoInvalida(
                    f"Campo de ordenação inválido: '{nome}'. Permitidos: {', '.join(sorted(permitidos))}.",
                    code="ORDENACAO_INVALIDA",
                )
            colunas.append(permitidos[nome].desc() if decrescente else permitidos[nome].asc())
    return stmt.order_by(*(colunas or padrao), desempate)


async def paginar(session: AsyncSession, stmt: Select[Any], pag: Paginacao) -> tuple[list[Any], int]:
    total = await session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    result = await session.execute(stmt.offset(pag.offset).limit(pag.page_size))
    return list(result.unique().scalars().all()), total


def montar_pagina(items: list[Any], total: int, pag: Paginacao) -> dict[str, Any]:
    return {
        "items": items,
        "page": pag.page,
        "page_size": pag.page_size,
        "total": total,
        "pages": math.ceil(total / pag.page_size) if total else 0,
    }
