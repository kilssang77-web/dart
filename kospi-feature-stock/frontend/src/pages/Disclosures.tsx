import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { clsx } from 'clsx'
import { Filter } from 'lucide-react'
import { disclosuresApi } from '@/api/disclosures'
import { SentimentBadge } from '@/components/ui/Badge'
import { fmt, pctColor } from '@/lib/utils'
import { DisclosureDetailModal } from '@/components/modals/DisclosureDetailModal'
import type { Disclosure } from '@/types'

export function Disclosures() {
  const nav = useNavigate()
  const [corp,     setCorp]     = useState('')
  const [category, setCategory] = useState('')
  const [hours,    setHours]    = useState('72')
  const [selected, setSelected] = useState<Disclosure | null>(null)

  const { data, isLoading } = useQuery({
    queryKey:       ['disclosures', corp, category, hours],
    queryFn:        () =>
      disclosuresApi.list({
        code:     corp || undefined,
        category: category || undefined,
        hours:    Number(hours),
        limit:    200,
      }),
    refetchInterval: 60_000,
  })

  return (
    <div className="p-5 space-y-4 max-w-[1600px]">

      {/* 필터 바 */}
      <div className="flex flex-wrap items-center gap-3 p-4 bg-[var(--card)] border border-[var(--border)] rounded-xl">
        <Filter size={13} className="text-[var(--muted)]" />

        <input
          value={corp}
          onChange={(e) => setCorp(e.target.value)}
          placeholder="종목명 / 코드"
          className="bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-[var(--fg)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-500 w-40"
        />

        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-[var(--fg)] focus:outline-none focus:border-cyan-500"
        >
          <option value="">전체 분류</option>
          <option value="favorable">호재</option>
          <option value="unfavorable">악재</option>
          <option value="neutral">중립</option>
        </select>

        <select
          value={hours}
          onChange={(e) => setHours(e.target.value)}
          className="bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-[var(--fg)] focus:outline-none focus:border-cyan-500"
        >
          <option value="12">12시간</option>
          <option value="24">24시간</option>
          <option value="48">48시간</option>
          <option value="72">72시간</option>
          <option value="168">1주</option>
        </select>

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
                <th className="text-right py-2.5 pr-3 text-xs font-semibold uppercase tracking-wider">감성 점수</th>
                <th className="text-right py-2.5 pr-3 text-xs font-semibold uppercase tracking-wider">공시 시각</th>
                <th className="text-right py-2.5 pr-3 text-xs font-semibold uppercase tracking-wider">금액</th>
                <th className="text-right py-2.5 pr-5 text-xs font-semibold uppercase tracking-wider">1일 등락</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && Array.from({ length: 8 }).map((_, i) => (
                <tr key={i} className="border-b border-[var(--border)]/50">
                  <td className="py-3 pl-5 pr-3">
                    <div className="h-4 skeleton rounded w-20 mb-1" />
                    <div className="h-3 skeleton rounded w-12" />
                  </td>
                  <td className="py-3 pr-3">
                    <div className="h-4 skeleton rounded w-48 mb-1.5" />
                    <div className="h-3 skeleton rounded w-24" />
                  </td>
                  <td className="py-3 pr-3 text-center"><div className="h-5 skeleton rounded w-12 mx-auto" /></td>
                  <td className="py-3 pr-3 text-right"><div className="h-4 skeleton rounded w-14 ml-auto" /></td>
                  <td className="py-3 pr-3 text-right"><div className="h-4 skeleton rounded w-28 ml-auto" /></td>
                  <td className="py-3 pr-3 text-right"><div className="h-4 skeleton rounded w-16 ml-auto" /></td>
                  <td className="py-3 pr-5 text-right"><div className="h-4 skeleton rounded w-12 ml-auto" /></td>
                </tr>
              ))}
              {data?.map((d) => (
                <tr
                  key={d.id}
                  className="border-b border-[var(--border)]/50 hover:bg-[var(--border)]/25 cursor-pointer transition-colors"
                  onClick={() => setSelected(d)}
                >
                  {/* 종목명 */}
                  <td className="py-3 pl-5 pr-3">
                    <div className="text-sm font-semibold text-[var(--fg)]">{d.corp_name ?? '—'}</div>
                    <div className="text-xs text-[var(--muted)] mt-0.5">{d.code ?? ''}</div>
                  </td>
                  {/* 공시 제목 */}
                  <td className="py-2.5 pr-3 max-w-xs">
                    <div className="truncate text-sm text-[var(--fg)]" title={d.title}>
                      {d.title}
                    </div>
                    {d.keywords && d.keywords.length > 0 && (
                      <div className="flex gap-1 mt-1 flex-wrap">
                        {d.keywords.slice(0, 3).map((k) => (
                          <span key={k} className="text-xs px-1 py-0 rounded bg-[var(--border)] text-[var(--muted)]">
                            {k}
                          </span>
                        ))}
                      </div>
                    )}
                  </td>
                  {/* 분류 */}
                  <td className="py-2.5 pr-3 text-center">
                    <SentimentBadge category={d.category} />
                  </td>
                  {/* 감성 점수 */}
                  <td className="py-2.5 pr-3 text-right tabular">
                    <SentimentScore score={d.sentiment_score} />
                  </td>
                  {/* 공시 시각 */}
                  <td className="py-2.5 pr-3 text-right tabular text-[var(--muted)]">
                    {fmt.smartTime(d.disclosed_at)}
                  </td>
                  {/* 금액 */}
                  <td className="py-2.5 pr-3 text-right tabular text-[var(--muted)]">
                    {fmt.amount(d.amount)}
                  </td>
                  {/* 1일 등락 */}
                  <td className={clsx('py-3 pr-5 text-right tabular font-semibold', pctColor(d.post_1d_change))}>
                    {fmt.pct(d.post_1d_change)}
                  </td>
                </tr>
              ))}
              {!isLoading && !data?.length && (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-[var(--muted)]">
                    공시 데이터가 없습니다
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 공시 상세 팝업 */}
      {selected && (
        <DisclosureDetailModal
          disclosure={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  )
}

function SentimentScore({ score }: { score?: number | null }) {
  if (score == null) return <span className="text-[var(--muted)]">—</span>
  const color =
    score >= 0.3  ? 'text-green-400' :
    score <= -0.3 ? 'text-red-400'   : 'text-[var(--muted)]'
  return <span className={clsx('font-semibold', color)}>{score.toFixed(3)}</span>
}
