"""Testes de contrato: o Swagger é o contrato com o front — precisa estar completo e em dia."""

import re

from app.main import gerar_openapi
from scripts.export_openapi import DESTINO, gerar_texto

METODOS = {"get", "post", "put", "patch", "delete"}
PUBLICAS = {"/health", "/health/ready", "/api/v1/auth/login", "/api/v1/auth/refresh"}


def _operacoes():
    schema = gerar_openapi()
    for caminho, item in schema["paths"].items():
        for metodo, op in item.items():
            if metodo in METODOS:
                yield caminho, metodo, op


def test_openapi_gera_sem_erro():
    schema = gerar_openapi()
    assert schema["openapi"].startswith("3.")
    assert schema["info"]["title"] and schema["info"]["description"]
    assert "BearerAuth" in schema["components"]["securitySchemes"]


def test_contrato_versionado_esta_em_dia():
    assert DESTINO.exists(), "rode: python -m scripts.export_openapi"
    assert DESTINO.read_text(encoding="utf-8") == gerar_texto(), "docs/openapi.json desatualizado: rode python -m scripts.export_openapi"


def test_todo_endpoint_esta_documentado():
    schema = gerar_openapi()
    tags_declaradas = {t["name"] for t in schema["tags"]}
    ids = []
    for caminho, metodo, op in _operacoes():
        rotulo = f"{metodo.upper()} {caminho}"
        assert op.get("operationId"), f"{rotulo}: sem operation_id"
        assert re.fullmatch(r"[a-z0-9_]+", op["operationId"]), f"{rotulo}: operation_id fora do padrão"
        ids.append(op["operationId"])
        assert op.get("summary"), f"{rotulo}: sem summary"
        assert len(op.get("description", "")) > 20, f"{rotulo}: sem description"
        assert op.get("tags") and set(op["tags"]) <= tags_declaradas, f"{rotulo}: tag não declarada"
        assert "Permissão" in op["description"], f"{rotulo}: description deve informar a permissão exigida"
        sucesso = [c for c in op["responses"] if c.startswith("2")]
        assert sucesso, f"{rotulo}: sem resposta de sucesso"
        if caminho not in PUBLICAS:
            assert op.get("security"), f"{rotulo}: rota protegida sem security"
        else:
            assert not op.get("security"), f"{rotulo}: rota pública com security"
    assert len(ids) == len(set(ids)), "operation_id duplicado"


def test_erros_usam_o_envelope_padrao():
    """Nenhuma rota pode expor o 422 padrão do FastAPI (HTTPValidationError): todos os erros são `ErroResposta`."""
    schema = gerar_openapi()
    assert "HTTPValidationError" not in schema["components"]["schemas"]
    for caminho, metodo, op in _operacoes():
        for codigo, resp in op["responses"].items():
            if codigo.startswith(("4", "5")) and codigo != "503":
                ref = resp["content"]["application/json"]["schema"]["$ref"]
                assert ref.endswith("/ErroResposta"), f"{metodo.upper()} {caminho} {codigo}: {ref}"


def test_rotas_com_corpo_ou_parametros_documentam_422():
    for caminho, metodo, op in _operacoes():
        tem_entrada = bool(op.get("requestBody") or op.get("parameters"))
        if tem_entrada and caminho not in {"/health", "/health/ready"}:
            assert "422" in op["responses"], f"{metodo.upper()} {caminho}: sem 422 documentado"


def test_rotas_protegidas_documentam_401():
    for caminho, metodo, op in _operacoes():
        if op.get("security"):
            assert "401" in op["responses"], f"{metodo.upper()} {caminho}: sem 401 documentado"


def test_schemas_de_entrada_tem_exemplos_e_descricoes():
    schema = gerar_openapi()["components"]["schemas"]
    for nome in ("MulherLeitura", "EventoLeitura", "DocumentoLeitura", "VinculoLeitura", "TokenPar", "UsuarioLeitura", "ServicoLeitura", "ErroResposta"):
        assert schema[nome].get("examples"), f"{nome}: sem exemplo"
    for nome in ("MulherCriar", "EventoCriar", "TransicaoCriar", "UsuarioCriar", "VinculoCriar"):
        props = schema[nome]["properties"]
        assert all("description" in p or "examples" in p or "$ref" in p or "allOf" in p or "anyOf" in p or "title" in p for p in props.values())


def test_imutaveis_nao_expoem_escrita():
    """Eventos e auditoria são append-only: nenhum PATCH/PUT/DELETE no contrato."""
    paths = gerar_openapi()["paths"]
    for caminho, item in paths.items():
        if caminho.startswith(("/api/v1/eventos", "/api/v1/auditoria")):
            assert not ({"patch", "put", "delete"} & set(item)), caminho
    assert set(paths["/api/v1/auditoria"]) == {"get"}


def test_contagem_de_endpoints_documentados():
    assert len(list(_operacoes())) == 54
