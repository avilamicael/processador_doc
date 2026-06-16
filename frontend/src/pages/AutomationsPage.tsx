import { AUTOMATIONS } from '../data/mock'
import { Icon } from '../components/Icon'
import { Switch } from '../components/Switch'

interface AutomationsPageProps {
  autoState: Record<number, boolean>
  onToggleAuto: (id: number) => void
}

export function AutomationsPage({ autoState, onToggleAuto }: AutomationsPageProps) {
  return (
    <div>
      <div className="sec-head">
        <div className="sec-head-col">
          <h2 className="sec-title">Automações</h2>
          <p className="sec-desc">
            Ações executadas automaticamente após o tratamento de um documento, no modelo{' '}
            <strong style={{ color: 'var(--text-2)', fontWeight: 600 }}>gatilho → condição → ação</strong>.
          </p>
        </div>
        <button className="btn-primary"><Icon name="plus" size={15} />Nova automação</button>
      </div>

      <div className="stack">
        {AUTOMATIONS.map((a) => {
          const on = !!autoState[a.id]
          return (
            <div key={a.id} className="card auto-card">
              <div className="auto-head">
                <div className="auto-icon"><Icon name="bolt" size={17} sw={1.8} /></div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="auto-name">{a.name}</div>
                  <div className="auto-runs">{a.runs}</div>
                </div>
                <span className={on ? 'badge badge-ok' : 'badge badge-off'}>{on ? 'Ativa' : 'Pausada'}</span>
                <Switch on={on} onToggle={() => onToggleAuto(a.id)} title="Ativar/pausar automação" />
              </div>
              <div className="auto-flow">
                <span className="flow-pill"><span className="flow-tag">QUANDO</span>{a.trigger}</span>
                <Icon name="arrowRight" size={15} stroke="var(--text-3)" />
                <span className="flow-pill"><span className="flow-tag">SE</span>{a.cond}</span>
                <Icon name="arrowRight" size={15} stroke="var(--text-3)" />
                <span className="flow-pill action"><span className="flow-tag">AÇÃO</span>{a.action}</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
