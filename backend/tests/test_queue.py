"""Wave 0 skeleton — fila durável in-process (SQLite) (PROC-02/PROC-03).

Stub coletável: o repositório de fila (`app/storage/queue_repo.py`) com
enqueue/claim atômico ainda não existe; será implementado num plano posterior da
Fase 2. Import lazy do alvo futuro; teste skip.
"""

import pytest


@pytest.mark.skip(reason="Wave 0 stub — fila implementada em plano posterior")
def test_queue_claim_atomico() -> None:
    from app.storage import queue_repo  # noqa: F401  (lazy — alvo futuro)

    raise AssertionError("não implementado")
