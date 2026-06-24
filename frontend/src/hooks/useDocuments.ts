// Hooks TanStack Query para a tela Documentos (polling sem flicker).
//
// UI-SPEC: polling 3-5s enquanto a aba está focada (refetchInterval: 4000),
// pausa quando a aba está oculta (refetchIntervalInBackground: false), e mantém
// os dados anteriores durante o refetch (placeholderData: keepPreviousData) para
// a tabela NUNCA piscar/colapsar num spinner em refetch de background.

import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getDocuments, getDuplicatesCount, postDeleteDocuments, postRescan } from '../lib/api'

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
