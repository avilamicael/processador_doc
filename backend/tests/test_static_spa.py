"""Mount estático do frontend + fallback SPA (quick 260622-ebo).

Prova que servir `frontend/dist` num único processo (single-origin) NÃO quebra a
API nem o `/health`, e que deep-links de SPA caem no `index.html` em vez de 404.

Padrão reusado de `tests/test_api_documents.py`:
- `from app.main import app`
- fixture `client` seta `app.state.engine = schema_engine` e instancia
  `TestClient(app)` SEM `with` (o lifespan NÃO roda — watcher/worker não sobem).

O serviço do frontend é resolvido POR REQUISIÇÃO a partir de
`app.main.FRONTEND_DIST` (não no import), então os testes apontam essa variável
para um `dist` temporário com `monkeypatch` — provando o comportamento de forma
determinística mesmo num checkout limpo onde `frontend/dist` é git-ignored/ausente.

Independentemente de o `dist` existir ou não, `/health` e `/documents` SEMPRE
respondem como API (nunca `index.html`) — é o que garante a não-quebra.
"""

import warnings
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient

from app import main as app_main
from app.main import app


@pytest.fixture
def client(schema_engine: Engine) -> Iterator[TestClient]:
    previous = getattr(app.state, "engine", None)
    app.state.engine = schema_engine
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.state.engine = previous


@pytest.fixture
def fake_dist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Cria um `frontend/dist` mínimo e aponta `FRONTEND_DIST` para ele.

    Estrutura idêntica à de um build Vite:
      dist/index.html
      dist/assets/app.js
      dist/vite.svg
    """
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><html><body><div id=root></div></body></html>",
        encoding="utf-8",
    )
    (dist / "assets" / "app.js").write_text("console.log('app')", encoding="utf-8")
    (dist / "vite.svg").write_text("<svg></svg>", encoding="utf-8")
    monkeypatch.setattr(app_main, "FRONTEND_DIST", dist)
    return dist


# --- API/health intactos COM e SEM dist (prova de não-quebra) ---------------


def test_health_ok_independente_de_dist(client: TestClient) -> None:
    """/health responde 200 com o corpo esperado — sem depender do dist."""
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert "version" in body


def test_documents_responde_api_nao_indexhtml(
    client: TestClient, fake_dist: Path
) -> None:
    """/documents segue para o router (JSON da API), NÃO o index.html do SPA,
    mesmo com o dist presente (o catch-all não pode capturar prefixos de API)."""
    resp = client.get("/documents")
    assert resp.status_code == 200
    ctype = resp.headers["content-type"]
    assert "application/json" in ctype
    assert "<html" not in resp.text.lower()


# --- Frontend servido quando dist existe ------------------------------------


def test_raiz_serve_index_html(client: TestClient, fake_dist: Path) -> None:
    """GET / serve o index.html do frontend/dist quando ele existe."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "<html" in resp.text.lower()
    assert 'id=root' in resp.text


def test_deep_link_spa_serve_index_html(client: TestClient, fake_dist: Path) -> None:
    """GET /documentos (deep-link sem arquivo correspondente) -> index.html, não 404."""
    resp = client.get("/documentos")
    assert resp.status_code == 200
    assert "<html" in resp.text.lower()


def test_asset_existente_servido_real(client: TestClient, fake_dist: Path) -> None:
    """GET /assets/<arquivo> serve o asset real, não o index.html."""
    resp = client.get("/assets/app.js")
    assert resp.status_code == 200
    assert "console.log" in resp.text
    assert "<html" not in resp.text.lower()


def test_arquivo_raiz_existente_servido_real(
    client: TestClient, fake_dist: Path
) -> None:
    """Arquivo existente na raiz do dist (ex.: vite.svg) é servido, não o index."""
    resp = client.get("/vite.svg")
    assert resp.status_code == 200
    assert "<svg" in resp.text


def test_path_traversal_cai_no_index(client: TestClient, fake_dist: Path) -> None:
    """Tentativa de sair do dist NÃO vaza arquivo do sistema; cai no index.html."""
    resp = client.get("/..%2f..%2fetc%2fpasswd")
    # Nunca 200 com conteúdo de /etc/passwd; ou cai no index (SPA) ou é rejeitado.
    assert "root:" not in resp.text


# --- Degradação quando dist ausente -----------------------------------------


def test_sem_dist_frontend_404_api_intacta(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem frontend/dist: rotas de frontend dão 404 (degradação), mas /health e
    /documents continuam respondendo como API (boot não crasha)."""
    ausente = tmp_path / "dist-inexistente"
    monkeypatch.setattr(app_main, "FRONTEND_DIST", ausente)

    assert client.get("/health").status_code == 200
    assert client.get("/documents").status_code == 200

    resp = client.get("/")
    assert resp.status_code == 404
    resp2 = client.get("/documentos")
    assert resp2.status_code == 404
