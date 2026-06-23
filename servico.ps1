# servico.ps1 — Controle do serviço Windows do Processador de Documentos (NSSM)
#
# Roda o backend (uvicorn) SEMPRE em background como serviço Windows nativo,
# supervisionado pelo NSSM:
#   - inicia no boot (antes do login)  -> Start=SERVICE_AUTO_START
#   - reinicia sozinho se cair          -> AppExit Default Restart
#   - grava logs em arquivo com rotação -> %ProgramData%\ProcessadorDocumentos\logs
#
# EM PRODUÇÃO, use SÓ o serviço (este script). NÃO rode `instalar.ps1` em primeiro
# plano enquanto o serviço estiver instalado/rodando — isso sobe uma SEGUNDA
# instância na porta 8000 (conflito de porta + escrita concorrente no SQLite).
#
# Subcomandos:
#   instalar    registra e inicia o serviço (alembic + NSSM + health-check)
#   iniciar     inicia o serviço
#   parar       para o serviço
#   reiniciar   reinicia o serviço
#   status      mostra o estado do serviço (nssm status + sc query)
#   remover     para e remove o serviço
#   logs        mostra o caminho e as últimas linhas dos logs do serviço
#
# Auto-elevação: os subcomandos que exigem privilégio se re-lançam via UAC.
#
# SEGREDO: a OPENAI_API_KEY NUNCA é lida, exibida nem logada por este script.
#   O serviço lê a chave do `backend\.env` via CWD (AppDirectory=backend\); a chave
#   NUNCA é passada por AppEnvironmentExtra (apareceria no registro do serviço) nem
#   exibida pelo subcomando `logs` (que só mostra os logs out/err do uvicorn).
#
# Compatível com Windows PowerShell 5.1 (sem `??`, `?.`, ou operador ternário).

param([Parameter(Position = 0)][string]$Comando = 'status')

$ErrorActionPreference = 'Stop'

# --- Constantes (caminhos derivados de $PSScriptRoot — NUNCA do CWD, pois a -------
# --- auto-elevação muda o diretório atual) ----------------------------------------
$RepoRoot       = $PSScriptRoot
$BackendDir     = Join-Path $RepoRoot 'backend'
$VenvPython     = Join-Path $BackendDir '.venv\Scripts\python.exe'
$ToolsDir       = Join-Path $RepoRoot 'tools'
$NssmExe        = Join-Path $ToolsDir 'nssm.exe'
$ServiceName    = 'ProcessadorDocumentos'
$ServiceDisplay = 'Processador de Documentos'
$DataDir        = Join-Path $env:ProgramData 'ProcessadorDocumentos'
$LogsDir        = Join-Path $DataDir 'logs'
$OutLog         = Join-Path $LogsDir 'service.out.log'
$ErrLog         = Join-Path $LogsDir 'service.err.log'
$NssmZipUrl     = 'https://nssm.cc/release/nssm-2.24.zip'
$HealthUrl      = 'http://127.0.0.1:8000/health'

function Write-Passo($texto) { Write-Host "`n==> $texto" -ForegroundColor Cyan }
function Write-Aviso($texto) { Write-Host "[AVISO] $texto" -ForegroundColor Yellow }
function Write-Ok($texto)    { Write-Host "[OK] $texto"   -ForegroundColor Green }

# --- Auto-elevação (Administrador) ------------------------------------------------
# nssm install/set/start/stop/remove exigem privilégio de administrador. Se não
# estivermos elevados, re-lança o script via UAC preservando o subcomando.
function Assert-Admin {
    $identidade = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal  = New-Object Security.Principal.WindowsPrincipal($identidade)
    $ehAdmin    = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $ehAdmin) {
        Write-Aviso "Privilégio de administrador necessário para '$Comando'. Solicitando elevação (UAC)..."
        # Re-lança SOMENTE o token do subcomando (vindo do switch) — sem injeção de
        # argumentos arbitrários.
        Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList @(
            '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath, $Comando
        )
        exit
    }
}

# --- Garantir o nssm.exe ----------------------------------------------------------
# Usa o binário vendorizado em tools\nssm.exe se presente e não-vazio; senão baixa
# o nssm-2.24.zip, extrai win64\nssm.exe e copia para tools\nssm.exe.
function Get-Nssm {
    if ((Test-Path $NssmExe) -and ((Get-Item $NssmExe).Length -gt 0)) {
        return
    }
    Write-Passo 'nssm.exe ausente — baixando NSSM 2.24'
    if (-not (Test-Path $ToolsDir)) { New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null }
    $tmpDir = Join-Path $env:TEMP ("nssm-dl-" + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null
    try {
        $zip = Join-Path $tmpDir 'nssm-2.24.zip'
        Invoke-WebRequest -Uri $NssmZipUrl -OutFile $zip -UseBasicParsing
        Expand-Archive -Path $zip -DestinationPath $tmpDir -Force
        # No Windows 64-bit moderno usamos o binário win64.
        $origem = Join-Path $tmpDir 'nssm-2.24\win64\nssm.exe'
        if (-not (Test-Path $origem)) { throw "nssm.exe (win64) não encontrado dentro do ZIP baixado." }
        Copy-Item -Path $origem -Destination $NssmExe -Force
    } finally {
        Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue
    }
    # Validação pós-cópia (A4: nssm.cc não publica hash canônico machine-friendly;
    # validamos por presença + tamanho + saída da versão contendo "2.24").
    if (-not ((Test-Path $NssmExe) -and ((Get-Item $NssmExe).Length -gt 0))) {
        throw "Falha ao obter o nssm.exe em $NssmExe."
    }
    $versao = (& $NssmExe version 2>&1 | Out-String)
    if ($versao -notmatch '2\.24') {
        throw "nssm.exe baixado não reporta versão 2.24 (saída: $versao). Abortando por integridade."
    }
    Write-Ok 'NSSM 2.24 disponível em tools\nssm.exe'
}

# --- Garantir o venv legível pelo SYSTEM (Pegadinha 1, mitigação opção 1) ---------
# O serviço roda como LocalSystem. Se o venv apontar (via pyvenv.cfg `home`) para
# um Python no perfil do usuário, o SYSTEM pode não conseguir lê-lo (ACL) e o
# serviço falha em runtime. Mitigação: criar o venv a partir de um Python base
# instalado para TODOS os usuários (acessível ao SYSTEM).
function Ensure-Venv {
    Write-Passo 'Garantindo o ambiente Python (venv legível pelo serviço)'

    # uv só é usado na INSTALAÇÃO (não em runtime). Garante uv no PATH desta sessão.
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"

    # Procura um Python base instalado all-users (fora do perfil do usuário).
    $pythonSistema = $null
    $candidatos = @(
        (Join-Path $env:ProgramFiles 'Python312\python.exe'),
        'C:\Python312\python.exe'
    )
    foreach ($c in $candidatos) {
        if (Test-Path $c) { $pythonSistema = $c; break }
    }
    if (-not $pythonSistema) {
        # Fallback: resolver via Get-Command, aceitando apenas caminhos que NÃO
        # estejam sob o perfil do usuário (senão não são legíveis pelo SYSTEM).
        $cmd = Get-Command python -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source) {
            $src = $cmd.Source
            if ($src -notlike "$env:USERPROFILE*") { $pythonSistema = $src }
        }
    }

    $venvDir = Join-Path $BackendDir '.venv'
    $precisaCriar = (-not (Test-Path $venvDir)) -or (-not (Test-Path $VenvPython))

    if ($pythonSistema) {
        Write-Ok "Python base (all-users) para o venv: $pythonSistema"
        if ($precisaCriar) {
            & uv venv --python $pythonSistema $venvDir
            if ($LASTEXITCODE -ne 0) { throw "uv venv falhou (codigo $LASTEXITCODE)." }
        }
    } else {
        # Não aborta aqui: o health-check da instalação confirmará se o serviço sobe
        # sob SYSTEM. A rede de segurança AppEnvironmentExtra + ACL ainda pode salvar.
        Write-Aviso 'Nenhum Python all-users encontrado (C:\Program Files\Python312 ou C:\Python312).'
        Write-Aviso 'O serviço dependerá da rede de segurança (AppEnvironmentExtra) e do health-check para confirmar.'
        if ($precisaCriar -and (Get-Command python -ErrorAction SilentlyContinue)) {
            & uv venv $venvDir
            if ($LASTEXITCODE -ne 0) { throw "uv venv falhou (codigo $LASTEXITCODE)." }
        }
    }

    # Instala/atualiza as dependências do backend a partir do lockfile.
    & uv sync --project $BackendDir
    if ($LASTEXITCODE -ne 0) { throw "uv sync falhou (codigo $LASTEXITCODE). Dependencias nao instaladas." }
    Write-Ok 'Ambiente Python pronto'
}

# --- Detecta se o serviço já existe (idempotência) --------------------------------
function Test-ServiceExists {
    $saida = (& $NssmExe status $ServiceName 2>&1 | Out-String)
    # Quando o serviço não existe, o nssm reporta erro/"service ... not installed".
    if ($saida -match 'SERVICE_') { return $true }
    return $false
}

# --- Instalação completa do serviço -----------------------------------------------
# IMPORTANTE: produção usa SÓ o serviço. NÃO rodar `instalar.ps1` em 1º plano junto
# (dupla instância → conflito de porta 8000 + SQLite single-writer).
function Invoke-Instalar {
    # (a) elevação
    Assert-Admin
    # (b) nssm
    Get-Nssm
    # (c) venv legível pelo SYSTEM
    Ensure-Venv
    if (-not (Test-Path $VenvPython)) {
        throw "python.exe do venv não encontrado em backend\.venv\Scripts. O serviço não pode ser registrado."
    }
    # (d) pasta de logs DEVE existir antes do NSSM gravar
    New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

    # (e) ALEMBIC FALHA-FECHADA (de dentro de backend\ — alembic procura alembic.ini
    # no CWD; o servidor NÃO roda alembic). Mesmo padrão do instalar.ps1.
    Write-Passo 'Aplicando o schema do banco (alembic upgrade head)'
    Push-Location $BackendDir
    try {
        & uv run alembic upgrade head
        if ($LASTEXITCODE -ne 0) {
            throw "alembic upgrade head falhou (codigo $LASTEXITCODE). Schema NAO aplicado; abortando antes de registrar o serviço."
        }
    } finally {
        Pop-Location
    }
    Write-Ok 'Schema do banco atualizado'

    # (f) REGISTRO NSSM (idempotente: se já existe, reaplica os `set`).
    Write-Passo 'Registrando o serviço no Windows (NSSM)'
    if (-not (Test-ServiceExists)) {
        & $NssmExe install $ServiceName $VenvPython
        if ($LASTEXITCODE -ne 0) { throw "nssm install falhou (codigo $LASTEXITCODE)." }
    } else {
        Write-Aviso "Serviço '$ServiceName' já existe — reaplicando a configuração (idempotente)."
    }

    # AppParameters = uvicorn --workers 1 (OBRIGATÓRIO --workers 1: watcher+worker
    # sobem 1x por processo; SQLite single-writer).
    $appParams = '-m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1'

    & $NssmExe set $ServiceName Application $VenvPython
    & $NssmExe set $ServiceName AppParameters $appParams
    & $NssmExe set $ServiceName AppDirectory $BackendDir
    & $NssmExe set $ServiceName DisplayName $ServiceDisplay
    & $NssmExe set $ServiceName Description 'Backend FastAPI do Processador de Documentos'
    & $NssmExe set $ServiceName Start SERVICE_AUTO_START
    & $NssmExe set $ServiceName ObjectName LocalSystem
    & $NssmExe set $ServiceName AppStdout $OutLog
    & $NssmExe set $ServiceName AppStderr $ErrLog
    & $NssmExe set $ServiceName AppRotateFiles 1
    & $NssmExe set $ServiceName AppRotateOnline 1
    # A1: a unidade de AppRotateBytes (bytes vs KB) diverge entre fontes; 10485760
    # PRETENDE ~10 MB. Confirmar empíricamente na máquina Windows.
    & $NssmExe set $ServiceName AppRotateBytes 10485760
    & $NssmExe set $ServiceName AppExit Default Restart
    & $NssmExe set $ServiceName AppRestartDelay 5000
    & $NssmExe set $ServiceName AppThrottle 10000
    # AppEnvironmentExtra: rede de segurança (Pegadinha 1) com valores ABSOLUTOS do
    # usuário instalador. NUNCA passar OPENAI_API_KEY aqui (apareceria no registro do
    # serviço); a chave é lida pelo app via backend\.env (AppDirectory=backend\).
    $envExtra = "USERPROFILE=$env:USERPROFILE LOCALAPPDATA=$env:LOCALAPPDATA APPDATA=$env:APPDATA PATH=$env:USERPROFILE\.local\bin;$env:Path"
    & $NssmExe set $ServiceName AppEnvironmentExtra $envExtra
    Write-Ok 'Serviço configurado (auto-start, LocalSystem, auto-restart, logs com rotação)'

    # (g) INICIAR
    Write-Passo 'Iniciando o serviço'
    & $NssmExe start $ServiceName

    # (h) HEALTH-CHECK FALHA-FECHADA. A falha SYSTEM/ACL (Pegadinha 1) só aparece em
    # runtime — esta verificação é a defesa contra "serviço quebrado silencioso".
    Write-Passo 'Verificando a saúde do serviço (/health)'
    $saudavel = $false
    for ($i = 0; $i -lt 15; $i++) {
        Start-Sleep -Seconds 2
        try {
            $resp = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 3
            if ($resp.StatusCode -eq 200) { $saudavel = $true; break }
        } catch {
            # ainda subindo — continua o polling
        }
    }

    if ($saudavel) {
        Write-Ok 'Serviço saudável.'
        Write-Host ''
        Write-Host '    Abra http://localhost:8000 no navegador.' -ForegroundColor Green
        Write-Host '    Controle: .\servico.ps1 status | parar | iniciar | reiniciar | logs | remover' -ForegroundColor Green
        Write-Host ''
    } else {
        Write-Aviso 'O serviço NÃO ficou saudável em ~30s.'
        Write-Aviso "Veja o log de erros: $ErrLog"
        if (Test-Path $ErrLog) {
            Write-Host '----- últimas linhas de service.err.log -----' -ForegroundColor Yellow
            Get-Content -Tail 30 $ErrLog
            Write-Host '---------------------------------------------' -ForegroundColor Yellow
        }
        Write-Aviso 'Causa provável: ambiente Python não acessível à conta do serviço (LocalSystem) — ver Pegadinha 1.'
        throw "Instalação do serviço falhou no health-check. Diagnostique pelo service.err.log acima."
    }
}

# --- Roteador de subcomandos ------------------------------------------------------
switch ($Comando.ToLower()) {
    'instalar' {
        Invoke-Instalar
    }
    'iniciar' {
        Assert-Admin
        Get-Nssm
        & $NssmExe start $ServiceName
        Write-Ok "Serviço '$ServiceName' iniciado."
    }
    'parar' {
        Assert-Admin
        Get-Nssm
        & $NssmExe stop $ServiceName
        Write-Ok "Serviço '$ServiceName' parado."
    }
    'reiniciar' {
        Assert-Admin
        Get-Nssm
        & $NssmExe restart $ServiceName
        Write-Ok "Serviço '$ServiceName' reiniciado."
    }
    'status' {
        # Não exige Admin.
        Get-Nssm
        Write-Passo "Status do serviço '$ServiceName' (NSSM)"
        & $NssmExe status $ServiceName
        Write-Passo "Status nativo do Windows (sc query)"
        & sc.exe query $ServiceName
    }
    'remover' {
        Assert-Admin
        Get-Nssm
        # Tolera erro se já estiver parado.
        try { & $NssmExe stop $ServiceName } catch { Write-Aviso 'Serviço já parado (ou inexistente).' }
        # O `confirm` é OBRIGATÓRIO em script (sem ele o nssm abre prompt interativo).
        & $NssmExe remove $ServiceName confirm
        Write-Ok "Serviço '$ServiceName' removido."
    }
    'logs' {
        # Não exige Admin. NUNCA expõe a OPENAI_API_KEY — só os logs out/err do uvicorn.
        Write-Passo 'Logs do serviço'
        Write-Host "  stdout: $OutLog"
        Write-Host "  stderr: $ErrLog"
        if (Test-Path $OutLog) {
            Write-Passo 'Últimas linhas de service.out.log'
            Get-Content -Tail 40 $OutLog
        } else {
            Write-Aviso 'service.out.log ainda não existe.'
        }
        if (Test-Path $ErrLog) {
            Write-Passo 'Últimas linhas de service.err.log'
            Get-Content -Tail 40 $ErrLog
        } else {
            Write-Aviso 'service.err.log ainda não existe.'
        }
    }
    default {
        Write-Host "Uso: .\servico.ps1 <subcomando>" -ForegroundColor Cyan
        Write-Host ''
        Write-Host '  instalar    registra e inicia o serviço Windows (NSSM)'
        Write-Host '  iniciar     inicia o serviço'
        Write-Host '  parar       para o serviço'
        Write-Host '  reiniciar   reinicia o serviço'
        Write-Host '  status      mostra o estado do serviço'
        Write-Host '  remover     para e remove o serviço'
        Write-Host '  logs        mostra os caminhos e as últimas linhas dos logs'
        exit 1
    }
}
