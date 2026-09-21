import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import confirmar
from app.modules.auditoria import service as auditoria
from app.modules.mulheres import repository
from app.modules.mulheres.model import Mulher
from app.modules.mulheres.schema import MulherAtualizar, MulherCriar, MulherFiltros
from app.modules.usuarios.model import Usuario
from app.shared.enums import AcaoAuditoria, PerfilUsuario
from app.shared.exceptions import AcessoNegado, Conflito, NaoEncontrado
from app.shared.pagination import PaginacaoOrdenavel, ordenar, paginar
from app.shared.utils import normalizar_texto, serializar_modelo, utcnow

_ORDENAVEIS = {
    "nome_completo": Mulher.nome_completo,
    "cidade": Mulher.cidade,
    "created_at": Mulher.created_at,
}
_MSG_CPF = "Já existe uma mulher cadastrada com este CPF."
_PODEM_VER_EXCLUIDAS = {PerfilUsuario.ADMIN, PerfilUsuario.GESTOR}


def _nome_busca(nome: str, nome_social: str | None) -> str:
    return normalizar_texto(f"{nome} {nome_social or ''}")


def _pode_ver_excluidas(ator: Usuario) -> bool:
    return ator.perfil in _PODEM_VER_EXCLUIDAS


async def listar(
    session: AsyncSession, filtros: MulherFiltros, pag: PaginacaoOrdenavel, ator: Usuario
) -> tuple[list[Mulher], int]:
    if filtros.incluir_excluidas and not _pode_ver_excluidas(ator):
        raise AcessoNegado("Apenas ADMIN e GESTOR podem incluir cadastros excluídos.")
    stmt = repository.consulta(filtros, filtros.incluir_excluidas)
    stmt = ordenar(stmt, pag.sort, _ORDENAVEIS, [Mulher.nome_completo.asc()], Mulher.id)
    return await paginar(session, stmt, pag)


async def obter_ou_404(session: AsyncSession, mulher_id: uuid.UUID, *, incluir_excluida: bool = False) -> Mulher:
    mulher = await repository.obter(session, mulher_id)
    if mulher is None or (mulher.deleted_at is not None and not incluir_excluida):
        raise NaoEncontrado("Mulher não encontrada.", code="MULHER_NAO_ENCONTRADA")
    return mulher


async def exigir_ativa(session: AsyncSession, mulher_id: uuid.UUID) -> Mulher:
    """Para mutações de outros módulos: 404 se não existe, 409 se excluída logicamente."""
    mulher = await repository.obter(session, mulher_id)
    if mulher is None:
        raise NaoEncontrado("Mulher não encontrada.", code="MULHER_NAO_ENCONTRADA")
    if mulher.deleted_at is not None:
        raise Conflito("Esta mulher está com o cadastro excluído.", code="MULHER_EXCLUIDA")
    return mulher


async def obter_para_leitura(
    session: AsyncSession, mulher_id: uuid.UUID, ator: Usuario, *, incluir_excluida: bool = False
) -> Mulher:
    """Leitura de dado sensível: valida acesso e **audita** (`READ_SENSITIVE`)."""
    if incluir_excluida and not _pode_ver_excluidas(ator):
        incluir_excluida = False
    mulher = await obter_ou_404(session, mulher_id, incluir_excluida=incluir_excluida)
    await auditoria.registrar(
        session,
        usuario_id=ator.id,
        acao=AcaoAuditoria.READ_SENSITIVE,
        entidade="mulher",
        entidade_id=mulher.id,
        mulher_id=mulher.id,
    )
    await session.commit()
    return mulher


async def criar(session: AsyncSession, dados: MulherCriar, ator: Usuario) -> Mulher:
    dados_dict = dados.model_dump()
    if dados.cpf and await repository.obter_por_cpf(session, dados.cpf):
        raise Conflito(_MSG_CPF, code="CPF_DUPLICADO")
    mulher = Mulher(
        **dados_dict,
        nome_busca=_nome_busca(dados.nome_completo, dados.nome_social),
        created_by=ator.id,
        updated_by=ator.id,
    )
    session.add(mulher)
    await session.flush()
    await auditoria.registrar(
        session,
        usuario_id=ator.id,
        acao=AcaoAuditoria.CREATE,
        entidade="mulher",
        entidade_id=mulher.id,
        mulher_id=mulher.id,
        depois=serializar_modelo(mulher),
    )
    await confirmar(session, code="CPF_DUPLICADO", message=_MSG_CPF)
    return mulher


async def atualizar(session: AsyncSession, mulher_id: uuid.UUID, dados: MulherAtualizar, ator: Usuario) -> Mulher:
    mulher = await exigir_ativa(session, mulher_id)
    campos = dados.model_dump(exclude_unset=True)
    if not campos:
        return mulher
    if campos.get("cpf"):
        outra = await repository.obter_por_cpf(session, campos["cpf"])
        if outra and outra.id != mulher.id:
            raise Conflito(_MSG_CPF, code="CPF_DUPLICADO")
    antes = serializar_modelo(mulher)
    for chave, valor in campos.items():
        setattr(mulher, chave, valor)
    mulher.nome_busca = _nome_busca(mulher.nome_completo, mulher.nome_social)
    mulher.updated_by = ator.id
    await session.flush()
    await auditoria.registrar(
        session,
        usuario_id=ator.id,
        acao=AcaoAuditoria.UPDATE,
        entidade="mulher",
        entidade_id=mulher.id,
        mulher_id=mulher.id,
        antes=antes,
        depois=serializar_modelo(mulher),
    )
    await confirmar(session, code="CPF_DUPLICADO", message=_MSG_CPF)
    return mulher


async def excluir(session: AsyncSession, mulher_id: uuid.UUID, motivo: str, ator: Usuario) -> None:
    mulher = await obter_ou_404(session, mulher_id)
    antes = serializar_modelo(mulher)
    mulher.deleted_at = utcnow()
    mulher.deleted_by = ator.id
    mulher.motivo_exclusao = motivo
    await session.flush()
    await auditoria.registrar(
        session,
        usuario_id=ator.id,
        acao=AcaoAuditoria.DELETE,
        entidade="mulher",
        entidade_id=mulher.id,
        mulher_id=mulher.id,
        antes=antes,
        depois=serializar_modelo(mulher),
    )
    await confirmar(session)


async def restaurar(session: AsyncSession, mulher_id: uuid.UUID, ator: Usuario) -> Mulher:
    mulher = await obter_ou_404(session, mulher_id, incluir_excluida=True)
    if mulher.deleted_at is None:
        raise Conflito("O cadastro não está excluído.", code="MULHER_NAO_EXCLUIDA")
    antes = serializar_modelo(mulher)
    mulher.deleted_at = None
    mulher.deleted_by = None
    mulher.motivo_exclusao = None
    await session.flush()
    await auditoria.registrar(
        session,
        usuario_id=ator.id,
        acao=AcaoAuditoria.RESTORE,
        entidade="mulher",
        entidade_id=mulher.id,
        mulher_id=mulher.id,
        antes=antes,
        depois=serializar_modelo(mulher),
    )
    await confirmar(session)
    return mulher
