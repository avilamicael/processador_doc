import type { DocState, StatusFilter } from '../types'
import { Icon } from '../components/Icon'
import { StatusPill } from '../components/StatusPill'
import { useDocuments, useDuplicatesCount, useRescan } from '../hooks/useDocuments'

interface DocumentsPageProps {
  search: string
  status: StatusFilter
  onStatus: (s: StatusFilter) => void
  selected: number[]
  onToggleSel: (id: number) => void
  onToggleAll: (ids: number[]) => void
}

// Stat-cards: estados de domínio reais (UI-SPEC). Cada card lê um count da API e
// usa o token visual correspondente. "Aguardando extração" deriva do estado
// terminal da Fase 2; aqui o card agrega por estado de domínio (processando).
const STAT_CARDS: { key: DocState; label: string; sub: string }[] = [
  { key: 'recebido', label: 'Na fila', sub: 'aguardando processamento' },
  { key: 'processando', label: 'Processando', sub: 'ingestão / separação' },
  { key: 'concluido', label: 'Concluídos', sub: 'prontos / arquivados' },
  { key: 'falha', label: 'Falhas', sub: 'requerem atenção' },
]

const STAT_TOKEN: Record<DocState, 'encontrado' | 'leitura' | 'tratado' | 'erro'> = {
  recebido: 'encontrado',
  processando: 'leitura',
  em_revisao: 'leitura',
  concluido: 'tratado',
  quarentena: 'leitura',
  falha: 'erro',
}

// Formata bytes (quando a API expõe tamanho); ausência → travessão neutro.
function formatSize(size?: number | null): string {
  if (size == null) return '—'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(0)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

// Data legível pt-BR a partir do ISO do backend.
function formatDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('pt-BR', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function DocumentsPage({ search, status, onStatus, selected, onToggleSel, onToggleAll }: DocumentsPageProps) {
  const docsQuery = useDocuments()
  const dupQuery = useDuplicatesCount()
  const rescan = useRescan()

  const data = docsQuery.data
  const items = data?.items ?? []
  const counts = data?.counts ?? {}
  const total = data?.total ?? 0

  const getCount = (k: DocState) => counts[k] ?? 0

  const q = search.trim().toLowerCase()
  const filtered = items.filter(
    (d) =>
      (status === 'todos' || d.state === status) &&
      (q === '' ||
        (d.original_filename + (d.source_folder_path ?? '')).toLowerCase().includes(q)),
  )
  const allIds = filtered.map((d) => d.id)
  const allSel = filtered.length > 0 && selected.length === filtered.length

  const chips: { key: StatusFilter; label: string; count: number }[] = [
    { key: 'todos', label: 'Todos', count: total },
    { key: 'recebido', label: 'Na fila', count: getCount('recebido') },
    { key: 'processando', label: 'Processando', count: getCount('processando') },
    { key: 'falha', label: 'Falha', count: getCount('falha') },
  ]

  // Estados da tela (renderizados DENTRO do card da tabela — foco constante).
  const isInitialLoading = docsQuery.isLoading && !data
  const isError = docsQuery.isError && !data
  const isEmpty = !isInitialLoading && !isError && filtered.length === 0
  const isRefetching = docsQuery.isFetching && !!data

  const dupCount = dupQuery.data?.count ?? 0

  // Número de colunas do corpo da tabela (para colspan dos estados internos).
  const BODY_COLS = 6

  return (
    <div>
      {/* stat row */}
      <div className="stat-grid">
        {STAT_CARDS.map((c) => (
          <div key={c.key} className="card stat-card">
            <div className="stat-head">
              <span className="stat-label">{c.label}</span>
              <span className="stat-dot" style={{ background: `var(--st-${STAT_TOKEN[c.key]})` }} />
            </div>
            <div className="stat-num">{getCount(c.key)}</div>
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
          <button
            className="btn-primary"
            onClick={() => rescan.mutate()}
            disabled={rescan.isPending}
            title="Forçar uma varredura das pastas monitoradas agora"
          >
            <Icon name="refresh" size={15} />
            {rescan.isPending ? 'Varrendo…' : 'Forçar varredura'}
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
                <th>Status</th>
                <th className="right">Tamanho</th>
                <th>Data</th>
              </tr>
            </thead>
            <tbody>
              {isInitialLoading &&
                Array.from({ length: 4 }).map((_, i) => (
                  <tr key={`sk-${i}`}>
                    <td colSpan={BODY_COLS + 1}>
                      <div
                        style={{
                          height: 18,
                          borderRadius: 5,
                          background: 'var(--surface-3)',
                          opacity: 0.7,
                        }}
                      />
                    </td>
                  </tr>
                ))}

              {isError && (
                <tr>
                  <td colSpan={BODY_COLS + 1}>
                    <div style={{ textAlign: 'center', padding: '48px 24px' }}>
                      <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>
                        Não foi possível carregar os documentos.
                      </div>
                      <p style={{ fontSize: 13, color: 'var(--text-3)', margin: '0 0 16px' }}>
                        Verifique se o serviço está em execução e tente novamente.
                      </p>
                      <button className="btn-primary" onClick={() => docsQuery.refetch()}>
                        <Icon name="refresh" size={15} />
                        Tentar novamente
                      </button>
                    </div>
                  </td>
                </tr>
              )}

              {isEmpty && (
                <tr>
                  <td colSpan={BODY_COLS + 1}>
                    <div style={{ textAlign: 'center', padding: '48px 24px' }}>
                      <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>
                        Nenhum documento ainda
                      </div>
                      <p style={{ fontSize: 13, color: 'var(--text-3)', margin: 0, maxWidth: 460, marginInline: 'auto' }}>
                        Os documentos aparecem aqui automaticamente quando arquivos chegam nas
                        pastas monitoradas. Configure uma pasta em Configurações → Pastas monitoradas.
                      </p>
                    </div>
                  </td>
                </tr>
              )}

              {!isInitialLoading &&
                !isError &&
                filtered.map((d) => {
                  const sel = selected.includes(d.id)
                  return (
                    <tr key={d.id} className={sel ? 'selected' : undefined}>
                      <td>
                        <button
                          className={sel ? 'checkbox on' : 'checkbox'}
                          onClick={() => onToggleSel(d.id)}
                          aria-label={`Selecionar ${d.original_filename}`}
                        >
                          <Icon name="check" size={11} stroke="#fff" style={{ opacity: sel ? 1 : 0 }} />
                        </button>
                      </td>
                      <td>
                        <div className="file-cell">
                          <Icon name="docMini" size={17} stroke="var(--text-3)" style={{ flex: 'none' }} />
                          <span className="file-name">{d.original_filename}</span>
                        </div>
                      </td>
                      <td className="cell-mono">{d.source_folder_path ?? '—'}</td>
                      <td>
                        <StatusPill state={d.state} lastCompletedStep={d.last_completed_step} />
                      </td>
                      <td className="right cell-mono">{formatSize(d.size)}</td>
                      <td style={{ whiteSpace: 'nowrap' }}>{formatDate(d.created_at)}</td>
                    </tr>
                  )
                })}
            </tbody>
          </table>
        </div>

        {/* footer */}
        <div className="table-foot">
          <span className="foot-text">
            Mostrando {filtered.length} de {total} documentos
          </span>
          {isRefetching && (
            <span className="foot-text" style={{ color: 'var(--text-3)', marginLeft: 12 }}>
              Atualizando…
            </span>
          )}
          <div className="spacer" />
          {dupCount > 0 && (
            <span
              className="foot-text"
              style={{ color: 'var(--text-3)' }}
              title="Arquivos com conteúdo idêntico a documentos já ingeridos não são reprocessados."
            >
              {dupCount} {dupCount === 1 ? 'duplicado ignorado' : 'duplicados ignorados'}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
