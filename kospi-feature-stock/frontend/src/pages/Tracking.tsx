import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { TrendingUp, TrendingDown, Minus, Target, Shield, CheckCircle2, XCircle, Clock } from 'lucide-react'
import { trackingApi } from '@/api/tracking'
import type { TrackingItem } from '@/api/tracking'
import { Card, CardHeader, CardTitle, CardBody, StatCard } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { EVENT_LABELS } from '@/components/ui/Badge'
import { fmt, pctColor } from '@/lib/utils'

type DaysFilter = 7 | 30 | 90

function RCell({ val }: { val?: number | null }) {
  if (val == null) return <span className="text-[var(--muted)]">—</span>
  const color = val > 0 ? 'text-red-400' : val < 0 ? 'text-blue-400' : 'text-[var(--muted)]'
  return (
    <span className={clsx('tabular font-semibold', color)}>
      {val >= 0 ? '+' : ''}{val.toFixed(1)}%
    </span>
  )
}

export function Tracking() {
  const [days, setDays] = useState<DaysFilter>(30)
  const [page, setPage] = useState(0)
  const [filterSuccess, setFilterSuccess] = useState<boolean | undefined>(undefined)
  const LIMIT = 50

  const { data: summary } = useQuery({
    queryKey: ['tracking-summary', days],
    queryFn: () => trackingApi.summary(days),
    staleTime: 60_000,
  })

  const { data: list, isLoading } = useQuery({
    queryKey: ['tracking-list', page, filterSuccess],
    queryFn: () => trackingApi.list({ success: filterSuccess, limit: LIMIT, offset: page * LIMIT }),
    staleTime: 30_000,
  })

  const successRate = summary?.success_rate ?? 0
  const rateColor = successRate >= 60 ? 'text-green-400' : successRate >= 45 ? 'text-yellow-400' : 'text-red-400'

  return (
    <div className="p-5 space-y-5 max-w-[1400px]">
      {/* 기간 선택 */}
      <div className="flex items-center gap-2">
        {([7, 30, 90] as DaysFilter[]).map((d) => (
          <button key={d} onClick={() => setDays(d)} className={clsx(
            'px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors',
            days === d
              ? 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30'
              : 'text-[var(--muted)] border-[var(--border)] hover:text-[var(--fg)]'
          )}>
            최근 {d}일
          </button>
        ))}
      </div>

      {/* 요약 StatCards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            
            label="성공률"
            value={summary.success_rate != null ? `${summary.success_rate.toFixed(1)}%` : '—'}
            sub={`완료 ${summary.completed}건 중`}
            valueColor={rateColor}
          />
          <StatCard
            
            label="평균 5일 수익률"
            value={summary.avg_r_5d != null ? `${summary.avg_r_5d >= 0 ? '+' : ''}${summary.avg_r_5d.toFixed(2)}%` : '—'}
            sub={`10일: ${summary.avg_r_10d != null ? `${summary.avg_r_10d >= 0 ? '+' : ''}${summary.avg_r_10d.toFixed(2)}%` : '—'}`}
            valueColor={summary.avg_r_5d != null && summary.avg_r_5d > 0 ? 'text-red-400' : 'text-blue-400'}
          />
          <StatCard
            
            label="목표가 달성"
            value={String(summary.hit_target_cnt)}
            sub={`전체 ${summary.total}건 중`}
            valueColor="text-red-400"
          />
          <StatCard
            
            label="손절 발생"
            value={String(summary.hit_stop_cnt)}
            sub={`전체 ${summary.total}건 중`}
            valueColor="text-blue-400"
          />
        </div>
      )}

      {/* 이벤트별 성과 */}
      {summary?.by_event && summary.by_event.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>이벤트별 성과 ({days}일)</CardTitle>
          </CardHeader>
          <CardBody className="pt-3 px-0 pb-0">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-[var(--border)] text-[var(--muted)]">
                    <th className="text-left py-2.5 pl-5 pr-3 text-xs uppercase tracking-wider">이벤트</th>
                    <th className="text-right py-2.5 pr-4 text-xs uppercase tracking-wider">건수</th>
                    <th className="text-right py-2.5 pr-4 text-xs uppercase tracking-wider">승률</th>
                    <th className="text-right py-2.5 pr-5 text-xs uppercase tracking-wider">평균 5일 수익</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.by_event.map((ev) => (
                    <tr key={ev.event_type} className="border-b border-[var(--border)]/50 hover:bg-[var(--border)]/15 transition-colors">
                      <td className="py-2.5 pl-5 pr-3">
                        <Badge eventType={ev.event_type} size="sm" />
                        <span className="ml-2 text-xs text-[var(--muted)]">{EVENT_LABELS[ev.event_type] ?? ev.event_type}</span>
                      </td>
                      <td className="py-2.5 pr-4 text-right tabular text-sm text-[var(--fg)] font-semibold">{ev.cnt}</td>
                      <td className="py-2.5 pr-4 text-right">
                        {ev.win_rate != null ? (
                          <span className={clsx('tabular text-sm font-semibold', ev.win_rate >= 60 ? 'text-green-400' : ev.win_rate >= 45 ? 'text-yellow-400' : 'text-red-400')}>
                            {ev.win_rate.toFixed(1)}%
                          </span>
                        ) : <span className="text-[var(--muted)]">—</span>}
                      </td>
                      <td className="py-2.5 pr-5 text-right">
                        <RCell val={ev.avg_r5d} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardBody>
        </Card>
      )}

      {/* 추적 목록 */}
      <Card>
        <CardHeader className="flex items-center justify-between">
          <div>
            <CardTitle>추적 내역</CardTitle>
            <div className="text-sm text-[var(--muted)] mt-0.5">총 {list?.total ?? '…'}건 · 1h~10d 수익률 추적</div>
          </div>
          <div className="flex items-center gap-2">
            {([undefined, true, false] as Array<boolean | undefined>).map((v, i) => {
              const label = v === undefined ? '전체' : v ? '성공' : '실패'
              return (
                <button key={i} onClick={() => { setFilterSuccess(v); setPage(0) }} className={clsx(
                  'px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors',
                  filterSuccess === v
                    ? 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30'
                    : 'text-[var(--muted)] border-[var(--border)] hover:text-[var(--fg)]'
                )}>
                  {label}
                </button>
              )
            })}
          </div>
        </CardHeader>
        <CardBody className="pt-2 px-0 pb-0">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[var(--border)] text-[var(--muted)]">
                  <th className="text-left py-2.5 pl-5 pr-3 uppercase tracking-wider">종목</th>
                  <th className="text-left py-2.5 pr-3 uppercase tracking-wider">이벤트</th>
                  <th className="text-right py-2.5 pr-3 uppercase tracking-wider">진입가</th>
                  <th className="text-right py-2.5 pr-3 uppercase tracking-wider">1h</th>
                  <th className="text-right py-2.5 pr-3 uppercase tracking-wider">3h</th>
                  <th className="text-right py-2.5 pr-3 uppercase tracking-wider">1d</th>
                  <th className="text-right py-2.5 pr-3 uppercase tracking-wider">3d</th>
                  <th className="text-right py-2.5 pr-3 uppercase tracking-wider">5d</th>
                  <th className="text-right py-2.5 pr-3 uppercase tracking-wider">10d</th>
                  <th className="text-right py-2.5 pr-3 uppercase tracking-wider">최대</th>
                  <th className="text-center py-2.5 pr-3 uppercase tracking-wider">결과</th>
                  <th className="text-right py-2.5 pr-5 uppercase tracking-wider">신호시각</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={12} className="py-12 text-center text-[var(--muted)]">로딩 중...</td></tr>
                ) : (list?.items ?? []).length === 0 ? (
                  <tr><td colSpan={12} className="py-12 text-center text-[var(--muted)]">추적 데이터 없음</td></tr>
                ) : (list?.items ?? []).map((item: TrackingItem) => (
                  <tr key={item.id} className="border-b border-[var(--border)]/50 hover:bg-[var(--border)]/15 transition-colors">
                    <td className="py-2.5 pl-5 pr-3">
                      <div className="font-semibold text-[var(--fg)]">{item.name ?? item.code}</div>
                      <div className="text-[var(--muted)]">{item.code}</div>
                    </td>
                    <td className="py-2.5 pr-3">
                      {item.event_type ? <Badge eventType={item.event_type} size="sm" /> : <span className="text-[var(--muted)]">—</span>}
                    </td>
                    <td className="py-2.5 pr-3 text-right tabular text-[var(--fg)] font-semibold">{item.entry_price.toLocaleString()}</td>
                    <td className="py-2.5 pr-3 text-right"><RCell val={item.r_1h} /></td>
                    <td className="py-2.5 pr-3 text-right"><RCell val={item.r_3h} /></td>
                    <td className="py-2.5 pr-3 text-right"><RCell val={item.r_1d} /></td>
                    <td className="py-2.5 pr-3 text-right"><RCell val={item.r_3d} /></td>
                    <td className="py-2.5 pr-3 text-right"><RCell val={item.r_5d} /></td>
                    <td className="py-2.5 pr-3 text-right"><RCell val={item.r_10d} /></td>
                    <td className="py-2.5 pr-3 text-right">
                      {item.max_return != null ? (
                        <span className={clsx('tabular font-bold', item.max_return > 0 ? 'text-red-400' : 'text-blue-400')}>
                          {item.max_return >= 0 ? '+' : ''}{item.max_return.toFixed(1)}%
                        </span>
                      ) : <span className="text-[var(--muted)]">—</span>}
                    </td>
                    <td className="py-2.5 pr-3 text-center">
                      {!item.tracking_complete ? (
                        <span className="flex items-center justify-center gap-0.5 text-cyan-400">
                          <Clock size={11} />추적중
                        </span>
                      ) : item.is_success === true ? (
                        <span className="flex items-center justify-center gap-0.5 text-green-400">
                          <CheckCircle2 size={11} />성공
                        </span>
                      ) : item.is_success === false ? (
                        <span className="flex items-center justify-center gap-0.5 text-red-400">
                          <XCircle size={11} />실패
                        </span>
                      ) : (
                        <span className="text-[var(--muted)]">—</span>
                      )}
                    </td>
                    <td className="py-2.5 pr-5 text-right text-[var(--muted)]">{fmt.dateTime(item.signal_time)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* 페이징 */}
          {(list?.total ?? 0) > LIMIT && (
            <div className="flex items-center justify-center gap-3 py-4 border-t border-[var(--border)]">
              <button disabled={page === 0} onClick={() => setPage(p => p - 1)} className="px-3 py-1.5 rounded-lg text-xs border border-[var(--border)] text-[var(--muted)] hover:text-[var(--fg)] disabled:opacity-30">이전</button>
              <span className="text-xs text-[var(--muted)]">{page + 1} / {Math.ceil((list?.total ?? 0) / LIMIT)}</span>
              <button disabled={(page + 1) * LIMIT >= (list?.total ?? 0)} onClick={() => setPage(p => p + 1)} className="px-3 py-1.5 rounded-lg text-xs border border-[var(--border)] text-[var(--muted)] hover:text-[var(--fg)] disabled:opacity-30">다음</button>
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  )
}

