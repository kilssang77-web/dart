import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { clsx } from 'clsx'
import { Hash, Newspaper, BarChart2 } from 'lucide-react'
import { newsApi } from '@/api/news'
import { marketApi } from '@/api/market'
import { SentimentBadge } from '@/components/ui/Badge'
import { fmt } from '@/lib/utils'

export function News() {
  const nav = useNavigate()
  const [category, setCategory] = useState('')
  const [hours,    setHours]    = useState('24')

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
        </select>
        <div className="ml-auto text-xs text-[var(--muted)]">
          {newsLoading ? '로딩 중…' : `${newsList?.length ?? 0}건`}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* 뉴스 피드 */}
        <div className="lg:col-span-2 space-y-2">
          {newsList?.map((item) => (
            <div
              key={item.id}
              className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 hover:border-cyan-500/30 transition-colors cursor-pointer"
              onClick={() => item.code && nav(`/search?code=${item.code}`)}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-sm text-[var(--fg)] leading-snug">{item.title}</div>
                  {item.content && (
                    <div className="text-xs text-[var(--muted)] mt-1.5 line-clamp-2 leading-relaxed">
                      {item.content}
                    </div>
                  )}
                  <div className="flex items-center flex-wrap gap-2 mt-2.5">
                    {item.corp_name && (
                      <span className="text-[10px] font-medium text-cyan-400">{item.corp_name}</span>
                    )}
                    {item.keywords?.slice(0, 4).map((k) => (
                      <span key={k} className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--border)] text-[var(--muted)]">
                        {k}
                      </span>
                    ))}
                    <span className="text-[10px] text-[var(--muted)] ml-auto">
                      {item.source && `${item.source} · `}{fmt.dateTime(item.published_at)}
                    </span>
                  </div>
                </div>
                <div className="flex-shrink-0">
                  <SentimentBadge category={item.category} />
                </div>
              </div>
            </div>
          ))}
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
          {themes?.map((theme) => (
            <div
              key={theme.theme}
              className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-3.5 hover:border-cyan-500/30 transition-colors"
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-1.5">
                  <Hash size={11} className={theme.source === 'news' ? 'text-cyan-400' : 'text-purple-400'} />
                  <span className="text-xs font-semibold text-[var(--fg)]">{theme.theme}</span>
                </div>
                <span className="text-[10px] tabular text-[var(--muted)]">{theme.count}건</span>
              </div>

              <div className="flex items-center justify-between text-[9px] text-[var(--muted)]">
                <span>관련 종목 {theme.stock_count}개</span>
                <div className="flex items-center gap-1.5">
                  <BarChart2 size={9} />
                  <span>평균 스코어 {theme.avg_score.toFixed(2)}</span>
                </div>
              </div>

              <div className="mt-2">
                <span className={clsx(
                  'text-[9px] px-1.5 py-0.5 rounded border',
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