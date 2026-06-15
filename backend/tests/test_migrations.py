"""Teste de integração das migrações Alembic (schema versionado round-trip).

Prova D-10: o schema nasce do Alembic versionado (NÃO de `create_all`) e faz
round-trip up/down. Aplica a migração programaticamente via API do Alembic
(`alembic.config.Config` + `alembic.command`) contra um SQLite temporário,
sobrescrevendo a URL para o arquivo do teste.

Asserta também que as colunas `state` (D-04) e `last_completed_step` (D-05)
chegam ao schema versionado em `documents`.
"""

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command

# Raiz do projeto backend (onde vivem alembic.ini e o pacote app).
BACKEND_ROOT = Path(__file__).resolve().parents[1]

ESPERADAS = {"documents", "pages", "audit_log", "usage"}


def _make_config(db_url: str) -> Config:
    """Config do Alembic apontando a URL para o banco temporário do teste."""
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    # Precedência em env.py: sqlalchemy.url explícito > Settings. Forçamos o DB do teste.
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'migr.db'}"


def test_upgrade_head_cria_todas_as_tabelas(db_url: str) -> None:
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    try:
        tabelas = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert ESPERADAS.issubset(tabelas), f"faltam tabelas: {ESPERADAS - tabelas}"
    # tabela de controle do Alembic confirma que o schema veio da migração, não de create_all
    assert "alembic_version" in tabelas


def test_documents_tem_state_e_last_completed_step(db_url: str) -> None:
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    try:
        colunas = {col["name"] for col in inspect(engine).get_columns("documents")}
    finally:
        engine.dispose()

    # Estado persistido (D-04) e marcador interno de etapa (D-05) no schema versionado.
    assert "state" in colunas
    assert "last_completed_step" in colunas
    assert "content_hash" in colunas


def test_downgrade_base_remove_as_tabelas(db_url: str) -> None:
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    engine = create_engine(db_url)
    try:
        tabelas = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    # Nenhuma tabela de domínio sobrevive ao downgrade base.
    assert not (ESPERADAS & tabelas), f"tabelas não removidas: {ESPERADAS & tabelas}"


def test_round_trip_up_down_up(db_url: str) -> None:
    """Up → down → up deve ser idempotente (determinismo de upgrade — T-01-06)."""
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    try:
        tabelas = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert ESPERADAS.issubset(tabelas)
