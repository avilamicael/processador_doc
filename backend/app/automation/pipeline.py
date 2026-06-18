"""Executor PURO do pipeline de automação (Fase 6 REDESIGN — D-12..D-15).

Coração do REDESIGN. Separa a EXECUÇÃO LÓGICA (pura, sem disco) da MATERIALIZAÇÃO
FÍSICA (uma vez, ao final — feita pelo `apply_stage`). `run_pipeline` recebe a lista
ordenada de etapas + os campos extraídos + os atributos de arquivo e devolve uma
DECISÃO (`PipelinePlan`): um plano-alvo `(target_folder, target_name)`, OU um sinal
de bloqueio (D-07), OU um sinal de roteamento (Pitfall 9).

Semântica (06-RESEARCH §Pattern 1, recomendação HIGH):
- **Materialização única (Open Q1):** cada etapa Rename muta SÓ o nome-alvo, cada
  Move muta SÓ a pasta-alvo — EM MEMÓRIA. O caller materializa o par final UMA vez.
- **Ordem (D-12):** itera as etapas por `position`; uma etapa `active=False` é
  PULADA antes do filtro (pausada = como se não existisse no pipeline ativo).
- **Filtros (D-14):** uma etapa só executa se `filter_matches` casa; etapa sem
  filtros casa sempre. Reusa `rules.filter_matches` (sem eval, V5).
- **Pitfall 8:** [Move,Rename] e [Rename,Move] produzem o MESMO plano-alvo (folder e
  name são dimensões independentes).
- **Route (Pitfall 9):** `route` INTERROMPE o pipeline e devolve `route_to=...`; o
  caller transita/marca e NÃO materializa.
- **Gate identify_type (D-15):** chama `classify_fn(template_id)` (idempotente, lê o
  `ClassificationResult` existente — custo 0, NÃO re-cobra a IA) e seta
  `identified_template_id`, consumível pelos filtros `template` seguintes.
- **No-match (Pitfall 10):** nenhuma etapa casa → `matched_any=False` e o plano-alvo
  fica no DEFAULT (raiz-base + nome original); o caller decide o no-op explícito
  (mantém na origem, NÃO materializa para a raiz).

PURO: sem disco, sem ORM, sem `eval`. NUNCA loga valores de campo (V7/V9).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.automation import naming
from app.automation.rules import FilterSpec, filter_matches


@dataclass(frozen=True)
class PipelinePlan:
    """Decisão do pipeline para UM documento.

    - `target_folder`/`target_name`: o plano-alvo final (materializado UMA vez pelo
      caller) quando o pipeline conclui sem bloquear/rotear;
    - `blocked=True`: um token referenciou campo faltante/inválido OU o destino
      escaparia da raiz-base (D-07/V4) → o caller rebaixa para revisão SEM materializar;
    - `route_to`: a etapa Rotear interrompeu (Pitfall 9) → "em_revisao" |
      "nao_tratar" | "ignorar"; o caller trata e NÃO materializa;
    - `identified_template_id`: resultado do gate identify_type (D-15);
    - `matched_any=False`: nenhuma etapa casou (Pitfall 10) → no-op explícito.
    """

    target_folder: Path | None = None
    target_name: str | None = None
    blocked: bool = False
    route_to: str | None = None
    identified_template_id: int | None = None
    matched_any: bool = False


@dataclass
class PipelineStepSpec:
    """Forma PURA de uma etapa do pipeline (o caller mapeia o ORM para isto).

    `params` é o dicionário já desserializado de `params_json` (D-13):
      move → {"folder_pattern": ...}; rename → {"name_pattern": ...};
      identify_type → {"template_id": N}; route → {"target": "em_revisao"|...}.
    `filters` são `FilterSpec` puros; `active=False` é uma etapa pausada.
    """

    position: int
    action_type: str
    conjunction: str = "and"
    params: dict = field(default_factory=dict)
    filters: list[FilterSpec] = field(default_factory=list)
    active: bool = True


def run_pipeline(
    steps: list[PipelineStepSpec],
    fields: dict[str, str],
    file_attrs: dict,
    *,
    base_root: Path,
    classify_fn: Callable[[int | None], int | None],
) -> PipelinePlan:
    """Percorre as etapas ordenadas e resolve o plano-alvo (PURO — sem disco).

    Plano-alvo inicial = DEFAULT: pasta = `base_root` resolvida, nome = nome
    original do arquivo. Para cada etapa (ordenada por `position`):
      1. etapa pausada (`active=False`) → PULA (D-12);
      2. filtro não casa → PULA (D-14);
      3. senão `matched_any=True` e despacha por `action_type`:
         - `identify_type`: `classify_fn(template_id)` → `identified_template_id`
           (consumível pelos filtros `template` seguintes, D-15); o gate é o ÚNICO
           ponto que chama a classificação (idempotente, custo 0);
         - `rename`: `resolve_pattern` muta SÓ o nome; None → blocked (D-07);
         - `move`: `resolve_dest_folder` (confinado) muta SÓ a pasta; None →
           blocked (D-07/V4);
         - `route`: RETORNA imediatamente `route_to` (Pitfall 9) — NÃO materializa.
    Ao fim, devolve o plano-alvo. NUNCA `eval`. NÃO loga valores.
    """
    folder: Path | None = base_root.resolve()
    name: str | None = file_attrs.get("original_filename")
    identified: int | None = file_attrs.get("template_id")
    matched_any = False

    for step in sorted(steps, key=lambda s: s.position):
        # (1) Etapa pausada = como se não existisse no pipeline ativo (D-12).
        if not step.active:
            continue
        # (2) Filtro de entrada (D-14): sem filtros = casa sempre (P10).
        if not filter_matches(
            step.filters, step.conjunction, fields, file_attrs, identified
        ):
            continue

        matched_any = True
        action = step.action_type

        if action == "identify_type":
            # Gate D-15: reusa a classificação existente (custo 0, NÃO re-cobra IA).
            identified = classify_fn(step.params.get("template_id"))
            file_attrs = {**file_attrs, "template_id": identified}

        elif action == "rename":
            resolved_name = naming.resolve_pattern(
                step.params.get("name_pattern", ""), fields
            )
            if resolved_name is None:
                return PipelinePlan(blocked=True, matched_any=True)  # D-07
            name = resolved_name

        elif action == "move":
            resolved_folder = naming.resolve_dest_folder(
                step.params.get("folder_pattern", ""), fields, base_root=base_root
            )
            if resolved_folder is None:
                return PipelinePlan(blocked=True, matched_any=True)  # D-07 / V4
            folder = resolved_folder

        elif action == "route":
            # Pitfall 9: interrompe o pipeline; o caller transita/marca, NÃO materializa.
            return PipelinePlan(
                route_to=step.params.get("target"),
                identified_template_id=identified,
                matched_any=True,
            )
        # action_type desconhecido: ignora (etapa inerte) — falha fechada.

    return PipelinePlan(
        target_folder=folder,
        target_name=name,
        identified_template_id=identified,
        matched_any=matched_any,
    )
