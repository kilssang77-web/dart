import { useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { TrendingUp, TrendingDown, Minus, ArrowUpRight, ArrowDownRight, Zap, AlertTriangle } from 'lucide-react'
import { clsx } from 'clsx'
import { featuresApi } from '@/api/features'
import { recommendationsApi } from '@/api/recommendations'
import { marketApi } from '@/api/market'
import { StatCard, Card, CardHeader, CardTitle, CardBody } from '@/components/ui/Card'
import { Badge, ActionBadge, MarketBadge, EVENT_LABELS } from '@/components/ui/Badge'
import { fmt, pctColor } from '@/lib/utils'
import { useRealtimeStream, StreamFeature, StreamRecommendation } from '@/hooks/useRealtimeStream'
import { EventDetailModal } from '@/components/modals/EventDetailModal'
import { RecDetailModal } from '@/components/modals/RecDetailModal'
import type { FeatureEvent, Recommendation } from '@/types'

interface LiveSignal {
  key:    string
  code:   string
  label:  string
  sub:    string
  type:   'feature' | 'rec'
}

export function Dashboard() {
  const nav = useNavigate()
  const [liveSignals, setLiveSignals] = useState<LiveSignal[]>([])
  const [selectedEvent, setSelectedEvent] = useState<FeatureEvent | null>(null)
  const [selectedRec,   setSelectedRec]   = useState<Recommendation | null>(null)

  const handleFeature = useCallback((ev: StreamFeature) => {
    setLiveSignals((prev) => [{
      key:   `f-${ev.code}-${Date.now()}`,
      code:  ev.code,
      label: `${ev.code} ${ev.event_type}`,
      sub:   ev.price ? `${ev.price.toLocaleString()}원` : '',
      type:  'feature' as const,
    }, ...prev].slice(0, 5))
  }, [])

  const handleRec = useCallback((rec: StreamRecommendation) => {
    if (rec.action !== 'BUY') return
    setLiveSignals((prev) => [{
      key:   `r-${rec.code}-${Date.now()}`,
      code:  rec.code,
      label: `${rec.code} 매수신호`,
      sub:   `확률 ${(rec.success_prob * 100).toFixed(1)}%`,
      type:  'rec' as const,
    }, ...prev].slice(0, 5))
  }, [])

  const { isConnected } = useRealtimeStream({
    onFeature:         handleFeature,
    onRecommendation:  handleRec,
    invalidateQueries: false,
  })

  const { data: summary, isError: summaryError } = useQuery({
    queryKey:        ['today-summary'],
    queryFn:         featuresApi.todaySummary,
    refetchInterval: 30_000,
  })

  const { data: recentFeatures, isError: featuresError } = useQuery({
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

  const isRt = indexLive?.source === 'realtime'

  return (
    <div className="p-6 space-y-5">

      {/* 실시간 연결 상태 + 최근 신호 플래시 배너 */}
      <div className="flex items-center justify-between min-h-[22px]">
        <div className="flex items-center gap-2">
          <span className={clsx(
            'inline-block w-2 h-2 rounded-full flex-shrink-0',
            isConnected ? 'bg-green-400 animate-pulse' : 'bg-[var(--muted)]/40'
          )} />
          <span className="text-sm text-[var(--muted)]">
            {isConnected ? '실시간 연결됨' : '연결 중...'}
          </span>
        </div>
        {liveSignals.length > 0 && (
          <div className="flex items-center gap-1.5 overflow-hidden max-w-[65vw]">
            <Zap size={12} className="text-yellow-400 flex-shrink-0" />
            {liveSignals.slice(0, 3).map((s) => (
              <button
                key={s.key}
                onClick={() => nav(`/search?code=${s.code}`)}
                className={clsx(
                  'text-xs px-2.5 py-1 rounded border whitespace-nowrap transition-colors',
                  s.type === 'rec'
                    ? 'border-green-500/40 text-green-400 bg-green-500/10 hover:bg-green-500/20'
                    : 'border-cyan-500/40 text-cyan-400 bg-cyan-500/10 hover:bg-cyan-500/20'
                )}
              >
                {s.label}{s.sub && <span className="opacity-70 ml-1">{s.sub}</span>}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* ── 시장 지수 바 ─────────────────────────────────────────────────── */}
      {(summaryError || featuresError) && (
        <div className="flex items-center gap-2 px-3 py-2 bg-yellow-500/10 border border-yellow-500/30 rounded-lg text-xs text-yellow-400">
          <AlertTriangle size={12} className="shrink-0" />
          데이터 로드 오류 — 잠시 후 자동 재시도됩니다
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { key: 'kospi',  label: 'KOSPI',  q: indexLive?.kospi  },
          { key: 'kosdaq', label: 'KOSDAQ', q: indexLive?.kosdaq },
        ].map(({ key, label, q }) => {
          const change = q?.change_rate ?? 0
          const up = change > 0; const dn = change < 0
          return (
            <div key={key} className="bg-[var(--card)] border border-[var(--border)] rounded-xl px-4 py-3">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-bold text-[var(--muted)] uppercase tracking-wider">{label}</span>
                {isRt
                  ? <span className="text-[10px] px-1.5 rounded bg-green-500/15 text-green-400 border border-green-500/20 animate-pulse">LIVE</span>
                  : <span className="text-[10px] px-1.5 rounded bg-yellow-500/10 text-yellow-400 border border-yellow-500/20">전일</span>
                }
              </div>
              {q?.price != null ? (
                <>
                  <div className={clsx('text-2xl font-bold tabular leading-tight', up ? 'text-red-400' : dn ? 'text-blue-400' : 'text-[var(--fg)]')}>
                    {q.price.toLocaleString()}
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    {q.change != null && (
                      <span className={clsx('text-sm tabular', up ? 'text-red-400' : dn ? 'text-blue-400' : 'text-[var(--fg)]')}>
                        {up ? '+' : ''}{q.change.toFixed(2)}
                      </span>
                    )}
                    <span className={clsx('text-sm font-bold tabular flex items-center gap-0.5', up ? 'text-red-400' : dn ? 'text-blue-400' : 'text-[var(--fg)]')}>
                      {up ? '+' : ''}{change.toFixed(2)}%
                      {up ? <TrendingUp size={12} className="inline ml-0.5" /> : dn ? <TrendingDown size={12} className="inline ml-0.5" /> : <Minus size={12} className="inline ml-0.5" />}
                    </span>
                  </div>
                </>
              ) : (
                <div className="h-8 skeleton mt-1 rounded-md" />
              )}
            </div>
          )
        })}

        <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl px-4 py-3">
          <div className="text-xs font-bold text-[var(--muted)] uppercase tracking-wider mb-1">상승 종목</div>
          {mkSummary?.advancers != null ? (
            <>
              <div className="text-xl font-bold text-red-400 tabular flex items-center gap-1">
                <ArrowUpRight size={16} />{mkSummary.advancers}
              </div>
              <div className="text-sm text-[var(--muted)] mt-0.5">보합 {mkSummary.unchanged ?? '—'}</div>
            </>
          ) : (
            <div className="h-8 skeleton mt-1 rounded-md" />
          )}
        </div>

        <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl px-4 py-3">
          <div className="text-xs font-bold text-[var(--muted)] uppercase tracking-wider mb-1">하락 종목</div>
          {mkSummary?.decliners != null ? (
            <>
              <div className="text-xl font-bold text-blue-400 tabular flex items-center gap-1">
                <ArrowDownRight size={16} />{mkSummary.decliners}
              </div>
              <div className="text-sm text-[var(--muted)] mt-0.5">
                {(indexLive?.data_date ?? mkSummary?.data_date) ? `${(indexLive?.data_date ?? mkSummary?.data_date)} 기준` : '전일 기준'}
              </div>
            </>
          ) : (
            <div className="h-8 skeleton mt-1 rounded-md" />
          )}
        </div>
      </div>

      {/* ── 통계 카드 4개 ──────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="오늘 탐지" value={summary?.total ?? '—'} sub={`평균 스코어 ${summary?.avg_score?.toFixed(2) ?? '—'}`} valueColor="text-cyan-400" onClick={() => nav('/features')} />
        <StatCard label="고점수 신호" value={summary?.high_score ?? '—'} sub="스코어 0.7 이상" valueColor="text-yellow-400" />
        <StatCard label="추천 종목" value={topRecs?.length ?? '—'} sub="확률 상위 · 24시간" valueColor="text-green-400" onClick={() => nav('/recommendations')} />
        <StatCard
          label="30일 성공률"
          value={perf ? `${(perf.success_rate * 100).toFixed(1)}%` : '—'}
          sub={`${perf?.success_count ?? '—'}/${perf?.buy_count ?? '—'} 성공`}
          valueColor={perf ? (perf.success_rate >= 0.55 ? 'text-green-400' : 'text-red-400') : 'text-[var(--muted)]'}
        />
      </div>

      {/* ── 본문 2열 ─────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* 최근 특징주 테이블 */}
        <Card className="lg:col-span-2">
          <CardHeader className="flex items-center justify-between">
            <div>
              <CardTitle>최근 특징주</CardTitle>
              <div className="text-sm text-[var(--muted)] mt-0.5">최근 8시간 탐지 · 스코어 높은 순 · 이벤트 클릭 시 상세</div>
            </div>
            <button onClick={() => nav('/features')} className="text-sm text-cyan-400 hover:text-cyan-300 transition-colors">전체보기 →</button>
          </CardHeader>
          <CardBody className="pt-3 px-0 pb-0">
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
                  {recentFeatures?.map((f) => (
                    <tr
                      key={f.id}
                      className="border-b border-[var(--border)]/50 hover:bg-[var(--border)]/25 cursor-pointer transition-colors"
                      onClick={() => nav(`/search?code=${f.code}`)}
                    >
                      <td className="py-3 pl-5 pr-3">
                        <div className="font-semibold text-sm text-[var(--fg)]">{f.name}</div>
                        <div className="flex items-center gap-1 mt-0.5">
                          <span className="text-sm text-[var(--muted)]">{f.code}</span>
                          <MarketBadge market={f.market} />
                        </div>
                      </td>
                      <td className="py-3 pr-3">
                        <button
                          onClick={(e) => { e.stopPropagation(); setSelectedEvent(f as FeatureEvent) }}
                          className="hover:scale-105 transition-transform"
                          title="이벤트 상세 보기"
                        >
                          <Badge eventType={f.event_type} size="sm" />
                        </button>
                      </td>
                      <td className="py-3 text-right tabular text-sm text-[var(--fg)] font-medium pr-3">{fmt.price(f.price)}</td>
                      <td className={clsx('py-3 text-right tabular text-sm font-semibold pr-3', pctColor(f.change_rate))}>{fmt.pct(f.change_rate)}</td>
                      <td className="py-3 text-right tabular text-sm text-yellow-400 font-semibold pr-5">{f.signal_score?.toFixed(2) ?? '—'}</td>
                    </tr>
                  ))}
                  {!recentFeatures?.length && (
                    <tr>
                      <td colSpan={5} className="py-14 text-center">
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

        {/* 추천 종목 */}
        <Card>
          <CardHeader className="flex items-center justify-between">
            <div>
              <CardTitle>추천 종목</CardTitle>
              <div className="text-sm text-[var(--muted)] mt-0.5">클릭 시 상세 분석</div>
            </div>
            <button onClick={() => nav('/recommendations')} className="text-sm text-cyan-400 hover:text-cyan-300 transition-colors">전체보기 →</button>
          </CardHeader>
          <CardBody className="pt-3">
            {topRecs && topRecs.length > 0 ? (
              <div className="grid grid-cols-1 gap-2">
                {topRecs.map((rec) => (
                  <div
                    key={rec.id}
                    className="flex items-center justify-between p-3 rounded-lg border border-[var(--border)] hover:bg-[var(--border)]/30 cursor-pointer transition-colors"
                    onClick={() => setSelectedRec(rec)}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="font-semibold text-sm text-[var(--fg)] truncate">{rec.name}</div>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <span className="text-sm text-[var(--muted)]">{rec.code}</span>
                        <MarketBadge market={rec.market} />
                        <ActionBadge action={rec.action} />
                      </div>
                    </div>
                    <div className="text-right ml-3 flex-shrink-0">
                      <div className="text-sm font-bold text-green-400 tabular">{(rec.success_prob * 100).toFixed(1)}%</div>
                      <div className="text-xs text-[var(--muted)] mt-0.5 tabular">R:R {rec.risk_reward_ratio?.toFixed(1) ?? '—'}</div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-10 text-center">
                <div className="text-sm text-[var(--muted)]">추천 데이터가 없습니다</div>
                <div className="text-xs text-[var(--muted)]/60 mt-1">조건에 맞는 신호를 기다리는 중</div>
              </div>
            )}
          </CardBody>
        </Card>
      </div>

      {/* ── 시장 상승/하락 + 이벤트 분포 ─────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {movers?.gainers && movers.gainers.length > 0 && (
          <Card>
            <CardHeader><CardTitle>상위 상승 종목</CardTitle></CardHeader>
            <CardBody className="pt-3 space-y-1">
              {movers.gainers.slice(0, 6).map((s) => (
                <div key={s.code} className="flex items-center justify-between cursor-pointer hover:bg-[var(--border)]/25 rounded-lg px-2 py-2 transition-colors" onClick={() => nav(`/search?code=${s.code}`)}>
                  <div className="text-[0.8125rem] font-medium text-[var(--fg)] truncate flex-1">{s.name}</div>
                  <div className="text-[0.8125rem] font-bold text-red-400 tabular ml-3">+{s.change_rate.toFixed(2)}%</div>
                </div>
              ))}
            </CardBody>
          </Card>
        )}

        {movers?.losers && movers.losers.length > 0 && (
          <Card>
            <CardHeader><CardTitle>상위 하락 종목</CardTitle></CardHeader>
            <CardBody className="pt-3 space-y-1">
              {movers.losers.slice(0, 6).map((s) => (
                <div key={s.code} className="flex items-center justify-between cursor-pointer hover:bg-[var(--border)]/25 rounded-lg px-2 py-2 transition-colors" onClick={() => nav(`/search?code=${s.code}`)}>
                  <div className="text-[0.8125rem] font-medium text-[var(--fg)] truncate flex-1">{s.name}</div>
                  <div className="text-[0.8125rem] font-bold text-blue-400 tabular ml-3">{s.change_rate.toFixed(2)}%</div>
                </div>
              ))}
            </CardBody>
          </Card>
        )}

        {summary?.by_type && Object.keys(summary.by_type).length > 0 && (
          <Card>
            <CardHeader><CardTitle>오늘 이벤트 분포</CardTitle></CardHeader>
            <CardBody className="pt-3">
              <div className="flex flex-wrap gap-2">
                {Object.entries(summary.by_type).sort(([, a], [, b]) => b - a).map(([type, count]) => (
                  <div
                    key={type}
                    className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-[var(--border)] cursor-pointer hover:bg-[var(--border)]/30 transition-colors"
                    onClick={() => nav(`/features?event_type=${type}`)}
                  >
                    <Badge eventType={type} size="sm" />
                    <span className="text-sm font-bold text-[var(--fg)] tabular">{count}</span>
                  </div>
                ))}
              </div>
            </CardBody>
          </Card>
        )}
      </div>

      {/* ── 이벤트 상세 팝업 ─────────────────────────────────────────── */}
      {selectedEvent && (
        <EventDetailModal
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
          onGoDetail={() => { setSelectedEvent(null); nav(`/search?code=${selectedEvent.code}`) }}
        />
      )}

      {/* ── 추천 신호 상세 팝업 ────────────────────────────────────────── */}
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
