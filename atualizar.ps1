# atualizar.ps1 — Atualizador do Processador de Documentos (Windows)
#
# Atualiza a instância PRESERVANDO os dados do cliente. O código é separado dos
# dados: banco SQLite, CAS, templates e configuração vivem em
#   %ProgramData%\ProcessadorDocumentos
# e NÃO são tocados por esta atualização. O Alembic migra apenas o SCHEMA do
# banco, preservando o conteúdo.
#
# O que faz:
#   1. Atualiza o código (git pull, se for repositório git).
#   2. uv sync (atualiza as dependências do backend).
#   3. (Opcional) Rebuilda o frontend se o Node estiver disponível.
#   4. alembic upgrade head (migra o schema preservando os dados).
#   5. Reinicia o servidor (uvicorn --workers 1) em http://localhost:8000.
#
# SEGREDO: a OPENAI_API_KEY NUNCA é lida, exibida nem logada por este script.

$ErrorActionPreference = 'Stop'

$RepoRoot    = $PSScriptRoot
$BackendDir  = Join-Path $RepoRoot 'backend'
$FrontendDir = Join-Path $RepoRoot 'frontend'
$DistDir     = Join-Path $FrontendDir 'dist'

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
Write-Host ' o schema do banco, preservando todo o conteúdo.' -ForegroundColor Yellow
Write-Host '================================================================' -ForegroundColor Yellow

# --- 1. Atualizar o código --------------------------------------------------
Write-Passo 'Atualizando o código'
if ((Test-Path (Join-Path $RepoRoot '.git')) -and (Get-Command git -ErrorAction SilentlyContinue)) {
    Push-Location $RepoRoot
    try { git pull } finally { Pop-Location }
    Write-Ok 'Código atualizado via git pull'
} else {
    Write-Aviso 'Não é um repositório git (ou git ausente).'
    Write-Aviso 'Copie os arquivos novos da nova versão SOBRE esta pasta do projeto'
    Write-Aviso '(substituindo o código) e rode .\atualizar.ps1 novamente.'
}

# --- 2. Dependências do backend ---------------------------------------------
Write-Passo 'Atualizando dependências do backend (uv sync)'
uv sync --project $BackendDir
Write-Ok 'Dependências sincronizadas'

# --- 3. Frontend (opcional) -------------------------------------------------
Write-Passo 'Rebuildando o frontend'
if (Get-Command npm -ErrorAction SilentlyContinue) {
    Push-Location $FrontendDir
    try {
        npm ci
        npm run build
        Write-Ok 'Frontend rebuildado em frontend\dist'
    } finally {
        Pop-Location
    }
} else {
    Write-Aviso 'Node/npm não encontrado: frontend não rebuildado (a API segue funcionando).'
    if (-not (Test-Path $DistDir)) {
        Write-Aviso 'frontend\dist ausente: a UI não será servida até buildar. Veja INSTALL-WINDOWS.md.'
    }
}

# --- 4. Migração do banco ---------------------------------------------------
Write-Passo 'Migrando o schema do banco (alembic upgrade head)'
uv run --project $BackendDir alembic upgrade head
Write-Ok 'Schema migrado (dados preservados)'

# --- 5. Reiniciar o servidor ------------------------------------------------
# OBRIGATÓRIO --workers 1 (mesmo motivo do instalar.ps1: watcher + worker sobem
# como asyncio.Task uma vez por processo; >1 worker duplicaria e causaria
# contenção de escrita no SQLite single-writer).
Write-Passo 'Reiniciando o servidor'
Write-Host ''
Write-Host '    Abra http://localhost:8000 no navegador.' -ForegroundColor Green
Write-Host '    (Pressione Ctrl+C para parar o servidor.)' -ForegroundColor Green
Write-Host ''
uv run --project $BackendDir uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
