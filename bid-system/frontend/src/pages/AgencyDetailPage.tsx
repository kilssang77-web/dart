import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, Building2 } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, ReferenceLine, ComposedChart, Area, Cell,
} from 'recharts'
import { bidsApi, recommendApi, statsApi, agenciesApi } from '@/api'
import type { MetaData, SrateHistogramResponse, AgencyRecentResultsResponse, AgencyYegaPattern } from '@/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table'

const FLOOR_RATE = 0.87745
const TABS = ['개요', '공고목록', '심층분석', '예가패턴'] as const
type Tab = (typeof TABS)[number]

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

  // 심층분석 쿼리 (탭 활성화 시에만 로드)
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

  const agencyStat = agencyStatsList.find((a) => a.agency_id === agencyId)
  const agencySrate = srateStats.find((s) => s.group_type === 'agency')
  const globalSrate = srateStats.find((s) => s.group_type === 'global')

  const closedBids = (bidsData?.items ?? []).filter((b) => b.winner_rate != null)
  const rateDistData = buildRateDist(closedBids)
  const totalPages = bidsData ? Math.ceil(bidsData.total / 20) : 1

  // 개요탭 — 낙찰률 흐름 시계열
  const trendData = closedBids
    .filter((b) => b.bid_open_date)
    .sort((a, b) => new Date(a.bid_open_date!).getTime() - new Date(b.bid_open_date!).getTime())
    .map((b) => ({
      date: new Date(b.bid_open_date!).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' }),
      rate: b.winner_rate != null ? +(b.winner_rate * 100).toFixed(3) : null,
    }))
  const globalMean = globalSrate?.srate_mean != null ? +(globalSrate.srate_mean * 100).toFixed(3) : null
  const agencyMean = agencySrate?.srate_mean != null ? +(agencySrate.srate_mean * 100).toFixed(3) : null

  // 심층분석탭 — 개찰 타임라인
  const timelineRaw = (recentResultsData?.items ?? [])
    .filter((r) => r.assessment_rate != null && r.bid_open_date != null)
    .sort((a, b) => new Date(a.bid_open_date!).getTime() - new Date(b.bid_open_date!).getTime())

  const trendValues = computeLinearTrend(timelineRaw.map((r) => ({ rate: r.assessment_rate! * 100 })))
  const timelineChartData = timelineRaw.map((r, i) => ({
    date: new Date(r.bid_open_date!).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' }),
    rate: +(r.assessment_rate! * 100).toFixed(3),
    trend: trendValues[i] ?? null,
  }))
  const tlN = timelineChartData.length
  const tlMeanRate =
    tlN > 0 ? +(timelineChartData.reduce((s, d) => s + d.rate, 0) / tlN).toFixed(3) : null

  // 트렌드 방향 계산
  const trendSlope = tlN >= 2 ? trendValues[tlN - 1] - trendValues[0] : 0

  // 심층분석탭 — 히스토그램 데이터
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
    <div className="p-6 space-y-5">
      {/* 헤더 */}
      <div className="flex items-center gap-3 flex-wrap">
        <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
          <ChevronLeft className="h-4 w-4 mr-1" />뒤로
        </Button>
        <Building2 className="h-5 w-5 text-muted-foreground" />
        <h1 className="text-xl font-bold tracking-tight">{agency?.name ?? `기관 #${agencyId}`}</h1>
        <span className="text-sm text-muted-foreground">발주처 심층 분석</span>
      </div>

      {/* 핵심 지표 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="총 입찰공고" value={bidsData?.total?.toLocaleString() ?? '-'} unit="건" />
        <StatCard
          label="평균 낙찰률"
          value={agencyStat?.avg_rate != null ? (agencyStat.avg_rate * 100).toFixed(2) : '-'}
          unit="%"
        />
        <StatCard
          label="평균 경쟁업체"
          value={agencyStat?.avg_competitor_count != null ? agencyStat.avg_competitor_count.toFixed(1) : '-'}
          unit="개사"
        />
        <StatCard
          label="기관 사정율 중앙값"
          value={agencySrate?.srate_p50 != null ? (agencySrate.srate_p50 * 100).toFixed(3) : '-'}
          unit="%"
        />
      </div>

      {/* 탭 내비게이션 */}
      <div className="flex border-b">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={cn(
              'px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors',
              activeTab === tab
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* ── 개요 탭 ── */}
      {activeTab === '개요' && (
        <div className="space-y-5">
          {agencySrate && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">사정율 분포 (기관 vs 전국 평균)</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                  <SrateBox label="P25" value={agencySrate.srate_p25} global={globalSrate?.srate_p25 ?? null} />
                  <SrateBox label="중앙(P50)" value={agencySrate.srate_p50} global={globalSrate?.srate_p50 ?? null} highlight />
                  <SrateBox label="P75" value={agencySrate.srate_p75} global={globalSrate?.srate_p75 ?? null} />
                  <SrateBox label="평균" value={agencySrate.srate_mean} global={globalSrate?.srate_mean ?? null} />
                </div>
                <p className="text-xs text-muted-foreground">
                  표본 {agencySrate.sample_count}건 기준
                  {agencySrate.srate_trend != null && (
                    <span className={cn('ml-2', agencySrate.srate_trend > 0 ? 'text-blue-600' : 'text-red-500')}>
                      최근 추세 {agencySrate.srate_trend > 0 ? '▲' : '▼'} {Math.abs(agencySrate.srate_trend * 100).toFixed(3)}%
                    </span>
                  )}
                </p>
              </CardContent>
            </Card>
          )}

          {trendData.length >= 3 && (
            <Card>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm">낙찰률 흐름 (시계열)</CardTitle>
                  <div className="text-xs text-muted-foreground space-x-3">
                    {agencyMean != null && <span className="text-primary font-medium">기관 평균 {agencyMean}%</span>}
                    {globalMean != null && <span>전국 평균 {globalMean}%</span>}
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={180}>
                  <ComposedChart data={trendData} margin={{ left: -10, right: 10 }}>
                    <defs>
                      <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.15} />
                        <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0.02} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="date" tick={{ fontSize: 9 }} interval={Math.max(1, Math.floor(trendData.length / 8))} />
                    <YAxis tick={{ fontSize: 10 }} unit="%" domain={['auto', 'auto']} />
                    <Tooltip formatter={(v: number) => [v + '%', '낙찰률']} />
                    <Area type="monotone" dataKey="rate" fill="url(#areaGrad)" stroke="hsl(var(--primary))" strokeWidth={2} dot={{ r: 3, fill: 'hsl(var(--primary))' }} connectNulls />
                    {agencyMean != null && (
                      <ReferenceLine y={agencyMean} stroke="hsl(var(--primary))" strokeDasharray="4 2"
                        label={{ value: '기관평균', position: 'insideTopRight', fontSize: 9, fill: 'hsl(var(--primary))' }} />
                    )}
                    {globalMean != null && (
                      <ReferenceLine y={globalMean} stroke="hsl(var(--muted-foreground))" strokeDasharray="4 2"
                        label={{ value: '전국', position: 'insideTopLeft', fontSize: 9 }} />
                    )}
                  </ComposedChart>
                </ResponsiveContainer>
                {agencySrate?.srate_trend != null && (
                  <p className={cn('text-xs mt-1', agencySrate.srate_trend > 0 ? 'text-blue-600' : 'text-red-500')}>
                    최근 추세 {agencySrate.srate_trend > 0 ? '▲ 상승' : '▼ 하락'} {Math.abs(agencySrate.srate_trend * 100).toFixed(3)}%
                  </p>
                )}
              </CardContent>
            </Card>
          )}

          {rateDistData.some((d) => d.count > 0) && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">낙찰률 분포 (수집된 공고 기준)</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={150}>
                  <BarChart data={rateDistData} margin={{ top: 5, right: 10, bottom: 5, left: -20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="range" tick={{ fontSize: 9 }} interval={1} />
                    <YAxis tick={{ fontSize: 10 }} />
                    <Tooltip formatter={(v: number) => [`${v}건`, '건수']} />
                    <Bar dataKey="count" fill="hsl(var(--primary))" radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* ── 공고목록 탭 ── */}
      {activeTab === '공고목록' && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">입찰 공고 목록</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>공고명</TableHead>
                  <TableHead>공종</TableHead>
                  <TableHead className="text-right">기초금액</TableHead>
                  <TableHead>개찰일</TableHead>
                  <TableHead className="text-right">낙찰률</TableHead>
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
                      <TableRow key={b.id} className="cursor-pointer" onClick={() => navigate(`/bids/${b.id}`)}>
                        <TableCell className="max-w-xs">
                          <span className="truncate block font-medium text-primary text-sm">{b.title}</span>
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{b.industry_name ?? '-'}</TableCell>
                        <TableCell className="text-right whitespace-nowrap text-xs">{(b.base_amount / 1e8).toFixed(1)}억</TableCell>
                        <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                          {b.bid_open_date ? new Date(b.bid_open_date).toLocaleDateString('ko-KR') : '-'}
                        </TableCell>
                        <TableCell className="text-right font-mono font-semibold text-xs">
                          {b.winner_rate != null ? (b.winner_rate * 100).toFixed(2) + '%' : '-'}
                        </TableCell>
                      </TableRow>
                    ))}
              </TableBody>
            </Table>
            {bidsData && bidsData.total > 20 && (
              <div className="flex items-center justify-between px-4 py-3 border-t">
                <Button variant="outline" size="sm"
                  onClick={() => setBidPage((p) => Math.max(1, p - 1))} disabled={bidPage === 1}>
                  이전
                </Button>
                <span className="text-xs text-muted-foreground">{bidPage} / {totalPages} ({bidsData.total}건)</span>
                <Button variant="outline" size="sm"
                  onClick={() => setBidPage((p) => p + 1)} disabled={bidPage >= totalPages}>
                  다음
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
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <CardTitle className="text-sm">사정율 히스토그램</CardTitle>
                <div className="flex gap-1">
                  {([6, 12, 24] as const).map((m) => (
                    <button
                      key={m}
                      onClick={() => setHistMonths(m)}
                      className={cn(
                        'px-2.5 py-1 text-xs rounded border transition-colors',
                        histMonths === m
                          ? 'bg-primary text-primary-foreground border-primary'
                          : 'border-border text-muted-foreground hover:bg-muted',
                      )}
                    >
                      {m}개월
                    </button>
                  ))}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {histLoading ? (
                <Skeleton className="h-[200px] w-full" />
              ) : histogram && histogram.sample_count > 0 ? (
                <>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={histBins} margin={{ top: 5, right: 10, bottom: 5, left: -20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="label" tick={{ fontSize: 8 }} interval={3} />
                      <YAxis tick={{ fontSize: 10 }} />
                      <Tooltip
                        formatter={(v: number, _name: string, props: { payload?: { pct?: number } }) =>
                          [`${v}건 (${props.payload?.pct ?? 0}%)`, '건수']
                        }
                        labelFormatter={(label) => `사정율 ${label}%`}
                      />
                      <Bar dataKey="count" radius={[2, 2, 0, 0]}>
                        {histBins.map((entry, i) => (
                          <Cell
                            key={i}
                            fill={entry.belowFloor ? 'hsl(var(--destructive) / 0.35)' : 'hsl(var(--primary))'}
                          />
                        ))}
                      </Bar>
                      {histMeanLabel && (
                        <ReferenceLine x={histMeanLabel} stroke="hsl(var(--primary))" strokeDasharray="4 2"
                          label={{ value: '평균', position: 'insideTopRight', fontSize: 9 }} />
                      )}
                      {histP50Label && histP50Label !== histMeanLabel && (
                        <ReferenceLine x={histP50Label} stroke="#94a3b8" strokeDasharray="4 2"
                          label={{ value: '중앙', position: 'insideTopLeft', fontSize: 9 }} />
                      )}
                      {histFloorLabel && (
                        <ReferenceLine x={histFloorLabel} stroke="hsl(var(--destructive))" strokeWidth={1.5}
                          label={{ value: '낙찰하한', position: 'insideTop', fontSize: 8, fill: 'hsl(var(--destructive))' }} />
                      )}
                    </BarChart>
                  </ResponsiveContainer>
                  <p className="text-xs text-muted-foreground mt-1">
                    {histMonths}개월 기준 {histogram.sample_count}건
                    {histogram.mean != null && (
                      <span className="ml-2">
                        평균 <strong>{(histogram.mean * 100).toFixed(3)}%</strong>
                      </span>
                    )}
                    {histogram.std != null && (
                      <span className="ml-2">
                        σ=<strong>{(histogram.std * 100).toFixed(3)}%</strong>
                      </span>
                    )}
                  </p>
                </>
              ) : (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  {histLoading ? '로딩 중…' : `${histMonths}개월 내 낙찰 데이터 없음`}
                </p>
              )}
            </CardContent>
          </Card>

          {/* 개찰 타임라인 */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">개찰 타임라인 (사정율 추이)</CardTitle>
            </CardHeader>
            <CardContent>
              {recentLoading ? (
                <Skeleton className="h-[200px] w-full" />
              ) : tlN >= 2 ? (
                <>
                  <ResponsiveContainer width="100%" height={200}>
                    <ComposedChart data={timelineChartData} margin={{ left: -10, right: 10 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="date" tick={{ fontSize: 9 }}
                        interval={Math.max(0, Math.floor(tlN / 8) - 1)} />
                      <YAxis tick={{ fontSize: 10 }} unit="%" domain={['auto', 'auto']} />
                      <Tooltip formatter={(v: number) => [v + '%', '사정율']} />
                      {/* 산점도 효과 — 연결선 없이 점만 */}
                      <Line type="monotone" dataKey="rate"
                        dot={{ r: 3.5, fill: 'hsl(var(--primary))', strokeWidth: 0 }}
                        stroke="transparent" strokeWidth={0} connectNulls={false} />
                      {/* 추세선 */}
                      <Line type="linear" dataKey="trend" dot={false}
                        stroke="#ef4444" strokeDasharray="4 2" strokeWidth={1.5} />
                      {/* 평균선 */}
                      {tlMeanRate != null && (
                        <ReferenceLine y={tlMeanRate} stroke="hsl(var(--primary))" strokeDasharray="4 2"
                          label={{ value: `평균 ${tlMeanRate}%`, position: 'insideTopRight', fontSize: 9 }} />
                      )}
                      {/* 낙찰하한율 */}
                      <ReferenceLine y={+(FLOOR_RATE * 100).toFixed(3)} stroke="hsl(var(--destructive))"
                        strokeWidth={1.5}
                        label={{ value: '하한', position: 'insideBottomRight', fontSize: 9, fill: 'hsl(var(--destructive))' }} />
                    </ComposedChart>
                  </ResponsiveContainer>
                  <p className="text-xs text-muted-foreground mt-1">
                    {trendSlope > 0.05
                      ? '▲ 사정율 상승 추세'
                      : trendSlope < -0.05
                        ? '▼ 사정율 하락 추세'
                        : '→ 안정적'}
                    <span className="ml-2">
                      (기울기 {trendSlope > 0 ? '+' : ''}{trendSlope.toFixed(3)}%p/회차)
                    </span>
                  </p>
                </>
              ) : (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  {recentLoading ? '로딩 중…' : '개찰 결과 데이터 부족 (최소 2건 필요)'}
                </p>
              )}
            </CardContent>
          </Card>

          {/* 백분위수 요약 카드 */}
          {histogram && histogram.sample_count > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">백분위수 요약</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-3 md:grid-cols-5 gap-2">
                  {(['p10', 'p25', 'p50', 'p75', 'p90'] as const).map((key) => (
                    <div
                      key={key}
                      className={cn(
                        'rounded-md p-2 bg-muted/50 text-center',
                        key === 'p50' && 'bg-primary/10 border border-primary/30',
                      )}
                    >
                      <div className="text-xs text-muted-foreground">{key.toUpperCase()}</div>
                      <div className={cn('text-sm font-bold mt-0.5', key === 'p50' && 'text-primary')}>
                        {histogram.percentiles[key] != null
                          ? (histogram.percentiles[key]! * 100).toFixed(3) + '%'
                          : '-'}
                      </div>
                    </div>
                  ))}
                </div>
                {histogram.std != null && (
                  <div className="mt-3 flex flex-wrap gap-4 text-xs text-muted-foreground">
                    <span>표준편차: <strong>{(histogram.std * 100).toFixed(3)}%</strong></span>
                    <span>표본 수: <strong>{histogram.sample_count}건</strong></span>
                    {histogram.mean != null && (
                      <span>평균: <strong>{(histogram.mean * 100).toFixed(3)}%</strong></span>
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
        <div className="space-y-4">
          {!yegaPattern ? (
            <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">로딩 중…</CardContent></Card>
          ) : !yegaPattern.has_data ? (
            <Card>
              <CardContent className="py-10 text-center">
                <p className="text-sm text-muted-foreground">수집된 inpo21c 예가 데이터가 없습니다.</p>
                <p className="text-xs text-muted-foreground mt-1">인포21c에서 예가 데이터 수집 후 사용 가능합니다.</p>
              </CardContent>
            </Card>
          ) : (
            <>
              {/* 요약 카드 */}
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <Card>
                  <CardContent className="pt-4 pb-3">
                    <p className="text-xs text-muted-foreground">수집 공고 수</p>
                    <p className="text-lg font-bold">{yegaPattern.sample_n}건</p>
                    <p className="text-xs text-muted-foreground mt-0.5">inpo21c 실측</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4 pb-3">
                    <p className="text-xs text-muted-foreground">예가 후보 범위</p>
                    <p className="text-lg font-bold">±{(yegaPattern.spread_half * 100).toFixed(2)}%</p>
                    <p className="text-xs text-muted-foreground mt-0.5">기초금액 대비</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4 pb-3">
                    <p className="text-xs text-muted-foreground">선호 위치 TOP 3</p>
                    <p className="text-lg font-bold">
                      {yegaPattern.pos_weights
                        ? [...yegaPattern.pos_weights]
                            .map((w, i) => ({ pos: i + 1, w }))
                            .sort((a, b) => b.w - a.w)
                            .slice(0, 3)
                            .map((x) => `#${x.pos}`)
                            .join(' · ')
                        : '-'}
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">추첨 확률 상위</p>
                  </CardContent>
                </Card>
              </div>

              {/* 위치별 추첨 확률 막대차트 */}
              {yegaPattern.pos_weights && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">위치별 추첨 확률 (1~15번)</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={200}>
                      <BarChart
                        data={yegaPattern.pos_weights.map((w, i) => ({
                          pos: `${i + 1}번`,
                          pct: +(w * 100).toFixed(1),
                          isTop: w >= [...yegaPattern.pos_weights!].sort((a, b) => b - a)[2],
                        }))}
                        margin={{ top: 8, right: 8, left: -20, bottom: 0 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="pos" tick={{ fontSize: 10 }} />
                        <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `${v}%`} domain={[0, 12]} />
                        <Tooltip formatter={(v: number) => [`${v}%`, '추첨 확률']} />
                        <ReferenceLine y={+(1 / 15 * 100).toFixed(1)} stroke="#94a3b8"
                          strokeDasharray="4 2"
                          label={{ value: '균등 6.7%', position: 'insideTopRight', fontSize: 9, fill: '#94a3b8' }} />
                        <Bar dataKey="pct" radius={[3, 3, 0, 0]}>
                          {yegaPattern.pos_weights.map((w, i) => {
                            const top3Threshold = [...yegaPattern.pos_weights!].sort((a, b) => b - a)[2]
                            return <Cell key={i} fill={w >= top3Threshold ? '#2563eb' : '#93c5fd'} />
                          })}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                    <p className="text-xs text-muted-foreground mt-2 text-center">
                      파란 막대: 상위 3개 선호 위치 · 점선: 균등 확률 기준선
                    </p>
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

function StatCard({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <Card>
      <CardContent className="pt-4 pb-3">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-2xl font-bold mt-1">
          {value}
          <span className="text-sm font-normal text-muted-foreground ml-1">{unit}</span>
        </p>
      </CardContent>
    </Card>
  )
}

function SrateBox({
  label, value, global: globalVal, highlight
}: {
  label: string; value: number | null; global: number | null; highlight?: boolean
}) {
  const pct = (v: number | null) => v != null ? (v * 100).toFixed(3) + '%' : '-'
  const diff = value != null && globalVal != null ? value - globalVal : null
  return (
    <div className={cn('rounded-md p-2.5 bg-muted/50', highlight && 'bg-primary/10 border border-primary/30')}>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn('text-sm font-bold mt-0.5', highlight && 'text-primary')}>{pct(value)}</div>
      {diff != null && (
        <div className={cn('text-[10px] mt-0.5',
          diff > 0 ? 'text-blue-600' : diff < 0 ? 'text-red-500' : 'text-muted-foreground')}>
          전국 대비 {diff > 0 ? '+' : ''}{(diff * 100).toFixed(3)}%
        </div>
      )}
    </div>
  )
}
