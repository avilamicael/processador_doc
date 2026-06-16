"""Fixtures de teste compartilhadas."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine

# Importar o pacote de modelos registra TODAS as tabelas em Base.metadata —
# necessário para a fixture `schema_engine` (create_all) ver todos os modelos.
import app.models  # noqa: F401
from app.storage.db import Base, create_db_engine


@pytest.fixture
def sqlite_url(tmp_path: Path) -> str:
    """URL SQLite apontando para um arquivo temporário isolado por teste."""
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def engine(sqlite_url: str) -> Iterator[Engine]:
    """Engine SQLite (WAL) sobre arquivo temporário, descartado ao final."""
    eng = create_db_engine(sqlite_url)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def schema_engine(engine: Engine) -> Iterator[Engine]:
    """Engine com o schema criado via `Base.metadata.create_all` — SOMENTE em
    teste (D-10 proíbe `create_all` no código de aplicação, não nas fixtures).

    Disponibiliza a fixture de forma compartilhada para os testes da Fase 2
    (queue/dedup/ingest_stage) sem cada arquivo redefini-la localmente.
    """
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
