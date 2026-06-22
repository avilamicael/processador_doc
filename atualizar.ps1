# atualizar.ps1 — Atualizador do Processador de Documentos (Windows)
#
# Atualiza a instância a partir de um ZIP de release AUTO-CONTIDO (sem Git e sem
# Node): baixa o ZIP da última GitHub Release (modo ONLINE) ou usa um ZIP local
# informado em -LocalZip (modo OFFLINE). O ZIP já traz o frontend\dist buildado.
#
# Os DADOS do cliente são PRESERVADOS. Código e dados são separados: banco SQLite,
# CAS, templates e configuração vivem em
#   %ProgramData%\ProcessadorDocumentos
# e NÃO são tocados por esta atualização. O Alembic migra apenas o SCHEMA do
# banco, preservando o conteúdo. O backend\.env (com a chave) também é PRESERVADO.
#
# O que faz:
#   1. Obtém o pacote da nova versão (GitHub Releases ou -LocalZip).
#   2. Extrai e sobrescreve APENAS o código, preservando backend\.env.
#   3. uv sync (atualiza as dependências do backend).
#   4. alembic upgrade head (migra o schema preservando os dados).
#   5. Reinicia o servidor (uvicorn --workers 1) em http://localhost:8000.
#
# Uso:
#   .\atualizar.ps1                       # ONLINE: baixa o ZIP da última release
#   .\atualizar.ps1 -LocalZip C:\caminho\processador-doc-X.Y.Z.zip   # OFFLINE
#
# SEGREDO: a OPENAI_API_KEY NUNCA é lida, exibida nem logada por este script.

param([string]$LocalZip)

$ErrorActionPreference = 'Stop'

$RepoRoot    = $PSScriptRoot
$BackendDir  = Join-Path $RepoRoot 'backend'
$FrontendDir = Join-Path $RepoRoot 'frontend'
$DistDir     = Join-Path $FrontendDir 'dist'

# API da última release do repositório oficial.
$ReleaseApi  = 'https://api.github.com/repos/avilamicael/processador_doc/releases/latest'

function Write-Passo($texto) { Write-Host "`n==> $texto" -ForegroundColor Cyan }
function Write-Aviso($texto) { Write-Host "[AVISO] $texto" -ForegroundColor Yellow }
function Write-Ok($texto)    { Write-Host "[OK] $texto"   -ForegroundColor Green }

# --- Banner: dados preservados ----------------------------------------------
Write-Host ''
Write-Host '================================================================' -ForegroundColor Yellow
Write-Host ' SEUS DADOS ESTÃO SEGUROS' -ForegroundColor Yellow
Write-Host ' Banco SQLite, CAS, templates e configuração vivem em:' -ForegroundColor Yellow
Write-Host '   %ProgramData%\ProcessadorDocumentos' -ForegroundColor Yellow
Write-Host ' Essa pasta NÃO é tocada pela atualização. O Alembic migra apenas' -ForegroundColor Yellow
Write-Host ' o schema do banco, preservando todo o conteúdo. O backend\.env' -ForegroundColor Yellow
Write-Host ' (sua configuração e a chave) também é preservado.' -ForegroundColor Yellow
Write-Host '================================================================' -ForegroundColor Yellow

# --- 1. Obter o pacote da nova versão ---------------------------------------
$tempDownload = $null   # ZIP baixado (limpar no final); $null se for -LocalZip
$tempExtract  = Join-Path $env:TEMP ("procdoc-extract-" + [DateTime]::Now.ToString('yyyyMMddHHmmss'))

if ($LocalZip) {
    Write-Passo 'Obtendo o pacote (modo OFFLINE: -LocalZip)'
    if (-not (Test-Path $LocalZip)) {
        throw "ZIP local não encontrado: $LocalZip"
    }
    $zipPath = $LocalZip
    Write-Ok "Usando ZIP local: $zipPath"
} else {
    Write-Passo 'Obtendo o pacote (modo ONLINE: última GitHub Release)'
    try {
        $rel = Invoke-RestMethod -Uri $ReleaseApi -Headers @{ 'User-Agent' = 'processador-doc-updater' }
    } catch {
        throw 'Falha ao consultar o GitHub. Verifique a conexão com a internet ou use -LocalZip <caminho>.'
    }
    $asset = $rel.assets | Where-Object { $_.name -like '*.zip' } | Select-Object -First 1
    if (-not $asset) {
        throw 'Nenhum pacote .zip encontrado na última release (avilamicael/processador_doc). Publique um ZIP ou use -LocalZip.'
    }
    Write-Ok ("Release: " + $rel.tag_name + " — asset: " + $asset.name)

    $tempDownload = Join-Path $env:TEMP ("procdoc-update-" + [DateTime]::Now.ToString('yyyyMMddHHmmss') + ".zip")
    Write-Passo 'Baixando o pacote da release'
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $tempDownload -Headers @{ 'User-Agent' = 'processador-doc-updater' }
    $zipPath = $tempDownload
    Write-Ok "Pacote baixado: $($asset.name)"
}

try {
    # --- 2. Aplicar a atualização (extrair + sobrescrever o código) ---------
    Write-Passo 'Extraindo o pacote'
    if (Test-Path $tempExtract) { Remove-Item -Recurse -Force $tempExtract }
    New-Item -ItemType Directory -Path $tempExtract | Out-Null
    Expand-Archive -Path $zipPath -DestinationPath $tempExtract -Force
    Write-Ok 'Pacote extraído'

    Write-Passo 'Aplicando a atualização (sobrescrevendo o código)'
    # PRESERVAÇÃO do backend\.env: o ZIP NÃO contém .env (só .env.example) e NÃO
    # apagamos backend/ antes de copiar — apenas sobrescrevemos arquivos de código
    # por cima. Assim o backend\.env existente permanece intacto.
    # NÃO tocamos %ProgramData%\ProcessadorDocumentos (fora do diretório de código;
    # nenhuma cópia abaixo mira essa pasta).
    $copiar = @(
        'backend',               # app, alembic, alembic.ini, pyproject.toml, uv.lock, .env.example, README.md
        'frontend',              # apenas frontend\dist vem no pacote
        'instalar.ps1',
        'atualizar.ps1',
        'INSTALL-WINDOWS.md'
    )
    foreach ($item in $copiar) {
        $origem = Join-Path $tempExtract $item
        if (Test-Path $origem) {
            Copy-Item -Path $origem -Destination $RepoRoot -Recurse -Force
        }
    }
    Write-Ok 'Código atualizado (backend\.env preservado; %ProgramData% intacto)'
}
finally {
    # --- Limpeza best-effort dos temporários --------------------------------
    if (Test-Path $tempExtract) { Remove-Item -Recurse -Force $tempExtract -ErrorAction SilentlyContinue }
    if ($tempDownload -and (Test-Path $tempDownload)) { Remove-Item -Force $tempDownload -ErrorAction SilentlyContinue }
}

# --- 3. Dependências do backend ---------------------------------------------
Write-Passo 'Atualizando dependências do backend (uv sync)'
uv sync --project $BackendDir
if ($LASTEXITCODE -ne 0) { throw "uv sync falhou (codigo $LASTEXITCODE). Dependencias nao atualizadas." }
Write-Ok 'Dependências sincronizadas'

# --- 4. Migração do banco + 5. Servidor (ambos de DENTRO de backend\) --------
# Rodamos a partir de backend\ por DOIS motivos críticos (mesmos do instalar.ps1):
#   1. O alembic procura o `alembic.ini` no diretório ATUAL — da raiz do repo ele
#      falha ("No 'script_location' key found") e o schema NÃO é migrado.
#   2. O app lê `backend\.env` (DATA_DIR / DATABASE_URL / OPENAI_API_KEY) relativo
#      ao diretório atual — da raiz, o `.env` não é carregado.
# Falha-fechada: se o alembic não retornar 0, ABORTA (não reinicia quebrado).
#
# OBRIGATÓRIO --workers 1 (mesmo motivo do instalar.ps1: watcher + worker sobem
# como asyncio.Task uma vez por processo; >1 worker duplicaria e causaria
# contenção de escrita no SQLite single-writer).
Push-Location $BackendDir
try {
    Write-Passo 'Migrando o schema do banco (alembic upgrade head)'
    uv run alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "alembic upgrade head falhou (codigo $LASTEXITCODE). O schema NAO foi migrado; abortando antes de reiniciar (seus dados em %ProgramData% estao intactos)."
    }
    Write-Ok 'Schema migrado (dados preservados)'

    Write-Passo 'Reiniciando o servidor'
    Write-Host ''
    Write-Host '    Abra http://localhost:8000 no navegador.' -ForegroundColor Green
    Write-Host '    (Pressione Ctrl+C para parar o servidor.)' -ForegroundColor Green
    Write-Host ''
    uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
} finally {
    Pop-Location
}
