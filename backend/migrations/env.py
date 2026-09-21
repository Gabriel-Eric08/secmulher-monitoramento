import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

import app.models  # noqa: F401  (registra todos os models)
from app.core.config import get_settings
from app.core.database import Base, criar_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata
URL = get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=URL,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,  # SQLite não faz ALTER completo; no Postgres é inofensivo
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = criar_engine(URL)
    async with engine.connect() as connection:
        await connection.run_sync(_do_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
