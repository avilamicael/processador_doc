# Phase 6: Automações de Arquivo (Renomear/Mover) - Research

**Researched:** 2026-06-17
**Domain:** Operações de arquivo seguras/reversíveis no Windows (rename/move atômico, cross-device, anti-colisão), audit-log write-ahead + undo, e motor de regras condicionais sobre campos extraídos
**Confidence:** HIGH (operações de arquivo Windows, padrões do código existente, modelagem de regras) / MEDIUM (mecânica exata de undo sob estado externo mutável — Claude's Discretion)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Disparo da automação**
- **D-01:** Auto-aplica para documentos de alta confiança (acima do `review_confidence_threshold` da Fase 5 — i.e., os que NÃO caíram em EM_REVISAO). Documentos de baixa confiança / em revisão só têm a automação aplicada **após** aprovação humana.
- **D-02:** Mesmo no auto-aplica, as garantias de segurança NÃO são puladas: log-antes-de-agir e undo continuam valendo. O auto-aplica só dispensa o clique humano de confirmação para os de alta confiança.
- **D-03:** Aplicação disponível **por documento E por lote/execução** (espelha o undo de AUT-05, que é por-doc e por-lote).

**Regras condicionais (TPL-02)**
- **D-04:** O usuário expressa regras como **condições estruturadas `{campo} [operador] valor`** (operadores: =, >, <, contém; combináveis com E/OU) → **qual automação aplicar**. Cobre tipo/cliente/emissor/valor (ex.: "tipo == holerite E valor > 3000 → pasta Análise").
- **D-05:** **Precedência por ordem de prioridade**: regras ordenadas pelo usuário; a **primeira que casar vence**. Simples de entender e depurar; o usuário controla a ordem.

**Padrões de nome e pasta (AUT-01/AUT-02)**
- **D-06:** Padrões usam tokens `{campo}` referenciando os campos extraídos (ex.: `{cliente}_{numero}_{data}.pdf`, `Documentos/{cliente}/{ano-mes}/`).
- **D-07:** **Campo vazio/inválido no padrão → bloqueia e manda pra revisão humana** (não aplica nome incompleto). Mesmo um documento de alta confiança é **rebaixado para revisão** se faltar um campo usado no nome/pasta. Evita arquivos com nome quebrado.
- **D-08:** O sistema **sanitiza automaticamente** caracteres inválidos no Windows (`\ / : * ? " < > |`) e **formata datas** via sufixo no token (ex.: `{data:aaaa-mm}`). O usuário não precisa se preocupar com isso.

**Política de colisão (AUT-04)**
- **D-09:** Destino já ocupado por arquivo de **conteúdo DIFERENTE** (mesmo nome) → **sufixo incremental automático** (`nome_1.pdf`, `nome_2.pdf`). Nunca sobrescreve, não trava o fluxo, nada se perde; a colisão é registrada no log/dry-run.
- **D-10:** Destino já ocupado por arquivo de **conteúdo IDÊNTICO** (mesmo SHA-256 do CAS) → **considera já-feito e pula como duplicata** (não cria `_1` de cópias idênticas). Reusa o dedup por hash já existente.

### Claude's Discretion
- Comportamento detalhado do **undo quando o arquivo de destino já foi movido/renomeado/apagado pelo usuário** depois da automação (resolver com checagem de integridade + falha controlada, sem corromper estado).
- **Formato/estrutura do audit log** (extensão do modelo `AuditLog` existente para guardar origem→destino + dados de undo).
- **Onde a automação aparece na UI**: nova aba de Automações (padrões + regras condicionais) + tela de dry-run/preview com pares origem→destino e colisões sinalizadas. Honra o design system travado (mesmos tokens das fases 2/4/5).
- Mecânica cross-device (AUT-06): copia→verifica(hash)→remove a origem.

### Deferred Ideas (OUT OF SCOPE)
- Automações além de renomear/mover (chamar API, enviar por e-mail/WhatsApp) — fora do v1 (PROJECT.md "Não-objetivos").
- Separação de documentos dirigida por IA e roteamento determinístico de custo (boleto/NF-e sem IA) — Fase 7.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AUT-01 | Padrões de renomeação com `{campo}` | §Padrão de tokens + sanitização (D-06/D-08); reusa `FilledField.normalized_value` e `validation/dates.py` para `{data:aaaa-mm}` |
| AUT-02 | Padrões de pasta-destino com `{campo}` | Mesmo motor de tokens; cada segmento de pasta é sanitizado individualmente; pasta criada com `mkdir(parents=True)` |
| AUT-03 | Dry-run/preview origem→destino, colisões sinalizadas | §Pattern Dry-run puro (resolução de destino + checagem de colisão SEM tocar disco); colisão via `cas`/SHA-256 (D-09/D-10) |
| AUT-04 | Audit log ANTES de agir + anti-colisão (nunca sobrescreve) | §Audit write-ahead (intent→executa→outcome); estende `AuditLog`; `os.open(O_CREAT\|O_EXCL)` / `Path.exists()` para nunca sobrescrever |
| AUT-05 | Undo por-documento E por-lote/execução | §Undo reversível; coluna `run_id`/`batch_id` no audit + CAS como rede de segurança final |
| AUT-06 | Cross-device seguro (copia→verifica→remove) | §Mover entre volumes: `os.replace` → fallback EXDEV → copy+fsync+verifica hash+remove (reusa `cas.store`/`hashing`) |
| TPL-02 | Regras condicionais por tipo/cliente/emissor/valor | §Motor de regras: novas tabelas `automation_rules`/`rule_conditions`/`automation_actions`; avaliador puro sobre `FilledField` normalizado |
</phase_requirements>

## Summary

Esta fase transforma o documento já classificado/aprovado num **efeito real sobre o sistema de arquivos do cliente** — a operação de maior risco de todo o produto (a constraint da CLAUDE.md é categórica: "nunca pode causar perda"). A boa notícia é que **a fundação de segurança já existe**: o CAS imutável por SHA-256 (`storage/cas.py`) preserva uma cópia íntegra de cada bloco para sempre, dando uma rede de recuperação independente do arquivo físico do cliente; a máquina de estados com allowlist (`pipeline/states.py`) já roteia para EM_REVISAO; o `AuditLog` já existe como casca esperando esta fase; e `validation/fields.py`/`dates.py`/`money.py` já normalizam exatamente os tipos que os tokens de nome e as condições numéricas precisam.

O trabalho concentra-se em três motores novos, todos seguindo o padrão já provado nas Fases 3–5 (função pura isolável → persistência atômica num único commit → step no worker): (1) **resolução de destino** (tokens `{campo}` → caminho sanitizado, com bloqueio→revisão quando falta campo, D-07); (2) **operação de arquivo segura** (audit write-ahead → `os.replace` atômico no mesmo volume, ou copia→verifica-hash→remove entre volumes, com anti-colisão por sufixo/dedup, D-09/D-10); e (3) **avaliador de regras condicionais** (condições estruturadas sobre campos normalizados, primeira-que-casa-vence, D-04/D-05). Tudo apenas em Python stdlib + as libs já no projeto — **nenhuma dependência nova é necessária**.

**Primary recommendation:** Modele a operação de arquivo como um novo **step de fila `apply`** que roda DEPOIS de classify/aprovação, espelhando `classify_stage` em forma e garantias atômicas. Escreva o registro de auditoria com `status=intent` ANTES de tocar o disco, execute a operação física (idempotente e nunca-sobrescreve), e atualize o mesmo registro para `status=done`+dados-de-undo num commit; um crash entre intent e done deixa um rastro auditável e reconciliável no startup. **Resolva primeiro a Open Question 1 (qual arquivo físico é movido)** — é a maior incógnita de design da fase.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Avaliação de regras condicionais (TPL-02) | API/Backend (módulo puro) | — | Lógica de negócio determinística sobre campos extraídos; nenhuma IA, nenhum disco — função pura testável, como `matcher`/`filler` |
| Resolução de tokens `{campo}` → caminho | API/Backend (módulo puro) | Database (lê `FilledField`) | Substituição + sanitização + format de data é transformação pura sobre dados já persistidos |
| Operação física rename/move | API/Backend (worker step) | Filesystem/OS | Tocar NTFS é responsabilidade do backend rodando na máquina do cliente; nunca do browser |
| Audit write-ahead + undo | Database / Storage | Filesystem (CAS) | Persistência transacional do intent/outcome; CAS é a rede de recuperação física |
| Dry-run/preview | API/Backend (puro) → exposto via API | Frontend (render) | Resolução de destino + colisão é backend; o React só renderiza pares origem→destino |
| Disparo (auto vs. pós-aprovação) | API/Backend (worker + endpoint) | — | O limiar e a transição de estado são autoridade do backend (Fase 5 seam) |
| UI de Automações + dry-run | Frontend (SSR não aplicável; SPA Vite) | API/Backend | Token-driven, mesmos padrões TanStack Query das Fases 2/4/5 |

## Standard Stack

### Core

**Nenhuma dependência nova é necessária.** A fase é construída inteiramente sobre a stdlib do Python 3.12 e bibliotecas já presentes no projeto.

| Lib / Módulo | Origem | Propósito nesta fase | Por que é o padrão |
|--------------|--------|----------------------|--------------------|
| `os` (`os.replace`, `os.open` `O_CREAT\|O_EXCL`, `os.fsync`, `os.stat`) | stdlib | Rename/replace atômico no mesmo volume; criação exclusiva anti-sobrescrita; durabilidade | `os.replace` é a primitiva atômica portável (Windows `MoveFileEx`/POSIX `rename`) — já usada com sucesso no `cas.py` `[VERIFIED: backend/app/storage/cas.py:107]` |
| `shutil` (`shutil.copyfile` / `copy2`) | stdlib | Cópia de bytes na trilha cross-device (AUT-06) | `shutil.move` lida com EXDEV, mas para AUT-06 queremos **copia→verifica→remove explícito** (controle de hash), não a magia opaca do `move` `[CITED: docs.python.org/3/library/shutil]` |
| `pathlib.Path` | stdlib | Manipulação de caminho, `mkdir(parents=True, exist_ok=True)`, `.exists()`, `.stat()` | Já é o padrão do projeto (`watched_folders.py`, `cas.py`) `[VERIFIED: codebase]` |
| `hashlib.sha256` | stdlib (via `storage/cas.py` + `ingest/hashing.py`) | Verificação pós-cópia cross-device (AUT-06) e detecção idêntico/diferente na colisão (D-09/D-10) | Reusa o MESMO hashing do CAS — o hash já calculado é `Document.content_hash` `[VERIFIED: backend/app/models/document.py:42]` |
| `SQLAlchemy 2.0` + `Alembic` | já no projeto | Tabelas de regras + extensão do `AuditLog`; migração **0006** | Padrão travado: "Migrações somente via Alembic" `[VERIFIED: CONTEXT.md code_context]` |
| `Pydantic 2.13` | já no projeto | Schemas In/Patch/Out dos endpoints de automação/regras | Espelha `watched_folders.py`/`templates.py` `[VERIFIED: codebase]` |
| `validation/fields.py`, `dates.py`, `money.py` | já no projeto | Format de `{data:...}` e coerção de tipos para comparação numérica das condições | Reuso direto — `normalize_date` devolve ISO `YYYY-MM-DD` fatiável; `normalize_money_brl` devolve string `Decimal` comparável `[VERIFIED: backend/app/validation/dates.py, money.py]` |

### Supporting (opcional — avaliar, não obrigatório)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pathvalidate` | 3.3.1 | Sanitização robusta de nome de arquivo + detecção de nomes reservados Windows (CON/PRN/NUL/COM1…) e truncamento por comprimento | **Só se** o planejador decidir não hand-rollar. Cobre casos que a lista simples de D-08 não cobre (nomes reservados, trailing dot/space, MAX_PATH). MIT, mantida (`github.com/thombashi/pathvalidate`). `[ASSUMED]` — ver Package Legitimacy Audit |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Sanitização hand-rolled (D-08) | `pathvalidate` 3.3.1 | Hand-roll cobre exatamente os 9 chars de D-08 + format de data, é zero-dependência e alinha com a cultura do projeto de hand-rollar determinismo (boleto/CNPJ/datas). `pathvalidate` adiciona cobertura de **nomes reservados Windows** e **MAX_PATH** que a lista de D-08 NÃO menciona — isto é um gap real de confiabilidade Windows. **Recomendação:** hand-roll a substituição dos 9 chars (D-08 explícito), MAS incluir explicitamente o tratamento de nomes reservados e comprimento (ver Pitfalls 4 e 5), seja à mão seja via lib. |
| `shutil.move` para cross-device | copia→fsync→verifica-hash→remove manual | `shutil.move` esconde o EXDEV e NÃO verifica integridade pós-cópia; AUT-06 exige "verifica e só então remove a origem" — o controle manual é o requisito, não escolha de estilo. |
| Linguagem de expressão (eval/AST) p/ regras | Condições estruturadas `{campo}[op]valor` | Nunca usar `eval`. As condições estruturadas (D-04) são exatamente o que evita injeção e mantém depurável (D-05). |

**Installation:**
```bash
# NENHUMA dependência nova obrigatória. Tudo é stdlib + libs já instaladas.
# OPCIONAL (somente se o planejador escolher não hand-rollar a sanitização):
#   cd backend && uv add pathvalidate==3.3.1
#   (requer gate de verificação humana — ver Package Legitimacy Audit)
```

**Version verification:** `pathvalidate` confirmado no PyPI: versão atual **3.3.1**, licença MIT, repo `github.com/thombashi/pathvalidate` `[VERIFIED: pip index versions pathvalidate → 3.3.1; pypi.org/pypi/pathvalidate/json → license MIT]`. Python do projeto: 3.12.13 `[VERIFIED: backend/.venv python --version]`.

## Package Legitimacy Audit

> slopcheck **não pôde ser instalado** (pip offline no sandbox). Por protocolo, qualquer pacote novo é tratado como `[ASSUMED]` e o planejador DEVE colocar um `checkpoint:human-verify` antes de instalá-lo. Como a recomendação primária é **zero-dependência**, este gate só se aplica se o planejador optar pela lib opcional.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `pathvalidate` | PyPI | ~10 anos (releases desde 2016, atual 3.3.1) | alto (lib popular de filename) | github.com/thombashi/pathvalidate (MIT) | indisponível (offline) | **Flagged** — opcional; se adotada, planejador insere `checkpoint:human-verify` antes do `uv add` |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none por evidência; `pathvalidate` marcado `[ASSUMED]` apenas porque slopcheck não rodou neste ambiente offline. Metadados verificados manualmente (MIT, repo oficial thombashi, versionamento longo e consistente) reduzem o risco a baixo, mas o gate humano permanece por disciplina.

*Recomendação operacional: a stack-padrão desta fase é stdlib-only; preferir hand-roll evita o gate inteiramente.*

## Architecture Patterns

### System Architecture Diagram

```
                    Documento classificado/aprovado
                    (state PROCESSANDO+classificado de alta confiança  → auto, D-01
                     OU EM_REVISAO→CONCLUIDO via aprovação humana)
                                    │
                                    ▼
                    ┌──────────────────────────────────────┐
                    │  Worker: novo step "apply" (fila)      │  ← espelha classify dispatch
                    └──────────────────────────────────────┘
                                    │
                                    ▼
       ┌─────────────────────────────────────────────────────────────┐
       │  apply_stage(session, content_hash)  [função pura+persist.]   │
       │                                                               │
       │  1. Lê FilledField (normalized_value) do doc                   │
       │  2. AVALIADOR DE REGRAS (puro) ───────────────► escolhe a      │
       │     condições {campo}[op]valor, 1ª que casa vence (D-05)       │  automação
       │  3. RESOLVE DESTINO (puro) ────────────────────► caminho final │
       │     tokens {campo}/{data:fmt} → sanitiza (D-08)                │
       │        │  campo faltante/inválido? ──► transition(EM_REVISAO)  │  (D-07, bloqueia)
       │        ▼                                                       │
       │  4. CHECA COLISÃO (puro, lê disco read-only)                   │
       │     destino existe? ── hash igual (CAS/SHA-256)? ─► PULA (D-10)│
       │                    └─ hash diferente? ─► sufixo _1/_2 (D-09)   │
       │        │                                                       │
       │        ▼  (modo DRY-RUN para aqui e retorna o preview)          │  ← AUT-03
       │  5. AUDIT WRITE-AHEAD: AuditLog(status=intent, src→dst, undo)  │  ← AUT-04 (ANTES de agir)
       │        │  commit                                               │
       │        ▼                                                       │
       │  6. OPERAÇÃO FÍSICA:                                           │
       │     mesmo volume?  ── os.replace(src→dst)  [atômico]           │
       │     volumes difer.? ─ copy→fsync→verifica SHA-256→remove src   │  ← AUT-06
       │        │  (nunca sobrescreve: O_EXCL/exists-check garantidos)   │
       │        ▼                                                       │
       │  7. AuditLog(status=done) + transition(CONCLUIDO) [1 commit]   │
       └─────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
            CAS (SHA-256) preserva o conteúdo original PARA SEMPRE
            ── rede de recuperação independente do arquivo físico ──
                                    │
                                    ▼
        UNDO (por-doc ou por-run/batch): lê AuditLog status=done,
        reverte dst→src (ou restaura do CAS se dst sumiu); marca status=undone
```

### Recommended Project Structure
```
backend/app/
├── automation/                    # NOVO módulo (espelha classification/)
│   ├── __init__.py
│   ├── rules.py                   # avaliador PURO: condições {campo}[op]valor (D-04/D-05)
│   ├── naming.py                  # resolução PURA de tokens→caminho + sanitização (D-06/D-07/D-08)
│   ├── fileops.py                 # operação física segura: replace/cross-device/anti-colisão (AUT-04/06, D-09/D-10)
│   ├── stage.py                   # apply_stage: orquestra rules→naming→fileops→audit→estado (1 commit)
│   └── undo.py                    # reversão por-doc e por-run (AUT-05)
├── models/
│   ├── audit_log.py               # ESTENDER: src/dst/run_id/status/undo_data (migração 0006)
│   └── automation_rule.py         # NOVO: AutomationRule + RuleCondition + AutomationAction
├── api/
│   └── automations.py             # NOVO: CRUD regras/padrões + POST /dry-run + POST /apply + POST /undo
└── alembic/versions/
    └── 0006_automations.py        # NOVO: tabelas de regra + colunas do audit
```

### Pattern 1: Stage com persistência atômica num único commit (REUSAR)
**What:** O `apply_stage` segue EXATAMENTE a forma de `classify_stage`: função `async`/`def` isolável, idempotente, que checa um registro existente ANTES de agir e persiste tudo num único `session.commit()` (ou via `transition`, que comita internamente).
**When to use:** Sempre — é o padrão estabelecido do pipeline.
```python
# Padrão (derivado de backend/app/classification/stage.py:160-364) [VERIFIED: codebase]
# 1. Localiza o doc por content_hash → None = ValueError (worker re-tenta)
# 2. IDEMPOTÊNCIA: AuditLog(status=done) já existe p/ este doc → no-op (não re-move)
# 3. ... avalia/resolve/checa colisão ...
# 4. transition(session, doc, DocState.CONCLUIDO, completed_step="aplicado")
#    → comita CR/audit/estado JUNTOS; allowlist PROCESSANDO→CONCLUIDO já existe
```
**Atenção crítica (do classify_stage):** NUNCA `session.commit()` manual antes de um `transition` — o `transition` comita tudo junto; commitar antes quebra a atomicidade `[VERIFIED: backend/app/classification/stage.py:341-346]`.

### Pattern 2: Audit write-ahead (intent → executa → outcome)
**What:** Antes de tocar o disco, persistir um `AuditLog` com `status="intent"` + origem + destino resolvido + payload de undo. Depois da operação física, atualizar para `status="done"`. Crash no meio = registro `intent` órfão, reconciliável no startup do worker.
**When to use:** AUT-04 ("registra a intenção ANTES de agir").
**Por quê NÃO basta o `os.replace` atômico:** o requisito é **auditar a intenção**, não só executar atômico. E há o ponto fino do Windows: `MoveFileEx` (que o `os.replace` usa) **pode silenciosamente cair para um `CopyFile` não-atômico** em circunstâncias indocumentadas `[CITED: github.com/untitaker/python-atomicwrites#25 discussion]` — o write-ahead é a rede contra essa janela.
```python
# 1. session.add(AuditLog(document_id=doc.id, action="move", status="intent",
#       source_path=str(src), dest_path=str(dst), run_id=run_id,
#       details=json.dumps({"undo": {"restore_to": str(src)}})))
#    session.commit()                 # <-- ANTES de tocar o disco
# 2. fileops.safe_move(src, dst)      # operação física
# 3. audit.status = "done"; transition(doc, CONCLUIDO); # 1 commit
```

### Pattern 3: Operação de arquivo segura por volume (AUT-06)
**What:** Decidir a trilha pela comparação de volume; nunca sobrescrever; verificar integridade na trilha cross-device.
```python
def safe_move(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    # ANTI-COLISÃO (nunca sobrescreve): o dst já foi resolvido p/ um nome livre
    # (sufixo _1/_2, D-09) ou pulado (D-10) ANTES de chegar aqui. Defesa extra:
    # criar exclusivo. os.replace SOBRESCREVE — por isso a resolução é a montante.
    try:
        os.replace(src, dst)                         # mesmo volume: atômico
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        # CROSS-DEVICE (AUT-06): copia → fsync → verifica hash → remove origem
        expected = sha256_of(src)                    # mesmo hashing do CAS
        tmp = dst.with_suffix(dst.suffix + ".partial")
        shutil.copyfile(src, tmp)
        with open(tmp, "rb") as f: os.fsync(f.fileno())
        if sha256_of(tmp) != expected:               # VERIFICA antes de remover
            tmp.unlink(missing_ok=True)
            raise IntegrityError("hash divergente pós-cópia cross-device")
        os.replace(tmp, dst)                         # commit local atômico
        src.unlink()                                 # só REMOVE após verificar
```
**Fonte da semântica EXDEV / errno 18:** `[CITED: alexwlchan.net/2019/atomic-cross-filesystem-moves-in-python; docs.python.org/3/library/os#os.replace]`. **Confirma `os.replace` atômico same-volume + falha cross-device** `[VERIFIED: WebSearch cross-referenced docs.python.org]`.

### Pattern 4: Avaliador de regras puro (D-04/D-05)
**What:** Sobre os `FilledField.normalized_value` do documento, avaliar cada `AutomationRule` na ordem de prioridade; a primeira cujas condições (`{campo}[op]valor`, combinadas E/OU) casam decide a automação.
```python
# Comparação por tipo do campo (REUSA validation/):
#  =      : igualdade sobre normalized_value (string)
#  >, <   : se o campo é moeda/numero/data → comparar Decimal/data ISO, não string
#           (normalize_money_brl já devolve string Decimal-comparável;
#            normalize_date devolve ISO YYYY-MM-DD, lexicograficamente ordenável)
#  contém : substring case-insensitive sobre raw_value/normalized_value
# Primeira regra que casa vence (D-05); nenhuma casa → automação default/nenhuma.
```
**Anti-pattern:** NUNCA `eval()` da condição. As condições são dados estruturados (3 colunas: campo, operador, valor), avaliados por um dispatch explícito por operador.

### Anti-Patterns to Avoid
- **Sobrescrever silenciosamente:** jamais `os.replace(src, dst)` sem que `dst` já tenha sido resolvido para um caminho livre (D-09) — `os.replace` SOBRESCREVE por design. A anti-colisão é a montante, na resolução do nome.
- **Mover sem CAS como rede:** o CAS já preserva o conteúdo; nunca tratar o arquivo físico como a única cópia.
- **`document.state = ...` direto:** sempre via `transition` (allowlist). Anti-pattern explícito no worker `[VERIFIED: backend/app/queue/worker.py:84]`.
- **Commit por operação dentro de um lote atômico:** quebra a reversibilidade do batch (mesma lição do `ingest_stage` CR-02).
- **Comparar `>`/`<` de moeda como string:** `"100" > "99"` é `False` lexicograficamente. Coerção para Decimal/data é obrigatória nas condições numéricas.
- **Assumir que existe um arquivo físico por bloco:** ver Open Question 1 — **não existe** para blocos separados.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Rename atômico same-volume | wrapper próprio sobre `MoveFileEx` | `os.replace` | Já é a primitiva portável usada no `cas.py`; reescrever só adiciona bugs |
| Hash de verificação cross-device | novo hasher | `ingest/hashing.py` + `storage/cas.py` (SHA-256) | O hash do bloco JÁ é `Document.content_hash`; recalcular com outro código diverge |
| Cópia de bytes com buffer | loop manual `read()/write()` | `shutil.copyfile` | stdlib, testada, lida com chunks |
| Recuperação do conteúdo original (undo último-recurso) | backup paralelo | CAS (`cas.read_bytes(content_hash)`) | O CAS é exatamente a rede de segurança imutável — `[VERIFIED: backend/app/storage/cas.py]` |
| Normalização de data/moeda p/ tokens e condições | parser novo | `validation/dates.py`, `validation/money.py` | Já resolvem `dayfirst` pt-BR e Decimal; reusar mantém consistência com a extração |
| Sanitização de nome reservado/MAX_PATH Windows | lista incompleta | `pathvalidate` 3.3.1 OU tratamento explícito documentado | A lista de 9 chars de D-08 NÃO cobre CON/PRN/NUL nem o limite de 260 — gap de confiabilidade Windows (ver Pitfalls 4/5) |

**Key insight:** A fase parece "só renomear arquivos", mas o domínio é **integridade de dados sob falha parcial no Windows**. Cada peça de segurança que você precisaria construir (cópia imutável, hashing, máquina de estados reversível, audit) **já está construída e testada** no projeto — o valor desta fase é orquestrá-las corretamente, não reinventá-las.

## Runtime State Inventory

> Fase de **efeito sobre o filesystem do cliente** (não rename de código). O inventário abaixo cobre o estado de runtime que esta fase cria/move e que afeta undo e idempotência.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `AuditLog` (existe, mínimo) será a fonte de verdade do undo. `ClassificationResult`/`FilledField` guardam os valores que viram tokens. `IngestedOriginal.source_folder_id`→`WatchedFolder.path` é o ÚNICO lugar que reconstrói o caminho de origem do **original** (não há coluna de caminho absoluto). | Migração 0006: estender `AuditLog` (src/dst/status/run_id/undo_data). Decidir persistência do caminho-fonte (ver Open Q1). |
| Live service config | Nenhuma. Single-tenant, sem serviço externo registrando estado. | None — verificado: não há broker/serviço externo no modo padrão (fila in-process SQLite). |
| OS-registered state | O arquivo FÍSICO do cliente no NTFS é o estado mutável externo crítico. Após mover, o caminho de origem deixa de existir; o usuário pode mexer no destino. | Undo deve checar integridade do destino (hash) antes de reverter; falha controlada se o destino sumiu/mudou (Claude's Discretion). |
| Secrets/env vars | `review_confidence_threshold` (lido da config, governa o auto-aplica D-01). Nenhum segredo novo. | None — reusa a config existente da Fase 5 `[VERIFIED: backend/app/config.py:151]`. |
| Build artifacts | Nenhum artefato compilado afetado. CAS blobs em `data_dir/cas` são imutáveis e crescem (rede de segurança), não precisam limpeza nesta fase. | None. |

**A pergunta canônica respondida:** depois de mover/renomear o arquivo do cliente, o que ainda tem o estado antigo? **(1)** o `AuditLog` precisa do caminho de origem para o undo — e esse caminho NÃO está persistido hoje (Open Q1); **(2)** o CAS mantém o conteúdo por hash independente do caminho físico — é a rede final.

## Common Pitfalls

### Pitfall 1: `os.replace` sobrescreve — anti-colisão tem que ser a montante
**What goes wrong:** `os.replace(src, dst)` apaga `dst` se existir, silenciosamente. Confiar nele para "não sobrescrever" viola AUT-04 e D-09.
**Why it happens:** A semântica POSIX/`MoveFileEx(REPLACE_EXISTING)` é sobrescrever por design.
**How to avoid:** Resolver o nome de destino para um caminho LIVRE (sufixo `_1/_2`, D-09) ou decidir PULAR (D-10) ANTES de chamar `safe_move`. Como defesa em profundidade, criar o destino exclusivo (`O_CREAT|O_EXCL`) ou checar `dst.exists()` imediatamente antes; mas a verdade é a resolução de nome.
**Warning signs:** Teste que move dois docs diferentes para o mesmo padrão e verifica que ambos sobrevivem (nenhum sumiu).

### Pitfall 2: Comparação numérica/data de condições como string
**What goes wrong:** Regra "valor > 3000" avaliada como string: `"500" > "3000"` é `True` (lexicográfico). Documento de R$500 é roteado errado.
**Why it happens:** `FilledField.normalized_value` é `Text`.
**How to avoid:** No avaliador, coerção por `field_type`: moeda/numero → `Decimal`; data → comparar ISO `YYYY-MM-DD` (já ordenável) ou objeto `date`. O `validation/money.py`/`dates.py` já produzem essas formas.
**Warning signs:** Casos de teste com valores que invertem na ordem lexicográfica (500 vs 3000, "2026-01" vs "2026-1").

### Pitfall 3: `os.replace` cross-device cai em `OSError EXDEV` (errno 18)
**What goes wrong:** Mover de `C:\` para `D:\` (ou para um share de rede) com `os.replace` levanta `OSError` errno 18 (`EXDEV`) — a operação NÃO acontece.
**Why it happens:** `rename`/`MoveFileEx` não atravessa volumes atomicamente.
**How to avoid:** `try os.replace` → `except OSError if errno==EXDEV` → trilha copia→fsync→verifica-hash→remove (AUT-06). NÃO usar `shutil.move` cego (esconde o EXDEV e não verifica integridade).
**Warning signs:** Teste cross-device (simular com dois temp dirs em mounts diferentes, ou mock do errno) — `[CITED: alexwlchan.net/2019/atomic-cross-filesystem-moves-in-python]`.

### Pitfall 4: Nomes reservados do Windows passam pela lista de 9 chars de D-08
**What goes wrong:** D-08 sanitiza `\ / : * ? " < > |`, mas um campo extraído com valor `CON`, `PRN`, `NUL`, `COM1`…`LPT9` (mesmo com extensão, ex.: `NUL.pdf`) é um nome **proibido** no Windows e o `open()`/`replace()` falha ou redireciona para o device.
**Why it happens:** A lista de D-08 cobre só caracteres, não nomes reservados.
**How to avoid:** Após substituir os 9 chars, checar se o stem (case-insensitive) é reservado e, se for, prefixar/sufixar (ex.: `_CON`). `pathvalidate` faz isso automaticamente; à mão é uma lista de ~24 nomes.
**Warning signs:** Teste com campo cujo valor normaliza para `CON`/`NUL`.
`[CITED: learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file; meziantou.net/reserved-filenames-on-windows]`

### Pitfall 5: MAX_PATH (260) estoura com `{cliente}/{ano-mes}/` + nome longo
**What goes wrong:** Em Windows pré-1607 ou sem long-path habilitado, caminho > 260 chars faz a operação falhar. Padrões com várias pastas + nomes longos atingem isso.
**Why it happens:** Limite histórico do Win32 API.
**How to avoid:** Truncar componentes longos do nome (preservando a extensão) a um teto seguro; opcionalmente prefixar com `\\?\` no Windows para long paths. Documentar o limite. NÃO assumir long-path habilitado no cliente.
**Warning signs:** Teste com padrão que gera caminho > 260.
`[CITED: learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation]`

### Pitfall 6: Lock de arquivo no Windows (compartilhamento exclusivo)
**What goes wrong:** Windows trava arquivos abertos por outro processo (ex.: o usuário abriu o PDF no Acrobat); `os.replace`/`unlink` falham com `PermissionError` (WinError 32).
**Why it happens:** Semântica de compartilhamento do Windows (diferente do POSIX, onde rename de arquivo aberto é OK).
**How to avoid:** Tratar `PermissionError`/`OSError` como FALHA retryável da operação (o write-ahead garante que o estado fique reconciliável); não corromper o documento — deixá-lo num estado que permita re-tentar. O projeto já tem o padrão de FALHA via `transition` + retry/dead-letter no worker.
**Warning signs:** Operação intermitente que falha quando o arquivo está aberto.

### Pitfall 7: Crash entre `intent` e `done` (reconciliação)
**What goes wrong:** Worker morre depois de escrever `AuditLog(status=intent)` e fazer o `os.replace`, mas antes de marcar `done`. No restart, o estado fica ambíguo.
**Why it happens:** Falha parcial — inerente a qualquer operação de duas etapas.
**How to avoid:** Reconciliação no startup (espelha `requeue_running` do worker): para cada `AuditLog(status=intent)` órfão, checar o filesystem (origem ainda existe? destino existe com o hash esperado?) e decidir done/retry/rollback. A idempotência (`status=done` já existe → no-op) + a checagem de existência tornam isso seguro.
**Warning signs:** Teste que simula crash entre as etapas e verifica que o restart converge sem perder o arquivo.

## Code Examples

### Resolução de token com format de data e sanitização (D-06/D-07/D-08)
```python
# Source: derivado de validation/dates.py (ISO YYYY-MM-DD) [VERIFIED: codebase]
import re

_WIN_INVALID = r'\/:*?"<>|'                       # os 9 chars de D-08
_WIN_RESERVED = {"CON","PRN","AUX","NUL",*(f"COM{i}" for i in range(1,10)),
                 *(f"LPT{i}" for i in range(1,10))}  # Pitfall 4

def _fmt_date(iso: str, spec: str) -> str:
    # {data:aaaa-mm} sobre normalized_value ISO "2026-04-03"
    y, m, d = iso.split("-")
    return spec.replace("aaaa", y).replace("mm", m).replace("dd", d)

def sanitize_component(value: str) -> str:
    cleaned = "".join("_" if c in _WIN_INVALID else c for c in value)
    cleaned = cleaned.rstrip(" .")                # trailing space/dot inválido no Win
    if cleaned.upper().split(".")[0] in _WIN_RESERVED:
        cleaned = "_" + cleaned                   # Pitfall 4
    return cleaned or "_"

def resolve_pattern(pattern: str, fields: dict[str, "FilledField"]) -> str | None:
    # Retorna None se algum token referencia campo faltante/inválido (D-07 → revisão).
    def repl(m: re.Match) -> str | None:
        name, _, spec = m.group(1).partition(":")
        ff = fields.get(name)
        if ff is None or not ff.valid or not ff.normalized_value:
            raise _MissingField(name)             # caller → transition(EM_REVISAO)
        val = _fmt_date(ff.normalized_value, spec) if spec else ff.normalized_value
        return sanitize_component(val)
    try:
        return re.sub(r"\{([^}]+)\}", lambda m: repl(m), pattern)
    except _MissingField:
        return None
```

### Resolução anti-colisão por hash (D-09/D-10)
```python
# Source: reusa storage/cas.py (SHA-256 do conteúdo) [VERIFIED: backend/app/storage/cas.py]
def resolve_collision(dst: Path, content_hash: str) -> Path | None:
    # Retorna o caminho final livre, ou None se for duplicata idêntica (D-10 → pula).
    if not dst.exists():
        return dst
    if _sha256_of_file(dst) == content_hash:      # D-10: idêntico → já-feito
        return None
    stem, suffix = dst.stem, dst.suffix           # D-09: diferente → sufixo
    i = 1
    while True:
        cand = dst.with_name(f"{stem}_{i}{suffix}")
        if not cand.exists():
            return cand
        if _sha256_of_file(cand) == content_hash:
            return None
        i += 1
```

### Extensão do AuditLog (migração 0006) — esqueleto
```python
# Source: padrão de alembic/versions/0005_confidence_review.py [VERIFIED: codebase]
# CAVEAT (Pitfall das migrações): se NÃO tocar a tabela `documents`, o trigger
# trg_documents_updated_at (criado na 0002) permanece intacto. Estender SÓ audit_log
# e criar as tabelas de regra — não fazer batch_alter_table em `documents`.
def upgrade() -> None:
    with op.batch_alter_table("audit_log") as b:
        b.add_column(sa.Column("status", sa.String(), nullable=False, server_default="done"))
        b.add_column(sa.Column("source_path", sa.Text(), nullable=True))
        b.add_column(sa.Column("dest_path", sa.Text(), nullable=True))
        b.add_column(sa.Column("run_id", sa.String(), nullable=True))   # AUT-05 batch/run
        b.add_column(sa.Column("content_hash", sa.String(64), nullable=True))  # undo via CAS
    op.create_table("automation_rules", ...)      # D-04/D-05 (priority, action)
    op.create_table("rule_conditions", ...)       # campo, operador, valor, conjunção
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `os.rename` (falha cross-device E ao sobrescrever no Windows) | `os.replace` (atômico same-volume, sobrescreve consistente) + fallback EXDEV explícito | Python 3.3+ | Já adotado no projeto; nada a migrar |
| `shutil.move` opaco para cross-device | copia→fsync→verifica-hash→remove explícito | requisito AUT-06 | Controle de integridade é o requisito, não preferência |
| Sub-templates por emissor (Fase 4 original) | Regras condicionais de automação (TPL-02 re-escopado p/ Fase 6) | 2026-06-16 | O que variava era a AUTOMAÇÃO, não a extração — modelo de regra, não de template |

**Deprecated/outdated:**
- `os.rename` para mover arquivos do cliente: substituído por `os.replace` + trilha cross-device.
- Qualquer ideia de "sub-template por emissor": morta; agora é regra condicional (TPL-02).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `pathvalidate` 3.3.1 é seguro/mantido (slopcheck não rodou offline) | Standard Stack / Package Audit | Baixo — metadados oficiais verificados (MIT, repo thombashi, histórico longo); gate humano cobre. Mitigado preferindo hand-roll. |
| A2 | O caminho físico de origem do **original** = `WatchedFolder.path / IngestedOriginal.original_filename` | Open Questions / Runtime Inventory | **ALTO** — se o original foi movido/renomeado pelo usuário entre ingestão e aplicação, o caminho reconstruído não existe mais. Ver Open Q1. |
| A3 | `MoveFileEx` pode cair em `CopyFile` não-atômico em casos raros | Pattern 2 | Médio — reforça a necessidade do write-ahead; mesmo se nunca ocorrer, o audit-antes-de-agir é exigido por AUT-04 de qualquer forma. |
| A4 | Comparar datas ISO `YYYY-MM-DD` lexicograficamente é equivalente a comparar cronologicamente | Pattern 4 / Pitfall 2 | Baixo — verdadeiro para datas completas ISO; cuidado com `{data:aaaa-mm}` (sem dia) que ainda ordena correto mês-a-mês. |

## Open Questions

1. **Qual arquivo físico é renomeado/movido — e onde está seu caminho?** (BLOQUEIA O DESIGN)
   - **O que sabemos:** Para um documento que NÃO foi separado (imagem, ou PDF sem split), existe 1 arquivo original em `WatchedFolder.path / original_filename` — reconstruível. Mas para **blocos de um PDF separado** (ING-05), o "documento" existe APENAS como blob no CAS (`data_dir/cas/...`); **não há arquivo físico individual no diretório do cliente** `[VERIFIED: backend/app/pipeline/ingest_stage.py:150-172 — blocos só vão ao CAS, nunca ao disco do cliente]`. Além disso, **nenhuma coluna persiste o caminho absoluto de origem** — só `original_filename` (basename) + `source_folder_id` `[VERIFIED: backend/app/models/ingested_original.py, document.py]`.
   - **O que não está claro:** O que "renomear/mover" significa para um bloco separado? Opções: (a) materializar o bloco do CAS para o destino (o destino é uma CÓPIA derivada do CAS, e o original multi-página fica/some conforme política); (b) só aplicar automação a documentos não-separados no v1; (c) mover o ORIGINAL inteiro quando `pages_per_block=None` (1 bloco = 1 arquivo) e materializar-do-CAS quando separado.
   - **Recommendation:** Decisão de produto a confirmar no plan. **Sugestão:** materializar o destino a partir do CAS (`cas.read_bytes(content_hash)` → escreve no destino), o que torna a operação uniforme para blocos e não-blocos E intrinsecamente segura (o CAS é a fonte; o arquivo do cliente na pasta de origem pode ser removido/quarentenado por política separada). Isso muda AUT-06 de "mover o original" para "materializar do CAS + verificar hash" — o que já é a operação mais segura possível. **Persistir o caminho de origem resolvido no `AuditLog` no momento da aplicação** (não depender de reconstrução posterior) resolve A2.

2. **Undo quando o destino foi alterado pelo usuário** (Claude's Discretion — confirmar abordagem)
   - **O que sabemos:** O CAS garante o conteúdo original por hash, sempre.
   - **O que não está claro:** Se o usuário moveu/editou/apagou o arquivo de destino, o undo deve: restaurar do CAS para a origem? falhar controladamente? avisar?
   - **Recommendation:** Undo checa integridade do destino por hash; se bate → reverte dst→origem; se o destino sumiu/mudou → **restaura o conteúdo do CAS para a origem** (rede final) e marca o audit como `undone_from_cas`, nunca corrompendo. Falha controlada + mensagem, jamais perda.

3. **Auto-aplica: qual transição de estado o documento de alta confiança faz?**
   - **O que sabemos:** Hoje o classify_stage deixa o doc de alta confiança em `PROCESSANDO` + `last_completed_step="classificado"` e NUNCA CONCLUIDO — exatamente para a Fase 6 capturá-lo `[VERIFIED: backend/app/classification/stage.py:357-364]`. A allowlist já tem `PROCESSANDO→CONCLUIDO`.
   - **O que não está claro:** O `apply` é enfileirado por um novo sweep (como `enqueue_pending_classifications`) que pega docs `PROCESSANDO+classificado` de alta confiança? E para os aprovados manualmente (que vão a CONCLUIDO via approve), como disparar o apply? (CONCLUIDO é terminal — sem aresta de saída).
   - **Recommendation:** Confirmar no plan. Possível: o `apply` roda ANTES da transição final a CONCLUIDO (apply é o que CONCLUI o doc); o approve manual também enfileira o `apply`. Revisar a allowlist se o apply precisar de um estado intermediário (ex.: `PROCESSANDO`→`PROCESSANDO`+step "aplicado"→`CONCLUIDO`).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python stdlib (`os`,`shutil`,`hashlib`,`pathlib`) | Toda a fase | ✓ | 3.12.13 | — |
| SQLAlchemy 2.0 + Alembic | Migração 0006 + modelos | ✓ | já instalado | — |
| CAS / hashing do projeto | AUT-06, D-10, undo | ✓ | `storage/cas.py`, `ingest/hashing.py` | — |
| `validation/*` (dates/money/fields) | Tokens + condições | ✓ | já instalado | — |
| `pathvalidate` (opcional) | Sanitização robusta | ✗ (não instalado) | 3.3.1 disponível no PyPI | Hand-roll a sanitização (recomendado) |
| Ambiente Windows real para teste NTFS | DIST-01 / Pitfalls 1,3,5,6 | ✗ (dev em WSL2/Linux) | — | Testar EXDEV/colisão com temp dirs no Linux; testes Windows-específicos (lock WinError 32, MAX_PATH, reservados) marcados para verificação manual no cliente Windows |

**Missing dependencies with no fallback:** Nenhuma bloqueia a fase. Os testes de comportamento puramente-Windows (lock de arquivo, MAX_PATH, nomes reservados) não rodam fielmente em WSL2/Linux — devem ser cobertos por testes unitários da LÓGICA (lista de reservados, truncamento) + verificação manual no Windows.
**Missing dependencies with fallback:** `pathvalidate` → hand-roll.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio `[VERIFIED: backend/tests/, conftest.py]` |
| Config file | `backend/tests/conftest.py` (fixtures de sessão/engine SQLite em memória) |
| Quick run command | `cd backend && . .venv/bin/activate && pytest tests/automation -x -q` |
| Full suite command | `cd backend && . .venv/bin/activate && pytest -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUT-01 | tokens `{campo}`→nome sanitizado | unit | `pytest tests/automation/test_naming.py -x` | ❌ Wave 0 |
| AUT-01/D-07 | campo faltante → None (→revisão) | unit | `pytest tests/automation/test_naming.py::test_missing_field_blocks -x` | ❌ Wave 0 |
| AUT-01/D-08 | sanitiza 9 chars + reservados + `{data:aaaa-mm}` | unit | `pytest tests/automation/test_naming.py -k sanitize -x` | ❌ Wave 0 |
| AUT-02 | tokens em pasta-destino + mkdir | unit | `pytest tests/automation/test_naming.py -k folder -x` | ❌ Wave 0 |
| AUT-03 | dry-run resolve origem→destino sem tocar disco | unit | `pytest tests/automation/test_stage.py -k dry_run -x` | ❌ Wave 0 |
| AUT-04 | audit `intent` escrito ANTES; nunca sobrescreve | unit | `pytest tests/automation/test_fileops.py -k no_overwrite -x` | ❌ Wave 0 |
| AUT-04/D-09 | colisão conteúdo diferente → `_1`/`_2`, ambos sobrevivem | unit | `pytest tests/automation/test_fileops.py -k collision_suffix -x` | ❌ Wave 0 |
| AUT-04/D-10 | colisão conteúdo idêntico (mesmo SHA) → pula | unit | `pytest tests/automation/test_fileops.py -k collision_duplicate -x` | ❌ Wave 0 |
| AUT-05 | undo por-doc e por-run restaura origem | unit | `pytest tests/automation/test_undo.py -x` | ❌ Wave 0 |
| AUT-05 | undo quando destino sumiu → restaura do CAS | unit | `pytest tests/automation/test_undo.py -k cas_fallback -x` | ❌ Wave 0 |
| AUT-06 | cross-device: copia→verifica-hash→remove (EXDEV simulado) | unit | `pytest tests/automation/test_fileops.py -k cross_device -x` | ❌ Wave 0 |
| AUT-06 | hash divergente pós-cópia → aborta, não remove origem | unit | `pytest tests/automation/test_fileops.py -k integrity -x` | ❌ Wave 0 |
| TPL-02/D-04 | condições `=,>,<,contém` + E/OU; numérico via Decimal | unit | `pytest tests/automation/test_rules.py -x` | ❌ Wave 0 |
| TPL-02/D-05 | primeira regra que casa vence (ordem de prioridade) | unit | `pytest tests/automation/test_rules.py -k precedence -x` | ❌ Wave 0 |
| AUT-04/Pitfall 7 | crash entre intent/done → reconciliação no startup | unit | `pytest tests/automation/test_stage.py -k reconcile -x` | ❌ Wave 0 |
| API | endpoints regras/dry-run/apply/undo (409/422/404) | integration | `pytest tests/test_api_automations.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/automation -x -q`
- **Per wave merge:** `pytest -q` (suite completa)
- **Phase gate:** Suite verde + verificação manual no Windows (lock/MAX_PATH/reservados) antes de `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/automation/__init__.py` + `tests/automation/conftest.py` — fixtures de doc classificado com FilledFields + temp dirs (origem/destino, mesmo e diferente "volume")
- [ ] `tests/automation/test_naming.py` — AUT-01/02, D-06/07/08
- [ ] `tests/automation/test_rules.py` — TPL-02, D-04/05
- [ ] `tests/automation/test_fileops.py` — AUT-04/06, D-09/10, EXDEV
- [ ] `tests/automation/test_stage.py` — orquestração, dry-run, idempotência, reconciliação
- [ ] `tests/automation/test_undo.py` — AUT-05 + fallback CAS
- [ ] `tests/test_api_automations.py` — espelha `test_api_templates.py`
- [ ] `tests/test_migrations.py` — estender p/ cobrir 0006 (trigger de documents intacto)

## Security Domain

> `security_enforcement: true`, ASVS level 1, block_on: high `[VERIFIED: .planning/config.json]`.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | App single-tenant local; sem contas (Out of Scope em REQUIREMENTS.md) |
| V3 Session Management | no | Idem |
| V4 Access Control | yes | **Path traversal**: o destino resolvido de tokens `{campo}` (valores vindos da IA/documento) pode conter `..` ou caminhos absolutos. O destino DEVE ser confinado sob uma raiz-base configurada (não permitir que um campo extraído escreva fora dela). Sanitização de componente já remove `\ /` mas confirmar confinamento por `resolve()` + checagem de prefixo. |
| V5 Input Validation | yes | Padrões de regra/nome são input do operador; condições são dados estruturados (sem `eval`). Valores de campo (da IA) são tratados como não-confiáveis ao virar caminho (V4). Regex de regra: reusar o teto `_MAX_REGEX_LEN` de `validation/fields.py` se houver operador regex. |
| V6 Cryptography | no | SHA-256 é integridade/dedup, não cripto secreta — `hashlib` stdlib, nunca hand-roll de primitiva |
| V7/V9 Logging | yes | **Não vazar conteúdo do documento em log** — padrão já estabelecido no `classify_stage` (loga só metadados: ids/paths, nunca valores de campo) `[VERIFIED: backend/app/classification/stage.py:34]`. Audit log guarda paths (necessário p/ undo) mas não o conteúdo dos campos sensíveis além do necessário. |

### Known Threat Patterns for Python file-ops + Windows

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via campo extraído (`{cliente}` = `..\..\Windows\System32`) | Elevation of Privilege / Tampering | Sanitizar componentes (remove `\ / :`) + confinar destino sob raiz-base via `resolved.is_relative_to(base)` (V4) |
| Sobrescrita destrutiva de arquivo existente | Tampering / Denial | Anti-colisão a montante (D-09) + `os.replace` só sobre caminho resolvido-livre; CAS como rede |
| Symlink/junction no destino apontando p/ fora | Tampering | Não seguir symlinks no destino; checar `is_symlink()` (padrão já usado em `watched_folders.py:65`) |
| TOCTOU entre checar colisão e mover | Tampering | Criação exclusiva (`O_CREAT\|O_EXCL`) ou aceitar a janela como risco baixo single-tenant + audit write-ahead reconciliável |
| Perda por falha parcial (crash mid-move) | Denial / data loss | Audit write-ahead + CAS imutável + reconciliação no startup (Pitfall 7) |
| ReDoS em regex de condição (se houver operador regex) | Denial | Teto de tamanho (`_MAX_REGEX_LEN`) já existente em `validation/fields.py:29` |

**Nota:** o vetor de segurança DOMINANTE desta fase é **integridade/perda de dados** (Tampering/Denial), não confidencialidade — alinhado à constraint "nunca pode causar perda". As mitigações primárias são CAS + audit write-ahead + anti-colisão, não controles de acesso.

## Sources

### Primary (HIGH confidence)
- Codebase do projeto (`backend/app/storage/cas.py`, `classification/stage.py`, `queue/worker.py`, `pipeline/state_machine.py`, `pipeline/states.py`, `models/*.py`, `validation/*.py`, `pipeline/ingest_stage.py`, `api/watched_folders.py`) — padrões, garantias e os ativos reutilizáveis citados. Lidos diretamente.
- `.planning/phases/06-.../06-CONTEXT.md`, `.planning/REQUIREMENTS.md`, `.planning/STATE.md`, `./CLAUDE.md`, `.planning/config.json` — decisões travadas, requisitos, stack.
- docs.python.org — `os.replace` (atômico same-volume, falha cross-device), `shutil` — semântica das primitivas.
- PyPI (`pip index versions pathvalidate` → 3.3.1; `pypi.org/pypi/pathvalidate/json` → MIT, repo thombashi) — verificação de versão/licença da lib opcional.

### Secondary (MEDIUM confidence)
- learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file — caracteres/nomes reservados Windows (CON/PRN/NUL…).
- learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation — MAX_PATH 260.
- alexwlchan.net/2019/atomic-cross-filesystem-moves-in-python — EXDEV (errno 18) + padrão copy-then-replace.

### Tertiary (LOW confidence)
- github.com/untitaker/python-atomicwrites#25 (discussão) — `MoveFileEx` pode cair em `CopyFile` não-atômico (motiva o write-ahead; o requisito AUT-04 já o exige independentemente).

## Metadata

**Confidence breakdown:**
- Standard stack (stdlib + libs do projeto): HIGH — tudo verificado no código; zero dependência nova.
- Arquitetura (apply_stage espelhando classify_stage, audit write-ahead, motor de regras): HIGH — segue padrões já provados e testados nas Fases 2–5.
- Operações de arquivo Windows (os.replace/EXDEV/colisão): HIGH para a mecânica; MEDIUM para os casos Windows-only (lock/MAX_PATH/reservados) que não testamos em WSL2.
- Undo sob estado externo mutável (Open Q2): MEDIUM — Claude's Discretion; recomendação dada, mas a abordagem final é decisão do plan.
- Open Question 1 (qual arquivo físico): a maior incógnita — design dependente de decisão de produto; **resolver antes de planejar tarefas de fileops**.

**Research date:** 2026-06-17
**Valid until:** ~2026-07-17 (stack estável, stdlib; reavaliar só se a decisão da Open Q1 mudar o escopo)
```