import { useEffect, useMemo, useRef, useState } from 'react'
import type {
  PipelineStepCreate,
  StepActionType,
  Template,
} from '../types'
import { Icon } from '../components/Icon'
import type { IconName } from '../components/Icon'
import { Switch } from '../components/Switch'
import {
  useAutomations,
  useCreatePipeline,
  useDeletePipeline,
  useUpdatePipeline,
} from '../hooks/useAutomations'
import { useTemplates } from '../hooks/useTemplates'

// ─── Construtor de PIPELINE (mockup 06-MOCKUP-automacoes.html, D-12..D-22) ─────
//
// Cada documento percorre TODAS as etapas cujo filtro casa, na ORDEM definida pelo
// usuário (D-12). 4 ações no v1 (D-13/D-17): Identificar arquivo (gate por extensão
// digitável), Identificar tipo (gate por template), Renomear (padrão com tokens),
// Mover (pasta destino com tokens). A ação "Decidir tratativa" (route) foi REMOVIDA
// do v1 (D-22) — não é exposta aqui.
//
// Edição INLINE por etapa (espelha o mockup): cada etapa renderiza seus próprios
// campos no card; o "Salvar" persiste a lista inteira de etapas (PATCH substitui a
// coleção). Reordenação por DRAG-AND-DROP nativo + botões ↑/↓ (D-20). Os chips de
// token são os CAMPOS REAIS do template escolhido no gate "Identificar tipo" do
// pipeline (D-19), buscados via API. Paths normalizam aspas ao sair do campo (D-21).
//
// Sem visualizador de documento; valores como texto puro (0 dangerouslySetInnerHTML).

// ─── Catálogo das 4 ações do v1 (D-13/D-17) ───────────────────────────────────

type EditableAction = 'identify_file' | 'identify_type' | 'rename' | 'move'

interface ActionMeta {
  value: EditableAction
  label: string
  icon: IconName
  // cor sólida do quadradinho do tipo (espelha k-fa/k-id/k-rn/k-mv do mockup)
  dot: string
}

const ACTIONS: ActionMeta[] = [
  { value: 'identify_file', label: 'Identificar arquivo', icon: 'filter', dot: 'var(--st-leitura)' },
  { value: 'identify_type', label: 'Identificar tipo', icon: 'grid', dot: 'var(--st-encontrado)' },
  { value: 'rename', label: 'Renomear', icon: 'docMini', dot: 'var(--st-quarentena)' },
  { value: 'move', label: 'Mover', icon: 'folder', dot: 'var(--st-tratado)' },
]

const ACTION_META: Record<EditableAction, ActionMeta> = {
  identify_file: ACTIONS[0],
  identify_type: ACTIONS[1],
  rename: ACTIONS[2],
  move: ACTIONS[3],
}

// Rótulo de qualquer ação (inclui `route` legado, que não é editável na UI v1).
function actionLabel(action: StepActionType): string {
  if (action in ACTION_META) return ACTION_META[action as EditableAction].label
  return 'Etapa'
}

// ─── Estado de rascunho do pipeline (draft) ───────────────────────────────────

let nextKey = 1

// Uma etapa em edição. Mantemos os params em campos planos (mais fácil de editar) e
// serializamos conforme a ação no submit. Cada etapa carrega uma `key` estável para
// o React (drag-and-drop reordena o array; ids do backend não bastam para etapas
// novas ainda-não-persistidas).
interface StepDraft {
  key: number
  action_type: EditableAction
  active: boolean
  // identify_file
  extensions: string
  source_folder: string
  // identify_type
  template_id: string
  // rename
  name_pattern: string
  // move
  folder_pattern: string
}

function newStepDraft(action: EditableAction): StepDraft {
  return {
    key: nextKey++,
    action_type: action,
    active: true,
    extensions: '',
    source_folder: '',
    template_id: '',
    name_pattern: '',
    folder_pattern: '',
  }
}

// Converte uma etapa persistida (PipelineStep) em rascunho editável. Etapas com ação
// `route` (legado D-22) são mapeadas para um rascunho neutro mas marcadas (filtradas
// fora do editor — preservamos no submit via stepToCreate sobre o original).
function persistedToDraft(s: {
  action_type: StepActionType
  active: boolean
  params: Record<string, unknown>
}): StepDraft {
  const p = s.params ?? {}
  const action: EditableAction =
    (s.action_type in ACTION_META ? s.action_type : 'identify_file') as EditableAction
  const exts = p.extensions
  return {
    key: nextKey++,
    action_type: action,
    active: s.active,
    extensions: Array.isArray(exts)
      ? exts.join(', ')
      : typeof exts === 'string'
        ? exts
        : '',
    source_folder: typeof p.source_folder === 'string' ? p.source_folder : '',
    template_id: p.template_id != null ? String(p.template_id) : '',
    name_pattern: typeof p.name_pattern === 'string' ? p.name_pattern : '',
    folder_pattern: typeof p.folder_pattern === 'string' ? p.folder_pattern : '',
  }
}

// Serializa um rascunho → body de etapa para a API (params conforme a ação, D-13).
function draftToCreate(d: StepDraft): PipelineStepCreate {
  const params: Record<string, unknown> = {}
  const filters: PipelineStepCreate['filters'] = []
  if (d.action_type === 'identify_file') {
    // D-17: extensões digitáveis, múltiplas (vírgula/espaço). O backend
    // (normalize_extensions) tolera string ou lista; enviamos a string crua.
    params.extensions = d.extensions.trim()
    const folder = stripQuotes(d.source_folder).trim()
    if (folder) {
      params.source_folder = folder
      // Filtro opcional de pasta de origem (D-14): só seguem arquivos dessa pasta.
      filters.push({ filter_type: 'source_folder', operator: 'eq', value: folder, field_name: null })
    }
  }
  if (d.action_type === 'identify_type') {
    const n = Number(d.template_id)
    if (Number.isFinite(n) && d.template_id.trim() !== '') params.template_id = n
  }
  if (d.action_type === 'rename') params.name_pattern = d.name_pattern.trim()
  if (d.action_type === 'move') params.folder_pattern = stripQuotes(d.folder_pattern).trim()
  return {
    action_type: d.action_type,
    conjunction: 'and',
    params,
    active: d.active,
    filters,
  }
}

// ─── Tokens e pré-visualização (D-19) ─────────────────────────────────────────

// Remove aspas (simples/duplas) nas pontas — espelha o strip_quotes do backend (D-21).
function stripQuotes(value: string): string {
  return value.trim().replace(/^["']+|["']+$/g, '')
}

// Sanitiza um valor de exemplo contra caracteres inválidos no Windows (D-08), só para
// a pré-visualização. A autoridade é o backend.
const WINDOWS_INVALID = /[<>:"|?*]/g

// Valor de exemplo de um campo do template (placeholder/hint, ou o nome capitalizado).
function sampleValue(field: { name: string; hint: string | null }): string {
  if (field.hint && field.hint.trim()) return field.hint.trim()
  return field.name
}

// Resolve um padrão {campo} com valores de exemplo dos campos do template (D-19).
function resolvePattern(
  pattern: string,
  fields: { name: string; hint: string | null }[],
): string {
  const byName = new Map(fields.map((f) => [f.name, sampleValue(f)]))
  return pattern.replace(/\{([^}]+)\}/g, (_m, token: string) => {
    const name = String(token).split(':')[0].trim()
    const value = byName.get(name)
    if (value === undefined) return `⟨${name}?⟩`
    return value.replace(WINDOWS_INVALID, '')
  })
}

// ─── Estilos inline reutilizados ──────────────────────────────────────────────

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
  width: '100%',
  height: 36,
  padding: '0 11px',
  border: '1px solid var(--border-strong)',
  borderRadius: 'var(--radius-sm)',
  background: 'var(--surface)',
  color: 'var(--text)',
  fontSize: 13,
  fontFamily: 'inherit',
  outline: 'none',
} as const
const monoInpStyle = { ...inpStyle, fontFamily: 'var(--font-mono)', fontSize: 12.5 } as const
const hintStyle = { fontSize: 11.5, color: 'var(--text-3)', marginTop: 8, lineHeight: 1.5 } as const

export function AutomationsPage() {
  const pipelinesQuery = useAutomations()
  const templatesQuery = useTemplates()
  const createPipeline = useCreatePipeline()
  const updatePipeline = useUpdatePipeline()
  const deletePipeline = useDeletePipeline()

  // Modelo v1: UM pipeline (o primeiro). O construtor edita suas ETAPAS.
  const pipeline = pipelinesQuery.data?.[0] ?? null

  // Rascunho local das etapas (fonte de verdade do editor). Sincronizado com o
  // backend ao carregar/alterar o pipeline. Drag-and-drop e edição mexem aqui;
  // "Salvar pipeline" persiste a lista inteira.
  const [steps, setSteps] = useState<StepDraft[]>([])
  const [dirty, setDirty] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [confirmRemove, setConfirmRemove] = useState<number | null>(null)
  // posição arrastada atualmente (índice) para o feedback visual.
  const dragIndex = useRef<number | null>(null)
  const [dragOver, setDragOver] = useState<number | null>(null)

  // Hidrata o rascunho a partir do backend quando o pipeline carrega/muda, exceto se
  // houver alterações locais não salvas (dirty) — não sobrescreve o trabalho.
  const pipelineSig = pipeline
    ? `${pipeline.id}:${pipeline.steps.map((s) => `${s.id}@${s.position}`).join(',')}`
    : 'none'
  useEffect(() => {
    if (dirty) return
    if (pipeline) {
      const ordered = [...pipeline.steps].sort((a, b) => a.position - b.position)
      setSteps(ordered.map(persistedToDraft))
    } else {
      setSteps([])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineSig])

  const templates = templatesQuery.data ?? []

  // D-19: o template "vigente" do pipeline = o do PRIMEIRO gate "Identificar tipo".
  // Os chips de campo (renomear/mover) vêm dos campos desse template.
  const activeTemplate: Template | null = useMemo(() => {
    const gate = steps.find((s) => s.action_type === 'identify_type' && s.template_id.trim())
    if (!gate) return null
    return templates.find((t) => String(t.id) === gate.template_id) ?? null
  }, [steps, templates])

  const isInitialLoading = pipelinesQuery.isLoading && !pipelinesQuery.data
  const isError = pipelinesQuery.isError && !pipelinesQuery.data
  const isEmpty = !isInitialLoading && !isError && steps.length === 0

  const saving = createPipeline.isPending || updatePipeline.isPending
  const busy = saving || deletePipeline.isPending

  // ── Mutadores do rascunho ──
  const patchStep = (key: number, patch: Partial<StepDraft>) => {
    setSteps((list) => list.map((s) => (s.key === key ? { ...s, ...patch } : s)))
    setDirty(true)
    setFormError(null)
  }

  const addStep = (action: EditableAction) => {
    setSteps((list) => [...list, newStepDraft(action)])
    setDirty(true)
    setFormError(null)
  }

  const removeStep = (index: number) => {
    setSteps((list) => list.filter((_, i) => i !== index))
    setDirty(true)
    setConfirmRemove(null)
  }

  // Reordenação por botões ↑/↓ (acessibilidade, D-20).
  const moveStep = (index: number, dir: -1 | 1) => {
    const j = index + dir
    if (j < 0 || j >= steps.length) return
    setSteps((list) => {
      const next = list.slice()
      ;[next[index], next[j]] = [next[j], next[index]]
      return next
    })
    setDirty(true)
  }

  // ── Drag-and-drop nativo (HTML5, sem libs — D-20) ──
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
    if (from == null || from === index) return
    setSteps((list) => {
      const next = list.slice()
      const [moved] = next.splice(from, 1)
      next.splice(index, 0, moved)
      return next
    })
    setDirty(true)
  }
  const onDragEnd = () => {
    dragIndex.current = null
    setDragOver(null)
  }

  // ── Persistência: valida e salva a lista inteira de etapas (D-12) ──
  const validate = (): string | null => {
    for (const s of steps) {
      if (s.action_type === 'identify_file' && !s.extensions.trim()) {
        return 'Em "Identificar arquivo", informe ao menos uma extensão (ex.: .pdf, .xlsx).'
      }
      if (s.action_type === 'identify_type' && !s.template_id.trim()) {
        return 'Em "Identificar tipo", escolha um template.'
      }
      if (s.action_type === 'rename' && !s.name_pattern.trim()) {
        return 'Em "Renomear", defina o padrão do nome (use os campos do template).'
      }
      if (s.action_type === 'move' && !stripQuotes(s.folder_pattern).trim()) {
        return 'Em "Mover", defina a pasta de destino.'
      }
    }
    return null
  }

  const save = () => {
    const err = validate()
    if (err) {
      setFormError(err)
      return
    }
    setFormError(null)
    const body = steps.map(draftToCreate)
    const onSuccess = () => setDirty(false)
    const onError = () =>
      setFormError('Não foi possível salvar o pipeline. Confira os dados e tente novamente.')
    if (pipeline) {
      updatePipeline.mutate({ id: pipeline.id, body: { steps: body } }, { onSuccess, onError })
    } else {
      createPipeline.mutate(
        { name: 'Pipeline de automação', active: true, steps: body },
        { onSuccess, onError },
      )
    }
  }

  const discard = () => {
    setDirty(false)
    setFormError(null)
    if (pipeline) {
      const ordered = [...pipeline.steps].sort((a, b) => a.position - b.position)
      setSteps(ordered.map(persistedToDraft))
    } else {
      setSteps([])
    }
  }

  // Liga/desliga o pipeline inteiro (header switch). Persiste direto.
  const togglePipelineActive = () => {
    if (!pipeline) return
    updatePipeline.mutate({ id: pipeline.id, body: { active: !pipeline.active } })
  }

  // Insere um token {campo} no fim do padrão da etapa (D-19).
  const insertToken = (key: number, field: 'name_pattern' | 'folder_pattern', token: string) => {
    setSteps((list) =>
      list.map((s) => (s.key === key ? { ...s, [field]: `${s[field]}{${token}}` } : s)),
    )
    setDirty(true)
  }

  // ─── Render de UMA etapa (card) ─────────────────────────────────────────────
  const renderStep = (s: StepDraft, index: number) => {
    const meta = ACTION_META[s.action_type]
    const isOver = dragOver === index
    return (
      <div
        key={s.key}
        className="card"
        draggable
        onDragStart={onDragStart(index)}
        onDragOver={onDragOver(index)}
        onDrop={onDrop(index)}
        onDragEnd={onDragEnd}
        style={{
          position: 'relative',
          padding: '14px 14px 14px 64px',
          background: 'var(--surface-2)',
          opacity: s.active ? 1 : 0.5,
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
            left: 12,
            top: 14,
            width: 20,
            color: 'var(--text-3)',
            cursor: 'grab',
            fontSize: 15,
            lineHeight: 1,
            userSelect: 'none',
          }}
        >
          ⠿
        </div>
        {/* número da etapa */}
        <span
          className="chip-count"
          style={{
            position: 'absolute',
            left: 34,
            top: 14,
            width: 24,
            height: 24,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'var(--accent-soft)',
            color: 'var(--accent)',
            borderRadius: 7,
          }}
        >
          {index + 1}
        </span>

        {/* topo: tipo + ações ↑/↓/✕ */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 10 }}>
          <span
            style={{
              width: 22,
              height: 22,
              borderRadius: 6,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: meta.dot,
              color: '#fff',
              flex: 'none',
            }}
          >
            <Icon name={meta.icon} size={13} stroke="#fff" />
          </span>
          <span style={{ fontSize: 13, fontWeight: 700 }}>{meta.label}</span>
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 4 }}>
            <Switch
              on={s.active}
              onToggle={() => patchStep(s.key, { active: !s.active })}
              title={s.active ? 'Pausar etapa' : 'Ativar etapa'}
            />
            <button
              className="row-action"
              aria-label="Mover etapa para cima"
              title="Mover etapa para cima"
              disabled={index === 0}
              onClick={() => moveStep(index, -1)}
              style={{ opacity: index === 0 ? 0.35 : 1 }}
            >
              <Icon name="arrowUp" size={15} />
            </button>
            <button
              className="row-action"
              aria-label="Mover etapa para baixo"
              title="Mover etapa para baixo"
              disabled={index === steps.length - 1}
              onClick={() => moveStep(index, 1)}
              style={{ opacity: index === steps.length - 1 ? 0.35 : 1 }}
            >
              <Icon name="arrowDown" size={15} />
            </button>
            <button
              className="row-action"
              aria-label="Remover etapa"
              title="Remover etapa"
              style={{ color: 'var(--st-erro)' }}
              onClick={() => setConfirmRemove(index)}
            >
              <Icon name="alert" size={15} />
            </button>
          </div>
        </div>

        {/* corpo conforme a ação */}
        {s.action_type === 'identify_file' && (
          <>
            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: 210 }}>
                <span style={lblStyle}>Tipo de arquivo (extensão)</span>
                <input
                  className="cell-mono"
                  style={monoInpStyle}
                  placeholder=".pdf, .xlsx"
                  value={s.extensions}
                  onChange={(e) => patchStep(s.key, { extensions: e.target.value })}
                />
              </div>
              <div style={{ flex: 1, minWidth: 210 }}>
                <span style={lblStyle}>Pasta de origem (opcional)</span>
                <input
                  className="cell-mono"
                  style={monoInpStyle}
                  placeholder="Downloads/"
                  value={s.source_folder}
                  onChange={(e) => patchStep(s.key, { source_folder: e.target.value })}
                  onBlur={(e) => patchStep(s.key, { source_folder: stripQuotes(e.target.value) })}
                />
              </div>
            </div>
            <div style={hintStyle}>
              Porteiro independente do template: só seguem os arquivos com essas extensões. Digite
              uma ou mais, separadas por vírgula (ex.: <code>.pdf, .xlsx</code>). Se não casar, o
              documento para aqui.
            </div>
          </>
        )}

        {s.action_type === 'identify_type' && (
          <>
            <div style={{ maxWidth: 320 }}>
              <span style={lblStyle}>Template</span>
              <select
                className="select"
                style={{ width: '100%' }}
                value={s.template_id}
                onChange={(e) => patchStep(s.key, { template_id: e.target.value })}
              >
                <option value="">Escolha um template…</option>
                {templates.map((t) => (
                  <option key={t.id} value={String(t.id)}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>
            <div style={hintStyle}>
              Porteiro por <b>conteúdo</b>: só seguem os documentos identificados com esse template.
              Os campos disponíveis para renomear/mover passam a ser os <b>campos desse template</b>.
              {templates.length === 0 && (
                <> Nenhum template cadastrado ainda — crie um na aba Templates.</>
              )}
            </div>
          </>
        )}

        {s.action_type === 'rename' && (
          <>
            <span style={lblStyle}>Padrão do nome</span>
            <input
              className="cell-mono"
              style={monoInpStyle}
              placeholder="{cliente}_{numero}"
              value={s.name_pattern}
              onChange={(e) => patchStep(s.key, { name_pattern: e.target.value })}
            />
            {renderTokenBar(s, 'name_pattern')}
            {renderPreview(s.name_pattern, 'name')}
            <div style={hintStyle}>
              <code>{'{campo}'}</code> é trocado pelo <b>valor lido do documento</b>. Os campos vêm
              do template do gate "Identificar tipo" — não são fixos; mudam conforme você cria/edita
              templates.
            </div>
          </>
        )}

        {s.action_type === 'move' && (
          <>
            <span style={lblStyle}>
              Pasta de destino{' '}
              <span style={{ textTransform: 'none', letterSpacing: 0, color: 'var(--text-3)' }}>
                — aceita com ou sem aspas
              </span>
            </span>
            <input
              className="cell-mono"
              style={monoInpStyle}
              placeholder="Documentos/{cliente}/{data}/"
              value={s.folder_pattern}
              onChange={(e) => patchStep(s.key, { folder_pattern: e.target.value })}
              onBlur={(e) => patchStep(s.key, { folder_pattern: stripQuotes(e.target.value) })}
            />
            {renderTokenBar(s, 'folder_pattern')}
            {renderPreview(s.folder_pattern, 'folder')}
            <div style={hintStyle}>
              Cole o caminho como vier do Windows — <code>"C:\Users\…\Análise"</code> ou{' '}
              <code>C:\Users\…\Análise</code>: as aspas são removidas automaticamente ao sair do
              campo.
            </div>
          </>
        )}
      </div>
    )
  }

  // Barra de chips de token = campos do template vigente (D-19). Sem template no
  // pipeline, não há chips (coerente).
  const renderTokenBar = (s: StepDraft, field: 'name_pattern' | 'folder_pattern') => {
    if (!activeTemplate) {
      return (
        <div
          style={{
            marginTop: 11,
            background: 'var(--surface-3)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            padding: '10px 11px',
            fontSize: 11.5,
            color: 'var(--text-3)',
          }}
        >
          Adicione um gate <b>Identificar tipo</b> com um template para ver os campos disponíveis
          como chips.
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
          Campos do template <b style={{ color: 'var(--accent)' }}>{activeTemplate.name}</b> — clique
          para inserir:
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
              onClick={() => insertToken(s.key, field, f.name)}
            >
              <span style={{ color: 'var(--text-3)', fontWeight: 700 }}>+</span> {`{${f.name}}`}
            </button>
          ))}
        </div>
      </div>
    )
  }

  // Pré-visualização ao vivo do padrão resolvido com valores de exemplo (D-19).
  const renderPreview = (pattern: string, kind: 'name' | 'folder') => {
    if (!pattern.trim() || !activeTemplate) return null
    const out = resolvePattern(pattern, activeTemplate.fields) + (kind === 'name' ? '.pdf' : '')
    const color = kind === 'name' ? 'var(--st-tratado)' : 'var(--st-encontrado)'
    const bg = kind === 'name' ? 'var(--st-tratado-bg)' : 'var(--st-encontrado-bg)'
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

  return (
    <div>
      <div className="sec-head">
        <div className="sec-head-col">
          <h2 className="sec-title">Automações</h2>
          <p className="sec-desc">
            Monte um pipeline de etapas que decidem o que fazer com cada documento. Cada documento
            passa pelas etapas, de cima para baixo, na ordem que você definir — arraste pela alça ⠿
            para reordenar.
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
          <button className="btn-primary" onClick={() => pipelinesQuery.refetch()}>
            <Icon name="refresh" size={15} />
            Tentar de novo
          </button>
        </div>
      )}

      {/* Pipeline card */}
      {!isInitialLoading && !isError && (
        <div className="card" style={{ marginBottom: 18 }}>
          {/* cabeçalho do pipeline: nome + estado + switch */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '15px 18px',
              borderBottom: '1px solid var(--border)',
            }}
          >
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 14.5, fontWeight: 700, letterSpacing: '-.2px' }}>
                {pipeline?.name ?? 'Pipeline de automação'}
              </div>
              <div style={{ fontSize: 11.5, color: 'var(--text-3)', marginTop: 1 }}>
                {steps.length} etapa{steps.length === 1 ? '' : 's'} · aplicado automaticamente em
                documentos de alta confiança
              </div>
            </div>
            {pipeline && (
              <>
                <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
                  {pipeline.active ? 'Ativo' : 'Pausado'}
                </span>
                <Switch
                  on={pipeline.active}
                  onToggle={togglePipelineActive}
                  title={pipeline.active ? 'Pausar pipeline' : 'Ativar pipeline'}
                />
              </>
            )}
          </div>

          <div style={{ padding: 18 }}>
            {/* Empty state */}
            {isEmpty && (
              <div style={{ padding: '36px 24px', textAlign: 'center' }}>
                <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>
                  Nenhuma etapa ainda
                </div>
                <p
                  style={{
                    fontSize: 13,
                    color: 'var(--text-3)',
                    margin: '0 auto 4px',
                    maxWidth: 520,
                  }}
                >
                  Comece adicionando etapas abaixo — ex.: 1) Identificar arquivo (só PDFs) → 2)
                  Identificar tipo → 3) Renomear → 4) Mover para a pasta certa.
                </p>
              </div>
            )}

            {/* Lista ORDENADA de etapas com conector descendente */}
            {steps.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 24, marginBottom: 8 }}>
                {steps.map((s, idx) => (
                  <div key={s.key} style={{ position: 'relative' }}>
                    {renderStep(s, idx)}
                    {idx < steps.length - 1 && (
                      <div
                        aria-hidden
                        style={{
                          position: 'absolute',
                          left: 33,
                          bottom: -20,
                          transform: 'translateX(-50%)',
                          color: 'var(--text-3)',
                          fontSize: 15,
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

            {/* Adicionar etapa: 4 ações (mockup .addstep) */}
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: steps.length ? 18 : 0 }}>
              {ACTIONS.map((a) => (
                <button
                  key={a.value}
                  type="button"
                  onClick={() => addStep(a.value)}
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
                    style={{ width: 8, height: 8, borderRadius: 3, background: a.dot, flex: 'none' }}
                  />
                  {a.label}
                </button>
              ))}
            </div>

            {formError && (
              <p style={{ fontSize: 13, color: 'var(--st-erro)', margin: '14px 0 0' }}>{formError}</p>
            )}

            {/* Barra de salvar (aparece quando há alterações não salvas) */}
            {dirty && (
              <div
                style={{
                  display: 'flex',
                  gap: 8,
                  justifyContent: 'flex-end',
                  alignItems: 'center',
                  marginTop: 18,
                  paddingTop: 16,
                  borderTop: '1px solid var(--border)',
                }}
              >
                <span style={{ fontSize: 12, color: 'var(--text-3)', marginRight: 'auto' }}>
                  Alterações não salvas
                </span>
                <button className="btn-ghost" onClick={discard} disabled={busy}>
                  Descartar
                </button>
                <button className="btn-primary" onClick={save} disabled={busy}>
                  {saving ? 'Salvando…' : 'Salvar pipeline'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      <div style={{ textAlign: 'center', fontSize: 12, color: 'var(--text-3)', marginTop: 8 }}>
        Reordenação por arraste (HTML nativo) + botões ↑/↓ para acessibilidade. A ação "Decidir
        tratativa" não faz parte do v1.
      </div>

      {/* Confirmação de remoção de etapa (reversível, sem linguagem destrutiva) */}
      {confirmRemove != null && steps[confirmRemove] && (
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
              Remover etapa
            </h3>
            <p style={{ fontSize: 13, color: 'var(--text-2)', margin: '0 0 18px' }}>
              Remover a etapa <b>«{actionLabel(steps[confirmRemove].action_type)}»</b>? As etapas
              seguintes continuam valendo. Salve o pipeline para confirmar.
            </p>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn-ghost" onClick={() => setConfirmRemove(null)}>
                Manter etapa
              </button>
              <button
                className="btn-primary"
                style={{ background: 'var(--st-erro)' }}
                onClick={() => removeStep(confirmRemove)}
              >
                Remover
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
