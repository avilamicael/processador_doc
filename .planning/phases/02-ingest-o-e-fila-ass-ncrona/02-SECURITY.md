---
phase: 02
slug: ingest-o-e-fila-ass-ncrona
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-16
---

# Phase 02 — Security

> Contrato de segurança da fase: registro de ameaças, riscos aceitos e trilha de auditoria.
> Ingestão e Fila Assíncrona. Auditado por gsd-security-auditor (block_on: high) — nenhum BLOCKER.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| UI/HTTP → API de pastas | path da pasta é entrada não-confiável (path traversal / leitura arbitrária) | caminho de filesystem |
| Pasta do cliente → estabilizador/watcher | arquivos do FS local; só PDF/JPG/PNG entram no pipeline | conteúdo de documento (sensível) |
| PDF do cliente → splitter | PDF malformado/malicioso pode travar o parser (DoS) | bytes de PDF |
| Job payload → worker | payload carrega source_path; deve referir-se a pasta monitorada conhecida | caminho + metadados |
| Worker → DB (single-writer) | claim/escritas concorrentes; corrida de dois consumidores | estado da fila |
| Crash/restart → fila | jobs em running precisam resumir sem duplicar trabalho/cobrança | jobs/originais/blocos |
| Alembic migration → DB | DDL autogerado pode divergir do modelo; revisão manual (D-10) | schema |
| Dependency install → venv | pacotes de terceiros (watchfiles, pikepdf, react-query) entram no runtime | código de terceiros |
| API → UI | dados do backend renderizados; original_filename pode conter chars de controle | metadados de documento |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-02-01 | Tampering | Migração 0002 corrompe schema / perde trigger updated_at | mitigate | Trigger recriado em upgrade/downgrade (`0002_ingestion.py:105-107,139-141`); round-trip up/down/up + trigger via SQL cru (`test_migrations.py`) | closed |
| T-02-02 | Tampering | Modelo não registrado → tabela ausente no schema versionado | mitigate | 3 modelos em imports+`__all__` (`models/__init__.py`); `test_migrations` asserta subset | closed |
| T-02-03 | Tampering | Hash/split sobre arquivo parcialmente escrito quebra dedup | mitigate | `wait_stable` quiescência (size,mtime) + lock-test antes de ler (`stabilizer.py:55-75`), chamado no watcher antes de hash/store | closed |
| T-02-04 | Denial of Service | PDF malformado trava o splitter | mitigate | split em try/except → `ValueError` controlado (`splitter.py:57-73`); worker `except Exception` → retry/FALHA (`worker.py:123-137`), processo nunca trava. Residual WR-06 (ver dívidas) | closed |
| T-02-05 | Denial of Service | PDF com milhares de páginas → explosão de blocos | accept | split via `asyncio.to_thread`; `block_count` observável; limite hard deferido. Ver Accepted Risks AR-01 | closed |
| T-02-06 | Tampering / Elevation | source_path aponta fora das pastas monitoradas | mitigate | payload gerado internamente (watcher/rescan); allowlist de extensão `is_supported_ext` no watcher e ingest_stage | closed |
| T-02-07 | Denial of Service / Repudiation | retry storm em falha transitória | mitigate | backoff exponencial+jitter + dead-letter→FALHA após max_attempts (`repo.py:143-152`) | closed |
| T-02-08 | Tampering | cobrança/trabalho duplicado após crash | mitigate | requeue_running no startup + UNIQUE(original_hash,step) + dedup gate + content_hash único + ingestão atômica em commit único (`ingest_stage.py:177`, fix CR-02) | closed |
| T-02-09 | Denial of Service | split de PDF grande bloqueia o event loop | mitigate | `process_ingest` despachado via `asyncio.to_thread` (`worker.py:117-122`) | closed |
| T-02-10 | Elevation / InfoDisclosure | path traversal no caminho da pasta | mitigate (escopo documentado) | `_normalize_path` rejeita vazio/symlink/não-diretório + `resolve()`; docstring honesto (CR-01 resolvido, `watched_folders.py:43-81`). Confinamento de raiz fora de escopo v1 → ver Accepted Risks AR-03 | closed |
| T-02-11 | InfoDisclosure / XSS | original_filename/path renderizado na UI | mitigate | CAS por hash; React escapa por padrão; zero `dangerouslySetInnerHTML` em `src/` | closed |
| T-02-12 | Denial of Service | múltiplos workers uvicorn duplicam watcher/worker | mitigate | watcher+worker como Task única por processo (`main.py:57-59`); `--workers 1` documentado/exigido | closed |
| T-02-13 | Spoofing (UX) | UI exibe estado falso/otimista que diverge do backend | mitigate | fonte de verdade = API por polling; mutations invalidam queries (`useDocuments.ts`, `useWatchedFolders.ts`) | closed |
| T-02-SC | Tampering | supply chain (watchfiles/pikepdf/@tanstack/react-query) | accept | versões pinadas + lockfiles (`uv.lock`, `package-lock.json`); aprovados no Package Legitimacy Audit. Ver Accepted Risks AR-02 | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01 | T-02-05 | Sem limite hard de páginas/blocos no v1; mitigado por execução off-thread (`to_thread`) + observabilidade de `block_count`. Limite explícito deferido para evolução. | usuário (via secure-phase) | 2026-06-16 |
| AR-02 | T-02-SC | Dependências aprovadas em audit, pinadas e com lockfiles; aceito sem SCA contínuo no v1. | usuário (via secure-phase) | 2026-06-16 |
| AR-03 | T-02-10 (residual) | Confinamento de raiz da pasta monitorada fora de escopo no v1 single-tenant local (decisão de produto). Endurecimento básico (rejeição de symlink/arquivo/vazio) presente; allowlist de raízes fica para eventual modo servidor/multiusuário. Dívida relacionada não-bloqueante: WR-03 (watcher resolve symlink interno). | usuário (via secure-phase) | 2026-06-16 |

*Accepted risks do not resurface in future audit runs.*

---

## Non-Blocking Quality Debt

- **WR-06** (relativo a T-02-04): `split_pdf` só captura `pikepdf.PdfError`; `OSError`/`FileNotFoundError` escapam crus mas são contidos pelo catch-all do worker (sem crash). Recomendado ampliar para `(pikepdf.PdfError, OSError)` e tratar arquivo removido como no-op em vez de FALHA permanente. Não compromete a mitigação declarada.
- **WR-03** (relativo a T-02-10): watcher segue symlink interno e pode ler alvo fora da pasta monitorada (rejeição de symlink hoje só na API de cadastro). Não-bloqueante no modelo single-tenant local.

Registrado em detalhe em `02-REVIEW.md`.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-16 | 14 | 14 | 0 | gsd-security-auditor (opus) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-16
