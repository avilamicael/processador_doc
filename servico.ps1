# servico.ps1 — Persistencia do Processador de Documentos no Windows (2 modos)
#
# Roda o backend (uvicorn) SEMPRE em background, de duas formas:
#
#   MODO PADRAO  -> -Modo tarefa  (Tarefa Agendada no logon, como o usuario atual)
#     - sobe sozinho ao FAZER LOGON do usuario      -> trigger AtLogOn
#     - reinicia sozinho se cair                     -> RestartCount/RestartInterval
#     - roda como a propria conta do usuario (sem admin, sem senha de servico)
#     - executa pythonw.exe -> tools\iniciar-servidor.py (sem console)
#     - logs em %LOCALAPPDATA%\ProcessadorDocumentos\logs\servidor.log
#     LIMITACAO: so roda enquanto o usuario esta logado (nao antes do login,
#     nem em servidor headless sem sessao).
#
#   MODO AVANCADO -> -Modo servico (Servico Windows nativo via NSSM, LocalSystem)
#     - inicia no boot (antes do login)              -> Start=SERVICE_AUTO_START
#     - reinicia sozinho se cair                      -> AppExit Default Restart
#     - logs em %ProgramData%\ProcessadorDocumentos\logs\service.{out,err}.log
#     PRE-REQUISITO: Python instalado para TODOS os usuarios (all-users). A conta
#     LocalSystem NAO le o Python gerenciado pelo uv no perfil do usuario (ACL) —
#     sem Python all-users o servico sobe e MORRE (Pegadinha 1). O modo tarefa
#     (padrao) NAO tem essa exigencia.
#
# Por que o padrao e a Tarefa: na maioria das instalacoes o `uv` instala o Python
# no perfil do usuario e o venv (backend\.venv) aponta pra la; nao ha Python
# all-users. A Tarefa roda como o dono do venv -> sem Pegadinha 1.
#
# EM PRODUCAO use SO UM modo de background por vez. NAO rode `instalar.ps1` em
# primeiro plano enquanto a Tarefa/Servico estiver ativa — isso sobe uma SEGUNDA
# instancia na porta 8000 (conflito de porta + escrita concorrente no SQLite).
#
# Subcomandos (detectam automaticamente o modo instalado p/ controle):
#   instalar    registra e inicia (alembic + registro + health-check falha-fechada)
#   iniciar     inicia
#   parar       para
#   reiniciar   reinicia
#   status      mostra o estado
#   remover     para e remove
#   logs        mostra o caminho e as ultimas linhas dos logs
#   diagnostico gera um relatorio unico (sem segredos) p/ enviar ao suporte
#
# SEGREDO: a chave da IA (no backend\.env) NUNCA e lida, exibida nem logada por
#   este script. O servidor le a chave do `backend\.env` via CWD; ela NUNCA e
#   passada por env da Tarefa/NSSM nem exibida pelo subcomando `logs` (que so
#   mostra a saida do uvicorn).
#
# Compativel com Windows PowerShell 5.1 (sem `??`, `?.`, ou operador ternario).

param(
    [Parameter(Position = 0)][string]$Comando = 'status',
    [ValidateSet('tarefa','servico')][string]$Modo = 'tarefa'
)

$ErrorActionPreference = 'Stop'

# Captura, NO CORPO do script, se -Modo foi passado explicitamente. Aqui
# $PSBoundParameters reflete os parametros REAIS do script (dentro de uma funcao
# ele e o da funcao, sempre vazio — origem do bug do Resolve-ModoInstalado).
$script:ModoExplicito = $PSBoundParameters.ContainsKey('Modo')

# --- Constantes (caminhos derivados de $PSScriptRoot — NUNCA do CWD, pois a -------
# --- auto-elevacao muda o diretorio atual) ----------------------------------------
$RepoRoot       = $PSScriptRoot
$BackendDir     = Join-Path $RepoRoot 'backend'
$ToolsDir       = Join-Path $RepoRoot 'tools'
$VenvPython     = Join-Path $BackendDir '.venv\Scripts\python.exe'
$NssmExe        = Join-Path $ToolsDir 'nssm.exe'
$HealthUrl      = 'http://127.0.0.1:8000/health'

# Modo servico (NSSM / LocalSystem)
$ServiceName    = 'ProcessadorDocumentos'
$ServiceDisplay = 'Processador de Documentos'
$DataDir        = Join-Path $env:ProgramData 'ProcessadorDocumentos'
$LogsDir        = Join-Path $DataDir 'logs'
$OutLog         = Join-Path $LogsDir 'service.out.log'
$ErrLog         = Join-Path $LogsDir 'service.err.log'
$NssmZipUrl     = 'https://nssm.cc/release/nssm-2.24.zip'

# Modo tarefa (Tarefa Agendada / usuario atual)
$VenvPythonw    = Join-Path $BackendDir '.venv\Scripts\pythonw.exe'
$Launcher       = Join-Path $ToolsDir 'iniciar-servidor.py'
$TaskName       = 'ProcessadorDocumentos-Servidor'
$TaskLogsDir    = Join-Path $env:LOCALAPPDATA 'ProcessadorDocumentos\logs'
$TaskLog        = Join-Path $TaskLogsDir 'servidor.log'

function Write-Passo($texto) { Write-Host "`n==> $texto" -ForegroundColor Cyan }
function Write-Aviso($texto) { Write-Host "[AVISO] $texto" -ForegroundColor Yellow }
function Write-Ok($texto)    { Write-Host "[OK] $texto"   -ForegroundColor Green }

# --- Auto-elevacao (Administrador) ------------------------------------------------
# Usado SO no modo servico: nssm install/set/start/stop/remove exigem privilegio de
# administrador. Se nao estivermos elevados, re-lanca o script via UAC preservando o
# subcomando E o -Modo servico (senao a re-execucao cairia no padrao 'tarefa').
function Assert-Admin {
    $identidade = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal  = New-Object Security.Principal.WindowsPrincipal($identidade)
    $ehAdmin    = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $ehAdmin) {
        Write-Aviso "Privilegio de administrador necessario para '$Comando -Modo servico'. Solicitando elevacao (UAC)..."
        Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList @(
            '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath, $Comando, '-Modo', 'servico'
        )
        exit
    }
}

# --- Garantir o nssm.exe (modo servico) -------------------------------------------
# Usa o binario vendorizado em tools\nssm.exe se presente e nao-vazio; senao baixa
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
        # No Windows 64-bit moderno usamos o binario win64.
        $origem = Join-Path $tmpDir 'nssm-2.24\win64\nssm.exe'
        if (-not (Test-Path $origem)) { throw "nssm.exe (win64) nao encontrado dentro do ZIP baixado." }
        Copy-Item -Path $origem -Destination $NssmExe -Force
    } finally {
        Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue
    }
    # Validacao pos-copia (A4: nssm.cc nao publica hash canonico machine-friendly;
    # validamos por presenca + tamanho + saida da versao contendo "2.24").
    if (-not ((Test-Path $NssmExe) -and ((Get-Item $NssmExe).Length -gt 0))) {
        throw "Falha ao obter o nssm.exe em $NssmExe."
    }
    $versao = (& $NssmExe version 2>&1 | Out-String)
    if ($versao -notmatch '2\.24') {
        throw "nssm.exe baixado nao reporta versao 2.24 (saida: $versao). Abortando por integridade."
    }
    Write-Ok 'NSSM 2.24 disponivel em tools\nssm.exe'
}

# --- Garantir o venv (reusado pelos DOIS modos) -----------------------------------
# No modo servico o venv DEVE ser legivel pelo SYSTEM (Pegadinha 1) — por isso
# tentamos um Python base all-users. No modo tarefa o usuario e o dono do venv, e
# qualquer Python que o uv resolva serve. A funcao cobre os dois casos.
function Ensure-Venv {
    Write-Passo 'Garantindo o ambiente Python (venv)'

    # uv so e usado na INSTALACAO (nao em runtime). Garante uv no PATH desta sessao.
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"

    # Procura um Python base instalado all-users (fora do perfil do usuario).
    $pythonSistema = $null
    $candidatos = @(
        (Join-Path $env:ProgramFiles 'Python312\python.exe'),
        'C:\Python312\python.exe'
    )
    foreach ($c in $candidatos) {
        if (Test-Path $c) { $pythonSistema = $c; break }
    }
    if (-not $pythonSistema) {
        # Fallback: resolver via Get-Command, aceitando apenas caminhos que NAO
        # estejam sob o perfil do usuario (relevante para o modo servico/SYSTEM).
        $cmd = Get-Command python -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source) {
            $src = $cmd.Source
            if ($src -notlike "$env:USERPROFILE*") { $pythonSistema = $src }
        }
    }

    $venvDir = Join-Path $BackendDir '.venv'
    $precisaCriar = (-not (Test-Path $venvDir)) -or (-not (Test-Path $VenvPython))

    if ($pythonSistema) {
        Write-Ok "Python base para o venv: $pythonSistema"
        if ($precisaCriar) {
            & uv venv --python $pythonSistema $venvDir
            if ($LASTEXITCODE -ne 0) { throw "uv venv falhou (codigo $LASTEXITCODE)." }
        }
    } else {
        # No modo servico isto pode ser um problema (SYSTEM x Python do usuario);
        # no modo tarefa e perfeitamente normal (o usuario e o dono do venv).
        Write-Aviso 'Nenhum Python all-users encontrado (C:\Program Files\Python312 ou C:\Python312).'
        Write-Aviso 'OK para o modo tarefa (roda como o usuario). No modo servico, ver Pegadinha 1.'
        if ($precisaCriar -and (Get-Command python -ErrorAction SilentlyContinue)) {
            & uv venv $venvDir
            if ($LASTEXITCODE -ne 0) { throw "uv venv falhou (codigo $LASTEXITCODE)." }
        }
    }

    # Instala/atualiza as dependencias do backend a partir do lockfile.
    & uv sync --project $BackendDir
    if ($LASTEXITCODE -ne 0) { throw "uv sync falhou (codigo $LASTEXITCODE). Dependencias nao instaladas." }
    Write-Ok 'Ambiente Python pronto'
}

# --- Deteccao de modo instalado ---------------------------------------------------
function Test-ServiceExists {
    if (-not (Test-Path $NssmExe)) { return $false }
    $saida = (& $NssmExe status $ServiceName 2>&1 | Out-String)
    # Quando o servico nao existe, o nssm reporta erro/"service ... not installed".
    if ($saida -match 'SERVICE_') { return $true }
    return $false
}

function Test-TaskExists {
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -ne $t) { return $true }
    return $false
}

# Resolve o modo efetivo para os subcomandos de CONTROLE:
#   - se o usuario passou -Modo explicitamente, respeita;
#   - senao, se a Tarefa existe -> 'tarefa'; senao se o Servico existe -> 'servico';
#   - senao, o padrao 'tarefa'.
function Resolve-ModoInstalado {
    if ($script:ModoExplicito) { return $Modo }
    if (Test-TaskExists) { return 'tarefa' }
    if (Test-ServiceExists) { return 'servico' }
    return 'tarefa'
}

# --- Health-check compartilhado (falha-fechada) -----------------------------------
# Polling ~30s (15 x 2s) em $HealthUrl. Retorna $true se 200.
function Test-Health {
    for ($i = 0; $i -lt 15; $i++) {
        Start-Sleep -Seconds 2
        try {
            $resp = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 3
            if ($resp.StatusCode -eq 200) { return $true }
        } catch {
            # ainda subindo — continua o polling
        }
    }
    return $false
}

# --- Diagnostico (relatorio unico, SEM segredos) ----------------------------------
# Coleta versoes, caminhos/existencia, estado de persistencia, rede/health e tails
# dos logs num UNICO arquivo em $LogsDir\diagnostico-<ts>.log para o usuario enviar
# ao suporte. NUNCA inclui a chave da IA nem o conteudo do backend\.env (so reporta
# se o .env EXISTE). Cada coletor e isolado em try/catch: uma falha vira uma linha e
# nao aborta o relatorio.
function Invoke-Diagnostico {
    $dts       = Get-Date -Format 'yyyyMMdd-HHmmss'
    $relatorio = Join-Path $LogsDir ("diagnostico-" + $dts + ".log")
    New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

    $linhas = New-Object System.Collections.Generic.List[string]
    function Add-Linha($txt) { $linhas.Add([string]$txt) }
    function Add-Secao($txt) { $linhas.Add(''); $linhas.Add('=== ' + $txt + ' ==='); }

    # (a) Cabecalho
    Add-Linha 'Processador de Documentos — diagnostico'
    try { Add-Linha ('Gerado em: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')) }
    catch { Add-Linha '(nao foi possivel coletar a data: ' + $_.Exception.Message + ')' }

    # (b) Ambiente
    Add-Secao 'Ambiente'
    try { Add-Linha ('PowerShell: ' + $PSVersionTable.PSVersion.ToString()) }
    catch { Add-Linha '(nao foi possivel coletar a versao do PowerShell: ' + $_.Exception.Message + ')' }
    try {
        $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
        Add-Linha ('SO: ' + $os.Caption + ' (versao ' + $os.Version + ')')
    } catch { Add-Linha ('(nao foi possivel coletar o SO: ' + $_.Exception.Message + ')') }

    # (c) Caminhos e existencia (so caminho/existencia — NUNCA conteudo)
    Add-Secao 'Caminhos e existencia'
    $alvos = @{
        'RepoRoot'    = $RepoRoot
        'BackendDir'  = $BackendDir
        'VenvPython'  = $VenvPython
        'VenvPythonw' = $VenvPythonw
        'NssmExe'     = $NssmExe
        'Launcher'    = $Launcher
        'backend\.env (existencia apenas)' = (Join-Path $BackendDir '.env')
    }
    foreach ($nome in $alvos.Keys) {
        try {
            $p = $alvos[$nome]
            if (Test-Path $p) { Add-Linha ('[OK]    ' + $nome + ' -> ' + $p) }
            else              { Add-Linha ('[FALTA] ' + $nome + ' -> ' + $p) }
        } catch { Add-Linha ('(nao foi possivel checar ' + $nome + ': ' + $_.Exception.Message + ')') }
    }

    # (d) Python / uv
    Add-Secao 'Python / uv'
    try {
        if (Get-Command uv -ErrorAction SilentlyContinue) {
            Add-Linha ('uv --version: ' + ((& uv --version 2>&1 | Out-String).Trim()))
        } else { Add-Linha '(uv nao encontrado no PATH)' }
    } catch { Add-Linha ('(nao foi possivel coletar uv: ' + $_.Exception.Message + ')') }
    try {
        if (Test-Path $VenvPython) {
            $exe = (& $VenvPython -c "import sys;print(sys.executable)" 2>&1 | Out-String).Trim()
            Add-Linha ('sys.executable do venv: ' + $exe)
        } else { Add-Linha '(venv python.exe ausente — sys.executable nao coletado)' }
    } catch { Add-Linha ('(nao foi possivel coletar sys.executable: ' + $_.Exception.Message + ')') }
    try {
        $pyvenvCfg = Join-Path $BackendDir '.venv\pyvenv.cfg'
        if (Test-Path $pyvenvCfg) {
            # Apenas a linha 'home' (relevante p/ Pegadinha 1) — nao despeja o arquivo todo.
            $linhaHome = Get-Content $pyvenvCfg | Where-Object { $_ -like 'home*' }
            if ($linhaHome) { Add-Linha ('pyvenv.cfg ' + ($linhaHome -join '; ')) }
            else            { Add-Linha 'pyvenv.cfg: (linha home nao encontrada)' }
        } else { Add-Linha '(pyvenv.cfg ausente)' }
    } catch { Add-Linha ('(nao foi possivel ler pyvenv.cfg: ' + $_.Exception.Message + ')') }

    # (e) Persistencia (Tarefa Agendada e Servico NSSM)
    Add-Secao 'Persistencia'
    try {
        if (Test-TaskExists) {
            $t    = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
            $info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
            Add-Linha ('Tarefa: ' + $TaskName)
            Add-Linha ('  State:          ' + $t.State)
            Add-Linha ('  LastRunTime:    ' + $info.LastRunTime)
            Add-Linha ('  LastTaskResult: ' + $info.LastTaskResult)
        } else { Add-Linha '(Tarefa Agendada nao instalada)' }
    } catch { Add-Linha ('(nao foi possivel coletar a Tarefa: ' + $_.Exception.Message + ')') }
    try {
        if (Test-ServiceExists) {
            Add-Linha ('Servico NSSM: ' + $ServiceName)
            Add-Linha ('  nssm status: ' + ((& $NssmExe status $ServiceName 2>&1 | Out-String).Trim()))
            Add-Linha ('  sc query:')
            (& sc.exe query $ServiceName 2>&1) | ForEach-Object { Add-Linha ('    ' + $_) }
        } else { Add-Linha '(Servico NSSM nao instalado)' }
    } catch { Add-Linha ('(nao foi possivel coletar o Servico: ' + $_.Exception.Message + ')') }

    # (f) Rede
    Add-Secao 'Rede'
    try {
        $conns = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
        if ($conns) {
            foreach ($c in $conns) { Add-Linha ('Porta 8000 LISTEN — OwningProcess: ' + $c.OwningProcess) }
        } else { Add-Linha 'Porta 8000: ninguem escutando.' }
    } catch { Add-Linha ('(nao foi possivel checar a porta 8000: ' + $_.Exception.Message + ')') }
    try {
        $resp = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 3
        Add-Linha ('/health StatusCode: ' + $resp.StatusCode)
    } catch { Add-Linha '(health nao respondeu)' }

    # (g) Tails dos logs (so se existirem; ultimas ~40 linhas)
    Add-Secao 'Tails de logs'
    $tailAlvos = @(
        @{ Nome = 'servidor.log (modo tarefa)';     Path = $TaskLog },
        @{ Nome = 'service.out.log (modo servico)'; Path = $OutLog },
        @{ Nome = 'service.err.log (modo servico)'; Path = $ErrLog }
    )
    foreach ($ta in $tailAlvos) {
        try {
            Add-Linha ('--- ' + $ta.Nome + ' (' + $ta.Path + ') ---')
            if (Test-Path $ta.Path) { Get-Content -Tail 40 $ta.Path | ForEach-Object { Add-Linha $_ } }
            else { Add-Linha '(arquivo nao existe)' }
        } catch { Add-Linha ('(nao foi possivel ler ' + $ta.Nome + ': ' + $_.Exception.Message + ')') }
    }
    try {
        $ultInstalar = Get-ChildItem $LogsDir -Filter 'instalar-*.log' -ErrorAction SilentlyContinue |
                        Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($ultInstalar) {
            Add-Linha ('--- ultimo instalar-*.log (' + $ultInstalar.FullName + ') ---')
            Get-Content -Tail 40 $ultInstalar.FullName | ForEach-Object { Add-Linha $_ }
        } else { Add-Linha '--- ultimo instalar-*.log: (nenhum encontrado) ---' }
    } catch { Add-Linha ('(nao foi possivel ler o ultimo instalar-*.log: ' + $_.Exception.Message + ')') }

    # (h) Rodape — confirmacao de ausencia de segredos
    Add-Secao 'Seguranca'
    Add-Linha 'NENHUM valor de .env / chave da IA foi incluido neste relatorio.'

    # Grava o relatorio unico e imprime o caminho DESTACADO.
    Set-Content -Path $relatorio -Encoding UTF8 -Value $linhas
    Write-Ok 'Diagnostico gravado.'
    Write-Host ("Envie este arquivo ao suporte: " + $relatorio) -ForegroundColor Cyan
}

# ==================================================================================
# MODO TAREFA (padrao) — Tarefa Agendada no logon, como o usuario atual
# ==================================================================================
function Invoke-InstalarTarefa {
    # (a) ambiente Python (NAO exige admin)
    Ensure-Venv

    # (b) o launcher roda via pythonw.exe (sem console)
    if (-not (Test-Path $VenvPythonw)) {
        throw "pythonw.exe do venv nao encontrado em backend\.venv\Scripts. A Tarefa nao pode ser registrada."
    }
    if (-not (Test-Path $Launcher)) {
        throw "Launcher ausente: tools\iniciar-servidor.py. O pacote PRECISA do launcher do modo tarefa."
    }

    # (c) ALEMBIC FALHA-FECHADA (de dentro de backend\ — alembic procura alembic.ini
    # no CWD; o servidor NAO roda alembic). Mesmo padrao do modo servico.
    Write-Passo 'Aplicando o schema do banco (alembic upgrade head)'
    Push-Location $BackendDir
    try {
        & uv run alembic upgrade head
        if ($LASTEXITCODE -ne 0) {
            throw "alembic upgrade head falhou (codigo $LASTEXITCODE). Schema NAO aplicado; abortando antes de registrar a Tarefa."
        }
    } finally {
        Pop-Location
    }
    Write-Ok 'Schema do banco atualizado'

    # (d) pasta de logs DEVE existir antes do servidor gravar
    New-Item -ItemType Directory -Force -Path $TaskLogsDir | Out-Null

    # (e) REGISTRO DA TAREFA (idempotente via -Force).
    Write-Passo 'Registrando a Tarefa Agendada (logon do usuario)'
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $acao    = New-ScheduledTaskAction -Execute $VenvPythonw `
                  -Argument ('"' + $Launcher + '"') `
                  -WorkingDirectory $BackendDir
    $usuario = "$env:USERDOMAIN\$env:USERNAME"
    $principal = New-ScheduledTaskPrincipal -UserId $usuario `
                    -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet `
                    -MultipleInstances IgnoreNew `
                    -StartWhenAvailable `
                    -ExecutionTimeLimit ([TimeSpan]::Zero) `
                    -RestartCount 3 `
                    -RestartInterval (New-TimeSpan -Minutes 1) `
                    -AllowStartIfOnBatteries `
                    -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $TaskName -Trigger $trigger -Action $acao `
        -Principal $principal -Settings $settings -Force -ErrorAction Stop | Out-Null
    # Confirma que a Tarefa REALMENTE existe (o Register-ScheduledTask pode emitir
    # "Acesso negado" como erro NAO-terminante e seguir sem criar nada). Falha-fechada:
    # se nao existir, aborta com orientacao acionavel em vez de mascarar com um [OK].
    if (-not (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)) {
        throw ("Nao foi possivel registrar a Tarefa '$TaskName' (Acesso negado?). " +
            "Rode este script num PowerShell ABERTO MANUALMENTE pela sua conta (Menu Iniciar " +
            "-> Windows PowerShell), NAO por duplo-clique nem por sessao remota/nao-interativa.")
    }
    Write-Ok "Tarefa '$TaskName' registrada (AtLogOn, RunLevel Limited, IgnoreNew, auto-restart)"

    # (f) INICIAR agora (sem esperar o proximo logon)
    Write-Passo 'Iniciando o servidor (Tarefa)'
    Start-ScheduledTask -TaskName $TaskName

    # (g) HEALTH-CHECK FALHA-FECHADA.
    Write-Passo 'Verificando a saude do servidor (/health)'
    if (Test-Health) {
        Write-Ok 'Servidor saudavel.'
        Write-Host ''
        Write-Host '    Abra http://localhost:8000 no navegador.' -ForegroundColor Green
        Write-Host '    Controle: .\servico.ps1 status | parar | iniciar | reiniciar | logs | remover' -ForegroundColor Green
        Write-Host ''
    } else {
        Write-Aviso 'O servidor NAO ficou saudavel em ~30s.'
        Write-Aviso "Veja o log: $TaskLog"
        if (Test-Path $TaskLog) {
            Write-Host '----- ultimas linhas de servidor.log -----' -ForegroundColor Yellow
            Get-Content -Tail 30 $TaskLog
            Write-Host '------------------------------------------' -ForegroundColor Yellow
        }
        throw "Instalacao da Tarefa falhou no health-check. Diagnostique pelo servidor.log acima."
    }
}

function Invoke-IniciarTarefa    { Start-ScheduledTask -TaskName $TaskName; Write-Ok "Tarefa '$TaskName' iniciada." }
function Invoke-PararTarefa       { Stop-ScheduledTask -TaskName $TaskName; Write-Ok "Tarefa '$TaskName' parada." }
function Invoke-ReiniciarTarefa  {
    try { Stop-ScheduledTask -TaskName $TaskName } catch { Write-Aviso 'Tarefa ja parada.' }
    Start-ScheduledTask -TaskName $TaskName
    Write-Ok "Tarefa '$TaskName' reiniciada."
}
function Invoke-StatusTarefa {
    Write-Passo "Status da Tarefa Agendada '$TaskName'"
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $t) {
        Write-Aviso "Tarefa '$TaskName' nao encontrada (modo tarefa nao instalado)."
        return
    }
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Host ("  Estado:        " + $t.State)
    Write-Host ("  Ultima exec.:  " + $info.LastRunTime)
    Write-Host ("  Ultimo result: " + $info.LastTaskResult)
    Write-Passo 'Verificando /health'
    try {
        $resp = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 3
        if ($resp.StatusCode -eq 200) { Write-Ok 'Servidor respondendo em /health (200).' }
    } catch {
        Write-Aviso 'Servidor NAO respondeu em /health (pode estar parado ou subindo).'
    }
}
function Invoke-RemoverTarefa {
    try { Stop-ScheduledTask -TaskName $TaskName } catch { Write-Aviso 'Tarefa ja parada (ou inexistente).' }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Ok "Tarefa '$TaskName' removida."
}
function Invoke-LogsTarefa {
    # NUNCA expoe a chave da IA — so o servidor.log do uvicorn.
    Write-Passo 'Logs do servidor (modo tarefa)'
    Write-Host "  log: $TaskLog"
    if (Test-Path $TaskLog) {
        Write-Passo 'Ultimas linhas de servidor.log'
        Get-Content -Tail 40 $TaskLog
    } else {
        Write-Aviso 'servidor.log ainda nao existe.'
    }
}

# ==================================================================================
# MODO SERVICO (avancado) — Servico Windows nativo via NSSM (LocalSystem)
# ==================================================================================
# IMPORTANTE: produção usa SO UM modo. NAO rodar `instalar.ps1` em 1o plano junto
# (dupla instancia -> conflito de porta 8000 + SQLite single-writer).
function Invoke-Instalar {
    # (a) elevacao
    Assert-Admin
    Write-Aviso 'Modo servico (NSSM/LocalSystem) EXIGE Python instalado para TODOS os usuarios (all-users).'
    Write-Aviso 'Sem Python all-users o servico sobe e MORRE (Pegadinha 1). O modo padrao (tarefa) nao tem essa exigencia.'
    # (b) nssm
    Get-Nssm
    # (c) venv legivel pelo SYSTEM
    Ensure-Venv
    if (-not (Test-Path $VenvPython)) {
        throw "python.exe do venv nao encontrado em backend\.venv\Scripts. O servico nao pode ser registrado."
    }
    # (d) pasta de logs DEVE existir antes do NSSM gravar
    New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

    # (e) ALEMBIC FALHA-FECHADA (de dentro de backend\ — alembic procura alembic.ini
    # no CWD; o servidor NAO roda alembic). Mesmo padrao do instalar.ps1.
    Write-Passo 'Aplicando o schema do banco (alembic upgrade head)'
    Push-Location $BackendDir
    try {
        & uv run alembic upgrade head
        if ($LASTEXITCODE -ne 0) {
            throw "alembic upgrade head falhou (codigo $LASTEXITCODE). Schema NAO aplicado; abortando antes de registrar o servico."
        }
    } finally {
        Pop-Location
    }
    Write-Ok 'Schema do banco atualizado'

    # (f) REGISTRO NSSM (idempotente: se ja existe, reaplica os `set`).
    Write-Passo 'Registrando o servico no Windows (NSSM)'
    if (-not (Test-ServiceExists)) {
        & $NssmExe install $ServiceName $VenvPython
        if ($LASTEXITCODE -ne 0) { throw "nssm install falhou (codigo $LASTEXITCODE)." }
    } else {
        Write-Aviso "Servico '$ServiceName' ja existe — reaplicando a configuracao (idempotente)."
    }

    # AppParameters = uvicorn --workers 1 (OBRIGATORIO --workers 1: watcher+worker
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
    # PRETENDE ~10 MB. Confirmar empiricamente na maquina Windows.
    & $NssmExe set $ServiceName AppRotateBytes 10485760
    & $NssmExe set $ServiceName AppExit Default Restart
    & $NssmExe set $ServiceName AppRestartDelay 5000
    & $NssmExe set $ServiceName AppThrottle 10000
    # AppEnvironmentExtra: rede de seguranca (Pegadinha 1) com valores ABSOLUTOS do
    # usuario instalador. NUNCA passar a chave da IA aqui (apareceria no registro do
    # servico); a chave e lida pelo app via backend\.env (AppDirectory=backend\).
    $envExtra = "USERPROFILE=$env:USERPROFILE LOCALAPPDATA=$env:LOCALAPPDATA APPDATA=$env:APPDATA PATH=$env:USERPROFILE\.local\bin;$env:Path"
    & $NssmExe set $ServiceName AppEnvironmentExtra $envExtra
    Write-Ok 'Servico configurado (auto-start, LocalSystem, auto-restart, logs com rotacao)'

    # (g) INICIAR
    Write-Passo 'Iniciando o servico'
    & $NssmExe start $ServiceName

    # (h) HEALTH-CHECK FALHA-FECHADA. A falha SYSTEM/ACL (Pegadinha 1) so aparece em
    # runtime — esta verificacao e a defesa contra "servico quebrado silencioso".
    Write-Passo 'Verificando a saude do servico (/health)'
    if (Test-Health) {
        Write-Ok 'Servico saudavel.'
        Write-Host ''
        Write-Host '    Abra http://localhost:8000 no navegador.' -ForegroundColor Green
        Write-Host '    Controle: .\servico.ps1 status | parar | iniciar | reiniciar | logs | remover' -ForegroundColor Green
        Write-Host ''
    } else {
        Write-Aviso 'O servico NAO ficou saudavel em ~30s.'
        Write-Aviso "Veja o log de erros: $ErrLog"
        if (Test-Path $ErrLog) {
            Write-Host '----- ultimas linhas de service.err.log -----' -ForegroundColor Yellow
            Get-Content -Tail 30 $ErrLog
            Write-Host '---------------------------------------------' -ForegroundColor Yellow
        }
        Write-Aviso 'Causa provavel: ambiente Python nao acessivel a conta do servico (LocalSystem) — ver Pegadinha 1.'
        throw "Instalacao do servico falhou no health-check. Diagnostique pelo service.err.log acima."
    }
}

# --- Log de execucao (transcript) por subcomando — FAIL-SOFT ----------------------
# Cada execucao grava um log timestampado em $LogsDir (%ProgramData%\...\logs\).
# Mesmo que a janela feche apos um erro, o log fica em disco e o caminho e impresso
# no fim (sucesso OU erro). Se o Start-Transcript falhar, seguimos SEM log (o
# logging NUNCA quebra o script).
$ts      = Get-Date -Format 'yyyyMMdd-HHmmss'
$cmdSlug = ($Comando.ToLower() -replace '[^a-z]','')
if (-not $cmdSlug) { $cmdSlug = 'cmd' }
$LogFile = Join-Path $LogsDir ("servico-" + $cmdSlug + "-" + $ts + ".log")
$transcriptOn = $false
try {
    New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
    Start-Transcript -Path $LogFile -Force | Out-Null
    $transcriptOn = $true
} catch {
    Write-Aviso ("Nao foi possivel iniciar o log desta execucao (seguindo sem log): " + $_.Exception.Message)
}

try {

# --- Roteador de subcomandos ------------------------------------------------------
$cmd = $Comando.ToLower()

if ($cmd -eq 'instalar') {
    if ($Modo -eq 'servico') { Invoke-Instalar } else { Invoke-InstalarTarefa }
    return
}

# diagnostico e INDEPENDENTE de modo (coleta os dois) e nao exige admin nem
# Resolve-ModoInstalado. O finally do transcript acima ainda fecha o log da propria
# execucao do diagnostico (servico-diagnostico-<ts>.log).
if ($cmd -eq 'diagnostico') {
    Invoke-Diagnostico
    return
}

switch ($cmd) {
    { $_ -in 'iniciar', 'parar', 'reiniciar', 'status', 'remover', 'logs' } {
        $modoEfetivo = Resolve-ModoInstalado
        if ($modoEfetivo -eq 'servico') {
            # --- modo servico (NSSM) — comportamento preservado ---
            switch ($cmd) {
                'iniciar'   { Assert-Admin; Get-Nssm; & $NssmExe start $ServiceName;   Write-Ok "Servico '$ServiceName' iniciado." }
                'parar'     { Assert-Admin; Get-Nssm; & $NssmExe stop $ServiceName;    Write-Ok "Servico '$ServiceName' parado." }
                'reiniciar' { Assert-Admin; Get-Nssm; & $NssmExe restart $ServiceName; Write-Ok "Servico '$ServiceName' reiniciado." }
                'status' {
                    Get-Nssm
                    Write-Passo "Status do servico '$ServiceName' (NSSM)"
                    & $NssmExe status $ServiceName
                    Write-Passo "Status nativo do Windows (sc query)"
                    & sc.exe query $ServiceName
                }
                'remover' {
                    Assert-Admin; Get-Nssm
                    try { & $NssmExe stop $ServiceName } catch { Write-Aviso 'Servico ja parado (ou inexistente).' }
                    & $NssmExe remove $ServiceName confirm
                    Write-Ok "Servico '$ServiceName' removido."
                }
                'logs' {
                    # NUNCA expoe a chave da IA — so os logs out/err do uvicorn.
                    Write-Passo 'Logs do servico'
                    Write-Host "  stdout: $OutLog"
                    Write-Host "  stderr: $ErrLog"
                    if (Test-Path $OutLog) { Write-Passo 'Ultimas linhas de service.out.log'; Get-Content -Tail 40 $OutLog }
                    else { Write-Aviso 'service.out.log ainda nao existe.' }
                    if (Test-Path $ErrLog) { Write-Passo 'Ultimas linhas de service.err.log'; Get-Content -Tail 40 $ErrLog }
                    else { Write-Aviso 'service.err.log ainda nao existe.' }
                }
            }
        } else {
            # --- modo tarefa (Tarefa Agendada) ---
            switch ($cmd) {
                'iniciar'   { Invoke-IniciarTarefa }
                'parar'     { Invoke-PararTarefa }
                'reiniciar' { Invoke-ReiniciarTarefa }
                'status'    { Invoke-StatusTarefa }
                'remover'   { Invoke-RemoverTarefa }
                'logs'      { Invoke-LogsTarefa }
            }
        }
    }
    default {
        Write-Host "Uso: .\servico.ps1 <subcomando> [-Modo tarefa|servico]" -ForegroundColor Cyan
        Write-Host ''
        Write-Host '  Modos de background:' -ForegroundColor Cyan
        Write-Host '    -Modo tarefa   (PADRAO) Tarefa Agendada no logon, como o usuario; sem admin.'
        Write-Host '                   Limitacao: so roda enquanto o usuario esta logado.'
        Write-Host '    -Modo servico  Servico Windows (NSSM/LocalSystem); inicia no boot.'
        Write-Host '                   EXIGE Python all-users (senao falha — Pegadinha 1); auto-eleva (UAC).'
        Write-Host ''
        Write-Host '  Subcomandos:' -ForegroundColor Cyan
        Write-Host '    instalar    registra e inicia (alembic + registro + health-check)'
        Write-Host '    iniciar     inicia'
        Write-Host '    parar       para'
        Write-Host '    reiniciar   reinicia'
        Write-Host '    status      mostra o estado'
        Write-Host '    remover     para e remove'
        Write-Host '    logs        mostra os caminhos e as ultimas linhas dos logs'
        Write-Host '    diagnostico gera um relatorio unico (sem segredos) p/ enviar ao suporte'
        Write-Host ''
        Write-Host '  Os subcomandos de controle detectam automaticamente o modo instalado.'
        Write-Host '  Exemplos: .\servico.ps1 instalar          (modo tarefa, padrao)'
        Write-Host '            .\servico.ps1 instalar -Modo servico'
        Write-Host '            .\servico.ps1 status'
        # `return` (em vez de `exit 1`) para o finally do transcript rodar e imprimir
        # o caminho do log mesmo no caminho de uso invalido. Sinaliza o codigo de saida.
        $global:LASTEXITCODE = 1
        return
    }
}

} finally {
    # Caminho do log impresso DESTACADO (entra no proprio log antes de pararmos o
    # transcript). Stop-Transcript e tolerante a falhas — nunca quebra o script.
    if ($transcriptOn) {
        Write-Host ("`nLog desta execucao: " + $LogFile + "`n") -ForegroundColor Cyan
        try { Stop-Transcript | Out-Null } catch { }
    }
}
