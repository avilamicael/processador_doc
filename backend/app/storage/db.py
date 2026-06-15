"""Camada de banco — fronteira única de acesso ao banco de dados.

Interface pública: `Base`, `create_db_engine`, `get_session`.

A camada é abstraível: o mesmo código serve SQLite (padrão single-tenant) e
Postgres (modo servidor) trocando apenas a connection string. PRAGMAs específicos
de SQLite (WAL, busy_timeout, foreign_keys) só são aplicados quando o dialeto é
SQLite — mantendo a porta aberta para Postgres (STACK.md §1; "não acoplar SQL ao
SQLite" em What NOT to Use).
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# busy_timeout em milissegundos: evita falha imediata sob contenção de escrita
# (T-01-05). Single-writer (worker da Fase 2) torna SQLite suficiente.
SQLITE_BUSY_TIMEOUT_MS = 5000


class Base(DeclarativeBase):
    """Base declarativa SQLAlchemy 2.0 para todos os modelos do domínio."""


def _register_sqlite_pragmas(engine: Engine) -> None:
    """Aplica PRAGMAs de SQLite a cada nova conexão (somente dialeto sqlite)."""

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


def create_db_engine(url: str, *, echo: bool = False) -> Engine:
    """Cria o engine SQLAlchemy para a URL dada.

    Para SQLite, registra os PRAGMAs WAL/busy_timeout/foreign_keys por conexão.
    Para outros dialetos (ex.: Postgres), nenhum PRAGMA SQLite é aplicado.
    """
    connect_args: dict = {}
    if url.startswith("sqlite"):
        # FastAPI/worker podem tocar a mesma conexão em threads distintas.
        connect_args["check_same_thread"] = False

    engine = create_engine(url, echo=echo, future=True, connect_args=connect_args)

    if engine.dialect.name == "sqlite":
        _register_sqlite_pragmas(engine)

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Cria uma fábrica de sessões ligada ao engine."""
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


@contextmanager
def get_session(engine: Engine) -> Iterator[Session]:
    """Fornece uma sessão SQLAlchemy 2.0 e a fecha ao final.

    Usável como dependência ou context manager. Faz commit em caso de sucesso e
    rollback em caso de exceção.
    """
    factory = make_session_factory(engine)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
