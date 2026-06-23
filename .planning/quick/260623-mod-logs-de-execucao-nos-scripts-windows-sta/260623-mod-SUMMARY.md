---
phase: quick-260623-mod
plan: 01
subsystem: instalacao-windows
tags: [powershell, logging, transcript, diagnostico, troubleshooting, seguranca]
requires: [instalar.ps1, atualizar.ps1, servico.ps1, INSTALL-WINDOWS.md]
provides:
  - "Log de execucao timestampado por execucao dos 3 scripts (%ProgramData%\\ProcessadorDocumentos\\logs\\)"
  - "servico.ps1 diagnostico — relatorio unico sem segredos para o suporte"
  - "Fix Resolve-ModoInstalado (-Modo explicito respeitado)"
  - "Troubleshooting de logs/diagnostico no guia"
affects: [INSTALL-WINDOWS.md]
tech-stack:
  added: []
  patterns: [Start-Transcript fail-soft (try/catch) + Stop-Transcript em finally, coletores isolados em try/catch]
key-files:
  created: []
  modified: [instalar.ps1, atualizar.ps1, servico.ps1, INSTALL-WINDOWS.md]
decisions:
  - "Transcript SEMPRE fail-soft: Start-Transcript em try/catch; falha vira aviso e o script segue sem log — o logging nunca quebra o script."
  - "Caminho do log impresso ANTES do Stop-Transcript (entra no proprio log) e Stop-Transcript tolerante a falha (try/catch vazio)."
  - "Logs em %ProgramData%\\ProcessadorDocumentos\\logs\\ (all-users) — derivado inline via \\$env:ProgramData em instalar/atualizar (que nao tinham \\$DataDir); reuso de \\$LogsDir em servico.ps1."
  - "default 'exit 1' trocado por \\$global:LASTEXITCODE=1; return para o finally fechar o transcript no caminho de uso invalido."
  - "Fix do bug: \\$script:ModoExplicito capturado no CORPO do script (onde \\$PSBoundParameters reflete os params reais); a funcao consulta a flag em vez de \\$PSBoundParameters.ContainsKey('Modo') (que dentro da funcao era sempre vazio)."
  - "diagnostico roteado como ramo independente de modo (sem Assert-Admin, sem Resolve-ModoInstalado) — coleta Tarefa E Servico."
  - "Diagnostico NUNCA le o conteudo do .env: reporta apenas EXISTE sim/nao; rodape confirma ausencia de segredos; coletores isolados em try/catch (uma falha vira linha, nao aborta o relatorio)."
metrics:
  duration: ~12 min
  completed: 2026-06-23
---

# Phase quick-260623-mod Plan 01: Logs de execução nos scripts Windows + diagnostico Summary

Cada execução de `instalar.ps1` / `atualizar.ps1` / `servico.ps1` passa a gravar um log de transcrição timestampado (fail-soft) em `%ProgramData%\ProcessadorDocumentos\logs\` e imprime o caminho no fim; `servico.ps1` ganha o subcomando `diagnostico` (relatório único sem segredos para o suporte) e o bug do `Resolve-ModoInstalado` (`-Modo` explícito ignorado) foi corrigido.

## What Was Built

- **Task 1 — Transcript fail-soft em `instalar.ps1` e `atualizar.ps1`** (commit `26dd2c2`):
  Bloco de log adicionado após `$ErrorActionPreference`/`param`, derivando `$LogsDir` inline via `$env:ProgramData`, timestamp `yyyyMMdd-HHmmss`, nomes `instalar-<ts>.log` / `atualizar-<ts>.log`. `Start-Transcript -Force` dentro de `try/catch` (fail-soft, flag `$transcriptOn`). Todo o corpo envolto num `try { ... } finally { ... }`; o `finally` imprime `Log desta execucao: <caminho>` (antes de parar, para entrar no próprio log) e faz `Stop-Transcript` tolerante a falha. O `Push-Location/Pop-Location` do `uvicorn` final permanece intacto dentro do novo `try`.

- **Task 2 — Transcript por subcomando + fix `Resolve-ModoInstalado` em `servico.ps1`** (commit `c51e75d`):
  `$script:ModoExplicito = $PSBoundParameters.ContainsKey('Modo')` capturado no corpo do script (logo após o `param`). Transcript por subcomando (`servico-<cmdSlug>-<ts>.log`, slug sanitizado para `[a-z]`, fallback `cmd`) com o mesmo padrão fail-soft + `try/finally` envolvendo todo o roteador. `Resolve-ModoInstalado` passa a consultar `$script:ModoExplicito` (corrige o `-Modo` explícito ser ignorado). O `exit 1` do `default` virou `$global:LASTEXITCODE = 1; return` para o `finally` fechar o transcript.

- **Task 3 — Subcomando `diagnostico` em `servico.ps1`** (commit `7008bb8`):
  `Invoke-Diagnostico` grava `diagnostico-<ts>.log` único via `Set-Content -Encoding UTF8`, com coletores isolados em `try/catch`: ambiente (`$PSVersionTable.PSVersion` + `Win32_OperatingSystem`), caminhos/existência (`Test-Path` `[OK]/[FALTA]`, incluindo `.env` **só como existe sim/não**), Python/uv (`uv --version`, `sys.executable` real do venv, linha `home` do `pyvenv.cfg`), persistência (`Get-ScheduledTask`/`Get-ScheduledTaskInfo` + `nssm status`/`sc query`), rede (`Get-NetTCPConnection -LocalPort 8000` + `/health`), tails (`Get-Content -Tail 40` de `servidor.log` / `service.{out,err}.log` / último `instalar-*.log`) e rodapé `NENHUM valor de .env / chave da IA foi incluido neste relatorio.`. Roteado por um ramo `if ($cmd -eq 'diagnostico') { Invoke-Diagnostico; return }` (independente de modo, sem admin). Ajuda e cabeçalho atualizados.

- **Task 4 — Troubleshooting no `INSTALL-WINDOWS.md`** (commit `3b15bae`):
  Subseção `### Logs de execução dos scripts e diagnóstico` (antes de "Onde ficam os dados e os logs") explicando os logs timestampados, a dica de abrir o PowerShell manualmente em vez de duplo-clique, o comando `.\servico.ps1 diagnostico` + anexo do arquivo, e o reforço de segurança (log/diagnóstico nunca expõem a chave/.env). Linha extra na seção "Onde ficam os dados e os logs" apontando a subpasta `logs\`.

## Deviations from Plan

Nenhum desvio funcional. Notas de implementação dentro do escopo previsto:

- **Ordem de commit dos Tasks 2 e 3 (mesmo arquivo):** ambos editam só `servico.ps1`. Para manter commits atômicos por task, o diff foi dividido por hunks e aplicado em duas etapas (Task 2 primeiro: transcript+fix+`return`; Task 3 depois: `Invoke-Diagnostico`+roteamento+ajuda). O estado intermediário do Task 2 foi verificado como balanceado (chaves 114/114) e auto-contido; o estado final foi confirmado idêntico (`diff`) à edição completa.
- **`exit`/`exit 0` pré-existentes em `instalar.ps1`/`atualizar.ps1` (Rule 3 — nota):** o plano só pediu trocar o `exit 1` do `default` em `servico.ps1`. Os `exit` de "feche e reabra o PowerShell" em `instalar.ps1` (winget/uv) **não** disparam o `finally`, então não imprimem a linha "Log desta execucao". Isso é **aceitável e seguro**: o `Start-Transcript` grava incrementalmente, logo o arquivo de log já está em disco mesmo nesses caminhos — só não recebe a linha-banner final. Não foram alterados para preservar o fluxo "reabrir o PowerShell".
- **Auto-elevação (`Assert-Admin` → `exit`) no modo serviço:** quando o processo não-elevado faz `exit`, seu transcript fecha sem o `finally`; o processo elevado re-lançado abre o **seu próprio** transcript (mesmo subcomando) e registra o que importa. Comportamento previsto pelo plano — não há coordenação entre processos.

## Threat Mitigations (do threat_model do plano)

- **T-quick-01 / T-quick-02 (Information Disclosure):** confirmado por grep que nenhum dos 3 scripts faz `Get-Content` do `.env`, `Get-ChildItem Env:`, nem referencia `$env:OPENAI_API_KEY` em expressão. As únicas ocorrências de `OPENAI_API_KEY` são menções textuais em comentários/avisos pré-existentes. Diagnóstico reporta `.env` só como existência; rodapé confirma ausência de segredos.
- **T-quick-03 (DoS via Start-Transcript sem permissão):** `Start-Transcript` dentro de `try/catch` nos 3 scripts → falha vira aviso e o script segue sem log.

## Static Verification (dev sem Windows)

Todos os `<automated>` das 4 tasks passaram. Checks consolidados:

| Check | Resultado |
|-------|-----------|
| `Start-Transcript` + `Stop-Transcript` (fora de comentário) + `$transcriptOn` + "Log desta execucao" nos 3 scripts | OK |
| `try`/`finally`/`catch` balanceados (servico.ps1: try 24 = catch 20 + finally 4) | OK |
| Chaves `{`/`}` balanceadas (servico.ps1 175/175; intermediário Task 2 114/114) | OK |
| `Push-Location`/`Pop-Location` balanceados (todos) | OK |
| `$script:ModoExplicito` capturado no corpo + consultado por `Resolve-ModoInstalado`; bug antigo (`ContainsKey('Modo')` com `return $Modo` dentro da função) removido | OK |
| `exit 1` do `default` em servico.ps1 substituído por `return` | OK (só sobra menção em comentário) |
| `Invoke-Diagnostico` + roteamento `eq 'diagnostico'` + `Win32_OperatingSystem` + `Get-NetTCPConnection` + `pyvenv.cfg` + `Get-ScheduledTaskInfo` + rodapé "NENHUM valor de .env" | OK |
| Nenhum `Get-Content` do `.env` / `Get-ChildItem Env:` / `$env:OPENAI_API_KEY` | OK |
| INSTALL-WINDOWS.md: "logs de execu", "diagnostico", "duplo-clique", "nunca inclu" | OK |

Sem `pwsh`/Windows no host → não houve parse real do PowerShell; verificação por análise estática (greps + balanceamento de chaves/try/finally/Push-Pop) conforme o plano.

## Roteiro de Teste Manual (Windows) — para o piloto executar

A validação final depende de rodar no Windows real (o dev não tem Windows):

1. `.\instalar.ps1` num PowerShell aberto manualmente → ao final imprime `Log desta execucao: ...\logs\instalar-<ts>.log`; o arquivo existe e contém a saída completa.
2. Forçar erro (ex.: renomear `backend\` temporariamente) e dar **duplo-clique** no script → a janela some, mas o `instalar-<ts>.log` fica gravado com o erro.
3. `.\servico.ps1 status` → gera `servico-status-<ts>.log`.
4. `.\servico.ps1 diagnostico` → gera `diagnostico-<ts>.log`; **abrir e confirmar à mão** que NÃO há a chave da OpenAI nem linhas de conteúdo do `.env`; conferir versões/caminhos/persistência/tails e o rodapé "NENHUM valor de .env...".
5. Com a Tarefa instalada, `.\servico.ps1 status -Modo servico` → confirma que respeita o `-Modo` explícito (não cai mais em 'tarefa' por engano). Reciprocamente, com o Serviço instalado, `.\servico.ps1 status -Modo tarefa`.
6. Abrir um `.env` no editor e rodar o diagnóstico → confirmar que nada do `.env` vaza no relatório.
7. `.\atualizar.ps1` (online ou `-LocalZip`) → ao final imprime `Log desta execucao: ...\logs\atualizar-<ts>.log`; arquivo gravado.

## Known Stubs

Nenhum. As mudanças são funcionais (scripts .ps1 + doc), sem placeholders ou dados mock.

## Commits

- `26dd2c2` feat(260623-mod): transcript fail-soft em instalar.ps1 e atualizar.ps1
- `c51e75d` feat(260623-mod): transcript por subcomando + fix Resolve-ModoInstalado em servico.ps1
- `7008bb8` feat(260623-mod): subcomando diagnostico em servico.ps1 (relatorio unico, sem segredos)
- `3b15bae` docs(260623-mod): troubleshooting de logs de execucao e diagnostico no INSTALL-WINDOWS.md

## Self-Check: PASSED

Todos os arquivos modificados existem (instalar.ps1, atualizar.ps1, servico.ps1, INSTALL-WINDOWS.md) e os 4 commits (26dd2c2, c51e75d, 7008bb8, 3b15bae) estao presentes no historico.
