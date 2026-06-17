// Cliente fetch tipado para a API do backend (Fase 2).
//
// URL base RELATIVA: em produção o FastAPI serve o frontend buildado
// (single-origin, sem CORS — ver vite.config.ts). Em dev o Vite faz proxy de
// `/documents`, `/watched-folders`, `/rescan` para o backend (ver vite.config.ts
// server.proxy), então as mesmas URLs relativas funcionam nos dois modos.
//
// Cada função checa `res.ok` e LANÇA em erro — o TanStack Query trata o erro
// (estado de erro na UI, retry). Nomes/paths vindos do backend são renderizados
// como texto puro pelo React (T-02-11): este módulo não interpreta HTML.

import type {
  AttentionList,
  Doc,
  DocumentDetail,
  DocumentList,
  Folder,
  FolderCreate,
  FolderPatch,
  ReviewThreshold,
  Template,
  TemplateCreate,
  TemplatePatch,
} from '../types'

class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = (await res.json()) as { detail?: string }
      if (body?.detail) detail = body.detail
    } catch {
      // resposta sem corpo JSON — mantém o status text
    }
    throw new ApiError(res.status, detail)
  }
  // 204 No Content (ex.: DELETE) não tem corpo.
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

// --- Documentos ---

export function getDocuments(): Promise<DocumentList> {
  return request<DocumentList>('/documents')
}

export function getDuplicatesCount(): Promise<{ count: number }> {
  return request<{ count: number }>('/documents/duplicates-count')
}

// Detalhe de classificação (S4, somente leitura — TPL-03/04).
export function getDocumentDetail(id: number): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/documents/${id}`)
}

export function postRescan(): Promise<{ enqueued: number }> {
  return request<{ enqueued: number }>('/rescan', { method: 'POST' })
}

// --- Triagem "Precisam de atenção" (Fase 5 — REV-03/04/05) ---

// Os 3 baldes (FALHA/QUARENTENA/EM_REVISAO) num payload só (endpoint dedicado, Open Q3).
export function getAttention(): Promise<AttentionList> {
  return request<AttentionList>('/documents/attention')
}

// FALHA → "Tentar de novo" (FALHA→PROCESSANDO; reenfileira o step adequado).
export function postRetry(id: number): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/documents/${id}/retry`, { method: 'POST' })
}

// QUARENTENA → "Reclassificar" com template forçado (QUARENTENA→PROCESSANDO, D-09).
export function postReclassify(id: number, templateId: number): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/documents/${id}/reclassify`, {
    method: 'POST',
    body: JSON.stringify({ template_id: templateId }),
  })
}

// EM_REVISAO → corrigir um campo (revalida SEM IA, D-08). `field_name` codificado na URL.
export function patchField(
  id: number,
  fieldName: string,
  rawValue: string | null,
): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/documents/${id}/fields/${encodeURIComponent(fieldName)}`, {
    method: 'PATCH',
    body: JSON.stringify({ raw_value: rawValue }),
  })
}

// EM_REVISAO → "Aprovar documento" (EM_REVISAO→CONCLUIDO; guard D-07 no backend).
export function postApprove(id: number): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/documents/${id}/approve`, { method: 'POST' })
}

// --- Limiar global de confiança (S6 — Config; D-03) ---

export function getReviewThreshold(): Promise<ReviewThreshold> {
  return request<ReviewThreshold>('/config/review-threshold')
}

export function putReviewThreshold(value: number): Promise<ReviewThreshold> {
  return request<ReviewThreshold>('/config/review-threshold', {
    method: 'PUT',
    body: JSON.stringify({ threshold: value }),
  })
}

// --- Pastas monitoradas (CRUD) ---

export function getWatchedFolders(): Promise<Folder[]> {
  return request<Folder[]>('/watched-folders')
}

export function createWatchedFolder(body: FolderCreate): Promise<Folder> {
  return request<Folder>('/watched-folders', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function updateWatchedFolder(id: number, body: FolderPatch): Promise<Folder> {
  return request<Folder>(`/watched-folders/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function deleteWatchedFolder(id: number): Promise<void> {
  return request<void>(`/watched-folders/${id}`, { method: 'DELETE' })
}

// --- Templates (CRUD schema-first — TPL-01) ---

export function getTemplates(): Promise<Template[]> {
  return request<Template[]>('/templates')
}

export function createTemplate(body: TemplateCreate): Promise<Template> {
  return request<Template>('/templates', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function updateTemplate(id: number, body: TemplatePatch): Promise<Template> {
  return request<Template>(`/templates/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function deleteTemplate(id: number): Promise<void> {
  return request<void>(`/templates/${id}`, { method: 'DELETE' })
}

export { ApiError }
export type { Doc }
