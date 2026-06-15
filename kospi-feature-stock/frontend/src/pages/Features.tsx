import { useState, useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { ChevronUp, ChevronDown, Filter, Zap, TrendingUp, ArrowUpRight, Users, FileText, CandlestickChart } from 'lucide-react'
import { featuresApi } from '@/api/features'
import { Badge, MarketBadge, EVENT_LABELS } from '@/components/ui/Badge'
import { EventDetailModal } from '@/components/modals/EventDetailModal'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { DataFreshness } from '@/components/ui/DataFreshness'
import { fmt, pctColor } from '@/lib/utils'
import type { FeatureEvent } from '@/types'

// ── 이벤트 타입 아이콘 ──────────────────────────────────────────────────────
const EVENT_ICONS: Record<string, React.ReactNode> = {
  VOLUME_SURGE:          <TrendingUp size={14} className="text-blue-400" />,
  AMOUNT_SURGE:          <TrendingUp size={14} className="text-purple-400" />,
  BREAKOUT_52W:          <ArrowUpRight size={14} className="text-green-400" />,
  BREAKOUT_26W:          <ArrowUpRight size={14} className="text-green-400" />,
  BREAKOUT_13W:          <ArrowUpRight size={14} className="text-green-400" />,
  BREAKOUT_20D:          <ArrowUpRight size={14} className="text-green-400" />,
  VI_TRIGGERED:          <Zap size={14} className="text-yellow-400" />,
  LONG_WHITE_CANDLE:     <CandlestickChart size={14} className="text-orange-400" />,
  SUPPLY_ANOMALY:        <Users size={14} className="text-cyan-400" />,
  POST_DISCLOSURE_SURGE: <FileText size={14} className="text-pink-400" />,
}

function isRecent(isoDate?: string | null): boolean {
  if (!isoDate) return false
  return new Date().getTime() - new Date(isoDate).getTime() < 5 * 60 * 1000
}

type SortKey = 'detected_at' | 'change_rate' | 'signal_score' | 'volume_ratio'
type SortDir = 'asc' | 'desc'

const EVENT_TYPE_OPTIONS = [
  'VOLUME_SURGE', 'AMOUNT_SURGE', 'BREAKOUT_52W', 'BREAKOUT_26W',
  'BREAKOUT_13W', 'BREAKOUT_20D', 'VI_TRIGGERED', 'LONG_WHITE_CANDLE',
  'HAMMER_CANDLE', 'MORNING_STAR', 'SUPPLY_ANOMALY', 'POST_DISCLOSURE_SURGE',
  'SHORT_SURGE', 'DUAL_BUY_STREAK',
]



// ── 메인 페이지 ─────────────────────────────────────────────────────────────
export function Features() {
  const nav = useNavigate()
  const [searchParams] = useSearchParams()

  const [eventType,      setEventType]      = useState(searchParams.get('event_type') ?? '')
  const [market,         setMarket]         = useState('')
  const [minScore,       setMinScore]       = useState('')
  const [hours,          setHours]          = useState('72')
  const [query,          setQuery]          = useState('')
  const [dedupe,         setDedupe]         = useState(true)
  const [sortKey,        setSortKey]        = useState<SortKey>('detected_at')
  const [sortDir,        setSortDir]        = useState<SortDir>('desc')
  const [selectedEvent,  setSelectedEvent]  = useState<FeatureEvent | null>(null)

  const { data, isLoading, isError, error, refetch, dataUpdatedAt } = useQuery({
    queryKey:        ['features', { eventType, market, minScore, hours, dedupe }],
    queryFn:         () =>
      featuresApi.list({
        event_type: eventType || undefined,
        market:     market    || undefined,
        min_score:  minScore  ? Number(minScore) : undefined,
        hours:      Number(hours),
        limit:      300,
        dedupe,
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
    <div className="p-5 space-y-4 max-w-[1600px]">

      {/* 필터 바 */}
      <div className="flex flex-wrap items-center gap-3 p-4 bg-[var(--card)] border border-[var(--border)] rounded-xl">
        <Filter size={13} className="text-[var(--muted)] flex-shrink-0" />

        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="종목명 / 코드 검색"
          className="bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-[var(--fg)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-500 w-40"
        />

        <select
          value={eventType}
          onChange={(e) => setEventType(e.target.value)}
          className="bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-[var(--fg)] focus:outline-none focus:border-cyan-500"
        >
          <option value="">모든 이벤트</option>
          {EVENT_TYPE_OPTIONS.map((t) => (
            <option key={t} value={t}>{EVENT_LABELS[t] ?? t}</option>
          ))}
        </select>

        <select
          value={market}
          onChange={(e) => setMarket(e.target.value)}
          className="bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-[var(--fg)] focus:outline-none focus:border-cyan-500"
        >
          <option value="">전체 시장</option>
          <option value="KOSPI">KOSPI</option>
          <option value="KOSDAQ">KOSDAQ</option>
        </select>

        <select
          value={hours}
          onChange={(e) => setHours(e.target.value)}
          className="bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-[var(--fg)] focus:outline-none focus:border-cyan-500"
        >
          <option value="4">4시간</option>
          <option value="8">8시간</option>
          <option value="24">24시간</option>
          <option value="48">48시간</option>
          <option value="72">72시간</option>
          <option value="168">1주</option>
        </select>

        <input
          value={minScore}
          onChange={(e) => setMinScore(e.target.value)}
          placeholder="최소 스코어"
          type="number" min="0" max="1" step="0.05"
          className="bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-[var(--fg)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-500 w-28"
        />

        <button
          onClick={() => setDedupe((v) => !v)}
          className={clsx(
            'flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium border transition-colors',
            dedupe
              ? 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30'
              : 'text-[var(--muted)] border-[var(--border)] hover:text-[var(--fg)]',
          )}
          title={dedupe ? '종목 통합 ON' : '전체 이벤트 표시 중'}
        >
          {dedupe ? '종목 통합' : '전체 이벤트'}
        </button>

        <button
          onClick={() => { setQuery(''); setEventType(''); setMarket(''); setHours('72'); setMinScore('') }}
          className="ml-auto text-xs text-[var(--muted)] hover:text-[var(--fg)] transition-colors px-2 py-1 rounded hover:bg-[var(--border)]"
        >
          초기화
        </button>
        <div className="flex items-center gap-2 text-sm text-[var(--muted)] tabular font-medium">
          {isLoading ? '로딩 중…' : `${rows.length}건`}
          {dataUpdatedAt > 0 && <DataFreshness updatedAt={dataUpdatedAt} staleAfterMs={60_000} />}
        </div>
      </div>

      {/* 테이블 */}
      <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border)] text-[var(--muted)] bg-[var(--bg)]/40">
                <th className="text-left py-2.5 pl-5 pr-3 text-xs font-semibold uppercase tracking-wider">종목</th>
                <th className="text-left py-2.5 pr-3 text-xs font-semibold uppercase tracking-wider">
                  이벤트 <span className="normal-case font-normal text-[var(--muted)]/70">(클릭 시 상세)</span>
                </th>
                <th className="text-right py-2.5 pr-3 text-xs font-semibold uppercase tracking-wider cursor-pointer hover:text-[var(--fg)]" onClick={() => handleSort('detected_at')}>
                  시각 <SortIcon k="detected_at" />
                </th>
                <th className="text-right py-2.5 pr-3 text-xs font-semibold uppercase tracking-wider">
                  탐지가 <span className="normal-case font-normal text-[var(--muted)]/70 text-[10px]">탐지 당시</span>
                </th>
                <th className="text-right py-2.5 pr-3 text-xs font-semibold uppercase tracking-wider cursor-pointer hover:text-[var(--fg)]" onClick={() => handleSort('change_rate')}>
                  등락률 <SortIcon k="change_rate" />
                </th>
                <th className="text-right py-2.5 pr-3 text-xs font-semibold uppercase tracking-wider cursor-pointer hover:text-[var(--fg)]" onClick={() => handleSort('volume_ratio')}>
                  거래량비 <SortIcon k="volume_ratio" />
                </th>
                <th className="text-right py-2.5 pr-3 text-xs font-semibold uppercase tracking-wider">거래대금</th>
                <th className="text-right py-2.5 pr-5 text-xs font-semibold uppercase tracking-wider cursor-pointer hover:text-[var(--fg)]" onClick={() => handleSort('signal_score')}>
                  스코어 <SortIcon k="signal_score" />
                </th>
              </tr>
            </thead>
            <tbody>
              {isLoading && Array.from({ length: 8 }).map((_, i) => (
                <tr key={i} className="border-b border-[var(--border)]/50">
                  <td className="py-3 pl-5 pr-3">
                    <div className="h-4 skeleton rounded w-24 mb-1.5" />
                    <div className="h-3 skeleton rounded w-14" />
                  </td>
                  <td className="py-3 pr-3"><div className="h-5 skeleton rounded w-28" /></td>
                  <td className="py-3 pr-3 text-right"><div className="h-4 skeleton rounded w-14 ml-auto" /></td>
                  <td className="py-3 pr-3 text-right"><div className="h-4 skeleton rounded w-16 ml-auto" /></td>
                  <td className="py-3 pr-3 text-right"><div className="h-4 skeleton rounded w-12 ml-auto" /></td>
                  <td className="py-3 pr-3 text-right"><div className="h-4 skeleton rounded w-10 ml-auto" /></td>
                  <td className="py-3 pr-3 text-right"><div className="h-4 skeleton rounded w-14 ml-auto" /></td>
                  <td className="py-3 pr-5 text-right"><div className="h-5 skeleton rounded w-20 ml-auto" /></td>
                </tr>
              ))}
              {rows.map((f) => {
                const recent = isRecent(f.detected_at)
                return (
                <tr
                  key={f.id}
                  className={clsx(
                    'border-b border-[var(--border)]/50 hover:bg-[var(--border)]/25 cursor-pointer transition-colors',
                    recent && 'bg-green-500/5 border-l-2 border-l-green-500/60',
                  )}
                  onClick={() => nav(`/search?code=${f.code}`)}
                >
                  <td className="py-3 pl-5 pr-3">
                    <div className="flex items-center gap-1.5">
                      {EVENT_ICONS[f.event_type] ?? <Zap size={14} className="text-[var(--muted)]" />}
                      <div>
                        <div className="text-sm font-semibold text-[var(--fg)]">{f.name}</div>
                        <div className="flex items-center gap-1 mt-0.5">
                          <span className="text-[var(--muted)]">{f.code}</span>
                          <MarketBadge market={f.market} />
                        </div>
                      </div>
                    </div>
                  </td>
                  {/* 이벤트 셀: 클릭 시 팝업 (행 이동 막음) */}
                  <td
                    className="py-3 pr-3"
                    onClick={(e) => { e.stopPropagation(); setSelectedEvent(f) }}
                  >
                    <div className="flex flex-wrap items-center gap-1 group">
                      <span className="group-hover:ring-1 group-hover:ring-cyan-500/50 rounded transition-all">
                        <Badge eventType={f.event_type} size="sm" />
                      </span>
                      {f.all_event_types
                        ?.filter((t) => t !== f.event_type)
                        .slice(0, 2)
                        .map((t) => <Badge key={t} eventType={t} size="sm" />)}
                      {(f.all_event_types?.length ?? 0) > 3 && (
                        <span className="text-xs px-1 py-0.5 rounded bg-[var(--border)] text-[var(--muted)] font-semibold">
                          +{f.all_event_types!.length - 3}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className={clsx('py-2.5 pr-3 text-right tabular', recent ? 'text-green-400 font-semibold' : 'text-[var(--muted)]')}>
                    {recent ? '방금' : fmt.smartTime(f.detected_at)}
                  </td>
                  <td className="py-2.5 pr-3 text-right tabular text-[var(--fg)] font-medium">
                    {fmt.price(f.price)}
                  </td>
                  <td className={clsx('py-3 pr-3 text-right tabular font-semibold', pctColor(f.change_rate))}>
                    {fmt.pct(f.change_rate)}
                  </td>
                  <td className={clsx('py-3 pr-3 text-right tabular font-semibold',
                    (f.volume_ratio ?? 0) >= 5 ? 'text-yellow-400' :
                    (f.volume_ratio ?? 0) >= 2 ? 'text-cyan-400' : 'text-[var(--muted)]'
                  )}>
                    {f.volume_ratio != null ? `${f.volume_ratio.toFixed(1)}x` : '—'}
                  </td>
                  <td className="py-2.5 pr-3 text-right tabular text-[var(--muted)]">
                    {fmt.amount(f.amount)}
                  </td>
                  <td className="py-3 pr-5 text-right tabular">
                    <ScoreBar score={f.signal_score} />
                  </td>
                </tr>
                )
              })}
              {isError && (
                <tr>
                  <td colSpan={8} className="py-8">
                    <ErrorState error={error as Error} retry={refetch} />
                  </td>
                </tr>
              )}
              {!isLoading && !isError && rows.length === 0 && (
                <tr>
                  <td colSpan={8}>
                    <EmptyState
                      icon={Zap}
                      title="탐지된 특징주 없음"
                      description="선택한 조건에 맞는 특징주가 없습니다. 기간이나 필터를 조정해보세요."
                    />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 이벤트 상세 팝업 */}
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
