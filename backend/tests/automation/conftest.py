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

from app.models.automation import (
    Automation,
    AutomationAction,
    AutomationCondition,
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


# Fábrica que cria uma Automation com N condições + N ações; retorna o id.
AutomationFactory = Callable[..., int]


@pytest.fixture
def automation_factory(schema_engine: Engine) -> AutomationFactory:
    """Cria uma `Automation` persistida com 0..N `AutomationCondition` (combinadas
    por E) e 0..N `AutomationAction` ordenadas — base dos testes do stage (executor).

    Uso:
        aid = automation_factory(
            name="A1",
            position=0,
            conditions=[
                {"field": "field", "field_name": "cliente",
                 "operator": "eq", "value": "ACME Ltda"},
                {"field": "extension", "operator": "eq", "value": ".pdf"},
            ],
            actions=[
                {"action_type": "rename",
                 "params_json": '{"name_pattern": "{cliente}_{numero}"}'},
                {"action_type": "move",
                 "params_json": '{"dest_folder": "{data}"}'},
            ],
        )

    Retorna o `id` da automação criada (a sessão é fechada ao final).
    """

    def _make(
        *,
        name: str = "Automação de teste",
        active: bool = True,
        position: int = 0,
        conditions: list[dict] | None = None,
        actions: list[dict] | None = None,
    ) -> int:
        conditions = conditions or []
        actions = actions or []
        with get_session(schema_engine) as session:
            automation = Automation(name=name, active=active, position=position)
            for i, cspec in enumerate(conditions):
                automation.conditions.append(
                    AutomationCondition(
                        field=cspec["field"],
                        operator=cspec["operator"],
                        value=cspec["value"],
                        field_name=cspec.get("field_name"),
                        position=cspec.get("position", i),
                    )
                )
            for i, aspec in enumerate(actions):
                automation.actions.append(
                    AutomationAction(
                        position=aspec.get("position", i),
                        action_type=aspec["action_type"],
                        params_json=aspec.get("params_json"),
                    )
                )
            session.add(automation)
            session.commit()
            return automation.id

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
