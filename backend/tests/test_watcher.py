"""Wave 0 skeleton — watcher de pasta monitorada (watchfiles).

Stub coletável: o watcher (`app/ingest/watcher.py`) que observa as pastas
monitoradas e emite candidatos ainda não existe; será implementado num plano
posterior da Fase 2. Import lazy do alvo futuro; teste skip.
"""

import pytest


@pytest.mark.skip(reason="Wave 0 stub — watcher implementado em plano posterior")
def test_watcher_emite_candidatos() -> None:
    from app.ingest import watcher  # noqa: F401  (lazy — alvo futuro)

    raise AssertionError("não implementado")
