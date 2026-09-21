"""Matriz de permissões (backend.md §6): 401 sem token, 403 sem perfil."""

import uuid

import pytest

API = "/api/v1"
ID = str(uuid.uuid4())

# (método, rota, corpo, perfis que PODEM). Corpo {} basta: a checagem de perfil vem antes da validação.
ADMIN, GESTOR, ATENDENTE, AUDITOR = "ADMIN", "GESTOR", "ATENDENTE", "AUDITOR"
TODOS = {ADMIN, GESTOR, ATENDENTE, AUDITOR}
ESCRITA = {ADMIN, GESTOR, ATENDENTE}
GEST = {ADMIN, GESTOR}
AUDIT = {ADMIN, GESTOR, AUDITOR}

CASOS = [
    ("GET", "/usuarios", {ADMIN}),
    ("POST", "/usuarios", {ADMIN}),
    ("PATCH", f"/usuarios/{ID}", {ADMIN}),
    ("POST", f"/usuarios/{ID}/redefinir-senha", {ADMIN}),
    ("POST", "/servicos", GEST),
    ("PATCH", f"/servicos/{ID}", GEST),
    ("POST", "/mulheres", ESCRITA),
    ("PATCH", f"/mulheres/{ID}", ESCRITA),
    ("DELETE", f"/mulheres/{ID}?motivo=teste", GEST),
    ("POST", f"/mulheres/{ID}/restaurar", GEST),
    ("POST", f"/mulheres/{ID}/servicos", ESCRITA),
    ("POST", f"/mulheres/{ID}/eventos", ESCRITA),
    ("POST", f"/mulheres/{ID}/documentos", ESCRITA),
    ("PATCH", f"/servicos-mulheres/{ID}", ESCRITA),
    ("POST", f"/servicos-mulheres/{ID}/transicoes", ESCRITA),
    ("POST", "/eventos", ESCRITA),
    ("POST", f"/eventos/{ID}/retificacoes", ESCRITA),
    ("POST", "/documentos", ESCRITA),
    ("PATCH", f"/documentos/{ID}", ESCRITA),
    ("DELETE", f"/documentos/{ID}", GEST),
    ("POST", f"/documentos/{ID}/restaurar", GEST),
    ("POST", f"/documentos/{ID}/versoes", ESCRITA),
    ("GET", "/auditoria", AUDIT),
    ("GET", f"/auditoria/{ID}", AUDIT),
    ("GET", f"/auditoria/entidades/mulher/{ID}", AUDIT),
]


@pytest.mark.parametrize("metodo,rota,permitidos", CASOS, ids=[f"{m} {r.split('?')[0]}" for m, r, _ in CASOS])
async def test_matriz(client, headers, metodo, rota, permitidos):
    sem_token = await client.request(metodo, API + rota)
    assert sem_token.status_code == 401, sem_token.text
    for perfil in TODOS - permitidos:
        r = await client.request(metodo, API + rota, headers=headers[perfil], json={} if metodo != "DELETE" else None)
        assert r.status_code == 403, f"{perfil} deveria ser 403 em {metodo} {rota}: {r.status_code} {r.text}"
    # perfis permitidos nunca recebem 401/403 (podem receber 404/422 por ID/corpo fictício)
    for perfil in permitidos:
        r = await client.request(metodo, API + rota, headers=headers[perfil], json={} if metodo != "DELETE" else None)
        assert r.status_code not in (401, 403), f"{perfil} deveria passar em {metodo} {rota}: {r.status_code}"


async def test_leituras_livres_para_qualquer_autenticado(client, headers):
    for perfil in TODOS:
        for rota in ("/mulheres", "/servicos", "/servicos-mulheres", "/eventos", "/documentos", "/meta/enums", "/auth/me"):
            r = await client.get(API + rota, headers=headers[perfil])
            assert r.status_code == 200, f"{perfil} GET {rota}: {r.status_code}"
