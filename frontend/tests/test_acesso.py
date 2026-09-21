"""Login, sessão, CSRF, permissões por perfil e segurança básica."""

import asyncio

import httpx
import pytest

from app.core.config import get_settings as backend_settings
from tests.conftest import SENHA, _client, entrar, make_front, post, token


async def test_login_renderiza_e_tem_assets(anon):
    r = await anon.get("/login")
    assert r.status_code == 200 and "Entrar" in r.text and "Secretaria da Mulher" in r.text
    for asset in ("/static/css/theme.css", "/static/js/app.js", "/static/vendor/bootstrap.min.css", "/static/vendor/bootstrap.bundle.min.js", "/static/vendor/fonts/inter-latin-wght-normal.woff2", "/static/vendor/fonts/bootstrap-icons.woff2"):
        assert (await anon.get(asset)).status_code == 200, asset
    assert "cdn." not in r.text  # nada de CDN: tudo local


async def test_cabecalhos_de_seguranca(anon):
    r = await anon.get("/login")
    assert "script-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY" and r.headers["x-content-type-options"] == "nosniff"
    assert "httponly" in r.headers["set-cookie"].lower()  # cookie de sessão inacessível ao JS
    assert "<script>" not in r.text.replace('<script id="flash-data" type="application/json">', "")  # sem JS inline


async def test_rota_protegida_redireciona_para_login_com_next(anon):
    r = await anon.get("/mulheres?q=maria")
    assert r.status_code == 303 and r.headers["location"].startswith("/login?next=/mulheres")
    assert (await anon.get("/")).headers["location"] == "/login"


async def test_login_invalido_e_valido(anon, novo_usuario):
    u = await novo_usuario(__import__("app.shared.enums", fromlist=["PerfilUsuario"]).PerfilUsuario.ATENDENTE)
    r = await entrar(anon, u.email, "senha-errada1")
    assert r.status_code == 401 and "E-mail ou senha inválidos" in r.text
    r = await entrar(anon, u.email)
    assert r.status_code == 303 and r.headers["location"] == "/"
    page = await anon.get("/mulheres")
    assert page.status_code == 200 and "Bem-vinda" in page.text and u.nome in page.text


async def test_next_so_aceita_caminho_local(anon, novo_usuario):
    from app.shared.enums import PerfilUsuario

    u = await novo_usuario(PerfilUsuario.ATENDENTE)
    csrf = await token(anon)
    r = await anon.post("/login", data={"email": u.email, "senha": SENHA, "csrf_token": csrf, "next": "https://evil.example/x"})
    assert r.headers["location"] == "/"  # open redirect bloqueado


async def test_csrf_obrigatorio_em_todo_post(sessoes):
    c = sessoes["ATENDENTE"]
    r = await c.post("/mulheres/nova", data={"nome_completo": "Sem Token"})
    assert r.status_code == 403 and "inválido" in r.text.lower()
    r = await c.post("/mulheres/nova", data={"nome_completo": "Token Errado", "csrf_token": "x"})
    assert r.status_code == 403
    assert (await c.post("/logout", data={})).status_code == 403


async def test_logout_encerra_sessao_e_revoga_refresh(sessoes):
    c = sessoes["ATENDENTE"]
    assert (await c.get("/mulheres")).status_code == 200
    r = await post(c, "/logout")
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert (await c.get("/mulheres")).status_code == 303  # sessão limpa


@pytest.mark.parametrize(
    "perfil,rota,esperado",
    [
        ("ATENDENTE", "/usuarios", 403), ("GESTOR", "/usuarios", 403), ("AUDITOR", "/usuarios", 403), ("ADMIN", "/usuarios", 200),
        ("ATENDENTE", "/auditoria", 403), ("AUDITOR", "/auditoria", 200), ("GESTOR", "/auditoria", 200),
        ("ATENDENTE", "/servicos/novo", 403), ("AUDITOR", "/servicos/novo", 403), ("GESTOR", "/servicos/novo", 200),
        ("AUDITOR", "/mulheres/nova", 403), ("ATENDENTE", "/mulheres/nova", 200),
        ("AUDITOR", "/documentos/novo", 403), ("AUDITOR", "/eventos/novo", 403), ("AUDITOR", "/vinculos/novo", 403),
    ],
)
async def test_permissoes_por_perfil(sessoes, perfil, rota, esperado):
    r = await sessoes[perfil].get(rota)
    assert r.status_code == esperado, f"{perfil} {rota}: {r.status_code}"
    if esperado == 403:
        assert "não tem acesso" in r.text.lower()


async def test_menu_e_botoes_respeitam_o_perfil(sessoes):
    adm, ate, aud = [await sessoes[p].get("/mulheres") for p in ("ADMIN", "ATENDENTE", "AUDITOR")]
    assert 'href="/usuarios"' in adm.text and 'href="/auditoria"' in adm.text
    assert 'href="/usuarios"' not in ate.text and 'href="/auditoria"' not in ate.text and "Nova mulher" in ate.text
    assert 'href="/auditoria"' in aud.text and "Nova mulher" not in aud.text


async def test_pagina_404_e_api_fora_do_ar(front, sessoes):
    r = await sessoes["ATENDENTE"].get("/nao-existe")
    assert r.status_code == 404 and "Não encontramos" in r.text
    r = await sessoes["ATENDENTE"].get("/mulheres/00000000-0000-4000-8000-000000000000")
    assert r.status_code == 404  # a API respondeu 404 → página 404 do front

    class ApiFora(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            raise httpx.ConnectError("recusado", request=request)

    app = make_front(ApiFora())
    async with app.router.lifespan_context(app), await _client(app) as c:
        csrf = await token(c)
        r = await c.post("/login", data={"email": "a@b.com", "senha": "x", "csrf_token": csrf})
        assert r.status_code == 503 and "conectar" in r.text.lower()


async def test_token_expirado_renova_sozinho_e_sem_corrida(sessoes, monkeypatch):
    """Access token vencido → o front renova (refresh rotativo). Requisições simultâneas não derrubam a sessão."""
    c = sessoes["ATENDENTE"]
    monkeypatch.setattr(backend_settings(), "access_token_expire_minutes", 0)  # novos access tokens já nascem vencidos
    assert (await c.get("/mulheres")).status_code == 200  # renovou (token antigo ainda válido, mas novos vencem)
    # agora o access token da sessão está vencido; 4 requisições simultâneas com o MESMO cookie
    respostas = await asyncio.gather(*[c.get(p) for p in ("/mulheres", "/servicos", "/vinculos", "/eventos")])
    assert [r.status_code for r in respostas] == [200, 200, 200, 200]
    assert (await c.get("/documentos")).status_code == 200  # e a sessão continua válida


async def test_sessao_invalida_volta_ao_login_com_aviso(sessoes, backend):
    from sqlalchemy import update

    from app.modules.usuarios.model import Usuario

    c = sessoes["ATENDENTE"]
    async with backend() as s:  # o usuário é desativado no backend
        await s.execute(update(Usuario).where(Usuario.perfil == "ATENDENTE").values(ativo=False))
        await s.commit()
    r = await c.get("/mulheres")
    assert r.status_code == 303 and r.headers["location"].startswith("/login")
    r = await c.get("/login")
    assert "expirou" in r.text.lower()
