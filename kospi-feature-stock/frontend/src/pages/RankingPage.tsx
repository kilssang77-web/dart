import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { TrendingUp, TrendingDown, BarChart3, ArrowUpRight, ArrowDownRight } from 'lucide-react'
import { rankingApi } from '@/api/ranking'
import type { RankingItem, RankingMarket, RankingSortBy } from '@/api/ranking'
import { Card, CardBody, StatCard } from '@/components/ui/Card'
import { fmt, pctColor } from '@/lib/utils'
import { ErrorState } from '@/components/ui/ErrorState'

const MARKET_OPTS: { label: string; value: RankingMarket }[] = [
  { label: '전체', value: 'ALL' },
  { label: 'KOSPI', value: 'KOSPI' },
  { label: 'KOSDAQ', value: 'KOSDAQ' },
]

const LIMIT_OPTS = [50, 100, 200]

const SORT_OPTS: { label: string; value: RankingSortBy }[] = [
  { label: '종합점수', value: 'score' },
  { label: '수급점수', value: 'supply_score' },
  { label: 'ML점수',  value: 'ml_score' },
  { label: '모멘텀',  value: 'momentum_score' },
  { label: '기대수익', value: 'expected_return' },
  { label: '당일등락', value: 'change_pct' },
]

function ScoreBar({ value, max, color }: { value: number; max: number; color: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className="flex-1 h-1.5 bg-[var(--border)] rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${color}`}
          style={{ width: `${Math.min(100, (value / max) * 100)}%` }}
        />
      </div>
      <span className="text-[10px] tabular text-[var(--muted)] w-8 text-right">{value.toFixed(0)}</span>
    </div>
  )
}

function RiskBadge({ level }: { level: RankingItem['risk_level'] }) {
  const cls = level === 'LOW'
    ? 'bg-green-500/15 text-green-400 border-green-500/30'
    : level === 'MEDIUM'
    ? 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30'
    : 'bg-red-500/15 text-red-400 border-red-500/30'
  const label = level === 'LOW' ? '낮음' : level === 'MEDIUM' ? '중간' : '높음'
  return (
    <span className={clsx('text-[10px] px-1.5 py-0.5 rounded border font-semibold whitespace-nowrap', cls)}>
      {label}
    </span>
  )
}

export function RankingPage() {
  const nav = useNavigate()
  const [market,  setMarket]  = useState<RankingMarket>('ALL')
  const [limit,   setLimit]   = useState(100)
  const [sortBy,  setSortBy]  = useState<RankingSortBy>('score')

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey:        ['ranking-daily', market, limit, sortBy],
    queryFn:         () => rankingApi.getDaily({ market, limit, sort_by: sortBy }),
    staleTime:       5 * 60_000,
    refetchInterval: 10 * 60_000,
  })

  const avgScore    = data ? data.reduce((s, r) => s + r.score, 0) / data.length : 0
  const topScore    = data?.[0]?.score ?? 0
  const lowRiskCnt  = data?.filter((r) => r.risk_level === 'LOW').length ?? 0
  const highRetCnt  = data?.filter((r) => r.expected_return >= 5).length ?? 0

  return (
    <div className="p-5 space-y-5 max-w-[1600px]">

      {/* 상단 통계 카드 */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="평균 종합점수"
          value={isLoading ? '—' : `${avgScore.toFixed(1)}점`}
          sub={`${data?.length ?? 0}종목 기준`}
          valueColor="text-cyan-400"
        />
        <StatCard
          label="최고 점수"
          value={isLoading ? '—' : `${topScore.toFixed(1)}점`}
          sub={data?.[0]?.name ?? ''}
          valueColor="text-green-400"
        />
        <StatCard
          label="저위험 종목"
          value={isLoading ? '—' : lowRiskCnt}
          sub="점수 70점 이상"
          valueColor="text-green-400"
        />
        <StatCard
          label="기대수익 5%+"
          value={isLoading ? '—' : highRetCnt}
          sub="52주 고가 여력"
          valueColor="text-purple-400"
        />
      </div>

      {/* 필터 바 */}
      <div className="flex flex-wrap items-center gap-3 p-4 bg-[var(--card)] border border-[var(--border)] rounded-xl">
        {/* 시장 필터 */}
        <div className="flex rounded-lg overflow-hidden border border-[var(--border)]">
          {MARKET_OPTS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setMarket(opt.value)}
              className={clsx(
                'px-4 py-2 text-sm font-medium transition-colors',
                market === opt.value
                  ? 'bg-cyan-500/20 text-cyan-400'
                  : 'text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)]'
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {/* 개수 */}
        <div className="flex items-center gap-1">
          <span className="text-sm text-[var(--muted)]">상위</span>
          <div className="flex rounded-lg overflow-hidden border border-[var(--border)]">
            {LIMIT_OPTS.map((l) => (
              <button
                key={l}
                onClick={() => setLimit(l)}
                className={clsx(
                  'px-3 py-2 text-sm font-medium transition-colors',
                  limit === l
                    ? 'bg-cyan-500/20 text-cyan-400'
                    : 'text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)]'
                )}
              >
                {l}
              </button>
            ))}
          </div>
        </div>

        {/* 정렬 */}
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as RankingSortBy)}
          className="px-3 py-2 rounded-lg text-sm border border-[var(--border)] bg-[var(--card)] text-[var(--fg)] outline-none"
        >
          {SORT_OPTS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>

        <span className="ml-auto text-sm text-[var(--muted)]">
          {isLoading ? '로딩 중…' : `${data?.length ?? 0}종목`}
        </span>
      </div>

      {/* 에러 */}
      {isError && <ErrorState error={error as Error} retry={refetch} />}

      {/* 랭킹 테이블 */}
      {!isError && (
        <Card>
          <CardBody className="p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] text-[var(--muted)] bg-[var(--bg)]">
                  <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider w-10">순위</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider">종목명/섹터</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold uppercase tracking-wider">현재가</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider min-w-[160px]">종합점수</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider min-w-[120px]">수급/ML</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold uppercase tracking-wider">기대수익</th>
                  <th className="text-center px-4 py-3 text-xs font-semibold uppercase tracking-wider">리스크</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold uppercase tracking-wider">당일등락</th>
                </tr>
              </thead>
              <tbody>
                {isLoading && Array.from({ length: 10 }).map((_, i) => (
                  <tr key={i} className="border-b border-[var(--border)]/40">
                    {Array.from({ length: 8 }).map((__, j) => (
                      <td key={j} className="px-4 py-3">
                        <div className="h-4 skeleton rounded w-full" />
                      </td>
                    ))}
                  </tr>
                ))}
                {data?.map((item, idx) => (
                  <tr
                    key={item.code}
                    className="border-b border-[var(--border)]/40 hover:bg-[var(--border)]/15 cursor-pointer transition-colors"
                    onClick={() => nav(`/search?code=${item.code}`)}
                  >
                    {/* 순위 */}
                    <td className="px-4 py-3">
                      <span className={clsx(
                        'text-sm font-bold tabular',
                        idx === 0 ? 'text-yellow-400' : idx === 1 ? 'text-gray-400' : idx === 2 ? 'text-amber-600' : 'text-[var(--muted)]'
                      )}>
                        {idx + 1}
                      </span>
                    </td>

                    {/* 종목명/섹터 */}
                    <td className="px-4 py-3">
                      <div className="flex flex-col min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="font-semibold text-[var(--fg)] truncate">{item.name}</span>
                          <span className="text-[10px] text-[var(--muted)] font-mono shrink-0">{item.code}</span>
                          <span className={clsx(
                            'text-[10px] px-1 rounded font-medium shrink-0',
                            item.market === 'KOSPI' ? 'bg-blue-500/15 text-blue-400' : 'bg-purple-500/15 text-purple-400'
                          )}>
                            {item.market}
                          </span>
                        </div>
                        {item.sector && (
                          <span className="text-[10px] text-[var(--muted)] truncate mt-0.5">{item.sector}</span>
                        )}
                      </div>
                    </td>

                    {/* 현재가 */}
                    <td className="px-4 py-3 text-right">
                      <span className="tabular font-medium text-[var(--fg)]">{item.current_price.toLocaleString()}</span>
                    </td>

                    {/* 종합점수 */}
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className={clsx(
                          'text-sm font-bold tabular w-12 shrink-0',
                          item.score >= 70 ? 'text-green-400' : item.score >= 50 ? 'text-amber-400' : 'text-[var(--muted)]'
                        )}>
                          {item.score.toFixed(1)}
                        </span>
                        <div className="flex-1 h-2 bg-[var(--border)] rounded-full overflow-hidden min-w-[60px]">
                          <div
                            className={clsx(
                              'h-full rounded-full',
                              item.score >= 70 ? 'bg-green-400' : item.score >= 50 ? 'bg-amber-400' : 'bg-red-400'
                            )}
                            style={{ width: `${Math.min(100, item.score)}%` }}
                          />
                        </div>
                      </div>
                    </td>

                    {/* 수급/ML */}
                    <td className="px-4 py-3">
                      <div className="space-y-1 min-w-[100px]">
                        <ScoreBar value={item.supply_score} max={30} color="bg-cyan-400" />
                        <ScoreBar value={item.ml_score} max={40} color="bg-purple-400" />
                      </div>
                    </td>

                    {/* 기대수익 */}
                    <td className="px-4 py-3 text-right">
                      <span className={clsx(
                        'tabular font-semibold text-sm',
                        item.expected_return >= 10 ? 'text-red-400' : item.expected_return >= 5 ? 'text-amber-400' : 'text-[var(--muted)]'
                      )}>
                        +{item.expected_return.toFixed(1)}%
                      </span>
                    </td>

                    {/* 리스크 */}
                    <td className="px-4 py-3 text-center">
                      <RiskBadge level={item.risk_level} />
                    </td>

                    {/* 당일등락 */}
                    <td className="px-4 py-3 text-right">
                      <div className={clsx(
                        'flex items-center justify-end gap-0.5 tabular font-semibold text-sm',
                        item.change_pct > 0 ? 'text-red-400' : item.change_pct < 0 ? 'text-blue-400' : 'text-[var(--muted)]'
                      )}>
                        {item.change_pct > 0 ? <ArrowUpRight size={12} /> : item.change_pct < 0 ? <ArrowDownRight size={12} /> : null}
                        {item.change_pct > 0 ? '+' : ''}{item.change_pct.toFixed(2)}%
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardBody>
        </Card>
      )}

      {!isLoading && !isError && (!data || data.length === 0) && (
        <div className="py-16 text-center text-[var(--muted)] text-sm">랭킹 데이터를 불러올 수 없습니다</div>
      )}
    </div>
  )
}
