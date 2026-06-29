import { useEffect, useRef, useState, useMemo, useCallback } from 'react'
import { createChart, ColorType } from 'lightweight-charts'
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, ResponsiveContainer,
  ReferenceLine, Tooltip,
} from 'recharts'
import type { DailyBar } from '@/types'
import { useThemeStore } from '@/store/theme'
import { clsx } from 'clsx'

export interface ChartEvent {
  date:  string
  type:  string
  score: number
}

interface CandleChartProps {
  data:       DailyBar[]
  height?:    number
  showMA?:    boolean
  events?:    ChartEvent[]
  className?: string
}

// ── 네이버 스타일 색상 ────────────────────────────────────────────────────────
const NAVER = {
  up:     '#d60000',   // 양봉 (진한 빨강)
  down:   '#0051c2',   // 음봉 (진한 파랑)
  flat:   '#555555',   // 보합봉
  ma5:    '#ff9500',   // MA5  주황
  ma20:   '#7b00a6',   // MA20 보라
  ma60:   '#0073e6',   // MA60 파랑
  ma120:  '#00a050',   // MA120 초록
  bb:     'rgba(168,85,247,0.55)',
}

const EVENT_MARKER_COLOR: Record<string, string> = {
  VI_TRIGGERED:          '#a78bfa',
  VOLUME_SURGE:          '#fbbf24',
  AMOUNT_SURGE:          '#f59e0b',
  BREAKOUT_52W:          '#34d399',
  BREAKOUT_26W:          '#34d399',
  BREAKOUT_13W:          '#6ee7b7',
  BREAKOUT_20D:          '#6ee7b7',
  LONG_WHITE_CANDLE:     '#ef4444',
  HAMMER_CANDLE:         '#f87171',
  MORNING_STAR:          '#fb923c',
  SUPPLY_ANOMALY:        '#38bdf8',
  POST_DISCLOSURE_SURGE: '#e879f9',
}

function eventLabel(type: string): string {
  const MAP: Record<string, string> = {
    VI_TRIGGERED: 'VI', VOLUME_SURGE: 'V', AMOUNT_SURGE: 'A',
    BREAKOUT_52W: '52H', BREAKOUT_26W: '26H', BREAKOUT_13W: '13H', BREAKOUT_20D: '20H',
    LONG_WHITE_CANDLE: 'LW', HAMMER_CANDLE: 'H', MORNING_STAR: 'MS',
    SUPPLY_ANOMALY: 'SD', POST_DISCLOSURE_SURGE: 'PD',
  }
  return MAP[type] ?? type.slice(0, 3)
}

const MA_DEFS = [
  { key: 'ma5',   label: 'MA5',   color: NAVER.ma5   },
  { key: 'ma20',  label: 'MA20',  color: NAVER.ma20  },
  { key: 'ma60',  label: 'MA60',  color: NAVER.ma60  },
  { key: 'ma120', label: 'MA120', color: NAVER.ma120 },
] as const

// ── RSI(Wilder's) ─────────────────────────────────────────────────────────────
function calcRSI(closes: number[], period = 14): (number | null)[] {
  if (closes.length < period + 1) return closes.map(() => null)
  const result: (number | null)[] = []
  let avgGain = 0, avgLoss = 0
  for (let i = 1; i <= period; i++) {
    const d = closes[i] - closes[i - 1]
    if (d > 0) avgGain += d; else avgLoss += Math.abs(d)
  }
  avgGain /= period; avgLoss /= period
  for (let i = 0; i < period; i++) result.push(null)
  const rs0 = avgLoss === 0 ? 100 : avgGain / avgLoss
  result.push(100 - 100 / (1 + rs0))
  for (let i = period + 1; i < closes.length; i++) {
    const d = closes[i] - closes[i - 1]
    avgGain = (avgGain * (period - 1) + (d > 0 ? d : 0)) / period
    avgLoss = (avgLoss * (period - 1) + (d < 0 ? Math.abs(d) : 0)) / period
    result.push(100 - 100 / (1 + (avgLoss === 0 ? 100 : avgGain / avgLoss)))
  }
  return result
}

// ── 볼린저밴드(MA20 ±2σ) ─────────────────────────────────────────────────────
function calcBB(closes: number[], period = 20) {
  return closes.map((_, i) => {
    if (i < period - 1) return { upper: null, lower: null }
    const s = closes.slice(i - period + 1, i + 1)
    const m = s.reduce((a, b) => a + b, 0) / period
    const std = Math.sqrt(s.reduce((a, b) => a + (b - m) ** 2, 0) / period)
    return { upper: m + 2 * std, lower: m - 2 * std }
  })
}

// ── 기간 버튼 ─────────────────────────────────────────────────────────────────
const PERIOD_BTNS = [
  { label: '1M', days: 30  },
  { label: '3M', days: 90  },
  { label: '6M', days: 180 },
  { label: '1Y', days: 250 },
  { label: '3Y', days: 750 },
]

function fmtVol(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000)     return `${(v / 1_000).toFixed(0)}K`
  return String(v)
}

function fmtPrc(v: number | undefined | null): string {
  if (v == null) return '—'
  return v >= 1000 ? v.toLocaleString('ko-KR', { maximumFractionDigits: 0 }) : v.toFixed(2)
}

// ── OHLCV 오버레이 타입 ───────────────────────────────────────────────────────
interface HoverInfo {
  date:   string
  open:   number
  high:   number
  low:    number
  close:  number
  volume: number
  ma5?:   number | null
  ma20?:  number | null
  ma60?:  number | null
  ma120?: number | null
  prevClose: number
}

export function CandleChart({ data, height = 360, showMA = true, events, className }: CandleChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef     = useRef<ReturnType<typeof createChart> | null>(null)
  const candleRef    = useRef<ReturnType<ReturnType<typeof createChart>['addCandlestickSeries']> | null>(null)
  const { mode }     = useThemeStore()
  const isDark       = mode === 'dark'

  const [activeMA,   setActiveMA]   = useState<Set<string>>(new Set(['ma5', 'ma20', 'ma60', 'ma120']))
  const [showBB,     setShowBB]     = useState(false)
  const [showVol,    setShowVol]    = useState(true)
  const [showRSI,    setShowRSI]    = useState(true)
  const [periodDays, setPeriodDays] = useState(90)
  const [hover,      setHover]      = useState<HoverInfo | null>(null)

  function toggleMA(key: string) {
    setActiveMA(prev => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  // 기간 슬라이스
  const filteredData = useMemo(() =>
    data.length ? data.slice(-periodDays) : data,
    [data, periodDays]
  )

  // RSI
  const rsiData = useMemo(() => {
    const rsi = calcRSI(filteredData.map(d => d.close))
    return filteredData.map((d, i) => ({
      date: d.date.slice(5),
      rsi:  rsi[i] != null ? +rsi[i]!.toFixed(1) : null,
    }))
  }, [filteredData])

  // 볼린저밴드
  const bbData = useMemo(() => calcBB(filteredData.map(d => d.close)), [filteredData])

  // 거래량
  const volData = useMemo(() =>
    filteredData.map((d, i) => {
      const prev = i > 0 ? filteredData[i - 1].close : d.open
      return { date: d.date.slice(5), volume: d.volume ?? 0, up: d.close >= prev }
    }),
    [filteredData]
  )

  // crosshair 이동 → hover 업데이트
  const updateHover = useCallback((param: {
    time?: unknown
    seriesData?: Map<unknown, unknown>
    logical?: number
  }) => {
    if (!param.time || !param.seriesData?.size) {
      // 마우스 이탈 시 마지막 봉 기본값 표시
      const last = filteredData[filteredData.length - 1]
      const prev = filteredData.length > 1 ? filteredData[filteredData.length - 2].close : last?.open
      if (last) setHover({
        date: last.date, open: last.open, high: last.high,
        low: last.low, close: last.close, volume: last.volume,
        ma5: last.ma5, ma20: last.ma20, ma60: last.ma60, ma120: last.ma120,
        prevClose: prev,
      })
      return
    }
    const timeStr = String(param.time)
    const idx = filteredData.findIndex(d => d.date === timeStr)
    if (idx < 0) return
    const d = filteredData[idx]
    const prev = idx > 0 ? filteredData[idx - 1].close : d.open
    setHover({
      date: d.date, open: d.open, high: d.high, low: d.low,
      close: d.close, volume: d.volume,
      ma5: d.ma5, ma20: d.ma20, ma60: d.ma60, ma120: d.ma120,
      prevClose: prev,
    })
  }, [filteredData])

  // 초기 hover = 최신 봉
  useEffect(() => {
    if (!filteredData.length) return
    const last = filteredData[filteredData.length - 1]
    const prev = filteredData.length > 1 ? filteredData[filteredData.length - 2].close : last.open
    setHover({
      date: last.date, open: last.open, high: last.high,
      low: last.low, close: last.close, volume: last.volume,
      ma5: last.ma5, ma20: last.ma20, ma60: last.ma60, ma120: last.ma120,
      prevClose: prev,
    })
  }, [filteredData])

  // ── 차트 생성 ──────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current || !filteredData.length) return

    const gridC  = isDark ? '#2a2a2a' : '#f0f0f0'
    const textC  = isDark ? '#9ca3af' : '#6b7280'
    const crossC = isDark ? '#4b5563' : '#9ca3af'
    const bgC    = isDark ? 'transparent' : 'transparent'

    chartRef.current?.remove()

    const chart = createChart(containerRef.current, {
      width:  containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: bgC },
        textColor:  textC,
        fontSize:   11,
      },
      grid: {
        vertLines: { color: gridC, style: 1 },
        horzLines: { color: gridC, style: 1 },
      },
      crosshair: {
        mode: 1,
        vertLine: { color: crossC, width: 1, style: 3, labelBackgroundColor: isDark ? '#374151' : '#e5e7eb' },
        horzLine: { color: crossC, width: 1, style: 3, labelBackgroundColor: isDark ? '#374151' : '#e5e7eb' },
      },
      timeScale: {
        borderColor:     gridC,
        timeVisible:     false,
        secondsVisible:  false,
        fixLeftEdge:     true,
        fixRightEdge:    true,
        barSpacing:      filteredData.length <= 60 ? 8 : filteredData.length <= 180 ? 5 : 3,
      },
      rightPriceScale: {
        borderColor:  gridC,
        minimumWidth: 65,
        scaleMargins: { top: 0.08, bottom: 0.05 },
      },
      localization: {
        dateFormat: 'yy/MM/dd',
        priceFormatter: (p: number) =>
          p >= 1000 ? p.toLocaleString('ko-KR', { maximumFractionDigits: 0 }) : p.toFixed(2),
      },
    })
    chartRef.current = chart

    // ── 캔들 시리즈 ──────────────────────────────────────────────────────────
    const candleSeries = chart.addCandlestickSeries({
      upColor:         NAVER.up,
      downColor:       NAVER.down,
      borderUpColor:   NAVER.up,
      borderDownColor: NAVER.down,
      wickUpColor:     NAVER.up,
      wickDownColor:   NAVER.down,
      borderVisible:   true,
      wickVisible:     true,
    })
    candleRef.current = candleSeries

    candleSeries.setData(
      filteredData.map((d, i) => {
        const prev = i > 0 ? filteredData[i - 1].close : d.open
        const isUp   = d.close > prev
        const isFlat = d.close === prev
        const c = isFlat ? NAVER.flat : isUp ? NAVER.up : NAVER.down
        return {
          time:        d.date as unknown as string,
          open:        d.open,
          high:        d.high,
          low:         d.low,
          close:       d.close,
          color:       c,
          wickColor:   c,
          borderColor: c,
        }
      })
    )

    // ── 이벤트 마커 ──────────────────────────────────────────────────────────
    if (events?.length) {
      const minDate = filteredData[0]?.date ?? ''
      const markers = events
        .filter(ev => ev.date && ev.date >= minDate)
        .map(ev => ({
          time:     ev.date as unknown as string,
          position: 'aboveBar' as const,
          color:    EVENT_MARKER_COLOR[ev.type] ?? '#94a3b8',
          shape:    'arrowDown' as const,
          text:     eventLabel(ev.type),
          size:     Math.max(0.5, Math.min(2, ev.score * 2)),
        }))
        .sort((a, b) => String(a.time).localeCompare(String(b.time)))
      candleSeries.setMarkers(markers)
    }

    // ── MA 시리즈 ─────────────────────────────────────────────────────────────
    if (showMA) {
      MA_DEFS.forEach(({ key, color, label }) => {
        if (!activeMA.has(key)) return
        const s = chart.addLineSeries({
          color,
          lineWidth:        1,
          title:            label,
          lastValueVisible: false,
          priceLineVisible: false,
        })
        const pts = filteredData
          .filter(d => (d as unknown as Record<string, unknown>)[key] != null)
          .map(d => ({ time: d.date as unknown as string, value: (d as unknown as Record<string, number>)[key]! }))
        s.setData(pts)
      })
    }

    // ── 볼린저밴드 ────────────────────────────────────────────────────────────
    if (showBB) {
      const makeLineSeries = (title: string) => chart.addLineSeries({
        color: NAVER.bb, lineWidth: 1, title,
        lastValueVisible: false, priceLineVisible: false,
        lineStyle: 2,
      })
      const upper = makeLineSeries('BB+')
      const lower = makeLineSeries('BB-')
      upper.setData(filteredData
        .map((d, i) => bbData[i].upper != null ? { time: d.date as unknown as string, value: bbData[i].upper! } : null)
        .filter((x): x is NonNullable<typeof x> => x !== null))
      lower.setData(filteredData
        .map((d, i) => bbData[i].lower != null ? { time: d.date as unknown as string, value: bbData[i].lower! } : null)
        .filter((x): x is NonNullable<typeof x> => x !== null))
    }

    chart.timeScale().fitContent()

    // ── crosshair → hover 업데이트 ───────────────────────────────────────────
    chart.subscribeCrosshairMove((param) => {
      updateHover(param as Parameters<typeof updateHover>[0])
    })

    const ro = new ResizeObserver(() => {
      if (containerRef.current) chart.resize(containerRef.current.clientWidth, height)
    })
    ro.observe(containerRef.current)

    return () => { ro.disconnect(); chart.remove(); chartRef.current = null }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filteredData, events, mode, height, showMA, activeMA, showBB, bbData])

  // ── 스타일 변수 ────────────────────────────────────────────────────────────
  const textColor = isDark ? '#9ca3af' : '#6b7280'
  const gridColor = isDark ? '#2a2a2a' : '#f0f0f0'
  const panelBg   = isDark ? '#18181b' : '#ffffff'
  const borderC   = isDark ? '#27272a' : '#e5e7eb'

  const hoverColor = hover
    ? hover.close > hover.prevClose ? NAVER.up
      : hover.close < hover.prevClose ? NAVER.down
      : NAVER.flat
    : NAVER.flat

  const changePct = hover && hover.prevClose
    ? ((hover.close - hover.prevClose) / hover.prevClose * 100)
    : null

  return (
    <div className={clsx('w-full select-none', className)}>

      {/* ── OHLCV 오버레이 패널 ─────────────────────────────────────────────── */}
      <div
        className="flex flex-wrap items-center gap-x-3 gap-y-0.5 px-2 py-1.5 text-[11px] border-b"
        style={{ background: panelBg, borderColor: borderC }}
      >
        {/* 날짜 */}
        <span className="font-medium" style={{ color: textColor }}>
          {hover?.date ?? '—'}
        </span>

        {/* OHLC */}
        {[
          { label: '시', key: 'open' },
          { label: '고', key: 'high' },
          { label: '저', key: 'low' },
        ].map(({ label, key }) => (
          <span key={key} style={{ color: textColor }}>
            {label}&nbsp;
            <span className="font-semibold" style={{ color: isDark ? '#e5e7eb' : '#111827' }}>
              {fmtPrc(hover?.[key as keyof HoverInfo] as number)}
            </span>
          </span>
        ))}
        <span>
          <span style={{ color: textColor }}>종&nbsp;</span>
          <span className="font-bold" style={{ color: hoverColor }}>
            {fmtPrc(hover?.close)}
          </span>
        </span>
        {changePct != null && (
          <span className="font-semibold" style={{ color: hoverColor }}>
            {changePct >= 0 ? '+' : ''}{changePct.toFixed(2)}%
          </span>
        )}

        {/* 거래량 */}
        <span style={{ color: textColor }}>
          거래량&nbsp;
          <span className="font-semibold" style={{ color: isDark ? '#e5e7eb' : '#111827' }}>
            {hover?.volume != null ? hover.volume.toLocaleString() : '—'}
          </span>
        </span>

        {/* MA 현재값 */}
        {showMA && MA_DEFS.filter(m => activeMA.has(m.key)).map(({ key, label, color }) => {
          const v = hover?.[key as keyof HoverInfo]
          if (v == null) return null
          return (
            <span key={key} className="font-medium" style={{ color }}>
              {label}&nbsp;{fmtPrc(v as number)}
            </span>
          )
        })}
      </div>

      {/* ── 컨트롤 바 ──────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-2 px-1 py-1.5">
        {/* 기간 버튼 */}
        <div className="flex rounded overflow-hidden border" style={{ borderColor: borderC }}>
          {PERIOD_BTNS.map(({ label, days }) => (
            <button
              key={label}
              onClick={() => setPeriodDays(days)}
              className={clsx(
                'text-[11px] px-2 py-0.5 font-medium transition-colors',
                periodDays === days
                  ? 'bg-blue-600 text-white'
                  : 'hover:bg-[var(--border)]'
              )}
              style={{ color: periodDays === days ? '#fff' : textColor }}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="w-px h-4" style={{ background: borderC }} />

        {/* MA 토글 */}
        {showMA && MA_DEFS.map(({ key, label, color }) => (
          <button
            key={key}
            onClick={() => toggleMA(key)}
            className="text-[11px] px-2 py-0.5 rounded border font-medium transition-all"
            style={{
              borderColor: color,
              color,
              opacity: activeMA.has(key) ? 1 : 0.25,
            }}
          >
            {label}
          </button>
        ))}

        {/* BB 토글 */}
        <button
          onClick={() => setShowBB(v => !v)}
          className="text-[11px] px-2 py-0.5 rounded border font-medium transition-all"
          style={{
            borderColor: NAVER.bb,
            color: NAVER.bb,
            opacity: showBB ? 1 : 0.3,
          }}
        >
          BB
        </button>

        <div className="w-px h-4" style={{ background: borderC }} />

        {/* 거래량/RSI 토글 */}
        {[
          { label: 'VOL', active: showVol, toggle: () => setShowVol(v => !v), color: '#38bdf8' },
          { label: 'RSI', active: showRSI, toggle: () => setShowRSI(v => !v), color: '#fbbf24' },
        ].map(({ label, active, toggle, color }) => (
          <button
            key={label}
            onClick={toggle}
            className="text-[11px] px-2 py-0.5 rounded border font-medium transition-all"
            style={{ borderColor: color, color, opacity: active ? 1 : 0.3 }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ── 캔들 차트 ──────────────────────────────────────────────────────── */}
      <div ref={containerRef} className="w-full" style={{ height }} />

      {/* ── 거래량 패널 ────────────────────────────────────────────────────── */}
      {showVol && volData.length > 0 && (
        <div className="w-full" style={{ height: 80 }}>
          <div
            className="text-[9px] px-2 pt-1 pb-0.5 font-medium uppercase tracking-wide"
            style={{ color: textColor }}
          >
            거래량
          </div>
          <ResponsiveContainer width="100%" height={62}>
            <BarChart data={volData} margin={{ top: 0, right: 65, left: 0, bottom: 0 }} barCategoryGap="0%">
              <XAxis dataKey="date" hide />
              <YAxis
                width={60}
                tickFormatter={fmtVol}
                tick={{ fontSize: 9, fill: textColor }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                formatter={(v: number) => [v.toLocaleString(), '거래량']}
                contentStyle={{
                  background: panelBg, border: `1px solid ${borderC}`,
                  borderRadius: 4, fontSize: 11, color: textColor,
                }}
              />
              <Bar
                dataKey="volume"
                isAnimationActive={false}
                shape={(props: unknown) => {
                  const p = props as { x: number; y: number; width: number; height: number; up: boolean }
                  return (
                    <rect
                      x={p.x} y={p.y} width={Math.max(1, p.width)} height={p.height}
                      fill={p.up ? NAVER.up : NAVER.down}
                      opacity={0.75}
                    />
                  )
                }}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* ── RSI 패널 ───────────────────────────────────────────────────────── */}
      {showRSI && rsiData.length > 0 && (
        <div className="w-full" style={{ height: 88 }}>
          <div
            className="text-[9px] px-2 pt-1 pb-0.5 font-medium uppercase tracking-wide"
            style={{ color: textColor }}
          >
            RSI (14)
          </div>
          <ResponsiveContainer width="100%" height={70}>
            <LineChart data={rsiData} margin={{ top: 2, right: 65, left: 0, bottom: 0 }}>
              <XAxis dataKey="date" hide />
              <YAxis
                domain={[0, 100]}
                ticks={[0, 30, 50, 70, 100]}
                width={60}
                tick={{ fontSize: 9, fill: textColor }}
                axisLine={false}
                tickLine={false}
              />
              {/* 과매수/과매도 기준선 */}
              <ReferenceLine y={70} stroke={NAVER.up}   strokeDasharray="4 3" strokeWidth={1} />
              <ReferenceLine y={50} stroke={textColor}  strokeDasharray="2 4" strokeWidth={0.8} />
              <ReferenceLine y={30} stroke={NAVER.down} strokeDasharray="4 3" strokeWidth={1} />
              <Tooltip
                formatter={(v: unknown) => [v != null ? Number(v).toFixed(1) : '—', 'RSI']}
                contentStyle={{
                  background: panelBg, border: `1px solid ${borderC}`,
                  borderRadius: 4, fontSize: 11, color: textColor,
                }}
              />
              <Line
                dataKey="rsi"
                stroke={NAVER.ma5}
                dot={false}
                strokeWidth={1.5}
                isAnimationActive={false}
                connectNulls={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
