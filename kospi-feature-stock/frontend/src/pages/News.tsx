import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { clsx } from 'clsx'
import { Hash, Newspaper, BarChart2, ChevronDown, ChevronUp, ExternalLink } from 'lucide-react'
import { newsApi } from '@/api/news'
import { marketApi } from '@/api/market'
import { SentimentBadge } from '@/components/ui/Badge'
import { fmt } from '@/lib/utils'

export function News() {
  const nav = useNavigate()
  const [category, setCategory] = useState('')
  const [hours,    setHours]    = useState('72')
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const { data: newsList, isLoading: newsLoading } = useQuery({
    queryKey:        ['news', category, hours],
    queryFn:         () => newsApi.list({ category: category || undefined, hours: Number(hours), limit: 100 }),
    refetchInterval: 60_000,
  })

  const { data: themes, isLoading: themesLoading } = useQuery({
    queryKey:        ['themes'],
    queryFn:         marketApi.getThemes,
    refetchInterval: 600_000,
  })

  return (
    <div className="p-6 space-y-4">

      {/* 필터 */}
      <div className="flex flex-wrap items-center gap-2 p-3 bg-[var(--card)] border border-[var(--border)] rounded-xl">
        <Newspaper size={13} className="text-[var(--muted)]" />
        <div className="flex rounded-lg overflow-hidden border border-[var(--border)]">
          {(['', 'favorable', 'unfavorable', 'neutral'] as const).map((c) => (
            <button
              key={c}
              onClick={() => setCategory(c)}
              className={clsx(
                'px-3 py-1.5 text-xs font-medium transition-colors',
                category === c
                  ? 'bg-cyan-500/20 text-cyan-400'
                  : 'text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)]'
              )}
            >
              {c === '' ? '전체' : c === 'favorable' ? '호재' : c === 'unfavorable' ? '악재' : '중립'}
            </button>
          ))}
        </div>
        <select
          value={hours}
          onChange={(e) => setHours(e.target.value)}
          className="bg-[var(--bg)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-xs text-[var(--fg)] focus:outline-none focus:border-cyan-500"
        >
          <option value="8">8시간</option>
          <option value="24">24시간</option>
          <option value="48">48시간</option>
          <option value="72">72시간</option>
          <option value="168">1주</option>
        </select>
        <button
          onClick={() => { setCategory(''); setHours('72') }}
          className="text-xs text-[var(--muted)] hover:text-[var(--fg)] transition-colors px-2 py-1 rounded hover:bg-[var(--border)]"
        >
          초기화
        </button>
        <div className="ml-auto text-xs text-[var(--muted)]">
          {newsLoading ? '로딩 중…' : `${newsList?.length ?? 0}건`}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* 뉴스 피드 */}
        <div className="lg:col-span-2 space-y-2">
          {newsLoading && Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 space-y-2">
                  <div className="h-4 skeleton rounded w-4/5" />
                  <div className="h-4 skeleton rounded w-3/5" />
                  <div className="flex gap-2 mt-2">
                    <div className="h-3 skeleton rounded w-16" />
                    <div className="h-3 skeleton rounded w-20" />
                    <div className="h-3 skeleton rounded w-24 ml-auto" />
                  </div>
                </div>
                <div className="h-5 skeleton rounded w-10 flex-shrink-0" />
              </div>
            </div>
          ))}
          {newsList?.map((item) => {
            const isExpanded = expandedId === item.id
            return (
              <div
                key={item.id}
                className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 hover:border-cyan-500/30 transition-colors"
              >
                {/* 헤더 — 제목 클릭시 종목 이동 */}
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div
                      className="font-medium text-sm text-[var(--fg)] leading-snug cursor-pointer hover:text-cyan-400 transition-colors"
                      onClick={() => item.codes?.[0] && nav(`/search?code=${item.codes[0]}`)}
                    >
                      {item.title}
                    </div>
                    <div className="flex items-center flex-wrap gap-2 mt-2">
                      {item.corp_name && (
                        <span className="text-xs font-medium text-cyan-400">{item.corp_name}</span>
                      )}
                      {item.keywords?.slice(0, 4).map((k) => (
                        <span key={k} className="text-xs px-1.5 py-0.5 rounded bg-[var(--border)] text-[var(--muted)]">
                          {k}
                        </span>
                      ))}
                      <span className="text-xs text-[var(--muted)] ml-auto">
                        {item.source && `${item.source} · `}{fmt.dateTime(item.published_at)}
                      </span>
                    </div>
                  </div>
                  <div className="flex-shrink-0">
                    <SentimentBadge category={item.category} />
                  </div>
                </div>

                {/* 본문 확장 */}
                {isExpanded && (
                  <div className="mt-3 pt-3 border-t border-[var(--border)] space-y-2">
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
                        감성 점수 <span className={clsx('font-semibold tabular', item.sentiment_score > 0 ? 'text-red-400' : item.sentiment_score < 0 ? 'text-blue-400' : 'text-[var(--muted)]')}>{item.sentiment_score.toFixed(2)}</span>
                      </div>
                    )}
                  </div>
                )}

                {/* 액션 버튼 */}
                <div className="flex items-center gap-2 mt-2.5 pt-2 border-t border-[var(--border)]/50">
                  <button
                    onClick={() => setExpandedId(isExpanded ? null : item.id)}
                    className="flex items-center gap-1 text-xs text-[var(--muted)] hover:text-cyan-400 transition-colors"
                  >
                    {isExpanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                    {isExpanded ? '접기' : '자세히보기'}
                  </button>
                  {item.url && (
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300 transition-colors ml-auto font-medium"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <ExternalLink size={10} />
                      원문보기
                    </a>
                  )}
                </div>
              </div>
            )
          })}
          {!newsLoading && !newsList?.length && (
            <div className="py-16 text-center text-[var(--muted)] text-sm">
              뉴스 데이터가 없습니다
            </div>
          )}
        </div>

        {/* 테마 클러스터 */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-[var(--fg)]">
            <Hash size={14} className="text-cyan-400" />
            테마 클러스터
          </div>
          {themes?.filter((t, i, arr) => arr.findIndex(x => x.theme === t.theme) === i).map((theme) => (
            <div
              key={theme.theme}
              className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-3.5 hover:border-cyan-500/30 transition-colors"
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-1.5">
                  <Hash size={11} className={theme.source === 'news' ? 'text-cyan-400' : 'text-purple-400'} />
                  <span className="text-xs font-semibold text-[var(--fg)]">{theme.theme}</span>
                </div>
                <span className="text-xs tabular text-[var(--muted)]">{theme.count}건</span>
              </div>

              <div className="flex items-center justify-between text-xs text-[var(--muted)]">
                <span>관련 종목 {theme.stock_count}개</span>
                <div className="flex items-center gap-1.5">
                  <BarChart2 size={9} />
                  <span>평균 스코어 {theme.avg_score.toFixed(2)}</span>
                </div>
              </div>

              <div className="mt-2">
                <span className={clsx(
                  'text-xs px-1.5 py-0.5 rounded border',
                  theme.source === 'news'
                    ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20'
                    : 'bg-purple-500/10 text-purple-400 border-purple-500/20'
                )}>
                  {theme.source === 'news' ? '뉴스 테마' : '섹터'}
                </span>
              </div>
            </div>
          ))}
          {!themesLoading && !themes?.length && (
            <div className="py-8 text-center text-xs text-[var(--muted)]">
              테마 클러스터 데이터가 없습니다
            </div>
          )}
        </div>
      </div>
    </div>
  )
}