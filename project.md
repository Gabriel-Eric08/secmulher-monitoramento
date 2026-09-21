# SPECIFICAÇÃO TÉCNICA E CONTEXTO DE ARQUITETURA (AI PROMPT SPEC)

**Projeto:** Sistema de Histórico de Serviços — Secretaria da Mulher  
**Objetivo:** Guia completo de arquitetura, modelo de dados e regras de negócio para implementação assistida por IA.

> ⚠️ **Nota sobre o Banco de Dados (Protótipo):**  
> Como esta é a **fase de protótipo**, iniciaremos com **SQLite** como banco de dados padrão para desenvolvimento e testes locais.  
> A arquitetura foi projetada para ser **agnóstica ao banco**, utilizando SQLAlchemy 2.0 (Async) com suporte a migrações via Alembic.  
> A migração para **PostgreSQL** (produção) será feita posteriormente sem alterações na lógica de negócio, apenas ajustando a string de conexão e eventuais tipos específicos (ex.: `JSONB` → `JSON` no SQLite).

---

## 1. Contexto e Visão Geral

O sistema é uma plataforma administrativa para **registro, acompanhamento, linha do tempo e auditoria** de atendimentos prestados às mulheres pela Secretaria da Mulher.

### Conceito Central

Separar rigorosamente **Estado Atual** de **Histórico/Linha do Tempo**:

- **Mulher:** Entidade principal (cadastro).
- **Serviços da Mulher:** Vínculo funcional com ciclo de vida (status atual).
- **Eventos:** Registros imutáveis em ordem cronológica (histórico de acontecimentos).
- **Documentos & Versões:** Arquivos com metadados temporais e versionamento não destrutivo.
- **Auditoria:** Log transversal de mutações feitas por usuários.

---

## 2. Tech Stack e Estrutura de Diretórios

### Stack

| Componente | Tecnologia |
|---|---|
| Linguagem | Python 3.11+ |
| Framework Web | FastAPI (Async) |
| ORM | SQLAlchemy 2.0 (Async Session) |
| Validação / Schemas | Pydantic v2 |
| Banco de Dados (Protótipo) | **SQLite** |
| Banco de Dados (Produção) | PostgreSQL |
| Migrações | Alembic |
| Testes | Pytest (pytest-asyncio) |
| Armazenamento | Local Storage (dev) / S3/MinIO (prod) |

### Estrutura por Módulo (Domain-Driven)

```plaintext
backend/
├── app/
│   ├── main.py
│   ├── core/
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── security.py
│   │   ├── exceptions.py
│   │   └── dependencies.py
│   ├── modules/
│   │   ├── mulheres/
│   │   │   ├── model.py
│   │   │   ├── schema.py
│   │   │   ├── repository.py
│   │   │   ├── service.py
│   │   │   └── router.py
│   │   ├── servicos/
│   │   ├── servicos_mulheres/
│   │   ├── eventos/
│   │   ├── documentos/
│   │   ├── usuarios/
│   │   └── auditoria/
│   └── shared/
│       ├── enums/
│       ├── pagination/
│       ├── exceptions/
│       └── utils/
├── migrations/
├── tests/
├── storage/
├── .env.example
├── alembic.ini
└── pyproject.toml