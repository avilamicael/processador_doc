---
phase: quick-260623-no9
plan: 01
subsystem: windows-persistencia
tags: [windows, powershell, startup, vbs, launcher, persistencia]
requires: [tools/iniciar-servidor.py, servico.ps1, empacotar.ps1]
provides: [modo-startup-padrao, guarda-instancia-unica]
affects: [INSTALL-WINDOWS.md, servico.ps1, tools/iniciar-servidor.py]
tech-stack:
  added: []
  patterns: [.vbs na pasta Inicializar do Windows (wscript, sem console), guarda de instancia unica por socket TCP]
key-files:
  created: []
  modified:
    - tools/iniciar-servidor.py
    - servico.ps1
    - INSTALL-WINDOWS.md
decisions:
  - "Modo startup (.vbs na pasta Inicializar) vira o PADRAO do servico.ps1 — roda no logon, INVISIVEL, sem admin, sem a API de Tarefas Agendadas (que era fragil: exigia sessao interativa)."
  - "Launcher ganha guarda de instancia unica (socket TCP 127.0.0.1:8000): se ja ha servidor, loga e sai com codigo 0 — nunca sobe um 2o uvicorn."
  - "tarefa e servico permanecem selecionaveis via -Modo; tarefa deixa de ser o padrao. NSSM intacto."
metrics:
  duration: ~12 min
  completed: 2026-06-23
---

# Phase quick-260623-no9 Plan 01: servico.ps1 modo startup (pasta Inicializar) padrao Summary

Modo **startup** (escreve um `ProcessadorDocumentos.vbs` na pasta Inicializar do Windows que sobe o servidor com `pythonw.exe` + `tools\iniciar-servidor.py`, completamente invisivel) passou a ser o **PADRAO** do `servico.ps1`; o launcher ganhou guarda de instancia unica na porta 8000; `tarefa` e `servico` (NSSM) seguem selecionaveis via `-Modo` mas deixaram de ser o padrao.

## O que foi feito

### Task 1 — Guarda de instancia unica no launcher (`db1ea06`)
- `import socket` no topo de `tools/iniciar-servidor.py`.
- Funcao `_porta_em_uso(host, porta) -> bool`: tenta `socket.create_connection((host, porta), timeout=0.5)`; True se conecta (servidor ja de pe), False em `OSError` (recusada/timeout).
- Checagem **antes** de `uvicorn.run`, **depois** de abrir o log: se a 8000 ja esta escutando, loga `ja ha um servidor escutando em 127.0.0.1:8000 — saindo` (timestamp ISO, mesmo formato do cabecalho), `flush`+`close` do log e `sys.exit(0)` (codigo 0 — comportamento esperado, nao erro). Caso contrario, segue o fluxo normal (sobe o uvicorn).
- CWD/sys.path/log inalterados; a chave da IA continua nunca lida/logada.

### Task 2 — Modo startup como novo padrao no `servico.ps1` (`17f5255`)
- **Param**: `[ValidateSet('startup','tarefa','servico')]$Modo = 'startup'`.
- **Constantes**: `$StartupDir = %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`; `$VbsFile = $StartupDir\ProcessadorDocumentos.vbs`. Reusa `$VenvPythonw`, `$Launcher`, `$BackendDir`, `$TaskLogsDir`/`$TaskLog` (mesmo `servidor.log` do modo tarefa).
- **`Test-StartupExists`**: `$true` se `Test-Path $VbsFile`.
- **`Resolve-ModoInstalado`**: prioridade `$script:ModoExplicito` -> startup (.vbs) -> tarefa -> servico; padrao **startup** quando nada instalado (mantido o fix `$script:ModoExplicito`, sem `$PSBoundParameters` dentro de funcao).
- **`Get-ServidorPid`** (helper): PID da 8000 via `Get-NetTCPConnection ... OwningProcess`; fallback `Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'"` filtrando `CommandLine -like '*iniciar-servidor.py*'`. Robusto a ausencia (`$null`).
- **`Invoke-InstalarStartup`** (sem admin): `Ensure-Venv` -> valida `pythonw.exe`/launcher -> **alembic falha-fechada** de dentro de `backend\` -> cria `$TaskLogsDir` e `$StartupDir` -> escreve o `.vbs` (3 linhas, caminhos de `$PSScriptRoot`, `Set-Content -Encoding ASCII`, sem BOM) -> inicia agora via `Start-Process wscript.exe "<vbs>"` -> **health-check falha-fechada** (`Test-Health`, ~30s) com tail do log e `throw` em falha -> mensagem final deixando claro que nao abre janela, sobe a cada logon, acesse `http://localhost:8000`.
- **Subcomandos** `Invoke-{Iniciar,Parar,Reiniciar,Status,Remover,Logs}Startup`: iniciar/reiniciar via `wscript`; parar via `Get-ServidorPid` + `Stop-Process -Force`; status mostra `.vbs` + porta 8000 (`Get-NetTCPConnection`) + `/health`; remover para e apaga o `.vbs`; logs faz tail do `servidor.log` (nunca expoe a chave).
- **Roteador**: `instalar` roteia `startup -> Invoke-InstalarStartup`, `tarefa -> Invoke-InstalarTarefa`, `servico -> Invoke-Instalar`; switch de controle ganha ramo `startup` (servico/tarefa intactos).
- **Diagnostico**: secao Persistencia inclui estado do `.vbs` + PID na 8000; `$VbsFile` adicionado a "Caminhos e existencia". Nunca inclui a chave.
- **Cabecalho + ajuda**: reescritos para 3 modos (startup padrao/invisivel/sem admin; tarefa opcional/auto-restart/exige sessao interativa; servico avancado 24/7) + AVISO de nao combinar modos.

### Task 3 — Guia (`INSTALL-WINDOWS.md`) + empacotamento (`8221d72`)
- Secao 6 reescrita: **3 modos** com startup como **PADRAO** (`.\servico.ps1 instalar` sem `-Modo`, invisivel/sem janela/sem admin, logs em `%LOCALAPPDATA%\...\servidor.log`, limitacao honesta de rodar so logado); tarefa como opcional (auto-restart, exige PowerShell aberto manualmente — duplo-clique nao registra); NSSM como 24/7 avancado (admin + Python all-users).
- Tabela de controle e nota de troubleshooting "O servidor nao inicia em background" atualizadas para os 3 modos (startup/tarefa compartilham `servidor.log`; dica de checar o `.vbs` na pasta Inicializar). AVISO de nao combinar modos atualizado.
- **`empacotar.ps1` NAO precisou de alteracao**: ja inclui `servico.ps1`, `INSTALL-WINDOWS.md` e `tools\iniciar-servidor.py` (verificado nas linhas de staging 145/162). O `.vbs` e gerado no cliente pelo `servico.ps1` — nao vai no pacote (confirmado: nenhuma referencia a escrever/copiar `.vbs` no empacotar).

## Deviations from Plan

None - plano executado exatamente como escrito.

Observacao de execucao (nao-deviation): durante a Task 1 o `python3 -m py_compile` gerou `tools/__pycache__/` (artefato transitorio). Removido antes de finalizar; arvore de trabalho limpa. `tools/` nao e pacote Python rastreado no repo (o `__pycache__/` de codigo fica em `backend/`, ja ignorado por `backend/.gitignore`).

## Seguranca (chave da IA)

- O launcher continua **nunca** lendo/imprimindo/logando a chave — so escreve no log o cabecalho e (novo) a linha de "ja ha servidor escutando".
- O `.vbs` so contem **caminhos resolvidos** (`$BackendDir`, `$VenvPythonw`, `$Launcher`) — **nunca** a chave. A chave segue lida pelo app de `backend\.env` via CWD (`sh.CurrentDirectory = backend\`).
- `grep` por `openai|api.key|chave` em `servico.ps1` retorna apenas comentarios de seguranca (nenhuma leitura/uso da chave).
- Diagnostico e logs continuam sem segredos.

## Verificacao estatica (host SEM Windows/pwsh)

Toda verificacao foi **estatica** (host nao tem pwsh). Checks executados e aprovados:

| Check | Resultado |
|-------|-----------|
| `python3 -m py_compile tools/iniciar-servidor.py` | OK |
| AST: `_porta_em_uso` definida E aparece ANTES de `uvicorn.run` E `create_connection` E `import socket` E `sys.exit(0)` | OK |
| `servico.ps1` comeca com BOM UTF-8 `efbbbf` (3 primeiros bytes) | **OK (efbbbf confirmado)** |
| `ValidateSet('startup','tarefa','servico')` e `$Modo = 'startup'` (default) | OK |
| Funcoes `Invoke-InstalarStartup`, `Invoke-IniciarStartup`, `Invoke-PararStartup`, `Invoke-ReiniciarStartup`, `Invoke-StatusStartup`, `Invoke-RemoverStartup`, `Invoke-LogsStartup`, `Test-StartupExists` presentes | OK |
| Caminho `Start Menu\Programs\Startup`, nome `ProcessadorDocumentos.vbs`, `wscript`, `Get-NetTCPConnection`, `Stop-Process` presentes | OK |
| Linha `sh.Run` gerada (simulada): `sh.Run """<pythonw>"" ""<launcher>""", 0, False` (VBScript valido, aspas duplicadas) | OK |
| Balanco de `{}` (235/235) e `()` (435/435) | OK |
| Nenhuma leitura/uso da chave da IA em `servico.ps1` (so comentarios de seguranca) | OK |
| `INSTALL-WINDOWS.md` cita Inicializar/startup/invisivel e mantem NSSM/24/7 | OK |
| `empacotar.ps1` ainda inclui `iniciar-servidor.py` e `servico.ps1` | OK |

## Roteiro de teste manual (maquina piloto Windows, via WSL/PowerShell)

Rodar numa **sessao PowerShell aberta manualmente** na pasta do programa (onde esta `servico.ps1`):

1. **Instalar (padrao startup):**
   ```powershell
   .\servico.ps1 instalar
   ```
   Esperado: **nenhuma janela/terminal nova** abre; ao final `/health` responde 200; o arquivo
   `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ProcessadorDocumentos.vbs` existe.
   Abrir `http://localhost:8000` no navegador deve carregar a UI.

2. **Persistencia no logon:** fazer **logoff e logon** (ou reiniciar a maquina e logar). Esperado:
   o servidor sobe **sozinho e invisivel** (sem janela). `http://localhost:8000` volta a responder
   sem rodar nada manualmente.

3. **Status:**
   ```powershell
   .\servico.ps1 status
   ```
   Esperado: mostra `.vbs` presente, porta 8000 em LISTEN (com OwningProcess) e `/health` 200.

4. **Parar:**
   ```powershell
   .\servico.ps1 parar
   ```
   Esperado: encerra o `pythonw` que serve a 8000; depois `.\servico.ps1 status` mostra a porta 8000
   sem ninguem escutando e `/health` sem resposta.

5. **Guarda de instancia unica:** com o servidor JA de pe (rode `.\servico.ps1 iniciar` se necessario),
   disparar o launcher de novo manualmente:
   ```powershell
   & "<repo>\backend\.venv\Scripts\pythonw.exe" "<repo>\tools\iniciar-servidor.py"
   ```
   Esperado: **NAO** sobe um 2o servidor; o `servidor.log` em
   `%LOCALAPPDATA%\ProcessadorDocumentos\logs\servidor.log` ganha a linha
   `ja ha um servidor escutando em 127.0.0.1:8000 — saindo` e o processo sai com codigo 0.

6. **Remover:**
   ```powershell
   .\servico.ps1 remover
   ```
   Esperado: apaga o `.vbs` da pasta Inicializar e encerra o `pythonw` da 8000. Confirmar que o `.vbs`
   nao existe mais e que a 8000 nao responde.

7. **Seguranca:** abrir o `ProcessadorDocumentos.vbs` num editor e rodar
   ```powershell
   .\servico.ps1 diagnostico
   ```
   Esperado: a chave da OpenAI **NAO** aparece no `.vbs` (so caminhos) **nem** no relatorio de
   diagnostico (que confirma "NENHUM valor de .env / chave da IA foi incluido").

(Opcional) Validar o parse no PowerShell 5.1 do piloto — o BOM UTF-8 e necessario:
```powershell
powershell -ExecutionPolicy Bypass -Command "$null = [scriptblock]::Create((Get-Content -Raw .\servico.ps1)); 'parse OK'"
```

## Commits

| Task | Commit | Mensagem |
|------|--------|----------|
| 1 | `db1ea06` | feat(260623-no9): guarda de instancia unica no launcher (porta 8000) |
| 2 | `17f5255` | feat(260623-no9): modo startup (.vbs Inicializar) como novo padrao no servico.ps1 |
| 3 | `8221d72` | docs(260623-no9): guia descreve startup (invisivel, sem admin) como padrao |

## Self-Check: PASSED
</content>
</invoke>
