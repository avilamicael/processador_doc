import type { DocStatus } from '../types'
import { STATUS_LABELS } from '../data/mock'

// Pílula de status (Encontrado / Em leitura / Tratado / Erro) com cores do tema.
export function StatusPill({ status }: { status: DocStatus }) {
  return (
    <span className="pill" style={{ color: `var(--st-${status})`, background: `var(--st-${status}-bg)` }}>
      <span className="pill-dot" style={{ background: `var(--st-${status})` }} />
      {STATUS_LABELS[status]}
    </span>
  )
}
