import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, and_
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, IdMixin, TimestampMixin, UTCDateTime
from app.shared.enums import TipoDocumento
from app.shared.utils import utcnow


class DocumentoVersao(Base, IdMixin):
    """Arquivo físico versionado (append-only): nova versão nunca sobrescreve a anterior."""

    __tablename__ = "documentos_versoes"
    __table_args__ = (UniqueConstraint("documento_id", "numero", name="uq_documentos_versoes_numero"),)

    documento_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documentos.id"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    nome_arquivo: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(120))
    tamanho_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(500))
    valido_de: Mapped[date | None] = mapped_column(Date, nullable=True)
    valido_ate: Mapped[date | None] = mapped_column(Date, nullable=True)
    motivo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    criado_por: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Documento(Base, IdMixin, TimestampMixin):
    __tablename__ = "documentos"

    mulher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("mulheres.id"), index=True)
    servico_mulher_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("servicos_mulheres.id"), nullable=True, index=True
    )
    evento_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("eventos.id"), nullable=True)
    titulo: Mapped[str] = mapped_column(String(200))
    tipo: Mapped[TipoDocumento] = mapped_column(
        Enum(TipoDocumento, native_enum=False, length=20, create_constraint=True, name="tipo"), index=True
    )
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    versao_atual: Mapped[int] = mapped_column(Integer, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True, index=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id"))

    versao: Mapped[DocumentoVersao | None] = relationship(
        DocumentoVersao,
        primaryjoin=lambda: and_(
            Documento.id == DocumentoVersao.documento_id, Documento.versao_atual == DocumentoVersao.numero
        ),
        foreign_keys=[DocumentoVersao.documento_id, DocumentoVersao.numero],
        viewonly=True,
        uselist=False,
        lazy="joined",
    )
