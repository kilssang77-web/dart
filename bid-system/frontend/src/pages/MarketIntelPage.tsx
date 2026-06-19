import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Building2, TrendingUp, Award, BarChart3, Activity, ChevronRight } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line,
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
    avg_rate: t.avg_rate != null ? +(t.avg_rate * 100).toFixed(4) : null,
    bid_count: t.bid_count,
  }))

  const boxData = (heatmap?.agencies ?? []).map((a: AgencyHeatmapItem) => ({
    name: a.agency_name.slice(0, 12),
    avg: a.avg_rate != null ? +(a.avg_rate * 100).toFixed(4) : 0,
    p25: a.p25 != null ? +(a.p25 * 100).toFixed(4) : 0,
    p75: a.p75 != null ? +(a.p75 * 100).toFixed(4) : 0,
    count: a.bid_count,
  }))

  const maxWinCount = (winners as TopWinnerItem[] | undefined)?.reduce((m, w) => Math.max(m, w.win_count), 1) ?? 1

  return (
    <div className="flex flex-col min-h-full">
      {/* 스티키 헤더 */}
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-sm border-b border-slate-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-slate-900 flex items-center gap-2">
              <TrendingUp className="h-5 w-5 text-blue-600" />시장 인텔리전스
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">inpo21c 실측 데이터 기반 낙찰 패턴 분석</p>
          </div>
          <div className="flex items-center gap-2">
            <Select value={String(months)} onValueChange={(v) => setMonths(Number(v))}>
              <SelectTrigger className="h-8 w-32 text-xs border-slate-200 bg-white">
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
      </div>

      <div className="flex-1 p-6 max-w-[1440px] mx-auto w-full space-y-5">
        {/* 발주기관 낙찰률 분포 차트 카드 */}
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="border-b border-slate-100 pb-3 flex flex-row items-center justify-between">
            <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
              <Building2 className="h-4 w-4 text-blue-500" />발주기관별 낙찰률 분포
              <span className="text-xs font-normal text-slate-500">상위 20사</span>
            </CardTitle>
            <span className="text-xs text-slate-500">최근 {months}개월</span>
          </CardHeader>
          <CardContent className="pt-4">
            {loadingHeatmap ? (
              <Skeleton className="h-64 w-full rounded-lg" />
            ) : boxData.length === 0 ? (
              <div className="h-64 flex flex-col items-center justify-center text-slate-500">
                <BarChart3 className="h-8 w-8 mb-2 opacity-30" />
                <p className="text-sm">데이터 없음</p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={boxData} margin={{ bottom: 64, left: -10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="name" tick={{ fontSize: 12, fill: '#475569' }} angle={-40} textAnchor="end" interval={0} />
                  <YAxis tick={{ fontSize: 12, fill: '#475569' }} unit="%" domain={['auto', 'auto']} />
                  <Tooltip
                    contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                    formatter={(v: number) => [v + '%', '평균 낙찰률']}
                    labelFormatter={(l: string) => `발주기관: ${l}`}
                  />
                  <Bar dataKey="avg" fill="#2563eb" fillOpacity={0.8} radius={[4, 4, 0, 0]} name="평균 낙찰률" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* 발주기관 상세 테이블 */}
        {!loadingHeatmap && heatmap && heatmap.agencies.length > 0 && (
          <Card className="bg-white border-slate-200 shadow-sm">
            <CardHeader className="border-b border-slate-100 pb-3 flex flex-row items-center justify-between">
              <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                <Building2 className="h-4 w-4 text-blue-500" />발주기관 낙찰 상세
              </CardTitle>
              <span className="text-xs text-slate-500">
                {selectedAgency ? (
                  <span className="flex items-center gap-1">
                    <span className="text-blue-600 font-medium">{selectedAgency.slice(0, 12)}</span> 선택됨
                    <button onClick={() => setSelectedAgency(undefined)} className="ml-1 text-slate-500 hover:text-slate-600 underline">해제</button>
                  </span>
                ) : '행 클릭 시 추세 필터링'}
              </span>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-hidden rounded-b-lg">
                <Table>
                  <TableHeader className="bg-slate-50">
                    <TableRow>
                      <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide w-8">#</TableHead>
                      <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide">발주기관</TableHead>
                      <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide text-right">낙찰건수</TableHead>
                      <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide text-right">평균 낙찰률</TableHead>
                      <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide text-right">Q1 (25%)</TableHead>
                      <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide text-right">Q3 (75%)</TableHead>
                      <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide text-right">범위</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {heatmap.agencies.slice(0, 10).map((a: AgencyHeatmapItem, idx: number) => (
                      <TableRow
                        key={a.agency_name}
                        className="cursor-pointer hover:bg-blue-50/50 transition-colors"
                        onClick={() => setSelectedAgency(a.agency_name === selectedAgency ? undefined : a.agency_name)}
                      >
                        <TableCell className="text-sm text-slate-500 font-mono">{idx + 1}</TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-slate-800">{a.agency_name}</span>
                            {a.agency_name === selectedAgency && (
                              <Badge className="text-xs h-4 px-1.5 bg-blue-100 text-blue-700 border-0">선택</Badge>
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="text-right text-slate-600">{a.bid_count.toLocaleString()}</TableCell>
                        <TableCell className="text-right font-mono font-semibold text-blue-600">
                          {a.avg_rate != null ? (a.avg_rate * 100).toFixed(4) + '%' : '-'}
                        </TableCell>
                        <TableCell className="text-right font-mono text-slate-500 text-xs">
                          {a.p25 != null ? (a.p25 * 100).toFixed(4) + '%' : '-'}
                        </TableCell>
                        <TableCell className="text-right font-mono text-slate-500 text-xs">
                          {a.p75 != null ? (a.p75 * 100).toFixed(4) + '%' : '-'}
                        </TableCell>
                        <TableCell className="text-right text-sm text-slate-500">
                          {a.min_rate && a.max_rate
                            ? `${(a.min_rate * 100).toFixed(1)}%~${(a.max_rate * 100).toFixed(1)}%`
                            : '-'}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {/* 월별 낙찰률 추세 */}
          <Card className="bg-white border-slate-200 shadow-sm">
            <CardHeader className="border-b border-slate-100 pb-3 flex flex-row items-center justify-between">
              <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-blue-500" />월별 낙찰률 추세
                {selectedAgency && (
                  <Badge variant="secondary" className="text-xs bg-blue-50 text-blue-700 border-blue-200">
                    {selectedAgency.slice(0, 10)}
                  </Badge>
                )}
              </CardTitle>
              <span className="text-xs text-slate-500">{selectedAgency ? '선택 기관' : '전체'}</span>
            </CardHeader>
            <CardContent className="pt-4">
              {loadingTrend ? (
                <Skeleton className="h-48 w-full rounded-lg" />
              ) : trendData.length === 0 ? (
                <div className="h-48 flex flex-col items-center justify-center text-slate-500">
                  <Activity className="h-7 w-7 mb-2 opacity-30" />
                  <p className="text-sm">데이터 없음</p>
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={trendData} margin={{ left: -20, bottom: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="label" tick={{ fontSize: 12, fill: '#475569' }} angle={-30} textAnchor="end" />
                    <YAxis tick={{ fontSize: 12, fill: '#475569' }} unit="%" domain={['auto', 'auto']} />
                    <Tooltip
                      contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                      formatter={(v: number) => [v + '%', '평균 낙찰률']}
                    />
                    <Line
                      type="monotone"
                      dataKey="avg_rate"
                      stroke="#2563eb"
                      strokeWidth={2.5}
                      dot={false}
                      connectNulls
                    />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          {/* 낙찰 다발 업체 TOP 10 */}
          <Card className="bg-white border-slate-200 shadow-sm">
            <CardHeader className="border-b border-slate-100 pb-3 flex flex-row items-center justify-between">
              <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                <Award className="h-4 w-4 text-amber-500" />낙찰 다발 업체
                <span className="text-xs font-normal text-slate-500">TOP 10</span>
                {selectedAgency && (
                  <Badge variant="secondary" className="text-xs bg-blue-50 text-blue-700 border-blue-200">
                    {selectedAgency.slice(0, 10)}
                  </Badge>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {loadingWinners ? (
                <div className="p-4">
                  <Skeleton className="h-48 w-full rounded-lg" />
                </div>
              ) : !winners || winners.length === 0 ? (
                <div className="h-48 flex flex-col items-center justify-center text-slate-500">
                  <Award className="h-7 w-7 mb-2 opacity-30" />
                  <p className="text-sm">데이터 없음</p>
                </div>
              ) : (
                <div className="overflow-hidden">
                  <Table>
                    <TableHeader className="bg-slate-50">
                      <TableRow>
                        <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide w-8">#</TableHead>
                        <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide">업체명</TableHead>
                        <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide">비율</TableHead>
                        <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide text-right">낙찰</TableHead>
                        <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide text-right">평균율</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(winners as TopWinnerItem[]).map((w, i) => {
                        const barPct = Math.round((w.win_count / maxWinCount) * 100)
                        return (
                          <TableRow key={i} className="hover:bg-slate-50/80 transition-colors">
                            <TableCell className="text-sm text-slate-500 font-mono">
                              {i < 3 ? (
                                <span className={['text-amber-500 font-bold', 'text-slate-500 font-bold', 'text-orange-400 font-bold'][i]}>
                                  {i + 1}
                                </span>
                              ) : i + 1}
                            </TableCell>
                            <TableCell>
                              <span className="text-sm font-medium text-slate-700 truncate block max-w-[120px]">{w.company_name}</span>
                            </TableCell>
                            <TableCell className="pr-4">
                              <div className="flex items-center gap-1.5">
                                <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden w-16">
                                  <div
                                    className="h-full bg-blue-500 rounded-full transition-all"
                                    style={{ width: `${barPct}%` }}
                                  />
                                </div>
                                <span className="text-xs text-slate-500 w-7 text-right">{barPct}%</span>
                              </div>
                            </TableCell>
                            <TableCell className="text-right font-semibold text-slate-800">{w.win_count}<span className="text-xs font-normal text-slate-500 ml-0.5">건</span></TableCell>
                            <TableCell className="text-right font-mono text-sm text-slate-500">
                              {w.avg_rate != null ? (w.avg_rate * 100).toFixed(4) + '%' : '-'}
                            </TableCell>
                          </TableRow>
                        )
                      })}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* 히트맵 색상 범례 카드 */}
        {!loadingHeatmap && heatmap && heatmap.agencies.length > 0 && (
          <Card className="bg-white border-slate-200 shadow-sm">
            <CardHeader className="border-b border-slate-100 pb-3 flex flex-row items-center justify-between">
              <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                <BarChart3 className="h-4 w-4 text-blue-500" />발주기관 낙찰률 범위 분포
                <span className="text-xs font-normal text-slate-500">Q1 ~ Q3 박스플롯</span>
              </CardTitle>
              <span className="text-xs text-slate-500">최근 {months}개월</span>
            </CardHeader>
            <CardContent className="pt-4 space-y-2">
              {heatmap.agencies.slice(0, 10).map((a: AgencyHeatmapItem) => {
                if (a.avg_rate == null) return null
                const avgPct = +(a.avg_rate * 100).toFixed(4)
                const p25Pct = a.p25 != null ? +(a.p25 * 100).toFixed(4) : avgPct
                const p75Pct = a.p75 != null ? +(a.p75 * 100).toFixed(4) : avgPct
                const minV = 87, maxV = 95
                const toPos = (v: number) => Math.max(0, Math.min(100, ((v - minV) / (maxV - minV)) * 100))
                return (
                  <div key={a.agency_name} className="flex items-center gap-3 group">
                    <div
                      className="w-32 text-sm text-slate-600 truncate shrink-0 group-hover:text-blue-600 cursor-pointer transition-colors"
                      onClick={() => setSelectedAgency(a.agency_name === selectedAgency ? undefined : a.agency_name)}
                    >
                      {a.agency_name}
                    </div>
                    <div className="flex-1 relative h-5">
                      {/* 배경 트랙 */}
                      <div className="absolute inset-y-2 left-0 right-0 bg-slate-100 rounded-full" />
                      {/* IQR 박스 */}
                      <div
                        className="absolute inset-y-1 bg-blue-200 rounded"
                        style={{ left: `${toPos(p25Pct)}%`, width: `${toPos(p75Pct) - toPos(p25Pct)}%` }}
                      />
                      {/* 평균 마커 */}
                      <div
                        className="absolute inset-y-0 w-0.5 bg-blue-600 rounded-full"
                        style={{ left: `${toPos(avgPct)}%` }}
                      />
                    </div>
                    <div className="text-xs font-mono text-blue-600 w-16 text-right shrink-0">{avgPct}%</div>
                    <div className="flex items-center gap-1 text-xs text-slate-500 shrink-0">
                      <ChevronRight className="h-3 w-3" />
                      <span>{a.bid_count}건</span>
                    </div>
                  </div>
                )
              })}
              <div className="flex items-center justify-between text-xs text-slate-500 pt-2 border-t border-slate-100 mt-2">
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1.5"><div className="w-3 h-2 bg-blue-200 rounded" /><span>IQR (Q1~Q3)</span></div>
                  <div className="flex items-center gap-1.5"><div className="w-0.5 h-4 bg-blue-600 rounded" /><span>평균</span></div>
                </div>
                <span>87% ~ 95% 구간 표시</span>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
