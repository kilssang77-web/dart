import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ComposedChart, Area,
} from 'recharts'
import {
  FileText, Users, TrendingUp, TrendingDown, Activity, ArrowUp, ArrowDown,
  Trophy, Building2, Zap, Star, Info, LayoutDashboard,
} from 'lucide-react'
import { statsApi, bidsApi } from '@/api'
import type { OverviewStatsWithChange, Bid, TopSrateTrend, BidRecommendItem } from '@/types'
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
    `발주처이력: ${b.personal_track.pts}/${b.personal_track.max}pt — ${b.personal_track.note}`,
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

  const trend = (overview?.monthly_trend ?? []).map((d) => ({
    label:  `${d.year}-${String(d.month).padStart(2, '0')}`,
    건수:   d.bid_count,
    낙찰률: d.avg_rate ? +(d.avg_rate * 100).toFixed(2) : null,
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
                <p className="text-[10px] text-slate-400 uppercase tracking-wide font-medium">누적 입찰</p>
                <p className="text-lg font-bold text-blue-600 tabular-nums">
                  {(allTime.total_bids ?? 0).toLocaleString()}
                  <span className="text-xs font-normal text-slate-400 ml-0.5">건</span>
                </p>
              </div>
              <div className="w-px h-8 bg-slate-200" />
              <div className="text-right">
                <p className="text-[10px] text-slate-400 uppercase tracking-wide font-medium">등록 경쟁사</p>
                <p className="text-lg font-bold text-purple-600 tabular-nums">
                  {(allTime.total_competitors ?? 0).toLocaleString()}
                  <span className="text-xs font-normal text-slate-400 ml-0.5">개사</span>
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 콘텐츠 */}
      <div className="flex-1 p-6 space-y-5 max-w-[1440px] mx-auto w-full">

        {/* KPI 카드 4개 */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {STAT_CARDS.map(({ key, label, unit, icon: Icon, accentColor, iconColor, iconBg, changeKey, higherIsBetter, pct }) => {
            const raw = overview?.[key as keyof OverviewStatsWithChange] as number | null | undefined
            const display = raw == null ? '-'
              : pct ? (raw * 100).toFixed(2) + unit
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
                          <span className="text-[10px] text-slate-400 ml-1">전월 대비</span>
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
                    className="flex items-center gap-3 px-5 py-3.5 hover:bg-slate-50 cursor-pointer transition-colors group"
                    onClick={() => navigate(`/bids/${b.bid_id}`)}
                  >
                    <GradeBadge grade={b.grade} />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-slate-800 truncate group-hover:text-blue-700 transition-colors">
                        {b.title}
                      </p>
                      <div className="flex items-center gap-2 mt-0.5">
                        <Building2 className="h-3 w-3 text-slate-400 shrink-0" />
                        <span className="text-xs text-slate-400 truncate">{b.agency_name}</span>
                        {b.open_date && (
                          <span className="text-[10px] text-slate-400 shrink-0">
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
                        <span className="text-[10px] font-mono text-slate-400 shrink-0 w-8 text-right">
                          {b.score?.toFixed(0) ?? '-'}점
                        </span>
                        {b.score_breakdown && (
                          <span title={breakdownTooltip(b.score_breakdown)} className="inline-flex shrink-0">
                            <Info className="h-3 w-3 text-slate-300 cursor-help hover:text-slate-500 transition-colors" />
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <p className="text-xs font-semibold text-slate-500 font-mono">{fmtAmt(b.base_amount)}</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-center text-slate-400 text-sm py-10">이번 주 개찰 예정 공고가 없습니다</p>
            )}
          </CardContent>
        </Card>

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
            <ResponsiveContainer width="100%" height={220}>
              <ComposedChart data={trend} margin={{ left: -10, right: 10 }}>
                <defs>
                  <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.25} />
                    <stop offset="100%" stopColor="#3b82f6" stopOpacity={0.05} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#94a3b8' }} interval={2} />
                <YAxis yAxisId="left" tick={{ fontSize: 11, fill: '#94a3b8' }} />
                <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11, fill: '#94a3b8' }} unit="%" />
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
                                                <ArrowUp      className="h-3.5 w-3.5 text-slate-400 shrink-0" />}
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
                  <p className="text-center text-slate-400 text-sm py-10">데이터 없음</p>
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
                        <Building2 className="h-3 w-3 text-slate-400 shrink-0" />
                        <span className="text-xs text-slate-400 truncate">{b.agency_name}</span>
                        {b.bid_open_date && (
                          <span className="text-[10px] text-slate-400 shrink-0">
                            · {new Date(b.bid_open_date).toLocaleDateString('ko-KR')}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <p className="text-sm font-bold font-mono text-blue-600 tabular-nums">
                        {b.winner_rate ? (b.winner_rate * 100).toFixed(2) + '%' : '-'}
                      </p>
                      <p className="text-[10px] text-slate-400">{fmtAmt(b.base_amount)}</p>
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
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={topAgencies} layout="vertical" margin={{ left: 80, right: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis type="number" tick={{ fontSize: 11, fill: '#94a3b8' }} />
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
