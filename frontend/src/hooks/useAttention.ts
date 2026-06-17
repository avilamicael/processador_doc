// Hooks TanStack Query da visão "Precisam de atenção" (Fase 5 — REV-03/04/05).
//
// Espelha useDocuments/useRescan: a query de polling NUNCA pisca
// (placeholderData: keepPreviousData), pausa em background
// (refetchIntervalInBackground: false) e cada mutation invalida ['attention']
// (e ['documents'], pois o item sai da lista geral também) em onSuccess. Fonte de
// verdade = API, sem otimismo que mascare falha.

import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getAttention,
  getReviewThreshold,
  patchField,
  postApprove,
  postReclassify,
  postRetry,
  putReviewThreshold,
} from '../lib/api'

const ATTENTION_KEY = ['attention'] as const
const DOCUMENTS_KEY = ['documents'] as const
const REVIEW_THRESHOLD_KEY = ['review-threshold'] as const
const POLL_INTERVAL_MS = 4000

// Lista os 3 baldes por polling (padrão useDocuments).
export function useAttentionDocuments() {
  return useQuery({
    queryKey: ATTENTION_KEY,
    queryFn: getAttention,
    refetchInterval: POLL_INTERVAL_MS,
    refetchIntervalInBackground: false,
    placeholderData: keepPreviousData,
  })
}

// Invalida ['attention'] + ['documents'] após uma ação de triagem bem-sucedida.
function useInvalidateAttention() {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: ATTENTION_KEY })
    qc.invalidateQueries({ queryKey: DOCUMENTS_KEY })
  }
}

// FALHA → "Tentar de novo".
export function useRetryDocument() {
  const invalidate = useInvalidateAttention()
  return useMutation({
    mutationFn: (id: number) => postRetry(id),
    onSuccess: invalidate,
  })
}

// QUARENTENA → "Reclassificar" com template forçado.
export function useReclassifyDocument() {
  const invalidate = useInvalidateAttention()
  return useMutation({
    mutationFn: ({ id, templateId }: { id: number; templateId: number }) =>
      postReclassify(id, templateId),
    onSuccess: invalidate,
  })
}

// EM_REVISAO → corrigir um campo (revalida sem IA, D-08).
export function usePatchField() {
  const invalidate = useInvalidateAttention()
  return useMutation({
    mutationFn: ({
      id,
      fieldName,
      rawValue,
    }: {
      id: number
      fieldName: string
      rawValue: string | null
    }) => patchField(id, fieldName, rawValue),
    onSuccess: invalidate,
  })
}

// EM_REVISAO → "Aprovar documento".
export function useApproveDocument() {
  const invalidate = useInvalidateAttention()
  return useMutation({
    mutationFn: (id: number) => postApprove(id),
    onSuccess: invalidate,
  })
}

// --- Limiar global de confiança (S6 — Config; D-03) ---

export function useReviewThreshold() {
  return useQuery({
    queryKey: REVIEW_THRESHOLD_KEY,
    queryFn: getReviewThreshold,
  })
}

export function useSaveReviewThreshold() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (value: number) => putReviewThreshold(value),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: REVIEW_THRESHOLD_KEY })
    },
  })
}
