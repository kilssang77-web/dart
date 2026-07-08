import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { Target, TrendingUp, Activity, CheckCircle2, XCircle, Clock, AlertTriangle, LineChartIcon, TrendingDown } from 'lucide-react'
import { StatCard, Card, CardHeader, CardTitle, CardBody } from '@/components/ui/Card'
import {
  BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ComposedChart, Line, Legend, AreaChart, Area, ReferenceLine,
} from 'recharts'
import {
  recommendationsApi,
  type ActivePerformanceItem,
  type HistoryPerformanceItem,
  type PerformanceSummary,
  type EventPerformanceItem,
} from '@/api/recommendations'
import { adminApi, type DailyPnl } from '@/api/admin'
import { fmt, pctColor, probToScore, scoreBarColor } from '@/lib/utils'

type HistoryDays = 30 | 90 | 180 | 365

const TOOLTIP_STYLE = {
  background: 'var(--card)', border: '1px solid var(--border)',
  borderRadius: 8, fontSize: 12, color: 'var(--fg)',
}

function ReturnCell({ value }: { value: number | null | undefined }) {
  if (value == null) return <span className="text-[var(--muted)]">—</span>
  return (
    <span className={clsx('tabular font-semibold', pctColor(value))}>
      {value >= 0 ? '+' : ''}{value.toFixed(2)}%
    </span>
  )
}

function StatusBadge({ hit_target, hit_stop, is_success }: {
  hit_target?: boolean | null
  hit_stop?:   boolean | null
  is_success?: boolean | null
}) {
  if (hit_target) return (
    <span className="flex items-center gap-1 text-xs text-red-400 font-semibold">
      <CheckCircle2 size={11} /> 목표달성
    </span>
  )
  if (hit_stop) return (
    <span className="flex items-center gap-1 text-xs text-blue-400 font-semibold">
      <XCircle size={11} /> 손절
    </span>
  )
  if (is_success === true) return (
    <span className="text-xs text-red-400 font-semibold">성공</span>
  )
  if (is_success === false) return (
    <span className="text-xs text-blue-400 font-semibold">실패</span>
  )
  return <span className="flex items-center gap-1 text-xs text-cyan-400"><Clock size={10} /> 추적중</span>
}

export function PerformanceTracking() {
  const [historyDays, setHistoryDays] = useState<HistoryDays>(365)

  const { data: summary } = useQuery<PerformanceSummary>({
    queryKey:        ['perf-summary', historyDays],
    queryFn:         () => recommendationsApi.getPerformanceSummary(historyDays),
    refetchInterval: 120_000,
  })

  const { data: active = [], isLoading: activeLoading } = useQuery<ActivePerformanceItem[]>({
    queryKey:        ['perf-active'],
    queryFn:         recommendationsApi.getActivePerformance,
    refetchInterval: 60_000,
  })

  const { data: history = [], isLoading: historyLoading } = useQuery<HistoryPerformanceItem[]>({
    queryKey: ['perf-history', historyDays],
    queryFn:  () => recommendationsApi.getPerformanceHistory(historyDays, 500),
    staleTime: 120_000,
  })

  const { data: byEvent = [] } = useQuery<EventPerformanceItem[]>({
    queryKey:        ['perf-by-event', historyDays],
    queryFn:         () => recommendationsApi.getPerformanceByEvent(historyDays),
    refetchInterval: 300_000,
  })

  const { data: pnl } = useQuery<DailyPnl>({
    queryKey:        ['daily-pnl', historyDays],
    queryFn:         () => adminApi.getDailyPnl(historyDays),
    refetchInterval: 300_000,
  })

  // 날짜별 성과 집계 (주간)
  const trendData = useMemo(() => {
    if (!history.length) return []
    const byWeek: Record<string, { r1d: number[]; r5d: number[]; wins: number; total: number }> = {}
    history.forEach((h) => {
      const d = h.created_at?.slice(0, 10) ?? ''
      if (!d) return
      const dt = new Date(d)
      const weekStart = new Date(dt)
      weekStart.setDate(dt.getDate() - dt.getDay())
      const key = weekStart.toISOString().slice(0, 10)
      if (!byWeek[key]) byWeek[key] = { r1d: [], r5d: [], wins: 0, total: 0 }
      if (h.r_1d != null) byWeek[key].r1d.push(h.r_1d)
      if (h.r_5d != null) byWeek[key].r5d.push(h.r_5d)
      byWeek[key].total++
      if (h.is_success) byWeek[key].wins++
    })
    return Object.entries(byWeek)
      .sort(([a], [b]) => a.localeCompare(b))
      .slice(-16)
      .map(([week, v]) => ({
        week: week.slice(5),
        avg_r1d: v.r1d.length ? +(v.r1d.reduce((s, x) => s + x, 0) / v.r1d.length).toFixed(2) : null,
        avg_r5d: v.r5d.length ? +(v.r5d.reduce((s, x) => s + x, 0) / v.r5d.length).toFixed(2) : null,
        win_rate: v.total > 0 ? +(v.wins / v.total * 100).toFixed(1) : null,
        count: v.total,
      }))
  }, [history])

  const returnDist = history.reduce<Record<string, number>>((acc, h) => {
    if (h.r_5d == null) return acc
    const bucket = h.r_5d >= 10 ? '10%+'
      : h.r_5d >= 5 ? '5~10%'
      : h.r_5d >= 0 ? '0~5%'
      : h.r_5d >= -5 ? '-5~0%'
      : '-5%↓'
    acc[bucket] = (acc[bucket] ?? 0) + 1
    return acc
  }, {})

  const distData = ['10%+', '5~10%', '0~5%', '-5~0%', '-5%↓'].map((b) => ({
    bucket: b, count: returnDist[b] ?? 0,
    fill: b.startsWith('-') ? '#3b82f6' : '#ef4444',
  }))

  return (
    <div className="p-6 space-y-5">

      {/* 기간 선택 */}
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-[var(--fg)] flex items-center gap-1.5">
          <Target size={15} className="text-cyan-400" /> 추천 성과 추적
        </span>
        <div className="flex gap-1 ml-auto">
          {([30, 90, 180, 365] as HistoryDays[]).map((d) => (
            <button key={d} onClick={() => setHistoryDays(d)}
              className={clsx(
                'px-3 py-1 rounded text-xs font-medium transition-colors',
                historyDays === d
                  ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/40'
                  : 'text-[var(--muted)] hover:text-[var(--fg)]',
              )}>
              {d}일
            </button>
          ))}
        </div>
      </div>

      {/* 데이터 신뢰도 경고 */}
      {summary && summary.completed < 30 && (
        <div className="flex items-start gap-2 rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-4 py-3 text-sm text-yellow-300">
          <AlertTriangle size={15} className="mt-0.5 shrink-0" />
          <span>
            평가 완료된 추천이 <strong>{summary.completed}건</strong>으로 통계 신뢰도가 낮습니다.
            최소 30건 이상 누적되면 수익률·승률 지표가 의미 있어집니다.
          </span>
        </div>
      )}

      {/* 요약 카드 */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <StatCard label="추적 중" value={summary.active_count.toString()} sub="BUY 추천" valueColor="text-cyan-400" />
          <StatCard label="완료" value={summary.completed.toLocaleString()} sub={`최근 ${summary.days}일`} valueColor="text-[var(--fg)]" />
          <StatCard label="승률" value={`${summary.win_rate.toFixed(1)}%`} sub="5일 기준"
            valueColor={summary.win_rate >= 55 ? 'text-red-400' : summary.win_rate >= 40 ? 'text-yellow-400' : 'text-blue-400'} />
          <StatCard label="목표 달성" value={summary.hit_target.toString()} sub="hit_target" valueColor="text-red-400" />
          <StatCard label="손절 발생" value={summary.hit_stop.toString()} sub="hit_stop" valueColor="text-blue-400" />
          <StatCard label="평균 5일 수익" value={`${summary.avg_return_5d >= 0 ? '+' : ''}${summary.avg_return_5d.toFixed(2)}%`} sub="완료 건"
            valueColor={pctColor(summary.avg_return_5d)} />
        </div>
      )}

      {/* 누적 P&L 곡선 */}
      {pnl && pnl.items.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp size={15} className="text-cyan-400" />
              누적 수익률 (Paper)
            </CardTitle>
            <div className="flex items-center gap-4 ml-auto text-xs">
              <span className={clsx('font-semibold', pctColor(pnl.total_return))}>
                총 수익: {pnl.total_return >= 0 ? '+' : ''}{pnl.total_return.toFixed(2)}%
              </span>
              <span className="flex items-center gap-1 text-blue-400 font-semibold">
                <TrendingDown size={12} />
                MDD: {pnl.mdd.toFixed(2)}%
              </span>
            </div>
          </CardHeader>
          <CardBody>
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={pnl.items} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
                <defs>
                  <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#ef4444" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#71717a' }}
                  tickFormatter={(v) => v.slice(5)} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 11, fill: '#71717a' }}
                  tickFormatter={(v) => `${v.toFixed(1)}%`} />
                <Tooltip contentStyle={TOOLTIP_STYLE}
                  formatter={(v: number, name: string) => [
                    `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`,
                    name === 'cum_r' ? '누적 수익' : '일별 5일 수익'
                  ]} />
                <ReferenceLine y={0} stroke="var(--border)" strokeDasharray="4 2" />
                <Area type="monotone" dataKey="cum_r" stroke="#ef4444" fill="url(#pnlGrad)"
                  strokeWidth={2} dot={false} name="cum_r" />
              </AreaChart>
            </ResponsiveContainer>
          </CardBody>
        </Card>
      )}

      {/* 수익률 분포 차트 */}
      {history.length > 0 && (
        <Card>
          <CardHeader><CardTitle>5일 수익률 분포</CardTitle></CardHeader>
          <CardBody>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={distData} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis dataKey="bucket" tick={{ fontSize: 12, fill: '#71717a' }} />
                <YAxis tick={{ fontSize: 12, fill: '#71717a' }} />
                <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number) => [v, '건수']} />
                <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                  {distData.map((d, i) => (
                    <Cell key={i} fill={d.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardBody>
        </Card>
      )}

      {/* 주간 수익률 추이 */}
      {trendData.length > 1 && (
        <Card>
          <CardHeader>
            <CardTitle>
              <span className="flex items-center gap-1.5">
                <LineChartIcon size={14} className="text-cyan-400" />
                주간 수익률 추이 (최근 16주)
              </span>
            </CardTitle>
          </CardHeader>
          <CardBody>
            <ResponsiveContainer width="100%" height={200}>
              <ComposedChart data={trendData} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis dataKey="week" tick={{ fontSize: 11, fill: '#71717a' }} />
                <YAxis yAxisId="ret" tick={{ fontSize: 11, fill: '#71717a' }} tickFormatter={(v) => `${v}%`} />
                <YAxis yAxisId="wr" orientation="right" tick={{ fontSize: 11, fill: '#71717a' }} tickFormatter={(v) => `${v}%`} domain={[0, 100]} />
                <Tooltip
                  contentStyle={TOOLTIP_STYLE}
                  formatter={(v: number, name: string) => [
                    `${v}%`,
                    name === 'avg_r1d' ? '1일 평균' : name === 'avg_r5d' ? '5일 평균' : '승률',
                  ]}
                />
                <Legend formatter={(v) => v === 'avg_r1d' ? '1일 평균%' : v === 'avg_r5d' ? '5일 평균%' : '승률%'} />
                <Bar yAxisId="wr" dataKey="win_rate" fill="#22d3ee" opacity={0.3} radius={[2, 2, 0, 0]} name="win_rate" />
                <Line yAxisId="ret" type="monotone" dataKey="avg_r1d" stroke="#f87171" strokeWidth={2} dot={{ r: 3 }} name="avg_r1d" connectNulls />
                <Line yAxisId="ret" type="monotone" dataKey="avg_r5d" stroke="#f97316" strokeWidth={2} dot={{ r: 3 }} name="avg_r5d" connectNulls />
              </ComposedChart>
            </ResponsiveContainer>
          </CardBody>
        </Card>
      )}

      {/* 신호 유형별 실적 */}
      {byEvent.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>
              <span className="flex items-center gap-1.5">
                <TrendingUp size={14} className="text-cyan-400" />
                신호 유형별 실적
              </span>
            </CardTitle>
          </CardHeader>
          <CardBody>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-[var(--muted)] border-b border-[var(--border)]">
                    <th className="text-left py-2 font-medium">신호 유형</th>
                    <th className="text-right py-2 font-medium">총건</th>
                    <th className="text-right py-2 font-medium">평가완료</th>
                    <th className="text-right py-2 font-medium">승률</th>
                    <th className="text-right py-2 font-medium">평균 1일</th>
                    <th className="text-right py-2 font-medium">평균 5일</th>
                    <th className="text-right py-2 font-medium">평균 10일</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border)]">
                  {byEvent.map((ev) => (
                    <tr key={ev.event_type} className="hover:bg-white/5">
                      <td className="py-2 font-mono text-[var(--fg)]">{ev.event_type}</td>
                      <td className="py-2 text-right tabular text-[var(--muted)]">{ev.total}</td>
                      <td className="py-2 text-right tabular text-[var(--muted)]">{ev.evaluated}</td>
                      <td className="py-2 text-right tabular">
                        {ev.win_rate != null
                          ? <span className={clsx('font-semibold', ev.win_rate >= 60 ? 'text-red-400' : ev.win_rate >= 40 ? 'text-yellow-400' : 'text-blue-400')}>
                              {ev.win_rate.toFixed(1)}%
                            </span>
                          : <span className="text-[var(--muted)]">—</span>}
                      </td>
                      <td className="py-2 text-right"><ReturnCell value={ev.avg_r1d} /></td>
                      <td className="py-2 text-right"><ReturnCell value={ev.avg_r5d} /></td>
                      <td className="py-2 text-right"><ReturnCell value={ev.avg_r10d} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardBody>
        </Card>
      )}

      {/* 활성 추적 */}
      <Card>
        <CardHeader>
          <CardTitle>
            <span className="flex items-center gap-1.5">
              <Activity size={14} className="text-cyan-400" />
              추적 중인 추천 ({active.length}건)
            </span>
          </CardTitle>
        </CardHeader>
        <CardBody>
          {activeLoading ? (
            <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-10 skeleton rounded" />)}</div>
          ) : active.length === 0 ? (
            <p className="text-sm text-[var(--muted)] text-center py-6">추적 중인 추천이 없습니다</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-[var(--muted)] border-b border-[var(--border)]">
                    <th className="text-left py-2 font-medium">종목</th>
                    <th className="text-right py-2 font-medium">진입가</th>
                    <th className="text-right py-2 font-medium">목표가</th>
                    <th className="text-right py-2 font-medium">손절가</th>
                    <th className="text-right py-2 font-medium">예측확률</th>
                    <th className="text-right py-2 font-medium">1일</th>
                    <th className="text-right py-2 font-medium">3일</th>
                    <th className="text-right py-2 font-medium">5일</th>
                    <th className="text-center py-2 font-medium">상태</th>
                    <th className="text-right py-2 font-medium">추천일시</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border)]">
                  {active.map((a) => (
                    <tr key={a.id} className="hover:bg-white/5">
                      <td className="py-2">
                        <div className="font-semibold text-[var(--fg)]">{a.name}</div>
                        <div className="text-[var(--muted)] font-mono">{a.code}</div>
                      </td>
                      <td className="py-2 text-right tabular text-[var(--fg)]">{fmt.price(a.entry_price)}</td>
                      <td className="py-2 text-right tabular text-red-400">{fmt.price(a.target_price)}</td>
                      <td className="py-2 text-right tabular text-blue-400">{fmt.price(a.stop_loss_price)}</td>
                      <td className="py-2 text-right tabular">
                        <span className={clsx('font-bold', scoreBarColor(probToScore(a.success_prob)).replace('bg-', 'text-'))}>{probToScore(a.success_prob)}점</span>
                        <span className="text-[var(--muted)] text-[10px] ml-0.5">{(a.success_prob * 100).toFixed(0)}%</span>
                      </td>
                      <td className="py-2 text-right"><ReturnCell value={a.r_1d} /></td>
                      <td className="py-2 text-right"><ReturnCell value={a.r_3d} /></td>
                      <td className="py-2 text-right"><ReturnCell value={a.r_5d} /></td>
                      <td className="py-2 text-center">
                        <StatusBadge hit_target={a.hit_target} hit_stop={a.hit_stop} />
                      </td>
                      <td className="py-2 text-right tabular text-[var(--muted)]">{fmt.smartTime(a.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>

      {/* 완료 이력 */}
      <Card>
        <CardHeader>
          <CardTitle>
            <span className="flex items-center gap-1.5">
              <CheckCircle2 size={14} className="text-green-400" />
              완료된 추천 이력 ({history.length}건)
            </span>
          </CardTitle>
        </CardHeader>
        <CardBody>
          {historyLoading ? (
            <div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-10 skeleton rounded" />)}</div>
          ) : history.length === 0 ? (
            <p className="text-sm text-[var(--muted)] text-center py-6">완료된 추천 이력이 없습니다</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-[var(--muted)] border-b border-[var(--border)]">
                    <th className="text-left py-2 font-medium">종목</th>
                    <th className="text-left py-2 font-medium">이벤트</th>
                    <th className="text-right py-2 font-medium">진입가</th>
                    <th className="text-right py-2 font-medium">예측</th>
                    <th className="text-right py-2 font-medium">1일</th>
                    <th className="text-right py-2 font-medium">3일</th>
                    <th className="text-right py-2 font-medium">5일</th>
                    <th className="text-right py-2 font-medium">10일</th>
                    <th className="text-right py-2 font-medium">최고</th>
                    <th className="text-center py-2 font-medium">결과</th>
                    <th className="text-right py-2 font-medium">추천일</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border)]">
                  {history.map((h) => (
                    <tr key={h.id} className={clsx('hover:bg-white/5', h.is_success === true && 'bg-red-500/3', h.is_success === false && 'bg-blue-500/3')}>
                      <td className="py-2">
                        <div className="font-semibold text-[var(--fg)]">{h.name}</div>
                        <div className="text-[var(--muted)] font-mono">{h.code}</div>
                      </td>
                      <td className="py-2 text-[var(--muted)]">{h.event_type ?? '—'}</td>
                      <td className="py-2 text-right tabular text-[var(--fg)]">{fmt.price(h.entry_price)}</td>
                      <td className="py-2 text-right tabular">
                        <span className={clsx('font-bold', scoreBarColor(probToScore(h.success_prob)).replace('bg-', 'text-'))}>{probToScore(h.success_prob)}점</span>
                        <span className="text-[var(--muted)] text-[10px] ml-0.5">{(h.success_prob * 100).toFixed(0)}%</span>
                      </td>
                      <td className="py-2 text-right"><ReturnCell value={h.r_1d} /></td>
                      <td className="py-2 text-right"><ReturnCell value={h.r_3d} /></td>
                      <td className="py-2 text-right"><ReturnCell value={h.r_5d} /></td>
                      <td className="py-2 text-right"><ReturnCell value={h.r_10d} /></td>
                      <td className="py-2 text-right">
                        {h.max_return != null
                          ? <span className="tabular text-red-400 font-semibold">+{h.max_return.toFixed(2)}%</span>
                          : <span className="text-[var(--muted)]">—</span>}
                      </td>
                      <td className="py-2 text-center">
                        <StatusBadge hit_target={h.hit_target} hit_stop={h.hit_stop} is_success={h.is_success} />
                      </td>
                      <td className="py-2 text-right tabular text-[var(--muted)]">{fmt.smartTime(h.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  )
}
