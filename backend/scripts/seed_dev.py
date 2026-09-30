"""Popula um banco de DESENVOLVIMENTO com usuários, serviços e (opcional) mulheres de exemplo.

    python -m scripts.seed_dev            # 4 usuários (um por perfil) + catálogo de serviços
    python -m scripts.seed_dev --demo     # ... + 8 mulheres com atendimentos, eventos e status variados

Idempotente (pode rodar de novo). Usa senhas CONHECIDAS — por isso se recusa a rodar com APP_ENV=prod.
Em produção, crie o primeiro administrador com `python -m scripts.criar_admin`.
"""

import argparse
import asyncio
import sys
from datetime import timedelta

from sqlalchemy import select

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import hash_senha
from app.modules.eventos import service as eventos
from app.modules.eventos.schema import EventoCriar
from app.modules.mulheres import service as mulheres
from app.modules.mulheres.model import Mulher
from app.modules.mulheres.schema import MulherCriar
from app.modules.servicos.model import Servico
from app.modules.servicos_mulheres import service as vinculos
from app.modules.servicos_mulheres.schema import TransicaoCriar, VinculoCriar
from app.modules.usuarios.model import Usuario
from app.shared.enums import PerfilUsuario, StatusServicoMulher, TipoEvento
from app.shared.utils import utcnow

SENHA = "Senha1234"
USUARIOS = [
    ("Administrador", "admin@secretaria.gov.br", PerfilUsuario.ADMIN),
    ("Beatriz Rocha (Gestora)", "gestor@secretaria.gov.br", PerfilUsuario.GESTOR),
    ("Ana Lima (Atendente)", "atendente@secretaria.gov.br", PerfilUsuario.ATENDENTE),
    ("Carlos Mendes (Auditor)", "auditor@secretaria.gov.br", PerfilUsuario.AUDITOR),
]
SERVICOS = [
    ("Acompanhamento psicológico", "Saúde", "Atendimento psicológico individual e em grupo."),
    ("Orientação jurídica", "Jurídico", "Orientação sobre medidas protetivas e direitos."),
    ("Assistência social (CRAS)", "Assistência", "Encaminhamento a benefícios e programas sociais."),
    ("Qualificação profissional", "Trabalho", "Cursos e inserção no mercado de trabalho."),
    ("Casa abrigo", "Proteção", "Acolhimento temporário em local sigiloso."),
]
S = StatusServicoMulher
# (nome, cpf, cidade, UF, [(índice do serviço, [status percorridos])])
MULHERES = [
    ("Maria Souza da Silva", "52998224725", "São Paulo", "SP", [(0, [S.EM_ANALISE, S.EM_ATENDIMENTO]), (1, [S.EM_ANALISE])]),
    ("Joana D'Arc Pereira", None, "Recife", "PE", [(1, [])]),
    ("Fernanda Oliveira Costa", "11144477735", "Salvador", "BA", [(0, [S.EM_ANALISE, S.EM_ATENDIMENTO, S.SUSPENSO])]),
    ("Luciana Almeida", None, "Belo Horizonte", "MG", [(2, [S.EM_ANALISE, S.EM_ATENDIMENTO, S.CONCLUIDO])]),
    ("Patrícia Gomes Ribeiro", None, "Fortaleza", "CE", [(3, [S.EM_ANALISE])]),
    ("Aline Barbosa", None, "São Paulo", "SP", [(0, [S.EM_ANALISE, S.EM_ATENDIMENTO])]),
    ("Camila Ferreira Nunes", None, "Curitiba", "PR", [(4, [S.EM_ANALISE, S.EM_ATENDIMENTO])]),
    ("Rita de Cássia Moura", None, "Recife", "PE", [(2, [S.CANCELADO])]),
]


async def main(demo: bool) -> int:
    if get_settings().app_env == "prod":
        print("Recusado: este seed usa senhas conhecidas e não roda com APP_ENV=prod.", file=sys.stderr)
        return 1
    async with SessionLocal() as s:
        for nome, email, perfil in USUARIOS:
            if not await s.scalar(select(Usuario).where(Usuario.email == email)):
                s.add(Usuario(nome=nome, email=email, senha_hash=hash_senha(SENHA), perfil=perfil))
        for nome, cat, desc in SERVICOS:
            if not await s.scalar(select(Servico).where(Servico.nome == nome)):
                s.add(Servico(nome=nome, categoria=cat, descricao=desc))
        await s.commit()
        print(f"Usuários e serviços prontos (senha de todos: {SENHA}).")
        if not demo:
            return 0

        ator = await s.scalar(select(Usuario).where(Usuario.email == "atendente@secretaria.gov.br"))
        catalogo = list((await s.scalars(select(Servico).order_by(Servico.nome))).all())
        por_nome = {sv.nome: sv for sv in catalogo}
        ordem = [por_nome[n] for n, _, _ in SERVICOS]
        criadas = 0
        for nome, cpf, cidade, uf, planos in MULHERES:
            if await s.scalar(select(Mulher).where(Mulher.nome_completo == nome)):
                continue
            m = await mulheres.criar(s, MulherCriar(nome_completo=nome, cpf=cpf, cidade=cidade, uf=uf, telefone="(11) 91234-5678"), ator)
            for idx, caminho in planos:
                v = await vinculos.criar(s, m.id, VinculoCriar(servico_id=ordem[idx].id, responsavel_id=ator.id), ator)
                for status in caminho:
                    motivo = "Solicitação da própria mulher" if status in (S.SUSPENSO, S.CANCELADO) else None
                    await vinculos.transitar(s, v.id, TransicaoCriar(status_novo=status, motivo=motivo), ator)
            await eventos.criar(
                s,
                EventoCriar(mulher_id=m.id, tipo=TipoEvento.CONTATO, titulo="Primeiro contato", descricao="Acolhimento inicial.", ocorrido_em=utcnow() - timedelta(days=3)),
                ator,
            )
            criadas += 1
        print(f"Mulheres de exemplo criadas: {criadas}.")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--demo", action="store_true", help="cria também mulheres, atendimentos e eventos de exemplo")
    sys.exit(asyncio.run(main(p.parse_args().demo)))
