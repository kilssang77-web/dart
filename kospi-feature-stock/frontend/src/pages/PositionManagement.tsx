import { useQuery } from '@tanstack/react-query'
import { TrendingUp, TrendingDown, Clock, Target, ShieldOff } from 'lucide-react'
import { trackingApi, TrackingItem } from '@/api/tracking'

function pct(v?: number | null) {
  if (v == null) return '—'
  const sign = v >= 0 ? '+' : ''
  return `${sign}${v.toFixed(2)}%`
}

function statusColor(v?: number | null) {
  if (v == null) return 'text-[var(--muted)]'
  return v >= 0 ? 'text-green-400' : 'text-red-400'
}

function daysAgo(signal_time: string) {
  const diff = Date.now() - new Date(signal_time).getTime()
  return Math.floor(diff / 86_400_000)
}

function PositionRow({ item }: { item: TrackingItem }) {
  const days = daysAgo(item.signal_time)
  const latest = item.r_5d ?? item.r_3d ?? item.r_1d ?? null

  return (
    <tr className="border-b border-[var(--border)] hover:bg-[var(--border)]/30 transition-colors">
      <td className="px-4 py-3">
        <div className="font-semibold text-sm font-mono">{item.code}</div>
        <div className="text-xs text-[var(--fg)]/80 font-medium">{item.name ?? '—'}</div>
        <div className="text-xs text-[var(--muted)]">{item.event_type ?? '—'}</div>
      </td>
      <td className="px-4 py-3 text-right text-sm">
        {item.entry_price.toLocaleString()}원
      </td>
      <td className="px-4 py-3 text-right text-sm">
        <div className={statusColor(item.r_1d)}>{pct(item.r_1d)}</div>
      </td>
      <td className="px-4 py-3 text-right text-sm">
        <div className={statusColor(item.r_3d)}>{pct(item.r_3d)}</div>
      </td>
      <td className="px-4 py-3 text-right text-sm">
        <div className={statusColor(item.r_5d)}>{pct(item.r_5d)}</div>
      </td>
      <td className="px-4 py-3 text-right text-sm">
        <div className={`font-bold ${statusColor(latest)}`}>{pct(latest)}</div>
      </td>
      <td className="px-4 py-3 text-center text-sm">
        <div className="flex items-center justify-center gap-1 text-[var(--muted)]">
          <Clock size={12} />
          <span>{days}일</span>
        </div>
      </td>
      <td className="px-4 py-3 text-center">
        {item.hit_target ? (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-green-500/10 text-green-400">
            <Target size={10} /> 목표도달
          </span>
        ) : item.hit_stop ? (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-red-500/10 text-red-400">
            <ShieldOff size={10} /> 손절
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-cyan-500/10 text-cyan-400">
            추적 중
          </span>
        )}
      </td>
    </tr>
  )
}

function SummaryCard({ label, value, sub, positive }: { label: string; value: string; sub?: string; positive?: boolean }) {
  return (
    <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4">
      <div className="text-xs text-[var(--muted)] mb-1">{label}</div>
      <div className={`text-xl font-bold ${positive === true ? 'text-green-400' : positive === false ? 'text-red-400' : ''}`}>
        {value}
      </div>
      {sub && <div className="text-xs text-[var(--muted)] mt-0.5">{sub}</div>}
    </div>
  )
}

export function PositionManagement() {
  const { data: activeData, isLoading: activeLoading } = useQuery({
    queryKey: ['positions-active'],
    queryFn:  () => trackingApi.list({ complete: false, limit: 200 }),
    refetchInterval: 60_000,
  })

  const { data: summary } = useQuery({
    queryKey: ['tracking-summary-30'],
    queryFn:  () => trackingApi.summary(30),
    refetchInterval: 300_000,
  })

  const active = activeData?.items ?? []
  const winning = active.filter((p) => (p.r_5d ?? p.r_3d ?? p.r_1d ?? 0) > 0).length
  const losing  = active.filter((p) => (p.r_5d ?? p.r_3d ?? p.r_1d ?? 0) < 0).length

  return (
    <div className="p-6 space-y-6">
      {/* 헤더 요약 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <SummaryCard
          label="추적 중 포지션"
          value={String(active.length)}
          sub="미완료 추적 건"
        />
        <SummaryCard
          label="수익 / 손실"
          value={`${winning} / ${losing}`}
          sub="현재 수익 / 손실 건"
          positive={winning > losing}
        />
        <SummaryCard
          label="30일 성공률"
          value={summary ? `${summary.success_rate?.toFixed(1) ?? '—'}%` : '—'}
          sub={`완료 ${summary?.completed ?? 0}건`}
          positive={(summary?.success_rate ?? 0) >= 50}
        />
        <SummaryCard
          label="30일 평균 5일 수익"
          value={summary?.avg_r_5d != null ? pct(summary.avg_r_5d) : '—'}
          sub="추적 완료 기준"
          positive={(summary?.avg_r_5d ?? 0) >= 0}
        />
      </div>

      {/* 활성 포지션 테이블 */}
      <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border)]">
          <h2 className="font-semibold flex items-center gap-2">
            <TrendingUp size={16} className="text-cyan-400" />
            추적 중 포지션
            {active.length > 0 && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400">
                {active.length}건
              </span>
            )}
          </h2>
          <div className="text-xs text-[var(--muted)]">1분마다 갱신</div>
        </div>

        {activeLoading ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <tbody>
                {Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i} className="border-b border-[var(--border)]">
                    <td className="px-4 py-3">
                      <div className="h-4 skeleton rounded w-16 mb-1.5" />
                      <div className="h-3 skeleton rounded w-24 mb-1" />
                      <div className="h-3 skeleton rounded w-20" />
                    </td>
                    {Array.from({ length: 6 }).map((__, j) => (
                      <td key={j} className="px-4 py-3 text-right">
                        <div className="h-4 skeleton rounded w-14 ml-auto" />
                      </td>
                    ))}
                    <td className="px-4 py-3 text-center">
                      <div className="h-6 skeleton rounded-full w-20 mx-auto" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : active.length === 0 ? (
          <div className="py-12 text-center text-[var(--muted)] text-sm">
            <TrendingDown size={32} className="mx-auto mb-3 opacity-30" />
            <div>현재 추적 중인 포지션이 없습니다</div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] text-[var(--muted)] text-xs">
                  <th className="px-4 py-3 text-left">종목코드 / 종목명</th>
                  <th className="px-4 py-3 text-right">진입가</th>
                  <th className="px-4 py-3 text-right">1일</th>
                  <th className="px-4 py-3 text-right">3일</th>
                  <th className="px-4 py-3 text-right">5일</th>
                  <th className="px-4 py-3 text-right">현재</th>
                  <th className="px-4 py-3 text-center">경과</th>
                  <th className="px-4 py-3 text-center">상태</th>
                </tr>
              </thead>
              <tbody>
                {active.map((item) => (
                  <PositionRow key={item.id} item={item} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
