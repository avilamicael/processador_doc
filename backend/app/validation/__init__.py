"""Validação determinística reutilizável (Fase 4) — coração de EXT-04.

Pacote PURO (sem DB, sem IA, sem HTTP), espelhando o estilo módulo-função de
`extraction/` (sem classe). Implementa:
- `doc_ids`: Módulo 11 CNPJ/CPF PRÓPRIO (dep externa de DV PROIBIDA — CLAUDE.md
  Decisão Crítica 3) + normalização para dígitos;
- `dates`: parser pt-BR `dayfirst=True` → ISO (Pitfall 3 — defaults en-US trocam
  dia↔mês);
- `money`: parser pt-BR → `Decimal` (NUNCA float — T-04-05);
- `fields`: orquestrador `validate_field` (despacho por tipo, marca válido/inválido
  sem bloquear D-10, preserva bruto + normalizado D-11, regex segura D-09/V5).

Consumido pelo classify_stage (Plan 05) e reutilizável pela Fase 7.
"""
