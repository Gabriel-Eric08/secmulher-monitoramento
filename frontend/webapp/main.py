import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from webapp.api import ApiError, SessionExpired
from webapp.config import Settings, get_settings
from webapp.routes import auditoria, auth, documentos, eventos, mulheres, perfil, servicos, usuarios, vinculos
from webapp.templating import flash, render

BASE = Path(__file__).parent
log = logging.getLogger("frontend")

_CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; font-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
)


def create_app(settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    """`transport` permite ligar o front direto a um app ASGI (testes ponta a ponta) em vez de HTTP real."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
        yield
        await app.state.http.aclose()

    app = FastAPI(title=settings.app_name, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    # Criado aqui, e não no lifespan: em serverless (Vercel) o lifespan pode não ser executado.
    app.state.http = httpx.AsyncClient(base_url=settings.api_base_url, timeout=30.0, transport=transport)
    app.state.meta = None
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="hs_session",
        max_age=settings.session_max_age_days * 86400,
        same_site="lax",
        https_only=settings.cookie_secure,
    )

    @app.middleware("http")
    async def cabecalhos_de_seguranca(request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("Content-Security-Policy", _CSP)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if request.url.path.startswith("/static/"):
            resp.headers.setdefault("Cache-Control", "public, max-age=3600")
        return resp

    app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
    for r in (auth, mulheres, servicos, vinculos, eventos, documentos, usuarios, auditoria, perfil):
        app.include_router(r.router)

    # ---------- erros ----------
    @app.exception_handler(SessionExpired)
    async def _sessao_expirada(request: Request, exc: SessionExpired):
        if request.session.pop("_expirou", False):
            flash(request, "warning", "Sua sessão expirou. Entre novamente.")
        destino = "/login"
        if request.method == "GET" and request.url.path not in ("/", "/login"):
            destino += "?next=" + request.url.path + (("%3F" + request.url.query.replace("&", "%26")) if request.url.query else "")
        return RedirectResponse(destino, status_code=303)

    @app.exception_handler(ApiError)
    async def _erro_api(request: Request, exc: ApiError) -> HTMLResponse:
        if exc.status >= 500:
            log.error("Falha ao consumir a API: %s %s (%s)", exc.status, exc.code, exc.message)
        status = exc.status if exc.status in (403, 404, 503) else (400 if exc.status < 500 else 502)
        return render(request, "erro.html", {"erro": exc, "status": status}, status=status)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> HTMLResponse:
        e = ApiError(exc.status_code, "NAO_ENCONTRADO" if exc.status_code == 404 else "ERRO", "Página não encontrada." if exc.status_code == 404 else str(exc.detail))
        return render(request, "erro.html", {"erro": e, "status": exc.status_code}, status=exc.status_code)

    @app.exception_handler(Exception)
    async def _inesperado(request: Request, exc: Exception) -> HTMLResponse:
        log.exception("Erro inesperado no front", exc_info=exc)
        e = ApiError(500, "ERRO_INTERNO", "Ocorreu um erro inesperado. Tente novamente.")
        return render(request, "erro.html", {"erro": e, "status": 500}, status=500)

    @app.get("/health", include_in_schema=False)
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
