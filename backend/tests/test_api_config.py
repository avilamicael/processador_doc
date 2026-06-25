"""API de config — limiar global de confiança (REV-02 / D-03).

Cobre GET/PUT /config/review-threshold:
- GET reflete o valor efetivo de get_settings()
- PUT persiste no .env (tmp_path, sem poluir o .env real) e GET seguinte reflete
- PUT fora de [0.0, 1.0] → 422 (validação Pydantic)
- PUT limpa o lru_cache de get_settings (novo valor lido sem reiniciar)

Usa um `.env` temporário via monkeypatch de `config.env_file_path` e limpa o cache
de `get_settings` no setup/teardown para isolamento total.
"""

import warnings
from collections.abc import Iterator
from pathlib import Path

import pytest

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient

from app import config
from app.main import app


@pytest.fixture
def env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Aponta o `.env` de persistência para um arquivo temporário isolado.

    Monkeypatcha `config.env_file_path` (ponto único usado por `persist_env_setting`)
    e força o `Settings` a NÃO ler o `.env` real, alimentando o limiar via env var
    quando o teste o definir. Limpa o cache de `get_settings` em volta.
    """
    env = tmp_path / ".env"
    monkeypatch.setattr(config, "env_file_path", lambda: env)
    # Garante que o Settings não leia um .env real do CWD durante os testes:
    # apontamos o env_file do model_config para o tmp também.
    monkeypatch.setitem(config.Settings.model_config, "env_file", str(env))
    monkeypatch.delenv("REVIEW_CONFIDENCE_THRESHOLD", raising=False)
    monkeypatch.delenv("APPROVAL_MODE_ENABLED", raising=False)
    config.get_settings.cache_clear()
    yield env
    config.get_settings.cache_clear()


@pytest.fixture
def client(env_file: Path) -> Iterator[TestClient]:
    test_client = TestClient(app)
    yield test_client


def test_get_returns_effective_threshold(client: TestClient) -> None:
    """GET reflete o default (0.8) quando nada foi persistido."""
    resp = client.get("/config/review-threshold")
    assert resp.status_code == 200, resp.text
    assert resp.json()["threshold"] == 0.8


def test_put_persists_and_get_reflects(client: TestClient, env_file: Path) -> None:
    """PUT 0.7 persiste no .env; GET seguinte reflete 0.7 (cache invalidado)."""
    put = client.put("/config/review-threshold", json={"threshold": 0.7})
    assert put.status_code == 200, put.text
    assert put.json()["threshold"] == 0.7

    # Persistido no .env temporário.
    assert "REVIEW_CONFIDENCE_THRESHOLD=0.7" in env_file.read_text(encoding="utf-8")

    # GET seguinte lê o novo valor (cache foi limpo no PUT).
    get = client.get("/config/review-threshold")
    assert get.status_code == 200
    assert get.json()["threshold"] == 0.7


def test_put_out_of_range_returns_422(client: TestClient) -> None:
    """PUT com threshold > 1.0 → 422 (faixa Pydantic ge=0 le=1); nada persistido."""
    resp = client.put("/config/review-threshold", json={"threshold": 1.5})
    assert resp.status_code == 422, resp.text


def test_put_negative_returns_422(client: TestClient) -> None:
    """PUT com threshold < 0.0 → 422."""
    resp = client.put("/config/review-threshold", json={"threshold": -0.1})
    assert resp.status_code == 422, resp.text


def test_put_replaces_existing_key(client: TestClient, env_file: Path) -> None:
    """PUT sucessivos substituem a linha (não duplicam a chave no .env)."""
    client.put("/config/review-threshold", json={"threshold": 0.6})
    client.put("/config/review-threshold", json={"threshold": 0.9})

    content = env_file.read_text(encoding="utf-8")
    assert content.count("REVIEW_CONFIDENCE_THRESHOLD=") == 1
    assert "REVIEW_CONFIDENCE_THRESHOLD=0.9" in content

    get = client.get("/config/review-threshold")
    assert get.json()["threshold"] == 0.9


# --- Modo de aprovação (Fase 12, D-05) — espelha o par ai-fallback/review-threshold ---


def test_approval_mode_get_default_false(client: TestClient) -> None:
    """GET reflete o default (False) quando nada foi persistido (D-04 OFF)."""
    resp = client.get("/config/approval-mode")
    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled"] is False


def test_approval_mode_put_persists_and_get_reflects(
    client: TestClient, env_file: Path
) -> None:
    """PUT True persiste no .env; GET seguinte reflete True (cache invalidado)."""
    put = client.put("/config/approval-mode", json={"enabled": True})
    assert put.status_code == 200, put.text
    assert put.json()["enabled"] is True

    assert "APPROVAL_MODE_ENABLED=True" in env_file.read_text(encoding="utf-8")

    get = client.get("/config/approval-mode")
    assert get.status_code == 200
    assert get.json()["enabled"] is True


def test_approval_mode_put_non_bool_returns_422(client: TestClient) -> None:
    """PUT com enabled não-bool → 422 (validação Pydantic); nada persistido."""
    resp = client.put("/config/approval-mode", json={"enabled": "talvez"})
    assert resp.status_code == 422, resp.text


def test_approval_mode_put_replaces_existing_key(
    client: TestClient, env_file: Path
) -> None:
    """PUT sucessivos substituem a linha (não duplicam a chave no .env)."""
    client.put("/config/approval-mode", json={"enabled": True})
    client.put("/config/approval-mode", json={"enabled": False})

    content = env_file.read_text(encoding="utf-8")
    assert content.count("APPROVAL_MODE_ENABLED=") == 1
    assert "APPROVAL_MODE_ENABLED=False" in content

    get = client.get("/config/approval-mode")
    assert get.json()["enabled"] is False
