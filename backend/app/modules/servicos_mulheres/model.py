import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, IdMixin, TimestampMixin
from app.modules.mulheres.model import Mulher
from app.modules.servicos.model import Servico
from app.shared.enums import StatusServicoMulher
from app.shared.utils import utcnow


class ServicoMulher(Base, IdMixin, TimestampMixin):
    """Vínculo mulher↔serviço com o **status atual**. O histórico vive em `eventos`."""

    __tablename__ = "servicos_mulheres"
    __table_args__ = (
        # No máximo um vínculo "aberto" por mulher+serviço.
        Index(
            "uq_servicos_mulheres_aberto",
            "mulher_id",
            "servico_id",
            unique=True,
            sqlite_where=text("status NOT IN ('CONCLUIDO', 'CANCELADO')"),
            postgresql_where=text("status NOT IN ('CONCLUIDO', 'CANCELADO')"),
        ),
    )

    mulher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("mulheres.id"), index=True)
    servico_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("servicos.id"), index=True)
    status: Mapped[StatusServicoMulher] = mapped_column(
        Enum(StatusServicoMulher, native_enum=False, length=20, create_constraint=True, name="status"),
        default=StatusServicoMulher.SOLICITADO,
        index=True,
    )
    data_inicio: Mapped[date] = mapped_column(Date, default=lambda: utcnow().date())
    data_encerramento: Mapped[date | None] = mapped_column(Date, nullable=True)
    responsavel_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)

    mulher: Mapped[Mulher] = relationship(lazy="joined")
    servico: Mapped[Servico] = relationship(lazy="joined")
