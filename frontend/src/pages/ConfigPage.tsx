import type { CSSProperties } from 'react'
import { useEffect, useState } from 'react'
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
import {
  useAiFallback,
  useApprovalMode,
  useReviewThreshold,
  useSaveAiFallback,
  useSaveApprovalMode,
  useSaveReviewThreshold,
} from '../hooks/useAttention'

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

// `soon` = aba ainda não funcional (v2): mostra uma badge "em breve" discreta.
// A aba continua clicável — abre o conteúdo desabilitado com o aviso.
const TABS: { key: ConfigTab; label: string; soon?: boolean }[] = [
  { key: 'pastas', label: 'Pastas monitoradas' },
  { key: 'regras', label: 'Regras de separação', soon: true },
  { key: 'leitura', label: 'Leitura de dados' },
  { key: 'integracoes', label: 'Integrações', soon: true },
]

// Aviso destacado de funcionalidade adiada para a versão 2.
function SoonBanner() {
  return (
    <div
      className="card"
      style={{
        padding: '12px 16px',
        marginBottom: 16,
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        borderLeft: '3px solid var(--st-leitura)',
      }}
    >
      <Icon name="alert" size={16} stroke="var(--st-leitura)" />
      <span style={{ fontSize: 13, color: 'var(--text-2)' }}>
        Em breve — disponível na versão 2.
      </span>
    </div>
  )
}

export function ConfigPage(props: ConfigPageProps) {
  const { tab, onTab } = props
  return (
    <div className="page-narrow">
      <div className="tabs">
        {TABS.map((t) => (
          <button key={t.key} className={tab === t.key ? 'tab active' : 'tab'} onClick={() => onTab(t.key)}>
            {t.label}
            {t.soon && (
              <span className="badge badge-off" style={{ marginLeft: 8, fontSize: 10 }}>
                em breve
              </span>
            )}
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

type FormState = { id: number | null; path: string; pages: string; splitToFiles: boolean }

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
    setForm({ id: null, path: '', pages: '', splitToFiles: false })
  }
  const openEdit = (f: Folder) => {
    setFormError(null)
    setForm({
      id: f.id,
      path: f.path,
      pages: f.pages_per_block ? String(f.pages_per_block) : '',
      splitToFiles: f.split_to_files,
    })
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
        { path, pages_per_block, active: true, split_to_files: form.splitToFiles },
        { onSuccess: closeForm, onError },
      )
    } else {
      updateFolder.mutate(
        { id: form.id, body: { path, pages_per_block, split_to_files: form.splitToFiles } },
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
            O monitoramento procura novos documentos nestas pastas e os envia para a fila
            conforme a regra de separação definida por pasta.
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
            <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  fontSize: 12,
                  fontWeight: 600,
                  color: 'var(--text-2)',
                }}
              >
                <Switch
                  on={form.splitToFiles}
                  onToggle={() => setForm({ ...form, splitToFiles: !form.splitToFiles })}
                  title="Separar o PDF em arquivos na pasta"
                />
                Separar o PDF em arquivos na pasta
              </span>
              <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
                Quando ligado, ao chegar um PDF a separação acontece NA PRÓPRIA PASTA: o PDF é
                dividido em vários arquivos (no lugar do original) antes da leitura. O arquivo
                original continua recuperável — nada é perdido. Depende de "Separar a cada N
                páginas" estar configurado.
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
            <span style={{ fontSize: 13, fontWeight: 600 }}>Monitoramento geral</span>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
              monitora as pastas ativas continuamente
            </span>
          </div>
          <Switch on={watcher} onToggle={onToggleWatcher} title="Ativar/desativar monitoramento" />
        </div>

        {foldersQuery.isLoading && (
          <div style={{ padding: '24px 18px', fontSize: 13, color: 'var(--text-3)' }}>
            Carregando pastas…
          </div>
        )}

        {foldersQuery.isError && (
          <div style={{ padding: '24px 18px' }}>
            <p style={{ fontSize: 13, margin: '0 0 12px' }}>
              Não foi possível carregar as pastas. Verifique se o aplicativo está aberto e tente de novo.
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
              Adicione uma pasta para o sistema começar a receber documentos automaticamente.
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
                {f.split_to_files && (
                  <>
                    <span>·</span>
                    <span>Separa em arquivos</span>
                  </>
                )}
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
              monitoramento? Os documentos já recebidos permanecem; apenas o monitoramento desta
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

function RegrasTab({ ruleState }: ConfigPageProps) {
  return (
    <div>
      <SoonBanner />
      <div className="sec-head">
        <div className="sec-head-col">
          <h2 className="sec-title">Regras de separação</h2>
          <p className="sec-desc">
            Definem como um PDF de várias páginas é dividido em documentos individuais antes da leitura. Aplicadas em ordem de prioridade.
          </p>
        </div>
        <button className="btn-primary" disabled title="em breve">
          <Icon name="plus" size={15} />Nova regra
        </button>
      </div>
      {/* Conteúdo esmaecido e não-interativo (Switch não aceita disabled, então
          envolvemos num container com pointer-events:none + opacity). */}
      <div className="stack" style={{ opacity: 0.5, pointerEvents: 'none' }}>
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
              <Switch on={on} onToggle={() => {}} title="em breve" />
            </div>
          )
        })}
      </div>
    </div>
  )
}

// Tag discreta "em breve" ao lado de um controle mock desabilitado.
function SoonTag() {
  return (
    <span className="badge badge-off" style={{ marginLeft: 8, fontSize: 10 }}>
      em breve
    </span>
  )
}

function LeituraTab({ deskew, denoise }: ConfigPageProps) {
  // Controles mock desabilitados (OCR/idioma/slider/deskew/denoise) — esmaecidos
  // e não-interativos. O Limiar de confiança (ReviewThresholdField) permanece
  // 100% FUNCIONAL (salva na API) e NÃO é tocado aqui.
  const mutedRow: CSSProperties = { opacity: 0.5 }
  return (
    <div className="read-card">
      <h2 className="sec-title">Leitura dos dados</h2>
      <div className="card" style={{ overflow: 'hidden' }}>
        <div className="read-row" style={mutedRow}>
          <div>
            <div className="read-label">
              Leitura de imagem
              <SoonTag />
            </div>
            <div className="read-hint">Usada quando o PDF é uma imagem (foto ou escaneado), sem texto.</div>
          </div>
          <select className="select" defaultValue="Tesseract 5" disabled title="em breve">
            <option>Tesseract 5</option>
            <option>Google Cloud Vision</option>
            <option>AWS Textract</option>
          </select>
        </div>
        <div className="read-row" style={mutedRow}>
          <div>
            <div className="read-label">
              Idioma principal
              <SoonTag />
            </div>
            <div className="read-hint">Dicionário usado na correção de leitura</div>
          </div>
          <select className="select" defaultValue="Português (BR)" disabled title="em breve">
            <option>Português (BR)</option>
            <option>Inglês</option>
            <option>Espanhol</option>
          </select>
        </div>
        <div className="read-row" style={mutedRow}>
          <div>
            <div className="read-label">
              Confiança mínima
              <SoonTag />
            </div>
            <div className="read-hint">Abaixo deste valor o campo é marcado para revisão manual</div>
          </div>
          <div className="slider-wrap" style={{ pointerEvents: 'none' }}>
            <div className="slider-track">
              <div className="slider-fill" style={{ width: '85%' }} />
              <div className="slider-knob" style={{ left: '85%' }} />
            </div>
            <span className="slider-val">85%</span>
          </div>
        </div>
        <div className="read-row" style={mutedRow}>
          <div>
            <div className="read-label">
              Corrigir inclinação
              <SoonTag />
            </div>
            <div className="read-hint">Endireita páginas escaneadas antes da leitura.</div>
          </div>
          <span style={{ pointerEvents: 'none' }}>
            <Switch on={deskew} onToggle={() => {}} title="em breve" />
          </span>
        </div>
        <div className="read-row" style={mutedRow}>
          <div>
            <div className="read-label">
              Remoção de ruído
              <SoonTag />
            </div>
            <div className="read-hint">Limpa manchas e pontos de digitalizações antigas</div>
          </div>
          <span style={{ pointerEvents: 'none' }}>
            <Switch on={denoise} onToggle={() => {}} title="em breve" />
          </span>
        </div>
      </div>

      {/* S6 — Limiar de confiança (D-03): lê/salva /config/review-threshold.
          PERMANECE FUNCIONAL — não é mock. */}
      <ReviewThresholdField />

      {/* IA-fallback opt-in (D-05): lê/salva /config/ai-fallback. Default OFF. */}
      <AiFallbackField />

      {/* Modo de aprovação (D-03/D-06): lê/salva /config/approval-mode. Default OFF. */}
      <ApprovalModeField />
    </div>
  )
}

// Modo de aprovação (D-03/D-06). Toggle "Automações aguardam minha aprovação": quando
// ligado, os documentos de alta confiança NÃO são aplicados sozinhos (gate no worker,
// 12-03) — ficam pendentes na Pré-visualização para você aprovar (aplicar) ou negar.
// Default OFF refletido pelo valor do GET. Salva ao alternar.
function ApprovalModeField() {
  const approvalQuery = useApprovalMode()
  const saveApproval = useSaveApprovalMode()
  const [saveError, setSaveError] = useState<string | null>(null)

  const enabled = approvalQuery.data?.enabled ?? false

  const toggle = () => {
    setSaveError(null)
    saveApproval.mutate(!enabled, {
      onError: () => setSaveError('Não foi possível salvar a opção. Tente novamente.'),
    })
  }

  return (
    <div className="card" style={{ padding: 18, marginTop: 16 }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 16,
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)' }}>
            Automações aguardam minha aprovação
          </span>
          <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
            Quando ligado, as automações ficam pendentes na Pré-visualização para você
            aprovar ou negar — nada é movido sozinho. Quando desligado, documentos lidos com
            bastante certeza são aplicados automaticamente (o nível mínimo de certeza continua
            valendo). Padrão: desligado.
          </span>
        </div>
        {!approvalQuery.isLoading && !approvalQuery.isError && (
          <span style={{ pointerEvents: saveApproval.isPending ? 'none' : 'auto', flex: 'none' }}>
            <Switch
              on={enabled}
              onToggle={toggle}
              title="Automações aguardam minha aprovação"
            />
          </span>
        )}
      </div>

      {approvalQuery.isLoading && (
        <div style={{ fontSize: 13, color: 'var(--text-3)', marginTop: 10 }}>
          Carregando configuração…
        </div>
      )}

      {approvalQuery.isError && (
        <div style={{ marginTop: 10 }}>
          <p style={{ fontSize: 13, margin: '0 0 12px' }}>
            Não foi possível carregar a configuração. Verifique se o aplicativo está aberto e tente de novo.
          </p>
          <button className="btn-primary" onClick={() => approvalQuery.refetch()}>
            <Icon name="refresh" size={15} />
            Tentar novamente
          </button>
        </div>
      )}

      {saveError && (
        <p style={{ fontSize: 13, color: 'var(--st-erro)', margin: '10px 0 0' }}>{saveError}</p>
      )}
    </div>
  )
}

// IA-fallback opt-in (D-05). Toggle "IA classifica quando nenhum template casa": quando
// ligado, todo documento que NENHUM template reconhecer gera 1 chamada de IA (custo por
// token). Default OFF refletido pelo valor do GET. Salva ao alternar.
function AiFallbackField() {
  const fallbackQuery = useAiFallback()
  const saveFallback = useSaveAiFallback()
  const [saveError, setSaveError] = useState<string | null>(null)

  const enabled = fallbackQuery.data?.enabled ?? false

  const toggle = () => {
    setSaveError(null)
    saveFallback.mutate(!enabled, {
      onError: () => setSaveError('Não foi possível salvar a opção. Tente novamente.'),
    })
  }

  return (
    <div className="card" style={{ padding: 18, marginTop: 16 }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 16,
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)' }}>
            Usar IA quando nenhum tipo reconhecer
          </span>
          <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
            Quando ligado, cada documento que nenhum tipo reconhecer gera 1 consulta à IA
            (custo por uso). Padrão: desligado.
          </span>
        </div>
        {!fallbackQuery.isLoading && !fallbackQuery.isError && (
          <span style={{ pointerEvents: saveFallback.isPending ? 'none' : 'auto', flex: 'none' }}>
            <Switch
              on={enabled}
              onToggle={toggle}
              title="Usar IA quando nenhum tipo reconhecer"
            />
          </span>
        )}
      </div>

      {fallbackQuery.isLoading && (
        <div style={{ fontSize: 13, color: 'var(--text-3)', marginTop: 10 }}>
          Carregando configuração…
        </div>
      )}

      {fallbackQuery.isError && (
        <div style={{ marginTop: 10 }}>
          <p style={{ fontSize: 13, margin: '0 0 12px' }}>
            Não foi possível carregar a configuração. Verifique se o aplicativo está aberto e tente de novo.
          </p>
          <button className="btn-primary" onClick={() => fallbackQuery.refetch()}>
            <Icon name="refresh" size={15} />
            Tentar novamente
          </button>
        </div>
      )}

      {saveError && (
        <p style={{ fontSize: 13, color: 'var(--st-erro)', margin: '10px 0 0' }}>{saveError}</p>
      )}
    </div>
  )
}

// S6 — Limiar de confiança global. Lê via useReviewThreshold (0.0–1.0 na API),
// exibe/edita em 0–100% com sufixo "%", e salva via useSaveReviewThreshold
// (converte 0–100 ↔ 0.0–1.0). Documentos com confiança abaixo do limiar (ou com
// obrigatório inválido) vão para revisão.
function ReviewThresholdField() {
  const thresholdQuery = useReviewThreshold()
  const saveThreshold = useSaveReviewThreshold()
  const [pct, setPct] = useState<string>('')
  const [saveError, setSaveError] = useState<string | null>(null)

  // Sincroniza o input com o valor carregado da API (0.0–1.0 → 0–100).
  useEffect(() => {
    if (thresholdQuery.data) {
      setPct(String(Math.round(thresholdQuery.data.threshold * 100)))
    }
  }, [thresholdQuery.data])

  const submit = () => {
    setSaveError(null)
    const parsed = Number.parseInt(pct, 10)
    if (Number.isNaN(parsed) || parsed < 0 || parsed > 100) {
      setSaveError('Informe um valor entre 0 e 100.')
      return
    }
    saveThreshold.mutate(parsed / 100, {
      onError: () =>
        setSaveError('Não foi possível salvar o nível mínimo de certeza. Tente novamente.'),
    })
  }

  return (
    <div className="card" style={{ padding: 18, marginTop: 16 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 12 }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)' }}>
          Nível mínimo de certeza
        </span>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
          Documentos lidos com certeza abaixo deste valor, ou com algum campo obrigatório
          inválido, vão para sua conferência.
        </span>
      </div>

      {thresholdQuery.isLoading && (
        <div style={{ fontSize: 13, color: 'var(--text-3)' }}>Carregando o nível mínimo de certeza…</div>
      )}

      {thresholdQuery.isError && (
        <div>
          <p style={{ fontSize: 13, margin: '0 0 12px' }}>
            Não foi possível carregar o nível mínimo de certeza. Verifique se o aplicativo está aberto e tente de novo.
          </p>
          <button className="btn-primary" onClick={() => thresholdQuery.refetch()}>
            <Icon name="refresh" size={15} />
            Tentar novamente
          </button>
        </div>
      )}

      {!thresholdQuery.isLoading && !thresholdQuery.isError && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input
              className="search-input"
              type="number"
              min={0}
              max={100}
              style={{ width: 120 }}
              value={pct}
              onChange={(e) => setPct(e.target.value)}
              aria-label="Nível mínimo de certeza em porcentagem"
            />
            <span style={{ fontSize: 13, color: 'var(--text-2)' }}>%</span>
          </div>
          <button className="btn-primary" onClick={submit} disabled={saveThreshold.isPending}>
            {saveThreshold.isPending ? 'Salvando…' : 'Salvar'}
          </button>
        </div>
      )}

      {saveError && (
        <p style={{ fontSize: 13, color: 'var(--st-erro)', margin: '10px 0 0' }}>{saveError}</p>
      )}
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
      <div className="integ-grid" style={{ opacity: 0.5, pointerEvents: 'none' }}>
        {INTEGRATIONS.map((i) => (
          <div key={i.id} className="card integ-card">
            <div className="integ-mono">{i.mono}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="integ-name">{i.name}</div>
              <div className="integ-cat">{i.cat}</div>
            </div>
            <span className="badge badge-off">Indisponível</span>
          </div>
        ))}
      </div>
    </div>
  )
}
