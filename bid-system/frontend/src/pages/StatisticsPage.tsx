import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
  LineChart, Line, PieChart, Pie, Cell, ScatterChart, Scatter, Legend,
  ComposedChart,
} from 'recharts'
import { statsApi, bidsApi } from '@/api'
import type { OverviewStatsWithChange, MetaData, RegionStat, IndustryStat, ClusterResult, ModelInfo } from '@/types'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select'
import {
  Download, BarChart3, MapPin, GitBranch, Cpu, SlidersHorizontal,
  TrendingUp, Users, Target, Activity, Building2, Award, Database,
} from 'lucide-react'

function downloadCsv(filename: string, rows: string[][]) {
  const bom = '﻿'
  const csv = bom + rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\r\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

const COLORS = ['#2563eb', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#be185d', '#65a30d']
const PERIOD_OPTIONS = [3, 6, 12, 24]

interface HeatmapItem { month: number; industry: string; avg_rate: number; count: number }
interface RateDistItem { rate_pct: number; count: number }
interface AgencyStatItem {
  agency_id: number; agency_name: string
  bid_count: number; avg_rate: number | null; avg_competitor_count: number | null
}

export default function StatisticsPage() {
  const [tab, setTab] = useState('overview')
  const [months, setMonths] = useState(12)
  const [srateAgencyId, setSrateAgencyId] = useState<number | null>(null)
  const [srateIndustryId, setSrateIndustryId] = useState<number | null>(null)
  const [srateViewMode, setSrateViewMode] = useState<'count' | 'ratio'>('count')
  const selectedLabel = `최근 ${months}개월`

  const { data: overview, isLoading: ovLoading } = useQuery<OverviewStatsWithChange>({
    queryKey: ['stats-overview', months], queryFn: () => statsApi.overview(months),
    enabled: tab === 'overview', staleTime: 30_000,
  })
  const { data: agencies = [], isLoading: agLoading } = useQuery<AgencyStatItem[]>({
    queryKey: ['stats-agencies', months], queryFn: () => statsApi.agencies(months),
    enabled: tab === 'overview', staleTime: 30_000,
  })
  const { data: rateDist = [] } = useQuery<RateDistItem[]>({
    queryKey: ['stats-rate-dist', months], queryFn: () => statsApi.rateDistribution({ months }),
    enabled: tab === 'overview', staleTime: 30_000,
  })
  const { data: heatmap = [] } = useQuery<HeatmapItem[]>({
    queryKey: ['stats-heatmap', months], queryFn: () => statsApi.heatmap(months),
    enabled: tab === 'overview', staleTime: 60_000,
  })
  const { data: regions = [], isLoading: rgLoading } = useQuery<RegionStat[]>({
    queryKey: ['stats-regions', months], queryFn: () => statsApi.regions(months),
    enabled: tab === 'level1', staleTime: 30_000,
  })
  const { data: industries = [], isLoading: indLoading } = useQuery<IndustryStat[]>({
    queryKey: ['stats-industries', months], queryFn: () => statsApi.industries(months),
    enabled: tab === 'level1', staleTime: 30_000,
  })
  const { data: cluster, isLoading: clusterLoading, isError: clusterError } = useQuery<ClusterResult>({
    queryKey: ['stats-cluster', months], queryFn: () => statsApi.cluster({ months }),
    enabled: tab === 'level2', staleTime: 60_000, retry: 1,
  })
  const { data: modelInfo, isLoading: mlLoading } = useQuery<ModelInfo>({
    queryKey: ['model-info', months], queryFn: () => statsApi.modelInfo(months),
    enabled: tab === 'level3', staleTime: 30_000,
  })
  const { data: meta } = useQuery<MetaData>({
    queryKey: ['bids-meta'], queryFn: () => bidsApi.meta(),
    enabled: tab === 'srate', staleTime: 300_000,
  })
  const { data: srateDist } = useQuery({
    queryKey: ['srate-dist', srateAgencyId, srateIndustryId, months],
    queryFn: () => statsApi.srateDistribution({ agency_id: srateAgencyId ?? undefined, industry_id: srateIndustryId ?? undefined, months }),
    enabled: tab === 'srate', staleTime: 60_000,
  })

  const industries_list: string[] = [...new Set((heatmap ?? []).map((d: HeatmapItem) => d.industry))].slice(0, 6)
  const months_list = Array.from({length: 12}, (_, i) => i + 1)
  const heatmapRows = months_list.map((m) => {
    const row: Record<string, string | number | null> = { month: m }
    industries_list.forEach((ind) => {
      const cell = (heatmap ?? []).find((d: HeatmapItem) => d.month === m && d.industry === ind)
      row[ind] = cell ? +(cell.avg_rate * 100).toFixed(2) : null
    })
    return row
  })
  const trendData = (overview?.monthly_trend ?? []).map((d) => ({
    label: `${d.year}-${String(d.month).padStart(2,'0')}`, 입찰수: d.bid_count,
    낙찰율: d.avg_rate ? +(d.avg_rate * 100).toFixed(2) : null,
  }))
  const regionChartData = regions.filter((r) => r.avg_rate !== null)
    .map((r) => ({ name: r.region_name, rate: +((r.avg_rate! * 100)).toFixed(2), count: r.bid_count })).slice(0, 12)
  const industryChartData = industries.filter((i) => i.avg_rate !== null)
    .map((i) => ({ name: i.industry_name.slice(0, 12), rate: +((i.avg_rate! * 100)).toFixed(2), count: i.bid_count })).slice(0, 15)
  const clusterChartData = (cluster?.clusters ?? []).filter((c) => c.avg_rate !== null)

  function fmtAmt(n: number) {
    if (n >= 1e12) return (n / 1e12).toFixed(1) + '조'
    if (n >= 1e8)  return (n / 1e8).toFixed(0) + '억'
    if (n >= 1e4)  return (n / 1e4).toFixed(0) + '만'
    return n.toLocaleString()
  }

  function handleCsvDownload() {
    if (tab === 'overview') {
      const headers = ['발주처', '입찰건수', '평균낙찰률(%)', '평균경쟁사수']
      const rows = [headers, ...(agencies as AgencyStatItem[]).map((a) => [
        a.agency_name,
        String(a.bid_count),
        a.avg_rate ? (a.avg_rate * 100).toFixed(2) : '',
        a.avg_competitor_count ? a.avg_competitor_count.toFixed(1) : '',
      ])]
      downloadCsv(`발주처통계_${months}개월.csv`, rows)
    } else if (tab === 'level1') {
      const headers = ['공종명', '입찰건수', '평균낙찰률(%)', '평균경쟁사수', '총금액']
      const rows = [headers, ...industries.map((ind) => [
        ind.industry_name,
        String(ind.bid_count),
        ind.avg_rate ? (ind.avg_rate * 100).toFixed(2) : '',
        ind.avg_competitor_count ? ind.avg_competitor_count.toFixed(1) : '',
        String(ind.total_amount),
      ])]
      downloadCsv(`공종별통계_${months}개월.csv`, rows)
    }
  }

  const tabConfig = [
    { value: 'overview', label: '개요', icon: BarChart3 },
    { value: 'level1', label: '지역 · 공종', icon: MapPin },
    { value: 'level2', label: '클러스터', icon: GitBranch },
    { value: 'level3', label: 'ML 모델', icon: Cpu },
    { value: 'srate', label: '사정율 분포', icon: SlidersHorizontal },
  ]

  return (
    <div className="flex flex-col min-h-full">
      {/* 스티키 헤더 */}
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-sm border-b border-slate-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-slate-900 flex items-center gap-2">
              <BarChart3 className="h-5 w-5 text-blue-600" />통계 분석
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">{selectedLabel} 기준 입찰 통계 현황</p>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center rounded-lg border border-slate-200 overflow-hidden">
              {PERIOD_OPTIONS.map((m) => (
                <button
                  key={m}
                  onClick={() => setMonths(m)}
                  className={cn(
                    'px-3 py-1.5 text-sm font-medium transition-colors',
                    months === m
                      ? 'bg-blue-600 text-white'
                      : 'bg-white text-slate-600 hover:bg-slate-50'
                  )}
                >
                  {m}개월
                </button>
              ))}
            </div>
            {(tab === 'overview' || tab === 'level1') && (
              <Button variant="outline" size="sm" onClick={handleCsvDownload}
                className="h-8 px-3 text-xs gap-1.5 border-slate-200 text-slate-600 hover:bg-slate-50">
                <Download className="h-3.5 w-3.5" />CSV
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* 탭 네비게이션 */}
      <div className="border-b border-slate-200 bg-white px-6">
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="h-auto p-0 bg-transparent gap-0 rounded-none">
            {tabConfig.map(({ value, label, icon: Icon }) => (
              <TabsTrigger
                key={value}
                value={value}
                className={cn(
                  'flex items-center gap-1.5 px-4 py-3 text-sm font-medium rounded-none border-b-2 transition-colors',
                  'data-[state=active]:border-blue-600 data-[state=active]:text-blue-600 data-[state=active]:bg-transparent',
                  'data-[state=inactive]:border-transparent data-[state=inactive]:text-slate-500',
                  'hover:text-slate-700 hover:bg-slate-50'
                )}
              >
                <Icon className="h-3.5 w-3.5" />{label}
              </TabsTrigger>
            ))}
          </TabsList>

          {/* ── 개요 탭 ── */}
          <TabsContent value="overview" className="mt-0">
            <div className="p-6 max-w-[1440px] mx-auto w-full space-y-5">
              {(ovLoading || agLoading) ? (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {Array.from({length: 4}).map((_, i) => <Skeleton key={i} className="h-28 w-full rounded-xl" />)}
                </div>
              ) : overview ? (
                <>
                  {/* KPI 카드 4개 */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    {[
                      { label: `총 입찰건수`, value: overview.total_bids.toLocaleString(), sub: `${selectedLabel} 기준`, unit: '건', icon: Activity, color: 'blue' },
                      { label: '경쟁업체 수', value: overview.total_competitors.toLocaleString(), sub: '입찰 참여 업체', unit: '개사', icon: Users, color: 'emerald' },
                      { label: '평균 낙찰률', value: overview.avg_win_rate ? (overview.avg_win_rate * 100).toFixed(2) : '-', sub: '전체 평균', unit: '%', icon: Target, color: 'amber' },
                      { label: '평균 경쟁사', value: (overview.avg_competitor_count ?? 0).toFixed(1), sub: '공고당 평균', unit: '개사', icon: TrendingUp, color: 'violet' },
                    ].map(({ label, value, sub, unit, icon: Icon, color }) => (
                      <Card key={label} className="relative overflow-hidden bg-white border-slate-200 shadow-sm">
                        <div className={cn('absolute top-0 left-0 right-0 h-0.5',
                          color === 'blue' ? 'bg-blue-500' :
                          color === 'emerald' ? 'bg-emerald-500' :
                          color === 'amber' ? 'bg-amber-500' : 'bg-violet-500'
                        )} />
                        <CardContent className="p-5">
                          <div className="flex items-start justify-between">
                            <div>
                              <p className="text-sm font-medium text-slate-500">{label}</p>
                              <p className="text-2xl font-bold mt-1 tabular-nums text-slate-900">
                                {value}<span className="text-sm font-normal text-slate-500 ml-1">{unit}</span>
                              </p>
                              <p className="text-xs text-slate-500 mt-1">{sub}</p>
                            </div>
                            <div className={cn('rounded-xl p-2.5',
                              color === 'blue' ? 'bg-blue-50' :
                              color === 'emerald' ? 'bg-emerald-50' :
                              color === 'amber' ? 'bg-amber-50' : 'bg-violet-50'
                            )}>
                              <Icon className={cn('h-5 w-5',
                                color === 'blue' ? 'text-blue-600' :
                                color === 'emerald' ? 'text-emerald-600' :
                                color === 'amber' ? 'text-amber-600' : 'text-violet-600'
                              )} />
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>

                  {/* 월별 입찰 추이 */}
                  {trendData.length > 0 && (
                    <Card className="bg-white border-slate-200 shadow-sm">
                      <CardHeader className="border-b border-slate-100 pb-3 flex flex-row items-center justify-between">
                        <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                          <TrendingUp className="h-4 w-4 text-blue-500" />월별 입찰 추이
                        </CardTitle>
                        <span className="text-xs text-slate-500">입찰수 / 낙찰율(%)</span>
                      </CardHeader>
                      <CardContent className="pt-4">
                        <ResponsiveContainer width="100%" height={220}>
                          <LineChart data={trendData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                            <XAxis dataKey="label" tick={{ fontSize: 12, fill: '#475569' }} interval={1} />
                            <YAxis yAxisId="l" tick={{ fontSize: 12, fill: '#475569' }} />
                            <YAxis yAxisId="r" orientation="right" tick={{ fontSize: 12, fill: '#475569' }} unit="%" />
                            <Tooltip contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }} />
                            <Line yAxisId="l" type="monotone" dataKey="입찰수" stroke="#94a3b8" strokeWidth={1.5} dot={false} />
                            <Line yAxisId="r" type="monotone" dataKey="낙찰율" stroke="#2563eb" strokeWidth={2} dot={false} />
                          </LineChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>
                  )}

                  <div className="grid grid-cols-2 gap-5">
                    {/* 기관별 낙찰률 TOP 20 */}
                    {agencies.length > 0 && (
                      <Card className="bg-white border-slate-200 shadow-sm">
                        <CardHeader className="border-b border-slate-100 pb-3 flex flex-row items-center justify-between">
                          <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                            <Building2 className="h-4 w-4 text-blue-500" />기관별 낙찰률
                          </CardTitle>
                          <span className="text-xs text-slate-500">상위 20개</span>
                        </CardHeader>
                        <CardContent className="p-0">
                          <div className="overflow-auto max-h-72">
                            <div className="overflow-hidden">
                              <Table>
                                <TableHeader className="bg-slate-50">
                                  <TableRow>
                                    <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide w-8">#</TableHead>
                                    <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide">기관명</TableHead>
                                    <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide text-right">건수</TableHead>
                                    <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide text-right">낙찰률</TableHead>
                                    <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide text-right">경쟁</TableHead>
                                  </TableRow>
                                </TableHeader>
                                <TableBody>
                                  {(agencies as AgencyStatItem[]).slice(0, 20).map((a, idx) => (
                                    <TableRow key={a.agency_id} className="hover:bg-slate-50/80 transition-colors">
                                      <TableCell className="py-2 text-sm text-slate-500 font-mono">{idx + 1}</TableCell>
                                      <TableCell className="py-2 text-xs truncate max-w-[130px] font-medium text-slate-700">{a.agency_name}</TableCell>
                                      <TableCell className="py-2 text-right text-sm text-slate-600">{a.bid_count.toLocaleString()}</TableCell>
                                      <TableCell className="py-2 text-right text-xs font-semibold text-blue-600">
                                        {a.avg_rate ? (a.avg_rate * 100).toFixed(2) + '%' : '-'}
                                      </TableCell>
                                      <TableCell className="py-2 text-right text-sm text-slate-500">
                                        {a.avg_competitor_count ? a.avg_competitor_count.toFixed(1) : '-'}
                                      </TableCell>
                                    </TableRow>
                                  ))}
                                </TableBody>
                              </Table>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    )}

                    {/* 낙찰률 분포 */}
                    {rateDist.length > 0 && (
                      <Card className="bg-white border-slate-200 shadow-sm">
                        <CardHeader className="border-b border-slate-100 pb-3 flex flex-row items-center justify-between">
                          <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                            <Activity className="h-4 w-4 text-blue-500" />낙찰률 분포
                          </CardTitle>
                          <span className="text-xs text-slate-500">80~100% 구간</span>
                        </CardHeader>
                        <CardContent className="pt-4">
                          <ResponsiveContainer width="100%" height={240}>
                            <BarChart data={(rateDist as RateDistItem[]).filter((d) => d.rate_pct >= 80 && d.rate_pct <= 100)}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                              <XAxis dataKey="rate_pct" tick={{ fontSize: 12, fill: '#475569' }} unit="%" interval={4} />
                              <YAxis tick={{ fontSize: 12, fill: '#475569' }} />
                              <Tooltip
                                contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                                formatter={(v) => [v, '건수']}
                                labelFormatter={(l) => `${l}%`}
                              />
                              <Bar dataKey="count" fill="#2563eb" radius={[3, 3, 0, 0]} opacity={0.8} />
                            </BarChart>
                          </ResponsiveContainer>
                        </CardContent>
                      </Card>
                    )}
                  </div>

                  {/* 히트맵 */}
                  {heatmapRows.some((r) => industries_list.some((ind) => r[ind] !== null)) && (
                    <Card className="bg-white border-slate-200 shadow-sm">
                      <CardHeader className="border-b border-slate-100 pb-3 flex flex-row items-center justify-between">
                        <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                          <Database className="h-4 w-4 text-blue-500" />월별 × 공종별 낙찰률 히트맵
                        </CardTitle>
                        <span className="text-xs text-slate-500">색상 진할수록 높은 낙찰률</span>
                      </CardHeader>
                      <CardContent className="pt-4">
                        <div className="overflow-x-auto">
                          <table className="text-xs w-full">
                            <thead>
                              <tr>
                                <th className="text-left px-3 py-2 text-slate-500 font-medium w-12">월</th>
                                {industries_list.map((ind) => (
                                  <th key={ind} className="text-center px-2 py-2 text-slate-500 font-medium truncate max-w-[90px]">
                                    {ind.slice(0, 8)}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {heatmapRows.map((row) => (
                                <tr key={row.month as number} className="border-t border-slate-50">
                                  <td className="px-3 py-2 text-slate-500 font-medium">{row.month}월</td>
                                  {industries_list.map((ind) => {
                                    const v = row[ind] as number | null
                                    const heat = v ? Math.min(1, Math.max(0, (v - 85) / 10)) : 0
                                    return (
                                      <td key={ind} className="px-2 py-2 text-center rounded-md mx-0.5"
                                        style={{
                                          backgroundColor: v ? `rgba(37,99,235,${heat * 0.65 + 0.08})` : '#f8fafc',
                                          color: heat > 0.5 ? 'white' : '#475569',
                                          fontWeight: heat > 0.5 ? 600 : 400,
                                        }}>
                                        {v ? `${v}%` : '–'}
                                      </td>
                                    )
                                  })}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        {/* 범례 */}
                        <div className="flex items-center gap-2 mt-3">
                          <span className="text-xs text-slate-500">낮음</span>
                          <div className="flex gap-0.5">
                            {[0.1, 0.25, 0.4, 0.55, 0.7, 0.85, 1.0].map((o) => (
                              <div key={o} className="w-5 h-3 rounded-sm" style={{ backgroundColor: `rgba(37,99,235,${o})` }} />
                            ))}
                          </div>
                          <span className="text-xs text-slate-500">높음</span>
                        </div>
                      </CardContent>
                    </Card>
                  )}
                </>
              ) : <div className="flex flex-col items-center justify-center py-20 text-slate-500">
                  <BarChart3 className="h-10 w-10 mb-3 opacity-30" />
                  <p className="text-sm">데이터가 없습니다</p>
                </div>}
            </div>
          </TabsContent>

          {/* ── Level 1: 지역·공종 탭 ── */}
          <TabsContent value="level1" className="mt-0">
            <div className="p-6 max-w-[1440px] mx-auto w-full space-y-5">
              {(rgLoading || indLoading) ? <Skeleton className="h-64 w-full rounded-xl" /> : (
                <>
                  <div className="flex items-center gap-2 px-4 py-2.5 bg-blue-50 border border-blue-200 rounded-lg">
                    <MapPin className="h-4 w-4 text-blue-600 shrink-0" />
                    <span className="text-sm text-blue-700">{selectedLabel} 기준 지역 · 공종 분석 데이터입니다.</span>
                  </div>

                  <div className="grid grid-cols-2 gap-5">
                    <Card className="bg-white border-slate-200 shadow-sm">
                      <CardHeader className="border-b border-slate-100 pb-3 flex flex-row items-center justify-between">
                        <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                          <MapPin className="h-4 w-4 text-blue-500" />지역별 평균 낙찰률
                        </CardTitle>
                        <span className="text-xs text-slate-500">상위 12개</span>
                      </CardHeader>
                      <CardContent className="pt-4">
                        {regionChartData.length > 0 ? (
                          <ResponsiveContainer width="100%" height={300}>
                            <BarChart data={regionChartData} layout="vertical">
                              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                              <XAxis type="number" tick={{ fontSize: 12, fill: '#475569' }} unit="%" domain={['auto','auto']} />
                              <YAxis type="category" dataKey="name" width={80} tick={{ fontSize: 10, fill: '#64748b' }} />
                              <Tooltip
                                contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                                formatter={(v) => [`${v}%`, '낙찰률']}
                              />
                              <Bar dataKey="rate" fill="#2563eb" radius={[0, 3, 3, 0]} opacity={0.85} />
                            </BarChart>
                          </ResponsiveContainer>
                        ) : <div className="flex items-center justify-center h-40 text-sm text-slate-500">데이터 없음</div>}
                      </CardContent>
                    </Card>

                    <Card className="bg-white border-slate-200 shadow-sm">
                      <CardHeader className="border-b border-slate-100 pb-3 flex flex-row items-center justify-between">
                        <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                          <Activity className="h-4 w-4 text-emerald-500" />지역별 입찰 비중
                        </CardTitle>
                        <span className="text-xs text-slate-500">상위 8개 지역</span>
                      </CardHeader>
                      <CardContent className="pt-4">
                        {regions.length > 0 ? (
                          <ResponsiveContainer width="100%" height={300}>
                            <PieChart>
                              <Pie data={regions.slice(0,8)} dataKey="bid_count" nameKey="region_name"
                                cx="50%" cy="50%" outerRadius={110} innerRadius={50}
                                label={({name, percent}) => percent > 0.05 ? `${name} ${(percent*100).toFixed(0)}%` : ''}>
                                {regions.slice(0,8).map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                              </Pie>
                              <Tooltip
                                contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                                formatter={(v) => [v + '건', '입찰수']}
                              />
                            </PieChart>
                          </ResponsiveContainer>
                        ) : <div className="flex items-center justify-center h-40 text-sm text-slate-500">데이터 없음</div>}
                      </CardContent>
                    </Card>
                  </div>

                  {industryChartData.length > 0 && (
                    <Card className="bg-white border-slate-200 shadow-sm">
                      <CardHeader className="border-b border-slate-100 pb-3 flex flex-row items-center justify-between">
                        <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                          <BarChart3 className="h-4 w-4 text-amber-500" />공종별 낙찰률
                        </CardTitle>
                        <span className="text-xs text-slate-500">상위 15개 공종</span>
                      </CardHeader>
                      <CardContent className="pt-4">
                        <ResponsiveContainer width="100%" height={260}>
                          <BarChart data={industryChartData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                            <XAxis dataKey="name" tick={{ fontSize: 12, fill: '#475569' }} interval={0} angle={-25} textAnchor="end" height={54} />
                            <YAxis tick={{ fontSize: 12, fill: '#475569' }} unit="%" domain={['auto','auto']} />
                            <Tooltip
                              contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                              formatter={(v) => [`${v}%`, '낙찰률']}
                            />
                            <Bar dataKey="rate" fill="#10b981" radius={[3, 3, 0, 0]} opacity={0.85} />
                          </BarChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>
                  )}

                  {industries.length > 0 && (
                    <Card className="bg-white border-slate-200 shadow-sm">
                      <CardHeader className="border-b border-slate-100 pb-3 flex flex-row items-center justify-between">
                        <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                          <Database className="h-4 w-4 text-blue-500" />공종별 상세 통계
                        </CardTitle>
                        <span className="text-xs text-slate-500">{industries.length}개 공종</span>
                      </CardHeader>
                      <CardContent className="p-0">
                        <div className="overflow-hidden rounded-b-lg">
                          <Table>
                            <TableHeader className="bg-slate-50">
                              <TableRow>
                                <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide">공종명</TableHead>
                                <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide text-right">입찰 건수</TableHead>
                                <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide text-right">평균 낙찰률</TableHead>
                                <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide text-right">평균 경쟁사</TableHead>
                                <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide text-right">총 금액</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {industries.map((ind) => (
                                <TableRow key={ind.industry_id} className="hover:bg-slate-50/80 transition-colors">
                                  <TableCell className="truncate max-w-[200px] font-medium text-slate-700">{ind.industry_name}</TableCell>
                                  <TableCell className="text-right text-slate-600">{ind.bid_count.toLocaleString()}</TableCell>
                                  <TableCell className="text-right font-semibold text-blue-600">
                                    {ind.avg_rate ? (ind.avg_rate * 100).toFixed(2) + '%' : '-'}
                                  </TableCell>
                                  <TableCell className="text-right text-slate-500">
                                    {ind.avg_competitor_count ? ind.avg_competitor_count.toFixed(1) : '-'}
                                  </TableCell>
                                  <TableCell className="text-right text-slate-500 text-xs">{fmtAmt(ind.total_amount)}</TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </div>
                      </CardContent>
                    </Card>
                  )}
                </>
              )}
            </div>
          </TabsContent>

          {/* ── Level 2: 클러스터 탭 ── */}
          <TabsContent value="level2" className="mt-0">
            <div className="p-6 max-w-[1440px] mx-auto w-full space-y-5">
              <div className="flex items-center gap-2 px-4 py-2.5 bg-blue-50 border border-blue-200 rounded-lg">
                <GitBranch className="h-4 w-4 text-blue-600 shrink-0" />
                <span className="text-sm text-blue-700">{selectedLabel} 기준 K-Means 클러스터링 분석</span>
              </div>

              {clusterLoading ? (
                <Card className="bg-white border-slate-200 shadow-sm">
                  <CardContent className="py-16 text-center">
                    <div className="flex flex-col items-center gap-3 text-slate-500">
                      <GitBranch className="h-8 w-8 animate-pulse" />
                      <p className="text-sm">클러스터 분석 중...</p>
                    </div>
                  </CardContent>
                </Card>
              ) : clusterError ? (
                <Card className="bg-white border-slate-200 shadow-sm">
                  <CardContent className="py-10 text-center text-red-500 text-sm">분석 중 오류 발생</CardContent>
                </Card>
              ) : !cluster || cluster.error ? (
                <Card className="bg-white border-slate-200 shadow-sm">
                  <CardContent className="py-10 text-center text-slate-500 text-sm">{cluster?.error ?? '분석 데이터 부족'}</CardContent>
                </Card>
              ) : (
                <>
                  <div className="flex items-center gap-3 px-4 py-3 bg-slate-50 border border-slate-200 rounded-lg">
                    <div className="flex items-center gap-1.5 text-sm text-slate-700">
                      <span className="font-semibold text-slate-900">{cluster.total_count.toLocaleString()}건</span>
                      <span className="text-slate-500">분석 →</span>
                      <span className="font-semibold text-blue-600">{cluster.clusters.length}개</span>
                      <span>클러스터로 분류됨</span>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {cluster.clusters.map((c, i) => (
                      <Card key={c.cluster_id} className="bg-white border-slate-200 shadow-sm overflow-hidden">
                        <div className="h-1" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                        <CardContent className="p-5">
                          <div className="flex items-center gap-2 mb-4">
                            <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                            <h3 className="text-sm font-semibold text-slate-800">클러스터 {c.cluster_id + 1}</h3>
                            <Badge variant="secondary" className="ml-auto text-xs bg-slate-100 text-slate-600">
                              {c.count.toLocaleString()}건
                            </Badge>
                          </div>
                          <div className="grid grid-cols-2 gap-2">
                            {[
                              { label: '평균 금액', value: fmtAmt(c.avg_amount), highlight: false },
                              { label: '평균 낙찰률', value: c.avg_rate ? (c.avg_rate * 100).toFixed(2) + '%' : '-', highlight: true },
                              { label: '평균 경쟁사', value: c.avg_comp.toFixed(1) + '개사', highlight: false },
                              { label: '주요 공종', value: c.top_industry, highlight: false, small: true },
                            ].map(({ label, value, highlight, small }) => (
                              <div key={label} className={cn(
                                'rounded-lg p-3',
                                highlight ? 'bg-blue-50 border border-blue-100' : 'bg-slate-50'
                              )}>
                                <div className="text-xs text-slate-500 mb-1">{label}</div>
                                <div className={cn(
                                  'font-semibold',
                                  small ? 'text-xs truncate' : 'text-sm',
                                  highlight && 'text-blue-600'
                                )}>{value}</div>
                              </div>
                            ))}
                          </div>
                          <p className="text-xs text-slate-500 mt-3">
                            금액 범위: {fmtAmt(c.amount_range[0])} ~ {fmtAmt(c.amount_range[1])}
                          </p>
                        </CardContent>
                      </Card>
                    ))}
                  </div>

                  {clusterChartData.length > 1 && (
                    <Card className="bg-white border-slate-200 shadow-sm">
                      <CardHeader className="border-b border-slate-100 pb-3 flex flex-row items-center justify-between">
                        <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                          <Activity className="h-4 w-4 text-blue-500" />클러스터별 금액 vs 낙찰률
                        </CardTitle>
                        <span className="text-xs text-slate-500">산점도</span>
                      </CardHeader>
                      <CardContent className="pt-4">
                        <ResponsiveContainer width="100%" height={240}>
                          <ScatterChart>
                            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                            <XAxis dataKey="avg_amount" name="평균금액" tickFormatter={(v) => fmtAmt(v)} tick={{ fontSize: 12, fill: '#475569' }} type="number" />
                            <YAxis dataKey="avg_rate" name="낙찰률" tickFormatter={(v) => typeof v === 'number' ? (v*100).toFixed(1) : '0'} unit="%" tick={{ fontSize: 12, fill: '#475569' }} type="number" />
                            <Tooltip
                              contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                              cursor={{ strokeDasharray: '3 3' }}
                              formatter={(v: unknown, name: string) => { const n = Number(v); return name === '낙찰률' ? [(n * 100).toFixed(2) + '%', name] : [fmtAmt(n), name] }}
                            />
                            <Legend />
                            {clusterChartData.map((c, i) => (
                              <Scatter key={c.cluster_id} name={`클러스터 ${c.cluster_id + 1}`}
                                data={[{ avg_amount: c.avg_amount, avg_rate: c.avg_rate }]} fill={COLORS[i % COLORS.length]} />
                            ))}
                          </ScatterChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>
                  )}
                </>
              )}
            </div>
          </TabsContent>

          {/* ── Level 3: ML 모델 탭 ── */}
          <TabsContent value="level3" className="mt-0">
            <div className="p-6 max-w-[1440px] mx-auto w-full space-y-5">
              {mlLoading ? <Skeleton className="h-64 w-full rounded-xl" /> : !modelInfo ? (
                <div className="flex flex-col items-center justify-center py-20 text-slate-500">
                  <Cpu className="h-10 w-10 mb-3 opacity-30" />
                  <p className="text-sm">모델 정보가 없습니다</p>
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {/* 모델 정보 카드 */}
                    <Card className="bg-white border-slate-200 shadow-sm">
                      <CardHeader className="border-b border-slate-100 pb-3">
                        <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                          <Cpu className="h-4 w-4 text-blue-500" />모델 정보
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="pt-4 space-y-3">
                        {[
                          { label: '버전', value: modelInfo.model.version, mono: true },
                          { label: '알고리즘', value: modelInfo.model.version.includes('rule') ? '규칙 기반' : 'XGBoost + LightGBM', mono: false },
                          { label: '학습 건수', value: (modelInfo.model.train_size || 0).toLocaleString() + '건', mono: false },
                          { label: '낙찰 데이터', value: (modelInfo.model.winner_size || 0).toLocaleString() + '건', mono: false },
                        ].map(({ label, value, mono }) => (
                          <div key={label} className="flex justify-between items-center">
                            <span className="text-xs text-slate-500">{label}</span>
                            <span className={cn('text-sm font-medium text-slate-800', mono && 'font-mono bg-slate-100 px-2 py-0.5 rounded')}>{value}</span>
                          </div>
                        ))}
                      </CardContent>
                    </Card>

                    {/* 데이터 준비 상태 */}
                    <Card className="bg-white border-slate-200 shadow-sm">
                      <CardHeader className="border-b border-slate-100 pb-3">
                        <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                          <Database className="h-4 w-4 text-emerald-500" />데이터 준비 상태
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="pt-4 space-y-4">
                        <div>
                          <div className="flex justify-between text-xs mb-1.5">
                            <span className="text-slate-500">전체 결과</span>
                            <span className="font-medium text-slate-700">{modelInfo.data_availability.total_results.toLocaleString()}건</span>
                          </div>
                          <div className="w-full bg-slate-100 rounded-full h-1.5">
                            <div className="bg-blue-500 h-1.5 rounded-full transition-all" style={{ width: `${Math.min(100, modelInfo.data_availability.total_results / 5)}%` }} />
                          </div>
                        </div>
                        <div>
                          <div className="flex justify-between text-xs mb-1.5">
                            <span className="text-slate-500">낙찰 결과</span>
                            <span className="font-medium text-slate-700">{modelInfo.data_availability.winner_results.toLocaleString()}건</span>
                          </div>
                          <div className="w-full bg-slate-100 rounded-full h-1.5">
                            <div
                              className={cn('h-1.5 rounded-full transition-all', modelInfo.data_availability.ready_for_ml ? 'bg-emerald-500' : 'bg-amber-400')}
                              style={{ width: `${Math.min(100, modelInfo.data_availability.winner_results / 20 * 100)}%` }}
                            />
                          </div>
                          <p className="text-xs text-slate-500 mt-1">ML 기준: 20건 ({modelInfo.data_availability.winner_results}/20)</p>
                        </div>
                        <div className={cn(
                          'flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium',
                          modelInfo.data_availability.ready_for_ml
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : 'bg-amber-50 text-amber-700 border border-amber-200'
                        )}>
                          <div className={cn('w-1.5 h-1.5 rounded-full', modelInfo.data_availability.ready_for_ml ? 'bg-emerald-500' : 'bg-amber-500')} />
                          {modelInfo.data_availability.ready_for_ml ? 'ML 모델 사용 가능' : '규칙 기반 추천 중'}
                        </div>
                      </CardContent>
                    </Card>

                    {/* 사용 현황 */}
                    <Card className="bg-white border-slate-200 shadow-sm">
                      <CardHeader className="border-b border-slate-100 pb-3">
                        <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                          <Award className="h-4 w-4 text-violet-500" />사용 현황
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="pt-4 space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-slate-500">30일 추천 요청</span>
                          <span className="text-2xl font-bold text-blue-600 tabular-nums">{modelInfo.usage.predictions_30d}</span>
                        </div>
                        {modelInfo.period_data && (
                          <div className="border-t border-slate-100 pt-3 space-y-2">
                            <p className="text-xs text-slate-500">{selectedLabel} 집계</p>
                            <div className="flex justify-between text-xs">
                              <span className="text-slate-500">기간 내 입찰결과</span>
                              <span className="font-semibold text-slate-700">{modelInfo.period_data.results.toLocaleString()}건</span>
                            </div>
                            <div className="flex justify-between text-xs">
                              <span className="text-slate-500">기간 내 낙찰결과</span>
                              <span className="font-semibold text-slate-700">{modelInfo.period_data.winners.toLocaleString()}건</span>
                            </div>
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  </div>

                  {/* ML 파이프라인 */}
                  <Card className="bg-white border-slate-200 shadow-sm">
                    <CardHeader className="border-b border-slate-100 pb-3">
                      <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                        <Cpu className="h-4 w-4 text-blue-500" />ML 파이프라인
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="pt-4">
                      <div className="flex items-stretch gap-2 flex-wrap">
                        {[
                          { step: '1', title: '나라장터 수집', desc: 'G2B API', color: 'bg-blue-50 border-blue-200', badge: 'text-blue-700 bg-blue-100', dot: 'bg-blue-500' },
                          { step: '2', title: '피처 엔지니어링', desc: '기관·지역·공종 통계', color: 'bg-purple-50 border-purple-200', badge: 'text-purple-700 bg-purple-100', dot: 'bg-purple-500' },
                          { step: '3', title: 'XGBoost 분위수', desc: '투찰률 범위 예측', color: 'bg-emerald-50 border-emerald-200', badge: 'text-emerald-700 bg-emerald-100', dot: 'bg-emerald-500' },
                          { step: '4', title: 'LightGBM', desc: '낙찰 확률 예측', color: 'bg-amber-50 border-amber-200', badge: 'text-amber-700 bg-amber-100', dot: 'bg-amber-500' },
                          { step: '5', title: 'SHAP 설명', desc: '의사결정 근거 제시', color: 'bg-red-50 border-red-200', badge: 'text-red-700 bg-red-100', dot: 'bg-red-500' },
                        ].map(({ step, title, desc, color, badge, dot }) => (
                          <div key={step} className={cn('border rounded-xl p-4 flex-1 min-w-[140px]', color)}>
                            <div className="flex items-center gap-1.5 mb-2">
                              <div className={cn('w-1.5 h-1.5 rounded-full', dot)} />
                              <span className={cn('text-xs font-bold px-1.5 py-0.5 rounded', badge)}>STEP {step}</span>
                            </div>
                            <div className="font-semibold text-slate-800 text-sm">{title}</div>
                            <div className="text-xs text-slate-500 mt-0.5">{desc}</div>
                          </div>
                        ))}
                      </div>
                      <p className="text-xs text-slate-500 mt-4 flex items-start gap-1.5">
                        <span className="text-slate-300 mt-0.5">*</span>
                        상용 AI 없이 로컬 ML 모델만 사용. 낙찰결과 20건 이상 시 ML 모드 자동 전환.
                      </p>
                    </CardContent>
                  </Card>
                </>
              )}
            </div>
          </TabsContent>

          {/* ── 사정율 분포 탭 ── */}
          <TabsContent value="srate" className="mt-0">
            <div className="p-6 max-w-[1440px] mx-auto w-full space-y-5">
              {/* 필터 바 */}
              <div className="flex flex-wrap items-center gap-2 p-3 bg-slate-50 rounded-lg border border-slate-200">
                <SlidersHorizontal className="h-4 w-4 text-slate-500 shrink-0" />
                <Select value={srateAgencyId != null ? String(srateAgencyId) : 'all'} onValueChange={(v) => setSrateAgencyId(v === 'all' ? null : Number(v))}>
                  <SelectTrigger className="w-48 h-8 text-xs bg-white border-slate-200">
                    <SelectValue placeholder="발주기관 전체" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">발주기관 전체</SelectItem>
                    {(meta?.agencies ?? []).slice(0, 100).map((a) => <SelectItem key={a.id} value={String(a.id)}>{a.name}</SelectItem>)}
                  </SelectContent>
                </Select>
                <Select value={srateIndustryId != null ? String(srateIndustryId) : 'all'} onValueChange={(v) => setSrateIndustryId(v === 'all' ? null : Number(v))}>
                  <SelectTrigger className="w-40 h-8 text-xs bg-white border-slate-200">
                    <SelectValue placeholder="공종 전체" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">공종 전체</SelectItem>
                    {(meta?.industries ?? []).map((i) => <SelectItem key={i.id} value={String(i.id)}>{i.name}</SelectItem>)}
                  </SelectContent>
                </Select>
                <div className="ml-auto flex items-center rounded-lg border border-slate-200 overflow-hidden bg-white">
                  {(['count', 'ratio'] as const).map((m) => (
                    <button key={m} onClick={() => setSrateViewMode(m)}
                      className={cn('px-3 py-1.5 text-sm font-medium transition-colors',
                        srateViewMode === m ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-50'
                      )}>
                      {m === 'count' ? '빈도수' : '비율(%)'}
                    </button>
                  ))}
                </div>
              </div>

              {srateDist && (() => {
                const totalCount = (srateDist.bins ?? []).reduce((s: number, b: { count: number }) => s + b.count, 0)
                const binsWithCumul = (() => {
                  let cum = 0
                  return (srateDist.bins ?? []).map((b: { rate_pct: number; count: number }) => {
                    cum += b.count
                    return {
                      ...b,
                      display: srateViewMode === 'ratio' ? +((b.count / (totalCount || 1)) * 100).toFixed(2) : b.count,
                      cumul: +(cum / (totalCount || 1) * 100).toFixed(1),
                      label: (b.rate_pct * 100).toFixed(3) + '%',
                    }
                  })
                })()
                return (
                  <>
                    {/* 사정율 KPI 카드 */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      {[
                        { label: '평균 사정율', value: srateDist.mean != null ? (srateDist.mean * 100).toFixed(3) + '%' : '-', color: 'blue' },
                        { label: '최빈 사정율', value: srateDist.mode != null ? (srateDist.mode * 100).toFixed(3) + '%' : '-', color: 'emerald' },
                        { label: '표준편차', value: srateDist.std != null ? (srateDist.std * 100).toFixed(3) + '%' : '-', color: 'amber' },
                        { label: '표본 수', value: (srateDist.sample_count ?? 0).toLocaleString() + '건', color: 'violet' },
                      ].map(({ label, value, color }) => (
                        <Card key={label} className="relative overflow-hidden bg-white border-slate-200 shadow-sm">
                          <div className={cn('absolute top-0 left-0 right-0 h-0.5',
                            color === 'blue' ? 'bg-blue-500' :
                            color === 'emerald' ? 'bg-emerald-500' :
                            color === 'amber' ? 'bg-amber-500' : 'bg-violet-500'
                          )} />
                          <CardContent className="p-5">
                            <p className="text-sm font-medium text-slate-500">{label}</p>
                            <p className="text-2xl font-bold mt-1 tabular-nums font-mono text-slate-900">{value}</p>
                          </CardContent>
                        </Card>
                      ))}
                    </div>

                    {/* 사정율 분포 차트 */}
                    <Card className="bg-white border-slate-200 shadow-sm">
                      <CardHeader className="border-b border-slate-100 pb-3">
                        <div className="flex items-center justify-between">
                          <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                            <Activity className="h-4 w-4 text-blue-500" />사정율 분포
                            <span className="text-xs font-normal text-slate-500">(소수점 3자리 · 누적 포함)</span>
                          </CardTitle>
                          <span className="text-xs text-slate-500">
                            P25: {srateDist.p25 != null ? (srateDist.p25*100).toFixed(3)+'%' : '-'}
                            {' · '}P75: {srateDist.p75 != null ? (srateDist.p75*100).toFixed(3)+'%' : '-'}
                          </span>
                        </div>
                      </CardHeader>
                      <CardContent className="pt-4">
                        {binsWithCumul.length === 0 ? (
                          <div className="flex flex-col items-center justify-center py-16 text-slate-500">
                            <SlidersHorizontal className="h-8 w-8 mb-3 opacity-30" />
                            <p className="text-sm">데이터가 없습니다.</p>
                          </div>
                        ) : (
                          <ResponsiveContainer width="100%" height={320}>
                            <ComposedChart data={binsWithCumul} margin={{ left: -10, right: 40 }}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                              <XAxis dataKey="label" tick={{ fontSize: 12, fill: '#475569' }} interval={Math.floor(binsWithCumul.length / 10)} angle={-30} textAnchor="end" height={40} />
                              <YAxis yAxisId="left" tick={{ fontSize: 12, fill: '#475569' }} label={{ value: srateViewMode === 'ratio' ? '%' : '건', position: 'insideTopLeft', fontSize: 12, fill: '#475569' }} />
                              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 12, fill: '#475569' }} unit="%" domain={[0, 100]} />
                              <Tooltip
                                contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                                formatter={(v: number, name: string) => [
                                  name === '누적' ? v + '%' : srateViewMode === 'ratio' ? v + '%' : v + '건',
                                  name,
                                ]}
                              />
                              <Bar yAxisId="left" dataKey="display" name={srateViewMode === 'ratio' ? '비율' : '빈도수'} fill="#2563eb" fillOpacity={0.65} radius={[2, 2, 0, 0]} />
                              <Line yAxisId="right" type="monotone" dataKey="cumul" name="누적" stroke="#ef4444" dot={false} strokeWidth={2} />
                              {srateDist.mode != null && (
                                <ReferenceLine yAxisId="left" x={(srateDist.mode * 100).toFixed(3) + '%'} stroke="#ef4444" strokeDasharray="4 2"
                                  label={{ value: '최빈', position: 'top', fontSize: 10, fill: '#ef4444' }} />
                              )}
                            </ComposedChart>
                          </ResponsiveContainer>
                        )}
                      </CardContent>
                    </Card>
                  </>
                )
              })()}
              {!srateDist && (
                <div className="flex flex-col items-center justify-center py-20 text-slate-500">
                  <SlidersHorizontal className="h-10 w-10 mb-3 opacity-30" />
                  <p className="text-sm">탭을 선택하면 데이터를 불러옵니다.</p>
                </div>
              )}
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}
