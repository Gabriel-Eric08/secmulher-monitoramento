import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_v1
from app.core.config import get_settings
from app.core.exceptions import registrar_handlers
from app.core.middleware import RequestContextMiddleware
from app.modules.meta.health import router as health_router

DESCRICAO = """
API REST do **Sistema de Histórico de Serviços** da Secretaria da Mulher: registro, acompanhamento,
linha do tempo e auditoria dos atendimentos prestados às mulheres.

## Conceitos
* **Estado atual × histórico:** o *status atual* de um serviço vive no vínculo (`servicos-mulheres`);
  o *histórico* vive nos **eventos**, que são imutáveis (correção = retificação).
* **Documentos versionados:** enviar um novo arquivo cria uma nova versão; nada é sobrescrito.
* **Auditoria:** toda mutação (e leitura de dado sensível) é registrada, com `antes` e `depois`.
* **Exclusão lógica:** mulheres e documentos nunca são apagados fisicamente.

## Autenticação
`POST /api/v1/auth/login` devolve `access_token` e `refresh_token`. Envie
`Authorization: Bearer <access_token>` (botão **Authorize**). Perfis: `ADMIN`, `GESTOR`, `ATENDENTE`, `AUDITOR`.

## Convenções
* Prefixo `/api/v1`, JSON `snake_case`, datas ISO-8601 em UTC, IDs UUID.
* Listas paginadas: `?page=1&page_size=20` → `{items, page, page_size, total, pages}`.
* **Todos os erros** seguem o envelope `{"error": {"code", "message", "details", "request_id"}}`.
* Cada resposta traz o header `X-Request-ID`.
"""

TAGS = [
    {"name": "Autenticação", "description": "Login, renovação de tokens, logout e troca de senha."},
    {"name": "Usuários", "description": "Gestão de operadores do sistema (somente ADMIN)."},
    {"name": "Mulheres", "description": "Cadastro, resumo consolidado e rotas aninhadas (serviços, linha do tempo e documentos)."},
    {"name": "Serviços", "description": "Catálogo de serviços oferecidos pela Secretaria."},
    {"name": "Serviços das Mulheres", "description": "Vínculo mulher↔serviço: **status atual** e transições."},
    {"name": "Eventos", "description": "Linha do tempo **imutável** (append-only) e retificações."},
    {"name": "Documentos", "description": "Arquivos com versionamento não destrutivo, metadados temporais e download auditado."},
    {"name": "Auditoria", "description": "Log transversal **somente leitura** das ações dos usuários."},
    {"name": "Meta", "description": "Enums, rótulos e transições para o front não duplicar constantes."},
    {"name": "Sistema", "description": "Health checks."},
]


def _configurar_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    _configurar_logging()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    docs = settings.docs_enabled
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=DESCRICAO,
        openapi_tags=TAGS,
        contact={"name": "Secretaria da Mulher — Equipe do sistema"},
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
        lifespan=lifespan,
    )
    registrar_handlers(app)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,  # adicionado por último = mais externo (cobre também as respostas de erro)
        allow_origins=settings.cors_origins_list,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "Content-Disposition", "Location"],
    )
    app.include_router(api_v1, prefix="/api/v1")
    app.include_router(health_router)
    return app


app = create_app()


def gerar_openapi() -> dict[str, Any]:
    """Esquema OpenAPI (usado por `scripts/export_openapi.py`, independente de DOCS_ENABLED)."""
    from fastapi.openapi.utils import get_openapi

    return get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=TAGS,
        contact=app.contact,
    )
