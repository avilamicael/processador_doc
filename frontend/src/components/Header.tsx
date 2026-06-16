import { Icon } from './Icon'

interface HeaderProps {
  title: string
  desc: string
  search: string
  onSearch: (v: string) => void
  isDark: boolean
  onToggleTheme: () => void
}

export function Header({ title, desc, search, onSearch, isDark, onToggleTheme }: HeaderProps) {
  return (
    <header className="header">
      <div style={{ minWidth: 0 }}>
        <h1 className="page-title">{title}</h1>
        <div className="page-desc">{desc}</div>
      </div>
      <div className="spacer" />

      <div className="search-wrap">
        <Icon name="search" size={15} stroke="var(--text-3)" className="search-icon" />
        <input
          className="search-input"
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          placeholder="Buscar documento, pasta…"
        />
      </div>

      <button className="icon-btn" title="Alternar tema" onClick={onToggleTheme}>
        <Icon name={isDark ? 'sun' : 'moon'} size={17} />
      </button>

      <button className="icon-btn" title="Notificações">
        <Icon name="bell" size={17} />
        <span className="notif-dot" />
      </button>
    </header>
  )
}
