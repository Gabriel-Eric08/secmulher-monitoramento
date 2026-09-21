import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, IdMixin, TimestampMixin, UTCDateTime


class Mulher(Base, IdMixin, TimestampMixin):
    __tablename__ = "mulheres"
    __table_args__ = (
        # CPF único quando informado (vale também para registros excluídos logicamente).
        Index(
            "uq_mulheres_cpf",
            "cpf",
            unique=True,
            sqlite_where=text("cpf IS NOT NULL"),
            postgresql_where=text("cpf IS NOT NULL"),
        ),
    )

    nome_completo: Mapped[str] = mapped_column(String(200))
    nome_social: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # nome(s) sem acento e em minúsculas, para busca insensível a acentos
    nome_busca: Mapped[str] = mapped_column(String(420), index=True, default="")
    cpf: Mapped[str | None] = mapped_column(String(11), nullable=True)
    rg: Mapped[str | None] = mapped_column(String(30), nullable=True)
    data_nascimento: Mapped[date | None] = mapped_column(Date, nullable=True)
    telefone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    telefone_alt: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)

    logradouro: Mapped[str | None] = mapped_column(String(200), nullable=True)
    numero: Mapped[str | None] = mapped_column(String(20), nullable=True)
    complemento: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bairro: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cidade: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    cep: Mapped[str | None] = mapped_column(String(8), nullable=True)

    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)

    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True, index=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    motivo_exclusao: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
