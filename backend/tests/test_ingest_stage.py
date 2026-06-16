"""Wave 0 skeleton — orquestração de ingestão (dedup → CAS → split → Document).

Stub coletável: o estágio de ingestão (`app/pipeline/ingest_stage.py`) ainda não
existe; compõe gate de dedup, CAS e máquina de estados num plano posterior da
Fase 2. Import lazy do alvo futuro; teste skip.
"""

import pytest


@pytest.mark.skip(reason="Wave 0 stub — ingest_stage implementado em plano posterior")
def test_ingest_stage_cria_documentos_por_bloco() -> None:
    from app.pipeline import ingest_stage  # noqa: F401  (lazy — alvo futuro)

    raise AssertionError("não implementado")
