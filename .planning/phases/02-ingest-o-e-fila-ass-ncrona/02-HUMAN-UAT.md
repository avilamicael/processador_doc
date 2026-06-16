---
status: partial
phase: 02-ingest-o-e-fila-ass-ncrona
source: [02-VERIFICATION.md]
started: 2026-06-16
updated: 2026-06-16
---

## Current Test

[aprovado pelo usuário no checkpoint do 02-05 — caminho principal validado; sub-cenários abaixo opcionais]

## Tests

### 1. Verificação visual end-to-end (PLAN 02-05 Task 3)
expected: |
  1. Subir backend + frontend. Em Configurações → Pastas monitoradas, adicionar pasta real → aparece na lista.
  2. Copiar PDF multi-página para a pasta. Editar para 'Separar a cada 1 página' e copiar outro PDF.
  3. Tela Documentos: documentos entram na fila e mudam de estado por polling (Na fila → Processando → Aguardando extração) SEM flicker. Nenhum aparece 'Tratado'/'Concluído' (verde).
  4. PDF separado vira N documentos independentes (1 por página).
  5. Copiar o MESMO PDF novamente: nenhum duplicado na lista; contador 'N duplicados ignorados' (rodapé) incrementa.
  6. Remover pasta: diálogo destrutivo aparece; documentos já ingeridos PERMANECEM.
  7. Parar backend: erro com 'Tentar novamente' dentro do card; reiniciar: recuperação.
result: passed (parcial) — usuário validou que arquivos aparecem nos Documentos e optou por seguir após revisar os 7 passos (2026-06-16). Sub-cenários 5 (dedup visível), 6 (remoção de pasta) e 7 (erro/recovery) não testados exaustivamente; reexecutar via /gsd:verify-work 02 se desejar cobertura completa.

## Summary

total: 1
passed: 1
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

Nenhum gap bloqueante. Itens de dívida técnica (não-bloqueantes) registrados em 02-REVIEW.md: WR-02 (requeue_running gasta tentativa em crash de infra), WR-03 (symlink não rejeitado no watcher, só na API), WR-06 (split_pdf só captura PdfError).
