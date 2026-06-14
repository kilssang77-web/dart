import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { Filter, ArrowUpDown, ArrowUp, ArrowDown, TrendingUp, TrendingDown } from 'lucide-react'
import { disclosuresApi } from '@/api/disclosures'
import { SentimentBadge } from '@/components/ui/Badge'
import { fmt, pctColor } from '@/lib/utils'
import { DisclosureDetailModal } from '@/components/modals/DisclosureDetailModal'
import type { Disclosure } from '@/types'

type SortKey = 'disclosed_at' | 'sentiment_score' | 'post_1h_change' | 'post_1d_change' | 'post_3d_change' | 'contract_amount'

const SORT_LABELS: Record<SortKey, string> = {
  disclosed_at:    '공시시각',
  sentiment_score: '감성점수',
  post_1h_change:  '1H 등락',
  post_1d_change:  '1D 등락',
  post_3d_change:  '3D 등락',
  contract_amount: '금액',
}

const AMOUNT_OPTIONS = [
  { label: '전체', value: undefined },
  { label: '100억+', value: 100 },
  { label: '500억+', value: 500 },
  { label: '1000억+', value: 1000 },
  { label: '1조+', value: 10000 },
]

function SortIcon({ col, active, dir }: { col: string; active: string; dir: string }) {
  if (col !== active) return <ArrowUpDown size={11} className="opacity-40" />
  return dir === 'desc' ? <ArrowDown size={11} className="text-cyan-400" /> : <ArrowUp size={11} className="text-cyan-400" />
}

function SentimentScore({ score }: { score?: number | null }) {
  if (score == null) return <span className="text-[var(--muted)]">—</span>
  const color = score >= 0.3 ? 'text-green-400' : score <= -0.3 ? 'text-red-400' : 'text-[var(--muted)]'
  return <span className={clsx('font-semibold tabular', color)}>{score >= 0 ? '+' : ''}{score.toFixed(3)}</span>
}

function PctCell({ value }: { value?: number | null }) {
  if (value == null) return <span className="text-[var(--muted)]">—</span>
  return (
    <span className={clsx('font-semibold tabular flex items-center justify-end gap-0.5', pctColor(value))}>
      {value >= 0
        ? <TrendingUp size={10} />
        : <TrendingDown size={10} />}
      {fmt.pct(value)}
    </span>
  )
}

export function Disclosures() {
  const [corp,      setCorp]      = useState('')
  const [category,  setCategory]  = useState('')
  const [hours,     setHours]     = useState('72')
  const [sortBy,    setSortBy]    = useState<SortKey>('disclosed_at')
  const [sortDir,   setSortDir]   = useState<'asc' | 'desc'>('desc')
  const [minAmount, setMinAmount] = useState<number | undefined>(undefined)
  const [selected,  setSelected]  = useState<Disclosure | null>(null)

  const queryKey = ['disclosures', corp, category, hours, sortBy, sortDir, minAmount]

  const { data, isLoading } = useQuery({
    queryKey,
    queryFn: () => disclosuresApi.list({
      code:       corp || undefined,
      category:   category || undefined,
      hours:      Number(hours),
      limit:      200,
      sort_by:    sortBy,
      sort_dir:   sortDir,
      min_amount: minAmount,
    }),
    refetchInterval: 60_000,
  })

  const { data: stats } = useQuery({
    queryKey: ['disclosure-stats', hours],
    queryFn:  () => disclosuresApi.getStats(Number(hours)),
    staleTime: 120_000,
    refetchInterval: 120_000,
  })

  function toggleSort(col: SortKey) {
    if (sortBy === col) {
      setSortDir((d) => d === 'desc' ? 'asc' : 'desc')
    } else {
      setSortBy(col)
      setSortDir('desc')
    }
  }

  const favorableRatio = stats && stats.total > 0
    ? Math.round(stats.favorable / stats.total * 100) : 0

  return (
    <div className="p-5 space-y-4 max-w-[1600px]">

      {/* 통계 바 */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="p-3 bg-[var(--card)] border border-[var(--border)] rounded-xl">
            <div className="text-xs text-[var(--muted)] mb-1">전체 공시</div>
            <div className="text-xl font-bold text-[var(--fg)] tabular">{stats.total.toLocaleString()}</div>
          </div>
          <div className="p-3 bg-[var(--card)] border border-green-500/20 rounded-xl">
            <div className="text-xs text-[var(--muted)] mb-1">호재 ({favorableRatio}%)</div>
            <div className="text-xl font-bold text-green-400 tabular">{stats.favorable.toLocaleString()}</div>
          </div>
          <div className="p-3 bg-[var(--card)] border border-red-500/20 rounded-xl">
            <div className="text-xs text-[var(--muted)] mb-1">악재</div>
            <div className="text-xl font-bold text-red-400 tabular">{stats.unfavorable.toLocaleString()}</div>
          </div>
          <div className="p-3 bg-[var(--card)] border border-[var(--border)] rounded-xl">
            <div className="text-xs text-[var(--muted)] mb-1">평균 1일 영향</div>
            <div className={clsx('text-xl font-bold tabular', pctColor(stats.avg_1d_impact))}>
              {stats.avg_1d_impact >= 0 ? '+' : ''}{stats.avg_1d_impact.toFixed(2)}%
            </div>
          </div>
        </div>
      )}

      {/* 필터 바 */}
      <div className="flex flex-wrap items-center gap-2.5 p-4 bg-[var(--card)] border border-[var(--border)] rounded-xl">
        <Filter size={13} className="text-[var(--muted)]" />

        <input
          value={corp}
          onChange={(e) => setCorp(e.target.value)}
          placeholder="종목명 / 코드"
          className="bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-1.5 text-sm text-[var(--fg)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-500 w-36"
        />

        <select value={category} onChange={(e) => setCategory(e.target.value)}
          className="bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-1.5 text-sm text-[var(--fg)] focus:outline-none focus:border-cyan-500">
          <option value="">전체 분류</option>
          <option value="favorable">호재</option>
          <option value="unfavorable">악재</option>
          <option value="neutral">중립</option>
        </select>

        <select value={hours} onChange={(e) => setHours(e.target.value)}
          className="bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-1.5 text-sm text-[var(--fg)] focus:outline-none focus:border-cyan-500">
          <option value="12">12시간</option>
          <option value="24">24시간</option>
          <option value="48">48시간</option>
          <option value="72">72시간</option>
          <option value="168">1주</option>
        </select>

        <select value={minAmount ?? ''} onChange={(e) => setMinAmount(e.target.value ? Number(e.target.value) : undefined)}
          className="bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-1.5 text-sm text-[var(--fg)] focus:outline-none focus:border-cyan-500">
          {AMOUNT_OPTIONS.map((o) => (
            <option key={o.label} value={o.value ?? ''}>{o.label}</option>
          ))}
        </select>

        <button onClick={() => { setCorp(''); setCategory(''); setHours('72'); setSortBy('disclosed_at'); setSortDir('desc'); setMinAmount(undefined) }}
          className="text-xs text-[var(--muted)] hover:text-[var(--fg)] transition-colors px-2 py-1 rounded hover:bg-[var(--border)]">
          초기화
        </button>
        <div className="ml-auto text-sm text-[var(--muted)] font-medium">
          {isLoading ? '로딩 중…' : `${data?.length ?? 0}건`}
        </div>
      </div>

      {/* 테이블 */}
      <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border)] text-[var(--muted)] bg-[var(--bg)]/40">
                <th className="text-left py-3 pl-5 pr-3 text-xs font-semibold uppercase tracking-wider">종목명</th>
                <th className="text-left py-2.5 pr-3 text-xs font-semibold uppercase tracking-wider">공시 제목</th>
                <th className="text-center py-2.5 pr-3 text-xs font-semibold uppercase tracking-wider">분류</th>
                {(['sentiment_score', 'disclosed_at', 'contract_amount', 'post_1h_change', 'post_1d_change', 'post_3d_change'] as SortKey[]).map((col) => (
                  <th key={col}
                    onClick={() => toggleSort(col)}
                    className="py-2.5 px-3 text-xs font-semibold uppercase tracking-wider text-right cursor-pointer hover:text-[var(--fg)] select-none transition-colors">
                    <span className="flex items-center justify-end gap-1">
                      {SORT_LABELS[col]}
                      <SortIcon col={col} active={sortBy} dir={sortDir} />
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {isLoading && Array.from({ length: 8 }).map((_, i) => (
                <tr key={i} className="border-b border-[var(--border)]/50">
                  <td className="py-3 pl-5 pr-3"><div className="h-4 skeleton rounded w-20 mb-1" /><div className="h-3 skeleton rounded w-12" /></td>
                  <td className="py-3 pr-3"><div className="h-4 skeleton rounded w-48 mb-1.5" /><div className="h-3 skeleton rounded w-24" /></td>
                  <td className="py-3 pr-3 text-center"><div className="h-5 skeleton rounded w-12 mx-auto" /></td>
                  {[1,2,3,4,5,6].map((j) => (
                    <td key={j} className="py-3 pr-3 text-right"><div className="h-4 skeleton rounded w-14 ml-auto" /></td>
                  ))}
                </tr>
              ))}
              {data?.map((d) => (
                <tr key={d.id}
                  className="border-b border-[var(--border)]/50 hover:bg-[var(--border)]/25 cursor-pointer transition-colors"
                  onClick={() => setSelected(d)}>
                  <td className="py-3 pl-5 pr-3">
                    <div className="text-sm font-semibold text-[var(--fg)]">{d.corp_name ?? '—'}</div>
                    <div className="text-xs text-[var(--muted)] mt-0.5">{d.code ?? ''}</div>
                  </td>
                  <td className="py-2.5 pr-3 max-w-xs">
                    <div className="truncate text-sm text-[var(--fg)]" title={d.title}>{d.title}</div>
                    {d.keywords && d.keywords.length > 0 && (
                      <div className="flex gap-1 mt-1 flex-wrap">
                        {d.keywords.slice(0, 3).map((k) => (
                          <span key={k} className="text-xs px-1.5 py-0 rounded bg-[var(--border)] text-[var(--muted)]">{k}</span>
                        ))}
                      </div>
                    )}
                  </td>
                  <td className="py-2.5 pr-3 text-center"><SentimentBadge category={d.category} /></td>
                  <td className="py-2.5 pr-3 text-right"><SentimentScore score={d.sentiment_score} /></td>
                  <td className="py-2.5 pr-3 text-right tabular text-[var(--muted)] text-xs whitespace-nowrap">
                    {fmt.smartTime(d.disclosed_at)}
                  </td>
                  <td className="py-2.5 pr-3 text-right tabular text-[var(--muted)] text-xs">
                    {d.amount ? fmt.amount(d.amount) : '—'}
                  </td>
                  <td className="py-2.5 pr-3 text-right text-xs"><PctCell value={d.post_1h_change} /></td>
                  <td className="py-2.5 pr-3 text-right text-xs"><PctCell value={d.post_1d_change} /></td>
                  <td className="py-2.5 pr-5 text-right text-xs"><PctCell value={d.post_3d_change} /></td>
                </tr>
              ))}
              {!isLoading && !data?.length && (
                <tr>
                  <td colSpan={9} className="py-12 text-center text-[var(--muted)]">공시 데이터가 없습니다</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {selected && (
        <DisclosureDetailModal disclosure={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  )
}
