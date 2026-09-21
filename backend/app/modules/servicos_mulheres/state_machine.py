"""Máquina de estados do vínculo mulher↔serviço — **única** fonte das transições válidas."""

from app.shared.enums import StatusServicoMulher as S

TRANSICOES: dict[S, tuple[S, ...]] = {
    S.SOLICITADO: (S.EM_ANALISE, S.CANCELADO),
    S.EM_ANALISE: (S.EM_ATENDIMENTO, S.CANCELADO),
    S.EM_ATENDIMENTO: (S.SUSPENSO, S.CONCLUIDO, S.CANCELADO),
    S.SUSPENSO: (S.EM_ATENDIMENTO, S.CANCELADO),
    S.CONCLUIDO: (),
    S.CANCELADO: (),
}

STATUS_FINAIS = frozenset({S.CONCLUIDO, S.CANCELADO})
# Status de destino que exigem justificativa.
EXIGEM_MOTIVO = frozenset({S.SUSPENSO, S.CANCELADO})


def permitidas(origem: S) -> tuple[S, ...]:
    return TRANSICOES[origem]


def eh_final(status: S) -> bool:
    return status in STATUS_FINAIS
