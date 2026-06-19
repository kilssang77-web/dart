import { useState, useRef, useEffect, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Search, ChevronLeft, ChevronRight, X, Building2, Star, CalendarDays, List,
  Sparkles, MapPin, Crosshair,
} from 'lucide-react'
import { bidsApi, selectionApi } from '@/api'
import type { Bid, MetaData, BidRecommendItem } from '@/types'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

const SIZE_OPTIONS = [20, 50, 100]

type ActiveMode = 'recommend' | 'all' | 'region'

function VerdictBadge({ verdict }: { verdict: string }) {
  if (verdict === 'GO')
    return <Badge className="bg-emerald-500 text-white text-xs px-1.5 py-0 shrink-0">GO</Badge>
  if (verdict === 'WATCH')
    return <Badge className="bg-amber-400 text-white text-xs px-1.5 py-0 shrink-0">WATCH</Badge>
  return null
}

function DaysBadge({ dateStr }: { dateStr: string | null | undefined }) {
  if (!dateStr) return null
  const days = Math.ceil((new Date(dateStr).getTime() - Date.now()) / 86400000)
  if (days <= 0 || days > 7) return null
  return (
    <Badge className={cn('text-xs px-1.5 py-0 shrink-0',
      days <= 1 ? 'bg-red-500 text-white animate-pulse' : 'bg-orange-400 text-white')}>
      D-{days}
    </Badge>
  )
}

function GradeBadge({ grade }: { grade: string | null }) {
  const colors: Record<string, string> = {
    A: 'bg-emerald-100 text-emerald-800 border-emerald-300',
    B: 'bg-blue-100 text-blue-800 border-blue-300',
    C: 'bg-amber-100 text-amber-800 border-amber-300',
    D: 'bg-slate-100 text-slate-600 border-slate-300',
  }
  if (!grade) return null
  return (
    <span className={cn('inline-flex items-center justify-center rounded border text-xs font-bold w-5 h-5 shrink-0',
      colors[grade] ?? colors.D)}>
      {grade}
    </span>
  )
}

export default function BidsPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [searchParams] = useSearchParams()

  const activeMode: ActiveMode =
    searchParams.get('tab') === 'recommend' ? 'recommend'
    : searchParams.get('tab') === 'region' ? 'region'
    : 'all'

  const initKeyword = searchParams.get('keyword') ?? ''
  const [keyword, setKeyword]               = useState(initKeyword)
  const [agencyInput, setAgencyInput]       = useState('')
  const [agencyId, setAgencyId]             = useState<number | null>(null)
  const [showAgencyDrop, setShowAgencyDrop] = useState(false)
  const [page, setPage]                     = useState(1)
  const [search, setSearch]                 = useState(initKeyword)
  const [statusFilter, setStatusFilter]     = useState('all')
  const [sortBy, setSortBy]                 = useState('notice_date')
  const [pageSize, setPageSize]             = useState(20)
  const [viewMode, setViewMode]             = useState<'list' | 'calendar'>('list')
  const [calYear, setCalYear]               = useState(() => new Date().getFullYear())
  const [calMonth, setCalMonth]             = useState(() => new Date().getMonth() + 1)
  const [regionId, setRegionId]             = useState<number | null>(null)
  const [yegaMethodFilter, setYegaMethodFilter]       = useState('')
  const [contractMethodFilter, setContractMethodFilter] = useState('')
  const [baseAmountMin, setBaseAmountMin]             = useState('')
  const [baseAmountMax, setBaseAmountMax]             = useState('')
  const agencyRef = useRef<HTMLDivElement>(null)

  const { data: meta } = useQuery<MetaData>({
    queryKey: ['meta'],
    queryFn: bidsApi.meta,
    staleTime: 300_000,
  })

  const { data: bookmarkData } = useQuery<{ items: { bid_id: number }[]; total: number }>({
    queryKey: ['bookmarks'],
    queryFn: () => bidsApi.bookmarks({ size: 100 }),
  })
  const bookmarkedIds = new Set((bookmarkData?.items ?? []).map((b) => b.bid_id))

  const effectiveRegionId = activeMode === 'region' ? 6 : regionId

  // Main list (all + region modes)
  const { data, isLoading } = useQuery<{ items: Bid[]; total: number; page: number; size: number }>({
    queryKey: ['bids', search, page, statusFilter, sortBy, agencyId, effectiveRegionId, pageSize, yegaMethodFilter, contractMethodFilter, baseAmountMin, baseAmountMax],
    queryFn: () => bidsApi.list({
      keyword:          search || undefined,
      page,
      size:             pageSize,
      status:           statusFilter === 'all' ? undefined : statusFilter,
      sort_by:          sortBy,
      agency_id:        agencyId ?? undefined,
      region_id:        effectiveRegionId ?? undefined,
      yega_method:      yegaMethodFilter || undefined,
      contract_method:  contractMethodFilter || undefined,
      base_amount_min:  baseAmountMin ? Math.round(parseFloat(baseAmountMin) * 1e8) : undefined,
      base_amount_max:  baseAmountMax ? Math.round(parseFloat(baseAmountMax) * 1e8) : undefined,
    }),
    enabled: activeMode !== 'recommend',
  })

  // AI recommended bids
  const { data: recommendedBids, isLoading: recLoading } = useQuery<BidRecommendItem[]>({
    queryKey: ['bids-recommended', 20],
    queryFn: () => bidsApi.recommended(20),
    enabled: activeMode === 'recommend',
    staleTime: 60_000,
  })

  // GO/WATCH verdict map (enriches main list with AI decision badges)
  const { data: goListData } = useQuery({
    queryKey: ['go-list', 30],
    queryFn: () => selectionApi.goList(30),
    staleTime: 300_000,
    enabled: activeMode !== 'recommend',
  })

  const verdictMap = useMemo(() => {
    const m: Record<number, string> = {}
    const gld = goListData as { go?: { bid_id: number }[]; watch?: { bid_id: number }[] } | null
    gld?.go?.forEach((d) => { m[d.bid_id] = 'GO' })
    gld?.watch?.forEach((d) => { m[d.bid_id] = 'WATCH' })
    return m
  }, [goListData])

  // Calendar query
  const { data: calData, isLoading: calLoading } = useQuery<{ items: Bid[]; total: number }>({
    queryKey: ['bids-cal', calYear, calMonth],
    queryFn: () => bidsApi.list({
      date_from: `${calYear}-${String(calMonth).padStart(2, '0')}-01`,
      date_to:   `${calYear}-${String(calMonth).padStart(2, '0')}-${new Date(calYear, calMonth, 0).getDate()}`,
      size: 100,
      sort_by: 'bid_open_date',
    }),
    enabled: viewMode === 'calendar' && activeMode !== 'recommend',
    staleTime: 60_000,
  })

  const calDaysMap = useMemo(() => {
    const m: Record<number, Bid[]> = {}
    for (const b of calData?.items ?? []) {
      const dateStr = b.bid_open_date ?? b.notice_date
      if (!dateStr) continue
      const d = parseInt(dateStr.slice(8, 10), 10)
      if (!m[d]) m[d] = []
      m[d].push(b)
    }
    return m
  }, [calData])

  const addBookmark = useMutation({
    mutationFn: (id: number) => bidsApi.addBookmark(id),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: ['bookmarks'] })
      const prev = qc.getQueryData<{ items: { bid_id: number }[]; total: number }>(['bookmarks'])
      qc.setQueryData(['bookmarks'], (old: { items: { bid_id: number }[]; total: number } | undefined) =>
        old ? { ...old, items: [...old.items, { bid_id: id }] } : old
      )
      return { prev }
    },
    onError: (_e, _id, ctx) => qc.setQueryData(['bookmarks'], ctx?.prev),
  })

  const removeBookmark = useMutation({
    mutationFn: (id: number) => bidsApi.removeBookmark(id),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: ['bookmarks'] })
      const prev = qc.getQueryData(['bookmarks'])
      qc.setQueryData(['bookmarks'], (old: { items: { bid_id: number }[]; total: number } | undefined) =>
        old ? { ...old, items: old.items.filter((b) => b.bid_id !== id) } : old
      )
      return { prev }
    },
    onError: (_e, _id, ctx) => qc.setQueryData(['bookmarks'], ctx?.prev),
  })

  function toggleBookmark(e: React.MouseEvent, bidId: number) {
    e.stopPropagation()
    if (bookmarkedIds.has(bidId)) removeBookmark.mutate(bidId)
    else addBookmark.mutate(bidId)
  }

  const totalPages = data ? Math.ceil(data.total / pageSize) : 1
  const filteredAgencies = agencyInput.length >= 1
    ? (meta?.agencies ?? []).filter((a) => a.name.includes(agencyInput)).slice(0, 10)
    : []

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (agencyRef.current && !agencyRef.current.contains(e.target as Node))
        setShowAgencyDrop(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  function handleSearch() { setSearch(keyword); setPage(1) }
  function handleAgencySelect(id: number, name: string) {
    setAgencyId(id); setAgencyInput(name); setShowAgencyDrop(false); setPage(1)
  }
  function handleAgencyClear() {
    setAgencyId(null); setAgencyInput(''); setPage(1)
  }

  const displayItems = data?.items ?? []

  return (
    <div className="min-h-full bg-slate-50">
      {/* Sticky Page Header */}
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-sm border-b border-slate-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-slate-900 flex items-center gap-2">
              <Search className="h-5 w-5 text-blue-600" />
              공고센터
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">
              {activeMode === 'recommend' ? 'AI가 선별한 추천 공고'
                : activeMode === 'region' ? `대전 지역 ${data?.total?.toLocaleString() ?? 0}건`
                : `전체 ${data?.total?.toLocaleString() ?? 0}건`}
            </p>
          </div>
          {activeMode === 'all' && (
            <div className="flex items-center gap-1.5">
              <Button
                variant={viewMode === 'list' ? 'default' : 'outline'}
                size="sm"
                className={cn('gap-1.5 h-8 text-xs',
                  viewMode === 'list'
                    ? 'bg-blue-600 hover:bg-blue-700 text-white'
                    : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                )}
                onClick={() => setViewMode('list')}
              >
                <List className="h-3.5 w-3.5" />목록
              </Button>
              <Button
                variant={viewMode === 'calendar' ? 'default' : 'outline'}
                size="sm"
                className={cn('gap-1.5 h-8 text-xs',
                  viewMode === 'calendar'
                    ? 'bg-blue-600 hover:bg-blue-700 text-white'
                    : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                )}
                onClick={() => setViewMode('calendar')}
              >
                <CalendarDays className="h-3.5 w-3.5" />달력
              </Button>
            </div>
          )}
        </div>
      </div>

      <div className="px-6 py-4 space-y-4">
        {/* Tab Bar */}
        <Tabs value={activeMode}>
          <TabsList className="bg-slate-100 border border-slate-200 h-9">
            <TabsTrigger
              value="recommend"
              className="gap-1.5 text-xs data-[state=active]:bg-white data-[state=active]:shadow-sm data-[state=active]:text-blue-600"
              onClick={() => navigate('/bids?tab=recommend')}
            >
              <Sparkles className="h-3.5 w-3.5" />추천공고
            </TabsTrigger>
            <TabsTrigger
              value="all"
              className="gap-1.5 text-xs data-[state=active]:bg-white data-[state=active]:shadow-sm data-[state=active]:text-blue-600"
              onClick={() => navigate('/bids')}
            >
              <Search className="h-3.5 w-3.5" />전체공고
            </TabsTrigger>
            <TabsTrigger
              value="region"
              className="gap-1.5 text-xs data-[state=active]:bg-white data-[state=active]:shadow-sm data-[state=active]:text-blue-600"
              onClick={() => navigate('/bids?tab=region')}
            >
              <MapPin className="h-3.5 w-3.5" />지역공고
            </TabsTrigger>
          </TabsList>
        </Tabs>

        {/* ── 추천공고 뷰 ── */}
        {activeMode === 'recommend' && (
          <>
            {recLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-20 w-full" />)}
              </div>
            ) : !recommendedBids?.length ? (
              <Card className="bg-white border-slate-200 shadow-sm">
                <CardContent className="py-16 text-center">
                  <Sparkles className="h-8 w-8 text-slate-300 mx-auto mb-3" />
                  <p className="text-sm text-slate-500">AI 추천 공고가 없습니다.</p>
                  <p className="text-xs text-slate-500 mt-1">키워드 설정을 먼저 등록하세요.</p>
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-2">
                {recommendedBids.map((rec) => (
                  <Card
                    key={rec.bid_id}
                    className="bg-white border-slate-200 shadow-sm hover:shadow-md transition-shadow cursor-pointer"
                    onClick={() => navigate(`/bids/${rec.bid_id}`)}
                  >
                    <CardContent className="py-3.5 px-4">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <GradeBadge grade={rec.grade} />
                            <span className="font-medium text-slate-900 truncate text-sm">{rec.title}</span>
                            <DaysBadge dateStr={rec.open_date} />
                          </div>
                          <div className="flex items-center gap-3 mt-1.5 text-xs text-slate-500 flex-wrap">
                            <span className="flex items-center gap-1">
                              <Building2 className="h-3 w-3" />{rec.agency_name}
                            </span>
                            <span className="font-medium text-slate-700">{rec.base_amount > 0 ? (rec.base_amount / 1e8).toFixed(1) + '억' : '-'}</span>
                            {rec.open_date && (
                              <span>개찰 {new Date(rec.open_date).toLocaleDateString('ko-KR')}</span>
                            )}
                          </div>
                          {rec.score_breakdown && (
                            <div className="flex flex-wrap gap-1.5 mt-2">
                              {(
                                [
                                  { key: 'competition',    label: '경쟁강도' },
                                  { key: 'personal_track', label: '발주기관이력' },
                                  { key: 'market_trend',   label: '시장추세' },
                                  { key: 'amount_fit',     label: '금액적합' },
                                ] as { key: keyof typeof rec.score_breakdown; label: string }[]
                              ).map(({ key, label }) => {
                                const c = rec.score_breakdown![key]
                                if (!c) return null
                                return (
                                  <span
                                    key={key}
                                    title={c.note}
                                    className="inline-flex items-center gap-1 bg-slate-100 border border-slate-200 rounded px-1.5 py-0.5 text-sm text-slate-600 cursor-default"
                                  >
                                    {label}
                                    <span className="font-semibold text-slate-800">{c.pts}</span>
                                    <span className="text-slate-500">/{c.max}</span>
                                  </span>
                                )
                              })}
                            </div>
                          )}
                        </div>
                        <div className="text-right shrink-0 flex flex-col items-end gap-1">
                          {rec.score !== null && rec.score !== undefined && (
                            <div className="bg-blue-50 border border-blue-200 rounded-lg px-2.5 py-1.5 text-center">
                              <p className="text-lg font-bold text-blue-600 tabular-nums leading-none">{Math.round(rec.score)}</p>
                              <p className="text-xs text-blue-400 mt-0.5">AI 점수</p>
                            </div>
                          )}
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 px-2.5 text-xs border-slate-200 text-slate-600 hover:bg-slate-50 hover:text-blue-600"
                            onClick={(e) => {
                              e.stopPropagation()
                              navigate(`/bids/${rec.bid_id}?tab=strategy`)
                            }}
                          >
                            전략 보기
                          </Button>
                          <Button
                            size="sm"
                            className="h-7 px-2.5 text-xs bg-blue-600 hover:bg-blue-700 text-white gap-1"
                            onClick={(e) => {
                              e.stopPropagation()
                              navigate(`/decision?bid=${rec.bid_id}`)
                            }}
                          >
                            <Crosshair className="h-3 w-3" />AI 투찰 결정
                          </Button>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </>
        )}

        {/* ── 전체/관심 뷰 ── */}
        {activeMode !== 'recommend' && <>

          {/* 달력 뷰 */}
          {viewMode === 'calendar' && (() => {
            const daysInMonth = new Date(calYear, calMonth, 0).getDate()
            const firstDay    = new Date(calYear, calMonth - 1, 1).getDay()
            const cells = Array.from({ length: firstDay + daysInMonth }, (_, i) =>
              i < firstDay ? null : i - firstDay + 1
            )
            return (
              <Card className="bg-white border-slate-200 shadow-sm">
                <CardContent className="p-5">
                  <div className="flex items-center justify-between mb-4">
                    <Button
                      variant="outline"
                      size="sm"
                      className="border-slate-200 text-slate-600 hover:bg-slate-50"
                      onClick={() => {
                        if (calMonth === 1) { setCalYear(y => y - 1); setCalMonth(12) }
                        else setCalMonth(m => m - 1)
                      }}
                    >
                      <ChevronLeft className="h-4 w-4" />이전달
                    </Button>
                    <div className="text-center">
                      <span className="font-semibold text-slate-900">
                        {calYear}년 {calMonth}월
                      </span>
                      {calLoading
                        ? <span className="ml-2 text-xs text-slate-500">불러오는 중...</span>
                        : <span className="ml-2 text-sm text-slate-500">({calData?.total ?? 0}건 · 개찰일 기준)</span>
                      }
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      className="border-slate-200 text-slate-600 hover:bg-slate-50"
                      onClick={() => {
                        if (calMonth === 12) { setCalYear(y => y + 1); setCalMonth(1) }
                        else setCalMonth(m => m + 1)
                      }}
                    >
                      다음달<ChevronRight className="h-4 w-4" />
                    </Button>
                  </div>
                  <div className="grid grid-cols-7 gap-1 text-center">
                    {['일','월','화','수','목','금','토'].map(d => (
                      <div key={d} className="text-xs font-semibold text-slate-500 py-1.5 border-b border-slate-100">{d}</div>
                    ))}
                    {cells.map((day, i) => {
                      const bids = day ? (calDaysMap[day] ?? []) : []
                      return (
                        <div key={i} className={cn('min-h-[80px] rounded-lg p-1.5 border text-xs',
                          day ? 'bg-white border-slate-200 hover:bg-slate-50' : 'bg-slate-50/50 border-transparent')}>
                          {day && (
                            <>
                              <div className="font-semibold text-slate-500 mb-1">{day}</div>
                              {bids.slice(0, 3).map((b) => (
                                <div key={b.id}
                                  className={cn('truncate rounded px-1 py-0.5 mb-0.5 cursor-pointer transition-colors',
                                    b.status === 'closed'
                                      ? 'bg-blue-50 text-blue-700 hover:bg-blue-100'
                                      : 'bg-amber-50 text-amber-700 hover:bg-amber-100')}
                                  onClick={() => navigate(`/bids/${b.id}`)}>
                                  {b.title.slice(0, 12)}
                                </div>
                              ))}
                              {bids.length > 3 && (
                                <div className="text-slate-500 text-center">+{bids.length - 3}건</div>
                              )}
                            </>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </CardContent>
              </Card>
            )
          })()}

          {viewMode === 'list' && <>
            {/* 필터 바 */}
            <Card className="bg-white border-slate-200 shadow-sm">
              <CardContent className="px-4 py-3">
                <div className="flex flex-wrap gap-2 items-center">
                  <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setPage(1) }}>
                    <SelectTrigger className="w-28 h-8 text-xs border-slate-200 bg-slate-50">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">전체</SelectItem>
                      <SelectItem value="open">공고중</SelectItem>
                      <SelectItem value="closed">개찰완료</SelectItem>
                    </SelectContent>
                  </Select>

                  <Select value={sortBy} onValueChange={(v) => { setSortBy(v); setPage(1) }}>
                    <SelectTrigger className="w-28 h-8 text-xs border-slate-200 bg-slate-50">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="notice_date">공고일순</SelectItem>
                      <SelectItem value="bid_open_date">개찰일순</SelectItem>
                    </SelectContent>
                  </Select>

                  {activeMode === 'region' ? (
                    <div className="flex items-center gap-1.5 h-8 px-3 rounded-md border border-blue-200 bg-blue-50 text-xs text-blue-700 font-semibold">
                      <MapPin className="h-3.5 w-3.5 shrink-0" />대전
                    </div>
                  ) : (
                    <Select value={regionId != null ? regionId.toString() : 'all'}
                      onValueChange={(v) => { setRegionId(v === 'all' ? null : parseInt(v)); setPage(1) }}>
                      <SelectTrigger className="w-24 h-8 text-xs border-slate-200 bg-slate-50">
                        <SelectValue placeholder="지역" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">전체지역</SelectItem>
                        {[['1','서울'],['2','부산'],['3','대구'],['4','인천'],['5','광주'],['6','대전'],
                          ['7','울산'],['8','세종'],['9','경기'],['10','강원'],['11','충북'],['12','충남'],
                          ['13','전북'],['14','전남'],['15','경북'],['16','경남'],['17','제주']
                        ].map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  )}

                  {/* 발주기관 자동완성 */}
                  <div className="relative" ref={agencyRef}>
                    <div className={cn(
                      'flex items-center h-8 rounded-md border border-slate-200 bg-slate-50 px-3 text-xs gap-2',
                      'focus-within:ring-1 focus-within:ring-blue-300 focus-within:border-blue-300',
                    )}>
                      <Building2 className="h-3.5 w-3.5 text-slate-500 shrink-0" />
                      <input
                        value={agencyInput}
                        onChange={(e) => {
                          setAgencyInput(e.target.value)
                          setShowAgencyDrop(true)
                          if (!e.target.value) handleAgencyClear()
                        }}
                        onFocus={() => agencyInput && setShowAgencyDrop(true)}
                        placeholder="발주기관 검색..."
                        className="outline-none w-40 bg-transparent placeholder:text-slate-500 text-slate-700"
                      />
                      {agencyId && (
                        <button onClick={handleAgencyClear} className="text-slate-500 hover:text-slate-600">
                          <X className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                    {showAgencyDrop && filteredAgencies.length > 0 && (
                      <Card className="absolute z-20 top-full left-0 mt-1 w-72 py-1 overflow-hidden shadow-lg border-slate-200">
                        {filteredAgencies.map((a) => (
                          <button
                            key={a.id}
                            onClick={() => handleAgencySelect(a.id, a.name)}
                            className={cn(
                              'w-full text-left px-3 py-1.5 text-sm hover:bg-slate-50 transition-colors text-slate-700',
                              agencyId === a.id && 'bg-blue-50 text-blue-700 font-medium',
                            )}
                          >
                            {a.name}
                          </button>
                        ))}
                      </Card>
                    )}
                  </div>

                  <div className="relative flex-1 max-w-sm">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" />
                    <Input
                      value={keyword}
                      onChange={(e) => setKeyword(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter') handleSearch() }}
                      placeholder="공고명 검색..."
                      className="pl-9 h-8 text-xs border-slate-200 bg-slate-50 focus:bg-white focus:border-blue-300"
                    />
                  </div>
                  <Button
                    onClick={handleSearch}
                    size="sm"
                    className="h-8 px-3 text-xs bg-blue-600 hover:bg-blue-700 text-white"
                  >
                    검색
                  </Button>
                </div>

                {/* 2번째 필터 행 */}
                <div className="flex flex-wrap gap-2 items-center mt-2 pt-2 border-t border-slate-100">
                  <Select value={yegaMethodFilter || 'all'} onValueChange={(v) => { setYegaMethodFilter(v === 'all' ? '' : v); setPage(1) }}>
                    <SelectTrigger className="w-32 h-8 text-xs border-slate-200 bg-slate-50">
                      <SelectValue placeholder="예가방법" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">전체예가</SelectItem>
                      <SelectItem value="복수예가">복수예가</SelectItem>
                      <SelectItem value="표준시장단가">표준시장단가</SelectItem>
                    </SelectContent>
                  </Select>

                  <Select value={contractMethodFilter || 'all'} onValueChange={(v) => { setContractMethodFilter(v === 'all' ? '' : v); setPage(1) }}>
                    <SelectTrigger className="w-32 h-8 text-xs border-slate-200 bg-slate-50">
                      <SelectValue placeholder="계약방법" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">전체계약</SelectItem>
                      <SelectItem value="일반경쟁">일반경쟁</SelectItem>
                      <SelectItem value="제한경쟁">제한경쟁</SelectItem>
                      <SelectItem value="지명경쟁">지명경쟁</SelectItem>
                      <SelectItem value="수의계약">수의계약</SelectItem>
                    </SelectContent>
                  </Select>

                  <div className="flex items-center gap-1.5">
                    <span className="text-xs text-slate-500">기초금액</span>
                    <Input
                      type="number"
                      value={baseAmountMin}
                      onChange={(e) => { setBaseAmountMin(e.target.value); setPage(1) }}
                      placeholder="최소"
                      className="w-20 h-8 text-xs border-slate-200 bg-slate-50"
                    />
                    <span className="text-xs text-slate-400">~</span>
                    <Input
                      type="number"
                      value={baseAmountMax}
                      onChange={(e) => { setBaseAmountMax(e.target.value); setPage(1) }}
                      placeholder="최대"
                      className="w-20 h-8 text-xs border-slate-200 bg-slate-50"
                    />
                    <span className="text-xs text-slate-500">억원</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* 테이블 */}
            <Card className="bg-white border-slate-200 shadow-sm overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="bg-slate-50 hover:bg-slate-50 border-b border-slate-200">
                    <TableHead className="w-8 text-slate-500" />
                    <TableHead className="text-slate-600 font-semibold text-sm">공고명</TableHead>
                    <TableHead className="text-slate-600 font-semibold text-sm">발주기관</TableHead>
                    <TableHead className="text-slate-600 font-semibold text-sm">지역</TableHead>
                    <TableHead className="text-right text-slate-600 font-semibold text-sm">기초금액</TableHead>
                    <TableHead className="text-right text-slate-600 font-semibold text-sm">추정가격</TableHead>
                    <TableHead className="text-slate-600 font-semibold text-sm">투찰마감</TableHead>
                    <TableHead className="text-slate-600 font-semibold text-sm">개찰일</TableHead>
                    <TableHead className="text-center text-slate-600 font-semibold text-sm">경쟁사</TableHead>
                    <TableHead className="text-right text-slate-600 font-semibold text-sm">낙찰하한율</TableHead>
                    <TableHead className="text-right text-slate-600 font-semibold text-sm">낙찰률</TableHead>
                    <TableHead className="w-20 text-center text-slate-600 font-semibold text-sm">투찰결정</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {isLoading ? (
                    Array.from({ length: 5 }).map((_, i) => (
                      <TableRow key={i} className="border-b border-slate-100">
                        {Array.from({ length: 12 }).map((_, j) => (
                          <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
                        ))}
                      </TableRow>
                    ))
                  ) : !displayItems.length ? (
                    <TableRow>
                      <TableCell colSpan={12} className="text-center text-slate-500 py-16">
                        <Search className="h-8 w-8 text-slate-200 mx-auto mb-2" />
                        <p className="text-sm">데이터가 없습니다.</p>
                      </TableCell>
                    </TableRow>
                  ) : (
                    displayItems.map((bid: Bid) => {
                      const verdict = verdictMap[bid.id]
                      return (
                        <TableRow
                          key={bid.id}
                          className="cursor-pointer hover:bg-slate-50 transition-colors border-b border-slate-100 last:border-0"
                          onClick={() => navigate(`/bids/${bid.id}`)}
                        >
                          <TableCell
                            onClick={(e) => toggleBookmark(e, bid.id)}
                            className="cursor-pointer px-3"
                          >
                            <Star className={cn('h-4 w-4 transition-colors',
                              bookmarkedIds.has(bid.id)
                                ? 'fill-amber-400 text-amber-400'
                                : 'text-slate-300 hover:text-amber-400')} />
                          </TableCell>
                          <TableCell className="max-w-xs py-3">
                            <div className="flex items-center gap-1.5 flex-wrap">
                              {verdict && <VerdictBadge verdict={verdict} />}
                              <span className="truncate font-medium text-slate-900 text-sm">{bid.title}</span>
                              {bid.source === 'g2b' && (
                                <Badge variant="info" className="shrink-0 text-xs px-1.5 py-0">G2B</Badge>
                              )}
                              {bid.status === 'open' && <DaysBadge dateStr={bid.bid_open_date} />}
                            </div>
                          </TableCell>
                          <TableCell className="whitespace-nowrap py-3">
                            <button
                              className="text-sm text-slate-600 hover:text-blue-600 hover:underline transition-colors text-left"
                              onClick={(e) => {
                                e.stopPropagation()
                                const ag = meta?.agencies.find((a) => a.name === bid.agency_name)
                                if (ag) navigate(`/agencies/${ag.id}`)
                              }}
                            >
                              {bid.agency_name}
                            </button>
                          </TableCell>
                          <TableCell className="whitespace-nowrap text-slate-500 text-sm py-3">
                            {bid.region_name ?? '-'}
                          </TableCell>
                          <TableCell className="text-right whitespace-nowrap font-medium text-slate-900 text-sm py-3">
                            {bid.base_amount > 0 ? (bid.base_amount / 1e8).toFixed(1) + '억' : '-'}
                          </TableCell>
                          <TableCell className="text-right whitespace-nowrap text-slate-500 text-sm py-3">
                            {bid.estimated_price && bid.estimated_price > 0
                              ? (bid.estimated_price / 1e8).toFixed(1) + '억'
                              : '-'}
                          </TableCell>
                          <TableCell className="whitespace-nowrap text-slate-500 text-sm py-3">
                            {bid.bid_close_date
                              ? new Date(bid.bid_close_date).toLocaleDateString('ko-KR')
                              : '-'}
                          </TableCell>
                          <TableCell className="whitespace-nowrap text-slate-500 text-sm py-3">
                            {bid.bid_open_date
                              ? new Date(bid.bid_open_date).toLocaleDateString('ko-KR')
                              : '-'}
                          </TableCell>
                          <TableCell className="text-center text-slate-600 text-sm py-3">
                            {bid.competitor_count}
                          </TableCell>
                          <TableCell className="text-right font-mono text-slate-600 text-sm py-3">
                            {bid.min_bid_rate ? (bid.min_bid_rate * 100).toFixed(4) + '%' : '-'}
                          </TableCell>
                          <TableCell className="text-right font-mono font-semibold text-slate-900 text-sm py-3">
                            {bid.winner_rate ? (bid.winner_rate * 100).toFixed(4) + '%' : '-'}
                          </TableCell>
                          <TableCell className="text-center py-3">
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                navigate(`/decision?bid=${bid.id}`)
                              }}
                              className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-blue-50 text-blue-700 hover:bg-blue-600 hover:text-white border border-blue-200 hover:border-blue-600 transition-all"
                            >
                              <Crosshair className="h-3 w-3" />AI
                            </button>
                          </TableCell>
                        </TableRow>
                      )
                    })
                  )}
                </TableBody>
              </Table>

              {/* 페이지네이션 */}
              <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100 bg-slate-50/50">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-slate-500 mr-1">페이지당</span>
                  {SIZE_OPTIONS.map((s) => (
                    <Button key={s}
                      variant={pageSize === s ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => { setPageSize(s); setPage(1) }}
                      className={cn('h-7 px-2.5 text-xs',
                        pageSize === s
                          ? 'bg-blue-600 hover:bg-blue-700 text-white'
                          : 'border-slate-200 text-slate-600 hover:bg-slate-100'
                      )}>
                      {s}
                    </Button>
                  ))}
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-7 w-7 border-slate-200 text-slate-600 hover:bg-slate-100"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page === 1}
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <span className="text-xs text-slate-500 tabular-nums min-w-[60px] text-center">
                    {page} / {totalPages}
                  </span>
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-7 w-7 border-slate-200 text-slate-600 hover:bg-slate-100"
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page >= totalPages}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </Card>
          </>}
        </>}
      </div>
    </div>
  )
}
