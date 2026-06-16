// Tipos do modelo de UI do DocWatch (Opção B).
// Fase 2 (GSD 02-05): os tipos de documento/pasta agora refletem a API REAL do
// backend (app/api/documents.py, app/api/watched_folders.py). Os tipos que ainda
// pertencem a telas mock de fases futuras (Template/Automation/Integration/Rule)
// permanecem como modelo de UI até serem fiados.

export type Page = 'documentos' | 'templates' | 'automacoes' | 'config'
export type ConfigTab = 'pastas' | 'regras' | 'leitura' | 'integracoes'

// Estado de domínio REAL do backend (app/models/enums.py DocState). Substitui a
// união mock 'encontrado'|'leitura'|'tratado'|'erro'.
export type DocState =
  | 'recebido'
  | 'processando'
  | 'em_revisao'
  | 'concluido'
  | 'quarentena'
  | 'falha'

// Filtro de status na tela Documentos (estados de domínio reais + 'todos').
export type StatusFilter = 'todos' | DocState

// Documento (BLOCO — D-06) exposto por GET /documents.
export interface Doc {
  id: number
  original_filename: string
  state: DocState
  last_completed_step: string | null
  source_folder_path: string | null
  created_at: string
  size?: number | null
}

// Resposta de GET /documents: lista + contagens por estado.
export interface DocumentList {
  items: Doc[]
  counts: Record<string, number>
  total: number
}

// Pasta monitorada exposta por GET /watched-folders (D-02).
export interface Folder {
  id: number
  path: string
  pages_per_block: number | null
  active: boolean
  created_at: string
  updated_at: string
}

// Body de criação de pasta (POST /watched-folders).
export interface FolderCreate {
  path: string
  pages_per_block: number | null
  active: boolean
}

// Body de edição parcial de pasta (PATCH /watched-folders/{id}).
export interface FolderPatch {
  path?: string
  pages_per_block?: number | null
  active?: boolean
}

// --- Tipos de UI ainda mock (telas de fases futuras; não fiados na Fase 2) ---

export interface Rule {
  id: number
  name: string
  param: string
  desc: string
}

export interface Integration {
  id: number
  name: string
  cat: string
  mono: string
  on: boolean
}

export interface Template {
  name: string
  type: string
  fields: string[]
  docs: string
  rule: string
}

export interface Automation {
  id: number
  name: string
  trigger: string
  cond: string
  action: string
  runs: string
}
