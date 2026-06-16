"""Testes dos modelos de domínio (Document/Page/AuditLog/Usage) + DocState.

Prova D-04 (estados enxutos), D-05 (marcador interno de etapa) e que a estrutura
de domínio persiste/relaciona corretamente. O schema do banco para os testes vem
de `Base.metadata.create_all` num SQLite temporário — aceitável APENAS em teste
(D-10 proíbe `create_all` no código de aplicação, não nas fixtures).
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError

from app.models import (
    AuditLog,
    DocState,
    Document,
    IngestedOriginal,
    Job,
    JobStatus,
    Page,
    Usage,
    WatchedFolder,
)
from app.storage.db import Base, get_session


@pytest.fixture
def schema_engine(engine: Engine) -> Iterator[Engine]:
    """Engine com o schema criado via metadata (somente para teste)."""
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)


def test_docstate_tem_exatamente_seis_membros() -> None:
    membros = {member.name for member in DocState}
    assert membros == {
        "RECEBIDO",
        "PROCESSANDO",
        "EM_REVISAO",
        "CONCLUIDO",
        "QUARENTENA",
        "FALHA",
    }


def test_docstate_valores_sao_strings_sem_acento() -> None:
    assert DocState.RECEBIDO.value == "recebido"
    assert DocState.EM_REVISAO.value == "em_revisao"
    assert DocState.CONCLUIDO.value == "concluido"
    # herda de str → comparável diretamente com a string
    assert DocState.RECEBIDO == "recebido"


def test_document_default_state_eh_recebido() -> None:
    doc = Document(content_hash="a" * 64, original_filename="nota.pdf")
    assert doc.state == DocState.RECEBIDO


def test_document_tem_content_hash_e_last_completed_step() -> None:
    doc = Document(content_hash="b" * 64, original_filename="boleto.pdf")
    assert hasattr(doc, "content_hash")
    assert hasattr(doc, "last_completed_step")
    # marcador interno começa vazio (nenhuma etapa concluída)
    assert doc.last_completed_step is None


def test_todos_os_modelos_aparecem_em_metadata() -> None:
    tabelas = set(Base.metadata.tables.keys())
    assert {"documents", "pages", "audit_log", "usage"}.issubset(tabelas)


def test_persistir_e_ler_de_volta_com_relacionamentos(schema_engine: Engine) -> None:
    with get_session(schema_engine) as session:
        doc = Document(content_hash="c" * 64, original_filename="doc.pdf")
        doc.pages.append(Page(page_number=1))
        doc.pages.append(Page(page_number=2))
        doc.usages.append(
            Usage(step="extracao", prompt_tokens=100, completion_tokens=42)
        )
        doc.audit_logs.append(AuditLog(action="ingerido", details="origem=hotfolder"))
        session.add(doc)

    with get_session(schema_engine) as session:
        lido = session.scalar(select(Document).where(Document.content_hash == "c" * 64))
        assert lido is not None
        assert lido.state == DocState.RECEBIDO
        assert lido.original_filename == "doc.pdf"
        assert {p.page_number for p in lido.pages} == {1, 2}
        assert len(lido.usages) == 1
        assert lido.usages[0].step == "extracao"
        assert len(lido.audit_logs) == 1
        assert lido.audit_logs[0].action == "ingerido"
        assert lido.created_at is not None


def test_state_persiste_como_string_de_valor(schema_engine: Engine) -> None:
    with get_session(schema_engine) as session:
        doc = Document(
            content_hash="d" * 64,
            original_filename="x.pdf",
            state=DocState.EM_REVISAO,
            last_completed_step="classificacao",
        )
        session.add(doc)

    with get_session(schema_engine) as session:
        lido = session.scalar(select(Document).where(Document.content_hash == "d" * 64))
        assert lido is not None
        assert lido.state == DocState.EM_REVISAO
        assert lido.last_completed_step == "classificacao"


def test_state_fora_do_dominio_eh_rejeitado_pelo_banco(schema_engine: Engine) -> None:
    """A garantia de estado legal (D-06 / WR-06) é imposta no storage, não só em
    Python: um INSERT via SQL cru com `state` fora do domínio viola a CHECK
    constraint e é rejeitado pelo banco."""
    from sqlalchemy import text

    with pytest.raises(IntegrityError):
        with get_session(schema_engine) as session:
            session.execute(
                text(
                    "INSERT INTO documents (content_hash, original_filename, state) "
                    "VALUES (:h, :f, :s)"
                ),
                {"h": "e" * 64, "f": "x.pdf", "s": "estado_invalido"},
            )
            session.commit()


def test_audit_log_document_id_eh_nullable(schema_engine: Engine) -> None:
    with get_session(schema_engine) as session:
        session.add(AuditLog(action="evento_global", document_id=None))

    with get_session(schema_engine) as session:
        log = session.scalar(select(AuditLog).where(AuditLog.action == "evento_global"))
        assert log is not None
        assert log.document_id is None


# --------------------------------------------------------------------------- #
# Fase 2 — JobStatus + 3 novos modelos + coluna de vínculo (Plan 02-01 Task 2)
# --------------------------------------------------------------------------- #


def test_jobstatus_tem_quatro_membros_string() -> None:
    assert {m.name for m in JobStatus} == {"PENDING", "RUNNING", "DONE", "FAILED"}
    assert JobStatus.PENDING.value == "pending"
    assert JobStatus.RUNNING.value == "running"
    assert JobStatus.DONE.value == "done"
    assert JobStatus.FAILED.value == "failed"
    # herda de str → comparável diretamente com a string
    assert JobStatus.PENDING == "pending"


def test_watched_folder_defaults() -> None:
    wf = WatchedFolder(path="/dados/entrada")
    assert wf.pages_per_block is None  # None = "não separar" (default da UI)
    assert wf.active is True


def test_watched_folder_persiste_com_timestamps(schema_engine: Engine) -> None:
    with get_session(schema_engine) as session:
        session.add(WatchedFolder(path="/dados/entrada", pages_per_block=2))

    with get_session(schema_engine) as session:
        wf = session.scalar(
            select(WatchedFolder).where(WatchedFolder.path == "/dados/entrada")
        )
        assert wf is not None
        assert wf.pages_per_block == 2
        assert wf.active is True
        assert wf.created_at is not None
        assert wf.updated_at is not None


def test_novos_modelos_aparecem_em_metadata() -> None:
    tabelas = set(Base.metadata.tables.keys())
    assert {"watched_folders", "ingested_originals", "jobs"}.issubset(tabelas)


def test_ingested_original_hash_unico_prova_gate_dedup(schema_engine: Engine) -> None:
    """D-09: dois originais com o mesmo `original_hash` são rejeitados (o gate)."""
    with get_session(schema_engine) as session:
        session.add(
            IngestedOriginal(original_hash="a" * 64, original_filename="a.pdf")
        )

    with pytest.raises(IntegrityError):
        with get_session(schema_engine) as session:
            session.add(
                IngestedOriginal(original_hash="a" * 64, original_filename="b.pdf")
            )
            session.commit()


def test_ingested_original_defaults_de_contagem(schema_engine: Engine) -> None:
    with get_session(schema_engine) as session:
        session.add(
            IngestedOriginal(original_hash="c" * 64, original_filename="c.pdf")
        )

    with get_session(schema_engine) as session:
        orig = session.scalar(
            select(IngestedOriginal).where(IngestedOriginal.original_hash == "c" * 64)
        )
        assert orig is not None
        assert orig.block_count == 0
        assert orig.duplicate_hits == 0
        assert orig.source_folder_id is None
        assert orig.created_at is not None


def test_job_par_hash_step_unico_prova_idempotencia(schema_engine: Engine) -> None:
    """PROC-03: o par (original_hash, step) é a chave de idempotência da fila."""
    from datetime import UTC, datetime

    agora = datetime.now(UTC)
    with get_session(schema_engine) as session:
        session.add(
            Job(
                original_hash="d" * 64,
                step="ingest",
                payload="{}",
                next_run_at=agora,
            )
        )

    with pytest.raises(IntegrityError):
        with get_session(schema_engine) as session:
            session.add(
                Job(
                    original_hash="d" * 64,
                    step="ingest",
                    payload="{}",
                    next_run_at=agora,
                )
            )
            session.commit()


def test_job_defaults(schema_engine: Engine) -> None:
    from datetime import UTC, datetime

    with get_session(schema_engine) as session:
        session.add(
            Job(
                original_hash="e" * 64,
                payload="{}",
                next_run_at=datetime.now(UTC),
            )
        )

    with get_session(schema_engine) as session:
        job = session.scalar(select(Job).where(Job.original_hash == "e" * 64))
        assert job is not None
        assert job.status == JobStatus.PENDING
        assert job.step == "ingest"
        assert job.attempts == 0
        assert job.max_attempts == 5
        assert job.last_error is None
        assert job.created_at is not None


def test_document_aceita_origin_original_id(schema_engine: Engine) -> None:
    """Vínculo bloco→original (RESEARCH Open Question 1): FK nullable."""
    with get_session(schema_engine) as session:
        orig = IngestedOriginal(original_hash="f" * 64, original_filename="f.pdf")
        session.add(orig)
        session.flush()
        session.add(
            Document(
                content_hash="1" * 64,
                original_filename="bloco.pdf",
                origin_original_id=orig.id,
            )
        )

    with get_session(schema_engine) as session:
        doc = session.scalar(
            select(Document).where(Document.content_hash == "1" * 64)
        )
        assert doc is not None
        assert doc.origin_original_id is not None


def test_document_origin_original_id_eh_nullable(schema_engine: Engine) -> None:
    with get_session(schema_engine) as session:
        session.add(
            Document(content_hash="2" * 64, original_filename="solto.pdf")
        )

    with get_session(schema_engine) as session:
        doc = session.scalar(
            select(Document).where(Document.content_hash == "2" * 64)
        )
        assert doc is not None
        assert doc.origin_original_id is None
