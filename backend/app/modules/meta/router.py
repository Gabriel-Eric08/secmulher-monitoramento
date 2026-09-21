from enum import Enum

from fastapi import APIRouter
from pydantic import Field

from app.core.dependencies import UsuarioLogado
from app.modules.servicos_mulheres.state_machine import EXIGEM_MOTIVO, TRANSICOES
from app.shared.enums import (
    ROTULOS,
    TIPOS_EVENTO_SISTEMA,
    AcaoAuditoria,
    PerfilUsuario,
    StatusServicoMulher,
    TipoDocumento,
    TipoEvento,
)
from app.shared.schemas import Esquema, erros

router = APIRouter(prefix="/meta", tags=["Meta"])


class OpcaoEnum(Esquema):
    valor: str = Field(..., examples=["EM_ATENDIMENTO"])
    rotulo: str = Field(..., examples=["Em atendimento"])


class MetaEnums(Esquema):
    perfis_usuario: list[OpcaoEnum]
    status_servico_mulher: list[OpcaoEnum]
    tipos_evento: list[OpcaoEnum]
    tipos_evento_manuais: list[OpcaoEnum] = Field(
        ..., description="Tipos que o usuário pode criar em `POST /eventos` (exclui os gerados pelo sistema)."
    )
    tipos_documento: list[OpcaoEnum]
    acoes_auditoria: list[OpcaoEnum]
    transicoes_status: dict[StatusServicoMulher, list[StatusServicoMulher]] = Field(
        ..., description="Máquina de estados do vínculo: status atual → próximos status permitidos."
    )
    status_exigem_motivo: list[StatusServicoMulher]


def _opcoes(enum: type[Enum], excluir: frozenset[Enum] = frozenset()) -> list[OpcaoEnum]:
    rotulos = ROTULOS[enum]
    return [OpcaoEnum(valor=m.value, rotulo=rotulos[m.value]) for m in enum if m not in excluir]


@router.get(
    "/enums",
    response_model=MetaEnums,
    operation_id="meta_enums",
    summary="Enums, rótulos e transições",
    description="Todos os enums com rótulos pt-BR e a tabela de transições de status. O front usa isto para montar "
    "selects e botões **sem duplicar constantes**.\n\n**Permissão:** qualquer usuário autenticado.",
    responses=erros(401),
)
async def enums(_: UsuarioLogado) -> MetaEnums:
    return MetaEnums(
        perfis_usuario=_opcoes(PerfilUsuario),
        status_servico_mulher=_opcoes(StatusServicoMulher),
        tipos_evento=_opcoes(TipoEvento),
        tipos_evento_manuais=_opcoes(TipoEvento, TIPOS_EVENTO_SISTEMA),
        tipos_documento=_opcoes(TipoDocumento),
        acoes_auditoria=_opcoes(AcaoAuditoria),
        transicoes_status={origem: list(destinos) for origem, destinos in TRANSICOES.items()},
        status_exigem_motivo=sorted(EXIGEM_MOTIVO, key=lambda s: s.value),
    )
