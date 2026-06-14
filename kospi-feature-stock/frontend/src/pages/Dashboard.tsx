import { useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  TrendingUp, TrendingDown, Minus, ArrowUpRight, ArrowDownRight,
  Zap, Target, ShieldAlert, BarChart3, Clock,
} from 'lucide-react'
import { clsx } from 'clsx'
import { featuresApi } from '@/api/features'
import { recommendationsApi } from '@/api/recommendations'
import { marketApi } from '@/api/market'
import { Card, CardHeader, CardTitle, CardBody } from '@/components/ui/Card'
import { ErrorState } from '@/components/ui/ErrorState'
import { Badge, ActionBadge, MarketBadge, EVENT_LABELS } from '@/components/ui/Badge'
import { fmt, pctColor } from '@/lib/utils'
import { useRealtimeStream, StreamFeature, StreamRecommendation } from '@/hooks/useRealtimeStream'
import { EventDetailModal } from '@/components/modals/EventDetailModal'
import { RecDetailModal } from '@/components/modals/RecDetailModal'
import type { FeatureEvent, Recommendation } from '@/types'

// ── 실시간 피드 아이템 타입 ──────────────────────────────────────────────────
interface LiveSignal {
  key:   string
  code:  string
  label: string
  sub:   string
  type:  'feature' | 'rec'
  ts:    number
}

// ── TOP 3 BUY 카드 ───────────────────────────────────────────────────────────
function Top3BuyCard({
  rec,
  rank,
  onClick,
}: {
  rec: Recommendation
  rank: number
  onClick: () => void
}) {
  const score = rec.success_prob * (rec.risk_reward_ratio ?? 1)
  const rankColors = ['text-yellow-400', 'text-slate-300', 'text-amber-600']
  const rankBg     = ['bg-yellow-500/10 border-yellow-500/30', 'bg-slate-500/10 border-slate-500/30', 'bg-amber-700/10 border-amber-700/30']

  return (
    <button
      onClick={onClick}
      className={clsx(
        'flex flex-col p-5 rounded-2xl border transition-all text-left w-full',
        'bg-[var(--card)] hover:bg-[var(--border)]/40 hover:scale-[1.01] active:scale-[0.99]',
        rank === 0
          ? 'border-yellow-500/40 ring-1 ring-yellow-500/20'
          : 'border-[var(--border)]',
      )}
    >
      {/* 순위 + 이벤트 배지 */}
      <div className="flex items-center justify-between mb-3">
        <span className={clsx('text-xs font-bold px-2 py-0.5 rounded-full border', rankColors[rank], rankBg[rank])}>
          #{rank + 1}
        </span>
        <div className="flex items-center gap-1.5">
          {rec.rationale?.event_type && (
            <Badge eventType={rec.rationale.event_type as string} size="sm" />
          )}
          <ActionBadge action={rec.action} />
        </div>
      </div>

      {/* 종목명 */}
      <div className="mb-3">
        <div className="text-base font-bold text-[var(--fg)] truncate">{rec.name}</div>
        <div className="flex items-center gap-1.5 mt-0.5">
          <span className="text-xs text-[var(--muted)]">{rec.code}</span>
          <MarketBadge market={rec.market} />
        </div>
      </div>

      {/* 성공확률 바 */}
      <div className="mb-3">
        <div className="flex items-center justify-between mb-1">
          <span className="text-[10px] text-[var(--muted)]">성공확률</span>
          <span className="text-sm font-bold text-green-400 tabular">{(rec.success_prob * 100).toFixed(1)}%</span>
        </div>
        <div className="h-1.5 rounded-full bg-[var(--border)] overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-green-500 to-emerald-400 transition-all"
            style={{ width: `${Math.min(rec.success_prob * 100, 100)}%` }}
          />
        </div>
      </div>

      {/* 진입 / 목표 / 손절 */}
      <div className="grid grid-cols-3 gap-2 mb-3">
        <div className="text-center p-2 rounded-lg bg-[var(--bg)]">
          <div className="text-[9px] text-[var(--muted)] mb-0.5">진입가</div>
          <div className="text-xs font-semibold text-[var(--fg)] tabular">{rec.entry_price.toLocaleString()}</div>
        </div>
        <div className="text-center p-2 rounded-lg bg-green-500/5 border border-green-500/15">
          <div className="text-[9px] text-green-400/70 mb-0.5">목표가</div>
          <div className="text-xs font-semibold text-green-400 tabular">{rec.target_price.toLocaleString()}</div>
        </div>
        <div className="text-center p-2 rounded-lg bg-red-500/5 border border-red-500/15">
          <div className="text-[9px] text-red-400/70 mb-0.5">손절가</div>
          <div className="text-xs font-semibold text-red-400 tabular">{rec.stop_loss_price.toLocaleString()}</div>
        </div>
      </div>

      {/* R:R + 복합 점수 */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-[var(--muted)]">
          R:R <span className="text-[var(--fg)] font-semibold">{rec.risk_reward_ratio?.toFixed(1) ?? '—'}</span>
        </span>
        <span className="text-xs text-[var(--muted)]">
          점수 <span className="text-cyan-400 font-semibold">{score.toFixed(2)}</span>
        </span>
      </div>
    </button>
  )
}

// ── 시장 현황 한 줄 바 ───────────────────────────────────────────────────────
function MarketStatusBar({
  indexLive,
  mkSummary,
  totalDetected,
  isRt,
}: {
  indexLive:    ReturnType<typeof useQuery>['data'] | undefined
  mkSummary:    ReturnType<typeof useQuery>['data'] | undefined
  totalDetected: number | undefined
  isRt:         boolean
}) {
  const kospi  = (indexLive as any)?.kospi
  const kosdaq = (indexLive as any)?.kosdaq
  const mk     = mkSummary as any

  function IndexPill({ label, data }: { label: string; data: any }) {
    const chg = data?.change_rate ?? 0
    const up = chg > 0; const dn = chg < 0
    const color = up ? 'text-red-400' : dn ? 'text-blue-400' : 'text-[var(--muted)]'
    return (
      <div className="flex items-center gap-1.5">
        <span className="text-xs font-bold text-[var(--muted)]">{label}</span>
        {data?.price != null ? (
          <>
            <span className={clsx('text-sm font-bold tabular', color)}>
              {data.price.toLocaleString()}
            </span>
            <span className={clsx('text-xs tabular flex items-center gap-0.5', color)}>
              {up ? '+' : ''}{chg.toFixed(2)}%
              {up ? <TrendingUp size={10} /> : dn ? <TrendingDown size={10} /> : <Minus size={10} />}
            </span>
          </>
        ) : (
          <span className="w-24 h-4 skeleton rounded" />
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 px-5 py-3 rounded-xl border border-[var(--border)] bg-[var(--card)] text-sm">
      {isRt && (
        <span className="text-[10px] px-1.5 rounded bg-green-500/15 text-green-400 border border-green-500/20 animate-pulse font-medium">LIVE</span>
      )}
      <IndexPill label="KOSPI"  data={kospi} />
      <div className="w-px h-4 bg-[var(--border)]" />
      <IndexPill label="KOSDAQ" data={kosdaq} />
      <div className="w-px h-4 bg-[var(--border)]" />
      {mk?.advancers != null ? (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-red-400 flex items-center gap-0.5"><ArrowUpRight size={12} />{mk.advancers} 상승</span>
          <span className="text-[var(--muted)]">|</span>
          <span className="text-blue-400 flex items-center gap-0.5"><ArrowDownRight size={12} />{mk.decliners} 하락</span>
          {mk.unchanged != null && <span className="text-[var(--muted)]">보합 {mk.unchanged}</span>}
        </div>
      ) : (
        <span className="w-32 h-4 skeleton rounded" />
      )}
      <div className="w-px h-4 bg-[var(--border)]" />
      <div className="flex items-center gap-1.5 text-xs">
        <Zap size={12} className="text-yellow-400" />
        <span className="text-[var(--muted)]">오늘 탐지</span>
        <span className="font-bold text-yellow-400 tabular">{totalDetected ?? '—'}건</span>
      </div>
    </div>
  )
}

// ── 실시간 이벤트 피드 ───────────────────────────────────────────────────────
function RealtimeFeed({
  liveSignals,
  recentFeatures,
  featuresError,
  refetchFeatures,
  onEventClick,
  isConnected,
}: {
  liveSignals:     LiveSignal[]
  recentFeatures:  FeatureEvent[] | undefined
  featuresError:   boolean
  refetchFeatures: () => void
  onEventClick:    (ev: FeatureEvent) => void
  isConnected:     boolean
}) {
  const nav = useNavigate()

  return (
    <Card className="flex flex-col">
      <CardHeader className="flex items-center justify-between flex-shrink-0">
        <div>
          <div className="flex items-center gap-2">
            <CardTitle>탐지 이벤트 피드</CardTitle>
            <span className={clsx(
              'inline-block w-2 h-2 rounded-full',
              isConnected ? 'bg-green-400 animate-pulse' : 'bg-[var(--muted)]/40'
            )} />
            <span className="text-xs text-[var(--muted)]">
              {isConnected ? '실시간' : '연결 중'}
            </span>
          </div>
          <div className="text-xs text-[var(--muted)] mt-0.5">최근 8시간 · 스코어 높은 순</div>
        </div>
        <button
          onClick={() => nav('/features')}
          className="text-sm text-cyan-400 hover:text-cyan-300 transition-colors"
        >
          전체보기 →
        </button>
      </CardHeader>

      {/* 실시간 신호 플래시 배너 */}
      {liveSignals.length > 0 && (
        <div className="mx-5 mb-3 flex items-center gap-2 overflow-hidden">
          <Zap size={11} className="text-yellow-400 flex-shrink-0" />
          {liveSignals.slice(0, 4).map((s) => (
            <button
              key={s.key}
              onClick={() => nav(`/search?code=${s.code}`)}
              className={clsx(
                'text-[10px] px-2 py-0.5 rounded border whitespace-nowrap transition-colors',
                s.type === 'rec'
                  ? 'border-green-500/40 text-green-400 bg-green-500/10 hover:bg-green-500/20'
                  : 'border-cyan-500/40 text-cyan-400 bg-cyan-500/10 hover:bg-cyan-500/20'
              )}
            >
              {s.label}
              {s.sub && <span className="opacity-70 ml-1">{s.sub}</span>}
            </button>
          ))}
        </div>
      )}

      <CardBody className="pt-0 px-0 pb-0 flex-1 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[var(--border)] text-[var(--muted)] bg-[var(--bg)]/30">
                <th className="text-left pb-2.5 pl-5 pr-3 text-xs font-semibold uppercase tracking-wider">종목</th>
                <th className="text-left pb-2.5 pr-3 text-xs font-semibold uppercase tracking-wider">이벤트</th>
                <th className="text-right pb-2.5 pr-3 text-xs font-semibold uppercase tracking-wider">현재가</th>
                <th className="text-right pb-2.5 pr-3 text-xs font-semibold uppercase tracking-wider">등락률</th>
                <th className="text-right pb-2.5 pr-5 text-xs font-semibold uppercase tracking-wider">스코어</th>
              </tr>
            </thead>
            <tbody>
              {recentFeatures?.slice(0, 8).map((f) => (
                <tr
                  key={f.id}
                  className="border-b border-[var(--border)]/50 hover:bg-[var(--border)]/25 cursor-pointer transition-colors"
                  onClick={() => nav(`/search?code=${f.code}`)}
                >
                  <td className="py-2.5 pl-5 pr-3">
                    <div className="font-semibold text-sm text-[var(--fg)]">{f.name}</div>
                    <div className="flex items-center gap-1 mt-0.5">
                      <span className="text-xs text-[var(--muted)]">{f.code}</span>
                      <MarketBadge market={f.market} />
                    </div>
                  </td>
                  <td className="py-2.5 pr-3">
                    <button
                      onClick={(e) => { e.stopPropagation(); onEventClick(f) }}
                      className="hover:scale-105 transition-transform"
                      title="이벤트 상세"
                    >
                      <Badge eventType={f.event_type} size="sm" />
                    </button>
                  </td>
                  <td className="py-2.5 text-right tabular text-sm text-[var(--fg)] font-medium pr-3">
                    {fmt.price(f.price)}
                  </td>
                  <td className={clsx('py-2.5 text-right tabular text-sm font-semibold pr-3', pctColor(f.change_rate))}>
                    {fmt.pct(f.change_rate)}
                  </td>
                  <td className="py-2.5 text-right tabular text-sm text-yellow-400 font-semibold pr-5">
                    {f.signal_score?.toFixed(2) ?? '—'}
                  </td>
                </tr>
              ))}
              {featuresError && (
                <tr>
                  <td colSpan={5}>
                    <ErrorState message="특징주 데이터 로드 실패" retry={refetchFeatures} />
                  </td>
                </tr>
              )}
              {!featuresError && !recentFeatures?.length && (
                <tr>
                  <td colSpan={5} className="py-10 text-center">
                    <div className="text-sm text-[var(--muted)]">탐지된 특징주가 없습니다</div>
                    <div className="text-xs text-[var(--muted)]/60 mt-1">장 중 실시간으로 업데이트됩니다</div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </CardBody>
    </Card>
  )
}

// ── 30일 성과 통계 패널 ──────────────────────────────────────────────────────
function PerfPanel({
  perf,
  summary,
}: {
  perf:    ReturnType<typeof useQuery>['data']
  summary: ReturnType<typeof useQuery>['data']
}) {
  const p = perf as any
  const s = summary as any

  return (
    <div className="space-y-4">
      {/* 30일 성과 통계 */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <BarChart3 size={14} className="text-cyan-400" />
            <CardTitle>30일 성과 통계</CardTitle>
          </div>
        </CardHeader>
        <CardBody className="pt-3 space-y-3">
          {p ? (
            <>
              <div className="grid grid-cols-2 gap-2">
                <div className="p-3 rounded-xl border border-[var(--border)] bg-[var(--bg)] text-center">
                  <div className="text-[10px] text-[var(--muted)] mb-1">성공률</div>
                  <div className={clsx(
                    'text-xl font-bold tabular',
                    p.success_rate >= 0.55 ? 'text-green-400' : 'text-red-400'
                  )}>
                    {(p.success_rate * 100).toFixed(1)}%
                  </div>
                </div>
                <div className="p-3 rounded-xl border border-[var(--border)] bg-[var(--bg)] text-center">
                  <div className="text-[10px] text-[var(--muted)] mb-1">평균 수익률</div>
                  <div className={clsx(
                    'text-xl font-bold tabular',
                    (p.avg_return ?? 0) >= 0 ? 'text-red-400' : 'text-blue-400'
                  )}>
                    {p.avg_return != null ? `${p.avg_return >= 0 ? '+' : ''}${p.avg_return.toFixed(1)}%` : '—'}
                  </div>
                </div>
              </div>
              <div className="flex items-center justify-between px-1 text-xs text-[var(--muted)]">
                <span>매수 신호</span>
                <span className="tabular font-medium text-[var(--fg)]">{p.buy_count ?? '—'}건</span>
              </div>
              <div className="flex items-center justify-between px-1 text-xs text-[var(--muted)]">
                <span>성공 / 전체</span>
                <span className="tabular font-medium text-[var(--fg)]">
                  {p.success_count ?? '—'} / {p.total_count ?? '—'}
                </span>
              </div>
              {p.avg_pred_prob != null && (
                <div className="flex items-center justify-between px-1 text-xs text-[var(--muted)]">
                  <span>평균 예측 확률</span>
                  <span className="tabular font-medium text-cyan-400">
                    {(p.avg_pred_prob * 100).toFixed(1)}%
                  </span>
                </div>
              )}
            </>
          ) : (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-8 skeleton rounded-lg" />
              ))}
            </div>
          )}
        </CardBody>
      </Card>

      {/* 오늘 이벤트 분포 */}
      {s?.by_type && Object.keys(s.by_type).length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Target size={14} className="text-purple-400" />
              <CardTitle>오늘 이벤트 분포</CardTitle>
            </div>
          </CardHeader>
          <CardBody className="pt-3">
            <div className="flex flex-wrap gap-2">
              {Object.entries(s.by_type as Record<string, number>)
                .sort(([, a], [, b]) => b - a)
                .map(([type, count]) => (
                  <div
                    key={type}
                    className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-[var(--border)] cursor-pointer hover:bg-[var(--border)]/30 transition-colors"
                    onClick={() => window.location.assign(`/features?event_type=${type}`)}
                  >
                    <Badge eventType={type} size="sm" />
                    <span className="text-sm font-bold text-[var(--fg)] tabular">{count}</span>
                  </div>
                ))
              }
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  )
}

// ── 상승/하락 Movers ─────────────────────────────────────────────────────────
function MoversRow({ movers }: { movers: ReturnType<typeof useQuery>['data'] }) {
  const nav = useNavigate()
  const mv = movers as any

  if (!mv?.gainers?.length && !mv?.losers?.length) return null

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {mv?.gainers?.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <ArrowUpRight size={14} className="text-red-400" />
              <CardTitle>상위 상승 종목</CardTitle>
            </div>
          </CardHeader>
          <CardBody className="pt-3 space-y-1">
            {mv.gainers.slice(0, 6).map((s: any) => (
              <div
                key={s.code}
                className="flex items-center justify-between cursor-pointer hover:bg-[var(--border)]/25 rounded-lg px-2 py-2 transition-colors"
                onClick={() => nav(`/search?code=${s.code}`)}
              >
                <div className="text-[0.8125rem] font-medium text-[var(--fg)] truncate flex-1">{s.name}</div>
                <div className="text-[0.8125rem] font-bold text-red-400 tabular ml-3">+{s.change_rate.toFixed(2)}%</div>
              </div>
            ))}
          </CardBody>
        </Card>
      )}

      {mv?.losers?.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <ArrowDownRight size={14} className="text-blue-400" />
              <CardTitle>상위 하락 종목</CardTitle>
            </div>
          </CardHeader>
          <CardBody className="pt-3 space-y-1">
            {mv.losers.slice(0, 6).map((s: any) => (
              <div
                key={s.code}
                className="flex items-center justify-between cursor-pointer hover:bg-[var(--border)]/25 rounded-lg px-2 py-2 transition-colors"
                onClick={() => nav(`/search?code=${s.code}`)}
              >
                <div className="text-[0.8125rem] font-medium text-[var(--fg)] truncate flex-1">{s.name}</div>
                <div className="text-[0.8125rem] font-bold text-blue-400 tabular ml-3">{s.change_rate.toFixed(2)}%</div>
              </div>
            ))}
          </CardBody>
        </Card>
      )}
    </div>
  )
}

// ── 메인 Dashboard ────────────────────────────────────────────────────────────
export function Dashboard() {
  const nav = useNavigate()
  const [liveSignals,  setLiveSignals]  = useState<LiveSignal[]>([])
  const [selectedEvent, setSelectedEvent] = useState<FeatureEvent | null>(null)
  const [selectedRec,   setSelectedRec]   = useState<Recommendation | null>(null)

  // 실시간 스트림 핸들러
  const handleFeature = useCallback((ev: StreamFeature) => {
    setLiveSignals((prev) => [{
      key:   `f-${ev.code}-${Date.now()}`,
      code:  ev.code,
      label: `${ev.code} ${ev.event_type}`,
      sub:   ev.price ? `${ev.price.toLocaleString()}원` : '',
      type:  'feature' as const,
      ts:    Date.now(),
    }, ...prev].slice(0, 8))
  }, [])

  const handleRec = useCallback((rec: StreamRecommendation) => {
    if (rec.action !== 'BUY') return
    setLiveSignals((prev) => [{
      key:   `r-${rec.code}-${Date.now()}`,
      code:  rec.code,
      label: `${rec.code} 매수신호`,
      sub:   `${(rec.success_prob * 100).toFixed(1)}%`,
      type:  'rec' as const,
      ts:    Date.now(),
    }, ...prev].slice(0, 8))
  }, [])

  const { isConnected } = useRealtimeStream({
    onFeature:         handleFeature,
    onRecommendation:  handleRec,
    invalidateQueries: false,
  })

  // 데이터 쿼리 (기존과 동일)
  const { data: summary } = useQuery({
    queryKey:        ['today-summary'],
    queryFn:         featuresApi.todaySummary,
    refetchInterval: 30_000,
  })

  const { data: recentFeatures, isError: featuresError, refetch: refetchFeatures } = useQuery({
    queryKey:        ['features-recent'],
    queryFn:         () => featuresApi.list({ limit: 12, hours: 8, dedupe: true }),
    refetchInterval: 30_000,
  })

  const { data: topRecs } = useQuery({
    queryKey:        ['top-recs'],
    queryFn:         () => recommendationsApi.list({ min_prob: 0.20, hours: 24, limit: 10 }),
    refetchInterval: 60_000,
  })

  const { data: perf } = useQuery({
    queryKey:        ['performance-30d'],
    queryFn:         () => recommendationsApi.getPerformance(30),
    refetchInterval: 300_000,
  })

  const { data: mkSummary } = useQuery({
    queryKey:        ['market-summary'],
    queryFn:         marketApi.getSummary,
    refetchInterval: 60_000,
  })

  const { data: indexLive } = useQuery({
    queryKey:        ['index-live'],
    queryFn:         marketApi.getIndexLive,
    refetchInterval: 30_000,
  })

  const { data: movers } = useQuery({
    queryKey:        ['market-movers'],
    queryFn:         marketApi.getMovers,
    refetchInterval: 60_000,
  })

  const isRt = (indexLive as any)?.source === 'realtime'

  // TOP 3 BUY 계산: success_prob × risk_reward_ratio 점수 기준 정렬
  const top3Buy = (topRecs ?? [])
    .filter((r) => r.action === 'BUY')
    .sort((a, b) => (b.success_prob * (b.risk_reward_ratio ?? 1)) - (a.success_prob * (a.risk_reward_ratio ?? 1)))
    .slice(0, 3)

  return (
    <div className="p-6 space-y-5">

      {/* ── Hero: TOP 3 BUY 신호 ────────────────────────────────────────── */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-base font-bold text-[var(--fg)] flex items-center gap-2">
              <ShieldAlert size={16} className="text-green-400" />
              오늘의 TOP BUY 신호
            </h2>
            <p className="text-xs text-[var(--muted)] mt-0.5">성공확률 × R:R 점수 기준 상위 3건</p>
          </div>
          <button
            onClick={() => nav('/recommendations')}
            className="text-sm text-cyan-400 hover:text-cyan-300 transition-colors"
          >
            전체보기 →
          </button>
        </div>

        {top3Buy.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {top3Buy.map((rec, i) => (
              <Top3BuyCard
                key={rec.id}
                rec={rec}
                rank={i}
                onClick={() => setSelectedRec(rec)}
              />
            ))}
          </div>
        ) : (
          <div className="flex items-center justify-center p-10 rounded-2xl border border-[var(--border)] border-dashed bg-[var(--card)]/50">
            <div className="text-center">
              <Clock size={28} className="text-[var(--muted)]/40 mx-auto mb-2" />
              <div className="text-sm text-[var(--muted)]">조건을 충족하는 BUY 신호가 없습니다</div>
              <div className="text-xs text-[var(--muted)]/60 mt-1">최근 24시간 탐지 결과를 기다리는 중</div>
            </div>
          </div>
        )}
      </section>

      {/* ── 시장 현황 바 ─────────────────────────────────────────────────── */}
      <MarketStatusBar
        indexLive={indexLive}
        mkSummary={mkSummary}
        totalDetected={summary?.total}
        isRt={isRt}
      />

      {/* ── 2열 레이아웃: 피드 + 성과 패널 ─────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* 왼쪽: 실시간 탐지 이벤트 피드 */}
        <div className="lg:col-span-2">
          <RealtimeFeed
            liveSignals={liveSignals}
            recentFeatures={recentFeatures}
            featuresError={featuresError}
            refetchFeatures={refetchFeatures}
            onEventClick={setSelectedEvent}
            isConnected={isConnected}
          />
        </div>

        {/* 오른쪽: 성과 통계 + 이벤트 분포 */}
        <div className="lg:col-span-1">
          <PerfPanel perf={perf} summary={summary} />
        </div>
      </div>

      {/* ── 하단: 상승/하락 Movers ────────────────────────────────────── */}
      <MoversRow movers={movers} />

      {/* ── 이벤트 상세 모달 ─────────────────────────────────────────── */}
      {selectedEvent && (
        <EventDetailModal
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
          onGoDetail={() => { setSelectedEvent(null); nav(`/search?code=${selectedEvent.code}`) }}
        />
      )}

      {/* ── TOP 3 추천 상세 모달 ─────────────────────────────────────── */}
      {selectedRec && (
        <RecDetailModal
          rec={selectedRec}
          onClose={() => setSelectedRec(null)}
          onGoDetail={() => { setSelectedRec(null); nav(`/search?code=${selectedRec.code}`) }}
        />
      )}
    </div>
  )
}
