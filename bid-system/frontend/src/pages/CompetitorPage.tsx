import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, ChevronLeft, ChevronRight, Trophy, CheckSquare, Square } from 'lucide-react'
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts'
import { competitorsApi } from '@/api'
import type { Competitor } from '@/types'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription
} from '@/components/ui/dialog'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table'

interface RivalItem { competitor_id: number; name: string; co_occurrence: number }
interface TrendItem { year: number; month: number; bid_count: number; win_count: number; avg_rate: number | null }
interface WinRecord {
  result_id: number; bid_id: number; title: string; agency_name: string
  base_amount: number; bid_open_date: string | null
  bid_amount: number; bid_rate: number | null; rank: number
}

export default function CompetitorPage() {
  const [keyword, setKeyword] = useState('')
  const [search, setSearch]   = useState('')
  const [page, setPage]       = useState(1)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [riskFilter, setRiskFilter] = useState('all')
  const [winnerOnly, setWinnerOnly] = useState(false)
  const [winsModalOpen, setWinsModalOpen] = useState(false)
  const SIZE = 15

  const { data: list, isLoading } = useQuery<{ items: Competitor[]; total: number }>({
    queryKey: ['competitors', search, page, riskFilter],
    queryFn: () => competitorsApi.list({
      keyword: search || undefined,
      page,
      size: SIZE,
      risk_level: riskFilter === 'all' ? undefined : riskFilter,
    }),
  })

  // 연속 낙찰 감지: 최근 trend 에서 연속 수주 개월 계산
  function consecutiveWins(trend: TrendItem[]): number {
    const sorted = [...trend].sort((a, b) => b.year * 12 + b.month - (a.year * 12 + a.month))
    let cnt = 0
    for (const t of sorted) { if (t.win_count > 0) cnt++; else break }
    return cnt
  }

  const filteredItems = winnerOnly
    ? (list?.items ?? []).filter((c) => c.win_rate > 0)
    : (list?.items ?? [])

  const { data: detail } = useQuery<Competitor>({
    queryKey: ['competitor', selectedId],
    queryFn: () => competitorsApi.detail(selectedId!),
    enabled: !!selectedId,
  })

  const { data: winHistory = [] } = useQuery<WinRecord[]>({
    queryKey: ['competitor-wins', selectedId],
    queryFn: () => competitorsApi.wins(selectedId!),
    enabled: !!selectedId && (detail?.win_count ?? 0) > 0,
  })


  const [detailTab, setDetailTab] = useState('overview')
  const [compareIds, setCompareIds] = useState<number[]>([])
  const [showCompare, setShowCompare] = useState(false)

  const { data: pattern } = useQuery({
    queryKey: ['competitor-pattern', selectedId],
    queryFn: () => competitorsApi.pattern(selectedId!),
    enabled: !!selectedId && detailTab === 'pattern',
  })

  const { data: compareData } = useQuery({
    queryKey: ['competitor-compare', compareIds],
    queryFn: () => competitorsApi.compare(compareIds),
    enabled: showCompare && compareIds.length === 2,
  })
  const totalPages = list ? Math.ceil(list.total / SIZE) : 1

  const riskVariant = (r: string): 'destructive' | 'warning' | 'success' | 'secondary' =>
    r === 'HIGH' ? 'destructive' : r === 'MEDIUM' ? 'warning' : r === 'LOW' ? 'success' : 'secondary'

  const radarData = detail ? [
    { subject: '공격성', value: detail.aggression_score  * 10 },
    { subject: '일관성', value: detail.consistency_score * 10 },
    { subject: '낙찰률', value: detail.win_rate          * 100 },
    { subject: '활동량', value: Math.min(detail.total_bids / 2, 100) },
    { subject: '안전성', value: Math.max(0, 100 - detail.aggression_score * 10) },
  ] : []

  const trendData = (detail?.monthly_trend as TrendItem[] ?? []).map((d) => ({
    label:  `${d.year}-${String(d.month).padStart(2,'0')}`,
    입찰수: d.bid_count,
    수주수: d.win_count,
    평균율: d.avg_rate ? +(d.avg_rate * 100).toFixed(2) : null,
  }))

  function handleSearch() { setSearch(keyword); setPage(1) }
  function handleSelect(id: number) { setSelectedId(id); setWinsModalOpen(false) }

  const fmtAmt = (v: number) => `${(v / 1e8).toFixed(2)}억`
  const fmtDate = (v: string | null) => v ? new Date(v).toLocaleDateString('ko-KR') : '-'

  const avgRate  = winHistory.length > 0 ? winHistory.reduce((s, w) => s + (w.bid_rate ?? 0), 0) / winHistory.length : 0
  const maxRate  = winHistory.length > 0 ? Math.max(...winHistory.map((w) => w.bid_rate ?? 0)) : 0
  const minRate  = winHistory.length > 0 ? Math.min(...winHistory.map((w) => w.bid_rate ?? 0)) : 0

  return (
    <div className="p-6 space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">경쟁사 분석</h1>
        <p className="text-muted-foreground text-sm mt-1">업체별 입찰 패턴 및 리스크 분석</p>
      </div>

      {/* 리스크 기준 안내 */}
      <Card>
        <CardContent className="py-3 px-4">
          <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
            <span><Badge variant="destructive" className="mr-1">HIGH</Badge> 리스크 점수 6+ (공격적·고수주율)</span>
            <span><Badge variant="warning" className="mr-1">MEDIUM</Badge> 점수 3~6</span>
            <span><Badge variant="success" className="mr-1">LOW</Badge> 점수 3 미만 (보수적·저수주율)</span>
          </div>
        </CardContent>
      </Card>

      <div className="flex gap-5">
        {/* 목록 패널 */}
        <div className="w-80 shrink-0 space-y-2">
          <div className="flex items-center gap-2">
            <Select value={riskFilter} onValueChange={(v) => { setRiskFilter(v); setPage(1) }}>
              <SelectTrigger className="flex-1"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">전체</SelectItem>
                <SelectItem value="HIGH">HIGH</SelectItem>
                <SelectItem value="MEDIUM">MEDIUM</SelectItem>
                <SelectItem value="LOW">LOW</SelectItem>
              </SelectContent>
            </Select>
            <Button
              size="sm"
              variant={winnerOnly ? 'default' : 'outline'}
              className="h-9 text-xs whitespace-nowrap gap-1"
              onClick={() => setWinnerOnly((v) => !v)}
            >
              <Trophy className="h-3 w-3" /> 낙찰만
            </Button>
          </div>

          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleSearch() }}
                placeholder="업체명 검색..."
                className="pl-8"
              />
            </div>
            <Button onClick={handleSearch} size="sm">검색</Button>
          </div>
          {compareIds.length === 2 && (
            <Button size="sm" className="w-full" onClick={() => setShowCompare(true)}>
              2개 업체 비교
            </Button>
          )}
          {compareIds.length > 0 && (
            <Button size="sm" variant="ghost" className="w-full text-xs text-muted-foreground" onClick={() => setCompareIds([])}>
              비교 선택 해제
            </Button>
          )}

          <Card className="overflow-hidden">
            {isLoading ? (
              <div className="p-4 space-y-2">
                {Array.from({length: 4}).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}
              </div>
            ) : (
              <div className="divide-y">
                {filteredItems.map((c) => {
                  const consec = consecutiveWins(c.monthly_trend as TrendItem[] ?? [])
                  return (
                    <div key={c.id}
                      className={cn('p-3 cursor-pointer hover:bg-accent transition-colors',
                        selectedId === c.id && 'bg-accent border-l-2 border-l-primary')}
                      onClick={() => handleSelect(c.id)}>
                      <div className="flex items-center gap-1.5 mb-1">
                        <button
                          className="shrink-0"
                          onClick={(e) => { e.stopPropagation(); setCompareIds((prev) => prev.includes(c.id) ? prev.filter((x) => x !== c.id) : prev.length < 2 ? [...prev, c.id] : prev) }}
                        >
                          {compareIds.includes(c.id) ? <CheckSquare className="h-3.5 w-3.5 text-primary" /> : <Square className="h-3.5 w-3.5 text-muted-foreground" />}
                        </button>
                        {consec >= 3 && (
                          <Badge variant="destructive" className="text-[9px] px-1 py-0">연속 {consec}개월 수주</Badge>
                        )}
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium truncate">{c.name}</span>
                        <Badge variant={riskVariant(c.risk_level)} className="shrink-0 ml-1 text-[10px] px-1.5 py-0">
                          {c.risk_level}
                        </Badge>
                      </div>
                      <div className="text-xs text-muted-foreground mt-0.5">
                        수주 {c.win_count}건 · 수주율 {(c.win_rate * 100).toFixed(1)}% · 평균 {(c.avg_bid_rate * 100).toFixed(2)}%
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
            <div className="flex items-center justify-between px-3 py-2 border-t bg-muted/30">
              <Button variant="outline" size="icon" className="h-7 w-7"
                onClick={() => setPage((p) => Math.max(1,p-1))} disabled={page===1}>
                <ChevronLeft className="h-3.5 w-3.5" />
              </Button>
              <span className="text-xs text-muted-foreground">{page}/{totalPages} ({list?.total ?? 0}개사)</span>
              <Button variant="outline" size="icon" className="h-7 w-7"
                onClick={() => setPage((p) => Math.min(totalPages,p+1))} disabled={page>=totalPages}>
                <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          </Card>
        </div>

        {/* 상세 패널 */}
        {detail ? (
          <div className="flex-1 space-y-4">
            <Tabs value={detailTab} onValueChange={setDetailTab}>
              <TabsList>
                <TabsTrigger value="overview">개요</TabsTrigger>
                <TabsTrigger value="pattern">투찰성향</TabsTrigger>
              </TabsList>

            <TabsContent value="overview" className="space-y-4 mt-3">
            {/* 기본 지표 */}
            <Card>
              <CardContent className="pt-5">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h2 className="text-lg font-bold">{detail.name}</h2>
                    <Badge variant={riskVariant(detail.risk_level)} className="mt-1">
                      리스크 {detail.risk_level}
                    </Badge>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <Metric label="총 입찰" value={detail.total_bids + '건'} />
                  {detail.win_count >= 1 ? (
                    <button
                      onClick={() => setWinsModalOpen(true)}
                      className="bg-muted/50 rounded-md p-2.5 w-full text-left hover:bg-yellow-50 transition-colors border border-transparent hover:border-yellow-200"
                    >
                      <div className="text-xs text-muted-foreground">수주 건수</div>
                      <div className="text-sm font-bold mt-0.5 text-yellow-600 flex items-center gap-1">
                        {detail.win_count}건 <Trophy className="h-3 w-3" />
                      </div>
                    </button>
                  ) : (
                    <Metric label="수주 건수" value={detail.win_count + '건'} />
                  )}
                  <Metric label="수주율"      value={(detail.win_rate * 100).toFixed(1) + '%'} />
                  <Metric label="평균 투찰률" value={(detail.avg_bid_rate * 100).toFixed(2) + '%'} />
                  <Metric label="공격성 점수" value={detail.aggression_score + '/10'} />
                  <Metric label="일관성 점수" value={(detail.consistency_score ?? 0).toFixed(1) + '/10'} />
                </div>
              </CardContent>
            </Card>

            {/* 레이더 + 자주 함께 */}
            <div className="grid grid-cols-2 gap-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">행동 패턴 레이더</CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={200}>
                    <RadarChart data={radarData}>
                      <PolarGrid />
                      <PolarAngleAxis dataKey="subject" tick={{ fontSize: 11 }} />
                      <Radar dataKey="value" stroke="hsl(var(--primary))" fill="hsl(var(--primary))" fillOpacity={0.3} />
                    </RadarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">자주 함께 참여하는 업체</CardTitle>
                </CardHeader>
                <CardContent className="space-y-1.5">
                  {(detail.frequent_rivals as RivalItem[] ?? []).slice(0, 7).map((r) => (
                    <div key={r.competitor_id} className="flex items-center justify-between">
                      <span className="text-sm truncate">{r.name}</span>
                      <Badge variant="secondary" className="shrink-0 ml-2">{r.co_occurrence}회</Badge>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </div>

            {/* 월별 추이 */}
            {trendData.length > 0 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">월별 활동 추이</CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={180}>
                    <LineChart data={trendData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="label" tick={{ fontSize: 10 }} interval={2} />
                      <YAxis yAxisId="l" tick={{ fontSize: 11 }} />
                      <YAxis yAxisId="r" orientation="right" tick={{ fontSize: 11 }} unit="%" />
                      <Tooltip />
                      <Line yAxisId="l" type="monotone" dataKey="입찰수" stroke="hsl(var(--muted-foreground))" strokeWidth={1} dot={false} />
                      <Line yAxisId="r" type="monotone" dataKey="평균율" stroke="hsl(var(--primary))" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            )}
            </TabsContent>

            <TabsContent value="pattern" className="space-y-4 mt-3">
              {pattern ? (
                <>
                  <div className="flex items-center gap-2">
                    {['aggressive','stable','defensive'].includes(pattern.recent_trend?.direction) && (
                      <Badge variant={pattern.recent_trend.direction === 'aggressive' ? 'destructive' : pattern.recent_trend.direction === 'defensive' ? 'success' : 'secondary'}>
                        {pattern.recent_trend.direction === 'aggressive' ? '공격적↑' : pattern.recent_trend.direction === 'defensive' ? '방어적↓' : '안정'}
                        {pattern.recent_trend.change_pct != null && ` (${pattern.recent_trend.change_pct > 0 ? '+' : ''}${pattern.recent_trend.change_pct.toFixed(1)}%)`}
                      </Badge>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <Card>
                      <CardHeader className="pb-2"><CardTitle className="text-sm">투찰 성향 레이더</CardTitle></CardHeader>
                      <CardContent>
                        <ResponsiveContainer width="100%" height={200}>
                          <RadarChart data={[
                            { subject: '공격성', value: pattern.radar.aggression },
                            { subject: '일관성', value: pattern.radar.consistency },
                            { subject: '집중도', value: pattern.radar.concentration },
                            { subject: '위험도', value: pattern.radar.risk },
                            { subject: '활동성', value: pattern.radar.activity },
                          ]}>
                            <PolarGrid />
                            <PolarAngleAxis dataKey="subject" tick={{ fontSize: 11 }} />
                            <PolarRadiusAxis domain={[0, 10]} tick={false} />
                            <Radar dataKey="value" stroke="hsl(var(--primary))" fill="hsl(var(--primary))" fillOpacity={0.35} />
                          </RadarChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardHeader className="pb-2"><CardTitle className="text-sm">금액대별 투찰 패턴</CardTitle></CardHeader>
                      <CardContent>
                        <ResponsiveContainer width="100%" height={200}>
                          <BarChart data={pattern.amount_pattern} margin={{ left: -10 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                            <XAxis dataKey="bucket" tick={{ fontSize: 10 }} />
                            <YAxis yAxisId="l" tick={{ fontSize: 11 }} />
                            <YAxis yAxisId="r" orientation="right" unit="%" tick={{ fontSize: 11 }} />
                            <Tooltip />
                            <Bar yAxisId="l" dataKey="bid_count" fill="hsl(var(--primary)/0.4)" name="입찰수" />
                            <Bar yAxisId="r" dataKey="win_rate" fill="hsl(142.1 76.2% 36.3%/0.6)" name="낙찰률" />
                          </BarChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>
                  </div>
                </>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-10">데이터를 불러오는 중...</p>
              )}
            </TabsContent>
            </Tabs>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-muted-foreground">
            목록에서 업체를 선택하세요
          </div>
        )}
      </div>

      {/* 2개 업체 비교 Dialog */}
      <Dialog open={showCompare} onOpenChange={(o) => { setShowCompare(o); if (!o) setCompareIds([]) }}>
        <DialogContent className="max-w-4xl max-h-[85vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>경쟁사 투찰 패턴 비교</DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              {compareData?.competitors?.map((c: { name: string }) => c.name).join(' vs ') ?? '...'}
            </DialogDescription>
          </DialogHeader>
          <div className="overflow-y-auto flex-1">
            {!compareData ? (
              <div className="py-16 text-center text-muted-foreground text-sm">데이터를 불러오는 중...</div>
            ) : (
              <div className="space-y-5 p-1">
                {/* 레이더 비교 */}
                <div className="grid grid-cols-2 gap-4">
                  {compareData.competitors.map((c: { id: number; name: string; radar: Record<string, number>; monthly_trend: { year_month: string; bid_count: number; win_count: number; avg_rate: number | null }[] }) => (
                    <Card key={c.id}>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm text-center">{c.name}</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <ResponsiveContainer width="100%" height={200}>
                          <RadarChart data={[
                            { subject: '공격성', value: c.radar.aggression ?? 0 },
                            { subject: '일관성', value: c.radar.consistency ?? 0 },
                            { subject: '집중도', value: c.radar.concentration ?? 0 },
                            { subject: '위험도', value: c.radar.risk ?? 0 },
                            { subject: '활동성', value: c.radar.activity ?? 0 },
                          ]}>
                            <PolarGrid />
                            <PolarAngleAxis dataKey="subject" tick={{ fontSize: 11 }} />
                            <PolarRadiusAxis domain={[0, 10]} tick={false} />
                            <Radar dataKey="value" stroke="hsl(var(--primary))" fill="hsl(var(--primary))" fillOpacity={0.3} />
                          </RadarChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>
                  ))}
                </div>

                {/* 월별 투찰 추이 비교 */}
                {compareData.competitors.length === 2 && (() => {
                  const c0 = compareData.competitors[0]
                  const c1 = compareData.competitors[1]
                  const allMonths = Array.from(new Set([
                    ...c0.monthly_trend.map((t: { year_month: string }) => t.year_month),
                    ...c1.monthly_trend.map((t: { year_month: string }) => t.year_month),
                  ])).sort()
                  const chartData = allMonths.map((ym) => {
                    const t0 = c0.monthly_trend.find((t: { year_month: string }) => t.year_month === ym)
                    const t1 = c1.monthly_trend.find((t: { year_month: string }) => t.year_month === ym)
                    return {
                      ym,
                      [c0.name]: t0?.avg_rate != null ? +(t0.avg_rate * 100).toFixed(3) : null,
                      [c1.name]: t1?.avg_rate != null ? +(t1.avg_rate * 100).toFixed(3) : null,
                    }
                  })
                  const COMPARE_COLORS = ['hsl(var(--primary))', '#f97316']
                  return (
                    <Card>
                      <CardHeader className="pb-2"><CardTitle className="text-sm">월별 평균 투찰률 추이 비교</CardTitle></CardHeader>
                      <CardContent>
                        <ResponsiveContainer width="100%" height={200}>
                          <LineChart data={chartData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                            <XAxis dataKey="ym" tick={{ fontSize: 9 }} interval={1} />
                            <YAxis tick={{ fontSize: 10 }} unit="%" domain={['auto', 'auto']} />
                            <Tooltip formatter={(v: number) => [v + '%', '']} />
                            {compareData.competitors.map((c: { name: string }, i: number) => (
                              <Line key={c.name} type="monotone" dataKey={c.name}
                                stroke={COMPARE_COLORS[i]} strokeWidth={2} dot={false} connectNulls />
                            ))}
                          </LineChart>
                        </ResponsiveContainer>
                        <div className="flex gap-4 text-xs mt-2">
                          {compareData.competitors.map((c: { name: string }, i: number) => (
                            <span key={c.name} className="flex items-center gap-1">
                              <span className="w-3 h-0.5 inline-block rounded" style={{ backgroundColor: COMPARE_COLORS[i] }} />
                              {c.name}
                            </span>
                          ))}
                        </div>
                      </CardContent>
                    </Card>
                  )
                })()}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* 수주 이력 Dialog */}
      <Dialog open={winsModalOpen} onOpenChange={setWinsModalOpen}>
        <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Trophy className="h-4 w-4 text-yellow-500" />
              {detail?.name} — 수주 이력 ({detail?.win_count}건)
            </DialogTitle>
          </DialogHeader>
          <div className="overflow-y-auto flex-1">
            {winHistory.length === 0 ? (
              <div className="p-10 text-center text-muted-foreground">불러오는 중...</div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>개찰일</TableHead>
                    <TableHead>수주 사업명</TableHead>
                    <TableHead>발주기관</TableHead>
                    <TableHead className="text-right">기초금액</TableHead>
                    <TableHead className="text-center">투찰률</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {winHistory.map((w) => (
                    <TableRow key={w.result_id} className="hover:bg-yellow-50/50">
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{fmtDate(w.bid_open_date)}</TableCell>
                      <TableCell className="max-w-[220px]">
                        <span className="block font-medium truncate text-xs" title={w.title}>{w.title}</span>
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-xs">{w.agency_name}</TableCell>
                      <TableCell className="text-right whitespace-nowrap text-xs">{fmtAmt(w.base_amount)}</TableCell>
                      <TableCell className="text-center">
                        <span className="font-mono font-bold text-primary text-sm">
                          {w.bid_rate ? (w.bid_rate * 100).toFixed(2) + '%' : '-'}
                        </span>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
          {winHistory.length > 0 && (
            <div className="border-t pt-3 flex gap-6 text-xs text-muted-foreground">
              <span>평균 투찰률 <strong className="text-primary text-sm">{(avgRate * 100).toFixed(2)}%</strong></span>
              <span>최고 <strong className="text-green-600">{(maxRate * 100).toFixed(2)}%</strong></span>
              <span>최저 <strong className="text-destructive">{(minRate * 100).toFixed(2)}%</strong></span>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-muted/50 rounded-md p-2.5">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-sm font-bold mt-0.5">{value}</div>
    </div>
  )
}