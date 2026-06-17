import type { Page } from '../types'
import { Icon } from './Icon'
import type { IconName } from './Icon'

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
    ],
  },
  { title: 'SISTEMA', items: [{ page: 'config', label: 'Configurações', icon: 'sliders' }] },
]

interface SidebarProps {
  page: Page
  onNavigate: (p: Page) => void
}

export function Sidebar({ page, onNavigate }: SidebarProps) {
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
          <span className="watcher-dot" />
          <div style={{ lineHeight: 1.25 }}>
            <div className="watcher-title">Watcher ativo</div>
            <div className="watcher-sub">4 pastas · varredura há 2 min</div>
          </div>
        </div>
      </div>
    </aside>
  )
}
