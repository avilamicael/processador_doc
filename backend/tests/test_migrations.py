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
from sqlalchemy import create_engine, inspect, text

from alembic import command

# Raiz do projeto backend (onde vivem alembic.ini e o pacote app).
BACKEND_ROOT = Path(__file__).resolve().parents[1]

ESPERADAS = {
    "documents",
    "pages",
    "audit_log",
    "usage",
    # Fase 2 (migração 0002) — fila, gate de dedup e pastas monitoradas.
    "watched_folders",
    "ingested_originals",
    "jobs",
    # Fase 3 (migração 0003) — resultado da extração genérica por bloco.
    "extractions",
    # Fase 4 (migração 0004) — templates, campos, classificação e campos preenchidos.
    "templates",
    "template_fields",
    "classification_results",
    "filled_fields",
}


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


def test_documents_ganha_origin_original_id_apos_upgrade(db_url: str) -> None:
    """Fase 2: a coluna de vínculo bloco→original (D-09) chega via migração 0002."""
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    try:
        colunas = {col["name"] for col in inspect(engine).get_columns("documents")}
    finally:
        engine.dispose()

    assert "origin_original_id" in colunas


def test_jobs_tem_indice_unico_hash_step(db_url: str) -> None:
    """PROC-03: o índice/constraint único `uq_jobs_hash_step` existe após upgrade."""
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    try:
        insp = inspect(engine)
        nomes_uc = {uc["name"] for uc in insp.get_unique_constraints("jobs")}
        nomes_idx = {ix["name"] for ix in insp.get_indexes("jobs")}
    finally:
        engine.dispose()

    assert "uq_jobs_hash_step" in (nomes_uc | nomes_idx)


def test_0003_cria_extractions_com_unique_em_document_id(db_url: str) -> None:
    """Fase 3 (0003): a tabela `extractions` existe após upgrade e seu índice em
    `document_id` é UNIQUE (1 extração por bloco = idempotência)."""
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    try:
        insp = inspect(engine)
        tabelas = set(insp.get_table_names())
        indices = {ix["name"]: ix for ix in insp.get_indexes("extractions")}
    finally:
        engine.dispose()

    assert "extractions" in tabelas
    idx = indices.get("ix_extractions_document_id")
    assert idx is not None, "índice de document_id ausente"
    # SQLite via inspector retorna unique como 1/0 (int), não bool — checar truthy.
    assert idx["unique"], "índice de document_id deve ser UNIQUE"


def test_0004_cria_quatro_tabelas_da_fase_4(db_url: str) -> None:
    """Fase 4 (0004): as 4 tabelas existem após upgrade e o índice de
    `classification_results.document_id` é UNIQUE (rede contra double-charge,
    Pitfall 2)."""
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    try:
        insp = inspect(engine)
        tabelas = set(insp.get_table_names())
        indices_cls = {ix["name"]: ix for ix in insp.get_indexes("classification_results")}
    finally:
        engine.dispose()

    fase4 = {"templates", "template_fields", "classification_results", "filled_fields"}
    assert fase4.issubset(tabelas), f"faltam tabelas da Fase 4: {fase4 - tabelas}"
    idx = indices_cls.get("ix_classification_results_document_id")
    assert idx is not None, "índice de classification_results.document_id ausente"
    # SQLite via inspector retorna unique como 1/0 (int), não bool — checar truthy.
    assert idx["unique"], "índice de classification_results.document_id deve ser UNIQUE"


def test_downgrade_um_passo_remove_so_as_colunas_da_fase_5(db_url: str) -> None:
    """downgrade -1 (de head=0005) reverte SOMENTE a 0005: dropa as 2 colunas da
    Fase 5 (confidence_score, manually_corrected) e preserva TODAS as tabelas das
    Fases 1–4 (a 0005 só adiciona colunas, não cria/dropa tabelas)."""
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "-1")

    engine = create_engine(db_url)
    try:
        insp = inspect(engine)
        tabelas = set(insp.get_table_names())
        cols_cls = {c["name"] for c in insp.get_columns("classification_results")}
        cols_ff = {c["name"] for c in insp.get_columns("filled_fields")}
    finally:
        engine.dispose()

    # As 2 colunas da Fase 5 saíram no downgrade -1.
    assert "confidence_score" not in cols_cls, "confidence_score não removida no downgrade -1"
    assert "manually_corrected" not in cols_ff, "manually_corrected não removida no downgrade -1"
    # Tabelas das Fases 1–4 (inclusive Fase 4) permanecem — a 0005 não as toca.
    fase1234 = {
        "documents", "pages", "audit_log", "usage",
        "watched_folders", "ingested_originals", "jobs",
        "extractions",
        "templates", "template_fields", "classification_results", "filled_fields",
    }
    assert fase1234.issubset(tabelas), "schema das Fases 1–4 não preservado no downgrade -1"


def test_downgrade_dois_passos_remove_so_a_fase_4(db_url: str) -> None:
    """downgrade -2 (de head=0005) reverte 0005 + 0004: remove as 4 tabelas da
    Fase 4, preservando intactos os schemas das Fases 1, 2 e 3."""
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "-2")

    engine = create_engine(db_url)
    try:
        tabelas = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    fase4 = {"templates", "template_fields", "classification_results", "filled_fields"}
    fase123 = {
        "documents", "pages", "audit_log", "usage",
        "watched_folders", "ingested_originals", "jobs",
        "extractions",
    }
    sobrando = fase4 & tabelas
    assert not sobrando, f"tabelas da Fase 4 não removidas no downgrade -2: {sobrando}"
    assert fase123.issubset(tabelas), "schema das Fases 1/2/3 não preservado no downgrade -2"


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


def test_updated_at_avanca_em_update_via_sql_cru(db_url: str) -> None:
    """WR-05: `updated_at` deve avançar mesmo num UPDATE via SQL cru (sem ORM),
    graças ao trigger criado pela migração."""
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO documents (content_hash, original_filename, state, updated_at) "
                    "VALUES (:h, :f, 'recebido', '2000-01-01 00:00:00')"
                ),
                {"h": "f" * 64, "f": "raw.pdf"},
            )
        with engine.begin() as conn:
            # UPDATE que NÃO toca updated_at: o trigger deve carimbá-lo mesmo assim.
            conn.execute(
                text("UPDATE documents SET state = 'processando' WHERE content_hash = :h"),
                {"h": "f" * 64},
            )
        with engine.connect() as conn:
            updated_at = conn.execute(
                text("SELECT updated_at FROM documents WHERE content_hash = :h"),
                {"h": "f" * 64},
            ).scalar()
    finally:
        engine.dispose()

    # O valor inicial era o ano 2000; após o UPDATE o trigger o avançou.
    assert updated_at is not None
    assert not str(updated_at).startswith("2000-01-01")


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
