"""Wave 0 skeleton — estabilizador de arquivo (quiescência antes de ingerir).

Stub coletável: o estabilizador (`app/ingest/stabilizer.py`) ainda não existe;
será implementado num plano posterior da Fase 2 (separação/ingestão). Esta
casca garante que o pytest colete o arquivo (Nyquist Rule) sem ImportError —
o import do alvo futuro é lazy (dentro da função) e o teste é skip.
"""

import pytest


@pytest.mark.skip(reason="Wave 0 stub — estabilizador implementado em plano posterior")
def test_stabilizer_quiescencia() -> None:
    from app.ingest import stabilizer  # noqa: F401  (lazy — alvo futuro)

    raise AssertionError("não implementado")
