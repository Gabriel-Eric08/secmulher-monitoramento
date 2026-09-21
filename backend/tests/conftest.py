import io
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.models  # noqa: F401  (registra os models no metadata)
from app.core.database import Base, criar_engine
from app.core.dependencies import get_session
from app.core.security import hash_senha
from app.core.storage import LocalStorage, get_storage
from app.main import app
from app.modules.usuarios.model import Usuario
from app.shared.enums import PerfilUsuario

SENHA = "Senha1234"

# Cabeçalhos mínimos reais de cada formato (o MIME é detectado pelo conteúdo).
PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 30


def pdf(conteudo: str = "a") -> bytes:
    return PDF + conteudo.encode()


@pytest_asyncio.fixture
async def sessionmaker_():
    engine = criar_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(sessionmaker_, tmp_path) -> AsyncIterator[AsyncClient]:
    async def _get_session():
        async with sessionmaker_() as session:
            yield session

    storage = LocalStorage(str(tmp_path / "storage"))
    app.dependency_overrides[get_session] = _get_session
    app.dependency_overrides[get_storage] = lambda: storage
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.storage = storage  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def criar_usuario(sessionmaker_) -> Callable[..., Awaitable[Usuario]]:
    async def _criar(perfil: PerfilUsuario, email: str | None = None, nome: str | None = None) -> Usuario:
        async with sessionmaker_() as s:
            u = Usuario(
                nome=nome or f"Usuário {perfil.value}",
                email=email or f"{perfil.value.lower()}@teste.gov.br",
                senha_hash=hash_senha(SENHA),
                perfil=perfil,
            )
            s.add(u)
            await s.commit()
            return u

    return _criar


@pytest_asyncio.fixture
async def login(client) -> Callable[..., Awaitable[dict[str, str]]]:
    async def _login(email: str) -> dict[str, str]:
        r = await client.post("/api/v1/auth/login", json={"email": email, "senha": SENHA})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _login


@pytest_asyncio.fixture
async def headers(criar_usuario, login) -> dict[str, dict[str, str]]:
    """Cabeçalhos autenticados por perfil: headers['ADMIN'], ['GESTOR'], ['ATENDENTE'], ['AUDITOR']."""
    out = {}
    for perfil in PerfilUsuario:
        u = await criar_usuario(perfil)
        out[perfil.value] = await login(u.email)
    return out


def upload(conteudo: bytes, nome: str = "doc.pdf") -> dict:
    return {"arquivo": (nome, io.BytesIO(conteudo), "application/octet-stream")}
