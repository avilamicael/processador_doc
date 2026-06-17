// Indicador de confiança reutilizável (S5 — Fase 5, D-02). Espelha StatusPill:
// mapa estático faixa→{rótulo, token} + render <span> token-driven com
// var(--st-${token})/var(--st-${token}-bg). O NÚMERO (0–100%) é a fonte de verdade;
// o rótulo (Alta/Média/Baixa) e a cor são derivados das faixas TRAVADAS do
// 05-UI-SPEC. NÃO usa accent (reservado a CTAs/foco). Reutilizável em S4
// (AttentionPage) e no DocumentDetailModal existente.
//
// Faixas PRESCRITAS (05-UI-SPEC §Color):
//   ≥0.80 → Alta  / token tratado (verde)
//   0.50–0.79 → Média / token leitura (âmbar)
//   <0.50 → Baixa / token erro (vermelho)
// score null/undefined → fallback neutro "—" (sem cor de status, sem quebrar).

type ConfidenceToken = 'tratado' | 'leitura' | 'erro'

interface ConfidenceSpec {
  label: string
  token: ConfidenceToken
}

function resolveConfidence(score: number): ConfidenceSpec {
  if (score >= 0.8) return { label: 'Alta', token: 'tratado' }
  if (score >= 0.5) return { label: 'Média', token: 'leitura' }
  return { label: 'Baixa', token: 'erro' }
}

export function ConfidenceBadge({ score }: { score: number | null | undefined }) {
  // Fallback neutro quando não há score (ex.: quarentena, ainda sem cálculo).
  if (score == null || Number.isNaN(score)) {
    return (
      <span
        className="badge"
        style={{ color: 'var(--text-3)', background: 'var(--surface-3)' }}
      >
        —
      </span>
    )
  }

  const pct = Math.round(score * 100)
  const { label, token } = resolveConfidence(score)
  return (
    <span
      className="badge"
      style={{ color: `var(--st-${token})`, background: `var(--st-${token}-bg)` }}
    >
      <span style={{ fontFamily: 'var(--font-mono)' }}>{pct}%</span>
      {' · '}
      {label}
    </span>
  )
}
