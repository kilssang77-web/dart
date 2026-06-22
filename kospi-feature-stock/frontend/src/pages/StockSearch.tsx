import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { Search, X, Clock, Trash2, ChevronRight, TrendingUp, TrendingDown, Minus, Star, StarOff, BarChart2, ShoppingCart, BookOpen, History, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { useSidebarStore } from '@/store/sidebar'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { stocksApi, type FinancialItem } from '@/api/stocks'
import { featuresApi } from '@/api/features'
import { recommendationsApi } from '@/api/recommendations'
import { watchlistApi, type WatchlistItem } from '@/api/watchlist'
import { http } from '@/api/client'
import { CandleChart } from '@/components/charts/CandleChart'
import { Badge, ActionBadge, MarketBadge } from '@/components/ui/Badge'
import { EventDetailModal } from '@/components/modals/EventDetailModal'
import { RecDetailModal } from '@/components/modals/RecDetailModal'
import { fmt, pctColor, probToScore, scoreBarColor } from '@/lib/utils'
import type { SupplyDemand, FeatureEvent, Recommendation } from '@/types'

interface SimilarCaseWithBars {
  event_id:      number
  code:          string
  name?:         string
  date:          string
  event_type?:   string
  similarity:    number
  return_1d?:    number
  return_3d?:    number
  return_5d?:    number
}

async function fetchSimilarCases(eventId: number): Promise<SimilarCaseWithBars[]> {
  try {
    const result = await featuresApi.getSimilarWithBars(eventId, 5, 5, 15)
    return (result.cases as unknown as SimilarCaseWithBars[]) ?? []
  } catch {
    return []
  }
}

const RECENT_KEY = 'recent_stocks'
const FAVORITE_KEY = 'fav_stocks'
const MAX_RECENT = 10

interface QuickStock { code: string; name: string }

function loadLS<T>(key: string, def: T): T {
  try { return JSON.parse(localStorage.getItem(key) || 'null') ?? def } catch { return def }
}

type ActiveTab = 'chart' | 'supply' | 'analysis' | 'financials' | 'similar'
type Period = 'D' | 'W' | 'M'

function aggregateBars(bars: import('@/types').DailyBar[], period: Period): import('@/types').DailyBar[] {
  if (period === 'D') return bars
  const groups: Record<string, import('@/types').DailyBar[]> = {}
  bars.forEach((b) => {
    const key = period === 'W'
      ? (() => { const d = new Date(b.date); const jan1 = new Date(d.getFullYear(), 0, 1); const wk = Math.ceil(((d.getTime()-jan1.getTime())/86400000 + jan1.getDay()+1)/7); return `${d.getFullYear()}-W${String(wk).padStart(2, '0')}` })()
      : b.date.substring(0, 7)
    if (!groups[key]) groups[key] = []
    groups[key].push(b)
  })
  return Object.values(groups).map((gb) => ({
    date: gb[gb.length - 1].date,
    open: gb[0].open,
    high: Math.max(...gb.map((x) => x.high)),
    low: Math.min(...gb.map((x) => x.low)),
    close: gb[gb.length - 1].close,
    volume: gb.reduce((s, x) => s + x.volume, 0),
    amount: gb.reduce((s, x) => s + (x.amount ?? 0), 0),
  })).sort((a, b) => (a.date < b.date ? -1 : 1))
}

function SupplyBar({ label, value, max }: { label: string; value: number; max: number }) {
  const pct = max > 0 ? Math.abs(value) / max * 100 : 0
  const isPos = value >= 0
  const amount = Math.abs(value) >= 100_000_000
    ? `${isPos ? '+' : '-'}${(Math.abs(value) / 100_000_000).toFixed(1)}억`
    : (value === 0 ? '—' : `${isPos ? '+' : ''}${value.toLocaleString()}`)
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-12 text-[var(--muted)] shrink-0">{label}</span>
      <div className="flex-1 h-2.5 bg-[var(--border)] rounded-full overflow-hidden">
        <div className={clsx('h-full rounded-full transition-all', isPos ? 'bg-red-400' : 'bg-blue-400')} style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
      <span className={clsx('w-20 text-right tabular font-medium', isPos ? 'text-red-400' : value < 0 ? 'text-blue-400' : 'text-[var(--muted)]')}>{amount}</span>
    </div>
  )
}

function RangeBar({ low, high, current, label }: { low: number; high: number; current: number; label: string }) {
  const pct = high > low ? ((current - low) / (high - low)) * 100 : 50
  return (
    <div>
      <div className="flex justify-between text-xs text-[var(--muted)] mb-1"><span>{label} 저 {low.toLocaleString()}</span><span>{label} 고 {high.toLocaleString()}</span></div>
      <div className="relative h-2 bg-[var(--border)] rounded-full">
        <div className="absolute inset-0 bg-gradient-to-r from-blue-500/30 via-[var(--border)] to-red-500/30 rounded-full" />
        <div className="absolute top-1/2 -translate-y-1/2 w-3 h-3 bg-white border-2 border-cyan-400 rounded-full shadow z-10" style={{ left: `calc(${Math.max(2, Math.min(98, pct))}% - 6px)` }} />
      </div>
      <div className="text-center text-xs text-cyan-400 font-semibold mt-1 tabular">{current.toLocaleString()}원 ({pct.toFixed(0)}%)</div>
    </div>
  )
}

function PriceStat({ label, value, color }: { label: string; value?: number | null; color?: string }) {
  return (
    <div className="flex flex-col gap-0.5 py-2 px-3 bg-[var(--bg)] rounded-lg">
      <span className="text-xs text-[var(--muted)]">{label}</span>
      <span className={clsx('text-sm font-semibold tabular', color ?? 'text-[var(--fg)]')}>{value != null ? value.toLocaleString() : '—'}</span>
    </div>
  )
}

function WatchlistRow({ item, active, onClick }: {
  item: WatchlistItem; active: boolean; onClick: () => void
}) {
  const chg = item.change_rate ?? 0
  const up = chg > 0; const dn = chg < 0
  return (
    <div
      onClick={onClick}
      className={clsx(
        'flex items-center justify-between px-3 py-2 border-b border-[var(--border)]/40',
        'hover:bg-[var(--border)]/25 cursor-pointer transition-colors',
        active && 'bg-cyan-500/10 border-l-2 border-l-cyan-500',
      )}
    >
      <div className="min-w-0">
        <div className="text-xs font-semibold text-[var(--fg)] truncate max-w-[120px]">{item.name}</div>
        <div className="text-[10px] text-[var(--muted)]">{item.code}</div>
      </div>
      <div className="text-right shrink-0 ml-1.5">
        {item.current_price != null && (
          <div className="text-xs font-semibold tabular text-[var(--fg)]">
            {item.current_price.toLocaleString()}
          </div>
        )}
        <div className={clsx('text-[10px] tabular font-medium',
          up ? 'text-red-400' : dn ? 'text-blue-400' : 'text-[var(--muted)]'
        )}>
          {item.change_rate != null ? `${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%` : '—'}
        </div>
      </div>
    </div>
  )
}

function OpinionText({ text }: { text: string }) {
  return (
    <div className="space-y-1.5 text-sm text-[var(--fg)] leading-relaxed">
      {text.split('\n').map((line, i) => {
        if (!line.trim()) return <div key={i} className="h-1" />
        const isStar = line.startsWith('★')
        const isBullet = line.startsWith('▸') || line.startsWith('  •')
        const isSell = line.startsWith('★ 매도')
        return (
          <div key={i} className={clsx(
            isSell ? 'text-orange-400 font-bold mt-2' :
            isStar ? 'text-cyan-400 font-bold mt-2' :
            isBullet ? 'text-[var(--fg)]' : 'text-[var(--muted)]'
          )}>
            {line}
          </div>
        )
      })}
    </div>
  )
}

export function StockSearch() {
  const { collapsed } = useSidebarStore()
  const isMobile      = useIsMobile()
  const sidebarW      = isMobile ? 0 : collapsed ? 56 : 220

  const [searchParams, setSearchParams] = useSearchParams()
  const [query, setQuery] = useState(searchParams.get('q') ?? '')
  const [market, setMarket] = useState('')
  const [selCode, setSelCode] = useState(searchParams.get('code') ?? '')
  const [recent, setRecent] = useState<QuickStock[]>(() => loadLS(RECENT_KEY, []))
  const [favs, setFavs] = useState<QuickStock[]>(() => loadLS(FAVORITE_KEY, []))
  const [tab, setTab] = useState<ActiveTab>('chart')
  const [period, setPeriod] = useState<Period>('D')
  const [showList, setShowList] = useState(true)
  const [selectedEvent, setSelectedEvent] = useState<FeatureEvent | null>(null)
  const [selectedRec, setSelectedRec] = useState<Recommendation | null>(null)
  const [purchaseInput, setPurchaseInput] = useState('')
  const [purchasePrice, setPurchasePrice] = useState<number | undefined>(undefined)
  const qc = useQueryClient()

  useEffect(() => {
    const code = searchParams.get('code')
    const q = searchParams.get('q')
    if (code) setSelCode(code)
    if (q) setQuery(q)
  }, [searchParams])

  const { data: results, isLoading: searching } = useQuery({
    queryKey: ['stock-search', query, market],
    queryFn: () => stocksApi.search(query, market || undefined),
    enabled: query.length >= 1,
    staleTime: 60_000,
  })
  const { data: stock } = useQuery({ queryKey: ['stock-detail', selCode], queryFn: () => stocksApi.getDetail(selCode), enabled: !!selCode })

  // URL 파라미터로 진입 시(외부 메뉴에서 클릭) 최근 검색 목록에 자동 추가
  useEffect(() => {
    if (!selCode || !stock) return
    setRecent((prev) => {
      if (prev[0]?.code === selCode) return prev
      const next = [{ code: selCode, name: stock.name }, ...prev.filter((r) => r.code !== selCode)].slice(0, MAX_RECENT)
      persistLS(RECENT_KEY, next)
      return next
    })
  }, [selCode, stock])
  const barsLimit = period === 'D' ? 120 : period === 'W' ? 260 : 780
  const { data: barsRaw } = useQuery({ queryKey: ['bars', selCode, period], queryFn: () => stocksApi.getDailyBars(selCode, barsLimit), enabled: !!selCode })
  const { data: quote } = useQuery({ queryKey: ['quote', selCode], queryFn: () => stocksApi.getQuote(selCode), enabled: !!selCode, refetchInterval: 10_000 })
  const todayKST = new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10)
  const rawForChart = (() => {
    if (!barsRaw) return undefined
    if (!quote?.price || quote.source === 'daily' || quote.source === 'none') return barsRaw
    const last = barsRaw[barsRaw.length - 1]
    const todayBar = {
      date: todayKST,
      open:   quote.open  ?? last?.close ?? quote.price,
      high:   Math.max(quote.high ?? quote.price, quote.price),
      low:    Math.min(quote.low  ?? quote.price, quote.price),
      close:  quote.price,
      volume: quote.volume ?? 0,
      amount: quote.amount ?? 0,
    }
    return last?.date === todayKST
      ? [...barsRaw.slice(0, -1), todayBar]
      : [...barsRaw, todayBar]
  })()
  const bars = rawForChart ? aggregateBars(rawForChart, period) : undefined
  const { data: supply } = useQuery({ queryKey: ['supply', selCode], queryFn: () => stocksApi.getSupply(selCode, 30), enabled: !!selCode && tab === 'supply' })
  const { data: events } = useQuery({ queryKey: ['events-by-code', selCode], queryFn: () => featuresApi.list({ code: selCode, hours: 168, limit: 20 }), enabled: !!selCode, refetchInterval: 60_000 })
  const { data: latestRec } = useQuery({ queryKey: ['rec-latest', selCode], queryFn: () => recommendationsApi.getLatestByCode(selCode), enabled: !!selCode, refetchInterval: 60_000 })
  const { data: analysis, isLoading: analysisLoading } = useQuery({
    queryKey: ['analysis', selCode, purchasePrice],
    queryFn: () => stocksApi.getAnalysis(selCode, purchasePrice),
    enabled: !!selCode && tab === 'analysis',
    staleTime: 120_000,
  })

  const { data: financials = [], isLoading: financialsLoading } = useQuery({
    queryKey: ['financials', selCode],
    queryFn: () => stocksApi.getFinancials(selCode),
    enabled: !!selCode && tab === 'financials',
    staleTime: 3_600_000,
  })

  const { data: watchlist = [] } = useQuery({
    queryKey:        ['watchlist'],
    queryFn:         () => watchlistApi.list(),
    refetchInterval: 60_000,
    staleTime:       30_000,
  })

  // 서버 관심종목 기준 (localStorage favs 는 레거시 보조용)
  const isFav = watchlist.some((w) => w.code === selCode)

  function persistLS(key: string, val: unknown) { localStorage.setItem(key, JSON.stringify(val)) }

  function selectCode(code: string, name?: string) {
    setSelCode(code); setSearchParams({ code }); setTab('chart')
    stocksApi.watchStock(code).catch(() => {})
    if (name) {
      const next = [{ code, name }, ...recent.filter((r) => r.code !== code)].slice(0, MAX_RECENT)
      setRecent(next); persistLS(RECENT_KEY, next)
    }
  }

  function toggleFav() {
    if (!selCode || !stock) return
    if (isFav) {
      const next = favs.filter((f) => f.code !== selCode)
      setFavs(next); persistLS(FAVORITE_KEY, next)
      watchlistApi.remove(selCode).catch(() => {})
      qc.invalidateQueries({ queryKey: ['watchlist'] })
    } else {
      const next = [{ code: selCode, name: stock.name }, ...favs].slice(0, 30)
      setFavs(next); persistLS(FAVORITE_KEY, next)
      watchlistApi.add(selCode).then(() => qc.invalidateQueries({ queryKey: ['watchlist'] })).catch(() => {})
    }
  }

  function applyPurchasePrice() {
    const v = parseFloat(purchaseInput.replace(/,/g, ''))
    setPurchasePrice(!isNaN(v) && v > 0 ? v : undefined)
  }

  const price = quote?.price ?? (bars?.length ? bars[bars.length - 1]?.close : null)
  const prevClose = quote?.prev_close ?? null
  const change = quote?.change ?? null
  const changeRate = quote?.change_rate ?? null
  const isUp = (changeRate ?? 0) > 0
  const isDn = (changeRate ?? 0) < 0
  const priceColor = isUp ? 'text-red-400' : isDn ? 'text-blue-400' : 'text-[var(--fg)]'
  const source = quote?.source ?? 'none'
  const openP = quote?.open ?? bars?.slice(-1)[0]?.open
  const highP = quote?.high ?? bars?.slice(-1)[0]?.high
  const lowP = quote?.low ?? bars?.slice(-1)[0]?.low
  const volP = quote?.volume ?? bars?.slice(-1)[0]?.volume
  const amtP = quote?.amount ?? bars?.slice(-1)[0]?.amount
  const year52 = barsRaw?.length ? { high: Math.max(...barsRaw.map((b) => b.high)), low: Math.min(...barsRaw.map((b) => b.low)) } : null
  const limitUp = prevClose ? Math.round(prevClose * 1.3 / 10) * 10 : null
  const limitDown = prevClose ? Math.round(prevClose * 0.7 / 10) * 10 : null
  const supplyMax = supply?.length ? Math.max(1, ...supply.map((s: SupplyDemand) => Math.max(Math.abs(s.foreign_net ?? 0), Math.abs(s.inst_net ?? 0), Math.abs(s.indiv_net ?? 0)))) : 1
  const recentSupply = supply?.slice(-5).reverse() ?? []

  return (
    <div className="flex h-full gap-0 overflow-hidden">
      {showList && (
        <div className="w-64 flex-shrink-0 flex flex-col border-r border-[var(--border)] bg-[var(--card)]">
          <div className="p-3 border-b border-[var(--border)] space-y-2">
            <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-[var(--bg)] border border-[var(--border)] rounded-lg">
              <Search size={12} className="text-[var(--muted)] shrink-0" />
              <input value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && setSearchParams({ q: query })} placeholder="종목명 / 코드" className="flex-1 bg-transparent text-xs text-[var(--fg)] placeholder:text-[var(--muted)] focus:outline-none min-w-0" />
              {query && <button onClick={() => { setQuery(''); setSearchParams({}) }} className="text-[var(--muted)] hover:text-[var(--fg)]"><X size={11} /></button>}
            </div>
            <select value={market} onChange={(e) => setMarket(e.target.value)} className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-md px-2.5 py-1 text-xs text-[var(--fg)] focus:outline-none">
              <option value="">전체 시장</option><option value="KOSPI">KOSPI</option><option value="KOSDAQ">KOSDAQ</option>
            </select>
          </div>
          <div className="flex-1 overflow-y-auto">
            {!query && watchlist.length > 0 && (<>
              <div className="px-3 py-2 text-xs font-semibold text-[var(--muted)] uppercase tracking-widest flex items-center justify-between">
                <span className="flex items-center gap-1"><Star size={9} className="text-yellow-400" />관심종목</span>
                <span className="tabular">{watchlist.length}</span>
              </div>
              {watchlist.map((item) => (
                <WatchlistRow
                  key={item.code}
                  item={item}
                  active={selCode === item.code}
                  onClick={() => selectCode(item.code, item.name)}
                />
              ))}
            </>)}
            {!query && (<>
              <div className="px-3 py-2 text-xs font-semibold text-[var(--muted)] uppercase tracking-widest flex items-center justify-between">
                <span className="flex items-center gap-1"><Clock size={9} />최근 검색</span>
                {recent.length > 0 && <button onClick={() => { setRecent([]); persistLS(RECENT_KEY, []) }} className="flex items-center gap-0.5 hover:text-red-400"><Trash2 size={8} />전체삭제</button>}
              </div>
              {recent.length === 0 ? <div className="py-4 text-center text-xs text-[var(--muted)]">검색 기록 없음</div>
                : recent.map((r) => <ListRow key={r.code} code={r.code} name={r.name} active={selCode === r.code} onClick={() => selectCode(r.code)} onRemove={() => { const n = recent.filter((x) => x.code !== r.code); setRecent(n); persistLS(RECENT_KEY, n) }} />)}
            </>)}
            {query && (<>
              <div className="px-3 py-2 text-xs font-semibold text-[var(--muted)] uppercase tracking-widest flex items-center justify-between">
                <span>검색 결과</span>
                {searching ? <span className="text-cyan-400">검색 중…</span> : <span className="tabular">{results?.length ?? 0}건</span>}
              </div>
              {results?.map((s) => (
                <div key={s.code} onClick={() => selectCode(s.code, s.name)} className={clsx('flex items-center justify-between px-3 py-2.5 border-b border-[var(--border)]/40 hover:bg-[var(--border)]/25 cursor-pointer transition-colors text-xs', selCode === s.code && 'bg-cyan-500/10 border-l-2 border-l-cyan-500')}>
                  <div><div className="font-semibold text-[var(--fg)] truncate max-w-[130px]">{s.name}</div><div className="flex items-center gap-1 mt-0.5"><span className="text-[var(--muted)] text-xs">{s.code}</span><MarketBadge market={s.market} /></div></div>
                  <ChevronRight size={12} className="text-[var(--muted)]" />
                </div>
              ))}
              {!searching && results?.length === 0 && <div className="py-6 text-center text-xs text-[var(--muted)]">"{query}" 결과 없음</div>}
            </>)}
          </div>
        </div>
      )}
      <div className="flex-1 overflow-y-auto min-w-0">
        <button onClick={() => setShowList((v) => !v)} className="fixed top-1/2 z-20 bg-[var(--card)] border border-[var(--border)] rounded-r-md p-1 text-[var(--muted)] hover:text-[var(--fg)] transition-colors -translate-y-1/2" style={{ left: showList ? sidebarW + 256 : sidebarW }} title={showList ? '목록 숨기기' : '목록 보기'}>
          {showList ? <PanelLeftClose size={13} /> : <PanelLeftOpen size={13} />}
        </button>
        {!selCode ? (
          <div className="flex flex-col items-center justify-center h-full gap-4 text-[var(--muted)]"><Search size={40} className="opacity-20" /><div className="text-center"><p className="text-sm font-medium">종목을 선택하세요</p><p className="text-xs mt-1">검색 또는 최근 검색 목록에서 종목을 클릭하세요</p></div></div>
        ) : (
          <div className="p-4 space-y-3">
            <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h1 className="text-xl font-bold text-[var(--fg)]">{stock?.name ?? selCode}</h1>
                    {stock?.market && <MarketBadge market={stock.market} />}
                    {stock?.is_trading_halt && <span className="text-xs px-1.5 py-0.5 rounded bg-red-500/20 text-red-400 border border-red-500/30">거래정지</span>}
                    {source === 'realtime' && <span className="text-xs px-1.5 py-0.5 rounded bg-green-500/10 text-green-400 border border-green-500/20 animate-pulse">실시간</span>}
                    {source === 'intraday' && <span className="text-xs px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">장중시세</span>}
                    {source === 'daily' && <span className="text-xs px-1.5 py-0.5 rounded bg-yellow-500/10 text-yellow-400 border border-yellow-500/20">전일 종가</span>}
                  </div>
                  <div className="flex items-center gap-2 mt-0.5 text-xs text-[var(--muted)]"><span>{selCode}</span>{stock?.sector && <><span>·</span><span>{stock.sector}</span></>}{stock?.industry && <><span>·</span><span>{stock.industry}</span></>}</div>
                </div>
                <button onClick={toggleFav} className={clsx('shrink-0 p-1.5 rounded-lg transition-colors', isFav ? 'text-yellow-400 hover:text-yellow-300' : 'text-[var(--muted)] hover:text-yellow-400')} title={isFav ? '관심종목 해제' : '관심종목 추가 (자동 등록)'}>
                  {isFav ? <Star size={16} fill="currentColor" /> : <StarOff size={16} />}
                </button>
              </div>
              <div className="mt-3 flex flex-wrap items-end gap-3">
                <div className={clsx('text-4xl font-bold tabular', priceColor)}>{price != null ? price.toLocaleString() : '—'}<span className="text-lg font-normal ml-1 text-[var(--muted)]">원</span></div>
                <div className="flex items-center gap-2 pb-1">
                  <span className={clsx('flex items-center gap-0.5 text-lg font-semibold tabular', priceColor)}>{isUp ? <TrendingUp size={16} /> : isDn ? <TrendingDown size={16} /> : <Minus size={16} />}{change != null ? `${change >= 0 ? '+' : ''}${change.toLocaleString()}` : '—'}</span>
                  <span className={clsx('text-base font-semibold tabular px-2 py-0.5 rounded', isUp ? 'bg-red-500/15 text-red-400' : isDn ? 'bg-blue-500/15 text-blue-400' : 'text-[var(--muted)]')}>{changeRate != null ? `${changeRate >= 0 ? '+' : ''}${changeRate.toFixed(2)}%` : '—'}</span>
                </div>
              </div>
              <div className="mt-3 grid grid-cols-4 gap-1.5">
                <PriceStat label="전일" value={prevClose} /><PriceStat label="시가" value={openP} />
                <PriceStat label="고가" value={highP} color="text-red-400" /><PriceStat label="저가" value={lowP} color="text-blue-400" />
                <PriceStat label="거래량" value={volP} />
                <div className="flex flex-col gap-0.5 py-2 px-3 bg-[var(--bg)] rounded-lg"><span className="text-xs text-[var(--muted)]">거래대금</span><span className="text-sm font-semibold tabular text-[var(--fg)]">{fmt.amount(amtP)}</span></div>
                <PriceStat label="상한가" value={limitUp} color="text-red-400" /><PriceStat label="하한가" value={limitDown} color="text-blue-400" />
              </div>
              {year52 && price != null && <div className="mt-3 pt-3 border-t border-[var(--border)]"><RangeBar low={year52.low} high={year52.high} current={price} label="52주" /></div>}
            </div>
            <div className="flex gap-1 bg-[var(--card)] border border-[var(--border)] rounded-xl p-1">
              {(['chart', 'supply', 'analysis', 'financials', 'similar'] as ActiveTab[]).map((t) => (
                <button key={t} onClick={() => setTab(t)} className={clsx('flex-1 py-1.5 text-xs font-medium rounded-lg transition-colors', tab === t ? 'bg-cyan-500/20 text-cyan-400' : 'text-[var(--muted)] hover:text-[var(--fg)]')}>
                  {t === 'chart' ? '차트' : t === 'supply' ? '수급' : t === 'analysis' ? '분석' : t === 'financials' ? '재무' : '유사사례'}
                </button>
              ))}
            </div>
            {tab === 'chart' && (
              <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-[var(--fg)]">{period === 'D' ? '일봉' : period === 'W' ? '주봉' : '월봉'} ({bars?.length ?? 0}봉)</span>
                    <div className="flex gap-0.5">{(['D', 'W', 'M'] as Period[]).map((p) => (<button key={p} onClick={() => setPeriod(p)} className={clsx('px-2 py-0.5 text-xs font-semibold rounded transition-colors', period === p ? 'bg-cyan-500/20 text-cyan-400' : 'text-[var(--muted)] hover:text-[var(--fg)]')}>{p === 'D' ? '일' : p === 'W' ? '주' : '월'}</button>))}</div>
                  </div>
                  <div className="flex items-center gap-3 text-xs">
                    <span className="flex items-center gap-1"><span className="w-4 h-0.5 bg-yellow-400 inline-block" />MA5</span>
                    <span className="flex items-center gap-1"><span className="w-4 h-0.5 bg-sky-400 inline-block" />MA20</span>
                    <span className="flex items-center gap-1"><span className="w-4 h-0.5 bg-orange-400 inline-block" />MA60</span>
                  </div>
                </div>
                {bars && bars.length > 0 ? <CandleChart data={bars} height={300} showMA /> : <div className="h-48 flex items-center justify-center text-[var(--muted)] text-sm">차트 데이터 없음</div>}
              </div>
            )}
            {tab === 'supply' && (
              <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4">
                <div className="text-sm font-semibold text-[var(--fg)] mb-4">최근 수급 현황 (최근 5영업일)</div>
                {recentSupply.length > 0 ? (
                  <div className="space-y-4">{recentSupply.map((s: SupplyDemand) => (<div key={s.date} className="space-y-1.5"><div className="text-xs font-semibold text-[var(--fg)]/70 mb-1">{s.date}</div><SupplyBar label="외국인" value={s.foreign_net ?? 0} max={supplyMax} /><SupplyBar label="기관" value={s.inst_net ?? 0} max={supplyMax} /><SupplyBar label="개인" value={s.indiv_net ?? 0} max={supplyMax} /></div>))}</div>
                ) : <div className="py-12 text-center text-sm text-[var(--muted)]">수급 데이터 없음</div>}
                {supply && supply.length > 0 && (() => {
                  const totF = supply.reduce((s: number, r: SupplyDemand) => s + (r.foreign_net ?? 0), 0)
                  const totI = supply.reduce((s: number, r: SupplyDemand) => s + (r.inst_net ?? 0), 0)
                  const totP = supply.reduce((s: number, r: SupplyDemand) => s + (r.indiv_net ?? 0), 0)
                  const totMax = Math.max(Math.abs(totF), Math.abs(totI), Math.abs(totP), 1)
                  return (<div className="mt-5 pt-4 border-t border-[var(--border)] space-y-1.5"><div className="text-xs font-semibold text-[var(--muted)] mb-2">30일 누적</div><SupplyBar label="외국인" value={totF} max={totMax} /><SupplyBar label="기관" value={totI} max={totMax} /><SupplyBar label="개인" value={totP} max={totMax} /></div>)
                })()}
              </div>
            )}
            {tab === 'analysis' && (
              <div className="space-y-3">
                {/* 매수가 입력 */}
                <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4">
                  <div className="text-sm font-semibold text-[var(--fg)] mb-3 flex items-center gap-2">
                    <ShoppingCart size={14} className="text-orange-400" />매수가 입력 (보유 중인 경우 매도 전략 제공)
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      value={purchaseInput}
                      onChange={(e) => setPurchaseInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && applyPurchasePrice()}
                      placeholder="예: 75000"
                      className="flex-1 bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-[var(--fg)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-500 tabular"
                    />
                    <button
                      onClick={applyPurchasePrice}
                      className="px-4 py-2 rounded-lg text-sm font-semibold bg-orange-500/15 text-orange-400 border border-orange-500/30 hover:bg-orange-500/25 transition-colors"
                    >
                      분석
                    </button>
                    {purchasePrice && (
                      <button
                        onClick={() => { setPurchasePrice(undefined); setPurchaseInput('') }}
                        className="px-3 py-2 rounded-lg text-sm text-[var(--muted)] hover:text-red-400 border border-[var(--border)] hover:border-red-500/30 transition-colors"
                      >
                        <X size={14} />
                      </button>
                    )}
                  </div>
                  {purchasePrice && (
                    <div className="mt-2 text-xs text-orange-400 font-medium">
                      매수가 {purchasePrice.toLocaleString()}원 기준 분석 적용 중
                    </div>
                  )}
                </div>

                {/* 종합의견 */}
                <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4">
                  <div className="text-sm font-semibold text-[var(--fg)] mb-3 flex items-center gap-2">
                    <BarChart2 size={14} />종합 분석 의견
                  </div>
                  {analysisLoading ? (
                    <div className="py-8 text-center text-xs text-[var(--muted)]">분석 중...</div>
                  ) : analysis?.opinion ? (
                    <OpinionText text={analysis.opinion} />
                  ) : (
                    <div className="py-6 text-center text-xs text-[var(--muted)]">분석 데이터 없음</div>
                  )}
                </div>

                {/* 최근 이벤트 */}
                <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4">
                  <div className="text-sm font-semibold text-[var(--fg)] mb-3 flex items-center gap-2"><BarChart2 size={14} />최근 이벤트 (7일) · 이벤트 클릭 시 상세</div>
                  {events && events.length > 0 ? (
                    <div className="space-y-2">{events.slice(0, 10).map((ev) => (
                      <div key={ev.id} className="flex items-center justify-between py-1.5 border-b border-[var(--border)]/50 last:border-0">
                        <div className="flex items-center gap-2">
                          <button onClick={() => setSelectedEvent(ev)} className="hover:scale-105 transition-transform" title="이벤트 상세"><Badge eventType={ev.event_type} size="sm" /></button>
                          {ev.signal_score != null && <span className="text-xs text-[var(--muted)] tabular">점수 {ev.signal_score.toFixed(2)}</span>}
                        </div>
                        <div className="flex items-center gap-3 text-right text-xs">
                          <span className={clsx('tabular font-semibold', pctColor(ev.change_rate))}>{fmt.pct(ev.change_rate)}</span>
                          <span className="text-[var(--muted)] text-xs">{fmt.dateTime(ev.detected_at)}</span>
                        </div>
                      </div>
                    ))}</div>
                  ) : <div className="py-6 text-center text-xs text-[var(--muted)]">최근 이벤트 없음</div>}
                </div>

                {/* ML 추천 신호 */}
                <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4">
                  <div className="text-sm font-semibold text-[var(--fg)] mb-3">ML 추천 신호 · 클릭 시 상세</div>
                  {latestRec ? (
                    <div className="space-y-3 cursor-pointer hover:bg-[var(--border)]/15 rounded-lg p-2 -m-2 transition-colors" onClick={() => setSelectedRec(latestRec)} title="클릭하여 상세 보기">
                      <div className="flex items-center justify-between"><ActionBadge action={latestRec.action} /><span className="text-xs text-[var(--muted)]">{fmt.dateTime(latestRec.created_at)}</span></div>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-2 bg-[var(--border)] rounded-full overflow-hidden"><div className={clsx('h-full rounded-full', scoreBarColor(probToScore(latestRec.success_prob)))} style={{ width: `${probToScore(latestRec.success_prob)}%` }} /></div>
                        <span className={clsx('text-sm font-bold tabular', scoreBarColor(probToScore(latestRec.success_prob)).replace('bg-', 'text-'))}>{probToScore(latestRec.success_prob)}점</span>
                        <span className="text-xs text-[var(--muted)] tabular">ML {(latestRec.success_prob * 100).toFixed(1)}%</span>
                      </div>
                      <div className="grid grid-cols-3 gap-2 text-center">
                        <div className="bg-[var(--bg)] rounded-lg p-2"><div className="text-xs text-[var(--muted)]">진입가(매수)</div><div className="text-xs font-bold tabular mt-0.5 text-[var(--fg)]">{fmt.price(latestRec.entry_price)}</div></div>
                        <div className="bg-red-500/10 rounded-lg p-2 border border-red-500/20"><div className="text-xs text-red-400">목표가(매도)</div><div className="text-xs font-bold tabular mt-0.5 text-red-400">{fmt.price(latestRec.target_price)}</div></div>
                        <div className="bg-blue-500/10 rounded-lg p-2 border border-blue-500/20"><div className="text-xs text-blue-400">손절가</div><div className="text-xs font-bold tabular mt-0.5 text-blue-400">{fmt.price(latestRec.stop_loss_price)}</div></div>
                      </div>
                      {latestRec.risk_reward_ratio && <div className="text-xs text-[var(--muted)] text-right">R:R {latestRec.risk_reward_ratio.toFixed(1)} · 예상 {latestRec.expected_hold_days}일</div>}
                    </div>
                  ) : <div className="py-6 text-center text-xs text-[var(--muted)]">추천 데이터 없음</div>}
                </div>

                {/* 기업 정보 */}
                {stock && (
                  <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4">
                    <div className="text-sm font-semibold text-[var(--fg)] mb-3">기업 정보</div>
                    <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                      {[['종목코드',stock.code],['시장',stock.market],['섹터',stock.sector??'—'],['업종',stock.industry??'—'],['거래상태',stock.is_trading_halt?'거래정지':'정상'],['상장주식수',stock.shares_total?`${(stock.shares_total/1_000_000).toFixed(1)}백만주`:'—']].map(([label,value])=>(
                        <div key={label} className="flex items-center justify-between py-1.5 border-b border-[var(--border)]/40"><span className="text-[var(--muted)]">{label}</span><span className="font-medium text-[var(--fg)]">{value}</span></div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
            {tab === 'financials' && (
              <FinancialsTab data={financials} loading={financialsLoading} />
            )}
            {tab === 'similar' && (
              <SimilarTab code={selCode} events={events} />
            )}
          </div>
        )}
      </div>
      {selectedEvent && <EventDetailModal event={selectedEvent} onClose={() => setSelectedEvent(null)} onGoDetail={() => setSelectedEvent(null)} />}
      {selectedRec && <RecDetailModal rec={selectedRec} onClose={() => setSelectedRec(null)} onGoDetail={() => setSelectedRec(null)} />}
    </div>
  )
}

// ── 유사사례 탭 ─────────────────────────────────────────────────────────────
function SimilarTab({ code, events }: { code: string; events?: FeatureEvent[] }) {
  // 최근 이벤트 중 첫 번째를 유사사례 조회에 사용
  const latestEvent = events?.[0]

  const { data: similar, isLoading } = useQuery({
    queryKey:  ['similar-cases', latestEvent?.id],
    queryFn:   () => fetchSimilarCases(latestEvent!.id),
    enabled:   !!latestEvent,
    staleTime: 300_000,
  })

  if (!latestEvent) {
    return (
      <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-8 text-center">
        <History size={28} className="text-[var(--muted)]/40 mx-auto mb-2" />
        <div className="text-sm text-[var(--muted)]">최근 탐지 이벤트가 없습니다</div>
        <div className="text-xs text-[var(--muted)]/60 mt-1">특징주 탐지 이후 유사사례를 확인할 수 있습니다</div>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {/* 기준 이벤트 */}
      <div className="bg-[var(--card)] border border-cyan-500/20 rounded-xl p-4">
        <div className="flex items-center gap-2 mb-1">
          <History size={14} className="text-cyan-400" />
          <span className="text-sm font-semibold text-[var(--fg)]">유사사례 기준 이벤트</span>
        </div>
        <div className="flex items-center gap-2 text-xs text-[var(--muted)]">
          <Badge eventType={latestEvent.event_type} size="sm" />
          <span>탐지: {fmt.dateTime(latestEvent.detected_at)}</span>
          {latestEvent.signal_score != null && <span>점수 {latestEvent.signal_score.toFixed(2)}</span>}
        </div>
      </div>

      {/* 유사사례 리스트 */}
      <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-[var(--border)] text-sm font-semibold text-[var(--fg)]">
          과거 유사 패턴 {isLoading ? '…' : `${similar?.length ?? 0}건`}
        </div>
        {isLoading && (
          <div className="space-y-2 p-4">
            {Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-8 skeleton rounded" />)}
          </div>
        )}
        {!isLoading && (!similar || similar.length === 0) && (
          <div className="py-12 text-center text-sm text-[var(--muted)]">유사사례 데이터 없음</div>
        )}
        {similar && similar.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] text-[var(--muted)] bg-[var(--bg)]/40">
                  <th className="text-left py-2.5 pl-5 pr-3 text-xs font-semibold uppercase tracking-wider">종목</th>
                  <th className="text-left py-2.5 pr-3 text-xs font-semibold uppercase tracking-wider">날짜</th>
                  <th className="text-left py-2.5 pr-3 text-xs font-semibold uppercase tracking-wider">이벤트</th>
                  <th className="text-right py-2.5 pr-3 text-xs font-semibold uppercase tracking-wider">유사도</th>
                  <th className="text-right py-2.5 pr-3 text-xs font-semibold uppercase tracking-wider">1D</th>
                  <th className="text-right py-2.5 pr-3 text-xs font-semibold uppercase tracking-wider">3D</th>
                  <th className="text-right py-2.5 pr-5 text-xs font-semibold uppercase tracking-wider">5D</th>
                </tr>
              </thead>
              <tbody>
                {similar.map((s, i) => (
                  <tr key={i} className="border-b border-[var(--border)]/50 hover:bg-[var(--border)]/25">
                    <td className="py-2.5 pl-5 pr-3">
                      <div className="text-sm font-semibold text-[var(--fg)]">{s.name ?? s.code}</div>
                      <div className="text-xs text-[var(--muted)]">{s.code}</div>
                    </td>
                    <td className="py-2.5 pr-3 text-xs text-[var(--muted)] whitespace-nowrap">{s.date}</td>
                    <td className="py-2.5 pr-3">
                      {s.event_type ? <Badge eventType={s.event_type} size="sm" /> : <span className="text-[var(--muted)]">—</span>}
                    </td>
                    <td className="py-2.5 pr-3 text-right tabular text-cyan-400 font-semibold">
                      {(s.similarity * 100).toFixed(0)}%
                    </td>
                    <td className={clsx('py-2.5 pr-3 text-right tabular font-semibold', pctColor(s.return_1d))}>
                      {s.return_1d != null ? fmt.pct(s.return_1d) : '—'}
                    </td>
                    <td className={clsx('py-2.5 pr-3 text-right tabular font-semibold', pctColor(s.return_3d))}>
                      {s.return_3d != null ? fmt.pct(s.return_3d) : '—'}
                    </td>
                    <td className={clsx('py-2.5 pr-5 text-right tabular font-semibold', pctColor(s.return_5d))}>
                      {s.return_5d != null ? fmt.pct(s.return_5d) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

const FIN_TOOLTIP_STYLE = {
  background: 'var(--card)', border: '1px solid var(--border)',
  borderRadius: 8, fontSize: 12, color: 'var(--fg)',
}

function fmtBillion(v: number | null | undefined) {
  if (v == null) return '—'
  const abs = Math.abs(v)
  if (abs >= 1_000_000_000_000) return `${(v / 1_000_000_000_000).toFixed(1)}조`
  if (abs >= 100_000_000) return `${(v / 100_000_000).toFixed(0)}억`
  return `${v.toLocaleString()}`
}

function FinancialsTab({ data, loading }: { data: FinancialItem[]; loading: boolean }) {
  const chartData = [...data].reverse().map((f) => ({
    label: f.quarter ? `${f.year}Q${f.quarter}` : `${f.year}`,
    revenue:          f.revenue          != null ? Math.round(f.revenue / 100_000_000)          : null,
    operating_profit: f.operating_profit != null ? Math.round(f.operating_profit / 100_000_000) : null,
    net_profit:       f.net_profit       != null ? Math.round(f.net_profit / 100_000_000)       : null,
  }))

  const latest = data[0]

  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-12 skeleton rounded" />)}
      </div>
    )
  }

  if (!data.length) {
    return (
      <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-8 text-center text-sm text-[var(--muted)]">
        재무 데이터가 없습니다
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {/* 밸류에이션 요약 */}
      {latest && (
        <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4">
          <div className="text-sm font-semibold text-[var(--fg)] mb-3 flex items-center gap-2">
            <BookOpen size={14} className="text-cyan-400" />
            밸류에이션 ({latest.quarter ? `${latest.year}Q${latest.quarter}` : `${latest.year}`} 기준)
          </div>
          <div className="grid grid-cols-3 gap-2">
            {[
              { label: 'PER', value: latest.per != null ? `${latest.per.toFixed(1)}배` : '—', color: latest.per != null && latest.per < 15 ? 'text-green-400' : latest.per != null && latest.per > 30 ? 'text-red-400' : 'text-[var(--fg)]' },
              { label: 'PBR', value: latest.pbr != null ? `${latest.pbr.toFixed(2)}배` : '—', color: latest.pbr != null && latest.pbr < 1 ? 'text-green-400' : 'text-[var(--fg)]' },
              { label: 'ROE', value: latest.roe != null ? `${latest.roe.toFixed(1)}%` : '—', color: latest.roe != null && latest.roe > 15 ? 'text-green-400' : latest.roe != null && latest.roe < 0 ? 'text-red-400' : 'text-[var(--fg)]' },
              { label: 'EPS', value: latest.eps != null ? `${latest.eps.toLocaleString()}원` : '—', color: 'text-[var(--fg)]' },
              { label: 'BPS', value: latest.bps != null ? `${latest.bps.toLocaleString()}원` : '—', color: 'text-[var(--fg)]' },
              { label: '부채비율', value: latest.debt_ratio != null ? `${latest.debt_ratio.toFixed(1)}%` : '—', color: latest.debt_ratio != null && latest.debt_ratio > 200 ? 'text-red-400' : 'text-[var(--fg)]' },
            ].map(({ label, value, color }) => (
              <div key={label} className="flex flex-col gap-0.5 py-2 px-3 bg-[var(--bg)] rounded-lg">
                <span className="text-xs text-[var(--muted)]">{label}</span>
                <span className={clsx('text-sm font-bold tabular', color)}>{value}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 분기 실적 차트 */}
      <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4">
        <div className="text-sm font-semibold text-[var(--fg)] mb-3">분기 실적 (억원)</div>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#71717a' }} />
            <YAxis tick={{ fontSize: 11, fill: '#71717a' }} tickFormatter={(v) => `${v.toLocaleString()}`} />
            <Tooltip contentStyle={FIN_TOOLTIP_STYLE} formatter={(v: number, name: string) => [`${v.toLocaleString()}억`, name === 'revenue' ? '매출' : name === 'operating_profit' ? '영업이익' : '순이익']} />
            <Legend formatter={(v) => v === 'revenue' ? '매출' : v === 'operating_profit' ? '영업이익' : '순이익'} wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="revenue" fill="#22d3ee" radius={[2, 2, 0, 0]} />
            <Bar dataKey="operating_profit" fill="#4ade80" radius={[2, 2, 0, 0]} />
            <Bar dataKey="net_profit" fill="#f59e0b" radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* 분기별 테이블 */}
      <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4">
        <div className="text-sm font-semibold text-[var(--fg)] mb-3">분기별 재무 상세</div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-[var(--muted)] border-b border-[var(--border)]">
                <th className="text-left py-2 font-medium">기간</th>
                <th className="text-right py-2 font-medium">매출</th>
                <th className="text-right py-2 font-medium">영업이익</th>
                <th className="text-right py-2 font-medium">순이익</th>
                <th className="text-right py-2 font-medium">영업이익률</th>
                <th className="text-right py-2 font-medium">ROE</th>
                <th className="text-right py-2 font-medium">PER</th>
                <th className="text-right py-2 font-medium">PBR</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {data.map((f, i) => {
                const label = f.quarter ? `${f.year}Q${f.quarter}` : `${f.year}`
                const opMargin = f.revenue && f.operating_profit != null
                  ? (f.operating_profit / f.revenue * 100) : null
                return (
                  <tr key={i} className="hover:bg-white/5">
                    <td className="py-2 font-semibold text-[var(--fg)]">{label}</td>
                    <td className="py-2 text-right tabular text-[var(--fg)]">{fmtBillion(f.revenue)}</td>
                    <td className={clsx('py-2 text-right tabular font-medium', f.operating_profit != null && f.operating_profit >= 0 ? 'text-green-400' : 'text-red-400')}>
                      {fmtBillion(f.operating_profit)}
                    </td>
                    <td className={clsx('py-2 text-right tabular font-medium', f.net_profit != null && f.net_profit >= 0 ? 'text-green-400' : 'text-red-400')}>
                      {fmtBillion(f.net_profit)}
                    </td>
                    <td className={clsx('py-2 text-right tabular', opMargin != null && opMargin >= 0 ? 'text-green-400' : 'text-red-400')}>
                      {opMargin != null ? `${opMargin.toFixed(1)}%` : '—'}
                    </td>
                    <td className={clsx('py-2 text-right tabular', f.roe != null && f.roe > 0 ? 'text-green-400' : 'text-[var(--fg)]')}>
                      {f.roe != null ? `${f.roe.toFixed(1)}%` : '—'}
                    </td>
                    <td className="py-2 text-right tabular text-[var(--fg)]">{f.per != null ? `${f.per.toFixed(1)}x` : '—'}</td>
                    <td className="py-2 text-right tabular text-[var(--fg)]">{f.pbr != null ? `${f.pbr.toFixed(2)}x` : '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function ListRow({ code, name, active, onClick, onRemove }: { code: string; name: string; active: boolean; onClick: () => void; onRemove?: () => void }) {
  return (
    <div onClick={onClick} className={clsx('flex items-center justify-between px-3 py-2.5 border-b border-[var(--border)]/40 hover:bg-[var(--border)]/25 cursor-pointer transition-colors group', active && 'bg-cyan-500/10 border-l-2 border-l-cyan-500')}>
      <div className="min-w-0"><div className="text-xs font-semibold text-[var(--fg)] truncate">{name}</div><div className="text-xs text-[var(--muted)]">{code}</div></div>
      {onRemove && <button onClick={(e) => { e.stopPropagation(); onRemove() }} className="opacity-0 group-hover:opacity-100 text-[var(--muted)] hover:text-red-400 transition-all shrink-0 ml-1"><X size={11} /></button>}
    </div>
  )
}
