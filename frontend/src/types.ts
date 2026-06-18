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

// --- Automações: PIPELINE (forma REAL da API /automations — Fase 6 REDESIGN, ---
// --- D-12..D-16, TPL-02). Substitui o modelo de regra única por um PIPELINE de  ---
// --- etapas ordenadas: cada etapa = 1 ação atômica + 0..N filtros E/OU.         ---

// Ações atômicas de uma etapa (V5: conjunto fechado no backend).
export type StepActionType = 'move' | 'rename' | 'identify_type' | 'route'

// Tipos de filtro de entrada de uma etapa (D-14).
export type StepFilterType =
  | 'field'
  | 'source_folder'
  | 'extension'
  | 'filename'
  | 'size'
  | 'template'

// Operadores de filtro aceitos pelo backend (V5: conjunto fechado).
export type RuleOperator = 'eq' | 'gt' | 'lt' | 'contains'

// Conjunção entre os filtros de uma etapa (E/OU — D-14).
export type RuleConjunction = 'and' | 'or'

// Alvo da ação `route` (Decidir tratativa — interrompe o pipeline).
export type RouteTarget = 'em_revisao' | 'nao_tratar' | 'ignorar'

// Filtro `{filter_type} {operator} {value}` de uma etapa (StepFilterOut do backend).
// `field_name` só é usado quando `filter_type === 'field'`.
export interface StepFilter {
  id: number
  filter_type: StepFilterType
  operator: RuleOperator
  value: string
  field_name: string | null
  position: number
}

// Body de filtro no POST/PATCH (StepFilterIn — sem id/position, server-gerados).
export interface StepFilterCreate {
  filter_type: StepFilterType
  operator: RuleOperator
  value: string
  field_name: string | null
}

// Etapa do pipeline (StepOut do backend): 1 ação + 0..N filtros combinados por
// `conjunction`. `params` depende da ação (move→folder_pattern, rename→name_pattern,
// identify_type→template_id, route→target). Etapas vêm ordenadas por `position` (D-12).
export interface PipelineStep {
  id: number
  position: number
  action_type: StepActionType
  conjunction: RuleConjunction
  params: Record<string, unknown>
  active: boolean
  filters: StepFilter[]
}

// Body de criação de etapa (StepIn — sem id/position, server-gerados).
// `position` é dada pela ordem da lista enviada (D-12).
export interface PipelineStepCreate {
  action_type: StepActionType
  conjunction: RuleConjunction
  params: Record<string, unknown>
  active: boolean
  filters: StepFilterCreate[]
}

// Pipeline de automação exposto por GET /automations (PipelineOut do backend).
// `steps` em ordem de execução (D-12).
export interface AutomationPipeline {
  id: number
  name: string
  active: boolean
  steps: PipelineStep[]
}

// Body de criação de pipeline (POST /automations — PipelineIn).
export interface PipelineCreate {
  name: string
  active: boolean
  steps: PipelineStepCreate[]
}

// Body de edição parcial (PATCH /automations/{id} — PipelinePatch).
// `steps` informado SUBSTITUI a coleção inteira; omitido preserva as etapas atuais.
export interface PipelinePatch {
  name?: string
  active?: boolean
  steps?: PipelineStepCreate[]
}

// Uma linha do preview de dry-run (DryRunRow do backend, AUT-03). UM par
// origem→destino-final por documento (materialização única, P8). Sinalização por
// flags booleanas: blocked (D-07, vermelho), collision (D-09, sufixo, âmbar),
// skipped_identical (D-10, duplicata, azul), routed (P9, informativo, com
// route_target), no_match (P10, neutro — mantido na origem).
export interface DryRunRow {
  document_id: number
  original_filename: string
  source_path: string | null
  dest_path: string | null
  blocked: boolean
  collision: boolean
  skipped_identical: boolean
  routed: boolean
  route_target: RouteTarget | string | null
  no_match: boolean
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
