// Hooks TanStack Query para a tela Documentos (polling sem flicker).
//
// UI-SPEC: polling 3-5s enquanto a aba está focada (refetchInterval: 4000),
// pausa quando a aba está oculta (refetchIntervalInBackground: false), e mantém
// os dados anteriores durante o refetch (placeholderData: keepPreviousData) para
// a tabela NUNCA piscar/colapsar num spinner em refetch de background.

import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getDocuments, getDuplicatesCount, postApprove, postDeleteDocuments, postRescan, postUndo } from '../lib/api'

const POLL_INTERVAL_MS = 4000

export function useDocuments() {
  return useQuery({
    queryKey: ['documents'],
    queryFn: getDocuments,
    refetchInterval: POLL_INTERVAL_MS,
    refetchIntervalInBackground: false,
    placeholderData: keepPreviousData,
  })
}

export function useDuplicatesCount() {
  return useQuery({
    queryKey: ['duplicates-count'],
    queryFn: getDuplicatesCount,
    refetchInterval: POLL_INTERVAL_MS,
    refetchIntervalInBackground: false,
    placeholderData: keepPreviousData,
  })
}

export function useRescan() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: postRescan,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['documents'] })
      qc.invalidateQueries({ queryKey: ['duplicates-count'] })
    },
  })
}

// D-11/D-12: aprovar um documento direto da lista (CTA na linha do doc "pronto").
// Reusa POST /documents/{id}/approve (guard de pré-condição de estado vive no
// backend — a UI só atalha, não burla autorização nem auto-conclui nada).
// Molde: useRescan; invalida a lista e o detalhe do doc no sucesso.
export function useApproveDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => postApprove(id),
    onSuccess: (_d, id) => {
      qc.invalidateQueries({ queryKey: ['documents'] })
      qc.invalidateQueries({ queryKey: ['document-detail', id] })
    },
  })
}

// Item 1/D-01: reverter UM documento à origem (botão "Reverter para a origem"
// no detalhe). Reusa POST /automations/undo por document_id — o backend restaura
// do CAS com seu próprio guard (a UI envia só o document_id do doc aberto).
// Molde: useRescan; invalida a lista, o detalhe e a auditoria do doc no sucesso
// (o doc reabre CONCLUIDO→PROCESSANDO).
export function useUndoDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => postUndo({ document_id: id }),
    onSuccess: (_d, id) => {
      qc.invalidateQueries({ queryKey: ['documents'] })
      qc.invalidateQueries({ queryKey: ['document-detail', id] })
      qc.invalidateQueries({ queryKey: ['document-audit', id] })
    },
  })
}

// Remoção em lote de documentos (só o registro — nunca o arquivo físico).
// Invalida a lista e o contador de duplicados (igual ao useRescan).
export function useDeleteDocuments() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ids: number[]) => postDeleteDocuments(ids),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['documents'] })
      qc.invalidateQueries({ queryKey: ['duplicates-count'] })
    },
  })
}
