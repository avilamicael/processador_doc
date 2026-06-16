// Hooks TanStack Query para o CRUD de pastas monitoradas (D-02).
//
// A query lista as pastas; as mutations (criar/editar/remover) invalidam
// ['watched-folders'] para a lista refletir o estado persistido no backend —
// fonte de verdade é a API (T-02-13), sem otimismo que mascare falha.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createWatchedFolder,
  deleteWatchedFolder,
  getWatchedFolders,
  updateWatchedFolder,
} from '../lib/api'
import type { FolderCreate, FolderPatch } from '../types'

const FOLDERS_KEY = ['watched-folders'] as const

export function useWatchedFolders() {
  return useQuery({
    queryKey: FOLDERS_KEY,
    queryFn: getWatchedFolders,
  })
}

export function useCreateFolder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: FolderCreate) => createWatchedFolder(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: FOLDERS_KEY }),
  })
}

export function useUpdateFolder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: FolderPatch }) =>
      updateWatchedFolder(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: FOLDERS_KEY }),
  })
}

export function useDeleteFolder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => deleteWatchedFolder(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: FOLDERS_KEY }),
  })
}
