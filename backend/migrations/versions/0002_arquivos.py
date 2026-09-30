"""arquivos no banco (STORAGE_BACKEND=db)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-30 15:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.core.database


revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('arquivos',
    sa.Column('chave', sa.String(length=500), nullable=False),
    sa.Column('conteudo', sa.LargeBinary(), nullable=False),
    sa.Column('tamanho', sa.Integer(), nullable=False),
    sa.Column('created_at', app.core.database.UTCDateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('chave', name=op.f('pk_arquivos'))
    )


def downgrade() -> None:
    op.drop_table('arquivos')
