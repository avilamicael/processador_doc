# Phase 9: Automação — destino configurável e transformação de valores - Research

**Researched:** 2026-06-24
**Domain:** Resolução de caminho cross-platform (Windows alvo / WSL dev) + parser de filtros inline de tokens, sobre o código existente de automação
**Confidence:** HIGH (verificado contra o código e com `ntpath`/`unicodedata` rodados localmente)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Destino **absoluto por automação**: mover/copiar aceita caminho ABSOLUTO completo com tokens (`C:\...\{fornecedor}`). Não confinar sob `data_dir\organizados`, não sanitizar drive/separadores do absoluto.
- **D-02:** Caminho com drive (`C:\…`) ou UNC (`\\…`) = absoluto, usado como está. Sem drive/UNC = relativo → juntado à base padrão (`AUTOMATION_DEST_ROOT` se setada, senão `data_dir\organizados`).
- **D-03:** Remover o confinamento V4 (`is_relative_to`) para destinos absolutos. Implicação de segurança ACEITA (single-tenant). Sanitização de chars proibidos do Windows continua **por SEGMENTO de nome** (não no drive/`\`).
- **D-04:** Validar, não mutilar. Caminho inválido → avisar no dry-run. Dry-run mostra o caminho final REAL (origem→destino absoluto resolvido).
- **D-05:** Criar subpastas automaticamente (mkdir recursivo) ao aplicar, exigindo que a RAIZ/drive exista (`C:\`). Raiz inexistente → erro no dry-run/apply.
- **D-06:** Filtros inline no token, encadeáveis: `{campo:filtro=arg:filtro}`.
- **D-07:** Conjunto v1 = `palavras=N`, `letras=N`/`truncar=N`, `maiusc`/`minusc`, `sem_acento`, `padrao=…`, `substituir=de>para`, e expor `_fmt_date` como `formato=`.
- **D-08:** Sanitização de chars inválidos do Windows continua automática, aplicada **DEPOIS** das transformações, por segmento (mantém `sanitize_component`).
- **D-09:** Preview no construtor de automações: resultado final (nome + caminho absoluto) com dados de exemplo (reaproveita `resolve_pattern`/caminho do dry-run).

### Claude's Discretion
- Nomes exatos dos filtros e gramática do parser (inline, cobrindo v1 D-07).
- Detecção "absoluto" (drive letter / UNC / leading slash) e normalização.
- Texto das mensagens de aviso/erro do dry-run.
- Base padrão editável na UI agora ou via env (preferência: manter via env).

### Deferred Ideas (OUT OF SCOPE)
- Substituição por regex e mapa de valores ("IGUACU DIST..." → "IGUACU") — v2.
- Base de saída editável na UI.
- Confinamento opt-in / allowlist de raízes permitidas (reintroduzir V4 opcional).
</user_constraints>

## Summary

A fase é 100% **lógica de caminho e de string** — sem novas dependências, sem mudança de schema, sem novo modelo ORM. Tudo vive em `naming.py` (resolução) + um ajuste em `executor._apply_actions`/`stage._base_root` (base relativa) + propagação do erro de "raiz inexistente" para o dry-run. O `fileops`/`undo`/`audit` **já operam sobre caminhos absolutos arbitrários** (`Path`, `os.replace`, `dst.parent.mkdir(parents=True)`) — não quebram com destino fora de `data_dir`. O risco real está em **dois pitfalls**: (1) detectar caminho absoluto do Windows **rodando em Linux/WSL** (o `os.path.isabs`/`Path` nativo retorna `False` para `C:\...` no Linux — bug silencioso no dev/CI), e (2) **não chamar `.resolve()`** no caminho do usuário (canoniza contra o CWD do backend e gera lixo — exatamente a lição já aprendida em `watched_folders._normalize_path`).

**Primary recommendation:** Em `resolve_dest_folder`, ramificar com `ntpath`/`PureWindowsPath` (não `os.path`): se o padrão resolvido tem drive ou é UNC → trata como **absoluto literal** (sem `base_root`, sem `is_relative_to`, sanitizando só os SEGMENTOS após o anchor); senão junta a `base_root`. Os filtros inline são um parser de pipeline simples dentro de `_substitute` (split por `:`, dispatch explícito por nome — nunca `eval`), aplicados ANTES de `sanitize_component`. A criação de pasta entra no `apply_stage`/`fileops` checando que o **anchor existe** antes do `mkdir(parents=True)`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Detectar absoluto vs relativo + montar destino | `naming.resolve_dest_folder` (pure) | `executor._apply_actions` | É onde tokens viram caminho hoje; pura/testável sem disco |
| Aplicar filtros inline aos valores | `naming._substitute` (pure) | `resolve_pattern` / `resolve_dest_folder` | Afeta nome E segmentos de pasta — ponto único |
| Sanitização final por segmento | `naming.sanitize_component` (inalterado) | — | Já existe; só muda a ORDEM (pós-transformação) |
| Criar subpastas / checar raiz existe | `fileops` + `stage.apply_stage` | — | Único tier com efeito de filesystem; preserva atomicidade |
| Mostrar caminho real + avisos | `stage.dry_run` → `DryRunRow` → frontend | `AutomationsPage` preview | Dry-run já carrega origem→destino; estender o sinal |

## Standard Stack

**Nenhuma dependência nova.** Tudo com a stdlib já em uso:

| Módulo stdlib | Uso nesta fase | Por quê |
|---------------|----------------|---------|
| `ntpath` / `pathlib.PureWindowsPath` | Detectar `C:\`/UNC de forma OS-independente | `os.path.isabs` é OS-dependente → falha em WSL/Linux (VERIFICADO abaixo) |
| `unicodedata` | filtro `sem_acento` (NFKD + drop combining) | Padrão Python; já usado implicitamente; sem dep externa |
| `re` | parser de filtros + tokens (já importado em `naming.py`) | — |
| `pathlib.Path` | montar/criar destino absoluto | Já em uso em todo `fileops`/`stage`/`undo` |

## Package Legitimacy Audit

Não se aplica — **zero pacotes externos instalados** nesta fase. Toda a implementação usa stdlib (`ntpath`, `pathlib`, `unicodedata`, `re`) já disponível.

## Runtime State Inventory

Fase de **lógica de caminho/nome**, não rename/refactor de identificadores. Mesmo assim, mudança de POLÍTICA de destino tem implicações de estado:

| Categoria | Achado | Ação |
|-----------|--------|------|
| Stored data | `AuditLog.source_path`/`dest_path` guardam caminhos como **string absoluta** (já hoje — ver `stage.py` `str(source)`/`str(dest)`). Nenhum schema muda. | Nenhuma migração. Caminhos antigos (sob `organizados`) continuam válidos para undo. |
| Live service config | `AUTOMATION_DEST_ROOT` (env) passa a importar **só para destino relativo** (D-02). Continua lida em `config.py`/`stage._base_root`. | Documentar no INSTALL/notes que absoluto ignora a base. |
| OS-registered state | Nenhum. | None — verificado (nenhuma tarefa agendada lê dest_root). |
| Secrets/env vars | `AUTOMATION_DEST_ROOT`, `AUTOMATION_MAX_COMPONENT_LEN` — nomes inalterados. | None. |
| Build artifacts | Nenhum. | None. |

**Mudança de postura de segurança (D-03):** documentar que automações agora escrevem em qualquer caminho com permissão do processo. Já está aceito no CONTEXT; basta refletir nos docstrings de `resolve_dest_folder`/`naming.py` (que hoje afirmam "confina V4").

## Architecture Patterns

### Fluxo (inalterado em forma, alterado em política)
```
fields {campo:val}  ──┐
dest_folder pattern ──┤→ resolve_dest_folder ──→ Path destino (ABS ou base+rel)
name_pattern        ──┘     │                         │
                            ├─ _substitute (tokens + FILTROS inline, D-06/07)
                            ├─ por segmento: sanitize_component (D-08, pós-filtro)
                            └─ ABS? não confina | REL? junta base_root, sem is_relative_to no abs
                                      │
dry_run ──→ DryRunRow.dest_path = caminho REAL (D-04/D-09)
apply ──→ fileops: checa anchor existe (D-05) → mkdir(parents) → materialize → os.replace
```

### Pattern 1: Detecção absoluto vs relativo cross-platform (D-02) — CRÍTICO
Use **`ntpath`** ou `PureWindowsPath`, NUNCA `os.path.isabs`/`Path(...).is_absolute()` (que dependem do OS de execução). VERIFICADO localmente em WSL/Linux:

```python
# Source: stdlib ntpath / pathlib — verificado neste host (Linux/WSL)
import os, ntpath
from pathlib import PureWindowsPath, PurePosixPath

p = r"C:\Users\x\NF"
os.path.isabs(p)        # False  (no Linux!) ← bug silencioso
ntpath.isabs(p)         # True   ← correto independente do OS
PureWindowsPath(p).drive   # 'C:'
PureWindowsPath(r"\\srv\share\NF").drive   # '\\srv\share' (UNC)
PureWindowsPath("NotasFiscais/x").drive    # ''  → relativo
PureWindowsPath("/posix/abs").drive        # ''  → trata como rel no contexto Windows
```

**Regra concreta para `resolve_dest_folder`:** após `strip_quotes`, decidir absoluto com `bool(PureWindowsPath(pattern).drive)` OU `ntpath.isabs(pattern)` (cobre `C:\`, UNC, e leading `\`). Adicionalmente aceitar POSIX absoluto (`/...`) via `PurePosixPath(pattern).is_absolute()` se quiser suportar dev Linux — discrição (D-02 cita Windows como alvo).

### Pattern 2: Resolver destino sem `.resolve()` (lição de `watched_folders`)
`watched_folders._normalize_path` (linhas 44-92) já documenta a armadilha: **`.resolve()` canoniza contra o CWD do backend** e, para um caminho não-reconhecido-como-absoluto-naquele-OS, gera `D:\...\backend\C:\...`. O caso real do teste (`C:\ProgramData\...\organizados\C_\Users\...`) é exatamente isso somado ao `sanitize_component` que transformou `C:` → `C_`.

**Concretamente:**
- Ramo ABSOLUTO: montar `PureWindowsPath(anchor) / segmento1_sanitizado / ...` e devolver como `Path(str(...))`. **NÃO** chamar `.resolve()`. **NÃO** sanitizar o anchor (drive/UNC). Sanitizar SÓ os segmentos após o anchor.
- Ramo RELATIVO: comportamento atual (`base_root / segmentos`), mas **remover** a checagem `is_relative_to` para o ramo absoluto (manter ou não no relativo é discrição — segmentos relativos já são neutralizados por `sanitize_component`, então traversal não escapa de qualquer forma).

### Pattern 3: Filtros inline — parser de pipeline (D-06/D-07)
Estender o `_TOKEN_RE` para capturar a cadeia de filtros e fazer split por `:`. Hoje:
```python
_TOKEN_RE = re.compile(r"\{([^{}:]+)(?::([^{}]+))?\}")  # group(2) = "spec" único
```
O group(2) atual já captura tudo após o primeiro `:` (ex.: `aaaa-mm`). Reusar: dividir `spec` por `:` em uma lista de filtros e aplicar em pipeline. Dispatch EXPLÍCITO (espelha `rules._OPERATORS`/V5 — nunca `eval`):

```python
# pseudo — dentro de repl(), depois de obter `value` cru
for f in spec.split(":"):
    f = f.strip()
    if f.startswith("palavras="):   value = " ".join(value.split()[:int(arg)])
    elif f.startswith(("letras=", "truncar=")):  value = value[:int(arg)]
    elif f == "maiusc":             value = value.upper()
    elif f == "minusc":             value = value.lower()
    elif f == "sem_acento":         value = _strip_accents(value)
    elif f.startswith("padrao="):   value = value or arg   # (mas vazio já bloqueia antes — ver nota)
    elif f.startswith("substituir="): de, _, para = arg.partition(">"); value = value.replace(de, para)
    elif f.startswith("formato="):  value = _fmt_date(value, arg) or RAISE _MissingField
    # nome de filtro desconhecido → ignora (inerte) OU _MissingField — discrição; prefira ignorar p/ não quebrar token simples
```
`_strip_accents` (VERIFICADO local): `"".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))` → `"IGUAÇU AÇÃO" → "IGUACU ACAO"`.

**Ordem (D-08):** filtros → resultado → `sanitize_component`. Para pasta, o `_substitute` roda com `sanitize=False` e o `sanitize_component` por segmento vem depois em `resolve_dest_folder` (já é assim hoje). Os filtros entram DENTRO de `repl`, antes do `return`.

**Compatibilidade com `{campo}` simples (CRÍTICO):** token sem `:` → `spec is None` → nenhum filtro aplicado (caminho atual intacto). `{data:aaaa-mm-dd}` legado: hoje cai em `_fmt_date`. Para não quebrar, mapear o spec sem `=` que case ano/mês/dia como `formato=` implícito, OU exigir `formato=aaaa-mm-dd` daqui pra frente e manter o atalho legado. **Recomendação:** se o primeiro filtro contém `aaaa`/`mm`/`dd` e não tem `=`, tratar como `_fmt_date` (retrocompat); senão pipeline de filtros.

### Pattern 4: `padrao=` (valor-default se vazio) — interage com D-07 (bloqueio)
Hoje, campo ausente/vazio levanta `_MissingField` ANTES de chegar ao spec → o `padrao=` nunca rodaria. Para `padrao=` funcionar, o caminho de "campo vazio" precisa, **quando o token tem filtro `padrao=`**, NÃO bloquear e usar o default. Concretamente: detectar `padrao=` no spec; se presente e o campo está ausente/vazio, usar o arg em vez de levantar `_MissingField`. Cobrir com teste explícito (campo ausente + `padrao=X` → "X", não bloqueio).

### Anti-Patterns to Avoid
- **`os.path.isabs` / `Path.is_absolute()` para detectar caminho Windows** → falha em WSL/Linux (dev/CI). Use `ntpath`/`PureWindowsPath`.
- **`.resolve()` no caminho do usuário** → canoniza contra CWD, gera `backend\C:\...`. Lição já registrada em `watched_folders`.
- **Sanitizar o drive/anchor** (`C:` → `C_`) → causa raiz do bug do teste. Sanitizar SÓ segmentos.
- **`eval`/`format()` dinâmico no parser de filtros** → V5; dispatch explícito por nome.
- **mkdir que cria a unidade** → checar anchor existe antes (D-05); raiz inexistente = erro, não criação.

## Don't Hand-Roll

| Problema | Não construir | Usar | Por quê |
|----------|---------------|------|---------|
| Escrita atômica do destino | novo writer | `fileops._verified_write`/`materialize_to_dest` (já fazem `mkdir(parents=True)` + fsync + `os.replace` + verify) | Já é seguro cross-device, com verificação de hash |
| Anti-colisão / idempotência | nada | `resolve_collision` + AuditLog write-ahead existentes | Inalterados — destino absoluto não muda a semântica |
| Remoção de acento | tabela própria | `unicodedata.normalize("NFKD")` | Padrão, cobre todo Latin-1/Unicode |
| Detecção de caminho Windows | regex de drive própria frágil | `ntpath.isabs` / `PureWindowsPath().drive` | Cobre `C:\`, UNC, edge cases testados na stdlib |

## Common Pitfalls

### Pitfall 1: Detecção de absoluto no OS errado
**O que dá errado:** dev/CI roda em WSL/Linux; `os.path.isabs("C:\\...")` retorna `False` → o caminho do cliente Windows vira "relativo" e é jogado sob `base_root`. Testes passam no Windows e falham (ou vice-versa) no Linux.
**Como evitar:** `ntpath`/`PureWindowsPath` (OS-independente). Testar AMBOS os formatos (`C:\`, UNC, relativo) sem depender do OS do runner.
**Sinal precoce:** teste de "destino absoluto" só passa quando rodado no Windows.

### Pitfall 2: `.resolve()` reintroduzido por hábito
**O que dá errado:** alguém adiciona `.resolve()` "para normalizar" → reaparece `backend\C:\...`.
**Como evitar:** comentar explicitamente (como `watched_folders` faz) e testar que o destino absoluto sai LITERAL (sem CWD prefixado).

### Pitfall 3: `is_relative_to` esquecido no ramo absoluto bloqueia tudo
**O que dá errado:** manter o `is_relative_to(base_resolved)` no ramo absoluto → todo destino fora de `organizados` vira `None` → `blocked` → tudo cai em revisão (regressão oposta).
**Como evitar:** o ramo absoluto **não** chama `is_relative_to`. Cobrir com teste: destino `C:\fora\da\base` resolve para si mesmo, não `None`.

### Pitfall 4: Filtro quebra token simples / `{data:fmt}` legado
**O que dá errado:** o split por `:` muda a semântica de tokens existentes (`{data:aaaa-mm}` deixa de formatar).
**Como evitar:** retrocompat — spec sem `=` contendo `aaaa/mm/dd` → `_fmt_date`; token sem `:` → sem filtro. Manter os testes atuais de `test_naming.py` verdes (são a fonte de verdade RED→GREEN).

### Pitfall 5: Raiz inexistente cria a unidade ou estoura no apply
**O que dá errado:** `mkdir(parents=True)` num drive inexistente (`Z:\`) lança no meio do apply, após write-ahead.
**Como evitar:** checar `Path(anchor).exists()` (drive/share) ANTES de `mkdir`, no dry-run E no apply; raiz ausente → bloqueio/erro reportado no `DryRunRow` (D-04/D-05), não exceção crua. Anchor via `PureWindowsPath(dest).anchor` (VERIFICADO: `C:\a\b` → `'C:\\'`; UNC → `'\\srv\share\\'`).

## Code Examples

### Detecção + montagem de destino absoluto (esboço para `resolve_dest_folder`)
```python
# Source: stdlib (ntpath/pathlib) — verificado neste host
import ntpath
from pathlib import Path, PureWindowsPath

def _is_abs_windows(p: str) -> bool:
    return bool(PureWindowsPath(p).drive) or ntpath.isabs(p)

# após strip_quotes(pattern) e resolução de tokens+filtros por segmento:
if _is_abs_windows(pattern):
    win = PureWindowsPath(pattern)
    anchor = win.anchor                      # 'C:\\' ou '\\srv\share\\' — NÃO sanitizar
    safe_parts = [sanitize_component(seg) for seg in win.parts[1:]]  # parts[0] == anchor
    dest = PureWindowsPath(anchor, *safe_parts)
    return Path(str(dest))                   # SEM .resolve()
# ramo relativo: base_root / segmentos (comportamento atual, sem is_relative_to no abs)
```

### Checagem de raiz existente (D-05) — no dry-run e no apply
```python
from pathlib import PureWindowsPath, Path
anchor = PureWindowsPath(str(dest)).anchor or Path(str(dest)).anchor
if anchor and not Path(anchor).exists():
    # → marcar blocked/erro no DryRunRow com mensagem "unidade/raiz {anchor} não existe"
    ...
```

### Remoção de acento (filtro `sem_acento`)
```python
# Source: stdlib unicodedata — verificado: "IGUAÇU AÇÃO" → "IGUACU ACAO"
import unicodedata
def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))
```

## Compatibilidade undo/audit (confirmação)

- `undo.undo_operation` opera sobre `Path(audit.source_path)`/`Path(audit.dest_path)` — strings absolutas arbitrárias. `_verified_write`/`_atomic_write_bytes` fazem `source.parent.mkdir(parents=True, exist_ok=True)`. **Não quebra** com destino fora de `organizados`. CONFIRMADO (undo.py 106-148).
- `reconcile_orphans` (stage.py 779-820) usa `Path(audit.dest_path).exists()` + `hash_file` — agnóstico ao local. **Não quebra.**
- `materialize_to_dest`/`_verified_write` já fazem `dst.parent.mkdir(parents=True, exist_ok=True)` (fileops 136) → **D-05 já está parcialmente coberto** para subpastas; falta só a **checagem de anchor existente** (não deixar `mkdir` tentar criar a unidade). CONFIRMADO.

## Migração?

**Não há mudança de schema.** `AuditLog.dest_path`/`source_path` já são strings; automação `move`/`copy` guarda `dest_folder` como string em `params_json`. `name_pattern`/`dest_folder` com filtros inline são apenas strings mais ricas — nenhum modelo novo, nenhum Alembic. CONFIRMADO contra `stage.py` (str(dest)) e `executor.ActionSpec.params`.

## Validation Architecture

`nyquist_validation` não está desabilitado → seção incluída.

**Sem 09-VALIDATION.md separado (opção leve, consistente com o projeto):** esta seção absorve a "Validation Architecture" da fase. A validação Nyquist está coberta por: (a) os blocos `<verify><automated>` de CADA task/feature nos planos 09-01, 09-02 e 09-03 (comandos `uv run pytest`/`npm run build` executáveis); e (b) o caso de API novo de dry-run com destino absoluto em `tests/test_api_automations.py` (cobre D-04 — ver Phase Requirements → Test Map). Não há artefato `09-VALIDATION.md` por design; este registro explícito satisfaz a Dimension 8e.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (já em uso) |
| Config | `backend/` (pyproject/pytest); testes em `backend/tests/automation/` |
| Quick run | `cd backend && uv run pytest tests/automation/test_naming.py -x` |
| Full suite | `cd backend && uv run pytest tests/automation -q` |

Padrão observado (`test_naming.py`): funções puras testadas direto, `tmp_path` para destino, `importorskip` no topo (RED→GREEN), docstrings amarrando ao requisito/decisão. Manter.

### Phase Requirements → Test Map
| Comportamento | Test Type | Comando | Existe? |
|---------------|-----------|---------|---------|
| `C:\...\{x}` resolve absoluto literal (sem CWD, sem `C_`) | unit | `pytest tests/automation/test_naming.py::test_dest_absolute_kept_literal -x` | ❌ Wave 0 |
| UNC `\\srv\share\{x}` resolve absoluto | unit | idem `::test_dest_unc_absolute` | ❌ Wave 0 |
| caminho relativo ainda junta `base_root` | unit | `::test_dest_relative_uses_base` | ❌ Wave 0 (adaptar dos existentes) |
| detecção independe do OS do runner | unit | `::test_abs_detection_cross_os` | ❌ Wave 0 |
| anchor não sanitizado; segmentos sim | unit | `::test_segments_sanitized_anchor_kept` | ❌ Wave 0 |
| raiz inexistente → bloqueio no dry-run | unit | `tests/automation/test_stage.py::test_missing_root_blocks_dry_run` | ❌ Wave 0 |
| filtro `palavras=1` → "IGUACU" | unit | `::test_filter_palavras` | ❌ Wave 0 |
| `letras=N`/`truncar`/`maiusc`/`minusc`/`sem_acento`/`substituir`/`padrao` | unit | `::test_filter_<cada>` | ❌ Wave 0 |
| filtros encadeados `{x:maiusc:palavras=2}` | unit | `::test_filter_chain` | ❌ Wave 0 |
| `{campo}` simples e `{data:aaaa-mm}` legado intactos | unit | testes EXISTENTES de `test_naming.py` (não regredir) | ✅ |
| sanitize roda DEPOIS do filtro (D-08) | unit | `::test_sanitize_after_filter` | ❌ Wave 0 |
| dry-run/DryRunRow mostra caminho absoluto real (D-04) | integration | `tests/test_api_automations.py::test_dry_run_absolute_dest_shows_real_path` (NOVO — blocker #3) | ✅ arquivo / ❌ caso |
| undo de destino absoluto devolve à origem | integration | `tests/automation/test_undo.py` (estender) | ✅ arquivo / ❌ caso |

### Sampling Rate
- Per task commit: `uv run pytest tests/automation/test_naming.py -x`
- Per wave merge: `uv run pytest tests/automation -q`
- Phase gate: suíte `tests/automation` + `tests/test_api_automations.py` verdes.

### Wave 0 Gaps
- [ ] Casos novos em `test_naming.py` (absoluto/UNC/relativo/anchor/cada filtro/cadeia/`padrao`/ordem sanitize).
- [ ] Caso "raiz inexistente bloqueia" em `test_stage.py`.
- [ ] Caso de dry-run mostrando caminho absoluto em `test_api_automations.py` (D-04 — blocker #3 resolvido no plano 09-01 Task 4).
- [ ] Caso de undo com destino absoluto em `test_undo.py`.
- (Sem novo framework/fixture — infra existente cobre.)

## Security Domain

`security_enforcement` (absent = enabled).

### ASVS aplicável
| Categoria | Aplica | Controle |
|-----------|--------|----------|
| V5 Input Validation | sim | `sanitize_component` por segmento (mantido, D-08); parser de filtros com **dispatch explícito, nunca `eval`** (espelha `rules.py` V5) |
| V4 Access Control | **mudança consciente** | D-03: confinamento V4 REMOVIDO para absoluto (aceito, single-tenant). Mitigação residual: sanitização por segmento + raiz deve existir |
| V6 Cryptography | não | — |

### Threats / mitigação
| Padrão | STRIDE | Mitigação |
|--------|--------|-----------|
| Path traversal via valor de campo (`../`) | Tampering | `sanitize_component` neutraliza `/`,`\`,`..` em CADA segmento (anchor não vem de campo) |
| Caminho absoluto arbitrário escrevendo fora da base | Elevation | ACEITO por D-03 (single-tenant). Risco residual documentado; allowlist é deferred |
| Injeção no parser de filtros | Tampering | Dispatch por nome literal, sem `eval`/`format` dinâmico; filtro desconhecido = inerte |
| Vazamento de valor de campo em log | Info Disclosure | Manter "NÃO loga valores" — não logar padrão resolvido nem caminho com dados sensíveis (V7/V9, já é regra) |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Manter atalho de retrocompat `{data:aaaa-mm}` (spec com `aaaa/mm/dd` sem `=` → `_fmt_date`) é aceitável vs. exigir `formato=` | Pattern 3/4 | Baixo — se o planner preferir `formato=` puro, ajustar testes legados; é discrição D-07 |
| A2 | Suportar também POSIX absoluto (`/...`) como absoluto é opcional (alvo é Windows) | Pattern 1 | Baixo — só afeta dev Linux; D-02 cita Windows |
| A3 | `padrao=` deve suprimir o bloqueio D-07 quando o campo está vazio (senão o filtro é inútil) | Pattern 4 | Médio — se não, `padrao=` não funciona; confirmar intenção com o planner |

**Tudo o mais foi verificado** (ntpath/unicodedata rodados localmente; código lido diretamente).

## Open Questions (RESOLVED)

1. **`{data:aaaa-mm}` legado vs `formato=` (A1) — RESOLVED:** **manter o atalho** `{data:aaaa-mm}` (spec sem `=` contendo `aaaa/mm/dd` → `_fmt_date`); retrocompat garantida para automações já configuradas. `formato=` é a forma canônica nova e coexiste com o atalho. Refletido nos testes `test_legacy_date_shortcut_still_works` + `test_filter_formato_explicit` (plano 09-02).
2. **`padrao=` e bloqueio (A3) — RESOLVED:** `padrao=` **deve ser detectado ANTES de levantar `_MissingField`** — quando o campo está ausente/vazio e a cadeia contém `padrao=X`, usar `X` como valor em vez de bloquear (suprime o rebaixamento para revisão de D-07). Sem isso o filtro seria inútil. Refletido no teste `test_filter_padrao_default_when_missing` (plano 09-02) e na implementação do Pattern 4.
3. **Suporte a POSIX absoluto `/...` (A2) — RESOLVED:** **opcional / discrição do dev.** O alvo é Windows (D-02); aceitar `/...` como absoluto via `PurePosixPath(p).is_absolute()` é permitido para conveniência do dev Linux, mas não é exigido. A escolha feita na Task 2 do plano 09-01 deve estar alinhada com os testes da Task 1 (mesmo formato de anchor inexistente usado no RED).

## Sources

### Primary (HIGH)
- Código do projeto lido diretamente: `naming.py`, `executor.py`, `stage.py`, `fileops.py`, `undo.py`, `rules.py`, `config.py`, `api/automations.py`, `api/watched_folders.py`, `tests/automation/test_naming.py`.
- stdlib `ntpath`/`pathlib`/`unicodedata` — **executados neste host (Linux/WSL)** confirmando `os.path.isabs` vs `ntpath.isabs`, `PureWindowsPath().drive/.anchor`, e NFKD accent strip.

## Metadata
**Confidence breakdown:**
- Detecção de caminho / política de destino: HIGH (verificado no host + lição já documentada em `watched_folders`).
- Parser de filtros: HIGH na mecânica (stdlib) / MEDIUM nas escolhas de gramática (discrição D-06/D-07 — ver Assumptions).
- Compatibilidade undo/audit/sem-migração: HIGH (lido no código).

**Research date:** 2026-06-24
**Valid until:** estável (sem libs externas) — revalidar só se a stack de automação mudar.
