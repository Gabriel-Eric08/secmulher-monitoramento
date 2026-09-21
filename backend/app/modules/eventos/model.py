import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, IdMixin, UTCDateTime
from app.modules.usuarios.model import Usuario
from app.shared.enums import TipoEvento
from app.shared.utils import utcnow


class Evento(Base, IdMixin):
    """Registro imutável da linha do tempo (append-only): sem UPDATE/DELETE na aplicação."""

    __tablename__ = "eventos"
    __table_args__ = (Index("ix_eventos_mulher_ocorrido", "mulher_id", "ocorrido_em"),)

    mulher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("mulheres.id"), index=True)
    servico_mulher_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("servicos_mulheres.id"), nullable=True, index=True
    )
    tipo: Mapped[TipoEvento] = mapped_column(
        Enum(TipoEvento, native_enum=False, length=20, create_constraint=True, name="tipo"), index=True
    )
    titulo: Mapped[str] = mapped_column(String(200))
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocorrido_em: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    registrado_em: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    registrado_por: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id"))
    corrige_evento_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("eventos.id"), nullable=True, index=True
    )
    metadados: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    autor: Mapped[Usuario] = relationship(lazy="joined", foreign_keys=[registrado_por])
    retificacoes: Mapped[list["Evento"]] = relationship(
        "Evento", foreign_keys=[corrige_evento_id], viewonly=True, lazy="selectin", join_depth=1
    )
