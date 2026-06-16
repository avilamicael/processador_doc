import { useState } from 'react'
import { INTEGRATIONS, RULES } from '../data/mock'
import type { ConfigTab, Folder } from '../types'
import { Icon } from '../components/Icon'
import { Switch } from '../components/Switch'
import {
  useCreateFolder,
  useDeleteFolder,
  useUpdateFolder,
  useWatchedFolders,
} from '../hooks/useWatchedFolders'

interface ConfigPageProps {
  tab: ConfigTab
  onTab: (t: ConfigTab) => void
  watcher: boolean
  onToggleWatcher: () => void
  ruleState: Record<number, boolean>
  onToggleRule: (id: number) => void
  deskew: boolean
  onToggleDeskew: () => void
  denoise: boolean
  onToggleDenoise: () => void
}

const TABS: { key: ConfigTab; label: string }[] = [
  { key: 'pastas', label: 'Pastas monitoradas' },
  { key: 'regras', label: 'Regras de separação' },
  { key: 'leitura', label: 'Leitura de dados' },
  { key: 'integracoes', label: 'Integrações' },
]

export function ConfigPage(props: ConfigPageProps) {
  const { tab, onTab } = props
  return (
    <div className="page-narrow">
      <div className="tabs">
        {TABS.map((t) => (
          <button key={t.key} className={tab === t.key ? 'tab active' : 'tab'} onClick={() => onTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'pastas' && <PastasTab watcher={props.watcher} onToggleWatcher={props.onToggleWatcher} />}
      {tab === 'regras' && <RegrasTab {...props} />}
      {tab === 'leitura' && <LeituraTab {...props} />}
      {tab === 'integracoes' && <IntegracoesTab />}
    </div>
  )
}

// Descrição da regra de separação por pasta (D-05: None/0 = "Não separar").
function splitLabel(pages: number | null): string {
  if (pages == null || pages <= 0) return 'Não separar'
  return pages === 1 ? 'Separar a cada 1 página' : `Separar a cada ${pages} páginas`
}

type FormState = { id: number | null; path: string; pages: string }

function PastasTab({ watcher, onToggleWatcher }: { watcher: boolean; onToggleWatcher: () => void }) {
  const foldersQuery = useWatchedFolders()
  const createFolder = useCreateFolder()
  const updateFolder = useUpdateFolder()
  const deleteFolder = useDeleteFolder()

  const [form, setForm] = useState<FormState | null>(null)
  const [confirmRemove, setConfirmRemove] = useState<Folder | null>(null)
  const [formError, setFormError] = useState<string | null>(null)

  const folders = foldersQuery.data ?? []

  const openAdd = () => {
    setFormError(null)
    setForm({ id: null, path: '', pages: '' })
  }
  const openEdit = (f: Folder) => {
    setFormError(null)
    setForm({ id: f.id, path: f.path, pages: f.pages_per_block ? String(f.pages_per_block) : '' })
  }
  const closeForm = () => {
    setForm(null)
    setFormError(null)
  }

  const saving = createFolder.isPending || updateFolder.isPending

  const submitForm = () => {
    if (!form) return
    const path = form.path.trim()
    if (!path) {
      setFormError('Informe o caminho da pasta.')
      return
    }
    const parsed = form.pages.trim() === '' ? null : Number.parseInt(form.pages, 10)
    const pages_per_block = parsed && parsed > 0 ? parsed : null
    setFormError(null)
    const onError = () =>
      setFormError('Não foi possível salvar a pasta. Confira o caminho e tente novamente.')
    if (form.id == null) {
      createFolder.mutate(
        { path, pages_per_block, active: true },
        { onSuccess: closeForm, onError },
      )
    } else {
      updateFolder.mutate(
        { id: form.id, body: { path, pages_per_block } },
        { onSuccess: closeForm, onError },
      )
    }
  }

  const toggleActive = (f: Folder) =>
    updateFolder.mutate({ id: f.id, body: { active: !f.active } })

  const confirmDelete = () => {
    if (!confirmRemove) return
    deleteFolder.mutate(confirmRemove.id, { onSettled: () => setConfirmRemove(null) })
  }

  return (
    <div>
      <div className="sec-head">
        <div className="sec-head-col">
          <h2 className="sec-title">Pastas monitoradas</h2>
          <p className="sec-desc">
            O watcher varre estas pastas em busca de novos documentos e os envia para a fila de
            processamento conforme a regra de separação definida por pasta.
          </p>
        </div>
        <button className="btn-primary" onClick={openAdd}>
          <Icon name="plus" size={15} />
          Adicionar pasta
        </button>
      </div>

      {/* Formulário inline de adicionar/editar pasta */}
      {form && (
        <div className="card" style={{ padding: 18, marginBottom: 16 }}>
          <h3 className="sec-title" style={{ fontSize: 14, marginBottom: 14 }}>
            {form.id == null ? 'Adicionar pasta' : 'Editar pasta'}
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)' }}>Caminho da pasta</span>
              <input
                className="search-input"
                style={{ fontFamily: 'var(--font-mono)' }}
                placeholder={'C:\\Documentos\\Entrada'}
                value={form.path}
                onChange={(e) => setForm({ ...form, path: e.target.value })}
              />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)' }}>
                Separar a cada N páginas
              </span>
              <input
                className="search-input"
                type="number"
                min={0}
                placeholder="Não separar"
                value={form.pages}
                onChange={(e) => setForm({ ...form, pages: e.target.value })}
              />
              <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
                Cada bloco de N páginas vira um documento independente. Deixe vazio (ou 0) em
                "Não separar" para tratar o arquivo inteiro como um documento.
              </span>
            </label>
            {formError && (
              <p style={{ fontSize: 13, color: 'var(--st-erro)', margin: 0 }}>{formError}</p>
            )}
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn-ghost" onClick={closeForm} disabled={saving}>
                Cancelar
              </button>
              <button className="btn-primary" onClick={submitForm} disabled={saving}>
                {saving
                  ? 'Salvando…'
                  : form.id == null
                    ? 'Salvar pasta'
                    : 'Salvar alterações'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="card" style={{ overflow: 'hidden' }}>
        <div className="list-head">
          <div className="list-head-info">
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: watcher ? 'var(--st-tratado)' : 'var(--text-3)',
              }}
            />
            <span style={{ fontSize: 13, fontWeight: 600 }}>Watcher global</span>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
              monitora as pastas ativas continuamente
            </span>
          </div>
          <Switch on={watcher} onToggle={onToggleWatcher} title="Ativar/desativar watcher" />
        </div>

        {foldersQuery.isLoading && (
          <div style={{ padding: '24px 18px', fontSize: 13, color: 'var(--text-3)' }}>
            Carregando pastas…
          </div>
        )}

        {foldersQuery.isError && (
          <div style={{ padding: '24px 18px' }}>
            <p style={{ fontSize: 13, margin: '0 0 12px' }}>
              Não foi possível carregar as pastas. Verifique se o serviço está em execução.
            </p>
            <button className="btn-primary" onClick={() => foldersQuery.refetch()}>
              <Icon name="refresh" size={15} />
              Tentar novamente
            </button>
          </div>
        )}

        {!foldersQuery.isLoading && !foldersQuery.isError && folders.length === 0 && (
          <div style={{ padding: '48px 24px', textAlign: 'center' }}>
            <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>Nenhuma pasta monitorada</div>
            <p style={{ fontSize: 13, color: 'var(--text-3)', margin: 0 }}>
              Adicione uma pasta para o sistema começar a ingerir documentos automaticamente.
            </p>
          </div>
        )}

        {folders.map((f) => (
          <div key={f.id} className="folder-row">
            <div className="folder-icon">
              <Icon name="folder" size={18} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="folder-path">{f.path}</div>
              <div className="folder-meta">
                <span>{splitLabel(f.pages_per_block)}</span>
                <span>·</span>
                <span>{f.active ? 'Ativa' : 'Inativa'}</span>
              </div>
            </div>
            <Switch on={f.active} onToggle={() => toggleActive(f)} title="Ativar/desativar pasta" />
            <button className="row-action" title="Editar pasta" onClick={() => openEdit(f)}>
              <Icon name="dots" size={16} />
            </button>
            <button
              className="row-action"
              title="Remover pasta"
              aria-label={`Remover ${f.path}`}
              style={{ color: 'var(--st-erro)' }}
              onClick={() => setConfirmRemove(f)}
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      {/* Confirmação destrutiva de remoção (UI-SPEC copy) */}
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
              Remover pasta
            </h3>
            <p style={{ fontSize: 13, color: 'var(--text-2)', margin: '0 0 18px' }}>
              Remover <b style={{ fontFamily: 'var(--font-mono)' }}>{confirmRemove.path}</b> do
              monitoramento? Os documentos já ingeridos permanecem; apenas o monitoramento desta
              pasta para.
            </p>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button
                className="btn-ghost"
                onClick={() => setConfirmRemove(null)}
                disabled={deleteFolder.isPending}
              >
                Manter pasta
              </button>
              <button
                className="btn-primary"
                style={{ background: 'var(--st-erro)' }}
                onClick={confirmDelete}
                disabled={deleteFolder.isPending}
              >
                {deleteFolder.isPending ? 'Removendo…' : 'Remover'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function RegrasTab({ ruleState, onToggleRule }: ConfigPageProps) {
  return (
    <div>
      <div className="sec-head">
        <div className="sec-head-col">
          <h2 className="sec-title">Regras de separação</h2>
          <p className="sec-desc">
            Definem como um PDF de várias páginas é dividido em documentos individuais antes da leitura. Aplicadas em ordem de prioridade.
          </p>
        </div>
        <button className="btn-primary"><Icon name="plus" size={15} />Nova regra</button>
      </div>
      <div className="stack">
        {RULES.map((r) => {
          const on = !!ruleState[r.id]
          return (
            <div key={r.id} className="card rule-card">
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="rule-title">
                  <span className="rule-name">{r.name}</span>
                  <span className="rule-param">{r.param}</span>
                </div>
                <p className="rule-desc">{r.desc}</p>
              </div>
              <Switch on={on} onToggle={() => onToggleRule(r.id)} title="Ativar/desativar regra" />
            </div>
          )
        })}
      </div>
    </div>
  )
}

function LeituraTab({ deskew, onToggleDeskew, denoise, onToggleDenoise }: ConfigPageProps) {
  return (
    <div className="read-card">
      <h2 className="sec-title">Leitura e extração de dados</h2>
      <div className="card" style={{ overflow: 'hidden' }}>
        <div className="read-row">
          <div>
            <div className="read-label">Motor de OCR</div>
            <div className="read-hint">Engine usado quando o PDF não possui texto nativo</div>
          </div>
          <select className="select" defaultValue="Tesseract 5">
            <option>Tesseract 5</option>
            <option>Google Cloud Vision</option>
            <option>AWS Textract</option>
          </select>
        </div>
        <div className="read-row">
          <div>
            <div className="read-label">Idioma principal</div>
            <div className="read-hint">Dicionário usado na correção de leitura</div>
          </div>
          <select className="select" defaultValue="Português (BR)">
            <option>Português (BR)</option>
            <option>Inglês</option>
            <option>Espanhol</option>
          </select>
        </div>
        <div className="read-row">
          <div>
            <div className="read-label">Confiança mínima</div>
            <div className="read-hint">Abaixo deste valor o campo é marcado para revisão manual</div>
          </div>
          <div className="slider-wrap">
            <div className="slider-track">
              <div className="slider-fill" style={{ width: '85%' }} />
              <div className="slider-knob" style={{ left: '85%' }} />
            </div>
            <span className="slider-val">85%</span>
          </div>
        </div>
        <div className="read-row">
          <div>
            <div className="read-label">Corrigir inclinação (deskew)</div>
            <div className="read-hint">Endireita páginas digitalizadas antes do OCR</div>
          </div>
          <Switch on={deskew} onToggle={onToggleDeskew} />
        </div>
        <div className="read-row">
          <div>
            <div className="read-label">Remoção de ruído</div>
            <div className="read-hint">Limpa manchas e pontos de digitalizações antigas</div>
          </div>
          <Switch on={denoise} onToggle={onToggleDenoise} />
        </div>
      </div>
    </div>
  )
}

function IntegracoesTab() {
  return (
    <div>
      <div style={{ marginBottom: 18 }}>
        <h2 className="sec-title">Integrações</h2>
        <p className="sec-desc">Destinos e serviços conectados para onde os documentos tratados são enviados.</p>
      </div>
      <div className="integ-grid">
        {INTEGRATIONS.map((i) => (
          <div key={i.id} className="card integ-card">
            <div className="integ-mono">{i.mono}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="integ-name">{i.name}</div>
              <div className="integ-cat">{i.cat}</div>
            </div>
            <span className={i.on ? 'badge badge-ok' : 'badge badge-off'}>{i.on ? 'Conectado' : 'Desconectado'}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
