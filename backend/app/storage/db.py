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
from weakref import WeakKeyDictionary

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
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
    # Detecta o dialeto UMA única vez e a partir do backend name canônico, para
    # que `check_same_thread` e os PRAGMAs (WAL/foreign_keys/busy_timeout) nunca
    # divirjam — caso contrário um URL incomum poderia abrir uma conexão sem WAL
    # silenciosamente (WR-02).
    is_sqlite = make_url(url).get_backend_name() == "sqlite"

    connect_args: dict = {}
    if is_sqlite:
        # FastAPI/worker podem tocar a mesma conexão em threads distintas.
        connect_args["check_same_thread"] = False

    engine = create_engine(url, echo=echo, future=True, connect_args=connect_args)

    if is_sqlite:
        _register_sqlite_pragmas(engine)

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Cria uma fábrica de sessões ligada ao engine."""
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


# Cache de fábricas por engine: `sessionmaker` é caro e deve ser criado uma única
# vez por engine e reusado (WR-03). Chaveado pela identidade do engine; usa
# WeakKeyDictionary para não impedir a coleta do engine quando descartado.
_SESSION_FACTORIES: "WeakKeyDictionary[Engine, sessionmaker[Session]]" = WeakKeyDictionary()


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Retorna a fábrica de sessões do engine, criando-a (e cacheando) uma vez."""
    factory = _SESSION_FACTORIES.get(engine)
    if factory is None:
        factory = make_session_factory(engine)
        _SESSION_FACTORIES[engine] = factory
    return factory


@contextmanager
def get_session(engine: Engine) -> Iterator[Session]:
    """Fornece uma sessão SQLAlchemy 2.0 e a fecha ao final.

    Usável como dependência ou context manager. Reusa a fábrica de sessões
    cacheada por engine (WR-03). Só faz `commit` quando há trabalho pendente
    (novos/sujos/removidos) — blocos somente-leitura (ex.: `SELECT 1` do health)
    não emitem COMMIT, evitando contenção desnecessária com o único writer sob
    SQLite WAL (WR-04). Faz rollback e re-levanta em caso de exceção.
    """
    factory = get_session_factory(engine)
    session = factory()
    try:
        yield session
        if session.in_transaction() and (session.new or session.dirty or session.deleted):
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
