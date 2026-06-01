import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Search, Building2 } from 'lucide-react'
import { bidsApi, statsApi } from '@/api'
import type { MetaData } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'

interface AgencyStatItem {
  agency_id: number
  agency_name: string
  bid_count: number
  avg_rate: number | null
  avg_competitor_count: number | null
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

  return (
    <div className="p-6 space-y-5">
      <div>
        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <Building2 className="h-5 w-5" />발주처 분석
        </h1>
        <p className="text-muted-foreground text-sm mt-1">
          발주기관별 입찰 패턴 · 사정율 분포 · 낙찰률 분석
        </p>
      </div>

      {/* 상위 발주처 */}
      <div>
        <p className="text-sm font-semibold mb-2">입찰공고 상위 발주처</p>
        {isLoading ? (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            {Array.from({ length: 10 }).map((_, i) => <Skeleton key={i} className="h-14 rounded-lg" />)}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            {top.map((s) => (
              <button
                key={s.agency_id}
                onClick={() => navigate(`/agencies/${s.agency_id}`)}
                className="bg-muted/40 hover:bg-accent rounded-lg p-3 text-left transition-colors border border-transparent hover:border-border"
              >
                <p className="text-xs font-medium truncate">{s.agency_name}</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {s.bid_count}건
                  {s.avg_rate != null && ` · ${(s.avg_rate * 100).toFixed(2)}%`}
                </p>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 전체 검색 */}
      <div>
        <div className="flex gap-2 mb-3">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="발주기관 검색..."
              className="pl-9"
            />
          </div>
          {search && (
            <Button variant="ghost" size="sm" onClick={() => setSearch('')}>초기화</Button>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
          {filtered.map((a) => {
            const s = statsMap.get(a.id)
            return (
              <Card
                key={a.id}
                className="cursor-pointer hover:border-primary/50 transition-colors"
                onClick={() => navigate(`/agencies/${a.id}`)}
              >
                <CardContent className="py-3 px-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium truncate">{a.name}</span>
                    {s && (
                      <Badge variant="secondary" className="shrink-0 ml-1 text-[10px]">
                        {s.bid_count}건
                      </Badge>
                    )}
                  </div>
                  {s && (
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {s.avg_rate != null ? `평균 ${(s.avg_rate * 100).toFixed(2)}%` : '낙찰 데이터 없음'}
                      {s.avg_competitor_count != null && ` · 경쟁 ${s.avg_competitor_count.toFixed(0)}개사`}
                    </p>
                  )}
                </CardContent>
              </Card>
            )
          })}
        </div>

        {filtered.length === 0 && (
          <p className="text-center text-muted-foreground py-10 text-sm">검색 결과가 없습니다.</p>
        )}
      </div>
    </div>
  )
}
