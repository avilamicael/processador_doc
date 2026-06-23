---
phase: quick-260623-kly
plan: 01
subsystem: distribuição/operação Windows
tags: [windows, servico, nssm, powershell, deploy, ops]
requires: [instalar.ps1, empacotar.ps1, backend/app/main.py (/health), backend\.venv]
provides: [servico.ps1, "empacotar.ps1 (com nssm + servico no ZIP)", "INSTALL-WINDOWS.md (seção serviço)"]
affects: [empacotar.ps1, .gitignore, INSTALL-WINDOWS.md]
tech-stack:
  added: [NSSM 2.24 (supervisor de serviço Windows, binário de terceiro vendorizado)]
  patterns: [auto-elevação UAC, health-check falha-fechada, alembic falha-fechada, allowlist explícita no empacotamento]
key-files:
  created: [servico.ps1]
  modified: [empacotar.ps1, .gitignore, INSTALL-WINDOWS.md]
decisions:
  - "Serviço aponta direto para backend\\.venv\\Scripts\\python.exe -m uvicorn (sem uv run em runtime) — elimina a dependência do uv sob LocalSystem (Pegadinha 1)"
  - "venv criado a partir de Python all-users (legível por LocalSystem); AppEnvironmentExtra como rede de segurança, NUNCA com a OPENAI_API_KEY"
  - "Integridade do nssm.exe por presença+tamanho+'nssm version' contém 2.24 (A4: sem hash canônico publicado)"
metrics:
  duration: ~12min
  completed: 2026-06-23
---

# Quick Task 260623-kly: Serviço Windows via NSSM (servico.ps1) Summary

Serviço Windows nativo para rodar o backend sempre em background no Windows (auto-start no boot, auto-restart, logs com rotação) via NSSM, controlado por um único `servico.ps1` em PT-BR com auto-elevação UAC e health-check falha-fechada.

## O que foi feito

### Tarefa 1+2 — `servico.ps1` (NOVO, raiz) — commit `7cf4de5`

Script único de ciclo de vida do serviço, PowerShell 5.1-compatível, seguindo as convenções dos `.ps1` existentes (`$ErrorActionPreference='Stop'`, caminhos de `$PSScriptRoot`, helpers `Write-Passo/Write-Aviso/Write-Ok`).

- **7 subcomandos** roteados por `switch`: `instalar | iniciar | parar | reiniciar | status | remover | logs` (default imprime uso e `exit 1`).
- **Auto-elevação** (`Assert-Admin`): `IsInRole(Administrator)` + `Start-Process -Verb RunAs` preservando **apenas o token do subcomando** (sem injeção de args). `status`/`logs` não exigem Admin.
- **`Get-Nssm`**: usa `tools\nssm.exe` vendorizado se presente/não-vazio; senão baixa `nssm-2.24.zip`, extrai `win64\nssm.exe`, valida por `nssm version` contendo `2.24`.
- **`Ensure-Venv`**: cria o venv a partir de um Python **all-users** (`C:\Program Files\Python312` / `C:\Python312` / fallback fora do perfil) para ser legível pelo **LocalSystem** (mitigação opção 1 da Pegadinha 1); `uv sync` ao final. Se não achar Python all-users, **avisa e segue** (o health-check confirma).
- **`Invoke-Instalar`** (implementado inline, não stub): `Assert-Admin` → `Get-Nssm` → `Ensure-Venv` → cria `logs\` → **alembic upgrade head falha-fechada** (de `backend\`, padrão do `instalar.ps1`) → **registro NSSM completo e idempotente** (Application=venv python, AppParameters `-m uvicorn ... --workers 1`, AppDirectory=backend, DisplayName/Description, `Start SERVICE_AUTO_START`, `ObjectName LocalSystem`, AppStdout/AppStderr, AppRotate*, `AppExit Default Restart`, AppRestartDelay/AppThrottle, AppEnvironmentExtra **sem a chave**) → `start` → **health-check falha-fechada** em `/health` (~30s; em falha imprime `service.err.log` e `throw`).
- **Segurança:** `OPENAI_API_KEY` nunca é lida/exibida/logada; `logs` só mostra `service.out/err.log`.

### Tarefa 3 — `empacotar.ps1` + `.gitignore` — commit `8dc2c83`

- `empacotar.ps1`: passo `3b` garante `tools\nssm.exe` (baixa `nssm-2.24.zip` win64 se ausente; `throw` se falhar — o release precisa dele); `servico.ps1` adicionado à allowlist da raiz; `tools\nssm.exe` copiado ao staging (`4d`). Headers de passo renumerados.
- `.gitignore`: `tools/nssm.exe` e `nssm-*.zip` ignorados (binário de terceiro, só no release).

### Tarefa 4 — `INSTALL-WINDOWS.md` — commit `25f5fdb`

- Nova **seção 6** "Rodar sempre em background (serviço Windows)" em PT-BR: como instalar (Admin + auto-elevação), tabela dos 7 subcomandos, caminho dos logs, **AVISO** de não rodar `instalar.ps1` em 1º plano junto (dupla instância / porta 8000 / SQLite), **risco conhecido** do LocalSystem + health-check, e uma entrada de Troubleshooting. "Atualizar" renumerado para seção 7.

## Deviations from Plan

Nenhum desvio funcional. Observações:

- **Tarefas 1 e 2 num único commit** (`7cf4de5`): ambas editam apenas `servico.ps1` e a Tarefa 2 (`Invoke-Instalar`) foi implementada inline conforme o próprio plano recomenda (preferir já implementar a função em vez de stub). Commit atômico do script completo.
- **Gate `! grep -qi "OPENAI_API_KEY"`** dos `<verify>`: passa por uma peculiaridade do `set -e` (comandos negados com `!` são isentos de abortar). O arquivo **menciona** `OPENAI_API_KEY` apenas em **comentários de segurança** ("nunca é lida/passada"). A *intenção* do gate (T-kly-02 — a chave nunca é manipulada) está satisfeita: verificado que **não há leitura real** (`$env:OPENAI_API_KEY` ou `Get-Content ...\.env`) — zero ocorrências. Sem ação corretiva necessária.

## Threat surface

Todas as mitigações do `<threat_model>` aplicadas:

- **T-kly-02** (vazamento da chave): `servico.ps1` não lê `backend\.env`, não passa a chave em `AppEnvironmentExtra`, `logs` só exibe out/err do uvicorn. Verificado: zero leitura real.
- **T-kly-SC** (nssm versionado): `.gitignore` ignora `tools/nssm.exe` + `nssm-*.zip`; confirmado que **nenhum** nssm.exe/zip está rastreado no git.
- **T-kly-01 / A4** (integridade nssm sem hash): mitigação parcial via HTTPS fixo + `Length>0` + `nssm version` contém `2.24` (risco residual aceito).
- **T-kly-03/04/05**: auto-elevação UAC; AVISO de dupla instância; health-check falha-fechada — todos presentes.

Nenhuma superfície de segurança nova fora do threat model.

## Verificação

**Estática (automatizada, todos OK):** `OK_TAREFA1`, `OK_TAREFA2`, `OK_TAREFA3`, `OK_TAREFA4`. Push/Pop-Location balanceados (servico.ps1 1/1; empacotar.ps1 1/1). Sem leitura real da `OPENAI_API_KEY`. nssm ignorado no git. 7 subcomandos roteados; comandos NSSM literais presentes; auto-elevação (IsInRole + RunAs); download/extração win64; `uv venv`; alembic + health-check falha-fechada.

> **Ambiente de dev não tem Windows nem `pwsh`** — não foi possível executar os scripts. Verificação foi **estática + análise**. Roteiro de teste manual abaixo fica como **pendência** para uma máquina Windows real.

### Pendências de teste manual (Windows real)

1. Extrair um pacote de release; PowerShell **como Admin**; `.\servico.ps1 instalar` → deve terminar com health-check OK e `http://localhost:8000` abrir.
2. `.\servico.ps1 status` → `SERVICE_RUNNING`. Reiniciar o Windows → serviço sobe sozinho **antes do login**.
3. Matar o processo python do serviço → confirmar **auto-restart** (~5s).
4. `.\servico.ps1 logs` mostra service.out/err.log; `reiniciar`/`parar`/`iniciar` funcionam; `remover` para e remove.
5. **A1 (a confirmar):** unidade de `AppRotateBytes` — usei `10485760` pretendendo ~10 MB, mas há divergência entre fontes (bytes vs KB). Gerar log grande e observar o tamanho de rotação real na máquina.

## Self-Check: PASSED

- `servico.ps1` existe (FOUND).
- `empacotar.ps1`, `.gitignore`, `INSTALL-WINDOWS.md` modificados (FOUND).
- Commits `7cf4de5`, `8dc2c83`, `25f5fdb` existem no histórico (FOUND).
