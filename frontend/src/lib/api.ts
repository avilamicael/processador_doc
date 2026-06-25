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
  AiFallback,
  ApplyResult,
  AttentionList,
  Automation,
  AutomationCreate,
  AutomationPatch,
  Doc,
  DocumentAudit,
  DocumentDetail,
  DocumentList,
  DryRunResult,
  Folder,
  FolderCreate,
  FolderPatch,
  PreviewSignalsResult,
  ReprocessBatchResult,
  ReviewThreshold,
  Template,
  TemplateCreate,
  TemplatePatch,
  UndoResult,
  WatcherStatus,
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

// Auditoria de um documento (origem→destino/status/run_id — item 1, D-02).
// Read-only; alimenta a UI de "Reverter para a origem" no detalhe.
export function getDocumentAudit(id: number): Promise<DocumentAudit> {
  return request<DocumentAudit>(`/documents/${id}/audit`)
}

// Após D-04, o /rescan também conta quantas duplicatas-de-conteúdo foram puladas
// na varredura (`skipped_duplicates`) — base do toast pós-"Forçar varredura".
export function postRescan(): Promise<{ enqueued: number; skipped_duplicates: number }> {
  return request<{ enqueued: number; skipped_duplicates: number }>('/rescan', { method: 'POST' })
}

// Remoção em LOTE — remove SÓ o registro do app (Document + cascata + órfãos);
// NUNCA toca no arquivo físico do cliente (constraint forte; ver documents.py).
export function postDeleteDocuments(ids: number[]): Promise<{ deleted: number }> {
  return request<{ deleted: number }>('/documents/delete', {
    method: 'POST',
    body: JSON.stringify({ ids }),
  })
}

// Status real do watcher (Sidebar — quick 260624-far).
export function getWatcherStatus(): Promise<WatcherStatus> {
  return request<WatcherStatus>('/watcher/status')
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

// QUARENTENA/EM_REVISAO → "Reprocessar" (sem template forçado — re-roda matcher→IA→filler
// com os templates ATUAIS, D-10). Espelha postReclassify mas sem template_id. O backend
// guarda o estado elegível (409 fora de QUARENTENA/EM_REVISAO, Plano 03).
export function postReprocess(id: number): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/documents/${id}/reprocess`, { method: 'POST' })
}

// QUARENTENA/EM_REVISAO → "Reprocessar todos" do balde (lote por bucket, D-12).
// Retorna quantos documentos foram re-enfileirados.
export function postReprocessBatch(
  bucket: 'quarentena' | 'em_revisao',
): Promise<ReprocessBatchResult> {
  return request<ReprocessBatchResult>('/documents/reprocess', {
    method: 'POST',
    body: JSON.stringify({ bucket }),
  })
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

// --- IA-fallback opt-in (S — Config; D-05). Default OFF refletido pelo GET. ---

export function getAiFallback(): Promise<AiFallback> {
  return request<AiFallback>('/config/ai-fallback')
}

export function putAiFallback(enabled: boolean): Promise<AiFallback> {
  return request<AiFallback>('/config/ai-fallback', {
    method: 'PUT',
    body: JSON.stringify({ enabled }),
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

// "Testar sinais" (D-07): envia um PDF de teste em base64 no body JSON (SEM multipart,
// SEM alterar o Content-Type) e recebe o relatório por-grupo/condição. A leitura do
// arquivo usa APIs nativas do browser (FileReader/btoa) — nenhum pacote npm novo.
// O backend valida tudo (teto de bytes, magic bytes — Plano 02); a UI só envia.
async function fileToBase64(file: File): Promise<string> {
  const buffer = await file.arrayBuffer()
  const bytes = new Uint8Array(buffer)
  // Constrói a string binária em blocos para não estourar o limite de argumentos
  // de String.fromCharCode com arquivos grandes, depois codifica em base64.
  let binary = ''
  const CHUNK = 0x8000
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode(...bytes.subarray(i, i + CHUNK))
  }
  return btoa(binary)
}

export async function previewSignals(
  templateId: number,
  file: File,
): Promise<PreviewSignalsResult> {
  const pdf_base64 = await fileToBase64(file)
  return request<PreviewSignalsResult>('/templates/preview-signals', {
    method: 'POST',
    body: JSON.stringify({ template_id: templateId, pdf_base64 }),
  })
}

// --- Automações: MODELO FINAL (CRUD de N automações nomeadas com conditions[]/  ---
// --- actions[] + dry-run/apply/undo — Fase 6, D-23..D-26, TPL-02/AUT-03/AUT-05) ---

export function getAutomations(): Promise<Automation[]> {
  return request<Automation[]>('/automations')
}

export function getAutomation(id: number): Promise<Automation> {
  return request<Automation>(`/automations/${id}`)
}

export function createAutomation(body: AutomationCreate): Promise<Automation> {
  return request<Automation>('/automations', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function updateAutomation(id: number, body: AutomationPatch): Promise<Automation> {
  return request<Automation>(`/automations/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function deleteAutomation(id: number): Promise<void> {
  return request<void>(`/automations/${id}`, { method: 'DELETE' })
}

// AUT-03 — preview origem→destino SEM tocar o disco. `documentIds` vazio = todos
// os documentos prontos (PROCESSANDO + classificado).
export function postDryRun(documentIds: number[] = []): Promise<DryRunResult> {
  return request<DryRunResult>('/automations/dry-run', {
    method: 'POST',
    body: JSON.stringify({ document_ids: documentIds }),
  })
}

// D-03 — aplica por-doc OU por-lote; retorna o run_id (base do undo por-run).
export function postApply(documentIds: number[]): Promise<ApplyResult> {
  return request<ApplyResult>('/automations/apply', {
    method: 'POST',
    body: JSON.stringify({ document_ids: documentIds }),
  })
}

// AUT-05 — desfaz por-doc (document_id) OU por-run (run_id). Reabre CONCLUIDO→PROCESSANDO.
export function postUndo(body: { document_id?: number; run_id?: string }): Promise<UndoResult> {
  return request<UndoResult>('/automations/undo', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export { ApiError }
export type { Doc }
