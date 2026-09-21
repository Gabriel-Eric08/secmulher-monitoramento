from app.shared.enums import PerfilUsuario
from tests.conftest import SENHA

API = "/api/v1"


async def test_login_e_me(client, criar_usuario):
    u = await criar_usuario(PerfilUsuario.ATENDENTE, email="ana@teste.gov.br")
    r = await client.post(f"{API}/auth/login", json={"email": "Ana@Teste.gov.br", "senha": SENHA})  # login normaliza caixa
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 1800
    me = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json()["id"] == str(u.id) and "senha_hash" not in me.json()


async def test_sem_token_e_token_invalido(client):
    r = await client.get(f"{API}/auth/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "NAO_AUTENTICADO"
    assert r.headers["www-authenticate"] == "Bearer"
    r = await client.get(f"{API}/auth/me", headers={"Authorization": "Bearer lixo"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "TOKEN_INVALIDO"


async def test_refresh_rotaciona_e_detecta_reuso(client, criar_usuario):
    await criar_usuario(PerfilUsuario.ATENDENTE)
    par = (await client.post(f"{API}/auth/login", json={"email": "atendente@teste.gov.br", "senha": SENHA})).json()
    novo = await client.post(f"{API}/auth/refresh", json={"refresh_token": par["refresh_token"]})
    assert novo.status_code == 200
    # reapresentar o refresh antigo = reuso → 401 e derruba a família inteira
    reuso = await client.post(f"{API}/auth/refresh", json={"refresh_token": par["refresh_token"]})
    assert reuso.status_code == 401
    depois = await client.post(f"{API}/auth/refresh", json={"refresh_token": novo.json()["refresh_token"]})
    assert depois.status_code == 401
    # access token não serve como refresh
    r = await client.post(f"{API}/auth/refresh", json={"refresh_token": par["access_token"]})
    assert r.status_code == 401


async def test_logout_revoga_refresh(client, criar_usuario, login):
    await criar_usuario(PerfilUsuario.ATENDENTE)
    par = (await client.post(f"{API}/auth/login", json={"email": "atendente@teste.gov.br", "senha": SENHA})).json()
    h = {"Authorization": f"Bearer {par['access_token']}"}
    assert (await client.post(f"{API}/auth/logout", json={"refresh_token": par["refresh_token"]}, headers=h)).status_code == 204
    assert (await client.post(f"{API}/auth/refresh", json={"refresh_token": par["refresh_token"]})).status_code == 401
    # idempotente
    assert (await client.post(f"{API}/auth/logout", json={"refresh_token": par["refresh_token"]}, headers=h)).status_code == 204


async def test_bloqueio_apos_falhas(client, criar_usuario):
    await criar_usuario(PerfilUsuario.ATENDENTE)
    for _ in range(5):
        r = await client.post(f"{API}/auth/login", json={"email": "atendente@teste.gov.br", "senha": "errada123"})
        assert r.status_code == 401 and r.json()["error"]["code"] == "CREDENCIAIS_INVALIDAS"
    # agora bloqueada — mesmo com a senha certa
    r = await client.post(f"{API}/auth/login", json={"email": "atendente@teste.gov.br", "senha": SENHA})
    assert r.status_code == 423 and r.json()["error"]["code"] == "CONTA_BLOQUEADA"


async def test_email_inexistente_nao_vaza(client):
    r = await client.post(f"{API}/auth/login", json={"email": "nao@existe.gov.br", "senha": SENHA})
    assert r.status_code == 401 and r.json()["error"]["code"] == "CREDENCIAIS_INVALIDAS"


async def test_alterar_senha(client, criar_usuario, login):
    await criar_usuario(PerfilUsuario.ATENDENTE)
    par = (await client.post(f"{API}/auth/login", json={"email": "atendente@teste.gov.br", "senha": SENHA})).json()
    h = {"Authorization": f"Bearer {par['access_token']}"}
    r = await client.post(f"{API}/auth/alterar-senha", json={"senha_atual": "errada123", "nova_senha": "Nova12345"}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "SENHA_ATUAL_INCORRETA"
    r = await client.post(f"{API}/auth/alterar-senha", json={"senha_atual": SENHA, "nova_senha": "somenteletras"}, headers=h)
    assert r.status_code == 422
    r = await client.post(f"{API}/auth/alterar-senha", json={"senha_atual": SENHA, "nova_senha": "Nova12345"}, headers=h)
    assert r.status_code == 204
    assert (await client.post(f"{API}/auth/refresh", json={"refresh_token": par["refresh_token"]})).status_code == 401
    assert (await client.post(f"{API}/auth/login", json={"email": "atendente@teste.gov.br", "senha": "Nova12345"})).status_code == 200


async def test_admin_gerencia_usuarios(client, headers):
    admin = headers["ADMIN"]
    r = await client.post(
        f"{API}/usuarios",
        json={"nome": "Novo Usuário", "email": "novo@teste.gov.br", "senha": "Senha9999", "perfil": "GESTOR"},
        headers=admin,
    )
    assert r.status_code == 201 and "senha" not in r.json()
    uid = r.json()["id"]
    dup = await client.post(
        f"{API}/usuarios", json={"nome": "Outro", "email": "NOVO@teste.gov.br", "senha": "Senha9999", "perfil": "GESTOR"}, headers=admin
    )
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "EMAIL_DUPLICADO"

    # o novo usuário loga; ao ser desativado perde o acesso imediatamente
    login = await client.post(f"{API}/auth/login", json={"email": "novo@teste.gov.br", "senha": "Senha9999"})
    token = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert (await client.patch(f"{API}/usuarios/{uid}", json={"ativo": False}, headers=admin)).status_code == 200
    assert (await client.get(f"{API}/auth/me", headers=token)).status_code == 401
    assert (await client.post(f"{API}/auth/refresh", json={"refresh_token": login.json()["refresh_token"]})).status_code == 401

    # admin não desativa a si mesmo
    me = (await client.get(f"{API}/auth/me", headers=admin)).json()
    r = await client.patch(f"{API}/usuarios/{me['id']}", json={"ativo": False}, headers=admin)
    assert r.status_code == 409 and r.json()["error"]["code"] == "OPERACAO_NAO_PERMITIDA"

    # não-admin não acessa
    assert (await client.get(f"{API}/usuarios", headers=headers["GESTOR"])).status_code == 403
