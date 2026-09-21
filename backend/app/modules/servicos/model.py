from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, IdMixin, TimestampMixin


class Servico(Base, IdMixin, TimestampMixin):
    """Catálogo de serviços oferecidos pela Secretaria."""

    __tablename__ = "servicos"

    nome: Mapped[str] = mapped_column(String(150), unique=True)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    categoria: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
