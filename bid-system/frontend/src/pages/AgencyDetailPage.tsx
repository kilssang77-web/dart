import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, Building2, BarChart3, FileText, Activity, GitBranch, TrendingUp, Users, Target, Layers, BarChart2 } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, ReferenceLine, ComposedChart, Area, Cell,
} from 'recharts'
import { bidsApi, recommendApi, statsApi, agenciesApi, executionsApi } from '@/api'
import type { MetaData, SrateHistogramResponse, AgencyRecentResultsResponse, AgencyYegaPattern, AgencyStrategy } from '@/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table'

const FLOOR_RATE = 0.87745
const TABS = ['개요', '공고목록', '심층분석', '예가패턴', '낙찰분포', '전략DB'] as const
type Tab = (typeof TABS)[number]

const TAB_ICONS = {
  '개요': Activity,
  '공고목록': FileText,
  '심층분석': BarChart3,
  '예가패턴': GitBranch,
  '낙찰분포': BarChart2,
  '전략DB': TrendingUp,
} as const

interface SrateStatItem {
  group_type: 'agency' | 'industry' | 'global'
  group_id: number
  sample_count: number
  srate_mean: number | null
  srate_std: number | null
  srate_p25: number | null
  srate_p50: number | null
  srate_p75: number | null
  srate_trend: number | null
}

interface AgencyStatItem {
  agency_id: number
  agency_name: string
  bid_count: number
  avg_rate: number | null
  avg_competitor_count: number | null
}

interface RateBucket { range: string; count: number }

function buildRateDist(bids: { winner_rate: number | null }[]): RateBucket[] {
  const step = 0.5
  const start = 87.0, end = 93.5
  const buckets: Record<string, number> = {}
  for (let r = start; r <= end; r += step) {
    buckets[r.toFixed(1)] = 0
  }
  for (const b of bids) {
    if (!b.winner_rate) continue
    const pct = b.winner_rate * 100
    const bucket = (Math.floor(pct / step) * step).toFixed(1)
    if (bucket in buckets) buckets[bucket]++
  }
  return Object.entries(buckets).map(([range, count]) => ({ range: range + '%', count }))
}

function computeLinearTrend(data: { rate: number }[]): number[] {
  const n = data.length
  if (n < 2) return data.map(d => d.rate)
  const xs = data.map((_, i) => i)
  const ys = data.map(d => d.rate)
  const mx = xs.reduce((s, x) => s + x, 0) / n
  const my = ys.reduce((s, y) => s + y, 0) / n
  const num = xs.reduce((s, x, i) => s + (x - mx) * (ys[i] - my), 0)
  const den = xs.reduce((s, x) => s + (x - mx) ** 2, 0)
  const slope = den > 0 ? num / den : 0
  const intercept = my - slope * mx
  return xs.map(x => +(slope * x + intercept).toFixed(4))
}

export default function AgencyDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const agencyId = Number(id)
  const [activeTab, setActiveTab] = useState<Tab>('개요')
  const [bidPage, setBidPage] = useState(1)
  const [histMonths, setHistMonths] = useState<6 | 12 | 24>(12)
  const [freqPeriod, setFreqPeriod] = useState<'6M' | '12M' | '24M' | '48M'>('48M')

  const { data: meta } = useQuery<MetaData>({
    queryKey: ['meta'],
    queryFn: bidsApi.meta,
    staleTime: 300_000,
  })
  const agency = meta?.agencies.find((a) => a.id === agencyId)

  const { data: bidsData, isLoading: bidsLoading } = useQuery<{
    items: {
      id: number; title: string; industry_name: string | null
      base_amount: number; bid_open_date: string | null; winner_rate: number | null; status: string
    }[]
    total: number
  }>({
    queryKey: ['agency-bids', agencyId, bidPage],
    queryFn: () => bidsApi.list({ agency_id: agencyId, page: bidPage, size: 20, sort_by: 'bid_open_date' }),
    enabled: !!agencyId,
  })

  const { data: srateStats = [] } = useQuery<SrateStatItem[]>({
    queryKey: ['srate-stats', agencyId],
    queryFn: () => recommendApi.srateStats(agencyId) as Promise<SrateStatItem[]>,
    enabled: !!agencyId,
  })

  const { data: agencyStatsList = [] } = useQuery<AgencyStatItem[]>({
    queryKey: ['stats-agencies', 24],
    queryFn: () => statsApi.agencies(24) as Promise<AgencyStatItem[]>,
    staleTime: 300_000,
  })

  const { data: histogram, isLoading: histLoading } = useQuery<SrateHistogramResponse>({
    queryKey: ['agency-srate-histogram', agencyId, histMonths],
    queryFn: () => agenciesApi.srateHistogram(agencyId, histMonths),
    enabled: !!agencyId && activeTab === '심층분석',
  })

  const { data: recentResultsData, isLoading: recentLoading } = useQuery<AgencyRecentResultsResponse>({
    queryKey: ['agency-recent-results', agencyId],
    queryFn: () => agenciesApi.recentResults(agencyId),
    enabled: !!agencyId && activeTab === '심층분석',
  })

  const { data: yegaPattern } = useQuery<AgencyYegaPattern>({
    queryKey: ['agency-yega-pattern', agencyId],
    queryFn: () => agenciesApi.yegaPattern(agencyId),
    enabled: !!agencyId && activeTab === '예가패턴',
    staleTime: 300_000,
  })

  const { data: freqData, isLoading: freqLoading } = useQuery({
    queryKey: ['agency-freq', agencyId, freqPeriod],
    queryFn: () => executionsApi.agencyFreq(agencyId, { period: freqPeriod }),
    enabled: !!agencyId && activeTab === '낙찰분포',
    staleTime: 300_000,
  })

  const { data: strategyData, isLoading: strategyLoading } = useQuery<AgencyStrategy>({
    queryKey: ['agency-strategy', agencyId],
    queryFn: () => agenciesApi.strategy(agencyId),
    enabled: !!agencyId && activeTab === '전략DB',
    staleTime: 600_000,
  })

  const agencyStat = agencyStatsList.find((a) => a.agency_id === agencyId)
  const agencySrate = srateStats.find((s) => s.group_type === 'agency')
  const globalSrate = srateStats.find((s) => s.group_type === 'global')

  const closedBids = (bidsData?.items ?? []).filter((b) => b.winner_rate != null)
  const rateDistData = buildRateDist(closedBids)
  const totalPages = bidsData ? Math.ceil(bidsData.total / 20) : 1

  const trendData = closedBids
    .filter((b) => b.bid_open_date)
    .sort((a, b) => new Date(a.bid_open_date!).getTime() - new Date(b.bid_open_date!).getTime())
    .map((b) => ({
      date: new Date(b.bid_open_date!).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' }),
      rate: b.winner_rate != null ? +(b.winner_rate * 100).toFixed(4) : null,
    }))
  const globalMean = globalSrate?.srate_mean != null ? +(globalSrate.srate_mean * 100).toFixed(4) : null
  const agencyMean = agencySrate?.srate_mean != null ? +(agencySrate.srate_mean * 100).toFixed(4) : null

  const timelineRaw = (recentResultsData?.items ?? [])
    .filter((r) => r.assessment_rate != null && r.bid_open_date != null)
    .sort((a, b) => new Date(a.bid_open_date!).getTime() - new Date(b.bid_open_date!).getTime())

  const trendValues = computeLinearTrend(timelineRaw.map((r) => ({ rate: r.assessment_rate! * 100 })))
  const timelineChartData = timelineRaw.map((r, i) => ({
    date: new Date(r.bid_open_date!).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' }),
    rate: +(r.assessment_rate! * 100).toFixed(4),
    trend: trendValues[i] ?? null,
  }))
  const tlN = timelineChartData.length
  const tlMeanRate =
    tlN > 0 ? +(timelineChartData.reduce((s, d) => s + d.rate, 0) / tlN).toFixed(4) : null

  const trendSlope = tlN >= 2 ? trendValues[tlN - 1] - trendValues[0] : 0

  const histBins = (histogram?.bins ?? []).map((b) => ({
    label: (b.range_lo * 100).toFixed(1),
    count: b.count,
    pct: b.pct,
    range_lo: b.range_lo,
    belowFloor: b.range_lo < FLOOR_RATE,
  }))

  const findBinLabel = (val: number | null): string | null => {
    if (val == null || !histogram) return null
    const bin = histogram.bins.find((b) => b.range_lo <= val && val < b.range_hi)
    return bin ? (bin.range_lo * 100).toFixed(1) : null
  }
  const histMeanLabel = findBinLabel(histogram?.mean ?? null)
  const histP50Label = findBinLabel(histogram?.percentiles.p50 ?? null)
  const histFloorLabel = findBinLabel(FLOOR_RATE)

  return (
    <div className="flex flex-col min-h-full">
      {/* 기관 정보 헤더 패널 */}
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-sm border-b border-slate-200">
        {/* 상단 네비게이션 바 */}
        <div className="px-6 py-3 border-b border-slate-100 flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => navigate(-1)}
            className="h-8 text-slate-600 hover:text-slate-900 hover:bg-slate-100 -ml-2">
            <ChevronLeft className="h-4 w-4 mr-1" />뒤로
          </Button>
          <div className="h-4 w-px bg-slate-200" />
          <div className="flex items-center gap-2">
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-blue-50 border border-blue-200 shrink-0">
              <Building2 className="h-4 w-4 text-blue-600" />
            </div>
            <div>
              <h1 className="text-base font-semibold text-slate-900 leading-tight">
                {agency?.name ?? `기관 #${agencyId}`}
              </h1>
              <p className="text-xs text-slate-500">발주기관 심층 분석</p>
            </div>
          </div>
          {agencyStat && agencyStat.bid_count >= 100 && (
            <Badge className="ml-1 bg-blue-50 text-blue-700 border-blue-200 text-xs">A등급</Badge>
          )}
          {agencyStat && agencyStat.bid_count >= 50 && agencyStat.bid_count < 100 && (
            <Badge className="ml-1 bg-emerald-50 text-emerald-700 border-emerald-200 text-xs">B등급</Badge>
          )}
        </div>

        {/* KPI 스트립 */}
        <div className="px-6 py-3 flex items-center gap-6 overflow-x-auto">
          {[
            { label: '총 입찰공고', value: bidsData?.total?.toLocaleString() ?? '-', unit: '건', icon: FileText, color: 'text-blue-600' },
            { label: '평균 낙찰률', value: agencyStat?.avg_rate != null ? (agencyStat.avg_rate * 100).toFixed(4) : '-', unit: '%', icon: Target, color: 'text-emerald-600' },
            { label: '평균 경쟁업체', value: agencyStat?.avg_competitor_count != null ? agencyStat.avg_competitor_count.toFixed(1) : '-', unit: '개사', icon: Users, color: 'text-amber-600' },
            { label: '사정율 중앙값', value: agencySrate?.srate_p50 != null ? (agencySrate.srate_p50 * 100).toFixed(4) : '-', unit: '%', icon: TrendingUp, color: 'text-violet-600' },
          ].map(({ label, value, unit, icon: Icon, color }) => (
            <div key={label} className="flex items-center gap-2.5 shrink-0">
              <Icon className={cn('h-4 w-4 shrink-0', color)} />
              <div>
                <p className="text-xs text-slate-500 leading-none">{label}</p>
                <p className="text-sm font-bold text-slate-900 tabular-nums leading-tight mt-0.5">
                  {value}
                  <span className="text-xs font-normal text-slate-500 ml-0.5">{unit}</span>
                </p>
              </div>
              <div className="h-6 w-px bg-slate-200 ml-1" />
            </div>
          ))}
        </div>

        {/* 탭 네비게이션 */}
        <div className="px-6 flex border-t border-slate-100">
          {TABS.map((tab) => {
            const Icon = TAB_ICONS[tab]
            return (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={cn(
                  'flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors',
                  activeTab === tab
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-slate-500 hover:text-slate-700 hover:bg-slate-50',
                )}
              >
                <Icon className="h-3.5 w-3.5" />{tab}
              </button>
            )
          })}
        </div>
      </div>

      {/* 탭 컨텐츠 */}
      <div className="flex-1 p-6 max-w-[1440px] mx-auto w-full">

        {/* ── 개요 탭 ── */}
        {activeTab === '개요' && (
          <div className="space-y-5">
            {/* 사정율 분포 (기관 vs 전국) */}
            {agencySrate && (
              <Card className="bg-white border-slate-200 shadow-sm">
                <CardHeader className="border-b border-slate-100 pb-3 flex flex-row items-center justify-between">
                  <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                    <BarChart3 className="h-4 w-4 text-blue-500" />사정율 분포
                    <span className="text-xs font-normal text-slate-500">기관 vs 전국 평균</span>
                  </CardTitle>
                  <span className="text-xs text-slate-500">표본 {agencySrate.sample_count}건 기준</span>
                </CardHeader>
                <CardContent className="pt-4">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                    <SrateBox label="P25" value={agencySrate.srate_p25} global={globalSrate?.srate_p25 ?? null} />
                    <SrateBox label="중앙(P50)" value={agencySrate.srate_p50} global={globalSrate?.srate_p50 ?? null} highlight />
                    <SrateBox label="P75" value={agencySrate.srate_p75} global={globalSrate?.srate_p75 ?? null} />
                    <SrateBox label="평균" value={agencySrate.srate_mean} global={globalSrate?.srate_mean ?? null} />
                  </div>
                  {agencySrate.srate_trend != null && (
                    <div className={cn(
                      'flex items-center gap-2 px-3 py-2 rounded-lg text-xs',
                      agencySrate.srate_trend > 0
                        ? 'bg-blue-50 text-blue-700 border border-blue-200'
                        : 'bg-red-50 text-red-700 border border-red-200'
                    )}>
                      <span>{agencySrate.srate_trend > 0 ? '▲' : '▼'} 최근 추세</span>
                      <span className="font-semibold">{Math.abs(agencySrate.srate_trend * 100).toFixed(4)}%</span>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {/* 낙찰률 흐름 */}
              {trendData.length >= 3 && (
                <Card className="bg-white border-slate-200 shadow-sm">
                  <CardHeader className="border-b border-slate-100 pb-3 flex flex-row items-center justify-between">
                    <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                      <TrendingUp className="h-4 w-4 text-blue-500" />낙찰률 흐름
                    </CardTitle>
                    <div className="flex items-center gap-3 text-xs">
                      {agencyMean != null && <span className="text-blue-600 font-medium">기관 {agencyMean}%</span>}
                      {globalMean != null && <span className="text-slate-500">전국 {globalMean}%</span>}
                    </div>
                  </CardHeader>
                  <CardContent className="pt-4">
                    <ResponsiveContainer width="100%" height={240}>
                      <ComposedChart data={trendData} margin={{ left: -10, right: 10 }}>
                        <defs>
                          <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#2563eb" stopOpacity={0.15} />
                            <stop offset="100%" stopColor="#2563eb" stopOpacity={0.02} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                        <XAxis dataKey="date" tick={{ fontSize: 12, fill: '#475569' }} interval={Math.max(1, Math.floor(trendData.length / 8))} />
                        <YAxis tick={{ fontSize: 12, fill: '#475569' }} unit="%" domain={['auto', 'auto']} />
                        <Tooltip
                          contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                          formatter={(v: number) => [v + '%', '낙찰률']}
                        />
                        <Area type="monotone" dataKey="rate" fill="url(#areaGrad)" stroke="#2563eb" strokeWidth={2}
                          dot={{ r: 3, fill: '#2563eb', strokeWidth: 0 }} connectNulls />
                        {agencyMean != null && (
                          <ReferenceLine y={agencyMean} stroke="#2563eb" strokeDasharray="4 2"
                            label={{ value: '기관평균', position: 'insideTopRight', fontSize: 11, fill: '#1d4ed8' }} />
                        )}
                        {globalMean != null && (
                          <ReferenceLine y={globalMean} stroke="#94a3b8" strokeDasharray="4 2"
                            label={{ value: '전국', position: 'insideTopLeft', fontSize: 11, fill: '#475569' }} />
                        )}
                      </ComposedChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              )}

              {/* 낙찰률 분포 */}
              {rateDistData.some((d) => d.count > 0) && (
                <Card className="bg-white border-slate-200 shadow-sm">
                  <CardHeader className="border-b border-slate-100 pb-3 flex flex-row items-center justify-between">
                    <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                      <Activity className="h-4 w-4 text-emerald-500" />낙찰률 분포
                    </CardTitle>
                    <span className="text-xs text-slate-500">수집 공고 기준</span>
                  </CardHeader>
                  <CardContent className="pt-4">
                    <ResponsiveContainer width="100%" height={240}>
                      <BarChart data={rateDistData} margin={{ top: 5, right: 10, bottom: 5, left: -20 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                        <XAxis dataKey="range" tick={{ fontSize: 12, fill: '#475569' }} interval={1} />
                        <YAxis tick={{ fontSize: 12, fill: '#475569' }} />
                        <Tooltip
                          contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                          formatter={(v: number) => [`${v}건`, '건수']}
                        />
                        <Bar dataKey="count" fill="#10b981" fillOpacity={0.8} radius={[3, 3, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        )}

        {/* ── 공고목록 탭 ── */}
        {activeTab === '공고목록' && (
          <Card className="bg-white border-slate-200 shadow-sm">
            <CardHeader className="border-b border-slate-100 pb-3 flex flex-row items-center justify-between">
              <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                <FileText className="h-4 w-4 text-blue-500" />입찰 공고 목록
              </CardTitle>
              {bidsData && (
                <span className="text-xs text-slate-500">총 {bidsData.total.toLocaleString()}건</span>
              )}
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-hidden">
                <Table>
                  <TableHeader className="bg-slate-50">
                    <TableRow>
                      <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide">공고명</TableHead>
                      <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide">공종</TableHead>
                      <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide text-right">기초금액</TableHead>
                      <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide">개찰일</TableHead>
                      <TableHead className="font-semibold text-slate-600 text-sm uppercase tracking-wide text-right">낙찰률</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {bidsLoading
                      ? Array.from({ length: 5 }).map((_, i) => (
                          <TableRow key={i}>
                            {Array.from({ length: 5 }).map((_, j) => (
                              <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
                            ))}
                          </TableRow>
                        ))
                      : (bidsData?.items ?? []).map((b) => (
                          <TableRow key={b.id}
                            className="cursor-pointer hover:bg-slate-50/80 transition-colors"
                            onClick={() => navigate(`/bids/${b.id}`)}>
                            <TableCell className="max-w-xs">
                              <span className="truncate block font-medium text-blue-600 hover:text-blue-700 text-sm">{b.title}</span>
                            </TableCell>
                            <TableCell>
                              <span className="text-xs text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full whitespace-nowrap">
                                {b.industry_name ?? '-'}
                              </span>
                            </TableCell>
                            <TableCell className="text-right whitespace-nowrap">
                              <span className="text-sm font-medium text-slate-700">{b.base_amount > 0 ? (b.base_amount / 1e8).toFixed(1) + '억' : '-'}</span>
                            </TableCell>
                            <TableCell className="whitespace-nowrap text-sm text-slate-500">
                              {b.bid_open_date ? new Date(b.bid_open_date).toLocaleDateString('ko-KR') : '-'}
                            </TableCell>
                            <TableCell className="text-right">
                              {b.winner_rate != null ? (
                                <span className="font-mono font-semibold text-xs text-blue-600">
                                  {(b.winner_rate * 100).toFixed(4)}%
                                </span>
                              ) : (
                                <span className="text-xs text-slate-300">-</span>
                              )}
                            </TableCell>
                          </TableRow>
                        ))}
                  </TableBody>
                </Table>
              </div>
              {bidsData && bidsData.total > 20 && (
                <div className="flex items-center justify-between px-5 py-3 border-t border-slate-100 bg-slate-50/50">
                  <Button variant="outline" size="sm"
                    onClick={() => setBidPage((p) => Math.max(1, p - 1))}
                    disabled={bidPage === 1}
                    className="h-8 text-xs border-slate-200">
                    <ChevronLeft className="h-3.5 w-3.5 mr-1" />이전
                  </Button>
                  <span className="text-xs text-slate-500">
                    <span className="font-medium text-slate-700">{bidPage}</span> / {totalPages} 페이지
                    <span className="text-slate-500 ml-1">({bidsData.total.toLocaleString()}건)</span>
                  </span>
                  <Button variant="outline" size="sm"
                    onClick={() => setBidPage((p) => p + 1)}
                    disabled={bidPage >= totalPages}
                    className="h-8 text-xs border-slate-200">
                    다음<ChevronLeft className="h-3.5 w-3.5 ml-1 rotate-180" />
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* ── 심층분석 탭 ── */}
        {activeTab === '심층분석' && (
          <div className="space-y-5">
            {/* 사정율 히스토그램 */}
            <Card className="bg-white border-slate-200 shadow-sm">
              <CardHeader className="border-b border-slate-100 pb-3 flex flex-row items-center justify-between">
                <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                  <BarChart3 className="h-4 w-4 text-blue-500" />사정율 히스토그램
                </CardTitle>
                <div className="flex items-center rounded-lg border border-slate-200 overflow-hidden">
                  {([6, 12, 24] as const).map((m) => (
                    <button
                      key={m}
                      onClick={() => setHistMonths(m)}
                      className={cn(
                        'px-3 py-1.5 text-sm font-medium transition-colors',
                        histMonths === m
                          ? 'bg-blue-600 text-white'
                          : 'bg-white text-slate-600 hover:bg-slate-50'
                      )}
                    >
                      {m}개월
                    </button>
                  ))}
                </div>
              </CardHeader>
              <CardContent className="pt-4">
                {histLoading ? (
                  <Skeleton className="h-[220px] w-full rounded-lg" />
                ) : histogram && histogram.sample_count > 0 ? (
                  <>
                    <ResponsiveContainer width="100%" height={220}>
                      <BarChart data={histBins} margin={{ top: 5, right: 10, bottom: 5, left: -20 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                        <XAxis dataKey="label" tick={{ fontSize: 12, fill: '#475569' }} interval={3} />
                        <YAxis tick={{ fontSize: 12, fill: '#475569' }} />
                        <Tooltip
                          contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                          formatter={(v: number, _name: string, props: { payload?: { pct?: number } }) =>
                            [`${v}건 (${props.payload?.pct ?? 0}%)`, '건수']
                          }
                          labelFormatter={(label) => `사정율 ${label}%`}
                        />
                        <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                          {histBins.map((entry, i) => (
                            <Cell key={i} fill={entry.belowFloor ? '#fca5a5' : '#2563eb'} fillOpacity={entry.belowFloor ? 0.6 : 0.8} />
                          ))}
                        </Bar>
                        {histMeanLabel && (
                          <ReferenceLine x={histMeanLabel} stroke="#2563eb" strokeDasharray="4 2"
                            label={{ value: '평균', position: 'insideTopRight', fontSize: 11, fill: '#1d4ed8' }} />
                        )}
                        {histP50Label && histP50Label !== histMeanLabel && (
                          <ReferenceLine x={histP50Label} stroke="#94a3b8" strokeDasharray="4 2"
                            label={{ value: '중앙', position: 'insideTopLeft', fontSize: 11, fill: '#475569' }} />
                        )}
                        {histFloorLabel && (
                          <ReferenceLine x={histFloorLabel} stroke="#ef4444" strokeWidth={1.5}
                            label={{ value: '낙찰하한', position: 'insideTop', fontSize: 8, fill: '#ef4444' }} />
                        )}
                      </BarChart>
                    </ResponsiveContainer>
                    <div className="flex items-center gap-4 mt-2 text-xs text-slate-500">
                      <span>{histMonths}개월 · {histogram.sample_count}건</span>
                      {histogram.mean != null && (
                        <span>평균 <strong className="text-slate-800">{(histogram.mean * 100).toFixed(4)}%</strong></span>
                      )}
                      {histogram.std != null && (
                        <span>σ=<strong className="text-slate-800">{(histogram.std * 100).toFixed(4)}%</strong></span>
                      )}
                      <div className="flex items-center gap-2 ml-auto">
                        <div className="flex items-center gap-1"><div className="w-3 h-2 bg-blue-500 rounded opacity-80" /><span>정상</span></div>
                        <div className="flex items-center gap-1"><div className="w-3 h-2 bg-red-300 rounded opacity-60" /><span>하한 미달</span></div>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="flex flex-col items-center justify-center py-14 text-slate-500">
                    <BarChart3 className="h-8 w-8 mb-2 opacity-30" />
                    <p className="text-sm">{histLoading ? '로딩 중…' : `${histMonths}개월 내 낙찰 데이터 없음`}</p>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* 개찰 타임라인 */}
            <Card className="bg-white border-slate-200 shadow-sm">
              <CardHeader className="border-b border-slate-100 pb-3 flex flex-row items-center justify-between">
                <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                  <Activity className="h-4 w-4 text-blue-500" />개찰 타임라인
                  <span className="text-xs font-normal text-slate-500">사정율 추이</span>
                </CardTitle>
                {tlN >= 2 && (
                  <span className={cn(
                    'text-xs px-2 py-0.5 rounded-full font-medium',
                    trendSlope > 0.05 ? 'bg-blue-50 text-blue-700' :
                    trendSlope < -0.05 ? 'bg-red-50 text-red-700' : 'bg-slate-100 text-slate-600'
                  )}>
                    {trendSlope > 0.05 ? '▲ 상승' : trendSlope < -0.05 ? '▼ 하락' : '→ 안정'}
                  </span>
                )}
              </CardHeader>
              <CardContent className="pt-4">
                {recentLoading ? (
                  <Skeleton className="h-[220px] w-full rounded-lg" />
                ) : tlN >= 2 ? (
                  <>
                    <ResponsiveContainer width="100%" height={220}>
                      <ComposedChart data={timelineChartData} margin={{ left: -10, right: 10 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                        <XAxis dataKey="date" tick={{ fontSize: 12, fill: '#475569' }}
                          interval={Math.max(0, Math.floor(tlN / 8) - 1)} />
                        <YAxis tick={{ fontSize: 12, fill: '#475569' }} unit="%" domain={['auto', 'auto']} />
                        <Tooltip
                          contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                          formatter={(v: number) => [v + '%', '사정율']}
                        />
                        <Line type="monotone" dataKey="rate"
                          dot={{ r: 3.5, fill: '#2563eb', strokeWidth: 0 }}
                          stroke="transparent" strokeWidth={0} connectNulls={false} />
                        <Line type="linear" dataKey="trend" dot={false}
                          stroke="#ef4444" strokeDasharray="4 2" strokeWidth={1.5} />
                        {tlMeanRate != null && (
                          <ReferenceLine y={tlMeanRate} stroke="#2563eb" strokeDasharray="4 2"
                            label={{ value: `평균 ${tlMeanRate}%`, position: 'insideTopRight', fontSize: 11, fill: '#1d4ed8' }} />
                        )}
                        <ReferenceLine y={+(FLOOR_RATE * 100).toFixed(4)} stroke="#ef4444" strokeWidth={1.5}
                          label={{ value: '하한', position: 'insideBottomRight', fontSize: 9, fill: '#ef4444' }} />
                      </ComposedChart>
                    </ResponsiveContainer>
                    <p className="text-xs text-slate-500 mt-2">
                      기울기 {trendSlope > 0 ? '+' : ''}{trendSlope.toFixed(4)}%p/회차
                    </p>
                  </>
                ) : (
                  <div className="flex flex-col items-center justify-center py-14 text-slate-500">
                    <Activity className="h-8 w-8 mb-2 opacity-30" />
                    <p className="text-sm">{recentLoading ? '로딩 중…' : '개찰 결과 데이터 부족 (최소 2건 필요)'}</p>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* 백분위수 요약 */}
            {histogram && histogram.sample_count > 0 && (
              <Card className="bg-white border-slate-200 shadow-sm">
                <CardHeader className="border-b border-slate-100 pb-3">
                  <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                    <Layers className="h-4 w-4 text-blue-500" />백분위수 요약
                  </CardTitle>
                </CardHeader>
                <CardContent className="pt-4">
                  <div className="grid grid-cols-3 md:grid-cols-5 gap-3">
                    {(['p10', 'p25', 'p50', 'p75', 'p90'] as const).map((key) => (
                      <div
                        key={key}
                        className={cn(
                          'rounded-xl p-3 text-center border',
                          key === 'p50'
                            ? 'bg-blue-50 border-blue-200'
                            : 'bg-slate-50 border-slate-200'
                        )}
                      >
                        <div className="text-xs text-slate-500 font-medium">{key.toUpperCase()}</div>
                        <div className={cn('text-sm font-bold mt-1 tabular-nums', key === 'p50' ? 'text-blue-600' : 'text-slate-800')}>
                          {histogram.percentiles[key] != null
                            ? (histogram.percentiles[key]! * 100).toFixed(4) + '%'
                            : '-'}
                        </div>
                      </div>
                    ))}
                  </div>
                  {histogram.std != null && (
                    <div className="mt-4 flex flex-wrap gap-5 text-xs text-slate-500 border-t border-slate-100 pt-3">
                      <span>표준편차: <strong className="text-slate-800">{(histogram.std * 100).toFixed(4)}%</strong></span>
                      <span>표본 수: <strong className="text-slate-800">{histogram.sample_count.toLocaleString()}건</strong></span>
                      {histogram.mean != null && (
                        <span>평균: <strong className="text-slate-800">{(histogram.mean * 100).toFixed(4)}%</strong></span>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </div>
        )}

        {/* ── 예가패턴 탭 ── */}
        {activeTab === '예가패턴' && (
          <div className="space-y-5">
            {!yegaPattern ? (
              <Card className="bg-white border-slate-200 shadow-sm">
                <CardContent className="py-16 text-center">
                  <div className="flex flex-col items-center gap-3 text-slate-500">
                    <GitBranch className="h-8 w-8 animate-pulse" />
                    <p className="text-sm">로딩 중…</p>
                  </div>
                </CardContent>
              </Card>
            ) : !yegaPattern.has_data ? (
              <Card className="bg-white border-slate-200 shadow-sm">
                <CardContent className="py-16 text-center">
                  <GitBranch className="h-10 w-10 text-slate-200 mx-auto mb-3" />
                  <p className="text-sm text-slate-500">수집된 inpo21c 예가 데이터가 없습니다.</p>
                  <p className="text-xs text-slate-500 mt-1">인포21c에서 예가 데이터 수집 후 사용 가능합니다.</p>
                </CardContent>
              </Card>
            ) : (
              <>
                {/* 요약 KPI 카드 */}
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                  {[
                    { label: '수집 공고 수', value: `${yegaPattern.sample_n}건`, sub: 'inpo21c 실측', color: 'blue' },
                    { label: '예가 후보 범위', value: `±${(yegaPattern.spread_half * 100).toFixed(4)}%`, sub: '기초금액 대비', color: 'emerald' },
                    {
                      label: '선호 위치 TOP 3',
                      value: yegaPattern.pos_weights
                        ? [...yegaPattern.pos_weights]
                            .map((w, i) => ({ pos: i + 1, w }))
                            .sort((a, b) => b.w - a.w)
                            .slice(0, 3)
                            .map((x) => `#${x.pos}`)
                            .join(' · ')
                        : '-',
                      sub: '추첨 확률 상위',
                      color: 'amber',
                    },
                  ].map(({ label, value, sub, color }) => (
                    <Card key={label} className="relative overflow-hidden bg-white border-slate-200 shadow-sm">
                      <div className={cn('absolute top-0 left-0 right-0 h-0.5',
                        color === 'blue' ? 'bg-blue-500' : color === 'emerald' ? 'bg-emerald-500' : 'bg-amber-500'
                      )} />
                      <CardContent className="p-5">
                        <p className="text-sm font-medium text-slate-500">{label}</p>
                        <p className="text-xl font-bold mt-1 tabular-nums text-slate-900">{value}</p>
                        <p className="text-xs text-slate-500 mt-1">{sub}</p>
                      </CardContent>
                    </Card>
                  ))}
                </div>

                {/* 위치별 추첨 확률 */}
                {yegaPattern.pos_weights && (
                  <Card className="bg-white border-slate-200 shadow-sm">
                    <CardHeader className="border-b border-slate-100 pb-3 flex flex-row items-center justify-between">
                      <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                        <GitBranch className="h-4 w-4 text-blue-500" />위치별 추첨 확률
                        <span className="text-xs font-normal text-slate-500">1~15번</span>
                      </CardTitle>
                      <span className="text-xs text-slate-500">균등 기준: 6.7%</span>
                    </CardHeader>
                    <CardContent className="pt-4">
                      <ResponsiveContainer width="100%" height={220}>
                        <BarChart
                          data={yegaPattern.pos_weights.map((w, i) => ({
                            pos: `${i + 1}번`,
                            pct: +(w * 100).toFixed(1),
                            isTop: w >= [...yegaPattern.pos_weights!].sort((a, b) => b - a)[2],
                          }))}
                          margin={{ top: 8, right: 8, left: -20, bottom: 0 }}
                        >
                          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                          <XAxis dataKey="pos" tick={{ fontSize: 12, fill: '#475569' }} />
                          <YAxis tick={{ fontSize: 12, fill: '#475569' }} tickFormatter={(v) => `${v}%`} domain={[0, 12]} />
                          <Tooltip
                            contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                            formatter={(v: number) => [`${v}%`, '추첨 확률']}
                          />
                          <ReferenceLine y={+(1 / 15 * 100).toFixed(1)} stroke="#94a3b8"
                            strokeDasharray="4 2"
                            label={{ value: '균등 6.7%', position: 'insideTopRight', fontSize: 11, fill: '#475569' }} />
                          <Bar dataKey="pct" radius={[4, 4, 0, 0]}>
                            {yegaPattern.pos_weights.map((w, i) => {
                              const top3Threshold = [...yegaPattern.pos_weights!].sort((a, b) => b - a)[2]
                              return <Cell key={i} fill={w >= top3Threshold ? '#2563eb' : '#bfdbfe'} />
                            })}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                      <div className="flex items-center gap-4 mt-3 text-xs text-slate-500">
                        <div className="flex items-center gap-1.5"><div className="w-3 h-2 bg-blue-600 rounded" /><span>선호 위치 (상위 3개)</span></div>
                        <div className="flex items-center gap-1.5"><div className="w-3 h-2 bg-blue-200 rounded" /><span>일반 위치</span></div>
                      </div>
                    </CardContent>
                  </Card>
                )}
              </>
            )}
          </div>
        )}

        {/* ── 전략DB 탭 ── */}
        {activeTab === '전략DB' && (
          <div className="space-y-5">
            {strategyLoading ? (
              <Skeleton className="h-64 w-full rounded-xl" />
            ) : !strategyData || strategyData.total_bid_count === 0 ? (
              <Card className="bg-white border-slate-200 shadow-sm">
                <CardContent className="py-16 text-center">
                  <TrendingUp className="h-10 w-10 text-slate-200 mx-auto mb-3" />
                  <p className="text-sm text-slate-500">발주기관 전략 DB 데이터가 없습니다.</p>
                  <p className="text-xs text-slate-500 mt-1">48개월 내 낙찰 데이터가 5건 이상 필요합니다.</p>
                </CardContent>
              </Card>
            ) : (
              <>
                {/* KPI 카드 */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  {[
                    { label: '표본 건수',     value: `${strategyData.total_bid_count.toLocaleString()}건`, color: 'blue' },
                    { label: '평균 낙찰률',   value: strategyData.avg_win_rate != null ? `${(strategyData.avg_win_rate * 100).toFixed(4)}%` : '-', color: 'emerald' },
                    { label: '평균 경쟁업체', value: strategyData.avg_competitor_cnt != null ? `${strategyData.avg_competitor_cnt.toFixed(1)}개사` : '-', color: 'amber' },
                    { label: '난이도',        value: strategyData.qual_difficulty ?? '-', color: 'violet' },
                  ].map(({ label, value, color }) => (
                    <Card key={label} className="relative overflow-hidden bg-white border-slate-200 shadow-sm">
                      <div className={cn('absolute top-0 left-0 right-0 h-0.5',
                        color === 'blue' ? 'bg-blue-500' : color === 'emerald' ? 'bg-emerald-500'
                          : color === 'amber' ? 'bg-amber-500' : 'bg-violet-500'
                      )} />
                      <CardContent className="p-4">
                        <p className="text-xs text-slate-500">{label}</p>
                        <p className="text-xl font-bold mt-1 tabular-nums text-slate-900">{value}</p>
                      </CardContent>
                    </Card>
                  ))}
                </div>

                {/* 백분위수 + 추천 구간 */}
                <Card className="bg-white border-slate-200 shadow-sm">
                  <CardHeader className="border-b border-slate-100 pb-3">
                    <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                      <Layers className="h-4 w-4 text-blue-500" />낙찰률 백분위수 (48개월)
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="pt-4">
                    <div className="grid grid-cols-5 gap-2 mb-4">
                      {(
                        [
                          ['P10', strategyData.win_rate_p10],
                          ['P25', strategyData.win_rate_p25],
                          ['P50 (중앙)', strategyData.win_rate_p50],
                          ['P75', strategyData.win_rate_p75],
                          ['P90', strategyData.win_rate_p90],
                        ] as [string, number | null][]
                      ).map(([key, val]) => (
                        <div key={key} className={cn(
                          'rounded-xl p-3 text-center border',
                          key === 'P50 (중앙)' ? 'bg-blue-50 border-blue-200' : 'bg-slate-50 border-slate-200'
                        )}>
                          <div className="text-xs text-slate-500 font-medium">{key}</div>
                          <div className={cn('text-sm font-bold mt-1 tabular-nums',
                            key === 'P50 (중앙)' ? 'text-blue-600' : 'text-slate-800'
                          )}>
                            {val != null ? `${(val * 100).toFixed(4)}%` : '-'}
                          </div>
                        </div>
                      ))}
                    </div>
                    {strategyData.recommended_range_lo != null && strategyData.recommended_range_hi != null && (
                      <div className="flex items-center gap-3 px-4 py-3 bg-emerald-50 rounded-xl border border-emerald-200 text-sm">
                        <Target className="h-4 w-4 text-emerald-600 shrink-0" />
                        <span className="text-emerald-700 font-medium">추천 투찰 구간</span>
                        <span className="text-emerald-800 font-bold tabular-nums ml-auto">
                          {(strategyData.recommended_range_lo * 100).toFixed(4)}% ~ {(strategyData.recommended_range_hi * 100).toFixed(4)}%
                        </span>
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* 히스토그램 */}
                {strategyData.histogram_data.length > 0 && (
                  <Card className="bg-white border-slate-200 shadow-sm">
                    <CardHeader className="border-b border-slate-100 pb-3 flex flex-row items-center justify-between">
                      <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                        <BarChart2 className="h-4 w-4 text-blue-500" />낙찰률 히스토그램 (48개월 · 0.5% 구간)
                      </CardTitle>
                      <div className="flex items-center gap-3 text-xs text-slate-500">
                        {strategyData.trend_direction && (
                          <span className={cn(
                            'px-2 py-0.5 rounded-full font-medium',
                            strategyData.trend_direction === 'up' ? 'bg-blue-50 text-blue-700' :
                            strategyData.trend_direction === 'down' ? 'bg-red-50 text-red-700' :
                            'bg-slate-100 text-slate-600'
                          )}>
                            {strategyData.trend_direction === 'up' ? '▲ 상승 추세' :
                             strategyData.trend_direction === 'down' ? '▼ 하락 추세' : '→ 안정'}
                          </span>
                        )}
                      </div>
                    </CardHeader>
                    <CardContent className="pt-4">
                      <ResponsiveContainer width="100%" height={240}>
                        <BarChart
                          data={strategyData.histogram_data
                            .filter(([, cnt]) => cnt > 0)
                            .map(([rate, cnt]) => ({
                              label: (rate * 100).toFixed(4),
                              count: cnt,
                              isRec: strategyData.recommended_range_lo != null &&
                                     strategyData.recommended_range_hi != null &&
                                     rate >= strategyData.recommended_range_lo &&
                                     rate < strategyData.recommended_range_hi,
                            }))}
                          margin={{ top: 8, right: 8, left: -15, bottom: 24 }}
                        >
                          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                          <XAxis dataKey="label" tick={{ fontSize: 12, fill: '#475569' }}
                            tickFormatter={(v) => `${v}%`} interval={2} angle={-40} textAnchor="end" height={44} />
                          <YAxis tick={{ fontSize: 12, fill: '#475569' }} />
                          <Tooltip
                            contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: 12 }}
                            formatter={(v: number) => [`${v}건`, '낙찰 건수']}
                            labelFormatter={(l) => `낙찰률 ${l}%~`}
                          />
                          <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                            {strategyData.histogram_data
                              .filter(([, cnt]) => cnt > 0)
                              .map(([rate], i) => (
                                <Cell key={i} fill={
                                  strategyData.recommended_range_lo != null &&
                                  strategyData.recommended_range_hi != null &&
                                  rate >= strategyData.recommended_range_lo &&
                                  rate < strategyData.recommended_range_hi
                                    ? '#16a34a'
                                    : '#2563eb'
                                } fillOpacity={0.8} />
                              ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                      <div className="flex items-center gap-4 mt-2 text-xs text-slate-500">
                        <div className="flex items-center gap-1.5"><div className="w-3 h-2 bg-blue-600 rounded opacity-80" /><span>일반 구간</span></div>
                        <div className="flex items-center gap-1.5"><div className="w-3 h-2 bg-green-600 rounded opacity-80" /><span>추천 구간 (P25~P75)</span></div>
                        {strategyData.std_win_rate != null && (
                          <span className="ml-auto">σ = {(strategyData.std_win_rate * 100).toFixed(4)}%</span>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* 부가 지표 */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <Card className="bg-white border-slate-200 shadow-sm">
                    <CardContent className="p-4">
                      <p className="text-xs text-slate-500 mb-1">공격성 지수</p>
                      <p className="text-2xl font-bold text-slate-900 tabular-nums">
                        {strategyData.aggression_index != null
                          ? `${(strategyData.aggression_index * 100).toFixed(1)}%`
                          : '-'}
                      </p>
                      <p className="text-xs text-slate-500 mt-1">하한율 이하 낙찰 비율</p>
                    </CardContent>
                  </Card>
                  <Card className="bg-white border-slate-200 shadow-sm">
                    <CardContent className="p-4">
                      <p className="text-xs text-slate-500 mb-1">30일 변동성</p>
                      <p className="text-2xl font-bold text-slate-900 tabular-nums">
                        {strategyData.volatility_30d != null
                          ? `${(strategyData.volatility_30d * 100).toFixed(4)}%`
                          : '-'}
                      </p>
                      <p className="text-xs text-slate-500 mt-1">최근 30일 표준편차</p>
                    </CardContent>
                  </Card>
                  <Card className="bg-white border-slate-200 shadow-sm">
                    <CardContent className="p-4">
                      <p className="text-xs text-slate-500 mb-1">낙찰률 범위</p>
                      <p className="text-lg font-bold text-slate-900 tabular-nums">
                        {strategyData.min_win_rate != null && strategyData.max_win_rate != null
                          ? `${(strategyData.min_win_rate * 100).toFixed(4)}% ~ ${(strategyData.max_win_rate * 100).toFixed(4)}%`
                          : '-'}
                      </p>
                      <p className="text-xs text-slate-500 mt-1">최저 ~ 최고 낙찰률</p>
                    </CardContent>
                  </Card>
                </div>
              </>
            )}
          </div>
        )}

        {/* ── 낙찰분포 탭 ── */}
        {activeTab === '낙찰분포' && (
          <div className="space-y-5">
            <Card className="bg-white border-slate-200 shadow-sm">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <CardTitle className="text-base">낙찰률 빈도표 (0.5% 구간)</CardTitle>
                  <div className="flex gap-1">
                    {(['6M', '12M', '24M', '48M'] as const).map((p) => (
                      <button
                        key={p}
                        onClick={() => setFreqPeriod(p)}
                        className={cn(
                          'px-2.5 py-1 text-xs rounded-md font-medium border transition-colors',
                          freqPeriod === p
                            ? 'bg-blue-600 text-white border-blue-600'
                            : 'bg-white text-slate-500 border-slate-200 hover:bg-slate-50',
                        )}
                      >
                        {p}
                      </button>
                    ))}
                  </div>
                </div>
                {freqData && (
                  <p className="text-sm text-muted-foreground mt-1">
                    {freqData.period} 집계 · 총 {freqData.total_bids.toLocaleString()}건
                  </p>
                )}
              </CardHeader>
              <CardContent>
                {freqLoading ? (
                  <div className="flex justify-center py-10">
                    <div className="h-8 w-8 rounded-full border-4 border-blue-200 border-t-blue-600 animate-spin" />
                  </div>
                ) : !freqData || freqData.buckets.length === 0 ? (
                  <div className="text-center py-10 text-sm text-muted-foreground">
                    해당 기관의 낙찰률 데이터가 없습니다.
                  </div>
                ) : (
                  <>
                    <ResponsiveContainer width="100%" height={280}>
                      <BarChart
                        data={freqData.buckets.map((b) => ({
                          label: (b.from * 100).toFixed(4),
                          count: b.count,
                          win_count: b.win_count,
                          win_rate: b.win_rate != null ? +(b.win_rate * 100).toFixed(1) : 0,
                          isFloor: b.from <= FLOOR_RATE && b.to > FLOOR_RATE,
                        }))}
                        margin={{ top: 8, right: 8, left: -15, bottom: 24 }}
                        barCategoryGap="10%"
                      >
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                        <XAxis
                          dataKey="label"
                          tick={{ fontSize: 12, fill: '#475569' }}
                          tickFormatter={(v) => `${v}%`}
                          interval={2}
                          angle={-40}
                          textAnchor="end"
                          height={44}
                        />
                        <YAxis yAxisId="left" tick={{ fontSize: 12, fill: '#475569' }} />
                        <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 12, fill: '#475569' }} tickFormatter={(v) => `${v}%`} domain={[0, 100]} />
                        <Tooltip
                          contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: 12 }}
                          formatter={(v: number, name: string) =>
                            name === 'win_rate' ? [`${v}%`, '낙찰률'] : [v.toLocaleString() + '건', name === 'count' ? '전체' : '낙찰']
                          }
                          labelFormatter={(l) => `${l}%~`}
                        />
                        <Bar yAxisId="left" dataKey="count" name="count" radius={[3, 3, 0, 0]}>
                          {freqData.buckets.map((b, i) => (
                            <Cell key={i} fill={b.from <= FLOOR_RATE && b.to > FLOOR_RATE ? '#f59e0b' : b.win_rate > 0.3 ? '#2563eb' : '#bfdbfe'} />
                          ))}
                        </Bar>
                        <Bar yAxisId="left" dataKey="win_count" name="win_count" fill="#16a34a" opacity={0.7} radius={[2, 2, 0, 0]} />
                        <ReferenceLine yAxisId="left" x={`${(FLOOR_RATE * 100).toFixed(4)}`} stroke="#f59e0b" strokeDasharray="4 2" label={{ value: '하한', position: 'top', fontSize: 9, fill: '#f59e0b' }} />
                      </BarChart>
                    </ResponsiveContainer>

                    <div className="flex items-center gap-5 mt-2 text-xs text-slate-500 flex-wrap">
                      <div className="flex items-center gap-1.5"><div className="w-3 h-2 bg-blue-600 rounded" /><span>전체 참여</span></div>
                      <div className="flex items-center gap-1.5"><div className="w-3 h-2 bg-green-600 rounded opacity-70" /><span>낙찰</span></div>
                      <div className="flex items-center gap-1.5"><div className="w-3 h-2 bg-amber-400 rounded" /><span>하한율 부근</span></div>
                    </div>

                    {/* 최빈 구간 */}
                    {(() => {
                      const top3 = [...freqData.buckets].sort((a, b) => b.count - a.count).slice(0, 3)
                      return (
                        <div className="mt-4 grid grid-cols-3 gap-2">
                          {top3.map((b, i) => (
                            <div key={i} className="rounded-lg bg-slate-50 border p-2.5 text-center">
                              <div className="text-sm text-muted-foreground">#{i + 1} 최다 구간</div>
                              <div className="text-sm font-bold text-slate-800 mt-0.5">
                                {(b.from * 100).toFixed(4)}–{(b.to * 100).toFixed(4)}%
                              </div>
                              <div className="text-xs text-slate-500">{b.count}건 / 낙찰 {b.win_count}건</div>
                              {b.win_rate > 0 && (
                                <div className="text-xs text-blue-600 font-medium">{(b.win_rate * 100).toFixed(0)}% 낙찰률</div>
                              )}
                            </div>
                          ))}
                        </div>
                      )
                    })()}
                  </>
                )}
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </div>
  )
}

function SrateBox({
  label, value, global: globalVal, highlight
}: {
  label: string; value: number | null; global: number | null; highlight?: boolean
}) {
  const pct = (v: number | null) => v != null ? (v * 100).toFixed(4) + '%' : '-'
  const diff = value != null && globalVal != null ? value - globalVal : null
  return (
    <div className={cn(
      'rounded-xl p-3.5 border',
      highlight
        ? 'bg-blue-50 border-blue-200'
        : 'bg-slate-50 border-slate-200'
    )}>
      <div className="text-sm font-medium text-slate-500 mb-1">{label}</div>
      <div className={cn('text-base font-bold tabular-nums', highlight ? 'text-blue-600' : 'text-slate-800')}>
        {pct(value)}
      </div>
      {diff != null && (
        <div className={cn(
          'text-xs mt-1 flex items-center gap-0.5',
          diff > 0 ? 'text-blue-600' : diff < 0 ? 'text-red-500' : 'text-slate-500'
        )}>
          <span>{diff > 0 ? '▲' : diff < 0 ? '▼' : '='}</span>
          <span>전국 대비 {diff > 0 ? '+' : ''}{(diff * 100).toFixed(4)}%</span>
        </div>
      )}
    </div>
  )
}
