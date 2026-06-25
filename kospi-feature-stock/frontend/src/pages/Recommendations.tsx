import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { TrendingUp, Shield, Zap, Target, X, ChevronRight, AlertTriangle, BrainCircuit, ExternalLink, Info, AlertCircle, ChevronDown } from 'lucide-react'
import { recommendationsApi } from '@/api/recommendations'
import type { SignalItem } from '@/api/recommendations'
import { Badge, ActionBadge, MarketBadge, EVENT_NAMES } from '@/components/ui/Badge'
import { StatCard, Card, CardBody } from '@/components/ui/Card'
import { fmt, pctColor, probColor, probToScore, scoreBarColor, recScoreBand } from '@/lib/utils'
import type { Recommendation } from '@/types'
import { RecDetailModal } from '@/components/modals/RecDetailModal'
import { ErrorState } from '@/components/ui/ErrorState'

// ── 날짜/시간 초 단위 포맷 ───────────────────────────────────────────────────
function fmtSec(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}.${pad(d.getMonth()+1)}.${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  } catch { return iso.slice(0, 19).replace('T', ' ') }
}

// ── 종합 추천 요약 섹션 ──────────────────────────────────────────────────────
function SignalSummary({ signals }: { signals: SignalItem[] }) {
  if (!signals.length) return null
  const sorted  = [...signals].sort((a, b) => b.success_prob - a.success_prob)
  const best    = sorted[0]
  const avgProb = signals.reduce((s, r) => s + r.success_prob, 0) / signals.length
  const prices  = signals.map((r) => r.entry_price)
  const minP    = Math.min(...prices)
  const maxP    = Math.max(...prices)
  const priceSpread = maxP - minP

  // 이벤트 타입 집계
  const evtMap: Record<string, number> = {}
  signals.forEach((s) => {
    const et = s.fe_event_type || s.rationale?.event_type || '—'
    evtMap[et] = (evtMap[et] || 0) + 1
  })
  const topEvts = Object.entries(evtMap).sort(([, a], [, b]) => b - a)

  // ML 확률 평균
  const mlVals  = signals.filter((s) => s.rationale?.ml_prob != null).map((s) => s.rationale!.ml_prob!)
  const avgML   = mlVals.length ? mlVals.reduce((a, b) => a + b, 0) / mlVals.length : null

  // 위험 요소 집계
  const riskMap: Record<string, number> = {}
  signals.forEach((s) => s.rationale?.risk_factors?.forEach((f: string) => { riskMap[f] = (riskMap[f] || 0) + 1 }))
  const topRisks = Object.entries(riskMap).sort(([, a], [, b]) => b - a).slice(0, 4)

  // 유사 케이스 (best 기준)
  const simCount  = best.rationale?.sim_count  ?? 0
  const simReturn = best.rationale?.avg_sim_return
  const atrBased  = best.rationale?.atr_based ?? false

  return (
    <div className="bg-[var(--bg)] rounded-xl p-4 space-y-3 border border-cyan-500/20">
      <div className="text-xs font-semibold text-cyan-400">종합 추천 근거</div>

      {/* 핵심 지표 4박스 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <div className="bg-[var(--card)] rounded-lg p-2 text-center">
          <div className="text-sm text-[var(--muted)] font-medium">최고 성공확률</div>
          <div className={clsx('text-sm font-bold tabular mt-0.5', probColor(best.success_prob))}>
            {fmt.prob(best.success_prob)}
          </div>
          <div className="text-sm text-[var(--muted)] font-medium">평균 {(avgProb * 100).toFixed(1)}%</div>
        </div>
        {avgML != null && (
          <div className="bg-[var(--card)] rounded-lg p-2 text-center">
            <div className="text-sm text-[var(--muted)] font-medium">ML 예측 평균</div>
            <div className={clsx('text-sm font-bold tabular mt-0.5', probColor(avgML))}>
              {(avgML * 100).toFixed(1)}%
            </div>
            <div className="text-sm text-[var(--muted)] font-medium">모델 확률</div>
          </div>
        )}
        <div className="bg-red-500/10 rounded-lg p-2 text-center border border-red-500/15">
          <div className="text-xs text-red-400">최고신호 목표가</div>
          <div className="text-sm font-bold tabular mt-0.5 text-red-400">{fmt.price(best.target_price)}</div>
          <div className="text-sm text-[var(--muted)] font-medium">R:R {best.risk_reward_ratio?.toFixed(1) ?? '—'}</div>
        </div>
        <div className="bg-blue-500/10 rounded-lg p-2 text-center border border-blue-500/15">
          <div className="text-xs text-blue-400">최고신호 손절가</div>
          <div className="text-sm font-bold tabular mt-0.5 text-blue-400">{fmt.price(best.stop_loss_price)}</div>
          <div className="text-sm text-[var(--muted)] font-medium">{atrBased ? 'ATR 기반' : '고정 비율'}</div>
        </div>
      </div>

      {/* 탐지 이벤트 분포 */}
      <div className="flex flex-wrap gap-1.5 items-center">
        <span className="text-xs text-[var(--muted)] shrink-0">탐지 이벤트:</span>
        {topEvts.map(([et, cnt]) => (
          <span key={et} className="flex items-center gap-0.5">
            <Badge eventType={et} size="sm" />
            <span className="text-xs text-[var(--muted)] tabular">×{cnt}</span>
          </span>
        ))}
      </div>

      {/* 유사 케이스 + ATR */}
      {simCount > 0 && (
        <div className="text-sm text-[var(--muted)] font-medium">
          유사 과거 사례 <span className="text-[var(--fg)] font-semibold">{simCount}건</span>
          {simReturn != null && (
            <span className={clsx('ml-1 font-semibold', simReturn >= 0 ? 'text-red-400' : 'text-blue-400')}>
              · 평균 {simReturn >= 0 ? '+' : ''}{(simReturn * 100).toFixed(1)}%
            </span>
          )}
          {atrBased && <span className="ml-2 text-cyan-400 font-semibold">· ATR 기반 손절/목표</span>}
        </div>
      )}

      {/* 위험 요소 */}
      {topRisks.length > 0 && (
        <div className="flex flex-wrap gap-1 items-center">
          <span className="text-xs text-[var(--muted)] shrink-0">위험 요소:</span>
          {topRisks.map(([r, cnt]) => (
            <span key={r} className="text-xs px-1.5 py-0.5 rounded bg-red-500/10 text-red-400">
              {r}{cnt > 1 ? ` ×${cnt}` : ''}
            </span>
          ))}
        </div>
      )}

      {/* 진입가 분산 경고 */}
      {priceSpread > 0 && (
        <div className="flex items-start gap-2 text-xs bg-yellow-500/10 rounded-lg px-3 py-2 text-yellow-400/90">
          <AlertTriangle size={11} className="mt-0.5 shrink-0" />
          <span>
            진입가가 <strong>{fmt.price(minP)} ~ {fmt.price(maxP)}</strong> 범위로 분산됨 —
            실시간 탐지 특성상 감지 시점마다 시장가가 진입가로 반영됩니다.
            <span className="text-[var(--muted)]"> 가장 최근 신호의 진입가를 기준으로 매매하세요.</span>
          </span>
        </div>
      )}
    </div>
  )
}

// ── 안전한 볼드 렌더러 (<b> / <b class="..."> 태그만 허용) ──────────────────
function SafeHtml({ html }: { html: string }): React.ReactElement {
  const nodes: React.ReactNode[] = []
  let remaining = html
  let key = 0
  while (remaining.length > 0) {
    const bStart = remaining.indexOf('<b')
    if (bStart === -1) { nodes.push(<span key={key++}>{remaining}</span>); break }
    if (bStart > 0) nodes.push(<span key={key++}>{remaining.slice(0, bStart)}</span>)
    const bEnd = remaining.indexOf('</b>', bStart)
    if (bEnd === -1) { nodes.push(<span key={key++}>{remaining.slice(bStart)}</span>); break }
    const tag = remaining.slice(bStart, bEnd + 4)
    const cls = (tag.match(/class="([^"]*)"/) ?? [])[1] ?? ''
    const inner = (tag.match(/>([^<]*)<\/b>/) ?? [])[1] ?? ''
    nodes.push(<b key={key++} className={cls}>{inner}</b>)
    remaining = remaining.slice(bEnd + 4)
  }
  return <>{nodes}</>
}

// ── AI 분석 해설 ─────────────────────────────────────────────────────────────
function RecommendationNarrative({ signals }: { signals: SignalItem[] }) {
  if (!signals.length) return null

  const sorted   = [...signals].sort((a, b) => b.success_prob - a.success_prob)
  const best     = sorted[0]
  const avgProb  = signals.reduce((s, r) => s + r.success_prob, 0) / signals.length

  const evtMap: Record<string, number> = {}
  signals.forEach((s) => {
    const et = s.fe_event_type || s.rationale?.event_type || '기타'
    evtMap[et] = (evtMap[et] || 0) + 1
  })
  const topEvts  = Object.entries(evtMap).sort(([, a], [, b]) => b - a)
  const domEvt   = topEvts[0]?.[0]

  const mlVals   = signals.filter((s) => s.rationale?.ml_prob != null).map((s) => s.rationale!.ml_prob!)
  const avgML    = mlVals.length ? mlVals.reduce((a, b) => a + b, 0) / mlVals.length : null

  const riskMap: Record<string, number> = {}
  signals.forEach((s) => s.rationale?.risk_factors?.forEach((f: string) => { riskMap[f] = (riskMap[f] || 0) + 1 }))
  const topRisks = Object.entries(riskMap).sort(([, a], [, b]) => b - a).slice(0, 3)

  const simCount  = best.rationale?.sim_count  ?? 0
  const simReturn = best.rationale?.avg_sim_return
  const atrBased  = best.rationale?.atr_based ?? false

  const parts: string[] = []

  // 1. 신호 개요
  if (signals.length === 1) {
    parts.push(`이 종목은 1건의 매수 신호가 감지되었으며 성공 확률은 <b>${fmt.prob(best.success_prob)}</b>입니다.`)
  } else {
    parts.push(
      `이 종목에서 <b>${signals.length}건</b>의 매수 신호가 반복 감지되었습니다. ` +
      `최고 성공 확률 <b>${fmt.prob(best.success_prob)}</b>, 평균 <b>${(avgProb * 100).toFixed(1)}%</b>로, ` +
      `복수 신호가 누적될수록 추세 지속 신뢰도가 높아집니다.`
    )
  }

  // 2. 이벤트 원인 설명
  if (domEvt) {
    const name = EVENT_NAMES[domEvt] || domEvt
    if (topEvts.length === 1) {
      parts.push(`신호의 핵심 원인은 <b>${name}</b> 이벤트입니다.`)
    } else {
      const others = topEvts.slice(1, 3).map(([et]) => EVENT_NAMES[et] || et).join(', ')
      parts.push(`신호의 주요 원인은 <b>${name}</b>이며, ${others} 등 복합 요인이 동시에 감지되어 신뢰도를 높이고 있습니다.`)
    }
  }

  // 3. ML 모델 해설
  if (avgML != null) {
    const mlStr = (avgML * 100).toFixed(1)
    if (avgML >= 0.35) {
      parts.push(
        `ML 모델의 평균 예측 확률은 <b>${mlStr}%</b>로 높은 편이며, ` +
        `이는 학습된 패턴 기반으로 단기 상승 가능성이 상당히 높다고 판단한 결과입니다.`
      )
    } else if (avgML >= 0.22) {
      parts.push(
        `ML 모델의 평균 예측 확률은 <b>${mlStr}%</b>로 추천 최소 기준(22%)을 충족합니다. ` +
        `다른 조건들과 함께 고려하면 유효한 신호입니다.`
      )
    } else {
      parts.push(
        `ML 모델의 평균 예측 확률은 <b>${mlStr}%</b>로 다소 낮으므로, ` +
        `이벤트 강도 및 시장 흐름과 병행하여 신중하게 판단하시기 바랍니다.`
      )
    }
  }

  // 4. 유사 과거 사례
  if (simCount > 0 && simReturn != null) {
    const retStr  = (simReturn * 100).toFixed(1)
    const retSign = simReturn >= 0 ? '+' : ''
    if (simReturn >= 0) {
      parts.push(
        `과거 유사 패턴 <b>${simCount}건</b>을 분석한 결과 평균 <b class="text-red-400">${retSign}${retStr}%</b>의 ` +
        `수익이 발생하였으며, 유사 사례 수가 많을수록 통계적 신뢰도가 올라갑니다.`
      )
    } else {
      parts.push(
        `과거 유사 패턴 <b>${simCount}건</b>의 평균 결과는 <b class="text-blue-400">${retSign}${retStr}%</b>로, ` +
        `손절 전략을 철저히 지키는 것이 특히 중요합니다.`
      )
    }
  } else if (simCount > 0) {
    parts.push(`유사 과거 패턴 <b>${simCount}건</b>이 확률 산정에 반영되었습니다.`)
  }

  // 5. ATR 기반 가격 설명
  if (atrBased) {
    parts.push(
      `손절가와 목표가는 <b>ATR(평균 변동폭)</b> 기반으로 동적 산정되었습니다. ` +
      `고정 비율 방식과 달리 해당 종목의 최근 변동성을 반영하므로, ` +
      `급등·급락장에서도 합리적인 리스크 범위를 유지합니다.`
    )
  } else {
    parts.push(`손절가와 목표가는 진입가 기준 고정 비율로 설정되어 있습니다.`)
  }

  // 6. 위험 요소
  if (topRisks.length > 0) {
    const riskStr = topRisks.map(([r]) => `<b>${r}</b>`).join(', ')
    parts.push(
      `주의할 위험 요소로는 ${riskStr} 등이 식별되었습니다. ` +
      `반드시 손절 원칙을 준수하고 포지션 규모를 적절히 조절하시기 바랍니다.`
    )
  } else {
    parts.push(`현재 별도로 식별된 위험 요소는 없습니다. 단, 시장 전반 변동성에는 항상 유의하십시오.`)
  }

  return (
    <div className="bg-[var(--bg)] rounded-xl p-4 border border-[var(--border)]/60 space-y-2">
      <div className="flex items-center gap-1.5 text-xs font-semibold text-[var(--muted)]">
        <BrainCircuit size={12} className="text-cyan-400" />
        <span>AI 분석 해설</span>
        <span className="text-[var(--border)] font-normal">· 탐지 데이터 기반 자동 생성</span>
      </div>
      <p className="text-xs text-[var(--muted)] leading-relaxed">
        {parts.map((part, i) => <span key={i}><SafeHtml html={part} />{' '}</span>)}
      </p>
    </div>
  )
}

// ── 신호 타임라인 테이블 행 ──────────────────────────────────────────────────
function SignalRow({ sig, index }: { sig: SignalItem; index: number }) {
  const dt      = sig.fe_detected_at || sig.created_at
  const evtType = sig.fe_event_type || sig.rationale?.event_type
  return (
    <tr className="border-b border-[var(--border)]/40 hover:bg-[var(--border)]/15">
      <td className="py-2 pr-3 tabular text-sm text-[var(--muted)] whitespace-nowrap">{fmtSec(dt)}</td>
      <td className="py-1.5 pr-3">
        {evtType ? <Badge eventType={evtType} size="sm" /> : <span className="text-[var(--muted)]">—</span>}
      </td>
      <td className="py-1.5 pr-3 text-right tabular text-[var(--fg)]">{fmt.price(sig.entry_price)}</td>
      <td className="py-1.5 pr-3 text-right tabular text-red-400">{fmt.price(sig.target_price)}</td>
      <td className="py-1.5 pr-3 text-right tabular text-blue-400">{fmt.price(sig.stop_loss_price)}</td>
      <td className={clsx('py-1.5 pr-3 text-right tabular font-semibold', probColor(sig.success_prob))}>
        {fmt.prob(sig.success_prob)}
      </td>
      <td className="py-1.5 pr-2 text-right tabular text-[var(--muted)]">
        {sig.risk_reward_ratio?.toFixed(1) ?? '—'}
      </td>
      <td className="py-1.5 text-right tabular text-xs text-[var(--muted)]">
        {sig.fe_signal_score != null ? sig.fe_signal_score.toFixed(2) : sig.rationale?.ml_prob != null ? (sig.rationale.ml_prob * 100).toFixed(0) + '%' : '—'}
      </td>
    </tr>
  )
}

// ── 추천 카드 컴포넌트 ────────────────────────────────────────────────────────
function RecCard({
  rec,
  crDelta,
  normProb,
  isToday,
  onOpen,
  onSignalModal,
  onNav,
}: {
  rec:          Recommendation
  crDelta:      number | null
  normProb:     number
  isToday:      boolean
  onOpen:       () => void
  onSignalModal: () => void
  onNav:        (code: string) => void
}) {
  const nav = useNavigate()
  const [showDetail, setShowDetail] = useState(false)

  return (
    <Card
      className={isToday
        ? 'border-amber-500/50 bg-amber-500/5 hover:border-amber-400/70 transition-colors cursor-pointer'
        : 'hover:border-cyan-500/40 transition-colors cursor-pointer'
      }
      onClick={onOpen}
    >
      <CardBody>
        {/* 헤더 */}
        <div className="flex items-start justify-between mb-3">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <button
                onClick={(e) => { e.stopPropagation(); onNav(rec.code) }}
                className="font-bold text-[0.9375rem] text-[var(--fg)] hover:text-cyan-400 transition-colors text-left"
              >
                {rec.name}
              </button>
              <MarketBadge market={rec.market} />
              {/* 신뢰도 등급 배지 */}
              {rec.rationale?.confidence_grade && (
                <span className={clsx(
                  'text-xs px-1.5 py-0.5 rounded border font-semibold',
                  rec.rationale.confidence_grade === 'A' ? 'border-green-500/40 text-green-400 bg-green-500/10' :
                  rec.rationale.confidence_grade === 'B' ? 'border-blue-500/40 text-blue-400 bg-blue-500/10' :
                  rec.rationale.confidence_grade === 'C' ? 'border-yellow-500/40 text-yellow-400 bg-yellow-500/10' :
                  'border-red-500/40 text-red-400 bg-red-500/10'
                )}>
                  {rec.rationale.confidence_grade}등급
                </span>
              )}
              {(rec.rec_count ?? 1) > 1 && (
                <button
                  onClick={(e) => { e.stopPropagation(); onSignalModal() }}
                  className="text-xs px-1.5 py-0.5 rounded-full bg-cyan-500/15 text-cyan-400 border border-cyan-500/25 font-semibold hover:bg-cyan-500/25 transition-colors flex items-center gap-0.5"
                >
                  {rec.rec_count}개 신호 <ChevronRight size={8} />
                </button>
              )}
            </div>
            <div className="text-sm text-[var(--muted)] mt-0.5">{rec.code} · 감지 {fmt.dateTime(rec.fe_detected_at ?? rec.created_at)}</div>
          </div>
          <div className="flex flex-col items-end gap-1 shrink-0">
            <ActionBadge action={rec.action} />
            {isToday && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full font-bold bg-amber-500/20 text-amber-400 border border-amber-500/40 whitespace-nowrap">
                오늘
              </span>
            )}
          </div>
        </div>

        {/* 추천 점수 */}
        <div className="mb-3">
          {(() => {
            const recScore = rec.rationale?.rec_score
            const score = recScore ?? probToScore(rec.success_prob)
            const band  = recScoreBand(score)
            return (
              <>
                <div className="flex justify-between text-sm mb-1.5">
                  <span className="flex items-center gap-1 text-[var(--muted)] font-medium">
                    추천 점수
                    <span title={`1~30 위험 / 31~49 중립 / 50~64 매수★ / 65~79 강한매수★★ / 80~100 최강매수★★★`} className="cursor-help">
                      <Info size={10} className="text-[var(--muted)]/60" />
                    </span>
                  </span>
                  <div className="flex items-baseline gap-1">
                    <span className={clsx('font-bold text-base tabular', band.colorClass)}>{score}점</span>
                    {band.stars && <span className={clsx('text-xs font-bold', band.colorClass)}>{band.stars}</span>}
                    <span className={clsx('text-xs font-semibold ml-0.5', band.colorClass)}>{band.label}</span>
                    <span className="text-xs text-[var(--muted)] tabular ml-1">ML {fmt.prob(rec.success_prob)}</span>
                  </div>
                </div>
                <div className="h-1.5 bg-[var(--border)] rounded-full overflow-hidden">
                  <div className={clsx('h-full rounded-full transition-all', band.barColorClass)} style={{ width: `${score}%` }} />
                </div>
              </>
            )
          })()}
        </div>

        {/* 경고 메시지 */}
        {(rec.rationale?.confidence_warnings?.length ?? 0) > 0 && (
          <div className="mb-3 px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/20">
            {rec.rationale!.confidence_warnings!.map((w, i) => (
              <p key={i} className="text-xs text-amber-400 flex items-center gap-1">
                <AlertCircle size={11} /> {w}
              </p>
            ))}
          </div>
        )}

        {/* 현재가 vs 진입가 */}
        {rec.current_price != null && (
          <div className="mb-3 flex items-center justify-between bg-[var(--bg)] rounded-lg px-3 py-1.5">
            <div className="flex items-center gap-1.5 text-xs">
              <span className="text-[var(--muted)] text-xs">현재가</span>
              <span className={clsx('font-bold tabular',
                (rec.current_change_rate ?? 0) > 0 ? 'text-red-400' : (rec.current_change_rate ?? 0) < 0 ? 'text-blue-400' : 'text-[var(--fg)]'
              )}>{fmt.price(rec.current_price)}</span>
              {rec.current_change_rate != null && rec.current_change_rate !== 0 && (
                <span className={clsx('text-xs tabular', rec.current_change_rate > 0 ? 'text-red-400' : 'text-blue-400')}>
                  {rec.current_change_rate > 0 ? '+' : ''}{rec.current_change_rate.toFixed(2)}%
                </span>
              )}
            </div>
            {crDelta != null && (
              <span className={clsx('text-xs tabular font-semibold', crDelta >= 0 ? 'text-red-400' : 'text-blue-400')}>
                진입대비 {crDelta >= 0 ? '+' : ''}{crDelta.toFixed(1)}%
              </span>
            )}
          </div>
        )}

        {/* 가격 정보 */}
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="bg-[var(--bg)] rounded-lg p-2">
            <div className="text-xs text-[var(--muted)] font-medium flex items-center justify-center gap-0.5 mb-1"><Zap size={9} /> 진입가</div>
            <div className="text-sm font-bold text-[var(--fg)] tabular">{fmt.price(rec.entry_price)}</div>
          </div>
          <div className="bg-red-500/10 rounded-lg p-2 border border-red-500/20">
            <div className="text-xs text-red-400 font-medium flex items-center justify-center gap-0.5 mb-1"><Target size={9} /> 목표가</div>
            <div className="text-sm font-bold text-red-400 tabular">{fmt.price(rec.target_price)}</div>
          </div>
          <div className="bg-blue-500/10 rounded-lg p-2 border border-blue-500/20">
            <div className="text-xs text-blue-400 font-medium flex items-center justify-center gap-0.5 mb-1"><Shield size={9} /> 손절가</div>
            <div className="text-sm font-bold text-blue-400 tabular">{fmt.price(rec.stop_loss_price)}</div>
          </div>
        </div>

        {/* 하단 메타 */}
        <div className="flex items-center justify-between mt-3 pt-3 border-t border-[var(--border)]">
          <div className="flex items-center gap-2 text-xs text-[var(--muted)]">
            <span className="flex items-center gap-0.5"><TrendingUp size={9} />R:R {rec.risk_reward_ratio?.toFixed(1) ?? '—'}</span>
            <span>예상 {rec.expected_hold_days}일</span>
            {rec.risk_score != null && (
              <span className={clsx(
                'px-1.5 py-0.5 rounded-full text-xs font-semibold border',
                rec.risk_score >= 0.6
                  ? 'bg-red-500/15 text-red-400 border-red-500/30'
                  : rec.risk_score >= 0.3
                  ? 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30'
                  : 'bg-green-500/15 text-green-400 border-green-500/30'
              )}>
                위험 {rec.risk_score >= 0.6 ? '높음' : rec.risk_score >= 0.3 ? '중간' : '낮음'}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            {rec.rationale?.model_mode === 'ml' ? (
              <span className="text-xs px-1.5 py-0.5 rounded border border-purple-500/30 text-purple-400">ML</span>
            ) : rec.rationale?.model_mode === 'fallback' ? (
              <span className="text-xs px-1.5 py-0.5 rounded border border-amber-500/30 text-amber-400">규칙기반</span>
            ) : null}
            {rec.rationale?.atr_based && (
              <span className="text-xs px-1.5 py-0.5 rounded border border-cyan-500/30 text-cyan-400">ATR</span>
            )}
            {rec.rationale?.event_type && <Badge eventType={rec.rationale.event_type} size="sm" />}
            <button
              onClick={(e) => { e.stopPropagation(); onNav(rec.code) }}
              className="text-[var(--muted)] hover:text-cyan-400 transition-colors p-0.5"
              title="종목 상세"
            >
              <ExternalLink size={11} />
            </button>
          </div>
        </div>

        {/* 상세 정보 접이식 */}
        {rec.rationale && (rec.rationale.risk_factors?.length || rec.rationale.sim_count) && (
          <div className="mt-2 pt-2 border-t border-[var(--border)]/50">
            <button
              onClick={(e) => { e.stopPropagation(); setShowDetail((v) => !v) }}
              className="flex items-center gap-1 text-xs text-[var(--muted)] hover:text-cyan-400 transition-colors"
            >
              {showDetail ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
              {showDetail ? '▲ 접기' : '▼ 상세'}
            </button>
            {showDetail && (
              <div className="mt-2 space-y-1.5">
                {rec.rationale.sim_count != null && rec.rationale.sim_count > 0 && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      if (rec.feature_event_id) {
                        nav(`/similar-cases/${rec.feature_event_id}`)
                      } else {
                        onOpen()
                      }
                    }}
                    className="flex items-center gap-1 text-xs text-[var(--muted)] hover:text-purple-400 transition-colors group"
                    title="유사사례 전용 페이지에서 보기"
                  >
                    <span>유사 사례</span>
                    <span className="text-[var(--fg)] font-semibold group-hover:text-purple-400">{rec.rationale.sim_count}건</span>
                    {rec.rationale.avg_sim_return != null && (
                      <span className={clsx('font-semibold', rec.rationale.avg_sim_return >= 0 ? 'text-red-400' : 'text-blue-400')}>
                        · 평균 {rec.rationale.avg_sim_return >= 0 ? '+' : ''}{rec.rationale.avg_sim_return.toFixed(1)}%
                      </span>
                    )}
                    <span className="ml-1 text-purple-400 opacity-0 group-hover:opacity-100 transition-opacity">→ 보기</span>
                  </button>
                )}
                {rec.rationale.risk_factors && rec.rationale.risk_factors.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {rec.rationale.risk_factors.map((r, i) => (
                      <span key={i} className="text-xs px-1.5 py-0.5 rounded bg-red-500/10 text-red-400">{r}</span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </CardBody>
    </Card>
  )
}

// ── 메인 페이지 ─────────────────────────────────────────────────────────────
export function Recommendations() {
  const nav = useNavigate()
  const [filter,     setFilter]     = useState<'ALL' | 'BUY' | 'WAIT' | 'SKIP'>('BUY')
  const [minProb,    setMinProb]    = useState(0.30)
  const [dedupe,     setDedupe]     = useState(true)
  const [signalModal, setSignalModal] = useState<{ code: string; name: string } | null>(null)
  const [selectedRec, setSelectedRec] = useState<Recommendation | null>(null)

  const { data: recs, isLoading, isError, error, refetch } = useQuery({
    queryKey:        ['recs', filter, minProb, dedupe],
    queryFn:         () => recommendationsApi.list({
      action:   filter === 'ALL' ? undefined : filter,
      min_prob: minProb,
      hours:    72,
      limit:    100,
      dedupe,
    }),
    refetchInterval: 60_000,
  })

  const { data: perf } = useQuery({
    queryKey:        ['perf-30'],
    queryFn:         () => recommendationsApi.getPerformance(30),
    refetchInterval: 300_000,
  })

  const { data: signalData, isLoading: signalsLoading } = useQuery({
    queryKey:  ['code-signals', signalModal?.code],
    queryFn:   () => recommendationsApi.codeSignals(signalModal!.code, 168),
    enabled:   !!signalModal,
    staleTime: 30_000,
  })

  // 탭 필터와 무관하게 BUY 신호 수를 항상 동일 기준으로 표시 (Dashboard와 동일: hours=72)
  const { data: buyRecs } = useQuery({
    queryKey:        ['recs-buy-count', minProb],
    queryFn:         () => recommendationsApi.list({ action: 'BUY', min_prob: minProb, hours: 72, limit: 100, dedupe: true }),
    refetchInterval: 60_000,
  })

  const buySignalCount = buyRecs?.length ?? 0

  // 현재 결과셋 기준 min-max 정규화 (1%~100%)
  const _probs   = recs?.map((r) => r.success_prob) ?? []
  const _probMin = _probs.length > 0 ? Math.min(..._probs) : 0
  const _probMax = _probs.length > 0 ? Math.max(..._probs) : 1
  const toNorm = (p: number): number =>
    _probMax > _probMin
      ? Math.round(((p - _probMin) / (_probMax - _probMin)) * 99 + 1)
      : 100

  return (
    <div className="p-5 space-y-5 max-w-[1600px]">

      {/* 성과 통계 */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="30일 성공률"
          value={perf ? `${(perf.success_rate * 100).toFixed(1)}%` : '—'}
          sub={`${perf?.success_count ?? '—'}건 성공`}
          valueColor={perf && perf.success_rate >= 0.55 ? 'text-green-400' : 'text-red-400'}
        />
        <StatCard
          label="평균 수익률"
          value={perf?.avg_return != null ? fmt.pct(perf.avg_return) : '—'}
          sub="매수 후 5일"
          valueColor={perf?.avg_return != null ? pctColor(perf.avg_return) : 'text-[var(--muted)]'}
        />
        <StatCard
          label="총 매수 신호"
          value={perf?.buy_count ?? '—'}
          sub="30일 누적"
          valueColor="text-cyan-400"
        />
        <StatCard
          label="현재 BUY 신호"
          value={buySignalCount}
          sub={`확률 ${(minProb * 100).toFixed(0)}% 이상`}
          valueColor="text-green-400"
        />
      </div>

      {/* 필터 바 */}
      <div className="flex flex-wrap items-center gap-3 p-4 bg-[var(--card)] border border-[var(--border)] rounded-xl">
        <div className="flex rounded-lg overflow-hidden border border-[var(--border)]">
          {(['ALL', 'BUY', 'WAIT', 'SKIP'] as const).map((a) => (
            <button
              key={a}
              onClick={() => setFilter(a)}
              className={clsx(
                'px-4 py-2 text-sm font-medium transition-colors',
                filter === a
                  ? 'bg-cyan-500/20 text-cyan-400'
                  : 'text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)]'
              )}
            >
              {a === 'ALL' ? '전체' : a}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <span className="text-sm text-[var(--muted)]">최소 확률</span>
          <input
            type="range" min="0.3" max="0.9" step="0.05" value={minProb}
            onChange={(e) => setMinProb(Number(e.target.value))}
            className="w-24 accent-cyan-400"
          />
          <span className="text-sm tabular text-cyan-400 font-semibold w-12">
            {(minProb * 100).toFixed(0)}%
          </span>
        </div>

        <button
          onClick={() => setDedupe((v) => !v)}
          className={clsx(
            'flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium border transition-colors',
            dedupe ? 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30' : 'text-[var(--muted)] border-[var(--border)] hover:text-[var(--fg)]',
          )}
        >
          {dedupe ? '종목 통합' : '전체 신호'}
        </button>
        {recs && recs.length > 0 && (() => {
          const probs = recs.map((r) => r.success_prob)
          const minP  = Math.min(...probs)
          const maxP  = Math.max(...probs)
          return (
            <span className="text-xs text-[var(--muted)] tabular whitespace-nowrap">
              성공확률&nbsp;
              <span className={clsx('font-semibold', probColor(minP))}>{(minP * 100).toFixed(1)}%</span>
              <span className="text-[var(--border)] mx-0.5">~</span>
              <span className={clsx('font-semibold', probColor(maxP))}>{(maxP * 100).toFixed(1)}%</span>
            </span>
          )
        })()}
        <button
          onClick={() => { setFilter('BUY'); setMinProb(0.30); setDedupe(true) }}
          className="ml-auto text-xs text-[var(--muted)] hover:text-[var(--fg)] transition-colors px-2 py-1 rounded hover:bg-[var(--border)]"
        >
          초기화
        </button>
        <div className="text-sm text-[var(--muted)] font-medium">
          {isLoading ? '로딩 중…' : `${recs?.length ?? 0}건`}
        </div>
      </div>

      {/* 신호 카드 그리드 */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {isError && (
          <div className="col-span-full">
            <ErrorState error={error as Error} retry={refetch} />
          </div>
        )}
        {isLoading && Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="bg-[var(--card)] border border-[var(--border)] rounded-2xl p-5 space-y-3">
            <div className="flex items-start justify-between">
              <div className="space-y-1.5 flex-1">
                <div className="h-4 skeleton rounded w-28" />
                <div className="h-3 skeleton rounded w-20" />
              </div>
              <div className="h-6 skeleton rounded w-12" />
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between">
                <div className="h-3 skeleton rounded w-16" />
                <div className="h-3 skeleton rounded w-10" />
              </div>
              <div className="h-2 skeleton rounded-full w-full" />
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div className="h-14 skeleton rounded-lg" />
              <div className="h-14 skeleton rounded-lg" />
              <div className="h-14 skeleton rounded-lg" />
            </div>
          </div>
        ))}
        {(() => {
          if (!recs || recs.length === 0) return null
          const todayKST = new Date(Date.now() + 9 * 3600_000).toISOString().slice(0, 10)
          const isToday = (rec: typeof recs[0]) => {
            const d = rec.fe_detected_at ?? rec.created_at
            return !!d && d.slice(0, 10) === todayKST
          }
          // 표시 점수(rec_score → probToScore 폴백) 기준 내림차순 정렬 후 그룹 분리
          const scored = [...recs].sort((a, b) => {
            const sa = a.rationale?.rec_score ?? probToScore(a.success_prob)
            const sb = b.rationale?.rec_score ?? probToScore(b.success_prob)
            return sb - sa
          })
          const todayRecs = scored.filter(isToday)
          const olderRecs = scored.filter((r) => !isToday(r))
          const todayCount = todayRecs.length

          return [...todayRecs, ...olderRecs].map((rec, idx) => {
            const crDelta = rec.current_price != null
              ? ((rec.current_price - rec.entry_price) / rec.entry_price * 100)
              : null
            const today = isToday(rec)

            // 오늘→이전 경계에 구분선 삽입
            const showDivider = todayCount > 0 && idx === todayCount

            return (
              <React.Fragment key={rec.id}>
                {showDivider && (
                  <div className="col-span-full flex items-center gap-3 py-1">
                    <div className="flex-1 border-t border-dashed border-[var(--border)]" />
                    <span className="text-xs text-[var(--muted)] whitespace-nowrap px-1">이전 추천</span>
                    <div className="flex-1 border-t border-dashed border-[var(--border)]" />
                  </div>
                )}
                <RecCard
                  rec={rec}
                  crDelta={crDelta}
                  normProb={toNorm(rec.success_prob)}
                  isToday={today}
                  onOpen={() => setSelectedRec(rec)}
                  onSignalModal={() => setSignalModal({ code: rec.code, name: rec.name })}
                  onNav={(code) => nav(`/search?code=${code}`)}
                />
              </React.Fragment>
            )
          })
        })()}
        {!isLoading && !isError && (!recs || recs.length === 0) && (
          <div className="col-span-full py-16 text-center text-[var(--muted)] text-sm">조건에 맞는 신호가 없습니다</div>
        )}
      </div>

      {/* ── 개별 추천 상세 팝업 ───────────────────────────────────────────────── */}
      {selectedRec && (
        <RecDetailModal
          rec={selectedRec}
          onClose={() => setSelectedRec(null)}
          onGoDetail={() => { setSelectedRec(null); nav(`/search?code=${selectedRec.code}`) }}
        />
      )}

      {/* ── 신호 상세 팝업 모달 ─────────────────────────────────────────────── */}
      {signalModal && (
        <div className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-6 overflow-y-auto"
          onClick={() => setSignalModal(null)}>
          <div className="absolute inset-0 bg-black/65" />
          <div
            className="relative bg-[var(--card)] border border-[var(--border)] rounded-2xl w-full max-w-5xl flex flex-col shadow-2xl mb-8"
            onClick={(e) => e.stopPropagation()}
          >
            {/* 모달 헤더 */}
            <div className="flex items-center justify-between p-4 border-b border-[var(--border)] shrink-0">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-bold text-[var(--fg)]">{signalModal.name}</span>
                  <span className="text-xs text-[var(--muted)]">{signalModal.code}</span>
                  {signalData != null && (
                    <span className="text-xs text-cyan-400 font-semibold bg-cyan-500/10 px-2 py-0.5 rounded-full">
                      {signalData.total_count}개 신호 (7일)
                    </span>
                  )}
                  {signalsLoading && <span className="text-xs text-[var(--muted)]">로딩 중…</span>}
                </div>
                <div className="text-xs text-[var(--muted)] mt-0.5">
                  각 신호는 탐지 시점의 시장가를 진입가로 사용합니다
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0 ml-4">
                <button
                  onClick={() => { setSignalModal(null); nav(`/search?code=${signalModal.code}`) }}
                  className="text-xs text-cyan-400 hover:text-cyan-300 flex items-center gap-1 transition-colors"
                >
                  종목 상세 <ChevronRight size={11} />
                </button>
                <button onClick={() => setSignalModal(null)} className="text-[var(--muted)] hover:text-[var(--fg)] transition-colors p-1">
                  <X size={16} />
                </button>
              </div>
            </div>

            {/* 모달 본문 */}
            <div className="overflow-y-auto max-h-[80vh] p-5 space-y-5">

              {/* 종합 추천 요약 */}
              {signalData && signalData.signals.length > 0 && (
                <SignalSummary signals={signalData.signals} />
              )}

              {/* AI 분석 해설 */}
              {signalData && signalData.signals.length > 0 && (
                <RecommendationNarrative signals={signalData.signals} />
              )}

              {/* 신호 타임라인 */}
              {signalData && signalData.signals.length > 0 && (
                <div>
                  <div className="text-xs font-semibold text-[var(--muted)] mb-2 flex items-center gap-2">
                    신호 이력
                    <span className="text-cyan-400 font-bold">{signalData.total_count}건</span>
                    <span className="text-xs font-normal">(최신순 · 최대 200건)</span>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-[var(--border)] text-[var(--muted)]">
                          <th className="text-left pb-2 pr-3 text-xs font-semibold uppercase tracking-wider whitespace-nowrap">감지 시간</th>
                          <th className="text-left pb-2 pr-3 text-xs font-semibold uppercase tracking-wider">이벤트</th>
                          <th className="text-right pb-2 pr-3 text-xs font-semibold uppercase tracking-wider">진입가</th>
                          <th className="text-right pb-2 pr-3 text-xs font-semibold uppercase tracking-wider">목표가</th>
                          <th className="text-right pb-2 pr-3 text-xs font-semibold uppercase tracking-wider">손절가</th>
                          <th className="text-right pb-2 pr-3 text-xs font-semibold uppercase tracking-wider">
                            <span className="flex items-center justify-end gap-1">
                              성공률
                              <span title="ML추정 · 상한95%" className="cursor-help">
                                <Info size={9} className="text-[var(--muted)]/60" />
                              </span>
                            </span>
                          </th>
                          <th className="text-right pb-2 pr-2 text-xs font-semibold uppercase tracking-wider">R:R</th>
                          <th className="text-right pb-2 text-xs font-semibold uppercase tracking-wider">점수</th>
                        </tr>
                      </thead>
                      <tbody>
                        {signalData.signals.map((sig, i) => (
                          <SignalRow key={sig.id} sig={sig} index={i} />
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {!signalsLoading && !signalData?.signals?.length && (
                <div className="py-12 text-center text-[var(--muted)] text-sm">신호 없음</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
