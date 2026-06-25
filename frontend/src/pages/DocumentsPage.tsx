import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { DocState, Page, StatusFilter } from '../types'
import { Icon } from '../components/Icon'
import { StatusPill } from '../components/StatusPill'
import { useApproveDocument, useDeleteDocuments, useDocuments, useDuplicatesCount, useRescan, useUndoDocument } from '../hooks/useDocuments'
import { getDocumentAudit, getDocumentDetail } from '../lib/api'

interface DocumentsPageProps {
  search: string
  status: StatusFilter
  onStatus: (s: StatusFilter) => void
  selected: number[]
  onToggleSel: (id: number) => void
  onToggleAll: (ids: number[]) => void
  // Limpa a seleção no App (vive lá) — chamado no sucesso da remoção.
  onClearSel: () => void
  // D-11: navegar para outra página (ex.: 'dryrun') a partir da CTA da linha.
  onNavigate?: (page: Page) => void
}

// D-10/D-11: condição derivada "pronto, aguardando ação" — doc fica DE PROPÓSITO em
// processando + last_completed_step = "classificado" (casa com CLASSIFIED_STEP,
// backend/app/classification/stage.py:69). Mesma condição do ramo do StatusPill;
// usada aqui para decidir quando exibir a CTA. NÃO é estado persistido novo.
function isClassifiedReady(state: DocState, lastCompletedStep?: string | null): boolean {
  return state === 'processando' && lastCompletedStep === 'classificado'
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

export function DocumentsPage({ search, status, onStatus, selected, onToggleSel, onToggleAll, onClearSel, onNavigate }: DocumentsPageProps) {
  const docsQuery = useDocuments()
  const dupQuery = useDuplicatesCount()
  const rescan = useRescan()
  const deleteDocs = useDeleteDocuments()
  const approve = useApproveDocument()

  // S4 — detalhe de classificação somente leitura (TPL-03/04). Abre num modal ao
  // clicar no nome do arquivo; busca GET /documents/{id} sob demanda.
  const [openDocId, setOpenDocId] = useState<number | null>(null)
  // Confirmação destrutiva da remoção em lote (só registro — nunca o arquivo).
  const [confirmDelete, setConfirmDelete] = useState(false)

  // Item 3/D-05: toast efêmero pós-"Forçar varredura" (sem lib de toast — estado
  // local + timeout). Mostra quantos foram enfileirados e quantos pulados por
  // duplicata, para o /rescan não "parecer que não fez nada".
  const [rescanToast, setRescanToast] = useState<string | null>(null)
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    return () => {
      if (toastTimer.current) clearTimeout(toastTimer.current)
    }
  }, [])

  const runRescan = () => {
    rescan.mutate(undefined, {
      onSuccess: (r) => {
        const enq = r.enqueued
        const dup = r.skipped_duplicates
        const enqTxt = `${enq} ${enq === 1 ? 'novo enfileirado' : 'novos enfileirados'}`
        const dupTxt = `${dup} ${dup === 1 ? 'pulado por já existir' : 'pulados por já existirem'}`
        setRescanToast(`${enqTxt}, ${dupTxt}`)
        if (toastTimer.current) clearTimeout(toastTimer.current)
        toastTimer.current = setTimeout(() => setRescanToast(null), 6000)
      },
    })
  }

  const confirmRemove = () => {
    deleteDocs.mutate(selected, {
      onSuccess: () => {
        onClearSel()
        setConfirmDelete(false)
      },
    })
  }

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
          {selected.length > 0 && (
            <button
              className="btn-primary"
              style={{ background: 'var(--st-erro)' }}
              onClick={() => setConfirmDelete(true)}
              disabled={deleteDocs.isPending}
              title="Remover os documentos selecionados da lista (não apaga arquivos)"
            >
              <Icon name="trash" size={15} />
              {deleteDocs.isPending
                ? 'Removendo…'
                : `Remover (${selected.length})`}
            </button>
          )}
          <button
            className="btn-primary"
            onClick={runRescan}
            disabled={rescan.isPending}
            title="Forçar uma varredura das pastas monitoradas agora"
          >
            <Icon name="refresh" size={15} />
            {rescan.isPending ? 'Varrendo…' : 'Forçar varredura'}
          </button>
        </div>

        {/* Toast efêmero pós-varredura (D-05) — mensagem neutra no estilo do chip
            de footer (var(--text-3)); valor TEXTO PURO, some sozinho após ~6s. */}
        {rescanToast && (
          <div
            role="status"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '8px 16px',
              fontSize: 13,
              color: 'var(--text-3)',
              borderBottom: '1px solid var(--border)',
            }}
          >
            <Icon name="check" size={14} stroke="var(--text-3)" />
            <span>{rescanToast}</span>
          </div>
        )}

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
                        <button
                          className="file-cell"
                          onClick={() => setOpenDocId(d.id)}
                          aria-label={`Ver classificação de ${d.original_filename}`}
                          style={{
                            background: 'transparent',
                            border: 0,
                            padding: 0,
                            cursor: 'pointer',
                            textAlign: 'left',
                          }}
                        >
                          <Icon name="docMini" size={17} stroke="var(--text-3)" style={{ flex: 'none' }} />
                          <span className="file-name">{d.original_filename}</span>
                        </button>
                      </td>
                      <td className="cell-mono">{d.source_folder_path ?? '—'}</td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                          <StatusPill state={d.state} lastCompletedStep={d.last_completed_step} />
                          {/* D-11/D-12: CTA na própria linha quando o doc está "pronto".
                              "Pré-visualizar" navega ao dry-run; "Aprovar" dispara o POST
                              approve (backend decide a conclusão — sem auto-conclude aqui). */}
                          {isClassifiedReady(d.state, d.last_completed_step) && (
                            <span style={{ display: 'inline-flex', gap: 6 }}>
                              <button
                                className="btn-ghost"
                                style={{ height: 26, padding: '0 10px', fontSize: 12 }}
                                onClick={() => onNavigate?.('dryrun')}
                                title="Conferir origem → destino antes de aplicar"
                              >
                                Pré-visualizar
                              </button>
                              <button
                                className="btn-primary"
                                style={{ height: 26, padding: '0 10px', fontSize: 12 }}
                                onClick={() => approve.mutate(d.id)}
                                disabled={approve.isPending}
                                title="Aprovar este documento e executar as automações configuradas"
                              >
                                {approve.isPending && approve.variables === d.id ? 'Aprovando…' : 'Aprovar'}
                              </button>
                            </span>
                          )}
                        </div>
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

      {/* S4 — Detalhe de classificação somente leitura (TPL-03/04) */}
      {openDocId != null && (
        <DocumentDetailModal docId={openDocId} onClose={() => setOpenDocId(null)} />
      )}

      {/* Confirmação destrutiva da remoção em lote — reforça que NENHUM arquivo é
          apagado/movido (constraint forte do projeto). Reusa o padrão do modal de
          remoção da PastasTab (overlay fixed + card). */}
      {confirmDelete && (
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
              Remover {selected.length} {selected.length === 1 ? 'documento' : 'documentos'} da lista?
            </h3>
            <p style={{ fontSize: 13, color: 'var(--text-2)', margin: '0 0 18px' }}>
              Isto remove apenas o registro no aplicativo — os arquivos originais{' '}
              <b>NÃO são apagados nem movidos</b>. Se um arquivo ainda estiver numa pasta
              monitorada, ele pode ser reprocessado numa próxima varredura.
            </p>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button
                className="btn-ghost"
                onClick={() => setConfirmDelete(false)}
                disabled={deleteDocs.isPending}
              >
                Manter
              </button>
              <button
                className="btn-primary"
                style={{ background: 'var(--st-erro)' }}
                onClick={confirmRemove}
                disabled={deleteDocs.isPending}
              >
                {deleteDocs.isPending ? 'Removendo…' : 'Remover'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// Modal somente leitura: classificação de um documento (template casado + campos
// bruto/normalizado com marca válido/inválido, ou estado de quarentena). NÃO
// edita/resolve nada nesta fase (Fase 5). Valores renderizados como TEXTO PURO
// (React, sem dangerouslySetInnerHTML — T-04-12).
function DocumentDetailModal({ docId, onClose }: { docId: number; onClose: () => void }) {
  const detailQuery = useQuery({
    queryKey: ['document-detail', docId],
    queryFn: () => getDocumentDetail(docId),
  })

  // Item 1/D-02: operações aplicadas (origem→destino) lidas do AuditLog. Alimenta
  // a seção "Operações aplicadas" e o botão "Reverter para a origem" (can_undo).
  const auditQuery = useQuery({
    queryKey: ['document-audit', docId],
    queryFn: () => getDocumentAudit(docId),
  })
  const undo = useUndoDocument()
  // Confirmação destrutiva antes de reverter (molde do confirmDelete da lista).
  const [confirmUndo, setConfirmUndo] = useState(false)

  const detail = detailQuery.data
  const cls = detail?.classification ?? null
  const isQuarantine = cls != null && cls.template_id == null

  const audit = auditQuery.data
  // Apenas as operações de fato materializadas (origem→destino reais).
  const doneOps = audit?.items.filter((it) => it.status === 'done') ?? []
  const canUndo = audit?.can_undo ?? false

  const doUndo = () => {
    undo.mutate(docId, {
      onSuccess: () => {
        setConfirmUndo(false)
        // O doc reabre (CONCLUIDO→PROCESSANDO); as queries do detalhe/audit/lista
        // são invalidadas no hook. Fecha o modal para refletir o novo estado.
        onClose()
      },
    })
  }

  return (
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
      onClick={onClose}
    >
      <div
        className="card"
        style={{ padding: 22, maxWidth: 640, width: '92%', maxHeight: '85vh', overflow: 'auto' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sec-head" style={{ marginBottom: 14 }}>
          <div className="sec-head-col">
            <h3 className="sec-title" style={{ fontSize: 15 }}>
              Classificação
            </h3>
            {detail && (
              <p className="sec-desc" style={{ fontFamily: 'var(--font-mono)', fontSize: 12.5 }}>
                {detail.original_filename}
              </p>
            )}
          </div>
          <button className="row-action" aria-label="Fechar" title="Fechar" onClick={onClose}>
            ✕
          </button>
        </div>

        {detailQuery.isLoading && (
          <div style={{ padding: '24px 0', fontSize: 13, color: 'var(--text-3)' }}>
            Carregando classificação…
          </div>
        )}

        {detailQuery.isError && (
          <div style={{ padding: '24px 0' }}>
            <p style={{ fontSize: 13, margin: '0 0 12px' }}>
              Não foi possível carregar a classificação. Verifique se o serviço está em execução.
            </p>
            <button className="btn-primary" onClick={() => detailQuery.refetch()}>
              <Icon name="refresh" size={15} />
              Tentar novamente
            </button>
          </div>
        )}

        {detail && cls == null && (
          <div style={{ padding: '24px 0', textAlign: 'center' }}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>
              Aguardando classificação
            </div>
            <p style={{ fontSize: 13, color: 'var(--text-3)', margin: 0 }}>
              Este documento ainda não foi classificado.
            </p>
          </div>
        )}

        {detail && cls != null && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Badge do template casado OU pílula de quarentena */}
            <div>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)', marginBottom: 6 }}>
                Template
              </div>
              {isQuarantine ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <span
                    className="pill"
                    style={{ color: 'var(--st-leitura)', background: 'var(--st-leitura-bg)' }}
                  >
                    <span className="pill-dot" style={{ background: 'var(--st-leitura)' }} />
                    Quarentena
                  </span>
                  <span style={{ fontSize: 13, color: 'var(--text-3)' }}>
                    Nenhum template casou com este documento. Ele fica em quarentena e nunca é
                    descartado.
                  </span>
                </div>
              ) : (
                <span className="badge badge-ok">{cls.template_name}</span>
              )}
            </div>

            {/* Tabela campo → valor (bruto) → normalizado */}
            {cls.fields.length > 0 && (
              <div>
                <div
                  style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)', marginBottom: 8 }}
                >
                  Campos extraídos
                </div>
                <div className="card" style={{ overflow: 'hidden' }}>
                  <div className="table-scroll">
                    <table className="docs" style={{ minWidth: 0 }}>
                      <thead>
                        <tr>
                          <th>Campo</th>
                          <th>Valor</th>
                          <th>Normalizado</th>
                          <th>Marca</th>
                        </tr>
                      </thead>
                      <tbody>
                        {cls.fields.map((f) => (
                          <tr key={f.field_name}>
                            <td>{f.field_name}</td>
                            <td className="cell-mono">{f.raw_value ?? '—'}</td>
                            <td className="cell-mono">{f.normalized_value ?? '—'}</td>
                            <td>
                              {f.valid ? (
                                <span className="badge badge-ok">válido</span>
                              ) : (
                                <span
                                  className="badge"
                                  style={{
                                    color: 'var(--st-erro)',
                                    background: 'var(--st-erro-bg)',
                                  }}
                                  title={f.invalid_reason ?? undefined}
                                >
                                  inválido
                                </span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Item 1/D-01: Operações aplicadas (origem→destino) + Reverter para a
            origem. Só aparece quando há operações materializadas para este doc.
            Os caminhos vêm do AuditLog persistido (não de input) e são renderizados
            como TEXTO PURO em cell-mono. O Reverter chama undo por document_id — o
            backend restaura do CAS com seu próprio guard. */}
        {doneOps.length > 0 && (
          <div style={{ marginTop: 18, paddingTop: 16, borderTop: '1px solid var(--border)' }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)', marginBottom: 8 }}>
              Operações aplicadas
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {doneOps.map((op) => (
                <div key={op.id} style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                  <span style={{ fontSize: 11.5, color: 'var(--text-3)' }}>
                    {op.action === 'copy' ? 'Cópia' : 'Movido'}
                  </span>
                  <span className="cell-mono" style={{ fontSize: 12.5 }}>
                    {op.source_path ?? '—'}
                  </span>
                  <span style={{ fontSize: 12, color: 'var(--text-3)' }}>→</span>
                  <span className="cell-mono" style={{ fontSize: 12.5 }}>
                    {op.dest_path ?? '—'}
                  </span>
                </div>
              ))}
            </div>

            {canUndo &&
              (confirmUndo ? (
                <div
                  className="card"
                  style={{ marginTop: 14, padding: 14, background: 'var(--surface-3)' }}
                >
                  <p style={{ fontSize: 13, color: 'var(--text-2)', margin: '0 0 12px' }}>
                    Reverter para a origem? O arquivo volta para a pasta original (restaurado do
                    armazenamento interno) e o documento reabre para reprocessamento.
                  </p>
                  <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                    <button
                      className="btn-ghost"
                      onClick={() => setConfirmUndo(false)}
                      disabled={undo.isPending}
                    >
                      Cancelar
                    </button>
                    <button className="btn-primary" onClick={doUndo} disabled={undo.isPending}>
                      {undo.isPending ? 'Revertendo…' : 'Confirmar reversão'}
                    </button>
                  </div>
                  {undo.isError && (
                    <p style={{ fontSize: 12.5, color: 'var(--st-erro)', margin: '10px 0 0' }}>
                      Não foi possível reverter. Tente novamente.
                    </p>
                  )}
                </div>
              ) : (
                <button
                  className="btn-primary"
                  style={{ marginTop: 14 }}
                  onClick={() => setConfirmUndo(true)}
                  title="Desfazer as operações deste documento e devolver o arquivo à origem"
                >
                  <Icon name="refresh" size={15} />
                  Reverter para a origem
                </button>
              ))}
          </div>
        )}
      </div>
    </div>
  )
}
