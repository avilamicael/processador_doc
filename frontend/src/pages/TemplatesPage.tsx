import { useState } from 'react'
import type { FieldType, Template, TemplateFieldCreate } from '../types'
import { Icon } from '../components/Icon'
import { Switch } from '../components/Switch'
import {
  useCreateTemplate,
  useDeleteTemplate,
  useTemplates,
  useUpdateTemplate,
} from '../hooks/useTemplates'

// Tipos de campo do construtor (D-08) — label pt-BR (UI-SPEC) → valor da API.
const FIELD_TYPES: { value: FieldType; label: string }[] = [
  { value: 'texto', label: 'Texto' },
  { value: 'numero', label: 'Número' },
  { value: 'data', label: 'Data' },
  { value: 'moeda', label: 'Moeda' },
  { value: 'cpf_cnpj', label: 'CPF/CNPJ' },
  { value: 'booleano', label: 'Booleano' },
]

// Hint inline por tipo de campo (UI-SPEC microcopy do construtor).
const FIELD_TYPE_HINT: Partial<Record<FieldType, string>> = {
  cpf_cnpj: 'Valida o dígito verificador (Módulo 11) e normaliza para apenas dígitos.',
  data: 'Normaliza para o formato ISO AAAA-MM-DD.',
  moeda: 'Normaliza para valor decimal.',
}

// Estado de um campo dentro do form (mesma forma do body da API + chave local p/ React).
type FieldDraft = TemplateFieldCreate & { key: number }

// Estado controlado do construtor (S2). `id` null = criação; preenchido = edição.
type FormState = {
  id: number | null
  name: string
  doc_type: string
  signals: string
  fields: FieldDraft[]
}

let nextFieldKey = 1
const newField = (): FieldDraft => ({
  key: nextFieldKey++,
  name: '',
  field_type: 'texto',
  required: false,
  regex: null,
  hint: null,
})

const labelStyle = { fontSize: 12, fontWeight: 600, color: 'var(--text-2)' } as const
const hintStyle = { fontSize: 12, color: 'var(--text-3)' } as const

export function TemplatesPage() {
  const templatesQuery = useTemplates()
  const createTemplate = useCreateTemplate()
  const updateTemplate = useUpdateTemplate()
  const deleteTemplate = useDeleteTemplate()

  const [form, setForm] = useState<FormState | null>(null)
  const [confirmRemove, setConfirmRemove] = useState<Template | null>(null)
  const [formError, setFormError] = useState<string | null>(null)

  const templates = templatesQuery.data ?? []

  // Estados de tela (UI-SPEC Interaction States).
  const isInitialLoading = templatesQuery.isLoading && !templatesQuery.data
  const isError = templatesQuery.isError && !templatesQuery.data
  const isEmpty = !isInitialLoading && !isError && templates.length === 0

  const saving = createTemplate.isPending || updateTemplate.isPending

  const openAdd = () => {
    setFormError(null)
    setForm({ id: null, name: '', doc_type: '', signals: '', fields: [newField()] })
  }

  const openEdit = (t: Template) => {
    setFormError(null)
    setForm({
      id: t.id,
      name: t.name,
      doc_type: t.doc_type ?? '',
      signals: t.signals.join(', '),
      fields: t.fields.map((f) => ({
        key: nextFieldKey++,
        name: f.name,
        field_type: f.field_type,
        required: f.required,
        regex: f.regex,
        hint: f.hint,
      })),
    })
  }

  const closeForm = () => {
    setForm(null)
    setFormError(null)
  }

  const patchField = (key: number, patch: Partial<FieldDraft>) => {
    if (!form) return
    setForm({
      ...form,
      fields: form.fields.map((f) => (f.key === key ? { ...f, ...patch } : f)),
    })
  }

  const addField = () => {
    if (!form) return
    setForm({ ...form, fields: [...form.fields, newField()] })
  }

  const removeField = (key: number) => {
    if (!form) return
    setForm({ ...form, fields: form.fields.filter((f) => f.key !== key) })
  }

  const submitForm = () => {
    if (!form) return
    const name = form.name.trim()
    if (!name) {
      setFormError('Informe o nome do template.')
      return
    }
    if (form.fields.length === 0) {
      setFormError('Adicione ao menos um campo ao template.')
      return
    }
    if (form.fields.some((f) => !f.name.trim())) {
      setFormError('Informe o nome do campo.')
      return
    }
    setFormError(null)

    const signals = form.signals
      .split(/[,\n]/)
      .map((s) => s.trim())
      .filter((s) => s !== '')
    const doc_type = form.doc_type.trim() === '' ? null : form.doc_type.trim()
    const fields: TemplateFieldCreate[] = form.fields.map((f) => ({
      name: f.name.trim(),
      field_type: f.field_type,
      required: f.required,
      regex: f.regex && f.regex.trim() !== '' ? f.regex.trim() : null,
      hint: f.hint && f.hint.trim() !== '' ? f.hint.trim() : null,
    }))

    const onError = () =>
      setFormError('Não foi possível salvar o template. Confira os dados e tente novamente.')

    if (form.id == null) {
      createTemplate.mutate(
        { name, doc_type, signals, fields },
        { onSuccess: closeForm, onError },
      )
    } else {
      updateTemplate.mutate(
        { id: form.id, body: { name, doc_type, signals, fields } },
        { onSuccess: closeForm, onError },
      )
    }
  }

  const confirmDelete = () => {
    if (!confirmRemove) return
    deleteTemplate.mutate(confirmRemove.id, { onSettled: () => setConfirmRemove(null) })
  }

  return (
    <div>
      <div className="sec-head">
        <div className="sec-head-col">
          <h2 className="sec-title">Templates de documento</h2>
          <p className="sec-desc">
            Cada template define o tipo de documento e os campos extraídos pelo motor de leitura.
          </p>
        </div>
        <button className="btn-primary" onClick={openAdd}>
          <Icon name="plus" size={15} />
          Novo template
        </button>
      </div>

      {/* S2 — Construtor schema-first (form inline, molde PastasTab) */}
      {form && (
        <div className="card" style={{ padding: 18, marginBottom: 16 }}>
          <h3 className="sec-title" style={{ fontSize: 14, marginBottom: 14 }}>
            {form.id == null ? 'Novo template' : 'Editar template'}
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span style={labelStyle}>Nome do template</span>
              <input
                className="search-input"
                style={{ width: '100%' }}
                placeholder="ex.: Nota Fiscal Eletrônica"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </label>

            <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span style={labelStyle}>Tipo de documento</span>
              <input
                className="search-input"
                style={{ width: '100%' }}
                placeholder="ex.: Fiscal, RH, Financeiro"
                value={form.doc_type}
                onChange={(e) => setForm({ ...form, doc_type: e.target.value })}
              />
            </label>

            <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span style={labelStyle}>Sinais identificadores</span>
              <input
                className="search-input"
                style={{ width: '100%', fontFamily: 'var(--font-mono)' }}
                placeholder="linha digitável, CNPJ, valor total"
                value={form.signals}
                onChange={(e) => setForm({ ...form, signals: e.target.value })}
              />
              <span style={hintStyle}>
                Dados cuja presença identifica este tipo (ex.: linha digitável, CNPJ, valor
                total). Usados para classificar antes de recorrer à IA.
              </span>
            </label>

            {/* Lista de campos do template */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <span style={labelStyle}>Campos extraídos</span>
              {form.fields.map((f, idx) => (
                <div
                  key={f.key}
                  className="card"
                  style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 12 }}
                >
                  <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end' }}>
                    <label style={{ display: 'flex', flexDirection: 'column', gap: 6, flex: 1, minWidth: 0 }}>
                      <span style={labelStyle}>Nome do campo</span>
                      <input
                        className="search-input"
                        style={{ width: '100%' }}
                        placeholder="ex.: CNPJ emitente"
                        value={f.name}
                        onChange={(e) => patchField(f.key, { name: e.target.value })}
                      />
                    </label>
                    <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      <span style={labelStyle}>Tipo</span>
                      <select
                        className="select"
                        value={f.field_type}
                        onChange={(e) =>
                          patchField(f.key, { field_type: e.target.value as FieldType })
                        }
                      >
                        {FIELD_TYPES.map((ft) => (
                          <option key={ft.value} value={ft.value}>
                            {ft.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'center' }}>
                      <span style={labelStyle}>Obrigatório</span>
                      <Switch
                        on={f.required}
                        onToggle={() => patchField(f.key, { required: !f.required })}
                        title="Campo obrigatório"
                      />
                    </div>
                    <button
                      className="row-action"
                      aria-label={`Remover campo ${f.name || idx + 1}`}
                      title="Remover campo"
                      style={{ color: 'var(--st-erro)' }}
                      onClick={() => removeField(f.key)}
                    >
                      ✕
                    </button>
                  </div>

                  {FIELD_TYPE_HINT[f.field_type] && (
                    <span style={hintStyle}>{FIELD_TYPE_HINT[f.field_type]}</span>
                  )}

                  <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <span style={labelStyle}>Validação por padrão (regex)</span>
                    <input
                      className="search-input"
                      style={{ width: '100%', fontFamily: 'var(--font-mono)' }}
                      placeholder="Opcional"
                      value={f.regex ?? ''}
                      onChange={(e) => patchField(f.key, { regex: e.target.value })}
                    />
                    <span style={hintStyle}>
                      Opcional. Valida o valor extraído contra uma expressão regular.
                    </span>
                  </label>

                  <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <span style={labelStyle}>Dica para a leitura</span>
                    <input
                      className="search-input"
                      style={{ width: '100%' }}
                      placeholder="ex.: número após o rótulo «Nº NF»"
                      value={f.hint ?? ''}
                      onChange={(e) => patchField(f.key, { hint: e.target.value })}
                    />
                    <span style={hintStyle}>
                      Texto que orienta a IA a encontrar este campo no documento (ex.: número
                      após o rótulo «Nº NF»).
                    </span>
                  </label>
                </div>
              ))}

              <button className="btn-ghost" onClick={addField} style={{ alignSelf: 'flex-start' }}>
                <Icon name="plus" size={15} />
                Adicionar campo
              </button>
            </div>

            {formError && (
              <p style={{ fontSize: 13, color: 'var(--st-erro)', margin: 0 }}>{formError}</p>
            )}

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn-ghost" onClick={closeForm} disabled={saving}>
                {form.id == null ? 'Descartar template' : 'Descartar alterações'}
              </button>
              <button className="btn-primary" onClick={submitForm} disabled={saving}>
                {saving
                  ? 'Salvando…'
                  : form.id == null
                    ? 'Salvar template'
                    : 'Salvar alterações'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* S1 — Loading (skeleton em cards) */}
      {isInitialLoading && (
        <div className="tpl-grid">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={`sk-${i}`} className="card tpl-card">
              <div
                style={{ height: 96, borderRadius: 8, background: 'var(--surface-3)', opacity: 0.7 }}
              />
            </div>
          ))}
        </div>
      )}

      {/* S1 — Erro */}
      {isError && (
        <div className="card" style={{ padding: '48px 24px', textAlign: 'center' }}>
          <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>
            Não foi possível carregar os templates.
          </div>
          <p style={{ fontSize: 13, color: 'var(--text-3)', margin: '0 0 16px' }}>
            Verifique se o serviço está em execução e tente novamente.
          </p>
          <button className="btn-primary" onClick={() => templatesQuery.refetch()}>
            <Icon name="refresh" size={15} />
            Tentar novamente
          </button>
        </div>
      )}

      {/* S1 — Vazio */}
      {isEmpty && !form && (
        <div className="card" style={{ padding: '48px 24px', textAlign: 'center' }}>
          <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>
            Nenhum template ainda
          </div>
          <p
            style={{
              fontSize: 13,
              color: 'var(--text-3)',
              margin: 0,
              maxWidth: 460,
              marginInline: 'auto',
            }}
          >
            Crie um template declarando os campos a extrair de um tipo de documento. O sistema usa
            os templates para classificar e preencher cada documento automaticamente.
          </p>
        </div>
      )}

      {/* S1 — Grid de templates */}
      {!isInitialLoading && !isError && templates.length > 0 && (
        <div className="tpl-grid">
          {templates.map((t) => (
            <div key={t.id} className="card tpl-card">
              <div className="tpl-head">
                <div className="tpl-head-info">
                  <div className="tpl-icon">
                    <Icon name="grid" size={19} />
                  </div>
                  <div>
                    <div className="tpl-name">{t.name}</div>
                    <div className="tpl-type">{t.doc_type ?? 'Sem tipo'}</div>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 4 }}>
                  <button
                    className="row-action"
                    title="Editar template"
                    aria-label={`Editar template ${t.name}`}
                    onClick={() => openEdit(t)}
                  >
                    <Icon name="dots" size={16} />
                  </button>
                  <button
                    className="row-action"
                    title="Remover template"
                    aria-label={`Remover template ${t.name}`}
                    style={{ color: 'var(--st-erro)' }}
                    onClick={() => setConfirmRemove(t)}
                  >
                    ✕
                  </button>
                </div>
              </div>

              <div className="tpl-fields-label">CAMPOS EXTRAÍDOS</div>
              <div className="tags">
                {t.fields.map((f) => (
                  <span key={f.id} className="tag">
                    {f.name}
                  </span>
                ))}
              </div>

              <div className="tpl-foot">
                <span>
                  <Icon name="tableMini" size={13} />
                  {t.fields.length} {t.fields.length === 1 ? 'campo' : 'campos'}
                </span>
                {t.signals.length > 0 && (
                  <span>
                    <Icon name="checkSmall" size={13} />
                    {t.signals.length} {t.signals.length === 1 ? 'sinal' : 'sinais'}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* S3 — Confirmação destrutiva de remoção */}
      {confirmRemove && (
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
              Remover template
            </h3>
            <p style={{ fontSize: 13, color: 'var(--text-2)', margin: '0 0 18px' }}>
              Remover o template{' '}
              <b style={{ fontFamily: 'var(--font-mono)' }}>«{confirmRemove.name}»</b>? Os
              documentos já classificados por ele permanecem; novos documentos deixarão de casar
              com este template.
            </p>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button
                className="btn-ghost"
                onClick={() => setConfirmRemove(null)}
                disabled={deleteTemplate.isPending}
              >
                Manter template
              </button>
              <button
                className="btn-primary"
                style={{ background: 'var(--st-erro)' }}
                onClick={confirmDelete}
                disabled={deleteTemplate.isPending}
              >
                {deleteTemplate.isPending ? 'Removendo…' : 'Remover'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
