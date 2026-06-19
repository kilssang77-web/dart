import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Search, Building2, ChevronRight, TrendingUp, Users, BarChart3, X } from 'lucide-react'
import { bidsApi, statsApi } from '@/api'
import type { MetaData } from '@/types'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

interface AgencyStatItem {
  agency_id: number
  agency_name: string
  bid_count: number
  avg_rate: number | null
  avg_competitor_count: number | null
}

function getRatingColor(bidCount: number): { bg: string; text: string; label: string } {
  if (bidCount >= 100) return { bg: 'bg-blue-50 border-blue-200', text: 'text-blue-700', label: 'A등급' }
  if (bidCount >= 50)  return { bg: 'bg-emerald-50 border-emerald-200', text: 'text-emerald-700', label: 'B등급' }
  if (bidCount >= 20)  return { bg: 'bg-amber-50 border-amber-200', text: 'text-amber-700', label: 'C등급' }
  return { bg: 'bg-slate-50 border-slate-200', text: 'text-slate-600', label: 'D등급' }
}

export default function AgenciesPage() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')

  const { data: meta } = useQuery<MetaData>({
    queryKey: ['meta'],
    queryFn: bidsApi.meta,
    staleTime: 300_000,
  })

  const { data: stats = [], isLoading } = useQuery<AgencyStatItem[]>({
    queryKey: ['stats-agencies', 24],
    queryFn: () => statsApi.agencies(24) as Promise<AgencyStatItem[]>,
    staleTime: 300_000,
  })

  const statsMap = new Map(stats.map((s) => [s.agency_id, s]))

  const filtered = (meta?.agencies ?? [])
    .filter((a) => !search || a.name.includes(search))
    .slice(0, 100)

  const top = [...stats]
    .sort((a, b) => (b.bid_count ?? 0) - (a.bid_count ?? 0))
    .slice(0, 10)

  const totalBids = stats.reduce((s, a) => s + a.bid_count, 0)
  const avgRate = stats.filter(a => a.avg_rate != null).reduce((s, a) => s + a.avg_rate!, 0) / Math.max(1, stats.filter(a => a.avg_rate != null).length)

  return (
    <div className="flex flex-col min-h-full">
      {/* 스티키 헤더 */}
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-sm border-b border-slate-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-slate-900 flex items-center gap-2">
              <Building2 className="h-5 w-5 text-blue-600" />발주기관 분석
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">발주기관별 입찰 패턴 · 사정율 분포 · 낙찰률 분석</p>
          </div>
          {/* 검색 바를 헤더에 통합 */}
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="발주기관 검색..."
                className="pl-9 pr-8 h-9 w-64 border-slate-200 bg-white text-sm focus:ring-2 focus:ring-blue-500/20"
              />
              {search && (
                <button
                  onClick={() => setSearch('')}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-600 transition-colors"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="flex-1 p-6 max-w-[1440px] mx-auto w-full space-y-6">
        {/* 요약 KPI */}
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: '총 발주기관', value: (meta?.agencies ?? []).length.toLocaleString(), unit: '개사', icon: Building2, color: 'blue' },
            { label: '총 입찰건수', value: totalBids.toLocaleString(), unit: '건', icon: BarChart3, color: 'emerald' },
            { label: '평균 낙찰률', value: avgRate ? (avgRate * 100).toFixed(4) : '-', unit: '%', icon: TrendingUp, color: 'amber' },
          ].map(({ label, value, unit, icon: Icon, color }) => (
            <Card key={label} className="relative overflow-hidden bg-white border-slate-200 shadow-sm">
              <div className={cn('absolute top-0 left-0 right-0 h-0.5',
                color === 'blue' ? 'bg-blue-500' : color === 'emerald' ? 'bg-emerald-500' : 'bg-amber-500'
              )} />
              <CardContent className="p-5">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm font-medium text-slate-500">{label}</p>
                    <p className="text-2xl font-bold mt-1 tabular-nums text-slate-900">
                      {value}<span className="text-sm font-normal text-slate-500 ml-1">{unit}</span>
                    </p>
                  </div>
                  <div className={cn('rounded-xl p-2.5',
                    color === 'blue' ? 'bg-blue-50' : color === 'emerald' ? 'bg-emerald-50' : 'bg-amber-50'
                  )}>
                    <Icon className={cn('h-5 w-5',
                      color === 'blue' ? 'text-blue-600' : color === 'emerald' ? 'text-emerald-600' : 'text-amber-600'
                    )} />
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* 입찰공고 상위 발주기관 TOP 10 */}
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="border-b border-slate-100 pb-3 flex flex-row items-center justify-between">
            <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
              <BarChart3 className="h-4 w-4 text-blue-500" />입찰공고 상위 발주기관
            </CardTitle>
            <span className="text-xs text-slate-500">최근 24개월 기준 TOP 10</span>
          </CardHeader>
          <CardContent className="pt-4">
            {isLoading ? (
              <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                {Array.from({ length: 10 }).map((_, i) => <Skeleton key={i} className="h-20 rounded-xl" />)}
              </div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                {top.map((s, i) => {
                  const rating = getRatingColor(s.bid_count)
                  return (
                    <button
                      key={s.agency_id}
                      onClick={() => navigate(`/agencies/${s.agency_id}`)}
                      className={cn(
                        'rounded-xl p-3.5 text-left transition-all border hover:shadow-md hover:-translate-y-0.5 group',
                        rating.bg
                      )}
                    >
                      <div className="flex items-start justify-between mb-2">
                        <span className={cn('text-xs font-bold px-1.5 py-0.5 rounded border', rating.text, rating.bg)}>
                          {rating.label}
                        </span>
                        <span className="text-xs text-slate-500 font-mono">#{i + 1}</span>
                      </div>
                      <p className="text-xs font-semibold text-slate-800 truncate group-hover:text-blue-700 transition-colors">{s.agency_name}</p>
                      <div className="flex items-center justify-between mt-1.5">
                        <p className="text-xs text-slate-500">{s.bid_count.toLocaleString()}건</p>
                        {s.avg_rate != null && (
                          <p className="text-xs font-mono text-blue-600">{(s.avg_rate * 100).toFixed(4)}%</p>
                        )}
                      </div>
                    </button>
                  )
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* 전체 기관 목록 */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
              <Users className="h-4 w-4 text-blue-500" />전체 발주기관
              {search && (
                <Badge variant="secondary" className="text-xs bg-blue-50 text-blue-700 border-blue-200">
                  "{search}" 검색 결과 {filtered.length}건
                </Badge>
              )}
            </h2>
            {!search && (
              <span className="text-xs text-slate-500">{filtered.length}개 기관 표시</span>
            )}
          </div>

          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-slate-500">
              <Search className="h-10 w-10 mb-3 opacity-30" />
              <p className="text-sm">검색 결과가 없습니다.</p>
              <button onClick={() => setSearch('')} className="text-xs text-blue-500 mt-2 hover:underline">검색 초기화</button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
              {filtered.map((a) => {
                const s = statsMap.get(a.id)
                const rating = s ? getRatingColor(s.bid_count) : null
                return (
                  <button
                    key={a.id}
                    onClick={() => navigate(`/agencies/${a.id}`)}
                    className="group bg-white border border-slate-200 hover:border-blue-300 hover:shadow-sm rounded-xl px-4 py-3 text-left transition-all"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 min-w-0">
                        <div className="w-1.5 h-1.5 rounded-full bg-slate-300 group-hover:bg-blue-500 transition-colors shrink-0" />
                        <span className="text-sm font-medium text-slate-800 truncate group-hover:text-blue-700 transition-colors">{a.name}</span>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0 ml-2">
                        {rating && (
                          <span className={cn('text-xs font-bold px-1.5 py-0.5 rounded border shrink-0', rating.text, rating.bg)}>
                            {rating.label}
                          </span>
                        )}
                        {s && (
                          <Badge variant="secondary" className="text-xs bg-slate-100 text-slate-600 border-0">
                            {s.bid_count.toLocaleString()}건
                          </Badge>
                        )}
                        <ChevronRight className="h-3.5 w-3.5 text-slate-300 group-hover:text-blue-500 transition-colors" />
                      </div>
                    </div>
                    {s && (
                      <div className="flex items-center gap-3 mt-1.5 ml-3.5">
                        {s.avg_rate != null ? (
                          <span className="text-xs text-blue-600 font-medium">평균 {(s.avg_rate * 100).toFixed(4)}%</span>
                        ) : (
                          <span className="text-xs text-slate-500">낙찰 데이터 없음</span>
                        )}
                        {s.avg_competitor_count != null && (
                          <span className="text-xs text-slate-500">경쟁 {s.avg_competitor_count.toFixed(0)}개사</span>
                        )}
                      </div>
                    )}
                  </button>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
