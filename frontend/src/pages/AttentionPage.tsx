import type { ReactNode } from 'react'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { AttentionItem, ClassificationField, ReviewItem } from '../types'
import { Icon } from '../components/Icon'
import { ConfidenceBadge } from '../components/ConfidenceBadge'
import { getTemplates } from '../lib/api'
import {
  useApproveDocument,
  useAttentionDocuments,
  usePatchField,
  useReclassifyDocument,
  useReprocessBucket,
  useReprocessDocument,
  useRetryDocument,
} from '../hooks/useAttention'

// Visão "Precisam de atenção" (S1-S4 — Fase 5). Molde DocumentsPage: stat-cards de
// contagem por balde + chips para alternar baldes + estados loading/erro/vazio. Cada
// balde tem sua ação leve (S2 retry / S3 reclassify / S4 corrigir+aprovar). Valores
// de campo renderizados como TEXTO PURO via interpolação React (sem HTML injetado — T-05-16).
// Sem visualizador de documento (D-06).

type BucketKey = 'falha' | 'quarentena' | 'em_revisao'

const BUCKETS: { key: BucketKey; label: string; sub: string; token: 'erro' | 'leitura' | 'quarentena' }[] = [
  { key: 'falha', label: 'Falhas', sub: 'erro no processamento', token: 'erro' },
  { key: 'quarentena', label: 'Não identificados', sub: 'nenhum tipo reconheceu o arquivo', token: 'quarentena' },
  { key: 'em_revisao', label: 'Aguardando conferência', sub: 'pouca certeza ou dado a conferir', token: 'leitura' },
]

const EMPTY_BY_BUCKET: Record<BucketKey, string> = {
  falha: 'Nenhuma falha pendente.',
  quarentena: 'Nada para identificar.',
  em_revisao: 'Nada aguardando conferência.',
}

export function AttentionPage() {
  const query = useAttentionDocuments()
  const [active, setActive] = useState<BucketKey>('falha')

  const data = query.data
  const falha = data?.falha ?? []
  const quarentena = data?.quarentena ?? []
  const emRevisao = data?.em_revisao ?? []
  const counts = data?.counts ?? {}

  const countOf = (k: BucketKey) => counts[k] ?? 0
  const totalPending = falha.length + quarentena.length + emRevisao.length

  // Estados da tela (derivação exata de DocumentsPage).
  const isInitialLoading = query.isLoading && !data
  const isError = query.isError && !data
  const isEmpty = !isInitialLoading && !isError && totalPending === 0
  const isRefetching = query.isFetching && !!data

  return (
    <div>
      {/* contagem por balde — focal point quando populada */}
      <div className="stat-grid">
        {BUCKETS.map((b) => (
          <div key={b.key} className="card stat-card">
            <div className="stat-head">
              <span className="stat-label">{b.label}</span>
              <span className="stat-dot" style={{ background: `var(--st-${b.token})` }} />
            </div>
            <div className="stat-num">{countOf(b.key)}</div>
            <div className="stat-sub">{b.sub}</div>
          </div>
        ))}
      </div>

      <div className="card" style={{ overflow: 'hidden' }}>
        {/* toolbar: chips de balde */}
        <div className="table-toolbar">
          <div className="chips">
            {BUCKETS.map((b) => (
              <button
                key={b.key}
                className={active === b.key ? 'chip active' : 'chip'}
                onClick={() => setActive(b.key)}
              >
                <span>{b.label}</span>
                <span className="chip-count">{countOf(b.key)}</span>
              </button>
            ))}
          </div>
          <div className="spacer" />
          {isRefetching && (
            <span className="foot-text" style={{ color: 'var(--text-3)' }}>
              Atualizando…
            </span>
          )}
        </div>

        {/* corpo: estados de tela ou lista do balde selecionado */}
        <div style={{ padding: 16 }}>
          {isInitialLoading &&
            Array.from({ length: 3 }).map((_, i) => (
              <div
                key={`sk-${i}`}
                style={{
                  height: 64,
                  borderRadius: 'var(--radius)',
                  background: 'var(--surface-3)',
                  opacity: 0.7,
                  marginBottom: 12,
                }}
              />
            ))}

          {isError && (
            <div style={{ textAlign: 'center', padding: '48px 24px' }}>
              <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>
                Não foi possível carregar os documentos.
              </div>
              <p style={{ fontSize: 13, color: 'var(--text-3)', margin: '0 0 16px' }}>
                Verifique se o aplicativo está aberto e tente de novo.
              </p>
              <button className="btn-primary" onClick={() => query.refetch()}>
                <Icon name="refresh" size={15} />
                Tentar novamente
              </button>
            </div>
          )}

          {isEmpty && (
            <div style={{ textAlign: 'center', padding: '48px 24px' }}>
              <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>Tudo em dia</div>
              <p
                style={{
                  fontSize: 13,
                  color: 'var(--text-3)',
                  margin: 0,
                  maxWidth: 460,
                  marginInline: 'auto',
                }}
              >
                Nenhum documento precisa de atenção agora. Documentos com falha, não identificados ou
                com pouca certeza na leitura aparecem aqui automaticamente.
              </p>
            </div>
          )}

          {!isInitialLoading && !isError && !isEmpty && (
            <BucketView
              bucket={active}
              falha={falha}
              quarentena={quarentena}
              emRevisao={emRevisao}
            />
          )}
        </div>
      </div>
    </div>
  )
}

function BucketView({
  bucket,
  falha,
  quarentena,
  emRevisao,
}: {
  bucket: BucketKey
  falha: AttentionItem[]
  quarentena: AttentionItem[]
  emRevisao: ReviewItem[]
}) {
  const isBucketEmpty =
    (bucket === 'falha' && falha.length === 0) ||
    (bucket === 'quarentena' && quarentena.length === 0) ||
    (bucket === 'em_revisao' && emRevisao.length === 0)

  if (isBucketEmpty) {
    return (
      <div style={{ textAlign: 'center', padding: '32px 24px', fontSize: 13, color: 'var(--text-3)' }}>
        {EMPTY_BY_BUCKET[bucket]}
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* "Reprocessar todos" — só em QUARENTENA/EM_REVISAO (FALHA usa retry, D-12). */}
      {(bucket === 'quarentena' || bucket === 'em_revisao') && (
        <ReprocessBucketBar bucket={bucket} />
      )}
      {bucket === 'falha' && falha.map((it) => <FailureRow key={it.id} item={it} />)}
      {bucket === 'quarentena' &&
        quarentena.map((it) => <QuarantineRow key={it.id} item={it} />)}
      {bucket === 'em_revisao' && emRevisao.map((it) => <ReviewRow key={it.id} item={it} />)}
    </div>
  )
}

// Cabeçalho do balde com "Reprocessar todos" — re-roda matcher→(IA)→filler com os
// templates ATUAIS para o balde inteiro (D-12). Confirmação simples antes do lote.
function ReprocessBucketBar({ bucket }: { bucket: 'quarentena' | 'em_revisao' }) {
  const reprocess = useReprocessBucket()
  const label = bucket === 'quarentena' ? 'os não identificados' : 'os que aguardam conferência'
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 8,
        flexWrap: 'wrap',
      }}
    >
      <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
        Mudou os tipos de documento? Tente identificar de novo {label} para aplicar as mudanças.
      </span>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
        <button
          className="btn-ghost"
          disabled={reprocess.isPending}
          onClick={() => {
            const message =
              bucket === 'em_revisao'
                ? 'Isto vai ler e identificar todos os documentos de novo e DESCARTAR as correções que você fez à mão. Continuar?'
                : `Tentar identificar de novo ${label}?`
            if (window.confirm(message)) {
              reprocess.mutate(bucket)
            }
          }}
        >
          <Icon name="refresh" size={15} />
          {reprocess.isPending ? 'Processando…' : 'Tentar identificar de novo'}
        </button>
        <ActionError show={reprocess.isError} />
      </div>
    </div>
  )
}

// Card base de um item de triagem (motivo + ações inline). Reusa o card de 14px.
function ItemCard({
  filename,
  children,
}: {
  filename: string
  children: ReactNode
}) {
  return (
    <div className="card" style={{ padding: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <Icon name="docMini" size={17} stroke="var(--text-3)" style={{ flex: 'none' }} />
        <span className="file-name" style={{ fontWeight: 600 }}>
          {filename}
        </span>
      </div>
      {children}
    </div>
  )
}

function ActionError({ show }: { show: boolean }) {
  if (!show) return null
  return (
    <p style={{ fontSize: 13, color: 'var(--st-erro)', margin: '8px 0 0' }}>
      Não foi possível concluir a ação. Tente novamente.
    </p>
  )
}

// S2 — FALHA: motivo + "Tentar de novo".
function FailureRow({ item }: { item: AttentionItem }) {
  const retry = useRetryDocument()
  return (
    <ItemCard filename={item.original_filename}>
      <p style={{ fontSize: 13, color: 'var(--text-2)', margin: '0 0 12px' }}>{item.motivo}</p>
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button
          className="btn-primary"
          onClick={() => retry.mutate(item.id)}
          disabled={retry.isPending}
        >
          <Icon name="refresh" size={15} />
          {retry.isPending ? 'Reenviando…' : 'Tentar de novo'}
        </button>
      </div>
      <ActionError show={retry.isError} />
    </ItemCard>
  )
}

// S3 — QUARENTENA: motivo + select "Atribuir template" + "Reclassificar".
function QuarantineRow({ item }: { item: AttentionItem }) {
  const reclassify = useReclassifyDocument()
  const reprocess = useReprocessDocument()
  const templatesQuery = useQuery({ queryKey: ['templates'], queryFn: getTemplates })
  const templates = templatesQuery.data ?? []
  const [templateId, setTemplateId] = useState<number | ''>('')

  return (
    <ItemCard filename={item.original_filename}>
      <p style={{ fontSize: 13, color: 'var(--text-2)', margin: '0 0 12px' }}>{item.motivo}</p>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          justifyContent: 'flex-end',
          flexWrap: 'wrap',
        }}
      >
        {/* Reprocessar (sem template forçado): reaplica matcher→(IA)→filler com os
            templates ATUAIS — use após editar/criar um template (D-10). */}
        <button
          className="btn-ghost"
          disabled={reprocess.isPending}
          onClick={() => {
            if (window.confirm('Tentar identificar este documento de novo?')) {
              reprocess.mutate(item.id)
            }
          }}
        >
          <Icon name="refresh" size={15} />
          {reprocess.isPending ? 'Processando…' : 'Tentar de novo'}
        </button>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)' }}>
            Escolher o tipo manualmente
          </span>
          <select
            className="select"
            value={templateId}
            onChange={(e) => setTemplateId(e.target.value === '' ? '' : Number(e.target.value))}
          >
            <option value="">Escolha um tipo…</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
        <button
          className="btn-primary"
          disabled={templateId === '' || reclassify.isPending}
          onClick={() =>
            templateId !== '' && reclassify.mutate({ id: item.id, templateId })
          }
        >
          <Icon name="refresh" size={15} />
          {reclassify.isPending ? 'Aplicando…' : 'Aplicar tipo'}
        </button>
      </div>
      <ActionError show={reclassify.isError || reprocess.isError} />
    </ItemCard>
  )
}

// S4 — EM_REVISAO: ConfidenceBadge + tabela de campos com correção inline + "Aprovar".
function ReviewRow({ item }: { item: ReviewItem }) {
  const approve = useApproveDocument()
  const reprocess = useReprocessDocument()
  // Algum campo inválido → o gate D-07 (defesa em profundidade na UI; backend é o
  // guard autoritativo). Aproximação na UI: bloqueia se HOUVER qualquer campo inválido.
  const hasInvalid = item.fields.some((f) => !f.valid)
  // Alguma correção manual feita neste documento → reprocessar vai DESCARTÁ-la (D-10/D-11).
  const hasCorrections = item.fields.some((f) => f.manually_corrected)

  return (
    <ItemCard filename={item.original_filename}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)' }}>Certeza da leitura</span>
        <ConfidenceBadge score={item.confidence_score} />
      </div>

      {item.fields.length > 0 && (
        <div className="card" style={{ overflow: 'hidden', marginBottom: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)', padding: '10px 14px 0' }}>
            Dados lidos
          </div>
          <div className="table-scroll">
            <table className="docs" style={{ minWidth: 0 }}>
              <thead>
                <tr>
                  <th>Campo</th>
                  <th>Valor</th>
                  <th>Valor padronizado</th>
                  <th>Situação</th>
                </tr>
              </thead>
              <tbody>
                {item.fields.map((f) => (
                  <FieldRow key={f.field_name} docId={item.id} field={f} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
        {hasInvalid && (
          <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
            Corrija os campos obrigatórios inválidos antes de aprovar o documento.
          </span>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          {/* Reprocessar: reaplica matcher→(IA)→filler com os templates ATUAIS (D-10). */}
          <button
            className="btn-ghost"
            disabled={reprocess.isPending}
            onClick={() => {
              const message = hasCorrections
                ? 'Isto vai ler e identificar o documento de novo e DESCARTAR as correções que você fez à mão. Continuar?'
                : 'Isto vai ler e identificar o documento de novo. Continuar?'
              if (window.confirm(message)) {
                reprocess.mutate(item.id)
              }
            }}
          >
            <Icon name="refresh" size={15} />
            {reprocess.isPending ? 'Processando…' : 'Tentar de novo'}
          </button>
          <button
            className="btn-primary"
            disabled={hasInvalid || approve.isPending}
            aria-label={`Aprovar documento ${item.original_filename}`}
            onClick={() => approve.mutate(item.id)}
          >
            <Icon name="check" size={15} />
            {approve.isPending ? 'Aprovando…' : 'Aprovar documento'}
          </button>
        </div>
        <ActionError show={approve.isError || reprocess.isError} />
      </div>
    </ItemCard>
  )
}

// Linha de campo: válido → texto puro; inválido → input de correção inline (mono) +
// "Salvar correção" (revalida sem IA, D-08). Marca verde/vermelha + "corrigido manualmente".
function FieldRow({ docId, field }: { docId: number; field: ClassificationField }) {
  const patch = usePatchField()
  const [value, setValue] = useState<string>(field.raw_value ?? '')

  return (
    <tr>
      <td>{field.field_name}</td>
      <td className="cell-mono">
        {field.valid ? (
          field.raw_value ?? '—'
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input
              className="search-input"
              style={{ fontFamily: 'var(--font-mono)' }}
              aria-label={`Corrigir valor de ${field.field_name}`}
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
            <button
              className="btn-ghost"
              disabled={patch.isPending}
              onClick={() =>
                patch.mutate({ id: docId, fieldName: field.field_name, rawValue: value })
              }
            >
              {patch.isPending ? 'Salvando…' : 'Salvar correção'}
            </button>
          </div>
        )}
      </td>
      <td className="cell-mono">{field.normalized_value ?? '—'}</td>
      <td>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          {field.valid ? (
            <span className="badge badge-ok">válido</span>
          ) : (
            <span
              className="badge"
              style={{ color: 'var(--st-erro)', background: 'var(--st-erro-bg)' }}
              title={field.invalid_reason ?? undefined}
            >
              inválido
            </span>
          )}
          {field.manually_corrected && (
            <span
              className="badge"
              style={{ color: 'var(--text-3)', background: 'var(--surface-3)' }}
            >
              corrigido manualmente
            </span>
          )}
        </div>
      </td>
    </tr>
  )
}
