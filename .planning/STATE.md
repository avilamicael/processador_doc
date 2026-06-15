# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-15)

**Core value:** Transformar uma pilha de documentos heterogêneos (PDFs e imagens, de tipos variados) em arquivos classificados, nomeados e organizados corretamente de forma automática e confiável — sem o usuário perder arquivos nem confiar cegamente na IA.
**Current focus:** Phase 1 — Fundação de Estado e Storage

## Current Position

Phase: 1 of 8 (Fundação de Estado e Storage)
Plan: 0 of TBD in current phase
Status: Ready to plan
Last activity: 2026-06-15 — Roadmap created (8 phases, 38/38 requirements mapped)

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: — min
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**
- Last 5 plans: —
- Trend: —

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: Motor é GENÉRICO — extração por IA dirigida pelo template (EXT-02) é o núcleo e vem primeiro (Phase 3); parsing determinístico (EXT-05) é módulo opcional/plugável movido para depois (Phase 7).
- [Roadmap]: Windows é plataforma primária; modo padrão usa fila in-process (SQLite), sem broker externo (refletido nas Phases 1 e 2).
- [Roadmap]: Reversibilidade (dry-run + audit write-ahead + undo + anti-colisão) é definição de pronto da Phase 6, não extra posterior.
- [Roadmap]: Documentação e atualização segura entre versões são entregáveis de v1 (Phase 8).

### Pending Todos

None yet.

### Blockers/Concerns

[From research — a confirmar durante o planejamento das fases]

- Licença PyMuPDF (AGPL-3.0): resolver antes de extração de PDF (Phase 3); avaliar pypdfium2/pdfminer permissivos. (research/SUMMARY.md)
- Modelo de confiança: OpenAI não expõe score por campo; usar validação determinística pós-extração (Phase 5). (research/SUMMARY.md)
- Fila in-process SQLite sem lib consagrada: validar polling de tabela próprio (Phase 2). (research/SUMMARY.md)
- Parser de boleto Python: sem lib madura; portar lógica + fixtures reais (Phase 7). (research/SUMMARY.md)

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-06-15
Stopped at: Roadmap and STATE created; REQUIREMENTS traceability updated.
Resume file: None
