import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Handshake, Search, Shield, TrendingUp, Activity, Award, ChevronDown, ChevronUp } from 'lucide-react'
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer,
} from 'recharts'
import { competitorsApi, bidsApi } from '@/api'
import type { Competitor, MetaData } from '@/types'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'

/*
 * 공동도급 협정사 궁합 분석
 * 기존 경쟁사 데이터를 기반으로 잠재 협력사를 탐색하고 궁합 점수를 산출
 */

interface CompatScore {
  total: number        // 0~100
  stability: number   // 위험도 기반 (40점)
  performance: number // 낙찰 실적 (25점)
  consistency: number // 일관성 (20점)
  activity: number    // 활동성 (15점)
}

function calcCompat(c: Competitor, myTargetRate: number): CompatScore {
  // 안정성 (40점)
  const stabilityMap: Record<string, number> = { LOW: 40, MEDIUM: 24, HIGH: 8, UNKNOWN: 16 }
  const stability = stabilityMap[c.risk_level] ?? 16

  // 실적 (25점) — win_rate 최대 30%를 기준으로 정규화
  const performance = Math.min(c.win_rate / 0.3, 1) * 25

  // 일관성 (20점)
  const consistency = (c.consistency_score ?? 0) * 20

  // 활동성 (15점) — total_bids 50건 이상이면 만점
  const activity = Math.min(c.total_bids / 50, 1) * 15

  // 투찰률 범위 패널티: 상대방 평균과 내 목표율이 ±3% 초과 시 감점
  const rateDiff = Math.abs((c.avg_bid_rate ?? 0) - myTargetRate)
  const ratePenalty = rateDiff > 0.03 ? Math.min(rateDiff * 200, 15) : 0

  const total = Math.max(0, Math.min(100, stability + performance + consistency + activity - ratePenalty))
  return { total: +total.toFixed(1), stability: +stability.toFixed(1), performance: +performance.toFixed(1), consistency: +consistency.toFixed(1), activity: +activity.toFixed(1) }
}

function CompatBar({ score }: { score: number }) {
  const color = score >= 75 ? 'bg-green-500' : score >= 55 ? 'bg-yellow-400' : 'bg-red-400'
  return (
    <div className="flex items-center gap-2">
      <div className="w-24 h-2 rounded-full bg-muted overflow-hidden">
        <div className={cn('h-2 rounded-full transition-all', color)} style={{ width: `${score}%` }} />
      </div>
      <span className={cn('text-xs font-bold tabular-nums', score >= 75 ? 'text-green-700' : score >= 55 ? 'text-yellow-700' : 'text-red-600')}>
        {score}
      </span>
    </div>
  )
}

function RiskBadge({ level }: { level: string }) {
  const map: Record<string, { label: string; className: string }> = {
    LOW:     { label: '안정', className: 'bg-green-100 text-green-700 border-green-200' },
    MEDIUM:  { label: '보통', className: 'bg-yellow-100 text-yellow-700 border-yellow-200' },
    HIGH:    { label: '위험', className: 'bg-red-100 text-red-700 border-red-200' },
    UNKNOWN: { label: '미상', className: 'bg-gray-100 text-gray-500 border-gray-200' },
  }
  const m = map[level] ?? map.UNKNOWN
  return <span className={cn('text-[10px] px-1.5 py-0.5 rounded border font-medium', m.className)}>{m.label}</span>
}

export default function JointBidPage() {
  const [keyword, setKeyword] = useState('')
  const [search, setSearch] = useState('')
  const [myTargetRate, setMyTargetRate] = useState('90.5')
  const [minScore, setMinScore] = useState('50')
  const [riskFilter, setRiskFilter] = useState('all')
  const [sortBy, setSortBy] = useState<'compat' | 'win_rate' | 'total_bids'>('compat')
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 20

  const { data: meta } = useQuery<MetaData>({
    queryKey: ['meta'],
    queryFn: bidsApi.meta,
    staleTime: 300_000,
  })

  // 전체 경쟁사 목록 (최대 200건)
  const { data: listData, isLoading } = useQuery<{ items: Competitor[]; total: number }>({
    queryKey: ['joint-bid-competitors', search, riskFilter],
    queryFn: () => competitorsApi.list({
      keyword: search || undefined,
      page: 1,
      size: 200,
      risk_level: riskFilter === 'all' ? undefined : riskFilter,
    }),
  })

  const targetRate = Number(myTargetRate) / 100

  const scoredList = useMemo(() => {
    const items = listData?.items ?? []
    return items
      .map((c) => ({ ...c, _compat: calcCompat(c, targetRate) }))
      .filter((c) => c._compat.total >= Number(minScore))
      .sort((a, b) => {
        if (sortBy === 'compat') return b._compat.total - a._compat.total
        if (sortBy === 'win_rate') return b.win_rate - a.win_rate
        return b.total_bids - a.total_bids
      })
  }, [listData, targetRate, minScore, sortBy])

  const paginated = scoredList.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  const totalPages = Math.ceil(scoredList.length / PAGE_SIZE)

  const handleSearch = () => { setSearch(keyword); setPage(1) }

  // 상위 3사 평균 궁합
  const top3avg = scoredList.length > 0
    ? +(scoredList.slice(0, 3).reduce((s, c) => s + c._compat.total, 0) / Math.min(3, scoredList.length)).toFixed(1)
    : null

  return (
    <div className="p-6 space-y-6 max-w-5xl">
      {/* 헤더 */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <Handshake className="h-5 w-5 text-primary" />
          공동도급 협정사 탐색
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          경쟁사 데이터 기반 잠재 협력사 궁합 분석 — 안정성·실적·일관성·활동성 종합 평가
        </p>
      </div>

      {/* 필터 */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">탐색 조건</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div className="space-y-2 md:col-span-2">
              <Label>업체명 검색</Label>
              <div className="flex gap-2">
                <Input
                  placeholder="업체명 입력"
                  value={keyword}
                  onChange={(e) => setKeyword(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                />
                <Button size="sm" onClick={handleSearch} className="shrink-0">
                  <Search className="h-4 w-4" />
                </Button>
              </div>
            </div>

            <div className="space-y-2">
              <Label>내 목표 투찰률 (%)</Label>
              <Input
                type="number"
                step="0.1"
                min="85"
                max="100"
                value={myTargetRate}
                onChange={(e) => setMyTargetRate(e.target.value)}
                placeholder="예: 90.5"
              />
            </div>

            <div className="space-y-2">
              <Label>최소 궁합점수</Label>
              <Select value={minScore} onValueChange={(v) => { setMinScore(v); setPage(1) }}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="0">전체</SelectItem>
                  <SelectItem value="40">40점 이상</SelectItem>
                  <SelectItem value="55">55점 이상</SelectItem>
                  <SelectItem value="70">70점 이상</SelectItem>
                  <SelectItem value="80">80점 이상</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>위험등급 필터</Label>
              <Select value={riskFilter} onValueChange={(v) => { setRiskFilter(v); setPage(1) }}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">전체</SelectItem>
                  <SelectItem value="LOW">안정(LOW)</SelectItem>
                  <SelectItem value="MEDIUM">보통(MEDIUM)</SelectItem>
                  <SelectItem value="HIGH">위험(HIGH)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>정렬 기준</Label>
              <Select value={sortBy} onValueChange={(v) => setSortBy(v as typeof sortBy)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="compat">궁합점수 순</SelectItem>
                  <SelectItem value="win_rate">낙찰률 순</SelectItem>
                  <SelectItem value="total_bids">입찰건수 순</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* 요약 KPI */}
          {scoredList.length > 0 && (
            <div className="flex items-center gap-6 pt-3 border-t text-sm">
              <span className="text-muted-foreground">탐색 결과 <strong className="text-foreground">{scoredList.length}</strong>개사</span>
              {top3avg != null && (
                <span className="text-muted-foreground">상위 3사 평균 궁합 <strong className="text-primary">{top3avg}점</strong></span>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 궁합 점수 기준 안내 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { icon: Shield, label: '안정성', desc: '위험등급 기반', max: 40, color: 'text-blue-600' },
          { icon: Award, label: '낙찰 실적', desc: '낙찰률 정규화', max: 25, color: 'text-green-600' },
          { icon: Activity, label: '일관성', desc: '투찰률 변동성', max: 20, color: 'text-purple-600' },
          { icon: TrendingUp, label: '활동성', desc: '총 입찰건수', max: 15, color: 'text-orange-600' },
        ].map(({ icon: Icon, label, desc, max, color }) => (
          <Card key={label} className="py-0">
            <CardContent className="pt-3 pb-3">
              <div className="flex items-center gap-2 mb-1">
                <Icon className={cn('h-3.5 w-3.5', color)} />
                <span className="text-xs font-semibold">{label}</span>
                <span className="ml-auto text-xs text-muted-foreground">{max}점</span>
              </div>
              <p className="text-[11px] text-muted-foreground">{desc}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* 결과 테이블 */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">후보 협정사 목록</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8">#</TableHead>
                <TableHead>업체명</TableHead>
                <TableHead>위험</TableHead>
                <TableHead className="text-right">궁합점수</TableHead>
                <TableHead className="text-right">낙찰률</TableHead>
                <TableHead className="text-right">평균 투찰률</TableHead>
                <TableHead className="text-right">입찰건</TableHead>
                <TableHead className="w-8" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading
                ? Array.from({ length: 8 }).map((_, i) => (
                    <TableRow key={i}>
                      {Array.from({ length: 8 }).map((_, j) => (
                        <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
                      ))}
                    </TableRow>
                  ))
                : paginated.map((c, idx) => {
                    const rank = (page - 1) * PAGE_SIZE + idx + 1
                    const expanded = expandedId === c.id
                    const radarData = [
                      { subject: '안정성', value: +(c._compat.stability / 40 * 100).toFixed(0) },
                      { subject: '실적', value: +(c._compat.performance / 25 * 100).toFixed(0) },
                      { subject: '일관성', value: +(c._compat.consistency / 20 * 100).toFixed(0) },
                      { subject: '활동성', value: +(c._compat.activity / 15 * 100).toFixed(0) },
                    ]
                    return (
                      <>
                        <TableRow
                          key={c.id}
                          className="cursor-pointer hover:bg-muted/40"
                          onClick={() => setExpandedId(expanded ? null : c.id)}
                        >
                          <TableCell className="text-xs text-muted-foreground font-mono">{rank}</TableCell>
                          <TableCell>
                            <div className="flex items-center gap-2">
                              {rank <= 3 && <span className="text-[10px] font-bold text-primary">TOP</span>}
                              <span className="font-medium text-sm">{c.name}</span>
                            </div>
                          </TableCell>
                          <TableCell><RiskBadge level={c.risk_level} /></TableCell>
                          <TableCell className="text-right">
                            <CompatBar score={c._compat.total} />
                          </TableCell>
                          <TableCell className="text-right font-mono text-xs">
                            {(c.win_rate * 100).toFixed(1)}%
                          </TableCell>
                          <TableCell className="text-right font-mono text-xs">
                            {c.avg_bid_rate != null ? (c.avg_bid_rate * 100).toFixed(3) + '%' : '-'}
                          </TableCell>
                          <TableCell className="text-right text-xs">{c.total_bids}건</TableCell>
                          <TableCell>
                            {expanded
                              ? <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" />
                              : <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />}
                          </TableCell>
                        </TableRow>

                        {expanded && (
                          <TableRow key={`${c.id}-detail`} className="bg-muted/20">
                            <TableCell colSpan={8} className="py-4 px-6">
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                {/* 레이더 차트 */}
                                <div>
                                  <p className="text-xs font-semibold mb-2 text-muted-foreground">궁합 구성 (각 항목 / 만점 비율)</p>
                                  <ResponsiveContainer width="100%" height={180}>
                                    <RadarChart data={radarData} margin={{ top: 5, right: 20, bottom: 5, left: 20 }}>
                                      <PolarGrid stroke="hsl(var(--border))" />
                                      <PolarAngleAxis dataKey="subject" tick={{ fontSize: 11 }} />
                                      <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} axisLine={false} />
                                      <Radar dataKey="value" stroke="hsl(var(--primary))" fill="hsl(var(--primary))" fillOpacity={0.2} />
                                    </RadarChart>
                                  </ResponsiveContainer>
                                </div>

                                {/* 항목별 점수 */}
                                <div className="space-y-3">
                                  <p className="text-xs font-semibold text-muted-foreground">항목별 점수 (만점 기준)</p>
                                  {[
                                    { label: '안정성', score: c._compat.stability, max: 40 },
                                    { label: '낙찰 실적', score: c._compat.performance, max: 25 },
                                    { label: '일관성', score: c._compat.consistency, max: 20 },
                                    { label: '활동성', score: c._compat.activity, max: 15 },
                                  ].map(({ label, score, max }) => (
                                    <div key={label}>
                                      <div className="flex justify-between text-xs mb-1">
                                        <span>{label}</span>
                                        <span className="font-mono font-semibold">{score.toFixed(1)} / {max}</span>
                                      </div>
                                      <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                                        <div
                                          className="h-1.5 rounded-full bg-primary"
                                          style={{ width: `${(score / max) * 100}%` }}
                                        />
                                      </div>
                                    </div>
                                  ))}
                                  <div className="pt-2 border-t">
                                    <div className="flex items-center justify-between">
                                      <span className="text-xs font-semibold">총 궁합점수</span>
                                      <span className={cn(
                                        'text-lg font-bold',
                                        c._compat.total >= 75 ? 'text-green-700' : c._compat.total >= 55 ? 'text-yellow-700' : 'text-red-600'
                                      )}>
                                        {c._compat.total}점
                                      </span>
                                    </div>
                                    <p className="text-[10px] text-muted-foreground mt-0.5">
                                      P25~P75 투찰구간: {c.p25_rate != null ? (c.p25_rate * 100).toFixed(3) : '-'}% ~ {c.p75_rate != null ? (c.p75_rate * 100).toFixed(3) : '-'}%
                                    </p>
                                  </div>
                                </div>
                              </div>
                            </TableCell>
                          </TableRow>
                        )}
                      </>
                    )
                  })}

              {!isLoading && paginated.length === 0 && (
                <TableRow>
                  <TableCell colSpan={8} className="text-center py-8 text-muted-foreground text-sm">
                    조건에 맞는 업체가 없습니다. 필터를 조정해보세요.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>

          {totalPages > 1 && (
            <div className="flex items-center justify-between px-4 py-3 border-t">
              <Button variant="outline" size="sm"
                onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>이전</Button>
              <span className="text-xs text-muted-foreground">{page} / {totalPages} ({scoredList.length}개사)</span>
              <Button variant="outline" size="sm"
                onClick={() => setPage((p) => p + 1)} disabled={page >= totalPages}>다음</Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 안내 */}
      <p className="text-xs text-muted-foreground">
        * 궁합점수는 수집된 입찰 데이터 기반 참고 지표입니다. 실제 협정 체결 전 재무상태·면허 등을 반드시 확인하세요.
      </p>
    </div>
  )
}
