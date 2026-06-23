---
phase: quick-260623-mod
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - instalar.ps1
  - atualizar.ps1
  - servico.ps1
  - INSTALL-WINDOWS.md
autonomous: true
requirements: [LOG-01, LOG-02, FIX-01, DOC-01]

must_haves:
  truths:
    - "Cada execução de instalar.ps1 / atualizar.ps1 / servico.ps1 grava um log timestampado em %ProgramData%\\ProcessadorDocumentos\\logs\\"
    - "Mesmo que o script falhe e a janela feche, o caminho do log é impresso de forma destacada no fim (sucesso OU erro) e o log fica gravado em disco"
    - "Se o Start-Transcript falhar (sem permissão), o script segue normalmente sem logging (fail-soft) — o log nunca quebra o script"
    - "servico.ps1 diagnostico gera UM relatório único em logs\\ com versões, caminhos, estado de persistência, rede/health e tails — SEM jamais incluir a chave da IA ou conteúdo do .env"
    - "servico.ps1 -Modo servico explícito é respeitado nos subcomandos de controle (bug do Resolve-ModoInstalado corrigido)"
    - "INSTALL-WINDOWS.md ensina onde ficam os logs, que cada execução gera um, e como rodar/enviar o diagnostico"
  artifacts:
    - path: "instalar.ps1"
      provides: "Transcript fail-soft + finally Stop-Transcript + impressão do caminho do log"
      contains: "Start-Transcript"
    - path: "atualizar.ps1"
      provides: "Transcript fail-soft + finally Stop-Transcript + impressão do caminho do log"
      contains: "Start-Transcript"
    - path: "servico.ps1"
      provides: "Transcript por subcomando + subcomando diagnostico + fix do Resolve-ModoInstalado"
      contains: "diagnostico"
    - path: "INSTALL-WINDOWS.md"
      provides: "Seção de troubleshooting sobre logs e diagnostico"
      contains: "diagnostico"
  key_links:
    - from: "instalar.ps1 / atualizar.ps1 / servico.ps1"
      to: "%ProgramData%\\ProcessadorDocumentos\\logs\\"
      via: "New-Item -Force + Start-Transcript em arquivo timestampado"
      pattern: "Start-Transcript"
    - from: "servico.ps1 diagnostico"
      to: "logs\\diagnostico-*.log"
      via: "switch de roteamento → coleta → grava arquivo único + imprime caminho"
      pattern: "diagnostico"
---

<objective>
Dar VISIBILIDADE de depuração às instalações Windows remotas. Hoje, quando um dos
scripts PowerShell falha, o terminal fecha (duplo-clique) e a mensagem de erro se
perde — o dev (sem Windows) fica cego. Este plano adiciona:

1. **Log de transcrição** em `instalar.ps1`, `atualizar.ps1` e `servico.ps1`:
   cada execução grava um arquivo timestampado em
   `%ProgramData%\ProcessadorDocumentos\logs\` e imprime o caminho no fim
   (sucesso OU erro), com **fail-soft** (logging nunca quebra o script).
2. **Novo subcomando `servico.ps1 diagnostico`** que coleta um relatório único
   (versões, caminhos, persistência, rede, tails de logs) para o usuário enviar ao
   suporte — **sem jamais expor a chave da IA / o conteúdo do .env**.
3. **Fix do bug `Resolve-ModoInstalado`** (hoje `-Modo` explícito é ignorado).
4. **Guia `INSTALL-WINDOWS.md`** com a seção de troubleshooting dos logs.

Purpose: depurar instalações remotas onde a janela fecha e a mensagem some.
Output: 3 scripts .ps1 com transcript + novo subcomando + fix, e o guia atualizado.

Restrição transversal CRÍTICA (todas as tarefas): a chave da IA (`backend\.env`)
NUNCA pode aparecer no transcript nem no diagnóstico. Os scripts JÁ não leem nem
ecoam o `.env`; manter assim. O transcript captura apenas comandos+saída desses
scripts de controle (que não tocam a chave), não o runtime do servidor.

Contexto de plataforma: Windows PowerShell 5.1+. `Start-Transcript`/`Stop-Transcript`,
`Get-Date`, `Get-ScheduledTask`, `Get-NetTCPConnection` existem no 5.1. O dev NÃO
tem Windows → verificação é ESTÁTICA (greps) + roteiro de teste manual no SUMMARY.

Fora de escopo (feito pelo orquestrador no empacotamento): bump de versão
0.1.3 → 0.1.4. NÃO commitar nssm.exe/.zip.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md

# Scripts a modificar (ler antes de editar — padrões a preservar):
@instalar.ps1
@atualizar.ps1
@servico.ps1
@INSTALL-WINDOWS.md

<interfaces>
<!-- Padrões e identificadores já presentes nos scripts; reusar SEM reinventar. -->

Helpers de saída (idênticos nos 3 scripts):
  function Write-Passo($texto) -> "`n==> $texto" (Cyan)
  function Write-Aviso($texto) -> "[AVISO] $texto" (Yellow)
  function Write-Ok($texto)    -> "[OK] $texto"   (Green)

Caminho de dados (servico.ps1 já o deriva):
  $DataDir = Join-Path $env:ProgramData 'ProcessadorDocumentos'
  $LogsDir = Join-Path $DataDir 'logs'
  -> logs de instalação/diagnóstico vão em $LogsDir (%ProgramData%, all-users,
     diferente do $TaskLogsDir do runtime que é %LOCALAPPDATA%).
  instalar.ps1 / atualizar.ps1 NÃO têm $DataDir/$LogsDir — derivar via
  $env:ProgramData (config.py confirma: _default_data_dir usa %ProgramData%).

servico.ps1 — identificadores relevantes para o diagnostico:
  $RepoRoot, $BackendDir, $ToolsDir, $VenvPython (.venv\Scripts\python.exe),
  $VenvPythonw, $NssmExe (tools\nssm.exe), $Launcher (tools\iniciar-servidor.py),
  $HealthUrl ('http://127.0.0.1:8000/health'),
  $ServiceName ('ProcessadorDocumentos'), $TaskName ('ProcessadorDocumentos-Servidor'),
  $OutLog/$ErrLog (service.{out,err}.log em %ProgramData%),
  $TaskLog (servidor.log em %LOCALAPPDATA%).
  function Test-TaskExists / Test-ServiceExists (já existem).
  function Resolve-ModoInstalado (com o BUG a corrigir, linhas ~208-213).

servico.ps1 — pontos de inserção do roteador (fim do arquivo):
  - bloco "if ($cmd -eq 'instalar') { ... return }" (~450)
  - "switch ($cmd) { { $_ -in 'iniciar','parar','reiniciar','status','remover','logs' } ..." (~455)
  - bloco "default { Write-Host 'Uso: ...' }" (~500-523) — texto de ajuda.

Heurística do bug Resolve-ModoInstalado:
  Hoje usa `$PSBoundParameters.ContainsKey('Modo')` DENTRO da função — ali
  $PSBoundParameters é o da FUNÇÃO (vazia), nunca o do script. Logo `-Modo`
  explícito jamais é respeitado. Corrigir capturando no CORPO do script (fora de
  função), ex.: `$script:ModoExplicito = $PSBoundParameters.ContainsKey('Modo')`,
  e a função consulta `$script:ModoExplicito`.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Transcript fail-soft em instalar.ps1 e atualizar.ps1</name>
  <files>instalar.ps1, atualizar.ps1</files>
  <action>
Em CADA um dos dois scripts, adicionar logging de transcrição que envolve TODO o
corpo principal, com fail-soft e impressão do caminho no fim.

Passos por script:

1. Logo APÓS o param block / `$ErrorActionPreference = 'Stop'` (em instalar.ps1 não
   há param block — inserir após a linha de ErrorActionPreference; em atualizar.ps1
   inserir após `param([string]$LocalZip)` e o ErrorActionPreference), e ANTES das
   funções Write-* serem usadas, montar o caminho do log:
   - Derivar `$LogsDir = Join-Path (Join-Path $env:ProgramData 'ProcessadorDocumentos') 'logs'`
     (instalar.ps1 e atualizar.ps1 NÃO têm $DataDir; derivar inline aqui).
   - Timestamp: `$ts = Get-Date -Format 'yyyyMMdd-HHmmss'`.
   - Nome do arquivo: instalar.ps1 → `instalar-$ts.log`; atualizar.ps1 → `atualizar-$ts.log`.
   - `$LogFile = Join-Path $LogsDir "<nome>"`.

2. Iniciar o transcript com FAIL-SOFT, guardando se ligou:
   - `$transcriptOn = $false`
   - try: `New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null` e
     `Start-Transcript -Path $LogFile -Force | Out-Null`; em sucesso `$transcriptOn = $true`.
   - catch: emitir um aviso simples via Write-Host amarelo "[AVISO] Nao foi possivel
     iniciar o log de execucao (seguindo sem log): <mensagem>" e CONTINUAR.
   - IMPORTANTE: `-Force` no Start-Transcript evita o erro "transcript ja em
     andamento"; ainda assim o catch protege contra sessao com transcript ativo.
   - As funções Write-Passo/Aviso/Ok são definidas DEPOIS no arquivo; portanto neste
     bloco inicial use `Write-Host ... -ForegroundColor Yellow` direto (não chame os
     helpers ainda não definidos). Alternativa aceitável: MOVER as definições dos 3
     helpers Write-* para ANTES deste bloco e então usá-los — escolha a que deixar o
     diff mais limpo, mas NÃO referencie helper antes de definido.

3. Envolver o RESTANTE do corpo do script num `try { ... } finally { ... }`:
   - O `try` abarca toda a lógica existente do script (do passo 1/Python até o
     `uv run uvicorn ...` final). NÃO altere a lógica interna — apenas indente/embrulhe.
   - O `finally` faz:
     a) Se `$transcriptOn`: imprimir DESTACADO o caminho do log ANTES de parar o
        transcript (para o caminho entrar no próprio log):
          Write-Host '' ; Write-Host ("Log desta execucao: " + $LogFile) -ForegroundColor Cyan ; Write-Host ''
     b) Se `$transcriptOn`: `try { Stop-Transcript | Out-Null } catch { }` (Stop tolerante).
   - ATENÇÃO ao `uv run uvicorn ...` final: ele é BLOQUEANTE (servidor em foreground).
     O bloco já existe DENTRO de um `Push-Location $BackendDir; try { ... } finally
     { Pop-Location }`. O novo try/finally do transcript deve ENVOLVER esse bloco
     Push/Pop inteiro. Em Ctrl+C / erro, o finally do transcript ainda roda e imprime
     o caminho do log. Manter o Push/Pop existente intacto dentro do novo try.

4. NÃO ecoar conteúdo do `.env`: nenhum dos dois scripts lê o `.env` hoje (instalar.ps1
   só faz Copy-Item do .env.example e avisa) — preservar. Não adicionar nada que leia
   ou imprima o `.env`.

Tudo em PT-BR (mensagens ao usuário). Não usar sintaxe PS7-only (`??`, `?.`, ternário).
  </action>
  <verify>
    <automated>bash -c 'set -e; for f in instalar.ps1 atualizar.ps1; do echo "== $f =="; grep -c "Start-Transcript" "$f"; grep -v "^#" "$f" | grep -c "Stop-Transcript"; grep -c "transcriptOn" "$f"; grep -c "Log desta execucao" "$f"; grep -c "finally" "$f"; done; echo "== sem leitura de .env (apenas .env.example permitido) =="; ! grep -nE "Get-Content[^#]*\\.env([^.]|$)" instalar.ps1 atualizar.ps1'</automated>
  </verify>
  <done>
Ambos os scripts: 1+ Start-Transcript, 1+ Stop-Transcript (fora de comentário),
flag $transcriptOn, impressão "Log desta execucao:", try/finally presente, e nenhum
Get-Content do `.env` (só .env.example é tolerado). Lógica original intacta.
  </done>
</task>

<task type="auto">
  <name>Task 2: Transcript por subcomando + fix Resolve-ModoInstalado em servico.ps1</name>
  <files>servico.ps1</files>
  <action>
Duas mudanças no servico.ps1 (a 3ª, o subcomando diagnostico, fica na Task 3).

PARTE A — Transcript por subcomando (fail-soft, finally, caminho impresso):

1. servico.ps1 JÁ deriva `$DataDir` e `$LogsDir` (linhas ~66-67). Reusar `$LogsDir`.
2. Após o param block + constantes + DEFINIÇÃO dos helpers Write-* (que já vêm cedo,
   linhas ~79-81), e ANTES do roteador de subcomandos no fim do arquivo, montar:
   - `$ts = Get-Date -Format 'yyyyMMdd-HHmmss'`
   - `$cmdSlug = $Comando.ToLower()` (sanitizar para nome de arquivo: manter só
     [a-z]; ex.: via `($Comando.ToLower() -replace '[^a-z]','')`; se vazio, usar 'cmd').
   - `$LogFile = Join-Path $LogsDir ("servico-" + $cmdSlug + "-" + $ts + ".log")`
   - `$transcriptOn = $false`
   - try: `New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null` +
     `Start-Transcript -Path $LogFile -Force | Out-Null`; sucesso → `$transcriptOn=$true`.
   - catch: `Write-Aviso "Nao foi possivel iniciar o log desta execucao (seguindo sem log): $($_.Exception.Message)"`
     (aqui Write-Aviso JÁ existe — pode usar).
3. Envolver TODO o roteador de subcomandos (do `$cmd = $Comando.ToLower()` ~448 até o
   fim do `switch`/`default`) num `try { ... } finally { ... }`:
   - finally: se `$transcriptOn` → imprimir `Write-Host ("`nLog desta execucao: " +
     $LogFile + "`n") -ForegroundColor Cyan` e depois `try { Stop-Transcript | Out-Null } catch { }`.
   - CUIDADO com os `return` e `exit` existentes dentro do roteador:
     * O bloco `if ($cmd -eq 'instalar') { ...; return }` usa `return` — em script de
       nível superior `return` encerra o script e o `finally` AINDA roda (ok).
     * O `default { ...; exit 1 }` usa `exit` — `exit` NÃO roda o `finally` do
       try/finally. Para o caminho de uso inválido ainda fechar o transcript,
       SUBSTITUIR esse `exit 1` por: parar o transcript inline antes de sair, OU
       trocar `exit 1` por `$global:LASTEXITCODE = 1; return`. Escolher `return`
       (deixa o finally rodar e imprime o caminho do log). Garantir que o restante do
       comportamento (texto de ajuda) seja preservado.
   - A auto-elevação (`Assert-Admin` → `Start-Process ... RunAs; exit`) acontece
     DENTRO de funções chamadas pelo roteador. Quando ela faz `exit`, o transcript do
     processo NÃO-elevado fecha sem o finally — ACEITÁVEL: o processo elevado (re-lançado)
     abre o SEU PRÓPRIO transcript (mesmo subcomando) e registra o que importa. Não
     tentar coordenar transcript entre processos; apenas garantir que cada processo
     que chega ao roteador inicie o seu. (Documentar isso como nota no SUMMARY.)

PARTE B — Fix do bug Resolve-ModoInstalado:

4. No CORPO do script (nível superior, fora de qualquer função — colocar logo após o
   `param(...)` block ou junto das constantes), capturar:
     `$script:ModoExplicito = $PSBoundParameters.ContainsKey('Modo')`
   (no corpo do script, `$PSBoundParameters` reflete os parâmetros REAIS do script).
5. Alterar `Resolve-ModoInstalado` para consultar `$script:ModoExplicito` em vez de
   `$PSBoundParameters.ContainsKey('Modo')`:
     if ($script:ModoExplicito) { return $Modo }
   Manter o resto da função idêntico (Test-TaskExists → 'tarefa'; Test-ServiceExists
   → 'servico'; default 'tarefa'). Comportamento padrão (sem -Modo) inalterado.

Tudo PT-BR; sem sintaxe PS7-only. NÃO ler/ecoar o `.env`.
  </action>
  <verify>
    <automated>bash -c 'set -e; f=servico.ps1; echo "== transcript =="; grep -c "Start-Transcript" "$f"; grep -v "^#" "$f" | grep -c "Stop-Transcript"; grep -c "transcriptOn" "$f"; grep -c "Log desta execucao" "$f"; echo "== fix Resolve-ModoInstalado =="; grep -c "ModoExplicito" "$f"; echo "== bug antigo eliminado (ContainsKey Modo nao deve sobrar dentro da funcao) =="; ! grep -nE "PSBoundParameters\\.ContainsKey\\(.Modo.\\)" "$f" | grep -vi "ModoExplicito" | grep -q "return \$Modo"; echo "== exit 1 do default trocado por return (finally roda) =="; grep -c "ModoExplicito" "$f"'</automated>
  </verify>
  <done>
servico.ps1: Start-Transcript/Stop-Transcript presentes, $transcriptOn e
"Log desta execucao:" impresso no finally, $script:ModoExplicito capturado no corpo
e consultado por Resolve-ModoInstalado, e o `exit 1` do default substituído por
`return` (para o finally fechar o transcript). Comportamento padrão preservado.
  </done>
</task>

<task type="auto">
  <name>Task 3: Subcomando servico.ps1 diagnostico (relatório único, sem segredos)</name>
  <files>servico.ps1</files>
  <action>
Adicionar o subcomando `diagnostico` que coleta um relatório ÚNICO em
`$LogsDir\diagnostico-<ts>.log` e imprime o caminho. NUNCA inclui a chave da IA nem
o conteúdo do `.env`.

1. Criar `function Invoke-Diagnostico` (junto das demais funções, antes do roteador):
   - Timestamp próprio: `$dts = Get-Date -Format 'yyyyMMdd-HHmmss'`.
   - `$relatorio = Join-Path $LogsDir ("diagnostico-" + $dts + ".log")`.
   - `New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null`.
   - Construir o conteúdo numa lista de strings (`$linhas = New-Object System.Collections.Generic.List[string]`)
     e ao final gravar com `Set-Content -Path $relatorio -Encoding UTF8 -Value $linhas`.
   - Cada coletor abaixo deve ser envolvido em try/catch individual: uma falha de
     coleta vira uma linha "(nao foi possivel coletar: <msg>)" e NÃO aborta o relatório.
   - Coletar (TODOS apenas caminhos/estados — SEM SEGREDOS):
     a) Cabeçalho: data/hora, "Processador de Documentos — diagnostico".
     b) Ambiente: `$PSVersionTable.PSVersion`; OS via
        `Get-CimInstance Win32_OperatingSystem` → Caption + Version.
     c) Caminhos e existência (Test-Path por item, imprimindo "[OK]/[FALTA] <caminho>"):
        $RepoRoot, $BackendDir, $VenvPython, $VenvPythonw, $NssmExe, $Launcher,
        $BackendDir\.env (apenas EXISTE sim/não — NUNCA o conteúdo).
     d) Python/uv:
        - `uv --version` se `Get-Command uv` existir (senão "(uv nao encontrado)").
        - Se $VenvPython existe: rodar `& $VenvPython -c "import sys;print(sys.executable)"`
          e registrar o caminho (sys.executable real do venv).
        - `pyvenv.cfg` do venv (Join-Path $BackendDir '.venv\pyvenv.cfg'): se existir,
          extrair APENAS a linha que começa com 'home' (Get-Content | Where-Object
          { $_ -like 'home*' }) — relevante p/ Pegadinha 1. Não despejar o arquivo todo.
     e) Persistência:
        - Tarefa: se Test-TaskExists → Get-ScheduledTask + Get-ScheduledTaskInfo →
          State, LastRunTime, LastTaskResult. Senão "(Tarefa nao instalada)".
        - Serviço: se Test-ServiceExists → `& $NssmExe status $ServiceName` e
          `& sc.exe query $ServiceName`. Senão "(Servico NSSM nao instalado)".
     f) Rede:
        - Porta 8000: `Get-NetTCPConnection -LocalPort 8000 -State Listen
          -ErrorAction SilentlyContinue` → sim/não + OwningProcess se houver.
        - Health: `Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 3`
          → StatusCode (try/catch → "(health nao respondeu)").
     g) Tails (últimas ~40 linhas, só se o arquivo existir, via Get-Content -Tail 40):
        - $TaskLog (servidor.log, modo tarefa).
        - $OutLog e $ErrLog (modo servico).
        - Último log de instalação: o `instalar-*.log` mais recente em $LogsDir
          (`Get-ChildItem $LogsDir -Filter 'instalar-*.log' | Sort-Object
          LastWriteTime -Descending | Select-Object -First 1`); se houver, tail 40.
     h) Rodapé: linha explícita "NENHUM valor de .env / chave da IA foi incluido neste
        relatorio." (confirmação para o usuário/suporte).
   - Ao final: imprimir no console DESTACADO o caminho:
     `Write-Ok "Diagnostico gravado."` + `Write-Host ("Envie este arquivo ao suporte: " + $relatorio) -ForegroundColor Cyan`.
   - GARANTIR que NENHUM coletor leia `$EnvFile`/`.env` conteúdo nem
     `$env:OPENAI_API_KEY`. Não imprimir `$env:*` em massa (nada de Get-ChildItem Env:).

2. Registrar `diagnostico` no roteador:
   - Adicionar `diagnostico` à lista do `{ $_ -in 'iniciar','parar',... }`? NÃO —
     diagnostico é INDEPENDENTE de modo (coleta os dois). Em vez disso, adicionar um
     ramo dedicado ANTES desse switch (ou um case próprio) que chama
     `Invoke-Diagnostico` sem exigir Assert-Admin e sem Resolve-ModoInstalado.
     Sugestão: logo após o bloco `if ($cmd -eq 'instalar') { ... return }`, adicionar
     `if ($cmd -eq 'diagnostico') { Invoke-Diagnostico; return }` (o finally do
     transcript da Task 2 ainda fecha o log da própria execução do diagnostico).
3. Atualizar a AJUDA (`default { Write-Host 'Uso...' }`) e o cabeçalho de comentários
   do topo do arquivo (lista "Subcomandos") incluindo:
   `diagnostico  gera um relatorio unico (sem segredos) p/ enviar ao suporte`.

Tudo PT-BR; sem sintaxe PS7-only; nenhum `.env`/chave no relatório.
  </action>
  <verify>
    <automated>bash -c 'set -e; f=servico.ps1; echo "== subcomando diagnostico =="; grep -c "Invoke-Diagnostico" "$f"; grep -c "diagnostico-" "$f"; grep -c "eq .diagnostico." "$f" || grep -c "diagnostico" "$f"; echo "== conteudo do relatorio =="; grep -c "Win32_OperatingSystem" "$f"; grep -c "Get-NetTCPConnection" "$f"; grep -c "pyvenv.cfg" "$f"; grep -c "Get-ScheduledTaskInfo" "$f"; echo "== confirmacao sem segredos no rodape =="; grep -ci "NENHUM valor de .env" "$f"; echo "== nao le conteudo do .env nem dump de Env: =="; ! grep -nE "Get-Content[^#]*EnvFile|Get-ChildItem[[:space:]]+Env:|OPENAI_API_KEY" "$f"; echo "== ajuda menciona diagnostico =="; grep -c "diagnostico" "$f"'</automated>
  </verify>
  <done>
servico.ps1 tem Invoke-Diagnostico que grava diagnostico-<ts>.log com versões
(PSVersion + Win32_OperatingSystem), caminhos/existência, sys.executable + home do
pyvenv.cfg, estado de Tarefa/Serviço, porta 8000 + /health, tails de servidor.log /
service.{out,err}.log / último instalar-*.log, e rodapé confirmando ausência de
segredos. Roteado via `diagnostico`, presente na ajuda. Nenhuma leitura de .env/chave.
  </done>
</task>

<task type="auto">
  <name>Task 4: Troubleshooting de logs e diagnostico no INSTALL-WINDOWS.md</name>
  <files>INSTALL-WINDOWS.md</files>
  <action>
Atualizar o guia (PT-BR) para ensinar o usuário a achar e enviar os logs.

1. Na seção `## Troubleshooting`, adicionar uma subseção nova
   `### Logs de execução dos scripts e diagnóstico` (pode ficar logo após
   "### O servidor não inicia em background / health-check falhou", antes de
   "### Onde ficam os dados e os logs"), explicando:
   - Que CADA execução de `instalar.ps1`, `atualizar.ps1` e `servico.ps1` agora grava
     um **log de execução** timestampado em:
     `%ProgramData%\ProcessadorDocumentos\logs\`
     com nomes `instalar-AAAAMMDD-HHMMSS.log`, `atualizar-...log`,
     `servico-<comando>-...log`.
   - Que, mesmo se a janela do PowerShell **fechar** após um erro, o **arquivo de log
     fica gravado** lá — e o caminho do log também é **impresso no fim** de cada
     execução ("Log desta execucao: ...").
   - **Dica para não perder a mensagem na hora:** abrir o **PowerShell manualmente**
     (menu Iniciar → PowerShell) e rodar o script de lá (ex.: `.\instalar.ps1`) em vez
     de dar **duplo-clique** — assim a janela **não fecha** ao terminar/errar.
   - Como gerar e enviar um **diagnóstico** ao suporte:
     ```powershell
     .\servico.ps1 diagnostico
     ```
     Explicar que isso gera UM arquivo único
     `%ProgramData%\ProcessadorDocumentos\logs\diagnostico-AAAAMMDD-HHMMSS.log`
     com versões, caminhos, estado da instalação, rede e trechos dos logs — e que o
     comando **imprime o caminho do arquivo** ao final, bastando **anexar esse
     arquivo** no contato com o suporte.
   - Reforçar a **segurança**: o log de execução e o diagnóstico **nunca incluem a
     chave da OpenAI** nem o conteúdo do `backend\.env` — pode enviar sem expor o
     segredo.
2. Opcional/coerência: na seção "### Onde ficam os dados e os logs", acrescentar uma
   linha apontando que os logs de execução dos scripts ficam na subpasta `logs\`
   dessa mesma pasta `%ProgramData%\ProcessadorDocumentos`.

Manter o tom e a formatação Markdown existentes (cabeçalhos, blocos ```powershell```,
blockquotes `>`). Não alterar outras seções.
  </action>
  <verify>
    <automated>bash -c 'set -e; f=INSTALL-WINDOWS.md; echo "== mencoes =="; grep -ci "logs de execu" "$f"; grep -c "diagnostico" "$f"; grep -c "ProcessadorDocumentos\\\\logs" "$f" || grep -c "logs" "$f"; echo "== dica duplo-clique / powershell manual =="; grep -ci "duplo-clique" "$f"; echo "== seguranca: sem chave =="; grep -ci "nunca inclu" "$f" || grep -ci "chave" "$f"'</automated>
  </verify>
  <done>
INSTALL-WINDOWS.md ganhou subseção de troubleshooting explicando os logs de execução
timestampados em %ProgramData%\...\logs\, a dica de abrir o PowerShell manualmente
para a janela não fechar, o comando `.\servico.ps1 diagnostico` e o anexo do arquivo
gerado, e a garantia de que log/diagnóstico não expõem a chave/.env.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| script PowerShell → disco (logs) | transcript/diagnóstico gravam em %ProgramData%\...\logs\ — devem NUNCA conter o segredo da IA |
| relatório de diagnóstico → suporte (humano externo) | arquivo enviado para fora da máquina; não pode vazar `.env`/chave |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-quick-01 | Information Disclosure | Start-Transcript (3 scripts) | mitigate | Os scripts não leem nem ecoam o `.env`/chave; o transcript captura só comandos+saída desses scripts de controle. Verify de cada task barra `Get-Content` do `.env` e leitura de `OPENAI_API_KEY`. |
| T-quick-02 | Information Disclosure | Invoke-Diagnostico | mitigate | Coletores restritos a versões/caminhos/estados; `.env` reportado só como EXISTE sim/não; rodapé confirma ausência de segredos; verify barra leitura de $EnvFile, `Get-ChildItem Env:` e `OPENAI_API_KEY`. |
| T-quick-03 | Denial of Service | Start-Transcript sem permissão | accept→mitigate | Fail-soft: try/catch em volta do Start-Transcript; falha vira aviso e o script segue sem log — logging NUNCA derruba o script. |
| T-quick-04 | Tampering | npm/pip/cargo installs | accept | Plano não instala nenhum pacote (só edita .ps1/.md); sem superfície de supply-chain. |
</threat_model>

<verification>
Verificação ESTÁTICA (o dev não tem Windows) — os `<automated>` greps de cada task
cobrem:
- Start-Transcript + Stop-Transcript(fora de comentário) + $transcriptOn +
  "Log desta execucao:" nos 3 scripts.
- try/finally presente (transcript fecha mesmo em erro).
- Ausência de leitura do `.env`/chave (Get-Content do .env, Get-ChildItem Env:,
  OPENAI_API_KEY) nos 3 scripts.
- Subcomando `diagnostico` roteado + Invoke-Diagnostico + coletores-chave
  (Win32_OperatingSystem, Get-NetTCPConnection, pyvenv.cfg, Get-ScheduledTaskInfo) +
  rodapé "NENHUM valor de .env".
- Fix Resolve-ModoInstalado: $script:ModoExplicito capturado e consultado; bug antigo
  removido; `exit 1` do default trocado por `return` (finally roda).
- INSTALL-WINDOWS.md menciona logs de execução, diagnostico, dica duplo-clique e
  segurança.

ROTEIRO DE TESTE MANUAL (registrar no SUMMARY para o piloto Windows executar):
1. `.\instalar.ps1` em PowerShell aberto manualmente → ao final imprime
   "Log desta execucao: ...\logs\instalar-<ts>.log"; o arquivo existe e contém a saída.
2. Forçar erro (ex.: renomear backend\ temporariamente) → janela some no duplo-clique,
   mas o log instalar-<ts>.log fica gravado com o erro.
3. `.\servico.ps1 status` → gera servico-status-<ts>.log.
4. `.\servico.ps1 diagnostico` → gera diagnostico-<ts>.log; ABRIR e confirmar à mão
   que NÃO há a chave da OpenAI nem linhas do .env; conferir versões/caminhos/tails.
5. `.\servico.ps1 status -Modo servico` com Tarefa instalada → confirma que respeita o
   -Modo explícito (não cai mais no 'tarefa' por engano).
6. Conferir que abrir um arquivo .env no editor e rodar diagnóstico não vaza nada.
</verification>

<success_criteria>
- Os 3 scripts gravam um log timestampado por execução em %ProgramData%\...\logs\ e
  imprimem o caminho no fim (sucesso ou erro), com fail-soft.
- `servico.ps1 diagnostico` produz um relatório único, completo e SEM segredos, e
  imprime o caminho para enviar ao suporte.
- `Resolve-ModoInstalado` respeita `-Modo` explícito.
- INSTALL-WINDOWS.md documenta logs, diagnóstico, dica de janela e segurança.
- Nenhuma alteração introduz leitura/eco do `.env` ou da chave da IA.
- Todos os `<automated>` das tasks passam.
</success_criteria>

<output>
Create `.planning/quick/260623-mod-logs-de-execucao-nos-scripts-windows-sta/260623-mod-SUMMARY.md` when done.
Inclua no SUMMARY o ROTEIRO DE TESTE MANUAL (Windows) acima — o dev não tem Windows,
então a validação final depende do piloto rodar esses passos.
</output>
