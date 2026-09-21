import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import confirmar
from app.modules.auditoria import service as auditoria
from app.modules.eventos import service as eventos
from app.modules.mulheres import service as mulheres
from app.modules.servicos import service as servicos
from app.modules.servicos_mulheres import state_machine
from app.modules.servicos_mulheres.model import ServicoMulher
from app.modules.servicos_mulheres.schema import (
    StatusOpcao,
    TransicaoCriar,
    TransicoesPermitidas,
    VinculoAtualizar,
    VinculoCriar,
    VinculoFiltros,
)
from app.modules.usuarios.model import Usuario
from app.shared.enums import ROTULOS, AcaoAuditoria, StatusServicoMulher, TipoEvento
from app.shared.exceptions import Conflito, NaoEncontrado, ValidacaoFalhou
from app.shared.pagination import PaginacaoOrdenavel, ordenar, paginar
from app.shared.utils import serializar_modelo, utcnow

_MSG_ABERTO = "Já existe um vínculo em aberto desta mulher com este serviço."
_ORDENAVEIS = {
    "data_inicio": ServicoMulher.data_inicio,
    "status": ServicoMulher.status,
    "created_at": ServicoMulher.created_at,
    "updated_at": ServicoMulher.updated_at,
}


async def _carregar(session: AsyncSession, vinculo_id: uuid.UUID) -> ServicoMulher | None:
    return await session.scalar(
        select(ServicoMulher).where(ServicoMulher.id == vinculo_id).execution_options(populate_existing=True)
    )


async def obter(session: AsyncSession, vinculo_id: uuid.UUID) -> ServicoMulher:
    vinculo = await _carregar(session, vinculo_id)
    if vinculo is None:
        raise NaoEncontrado("Vínculo não encontrado.", code="SERVICO_MULHER_NAO_ENCONTRADO")
    return vinculo


async def listar(
    session: AsyncSession, filtros: VinculoFiltros, pag: PaginacaoOrdenavel
) -> tuple[list[ServicoMulher], int]:
    stmt = select(ServicoMulher)
    if filtros.mulher_id:
        stmt = stmt.where(ServicoMulher.mulher_id == filtros.mulher_id)
    if filtros.servico_id:
        stmt = stmt.where(ServicoMulher.servico_id == filtros.servico_id)
    if filtros.status:
        stmt = stmt.where(ServicoMulher.status == filtros.status)
    if filtros.responsavel_id:
        stmt = stmt.where(ServicoMulher.responsavel_id == filtros.responsavel_id)
    if filtros.data_inicio_de:
        stmt = stmt.where(ServicoMulher.data_inicio >= filtros.data_inicio_de)
    if filtros.data_inicio_ate:
        stmt = stmt.where(ServicoMulher.data_inicio <= filtros.data_inicio_ate)
    stmt = ordenar(stmt, pag.sort, _ORDENAVEIS, [ServicoMulher.created_at.desc()], ServicoMulher.id)
    return await paginar(session, stmt, pag)


async def listar_da_mulher(
    session: AsyncSession, mulher_id: uuid.UUID, pag: PaginacaoOrdenavel
) -> tuple[list[ServicoMulher], int]:
    await mulheres.obter_ou_404(session, mulher_id)
    return await listar(session, VinculoFiltros(mulher_id=mulher_id), pag)


async def _validar_responsavel(session: AsyncSession, responsavel_id: uuid.UUID | None) -> None:
    if responsavel_id is None:
        return
    responsavel = await session.get(Usuario, responsavel_id)
    if responsavel is None or not responsavel.ativo:
        raise ValidacaoFalhou(
            "Responsável inexistente ou inativo.",
            code="RESPONSAVEL_INVALIDO",
            details=[{"field": "responsavel_id", "issue": "usuário inexistente ou inativo"}],
        )


async def criar(session: AsyncSession, mulher_id: uuid.UUID, dados: VinculoCriar, ator: Usuario) -> ServicoMulher:
    await mulheres.exigir_ativa(session, mulher_id)
    servico = await servicos.obter(session, dados.servico_id)
    if not servico.ativo:
        raise Conflito("Este serviço está inativo e não aceita novos vínculos.", code="SERVICO_INATIVO")
    await _validar_responsavel(session, dados.responsavel_id)

    existente = await session.scalar(
        select(ServicoMulher.id).where(
            ServicoMulher.mulher_id == mulher_id,
            ServicoMulher.servico_id == servico.id,
            ServicoMulher.status.notin_(state_machine.STATUS_FINAIS),
        )
    )
    if existente:
        raise Conflito(_MSG_ABERTO, code="VINCULO_ABERTO_EXISTENTE")

    vinculo = ServicoMulher(
        mulher_id=mulher_id,
        servico_id=servico.id,
        status=StatusServicoMulher.SOLICITADO,
        data_inicio=dados.data_inicio or utcnow().date(),
        responsavel_id=dados.responsavel_id,
        observacoes=dados.observacoes,
    )
    session.add(vinculo)
    await session.flush()
    eventos.registrar_interno(
        session,
        mulher_id=mulher_id,
        servico_mulher_id=vinculo.id,
        tipo=TipoEvento.MUDANCA_STATUS,
        titulo=f"Serviço vinculado: {servico.nome}",
        descricao="Vínculo criado com status inicial SOLICITADO.",
        usuario_id=ator.id,
        metadados={"status_anterior": None, "status_novo": StatusServicoMulher.SOLICITADO.value},
    )
    await auditoria.registrar(
        session,
        usuario_id=ator.id,
        acao=AcaoAuditoria.CREATE,
        entidade="servico_mulher",
        entidade_id=vinculo.id,
        mulher_id=mulher_id,
        depois=serializar_modelo(vinculo),
    )
    await confirmar(session, code="VINCULO_ABERTO_EXISTENTE", message=_MSG_ABERTO)
    return await obter(session, vinculo.id)


async def atualizar(
    session: AsyncSession, vinculo_id: uuid.UUID, dados: VinculoAtualizar, ator: Usuario
) -> ServicoMulher:
    vinculo = await obter(session, vinculo_id)
    await mulheres.exigir_ativa(session, vinculo.mulher_id)
    campos = dados.model_dump(exclude_unset=True)
    if not campos:
        return vinculo
    if campos.get("responsavel_id"):
        await _validar_responsavel(session, campos["responsavel_id"])
    antes = serializar_modelo(vinculo)
    for chave, valor in campos.items():
        setattr(vinculo, chave, valor)
    await session.flush()
    await auditoria.registrar(
        session,
        usuario_id=ator.id,
        acao=AcaoAuditoria.UPDATE,
        entidade="servico_mulher",
        entidade_id=vinculo.id,
        mulher_id=vinculo.mulher_id,
        antes=antes,
        depois=serializar_modelo(vinculo),
    )
    await confirmar(session)
    return await obter(session, vinculo.id)


def transicoes_permitidas(vinculo: ServicoMulher) -> TransicoesPermitidas:
    rotulos = ROTULOS[StatusServicoMulher]
    return TransicoesPermitidas(
        status_atual=vinculo.status,
        permitidas=[StatusOpcao(valor=s, rotulo=rotulos[s.value]) for s in state_machine.permitidas(vinculo.status)],
        exigem_motivo=sorted(state_machine.EXIGEM_MOTIVO, key=lambda s: s.value),
    )


async def transitar(
    session: AsyncSession, vinculo_id: uuid.UUID, dados: TransicaoCriar, ator: Usuario
) -> ServicoMulher:
    """Muda o status, cria o evento `MUDANCA_STATUS` e a auditoria — tudo na mesma transação."""
    vinculo = await obter(session, vinculo_id)
    await mulheres.exigir_ativa(session, vinculo.mulher_id)

    origem, destino = vinculo.status, dados.status_novo
    if destino not in state_machine.permitidas(origem):
        raise Conflito(
            f"Não é possível ir de {origem.value} para {destino.value}.",
            code="SERVICO_MULHER_TRANSICAO_INVALIDA",
            details=[{"field": "status_novo", "issue": "transição não permitida"}],
        )
    if destino in state_machine.EXIGEM_MOTIVO and not dados.motivo:
        raise ValidacaoFalhou(
            f"Informe o motivo para mudar para {destino.value}.",
            code="MOTIVO_OBRIGATORIO",
            details=[{"field": "motivo", "issue": "obrigatório para este status"}],
        )

    antes = serializar_modelo(vinculo)
    vinculo.status = destino
    vinculo.data_encerramento = utcnow().date() if state_machine.eh_final(destino) else None
    await session.flush()
    eventos.registrar_interno(
        session,
        mulher_id=vinculo.mulher_id,
        servico_mulher_id=vinculo.id,
        tipo=TipoEvento.MUDANCA_STATUS,
        titulo=f"Status alterado: {origem.value} → {destino.value}",
        descricao=dados.motivo,
        ocorrido_em=dados.ocorrido_em,
        usuario_id=ator.id,
        metadados={"status_anterior": origem.value, "status_novo": destino.value},
    )
    await auditoria.registrar(
        session,
        usuario_id=ator.id,
        acao=AcaoAuditoria.STATUS_CHANGE,
        entidade="servico_mulher",
        entidade_id=vinculo.id,
        mulher_id=vinculo.mulher_id,
        antes=antes,
        depois={**serializar_modelo(vinculo), "motivo": dados.motivo},
    )
    await confirmar(session)
    return await obter(session, vinculo.id)
