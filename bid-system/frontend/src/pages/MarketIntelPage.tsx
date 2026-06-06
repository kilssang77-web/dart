import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Building2, TrendingUp, Award } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, ErrorBar
} from 'recharts'
import { marketIntelApi } from '@/api'
import type { AgencyHeatmapItem, WinnerTrendItem, TopWinnerItem } from '@/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'

export default function MarketIntelPage() {
  const [months, setMonths] = useState(12)
  const [selectedAgency, setSelectedAgency] = useState<string | undefined>(undefined)

  const { data: heatmap, isLoading: loadingHeatmap } = useQuery({
    queryKey: ['market-intel-heatmap', months],
    queryFn: () => marketIntelApi.agencyHeatmap(months, 20),
    staleTime: 300_000,
  })

  const { data: trend, isLoading: loadingTrend } = useQuery({
    queryKey: ['market-intel-trend', selectedAgency],
    queryFn: () => marketIntelApi.winnerTrend(selectedAgency),
    staleTime: 300_000,
  })

  const { data: winners, isLoading: loadingWinners } = useQuery({
    queryKey: ['market-intel-winners', selectedAgency],
    queryFn: () => marketIntelApi.topWinners(selectedAgency, 10),
    staleTime: 300_000,
  })

  const trendData = (trend?.trend ?? []).map((t: WinnerTrendItem) => ({
    label: `${t.year}-${String(t.month).padStart(2, '0')}`,
    avg_rate: t.avg_rate != null ? +(t.avg_rate * 100).toFixed(3) : null,
    bid_count: t.bid_count,
  }))

  const boxData = (heatmap?.agencies ?? []).map((a: AgencyHeatmapItem) => ({
    name: a.agency_name.slice(0, 12),
    avg: a.avg_rate != null ? +(a.avg_rate * 100).toFixed(3) : 0,
    p25: a.p25 != null ? +(a.p25 * 100).toFixed(3) : 0,
    p75: a.p75 != null ? +(a.p75 * 100).toFixed(3) : 0,
    count: a.bid_count,
  }))

  return (
    <div className="p-6 space-y-5">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-primary" /> 시장 인텔리전스
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            inpo21c 실측 데이터 기반 낙찰 패턴 분석
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={String(months)} onValueChange={(v) => setMonths(Number(v))}>
            <SelectTrigger className="h-8 w-28 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="6">최근 6개월</SelectItem>
              <SelectItem value="12">최근 12개월</SelectItem>
              <SelectItem value="24">최근 24개월</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* 발주처 낙찰율 분포 */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Building2 className="h-4 w-4" /> 발주처별 낙찰율 분포 (상위 20사)
            </CardTitle>
            <span className="text-xs text-muted-foreground">최근 {months}개월</span>
          </div>
        </CardHeader>
        <CardContent>
          {loadingHeatmap ? (
            <Skeleton className="h-48 w-full" />
          ) : boxData.length === 0 ? (
            <div className="h-48 flex items-center justify-center text-sm text-muted-foreground">
              데이터 없음
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={boxData} margin={{ bottom: 60, left: -10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="name" tick={{ fontSize: 9 }} angle={-40} textAnchor="end" interval={0} />
                <YAxis tick={{ fontSize: 9 }} unit="%" domain={['auto', 'auto']} />
                <Tooltip
                  formatter={(v: number) => [v + '%', '평균 낙찰율']}
                  labelFormatter={(l: string) => `발주처: ${l}`}
                />
                <Bar dataKey="avg" fill="hsl(var(--primary)/0.7)" radius={[3, 3, 0, 0]} name="평균 낙찰율" />
              </BarChart>
            </ResponsiveContainer>
          )}

          {/* 상세 테이블 */}
          {!loadingHeatmap && heatmap && heatmap.agencies.length > 0 && (
            <div className="mt-4 overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>발주처</TableHead>
                    <TableHead className="text-right">낙찰건수</TableHead>
                    <TableHead className="text-right">평균 낙찰율</TableHead>
                    <TableHead className="text-right">Q1(25%)</TableHead>
                    <TableHead className="text-right">Q3(75%)</TableHead>
                    <TableHead className="text-right">범위</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {heatmap.agencies.slice(0, 10).map((a: AgencyHeatmapItem) => (
                    <TableRow
                      key={a.agency_name}
                      className="cursor-pointer hover:bg-accent"
                      onClick={() => setSelectedAgency(a.agency_name === selectedAgency ? undefined : a.agency_name)}
                    >
                      <TableCell className="font-medium">
                        {a.agency_name}
                        {a.agency_name === selectedAgency && <Badge className="ml-1 text-[10px] h-4">선택됨</Badge>}
                      </TableCell>
                      <TableCell className="text-right">{a.bid_count}</TableCell>
                      <TableCell className="text-right font-mono">
                        {a.avg_rate != null ? (a.avg_rate * 100).toFixed(3) + '%' : '-'}
                      </TableCell>
                      <TableCell className="text-right font-mono text-muted-foreground">
                        {a.p25 != null ? (a.p25 * 100).toFixed(3) + '%' : '-'}
                      </TableCell>
                      <TableCell className="text-right font-mono text-muted-foreground">
                        {a.p75 != null ? (a.p75 * 100).toFixed(3) + '%' : '-'}
                      </TableCell>
                      <TableCell className="text-right text-xs text-muted-foreground">
                        {a.min_rate && a.max_rate
                          ? `${(a.min_rate * 100).toFixed(1)}%~${(a.max_rate * 100).toFixed(1)}%`
                          : '-'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* 월별 낙찰율 추세 */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <TrendingUp className="h-4 w-4" /> 월별 낙찰율 추세
              {selectedAgency && <Badge variant="secondary" className="text-[10px]">{selectedAgency.slice(0, 10)}</Badge>}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loadingTrend ? (
              <Skeleton className="h-40 w-full" />
            ) : trendData.length === 0 ? (
              <div className="h-40 flex items-center justify-center text-sm text-muted-foreground">데이터 없음</div>
            ) : (
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={trendData} margin={{ left: -20, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="label" tick={{ fontSize: 9 }} angle={-30} textAnchor="end" />
                  <YAxis tick={{ fontSize: 9 }} unit="%" domain={['auto', 'auto']} />
                  <Tooltip formatter={(v: number) => [v + '%', '평균 낙찰율']} />
                  <Line
                    type="monotone"
                    dataKey="avg_rate"
                    stroke="hsl(var(--primary))"
                    strokeWidth={2}
                    dot={false}
                    connectNulls
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* 낙찰 다발 업체 */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Award className="h-4 w-4" /> 낙찰 다발 업체 TOP 10
              {selectedAgency && <Badge variant="secondary" className="text-[10px]">{selectedAgency.slice(0, 10)}</Badge>}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {loadingWinners ? (
              <Skeleton className="h-40 w-full m-4" />
            ) : !winners || winners.length === 0 ? (
              <div className="h-40 flex items-center justify-center text-sm text-muted-foreground">데이터 없음</div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>#</TableHead>
                    <TableHead>업체명</TableHead>
                    <TableHead className="text-right">낙찰</TableHead>
                    <TableHead className="text-right">평균 낙찰율</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(winners as TopWinnerItem[]).map((w, i) => (
                    <TableRow key={i}>
                      <TableCell className="text-muted-foreground text-xs">{i + 1}</TableCell>
                      <TableCell className="text-sm truncate max-w-32">{w.company_name}</TableCell>
                      <TableCell className="text-right font-semibold">{w.win_count}건</TableCell>
                      <TableCell className="text-right font-mono text-xs">
                        {w.avg_rate != null ? (w.avg_rate * 100).toFixed(3) + '%' : '-'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
