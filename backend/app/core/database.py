import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, MetaData, Uuid, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool, StaticPool
from sqlalchemy.types import TypeDecorator

from app.core.config import get_settings
from app.shared.exceptions import Conflito
from app.shared.utils import utcnow

# Nomes determinísticos de constraints: necessários para o Alembic (batch mode no SQLite).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class UTCDateTime(TypeDecorator[datetime]):
    """Sempre armazena UTC e devolve datetime *aware* (o SQLite perde o fuso)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {datetime: UTCDateTime}


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


def criar_engine(url: str) -> AsyncEngine:
    kwargs: dict[str, Any] = {}
    sqlite = url.startswith("sqlite")
    if sqlite and ":memory:" in url:
        kwargs.update(poolclass=StaticPool, connect_args={"check_same_thread": False})
    elif not sqlite and get_settings().db_serverless:
        kwargs.update(poolclass=NullPool, connect_args={"statement_cache_size": 0})
    engine = create_async_engine(url, **kwargs)
    if sqlite:

        @event.listens_for(engine.sync_engine, "connect")
        def _pragma_fk(dbapi_conn: Any, _: Any) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine = criar_engine(get_settings().database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def confirmar(session: AsyncSession, *, code: str = "CONFLITO", message: str | None = None) -> None:
    """Commit da unidade de trabalho; violação de unicidade/FK vira 409 com o código informado."""
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise Conflito(message, code=code) from exc
