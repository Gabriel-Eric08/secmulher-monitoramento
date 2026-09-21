from enum import Enum


class PerfilUsuario(str, Enum):
    ADMIN = "ADMIN"
    GESTOR = "GESTOR"
    ATENDENTE = "ATENDENTE"
    AUDITOR = "AUDITOR"


class StatusServicoMulher(str, Enum):
    SOLICITADO = "SOLICITADO"
    EM_ANALISE = "EM_ANALISE"
    EM_ATENDIMENTO = "EM_ATENDIMENTO"
    SUSPENSO = "SUSPENSO"
    CONCLUIDO = "CONCLUIDO"
    CANCELADO = "CANCELADO"


class TipoEvento(str, Enum):
    ATENDIMENTO = "ATENDIMENTO"
    ENCAMINHAMENTO = "ENCAMINHAMENTO"
    CONTATO = "CONTATO"
    VISITA = "VISITA"
    MUDANCA_STATUS = "MUDANCA_STATUS"
    DOCUMENTO_ANEXADO = "DOCUMENTO_ANEXADO"
    OBSERVACAO = "OBSERVACAO"
    RETIFICACAO = "RETIFICACAO"
    OUTRO = "OUTRO"


class TipoDocumento(str, Enum):
    IDENTIFICACAO = "IDENTIFICACAO"
    COMPROVANTE = "COMPROVANTE"
    LAUDO = "LAUDO"
    ENCAMINHAMENTO = "ENCAMINHAMENTO"
    TERMO = "TERMO"
    OUTRO = "OUTRO"


class AcaoAuditoria(str, Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    RESTORE = "RESTORE"
    STATUS_CHANGE = "STATUS_CHANGE"
    UPLOAD = "UPLOAD"
    DOWNLOAD = "DOWNLOAD"
    READ_SENSITIVE = "READ_SENSITIVE"
    LOGIN = "LOGIN"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGOUT = "LOGOUT"


# Eventos gerados exclusivamente pelo sistema (não podem ser criados via POST /eventos).
TIPOS_EVENTO_SISTEMA = frozenset(
    {TipoEvento.MUDANCA_STATUS, TipoEvento.DOCUMENTO_ANEXADO, TipoEvento.RETIFICACAO}
)

ROTULOS: dict[type[Enum], dict[str, str]] = {
    PerfilUsuario: {
        "ADMIN": "Administrador",
        "GESTOR": "Gestor",
        "ATENDENTE": "Atendente",
        "AUDITOR": "Auditor",
    },
    StatusServicoMulher: {
        "SOLICITADO": "Solicitado",
        "EM_ANALISE": "Em análise",
        "EM_ATENDIMENTO": "Em atendimento",
        "SUSPENSO": "Suspenso",
        "CONCLUIDO": "Concluído",
        "CANCELADO": "Cancelado",
    },
    TipoEvento: {
        "ATENDIMENTO": "Atendimento",
        "ENCAMINHAMENTO": "Encaminhamento",
        "CONTATO": "Contato",
        "VISITA": "Visita",
        "MUDANCA_STATUS": "Mudança de status",
        "DOCUMENTO_ANEXADO": "Documento anexado",
        "OBSERVACAO": "Observação",
        "RETIFICACAO": "Retificação",
        "OUTRO": "Outro",
    },
    TipoDocumento: {
        "IDENTIFICACAO": "Identificação",
        "COMPROVANTE": "Comprovante",
        "LAUDO": "Laudo",
        "ENCAMINHAMENTO": "Encaminhamento",
        "TERMO": "Termo",
        "OUTRO": "Outro",
    },
    AcaoAuditoria: {
        "CREATE": "Criação",
        "UPDATE": "Atualização",
        "DELETE": "Exclusão",
        "RESTORE": "Restauração",
        "STATUS_CHANGE": "Mudança de status",
        "UPLOAD": "Upload de arquivo",
        "DOWNLOAD": "Download de arquivo",
        "READ_SENSITIVE": "Leitura de dado sensível",
        "LOGIN": "Login",
        "LOGIN_FAILED": "Falha de login",
        "LOGOUT": "Logout",
    },
}
