"""API de templates — CRUD schema-first (Fase 4, TPL-01).

Router fino (`/templates`) que a UI (Plano 06) usa para o construtor de templates:
criar/listar/editar/remover templates com seus **campos a extrair** aninhados e os
**sinais identificadores** (D-02). Espelha exatamente o padrão de
`api/watched_folders.py`: schemas `In`/`Patch`/`Out` Pydantic, `request.app.state.engine`
+ `with get_session(engine)`, `IntegrityError → 409`, `404` em ausente, `204` no DELETE.

Um `Template` tem `name` único (rótulo), `doc_type` LEGADO/opcional (coluna dormente,
fora do form — D-T5), `signals` (sinais identificadores como GRUPOS E/OU de condições
`{mode, value}` — D-T2 — persistidos como JSON em `signals_json`) e uma lista de
`fields` (cada `TemplateField`: name/field_type/required/regex/hint).
Criar/editar persiste Template + TemplateField num único commit (atomicidade).

A forma canônica de `signals` é uma lista de GRUPOS; cada grupo é uma lista de
condições `SignalConditionIn` (`mode: Literal["texto","regex"]`, `value: str`). O
matcher (Plano 01) avalia OU entre grupos e E dentro do grupo. `_loads_signals_groups`
lê de volta de forma forward-compatible (a forma plana legada `list[str]` é normalizada
para 1 grupo OU por termo) — sincronizada com `matcher._parse_groups`.

SEGURANÇA — regex do operador (T-04-10): a `regex` de validação de campo E a `value`
em modo `regex` de uma condição de sinal são guardadas APENAS como string aqui; este
endpoint NÃO compila nem executa nenhuma regex. O modo inválido é rejeitado com 422
pelo `Literal` (dispatch por etiqueta, sem `eval` — V5/T-06.1-07).
A aplicação segura (`re.fullmatch` + limite de tamanho) é responsabilidade do Plano
de validação (04-02) — não há ReDoS no caminho HTTP. Não adicionar `re.compile`/
`re.fullmatch` neste módulo.

SEGURANÇA — SQL injection (T-04-09): todo acesso é via ORM SQLAlchemy parametrizado;
nenhuma string-building de SQL. `template_id` é tipado `int` na rota.

DELETE remove só o template — documentos já classificados permanecem (D-03): a FK
`classification_results.template_id` é `ON DELETE SET NULL`, então o histórico de
classificação sobrevive; novos documentos apenas deixam de casar com este template.
"""

import json
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.template import Template, TemplateField
from app.storage.db import get_session

router = APIRouter(prefix="/templates", tags=["templates"])


def _loads_signals_groups(raw: str | None) -> list[list[dict]]:
    """Lê `signals_json` como lista de GRUPOS de condições (forward-compatible).

    Réplica EXATA de `classification.matcher._parse_groups` — o endpoint e o matcher
    são DOIS pontos que devem ficar sincronizados na mesma forma canônica de
    `signals_json` (grupos E/OU de condições `{mode, value}`, D-T2). Tolerante a:
    - JSON inválido/ausente → [] (T-06.1-03 / T-06.1-08: nunca propaga erro);
    - forma legada plana `list[str]` → cada termo vira `[{"mode":"texto","value":s}]`
      (1 grupo OU por termo, preserva "qualquer termo basta");
    - forma de grupos `list[list[dict]]` → normaliza mantendo só os `dict`.

    NÃO compila/executa regex aqui (T-04-10) — só lê e normaliza a estrutura.
    """
    try:
        parsed = json.loads(raw or "[]")
    except (ValueError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []

    # Forma legada plana: lista de strings → 1 grupo OU por termo.
    if parsed and all(isinstance(item, str) for item in parsed):
        return [[{"mode": "texto", "value": item}] for item in parsed]

    # Forma de grupos: lista de listas de condições (dict).
    groups: list[list[dict]] = []
    for group in parsed:
        if isinstance(group, list):
            groups.append([cond for cond in group if isinstance(cond, dict)])
    return groups


class SignalConditionIn(BaseModel):
    """Uma condição de sinal: etiqueta de modo + valor (D-T2).

    `mode` é um `Literal["texto","regex"]` — o dispatch por etiqueta no Pydantic dá
    422 limpo em modo desconhecido, sem `eval` (V5/T-06.1-07). A `value` é guardada
    APENAS como STRING; este endpoint NÃO compila nem executa a regex (T-04-10) — a
    avaliação segura vive no matcher (Plano 01) com tetos ReDoS.
    """

    mode: Literal["texto", "regex"] = "texto"
    value: str

    @field_validator("value")
    @classmethod
    def _value_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Informe o valor da condição.")
        return v.strip()


class SignalConditionOut(BaseModel):
    """Espelho de resposta de uma condição de sinal."""

    mode: str
    value: str


class TemplateFieldIn(BaseModel):
    """Campo a extrair declarado no construtor (D-08/D-09).

    `regex` é guardada como string — NÃO compilada/executada aqui (T-04-10).
    """

    name: str
    field_type: str = "texto"
    required: bool = False
    regex: str | None = None
    hint: str | None = None

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Informe o nome do campo.")
        return v.strip()


class TemplateIn(BaseModel):
    """Body de criação de template: nome + sinais (grupos E/OU) + ≥1 campo.

    `signals` é uma lista de GRUPOS; cada grupo é uma lista de condições
    `SignalConditionIn` (D-T2). Semântica booleana no matcher: OU entre grupos, E
    dentro do grupo. `doc_type` é LEGADO/OPCIONAL — o form do Plano 03 não o alimenta
    mais (D-T5); a coluna permanece dormente, aceita aqui só por compatibilidade.
    """

    name: str
    doc_type: str | None = None  # legado/opcional (D-T5): coluna dormente, fora do form.
    signals: list[list[SignalConditionIn]] = []
    fields: list[TemplateFieldIn] = []

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Informe o nome do template.")
        return v.strip()

    @field_validator("fields")
    @classmethod
    def _at_least_one_field(cls, v: list[TemplateFieldIn]) -> list[TemplateFieldIn]:
        if not v:
            raise ValueError("Adicione ao menos um campo ao template.")
        return v


class TemplatePatch(BaseModel):
    """Body de edição parcial de template (todos opcionais).

    Quando `fields` é informado, SUBSTITUI a coleção inteira de campos. Quando
    omitido (`None`), os campos atuais são preservados.
    """

    name: str | None = None
    doc_type: str | None = None  # legado/opcional (D-T5): coluna dormente.
    signals: list[list[SignalConditionIn]] | None = None
    fields: list[TemplateFieldIn] | None = None

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Informe o nome do template.")
        return v.strip() if v is not None else v

    @field_validator("fields")
    @classmethod
    def _at_least_one_field(
        cls, v: list[TemplateFieldIn] | None
    ) -> list[TemplateFieldIn] | None:
        if v is not None and not v:
            raise ValueError("Adicione ao menos um campo ao template.")
        return v


class TemplateFieldOut(BaseModel):
    """Representação de resposta de um campo do template."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    field_type: str
    required: bool
    regex: str | None
    hint: str | None


class TemplateOut(BaseModel):
    """Representação de resposta de um template com campos aninhados."""

    id: int
    name: str
    doc_type: str | None
    signals: list[list[SignalConditionOut]]
    fields: list[TemplateFieldOut]
    created_at: datetime
    updated_at: datetime


def _serialize(template: Template) -> TemplateOut:
    """Converte um `Template` ORM (com fields carregados) no schema de saída.

    Desserializa `signals_json` → grupos de condições (forward-compatible: lê a forma
    plana legada sem erro); os campos vêm via `from_attributes`.
    """
    return TemplateOut(
        id=template.id,
        name=template.name,
        doc_type=template.doc_type,
        signals=[
            [
                SignalConditionOut(
                    mode=str(c.get("mode", "texto")), value=str(c.get("value", ""))
                )
                for c in group
            ]
            for group in _loads_signals_groups(template.signals_json)
        ],
        fields=[TemplateFieldOut.model_validate(f) for f in template.fields],
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


def _dump_signals(signals: list[list[SignalConditionIn]]) -> str:
    """Serializa os grupos de condições Pydantic → JSON `[[{mode,value},...],...]`.

    MESMA forma de grupos que `matcher._parse_groups` consome (seam sincronizado).
    """
    return json.dumps([[c.model_dump() for c in group] for group in signals])


def _apply_fields(template: Template, fields: list[TemplateFieldIn]) -> None:
    """Substitui a coleção de campos do template (delete-orphan cuida do resto)."""
    template.fields = [
        TemplateField(
            name=f.name,
            field_type=f.field_type,
            required=f.required,
            regex=f.regex,
            hint=f.hint,
        )
        for f in fields
    ]


@router.get("", response_model=list[TemplateOut])
def list_templates(request: Request) -> list[TemplateOut]:
    """Lista todos os templates cadastrados (com campos aninhados)."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        templates = session.scalars(select(Template).order_by(Template.id)).all()
        return [_serialize(t) for t in templates]


@router.get("/{template_id}", response_model=TemplateOut)
def get_template(request: Request, template_id: int) -> TemplateOut:
    """Detalhe de um template; 404 se ausente."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        template = session.get(Template, template_id)
        if template is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"template {template_id} não encontrado",
            )
        return _serialize(template)


@router.post("", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
def create_template(request: Request, body: TemplateIn) -> TemplateOut:
    """Cria um template + campos num único commit; name duplicado → 409."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        template = Template(
            name=body.name,
            doc_type=body.doc_type,
            signals_json=_dump_signals(body.signals),
        )
        _apply_fields(template, body.fields)
        session.add(template)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"template já cadastrado com o nome: {body.name}",
            ) from exc
        session.refresh(template)
        return _serialize(template)


@router.patch("/{template_id}", response_model=TemplateOut)
def update_template(request: Request, template_id: int, body: TemplatePatch) -> TemplateOut:
    """Edita nome/tipo/sinais/campos; ao trocar `fields`, substitui a coleção. 404 se ausente."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        template = session.get(Template, template_id)
        if template is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"template {template_id} não encontrado",
            )
        if body.name is not None:
            template.name = body.name
        if body.doc_type is not None:
            template.doc_type = body.doc_type
        if body.signals is not None:
            template.signals_json = _dump_signals(body.signals)
        if body.fields is not None:
            _apply_fields(template, body.fields)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="template já cadastrado com este nome",
            ) from exc
        session.refresh(template)
        return _serialize(template)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(request: Request, template_id: int) -> None:
    """Remove o template. Documentos já classificados permanecem (D-03, SET NULL)."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        template = session.get(Template, template_id)
        if template is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"template {template_id} não encontrado",
            )
        session.delete(template)
        session.commit()
