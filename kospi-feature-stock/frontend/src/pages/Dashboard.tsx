import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { TrendingUp, TrendingDown, Minus, ArrowUpRight, ArrowDownRight } from 'lucide-react'
import { clsx } from 'clsx'
import { featuresApi } from '@/api/features'
import { recommendationsApi } from '@/api/recommendations'
import { marketApi } from '@/api/market'
import { StatCard, Card, CardHeader, CardTitle, CardBody } from '@/components/ui/Card'
import { Badge, ActionBadge, MarketBadge } from '@/components/ui/Badge'
import { fmt, pctColor } from '@/lib/utils'

export function Dashboard() {
  const nav = useNavigate()

  const { data: summary } = useQuery({
    queryKey:        ['today-summary'],
    queryFn:         featuresApi.todaySummary,
    refetchInterval: 30_000,
  })

  const { data: recentFeatures } = useQuery({
    queryKey:        ['features-recent'],
    queryFn:         () => featuresApi.list({ limit: 12, hours: 8 }),
    refetchInterval: 30_000,
  })

  const { data: buySignals } = useQuery({
    queryKey:        ['buy-signals'],
    queryFn:         () => recommendationsApi.getBuySignals(0.55),
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

  const { data: movers } = useQuery({
    queryKey:        ['market-movers'],
    queryFn:         marketApi.getMovers,
    refetchInterval: 60_000,
  })

  return (
    <div className="p-6 space-y-5">

      {/* 시장 요약 바 */}
      {mkSummary && (
        <div className="flex flex-wrap gap-3">
          {[
            { name: 'KOSPI',  change: mkSummary.kospi_avg_change },
            { name: 'KOSDAQ', change: mkSummary.kosdaq_avg_change },
          ].map((idx) => {
            const up = idx.change > 0
            const dn = idx.change < 0
            return (
              <div key={idx.name} className="flex items-center gap-3 bg-[var(--card)] border border-[var(--border)] rounded-xl px-4 py-2.5 min-w-[160px]">
                <div>
                  <div className="text-[10px] font-semibold text-[var(--muted)] uppercase tracking-wide">{idx.name}</div>
                  <div className={clsx('text-xs font-medium mt-0.5 text-[var(--muted)]')}>평균 등락률</div>
                </div>
                <div className={clsx('ml-auto text-lg font-bold tabular', up ? 'text-red-400' : dn ? 'text-blue-400' : 'text-[var(--fg)]')}>
                  {up ? '+' : ''}{idx.change.toFixed(2)}%
                  {up ? <TrendingUp size={14} className="inline ml-1" /> : dn ? <TrendingDown size={14} className="inline ml-1" /> : <Minus size={14} className="inline ml-1" />}
                </div>
              </div>
            )
          })}

          {mkSummary.advancers != null && (
            <div className="flex items-center gap-3 bg-[var(--card)] border border-[var(--border)] rounded-xl px-4 py-2.5">
              <div className="text-[10px] text-[var(--muted)]">상승/하락</div>
              <div className="flex items-center gap-2 ml-2">
                <span className="text-sm font-bold text-red-400 tabular flex items-center gap-0.5">
                  <ArrowUpRight size={12} />{mkSummary.advancers}
                </span>
                <span className="text-[var(--muted)]">/</span>
                <span className="text-sm font-bold text-blue-400 tabular flex items-center gap-0.5">
                  <ArrowDownRight size={12} />{mkSummary.decliners}
                </span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 통계 카드 4개 */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="오늘 탐지"
          value={summary?.total ?? '—'}
          sub={`평균 스코어 ${summary?.avg_score?.toFixed(2) ?? '—'}`}
          valueColor="text-cyan-400"
          onClick={() => nav('/features')}
        />
        <StatCard
          label="고점수 신호"
          value={summary?.high_score ?? '—'}
          sub="스코어 0.7 이상"
          valueColor="text-yellow-400"
        />
        <StatCard
          label="매수 신호"
          value={buySignals?.length ?? '—'}
          sub="ML 확률 55% 이상"
          valueColor="text-green-400"
          onClick={() => nav('/recommendations')}
        />
        <StatCard
          label="30일 성공률"
          value={perf ? `${(perf.success_rate * 100).toFixed(1)}%` : '—'}
          sub={`${perf?.success_count ?? '—'}/${perf?.buy_count ?? '—'} 성공`}
          valueColor={perf ? (perf.success_rate >= 0.55 ? 'text-green-400' : 'text-red-400') : 'text-[var(--muted)]'}
        />
      </div>

      {/* 본문 2열 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* 최근 특징주 테이블 */}
        <Card className="lg:col-span-2">
          <CardHeader className="flex items-center justify-between">
            <div>
              <CardTitle>최근 특징주</CardTitle>
              <div className="text-xs text-[var(--muted)] mt-0.5">최근 8시간 탐지 · 스코어 높은 순</div>
            </div>
            <button onClick={() => nav('/features')} className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors">
              전체보기 →
            </button>
          </CardHeader>
          <CardBody className="pt-3 px-0 pb-0">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-[var(--border)] text-[var(--muted)]">
                    <th className="text-left pb-2 pl-5 pr-3 font-medium">종목</th>
                    <th className="text-left pb-2 pr-3 font-medium">이벤트</th>
                    <th className="text-right pb-2 pr-3 font-medium">현재가</th>
                    <th className="text-right pb-2 pr-3 font-medium">등락률</th>
                    <th className="text-right pb-2 pr-5 font-medium">스코어</th>
                  </tr>
                </thead>
                <tbody>
                  {recentFeatures?.map((f) => (
                    <tr key={f.id} className="border-b border-[var(--border)]/50 hover:bg-[var(--border)]/25 cursor-pointer transition-colors" onClick={() => nav(`/search?code=${f.code}`)}>
                      <td className="py-2.5 pl-5 pr-3">
                        <div className="font-semibold text-[var(--fg)]">{f.name}</div>
                        <div className="flex items-center gap-1 mt-0.5">
                          <span className="text-[var(--muted)]">{f.code}</span>
                          <MarketBadge market={f.market} />
                        </div>
                      </td>
                      <td className="py-2.5 pr-3"><Badge eventType={f.event_type} size="sm" /></td>
                      <td className="py-2.5 text-right tabular text-[var(--fg)] font-medium pr-3">{fmt.price(f.price)}</td>
                      <td className={clsx('py-2.5 text-right tabular font-semibold pr-3', pctColor(f.change_rate))}>{fmt.pct(f.change_rate)}</td>
                      <td className="py-2.5 text-right tabular text-yellow-400 font-semibold pr-5">{f.signal_score?.toFixed(2) ?? '—'}</td>
                    </tr>
                  ))}
                  {!recentFeatures?.length && (
                    <tr><td colSpan={5} className="py-10 text-center text-[var(--muted)]">탐지된 특징주가 없습니다</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </CardBody>
        </Card>

        {/* 매수 신호 패널 */}
        <Card>
          <CardHeader className="flex items-center justify-between">
            <div>
              <CardTitle>매수 신호</CardTitle>
              <div className="text-xs text-[var(--muted)] mt-0.5">ML 확률 기준 정렬</div>
            </div>
            <button onClick={() => nav('/recommendations')} className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors">
              전체보기 →
            </button>
          </CardHeader>
          <CardBody className="pt-3 space-y-2">
            {buySignals?.slice(0, 9).map((rec) => (
              <div key={rec.id} className="flex items-center justify-between p-2.5 rounded-lg border border-[var(--border)] hover:bg-[var(--border)]/30 cursor-pointer transition-colors" onClick={() => nav(`/search?code=${rec.code}`)}>
                <div className="min-w-0 flex-1">
                  <div className="font-semibold text-xs text-[var(--fg)] truncate">{rec.name}</div>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <span className="text-[10px] text-[var(--muted)]">{rec.code}</span>
                    <MarketBadge market={rec.market} />
                  </div>
                </div>
                <div className="text-right ml-3 flex-shrink-0">
                  <div className="text-xs font-bold text-green-400 tabular">{(rec.success_prob * 100).toFixed(1)}%</div>
                  <div className="text-[10px] text-[var(--muted)] mt-0.5">R:R {rec.risk_reward_ratio?.toFixed(1) ?? '—'}</div>
                </div>
              </div>
            ))}
            {!buySignals?.length && (
              <div className="py-8 text-center text-xs text-[var(--muted)]">매수 신호가 없습니다</div>
            )}
          </CardBody>
        </Card>
      </div>

      {/* 시장 상승/하락 탑 리스트 + 이벤트 분포 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* 상위 상승 */}
        {movers?.gainers && movers.gainers.length > 0 && (
          <Card>
            <CardHeader><CardTitle>상위 상승 종목</CardTitle></CardHeader>
            <CardBody className="pt-2 space-y-1.5">
              {movers.gainers.slice(0, 6).map((s) => (
                <div key={s.code} className="flex items-center justify-between cursor-pointer hover:bg-[var(--border)]/25 rounded-md px-1 py-1 transition-colors" onClick={() => nav(`/search?code=${s.code}`)}>
                  <div className="text-xs text-[var(--fg)] truncate flex-1">{s.name}</div>
                  <div className="text-xs font-bold text-red-400 tabular ml-2">+{s.change_rate.toFixed(2)}%</div>
                </div>
              ))}
            </CardBody>
          </Card>
        )}

        {/* 상위 하락 */}
        {movers?.losers && movers.losers.length > 0 && (
          <Card>
            <CardHeader><CardTitle>상위 하락 종목</CardTitle></CardHeader>
            <CardBody className="pt-2 space-y-1.5">
              {movers.losers.slice(0, 6).map((s) => (
                <div key={s.code} className="flex items-center justify-between cursor-pointer hover:bg-[var(--border)]/25 rounded-md px-1 py-1 transition-colors" onClick={() => nav(`/search?code=${s.code}`)}>
                  <div className="text-xs text-[var(--fg)] truncate flex-1">{s.name}</div>
                  <div className="text-xs font-bold text-blue-400 tabular ml-2">{s.change_rate.toFixed(2)}%</div>
                </div>
              ))}
            </CardBody>
          </Card>
        )}

        {/* 이벤트 분포 */}
        {summary?.by_type && Object.keys(summary.by_type).length > 0 && (
          <Card>
            <CardHeader><CardTitle>오늘 이벤트 분포</CardTitle></CardHeader>
            <CardBody className="pt-3">
              <div className="flex flex-wrap gap-2">
                {Object.entries(summary.by_type).sort(([, a], [, b]) => b - a).map(([type, count]) => (
                  <div key={type} className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-[var(--border)] cursor-pointer hover:bg-[var(--border)]/30 transition-colors" onClick={() => nav(`/features?event_type=${type}`)}>
                    <Badge eventType={type} size="sm" />
                    <span className="text-xs font-bold text-[var(--fg)] tabular">{count}</span>
                  </div>
                ))}
              </div>
            </CardBody>
          </Card>
        )}
      </div>
    </div>
  )
}
