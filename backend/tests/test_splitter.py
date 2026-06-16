"""Wave 0 skeleton — separação de PDF em blocos (pikepdf).

Stub coletável: o splitter (`app/ingest/splitter.py`) ainda não existe; será
implementado num plano posterior da Fase 2 (separação por `pages_per_block`).
Import do alvo futuro é lazy; teste skip para nunca falhar a coleta.
"""

import pytest


@pytest.mark.skip(reason="Wave 0 stub — splitter implementado em plano posterior")
def test_splitter_separa_por_bloco() -> None:
    from app.ingest import splitter  # noqa: F401  (lazy — alvo futuro)

    raise AssertionError("não implementado")
