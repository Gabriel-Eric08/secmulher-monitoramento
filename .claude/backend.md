# Backend — API REST (Sistema de Histórico de Serviços)

Fonte: `project.md`. Arquitetura geral em `arch.md`. Itens marcados **[ASSUNÇÃO]** não constam no `project.md`.

O backend é uma **API REST isolada** com **Swagger/OpenAPI próprio**. Não renderiza HTML. É consumida por um front Jinja2 agora e por React depois, sem mudanças.

## 1. Stack

Python 3.11+ · FastAPI (async) · SQLAlchemy 2.0 async · Pydantic v2 · Alembic · SQLite (protótipo) → PostgreSQL · Pytest + pytest-asyncio · Storage local (dev) / S3-MinIO (prod).

Dependências extras (em `pyproject.toml`): `aiosqlite`, `pydantic-settings`, `email-validator`, `python-multipart` (upload), `pyjwt`, `argon2-cffi`, `filetype` (MIME real pelo conteúdo, sem libmagic do SO), `httpx` (testes). Extras opcionais: `postgres` (`asyncpg`) e `s3` (`boto3`). Logging com o módulo padrão `logging` (sem structlog).

## 2. Estrutura

Conforme `project.md`, mais `docs/` e `scripts/`:

```
backend/
├── app/
│   ├── main.py                 # cria o app, routers, CORS, handlers, OpenAPI
│   ├── core/
│   │   ├── config.py           # Settings (pydantic-settings, lê .env)
│   │   ├── database.py         # engine async, sessionmaker, PRAGMA FK no SQLite
│   │   ├── security.py         # hash de senha, JWT
│   │   ├── exceptions.py       # handlers globais -> envelope de erro
│   │   ├── dependencies.py     # get_session, get_current_user, require_perfil, request_id
│   │   └── storage.py          # StorageBackend + Local/S3
│   ├── modules/
│   │   ├── auth/  usuarios/  mulheres/  servicos/  servicos_mulheres/
│   │   ├── eventos/  documentos/  auditoria/
│   │   └── (cada um: model.py schema.py repository.py service.py router.py)
│   └── shared/
│       ├── enums/  pagination/  exceptions/  utils/
├── migrations/                 # Alembic (render_as_batch=True)
├── tests/
├── storage/                    # arquivos locais (git-ignored)
├── docs/openapi.json           # exportado (contrato p/ o front)
├── scripts/export_openapi.py
├── .env.example  alembic.ini  pyproject.toml
```

`auth/` é módulo à parte (login/refresh/logout); `usuarios/` cuida do CRUD.

Arquivos adicionais implementados: `app/api.py` (agrega os routers v1), `app/models.py` (registra todos os models), `core/context.py` (request_id/ip/user-agent por requisição, lido pela auditoria), `core/middleware.py`, `modules/mulheres/router_aninhado.py` e `resumo.py` (rotas `/mulheres/{id}/...` e a visão consolidada, que compõem services de outros módulos), `modules/documentos/forms.py` (formulários multipart), `modules/servicos_mulheres/state_machine.py`, `modules/meta/` (enums e health) e `scripts/criar_admin.py`.

## 3. Convenções gerais

- Prefixo **`/api/v1`**. Recursos no plural, `snake_case`, kebab-case nos caminhos compostos (`servicos-mulheres`).
- IDs **UUID v4** gerados pela aplicação. Datas ISO-8601 UTC.
- `PATCH` para atualização parcial. `PUT` só se houver substituição total (não usar por padrão).
- `DELETE` = exclusão **lógica** (204). Só nos recursos que a permitem.
- Ações de domínio que não são CRUD viram sub-recurso com `POST` (ex.: `POST /servicos-mulheres/{id}/transicoes`).
- Listas sempre paginadas e ordenadas de forma estável.
- Mutação retorna o recurso atualizado (`200`/`201` + `Location`).

## 4. Modelo de dados

Colunas comuns em todas as tabelas de estado: `id (UUID, PK)`, `created_at`, `updated_at`. Tabelas append-only só têm `created_at`.

### 4.1 `usuarios`
| Coluna | Tipo | Notas |
|---|---|---|
| nome | str(150) | |
| email | str(254) | único, minúsculo |
| senha_hash | str | argon2 |
| perfil | enum `PerfilUsuario` | |
| ativo | bool | default true |
| ultimo_login_em | datetime? | |
| tentativas_falhas / bloqueado_ate | int / datetime? | bloqueio temporário |

### 4.1.1 `refresh_tokens`
`id` (= `jti` do JWT), `usuario_id`, `expira_em`, `revogado_em?`, `created_at`. Permite revogação, rotação e detecção de reuso.

### 4.2 `mulheres` **[ASSUNÇÃO de campos]**
| Coluna | Tipo | Notas |
|---|---|---|
| nome_completo | str(200) | obrigatório |
| nome_social | str(200)? | |
| cpf | str(11)? | único quando informado (parcial); validar dígitos |
| rg, data_nascimento | str? / date? | |
| telefone, telefone_alt, email | str? | |
| logradouro, numero, complemento, bairro, cidade, uf, cep | str? | endereço |
| observacoes | text? | |
| deleted_at / deleted_by | datetime? / UUID? | exclusão lógica |
| created_by / updated_by | UUID (FK usuarios) | |

Extras: `nome_busca` (nome + nome social sem acento e minúsculo, mantido pelo service) para busca insensível a acentos; `motivo_exclusao`.

Índices: `nome_busca`, `cpf` único parcial (`WHERE cpf IS NOT NULL`, vale também para excluídas), `cidade`, `deleted_at`.

### 4.3 `servicos` (catálogo) **[ASSUNÇÃO]**
`nome` (único), `descricao`, `categoria`, `ativo`.

### 4.4 `servicos_mulheres` (estado atual do vínculo)
| Coluna | Tipo | Notas |
|---|---|---|
| mulher_id | FK mulheres | |
| servico_id | FK servicos | |
| status | enum `StatusServicoMulher` | estado **atual** |
| data_inicio | date | |
| data_encerramento | date? | preenchida em status final |
| responsavel_id | FK usuarios? | |
| observacoes | text? | |

Índice único parcial: `(mulher_id, servico_id) WHERE status NOT IN ('CONCLUIDO','CANCELADO')` → só um vínculo "aberto" por mulher+serviço **[ASSUNÇÃO]**. O histórico completo está nos `eventos`.

### 4.5 `eventos` (append-only)
| Coluna | Tipo | Notas |
|---|---|---|
| mulher_id | FK | sempre |
| servico_mulher_id | FK? | quando ligado a um vínculo |
| tipo | enum `TipoEvento` | |
| titulo | str(200) | |
| descricao | text? | |
| ocorrido_em | datetime | **quando aconteceu** (informado; pode ser retroativo, nunca futuro) |
| registrado_em | datetime | **quando foi registrado** (servidor) |
| registrado_por | FK usuarios | |
| corrige_evento_id | FK eventos? | preenchido só em retificação (a leitura expõe o inverso em `retificado_por: [ids]`) |
| metadados | JSON? | ex.: `{"status_anterior":..., "status_novo":...}` |

Ordenação da linha do tempo: `ocorrido_em DESC, registrado_em DESC, id`.

### 4.6 `documentos` e `documentos_versoes`
`documentos`: `mulher_id`, `servico_mulher_id?`, `evento_id?`, `titulo`, `tipo` (enum `TipoDocumento`), `descricao?`, `versao_atual` (int — **número** da versão vigente; não é FK para evitar dependência circular, que o SQLite não resolve com `ALTER`), `deleted_at?`, `created_by`.

`documentos_versoes` (append-only): `documento_id`, `numero` (1, 2, 3…, único por documento), `nome_arquivo`, `mime_type`, `tamanho_bytes`, `sha256`, `storage_key`, `valido_de` (date?), `valido_ate` (date?) — **metadados temporais**, `motivo` (por que nova versão), `criado_por`, `created_at`.

### 4.7 `auditoria` (append-only)
`usuario_id?` (nulo em login falho), `acao` (enum `AcaoAuditoria`), `entidade` (str), `entidade_id` (UUID?), `mulher_id?` (para filtrar tudo de uma mulher), `antes` (JSON?), `depois` (JSON?), `ip`, `user_agent`, `request_id`, `created_at`. Índices: `(entidade, entidade_id)`, `mulher_id`, `usuario_id`, `created_at`. Campos sensíveis (senha, tokens) nunca entram em `antes/depois`.

## 5. Enums **[ASSUNÇÃO: valores]**

```
PerfilUsuario        ADMIN | GESTOR | ATENDENTE | AUDITOR
StatusServicoMulher  SOLICITADO | EM_ANALISE | EM_ATENDIMENTO | SUSPENSO | CONCLUIDO | CANCELADO
TipoEvento           ATENDIMENTO | ENCAMINHAMENTO | CONTATO | VISITA | MUDANCA_STATUS |
                     DOCUMENTO_ANEXADO | OBSERVACAO | RETIFICACAO | OUTRO
TipoDocumento        IDENTIFICACAO | COMPROVANTE | LAUDO | ENCAMINHAMENTO | TERMO | OUTRO
AcaoAuditoria        CREATE | UPDATE | DELETE | RESTORE | STATUS_CHANGE | UPLOAD | DOWNLOAD |
                     READ_SENSITIVE | LOGIN | LOGIN_FAILED | LOGOUT
```

Transições válidas de `StatusServicoMulher` (máquina de estados no `service`, inválida → `409`):

```
SOLICITADO     → EM_ANALISE, CANCELADO
EM_ANALISE     → EM_ATENDIMENTO, CANCELADO
EM_ATENDIMENTO → SUSPENSO, CONCLUIDO, CANCELADO
SUSPENSO       → EM_ATENDIMENTO, CANCELADO
CONCLUIDO, CANCELADO → (finais; reabrir = novo vínculo)
```

A tabela de transições fica em um único lugar (`servicos_mulheres/state_machine.py`) e é exposta em `GET /meta/enums`.

## 6. Autorização (RBAC) **[ASSUNÇÃO]**

| Recurso / ação | ADMIN | GESTOR | ATENDENTE | AUDITOR |
|---|:-:|:-:|:-:|:-:|
| Usuários (CRUD) | ✔ | – | – | – |
| Serviços (catálogo) escrita | ✔ | ✔ | – | – |
| Serviços leitura | ✔ | ✔ | ✔ | ✔ |
| Mulheres criar/editar | ✔ | ✔ | ✔ | – |
| Mulheres excluir/restaurar | ✔ | ✔ | – | – |
| Mulheres/eventos/docs leitura | ✔ | ✔ | ✔ | ✔ |
| Vínculos criar/transicionar | ✔ | ✔ | ✔ | – |
| Eventos criar/retificar | ✔ | ✔ | ✔ | – |
| Documentos upload/nova versão | ✔ | ✔ | ✔ | – |
| Documentos excluir | ✔ | ✔ | – | – |
| Auditoria leitura | ✔ | ✔ | – | ✔ |

Implementação: dependência `require_perfil(*perfis)` nos routers. Resposta `401` (sem/ token inválido) e `403` (sem permissão).

## 7. Convenções de resposta

### 7.1 Paginação (listas)
Query: `page` (≥1, default 1), `page_size` (1–100, default 20), `sort` (ex.: `-created_at,nome_completo`).

```json
{
  "items": [ ... ],
  "page": 1,
  "page_size": 20,
  "total": 134,
  "pages": 7
}
```

### 7.2 Erros (todos os erros, inclusive 422 e 500)
```json
{
  "error": {
    "code": "SERVICO_MULHER_TRANSICAO_INVALIDA",
    "message": "Não é possível ir de CONCLUIDO para EM_ATENDIMENTO.",
    "details": [ { "field": "status_novo", "issue": "transição não permitida" } ],
    "request_id": "01J..."
  }
}
```

| HTTP | Uso | `code` exemplos |
|---|---|---|
| 400 | Requisição malformada | `REQUISICAO_INVALIDA` |
| 401 | Não autenticado / token expirado | `NAO_AUTENTICADO`, `TOKEN_EXPIRADO` |
| 403 | Sem permissão | `ACESSO_NEGADO` |
| 404 | Não encontrado (ou excluído logicamente) | `MULHER_NAO_ENCONTRADA` … |
| 409 | Conflito de regra/estado | `CPF_DUPLICADO`, `VINCULO_ABERTO_EXISTENTE`, `SERVICO_MULHER_TRANSICAO_INVALIDA` |
| 413 | Arquivo grande demais | `ARQUIVO_MUITO_GRANDE` |
| 415 | Tipo de arquivo não permitido | `TIPO_ARQUIVO_NAO_PERMITIDO` |
| 422 | Falha de validação Pydantic | `VALIDACAO_FALHOU` |
| 423 | Conta bloqueada | `CONTA_BLOQUEADA` |
| 500 | Erro interno (sem vazar detalhes) | `ERRO_INTERNO` |

Exceções de domínio herdam de `AppError(code, message, status_code)` em `shared/exceptions` e são convertidas por handlers em `core/exceptions.py`.

## 8. Swagger / OpenAPI (requisito de primeira classe)

O Swagger é o contrato com o front. Ele precisa estar completo desde o primeiro endpoint.

**Exposição:** `/docs` (Swagger UI), `/redoc`, `/openapi.json`. Em produção, protegidos ou desligados por `.env` (`DOCS_ENABLED`).

**Metadados do app:** título, versão (`1.0.0`), descrição em Markdown, contato e `openapi_tags` com descrição de cada tag. Os caminhos no OpenAPI já incluem `/api/v1` (não se usa `servers` para o prefixo).

**Padrão obrigatório em TODA rota:**

- `tags=[...]` (uma por módulo), `summary` curto, `description` com regras de negócio e permissões exigidas.
- `operation_id` estável e único no formato `modulo_acao` (ex.: `mulheres_criar`). Ele vira o nome da função no cliente TypeScript gerado.
- `response_model` explícito; nunca retornar model ORM.
- `status_code` correto (`201` criação, `204` sem corpo).
- `responses={...}` documentando **todos** os erros possíveis com o schema `ErroResposta` (400/401/403/404/409/422 conforme a rota).
- Exemplos (`Field(examples=[...])` / `model_config json_schema_extra`) em todos os schemas de entrada e saída.
- Parâmetros de query/path com `description`, limites e `examples`.
- Segurança: `securitySchemes.BearerAuth` (HTTP bearer JWT) aplicado globalmente; rotas públicas (`/auth/login`, `/auth/refresh`, `/health*`) com `security=[]`.

**Schemas por recurso (padrão de nomes):** `XCriar`, `XAtualizar` (todos os campos opcionais), `XLeitura`, `XItemLista` (resumo p/ listagem), `XFiltros`. Componentes reutilizáveis: `Pagina[T]`, `ErroResposta`, `ErroDetalhe`.

**Contrato exportado:** `scripts/export_openapi.py` grava `docs/openapi.json`. Um teste falha se o arquivo estiver desatualizado, para o contrato não divergir sem ninguém notar.

## 9. Endpoints

Todos sob `/api/v1`. "Perm." referencia a matriz do §6 (A=admin, G=gestor, T=atendente, U=auditor, * = qualquer autenticado).

### 9.1 Auth — tag `Autenticação`
| Método | Rota | Descrição | Perm. | Sucesso |
|---|---|---|---|---|
| POST | `/auth/login` | email+senha → `access_token`, `refresh_token`, `expires_in`. 5 falhas seguidas bloqueiam a conta por 15 min (`423`) | pública | 200 |
| POST | `/auth/refresh` | troca refresh por novo par (rotaciona). Reuso de refresh já usado revoga todas as sessões do usuário | pública | 200 |
| POST | `/auth/logout` | corpo `{refresh_token}`; revoga o refresh token (idempotente) | * | 204 |
| GET | `/auth/me` | usuário logado + perfil | * | 200 |
| POST | `/auth/alterar-senha` | senha atual + nova | * | 204 |

### 9.2 Usuários — tag `Usuários`
| Método | Rota | Descrição | Perm. | Sucesso |
|---|---|---|---|---|
| GET | `/usuarios` | lista (filtros: `q`, `perfil`, `ativo`) | A | 200 |
| POST | `/usuarios` | cria (senha inicial) | A | 201 |
| GET | `/usuarios/{id}` | detalhe | A | 200 |
| PATCH | `/usuarios/{id}` | nome, perfil, ativo | A | 200 |
| POST | `/usuarios/{id}/redefinir-senha` | admin redefine | A | 204 |

Sem `DELETE`: usuário é desativado (`ativo=false`) para preservar a auditoria.

### 9.3 Serviços (catálogo) — tag `Serviços`
| Método | Rota | Descrição | Perm. | Sucesso |
|---|---|---|---|---|
| GET | `/servicos` | lista (`q`, `categoria`, `ativo`) | * | 200 |
| POST | `/servicos` | cria | A,G | 201 |
| GET | `/servicos/{id}` | detalhe | * | 200 |
| PATCH | `/servicos/{id}` | edita / ativa / inativa | A,G | 200 |

Sem `DELETE` (serviço já usado em vínculos; inativar).

### 9.4 Mulheres — tag `Mulheres`
| Método | Rota | Descrição | Perm. | Sucesso |
|---|---|---|---|---|
| GET | `/mulheres` | lista (`q` nome/nome social/CPF, `cpf`, `cidade`, `servico_id`, `status`, `incluir_excluidas`) | * | 200 |
| POST | `/mulheres` | cadastra (`409 CPF_DUPLICADO`) | A,G,T | 201 |
| GET | `/mulheres/{id}` | cadastro completo | * | 200 |
| PATCH | `/mulheres/{id}` | edita cadastro | A,G,T | 200 |
| DELETE | `/mulheres/{id}?motivo=...` | exclusão lógica (`motivo` obrigatório, query param, 3–500 caracteres) | A,G | 204 |
| POST | `/mulheres/{id}/restaurar` | desfaz exclusão lógica | A,G | 200 |
| GET | `/mulheres/{id}/resumo` | visão consolidada: cadastro, vínculos com **status atual**, últimos N eventos, contagem de documentos | * | 200 |
| GET | `/mulheres/{id}/servicos` | vínculos da mulher | * | 200 |
| POST | `/mulheres/{id}/servicos` | cria vínculo (status inicial `SOLICITADO`) | A,G,T | 201 |
| GET | `/mulheres/{id}/eventos` | **linha do tempo** (`tipo`, `servico_mulher_id`, `de`, `ate`) | * | 200 |
| POST | `/mulheres/{id}/eventos` | registra evento | A,G,T | 201 |
| GET | `/mulheres/{id}/documentos` | documentos da mulher | * | 200 |
| POST | `/mulheres/{id}/documentos` | cria documento + 1ª versão (multipart) | A,G,T | 201 |

Rotas aninhadas são atalhos de leitura/criação com o `mulher_id` implícito; operações sobre um item específico ficam no recurso raiz (§9.5–9.7).

### 9.5 Serviços das mulheres (vínculos) — tag `Serviços das Mulheres`
| Método | Rota | Descrição | Perm. | Sucesso |
|---|---|---|---|---|
| GET | `/servicos-mulheres` | lista global (`mulher_id`, `servico_id`, `status`, `responsavel_id`, `data_inicio_de/ate`) | * | 200 |
| GET | `/servicos-mulheres/{id}` | detalhe + status atual | * | 200 |
| PATCH | `/servicos-mulheres/{id}` | edita `responsavel_id`, `observacoes`, datas. **Não altera status** | A,G,T | 200 |
| POST | `/servicos-mulheres/{id}/transicoes` | corpo `{status_novo, motivo?, ocorrido_em?}` (`motivo` obrigatório só para `SUSPENSO` e `CANCELADO`, senão `422 MOTIVO_OBRIGATORIO`). Valida máquina de estados, atualiza status, define `data_encerramento` se final e **cria evento `MUDANCA_STATUS`** (mesma transação) | A,G,T | 200 |
| GET | `/servicos-mulheres/{id}/eventos` | linha do tempo do vínculo | * | 200 |
| GET | `/servicos-mulheres/{id}/transicoes-permitidas` | próximos status válidos p/ o front montar o botão | * | 200 |

Sem `DELETE` (cancelar = transição para `CANCELADO`).

### 9.6 Eventos — tag `Eventos`
| Método | Rota | Descrição | Perm. | Sucesso |
|---|---|---|---|---|
| GET | `/eventos` | lista global (`mulher_id`, `servico_mulher_id`, `tipo`, `de`, `ate`, `registrado_por`) | * | 200 |
| POST | `/eventos` | registra evento (`mulher_id` no corpo) | A,G,T | 201 |
| GET | `/eventos/{id}` | detalhe (inclui retificações que o apontam) | * | 200 |
| POST | `/eventos/{id}/retificacoes` | cria evento `RETIFICACAO` com `corrige_evento_id={id}` e o texto corrigido | A,G,T | 201 |

**Sem `PATCH`/`PUT`/`DELETE`.** Eventos do tipo `MUDANCA_STATUS` são gerados só pelo sistema e não podem ser criados por `POST /eventos` (`422`).

### 9.7 Documentos — tag `Documentos`
| Método | Rota | Descrição | Perm. | Sucesso |
|---|---|---|---|---|
| GET | `/documentos` | lista (`mulher_id`, `servico_mulher_id`, `tipo`, `q`, `incluir_excluidos`) | * | 200 |
| POST | `/documentos` | cria documento + versão 1 (`multipart/form-data`: `arquivo`, `mulher_id`, `titulo`, `tipo`, `valido_de?`, `valido_ate?`, …) | A,G,T | 201 |
| GET | `/documentos/{id}` | metadados + versão atual | * | 200 |
| PATCH | `/documentos/{id}` | só metadados (`titulo`, `tipo`, `descricao`) | A,G,T | 200 |
| DELETE | `/documentos/{id}` | exclusão lógica (versões preservadas) | A,G | 204 |
| POST | `/documentos/{id}/restaurar` | restaura | A,G | 200 |
| GET | `/documentos/{id}/versoes` | histórico de versões (paginado, da mais recente à mais antiga) | * | 200 |
| POST | `/documentos/{id}/versoes` | nova versão (`multipart`: `arquivo`, `motivo`, `valido_de?`, `valido_ate?`). Nunca sobrescreve; move `versao_atual_id`; cria evento `DOCUMENTO_ANEXADO` | A,G,T | 201 |
| GET | `/documentos/{id}/versoes/{numero}` | metadados da versão | * | 200 |
| GET | `/documentos/{id}/download` | baixa a **versão atual** (stream, `Content-Disposition`) | * | 200 |
| GET | `/documentos/{id}/versoes/{numero}/download` | baixa versão específica | * | 200 |

Os campos multipart são declarados individualmente com `Form()` em `documentos/forms.py` (o FastAPI não combina um modelo `Form()` com `File` no mesmo endpoint) e depois validados pelos schemas (`valido_de <= valido_ate` etc.); campos opcionais vazios (`""`, como o Swagger UI envia) são ignorados.

Regras de upload: tamanho máx. `MAX_UPLOAD_MB` (default 20), lista branca de MIME (PDF, JPG, PNG, DOC, DOCX, XLSX) validada pelo conteúdo (`filetype`; texto/executável renomeado para `.pdf` → `415`), `sha256` calculado em streaming. Se o `sha256` for igual ao da versão atual → `409 VERSAO_IDENTICA`. O download registra `AcaoAuditoria.DOWNLOAD`. No OpenAPI, os downloads documentam `content: {"application/octet-stream": {}}`.

### 9.8 Auditoria — tag `Auditoria` (somente leitura)
| Método | Rota | Descrição | Perm. | Sucesso |
|---|---|---|---|---|
| GET | `/auditoria` | lista (`usuario_id`, `acao`, `entidade`, `entidade_id`, `mulher_id`, `de`, `ate`) | A,G,U | 200 |
| GET | `/auditoria/{id}` | detalhe com `antes`/`depois` | A,G,U | 200 |
| GET | `/auditoria/entidades/{entidade}/{entidade_id}` | trilha completa de um registro | A,G,U | 200 |

Sem `POST`/`PATCH`/`DELETE`: a auditoria é escrita apenas internamente pelo `service`.

### 9.9 Meta e saúde — tags `Meta`, `Sistema`
| Método | Rota | Descrição | Perm. |
|---|---|---|---|
| GET | `/meta/enums` | todos os enums (valores + rótulos pt-BR) + tabela de transições de status. Evita duplicar constantes no front | * |
| GET | `/health` | liveness | pública |
| GET | `/health/ready` | banco + storage (`503` se algum falhar) | pública |

`/health*` ficam na **raiz** (fora de `/api/v1`), por convenção de orquestradores/balanceadores.

## 10. Regras de negócio consolidadas

1. **Estado × histórico:** o status atual vive em `servicos_mulheres.status`; o "como chegou aqui" vive em `eventos`. Nunca inferir status atual varrendo eventos.
2. **Transição de status** = atualiza vínculo + cria evento + cria auditoria, em **uma** transação (tudo ou nada).
3. **Eventos imutáveis:** correção só por retificação. A linha do tempo mostra o original e a retificação ligada a ele.
4. **`ocorrido_em` ≤ agora**; `registrado_em` é sempre do servidor.
5. **Documentos versionados:** upload nunca substitui. Todas as versões permanecem acessíveis. `valido_de <= valido_ate`.
6. **Exclusão lógica:** `Mulher` excluída some das listagens padrão e retorna `404` no detalhe, exceto com `incluir_excluidas` (A,G). Seus vínculos, eventos e documentos permanecem intactos. Não se pode criar vínculos/eventos/documentos para mulher excluída (`409`).
7. **Vínculo duplicado aberto** (mesma mulher+serviço, não final) → `409`.
8. **Serviço inativo** não aceita novos vínculos (`409`).
9. **CPF** único e com dígitos válidos quando informado. Armazenado só com dígitos.
10. **Auditoria** em toda mutação, incluindo login, upload e download. Falha ao gravar auditoria aborta a operação.

## 11. Configuração (`.env.example`)

```
APP_ENV=dev
DATABASE_URL=sqlite+aiosqlite:///./dev.db        # prod: postgresql+asyncpg://...
SECRET_KEY=troque-isto
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
CORS_ORIGINS=http://localhost:3000,http://localhost:8080
DOCS_ENABLED=true
STORAGE_BACKEND=local                             # local | s3
STORAGE_LOCAL_PATH=./storage
S3_ENDPOINT= S3_BUCKET= S3_ACCESS_KEY= S3_SECRET_KEY=
MAX_UPLOAD_MB=20
```

## 12. Testes

- Fixture com SQLite em memória e `httpx.AsyncClient` sobre o app; dependências (`get_session`, storage) sobrescritas.
- Por módulo: CRUD, permissões (403), validações (422), conflitos (409).
- Testes obrigatórios de regra crítica: transição inválida; transição gera evento e auditoria atomicamente; evento sem UPDATE/DELETE (rota inexistente → 405); nova versão preserva a antiga; download de versão antiga; exclusão lógica e restauração; `openapi.json` gerado sem erro e igual ao versionado.

## 13. Ordem de implementação sugerida

1. `core/` (config, database, security, exceptions, dependencies) + `main.py` com OpenAPI base + `/health`.
2. Alembic + `shared/`.
3. `usuarios` + `auth` (necessários para todo o resto e para a auditoria).
4. `auditoria` (serviço interno de gravação) e depois seus endpoints.
5. `servicos` → `mulheres` → `servicos_mulheres` (+ máquina de estados).
6. `eventos` (+ geração automática a partir das transições).
7. `documentos` (+ storage) e versões.
8. `meta/enums`, exportação do `openapi.json`, testes de contrato.

## 14. Estado da implementação (2026-09-21)

**Concluído:** todas as etapas do §13 — 54 operações REST, Swagger completo, migração Alembic `0001`, scripts `criar_admin` e `export_openapi`, 61 testes (fluxo completo, matriz de permissões, regras de negócio, atomicidade, auth e contrato OpenAPI).

**Como rodar** (a partir de `backend/`):

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env                       # ajustar SECRET_KEY
.venv/bin/alembic upgrade head             # cria as tabelas
.venv/bin/python -m scripts.criar_admin --nome "Admin" --email admin@secretaria.gov.br
.venv/bin/uvicorn app.main:app --reload    # Swagger em http://127.0.0.1:8000/docs
.venv/bin/pytest                           # testes
.venv/bin/python -m scripts.export_openapi # regrava docs/openapi.json após mudar a API
```

**Comportamentos decididos na implementação** (além do descrito acima):

- Toda **leitura sensível** é auditada (`READ_SENSITIVE`): `GET /mulheres/{id}`, `/resumo` e a linha do tempo `GET /mulheres/{id}/eventos`. Downloads são auditados (`DOWNLOAD`).
- Criar vínculo gera evento `MUDANCA_STATUS` (`status_anterior: null → SOLICITADO`); enviar documento/versão gera `DOCUMENTO_ANEXADO`. Eventos internos não geram auditoria própria (a operação-mãe já audita na mesma transação).
- Mulher excluída logicamente: `GET` → `404`; qualquer mutação em vínculos/eventos/documentos dela → `409 MULHER_EXCLUIDA`. Só ADMIN/GESTOR enxergam excluídos (`incluir_excluidas` / `incluir_excluidos` → `403` para os demais).
- Detalhe da mulher devolve CPF/telefone completos para **qualquer** perfil autenticado (a leitura é auditada); só as listagens mascaram.
- Admin não pode desativar a si mesmo nem alterar o próprio perfil (`409 OPERACAO_NAO_PERMITIDA`).
- Se o commit falhar depois de gravar o arquivo no storage, o arquivo órfão é removido.
- `ocorrido_em` aceita até 5 minutos no futuro (tolerância de relógio). Datetimes sem fuso são tratados como UTC.
- Queries de listagem podem referenciar **models** de outros módulos para filtros (ex.: filtrar mulheres por status do vínculo); **regras** sempre passam pelo `service` do outro módulo.
- Não testado automaticamente: `S3Storage` (requer MinIO/S3 e `boto3`) e execução em PostgreSQL. A migração usa `render_as_batch` e índices parciais com `sqlite_where`/`postgresql_where`, mas ainda deve ser validada em um Postgres real antes da produção.

**Ajuste de contrato para o front (2026-09-21):** `VinculoLeitura` passou a incluir `responsavel: {id, nome}`, e `EventoLeitura` e `DocumentoLeitura` passaram a incluir `mulher: {id, nome_completo, nome_social}` (relacionamentos com carregamento já feito por join), para que as listas globais mostrem nomes em vez de UUIDs. Mudança apenas aditiva.

## 15. Perguntas em aberto

Ver `arch.md` §11. As principais: campos reais do cadastro, status/transições reais, perfis, tipos de evento e se leituras serão auditadas.
