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

// --- Templates (forma REAL da API /templates — Fase 4, TPL-01) ---

// Tipos de campo do construtor (D-08): os 6 valores aceitos pelo select de S2.
export type FieldType = 'texto' | 'numero' | 'data' | 'moeda' | 'cpf_cnpj' | 'booleano'

// Campo a extrair de um template (TemplateFieldOut do backend).
export interface TemplateField {
  id: number
  name: string
  field_type: FieldType
  required: boolean
  regex: string | null
  hint: string | null
}

// Template exposto por GET /templates (TemplateOut do backend).
export interface Template {
  id: number
  name: string
  doc_type: string | null
  signals: string[]
  fields: TemplateField[]
  created_at: string
  updated_at: string
}

// Body de criação de campo no POST/PATCH (TemplateFieldIn — sem id, server-gerado).
export interface TemplateFieldCreate {
  name: string
  field_type: FieldType
  required: boolean
  regex: string | null
  hint: string | null
}

// Body de criação de template (POST /templates — TemplateIn).
export interface TemplateCreate {
  name: string
  doc_type: string | null
  signals: string[]
  fields: TemplateFieldCreate[]
}

// Body de edição parcial (PATCH /templates/{id} — TemplatePatch).
// `fields` informado SUBSTITUI a coleção inteira; omitido preserva os campos atuais.
export interface TemplatePatch {
  name?: string
  doc_type?: string | null
  signals?: string[]
  fields?: TemplateFieldCreate[]
}

// --- Detalhe de classificação do documento (S4, somente leitura — TPL-03/04) ---

// Campo preenchido pela classificação (ClassificationFieldOut do backend).
export interface ClassificationField {
  field_name: string
  raw_value: string | null
  normalized_value: string | null
  valid: boolean
  invalid_reason: string | null
}

// Bloco de classificação (template_id/template_name null = quarentena, D-03).
export interface Classification {
  template_id: number | null
  template_name: string | null
  confidence: number | null
  fields: ClassificationField[]
}

// Detalhe de um documento (GET /documents/{id} — DocumentDetailOut).
// `classification` é null quando o doc ainda não foi classificado.
export interface DocumentDetail {
  id: number
  original_filename: string
  state: DocState
  last_completed_step: string | null
  source_folder_path: string | null
  created_at: string
  classification: Classification | null
}

export interface Automation {
  id: number
  name: string
  trigger: string
  cond: string
  action: string
  runs: string
}
