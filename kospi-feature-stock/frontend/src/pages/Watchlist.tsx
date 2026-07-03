import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Star, Trash2, Plus, TrendingUp, TrendingDown, Minus, Zap } from 'lucide-react'
import { clsx } from 'clsx'
import { watchlistApi } from '@/api/watchlist'
import { recommendationsApi } from '@/api/recommendations'
import { Card, CardHeader, CardTitle, CardBody } from '@/components/ui/Card'
import { MarketBadge } from '@/components/ui/Badge'
import { fmt, pctColor } from '@/lib/utils'
import { RecDetailModal } from '@/components/modals/RecDetailModal'
import type { Recommendation } from '@/types'

export function Watchlist() {
  const nav = useNavigate()
  const qc  = useQueryClient()
  const [addCode,      setAddCode]      = useState('')
  const [addNote,      setAddNote]      = useState('')
  const [addError,     setAddError]     = useState('')
  const [fetchCode,    setFetchCode]    = useState<string | null>(null)
  const [selectedRec,  setSelectedRec]  = useState<Recommendation | null>(null)
  const [noSignalCode, setNoSignalCode] = useState<string | null>(null)

  const { data: items = [], isLoading } = useQuery({
    queryKey:        ['watchlist'],
    queryFn:         () => watchlistApi.list(),
    refetchInterval: 60_000,
  })

  /* 최신 ML 추천 조회 — fetchCode가 설정되면 실행 */
  const { data: latestRec, isError: recError, isFetching: recFetching } = useQuery<Recommendation>({
    queryKey:  ['rec-latest', fetchCode],
    queryFn:   () => recommendationsApi.getLatestByCode(fetchCode!),
    enabled:   !!fetchCode,
    staleTime: 30_000,
    retry:     false,
  })

  useEffect(() => {
    if (!fetchCode) return
    if (recFetching) return
    if (latestRec) {
      setSelectedRec(latestRec)
      setFetchCode(null)
    } else if (recError) {
      setNoSignalCode(fetchCode)
      setFetchCode(null)
      setTimeout(() => setNoSignalCode(null), 3000)
    }
  }, [latestRec, recError, recFetching, fetchCode])

  const addMutation = useMutation({
    mutationFn: ({ code, note }: { code: string; note?: string }) =>
      watchlistApi.add(code, note),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['watchlist'] })
      setAddCode('')
      setAddNote('')
      setAddError('')
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail ?? '추가 실패'
      setAddError(msg)
    },
  })

  const removeMutation = useMutation({
    mutationFn: (code: string) => watchlistApi.remove(code),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['watchlist'] }),
  })

  function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    const code = addCode.trim().toUpperCase()
    if (!code) return
    addMutation.mutate({ code, note: addNote.trim() || undefined })
  }

  return (
    <div className="p-5 space-y-5 max-w-[1400px]">

      {/* 종목 추가 폼 */}
      <Card>
        <CardHeader>
          <CardTitle>
            <Star size={14} className="text-yellow-400" />
            관심종목 추가</CardTitle>
        </CardHeader>
        <CardBody className="pt-3">
          <form onSubmit={handleAdd} className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-[var(--muted)]">종목 코드 *</label>
              <input
                value={addCode}
                onChange={(e) => setAddCode(e.target.value.toUpperCase())}
                placeholder="예: 005930"
                maxLength={10}
                className="bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-[var(--fg)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-500 w-36"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-[var(--muted)]">메모 (선택)</label>
              <input
                value={addNote}
                onChange={(e) => setAddNote(e.target.value)}
                placeholder="매수 이유 등..."
                maxLength={100}
                className="bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-[var(--fg)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-500 w-64"
              />
            </div>
            <button
              type="submit"
              disabled={addMutation.isPending || !addCode.trim()}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium bg-cyan-500/15 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-500/25 disabled:opacity-40 transition-colors"
            >
              <Plus size={12} />
              {addMutation.isPending ? '추가 중...' : '추가'}
            </button>
            {addError && (
              <span className="text-xs text-red-400">{addError}</span>
            )}
          </form>
        </CardBody>
      </Card>

      {/* 관심종목 목록 */}
      <Card>
        <CardHeader className="flex items-center justify-between">
          <div>
            <CardTitle>관심종목 목록</CardTitle>
            <div className="text-sm text-[var(--muted)] mt-0.5">{items.length}개 종목 · ML 신호 버튼 클릭 시 추천 상세</div>
          </div>
        </CardHeader>
        <CardBody className="pt-3 px-0 pb-0">
          {isLoading ? (
            <div className="overflow-x-auto">
              <table className="w-full">
                <tbody>
                  {Array.from({ length: 6 }).map((_, i) => (
                    <tr key={i} className="border-b border-[var(--border)]/50">
                      <td className="py-3 pl-5 pr-3">
                        <div className="h-4 skeleton rounded w-20 mb-1.5" />
                        <div className="h-3 skeleton rounded w-14" />
                      </td>
                      <td className="py-3 pr-3"><div className="h-4 skeleton rounded w-16 ml-auto" /></td>
                      <td className="py-3 pr-3"><div className="h-4 skeleton rounded w-14 ml-auto" /></td>
                      <td className="py-3 pr-3"><div className="h-4 skeleton rounded w-28" /></td>
                      <td className="py-3 pr-3"><div className="h-4 skeleton rounded w-20 ml-auto" /></td>
                      <td className="py-3 pr-3 text-center"><div className="h-6 skeleton rounded-full w-16 mx-auto" /></td>
                      <td className="py-3 pr-5" />
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : items.length === 0 ? (
            <div className="py-12 text-center text-xs text-[var(--muted)]">
              관심종목이 없습니다. 위에서 종목을 추가해보세요.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-[var(--border)] text-[var(--muted)]">
                    <th className="text-left py-3 pl-5 pr-3 font-semibold text-xs uppercase tracking-wider text-[var(--muted)]">종목</th>
                    <th className="text-right py-3 pr-3 font-semibold text-xs uppercase tracking-wider text-[var(--muted)]">현재가</th>
                    <th className="text-right py-3 pr-3 font-semibold text-xs uppercase tracking-wider text-[var(--muted)]">등락률</th>
                    <th className="text-left py-3 pr-3 font-semibold text-xs uppercase tracking-wider text-[var(--muted)]">메모</th>
                    <th className="text-right py-3 pr-3 font-semibold text-xs uppercase tracking-wider text-[var(--muted)]">추가일</th>
                    <th className="text-center py-3 pr-3 font-semibold text-xs uppercase tracking-wider text-[var(--muted)]">ML 신호</th>
                    <th className="py-3 pr-5" />
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => {
                    const chg      = item.change_rate ?? 0
                    const up       = chg > 0
                    const dn       = chg < 0
                    const noSignal = noSignalCode === item.code
                    const loading  = fetchCode === item.code
                    return (
                      <tr
                        key={item.id}
                        className="border-b border-[var(--border)]/50 hover:bg-[var(--border)]/20 transition-colors group"
                      >
                        <td className="py-3 pl-5 pr-3 cursor-pointer" onClick={() => nav(`/search?code=${item.code}`)}>
                          <div className="font-semibold text-sm text-[var(--fg)]">{item.name}</div>
                          <div className="flex items-center gap-1 mt-0.5">
                            <span className="text-[var(--muted)]">{item.code}</span>
                            <MarketBadge market={item.market} />
                          </div>
                        </td>
                        <td className="py-3 pr-3 text-right tabular text-[var(--fg)] font-semibold">
                          {item.current_price != null ? item.current_price.toLocaleString() : '—'}
                        </td>
                        <td className={clsx('py-3 pr-3 text-right tabular font-semibold', pctColor(chg))}>
                          <span className="flex items-center justify-end gap-0.5">
                            {up ? <TrendingUp size={10} /> : dn ? <TrendingDown size={10} /> : <Minus size={10} />}
                            {fmt.pct(chg)}
                          </span>
                        </td>
                        <td className="py-3 pr-3 text-sm text-[var(--muted)] max-w-[200px] truncate">
                          {item.note ?? '—'}
                        </td>
                        <td className="py-3 pr-3 text-right tabular text-[var(--muted)] text-sm">
                          {item.added_at.slice(0, 10)}
                        </td>
                        <td className="py-3 pr-3 text-center">
                          <button
                            onClick={() => setFetchCode(item.code)}
                            disabled={loading || !!fetchCode}
                            title="최신 ML 추천 신호 보기"
                            className={clsx(
                              'inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold border transition-colors',
                              noSignal
                                ? 'border-[var(--border)] text-[var(--muted)] bg-[var(--border)] cursor-default'
                                : loading
                                ? 'border-cyan-500/30 text-cyan-400/50 bg-cyan-500/5 cursor-wait'
                                : 'border-cyan-500/30 text-cyan-400 bg-cyan-500/10 hover:bg-cyan-500/20',
                            )}
                          >
                            <Zap size={9} />
                            {loading ? '조회 중…' : noSignal ? '신호 없음' : 'ML 신호'}
                          </button>
                        </td>
                        <td className="py-3 pr-5 text-right">
                          <button
                            onClick={() => removeMutation.mutate(item.code)}
                            disabled={removeMutation.isPending}
                            className="opacity-0 group-hover:opacity-100 p-1 rounded text-red-400/70 hover:text-red-400 hover:bg-red-500/10 transition-all"
                            title="관심종목 삭제"
                          >
                            <Trash2 size={12} />
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>

      {/* ML 추천 상세 팝업 */}
      {selectedRec && (
        <RecDetailModal
          rec={selectedRec}
          compact
          onClose={() => setSelectedRec(null)}
          onGoDetail={() => { setSelectedRec(null); nav(`/search?code=${selectedRec.code}`) }}
        />
      )}
    </div>
  )
}
