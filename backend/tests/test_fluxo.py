"""Fluxo completo do exemplo validado: cadastro → vínculo → transições → eventos → documentos → auditoria."""

from tests.conftest import pdf, upload

API = "/api/v1"
CPF = "529.982.247-25"


async def test_fluxo_maria(client, headers):
    ana = headers["ATENDENTE"]
    gestor = headers["GESTOR"]
    auditor = headers["AUDITOR"]

    # 1. Ana cadastra Maria
    r = await client.post(
        f"{API}/mulheres",
        json={"nome_completo": "Maria Souza da Silva", "cpf": CPF, "telefone": "(11) 91234-5678", "cidade": "São Paulo", "uf": "sp"},
        headers=ana,
    )
    assert r.status_code == 201, r.text
    maria = r.json()
    mid = maria["id"]
    assert maria["cpf"] == "52998224725" and maria["uf"] == "SP"
    assert r.headers["location"] == f"/api/v1/mulheres/{mid}"

    # CPF duplicado
    r = await client.post(f"{API}/mulheres", json={"nome_completo": "Outra Pessoa", "cpf": "52998224725"}, headers=ana)
    assert r.status_code == 409 and r.json()["error"]["code"] == "CPF_DUPLICADO"

    # 2. Gestor cria o serviço; Ana vincula → SOLICITADO
    r = await client.post(f"{API}/servicos", json={"nome": "Acompanhamento psicológico", "categoria": "Saúde"}, headers=gestor)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    r = await client.post(f"{API}/mulheres/{mid}/servicos", json={"servico_id": sid}, headers=ana)
    assert r.status_code == 201, r.text
    vid = r.json()["id"]
    assert r.json()["status"] == "SOLICITADO"
    assert r.json()["servico"]["nome"] == "Acompanhamento psicológico"

    # vínculo aberto duplicado
    r = await client.post(f"{API}/mulheres/{mid}/servicos", json={"servico_id": sid}, headers=ana)
    assert r.status_code == 409 and r.json()["error"]["code"] == "VINCULO_ABERTO_EXISTENTE"

    # 3. Documento v1 (encaminhamento)
    r = await client.post(
        f"{API}/mulheres/{mid}/documentos",
        data={"titulo": "Encaminhamento", "tipo": "ENCAMINHAMENTO", "valido_de": "2026-03-01", "valido_ate": "2026-09-01"},
        files=upload(pdf("v1"), "encaminhamento.pdf"),
        headers=ana,
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    did = doc["id"]
    assert doc["versao_atual"] == 1 and doc["versao"]["mime_type"] == "application/pdf"

    # 4. Transições
    r = await client.post(f"{API}/servicos-mulheres/{vid}/transicoes", json={"status_novo": "EM_ATENDIMENTO"}, headers=ana)
    assert r.status_code == 409 and r.json()["error"]["code"] == "SERVICO_MULHER_TRANSICAO_INVALIDA"
    r = await client.post(f"{API}/servicos-mulheres/{vid}/transicoes", json={"status_novo": "EM_ANALISE", "motivo": "Docs ok"}, headers=ana)
    assert r.status_code == 200 and r.json()["status"] == "EM_ANALISE"
    r = await client.post(f"{API}/servicos-mulheres/{vid}/transicoes", json={"status_novo": "EM_ATENDIMENTO"}, headers=ana)
    assert r.status_code == 200
    r = await client.get(f"{API}/servicos-mulheres/{vid}/transicoes-permitidas", headers=ana)
    assert [o["valor"] for o in r.json()["permitidas"]] == ["SUSPENSO", "CONCLUIDO", "CANCELADO"]
    # suspender exige motivo
    r = await client.post(f"{API}/servicos-mulheres/{vid}/transicoes", json={"status_novo": "SUSPENSO"}, headers=ana)
    assert r.status_code == 422 and r.json()["error"]["code"] == "MOTIVO_OBRIGATORIO"

    # 5. Evento retroativo + retificação
    r = await client.post(
        f"{API}/mulheres/{mid}/eventos",
        json={"tipo": "VISITA", "titulo": "Visita domiciliar", "ocorrido_em": "2026-01-10T14:00:00Z", "servico_mulher_id": vid},
        headers=ana,
    )
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["ocorrido_em"].startswith("2026-01-10") and ev["registrado_em"] > ev["ocorrido_em"]
    r = await client.post(f"{API}/eventos/{ev['id']}/retificacoes", json={"descricao": "Data correta: 12/01."}, headers=ana)
    assert r.status_code == 201 and r.json()["tipo"] == "RETIFICACAO" and r.json()["corrige_evento_id"] == ev["id"]
    r = await client.get(f"{API}/eventos/{ev['id']}", headers=ana)
    assert len(r.json()["retificado_por"]) == 1
    # eventos são imutáveis
    assert (await client.patch(f"{API}/eventos/{ev['id']}", json={"titulo": "x"}, headers=ana)).status_code == 405
    assert (await client.delete(f"{API}/eventos/{ev['id']}", headers=ana)).status_code == 405
    # tipo de sistema não pode ser criado à mão
    r = await client.post(f"{API}/eventos", json={"mulher_id": mid, "tipo": "MUDANCA_STATUS", "titulo": "fraude"}, headers=ana)
    assert r.status_code == 422

    # 6. Documento v2 (não sobrescreve) + v idêntica é rejeitada
    r = await client.post(f"{API}/documentos/{did}/versoes", data={"motivo": "Renovação"}, files=upload(pdf("v1"), "igual.pdf"), headers=ana)
    assert r.status_code == 409 and r.json()["error"]["code"] == "VERSAO_IDENTICA"
    r = await client.post(f"{API}/documentos/{did}/versoes", data={"motivo": "Renovação"}, files=upload(pdf("v2"), "renovado.pdf"), headers=ana)
    assert r.status_code == 201 and r.json()["versao_atual"] == 2
    r = await client.get(f"{API}/documentos/{did}/versoes", headers=ana)
    assert [v["numero"] for v in r.json()["items"]] == [2, 1]
    # v1 continua baixável e íntegra
    r = await client.get(f"{API}/documentos/{did}/versoes/1/download", headers=ana)
    assert r.status_code == 200 and r.content == pdf("v1")
    assert "encaminhamento.pdf" in r.headers["content-disposition"]
    r = await client.get(f"{API}/documentos/{did}/download", headers=ana)
    assert r.content == pdf("v2")

    # 7. Auditor vê a trilha do vínculo com antes/depois
    r = await client.get(f"{API}/auditoria/entidades/servico_mulher/{vid}", headers=auditor)
    assert r.status_code == 200
    acoes = [i["acao"] for i in r.json()["items"]]
    assert acoes.count("STATUS_CHANGE") == 2 and "CREATE" in acoes
    det = await client.get(f"{API}/auditoria/{next(i['id'] for i in r.json()['items'] if i['acao'] == 'STATUS_CHANGE')}", headers=auditor)
    assert det.json()["antes"]["status"] and det.json()["depois"]["status"]
    # downloads foram auditados
    r = await client.get(f"{API}/auditoria", params={"mulher_id": mid, "acao": "DOWNLOAD"}, headers=auditor)
    assert r.json()["total"] == 2

    # 8. Resumo (gestor)
    r = await client.get(f"{API}/mulheres/{mid}/resumo", headers=gestor)
    assert r.status_code == 200, r.text
    resumo = r.json()
    assert resumo["servicos"][0]["status"] == "EM_ATENDIMENTO"
    assert resumo["total_documentos"] == 1
    tipos = [e["tipo"] for e in resumo["ultimos_eventos"]]
    assert "MUDANCA_STATUS" in tipos and "DOCUMENTO_ANEXADO" in tipos and "RETIFICACAO" in tipos
    assert resumo["total_eventos"] == 1 + 1 + 1 + 2 + 2  # vínculo + evento + retif + 2 transições + 2 docs

    # timeline: ordenada por ocorrido_em desc
    r = await client.get(f"{API}/mulheres/{mid}/eventos", headers=ana)
    datas = [e["ocorrido_em"] for e in r.json()["items"]]
    assert datas == sorted(datas, reverse=True)

    # listagem mascara CPF/telefone
    r = await client.get(f"{API}/mulheres", params={"q": "maria"}, headers=ana)
    item = r.json()["items"][0]
    assert item["cpf_mascarado"] == "***.982.247-**" and item["telefone_mascarado"].endswith("5678")
    assert "cpf" not in item

    # 9. Exclusão lógica: some da lista, bloqueia mutações, gestor restaura
    assert (await client.delete(f"{API}/mulheres/{mid}", params={"motivo": "Cadastro duplicado"}, headers=ana)).status_code == 403
    assert (await client.delete(f"{API}/mulheres/{mid}", params={"motivo": "Cadastro duplicado"}, headers=gestor)).status_code == 204
    assert (await client.get(f"{API}/mulheres/{mid}", headers=ana)).status_code == 404
    assert (await client.get(f"{API}/mulheres", params={"q": "maria"}, headers=ana)).json()["total"] == 0
    r = await client.post(f"{API}/mulheres/{mid}/eventos", json={"tipo": "OBSERVACAO", "titulo": "Nota qualquer"}, headers=ana)
    assert r.status_code == 409 and r.json()["error"]["code"] == "MULHER_EXCLUIDA"
    r = await client.post(f"{API}/servicos-mulheres/{vid}/transicoes", json={"status_novo": "SUSPENSO", "motivo": "teste"}, headers=ana)
    assert r.status_code == 409 and r.json()["error"]["code"] == "MULHER_EXCLUIDA"
    assert (await client.get(f"{API}/mulheres", params={"incluir_excluidas": True}, headers=ana)).status_code == 403
    assert (await client.get(f"{API}/mulheres", params={"incluir_excluidas": True}, headers=gestor)).json()["total"] == 1
    assert (await client.post(f"{API}/mulheres/{mid}/restaurar", headers=gestor)).status_code == 200
    assert (await client.get(f"{API}/mulheres/{mid}", headers=ana)).status_code == 200
