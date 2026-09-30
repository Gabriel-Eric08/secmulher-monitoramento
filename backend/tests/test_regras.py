"""Regras de negócio, validações, documentos e atomicidade."""


import pytest
from sqlalchemy import func, select

from app.modules.eventos.model import Evento
from tests.conftest import PDF, PNG, pdf, upload

API = "/api/v1"


@pytest.fixture
async def cenario(client, headers):
    """Uma mulher + um serviço + um vínculo aberto."""
    ana = headers["ATENDENTE"]
    mid = (await client.post(f"{API}/mulheres", json={"nome_completo": "Joana D'Arc Pereira"}, headers=ana)).json()["id"]
    sid = (await client.post(f"{API}/servicos", json={"nome": "Orientação jurídica"}, headers=headers["GESTOR"])).json()["id"]
    vid = (await client.post(f"{API}/mulheres/{mid}/servicos", json={"servico_id": sid}, headers=ana)).json()["id"]
    return {"mid": mid, "sid": sid, "vid": vid, "h": ana, "gestor": headers["GESTOR"]}


# ---------- validações de entrada ----------
async def test_validacoes_mulher(client, headers):
    h = headers["ATENDENTE"]
    r = await client.post(f"{API}/mulheres", json={"nome_completo": "Fulana de Tal", "cpf": "111.111.111-11"}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDACAO_FALHOU"
    assert r.json()["error"]["details"][0]["field"] == "cpf"
    assert (await client.post(f"{API}/mulheres", json={"nome_completo": "Fulana de Tal", "data_nascimento": "2999-01-01"}, headers=h)).status_code == 422
    assert (await client.post(f"{API}/mulheres", json={"nome_completo": "Fulana de Tal", "cep": "123"}, headers=h)).status_code == 422
    assert (await client.post(f"{API}/mulheres", json={"nome_completo": "Fulana de Tal", "uf": "SPX"}, headers=h)).status_code == 422
    assert (await client.post(f"{API}/mulheres", json={"nome_completo": "Fulana de Tal", "email": "invalido"}, headers=h)).status_code == 422
    assert (await client.post(f"{API}/mulheres", json={}, headers=h)).status_code == 422


async def test_patch_parcial_e_busca_sem_acento(client, cenario):
    h, mid = cenario["h"], cenario["mid"]
    r = await client.patch(f"{API}/mulheres/{mid}", json={"nome_social": "Joaninha", "cidade": "Recife"}, headers=h)
    assert r.status_code == 200 and r.json()["nome_completo"] == "Joana D'Arc Pereira" and r.json()["cidade"] == "Recife"
    assert (await client.patch(f"{API}/mulheres/{mid}", json={"nome_completo": None}, headers=h)).status_code == 422
    for termo in ("joana", "JOANINHA", "pereira", "d'arc"):
        assert (await client.get(f"{API}/mulheres", params={"q": termo}, headers=h)).json()["total"] == 1, termo
    assert (await client.get(f"{API}/mulheres", params={"cidade": "recife"}, headers=h)).json()["total"] == 1
    assert (await client.get(f"{API}/mulheres", params={"status": "SOLICITADO"}, headers=h)).json()["total"] == 1
    assert (await client.get(f"{API}/mulheres", params={"status": "CONCLUIDO"}, headers=h)).json()["total"] == 0


async def test_paginacao_e_ordenacao(client, headers):
    h = headers["ATENDENTE"]
    for nome in ("Carla Dias", "Ana Lima", "Bia Souza"):
        await client.post(f"{API}/mulheres", json={"nome_completo": nome}, headers=h)
    r = await client.get(f"{API}/mulheres", params={"page_size": 2, "page": 2}, headers=h)
    assert r.json()["total"] == 3 and r.json()["pages"] == 2 and len(r.json()["items"]) == 1
    r = await client.get(f"{API}/mulheres", params={"sort": "-nome_completo"}, headers=h)
    assert [i["nome_completo"] for i in r.json()["items"]] == ["Carla Dias", "Bia Souza", "Ana Lima"]
    r = await client.get(f"{API}/mulheres", params={"sort": "senha"}, headers=h)
    assert r.status_code == 400 and r.json()["error"]["code"] == "ORDENACAO_INVALIDA"
    assert (await client.get(f"{API}/mulheres", params={"page_size": 1000}, headers=h)).status_code == 422


async def test_evento_futuro_e_vinculo_de_outra_mulher(client, cenario, headers):
    h, mid, vid = cenario["h"], cenario["mid"], cenario["vid"]
    r = await client.post(f"{API}/mulheres/{mid}/eventos", json={"tipo": "CONTATO", "titulo": "Ligação", "ocorrido_em": "2999-01-01T00:00:00Z"}, headers=h)
    assert r.status_code == 422
    outra = (await client.post(f"{API}/mulheres", json={"nome_completo": "Outra Mulher"}, headers=h)).json()["id"]
    r = await client.post(f"{API}/mulheres/{outra}/eventos", json={"tipo": "CONTATO", "titulo": "Ligação", "servico_mulher_id": vid}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "VINCULO_INVALIDO"


# ---------- máquina de estados ----------
async def test_ciclo_completo_e_reabertura(client, cenario):
    h, mid, sid, vid = cenario["h"], cenario["mid"], cenario["sid"], cenario["vid"]

    async def ir(status, motivo=None):
        return await client.post(f"{API}/servicos-mulheres/{vid}/transicoes", json={"status_novo": status, "motivo": motivo}, headers=h)

    assert (await ir("EM_ANALISE")).status_code == 200
    assert (await ir("EM_ATENDIMENTO")).status_code == 200
    assert (await ir("SUSPENSO", "Paciente viajou")).status_code == 200
    assert (await ir("EM_ATENDIMENTO")).status_code == 200
    r = await ir("CONCLUIDO")
    assert r.status_code == 200 and r.json()["data_encerramento"] is not None
    # estado final: nada mais
    r = await ir("EM_ATENDIMENTO")
    assert r.status_code == 409 and r.json()["error"]["code"] == "SERVICO_MULHER_TRANSICAO_INVALIDA"
    perm = (await client.get(f"{API}/servicos-mulheres/{vid}/transicoes-permitidas", headers=h)).json()
    assert perm["permitidas"] == []
    # reabrir = NOVO vínculo (o anterior está encerrado, então não há duplicidade em aberto)
    novo = await client.post(f"{API}/mulheres/{mid}/servicos", json={"servico_id": sid}, headers=h)
    assert novo.status_code == 201 and novo.json()["id"] != vid
    assert (await client.get(f"{API}/mulheres/{mid}/servicos", headers=h)).json()["total"] == 2


async def test_servico_inativo_nao_aceita_vinculo(client, cenario, headers):
    h, sid = cenario["h"], cenario["sid"]
    outra = (await client.post(f"{API}/mulheres", json={"nome_completo": "Terceira Pessoa"}, headers=h)).json()["id"]
    assert (await client.patch(f"{API}/servicos/{sid}", json={"ativo": False}, headers=cenario["gestor"])).status_code == 200
    r = await client.post(f"{API}/mulheres/{outra}/servicos", json={"servico_id": sid}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "SERVICO_INATIVO"


async def test_transicao_e_atomica(client, cenario, sessionmaker_, monkeypatch):
    """Se a auditoria falhar, o status NÃO muda e nenhum evento é criado (mesma transação)."""
    from app.modules.servicos_mulheres import service as svc
    from app.shared.exceptions import Conflito

    h, vid = cenario["h"], cenario["vid"]

    async def _falha(*a, **k):
        raise Conflito("falha simulada na auditoria", code="FALHA_SIMULADA")

    async with sessionmaker_() as s:
        eventos_antes = await s.scalar(select(func.count()).select_from(Evento))
    monkeypatch.setattr(svc.auditoria, "registrar", _falha)
    r = await client.post(f"{API}/servicos-mulheres/{vid}/transicoes", json={"status_novo": "EM_ANALISE"}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "FALHA_SIMULADA"
    monkeypatch.undo()

    assert (await client.get(f"{API}/servicos-mulheres/{vid}", headers=h)).json()["status"] == "SOLICITADO"
    async with sessionmaker_() as s:
        assert await s.scalar(select(func.count()).select_from(Evento)) == eventos_antes


# ---------- documentos ----------
async def test_upload_valida_tipo_pelo_conteudo(client, cenario):
    h, mid = cenario["h"], cenario["mid"]
    dados = {"titulo": "Arquivo teste", "tipo": "OUTRO"}
    # PDF de verdade com extensão enganosa é aceito; o MIME vem do conteúdo
    r = await client.post(f"{API}/mulheres/{mid}/documentos", data=dados, files=upload(pdf(), "foto.jpg"), headers=h)
    assert r.status_code == 201 and r.json()["versao"]["mime_type"] == "application/pdf"
    r = await client.post(f"{API}/mulheres/{mid}/documentos", data=dados, files=upload(PNG, "x.png"), headers=h)
    assert r.status_code == 201 and r.json()["versao"]["mime_type"] == "image/png"
    # executável/texto renomeado para .pdf é rejeitado
    r = await client.post(f"{API}/mulheres/{mid}/documentos", data=dados, files=upload(b"MZ\x90\x00 executavel", "virus.pdf"), headers=h)
    assert r.status_code == 415 and r.json()["error"]["code"] == "TIPO_ARQUIVO_NAO_PERMITIDO"
    r = await client.post(f"{API}/mulheres/{mid}/documentos", data=dados, files=upload(b"so texto", "a.pdf"), headers=h)
    assert r.status_code == 415
    r = await client.post(f"{API}/mulheres/{mid}/documentos", data=dados, files=upload(b"", "vazio.pdf"), headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "ARQUIVO_VAZIO"


async def test_upload_limite_de_tamanho(client, cenario, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    grande = PDF + b"0" * (1024 * 1024)
    r = await client.post(
        f"{API}/mulheres/{cenario['mid']}/documentos", data={"titulo": "Grande demais", "tipo": "OUTRO"}, files=upload(grande), headers=cenario["h"]
    )
    assert r.status_code == 413 and r.json()["error"]["code"] == "ARQUIVO_MUITO_GRANDE"


async def test_upload_validacoes_de_formulario(client, cenario):
    h, mid = cenario["h"], cenario["mid"]
    r = await client.post(
        f"{API}/mulheres/{mid}/documentos",
        data={"titulo": "Vigência errada", "tipo": "OUTRO", "valido_de": "2026-12-01", "valido_ate": "2026-01-01"},
        files=upload(pdf()),
        headers=h,
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDACAO_FALHOU"
    r = await client.post(f"{API}/mulheres/{mid}/documentos", data={"titulo": "Sem tipo"}, files=upload(pdf()), headers=h)
    assert r.status_code == 422
    r = await client.post(f"{API}/mulheres/{mid}/documentos", data={"titulo": "Sem arquivo", "tipo": "OUTRO"}, headers=h)
    assert r.status_code == 422
    # campos opcionais vazios (como o Swagger UI envia) são ignorados
    r = await client.post(
        f"{API}/mulheres/{mid}/documentos",
        data={"titulo": "Com vazios", "tipo": "OUTRO", "descricao": "", "valido_de": ""},
        files=upload(pdf()),
        headers=h,
    )
    assert r.status_code == 201, r.text


async def test_documento_global_e_exclusao_logica(client, cenario):
    h, gestor, mid = cenario["h"], cenario["gestor"], cenario["mid"]
    r = await client.post(
        f"{API}/documentos",
        data={"mulher_id": mid, "titulo": "Laudo", "tipo": "LAUDO", "servico_mulher_id": cenario["vid"]},
        files=upload(pdf("laudo"), "laudo.pdf"),
        headers=h,
    )
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    assert (await client.patch(f"{API}/documentos/{did}", json={"titulo": "Laudo médico"}, headers=h)).json()["titulo"] == "Laudo médico"
    assert (await client.patch(f"{API}/documentos/{did}", json={"tipo": None}, headers=h)).status_code == 422

    assert (await client.delete(f"{API}/documentos/{did}", headers=gestor)).status_code == 204
    assert (await client.get(f"{API}/documentos/{did}", headers=h)).status_code == 404  # atendente não vê excluído
    assert (await client.get(f"{API}/documentos/{did}", headers=gestor)).status_code == 200
    assert (await client.get(f"{API}/documentos", params={"mulher_id": mid}, headers=h)).json()["total"] == 0
    assert (await client.get(f"{API}/documentos", params={"mulher_id": mid, "incluir_excluidos": True}, headers=h)).status_code == 403
    assert (await client.get(f"{API}/documentos", params={"mulher_id": mid, "incluir_excluidos": True}, headers=gestor)).json()["total"] == 1
    # o arquivo físico foi preservado
    assert (await client.get(f"{API}/documentos/{did}/download", headers=gestor)).content == pdf("laudo")
    assert (await client.post(f"{API}/documentos/{did}/restaurar", headers=gestor)).status_code == 200
    assert (await client.post(f"{API}/documentos/{did}/restaurar", headers=gestor)).status_code == 409


async def test_arquivo_orfao_removido_se_commit_falha(client, cenario, monkeypatch):
    from app.modules.documentos import service as svc
    from app.shared.exceptions import Conflito

    async def _falha(*a, **k):
        raise Conflito("commit falhou", code="FALHA_SIMULADA")

    monkeypatch.setattr(svc, "confirmar", _falha)
    r = await client.post(
        f"{API}/mulheres/{cenario['mid']}/documentos", data={"titulo": "Doc órfão", "tipo": "OUTRO"}, files=upload(pdf("orfao")), headers=cenario["h"]
    )
    assert r.status_code == 409
    arquivos = [p for p in client.storage.base.rglob("*") if p.is_file()]  # type: ignore[attr-defined]
    assert arquivos == []



async def test_storage_no_banco(client, cenario, sessionmaker_, monkeypatch):
    """STORAGE_BACKEND=db: upload, versões e download saem da tabela `arquivos`; órfão é removido."""
    from app.core.storage import ArquivoArmazenado, DatabaseStorage, get_storage
    from app.main import app
    from app.modules.documentos import service as svc
    from app.shared.exceptions import Conflito

    app.dependency_overrides[get_storage] = lambda: DatabaseStorage(sessionmaker_)
    h, mid = cenario["h"], cenario["mid"]
    r = await client.post(f"{API}/mulheres/{mid}/documentos", data={"titulo": "RG digitalizado", "tipo": "IDENTIFICACAO"}, files=upload(pdf("v1")), headers=h)
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    assert (await client.post(f"{API}/documentos/{did}/versoes", data={"motivo": "Renovação"}, files=upload(pdf("v2")), headers=h)).status_code == 201
    assert (await client.get(f"{API}/documentos/{did}/download", headers=h)).content == pdf("v2")
    assert (await client.get(f"{API}/documentos/{did}/versoes/1/download", headers=h)).content == pdf("v1")

    async def _falha(*a, **k):
        raise Conflito("commit falhou", code="FALHA_SIMULADA")

    monkeypatch.setattr(svc, "confirmar", _falha)
    r = await client.post(f"{API}/mulheres/{mid}/documentos", data={"titulo": "Doc órfão", "tipo": "OUTRO"}, files=upload(pdf("orfao")), headers=h)
    assert r.status_code == 409
    async with sessionmaker_() as s:
        assert await s.scalar(select(func.count()).select_from(ArquivoArmazenado)) == 2
    assert (await client.get("/health/ready")).json()["storage"] is True


# ---------- auditoria ----------
async def test_auditoria_registra_antes_e_depois_e_ip(client, cenario, headers):
    h, mid = cenario["h"], cenario["mid"]
    await client.patch(f"{API}/mulheres/{mid}", json={"cidade": "Natal"}, headers=h, )
    r = await client.get(f"{API}/auditoria/entidades/mulher/{mid}", headers=headers["AUDITOR"])
    upd = next(i for i in r.json()["items"] if i["acao"] == "UPDATE")
    det = (await client.get(f"{API}/auditoria/{upd['id']}", headers=headers["AUDITOR"])).json()
    assert det["antes"]["cidade"] is None and det["depois"]["cidade"] == "Natal"
    assert det["usuario"]["nome"] and det["request_id"] and det["ip"]
    # leitura de dado sensível também é auditada
    await client.get(f"{API}/mulheres/{mid}", headers=h)
    r = await client.get(f"{API}/auditoria", params={"mulher_id": mid, "acao": "READ_SENSITIVE"}, headers=headers["AUDITOR"])
    assert r.json()["total"] == 1
    # senha nunca aparece na auditoria
    usuarios_aud = await client.get(f"{API}/auditoria", params={"entidade": "usuario"}, headers=headers["AUDITOR"])
    for item in usuarios_aud.json()["items"]:
        d = (await client.get(f"{API}/auditoria/{item['id']}", headers=headers["AUDITOR"])).json()
        assert "senha_hash" not in (d["antes"] or {}) and "senha_hash" not in (d["depois"] or {})


async def test_auditoria_e_somente_leitura(client, headers):
    aud = headers["ADMIN"]
    for metodo in ("POST", "PATCH", "PUT", "DELETE"):
        r = await client.request(metodo, f"{API}/auditoria", headers=aud)
        assert r.status_code == 405


# ---------- envelope de erro, meta e saúde ----------
async def test_envelope_de_erros(client, headers):
    r = await client.get(f"{API}/rota-inexistente", headers=headers["ADMIN"])
    assert r.status_code == 404 and r.json()["error"]["code"] == "ROTA_NAO_ENCONTRADA"
    assert r.json()["error"]["request_id"] == r.headers["x-request-id"]
    r = await client.get(f"{API}/mulheres/nao-e-uuid", headers=headers["ADMIN"])
    assert r.status_code == 422 and r.json()["error"]["details"][0]["field"] == "mulher_id"
    r = await client.get(f"{API}/mulheres", headers={**headers["ADMIN"], "X-Request-ID": "abc123"})
    assert r.headers["x-request-id"] == "abc123"


async def test_meta_enums(client, headers):
    r = await client.get(f"{API}/meta/enums", headers=headers["ATENDENTE"])
    meta = r.json()
    assert {o["valor"] for o in meta["tipos_evento_manuais"]}.isdisjoint({"MUDANCA_STATUS", "DOCUMENTO_ANEXADO", "RETIFICACAO"})
    assert meta["transicoes_status"]["EM_ATENDIMENTO"] == ["SUSPENSO", "CONCLUIDO", "CANCELADO"]
    assert meta["transicoes_status"]["CONCLUIDO"] == []
    assert meta["status_servico_mulher"][0] == {"valor": "SOLICITADO", "rotulo": "Solicitado"}


async def test_health(client):
    assert (await client.get("/health")).json() == {"status": "ok"}
    r = await client.get("/health/ready")
    assert r.status_code == 200 and r.json() == {"status": "ok", "banco": True, "storage": True}
