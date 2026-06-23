---
phase: quick-260623-kly
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - servico.ps1
  - empacotar.ps1
  - INSTALL-WINDOWS.md
  - .gitignore
autonomous: true
requirements: [SERVICO-WIN-01]
must_haves:
  truths:
    - "Existe um servico.ps1 com os subcomandos instalar|iniciar|parar|reiniciar|status|remover|logs"
    - "servico.ps1 instalar registra um serviço Windows chamado ProcessadorDocumentos via NSSM apontando para o python.exe do venv (não uv run)"
    - "O serviço sobe no boot (SERVICE_AUTO_START), reinicia ao cair (AppExit Restart) e grava logs com rotação em %ProgramData%\\ProcessadorDocumentos\\logs"
    - "servico.ps1 se auto-eleva (RunAs) preservando o subcomando quando não roda como Administrador"
    - "servico.ps1 instalar faz health-check falha-fechada em http://127.0.0.1:8000/health e sai com erro + caminho/últimas linhas do service.err.log se não ficar saudável"
    - "empacotar.ps1 inclui servico.ps1 e tools\\nssm.exe no ZIP de release"
    - "INSTALL-WINDOWS.md tem uma seção de serviço Windows em PT-BR com o aviso de não rodar instalar.ps1 em 1º plano junto"
    - "tools/nssm.exe está no .gitignore (binário de terceiro, nunca versionado)"
    - "A OPENAI_API_KEY nunca é lida, exibida nem logada por servico.ps1"
  artifacts:
    - path: "servico.ps1"
      provides: "Script único de ciclo de vida do serviço Windows (NSSM)"
      min_lines: 180
    - path: "empacotar.ps1"
      provides: "Empacotador atualizado incluindo servico.ps1 + tools/nssm.exe"
      contains: "servico.ps1"
    - path: "INSTALL-WINDOWS.md"
      provides: "Seção de serviço Windows (background) em PT-BR"
      contains: "servico.ps1"
    - path: ".gitignore"
      provides: "Ignora tools/nssm.exe"
      contains: "nssm.exe"
  key_links:
    - from: "servico.ps1"
      to: "tools\\nssm.exe"
      via: "registro do serviço NSSM (nssm install/set/start)"
      pattern: "nssm.*(install|set|start)"
    - from: "servico.ps1 (Application do serviço)"
      to: "backend\\.venv\\Scripts\\python.exe -m uvicorn"
      via: "nssm set Application + AppParameters"
      pattern: "AppParameters"
    - from: "servico.ps1 instalar"
      to: "http://127.0.0.1:8000/health"
      via: "polling de health-check falha-fechada"
      pattern: "/health"
---

<objective>
Permitir que o backend rode SEMPRE em background no Windows como serviço nativo (inicia no boot antes do login, reinicia sozinho se cair, logs em arquivo com rotação), via NSSM, com um único script de controle em PT-BR.

Purpose: O cliente Windows não pode depender de uma janela do PowerShell aberta (instalar.ps1 em 1º plano). Produção precisa de um serviço supervisionado pelo Service Control Manager. Decisão tomada: NSSM como supervisor, serviço rodando como LocalSystem apontando direto para o python.exe do venv (sem uv run em runtime).

Output:
- `servico.ps1` (NOVO, raiz): subcomandos instalar|iniciar|parar|reiniciar|status|remover|logs, com auto-elevação e health-check falha-fechada.
- `empacotar.ps1` (AJUSTE): inclui servico.ps1 + tools\nssm.exe no ZIP.
- `INSTALL-WINDOWS.md` (AJUSTE): seção de serviço em background.
- `.gitignore` (AJUSTE): ignora tools/nssm.exe.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/quick/260623-kly-servico-windows-via-nssm-servico-ps1-ins/260623-kly-RESEARCH.md
@CLAUDE.md
@instalar.ps1
@empacotar.ps1
@atualizar.ps1
@INSTALL-WINDOWS.md

<interfaces>
<!-- Contratos já estabelecidos no codebase que o executor DEVE reusar. Não explorar. -->

Convenções dos .ps1 existentes (instalar.ps1 / empacotar.ps1 / atualizar.ps1), reusar exatamente:
- `$ErrorActionPreference = 'Stop'` no topo.
- Caminhos derivados de `$PSScriptRoot` / `$PSCommandPath` (NUNCA do diretório atual — crítico porque a auto-elevação muda o CWD).
- Helpers de saída coloridos:
  - `function Write-Passo($texto) { Write-Host "`n==> $texto" -ForegroundColor Cyan }`
  - `function Write-Aviso($texto) { Write-Host "[AVISO] $texto" -ForegroundColor Yellow }`
  - `function Write-Ok($texto)    { Write-Host "[OK] $texto"   -ForegroundColor Green }`
- `$BackendDir = Join-Path $RepoRoot 'backend'` (AppDirectory do serviço = este caminho).
- Verificação de exit code de subprocesso via `$LASTEXITCODE -ne 0` + `throw`.

Backend (verificado):
- Endpoint de health: `GET /health` em backend/app/main.py (linha 99-100) — usar para o polling falha-fechada.
- Servidor sobe com: `uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1` (de dentro de backend\). `--workers 1` é OBRIGATÓRIO.
- App lê `backend\.env` relativo ao CWD → AppDirectory DEVE ser `backend\`.
- `DATA_DIR` = `%ProgramData%\ProcessadorDocumentos` (gravável por LocalSystem).

Comandos NSSM exatos (verificados em RESEARCH.md — usar literalmente):
- `nssm install <NOME> <python_abs> <args...>` OU install só o nome e setar Application depois.
- `nssm set <NOME> Application <repo>\backend\.venv\Scripts\python.exe`
- `nssm set <NOME> AppParameters -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1`
- `nssm set <NOME> AppDirectory <repo>\backend`
- `nssm set <NOME> DisplayName "Processador de Documentos"`
- `nssm set <NOME> Description "Backend FastAPI do Processador de Documentos"`
- `nssm set <NOME> Start SERVICE_AUTO_START`
- `nssm set <NOME> ObjectName LocalSystem`
- `nssm set <NOME> AppStdout <ProgramData>\ProcessadorDocumentos\logs\service.out.log`
- `nssm set <NOME> AppStderr <ProgramData>\ProcessadorDocumentos\logs\service.err.log`
- `nssm set <NOME> AppRotateFiles 1`
- `nssm set <NOME> AppRotateOnline 1`
- `nssm set <NOME> AppRotateBytes 10485760`   (A1: unidade bytes vs KB incerta — comentar a suposição no script)
- `nssm set <NOME> AppExit Default Restart`
- `nssm set <NOME> AppRestartDelay 5000`
- `nssm set <NOME> AppThrottle 10000`
- `nssm set <NOME> AppEnvironmentExtra USERPROFILE=... LOCALAPPDATA=... APPDATA=... PATH=...` (rede de segurança da Pegadinha 1)
- Controle: `nssm start|stop|restart|status <NOME>` ; `nssm remove <NOME> confirm` (o `confirm` é OBRIGATÓRIO em script).
- Status nativo complementar: `sc query <NOME>`.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Tarefa 1: Criar servico.ps1 — fundação (auto-elevação, garantir nssm.exe, garantir venv legível por SYSTEM, roteador de subcomandos)</name>
  <files>servico.ps1</files>
  <action>
Criar `servico.ps1` na raiz do repositório, em PT-BR, seguindo as convenções dos .ps1 existentes (ver `<interfaces>`): `$ErrorActionPreference = 'Stop'`, caminhos derivados de `$PSScriptRoot`/`$PSCommandPath`, e os três helpers Write-Passo/Write-Aviso/Write-Ok. Compatível com PowerShell 5.1 (Windows PowerShell) — NÃO usar sintaxe exclusiva de PS7 (sem `??`, sem `?.`, sem operador ternário `? :`).

Cabeçalho de comentário explicando: o que o script faz, que produção usa SÓ o serviço, e que a OPENAI_API_KEY nunca é lida/exibida/logada.

Constantes no topo:
- `$RepoRoot = $PSScriptRoot`
- `$BackendDir = Join-Path $RepoRoot 'backend'`
- `$VenvPython = Join-Path $BackendDir '.venv\Scripts\python.exe'`
- `$ToolsDir = Join-Path $RepoRoot 'tools'`
- `$NssmExe = Join-Path $ToolsDir 'nssm.exe'`
- `$ServiceName = 'ProcessadorDocumentos'`
- `$ServiceDisplay = 'Processador de Documentos'`
- `$DataDir = Join-Path $env:ProgramData 'ProcessadorDocumentos'`
- `$LogsDir = Join-Path $DataDir 'logs'`
- `$OutLog = Join-Path $LogsDir 'service.out.log'`
- `$ErrLog = Join-Path $LogsDir 'service.err.log'`
- `$NssmZipUrl = 'https://nssm.cc/release/nssm-2.24.zip'`
- `$HealthUrl = 'http://127.0.0.1:8000/health'`

Aceitar o subcomando como primeiro argumento posicional: `param([Parameter(Position=0)][string]$Comando = 'status')`.

(1) AUTO-ELEVAÇÃO — função `Assert-Admin`: detecta se é Administrador via `([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)`. Se NÃO for, re-lança elevado preservando o subcomando: `Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList @('-ExecutionPolicy','Bypass','-File', $PSCommandPath, $Comando)` e `exit`. Chamar Assert-Admin no início dos subcomandos que exigem privilégio (instalar/iniciar/parar/reiniciar/remover); `status` e `logs` podem rodar sem elevar (mas funcionam elevados também).

(2) GARANTIR NSSM — função `Get-Nssm`: se `Test-Path $NssmExe` e `(Get-Item $NssmExe).Length -gt 0`, usa o vendorizado. Senão, baixa de `$NssmZipUrl` para um ZIP temporário (`Invoke-WebRequest`), extrai (`Expand-Archive`) num diretório temporário, copia `nssm-2.24\win64\nssm.exe` para `$NssmExe` (criar `$ToolsDir` se ausente), limpa os temporários. Validar pós-cópia: `Test-Path $NssmExe` + executar `& $NssmExe version` e confirmar que a saída contém "2.24" (NSSM imprime a versão em stderr/stdout — capturar com `2>&1`); se não conferir, `throw` com mensagem clara. Comentar a suposição A4 (sem hash oficial publicado).

(3) GARANTIR VENV LEGÍVEL POR SYSTEM — função `Ensure-Venv` (Pegadinha 1, mitigação opção 1 do RESEARCH): localizar um Python base instalado all-users e acessível ao LocalSystem (preferir o Python 3.12 do winget; procurar em `C:\Program Files\Python312\python.exe`, `C:\Python312\python.exe`, e como fallback resolver via `where.exe python`/`Get-Command python` confirmando que o caminho NÃO está sob `$env:USERPROFILE`). Garantir `uv` no PATH desta sessão (`$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"`). Criar/garantir o venv a partir desse Python base: `& uv venv --python <python_sistema> (Join-Path $BackendDir '.venv')` se o `.venv` ainda não existir OU se o `python.exe` do venv não existir; depois `& uv sync --project $BackendDir` (checar `$LASTEXITCODE`). Comentar claramente: o objetivo é que `pyvenv.cfg home` aponte para um Python legível por SYSTEM. Se nenhum Python all-users for encontrado, NÃO abortar aqui — avisar (Write-Aviso) que o serviço dependerá da rede de segurança AppEnvironmentExtra + ACL e que o health-check da Tarefa 2 confirmará; seguir adiante.

(4) ROTEADOR DE SUBCOMANDOS — `switch` sobre `$Comando` (lowercase) com casos: instalar, iniciar, parar, reiniciar, status, remover, logs. NESTA tarefa, implementar apenas os corpos triviais (iniciar/parar/reiniciar/status/remover/logs); deixar `instalar` chamando uma função `Invoke-Instalar` cuja implementação completa vem na Tarefa 2 (stub que faz `throw 'implementado na Tarefa 2'` é aceitável temporariamente — mas como esta é a única plano, prefira já deixar a chamada `Invoke-Instalar` definida e implementá-la na Tarefa 2). Default do switch: imprimir uso (lista de subcomandos) e `exit 1`.

Subcomandos de controle (todos chamam `Get-Nssm` para resolver `$NssmExe`; iniciar/parar/reiniciar/remover chamam `Assert-Admin` antes):
- iniciar:   `& $NssmExe start $ServiceName`
- parar:     `& $NssmExe stop $ServiceName`
- reiniciar: `& $NssmExe restart $ServiceName`
- status:    `& $NssmExe status $ServiceName` seguido de `sc.exe query $ServiceName` (saída nativa do SCM como complemento). Não exigir Admin.
- remover:   `& $NssmExe stop $ServiceName` (tolerar erro se já parado, via try/catch) e depois `& $NssmExe remove $ServiceName confirm` (o `confirm` é OBRIGATÓRIO).
- logs:      imprimir os caminhos `$OutLog` e `$ErrLog`; se existirem, `Get-Content -Tail 40` de cada um. NUNCA filtrar/expor conteúdo de chave; apenas exibir as últimas linhas dos logs do serviço (que não contêm a chave). Não exigir Admin.

SEGURANÇA: em nenhum momento ler `backend\.env`, nem imprimir `OPENAI_API_KEY`, nem passar a chave por `AppEnvironmentExtra`.
  </action>
  <verify>
    <automated>bash -c 'set -e; f=servico.ps1; test -f "$f"; grep -q "IsInRole" "$f"; grep -q "Start-Process" "$f"; grep -q "Verb RunAs" "$f"; grep -q "nssm-2.24.zip" "$f"; grep -q "win64" "$f"; grep -q "uv venv" "$f"; grep -q "remove .*confirm\|remove\b" "$f"; for sc in instalar iniciar parar reiniciar status remover logs; do grep -qi "$sc" "$f"; done; po=$(grep -c "Push-Location" "$f" || true); pp=$(grep -c "Pop-Location" "$f" || true); test "$po" = "$pp"; ! grep -qi "OPENAI_API_KEY" "$f"; echo OK_TAREFA1'</automated>
  </verify>
  <done>servico.ps1 existe com auto-elevação (IsInRole + Start-Process -Verb RunAs preservando o subcomando), Get-Nssm (vendor ou download de nssm-2.24.zip → win64\nssm.exe), Ensure-Venv (uv venv a partir de Python all-users + uv sync), roteador com os 7 subcomandos e os controles via nssm. Push/Pop-Location balanceados. Nenhuma menção a OPENAI_API_KEY. PowerShell 5.1-compatível.</done>
</task>

<task type="auto">
  <name>Tarefa 2: Implementar Invoke-Instalar no servico.ps1 (registro NSSM completo + alembic falha-fechada + health-check falha-fechada)</name>
  <files>servico.ps1</files>
  <action>
Implementar a função `Invoke-Instalar` em `servico.ps1` (chamada pelo subcomando `instalar`). Ordem exata e falha-fechada em cada etapa crítica:

(a) `Assert-Admin` (garante elevação).
(b) `Get-Nssm` (garante `$NssmExe`).
(c) `Ensure-Venv` (garante o venv legível por SYSTEM). Após, validar `Test-Path $VenvPython`; se ausente, `throw` claro ("python.exe do venv não encontrado em backend\.venv\Scripts").
(d) Garantir `New-Item -ItemType Directory -Force $LogsDir` (a pasta de logs DEVE existir antes do NSSM gravar).
(e) ALEMBIC FALHA-FECHADA: `Push-Location $BackendDir; try { & uv run alembic upgrade head; if ($LASTEXITCODE -ne 0) { throw "alembic upgrade head falhou (codigo $LASTEXITCODE). Schema NAO aplicado; abortando antes de registrar o serviço." } } finally { Pop-Location }`. Reusar o padrão exato do instalar.ps1 (motivo: alembic precisa do CWD em backend\; servidor não roda alembic).
(f) REGISTRO NSSM (idempotente — se o serviço já existe, reaplicar os `set`; detectar via `& $NssmExe status $ServiceName 2>$null` ou `sc.exe query $ServiceName`). Instalar se ausente: `& $NssmExe install $ServiceName $VenvPython` (ou install só o nome). Depois aplicar TODOS os `set` (ver `<interfaces>` para a lista literal exata):
  - Application = `$VenvPython`
  - AppParameters = `-m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1`
  - AppDirectory = `$BackendDir`
  - DisplayName = `$ServiceDisplay`  ; Description = "Backend FastAPI do Processador de Documentos"
  - Start = `SERVICE_AUTO_START` ; ObjectName = `LocalSystem`
  - AppStdout = `$OutLog` ; AppStderr = `$ErrLog`
  - AppRotateFiles 1 ; AppRotateOnline 1 ; AppRotateBytes 10485760  (comentar A1: unidade bytes vs KB incerta — ~10 MB pretendido)
  - AppExit Default Restart ; AppRestartDelay 5000 ; AppThrottle 10000
  - AppEnvironmentExtra (rede de segurança Pegadinha 1): montar com os valores ABSOLUTOS resolvidos do usuário instalador — `USERPROFILE=$env:USERPROFILE LOCALAPPDATA=$env:LOCALAPPDATA APPDATA=$env:APPDATA PATH=$env:USERPROFILE\.local\bin;$env:Path`. Comentar que NUNCA se passa OPENAI_API_KEY aqui (apareceria no registro do serviço).
  Para args com espaços (DisplayName, Description, AppParameters), passar como string única corretamente citada ao chamar `& $NssmExe set ...`.
(g) INICIAR: `& $NssmExe start $ServiceName`.
(h) HEALTH-CHECK FALHA-FECHADA: fazer polling em `$HealthUrl` por ~30s (loop ~15 tentativas com `Start-Sleep -Seconds 2`), usando `Invoke-WebRequest -UseBasicParsing -TimeoutSec 3` dentro de try/catch; sucesso = status 200. Se ficar saudável: `Write-Ok` com a URL `http://localhost:8000` e instruções de controle. Se NÃO ficar saudável em 30s: `Write-Aviso` com o caminho de `$ErrLog`, imprimir `Get-Content -Tail 30 $ErrLog` (se existir), explicar a causa provável (Pegadinha 1 — venv/Python não legível pelo SYSTEM), e `throw`/`exit 1` com mensagem clara em PT-BR (não deixar serviço quebrado silencioso). Documentar inline que esta verificação é a defesa contra a falha SYSTEM/ACL que só aparece em runtime.

Comentário de bloco antes de Invoke-Instalar reforçando: produção usa SÓ o serviço; NÃO rodar `instalar.ps1` em 1º plano junto (dupla instância → conflito de porta 8000 + SQLite single-writer).
  </action>
  <verify>
    <automated>bash -c 'set -e; f=servico.ps1; grep -q "Invoke-Instalar" "$f"; grep -q "alembic upgrade head" "$f"; grep -q "SERVICE_AUTO_START" "$f"; grep -q "AppExit Default Restart\|AppExit .*Restart" "$f"; grep -q "AppRotateBytes" "$f"; grep -q "AppParameters" "$f"; grep -q "ObjectName .*LocalSystem\|LocalSystem" "$f"; grep -q "AppEnvironmentExtra" "$f"; grep -q "/health\|HealthUrl" "$f"; grep -q "service.err.log\|ErrLog" "$f"; grep -q "Invoke-WebRequest" "$f"; grep -q "Start-Sleep" "$f"; po=$(grep -c "Push-Location" "$f"); pp=$(grep -c "Pop-Location" "$f"); test "$po" = "$pp"; ! grep -qi "OPENAI_API_KEY" "$f"; echo OK_TAREFA2'</automated>
  </verify>
  <done>Invoke-Instalar registra o serviço NSSM completo (Application=venv python, AppParameters uvicorn --workers 1, AppDirectory=backend, logs+rotação, auto-start, LocalSystem, auto-restart, AppEnvironmentExtra sem a chave), roda alembic upgrade head falha-fechada de backend\, inicia o serviço e faz health-check falha-fechada em /health (sai com erro + últimas linhas do service.err.log se falhar). Push/Pop balanceados. Sem OPENAI_API_KEY.</done>
</task>

<task type="auto">
  <name>Tarefa 3: Ajustar empacotar.ps1 (incluir servico.ps1 + tools\nssm.exe no ZIP) e .gitignore (ignorar tools/nssm.exe)</name>
  <files>empacotar.ps1, .gitignore</files>
  <action>
empacotar.ps1 — duas mudanças, preservando a inclusão EXPLÍCITA (allowlist) e o padrão de `throw` em item obrigatório ausente:

(1) Garantir o nssm.exe ANTES de montar o staging. Após o passo de versão (ou logo antes do staging dos scripts da raiz), adicionar um passo `Write-Passo 'Garantindo tools\nssm.exe para o pacote'`: se `tools\nssm.exe` ausente, baixar `https://nssm.cc/release/nssm-2.24.zip` e extrair `win64\nssm.exe` para `tools\nssm.exe` (mesma lógica do Get-Nssm do servico.ps1 — pode duplicar inline aqui, são scripts independentes no pacote). Se o download falhar, `throw` com mensagem clara (o pacote de release PRECISA do nssm.exe).

(2) Adicionar `servico.ps1` à allowlist de scripts da raiz copiados ao staging — alterar o array existente de `@('instalar.ps1', 'atualizar.ps1', 'INSTALL-WINDOWS.md')` para incluir `'servico.ps1'`. E copiar `tools\nssm.exe` para `$staging\tools\nssm.exe` (criar `tools\` no staging, `New-Item -ItemType Directory`, depois `Copy-Item`). Atualizar o comentário "EXCLUSÕES"/"NÃO incluídos" se necessário, mas tools\nssm.exe AGORA É INCLUÍDO explicitamente.

Atenção: NÃO incluir o ZIP nem nssm.exe no controle de versão — apenas no pacote de release. Manter todas as exclusões existentes (.env, .git, .planning, node_modules, frontend\src, tests, *.db*, data).

.gitignore — adicionar uma entrada para o binário de terceiro: `tools/nssm.exe` (e, por segurança, `nssm-*.zip` para não commitar o zip baixado). Adicionar com um comentário em PT-BR explicando que é binário de terceiro, vai só no pacote de release.
  </action>
  <verify>
    <automated>bash -c 'set -e; grep -q "servico.ps1" empacotar.ps1; grep -q "nssm.exe" empacotar.ps1; grep -q "nssm-2.24.zip" empacotar.ps1; grep -q "win64" empacotar.ps1; po=$(grep -c "Push-Location" empacotar.ps1); pp=$(grep -c "Pop-Location" empacotar.ps1); test "$po" = "$pp"; grep -q "nssm.exe" .gitignore; echo OK_TAREFA3'</automated>
  </verify>
  <done>empacotar.ps1 garante tools\nssm.exe (download nssm-2.24.zip → win64) e inclui servico.ps1 + tools\nssm.exe no staging do ZIP, mantendo a allowlist e as exclusões. .gitignore ignora tools/nssm.exe (e nssm-*.zip). Push/Pop balanceados.</done>
</task>

<task type="auto">
  <name>Tarefa 4: Adicionar seção "Rodar sempre em background (serviço Windows)" ao INSTALL-WINDOWS.md (PT-BR)</name>
  <files>INSTALL-WINDOWS.md</files>
  <action>
Adicionar uma nova seção em PT-BR no INSTALL-WINDOWS.md, dentro do Fluxo A (Cliente/produção) — inseri-la após a seção "5. Acessar o sistema" e antes de "6. Atualizar para uma nova versão", OU como uma subseção própria claramente sinalizada. Conteúdo:

Título: "Rodar sempre em background (serviço Windows) — recomendado em produção".

Explicar (linguagem de usuário final, sem jargão excessivo):
- Para que o sistema rode SEMPRE (inicia no boot do Windows, antes do login; reinicia sozinho se cair), instale-o como serviço Windows. Abrir o PowerShell COMO ADMINISTRADOR na pasta extraída e rodar:
  ```powershell
  .\servico.ps1 instalar
  ```
  (o script se auto-eleva pedindo confirmação do UAC se não estiver como Admin).
- O instalar do serviço cuida de tudo: garante o nssm.exe, prepara o ambiente Python acessível ao serviço, aplica o schema do banco e registra/inicia o serviço `ProcessadorDocumentos`. Ao final faz uma verificação de saúde em `http://localhost:8000/health`.
- Comandos de controle (tabela ou lista):
  - `.\servico.ps1 status`    — mostra se está rodando
  - `.\servico.ps1 parar`     — para o serviço
  - `.\servico.ps1 iniciar`   — inicia o serviço
  - `.\servico.ps1 reiniciar` — reinicia o serviço
  - `.\servico.ps1 logs`      — mostra onde estão os logs e as últimas linhas
  - `.\servico.ps1 remover`   — para e remove o serviço
- Onde ficam os logs do serviço:
  ```
  %ProgramData%\ProcessadorDocumentos\logs\service.out.log
  %ProgramData%\ProcessadorDocumentos\logs\service.err.log
  ```
  (com rotação automática quando crescem).
- AVISO (destacar em bloco `>`): NÃO rode o `instalar.ps1` em primeiro plano enquanto o serviço estiver instalado/rodando — isso sobe uma SEGUNDA instância na porta 8000 e causa conflito (porta ocupada + escrita concorrente no banco SQLite). Em produção, use APENAS o serviço (`servico.ps1`). O `instalar.ps1` em 1º plano é só para teste rápido / desenvolvimento.
- RISCO CONHECIDO (bloco `>`): o serviço roda como conta do sistema (LocalSystem). Em casos raros, o ambiente Python pode não ficar acessível a essa conta — por isso o `servico.ps1 instalar` faz a verificação de saúde e AVISA com o caminho do `service.err.log` se algo falhar. Se a instalação do serviço reportar falha de saúde, abra esse log para diagnóstico (ou rode `.\servico.ps1 logs`).

Opcional (Troubleshooting): acrescentar uma entrada curta "O serviço não inicia / health-check falhou" apontando para `service.err.log` e a causa provável (ambiente Python não acessível ao serviço).

Não alterar as seções existentes além da inserção. Manter o estilo/formatação Markdown do arquivo.
  </action>
  <verify>
    <automated>bash -c 'set -e; grep -qi "servi[çc]o" INSTALL-WINDOWS.md; grep -q "servico.ps1 instalar" INSTALL-WINDOWS.md; grep -q "service.err.log" INSTALL-WINDOWS.md; grep -qi "primeiro plano\|1º plano\|1. plano" INSTALL-WINDOWS.md; grep -q "ProcessadorDocumentos" INSTALL-WINDOWS.md; for c in status parar iniciar reiniciar logs remover; do grep -q "servico.ps1 $c" INSTALL-WINDOWS.md; done; echo OK_TAREFA4'</automated>
  </verify>
  <done>INSTALL-WINDOWS.md tem a seção de serviço Windows em PT-BR: como instalar (Admin), os 7 subcomandos de controle, caminho dos logs, o AVISO de não rodar instalar.ps1 em 1º plano junto, e o RISCO CONHECIDO do LocalSystem + health-check.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| download nssm.cc → tools\nssm.exe | binário de terceiro baixado pela rede entra na máquina e é registrado como serviço |
| script PowerShell → SCM (serviço Windows) | servico.ps1 elevado registra/controla um serviço que roda como LocalSystem |
| backend\.env (segredo) → registro do serviço / logs | risco de vazamento de OPENAI_API_KEY se passada por AppEnvironmentExtra ou logada |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-kly-01 | Tampering | download de nssm-2.24.zip (HTTP→HTTPS) sem hash canônico | accept | Sem hash oficial publicado (A4). Mitigação parcial: URL HTTPS fixa de nssm.cc + validação `nssm version` contém "2.24" + Length>0. Risco residual aceito (binário público estável desde 2014). |
| T-kly-02 | Information Disclosure | OPENAI_API_KEY exposta no registro do serviço (AppEnvironmentExtra) ou nos logs | mitigate | servico.ps1 NUNCA lê backend\.env nem passa a chave por AppEnvironmentExtra; serviço lê a chave via CWD (backend\.env). Subcomando `logs` só exibe service.out/err.log (sem a chave). Gate de verificação: `! grep -qi OPENAI_API_KEY servico.ps1`. |
| T-kly-03 | Elevation of Privilege | auto-elevação via Start-Process -Verb RunAs | accept | Padrão consagrado; UAC do Windows controla o consentimento. Subcomando preservado literalmente (sem injeção de args arbitrários — só o token de subcomando do switch). |
| T-kly-04 | Denial of Service | dupla instância (serviço + instalar.ps1 em 1º plano) → porta 8000 + SQLite single-writer | mitigate | Documentado como AVISO destacado no INSTALL-WINDOWS.md; produção usa só o serviço. Health-check falha-fechada detecta serviço não saudável. |
| T-kly-05 | Denial of Service | serviço sobe mas backend quebrado sob LocalSystem (Pegadinha 1, ACL do venv) fica em loop de restart silencioso | mitigate | Health-check falha-fechada em /health por ~30s no instalar; em falha, exibe service.err.log e sai com erro (não deixa quebrado silencioso). Ensure-Venv usa Python all-users para reduzir a chance. |
| T-kly-SC | Tampering | nssm.exe (binário) versionado/empacotado | mitigate | .gitignore ignora tools/nssm.exe + nssm-*.zip (nunca versionado); entra só no pacote de release via empacotar.ps1 (allowlist explícita). |
</threat_model>

<verification>
Ambiente de dev NÃO tem Windows nem pwsh — verificação é ESTÁTICA + roteiro manual:

Estática (automatizada nos `<verify>` de cada tarefa): existência de arquivos; presença dos comandos NSSM literais; subcomandos roteados; auto-elevação (IsInRole + RunAs); download/extração win64 do nssm; uv venv a partir de Python all-users; alembic falha-fechada; health-check (/health + service.err.log); Push/Pop-Location balanceados; ausência total de OPENAI_API_KEY nos scripts; .gitignore ignora nssm.exe; empacotar inclui servico.ps1 + tools\nssm.exe; guia em PT-BR com os subcomandos + avisos.

Roteiro manual para o usuário (numa máquina Windows real — documentar no SUMMARY como pendência de verificação):
1. Extrair um pacote de release; abrir PowerShell como Admin; `.\servico.ps1 instalar`.
2. Confirmar que termina com health-check OK e `http://localhost:8000` abre.
3. `.\servico.ps1 status` → SERVICE_RUNNING. Reiniciar o Windows → o serviço sobe sozinho antes do login.
4. Matar o processo python do serviço → confirmar auto-restart (~5s).
5. `.\servico.ps1 logs` mostra service.out/err.log; `.\servico.ps1 reiniciar`/`parar`/`iniciar` funcionam; `.\servico.ps1 remover` para e remove.
6. Confirmar empíricamente A1 (AppRotateBytes em bytes vs KB) gerando log grande.
</verification>

<success_criteria>
- servico.ps1 existe na raiz com os 7 subcomandos (instalar|iniciar|parar|reiniciar|status|remover|logs), auto-elevação, Get-Nssm, Ensure-Venv, Invoke-Instalar com alembic + registro NSSM completo + health-check falha-fechada.
- Serviço configurado: Application=venv python.exe, AppParameters uvicorn --workers 1, AppDirectory=backend, SERVICE_AUTO_START, LocalSystem, auto-restart, logs com rotação em %ProgramData%\...\logs, AppEnvironmentExtra (sem a chave).
- empacotar.ps1 inclui servico.ps1 + tools\nssm.exe no ZIP (garantindo o download do nssm se ausente).
- .gitignore ignora tools/nssm.exe (e nssm-*.zip).
- INSTALL-WINDOWS.md documenta a seção de serviço em PT-BR com o aviso de não rodar instalar.ps1 em 1º plano junto e o risco conhecido do LocalSystem.
- Nenhum script lê/exibe/loga OPENAI_API_KEY.
- Scripts PowerShell 5.1-compatíveis; Push/Pop-Location balanceados.
</success_criteria>

<output>
Create `.planning/quick/260623-kly-servico-windows-via-nssm-servico-ps1-ins/260623-kly-SUMMARY.md` when done.
No SUMMARY de verificação, REGISTRAR a pendência de teste manual no Windows (não há Windows/pwsh no ambiente de dev) e a suposição A1 (AppRotateBytes bytes vs KB) a confirmar na máquina.
</output>
