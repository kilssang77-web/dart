import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { clsx } from 'clsx'
import {
  FileText, Newspaper, Hash, Filter, TrendingUp, TrendingDown,
  ArrowUpDown, ArrowUp, ArrowDown, ExternalLink, ChevronDown, ChevronUp, BarChart2,
} from 'lucide-react'
import { disclosuresApi } from '@/api/disclosures'
import { newsApi } from '@/api/news'
import { marketApi } from '@/api/market'
import { SentimentBadge } from '@/components/ui/Badge'
import { fmt, pctColor } from '@/lib/utils'
import { DisclosureDetailModal } from '@/components/modals/DisclosureDetailModal'
import type { Disclosure } from '@/types'

type IntelTab = 'disclosures' | 'news' | 'themes'

// ── 공시 탭 ──────────────────────────────────────────────────────────────────
type DisclosureSortKey = 'disclosed_at' | 'sentiment_score' | 'post_1h_change' | 'post_1d_change'

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
      {value >= 0 ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
      {fmt.pct(value)}
    </span>
  )
}

function DisclosuresTab() {
  const [corp,     setCorp]     = useState('')
  const [category, setCategory] = useState('')
  const [hours,    setHours]    = useState('72')
  const [sortBy,   setSortBy]   = useState<DisclosureSortKey>('disclosed_at')
  const [sortDir,  setSortDir]  = useState<'asc' | 'desc'>('desc')
  const [selected, setSelected] = useState<Disclosure | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['disclosures-intel', corp, category, hours, sortBy, sortDir],
    queryFn: () => disclosuresApi.list({
      code:     corp || undefined,
      category: category || undefined,
      hours:    Number(hours),
      limit:    200,
      sort_by:  sortBy,
      sort_dir: sortDir,
    }),
    refetchInterval: 60_000,
  })

  const { data: stats } = useQuery({
    queryKey: ['disclosure-stats-intel', hours],
    queryFn:  () => disclosuresApi.getStats(Number(hours)),
    staleTime: 120_000,
    refetchInterval: 120_000,
  })

  function toggleSort(col: DisclosureSortKey) {
    if (sortBy === col) setSortDir((d) => d === 'desc' ? 'asc' : 'desc')
    else { setSortBy(col); setSortDir('desc') }
  }

  const favorableRatio = stats && stats.total > 0
    ? Math.round(stats.favorable / stats.total * 100) : 0

  return (
    <div className="space-y-4">
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
        <div className="flex rounded-lg overflow-hidden border border-[var(--border)]">
          {(['', 'favorable', 'unfavorable', 'neutral'] as const).map((c) => (
            <button key={c} onClick={() => setCategory(c)}
              className={clsx('px-3 py-1.5 text-xs font-medium transition-colors',
                category === c ? 'bg-cyan-500/20 text-cyan-400' : 'text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)]'
              )}>
              {c === '' ? '전체' : c === 'favorable' ? '호재' : c === 'unfavorable' ? '악재' : '중립'}
            </button>
          ))}
        </div>
        <select value={hours} onChange={(e) => setHours(e.target.value)}
          className="bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-1.5 text-sm text-[var(--fg)] focus:outline-none focus:border-cyan-500">
          <option value="24">24시간</option>
          <option value="72">72시간</option>
          <option value="168">1주</option>
        </select>
        <button onClick={() => { setCorp(''); setCategory(''); setHours('72'); setSortBy('disclosed_at'); setSortDir('desc') }}
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
                {(['sentiment_score', 'disclosed_at', 'post_1h_change', 'post_1d_change'] as DisclosureSortKey[]).map((col) => (
                  <th key={col} onClick={() => toggleSort(col)}
                    className="py-2.5 px-3 text-xs font-semibold uppercase tracking-wider text-right cursor-pointer hover:text-[var(--fg)] select-none transition-colors">
                    <span className="flex items-center justify-end gap-1">
                      {col === 'sentiment_score' ? '감성' : col === 'disclosed_at' ? '시각' : col === 'post_1h_change' ? '1H' : '1D'}
                      <SortIcon col={col} active={sortBy} dir={sortDir} />
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {isLoading && Array.from({ length: 6 }).map((_, i) => (
                <tr key={i} className="border-b border-[var(--border)]/50">
                  <td className="py-3 pl-5 pr-3"><div className="h-4 skeleton rounded w-20 mb-1" /><div className="h-3 skeleton rounded w-12" /></td>
                  <td className="py-3 pr-3"><div className="h-4 skeleton rounded w-48" /></td>
                  <td className="py-3 pr-3 text-center"><div className="h-5 skeleton rounded w-12 mx-auto" /></td>
                  {[1, 2, 3, 4].map((j) => <td key={j} className="py-3 pr-3 text-right"><div className="h-4 skeleton rounded w-14 ml-auto" /></td>)}
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
                  <td className="py-2.5 pr-3 text-right text-xs"><PctCell value={d.post_1h_change} /></td>
                  <td className="py-2.5 pr-5 text-right text-xs"><PctCell value={d.post_1d_change} /></td>
                </tr>
              ))}
              {!isLoading && !data?.length && (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-[var(--muted)]">공시 데이터가 없습니다</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {selected && <DisclosureDetailModal disclosure={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}

// ── 뉴스 탭 ──────────────────────────────────────────────────────────────────
function NewsTab() {
  const nav = useNavigate()
  const [category, setCategory] = useState('')
  const [hours,    setHours]    = useState('72')
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const { data: newsData, isLoading } = useQuery({
    queryKey: ['news-intel', category, hours],
    queryFn: () => newsApi.list({
      category: category || undefined,
      hours:    Number(hours),
      limit:    100,
    }),
    refetchInterval: 60_000,
  })

  const items = newsData ?? []

  return (
    <div className="space-y-4">
      {/* 필터 바 */}
      <div className="flex flex-wrap items-center gap-2 p-3 bg-[var(--card)] border border-[var(--border)] rounded-xl">
        <Newspaper size={13} className="text-[var(--muted)]" />
        <div className="flex rounded-lg overflow-hidden border border-[var(--border)]">
          {(['', 'favorable', 'unfavorable', 'neutral'] as const).map((c) => (
            <button key={c} onClick={() => setCategory(c)}
              className={clsx('px-3 py-1.5 text-xs font-medium transition-colors',
                category === c ? 'bg-cyan-500/20 text-cyan-400' : 'text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)]'
              )}>
              {c === '' ? '전체' : c === 'favorable' ? '긍정' : c === 'unfavorable' ? '부정' : '중립'}
            </button>
          ))}
        </div>
        <select value={hours} onChange={(e) => setHours(e.target.value)}
          className="bg-[var(--bg)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-xs text-[var(--fg)] focus:outline-none focus:border-cyan-500">
          <option value="24">24시간</option>
          <option value="72">72시간</option>
          <option value="168">1주</option>
        </select>
        <button onClick={() => { setCategory(''); setHours('72') }}
          className="text-xs text-[var(--muted)] hover:text-[var(--fg)] transition-colors px-2 py-1 rounded hover:bg-[var(--border)]">
          초기화
        </button>
        <div className="ml-auto text-xs text-[var(--muted)]">
          {isLoading ? '로딩 중…' : `${items.length}건`}
        </div>
      </div>

      {/* 뉴스 리스트 */}
      <div className="space-y-2">
        {isLoading && Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 space-y-3">
            <div className="h-4 skeleton rounded w-4/5" />
            <div className="flex gap-2 mt-2">
              <div className="h-3 skeleton rounded w-16" />
              <div className="h-3 skeleton rounded w-20" />
            </div>
          </div>
        ))}
        {items.map((item) => (
          <div key={item.id} className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 hover:border-cyan-500/30 transition-colors">
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="font-medium text-sm text-[var(--fg)] leading-snug">{item.title}</div>
                <div className="flex items-center flex-wrap gap-2 mt-2">
                  {item.codes && item.codes.length > 0 && (
                    <div className="flex gap-1 flex-wrap">
                      {item.codes.map((code) => (
                        <button key={code}
                          onClick={() => nav(`/search?code=${code}`)}
                          className="text-xs px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 hover:bg-cyan-500/20 transition-colors font-mono">
                          {code}
                        </button>
                      ))}
                    </div>
                  )}
                  {item.keywords?.slice(0, 3).map((k) => (
                    <span key={k} className="text-xs px-1.5 py-0.5 rounded bg-[var(--border)] text-[var(--muted)]">{k}</span>
                  ))}
                  <span className="text-xs text-[var(--muted)] ml-auto whitespace-nowrap">
                    {item.source && `${item.source} · `}{fmt.dateTime(item.published_at)}
                  </span>
                </div>
                {/* 감성 점수 */}
                {item.sentiment_score != null && (
                  <div className="text-xs text-[var(--muted)] mt-1">
                    감성{' '}
                    <span className={clsx('font-semibold tabular',
                      item.sentiment_score > 0 ? 'text-red-400' : item.sentiment_score < 0 ? 'text-blue-400' : 'text-[var(--muted)]')}>
                      {item.sentiment_score >= 0 ? '+' : ''}{item.sentiment_score.toFixed(3)}
                    </span>
                  </div>
                )}
              </div>
              <div className="flex flex-col items-end gap-2 flex-shrink-0">
                <SentimentBadge category={item.category} />
                {item.url && (
                  <a href={item.url} target="_blank" rel="noopener noreferrer"
                    className="flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300 transition-colors font-medium"
                    onClick={(e) => e.stopPropagation()}>
                    <ExternalLink size={10} />원문
                  </a>
                )}
              </div>
            </div>
            {/* 본문 접기 */}
            {item.content && (
              <div className="mt-2.5 pt-2 border-t border-[var(--border)]/50">
                <button onClick={() => setExpandedId(expandedId === item.id ? null : item.id)}
                  className="flex items-center gap-1 text-xs text-[var(--muted)] hover:text-cyan-400 transition-colors">
                  {expandedId === item.id ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                  {expandedId === item.id ? '접기' : '본문 보기'}
                </button>
                {expandedId === item.id && (
                  <p className="text-sm text-[var(--fg)] leading-relaxed mt-2">{item.content}</p>
                )}
              </div>
            )}
          </div>
        ))}
        {!isLoading && !items.length && (
          <div className="py-16 text-center text-[var(--muted)] text-sm">뉴스 데이터가 없습니다</div>
        )}
      </div>
    </div>
  )
}

// ── 테마 탭 ──────────────────────────────────────────────────────────────────
function ThemesTab() {
  const nav = useNavigate()

  const { data: themes, isLoading } = useQuery({
    queryKey:        ['themes-intel'],
    queryFn:         marketApi.getThemes,
    refetchInterval: 600_000,
  })

  // 중복 제거 + 상승 테마 우선 정렬
  const sortedThemes = useMemo(() => {
    if (!themes) return []
    const deduped = themes.filter((t, i, arr) => arr.findIndex((x) => x.theme === t.theme) === i)
    return [...deduped].sort((a, b) => {
      // avg_score 높은 순 정렬 (상승 테마 우선)
      return b.avg_score - a.avg_score
    })
  }, [themes])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-[var(--muted)]">뉴스 기반 K-Means 동적 테마 클러스터 · avg_score 높은 순</p>
        <span className="text-xs text-[var(--muted)]">{sortedThemes.length}개 테마</span>
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 space-y-3">
              <div className="h-4 skeleton rounded w-32" />
              <div className="h-3 skeleton rounded w-20" />
              <div className="h-3 skeleton rounded w-16" />
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {sortedThemes.map((theme) => {
          // 상승/하락/안정 추세 판단 (avg_score 기준)
          const trend = theme.avg_score >= 0.5 ? '상승' : theme.avg_score >= 0.3 ? '안정' : '하락'
          const trendColor = trend === '상승' ? 'text-red-400' : trend === '안정' ? 'text-yellow-400' : 'text-blue-400'
          const trendBg = trend === '상승' ? 'bg-red-500/10 border-red-500/20' : trend === '안정' ? 'bg-yellow-500/10 border-yellow-500/20' : 'bg-blue-500/10 border-blue-500/20'

          return (
            <div key={theme.theme}
              className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 hover:border-cyan-500/30 transition-colors">
              {/* 헤더 */}
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-1.5">
                  <Hash size={12} className={theme.source === 'news' ? 'text-cyan-400' : 'text-purple-400'} />
                  <span className="text-sm font-bold text-[var(--fg)]">{theme.theme}</span>
                </div>
                <span className={clsx('text-xs px-1.5 py-0.5 rounded border font-semibold', trendColor, trendBg)}>
                  {trend}
                </span>
              </div>

              {/* 메타 */}
              <div className="flex items-center justify-between text-xs text-[var(--muted)] mb-3">
                <span>종목 {theme.stock_count}개</span>
                <div className="flex items-center gap-1.5">
                  <BarChart2 size={10} />
                  <span className="tabular">avg {theme.avg_score.toFixed(2)}</span>
                </div>
              </div>

              {/* 타입 배지 + 건수 */}
              <div className="flex items-center justify-between">
                <span className={clsx('text-xs px-1.5 py-0.5 rounded border',
                  theme.source === 'news'
                    ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20'
                    : 'bg-purple-500/10 text-purple-400 border-purple-500/20'
                )}>
                  {theme.source === 'news' ? '뉴스 테마' : '섹터'}
                </span>
                <span className="text-xs text-[var(--muted)] tabular">{theme.count}건</span>
              </div>
            </div>
          )
        })}
        {!isLoading && !sortedThemes.length && (
          <div className="col-span-full py-16 text-center text-[var(--muted)] text-sm">테마 데이터가 없습니다</div>
        )}
      </div>
    </div>
  )
}

// ── 메인 Intel 페이지 ─────────────────────────────────────────────────────────
export function Intel() {
  const [activeTab, setActiveTab] = useState<IntelTab>('disclosures')

  const tabs: { key: IntelTab; label: string; icon: React.ReactNode }[] = [
    { key: 'disclosures', label: '공시', icon: <FileText size={14} /> },
    { key: 'news',        label: '뉴스', icon: <Newspaper size={14} /> },
    { key: 'themes',      label: '테마', icon: <Hash size={14} /> },
  ]

  return (
    <div className="p-5 space-y-5 max-w-[1600px]">
      {/* 탭 바 */}
      <div className="flex gap-1 bg-[var(--card)] border border-[var(--border)] rounded-xl p-1 w-fit">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={clsx(
              'flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg transition-colors',
              activeTab === tab.key
                ? 'bg-cyan-500/20 text-cyan-400'
                : 'text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)]'
            )}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* 탭 콘텐츠 */}
      {activeTab === 'disclosures' && <DisclosuresTab />}
      {activeTab === 'news'        && <NewsTab />}
      {activeTab === 'themes'      && <ThemesTab />}
    </div>
  )
}
