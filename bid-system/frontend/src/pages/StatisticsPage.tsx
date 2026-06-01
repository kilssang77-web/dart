import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
  LineChart, Line, PieChart, Pie, Cell, ScatterChart, Scatter, Legend
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

const COLORS = ['#2563eb','#16a34a','#d97706','#dc2626','#7c3aed','#0891b2','#be185d','#65a30d']
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

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">통계 분석</h1>
          <p className="text-muted-foreground text-sm mt-1">{selectedLabel} 기준</p>
        </div>
        <div className="flex items-center gap-1">
          {PERIOD_OPTIONS.map((m) => (
            <Button key={m} variant={months === m ? 'default' : 'outline'} size="sm"
              onClick={() => setMonths(m)} className="h-8 px-3 text-xs">{m}개월</Button>
          ))}
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="h-auto p-1">
          <TabsTrigger value="overview">개요</TabsTrigger>
          <TabsTrigger value="level1">Level 1</TabsTrigger>
          <TabsTrigger value="level2">Level 2 · 클러스터</TabsTrigger>
          <TabsTrigger value="level3">Level 3 · ML</TabsTrigger>
          <TabsTrigger value="srate">사정율 분포</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4 mt-4">
          {(ovLoading || agLoading) ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {Array.from({length: 4}).map((_, i) => <Skeleton key={i} className="h-24 w-full" />)}
            </div>
          ) : overview ? (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  { label: `총 입찰 (${selectedLabel})`, value: overview.total_bids.toLocaleString() + '건' },
                  { label: '전체 경쟁사 수', value: overview.total_competitors.toLocaleString() + '개사' },
                  { label: '평균 낙찰률', value: overview.avg_win_rate ? (overview.avg_win_rate * 100).toFixed(2) + '%' : '-' },
                  { label: '평균 경쟁사', value: (overview.avg_competitor_count ?? 0).toFixed(1) + '개사' },
                ].map(({ label, value }) => (
                  <Card key={label}><CardContent className="pt-4 pb-4">
                    <div className="text-xs text-muted-foreground mb-1">{label}</div>
                    <div className="text-xl font-bold">{value}</div>
                  </CardContent></Card>
                ))}
              </div>
              {trendData.length > 0 && (
                <Card>
                  <CardHeader className="pb-2"><CardTitle className="text-sm">월별 입찰 추이</CardTitle></CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={200}>
                      <LineChart data={trendData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                        <XAxis dataKey="label" tick={{ fontSize: 10 }} interval={1} />
                        <YAxis yAxisId="l" tick={{ fontSize: 11 }} />
                        <YAxis yAxisId="r" orientation="right" tick={{ fontSize: 11 }} unit="%" />
                        <Tooltip />
                        <Line yAxisId="l" type="monotone" dataKey="입찰수" stroke="hsl(var(--muted-foreground))" strokeWidth={1.5} dot={false} />
                        <Line yAxisId="r" type="monotone" dataKey="낙찰율" stroke="hsl(var(--primary))" strokeWidth={2} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              )}
              <div className="grid grid-cols-2 gap-4">
                {agencies.length > 0 && (
                  <Card>
                    <CardHeader className="pb-2"><CardTitle className="text-sm">기관별 낙찰률 TOP 10</CardTitle></CardHeader>
                    <CardContent className="p-0">
                      <div className="overflow-auto max-h-64">
                        <Table>
                          <TableHeader><TableRow>
                            <TableHead className="text-xs">기관</TableHead>
                            <TableHead className="text-right text-xs">건수</TableHead>
                            <TableHead className="text-right text-xs">낙찰률</TableHead>
                            <TableHead className="text-right text-xs">경쟁</TableHead>
                          </TableRow></TableHeader>
                          <TableBody>
                            {(agencies as AgencyStatItem[]).slice(0, 10).map((a) => (
                              <TableRow key={a.agency_id}>
                                <TableCell className="py-1.5 text-xs truncate max-w-[140px]">{a.agency_name}</TableCell>
                                <TableCell className="py-1.5 text-right text-xs">{a.bid_count}</TableCell>
                                <TableCell className="py-1.5 text-right text-xs font-medium text-primary">
                                  {a.avg_rate ? (a.avg_rate * 100).toFixed(2) + '%' : '-'}
                                </TableCell>
                                <TableCell className="py-1.5 text-right text-xs text-muted-foreground">
                                  {a.avg_competitor_count ? a.avg_competitor_count.toFixed(1) : '-'}
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                    </CardContent>
                  </Card>
                )}
                {rateDist.length > 0 && (
                  <Card>
                    <CardHeader className="pb-2"><CardTitle className="text-sm">낙찰률 분포</CardTitle></CardHeader>
                    <CardContent>
                      <ResponsiveContainer width="100%" height={220}>
                        <BarChart data={(rateDist as RateDistItem[]).filter((d) => d.rate_pct >= 80 && d.rate_pct <= 100)}>
                          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                          <XAxis dataKey="rate_pct" tick={{ fontSize: 9 }} unit="%" interval={4} />
                          <YAxis tick={{ fontSize: 11 }} />
                          <Tooltip formatter={(v) => [v, '건수']} labelFormatter={(l) => `${l}%`} />
                          <Bar dataKey="count" fill="hsl(var(--primary))" radius={[2,2,0,0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </CardContent>
                  </Card>
                )}
              </div>
              {heatmapRows.some((r) => industries_list.some((ind) => r[ind] !== null)) && (
                <Card>
                  <CardHeader className="pb-2"><CardTitle className="text-sm">월별 × 공종별 낙찰률 히트맵</CardTitle></CardHeader>
                  <CardContent>
                    <div className="overflow-x-auto">
                      <table className="text-xs w-full">
                        <thead><tr>
                          <th className="text-left px-2 py-1 text-muted-foreground">월</th>
                          {industries_list.map((ind) => (
                            <th key={ind} className="text-center px-1 py-1 text-muted-foreground truncate max-w-[80px]">{ind.slice(0,8)}</th>
                          ))}
                        </tr></thead>
                        <tbody>
                          {heatmapRows.map((row) => (
                            <tr key={row.month as number}>
                              <td className="px-2 py-1 text-muted-foreground">{row.month}월</td>
                              {industries_list.map((ind) => {
                                const v = row[ind] as number | null
                                const heat = v ? Math.min(1, Math.max(0, (v - 85) / 10)) : 0
                                return (
                                  <td key={ind} className="px-1 py-1 text-center rounded"
                                    style={{ backgroundColor: v ? `rgba(37,99,235,${heat * 0.6 + 0.1})` : 'hsl(var(--muted))',
                                             color: heat > 0.5 ? 'white' : 'hsl(var(--foreground))' }}>
                                    {v ? `${v}%` : '-'}
                                  </td>
                                )
                              })}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                </Card>
              )}
            </>
          ) : <div className="text-center text-muted-foreground py-12">데이터 없음</div>}
        </TabsContent>

        <TabsContent value="level1" className="space-y-4 mt-4">
          {(rgLoading || indLoading) ? <Skeleton className="h-64 w-full" /> : (
            <>
              <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-2 text-sm text-blue-700">{selectedLabel} 기준 데이터입니다.</div>
              <div className="grid grid-cols-2 gap-4">
                <Card>
                  <CardHeader className="pb-2"><CardTitle className="text-sm">지역별 평균 낙찰률</CardTitle></CardHeader>
                  <CardContent>
                    {regionChartData.length > 0 ? (
                      <ResponsiveContainer width="100%" height={280}>
                        <BarChart data={regionChartData} layout="vertical">
                          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                          <XAxis type="number" tick={{ fontSize: 10 }} unit="%" domain={['auto','auto']} />
                          <YAxis type="category" dataKey="name" width={80} tick={{ fontSize: 10 }} />
                          <Tooltip formatter={(v) => [`${v}%`, '낙찰률']} />
                          <Bar dataKey="rate" fill="hsl(var(--primary))" radius={[0,2,2,0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    ) : <div className="text-sm text-muted-foreground py-8 text-center">데이터 없음</div>}
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="pb-2"><CardTitle className="text-sm">지역별 입찰 비중</CardTitle></CardHeader>
                  <CardContent>
                    {regions.length > 0 ? (
                      <ResponsiveContainer width="100%" height={280}>
                        <PieChart>
                          <Pie data={regions.slice(0,8)} dataKey="bid_count" nameKey="region_name" cx="50%" cy="50%" outerRadius={100}
                            label={({name, percent}) => percent > 0.05 ? `${name} ${(percent*100).toFixed(0)}%` : ''}>
                            {regions.slice(0,8).map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                          </Pie>
                          <Tooltip formatter={(v) => [v + '건', '입찰수']} />
                        </PieChart>
                      </ResponsiveContainer>
                    ) : <div className="text-sm text-muted-foreground py-8 text-center">데이터 없음</div>}
                  </CardContent>
                </Card>
              </div>
              {industryChartData.length > 0 && (
                <Card>
                  <CardHeader className="pb-2"><CardTitle className="text-sm">공종별 낙찰률</CardTitle></CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={240}>
                      <BarChart data={industryChartData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                        <XAxis dataKey="name" tick={{ fontSize: 9 }} interval={0} angle={-25} textAnchor="end" height={50} />
                        <YAxis tick={{ fontSize: 11 }} unit="%" domain={['auto','auto']} />
                        <Tooltip formatter={(v) => [`${v}%`, '낙찰률']} />
                        <Bar dataKey="rate" fill="#16a34a" radius={[2,2,0,0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              )}
              {industries.length > 0 && (
                <Card>
                  <CardHeader className="pb-2"><CardTitle className="text-sm">공종별 상세 통계</CardTitle></CardHeader>
                  <CardContent className="p-0">
                    <Table>
                      <TableHeader><TableRow>
                        <TableHead>공종명</TableHead><TableHead>입찰 건수</TableHead>
                        <TableHead>평균 낙찰률</TableHead><TableHead>평균 경쟁사 수</TableHead><TableHead>총 금액</TableHead>
                      </TableRow></TableHeader>
                      <TableBody>
                        {industries.map((ind) => (
                          <TableRow key={ind.industry_id}>
                            <TableCell className="truncate max-w-[200px]">{ind.industry_name}</TableCell>
                            <TableCell>{ind.bid_count.toLocaleString()}</TableCell>
                            <TableCell className="font-medium text-primary">{ind.avg_rate ? (ind.avg_rate * 100).toFixed(2) + '%' : '-'}</TableCell>
                            <TableCell className="text-muted-foreground">{ind.avg_competitor_count ? ind.avg_competitor_count.toFixed(1) : '-'}</TableCell>
                            <TableCell className="text-muted-foreground text-xs">{fmtAmt(ind.total_amount)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </TabsContent>

        <TabsContent value="level2" className="space-y-4 mt-4">
          <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-2 text-sm text-blue-700">
            {selectedLabel} 기준 K-Means 클러스터링
          </div>
          {clusterLoading ? (
            <Card><CardContent className="py-12 text-center text-muted-foreground">클러스터 분석 중...</CardContent></Card>
          ) : clusterError ? (
            <Card><CardContent className="py-8 text-center text-destructive">분석 중 오류 발생</CardContent></Card>
          ) : !cluster || cluster.error ? (
            <Card><CardContent className="py-8 text-center text-muted-foreground">{cluster?.error ?? '분석 데이터 부족'}</CardContent></Card>
          ) : (
            <>
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-700">
                총 <strong>{cluster.total_count.toLocaleString()}</strong>건 →
                <strong> {cluster.clusters.length}개</strong> 클러스터 분류
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {cluster.clusters.map((c, i) => (
                  <Card key={c.cluster_id}><CardContent className="pt-5">
                    <div className="flex items-center gap-2 mb-3">
                      <div className="w-3 h-3 rounded-full" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                      <h3 className="text-sm font-semibold">클러스터 {c.cluster_id + 1}</h3>
                      <Badge variant="secondary" className="ml-auto">{c.count.toLocaleString()}건</Badge>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div className="bg-muted/50 rounded p-2"><div className="text-xs text-muted-foreground">평균 금액</div><div className="font-semibold text-sm">{fmtAmt(c.avg_amount)}</div></div>
                      <div className="bg-muted/50 rounded p-2"><div className="text-xs text-muted-foreground">평균 낙찰률</div><div className="font-semibold text-sm text-primary">{c.avg_rate ? (c.avg_rate * 100).toFixed(2) + '%' : '-'}</div></div>
                      <div className="bg-muted/50 rounded p-2"><div className="text-xs text-muted-foreground">평균 경쟁사</div><div className="font-semibold text-sm">{c.avg_comp.toFixed(1)}개사</div></div>
                      <div className="bg-muted/50 rounded p-2"><div className="text-xs text-muted-foreground">주요 공종</div><div className="font-semibold text-xs truncate">{c.top_industry}</div></div>
                    </div>
                    <div className="mt-2 text-xs text-muted-foreground">금액 범위: {fmtAmt(c.amount_range[0])} ~ {fmtAmt(c.amount_range[1])}</div>
                  </CardContent></Card>
                ))}
              </div>
              {clusterChartData.length > 1 && (
                <Card>
                  <CardHeader className="pb-2"><CardTitle className="text-sm">클러스터별 금액 vs 낙찰률</CardTitle></CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={220}>
                      <ScatterChart>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                        <XAxis dataKey="avg_amount" name="평균금액" tickFormatter={(v) => fmtAmt(v)} tick={{ fontSize: 10 }} type="number" />
                        <YAxis dataKey="avg_rate" name="낙찰률" tickFormatter={(v) => typeof v === 'number' ? (v*100).toFixed(1) : '0'} unit="%" tick={{ fontSize: 10 }} type="number" />
                        <Tooltip cursor={{ strokeDasharray: '3 3' }}
                          formatter={(v: unknown, name: string) => { const n = Number(v); return name === '낙찰률' ? [(n * 100).toFixed(2) + '%', name] : [fmtAmt(n), name] }} />
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
        </TabsContent>

        <TabsContent value="level3" className="space-y-4 mt-4">
          {mlLoading ? <Skeleton className="h-64 w-full" /> : !modelInfo ? (
            <div className="text-center text-muted-foreground py-12">데이터 없음</div>
          ) : (
            <>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Card>
                  <CardHeader className="pb-2"><CardTitle className="text-sm">모델 정보</CardTitle></CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    <div className="flex justify-between"><span className="text-muted-foreground">버전</span><span className="font-mono text-xs">{modelInfo.model.version}</span></div>
                    <div className="flex justify-between"><span className="text-muted-foreground">알고리즘</span><span>{modelInfo.model.version.includes('rule') ? '규칙 기반' : 'XGBoost + LightGBM'}</span></div>
                    <div className="flex justify-between"><span className="text-muted-foreground">학습 건수</span><span>{(modelInfo.model.train_size || 0).toLocaleString()}건</span></div>
                    <div className="flex justify-between"><span className="text-muted-foreground">낙찰 데이터</span><span>{(modelInfo.model.winner_size || 0).toLocaleString()}건</span></div>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="pb-2"><CardTitle className="text-sm">데이터 준비 상태</CardTitle></CardHeader>
                  <CardContent className="space-y-3">
                    <div>
                      <div className="flex justify-between text-sm mb-1"><span className="text-muted-foreground">전체 결과</span><span>{modelInfo.data_availability.total_results.toLocaleString()}건</span></div>
                      <div className="w-full bg-muted rounded-full h-2"><div className="bg-primary h-2 rounded-full" style={{ width: `${Math.min(100, modelInfo.data_availability.total_results / 5)}%` }} /></div>
                    </div>
                    <div>
                      <div className="flex justify-between text-sm mb-1"><span className="text-muted-foreground">낙찰 결과</span><span>{modelInfo.data_availability.winner_results.toLocaleString()}건</span></div>
                      <div className="w-full bg-muted rounded-full h-2">
                        <div className={cn('h-2 rounded-full', modelInfo.data_availability.ready_for_ml ? 'bg-green-500' : 'bg-orange-400')}
                          style={{ width: `${Math.min(100, modelInfo.data_availability.winner_results / 20 * 100)}%` }} />
                      </div>
                      <div className="text-xs text-muted-foreground mt-0.5">ML 기준: 20건 ({modelInfo.data_availability.winner_results}/20)</div>
                    </div>
                    <Badge variant={modelInfo.data_availability.ready_for_ml ? 'success' : 'warning'} className="text-sm px-3 py-1">
                      {modelInfo.data_availability.ready_for_ml ? 'ML 모델 사용 가능' : '규칙 기반 추천 중'}
                    </Badge>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="pb-2"><CardTitle className="text-sm">사용 현황</CardTitle></CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    <div className="flex justify-between items-center"><span className="text-muted-foreground">30일 추천 요청</span><span className="text-2xl font-bold text-primary">{modelInfo.usage.predictions_30d}</span></div>
                    {modelInfo.period_data && (
                      <div className="border-t pt-2 mt-1 space-y-1">
                        <div className="text-xs text-muted-foreground">{selectedLabel} 집계</div>
                        <div className="flex justify-between"><span className="text-muted-foreground">기간 내 입찰결과</span><span className="font-semibold">{modelInfo.period_data.results.toLocaleString()}건</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">기간 내 낙찰결과</span><span className="font-semibold">{modelInfo.period_data.winners.toLocaleString()}건</span></div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>
              <Card>
                <CardHeader className="pb-2"><CardTitle className="text-sm">ML 파이프라인</CardTitle></CardHeader>
                <CardContent>
                  <div className="flex items-start gap-3 flex-wrap text-sm">
                    {[
                      { step: '1', title: '나라장터 수집', desc: 'G2B API', color: 'bg-blue-50 border-blue-200 text-blue-700' },
                      { step: '2', title: '피처 엔지니어링', desc: '기관·지역·공종 통계', color: 'bg-purple-50 border-purple-200 text-purple-700' },
                      { step: '3', title: 'XGBoost 분위수', desc: '투찰률 범위 예측', color: 'bg-green-50 border-green-200 text-green-700' },
                      { step: '4', title: 'LightGBM', desc: '낙찰 확률 예측', color: 'bg-orange-50 border-orange-200 text-orange-700' },
                      { step: '5', title: 'SHAP 설명', desc: '의사결정 근거 제시', color: 'bg-red-50 border-red-200 text-red-700' },
                    ].map(({ step, title, desc, color }) => (
                      <div key={step} className={cn('border rounded-lg p-3 flex-1 min-w-[140px]', color)}>
                        <div className="text-xs font-bold mb-1">STEP {step}</div>
                        <div className="font-semibold">{title}</div>
                        <div className="text-xs opacity-75 mt-0.5">{desc}</div>
                      </div>
                    ))}
                  </div>
                  <p className="text-xs text-muted-foreground mt-3">* 상용 AI 없이 로컬 ML 모델만 사용. 낙찰결과 20건 이상 시 ML 모드 자동 전환.</p>
                </CardContent>
              </Card>
            </>
          )}
        </TabsContent>
        <TabsContent value="srate" className="space-y-4 mt-4">
          <div className="flex flex-wrap gap-2">
            <Select value={srateAgencyId != null ? String(srateAgencyId) : 'all'} onValueChange={(v) => setSrateAgencyId(v === 'all' ? null : Number(v))}>
              <SelectTrigger className="w-48"><SelectValue placeholder="발주기관 전체" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">발주기관 전체</SelectItem>
                {(meta?.agencies ?? []).slice(0, 100).map((a) => <SelectItem key={a.id} value={String(a.id)}>{a.name}</SelectItem>)}
              </SelectContent>
            </Select>
            <Select value={srateIndustryId != null ? String(srateIndustryId) : 'all'} onValueChange={(v) => setSrateIndustryId(v === 'all' ? null : Number(v))}>
              <SelectTrigger className="w-40"><SelectValue placeholder="공종 전체" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">공종 전체</SelectItem>
                {(meta?.industries ?? []).map((i) => <SelectItem key={i.id} value={String(i.id)}>{i.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          {srateDist && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  { label: '평균 사정율', value: srateDist.mean != null ? (srateDist.mean * 100).toFixed(3) + '%' : '-' },
                  { label: '최빈 사정율', value: srateDist.mode != null ? (srateDist.mode * 100).toFixed(3) + '%' : '-' },
                  { label: '표준편차',   value: srateDist.std  != null ? (srateDist.std  * 100).toFixed(3) + '%' : '-' },
                  { label: '표본 수',    value: srateDist.sample_count?.toLocaleString() + '건' },
                ].map(({ label, value }) => (
                  <Card key={label}><CardContent className="pt-4 pb-3">
                    <div className="text-xs text-muted-foreground mb-1">{label}</div>
                    <div className="text-xl font-bold">{value}</div>
                  </CardContent></Card>
                ))}
              </div>
              <Card>
                <CardHeader><CardTitle className="text-sm">사정율 빈도 분포 (히스토그램)</CardTitle></CardHeader>
                <CardContent>
                  {srateDist.bins?.length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-10">데이터가 없습니다.</p>
                  ) : (
                    <ResponsiveContainer width="100%" height={280}>
                      <BarChart data={srateDist.bins} margin={{ left: -10, right: 10 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                        <XAxis dataKey="rate_pct" tickFormatter={(v: number) => (v * 100).toFixed(1) + '%'} tick={{ fontSize: 10 }} interval={3} />
                        <YAxis tick={{ fontSize: 11 }} />
                        <Tooltip formatter={(v: unknown) => [String(v) + '건', '건수']} />
                        <Bar dataKey="count" fill="hsl(var(--primary)/0.7)" radius={[2, 2, 0, 0]} />
                        {srateDist.mode != null && (
                          <ReferenceLine x={srateDist.mode} stroke="hsl(var(--destructive))" strokeDasharray="4 2" label={{ value: '최빈', position: 'top', fontSize: 10, fill: 'hsl(var(--destructive))' }} />
                        )}
                        {srateDist.p25 != null && <ReferenceLine x={srateDist.p25} stroke="hsl(var(--primary)/0.4)" strokeDasharray="2 2" />}
                        {srateDist.p75 != null && <ReferenceLine x={srateDist.p75} stroke="hsl(var(--primary)/0.4)" strokeDasharray="2 2" />}
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </CardContent>
              </Card>
            </>
          )}
          {!srateDist && <p className="text-sm text-muted-foreground text-center py-10">탭을 선택하면 데이터를 불러옵니다.</p>}
        </TabsContent>
      </Tabs>
    </div>
  )
}