"""Cria o primeiro usuário ADMIN (bootstrap). Uso:

    python -m scripts.criar_admin --nome "Fulana" --email admin@secretaria.gov.br
    (a senha é pedida no terminal; ou use --senha / a variável ADMIN_SENHA)
"""

import argparse
import asyncio
import getpass
import os
import sys

from sqlalchemy import select

import app.models  # noqa: F401
from app.core.database import SessionLocal
from app.core.security import hash_senha
from app.modules.usuarios.model import Usuario
from app.modules.usuarios.schema import UsuarioCriar
from app.shared.enums import PerfilUsuario


async def main(nome: str, email: str, senha: str) -> int:
    dados = UsuarioCriar(nome=nome, email=email, senha=senha, perfil=PerfilUsuario.ADMIN)  # valida e-mail/senha
    async with SessionLocal() as session:
        if await session.scalar(select(Usuario).where(Usuario.email == dados.email)):
            print(f"Já existe um usuário com o e-mail {dados.email}.", file=sys.stderr)
            return 1
        session.add(Usuario(nome=dados.nome, email=dados.email, senha_hash=hash_senha(dados.senha), perfil=dados.perfil))
        await session.commit()
    print(f"Administrador {dados.email} criado.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--nome", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--senha", default=os.environ.get("ADMIN_SENHA"))
    args = parser.parse_args()
    senha = args.senha or getpass.getpass("Senha: ")
    sys.exit(asyncio.run(main(args.nome, args.email, senha)))
