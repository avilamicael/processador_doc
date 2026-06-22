---
phase: quick-260622-ebo
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/app/main.py
  - backend/tests/test_static_spa.py
  - instalar.ps1
  - atualizar.ps1
  - INSTALL-WINDOWS.md
autonomous: true
requirements: [INSTALL-WIN]
must_haves:
  truths:
    - "GET /health continua retornando 200 com {status, db, version} apos o mount estatico"
    - "Todas as rotas de API (/documents, /watched-folders, /rescan, /templates, /automations, /config) continuam respondendo (nao capturadas pelo catch-all)"
    - "GET / serve o index.html do frontend/dist quando ele existe"
    - "Deep-link de SPA (ex.: GET /documentos) serve index.html em vez de 404"
    - "Boot do app NAO crasha quando frontend/dist esta ausente (degrada com aviso)"
    - "instalar.ps1 instala/verifica Python+uv, roda uv sync, garante .env, aplica alembic upgrade head e sobe uvicorn com 1 worker em http://localhost:8000"
    - "atualizar.ps1 atualiza codigo + deps + schema preservando os dados em %ProgramData%\\ProcessadorDocumentos"
    - "INSTALL-WINDOWS.md descreve instalacao, configuracao da OPENAI_API_KEY, acesso, atualizacao e troubleshooting em PT-BR"
  artifacts:
    - path: "backend/app/main.py"
      provides: "Mount StaticFiles do frontend/dist + fallback SPA, depois dos routers"
      contains: "StaticFiles"
    - path: "backend/tests/test_static_spa.py"
      provides: "Teste do mount estatico + fallback SPA sem quebrar API/health"
      contains: "def test_"
    - path: "instalar.ps1"
      provides: "Instalador idempotente Windows (PowerShell, PT-BR)"
      min_lines: 40
    - path: "atualizar.ps1"
      provides: "Atualizador preservando dados (PowerShell, PT-BR)"
      min_lines: 25
    - path: "INSTALL-WINDOWS.md"
      provides: "Guia de instalacao Windows passo a passo (PT-BR)"
      min_lines: 60
  key_links:
    - from: "backend/app/main.py"
      to: "frontend/dist"
      via: "Path resolvido relativo a raiz do repo (nao ao CWD)"
      pattern: "frontend.*dist"
    - from: "instalar.ps1"
      to: "uvicorn app.main:app"
      via: "uv run uvicorn ... --workers 1"
      pattern: "uvicorn"
---

<objective>
Permitir instalar e rodar o Processador de Documentos no Windows via script Python+uv,
servindo backend e frontend num unico processo (single-origin) em http://localhost:8000.

Purpose: O motor (Fases 1-6.2) esta completo, mas nao ha forma de instalar/validar o
sistema na maquina do dev e depois em 1 cliente piloto. A decisao de empacotamento ja foi
tomada pelo usuario: script de instalacao Python+uv (nao PyInstaller, nao Docker).

Output:
- backend/app/main.py passa a servir frontend/dist com fallback SPA (sem quebrar API/health)
- backend/tests/test_static_spa.py prova o comportamento
- instalar.ps1, atualizar.ps1, INSTALL-WINDOWS.md na raiz do repo
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md

<interfaces>
<!-- Contratos extraidos do codigo. O executor usa estes diretamente - sem explorar a base. -->

backend/app/main.py (estado ATUAL - referencia):
- app = FastAPI(title=..., version=__version__, lifespan=lifespan)
- Routers ja incluidos NESTA ordem (linhas 81-85):
  watched_folders_api.router, documents_api.router, templates_api.router,
  config_api.router, automations_api.router
- @app.get("/health") retorna {"status": "ok", "db": "ok", "version": __version__}
- O lifespan sobe watcher+worker como asyncio.Task (1 worker uvicorn obrigatorio).

Prefixos de rota de API que o catch-all NAO pode capturar:
  /documents, /watched-folders, /rescan, /templates, /automations, /config, /health
(a fonte canonica da lista de prefixos da API e o proxy em frontend/vite.config.ts.)

backend/tests/conftest.py + tests/test_api_documents.py (padrao de teste a reusar):
- from app.main import app
- fixture client: seta app.state.engine = schema_engine; TestClient(app) e instanciado
  SEM `with` (lifespan NAO e executado) -> o mount estatico DEVE ser montado em tempo de
  import (na criacao do app), nao dentro do lifespan.
- TestClient vem de fastapi.testclient. schema_engine e fixture do conftest.

frontend/package.json: build via `npm run build` (tsc -b && vite build) -> gera frontend/dist.
IMPORTANTE: frontend/dist esta GIT-IGNORED (nao versionado, confirmado via git check-ignore).
Numa checkout limpa a pasta pode nao existir - por isso o mount precisa degradar quando
ausente, o instalador precisa builda-la (se Node disponivel) e o guia precisa documentar
`npm run build`. Os bundles Vite ficam em frontend/dist/assets/.

backend/app/config.py: data_dir -> %ProgramData%\ProcessadorDocumentos no Windows; banco
SQLite derivado ali. Esta pasta e onde vivem os dados do cliente (nao tocados pelo update).
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Servir frontend/dist com fallback SPA em main.py</name>
  <files>backend/app/main.py, backend/tests/test_static_spa.py</files>
  <behavior>
    - GET /health -> 200 com {"status","db","version"} (inalterado).
    - GET /documents (e demais prefixos de API) -> NAO retorna index.html; segue para o router.
    - GET / -> 200 servindo index.html quando frontend/dist existe.
    - GET /documentos (deep-link de SPA inexistente como arquivo) -> 200 servindo index.html (nao 404).
    - GET /assets/<arquivo-existente> -> 200 com o asset real (nao index.html).
    - Quando frontend/dist NAO existe: o app importa/boota sem excecao; rotas de API e /health
      seguem funcionando; rotas de frontend retornam 404 (degradacao aceitavel).
  </behavior>
  <action>
    Adicionar, em backend/app/main.py, o servico do frontend buildado APOS todos os
    include_router e APOS o @app.get("/health") (ordem importa: rotas de API e health
    registradas antes; estatico/catch-all por ultimo).

    Resolucao robusta do caminho (nao depender do CWD): derivar frontend/dist a partir de
    Path(__file__).resolve(). __file__ = backend/app/main.py -> raiz do repo e parents[2];
    o dist e repo_root / "frontend" / "dist". Computar uma vez em nivel de modulo, por ex.
    FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist".

    Montar SOMENTE se FRONTEND_DIST.is_dir(). Se nao existir, NAO montar e emitir aviso claro
    via logging (ou warnings.warn) em PT-BR, ex.: "frontend/dist ausente - UI nao sera
    servida; rode 'npm run build' no frontend". NAO levantar excecao (boot nao pode crashar;
    caso comum em dev/CI).

    Abordagem do fallback SPA (escolher a mais simples e robusta e documentar no docstring):
    1. app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")
       - serve os bundles JS/CSS de Vite (vivem em dist/assets/).
    2. Um handler catch-all @app.get("/{full_path:path}") registrado POR ULTIMO que:
       - serve FRONTEND_DIST / full_path com FileResponse se for arquivo existente DENTRO de
         dist (ex.: favicon, vite.svg);
       - caso contrario retorna FileResponse(FRONTEND_DIST / "index.html") (fallback SPA).
       Como este handler e registrado por ultimo e os routers de API + /health ja estao
       registrados antes, o FastAPI casa as rotas de API primeiro; o catch-all so pega o resto.
       NAO usar app.mount("/", StaticFiles(html=True)) para o deep-link: html=True serve
       index.html so na raiz e da 404 em subcaminhos inexistentes (quebra deep-links de SPA).
    Confinar o full_path a dentro de dist (rejeitar path traversal): resolver o caminho e
    checar is_relative_to(FRONTEND_DIST.resolve()) antes de servir arquivo existente; fora ->
    cair no index.html.

    Imports novos: from pathlib import Path; from fastapi.responses import FileResponse;
    from fastapi.staticfiles import StaticFiles; e logging/warnings para o aviso.

    Escrever backend/tests/test_static_spa.py reusando o padrao de tests/test_api_documents.py:
    from app.main import app; fixture que seta app.state.engine = schema_engine (do conftest) e
    TestClient(app). Cobrir os casos do bloco <behavior>. Para "dist ausente": como o mount e
    decidido no import, condicionar os testes de frontend com
    pytest.mark.skipif(not FRONTEND_DIST.is_dir(), ...) e SEMPRE testar que /health e /documents
    respondem independentemente do dist - assim o teste prova a nao-quebra da API com e sem dist.
  </action>
  <verify>
    <automated>cd backend && uv run pytest tests/test_static_spa.py tests/test_api_documents.py -x -q</automated>
  </verify>
  <done>Testes passam: /health e API intactos; / e deep-link servem index.html quando dist existe; boot nao crasha sem dist.</done>
</task>

<task type="auto">
  <name>Task 2: Scripts PowerShell instalar.ps1 e atualizar.ps1 (PT-BR)</name>
  <files>instalar.ps1, atualizar.ps1</files>
  <action>
    Criar instalar.ps1 na RAIZ do repo - instalador idempotente para Windows, mensagens em
    PT-BR, $ErrorActionPreference = 'Stop' e tratamento de erro com mensagens acionaveis:
    1. Verificar Python 3.12: se ausente, instruir/instalar via winget
       (winget install --id Python.Python.3.12) com fallback de instrucao manual.
    2. Verificar uv: se ausente, instalar via instalador oficial
       (irm https://astral.sh/uv/install.ps1 | iex); reavaliar PATH na sessao apos instalar.
    3. uv sync no projeto backend (uv sync --project backend, ou Push-Location backend).
    4. Garantir .env: se backend/.env nao existir, copiar de backend/.env.example e AVISAR em
       destaque para preencher OPENAI_API_KEY. NUNCA logar/exibir o valor da chave.
    5. (Frontend) Se frontend/dist nao existir E Node disponivel, rodar npm ci + npm run build
       em frontend/ para gerar o dist. Se Node ausente, avisar (PT-BR) que a UI nao sera
       servida ate buildar e apontar o INSTALL-WINDOWS.md. NAO falhar a instalacao por isso
       (a API funciona sem dist).
    6. uv run --project backend alembic upgrade head (aplica/atualiza schema; idempotente).
    7. Subir o servidor:
       uv run --project backend uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
       - comentar no script que --workers 1 e OBRIGATORIO (lifespan sobe watcher+worker como
       asyncio.Task; >1 worker duplicaria e causaria contencao de escrita no SQLite single-writer).
       Imprimir antes: "Abra http://localhost:8000 no navegador".
    Idempotencia: rodar 2x nao deve quebrar (checagens condicionais antes de instalar; uv sync
    e alembic upgrade ja sao idempotentes).

    Criar atualizar.ps1 na RAIZ - atualiza a instancia preservando dados, PT-BR,
    $ErrorActionPreference = 'Stop':
    1. git pull (se for repo git) OU instrucao clara de como copiar os arquivos novos.
    2. uv sync --project backend.
    3. (Frontend) rebuildar dist se Node disponivel (mesma logica do instalar).
    4. uv run --project backend alembic upgrade head.
    5. Reiniciar o uvicorn (mesma linha do passo 7 do instalar, --workers 1).
    DEIXAR EXPLICITO (banner PT-BR) que os dados do cliente - banco SQLite, CAS, templates e
    config - vivem em %ProgramData%\ProcessadorDocumentos e NAO sao tocados pela atualizacao
    (o codigo e separado dos dados; Alembic migra o schema preservando o conteudo).
  </action>
  <verify>
    <automated>grep -q 'workers 1' instalar.ps1 && grep -q 'alembic upgrade head' instalar.ps1 && grep -q '.env.example' instalar.ps1 && grep -q 'ProgramData' atualizar.ps1 && grep -q 'alembic upgrade head' atualizar.ps1 && echo OK</automated>
  </verify>
  <done>Ambos os scripts existem na raiz; instalar.ps1 cobre Python/uv/sync/.env/migracao/uvicorn --workers 1; atualizar.ps1 preserva %ProgramData% e roda upgrade head.</done>
</task>

<task type="auto">
  <name>Task 3: Guia INSTALL-WINDOWS.md (PT-BR)</name>
  <files>INSTALL-WINDOWS.md</files>
  <action>
    Criar INSTALL-WINDOWS.md na RAIZ do repo, em PT-BR, passo a passo:
    1. Pre-requisitos: Windows; (opcional) Node 20.19+/22.12+ para buildar o frontend.
       Explicar que instalar.ps1 cuida de Python 3.12 e uv automaticamente.
    2. Como rodar instalar.ps1: abrir PowerShell na pasta do projeto e executar .\instalar.ps1.
       Incluir o ajuste de ExecutionPolicy quando bloquear scripts, ex.:
       Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass (explicar que e por sessao).
    3. Configurar OPENAI_API_KEY: editar backend/.env (criado a partir de .env.example) e
       preencher OPENAI_API_KEY. Reforcar que o .env nunca e versionado e a chave e segredo.
    4. Acessar: abrir http://localhost:8000 no navegador.
    5. Atualizar: rodar .\atualizar.ps1; reforcar que os dados em
       %ProgramData%\ProcessadorDocumentos sao preservados.
    6. Troubleshooting (secao com cada caso e solucao):
       - Porta 8000 ocupada: como identificar/encerrar o processo ou trocar a porta no comando uvicorn.
       - ExecutionPolicy bloqueando: o comando Set-ExecutionPolicy do passo 2.
       - OPENAI_API_KEY ausente/invalida: onde definir no .env; sintoma (falha nas extracoes por IA).
       - frontend/dist faltando (UI nao carrega / 404 na raiz): como buildar -
         cd frontend; npm ci; npm run build; explicar que dist e gerado e git-ignored.
       - Onde ficam os dados e logs: %ProgramData%\ProcessadorDocumentos (banco SQLite app.db,
         CAS, etc.); separados do codigo, por isso a atualizacao e segura.
  </action>
  <verify>
    <automated>grep -qi 'ExecutionPolicy' INSTALL-WINDOWS.md && grep -q 'OPENAI_API_KEY' INSTALL-WINDOWS.md && grep -q 'ProgramData' INSTALL-WINDOWS.md && grep -q 'npm run build' INSTALL-WINDOWS.md && grep -q 'localhost:8000' INSTALL-WINDOWS.md && echo OK</automated>
  </verify>
  <done>INSTALL-WINDOWS.md cobre pre-requisitos, ExecutionPolicy, OPENAI_API_KEY no .env, acesso em localhost:8000, atualizacao preservando dados e troubleshooting (porta, dist faltando, dados/logs).</done>
</task>

</tasks>

<verification>
Apos as 3 tarefas, validar de ponta a ponta:
- cd backend && uv run pytest -q  (suite inteira passa; nenhuma rota de API quebrada pelo mount estatico)
- Boot manual: cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
  - curl http://127.0.0.1:8000/health  -> 200 {"status":"ok",...}
  - curl http://127.0.0.1:8000/documents -> resposta da API (nao index.html)
  - curl http://127.0.0.1:8000/  -> index.html do frontend (quando dist existe)
  - curl http://127.0.0.1:8000/documentos -> index.html (fallback SPA, nao 404)
- Sintaxe dos scripts: instalar.ps1 e atualizar.ps1 existem na raiz e contem os marcadores
  verificados nas tasks (workers 1, alembic upgrade head, .env.example, ProgramData).
</verification>

<success_criteria>
- main.py serve frontend/dist com fallback SPA SEM quebrar API/health, degradando sem crash quando dist ausente.
- backend/tests/test_static_spa.py prova o comportamento e passa junto com a suite existente.
- instalar.ps1 (idempotente), atualizar.ps1 (preserva %ProgramData%) e INSTALL-WINDOWS.md existem na raiz, em PT-BR.
- uvicorn sempre documentado/invocado com --workers 1.
- Nenhum segredo (OPENAI_API_KEY) e logado/exposto; .env nao versionado.
</success_criteria>

<output>
Criar .planning/quick/260622-ebo-criar-instalacao-windows-python-uv-servi/260622-ebo-SUMMARY.md quando concluido.
</output>
