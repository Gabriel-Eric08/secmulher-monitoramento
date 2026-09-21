import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Enum, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, IdMixin, UTCDateTime
from app.modules.usuarios.model import Usuario
from app.shared.enums import AcaoAuditoria
from app.shared.utils import utcnow


class Auditoria(Base, IdMixin):
    """Log transversal e imutável (append-only) das ações dos usuários."""

    __tablename__ = "auditoria"
    __table_args__ = (Index("ix_auditoria_entidade", "entidade", "entidade_id"),)

    usuario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True, index=True)
    acao: Mapped[AcaoAuditoria] = mapped_column(
        Enum(AcaoAuditoria, native_enum=False, length=20, create_constraint=True, name="acao"), index=True
    )
    entidade: Mapped[str] = mapped_column(String(50))
    entidade_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    mulher_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    antes: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    depois: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)

    usuario: Mapped[Usuario | None] = relationship(lazy="joined")
