import { clsx } from 'clsx'
import { X, Building2, FileText, Tag, TrendingUp, TrendingDown, Calendar, DollarSign, Lightbulb, Users, Clock4 } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { http } from '@/api/client'
import { SentimentBadge } from '@/components/ui/Badge'
import { fmt, pctColor } from '@/lib/utils'
import type { Disclosure } from '@/types'

function buildDisclosureNarrative(d: Disclosure): string {
  const corpStr = d.corp_name ? `${d.corp_name}${d.code ? ` (${d.code})` : ''}` : d.code ?? '해당 법인'
  const catMap: Record<string, string> = {
    favorable:   '호재성',
    unfavorable: '악재성',
    neutral:     '중립적',
  }
  const catStr   = catMap[d.category ?? ''] ?? '내용 미분류'
  const scoreStr = d.sentiment_score != null
    ? `감성 분석 점수는 <strong>${d.sentiment_score >= 0 ? '+' : ''}${d.sentiment_score?.toFixed(3)}</strong>으로 `
    + (d.sentiment_score >= 0.3 ? '시장에 긍정적인 반응이 예상됩니다.' : d.sentiment_score <= -0.3 ? '시장에 부정적인 반응이 우려됩니다.' : '중립 수준의 반응이 예상됩니다.')
    : ''
  const amtStr = (d.amount_text || d.amount)
    ? `공시와 관련된 금액은 <strong>${d.amount_text ?? fmt.amount(d.amount)}</strong>입니다. ` : ''
  const cpStr    = d.counterparty ? `거래 상대방은 <strong>${d.counterparty}</strong>입니다. ` : ''
  const chgStr   = d.post_1d_change != null
    ? `공시 다음날 주가 등락률은 <strong>${fmt.pct(d.post_1d_change)}</strong>를 기록했습니다. ` : ''
  const kwStr    = d.keywords && d.keywords.length > 0
    ? `주요 키워드: <strong>${d.keywords.slice(0, 5).join(', ')}</strong>.` : ''

  return [
    `${corpStr}이(가) <strong>${d.title}</strong> 공시를 제출했습니다.`,
    `해당 공시는 <strong>${catStr}</strong> 성격의 ${d.disclosure_type ?? d.report_type ?? ''}공시로 분류되어 있습니다.`,
    scoreStr,
    amtStr,
    cpStr,
    chgStr,
    kwStr,
  ].filter(Boolean).join(' ')
}

interface Props {
  disclosure: Disclosure
  onClose:    () => void
}

interface ImpactPrediction {
  predicted_1d:   number | null
  predicted_3d:   number | null
  std_1d:         number
  confidence:     number
  avg_similarity: number
  similar_count:  number
  note?:          string
  similar?: Array<{ rcept_no: string; title: string; category: string; similarity: number; post_1d_change: number }>
}

function PriceReactionCell({ label, value }: { label: string; value?: number | null }) {
  return (
    <div className="bg-[var(--bg)] rounded-xl p-3 text-center">
      <div className="text-xs text-[var(--muted)] mb-1.5">{label}</div>
      <div className={clsx('text-base font-bold tabular', pctColor(value))}>
        {value != null ? fmt.pct(value) : '—'}
      </div>
    </div>
  )
}

export function DisclosureDetailModal({ disclosure: d, onClose }: Props) {
  const sentiment = d.sentiment_score ?? 0
  const hasReaction = d.post_1h_change != null || d.post_1d_change != null || d.post_3d_change != null

  const { data: impact, isLoading: impactLoading } = useQuery<ImpactPrediction>({
    queryKey: ['disclosure-impact', d.rcept_no],
    queryFn:  () => http.get<ImpactPrediction>(`/disclosures/${d.rcept_no}/predict-impact`).then((r) => r.data),
    staleTime: 600_000,
    retry: false,
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
      <div
        className="relative w-full max-w-2xl bg-[var(--card)] border border-[var(--border)] rounded-2xl shadow-2xl overflow-hidden flex flex-col"
        style={{ maxHeight: '90vh' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 헤더 */}
        <div className="flex items-start justify-between px-6 py-5 border-b border-[var(--border)] shrink-0">
          <div className="flex items-start gap-3 pr-4">
            <div className="mt-0.5 w-10 h-10 rounded-xl bg-cyan-500/10 flex items-center justify-center shrink-0">
              <FileText size={20} className="text-cyan-400" />
            </div>
            <div>
              <div className="text-xs font-medium text-[var(--muted)] mb-1">공시 상세</div>
              <div className="text-base font-semibold text-[var(--fg)] leading-snug">{d.title}</div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 w-8 h-8 flex items-center justify-center rounded-lg text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)] transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* 스크롤 본문 */}
        <div className="overflow-y-auto" style={{ flex: 1 }}>

          {/* 법인 정보 */}
          <div className="px-6 py-4 flex items-center gap-2.5 border-b border-[var(--border)]/60">
            <Building2 size={16} className="text-[var(--muted)] shrink-0" />
            <span className="text-base font-semibold text-[var(--fg)]">{d.corp_name ?? '—'}</span>
            {d.code && (
              <code className="text-sm px-2 py-0.5 rounded-lg bg-[var(--border)] text-cyan-400 font-mono">
                {d.code}
              </code>
            )}
            <div className="ml-auto"><SentimentBadge category={d.category} /></div>
          </div>

          {/* 거래처 / 계약기간 정보 (있을 때만) */}
          {(d.counterparty || d.contract_period) && (
            <div className="px-6 py-3 flex flex-wrap items-center gap-4 border-b border-[var(--border)]/60 bg-[var(--bg)]/40">
              {d.counterparty && (
                <div className="flex items-center gap-1.5 text-sm">
                  <Users size={13} className="text-[var(--muted)] shrink-0" />
                  <span className="text-[var(--muted)]">거래상대방</span>
                  <span className="font-semibold text-[var(--fg)]">{d.counterparty}</span>
                </div>
              )}
              {d.contract_period && (
                <div className="flex items-center gap-1.5 text-sm">
                  <Clock4 size={13} className="text-[var(--muted)] shrink-0" />
                  <span className="text-[var(--muted)]">계약기간</span>
                  <span className="font-semibold text-[var(--fg)]">{d.contract_period}</span>
                </div>
              )}
            </div>
          )}

          {/* 핵심 지표 */}
          <div className="px-6 py-5 space-y-3 border-b border-[var(--border)]/60">
            {/* 감성 / 시각 / 금액 */}
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-[var(--bg)] rounded-xl p-4">
                <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--muted)] mb-2">
                  <Tag size={13} /> 감성 점수
                </div>
                <div className={clsx('text-xl font-bold tabular',
                  sentiment >= 0.3 ? 'text-green-400' :
                  sentiment <= -0.3 ? 'text-red-400' : 'text-[var(--fg)]'
                )}>
                  {d.sentiment_score != null ? (sentiment >= 0 ? '+' : '') + sentiment.toFixed(3) : '—'}
                </div>
              </div>
              <div className="bg-[var(--bg)] rounded-xl p-4">
                <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--muted)] mb-2">
                  <Calendar size={13} /> 공시 시각
                </div>
                <div className="text-sm font-semibold text-[var(--fg)] tabular leading-relaxed">
                  {fmt.dateTime(d.disclosed_at)}
                </div>
              </div>
              <div className="bg-[var(--bg)] rounded-xl p-4">
                <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--muted)] mb-2">
                  <DollarSign size={13} /> 관련 금액
                </div>
                <div className="text-sm font-semibold text-[var(--fg)] tabular leading-relaxed">
                  {d.amount_text ?? (d.amount ? fmt.amount(d.amount) : '—')}
                </div>
              </div>
            </div>

            {/* 공시 후 주가 반응 */}
            {hasReaction && (
              <div>
                <div className="text-xs font-semibold text-[var(--muted)] mb-2 flex items-center gap-1.5">
                  {(d.post_1d_change ?? 0) >= 0
                    ? <TrendingUp size={12} className="text-red-400" />
                    : <TrendingDown size={12} className="text-blue-400" />}
                  공시 후 주가 반응
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <PriceReactionCell label="1시간 후" value={d.post_1h_change} />
                  <PriceReactionCell label="1일 후"   value={d.post_1d_change} />
                  <PriceReactionCell label="3일 후"   value={d.post_3d_change} />
                </div>
              </div>
            )}
          </div>

          {/* 키워드 */}
          {d.keywords && d.keywords.length > 0 && (
            <div className="px-6 py-4 border-b border-[var(--border)]/60">
              <div className="text-xs font-semibold text-[var(--muted)] mb-2.5 uppercase tracking-wider">추출 키워드</div>
              <div className="flex flex-wrap gap-2">
                {d.keywords.map((k) => (
                  <span
                    key={k}
                    className="text-sm px-3 py-1 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20"
                  >
                    #{k}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* AI 분석 요약 */}
          <div className="px-6 pt-5 pb-3">
            <div className="text-sm font-semibold text-[var(--fg)] mb-3">📋 AI 분석 요약</div>
            <p
              className="modal-narrative text-sm text-[var(--fg)] leading-7"
              dangerouslySetInnerHTML={{ __html: buildDisclosureNarrative(d) }}
            />
          </div>

          {/* 유사 공시 기반 가격 충격 예측 */}
          <div className="px-6 pb-6">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-[var(--muted)] mb-2 uppercase tracking-wider">
              <Lightbulb size={12} className="text-yellow-400" />
              유사 공시 기반 가격 충격 예측
            </div>
            {impactLoading ? (
              <div className="h-10 skeleton rounded-lg" />
            ) : impact?.note === 'embedding_not_computed' ? (
              <p className="text-xs text-[var(--muted)]">임베딩 미생성 — analyzer 처리 후 이용 가능</p>
            ) : impact && impact.similar_count > 0 ? (
              <div className="bg-[var(--bg)] rounded-xl p-4 space-y-3">
                <div className="grid grid-cols-3 gap-3 text-center">
                  <div>
                    <div className="text-xs text-[var(--muted)] mb-0.5">1일 예측</div>
                    <div className={clsx('text-base font-bold tabular', pctColor(impact.predicted_1d))}>
                      {impact.predicted_1d != null ? fmt.pct(impact.predicted_1d) : '—'}
                    </div>
                    <div className="text-xs text-[var(--muted)]">±{impact.std_1d.toFixed(2)}%</div>
                  </div>
                  <div>
                    <div className="text-xs text-[var(--muted)] mb-0.5">3일 예측</div>
                    <div className={clsx('text-base font-bold tabular', pctColor(impact.predicted_3d))}>
                      {impact.predicted_3d != null ? fmt.pct(impact.predicted_3d) : '—'}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-[var(--muted)] mb-0.5">신뢰도</div>
                    <div className="text-base font-bold tabular text-cyan-400">
                      {(impact.confidence * 100).toFixed(0)}%
                    </div>
                    <div className="text-xs text-[var(--muted)]">유사 {impact.similar_count}건</div>
                  </div>
                </div>
                {/* 유사 공시 개별 목록 */}
                {impact.similar && impact.similar.length > 0 && (
                  <div className="border-t border-[var(--border)]/60 pt-3 space-y-1.5">
                    <div className="text-xs text-[var(--muted)] font-semibold mb-1.5">유사 공시 사례</div>
                    {impact.similar.map((s, i) => (
                      <div key={i} className="flex items-center justify-between text-xs py-1 px-2 rounded-lg bg-[var(--card)] border border-[var(--border)]/60">
                        <span className="text-[var(--fg)] truncate max-w-[55%]">{s.title}</span>
                        <div className="flex items-center gap-2 shrink-0">
                          <span className="text-[var(--muted)]">유사도 {(s.similarity * 100).toFixed(0)}%</span>
                          <SentimentBadge category={s.category as 'favorable' | 'unfavorable' | 'neutral'} />
                          <span className={clsx('font-semibold tabular', pctColor(s.post_1d_change))}>
                            {fmt.pct(s.post_1d_change)}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <p className="text-xs text-[var(--muted)]">유사 공시 데이터 없음</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
