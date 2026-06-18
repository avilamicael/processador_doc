// Hooks TanStack Query para o MODELO FINAL de automações (Fase 6, D-23..D-26,
// TPL-02/AUT-03/AUT-05).
//
// Espelha useTemplates.ts: a query lista as automações (com conditions[]/actions[]
// aninhados); as mutations de CRUD invalidam ['automations']. As AÇÕES
// (dry-run/apply/undo) invalidam também ['documents'] e ['attention'] porque mudam
// o estado dos documentos (auto-aplicado → CONCLUIDO, bloqueado → EM_REVISAO, undo
// reabre PROCESSANDO). Fonte de verdade é a API — sem otimismo que mascare falha de
// operação.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createAutomation,
  deleteAutomation,
  getAutomations,
  postApply,
  postDryRun,
  postUndo,
  updateAutomation,
} from '../lib/api'
import type { AutomationCreate, AutomationPatch } from '../types'

const AUTOMATIONS_KEY = ['automations'] as const

export function useAutomations() {
  return useQuery({
    queryKey: AUTOMATIONS_KEY,
    queryFn: getAutomations,
  })
}

export function useCreateAutomation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: AutomationCreate) => createAutomation(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: AUTOMATIONS_KEY }),
  })
}

export function useUpdateAutomation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: AutomationPatch }) =>
      updateAutomation(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: AUTOMATIONS_KEY }),
  })
}

export function useDeleteAutomation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => deleteAutomation(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: AUTOMATIONS_KEY }),
  })
}

// AUT-03 — dry-run NÃO altera estado; não precisa invalidar nada além do próprio cache.
export function useDryRun() {
  return useMutation({
    mutationFn: (documentIds: number[] = []) => postDryRun(documentIds),
  })
}

// Invalida documents/attention porque aplicar muda o estado do documento.
function invalidateAfterAction(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: AUTOMATIONS_KEY })
  qc.invalidateQueries({ queryKey: ['documents'] })
  qc.invalidateQueries({ queryKey: ['attention'] })
}

export function useApply() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (documentIds: number[]) => postApply(documentIds),
    onSuccess: () => invalidateAfterAction(qc),
  })
}

export function useUndo() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { document_id?: number; run_id?: string }) => postUndo(body),
    onSuccess: () => invalidateAfterAction(qc),
  })
}
