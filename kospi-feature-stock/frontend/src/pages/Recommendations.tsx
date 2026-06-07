import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { TrendingUp, Shield, Zap, Target } from 'lucide-react'
import { recommendationsApi } from '@/api/recommendations'
import { Badge, ActionBadge, MarketBadge } from '@/components/ui/Badge'
import { StatCard, Card, CardBody } from '@/components/ui/Card'
import { fmt, pctColor, probColor } from '@/lib/utils'

export function Recommendations() {
  const nav = useNavigate()
  const [filter, setFilter] = useState<'ALL' | 'BUY' | 'WAIT' | 'SKIP'>('BUY')
  const [minProb, setMinProb] = useState(0.5)

  const { data: recs, isLoading } = useQuery({
    queryKey:       ['recs', filter, minProb],
    queryFn:        () =>
      recommendationsApi.list({
        action:   filter === 'ALL' ? undefined : filter,
        min_prob: minProb,
        limit:    100,
      }),
    refetchInterval: 60_000,
  })

  const { data: perf } = useQuery({
    queryKey:       ['perf-30'],
    queryFn:        () => recommendationsApi.getPerformance(30),
    refetchInterval: 300_000,
  })

  const buys = recs?.filter((r) => r.action === 'BUY') ?? []

  return (
    <div className="p-6 space-y-5">

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
          value={buys.length}
          sub={`확률 ${(minProb * 100).toFixed(0)}% 이상`}
          valueColor="text-green-400"
        />
      </div>

      {/* 필터 바 */}
      <div className="flex flex-wrap items-center gap-3 p-3 bg-[var(--card)] border border-[var(--border)] rounded-xl">
        <div className="flex rounded-lg overflow-hidden border border-[var(--border)]">
          {(['ALL', 'BUY', 'WAIT', 'SKIP'] as const).map((a) => (
            <button
              key={a}
              onClick={() => setFilter(a)}
              className={clsx(
                'px-3 py-1.5 text-xs font-medium transition-colors',
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
          <span className="text-xs text-[var(--muted)]">최소 확률</span>
          <input
            type="range"
            min="0.3"
            max="0.9"
            step="0.05"
            value={minProb}
            onChange={(e) => setMinProb(Number(e.target.value))}
            className="w-24 accent-cyan-400"
          />
          <span className="text-xs tabular text-cyan-400 font-semibold w-10">
            {(minProb * 100).toFixed(0)}%
          </span>
        </div>

        <div className="ml-auto text-xs text-[var(--muted)]">
          {isLoading ? '로딩 중…' : `${recs?.length ?? 0}건`}
        </div>
      </div>

      {/* 신호 카드 그리드 */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {recs?.map((rec) => (
          <Card
            key={rec.id}
            className="hover:border-cyan-500/40 transition-colors cursor-pointer"
            onClick={() => nav(`/search?code=${rec.code}`)}
          >
            <CardBody>
              {/* 헤더 */}
              <div className="flex items-start justify-between mb-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-sm text-[var(--fg)]">{rec.name}</span>
                    <MarketBadge market={rec.market} />
                  </div>
                  <div className="text-[10px] text-[var(--muted)] mt-0.5">{rec.code} · {fmt.dateTime(rec.created_at)}</div>
                </div>
                <ActionBadge action={rec.action} />
              </div>

              {/* 확률 바 */}
              <div className="mb-3">
                <div className="flex justify-between text-[10px] mb-1">
                  <span className="text-[var(--muted)]">성공 확률</span>
                  <span className={clsx('font-bold tabular', probColor(rec.success_prob))}>
                    {fmt.prob(rec.success_prob)}
                  </span>
                </div>
                <div className="h-1.5 bg-[var(--border)] rounded-full overflow-hidden">
                  <div
                    className={clsx('h-full rounded-full transition-all',
                      rec.success_prob >= 0.7 ? 'bg-green-400' :
                      rec.success_prob >= 0.55 ? 'bg-yellow-400' : 'bg-[var(--muted)]'
                    )}
                    style={{ width: `${rec.success_prob * 100}%` }}
                  />
                </div>
              </div>

              {/* 가격 정보 */}
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="bg-[var(--bg)] rounded-lg p-2">
                  <div className="text-[9px] text-[var(--muted)] font-medium flex items-center justify-center gap-0.5">
                    <Zap size={8} /> 진입가
                  </div>
                  <div className="text-xs font-bold text-[var(--fg)] tabular mt-0.5">
                    {fmt.price(rec.entry_price)}
                  </div>
                </div>
                <div className="bg-red-500/10 rounded-lg p-2 border border-red-500/20">
                  <div className="text-[9px] text-red-400 font-medium flex items-center justify-center gap-0.5">
                    <Target size={8} /> 목표가
                  </div>
                  <div className="text-xs font-bold text-red-400 tabular mt-0.5">
                    {fmt.price(rec.target_price)}
                  </div>
                </div>
                <div className="bg-blue-500/10 rounded-lg p-2 border border-blue-500/20">
                  <div className="text-[9px] text-blue-400 font-medium flex items-center justify-center gap-0.5">
                    <Shield size={8} /> 손절가
                  </div>
                  <div className="text-xs font-bold text-blue-400 tabular mt-0.5">
                    {fmt.price(rec.stop_loss_price)}
                  </div>
                </div>
              </div>

              {/* 하단 메타 */}
              <div className="flex items-center justify-between mt-3 pt-3 border-t border-[var(--border)]">
                <div className="flex items-center gap-3 text-[10px] text-[var(--muted)]">
                  <span className="flex items-center gap-0.5">
                    <TrendingUp size={9} />
                    R:R {rec.risk_reward_ratio?.toFixed(1) ?? '—'}
                  </span>
                  <span>예상 {rec.expected_hold_days}일</span>
                </div>
                <div className="flex items-center gap-1.5">
                  {rec.rationale?.atr_based && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded border border-cyan-500/30 text-cyan-400">ATR</span>
                  )}
                  {rec.rationale?.event_type && (
                    <Badge eventType={rec.rationale.event_type} size="sm" />
                  )}
                </div>
              </div>
            </CardBody>
          </Card>
        ))}
        {!isLoading && (!recs || recs.length === 0) && (
          <div className="col-span-full py-16 text-center text-[var(--muted)] text-sm">
            조건에 맞는 신호가 없습니다
          </div>
        )}
      </div>
    </div>
  )
}
