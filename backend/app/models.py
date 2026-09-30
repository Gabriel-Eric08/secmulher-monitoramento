"""Importa todos os models para registrá-los no metadata (Alembic e testes)."""

from app.core.storage import ArquivoArmazenado  # noqa: F401
from app.modules.auditoria.model import Auditoria  # noqa: F401
from app.modules.auth.model import RefreshToken  # noqa: F401
from app.modules.documentos.model import Documento, DocumentoVersao  # noqa: F401
from app.modules.eventos.model import Evento  # noqa: F401
from app.modules.mulheres.model import Mulher  # noqa: F401
from app.modules.servicos.model import Servico  # noqa: F401
from app.modules.servicos_mulheres.model import ServicoMulher  # noqa: F401
from app.modules.usuarios.model import Usuario  # noqa: F401
