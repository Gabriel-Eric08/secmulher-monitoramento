# Arquitetura — Sistema de Histórico de Serviços (Secretaria da Mulher)

Fonte: `project.md`. Itens marcados **[ASSUNÇÃO]** não constam no `project.md` e precisam de validação.

## 1. Princípio central

Dois sistemas separados, que só se falam por HTTP:

```
┌──────────────────────────┐        HTTP / JSON         ┌──────────────────────────┐
│ FRONTEND (fase 1)        │  ───────────────────────►  │ BACKEND (API REST)       │
│ FastAPI/Jinja2 + HTML/   │   /api/v1/*  (Bearer JWT)  │ FastAPI + SQLAlchemy     │
│ CSS/JS puro              │  ◄───────────────────────  │ Swagger próprio (/docs)  │
├──────────────────────────┤                            ├──────────────────────────┤
│ FRONTEND (fase 2)        │  mesmo contrato OpenAPI    │ SQLite → PostgreSQL      │
│ React                    │                            │ Storage local → S3/MinIO │
└──────────────────────────┘                            └──────────────────────────┘
```

Regras inegociáveis:

1. **O backend não sabe que o front existe.** Ele não renderiza HTML, não usa Jinja2, não tem rotas de página, não usa sessão/cookie de servidor. Só devolve JSON (e bytes em downloads).
2. **O contrato é o OpenAPI** (`/openapi.json`). Trocar Jinja2 por React não pode exigir nenhuma mudança no backend.
3. **O front nunca acessa banco, storage ou código do backend.** Só chama a API.
4. **Toda regra de negócio fica no backend.** O front só apresenta e valida por conveniência. Validação e autorização são repetidas no backend.
5. O front fica em pasta irmã (`frontend/`), com deploy e dependências próprios. **Escopo atual: só `backend/`.**

## 2. Estrutura do repositório

```
history/
├── .claude/            # arch.md, backend.md (e frontend.md no futuro)
├── project.md
├── backend/            # ver backend.md (escopo atual)
└── frontend/           # FUTURO — Jinja2 agora, React depois
```

## 3. Backend: camadas

Estrutura por módulo (DDD leve, como em `project.md`). Dependências só descem:

```
router  →  service  →  repository  →  model (SQLAlchemy)
   ↑          ↑
 schema (Pydantic v2: entrada/saída da API; nunca expõe model)
```

| Camada | Responsabilidade | Proibido |
|---|---|---|
| `router.py` | HTTP: parse, `Depends`, status codes, documentação OpenAPI | Regra de negócio, acesso a `Session` |
| `service.py` | Regras de negócio, transações, orquestração entre módulos, grava auditoria/eventos | Conhecer FastAPI/`Request` |
| `repository.py` | Consultas e persistência (SQLAlchemy 2.0 async) | Regra de negócio, commit |
| `model.py` | Mapeamento ORM | Lógica |
| `schema.py` | Contratos Pydantic v2 (`Create`, `Update`, `Read`, `ListItem`, filtros) | Reutilizar model como resposta |

Regras transversais:

- **Unit of Work por requisição:** a sessão é aberta em `core/dependencies.py`. O `service` decide o commit. Mutação + evento automático + auditoria acontecem **na mesma transação**.
- **Regras de um módulo em outro passam pelo `service` dele** (evita ciclos). Queries de listagem podem referenciar o **model** de outro módulo só para montar filtros/joins. Composições entre módulos (resumo da mulher, rotas aninhadas) ficam em arquivos próprios (`resumo.py`, `router_aninhado.py`).
- `shared/` guarda enums, paginação, exceções base e utilitários sem dependência de módulo.

## 4. Conceitos de domínio

Separação rígida entre **estado atual** e **histórico** (`project.md` §1):

| Conceito | Natureza | Mutável? |
|---|---|---|
| `Mulher` | Cadastro (estado atual) | Sim (com auditoria); exclusão lógica |
| `Servico` | Catálogo de serviços oferecidos | Sim |
| `ServicoMulher` | Vínculo mulher↔serviço com **status atual** | Sim, só por transições válidas |
| `Evento` | Linha do tempo | **Nunca** (append-only) |
| `Documento` | Cabeçalho lógico do arquivo | Só metadados |
| `DocumentoVersao` | Arquivo físico versionado | **Nunca** (append-only) |
| `Auditoria` | Log de mutações por usuário | **Nunca** (append-only, sem endpoint de escrita) |
| `Usuario` | Operador do sistema | Sim |

Relações:

```
Mulher 1─N ServicoMulher N─1 Servico
Mulher 1─N Evento          (Evento N─0..1 ServicoMulher)
Mulher 1─N Documento 1─N DocumentoVersao   (Documento N─0..1 ServicoMulher/Evento)
Usuario 1─N (Evento | DocumentoVersao | Auditoria | ServicoMulher.responsavel)
```

### Invariantes que a arquitetura garante

1. **Imutabilidade:** `Evento`, `DocumentoVersao` e `Auditoria` não têm rota nem método de repositório de UPDATE/DELETE. Correção de evento = novo evento de **retificação** que aponta para o original.
2. **Toda transição de status** de `ServicoMulher` gera um `Evento` automático (mesma transação).
3. **Toda mutação** (`POST/PATCH/PUT/DELETE`) grava `Auditoria` com `antes`/`depois`, usuário, IP, `request_id`.
4. **Versionamento não destrutivo:** novo upload nunca sobrescreve; cria nova versão e move o ponteiro `versao_atual` (número da versão vigente). Versões antigas continuam baixáveis.
5. **Exclusão lógica** (`deleted_at`) para `Mulher` e `Documento`. Nada some fisicamente.

## 5. Contrato de API (visão de arquitetura)

- Prefixo `/api/v1`. Mudança incompatível → `/api/v2`, mantendo a v1 durante a transição.
- **Swagger próprio do backend:** `/docs` (Swagger UI), `/redoc`, `/openapi.json`. Ver `backend.md` §8 para o padrão de documentação.
- JSON em `snake_case`, datas em ISO-8601 UTC, IDs UUID.
- Envelope padrão de listas (paginação) e de erros: definidos em `backend.md` §7.
- Autenticação: JWT Bearer (`Authorization: Bearer <token>`); o mesmo mecanismo serve Jinja2 e React.
- **CORS** configurável por `.env` (`CORS_ORIGINS`) para o React em outra origem.
- `openapi.json` exportado e versionado em `backend/docs/openapi.json`, para gerar cliente TypeScript no futuro (ex.: `openapi-typescript`).

## 6. Como cada front consome (para não travar a evolução)

| | Fase 1 — Jinja2 + HTML/CSS/JS | Fase 2 — React |
|---|---|---|
| Onde roda | Servidor próprio em `frontend/` (app Python separado) renderiza páginas | SPA estática |
| Chama a API | Servidor Jinja2 chama via `httpx` (server-side) e/ou o JS do navegador via `fetch` | `fetch`/cliente gerado |
| Token | **[ASSUNÇÃO]** guardado em cookie `HttpOnly` + `SameSite` no servidor do front; repassado como Bearer à API | Memória + refresh token, ou BFF |
| Contrato | OpenAPI | OpenAPI (idêntico) |

Consequência: **nada de sessão, template ou cookie no backend**. Detalhes do front ficam para `.claude/frontend.md`, quando forem definidos.

## 7. Dados e portabilidade SQLite → PostgreSQL

`project.md` exige agnosticismo de banco. Regras para não quebrar na migração:

- SQLAlchemy 2.0 async: `aiosqlite` (dev) e `asyncpg` (prod), escolhidos só por `DATABASE_URL`.
- **UUID:** tipo `sqlalchemy.Uuid` (vira `CHAR(32)` no SQLite, `UUID` nativo no Postgres). Sem FK circular (ex.: `documentos.versao_atual` guarda o número da versão).
- **JSON:** `sqlalchemy.JSON` (nunca `JSONB`/`ARRAY` direto). No Postgres pode-se usar `JSON().with_variant(JSONB, "postgresql")`.
- **Enums:** `String` + `CheckConstraint` (`native_enum=False`), pois ALTER de enum é problemático em SQLite e Postgres.
- **Alembic com `render_as_batch=True`** (SQLite não faz ALTER completo). Constraints com nomes determinísticos (`naming_convention`). Datas via `UTCDateTime` (sempre UTC e *aware*, pois o SQLite perde o fuso).
- SQLite: `PRAGMA foreign_keys=ON` em todo connect. Timestamps sempre UTC (`DateTime(timezone=True)`, guardando UTC).
- Sem SQL cru específico de dialeto, sem funções de banco (`now()`, `gen_random_uuid()`); a aplicação gera UUID e timestamps.
- Índices parciais (ex.: um vínculo ativo por mulher+serviço) são suportados nos dois bancos, via `sqlite_where` e `postgresql_where`.

## 8. Armazenamento de arquivos

Interface `StorageBackend` em `core/` (`save`, `open`, `delete`, `exists`), com implementações `LocalStorage` (dev, `backend/storage/`) e `S3Storage` (prod, S3/MinIO). Escolha por `STORAGE_BACKEND` no `.env`.

- O banco guarda só `storage_key` (caminho lógico), nunca caminho absoluto.
- Chave: `mulheres/{mulher_id}/documentos/{documento_id}/v{n}-{sha256[:12]}` (sem nome original no caminho). `LocalStorage` bloqueia path traversal; `S3Storage` existe mas não tem teste automatizado.
- O download **sempre passa pela API** (autorização + auditoria). Não expor URL direta do storage.

## 9. Segurança e LGPD

Dados de atendimento a mulheres, possivelmente em situação de violência, são **dados pessoais sensíveis**:

- Autenticação JWT (access curto + refresh), senha com `argon2`/`bcrypt`, bloqueio por tentativas.
- Autorização por perfil (RBAC) no `service`/dependência. Ver matriz em `backend.md` §6.
- Auditoria também de **leituras sensíveis** (abrir cadastro/resumo/linha do tempo, download de documento) — implementado; ainda é **[ASSUNÇÃO]** de negócio.
- CPF e telefone mascarados nas listagens; o detalhe traz o valor completo para qualquer perfil autenticado, com a leitura auditada (`READ_SENSITIVE`).
- Logs sem dados pessoais. `request_id` em toda requisição.
- Upload: validar MIME real, extensão e tamanho máximo, com hash SHA-256.
- Segredos só por `.env` (nunca versionado); `.env.example` versionado.

## 10. Observabilidade e qualidade

- Log de cada requisição (método, rota, status, latência) com `request_id`; o `X-Request-ID` recebido é reaproveitado ou gerado, devolvido no header e incluído no envelope de erro. (Logs em JSON estruturado ficam como evolução.)
- `GET /health` (liveness) e `GET /health/ready` (banco + storage, `503` se falhar), na raiz.
- Testes: `pytest` + `pytest-asyncio`, banco SQLite em memória por teste; testes de contrato garantem que `/openapi.json` gera e que todo endpoint tem resposta documentada.

## 11. Decisões pendentes (perguntar quando o usuário puder)

1. Perfis de usuário e permissões reais (a matriz do `backend.md` é sugestão).
2. Campos exatos do cadastro da mulher e dos documentos.
3. Status e transições reais de `ServicoMulher`.
4. Catálogo de tipos de evento.
5. Se leituras devem ser auditadas.
6. Estratégia de token no front Jinja2 (cookie no servidor do front vs. `localStorage`).
