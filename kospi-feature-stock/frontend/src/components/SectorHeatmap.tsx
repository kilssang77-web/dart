import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { X, BarChart3 } from 'lucide-react'
import { marketApi } from '@/api/market'
import type { SectorHeatmapItem } from '@/api/market'

function sectorColor(chg: number): string {
  if (chg >= 2)   return 'bg-red-600 text-white'
  if (chg >= 1)   return 'bg-red-400 text-white'
  if (chg >= 0.3) return 'bg-red-300/80 text-red-900 dark:text-white'
  if (chg > -0.3) return 'bg-[var(--border)] text-[var(--fg)]'
  if (chg > -1)   return 'bg-blue-300/80 text-blue-900 dark:text-white'
  if (chg > -2)   return 'bg-blue-400 text-white'
  return 'bg-blue-600 text-white'
}

function SectorModal({
  sector,
  onClose,
}: {
  sector: SectorHeatmapItem
  onClose: () => void
}) {
  const nav = useNavigate()
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60" />
      <div
        className="relative bg-[var(--card)] border border-[var(--border)] rounded-2xl p-5 w-full max-w-sm shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="font-bold text-[var(--fg)]">{sector.sector}</div>
            <div className="text-xs text-[var(--muted)] mt-0.5">
              {sector.stock_count}종목 · 평균 등락
              <span className={clsx(
                'ml-1 font-semibold',
                sector.avg_change_pct > 0 ? 'text-red-400' : sector.avg_change_pct < 0 ? 'text-blue-400' : 'text-[var(--muted)]'
              )}>
                {sector.avg_change_pct > 0 ? '+' : ''}{sector.avg_change_pct.toFixed(2)}%
              </span>
            </div>
          </div>
          <button onClick={onClose} className="text-[var(--muted)] hover:text-[var(--fg)] transition-colors p-1">
            <X size={16} />
          </button>
        </div>
        <div className="space-y-1.5">
          {sector.top_stocks.slice(0, 10).map((s) => (
            <button
              key={s.code}
              onClick={() => { onClose(); nav(`/search?code=${s.code}`) }}
              className="w-full flex items-center justify-between hover:bg-[var(--border)]/30 rounded-lg px-3 py-2 transition-colors text-left"
            >
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-sm text-[var(--fg)] font-medium truncate">{s.name}</span>
                <span className="text-[10px] text-[var(--muted)] font-mono shrink-0">{s.code}</span>
              </div>
              {s.change_pct != null && (
                <span className={clsx(
                  'text-sm font-bold tabular shrink-0 ml-2',
                  s.change_pct > 0 ? 'text-red-400' : s.change_pct < 0 ? 'text-blue-400' : 'text-[var(--muted)]'
                )}>
                  {s.change_pct > 0 ? '+' : ''}{s.change_pct.toFixed(2)}%
                </span>
              )}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

export function SectorHeatmap() {
  const [modalSector, setModalSector] = useState<SectorHeatmapItem | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey:        ['sector-heatmap'],
    queryFn:         marketApi.getSectorHeatmap,
    staleTime:       5 * 60_000,
    refetchInterval: 5 * 60_000,
  })

  if (isLoading) {
    return (
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-2">
        {Array.from({ length: 16 }).map((_, i) => (
          <div key={i} className="h-16 skeleton rounded-xl" />
        ))}
      </div>
    )
  }

  if (isError || !data || data.length === 0) {
    return (
      <div className="py-6 text-center text-sm text-[var(--muted)]">섹터 데이터를 불러올 수 없습니다</div>
    )
  }

  return (
    <>
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 xl:grid-cols-10 gap-2">
        {data.map((sector) => (
          <button
            key={sector.sector}
            onClick={() => setModalSector(sector)}
            className={clsx(
              'rounded-xl p-2 flex flex-col items-center justify-center gap-1 min-h-[56px] transition-opacity hover:opacity-80 cursor-pointer text-center',
              sectorColor(sector.avg_change_pct)
            )}
          >
            <div className="text-[11px] font-semibold leading-tight line-clamp-2">{sector.sector}</div>
            <div className="text-[10px] font-bold tabular">
              {sector.avg_change_pct > 0 ? '+' : ''}{sector.avg_change_pct.toFixed(1)}%
            </div>
            <div className="text-[9px] opacity-70">{sector.stock_count}종목</div>
          </button>
        ))}
      </div>

      {modalSector && (
        <SectorModal sector={modalSector} onClose={() => setModalSector(null)} />
      )}
    </>
  )
}
