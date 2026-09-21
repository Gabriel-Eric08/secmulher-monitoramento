"""Abstração de armazenamento de arquivos (local em dev, S3/MinIO em produção)."""

import asyncio
import shutil
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from pathlib import Path
from typing import BinaryIO

from app.core.config import Settings, get_settings

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
    """Compatível com S3 e MinIO. Requer `pip install .[s3]` (boto3). Não coberto pelos testes automatizados."""

    def __init__(self, settings: Settings) -> None:
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("STORAGE_BACKEND=s3 requer a dependência boto3 (pip install .[s3]).") from exc
        if not settings.s3_bucket:
            raise RuntimeError("S3_BUCKET não configurado.")
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint or None,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
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


_storage: StorageBackend | None = None


def get_storage() -> StorageBackend:
    """Dependência FastAPI (singleton). Sobrescrevível nos testes."""
    global _storage
    if _storage is None:
        settings = get_settings()
        _storage = S3Storage(settings) if settings.storage_backend == "s3" else LocalStorage(settings.storage_local_path)
    return _storage
