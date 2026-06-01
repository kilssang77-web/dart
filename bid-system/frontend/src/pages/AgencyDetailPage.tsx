import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, Building2 } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts'
import { bidsApi, recommendApi, statsApi } from '@/api'
import type { MetaData } from '@/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table'

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

export default function AgencyDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const agencyId = Number(id)
  const [bidPage, setBidPage] = useState(1)

  const { data: meta } = useQuery<MetaData>({
    queryKey: ['meta'],
    queryFn: bidsApi.meta,
    staleTime: 300_000,
  })
  const agency = meta?.agencies.find((a) => a.id === agencyId)

  const { data: bidsData, isLoading: bidsLoading } = useQuery<{ items: { id: number; title: string; industry_name: string | null; base_amount: number; bid_open_date: string | null; winner_rate: number | null; status: string }[]; total: number }>({
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

  const agencyStat = agencyStatsList.find((a) => a.agency_id === agencyId)
  const agencySrate = srateStats.find((s) => s.group_type === 'agency')
  const globalSrate = srateStats.find((s) => s.group_type === 'global')

  const closedBids = (bidsData?.items ?? []).filter((b) => b.winner_rate != null)
  const rateDistData = buildRateDist(closedBids)
  const totalPages = bidsData ? Math.ceil(bidsData.total / 20) : 1

  return (
    <div className="p-6 space-y-5">
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

      {/* 사정율 분포 */}
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

      {/* 낙찰률 분포 차트 */}
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

      {/* 입찰 목록 */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">최근 입찰 공고</CardTitle>
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
