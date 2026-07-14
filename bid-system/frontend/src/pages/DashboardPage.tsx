import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import DashboardTabBar from '@/components/DashboardTabBar'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ComposedChart, Area,
} from 'recharts'
import {
  FileText, Users, TrendingUp, TrendingDown, Activity, ArrowUp, ArrowDown,
  Trophy, Building2, Zap, Star, Info, LayoutDashboard, Target, Bell, ChevronRight,
  Clock, AlertTriangle, CheckCircle2, FileSearch,
} from 'lucide-react'
import { statsApi, bidsApi, journalApi, preSpecApi } from '@/api'
import type { OverviewStatsWithChange, Bid, TopSrateTrend, BidRecommendItem, UpcomingOpening, JournalStats } from '@/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

interface AgencyStat {
  agency_id: number; agency_name: string
  bid_count: number; avg_rate: number | null; avg_competitor_count: number | null
}

interface StatCardDef {
  key: keyof OverviewStatsWithChange
  label: string
  unit: string
  icon: React.ComponentType<{ className?: string }>
  accentColor: string
  iconColor: string
  iconBg: string
  changeKey: keyof OverviewStatsWithChange | null
  higherIsBetter: boolean
  pct?: boolean
}

const STAT_CARDS: StatCardDef[] = [
  {
    key: 'total_bids', label: '전체 입찰 (24개월)', unit: '건',
    icon: FileText, accentColor: 'bg-blue-500', iconColor: 'text-blue-600', iconBg: 'bg-blue-50',
    changeKey: 'bid_count_change_pct', higherIsBetter: true,
  },
  {
    key: 'total_competitors', label: '등록 경쟁사', unit: '개사',
    icon: Users, accentColor: 'bg-purple-500', iconColor: 'text-purple-600', iconBg: 'bg-purple-50',
    changeKey: null, higherIsBetter: true,
  },
  {
    key: 'avg_win_rate', label: '평균 낙찰률', unit: '%',
    icon: TrendingUp, accentColor: 'bg-emerald-500', iconColor: 'text-emerald-600', iconBg: 'bg-emerald-50',
    changeKey: 'win_rate_change_pct', higherIsBetter: true, pct: true,
  },
  {
    key: 'avg_competitor_count', label: '평균 경쟁강도', unit: '개사',
    icon: Activity, accentColor: 'bg-amber-500', iconColor: 'text-amber-600', iconBg: 'bg-amber-50',
    changeKey: 'avg_competitors_change', higherIsBetter: false,
  },
]

function ChangeBadge({ value, higherIsBetter }: { value: number | null | undefined; higherIsBetter: boolean }) {
  if (value == null) return null
  const up = value > 0
  const isGood = higherIsBetter ? up : !up
  return (
    <span className={cn(
      'inline-flex items-center gap-0.5 text-xs font-semibold px-1.5 py-0.5 rounded-md',
      isGood
        ? 'text-emerald-700 bg-emerald-50 border border-emerald-200'
        : 'text-red-600 bg-red-50 border border-red-200',
    )}>
      {up ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />}
      {Math.abs(value).toFixed(1)}%
    </span>
  )
}

const GRADE_STYLE: Record<string, string> = {
  A: 'bg-emerald-100 text-emerald-700 border-emerald-300',
  B: 'bg-blue-100 text-blue-700 border-blue-300',
  C: 'bg-amber-100 text-amber-700 border-amber-300',
  D: 'bg-slate-100 text-slate-500 border-slate-300',
}

function GradeBadge({ grade }: { grade: string | null }) {
  if (!grade) return null
  return (
    <span className={cn(
      'inline-flex items-center justify-center w-6 h-6 rounded-md text-[11px] font-bold border shrink-0',
      GRADE_STYLE[grade] ?? GRADE_STYLE.D,
    )}>
      {grade}
    </span>
  )
}

function scoreBarColor(score: number | null) {
  if (!score) return 'bg-slate-200'
  if (score >= 75) return 'bg-emerald-500'
  if (score >= 55) return 'bg-blue-500'
  if (score >= 35) return 'bg-amber-400'
  return 'bg-slate-300'
}

function breakdownTooltip(b: BidRecommendItem['score_breakdown']): string {
  if (!b) return ''
  return [
    `경쟁강도: ${b.competition.pts}/${b.competition.max}pt — ${b.competition.note}`,
    `발주기관이력: ${b.personal_track.pts}/${b.personal_track.max}pt — ${b.personal_track.note}`,
    `시장추세: ${b.market_trend.pts}/${b.market_trend.max}pt — ${b.market_trend.note}`,
    `금액적합: ${b.amount_fit.pts}/${b.amount_fit.max}pt — ${b.amount_fit.note}`,
  ].join('\n')
}

function fmtAmt(n: number) {
  if (n >= 1e12) return (n / 1e12).toFixed(1) + '조'
  if (n >= 1e8)  return (n / 1e8).toFixed(0) + '억'
  if (n >= 1e4)  return (n / 1e4).toFixed(0) + '만'
  return n.toLocaleString()
}

export default function DashboardPage() {
  const navigate = useNavigate()

  const { data: overview, isLoading } = useQuery<OverviewStatsWithChange>({
    queryKey: ['overview', 24],
    queryFn: () => statsApi.overview(24),
  })

  const { data: allTime } = useQuery<OverviewStatsWithChange>({
    queryKey: ['overview', 60],
    queryFn: () => statsApi.overview(60),
    staleTime: 300_000,
  })

  const { data: agencies } = useQuery<AgencyStat[]>({
    queryKey: ['agency-stats', 12],
    queryFn: () => statsApi.agencies(12),
  })

  const { data: recentClosed } = useQuery<{ items: Bid[]; total: number }>({
    queryKey: ['recent-closed'],
    queryFn: () => bidsApi.list({ status: 'closed', sort_by: 'bid_open_date', size: 8 }),
    staleTime: 60_000,
  })

  const { data: topTrends } = useQuery<TopSrateTrend[]>({
    queryKey: ['top-srate-trends'],
    queryFn: () => statsApi.topSrateTrends(3),
    staleTime: 300_000,
  })

  const { data: recommendedBids, isLoading: isLoadingRecommended } = useQuery<BidRecommendItem[]>({
    queryKey: ['recommended-bids'],
    queryFn: () => bidsApi.recommended(5),
    staleTime: 300_000,
  })

  const { data: pendingJournals } = useQuery({
    queryKey: ['journal-pending'],
    queryFn: () => journalApi.pending(),
    staleTime: 60_000,
  })

  const { data: upcomingData } = useQuery({
    queryKey: ['upcoming-openings', 7],
    queryFn: () => bidsApi.upcomingOpenings(7),
    staleTime: 120_000,
  })

  const { data: journalStats } = useQuery<JournalStats>({
    queryKey: ['journal-stats-dash'],
    queryFn: () => journalApi.stats(),
    staleTime: 120_000,
  })

  const { data: preSpecSummary } = useQuery({
    queryKey: ['pre-spec-summary-dash', 14],
    queryFn: () => preSpecApi.summary(14),
    staleTime: 300_000,
  })

  const trend = (overview?.monthly_trend ?? []).map((d) => ({
    label:  `${d.year}-${String(d.month).padStart(2, '0')}`,
    건수:   d.bid_count,
    낙찰률: d.avg_rate ? +(d.avg_rate * 100).toFixed(4) : null,
  }))
  const topAgencies = (agencies ?? []).slice(0, 10)
  const recentWins = (recentClosed?.items ?? []).filter((b) => b.winner_rate != null).slice(0, 8)

  return (
    <div className="flex flex-col min-h-full bg-slate-50">
      {/* 스티키 헤더 */}
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-sm border-b border-slate-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-[1440px] mx-auto w-full">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-slate-900 flex items-center gap-2">
              <LayoutDashboard className="h-5 w-5 text-blue-600" />
              대시보드
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">최근 24개월 입찰 현황 · 전체 누적 통계</p>
          </div>

          {allTime && (
            <div className="flex items-center gap-6">
              <div className="text-right">
                <p className="text-xs text-slate-500 uppercase tracking-wide font-medium">누적 입찰</p>
                <p className="text-lg font-bold text-blue-600 tabular-nums">
                  {(allTime.total_bids ?? 0).toLocaleString()}
                  <span className="text-xs font-normal text-slate-500 ml-0.5">건</span>
                </p>
              </div>
              <div className="w-px h-8 bg-slate-200" />
              <div className="text-right">
                <p className="text-xs text-slate-500 uppercase tracking-wide font-medium">등록 경쟁사</p>
                <p className="text-lg font-bold text-purple-600 tabular-nums">
                  {(allTime.total_competitors ?? 0).toLocaleString()}
                  <span className="text-xs font-normal text-slate-500 ml-0.5">개사</span>
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 대시보드 탭 네비게이션 */}
      <DashboardTabBar />

      {/* 콘텐츠 */}
      <div className="flex-1 p-6 space-y-5 max-w-[1440px] mx-auto w-full">

        {/* 지금 할 일 — 액션 바 */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {/* AI 투찰 결정 */}
          <button
            onClick={() => navigate('/decision')}
            className="flex items-center gap-3 bg-blue-600 hover:bg-blue-700 text-white rounded-xl px-5 py-4 shadow-sm transition-colors text-left"
          >
            <div className="w-10 h-10 bg-blue-500 rounded-lg flex items-center justify-center shrink-0">
              <Target className="w-5 h-5" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-semibold text-sm">AI 투찰 결정</div>
              <div className="text-xs text-blue-200 mt-0.5">공고 선택 → 자동 분석 → 즉시 추천</div>
            </div>
            <ChevronRight className="w-4 h-4 text-blue-300 shrink-0" />
          </button>

          {/* 결과 입력 대기 */}
          <button
            onClick={() => navigate('/journal-history')}
            className={cn(
              'flex items-center gap-3 rounded-xl px-5 py-4 shadow-sm transition-colors text-left',
              (pendingJournals?.count ?? 0) > 0
                ? 'bg-amber-50 hover:bg-amber-100 border border-amber-200'
                : 'bg-white hover:bg-gray-50 border border-gray-200'
            )}
          >
            <div className={cn(
              'w-10 h-10 rounded-lg flex items-center justify-center shrink-0',
              (pendingJournals?.count ?? 0) > 0 ? 'bg-amber-100' : 'bg-gray-100'
            )}>
              <Bell className={cn('w-5 h-5', (pendingJournals?.count ?? 0) > 0 ? 'text-amber-600' : 'text-gray-400')} />
            </div>
            <div className="flex-1 min-w-0">
              <div className={cn('font-semibold text-sm', (pendingJournals?.count ?? 0) > 0 ? 'text-amber-800' : 'text-gray-700')}>
                개찰 결과 입력 대기
              </div>
              <div className={cn('text-xs mt-0.5', (pendingJournals?.count ?? 0) > 0 ? 'text-amber-600' : 'text-gray-400')}>
                {(pendingJournals?.count ?? 0) > 0
                  ? `${pendingJournals!.count}건 — AI 피드백 루프에 필요합니다`
                  : '결과 입력 대기 없음'}
              </div>
            </div>
            <ChevronRight className="w-4 h-4 text-gray-300 shrink-0" />
          </button>

          {/* 추천 공고 */}
          <button
            onClick={() => navigate('/bids?tab=recommend')}
            className="flex items-center gap-3 bg-white hover:bg-gray-50 border border-gray-200 rounded-xl px-5 py-4 shadow-sm transition-colors text-left"
          >
            <div className="w-10 h-10 bg-emerald-50 rounded-lg flex items-center justify-center shrink-0">
              <Star className="w-5 h-5 text-emerald-600" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-semibold text-sm text-gray-700">AI 추천 공고</div>
              <div className="text-xs text-gray-400 mt-0.5">
                {isLoadingRecommended ? '로딩 중...' : `${recommendedBids?.length ?? 0}건 추천 대기`}
              </div>
            </div>
            <ChevronRight className="w-4 h-4 text-gray-300 shrink-0" />
          </button>
        </div>

        {/* ── 개찰 임박 공고 + 최근 투찰 성과 ── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* 개찰 임박 공고 */}
          <Card className="bg-white border-slate-200 shadow-sm">
            <CardHeader className="px-5 pt-4 pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-red-500" />
                <CardTitle className="text-sm font-semibold text-slate-800">개찰 임박 공고</CardTitle>
                <span className="bg-slate-100 text-slate-500 border border-slate-200 text-xs font-semibold px-2 py-0.5 rounded-md ml-auto">
                  7일 이내
                </span>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              {!upcomingData || upcomingData.items.length === 0 ? (
                <p className="text-center text-slate-400 text-sm py-6">개찰 임박 공고 없음</p>
              ) : (
                <div className="divide-y divide-slate-100">
                  {upcomingData.items.slice(0, 6).map((item: UpcomingOpening) => {
                    const urgencyStyle =
                      item.urgency === 'today'    ? 'bg-red-50 border-red-200' :
                      item.urgency === 'tomorrow' ? 'bg-orange-50 border-orange-200' :
                      item.urgency === 'soon'     ? 'bg-amber-50 border-amber-200' :
                                                    'bg-white'
                    const badgeStyle =
                      item.urgency === 'today'    ? 'bg-red-500 text-white' :
                      item.urgency === 'tomorrow' ? 'bg-orange-400 text-white' :
                      item.urgency === 'soon'     ? 'bg-amber-400 text-white' :
                                                    'bg-slate-200 text-slate-600'
                    const urgencyLabel =
                      item.urgency === 'today'    ? 'D-Day' :
                      item.urgency === 'tomorrow' ? 'D-1' :
                      item.urgency === 'soon'     ? `D-${item.days_left}` :
                                                    `D-${item.days_left}`
                    return (
                      <div
                        key={item.id}
                        className={cn('flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-blue-50 transition-colors', urgencyStyle)}
                        onClick={() => navigate(`/decision?bid=${item.id}`)}
                      >
                        <span className={cn('text-xs font-bold px-2 py-0.5 rounded shrink-0', badgeStyle)}>
                          {urgencyLabel}
                        </span>
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-semibold text-slate-800 truncate">{item.title}</p>
                          <p className="text-[10px] text-slate-500 mt-0.5">{item.agency_name} · {fmtAmt(item.base_amount)}</p>
                        </div>
                        <ChevronRight className="w-3.5 h-3.5 text-blue-400 shrink-0" />
                      </div>
                    )
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          {/* 최근 투찰 성과 요약 */}
          <Card className="bg-white border-slate-200 shadow-sm">
            <CardHeader className="px-5 pt-4 pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Trophy className="h-4 w-4 text-amber-500" />
                <CardTitle className="text-sm font-semibold text-slate-800">최근 투찰 성과</CardTitle>
                <button
                  onClick={() => navigate('/kpi-dashboard')}
                  className="ml-auto text-xs text-blue-500 hover:text-blue-700 flex items-center gap-1"
                >
                  상세 KPI <ChevronRight className="w-3 h-3" />
                </button>
              </div>
            </CardHeader>
            <CardContent className="p-4">
              {!journalStats || journalStats.total === 0 ? (
                <div className="text-center py-6">
                  <p className="text-slate-400 text-sm">투찰 이력이 없습니다.</p>
                  <button
                    onClick={() => navigate('/decision')}
                    className="mt-2 text-xs text-blue-500 hover:text-blue-700"
                  >
                    AI 투찰 결정 시작 →
                  </button>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="grid grid-cols-3 gap-3">
                    <div className="text-center p-3 bg-slate-50 rounded-lg">
                      <div className={cn('text-xl font-bold tabular-nums',
                        journalStats.win_rate != null && journalStats.win_rate >= 0.35 ? 'text-emerald-600' :
                        journalStats.win_rate != null && journalStats.win_rate >= 0.20 ? 'text-blue-600' : 'text-amber-600'
                      )}>
                        {journalStats.win_rate != null ? `${(journalStats.win_rate * 100).toFixed(1)}%` : '—'}
                      </div>
                      <div className="text-[10px] text-slate-500 mt-0.5">저널 낙찰률</div>
                    </div>
                    <div className="text-center p-3 bg-slate-50 rounded-lg">
                      <div className="text-xl font-bold text-slate-800 tabular-nums">
                        {journalStats.wins}/{journalStats.total}
                      </div>
                      <div className="text-[10px] text-slate-500 mt-0.5">낙찰/전체</div>
                    </div>
                    <div className="text-center p-3 bg-slate-50 rounded-lg">
                      <div className={cn('text-xl font-bold tabular-nums',
                        journalStats.avg_rate_gap_loss != null && Math.abs(journalStats.avg_rate_gap_loss) <= 0.002
                          ? 'text-emerald-600' : 'text-amber-600'
                      )}>
                        {journalStats.avg_rate_gap_loss != null
                          ? `${(journalStats.avg_rate_gap_loss * 100).toFixed(2)}%`
                          : '—'}
                      </div>
                      <div className="text-[10px] text-slate-500 mt-0.5">패찰 rate gap</div>
                    </div>
                  </div>

                  {/* 전략별 최고 성과 */}
                  {journalStats.strategy_stats.length > 0 && (() => {
                    const best = journalStats.strategy_stats
                      .filter(s => s.total >= 3)
                      .sort((a, b) => (b.win_rate ?? 0) - (a.win_rate ?? 0))[0]
                    return best ? (
                      <div className="flex items-center gap-2 bg-emerald-50 border border-emerald-100 rounded-lg px-3 py-2">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                        <span className="text-xs text-emerald-700">
                          최고 성과 전략: <strong>{best.strategy}</strong> — 낙찰률 {best.win_rate != null ? `${(best.win_rate * 100).toFixed(1)}%` : '—'} ({best.wins}/{best.total}건)
                        </span>
                      </div>
                    ) : null
                  })()}

                  {/* 개선 필요 알림 */}
                  {journalStats.win_rate != null && journalStats.win_rate < 0.20 && journalStats.total >= 5 && (
                    <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-500 shrink-0 mt-0.5" />
                      <span className="text-xs text-amber-700">
                        낙찰률 20% 미만 — <button onClick={() => navigate('/kpi-dashboard')} className="underline font-medium">KPI 분석</button>에서 개선 전략을 확인하세요.
                      </span>
                    </div>
                  )}

                  <button
                    onClick={() => navigate('/journal-history')}
                    className="w-full text-xs text-blue-500 hover:text-blue-700 text-center py-1 border border-blue-100 rounded-lg hover:bg-blue-50 transition-colors"
                  >
                    전체 투찰 이력 보기 →
                  </button>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* ── 오늘 할 일 패널 ── */}
        {(pendingJournals?.count ?? 0) > 0 && (
          <Card className="bg-amber-50 border-amber-200 shadow-sm">
            <CardHeader className="pb-2 pt-4 px-5">
              <CardTitle className="text-sm font-semibold text-amber-800 flex items-center gap-2">
                <Bell className="h-4 w-4 text-amber-600" />
                오늘 할 일 — 개찰 결과 입력 대기 {pendingJournals!.count}건
              </CardTitle>
            </CardHeader>
            <CardContent className="px-5 pb-4">
              <div className="space-y-2">
                {(pendingJournals!.items as Record<string, unknown>[]).slice(0, 5).map((item) => (
                  <div
                    key={String(item.journal_id)}
                    className="flex items-center justify-between bg-white border border-amber-100 rounded-lg px-3 py-2 cursor-pointer hover:border-amber-300 transition-colors"
                    onClick={() => navigate(`/journal-history?journal_id=${item.journal_id}`)}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-semibold text-slate-800 truncate">{String(item.title ?? '제목 없음')}</div>
                      <div className="text-[10px] text-slate-500 mt-0.5">
                        {String(item.agency_name ?? '')} | 개찰 {item.bid_open_date ? String(item.bid_open_date).slice(0, 10) : '날짜 미정'}
                        {item.submitted_rate != null && ` | 투찰 ${((item.submitted_rate as number) * 100).toFixed(4)}%`}
                      </div>
                    </div>
                    <ChevronRight className="w-3.5 h-3.5 text-amber-400 shrink-0 ml-2" />
                  </div>
                ))}
                {pendingJournals!.count > 5 && (
                  <button
                    onClick={() => navigate('/journal-history')}
                    className="w-full text-xs text-amber-700 hover:text-amber-900 text-center py-1"
                  >
                    + {pendingJournals!.count - 5}건 더 보기
                  </button>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {/* KPI 카드 4개 */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {STAT_CARDS.map(({ key, label, unit, icon: Icon, accentColor, iconColor, iconBg, changeKey, higherIsBetter, pct }) => {
            const raw = overview?.[key as keyof OverviewStatsWithChange] as number | null | undefined
            const display = raw == null ? '-'
              : pct ? (raw * 100).toFixed(4) + unit
              : key === 'avg_competitor_count' ? raw.toFixed(1) + unit
              : raw.toLocaleString() + unit
            const changeVal = changeKey ? overview?.[changeKey as keyof OverviewStatsWithChange] as number | null | undefined : null

            return (
              <Card key={key} className="relative overflow-hidden bg-white border-slate-200 shadow-sm hover:shadow-md transition-shadow">
                <div className={cn('absolute top-0 left-0 right-0 h-0.5', accentColor)} />
                <CardContent className="p-5">
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-slate-500">{label}</p>
                      {isLoading ? (
                        <Skeleton className="h-8 w-24 mt-1" />
                      ) : (
                        <p className="text-2xl font-bold mt-1 tabular-nums text-slate-900">{display}</p>
                      )}
                      {changeVal != null && (
                        <div className="mt-2">
                          <ChangeBadge value={changeVal} higherIsBetter={higherIsBetter} />
                          <span className="text-xs text-slate-500 ml-1">전월 대비</span>
                        </div>
                      )}
                    </div>
                    <div className={cn('rounded-xl p-2.5 shrink-0 ml-3', iconBg)}>
                      <Icon className={cn('h-5 w-5', iconColor)} />
                    </div>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>

        {/* 이번 주 추천 공고 */}
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="px-5 pt-5 pb-3 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <Star className="h-4 w-4 text-amber-500" />
              <CardTitle className="text-sm font-semibold text-slate-800">이번 주 추천 공고</CardTitle>
              <span className="bg-slate-100 text-slate-500 border border-slate-200 text-xs font-semibold px-2 py-0.5 rounded-md ml-auto">
                개찰 7일 이내 · AI 점수 순
              </span>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {isLoadingRecommended ? (
              <div className="p-5 space-y-3">
                {[0, 1, 2].map((i) => <Skeleton key={i} className="h-14 w-full" />)}
              </div>
            ) : recommendedBids && recommendedBids.length > 0 ? (
              <div className="divide-y divide-slate-100">
                {recommendedBids.map((b) => (
                  <div
                    key={b.bid_id}
                    className="flex items-center gap-3 px-5 py-3.5 hover:bg-slate-50 transition-colors group"
                  >
                    <GradeBadge grade={b.grade} />
                    <div className="min-w-0 flex-1 cursor-pointer" onClick={() => navigate(`/bids/${b.bid_id}`)}>
                      <p className="text-sm font-semibold text-slate-800 truncate group-hover:text-blue-700 transition-colors">
                        {b.title}
                      </p>
                      <div className="flex items-center gap-2 mt-0.5">
                        <Building2 className="h-3 w-3 text-slate-500 shrink-0" />
                        <span className="text-xs text-slate-500 truncate">{b.agency_name}</span>
                        {b.open_date && (
                          <span className="text-xs text-slate-500 shrink-0">
                            · {new Date(b.open_date).toLocaleDateString('ko-KR')}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 mt-1.5">
                        <div className="flex-1 bg-slate-100 rounded-full h-1.5 overflow-hidden">
                          <div
                            className={cn('h-1.5 rounded-full transition-all', scoreBarColor(b.score))}
                            style={{ width: `${b.score ?? 0}%` }}
                          />
                        </div>
                        <span className="text-xs font-mono text-slate-500 shrink-0 w-8 text-right">
                          {b.score?.toFixed(0) ?? '-'}점
                        </span>
                        {b.score_breakdown && (
                          <span title={breakdownTooltip(b.score_breakdown)} className="inline-flex shrink-0">
                            <Info className="h-3 w-3 text-slate-300 cursor-help hover:text-slate-500 transition-colors" />
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-1.5 shrink-0">
                      <p className="text-xs font-semibold text-slate-500 font-mono">{fmtAmt(b.base_amount)}</p>
                      <button
                        onClick={() => navigate(`/decision?bid=${b.bid_id}`)}
                        className="flex items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-800 bg-blue-50 hover:bg-blue-100 px-2 py-0.5 rounded-full transition-colors"
                      >
                        AI 분석 <ChevronRight className="w-3 h-3" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-center text-slate-500 text-sm py-10">이번 주 개찰 예정 공고가 없습니다</p>
            )}
          </CardContent>
        </Card>

        {/* 수주 예보 미니 패널 */}
        {preSpecSummary && (preSpecSummary.total > 0 || preSpecSummary.matched > 0) && (
          <Card className="bg-white border-slate-200 shadow-sm">
            <CardHeader className="px-5 pt-4 pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <FileSearch className="h-4 w-4 text-violet-500" />
                <CardTitle className="text-sm font-semibold text-slate-800">수주 예보 — 사전규격</CardTitle>
                <span className="bg-slate-100 text-slate-500 border border-slate-200 text-xs font-semibold px-2 py-0.5 rounded-md ml-auto">
                  최근 14일
                </span>
                <button
                  onClick={() => navigate('/pre-spec')}
                  className="text-xs text-blue-500 hover:text-blue-700 flex items-center gap-1"
                >
                  전체 보기 <ChevronRight className="w-3 h-3" />
                </button>
              </div>
            </CardHeader>
            <CardContent className="p-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="text-center p-3 bg-violet-50 rounded-lg">
                  <div className="text-xl font-bold text-violet-700 tabular-nums">{preSpecSummary.total.toLocaleString()}</div>
                  <div className="text-[10px] text-slate-500 mt-0.5">사전규격 등록</div>
                </div>
                <div className="text-center p-3 bg-emerald-50 rounded-lg">
                  <div className="text-xl font-bold text-emerald-600 tabular-nums">{preSpecSummary.matched.toLocaleString()}</div>
                  <div className="text-[10px] text-slate-500 mt-0.5">공고 매핑 완료</div>
                </div>
                <div className="text-center p-3 bg-blue-50 rounded-lg">
                  <div className="text-xl font-bold text-blue-600 tabular-nums">{preSpecSummary.agencies.toLocaleString()}</div>
                  <div className="text-[10px] text-slate-500 mt-0.5">발주기관 수</div>
                </div>
                <div className="text-center p-3 bg-amber-50 rounded-lg">
                  <div className="text-xl font-bold text-amber-600 tabular-nums">
                    {preSpecSummary.total_amount != null
                      ? (preSpecSummary.total_amount / 1e8).toFixed(0) + '억'
                      : '-'}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5">총 추정금액</div>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* 월별 추이 */}
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="px-5 pt-5 pb-3 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-blue-500" />
              <CardTitle className="text-sm font-semibold text-slate-800">월별 입찰 건수 · 낙찰률 추이</CardTitle>
              <span className="bg-slate-100 text-slate-500 border border-slate-200 text-xs font-semibold px-2 py-0.5 rounded-md ml-auto">
                24개월
              </span>
            </div>
          </CardHeader>
          <CardContent className="p-5">
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={trend} margin={{ left: -10, right: 10 }}>
                <defs>
                  <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.7} />
                    <stop offset="100%" stopColor="#3b82f6" stopOpacity={0.3} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="label" tick={{ fontSize: 12, fill: '#475569' }} interval={2} />
                <YAxis yAxisId="left" tick={{ fontSize: 12, fill: '#475569' }} />
                <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 12, fill: '#475569' }} unit="%" />
                <Tooltip
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e2e8f0', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                  formatter={(v: number, n: string) => [n === '낙찰률' ? v + '%' : v + '건', n]}
                />
                <Bar yAxisId="left" dataKey="건수" fill="url(#barGradient)" stroke="#3b82f6" strokeWidth={1} radius={[3, 3, 0, 0]} />
                <Line yAxisId="right" type="monotone" dataKey="낙찰률" stroke="#10b981" dot={false} strokeWidth={2} />
              </ComposedChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* 사정율 트렌드 알림 */}
        {topTrends && topTrends.length > 0 && (
          <Card className="bg-white border-slate-200 shadow-sm">
            <CardHeader className="px-5 pt-5 pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-amber-500" />
                <CardTitle className="text-sm font-semibold text-slate-800">사정율 트렌드 알림</CardTitle>
                <span className="bg-slate-100 text-slate-500 border border-slate-200 text-xs font-semibold px-2 py-0.5 rounded-md ml-auto">
                  최근 3개월 기준
                </span>
              </div>
            </CardHeader>
            <CardContent className="p-5">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {topTrends.map((t) => (
                  <div
                    key={t.agency_id}
                    className={cn(
                      'rounded-xl border p-4',
                      t.direction === 'up'   ? 'border-red-200  bg-red-50/60'   :
                      t.direction === 'down' ? 'border-blue-200 bg-blue-50/60'  :
                                              'border-slate-200 bg-slate-50',
                    )}
                  >
                    <div className="flex items-center gap-1.5 mb-2">
                      {t.direction === 'up'   ? <TrendingUp   className="h-3.5 w-3.5 text-red-500  shrink-0" /> :
                       t.direction === 'down' ? <TrendingDown className="h-3.5 w-3.5 text-blue-500 shrink-0" /> :
                                                <ArrowUp      className="h-3.5 w-3.5 text-slate-500 shrink-0" />}
                      <span className="text-xs font-semibold text-slate-700 truncate">{t.agency_name}</span>
                      <span className={cn(
                        'ml-auto text-xs font-mono font-bold shrink-0',
                        t.direction === 'up' ? 'text-red-600' : t.direction === 'down' ? 'text-blue-600' : 'text-slate-500',
                      )}>
                        {t.delta > 0 ? '+' : ''}{(t.delta * 100).toFixed(2)}%p
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 leading-snug">{t.signal}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* 최근 낙찰현황 + 발주기관 TOP10 */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* 최근 낙찰현황 */}
          <Card className="bg-white border-slate-200 shadow-sm">
            <CardHeader className="px-5 pt-5 pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Trophy className="h-4 w-4 text-amber-500" />
                <CardTitle className="text-sm font-semibold text-slate-800">최근 낙찰현황</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <div className="divide-y divide-slate-100">
                {recentWins.length === 0 ? (
                  <p className="text-center text-slate-500 text-sm py-10">데이터 없음</p>
                ) : recentWins.map((b, idx) => (
                  <div
                    key={b.id}
                    className={cn(
                      'flex items-center gap-3 px-5 py-3 cursor-pointer transition-colors group',
                      idx % 2 === 0 ? 'bg-white' : 'bg-slate-50/50',
                      'hover:bg-blue-50/50',
                    )}
                    onClick={() => navigate(`/bids/${b.id}`)}
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-slate-800 truncate group-hover:text-blue-700 transition-colors">
                        {b.title}
                      </p>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <Building2 className="h-3 w-3 text-slate-500 shrink-0" />
                        <span className="text-xs text-slate-500 truncate">{b.agency_name}</span>
                        {b.bid_open_date && (
                          <span className="text-xs text-slate-500 shrink-0">
                            · {new Date(b.bid_open_date).toLocaleDateString('ko-KR')}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <p className="text-sm font-bold font-mono text-blue-600 tabular-nums">
                        {b.winner_rate ? (b.winner_rate * 100).toFixed(4) + '%' : '-'}
                      </p>
                      <p className="text-xs text-slate-500">{fmtAmt(b.base_amount)}</p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* 발주기관 TOP10 */}
          <Card className="bg-white border-slate-200 shadow-sm">
            <CardHeader className="px-5 pt-5 pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Zap className="h-4 w-4 text-amber-500" />
                <CardTitle className="text-sm font-semibold text-slate-800">발주기관 입찰 건수 TOP 10</CardTitle>
                <span className="bg-slate-100 text-slate-500 border border-slate-200 text-xs font-semibold px-2 py-0.5 rounded-md ml-auto">
                  12개월
                </span>
              </div>
            </CardHeader>
            <CardContent className="p-5">
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={topAgencies} layout="vertical" margin={{ left: 80, right: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis type="number" tick={{ fontSize: 12, fill: '#475569' }} />
                  <YAxis
                    type="category"
                    dataKey="agency_name"
                    tick={{ fontSize: 10, fill: '#64748b' }}
                    width={80}
                    tickFormatter={(v: string) => v.length > 8 ? v.slice(0, 8) + '…' : v}
                  />
                  <Tooltip
                    contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e2e8f0', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                    formatter={(v: number) => [v + '건', '입찰 건수']}
                  />
                  <Bar dataKey="bid_count" fill="#3b82f6" radius={[0, 3, 3, 0]} opacity={0.85} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
