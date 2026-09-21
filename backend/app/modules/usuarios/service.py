import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import confirmar
from app.core.security import hash_senha
from app.modules.auditoria import service as auditoria
from app.modules.auth import repository as auth_repo
from app.modules.usuarios import repository
from app.modules.usuarios.model import Usuario
from app.modules.usuarios.schema import UsuarioAtualizar, UsuarioCriar, UsuarioFiltros
from app.shared.enums import AcaoAuditoria
from app.shared.exceptions import Conflito, NaoEncontrado
from app.shared.pagination import PaginacaoOrdenavel, ordenar, paginar
from app.shared.utils import serializar_modelo

_ORDENAVEIS = {"nome": Usuario.nome, "email": Usuario.email, "created_at": Usuario.created_at}


async def listar(
    session: AsyncSession, filtros: UsuarioFiltros, pag: PaginacaoOrdenavel
) -> tuple[list[Usuario], int]:
    stmt = ordenar(repository.consulta(filtros), pag.sort, _ORDENAVEIS, [Usuario.nome.asc()], Usuario.id)
    return await paginar(session, stmt, pag)


async def obter(session: AsyncSession, usuario_id: uuid.UUID) -> Usuario:
    usuario = await repository.obter(session, usuario_id)
    if usuario is None:
        raise NaoEncontrado("Usuário não encontrado.", code="USUARIO_NAO_ENCONTRADO")
    return usuario


async def criar(session: AsyncSession, dados: UsuarioCriar, ator: Usuario) -> Usuario:
    if await repository.obter_por_email(session, dados.email):
        raise Conflito("Já existe um usuário com este e-mail.", code="EMAIL_DUPLICADO")
    usuario = Usuario(
        nome=dados.nome, email=dados.email, senha_hash=hash_senha(dados.senha), perfil=dados.perfil
    )
    session.add(usuario)
    await session.flush()
    await auditoria.registrar(
        session,
        usuario_id=ator.id,
        acao=AcaoAuditoria.CREATE,
        entidade="usuario",
        entidade_id=usuario.id,
        depois=serializar_modelo(usuario),
    )
    await confirmar(session, code="EMAIL_DUPLICADO", message="Já existe um usuário com este e-mail.")
    return usuario


async def atualizar(session: AsyncSession, usuario_id: uuid.UUID, dados: UsuarioAtualizar, ator: Usuario) -> Usuario:
    usuario = await obter(session, usuario_id)
    campos = dados.model_dump(exclude_unset=True)
    if not campos:
        return usuario
    if usuario.id == ator.id and (
        campos.get("ativo") is False or ("perfil" in campos and campos["perfil"] != usuario.perfil)
    ):
        raise Conflito(
            "Você não pode desativar a própria conta nem alterar o próprio perfil.",
            code="OPERACAO_NAO_PERMITIDA",
        )
    antes = serializar_modelo(usuario)
    for chave, valor in campos.items():
        setattr(usuario, chave, valor)
    if campos.get("ativo") is False:
        await auth_repo.revogar_todos_do_usuario(session, usuario.id)
    await session.flush()
    await auditoria.registrar(
        session,
        usuario_id=ator.id,
        acao=AcaoAuditoria.UPDATE,
        entidade="usuario",
        entidade_id=usuario.id,
        antes=antes,
        depois=serializar_modelo(usuario),
    )
    await confirmar(session)
    return usuario


async def redefinir_senha(session: AsyncSession, usuario_id: uuid.UUID, nova_senha: str, ator: Usuario) -> None:
    usuario = await obter(session, usuario_id)
    usuario.senha_hash = hash_senha(nova_senha)
    usuario.tentativas_falhas = 0
    usuario.bloqueado_ate = None
    await auth_repo.revogar_todos_do_usuario(session, usuario.id)
    await auditoria.registrar(
        session,
        usuario_id=ator.id,
        acao=AcaoAuditoria.UPDATE,
        entidade="usuario",
        entidade_id=usuario.id,
        depois={"senha_redefinida_por_admin": True},
    )
    await confirmar(session)
