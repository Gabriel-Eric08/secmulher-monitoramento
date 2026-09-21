import uuid
from datetime import datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings
from app.shared.exceptions import NaoAutenticado
from app.shared.utils import utcnow

_hasher = PasswordHasher()
# Hash fictício para igualar o tempo de resposta quando o e-mail não existe.
_HASH_FALSO = _hasher.hash("senha-fictícia-para-timing")

TipoToken = Literal["access", "refresh"]


def hash_senha(senha: str) -> str:
    return _hasher.hash(senha)


def verificar_senha(senha: str, senha_hash: str | None) -> bool:
    try:
        return _hasher.verify(senha_hash or _HASH_FALSO, senha) and senha_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def _codificar(claims: dict[str, Any]) -> str:
    settings = get_settings()
    return jwt.encode(claims, settings.secret_key, algorithm=settings.jwt_algorithm)


def criar_access_token(usuario_id: uuid.UUID, perfil: str) -> tuple[str, int]:
    """Retorna (token, expires_in em segundos)."""
    settings = get_settings()
    agora = utcnow()
    exp = agora + timedelta(minutes=settings.access_token_expire_minutes)
    token = _codificar(
        {"sub": str(usuario_id), "perfil": perfil, "type": "access", "iat": agora, "exp": exp}
    )
    return token, settings.access_token_expire_minutes * 60


def criar_refresh_token(usuario_id: uuid.UUID) -> tuple[str, uuid.UUID, datetime]:
    """Retorna (token, jti, expira_em)."""
    settings = get_settings()
    agora = utcnow()
    exp = agora + timedelta(days=settings.refresh_token_expire_days)
    jti = uuid.uuid4()
    token = _codificar(
        {"sub": str(usuario_id), "jti": str(jti), "type": "refresh", "iat": agora, "exp": exp}
    )
    return token, jti, exp


def decodificar_token(token: str, tipo: TipoToken) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise NaoAutenticado("Token expirado.", code="TOKEN_EXPIRADO") from exc
    except jwt.PyJWTError as exc:
        raise NaoAutenticado("Token inválido.", code="TOKEN_INVALIDO") from exc
    if payload.get("type") != tipo or not payload.get("sub"):
        raise NaoAutenticado("Token inválido.", code="TOKEN_INVALIDO")
    return payload
