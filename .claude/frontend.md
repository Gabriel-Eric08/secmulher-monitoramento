# Frontend — Jinja2 + Bootstrap 5 (fase 1)

Arquitetura geral em `arch.md`; contrato da API em `backend.md` e no Swagger do backend (`/docs`).
O front é uma **aplicação separada** (`frontend/`, pacote `webapp`) que **só conversa com o backend por HTTP**. Nada do backend é importado em produção. Quando o front virar React, esta pasta é substituída e o backend não muda.

## 1. Stack e decisões

| Item | Escolha |
|---|---|
| Servidor | FastAPI + Jinja2 (render no servidor), porta sugerida `8090` |
| UI | Bootstrap 5.3 + Bootstrap Icons + fonte Inter, **empacotados em `static/vendor/`** (sem CDN) |
| Estilo | `static/css/theme.css`: tokens HSL **no padrão do shadcn/ui** (`--primary`, `--muted`, `--ring`, `--radius`…), branco + roxo |
| JS | `static/js/app.js`, vanilla, sem inline (CSP `script-src 'self'`); tudo funciona sem JS, o JS só melhora |
| Pacote | `webapp` (não `app`, para não colidir com o backend nos testes ponta a ponta) |

**Sobre o shadcn/ui:** é uma biblioteca React (Radix + Tailwind) e não roda em Jinja2. Foi reproduzida a **linguagem visual** dela (cards, botões outline/soft/ghost, badges, tabs, diálogos, toasts, foco com anel) sobre Bootstrap. No React, o shadcn entra nativamente com os mesmos tokens.

Cores semânticas de status (azul, âmbar, verde, vermelho) são exceção mínima à paleta roxa, porque status precisam ser distinguíveis.

## 2. Autenticação e sessão

- Login → `POST /auth/login` da API. Os tokens ficam **na sessão do front**: cookie assinado (`itsdangerous`), `HttpOnly`, `SameSite=Lax` (`Secure` com `COOKIE_SECURE=true`). **O token nunca vai ao JavaScript nem ao HTML.**
- Cada requisição ao backend leva `Authorization: Bearer`. O access token é renovado **antes** de expirar (`ensure_fresh`) e, se ainda assim vier `401`, uma vez sob demanda.
- Refresh tokens são de uso único (reuso derruba a sessão). Requisições simultâneas com o mesmo cookie **compartilham o resultado da renovação por 30 s** (`api.py`), evitando deslogar por corrida.
- Sessão inválida/desativada → redireciona para `/login?next=…` com aviso. `next` só aceita caminho local (sem open redirect).
- **CSRF:** todo `POST` exige `csrf_token` (campo oculto) igual ao da sessão.
- Cabeçalhos: CSP restrita, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`.
- Downloads passam pelo front (proxy em streaming): o navegador nunca fala com a API.

## 3. Telas e rotas (todas consomem a API; o CRUD é completo)

| Área | Rotas | API usada |
|---|---|---|
| Login/Sair | `GET/POST /login`, `POST /logout` | `/auth/login`, `/auth/logout`, `/auth/me` |
| **Mulheres** (aba principal) | `GET /mulheres` (cards + busca + filtros + ordenação + paginação), `/mulheres/nova`, `/{id}` (abas), `/{id}/editar`, `POST /{id}/excluir`, `/{id}/restaurar` | `/mulheres*`, `/servicos-mulheres` (contadores) |
| Detalhe da mulher (abas) | **Visão geral · Serviços · Linha do tempo · Documentos**, com modais: vincular serviço, mudar status, editar atendimento, novo evento, retificar, enviar documento | `/mulheres/{id}/resumo`, `/servicos`, `/eventos`, `/documentos` |
| Serviços (catálogo) | `/servicos`, `/servicos/novo`, `/{id}/editar`, `POST /{id}/ativo` | `/servicos*` |
| Atendimentos (vínculos) | `/vinculos`, `/vinculos/novo`, `/{id}`, `POST /{id}/editar`, `POST /{id}/transicao` | `/servicos-mulheres*` |
| Eventos | `/eventos`, `/eventos/novo`, `/{id}`, `POST /{id}/retificar` | `/eventos*` |
| Documentos | `/documentos`, `/documentos/novo`, `/{id}` (versões), editar, nova versão, excluir/restaurar, downloads | `/documentos*` |
| Usuários (ADMIN) | `/usuarios`, `/novo`, `/{id}/editar`, `POST /{id}/senha` | `/usuarios*` |
| Auditoria (ADMIN/GESTOR/AUDITOR) | `/auditoria` (filtros), `/auditoria/{id}` (antes × depois) | `/auditoria*` |
| Perfil | `/perfil`, `POST /perfil/senha` | `/auth/me`, `/auth/alterar-senha` |
| Apoio | `GET /mulheres/buscar?q=` (JSON do autocompletar), `GET /health` | `/mulheres` |

Permissões por perfil são aplicadas **no front** (esconde menu e botões; `403` amigável nas rotas) **e no backend** (fonte da verdade).

## 4. Componentes e comportamento

- Macros Jinja (`templates/_macros.html`): `status`, `header`, `empty`, `pager`, `th_sort`, `field`, `mulher_picker`, `dropzone`, `confirm_form`, `btn_status`, `evento_item`.
- Enums, rótulos e a **máquina de estados** vêm de `GET /meta/enums` (cache de 10 min): o front não duplica constantes.
- Erros da API: de validação → voltam ao formulário com o erro no campo e os valores preservados; demais → toast. Falha de comunicação → página `503`.
- JS: toasts, confirmação em modal (com motivo obrigatório na exclusão), máscaras (CPF, telefone, CEP, UF), autocompletar de mulher, arrastar-e-soltar de arquivo, busca com envio automático, contadores animados, barra de progresso de navegação, botão "Aguarde…" anti-duplo-clique.
- Animações suaves (entrada em cascata, hover, modal, timeline, toasts) — desligadas com `prefers-reduced-motion`.
- Regra de CSS importante: animações de entrada usam `animation-fill-mode: backwards`, **não** `both`. `both` deixa um contexto de empilhamento vivo que prende modais e dropdowns atrás do backdrop.

## 5. Configuração (`frontend/.env`)

```
API_BASE_URL=http://127.0.0.1:8000
SECRET_KEY=...            # assina o cookie de sessão (obrigatório trocar em prod)
COOKIE_SECURE=false       # true em HTTPS
SESSION_MAX_AGE_DAYS=7
TIMEZONE=America/Sao_Paulo
```

Datas chegam da API em UTC e são exibidas em `TIMEZONE`. Campos `datetime-local` são enviados com o fuso configurado.

## 6. Como rodar e testar (a partir de `frontend/`)

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]" -e "../backend[dev]"   # o backend só é necessário para os testes
cp .env.example .env
.venv/bin/uvicorn webapp.main:app --reload --port 8090     # com o backend em :8000
.venv/bin/pytest                                           # e2e: front real + backend real em memória (ASGI), sem mocks
```

## 7. Pendências / evoluções

- Filtro por mulher nas listas globais só existe via `?mulher_id=` (sem seletor visual na barra de filtros).
- Não há tela de "esqueci a senha" (a redefinição é feita por um ADMIN).
- Verificado em Chrome (headless) em desktop e celular; não testado em Firefox/Safari.
