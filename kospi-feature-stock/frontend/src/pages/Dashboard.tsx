import { useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, Link } from 'react-router-dom'
import {
  TrendingUp, TrendingDown, Minus, ArrowUpRight, ArrowDownRight,
  Zap, BarChart3, Target, FileText, Users, Clock,
} from 'lucide-react'
import { clsx } from 'clsx'
import { featuresApi } from '@/api/features'
import { recommendationsApi } from '@/api/recommendations'
import { marketApi } from '@/api/market'
import { disclosuresApi } from '@/api/disclosures'
import { Card, CardHeader, CardTitle, CardBody } from '@/components/ui/Card'
import { ErrorState } from '@/components/ui/ErrorState'
import { Badge, MarketBadge, EVENT_LABELS } from '@/components/ui/Badge'
import { fmt, pctColor, probToScore } from '@/lib/utils'
import { useRealtimeStream, StreamFeature, StreamRecommendation } from '@/hooks/useRealtimeStream'
import { EventDetailModal } from '@/components/modals/EventDetailModal'
import type { FeatureEvent, Recommendation, TodaySummary, PerformanceStats } from '@/types'
import type { IndexLive, MarketSummary, MarketMovers, MarketMover } from '@/api/market'

// ── 이벤트 타입 아이콘 매핑 ─────────────────────────────────────────────────
const EVENT_ICONS: Record<string, React.ReactNode> = {
  VOLUME_SURGE:          <TrendingUp size={14} className="text-blue-400" />,
  AMOUNT_SURGE:          <TrendingUp size={14} className="text-purple-400" />,
  BREAKOUT_52W:          <ArrowUpRight size={14} className="text-green-400" />,
  BREAKOUT_26W:          <ArrowUpRight size={14} className="text-green-400" />,
  BREAKOUT_13W:          <ArrowUpRight size={14} className="text-green-400" />,
  BREAKOUT_20D:          <ArrowUpRight size={14} className="text-green-400" />,
  VI_TRIGGERED:          <Zap size={14} className="text-yellow-400" />,
  LONG_WHITE_CANDLE:     <TrendingUp size={14} className="text-orange-400" />,
  SUPPLY_ANOMALY:        <Users size={14} className="text-cyan-400" />,
  POST_DISCLOSURE_SURGE: <FileText size={14} className="text-pink-400" />,
}

function getEventIcon(eventType: string): React.ReactNode {
  return EVENT_ICONS[eventType] ?? <Zap size={14} className="text-[var(--muted)]" />
}

function isRecent(isoDate?: string | null): boolean {
  if (!isoDate) return false
  return new Date().getTime() - new Date(isoDate).getTime() < 5 * 60 * 1000
}

// ── ActionBar ────────────────────────────────────────────────────────────────
function ActionBar({
  buyCount,
  indexLive,
  mkSummary,
  mlMode,
  isRt,
}: {
  buyCount:   number | undefined
  indexLive:  IndexLive | undefined
  mkSummary:  MarketSummary | undefined
  mlMode:     string | undefined
  isRt:       boolean
}) {
  const kospi  = indexLive?.kospi
  const kosdaq = indexLive?.kosdaq

  function IndexPill({ label, data }: { label: string; data: IndexLive['kospi'] | undefined }) {
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
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 px-5 py-3 rounded-xl border border-[var(--border)] bg-[var(--card)]">
      {/* BUY 신호 수 */}
      <Link
        to="/recommendations"
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-green-500/15 border border-green-500/30 text-green-400 hover:bg-green-500/25 transition-colors"
      >
        <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
        <span className="text-sm font-bold tabular">BUY {buyCount ?? '—'}개</span>
      </Link>

      {/* LIVE 배지 */}
      {isRt && (
        <span className="text-[10px] px-1.5 rounded bg-green-500/15 text-green-400 border border-green-500/20 animate-pulse font-medium">LIVE</span>
      )}

      {/* 지수 */}
      <IndexPill label="KOSPI"  data={kospi} />
      <div className="w-px h-4 bg-[var(--border)]" />
      <IndexPill label="KOSDAQ" data={kosdaq} />

      {/* 상승/하락 */}
      {mkSummary?.advancers != null && (
        <>
          <div className="w-px h-4 bg-[var(--border)]" />
          <div className="flex items-center gap-2 text-xs">
            <span className="text-red-400 flex items-center gap-0.5"><ArrowUpRight size={12} />{mkSummary.advancers} 상승</span>
            <span className="text-[var(--muted)]">|</span>
            <span className="text-blue-400 flex items-center gap-0.5"><ArrowDownRight size={12} />{mkSummary.decliners} 하락</span>
          </div>
        </>
      )}

      {/* ML 모드 */}
      {mlMode && (
        <>
          <div className="w-px h-4 bg-[var(--border)]" />
          <span className={clsx(
            'text-xs px-1.5 py-0.5 rounded border font-medium',
            mlMode === 'ml'
              ? 'border-purple-500/30 text-purple-400 bg-purple-500/10'
              : 'border-amber-500/30 text-amber-400 bg-amber-500/10'
          )}>
            {mlMode === 'ml' ? 'ML 활성' : '규칙 기반'}
          </span>
        </>
      )}
    </div>
  )
}

// ── 실시간 피드 카드 ─────────────────────────────────────────────────────────
function FeedCard({
  event,
  onEventClick,
}: {
  event: FeatureEvent
  onEventClick: (ev: FeatureEvent) => void
}) {
  const nav = useNavigate()
  const recent = isRecent(event.detected_at)
  const score = event.signal_score

  return (
    <div className={clsx(
      'flex items-start gap-3 p-3 rounded-xl border transition-colors hover:bg-[var(--border)]/20 cursor-pointer',
      recent
        ? 'border-green-500/40 bg-green-500/5'
        : 'border-[var(--border)] bg-[var(--card)]',
    )}
      onClick={() => nav(`/search?code=${event.code}`)}
    >
      {/* 이벤트 아이콘 */}
      <div className={clsx(
        'w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5',
        recent ? 'bg-green-500/15' : 'bg-[var(--bg)]'
      )}>
        {getEventIcon(event.event_type)}
      </div>

      {/* 메인 콘텐츠 */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="font-semibold text-sm text-[var(--fg)] truncate">{event.name}</span>
          <MarketBadge market={event.market} />
          <button
            onClick={(e) => { e.stopPropagation(); onEventClick(event) }}
            className="hover:scale-105 transition-transform"
            title="이벤트 상세"
          >
            <Badge eventType={event.event_type} size="sm" />
          </button>
          {recent && (
            <span className="text-[10px] px-1 rounded bg-green-500/20 text-green-400 border border-green-500/30 animate-pulse font-medium">실시간</span>
          )}
        </div>

        <div className="flex items-center gap-2 mt-1">
          <span className="text-xs text-[var(--muted)]">{event.code}</span>
          <span className="text-xs text-[var(--fg)] font-medium tabular">{fmt.price(event.price)}</span>
          <span className={clsx('text-xs font-semibold tabular', pctColor(event.change_rate))}>
            {fmt.pct(event.change_rate)}
          </span>
        </div>

        {/* 신호 점수 진행 바 */}
        {score != null && (
          <div className="flex items-center gap-2 mt-1.5">
            <div className="flex-1 h-1.5 bg-[var(--border)] rounded-full overflow-hidden">
              <div
                className={clsx('h-full rounded-full', score >= 0.75 ? 'bg-green-400' : score >= 0.55 ? 'bg-amber-400' : 'bg-red-400')}
                style={{ width: `${Math.round(score * 100)}%` }}
              />
            </div>
            <span className="text-xs tabular text-[var(--fg)] font-semibold">{score.toFixed(2)}</span>
          </div>
        )}
      </div>

      {/* 우측: 시간 + 빠른 분석 */}
      <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
        <span className={clsx(
          'text-xs tabular',
          recent ? 'text-green-400 font-semibold' : 'text-[var(--muted)]'
        )}>
          {fmt.smartTime(event.detected_at)}
        </span>
        <button
          onClick={(e) => { e.stopPropagation(); nav(`/search?code=${event.code}`) }}
          className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 hover:bg-cyan-500/20 transition-colors whitespace-nowrap"
        >
          빠른 분석
        </button>
      </div>
    </div>
  )
}

// ── 실시간 이벤트 피드 섹션 ──────────────────────────────────────────────────
function RealtimeFeed({
  liveSignals,
  recentFeatures,
  featuresError,
  refetchFeatures,
  onEventClick,
  isConnected,
}: {
  liveSignals:     Array<{ key: string; code: string; label: string; sub: string; type: 'feature' | 'rec'; ts: number }>
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
          <div className="text-xs text-[var(--muted)] mt-0.5">최근 8시간 · 스코어 높은 순 · 최대 50건</div>
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

      <CardBody className="pt-0 flex-1 overflow-hidden">
        {featuresError && (
          <ErrorState message="특징주 데이터 로드 실패" retry={refetchFeatures} />
        )}
        {!featuresError && !recentFeatures?.length && !recentFeatures && (
          <div className="py-8 text-center">
            <div className="text-sm text-[var(--muted)]">탐지된 특징주가 없습니다</div>
            <div className="text-xs text-[var(--muted)]/60 mt-1">장 중 실시간으로 업데이트됩니다</div>
          </div>
        )}
        <div className="space-y-2">
          {recentFeatures?.slice(0, 50).map((f) => (
            <FeedCard key={f.id} event={f} onEventClick={onEventClick} />
          ))}
        </div>
      </CardBody>
    </Card>
  )
}

// ── 오늘 요약 패널 ────────────────────────────────────────────────────────────
function TodaySummaryPanel({
  summary,
  perf,
  buyCount,
  disclosureCount,
}: {
  summary:         TodaySummary | undefined
  perf:            PerformanceStats | undefined
  buyCount:        number | undefined
  disclosureCount: number | undefined
}) {
  const p = perf
  const s = summary

  return (
    <div className="space-y-4">
      {/* 오늘 요약 수치 */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Target size={14} className="text-cyan-400" />
            <CardTitle>오늘 요약</CardTitle>
          </div>
        </CardHeader>
        <CardBody className="pt-3 space-y-2">
          <div className="flex items-center justify-between py-2 border-b border-[var(--border)]/50">
            <span className="text-xs text-[var(--muted)]">탐지 이벤트</span>
            <span className="text-sm font-bold text-yellow-400 tabular">{s?.total ?? '—'}건</span>
          </div>
          <div className="flex items-center justify-between py-2 border-b border-[var(--border)]/50">
            <span className="text-xs text-[var(--muted)]">BUY 신호</span>
            <Link to="/recommendations" className="text-sm font-bold text-green-400 tabular hover:text-green-300 transition-colors">
              {buyCount ?? '—'}건
            </Link>
          </div>
          <div className="flex items-center justify-between py-2 border-b border-[var(--border)]/50">
            <span className="text-xs text-[var(--muted)]">공시</span>
            <Link to="/intel" className="text-sm font-bold text-blue-400 tabular hover:text-blue-300 transition-colors">
              {disclosureCount ?? '—'}건
            </Link>
          </div>
          <div className="flex items-center justify-between py-2">
            <span className="text-xs text-[var(--muted)]">30일 성공률</span>
            <span className={clsx(
              'text-sm font-bold tabular',
              p?.success_rate != null ? (p.success_rate >= 0.55 ? 'text-green-400' : 'text-red-400') : 'text-[var(--muted)]'
            )}>
              {p?.success_rate != null ? `${(p.success_rate * 100).toFixed(1)}%` : '—'}
            </span>
          </div>
        </CardBody>
      </Card>

      {/* 이벤트 타입별 바 차트 */}
      {s?.by_type && Object.keys(s.by_type).length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <BarChart3 size={14} className="text-purple-400" />
              <CardTitle>이벤트 분포</CardTitle>
            </div>
          </CardHeader>
          <CardBody className="pt-3 space-y-2">
            {(() => {
              const entries = Object.entries(s.by_type as Record<string, number>).sort(([, a], [, b]) => b - a)
              const maxVal = Math.max(1, ...entries.map(([, v]) => v))
              return entries.map(([type, count]) => (
                <div key={type} className="space-y-0.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-[var(--muted)] truncate flex-1">{EVENT_LABELS[type] ?? type}</span>
                    <span className="text-[var(--fg)] font-semibold tabular ml-2">{count}</span>
                  </div>
                  <div className="h-1.5 bg-[var(--border)] rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full bg-cyan-500/60"
                      style={{ width: `${(count / maxVal) * 100}%` }}
                    />
                  </div>
                </div>
              ))
            })()}
          </CardBody>
        </Card>
      )}

      {/* 30일 성과 통계 */}
      {p && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <BarChart3 size={14} className="text-cyan-400" />
              <CardTitle>30일 성과 통계</CardTitle>
            </div>
          </CardHeader>
          <CardBody className="pt-3 space-y-3">
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
          </CardBody>
        </Card>
      )}
    </div>
  )
}

// ── 상승/하락 Movers ─────────────────────────────────────────────────────────
function MoversRow({ movers }: { movers: MarketMovers | undefined }) {
  const nav = useNavigate()

  if (!movers?.gainers?.length && !movers?.losers?.length) return null

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {movers?.gainers?.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <ArrowUpRight size={14} className="text-red-400" />
              <CardTitle>상위 상승 종목</CardTitle>
            </div>
          </CardHeader>
          <CardBody className="pt-3 space-y-1">
            {movers.gainers.slice(0, 6).map((s: MarketMover) => (
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

      {movers?.losers?.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <ArrowDownRight size={14} className="text-blue-400" />
              <CardTitle>상위 하락 종목</CardTitle>
            </div>
          </CardHeader>
          <CardBody className="pt-3 space-y-1">
            {movers.losers.slice(0, 6).map((s: MarketMover) => (
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
  const [liveSignals, setLiveSignals] = useState<Array<{
    key: string; code: string; label: string; sub: string; type: 'feature' | 'rec'; ts: number
  }>>([])
  const [selectedEvent, setSelectedEvent] = useState<FeatureEvent | null>(null)
  const nav = useNavigate()

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
      sub:   `${probToScore(rec.success_prob)}점 (${(rec.success_prob * 100).toFixed(1)}%)`,
      type:  'rec' as const,
      ts:    Date.now(),
    }, ...prev].slice(0, 8))
  }, [])

  const { isConnected } = useRealtimeStream({
    onFeature:         handleFeature,
    onRecommendation:  handleRec,
    invalidateQueries: false,
  })

  // 데이터 쿼리
  const { data: summary } = useQuery({
    queryKey:        ['today-summary'],
    queryFn:         featuresApi.todaySummary,
    refetchInterval: 30_000,
  })

  const { data: recentFeatures, isError: featuresError, refetch: refetchFeatures } = useQuery({
    queryKey:        ['features-recent'],
    queryFn:         () => featuresApi.list({ limit: 50, hours: 8, dedupe: true }),
    refetchInterval: 30_000,
  })

  const { data: topRecs } = useQuery({
    queryKey:        ['top-recs'],
    queryFn:         () => recommendationsApi.list({ action: 'BUY', min_prob: 0.30, hours: 72, limit: 100, dedupe: true }),
    refetchInterval: 60_000,
  })

  const { data: perf } = useQuery({
    queryKey:        ['perf-30'],
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

  const { data: discStats } = useQuery({
    queryKey:  ['disclosure-stats-24h'],
    queryFn:   () => disclosuresApi.getStats(24),
    staleTime: 300_000,
  })

  const isRt = (indexLive as any)?.source === 'realtime'
  const buyCount = topRecs?.length

  // ML 모드 추론 (최근 추천 중 첫 번째 신호 기준)
  const mlMode = topRecs?.find((r) => r.rationale?.model_mode)?.rationale?.model_mode

  return (
    <div className="p-6 space-y-5">

      {/* ── 액션 바 ─────────────────────────────────────────────────────── */}
      <ActionBar
        buyCount={buyCount}
        indexLive={indexLive}
        mkSummary={mkSummary}
        mlMode={mlMode}
        isRt={isRt}
      />

      {/* ── 2열 레이아웃: 피드(75%) + 요약(25%) ─────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">

        {/* 왼쪽: 실시간 탐지 이벤트 피드 */}
        <div className="lg:col-span-3">
          {recentFeatures?.length === 0 && !featuresError ? (
            <Card>
              <CardBody>
                <div className="py-16 text-center">
                  <Clock size={28} className="text-[var(--muted)]/40 mx-auto mb-2" />
                  <div className="text-sm text-[var(--muted)]">탐지된 특징주가 없습니다</div>
                  <div className="text-xs text-[var(--muted)]/60 mt-1">장 중 실시간으로 업데이트됩니다</div>
                </div>
              </CardBody>
            </Card>
          ) : (
            <RealtimeFeed
              liveSignals={liveSignals}
              recentFeatures={recentFeatures}
              featuresError={featuresError}
              refetchFeatures={refetchFeatures}
              onEventClick={setSelectedEvent}
              isConnected={isConnected}
            />
          )}
        </div>

        {/* 오른쪽: 오늘 요약 */}
        <div className="lg:col-span-1">
          <TodaySummaryPanel
            summary={summary}
            perf={perf}
            buyCount={buyCount}
            disclosureCount={discStats?.total}
          />
        </div>
      </div>

      {/* ── 하단: 상승/하락 Movers ──────────────────────────────────── */}
      <MoversRow movers={movers} />

      {/* ── 이벤트 상세 모달 ─────────────────────────────────────── */}
      {selectedEvent && (
        <EventDetailModal
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
          onGoDetail={() => { setSelectedEvent(null); nav(`/search?code=${selectedEvent.code}`) }}
        />
      )}
    </div>
  )
}
