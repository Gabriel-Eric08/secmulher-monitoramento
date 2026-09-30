"""Abstração de armazenamento de arquivos (local em dev; S3/R2 ou o próprio banco em produção)."""

import asyncio
import shutil
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import LargeBinary, String, delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import Settings, get_settings
from app.core.database import Base, SessionLocal, UTCDateTime
from app.shared.utils import utcnow

CHUNK = 64 * 1024


class StorageBackend(ABC):
    @abstractmethod
    async def save(self, key: str, fileobj: BinaryIO) -> None: ...

    @abstractmethod
    def open(self, key: str) -> AsyncIterator[bytes]: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def exists(self, key: str) -> bool: ...

    async def healthcheck(self) -> bool:
        return True


class LocalStorage(StorageBackend):
    def __init__(self, base_path: str) -> None:
        self.base = Path(base_path).resolve()
        self.base.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.base / key).resolve()
        if self.base not in path.parents:  # bloqueia path traversal
            raise ValueError("Chave de storage inválida.")
        return path

    async def save(self, key: str, fileobj: BinaryIO) -> None:
        path = self._path(key)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as out:
                shutil.copyfileobj(fileobj, out, CHUNK)

        await asyncio.to_thread(_write)

    async def open(self, key: str) -> AsyncIterator[bytes]:  # type: ignore[override]
        path = self._path(key)
        handle = await asyncio.to_thread(open, path, "rb")
        try:
            while chunk := await asyncio.to_thread(handle.read, CHUNK):
                yield chunk
        finally:
            handle.close()

    async def delete(self, key: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.unlink, True)

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(self._path(key).exists)

    async def healthcheck(self) -> bool:
        return await asyncio.to_thread(lambda: self.base.is_dir())


class S3Storage(StorageBackend):
    """Compatível com S3, R2 e MinIO. Não coberto pelos testes automatizados."""

    def __init__(self, settings: Settings) -> None:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("STORAGE_BACKEND=s3 requer a dependência boto3.") from exc
        if not settings.s3_bucket:
            raise RuntimeError("S3_BUCKET não configurado.")
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint or None,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            # R2/MinIO não aceitam os checksums extras que o boto3 recente envia por padrão.
            config=Config(request_checksum_calculation="when_required", response_checksum_validation="when_required"),
        )

    async def save(self, key: str, fileobj: BinaryIO) -> None:
        await asyncio.to_thread(self.client.upload_fileobj, fileobj, self.bucket, key)

    async def open(self, key: str) -> AsyncIterator[bytes]:  # type: ignore[override]
        obj = await asyncio.to_thread(self.client.get_object, Bucket=self.bucket, Key=key)
        body = obj["Body"]
        try:
            while chunk := await asyncio.to_thread(body.read, CHUNK):
                yield chunk
        finally:
            body.close()

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=key)

    async def exists(self, key: str) -> bool:
        def _head() -> bool:
            try:
                self.client.head_object(Bucket=self.bucket, Key=key)
                return True
            except Exception:
                return False

        return await asyncio.to_thread(_head)

    async def healthcheck(self) -> bool:
        def _check() -> bool:
            try:
                self.client.head_bucket(Bucket=self.bucket)
                return True
            except Exception:
                return False

        return await asyncio.to_thread(_check)


class ArquivoArmazenado(Base):
    """Conteúdo dos arquivos quando `STORAGE_BACKEND=db` (BLOB/bytea, uma linha por chave)."""

    __tablename__ = "arquivos"

    chave: Mapped[str] = mapped_column(String(500), primary_key=True)
    conteudo: Mapped[bytes] = mapped_column(LargeBinary)
    tamanho: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class DatabaseStorage(StorageBackend):
    """Guarda os arquivos no próprio banco (tabela `arquivos`). Dispensa S3; adequado a arquivos pequenos.

    Usa sessões próprias: o arquivo é gravado antes do commit do documento, como nos demais backends
    (e removido pelo serviço se esse commit falhar).
    """

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession] = SessionLocal) -> None:
        self.sessionmaker = sessionmaker

    async def save(self, key: str, fileobj: BinaryIO) -> None:
        conteudo = await asyncio.to_thread(fileobj.read)
        async with self.sessionmaker() as session:
            await session.merge(ArquivoArmazenado(chave=key, conteudo=conteudo, tamanho=len(conteudo)))
            await session.commit()

    async def open(self, key: str) -> AsyncIterator[bytes]:  # type: ignore[override]
        async with self.sessionmaker() as session:
            conteudo = await session.scalar(select(ArquivoArmazenado.conteudo).where(ArquivoArmazenado.chave == key))
        if conteudo is None:
            raise FileNotFoundError(key)
        for inicio in range(0, len(conteudo), CHUNK):
            yield conteudo[inicio : inicio + CHUNK]

    async def delete(self, key: str) -> None:
        async with self.sessionmaker() as session:
            await session.execute(delete(ArquivoArmazenado).where(ArquivoArmazenado.chave == key))
            await session.commit()

    async def exists(self, key: str) -> bool:
        async with self.sessionmaker() as session:
            return await session.scalar(select(ArquivoArmazenado.chave).where(ArquivoArmazenado.chave == key)) is not None

    async def healthcheck(self) -> bool:
        async with self.sessionmaker() as session:
            await session.execute(text("SELECT 1"))
        return True


_storage: StorageBackend | None = None


def get_storage() -> StorageBackend:
    """Dependência FastAPI (singleton). Sobrescrevível nos testes."""
    global _storage
    if _storage is None:
        settings = get_settings()
        if settings.storage_backend == "s3":
            _storage = S3Storage(settings)
        elif settings.storage_backend == "db":
            _storage = DatabaseStorage()
        else:
            _storage = LocalStorage(settings.storage_local_path)
    return _storage
