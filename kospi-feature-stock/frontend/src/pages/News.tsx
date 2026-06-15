import { useState, useCallback, useRef, useEffect } from 'react'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { clsx } from 'clsx'
import { Hash, Newspaper, BarChart2, ChevronDown, ChevronUp, ExternalLink, RefreshCw, Link2 } from 'lucide-react'
import { newsApi, type NewsItem } from '@/api/news'
import { marketApi } from '@/api/market'
import { SentimentBadge } from '@/components/ui/Badge'
import { fmt } from '@/lib/utils'
import { ErrorState } from '@/components/ui/ErrorState'

const PAGE_SIZE = 30

function NewsCard({
  item,
  isExpanded,
  onToggle,
  onCodeClick,
}: {
  item: NewsItem
  isExpanded: boolean
  onToggle: () => void
  onCodeClick: (code: string) => void
}) {
  const { data: similar, isLoading: simLoading } = useQuery({
    queryKey:  ['news-similar', item.id],
    queryFn:   () => newsApi.getSimilar(item.id),
    enabled:   isExpanded,
    staleTime: 600_000,
    retry:     false,
  })

  return (
    <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 hover:border-cyan-500/30 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="font-medium text-sm text-[var(--fg)] leading-snug">{item.title}</div>
          <div className="flex items-center flex-wrap gap-2 mt-2">
            {/* 모든 종목 코드 표시 */}
            {item.codes && item.codes.length > 0 && (
              <div className="flex gap-1 flex-wrap">
                {item.codes.map((code) => (
                  <button key={code}
                    onClick={() => onCodeClick(code)}
                    className="text-xs px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 hover:bg-cyan-500/20 transition-colors font-mono">
                    {code}
                  </button>
                ))}
              </div>
            )}
            {item.corp_name && !item.codes?.length && (
              <span className="text-xs font-medium text-cyan-400">{item.corp_name}</span>
            )}
            {item.keywords?.slice(0, 3).map((k) => (
              <span key={k} className="text-xs px-1.5 py-0.5 rounded bg-[var(--border)] text-[var(--muted)]">{k}</span>
            ))}
            <span className="text-xs text-[var(--muted)] ml-auto whitespace-nowrap">
              {item.source && `${item.source} · `}{fmt.dateTime(item.published_at)}
            </span>
          </div>
        </div>
        <div className="flex-shrink-0"><SentimentBadge category={item.category} /></div>
      </div>

      {/* 확장 본문 */}
      {isExpanded && (
        <div className="mt-3 pt-3 border-t border-[var(--border)] space-y-3">
          {item.content ? (
            <p className="text-sm text-[var(--fg)] leading-relaxed">{item.content}</p>
          ) : (
            <p className="text-sm text-[var(--muted)] italic">본문 미저장 — 원문보기로 전체 기사를 확인하세요.</p>
          )}
          {item.keywords && item.keywords.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {item.keywords.map((k) => (
                <span key={k} className="text-xs px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">{k}</span>
              ))}
            </div>
          )}
          {item.sentiment_score != null && (
            <div className="text-xs text-[var(--muted)]">
              감성 점수{' '}
              <span className={clsx('font-semibold tabular',
                item.sentiment_score > 0 ? 'text-red-400' : item.sentiment_score < 0 ? 'text-blue-400' : 'text-[var(--muted)]')}>
                {item.sentiment_score >= 0 ? '+' : ''}{item.sentiment_score.toFixed(3)}
              </span>
            </div>
          )}
          {/* 유사 뉴스 */}
          {simLoading ? (
            <div className="h-8 skeleton rounded" />
          ) : similar && similar.length > 0 && (
            <div className="border-t border-[var(--border)]/60 pt-2 space-y-1">
              <div className="flex items-center gap-1 text-xs font-semibold text-[var(--muted)] mb-1.5">
                <Link2 size={10} /> 유사 뉴스
              </div>
              {similar.map((s) => (
                <div key={s.id} className="flex items-center justify-between gap-2 text-xs py-1 px-2 rounded bg-[var(--bg)] hover:bg-[var(--border)] transition-colors">
                  <span className="text-[var(--fg)] truncate">{s.title}</span>
                  <div className="flex items-center gap-2 shrink-0">
                    <SentimentBadge category={s.category} />
                    <span className="text-[var(--muted)]">{fmt.dateTime(s.published_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="flex items-center gap-2 mt-2.5 pt-2 border-t border-[var(--border)]/50">
        <button onClick={onToggle}
          className="flex items-center gap-1 text-xs text-[var(--muted)] hover:text-cyan-400 transition-colors">
          {isExpanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
          {isExpanded ? '접기' : '자세히보기'}
        </button>
        {item.url && (
          <a href={item.url} target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300 transition-colors ml-auto font-medium"
            onClick={(e) => e.stopPropagation()}>
            <ExternalLink size={10} />원문보기
          </a>
        )}
      </div>
    </div>
  )
}

export function News() {
  const nav = useNavigate()
  const [category, setCategory]     = useState('')
  const [hours,    setHours]        = useState('72')
  const [source,   setSource]       = useState('')
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [themeFilter, setThemeFilter] = useState<string | null>(null)
  const loaderRef = useRef<HTMLDivElement>(null)

  const {
    data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading: newsLoading,
    isError: newsError, error: newsErrorObj, refetch: refetchNews,
  } = useInfiniteQuery({
    queryKey:  ['news-infinite', category, hours, source, themeFilter],
    queryFn:   ({ pageParam = 0 }) =>
      newsApi.list({
        category: category || undefined,
        hours:    Number(hours),
        source:   source || undefined,
        limit:    PAGE_SIZE,
        offset:   pageParam as number,
      }),
    getNextPageParam: (lastPage, pages) =>
      lastPage.length === PAGE_SIZE ? pages.length * PAGE_SIZE : undefined,
    initialPageParam: 0,
    refetchInterval: 60_000,
  })

  const { data: themes } = useQuery({
    queryKey:        ['themes'],
    queryFn:         marketApi.getThemes,
    refetchInterval: 600_000,
  })

  const { data: sources = [] } = useQuery({
    queryKey: ['news-sources', hours],
    queryFn:  () => newsApi.getSources(Number(hours)),
    staleTime: 300_000,
  })

  const allNews: NewsItem[] = data?.pages.flat() ?? []
  const totalCount = allNews.length

  // IntersectionObserver for infinite scroll
  useEffect(() => {
    if (!loaderRef.current) return
    const obs = new IntersectionObserver(
      (entries) => { if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) fetchNextPage() },
      { threshold: 0.1 },
    )
    obs.observe(loaderRef.current)
    return () => obs.disconnect()
  }, [fetchNextPage, hasNextPage, isFetchingNextPage])

  const handleCodeClick = useCallback((code: string) => {
    nav(`/search?code=${code}`)
  }, [nav])

  return (
    <div className="p-6 space-y-4">

      {/* 필터 바 */}
      <div className="flex flex-wrap items-center gap-2 p-3 bg-[var(--card)] border border-[var(--border)] rounded-xl">
        <Newspaper size={13} className="text-[var(--muted)]" />
        <div className="flex rounded-lg overflow-hidden border border-[var(--border)]">
          {(['', 'favorable', 'unfavorable', 'neutral'] as const).map((c) => (
            <button key={c} onClick={() => setCategory(c)}
              className={clsx(
                'px-3 py-1.5 text-xs font-medium transition-colors',
                category === c
                  ? 'bg-cyan-500/20 text-cyan-400'
                  : 'text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)]',
              )}>
              {c === '' ? '전체' : c === 'favorable' ? '호재' : c === 'unfavorable' ? '악재' : '중립'}
            </button>
          ))}
        </div>

        <select value={hours} onChange={(e) => setHours(e.target.value)}
          className="bg-[var(--bg)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-xs text-[var(--fg)] focus:outline-none focus:border-cyan-500">
          <option value="8">8시간</option>
          <option value="24">24시간</option>
          <option value="48">48시간</option>
          <option value="72">72시간</option>
          <option value="168">1주</option>
        </select>

        {sources.length > 0 && (
          <select value={source} onChange={(e) => setSource(e.target.value)}
            className="bg-[var(--bg)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-xs text-[var(--fg)] focus:outline-none focus:border-cyan-500">
            <option value="">전체 소스</option>
            {sources.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        )}

        <button onClick={() => { setCategory(''); setHours('72'); setSource(''); setThemeFilter(null) }}
          className="text-xs text-[var(--muted)] hover:text-[var(--fg)] transition-colors px-2 py-1 rounded hover:bg-[var(--border)]">
          초기화
        </button>

        {themeFilter && (
          <span className="flex items-center gap-1 px-2 py-1 rounded-full bg-purple-500/15 text-purple-400 border border-purple-500/30 text-xs">
            #{themeFilter}
            <button onClick={() => setThemeFilter(null)} className="ml-0.5 hover:text-white">×</button>
          </span>
        )}

        <div className="ml-auto text-xs text-[var(--muted)]">
          {newsLoading ? '로딩 중…' : `${totalCount}건 표시`}
          {hasNextPage && <span className="ml-1 text-cyan-400">↓ 더보기</span>}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* 뉴스 피드 */}
        <div className="lg:col-span-2 space-y-2">
          {newsError && <ErrorState error={newsErrorObj as Error} retry={refetchNews} />}
          {newsLoading && Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 space-y-3">
              <div className="h-4 skeleton rounded w-4/5" />
              <div className="h-4 skeleton rounded w-3/5" />
              <div className="flex gap-2 mt-2">
                <div className="h-3 skeleton rounded w-16" />
                <div className="h-3 skeleton rounded w-20" />
              </div>
            </div>
          ))}

          {allNews.map((item) => (
            <NewsCard key={item.id} item={item}
              isExpanded={expandedId === item.id}
              onToggle={() => setExpandedId(expandedId === item.id ? null : item.id)}
              onCodeClick={handleCodeClick}
            />
          ))}

          {/* 무한 스크롤 트리거 */}
          <div ref={loaderRef} className="py-2 text-center">
            {isFetchingNextPage && (
              <div className="flex items-center justify-center gap-2 text-xs text-[var(--muted)]">
                <RefreshCw size={12} className="animate-spin" /> 불러오는 중…
              </div>
            )}
            {!hasNextPage && totalCount > 0 && (
              <p className="text-xs text-[var(--muted)]">모든 뉴스를 불러왔습니다</p>
            )}
          </div>

          {!newsLoading && !newsError && !allNews.length && (
            <div className="py-16 text-center text-[var(--muted)] text-sm">뉴스 데이터가 없습니다</div>
          )}
        </div>

        {/* 테마 클러스터 사이드바 */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-[var(--fg)]">
            <Hash size={14} className="text-cyan-400" /> 테마 클러스터
          </div>
          {themes?.filter((t, i, arr) => arr.findIndex((x) => x.theme === t.theme) === i).map((theme) => (
            <button key={theme.theme}
              onClick={() => setThemeFilter(themeFilter === theme.theme ? null : theme.theme)}
              className={clsx(
                'w-full text-left bg-[var(--card)] border rounded-xl p-3.5 transition-colors',
                themeFilter === theme.theme
                  ? 'border-purple-500/50 bg-purple-500/5'
                  : 'border-[var(--border)] hover:border-cyan-500/30',
              )}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-1.5">
                  <Hash size={11} className={theme.source === 'news' ? 'text-cyan-400' : 'text-purple-400'} />
                  <span className="text-xs font-semibold text-[var(--fg)]">{theme.theme}</span>
                </div>
                <span className="text-xs tabular text-[var(--muted)]">{theme.count}건</span>
              </div>
              <div className="flex items-center justify-between text-xs text-[var(--muted)]">
                <span>종목 {theme.stock_count}개</span>
                <div className="flex items-center gap-1.5">
                  <BarChart2 size={9} />
                  <span>avg {theme.avg_score.toFixed(2)}</span>
                </div>
              </div>
              <div className="mt-2">
                <span className={clsx(
                  'text-xs px-1.5 py-0.5 rounded border',
                  theme.source === 'news'
                    ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20'
                    : 'bg-purple-500/10 text-purple-400 border-purple-500/20',
                )}>
                  {theme.source === 'news' ? '뉴스 테마' : '섹터'}
                </span>
              </div>
            </button>
          ))}
          {!themes?.length && (
            <div className="py-8 text-center text-xs text-[var(--muted)]">테마 클러스터 없음</div>
          )}
        </div>
      </div>
    </div>
  )
}
