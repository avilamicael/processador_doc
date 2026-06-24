# Phase 9: Automação — destino configurável e transformação de valores - Context

**Gathered:** 2026-06-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Tornar o renomear/mover **utilizável de verdade**, em duas frentes (backlog itens 10–11):
1. **Destino de arquivo** que o usuário escolhe (hoje confinado sob `data_dir\organizados` e caminho absoluto é mutilado: `C:`→`C_`).
2. **Transformação dos valores extraídos** no nome/pasta (hoje só `{campo}` cru + sanitize).

Fora de escopo (outras fases): qualquer mudança em classificação/ingestão, undo na UI (Phase 11), preview de sinais de template (Phase 10). Aqui o foco é a **ação de automação** (renomear/mover/copiar) e como ela monta destino + nome.
</domain>

<decisions>
## Implementation Decisions

### Política de destino (Item 10)
- **D-01:** Destino **absoluto por automação**. A ação mover/copiar aceita um caminho **ABSOLUTO completo, com tokens**, ex.: `C:\Users\Usuario\Downloads\NOTAS_FISCAIS\{fornecedor}`. Não confinar mais sob `data_dir\organizados`, não sanitizar drive/separadores do caminho absoluto.
- **D-02:** **Absoluto vs relativo:** caminho com drive (`C:\…`) ou UNC (`\\…`) = absoluto, usado como está. Caminho **sem** drive/UNC = relativo → juntado à **base padrão** (a atual `AUTOMATION_DEST_ROOT` se setada, senão `data_dir\organizados`), mantida como fallback. (Detecção Windows/POSIX = discrição do dev.)
- **D-03:** **Remover o confinamento V4** (`is_relative_to`) para destinos absolutos. **Implicação de segurança ACEITA e documentada:** single-tenant, na máquina do cliente — a automação pode escrever onde o processo tiver permissão. Mudança consciente de postura (era confinamento V4). A **sanitização de chars proibidos do Windows continua por SEGMENTO de nome** (não no drive/`\` do caminho).
- **D-04:** **Validar, não mutilar.** Caminho inválido → **avisar no dry-run** (nunca aceitar silenciosamente e mutilar como hoje). O **dry-run mostra o caminho final REAL** (origem→destino absoluto resolvido).

### Pasta de destino ausente (Item 10)
- **D-05:** **Criar as subpastas automaticamente** (mkdir recursivo) ao aplicar, **exigindo que a RAIZ/drive exista** (ex.: `C:\` existe). Raiz/drive inexistente → erro no dry-run/apply (não cria unidade). Comum em "mover para `{fornecedor}\{data}`".

### Transformação de valores (Item 11)
- **D-06:** **Filtros inline no token**, encadeáveis: `{campo:filtro=arg:filtro}`. Ex.: `{fornecedor:maiusc:palavras=2}`, `{data:formato=aaaa-mm-dd}`. (Nomes/gramática exatos = discrição do dev, mantendo a sintaxe inline.)
- **D-07:** **Conjunto v1 = essencial + substituir:** primeiras N palavras (`palavras=N`); truncar N chars (`letras=N`/`truncar=N`); caixa (`maiusc`/`minusc`); remover acentos (`sem_acento`); valor-padrão se vazio (`padrao=…`); substituição de texto **literal simples** (`substituir=de>para`). Expor a formatação de data já existente (`_fmt_date`) como filtro (`formato=`).
- **D-08:** A **sanitização de chars inválidos do Windows continua automática**, aplicada **DEPOIS** das transformações, por segmento de nome (mantém `sanitize_component`). Usuário não lida com isso; o resultado aparece no preview.
- **D-09:** **Preview no construtor de automações:** mostrar o resultado final (nome + caminho absoluto) das transformações com dados de exemplo (reaproveita `resolve_pattern`/caminho do dry-run). Liga com o preview do Item 5 (Phase 10).

### Claude's Discretion
- Nomes exatos dos filtros e a gramática do parser (desde que inline e cobrindo o conjunto v1 D-07).
- Detecção "absoluto" (drive letter / UNC / leading slash) e normalização.
- Texto das mensagens de aviso/erro do dry-run.
- Se a base padrão vira editável na UI agora ou continua via env (preferência: continuar via env; destino é absoluto por automação — ver Deferred).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Origem dos requisitos
- `.planning/notes/2026-06-24-melhorias-teste-usuario-final.md` §Item 10 e §Item 11 — sintomas reais do teste, diagnóstico e melhorias propostas.

### Código a alterar (automação)
- `backend/app/automation/naming.py` — `sanitize_component`, `strip_quotes`, `_substitute`, `_fmt_date`, `resolve_pattern`, `resolve_dest_folder` (é AQUI que destino e nome são montados; a política de destino D-01..D-04 e os filtros D-06..D-08 vivem aqui).
- `backend/app/automation/stage.py` §251-260 — `_dest_root`/base padrão (`automation_dest_root` ou `data_dir/organizados`).
- `backend/app/automation/fileops.py` — escrita verificada + `os.replace` atômico (criação de pasta D-05 entra perto daqui).
- `backend/app/config.py` §186-193 — `automation_dest_root` (base fallback).
- `backend/app/api/automations.py` — dry-run/apply; `DryRunRow` expõe origem→destino (estender p/ caminho absoluto final, D-04).
- `frontend/src/pages/DryRunPage.tsx` e `frontend/src/pages/AutomationsPage.tsx` — preview/construtor (D-09).
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `naming._substitute` / `resolve_pattern` / `_fmt_date` — base do mecanismo de tokens; estender com os filtros inline (D-06/D-07).
- `naming.sanitize_component` — manter como passo final por segmento (D-08).
- `naming.resolve_dest_folder` — **reescrever a política** (hoje confina + sanitiza absoluto; passar a aceitar absoluto, D-01..D-04).
- `fileops` (apply atômico + verificação por hash + undo/audit) — manter compatível; mkdir recursivo do destino (D-05).
- `DryRunRow` (automations.py) já carrega origem→destino — estender para mostrar o caminho absoluto final resolvido.

### Established Patterns
- Tokens `{campo}` no `name_pattern` (rename) e `dest_folder` (move/copy).
- **Dry-run antes de aplicar** (AUT-03) — invariante a preservar; agora deve refletir destino absoluto + transformações.
- **Audit write-ahead + undo** (AUT-04/05) — a mudança de destino não pode quebrar o undo (que devolve do destino→origem ou restaura do CAS).

### Integration Points
- Política de destino → `resolve_dest_folder` + o cálculo do `DryRunRow` + apply (`fileops`).
- Transformações → `_substitute`/`resolve_pattern` (afeta tanto `name_pattern` quanto segmentos de `dest_folder`).
</code_context>

<specifics>
## Specific Ideas

- Caso real do teste: destino saiu como `C:\ProgramData\…\organizados\C_\Users\Usuario\Downloads\NOTAS_FISCAIS\IGUACU DIST. DE PROD. OTICOS LTDA - F6\…` — o esperado era `C:\Users\Usuario\Downloads\NOTAS_FISCAIS\{fornecedor}\…`.
- Caso real de transformação: encurtar "IGUACU DIST. DE PROD. OTICOS LTDA" → algo curto (ex.: `palavras=1` → "IGUACU"). (Mapa de valores explícito ficou para v2 — ver Deferred.)
</specifics>

<deferred>
## Deferred Ideas

- **Substituição por regex** e **mapa de valores** (ex.: "IGUACU DIST. DE PROD. OTICOS LTDA" → "IGUACU") — adiados do v1 (D-07 = essencial + substituir simples). Backlog Item 11, fase futura.
- **Base de saída editável na UI** — por ora a base padrão fica via env (`AUTOMATION_DEST_ROOT`); como o destino passou a ser absoluto por automação (D-01), a base só importa para caminho relativo. Reavaliar se houver demanda.
- **Confinamento opt-in / allowlist de raízes permitidas** — se algum cliente quiser travar onde a automação pode escrever (reintroduzir um V4 opcional). Não no v1.

</deferred>

---

*Phase: 9-automacao-destino-de-arquivo-configuravel-e-transformacao-de*
*Context gathered: 2026-06-24*
