# Histórico de Serviços — Secretaria da Mulher

Sistema para registrar, acompanhar e auditar os atendimentos prestados às mulheres.

| Parte | Pasta | O que é | Porta |
|---|---|---|---|
| **Backend** | `backend/` | API REST (FastAPI) com Swagger próprio | `8000` |
| **Frontend** | `frontend/` | Telas em Jinja2 + Bootstrap, que consomem a API | `8090` |

Requisitos: **Python 3.11+**. Documentação técnica em `.claude/` (`arch.md`, `backend.md`, `frontend.md`).

## Rodar em desenvolvimento

Use **dois terminais** (um para cada parte).

### 1) Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate                  # Windows: .venv\Scripts\activate
pip install -r requirements.txt            # (testes: requirements-dev.txt)
cp .env.example .env                       # Windows: copy .env.example .env

alembic upgrade head                       # cria o banco SQLite (dev.db)
python -m scripts.seed_dev --demo          # usuários + serviços + mulheres de exemplo
uvicorn app.main:app --reload --port 8000
```
Swagger: <http://127.0.0.1:8000/docs> · ReDoc: `/redoc` · Contrato: `/openapi.json`

### 2) Frontend
```bash
cd frontend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                       # API_BASE_URL já aponta para http://127.0.0.1:8000
uvicorn webapp.main:app --reload --port 8090
```
Abra <http://127.0.0.1:8090> e entre com um dos usuários abaixo.

## Usuários do seed (só desenvolvimento)

Senha de todos: **`Senha1234`**

| Perfil | E-mail |
|---|---|
| Administrador | `admin@secretaria.gov.br` |
| Gestor | `gestor@secretaria.gov.br` |
| Atendente | `atendente@secretaria.gov.br` |
| Auditor | `auditor@secretaria.gov.br` |

- `seed_dev` **se recusa a rodar com `APP_ENV=prod`**. É idempotente: pode rodar de novo sem duplicar.
- Sem `--demo` ele cria só usuários e o catálogo de serviços.
- Não há usuário padrão embutido no sistema: sem rodar o seed (ou o `criar_admin`), ninguém consegue entrar.

## Produção / primeiro acesso
```bash
python -m scripts.criar_admin --nome "Fulana" --email fulana@secretaria.gov.br   # pede a senha no terminal
```
Antes de subir: defina `APP_ENV=prod`, um `SECRET_KEY` longo e aleatório (backend **e** front; com o valor padrão a aplicação se recusa a iniciar), `COOKIE_SECURE=true` (HTTPS) e `DATABASE_URL` do PostgreSQL (`pip install asyncpg`).

## Deploy gratuito (Vercel + Neon)

Front e back são dois servidores FastAPI, então viram **dois projetos na Vercel** (mesmo repositório). Como o disco da
Vercel é efêmero, o banco fica no **Neon** (PostgreSQL). Os documentos podem ficar **no próprio banco**
(`STORAGE_BACKEND=db`, tabela `arquivos`) — sem precisar de S3. Atenção ao espaço: o Neon gratuito tem 0,5 GB.
Se crescer, troque para um bucket S3 (Cloudflare R2) com `STORAGE_BACKEND=s3`.

1. **Neon**: crie o projeto e copie a connection string (pode colar como vem, `postgresql://...?sslmode=require`).
2. *(Só se usar S3)* **R2**: crie um bucket e um token de API. O endpoint é `https://<account-id>.r2.cloudflarestorage.com`.
3. **Tabelas e administrador** — da sua máquina, apontando para o Neon:
   ```bash
   cd backend
   export DATABASE_URL='postgresql://...'      # a do Neon
   alembic upgrade head
   python -m scripts.criar_admin --nome "Fulana" --email fulana@secretaria.gov.br
   ```
4. **Projeto do backend** na Vercel: *Root Directory* = `backend`. Variáveis de ambiente:

   | Variável | Valor |
   |---|---|
   | `APP_ENV` | `prod` |
   | `SECRET_KEY` | segredo longo e aleatório (`python -c "import secrets; print(secrets.token_urlsafe(48))"`) |
   | `DATABASE_URL` | a connection string do Neon (de preferência a *pooled*) |
   | `STORAGE_BACKEND` | `db` (arquivos no banco) — ou `s3` |
   | `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION=auto` | só com `s3` (dados do R2) |
   | `MAX_UPLOAD_MB` | `4` (a Vercel recusa requisições acima de 4,5 MB) |
   | `DOCS_ENABLED` | `false` (opcional: esconde o Swagger) |

   Confira em `https://<backend>.vercel.app/health/ready` → `{"status":"ok","banco":true,"storage":true}`.
5. **Projeto do frontend** na Vercel: *Root Directory* = `frontend` (a Vercel usa o `frontend/main.py`). Variáveis:

   | Variável | Valor |
   |---|---|
   | `APP_ENV` | `prod` |
   | `SECRET_KEY` | outro segredo longo e aleatório |
   | `API_BASE_URL` | `https://<backend>.vercel.app` |
   | `COOKIE_SECURE` | `true` |
   | `MAX_UPLOAD_MB` | `4` |

Na Vercel o backend liga sozinho o modo serverless do banco (`DB_SERVERLESS`: sem pool de conexões).
O plano gratuito da Vercel é para uso pessoal/não comercial — serve para demonstração e homologação.

## Testes
```bash
cd backend  && pytest        # 61 testes
cd frontend && pip install -r requirements-dev.txt && pytest   # 37 testes ponta a ponta (sobem o backend em memória)
```

## Problemas comuns
- **Porta ocupada** (`address already in use`): use outra (`--port 8091`; se mudar a do backend, ajuste `API_BASE_URL` em `frontend/.env`).
- **"Não foi possível conectar à API"** no front: o backend não está rodando em `API_BASE_URL`.
- **Voltou para o login sozinho**: sessão expirada ou usuário desativado.
- **Resetar os dados de dev**: apague `backend/dev.db` e `backend/storage/*`, e repita `alembic upgrade head` + seed.
