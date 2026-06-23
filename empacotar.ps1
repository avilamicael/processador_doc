# empacotar.ps1 — Empacotador de release do Processador de Documentos (DEV)
#
# Rodado pelo DEV (em Windows com Node) para gerar um ZIP de release
# AUTO-CONTIDO: o frontend é buildado e o `frontend\dist` resultante vai DENTRO
# do pacote, de modo que o cliente NÃO precisa de Node nem de Git para instalar.
#
# O que faz:
#   1. Exige Node/npm (o build do frontend é OBRIGATÓRIO aqui).
#   2. Builda o frontend (npm ci + npm run build) → gera frontend\dist.
#   3. Lê a versão de backend\pyproject.toml (não assume 0.1.0).
#   4. Monta uma área de staging com APENAS os arquivos de código necessários,
#      por INCLUSÃO EXPLÍCITA (nunca copia .env, .git, node_modules, frontend\src,
#      tests, *.db*, data, etc.).
#   5. Garante tools\nssm.exe (baixa nssm-2.24.zip se ausente) e inclui no pacote,
#      junto com o servico.ps1 (controle do background) e o launcher versionado
#      tools\iniciar-servidor.py (usado pelo modo padrão — Tarefa Agendada).
#   6. Gera processador-doc-<versao>.zip na raiz do repositório.
#   7. Imprime o caminho do ZIP e instrui (sem executar) o `gh release create`.
#
# SEGREDO: a OPENAI_API_KEY NUNCA é lida, exibida nem logada por este script.
# O .env do desenvolvedor NUNCA entra no pacote (só o .env.example).

$ErrorActionPreference = 'Stop'

# Raiz do repositório = pasta deste script (não depende do diretório atual).
$RepoRoot    = $PSScriptRoot
$BackendDir  = Join-Path $RepoRoot 'backend'
$FrontendDir = Join-Path $RepoRoot 'frontend'
$DistDir     = Join-Path $FrontendDir 'dist'
$PyProject   = Join-Path $BackendDir 'pyproject.toml'
$ToolsDir    = Join-Path $RepoRoot 'tools'
$NssmExe     = Join-Path $ToolsDir 'nssm.exe'
$Launcher    = Join-Path $ToolsDir 'iniciar-servidor.py'
$NssmZipUrl  = 'https://nssm.cc/release/nssm-2.24.zip'

function Write-Passo($texto) { Write-Host "`n==> $texto" -ForegroundColor Cyan }
function Write-Aviso($texto) { Write-Host "[AVISO] $texto" -ForegroundColor Yellow }
function Write-Ok($texto)    { Write-Host "[OK] $texto"   -ForegroundColor Green }

# --- 1. Node/npm OBRIGATÓRIO ------------------------------------------------
Write-Passo 'Verificando Node.js (npm)'
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw 'Node.js (npm) é obrigatório para empacotar (gera frontend/dist). Instale Node 20.19+/22.12+ e rode de novo.'
}
Write-Ok 'npm encontrado'

# --- 2. Build do frontend ---------------------------------------------------
Write-Passo 'Buildando o frontend (npm ci + npm run build)'
Push-Location $FrontendDir
try {
    npm ci
    npm run build
} finally {
    Pop-Location
}
if (-not (Test-Path $DistDir)) {
    throw "Build do frontend não gerou frontend\dist. Verifique os erros do npm acima."
}
Write-Ok 'Frontend buildado em frontend\dist'

# --- 3. Versão (de backend\pyproject.toml) ----------------------------------
Write-Passo 'Lendo a versão de backend\pyproject.toml'
if (-not (Test-Path $PyProject)) { throw "Arquivo não encontrado: $PyProject" }
$versao = $null
foreach ($linha in (Get-Content $PyProject)) {
    if ($linha -match '^\s*version\s*=\s*"([^"]+)"') {
        $versao = $Matches[1]
        break
    }
}
if (-not $versao) {
    throw "Não foi possível ler a versão em backend\pyproject.toml (linha 'version = \"...\"' sob [project])."
}
$nome    = "processador-doc-$versao.zip"
$zipFinal = Join-Path $RepoRoot $nome
Write-Ok "Versão: $versao  ->  $nome"

# --- 3b. Garantir tools\nssm.exe (binário de terceiro, vai SÓ no pacote) -----
# O nssm.exe NÃO é versionado (.gitignore) — o pacote de release PRECISA dele para
# o servico.ps1 registrar o serviço Windows no cliente. Mesma lógica do Get-Nssm
# do servico.ps1 (scripts independentes no pacote — duplicação intencional).
Write-Passo 'Garantindo tools\nssm.exe para o pacote'
if ((Test-Path $NssmExe) -and ((Get-Item $NssmExe).Length -gt 0)) {
    Write-Ok 'tools\nssm.exe já presente'
} else {
    Write-Aviso 'tools\nssm.exe ausente — baixando NSSM 2.24...'
    if (-not (Test-Path $ToolsDir)) { New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null }
    $tmpNssm = Join-Path $env:TEMP ("nssm-pack-" + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $tmpNssm | Out-Null
    try {
        $zipNssm = Join-Path $tmpNssm 'nssm-2.24.zip'
        Invoke-WebRequest -Uri $NssmZipUrl -OutFile $zipNssm -UseBasicParsing
        Expand-Archive -Path $zipNssm -DestinationPath $tmpNssm -Force
        $origemNssm = Join-Path $tmpNssm 'nssm-2.24\win64\nssm.exe'
        if (-not (Test-Path $origemNssm)) {
            throw "nssm.exe (win64) não encontrado no ZIP baixado. O pacote de release PRECISA do nssm.exe."
        }
        Copy-Item -Path $origemNssm -Destination $NssmExe -Force
    } finally {
        Remove-Item -Recurse -Force $tmpNssm -ErrorAction SilentlyContinue
    }
    if (-not ((Test-Path $NssmExe) -and ((Get-Item $NssmExe).Length -gt 0))) {
        throw "Falha ao obter tools\nssm.exe. O pacote de release PRECISA do nssm.exe."
    }
    Write-Ok 'tools\nssm.exe obtido (NSSM 2.24, win64)'
}

# --- 4. Staging (inclusão EXPLÍCITA) ----------------------------------------
Write-Passo 'Montando a área de staging do pacote'
$staging = Join-Path $env:TEMP "pacote-procdoc-$versao"
if (Test-Path $staging) { Remove-Item -Recurse -Force $staging }
New-Item -ItemType Directory -Path $staging | Out-Null

# 4a. backend/ — APENAS os itens permitidos (inclusão explícita).
$stagingBackend = Join-Path $staging 'backend'
New-Item -ItemType Directory -Path $stagingBackend | Out-Null

$backendItens = @(
    'app',            # diretório (recursivo)
    'alembic',        # diretório (recursivo)
    'alembic.ini',
    'pyproject.toml',
    'uv.lock',
    '.env.example',
    'README.md'
)
foreach ($item in $backendItens) {
    $origem = Join-Path $BackendDir $item
    if (-not (Test-Path $origem)) {
        throw "Item obrigatório do backend ausente: backend\$item"
    }
    Copy-Item -Path $origem -Destination $stagingBackend -Recurse -Force
}
# EXCLUSÕES (por desenho, nunca copiadas acima): tests/, __pycache__/, .venv/,
# *.db / *.db-wal / *.db-shm, .env, scripts/, seed_*.py, .ruff_cache/,
# .pytest_cache/, data/. Como a cópia é por inclusão explícita, nenhum desses
# itens entra no pacote.

# 4b. frontend/dist — somente o dist buildado (NÃO src, node_modules, etc.).
$stagingFrontend = Join-Path $staging 'frontend'
New-Item -ItemType Directory -Path $stagingFrontend | Out-Null
Copy-Item -Path $DistDir -Destination $stagingFrontend -Recurse -Force

# 4c. Scripts e guia da raiz.
foreach ($raizItem in @('instalar.ps1', 'atualizar.ps1', 'servico.ps1', 'INSTALL-WINDOWS.md')) {
    $origem = Join-Path $RepoRoot $raizItem
    if (-not (Test-Path $origem)) { throw "Arquivo obrigatório da raiz ausente: $raizItem" }
    Copy-Item -Path $origem -Destination $staging -Force
}

# 4d. tools\ — nssm.exe (binário de terceiro, gitignored, só no pacote) +
# iniciar-servidor.py (FONTE versionada — o launcher do modo tarefa). Ambos
# PRECISAM estar no pacote: o servico.ps1 usa o nssm no modo servico e o launcher
# no modo tarefa (padrão).
$stagingTools = Join-Path $staging 'tools'
New-Item -ItemType Directory -Path $stagingTools | Out-Null
Copy-Item -Path $NssmExe -Destination (Join-Path $stagingTools 'nssm.exe') -Force
# O launcher é fonte do repo (versionado) — basta validar a presença e copiar.
if (-not (Test-Path $Launcher)) {
    throw "iniciar-servidor.py ausente — o pacote PRECISA do launcher do modo tarefa (tools\iniciar-servidor.py)."
}
Copy-Item -Path $Launcher -Destination (Join-Path $stagingTools 'iniciar-servidor.py') -Force

# NÃO incluídos por desenho: .git, .planning, node_modules, frontend\src, .env.
Write-Ok 'Staging montado (com servico.ps1 + tools\iniciar-servidor.py + tools\nssm.exe; sem .env, .git, node_modules, frontend\src, tests)'

# --- 6. Gerar o ZIP ---------------------------------------------------------
Write-Passo "Gerando o pacote $nome"
Compress-Archive -Path (Join-Path $staging '*') -DestinationPath $zipFinal -Force
Write-Ok "Pacote gerado: $zipFinal"

# Limpeza best-effort do staging.
Remove-Item -Recurse -Force $staging -ErrorAction SilentlyContinue

# --- 7. Instrução de upload (NÃO executar) ----------------------------------
Write-Passo 'Próximo passo: publicar a release (manual)'
Write-Host ''
Write-Host '    O upload NÃO foi feito automaticamente. Para publicar a release,' -ForegroundColor Yellow
Write-Host '    rode (com o gh CLI autenticado):' -ForegroundColor Yellow
Write-Host ''
Write-Host "        gh release create v$versao `"$zipFinal`" --title `"v$versao`" --notes `"Release $versao`"" -ForegroundColor Green
Write-Host ''
Write-Host '    O cliente então atualiza com .\atualizar.ps1 (baixa o ZIP da última' -ForegroundColor Yellow
Write-Host '    release) ou .\atualizar.ps1 -LocalZip <caminho> (offline).' -ForegroundColor Yellow
Write-Host ''
