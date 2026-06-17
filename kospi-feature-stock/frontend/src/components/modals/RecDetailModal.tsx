// v3
import type { ReactNode } from 'react'
import { X, Target, Shield, Zap, TrendingUp, BrainCircuit, BarChart2, Clock, History } from 'lucide-react'
import { clsx } from 'clsx'
import { fmt, probColor, pctColor } from '@/lib/utils'
import type { Recommendation, SimilarCase } from '@/types'
import { ActionBadge, Badge, EVENT_LABELS, EVENT_NAMES } from '@/components/ui/Badge'

function SimilarCaseCard({ sc, rank }: { sc: SimilarCase; rank: number }) {
  const best = sc.return_5d ?? sc.return_3d ?? sc.return_1d
  return (
    <div className="flex items-center gap-3 bg-[var(--bg)] rounded-xl px-4 py-3 border border-[var(--border)]/60">
      <div className="w-5 h-5 rounded-full bg-[var(--border)] flex items-center justify-center text-xs font-bold text-[var(--muted)] shrink-0">
        {rank}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-semibold text-sm text-[var(--fg)]">{sc.name ?? sc.code}</span>
          <code className="text-xs text-[var(--muted)] font-mono">{sc.code}</code>
          {sc.event_type && (
            <Badge eventType={sc.event_type} size="sm" />
          )}
        </div>
        <div className="text-xs text-[var(--muted)] mt-0.5">{sc.date?.slice(0, 10)}</div>
      </div>
      <div className="text-right shrink-0 space-y-0.5">
        <div className="text-xs text-[var(--muted)]">유사도 {(sc.similarity * 100).toFixed(0)}%</div>
        {best != null && (
          <div className={clsx('text-sm font-bold tabular', pctColor(best))}>
            {best >= 0 ? '+' : ''}{(best * 100).toFixed(1)}%
            <span className="text-xs font-normal text-[var(--muted)] ml-1">
              {sc.return_5d != null ? '5일' : sc.return_3d != null ? '3일' : '1일'}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}


function RecNarrative({ rec }: { rec: Recommendation }) {
  const evtType   = rec.rationale?.event_type
  const mlProb    = rec.rationale?.ml_prob
  const simCount  = rec.rationale?.sim_count ?? 0
  const simReturn = rec.rationale?.avg_sim_return
  const atrBased  = rec.rationale?.atr_based ?? false
  const risks     = rec.rationale?.risk_factors ?? []
  const evtName   = evtType ? (EVENT_NAMES[evtType] || evtType) : null
  const B = ({ children }: { children: ReactNode }) => <strong className="font-bold text-[var(--fg)]">{children}</strong>

  const sentences: ReactNode[] = []
  if (rec.action === 'BUY') {
    sentences.push(<span key="action">ML 모델이 이 종목을 <B>매수(BUY)</B> 추천합니다. 성공 확률 <B>{fmt.prob(rec.success_prob)}</B>로 모델이 단기 상승 가능성이 높다고 판단했습니다.</span>)
  } else if (rec.action === 'WAIT') {
    sentences.push(<span key="action">현재 조건이 완전히 충족되지 않아 <B>대기(WAIT)</B> 신호입니다. 성공 확률 <B>{fmt.prob(rec.success_prob)}</B>로, 조건이 개선되면 BUY 신호로 전환될 수 있습니다.</span>)
  } else {
    sentences.push(<span key="action">현재 리스크가 높아 <B>보류(SKIP)</B> 판단입니다. 신호 확률 <B>{fmt.prob(rec.success_prob)}</B>.</span>)
  }
  if (evtName) {
    sentences.push(<span key="evt"> 신호 발생의 핵심 트리거는 <B>{evtName}</B> 이벤트입니다.</span>)
  }
  if (mlProb != null) {
    const pStr = (mlProb * 100).toFixed(1)
    const mlDesc = mlProb >= 0.55
      ? '로, 학습 패턴 기반으로 매우 높은 상승 신뢰도를 의미합니다.'
      : mlProb >= 0.35
        ? '로, 학습 패턴 기반으로 상승 가능성이 충분합니다.'
        : mlProb >= 0.22
          ? '로, 추천 최소 기준을 충족합니다.'
          : '입니다.'
    sentences.push(<span key="ml"> ML 모델의 원시 예측 확률은 <B>{pStr}%</B>{mlDesc}</span>)
  }
  if (simCount > 0 && simReturn != null) {
    const retSign = simReturn >= 0 ? '+' : ''
    sentences.push(<span key="sim"> 과거 유사 패턴 <B>{simCount}건</B>에서 평균 <B>{retSign}{(simReturn * 100).toFixed(1)}%</B>의 수익이 관측됐습니다.</span>)
  }
  if (atrBased) {
    sentences.push(<span key="price"> 진입가 <B>{fmt.price(rec.entry_price)}</B>을 기준으로, 목표가 <B>{fmt.price(rec.target_price)}</B> · 손절가 <B>{fmt.price(rec.stop_loss_price)}</B>는 ATR(변동폭) 기반으로 동적 산정됩니다. R:R {rec.risk_reward_ratio?.toFixed(1) ?? '—'}.</span>)
  } else {
    sentences.push(<span key="price"> 진입가 <B>{fmt.price(rec.entry_price)}</B> 기준, 목표가 <B>{fmt.price(rec.target_price)}</B> · 손절가 <B>{fmt.price(rec.stop_loss_price)}</B>. R:R {rec.risk_reward_ratio?.toFixed(1) ?? '—'}.</span>)
  }
  if (risks.length > 0) {
    sentences.push(<span key="risk"> 주의 위험 요소: {risks.map((r, i) => <span key={i}>{i > 0 ? ', ' : ''}<B>{r}</B></span>)}. 손절 원칙을 반드시 지키세요.</span>)
  }
  return <>{sentences}</>
}

interface RecDetailModalProps {
  rec: Recommendation
  onClose: () => void
  onGoDetail: () => void
  compact?: boolean
}

export function RecDetailModal({ rec, onClose, onGoDetail, compact = false }: RecDetailModalProps) {
  const crDelta   = rec.current_price != null
    ? ((rec.current_price - rec.entry_price) / rec.entry_price * 100)
    : null

  const barColor =
    rec.success_prob >= 0.55 ? 'bg-green-400' :
    rec.success_prob >= 0.35 ? 'bg-orange-400' :
    rec.success_prob >= 0.22 ? 'bg-yellow-500' : 'bg-zinc-500'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4" data-v="2" onClick={onClose}>
      <div className="absolute inset-0 bg-black/85 backdrop-blur-md" />
      <div
        className={`relative bg-[var(--card)] border border-[var(--border)] rounded-2xl shadow-[0_32px_80px_rgba(0,0,0,0.7)] flex flex-col ${compact ? 'w-[88vw] max-w-[460px]' : 'w-[92vw] max-w-[900px]'}`}
        style={{ maxHeight: compact ? '72vh' : '95vh' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── 헤더 ── */}
        <div className={`flex items-start justify-between border-b-2 border-[var(--border)] shrink-0 ${compact ? 'px-4 py-3' : 'px-10 py-7'}`}>
          <div className="flex flex-col gap-1.5 min-w-0 pr-3">
            <div className="flex items-center gap-2 flex-wrap">
              <span className={compact ? 'text-base font-bold text-[var(--fg)] tracking-tight' : 'text-3xl font-extrabold text-[var(--fg)] tracking-tight'}>{rec.name}</span>
              <ActionBadge action={rec.action} />
              {rec.rationale?.event_type && <Badge eventType={rec.rationale.event_type} size="sm" />}
            </div>
            <div className={`flex items-center gap-2 font-medium text-[var(--muted)] ${compact ? 'text-xs' : 'text-lg'}`}>
              <span className="font-mono">{rec.code}</span>
              <span className="opacity-40">·</span>
              <span>{rec.market}</span>
              <span className="opacity-40">·</span>
              <span className="flex items-center gap-1"><Clock size={compact ? 11 : 15} />{fmt.dateTime(rec.created_at)}</span>
            </div>
          </div>
          <button
            onClick={onClose}
            className={`shrink-0 flex items-center justify-center rounded-xl bg-[var(--bg)] text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)] transition-colors ${compact ? 'w-7 h-7' : 'w-11 h-11'}`}
          >
            <X size={compact ? 15 : 24} />
          </button>
        </div>

        {/* ── 스크롤 본문 ── */}
        <div className={`overflow-y-auto ${compact ? 'space-y-3 px-4 py-3' : 'space-y-6 px-10 py-8'}`} style={{ flex: 1 }}>

          {/* 성공확률 */}
          <div>
            <div className={`flex justify-between items-end ${compact ? 'mb-2' : 'mb-4'}`}>
              <span className={compact ? 'text-sm font-semibold text-[var(--fg)]' : 'text-xl font-bold text-[var(--fg)]'}>성공 확률</span>
              <span className={clsx(compact ? 'text-2xl' : 'text-5xl', 'font-extrabold tabular tracking-tight', probColor(rec.success_prob))}>
                {fmt.prob(rec.success_prob)}
              </span>
            </div>
            <div className={`${compact ? 'h-4' : 'h-7'} bg-[var(--border)] rounded-full overflow-hidden`}>
              <div
                className={clsx('h-full rounded-full transition-all duration-700', barColor)}
                style={{ width: `${rec.success_prob * 100}%` }}
              />
            </div>
            <div className={`flex justify-between text-[var(--muted)] ${compact ? 'mt-1.5 text-xs' : 'mt-2 text-sm'}`}>
              <span>0%</span>
              <span className="text-yellow-400 font-semibold">22%</span>
              <span className="text-orange-400 font-semibold">35%</span>
              <span className="text-green-400 font-semibold">55%</span>
              <span>100%</span>
            </div>
          </div>

          {/* 현재가 vs 진입가 */}
          {rec.current_price != null && (
            <div className={`flex items-center justify-between bg-[var(--bg)] border border-[var(--border)] ${compact ? 'rounded-xl px-4 py-2.5' : 'rounded-2xl px-8 py-6'}`}>
              <div className={`flex items-center ${compact ? 'gap-2' : 'gap-5'}`}>
                <span className={compact ? 'text-xs font-semibold text-[var(--muted)]' : 'text-lg font-bold text-[var(--muted)]'}>현재가</span>
                <span className={clsx(compact ? 'text-lg font-bold' : 'text-3xl font-extrabold', 'tabular',
                  (rec.current_change_rate ?? 0) > 0 ? 'text-red-400' :
                  (rec.current_change_rate ?? 0) < 0 ? 'text-blue-400' : 'text-[var(--fg)]'
                )}>
                  {fmt.price(rec.current_price)}
                </span>
                {rec.current_change_rate != null && rec.current_change_rate !== 0 && (
                  <span className={clsx(
                    compact ? 'text-xs font-semibold px-2 py-0.5 rounded-lg' : 'text-xl font-bold px-4 py-1.5 rounded-xl',
                    rec.current_change_rate > 0
                      ? 'text-red-300 bg-red-500/15 border border-red-500/30'
                      : 'text-blue-300 bg-blue-500/15 border border-blue-500/30'
                  )}>
                    {rec.current_change_rate > 0 ? '+' : ''}{rec.current_change_rate.toFixed(2)}%
                  </span>
                )}
              </div>
              {crDelta != null && (
                <div className="text-right">
                  <div className={`font-medium text-[var(--muted)] ${compact ? 'text-[10px] mb-0.5' : 'text-sm mb-1'}`}>진입 대비</div>
                  <span className={clsx(compact ? 'text-base font-bold' : 'text-2xl font-extrabold', 'tabular',
                    crDelta >= 0 ? 'text-red-400' : 'text-blue-400'
                  )}>
                    {crDelta >= 0 ? '+' : ''}{crDelta.toFixed(1)}%
                  </span>
                </div>
              )}
            </div>
          )}

          {/* 가격 3박스 */}
          <div className={`grid grid-cols-3 ${compact ? 'gap-2' : 'gap-5'}`}>
            <div className={`bg-[var(--bg)] rounded-xl text-center border border-[var(--border)] ${compact ? 'p-3' : 'rounded-2xl p-7'}`}>
              <div className={`flex items-center justify-center font-bold text-[var(--muted)] ${compact ? 'gap-1 text-[11px] mb-1.5' : 'gap-2 text-lg mb-3'}`}>
                <Zap size={compact ? 11 : 20} /> 진입가
              </div>
              {!compact && <div className="text-sm font-medium text-[var(--muted)] mb-3">매수 기준</div>}
              <div className={`font-extrabold tabular text-[var(--fg)] ${compact ? 'text-[13px]' : 'text-2xl'}`}>{fmt.price(rec.entry_price)}</div>
            </div>
            <div className={`bg-red-500/10 rounded-xl text-center border border-red-500/40 ${compact ? 'p-3' : 'rounded-2xl p-7'}`}>
              <div className={`flex items-center justify-center font-bold text-red-400 ${compact ? 'gap-1 text-[11px] mb-1.5' : 'gap-2 text-lg mb-3'}`}>
                <Target size={compact ? 11 : 20} /> 목표가
              </div>
              {!compact && <div className="text-sm font-medium text-red-400/70 mb-3">익절 기준</div>}
              <div className={`font-extrabold tabular text-red-400 ${compact ? 'text-[13px]' : 'text-2xl'}`}>{fmt.price(rec.target_price)}</div>
              {rec.rationale?.target_dist_pct != null && (
                <div className={`font-bold text-red-400 tabular ${compact ? 'text-[11px] mt-1' : 'text-base mt-2.5'}`}>
                  +{rec.rationale.target_dist_pct.toFixed(1)}%
                </div>
              )}
            </div>
            <div className={`bg-blue-500/10 rounded-xl text-center border border-blue-500/40 ${compact ? 'p-3' : 'rounded-2xl p-7'}`}>
              <div className={`flex items-center justify-center font-bold text-blue-400 ${compact ? 'gap-1 text-[11px] mb-1.5' : 'gap-2 text-lg mb-3'}`}>
                <Shield size={compact ? 11 : 20} /> 손절가
              </div>
              {!compact && <div className="text-sm font-medium text-blue-400/70 mb-3">손절 기준</div>}
              <div className={`font-extrabold tabular text-blue-400 ${compact ? 'text-[13px]' : 'text-2xl'}`}>{fmt.price(rec.stop_loss_price)}</div>
              {rec.rationale?.stop_dist_pct != null && (
                <div className={`font-bold text-blue-400 tabular ${compact ? 'text-[11px] mt-1' : 'text-base mt-2.5'}`}>
                  -{rec.rationale.stop_dist_pct.toFixed(1)}%
                </div>
              )}
            </div>
          </div>

          {/* R:R / 보유기간 / 리스크 */}
          <div className={`grid grid-cols-3 ${compact ? 'gap-2' : 'gap-5'}`}>
            <div className={`bg-[var(--bg)] rounded-xl text-center border border-[var(--border)] ${compact ? 'px-2 py-2.5' : 'rounded-2xl px-6 py-5'}`}>
              <div className={`flex items-center justify-center font-semibold text-[var(--muted)] ${compact ? 'gap-1 text-[10px] mb-1' : 'gap-2 text-base mb-2.5'}`}>
                <TrendingUp size={compact ? 11 : 17} /> 리스크/리워드
              </div>
              <div className={`font-extrabold tabular text-[var(--fg)] ${compact ? 'text-base' : 'text-3xl'}`}>
                {rec.risk_reward_ratio?.toFixed(1) ?? '—'}
              </div>
              <div className={`text-[var(--muted)] ${compact ? 'text-[10px] mt-0.5' : 'text-sm mt-1'}`}>R:R 비율</div>
            </div>
            <div className={`bg-[var(--bg)] rounded-xl text-center border border-[var(--border)] ${compact ? 'px-2 py-2.5' : 'rounded-2xl px-6 py-5'}`}>
              <div className={`flex items-center justify-center font-semibold text-[var(--muted)] ${compact ? 'gap-1 text-[10px] mb-1' : 'gap-2 text-base mb-2.5'}`}>
                <BarChart2 size={compact ? 11 : 17} /> 예상 보유
              </div>
              <div className={`font-extrabold tabular text-[var(--fg)] ${compact ? 'text-base' : 'text-3xl'}`}>{rec.expected_hold_days}일</div>
              <div className={`text-[var(--muted)] ${compact ? 'text-[10px] mt-0.5' : 'text-sm mt-1'}`}>권장 보유기간</div>
            </div>
            <div className={`bg-[var(--bg)] rounded-xl text-center border border-[var(--border)] ${compact ? 'px-2 py-2.5' : 'rounded-2xl px-6 py-5'}`}>
              <div className={`font-semibold text-[var(--muted)] ${compact ? 'text-[10px] mb-1' : 'text-base mb-2.5'}`}>리스크 점수</div>
              <div className={clsx(compact ? 'text-base' : 'text-3xl', 'font-extrabold tabular',
                (rec.risk_score ?? 0) >= 0.5 ? 'text-red-400' : 'text-green-400'
              )}>
                {rec.risk_score?.toFixed(2) ?? '—'}
              </div>
              <div className={`text-[var(--muted)] ${compact ? 'text-[10px] mt-0.5' : 'text-sm mt-1'}`}>
                {(rec.risk_score ?? 0) >= 0.5 ? '고위험' : '저위험'}
              </div>
            </div>
          </div>

          {/* AI 분석 해설 */}
          <div className="rounded-xl border border-cyan-500/30 overflow-hidden bg-[var(--card2)]">
            <div className={`flex items-center gap-2 border-b border-cyan-500/20 bg-cyan-500/8 ${compact ? 'px-4 py-2.5' : 'px-8 py-6'}`}>
              <BrainCircuit size={compact ? 16 : 26} className="text-cyan-400 shrink-0" />
              <span className={compact ? 'text-sm font-bold text-[var(--fg)]' : 'text-xl font-extrabold text-[var(--fg)]'}>AI 분석 해설</span>
              {rec.rationale?.atr_based && (
                <span className={`ml-auto font-bold text-cyan-300 bg-cyan-500/15 border border-cyan-500/30 rounded-full ${compact ? 'text-[10px] px-2 py-0.5' : 'text-sm px-3 py-1'}`}>
                  ATR 기반
                </span>
              )}
            </div>
            <div className={compact ? 'px-4 py-3' : 'px-8 py-7'}>
              <p className={`modal-narrative text-[var(--fg)] ${compact ? 'text-sm font-medium leading-relaxed' : 'text-[18px] leading-[2.1]'}`}>
                <RecNarrative rec={rec} />
              </p>
            </div>
          </div>

          {/* 유사 과거 사례 */}
          {rec.similar_cases && rec.similar_cases.length > 0 && (
            <div className={`rounded-xl border border-[var(--border)] overflow-hidden`}>
              <div className={`flex items-center gap-2 border-b border-[var(--border)]/60 bg-[var(--bg)] ${compact ? 'px-4 py-2.5' : 'px-8 py-5'}`}>
                <History size={compact ? 14 : 20} className="text-purple-400 shrink-0" />
                <span className={compact ? 'text-sm font-bold text-[var(--fg)]' : 'text-lg font-bold text-[var(--fg)]'}>
                  유사 과거 사례
                </span>
                <span className="ml-auto text-xs text-[var(--muted)]">
                  총 {rec.rationale?.sim_count ?? rec.similar_cases.length}건 검색 ·{' '}
                  {rec.rationale?.avg_sim_return != null && (
                    <span className={clsx('font-semibold', pctColor(rec.rationale.avg_sim_return))}>
                      평균 {rec.rationale.avg_sim_return >= 0 ? '+' : ''}{(rec.rationale.avg_sim_return * 100).toFixed(1)}%
                    </span>
                  )}
                </span>
              </div>
              <div className={`${compact ? 'px-4 py-3 space-y-2' : 'px-8 py-5 space-y-2.5'}`}>
                {rec.similar_cases.slice(0, 5).map((sc, i) => (
                  <SimilarCaseCard key={`${sc.code}-${sc.date}-${i}`} sc={sc} rank={i + 1} />
                ))}
              </div>
            </div>
          )}

          {/* 하단 */}
          <div className="flex items-center justify-end pb-1">
            <button
              onClick={onGoDetail}
              className={`font-bold text-cyan-400 hover:text-cyan-200 transition-colors flex items-center gap-2 rounded-xl bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 ${compact ? 'text-sm px-3 py-2' : 'text-lg px-5 py-2.5'}`}
            >
              종목 상세 보기 →
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
