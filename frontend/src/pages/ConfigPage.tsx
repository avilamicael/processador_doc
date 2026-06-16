import { FOLDERS, INTEGRATIONS, RULES } from '../data/mock'
import type { ConfigTab } from '../types'
import { Icon } from '../components/Icon'
import { Switch } from '../components/Switch'

interface ConfigPageProps {
  tab: ConfigTab
  onTab: (t: ConfigTab) => void
  watcher: boolean
  onToggleWatcher: () => void
  folderState: Record<number, boolean>
  onToggleFolder: (id: number) => void
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

      {tab === 'pastas' && <PastasTab {...props} />}
      {tab === 'regras' && <RegrasTab {...props} />}
      {tab === 'leitura' && <LeituraTab {...props} />}
      {tab === 'integracoes' && <IntegracoesTab />}
    </div>
  )
}

function PastasTab({ watcher, onToggleWatcher, folderState, onToggleFolder }: ConfigPageProps) {
  return (
    <div>
      <div className="sec-head">
        <div className="sec-head-col">
          <h2 className="sec-title">Pastas monitoradas</h2>
          <p className="sec-desc">
            O watcher varre estas pastas em busca de novos PDFs e os envia para a fila de processamento conforme as regras definidas.
          </p>
        </div>
        <button className="btn-primary"><Icon name="plus" size={15} />Adicionar pasta</button>
      </div>

      <div className="card" style={{ overflow: 'hidden' }}>
        <div className="list-head">
          <div className="list-head-info">
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#2FBF71' }} />
            <span style={{ fontSize: 13, fontWeight: 600 }}>Watcher global</span>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>intervalo padrão de varredura: 5 min</span>
          </div>
          <Switch on={watcher} onToggle={onToggleWatcher} title="Ativar/desativar watcher" />
        </div>

        {FOLDERS.map((f) => {
          const on = !!folderState[f.id]
          return (
            <div key={f.id} className="folder-row">
              <div className="folder-icon"><Icon name="folder" size={18} /></div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="folder-path">{f.path}</div>
                <div className="folder-meta">
                  <span>{f.rec ? 'Recursiva' : 'Não recursiva'}</span><span>·</span>
                  <span>{f.types}</span><span>·</span>
                  <span>{f.freq}</span><span>·</span>
                  <span>{f.files} arquivos</span>
                </div>
              </div>
              <div className="folder-last">última varredura<br /><b>{f.last}</b></div>
              <Switch on={on} onToggle={() => onToggleFolder(f.id)} title="Ativar/desativar pasta" />
              <button className="row-action" title="Mais"><Icon name="dots" size={16} /></button>
            </div>
          )
        })}
      </div>
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
