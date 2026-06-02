import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ComposedChart, Area,
} from 'recharts'
import {
  FileText, Users, TrendingUp, Activity, ArrowUp, ArrowDown,
  Trophy, Building2, Clock, Zap,
} from 'lucide-react'
import { statsApi, bidsApi } from '@/api'
import type { OverviewStatsWithChange, Bid } from '@/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

interface AgencyStat {
  agency_id: number; agency_name: string
  bid_count: number; avg_rate: number | null; avg_competitor_count: number | null
}

interface StatCardDef {
  key: keyof OverviewStatsWithChange
  label: string
  unit: string
  icon: React.ComponentType<{ className?: string }>
  color: string
  bg: string
  changeKey: keyof OverviewStatsWithChange | null
  higherIsBetter: boolean
  pct?: boolean
}

const STAT_CARDS: StatCardDef[] = [
  { key: 'total_bids',           label: '전체 입찰 (24개월)', unit: '건',  icon: FileText,   color: 'text-blue-600',   bg: 'bg-blue-50',    changeKey: 'bid_count_change_pct',   higherIsBetter: true },
  { key: 'total_competitors',    label: '등록 경쟁사',        unit: '개사', icon: Users,      color: 'text-purple-600', bg: 'bg-purple-50',  changeKey: null,                      higherIsBetter: true },
  { key: 'avg_win_rate',         label: '평균 낙찰률',        unit: '%',   icon: TrendingUp, color: 'text-green-600',  bg: 'bg-green-50',   changeKey: 'win_rate_change_pct',     higherIsBetter: true, pct: true },
  { key: 'avg_competitor_count', label: '평균 경쟁강도',      unit: '개사', icon: Activity,   color: 'text-orange-600', bg: 'bg-orange-50',  changeKey: 'avg_competitors_change',  higherIsBetter: false },
]

function ChangeBadge({ value, higherIsBetter }: { value: number | null | undefined; higherIsBetter: boolean }) {
  if (value == null) return null
  const up = value > 0
  const isGood = higherIsBetter ? up : !up
  return (
    <span className={cn('inline-flex items-center gap-0.5 text-xs font-semibold', isGood ? 'text-green-600' : 'text-red-500')}>
      {up ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />}
      {Math.abs(value).toFixed(1)}%
    </span>
  )
}

function fmtAmt(n: number) {
  if (n >= 1e12) return (n / 1e12).toFixed(1) + '조'
  if (n >= 1e8)  return (n / 1e8).toFixed(0) + '억'
  if (n >= 1e4)  return (n / 1e4).toFixed(0) + '만'
  return n.toLocaleString()
}

export default function DashboardPage() {
  const navigate = useNavigate()

  const { data: overview, isLoading } = useQuery<OverviewStatsWithChange>({
    queryKey: ['overview', 24],
    queryFn: () => statsApi.overview(24),
  })

  const { data: allTime } = useQuery<OverviewStatsWithChange>({
    queryKey: ['overview', 120],
    queryFn: () => statsApi.overview(120),
    staleTime: 300_000,
  })

  const { data: agencies } = useQuery<AgencyStat[]>({
    queryKey: ['agency-stats', 12],
    queryFn: () => statsApi.agencies(12),
  })

  const { data: recentClosed } = useQuery<{ items: Bid[]; total: number }>({
    queryKey: ['recent-closed'],
    queryFn: () => bidsApi.list({ status: 'closed', sort_by: 'bid_open_date', size: 8 }),
    staleTime: 60_000,
  })

  const trend = (overview?.monthly_trend ?? []).map((d) => ({
    label:  `${d.year}-${String(d.month).padStart(2, '0')}`,
    건수:   d.bid_count,
    낙찰률: d.avg_rate ? +(d.avg_rate * 100).toFixed(2) : null,
  }))
  const topAgencies = (agencies ?? []).slice(0, 10)
  const recentWins = (recentClosed?.items ?? []).filter((b) => b.winner_rate != null).slice(0, 8)

  return (
    <div className="p-6 space-y-6">
      {/* 헤더 */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">대시보드</h1>
          <p className="text-muted-foreground text-sm mt-1">최근 24개월 입찰 현황 · 전체 누적 통계</p>
        </div>
        {allTime && (
          <div className="flex items-center gap-4 text-right">
            <div>
              <p className="text-[10px] text-muted-foreground uppercase tracking-wide">누적 입찰</p>
              <p className="text-lg font-bold text-primary">{(allTime.total_bids ?? 0).toLocaleString()}<span className="text-xs font-normal ml-0.5">건</span></p>
            </div>
            <div>
              <p className="text-[10px] text-muted-foreground uppercase tracking-wide">등록 경쟁사</p>
              <p className="text-lg font-bold text-purple-600">{(allTime.total_competitors ?? 0).toLocaleString()}<span className="text-xs font-normal ml-0.5">개사</span></p>
            </div>
          </div>
        )}
      </div>

      {/* KPI 카드 */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {STAT_CARDS.map(({ key, label, unit, icon: Icon, color, bg, changeKey, higherIsBetter, pct }) => {
          const raw = overview?.[key as keyof OverviewStatsWithChange] as number | null | undefined
          const display = raw == null ? '-'
            : pct ? (raw * 100).toFixed(2) + unit
            : key === 'avg_competitor_count' ? raw.toFixed(1) + unit
            : raw.toLocaleString() + unit
          const changeVal = changeKey ? overview?.[changeKey as keyof OverviewStatsWithChange] as number | null | undefined : null
          return (
            <Card key={key} className="overflow-hidden">
              <CardContent className="p-0">
                <div className={cn('px-4 pt-4 pb-3', bg + '/30')}>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-muted-foreground font-medium">{label}</span>
                    <div className={cn('p-1.5 rounded-md', bg)}>
                      <Icon className={cn('h-3.5 w-3.5', color)} />
                    </div>
                  </div>
                  {isLoading
                    ? <Skeleton className="h-8 w-24" />
                    : (
                      <div className="flex items-end gap-2">
                        <p className="text-2xl font-bold">{display}</p>
                        <div className="mb-0.5">
                          <ChangeBadge value={changeVal} higherIsBetter={higherIsBetter} />
                        </div>
                      </div>
                    )}
                  {changeVal != null && (
                    <p className="text-[10px] text-muted-foreground mt-1">전월 대비</p>
                  )}
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>

      {/* 월별 추이 */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center gap-2">
            <CardTitle className="text-sm font-semibold">월별 입찰 건수 · 낙찰률 추이</CardTitle>
            <Badge variant="secondary" className="text-[10px]">24개월</Badge>
          </div>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={220}>
            <ComposedChart data={trend} margin={{ left: -10, right: 10 }}>
              <defs>
                <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.2} />
                  <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="label" tick={{ fontSize: 10 }} interval={2} />
              <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} unit="%" />
              <Tooltip formatter={(v: number, n: string) => [n === '낙찰률' ? v + '%' : v + '건', n]} />
              <Bar yAxisId="left" dataKey="건수" fill="url(#barGradient)" stroke="hsl(var(--primary))" strokeWidth={1} radius={[3,3,0,0]} />
              <Line yAxisId="right" type="monotone" dataKey="낙찰률" stroke="hsl(var(--primary))" dot={false} strokeWidth={2} />
            </ComposedChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* 최근 낙찰현황 + 발주기관 TOP10 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 최근 낙찰현황 */}
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <Trophy className="h-4 w-4 text-yellow-500" />
              <CardTitle className="text-sm font-semibold">최근 낙찰현황</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y">
              {recentWins.length === 0
                ? <p className="text-center text-muted-foreground text-sm py-8">데이터 없음</p>
                : recentWins.map((b) => (
                  <div
                    key={b.id}
                    className="flex items-center gap-3 px-4 py-2.5 hover:bg-accent cursor-pointer transition-colors"
                    onClick={() => navigate(`/bids/${b.id}`)}
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium truncate">{b.title}</p>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <Building2 className="h-3 w-3 text-muted-foreground shrink-0" />
                        <span className="text-xs text-muted-foreground truncate">{b.agency_name}</span>
                        {b.bid_open_date && (
                          <span className="text-[10px] text-muted-foreground shrink-0">
                            · {new Date(b.bid_open_date).toLocaleDateString('ko-KR')}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <p className="text-sm font-bold font-mono text-primary">
                        {b.winner_rate ? (b.winner_rate * 100).toFixed(2) + '%' : '-'}
                      </p>
                      <p className="text-[10px] text-muted-foreground">{fmtAmt(b.base_amount)}</p>
                    </div>
                  </div>
                ))}
            </div>
          </CardContent>
        </Card>

        {/* 발주기관 TOP10 */}
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <Zap className="h-4 w-4 text-orange-500" />
              <CardTitle className="text-sm font-semibold">발주기관 입찰 건수 TOP 10</CardTitle>
              <Badge variant="secondary" className="text-[10px] ml-auto">12개월</Badge>
            </div>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={topAgencies} layout="vertical" margin={{ left: 80, right: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis
                  type="category"
                  dataKey="agency_name"
                  tick={{ fontSize: 10 }}
                  width={80}
                  tickFormatter={(v: string) => v.length > 8 ? v.slice(0, 8) + '…' : v}
                />
                <Tooltip formatter={(v: number) => [v + '건', '입찰 건수']} />
                <Bar dataKey="bid_count" fill="hsl(var(--primary))" radius={[0,3,3,0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
