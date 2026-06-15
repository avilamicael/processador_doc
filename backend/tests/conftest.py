"""Fixtures de teste compartilhadas."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine

from app.storage.db import create_db_engine


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
