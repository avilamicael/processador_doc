// Tipos do modelo de UI do DocWatch (Opção B).
// Fase 2 (GSD 02-05): os tipos de documento/pasta agora refletem a API REAL do
// backend (app/api/documents.py, app/api/watched_folders.py). Os tipos que ainda
// pertencem a telas mock de fases futuras (Integration/Rule)
// permanecem como modelo de UI até serem fiados.

export type Page = 'documentos' | 'atencao' | 'templates' | 'automacoes' | 'dryrun' | 'config'
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
  // D-08: campo corrigido manualmente pelo operador (não veio da IA/documento).
  manually_corrected: boolean
}

// Bloco de classificação (template_id/template_name null = quarentena, D-03).
export interface Classification {
  template_id: number | null
  template_name: string | null
  confidence: number | null
  // D-02: score 0.0–1.0 de qualidade de extração (a UI multiplica por 100).
  // `null` em quarentena (sem template = sem obrigatórios).
  confidence_score: number | null
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

// --- Automações: MODELO FINAL (forma REAL da API /automations — Fase 6,        ---
// --- D-23..D-26, TPL-02/AUT-01..AUT-06). VÁRIAS automações nomeadas; cada uma = ---
// --- CONDIÇÕES (quando rodar, combinadas por E) → AÇÕES (o que fazer: rename/move). ---

// Dimensão comparada por uma condição (D-24; V5: conjunto fechado no backend).
export type ConditionField =
  | 'source_folder'
  | 'extension'
  | 'template'
  | 'field'
  | 'filename'
  | 'size'

// Operadores aceitos pelo backend (D-24; V5: conjunto fechado).
// 'eq' ('é') | 'contains' ('contém') | 'gt' ('>') | 'lt' ('<').
export type ConditionOperator = 'eq' | 'contains' | 'gt' | 'lt'

// Tipos de ação ordenada de uma automação (D-24): renomear/mover. Sem "route" (D-22).
export type ActionType = 'rename' | 'move'

// Condição `{field} {operator} {value}` no nível da automação (ConditionOut).
// `field_name` só é usado quando `field === 'field'` (qual campo extraído comparar).
export interface AutomationCondition {
  id: number
  field: ConditionField
  operator: ConditionOperator
  value: string
  field_name: string | null
  position: number
}

// Body de condição no POST/PATCH (ConditionIn — sem id/position, server-gerados).
export interface AutomationConditionCreate {
  field: ConditionField
  operator: ConditionOperator
  value: string
  field_name: string | null
}

// Ação ordenada (ActionOut do backend). `params`: rename→{name_pattern},
// move→{dest_folder}. Ordem por `position` (drag-and-drop / ↑↓ na UI, D-24).
export interface AutomationAction {
  id: number
  position: number
  action_type: ActionType
  params: Record<string, unknown>
}

// Body de criação de ação (ActionIn — sem id/position; position vem da ordem da lista).
export interface AutomationActionCreate {
  action_type: ActionType
  params: Record<string, unknown>
}

// Automação nomeada exposta por GET /automations (AutomationOut do backend, D-23).
// `conditions`/`actions` já vêm ordenados por `position`.
export interface Automation {
  id: number
  name: string
  active: boolean
  position: number
  conditions: AutomationCondition[]
  actions: AutomationAction[]
}

// Body de criação (POST /automations — AutomationIn).
export interface AutomationCreate {
  name: string
  active: boolean
  position?: number
  conditions: AutomationConditionCreate[]
  actions: AutomationActionCreate[]
}

// Body de edição parcial (PATCH /automations/{id} — AutomationPatch).
// `conditions`/`actions` informados SUBSTITUEM a coleção inteira; omitidos preservam.
export interface AutomationPatch {
  name?: string
  active?: boolean
  position?: number
  conditions?: AutomationConditionCreate[]
  actions?: AutomationActionCreate[]
}

// Uma linha do preview de dry-run (DryRunRow do backend, AUT-03). UM par
// origem→destino-final por documento (materialização única, D-26). Sinalização por
// flags booleanas: blocked (D-07, vermelho), collision (D-09, sufixo, âmbar),
// skipped_identical (D-10, duplicata, azul), no_match (nenhuma automação casou —
// neutro, mantido na origem). `automation_id` = qual automação casou (D-25).
export interface DryRunRow {
  document_id: number
  original_filename: string
  source_path: string | null
  dest_path: string | null
  blocked: boolean
  collision: boolean
  skipped_identical: boolean
  no_match: boolean
  automation_id: number | null
}

// Resultado de POST /automations/dry-run (DryRunOut).
export interface DryRunResult {
  rows: DryRunRow[]
}

// Resultado de POST /automations/apply (ApplyOut): run_id do lote + enfileirados.
export interface ApplyResult {
  run_id: string
  enqueued: number
}

// Resultado de POST /automations/undo (UndoOut): quantos foram revertidos.
export interface UndoResult {
  reverted: number
}

// --- Triagem "Precisam de atenção" (Fase 5 — REV-03/04/05) ---

// Item dos baldes FALHA/QUARENTENA (AttentionItemOut do backend): id + nome + motivo.
export interface AttentionItem {
  id: number
  original_filename: string
  motivo: string | null
}

// Item de EM_REVISAO (ReviewItemOut): estende com score + campos editáveis inline.
export interface ReviewItem {
  id: number
  original_filename: string
  motivo: string | null
  confidence_score: number | null
  fields: ClassificationField[]
}

// Resposta de GET /documents/attention (AttentionOut): os 3 baldes + contagens.
export interface AttentionList {
  falha: AttentionItem[]
  quarentena: AttentionItem[]
  em_revisao: ReviewItem[]
  counts: Record<string, number>
}

// Limiar global de confiança (GET/PUT /config/review-threshold) — 0.0–1.0 (D-03).
export interface ReviewThreshold {
  threshold: number
}
