import { useEffect, useState } from 'react'
import type { DryRunRow } from '../types'
import { Icon } from '../components/Icon'
import { useApply, useDryRun, useUndo } from '../hooks/useAutomations'

// S4 — Tela de Dry-run / Preview (origem→destino). Core surface da fase (AUT-03):
// o usuário VÊ o que vai acontecer no disco ANTES de aplicar. "Aplicar" só habilita
// depois que o preview carrega. Sinalização de colisão/bloqueio por token de cor
// (informativo: âmbar sufixo D-09 / azul duplicata D-10; vermelho só bloqueio D-07).
//
// Sem visualizador de documento (restrição absoluta): só caminhos como texto mono.

// Badge de sinalização da linha (informativo vs bloqueio). Texto puro.
function CollisionBadge({ row }: { row: DryRunRow }) {
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
        title="Já existe um arquivo diferente com esse nome — será salvo com sufixo para evitar colisão."
      >
        Renomeado p/ evitar colisão
      </span>
    )
  }
  return (
    <span className="badge" style={{ color: 'var(--st-tratado)', background: 'var(--st-tratado-bg)' }}>
      Pronto
    </span>
  )
}

export function DryRunPage() {
  const dryRun = useDryRun()
  const apply = useApply()
  const undo = useUndo()

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

  // Linhas aplicáveis = não bloqueadas e não duplicatas idênticas (essas são no-op).
  const applicable = rows.filter((r) => !r.blocked)
  const applicableIds = applicable.map((r) => r.document_id)
  const allSel = applicable.length > 0 && selected.length === applicable.length

  const toggleSel = (id: number) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))
  const toggleAll = () => setSelected((s) => (s.length === applicableIds.length ? [] : applicableIds.slice()))

  const movedCount = applicable.filter((r) => !r.skipped_identical).length
  const skippedCount = rows.filter((r) => r.skipped_identical).length
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

  const BODY_COLS = 4

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

      {/* Contagem-resumo do topo (focal point S4) */}
      {previewLoaded && rows.length > 0 && (
        <div className="stat-grid" style={{ marginBottom: 16 }}>
          <div className="card stat-card">
            <div className="stat-head">
              <span className="stat-label">Serão movidos</span>
              <span className="stat-dot" style={{ background: 'var(--st-tratado)' }} />
            </div>
            <div className="stat-num">{movedCount}</div>
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
              : `${applicable.length} documento(s) prontos`}
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
                rows.map((r) => {
                  const sel = selected.includes(r.document_id)
                  return (
                    <tr key={r.document_id} className={sel ? 'selected' : undefined}>
                      <td>
                        <button
                          className={sel ? 'checkbox on' : 'checkbox'}
                          onClick={() => toggleSel(r.document_id)}
                          disabled={r.blocked}
                          aria-label={`Selecionar ${r.original_filename}`}
                          style={{ opacity: r.blocked ? 0.35 : 1 }}
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
                        <CollisionBadge row={r} />
                      </td>
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
                Os arquivos deste lote voltam ao local de origem. Se o destino tiver sido movido,
                restauramos a cópia íntegra preservada pelo sistema. Nada é apagado.
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
