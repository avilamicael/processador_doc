"""Fixtures compartilhadas da suíte de automações (Fase 6).

Provê, reusando as fixtures de engine/sessão de `tests/conftest.py`:
- `classified_doc`: um `Document` em PROCESSANDO (last_completed_step="classificado")
  com um `Template`, um `ClassificationResult` e `FilledField`s — alguns válidos,
  um obrigatório FALTANTE (raw_value None, valid=False) e um inválido — para os
  testes de naming (token faltante → None → revisão, D-07) e de regras (TPL-02).
- `src_dir` / `dst_dir`: temp dirs no MESMO volume (os.replace atômico funciona),
  consumidos por test_fileops/test_undo.

As fixtures de schema (`schema_engine`) e de pasta de dados (`data_dir`, que aponta
o CAS para um dir temporário) vêm do conftest raiz — não redefinir aqui.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import Engine

from app.models.automation_pipeline import (
    AutomationPipeline,
    PipelineStep,
    StepFilter,
)
from app.models.classification import ClassificationResult, FilledField
from app.models.document import Document
from app.models.enums import DocState
from app.models.template import Template, TemplateField
from app.storage.db import get_session

# Marcador interno de etapa que o classify_stage grava ao concluir (D-05).
CLASSIFIED_STEP = "classificado"


@dataclass
class ClassifiedDoc:
    """Bundle do documento classificado semeado, com os ids para os testes."""

    document_id: int
    content_hash: str
    template_id: int
    classification_result_id: int
    # Mapa field_name -> (raw_value, normalized_value, valid) do que foi semeado.
    fields: dict[str, tuple[str | None, str | None, bool]]


@pytest.fixture
def classified_doc(schema_engine: Engine) -> ClassifiedDoc:
    """Semeia um documento classificado pronto para a automação.

    Campos semeados (cobrindo os caminhos D-07/D-10 que naming/rules exercitam):
    - `cliente` (texto, válido) → "ACME Ltda"
    - `numero` (numero, válido) → raw "001234" / normalized "1234"
    - `valor` (moeda, válido) → raw "R$ 1.500,00" / normalized "1500.00"
    - `data` (data, válido) → raw "17/06/2026" / normalized "2026-06-17"
    - `obrigatorio_faltante` (texto, REQUIRED, FALTANTE) → raw None, valid=False
    - `invalido` (numero, inválido) → raw "abc", valid=False
    """
    content_hash = "a" * 64
    seeded = {
        "cliente": ("ACME Ltda", "ACME Ltda", True),
        "numero": ("001234", "1234", True),
        "valor": ("R$ 1.500,00", "1500.00", True),
        "data": ("17/06/2026", "2026-06-17", True),
        "obrigatorio_faltante": (None, None, False),
        "invalido": ("abc", None, False),
    }
    with get_session(schema_engine) as session:
        template = Template(name="Nota Fiscal", doc_type="Fiscal")
        template.fields = [
            TemplateField(name="cliente", field_type="texto"),
            TemplateField(name="numero", field_type="numero"),
            TemplateField(name="valor", field_type="moeda"),
            TemplateField(name="data", field_type="data"),
            TemplateField(
                name="obrigatorio_faltante", field_type="texto", required=True
            ),
            TemplateField(name="invalido", field_type="numero"),
        ]
        session.add(template)
        session.flush()

        doc = Document(
            content_hash=content_hash,
            original_filename="entrada.pdf",
            state=DocState.PROCESSANDO,
            last_completed_step=CLASSIFIED_STEP,
        )
        session.add(doc)
        session.flush()

        result = ClassificationResult(
            document_id=doc.id, template_id=template.id, confidence=0.95
        )
        result.filled_fields = [
            FilledField(
                field_name=name,
                raw_value=raw,
                normalized_value=norm,
                valid=valid,
                invalid_reason=None if valid else "valor ausente/ inválido",
            )
            for name, (raw, norm, valid) in seeded.items()
        ]
        session.add(result)
        session.commit()

        return ClassifiedDoc(
            document_id=doc.id,
            content_hash=content_hash,
            template_id=template.id,
            classification_result_id=result.id,
            fields=seeded,
        )


@dataclass
class FileAttrs:
    """Atributos de arquivo do bloco — base dos filtros D-14 do pipeline (06-07).

    Estende o `classified_doc` (campos extraídos) com a dimensão "arquivo": a
    extensão, o tamanho, a pasta de origem (`source_folder_id`→`WatchedFolder.path`)
    e o nome original. Consumidos pelos filtros `extension`/`size`/`source_folder`/
    `filename` que o executor do pipeline aplica.
    """

    ext: str
    size: int
    source_folder_id: int | None
    original_filename: str


@pytest.fixture
def classified_doc_attrs(classified_doc: "ClassifiedDoc") -> FileAttrs:
    """Atributos de arquivo que ACOMPANHAM o `classified_doc` (NÃO o redefine).

    Disponibiliza, para os testes de filtros do pipeline (06-07), a dimensão de
    arquivo do mesmo bloco semeado por `classified_doc`: `.pdf`, ~120 KB, sem
    pasta de origem específica e com o nome original do bundle.
    """
    return FileAttrs(
        ext=".pdf",
        size=120_000,
        source_folder_id=None,
        original_filename="entrada.pdf",
    )


# Fábrica que cria um AutomationPipeline com N steps; retorna o id do pipeline.
PipelineFactory = Callable[..., int]


@pytest.fixture
def pipeline_factory(schema_engine: Engine) -> PipelineFactory:
    """Cria um `AutomationPipeline` persistido com N `PipelineStep` (cada um com
    `action_type`/`params_json` e 0..N `StepFilter`) — base dos testes do executor
    (06-07).

    Uso:
        pid = pipeline_factory(
            name="P1",
            steps=[
                {
                    "action_type": "rename",
                    "params_json": '{"name_pattern": "{cliente}_{numero}"}',
                    "filters": [
                        {"filter_type": "field", "field_name": "cliente",
                         "operator": "eq", "value": "ACME Ltda"},
                    ],
                },
                {"action_type": "move", "params_json": '{"folder_pattern": "{data}"}'},
            ],
        )

    Retorna o `id` do pipeline criado (a sessão é fechada ao final).
    """

    def _make(
        *,
        name: str = "Pipeline de teste",
        active: bool = True,
        steps: list[dict] | None = None,
    ) -> int:
        steps = steps or []
        with get_session(schema_engine) as session:
            pipeline = AutomationPipeline(name=name, active=active)
            for i, spec in enumerate(steps):
                step = PipelineStep(
                    position=spec.get("position", i),
                    action_type=spec["action_type"],
                    conjunction=spec.get("conjunction", "and"),
                    params_json=spec.get("params_json"),
                    active=spec.get("active", True),
                )
                for j, fspec in enumerate(spec.get("filters", [])):
                    step.filters.append(
                        StepFilter(
                            filter_type=fspec["filter_type"],
                            operator=fspec["operator"],
                            value=fspec["value"],
                            field_name=fspec.get("field_name"),
                            position=fspec.get("position", j),
                        )
                    )
                pipeline.steps.append(step)
            session.add(pipeline)
            session.commit()
            return pipeline.id

    return _make


@pytest.fixture
def src_dir(tmp_path: Path) -> Iterator[Path]:
    """Diretório de ORIGEM (mesmo volume do destino — rename atômico funciona)."""
    d = tmp_path / "src"
    d.mkdir()
    yield d


@pytest.fixture
def dst_dir(tmp_path: Path) -> Iterator[Path]:
    """Diretório de DESTINO (mesmo volume da origem)."""
    d = tmp_path / "dst"
    d.mkdir()
    yield d
