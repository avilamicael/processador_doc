"""Wave 0 skeleton — gate de deduplicação pré-split (D-09).

Stub coletável: o gate de dedup (sobre `ingested_originals.original_hash`) é
exercitado pelo `pipeline/ingest_stage.py`, implementado num plano posterior da
Fase 2. Import lazy do alvo futuro; teste skip.
"""

import pytest


@pytest.mark.skip(reason="Wave 0 stub — dedup gate implementado em plano posterior")
def test_dedup_gate_rejeita_original_repetido() -> None:
    from app.pipeline import ingest_stage  # noqa: F401  (lazy — alvo futuro)

    raise AssertionError("não implementado")
