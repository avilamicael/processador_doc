"""Desfazer automações aplicadas — reversão por-doc e por-run (AUT-05, Open Q2).

Molde: `app/automation/fileops.py` (irmão: escrita verificada, hashing) +
`app/storage/cas.py` `read_bytes` (rede final de recuperação). O undo é a
contraparte da operação física: devolve o arquivo do DESTINO para a ORIGEM,
com uma rede de segurança no CAS quando o destino foi alterado/apagado pelo
usuário entre o apply e o undo.

Mecânica central (por `AuditLog(status="done")`):
- DESTINO PRESENTE → o arquivo no destino é o artefato aplicado: move-o de volta
  para `source_path` (escrita verificada) e remove o destino; `status="undone"`.
- DESTINO SUMIU/MUDOU → restaura o conteúdo imutável do CAS
  (`read_bytes_from_cas(content_hash)`) para `source_path`; `status="undone_from_cas"`
  (Open Q2 / AUT-05). NUNCA perde: o CAS guarda o conteúdo para sempre.

Orquestradores:
- `undo_document(session, document_id)` — reverte os `done` de um documento e o
  REABRE (CONCLUIDO→PROCESSANDO, a aresta nova da allowlist da Fase 6) para o doc
  voltar a ser acionável.
- `undo_run(session, run_id)` — reverte em lote tudo que uma execução aplicou
  (AUT-05/D-03); devolve a quantidade revertida.

Esta camada é só a MECÂNICA de arquivo + persistência do status do audit/estado
do doc. A reaplicação/reprocessamento pós-undo é responsabilidade do endpoint
(Plan 04). NÃO loga conteúdo — só ids/paths/status (V7/V9).
"""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.automation import fileops
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.enums import DocState
from app.pipeline.state_machine import transition
from app.pipeline.states import InvalidTransition
from app.storage import cas

# Marcador interno ao qual o documento volta ao ser reaberto pelo undo: a fila/UI
# o trata como "pronto para reaplicar/reprocessar" no estado PROCESSANDO.
_REOPENED_STEP = "classificado"


def _atomic_write_bytes(data: bytes, dst: Path) -> None:
    """Escreve `data` atomicamente no `dst` (tmp no mesmo dir + fsync + replace).

    Espelha o padrão do CAS: grava num temporário no diretório do destino, faz
    `fsync` e `os.replace`. Usado na restauração da rede final (CAS), onde o
    conteúdo já é a fonte da verdade e não precisa de re-verificação de hash.
    """
    import os
    import uuid

    dst = Path(dst)
    tmp: Path | None = dst.parent / f".{uuid.uuid4().hex}.tmp"
    try:
        with tmp.open("wb") as fout:
            fout.write(data)
            fout.flush()
            os.fsync(fout.fileno())
        os.replace(tmp, dst)
        tmp = None
    finally:
        if tmp is not None and tmp.exists():
            tmp.unlink(missing_ok=True)


def read_bytes_from_cas(content_hash: str) -> bytes:
    """Rede final de recuperação: conteúdo imutável do CAS por hash (AUT-05).

    Fachada fina sobre `cas.read_bytes` — ponto único monkeypatchável nos testes
    do fallback. O CAS preserva o conteúdo para sempre (D-08), então restaurar
    daqui nunca perde.
    """
    return cas.read_bytes(content_hash)


def undo_operation(session: Session, audit: AuditLog) -> str:
    """Reverte UMA automação registrada em `audit`; devolve o status resultante.

    - destino presente (`dest_path` existe) → é o artefato aplicado: escreve-o de
      volta na `source_path` (escrita verificada por hash do próprio conteúdo do
      destino) e remove o destino; retorna `"undone"`;
    - destino sumiu/mudou → restaura `read_bytes_from_cas(content_hash)` para a
      `source_path` (rede final); retorna `"undone_from_cas"`.

    Persiste `audit.status` no commit. NUNCA perde: se o destino existe usa-o;
    senão recorre ao CAS imutável. Falha de disco (`PermissionError`) propaga sem
    corromper o audit (não vira "done" inconsistente). NÃO loga conteúdo.
    """
    source = Path(audit.source_path) if audit.source_path else None
    dest = Path(audit.dest_path) if audit.dest_path else None
    content_hash = audit.content_hash

    if source is None:
        # Sem origem registrada não há para onde reverter — falha controlada, sem
        # marcar o audit como revertido.
        raise ValueError("AuditLog sem source_path — undo impossível")

    if dest is not None and dest.exists():
        # Destino presente: o arquivo no destino É o que aplicamos → devolve à
        # origem com escrita verificada (hash do conteúdo do próprio destino) e
        # remove o destino. Origem livre garantida pelo fluxo de apply.
        expected = fileops.hash_file(dest)
        source.parent.mkdir(parents=True, exist_ok=True)
        fileops._verified_write(fileops._stream_file(dest), source, expected)
        dest.unlink(missing_ok=True)
        result = "undone"
    else:
        # Destino sumiu/mudou (usuário mexeu) → rede final do CAS (Open Q2).
        if not content_hash:
            raise ValueError(
                "AuditLog sem content_hash e destino ausente — undo impossível"
            )
        blob = read_bytes_from_cas(content_hash)
        source.parent.mkdir(parents=True, exist_ok=True)
        # O CAS é a fonte da verdade por construção (blob endereçado pelo hash);
        # restaura o conteúdo direto, sem re-verificar contra content_hash.
        _atomic_write_bytes(blob, source)
        result = "undone_from_cas"

    audit.status = result
    session.commit()
    return result


def _reopen_document(session: Session, document_id: int) -> None:
    """Reabre o documento aplicado: CONCLUIDO→PROCESSANDO (aresta nova, AUT-05).

    Só transita quando o documento está em CONCLUIDO (a única origem válida da
    aresta nova). Em qualquer outro estado, não força transição inválida — o undo
    da mecânica de arquivo já ocorreu e não deve ser revertido por isso.
    """
    doc = session.get(Document, document_id)
    if doc is None or doc.state != DocState.CONCLUIDO:
        return
    try:
        transition(session, doc, DocState.PROCESSANDO, completed_step=_REOPENED_STEP)
    except InvalidTransition:
        # Estado mudou concorrentemente para algo sem a aresta — não corromper.
        session.rollback()


def undo_document(session: Session, document_id: int) -> list[str]:
    """Reverte todas as automações `done` de um documento e o REABRE.

    Seleciona `AuditLog(document_id=X, status="done")`, reverte cada uma
    (`undo_operation`) e, ao final, reabre o documento (CONCLUIDO→PROCESSANDO) para
    voltar a ser acionável. Devolve a lista de status resultantes.
    """
    audits = session.scalars(
        select(AuditLog).where(
            AuditLog.document_id == document_id,
            AuditLog.status == "done",
        )
    ).all()
    results = [undo_operation(session, audit) for audit in audits]
    _reopen_document(session, document_id)
    return results


def undo_run(session: Session, run_id: str) -> int:
    """Reverte em lote tudo que a execução `run_id` aplicou (AUT-05/D-03).

    Seleciona `AuditLog(run_id=R, status="done")`, reverte cada uma e reabre os
    documentos envolvidos (CONCLUIDO→PROCESSANDO). Devolve a quantidade revertida.
    """
    audits = session.scalars(
        select(AuditLog).where(
            AuditLog.run_id == run_id,
            AuditLog.status == "done",
        )
    ).all()
    reverted = 0
    doc_ids: set[int] = set()
    for audit in audits:
        if audit.document_id is not None:
            doc_ids.add(audit.document_id)
        undo_operation(session, audit)
        reverted += 1
    for document_id in doc_ids:
        _reopen_document(session, document_id)
    return reverted
