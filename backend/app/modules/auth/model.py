import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UTCDateTime
from app.shared.utils import utcnow


class RefreshToken(Base):
    """Refresh tokens emitidos (permite revogação e rotação). `id` é o `jti` do JWT."""

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id"), index=True)
    expira_em: Mapped[datetime] = mapped_column(UTCDateTime)
    revogado_em: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
