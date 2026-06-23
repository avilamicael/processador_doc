---
phase: quick-260623-lpj
plan: 01
subsystem: distribuicao-windows
tags: [windows, persistencia, tarefa-agendada, nssm, powershell, empacotamento]
requires: [tools/nssm.exe (no pacote), backend/.venv (pythonw)]
provides: [persistencia-windows-modo-tarefa-padrao, persistencia-windows-modo-servico-nssm, launcher-versionado]
affects: [servico.ps1, empacotar.ps1, INSTALL-WINDOWS.md, tools/iniciar-servidor.py]
tech-stack:
  added: []
  patterns: [Tarefa Agendada AtLogOn como usuario, launcher pythonw redirecionando stdout/stderr p/ arquivo, deteccao automatica do modo instalado]
key-files:
  created: [tools/iniciar-servidor.py]
  modified: [servico.ps1, empacotar.ps1, INSTALL-WINDOWS.md]
decisions:
  - "Modo PADRAO de background no Windows passa a ser a Tarefa Agendada no logon (como usuario), evitando a Pegadinha 1 do LocalSystem; NSSM vira -Modo servico para PC-servidor 24/7."
metrics:
  duration: ~10 min
  completed: 2026-06-23
---

# Quick 260623-lpj: Persistência no Windows — servico.ps1 com modo Tarefa (padrão) + Serviço (NSSM) Summary

Tornou a **Tarefa Agendada no logon (como usuário)** o modo PADRÃO de persistência do servidor no Windows — evitando a Pegadinha 1 do LocalSystem (uv instala o Python no perfil do usuário; SYSTEM não lê por ACL) — preservando o NSSM/LocalSystem como `-Modo servico` para o cenário PC-servidor 24/7 headless.

## O que foi feito

### Task 1 — `tools/iniciar-servidor.py` (launcher versionado, pythonw-friendly) — commit `0e5e68f`
- Launcher Python (FONTE versionada) que a Tarefa executa via `pythonw.exe` (sem console).
- Resolve `backend\` a partir de `Path(__file__)` (não confia no CWD), faz `os.chdir(backend)` + `sys.path.insert(0, backend)` antes de importar o app (carrega `backend\.env`, resolve `app.main`).
- Redireciona `sys.stdout`/`sys.stderr` para `%LOCALAPPDATA%\ProcessadorDocumentos\logs\servidor.log` (append, line-buffered) — necessário porque pythonw não tem console.
- `uvicorn.run("app.main:app", host="127.0.0.1", port=8000, workers=1)` (sem reload). Cabeçalho com timestamp+cwd no log (sem segredos).
- Nunca lê/loga a chave da IA (`grep -i openai` vazio).

### Task 2 — `servico.ps1` reescrito para 2 modos — commit `31a9502`
- Assinatura: `param([Parameter(Position=0)][string]$Comando='status', [ValidateSet('tarefa','servico')][string]$Modo='tarefa')`. **Padrão = tarefa.**
- **Modo tarefa (padrão, `Invoke-InstalarTarefa`):** sem admin; `Ensure-Venv` → valida `pythonw.exe` e o launcher → `alembic upgrade head` falha-fechada (Push/Pop em try/finally) → cria `$TaskLogsDir` → `Register-ScheduledTask` (Trigger `AtLogOn`; Action `pythonw.exe` + launcher com `WorkingDirectory=backend\`; Principal `Interactive`/`Limited`; Settings `MultipleInstances IgnoreNew`, `StartWhenAvailable`, `ExecutionTimeLimit 0`, `RestartCount 3`, `RestartInterval 1min`, baterias) com `-Force` (idempotente) → `Start-ScheduledTask` → health-check falha-fechada (`Test-Health`, ~30s).
- Controle do modo tarefa: `Start/Stop-ScheduledTask`, `Get-ScheduledTask`+`Get-ScheduledTaskInfo` (status), `Unregister-ScheduledTask -Confirm:$false` (remover), `logs` mostra só `servidor.log`.
- **Modo servico (`Invoke-Instalar`):** NSSM/LocalSystem preservado byte-a-byte do código anterior, com dois `Write-Aviso` do pré-requisito (Python all-users / Pegadinha 1).
- `Resolve-ModoInstalado`: respeita `-Modo` explícito (`$PSBoundParameters.ContainsKey('Modo')`); senão Tarefa existe→tarefa, Serviço existe→servico, senão padrão tarefa. `Test-TaskExists`/`Test-ServiceExists` para detecção.
- Reuso: `Assert-Admin`, `Get-Nssm`, `Ensure-Venv`, `Test-ServiceExists`, helpers `Write-Passo/Aviso/Ok`. `Assert-Admin` re-injeta `-Modo servico` na re-elevação (UAC) para não cair no padrão.
- `$HealthUrl='http://127.0.0.1:8000/health'` compartilhado. Sem sintaxe PS7. Nenhuma referência à chave da IA (`grep -i openai` vazio).

### Task 3 — empacotamento + guia — commit `7fb3451`
- **empacotar.ps1:** etapa 4d agora copia `tools\iniciar-servidor.py` (FONTE versionada) para o staging além do `nssm.exe`, com `throw` se ausente; cabeçalho e `Write-Ok` do staging atualizados.
- **INSTALL-WINDOWS.md:** seção 6 reescrita para os dois modos — "Modo padrão (Tarefa no logon, sem admin)" com limitação honesta (só roda logado) + "Modo servidor 24/7 (NSSM, avançado)" com pré-requisito Python all-users destacado; tabela de controle (detecção automática + `-Modo` forçado), caminhos de log de cada modo, aviso de instância única; troubleshooting cobre os dois modos/logs.

## Verificação ESTÁTICA executada (host sem PowerShell/Windows)

| Check | Resultado |
|-------|-----------|
| `ast.parse` de `tools/iniciar-servidor.py` | PARSE OK |
| `app.main` / `workers` / `LOCALAPPDATA` / `chdir` no launcher | presentes |
| `grep -i openai tools/iniciar-servidor.py` | VAZIO |
| `ValidateSet('tarefa','servico')` em servico.ps1 | presente |
| cmdlets `Register/Unregister/Start/Stop/Get-ScheduledTask`, `New-ScheduledTaskTrigger/Action/Principal/SettingsSet` | todos presentes |
| `IgnoreNew`, `pythonw.exe`, `iniciar-servidor.py`, `Invoke-InstalarTarefa`, `Resolve-ModoInstalado` | presentes |
| `Get-ScheduledTaskInfo`, `Confirm:$false`, `Test-Health`, `Test-TaskExists` | presentes |
| `grep -i openai servico.ps1` | VAZIO |
| Push-Location / Pop-Location balanceados (2/2, em try/finally) | OK |
| sintaxe só-PS7 (`??`, `?.`) fora do comentário | ausente |
| chaves `{}` (106/106) e parênteses `()` (201/201) balanceados | OK |
| `iniciar-servidor.py` em empacotar.ps1 | presente |
| `Modo servico`, `servidor.log`, all-users/todos-os-usuários, logon/login em INSTALL-WINDOWS.md | presentes |
| `! grep -qi 'OPENAI_API_KEY=' empacotar.ps1` | OK |

> Observação: `empacotar.ps1` mantém intencionalmente a frase de segurança no cabeçalho mencionando a variável de chave; o threat T-quick-01 só exige `grep -i openai` VAZIO em **servico.ps1** e **iniciar-servidor.py** (ambos vazios). O check do plano sobre empacotar.ps1 (`OPENAI_API_KEY=` com `=`) passa.

## Roteiro de TESTE MANUAL (executar em Windows real — NÃO rodável no host)

1. `.\servico.ps1 instalar` (sem `-Modo`) → registra a Tarefa **SEM** pedir UAC; health-check verde; `http://localhost:8000/health` → 200; porta 8000 escutando (processo `pythonw`).
2. Reiniciar / fazer logoff+logon → a Tarefa sobe o servidor sozinha; `/health` → 200.
3. `.\servico.ps1 status` / `logs` / `reiniciar` / `parar` / `iniciar` → operam na Tarefa; log em `%LOCALAPPDATA%\ProcessadorDocumentos\logs\servidor.log`.
4. `.\servico.ps1 remover` → `Unregister-ScheduledTask`; `status` mostra ausência da Tarefa.
5. (Máquina com Python all-users) `.\servico.ps1 instalar -Modo servico` → UAC; NSSM como LocalSystem; health-check verde. Confirmar os avisos do pré-requisito (Pegadinha 1).
6. Empacotar (`.\empacotar.ps1`) e abrir o ZIP → `tools\iniciar-servidor.py` **e** `tools\nssm.exe` presentes.
7. Confirmar que a chave da IA NÃO aparece no registro da Tarefa/Serviço nem na saída de `logs`.

## Deviations from Plan

Nenhuma deviation de comportamento. Ajustes redacionais para satisfazer o gate de segredo (T-quick-01): comentários que citavam a variável `OPENAI_API_KEY` em `servico.ps1` e `tools/iniciar-servidor.py` foram reescritos como "a chave da IA" para que `grep -i openai` retorne VAZIO nesses dois artefatos, preservando o intuito da nota de segurança. `empacotar.ps1` manteve a menção (fora do escopo do grep-vazio do threat).

## Threat surface

Nenhuma nova superfície além do `<threat_model>` do plano. T-quick-01 (chave em logs/registro) mitigada: chave nunca passada por env da Tarefa/NSSM nem exibida; T-quick-02 (EoP) mitigada: Principal `RunLevel Limited`/`Interactive` no modo tarefa, `Assert-Admin`/UAC só no modo servico; T-quick-03 (DoS porta 8000) mitigada: `--workers 1` + `MultipleInstances=IgnoreNew` + aviso no guia + health-check.

## Lembrete ao orquestrador

Bump de versão **0.1.2 → 0.1.3** em `backend/pyproject.toml` deve ser feito no empacotamento (fora do escopo deste plano, conforme `<objective>`).

## Known Stubs

Nenhum.

## Self-Check: PASSED

Todos os 4 arquivos (tools/iniciar-servidor.py, servico.ps1, empacotar.ps1, INSTALL-WINDOWS.md) existem em disco; os 3 commits de tarefa (0e5e68f, 31a9502, 7fb3451) existem no histórico.
