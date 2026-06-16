---
phase: 02-ingest-o-e-fila-ass-ncrona
plan: 02
subsystem: infra
tags: [ingestion, pikepdf, pdf-split, file-stabilization, watchfiles, windows, config]

# Dependency graph
requires:
  - phase: 02-01
    provides: substrato de schema da Fase 2 (jobs, ingested_originals, watched_folders) que será consumido pelo worker que orquestra estas utilidades
  - phase: 01-03
    provides: estilo de utilidade FS pura (cas.store) replicado no estabilizador/splitter
provides:
  - "wait_stable: detecção de arquivo estável (quiescência size/mtime + lock-test Windows) antes de qualquer leitura de conteúdo"
  - "split_pdf: separação de PDF em ceil(M/N) blocos via pikepdf; 'não separar' (None/0) => 1 bloco"
  - "is_supported_ext / SUPPORTED_EXTENSIONS: allowlist de formatos de entrada PDF/JPG/JPEG/PNG (ING-04)"
  - "Settings.stabilization_window_seconds (D-04) + tunables globais da fila (poll/attempts/backoff)"
affects: [02-03 (worker/ingest_stage consome wait_stable + split_pdf + allowlist), 02-04 (watcher consome wait_stable)]

# Tech tracking
tech-stack:
  added: [pikepdf 10.8.0 (MPL-2.0) para split de PDF]
  patterns:
    - "Utilidades puras de ingestão (sem HTTP/DB) com testes próprios isolados — validar lógica difícil antes de costurar no worker"
    - "Exceção controlada (ValueError) em entrada não-confiável: PDF malformado re-levantado para o worker rotear a retry/FALHA, nunca derruba o processo"
    - "Default de config lido lazy via get_settings() quando o argumento é None — permite override por arg sem acoplar o módulo à config"

key-files:
  created:
    - backend/app/ingest/__init__.py
    - backend/app/ingest/stabilizer.py
    - backend/app/ingest/splitter.py
  modified:
    - backend/app/config.py
    - backend/tests/test_stabilizer.py
    - backend/tests/test_splitter.py
    - backend/tests/test_config.py

key-decisions:
  - "Janela de estabilização default 4.0s (intervalo ~3-5s da A2), configurável por env STABILIZATION_WINDOW_SECONDS"
  - "pikepdf (MPL-2.0) para split em vez de PyMuPDF (AGPL-3.0) — evita licença comercial num produto vendido"
  - "pages_per_block None ou 0 = 'não separar' (D-05 default) => 1 bloco com o PDF inteiro"
  - "PDF malformado re-levantado como ValueError com nome do arquivo (T-02-04), não PdfError cru"

patterns-established:
  - "Pacote app.ingest re-exporta as utilidades públicas (wait_stable, split_pdf, is_supported_ext, SUPPORTED_EXTENSIONS)"
  - "Fixtures de PDF geradas em runtime via pikepdf.Pdf.new().add_blank_page() — nenhum binário commitado em tests/"

requirements-completed: [ING-02, ING-04, ING-05]

# Metrics
duration: 3min
completed: 2026-06-16
---

# Phase 02 Plan 02: Utilidades de Ingestão (estabilizador + separador de PDF) Summary

**Estabilizador de arquivo por quiescência size/mtime + lock-test Windows e separador de PDF em blocos de N páginas via pikepdf, com config global de janela e allowlist de formatos — duas utilidades puras testadas isoladamente.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-06-16T00:56:46Z
- **Completed:** 2026-06-16T01:00:09Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- `wait_stable` (ING-02 / Pitfall 1 / T-02-03): só considera um arquivo estável após `(size, mtime_ns)` ficarem parados por toda a janela e o arquivo abrir sem lock; reinicia a contagem em qualquer mudança; retorna False se removido durante a espera.
- `split_pdf` (ING-05 / D-05/D-06/D-07): PDF de M páginas + regra N → `ceil(M/N)` blocos válidos; "não separar" (None/0) → 1 bloco; PDF malformado vira `ValueError` controlado (T-02-04).
- `is_supported_ext` / `SUPPORTED_EXTENSIONS` (ING-04): allowlist case-insensitive PDF/JPG/JPEG/PNG.
- `Settings.stabilization_window_seconds` (D-04, default 4.0s) + tunables globais da fila (`queue_poll_interval_seconds`, `queue_max_attempts`, `queue_backoff_base_seconds`, `queue_backoff_max_seconds`) que o Plano 03 consumirá.

## Task Commits

Each task was committed atomically (TDD: test → feat):

1. **Task 1 (RED): tests do estabilizador + config** - `10fb4eb` (test)
2. **Task 1 (GREEN): estabilizador + config de janela** - `39ad5a1` (feat)
3. **Task 2 (RED): tests do splitter + allowlist** - `5382235` (test)
4. **Task 2 (GREEN): splitter de PDF + allowlist** - `10d4d9b` (feat)

**Plan metadata:** _(este commit)_ (docs: complete plan)

## Files Created/Modified
- `backend/app/ingest/__init__.py` - Pacote de ingestão; re-exporta wait_stable/split_pdf/is_supported_ext/SUPPORTED_EXTENSIONS
- `backend/app/ingest/stabilizer.py` - `wait_stable` (quiescência size/mtime + lock-test Windows)
- `backend/app/ingest/splitter.py` - `split_pdf` (pikepdf), `is_supported_ext`, `SUPPORTED_EXTENSIONS`
- `backend/app/config.py` - Campos `stabilization_window_seconds` + tunables da fila
- `backend/tests/test_stabilizer.py` - 5 testes (estável/removido/remoção-mid/reinício/janela-da-config)
- `backend/tests/test_splitter.py` - 9 testes (1/bloco, 3/bloco ceil, no-split None/0, blocos válidos, malformado, allowlist)
- `backend/tests/test_config.py` - 3 testes novos (janela default ~3-5s, override por env, tunables da fila)

## Decisions Made
- Janela de estabilização default **4.0s** (centro do intervalo ~3-5s da A2), ajustável por instância via `STABILIZATION_WINDOW_SECONDS` sem deploy.
- **pikepdf (MPL-2.0)** para split — não PyMuPDF (AGPL-3.0), evitando implicação de licença comercial no produto vendido.
- PDF malformado re-levantado como **`ValueError`** com o nome do arquivo (contexto de diagnóstico) em vez do `pikepdf.PdfError` cru, dando ao worker do Plano 03 um tipo de exceção estável para rotear a retry/FALHA (T-02-04).
- `pages_per_block` **None ou 0** tratados igualmente como "não separar" (D-05 default).

## Deviations from Plan

None - plan executed exactly as written. (Todos os defaults, assinaturas e comportamentos seguem o PLAN/RESEARCH; o único ajuste de teste — asserir `ValueError` em vez de `Exception` cego — alinha o teste ao tipo controlado já especificado pelo plano para T-02-04 e satisfaz o lint, sem mudar comportamento.)

## Issues Encountered
- Ordenação de import no pacote: `app/ingest/__init__.py` re-exporta `splitter` (que só existe no fim do Task 2). Durante o Task 1 GREEN o `__init__` foi mantido sem o import de `splitter` para não quebrar o import do estabilizador; restaurado para re-exportar ambos no Task 2. Resolvido sem deviation.
- Lint `B017` (assert de `Exception` cego) no teste de PDF malformado → estreitado para `pytest.raises(ValueError)`, coerente com o re-raise controlado do splitter.

## User Setup Required
None - nenhuma configuração de serviço externo necessária. Os novos campos de Settings têm defaults sensatos; `STABILIZATION_WINDOW_SECONDS` e os tunables de fila são opcionais.

## Next Phase Readiness
- Pronto para o Plano 03 (worker/ingest_stage): `wait_stable` e `split_pdf` são utilidades puras prontas para serem despachadas via `asyncio.to_thread`; a fila (02-01) e os tunables de config já existem.
- Pronto para o Plano 04 (watcher): `wait_stable` e `is_supported_ext` são os ganchos que o watcher usará para filtrar/estabilizar candidatos.
- Sem blockers introduzidos. Janela de estabilização default (4s) deve ser confirmada com o usuário em ambiente real de rede lenta (A2), mas é ajustável por env.

## Self-Check: PASSED

---
*Phase: 02-ingest-o-e-fila-ass-ncrona*
*Completed: 2026-06-16*
