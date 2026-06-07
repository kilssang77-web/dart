import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { Search, X, ChevronRight } from 'lucide-react'
import { stocksApi } from '@/api/stocks'
import { featuresApi } from '@/api/features'
import { recommendationsApi } from '@/api/recommendations'
import { CandleChart } from '@/components/charts/CandleChart'
import { Badge, ActionBadge, MarketBadge } from '@/components/ui/Badge'
import { Card, CardHeader, CardTitle, CardBody } from '@/components/ui/Card'
import { fmt, pctColor, probColor } from '@/lib/utils'

export function StockSearch() {
  const [searchParams, setSearchParams] = useSearchParams()

  const [query,   setQuery]   = useState(searchParams.get('q') ?? '')
  const [market,  setMarket]  = useState('')
  const [selCode, setSelCode] = useState(searchParams.get('code') ?? '')

  useEffect(() => {
    const code = searchParams.get('code')
    const q    = searchParams.get('q')
    if (code) setSelCode(code)
    if (q)    setQuery(q)
  }, [searchParams])

  const { data: results, isLoading: searching } = useQuery({
    queryKey:  ['stock-search', query, market],
    queryFn:   () => stocksApi.search(query, market || undefined),
    enabled:   query.length >= 1,
    staleTime: 60_000,
  })

  const { data: stock } = useQuery({
    queryKey: ['stock-detail', selCode],
    queryFn:  () => stocksApi.getDetail(selCode),
    enabled:  !!selCode,
  })

  const { data: bars } = useQuery({
    queryKey: ['bars', selCode],
    queryFn:  () => stocksApi.getDailyBars(selCode, 120),
    enabled:  !!selCode,
  })

  const { data: events } = useQuery({
    queryKey:        ['events-by-code', selCode],
    queryFn:         () => featuresApi.list({ code: selCode, hours: 168, limit: 20 }),
    enabled:         !!selCode,
    refetchInterval: 60_000,
  })

  const { data: latestRec } = useQuery({
    queryKey:        ['rec-latest', selCode],
    queryFn:         () => recommendationsApi.getLatestByCode(selCode),
    enabled:         !!selCode,
    refetchInterval: 60_000,
  })

  function selectCode(code: string) {
    setSelCode(code)
    setSearchParams({ code })
  }

  function clearSelection() {
    setSelCode('')
    setSearchParams(query ? { q: query } : {})
  }

  return (
    <div className="p-6 space-y-4">
      {/* 검색 바 */}
      <div className="flex flex-wrap items-center gap-2 p-3 bg-[var(--card)] border border-[var(--border)] rounded-xl">
        <Search size={14} className="text-[var(--muted)]" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') setSearchParams({ q: query })
          }}
          placeholder="종목명 또는 종목코드 입력"
          className="flex-1 bg-transparent text-sm text-[var(--fg)] placeholder:text-[var(--muted)] focus:outline-none"
        />
        {query && (
          <button onClick={() => { setQuery(''); clearSelection() }} className="text-[var(--muted)] hover:text-[var(--fg)]">
            <X size={13} />
          </button>
        )}
        <select
          value={market}
          onChange={(e) => setMarket(e.target.value)}
          className="bg-[var(--bg)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-xs text-[var(--fg)] focus:outline-none focus:border-cyan-500"
        >
          <option value="">전체 시장</option>
          <option value="KOSPI">KOSPI</option>
          <option value="KOSDAQ">KOSDAQ</option>
        </select>
        <button
          onClick={() => setSearchParams({ q: query })}
          className="px-3 py-1.5 rounded-md bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 text-xs font-medium transition-colors"
        >
          검색
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* 검색 결과 리스트 */}
        <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-[var(--border)] text-xs font-semibold text-[var(--muted)] flex items-center justify-between">
            <span>검색 결과</span>
            {searching && <span className="text-cyan-400">검색 중…</span>}
            {!searching && results && <span className="tabular">{results.length}건</span>}
          </div>
          <div className="overflow-y-auto max-h-[calc(100vh-260px)]">
            {results?.map((s) => (
              <div
                key={s.code}
                onClick={() => selectCode(s.code)}
                className={clsx(
                  'flex items-center justify-between px-4 py-3 border-b border-[var(--border)]/50',
                  'hover:bg-[var(--border)]/25 cursor-pointer transition-colors',
                  selCode === s.code && 'bg-cyan-500/10 border-l-2 border-l-cyan-500'
                )}
              >
                <div>
                  <div className="font-semibold text-sm text-[var(--fg)]">{s.name}</div>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <span className="text-xs text-[var(--muted)]">{s.code}</span>
                    <MarketBadge market={s.market} />
                  </div>
                </div>
                <ChevronRight size={13} className="text-[var(--muted)]" />
              </div>
            ))}
            {!searching && results?.length === 0 && query && (
              <div className="py-8 text-center text-xs text-[var(--muted)]">
                "{query}" 검색 결과 없음
              </div>
            )}
            {!query && (
              <div className="py-8 text-center text-xs text-[var(--muted)]">
                종목명 또는 코드를 입력하세요
              </div>
            )}
          </div>
        </div>

        {/* 상세 패널 */}
        {selCode ? (
          <div className="lg:col-span-2 space-y-4">

            {/* 종목 헤더 */}
            {stock && (
              <div className="flex items-center gap-3 p-4 bg-[var(--card)] border border-[var(--border)] rounded-xl">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-lg font-bold text-[var(--fg)]">{stock.name}</span>
                    <MarketBadge market={stock.market} />
                    {stock.is_trading_halt && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-400 border border-red-500/30">
                        거래정지
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-xs text-[var(--muted)]">
                    <span>{stock.code}</span>
                    {stock.sector && <span>· {stock.sector}</span>}
                  </div>
                </div>
                <button
                  onClick={clearSelection}
                  className="ml-auto text-[var(--muted)] hover:text-[var(--fg)] p-1"
                >
                  <X size={14} />
                </button>
              </div>
            )}

            {/* 캔들 차트 */}
            {bars && bars.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>일봉 차트 ({bars.length}일)</CardTitle>
                </CardHeader>
                <CardBody>
                  <CandleChart data={bars} height={280} />
                </CardBody>
              </Card>
            )}

            {/* 최근 추천 + 최근 이벤트 */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

              {/* 최근 추천 */}
              <Card>
                <CardHeader><CardTitle>최근 추천</CardTitle></CardHeader>
                <CardBody className="pt-3">
                  {latestRec ? (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <ActionBadge action={latestRec.action} />
                        <span className="text-xs text-[var(--muted)]">{fmt.dateTime(latestRec.created_at)}</span>
                      </div>
                      <div className={clsx('text-2xl font-bold tabular', probColor(latestRec.success_prob))}>
                        {fmt.prob(latestRec.success_prob)}
                      </div>
                      <div className="grid grid-cols-3 gap-2 text-center text-xs">
                        <div className="bg-[var(--bg)] rounded-lg p-2">
                          <div className="text-[9px] text-[var(--muted)]">진입가</div>
                          <div className="font-bold text-[var(--fg)] tabular mt-0.5">{fmt.price(latestRec.entry_price)}</div>
                        </div>
                        <div className="bg-red-500/10 rounded-lg p-2">
                          <div className="text-[9px] text-red-400">목표가</div>
                          <div className="font-bold text-red-400 tabular mt-0.5">{fmt.price(latestRec.target_price)}</div>
                        </div>
                        <div className="bg-blue-500/10 rounded-lg p-2">
                          <div className="text-[9px] text-blue-400">손절가</div>
                          <div className="font-bold text-blue-400 tabular mt-0.5">{fmt.price(latestRec.stop_loss_price)}</div>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="py-6 text-center text-xs text-[var(--muted)]">추천 데이터 없음</div>
                  )}
                </CardBody>
              </Card>

              {/* 최근 이벤트 */}
              <Card>
                <CardHeader><CardTitle>최근 이벤트</CardTitle></CardHeader>
                <CardBody className="pt-3">
                  <div className="space-y-2">
                    {events?.slice(0, 8).map((ev) => (
                      <div key={ev.id} className="flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <Badge eventType={ev.event_type} size="sm" />
                        </div>
                        <div className="flex items-center gap-3 text-right">
                          <span className={clsx('tabular font-semibold', pctColor(ev.change_rate))}>
                            {fmt.pct(ev.change_rate)}
                          </span>
                          <span className="text-[var(--muted)]">{fmt.dateTime(ev.detected_at)}</span>
                        </div>
                      </div>
                    ))}
                    {!events?.length && (
                      <div className="py-4 text-center text-[var(--muted)]">최근 이벤트 없음</div>
                    )}
                  </div>
                </CardBody>
              </Card>
            </div>
          </div>
        ) : (
          <div className="lg:col-span-2 flex items-center justify-center py-24 text-[var(--muted)] text-sm">
            왼쪽 목록에서 종목을 선택하세요
          </div>
        )}
      </div>
    </div>
  )
}