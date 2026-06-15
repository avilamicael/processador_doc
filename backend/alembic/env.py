"""Ambiente Alembic.

Wireado à fundação da aplicação:
- `target_metadata = Base.metadata` com TODOS os modelos importados (via
  `import app.models`) — base do autogenerate e da migração versionada.
- A URL do banco vem de `get_settings().effective_database_url` (que respeita
  `DATABASE_URL` do ambiente; D-02 permite apontar para outro disco/banco). Não
  hardcodada no `alembic.ini`.
- `render_as_batch=True` para suportar ALTER TABLE no SQLite em migrações futuras
  (base da atualização segura da Fase 8 — T-01-07).

O schema do banco evolui SOMENTE por aqui (D-10); nenhum `create_all` em produção.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

# Importar o pacote de modelos registra todas as tabelas em Base.metadata.
import app.models  # noqa: F401
from alembic import context
from app.config import get_settings
from app.storage.db import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata alvo do autogenerate e das migrações.
target_metadata = Base.metadata


def _database_url() -> str:
    """URL efetiva do banco, lida da configuração da aplicação.

    Precedência: `sqlalchemy.url` explícito no `alembic.ini` (quando preenchido)
    > `Settings.effective_database_url` (que honra `DATABASE_URL` do ambiente).
    """
    ini_url = config.get_main_option("sqlalchemy.url")
    if ini_url:
        return ini_url
    return get_settings().effective_database_url


def run_migrations_offline() -> None:
    """Executa migrações em modo 'offline' (apenas URL, sem DBAPI)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Executa migrações em modo 'online' (com Engine/conexão)."""
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
