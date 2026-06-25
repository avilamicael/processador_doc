// Hooks TanStack Query para o CRUD de templates (TPL-01).
//
// Espelha 1-para-1 useWatchedFolders.ts: a query lista os templates; as mutations
// (criar/editar/remover) invalidam ['templates'] para a lista refletir o estado
// persistido no backend — fonte de verdade é a API, sem otimismo que mascare falha.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createTemplate,
  deleteTemplate,
  getTemplates,
  previewSignals,
  updateTemplate,
} from '../lib/api'
import type { TemplateCreate, TemplatePatch } from '../types'

const TEMPLATES_KEY = ['templates'] as const

export function useTemplates() {
  return useQuery({
    queryKey: TEMPLATES_KEY,
    queryFn: getTemplates,
  })
}

export function useCreateTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: TemplateCreate) => createTemplate(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: TEMPLATES_KEY }),
  })
}

export function useUpdateTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: TemplatePatch }) =>
      updateTemplate(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: TEMPLATES_KEY }),
  })
}

export function useDeleteTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => deleteTemplate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: TEMPLATES_KEY }),
  })
}

// "Testar sinais" (D-07): leitura sob demanda, sem invalidação — não muta o servidor.
export function usePreviewSignals() {
  return useMutation({
    mutationFn: ({ templateId, file }: { templateId: number; file: File }) =>
      previewSignals(templateId, file),
  })
}
