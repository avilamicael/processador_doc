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
    # Fase 6 (migração 0008) — modelo final de automações (condições → ações).
    "automations",
    "automation_conditions",
    "automation_actions",
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


def test_0008_cria_automations_e_remove_pipeline(db_url: str) -> None:
    """Fase 6 MODELO FINAL (0008): após upgrade head, as tabelas do modelo final
    (`automations`/`automation_conditions`/`automation_actions`) EXISTEM e as tabelas
    de pipeline da 0007 (`automation_pipelines`/`pipeline_steps`/`step_filters`) NÃO
    existem mais. Os índices de FK CASCADE (condições/ações por automation_id), a
    ordem das ações (`automation_actions.position`) e a ordem entre automações
    (`automations.position`, D-25) estão presentes."""
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    try:
        insp = inspect(engine)
        tabelas = set(insp.get_table_names())
        idx_auto = {ix["name"] for ix in insp.get_indexes("automations")}
        idx_cond = {ix["name"] for ix in insp.get_indexes("automation_conditions")}
        idx_act = {ix["name"] for ix in insp.get_indexes("automation_actions")}
    finally:
        engine.dispose()

    assert {"automations", "automation_conditions", "automation_actions"}.issubset(
        tabelas
    )
    # As tabelas de pipeline da 0007 foram dropadas pela 0008.
    assert not (
        {"automation_pipelines", "pipeline_steps", "step_filters"} & tabelas
    ), "tabelas de pipeline da 0007 não removidas pela 0008"
    assert "ix_automations_position" in idx_auto
    assert "ix_automation_conditions_automation_id" in idx_cond
    assert "ix_automation_actions_automation_id" in idx_act
    assert "ix_automation_actions_position" in idx_act


def test_0008_preserva_write_ahead_de_audit_log(db_url: str) -> None:
    """A 0008 NÃO toca `audit_log` — as 5 colunas write-ahead (status/source_path/
    dest_path/run_id/content_hash, base de AUT-04/05) permanecem após upgrade head."""
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    try:
        cols_audit = {c["name"] for c in inspect(engine).get_columns("audit_log")}
    finally:
        engine.dispose()

    assert {"status", "source_path", "dest_path", "run_id", "content_hash"} <= cols_audit, (
        f"colunas write-ahead de audit_log perdidas após 0008: {cols_audit}"
    )
    assert "status" in cols_audit


def test_0008_preserva_trigger_documents_updated_at(db_url: str) -> None:
    """A 0008 NÃO toca `documents` (sem batch recreate), logo o trigger
    `trg_documents_updated_at` (criado na 0002) permanece após upgrade head."""
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            trigger = conn.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'trigger' AND name = 'trg_documents_updated_at'"
                )
            ).scalar()
    finally:
        engine.dispose()

    assert trigger == "trg_documents_updated_at", "trigger de documents perdido após 0008"


def test_downgrade_um_passo_reverte_so_o_modelo_final(db_url: str) -> None:
    """downgrade -1 (de head=0008) reverte SOMENTE a 0008: dropa as tabelas do modelo
    final e RECRIA as tabelas de pipeline da 0007 (reversibilidade do histórico),
    preservando o write-ahead de `audit_log` e o schema das Fases 1–5."""
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "-1")

    engine = create_engine(db_url)
    try:
        insp = inspect(engine)
        tabelas = set(insp.get_table_names())
        cols_audit = {c["name"] for c in insp.get_columns("audit_log")}
        cols_cls = {c["name"] for c in insp.get_columns("classification_results")}
        cols_ff = {c["name"] for c in insp.get_columns("filled_fields")}
    finally:
        engine.dispose()

    # As tabelas do modelo final saíram; as tabelas de pipeline da 0007 voltaram.
    assert not (
        {"automations", "automation_conditions", "automation_actions"} & tabelas
    ), "tabelas do modelo final não removidas no downgrade -1"
    assert {"automation_pipelines", "pipeline_steps", "step_filters"}.issubset(
        tabelas
    ), "tabelas de pipeline da 0007 não recriadas no downgrade -1"
    # O write-ahead de audit_log (0006) permanece — a 0008 não o toca.
    assert {"status", "source_path", "dest_path", "run_id", "content_hash"} <= cols_audit
    # As colunas da Fase 5 permanecem.
    assert "confidence_score" in cols_cls
    assert "manually_corrected" in cols_ff


def test_downgrade_remove_toda_a_automacao(db_url: str) -> None:
    """downgrade -3 (de head=0008) reverte 0008 + 0007 + 0006: remove as tabelas do
    modelo final, de pipeline E de regra E as 5 colunas write-ahead de `audit_log`,
    preservando intactos os schemas das Fases 1–5 (confidence_score/manually_corrected)."""
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "-3")

    engine = create_engine(db_url)
    try:
        insp = inspect(engine)
        tabelas = set(insp.get_table_names())
        cols_audit = {c["name"] for c in insp.get_columns("audit_log")}
        cols_cls = {c["name"] for c in insp.get_columns("classification_results")}
    finally:
        engine.dispose()

    fase6 = {
        "automations", "automation_conditions", "automation_actions",
        "automation_pipelines", "pipeline_steps", "step_filters",
        "automation_rules", "rule_conditions",
    }
    sobrando = fase6 & tabelas
    assert not sobrando, f"tabelas da Fase 6 não removidas no downgrade -3: {sobrando}"
    assert not ({"status", "source_path", "dest_path", "run_id", "content_hash"} & cols_audit), (
        "colunas write-ahead da Fase 6 não removidas no downgrade -3"
    )
    # As colunas da Fase 5 permanecem.
    assert "confidence_score" in cols_cls
    # Tabelas das Fases 1–4 permanecem.
    fase1234 = {
        "documents", "pages", "audit_log", "usage",
        "watched_folders", "ingested_originals", "jobs",
        "extractions",
        "templates", "template_fields", "classification_results", "filled_fields",
    }
    assert fase1234.issubset(tabelas), "schema das Fases 1–4 não preservado no downgrade -3"


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
