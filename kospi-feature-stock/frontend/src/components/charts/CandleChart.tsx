import { useEffect, useRef } from 'react'
import { createChart, ColorType } from 'lightweight-charts'
import type { DailyBar } from '@/types'
import { useThemeStore } from '@/store/theme'

interface CandleChartProps {
  data:    DailyBar[]
  height?: number
}

export function CandleChart({ data, height = 320 }: CandleChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef     = useRef<ReturnType<typeof createChart> | null>(null)
  const { mode }     = useThemeStore()

  useEffect(() => {
    if (!containerRef.current || !data.length) return

    const isDark = mode === 'dark'
    const gridC  = isDark ? '#27272a' : '#e4e4e7'
    const textC  = isDark ? '#71717a' : '#71717a'
    const crossC = isDark ? '#52525b' : '#a1a1aa'

    chartRef.current?.remove()

    const chart = createChart(containerRef.current, {
      width:  containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor:  textC,
        fontSize:   11,
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
        timeVisible:    true,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: gridC,
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
      data.map((d) => ({
        time:  d.date as unknown as string,
        open:  d.open,
        high:  d.high,
        low:   d.low,
        close: d.close,
      }))
    )

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
  }, [data, mode, height])

  return <div ref={containerRef} className="w-full" style={{ height }} />
}
