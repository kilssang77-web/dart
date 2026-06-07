import { useState, useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { ChevronUp, ChevronDown, Filter } from 'lucide-react'
import { featuresApi } from '@/api/features'
import { Badge, MarketBadge } from '@/components/ui/Badge'
import { fmt, pctColor } from '@/lib/utils'
import type { FeatureEvent } from '@/types'

type SortKey = 'detected_at' | 'change_rate' | 'signal_score' | 'volume_ratio'
type SortDir = 'asc' | 'desc'

const EVENT_TYPE_OPTIONS = [
  'VOLUME_SURGE', 'AMOUNT_SURGE', 'BREAKOUT_52W', 'BREAKOUT_26W',
  'BREAKOUT_13W', 'BREAKOUT_20D', 'VI_TRIGGERED', 'LONG_WHITE_CANDLE',
  'HAMMER_CANDLE', 'MORNING_STAR', 'SUPPLY_ANOMALY', 'POST_DISCLOSURE_SURGE',
]

export function Features() {
  const nav = useNavigate()
  const [searchParams] = useSearchParams()

  const [eventType, setEventType] = useState(searchParams.get('event_type') ?? '')
  const [market,    setMarket]    = useState('')
  const [minScore,  setMinScore]  = useState('')
  const [hours,     setHours]     = useState('24')
  const [query,     setQuery]     = useState('')
  const [sortKey,   setSortKey]   = useState<SortKey>('detected_at')
  const [sortDir,   setSortDir]   = useState<SortDir>('desc')

  const { data, isLoading } = useQuery({
    queryKey:       ['features', { eventType, market, minScore, hours }],
    queryFn:        () =>
      featuresApi.list({
        event_type: eventType || undefined,
        market:     market    || undefined,
        min_score:  minScore  ? Number(minScore) : undefined,
        hours:      Number(hours),
        limit:      300,
      }),
    refetchInterval: 30_000,
  })

  const rows = useMemo(() => {
    let list = (data ?? []) as FeatureEvent[]
    if (query) {
      const q = query.toLowerCase()
      list = list.filter((f) => f.name.toLowerCase().includes(q) || f.code.includes(q))
    }
    list = [...list].sort((a, b) => {
      let diff = 0
      if (sortKey === 'detected_at') diff = (a.detected_at ?? '').localeCompare(b.detected_at ?? '')
      if (sortKey === 'change_rate')  diff = (a.change_rate ?? 0) - (b.change_rate ?? 0)
      if (sortKey === 'signal_score') diff = (a.signal_score ?? 0) - (b.signal_score ?? 0)
      if (sortKey === 'volume_ratio') diff = (a.volume_ratio ?? 0) - (b.volume_ratio ?? 0)
      return sortDir === 'asc' ? diff : -diff
    })
    return list
  }, [data, query, sortKey, sortDir])

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  function SortIcon({ k }: { k: SortKey }) {
    if (sortKey !== k) return <span className="ml-0.5 opacity-30">↕</span>
    return sortDir === 'asc'
      ? <ChevronUp size={11} className="inline ml-0.5" />
      : <ChevronDown size={11} className="inline ml-0.5" />
  }

  return (
    <div className="p-6 space-y-4">

      {/* 필터 바 */}
      <div className="flex flex-wrap items-center gap-2 p-3 bg-[var(--card)] border border-[var(--border)] rounded-xl">
        <Filter size={13} className="text-[var(--muted)] flex-shrink-0" />

        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="종목명 / 코드 검색"
          className="bg-[var(--bg)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-xs text-[var(--fg)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-500 w-36"
        />

        <select
          value={eventType}
          onChange={(e) => setEventType(e.target.value)}
          className="bg-[var(--bg)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-xs text-[var(--fg)] focus:outline-none focus:border-cyan-500"
        >
          <option value="">모든 이벤트</option>
          {EVENT_TYPE_OPTIONS.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>

        <select
          value={market}
          onChange={(e) => setMarket(e.target.value)}
          className="bg-[var(--bg)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-xs text-[var(--fg)] focus:outline-none focus:border-cyan-500"
        >
          <option value="">전체 시장</option>
          <option value="KOSPI">KOSPI</option>
          <option value="KOSDAQ">KOSDAQ</option>
        </select>

        <select
          value={hours}
          onChange={(e) => setHours(e.target.value)}
          className="bg-[var(--bg)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-xs text-[var(--fg)] focus:outline-none focus:border-cyan-500"
        >
          <option value="4">4시간</option>
          <option value="8">8시간</option>
          <option value="24">24시간</option>
          <option value="48">48시간</option>
          <option value="168">1주</option>
        </select>

        <input
          value={minScore}
          onChange={(e) => setMinScore(e.target.value)}
          placeholder="최소 스코어"
          type="number"
          min="0"
          max="1"
          step="0.05"
          className="bg-[var(--bg)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-xs text-[var(--fg)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-500 w-24"
        />

        <div className="ml-auto text-xs text-[var(--muted)] tabular">
          {isLoading ? '로딩 중…' : `${rows.length}건`}
        </div>
      </div>

      {/* 테이블 */}
      <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-[var(--border)] text-[var(--muted)] bg-[var(--bg)]/40">
                <th className="text-left py-2.5 pl-5 pr-3 font-medium">종목</th>
                <th className="text-left py-2.5 pr-3 font-medium">이벤트</th>
                <th
                  className="text-right py-2.5 pr-3 font-medium cursor-pointer hover:text-[var(--fg)]"
                  onClick={() => handleSort('detected_at')}
                >
                  시각 <SortIcon k="detected_at" />
                </th>
                <th className="text-right py-2.5 pr-3 font-medium">현재가</th>
                <th
                  className="text-right py-2.5 pr-3 font-medium cursor-pointer hover:text-[var(--fg)]"
                  onClick={() => handleSort('change_rate')}
                >
                  등락률 <SortIcon k="change_rate" />
                </th>
                <th
                  className="text-right py-2.5 pr-3 font-medium cursor-pointer hover:text-[var(--fg)]"
                  onClick={() => handleSort('volume_ratio')}
                >
                  거래량비 <SortIcon k="volume_ratio" />
                </th>
                <th className="text-right py-2.5 pr-3 font-medium">거래대금</th>
                <th
                  className="text-right py-2.5 pr-5 font-medium cursor-pointer hover:text-[var(--fg)]"
                  onClick={() => handleSort('signal_score')}
                >
                  스코어 <SortIcon k="signal_score" />
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((f) => (
                <tr
                  key={f.id}
                  className="border-b border-[var(--border)]/50 hover:bg-[var(--border)]/25 cursor-pointer transition-colors"
                  onClick={() => nav(`/search?code=${f.code}`)}
                >
                  <td className="py-2.5 pl-5 pr-3">
                    <div className="font-semibold text-[var(--fg)]">{f.name}</div>
                    <div className="flex items-center gap-1 mt-0.5">
                      <span className="text-[var(--muted)]">{f.code}</span>
                      <MarketBadge market={f.market} />
                    </div>
                  </td>
                  <td className="py-2.5 pr-3">
                    <div className="flex flex-wrap gap-1">
                      <Badge eventType={f.event_type} size="sm" />
                      {f.all_event_types
                        ?.filter((t) => t !== f.event_type)
                        .slice(0, 2)
                        .map((t) => <Badge key={t} eventType={t} size="sm" />)}
                    </div>
                  </td>
                  <td className="py-2.5 pr-3 text-right tabular text-[var(--muted)]">
                    {fmt.time(f.detected_at)}
                  </td>
                  <td className="py-2.5 pr-3 text-right tabular text-[var(--fg)] font-medium">
                    {fmt.price(f.price)}
                  </td>
                  <td className={clsx('py-2.5 pr-3 text-right tabular font-semibold', pctColor(f.change_rate))}>
                    {fmt.pct(f.change_rate)}
                  </td>
                  <td className={clsx('py-2.5 pr-3 text-right tabular font-semibold',
                    (f.volume_ratio ?? 0) >= 5 ? 'text-yellow-400' :
                    (f.volume_ratio ?? 0) >= 2 ? 'text-cyan-400' : 'text-[var(--muted)]'
                  )}>
                    {f.volume_ratio != null ? `${f.volume_ratio.toFixed(1)}x` : '—'}
                  </td>
                  <td className="py-2.5 pr-3 text-right tabular text-[var(--muted)]">
                    {fmt.amount(f.amount)}
                  </td>
                  <td className="py-2.5 pr-5 text-right tabular">
                    <ScoreBar score={f.signal_score} />
                  </td>
                </tr>
              ))}
              {!isLoading && rows.length === 0 && (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-[var(--muted)]">
                    조건에 맞는 특징주가 없습니다
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function ScoreBar({ score }: { score?: number | null }) {
  if (score == null) return <span className="text-[var(--muted)]">—</span>
  const color =
    score >= 0.7 ? 'bg-green-400'  :
    score >= 0.5 ? 'bg-yellow-400' : 'bg-[var(--muted)]'
  return (
    <div className="flex items-center justify-end gap-2">
      <div className="w-16 h-1.5 bg-[var(--border)] rounded-full overflow-hidden">
        <div className={clsx('h-full rounded-full', color)} style={{ width: `${score * 100}%` }} />
      </div>
      <span className={clsx('font-semibold tabular min-w-[2.5rem] text-right',
        score >= 0.7 ? 'text-green-400' : score >= 0.5 ? 'text-yellow-400' : 'text-[var(--muted)]'
      )}>
        {score.toFixed(2)}
      </span>
    </div>
  )
}
