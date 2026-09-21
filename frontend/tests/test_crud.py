"""CRUD completo pela interface (formulários HTML → front → API real)."""

import io
import re

from tests.conftest import local_id, pdf, post, toasts

CPF = "529.982.247-25"


async def _mulher(c, nome="Maria Souza da Silva", **extra) -> str:
    r = await post(c, "/mulheres/nova", {"nome_completo": nome, **extra})
    assert r.status_code == 303, r.text[:600]
    return local_id(r, "/mulheres")


async def _servico(c, nome="Acompanhamento psicológico") -> str:
    r = await post(c, "/servicos/novo", {"nome": nome, "categoria": "Saúde"})
    assert r.status_code == 303, r.text[:400]
    lista = await c.get("/servicos", params={"q": nome})
    return re.search(r"/servicos/([0-9a-f-]{36})/editar", lista.text).group(1)


async def test_mulheres_criar_listar_buscar_editar(sessoes):
    ate = sessoes["ATENDENTE"]
    # formulário renderiza com máscaras e seções
    form = await ate.get("/mulheres/nova")
    assert form.status_code == 200 and 'data-mask="cpf"' in form.text and "Dados pessoais" in form.text

    # validação: CPF inválido volta ao formulário com o erro no campo e os valores preservados
    r = await post(ate, "/mulheres/nova", {"nome_completo": "Fulana de Tal", "cpf": "111.111.111-11", "cidade": "Recife"})
    assert r.status_code == 422 and "CPF inválido" in r.text and 'value="Fulana de Tal"' in r.text and 'value="Recife"' in r.text

    mid = await _mulher(ate, cpf=CPF, telefone="(11) 91234-5678", cidade="São Paulo", uf="sp")
    # CPF duplicado
    r = await post(ate, "/mulheres/nova", {"nome_completo": "Outra Mulher", "cpf": CPF})
    assert r.status_code == 422 and "CPF" in r.text and "Já existe" in r.text

    # lista principal: mascarada, com busca (sem acento) e cards
    lista = await ate.get("/mulheres", params={"q": "souza"})
    assert "Maria Souza da Silva" in lista.text and "***.982.247-**" in lista.text and CPF not in lista.text
    assert "Mulheres cadastradas" in lista.text
    assert "Maria Souza" not in (await ate.get("/mulheres", params={"q": "inexistente"})).text
    assert "Nenhuma mulher encontrada" in (await ate.get("/mulheres", params={"q": "inexistente"})).text

    # detalhe (audita a leitura) — CPF completo formatado
    det = await ate.get(f"/mulheres/{mid}")
    assert det.status_code == 200 and CPF in det.text and "Visão geral" in det.text

    # editar: formulário vem preenchido; salvar; limpar campo opcional
    ed = await ate.get(f"/mulheres/{mid}/editar")
    assert 'value="Maria Souza da Silva"' in ed.text
    r = await post(ate, f"/mulheres/{mid}/editar", {"nome_completo": "Maria Souza Lima", "cpf": CPF, "cidade": "Recife", "uf": "PE", "telefone": ""})
    assert r.status_code == 303
    det = await ate.get(f"/mulheres/{mid}")
    assert "Maria Souza Lima" in det.text and "Recife" in det.text


async def test_mulheres_excluir_e_restaurar(sessoes):
    ate, ges = sessoes["ATENDENTE"], sessoes["GESTOR"]
    mid = await _mulher(ate, "Joana Excluível")
    assert "Excluir cadastro" not in (await ate.get(f"/mulheres/{mid}")).text  # atendente não vê a ação
    assert (await post(ate, f"/mulheres/{mid}/excluir", {"motivo": "duplicado"})).status_code == 403
    assert "Excluir cadastro" in (await ges.get(f"/mulheres/{mid}")).text

    r = await post(ges, f"/mulheres/{mid}/excluir", {"motivo": "Cadastro duplicado"})
    assert r.status_code == 303 and r.headers["location"] == "/mulheres"
    assert "Joana Excluível" not in (await ges.get("/mulheres")).text
    assert (await ate.get(f"/mulheres/{mid}")).status_code == 404
    # gestor enxerga excluídas e a tela de restauração
    assert "Joana Excluível" in (await ges.get("/mulheres", params={"incluir_excluidas": "true"})).text
    tela = await ges.get(f"/mulheres/{mid}")
    assert tela.status_code == 200 and "Cadastro duplicado" in tela.text and "Restaurar cadastro" in tela.text
    assert (await post(ges, f"/mulheres/{mid}/restaurar")).status_code == 303
    assert (await ate.get(f"/mulheres/{mid}")).status_code == 200


async def test_servicos_crud_e_inativacao(sessoes):
    ges, ate = sessoes["GESTOR"], sessoes["ATENDENTE"]
    sid = await _servico(ges, "Orientação jurídica")
    r = await post(ges, "/servicos/novo", {"nome": "Orientação jurídica"})
    assert r.status_code == 422 and "Já existe um serviço" in r.text
    lista = await ate.get("/servicos")
    assert "Orientação jurídica" in lista.text and "/editar" not in lista.text  # atendente lê, mas não edita

    assert (await ges.get(f"/servicos/{sid}/editar")).status_code == 200
    r = await post(ges, f"/servicos/{sid}/editar", {"nome": "Orientação jurídica gratuita", "categoria": "Jurídico", "ativo": "1"})
    assert r.status_code == 303 and "Orientação jurídica gratuita" in (await ges.get("/servicos")).text
    # inativar → some do catálogo ativo
    assert (await post(ges, f"/servicos/{sid}/ativo", {"ativo": "false"})).status_code == 303
    assert "Inativo" in (await ges.get("/servicos", params={"ativo": "false"})).text
    mid = await _mulher(ate)
    r = await post(ate, f"/mulheres/{mid}/servicos", {"servico_id": sid})
    assert r.status_code == 303
    assert any("inativo" in t for t in toasts(await ate.get(f"/mulheres/{mid}?aba=servicos")))  # erro da API exibido em toast


async def test_atendimento_completo_status_eventos_e_retificacao(sessoes):
    ate, ges = sessoes["ATENDENTE"], sessoes["GESTOR"]
    sid = await _servico(ges)
    mid = await _mulher(ate)

    # vincular (com "sou o responsável")
    r = await post(ate, f"/mulheres/{mid}/servicos", {"servico_id": sid, "assumir": "1", "observacoes": "Primeiro contato"})
    assert r.status_code == 303 and r.headers["location"].endswith("aba=servicos")
    aba = await ate.get(f"/mulheres/{mid}?aba=servicos")
    assert "Acompanhamento psicológico" in aba.text and "Solicitado" in aba.text and "Ana Atendente" in aba.text
    vid = re.search(r"/vinculos/([0-9a-f-]{36})", aba.text).group(1)
    assert any("Já existe um vínculo" in t for t in toasts(await ate.get(f"/mulheres/{mid}?aba=servicos")) ) is False  # 1º vínculo: sem erro
    dup = await post(ate, f"/mulheres/{mid}/servicos", {"servico_id": sid})
    assert dup.status_code == 303
    assert any("Já existe um vínculo" in t for t in toasts(await ate.get(f"/mulheres/{mid}?aba=servicos")))

    # transição inválida e válidas
    r = await post(ate, f"/vinculos/{vid}/transicao", {"status_novo": "EM_ATENDIMENTO"})
    assert any("Não é possível ir de SOLICITADO" in t for t in toasts(await ate.get(f"/vinculos/{vid}")))
    await post(ate, f"/vinculos/{vid}/transicao", {"status_novo": "EM_ANALISE", "motivo": "Documentos ok"})
    await post(ate, f"/vinculos/{vid}/transicao", {"status_novo": "EM_ATENDIMENTO"})
    det = await ate.get(f"/vinculos/{vid}")
    assert "Em atendimento" in det.text and "Suspenso" in det.text and "Concluído" in det.text  # próximos status possíveis
    assert "Status alterado: EM_ANALISE → EM_ATENDIMENTO" in det.text  # evento automático na linha do tempo do vínculo
    lista = await ate.get("/vinculos", params={"status": "EM_ATENDIMENTO"})
    assert "Maria Souza da Silva" in lista.text and "Em atendimento" in lista.text
    # suspender exige motivo
    await post(ate, f"/vinculos/{vid}/transicao", {"status_novo": "SUSPENSO"})
    assert any("motivo" in t.lower() for t in toasts(await ate.get(f"/vinculos/{vid}")))

    # editar vínculo
    r = await post(ate, f"/vinculos/{vid}/editar", {"observacoes": "Retomar em abril", "data_inicio": "2026-03-01"})
    assert r.status_code == 303 and "Retomar em abril" in (await ate.get(f"/vinculos/{vid}")).text

    # eventos: criar (retroativo), ver na linha do tempo, retificar
    r = await post(ate, f"/mulheres/{mid}/eventos", {"tipo": "VISITA", "titulo": "Visita domiciliar", "descricao": "Sem intercorrências", "ocorrido_em": "2026-01-10T14:00", "servico_mulher_id": vid})
    assert r.status_code == 303 and r.headers["location"].endswith("aba=linha")
    linha = await ate.get(f"/mulheres/{mid}?aba=linha")
    assert "Visita domiciliar" in linha.text and "10/01/2026" in linha.text
    eid = re.search(r"/eventos/([0-9a-f-]{36})", (await ate.get("/eventos", params={"tipo": "VISITA"})).text).group(1)
    r = await post(ate, f"/eventos/{eid}/retificar", {"descricao": "A visita foi no dia 12."})
    assert r.status_code == 303
    novo_id = local_id(r, "/eventos")
    det = await ate.get(f"/eventos/{eid}")
    assert "Retificações" in det.text and "A visita foi no dia 12." in det.text
    ret = await ate.get(f"/eventos/{novo_id}")
    assert "retifica" in ret.text and "Visita domiciliar" in ret.text
    # evento global + filtros
    assert "Visita domiciliar" in (await ate.get("/eventos", params={"tipo": "VISITA"})).text
    assert "Visita domiciliar" not in (await ate.get("/eventos", params={"tipo": "CONTATO"})).text
    # criar evento pela página global (picker envia mulher_id)
    r = await post(ate, "/eventos/novo", {"mulher_id": mid, "tipo": "CONTATO", "titulo": "Ligação de retorno"})
    assert r.status_code == 303
    assert "Ligação de retorno" in (await ate.get(f"/mulheres/{mid}?aba=linha")).text
    # sem mulher escolhida
    r = await post(ate, "/eventos/novo", {"tipo": "CONTATO", "titulo": "Sem mulher"})
    assert r.status_code == 303 and r.headers["location"] == "/eventos/novo"

    # resumo (visão geral) reúne serviços e últimos eventos
    visao = await ate.get(f"/mulheres/{mid}")
    assert "Últimos eventos" in visao.text and "Acompanhamento psicológico" in visao.text


async def test_novo_atendimento_pela_pagina_global(sessoes):
    ate, ges = sessoes["ATENDENTE"], sessoes["GESTOR"]
    sid, mid = await _servico(ges), await _mulher(ate)
    form = await ate.get("/vinculos/novo")
    assert "picker" in form.text and "Acompanhamento psicológico" in form.text
    r = await post(ate, "/vinculos/novo", {"mulher_id": mid, "servico_id": sid, "assumir": "1"})
    assert r.status_code == 303 and "/vinculos/" in r.headers["location"]
    assert "Maria Souza da Silva" in (await ate.get(r.headers["location"])).text


async def test_busca_para_o_seletor_de_mulher(sessoes):
    ate = sessoes["ATENDENTE"]
    await _mulher(ate, "Beatriz Almeida")
    r = await ate.get("/mulheres/buscar", params={"q": "beat"})
    assert r.status_code == 200 and r.json()[0]["nome"] == "Beatriz Almeida" and "id" in r.json()[0]
    assert (await ate.get("/mulheres/buscar", params={"q": "b"})).json() == []  # mínimo 2 letras


async def test_documentos_upload_versoes_download_e_exclusao(sessoes):
    ate, ges = sessoes["ATENDENTE"], sessoes["GESTOR"]
    mid = await _mulher(ate)
    arq = lambda conteudo, nome="encaminhamento.pdf": {"arquivo": (nome, io.BytesIO(conteudo), "application/pdf")}  # noqa: E731

    # upload pela aba da mulher
    csrf_data = {"titulo": "Encaminhamento", "tipo": "ENCAMINHAMENTO", "valido_de": "2026-03-01", "valido_ate": "2026-09-01"}
    from tests.conftest import token

    r = await ate.post(f"/mulheres/{mid}/documentos", data={**csrf_data, "csrf_token": await token(ate)}, files=arq(pdf("v1")))
    assert r.status_code == 303 and r.headers["location"].endswith("aba=documentos")
    aba = await ate.get(f"/mulheres/{mid}?aba=documentos")
    assert "Encaminhamento" in aba.text and "v1" in aba.text
    did = re.search(r"/documentos/([0-9a-f-]{36})", aba.text).group(1)

    # tipo inválido (executável) — erro amigável via toast
    r = await ate.post(f"/mulheres/{mid}/documentos", data={"titulo": "Vírus", "tipo": "OUTRO", "csrf_token": await token(ate)}, files=arq(b"MZ\x90 exe", "virus.pdf"))
    assert r.status_code == 303
    assert any("Tipo de arquivo não permitido" in t for t in toasts(await ate.get(f"/mulheres/{mid}?aba=documentos")))
    # sem arquivo
    r = await post(ate, f"/mulheres/{mid}/documentos", {"titulo": "Sem arquivo", "tipo": "OUTRO"})
    assert any("Selecione um arquivo" in t for t in toasts(await ate.get(f"/mulheres/{mid}?aba=documentos")))

    # nova versão (a antiga continua baixável) e versão idêntica é recusada
    r = await ate.post(f"/documentos/{did}/versoes", data={"motivo": "Renovação", "csrf_token": await token(ate)}, files=arq(pdf("v2"), "renovado.pdf"))
    assert r.status_code == 303
    det = await ate.get(f"/documentos/{did}")
    assert "v2" in det.text and "Renovação" in det.text and "renovado.pdf" in det.text and "atual" in det.text
    await ate.post(f"/documentos/{did}/versoes", data={"motivo": "Repetido", "csrf_token": await token(ate)}, files=arq(pdf("v2")))
    assert any("idêntico" in t for t in toasts(await ate.get(f"/documentos/{did}")))

    # downloads passam pelo front (o token não vai ao navegador) e o conteúdo é íntegro
    atual = await ate.get(f"/documentos/{did}/download")
    assert atual.status_code == 200 and atual.content == pdf("v2") and "attachment" in atual.headers["content-disposition"]
    v1 = await ate.get(f"/documentos/{did}/versoes/1/download")
    assert v1.content == pdf("v1") and "encaminhamento.pdf" in v1.headers["content-disposition"]
    assert (await ate.get(f"/documentos/{did}/versoes/9/download")).status_code == 404

    # metadados + lista global com filtros
    assert (await post(ate, f"/documentos/{did}/editar", {"titulo": "Encaminhamento CRAS", "tipo": "ENCAMINHAMENTO", "descricao": "Renovado"})).status_code == 303
    lista = await ate.get("/documentos", params={"q": "cras"})
    assert "Encaminhamento CRAS" in lista.text and "Maria Souza da Silva" in lista.text
    assert "Nenhum documento" in (await ate.get("/documentos", params={"tipo": "LAUDO"})).text

    # excluir (só gestor) → some; gestor vê e restaura
    assert (await post(ate, f"/documentos/{did}/excluir")).status_code == 403
    assert (await post(ges, f"/documentos/{did}/excluir")).status_code == 303
    assert (await ate.get(f"/documentos/{did}")).status_code == 404
    assert "Encaminhamento CRAS" not in (await ges.get("/documentos")).text
    assert "Excluídos" in (await ges.get("/documentos")).text
    assert "Restaurar" in (await ges.get(f"/documentos/{did}")).text
    assert (await post(ges, f"/documentos/{did}/restaurar")).status_code == 303
    assert (await ate.get(f"/documentos/{did}")).status_code == 200


async def test_documento_pela_pagina_global(sessoes):
    ate = sessoes["ATENDENTE"]
    mid = await _mulher(ate)
    from tests.conftest import token

    r = await ate.post("/documentos/novo", data={"mulher_id": mid, "titulo": "Laudo médico", "tipo": "LAUDO", "csrf_token": await token(ate)}, files={"arquivo": ("laudo.pdf", io.BytesIO(pdf("l")), "application/pdf")})
    assert r.status_code == 303 and r.headers["location"] == "/documentos"
    assert "Laudo médico" in (await ate.get("/documentos")).text
    r = await post(ate, "/documentos/novo", {"titulo": "x", "tipo": "OUTRO"})  # sem mulher
    assert r.headers["location"] == "/documentos/novo"


async def test_usuarios_admin_crud_e_redefinir_senha(sessoes, front):
    from tests.conftest import _client, entrar

    adm = sessoes["ADMIN"]
    r = await post(adm, "/usuarios/novo", {"nome": "Carla Nova", "email": "carla@teste.gov.br", "senha": "curta", "perfil": "ATENDENTE"})
    assert r.status_code == 422 and "senha" in r.text.lower()
    r = await post(adm, "/usuarios/novo", {"nome": "Carla Nova", "email": "carla@teste.gov.br", "senha": "Senha9999", "perfil": "ATENDENTE"})
    assert r.status_code == 303
    r = await post(adm, "/usuarios/novo", {"nome": "Carla 2", "email": "CARLA@teste.gov.br", "senha": "Senha9999", "perfil": "ATENDENTE"})
    assert r.status_code == 422 and "Já existe um usuário" in r.text
    lista = await adm.get("/usuarios", params={"q": "carla"})
    assert "Carla Nova" in lista.text
    uid = re.search(r"/usuarios/([0-9a-f-]{36})/editar", lista.text).group(1)

    async with await _client(front) as carla:  # a Carla consegue entrar…
        assert (await entrar(carla, "carla@teste.gov.br", "Senha9999")).status_code == 303
        # …até ser desativada (efeito imediato)
        assert (await post(adm, f"/usuarios/{uid}/editar", {"nome": "Carla Nova", "perfil": "GESTOR"})).status_code == 303  # sem "ativo" = desativa
        assert (await carla.get("/mulheres")).status_code == 303
    assert "Inativo" in (await adm.get("/usuarios", params={"ativo": "false"})).text
    await post(adm, f"/usuarios/{uid}/editar", {"nome": "Carla Nova", "perfil": "GESTOR", "ativo": "1"})
    assert (await post(adm, f"/usuarios/{uid}/senha", {"nova_senha": "Outra12345"})).status_code == 303
    async with await _client(front) as carla:
        assert (await entrar(carla, "carla@teste.gov.br", "Outra12345")).status_code == 303
    # admin não desativa a si mesmo
    meu = re.search(r"/usuarios/([0-9a-f-]{36})/editar", (await adm.get("/usuarios", params={"q": "Ana Admin"})).text).group(1)
    await post(adm, f"/usuarios/{meu}/editar", {"nome": "Ana Admin", "perfil": "ADMIN"})
    assert (await adm.get("/mulheres")).status_code == 200


async def test_auditoria_lista_e_detalhe_com_antes_e_depois(sessoes):
    ate, aud = sessoes["ATENDENTE"], sessoes["AUDITOR"]
    mid = await _mulher(ate)
    await post(ate, f"/mulheres/{mid}/editar", {"nome_completo": "Maria Souza da Silva", "cidade": "Natal"})
    lista = await aud.get("/auditoria", params={"entidade": "mulher", "acao": "UPDATE"})
    assert lista.status_code == 200 and "Atualização" in lista.text
    rid = re.search(r"/auditoria/([0-9a-f-]{36})", lista.text).group(1)
    det = await aud.get(f"/auditoria/{rid}")
    assert "cidade" in det.text and "Natal" in det.text and "diff-new" in det.text and "campo(s) alterado(s)" in det.text
    assert "senha_hash" not in det.text
    # filtros de período aceitam datas do formulário
    assert (await aud.get("/auditoria", params={"de": "2020-01-01", "ate": "2099-12-31"})).status_code == 200


async def test_perfil_e_troca_de_senha(sessoes, front):
    from tests.conftest import _client, entrar

    ate = sessoes["ATENDENTE"]
    perfil = await ate.get("/perfil")
    assert perfil.status_code == 200 and "atendente@teste.gov.br" in perfil.text
    r = await post(ate, "/perfil/senha", {"senha_atual": "errada123", "nova_senha": "Nova12345", "confirmar": "Nova12345"})
    assert r.status_code == 422 and "incorreta" in r.text
    r = await post(ate, "/perfil/senha", {"senha_atual": "Senha1234", "nova_senha": "Nova12345", "confirmar": "Diferente1"})
    assert r.status_code == 422 and "não confere" in r.text
    r = await post(ate, "/perfil/senha", {"senha_atual": "Senha1234", "nova_senha": "Nova12345", "confirmar": "Nova12345"})
    assert r.status_code == 303 and r.headers["location"] == "/login"  # precisa entrar de novo
    assert (await ate.get("/mulheres")).status_code == 303
    async with await _client(front) as novo:
        assert (await entrar(novo, "atendente@teste.gov.br", "Nova12345")).status_code == 303
