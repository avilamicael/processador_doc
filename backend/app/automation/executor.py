"""Executor PURO das automações (MODELO FINAL — D-23..D-26).

Coração do modelo final. Separa a EXECUÇÃO LÓGICA (pura, sem disco) da
MATERIALIZAÇÃO FÍSICA (uma vez, ao final — feita pelo `stage`). Substitui o antigo
`pipeline.run_pipeline` (pipeline de etapas com filtros/gates) por:

    Avalia as automações ATIVAS por ORDEM (`position`). A PRIMEIRA cujas TODAS as
    condições casam (E) executa suas AÇÕES (rename/move) em ordem. As demais NÃO
    rodam. Nenhuma casa → no-op (documento mantido na origem).

Semântica (D-25 primeira-que-casa-vence; D-26 materialização única):
- **Condições (D-24):** combinadas por E; reusa `rules.automation_conditions_match`
  (sem eval, V5). A condição `template` lê o `ClassificationResult` existente (custo
  0, NÃO re-cobra a IA — o `template_id` chega em `file_attrs`).
- **Ações (D-24):** `rename` muta SÓ o nome-alvo, `move` muta SÓ a pasta-alvo — EM
  MEMÓRIA, na ordem. O caller materializa o par final UMA vez (D-26).
- **Bloqueio (D-07):** um token referenciou campo faltante/inválido (ou o destino
  escaparia da raiz-base, V4) → `blocked=True`; o caller rebaixa para revisão SEM
  materializar.
- **No-match (D-25):** nenhuma automação casou → `matched=False` e o plano-alvo fica
  no DEFAULT (raiz-base + nome original); o caller faz o no-op explícito (mantém na
  origem, NÃO materializa para a raiz).

PURO: sem disco, sem ORM, sem `eval`. NUNCA loga valores de campo (V7/V9).
"""

from dataclasses import dataclass, field
from pathlib import Path

from app.automation import naming
from app.automation.rules import ConditionSpec, automation_conditions_match


@dataclass(frozen=True)
class AutomationPlan:
    """Decisão das automações para UM documento (D-23..D-26).

    - `target_folder`/`target_name`: o plano-alvo final (materializado UMA vez pelo
      caller) quando uma automação casa e suas ações resolvem sem bloquear;
    - `blocked=True`: um token referenciou campo faltante/inválido OU o destino
      escaparia da raiz-base (D-07/V4) → o caller rebaixa para revisão SEM materializar;
    - `matched=False`: nenhuma automação casou (D-25 no-match) → no-op explícito;
    - `automation_id`: id da automação que casou (diagnóstico/auditoria; None se nenhuma).
    """

    target_folder: Path | None = None
    target_name: str | None = None
    blocked: bool = False
    matched: bool = False
    automation_id: int | None = None


@dataclass
class ActionSpec:
    """Ação PURA de uma automação (o caller mapeia o ORM para isto).

    `params` é o dicionário já desserializado de `params_json` (D-24):
      rename → {"name_pattern": "{cliente}_{numero}"}
      move   → {"dest_folder": "Documentos/{cliente}/{data:aaaa-mm}"}
    """

    position: int
    action_type: str
    params: dict = field(default_factory=dict)


@dataclass
class AutomationSpec:
    """Forma PURA de uma automação (o caller mapeia o ORM para isto).

    `position` é a prioridade/ordem entre automações (D-25); `active=False` é uma
    automação pausada (ignorada na avaliação). `conditions` combinam por E (D-24);
    `actions` executam em ordem de `position`.
    """

    position: int
    conditions: list[ConditionSpec] = field(default_factory=list)
    actions: list[ActionSpec] = field(default_factory=list)
    active: bool = True
    automation_id: int | None = None


def _apply_actions(
    actions: list[ActionSpec],
    fields: dict[str, str],
    *,
    base_root: Path,
    default_folder: Path,
    default_name: str | None,
) -> tuple[Path | None, str | None, bool]:
    """Aplica as AÇÕES ordenadas, mutando nome/pasta-alvo em memória (D-24/D-26).

    rename → `resolve_pattern` muta SÓ o nome; move → `resolve_dest_folder`
    (confinado V4) muta SÓ a pasta. Token p/ campo faltante/inválido ou destino fora
    da raiz → devolve `blocked=True` (terceiro elemento). Retorna `(folder, name,
    blocked)`. NÃO loga valores.
    """
    folder: Path | None = default_folder
    name: str | None = default_name

    for action in sorted(actions, key=lambda a: a.position):
        if action.action_type == "rename":
            resolved_name = naming.resolve_pattern(
                action.params.get("name_pattern", ""), fields
            )
            if resolved_name is None:
                return None, None, True  # D-07
            name = resolved_name
        elif action.action_type == "move":
            resolved_folder = naming.resolve_dest_folder(
                action.params.get("dest_folder", ""), fields, base_root=base_root
            )
            if resolved_folder is None:
                return None, None, True  # D-07 / V4
            folder = resolved_folder
        # action_type desconhecido: ignora (ação inerte) — falha fechada (V5).

    return folder, name, False


def evaluate_automations(
    automations: list[AutomationSpec],
    fields: dict[str, str],
    file_attrs: dict,
    *,
    base_root: Path,
) -> AutomationPlan:
    """Avalia as automações por ORDEM; a PRIMEIRA que casa executa suas ações (D-25).

    Plano-alvo inicial = DEFAULT: pasta = `base_root` resolvida, nome = nome original
    do arquivo. As automações ATIVAS são avaliadas por `position` (menor primeiro);
    para a PRIMEIRA cujas TODAS as condições casam (E, `automation_conditions_match`):
      - executa suas AÇÕES em ordem (`_apply_actions`): rename muta só o nome, move
        muta só a pasta; campo faltante/destino fora da raiz → `blocked` (D-07/V4);
      - devolve o plano-alvo com `matched=True`.
    Nenhuma automação casa → `matched=False` e o plano fica no DEFAULT (o caller faz
    o no-op explícito, NÃO materializa para a raiz). NUNCA `eval`. NÃO loga valores.
    """
    base = base_root.resolve()
    default_name: str | None = file_attrs.get("original_filename")
    template_id: int | None = file_attrs.get("template_id")

    ordered = sorted(
        (a for a in automations if a.active), key=lambda a: a.position
    )
    for automation in ordered:
        if not automation_conditions_match(
            automation.conditions, fields, file_attrs, template_id
        ):
            continue

        # Primeira automação que casa (D-25): executa suas ações e PARA.
        folder, name, blocked = _apply_actions(
            automation.actions,
            fields,
            base_root=base_root,
            default_folder=base,
            default_name=default_name,
        )
        if blocked:
            return AutomationPlan(
                blocked=True, matched=True, automation_id=automation.automation_id
            )
        return AutomationPlan(
            target_folder=folder,
            target_name=name,
            matched=True,
            automation_id=automation.automation_id,
        )

    # Nenhuma automação casou (D-25 no-match): plano default, no-op no caller.
    return AutomationPlan(
        target_folder=base,
        target_name=default_name,
        matched=False,
    )
