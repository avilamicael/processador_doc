import type { Page } from '../types'
import { Icon } from './Icon'
import type { IconName } from './Icon'
import { useWatcherStatus } from '../hooks/useWatcherStatus'

// Tempo relativo em pt-BR a partir do ISO da última varredura ("há Xs / X min /
// X h"; "—" se null/inválido). Sem libs — cálculo direto.
function relativeScan(iso: string | null): string {
  if (!iso) return '—'
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return '—'
  const secs = Math.max(0, Math.round((Date.now() - t) / 1000))
  if (secs < 60) return `há ${secs}s`
  const mins = Math.round(secs / 60)
  if (mins < 60) return `há ${mins} min`
  const hours = Math.round(mins / 60)
  return `há ${hours} h`
}

interface NavItem { page: Page; label: string; icon: IconName }

const GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: 'OPERAÇÃO',
    items: [
      { page: 'documentos', label: 'Documentos', icon: 'doc' },
      { page: 'atencao', label: 'Precisam de atenção', icon: 'alert' },
    ],
  },
  {
    title: 'PROCESSAMENTO',
    items: [
      { page: 'templates', label: 'Templates', icon: 'grid' },
      { page: 'automacoes', label: 'Automações', icon: 'bolt' },
      { page: 'dryrun', label: 'Pré-visualização', icon: 'eye' },
    ],
  },
  { title: 'SISTEMA', items: [{ page: 'config', label: 'Configurações', icon: 'sliders' }] },
]

interface SidebarProps {
  page: Page
  onNavigate: (p: Page) => void
}

export function Sidebar({ page, onNavigate }: SidebarProps) {
  const statusQuery = useWatcherStatus()
  const status = statusQuery.data
  const active = status?.active ?? false
  // Sub-texto: enquanto carrega sem dados → "verificando…"; erro → "—".
  let sub: string
  if (statusQuery.isLoading && !status) {
    sub = 'verificando…'
  } else if (statusQuery.isError && !status) {
    sub = '—'
  } else if (status) {
    const n = status.active_folder_count
    sub = `${n} ${n === 1 ? 'pasta' : 'pastas'} · varredura ${relativeScan(status.last_scan_at)}`
  } else {
    sub = '—'
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-head">
        <div className="logo-box">
          <Icon name="logo" size={19} />
        </div>
        <div style={{ lineHeight: 1.15 }}>
          <div className="brand-name">DocWatch</div>
          <div className="brand-sub">Gestão documental</div>
        </div>
      </div>

      <nav className="nav">
        {GROUPS.map((group, gi) => (
          <div key={group.title}>
            <div className={gi === 0 ? 'nav-group' : 'nav-group mt'}>{group.title}</div>
            {group.items.map((item) => (
              <button
                key={item.page}
                className={page === item.page ? 'nav-item active' : 'nav-item'}
                onClick={() => onNavigate(item.page)}
              >
                <span className="nav-ind" />
                <Icon name={item.icon} size={18} />
                <span>{item.label}</span>
              </button>
            ))}
          </div>
        ))}
      </nav>

      <div className="sidebar-foot">
        <div className="watcher-box">
          <span
            className="watcher-dot"
            style={{ background: active ? 'var(--st-tratado)' : 'var(--text-3)' }}
          />
          <div style={{ lineHeight: 1.25 }}>
            <div className="watcher-title">{active ? 'Watcher ativo' : 'Watcher inativo'}</div>
            <div className="watcher-sub">{sub}</div>
          </div>
        </div>
      </div>
    </aside>
  )
}
