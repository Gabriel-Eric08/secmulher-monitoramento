import re
import unicodedata
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import inspect as sa_inspect


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    """Datetime sem fuso é tratado como UTC; com fuso é convertido para UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def so_digitos(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def normalizar_texto(value: str | None) -> str:
    """minúsculas, sem acentos e com espaços colapsados (para busca)."""
    if not value:
        return ""
    sem_acento = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sem_acento).strip().lower()


def validar_cpf(cpf: str) -> bool:
    if len(cpf) != 11 or not cpf.isdigit() or cpf == cpf[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10 % 11) % 10
        if digito != int(cpf[tamanho]):
            return False
    return True


def mascarar_cpf(cpf: str | None) -> str | None:
    if not cpf or len(cpf) != 11:
        return cpf
    return f"***.{cpf[3:6]}.{cpf[6:9]}-**"


def mascarar_telefone(telefone: str | None) -> str | None:
    digitos = so_digitos(telefone)
    if len(digitos) < 4:
        return telefone
    return f"(**) *****-{digitos[-4:]}"


def _json_safe(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    return value


def serializar_modelo(obj: Any, excluir: frozenset[str] = frozenset({"senha_hash"})) -> dict[str, Any]:
    """Snapshot JSON-safe das colunas *já carregadas* do objeto (usado na auditoria)."""
    state = sa_inspect(obj)
    return {
        key: _json_safe(state.dict[key])
        for key in state.mapper.column_attrs.keys()
        if key in state.dict and key not in excluir
    }
