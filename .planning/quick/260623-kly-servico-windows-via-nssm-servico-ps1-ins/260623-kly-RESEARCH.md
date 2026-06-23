# Quick Task: Serviço Windows via NSSM (servico.ps1) — Research

**Researched:** 2026-06-23
**Domain:** Windows service management (NSSM) + uv/uvicorn toolchain sob conta de serviço
**Confidence:** HIGH (comandos NSSM e estrutura do zip verificados em nssm.cc); MEDIUM nas recomendações de toolchain sob SYSTEM (raciocínio + comportamento documentado do uv)

## Summary

Objetivo: rodar `uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1` (hoje iniciado via `uv run` de dentro de `backend/`) como **serviço Windows permanente** — auto-start no boot (antes do login), auto-restart, logs em arquivo com rotação, scripts de controle. NSSM é o supervisor de processo padrão para isso (envolve o uvicorn num serviço Win32 nativo, reinicia se cair).

**Recomendação primária:** instalar o serviço apontando o `Application` para o **`python.exe` do venv do projeto** (`backend\.venv\Scripts\python.exe`), com `AppParameters = -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1` e `AppDirectory = <repo>\backend`. Isso elimina a dependência do `uv` em runtime (a pegadinha SYSTEM/PATH) — o serviço chama o interpretador diretamente. O `uv` continua sendo usado só na **instalação** (`uv sync` + resolver o sys.executable). Manter `AppEnvironmentExtra` com as variáveis de perfil como **rede de segurança** (porque o Python base do venv é gerenciado pelo uv e mora no perfil do usuário — ver Pegadinha 1).

## User Constraints

Nenhum CONTEXT.md (quick-task). Constraints herdadas do CLAUDE.md / código:
- **`--workers 1` obrigatório** — lifespan sobe watcher+worker como `asyncio.Task` 1x/processo; SQLite single-writer. O serviço **não pode coexistir** com o `instalar.ps1` rodando o servidor em primeiro plano (duas instâncias = contenção de escrita + watcher duplicado).
- **AppDirectory deve ser `backend\`** — o app lê `backend\.env` relativo ao CWD; `alembic` procura `alembic.ini` no CWD. Mesmo motivo do `Push-Location $BackendDir` no `instalar.ps1`.
- `DATA_DIR` default = `%ProgramData%\ProcessadorDocumentos` (gravável por SYSTEM e por admin — OK para serviço).
- Segredo `OPENAI_API_KEY` nunca logado/exibido pelos scripts.

## Standard Stack

| Componente | Versão | Origem | Confiança |
|------------|--------|--------|-----------|
| NSSM | **2.24** (release estável, 2014-08-31) | `https://nssm.cc/release/nssm-2.24.zip` [CITED: nssm.cc/download] | HIGH |
| (alt) NSSM pre-release | 2.24-101-g897c7ad (2017-04-26) | nssm.cc — corrige Win10 Creators Update | MEDIUM |

**Obter o nssm.exe (estratégia vendor):** baixar `nssm-2.24.zip`, extrair, e o binário 64-bit está em **`nssm-2.24\win64\nssm.exe`** (32-bit em `win32\`) [VERIFIED: web search confirmando estrutura; CITED: nssm.cc/download "32-bit and 64-bit binaries are included"]. Copiar para `tools\nssm.exe` no repo se ausente, OU bundlar no pacote de release (alinha com o fluxo `empacotar.ps1` já existente). Em Windows 64-bit moderno, usar `win64`.

**Checagem de integridade:** nssm.cc não publica hash oficial estável de forma machine-friendly. Mínimo viável: após extrair, verificar `Test-Path tools\nssm.exe` + `(Get-Item).Length > 0` + rodar `tools\nssm.exe version` e confirmar saída contém "2.24". (Opcional/robusto: pinar um SHA-256 conhecido do zip no script e validar com `Get-FileHash`.) [ASSUMED] — não há hash canônico publicado pela nssm.cc para automatizar.

## Comandos NSSM exatos (verificados)

> Fonte: [CITED: nssm.cc/usage] e [CITED: nssm.cc/commands]. Sintaxe `nssm set <servicename> <Param> <valor>`.

**Instalação + configuração** (rodar elevado):
```
nssm install  <NOME> <Application_abs> <args...>           # ou install só o nome e setar Application depois
nssm set <NOME> Application      <repo>\backend\.venv\Scripts\python.exe
nssm set <NOME> AppParameters    -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
nssm set <NOME> AppDirectory     <repo>\backend
nssm set <NOME> DisplayName      "Processador de Documentos"
nssm set <NOME> Description       "Backend FastAPI do Processador de Documentos"
nssm set <NOME> Start            SERVICE_AUTO_START          # auto-start no boot (antes do login)
```

**Logs em arquivo + rotação:**
```
nssm set <NOME> AppStdout      C:\ProgramData\ProcessadorDocumentos\logs\service-out.log
nssm set <NOME> AppStderr      C:\ProgramData\ProcessadorDocumentos\logs\service-err.log
nssm set <NOME> AppRotateFiles 1
nssm set <NOME> AppRotateOnline 1                            # rotaciona enquanto o serviço roda
nssm set <NOME> AppRotateBytes 10485760                      # rotaciona ao atingir ~10 MB (valor em bytes)
```
> NOTA de verificação: a doc da nssm cita `AppRotateBytes` como tamanho de rotação. Há divergência em fontes terceiras sobre se a unidade é bytes ou KB — **o planner deve confirmar empíricamente** (setar um valor pequeno, gerar log, observar) ou consultar `nssm.cc/usage` na máquina. [CITED: nssm.cc/usage diz "<kilobytes>" no resumo extraído] → tratar como **possível KB**; logar a decisão. (A pasta `logs\` precisa existir antes — criar no script.)

**Auto-restart (resiliência):**
```
nssm set <NOME> AppExit Default Restart      # ação padrão ao processo sair = reiniciar
nssm set <NOME> AppRestartDelay 5000         # espera 5s antes de reiniciar (ms)
nssm set <NOME> AppThrottle     10000        # se cair < 10s após subir, considera "crash rápido" e aumenta o intervalo (anti-flapping) (ms)
```

**Conta do serviço (boot antes do login):**
- Default do NSSM = **LocalSystem** (roda no boot, sem login). É o caminho mais simples e atende "antes do login". Para travar conta explicitamente: `nssm set <NOME> ObjectName LocalSystem`. [CITED: nssm.cc/usage]
- ObjectName também aceita `.\Usuario senha` para rodar como conta de usuário (evita a Pegadinha 1, mas exige guardar senha) — **não recomendado** aqui; preferir SYSTEM + AppEnvironmentExtra.

**Controle / status:**
```
nssm start   <NOME>
nssm stop    <NOME>
nssm restart <NOME>
nssm status  <NOME>        # ex.: SERVICE_RUNNING / SERVICE_STOPPED
nssm remove  <NOME> confirm   # 'confirm' evita o prompt interativo (essencial em script)
```
Status nativo do Windows (sem depender do nssm): `sc query <NOME>` (lê `STATE : 4 RUNNING`). Útil para o `servico.ps1 status`. [CITED: nssm.cc/commands]

## Pegadinha 1 (PRINCIPAL) — uv per-user vs serviço SYSTEM

**O problema:** `uv.exe` mora em `%USERPROFILE%\.local\bin` e os Pythons gerenciados pelo uv ficam em `%LOCALAPPDATA%\uv\python\...`. Quando o serviço roda como **LocalSystem**, `%USERPROFILE%`/`%APPDATA%`/`%LOCALAPPDATA%` apontam para o perfil do *SYSTEM* (`C:\Windows\System32\config\systemprofile`), **não** para o do usuário instalador. Logo `uv run` sob o serviço (a) pode não achar o `uv.exe` no PATH e (b) o Python gerenciado some.

**Recomendação (mais confiável): apontar o serviço direto para o python do venv, NÃO para `uv run`.**
- `Application = <repo>\backend\.venv\Scripts\python.exe`
- `AppParameters = -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1`
- Vantagem: zero dependência do `uv` em runtime; o serviço chama o interpretador real diretamente.

**Sub-pegadinha do venv do uv (por que ainda precisa de rede de segurança):** o venv do projeto é criado **com um Python base gerenciado pelo uv**. O `pyvenv.cfg` do venv grava `home = ` apontando para a instalação do uv (no perfil do usuário, em `%LOCALAPPDATA%\uv\...` ou no symlink em `~\.local\bin`). O `python.exe` dentro do `.venv\Scripts` é apenas um *launcher/cópia fina* que delega ao Python base via `home`. Se esse caminho base estiver sob o perfil do usuário, **SYSTEM precisa de permissão de leitura/execução nele** [VERIFIED: comportamento do `pyvenv.cfg home` confirmado no issue astral-sh/uv#16411 e docs venv]. Em geral `%LOCALAPPDATA%\uv` do usuário **não** é legível pelo SYSTEM por ACL → o serviço falharia ao iniciar.

**Mitigações (o planner escolhe, em ordem de robustez):**

1. **Mais robusto — Python base do sistema, não per-user.** Criar o venv a partir de um Python instalado *para todos os usuários* (ex.: o Python 3.12 via winget que o `instalar.ps1` já instala, em `C:\Program Files\...` ou `C:\Python312`), acessível ao SYSTEM. Comando: `uv venv --python <python_do_sistema> .venv` (uv usa esse base; `home` aponta para local legível por SYSTEM). Assim `python.exe` do venv roda sob SYSTEM sem depender do perfil do usuário. **Recomendado.**

2. **Rede de segurança via AppEnvironmentExtra.** Se o venv depender de um Python gerenciado pelo uv no perfil do usuário, injetar no serviço as variáveis do usuário instalador (resolvidas no install, **valores absolutos**):
```
nssm set <NOME> AppEnvironmentExtra ^
  USERPROFILE=C:\Users\<user> ^
  LOCALAPPDATA=C:\Users\<user>\AppData\Local ^
  APPDATA=C:\Users\<user>\AppData\Roaming ^
  PATH=C:\Users\<user>\.local\bin;<demais>
```
   Mesmo assim, **as ACLs precisam permitir SYSTEM** ler `%LOCALAPPDATA%\uv`. Variável certa + ACL errada = ainda falha. Por isso a opção 1 é preferível.

3. **Última opção — rodar o serviço como o usuário** (`ObjectName .\user senha`). Resolve PATH/perfil naturalmente, mas exige armazenar senha e o serviço só sobe se a conta existir/estiver válida. Evitar.

**Descobrir o python real no install (sempre fazer):** rodar, de dentro de `backend\`, o resolvedor canônico e gravar o caminho absoluto:
```powershell
$py = & uv run python -c "import sys; print(sys.executable)"
```
Usar `$py` como `Application`. Isso captura exatamente o `python.exe` que o `uv run` usaria, sem chumbar `.venv\Scripts\python.exe` (que pode variar). [ASSUMED — padrão idiomático; `sys.executable` retorna o interpretador efetivo].

**Verificação obrigatória no install:** após `nssm install`/`start`, fazer `nssm status` + um `Invoke-WebRequest http://127.0.0.1:8000/` (ou endpoint de health) com timeout, e **falhar-fechado** se não responder em ~30s — porque a falha SYSTEM/ACL só aparece em runtime, não no install.

## Pegadinha 2 — Elevação (Administrador)

`nssm install/set/start/remove` exigem privilégio de administrador. Padrão idiomático PowerShell:

```powershell
$elevado = ([Security.Principal.WindowsPrincipal] `
  [Security.Principal.WindowsIdentity]::GetCurrent()
  ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $elevado) {
  Start-Process -FilePath 'powershell.exe' -Verb RunAs `
    -ArgumentList @('-ExecutionPolicy','Bypass','-File', $PSCommandPath) + $args
  exit
}
```
[ASSUMED — padrão consagrado de self-elevation; `-Verb RunAs` dispara o UAC.] Cuidado: ao re-lançar elevado, o **CWD muda** — sempre derivar caminhos de `$PSScriptRoot`/`$PSCommandPath`, nunca do diretório atual (o `instalar.ps1` já faz isso).

## Don't Hand-Roll

| Problema | Não construa | Use | Por quê |
|----------|--------------|-----|---------|
| Supervisão/restart de processo | Loop PowerShell que re-spawna uvicorn | NSSM `AppExit Restart`+`AppThrottle` | NSSM é serviço Win32 nativo: sobe no boot, restart com backoff, integra ao Service Control Manager |
| Rotação de log | Cortar/renomear `.log` manualmente | NSSM `AppRotate*` | Rotação online sem derrubar o processo |
| Início no boot antes do login | Tarefa agendada "At logon" | Serviço `SERVICE_AUTO_START` | Serviço roda sem ninguém logado; "At logon" não |

## Common Pitfalls

1. **Duas instâncias do servidor.** O serviço NSSM + alguém rodando `instalar.ps1` (que termina subindo `uvicorn` em primeiro plano) = duas instâncias na porta 8000 → a segunda falha no bind e o SQLite vê 2 writers/2 watchers. **Ação:** separar "instalar/atualizar" de "rodar". Idealmente o `instalar.ps1` deixa de subir o servidor quando o serviço está instalado (ou o serviço é o único caminho de execução em produção). O planner deve decidir o ponto de corte.
2. **Porta ocupada no restart.** uvicorn pode demorar a liberar a 8000; `AppRestartDelay 5000` dá folga.
3. **`backend\.env` ausente.** Serviço sobe mas o app não acha config → criar `.env` no install (já feito pelo `instalar.ps1`) **antes** de instalar o serviço; `AppDirectory=backend\` garante leitura.
4. **`DATA_DIR` sob SYSTEM.** `%ProgramData%\ProcessadorDocumentos` é gravável por SYSTEM → OK. (Se algum dia o serviço rodar como usuário comum, revalidar permissão de escrita.)
5. **`nssm remove` interativo.** Sempre `nssm remove <NOME> confirm` em script (sem `confirm` abre prompt e trava automação).
6. **Migração Alembic.** O serviço só roda `uvicorn`; `alembic upgrade head` deve continuar no install/update (de `backend\`), **antes** de subir o serviço — senão rotas dão 500 (bug já visto, ver STATE.md 2026-06-22).

## Runtime State Inventory (refactor/instalação)

| Categoria | Achado | Ação |
|-----------|--------|------|
| Stored data | `%ProgramData%\ProcessadorDocumentos\app.db` (SQLite WAL) — inalterado pelo serviço | Nenhuma migração de dados; só garantir gravável por SYSTEM (já é) |
| Live service config | **NOVO**: serviço Windows `<NOME>` registrado no SCM (não vive no git) | `servico.ps1` instala/atualiza/remove idempotente |
| OS-registered state | Serviço com `Start=AUTO`, conta `LocalSystem`, `Application`/`AppDirectory`/`AppEnvironmentExtra` setados no registro de serviço do NSSM | re-aplicar via `nssm set` no update (idempotente) |
| Secrets/env vars | `OPENAI_API_KEY` em `backend\.env` (não no serviço) — serviço lê via CWD | Nenhuma; nunca passar a chave por `AppEnvironmentExtra` (apareceria no registro) |
| Build artifacts | `backend\.venv` criado pelo uv; `frontend\dist` servido pelo FastAPI | `python.exe` do venv = `Application`; reinstalar venv invalida o caminho → re-setar `Application` no update |

## Environment Availability

| Dependência | Necessária por | Verificação | Fallback |
|-------------|----------------|-------------|----------|
| NSSM (`nssm.exe`) | Registrar o serviço | vendor em `tools\` ou baixar `nssm-2.24.zip` | baixar no install se ausente |
| Privilégio Admin | install/set/start/remove | self-elevation `-Verb RunAs` | abortar com mensagem se UAC negado |
| Python base legível por SYSTEM | venv rodar sob LocalSystem | preferir Python all-users (winget) como base do venv | AppEnvironmentExtra + ACL (Pegadinha 1) |
| `uv.exe` | só install (`uv sync`, resolver sys.executable) | já garantido pelo `instalar.ps1` | — |

## Assumptions Log

| # | Claim | Risco se errado |
|---|-------|-----------------|
| A1 | `AppRotateBytes` em bytes (usei 10485760 = 10MB) vs KB | Rotação em tamanho errado (10MB vs 10GB) — confirmar na máquina; baixo impacto |
| A2 | venv do uv com Python base no perfil do usuário não é legível por SYSTEM por ACL default | Se for legível, opção 2 (AppEnvironmentExtra) já bastaria; baixo risco — opção 1 é segura de qualquer forma |
| A3 | `uv venv --python <python_sistema>` faz `pyvenv.cfg home` apontar para local legível por SYSTEM | Se não, cai na opção 2/3; verificação em runtime (health-check) pega a falha |
| A4 | Sem hash oficial publicado por nssm.cc para automatizar integridade | Integridade fraca; mitigar com `nssm version` + (opcional) SHA-256 pinado pelo dev |

## Open Questions

1. **Quem sobe o servidor em produção?** Definir se `instalar.ps1` para de subir uvicorn em 1º plano quando o serviço existe (recomendado), evitando dupla instância. — *Decisão do planner.*
2. **Nome do serviço:** sugerir `ProcessadorDocumentos` (interno) + DisplayName "Processador de Documentos". Confirmar unicidade (`sc query ProcessadorDocumentos`).
3. **AppRotateBytes unidade:** confirmar bytes vs KB empíricamente (A1).

## Sources

### Primary (HIGH)
- nssm.cc/usage — comandos `set` (Application, AppDirectory, AppParameters, AppStdout/Err, AppRotate*, Start, AppExit, AppThrottle, AppRestartDelay, AppEnvironmentExtra, ObjectName)
- nssm.cc/commands — start/stop/restart/status/remove/rotate
- nssm.cc/download — release 2.24, URL `https://nssm.cc/release/nssm-2.24.zip`, win32/win64 no zip

### Secondary (MEDIUM)
- web search — estrutura `nssm-2.24\win64\nssm.exe`; gist magnetikonline NSSM cheatsheet
- github.com/astral-sh/uv#16411 — `pyvenv.cfg home` aponta para instalação uv-managed (raiz da Pegadinha 1)
- docs.astral.sh/uv/concepts/python-versions — Pythons gerenciados pelo uv

## Metadata
- NSSM stack: HIGH (docs oficiais)
- Toolchain SYSTEM/uv: MEDIUM (raciocínio + comportamento documentado; exige verificação runtime no install)
- **Valid until:** ~2026-12 (NSSM estável desde 2014; uv evolui rápido — revalidar `uv venv` se o uv mudar layout de Python gerenciado)
