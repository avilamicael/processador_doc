"""Estágio de automação — orquestra automações→naming→fileops→audit write-ahead→
estado num fluxo IDEMPOTENTE (Fase 6, MODELO FINAL D-23..D-26; AUT-03/04/06, D-07).

Espelha `classification/stage.py` em forma e garantias: função isolável (sem HTTP),
idempotente e com persistência ATÔMICA via `transition`. Executa as AUTOMAÇÕES
(`executor.evaluate_automations` — primeira-que-casa-vence) e materializa do CAS UMA
ÚNICA VEZ ao final (D-26). Liga as peças puras:
- `automation.executor` (avalia condições E → primeira automação → ações, D-24/D-25);
- `automation.rules` (condições `automation_conditions_match`, D-24);
- `automation.naming` (`resolve_pattern`/`resolve_dest_folder`, confinado V4 — usado
  dentro do executor);
- `automation.fileops` (`materialize_to_dest` do CAS + `remove_original`, AUT-06);
à persistência (`AuditLog` write-ahead) e à máquina de estados (`transition`).

Garantias materializadas:
- **Idempotência:** checa `AuditLog(document_id, status="done")` ANTES de qualquer
  operação física → no-op (NÃO re-materializa).
- **Write-ahead (AUT-04):** `AuditLog(status="intent", source_path, dest_path,
  run_id, content_hash)` é persistido (commit) ANTES de tocar o disco
  (`materialize_to_dest`). Um crash entre intent e done deixa um `intent` órfão
  RECONCILIÁVEL no startup (`reconcile_orphans`).
- **Copia→verifica→remove a origem (AUT-06):** `materialize_to_dest` escreve do CAS
  e verifica o hash; só ENTÃO `remove_original(source_path)`.
- **Estado via transition (commit único):** ao concluir, `transition(CONCLUIDO,
  completed_step="aplicado")` comita o `status="done"` + o estado JUNTOS.
- **Bloqueio → revisão (D-07):** token referenciando campo faltante/inválido (ou
  destino que escaparia da raiz-base, V4) → `resolve_*` devolve None →
  `transition(EM_REVISAO)` SEM tocar o disco e SEM AuditLog de operação.
- **No-match (D-25):** nenhuma automação casou → NO-OP explícito (doc mantido na
  origem, SEM transição, SEM disco).
- **Duplicata idêntica (D-10):** destino já contém o mesmo conteúdo → conclui sem mover.
- **Não vazar conteúdo (V7/V9):** loga só metadados — NUNCA valores de campo.

Interface pública: `apply_stage`, `dry_run`, `reconcile_orphans`, `ApplyStageResult`,
`APPLY_STEP`.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.automation import fileops, naming
from app.automation.executor import (
    ActionSpec,
    AutomationPlan,
    AutomationSpec,
    evaluate_automations,
)
from app.automation.rules import ConditionSpec
from app.config import get_settings
from app.models.audit_log import AuditLog
from app.models.automation import Automation
from app.models.classification import ClassificationResult, FilledField
from app.models.document import Document
from app.models.enums import DocState
from app.models.ingested_original import IngestedOriginal
from app.models.watched_folder import WatchedFolder
from app.pipeline.state_machine import transition
from app.storage import cas

logger = logging.getLogger(__name__)

# Step do job de automação despachado pelo worker. A fila enfileira
# (content_hash, APPLY_STEP) quando o doc está pronto para aplicar.
APPLY_STEP = "apply"

# Marcador interno avançado ao concluir a automação. NÃO é estado de topo.
APPLIED_STEP = "aplicado"

# Marcador ao qual o documento volta quando rebaixado para revisão (D-07).
CLASSIFIED_STEP = "classificado"

# Ação registrada no AuditLog write-ahead do MOVE (alvo final que remove o original).
_ACTION = "apply"

# Ação registrada no AuditLog write-ahead de CADA cópia (Fase 06.2 — D-01/D-07). O
# undo discrimina por este rótulo: "copy" apaga a cópia (nunca toca o original).
_COPY_ACTION = "copy"


@dataclass(frozen=True)
class StageOutput:
    """UMA saída de uma automação aplicada/simulada (Fase 06.2 — multi-saída).

    `kind` discrimina `"copy"` (saída ADICIONAL que NÃO remove o original, D-01) de
    `"move"` (o alvo final que remove o original ao fim, D-03). `dest_path` é o destino
    efetivo (já com anti-colisão resolvida). `collision`/`skipped_identical` espelham
    a semântica D-09/D-10 POR saída. `removes_original` deriva de `kind` (só o move
    remove) — explícito para a UI mostrar o badge "não remove o original" na cópia.
    """

    kind: str  # "copy" | "move"
    dest_path: str
    collision: bool = False
    skipped_identical: bool = False

    @property
    def removes_original(self) -> bool:
        """True só para o move — a cópia NUNCA remove o original (D-01)."""
        return self.kind == "move"


@dataclass(frozen=True)
class ApplyStageResult:
    """Resultado de `apply_stage`/`dry_run`: o plano origem→destino e o que ocorreu.

    `materialized=True` só quando alguma operação física de fato escreveu num destino
    (não em no-op idempotente, duplicata idêntica D-10, dry-run, bloqueio D-07 ou
    no-match D-25).
    `blocked=True` quando o destino não pôde ser resolvido (campo faltante/inválido
    ou confinamento V4) e o documento foi rebaixado para revisão.
    `collision=True` quando o nome de destino colidiu e foi resolvido por sufixo (D-09).
    `no_match=True` quando NENHUMA automação casou (no-op, doc fica na origem, D-25).

    Multi-saída (Fase 06.2): `outputs` lista CADA saída (N cópias + 0..1 move), cada
    uma com seu `kind`/`dest_path`/flags — a API emite uma linha por saída. Os campos
    single-output (`dest_path`/`collision`/`skipped_identical`) permanecem preenchidos
    pela saída de MOVE (ou, em copy-only, pela ÚLTIMA cópia) para não quebrar os
    consumidores existentes (D-04: não-regressão).
    """

    document_id: int
    source_path: str | None
    dest_path: str | None
    materialized: bool
    blocked: bool
    collision: bool
    skipped_identical: bool
    no_match: bool = False
    automation_id: int | None = None
    outputs: tuple[StageOutput, ...] = ()


def _conditions_to_pure(automation: Automation) -> list[ConditionSpec]:
    """Mapeia os `AutomationCondition` ORM → forma pura `ConditionSpec` (D-24).

    Ordena por `position` (cosmético — todas combinam por E). Só metadados de
    configuração — sem valores de campo do documento.
    """
    return [
        ConditionSpec(
            field=c.field,
            operator=c.operator,
            value=c.value,
            field_name=c.field_name,
        )
        for c in sorted(automation.conditions, key=lambda c: c.position)
    ]


def _actions_to_pure(automation: Automation) -> list[ActionSpec]:
    """Mapeia os `AutomationAction` ORM → forma pura `ActionSpec` (D-24).

    Ordena por `position` (ordem de execução, D-24). `params_json` é desserializado
    (json.loads; vazio/inválido → {}).
    """
    specs: list[ActionSpec] = []
    for action in sorted(automation.actions, key=lambda a: a.position):
        try:
            params = json.loads(action.params_json) if action.params_json else {}
        except (ValueError, TypeError):
            params = {}
        if not isinstance(params, dict):
            params = {}
        specs.append(
            ActionSpec(
                position=action.position,
                action_type=action.action_type,
                params=params,
            )
        )
    return specs


def _load_automation_specs(session: Session) -> list[AutomationSpec]:
    """Carrega TODAS as automações e mapeia para a forma pura `AutomationSpec`.

    Carrega todas (inclusive pausadas — o executor pula as `active=False`, mantendo
    a decisão num único lugar), ordenadas por `position` (D-25). Sem automações →
    lista vazia (o executor produz um plano default = no-match).
    """
    automations = session.scalars(
        select(Automation).order_by(Automation.position, Automation.id)
    ).all()
    specs: list[AutomationSpec] = []
    for automation in automations:
        specs.append(
            AutomationSpec(
                position=automation.position,
                conditions=_conditions_to_pure(automation),
                actions=_actions_to_pure(automation),
                active=automation.active,
                automation_id=automation.id,
            )
        )
    return specs


def _fields_map(session: Session, doc: Document) -> dict[str, str]:
    """Monta `{field_name: normalized_value}` dos campos VÁLIDOS do documento.

    Consome o `ClassificationResult` + `FilledField`s do doc. Só os campos válidos
    com valor normalizado entram (D-07: um campo faltante/inválido simplesmente não
    está no mapa, então um token que o referencie resolve para None → bloqueio). NÃO
    loga valores (V7/V9).
    """
    cr = session.scalar(
        select(ClassificationResult).where(ClassificationResult.document_id == doc.id)
    )
    if cr is None:
        return {}
    fields = session.scalars(
        select(FilledField).where(FilledField.classification_result_id == cr.id)
    ).all()
    result: dict[str, str] = {}
    for ff in fields:
        if ff.valid and ff.normalized_value is not None and ff.normalized_value.strip():
            result[ff.field_name] = ff.normalized_value
    return result


def _source_path(session: Session, doc: Document) -> Path:
    """Reconstrói o caminho de ORIGEM do arquivo do documento.

    Padrão de documents.py: `WatchedFolder.path / IngestedOriginal.original_filename`
    via `origin_original_id`. Sem original registrado (ex.: testes/legados) → cai no
    `original_filename` do próprio documento como caminho relativo. NÃO loga conteúdo.
    """
    if doc.origin_original_id is not None:
        row = session.execute(
            select(WatchedFolder.path, IngestedOriginal.original_filename)
            .join(
                IngestedOriginal,
                IngestedOriginal.source_folder_id == WatchedFolder.id,
            )
            .where(IngestedOriginal.id == doc.origin_original_id)
        ).first()
        if row is not None:
            folder_path, original_filename = row
            return Path(folder_path) / original_filename
    return Path(doc.original_filename)


def _base_root() -> Path:
    """Raiz-base de confinamento dos destinos (V4).

    `automation_dest_root` da config quando definido (o cliente trava a base por env);
    caso contrário, uma pasta padrão sob a pasta de dados única (`data_dir/organizados`).
    Confinamento é responsabilidade de `naming.resolve_dest_folder` (is_relative_to).
    """
    settings = get_settings()
    if settings.automation_dest_root:
        # D-21: normaliza aspas nas pontas (o env pode vir com caminho Windows entre
        # aspas) antes de construir o Path; confinamento V4 segue na resolução.
        return Path(naming.strip_quotes(settings.automation_dest_root))
    return settings.data_dir / "organizados"


def _source_folder_name(session: Session, source_folder_id: int | None) -> str | None:
    """Nome/caminho da pasta de origem — base da condição `source_folder` (D-24).

    A condição `source_folder` compara o caminho da pasta monitorada de origem. O
    avaliador casa `str(file_attrs["source_folder"])`; aqui devolvemos o `path` da
    `WatchedFolder` (o que o usuário digita na condição). None → condição não casa.
    """
    if source_folder_id is None:
        return None
    folder = session.get(WatchedFolder, source_folder_id)
    return folder.path if folder is not None else None


def _file_attrs(session: Session, doc: Document) -> dict:
    """Monta os atributos de arquivo do documento — base das condições D-24.

    `ext` (suffix do original), `size` (do CAS pelo content_hash; lido UMA vez),
    `source_folder_id` + `source_folder` (path da pasta de origem),
    `original_filename` e `template_id` (do `ClassificationResult` existente — a
    condição `template` lê isto, custo 0, NÃO re-cobra IA). NÃO loga valores.
    """
    original_filename = doc.original_filename
    source_folder_id: int | None = None
    if doc.origin_original_id is not None:
        original = session.get(IngestedOriginal, doc.origin_original_id)
        if original is not None:
            source_folder_id = original.source_folder_id
            original_filename = original.original_filename

    # Tamanho: lê o blob do CAS uma vez. Ausente/erro → 0 (condição size não casa).
    size = 0
    try:
        if cas.exists(doc.content_hash):
            size = len(cas.read_bytes(doc.content_hash))
    except OSError:
        size = 0

    template_id: int | None = None
    cr = session.scalar(
        select(ClassificationResult).where(
            ClassificationResult.document_id == doc.id
        )
    )
    if cr is not None:
        template_id = cr.template_id

    return {
        "ext": Path(original_filename).suffix,
        "size": size,
        "source_folder_id": source_folder_id,
        "source_folder": _source_folder_name(session, source_folder_id),
        "original_filename": Path(original_filename).name,
        "template_id": template_id,
    }


def _resolve_plan(session: Session, doc: Document) -> tuple[Path, AutomationPlan]:
    """Avalia as automações e devolve (source_path, AutomationPlan). NÃO toca o disco.

    Monta `fields` (campos extraídos), `file_attrs` (dimensão de arquivo, D-24) e os
    `AutomationSpec`, e chama `evaluate_automations` (PURO). O caller (dry_run/
    apply_stage) interpreta o `AutomationPlan`: `blocked` → revisão; `matched=False`
    → no-op explícito; senão materializa o par `(target_folder, target_name)` UMA
    vez. NÃO loga valores.
    """
    fields = _fields_map(session, doc)
    base_root = _base_root()
    source = _source_path(session, doc)
    file_attrs = _file_attrs(session, doc)
    specs = _load_automation_specs(session)

    plan = evaluate_automations(specs, fields, file_attrs, base_root=base_root)
    return source, plan


def _plan_dest(source: Path, plan: AutomationPlan) -> Path:
    """Compõe o caminho-destino final do `AutomationPlan` (pasta/nome), preservando ext.

    Sanitiza o nome-alvo como componente; se o padrão não trouxe extensão e a origem
    tem, preserva a extensão do original. Só faz sentido quando o plano NÃO está
    bloqueado.
    """
    folder = plan.target_folder if plan.target_folder is not None else source.parent
    name = plan.target_name if plan.target_name is not None else source.name
    if not Path(name).suffix and source.suffix:
        name = name + source.suffix
    return folder / name


def _copy_dest(source: Path, copy) -> Path:
    """Compõe o destino de UMA `PlannedCopy`, preservando a extensão do original.

    Mesma lógica de `_plan_dest` (sanitiza/preserva ext) aplicada à pasta confinada e
    ao nome-alvo CORRENTE da cópia (D-03). `copy` é um `executor.PlannedCopy`.
    """
    name = copy.name if copy.name is not None else source.name
    if not Path(name).suffix and source.suffix:
        name = name + source.suffix
    return copy.folder / name


def _has_done(session: Session, document_id: int) -> bool:
    """True se já existe um AuditLog(status="done") para o doc (idempotência)."""
    existing = session.scalar(
        select(AuditLog).where(
            AuditLog.document_id == document_id,
            AuditLog.status == "done",
        )
    )
    return existing is not None


def dry_run(session: Session, *, content_hash: str) -> ApplyStageResult | None:
    """Simula as automações por doc SEM tocar o disco e SEM AuditLog (AUT-03).

    Localiza o documento por `content_hash`; avalia as automações (`_resolve_plan`)
    e interpreta o `AutomationPlan`, sinalizando para o preview da UI: `no_match`
    (D-25), `blocked` (D-07), `collision` (D-09) e `skipped_identical` (D-10). NUNCA
    move nem escreve AuditLog. Documento inexistente → None. NÃO loga valores.
    """
    doc = session.scalar(select(Document).where(Document.content_hash == content_hash))
    if doc is None:
        return None

    source, plan = _resolve_plan(session, doc)

    # Bloqueio (D-07): campo faltante/inválido ou confinamento V4.
    if plan.blocked:
        return ApplyStageResult(
            document_id=doc.id,
            source_path=str(source),
            dest_path=None,
            materialized=False,
            blocked=True,
            collision=False,
            skipped_identical=False,
            automation_id=plan.automation_id,
        )

    # No-match (D-25): nenhuma automação casou — doc fica na origem (no-op).
    if not plan.matched:
        return ApplyStageResult(
            document_id=doc.id,
            source_path=str(source),
            dest_path=None,
            materialized=False,
            blocked=False,
            collision=False,
            skipped_identical=False,
            no_match=True,
        )

    def _preview_collision(dst: Path) -> tuple[Path, bool, bool]:
        """Consulta colisão/idêntico SEM tocar o disco (só lê a existência)."""
        if not dst.exists():
            return dst, False, False
        try:
            resolved = fileops.resolve_collision(dst, source)
        except OSError:
            return dst, False, False
        if resolved is None:
            return dst, False, True  # D-10 (idêntico)
        if resolved != dst:
            return resolved, True, False  # D-09 (sufixo)
        return dst, False, False

    outputs: list[StageOutput] = []

    # (Fase 06.2) Uma linha por CÓPIA — origem→destino, sem remover o original.
    for planned_copy in plan.copies:
        cdst, c_collision, c_identical = _preview_collision(
            _copy_dest(source, planned_copy)
        )
        outputs.append(
            StageOutput(
                kind="copy",
                dest_path=str(cdst),
                collision=c_collision,
                skipped_identical=c_identical,
            )
        )

    # A saída de MOVE (alvo final) — emitida só quando há MOVE EFETIVO. Copy-only
    # (cópias + plano-alvo no DEFAULT) NÃO gera linha de move (o original permanece).
    base = _base_root().resolve()
    default_name = Path(source).name
    is_default_target = (
        plan.target_folder is not None
        and Path(plan.target_folder).resolve() == base
        and (plan.target_name is None or plan.target_name == default_name)
    )
    has_effective_move = not (plan.copies and is_default_target)

    m_collision = False
    m_identical = False
    move_dest = _plan_dest(source, plan)
    if has_effective_move:
        move_dest, m_collision, m_identical = _preview_collision(move_dest)
        outputs.append(
            StageOutput(
                kind="move",
                dest_path=str(move_dest),
                collision=m_collision,
                skipped_identical=m_identical,
            )
        )

    return ApplyStageResult(
        document_id=doc.id,
        source_path=str(source),
        dest_path=outputs[-1].dest_path if outputs else None,
        materialized=False,
        blocked=False,
        collision=m_collision,
        skipped_identical=m_identical,
        automation_id=plan.automation_id,
        outputs=tuple(outputs),
    )


# Alias do `dry_run` de módulo — o parâmetro `dry_run` de `apply_stage` sombreia o
# nome da função, então o caminho dry_run=True reusa a simulação multi-saída por aqui.
dry_run_result = dry_run


async def apply_stage(
    session: Session, *, content_hash: str, run_id: str | None = None, dry_run: bool = False
) -> ApplyStageResult:
    """Aplica as automações no bloco `content_hash`: write-ahead → materializa 1x → conclui.

    Coroutine (espelha `classify_stage`; o worker faz `await`). Fluxo:
      1. Localiza o `Document` por `content_hash` (None → ValueError, o worker re-tenta).
      2. IDEMPOTÊNCIA: `AuditLog(status="done")` existente → no-op (NÃO re-materializa).
      3. Avalia as automações (`_resolve_plan` → `AutomationPlan`):
         - `blocked` (D-07): `transition(EM_REVISAO)` SEM tocar o disco e SEM AuditLog;
         - `matched=False` (D-25): NO-OP explícito — doc MANTIDO NA ORIGEM, SEM
           transição e SEM tocar o disco. NUNCA materializa p/ a raiz.
      4. `dry_run=True` → devolve o plano SEM AuditLog e SEM disco (AUT-03).
      5. Anti-colisão (`resolve_collision`): idêntico → conclui sem mover (D-10);
         diferente → sufixo (D-09).
      6. WRITE-AHEAD: `AuditLog(status="intent", ...)` + `session.commit()` ANTES de
         materializar (AUT-04) — materialização ÚNICA (D-26).
      7. `materialize_to_dest` (do CAS, verifica hash). Erros de disco PROPAGAM.
      8. `remove_original(source)` — só APÓS a verificação passar (AUT-06).
      9. `audit.status="done"` + `transition(CONCLUIDO, completed_step="aplicado")`
         num COMMIT ÚNICO.

    Recusa/erros de disco PROPAGAM (sem try/catch aqui). NÃO loga valores de campo.
    """
    doc = session.scalar(select(Document).where(Document.content_hash == content_hash))
    if doc is None:
        raise ValueError("Document inexistente para content_hash informado")

    # (2) Idempotência: operação já concluída → no-op.
    if _has_done(session, doc.id):
        logger.debug("Automação já aplicada para document_id=%s — no-op", doc.id)
        return ApplyStageResult(
            document_id=doc.id,
            source_path=None,
            dest_path=None,
            materialized=False,
            blocked=False,
            collision=False,
            skipped_identical=False,
        )

    # (3) Avaliar as automações. Interpreta blocked/no-match ANTES de tocar o disco.
    source, plan = _resolve_plan(session, doc)

    # (3a) Bloqueio (D-07): revisão sem tocar o disco e sem AuditLog de operação.
    if plan.blocked:
        # NUNCA `session.commit()` antes do `transition` (atomicidade). Só transita
        # se o doc estiver num estado com aresta para EM_REVISAO (PROCESSANDO).
        if doc.state == DocState.PROCESSANDO:
            transition(
                session, doc, DocState.EM_REVISAO, completed_step=CLASSIFIED_STEP
            )
        logger.info(
            "Documento %s rebaixado para EM_REVISAO (campo faltante no padrão, D-07)",
            doc.id,
        )
        return ApplyStageResult(
            document_id=doc.id,
            source_path=str(source),
            dest_path=None,
            materialized=False,
            blocked=True,
            collision=False,
            skipped_identical=False,
            automation_id=plan.automation_id,
        )

    # (3b) No-match (D-25): nenhuma automação casou → NO-OP explícito. O documento é
    # MANTIDO NA ORIGEM, SEM transição de estado e SEM tocar o disco.
    if not plan.matched:
        logger.info(
            "Documento %s: nenhuma automação casou (D-25) — mantido na origem",
            doc.id,
        )
        return ApplyStageResult(
            document_id=doc.id,
            source_path=str(source),
            dest_path=None,
            materialized=False,
            blocked=False,
            collision=False,
            skipped_identical=False,
            no_match=True,
        )

    dest = _plan_dest(source, plan)

    # (4) dry-run: plano puro multi-saída, sem AuditLog e sem disco (AUT-03).
    if dry_run:
        return dry_run_result(session, content_hash=content_hash) or ApplyStageResult(
            document_id=doc.id,
            source_path=str(source),
            dest_path=str(dest),
            materialized=False,
            blocked=False,
            collision=False,
            skipped_identical=False,
            automation_id=plan.automation_id,
        )

    def _resolve_for_write(dst: Path) -> tuple[Path, bool, bool]:
        """Anti-colisão a MONTANTE (resolve_collision): devolve (dest, collision,
        skipped_identical) sem escrever. idêntico → skip (D-10); diferente → sufixo (D-09)."""
        if not dst.exists():
            return dst, False, False
        resolved = fileops.resolve_collision(dst, dst_src_for_collision(dst))
        if resolved is None:
            return dst, False, True  # D-10
        if resolved != dst:
            return resolved, True, False  # D-09
        return dst, False, False

    def dst_src_for_collision(_dst: Path) -> Path:
        # resolve_collision compara o conteúdo do destino contra o `src`; aqui o
        # conteúdo real vem do CAS, mas a origem física (`source`) é idêntica por
        # construção (mesmo content_hash) — usá-la mantém a semântica D-10.
        return source

    def _materialize(dst: Path) -> bool:
        """Materializa o blob do CAS em `dst` e verifica o hash (AUT-06). Devolve
        True se houve conteúdo físico; False se o blob não existe no CAS (conclusão
        lógica). Erros de disco PROPAGAM (origem intacta — verify-then-remove)."""
        try:
            fileops.materialize_to_dest(content_hash, dst)
            return True
        except FileNotFoundError:
            if cas.exists(content_hash):
                raise  # blob existe, destino falhou — propaga (retryável)
            logger.info(
                "Documento %s: sem conteúdo físico no CAS — conclusão lógica", doc.id
            )
            return False

    materialized_any = False
    outputs: list[StageOutput] = []

    # (5–7c) CÓPIAS PRIMEIRO (D-03): cada cópia com write-ahead próprio (D-07),
    # anti-colisão por destino (D-07/D-09/D-10) e materialização SEM remover o
    # original (D-01). O move (se houver) vem por ÚLTIMO.
    for planned_copy in plan.copies:
        cdst, c_collision, c_identical = _resolve_for_write(
            _copy_dest(source, planned_copy)
        )
        if c_identical:
            # D-10: a cópia idêntica já existe — registra como done sem re-materializar.
            copy_audit = AuditLog(
                document_id=doc.id,
                action=_COPY_ACTION,
                status="done",
                source_path=str(source),
                dest_path=str(cdst),
                run_id=run_id,
                content_hash=content_hash,
            )
            session.add(copy_audit)
            session.commit()
            outputs.append(
                StageOutput(kind="copy", dest_path=str(cdst), skipped_identical=True)
            )
            continue

        # WRITE-AHEAD por cópia (D-07): intenção persistida ANTES de materializar.
        copy_audit = AuditLog(
            document_id=doc.id,
            action=_COPY_ACTION,
            status="intent",
            source_path=str(source),
            dest_path=str(cdst),
            run_id=run_id,
            content_hash=content_hash,
        )
        session.add(copy_audit)
        session.commit()
        session.refresh(copy_audit)

        copied = _materialize(cdst)  # D-01: NUNCA chama remove_original p/ cópia.
        materialized_any = materialized_any or copied
        copy_audit.status = "done"
        session.commit()
        outputs.append(
            StageOutput(kind="copy", dest_path=str(cdst), collision=c_collision)
        )

    # Distingue MOVE EFETIVO de DEFAULT. Copy-only é LEGÍTIMO (cópias + nenhum move):
    # o plano-alvo fica no DEFAULT (base_root + nome original) e NÃO deve materializar
    # para a raiz. Há move efetivo quando a pasta-alvo difere do base_root OU o nome
    # difere do original (rename mudou o nome). Sem cópias, o caminho legado roda
    # sempre (não-regressão D-04: o move default vira o no-op/conclusão da Fase 6).
    base = _base_root().resolve()
    default_name = Path(source).name
    is_default_target = (
        plan.target_folder is not None
        and Path(plan.target_folder).resolve() == base
        and (plan.target_name is None or plan.target_name == default_name)
    )
    has_effective_move = not (plan.copies and is_default_target)

    if not has_effective_move:
        # COPY-ONLY (D-01/D-03): só cópias, sem move. Conclui o documento (D-05) sem
        # tocar o original — ele permanece na origem.
        if doc.state in (DocState.PROCESSANDO, DocState.EM_REVISAO):
            transition(session, doc, DocState.CONCLUIDO, completed_step=APPLIED_STEP)
        else:
            session.commit()
        logger.info(
            "Documento %s: copy-only aplicado (original mantido, D-01) — concluído",
            doc.id,
        )
        return ApplyStageResult(
            document_id=doc.id,
            source_path=str(source),
            dest_path=outputs[-1].dest_path if outputs else None,
            materialized=materialized_any,
            blocked=False,
            collision=False,
            skipped_identical=False,
            automation_id=plan.automation_id,
            outputs=tuple(outputs),
        )

    # (5–9) MOVE por ÚLTIMO: o original é a garantia até todas as cópias estarem
    # materializadas/verificadas (D-03). Mantém o comportamento da Fase 6.
    dest, collision, skipped_identical = _resolve_for_write(dest)

    if skipped_identical:
        # No-op de disco do move mas CONCLUI o documento (operação já-feita, D-10).
        outputs.append(
            StageOutput(kind="move", dest_path=str(dest), skipped_identical=True)
        )
        if doc.state in (DocState.PROCESSANDO, DocState.EM_REVISAO):
            transition(session, doc, DocState.CONCLUIDO, completed_step=APPLIED_STEP)
        else:
            session.commit()
        logger.info("Documento %s: destino idêntico já presente (D-10), concluído", doc.id)
        return ApplyStageResult(
            document_id=doc.id,
            source_path=str(source),
            dest_path=str(dest),
            materialized=materialized_any,
            blocked=False,
            collision=False,
            skipped_identical=True,
            automation_id=plan.automation_id,
            outputs=tuple(outputs),
        )

    # (6) WRITE-AHEAD do MOVE (AUT-04): intenção persistida ANTES de tocar o disco.
    audit = AuditLog(
        document_id=doc.id,
        action=_ACTION,
        status="intent",
        source_path=str(source),
        dest_path=str(dest),
        run_id=run_id,
        content_hash=content_hash,
    )
    session.add(audit)
    session.commit()
    session.refresh(audit)

    # (7) Materializa o move do CAS e verifica o hash (AUT-06).
    physically_moved = _materialize(dest)
    materialized_any = materialized_any or physically_moved

    # (8) Verificação passou → remove a origem (AUT-06: copia→verifica→remove). SÓ
    # AQUI, e SÓ DEPOIS de todas as cópias materializadas (D-03).
    if physically_moved:
        fileops.remove_original(source)

    outputs.append(
        StageOutput(kind="move", dest_path=str(dest), collision=collision)
    )

    # (9) status="done" + transition(CONCLUIDO) num COMMIT ÚNICO.
    audit.status = "done"
    if doc.state in (DocState.PROCESSANDO, DocState.EM_REVISAO):
        transition(session, doc, DocState.CONCLUIDO, completed_step=APPLIED_STEP)
    else:
        # Estado sem aresta para CONCLUIDO (ex.: já concluído): persiste só o done.
        session.commit()

    logger.info(
        "Automação aplicada document_id=%s run_id=%s status=done",
        doc.id,
        run_id,
    )
    return ApplyStageResult(
        document_id=doc.id,
        source_path=str(source),
        dest_path=str(dest),
        materialized=materialized_any,
        blocked=False,
        collision=collision,
        skipped_identical=False,
        automation_id=plan.automation_id,
        outputs=tuple(outputs),
    )


def reconcile_orphans(session: Session) -> int:
    """Reconcilia AuditLog(status="intent") órfãos (crash entre intent e done).

    Espelha `repo.requeue_running`: roda no STARTUP do worker (UMA vez). Para cada
    `intent` pendente, ADJUDICA o registro checando a integridade do DESTINO:
    - destino existe com o hash esperado (`content_hash`) → a materialização DE FATO
      ocorreu antes do crash → marca `status="done"` (idempotente, evita re-mover);
    - destino ausente/divergente/sem caminho registrado → a operação NÃO se
      completou → marca `status="orphaned"`. O documento permanece SEM
      `AuditLog(status="done")`, logo o apply o re-captura e re-materializa do CAS.

    Devolve quantos intents foram reconciliados. NÃO loga conteúdo.
    """
    intents = session.scalars(
        select(AuditLog).where(AuditLog.status == "intent")
    ).all()
    reconciled = 0
    for audit in intents:
        dest = Path(audit.dest_path) if audit.dest_path else None
        expected = audit.content_hash
        completed = False
        if dest is not None and expected and dest.exists():
            try:
                completed = fileops.hash_file(dest) == expected
            except OSError:
                logger.warning(
                    "Reconcile: destino ilegivel para audit %s — tratado como orfao",
                    audit.id,
                )
        if completed:
            audit.status = "done"
            logger.info("Reconcile: intent %s confirmado done (destino integro)", audit.id)
        else:
            audit.status = "orphaned"
            logger.info(
                "Reconcile: intent orfao %s sem destino integro — marcado orphaned",
                audit.id,
            )
        reconciled += 1
    if reconciled:
        session.commit()
    return reconciled
