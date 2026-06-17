import type { DocState } from '../types'

// Pílula de status mapeando ESTADOS DE DOMÍNIO REAIS → label pt-BR → token --st-*
// (UI-SPEC tabela de cores, autoritativa). A Fase 2 NÃO alcança extração, logo:
//  - o estado terminal é processando + last_completed_step="aguardando_extracao"
//    → rótulo "Aguardando extração", azul muted (reusa --st-encontrado), NUNCA verde;
//  - "Concluído"/--st-tratado fica RESERVADO (não setado por esta fase).
//
// Cada estado mapeia para um token visual do design (encontrado/leitura/tratado/
// erro/quarentena) mantendo o estilo token-driven var(--st-${token}).

type PillToken = 'encontrado' | 'leitura' | 'tratado' | 'erro' | 'quarentena'

interface PillSpec {
  label: string
  token: PillToken
}

const STATE_PILL: Record<DocState, PillSpec> = {
  recebido: { label: 'Na fila', token: 'encontrado' },
  processando: { label: 'Processando', token: 'leitura' },
  em_revisao: { label: 'Em revisão', token: 'leitura' },
  concluido: { label: 'Concluído', token: 'tratado' },
  quarentena: { label: 'Quarentena', token: 'quarentena' },
  falha: { label: 'Falha', token: 'erro' },
}

function resolvePill(state: DocState, lastCompletedStep?: string | null): PillSpec {
  // Estado terminal da Fase 2: processando + marcador de "aguardando extração".
  // Azul muted (--st-encontrado), visualmente distinto de "Processando", nunca verde.
  if (state === 'processando' && lastCompletedStep === 'aguardando_extracao') {
    return { label: 'Aguardando extração', token: 'encontrado' }
  }
  return STATE_PILL[state]
}

export function StatusPill({
  state,
  lastCompletedStep,
}: {
  state: DocState
  lastCompletedStep?: string | null
}) {
  const { label, token } = resolvePill(state, lastCompletedStep)
  return (
    <span className="pill" style={{ color: `var(--st-${token})`, background: `var(--st-${token}-bg)` }}>
      <span className="pill-dot" style={{ background: `var(--st-${token})` }} />
      {label}
    </span>
  )
}
