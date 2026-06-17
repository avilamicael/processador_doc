"""Testes da função pura `compute_confidence` (Fase 5, REV-01 / D-01 / D-04).

A função é PURA (sem DB/IA) — usamos objetos leves (`SimpleNamespace`) com os
atributos mínimos consumidos: `.field_name`/`.valid` (campo preenchido) e
`.name`/`.required` (campo de template). Não há fixture de banco.
"""

from types import SimpleNamespace

from app.classification.confidence import compute_confidence


def _ff(field_name: str, valid: bool) -> SimpleNamespace:
    """Campo preenchido leve (FilledField-like)."""
    return SimpleNamespace(field_name=field_name, valid=valid)


def _tf(name: str, required: bool) -> SimpleNamespace:
    """Campo de template leve (TemplateField-like)."""
    return SimpleNamespace(name=name, required=required)


def test_sem_obrigatorios_retorna_perfeito() -> None:
    """Sem campos obrigatórios → (1.0, False): nada a revisar."""
    assert compute_confidence([], []) == (1.0, False)


def test_todos_obrigatorios_validos() -> None:
    """2 obrigatórios ambos válidos → (1.0, False)."""
    filled = [_ff("a", True), _ff("b", True)]
    template = [_tf("a", True), _tf("b", True)]
    assert compute_confidence(filled, template) == (1.0, False)


def test_metade_obrigatorios_invalidos() -> None:
    """2 obrigatórios, 1 válido 1 inválido → (0.5, True)."""
    filled = [_ff("a", True), _ff("b", False)]
    template = [_tf("a", True), _tf("b", True)]
    assert compute_confidence(filled, template) == (0.5, True)


def test_todos_obrigatorios_invalidos() -> None:
    """Todos obrigatórios inválidos → (0.0, True)."""
    filled = [_ff("a", False), _ff("b", False)]
    template = [_tf("a", True), _tf("b", True)]
    assert compute_confidence(filled, template) == (0.0, True)


def test_obrigatorio_ausente_conta_como_invalido() -> None:
    """Obrigatório AUSENTE em filled_fields conta como inválido (get default False)."""
    filled = [_ff("a", True)]  # "b" não está presente
    template = [_tf("a", True), _tf("b", True)]
    assert compute_confidence(filled, template) == (0.5, True)


def test_nao_obrigatorios_nao_afetam_score() -> None:
    """Campos NÃO obrigatórios (mesmo inválidos) não afetam score nem o flag."""
    filled = [_ff("a", True), _ff("opcional", False)]
    template = [_tf("a", True), _tf("opcional", False)]
    assert compute_confidence(filled, template) == (1.0, False)
