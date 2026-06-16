// Tipos do modelo de UI do DocWatch (Opção B).
// NOTA: estes refletem o MOCK do design. A fiação com a API real do backend
// acontece nas fases GSD correspondentes (Fase 2 ingestão, Fase 4 templates, etc.).

export type Page = 'documentos' | 'templates' | 'automacoes' | 'config'
export type ConfigTab = 'pastas' | 'regras' | 'leitura' | 'integracoes'
export type DocStatus = 'encontrado' | 'leitura' | 'tratado' | 'erro'
export type StatusFilter = 'todos' | DocStatus

export interface Doc {
  id: number
  name: string
  folder: string
  type: string
  tmpl: string
  status: DocStatus
  size: string
  date: string
  who: string
}

export interface Folder {
  id: number
  path: string
  rec: boolean
  types: string
  freq: string
  last: string
  files: string
}

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
