---
phase: quick-260623-lpj
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tools/iniciar-servidor.py
  - servico.ps1
  - empacotar.ps1
  - INSTALL-WINDOWS.md
autonomous: true
requirements: [QUICK-PERSIST-WIN]
must_haves:
  truths:
    - "No Windows, o modo PADRÃO do servico.ps1 é a Tarefa Agendada no logon, rodando como o usuário atual (sem admin, sem senha de serviço, sem Pegadinha 1)"
    - "O NSSM/LocalSystem continua disponível e funcional via --modo servico, com aviso claro do pré-requisito (Python all-users)"
    - "tools/iniciar-servidor.py sobe o uvicorn de dentro de backend\\ com --workers 1, sem console (pythonw), logando em arquivo"
    - "tools/iniciar-servidor.py é versionado (fonte) e entra no pacote; o nssm.exe segue gitignored mas no pacote"
    - "O guia INSTALL-WINDOWS.md descreve os DOIS modos com suas limitações"
    - "OPENAI_API_KEY nunca é lida, exibida nem logada por nenhum artefato deste plano"
  artifacts:
    - path: "tools/iniciar-servidor.py"
      provides: "Launcher pythonw-friendly do uvicorn (CWD=backend, log em arquivo)"
      contains: "uvicorn"
    - path: "servico.ps1"
      provides: "Controle 2-modos: tarefa (padrão) + servico (NSSM)"
      contains: "ScheduledTask"
    - path: "empacotar.ps1"
      provides: "Inclui tools/iniciar-servidor.py no staging"
      contains: "iniciar-servidor.py"
    - path: "INSTALL-WINDOWS.md"
      provides: "Guia dos dois modos de background"
  key_links:
    - from: "servico.ps1"
      to: "tools/iniciar-servidor.py"
      via: "ação da Tarefa Agendada: pythonw.exe + caminho do launcher"
      pattern: "iniciar-servidor\\.py"
    - from: "tools/iniciar-servidor.py"
      to: "app.main:app"
      via: "uvicorn.run com CWD/sys.path em backend\\"
      pattern: "app\\.main"
---

<objective>
Tornar a **Tarefa Agendada no logon (como usuário)** o modo PADRÃO de persistência
do servidor no Windows, validado numa máquina piloto em 2026-06-23 (release v0.1.2,
instalação em D:\processador_doc). O NSSM/LocalSystem (código atual) passa a ser a
opção `--modo servico` para o cenário PC-servidor 24/7 headless.

Motivo: na máquina piloto o `uv` instala o Python gerenciado no perfil do usuário
(`%APPDATA%\uv\python\cpython-3.12-...`) e o venv (`backend\.venv`) aponta pra lá;
NÃO há Python all-users. LocalSystem não lê esse Python por ACL → o serviço sobe e
morre (Pegadinha 1). A Tarefa no logon roda como o **dono do venv** → sem Pegadinha 1,
sem senha de serviço, sem admin.

Purpose: entregar persistência confiável no Windows no caminho que comprovadamente
funciona, preservando o caminho NSSM para quem tem Python all-users e quer headless.
Output: launcher versionado, `servico.ps1` 2-modos, `empacotar.ps1` atualizado e guia
reescrito. (Bump de versão 0.1.2 -> 0.1.3 fica fora do plano — o orquestrador faz no
empacotamento.)
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md

<interfaces>
<!-- Contratos/fatos do codigo atual que o executor DEVE reusar — sem explorar de novo. -->

Layout do repo (caminhos derivados SEMPRE de $PSScriptRoot, NUNCA do CWD):
- RepoRoot     = $PSScriptRoot
- BackendDir   = repo\backend            (alembic.ini e app/ vivem aqui; CWD obrigatorio)
- ToolsDir     = repo\tools
- VenvPython   = repo\backend\.venv\Scripts\python.exe    (ja usado pelo servico.ps1 atual)
- VenvPythonw  = repo\backend\.venv\Scripts\pythonw.exe   (NOVO — sem console, mesmo dir)
- NssmExe      = repo\tools\nssm.exe
- Launcher     = repo\tools\iniciar-servidor.py           (NOVO — versionado)

App / servidor (identico ao instalar.ps1 e ao NSSM atual):
- modulo ASGI: app.main:app
- comando: uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
- OBRIGATORIO --workers 1: watcher+worker sobem 1x por processo; SQLite single-writer.
- CWD DEVE ser backend\: (1) alembic procura alembic.ini no CWD; (2) o app le backend\.env
  (DATA_DIR/DATABASE_URL/OPENAI_API_KEY) relativo ao CWD. Rodar da raiz quebra ambos.

Funcoes ja existentes no servico.ps1 (REUSAR, nao reimplementar):
- Write-Passo / Write-Aviso / Write-Ok  (helpers de saida coloridos)
- Assert-Admin  (auto-elevacao UAC — usar SO no modo servico)
- Get-Nssm      (garante tools\nssm.exe — usar SO no modo servico)
- Ensure-Venv   (garante venv + uv sync — reusar nos DOIS modos)
- Test-ServiceExists  (deteccao do servico NSSM — usar para detectar modo instalado)
- Invoke-Instalar     (instalacao NSSM completa — vira o corpo do modo servico)

Constantes NSSM atuais (modo servico): ServiceName='ProcessadorDocumentos',
DataDir=%ProgramData%\ProcessadorDocumentos, logs em DataDir\logs\service.{out,err}.log,
HealthUrl='http://127.0.0.1:8000/health'.

Config DATA_DIR (backend/app/config.py): padrao Windows = %ProgramData%\ProcessadorDocumentos;
o usuario no modo tarefa JA tem permissao de escrita la (consistente com a instalacao atual).

Segredo: OPENAI_API_KEY e lida pelo app via backend\.env (CWD=backend\). NUNCA passar a
chave por env da Tarefa/NSSM nem exibi-la em logs/subcomando `logs`.

Compatibilidade: Windows PowerShell 5.1+. Os cmdlets Register-ScheduledTask,
Unregister-ScheduledTask, Start/Stop-ScheduledTask, Get-ScheduledTask,
Get-ScheduledTaskInfo, New-ScheduledTaskTrigger/Action/Principal/Settings existem no
PS 5.1. NAO usar sintaxe so-PS7 (operadores de coalescencia/condicional null nem ternario).
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Criar tools/iniciar-servidor.py (launcher versionado, pythonw-friendly)</name>
  <files>tools/iniciar-servidor.py</files>
  <action>
Criar o launcher Python que a Tarefa Agendada executa via pythonw.exe (sem console).
E FONTE versionada (diferente do nssm.exe, gitignored). Comentario no topo (PT-BR)
explicando o porque: a Tarefa roda como o usuario dono do venv, evitando a Pegadinha 1
do LocalSystem (uv instala o Python no perfil do usuario; SYSTEM nao le por ACL).

Comportamento exigido:
- Resolver o diretorio backend\ a partir da localizacao do proprio arquivo
  (Path(__file__).resolve().parent.parent / "backend"). NAO depender do CWD do processo
  (a Tarefa define WorkingDirectory, mas o launcher nao pode confiar nisso).
- os.chdir(backend) e inserir o backend em sys.path[0] ANTES de importar app — para que
  backend\.env seja carregado e app.main resolva (mesmo motivo do --workers 1 em backend\
  no instalar.ps1).
- Resolver a pasta de logs em %LOCALAPPDATA%\ProcessadorDocumentos\logs (os.environ
  LOCALAPPDATA, com fallback para Path.home()/"AppData"/"Local" se ausente). Criar a pasta
  com parents=True, exist_ok=True. Abrir <logs>\servidor.log em modo append e redirecionar
  sys.stdout e sys.stderr para esse arquivo (line-buffered) — pythonw nao tem console, entao
  toda saida do uvicorn PRECISA ir pro arquivo.
- Importar uvicorn e chamar uvicorn.run("app.main:app", host="127.0.0.1", port=8000,
  workers=1). Garantir 1 instancia: workers=1 + a Tarefa configurada com
  MultipleInstances=IgnoreNew (Task 2). NAO usar reload.
- NUNCA logar, ler nem imprimir OPENAI_API_KEY (o app a le do .env; o launcher nao toca nela).
- Escrever no servidor.log uma linha de cabecalho com timestamp + cwd na inicializacao
  (sem segredos), para o subcomando `logs` ter algo legivel.

NAO colocar bloco de codigo aqui; o arquivo E o entregavel — escrever Python real e direto.
  </action>
  <verify>
    <automated>python -c "import ast; ast.parse(open('tools/iniciar-servidor.py',encoding='utf-8').read()); print('PARSE OK')" && grep -q 'app.main' tools/iniciar-servidor.py && grep -q 'workers' tools/iniciar-servidor.py && grep -q 'LOCALAPPDATA' tools/iniciar-servidor.py && grep -q 'chdir' tools/iniciar-servidor.py && ! grep -qi 'OPENAI_API_KEY' tools/iniciar-servidor.py && echo "STATIC OK"</automated>
  </verify>
  <done>
tools/iniciar-servidor.py existe, faz parse como Python valido, chdir para backend\,
roda uvicorn app.main:app workers=1 em 127.0.0.1:8000, redireciona stdout/stderr para
%LOCALAPPDATA%\ProcessadorDocumentos\logs\servidor.log, e NAO referencia OPENAI_API_KEY.
  </done>
</task>

<task type="auto">
  <name>Task 2: Reescrever servico.ps1 para 2 modos (tarefa=padrao, servico=NSSM)</name>
  <files>servico.ps1</files>
  <action>
Reescrever servico.ps1 com parametro de modo. Assinatura:
param([Parameter(Position=0)][string]$Comando='status',
      [ValidateSet('tarefa','servico')][string]$Modo='tarefa').
PADRAO = tarefa. Atualizar o comentario-cabecalho (PT-BR) descrevendo os dois modos,
a Pegadinha 1 e a regra de segredo (OPENAI_API_KEY nunca lida/exibida/logada).

PRESERVAR o codigo NSSM atual movendo-o para o modo servico: manter Assert-Admin,
Get-Nssm, Ensure-Venv, Test-ServiceExists e Invoke-Instalar exatamente como hoje
(Invoke-Instalar vira a instalacao do modo servico). Adicionar constantes do modo tarefa:
  $VenvPythonw = Join-Path $BackendDir '.venv\Scripts\pythonw.exe'
  $Launcher    = Join-Path $ToolsDir 'iniciar-servidor.py'
  $TaskName    = 'ProcessadorDocumentos-Servidor'
  $TaskLogsDir = Join-Path $env:LOCALAPPDATA 'ProcessadorDocumentos\logs'
  $TaskLog     = Join-Path $TaskLogsDir 'servidor.log'

Funcoes NOVAS do modo tarefa:
- Test-TaskExists: retorna $true se Get-ScheduledTask -TaskName $TaskName existe
  (usar -ErrorAction SilentlyContinue + checar $null).
- Resolve-ModoInstalado: deteccao do modo instalado para os subcomandos de controle.
  Regra simples e robusta: se -Modo foi passado explicitamente pelo usuario, respeita-lo;
  senao, se Test-TaskExists -> 'tarefa'; senao se Test-ServiceExists -> 'servico'; senao o
  default 'tarefa'. (Para saber se -Modo foi explicito, usar
  $PSBoundParameters.ContainsKey('Modo').)
- Invoke-InstalarTarefa: instalacao do modo tarefa. NAO chama Assert-Admin (RunLevel limitado).
  Passos: (1) Ensure-Venv (reusar); (2) validar que $VenvPythonw existe — senao throw com
  mensagem clara; (3) alembic upgrade head FALHA-FECHADA de dentro de backend\ (Push-Location
  $BackendDir / `& uv run alembic upgrade head` / checar $LASTEXITCODE / Pop-Location no
  finally), mesmo padrao do Invoke-Instalar atual; (4) criar $TaskLogsDir; (5) registrar a
  Tarefa via Register-ScheduledTask compondo:
    Trigger  = New-ScheduledTaskTrigger -AtLogOn (do usuario atual);
    Action   = New-ScheduledTaskAction -Execute $VenvPythonw -Argument ('"' + $Launcher + '"')
               -WorkingDirectory $BackendDir;
    Principal= New-ScheduledTaskPrincipal -UserId ("$env:USERDOMAIN\$env:USERNAME")
               -LogonType Interactive -RunLevel Limited;
    Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable
               -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3
               -RestartInterval (New-TimeSpan -Minutes 1)
               -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries;
    Register-ScheduledTask -TaskName $TaskName -Trigger $t -Action $a -Principal $p
               -Settings $s -Force.
    (-Force = idempotencia: re-registra se ja existe.)
  (6) Start-ScheduledTask -TaskName $TaskName; (7) HEALTH-CHECK FALHA-FECHADA: polling ~30s
  (15 x 2s) em $HealthUrl (Invoke-WebRequest 200). Se falhar: mostrar o caminho $TaskLog +
  Get-Content -Tail 30 $TaskLog (se existir) e `throw` (SAIR com erro). Se ok: Write-Ok +
  instrucoes de acesso (http://localhost:8000) e os comandos de controle.

Roteador de subcomandos (switch sobre $Comando.ToLower()): para os subcomandos de CONTROLE,
primeiro resolver $modoEfetivo = Resolve-ModoInstalado; 'instalar' usa $Modo diretamente.
  - instalar:   if ($Modo -eq 'servico') { Invoke-Instalar } else { Invoke-InstalarTarefa }.
  - iniciar/parar/reiniciar/status/remover/logs: ramificar por $modoEfetivo.
    * modo tarefa: iniciar=Start-ScheduledTask; parar=Stop-ScheduledTask; reiniciar=Stop+Start;
      status=Get-ScheduledTask + Get-ScheduledTaskInfo (State, LastRunTime, LastTaskResult) +
      tentar /health; remover=Stop-ScheduledTask (tolerante a erro) depois
      Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false; logs=mostrar $TaskLog +
      Get-Content -Tail 40 (NUNCA expoe OPENAI_API_KEY — so o servidor.log do uvicorn).
    * modo servico: comportamento NSSM ATUAL preservado (Assert-Admin + Get-Nssm + nssm
      start/stop/restart/status/remove, logs em %ProgramData%).
  - default: uso atualizado listando os subcomandos E os dois modos (-Modo tarefa|servico,
    padrao tarefa).

Avisar de forma clara o pre-requisito do modo servico: pelo menos um Write-Aviso (no
Invoke-Instalar e/ou no ramo 'instalar' do modo servico) dizendo que o NSSM/LocalSystem
EXIGE Python all-users e FALHA sem ele (Pegadinha 1), e que o modo padrao (tarefa) nao tem
essa exigencia.

Restricoes: PowerShell 5.1+ (sem sintaxe so-PS7). Caminhos SEMPRE de $PSScriptRoot.
OPENAI_API_KEY NUNCA lida/exibida/logada. Manter Push/Pop-Location em try/finally onde houver
chdir. Manter $HealthUrl = 'http://127.0.0.1:8000/health' compartilhado pelos dois modos.
  </action>
  <verify>
    <automated>grep -Eq "ValidateSet\\('tarefa','servico'\\)" servico.ps1 && for c in Register-ScheduledTask Unregister-ScheduledTask Start-ScheduledTask Stop-ScheduledTask Get-ScheduledTask New-ScheduledTaskTrigger New-ScheduledTaskAction New-ScheduledTaskPrincipal New-ScheduledTaskSettingsSet; do grep -q "$c" servico.ps1 || { echo "FALTA $c"; exit 1; }; done && grep -q 'IgnoreNew' servico.ps1 && grep -q 'pythonw.exe' servico.ps1 && grep -q 'iniciar-servidor.py' servico.ps1 && grep -q 'Invoke-InstalarTarefa' servico.ps1 && grep -q 'Resolve-ModoInstalado' servico.ps1 && echo "TAREFA OK"</automated>
    Conferir manualmente (sem PS no host): sem sintaxe so-PS7; Push/Pop-Location em try/finally; nenhuma mencao a OPENAI_API_KEY (`grep -i openai servico.ps1` deve voltar VAZIO).
  </verify>
  <done>
servico.ps1 aceita -Modo tarefa|servico (padrao tarefa). Modo tarefa registra/controla a
Tarefa Agendada ProcessadorDocumentos-Servidor (AtLogOn, RunLevel Limited, IgnoreNew,
auto-restart) apontando pythonw.exe -> tools\iniciar-servidor.py com WorkingDirectory=backend\,
faz alembic falha-fechada e health-check falha-fechada. Modo servico preserva o NSSM atual e
avisa o pre-requisito (Python all-users / Pegadinha 1). Os subcomandos de controle detectam o
modo instalado. Nenhuma referencia a OPENAI_API_KEY no script.
  </done>
</task>

<task type="auto">
  <name>Task 3: Incluir o launcher no pacote (empacotar.ps1) e reescrever o guia (INSTALL-WINDOWS.md)</name>
  <files>empacotar.ps1, INSTALL-WINDOWS.md</files>
  <action>
PARTE A — empacotar.ps1: garantir que tools\iniciar-servidor.py (FONTE versionada) entre no
pacote junto com tools\nssm.exe. Hoje a etapa 4d copia apenas o nssm.exe para o staging
($stagingTools). Adicionar a copia do launcher: validar que repo\tools\iniciar-servidor.py
existe (senao `throw` "iniciar-servidor.py ausente — o pacote PRECISA do launcher do modo
tarefa") e Copy-Item para (Join-Path $stagingTools 'iniciar-servidor.py'). O launcher e fonte
do repo (ao contrario do nssm.exe, que e baixado/gitignored) — apenas garantir a inclusao no
staging; nao precisa baixar nada. Atualizar a mensagem Write-Ok do staging para mencionar
iniciar-servidor.py + nssm.exe. NAO mexer na logica de Get-Nssm do empacotador.

PARTE B — INSTALL-WINDOWS.md: reescrever a secao "6. Rodar sempre em background" para os DOIS
modos. Tudo PT-BR, voltado ao usuario final.
  - Abertura: explicar que ha dois modos e quando usar cada um.
  - "Modo padrao — Tarefa Agendada no logon (sem admin)": comando `.\servico.ps1 instalar`
    (sem -Modo, pois tarefa e o padrao; NAO exige Administrador). Explicar que sobe sozinho ao
    fazer LOGON do usuario, reinicia se cair, e roda como a propria conta do usuario (por isso
    nao sofre a falha de Python do modo servico). LIMITACAO clara e honesta: so roda enquanto o
    usuario esta logado; NAO roda antes do login nem em servidor headless sem sessao. Logs em
    `%LOCALAPPDATA%\ProcessadorDocumentos\logs\servidor.log`.
  - "Modo servidor 24/7 — Servico Windows (NSSM, avancado)": comando
    `.\servico.ps1 instalar -Modo servico` (EXIGE Administrador — auto-eleva via UAC).
    PRE-REQUISITO destacado: precisa de Python instalado para TODOS os usuarios (all-users);
    sem ele o servico falha ao subir (a conta LocalSystem nao le o Python do perfil do usuario).
    Vantagem: inicia no boot, antes do login, ideal para PC-servidor sem sessao aberta. Logs em
    `%ProgramData%\ProcessadorDocumentos\logs\service.{out,err}.log`.
  - Tabela de controle aplicavel aos DOIS modos (os subcomandos detectam o modo instalado):
    status | parar | iniciar | reiniciar | logs | remover. Mostrar que `-Modo servico` pode ser
    passado nos comandos de controle se necessario, mas normalmente a deteccao automatica
    resolve.
  - Manter/atualizar o aviso de "nao rode duas instancias" (instalar.ps1 em 1o plano + um modo
    de background ao mesmo tempo = conflito de porta 8000 + SQLite).
  - Onde ficam os logs de cada modo (os dois caminhos acima).
  Preservar o tom e o estilo do guia atual; nao quebrar os links internos das outras secoes.
  </action>
  <verify>
    <automated>grep -q 'iniciar-servidor.py' empacotar.ps1 && grep -q 'Modo servico' INSTALL-WINDOWS.md && grep -q 'servidor.log' INSTALL-WINDOWS.md && (grep -qi 'all-users' INSTALL-WINDOWS.md || grep -qi 'todos os usu' INSTALL-WINDOWS.md) && (grep -qi 'logon' INSTALL-WINDOWS.md || grep -qi 'login' INSTALL-WINDOWS.md) && ! grep -qi 'OPENAI_API_KEY=' empacotar.ps1 && echo "PACOTE+GUIA OK"</automated>
  </verify>
  <done>
empacotar.ps1 inclui tools\iniciar-servidor.py no staging (alem do nssm.exe) com validacao de
presenca. INSTALL-WINDOWS.md descreve os dois modos de background: padrao (Tarefa no logon, sem
admin, limitacao "so logado") e servidor 24/7 (NSSM, exige admin + Python all-users), com os
comandos de controle, os caminhos de log de cada modo e o aviso de instancia unica.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| script PowerShell -> Agendador/Serviço do Windows | servico.ps1 registra Tarefa/Serviço que executa pythonw/uvicorn |
| launcher -> backend\.env | o app lê DATA_DIR/DATABASE_URL/OPENAI_API_KEY do .env via CWD=backend\ |
| processo do servidor -> rede | uvicorn escuta em 127.0.0.1:8000 (somente loopback) |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-quick-01 | Information Disclosure | OPENAI_API_KEY em logs/registro de Tarefa/Serviço | mitigate | Nunca passar a chave por env da Tarefa/NSSM nem por argumento; nunca lê-la/exibi-la nos scripts; o launcher só redireciona stdout/stderr do uvicorn (que não imprime a chave). Verify: `grep -i openai` vazio em servico.ps1 e iniciar-servidor.py |
| T-quick-02 | Elevation of Privilege | modo tarefa registrando com privilégio excessivo | mitigate | Principal com -RunLevel Limited + -LogonType Interactive (sem admin); só o modo servico exige/usa Assert-Admin (UAC) |
| T-quick-03 | Denial of Service | duas instâncias na porta 8000 (Tarefa + instalar.ps1, ou Tarefa + Serviço) | mitigate | --workers 1 + MultipleInstances=IgnoreNew na Tarefa; aviso no guia de não rodar 1º plano junto; health-check confirma uma instância saudável |
| T-quick-04 | Tampering | servidor exposto na rede | accept | uvicorn escuta só em 127.0.0.1 (loopback); single-tenant local — fora do escopo deste plano alterar bind |
| T-quick-SC | Tampering | npm/pip/cargo installs | accept | Este plano NÃO instala pacotes novos (uvicorn/uv já são dependências existentes; nssm.exe inalterado). Sem nova superfície de supply-chain |
</threat_model>

<verification>
Host sem PowerShell/Windows → verificação ESTÁTICA + roteiro de teste manual no SUMMARY.

Estática (automatizável aqui):
- `python -c "import ast; ast.parse(...)"` em tools/iniciar-servidor.py (sintaxe válida).
- grep dos cmdlets *-ScheduledTask, do ValidateSet do modo, de pythonw.exe, do launcher, das
  funções novas (Invoke-InstalarTarefa, Resolve-ModoInstalado) em servico.ps1.
- grep de `iniciar-servidor.py` em empacotar.ps1; dos dois modos e caminhos de log em
  INSTALL-WINDOWS.md.
- `grep -i openai` deve voltar VAZIO em servico.ps1 e tools/iniciar-servidor.py.

Roteiro de teste manual (registrar no SUMMARY, executar em Windows real):
1. `.\servico.ps1 instalar` (sem -Modo) → registra a Tarefa SEM pedir UAC; health-check
   verde; http://localhost:8000/health → 200; porta 8000 escutando (pythonw).
2. Reiniciar/fazer logoff+logon → a Tarefa sobe o servidor sozinha; /health 200.
3. `.\servico.ps1 status` / `logs` / `reiniciar` / `parar` / `iniciar` → operam na Tarefa;
   logs em %LOCALAPPDATA%\ProcessadorDocumentos\logs\servidor.log.
4. `.\servico.ps1 remover` → Unregister-ScheduledTask; status mostra ausência.
5. (Máquina com Python all-users) `.\servico.ps1 instalar -Modo servico` → UAC; NSSM como
   LocalSystem; health-check verde. Confirmar aviso do pré-requisito.
6. Empacotar e abrir o ZIP → tools\iniciar-servidor.py e tools\nssm.exe presentes.
</verification>

<success_criteria>
- tools/iniciar-servidor.py existe (versionado), faz parse, roda uvicorn app.main:app
  --workers 1 de dentro de backend\ via pythonw, loga em
  %LOCALAPPDATA%\ProcessadorDocumentos\logs\servidor.log, sem tocar a OPENAI_API_KEY.
- servico.ps1 tem -Modo tarefa|servico (padrão tarefa); modo tarefa registra/controla a Tarefa
  Agendada (sem admin, IgnoreNew, AtLogOn, auto-restart, alembic + health-check falha-fechada);
  modo servico preserva o NSSM atual com aviso do pré-requisito; controle detecta o modo
  instalado; sem referência a OPENAI_API_KEY.
- empacotar.ps1 inclui tools/iniciar-servidor.py no pacote (além do nssm.exe).
- INSTALL-WINDOWS.md documenta os dois modos com limitações, comandos e caminhos de log.
- Verificação estática passa; roteiro de teste manual registrado no SUMMARY.
</success_criteria>

<output>
Create `.planning/quick/260623-lpj-persistencia-windows-servico-ps1-padrao-/260623-lpj-SUMMARY.md` when done.
Incluir no SUMMARY o roteiro de teste manual (não rodável no host) e lembrar o orquestrador
do bump 0.1.2 -> 0.1.3 no empacotamento.
</output>
