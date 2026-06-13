import { useEffect, useRef, useState } from 'react'
import { createChart, ColorType } from 'lightweight-charts'
import type { DailyBar } from '@/types'
import { useThemeStore } from '@/store/theme'
import { clsx } from 'clsx'

export interface ChartEvent {
  date:  string
  type:  string
  score: number
}

interface CandleChartProps {
  data:      DailyBar[]
  height?:   number
  showMA?:   boolean
  events?:   ChartEvent[]
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

export function CandleChart({ data, height = 360, showMA = true, events, className }: CandleChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef     = useRef<ReturnType<typeof createChart> | null>(null)
  const { mode }     = useThemeStore()
  const [activeMA, setActiveMA] = useState<Set<string>>(new Set(['ma5', 'ma20', 'ma60']))

  function toggleMA(key: string) {
    setActiveMA((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key); else next.add(key)
      return next
    })
  }

  useEffect(() => {
    if (!containerRef.current || !data.length) return

    const isDark = mode === 'dark'
    const gridC  = isDark ? '#27272a' : '#e4e4e7'
    const textC  = isDark ? '#a1a1aa' : '#52525b'   /* 개선된 가시성 */
    const crossC = isDark ? '#52525b' : '#a1a1aa'

    chartRef.current?.remove()

    const chart = createChart(containerRef.current, {
      width:  containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor:  textC,
        fontSize:   12,    /* 11 → 12 */
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

    // Korean convention: color based on close vs prev-day close (not vs open)
    series.setData(
      data.map((d, idx) => {
        const prevClose = idx > 0 ? data[idx - 1].close : d.open
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
      const markers = events
        .filter((ev) => ev.date)
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

    if (showMA) {
      MA_DEFS.forEach(({ key, color, label }) => {
        if (!activeMA.has(key)) return
        const s = chart.addLineSeries({
          color,
          lineWidth:          1,
          title:              label,
          lastValueVisible:   false,
          priceLineVisible:   false,
        })
        const pts = data
          .filter((d) => (d as unknown as Record<string, unknown>)[key] != null)
          .map((d) => ({ time: d.date as unknown as string, value: (d as unknown as Record<string, number>)[key]! }))
        s.setData(pts)
      })
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
  }, [data, events, mode, height, showMA, activeMA])

  return (
    <div className={clsx('w-full', className)}>
      {showMA && (
        <div className="flex gap-1.5 mb-2 px-1">
          {MA_DEFS.map(({ key, label, color }) => (
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
        </div>
      )}
      <div ref={containerRef} className="w-full" style={{ height }} />
    </div>
  )
}