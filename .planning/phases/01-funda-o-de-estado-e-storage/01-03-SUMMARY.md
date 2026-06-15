---
phase: 01-funda-o-de-estado-e-storage
plan: 03
subsystem: storage-cas
tags: [cas, sha256, content-addressable, immutable-storage, streaming, atomic-write, windows, python-3.12]

# Dependency graph
requires:
  - "01-01: get_settings().data_dir e ensure_data_dir (app/config.py) — raiz do CAS deriva da pasta de dados única"
provides:
  - "app/storage/cas.py — fronteira única do CAS: store(src)->hash, path_for(hash), exists(hash), read_bytes(hash), open_blob(hash) e cas_root()"
  - "Armazenamento imutável endereçado por SHA-256 dentro de data_dir/cas (D-01); cópia preserva o original (D-07); recuperável por hash para sempre (D-08); idempotente por conteúdo"
affects: [02-ingestao-e-fila, 06-automacoes-reversibilidade]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "CAS endereçado por SHA-256 com sharding por prefixo do hash (data_dir/cas/ab/cd/<hash>)"
    - "Escrita imutável: temporário + os.replace (rename atômico portável Windows/POSIX) — nunca expõe blob meio-escrito"
    - "Hashing e cópia por streaming em chunks de 64KB — não carrega o arquivo inteiro em memória"
    - "Fronteira única de storage de blobs (espelha app/storage/db.py); sem API de delete/update (imutável — D-08)"

key-files:
  created:
    - backend/app/storage/cas.py
    - backend/tests/test_cas.py
  modified: []

key-decisions:
  - "Raiz do CAS computada em runtime via cas_root() = get_settings().data_dir / 'cas' (não constante de import) — permite isolar a pasta de dados por teste e respeita DATA_DIR de produção"
  - "store calcula o SHA-256 e copia simultaneamente no mesmo loop de streaming (single-pass) — evita ler o arquivo duas vezes"
  - "Temporário criado na raiz do CAS e movido (os.replace) para o diretório do shard antes do replace final — garante que tmp e blob fiquem no mesmo diretório/volume (rename atômico, não copy)"
  - "Idempotência por conteúdo: se path_for(hash) já existe, descarta o temporário e não reescreve o blob imutável (D-08)"

patterns-established:
  - "Todo acesso a blobs passa por app/storage/cas.py (fronteira única, como app/storage/db.py para o banco)"
  - "Blobs do CAS são imutáveis e mantidos para sempre no v1 — nenhuma operação de delete/update exposta"

requirements-completed: [DIST-01]

# Metrics
duration: 3min
completed: 2026-06-15
---

# Phase 1 Plan 3: CAS Imutável por Conteúdo (SHA-256) Summary

**Armazenamento endereçado por conteúdo (SHA-256) dentro da pasta de dados única (`data_dir/cas`): a ingestão COPIA o original preservando-o byte-a-byte (D-07), o conteúdo é recuperável pelo hash a qualquer momento como rede de segurança/undo (D-08), conteúdo idêntico nunca duplica blob, e a escrita é imutável e atômica (temporário + `os.replace`) — só com a stdlib, roda em Windows sem infra adicional (DIST-01).**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-06-15T22:21:24Z
- **Completed:** 2026-06-15T22:24:00Z
- **Tasks:** 1 (TDD)
- **Files created:** 2

## Accomplishments
- `app/storage/cas.py`: fronteira única do CAS com `store(src) -> hash`, `path_for(hash)`, `exists(hash)`, `read_bytes(hash)`, `open_blob(hash)` (context manager de streaming) e `cas_root()`.
- **Endereçamento por SHA-256** com sharding por prefixo (`data_dir/cas/ab/cd/<hash>`) — evita diretórios com milhares de arquivos no mesmo nível (degradação em NTFS/ext4).
- **Cópia que preserva o original** (D-07): `store` abre a origem somente para leitura, nunca a modifica nem remove; teste assere byte-igualdade pós-store.
- **Recuperação por hash para sempre** (D-08): `read_bytes`/`open_blob` devolvem o conteúdo original mesmo após o arquivo de origem ser removido por uma automação posterior (base do undo da Fase 6) — sem API de delete/update.
- **Idempotência por conteúdo:** armazenar o mesmo conteúdo duas vezes retorna o mesmo hash e mantém um único blob (temporário descartado quando o blob já existe).
- **Escrita imutável e atômica:** streaming em chunks de 64KB (sem carregar o arquivo inteiro), gravação em temporário + `os.replace` (rename portável Windows/POSIX), sem `.tmp` órfãos no caminho feliz.
- 11 testes novos, todos verdes; suíte total 40 verde; ruff limpo.

## Task Commits

Each task was committed atomically:

1. **Task 1: CAS por SHA-256 (store/recuperar/imutável/idempotente) dentro da pasta de dados** - `9617579` (feat, TDD RED→GREEN consolidado num commit)

_Tarefa TDD: testes (RED) e implementação (GREEN) foram consolidados num único commit (executor sequencial). RED foi verificado antes do GREEN: a suíte falhou com ImportError (módulo inexistente) e passou após a implementação._

## Files Created/Modified
- `backend/app/storage/cas.py` - Fronteira única do CAS: `cas_root()` (= `data_dir/cas`), `path_for` (sharding), `store` (hash+cópia streaming, temporário+`os.replace`, idempotente), `exists`, `read_bytes`, `open_blob`. Sem delete/update (imutável).
- `backend/tests/test_cas.py` - 11 testes: hash == SHA-256 do conteúdo; blob sob `data_dir/cas`; original preservado byte-a-byte; recuperação por hash; streaming via `open_blob`; idempotência (1 só blob); recuperação após "automação posterior" (origem removida); `exists` True/False; sem `.tmp` órfão; sharding por prefixo; ausência de delete/update.

## Decisions Made
- **Raiz do CAS em runtime (`cas_root()`), não constante de import:** deriva sempre de `get_settings().data_dir` no momento da chamada. Isso permite que os testes isolem a pasta de dados por teste (`DATA_DIR` + `get_settings.cache_clear()`) e respeita a precedência de configuração de produção, sem acoplar o módulo a um caminho fixo.
- **Single-pass hash+cópia:** o loop de streaming alimenta o `hashlib.sha256` e escreve o temporário ao mesmo tempo — o arquivo de origem é lido uma única vez.
- **Staging do temporário no diretório do shard antes do `os.replace` final:** o temporário nasce na raiz do CAS (mesmo volume do destino) e é movido para o diretório de shard antes do replace final, garantindo que origem e destino do rename atômico estejam no mesmo diretório — `os.replace` é então um rename local atômico, nunca um copy cross-dir.
- **Idempotência por conteúdo:** quando `path_for(hash)` já existe, o temporário é descartado e o blob imutável NÃO é reescrito (D-08).

## Deviations from Plan

None - plan executed exactly as written. As funções da interface mínima (`store`, `path_for`, `exists`, `read_bytes`, `open_blob`) foram implementadas conforme especificado; adicionada apenas a função auxiliar pública `cas_root()` (helper de raiz, não solicitado explicitamente mas alinhado ao guidance "raiz computada de data_dir" e usado pelos testes para verificar D-01) — não altera escopo nem comportamento.

## Threat Model Compliance
Todas as disposições `mitigate` do registro STRIDE do plano estão materializadas:
- **T-01-10 (Tampering — integridade do blob):** caminho derivado do SHA-256 do conteúdo; escrita via temporário + `os.replace`; sem API de update/delete (imutável). ✓
- **T-01-11 (DoS — arquivos grandes em memória):** hashing e cópia por streaming em chunks de 64KB. ✓
- **T-01-12 (Tampering — original na origem):** `store` COPIA (não move); origem aberta só em leitura; teste de byte-igualdade pós-store. ✓
- **T-01-14 (Repudiation — recuperabilidade/undo):** blobs mantidos para sempre, recuperáveis por hash; teste cobre recuperação após a origem ser removida. ✓
- **T-01-13 (Information Disclosure — blobs em repouso):** `accept` (herdado de T-01-03; criptografia em repouso é evolução) — sem ação nesta fase.

Nenhuma nova superfície de ameaça fora do `<threat_model>` do plano foi introduzida.

## Known Stubs
Nenhum stub. O módulo é funcional e completo para o escopo da fase; a integração com a ingestão (gravar o `content_hash` em `Document` e copiar para o CAS na entrada) é da Fase 2 (ING-06), que reusa este hash.

## User Setup Required
None — nenhuma configuração externa. O CAS usa apenas a stdlib e a pasta de dados já configurada (DATA_DIR / padrão `%ProgramData%`).

## Next Phase Readiness
- **Fase 2 (Ingestão/Fila):** `cas.store(src)` é o ponto de entrada para materializar a cópia imutável na ingestão; o hash retornado alimenta `Document.content_hash` (dedup ING-06) já modelado em 01-02.
- **Fase 6 (Automações/Reversibilidade):** `read_bytes`/`open_blob` por hash são a rede de segurança do undo — o original permanece recuperável mesmo após renomear/mover (D-08).
- **Windows (DIST-01):** `os.replace`/`pathlib` dão rename atômico portável; nenhuma infra adicional. Validação ponta-a-ponta em Windows real continua pendente para as fases com I/O de arquivos do cliente (Fase 2/6).

## Self-Check: PASSED

Both declared files exist on disk (`backend/app/storage/cas.py`, `backend/tests/test_cas.py`); task commit hash `9617579` present in git history; full suite 40 passed, ruff clean.

---
*Phase: 01-funda-o-de-estado-e-storage*
*Completed: 2026-06-15*
