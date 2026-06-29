import { useEffect, useRef, useState, useMemo } from 'react'
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
  { key: 'ma5',  label: 'MA5',  color: '#fbbf24' },
  { key: 'ma20', label: 'MA20', color: '#38bdf8' },
  { key: 'ma60', label: 'MA60', color: '#fb923c' },
] as const

// ── RSI 계산 (Wilder's RSI) ─────────────────────────────────────────────────
function calcRSI(closes: number[], period = 14): (number | null)[] {
  if (closes.length < period + 1) return closes.map(() => null)
  const result: (number | null)[] = []
  let avgGain = 0
  let avgLoss = 0

  for (let i = 1; i <= period; i++) {
    const diff = closes[i] - closes[i - 1]
    if (diff > 0) avgGain += diff
    else avgLoss += Math.abs(diff)
  }
  avgGain /= period
  avgLoss /= period

  for (let i = 0; i < period; i++) result.push(null)

  const firstRS = avgLoss === 0 ? 100 : avgGain / avgLoss
  result.push(100 - 100 / (1 + firstRS))

  for (let i = period + 1; i < closes.length; i++) {
    const diff = closes[i] - closes[i - 1]
    const gain = diff > 0 ? diff : 0
    const loss = diff < 0 ? Math.abs(diff) : 0
    avgGain = (avgGain * (period - 1) + gain) / period
    avgLoss = (avgLoss * (period - 1) + loss) / period
    const rs = avgLoss === 0 ? 100 : avgGain / avgLoss
    result.push(100 - 100 / (1 + rs))
  }
  return result
}

// ── 볼린저밴드 계산 (MA20 ± 2σ) ─────────────────────────────────────────────
function calcBB(closes: number[], period = 20): { upper: number | null; mid: number | null; lower: number | null }[] {
  return closes.map((_, i) => {
    if (i < period - 1) return { upper: null, mid: null, lower: null }
    const slice = closes.slice(i - period + 1, i + 1)
    const mean = slice.reduce((a, b) => a + b, 0) / period
    const variance = slice.reduce((a, b) => a + (b - mean) ** 2, 0) / period
    const std = Math.sqrt(variance)
    return { upper: mean + 2 * std, mid: mean, lower: mean - 2 * std }
  })
}

// 기간 버튼 정의
const PERIOD_BTNS: { label: string; days: number }[] = [
  { label: '1M', days: 30 },
  { label: '3M', days: 90 },
  { label: '6M', days: 180 },
  { label: '1Y', days: 250 },
  { label: '3Y', days: 750 },
]

// 거래량 포맷
function fmtVol(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`
  return String(v)
}

export function CandleChart({ data, height = 360, showMA = true, events, className }: CandleChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef     = useRef<ReturnType<typeof createChart> | null>(null)
  const { mode }     = useThemeStore()

  // 토글 상태
  const [activeMA,  setActiveMA]  = useState<Set<string>>(new Set(['ma5', 'ma20', 'ma60']))
  const [showBB,    setShowBB]    = useState(false)
  const [showVol,   setShowVol]   = useState(true)
  const [showRSI,   setShowRSI]   = useState(true)
  const [periodDays, setPeriodDays] = useState(90) // 기본 3M

  function toggleMA(key: string) {
    setActiveMA((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key); else next.add(key)
      return next
    })
  }

  // 기간 필터링된 데이터
  const filteredData = useMemo(() => {
    if (!data.length) return data
    return data.slice(-periodDays)
  }, [data, periodDays])

  // RSI 데이터
  const rsiData = useMemo(() => {
    const closes = filteredData.map((d) => d.close)
    const rsiValues = calcRSI(closes)
    return filteredData.map((d, i) => ({
      date:  d.date.slice(5),  // MM-DD
      rsi:   rsiValues[i] != null ? Number(rsiValues[i]!.toFixed(1)) : null,
    }))
  }, [filteredData])

  // 볼린저밴드 데이터
  const bbData = useMemo(() => {
    const closes = filteredData.map((d) => d.close)
    return calcBB(closes)
  }, [filteredData])

  // 거래량 데이터
  const volData = useMemo(() => {
    return filteredData.map((d, i) => {
      const prevClose = i > 0 ? filteredData[i - 1].close : d.open
      const up = d.close >= prevClose
      return {
        date:   d.date.slice(5),
        volume: d.volume ?? 0,
        up,
      }
    })
  }, [filteredData])

  useEffect(() => {
    if (!containerRef.current || !filteredData.length) return

    const isDark = mode === 'dark'
    const gridC  = isDark ? '#27272a' : '#e4e4e7'
    const textC  = isDark ? '#a1a1aa' : '#52525b'
    const crossC = isDark ? '#52525b' : '#a1a1aa'

    chartRef.current?.remove()

    const chart = createChart(containerRef.current, {
      width:  containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor:  textC,
        fontSize:   12,
      },
      grid: {
        vertLines: { color: gridC },
        horzLines: { color: gridC },
      },
      crosshair: {
        vertLine: { color: crossC, labelBackgroundColor: isDark ? '#27272a' : '#e4e4e7' },
        horzLine: { color: crossC, labelBackgroundColor: isDark ? '#27272a' : '#e4e4e7' },
      },
      timeScale: {
        borderColor:    gridC,
        timeVisible:    false,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: gridC,
        minimumWidth: 60,
      },
      localization: {
        dateFormat: 'yy/MM/dd',
        priceFormatter: (price: number) =>
          price >= 1000
            ? price.toLocaleString('ko-KR', { maximumFractionDigits: 0 })
            : price.toFixed(2),
      },
    })
    chartRef.current = chart

    const series = chart.addCandlestickSeries({
      upColor:         '#ef4444',
      downColor:       '#3b82f6',
      borderUpColor:   '#ef4444',
      borderDownColor: '#3b82f6',
      wickUpColor:     '#ef4444',
      wickDownColor:   '#3b82f6',
    })

    series.setData(
      filteredData.map((d, idx) => {
        const prevClose = idx > 0 ? filteredData[idx - 1].close : d.open
        const up = d.close >= prevClose
        const upC = '#ef4444'
        const dnC = '#3b82f6'
        return {
          time:        d.date as unknown as string,
          open:        d.open,
          high:        d.high,
          low:         d.low,
          close:       d.close,
          color:       up ? upC : dnC,
          wickColor:   up ? upC : dnC,
          borderColor: up ? upC : dnC,
        }
      })
    )

    // 탐지 이벤트 마커
    if (events && events.length > 0) {
      const minDate = filteredData[0]?.date ?? ''
      const markers = events
        .filter((ev) => ev.date && ev.date >= minDate)
        .map((ev) => ({
          time:     ev.date as unknown as string,
          position: 'aboveBar' as const,
          color:    EVENT_MARKER_COLOR[ev.type] ?? '#94a3b8',
          shape:    'arrowDown' as const,
          text:     eventLabel(ev.type),
          size:     Math.max(0.5, Math.min(2, ev.score * 2)),
        }))
        .sort((a, b) => String(a.time).localeCompare(String(b.time)))
      series.setMarkers(markers)
    }

    // MA 시리즈
    if (showMA) {
      MA_DEFS.forEach(({ key, color, label }) => {
        if (!activeMA.has(key)) return
        const s = chart.addLineSeries({
          color,
          lineWidth:         1,
          title:             label,
          lastValueVisible:  false,
          priceLineVisible:  false,
        })
        const pts = filteredData
          .filter((d) => (d as unknown as Record<string, unknown>)[key] != null)
          .map((d) => ({ time: d.date as unknown as string, value: (d as unknown as Record<string, number>)[key]! }))
        s.setData(pts)
      })
    }

    // 볼린저밴드 시리즈
    if (showBB) {
      const upperSeries = chart.addLineSeries({
        color: 'rgba(168,85,247,0.6)',
        lineWidth: 1,
        lastValueVisible: false,
        priceLineVisible: false,
        title: 'BB+',
      })
      const lowerSeries = chart.addLineSeries({
        color: 'rgba(168,85,247,0.6)',
        lineWidth: 1,
        lastValueVisible: false,
        priceLineVisible: false,
        title: 'BB-',
      })
      const upperPts = filteredData
        .map((d, i) => bbData[i].upper != null ? { time: d.date as unknown as string, value: bbData[i].upper! } : null)
        .filter((x): x is NonNullable<typeof x> => x !== null)
      const lowerPts = filteredData
        .map((d, i) => bbData[i].lower != null ? { time: d.date as unknown as string, value: bbData[i].lower! } : null)
        .filter((x): x is NonNullable<typeof x> => x !== null)
      upperSeries.setData(upperPts)
      lowerSeries.setData(lowerPts)
    }

    chart.timeScale().fitContent()

    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.resize(containerRef.current.clientWidth, height)
      }
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
    }
  }, [filteredData, events, mode, height, showMA, activeMA, showBB, bbData])

  const isDark = mode === 'dark'
  const axisColor = isDark ? '#52525b' : '#a1a1aa'
  const gridColor = isDark ? '#27272a' : '#f0f0f0'
  const textColor = isDark ? '#a1a1aa' : '#52525b'

  return (
    <div className={clsx('w-full', className)}>
      {/* 컨트롤 바 */}
      <div className="flex flex-wrap items-center gap-2 mb-2 px-1">
        {/* 기간 버튼 */}
        <div className="flex rounded overflow-hidden border border-[var(--border)]">
          {PERIOD_BTNS.map(({ label, days }) => (
            <button
              key={label}
              onClick={() => setPeriodDays(days)}
              className={clsx(
                'text-[11px] px-2 py-0.5 font-medium transition-colors select-none',
                periodDays === days
                  ? 'bg-cyan-500/20 text-cyan-400'
                  : 'text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)]'
              )}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="w-px h-4 bg-[var(--border)]" />

        {/* MA 토글 */}
        {showMA && MA_DEFS.map(({ key, label, color }) => (
          <button
            key={key}
            onClick={() => toggleMA(key)}
            className={clsx(
              'text-[11px] px-2 py-0.5 rounded border font-medium transition-all select-none',
              activeMA.has(key) ? 'opacity-100' : 'opacity-25'
            )}
            style={{ borderColor: color, color }}
          >
            {label}
          </button>
        ))}

        {/* BB 토글 */}
        <button
          onClick={() => setShowBB((v) => !v)}
          className={clsx(
            'text-[11px] px-2 py-0.5 rounded border font-medium transition-all select-none',
            showBB ? 'border-purple-400 text-purple-400 opacity-100' : 'border-purple-400 text-purple-400 opacity-25'
          )}
        >
          BB
        </button>

        <div className="w-px h-4 bg-[var(--border)]" />

        {/* 거래량/RSI 토글 */}
        <button
          onClick={() => setShowVol((v) => !v)}
          className={clsx(
            'text-[11px] px-2 py-0.5 rounded border font-medium transition-all select-none',
            showVol ? 'border-sky-400 text-sky-400 opacity-100' : 'border-sky-400 text-sky-400 opacity-25'
          )}
        >
          VOL
        </button>
        <button
          onClick={() => setShowRSI((v) => !v)}
          className={clsx(
            'text-[11px] px-2 py-0.5 rounded border font-medium transition-all select-none',
            showRSI ? 'border-amber-400 text-amber-400 opacity-100' : 'border-amber-400 text-amber-400 opacity-25'
          )}
        >
          RSI
        </button>
      </div>

      {/* 캔들 차트 */}
      <div ref={containerRef} className="w-full" style={{ height }} />

      {/* 거래량 패널 */}
      {showVol && volData.length > 0 && (
        <div className="w-full mt-1" style={{ height: 72 }}>
          <div className="text-[10px] text-[var(--muted)] px-1 mb-0.5">거래량</div>
          <ResponsiveContainer width="100%" height={60}>
            <BarChart data={volData} margin={{ top: 0, right: 60, left: 0, bottom: 0 }}
              barCategoryGap="0%">
              <XAxis dataKey="date" hide />
              <YAxis
                width={55}
                tickFormatter={fmtVol}
                tick={{ fontSize: 9, fill: textColor }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                formatter={(v: number) => [v.toLocaleString(), '거래량']}
                labelFormatter={(l: string) => l}
                contentStyle={{
                  background: isDark ? '#18181b' : '#fff',
                  border: `1px solid ${gridColor}`,
                  borderRadius: 6,
                  fontSize: 11,
                  color: textColor,
                }}
              />
              <Bar dataKey="volume" isAnimationActive={false}
                fill="#38bdf8"
                // 상승 빨강, 하락 파랑
                shape={(props: unknown) => {
                  const p = props as { x: number; y: number; width: number; height: number; up: boolean }
                  return <rect x={p.x} y={p.y} width={p.width} height={p.height} fill={p.up ? '#ef4444' : '#3b82f6'} opacity={0.7} />
                }}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* RSI 패널 */}
      {showRSI && rsiData.length > 0 && (
        <div className="w-full mt-1" style={{ height: 80 }}>
          <div className="text-[10px] text-[var(--muted)] px-1 mb-0.5">RSI(14)</div>
          <ResponsiveContainer width="100%" height={68}>
            <LineChart data={rsiData} margin={{ top: 2, right: 60, left: 0, bottom: 0 }}>
              <XAxis dataKey="date" hide />
              <YAxis
                domain={[0, 100]}
                ticks={[0, 30, 70, 100]}
                width={55}
                tick={{ fontSize: 9, fill: textColor }}
                axisLine={false}
                tickLine={false}
              />
              <ReferenceLine y={70} stroke="#ef4444" strokeDasharray="3 3" strokeWidth={1} />
              <ReferenceLine y={30} stroke="#3b82f6" strokeDasharray="3 3" strokeWidth={1} />
              <Tooltip
                formatter={(v: unknown) => [v != null ? Number(v).toFixed(1) : '—', 'RSI']}
                labelFormatter={(l: string) => l}
                contentStyle={{
                  background: isDark ? '#18181b' : '#fff',
                  border: `1px solid ${gridColor}`,
                  borderRadius: 6,
                  fontSize: 11,
                  color: textColor,
                }}
              />
              <Line
                dataKey="rsi"
                stroke="#fbbf24"
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
