import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { agenciesApi } from '@/api'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { TrendingUp, Building2, AlertTriangle, CalendarDays } from 'lucide-react'
import type { AgencyBudgetSurgeItem } from '@/types'

const MONTH_COLORS: Record<number, string> = {
  1:  'bg-slate-100 text-slate-700',
  2:  'bg-slate-100 text-slate-700',
  3:  'bg-green-100 text-green-700',
  4:  'bg-green-100 text-green-700',
  5:  'bg-blue-100 text-blue-700',
  6:  'bg-blue-100 text-blue-700',
  7:  'bg-amber-100 text-amber-700',
  8:  'bg-amber-100 text-amber-700',
  9:  'bg-orange-100 text-orange-700',
  10: 'bg-red-100 text-red-700',
  11: 'bg-red-100 text-red-700',
  12: 'bg-red-200 text-red-800 font-semibold',
}

function surgeColor(v: number) {
  if (v >= 3.0) return 'text-red-600 font-bold'
  if (v >= 2.0) return 'text-orange-600 font-semibold'
  if (v >= 1.5) return 'text-amber-600 font-semibold'
  return 'text-gray-700'
}

function fmt(n: number) {
  if (n >= 1e12) return (n / 1e12).toFixed(1) + '조'
  if (n >= 1e8)  return (n / 1e8).toFixed(0) + '억'
  return (n / 1e4).toFixed(0) + '만'
}

export default function AgencyBudgetSurgePage() {
  const [monthsAhead,   setMonthsAhead]   = useState(3)
  const [minSurge,      setMinSurge]      = useState(1.3)
  const [minBidCount,   setMinBidCount]   = useState(3)
  const [expandedMonth, setExpandedMonth] = useState<number | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['agency-budget-surge', monthsAhead, minSurge],
    queryFn:  () => agenciesApi.budgetSurge({ months_ahead: monthsAhead, min_surge_index: minSurge, size: 100 }),
    staleTime: 600_000,
  })

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <TrendingUp className="h-6 w-6 text-orange-600" />
        <div>
          <h1 className="text-xl font-bold text-gray-900">발주기관 예산 집행 예보</h1>
          <p className="text-sm text-gray-500">월별 발주 급증 예상 기관 · 2~5년 입찰 이력 기반 surge 분석</p>
        </div>
      </div>

      {/* 필터 */}
      <div className="flex flex-wrap gap-3 items-center bg-gray-50 rounded-lg px-4 py-3">
        <label className="text-sm text-gray-600">
          예보 기간
          <select
            value={monthsAhead}
            onChange={e => setMonthsAhead(Number(e.target.value))}
            className="ml-2 border rounded px-2 py-1 text-sm bg-white"
          >
            {[1,2,3,4,5,6].map(m => <option key={m} value={m}>{m}개월</option>)}
          </select>
        </label>
        <label className="text-sm text-gray-600">
          최소 급증 지수
          <select
            value={minSurge}
            onChange={e => setMinSurge(Number(e.target.value))}
            className="ml-2 border rounded px-2 py-1 text-sm bg-white"
          >
            <option value={1.3}>1.3x 이상</option>
            <option value={1.5}>1.5x 이상</option>
            <option value={2.0}>2.0x 이상</option>
            <option value={3.0}>3.0x 이상</option>
          </select>
        </label>
        <label className="text-sm text-gray-600">
          최소 월 발주 건수
          <select
            value={minBidCount}
            onChange={e => setMinBidCount(Number(e.target.value))}
            className="ml-2 border rounded px-2 py-1 text-sm bg-white"
          >
            <option value={1}>1건 이상</option>
            <option value={3}>3건 이상</option>
            <option value={5}>5건 이상</option>
            <option value={10}>10건 이상</option>
          </select>
        </label>
      </div>

      {/* 예보 카드 */}
      {isLoading ? (
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-32 w-full" />)}
        </div>
      ) : data ? (
        <div className="space-y-4">
          {data.forecast.map(fc => {
            const filtered = fc.agencies.filter(a => a.avg_bid_count >= minBidCount)
            const isExpanded = expandedMonth === fc.month
            const shown = isExpanded ? filtered : filtered.slice(0, 8)
            const monthBadge = MONTH_COLORS[fc.month] || 'bg-gray-100 text-gray-700'

            return (
              <Card key={fc.month} className="overflow-hidden">
                <div className={`px-4 py-2.5 flex items-center justify-between cursor-pointer hover:opacity-90 ${fc.month === 12 ? 'bg-red-50' : fc.month >= 10 ? 'bg-orange-50' : 'bg-gray-50'}`}
                  onClick={() => setExpandedMonth(isExpanded ? null : fc.month)}>
                  <div className="flex items-center gap-3">
                    <CalendarDays className="h-4 w-4 text-gray-500" />
                    <span className={`px-2 py-0.5 rounded text-xs ${monthBadge}`}>{fc.label}</span>
                    <span className="text-sm font-semibold text-gray-800">
                      {filtered.length}개 기관 급증 예상
                    </span>
                    {fc.month === 12 && (
                      <span className="flex items-center gap-1 text-xs text-red-600">
                        <AlertTriangle className="h-3.5 w-3.5" />연말 예산 집행 최대
                      </span>
                    )}
                  </div>
                  <span className="text-xs text-gray-400">{isExpanded ? '접기 ▲' : '더보기 ▼'}</span>
                </div>

                {filtered.length === 0 ? (
                  <CardContent className="pt-3 pb-3 text-sm text-gray-400 text-center">
                    해당 기간 급증 기관 없음 (기준: avg_bid_count≥{minBidCount}, surge≥{minSurge}x)
                  </CardContent>
                ) : (
                  <CardContent className="pt-3 pb-3">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      {shown.map((a: AgencyBudgetSurgeItem) => (
                        <div key={a.agency_id}
                          className="flex items-center justify-between px-3 py-2 rounded-md bg-gray-50 hover:bg-gray-100 transition-colors">
                          <div className="flex items-center gap-2 min-w-0">
                            <Building2 className="h-3.5 w-3.5 text-gray-400 shrink-0" />
                            <span className="text-sm font-medium text-gray-800 truncate">{a.agency_name}</span>
                          </div>
                          <div className="flex items-center gap-3 shrink-0 ml-2">
                            <span className="text-xs text-gray-500">{a.avg_bid_count.toFixed(0)}건/월</span>
                            <span className="text-xs text-gray-500">{fmt(a.avg_bid_amount)}</span>
                            <span className={`text-sm ${surgeColor(a.surge_index)}`}>
                              {a.surge_index.toFixed(1)}x
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                    {!isExpanded && filtered.length > 8 && (
                      <button
                        onClick={() => setExpandedMonth(fc.month)}
                        className="mt-2 text-xs text-violet-600 hover:underline w-full text-center"
                      >
                        +{filtered.length - 8}개 더 보기
                      </button>
                    )}
                  </CardContent>
                )}
              </Card>
            )
          })}
        </div>
      ) : null}

      <p className="text-xs text-gray-400 text-right">
        surge_index = 해당 월 평균 발주 건수 / 연간 월평균 · 매주 월요일 갱신
      </p>
    </div>
  )
}
