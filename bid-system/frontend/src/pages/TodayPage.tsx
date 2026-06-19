/**
 * 오늘의 입찰 — 메인 허브
 * 입찰 담당자가 출근 후 30초 안에 오늘 할 일을 파악하는 화면
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Sparkles, AlertCircle, Clock, Trophy, Target,
  TrendingUp, TrendingDown, ChevronRight, CheckCircle2,
  Building2, Calendar, Zap, BarChart2, Search, ListChecks, Plus,
  BookOpen, ClipboardCheck, Crosshair,
} from 'lucide-react'
import { bidsApi, statsApi, selectionApi, kpiApi, executionsApi, journalApi } from '@/api'
import type { BidRecommendItem, OverviewStatsWithChange, ExecutionSummary, JournalStats } from '@/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

function fmtAmt(n: number) {
  if (n >= 1e8) return (n / 1e8).toFixed(0) + '억'
  if (n >= 1e4) return (n / 1e4).toFixed(0) + '만'
  return n.toLocaleString()
}

function daysUntil(dateStr: string | null | undefined): number | null {
  if (!dateStr) return null
  const diff = new Date(dateStr).getTime() - Date.now()
  return Math.ceil(diff / (1000 * 60 * 60 * 24))
}

function DeadlineBadge({ days }: { days: number | null }) {
  if (days === null) return null
  if (days <= 0) return (
    <span className="bg-red-500 text-white text-xs font-bold px-2 py-0.5 rounded-md">오늘마감</span>
  )
  if (days === 1) return (
    <span className="bg-red-500 text-white text-xs font-bold px-2 py-0.5 rounded-md animate-pulse">D-1 긴급</span>
  )
  if (days <= 3) return (
    <span className="bg-orange-400 text-white text-xs font-semibold px-2 py-0.5 rounded-md">D-{days}</span>
  )
  return (
    <span className="bg-slate-100 text-slate-500 border border-slate-200 text-xs font-semibold px-2 py-0.5 rounded-md">D-{days}</span>
  )
}

function VerdictBadge({ score }: { score: number | null }) {
  if (score === null) return null
  if (score >= 70) return (
    <span className="bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-semibold px-2 py-0.5 rounded-md">GO</span>
  )
  if (score >= 45) return (
    <span className="bg-amber-50 text-amber-700 border border-amber-200 text-xs font-semibold px-2 py-0.5 rounded-md">관심</span>
  )
  return (
    <span className="bg-slate-50 text-slate-500 border border-slate-200 text-xs font-semibold px-2 py-0.5 rounded-md">검토</span>
  )
}

function ScoreBar({ score }: { score: number | null }) {
  const s = score ?? 0
  const color = s >= 70 ? 'bg-emerald-500' : s >= 45 ? 'bg-amber-400' : 'bg-slate-300'
  return (
    <div className="flex items-center gap-1.5">
      <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div className={cn('h-1.5 rounded-full transition-all', color)} style={{ width: `${s}%` }} />
      </div>
      <span className="text-xs font-mono text-slate-500 w-7 text-right shrink-0">{s.toFixed(0)}점</span>
    </div>
  )
}

interface KPIData {
  total_bids: number
  total_wins: number
  win_rate: number
  monthly_target: number
  alerts: string[]
}

export default function TodayPage() {
  const navigate = useNavigate()
  const [checkedIds, setCheckedIds] = useState<Set<number>>(new Set())

  const today = new Date()
  const dateStr = today.toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' })

  // AI 추천 공고
  const { data: recommended, isLoading: loadingRec } = useQuery<BidRecommendItem[]>({
    queryKey: ['recommended-bids'],
    queryFn: () => bidsApi.recommended(10),
    staleTime: 300_000,
  })

  // 마감 임박 공고 (7일 이내 open)
  const { data: urgentBids } = useQuery({
    queryKey: ['urgent-bids'],
    queryFn: () => bidsApi.list({ status: 'open', sort_by: 'bid_open_date', size: 20 }),
    staleTime: 120_000,
  })

  // 통계 개요
  const { data: overview } = useQuery<OverviewStatsWithChange>({
    queryKey: ['overview', 3],
    queryFn: () => statsApi.overview(3),
    staleTime: 300_000,
  })

  // KPI 대시보드
  const { data: kpi } = useQuery<KPIData>({
    queryKey: ['kpi-dashboard'],
    queryFn: () => kpiApi.dashboard('MONTHLY'),
    staleTime: 300_000,
  })

  // GO 목록
  const { data: goList } = useQuery({
    queryKey: ['go-list'],
    queryFn: () => selectionApi.goList(14),
    staleTime: 300_000,
  })

  // 피드백 루프 — 결과 입력 대기 목록
  const { data: pendingJournals } = useQuery({
    queryKey: ['journal-pending'],
    queryFn: () => journalApi.pending(),
    staleTime: 60_000,
  })

  // 피드백 통계
  const { data: journalStats } = useQuery<JournalStats>({
    queryKey: ['journal-stats'],
    queryFn: () => journalApi.stats(),
    staleTime: 300_000,
  })

  // 투찰 실행 파이프라인
  const queryClient = useQueryClient()
  const { data: execSummary } = useQuery<ExecutionSummary>({
    queryKey: ['execution-summary'],
    queryFn: () => executionsApi.summary(),
    staleTime: 60_000,
  })
  const createExecMutation = useMutation({
    mutationFn: executionsApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['execution-summary'] })
      navigate('/executions')
    },
  })

  type PendingJournalItem = { journal_id: number; title: string; agency_name: string; bid_open_date: string | null; submitted_rate: number | null; recommended_rate: number | null }
  const pendingList: PendingJournalItem[] = ((pendingJournals as unknown as { items?: PendingJournalItem[] } | null)?.items ?? [])

  const activeExecCount =
    (execSummary?.status_counts?.['참여결정'] ?? 0) +
    (execSummary?.status_counts?.['투찰완료'] ?? 0) +
    (execSummary?.status_counts?.['개찰대기'] ?? 0)
  const todayClosings = execSummary?.today_closing ?? []

  const urgentList = (urgentBids?.items ?? []).filter((b: { bid_open_date: string | null }) => {
    const d = daysUntil(b.bid_open_date)
    return d !== null && d <= 5
  }).slice(0, 5)

  const topRec = (recommended ?? []).slice(0, 7)
  const goCount = (goList as { go: unknown[] } | null)?.go?.length ?? 0
  const winRate = kpi?.win_rate ?? overview?.avg_win_rate ?? 0
  const totalWins = kpi?.total_wins ?? 0
  const monthlyTarget = kpi?.monthly_target ?? 3

  const toggleCheck = (id: number) => {
    setCheckedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  return (
    <div className="flex flex-col min-h-full bg-slate-50">
      {/* 스티키 헤더 */}
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-sm border-b border-slate-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-[1440px] mx-auto w-full">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-slate-900 flex items-center gap-2">
              <Zap className="h-5 w-5 text-blue-600" />
              오늘의 입찰
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">{dateStr}</p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate('/bids')}
            className="gap-1.5 border-slate-200 text-slate-600 hover:bg-slate-50 hover:text-slate-900"
          >
            <Search className="h-3.5 w-3.5" />
            전체공고 검색
          </Button>
        </div>
      </div>

      {/* 콘텐츠 */}
      <div className="flex-1 p-6 space-y-5 max-w-[1440px] mx-auto w-full">

        {/* 상단 KPI 4개 */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {/* AI 추천 공고 */}
          <Card
            className="relative overflow-hidden bg-white border-slate-200 shadow-sm hover:shadow-md transition-shadow cursor-pointer"
            onClick={() => navigate('/bids?tab=recommend')}
          >
            <div className="absolute top-0 left-0 right-0 h-0.5 bg-blue-500" />
            <CardContent className="p-5">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-500">AI 추천 공고</p>
                  <p className="text-2xl font-bold mt-1 tabular-nums text-slate-900">{topRec.length}건</p>
                  <p className="text-xs text-slate-500 mt-1">오늘 검토 대상</p>
                </div>
                <div className="rounded-xl p-2.5 bg-blue-50 shrink-0">
                  <Sparkles className="h-5 w-5 text-blue-600" />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* 마감 임박 */}
          <Card
            className="relative overflow-hidden bg-white border-slate-200 shadow-sm hover:shadow-md transition-shadow cursor-pointer"
            onClick={() => navigate('/bids?sort=deadline')}
          >
            <div className="absolute top-0 left-0 right-0 h-0.5 bg-red-500" />
            <CardContent className="p-5">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-500">마감 임박</p>
                  <p className="text-2xl font-bold mt-1 tabular-nums text-slate-900">{urgentList.length}건</p>
                  <p className="text-xs text-slate-500 mt-1">D-5 이내</p>
                </div>
                <div className="rounded-xl p-2.5 bg-red-50 shrink-0">
                  <AlertCircle className="h-5 w-5 text-red-500" />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* 이번달 수주율 */}
          <Card
            className="relative overflow-hidden bg-white border-slate-200 shadow-sm hover:shadow-md transition-shadow cursor-pointer"
            onClick={() => navigate('/performance')}
          >
            <div className={cn('absolute top-0 left-0 right-0 h-0.5', winRate >= 0.3 ? 'bg-emerald-500' : winRate >= 0.2 ? 'bg-amber-500' : 'bg-red-500')} />
            <CardContent className="p-5">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-500">이번달 수주율</p>
                  <p className={cn('text-2xl font-bold mt-1 tabular-nums', winRate >= 0.3 ? 'text-emerald-600' : winRate >= 0.2 ? 'text-amber-600' : 'text-red-600')}>
                    {(winRate * 100).toFixed(1)}%
                  </p>
                  <p className="text-xs text-slate-500 mt-1">{totalWins}건 / 목표 {monthlyTarget}건</p>
                </div>
                <div className={cn('rounded-xl p-2.5 shrink-0', winRate >= 0.3 ? 'bg-emerald-50' : winRate >= 0.2 ? 'bg-amber-50' : 'bg-red-50')}>
                  <Trophy className={cn('h-5 w-5', winRate >= 0.3 ? 'text-emerald-600' : winRate >= 0.2 ? 'text-amber-600' : 'text-red-600')} />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* 진행중 투찰 */}
          <Card
            className="relative overflow-hidden bg-white border-slate-200 shadow-sm hover:shadow-md transition-shadow cursor-pointer"
            onClick={() => navigate('/executions')}
          >
            <div className={cn('absolute top-0 left-0 right-0 h-0.5', activeExecCount > 0 ? 'bg-violet-500' : 'bg-slate-300')} />
            <CardContent className="p-5">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-500">진행중 투찰</p>
                  <p className="text-2xl font-bold mt-1 tabular-nums text-slate-900">{activeExecCount}건</p>
                  <p className="text-xs text-slate-500 mt-1">
                    {todayClosings.length > 0
                      ? <span className="text-red-500 font-semibold">오늘 개찰 {todayClosings.length}건</span>
                      : '개찰대기·투찰완료·참여결정'}
                  </p>
                </div>
                <div className="rounded-xl p-2.5 bg-violet-50 shrink-0">
                  <ListChecks className="h-5 w-5 text-violet-600" />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* AI 추천 공고 목록 */}
          <div className="lg:col-span-2 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
                <Sparkles className="h-4 w-4 text-blue-500" />
                AI 추천 공고
                <span className="bg-blue-50 text-blue-600 border border-blue-200 text-xs font-semibold px-2 py-0.5 rounded-md ml-1">
                  수주가능성 순
                </span>
              </h2>
              <button
                className="text-xs text-blue-600 hover:text-blue-700 font-medium hover:underline"
                onClick={() => navigate('/bids?tab=recommend')}
              >
                전체보기 →
              </button>
            </div>

            {loadingRec ? (
              <div className="space-y-2">
                {[0, 1, 2].map((i) => <Skeleton key={i} className="h-20 w-full" />)}
              </div>
            ) : topRec.length === 0 ? (
              <Card className="bg-white border-slate-200">
                <CardContent className="py-10 text-center text-slate-500 text-sm">
                  추천 공고가 없습니다. 키워드 설정을 확인해주세요.
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-2">
                {topRec.map((b) => {
                  const days = daysUntil(b.open_date)
                  const isChecked = checkedIds.has(b.bid_id)
                  return (
                    <Card
                      key={b.bid_id}
                      className={cn(
                        'group cursor-pointer transition-all border bg-white',
                        isChecked
                          ? 'opacity-50 border-slate-200'
                          : days !== null && days <= 1
                            ? 'border-red-200 hover:border-red-300 hover:shadow-sm'
                            : 'border-slate-200 hover:border-blue-200 hover:shadow-md',
                      )}
                      onClick={() => navigate(`/bids/${b.bid_id}`)}
                    >
                      <CardContent className="p-4">
                        <div className="flex items-start gap-3">
                          {/* 체크 */}
                          <button
                            className="mt-0.5 shrink-0"
                            onClick={(e) => { e.stopPropagation(); toggleCheck(b.bid_id) }}
                          >
                            <CheckCircle2 className={cn(
                              'h-4 w-4 transition-colors',
                              isChecked ? 'text-emerald-500' : 'text-slate-200 group-hover:text-slate-300',
                            )} />
                          </button>

                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1.5 mb-1.5 flex-wrap">
                              <VerdictBadge score={b.score} />
                              {days !== null && days <= 5 && <DeadlineBadge days={days} />}
                            </div>
                            <p className="text-sm font-semibold text-slate-800 truncate group-hover:text-blue-700 transition-colors">
                              {b.title}
                            </p>
                            <div className="flex items-center gap-3 mt-1.5 text-xs text-slate-500">
                              <span className="flex items-center gap-1">
                                <Building2 className="h-3 w-3 shrink-0" />
                                <span className="truncate max-w-[140px]">{b.agency_name}</span>
                              </span>
                              <span className="font-mono shrink-0">{fmtAmt(b.base_amount)}원</span>
                              {b.open_date && (
                                <span className="flex items-center gap-1 shrink-0">
                                  <Clock className="h-3 w-3" />
                                  {new Date(b.open_date).toLocaleDateString('ko-KR')}
                                </span>
                              )}
                            </div>
                            <div className="mt-2">
                              <ScoreBar score={b.score} />
                            </div>
                          </div>

                          <div className="flex flex-col gap-1 shrink-0">
                            <Button
                              size="sm"
                              className="h-7 px-2.5 text-xs gap-1 bg-blue-600 hover:bg-blue-700 text-white"
                              onClick={(e) => { e.stopPropagation(); navigate(`/decision?bid=${b.bid_id}`) }}
                            >
                              <Crosshair className="h-3 w-3" />
                              AI 투찰 결정
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-7 px-2.5 text-xs gap-1 text-slate-500 hover:text-blue-600 hover:bg-blue-50"
                              onClick={(e) => { e.stopPropagation(); navigate(`/bids/${b.bid_id}?tab=strategy`) }}
                            >
                              전략
                              <ChevronRight className="h-3 w-3" />
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-7 px-2.5 text-xs gap-1 text-violet-600 hover:text-violet-700 hover:bg-violet-50"
                              disabled={createExecMutation.isPending}
                              onClick={(e) => {
                                e.stopPropagation()
                                createExecMutation.mutate({
                                  title: b.title,
                                  agency_name: b.agency_name,
                                  base_amount: b.base_amount,
                                  bid_open_date: b.open_date ?? undefined,
                                })
                              }}
                            >
                              <Plus className="h-3 w-3" />
                              등록
                            </Button>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  )
                })}
              </div>
            )}
          </div>

          {/* 우측 패널 */}
          <div className="space-y-4">
            {/* 마감 임박 */}
            <Card className="bg-white border-slate-200 shadow-sm">
              <CardHeader className="pb-2 pt-4 px-4">
                <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
                  <AlertCircle className="h-4 w-4 text-red-500" />
                  마감 임박
                </CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-4 space-y-1.5">
                {urgentList.length === 0 ? (
                  <p className="text-xs text-slate-500 py-3 text-center">D-5 이내 마감 공고 없음</p>
                ) : (
                  urgentList.map((b: { id: number; title: string; agency_name: string; base_amount: number; bid_open_date: string | null }) => {
                    const days = daysUntil(b.bid_open_date)
                    return (
                      <div
                        key={b.id}
                        className="flex items-center gap-2 cursor-pointer hover:bg-slate-50 rounded-lg p-2 -mx-1 transition-colors group"
                        onClick={() => navigate(`/bids/${b.id}`)}
                      >
                        <DeadlineBadge days={days} />
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-semibold text-slate-700 truncate group-hover:text-blue-700 transition-colors">
                            {b.title}
                          </p>
                          <p className="text-xs text-slate-500 truncate mt-0.5">
                            {b.agency_name} · {fmtAmt(b.base_amount)}원
                          </p>
                        </div>
                        <ChevronRight className="h-3 w-3 text-slate-300 group-hover:text-blue-400 transition-colors shrink-0" />
                      </div>
                    )
                  })
                )}
              </CardContent>
            </Card>

            {/* 오늘 개찰 마감 */}
            {todayClosings.length > 0 && (
              <Card className="bg-white border-red-200 shadow-sm ring-1 ring-red-100">
                <CardHeader className="pb-2 pt-4 px-4">
                  <CardTitle className="text-sm font-semibold text-red-700 flex items-center gap-1.5">
                    <Clock className="h-4 w-4 text-red-500 animate-pulse" />
                    오늘 개찰 마감
                    <span className="ml-auto bg-red-500 text-white text-xs font-bold px-1.5 py-0.5 rounded-full">
                      {todayClosings.length}건
                    </span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="px-4 pb-4 space-y-1.5">
                  {todayClosings.slice(0, 4).map((ex) => (
                    <div
                      key={ex.id}
                      className="flex items-center gap-2 cursor-pointer hover:bg-red-50 rounded-lg p-2 -mx-1 transition-colors group"
                      onClick={() => navigate('/executions')}
                    >
                      <div className="h-1.5 w-1.5 rounded-full bg-red-500 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-semibold text-slate-700 truncate group-hover:text-red-700 transition-colors">
                          {ex.title}
                        </p>
                        <p className="text-xs text-slate-500 truncate mt-0.5">
                          {ex.status} · {ex.agency_name ?? '-'}
                        </p>
                      </div>
                      <ChevronRight className="h-3 w-3 text-slate-300 group-hover:text-red-400 shrink-0" />
                    </div>
                  ))}
                  {todayClosings.length > 4 && (
                    <p className="text-xs text-slate-500 text-center pt-1">
                      +{todayClosings.length - 4}건 더보기 →
                    </p>
                  )}
                </CardContent>
              </Card>
            )}

            {/* 개찰 결과 입력 대기 */}
            {pendingList.length > 0 && (
              <Card className="bg-white border-amber-200 shadow-sm ring-1 ring-amber-100">
                <CardHeader className="pb-2 pt-4 px-4">
                  <CardTitle className="text-sm font-semibold text-amber-700 flex items-center gap-1.5">
                    <ClipboardCheck className="h-4 w-4 text-amber-500" />
                    개찰 결과 입력 대기
                    <span className="ml-auto bg-amber-500 text-white text-xs font-bold px-1.5 py-0.5 rounded-full">
                      {pendingList.length}건
                    </span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="px-4 pb-4 space-y-1.5">
                  {pendingList.slice(0, 4).map((j) => (
                    <div
                      key={j.journal_id}
                      className="flex items-center gap-2 cursor-pointer hover:bg-amber-50 rounded-lg p-2 -mx-1 transition-colors group"
                      onClick={() => navigate('/journal-history')}
                    >
                      <div className="h-1.5 w-1.5 rounded-full bg-amber-400 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-semibold text-slate-700 truncate group-hover:text-amber-700">
                          {j.title}
                        </p>
                        <p className="text-xs text-slate-500 mt-0.5">
                          {j.agency_name ?? '-'} · 개찰 {j.bid_open_date ? new Date(j.bid_open_date).toLocaleDateString('ko-KR') : '-'}
                        </p>
                      </div>
                      <ChevronRight className="h-3 w-3 text-slate-300 group-hover:text-amber-400 shrink-0" />
                    </div>
                  ))}
                  {pendingList.length > 4 && (
                    <p className="text-xs text-slate-500 text-center pt-1">
                      +{pendingList.length - 4}건 더보기 →
                    </p>
                  )}
                </CardContent>
              </Card>
            )}

            {/* AI 피드백 현황 */}
            {journalStats && journalStats.total > 0 && (
              <Card className="bg-white border-slate-200 shadow-sm">
                <CardHeader className="pb-2 pt-4 px-4">
                  <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
                    <BookOpen className="h-4 w-4 text-blue-500" />
                    AI 피드백 현황
                  </CardTitle>
                </CardHeader>
                <CardContent className="px-4 pb-4 space-y-2">
                  <div className="grid grid-cols-2 gap-2">
                    <div className="bg-slate-50 rounded-lg p-2.5 text-center">
                      <p className="text-xs text-slate-400">피드백 완결률</p>
                      <p className="text-base font-bold text-slate-800 mt-0.5">
                        {(journalStats.feedback_completeness * 100).toFixed(0)}%
                      </p>
                    </div>
                    <div className="bg-slate-50 rounded-lg p-2.5 text-center">
                      <p className="text-xs text-slate-400">사정율 MAE</p>
                      <p className="text-base font-bold text-blue-700 mt-0.5 font-mono">
                        {journalStats.avg_srate_mae != null ? (journalStats.avg_srate_mae * 100).toFixed(4) + '%' : '-'}
                      </p>
                    </div>
                  </div>
                  <div className="flex justify-between text-xs text-slate-500 border-t pt-2 mt-1">
                    <span>총 {journalStats.total}건 기록</span>
                    <span>결과 대기 {journalStats.pending_result}건</span>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* 이달 수주 현황 */}
            <Card className="bg-white border-slate-200 shadow-sm">
              <CardHeader className="pb-2 pt-4 px-4">
                <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
                  <BarChart2 className="h-4 w-4 text-blue-500" />
                  이달 수주 현황
                </CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-4 space-y-3">
                <div className="space-y-2">
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-500">수주 목표 달성</span>
                    <span className="font-semibold text-slate-700 tabular-nums">{totalWins} / {monthlyTarget}건</span>
                  </div>
                  <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
                    <div
                      className={cn(
                        'h-2 rounded-full transition-all',
                        totalWins >= monthlyTarget ? 'bg-emerald-500' : 'bg-blue-500',
                      )}
                      style={{ width: `${Math.min(100, (totalWins / Math.max(monthlyTarget, 1)) * 100)}%` }}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div className="bg-slate-50 border border-slate-100 rounded-xl p-3 text-center">
                    <p className="text-xs text-slate-500 font-medium">수주율</p>
                    <p className={cn(
                      'text-lg font-bold tabular-nums mt-0.5',
                      winRate >= 0.3 ? 'text-emerald-600' : winRate >= 0.2 ? 'text-amber-600' : 'text-red-500',
                    )}>
                      {(winRate * 100).toFixed(1)}%
                    </p>
                  </div>
                  <div className="bg-slate-50 border border-slate-100 rounded-xl p-3 text-center">
                    <p className="text-xs text-slate-500 font-medium">전월대비</p>
                    <p className="text-lg font-bold flex items-center justify-center gap-0.5 mt-0.5">
                      {overview?.win_rate_change_pct != null ? (
                        <>
                          {overview.win_rate_change_pct > 0
                            ? <TrendingUp className="h-4 w-4 text-emerald-500" />
                            : <TrendingDown className="h-4 w-4 text-red-500" />}
                          <span className={cn(
                            'tabular-nums',
                            overview.win_rate_change_pct > 0 ? 'text-emerald-600' : 'text-red-500',
                          )}>
                            {Math.abs(overview.win_rate_change_pct).toFixed(1)}%p
                          </span>
                        </>
                      ) : (
                        <span className="text-slate-500 text-sm">-</span>
                      )}
                    </p>
                  </div>
                </div>

                {kpi?.alerts && kpi.alerts.length > 0 && (
                  <div className="space-y-1.5">
                    {kpi.alerts.slice(0, 2).map((alert, i) => (
                      <div key={i} className="text-xs text-amber-700 bg-amber-50 border border-amber-100 rounded-lg px-2.5 py-1.5 flex items-start gap-1">
                        <AlertCircle className="h-3 w-3 shrink-0 mt-0.5" />
                        {alert}
                      </div>
                    ))}
                  </div>
                )}

                <Button
                  variant="ghost"
                  size="sm"
                  className="w-full h-8 text-xs text-slate-500 hover:text-blue-600 hover:bg-blue-50"
                  onClick={() => navigate('/performance')}
                >
                  성과센터 상세보기 →
                </Button>
              </CardContent>
            </Card>

            {/* 빠른 실행 */}
            <Card className="bg-white border-slate-200 shadow-sm">
              <CardHeader className="pb-2 pt-4 px-4">
                <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
                  <Calendar className="h-4 w-4 text-blue-500" />
                  빠른 실행
                </CardTitle>
              </CardHeader>
              <CardContent className="px-3 pb-3 space-y-0.5">
                {[
                  { label: 'AI 투찰 결정',    path: '/decision',       icon: Crosshair,  color: 'text-blue-600',   bg: 'bg-blue-50'    },
                  { label: '투찰 이력 분석',   path: '/journal-history',icon: BookOpen,   color: 'text-amber-600',  bg: 'bg-amber-50'   },
                  { label: '투찰 관리',        path: '/executions',     icon: ListChecks, color: 'text-violet-500', bg: 'bg-violet-50'  },
                  { label: '경쟁사 분석',      path: '/competitors',    icon: Building2,  color: 'text-purple-500', bg: 'bg-purple-50'  },
                  { label: 'GO 판정 공고',     path: '/bid-selection',  icon: Zap,        color: 'text-emerald-600',bg: 'bg-emerald-50' },
                  { label: '성과 대시보드',    path: '/performance',    icon: BarChart2,  color: 'text-slate-500',  bg: 'bg-slate-50'   },
                ].map((item) => (
                  <button
                    key={item.path}
                    className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs hover:bg-slate-50 transition-colors text-left group"
                    onClick={() => navigate(item.path)}
                  >
                    <div className={cn('flex h-6 w-6 items-center justify-center rounded-md shrink-0', item.bg)}>
                      <item.icon className={cn('h-3.5 w-3.5', item.color)} />
                    </div>
                    <span className="text-slate-600 group-hover:text-slate-900 font-medium transition-colors">{item.label}</span>
                    <ChevronRight className="h-3 w-3 text-slate-300 group-hover:text-slate-500 ml-auto shrink-0 transition-colors" />
                  </button>
                ))}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  )
}
