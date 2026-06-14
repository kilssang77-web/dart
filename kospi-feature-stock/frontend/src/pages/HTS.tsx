import { useEffect, useRef, useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { Wifi, WifiOff, RefreshCw, Clock, X, Search, BookOpen } from 'lucide-react'
import { fmt } from '@/lib/utils'
import { stocksApi, type Orderbook } from '@/api/stocks'

interface TickData {
  code:        string
  name:        string
  price:       number
  prev_close:  number
  change:      number
  change_rate: number
  volume:      number
  amount?:     number
  high?:       number
  low?:        number
  ask1?:       number
  bid1?:       number
  snapshot?:   boolean
  snap_date?:  string
}

type WsStatus = 'connecting' | 'connected' | 'disconnected'

const SORT_OPTIONS = [
  { value: 'change_rate_abs', label: '등락률 절대값' },
  { value: 'change_rate',     label: '상승률' },
  { value: 'volume',          label: '거래량' },
  { value: 'amount',          label: '거래대금' },
]

export function HTS() {
  const wsRef       = useRef<WebSocket | null>(null)
  const timerRef    = useRef<ReturnType<typeof setTimeout>>()
  const [ticks,         setTicks]         = useState<Map<string, TickData>>(new Map())
  const [flash,         setFlash]         = useState<Map<string, 'up' | 'dn'>>(new Map())
  const [status,        setStatus]        = useState<WsStatus>('connecting')
  const [sortBy,        setSortBy]        = useState('change_rate_abs')
  const [filterQ,       setFilterQ]       = useState('')
  const [isMarketOpen,  setIsMarketOpen]  = useState<boolean | null>(null)
  const [watchInput,    setWatchInput]    = useState('')
  const [watchQuery,    setWatchQuery]    = useState('')
  const [watchedCodes,  setWatchedCodes]  = useState<Map<string, string>>(new Map())
  const [showWatchSearch, setShowWatchSearch] = useState(false)
  const [selectedCode,  setSelectedCode]  = useState<string | null>(null)

  const { data: orderbook } = useQuery<Orderbook>({
    queryKey:  ['orderbook', selectedCode],
    queryFn:   () => stocksApi.getOrderbook(selectedCode!),
    enabled:   !!selectedCode,
    staleTime: 15_000,
    refetchInterval: selectedCode ? 15_000 : false,
  })

  const { data: watchResults } = useQuery({
    queryKey:  ['hts-watch-search', watchQuery],
    queryFn:   () => stocksApi.search(watchQuery),
    enabled:   watchQuery.length >= 1,
    staleTime: 60_000,
  })

  async function addWatch(code: string, name: string) {
    try { await stocksApi.watchStock(code) } catch { /* ignore */ }
    setWatchedCodes((prev) => new Map([...prev, [code, name]]))
    setWatchInput('')
    setWatchQuery('')
    setShowWatchSearch(false)
  }

  function removeWatch(code: string) {
    setWatchedCodes((prev) => { const m = new Map(prev); m.delete(code); return m })
  }

  useEffect(() => {
    if (watchedCodes.size === 0) return
    const id = setInterval(() => {
      watchedCodes.forEach((_, code) => { stocksApi.watchStock(code).catch(() => {}) })
    }, 60_000)
    return () => clearInterval(id)
  }, [watchedCodes])

  const connect = useCallback(() => {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url   = `${proto}//${location.host}/ws/ticks`
    const ws    = new WebSocket(url)
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws
    setStatus('connecting')

    ws.onopen  = () => setStatus('connected')
    ws.onclose = () => {
      setStatus('disconnected')
      timerRef.current = setTimeout(connect, 5_000)
    }
    ws.onerror = () => ws.close()

    ws.onmessage = (ev) => {
      try {
        const data = typeof ev.data === 'string' ? JSON.parse(ev.data)
          : JSON.parse(new TextDecoder().decode(ev.data as ArrayBuffer))
        if (data.type === 'market_status') {
          setIsMarketOpen(data.is_open)
          return
        }
        const tick = data as TickData
        setTicks((prev) => {
          const next = new Map(prev)
          const old  = prev.get(tick.code)
          next.set(tick.code, tick)
          if (old && old.price !== tick.price && !tick.snapshot) {
            const dir: 'up' | 'dn' = tick.price > old.price ? 'up' : 'dn'
            setFlash((f) => {
              const nf = new Map(f)
              nf.set(tick.code, dir)
              return nf
            })
            setTimeout(() => {
              setFlash((f) => { const nf = new Map(f); nf.delete(tick.code); return nf })
            }, 400)
          }
          return next
        })
      } catch { /* ignore malformed messages */ }
    }
  }, [])

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(timerRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  const rows = [...ticks.values()]
    .filter((t) => {
      if (filterQ) {
        const q = filterQ.toLowerCase()
        if (!t.name.toLowerCase().includes(q) && !t.code.includes(q)) return false
      }
      return true
    })
    .sort((a, b) => {
      if (sortBy === 'change_rate_abs') return Math.abs(b.change_rate) - Math.abs(a.change_rate)
      if (sortBy === 'change_rate')     return b.change_rate - a.change_rate
      if (sortBy === 'volume')          return (b.volume ?? 0) - (a.volume ?? 0)
      if (sortBy === 'amount')          return (b.amount ?? 0) - (a.amount ?? 0)
      return 0
    })

  const selectedTick = selectedCode ? ticks.get(selectedCode) : null
  const obMaxQty = orderbook
    ? Math.max(...[...orderbook.asks, ...orderbook.bids].map((l) => l.qty), 1)
    : 1

  return (
    <div className="flex h-full">
    <div className="flex-1 p-4 space-y-3 min-w-0 overflow-auto">

      {/* 상태 바 */}
      <div className="flex items-center gap-3 p-3 bg-[var(--card)] border border-[var(--border)] rounded-xl">
        <div className={clsx('flex items-center gap-1.5 text-sm font-medium',
          status === 'connected'    ? 'text-green-400' :
          status === 'connecting'   ? 'text-yellow-400' : 'text-red-400'
        )}>
          {status === 'connected' ? <Wifi size={13} /> : <WifiOff size={13} />}
          {status === 'connected'  ? '실시간 연결됨' :
           status === 'connecting' ? '연결 중…'     : '연결 끊김 (재연결 대기)'}
        </div>

        <div className="h-4 w-px bg-[var(--border)]" />

        <input
          value={filterQ}
          onChange={(e) => setFilterQ(e.target.value)}
          placeholder="종목명 / 코드"
          className="bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-[var(--fg)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-500 w-36"
        />

        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          className="bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-[var(--fg)] focus:outline-none focus:border-cyan-500"
        >
          {SORT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>

        <div className="ml-auto text-sm text-[var(--muted)] tabular font-medium">
          {rows.length}종목
        </div>
      </div>

      {/* 종목 추가/제거 패널 */}
      <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-semibold text-[var(--muted)]">모니터링</span>

          {[...watchedCodes.entries()].map(([code, name]) => (
            <div key={code} className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-cyan-500/15 border border-cyan-500/30 text-xs text-cyan-400">
              <span className="font-semibold">{name}</span>
              <span className="text-cyan-400/60">{code}</span>
              <button onClick={() => removeWatch(code)} className="ml-0.5 hover:text-white transition-colors">
                <X size={10} />
              </button>
            </div>
          ))}

          <div className="relative">
            <div className="flex items-center gap-1 px-2 py-1 bg-[var(--bg)] border border-[var(--border)] rounded-lg focus-within:border-cyan-500">
              <Search size={11} className="text-[var(--muted)] shrink-0" />
              <input
                value={watchInput}
                onChange={(e) => { setWatchInput(e.target.value); setWatchQuery(e.target.value); setShowWatchSearch(true) }}
                onFocus={() => setShowWatchSearch(true)}
                onBlur={() => setTimeout(() => setShowWatchSearch(false), 200)}
                placeholder="종목 추가…"
                className="bg-transparent text-xs text-[var(--fg)] placeholder:text-[var(--muted)] focus:outline-none w-28"
              />
            </div>
            {showWatchSearch && watchResults && watchResults.length > 0 && (
              <div className="absolute top-full left-0 z-50 mt-1 w-56 bg-[var(--card)] border border-[var(--border)] rounded-xl shadow-lg overflow-hidden max-h-48 overflow-y-auto">
                {watchResults.slice(0, 8).map((s) => (
                  <button
                    key={s.code}
                    onMouseDown={() => addWatch(s.code, s.name)}
                    className="w-full flex items-center justify-between px-3 py-2 hover:bg-[var(--border)]/30 text-xs border-b border-[var(--border)]/40 last:border-0"
                  >
                    <span className="font-semibold text-[var(--fg)]">{s.name}</span>
                    <span className="text-[var(--muted)]">{s.code}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {watchedCodes.size === 0 && (
            <span className="text-xs text-[var(--muted)]/60">종목을 추가하면 실시간 구독됩니다</span>
          )}
        </div>
      </div>

      {/* 장 마감 배너 */}
      {isMarketOpen === false && (
        <div className="flex items-center gap-2 px-3 py-2 bg-gray-500/10 border border-[var(--border)] rounded-lg text-xs text-[var(--muted)]">
          <Clock size={12} className="shrink-0" />
          <span>장 마감 — 거래대금 상위 30종목 최근 종가 기준 표시</span>
          <span className="ml-auto opacity-60">장 운영: 09:00 – 15:35 (KST)</span>
        </div>
      )}

      {/* 시세 그리드 */}
      {rows.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 gap-3 text-[var(--muted)]">
          {status === 'connecting' ? (
            <RefreshCw size={24} className="animate-spin" />
          ) : isMarketOpen === false ? (
            <Clock size={24} />
          ) : (
            <WifiOff size={24} />
          )}
          <p className="text-sm">
            {status === 'connecting'   ? '시세 데이터 연결 중…' :
             isMarketOpen === false    ? '장 마감 — 종가 기준 데이터' :
                                         '시세 데이터 수신 대기 중'}
          </p>
          {isMarketOpen !== false && (
            <p className="text-xs">KIS API에서 실시간 데이터가 수신되면 자동으로 표시됩니다</p>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-2">
          {rows.map((tick) => {
            const up  = tick.change_rate > 0
            const dn  = tick.change_rate < 0
            const dir = flash.get(tick.code)
            return (
              <div
                key={tick.code}
                onClick={() => setSelectedCode((c) => c === tick.code ? null : tick.code)}
                className={clsx(
                  'relative bg-[var(--card)] border border-[var(--border)] rounded-xl p-3 cursor-pointer',
                  'hover:border-cyan-500/40 transition-colors',
                  selectedCode === tick.code && 'border-cyan-500/60 ring-1 ring-cyan-500/30',
                  dir === 'up' && 'flash-up',
                  dir === 'dn' && 'flash-dn'
                )}
              >
                <div className={clsx(
                  'absolute top-0 left-0 right-0 h-0.5 rounded-t-xl',
                  up ? 'bg-red-400' : dn ? 'bg-blue-400' : 'bg-transparent'
                )} />

                <div className="flex items-start justify-between gap-1">
                  <div>
                    <div className="text-sm font-semibold text-[var(--fg)] truncate">{tick.name}</div>
                    <div className="text-xs text-[var(--muted)]/70">{tick.code}</div>
                  </div>
                  {tick.snapshot && (
                    <span className="text-xs text-[var(--muted)]/50 shrink-0 mt-0.5">
                      장 마감·종가 {tick.snap_date?.slice(5) ?? ''}
                    </span>
                  )}
                </div>

                <div className={clsx(
                  'text-xl font-bold tabular leading-tight mt-1.5',
                  up ? 'text-red-400' : dn ? 'text-blue-400' : 'text-[var(--fg)]'
                )}>
                  {tick.price.toLocaleString()}
                </div>

                <div className={clsx(
                  'text-sm font-semibold tabular mt-0.5',
                  up ? 'text-red-400' : dn ? 'text-blue-400' : 'text-[var(--muted)]'
                )}>
                  {up ? '▲' : dn ? '▼' : '—'}{' '}
                  {Math.abs(tick.change_rate).toFixed(2)}%
                </div>

                <div className="flex items-center justify-between mt-2 pt-2 border-t border-[var(--border)]">
                  <span className="text-xs text-[var(--muted)]">거래량</span>
                  <span className="text-sm tabular text-[var(--muted)]">
                    {fmt.vol(tick.volume)}
                  </span>
                </div>

                {(tick.ask1 || tick.bid1) && (
                  <div className="flex justify-between mt-1 text-xs tabular">
                    <span className="text-blue-400">{fmt.price(tick.bid1)}</span>
                    <span className="text-[var(--muted)]">/</span>
                    <span className="text-red-400">{fmt.price(tick.ask1)}</span>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>

    {/* 호가창 사이드 패널 */}
    {selectedCode && (
      <div className="w-64 shrink-0 border-l border-[var(--border)] bg-[var(--card)] flex flex-col">
        {/* 헤더 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)]">
          <div>
            <div className="text-sm font-semibold text-[var(--fg)] flex items-center gap-1.5">
              <BookOpen size={13} className="text-cyan-400" />
              {selectedTick?.name ?? selectedCode}
            </div>
            {selectedTick && (
              <div className={clsx(
                'text-xs tabular mt-0.5',
                selectedTick.change_rate > 0 ? 'text-red-400' : selectedTick.change_rate < 0 ? 'text-blue-400' : 'text-[var(--muted)]'
              )}>
                {selectedTick.price.toLocaleString()} ({selectedTick.change_rate > 0 ? '+' : ''}{selectedTick.change_rate.toFixed(2)}%)
              </div>
            )}
          </div>
          <button onClick={() => setSelectedCode(null)} className="text-[var(--muted)] hover:text-[var(--fg)]">
            <X size={14} />
          </button>
        </div>

        {/* 호가 테이블 */}
        <div className="flex-1 overflow-y-auto p-2 space-y-px text-xs">
          {(!orderbook || (orderbook.asks.length === 0 && orderbook.bids.length === 0)) ? (
            <div className="flex flex-col items-center justify-center h-full text-[var(--muted)] gap-2 py-8">
              <Clock size={18} className="opacity-40" />
              <p className="text-center">장 중에 호가 데이터가<br/>표시됩니다</p>
            </div>
          ) : (
            <>
              {/* 매도 (역순 — 가장 낮은 매도가가 아래) */}
              <div className="text-[10px] text-[var(--muted)] px-1 pt-1 pb-0.5 uppercase tracking-wider">매도 잔량</div>
              {[...orderbook.asks].reverse().map((lv, i) => {
                const pct = Math.min(100, (lv.qty / obMaxQty) * 100)
                return (
                  <div key={`ask-${i}`} className="flex items-center gap-1 h-5 relative px-1">
                    <div className="absolute right-0 top-0 bottom-0 bg-blue-500/10 rounded"
                         style={{ width: `${pct}%` }} />
                    <span className="w-20 text-right tabular text-blue-400 font-medium relative z-10">
                      {lv.price.toLocaleString()}
                    </span>
                    <span className="flex-1 text-right tabular text-[var(--muted)] relative z-10">
                      {lv.qty.toLocaleString()}
                    </span>
                  </div>
                )
              })}

              {/* 현재가 구분선 */}
              {selectedTick && (
                <div className="flex items-center gap-1 my-1 px-1">
                  <div className="flex-1 h-px bg-[var(--border)]" />
                  <span className={clsx(
                    'text-xs font-bold tabular',
                    selectedTick.change_rate > 0 ? 'text-red-400' : selectedTick.change_rate < 0 ? 'text-blue-400' : 'text-[var(--fg)]'
                  )}>
                    {selectedTick.price.toLocaleString()}
                  </span>
                  <div className="flex-1 h-px bg-[var(--border)]" />
                </div>
              )}

              {/* 매수 */}
              <div className="text-[10px] text-[var(--muted)] px-1 pt-0.5 pb-0.5 uppercase tracking-wider">매수 잔량</div>
              {orderbook.bids.map((lv, i) => {
                const pct = Math.min(100, (lv.qty / obMaxQty) * 100)
                return (
                  <div key={`bid-${i}`} className="flex items-center gap-1 h-5 relative px-1">
                    <div className="absolute left-0 top-0 bottom-0 bg-red-500/10 rounded"
                         style={{ width: `${pct}%` }} />
                    <span className="w-20 text-right tabular text-red-400 font-medium relative z-10">
                      {lv.price.toLocaleString()}
                    </span>
                    <span className="flex-1 text-right tabular text-[var(--muted)] relative z-10">
                      {lv.qty.toLocaleString()}
                    </span>
                  </div>
                )
              })}

              {/* 총 잔량 */}
              <div className="flex justify-between px-1 pt-2 pb-1 border-t border-[var(--border)] mt-1 text-[10px]">
                <span className="text-blue-400 tabular">매도 {orderbook.total_ask_qty.toLocaleString()}</span>
                <span className="text-red-400 tabular">매수 {orderbook.total_bid_qty.toLocaleString()}</span>
              </div>
            </>
          )}
        </div>
      </div>
    )}
    </div>
  )
}
