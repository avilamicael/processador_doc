# instalar.ps1 — Instalador do Processador de Documentos (Windows)
#
# Instalador IDEMPOTENTE: rodar duas vezes não quebra (todas as checagens são
# condicionais; `uv sync` e `alembic upgrade head` já são idempotentes).
#
# O que faz:
#   1. Garante Python 3.12 (instala via winget se ausente).
#   2. Garante o uv (instalador oficial da Astral se ausente).
#   3. uv sync (instala as dependências do backend a partir do lockfile).
#   4. Garante backend\.env (copia de .env.example e avisa para preencher a chave).
#   5. (Opcional) Builda o frontend (npm) se Node estiver disponível.
#   6. alembic upgrade head (aplica/atualiza o schema do banco).
#   7. Sobe o servidor (uvicorn --workers 1) em http://localhost:8000.
#
# SEGREDO: a OPENAI_API_KEY NUNCA é lida, exibida nem logada por este script.

$ErrorActionPreference = 'Stop'

# Raiz do repositório = pasta deste script (não depende do diretório atual).
$RepoRoot    = $PSScriptRoot
$BackendDir  = Join-Path $RepoRoot 'backend'
$FrontendDir = Join-Path $RepoRoot 'frontend'
$EnvFile     = Join-Path $BackendDir '.env'
$EnvExample  = Join-Path $BackendDir '.env.example'
$DistDir     = Join-Path $FrontendDir 'dist'

function Write-Passo($texto) { Write-Host "`n==> $texto" -ForegroundColor Cyan }
function Write-Aviso($texto) { Write-Host "[AVISO] $texto" -ForegroundColor Yellow }
function Write-Ok($texto)    { Write-Host "[OK] $texto"   -ForegroundColor Green }

# --- Log de execucao (transcript) — FAIL-SOFT -------------------------------
# Cada execucao grava um log timestampado em %ProgramData%\ProcessadorDocumentos\logs\.
# Mesmo que a janela feche apos um erro, o log fica gravado em disco e o caminho e
# impresso no fim (sucesso OU erro). Se o Start-Transcript falhar (sem permissao),
# seguimos SEM log — o logging NUNCA quebra o script.
$LogsDir = Join-Path (Join-Path $env:ProgramData 'ProcessadorDocumentos') 'logs'
$ts      = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogFile = Join-Path $LogsDir "instalar-$ts.log"
$transcriptOn = $false
try {
    New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
    Start-Transcript -Path $LogFile -Force | Out-Null
    $transcriptOn = $true
} catch {
    Write-Aviso ("Nao foi possivel iniciar o log de execucao (seguindo sem log): " + $_.Exception.Message)
}

try {

# --- 1. Python 3.12 ---------------------------------------------------------
Write-Passo 'Verificando Python 3.12'
$temPython = $false
try {
    $versao = & python --version 2>&1
    if ($versao -match 'Python 3\.(1[1-3])') { $temPython = $true; Write-Ok "$versao encontrado" }
} catch { $temPython = $false }

if (-not $temPython) {
    Write-Aviso 'Python 3.12 não encontrado. Tentando instalar via winget...'
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id Python.Python.3.12 --silent --accept-source-agreements --accept-package-agreements
        Write-Aviso 'Python instalado. FECHE e reabra o PowerShell para atualizar o PATH e rode .\instalar.ps1 de novo.'
        exit 0
    } else {
        throw 'winget indisponível. Instale o Python 3.12 manualmente em https://www.python.org/downloads/ e rode .\instalar.ps1 de novo.'
    }
}

# --- 2. uv ------------------------------------------------------------------
Write-Passo 'Verificando uv (gerenciador de pacotes Python)'
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Ok 'uv já instalado'
} else {
    Write-Aviso 'uv não encontrado. Instalando via instalador oficial da Astral...'
    powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    # Reavalia o PATH NESTA sessão (o instalador adiciona ~\.local\bin).
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw 'uv não ficou disponível após a instalação. Feche e reabra o PowerShell e rode .\instalar.ps1 de novo.'
    }
    Write-Ok 'uv instalado'
}

# --- 3. Dependências do backend ---------------------------------------------
Write-Passo 'Instalando dependências do backend (uv sync)'
uv sync --project $BackendDir
if ($LASTEXITCODE -ne 0) { throw "uv sync falhou (codigo $LASTEXITCODE). Dependencias nao instaladas." }
Write-Ok 'Dependências sincronizadas'

# --- 4. Arquivo .env --------------------------------------------------------
Write-Passo 'Garantindo o arquivo de configuração backend\.env'
if (Test-Path $EnvFile) {
    Write-Ok '.env já existe (mantido como está)'
} else {
    if (-not (Test-Path $EnvExample)) { throw "Modelo não encontrado: $EnvExample" }
    Copy-Item $EnvExample $EnvFile
    Write-Aviso '================================================================'
    Write-Aviso ' backend\.env criado a partir de .env.example.'
    Write-Aviso ' EDITE backend\.env e preencha OPENAI_API_KEY antes de usar a IA.'
    Write-Aviso ' (A chave é um SEGREDO; nunca é versionada nem exibida.)'
    Write-Aviso '================================================================'
}

# --- 5. Frontend (opcional) -------------------------------------------------
Write-Passo 'Verificando o frontend buildado (frontend\dist)'
if (Test-Path $DistDir) {
    Write-Ok 'frontend\dist já presente (pacote de release ou build anterior) — build pulado'
} elseif (Get-Command npm -ErrorAction SilentlyContinue) {
    Write-Aviso 'frontend\dist ausente. Buildando com npm...'
    Push-Location $FrontendDir
    try {
        npm ci
        npm run build
        Write-Ok 'Frontend buildado em frontend\dist'
    } finally {
        Pop-Location
    }
} else {
    Write-Aviso 'Node/npm não encontrado: a interface (UI) NÃO será servida até buildar o frontend.'
    Write-Aviso 'A API continua funcionando. Veja INSTALL-WINDOWS.md (seção Troubleshooting) para buildar.'
}

# --- 6. Migração do banco + 7. Servidor (ambos de DENTRO de backend\) --------
# Rodamos a partir de backend\ por DOIS motivos críticos:
#   1. O alembic procura o `alembic.ini` no diretório ATUAL. Rodando da raiz do
#      repo ele falha com "No 'script_location' key found" e o schema NÃO é criado
#      — banco fica sem tabelas e as rotas de lista respondem 500.
#   2. O app lê `backend\.env` (DATA_DIR / DATABASE_URL / OPENAI_API_KEY) relativo
#      ao diretório atual. Rodando da raiz, o `.env` não é carregado (a chave
#      OpenAI não seria lida e um DATA_DIR customizado seria ignorado).
# Falha-fechada: se o alembic não retornar 0, ABORTA (não sobe servidor quebrado).
#
# OBRIGATÓRIO --workers 1: o lifespan sobe watcher + worker como asyncio.Task UMA
# vez por PROCESSO. Com mais de 1 worker, watcher e worker seriam duplicados,
# causando processamento concorrente da mesma pasta e contenção de escrita no
# SQLite (single-writer). NÃO aumente o número de workers.
Push-Location $BackendDir
try {
    Write-Passo 'Aplicando o schema do banco (alembic upgrade head)'
    uv run alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "alembic upgrade head falhou (codigo $LASTEXITCODE). O schema do banco NAO foi aplicado; abortando antes de subir o servidor."
    }
    Write-Ok 'Schema do banco atualizado'

    Write-Passo 'Iniciando o servidor'
    Write-Host ''
    Write-Host '    Abra http://localhost:8000 no navegador.' -ForegroundColor Green
    Write-Host '    (Pressione Ctrl+C para parar o servidor.)' -ForegroundColor Green
    Write-Host ''
    uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
} finally {
    Pop-Location
}

} finally {
    # Caminho do log impresso DESTACADO (entra no proprio log antes de pararmos o
    # transcript). Stop-Transcript e tolerante a falhas — nunca quebra o script.
    if ($transcriptOn) {
        Write-Host ''
        Write-Host ("Log desta execucao: " + $LogFile) -ForegroundColor Cyan
        Write-Host ''
        try { Stop-Transcript | Out-Null } catch { }
    }
}
