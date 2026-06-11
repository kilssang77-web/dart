import { useState, useRef, useEffect } from 'react'
import { useQuery, useQueries } from '@tanstack/react-query'
import { Search, ChevronLeft, ChevronRight, Trophy, CheckSquare, Square, Target, Loader2, Users, ShieldAlert } from 'lucide-react'
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  LineChart, Line, BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts'
import { competitorsApi, bidsApi } from '@/api'
import type { Competitor, CompetitorZoneItem, BidZonePredItem, CompetitorPredictResponse, BidSearchItem } from '@/types'
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
  const [zonesDays, setZonesDays] = useState<90 | 180>(90)

  // 공고 예측 상태
  const [selectedBid, setSelectedBid] = useState<BidSearchItem | null>(null)
  const [bidSearchInput, setBidSearchInput] = useState('')
  const [bidSearchQuery, setBidSearchQuery] = useState('')
  const [showBidDropdown, setShowBidDropdown] = useState(false)
  const [showBatchAnalysis, setShowBatchAnalysis] = useState(false)
  const bidSearchRef = useRef<HTMLDivElement>(null)

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

  const { data: zonesData } = useQuery({
    queryKey: ['competitor-zones', selectedId, zonesDays],
    queryFn: () => competitorsApi.zones(selectedId!, zonesDays),
    enabled: !!selectedId && detailTab === 'zones',
  })

  const { data: bidSearchResults = [] } = useQuery<BidSearchItem[]>({
    queryKey: ['bid-search-predict', bidSearchQuery],
    queryFn: () => bidsApi.search(bidSearchQuery),
    enabled: bidSearchQuery.length >= 2,
  })

  const { data: predictData, isLoading: predictLoading } = useQuery<CompetitorPredictResponse>({
    queryKey: ['competitor-predict', selectedId, selectedBid?.id],
    queryFn: () => competitorsApi.predict(selectedId!, selectedBid!.id),
    enabled: !!selectedId && !!selectedBid && detailTab === 'predict',
  })

  const totalPages = list ? Math.ceil(list.total / SIZE) : 1

  // 드롭다운 외부 클릭 시 닫기
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (bidSearchRef.current && !bidSearchRef.current.contains(e.target as Node)) {
        setShowBidDropdown(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  function handleBidSearchChange(val: string) {
    setBidSearchInput(val)
    if (val.length >= 2) {
      setBidSearchQuery(val)
      setShowBidDropdown(true)
    } else {
      setShowBidDropdown(false)
    }
  }

  function handleBidSelect(bid: BidSearchItem) {
    setSelectedBid(bid)
    setBidSearchInput(bid.announcement_no)
    setShowBidDropdown(false)
  }

  const riskVariant = (r: string): 'destructive' | 'warning' | 'success' | 'secondary' =>
    r === 'HIGH' ? 'destructive' : r === 'MEDIUM' ? 'warning' : r === 'LOW' ? 'success' : 'secondary'

  // 위험도 색상 클래스
  const riskColorClass = (r: string) =>
    r === 'HIGH'
      ? 'bg-red-50 text-red-700 border-red-200'
      : r === 'MEDIUM'
      ? 'bg-amber-50 text-amber-700 border-amber-200'
      : r === 'LOW'
      ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
      : 'bg-slate-100 text-slate-500 border-slate-200'

  const riskTopBarColor = (r: string) =>
    r === 'HIGH' ? 'bg-red-500' : r === 'MEDIUM' ? 'bg-amber-400' : r === 'LOW' ? 'bg-emerald-500' : 'bg-slate-300'

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
    <div className="min-h-screen bg-slate-50">
      {/* 스티키 헤더 */}
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-sm border-b border-slate-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-slate-900 flex items-center gap-2">
              <ShieldAlert className="h-5 w-5 text-purple-600" />
              경쟁사 분석
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">업체별 입찰 패턴 및 리스크 분석</p>
          </div>
          <div className="flex items-center gap-2">
            {compareIds.length === 2 && (
              <Button size="sm" className="h-8 text-xs gap-1.5 bg-purple-600 hover:bg-purple-700" onClick={() => setShowCompare(true)}>
                <Users className="h-3.5 w-3.5" />
                2개 업체 비교
              </Button>
            )}
            {compareIds.length > 0 && (
              <Button size="sm" variant="ghost" className="h-8 text-xs text-slate-500" onClick={() => setCompareIds([])}>
                선택 해제
              </Button>
            )}
          </div>
        </div>
      </div>

      <div className="p-6 space-y-4">
        {/* 리스크 기준 + 예측 공고 선택 */}
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardContent className="py-3 px-4">
            <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
              {/* 위험도 범례 */}
              <div className="flex items-center gap-4 text-xs text-slate-500">
                <span className="font-medium text-slate-700">위험도 기준</span>
                <span className="flex items-center gap-1">
                  <span className="inline-block w-2 h-2 rounded-full bg-red-500" />
                  <span className="font-medium text-red-700">HIGH</span> 공격적·고수주
                </span>
                <span className="flex items-center gap-1">
                  <span className="inline-block w-2 h-2 rounded-full bg-amber-400" />
                  <span className="font-medium text-amber-700">MEDIUM</span> 점수 3~6
                </span>
                <span className="flex items-center gap-1">
                  <span className="inline-block w-2 h-2 rounded-full bg-emerald-500" />
                  <span className="font-medium text-emerald-700">LOW</span> 보수적·저수주
                </span>
              </div>

              {/* 구분선 */}
              <div className="hidden md:block w-px h-5 bg-slate-200" />

              {/* 예측 대상 공고 */}
              <div className="flex items-center gap-2 flex-1 min-w-[320px]">
                <Target className="h-4 w-4 text-purple-500 shrink-0" />
                <span className="text-sm font-medium text-slate-600 whitespace-nowrap">예측 공고</span>
                <div className="relative flex-1" ref={bidSearchRef}>
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" />
                  <Input
                    value={bidSearchInput}
                    onChange={(e) => handleBidSearchChange(e.target.value)}
                    onFocus={() => bidSearchInput.length >= 2 && setShowBidDropdown(true)}
                    placeholder="공고번호 입력 (2자 이상)..."
                    className="pl-8 h-8 text-xs border-slate-200 bg-slate-50 focus:bg-white"
                  />
                  {showBidDropdown && bidSearchResults.length > 0 && (
                    <div className="absolute top-full left-0 right-0 z-50 bg-white border border-slate-200 rounded-lg shadow-lg mt-1 max-h-48 overflow-y-auto">
                      {bidSearchResults.map((b) => (
                        <button
                          key={b.id}
                          className="w-full text-left px-3 py-2 text-xs hover:bg-slate-50 border-b border-slate-100 last:border-0"
                          onClick={() => handleBidSelect(b)}
                        >
                          <span className="font-mono text-purple-600">{b.announcement_no}</span>
                          <span className="ml-2 text-slate-500 truncate">{b.title}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                {selectedBid && (
                  <>
                    <Badge className="bg-purple-50 text-purple-700 border-purple-200 text-xs max-w-[200px] truncate border">
                      {selectedBid.title}
                    </Badge>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs border-slate-200"
                      onClick={() => { setSelectedBid(null); setBidSearchInput('') }}
                    >
                      초기화
                    </Button>
                    <Button
                      size="sm"
                      className="h-7 text-xs gap-1 bg-purple-600 hover:bg-purple-700"
                      onClick={() => setShowBatchAnalysis(true)}
                      disabled={!list?.items?.length}
                    >
                      <Target className="h-3 w-3" />
                      일괄 분석
                    </Button>
                  </>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="flex gap-5">
          {/* 목록 패널 */}
          <div className="w-72 shrink-0 space-y-2">
            {/* 필터 */}
            <div className="flex items-center gap-2">
              <Select value={riskFilter} onValueChange={(v) => { setRiskFilter(v); setPage(1) }}>
                <SelectTrigger className="flex-1 h-9 border-slate-200 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">전체 위험도</SelectItem>
                  <SelectItem value="HIGH">HIGH</SelectItem>
                  <SelectItem value="MEDIUM">MEDIUM</SelectItem>
                  <SelectItem value="LOW">LOW</SelectItem>
                </SelectContent>
              </Select>
              <Button
                size="sm"
                variant={winnerOnly ? 'default' : 'outline'}
                className={cn('h-9 text-xs whitespace-nowrap gap-1 border-slate-200',
                  winnerOnly && 'bg-amber-500 hover:bg-amber-600 border-amber-500')}
                onClick={() => setWinnerOnly((v) => !v)}
              >
                <Trophy className="h-3 w-3" /> 낙찰만
              </Button>
            </div>

            {/* 검색 */}
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" />
                <Input
                  value={keyword}
                  onChange={(e) => setKeyword(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleSearch() }}
                  placeholder="업체명 검색..."
                  className="pl-8 border-slate-200"
                />
              </div>
              <Button onClick={handleSearch} size="sm" className="bg-slate-800 hover:bg-slate-900">검색</Button>
            </div>

            {/* 경쟁사 목록 카드 */}
            <Card className="overflow-hidden bg-white border-slate-200 shadow-sm">
              {isLoading ? (
                <div className="p-3 space-y-2">
                  {Array.from({length: 5}).map((_, i) => <Skeleton key={i} className="h-14 w-full rounded-lg" />)}
                </div>
              ) : (
                <div className="divide-y divide-slate-100">
                  {filteredItems.map((c) => {
                    const consec = consecutiveWins(c.monthly_trend as TrendItem[] ?? [])
                    const isSelected = selectedId === c.id
                    return (
                      <div key={c.id}
                        className={cn(
                          'p-3 cursor-pointer transition-colors group',
                          isSelected
                            ? 'bg-purple-50 border-l-2 border-l-purple-500'
                            : 'hover:bg-slate-50 border-l-2 border-l-transparent'
                        )}
                        onClick={() => handleSelect(c.id)}>
                        <div className="flex items-center gap-1.5 mb-1.5">
                          <button
                            className="shrink-0 rounded hover:bg-slate-100 p-0.5"
                            onClick={(e) => { e.stopPropagation(); setCompareIds((prev) => prev.includes(c.id) ? prev.filter((x) => x !== c.id) : prev.length < 2 ? [...prev, c.id] : prev) }}
                          >
                            {compareIds.includes(c.id)
                              ? <CheckSquare className="h-3.5 w-3.5 text-purple-600" />
                              : <Square className="h-3.5 w-3.5 text-slate-300" />}
                          </button>
                          {consec >= 3 && (
                            <span className="inline-flex items-center text-[9px] px-1.5 py-0.5 rounded-full bg-red-50 text-red-600 font-semibold border border-red-100">
                              연속 {consec}개월 수주
                            </span>
                          )}
                        </div>
                        <div className="flex items-center justify-between gap-2">
                          <span className={cn('text-sm font-semibold truncate transition-colors',
                            isSelected ? 'text-purple-800' : 'text-slate-800 group-hover:text-purple-700')}>
                            {c.name}
                          </span>
                          <span className={cn('text-xs px-1.5 py-0.5 rounded border font-semibold shrink-0', riskColorClass(c.risk_level))}>
                            {c.risk_level}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 mt-1.5">
                          <span className="text-xs text-slate-500">수주율</span>
                          <div className="flex-1 h-1 bg-slate-100 rounded-full">
                            <div
                              className={cn('h-1 rounded-full', c.risk_level === 'HIGH' ? 'bg-red-400' : c.risk_level === 'MEDIUM' ? 'bg-amber-400' : 'bg-emerald-400')}
                              style={{ width: `${Math.min(c.win_rate * 100 * 3, 100)}%` }}
                            />
                          </div>
                          <span className="text-xs font-semibold text-slate-600 tabular-nums">
                            {(c.win_rate * 100).toFixed(1)}%
                          </span>
                        </div>
                        <div className="text-xs text-slate-500 mt-0.5">
                          수주 {c.win_count}건 · 평균 {(c.avg_bid_rate * 100).toFixed(2)}%
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
              <div className="flex items-center justify-between px-3 py-2 border-t border-slate-100 bg-slate-50/80">
                <Button variant="outline" size="icon" className="h-7 w-7 border-slate-200"
                  onClick={() => setPage((p) => Math.max(1,p-1))} disabled={page===1}>
                  <ChevronLeft className="h-3.5 w-3.5" />
                </Button>
                <span className="text-xs text-slate-500 tabular-nums">{page}/{totalPages} ({list?.total ?? 0}개사)</span>
                <Button variant="outline" size="icon" className="h-7 w-7 border-slate-200"
                  onClick={() => setPage((p) => Math.min(totalPages,p+1))} disabled={page>=totalPages}>
                  <ChevronRight className="h-3.5 w-3.5" />
                </Button>
              </div>
            </Card>
          </div>

          {/* 상세 패널 */}
          {detail ? (
            <div className="flex-1 space-y-4 min-w-0">
              <Tabs value={detailTab} onValueChange={setDetailTab}>
                <TabsList className="bg-slate-100 border border-slate-200">
                  <TabsTrigger value="overview" className="text-xs">개요</TabsTrigger>
                  <TabsTrigger value="pattern" className="text-xs">투찰성향</TabsTrigger>
                  <TabsTrigger value="zones" className="text-xs">투찰구간</TabsTrigger>
                  <TabsTrigger value="predict" disabled={!selectedBid} className="gap-1 text-xs">
                    <Target className="h-3 w-3" />
                    예측{!selectedBid && <span className="text-xs opacity-40 ml-0.5">(공고선택)</span>}
                  </TabsTrigger>
                </TabsList>

              <TabsContent value="overview" className="space-y-4 mt-3">
                {/* 업체 헤더 카드 */}
                <Card className="relative overflow-hidden bg-white border-slate-200 shadow-sm">
                  <div className={cn('absolute top-0 left-0 right-0 h-1', riskTopBarColor(detail.risk_level))} />
                  <CardContent className="pt-5 pb-4">
                    <div className="flex items-start justify-between mb-4">
                      <div>
                        <h2 className="text-lg font-bold text-slate-900">{detail.name}</h2>
                        <span className={cn('inline-flex items-center text-xs px-2 py-0.5 rounded-full border font-semibold mt-1.5', riskColorClass(detail.risk_level))}>
                          리스크 {detail.risk_level}
                        </span>
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-2.5">
                      <MetricCard label="총 입찰" value={detail.total_bids + '건'} />
                      {detail.win_count >= 1 ? (
                        <button
                          onClick={() => setWinsModalOpen(true)}
                          className="relative overflow-hidden rounded-xl bg-amber-50 border border-amber-100 p-3 text-left hover:bg-amber-100 transition-colors group"
                        >
                          <div className="text-xs text-amber-600 font-medium">수주 건수</div>
                          <div className="text-xl font-bold mt-0.5 text-amber-700 flex items-center gap-1">
                            {detail.win_count}건 <Trophy className="h-4 w-4 group-hover:scale-110 transition-transform" />
                          </div>
                          <div className="text-xs text-amber-500 mt-0.5">클릭하여 이력 보기</div>
                        </button>
                      ) : (
                        <MetricCard label="수주 건수" value={detail.win_count + '건'} />
                      )}
                      <MetricCard label="수주율" value={(detail.win_rate * 100).toFixed(1) + '%'} highlight />
                      <MetricCard label="평균 투찰률" value={(detail.avg_bid_rate * 100).toFixed(2) + '%'} />
                      <MetricCard label="공격성 점수" value={detail.aggression_score + '/10'} />
                      <MetricCard label="일관성 점수" value={(detail.consistency_score ?? 0).toFixed(1) + '/10'} />
                    </div>
                  </CardContent>
                </Card>

                {/* 레이더 + 자주 함께 */}
                <div className="grid grid-cols-2 gap-4">
                  <Card className="bg-white border-slate-200 shadow-sm">
                    <CardHeader className="pb-1 pt-4 px-4">
                      <CardTitle className="text-sm font-semibold text-slate-800">행동 패턴 레이더</CardTitle>
                    </CardHeader>
                    <CardContent className="px-4 pb-4">
                      <ResponsiveContainer width="100%" height={200}>
                        <RadarChart data={radarData}>
                          <PolarGrid stroke="#e2e8f0" />
                          <PolarAngleAxis dataKey="subject" tick={{ fontSize: 12, fill: '#64748b' }} />
                          <Radar dataKey="value" stroke="#7c3aed" fill="#7c3aed" fillOpacity={0.2} strokeWidth={2} />
                        </RadarChart>
                      </ResponsiveContainer>
                    </CardContent>
                  </Card>

                  <Card className="bg-white border-slate-200 shadow-sm">
                    <CardHeader className="pb-1 pt-4 px-4">
                      <CardTitle className="text-sm font-semibold text-slate-800">자주 함께 참여하는 업체</CardTitle>
                    </CardHeader>
                    <CardContent className="px-4 pb-4 space-y-1.5">
                      {(detail.frequent_rivals as RivalItem[] ?? []).slice(0, 7).map((r) => (
                        <div key={r.competitor_id} className="flex items-center justify-between py-1 border-b border-slate-50 last:border-0">
                          <span className="text-sm text-slate-700 truncate">{r.name}</span>
                          <span className="text-xs font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full shrink-0 ml-2 tabular-nums">
                            {r.co_occurrence}회
                          </span>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                </div>

                {/* 월별 추이 */}
                {trendData.length > 0 && (
                  <Card className="bg-white border-slate-200 shadow-sm">
                    <CardHeader className="pb-1 pt-4 px-4">
                      <CardTitle className="text-sm font-semibold text-slate-800">월별 활동 추이</CardTitle>
                    </CardHeader>
                    <CardContent className="px-4 pb-4">
                      <ResponsiveContainer width="100%" height={240}>
                        <LineChart data={trendData}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                          <XAxis dataKey="label" tick={{ fontSize: 12, fill: '#475569' }} interval={2} />
                          <YAxis yAxisId="l" tick={{ fontSize: 12, fill: '#475569' }} />
                          <YAxis yAxisId="r" orientation="right" tick={{ fontSize: 12, fill: '#475569' }} unit="%" />
                          <Tooltip contentStyle={{ border: '1px solid #e2e8f0', borderRadius: '8px', fontSize: '12px' }} />
                          <Line yAxisId="l" type="monotone" dataKey="입찰수" stroke="#cbd5e1" strokeWidth={1} dot={false} />
                          <Line yAxisId="r" type="monotone" dataKey="평균율" stroke="#7c3aed" strokeWidth={2} dot={false} />
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
                      <Card className="bg-white border-slate-200 shadow-sm">
                        <CardHeader className="pb-1 pt-4 px-4"><CardTitle className="text-sm font-semibold text-slate-800">투찰 성향 레이더</CardTitle></CardHeader>
                        <CardContent className="px-4 pb-4">
                          <ResponsiveContainer width="100%" height={200}>
                            <RadarChart data={[
                              { subject: '공격성', value: pattern.radar.aggression },
                              { subject: '일관성', value: pattern.radar.consistency },
                              { subject: '집중도', value: pattern.radar.concentration },
                              { subject: '위험도', value: pattern.radar.risk },
                              { subject: '활동성', value: pattern.radar.activity },
                            ]}>
                              <PolarGrid stroke="#e2e8f0" />
                              <PolarAngleAxis dataKey="subject" tick={{ fontSize: 12, fill: '#64748b' }} />
                              <PolarRadiusAxis domain={[0, 10]} tick={false} />
                              <Radar dataKey="value" stroke="#7c3aed" fill="#7c3aed" fillOpacity={0.2} strokeWidth={2} />
                            </RadarChart>
                          </ResponsiveContainer>
                        </CardContent>
                      </Card>
                      <Card className="bg-white border-slate-200 shadow-sm">
                        <CardHeader className="pb-1 pt-4 px-4"><CardTitle className="text-sm font-semibold text-slate-800">금액대별 투찰 패턴</CardTitle></CardHeader>
                        <CardContent className="px-4 pb-4">
                          <ResponsiveContainer width="100%" height={200}>
                            <BarChart data={pattern.amount_pattern} margin={{ left: -10 }}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                              <XAxis dataKey="bucket" tick={{ fontSize: 12, fill: '#475569' }} />
                              <YAxis yAxisId="l" tick={{ fontSize: 12, fill: '#475569' }} />
                              <YAxis yAxisId="r" orientation="right" unit="%" tick={{ fontSize: 12, fill: '#475569' }} />
                              <Tooltip contentStyle={{ border: '1px solid #e2e8f0', borderRadius: '8px', fontSize: '12px' }} />
                              <Bar yAxisId="l" dataKey="bid_count" fill="#c4b5fd" name="입찰수" radius={[3, 3, 0, 0]} />
                              <Bar yAxisId="r" dataKey="win_rate" fill="#10b981" name="낙찰률" radius={[3, 3, 0, 0]} />
                            </BarChart>
                          </ResponsiveContainer>
                        </CardContent>
                      </Card>
                    </div>
                  </>
                ) : (
                  <div className="flex items-center justify-center py-16 text-slate-500 text-sm">
                    <Loader2 className="h-5 w-5 animate-spin mr-2" />데이터를 불러오는 중...
                  </div>
                )}
              </TabsContent>

              <TabsContent value="zones" className="space-y-4 mt-3">
                <div className="flex items-center justify-between">
                  <div className="flex gap-1.5">
                    {([90, 180] as const).map((d) => (
                      <Button
                        key={d}
                        size="sm"
                        variant={zonesDays === d ? 'default' : 'outline'}
                        className={cn('h-7 text-xs border-slate-200',
                          zonesDays === d && 'bg-purple-600 hover:bg-purple-700')}
                        onClick={() => setZonesDays(d)}
                      >
                        {d}일
                      </Button>
                    ))}
                  </div>
                  {zonesData && (
                    <span className="text-xs text-slate-500">총 {zonesData.total_count.toLocaleString()}건 기준</span>
                  )}
                </div>

                {!zonesData ? (
                  <div className="flex items-center justify-center py-16 text-slate-500 text-sm">
                    <Loader2 className="h-5 w-5 animate-spin mr-2" />데이터를 불러오는 중...
                  </div>
                ) : zonesData.total_count === 0 ? (
                  <Card className="bg-white border-slate-200">
                    <CardContent className="py-12 text-center text-sm text-slate-500">
                      inpo21c 데이터 없음 — 해당 경쟁사의 수집 데이터가 없습니다
                    </CardContent>
                  </Card>
                ) : (
                  <>
                    {zonesData.peak_zone && (
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="inline-flex items-center text-xs px-2.5 py-1 rounded-full bg-red-50 text-red-700 border border-red-200 font-medium">
                          피크 구간 {(zonesData.peak_zone.range_lo * 100).toFixed(1)}%~{(zonesData.peak_zone.range_hi * 100).toFixed(1)}%
                          ({zonesData.peak_zone.pct}%)
                        </span>
                        <span className="inline-flex items-center text-xs px-2.5 py-1 rounded-full bg-amber-50 text-amber-700 border border-amber-200 font-medium">
                          이 구간 회피 추천
                        </span>
                      </div>
                    )}
                    <Card className="bg-white border-slate-200 shadow-sm">
                      <CardHeader className="pb-1 pt-4 px-4">
                        <CardTitle className="text-sm font-semibold text-slate-800">사정율 구간별 투찰 빈도</CardTitle>
                      </CardHeader>
                      <CardContent className="px-4 pb-4">
                        <ResponsiveContainer width="100%" height={260}>
                          <BarChart
                            data={zonesData.zones.map((z: CompetitorZoneItem) => ({
                              label: `${(z.range_lo * 100).toFixed(1)}`,
                              pct: z.pct,
                              isPeak: zonesData.peak_zone
                                ? z.range_lo === zonesData.peak_zone.range_lo
                                : false,
                            }))}
                            margin={{ left: -10 }}
                          >
                            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                            <XAxis dataKey="label" tick={{ fontSize: 12, fill: '#475569' }} interval={3} unit="%" />
                            <YAxis tick={{ fontSize: 12, fill: '#475569' }} unit="%" />
                            <Tooltip
                              contentStyle={{ border: '1px solid #e2e8f0', borderRadius: '8px', fontSize: '12px' }}
                              formatter={(v: number) => [`${v}%`, '빈도']}
                              labelFormatter={(l) => `${l}%대`}
                            />
                            <Bar dataKey="pct" name="빈도%" radius={[3, 3, 0, 0]}>
                              {zonesData.zones.map((z: CompetitorZoneItem, i: number) => (
                                <Cell
                                  key={i}
                                  fill={
                                    zonesData.peak_zone && z.range_lo === zonesData.peak_zone.range_lo
                                      ? '#ef4444'
                                      : '#a78bfa'
                                  }
                                />
                              ))}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>
                  </>
                )}
              </TabsContent>

              <TabsContent value="predict" className="space-y-4 mt-3">
                {!selectedBid ? (
                  <Card className="bg-white border-slate-200">
                    <CardContent className="py-12 text-center text-sm text-slate-500">
                      상단에서 예측 대상 공고를 선택하세요
                    </CardContent>
                  </Card>
                ) : predictLoading ? (
                  <div className="flex items-center justify-center py-16 text-slate-500 text-sm">
                    <Loader2 className="h-5 w-5 animate-spin mr-2" />예측 데이터 로딩 중...
                  </div>
                ) : !predictData ? (
                  <Card className="bg-white border-slate-200">
                    <CardContent className="py-12 text-center text-sm text-slate-500">
                      데이터를 불러오는 중...
                    </CardContent>
                  </Card>
                ) : (
                  <div className="space-y-4">
                    {/* 참여 확률 카드 */}
                    <Card className="relative overflow-hidden bg-white border-slate-200 shadow-sm">
                      <div className="absolute top-0 left-0 right-0 h-0.5 bg-purple-500" />
                      <CardHeader className="pb-1 pt-4 px-4">
                        <CardTitle className="text-sm font-semibold text-slate-800">참여 확률 예측</CardTitle>
                      </CardHeader>
                      <CardContent className="px-4 pb-4 space-y-3">
                        <div className="flex items-end gap-3">
                          <span className="text-4xl font-bold text-purple-600 tabular-nums">
                            {(predictData.participation.probability * 100).toFixed(0)}%
                          </span>
                          <Badge
                            variant={
                              predictData.participation.confidence === 'high' ? 'default'
                                : predictData.participation.confidence === 'medium' ? 'warning'
                                : 'secondary'
                            }
                            className="mb-1"
                          >
                            신뢰도 {predictData.participation.confidence === 'high' ? '높음' : predictData.participation.confidence === 'medium' ? '보통' : '낮음'}
                          </Badge>
                        </div>
                        <p className="text-xs text-slate-500">{predictData.participation.basis}</p>
                        <div className="w-full bg-slate-100 rounded-full h-2">
                          <div
                            className="bg-purple-500 h-2 rounded-full transition-all"
                            style={{ width: `${predictData.participation.probability * 100}%` }}
                          />
                        </div>
                      </CardContent>
                    </Card>

                    {/* 투찰 구간 예측 */}
                    {predictData.bid_zone.sample_count === 0 ? (
                      <Card className="bg-white border-slate-200">
                        <CardContent className="py-8 text-center text-sm text-slate-500">
                          inpo21c 투찰 구간 데이터 없음
                        </CardContent>
                      </Card>
                    ) : (
                      <Card className="bg-white border-slate-200 shadow-sm">
                        <CardHeader className="pb-1 pt-4 px-4">
                          <CardTitle className="text-sm font-semibold text-slate-800 flex items-center justify-between">
                            <span>예상 투찰 구간 분포</span>
                            <span className="text-xs font-normal text-slate-500">{predictData.bid_zone.sample_count}건 기반</span>
                          </CardTitle>
                        </CardHeader>
                        <CardContent className="px-4 pb-4 space-y-3">
                          {predictData.bid_zone.peak_zone && (
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="inline-flex items-center text-xs px-2.5 py-1 rounded-full bg-red-50 text-red-700 border border-red-200 font-medium">
                                피크 {(predictData.bid_zone.peak_zone.range_lo * 100).toFixed(1)}%~{(predictData.bid_zone.peak_zone.range_hi * 100).toFixed(1)}%
                                ({predictData.bid_zone.peak_zone.pct}%)
                              </span>
                              <span className="inline-flex items-center text-xs px-2.5 py-1 rounded-full bg-amber-50 text-amber-700 border border-amber-200 font-medium">
                                이 구간 회피 추천
                              </span>
                            </div>
                          )}
                          <ResponsiveContainer width="100%" height={200}>
                            <BarChart
                              data={predictData.bid_zone.zones.map((z: BidZonePredItem) => ({
                                label: `${(z.range_lo * 100).toFixed(1)}`,
                                pct: z.pct,
                                isPeak: predictData.bid_zone.peak_zone?.range_lo === z.range_lo,
                              }))}
                              margin={{ left: -10 }}
                            >
                              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                              <XAxis dataKey="label" tick={{ fontSize: 12, fill: '#475569' }} interval={1} unit="%" />
                              <YAxis tick={{ fontSize: 12, fill: '#475569' }} unit="%" />
                              <Tooltip
                                contentStyle={{ border: '1px solid #e2e8f0', borderRadius: '8px', fontSize: '12px' }}
                                formatter={(v: number) => [`${v}%`, '빈도']}
                                labelFormatter={(l) => `${l}%대`}
                              />
                              <Bar dataKey="pct" name="빈도%" radius={[3, 3, 0, 0]}>
                                {predictData.bid_zone.zones.map((z: BidZonePredItem, i: number) => (
                                  <Cell
                                    key={i}
                                    fill={
                                      predictData.bid_zone.peak_zone?.range_lo === z.range_lo
                                        ? '#ef4444'
                                        : '#a78bfa'
                                    }
                                  />
                                ))}
                              </Bar>
                            </BarChart>
                          </ResponsiveContainer>
                        </CardContent>
                      </Card>
                    )}
                  </div>
                )}
              </TabsContent>
              </Tabs>
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-slate-500 gap-2">
              <ShieldAlert className="h-10 w-10 text-slate-200" />
              <p className="text-sm">목록에서 업체를 선택하세요</p>
            </div>
          )}
        </div>
      </div>

      {/* 2개 업체 비교 Dialog */}
      <Dialog open={showCompare} onOpenChange={(o) => { setShowCompare(o); if (!o) setCompareIds([]) }}>
        <DialogContent className="max-w-4xl max-h-[85vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="text-slate-900">경쟁사 투찰 패턴 비교</DialogTitle>
            <DialogDescription className="text-xs text-slate-500">
              {compareData?.competitors?.map((c: { name: string }) => c.name).join(' vs ') ?? '...'}
            </DialogDescription>
          </DialogHeader>
          <div className="overflow-y-auto flex-1">
            {!compareData ? (
              <div className="py-16 flex items-center justify-center text-slate-500 text-sm">
                <Loader2 className="h-5 w-5 animate-spin mr-2" />데이터를 불러오는 중...
              </div>
            ) : (
              <div className="space-y-5 p-1">
                {/* 레이더 비교 */}
                <div className="grid grid-cols-2 gap-4">
                  {compareData.competitors.map((c: { id: number; name: string; radar: Record<string, number>; monthly_trend: { year_month: string; bid_count: number; win_count: number; avg_rate: number | null }[] }) => (
                    <Card key={c.id} className="bg-white border-slate-200">
                      <CardHeader className="pb-1 pt-4 px-4">
                        <CardTitle className="text-sm font-semibold text-center text-slate-800">{c.name}</CardTitle>
                      </CardHeader>
                      <CardContent className="px-4 pb-4">
                        <ResponsiveContainer width="100%" height={200}>
                          <RadarChart data={[
                            { subject: '공격성', value: c.radar.aggression ?? 0 },
                            { subject: '일관성', value: c.radar.consistency ?? 0 },
                            { subject: '집중도', value: c.radar.concentration ?? 0 },
                            { subject: '위험도', value: c.radar.risk ?? 0 },
                            { subject: '활동성', value: c.radar.activity ?? 0 },
                          ]}>
                            <PolarGrid stroke="#e2e8f0" />
                            <PolarAngleAxis dataKey="subject" tick={{ fontSize: 12, fill: '#64748b' }} />
                            <PolarRadiusAxis domain={[0, 10]} tick={false} />
                            <Radar dataKey="value" stroke="#7c3aed" fill="#7c3aed" fillOpacity={0.2} strokeWidth={2} />
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
                  const COMPARE_COLORS = ['#7c3aed', '#f97316']
                  return (
                    <Card className="bg-white border-slate-200">
                      <CardHeader className="pb-1 pt-4 px-4">
                        <CardTitle className="text-sm font-semibold text-slate-800">월별 평균 투찰률 추이 비교</CardTitle>
                      </CardHeader>
                      <CardContent className="px-4 pb-4">
                        <ResponsiveContainer width="100%" height={200}>
                          <LineChart data={chartData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                            <XAxis dataKey="ym" tick={{ fontSize: 12, fill: '#475569' }} interval={1} />
                            <YAxis tick={{ fontSize: 12, fill: '#475569' }} unit="%" domain={['auto', 'auto']} />
                            <Tooltip
                              contentStyle={{ border: '1px solid #e2e8f0', borderRadius: '8px', fontSize: '12px' }}
                              formatter={(v: number) => [v + '%', '']}
                            />
                            {compareData.competitors.map((c: { name: string }, i: number) => (
                              <Line key={c.name} type="monotone" dataKey={c.name}
                                stroke={COMPARE_COLORS[i]} strokeWidth={2} dot={false} connectNulls />
                            ))}
                          </LineChart>
                        </ResponsiveContainer>
                        <div className="flex gap-4 text-xs mt-2">
                          {compareData.competitors.map((c: { name: string }, i: number) => (
                            <span key={c.name} className="flex items-center gap-1.5">
                              <span className="w-3 h-0.5 inline-block rounded" style={{ backgroundColor: COMPARE_COLORS[i] }} />
                              <span className="text-slate-600">{c.name}</span>
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

      {/* 이 공고 경쟁사 일괄 분석 Dialog */}
      {selectedBid && (
        <BatchAnalysisDialog
          open={showBatchAnalysis}
          onOpenChange={setShowBatchAnalysis}
          bidItem={selectedBid}
          competitors={(list?.items ?? []).slice(0, 5)}
        />
      )}

      {/* 수주 이력 Dialog */}
      <Dialog open={winsModalOpen} onOpenChange={setWinsModalOpen}>
        <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-slate-900">
              <Trophy className="h-4 w-4 text-amber-500" />
              {detail?.name} — 수주 이력 ({detail?.win_count}건)
            </DialogTitle>
          </DialogHeader>
          <div className="overflow-y-auto flex-1">
            {winHistory.length === 0 ? (
              <div className="p-10 text-center text-slate-500">불러오는 중...</div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow className="bg-slate-50">
                    <TableHead className="text-sm text-slate-500">개찰일</TableHead>
                    <TableHead className="text-sm text-slate-500">수주 사업명</TableHead>
                    <TableHead className="text-sm text-slate-500">발주기관</TableHead>
                    <TableHead className="text-right text-sm text-slate-500">기초금액</TableHead>
                    <TableHead className="text-center text-sm text-slate-500">투찰률</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {winHistory.map((w) => (
                    <TableRow key={w.result_id} className="hover:bg-amber-50/30 transition-colors">
                      <TableCell className="whitespace-nowrap text-sm text-slate-500">{fmtDate(w.bid_open_date)}</TableCell>
                      <TableCell className="max-w-[220px]">
                        <span className="block font-medium truncate text-xs text-slate-800" title={w.title}>{w.title}</span>
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-sm text-slate-600">{w.agency_name}</TableCell>
                      <TableCell className="text-right whitespace-nowrap text-sm text-slate-600">{fmtAmt(w.base_amount)}</TableCell>
                      <TableCell className="text-center">
                        <span className="font-mono font-bold text-purple-600 text-sm">
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
            <div className="border-t border-slate-100 pt-3 flex gap-6 text-xs text-slate-500">
              <span>평균 투찰률 <strong className="text-purple-600 text-sm">{(avgRate * 100).toFixed(2)}%</strong></span>
              <span>최고 <strong className="text-emerald-600">{(maxRate * 100).toFixed(2)}%</strong></span>
              <span>최저 <strong className="text-red-500">{(minRate * 100).toFixed(2)}%</strong></span>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

function MetricCard({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className={cn(
      'rounded-xl p-3 border',
      highlight
        ? 'bg-purple-50 border-purple-100'
        : 'bg-slate-50 border-slate-100'
    )}>
      <div className={cn('text-sm font-medium', highlight ? 'text-purple-500' : 'text-slate-500')}>{label}</div>
      <div className={cn('text-lg font-bold mt-0.5 tabular-nums', highlight ? 'text-purple-700' : 'text-slate-800')}>{value}</div>
    </div>
  )
}

interface BatchAnalysisDialogProps {
  open: boolean
  onOpenChange: (o: boolean) => void
  bidItem: BidSearchItem
  competitors: Competitor[]
}

function BatchAnalysisDialog({ open, onOpenChange, bidItem, competitors }: BatchAnalysisDialogProps) {
  const results = useQueries({
    queries: competitors.map((c) => ({
      queryKey: ['competitor-predict-batch', c.id, bidItem.id],
      queryFn: () => competitorsApi.predict(c.id, bidItem.id),
      enabled: open,
    })),
  })

  const confidenceLabel = (c: string) =>
    c === 'high' ? '높음' : c === 'medium' ? '보통' : '낮음'
  const confidenceVariant = (c: string): 'default' | 'warning' | 'secondary' =>
    c === 'high' ? 'default' : c === 'medium' ? 'warning' : 'secondary'

  const riskColorClass = (r: string) =>
    r === 'HIGH'
      ? 'bg-red-50 text-red-700 border-red-200'
      : r === 'MEDIUM'
      ? 'bg-amber-50 text-amber-700 border-amber-200'
      : r === 'LOW'
      ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
      : 'bg-slate-100 text-slate-500 border-slate-200'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-slate-900">
            <Target className="h-4 w-4 text-purple-600" />
            이 공고 경쟁사 일괄 분석
          </DialogTitle>
          <DialogDescription className="text-xs text-slate-500 truncate">
            {bidItem.announcement_no} · {bidItem.title}
          </DialogDescription>
        </DialogHeader>
        <div className="overflow-y-auto flex-1 space-y-3 pr-1">
          {competitors.map((c, i) => {
            const q = results[i]
            return (
              <Card key={c.id} className="bg-white border-slate-200 shadow-sm">
                <CardContent className="pt-4 pb-3">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-sm text-slate-800">{c.name}</span>
                      <span className={cn('text-xs px-1.5 py-0.5 rounded border font-semibold', riskColorClass(c.risk_level))}>
                        {c.risk_level}
                      </span>
                    </div>
                    {q.isLoading && <Loader2 className="h-4 w-4 animate-spin text-slate-500" />}
                  </div>
                  {q.data ? (
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <div className="text-xs text-slate-500 mb-1">참여 확률</div>
                        <div className="flex items-center gap-2">
                          <span className="text-2xl font-bold text-purple-600 tabular-nums">
                            {(q.data.participation.probability * 100).toFixed(0)}%
                          </span>
                          <Badge variant={confidenceVariant(q.data.participation.confidence)} className="text-xs">
                            신뢰 {confidenceLabel(q.data.participation.confidence)}
                          </Badge>
                        </div>
                        <p className="text-[11px] text-slate-500 mt-1 leading-tight">{q.data.participation.basis}</p>
                      </div>
                      <div>
                        <div className="text-xs text-slate-500 mb-1">
                          예상 피크 구간
                          {q.data.bid_zone.sample_count > 0 && (
                            <span className="ml-1 text-xs text-slate-500">({q.data.bid_zone.sample_count}건 기반)</span>
                          )}
                        </div>
                        {q.data.bid_zone.peak_zone ? (
                          <span className="inline-flex items-center text-xs px-2 py-0.5 rounded-full bg-red-50 text-red-700 border border-red-200 font-medium">
                            {(q.data.bid_zone.peak_zone.range_lo * 100).toFixed(1)}%~{(q.data.bid_zone.peak_zone.range_hi * 100).toFixed(1)}%
                            ({q.data.bid_zone.peak_zone.pct}%)
                          </span>
                        ) : (
                          <span className="text-xs text-slate-500">데이터 없음</span>
                        )}
                      </div>
                    </div>
                  ) : q.isError ? (
                    <p className="text-xs text-red-500">데이터 조회 실패</p>
                  ) : null}
                </CardContent>
              </Card>
            )
          })}
        </div>
      </DialogContent>
    </Dialog>
  )
}
