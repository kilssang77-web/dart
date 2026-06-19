// v3
import type { ReactNode } from 'react'
import { X, Target, Shield, Zap, TrendingUp, BrainCircuit, BarChart2, Clock, History } from 'lucide-react'
import { clsx } from 'clsx'
import { fmt, probColor, pctColor, probToScore, scoreBarColor } from '@/lib/utils'
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
            {best >= 0 ? '+' : ''}{best.toFixed(1)}%
            <span className="text-xs font-normal text-[var(--muted)] ml-1">
              {sc.return_5d != null ? '5일' : sc.return_3d != null ? '3일' : '1일'}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}


function SimilarCasesNarrative({ cases, avgReturn, simCount, compact }: {
  cases: SimilarCase[]
  avgReturn?: number | null
  simCount?: number | null
  compact?: boolean
}) {
  if (!cases.length && avgReturn == null) return null

  // 표시된 사례 중 수익 데이터 집계
  const with5d = cases.filter((c) => c.return_5d != null)
  const with3d = cases.filter((c) => c.return_3d != null)
  const with1d = cases.filter((c) => c.return_1d != null)

  // 각 사례의 "가장 긴 보유 수익"을 대표값으로 사용
  const returns5d = with5d.map((c) => c.return_5d!)
  const allReturns = cases.map((c) => c.return_5d ?? c.return_3d ?? c.return_1d).filter((v): v is number => v != null)

  const totalWithData = allReturns.length
  const positiveCount = allReturns.filter((r) => r > 0).length
  const negativeCount = allReturns.filter((r) => r < 0).length
  const positivePct   = totalWithData > 0 ? Math.round((positiveCount / totalWithData) * 100) : null

  const maxRet = allReturns.length > 0 ? Math.max(...allReturns) : null
  const minRet = allReturns.length > 0 ? Math.min(...allReturns) : null

  const topBySim = [...cases].sort((a, b) => b.similarity - a.similarity)[0]
  const topReturn = topBySim ? (topBySim.return_5d ?? topBySim.return_3d ?? topBySim.return_1d) : null
  const topPeriod = topBySim
    ? (topBySim.return_5d != null ? '5일' : topBySim.return_3d != null ? '3일' : '1일')
    : null

  const fmt2 = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`

  // 어떤 기간 데이터가 주로 사용됐는지
  const dominantPeriod = with5d.length >= with3d.length && with5d.length >= with1d.length
    ? '5일 후' : with3d.length >= with1d.length ? '3일 후' : '1일 후'

  const totalCount = simCount ?? cases.length

  const lines: string[] = []

  // 1. 평균 수치 산출 기준 설명
  if (avgReturn != null && totalWithData > 0) {
    lines.push(
      `위 중위수 ${fmt2(avgReturn)}은 전체 ${totalCount}건의 유사 사례 중 수익 데이터가 확인된 ${totalWithData}건을 대상으로 산출된 중위값입니다. ` +
      `각 사례의 수익은 주로 ${dominantPeriod} 종가 기준으로 측정되었으며${with5d.length > 0 && with3d.length > 0 ? `, 5일 기준 ${with5d.length}건·3일 기준 ${with3d.length}건·1일 기준 ${with1d.length}건이 포함되었습니다` : ''}.`
    )
  } else if (avgReturn != null) {
    lines.push(
      `위 중위수 ${fmt2(avgReturn)}은 ${totalCount}건의 유사 사례에 대한 보유 기간 수익률의 중위값입니다.`
    )
  } else if (totalWithData === 0) {
    lines.push(
      `${totalCount}건의 유사 사례가 ML 확률 산정에 참조되었으나, 해당 사례들의 보유 기간 수익 데이터는 아직 축적되지 않아 평균 수익을 산출할 수 없습니다.`
    )
  }

  // 2. 수익 분포 (양수/음수 비율)
  if (positivePct != null && totalWithData > 0) {
    const trend = positivePct >= 60
      ? '상승 우세(매수 성공률 양호)'
      : positivePct >= 40
        ? '혼조세(상승·하락이 팽팽)'
        : '하락 우세(신중한 접근 필요)'
    lines.push(
      `수익 데이터가 있는 ${totalWithData}건 중 ${positiveCount}건(${positivePct}%)이 양의 수익을 기록했고 ${negativeCount}건은 손실을 기록해 ${trend}를 보였습니다.`
    )
  }

  // 3. 수익 범위
  if (maxRet != null && minRet != null && maxRet !== minRet) {
    lines.push(
      `수익 분포 범위는 최고 ${fmt2(maxRet)}에서 최저 ${fmt2(minRet)}으로, ` +
      `동일 패턴이더라도 시장 국면과 종목 특성에 따라 결과가 크게 달라질 수 있음을 나타냅니다.`
    )
  }

  // 4. 최고 유사도 사례 설명
  if (topBySim && topReturn != null && topPeriod) {
    lines.push(
      `표시된 사례 중 현재 패턴과 가장 유사한 사례는 ${topBySim.name ?? topBySim.code}(${topBySim.date?.slice(0, 10)}, 유사도 ${(topBySim.similarity * 100).toFixed(0)}%)로, ` +
      `${topPeriod} 수익 ${fmt2(topReturn)}를 기록했습니다.`
    )
  }

  // 5. 면책 안내
  lines.push(
    `이 분석은 과거 패턴의 통계적 경향을 참고하기 위한 것으로 미래 수익을 보장하지 않습니다. 반드시 설정된 손절가를 준수하여 리스크를 관리하세요.`
  )

  return (
    <div className={`border-t border-purple-500/20 bg-purple-500/5 ${compact ? 'px-4 py-3' : 'px-8 py-5'}`}>
      <p className={`text-[var(--muted)] leading-relaxed ${compact ? 'text-[11px]' : 'text-sm'}`} style={{ lineHeight: compact ? 1.7 : 1.9 }}>
        {lines.map((s, i) => (
          <span key={i}>
            {i > 0 && ' '}
            {s}
          </span>
        ))}
      </p>
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
  const scoreVal = rec.success_prob != null ? probToScore(rec.success_prob) : null
  const probLabel = scoreVal != null
    ? <><B>{scoreVal}점</B> <span style={{fontSize:'0.85em',opacity:0.7}}>({fmt.prob(rec.success_prob)})</span></>
    : <B>{fmt.prob(rec.success_prob)}</B>

  if (rec.action === 'BUY') {
    sentences.push(<span key="action">ML 모델이 이 종목을 <B>매수(BUY)</B> 추천합니다. 성공 확률 {probLabel}로 모델이 단기 상승 가능성이 높다고 판단했습니다.</span>)
  } else if (rec.action === 'WAIT') {
    sentences.push(<span key="action">현재 조건이 완전히 충족되지 않아 <B>대기(WAIT)</B> 신호입니다. 성공 확률 {probLabel}로, 조건이 개선되면 BUY 신호로 전환될 수 있습니다.</span>)
  } else {
    sentences.push(<span key="action">현재 리스크가 높아 <B>보류(SKIP)</B> 판단입니다. 신호 확률 {probLabel}.</span>)
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
    sentences.push(<span key="sim"> 과거 유사 패턴 <B>{simCount}건</B>에서 중위수 <B>{retSign}{simReturn.toFixed(1)}%</B>의 수익이 관측됐습니다.</span>)
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

  const score    = rec.success_prob != null ? probToScore(rec.success_prob) : 1
  const barColor = scoreBarColor(score)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4" data-v="2" onClick={onClose}>
      <div className="absolute inset-0 bg-black/85 backdrop-blur-md" />
      <div
        className={`relative bg-[var(--card)] border border-[var(--border)] rounded-2xl shadow-[0_32px_80px_rgba(0,0,0,0.7)] flex flex-col ${compact ? 'w-[88vw] max-w-[460px]' : 'w-[92vw] max-w-[900px]'}`}
        style={{ maxHeight: compact ? '72vh' : '95vh' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── 헤더 ── */}
        <div className="flex items-start justify-between border-b-2 border-[var(--border)] shrink-0 px-5 py-4">
          <div className="flex flex-col gap-1 min-w-0 pr-3">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-base font-bold text-[var(--fg)] tracking-tight">{rec.name}</span>
              <ActionBadge action={rec.action} />
              {rec.rationale?.event_type && <Badge eventType={rec.rationale.event_type} size="sm" />}
            </div>
            <div className="flex items-center gap-2 text-xs font-medium text-[var(--muted)]">
              <span className="font-mono">{rec.code}</span>
              <span className="opacity-40">·</span>
              <span>{rec.market}</span>
              <span className="opacity-40">·</span>
              <span className="flex items-center gap-1"><Clock size={11} />{fmt.dateTime(rec.created_at)}</span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 flex items-center justify-center rounded-xl bg-[var(--bg)] text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)] transition-colors w-8 h-8"
          >
            <X size={16} />
          </button>
        </div>

        {/* ── 스크롤 본문 ── */}
        <div className="overflow-y-auto space-y-4 px-5 py-4" style={{ flex: 1 }}>

          {/* 성공확률 */}
          <div>
            <div className="flex justify-between items-end mb-2">
              <span className="text-sm font-semibold text-[var(--fg)]">성공 확률</span>
              <div className="text-right">
                <span className={clsx('text-2xl font-extrabold tabular tracking-tight', scoreBarColor(score).replace('bg-', 'text-'))}>
                  {score}점
                </span>
                <div className="text-[var(--muted)] tabular text-[10px] mt-0.5">
                  ML확률 {fmt.prob(rec.success_prob)}
                </div>
              </div>
            </div>
            <div className="h-4 bg-[var(--border)] rounded-full overflow-hidden">
              <div
                className={clsx('h-full rounded-full transition-all duration-700', barColor)}
                style={{ width: `${score}%` }}
              />
            </div>
            <div className="flex justify-between text-[var(--muted)] mt-1.5 text-xs">
              <span>1점</span>
              <span className="text-yellow-400 font-semibold">31점</span>
              <span className="text-orange-400 font-semibold">51점</span>
              <span className="text-green-400 font-semibold">70점</span>
              <span>100점</span>
            </div>
          </div>

          {/* 현재가 vs 진입가 */}
          {rec.current_price != null && (
            <div className="flex items-center justify-between bg-[var(--bg)] border border-[var(--border)] rounded-xl px-4 py-2.5">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-[var(--muted)]">현재가</span>
                <span className={clsx('text-lg font-bold tabular',
                  (rec.current_change_rate ?? 0) > 0 ? 'text-red-400' :
                  (rec.current_change_rate ?? 0) < 0 ? 'text-blue-400' : 'text-[var(--fg)]'
                )}>
                  {fmt.price(rec.current_price)}
                </span>
                {rec.current_change_rate != null && rec.current_change_rate !== 0 && (
                  <span className={clsx(
                    'text-xs font-semibold px-2 py-0.5 rounded-lg',
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
                  <div className="text-[10px] font-medium text-[var(--muted)] mb-0.5">진입 대비</div>
                  <span className={clsx('text-base font-bold tabular',
                    crDelta >= 0 ? 'text-red-400' : 'text-blue-400'
                  )}>
                    {crDelta >= 0 ? '+' : ''}{crDelta.toFixed(1)}%
                  </span>
                </div>
              )}
            </div>
          )}

          {/* 가격 3박스 */}
          <div className="grid grid-cols-3 gap-2">
            <div className="bg-[var(--bg)] rounded-xl text-center border border-[var(--border)] p-3">
              <div className="flex items-center justify-center font-bold text-[var(--muted)] gap-1 text-[11px] mb-1.5">
                <Zap size={11} /> 진입가
              </div>
              <div className="font-bold tabular text-[var(--fg)] text-sm">{fmt.price(rec.entry_price)}</div>
            </div>
            <div className="bg-red-500/10 rounded-xl text-center border border-red-500/40 p-3">
              <div className="flex items-center justify-center font-bold text-red-400 gap-1 text-[11px] mb-1.5">
                <Target size={11} /> 목표가
              </div>
              <div className="font-bold tabular text-red-400 text-sm">{fmt.price(rec.target_price)}</div>
              {rec.rationale?.target_dist_pct != null && (
                <div className="font-semibold text-red-400 tabular text-[11px] mt-1">
                  +{rec.rationale.target_dist_pct.toFixed(1)}%
                </div>
              )}
            </div>
            <div className="bg-blue-500/10 rounded-xl text-center border border-blue-500/40 p-3">
              <div className="flex items-center justify-center font-bold text-blue-400 gap-1 text-[11px] mb-1.5">
                <Shield size={11} /> 손절가
              </div>
              <div className="font-bold tabular text-blue-400 text-sm">{fmt.price(rec.stop_loss_price)}</div>
              {rec.rationale?.stop_dist_pct != null && (
                <div className="font-semibold text-blue-400 tabular text-[11px] mt-1">
                  -{rec.rationale.stop_dist_pct.toFixed(1)}%
                </div>
              )}
            </div>
          </div>

          {/* R:R / 보유기간 / 리스크 */}
          <div className="grid grid-cols-3 gap-2">
            <div className="bg-[var(--bg)] rounded-xl text-center border border-[var(--border)] px-2 py-2.5">
              <div className="flex items-center justify-center font-semibold text-[var(--muted)] gap-1 text-[10px] mb-1">
                <TrendingUp size={11} /> 리스크/리워드
              </div>
              <div className="font-extrabold tabular text-[var(--fg)] text-lg">
                {rec.risk_reward_ratio?.toFixed(1) ?? '—'}
              </div>
              <div className="text-[var(--muted)] text-[10px] mt-0.5">R:R 비율</div>
            </div>
            <div className="bg-[var(--bg)] rounded-xl text-center border border-[var(--border)] px-2 py-2.5">
              <div className="flex items-center justify-center font-semibold text-[var(--muted)] gap-1 text-[10px] mb-1">
                <BarChart2 size={11} /> 예상 보유
              </div>
              <div className="font-extrabold tabular text-[var(--fg)] text-lg">{rec.expected_hold_days}일</div>
              <div className="text-[var(--muted)] text-[10px] mt-0.5">
                {rec.rationale?.sim_count && rec.rationale.sim_count >= 2 ? '유사사례 중위수' : '목표가 기반 추정'}
              </div>
            </div>
            <div className="bg-[var(--bg)] rounded-xl text-center border border-[var(--border)] px-2 py-2.5">
              <div className="font-semibold text-[var(--muted)] text-[10px] mb-1">리스크 점수</div>
              <div className={clsx('text-lg font-extrabold tabular',
                (rec.risk_score ?? 0) >= 0.5 ? 'text-red-400' : 'text-green-400'
              )}>
                {rec.risk_score?.toFixed(2) ?? '—'}
              </div>
              <div className="text-[var(--muted)] text-[10px] mt-0.5">
                {(rec.risk_score ?? 0) >= 0.5 ? '고위험' : '저위험'}
              </div>
            </div>
          </div>

          {/* AI 분석 해설 */}
          <div className="rounded-xl border border-cyan-500/30 overflow-hidden bg-[var(--card2)]">
            <div className="flex items-center gap-2 border-b border-cyan-500/20 bg-cyan-500/8 px-4 py-2.5">
              <BrainCircuit size={15} className="text-cyan-400 shrink-0" />
              <span className="text-sm font-bold text-[var(--fg)]">AI 분석 해설</span>
              {rec.rationale?.atr_based && (
                <span className="ml-auto text-[10px] font-bold text-cyan-300 bg-cyan-500/15 border border-cyan-500/30 rounded-full px-2 py-0.5">
                  ATR 기반
                </span>
              )}
            </div>
            <div className="px-4 py-3">
              <p className="modal-narrative text-[var(--fg)] text-sm leading-relaxed">
                <RecNarrative rec={rec} />
              </p>
            </div>
          </div>

          {/* 유사 과거 사례 */}
          {rec.similar_cases && rec.similar_cases.length > 0 && (
            <div className="rounded-xl border border-[var(--border)] overflow-hidden">
              <div className="flex items-center gap-2 border-b border-[var(--border)]/60 bg-[var(--bg)] px-4 py-2.5">
                <History size={14} className="text-purple-400 shrink-0" />
                <span className="text-sm font-bold text-[var(--fg)]">
                  유사 과거 사례
                </span>
                <span className="ml-auto text-xs text-[var(--muted)]">
                  총 {rec.rationale?.sim_count ?? rec.similar_cases.length}건 검색 ·{' '}
                  {rec.rationale?.avg_sim_return != null && (
                    <span className={clsx('font-semibold', pctColor(rec.rationale.avg_sim_return))}>
                      중위수 {rec.rationale.avg_sim_return >= 0 ? '+' : ''}{rec.rationale.avg_sim_return.toFixed(1)}%
                    </span>
                  )}
                </span>
              </div>
              {/* 평균 수치 산출 기준 서술형 설명 — 헤더 바로 아래 */}
              <SimilarCasesNarrative
                cases={rec.similar_cases}
                avgReturn={rec.rationale?.avg_sim_return}
                simCount={rec.rationale?.sim_count}
                compact={compact}
              />
              <div className="px-4 py-3 space-y-2">
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
              className="text-sm font-bold text-cyan-400 hover:text-cyan-200 transition-colors flex items-center gap-2 rounded-xl bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 px-3 py-2"
            >
              종목 상세 보기 →
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
