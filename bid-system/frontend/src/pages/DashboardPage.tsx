import React from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer
} from 'recharts'
import { FileText, Users, TrendingUp, Activity, ArrowUp, ArrowDown } from 'lucide-react'
import { statsApi } from '@/api'
import type { OverviewStatsWithChange } from '@/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

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
  changeKey: keyof OverviewStatsWithChange | null
  higherIsBetter: boolean
  pct?: boolean
}

const STAT_CARDS: StatCardDef[] = [
  { key: 'total_bids',           label: '전체 입찰',    unit: '건',  icon: FileText,   color: 'text-blue-600',   changeKey: 'bid_count_change_pct',    higherIsBetter: true },
  { key: 'total_competitors',    label: '등록 경쟁사',  unit: '개사', icon: Users,      color: 'text-purple-600', changeKey: null,                       higherIsBetter: true },
  { key: 'avg_win_rate',         label: '평균 낙찰률',  unit: '%',   icon: TrendingUp, color: 'text-green-600',  changeKey: 'win_rate_change_pct',      higherIsBetter: true, pct: true },
  { key: 'avg_competitor_count', label: '평균 경쟁강도', unit: '개사', icon: Activity,   color: 'text-orange-600', changeKey: 'avg_competitors_change',   higherIsBetter: false },
]

function ChangeBadge({ value, higherIsBetter }: { value: number | null | undefined; higherIsBetter: boolean }) {
  if (value == null) return null
  const up = value > 0
  const isGood = higherIsBetter ? up : !up
  return (
    <span className={`inline-flex items-center gap-0.5 text-xs font-semibold ${isGood ? 'text-green-600' : 'text-red-500'}`}>
      {up ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />}
      {Math.abs(value).toFixed(1)}%
    </span>
  )
}

export default function DashboardPage() {
  const { data: overview, isLoading } = useQuery<OverviewStatsWithChange>({
    queryKey: ['overview'],
    queryFn: () => statsApi.overview(24),
  })
  const { data: agencies } = useQuery<AgencyStat[]>({
    queryKey: ['agency-stats'],
    queryFn: () => statsApi.agencies(12),
  })

  const trend = (overview?.monthly_trend ?? []).map((d) => ({
    label:  `${d.year}-${String(d.month).padStart(2, '0')}`,
    건수:   d.bid_count,
    낙찰률: d.avg_rate ? +(d.avg_rate * 100).toFixed(2) : null,
  }))
  const topAgencies = (agencies ?? []).slice(0, 10)

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">대시보드</h1>
        <p className="text-muted-foreground text-sm mt-1">최근 24개월 입찰 현황 개요</p>
      </div>

      {/* 통계 카드 */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {STAT_CARDS.map(({ key, label, unit, icon: Icon, color, changeKey, higherIsBetter, pct }) => {
          const raw = overview?.[key as keyof OverviewStatsWithChange] as number | null | undefined
          const display = raw == null
            ? '-'
            : pct
              ? (raw * 100).toFixed(2) + unit
              : key === 'avg_competitor_count'
                ? raw.toFixed(1) + unit
                : raw.toLocaleString() + unit
          const changeVal = changeKey ? overview?.[changeKey as keyof OverviewStatsWithChange] as number | null | undefined : null
          return (
            <Card key={key}>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
                <Icon className={`h-4 w-4 ${color}`} />
              </CardHeader>
              <CardContent>
                {isLoading
                  ? <Skeleton className="h-8 w-24" />
                  : (
                    <div className="flex items-end gap-2">
                      <p className="text-2xl font-bold">{display}</p>
                      <div className="mb-0.5">
                        <ChangeBadge value={changeVal} higherIsBetter={higherIsBetter} />
                      </div>
                    </div>
                  )
                }
              </CardContent>
            </Card>
          )
        })}
      </div>

      {/* 월별 추이 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold">월별 입찰 건수 / 낙찰률 추이 (24개월)</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={trend} margin={{ left: -10, right: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} interval={2} />
              <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
              <YAxis yAxisId="right" orientation="right" domain={[87, 92]} tick={{ fontSize: 11 }} unit="%" />
              <Tooltip formatter={(v: number, n: string) => [n === '낙찰률' ? v + '%' : v + '건', n]} />
              <Bar yAxisId="left" dataKey="건수" fill="hsl(var(--primary)/0.15)" radius={[3,3,0,0]} />
              <Line yAxisId="right" type="monotone" dataKey="낙찰률" stroke="hsl(var(--primary))" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* 발주기관 TOP 10 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold">발주기관별 입찰 건수 TOP 10 (12개월)</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={topAgencies} layout="vertical" margin={{ left: 80, right: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis type="number" tick={{ fontSize: 11 }} />
              <YAxis type="category" dataKey="agency_name" tick={{ fontSize: 11 }} width={80} />
              <Tooltip formatter={(v: number) => [v + '건', '입찰 건수']} />
              <Bar dataKey="bid_count" fill="hsl(var(--primary))" radius={[0,3,3,0]} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  )
}