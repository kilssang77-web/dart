import { useEffect, useRef, useState, useCallback } from 'react'
import { clsx } from 'clsx'
import { Wifi, WifiOff, RefreshCw } from 'lucide-react'
import { fmt } from '@/lib/utils'

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
  const [ticks,     setTicks]     = useState<Map<string, TickData>>(new Map())
  const [flash,     setFlash]     = useState<Map<string, 'up' | 'dn'>>(new Map())
  const [status,    setStatus]    = useState<WsStatus>('connecting')
  const [sortBy,    setSortBy]    = useState('change_rate_abs')
  const [filterQ,   setFilterQ]   = useState('')

  const connect = useCallback(() => {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url   = `${proto}//${location.host}/ws/ticks`
    const ws    = new WebSocket(url)
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
        const tick: TickData = JSON.parse(ev.data)
        setTicks((prev) => {
          const next = new Map(prev)
          const old  = prev.get(tick.code)
          next.set(tick.code, tick)
          if (old && old.price !== tick.price) {
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

  return (
    <div className="p-4 space-y-3 h-full">

      {/* 상태 바 */}
      <div className="flex items-center gap-3 p-3 bg-[var(--card)] border border-[var(--border)] rounded-xl">
        <div className={clsx('flex items-center gap-1.5 text-xs font-medium',
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
          className="bg-[var(--bg)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-xs text-[var(--fg)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-500 w-32"
        />

        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          className="bg-[var(--bg)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-xs text-[var(--fg)] focus:outline-none focus:border-cyan-500"
        >
          {SORT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>

        <div className="ml-auto text-xs text-[var(--muted)] tabular">
          {rows.length}종목
        </div>
      </div>

      {/* 시세 그리드 */}
      {rows.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 gap-3 text-[var(--muted)]">
          {status === 'connecting' ? (
            <RefreshCw size={24} className="animate-spin" />
          ) : (
            <WifiOff size={24} />
          )}
          <p className="text-sm">
            {status === 'connecting' ? 'WebSocket 연결 중…' : 'WebSocket 수신 대기 중'}
          </p>
          <p className="text-xs">KIS API에서 실시간 데이터가 수신되면 자동으로 표시됩니다</p>
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
                className={clsx(
                  'relative bg-[var(--card)] border border-[var(--border)] rounded-xl p-3 cursor-pointer',
                  'hover:border-cyan-500/40 transition-colors',
                  dir === 'up' && 'flash-up',
                  dir === 'dn' && 'flash-dn'
                )}
              >
                {/* 등락 표시바 */}
                <div className={clsx(
                  'absolute top-0 left-0 right-0 h-0.5 rounded-t-xl',
                  up ? 'bg-red-400' : dn ? 'bg-blue-400' : 'bg-transparent'
                )} />

                <div className="text-[10px] text-[var(--muted)] truncate">{tick.name}</div>
                <div className="text-[10px] text-[var(--muted)]/60 mb-1">{tick.code}</div>

                <div className={clsx(
                  'text-lg font-bold tabular leading-tight',
                  up ? 'text-red-400' : dn ? 'text-blue-400' : 'text-[var(--fg)]'
                )}>
                  {tick.price.toLocaleString()}
                </div>

                <div className={clsx(
                  'text-xs font-semibold tabular mt-0.5',
                  up ? 'text-red-400' : dn ? 'text-blue-400' : 'text-[var(--muted)]'
                )}>
                  {up ? '▲' : dn ? '▼' : '—'}{' '}
                  {Math.abs(tick.change_rate).toFixed(2)}%
                </div>

                <div className="flex items-center justify-between mt-2 pt-2 border-t border-[var(--border)]">
                  <span className="text-[9px] text-[var(--muted)]">거래량</span>
                  <span className="text-[9px] tabular text-[var(--muted)]">
                    {fmt.vol(tick.volume)}
                  </span>
                </div>

                {(tick.ask1 || tick.bid1) && (
                  <div className="flex justify-between mt-1 text-[9px] tabular">
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
  )
}
