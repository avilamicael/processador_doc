// Hook TanStack Query para o status real do watcher (Sidebar — quick 260624-far).
//
// Espelha o padrão de useDocuments: polling enquanto a aba está focada
// (refetchInterval), pausa quando oculta (refetchIntervalInBackground: false) e
// mantém os dados anteriores no refetch (placeholderData: keepPreviousData) para
// a Sidebar não piscar. Intervalo um pouco mais folgado (8s) — status muda devagar.

import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { getWatcherStatus } from '../lib/api'

const POLL_INTERVAL_MS = 8000

export function useWatcherStatus() {
  return useQuery({
    queryKey: ['watcher-status'],
    queryFn: getWatcherStatus,
    refetchInterval: POLL_INTERVAL_MS,
    refetchIntervalInBackground: false,
    placeholderData: keepPreviousData,
  })
}
