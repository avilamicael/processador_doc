import { useState } from 'react'
import type {
  FieldType,
  SignalCondition,
  SignalGroup,
  SignalMode,
  Signals,
  Template,
  TemplateFieldCreate,
} from '../types'
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
  { value: 'texto', label: 'texto' },
  { value: 'numero', label: 'número' },
  { value: 'data', label: 'data' },
  { value: 'moeda', label: 'moeda' },
  { value: 'cpf_cnpj', label: 'CPF/CNPJ' },
  { value: 'booleano', label: 'booleano' },
]

// --- Drafts com chave local p/ React (espelha o padrão FieldDraft & { key }) ---

// Condição de sinal no form (mode/value + chave React estável).
type CondDraft = SignalCondition & { key: number }
// Grupo de condições (combinadas por E) + chave React estável.
type GroupDraft = { key: number; conds: CondDraft[] }
// Campo a extrair no form (body da API + chave React + flag de "Avançado" aberto).
type FieldDraft = TemplateFieldCreate & { key: number; advOpen: boolean }

// Estado controlado do construtor. `id` null = criação; preenchido = edição.
// NÃO há "tipo de documento" (D-T5 — campo removido do formulário).
type FormState = {
  id: number | null
  name: string
  groups: GroupDraft[]
  fields: FieldDraft[]
}

let nextKey = 1
const k = () => nextKey++

const newCond = (mode: SignalMode = 'texto', value = ''): CondDraft => ({
  key: k(),
  mode,
  value,
})
const newGroup = (): GroupDraft => ({ key: k(), conds: [newCond()] })
const newField = (): FieldDraft => ({
  key: k(),
  name: '',
  field_type: 'texto',
  required: false,
  regex: null,
  hint: null,
  advOpen: false,
})

// Converte os grupos da API (Signals) em drafts com chave local.
const groupsToDrafts = (signals: Signals): GroupDraft[] => {
  if (signals.length === 0) return [newGroup()]
  return signals.map((g) => ({
    key: k(),
    conds:
      g.length === 0
        ? [newCond()]
        : g.map((c) => ({ key: k(), mode: c.mode, value: c.value })),
  }))
}

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
    setForm({ id: null, name: '', groups: [newGroup()], fields: [newField()] })
  }

  const openEdit = (t: Template) => {
    setFormError(null)
    setForm({
      id: t.id,
      name: t.name,
      groups: groupsToDrafts(t.signals),
      fields: t.fields.map((f) => ({
        key: k(),
        name: f.name,
        field_type: f.field_type,
        required: f.required,
        regex: f.regex,
        hint: f.hint,
        advOpen: false,
      })),
    })
  }

  const closeForm = () => {
    setForm(null)
    setFormError(null)
  }

  // --- Handlers imutáveis de GRUPOS / CONDIÇÕES (estilo patchField) ---

  const addGroup = () => {
    if (!form) return
    setForm({ ...form, groups: [...form.groups, newGroup()] })
  }

  const addCond = (gKey: number) => {
    if (!form) return
    setForm({
      ...form,
      groups: form.groups.map((g) =>
        g.key === gKey ? { ...g, conds: [...g.conds, newCond()] } : g,
      ),
    })
  }

  const patchCond = (gKey: number, cKey: number, patch: Partial<SignalCondition>) => {
    if (!form) return
    setForm({
      ...form,
      groups: form.groups.map((g) =>
        g.key === gKey
          ? {
              ...g,
              conds: g.conds.map((c) => (c.key === cKey ? { ...c, ...patch } : c)),
            }
          : g,
      ),
    })
  }

  // Remove a condição; se o grupo ficar vazio, remove o grupo inteiro.
  const removeCond = (gKey: number, cKey: number) => {
    if (!form) return
    const groups = form.groups
      .map((g) =>
        g.key === gKey ? { ...g, conds: g.conds.filter((c) => c.key !== cKey) } : g,
      )
      .filter((g) => g.conds.length > 0)
    setForm({ ...form, groups })
  }

  // --- Handlers imutáveis de CAMPOS ---

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

    // Sinais: descarta condições vazias e grupos sem condição. Pode ficar [].
    const signals: Signals = form.groups
      .map<SignalGroup>((g) =>
        g.conds
          .filter((c) => c.value.trim() !== '')
          .map<SignalCondition>((c) => ({ mode: c.mode, value: c.value.trim() })),
      )
      .filter((g) => g.length > 0)

    // field.name enviado EXATAMENTE como digitado (sem snake_case — D-T6/D-T9).
    const fields: TemplateFieldCreate[] = form.fields.map((f) => ({
      name: f.name.trim(),
      field_type: f.field_type,
      required: f.required,
      regex: f.regex && f.regex.trim() !== '' ? f.regex.trim() : null,
      hint: f.hint && f.hint.trim() !== '' ? f.hint.trim() : null,
    }))

    const onError = () =>
      setFormError('Não foi possível salvar o template. Confira os dados e tente novamente.')

    // Payload sem o campo "tipo de documento" (D-T5 — coluna dormente, fora do form).
    if (form.id == null) {
      createTemplate.mutate({ name, signals, fields }, { onSuccess: closeForm, onError })
    } else {
      updateTemplate.mutate(
        { id: form.id, body: { name, signals, fields } },
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
            Defina um tipo de documento: como reconhecê-lo (Passo 1, sem IA) e o que extrair
            (Passo 2, com IA).
          </p>
        </div>
        <button className="btn-primary" onClick={openAdd}>
          <Icon name="plus" size={15} />
          Novo template
        </button>
      </div>

      {/* Construtor (form inline) — pipeline explícito Passo 1 / Passo 2 (D-T0) */}
      {form && (
        <div className="card" style={{ marginBottom: 16 }}>
          {/* Nome do template */}
          <div className="tpl-sec">
            <div className="tpl-sec-t">
              {form.id == null ? 'Nome do template' : 'Editar template'}
              <span className="info">
                i
                <span className="tip">
                  Como este tipo aparece no app (ex.: <b>Holerite</b>, <b>Nota Fiscal</b>). É
                  também o nome que você seleciona nas automações.
                </span>
              </span>
            </div>
            <div style={{ marginTop: 10 }}>
              <input
                className="tpl-inp"
                placeholder="ex.: Nota Fiscal, Nota Fiscal — TryLab"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
          </div>

          {/* Passo 1 — SINAIS (sem IA) — grupos E/OU (D-T3/D-T4) */}
          <div className="tpl-sec">
            <div className="tpl-sec-t">
              Como reconhecer este tipo <span className="sec-tag t-noai">sem IA</span>
              <span className="info">
                i
                <span className="tip">
                  <b>Passo 1 — sem IA, de graça.</b> O sistema procura estes sinais no texto do
                  documento. Bateu na lógica abaixo → é deste tipo. Em dúvida → vai para{' '}
                  <b>revisão humana</b> (nada se perde).
                </span>
              </span>
            </div>
            <div className="tpl-sec-mini">
              O documento é deste tipo se bater em <b>qualquer grupo (OU)</b>; dentro do grupo,{' '}
              <b>todas</b> as condições (E).
              <span className="info">
                i
                <span className="tip">
                  <b>Cada condição é uma busca no documento:</b>
                  <br />• <b>contém o texto</b> = procura essa palavra/frase <b>dentro do
                  documento</b> (ex.: <code>DANFE</code>, ou o nome <code>TryLab</code>).
                  <br />• <b>corresponde ao padrão (regex)</b> = um “molde” para formatos que{' '}
                  <b>variam</b>. Ex.: <code>\d{'{'}44{'}'}</code> casa qualquer chave de 44
                  dígitos; você gera o regex onde preferir e <b>cola aqui</b>.
                  <br />
                  <br />
                  <b>Dica:</b> um template <b>geral</b> usa âncoras como <code>DANFE</code>; um
                  template <b>por cliente</b> adiciona o <b>CNPJ ou o nome</b> do cliente.
                </span>
              </span>
            </div>

            {form.groups.map((g, gi) => (
              <div key={g.key}>
                <div className="group">
                  <div className="group-h">Grupo {gi + 1} — todas (E)</div>
                  {g.conds.map((c, ci) => {
                    const isRx = c.mode === 'regex'
                    return (
                      <div key={c.key} className="cond">
                        <span className="cond-and">{ci === 0 ? '' : 'E'}</span>
                        <select
                          className="select"
                          style={{ flex: 'none', width: 235 }}
                          value={c.mode}
                          onChange={(e) =>
                            patchCond(g.key, c.key, { mode: e.target.value as SignalMode })
                          }
                        >
                          <option value="texto">contém o texto</option>
                          <option value="regex">corresponde ao padrão (regex)</option>
                        </select>
                        <input
                          className={isRx ? 'tpl-inp mono' : 'tpl-inp'}
                          placeholder={
                            isRx
                              ? 'cole o regex, ex.: \\d{44}'
                              : 'ex.: NOTA FISCAL ELETRÔNICA, TryLab'
                          }
                          value={c.value}
                          onChange={(e) => patchCond(g.key, c.key, { value: e.target.value })}
                        />
                        <button
                          className="icon-x"
                          title="Remover condição"
                          aria-label="Remover condição"
                          onClick={() => removeCond(g.key, c.key)}
                        >
                          ×
                        </button>
                      </div>
                    )
                  })}
                  <button className="add-link" onClick={() => addCond(g.key)}>
                    + E — adicionar condição
                  </button>
                </div>
                {gi < form.groups.length - 1 && <div className="or-div">OU</div>}
              </div>
            ))}
            <div style={{ marginTop: 12 }}>
              <button className="add-link" onClick={addGroup}>
                + OU — adicionar grupo
              </button>
            </div>
          </div>

          {/* Passo 2 — CAMPOS (com IA) — linhas densas (D-T7) */}
          <div className="tpl-sec">
            <div className="tpl-sec-t">
              O que extrair <span className="sec-tag t-ai">com IA</span>
              <span className="info">
                i
                <span className="tip">
                  <b>Passo 2 — com IA.</b> A IA lê o documento inteiro e preenche os campos. O{' '}
                  <b>nome do campo</b> descreve o dado que você quer (ex.: <b>Emitente</b>,{' '}
                  <b>Número da NF</b>). Você não diz onde está — a IA acha pelo nome e pela dica.
                </span>
              </span>
            </div>
            <div className="tpl-sec-mini">Liste os dados que você quer tirar do documento.</div>

            <div className="fhead">
              <div className="h">
                Nome do campo — o dado que você quer
                <span className="info">
                  i
                  <span className="tip">
                    Dê um nome claro do <b>dado</b>; a IA procura no documento e preenche.
                    Exemplo (NF da TryLab):
                    <br />• <b>Emitente</b> → TryLab
                    <br />• <b>CNPJ do emitente</b> → 12.345.678/0001-99
                    <br />• <b>Número da NF</b> → 000123456
                    <br />• <b>Valor total</b> → R$ 1.234,56
                  </span>
                </span>
              </div>
              <div className="h">
                Tipo
                <span className="info">
                  i
                  <span className="tip">
                    Valida e normaliza o formato: <b>data</b>, <b>moeda</b>, <b>CPF/CNPJ</b>,{' '}
                    <b>número</b>, <b>texto</b>, <b>sim/não</b>.
                  </span>
                </span>
              </div>
              <div className="h">
                Obrig.
                <span className="info">
                  i
                  <span className="tip">
                    Se marcado e a IA não encontrar o dado, o documento vai para{' '}
                    <b>revisão humana</b> em vez de seguir.
                  </span>
                </span>
              </div>
              <div></div>
              <div></div>
            </div>

            {form.fields.map((f, idx) => (
              <div key={f.key} className="frow">
                <input
                  className="tpl-inp"
                  placeholder="ex.: Emitente, Número da NF, Valor total"
                  value={f.name}
                  onChange={(e) => patchField(f.key, { name: e.target.value })}
                />
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
                <Switch
                  on={f.required}
                  onToggle={() => patchField(f.key, { required: !f.required })}
                  title="Obrigatório"
                />
                <button
                  className="iconbtn"
                  title="Avançado: regex de validação e dica para a IA"
                  aria-label={`Avançado do campo ${f.name || idx + 1}`}
                  aria-expanded={f.advOpen}
                  onClick={() => patchField(f.key, { advOpen: !f.advOpen })}
                >
                  ⚙
                </button>
                <button
                  className="iconbtn danger"
                  title="Remover campo"
                  aria-label={`Remover campo ${f.name || idx + 1}`}
                  onClick={() => removeField(f.key)}
                >
                  ×
                </button>

                {f.advOpen && (
                  <div className="adv">
                    <div className="row2">
                      <div className="half">
                        <span className="adv-lbl">
                          Validação por regex <span className="soft">— opcional</span>
                          <span className="info r">
                            i
                            <span className="tip">
                              <b>Regra extra de formato</b>, opcional. Cole um regex que o valor
                              extraído deve seguir. Ex.: <code>\d{'{'}2{'}'}/\d{'{'}4{'}'}</code>{' '}
                              (mês/ano). Se o valor não casar, marca como inválido (vai para
                              revisão). O <b>tipo</b> já valida o básico — use isto só se
                              precisar.
                            </span>
                          </span>
                        </span>
                        <input
                          className="tpl-inp mono"
                          placeholder="cole o regex, ex.: \d{2}/\d{4}"
                          value={f.regex ?? ''}
                          onChange={(e) => patchField(f.key, { regex: e.target.value })}
                        />
                      </div>
                      <div className="half">
                        <span className="adv-lbl">
                          Dica para a IA <span className="soft">— opcional</span>
                          <span className="info r">
                            i
                            <span className="tip">
                              Texto livre para orientar a IA <b>onde/como</b> achar o dado. Ex.:{' '}
                              <i>“o valor após ‘Total da nota’”</i> ou{' '}
                              <i>“o nome no topo, em maiúsculas”</i>.
                            </span>
                          </span>
                        </span>
                        <input
                          className="tpl-inp"
                          placeholder="ex.: o valor após 'Total da nota'"
                          value={f.hint ?? ''}
                          onChange={(e) => patchField(f.key, { hint: e.target.value })}
                        />
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}

            <div style={{ marginTop: 12 }}>
              <button className="add-link" onClick={addField}>
                + Adicionar campo
              </button>
            </div>

            {formError && (
              <p style={{ fontSize: 13, color: 'var(--st-erro)', margin: '14px 0 0' }}>
                {formError}
              </p>
            )}

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
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
            Crie um template declarando como reconhecer o tipo (sinais) e os campos a extrair. O
            sistema usa os templates para classificar e preencher cada documento automaticamente.
          </p>
        </div>
      )}

      {/* S1 — Grid de templates */}
      {!isInitialLoading && !isError && templates.length > 0 && (
        <div className="tpl-grid">
          {templates.map((t) => {
            const condCount = t.signals.reduce((acc, g) => acc + g.length, 0)
            return (
              <div key={t.id} className="card tpl-card">
                <div className="tpl-head">
                  <div className="tpl-head-info">
                    <div className="tpl-icon">
                      <Icon name="grid" size={19} />
                    </div>
                    <div>
                      <div className="tpl-name">{t.name}</div>
                      <div className="tpl-type">
                        {t.signals.length > 0
                          ? `${t.signals.length} ${t.signals.length === 1 ? 'grupo' : 'grupos'} de sinais`
                          : 'Sem sinais'}
                      </div>
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
                  {condCount > 0 && (
                    <span>
                      <Icon name="checkSmall" size={13} />
                      {condCount} {condCount === 1 ? 'sinal' : 'sinais'}
                    </span>
                  )}
                </div>
              </div>
            )
          })}
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
