import { useEffect, useState } from 'react'
import type { DryRunRow } from '../types'
import { Icon } from '../components/Icon'
import { useApply, useDryRun, useUndo } from '../hooks/useAutomations'
import { useApprovalMode } from '../hooks/useAttention'

// S4 — Tela de Dry-run / Preview (origem→destino). Core surface da fase (AUT-03):
// o usuário VÊ o que vai acontecer no disco ANTES de aplicar. "Aplicar" só habilita
// depois que o preview carrega. Sinalização de colisão/bloqueio por token de cor
// (informativo: âmbar sufixo D-09 / azul duplicata D-10; vermelho só bloqueio D-07).
//
// Sem visualizador de documento (restrição absoluta): só caminhos como texto mono.

// Badge de sinalização da situação da linha. Texto puro. Cores SEMPRE via tokens
// --st-* (06-UI-SPEC §Cores semânticas): vermelho só bloqueio (D-07); colisão âmbar
// (D-09); duplicata azul (D-10); sem-automação neutro; cópia verde (06.2, D-07);
// pronto verde. Ordem de precedência: bloqueio → sem-automação → duplicata →
// colisão → cópia → pronto (cada saída de cópia é uma linha própria, D-03/D-07).
function SituationBadge({ row }: { row: DryRunRow }) {
  if (row.blocked) {
    return (
      <span
        className="badge"
        style={{ color: 'var(--st-erro)', background: 'var(--st-erro-bg)' }}
        title="Campo usado no nome/pasta está faltando ou inválido. Enviado para revisão antes de aplicar."
      >
        Campo faltando — enviado para revisão
      </span>
    )
  }
  if (row.no_match) {
    return (
      <span
        className="badge badge-off"
        title="Nenhuma automação se aplica a este documento — ele permanece no local de origem."
      >
        Nenhuma automação se aplica — mantido na origem
      </span>
    )
  }
  if (row.skipped_identical) {
    return (
      <span
        className="badge"
        style={{ color: 'var(--st-encontrado)', background: 'var(--st-encontrado-bg)' }}
        title="Esse arquivo já existe no destino (conteúdo idêntico) — será pulado."
      >
        Já existe (idêntico) — pulado
      </span>
    )
  }
  if (row.collision) {
    return (
      <span
        className="badge"
        style={{ color: 'var(--st-leitura)', background: 'var(--st-leitura-bg)' }}
        title="Já existe um arquivo diferente com esse nome — será salvo com sufixo (ex.: nome_1)."
      >
        Renomeado p/ evitar colisão
      </span>
    )
  }
  if (row.action_kind === 'copy') {
    return (
      <span
        className="badge"
        style={{ color: 'var(--st-encontrado)', background: 'var(--st-encontrado-bg)' }}
        title="O arquivo será copiado para o destino. O original permanece onde está."
      >
        Copiado — original mantido
      </span>
    )
  }
  return (
    <span
      className="badge"
      style={{ color: 'var(--st-tratado)', background: 'var(--st-tratado-bg)' }}
      title="O documento está pronto para ser movido/renomeado conforme o pipeline."
    >
      Pronto
    </span>
  )
}

export function DryRunPage() {
  const dryRun = useDryRun()
  const apply = useApply()
  const undo = useUndo()
  // Modo de aprovação (D-03/D-06): quando LIGADO, esta página é a fila de aprovação.
  // O auto-apply de alta confiança já é gateado no worker (12-03); aqui o usuário
  // aprova (= aplicar) ou nega/pula por linha. DESLIGADO = comportamento atual.
  const approvalMode = useApprovalMode()
  const approvalEnabled = approvalMode.data?.enabled ?? false

  const [rows, setRows] = useState<DryRunRow[]>([])
  const [selected, setSelected] = useState<number[]>([])
  const [previewLoaded, setPreviewLoaded] = useState(false)
  // S6 — diálogo de undo: run_id do último lote aplicado (reversível).
  const [undoRunId, setUndoRunId] = useState<string | null>(null)
  const [undoResult, setUndoResult] = useState<string | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)

  // Carrega o preview ao montar (todos os documentos prontos).
  const loadPreview = () => {
    dryRun.mutate([], {
      onSuccess: (res) => {
        setRows(res.rows)
        setPreviewLoaded(true)
      },
    })
  }
  useEffect(() => {
    loadPreview()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Aplicável = vai tocar o disco. Bloqueado (D-07) e sem-automação NÃO materializam
  // — ficam fora da seleção (checkbox disabled).
  const isApplicable = (r: DryRunRow) => !r.blocked && !r.no_match
  const applicable = rows.filter(isApplicable)
  // Multi-saída (06.2): um doc copy+move gera 2+ linhas com o MESMO document_id. O
  // apply enfileira POR DOCUMENTO — dedupe os ids para não enviar/contar/selecionar
  // o mesmo doc duas vezes (WR-02/WR-03).
  const applicableIds = [...new Set(applicable.map((r) => r.document_id))]
  const allSel = applicableIds.length > 0 && selected.length === applicableIds.length

  const toggleSel = (id: number) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))
  const toggleAll = () => setSelected((s) => (s.length === applicableIds.length ? [] : applicableIds.slice()))

  // readyCount conta DOCUMENTOS prontos (não linhas): dedupe e exclui os que só têm
  // saídas idênticas puladas (D-10).
  const readyCount = [
    ...new Set(
      applicable.filter((r) => !r.skipped_identical).map((r) => r.document_id),
    ),
  ].length
  const skippedCount = rows.filter((r) => r.skipped_identical && isApplicable(r)).length
  const noMatchCount = rows.filter((r) => r.no_match).length
  const blockedCount = rows.filter((r) => r.blocked).length

  // "Aplicar" só habilita após o preview carregar (AUT-03) e havendo o que aplicar.
  const canApply = previewLoaded && applicable.length > 0 && !apply.isPending

  const doApply = (ids: number[]) => {
    if (ids.length === 0) return
    apply.mutate(ids, {
      onSuccess: (res) => {
        setUndoRunId(res.run_id)
        setUndoResult(null)
        setSelected([])
        // Recarrega o preview: documentos aplicados saem da lista de prontos.
        loadPreview()
      },
    })
  }

  // "Negar / Pular" (modo de aprovação, D-06): filtro LOCAL apenas — remove TODAS as
  // linhas daquele document_id de `rows` via setRows e tira o id de `selected`. NÃO
  // chama o backend e NÃO move/apaga nenhum arquivo (o move só acontece no aprovar).
  // O documento segue pronto para uma rodada futura. (T-12-11)
  const denyDoc = (id: number) => {
    setRows((rs) => rs.filter((r) => r.document_id !== id))
    setSelected((s) => s.filter((x) => x !== id))
  }

  const confirmUndo = () => {
    if (!undoRunId) return
    undo.mutate(
      { run_id: undoRunId },
      {
        onSuccess: () => {
          setUndoResult('Desfeito. O arquivo voltou ao local de origem.')
          loadPreview()
        },
        onError: () =>
          setUndoResult(
            'O arquivo de destino não foi encontrado no lugar esperado. Restauramos a cópia íntegra preservada pelo sistema para a pasta de origem.',
          ),
      },
    )
  }

  const isLoading = dryRun.isPending && !previewLoaded
  const isError = dryRun.isError && !previewLoaded
  const isEmpty = previewLoaded && rows.length === 0

  // Coluna extra de ações (Aprovar / Negar) só aparece no modo de aprovação.
  const BODY_COLS = approvalEnabled ? 5 : 4

  return (
    <div>
      <div className="sec-head">
        <div className="sec-head-col">
          <h2 className="sec-title">Pré-visualização das automações</h2>
          <p className="sec-desc">
            Confira origem → destino de cada documento antes de aplicar. Nada é movido até
            você confirmar — e toda aplicação pode ser desfeita.
          </p>
        </div>
        <button className="btn-ghost" onClick={loadPreview} disabled={dryRun.isPending}>
          <Icon name="refresh" size={15} />
          {dryRun.isPending ? 'Atualizando…' : 'Atualizar prévia'}
        </button>
      </div>

      {/* Banner do modo de aprovação (apenas quando LIGADO). Texto puro. */}
      {approvalEnabled && (
        <div
          className="card"
          style={{
            padding: '12px 16px',
            marginBottom: 16,
            display: 'flex',
            alignItems: 'flex-start',
            gap: 10,
            borderLeft: '3px solid var(--st-leitura)',
          }}
        >
          <Icon name="alert" size={16} style={{ color: 'var(--st-leitura)', flex: 'none', marginTop: 1 }} />
          <span style={{ fontSize: 13, color: 'var(--text-2)' }}>
            Modo de aprovação ligado — as automações aguardam você. <strong>Aprovar</strong>{' '}
            aplica a automação (move/renomeia); <strong>Negar</strong> deixa o documento
            pronto sem mover — o arquivo não é tocado.
          </span>
        </div>
      )}

      {/* Contagem-resumo do topo (focal point S4) */}
      {previewLoaded && rows.length > 0 && (
        <div className="stat-grid" style={{ marginBottom: 16 }}>
          <div className="card stat-card">
            <div className="stat-head">
              <span className="stat-label">Prontos</span>
              <span className="stat-dot" style={{ background: 'var(--st-tratado)' }} />
            </div>
            <div className="stat-num">{readyCount}</div>
          </div>
          <div className="card stat-card">
            <div className="stat-head">
              <span className="stat-label">Duplicatas puladas</span>
              <span className="stat-dot" style={{ background: 'var(--st-encontrado)' }} />
            </div>
            <div className="stat-num">{skippedCount}</div>
          </div>
          <div className="card stat-card">
            <div className="stat-head">
              <span className="stat-label">Sem automação</span>
              <span className="stat-dot" style={{ background: 'var(--st-leitura)' }} />
            </div>
            <div className="stat-num">{noMatchCount}</div>
          </div>
          <div className="card stat-card">
            <div className="stat-head">
              <span className="stat-label">Bloqueados → revisão</span>
              <span className="stat-dot" style={{ background: 'var(--st-erro)' }} />
            </div>
            <div className="stat-num">{blockedCount}</div>
          </div>
        </div>
      )}

      <div className="card" style={{ overflow: 'hidden' }}>
        {/* toolbar com CTAs de aplicar */}
        <div className="table-toolbar">
          <span className="foot-text">
            {selected.length > 0
              ? `${selected.length} selecionado(s)`
              : `${applicableIds.length} documento(s) prontos`}
          </span>
          <div className="spacer" />
          {selected.length > 0 && (
            <button
              className="btn-primary"
              onClick={() => doApply(selected)}
              disabled={!canApply}
              title="Aplicar as automações aos documentos selecionados"
            >
              <Icon name="bolt" size={15} />
              Aplicar selecionados
            </button>
          )}
          {selected.length === 0 && (
            <button
              className="btn-primary"
              onClick={() => doApply(applicableIds)}
              disabled={!canApply}
              title="Aplicar as automações a todos os documentos prontos"
            >
              <Icon name="bolt" size={15} />
              {apply.isPending ? 'Aplicando…' : 'Aplicar automações'}
            </button>
          )}
        </div>

        <div className="table-scroll">
          <table className="docs">
            <thead>
              <tr>
                <th className="check">
                  <button
                    className={allSel ? 'checkbox on' : 'checkbox'}
                    onClick={toggleAll}
                    aria-label="Selecionar todos os documentos aplicáveis"
                  >
                    <Icon name="check" size={11} stroke="#fff" style={{ opacity: allSel ? 1 : 0 }} />
                  </button>
                </th>
                <th>Origem</th>
                <th>Destino</th>
                <th>Situação</th>
                {approvalEnabled && <th>Ações</th>}
              </tr>
            </thead>
            <tbody>
              {isLoading &&
                Array.from({ length: 4 }).map((_, i) => (
                  <tr key={`sk-${i}`}>
                    <td colSpan={BODY_COLS}>
                      <div style={{ height: 18, borderRadius: 5, background: 'var(--surface-3)', opacity: 0.7 }} />
                    </td>
                  </tr>
                ))}

              {isError && (
                <tr>
                  <td colSpan={BODY_COLS}>
                    <div style={{ textAlign: 'center', padding: '48px 24px' }}>
                      <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>
                        Não foi possível carregar.
                      </div>
                      <p style={{ fontSize: 13, color: 'var(--text-3)', margin: '0 0 16px' }}>
                        Verifique se o servidor está rodando e tente de novo.
                      </p>
                      <button className="btn-primary" onClick={loadPreview}>
                        <Icon name="refresh" size={15} />
                        Tentar de novo
                      </button>
                    </div>
                  </td>
                </tr>
              )}

              {isEmpty && (
                <tr>
                  <td colSpan={BODY_COLS}>
                    <div style={{ textAlign: 'center', padding: '48px 24px' }}>
                      <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>
                        Nenhum documento pronto para automação
                      </div>
                      <p style={{ fontSize: 13, color: 'var(--text-3)', margin: 0, maxWidth: 480, marginInline: 'auto' }}>
                        Documentos de alta confiança são aplicados automaticamente; os demais
                        aguardam revisão.
                      </p>
                    </div>
                  </td>
                </tr>
              )}

              {previewLoaded &&
                rows.map((r, i) => {
                  const sel = selected.includes(r.document_id)
                  const selectable = isApplicable(r)
                  return (
                    // Multi-saída: várias linhas compartilham document_id (copy+move) —
                    // a chave une o id, o tipo da saída e o índice p/ ser única (WR-01).
                    <tr
                      key={`${r.document_id}-${r.action_kind ?? 'single'}-${i}`}
                      className={sel ? 'selected' : undefined}
                    >
                      <td>
                        <button
                          className={sel ? 'checkbox on' : 'checkbox'}
                          onClick={() => toggleSel(r.document_id)}
                          disabled={!selectable}
                          aria-label={`Selecionar ${r.original_filename}`}
                          style={{ opacity: selectable ? 1 : 0.35 }}
                        >
                          <Icon name="check" size={11} stroke="#fff" style={{ opacity: sel ? 1 : 0 }} />
                        </button>
                      </td>
                      <td className="cell-mono" style={{ wordBreak: 'break-all' }}>
                        {r.source_path ?? r.original_filename}
                      </td>
                      <td className="cell-mono" style={{ wordBreak: 'break-all' }}>
                        {r.dest_path ?? '—'}
                      </td>
                      <td>
                        <SituationBadge row={r} />
                      </td>
                      {approvalEnabled && (
                        <td>
                          {selectable ? (
                            <div style={{ display: 'flex', gap: 6 }}>
                              <button
                                className="row-action"
                                aria-label={`Aprovar e aplicar ${r.original_filename}`}
                                title="Aprovar: aplica a automação (move/renomeia este documento)"
                                onClick={() => doApply([r.document_id])}
                                disabled={!canApply}
                                style={{ width: 'auto', padding: '6px 10px', gap: 6, color: 'var(--st-tratado)' }}
                              >
                                <Icon name="check" size={14} />
                                Aprovar
                              </button>
                              <button
                                className="row-action"
                                aria-label={`Negar ou pular ${r.original_filename}`}
                                title="Negar / Pular: tira o documento desta rodada sem mover o arquivo (nada é tocado)"
                                onClick={() => denyDoc(r.document_id)}
                                style={{ width: 'auto', padding: '6px 10px', gap: 6, color: 'var(--text-2)' }}
                              >
                                <Icon name="undo" size={14} />
                                Negar / Pular
                              </button>
                            </div>
                          ) : (
                            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>—</span>
                          )}
                        </td>
                      )}
                    </tr>
                  )
                })}
            </tbody>
          </table>
        </div>

        {/* footer: ação de desfazer o último lote aplicado (não-destrutiva) */}
        <div className="table-foot">
          {undoRunId && (
            <>
              <span className="foot-text" style={{ color: 'var(--text-3)' }}>
                Último lote aplicado pode ser revertido.
              </span>
              <div className="spacer" />
              <button
                className="row-action"
                aria-label="Desfazer aplicação do último lote"
                title="Desfazer aplicação do último lote"
                onClick={() => {
                  setUndoResult(null)
                  setConfirmOpen(true)
                }}
                style={{ width: 'auto', padding: '6px 10px', gap: 6, color: 'var(--text-2)' }}
              >
                <Icon name="undo" size={15} />
                Desfazer aplicação
              </button>
            </>
          )}
        </div>
      </div>

      {/* S6 — Confirmação de Desfazer (comunica reversibilidade, nunca exclusão) */}
      {confirmOpen && undoRunId && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,.45)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 50,
          }}
        >
          <div className="card" style={{ padding: 22, maxWidth: 460, width: '90%' }}>
            <h3 className="sec-title" style={{ fontSize: 15, marginBottom: 10 }}>
              Desfazer aplicação
            </h3>
            {undoResult ? (
              <p style={{ fontSize: 13, color: 'var(--text-2)', margin: '0 0 18px' }}>
                {undoResult}
              </p>
            ) : (
              <p style={{ fontSize: 13, color: 'var(--text-2)', margin: '0 0 18px' }}>
                Os arquivos movidos deste lote voltam ao local de origem (se o destino tiver
                sumido, restauramos a cópia íntegra preservada pelo sistema). As cópias criadas
                são apagadas do destino — o original nunca é tocado. Nenhum arquivo se perde.
              </p>
            )}
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button
                className="btn-ghost"
                onClick={() => {
                  setConfirmOpen(false)
                  setUndoResult(null)
                }}
                disabled={undo.isPending}
              >
                {undoResult ? 'Fechar' : 'Manter como está'}
              </button>
              {!undoResult && (
                <button className="btn-primary" onClick={confirmUndo} disabled={undo.isPending}>
                  {undo.isPending ? 'Desfazendo…' : 'Desfazer aplicação'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
