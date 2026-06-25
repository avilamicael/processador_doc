import { useEffect, useMemo, useRef, useState } from 'react'
import type {
  ActionType,
  Automation,
  AutomationActionCreate,
  AutomationConditionCreate,
  ConditionField,
  ConditionOperator,
  Template,
} from '../types'
import { Icon } from '../components/Icon'
import { Switch } from '../components/Switch'
import {
  useAutomations,
  useCreateAutomation,
  useDeleteAutomation,
  useUpdateAutomation,
} from '../hooks/useAutomations'
import { useTemplates } from '../hooks/useTemplates'

// ─── Construtor de AUTOMAÇÕES (MODELO FINAL, mockup v3, D-23..D-26) ────────────
//
// VÁRIAS automações nomeadas (a UI lista N; a API lista N — D-23). A tela antiga
// hardcodava uma só (`data[0]`) — corrigido. Cada automação =
//   CONDIÇÕES (quando rodar, combinadas por E) → AÇÕES (o que fazer: rename/move).
//
// Layout do mockup: LISTA à esquerda (selecionar/criar/estado) + EDITOR à direita
// (cabeçalho com nome editável + switch ativo/pausado; seção "Quando rodar" com as
// condições; seção "O que fazer" com as ações ordenadas por drag-and-drop nativo +
// ↑/↓, D-24). Os chips de token (renomear/mover) são os CAMPOS REAIS do template
// referenciado pela condição "Tipo de documento" (D-26), buscados via API. Paths
// (Mover destino, Pasta de origem) normalizam aspas ao sair do campo (D-21).
//
// Sem visualizador de documento; valores como texto puro (0 dangerouslySetInnerHTML).

// ─── Catálogos (espelham FIELD_OPTS / operadores / ações do mockup) ────────────

const FIELD_OPTS: { value: ConditionField; label: string }[] = [
  { value: 'source_folder', label: 'Pasta de origem' },
  { value: 'extension', label: 'Tipo de arquivo' },
  { value: 'template', label: 'Tipo de documento' },
  { value: 'field', label: 'Valor de campo' },
  { value: 'filename', label: 'Nome do arquivo' },
  { value: 'size', label: 'Tamanho' },
]

const FIELD_LABEL: Record<ConditionField, string> = {
  source_folder: 'Pasta de origem',
  extension: 'Tipo de arquivo',
  template: 'Tipo de documento',
  field: 'Valor de campo',
  filename: 'Nome do arquivo',
  size: 'Tamanho',
}

// Operadores: rótulo amigável ↔ valor do backend (D-24).
const OP_OPTS: { value: ConditionOperator; label: string }[] = [
  { value: 'eq', label: 'é' },
  { value: 'contains', label: 'contém' },
  { value: 'gt', label: '>' },
  { value: 'lt', label: '<' },
]
const OP_LABEL: Record<ConditionOperator, string> = {
  eq: 'é',
  contains: 'contém',
  gt: '>',
  lt: '<',
}

// Catálogo das ações (D-24 + 06.2). Cores por token, distintas entre si:
// rename → --st-quarentena ; move → --st-tratado ; copy → --st-encontrado.
// 'copy' espelha 'move' (usa dest_folder) mas NÃO remove o original (D-01/D-05).
const ACTION_META: Record<
  ActionType,
  { label: string; icon: 'docMini' | 'folder'; dot: string }
> = {
  rename: { label: 'Renomear', icon: 'docMini', dot: 'var(--st-quarentena)' },
  move: { label: 'Mover', icon: 'folder', dot: 'var(--st-tratado)' },
  copy: { label: 'Copiar', icon: 'folder', dot: 'var(--st-encontrado)' },
}

// ─── Rascunho local (draft) ────────────────────────────────────────────────────

let nextKey = 1

interface CondDraft {
  key: number
  field: ConditionField
  operator: ConditionOperator
  value: string
  field_name: string
}

interface ActDraft {
  key: number
  action_type: ActionType
  // rename → name_pattern ; move|copy → dest_folder (genérico)
  pattern: string
}

interface AutoDraft {
  // id do backend (null = automação nova ainda não persistida)
  id: number | null
  name: string
  active: boolean
  position: number
  conds: CondDraft[]
  acts: ActDraft[]
}

function newCond(field: ConditionField = 'source_folder'): CondDraft {
  return { key: nextKey++, field, operator: 'eq', value: '', field_name: '' }
}

function newAct(action: ActionType): ActDraft {
  return { key: nextKey++, action_type: action, pattern: '' }
}

function automationToDraft(a: Automation): AutoDraft {
  return {
    id: a.id,
    name: a.name,
    active: a.active,
    position: a.position,
    conds: a.conditions.map((c) => ({
      key: nextKey++,
      field: c.field,
      operator: c.operator,
      value: c.value,
      field_name: c.field_name ?? '',
    })),
    acts: a.actions.map((ac) => ({
      key: nextKey++,
      action_type: ac.action_type,
      pattern:
        ac.action_type === 'rename'
          ? typeof ac.params.name_pattern === 'string'
            ? ac.params.name_pattern
            : ''
          : typeof ac.params.dest_folder === 'string'
            ? ac.params.dest_folder
            : '',
    })),
  }
}

function blankDraft(): AutoDraft {
  return {
    id: null,
    name: 'Nova automação',
    active: true,
    position: 0,
    conds: [newCond()],
    acts: [],
  }
}

// ─── Helpers de path / tokens / preview (D-21/D-26) ────────────────────────────

// Remove aspas (simples/duplas) nas pontas — espelha o strip_quotes do backend (D-21).
function stripQuotes(value: string): string {
  return value.trim().replace(/^["']+|["']+$/g, '')
}

// Sanitiza caracteres inválidos no Windows (D-08), só para a pré-visualização.
// Espelha sanitize_component do backend: < > : " / \ | ? * → "_" POR SEGMENTO,
// DEPOIS dos filtros. O anchor (drive/UNC) nunca passa por aqui (ver resolveFolderSegments).
const WINDOWS_INVALID = /[<>:"/\\|?*]/g

function sanitizeSegment(seg: string): string {
  return seg.replace(WINDOWS_INVALID, '_')
}

// Detecta o ANCHOR absoluto Windows (espelha 09-01 _is_abs_windows): drive `C:\`/`C:/`
// ou UNC `\\srv\share`. Devolve o anchor e o RESTO do caminho, ou null se relativo.
// (Para a prévia client-side basta a forma Windows — o caso real do piloto é `C:\…`.)
function splitWindowsAbsolute(pattern: string): { anchor: string; rest: string } | null {
  // Drive: uma letra + ':' + separador. Ex.: C:\Users\…  ou  C:/Users/…
  const drive = pattern.match(/^([A-Za-z]:[\\/])/)
  if (drive) {
    return { anchor: drive[1], rest: pattern.slice(drive[1].length) }
  }
  // UNC: \\servidor\share\…  (anchor = \\servidor\share)
  const unc = pattern.match(/^(\\\\[^\\/]+[\\/][^\\/]+)([\\/]?)/)
  if (unc) {
    const anchor = unc[1] + (unc[2] || '')
    return { anchor, rest: pattern.slice(anchor.length) }
  }
  return null
}

function sampleValue(field: { name: string; hint: string | null }): string {
  if (field.hint && field.hint.trim()) return field.hint.trim()
  return field.name
}

// Detecta o atalho LEGADO de data `{data:aaaa-mm}` (spec SEM '=' contendo aaaa/mm/dd) —
// espelha _DATE_SHORTCUT_RE do backend (A1). `formato=` é a forma canônica nova.
const DATE_SHORTCUT_RE = /aaaa|mm|dd/

// Formata um valor ISO `YYYY-MM-DD` segundo `spec` (aaaa/mm/dd) — espelha _fmt_date.
// Valor não-ISO → null (sinal de "não dá pra formatar"; na prévia mostramos o token cru).
function fmtDate(iso: string, spec: string): string | null {
  const parts = iso.split('-')
  if (parts.length !== 3) return null
  const [y, m, d] = parts
  if (!(y.length === 4 && /^\d+$/.test(y) && /^\d+$/.test(m) && /^\d+$/.test(d))) return null
  return spec.replace(/aaaa/g, y).replace(/mm/g, m).replace(/dd/g, d)
}

// Remove acentos — equivalente client-side de _strip_accents (NFKD + drop combining).
function stripAccents(s: string): string {
  return s.normalize('NFD').replace(/\p{Diacritic}/gu, '')
}

// Aplica UM filtro via DISPATCH EXPLÍCITO (espelha _apply_filter; NUNCA eval, T-09-08).
// Filtro desconhecido OU arg inválido → INERTE (devolve o value cru). `formato=` que
// não casa data → null (a prévia mostra o token cru, sem chutar). `padrao=` é no-op aqui.
function applyFilter(value: string, f: string): string | null {
  f = f.trim()
  if (f.startsWith('palavras=')) {
    const n = Number(f.slice('palavras='.length))
    if (!Number.isInteger(n)) return value // inerte
    return value.split(/\s+/).filter(Boolean).slice(0, n).join(' ')
  }
  if (f.startsWith('letras=') || f.startsWith('truncar=')) {
    const n = Number(f.split('=', 2)[1])
    if (!Number.isInteger(n)) return value // inerte
    return value.slice(0, n)
  }
  if (f === 'maiusc') return value.toUpperCase()
  if (f === 'minusc') return value.toLowerCase()
  if (f === 'sem_acento') return stripAccents(value)
  if (f.startsWith('substituir=')) {
    const arg = f.slice('substituir='.length)
    const i = arg.indexOf('>')
    const de = i < 0 ? arg : arg.slice(0, i)
    const para = i < 0 ? '' : arg.slice(i + 1)
    return de === '' ? value : value.split(de).join(para)
  }
  if (f.startsWith('formato=')) {
    const spec = f.slice('formato='.length)
    return fmtDate(value, spec) // null → caller mostra o token cru
  }
  if (f.startsWith('padrao=')) return value // resolvido antes (no-op aqui)
  return value // desconhecido → inerte
}

// Extrai `padrao=X` da cadeia (espelha _has_padrao). Usado quando o campo não tem
// exemplo: na prévia, vira o valor de exemplo.
function hasPadrao(filters: string[]): string | null {
  for (const f of filters) {
    const t = f.trim()
    if (t.startsWith('padrao=')) return t.slice('padrao='.length)
  }
  return null
}

// Resolve UM token `{campo:filtro=arg:filtro}` para texto (sem sanitizar — a
// sanitização por segmento é responsabilidade do caller, D-08). Espelha _substitute.repl.
function resolveToken(token: string, byName: Map<string, string>): string {
  const colon = token.indexOf(':')
  const name = (colon < 0 ? token : token.slice(0, colon)).trim()
  const spec = colon < 0 ? null : token.slice(colon + 1)
  const filters = spec !== null ? spec.split(':').map((s) => s.trim()) : []

  const sample = byName.get(name)
  const missing = sample === undefined || !sample.trim()

  let value: string
  if (missing) {
    const def = hasPadrao(filters)
    if (def === null) return `⟨${name}?⟩` // campo ausente sem padrao= → marcador
    value = def
  } else {
    value = sample
  }

  if (spec !== null) {
    const specStr = spec.trim()
    if (!missing && !specStr.includes('=') && DATE_SHORTCUT_RE.test(specStr)) {
      // Atalho LEGADO `{data:aaaa-mm}` (sem '='): trata o spec como formato de data.
      const formatted = fmtDate(value, specStr)
      value = formatted ?? `{${token}}` // não-ISO → token cru (prévia)
    } else {
      // PIPELINE de filtros inline (D-06/D-07), dispatch explícito sem eval.
      for (const filt of filters) {
        const out = applyFilter(value, filt)
        if (out === null) return `{${token}}` // formato= sobre não-data → token cru
        value = out
      }
    }
  }
  return value
}

// Resolve um padrão de NOME (rename): aplica os filtros e sanitiza o COMPONENTE inteiro
// como hoje (espelha resolve_pattern → _substitute + sanitize_component).
function resolvePattern(
  pattern: string,
  fields: { name: string; hint: string | null }[],
): string {
  const byName = new Map(fields.map((f) => [f.name, sampleValue(f)]))
  const resolved = pattern.replace(/\{([^}]+)\}/g, (_m, token: string) =>
    resolveToken(String(token), byName),
  )
  return sanitizeSegment(resolved)
}

// Resolve um padrão de PASTA (move/copy) preservando o ANCHOR absoluto e sanitizando
// só os segmentos APÓS o anchor (D-08, espelha resolve_dest_folder). Devolve o caminho
// montado: anchor + segmentos resolvidos juntados por '\'. Para padrão relativo, devolve
// os segmentos juntados por '/' (mantém a prévia atual de pasta relativa).
function resolveFolderPreview(
  pattern: string,
  fields: { name: string; hint: string | null }[],
): { text: string; absolute: boolean } {
  const byName = new Map(fields.map((f) => [f.name, sampleValue(f)]))
  const resolveSeg = (seg: string) =>
    sanitizeSegment(
      seg.replace(/\{([^}]+)\}/g, (_m, token: string) => resolveToken(String(token), byName)),
    )

  const abs = splitWindowsAbsolute(pattern)
  if (abs) {
    // Segmentos APÓS o anchor: fatia por '/' e '\', resolve+sanitiza cada um.
    const segs = abs.rest
      .split(/[\\/]+/)
      .filter((s) => s.length > 0)
      .map(resolveSeg)
    // anchor já termina em separador (drive) — junta os segmentos por '\' (Windows).
    const tail = segs.join('\\')
    const anchor = abs.anchor
    const joined = tail ? (/[\\/]$/.test(anchor) ? anchor + tail : anchor + '\\' + tail) : anchor
    return { text: joined, absolute: true }
  }

  // Relativo: mantém a prévia por segmento (juntada por '/'), como antes.
  const segs = pattern
    .split(/[\\/]+/)
    .filter((s) => s.length > 0)
    .map(resolveSeg)
  return { text: segs.join('/'), absolute: false }
}

// Resumo das condições para o card da lista (espelha o condTxt do mockup).
function summarizeConds(a: AutoDraft, templates: Template[]): string {
  if (a.conds.length === 0) return 'Sem condições — roda para qualquer documento'
  return a.conds
    .map((c) => {
      const fld = FIELD_LABEL[c.field]
      let val = c.value
      if (c.field === 'template') {
        const t = templates.find((t) => String(t.id) === c.value)
        val = t ? t.name : c.value || '—'
      }
      const lead = c.field === 'field' && c.field_name ? `${fld} (${c.field_name})` : fld
      return `${lead} ${OP_LABEL[c.operator]} ${val}`.trim()
    })
    .join(' · ')
}

// ─── Estilos inline reutilizados (espelham .select/.inp/.lbl do mockup) ─────────

const lblStyle = {
  fontSize: 11,
  fontWeight: 600,
  letterSpacing: '.3px',
  textTransform: 'uppercase' as const,
  color: 'var(--text-3)',
  marginBottom: 6,
  display: 'block',
}
const inpStyle = {
  height: 34,
  padding: '0 10px',
  border: '1px solid var(--border-strong)',
  borderRadius: 'var(--radius-sm)',
  background: 'var(--surface)',
  color: 'var(--text)',
  fontSize: 12.5,
  fontFamily: 'inherit',
  outline: 'none',
} as const
const monoInpStyle = { ...inpStyle, fontFamily: 'var(--font-mono)', fontSize: 12 } as const
const hintStyle = { fontSize: 11.5, color: 'var(--text-3)', marginTop: 8, lineHeight: 1.5 } as const

export function AutomationsPage() {
  const autosQuery = useAutomations()
  const templatesQuery = useTemplates()
  const createAutomation = useCreateAutomation()
  const updateAutomation = useUpdateAutomation()
  const deleteAutomation = useDeleteAutomation()

  const templates = templatesQuery.data ?? []

  // Lista de rascunhos (fonte de verdade do editor). Hidratada da API; cada draft
  // carrega id do backend (ou null se nova/não-persistida).
  const [drafts, setDrafts] = useState<AutoDraft[]>([])
  // Chave de seleção: id do backend para persistidas; id negativo estável p/ novas.
  const [selKey, setSelKey] = useState<number | null>(null)
  const newSeq = useRef(-1)
  const newKeys = useRef(new Map<AutoDraft, number>())
  const [dirty, setDirty] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const dragIndex = useRef<number | null>(null)
  const [dragOver, setDragOver] = useState<number | null>(null)

  // Hidrata a lista a partir do backend, exceto se houver alterações não salvas.
  const apiSig = autosQuery.data
    ? autosQuery.data.map((a) => `${a.id}@${a.position}`).join(',')
    : 'none'
  useEffect(() => {
    if (dirty) return
    const list = (autosQuery.data ?? [])
      .slice()
      .sort((a, b) => a.position - b.position)
      .map(automationToDraft)
    setDrafts(list)
    // mantém a seleção por id quando possível; senão seleciona a primeira.
    setSelKey((prev) => {
      if (prev != null && list.some((d) => d.id === prev)) return prev
      return list.length > 0 && list[0].id != null ? list[0].id : null
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiSig])

  // Chave de seleção estável: id do backend quando há; senão id negativo p/ novas.
  function selectionKey(d: AutoDraft): number {
    if (d.id != null) return d.id
    let k = newKeys.current.get(d)
    if (k == null) {
      k = newSeq.current--
      newKeys.current.set(d, k)
    }
    return k
  }

  const selected = drafts.find((d) => selectionKey(d) === selKey) ?? null

  const isInitialLoading = autosQuery.isLoading && !autosQuery.data
  const isError = autosQuery.isError && !autosQuery.data
  const saving = createAutomation.isPending || updateAutomation.isPending
  const busy = saving || deleteAutomation.isPending

  // Template referenciado pela condição "Tipo de documento" da automação selecionada
  // — os chips de token vêm dos campos desse template (D-26).
  const activeTemplate: Template | null = useMemo(() => {
    if (!selected) return null
    const cond = selected.conds.find((c) => c.field === 'template' && c.value.trim())
    if (!cond) return null
    return templates.find((t) => String(t.id) === cond.value) ?? null
  }, [selected, templates])

  // ── Mutadores do rascunho selecionado ──
  const patchSelected = (patch: Partial<AutoDraft>) => {
    if (!selected) return
    setDrafts((list) =>
      list.map((d) => {
        if (d !== selected) return d
        const updated = { ...d, ...patch }
        // Preserva a chave de seleção das automações novas (sem id): a chave é
        // indexada pela identidade do objeto; ao recriar o draft, transfere a
        // chave p/ o novo objeto — senão o editor deseleciona ao editar (bug).
        const k = newKeys.current.get(d)
        if (k != null) newKeys.current.set(updated, k)
        return updated
      }),
    )
    setDirty(true)
    setFormError(null)
  }

  const patchCond = (key: number, patch: Partial<CondDraft>) => {
    if (!selected) return
    const conds = selected.conds.map((c) => (c.key === key ? { ...c, ...patch } : c))
    patchSelected({ conds })
  }
  const addCond = () => {
    if (!selected) return
    patchSelected({ conds: [...selected.conds, newCond()] })
  }
  const removeCond = (key: number) => {
    if (!selected) return
    patchSelected({ conds: selected.conds.filter((c) => c.key !== key) })
  }

  const patchAct = (key: number, patch: Partial<ActDraft>) => {
    if (!selected) return
    const acts = selected.acts.map((a) => (a.key === key ? { ...a, ...patch } : a))
    patchSelected({ acts })
  }
  const addAct = (action: ActionType) => {
    if (!selected) return
    patchSelected({ acts: [...selected.acts, newAct(action)] })
  }
  const removeAct = (key: number) => {
    if (!selected) return
    patchSelected({ acts: selected.acts.filter((a) => a.key !== key) })
  }

  // Reordenação por botões ↑/↓ (acessibilidade, D-24).
  const moveAct = (index: number, dir: -1 | 1) => {
    if (!selected) return
    const j = index + dir
    if (j < 0 || j >= selected.acts.length) return
    const next = selected.acts.slice()
    ;[next[index], next[j]] = [next[j], next[index]]
    patchSelected({ acts: next })
  }

  // Insere {campo} no fim do padrão da ação (D-26).
  const insertToken = (key: number, token: string) => {
    if (!selected) return
    const acts = selected.acts.map((a) =>
      a.key === key ? { ...a, pattern: `${a.pattern}{${token}}` } : a,
    )
    patchSelected({ acts })
  }

  // ── Drag-and-drop nativo das ações (HTML5, sem libs — D-24) ──
  const onDragStart = (index: number) => (e: React.DragEvent) => {
    dragIndex.current = index
    e.dataTransfer.effectAllowed = 'move'
  }
  const onDragOver = (index: number) => (e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    if (dragIndex.current != null && dragIndex.current !== index) setDragOver(index)
  }
  const onDrop = (index: number) => (e: React.DragEvent) => {
    e.preventDefault()
    const from = dragIndex.current
    setDragOver(null)
    dragIndex.current = null
    if (from == null || from === index || !selected) return
    const next = selected.acts.slice()
    const [moved] = next.splice(from, 1)
    next.splice(index, 0, moved)
    patchSelected({ acts: next })
  }
  const onDragEnd = () => {
    dragIndex.current = null
    setDragOver(null)
  }

  // ── Criar / selecionar ──
  const createNew = () => {
    const draft = blankDraft()
    setDrafts((list) => [...list, draft])
    setSelKey(selectionKey(draft))
    setDirty(true)
    setFormError(null)
  }

  const select = (d: AutoDraft) => {
    setSelKey(selectionKey(d))
    setFormError(null)
  }

  // ── Validação + persistência (D-23/D-24) ──
  const validate = (d: AutoDraft): string | null => {
    if (!d.name.trim()) return 'Informe o nome da automação.'
    // Template determinável do próprio draft (mesma regra de activeTemplate, mas
    // resolvida a partir de `d` — independe do closure de `selected`).
    const draftTemplate: Template | null = (() => {
      const cond = d.conds.find((c) => c.field === 'template' && c.value.trim())
      if (!cond) return null
      return templates.find((t) => String(t.id) === cond.value) ?? null
    })()
    for (const c of d.conds) {
      if (c.field === 'template' && !c.value.trim()) {
        return 'Na condição "Tipo de documento", escolha um template.'
      }
      // D-08: a condição "Valor de campo" exige um template determinável — sem ele
      // não há dropdown de campos e a comparação seria às cegas. Bloqueia salvar.
      if (c.field === 'field' && !draftTemplate) {
        return 'Na condição "Valor de campo", escolha um template na condição "Tipo de documento" para comparar um campo.'
      }
      if (c.field === 'field' && !c.field_name.trim()) {
        return 'Na condição "Valor de campo", informe qual campo comparar.'
      }
      if (!c.value.trim()) {
        return `Na condição "${FIELD_LABEL[c.field]}", informe um valor.`
      }
    }
    if (d.acts.length === 0) return 'Adicione ao menos uma ação (Renomear ou Mover).'
    for (const a of d.acts) {
      if (a.action_type === 'rename' && !a.pattern.trim()) {
        return 'Em "Renomear", defina o padrão do nome.'
      }
      if (a.action_type === 'move' && !stripQuotes(a.pattern).trim()) {
        return 'Em "Mover", defina a pasta de destino.'
      }
      if (a.action_type === 'copy' && !stripQuotes(a.pattern).trim()) {
        return 'Em "Copiar", defina a pasta de destino.'
      }
    }
    return null
  }

  const toCreateBody = (d: AutoDraft) => {
    const conditions: AutomationConditionCreate[] = d.conds.map((c) => ({
      field: c.field,
      operator: c.operator,
      value: c.field === 'source_folder' ? stripQuotes(c.value) : c.value.trim(),
      field_name: c.field === 'field' ? c.field_name.trim() || null : null,
    }))
    const actions: AutomationActionCreate[] = d.acts.map((a) =>
      a.action_type === 'rename'
        ? { action_type: 'rename', params: { name_pattern: a.pattern.trim() } }
        : // move|copy: mesmo mapeamento → dest_folder; o action_type preserva a distinção.
          { action_type: a.action_type, params: { dest_folder: stripQuotes(a.pattern) } },
    )
    return { name: d.name.trim(), active: d.active, conditions, actions }
  }

  const save = () => {
    if (!selected) return
    const err = validate(selected)
    if (err) {
      setFormError(err)
      return
    }
    setFormError(null)
    const body = toCreateBody(selected)
    const onError = () =>
      setFormError('Não foi possível salvar. Confira os dados e tente novamente.')
    if (selected.id != null) {
      updateAutomation.mutate(
        { id: selected.id, body },
        { onSuccess: () => setDirty(false), onError },
      )
    } else {
      const position = drafts.length
      createAutomation.mutate(
        { ...body, position },
        {
          onSuccess: (created) => {
            // re-aponta a seleção para o id recém-criado e libera a hidratação.
            setDirty(false)
            setSelKey(created.id)
          },
          onError,
        },
      )
    }
  }

  const discard = () => {
    setDirty(false)
    setFormError(null)
    setConfirmDelete(false)
    autosQuery.refetch()
  }

  const doDelete = () => {
    if (!selected) return
    setConfirmDelete(false)
    if (selected.id == null) {
      // automação nova nunca persistida: só remove do rascunho local.
      const rest = drafts.filter((d) => d !== selected)
      setDrafts(rest)
      setSelKey(rest.length > 0 ? selectionKey(rest[0]) : null)
      return
    }
    deleteAutomation.mutate(selected.id, {
      onSuccess: () => {
        setDirty(false)
      },
    })
  }

  // Liga/desliga a automação (header switch). Persiste direto se já existe.
  const toggleActive = () => {
    if (!selected) return
    const next = !selected.active
    if (selected.id != null && !dirty) {
      updateAutomation.mutate({ id: selected.id, body: { active: next } })
    }
    patchSelected({ active: next })
  }

  // ─── Render: chips de token ─────────────────────────────────────────────────
  const renderTokenBar = (a: ActDraft) => {
    if (!activeTemplate) {
      return (
        <div
          className="nochip-box"
          style={{
            marginTop: 11,
            background: 'var(--surface-3)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            padding: '10px 11px',
            fontSize: 11.5,
            color: 'var(--text-3)',
            fontStyle: 'italic',
          }}
        >
          Adicione a condição <b>«Tipo de documento»</b> para usar os campos do template
          como tokens.
        </div>
      )
    }
    return (
      <div
        style={{
          marginTop: 11,
          background: 'var(--surface-3)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)',
          padding: '10px 11px',
        }}
      >
        <div style={{ fontSize: 11.5, color: 'var(--text-2)', marginBottom: 8 }}>
          Campos do template <b style={{ color: 'var(--accent)' }}>{activeTemplate.name}</b> —
          clique para inserir:
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {activeTemplate.fields.length === 0 && (
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
              Esse template ainda não tem campos.
            </span>
          )}
          {activeTemplate.fields.map((f) => (
            <button
              key={f.id}
              type="button"
              className="chip"
              style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600 }}
              aria-label={`Inserir {${f.name}} no padrão`}
              title={`Inserir {${f.name}}`}
              onClick={() => insertToken(a.key, f.name)}
            >
              <span style={{ color: 'var(--text-3)', fontWeight: 700 }}>+</span> {`{${f.name}}`}
            </button>
          ))}
        </div>
      </div>
    )
  }

  // Pré-visualização ao vivo (D-09/D-26). Para rename: nome sanitizado + .pdf.
  // Para move/copy: caminho de pasta — ABSOLUTO (anchor preservado) quando o destino
  // é absoluto; senão segmentos relativos. Filtros inline aplicados nos dois casos.
  const renderPreview = (a: ActDraft) => {
    if (!a.pattern.trim() || !activeTemplate) return null
    const isRn = a.action_type === 'rename'
    let out: string
    if (isRn) {
      out = resolvePattern(a.pattern, activeTemplate.fields) + '.pdf'
    } else {
      out = resolveFolderPreview(a.pattern, activeTemplate.fields).text
    }
    const color = isRn ? 'var(--st-tratado)' : 'var(--st-encontrado)'
    const bg = isRn ? 'var(--st-tratado-bg)' : 'var(--st-encontrado-bg)'
    return (
      <div
        style={{
          marginTop: 11,
          display: 'flex',
          alignItems: 'center',
          gap: 9,
          fontSize: 12.5,
          flexWrap: 'wrap',
        }}
      >
        <span style={{ color: 'var(--text-3)' }}>Prévia:</span>
        <span style={{ color: 'var(--text-3)' }}>→</span>
        <span
          className="cell-mono"
          style={{
            fontWeight: 600,
            color,
            background: bg,
            padding: '3px 9px',
            borderRadius: 7,
            wordBreak: 'break-all',
          }}
        >
          {out}
        </span>
      </div>
    )
  }

  // ─── Render: UMA condição (linha) ───────────────────────────────────────────
  const renderCond = (c: CondDraft, index: number) => {
    const isTmpl = c.field === 'template'
    const isField = c.field === 'field'
    const isPath = c.field === 'source_folder'
    return (
      <div
        key={c.key}
        style={{
          display: 'flex',
          gap: 8,
          alignItems: 'center',
          marginBottom: 8,
          flexWrap: 'wrap',
        }}
      >
        <span
          style={{
            fontSize: 11,
            fontWeight: 700,
            color: 'var(--text-3)',
            width: 24,
            textAlign: 'right',
          }}
        >
          {index === 0 ? 'SE' : 'E'}
        </span>
        <select
          className="select"
          style={{ width: 168, height: 34 }}
          value={c.field}
          onChange={(e) =>
            patchCond(c.key, {
              field: e.target.value as ConditionField,
              // ao virar template, zera value (passa a ser select de template)
              value: '',
            })
          }
        >
          {FIELD_OPTS.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </select>
        {isField &&
          (activeTemplate ? (
            // D-07: o nome do campo é escolhido num dropdown ESTRITO dos campos do
            // template referenciado pela condição "Tipo de documento" — nunca digitado
            // (um typo fazia a condição nunca casar, sem aviso).
            <select
              className="select"
              style={{ width: 168, height: 34 }}
              aria-label="Qual campo extraído comparar"
              value={c.field_name}
              onChange={(e) => patchCond(c.key, { field_name: e.target.value })}
            >
              <option value="">Escolha um campo…</option>
              {activeTemplate.fields.map((f) => (
                <option key={f.id} value={f.name}>
                  {f.name}
                </option>
              ))}
            </select>
          ) : (
            // D-08: sem template determinável, a condição é BLOQUEADA com aviso — sem
            // fallback de texto livre nem autocomplete global. O guard correspondente
            // em validate() impede salvar.
            <span
              className="nochip-box"
              style={{
                flex: 1,
                minWidth: 200,
                background: 'var(--surface-3)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                padding: '7px 10px',
                fontSize: 11.5,
                color: 'var(--text-3)',
                fontStyle: 'italic',
              }}
            >
              Escolha um template na condição «Tipo de documento» para comparar um campo.
            </span>
          ))}
        <select
          className="select"
          style={{ width: 96, height: 34 }}
          value={c.operator}
          onChange={(e) => patchCond(c.key, { operator: e.target.value as ConditionOperator })}
        >
          {OP_OPTS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        {isTmpl ? (
          <select
            className="select"
            style={{ flex: 1, minWidth: 140, height: 34 }}
            value={c.value}
            onChange={(e) => patchCond(c.key, { value: e.target.value })}
          >
            <option value="">Escolha um template…</option>
            {templates.map((t) => (
              <option key={t.id} value={String(t.id)}>
                {t.name}
              </option>
            ))}
          </select>
        ) : (
          <input
            style={{
              ...(isPath || c.field === 'extension' ? monoInpStyle : inpStyle),
              flex: 1,
              minWidth: 120,
            }}
            placeholder={
              c.field === 'extension'
                ? '.pdf'
                : isPath
                  ? 'Downloads/'
                  : c.field === 'size'
                    ? 'ex.: 1048576'
                    : 'valor'
            }
            value={c.value}
            onChange={(e) => patchCond(c.key, { value: e.target.value })}
            onBlur={isPath ? (e) => patchCond(c.key, { value: stripQuotes(e.target.value) }) : undefined}
          />
        )}
        <button
          className="row-action"
          aria-label="Remover condição"
          title="Remover condição"
          onClick={() => removeCond(c.key)}
          style={{ color: 'var(--st-erro)' }}
        >
          <Icon name="alert" size={15} />
        </button>
      </div>
    )
  }

  // ─── Render: UMA ação (card) ────────────────────────────────────────────────
  const renderAct = (a: ActDraft, index: number) => {
    const meta = ACTION_META[a.action_type]
    const isRn = a.action_type === 'rename'
    const isOver = dragOver === index
    return (
      <div
        key={a.key}
        className="card"
        draggable
        onDragStart={onDragStart(index)}
        onDragOver={onDragOver(index)}
        onDrop={onDrop(index)}
        onDragEnd={onDragEnd}
        style={{
          position: 'relative',
          padding: '13px 13px 13px 56px',
          background: 'var(--surface-2)',
          boxShadow: isOver ? 'inset 0 3px 0 var(--accent)' : undefined,
          borderColor: isOver ? 'var(--accent)' : undefined,
        }}
      >
        {/* alça de arraste */}
        <div
          title="Arraste para reordenar"
          aria-hidden
          style={{
            position: 'absolute',
            left: 11,
            top: 13,
            width: 18,
            color: 'var(--text-3)',
            cursor: 'grab',
            fontSize: 15,
            lineHeight: 1,
            userSelect: 'none',
          }}
        >
          ⠿
        </div>
        {/* quadradinho do tipo */}
        <span
          style={{
            position: 'absolute',
            left: 31,
            top: 13,
            width: 22,
            height: 22,
            borderRadius: 6,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: meta.dot,
            color: '#fff',
          }}
        >
          <Icon name={meta.icon} size={13} stroke="#fff" />
        </span>

        {/* topo: tipo + ações ↑/↓/✕ */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <span style={{ fontSize: 13, fontWeight: 700 }}>{meta.label}</span>
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 4 }}>
            <button
              className="row-action"
              aria-label="Mover ação para cima"
              title="Mover ação para cima"
              disabled={index === 0}
              onClick={() => moveAct(index, -1)}
              style={{ opacity: index === 0 ? 0.35 : 1 }}
            >
              <Icon name="arrowUp" size={15} />
            </button>
            <button
              className="row-action"
              aria-label="Mover ação para baixo"
              title="Mover ação para baixo"
              disabled={!selected || index === selected.acts.length - 1}
              onClick={() => moveAct(index, 1)}
              style={{
                opacity: !selected || index === selected.acts.length - 1 ? 0.35 : 1,
              }}
            >
              <Icon name="arrowDown" size={15} />
            </button>
            <button
              className="row-action"
              aria-label="Remover ação"
              title="Remover ação"
              style={{ color: 'var(--st-erro)' }}
              onClick={() => removeAct(a.key)}
            >
              <Icon name="alert" size={15} />
            </button>
          </div>
        </div>

        <span style={lblStyle}>
          {isRn ? 'Padrão do nome' : 'Pasta de destino'}
          {!isRn && (
            <span
              style={{ textTransform: 'none', letterSpacing: 0, color: 'var(--text-3)', fontWeight: 500 }}
            >
              {' '}
              — aceita com ou sem aspas
            </span>
          )}
        </span>
        <input
          className="cell-mono"
          style={{ ...monoInpStyle, width: '100%', height: 36 }}
          placeholder={isRn ? '{cliente}_{numero}' : 'Documentos/{cliente}/{data}/'}
          value={a.pattern}
          onChange={(e) => patchAct(a.key, { pattern: e.target.value })}
          onBlur={isRn ? undefined : (e) => patchAct(a.key, { pattern: stripQuotes(e.target.value) })}
        />
        {renderTokenBar(a)}
        {renderPreview(a)}
        {isRn ? (
          <div style={hintStyle}>
            <code>{'{campo}'}</code> é trocado pelo <b>valor lido do documento</b>. Os campos
            vêm do template da condição "Tipo de documento". Você pode transformar o valor com{' '}
            <b>filtros</b>: <code>{'{fornecedor:maiusc:palavras=2}'}</code>,{' '}
            <code>{'{cliente:sem_acento}'}</code>, <code>{'{data:formato=aaaa-mm-dd}'}</code>.
          </div>
        ) : (
          <div style={hintStyle}>
            Cole o caminho como vier do Windows — <code>"C:\Users\…\Análise"</code> ou{' '}
            <code>C:\Users\…\Análise</code>: as aspas são removidas ao sair do campo. Caminhos
            absolutos (<code>C:\…</code>, <code>\\servidor\…</code>) vão exatamente para onde
            você indicar. Use <b>filtros</b> nos campos, ex.:{' '}
            <code>{'C:\\NOTAS\\{fornecedor:maiusc:palavras=1}'}</code>.
          </div>
        )}
        {a.action_type === 'copy' && (
          <div style={{ ...hintStyle, color: 'var(--st-encontrado)', fontWeight: 600 }}>
            O original permanece onde está — uma cópia é criada no destino.
          </div>
        )}
      </div>
    )
  }

  // ─── Render principal ───────────────────────────────────────────────────────
  return (
    <div>
      <div className="sec-head">
        <div className="sec-head-col">
          <h2 className="sec-title">Automações</h2>
          <p className="sec-desc">
            Quando um documento bate nas <b>condições</b>, a automação executa suas{' '}
            <b>ações</b> (renomear/mover), na ordem definida. As automações são avaliadas de
            cima para baixo — a primeira cujas condições casam vence.
          </p>
        </div>
      </div>

      {/* Loading */}
      {isInitialLoading && (
        <div className="stack">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={`sk-${i}`} className="card" style={{ padding: 18 }}>
              <div style={{ height: 56, borderRadius: 8, background: 'var(--surface-3)', opacity: 0.7 }} />
            </div>
          ))}
        </div>
      )}

      {/* Erro */}
      {isError && (
        <div className="card" style={{ padding: '48px 24px', textAlign: 'center' }}>
          <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>Não foi possível carregar.</div>
          <p style={{ fontSize: 13, color: 'var(--text-3)', margin: '0 0 16px' }}>
            Verifique se o servidor está rodando e tente de novo.
          </p>
          <button className="btn-primary" onClick={() => autosQuery.refetch()}>
            <Icon name="refresh" size={15} />
            Tentar de novo
          </button>
        </div>
      )}

      {!isInitialLoading && !isError && (
        <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: 18, alignItems: 'start' }}>
          {/* ── LISTA de automações ── */}
          <div>
            <div
              style={{
                fontSize: 11,
                fontWeight: 700,
                letterSpacing: '.9px',
                textTransform: 'uppercase',
                color: 'var(--text-3)',
                margin: '2px 2px 8px',
              }}
            >
              Minhas automações
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
              {drafts.length === 0 && (
                <div
                  className="card"
                  style={{ padding: '20px 14px', fontSize: 12.5, color: 'var(--text-3)', textAlign: 'center' }}
                >
                  Nenhuma automação ainda. Crie a primeira abaixo.
                </div>
              )}
              {drafts.map((d) => {
                const isSel = selectionKey(d) === selKey
                return (
                  <button
                    key={selectionKey(d)}
                    type="button"
                    className="card"
                    onClick={() => select(d)}
                    style={{
                      padding: '12px 13px',
                      cursor: 'pointer',
                      textAlign: 'left',
                      border: isSel ? '1px solid var(--accent)' : undefined,
                      boxShadow: isSel ? '0 0 0 2px var(--accent-ring)' : undefined,
                    }}
                  >
                    <div
                      style={{
                        fontSize: 13.5,
                        fontWeight: 700,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                      }}
                    >
                      <span
                        aria-hidden
                        style={{
                          width: 7,
                          height: 7,
                          borderRadius: '50%',
                          flex: 'none',
                          background: d.active ? '#2FBF71' : 'var(--text-3)',
                        }}
                      />
                      {d.name || 'Sem nome'}
                      {d.id == null && (
                        <span style={{ fontSize: 10.5, color: 'var(--accent)', fontWeight: 600 }}>
                          (nova)
                        </span>
                      )}
                    </div>
                    <div
                      style={{
                        fontSize: 11.5,
                        color: 'var(--text-3)',
                        marginTop: 4,
                        lineHeight: 1.5,
                      }}
                    >
                      {summarizeConds(d, templates)}
                    </div>
                  </button>
                )
              })}
            </div>
            <button
              type="button"
              onClick={createNew}
              style={{
                marginTop: 9,
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 7,
                padding: 11,
                borderRadius: 'var(--radius)',
                border: '1px dashed var(--border-strong)',
                background: 'transparent',
                color: 'var(--text-2)',
                fontSize: 13,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              <Icon name="plus" size={15} /> Nova automação
            </button>
          </div>

          {/* ── EDITOR ── */}
          <div className="card">
            {!selected ? (
              <div style={{ padding: '52px 24px', textAlign: 'center' }}>
                <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>
                  Selecione ou crie uma automação
                </div>
                <p style={{ fontSize: 13, color: 'var(--text-3)', margin: 0 }}>
                  Cada automação define <b>quando rodar</b> (condições) e <b>o que fazer</b>{' '}
                  (renomear/mover).
                </p>
              </div>
            ) : (
              <>
                {/* cabeçalho: nome editável + estado + switch */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    padding: '15px 18px',
                    borderBottom: '1px solid var(--border)',
                  }}
                >
                  <input
                    aria-label="Nome da automação"
                    value={selected.name}
                    onChange={(e) => patchSelected({ name: e.target.value })}
                    style={{
                      fontSize: 15,
                      fontWeight: 700,
                      border: '1px solid transparent',
                      background: 'transparent',
                      color: 'var(--text)',
                      fontFamily: 'inherit',
                      padding: '4px 6px',
                      borderRadius: 7,
                      width: 340,
                      outline: 'none',
                    }}
                  />
                  <div style={{ flex: 1 }} />
                  <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
                    {selected.active ? 'Ativa' : 'Pausada'}
                  </span>
                  <Switch
                    on={selected.active}
                    onToggle={toggleActive}
                    title={selected.active ? 'Pausar automação' : 'Ativar automação'}
                  />
                </div>

                {/* SEÇÃO: Quando rodar — Condições */}
                <div style={{ padding: '16px 18px', borderBottom: '1px solid var(--border)' }}>
                  <div
                    style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, fontWeight: 700, marginBottom: 3 }}
                  >
                    <span
                      style={{
                        fontSize: 10,
                        fontWeight: 700,
                        letterSpacing: '.6px',
                        textTransform: 'uppercase',
                        padding: '2px 7px',
                        borderRadius: 999,
                        color: 'var(--st-leitura)',
                        background: 'var(--st-leitura-bg)',
                      }}
                    >
                      Quando rodar
                    </span>
                    Condições
                  </div>
                  <p style={{ fontSize: 11.5, color: 'var(--text-3)', margin: '0 0 12px' }}>
                    O documento precisa atender a TODAS as condições (E) para esta automação rodar.
                  </p>
                  {selected.conds.map((c, i) => renderCond(c, i))}
                  <button
                    type="button"
                    onClick={addCond}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 6,
                      marginTop: 4,
                      padding: '7px 11px',
                      borderRadius: 'var(--radius-sm)',
                      border: '1px dashed var(--border-strong)',
                      background: 'transparent',
                      color: 'var(--text-2)',
                      fontSize: 12,
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    <Icon name="plus" size={14} /> Adicionar condição
                  </button>
                </div>

                {/* SEÇÃO: O que fazer — Ações */}
                <div style={{ padding: '16px 18px', borderBottom: '1px solid var(--border)' }}>
                  <div
                    style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, fontWeight: 700, marginBottom: 3 }}
                  >
                    <span
                      style={{
                        fontSize: 10,
                        fontWeight: 700,
                        letterSpacing: '.6px',
                        textTransform: 'uppercase',
                        padding: '2px 7px',
                        borderRadius: 999,
                        color: 'var(--st-tratado)',
                        background: 'var(--st-tratado-bg)',
                      }}
                    >
                      O que fazer
                    </span>
                    Ações
                  </div>
                  <p style={{ fontSize: 11.5, color: 'var(--text-3)', margin: '0 0 12px' }}>
                    Executadas em ordem, de cima para baixo. Arraste ⠿ para reordenar.
                  </p>

                  {selected.acts.length === 0 && (
                    <p style={{ fontSize: 12.5, color: 'var(--text-3)', margin: '0 0 12px' }}>
                      Nenhuma ação ainda — adicione Renomear e/ou Mover abaixo.
                    </p>
                  )}

                  {selected.acts.length > 0 && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 24, marginBottom: 16 }}>
                      {selected.acts.map((a, idx) => (
                        <div key={a.key} style={{ position: 'relative' }}>
                          {renderAct(a, idx)}
                          {idx < selected.acts.length - 1 && (
                            <div
                              aria-hidden
                              style={{
                                position: 'absolute',
                                left: 28,
                                bottom: -20,
                                transform: 'translateX(-50%)',
                                color: 'var(--text-3)',
                                fontSize: 14,
                                fontWeight: 700,
                              }}
                            >
                              ↓
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    {(['rename', 'move', 'copy'] as ActionType[]).map((act) => (
                      <button
                        key={act}
                        type="button"
                        onClick={() => addAct(act)}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 7,
                          padding: '9px 13px',
                          borderRadius: 'var(--radius-sm)',
                          border: '1px dashed var(--border-strong)',
                          background: 'transparent',
                          color: 'var(--text-2)',
                          fontSize: 12.5,
                          fontWeight: 600,
                          cursor: 'pointer',
                        }}
                      >
                        <span
                          style={{ width: 8, height: 8, borderRadius: 3, background: ACTION_META[act].dot, flex: 'none' }}
                        />
                        {ACTION_META[act].label}
                      </button>
                    ))}
                  </div>
                </div>

                {formError && (
                  <p style={{ fontSize: 13, color: 'var(--st-erro)', margin: 0, padding: '14px 18px 0' }}>
                    {formError}
                  </p>
                )}

                {/* savebar */}
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'flex-end',
                    alignItems: 'center',
                    gap: 9,
                    padding: '14px 18px',
                    background: 'var(--surface-2)',
                    borderBottomLeftRadius: 'var(--radius)',
                    borderBottomRightRadius: 'var(--radius)',
                  }}
                >
                  {dirty && (
                    <span style={{ fontSize: 12, color: 'var(--text-3)', marginRight: 'auto' }}>
                      Alterações não salvas
                    </span>
                  )}
                  {dirty && (
                    <button className="btn-ghost" onClick={discard} disabled={busy}>
                      Descartar
                    </button>
                  )}
                  <button
                    className="btn-ghost"
                    onClick={() => setConfirmDelete(true)}
                    disabled={busy}
                    style={{ color: 'var(--st-erro)', borderColor: 'var(--border-strong)' }}
                  >
                    Excluir
                  </button>
                  <button className="btn-primary" onClick={save} disabled={busy || !dirty}>
                    {saving ? 'Salvando…' : 'Salvar automação'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Confirmação de exclusão */}
      {confirmDelete && selected && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,.45)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 50,
          }}
        >
          <div className="card" style={{ padding: 22, maxWidth: 440, width: '90%' }}>
            <h3 className="sec-title" style={{ fontSize: 15, marginBottom: 10 }}>
              Excluir automação
            </h3>
            <p style={{ fontSize: 13, color: 'var(--text-2)', margin: '0 0 18px' }}>
              Excluir a automação <b>«{selected.name || 'Sem nome'}»</b>? As demais automações
              continuam valendo. Documentos já tratados não são afetados.
            </p>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn-ghost" onClick={() => setConfirmDelete(false)}>
                Manter
              </button>
              <button
                className="btn-primary"
                style={{ background: 'var(--st-erro)' }}
                onClick={doDelete}
              >
                Excluir
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
