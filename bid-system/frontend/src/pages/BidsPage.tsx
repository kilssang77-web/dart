import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Search, ChevronLeft, ChevronRight, X, Building2, Star, CalendarDays, List } from 'lucide-react'
import { bidsApi } from '@/api'
import type { Bid, MetaData } from '@/types'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'

const SIZE_OPTIONS = [20, 50, 100]

export default function BidsPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [searchParams] = useSearchParams()
  const initKeyword = searchParams.get('keyword') ?? ''
  const [keyword, setKeyword]       = useState(initKeyword)
  const [agencyInput, setAgencyInput] = useState('')
  const [agencyId, setAgencyId]     = useState<number | null>(null)
  const [showAgencyDrop, setShowAgencyDrop] = useState(false)
  const [page, setPage]             = useState(1)
  const [search, setSearch]         = useState(initKeyword)
  const [statusFilter, setStatusFilter] = useState('all')
  const [sortBy, setSortBy]         = useState('notice_date')
  const [pageSize, setPageSize]     = useState(20)
  const [bookmarkOnly, setBookmarkOnly] = useState(false)
  const [viewMode, setViewMode]         = useState<'list' | 'calendar'>('list')
  const [calYear, setCalYear]           = useState(() => new Date().getFullYear())
  const [calMonth, setCalMonth]         = useState(() => new Date().getMonth() + 1)
  const agencyRef = useRef<HTMLDivElement>(null)
  const [regionId, setRegionId]     = useState<number | null>(null)

  const { data: meta } = useQuery<MetaData>({
    queryKey: ['meta'],
    queryFn: bidsApi.meta,
    staleTime: 300_000,
  })

  const { data: bookmarkData } = useQuery<{ items: { bid_id: number }[]; total: number }>({
    queryKey: ['bookmarks'],
    queryFn: () => bidsApi.bookmarks({ size: 1000 }),
  })
  const bookmarkedIds = new Set((bookmarkData?.items ?? []).map((b) => b.bid_id))

  const { data, isLoading } = useQuery<{ items: Bid[]; total: number; page: number; size: number }>({
    queryKey: ['bids', search, page, statusFilter, sortBy, agencyId, regionId, pageSize],
    queryFn: () => bidsApi.list({
      keyword:   search || undefined,
      page,
      size:      pageSize,
      status:    statusFilter === 'all' ? undefined : statusFilter,
      sort_by:   sortBy,
      agency_id: agencyId ?? undefined,
      region_id: regionId ?? undefined,
    }),
  })

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

  // 달력뷰용 해당 월 전체 데이터 (최대 200건)
  const { data: calData, isLoading: calLoading } = useQuery<{ items: Bid[]; total: number }>({
    queryKey: ['bids-cal', calYear, calMonth],
    queryFn: () => bidsApi.list({
      date_from: `${calYear}-${String(calMonth).padStart(2,'0')}-01`,
      date_to:   `${calYear}-${String(calMonth).padStart(2,'0')}-${new Date(calYear, calMonth, 0).getDate()}`,
      size: 200,
      sort_by: 'bid_open_date',
    }),
    enabled: viewMode === 'calendar',
    staleTime: 60_000,
  })

  const calDaysMap = (() => {
    const m: Record<number, Bid[]> = {}
    for (const b of calData?.items ?? []) {
      const dateStr = b.bid_open_date ?? b.notice_date
      if (!dateStr) continue
      // KST(UTC+9) 기준 날짜로 파싱
      const dt = new Date(dateStr)
      const kstDate = new Date(dt.getTime() + 9 * 60 * 60 * 1000)
      const d = kstDate.getUTCDate()
      if (!m[d]) m[d] = []
      m[d].push(b)
    }
    return m
  })()

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

  return (
    <div className="p-6 space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">입찰 현황</h1>
        <p className="text-muted-foreground text-sm mt-1">
          전체 {data?.total?.toLocaleString() ?? 0}건
        </p>
      </div>

      {/* 탭 + 뷰 모드 */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex gap-1">
          <Button variant={!bookmarkOnly ? 'default' : 'outline'} size="sm"
            onClick={() => { setBookmarkOnly(false); setPage(1) }}>전체</Button>
          <Button variant={bookmarkOnly ? 'default' : 'outline'} size="sm" className="gap-1.5"
            onClick={() => { setBookmarkOnly(true); setPage(1) }}>
            <Star className="h-3.5 w-3.5" />
            북마크 {bookmarkedIds.size > 0 && `(${bookmarkedIds.size})`}
          </Button>
        </div>
        <div className="flex gap-1">
          <Button variant={viewMode === 'list' ? 'default' : 'outline'} size="sm" className="gap-1.5 h-8"
            onClick={() => setViewMode('list')}><List className="h-3.5 w-3.5" />목록</Button>
          <Button variant={viewMode === 'calendar' ? 'default' : 'outline'} size="sm" className="gap-1.5 h-8"
            onClick={() => setViewMode('calendar')}><CalendarDays className="h-3.5 w-3.5" />달력</Button>
        </div>
      </div>

      {/* 달력 뷰 */}
      {viewMode === 'calendar' && (() => {
        const daysInMonth = new Date(calYear, calMonth, 0).getDate()
        const firstDay    = new Date(calYear, calMonth - 1, 1).getDay()
        const cells = Array.from({ length: firstDay + daysInMonth }, (_, i) => i < firstDay ? null : i - firstDay + 1)
        return (
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-3">
                <Button variant="ghost" size="sm" onClick={() => { if (calMonth === 1) { setCalYear(y=>y-1); setCalMonth(12) } else setCalMonth(m=>m-1) }}>← 이전달</Button>
                <span className="font-semibold">
                  {calYear}년 {calMonth}월{' '}
                  {calLoading
                    ? <span className="text-xs text-muted-foreground font-normal">불러오는 중...</span>
                    : <span className="text-sm font-normal text-muted-foreground">({calData?.total ?? 0}건 · 개찰일 기준)</span>
                  }
                </span>
                <Button variant="ghost" size="sm" onClick={() => { if (calMonth === 12) { setCalYear(y=>y+1); setCalMonth(1) } else setCalMonth(m=>m+1) }}>다음달 →</Button>
              </div>
              <div className="grid grid-cols-7 gap-1 text-center">
                {['일','월','화','수','목','금','토'].map(d => (
                  <div key={d} className="text-[10px] font-semibold text-muted-foreground py-1">{d}</div>
                ))}
                {cells.map((day, i) => {
                  const bids = day ? (calDaysMap[day] ?? []) : []
                  return (
                    <div key={i} className={cn('min-h-[80px] rounded-md p-1 border text-[10px]',
                      day ? 'bg-background hover:bg-accent/30' : 'bg-muted/20 border-transparent')}>
                      {day && (
                        <>
                          <div className="font-semibold text-muted-foreground mb-1">{day}</div>
                          {bids.slice(0,3).map((b) => (
                            <div key={b.id}
                              className={cn('truncate rounded px-1 py-0.5 mb-0.5 cursor-pointer',
                                b.status === 'closed' ? 'bg-primary/10 text-primary' : 'bg-orange-50 text-orange-700')}
                              onClick={() => navigate(`/bids/${b.id}`)}>
                              {b.title.slice(0, 12)}
                            </div>
                          ))}
                          {bids.length > 3 && (
                            <div className="text-muted-foreground text-center">+{bids.length-3}건</div>
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
      <div className="flex flex-wrap gap-2 items-center">
        <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setPage(1) }}>
          <SelectTrigger className="w-28">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">전체</SelectItem>
            <SelectItem value="open">공고중</SelectItem>
            <SelectItem value="closed">개찰완료</SelectItem>
          </SelectContent>
        </Select>

        <Select value={sortBy} onValueChange={(v) => { setSortBy(v); setPage(1) }}>
          <SelectTrigger className="w-28">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="notice_date">공고일순</SelectItem>
            <SelectItem value="bid_open_date">개찰일순</SelectItem>
          </SelectContent>
        </Select>

        <Select value={regionId != null ? regionId.toString() : "all"} onValueChange={(v) => { setRegionId(v === "all" ? null : parseInt(v)); setPage(1) }}>
          <SelectTrigger className="w-24">
            <SelectValue placeholder="지역" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">전체지역</SelectItem>
            <SelectItem value="1">서울</SelectItem>
            <SelectItem value="2">부산</SelectItem>
            <SelectItem value="3">대구</SelectItem>
            <SelectItem value="4">인천</SelectItem>
            <SelectItem value="5">광주</SelectItem>
            <SelectItem value="6">대전</SelectItem>
            <SelectItem value="7">울산</SelectItem>
            <SelectItem value="8">세종</SelectItem>
            <SelectItem value="9">경기</SelectItem>
            <SelectItem value="10">강원</SelectItem>
            <SelectItem value="11">충북</SelectItem>
            <SelectItem value="12">충남</SelectItem>
            <SelectItem value="13">전북</SelectItem>
            <SelectItem value="14">전남</SelectItem>
            <SelectItem value="15">경북</SelectItem>
            <SelectItem value="16">경남</SelectItem>
            <SelectItem value="17">제주</SelectItem>
          </SelectContent>
        </Select>

        {/* 발주기관 자동완성 */}
        <div className="relative" ref={agencyRef}>
          <div className={cn(
            "flex items-center h-9 rounded-md border border-input bg-transparent px-3 text-sm gap-2",
            "focus-within:ring-1 focus-within:ring-ring"
          )}>
            <Building2 className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            <input
              value={agencyInput}
              onChange={(e) => {
                setAgencyInput(e.target.value)
                setShowAgencyDrop(true)
                if (!e.target.value) handleAgencyClear()
              }}
              onFocus={() => agencyInput && setShowAgencyDrop(true)}
              placeholder="발주기관 검색..."
              className="outline-none w-40 bg-transparent placeholder:text-muted-foreground"
            />
            {agencyId && (
              <button onClick={handleAgencyClear} className="text-muted-foreground hover:text-foreground">
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          {showAgencyDrop && filteredAgencies.length > 0 && (
            <Card className="absolute z-20 top-full left-0 mt-1 w-72 py-1 overflow-hidden shadow-lg">
              {filteredAgencies.map((a) => (
                <button
                  key={a.id}
                  onClick={() => handleAgencySelect(a.id, a.name)}
                  className={cn(
                    'w-full text-left px-3 py-1.5 text-sm hover:bg-accent transition-colors',
                    agencyId === a.id && 'bg-accent font-medium'
                  )}
                >
                  {a.name}
                </button>
              ))}
            </Card>
          )}
        </div>

        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSearch() }}
            placeholder="공고명 검색..."
            className="pl-9"
          />
        </div>
        <Button onClick={handleSearch} size="sm">검색</Button>
      </div>

      {/* 테이블 */}
      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8" />
              <TableHead>공고명</TableHead>
              <TableHead>발주기관</TableHead>
              <TableHead>지역</TableHead>
              <TableHead className="text-right">기초금액</TableHead>
              <TableHead>공고일</TableHead>
              <TableHead>개찰일</TableHead>
              <TableHead className="text-center">경쟁사</TableHead>
              <TableHead className="text-right">낙찰률</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 9 }).map((_, j) => (
                    <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : !data?.items?.length ? (
              <TableRow>
                <TableCell colSpan={9} className="text-center text-muted-foreground py-10">
                  데이터가 없습니다.
                </TableCell>
              </TableRow>
            ) : (
              data.items
                .filter((bid) => !bookmarkOnly || bookmarkedIds.has(bid.id))
                .map((bid: Bid) => (
                <TableRow
                  key={bid.id}
                  className="cursor-pointer"
                  onClick={() => navigate(`/bids/${bid.id}`)}
                >
                  <TableCell onClick={(e) => toggleBookmark(e, bid.id)} className="cursor-pointer">
                    <Star
                      className={cn(
                        'h-4 w-4 transition-colors',
                        bookmarkedIds.has(bid.id)
                          ? 'fill-yellow-400 text-yellow-400'
                          : 'text-muted-foreground hover:text-yellow-400'
                      )}
                    />
                  </TableCell>
                  <TableCell className="max-w-xs">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-medium text-primary">{bid.title}</span>
                      {bid.source === 'g2b' && (
                        <Badge variant="info" className="shrink-0 text-[10px] px-1 py-0">G2B</Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="whitespace-nowrap">
                    <button
                      className="hover:text-primary hover:underline transition-colors text-left"
                      onClick={(e) => {
                        e.stopPropagation()
                        const ag = meta?.agencies.find((a) => a.name === bid.agency_name)
                        if (ag) navigate(`/agencies/${ag.id}`)
                      }}
                    >
                      {bid.agency_name}
                    </button>
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-muted-foreground">{bid.region_name ?? '-'}</TableCell>
                  <TableCell className="text-right whitespace-nowrap">{(bid.base_amount / 1e8).toFixed(1)}억</TableCell>
                  <TableCell className="whitespace-nowrap text-muted-foreground">
                    {bid.notice_date ? new Date(bid.notice_date).toLocaleDateString('ko-KR') : '-'}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-muted-foreground">
                    {bid.bid_open_date ? new Date(bid.bid_open_date).toLocaleDateString('ko-KR') : '-'}
                  </TableCell>
                  <TableCell className="text-center">{bid.competitor_count}</TableCell>
                  <TableCell className="text-right font-mono font-semibold">
                    {bid.winner_rate ? (bid.winner_rate * 100).toFixed(2) + '%' : '-'}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>

        {/* 페이지네이션 */}
        <div className="flex items-center justify-between px-4 py-3 border-t">
          <div className="flex items-center gap-1">
            <span className="text-xs text-muted-foreground mr-2">페이지당</span>
            {SIZE_OPTIONS.map((s) => (
              <Button
                key={s}
                variant={pageSize === s ? 'default' : 'outline'}
                size="sm"
                onClick={() => { setPageSize(s); setPage(1) }}
                className="h-7 px-2 text-xs"
              >
                {s}
              </Button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="icon" className="h-8 w-8"
              onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="text-sm text-muted-foreground">{page} / {totalPages}</span>
            <Button variant="outline" size="icon" className="h-8 w-8"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages}>
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </Card>
      </>}
    </div>
  )
}
