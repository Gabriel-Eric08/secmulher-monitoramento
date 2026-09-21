from datetime import datetime

from sqlalchemy import Boolean, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, IdMixin, TimestampMixin, UTCDateTime
from app.shared.enums import PerfilUsuario


class Usuario(Base, IdMixin, TimestampMixin):
    __tablename__ = "usuarios"

    nome: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    perfil: Mapped[PerfilUsuario] = mapped_column(
        Enum(PerfilUsuario, native_enum=False, length=20, create_constraint=True, name="perfil")
    )
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    ultimo_login_em: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    tentativas_falhas: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_ate: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
