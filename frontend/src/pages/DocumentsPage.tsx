import { DOCS } from '../data/mock'
import type { DocStatus, StatusFilter } from '../types'
import { Icon } from '../components/Icon'
import { StatusPill } from '../components/StatusPill'

interface DocumentsPageProps {
  search: string
  status: StatusFilter
  onStatus: (s: StatusFilter) => void
  selected: number[]
  onToggleSel: (id: number) => void
  onToggleAll: (ids: number[]) => void
}

const STAT_CARDS: { key: DocStatus; label: string; sub: string }[] = [
  { key: 'encontrado', label: 'Encontrados', sub: 'aguardando processamento' },
  { key: 'leitura', label: 'Em leitura', sub: 'extração em andamento' },
  { key: 'tratado', label: 'Tratados', sub: 'prontos / arquivados' },
  { key: 'erro', label: 'Erros', sub: 'requerem atenção' },
]

function initials(name: string): string {
  if (!name || name === '—') return ''
  return name.split(/[ .]+/).filter(Boolean).map((x) => x[0]).join('').slice(0, 2).toUpperCase()
}

export function DocumentsPage({ search, status, onStatus, selected, onToggleSel, onToggleAll }: DocumentsPageProps) {
  const counts = {
    encontrado: DOCS.filter((d) => d.status === 'encontrado').length,
    leitura: DOCS.filter((d) => d.status === 'leitura').length,
    tratado: DOCS.filter((d) => d.status === 'tratado').length,
    erro: DOCS.filter((d) => d.status === 'erro').length,
    total: DOCS.length,
  }

  const q = search.trim().toLowerCase()
  const filtered = DOCS.filter(
    (d) =>
      (status === 'todos' || d.status === status) &&
      (q === '' || (d.name + d.folder + d.type + d.tmpl).toLowerCase().includes(q)),
  )
  const allIds = filtered.map((d) => d.id)
  const allSel = filtered.length > 0 && selected.length === filtered.length

  const chips: { key: StatusFilter; label: string; count: number }[] = [
    { key: 'todos', label: 'Todos', count: counts.total },
    { key: 'encontrado', label: 'Encontrado', count: counts.encontrado },
    { key: 'leitura', label: 'Em leitura', count: counts.leitura },
    { key: 'tratado', label: 'Tratado', count: counts.tratado },
    { key: 'erro', label: 'Erro', count: counts.erro },
  ]

  return (
    <div>
      {/* stat row */}
      <div className="stat-grid">
        {STAT_CARDS.map((c) => (
          <div key={c.key} className="card stat-card">
            <div className="stat-head">
              <span className="stat-label">{c.label}</span>
              <span className="stat-dot" style={{ background: `var(--st-${c.key})` }} />
            </div>
            <div className="stat-num">{counts[c.key]}</div>
            <div className="stat-sub">{c.sub}</div>
          </div>
        ))}
      </div>

      {/* table card */}
      <div className="card" style={{ overflow: 'hidden' }}>
        {/* toolbar */}
        <div className="table-toolbar">
          <div className="chips">
            {chips.map((chip) => (
              <button
                key={chip.key}
                className={status === chip.key ? 'chip active' : 'chip'}
                onClick={() => onStatus(chip.key)}
              >
                <span>{chip.label}</span>
                <span className="chip-count">{chip.count}</span>
              </button>
            ))}
          </div>
          <div className="spacer" />
          <button className="btn-ghost">
            <Icon name="filter" size={15} />
            Filtros
          </button>
          <button className="btn-primary">
            <Icon name="refresh" size={15} />
            Forçar varredura
          </button>
        </div>

        {/* table */}
        <div className="table-scroll">
          <table className="docs">
            <thead>
              <tr>
                <th className="check">
                  <button
                    className={allSel ? 'checkbox on' : 'checkbox'}
                    onClick={() => onToggleAll(allIds)}
                    aria-label="Selecionar todos"
                  >
                    <Icon name="check" size={11} stroke="#fff" style={{ opacity: allSel ? 1 : 0 }} />
                  </button>
                </th>
                <th>Arquivo</th>
                <th>Pasta de origem</th>
                <th>Tipo</th>
                <th>Template</th>
                <th>Status</th>
                <th className="right">Tamanho</th>
                <th>Data</th>
                <th>Responsável</th>
                <th className="right">Ações</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((d) => {
                const sel = selected.includes(d.id)
                const init = initials(d.who)
                return (
                  <tr key={d.id} className={sel ? 'selected' : undefined}>
                    <td>
                      <button
                        className={sel ? 'checkbox on' : 'checkbox'}
                        onClick={() => onToggleSel(d.id)}
                        aria-label={`Selecionar ${d.name}`}
                      >
                        <Icon name="check" size={11} stroke="#fff" style={{ opacity: sel ? 1 : 0 }} />
                      </button>
                    </td>
                    <td>
                      <div className="file-cell">
                        <Icon name="docMini" size={17} stroke="var(--text-3)" style={{ flex: 'none' }} />
                        <span className="file-name">{d.name}</span>
                      </div>
                    </td>
                    <td className="cell-mono">{d.folder}</td>
                    <td>{d.type}</td>
                    <td>{d.tmpl}</td>
                    <td>
                      <StatusPill status={d.status} />
                    </td>
                    <td className="right cell-mono">{d.size}</td>
                    <td style={{ whiteSpace: 'nowrap' }}>{d.date}</td>
                    <td>
                      <div className="who-wrap">
                        {init && <span className="who-chip">{init}</span>}
                        <span className="who-name">{d.who}</span>
                      </div>
                    </td>
                    <td>
                      <div className="row-actions">
                        <button className="row-action" title="Visualizar"><Icon name="eye" size={16} /></button>
                        <button className="row-action" title="Baixar"><Icon name="download" size={16} /></button>
                        <button className="row-action" title="Mais"><Icon name="dots" size={16} /></button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {/* footer */}
        <div className="table-foot">
          <span className="foot-text">Mostrando {filtered.length} de {counts.total} documentos</span>
          <div className="spacer" />
          <span className="foot-text">Linhas por página: 25</span>
          <div style={{ display: 'flex', gap: 4 }}>
            <button className="pg disabled">‹</button>
            <button className="pg active">1</button>
            <button className="pg">›</button>
          </div>
        </div>
      </div>
    </div>
  )
}
