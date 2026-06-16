"""Pacote de ingestão — utilidades puras de filesystem/PDF da Fase 2.

Expõe as utilidades isoláveis (sem HTTP, sem DB) usadas pelo worker/ingest_stage
(Plano 03) e pelo watcher (Plano 04):
- `stabilizer.wait_stable`: decide quando um arquivo da pasta monitorada parou de
  ser escrito (quiescência size/mtime + lock-test Windows — Pitfall 1 / ING-02).

Importações concretas de submódulos são feitas pelos consumidores (ex.:
`from app.ingest.stabilizer import wait_stable`) para manter o pacote leve.
"""
