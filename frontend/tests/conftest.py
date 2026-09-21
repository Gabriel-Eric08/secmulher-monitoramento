"""Testes ponta a ponta: o front (Jinja2) conversa com o backend REAL, em memória, via ASGI — sem mocks da API."""

import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.models  # noqa: F401  (backend)
from app.core.database import Base, criar_engine
from app.core.dependencies import get_session
from app.core.security import hash_senha
from app.core.storage import LocalStorage, get_storage
from app.main import app as backend_app
from app.modules.usuarios.model import Usuario
from app.shared.enums import PerfilUsuario
from webapp.config import Settings
from webapp.main import create_app

SENHA = "Senha1234"
PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"


def pdf(txt: str = "a") -> bytes:
    return PDF + txt.encode()


@pytest_asyncio.fixture
async def backend(tmp_path):
    engine = criar_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)

    async def _session():
        async with sm() as s:
            yield s

    backend_app.dependency_overrides[get_session] = _session
    backend_app.dependency_overrides[get_storage] = lambda: LocalStorage(str(tmp_path / "storage"))
    yield sm
    backend_app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def novo_usuario(backend) -> Callable[..., Awaitable[Usuario]]:
    async def _mk(perfil: PerfilUsuario, email: str | None = None, nome: str | None = None) -> Usuario:
        async with backend() as s:
            u = Usuario(nome=nome or f"Ana {perfil.value.title()}", email=email or f"{perfil.value.lower()}@teste.gov.br", senha_hash=hash_senha(SENHA), perfil=perfil)
            s.add(u)
            await s.commit()
            return u

    return _mk


def make_front(transport: httpx.AsyncBaseTransport | None = None):
    return create_app(Settings(secret_key="segredo-de-teste", api_base_url="http://api"), transport=transport or httpx.ASGITransport(app=backend_app))


@pytest_asyncio.fixture
async def front(backend):
    app = make_front()
    async with app.router.lifespan_context(app):
        yield app


async def _client(front_app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=front_app), base_url="http://web", follow_redirects=False)


@pytest_asyncio.fixture
async def anon(front) -> AsyncIterator[httpx.AsyncClient]:
    async with await _client(front) as c:
        yield c


async def token(c: httpx.AsyncClient) -> str:
    """Lê o token CSRF de uma página autenticada (/perfil) ou do /login."""
    r = await c.get("/perfil")
    if r.status_code != 200:
        r = await c.get("/login")
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    assert m, r.text[:300]
    return m.group(1)


async def entrar(c: httpx.AsyncClient, email: str, senha: str = SENHA) -> httpx.Response:
    csrf = await token(c)
    return await c.post("/login", data={"email": email, "senha": senha, "csrf_token": csrf})


@pytest_asyncio.fixture
async def sessoes(front, novo_usuario) -> AsyncIterator[dict[str, httpx.AsyncClient]]:
    """Um cliente do front já logado para cada perfil: sessoes['ADMIN'], ['GESTOR'], ['ATENDENTE'], ['AUDITOR']."""
    out: dict[str, httpx.AsyncClient] = {}
    for perfil in PerfilUsuario:
        u = await novo_usuario(perfil)
        c = await _client(front)
        r = await entrar(c, u.email)
        assert r.status_code == 303, r.text[:400]
        out[perfil.value] = c
    yield out
    for c in out.values():
        await c.aclose()


async def post(c: httpx.AsyncClient, url: str, data: dict | None = None, **kw) -> httpx.Response:
    """POST autenticado com CSRF automático."""
    data = {**(data or {}), "csrf_token": await token(c)}
    return await c.post(url, data=data, **kw)


def local_id(resp: httpx.Response, prefixo: str) -> str:
    """Extrai o UUID de um redirect `/prefixo/<uuid>`."""
    m = re.search(rf"{re.escape(prefixo)}/([0-9a-f-]{{36}})", resp.headers["location"])
    assert m, resp.headers.get("location")
    return m.group(1)


def toasts(resp: httpx.Response) -> list[str]:
    """Mensagens (toasts) que a página entrega ao JS — vêm em JSON com acentos escapados."""
    m = re.search(r'<script id="flash-data" type="application/json">(.*?)</script>', resp.text, re.S)
    return [f["msg"] for f in json.loads(m.group(1))] if m else []
